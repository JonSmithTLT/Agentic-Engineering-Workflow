**A1-0, the planned dispositions and the G3 measurement** (the A1 slice plan, reviewed CLEAR, §2.1, §3.4 and §6's
A1-0 row; data and tests only, no behaviour change). [`surface-map.yaml`](../../surface-map.yaml) now records, on
each of the 36 still-`undecided` Lead-reachable commands, its `planned` disposition, homes, primitive, landing slice
and reason, and lists the homes not built yet under `proposed_tools` (`ticket_rework`, `work_amend`, F9-A's
`message_send`) and `proposed_choices` (13 `resolve` choices). The planned rows and both lists are digest-pinned and
only shrink. Two new enforced checks hold the rule: `home_built` ("home built ⇒ row decided") and `out_of_door`
("out of the door ⇒ row decided"); two report checks list the A2 debts (`planned_sweep`: `work.staff` and
`history.load`) and the planned rows by slice (`planned_by_slice`). `aew.surface.contract.RESOLVE_CHOICE_PRIMITIVE`
lands with today's pairs and owns `resolve`'s choices and `expands_to`; the door proof checks a `resolve` home by its
pair (`via_choices`).

The G3 spike, measured by the cap test's own measure with catalog-only candidate rows: today's normal surface is
exactly the 11,694 B pin; the fold −319 B and `status.runs` +119 B (A1a-1 net −200 B); `ticket_rework` +923 B; A1a-2
net +284 B; `resume`'s readOnlyHint (A1b) +1 B; A1 composed 12,702 B, 15 tools. The figures go to the designer's G3
question; the 11,694 B assertion is unchanged until it is answered.
