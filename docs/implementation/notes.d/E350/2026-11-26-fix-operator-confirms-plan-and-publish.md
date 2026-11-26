**Built (`fix/operator-confirms-plan-and-publish`), part of the row's Work, on the operator's ruling of 2026-11-26:**
plan acceptance and publish are the operator's decisions, confirmed through the operator channel. In the operator's
words: "Its me basically approving a plan fits requirements and final verification of the outputs actually does what I
want it to".

- **The confirmation.** `aew operator confirm plan <T>` and `aew operator confirm publish <T>`, at the operator's own
  terminal, ask the operator endpoint, which shows the exact plan (path and SHA-256) or candidate (commit, base, changed
  paths) with a one-time code, typed back at the requesting terminal: the path `aew lead mode raise` uses. The endpoint
  records the confirmation with the principal only it constructs, one per decision and unit, in
  `.aew/local/operator/confirmations.json`, which a contained run cannot see (`src/aew/engine/operator_decisions.py`).
  It is held beside control state and moves no revision, so the Lead's call at the revision it asked at is not
  refused as stale; the commit that uses it names it in the transition log.
- **What a Lead session needs.** `plan accept` and `integrate publish` stay in `LEAD_REACHABLE`, and a Lead session's
  call (the broker's relay, the typed `integration_publish`, the steering loop) is refused with
  `OPERATOR_AUTHORIZATION_REQUIRED` until a confirmation of exactly that plan or candidate stands
  (`operator_confirmation_required`, `operator_confirmation_stale`), and uses it up. The refusal names the command to
  ask the operator for. No argument, flag or reason string carries a confirmation, and `aew operator confirm` is
  refused in a Lead session (`lead_broker.OPERATOR_CONFIRMS`).
- **The operator's own call** (`aew plan accept`, `aew integrate publish` at their terminal with the Lead credential)
  is the decision itself and asks nothing more. Who is asked is read from the call's dispatch channel: the broker's
  ingresses and the steering loop are a Lead session's.
- **The limit, as for a steering raise:** the guarantee is `dev`. A Lead that runs as the operator's own account is
  held by the same-uid residuals the endpoint reports (`operator_client.RESIDUALS`), not by this.
- **The vertical UAT:** the scripted operator answers the plan and publish questions in chat and confirms each at the
  endpoint with its code. Steps 5 and 7 stay "not built", their fallbacks stand, and no expected count moved.
- **The Lead's guide:** the core gains one rule, and its opening line no longer says the Lead accepts plans and makes
  every decision (the follow-on #597's quick check gave this pull request, m2; it names no owner, since `aew.owners`
  had not merged). Together 270 B, with no allocation: it sits in the room the operator's reserve keeps under the
  40000 B cap, for the operator to accept (`lead-context-pool.yaml`).
- **Tests:** `tests/integration/test_operator_decisions.py`.

**What remains**

- The row's other commands: `verify ingest` (PUBLISH's verifier variants), `verify classify` and `work reconcile` are
  still Lead-reachable with no confirmation, and the placements of `lead release` and `lead handoff cancel` are not
  yet checked against L14 and L13.
- The wire replacement: `DECIDE_WORK_PROPOSAL` (W02) and `APPROVE_INTEGRATION` (W09) as G3-protected O-01 actions. A
  consumed G3 approval then stands in for the typed code at the endpoint, as `SET_STEERING_MODE` does
  (`g3_adapter.BINDINGS`); the binding to the plan or candidate and its single use stay as built here.
