#!/usr/bin/env python3
"""Run a post-deploy smoke-test suite and publish a JUnit report.

DEMO: checks are simulated. Point ``CHECKS`` at real endpoints (e.g. with
urllib) to make it live.

Parameters (in order): environment, suite
"""
import os
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape

environment = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("environment", "staging")
suite = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("suite", "core")

CHECKS = [
    ("api: GET /healthz returns 200", 0.12),
    ("api: login round-trip", 0.31),
    ("orders: create + fetch order", 0.48),
    ("payments: sandbox charge", 0.62),
    ("search: index freshness < 5m", 0.21),
]

print(f"[smoke] running '{suite}' suite against {environment}", flush=True)
cases = []
for name, seconds in CHECKS:
    time.sleep(seconds)
    print(f"  PASS  {name}  ({seconds:.2f}s)", flush=True)
    cases.append((name, seconds))

total = sum(s for _, s in cases)
print(f"[smoke] {len(cases)} passed, 0 failed in {total:.2f}s")

xml = [f'<testsuite name="smoke-{escape(suite)}" tests="{len(cases)}" failures="0" time="{total:.2f}">']
xml += [f'  <testcase classname="{escape(environment)}" name="{escape(n)}" time="{s:.2f}"/>' for n, s in cases]
xml.append("</testsuite>")
out = Path(os.environ.get("OUTPUTS_DIR", "."), "junit-smoke.xml")
out.write_text("\n".join(xml) + "\n", encoding="utf-8")
print("[smoke] wrote junit-smoke.xml")
