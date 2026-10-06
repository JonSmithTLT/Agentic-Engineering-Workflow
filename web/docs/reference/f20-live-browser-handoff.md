# F20.6 authenticated browser handoff

Status: **web-owned authenticated live runner implemented; packaged-server integration acceptance pending**. The [runner guide](../how-to/authenticated-live-browser.md) defines its invocation, version-1 private cookie-file interface, checks and remaining coverage. Existing fixture and HTTP-demo scripts remain separate from live authenticated acceptance.

The main line can proceed with its server/session, API conformance, security and conditional-request tests and invoke the runner against its packaged production server. Browser acceptance remains pending until those actual integration results are recorded. Do not report the complete F20.6 browser gate as passed from the runner's test-adapter regression or convert fixture-specific assertions into live claims.

The runner must accept an explicit target origin and a private session-cookie file, start no fixture servers, and use no response mocks or provisional endpoints. The main line owns the live server, authorized test project, cookie acquisition through F20.3, private scratch file and final integration acceptance record. The web side owns the runner and production UI assertions. Both use the [agreed production baseline](f20-production-baseline.md).

The implemented file interface contains only version, exact origin and one `aew_session` cookie; it does not accept Playwright storage-state JSON or local-storage contents. Service workers are blocked. On POSIX keep the file mode 0600; on Windows restrict access to the operator. Never commit the file or include its contents, credential-bearing URLs, storage state, request headers, traces or HAR in review evidence. Publish only sanitized results and build identities.

Live assertions must exercise accepted production pages against explicitly supplied test records and capability states, without fictional clangd IDs or `fixture` query parameters. Cover navigation, desktop/phone layouts, refusal/session states and the integration checklist's validator/scope and hostile-content checks. Backend negative controls remain main-line tests; preview browser suites remain fixture regressions. The final acceptance records the server commit, static `BUILD.json`, accepted contract digest, commands, platform coverage and outstanding limitations separately from frontend fixture reviews.

This is a dependency/ownership handoff, not live acceptance or a new API contract. The [Engine design note §6](../../../docs/design/proposals/dashboard-main-line-api-design-v0.1.md) describes the integration boundary.
