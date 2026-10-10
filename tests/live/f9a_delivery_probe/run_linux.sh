#!/bin/bash
# Run probe cases on Linux (the reference host is Rocky 8 under AEW's bubblewrap layout), each twice, one OpenCode
# server at a time.
# Usage: run_linux.sh MODE OUT CASE...
#   MODE: plain (AEW's POSIX process tree) | bwrap (AEW's bubblewrap layout, as a contained run)
#   OUT is a directory outside the checkout. AEW_PROBE_PYTHON is the interpreter of an environment with AEW installed
#   (default: python3); AEW_OPENCODE_BIN names the OpenCode 2.0.18 CLI when it is not on PATH.
set -u
PY="${AEW_PROBE_PYTHON:-python3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="$1"; OUT="$2"; shift 2
if [ "$MODE" = bwrap ]; then export AEW_PROBE_BWRAP=1; else unset AEW_PROBE_BWRAP; fi
for c in "$@"; do
  for r in 1 2; do
    timeout 1800 "$PY" -B "$HERE/probe.py" "$OUT" "$c" "$r" 2>&1 | tail -2
  done
done
