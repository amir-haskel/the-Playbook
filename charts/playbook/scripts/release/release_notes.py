#!/usr/bin/env python3
"""Generate Markdown release notes between two versions.

DEMO: uses a canned commit list. Replace ``commits()`` with
``git log --pretty=%s FROM..TO`` against your repository.

Parameters (in order): from_version, to_version
"""
import os
import sys
import time
from pathlib import Path

frm = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("from_version", "v2.3.0")
to = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("to_version", "v2.4.0")


def commits() -> list[str]:
    return [
        "feat(orders): support partial refunds",
        "feat(api): add idempotency keys to POST /payments",
        "fix(auth): refresh tokens no longer expire early",
        "fix(search): escape special characters in queries",
        "chore(deps): bump fastapi to 0.115.6",
        "docs: document the rollback runbook",
    ]


print(f"[notes] collecting commits {frm}..{to}", flush=True)
time.sleep(0.6)
groups: dict[str, list[str]] = {"Features": [], "Fixes": [], "Maintenance": []}
for msg in commits():
    if msg.startswith("feat"):
        kind = "Features"
    elif msg.startswith("fix"):
        kind = "Fixes"
    else:
        kind = "Maintenance"
    groups[kind].append(msg.split(": ", 1)[-1])
    print(f"  + {msg}", flush=True)

md = [f"# Release {to}", "", f"Changes since {frm}.", ""]
for title, items in groups.items():
    if items:
        md += [f"## {title}", *[f"- {i}" for i in items], ""]
out = Path(os.environ.get("OUTPUTS_DIR", "."), f"release-notes-{to}.md")
out.write_text("\n".join(md), encoding="utf-8")
print(f"[notes] wrote {out.name}")
