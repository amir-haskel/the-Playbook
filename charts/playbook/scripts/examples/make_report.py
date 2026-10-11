#!/usr/bin/env python3
"""Generate a small CSV report artifact from a numeric parameter.

Parameters (in order): rows, label
"""
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

raw_rows = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("rows", "5")
label = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("label", "sample")

try:
    rows = max(1, min(1000, int(raw_rows)))
except ValueError:
    rows = 5

outputs = Path(os.environ.get("OUTPUTS_DIR", "."))
outputs.mkdir(parents=True, exist_ok=True)
path = outputs / "report.csv"

print(f"[report] generating {rows} rows labelled {label!r}")
with path.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["index", "label", "timestamp"])
    for i in range(1, rows + 1):
        writer.writerow([i, label, datetime.now(timezone.utc).isoformat()])
        print(f"[report] row {i} written")

print(f"[report] done -> {path.name}")
