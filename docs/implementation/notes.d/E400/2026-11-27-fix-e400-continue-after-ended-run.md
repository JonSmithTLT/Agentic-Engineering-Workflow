**Built in part, by #651: a continue over a stage's run that ended with its evidence.** The Lead recommended three
things:
- if the ended run's evidence is still sealed and bound to the current snapshot, `continue` takes it and moves the
  stage on;
- if the snapshot has changed, a fresh attempt;
- the continue never relaunches a run that has ended.

The operator accepted that recommendation on 2026-11-27, adding:

> "For e400. I would say yes if code hasn't changed from.snapshot yes just pick up and finish. If it has its bascially activate recovery procedures and tell them.hey this is what previous worker did. Here's what the requirements were. Here's the end criteria maybe even Here's the diff. Continue."

The same day the operator changed the moved-snapshot case to a relaunch of the same worker rather than a fresh agent:

> "Oh yeah if relaunch is an option to just tell them.to pick up and continue with added context of what changed thats a clean option as well probbaly cleaner than a fresh agent that has to orient itself"

and, on a relaunch that fails at run time:

> "If it fails then thats not a ux failure its graceful degradation and the fix is just the lead recognizing the issue. Aggregating the dtare and then responding woth an agent to fill the gap"

So for a moved snapshot the remedy is a relaunch. What stays from the first point is that the continue itself starts
no run: the relaunch is the Lead's `harness.launch`, which rotates the credential (#142 review).

**What is built** (`StageIntents._launch_check`, `src/aew/engine/stage_intents.py`). Only the launch check of a
launching step whose run is observed `ended_with_evidence` changes. Every other run status is checked as before, pinned
by `test_continue_over_any_other_ended_run_stops_as_it_did_before`.

**Same snapshot: the evidence is taken.** Two conditions must hold:
- The run's records are sealed: the evidence store reports no integrity problem, which is `find_evidence`'s rule.
- Its expected output is bound to the snapshot its invocation evaluates now. That is the latest record of each kind
  the run's contract expected (`expected_kinds`, the set its supervisor counted to call it `ended_with_evidence`),
  checked against the snapshot from `Invocations.invocation_workspace` and `snapshot_of`. The binding test is
  `gates.bound_to`, which `gates._matches` now uses too.

The check reads the expected output, not the last record of any kind. #651's review, M1, found the case: a check run
after the report must not stand in for the report.

When both hold, the check passes and the continue completes the stage, or runs its remaining steps. It starts no run,
and its commit's summary names the evidence it took. The Ticket then moves on through its own unchanged guards.
V2-forced-mid-stage's refusal at this continue is gone.

**Snapshot moved: a named stop.** An implementer's expected output may be bound to a snapshot its workspace has since
moved from, as when it rechecked after its report. Then the continue takes none of it and starts no run. It stops the
stage as `launch_failed`, with `HARNESS_LAUNCH_FAILED` and the reason code `snapshot_moved`, and the stage's committed
steps stand. The message names two next steps; each is tested as the CLI parses it, and run as printed:
- the relaunch (`aew harness launch <inv> --prior-value <run>`). The relaunched run's continuation already lists the
  earlier run, marks its evidence STALE and lists the workspace's changed paths;
- or a fresh attempt: `aew invoke cancel` with a reason, then `aew invoke create <T> --role implementer --launch`. The
  new implementer's pack carries F36's recovery section (the predecessor, its evidence ids and the paths it changed).

**What remains**: three things.

1. **The continue does not relaunch by itself.** The operator's choice is for `continue` to relaunch on a moved
   snapshot. It was not built, for three reasons:
   - §3.4 rule 2 of the typed Lead surface v0.2: the intent records its planned primitive sequence, and a continue
     runs only its uncommitted steps. A relaunch is no step of the stage's plan.
   - §3.4 rule 8: "recovery does not infer intent from current state alone". A relaunch the engine chooses because
     the snapshot moved is that inference.
   - `resolve` expands to no `harness.launch`, so running one inside it would be an unjournaled mutating step.

   So the Lead runs the printed relaunch. If that relaunch is refused or fails, the refusal is `harness launch`'s own,
   as today, and the stop's message has already named the fresh attempt as the alternative. The designer decides
   whether a continue may relaunch, as a planned relaunch step. A journaled "replace the worker" stage (a typed
   invocation cancel, or an atomic supersede-and-redispatch for mutating Tickets) is the other designer-level way in.

2. **The relaunch is not offered as a typed action** (#651 review, m3, recorded as a follow-on). The projection offers
   `harness.launch` only as a primitive action with a CLI fallback, never through a typed tool: no tool in the
   catalog expands to it. Its offer of a relaunch, `relaunchable`, also leaves out an `ended_with_evidence` run.
   Following the stop's relaunch is therefore a shell call (`shell_aew_calls`), whatever the projection lists. Making
   it typed needs a tool that expands to `harness.launch`, which is a change to the catalog and the surface map, and
   so not this follow-on's to make.

3. **Limits.** The named stop is for an implementer at ticket scope. A moved snapshot under any other role (a
   reviewer, a verifier, an integration-scope invocation, a non-mutating executor) still stops as `not_live`, as
   before. That is pinned by `test_a_moved_snapshot_is_snapshot_moved_only_for_a_ticket_implementer`. The vertical
   ledger counts every call that ends `ok: false` as a refusal (`tests/helpers/vertical/ledger.py`, `_lead_call`),
   this named stop included. V2-forced-mid-stage never reaches it, because its workspace is unchanged.
