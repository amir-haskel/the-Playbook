"""OpsPulse FastAPI application entrypoint.

Single container: serves the static SPA-ish frontend, the JSON/SSE API, and
artifact downloads. All state persists in PVC-backed SQLite under DATA_DIR.
"""
from __future__ import annotations

import html
import logging
import mimetypes
from pathlib import Path

# Ensure correct Content-Type for the self-hosted webfont. Slim base images
# (and some Windows setups) don't map .woff2, so StaticFiles would serve it as
# text/plain; register it explicitly so browsers accept it everywhere.
mimetypes.add_type("font/woff2", ".woff2")

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from . import store
from .config import settings
from .database import init_db
from .routers import actions, admin, download, dynamic, execute, settings as settings_router, tags, uploads

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
app.include_router(tags.router)
app.include_router(execute.router)
app.include_router(uploads.router)
app.include_router(dynamic.router)
app.include_router(download.router)
app.include_router(admin.router)
app.include_router(settings_router.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # A restart wipes in-memory execution state, so any run still marked
    # RUNNING/PENDING in the DB is orphaned — reconcile it to a terminal state.
    reconciled = store.reconcile_orphaned_executions()
    if reconciled:
        logger.warning("Reconciled %d orphaned execution(s) to FAILED on startup", reconciled)
    for warning in settings.warnings():
        logger.warning(warning)
    logger.info("OpsPulse %s started. DB_DIR=%s STORE_DIR=%s SCRIPTS_DIR=%s",
                __version__, settings.db_dir, settings.store_dir, settings.scripts_dir)


@app.middleware("http")
async def _revalidate_static(request, call_next):
    """Force browsers to revalidate static assets (ETag/Last-Modified) instead
    of serving stale JS/CSS from heuristic cache — assets update in place. The
    HTML shells ("/" and "/admin") are also no-cache so a brand/env change or a
    redeploy is reflected on the next load rather than served stale."""
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path in ("/", "/admin"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


def _render_page(filename: str) -> HTMLResponse:
    """Serve a static HTML shell with the brand wordmark substituted in.

    The two brand words are env-driven (BRAND_ARTICLE / BRAND_NAME) so the
    portal can be re-labelled without editing templates. Substitution happens
    server-side (rather than in JS) so there is no flash of the default name,
    and it stays air-gap friendly — no templating engine, just str.replace on
    a handful of {{PLACEHOLDER}} tokens. Values are HTML-escaped since they
    land inside markup.
    """
    article = html.escape(settings.brand_article)
    name = html.escape(settings.brand_name)
    full = html.escape(" ".join(w for w in (settings.brand_article, settings.brand_name) if w))
    text = (STATIC_DIR / filename).read_text(encoding="utf-8")
    text = (text
            .replace("{{BRAND_ARTICLE}}", article)
            .replace("{{BRAND_NAME}}", name)
            .replace("{{BRAND_FULL}}", full))
    return HTMLResponse(text)


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    return _render_page("index.html")


@app.get("/admin", include_in_schema=False)
def admin_page() -> HTMLResponse:
    return _render_page("admin.html")


# Static assets (CSS/JS). Mounted last so API routes take precedence.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
