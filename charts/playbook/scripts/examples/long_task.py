#!/usr/bin/env python3
"""Long-running task that installs a SIGTERM handler and a finalizer, to
demonstrate the Playbook's graceful stop (the finalizer must run on Stop)."""
import os
import signal
import sys
import time
from pathlib import Path

_stop = False


def _on_term(signum, frame):
    global _stop
    _stop = True
    print(f"[long_task] received signal {signum}; finishing up...", flush=True)


signal.signal(signal.SIGTERM, _on_term)
try:
    signal.signal(signal.SIGINT, _on_term)
except Exception:
    pass
# On Windows, the Playbook's graceful stop sends CTRL_BREAK (-> SIGBREAK); trap it
# too so the finalizer also runs during local Windows testing.
if hasattr(signal, "SIGBREAK"):
    try:
        signal.signal(signal.SIGBREAK, _on_term)
    except Exception:
        pass

outputs = Path(os.environ.get("OUTPUTS_DIR", "."))
print("[long_task] starting; will run up to 60 steps", flush=True)
for i in range(1, 61):
    if _stop:
        break
    print(f"[long_task] step {i}", flush=True)
    time.sleep(1)

# Finalizer — must run even when stopped, to prove graceful shutdown.
(outputs / "cleanup.txt").write_text(
    "finalizer ran; stopped=%s\n" % _stop, encoding="utf-8"
)
print("[long_task] finalizer done (wrote cleanup.txt)", flush=True)
sys.exit(0)
