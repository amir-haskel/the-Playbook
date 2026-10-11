#!/usr/bin/env python3
"""Example Playbook action script.

Demonstrates that the Playbook passes each parameter BOTH as a positional CLI
argument (in parameter order: ``$1 $2 ...``) and as an environment variable
named after the parameter, and that files written into $OUTPUTS_DIR become
downloadable artifacts.

Parameters (in order): name, greeting
"""
import os
import sys
import time
from pathlib import Path

name = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("name", "world")
greeting = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("greeting", "Hello")

print(f"[hello] received via CLI arg  : name={name!r}")
print(f"[hello] received via env var  : name={os.environ.get('name')!r}")

for i in range(1, 4):
    print(f"[hello] working... step {i}/3")
    sys.stdout.flush()
    time.sleep(0.4)

message = f"{greeting}, {name}!"
print(f"[hello] {message}")

# Write an artifact into the per-execution output directory.
outputs = Path(os.environ.get("OUTPUTS_DIR", "."))
outputs.mkdir(parents=True, exist_ok=True)
report = outputs / "greeting.txt"
report.write_text(message + "\n", encoding="utf-8")
print(f"[hello] wrote artifact: {report.name}")
