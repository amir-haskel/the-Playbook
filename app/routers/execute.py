"""Trigger script execution and stream stdout/stderr over SSE."""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import database as db
from .. import store
from ..executor import _TERMINAL, load_persisted_console, manager
from ..models import ExecuteRequest

router = APIRouter(prefix="/api/v1", tags=["execute"])

# SSE response headers shared by the live and replay streams.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx/openshift)
}

# Poll cadence for new buffered lines (responsiveness) and the maximum silence
# before an SSE keepalive comment is emitted so idle connections stay warm and
# proxies/load balancers don't drop a quiet-but-alive stream.
_POLL_SECONDS = 0.15
_HEARTBEAT_SECONDS = 10.0


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


@router.get("/executions/stats")
def executions_stats() -> dict:
    """Counts for the history control's badge — how many stored runs succeeded."""
    ok = db.query_one("SELECT COUNT(*) AS n FROM executions WHERE status = ?", ("SUCCESS",))
    total = db.query_one("SELECT COUNT(*) AS n FROM executions")
    return {
        "success": int(ok["n"]) if ok else 0,
        "total": int(total["n"]) if total else 0,
    }


@router.post("/executions/{execution_id}/stop")
async def stop_execution(execution_id: str) -> dict:
    """Gracefully stop a running execution."""
    if not manager.stop(execution_id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"stopped": True}


@router.get("/stream/{execution_id}")
async def stream_execution(execution_id: str, request: Request) -> StreamingResponse:
    execution = manager.get(execution_id)
    if execution is not None:
        # Live (or still in-memory) execution: poll the in-memory buffer.
        return StreamingResponse(
            _live_generator(execution, request),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # Not in memory. It may be a historical run whose output was persisted to
    # disk before a restart. If a DB row exists, replay the durable log; only a
    # truly unknown id 404s.
    row = db.query_one(
        "SELECT id, status, exit_code FROM executions WHERE id=?", (execution_id,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    return StreamingResponse(
        _replay_generator(execution_id, dict(row), request),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _resume_index(request: Request) -> int:
    """Return the first line index to send, honoring the ``Last-Event-ID`` header.

    The browser's ``EventSource`` automatically re-sends the id of the last event
    it received as ``Last-Event-ID`` when it reconnects. Our stdout/stderr events
    carry ``id: <lineIndex>``, so resuming from ``N + 1`` replays exactly the
    lines the client has not seen — no duplicates, no gaps. Absent/invalid header
    means "start from the beginning".
    """
    raw = request.headers.get("last-event-id")
    if raw is None:
        return 0
    try:
        n = int(raw.strip())
    except (TypeError, ValueError):
        return 0
    return n + 1 if n >= 0 else 0


async def _live_generator(execution, request: Request):
    # Poll the buffered line list so a client can disconnect and re-attach
    # later and still replay the full output. On an automatic EventSource
    # reconnect the Last-Event-ID header lets us resume from where the client
    # left off instead of replaying from the top.
    idx = _resume_index(request)
    last_send = time.monotonic()
    while True:
        if await request.is_disconnected():
            # Client closed the modal; the process keeps running.
            return

        lines = execution.lines
        while idx < len(lines):
            channel, text = lines[idx]
            yield _sse(channel, {"line": text}, event_id=idx)
            idx += 1
            last_send = time.monotonic()

        if execution.status in _TERMINAL and idx >= len(execution.lines):
            payload = {
                "status": execution.status.value,
                "exit_code": execution.exit_code,
                "artifacts": [
                    {"file_id": a.file_id, "filename": a.filename, "size": a.size}
                    for a in execution.artifacts
                ],
            }
            # Terminal status carries no id (nothing to resume past it).
            yield _sse("status", payload)
            return

        # Emit an SSE comment as a keepalive during silence so an idle-but-alive
        # connection is never dropped by a proxy/LB timeout. Comment lines begin
        # with ':' and are ignored by EventSource clients.
        now = time.monotonic()
        if now - last_send >= _HEARTBEAT_SECONDS:
            yield ": keepalive\n\n"
            last_send = now

        await asyncio.sleep(_POLL_SECONDS)


async def _replay_generator(execution_id: str, row: dict, request: Request):
    """Replay a persisted historical run from durable storage, then close.

    Used post-restart when the in-memory ``Execution`` is gone. Emits the stored
    console lines followed by a terminal ``status`` event carrying the artifacts
    recorded in the DB (which still live on disk under the output dir). Lines
    carry ``id: <lineIndex>`` and honor ``Last-Event-ID`` so a reconnect resumes
    without duplication, matching the live stream.
    """
    lines = load_persisted_console(execution_id)
    if lines is None:
        # No durable log — the run was interrupted mid-flight by the restart and
        # reconciled to a terminal state on boot.
        yield _sse(
            "stderr",
            {"line": "[opspulse] output not available (server restarted during this run)."},
        )
    else:
        start = _resume_index(request)
        for i in range(start, len(lines)):
            yield _sse("stdout", {"line": lines[i]}, event_id=i)

    art_rows = db.query_all(
        "SELECT file_id, filename, size FROM artifacts WHERE execution_id=?",
        (execution_id,),
    )
    payload = {
        "status": row["status"],
        "exit_code": row["exit_code"],
        "artifacts": [dict(a) for a in art_rows],
    }
    yield _sse("status", payload)


def _sse(event: str, data: dict, event_id: int | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event}\ndata: {json.dumps(data)}\n\n"


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")
