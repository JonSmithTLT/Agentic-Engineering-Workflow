#!/usr/bin/env bash
# Connected staging only. The npm cache carrier deliberately excludes browsers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${SPT_FRONTEND_IMAGE:?Set the validated immutable carrier image ID}"
[[ "$IMAGE" =~ ^sha256:[a-f0-9]{64}$ ]] || exit 1
mkdir -p "$ROOT/artifacts/playwright"
docker run --rm -v "$ROOT:/source:ro" -v "$ROOT/artifacts/playwright:/artifacts" \
  -e PLAYWRIGHT_BROWSERS_PATH=/artifacts/browsers "$IMAGE" sh -c '
    set -eu
    node /source/node_modules/playwright/cli.js --version
    node /source/node_modules/playwright/cli.js install chromium
    cp /source/node_modules/playwright-core/browsers.json /artifacts/browsers.json
    node -p "require(\"/source/node_modules/playwright/package.json\").version" > /artifacts/playwright-version.txt
    cd /artifacts
    find browsers -type f ! -path "*/.links/*" -print | sort | xargs sha256sum > SHA256SUMS
    sha256sum browsers.json playwright-version.txt >> SHA256SUMS
  '
