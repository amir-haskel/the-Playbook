"""Script execution engine with live SSE streaming.

An execution:
  1. resolves + validates the action's script (confined to SCRIPTS_DIR),
  2. spawns it via asyncio.subprocess with inputs passed BOTH as environment
     variables and as ``--name value`` CLI args,
  3. streams stdout/stderr line-by-line into an asyncio.Queue that the SSE
     endpoint drains,
  4. on exit, scans the per-execution output directory and registers any
     generated files as downloadable artifacts.

Live output lives only in memory (the queue); the DB keeps execution status and
artifact metadata for history/download.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import database as db
from . import scripts as script_utils
from .config import settings
from .models import Action, ArtifactInfo, ExecutionState, Parameter

# Sentinel pushed onto a queue to signal the stream is complete.
_DONE = object()


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class Execution:
    id: str
    action_id: str
    status: ExecutionState = ExecutionState.PENDING
    exit_code: int | None = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    artifacts: list[ArtifactInfo] = field(default_factory=list)
    output_dir: Path | None = None
    error: str | None = None


class ExecutionManager:
    """Owns in-flight and recently completed executions."""

    def __init__(self) -> None:
        self._executions: dict[str, Execution] = {}

    def get(self, execution_id: str) -> Execution | None:
        return self._executions.get(execution_id)

    # ------------------------------------------------------------------ #
    def create(self, action: Action) -> Execution:
        execution_id = uuid.uuid4().hex
        output_dir = settings.outputs_dir / execution_id
        subdir = action.output_subdir.strip("/\\")
        if subdir:
            output_dir = output_dir / subdir
        output_dir.mkdir(parents=True, exist_ok=True)

        execution = Execution(
            id=execution_id, action_id=action.id, output_dir=output_dir
        )
        self._executions[execution_id] = execution

        db.execute(
            "INSERT INTO executions (id, action_id, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            (execution_id, action.id, execution.status.value, _utcnow()),
        )
        return execution

    # ------------------------------------------------------------------ #
    def start(self, execution: Execution, action: Action, values: dict[str, Any]) -> None:
        """Kick off the subprocess as a background task."""
        asyncio.create_task(self._run(execution, action, values))

    async def _run(
        self, execution: Execution, action: Action, values: dict[str, Any]
    ) -> None:
        try:
            script = script_utils.resolve_script(action.script_path)
            argv = script_utils.build_command(script, action.interpreter)
        except script_utils.ScriptError as exc:
            await self._fail(execution, f"[opspulse] {exc}")
            return

        env_extra, cli_args = _build_inputs(action.parameters, values)
        argv = argv + cli_args

        env = os.environ.copy()
        env.update(env_extra)
        env["OUTPUTS_DIR"] = str(execution.output_dir)
        env["OPSPULSE_EXECUTION_ID"] = execution.id

        await self._set_status(execution, ExecutionState.RUNNING)
        await execution.queue.put(("stdout", f"$ {' '.join(argv)}"))

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(script.parent),
                env=env,
            )
        except OSError as exc:
            await self._fail(execution, f"[opspulse] failed to launch script: {exc}")
            return

        await asyncio.gather(
            self._pump(execution, proc.stdout, "stdout"),
            self._pump(execution, proc.stderr, "stderr"),
        )
        exit_code = await proc.wait()
        execution.exit_code = exit_code

        self._scan_artifacts(execution)
        state = ExecutionState.SUCCESS if exit_code == 0 else ExecutionState.FAILED
        await self._set_status(execution, state, finished=True)
        await execution.queue.put(_DONE)

    # ------------------------------------------------------------------ #
    async def _pump(self, execution: Execution, stream: Any, channel: str) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            await execution.queue.put((channel, text))

    def _scan_artifacts(self, execution: Execution) -> None:
        out_dir = execution.output_dir
        if not out_dir or not out_dir.exists():
            return
        for path in sorted(out_dir.rglob("*")):
            if not path.is_file():
                continue
            file_id = uuid.uuid4().hex
            size = path.stat().st_size
            db.execute(
                "INSERT INTO artifacts (file_id, execution_id, path, filename, "
                "size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (file_id, execution.id, str(path), path.name, size, _utcnow()),
            )
            execution.artifacts.append(
                ArtifactInfo(file_id=file_id, filename=path.name, size=size)
            )

    async def _set_status(
        self, execution: Execution, state: ExecutionState, finished: bool = False
    ) -> None:
        execution.status = state
        if finished:
            db.execute(
                "UPDATE executions SET status=?, exit_code=?, finished_at=? WHERE id=?",
                (state.value, execution.exit_code, _utcnow(), execution.id),
            )
        else:
            db.execute(
                "UPDATE executions SET status=? WHERE id=?",
                (state.value, execution.id),
            )

    async def _fail(self, execution: Execution, message: str) -> None:
        execution.error = message
        execution.exit_code = 1
        await execution.queue.put(("stderr", message))
        await self._set_status(execution, ExecutionState.FAILED, finished=True)
        await execution.queue.put(_DONE)


def _build_inputs(
    parameters: list[Parameter], values: dict[str, Any]
) -> tuple[dict[str, str], list[str]]:
    """Translate submitted values into (env vars, CLI args).

    Each parameter becomes an env var named exactly as the parameter, AND a
    ``--name value`` CLI arg. Booleans: env "true"/"false"; CLI emits a bare
    ``--name`` flag when true and is omitted when false.
    """
    env: dict[str, str] = {}
    cli: list[str] = []
    for param in parameters:
        raw = values.get(param.name, param.default)
        if raw is None:
            continue

        if param.type.value == "checkbox":
            if param.options:
                # Multi-select checkbox group -> repeated CLI args, comma env.
                vals = raw if isinstance(raw, list) else [raw]
                vals = [str(v) for v in vals if v not in (None, "")]
                env[param.name] = ",".join(vals)
                for v in vals:
                    cli.extend([f"--{param.name}", v])
            else:
                truthy = _as_bool(raw)
                env[param.name] = "true" if truthy else "false"
                if truthy:
                    cli.append(f"--{param.name}")
            continue

        text = str(raw)
        env[param.name] = text
        cli.extend([f"--{param.name}", text])
    return env, cli


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# Module-level singleton used by the routers.
manager = ExecutionManager()
