"""OpsPulse FastAPI application entrypoint.

Single container: serves the static SPA-ish frontend, the JSON/SSE API, and
artifact downloads. All state persists in PVC-backed SQLite under DATA_DIR.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .config import settings
from .database import init_db
from .routers import actions, admin, download, dynamic, execute

logger = logging.getLogger("opspulse")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="OpsPulse", version=__version__)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="opspulse_session",
    same_site="lax",
    https_only=False,  # served behind the OpenShift TLS-terminating route
)

app.include_router(actions.router)
app.include_router(execute.router)
app.include_router(dynamic.router)
app.include_router(download.router)
app.include_router(admin.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    for warning in settings.warnings():
        logger.warning(warning)
    logger.info("OpsPulse %s started. DATA_DIR=%s SCRIPTS_DIR=%s",
                __version__, settings.data_dir, settings.scripts_dir)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


# Static assets (CSS/JS). Mounted last so API routes take precedence.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
