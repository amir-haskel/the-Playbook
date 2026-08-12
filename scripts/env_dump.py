#!/usr/bin/env python3
"""Echo the CLI args and OpsPulse-provided env vars — proves input passing."""
import os
import sys

print("[env_dump] argv:")
for a in sys.argv[1:]:
    print(f"    {a}")

print("[env_dump] OpsPulse env:")
print(f"    OUTPUTS_DIR={os.environ.get('OUTPUTS_DIR')}")
print(f"    OPSPULSE_EXECUTION_ID={os.environ.get('OPSPULSE_EXECUTION_ID')}")

# Any lowercase env vars are the parameters OpsPulse injected.
print("[env_dump] parameter-shaped env vars:")
for key in sorted(os.environ):
    if key.islower() and key not in {"path"}:
        print(f"    {key}={os.environ[key]}")
