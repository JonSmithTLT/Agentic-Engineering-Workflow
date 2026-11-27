**Built in part, by #651 (placeholder: the pull request's number once it is opened): a continue over a stage's run
that ended with its evidence.** The operator's ruling of 2026-11-27, on the Lead's recommendation (if the ended run's
evidence is still sealed and bound to the current snapshot, `continue` takes it and moves the stage on; if the snapshot
has changed, a fresh attempt; never relaunch a run that has already ended), which the operator accepted:

> "For e400. I would say yes if code hasn't changed from.snapshot yes just pick up and finish. If it has its bascially activate recovery procedures and tell them.hey this is what previous worker did. Here's what the requirements were. Here's the end criteria maybe even Here's the diff. Continue."

and, choosing a relaunch for the moved snapshot over a fresh agent, the same day:

> "Oh yeah if relaunch is an option to just tell them.to pick up and continue with added context of what changed thats a clean option as well probbaly cleaner than a fresh agent that has to orient itself"

and, on a relaunch that fails at run time:

> "If it fails then thats not a ux failure its graceful degradation and the fix is just the lead recognizing the issue. Aggregating the dtare and then responding woth an agent to fill the gap"

**What is built** (`StageIntents._launch_check`, `src/aew/engine/stage_intents.py`). Only the launch check of a
launching step whose run is observed `ended_with_evidence` changes; every other run status is checked as before, pinned
by `test_continue_over_any_other_ended_run_stops_as_it_did_before`.
- **Same snapshot: the evidence is taken.** When the run's records are sealed (the evidence store reports no integrity
  problem, `find_evidence`'s rule) and the last of them is bound to the snapshot its invocation evaluates now
  (`Invocations.invocation_workspace` and `snapshot_of`; the binding test is `gates.bound_to`, which `gates._matches`
  now uses too), the check passes and the continue completes the stage, or runs its remaining steps. It starts no
  run. The Ticket then moves on through its own unchanged guards. V2-forced-mid-stage's refusal at this continue is
  gone.
- **Snapshot moved: a named stop.** When an implementer's evidence is bound to a snapshot that its workspace has
  since moved from, the continue takes none of it and starts no run. It stops the stage as `launch_failed`, with
  `HARNESS_LAUNCH_FAILED` and the reason code `snapshot_moved`. The stage's committed steps stand. The message names
  two next steps, each tested as the CLI parses it and run as printed:
  - the relaunch (`aew harness launch <inv> --prior-value <run>`), whose run's continuation already lists the earlier
    run, marks its evidence STALE and lists the workspace's changed paths;
  - or a fresh attempt: `aew invoke cancel` with a reason, then `aew invoke create <T> --role implementer --launch`,
    whose pack carries F36's recovery section (the predecessor, its evidence ids and the paths it changed).

**What remains**: the continue does not relaunch by itself. The operator's choice is for `continue` to relaunch on a
moved snapshot. That was not built, because it needs a step outside the stage's plan:
- the intent records its planned primitive sequence, and a continue runs only its uncommitted steps (typed Lead surface
  v0.2 §3.4, rules 2 and 8);
- `resolve` expands to no `harness.launch`;
- run after the continue's commit, the relaunch would be a second commit, with a crash window between the two that
  nothing records.

So the Lead runs the printed relaunch. If that relaunch is refused or fails, the refusal is `harness launch`'s own, as
today, and the stop's message has already named the fresh attempt as the alternative. Who decides: the designer, on
whether a continue may relaunch (a planned relaunch step, or `resolve` expanding to `harness.launch` with the crash
window closed). The designer-level alternative, a journaled "replace the worker" stage (a typed invocation cancel, or
an atomic supersede-and-redispatch for mutating Tickets), is the other way in.

Limits: the named stop is for an implementer at ticket scope. A moved snapshot under any other role (a reviewer, a
verifier, an integration-scope invocation, a non-mutating executor) still stops as `not_live`, as before. The vertical
ledger counts every call that ends `ok: false` as a refusal (`tests/helpers/vertical/ledger.py`, `_lead_call`),
including this named stop. V2-forced-mid-stage never reaches it, because its workspace is unchanged.
