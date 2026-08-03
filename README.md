# OpsPulse — Self-Service Internal Developer Dashboard

OpsPulse is a lightweight, single-container developer portal for **closed / air-gapped
OpenShift** environments. Admins define actions in a visual builder; developers click a
card, fill a dynamic form, run a pre-placed script on the pod, watch stdout/stderr stream
live, and download generated artifacts — no CLI access and no handling of credentials.

- **Backend:** FastAPI + Uvicorn, stdlib `sqlite3`, `asyncio.subprocess` streamed over SSE.
- **Frontend:** vanilla ES6 + a vendored utility CSS. **No CDN calls** — fully air-gapped.
- **State:** SQLite at `DATA_DIR/app.db` (PVC-mounted in OpenShift). The pod is stateless.
- **Secrets:** sourced from env vars (OpenShift Secrets); injected **server-side only**.

## Model

- **Trigger buttons run scripts only.** Each action maps to a script path under `SCRIPTS_DIR`
  (traversal is rejected — an action can only run a script the operator placed there).
- **Inputs are passed to scripts two ways:** as an **environment variable** named exactly as
  the parameter *and* as a **`--name value` CLI arg**. Checkboxes become `true`/`false` env
  values and a bare `--name` flag when true.
- **Artifacts:** anything a script writes to `$OUTPUTS_DIR` becomes a download button.
- **Dynamic dropdowns are the only outbound API calls** — fetched live from GitLab/OpenShift
  server-side with the secret token injected, never exposed to the browser.

## Quick start (local dev — Windows or Linux)

```bash
pip install -r requirements.txt
```

Set config (PowerShell shown; use `export` on Linux):

```powershell
$env:ADMIN_PASSWORD = "changeme"
$env:DATA_DIR = "./data"
$env:SCRIPTS_DIR = "./scripts"
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. Go to **/admin**, sign in with `ADMIN_PASSWORD`, and create an
action pointing at `hello.py` with a text parameter named `name`. Back on the dashboard, click
the card, run it, watch the live stream, and download `greeting.txt`.

> **Windows note:** `python` and `powershell` scripts run natively. `bash` scripts require a
> bash on PATH (Git Bash or WSL). Prefer Python actions for maximum portability.

## Bundled example scripts (`scripts/`)

| Script | Shows |
|---|---|
| `hello.py` | Env + CLI arg passing; writes a `greeting.txt` artifact. |
| `make_report.py` | Generates a downloadable `report.csv` from a numeric param. |
| `env_dump.py` | Dumps received args/env — handy for debugging parameter wiring. |
| `fail_demo.sh` | Non-zero exit → **FAILED** status (needs bash). |

## Configuration (environment variables)

| Var | Purpose | Local default |
|---|---|---|
| `ADMIN_PASSWORD` | Admin login (required) | — |
| `SESSION_SECRET` | Session cookie signing (set in prod) | random per-boot |
| `DATA_DIR` | SQLite + artifacts | `./data` |
| `SCRIPTS_DIR` | Script root | `./scripts` |
| `GITLAB_API_URL` / `GITLAB_TOKEN` | Dropdown fetches | — |
| `OPENSHIFT_API_URL` / `OPENSHIFT_TOKEN` | Dropdown fetches | — |
| `HTTP_TIMEOUT` | Dropdown fetch timeout (s) | `15` |

## Dynamic dropdowns

A `dynamic_select` parameter declares a source. Built-in sources prefill everything:

- `gitlab-branches` → `GET ${GITLAB_API_URL}/<endpoint>` with `PRIVATE-TOKEN: ${GITLAB_TOKEN}`,
  parsed as `[].name` (set `endpoint` to e.g. `projects/42/repository/branches`).
- `oc-namespaces` → `GET ${OPENSHIFT_API_URL}/<endpoint>` with `Authorization: Bearer ${OPENSHIFT_TOKEN}`,
  parsed as `items[].metadata.name`.
- `custom` → set `endpoint`, `response_key`, and `auth_header` yourself.

`response_key` supports dotted paths with one `[]` list projection, e.g. `[].name` or
`items[].metadata.name`.

## API

| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/actions` | GET | Public list (secret templates stripped). |
| `/api/v1/actions` | POST | Admin. Create. |
| `/api/v1/actions/{id}` | PUT / DELETE | Admin. |
| `/api/v1/dynamic-options/{type}?action_id=&param=` | GET | Live dropdown fetch. |
| `/api/v1/execute/{action_id}` | POST | Start execution → `execution_id`. |
| `/api/v1/stream/{execution_id}` | GET | SSE stdout/stderr + terminal status event. |
| `/api/v1/download/{file_id}` | GET | Stream an artifact. |
| `/api/v1/admin/login` · `/logout` · `/session` | POST/GET | Session auth. |
| `/api/v1/admin/scripts` | GET | Admin. Discover scripts for the builder. |
| `/healthz` | GET | Readiness/liveness probe. |

## Container

```bash
docker build -t opspulse .
docker run -e ADMIN_PASSWORD=changeme -p 8000:8000 opspulse
```

The image sets `DATA_DIR=/data` and `SCRIPTS_DIR=/scripts` and runs as a non-root user.

## OpenShift

```bash
oc apply -f openshift/pvc.yaml
oc apply -f openshift/secret.yaml      # edit real values first (or use a sealed-secret)
oc apply -f openshift/deployment.yaml
oc apply -f openshift/service.yaml
oc apply -f openshift/route.yaml
```

Notes: keep `replicas: 1` (SQLite on a single RWO PVC); the Route sets a 1h HAProxy timeout so
SSE streams aren't cut mid-execution. Scripts can be baked into the image or mounted from a
ConfigMap (see the commented block in `deployment.yaml`).

## Security model

OpsPulse **runs admin-configured scripts by design** — that is the product. Exposure is bounded
by: admin-only action management (session-cookie auth, constant-time password check), script
execution confined to `SCRIPTS_DIR` (no path traversal), and artifact downloads confined to the
outputs directory. Deploy it only inside a **trusted internal network**. Set a strong
`ADMIN_PASSWORD` and a stable `SESSION_SECRET`.

## Tests

```bash
pip install pytest
pytest -q
```

Covers the response-key parser, secret substitution, script-path confinement, and env+CLI input
translation.
