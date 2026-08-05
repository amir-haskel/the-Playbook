"""Trigger script execution and stream stdout/stderr over SSE."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import database as db
from .. import store
from ..executor import _TERMINAL, manager
from ..models import ExecuteRequest

router = APIRouter(prefix="/api/v1", tags=["execute"])


@router.post("/execute/{action_id}")
async def execute_action(action_id: str, payload: ExecuteRequest) -> dict:
    action = store.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")

    # Validate required parameters are present and non-empty.
    missing = [
        p.name
        for p in action.parameters
        if p.required and _is_blank(payload.values.get(p.name, p.default))
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required parameter(s): {', '.join(missing)}",
        )

    # Number params must be numeric and non-negative.
    for p in action.parameters:
        if p.type.value != "number":
            continue
        value = payload.values.get(p.name, p.default)
        if _is_blank(value):
            continue
        try:
            if float(value) < 0:
                raise HTTPException(
                    status_code=422, detail=f"'{p.name}' must be 0 or greater"
                )
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail=f"'{p.name}' must be a number"
            )

    execution = manager.create(action)
    store.prune_executions()  # keep history within the configured limit
    manager.start(execution, action, payload.values)
    return {"execution_id": execution.id, "status": execution.status.value}


@router.get("/executions")
def list_executions(limit: int = 50) -> list[dict]:
    """Return recent executions (newest first) for the history view."""
    limit = max(1, min(int(limit), 500))
    rows = db.query_all(
        "SELECT id, action_id, action_title, status, created_at, finished_at "
        "FROM executions ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in rows]


@router.post("/executions/{execution_id}/stop")
async def stop_execution(execution_id: str) -> dict:
    """Gracefully stop a running execution."""
    if not manager.stop(execution_id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"stopped": True}


@router.get("/stream/{execution_id}")
async def stream_execution(execution_id: str, request: Request) -> StreamingResponse:
    execution = manager.get(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    async def event_generator():
        # Poll the buffered line list so a client can disconnect and re-attach
        # later and still replay the full output from the beginning.
        idx = 0
        while True:
            if await request.is_disconnected():
                # Client closed the modal; the process keeps running.
                return

            lines = execution.lines
            while idx < len(lines):
                channel, text = lines[idx]
                idx += 1
                yield _sse(channel, {"line": text})

            if execution.status in _TERMINAL and idx >= len(execution.lines):
                payload = {
                    "status": execution.status.value,
                    "exit_code": execution.exit_code,
                    "artifacts": [
                        {"file_id": a.file_id, "filename": a.filename, "size": a.size}
                        for a in execution.artifacts
                    ],
                }
                yield _sse("status", payload)
                return

            await asyncio.sleep(0.15)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx/openshift)
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")
