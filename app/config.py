"""Environment-driven configuration for OpsPulse.

All runtime configuration comes from environment variables (sourced from
OpenShift Secrets in production). Nothing is hardcoded. Directories are
resolved and created on import so the rest of the app can assume they exist.
"""
from __future__ import annotations

import os
import secrets as _secrets
import sys
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else value


class Settings:
    """Parsed application settings. Instantiated once as ``settings``."""

    def __init__(self) -> None:
        # --- External API endpoints (used ONLY for dynamic dropdown fetches) ---
        self.openshift_api_url: str = _env("OPENSHIFT_API_URL")
        self.gitlab_api_url: str = _env("GITLAB_API_URL")
        self.gitlab_token: str = _env("GITLAB_TOKEN")
        self.openshift_token: str = _env("OPENSHIFT_TOKEN")

        # --- Admin auth ---
        self.admin_password: str = _env("ADMIN_PASSWORD")

        # --- Session signing ---
        session_secret = _env("SESSION_SECRET")
        if not session_secret:
            session_secret = _secrets.token_urlsafe(48)
            self._session_secret_ephemeral = True
        else:
            self._session_secret_ephemeral = False
        self.session_secret: str = session_secret

        # --- Filesystem: state (DATA_DIR) and scripts (SCRIPTS_DIR) ---
        # Local dev defaults are relative so the app runs on Windows out of the
        # box. The container/OpenShift image overrides these to /data and
        # /scripts respectively.
        self.data_dir: Path = Path(_env("DATA_DIR", "./data")).resolve()
        self.scripts_dir: Path = Path(_env("SCRIPTS_DIR", "./scripts")).resolve()

        self.db_path: Path = self.data_dir / "app.db"
        self.outputs_dir: Path = self.data_dir / "outputs"

        # HTTP client timeout (seconds) for dropdown fetches.
        self.http_timeout: float = float(_env("HTTP_TIMEOUT", "15"))

    # ------------------------------------------------------------------ #
    def ensure_dirs(self) -> None:
        """Create writable directories. Called on startup."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        # SCRIPTS_DIR may be a read-only mount; only create it if missing.
        try:
            self.scripts_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def warnings(self) -> list[str]:
        """Non-fatal configuration warnings surfaced at startup."""
        out: list[str] = []
        if not self.admin_password:
            out.append(
                "ADMIN_PASSWORD is not set — the /admin builder is effectively "
                "locked (no password will authenticate). Set it to enable admin."
            )
        if self._session_secret_ephemeral:
            out.append(
                "SESSION_SECRET is not set — using a random per-boot secret. "
                "Admin sessions will be invalidated on restart. Set it in prod."
            )
        if not self.scripts_dir.exists():
            out.append(f"SCRIPTS_DIR does not exist: {self.scripts_dir}")
        return out


settings = Settings()
settings.ensure_dirs()

# Interpreter used for .py scripts — the running Python by default.
PYTHON_EXECUTABLE = sys.executable or "python"
