# Joint run 2 evidence

Runtime: website `af77308aa48cbc73a73791b58b807c0a9ebdbe55`, reviewed wrapper `f8dd097cf9f929c1759820b66b4f169cb32fad11`, backend `966fc2c610c7b9e26c8d9d9f004139532c956520`. Fresh synthetic `joint-state-2`. No real credentials/project. See `../../JOINT-TEST-NOTES.md` for the normalized launch commands, full chronology, gap classifications and remaining decisions.

- `run-identity.json`: actual wrapper start/expiry, source commits and request hash.
- `browser-environment.json`: headless Edge/Node versions and the two responsive viewports.
- `traffic.json`: 29 primary browser responses with exact paths, version headers, request bodies and response-body hashes. The two lost-response POST replies are separately recorded in `lost-*.json`; they are not missing command attempts.
- `session.json`: capture chronology, command POST counts and page errors. `*-before-driver-correction.json` preserves the earlier trace before strengthening capture waits.
- `operator-events.json`: explicitly attributed switch times from the operator's relay of backend logs.
- `owner-observation.json`: owner-reported ledger counts and three exact timestamped POST log lines. These counts are not inferred from the partial list.
- `lost-held-response.json`, `wrapper-stop.json`, `wrapper-restart.json`, `lost-reconciled.json`, `lost-session.json`: controlled response-loss staging and byte-identical lookup. The real reply was held by a browser barrier; the owned wrapper was stopped before release/deadline, then the route was aborted. This is not an uninstrumented socket-loss test.
- `verification.json`: all 29 primary body hashes checked; held/reconciled request and response bytes equal original; clean runtime snapshots and unchanged production/demo/STG-02 inventories. Remote assurance not observed.
- `SHA256SUMS.txt`: inventory of selected committed evidence. Both width screenshots and state text are included for each selected step/probe label.

Accepted negative-state screenshots use `probe-outage-run-503-settled`, `probe-outage-work-503-confirmed`, `probe-outage-waiting-partial-settled` and `probe-entitlement-owner-404-settled`, plus the run/work/waiting/index refusal captures. Early work-503 Loading and same-view owner-refresh captures are inconclusive and excluded from this selected image set; full originals remain in ignored local artifacts. The protected-actions step is visible in `05-owner-index`, backed by the session's original zero-button check; a later overwritten `06-protected` image is excluded.

One journey resized to 1440×1000 and 390×1000 does not establish human usability or physical-device coverage. The encoded owner route now succeeds; missing supplied run links and interim reason vocabulary still require designer triage. This bundle is author evidence, not independent joint acceptance or green CI.
