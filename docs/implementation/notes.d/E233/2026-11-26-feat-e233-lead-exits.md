**Seven of the eleven dead ends have an exit (2026-11-26).** Checked against `main` first: all eleven were still
open by the row's own measure (`DEAD_ENDS` in `tests/integration/test_every_state_has_an_exit.py`), though five of
their hints already named a whole command. The action projection now offers the Lead's own move in each of these
states, as a primitive with its whole command and its guard's answer, never auto-runnable. It adds no tool, no
decision kind and no always-sent text.

| Dead end E133 left | Now offered |
|---|---|
| ASSIGNED | `harness launch` first for an implementer no harness was launched for, then `work transition` to RUNNING |
| REVIEW_PENDING, no report and no live run | the reviewer's dispatch (`invoke create --role reviewer --launch`) |
| REVIEW_FAILED | `work transition` to RUNNING; there the implementer's dispatch is offered, second (below) |
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
  not take as offered or that no Lead session reaches. The two verifier dispatches are the reviewer's command with
  another role or scope: parsed, held equal to the hint's, and asked of their own dispatch decision and of the
  launch's profile, not launched by the walk.

- **A dispatch is an exit only where its launch has a harness.** The offered command carries `--launch`, and the
  dispatch decision does not ask the launch. So while the execution policy pins no profile the dispatch is BLOCKED,
  with a blocker that says what to configure (`Engine.launch_refusal`). The walk is made in projects that route to a
  harness, as a Lead session's does, and one leg with no profile is pinned as a dead end the walk found.
- **The walk follows the one next step** the readable result gives, where that step is a command, and takes a move
  by name only where it carries the Lead's reason.

**What remains**

Four of the eleven, each needing a decision this row's builder does not make, and two things found on the way:
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

- **After a return to RUNNING the next step is still the review request, on the unchanged work.** From REVIEW_FAILED
  (and from an inconclusive verification or an escalation returned to RUNNING) the old implementation report still
  satisfies `ticket_request_review`'s gate, so it is offered first, AVAILABLE and auto-runnable, and the implementer's
  dispatch second. This is as on `main`, where the hint's command led to the same place. `ticket_rework`'s decision
  is meant to fix it: one step that returns the Ticket and dispatches the implementer with the findings.
- **With no execution profile, the blocker also stops the steering loop on a Ticket returned to RUNNING.** There the
  review request is available and auto-runnable on the old report, and the loop chose it before. Now the Ticket
  carries the blocker of its implementer's dispatch, so the loop reports BLOCKED and runs nothing, while the readable
  next step still names the review request. Given the point above this is the safer of the two, and the walk pins
  it (`steering_loop.select`); `ticket_rework`'s decision is meant to settle both.
- **A project with no execution profile** offers no dispatch (above): the operator's hand-run flow dispatches without
  `--launch`, which a Lead session is refused. Whether the projection should name that form for an operator is not
  decided here.

Also left, as the row says: `work_amend` stays undecided until a real Lead needs it, and `ticket_rework` stays
proposed. These moves reach rework from the shell door only (`work transition`, then `invoke create`); whether
`ticket_start` carries rework as one typed step, under TLS-21's ceiling of 16 tools, is the designer's. The lands
guard is this row's other pull request, #606.
