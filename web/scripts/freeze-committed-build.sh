#!/usr/bin/env bash
set -euo pipefail
# Evidence builds must read an immutable Git checkout, never the operator tree.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REF="${1:?Supply the full source commit SHA}"
[[ "$REF" =~ ^[a-f0-9]{40}$ ]] || { echo 'Full commit SHA required' >&2; exit 1; }
: "${SPT_FRONTEND_IMAGE:?Set the immutable builder image}"
COMMIT="$(git -C "$ROOT" rev-parse --verify "$REF^{commit}")"
mkdir -p "$ROOT/web/artifacts/commit-freeze"
STAGE="$(mktemp -d "$ROOT/web/artifacts/commit-freeze/run-XXXXXXXX")"
git -c core.autocrlf=false clone --quiet --shared --no-checkout "$ROOT" "$STAGE/source"
git -C "$STAGE/source" -c core.autocrlf=false checkout --quiet --detach "$COMMIT"
test -z "$(git -C "$STAGE/source" status --porcelain)"
test "$(git -C "$STAGE/source" rev-parse HEAD)" = "$COMMIT"
SOURCE_TREE="$(git -C "$STAGE/source" rev-parse HEAD^{tree})"
SPT_FRONTEND_IMAGE="$SPT_FRONTEND_IMAGE" bash "$STAGE/source/web/scripts/offline-gate.sh" > "$STAGE/offline-gate.log" 2>&1
test -z "$(git -C "$STAGE/source" status --porcelain)"
for MODE in dist dist-demo; do
  (cd "$STAGE/source/web/artifacts/offline-gate/$MODE"; find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$STAGE/$MODE.SHA256SUMS"
done
python3 - "$ROOT" "$STAGE" "$COMMIT" "$SOURCE_TREE" "$SPT_FRONTEND_IMAGE" <<'PY'
import hashlib, json, pathlib, sys
root, stage = map(pathlib.Path, sys.argv[1:3])
report = {'source_commit': sys.argv[3], 'source_tree': sys.argv[4], 'builder': sys.argv[5],
          'method': 'Local shared clone, detached explicit commit, core.autocrlf=false; clean tracked/untracked tree before and after offline gate.',
          'gate': 'PASS', 'network': 'none', 'checkout': str((stage/'source').relative_to(root)),
          'build_trees': {name: hashlib.sha256((stage/(name+'.SHA256SUMS')).read_bytes()).hexdigest() for name in ('dist','dist-demo')}}
(stage/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
PY
