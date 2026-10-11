#!/usr/bin/env bash
# Demonstrates a non-zero exit -> FAILED status in the Playbook.
echo "[fail_demo] starting"
echo "[fail_demo] this is going to fail on purpose" >&2
exit 3
