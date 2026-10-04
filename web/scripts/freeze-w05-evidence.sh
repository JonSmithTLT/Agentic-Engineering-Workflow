#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${PINNED_NODE22:?Set the pinned Node 22 executable absolute path}"
: "${CHROMIUM_PATH:?Set the pinned Chromium executable absolute path}"
test "$("$PINNED_NODE22" --version)" = v22.22.2
REPORT="$(bash "$ROOT/web/scripts/freeze-committed-build.sh" "${1:?Supply full source commit SHA}")"
REL="$(printf '%s' "$REPORT" | python3 -c 'import sys,json; print(json.load(sys.stdin)["checkout"])')"
CHECKOUT="$ROOT/$REL"
STAGE="$(dirname "$CHECKOUT")"
ln -s "$ROOT/web/node_modules" "$CHECKOUT/web/node_modules"
ln -s artifacts/offline-gate/dist-demo "$CHECKOUT/web/dist-demo"
(
  cd "$CHECKOUT/web"
  "$PINNED_NODE22" scripts/browser-w05.mjs > "$STAGE/browser-w05.log" 2>&1
)
test -z "$(git -C "$CHECKOUT" status --porcelain)"
for MODE in dist dist-demo; do
  (cd "$CHECKOUT/web/artifacts/offline-gate/$MODE"; find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$STAGE/$MODE.after-browser.SHA256SUMS"
  cmp "$STAGE/$MODE.SHA256SUMS" "$STAGE/$MODE.after-browser.SHA256SUMS"
  (cd "$CHECKOUT/web/artifacts/offline-gate/$MODE"; sha256sum -c "$STAGE/$MODE.SHA256SUMS") > "$STAGE/$MODE.verified.log"
done
python3 - "$STAGE" <<'PY'
import json,pathlib,sys
stage=pathlib.Path(sys.argv[1]); report=json.loads((stage/'provenance.json').read_text())
checks=json.loads((stage/'source/web/output/playwright-w05/result.json').read_text())['checks']
assert checks and all(c['result']=='PASS' for c in checks)
report.update(browser_groups=len(checks), browser='PASS; executed within committed checkout', build_unchanged_after_browser=True, source_clean_after_browser=True)
(stage/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
PY
