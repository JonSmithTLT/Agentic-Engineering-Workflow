#!/usr/bin/env bash
# ADR-0011 on a representative Rocky Linux 8 host (ADR-0011 completion; implementation plan 7.2).
#
# Runs the minimum the ADR requires there:
#   1. the hierarchy-history sweep (one open Epic and Story, 250 / 1,000 / 3,000 completed descendant Tickets);
#   2. H3 and the absolute heartbeat bound: a supervisor's re-parse of a changed control state at 20 open and
#      3,000 completed (``micro.control_reparse_s`` in the JSON; H3 <= 0.25 s, heartbeat bound <= 2.5 s);
#   3. archival-write scaling: the cold-write series at 1k / 3k / 10k / 30k records.
#
# Usage, from a clone of the commit under test, with AEW installed in the active Python environment
# (``pip install -e .``) and nothing else running on the host:
#
#   tools/perf/rocky8-gate.sh OUT_DIR [WORK_DIR]
#
# OUT_DIR receives rocky8-env.txt, rocky8-hierarchy.json, rocky8-h3.json and rocky8-coldwrite.json. WORK_DIR holds
# the synthetic projects, about 1 GB at its peak. Without it, a new directory under /tmp is used and removed at the
# end; a WORK_DIR you name is left in place.
set -euo pipefail

out=${1:?usage: rocky8-gate.sh OUT_DIR [WORK_DIR]}
if [ -n "${2:-}" ]; then work=$2; created=; else work=$(mktemp -d /tmp/aew-perf.XXXXXX); created=1; fi
here=$(cd "$(dirname "$0")" && pwd)
tool="$here/control_plane.py"
mkdir -p "$out" "$work"

{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "commit: $(git -C "$here" rev-parse HEAD)"
  echo "kernel: $(uname -sr)"
  [ -r /etc/os-release ] && grep -E '^(NAME|VERSION)=' /etc/os-release
  echo "cpus: $(nproc)"
  echo "load: $(cut -d' ' -f1-3 /proc/loadavg)"
  echo "python: $(python3 -c 'import sys; print(sys.version.split()[0])')"
  echo "pyyaml: $(python3 -c 'import yaml; print(yaml.__version__, "libyaml" if yaml.__with_libyaml__ else "pure-python")')"
  echo "git: $(git --version)"
} > "$out/rocky8-env.txt"
cat "$out/rocky8-env.txt"

python3 "$tool" sweep --hierarchy --points 3:250,3:1000,3:3000 --reps 3 --work "$work/hierarchy" \
  --json "$out/rocky8-hierarchy.json"
python3 "$tool" sweep --points 20:3000 --reps 1 --work "$work/h3" --json "$out/rocky8-h3.json"
python3 "$tool" coldwrite --records 1000,3000,10000,30000 --reps 3 --work "$work/cold" \
  --json "$out/rocky8-coldwrite.json"

python3 - "$out/rocky8-h3.json" <<'EOF'
import json, sys
point = json.load(open(sys.argv[1]))[0]
reparse = point["micro"]["control_reparse_s"]
print(f"H3 re-parse at {point['point']}: {reparse:.3f} s "
      f"(H3 <= 0.25 s: {'pass' if reparse <= 0.25 else 'FAIL'}; heartbeat bound <= 2.5 s: "
      f"{'pass' if reparse <= 2.5 else 'FAIL'})")
EOF
if [ -n "$created" ]; then rm -rf "$work"; fi
