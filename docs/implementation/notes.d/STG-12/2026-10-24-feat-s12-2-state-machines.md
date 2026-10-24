**S12-2, pull request 7 of 10 (2026-10-24): the state machines (family 5).**
The reference gains six families, on one page ([`docs/reference/state-machines.md`](../../../reference/state-machines.md)):
`transitions` (one record per edge of `aew.engine.transitions.RULES`), `states`, `guards`, `reason-rules`, and the two
other machines the product has a table for, `configuration-states` and `usage-live-states`.

- **The table does not stop a bypass, so the edge records say which edges are exposed.** `WorkUnits.set_state` is where
  a Lead decision or an event changes a Ticket's state and the state hooks run, but it does not call
  `transitions.check` (its callers do), and three writers assign a state themselves, so the hooks do not act on their
  edges: `recompute_readiness` (BLOCKED and READY, the `recompute` rules), `Lead._interrupt_invocations` (into
  INTERRUPTED, the `interrupt` rules) and `recompute_parents` (a Story's or Epic's derived phase). A detector pair
  (`ast`, and a text reading that shares no code) finds every state-write site in the package; one with no
  `transitions.check` call in its function is an unresolved item on the edges it can take, through a declared table of
  its operations (`SITES` in `tools/reference_families/machines.py`), held to the detector in both directions. Today 72
  of the 94 edges are lower-bound for that reason and 22 are complete-by-construction. A site the table does not know is
  unresolved on every edge, so a new unchecked write is never silent. Whether a direct write is intended is the trace's
  judgement, not the reference's. The `set_state` docstring, which said it was the single place a state changes, now
  names the three writers: the only `src/` change, comment-only.
- **Two more state sets are not in `STATES`.** A Story's or Epic's phase is derived (`aew.engine.hierarchy.PARENT_STATES`),
  and the control schema's work unit state enum admits one more state that no table lists. Both are unresolved items of
  the `states` records, read from their owners. `usage_live.PROMPT_STATES`, a second tuple beside `STATES`, is one of
  the `usage-live-states` records. They are in `gaps.md`; none is a family (the series is frozen).
- **Edges of the two small machines are not recorded.** Neither module has an edge table, so each state's `exits` is an
  empty list whose `fact_coverage` is lower-bound with the one unresolved item "no edge table": an empty list found
  by a detector never means none.
- **Guards are read from an `Engine`.** The guard table is filled by the composition root, so the generator builds an
  `Engine` in a temporary directory (its construction touches no file) and reads the table for each guard name a rule
  names: the evaluator per unit kind and whether it has a query form. The names the rules use, the names registered and
  the records are one set, tested both ways.
- **What a change to the machines does.** Adding an edge, a state or a guard, or adding or removing a state write,
  changes the page and the index: run `python tools/reference.py render` and commit `docs/reference/`. A new unchecked
  state write fails nothing; it is listed on every edge until it is declared in `SITES`.
