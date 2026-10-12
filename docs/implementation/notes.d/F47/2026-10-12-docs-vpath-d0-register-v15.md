**Two slices added to the vertical path since the slice list in this row's Notes (the vertical-path plan, as
independently reviewed CLEAR; the designer's decisions of 2026-10-12).** Each re-runs the `vertical` lane and puts its
ledger diff in its pull request, as every slice does.

- **B6 (lane B, F47.3): authenticated-publication isolation plus adversarial bypass tests.** The designer's Decision
  Record of 2026-10-12 on the publication path, verbatim: "D2 — REQUIRED (B6): Demonstrate that Lead and worker
  environments cannot access publication credentials or exercise authenticated external-publication authority through
  any available model-accessible surface. Test applicable shell, Git, GitHub API, credential-store, and agent paths."
  On Linux, B6 isolates the credential routes (the runtime directory and its agent sockets, git's system and global
  configuration and credential helpers, the askpass and SSH-command variables, the discovered credential stores),
  refuses a repository whose configuration carries a credential (without echoing it), and pins an "external-egress:
  none" inventory over every model-accessible surface: the surface map, the typed Lead tools, the broker's relays and
  the worker bridge's operations. Its adversarial tests run from the Lead's and a worker's shell and through the real
  MCP server and broker, with synthetic credentials and local stubs only, and show every `gh`, `git push` and API
  attempt failing for lack of a credential. Residuals its self-test reports go to F51. It comes after B1 and B4,
  depends on G1 (pull request 215), and uses the credential-store discovery helper it shares with B5a (built by
  whichever of the two lands first). Its result is `egress.authenticated: pass` on the Linux profile, scoped to the
  profile and surfaces tested (D5). Windows stays UNQUALIFIED; B5q probes its credential routes (F48). **E requires
  it.**
- **D0c: the vertical UAT specification v3 lines (F47.5).** The egress verdict line (`egress.authenticated`,
  `egress.unauthenticated: UNQUALIFIED` until F51 closes, the `profile` tested and the surfaces tested); the
  control-plane attention measure (the Lead's existing counters plus lifecycle calls per Ticket and turns spent on
  workflow mechanics, with per-scenario baselines), which judges A1, A2 and A4; and a new operator counter,
  `config_edits`, threshold 0, counting any operator edit to git or host configuration needed during a scenario. A
  finding that `doctor` or preflight reports before any launch is a readiness result and is not counted. It depends on
  D0b (merged) and is operator-gated. **Approved by the operator, 2026-10-12:** "yup d0c look good to me only config
  edits should basically just be the model and the site makes that a nice experience eventually". The Lead's reading:
  `config_edits` counts hand edits only; an edit made through the settings editor (F46) or a typed Lead path is not
  counted.
- **E,** the enforce slice (F47.5), depends on both: it requires `egress.authenticated: pass` on the Linux profile
  (B6) and spec D0c.
