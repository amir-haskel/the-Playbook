"""Trigger script execution and stream stdout/stderr over SSE."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import store
from ..executor import _DONE, manager
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
    manager.start(execution, action, payload.values)
    return {"execution_id": execution.id, "status": execution.status.value}


@router.get("/stream/{execution_id}")
async def stream_execution(execution_id: str, request: Request) -> StreamingResponse:
    execution = manager.get(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            item = await execution.queue.get()
            if item is _DONE:
                payload = {
                    "status": execution.status.value,
                    "exit_code": execution.exit_code,
                    "artifacts": [a.model_dump() for a in execution.artifacts],
                }
                yield _sse("status", payload)
                break
            channel, text = item
            yield _sse(channel, {"line": text})

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
