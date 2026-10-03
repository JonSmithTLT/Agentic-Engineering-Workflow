# Service-worker-free fixture demo

From `web/`, after the demo build, use pinned Node22:

```bash
node --experimental-strip-types scripts/demo-server.mjs
```

Open `http://127.0.0.1:4249/knowledge?fixture=F1&selected=J-05`. `DASHBOARD_PORT` and `DASHBOARD_STATIC_ROOT` configure the listener and compiled demo root. The server binds localhost and serves the demo build, accepted fixture projections and provisional Journal projections. It is a local fixture adapter, not a backend implementation or live integration. Production continues to exclude demo initialization, handlers and fixtures.

The server supplies a document marker that selects HTTP transport; the app never imports or registers the service-worker adapter in this mode. Same-origin demo request headers select the page's fixture/fault without shared browser cookies, preserving independent tab scopes. Component/type/cursor parameters and Journal cases keep their current APIs. GET/HEAD, conditional ETags and strict CSP remain enforced. Unknown fixture identity is rejected.

Normal F1–F11 fixture browsing, Journal cases and Contract Playground are available. Stateful Scenario Lab replay recipes require the original service-worker demo; the HTTP mode explicitly explains that boundary and does not pretend to run a recipe. Vite demo preview remains available for existing replay/browser suites.

`scripts/browser-http-demo.mjs` runs with service workers blocked, verifies the fictional investigation and selected-item/focus/legend fixes, and checks HTTP status, conditional requests, fixture switching and production boundaries. It accepts `CHROMIUM_PATH` with the established staged fallback.
