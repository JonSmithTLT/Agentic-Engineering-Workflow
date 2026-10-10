#!/usr/bin/env bash
# Prepare the lane's arm host (the Rocky 8 VM): a fresh lane directory with this checkout and an offline venv.
# Nothing private is copied here; the oracles arrive only for scoring, after every model run (README.md).
#
#   LANE=~/aew-eval/lbq-v1 bash setup.sh      # run from anywhere; the checkout must already be at $LANE/aew
#
# The venv installs nothing: Python 3.11's own venv, with a .pth naming this checkout's src and the dependency
# directory of an existing AEW venv (PyYAML, jsonschema, referencing, pytest), so no package is downloaded.
set -euo pipefail
LANE=${LANE:-$HOME/aew-eval/lbq-v1}
DEPS=${DEPS:-$HOME/aew-venv/lib/python3.11/site-packages}
PY=${PY:-python3.11}
[ -d "$LANE/aew/src/aew" ] || { echo "no AEW checkout at $LANE/aew" >&2; exit 1; }
[ -d "$DEPS/yaml" ] && [ -d "$DEPS/jsonschema" ] && [ -d "$DEPS/pytest" ] || { echo "no dependencies at $DEPS" >&2; exit 1; }
[ -e "$LANE/venv" ] || "$PY" -m venv --without-pip "$LANE/venv"
site=$("$LANE/venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
printf '%s\n%s\n' "$LANE/aew/src" "$DEPS" > "$site/aew-lane.pth"
cat > "$LANE/venv/bin/aew" <<PYEOF
#!$LANE/venv/bin/python
import sys
from aew.cli.main import main
sys.exit(main())
PYEOF
chmod +x "$LANE/venv/bin/aew"
"$LANE/venv/bin/python" -c 'import aew, yaml, jsonschema, pytest, sys; print("aew:", aew.__file__); print("python:", sys.executable)'
command -v bwrap >/dev/null || { echo "bubblewrap (bwrap) is missing: the raw runs cannot be contained" >&2; exit 1; }
echo "ready: $LANE"
