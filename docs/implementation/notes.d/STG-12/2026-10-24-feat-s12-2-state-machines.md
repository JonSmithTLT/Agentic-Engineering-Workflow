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
  its operations (`SITES` in `tools/reference_families/machines.py`), held to the detector in both directions. The
  interrupt writer is placed only on the `interrupt` edges that leave a state its owner names
  (`lead_ops.PHASE_DRIVERS`, read from the owner: the phases that wait on an invocation), held to `RULES` both ways and
  to `Lead._phase_waits_on`, the only gate to the write. Today 65 of the 94 edges are lower-bound for that reason and 29
  are complete-by-construction. A site the table does not know is unresolved on every edge. Whether a direct write is
  intended is the trace's judgement, not the reference's. The `set_state` docstring, which said it was the single place
  a state changes, now names the three writers: the only `src/` change, comment-only.
- **The limit of that pin.** Sites are found per function, with the forms of write each makes. A new unchecked write in a
  function the table does not declare fails `check` and `test_every_state_write_site_is_behind_the_table_or_declared`
  (the build still renders, with the site unresolved on every edge). A second write of the same form inside a function
  that is already declared, or that already asks the table, is not a difference: writes are not counted per function.
- **Other state sets are not in `STATES`.** A Story's or Epic's phase is derived (`aew.engine.hierarchy.PARENT_STATES`),
  the control schema's work unit state enum admits one more state that no table lists, and three other machines have a
  `["state"]` key a declared site writes (an integration queue entry, a validation run, a projected field value). Each is
  an unresolved item of the `states` records, read from its owner or from the declared sites. `usage_live.PROMPT_STATES`,
  a second tuple beside `STATES`, is one of the `usage-live-states` records. They are in `gaps.md`; none is a family (the
  series is frozen). A state set that is not a tuple of strings named `*STATES` in a machine's module is not seen.
- **Edges of the two small machines are not recorded.** Neither module has an edge table, so each state's `exits` is an
  empty list whose `fact_coverage` is lower-bound with the one unresolved item "no edge table": an empty list found
  by a detector never means none. A state's `position` is its index in the module's order.
- **The configuration states have a check of their own.** Their label is complete-by-construction on two readings that are
  not the generator's: the constants `configuration` defines are `STATES`, in order, and the states its producer returns
  (read from its source, and by running it over every input) are in `STATES`.
- **Guards are read from an `Engine`.** The guard table is filled by the composition root, so the generator builds an
  `Engine` in a temporary directory (its construction touches no file) and reads the table for each guard name a rule
  names: the evaluator per unit kind and whether it has a query form. The names the rules use, the names registered and
  the records are one set, tested both ways. Every `coverage.registry` of a record resolves to an object (a series-wide
  test in the fast lane).
