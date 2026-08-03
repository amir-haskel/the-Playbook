"""Script discovery, path validation and interpreter resolution.

Trigger buttons run pre-placed scripts under SCRIPTS_DIR. Every resolved path
is confined to SCRIPTS_DIR — traversal (``..``) or absolute escapes are
rejected — so an action can only ever run a script the operator placed there.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .config import PYTHON_EXECUTABLE, settings
from .models import Interpreter

# Extensions we know how to run and their default interpreter.
_EXT_INTERPRETER = {
    ".py": Interpreter.python,
    ".sh": Interpreter.bash,
    ".bash": Interpreter.bash,
    ".ps1": Interpreter.powershell,
}

ALLOWED_EXTENSIONS = tuple(_EXT_INTERPRETER.keys())


class ScriptError(ValueError):
    """Raised when a script path is invalid or unrunnable."""


def list_scripts() -> list[str]:
    """Return runnable script paths (relative to SCRIPTS_DIR), sorted."""
    root = settings.scripts_dir
    if not root.exists():
        return []
    found: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in _EXT_INTERPRETER:
            found.append(path.relative_to(root).as_posix())
    return sorted(found)


def resolve_script(script_path: str) -> Path:
    """Resolve ``script_path`` against SCRIPTS_DIR, rejecting escapes.

    Raises ScriptError if the path escapes SCRIPTS_DIR, does not exist, or has
    an unsupported extension.
    """
    if not script_path:
        raise ScriptError("script_path is empty")

    root = settings.scripts_dir.resolve()
    candidate = (root / script_path).resolve()

    # Confinement check: candidate must be inside root.
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ScriptError(f"script_path escapes SCRIPTS_DIR: {script_path!r}")

    if candidate.suffix.lower() not in _EXT_INTERPRETER:
        raise ScriptError(f"unsupported script type: {candidate.suffix!r}")
    if not candidate.is_file():
        raise ScriptError(f"script not found: {script_path!r}")
    return candidate


def _which(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def build_command(script: Path, interpreter: Interpreter) -> list[str]:
    """Build the argv prefix (interpreter + script) for a resolved script.

    ``auto`` infers the interpreter from the file extension. Raises ScriptError
    when the required interpreter is not available on PATH.
    """
    if interpreter == Interpreter.auto:
        interpreter = _EXT_INTERPRETER.get(script.suffix.lower(), Interpreter.python)

    if interpreter == Interpreter.python:
        return [PYTHON_EXECUTABLE, str(script)]

    if interpreter == Interpreter.bash:
        bash = _which("bash")
        if not bash:
            raise ScriptError(
                "bash interpreter not found on PATH (install Git Bash / WSL, "
                "or use a Python/PowerShell script)."
            )
        return [bash, str(script)]

    if interpreter == Interpreter.powershell:
        ps = _which("pwsh", "powershell")
        if not ps:
            raise ScriptError("PowerShell (pwsh/powershell) not found on PATH.")
        return [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]

    raise ScriptError(f"unknown interpreter: {interpreter}")
