# V-01's burn-down: the vertical UAT's failures mapped to fixes

**Status:** living implementation document (operator, 2026-11-26: a V-01 burn-down plan page, its missing rows filed,
and a check that keeps it from going stale). It is not a design and decides nothing: each fix is its register row's,
and each question below is the operator's or the designer's. The operator answered Q1, Q5, Q7 and Q10 on 2026-11-26.
The alpha scripted gate passed at the re-measure of 2026-11-27 (`f848983e`); the strict gate still fails 4 of the 8
cases the alpha reads, and its other ten were not re-run (below, "The order"). It changes no threshold: those are
[`vertical-uat.md`](vertical-uat.md)'s, which only the operator changes.

**What it maps.** V-01's acceptance oracle, the [vertical UAT](vertical-uat.md), is red on Linux. This page maps the
re-measure of 2026-11-26 to fixes: `pytest --lane vertical tests/acceptance/test_vertical_path.py` at `3640b585` (#595),
14 failed and 4 passed, the same as CI runs 45733486683 (`b71908e0`) and 45744120018. The cases, the counters and their
thresholds, the hard limits, V1's exact decisions and V01-01's 13 steps are the oracle's: they are named here and never
copied (`tests/helpers/vertical/ledger.py`, `tests/helpers/vertical/oracle.py`, and the cases in
`tests/acceptance/test_vertical_path.py`). The line numbers cited are at `eece01e5`.

**How it stays true.** `tests/unit/test_v01_burn_down.py` reads both tables below and fails when:
- a breach category the ledger or the oracle defines has no entry in the categories table, or an entry names one they
  no longer define;
- a step the oracle derives as not landed names no open cluster;
- a cluster names a row the register does not have, a cluster not done names a closed row, or a done cluster names an
  open one.

So the pull request that closes a cluster's last row marks that cluster `done` here, in the same change. A pull request
that closes one row of a cluster's several takes that row out of the cluster's Rows cell in the same change, or names
there the row that now holds what remains: a note on the row is not enough, because the guard fails on a cluster that
is not done and still names a closed row.

**What the guard cannot see.**
- It reads a state only against its rows being open or closed. `open` and `in flight (#N)` are the same to it, and the
  pull request a state names is never read: a fix that merges without closing its row leaves its cluster not done, and
  nothing fails. C7 and C8 went to `done` when E376 and E377 were closed after #603 merged, by the agreement between #603 and this
  page's pull request, not by the guard.
- A category's clusters are checked only for existing, except a step's, where one must not be done: a counter's entry
  can go on naming a done cluster.
- It reads a cluster's rows only from the backticked ids of its Rows cell: an id written without backticks, or
  anywhere else on the page, is not checked.
- It does not read the case-specific checks of `tests/acceptance/test_vertical_path.py`, nor `HARNESS_FAULTS`.

## The clusters

Class: **product** (a product defect), **oracle** (the driver, the scripted actors, the offline world or the counting),
**design** (a gap a ruling must fill first), or **scenario** (measured by the scenario's design). "Alone it turns
green" is the strict cases a cluster turns green by itself; "Still breaks" is what those cases, or the cases it touches,
still fail on after it. The state is `open`, `in flight` (a builder or a pull request has it) or `done`.

| Cluster | Cause | Class | Rows | Alone it turns green | Still breaks | Size | Depends on | State |
|---|---|---|---|---|---|---|---|---|
| **C1** Decision owners | Decisions carry no `owner` (`src/aew/surface/projection.py:246-299`, `_ticket_actions`; `:444-499`, `_decisions`), so the scripted Lead asks every one (`tests/helpers/vertical/lead.py:350-354`, `:392-393`): the review and verification acceptances reach the operator in every case that compares decisions | product | `E335` | No strict case; it clears the alpha's V1 line | Everything else; `reconcile` stays the operator's (E350); `resolve_stage` becomes the Lead's, whose `resolve` is still refused (C5) | M, 1 PR | none | done (#597) |
| **C2** Plan approval is not a decision | The projection had no plan decision: the proposed plan showed only as blocker `PLAN_NOT_ACCEPTED` with a hint, so the Lead's fallback asked and accepted from its shell (`gap_plan`, `tests/helpers/vertical/lead.py:779-789`). E351 (done, #628) offers it as the operator's `PLAN` decision (Q8, answered), whose `cli_fallback` the Lead still runs from its shell (`decide` and `without_tool`, `lead.py:544-581`) | design, then product | `E163` (E351 done, #628) | None: E351 alone still runs its `cli_fallback` from the shell; with a typed accept (E163, or the surface map's A1a-2) the shell call goes | The other clusters | 2 PRs | E335 (done); Q8 (answered) | open |
| **C3** An empty project offers no action | `_control_part` returns the project's part before any action (`projection.py:122`); `_stage_actions` returns nothing for a non-Ticket (`:341-342`), so the built `ticket_draft` (`src/aew/surface/availability.py:173`) is never offered and the Lead guesses it | design | `E373` | None | The other clusters | M, 1 PR | Q4 | open |
| **C4** `expect_rev` on every call | The revision check is project-wide: every typed tool requires `expect_rev` (`src/aew/surface/contract.py:103`) and the projection supplies it; the driver's hint filler appends it to every hinted command (`tests/helpers/vertical/hints.py:79`), and the Lead's retries strip it (`lead.py:558-563`) | product | `E329` | None | The other clusters | L, 1 PR plus a driver change | none | in flight (#596) |
| **C5** RESOLVE_STAGE for the loop's own stage | `_stage_decisions` (`projection.py`) lists every unfinished stage intent, the steering loop's running one included (E374, after Q9). Its `resolve` arguments no longer lack `choice` and `rationale`: E388 is done (#630), the decision names both as judgment inputs and the typed call with them filled in succeeds. Still breaking: in V2-forced, that continue of the stage whose killed run ended with evidence is refused `HARNESS_LAUNCH_FAILED` at its launch (E400) | product, design | `E374`, `E400`; E388 done (#630) | None | The other clusters | M, 1 to 2 PRs | E335 (done); Q9 | open |
| **C6** Steering-on mechanical calls | The scripted Lead ignores a wait marked `woken` (`projection.py:558`) and calls it (`lead.py:355-364`), with no wake channel from the fake TUI (`lead.py:167-191`); and `loop_acts` takes a self-clearing BLOCKED stop as a decline (`lead.py:379-382`; the loop keeps BLOCKED out of `LEAD_ONLY`, `src/aew/harness/steering_loop.py:162`) | oracle | `E375` | None | The other clusters; with the loop now running the review stage itself, C5's refused `resolve` of the loop's stage also shows at REVIEW_PENDING | S, 1 PR | Q1 and Q10, both answered: `vertical-uat.md` §2 and §3 amended in E375's pull request | done (#627) |
| **C7** The reopen blocks at the tool-consent screen | Only the reopen runs on a controlling terminal (`tests/helpers/vertical/scripted_operator.py:91-97`), so `aew opencode` asks the consent screen before the seat (`src/aew/harness/opencode/lead.py:436`; `src/aew/capability/consent.py:401-405`) and waits out `src/aew/operator.py:28`'s timeout; the scripted operator answers only the resume code (`scripted_operator.py:316-321`). The counted takeover follows and interrupts the implementer | oracle | `E376` | No strict case; it clears the alpha's V2-forced line | The resume code counts under `pin_reentries` on Linux (`scripted_operator.py:320`; `Ledger.console_challenge`), reopen stays a G3 fallback (C12) | S, test-only | E335 for the alpha; Q5, answered: the consent screen is a setup fixture, recorded and never counted | done (#603) |
| **C8** Not told where things stand in words | The scripted Lead reads only `structuredContent` (`lead.py:254`), and `_words` looks for fields `resume` does not carry (`lead.py:710-715`); the readable text is the MCP `content[0].text` (`src/aew/surface/mcp.py:240-247`). Unverified: whether the rendered resume names the Ticket | oracle, probably | `E377` | None | As C7 | Part of C7's PR | C7 | done (#603) |
| **C9** A semantic conflict has no decision | At COMMIT_READY with the queue entry AWAITING_DISPOSITION, `_ticket_actions` emits no decision (`projection.py:246-299`); the only guidance is a requeue hint (`src/aew/engine/resume_ops.py:471-476`); after it `ticket_prepare` is offered and refused, and the Lead's gap key carries the revision (`lead.py:510-525`), so it loops | design, product, oracle | `E378` | None | Counters and fallbacks of the other clusters | M, 1 to 2 PRs | E335; Q2 | open |
| **C10** A compatible rebuild asks again | PUBLISH binds the validated candidate (`projection.py:270-289`); the rebuilt, re-verified candidate raises a new PUBLISH, asked again | design | `E379` | V1 compatible-move (its verdict filters counters and fallbacks) | Nothing in that case | M, 1 PR | Q3; W09's approval binding | open |
| **C11** After the evidence-mismatch refusal, nothing is offered | The gate's refusal for a check that changes a tracked file is BLOCKED with no decision (`projection.py:334-372`); the driver appends `--expect-rev` to a hinted read command too (`hints.py:79`), and that refusal counts | design, oracle | `E380` | None | Counters and fallbacks of the other clusters | M, 1 PR plus a driver line | E335; Q6 | open |
| **C12** V01-01's wire steps are not on the O-01 wire | The oracle derives them not built: the vendored O-01 registry lacks the actions or holds them registry-only, and the carrier admits one origin (`tests/helpers/vertical/oracle.py:196-210`). `path_problems` fails any operator fallback (`tests/acceptance/test_vertical_path.py:217-226`), so no strict V1, V2 or V4 case passes before it | design (the wire track) | `E381`, `E382`, `E383`, `E390`, `E391`, `E392`, `E393`, `E181`, `STG-14` | None, but every strict V1, V2 and V4 green needs it | Nothing it leaves; the alpha excuses it | Many PRs | Q7, answered: after the personal alpha, aligned with STG-14 | open |
| **C13** The credential route a scenario measures | V2's same-shell extra keeps the credential route by design; V4 changes its setting through acquire, export, a hand-edited policy and a separate adopt: there is no `aew policy route` (only `aew settings show`) | scenario; product for V4 | `E164`, `E331` | None | The other clusters | 2 PRs | E327 (merged) for E331 | open |
| **C14** Readiness has no seat row | Neither `src/aew/doctor.py:150-162` nor `Engine.doctor_checks` (`src/aew/engine/api.py:411`) reads the seat, so doctor names neither the dead session nor the fix; `V3_HELD` cites G3-C, which merged (`test_vertical_path.py:753`) | product | `E384` | None: the case still takes the G3 open fallback (C12) | C12's open step | S, 1 PR | E330 (merged) | open |
| **C15** The #213 autopsy cannot see the contained TUI | The TUI writes its childdiag events to the children directory the autopsy names (`tests/helpers/autopsy.py:431-442`), outside the contained Lead's writable roots, the scripts directory and `sync` (`scripted_operator.py:494`) | oracle | `E385` | G3 #213 diagnosis | Nothing in that case | S, test-only | none | done (#602) |
| **C16** The forced kill's own refusal | The call in flight when the test kills the session mid-stage is refused `BROKER_UNREACHABLE` and counted as the Lead's; the refused `stale_hint` that follows belongs to C7's takeover chain | oracle | `E386` | None | C7's chain, C5 | S, one oracle rule | none | open |
| **C17** The offline world is not offline under doctor | Doctor's `provider-relay` rows (`src/aew/doctor.py:160`, `src/aew/harness/doctor_relay.py`) send the world's synthetic login to the real provider host, which answers HTTP 401 in every V3 case. No counter reads it, and no verdict changes | oracle | `E387` | None | Nothing | S, 1 PR | none | open |

C17 is the re-measure's observation with no counter; the other sixteen are its root causes.

## The breach categories

Every breach the ledger or the oracle can report, and the clusters that own it. A category the re-measure did not
breach still has an entry; "none" says no cluster owns a breach of it today.

| Kind | Category | Clusters | At the re-measure |
|---|---|---|---|
| counter | `credentials` | C7, C13 | V2's takeover chain; the credential route of V2's same-shell extra and V4 |
| counter | `env_vars` | C7, C13 | as `credentials` |
| counter | `raw_yaml` | C13 | V4's hand-edited policy |
| counter | `revisions` | C4, C7, C13 | the operator's acquire, takeover and adopt |
| counter | `generations` | none | not breached |
| counter | `invocation_ids` | none | not breached |
| counter | `run_ids` | none | not breached |
| counter | `takeovers` | C7 | every fresh-terminal reopen |
| counter | `seat_operations` | C13 | V2's same-shell extra and V4 |
| counter | `lifecycle_steps` | none | not breached |
| counter | `manifest_adopts` | C13 | V4 |
| counter | `pin_reentries` | C7 | not breached; since C7 (#603) the resume code counts on Linux until REATTACH_LEAD lands (Q5's answer keeps it counted) |
| counter | `windows_console_challenges` | none | not breached on Linux; Windows is outside the enforced gate |
| counter | `help_calls` | C5, C7, C9, C11 | the gap ladder's `work_show` with `explain: true` |
| counter | `guessed_commands` | C3 | `ticket_draft` on an empty project |
| counter | `cli_tool_calls` | none | not breached |
| counter | `shell_aew_calls` | C2, C5, C7, C9, C11 | the plan accept, the stage continue, the reconcile and new attempt, the requeue, the gate reads |
| counter | `ambiguous_next_action` | none | not breached |
| counter | `revision_args` | C4 | every case with a Lead |
| counter | `stale_retries` | C4 | not breached; E329 names it as a test |
| counter | `refusals` | C5, C7, C9, C11, C16 | `resolve`, the stale hint, `ticket_prepare`, the driver's read, the forced kill |
| counter | `mechanical_calls` | C6 | each steering-on case |
| hard limit | `semantic_conflict` | none | held |
| hard limit | `evidence_mismatch` | none | held |
| hard limit | `publish_needs_decision` | none | held |
| hard limit | `containment` | none | held |
| decisions | `V1_DECISIONS` | C1, C2, C5, C7, C10 | the acceptances, `resolve_stage`, `reconcile`, a second publish; C2 keeps the plan's label |
| result | `result_reached` | C9, C11 | V1 semantic-conflict and evidence-mismatch end stuck |
| lead ending | `lead_silent` | C7 | every fresh-terminal reopen |
| lead ending | `lead.lead_error` | none | not seen |
| lead ending | `lead.thread_died` | none | not seen |
| step | `init` | none | landed |
| step | `configure` | none | landed |
| step | `open` | C12 | G3 fallback in every failing case but G3 #213 |
| step | `ask` | C3, C12 | not built (W15); no operator fallback, the Lead guesses instead (C3) |
| step | `plan` | C2, C12 | G3 fallback |
| step | `work` | C12 | not built (W10 and the catalog's C17, CONTINUE_ELIGIBLE_WORK); no operator fallback |
| step | `publish` | C12 | G3 fallback |
| step | `result` | C12 | not built (the D-01 reads); no operator fallback |
| step | `exit` | none | outside AEW |
| step | `reopen` | C7, C12 | G3 fallback, after C7's block |
| step | `preflight` | C14 | landed; V3 stale-lead-session is not diagnosed |
| step | `setting` | C12, C13 | G3 fallback |
| step | `raise` | C12 | G3 fallback |

C12's rows, by step (V-01's actions and reads as the wire sizing of 2026-11-26 names them; each on the wire track,
SYS-46, after the personal alpha and aligned with STG-14, by Q7's answer). Each row says what is owed; its shape is the
designer's session's to decide:
- **open** (3): ATTACH_LEAD, E381; its attachments read is E181's.
- **ask** (4): CREATE_PROPOSED_WORK, E391. E373 is the interim offer on the typed surface.
- **plan** (5): DECIDE_WORK_PROPOSAL, E390. E351 is the projection's decision kind, not the wire action.
- **work** (6): DELEGATE_NEW_WORKER, E392. Its CONTINUE_ELIGIBLE_WORK part reaches the STG-02 carrier's fixture owner today,
  and its production owner goes with E356.
- **publish** (7): APPROVE_INTEGRATION, E383.
- **result** (8): the assurance, resolve and work reads, E181's.
- **reopen** (10): REATTACH_LEAD, E382; attention and attachments are E181's. The oracle already derives waiting and
  continuation state as served, by the STG-02 slice producer, so E393 (those two and the other two reads E181 does not
  list) changes no step's state today: it is owed so that they stay served when E356 retires that producer.
- **setting** (12) and **raise** (13): ADOPT_MANIFEST_EDIT and SET_STEERING_MODE, STG-14's.

## The order

Two tracks. The alpha gate is the personal alpha's scripted gate ([the register](future-work.md), §1;
`tests/helpers/vertical/alpha.py`), which excuses the G3 steps not yet landed. The strict gate is the vertical itself.

**The alpha gate** is the near-term bar (the operator's answer to Q7). The re-measure's ledgers of 2026-11-26 failed it on two lines, V1's decisions and V2-forced's takeover; both are clear since C1 and C7 below.
1. **C15** (E385, done: #602 merged on 2026-11-26). It turns G3 #213 green and does not touch the alpha.
2. **C1** (E335, done: #597). It clears the alpha's V1 line.
3. **C7 + C8** (E376 and E377, done: #603). It clears the V2-forced line. **The alpha is then
   expected to PASS**, which a rerun must confirm. #603's own run (`637bc652`) saw the five fresh-terminal reopens reach E330's seat
   resume, with the implementer's run left running and no V2-forced takeover; the alpha then still failed on V1's line
   (C1), since cleared by #597. Q5's
   answer settles its counting: the consent screen is a setup fixture, and the resume code counts under
   `pin_reentries`.

**The alpha scripted gate passes** (the re-measure of 2026-11-27, `main` at `f848983e`, the merge of #617). Each of
the 8 cases the alpha reads ran once, one per process, on Linux with steering off:
`pytest -p no:xdist --lane vertical`, then the lane's own reporter over their ledgers, `python -m vertical.report`
(`tests/helpers/vertical/report.py`, which calls `alpha.summary`). The verdict is that job summary's; nothing else
records it.
- **Alpha scripted gate: PASS.** Both lines that failed clear: V1's decisions are exactly plan and publish (C1), and
  V2-forced has no takeover (C7). The other alpha lines hold: the hard limits, V1's operator counters at 0, a result
  reached where one is asked, and the four V3 cases.
- **Three excused G3 fallbacks:** open (step 3), plan (step 5) and publish (step 7, held by G3, I4-06 and I4-B7).
  They are excused, not landed.
- **Alpha receipt: NOT RECORDED.** It is a real-model run the operator starts, not part of the scripted gate.
- **Each case ran once,** so the pass does not show stability.

The strict gate still fails 4 of the 8 cases the alpha reads; its other ten were not re-run, since the alpha does not
read them: V1 compatible-move, the V2 exit/kill and steering-on cases, V2 same-shell, V3 stale-lead-session, V4 and
G3 #213. Each failure of the 8, as the measure's report reads it, and the clusters it maps to:

| Case | Strict | Fails on | Clusters |
|---|---|---|---|
| V1 steering-off | fail | `guessed_commands` 1 (`ticket_draft` on an empty project); `shell_aew_calls` 1 (`aew plan accept`); `revision_args` 7; the open, plan and publish fallbacks | C3; C2 (E163; E351's `cli_fallback` still runs from the shell); C4; C12 |
| V2-forced-mid-stage | fail | `pin_reentries` 1 (the seat resume); `help_calls` 2; `guessed_commands` 1; `shell_aew_calls` 3 (the plan accept, `stage continue`, `work transition --to RUNNING`); `revision_args` 9; `refusals` 2 (the stage's `resolve`, refused for want of a choice and a rationale, and `stage continue`); the open, plan, reopen and publish fallbacks | `pin_reentries` by Q5 until REATTACH_LEAD (C12, E382); C5 (E374, E388); C3; C2; C4; C12. No `BROKER_UNREACHABLE` refusal this run: C16 not observed |
| V1 evidence-mismatch | fail | `help_calls` 1; `guessed_commands` 1; `shell_aew_calls` 3 (the plan accept, `gate show` twice); `revision_args` 4; `refusals` 1 (the driver's `gate show --expect-rev`); the open and plan fallbacks; it ends at RUNNING with `ticket_request_review` BLOCKED, and no result | C11 (E380, with `hints.py`'s `--expect-rev`); C3; C2; C4; C12 |
| V1 semantic-conflict | fail | `help_calls` 47; `shell_aew_calls` 47 (46 of them `aew integrate requeue`); `refusals` 47 (`ticket_prepare` in a loop, and one `integration_publish`); `revision_args` 99; `guessed_commands` 1; the open, plan and publish fallbacks; no result | C9 (E378), the loop; C2; C3; C4; C12 |
| V3 check-changes-snapshot, model-id-provider-prefix, model-not-listed, provider-env-unset | pass | - | - |

With the alpha passed, the wire track (C12) now follows, by the operator's answer to Q7 above ("this seems after alpha
when we align the wires").

**The strict gate.** The wire track and the rest. In the re-measure's proposed order, each after the alpha track:
1. **C10** (E379), after Q3: turns V1 compatible-move green.
2. **C2** (E351, done; then E163 or A1a-2).
3. **C3** (E373), after Q4.
4. **C4** (E329, #596), with its driver change.
5. **C5** (E374, after Q9; E388, the `resolve` decisions' arguments, filed by #597, done by #630; E400, the continue refused at its launch in V2-forced, filed by #630).
6. **C9** and **C11** (E378, E380), after Q2 and Q6.
7. **C6** (E375, done: #627), an oracle fix with its `vertical-uat.md` §2 and §3 amendments (Q1 and Q10 answered):
   `mechanical_calls` 0 in each steering-on case.
8. **C14** (E384), with C16 (E386) and C17 (E387) as small fixes beside it.
9. **C13** (E164, E331).
10. **C12**, the wire track (E381 to E383, E390 to E393, E181, STG-14): after the personal alpha, aligned with STG-14 (Q7).

After 1 to 9, V1's counters and decisions are expected clear, and the V1, V2 and V4 cases fail only on C12's
fallbacks (and V2 on the resume code under `pin_reentries`, Q5); V1 semantic-conflict and evidence-mismatch also need
C9 and C11. Before the wire track the most the strict gate can pass is the four V3 cases besides stale-lead-session,
G3 #213 and V1 compatible-move.

## Questions

The operator's four, as they were put, each with the operator's answer of 2026-11-26. Of the designer's six, Q8 was
answered by the operator on 2026-11-26 (after the operator's); Q2 to Q4, Q6 and Q9 are open, and are owned by [what the operator and
designer owe](decisions-due.md), each on the row it holds: Q2 on E378, Q3 on E379, Q4 on E373, Q6 on E380 and Q9 on
E374 (`python tools/register.py show <row>`). The wire track's actions with no design, ATTACH_LEAD, REATTACH_LEAD and APPROVE_INTEGRATION
(C12, after Q7), are owed by the designer on E381's item there, which blocks E382 and E383.

- **Q1 (operator; vertical-uat.md §2):** "With steering on, when the projection marks the live run's wait `woken: true`, may the scripted Lead end its turn and wait for AEW's wake instead of calling `harness_wait`, so that the wait is not counted under `mechanical_calls`?"
  - **Answered yes** (operator, 2026-11-26): "For q1 yes. That honestly just seems like a bug and sint how aew works now."
    With steering on, the scripted Lead ends its turn on a wait marked `woken` instead of calling `harness_wait`. That
    part of C6 (E375) is an oracle fix, and the operator approves the matching amendment of `vertical-uat.md` §2, which
    E375's pull request makes. The answer covers the wait Q1 asked about and nothing else: E375's other part is Q10's.
- **Q10 (operator; vertical-uat.md §3, "Steering on"), raised at this page's review:** with steering on, does a
  BLOCKED loop stop count as the loop having declined only once its blocker is still present after the run's end, and
  not at once, as the scripted Lead counts it today? It decides whether the Lead's push after a self-clearing stop is
  the spec's counted exception or a mechanical call.
  - **As it was put to the operator:** item 5 of the questions the Lead put in its session on 2026-11-26, verbatim:

    > **5. Q10, what a "BLOCKED" stop counts as in the vertical test**
    >
    > With steering on, a background steering loop is supposed to do the routine mechanical steps, so the Lead doesn't
    > have to. The vertical test counts each time the Lead does one of those steps itself as a "mechanical call", and
    > too many of them fail the test. The one allowed exception: if the loop declined to act, the Lead stepping in is
    > fine.
    >
    > The question is about one kind of stop. Sometimes the loop stops with BLOCKED, for example because a run is
    > still finishing, and the blocker then clears on its own a moment later. Today the scripted Lead treats every
    > BLOCKED stop as the loop declining, so it steps in and that is not counted.
    >
    > The choice:
    > - **(a) Count a BLOCKED stop as declined at once (today's behaviour).** It is lenient: the Lead may do work the
    >   loop would have done seconds later, and the test won't notice.
    > - **(b) Count it as declined only if the blocker is still there after the run ends.** It is stricter: a Lead
    >   that jumps in on a self-clearing stop is doing the loop's job, and that counts against it.
    >
    > I recommend (b). It keeps the test honest about whether steering actually removes routine work from the Lead,
    > which is the point of steering. The cost is that the scripted Lead must wait out self-clearing stops before it
    > acts, which is a small change to the test helper (E375).
  - **Answered** (operator, 2026-11-26). To an earlier, shorter version of the item the operator answered "5. Tell me
    more about this."; to the version above: "5. B yes its meant to make sure the lead doesnt do menial labor." A
    BLOCKED stop counts as a decline only when its blocker is still present after the run ends; the Lead's push after
    a self-clearing stop is a mechanical call and is counted. E375's pull request amends `vertical-uat.md` §3 with it.
- **Q5 (operator):** "Is AEW's tool-consent screen at a reopen a setup fixture of the offline world (recorded, never counted), or an operator step the vertical counts? And until REATTACH_LEAD lands, is the seat-resume confirmation code meant to count under `pin_reentries` on Linux, as `Ledger.console_challenge` counts it today?"
  - **Answered** (operator, 2026-11-26): a setup fixture, recorded but not counted. "The vertical was meant to fix ux
    issues. Aew saying a critical item is missing isnt a ux failure its common sense." The seat-resume code still
    counts under `pin_reentries`. C7 (E376) is #603.
- **Q7 (operator):** "No strict V1, V2 or V4 case can pass until ATTACH_LEAD, DECIDE_WORK_PROPOSAL, APPROVE_INTEGRATION, REATTACH_LEAD, SET_STEERING_MODE and ADOPT_MANIFEST_EDIT reach the O-01 wire. ATTACH_LEAD and REATTACH_LEAD 'stay proposed, with no row', and APPROVE_INTEGRATION (I4-06, I4-B7) has none. Which rows and order carry them, or is the alpha's G3 excuse the bar until then?"
  - **Answered** (operator, 2026-11-26): "this seems after alpha when we align the wires." The alpha, with its G3-held
    steps excused, is the near-term bar; the wire-track rows (C12's) come after it, aligned with STG-14.

Q7 was put before this page filed E381 to E383 and E390 to E393.

The designer's Q8, answered by the operator:

- **Q8 (put to the designer, answered by the operator):** "What is the plan decision kind's name? The vertical records a
  decision under its kind lowercased, so anything but `PLAN` needs the oracle to map it to `plan`."
  - **Answered `PLAN`** (operator, 2026-11-26): "6 yeah that seems like jts less a choice and more do you like the
    name? Which sounds good to me". E351 builds it (its note).
