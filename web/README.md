# AEW read-only web workbench

React/Vite frontend with accepted API **0.1.2** and separate demo-only provisional Journal, Investigation, Evidence inspection and Execution workflows. Backend schema adoption and live integration are separate acceptance gates.

Start with the [documentation index](docs/README.md), [current status](docs/reference/status.md), [local development](docs/how-to/local-development.md) and [verification guide](docs/how-to/verification.md).

From `web/`, with Node 22 and locked dependencies:

```bash
npm ci --ignore-scripts
npm run dev:demo
```

For the compiled service-worker-free demo:

```bash
npm run build:demo
node --experimental-strip-types scripts/demo-server.mjs
```

Default URL: `http://127.0.0.1:4249/`. This serves local fixtures, not the live Engine. See [HTTP mode](docs/how-to/http-demo.md) for supported workflows and limitations. `npm run build` produces production behavior and rejects preview initialization/fixtures.

Independent reproduction uses the [immutable offline builder](docs/how-to/pinned-web-builder.md), not a fresh network install. Browser staging is a separate prerequisite. Commit runtime changes before freezing evidence from the exact clean detached source tree.

Completed handoffs/reports/screenshots are in the [archive](docs/archive/README.md); the [catalog](docs/reference/catalog.md) resolves older paths. [Current design plans](docs/design/plans/README.md) retain their approved bytes. Do not treat provisional fixture semantics as Engine authority.
