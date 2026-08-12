# OpsPulse — Project State (debugging reference)

_Snapshot for future debugging sessions. The PoC branch `feat/opspulse-poc` has
been merged into `main`._

## 1. Purpose & architecture
OpsPulse is a **single-container, air-gapped self-service developer portal** for
closed OpenShift. Admins define **actions** (each maps to a pre-placed script) in
a visual builder; developers run them from a card grid, watch stdout/stderr
stream live over **SSE**, and download generated artifacts. No CLI access, no
credential handling by users.

- **Backend:** FastAPI + Uvicorn, **stdlib `sqlite3`** (single connection + lock)
  on a PVC, `asyncio.subprocess` for execution, SSE for streaming.
- **Frontend:** vanilla ES6 + hand-written CSS, **no build step, no npm, no CDN**.
  Everything is served from `static/` by FastAPI.
- **State:** SQLite at `DATA_DIR/app.db`; artifacts under `DATA_DIR/outputs/<exec_id>/`;
  uploads staged under `DATA_DIR/uploads/<token>/`.
- **Secrets:** env vars (OpenShift Secrets), injected **server-side only**.

Run locally (Windows dev):
```bash
ADMIN_PASSWORD=opspulse SESSION_SECRET=local-dev-secret DATA_DIR=./data SCRIPTS_DIR=./scripts \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Tests: `ADMIN_PASSWORD=test SCRIPTS_DIR=./scripts DATA_DIR=./data python -m pytest -q` (20 pass).

## 2. Important files
**Backend (`app/`)**
- `main.py` — app factory; SessionMiddleware; **no-cache middleware for `/static`**; router registration; `/healthz`; serves `index.html`/`admin.html`; `init_db()` on startup.
- `config.py` — `Settings` from env: `DATA_DIR` (def `./data`), `SCRIPTS_DIR` (def `./scripts`), `data_dir/outputs/uploads` dirs, `db_path`, `ADMIN_PASSWORD`, `SESSION_SECRET`, GitLab/OpenShift URLs+tokens, `HTTP_TIMEOUT`. `ensure_dirs()` runs at import.
- `database.py` — one shared `sqlite3` conn (WAL, `check_same_thread=False`) guarded by a `threading.Lock`. Tables: `actions`, `tags`, `executions`, `artifacts`, `app_settings`. `init_db()` runs schema + **PRAGMA-based column migrations** (added `tags`, tag `type`, `action_title` over time). `query_all/one/execute`, `dumps/loads`.
- `models.py` — Pydantic. `ParamType` (text/number/checkbox/radio/select/dynamic_select/**file**); `Interpreter`; `Parameter` with `_check_defaults` validator (default∈options for select/radio/checkbox-group; number ≥0 & numeric); `TagType` (function/team); `Tag`; `Action`; `ExecutionState` (PENDING/RUNNING/SUCCESS/FAILED/**STOPPED**).
- `store.py` — action CRUD, tag CRUD (delete detaches from actions), **settings** (`get/set_setting`, `get_history_limit` def 50), **`prune_executions()`** (delete rows + artifact rows + output dirs beyond newest N).
- `executor.py` — `ExecutionManager` + `Execution` dataclass. Key behaviors:
  - `_build_inputs()` → `(env, cli)` where **cli is positional values in param order, no `--name`**; env vars kept (named as param; checkbox-group comma-joined).
  - `_run()`: stage file-param uploads into the working dir, spawn subprocess with **`cwd = execution.output_dir`**, in a **new process group** (`start_new_session=True` POSIX / `CREATE_NEW_PROCESS_GROUP` Windows), pump stdout/stderr into `Execution.lines` (buffered for replay), scan artifacts (**excludes uploaded input filenames**), clean up upload staging.
  - `stop()`: `os.killpg(SIGTERM)` POSIX / `CTRL_BREAK_EVENT` Windows, escalate to SIGKILL after ~10s; final status `STOPPED`.
- `scripts.py` — `list_scripts()`, `resolve_script()` (**confined to SCRIPTS_DIR**, rejects traversal), `build_command()` (interpreter by ext or explicit; python/bash/powershell).
- `http_client.py` — dropdown fetching only (the **one** outbound-API path). `fetch_options()`, `parse_response_key()` (`[].name`, `items[].metadata.name`), `_resolve_source()` (endpoint + auth header support `${VAR}` substitution). `BUILTIN_SOURCES` presets still exist server-side but the UI now always sends custom.
- `secrets.py` — `${VAR}` substitution + `parse_header()`.
- `auth.py` — cookie session; `verify_password` (constant-time, fails closed if no `ADMIN_PASSWORD`); `admin_required` dependency.
- `routers/` — `actions.py` (CRUD + `tag_details` resolution + ≤1 function/≤1 team validation), `execute.py` (execute + required/number validation + `prune_executions()`; `GET /executions`; `POST /executions/{id}/stop`; **poll-based replay SSE** `GET /stream/{id}`), `dynamic.py` (`/dynamic-options/{type}` + `POST /dynamic-options/test`), `download.py` (path-confined), `admin.py` (login/logout/session, `/admin/scripts`), `tags.py`, `uploads.py` (`POST /upload`), `settings.py` (`GET/PUT /settings`).

**Frontend (`static/`)**
- `index.html` — dashboard: header (theme toggle, **history-toggle**, Admin), search, `#filter-bar`, `#board`, execution `#modal` (icon, title, form, terminal, status badge, `#m-gate`, `#m-stop`, `#m-execute`), `#history-drawer` + `#drawer-overlay`.
- `admin.html` — login gate; builder: Tags, Actions, **Settings** (history limit); tag-editor & action-editor modals (icon picker, function/team single-selects, script `<select>`, param builder).
- `css/app.css` — all styles: light/dark tokens, buttons/badges/cards/modal/forms/terminal, tag pills & team badges, filter chips (**monospace**), icon picker, **history drawer**, **dropzone**, **docked modal** (`.modal-overlay.docked` keeps dim+blur, offset left of drawer), **night-sky dark mode** (`body::before/::after` starfield + drift, `#space-fx` overlay).
- `js/dashboard.js` — grid, filters (one function + one team, AND), execute modal, SSE stream (`stream()`), file **dropzone** (upload→token), execute **gating** (`gateExecute`), **history drawer** (poll every 3s), **docked** re-attach (`openExecution`), stop.
- `js/admin.js` — tags, actions, icon picker, settings load/save.
- `js/icons.js` — bundled SVG icons incl. brand logos (docker/gitlab/kubernetes/openshift/argocd/nexus/jenkins/terraform/helm/github/linux/ansible/prometheus/vault). `window.OpsIcons.{ICON_KEYS,render,has}`.
- `js/theme.js` — light/dark toggle (persist `opspulse-theme`, pre-paint snippet in each HTML `<head>`).
- `js/space.js` — dark-mode **shooting stars** (Web Animations API, motion-safe), creates `#space-fx`.
- Asset URLs carry `?v=N` (currently **v=7**) for cache-busting alongside the no-cache header.

**Other:** `scripts/` (hello, make_report, env_dump, fail_demo.sh, **show_file.py** [file param demo], **long_task.py** [graceful-stop demo, traps SIGTERM+SIGBREAK]); `tests/test_units.py`; `openshift/` (pvc/secret/deployment/service/route); `Dockerfile` (python:3.11-slim, non-root); `requirements.txt`; `README.md`.

## 3. API surface
`GET /healthz` · `GET/POST /api/v1/actions`, `PUT/DELETE .../{id}` · `GET/POST /api/v1/tags`, `PUT/DELETE .../{id}` · `GET/PUT /api/v1/settings` · `GET /api/v1/dynamic-options/{type}?action_id=&param=`, `POST /api/v1/dynamic-options/test` · `POST /api/v1/execute/{action_id}` · `GET /api/v1/stream/{execution_id}` (SSE) · `GET /api/v1/executions?limit=` · `POST /api/v1/executions/{id}/stop` · `POST /api/v1/upload` · `GET /api/v1/download/{file_id}` · `POST /api/v1/admin/login|logout`, `GET /admin/session`, `GET /admin/scripts`.

## 4. Key design decisions (why)
- **Script-only actions, positional args:** buttons run a pre-placed script; inputs passed positionally (`$1 $2 …`) in param order + as env vars. (User: scripts read `$1 $2`; earlier `--name` prefix was removed.)
- **File params:** uploaded to a staging token, copied into the exec working dir at run time, passed as **basename**; excluded from artifact scan; script owns deletion. `cwd = output_dir` so uploads, relative reads, and outputs share one path.
- **Artifacts = everything in `$OUTPUTS_DIR`** (no "final file" heuristic). Documented; scripts must write only intended outputs there.
- **Tags are first-class, two types:** function (colored, ≤1/action, drives filters+card accent) and team (colorless uppercase JetBrains-Mono badge top-right, ≤1/action). Filters combine one-of-each with **AND**.
- **Graceful stop = SIGTERM to the process group** so bash `trap`/python finalizers run (verified on Linux). New process group so signals reach children.
- **Re-attachable SSE:** output buffered in `Execution.lines`; stream endpoint polls+replays so closing/reopening the modal (or history) keeps output. Background runs continue after modal close.
- **Air-gapped everything:** no CDN/npm/web-fonts; icons are inline SVG; "prebuilt CSS" is hand-written; JetBrains Mono referenced with a monospace fallback (not bundled).
- **No-cache + `?v=`** on static to defeat stale-asset caching during iteration.
- **Dark mode = "midnight portal" palette:** `#05060a` base + lime (top-right) & violet (top-left) nebula glows (copied from `portal-midnight-cat/style.css`), with our starfield + shooting stars layered on top.

## 5. Known bugs / issues / limitations
- **Windows graceful stop:** `CTRL_BREAK` → `SIGBREAK`, which a script must trap explicitly; a SIGTERM-only handler won't run its finalizer on Windows (works on Linux/OpenShift — the real target). `long_task.py` traps both as a workaround.
- **Server restart loses in-memory executions:** `ExecutionManager` is in-memory; after restart, `GET /stream/{id}` 404s for old executions, and DB rows left in `RUNNING` are **not reconciled** to FAILED on startup (stale status).
- **Prune vs. running:** `prune_executions()` deletes oldest beyond the limit by `created_at`; with a very small limit and many concurrent runs it could in theory remove a still-relevant/running row + its output dir. Not observed; edge case.
- **No upload size limit / disk-exhaustion guard** on `POST /upload`.
- **Brand icons are hand-drawn approximations** (recognizable, not pixel-accurate).
- **JetBrains Mono not bundled** — team badges/filter chips fall back to system monospace unless the font is installed.
- **Docked-modal desktop position** couldn't be pixel-verified in the headless browser pane (`innerWidth` reports 0 there); CSS logic verified, visual position unconfirmed in-tool.

## 6. Things already tried & results
- **Cross-platform wheel download from Windows → WRONG** (mis-evaluates env markers: drops `uvloop`/`httptools`, adds `colorama`). **Fixed** by running `pip download` **inside `python:3.11-slim`**. Wheelhouse at `C:\Users\amirha\opspulse-wheelhouse\` (23 wheels, Linux x86_64/cp311), verified with an offline `--no-index` install + `from app.main import app`.
- **Stale static assets** → fixed with `Cache-Control: no-cache` middleware + `?v=N` URLs.
- **`[object Object]` errors** → frontend now formats FastAPI `detail` (string or 422 list).
- **Button contrast bug** (danger/success washed to light on hover because generic `.btn:hover` set `background`) → re-assert colored background in the variant `:hover`.
- **Graceful stop on Linux** → verified in-container: finalizer ran, `cleanup.txt` written, status STOPPED.
- **Big feature batch built via 3 parallel sub-agents** with disjoint file ownership (backend Python / frontend JS+HTML / CSS) against a fixed API+class contract — integrated cleanly.

## 7. Assumptions & constraints
- **Dev host = Windows; deploy target = Linux/OpenShift** `python:3.11-slim`, x86_64, glibc. Wheels/behaviors target that.
- **SQLite single-writer** → `replicas: 1`, `strategy: Recreate` in the Deployment.
- **Script execution is the intended feature**, admin-gated, confined to `SCRIPTS_DIR`; deploy only on a **trusted internal network**.
- **OpenShift arbitrary UID** (restricted SCC): image is non-root, `/data` group-writable. Verify `outputs/`, `uploads/` are writable under the assigned UID.
- `python-multipart` (already in `requirements.txt`) is required for uploads. **No dependency changes since the wheelhouse was built.**

## 8. Suggested next investigations
1. **Startup reconciliation:** on boot, mark orphaned `RUNNING`/`PENDING` executions as `FAILED` (or STOPPED) so history isn't stuck; optionally persist enough to explain "output lost on restart".
2. **SSE at scale:** each `/stream` polls `Execution.lines` every 0.15s; check behavior with many concurrent viewers / long-lived streams behind the OpenShift Route (1h HAProxy timeout is set).
3. **Upload hardening:** max size, content-type allowlist (if desired), disk quota / cleanup of orphaned staging dirs on failure.
4. **Prune safety:** exclude non-terminal executions from `prune_executions()`.
5. **OpenShift perms:** confirm PVC mount + `outputs/`+`uploads/` writability under a random UID; confirm SSE works through the Route end-to-end.
6. **Windows finalizers** (dev-only nicety): document that user scripts should trap `SIGBREAK` too, or accept Linux-only graceful cleanup.
