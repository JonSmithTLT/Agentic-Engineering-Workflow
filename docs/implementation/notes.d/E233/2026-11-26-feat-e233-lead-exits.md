**Seven of the eleven dead ends have an exit (2026-11-26).** Checked against `main` first: all eleven were still
open by the row's own measure (`DEAD_ENDS` in `tests/integration/test_every_state_has_an_exit.py`), though five of
their hints already named a whole command. The action projection now offers the Lead's own move in each of these
states, as a primitive with its whole command and its guard's answer, never auto-runnable. It adds no tool, no
decision kind and no always-sent text.

| Dead end E133 left | Now offered |
|---|---|
| ASSIGNED | `work transition` to RUNNING, and `harness launch` for an implementer no harness was launched for |
| REVIEW_PENDING, no report and no live run | the reviewer's dispatch (`invoke create --role reviewer --launch`) |
| REVIEW_FAILED | `work transition` to RUNNING, then the implementer's dispatch |
| VERIFY_PENDING, no report and no live run | the verifier's dispatch |
| VERIFICATION_INCONCLUSIVE | `work transition` to VERIFY_PENDING (or RUNNING), with the Lead's reason |
| COMMIT_READY, prepared with no report | the integration verifier's dispatch (`invoke create --scope integration --launch`) |
| ESCALATED | `work transition` to each phase the return admits, with the Lead's reason |

In any state, an active invocation whose latest run ended without its output is offered its relaunch
(`harness launch`), as the engine's guidance already said in words.

- **One owner each.** The transitions come from `transitions.lead_moves` and `transitions.command`; the dispatch from
  `Resume.worker_needed`, which the hints' own branches now read; the relaunch from `contract.relaunchable`, held
  equal to the guidance's text by a test. The hints for ASSIGNED, REVIEW_FAILED, VERIFICATION_INCONCLUSIVE and
  ESCALATED now name the command.
- **A move that carries the Lead's reason** (a return or a regression) is judgment-bearing. The readable result
  lists it, and its one next step stays the engine's hint, which says what is settled first.
- **An exit must land.** The walk fails on an offered command, an action's or a decision's, that the real CLI does
  not take as offered or that no Lead session reaches. It goes on by the moves it is offered, run as offered: the four
  transitions, and a reviewer's dispatch and a never-launched implementer's launch where a harness is routed. The two
  verifier dispatches are the reviewer's command with another role or scope: parsed, and asked of their own dispatch
  decision, not launched by the walk.

**What remains**

Four of the eleven, each needing a decision this row's builder does not make:
- **BLOCKED with no plan, and REPLAN_REQUIRED.** The way on is a plan revision. Proposing one takes the plan's body
  on standard input and one of three assurance forms, so no single offered command states it, and accepting it is
  being changed to need the operator's confirmation, in work now in flight. The typed home is E163's. Recommended:
  once that work merges, E163 designs propose and accept together, and the projection offers them.
- **RUNNING with no report.** The measure says waiting is no exit, and here waiting is the move. A run that ended
  without its report is now offered its relaunch, and a live run its wait. What is left is a worker run by hand from
  its pack, which leaves no run to wait on. Recommended: the designer rules that a wait on the live run of the role
  the state waits on is that state's exit, and the walk then reaches RUNNING through a launched run.
- **COMMIT_READY, prepared, with an entry that awaits the Lead on a report that is not clean.** The moves are a
  requeue, a return to RUNNING or a replan. `integrate.requeue` has no guard query, so its availability could only be
  UNKNOWN, which the steering loop reads as a stop only the Lead clears; and whose decision a queue disposition is
  belongs to E335 and E350. The projection still carries the requeue's bound command under `cli_fallback`. Recommended: give
  `integrate.requeue` a guard query, and offer it once E335 states its owner.

Also left, as the row says: `work_amend` stays undecided until a real Lead needs it, and `ticket_rework` stays
proposed. These moves reach rework from the shell door only (`work transition`, then `invoke create`); whether
`ticket_start` carries rework as one typed step, under TLS-21's ceiling of 16 tools, is the designer's. The lands
guard is this row's other pull request, #606.
