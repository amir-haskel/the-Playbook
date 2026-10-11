#!/usr/bin/env python3
"""Take a logical backup of a database and publish it as a download.

DEMO: produces a small synthetic dump instead of calling pg_dump, so the action
runs anywhere. Replace ``dump()`` with a real ``pg_dump`` subprocess call.

Parameters (in order): database, compress
"""
import gzip
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

database = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("database", "orders")
compress = (sys.argv[2] if len(sys.argv) > 2 else os.environ.get("compress", "true")) == "true"


def dump(db: str) -> bytes:
    lines = [f"-- logical backup of {db} at {datetime.now(timezone.utc).isoformat()}"]
    for table in ("customers", "orders", "order_items", "invoices"):
        print(f"[backup] dumping table {db}.{table} ...", flush=True)
        time.sleep(0.5)
        lines.append(f"COPY public.{table} FROM stdin;  -- (demo rows elided)")
    return ("\n".join(lines) + "\n").encode()


stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
print(f"[backup] starting backup of '{database}' (compress={compress})", flush=True)
data = dump(database)

outputs = Path(os.environ.get("OUTPUTS_DIR", "."))
name = f"{database}-{stamp}.sql" + (".gz" if compress else "")
path = outputs / name
path.write_bytes(gzip.compress(data) if compress else data)

digest = hashlib.sha256(path.read_bytes()).hexdigest()
(outputs / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")
print(f"[backup] wrote {name} ({path.stat().st_size} bytes), sha256={digest[:12]}")
