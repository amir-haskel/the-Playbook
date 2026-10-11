# Scripts shipped with the chart

Every file in this folder (except dotfiles and this README) is rendered into the
`<release>-scripts` ConfigMap and mounted read-only at `/scripts` in the pod.
Admins point actions at them in **/admin**; the script picker lists each one by
its path relative to this folder (e.g. `deploy/deploy_service.sh`).

What every script can rely on:

| What | How |
|---|---|
| Parameters | Positional args in the order defined on the action (`$1 $2 …` / `sys.argv`), **and** env vars named after each parameter. |
| Artifacts | Anything written to `$OUTPUTS_DIR` becomes a download button. It is also the script's working directory. |
| Uploaded files | A file parameter arrives as the file's name, already placed in the working directory. |
| Run id | `$PLAYBOOK_EXECUTION_ID` |
| Exit code | `0` → SUCCESS, anything else → FAILED. |
| Stop button | The process group receives `SIGTERM` (then `SIGKILL` after 10 s). Trap it to clean up. |

Interpreters are picked by extension: `.py` → Python, `.sh`/`.bash` → bash, `.ps1` → PowerShell.

File and folder names may only use letters, digits, `-`, `_` and `.` (a ConfigMap
key restriction). The whole folder must stay under ~1 MiB, so ship heavy tooling
(CLIs, binaries) in the container image instead.

The scripts under `deploy/`, `kubernetes/`, `database/`, `quality/`, `security/` and
`release/` are **demos with simulated output** so the chart runs anywhere. Replace
them with your real automation.
