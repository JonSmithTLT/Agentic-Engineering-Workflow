#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${SPT_FRONTEND_IMAGE:?Set SPT_FRONTEND_IMAGE to the validated sha256 image ID}"
[[ "$IMAGE" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Immutable image ID required' >&2; exit 1; }
mkdir -p "$ROOT/web/artifacts/offline-gate"
docker run --rm -i --network none \
  -v "$ROOT:/source:ro" -v "$ROOT/web/artifacts/offline-gate:/evidence" \
  "$IMAGE" bash -s <<'SCRIPT' 2>&1 | tee "$ROOT/web/artifacts/offline-gate.log"
set -euo pipefail
mkdir -p /tmp/aew/docs/design
cd /source
tar --exclude=web/node_modules --exclude=web/artifacts --exclude=web/output --exclude=web/.playwright-cli --exclude=web/dist --exclude=web/dist-demo -cf - web docs | tar -xf - -C /tmp/aew
cd /tmp/aew/web
test ! -e node_modules
node --version; npm --version
sha256sum package-lock.json /opt/spt-frontend/frontend-npm-manifest.json /opt/spt-frontend/SHA256SUMS
npm ci --offline --ignore-scripts
npm ls --all
node --test scripts/live-inputs.test.mjs
cp src/api/types.ts /tmp/types-before.ts
npm run generate:types
cmp src/api/types.ts /tmp/types-before.ts
node scripts/generate-additive-schemas.mjs --check
node --experimental-strip-types scripts/generate-stg02.mjs --check
node scripts/check-contract.mjs
npm run check:scenario
node --experimental-strip-types scripts/journal-artifact.mjs
node --experimental-strip-types scripts/investigation-artifact.mjs
node --experimental-strip-types scripts/evidence-artifact.mjs
node --experimental-strip-types scripts/execution-artifact.mjs
npm run check:docs
npm run typecheck
npm run lint
npm test
npm run build
npm run build:demo
node node_modules/vite/bin/vite.js build --mode stg02
rm -rf /evidence/dist /evidence/dist-demo /evidence/dist-stg02
cp -r dist dist-demo dist-stg02 /evidence/
SCRIPT
