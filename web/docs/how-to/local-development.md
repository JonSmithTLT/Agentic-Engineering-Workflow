# Local development

Use Node 22 (`>=22.13 <23`); reproducible validation pins Node **22.22.2** and npm **10.9.7**. Run commands from `web/` unless stated otherwise. Install the locked dependencies with `npm ci --ignore-scripts`; the independent offline gate uses its pre-staged cache instead of the network. Do not update the dependency lock to repair a local environment.

```bash
npm run dev:demo
npm run build:demo
node --experimental-strip-types scripts/demo-server.mjs
```

The first command runs the worker-backed Vite demo. The last two serve compiled demo fixtures over HTTP on localhost, default port 4249; see [HTTP demo](http-demo.md). Stop an owned server before reusing its port. Preserve other checkouts and servers.

```bash
npm run dev
npm run build
npm run preview
```

These use production behavior and the accepted API. Production requires the actual authenticated same-origin backend; compiling it alone supplies no live data. `scripts/projection-server.mjs` is a production-build test fixture server, not Engine integration.

For the immutable offline carrier and separate Chromium staging, follow [pinned builder](pinned-web-builder.md) and [verification](verification.md). Windows and WSL Docker engines have separate image stores. A stable checkout alias does not change Git worktree ownership; use the shell that can resolve its Git metadata.
