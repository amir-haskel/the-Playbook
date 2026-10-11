#!/usr/bin/env python3
"""Demo for the file parameter: receives the uploaded file's name as $1,
reads it from the execution working dir, and writes a result artifact."""
import os
import sys
from pathlib import Path

filename = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("doc", "")
print(f"[show_file] filename arg: {filename!r}")

src = Path(filename)
print(f"[show_file] present in working dir: {src.exists()}")
if src.exists():
    print(f"[show_file] contents: {src.read_text(encoding='utf-8', errors='replace')!r}")

out = Path(os.environ.get("OUTPUTS_DIR", ".")) / "result.txt"
out.write_text(f"processed {filename}\n", encoding="utf-8")
print(f"[show_file] wrote {out.name}")
