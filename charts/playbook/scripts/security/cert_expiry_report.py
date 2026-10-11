#!/usr/bin/env python3
"""Report TLS certificates that expire within a threshold.

DEMO: uses a synthetic inventory. In a real setup, read certificates from the
cluster (`oc get secrets --field-selector type=kubernetes.io/tls`) or probe
endpoints with ``ssl``.

Parameters (in order): days
"""
import csv
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

try:
    days = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("days", "30"))
except ValueError:
    days = 30

today = date.today()
inventory = [
    ("api.example.com", 12),
    ("auth.example.com", 87),
    ("grafana.apps.example.com", 4),
    ("registry.example.com", 160),
    ("*.apps.example.com", 25),
    ("vault.example.com", 340),
]

print(f"[certs] scanning {len(inventory)} certificates (threshold: {days} days)", flush=True)
rows = []
for host, left in inventory:
    time.sleep(0.25)
    status = "EXPIRING" if left <= days else "ok"
    expires = today + timedelta(days=left)
    print(f"  {status:<8} {host:<28} expires {expires} ({left}d)", flush=True)
    rows.append((host, expires.isoformat(), left, status))

path = Path(os.environ.get("OUTPUTS_DIR", "."), "cert-expiry.csv")
with path.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["host", "not_after", "days_left", "status"])
    writer.writerows(sorted(rows, key=lambda r: r[2]))

expiring = sum(1 for r in rows if r[3] == "EXPIRING")
print(f"[certs] {expiring} certificate(s) expire within {days} days -> {path.name}")
