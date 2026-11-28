**O-IDS rule precision: the first of E188's O-IDS pull requests** (the triage's row 1). The rule changes, each with a
planted test in `tests/unit/test_discovery_rules.py` that fails with it undone, and vertical-uat.md §8.2 amended to
state them:
- **R1, the operator's ruling of 2026-11-28:** in a runtime output, an id or binding the output fills in itself is not
  an ask; a placeholder the reader must look up still is. The capture plugin marks its outputs as runtime
  (`rules.Output.runtime`), and there `o_ids` judges an id-typed slot or an engine-format id only when it is a
  placeholder. Static texts keep every bullet (U1).
- **R2:** a placeholder that lists its values (`<a|b>`, none of them a placeholder) is §8.2's "slot whose values the
  text lists" (`rules.listed_values`), each value judged as a value of its slot. One that lists a placeholder
  (`<implementer|N>`) stays a placeholder; before, only its first alternative was read.
- **R3:** a Ticket's slot is read from the parser (`rules.is_work_action`: a work unit named in the argument's dest or
  metavar), replacing the hand-kept `WORK_DESTS`, which missed `--from`. The CLI's Ticket options that named no work
  unit now carry the metavar `WORK-ID`.

**Measured** as the triage measured: its 119 tests that reach O-IDS keys, run at `129bbaf4` (Linux) with every
judged output recorded, then judged with the rules before and after. 131 O-IDS runtime keys observed before, 112
after: **19 cleared** (12 of them new against the allow-list, 7 listed), none added: `harness launch`, `send`,
`status` and `wait`, `invoke create`, `plan assess`, `record body|NOT_FOUND`, `work assign` and `work dispatch`, and
the `result` of `integration_publish`, `probe_named`, `probe_start`, `ticket_prepare`, `ticket_request_review`,
`ticket_request_verification` and `ticket_start`. The static keys are unchanged (R3 changes one finding's detail).
Nothing is removed from the allow-list here: the full-tier run shows which listed keys are now stale, and the stale
removals are the triage's row 5. Not covered: Windows, and outputs of tests outside the 119.

**What remains** (2026-11-28): the triage's rows 2 to 6 for O-IDS (the authority-candidate next action, free text to
the elision, values the engine knows, the stale removals and residuals with the operator, then the flip), and
O-WORDS, which stays in shadow until DX3.
