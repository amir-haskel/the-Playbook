#!/usr/bin/env python3
"""Example OpsPulse action script.

Demonstrates that OpsPulse passes each parameter BOTH as an environment
variable (named exactly as the parameter) and as a ``--name value`` CLI arg,
and that files written into $OUTPUTS_DIR become downloadable artifacts.
"""
import argparse
import os
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--name", default=os.environ.get("name", "world"))
parser.add_argument("--greeting", default=os.environ.get("greeting", "Hello"))
args, _ = parser.parse_known_args()

print(f"[hello] received via CLI arg  : name={args.name!r}")
print(f"[hello] received via env var  : name={os.environ.get('name')!r}")

for i in range(1, 4):
    print(f"[hello] working... step {i}/3")
    sys.stdout.flush()
    time.sleep(0.4)

message = f"{args.greeting}, {args.name}!"
print(f"[hello] {message}")

# Write an artifact into the per-execution output directory.
outputs = Path(os.environ.get("OUTPUTS_DIR", "."))
outputs.mkdir(parents=True, exist_ok=True)
report = outputs / "greeting.txt"
report.write_text(message + "\n", encoding="utf-8")
print(f"[hello] wrote artifact: {report.name}")
