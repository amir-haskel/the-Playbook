#!/usr/bin/env python3
"""Generate a small CSV report artifact from a numeric parameter."""
import argparse
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--rows", default=os.environ.get("rows", "5"))
parser.add_argument("--label", default=os.environ.get("label", "sample"))
args, _ = parser.parse_known_args()

try:
    rows = max(1, min(1000, int(args.rows)))
except ValueError:
    rows = 5

outputs = Path(os.environ.get("OUTPUTS_DIR", "."))
outputs.mkdir(parents=True, exist_ok=True)
path = outputs / "report.csv"

print(f"[report] generating {rows} rows labelled {args.label!r}")
with path.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["index", "label", "timestamp"])
    for i in range(1, rows + 1):
        writer.writerow([i, args.label, datetime.now(timezone.utc).isoformat()])
        print(f"[report] row {i} written")

print(f"[report] done -> {path.name}")
