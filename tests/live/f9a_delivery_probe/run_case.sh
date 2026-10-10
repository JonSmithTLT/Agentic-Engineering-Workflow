#!/bin/bash
# Run probe cases on Windows (Git Bash), each twice, one OpenCode server at a time.
# Usage: run_case.sh OUT CASE...
#   OUT is a directory outside the checkout. AEW_PROBE_PYTHON is the interpreter of an environment with AEW installed
#   (default: python); AEW_OPENCODE_BIN names the OpenCode 2.0.18 CLI when adapter.default_binary() does not find it.
set -u
PY="${AEW_PROBE_PYTHON:-python}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$1"; shift
for c in "$@"; do
  for r in 1 2; do
    timeout 1800 "$PY" "$HERE/probe.py" "$OUT" "$c" "$r" 2>&1 | tail -3
  done
done
