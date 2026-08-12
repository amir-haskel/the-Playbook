"""Script execution engine with live, re-attachable SSE streaming.

An execution:
  1. resolves + validates the action's script (confined to SCRIPTS_DIR),
  2. stages any user-uploaded file params into the execution working dir,
  3. spawns the script via asyncio.subprocess with inputs passed BOTH as
     environment variables and as positional CLI args (``$1 $2 ...``),
  4. streams stdout/stderr line-by-line into an in-memory buffer that the SSE
     endpoint polls (so a client can disconnect and later re-attach),
  5. on exit, scans the per-execution output directory and registers any
     generated files as downloadable artifacts.

Live output is buffered in ``Execution.lines`` (in memory) so the execute modal
can be closed and re-opened without losing output; the DB keeps execution status
and artifact metadata for history/download.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import os
import shutil
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import database as db
from . import scripts as script_utils
from .config import settings
from .models import Action, ArtifactInfo, ExecutionState, Parameter

# Grace period (seconds) between a graceful stop signal and a forceful kill.
_STOP_GRACE_SECONDS = 10.0

# Terminal execution states.
_TERMINAL = {ExecutionState.SUCCESS, ExecutionState.FAILED, ExecutionState.STOPPED}


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class Execution:
    id: str
    action_id: str
    status: ExecutionState = ExecutionState.PENDING
    exit_code: int | None = None
    # Buffered output lines: (channel, text). Appended to as the script runs;
    # the SSE endpoint replays these so late/re-attaching clients see everything.
    lines: list[tuple[str, str]] = field(default_factory=list)
    artifacts: list[ArtifactInfo] = field(default_factory=list)
    output_dir: Path | None = None
    error: str | None = None
    # Live process handle + stop bookkeeping.
    proc: Any = None
    stop_requested: bool = False
    finished: bool = False


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
            "INSERT INTO executions (id, action_id, action_title, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (execution_id, action.id, action.title, execution.status.value, _utcnow()),
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

        # Stage uploaded file params into the working dir (= output_dir). The
        # value submitted for a file param is an upload token, not a path.
        staged_tokens: list[str] = []
        uploaded_names: set[str] = set()
        try:
            values = self._stage_uploads(
                execution, action.parameters, values, staged_tokens, uploaded_names
            )
        except _UploadError as exc:
            await self._fail(execution, f"[opspulse] {exc}")
            self._cleanup_uploads(staged_tokens)
            return

        env_extra, cli_args = _build_inputs(action.parameters, values)
        argv = argv + cli_args

        env = os.environ.copy()
        env.update(env_extra)
        env["OUTPUTS_DIR"] = str(execution.output_dir)
        env["OPSPULSE_EXECUTION_ID"] = execution.id

        await self._set_status(execution, ExecutionState.RUNNING)
        execution.lines.append(("stdout", f"$ {' '.join(argv)}"))

        # Launch in its own process group so a stop can signal the whole tree
        # (letting traps/finalizers run), not just the interpreter.
        popen_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(execution.output_dir),
                env=env,
                **popen_kwargs,
            )
        except OSError as exc:
            await self._fail(execution, f"[opspulse] failed to launch script: {exc}")
            self._cleanup_uploads(staged_tokens)
            return

        execution.proc = proc
        # Handle a stop that raced ahead of the launch.
        if execution.stop_requested:
            self._signal_stop(execution)

        await asyncio.gather(
            self._pump(execution, proc.stdout, "stdout"),
            self._pump(execution, proc.stderr, "stderr"),
        )
        exit_code = await proc.wait()
        execution.exit_code = exit_code

        self._scan_artifacts(execution, uploaded_names)
        self._cleanup_uploads(staged_tokens)

        if execution.stop_requested:
            state = ExecutionState.STOPPED
        else:
            state = ExecutionState.SUCCESS if exit_code == 0 else ExecutionState.FAILED
        await self._set_status(execution, state, finished=True)

    # ------------------------------------------------------------------ #
    def _stage_uploads(
        self,
        execution: Execution,
        parameters: list[Parameter],
        values: dict[str, Any],
        staged_tokens: list[str],
        uploaded_names: set[str],
    ) -> dict[str, Any]:
        """Copy each uploaded file param into the working dir.

        Replaces the submitted token with the copied file's basename in a shallow
        copy of ``values``. Records staged tokens (for later cleanup) and copied
        basenames (so they're excluded from artifacts). Raises _UploadError if a
        referenced upload is missing.
        """
        resolved = dict(values)
        for param in parameters:
            if param.type.value != "file":
                continue
            token = values.get(param.name)
            if token is None or str(token).strip() == "":
                # Unset optional file param; leave it for _build_inputs to skip.
                continue
            token = str(token)
            stage_dir = settings.uploads_dir / token
            files = (
                [p for p in stage_dir.iterdir() if p.is_file()]
                if stage_dir.is_dir()
                else []
            )
            if not files:
                raise _UploadError(
                    f"uploaded file for '{param.name}' is missing or expired"
                )
            src = files[0]
            dest = execution.output_dir / src.name
            shutil.copyfile(src, dest)
            resolved[param.name] = src.name
            uploaded_names.add(src.name)
            staged_tokens.append(token)
        return resolved

    def _cleanup_uploads(self, staged_tokens: list[str]) -> None:
        """Best-effort removal of upload staging dirs after a run."""
        for token in staged_tokens:
            shutil.rmtree(settings.uploads_dir / token, ignore_errors=True)

    # ------------------------------------------------------------------ #
    def stop(self, execution_id: str) -> bool:
        """Gracefully stop a running execution. Returns False if unknown."""
        execution = self._executions.get(execution_id)
        if execution is None:
            return False
        execution.stop_requested = True
        if execution.proc is not None and execution.proc.returncode is None:
            self._signal_stop(execution)
        return True

    def _signal_stop(self, execution: Execution) -> None:
        """Send a graceful signal to the process group, then schedule a kill."""
        proc = execution.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            if sys.platform == "win32":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return
        asyncio.create_task(self._escalate(execution))

    async def _escalate(self, execution: Execution) -> None:
        """After a grace period, forcefully kill a still-running process."""
        await asyncio.sleep(_STOP_GRACE_SECONDS)
        proc = execution.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            if sys.platform == "win32":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            return

    # ------------------------------------------------------------------ #
    async def _pump(self, execution: Execution, stream: Any, channel: str) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            execution.lines.append((channel, text))

    def _scan_artifacts(
        self, execution: Execution, uploaded_names: set[str]
    ) -> None:
        out_dir = execution.output_dir
        if not out_dir or not out_dir.exists():
            return
        for path in sorted(out_dir.rglob("*")):
            if not path.is_file():
                continue
            # Never surface the user's own uploaded input as a download.
            if path.name in uploaded_names:
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
            execution.finished = True
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
        execution.lines.append(("stderr", message))
        await self._set_status(execution, ExecutionState.FAILED, finished=True)


class _UploadError(Exception):
    """Raised when a referenced upload token cannot be resolved to a file."""


def _build_inputs(
    parameters: list[Parameter], values: dict[str, Any]
) -> tuple[dict[str, str], list[str]]:
    """Translate submitted values into (env vars, positional CLI args).

    Each parameter becomes an env var named exactly as the parameter, AND one or
    more positional CLI args (scripts read them as ``$1 $2 ...`` / ``sys.argv``),
    emitted in parameter order. No ``--name`` flags are produced.

    * text/number/select/radio/dynamic_select/file: one positional arg
      ``str(value)``; env[name] = str(value).
    * checkbox boolean (no options): positional ``"true"``/``"false"``;
      env[name] = ``"true"``/``"false"``.
    * checkbox group (has options; value is a list): each selected value becomes
      its own positional arg in order; env[name] = comma-joined.
    """
    env: dict[str, str] = {}
    cli: list[str] = []
    for param in parameters:
        raw = values.get(param.name, param.default)
        if raw is None:
            continue

        if param.type.value == "checkbox":
            if param.options:
                # Multi-select checkbox group -> repeated positional args.
                vals = raw if isinstance(raw, list) else [raw]
                vals = [str(v) for v in vals if v not in (None, "")]
                env[param.name] = ",".join(vals)
                cli.extend(vals)
            else:
                truthy = _as_bool(raw)
                env[param.name] = "true" if truthy else "false"
                cli.append("true" if truthy else "false")
            continue

        text = str(raw)
        env[param.name] = text
        cli.append(text)
    return env, cli


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# Module-level singleton used by the routers.
manager = ExecutionManager()
