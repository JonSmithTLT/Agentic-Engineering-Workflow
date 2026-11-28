**PR 2 is merged, and the row stays open for the qualification (the register reconcile of 2026-11-26).** The selector
and the Linux relay route for a worker's plan login merged as #468 (`3b79d9b8`, 2026-11-14), and the offline
qualification tool's fixes as #471 (`dacb2646`, 2026-11-14). **What remains** is what the row's When names: the keyless
qualification against the pinned OpenCode (2.2.6), which records the version in
`capabilities.PLAN_LOGIN_QUALIFIED_VERSIONS`. That tuple is empty at `b71908e0`, so `plan_login` is still refused at
adoption (`policy/execution.py`, `PLAN_QUALIFICATION`), as the row intends until then.
