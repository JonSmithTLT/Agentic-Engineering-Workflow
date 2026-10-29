# AEW future work register

**What this is:** the one place that lists AEW's deferred work, so that nothing designed or decided is forgotten. Each entry points to its source and names the gate it must pass before, or the milestone it belongs to.

**Authority:** none. This is an index, like `docs/design/invariant-index.md` (`AEW-INV-TRACE-001`). The governing texts are the design documents, contracts and ADRs it points to. When one of them changes, update this register in the same change. Never reinterpret a design from its entry here.

**Keeping it current:** add an entry whenever work is deferred, whether a design is accepted, a review defers a finding, or a dogfood finding is left open. Give it a target (below). When its work is accepted, or another entry absorbs it, move it to §9 *Closed* with the date and the commit, PR or document that closed it. Never drop an entry silently. When an entry waits for a decision or a design, give it an item in [`decisions-due.yaml`](decisions-due.yaml) (what is owed, by whom, by which gate or milestone, and what it blocks); the rendered [`decisions-due.md`](decisions-due.md) is the list of what is due. **Edit the data, not this page:** this file is rendered from `future-work.yaml` by `tools/register.py render`; `tests/unit/test_register.py` fails when the two differ (E30). Append a closed row anywhere in §9: `render` sorts §9 into id order, so two changes that close different entries land in different places and merge without conflict. **Add a note, never edit a Notes cell:** what a change has to say about an existing row (a slice built, a decision, a review's outcome, a pointer to new evidence) goes in a file of its own, `notes.d/<row id>/<YYYY-MM-DD>-<branch slug>.md`, which `python tools/register.py note <id>` creates for you to write; branches whose slugs differ never write the same file, so notes never conflict; every row with an id ends with a pointer to its directory, and `python tools/register.py show <id>` prints the row with its notes oldest first ([`notes.d/README.md`](notes.d/README.md)). Edit a row's cells only when what they state changes (its work, its source, its target, its closing), and never append to them. The notes already in the cells stay there. **The Now list (§1) is the build order, and the Lead keeps it current.** A new row names its milestone (Contained, V-01 or Internal alpha) or After the trace in its target. A hold group leaves the hold only when STG-12's S12-4 trace is final and S12-5's flags are decided: the designer matches each member to the requirements it would serve; a member that serves one becomes a row again, sourced to those requirement ids and placed by the operator into a milestone, and a member that serves none is dropped, with the operator's OK, one batch per group; until then nothing in a group is built, unless the operator asks for it (the development hold's exemption).

**At each milestone start** (operator, 2026-10-01): the milestone's ambiguity report goes through this register. It covers every entry whose *When* names that milestone or a gate before it, and any other open entry that fits the milestone's scope. It marks each one as **in scope**, **deferred** (with the reason) or **closed** (naming what closed it). Items with no fixed milestone may be pulled in where they fit. The operator and designer approve that scope at plan review, with the rest of the plan.

**Targets.** Every open entry's *When* (or *Target and notes*) starts with one target, in bold:

| Target | Meaning |
|---|---|
| **Gate: …** | Must be done before the named point (§1) |
| **Now** | In the build queue, whose order §1 gives and the Lead keeps |
| **Contained**, **V-01**, **Internal alpha** | Belongs to that milestone (§1) |
| **After the trace** | Held until STG-12's requirements trace is final: a hold group (`HOLD-NN`, one per adopted position) or a row waiting on the trace |
| **Designer** | Waits for a decision (§4); nothing is built before it |
| **Evaluation** | Measurement with no product code, run alongside milestones |
| **On measured need** | Only if evidence shows the cost or pain |
| **Unscheduled** | No milestone yet; the next triage it fits may pull it in |
| **Stage** | A build stage of the architecture map (`STG-NN`), built from the designer's hand-offs in the map's order; each slice adds a note on the stage's row |

The targets were reset by the register rebaseline (operator, 2026-10-24).

*History: each row carries its own dates; the file's history is `git log -- docs/implementation/future-work.yaml`. The change log kept in this line until 2026-10-05 is archived as `docs/archive/register-changelog-to-2026-10-05.md`. Nothing in this preamble changes per entry. After every sync with main, run `python tools/register.py render`, conflict or not: a clean merge can still leave §9 unsorted and the markdown stale, which `check` (and CI) refuse. When a merge conflicts, resolve `future-work.yaml` only, then render: the markdown is derived and is never merged by hand.*

## 1. Now, the milestones and the gates (in order)

**Now, in order.** The build queue, each item on the row that carries it. **The Lead keeps it current:** this register owns the build order, and the architecture map's build order points here for it. The design queue stays in the map. `python tools/register.py check` holds the list to the rows: every row it names is open and targeted **Now** or **Stage**, and every row targeted **Now** is in it. A stage is named once it is queued. A change that closes or retargets a row named here edits this list in the same change.

| # | Row | Item |
|---|---|---|
| 1 | STG-12 | S12-2's PRs 4 to 10, on two builders, to the pack cut (the list is frozen) (all merged: PR 10 as #268, `a4d81bae`) |
| 2 | STG-05 | the owner-only store (#256) (merged, `e78c6386`) |
| 3 | STG-05 | CS-3b, the network namespace (#257) (merged, `d796a342`) |
| 4 | STG-15 | CAP-1: AEW brings ripgrep through the capability register (PR 1 merged as #272, `af951c92`; PR 2 starts from CS-4's merge) |
| 5 | E35 | H-1: OpenCode 2.1.4 through the live lane, with its token semantics |
| 6 | STG-05, STG-03 | CS-4, the Lead contained, with the G3 service beside it (G3-A merged as #269, `24d4eec0`; G3-B, the confirmer, merged as #282, `61310fb3`; G3-D, the CLI client, merged as #286, `21ea8674`; G3-C after CS-4's merge) |
| 7 | E35 | H-2 (`aew harness qualify` and its records), then H-3 (the feed check, the automatic switch, rollback, bundle import) |
| 8 | STG-13 | V-01's oracle rebuilt |
| 9 | STG-14 | I-6, the resource, model and host policy (A-39): the first of V-01's wire increments. Moving it ahead is the operator's call. Its protected rows stay held until G3 is established, which is no sooner than CS-4's merge |

**Contention for a slot:** STG-05's slices first (CAP-1 counts as CS-3b's follow-up), then H-1 to H-3, then G3, then the oracle's rebuild, as the map says today, then I-6 (STG-14, item 9). On 2026-10-25 the operator gave the G3 service a builder slot of its own (in chat), so it is building ahead of H-1, beside CS-4 as the operator's decision of 2026-10-23 placed it (design workspace). **After I-6,** V-01's next build items are the provider relay's meter (E97), then R-01's qualification of the paid class (E98), which judges that meter (the Lead's order, as A-42's adoption leaves it). They join this list when they are queued.

**The milestones and gates, in order.** They replace the gates this section held before the rebaseline, and the M4, M5 and M6 targets (register rebaseline, operator, 2026-10-24).

<!-- columns: Milestone or gate | Done when | Source -->

### **Contained and reconciled**

**Done when:** **Every agent runs contained:** CS-3b and CS-4 merged, with their live lanes on Rocky 8 (STG-05), and the G3 service installed (STG-03, A-37). **The rest:** the owner-only store merged, AEW's base tools shipped (STG-15, CAP-1 and the bundle), and harness currency in place (E35, H-1 to H-3). **Reconciled:** the as-built reference is complete and the requirements trace is final, with its flags decided (STG-12: S12-2, S12-4, S12-5)

**Source:** A-33, A-37, A-35; the operator's decisions of 2026-10-24 (AEW brings its tools; OpenCode version currency); the register rebaseline (design workspace, `b598fdc`)

### **V-01, the first vertical slice: before feature work resumes, and before any release**

**Done when:** **The operator's outcome:** authenticate once, say "fix this", and get the published result. It is measured by V-01's rebuilt oracle (STG-13) passing on Linux; Windows is outside it, as today. **The wire track** builds the increments the slice needs: I-6, then I-7; RX-01, K-01 and P-01 selected before I-7 (made on 2026-10-25, among its five choices: knowledge in V-01 is history and source lookup only, K-01's H profile; a research claim reads `NOT_ESTABLISHED` until its owner qualifies it; V-01 shows the maps to agents only, with no site map view); O-02; U-01. **Research, PoCs and one mission:** research's minimum slice (an inquiry as WIS work with no Ticket, an outcome by answer, and links between a Ticket and an inquiry in both directions, in CNI's link vocabulary); PoCs as linked Tickets (contained scratch, while a PoC in the real project is an engineering Ticket linked to the inquiry); one bounded unattended mission (hours, an I-6 spend cap metered at CS-3b's provider relay, a preflight, held questions and a report). The mission counts only where the relay meters every paid route a mission's run can reach and R-01 qualifies the class, so its cap is hard there (A-42, option (a)): the relay's meter (E97) and the qualification (E98) are V-01's build items

**Source:** the operator's verdict of 2026-10-11; the vertical-UAT ruling of 2026-10-23; the operator's decisions of 2026-10-24 (V-01's first row; the oracle rebuild's exemption; the first selections for RX-01, P-01 and K-01, with research, linked PoCs and one bounded mission in V-01, design workspace `f9f0c1a`); the register rebaseline (design workspace, `b598fdc`); A-40, WIS's research statements (adopted by the operator on 2026-10-25, design workspace `44156d0`), from which research's minimum slice is briefed; the operator's selection before I-7 of 2026-10-25 (design workspace `a8a5efc`); A-41, CNI's link vocabulary, and A-42, the bounded unattended mission with option (a) (both adopted by the operator on 2026-10-25, design workspace `b2ade18`), from which I-7 and the mission are briefed

### **Internal alpha**

**Done when:** **The trace's removals and FIX rows are done** (S12-6). **The hold groups** the operator keeps for alpha are re-sourced and built. **AEW is packaged for the operator's own trial:** an install the operator can run on their own machine and on a managed Linux host. The trial itself follows the milestone and is the operator's: first SPT's backlog, then, if that goes well, the issues it turns up, then use on that host, with the feedback brought back

**Source:** A-35; the register rebaseline (design workspace, `b598fdc`); the operator's decision of 2026-10-25 on the triage's ST-46 (design workspace `0d6292f`)

### **Before a provider that requires a client certificate is used**

**Done when:** The AEW Provider Gateway (F18.8 with F28) holds the provider's mutual-TLS client certificate and key and presents them: the pinned harness (OpenCode 2.0.18) speaks chat completions but cannot present a client certificate (harness probe, 2026-10-11), and the credential never enters a sandbox or a harness's configuration. Applies only to such providers; for others Q5's hardening milestone and its order are unchanged (designer, 2026-10-11; Q5 closed in the register rebaseline). The forced request fields have been qualified against the provider (operator, live; AIR-85). Its work, F18.8, is now held in HOLD-20 (register rebaseline).

**Source:** [decision record](../design/decisions-2026-10-11-architecture-integration.md) §6.4, §6.5, §6.8 (ledger AIR-81, AIR-82, AIR-85)

### **Met**

**Done when:** F2's containment regression gate and E13's process ownership (M4-B, 2026-10-03)

**Source:** `docs/design/proposals/execution-workspace-and-isolation-design-v0.1.md` §6.6 and §12; `m3-companion-review-triage.md` P1 and B2; E13

## 2. Designed, not implemented

<!-- columns: # | Work | Source (governing) | Belongs to or gated by | Notes -->

### F19

**Work:** One evaluation program: Q7 (the next dogfood), F14 phases 1–4, the F17 corpus and Class 0 sampling share one fixture format, runner, run-record schema, hidden-evaluator mechanism, model and profile configuration, and metrics collector; each experiment is preregistered separately, and one run stays one run however many metrics it informs

**Source (governing):** Designer, 2026-10-01 ([`plan-assurance-and-classification-decisions-2026-10-01.md`](../design/plan-assurance-and-classification-decisions-2026-10-01.md) §3.6)

**Belongs to or gated by:** **Evaluation.** Hidden material lives in the private repository (`aew-private/eval/`); execution profiles and budget are pinned at preregistration (§3.4). Q7's scratch rule (F2) applies to every F19 run

**Notes:** Builds on the M3 dogfood harness (`eval/m3/dogfood/`). Q11 adds the provider research's evaluation plan to it. Architecture review 2026-10-04 (accepted 2026-10-05, Q13): F19 becomes a code component (D-AR1); deterministic state/context reconstruction for fixtures; model-diverse review as a probe; the knowledge corpus K01 to K28 (ledger KRB-14). The component design is [evaluation component v0.2](../design/evaluation-component-design-v0.2.md) (adopted by the operator and the designer 2026-10-05; ledger EVC; the review's [T2 plan](../archive/reviews/architecture-review-2026-10-04/t2-evaluation-component-plan.md) it grew from is archived): `eval/aew_eval/` public, hidden material private, every paid attempt registered before launch, immutable runs with separate analyses. Its first slice (schemas, preregistration and the attempt ledger, proved against the M3 corpus) comes before M4-H's preregistration. ARV-05 (operator, 2026-10-05): the probes the architecture review could not run (gateway features such as tool search, structured output and caching; recall performance on the target hardware) are evaluation items here. **Slice 1 built (2026-10-05):** `eval/aew_eval/` with the four schemas (`aew/eval-case/v1`, `aew/eval-prereg/v1`, `aew/eval-attempt/v1`, `aew/eval-run/v1`), `prereg.py` (freeze: consistency, the seeded schedule, the canonical hash; refusal of a run whose material inputs changed), the append-only attempt ledger (registered and synced before any provider action, a result finalized once, a killed runner visible as `runner_lost`, retries only under the frozen policy; each transaction under a per-experiment lock, every byte written, a torn tail repaired, every pinned field of a result checked) and the deterministic mapping of all 68 M3 records (`compat.py`), proved in `tests/unit/test_eval_instrument.py`. **Slice 2 built (2026-10-06):** `fixture.py` (a case manifest's fixture trees read once into a snapshot that is both hashed and built from, with LF line ends; paths that would build differently on Windows and Linux, `.git` components, links and junctions, and trees outside or nested in each other refused; git run with a scrubbed environment and no configuration, hooks or signing), `arms.py` (the `scripted` arm: exact edits, no model, its configuration checked against the case before registering) and `runner.py` (one preregistered cell: a changed input, an arm kind not built yet, a bad configuration or a scratch root inside a git work tree is refused before anything is registered; the attempt is registered before the arm runs; an arm failure is a counted `invalid_measurement`; after the arm the work tree is read as plain files, never through git, for the changed paths and an export outside it for the optional scorer; the result is finalized once, with whether the AEW checkout was touched), proved in `tests/unit/test_eval_runner.py`. **Slice 3 built (2026-10-06), the hidden-evaluator channel (design §5, §8 step 3):** `hidden.py` takes the private root from `AEW_EVAL_HIDDEN_ROOT` and removes it from the environment before any arm runs; an oracle (`cases/<id>/oracle/checks.py`) is hashed like a fixture and refused before registration when it is missing, no longer matches its preregistered commitment, or belongs to a held-out case that `exposure.yaml` records as exposed; it is read once, and those bytes score: after the arm has returned, sent to an isolated scoring process (`score_child.py`, `python -I -B`) on its standard input, never to the disk, in an AEW process tree. The model's code never runs in that process: the checks reach the model's program only through `run`, which gives each program its own process tree (a job object on Windows; on Linux a bubblewrap sandbox in its own pid namespace with the hidden root's whole private repository (for a worktree or submodule also its object store and every checkout), the ledger and the user's secrets masked; another copy of the corpus elsewhere on the host is not masked, so it lives in one place on a scoring host) and an allow-listed environment. The runner accepts only a clean exit with exactly one well-formed result, computes `passed` itself, and records no result or a timeout as a failed score, never a retryable `invalid_measurement`. Linux without bubblewrap refuses oracle-scored cells; Windows refuses held-out cases, and every other score there records `contained: false` (a same-user program could search the disk, so it is not tamper-evident). Proved in `tests/unit/test_eval_hidden.py`. **Held-out corpus isolation (designer, 2026-10-06, [decision record](../design/decisions-2026-10-06-f19-held-out-corpus-isolation.md)):** an M4-H experiment-protocol requirement, not an AEW architecture surface. Held-out material not yet assigned to a trial is never readable by a model-controlled process in either arm; for M4-H the private corpus stays off the arm hosts entirely, and the evaluator side releases only the selected task's material at the trial's start. Masking, F23 and F28 are not prerequisites. The runner as built scores and runs the arm on one host, so the next slice, with the `aew` and `raw` arms, splits it: the evaluator side keeps the corpus, ledger and oracle and releases one task; a corpus-free arm host runs the arm (designer's arm-host rule, record §3: no copy, no parent directory, no mounted, shared or synced path and no obvious host-integration path to unreleased material; a WSL instance on a Windows host holding the corpus is ineligible by default; a preflight that cannot establish isolation releases nothing) and returns the final tree for scoring, with the facts only it can observe (whether the AEW checkout was touched, its environment), so the run record describes the arm host, not the evaluator. Next: the `aew` and `raw` arms by generalizing `dogfood.py` (the M3 driver still runs them). **Q7 adopted ([v0.3.1](../design/q7-m4h-value-gate-experiment-v0.3.1.md), operator, 2026-10-07; ledger VGX):** M4-H's experiment design is frozen. **Prerequisite before M4-H executes:** the evaluator/arm-host split and the held-out task-release runner (decision record of 2026-10-06 on held-out corpus isolation), the cold-start attestation (§5) and the preregistration values of §14. **Agent-effectiveness adoption (2026-10-09, [agent-effectiveness adoption](../design/decisions-2026-10-09-agent-effectiveness-adoption.md), ledger AEA; [agent-effectiveness synthesis](../research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md), ledger AES):** raised: an evaluator-side reader of a completed run's retained harness session database, approved by the operator with bounds (Revision C): the hidden evaluator opens it read-only after the run, extracts only preregistered measurement fields, computes named, versioned metric functions and records the result; the raw database is kept only for the operator-configured retention window, which has no default and is enforced: past the expiry the reader refuses to open it and the evaluator's retention step purges it and records the purge, both tested; AEW's runtime never consumes it, it is never a Knowledge or supervision source, and arbitrary conversational content is not ingested. Research profiles are capability classes (frontier, mid, lower-bound), each run recording provider, model, harness, effective profile and qualification state at preregistration; results per class, raw against assisted, never a cross-class leaderboard, with cost per correctly accepted outcome across classes. The lower-bound qualification lane may run before M4-H on an independent non-held-out fixture (preferably a sanitized public or synthetic repository of several hundred files); its runs are marked `purpose: qualification`, are qualification and instrumentation evidence only, never M4-H or treatment-effect claims, and Q7's sealed tasks stay unexposed. After the gate: `r8-pack-arms`, `r9-intent-surface`, `r2b-coherence`, `e1-completeness-nudge` and `e2-delta-first`; their aggressive modes become defaults only after measurement. Nothing here changes M4-H's frozen treatment (Revision B). Delta items D2, D3 and D14. **F9-A1 adoption (operator and designer, 2026-10-09; [decision record](../design/decisions-2026-10-09-f9-a1-adoption.md), ledger LWA):** F9 messaging stays off in M4-H's frozen treatment, which is not amended; messaging is evaluated separately here using the F9 A/B/C/D supervision arms (F9-A1 §16 and §20: A no proactive supervision, B messaging available only, C AEW-recommended adaptive supervision, D mandatory periodic supervision), with F9-A built behind a switch with disabled-state identity tests. **F21's Arm B prototype and M4-H (2026-10-09):** the sealed M4-H configuration has `recall.raw_history_search: "off"`, so `aew history search` is absent from both arms whether or not the prototype has merged; the M4-H cold-start attestation must show `recall.raw_history_search: "off"` and no `local/recall/` directory, and a treatment freeze names its commit, never `main`'s head implicitly. When F21's A/B evaluation runs (after the knowledge adoption record's §8 readiness package), each run starts from the history snapshot its preregistration names, and the HOC arm-host preflight applies to that snapshot (the search index is project-scoped: a search reaches only the project it runs in). **D3's lane prepared (2026-10-10, PR #153), the run is the operator's:** the `raw` arm (`raw.py`: OpenCode's own agent through the M3 headless session, the case's new `task` its only message; the harness binary, the model and effort, and the profile pinned in its frozen configuration; on Linux contained by bubblewrap, its layout self-tested and its hidden paths probed before OpenCode starts; its session database kept under the preregistered retention window and structured field allowlist; a run on another model or harness, a provider value in retained state (deleted at once), a provider error instead of a model step or ending the turn, or a failure after the session started is counted and not valid, its cost charged at the cap when unknown); the runner refuses a held-out case for any model arm until the evaluator/arm-host split exists, and defers scoring so that the arm host holds no oracle while a model runs (`score_run` scores the hashed export afterwards, once); `retention.py` enforces the window (a database past it is refused and purged, the purge recorded); the preregistration's `purpose`; the `aew/eval-profile/v1` record (`profiles.py`). `eval/experiments/lower-bound-qualification/` holds the preregistration, the profiles, three seeded cases on Python-Markdown 3.11.0 (BSD-3-Clause, 480 files) with their oracles validated against the real fixture, the rubric and the driver; the runs happen on the Rocky 8 VM. Three experiments share the cases, oracles, rubric and budget rules, each with its own preregistration, frozen record and lane directory: `lbq-v1-deepseek-v4-flash` (its profile became unavailable on OpenCode Zen on 2026-10-10), `lbq-v1-deepseek-v4-1-flash` (the replacement primary the operator chose) and `lbq-v1-gpt-5-nano` (the next-cheaper profile, run after it for coverage and a second model family). `lbq-v1-deepseek-v4-1-flash` ran on 2026-10-10: its floor passed, but every ceiling attempt was refused before any model ran by a containment defect in the raw arm (a lane under the home directory masked the runs beside each run inside the runs directory's own tmpfs; fixed, and a run refused before launch is now charged nothing and stops the ceiling at once). Under the amendment policy the operator chose a new experiment, `lbq-v2-deepseek-v4-1-flash` (the same preregistration, a new id), and kept v1's lane as the record. **Run 2026-10-10 (at ed98424; frozen records and results committed in the lane):** `lbq-v1-gpt-5-nano` passed the floor and showed behaviour 5 (requirement loss on longer tasks), so `opencode/gpt-5-nano#high` is qualified as the lower bound ($0.066 in all); `lbq-v2-deepseek-v4-1-flash` passed the floor and solved all 6 ceiling runs with no tree-observable behaviour ($0.22), so its ceiling waits for the session-observable half. The session-observable metrics wait for D2's reader; the aew arm and the evaluator/arm-host split are still next. **F9-A messaging arms (F9-A plan amendment 2, §11):** messaging may be on in an evaluation arm (arm B, F9-D) only after U1 S11 and F9-A's MS5b have merged: before MS5b, every `aew harness send` is refused while messaging is on (HS1, register E55), so such an arm would silently lose the Lead's nudge. **Designer decisions of 2026-10-10, evening ([decision record](../design/decisions-2026-10-10-m4h-instrument-and-claude-code.md), ledger MIC):** D1, F25's G1 is approved, so M4-H's counted cost is F25's settled figure under its boundary, which F19 hashes into the run record (MIC-01). D2 (F19's G1), each counted AEW-arm run gets its own operator ceremony (the mode raise and the publication grant) through the constrained evaluator relay, an acceptable human-intent channel under M4-E's `guarantee: dev`, for v1; a campaign-scoped grant (new authority) is revisited only if the ceremony proves impractical in calibration (MIC-02). The relay's conditions are binding: it shows the bound action verbatim, strips terminal control sequences, and cannot answer a challenge itself, which a static test proves (MIC-03). D3 (F19's G2), the request and attention disposition table is exhaustive and sealed before calibration: every AEW request or attention kind, drafted by the lead developer from M4-E E7's event vocabulary, is sorted into pre-granted, denied or an operator-only halt; a confirmation is never pre-granted; a high anomaly that needs a disposition is an operator-only halt; the fixed texts go to the Lead's session as a user message; the designer confirms the table before the seal (MIC-04 to MIC-06). **M4-H's analysis bundle built (F19 plan v5, slice S11):** `eval/aew_eval/analysis.py` implements Q7 §13's fixed-cell Jeffreys rule (10^6 joint draws from numpy's `PCG64` under the sealed seed; the verdicts, with no selectable pooled or weighted estimator), its exact cross-check (a regularized incomplete beta by Lentz's continued fraction, posteriors discretized by CDF differences so all-pass and all-fail cells keep their mass, convolved in pure Python), the operating-characteristic simulation as a tool (`python -m aew_eval.analysis simulate`), the §6.3 cost axis (ratio of totals, undefined at zero successes, cell-stratified bootstrap), §13.7's safety axis, §12's U3 flag and the versioned §6.3 secondary outcomes; the `aew/m4h-analysis-plan/v1`, `aew/eval-analysis/v1` and `aew/m4h-simulation/v1` schemas, and a minimal `aew/m4h-reconciliation/v1` (per run, bound to the analysed runs and to the plan's sealed spend layer; `COST_UNRESOLVED` comes only from it, the sealed mismatch fraction and, under layer (c), the sealed `usage_estimated` share; S15 produces it and extends it with both figures per run, then the analysis recomputes each run's mismatch from them and refuses a disagreeing flag, and `campaign verify` checks the analysis's `reconciliation_sha256`; S18 produces the `usage_estimated` flag; the deciding rates are over the primary runs, F4's reported beside them); a draft plan and frozen test vectors, exact and seeded, in `eval/experiments/m4h-dogfood/`. numpy is the evaluator-only `eval` extra (pinned), which no other module imports. Proved in `tests/unit/test_eval_analysis.py`. **Cross-feature integration v0.5 ([cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §18; ledger CFI-106):** field-log #20, PR lifetime, is an evaluator / process metric candidate (F41.14). **The M4-H instrument (the F19 M4-H instrument plan v5, slices S0 to S18; note layout from 2026-10-10):** each slice's progress is its own paragraph of [implementation-status.md](implementation-status.md)'s section "The evaluation instrument (register F19)", so slices landing in parallel never edit this cell; this row keeps the decisions and gates. **S4 built (2026-10-10):** the evaluator/arm-host split's core ([ADR-0018](adr/0018-evaluator-arm-host-split.md), ledger EAS): a cell released to an arm host through a transport, registered before its bundle leaves, collected under hostile receive and finalized for deferred scoring on the evaluator, with a hash-chained release ledger and the run manifest `aew/m4h-run-manifest/v1`; scripted arm only until the run supervisor (S8), and no model arm or held-out case released until S5's preflight can establish isolation. **For F25's live usage (P1, sst/opencode tag v2.0.18):** session generation (called by `POST /api/session/{id}/generate`, the first-party `/btw`, the plugin host and the `warming` plugin) and the stateless generation (`POST /api/experimental/generate`, the plugin host) make model calls that record no usage, so the live figure cannot see them. A counted server sets no `warming` (L3's preflight refuses one), loads no plugin beyond OpenCode's own and has no TUI or app attached that could send `/btw`; otherwise the provider reconciliation (Q7 v0.3.1 §9.1) is the only backstop for that usage. **S8a built (2026-10-10):** the run supervisor's core; its status is in implementation-status.md's F19 section.

*Later notes: `notes.d/F19/`, oldest first (`python tools/register.py show F19`).*

### STG-03

**Work:** The G3 service build, beside CS-4, briefed from A-37 (G3 revision 7.1)

**Source (governing):** A-37 (G3 revision 7.1); the register rebaseline (design workspace, `b598fdc`)

**Belongs to or gated by:** **Stage.** STG-03; built beside STG-05's CS-4

**Notes:** One row per build stage, and each slice notes on it (designer, D-CS1-12, 2026-10-23).

*Later notes: `notes.d/STG-03/`, oldest first (`python tools/register.py show STG-03`).*

### STG-05

**Work:** Agent containment, built in slices (CS-1 to CS-4; CS-5 was cut with the WIS issuer, operator, 2026-10-24, design workspace `f206099`): the store's path and the control lock kept out of agents' reach, the store's modes, the masks (`/run`, sockets, display credentials, the terminal), the network namespace (CS-3, F28's network containment), and the launch self-test's rows, failing closed

**Source (governing):** the designer's STG-05 hand-offs and rulings (D-CS1-1 to D-CS1-13, and the amended D-CS1-10 and D-CS1-11); ADR-0009 and its amendments from 2026-10-21

**Belongs to or gated by:** **Stage.** STG-05, in the slice order the designer set: CS-1 (#230 and #231 merged; the CB-08 group follow-up closed when the operator cut the WIS issuer, 2026-10-24, and the store is owner-only again, #256), CS-2 (#244 merged), CS-3 (CS-3a, #246, and CS-3b, #257, merged), then CS-4 in the map's order

**Notes:** One row per build stage, and each slice notes on it (designer, D-CS1-12, 2026-10-23). CS-1's notes moved here from the closed F2 row.

*Later notes: `notes.d/STG-05/`, oldest first (`python tools/register.py show STG-05`).*

### STG-12

**Work:** As-built reconciliation: a generated, CI-checked reference of what the code is (`docs/reference/`), from the code's own owners, so that a design-side trace can pair it with the requirements

**Source (governing):** the documentation recovery plan v0.3 (adopted 2026-10-23); the designer's S12-2 hand-off and its two addenda

**Belongs to or gated by:** **Stage.** STG-12; S12-2 builds the reference in pull requests one after another

**Notes:** No requirement ids or text in the repository: the trace is the design side's.

*Later notes: `notes.d/STG-12/`, oldest first (`python tools/register.py show STG-12`).*

### STG-13

**Work:** V-01's oracle rebuilt: the frozen vertical instrument re-derived as V-01's oracle and retired in the same PR (exempted by the operator)

**Source (governing):** the vertical-UAT ruling of 2026-10-23; the operator's decisions of 2026-10-24 (V-01's first row; the oracle rebuild's exemption); the register rebaseline (design workspace, `b598fdc`)

**Belongs to or gated by:** **Stage.** STG-13; V-01's first row, after G3 in the contention order (§1)

**Notes:** One row per build stage, and each slice notes on it (designer, D-CS1-12, 2026-10-23).

*Later notes: `notes.d/STG-13/`, oldest first (`python tools/register.py show STG-13`).*

### STG-14

**Work:** I-6, the resource, model and host policy: the first of the wire increments V-01 needs, with O-01 0.8 (42 actions) as the selected command wire

**Source (governing):** A-39, I-6 at revision 3 (adopted by the operator on 2026-10-25, design workspace `43e14c0`)

**Belongs to or gated by:** **Stage.** STG-14; after V-01's oracle in the Now list (§1), unless the operator moves it. A contract, not an activation: its protected rows stay held until G3 is established, which is no sooner than CS-4's merge

**Notes:** One row per build stage, and each slice notes on it (designer, D-CS1-12, 2026-10-23).

*Later notes: `notes.d/STG-14/`, oldest first (`python tools/register.py show STG-14`).*

### STG-15

**Work:** The capability register: CAP-1 (ripgrep), then the rest of the base bundle; MCP servers later, imported from SPT

**Source (governing):** A-38, the capability register position (revision 2.1, adopted by the operator on 2026-10-24; design workspace, `7fde841`); the operator's decision of 2026-10-24 (AEW brings its own base tools); the register rebaseline (design workspace, `b598fdc`)

**Belongs to or gated by:** **Stage.** STG-15; CAP-1 first, then the rest of the base bundle

**Notes:** One row per build stage, and each slice notes on it (designer, D-CS1-12, 2026-10-23).

*Later notes: `notes.d/STG-15/`, oldest first (`python tools/register.py show STG-15`).*

### HOLD-02

**Work:** The register rows held on the adopted position A-02, product cohesion and the operator's and Lead's experience: 6 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-02; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F8**, Lead and operator interaction: reconnaissance, elicitation, project maps and freshness, durable stakeholder decisions, checkpoints (source: `docs/design/proposals/lead-operator-interaction-design-v0.1.md` §3 to §15, §18)
- **F16**, Explain AEW to the model Lead instead of leaving it to trial and error (operator, 2026-09-30) (source: operator; the dogfood: 51 refused commands of 887, 37 `--help` lookups, Leads guessing at classes (`m3-audit-findings.md` T3, X4; Q10))
- **F27**, Dogfood AEW on AEW: the register and AEW's own backlog as the real-repository dogfood (source: architecture review F-J; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05)); note: after V-01
- **F37**, Field diagnostics, so that an operator running a released AEW elsewhere can find out what went wrong in a run and hand the evidence to AEW's maintainers safely: correlation IDs and timing carried across the CLI, engine, supervisor, harness and bridge, so one run's events line up end to end; an `aew debug bundle` command that gathers a run's diagnostic material (logs, state and timings) into one archive; and work-safe sharing: a metadata-only mode, a manifest of every item that the operator reviews before anything leaves the machine, and scrubbing of secrets, paths, internal names and content (source: operator request, 2026-10-09)
- **F47.6**, The discovery layer: mechanisms that find a whole class of problem without being pointed at it, over the vertical UAT (source: the operator's standing rule of 2026-10-12 (build mechanisms that find a whole class, never "fix this one, handle the next later") and approval of the concept; the Lead's discovery-layer specification v3.4 (independently reviewed CLEAR, parked; not in the repository)); note: a parked concept
- **U5**, Generated per-archetype command references in role briefings and the Lead's guide (source: review finding 4; operator note 1)

*Later notes: `notes.d/HOLD-02/`, oldest first (`python tools/register.py show HOLD-02`).*

### HOLD-04

**Work:** The register rows held on the adopted position A-04, the engineering workflow: plan assurance and work conservation: 7 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-04; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F14**, Plan assurance and premise validation before mutating dispatch: raw stakeholder intent kept apart from derived interpretation, with statements typed (requirement, observation, diagnosis, inference, decision); acceptance reconstructed independently by a fresh role *before* it sees the proposed plan; decision-sensitive premises tested by discriminating probes; typed pre-implementation baselines (`EXPECTED_FAILURE`, `UNEXPECTED_PASS`, `INVALID_MEASUREMENT`, …); negative controls; subject kept apart from acceptance inputs, oracle, evaluator and environment, with protected acceptance conditions enforced through final verification; a Plan Challenge with bounded outcomes and disagreement budgets; assurance bound to the whole dependency set by canonical hash; `ASSURED` as one derived gate predicate at plan acceptance and at every dispatch path; deterministic plan lint; hierarchical inheritance of parent obligations; proportional tiers A–E with hard triggers; strong models at interpretation points (source: `docs/design/plan-assurance-and-premise-validation-design-v0.4.md` (supersedes v0.3))
- **F14.1**, Parent-plan `interactions[]` and the composition rule: a parent plan lists structured interactions between sibling work units wherever a material interaction exists (`between`, dependency and interface refs, shared surfaces, allocated identifiers, `parallelism` PARALLEL_ALLOWED|SERIAL_REQUIRED|CONDITIONAL, conditions, rationale refs), the reviewed parallelism verdict of Q4; `SERIAL_REQUIRED` compiles to the existing blocking dependency; `PARALLEL_ALLOWED` is permission only; `CONDITIONAL` governs only through closed, engine-evaluable predicates (an interface digest still current, an overlap set still empty, a named dependency state), free text explaining only; no model-generated coupling score: the engine supplies deterministic dependency, interface and overlap evidence and plan review judges; parent-plan lint at acceptance (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §1 Q4, §3.7, §3.18 (ledger AIR-05, AIR-29 to AIR-32, AIR-74); the architecture audit of 2026-10-11, §8(a))
- **F34**, Deterministic work conservation, the cross-cutting requirement's own obligations: the design review question (is the model being asked to do something AEW could safely and deterministically do itself?) asked of every significant feature or workflow, and the measurement that it works: navigation, workflow-ceremony and multi-agent metrics and the useful-reasoning ratio, on F25's usage substrate and F19's evaluation program (source: [deterministic work conservation requirement v0.1](../design/deterministic-work-conservation-requirement-v0.1.md) (adopted by the operator 2026-10-09; ledger WCR) §1, §15 to §19, §21 to §24, §26)
- **F41.12**, Plan underspecification signals (F14): no plan-length score; structured `mechanisms[]` fields filled or `n/a: reason` (an advisory author claim review may challenge); review finding a material schema, registry key, reason code, error class, authority owner or mechanism invented during implementation and absent from the accepted plan; a worker's `design_decision_required` (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §5.1, §16 (ledger CFI-24, CFI-64, CFI-65); acceptance check 23 (CFI-93))
- **O3**, A goal met by changing its own inputs: AEW integrated a wrong T4 change after the implementer edited the sample data the goal was stated against (source: `m3-dogfood-report.md` §6.2); note: with F14
- **U3**, F14 addendum: operator-provided factual premises can be decision-sensitive, not only explicit diagnoses (source: review §"How good is the report?"; the headless premise); note: with F14
- **V3**, Whether review-type work should default to a plan-bound reviewer (source: the run: the Lead accepted all three plans with `--assurance none`; review and verification of the deep ticket were staffed by hand); note: with F14

*Later notes: `notes.d/HOLD-04/`, oldest first (`python tools/register.py show HOLD-04`).*

### HOLD-05

**Work:** The register rows held on the adopted position A-05, authority, delegation and classification: 4 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-05; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F6**, Fail-closed classification applied to existing classifiers: the downgrade rule for `verify classify`, and risk-class choice (source: invariant index `AEW-INV-CLASS-001` and `AEW-INV-VERIFY-001`; hierarchy design §11.1 (Scenario H)); note: with Q4
- **F7**, Delegation and resource governance: bounded nested-delegation grants, duplicate-work detection, fanout, retry and interruption budgets, exact-match permission aggregation, cancellation propagation across fanout (source: lead/operator design §16 and §17; lessons note, Incident A); note: its budget part with HOLD-21
- **F50**, Operator rules, the record contract: standing guidance the operator makes binding, as a **new governed record kind**, outside Knowledge's authority (not a Knowledge subtype) (source: the designer's decisions of 2026-10-12 on the Lead's experience-log batch 3, relayed by the operator (operator rules are a new record kind outside Knowledge; rules reach worker briefs automatically, compiled by the engine with role and scope checks; the correction on precedence and approval fatigue; the resolution of the Lead-notebook conflict), read with the earlier ruling on the same brief (operator activation, provenance in briefs, no second policy language); the vertical-path plan §1e (Lead, 2026-10-12; independently reviewed CLEAR; not in the repository))
- **Q4**, Fail-closed rules for `verify classify` and risk class (source: F6); note: with F6

*Later notes: `notes.d/HOLD-05/`, oldest first (`python tools/register.py show HOLD-05`).*

### HOLD-06

**Work:** The register rows held on the adopted position A-06, hosting and the execution boundary: isolation, concurrency, recovery, harness adapters: 12 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-06; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **E50**, Lead inactivity expiry: after long inactivity a Lead attachment is staled or revoked and a fresh attachment and generation are required, under Q12's semantics; for abandonment cleanup (an attachment left over a long absence), not short-session policing; it never silently kills independently admitted child work (source: [F23 decision record](../design/decisions-2026-10-07-f23-internal-alpha-threat-model.md) §1 item 4 (ledger IAT-05)); note: the Lead seat lifecycle is A-28's
- **E66**, Platform asymmetry of the joins: check that packs, wakes and usage behave the same on Linux, where containment is real, and on Windows, where it is a label (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.15 (ledger AIR-63); the second brief's list of what the audit did not cover)
- **F3**, Workspace strategy abstraction, role-sensitive isolation, repository-scale benchmarks (source: isolation design §4 to §14; lessons note, Incident B)
- **F10**, Mutating concurrency above 1: integration queue, merge revalidation (source: `m1-implementation-plan.md`; `implementation-status.md`)
- **F15.3**, The `aew-run` role server (the run bridge's `whoami`, `check.run` and typed `submit` as tools inside the sandbox, the supervisor keeping the credential) and `aew-knowledge` as a separate capability namespace over the shared transport library (source: [typed Lead surface v0.2](../design/typed-lead-surface-design-v0.2.md) §6, §11 (ledger TLS-23, TLS-28)); note: no longer waits on M6a
- **F15.6**, Bounded recovery, the approved limited slice: R5-1, one `STALE_REVISION` retry of a non-judgment step with legality recomputed and a durable `retried_after_stale_revision` marker; and R5-3, one relaunch of a `launch_failed` run (`recovery.relaunch_launch_failed: 1`, default 0), fail-closed: a termination proof from every custody mechanism, the old credential revoked and confirmed before a fresh one is bound to the new run id, a positive no-side-effect proof over every effect channel, an implementation-owned allow-list of transient reasons (unknown fails closed), a circuit breaker (recommended 3 in 5 minutes per endpoint, or project-wide; operator reset), and a relaunch record binding all of it (source: [bounded recovery policy design v0.1](../design/bounded-recovery-policy-design-v0.1.md) (approved, limited slice, 2026-10-05; ledger BRP-01 to BRP-07, BRP-09, BRP-10), as amended by [A2, launch-failure recovery safety](../design/launch-failure-recovery-safety-amendment-v0.1.md) (approved 2026-10-05; ledger LFR-01 to LFR-08); [pre-F15.2 amendment set v0.1](../design/pre-f15-2-amendment-set-v0.1.md) (ledger PFS-01 to PFS-04); [A3, policy binding and digests](../design/policy-binding-digest-amendment-v0.1.md) §5 (PBD-06))
- **F15.7**, The deferred recovery rows: row 4 `REDISPATCH_IF_LOST` (a pre-authorized re-dispatch of a lost clean run, a sibling of `PUBLISH_IF_CLEAN`), row 6 a policy-resolved Investigator after a blocked report, row 8 `max_fix_attempts` (the fix-loop cap) (source: [bounded recovery policy design v0.1](../design/bounded-recovery-policy-design-v0.1.md) §8, §10 (ledger BRP-08, BRP-10))
- **F15.8**, The `aew-run` read half, ahead of M6a: the role-side server inside the sandbox over the existing run bridge (credentials stay supervisor-side), `whoami` and `check.run` as tools, and typed read operations as `bridge.OPERATIONS` rows: map search with exact resolution first and a workspace-rooted lexical fallback, `map.symbol`, `map.callers` and `map.callees` (`NOT_SUPPORTED` until a semantic extension covers the language), `map.tests_for`, `map.constraints`, `map.changed`, `evidence.show` and `check.suggest`, under one result envelope (terminal state, coverage, freshness, evidence locators, omitted counts); the execution profile's `tools.presentation` (raw-first, neutral or typed-first); raw tools unchanged (source: [agent-effectiveness adoption](../design/decisions-2026-10-09-agent-effectiveness-adoption.md) §3 Revision A, §5, §10.1, §11 (ledger AEA-10, AEA-19 to AEA-21, AEA-29); [typed Lead surface v0.2](../design/typed-lead-surface-design-v0.2.md) §6; [project maps v0.5](../design/project-maps-design-v0.5.md) §7; [agent-effectiveness synthesis](../research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md) §3 (ledger AES-03, AES-04))
- **F24**, A second real harness adapter (Codex app-server or Claude Code headless) through the existing conformance suite and the live lane (source: architecture review G4, F-E; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05))
- **F24.1**, Codex runtime-semantics probe, the first slice of any Codex adapter work: the pinned Codex app-server against a scripted loopback model, on Windows and AEW_RL8 under AEW's own containment, with no real provider or credential (source: operator request, 2026-10-10; method as the F9-A MS0 and U1 S0 probes of OpenCode 2.0.18 (evidence in `docs/implementation/adr/evidence/f9a-delivery-probe-2026-10-10/`))
- **F24.2**, Claude Code headless as a further harness adapter, a stretch goal after the Codex adapter: the same F24.1-style runtime probe first, then the conformance suite and the live lane (source: operator request, 2026-10-10 (a stretch goal: support for every harness the operator uses))
- **F48**, The Windows containment backend for the Lead and the workers, so Windows can qualify (source: the designer's Windows containment decisions of 2026-10-11 and 2026-10-12 (relayed by the operator); ADR-0009 (labels); the Windows containment research of 2026-10-09 (not in the repository; a sanitized copy is owed through the ingestion gate)); note: Windows is outside the release gate

*Later notes: `notes.d/HOLD-06/`, oldest first (`python tools/register.py show HOLD-06`).*

### HOLD-07

**Work:** The register rows held on the adopted position A-07, assurance and evidence: 10 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-07; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **E61**, Integration debt, audit AX-14 (P3): a re-review gets no delta against the prior review (source: The architecture audit of `main` at `1dd89d5` (2026-10-11), AX-14; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.9 (ledger AIR-41))
- **E63**, A fix round names the review it answers: a minimal `answers` link on the repair or re-dispatch record, so review and fix rounds can be counted as cycles (observability inventory gap 3) (source: The observability inventory of 2026-10-11, gap 3; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.8 (ledger AIR-33))
- **E77**, Recurring finding classes across review rounds: a future AEW mechanism that detects a finding class recurring across review rounds and prompts method-level rework instead of repeated instance fixes (source: Designer ruling, 2026-10-12, M2 (approved with amendment) and M3 (register M2 for future product design, outside the vertical recovery gate). Its practice counterpart, M1 (a repeatable-class finding states its invariant, scope, enumeration and coverage limits), is added to AGENTS.md §1 by #224)
- **F17**, Consequence tracing and evidence depth ("shallow finding termination"): a role finds a consequential fact, capability or boundary condition but closes before establishing what it leads to (source: Designer and operator, 2026-10-01. Evidence: the M3 review comparison (R1: T-0001 closed the primitive as a known limit by its containment label; T-0003 checked only the readers of `run.json`, and its verifier stopped three lines above the request queue) and the SPT UAT (two item-9 misses found only by tracing through the build; the unchallenged headless premise). Proposal: [`shallow-finding-termination-proposal.md`](../design/proposals/shallow-finding-termination-proposal.md) (v0.2, after the designer's and a second reviewer's review).); note: evaluation first
- **F41.9**, `operator_validation` evidence: a new evidence kind integrated with the operator queue, verification observation evidence (not review evidence, never a substitute for required independent verification); a model-proposed script runs only after the operator approves the target host (resolved through the operator-pinned host registry), the full rendered content, the intended action and the capture schema; secrets only through secret-input channels and never persisted; only capture-schema fields persisted; a requirement-to-step coverage check that never claims adequacy (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §13 to §13.3 (ledger CFI-53 to CFI-56); acceptance checks 18 to 20 (CFI-88 to CFI-90))
- **F41.10**, The delta-review packet: engine-derived facts (prior finding ids and status, base and reviewed revision, the engine-computed diff, files changed), qualified-derived facts with provenance only where a qualified T5/F30 source supports them, and claims (the implementer's finding-to-fix map, claimed assumptions and intent) labelled as claims and never promoted to evidence (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §14 (ledger CFI-57 to CFI-60); acceptance check 21 (CFI-91))
- **F41.11**, The nit/observation fast path: the canonical severity vocabulary, with project `nit` presentation-only and an operator-pinned mapping to canonical `observation` that never remaps blocker, major or minor downward; after a CLEAR, eligible observation corrections get one cheap delta review over the full engine-computed delta; any blocker, major or minor finding, an unexpected behavioural change or a further cycle returns the work to the normal review path (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §15, §21 (ledger CFI-61 to CFI-63, CFI-97); acceptance check 22 (CFI-92))
- **F41.13**, The engine-behavior citation rule: a claim about current engine behaviour used as a premise for a fix or a designer decision cites its code basis; AEW checks mechanically only that the cited path, symbol, test and revision resolve at the cited base commit; whether the code supports the claim stays a review judgment (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §17 (ledger CFI-66, CFI-67); acceptance check 24 (CFI-94))
- **F49**, Scoped fix briefs, as a product feature (source: the operator's rule of 2026-10-12 (fix the class, never one instance per round); the Lead's process observations of 2026-10-10: fixes reintroducing one instance of a finding class per review round, and the opposite failure, a bounded fix that over-reached)
- **U10**, A small correction to an accepted record needs a full replacement record (source: the Lead's debrief)

*Later notes: `notes.d/HOLD-07/`, oldest first (`python tools/register.py show HOLD-07`).*

### HOLD-08

**Work:** The register rows held on the adopted position A-08, work identity and scope: hierarchy revision: 2 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-08; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F4**, Ticket supersession lineage, and a first-class goal-revision path (source: hierarchy design §8 to §10, §20 (Scenarios A and E); [Ticket-revision contract amendment](../design/workflow-contract-amendment-ticket-revisions-2026-10-06.md) (E19-B v0.4, adopted by the operator 2026-10-06; ledger TRA)); note: its plan is CLEAR at v8, dormant until S12
- **F5**, Hierarchy revision semantics: EDITORIAL, CLARIFICATION and MATERIAL; Story and Epic revision; approved-baseline drift; admissibility as a Knowledge Contract concept (source: hierarchy design §4 to §7, §12 to §18)

*Later notes: `notes.d/HOLD-08/`, oldest first (`python tools/register.py show HOLD-08`).*

### HOLD-09

**Work:** The register rows held on the adopted position A-09, coordination and integration: 22 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-09; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **E55**, `--when next-step|turn-end` on `aew harness send` (the designer's decision of 2026-10-10) (source: designer decision, 2026-10-10 (steer vs queue, option B; ledger CMG-34, [record](../design/decisions-2026-10-10-f9-steer-vs-queue.md), ledger SVQ); the G1 and G2 decisions ([record](../design/decisions-2026-10-10-f9-a-g1-g2.md), ledger MGT) and the G4 and rename decisions ([record](../design/decisions-2026-10-10-f9-a-g4-rename.md), ledger MGR); F9-A plan v4 amendment 2 (CLEAR at v10) §3 and §4; the MS0 probe (P1, P4; [evidence](adr/evidence/f9a-delivery-probe-2026-10-10/probe-results.md)); [ADR-0017](adr/0017-coordination-messages.md) D8 (ledger CMG-28, CMG-33))
- **E56**, Integration debt, audit AX-06 (P2): a `follow_up` disposition is not linked to the follow-up Ticket it promises (no back-link, and no anomaly when the follow-up is abandoned) (source: The architecture audit of `main` at `1dd89d5` (2026-10-11), AX-06; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.9 (ledger AIR-41))
- **E57**, Integration debt, audit AX-07 (P2): an adopted plan's source freshness never reaches the dispatch predicate, so a plan premise is not rechecked (source: The architecture audit of `main` at `1dd89d5` (2026-10-11), AX-07; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.9 (ledger AIR-41))
- **E58**, Integration debt, audit AX-08 (P2): an ancestor plan's invalidation produces no event, no Lead decision and nothing for the worker (source: The architecture audit of `main` at `1dd89d5` (2026-10-11), AX-08; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.9 (ledger AIR-41))
- **E59**, Integration debt, audit AX-12 (P4): the published commit names no integration record or evidence (no trailers), so joining a commit back to its Ticket relies on commit subjects (source: The architecture audit of `main` at `1dd89d5` (2026-10-11), AX-12; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.9 (ledger AIR-41))
- **E60**, Integration debt, audit AX-13 (P3): `coordination_unseen` is not read by the projections, which blocks F9's worker-reply slice (source: The architecture audit of `main` at `1dd89d5` (2026-10-11), AX-13; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.9 (ledger AIR-41))
- **E64**, Identity-bearing block and queue-wait events: blocked time produced by the dependency engine, queue-wait time by the queue, each as canonical process facts that F42 aggregates (observability inventory gap 8) (source: The observability inventory of 2026-10-11, gap 8; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.8 (ledger AIR-36))
- **E78**, Head-bound CI status in the product: the existing engine evidence and projection owners surface the CI status bound to the exact head in hand-backs, verdict records and the Lead projection (source: Designer ruling, 2026-10-12, C2 (approved with amendment). Its practice counterpart, C1 (every hand-back and verdict carries the CI observation at its exact head), is added to AGENTS.md §1 by #224)
- **F9**, Live coordination and assumption propagation (source: `docs/design/proposals/AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md`, as amended by the adopted [F9-A1 v0.1](../design/f9-a1-lead-worker-messaging-and-adaptive-supervision-amendment-v0.1.md) (ledger LWM)); note: F9-A is built
- **F9.1**, Typed worker consultation and feedback messages (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.8 gap 12, §3.10 to §3.12 (ledger AIR-38, AIR-43 to AIR-53); the observability inventory of 2026-10-11, gap 12)
- **F9.2**, Admitted Lead instructions in review and verification context (audit AX-02): a bounded, engine-owned, immutable content record for each admitted Lead-to-worker send, one canonical content object referenced by both paths (`harness send` with messaging off, the F9 thread with messaging on), never two histories; a small durable body limit aligned with F9's message discipline (about 4,000 characters), larger material by referenced artifact; reviewer and verifier packs carry each admitted instruction that materially applies to the reviewed attempt, with its message id, kind, admission time, Ticket, revision and attempt binding, canonical sanitized content and provenance, and show explicitly when content is redacted (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.4 (ledger AIR-21 to AIR-23); the architecture audit of 2026-10-11, AX-02 (P1))
- **F33**, Operator-approved exact-commit push, a delivery capability: after a Ticket is accepted on its verified local result, the operator approves pushing that exact commit to an explicit remote and ref, never forced; AEW records an attributable receipt (the accepted local commit, the requested remote and ref, the resulting remote SHA and ref) and checks the pushed remote object resolves to the exact accepted commit; push is never part of correctness or `DONE`, needs no second verification for crossing the network, and its failure is a delivery failure, never a retroactive `VERIFICATION_FAILED` (source: [F23 decision record](../design/decisions-2026-10-07-f23-internal-alpha-threat-model.md) §1 item 6 (ledger IAT-07)); note: AEW never pushes without the operator's sign-off
- **F41**, Cross-feature integration, the activation gate: the design that connects the adopted owners (plans as governed parent work, section binding, a non-blocking interface-dependency edge, overlap, health, operator validation, delta review, plan underspecification) with no second lifecycle, invalidation, review-proof, health or coordination system; the activation gate that checks the required WC/F14 and WC §8 amendments are present (acceptance check 26); the field-log disposition table kept complete (check 25) (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §1, §18 to §20, §22 (ledger CFI-01, CFI-02, CFI-68 to CFI-70, CFI-95, CFI-96, CFI-99), frozen by the designer 2026-10-10; [decision record](../design/decisions-2026-10-10-cross-feature-integration-freeze.md) (ledger CFD)); note: the cross-feature design v0.5 was never adopted; A-09 and the wire track carry integration
- **F41.1**, The Workflow Contract / F14 amendment for mandatory reviewed parent plans: every ancestor Epic and Story, Class 0 included, has a reviewed accepted plan, which changes `parent_paths["0"]` (the Class-0 parent path); the parent-plan guard as an input to F14 §17.1's single `DispatchDecision`, not a second dispatch engine; the reviewed-plan record contract (proposal, independent R1 review bound to the proposal's sha256, adoption by someone other than the proposer); the minimal Class-0 parent plan (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §2, §4, §4.3, §19 (ledger CFI-03, CFI-04, CFI-17, CFI-21, CFI-70))
- **F41.2**, The reviewed-plan contract, built: a derived `plan_phase` (no new stored parent work state); the parent-plan guard in `DispatchDecision`; plan proposal, review and adoption with the proposer barred from the reviewer and adopter slots (operator adoption or a Lead generation with a different admitted identity when the Lead proposed); the engine-derived planning/research child exemption (admitted purpose and the resolved effect envelope against the allow-list, never a label); the planner's own plan obligation met by its assignment; the migration of in-flight parents; Ticket planning kept conditional; `design_decision_required` as an attention reason, never a transition (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §2 to §5.1 (ledger CFI-03, CFI-05 to CFI-12, CFI-14 to CFI-24, CFI-30); acceptance checks 1 to 6 and 23 (CFI-71 to CFI-76, CFI-93))
- **F41.3**, The `non_mutating_paths` migration: the planning-child exemption changes the existing `non_mutating_paths` default, so adoption migrates project policy in `policy/gates.yaml` and no existing project silently keeps the old rule (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §3.1 (ledger CFI-13))
- **F41.4**, Section-digest plan binding (E19-B with F5): every mutating descendant dispatch records the ancestor plan id and revision, the consumed section ids and an engine-computed normalized digest of each; the default consumed set (objective, requirements and acceptance criteria, the interfaces it names, its decomposition entry), narrowed only by the parent plan's structured decomposition; a governed, versioned normalization algorithm; staleness iff a consumed digest changes; the replacement-plan rules; `plan reconfirm --subtree` as an explicit recovery action that makes no evidence admissible (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §6 to §6.3 (ledger CFI-25 to CFI-33); acceptance checks 7 and 8 (CFI-77, CFI-78))
- **F41.5**, The Workflow Contract §8 amendment for the `interface_dependency` edge (V-1(b)): a new non-blocking edge kind for a contract or assumption dependency between work that may run in parallel, blocking edges keeping their meaning; the same amendment extends E19-B §7.5's `revision_impact_hold` trigger to accepted interface revisions on `interface_dependency` edges (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §7, §19 (ledger CFI-34, CFI-35, CFI-70))
- **F41.6**, The interface-dependency edge, built (E19-B with F9): the edge's fields; dispatch of a consumer while its provider is active when the accepted contract is current and the consumer is bound to its digest; engine-computed interface digests, never author-supplied, rename or removal counting as a change; the `INTERFACE_CONTRACT_DRIFT` integration and publish refusal; the E19-B `revision_impact_hold` on direct named consumers (dispatch, forward gates, publish; no recursive fan-out); hold clearing only by the Lead's F9 disposition (`RECONTEXTUALIZE` or `TICKET_REPLAN`) plus the engine's rebinding; the held worker can neither clear its own hold nor record either of those authority-bearing actions; a new attempt against the new digest (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §7.1 to §9, §11 (ledger CFI-36 to CFI-45, CFI-48, CFI-100); acceptance checks 9 to 13 and 15 (CFI-79 to CFI-83, CFI-85))
- **F41.14**, The cross-feature integration design's field-log dispositions that hand work to owners outside F41's own rows, each to be taken up by its owner: #4 test scope (the launch-contract / test-policy owner); #10 public/private review (a review-artifact policy follow-up); #12 operator waiting queue (the existing operator-attention / dashboard owner: F15.5 for the operator-attention half, F20 for the dashboard half); #15 disk budget (the doctor / workspace-retirement owner, F18.2); #16 CI external check (an external-check / `wait --any` integration candidate, F9); #20 PR lifetime (an evaluator / process metric candidate, F19) (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §18 (ledger CFI-68, CFI-101 to CFI-106))
- **F45**, Base-drift integration validation (AX-01): at prepare and rebuild the engine computes the drift between the Ticket's base and the integration base from Git and records its changed paths and their overlap with the Ticket's; the validation obligation consumes the recorded overlap under a legality-affecting key, `gates.post_integration.base_drift_overlap`; the integration verifier's pack gains an engine-derived section, the work integrated since this Ticket's base (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.1 (ledger AIR-09 to AIR-13); the architecture audit of 2026-10-11, AX-01)
- **Q14**, The remote integration target's scope (not before internal alpha, the operator decided on 2026-10-07, F23): when the provider's merge commit differs from the candidate, does `DONE` need a second post-integration verification on it or is verification on the candidate plus containment enough? Also undecided: the first provider, whether AEW ever merges through the provider's API with a precondition, and how the proposal's CI checks relate to AEW's verification (source: [remote integration target sketch](../design/proposals/remote-integration-target-sketch-2026-10-04.md) §5 and "Not decided here" (ledger RIT-05, RIT-07); M4-D must not foreclose it (RIT-06). **Deferred (operator, 2026-10-07, [F23 decision](../design/decisions-2026-10-07-f23-internal-alpha-threat-model.md)):** not an internal-alpha gate; reopened when remote PR or merge integration becomes a product requirement); note: deferred by the operator, 2026-10-07

*Later notes: `notes.d/HOLD-09/`, oldest first (`python tools/register.py show HOLD-09`).*

### HOLD-10

**Work:** The register rows held on the adopted position A-10, the operator and Lead interface: stages, attention, events, observability: 16 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-10; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **E12**, `aew evidence show <id>`, the canonical detailed Evidence read surface, through the existing projection layer with structured output for the typed Lead surface and bounded bodies; normal workflow surfaces keep the record's conclusion and Evidence ID (source: the A6 debriefs: 4 Leads opened evidence files directly, since `aew evidence` has only `ingest` (`m3-evidence-synthesis.md` §3.4); the designer's [decision record of 2026-10-06](../design/decisions-2026-10-06-e12-evidence-read-surface.md) (ledger EVR))
- **E20**, `--json` output on read commands, so the typed action surface wraps structured results, not prose (source: architecture review I3; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05))
- **E28**, Structured `check.run` results: counts, first failures with locations, an artifact reference; the full log stays expandable evidence (source: architecture review §4.2; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05) §6)
- **E69**, One canonical reason vocabulary for externally projected liveness outcomes where their meanings coincide (`lost`, `stale`, `wedged`, `gone`), used by the operator notifier and the projections; the run heartbeat, the broker's beat and the custody worker's identity keep their own mechanisms and thresholds (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.13 (ledger AIR-54))
- **E70**, The hard deadline as one semantic fact: canonical in the error and reason vocabulary and projected into the spool, anomaly and steering-loop surfaces, replacing three independent spellings of it (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.13 (ledger AIR-56))
- **F15**, Lead workflow efficiency: stage commands named for the Lead's judgment (`draft`, `start`, `request-review`, `request-verification`, `prepare`), each a guarded sequence of existing operations with its own durable records, returning completed steps, revision, runs and a typed next action; publish stays a separate decision; exit-code instrumentation of the command log; a paired replay against the M3 dogfood baseline (source: [typed Lead surface v0.2](../design/typed-lead-surface-design-v0.2.md) (governing since 2026-10-05; ledger TLS); the idea note [`aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md`](../design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md) (adopted direction; governs §16, §17 and the F17 and anomaly obligations); `docs/design/proposals/lead-workflow-efficiency-design-v0.1.md` (superseded)); note: the stages built so far stay
- **F15.2**, Governed mutating stages: the `StageIntent` journal (hot while active, cold when terminal), the policy/dependency digest and `STALE_POLICY`, effective-class promotion, queryable transition and ingest guards, policy-resolved review and verification card sets, `ticket_draft`/`ticket_start`/`ticket_request_review`/`ticket_request_verification`/`ticket_prepare` as governed stages, the typed `integration_publish` decision tool, stage/primitive equivalence tests and a live OpenCode 2.0.18 MCP spawn check (source: [typed Lead surface v0.2](../design/typed-lead-surface-design-v0.2.md) §3.4, §3.6, §10, §11 (ledger TLS-13, TLS-14, TLS-17, TLS-26 to TLS-28)); note: E3a is built
- **F15.4**, Policy digest separation: every execution-policy field classified `legality_affecting` or `operational` (an unclassified field fails schema validation); each staged action records `legality_digest`, `operational_digest`, the revision, the authority generation and any action-specific authorization digest; only a legality mismatch is `STALE_POLICY`, an operational change takes effect at the next safe boundary, and a recovery action snapshots the operational settings it depends on (source: [A3, policy binding and digests](../design/policy-binding-digest-amendment-v0.1.md) (approved 2026-10-05; ledger PBD-01 to PBD-10); [pre-F15.2 amendment set v0.1](../design/pre-f15-2-amendment-set-v0.1.md) §1, §4, §5 (ledger PFS-01, PFS-03, PFS-04))
- **F15.9**, Delta-first Lead attention (E2): one typed read query on the Lead surface, changes since a cursor (`changes {since_revision, since_observed?}`), over the outbox's committed transitions and the projection's derived deltas, with the decisions required, blockers and supervision candidates always present, one line per item with an expansion reference, and a size cap; `status` and `resume` stay the full view; no second event or state store (source: [agent-effectiveness adoption](../design/decisions-2026-10-09-agent-effectiveness-adoption.md) §8, §11, §12 (ledger AEA-08, AEA-26, AEA-34); [typed Lead surface v0.2](../design/typed-lead-surface-design-v0.2.md) §3.1; ADR-0012; [agent-effectiveness synthesis](../research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md) §5 (ledger AES-08, AES-13))
- **F42**, Observability and Feedback, the first cross-cutting integration note (Q1, Q2): attribute, aggregate, detect, triage and verify over one process-event model; detectors and their candidates advisory; an accepted improvement verified on the same metric it was meant to move (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §1 Q1, Q2, §3.2, §3.8, §3.18 (ledger AIR-01 to AIR-03, AIR-40, AIR-74); the observability inventory of 2026-10-11)
- **F42.1**, The canonical process-event model: one read-time schema and vocabulary with common ids (a pull request opened, ready or merged; a review round opened or settled; a fix round; CI queued, started or settled; a merge-main round; a conflict and its resolution; a lane blocked or unblocked; an integration wait); the native producer derives events from the transition log, as F25 derives its projections; check and validation durations are elapsed resource use, never F25 model usage (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.2, §3.8 gap 13 (ledger AIR-15, AIR-39))
- **F42.2**, The repository-process adapter: ingests pull request, CI, merge, review and blocking events from the repository host into F42.1's model, in its own append-only store outside control state, with a project id and a mapping from pull request to work unit for AEW's own development (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.2 (ledger AIR-14, AIR-15))
- **F42.3**, Structured role-context and skill feedback: bounded feedback from each role, under the existing Observability and Feedback design, capturing the role, the task, the pack and skill versions, missing, wrong or noisy information, and rule candidates when applicable (source: Designer ruling, 2026-10-12, F1 (approved with amendment))
- **F43**, The attention spine, three ordered slices; S1 and S2 together absorb every duplicate derivation of next actions, as consumers or producers where appropriate (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.3, §3.13 (ledger AIR-16 to AIR-20, AIR-61); the architecture audit of 2026-10-11, AX-03 to AX-05; ADR-0012 D2, D5)
- **F44**, The consequential-fact owner registry: one row per semantic control fact or evidence kind that may influence dispatch, `ActionProjection`, a gate, progression, evidence admissibility, publication, Lead or operator attention, or reviewer, verifier or model context; each row records the fact, owner, producers, authoritative or advisory, the A3 classification reference (never restated), outbox consequences, the Lead or operator projection, consuming packs, the staleness or freshness rule, the data and redaction class and the schema version; it covers the top-level control keys and a declared unit-key inventory; CI and static checks fail on a fact with no complete row (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.6, §3.13, §3.18 (ledger AIR-20, AIR-25 to AIR-28, AIR-54, AIR-55, AIR-74); the architecture audit of 2026-10-11, §8(b))
- **O4**, The Lead is about 40% of AEW's cost (source: `m3-dogfood-report.md` §6.3; `m3-audit-findings.md` L1, L2); note: with F15

*Later notes: `notes.d/HOLD-10/`, oldest first (`python tools/register.py show HOLD-10`).*

### HOLD-12

**Work:** The register rows held on the adopted position A-12, the shared read wire and the dashboard's reads: 4 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-12; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F20**, Read-only operator dashboard, main-line integration (source: Dashboard API contract 0.1.2 (accepted 2026-10-02; SHA-256 `68b46527…d691`); frontend core frozen at `7c120b4` (main-line review and fix verification ACCEPT, 2026-10-02). Merged to `main` by F20.1 (PR #26); the records are `web/docs/reference/integration-checklist.md` and `web/docs/archive/core/frontend-core-review-main-line.md` (index: `web/docs/README.md`)); note: F20.1 to F20.5 are done
- **F20.6**, Integrated acceptance: the browser and security checks against authenticated live state, recorded separately from the frontend's acceptance (source: `web/docs/reference/integration-checklist.md`)
- **F20.7**, The dashboard event endpoint (ADR-0012 D8): `GET /api/v1/events?since=R` as a bounded long poll on the revision cursor over the outbox's typed events, waking on `local/wake` through F20.2's lock-free reader; the reply names only which revisions changed which kinds and ids, and the frontend refetches the projections with their ETags (source: ADR-0012 D8; [`dashboard-main-line-api-design-v0.1.md`](../design/proposals/dashboard-main-line-api-design-v0.1.md) §4.7)
- **F20.8**, Dashboard maps and raw-history search: contract 0.1.3 (source: [`dashboard-maps-and-history-search-v0.1.md`](../design/proposals/dashboard-maps-and-history-search-v0.1.md) (ledger DMS), from the lead developer's plan v6 (CLEAR after five independent reviews); the operator's approval of 2026-10-09 and sign-off of 2026-10-10, the search route included (note §1); the [dashboard design note](../design/proposals/dashboard-main-line-api-design-v0.1.md) §2 and §8 (a contract change renews C0)); note: S1 and S2 are built

*Later notes: `notes.d/HOLD-12/`, oldest first (`python tools/register.py show HOLD-12`).*

### HOLD-13

**Work:** The register rows held on the adopted position A-13, knowledge and context: 2 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-13; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F21**, The M6b knowledge system: capture and admission of reusable knowledge (K0 references, K1 Cases, K2 Lessons, K3 held), guarded recall and context routing, and their shared semantics (identity, provenance, orthogonal state, receipts, visibility composition, provider boundary) (source: **Adopted and governing (operator, 2026-10-09; [adoption decision](../design/decisions-2026-10-09-knowledge-system-adoption.md), ledger KAD):** [knowledge capture/admission v0.4](../design/aew-knowledge-capture-admission-design-v0.4.md), [shared semantics v0.4](../design/aew-knowledge-capture-recall-shared-semantics-v0.4.md), [recall/routing v0.3](../design/aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md) and [ADR-0013](adr/0013-knowledge-storage-placement.md), adopted together; the designer's rulings on worker tool delivery and reviewer independence ([decision record](../design/decisions-2026-10-09-knowledge-tool-delivery-and-reviewer-independence.md), ledger KDR); research basis [v0.1](../research/aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md)); note: K-01 is selected before I-7
- **F35**, Context-pack serving (R8), in the existing `ContextPacks` and `knowledge/context.py`, with no new component: a per-role, per-tier serving-policy table as archetype data (mandatory, opportunistic, on-demand, prohibited) with a conformance test per role; the derived-section rendering convention (source, revision, freshness and coverage or limitations in the heading, one item per line with an expansion reference, a degraded section as one labelled line); the execution profile's `context.budget_chars`, `context.orientation_max_chars` and `context.orientation` (minimal, standard or explicit) passed to the pack, the wiring E29 deferred; the criteria repeated last under explicit orientation if evaluation supports it; the reviewer's layout row; the pack's independence filter for reviewers and verifiers, with sentinel tests (source: [agent-effectiveness adoption](../design/decisions-2026-10-09-agent-effectiveness-adoption.md) §4, §11, §14 (ledger AEA-04, AEA-14 to AEA-18, AEA-40); [project maps v0.5](../design/project-maps-design-v0.5.md) §11; [agent-effectiveness synthesis](../research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md) §2, §6, §7 (ledger AES-01, AES-02, AES-09 to AES-11); E29 (§9))

*Later notes: `notes.d/HOLD-13/`, oldest first (`python tools/register.py show HOLD-13`).*

### HOLD-14

**Work:** The register rows held on the adopted position A-14, project understanding and maps: 6 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-14; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **E62**, Integration debt, audit AX-15 (P4): project maps reach only the investigator's pack, not the planner's, and are not regenerated on publish (source: The architecture audit of `main` at `1dd89d5` (2026-10-11), AX-15; [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.9 (ledger AIR-41))
- **F22**, Project maps: the deterministic structural codebase map, language-specific semantic extensions (C/C++ first) that add qualified facts without redefining it, sibling derived indexes, and the attributable architecture map, composed into one navigation/context view that never becomes an authority source (source: KC §8.2 to §8.5, §13; architecture review G3; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05) G3, D-AR6; **the design is [project maps v0.5](../design/project-maps-design-v0.5.md)** (frozen by the designer and adopted by the operator 2026-10-05; ledger PMP; the repository's v0.4 and v0.3 are archived under `archive/superseded/`), with the research behind it in `docs/research/` (ledger CXS, CXP, SEF, QRC, LRB, PUI)); note: F22.1 is built; P-01 is selected before I-7
- **F22.2**, T5-B then T5-C (source: [project maps v0.5](../design/project-maps-design-v0.5.md) §3.1, §3.2, §3.4, §3.5, §4 to §8, §16 T5-B and T5-C, §17 (ledger PMP-10 to PMP-14, PMP-19, PMP-20, PMP-31 to PMP-58, PMP-70, PMP-71); [semantic-extension framework](../research/semantic-extension-framework-2026-10-04.md) (SEF), [C/C++ extraction](../research/cxx-semantic-extraction-investigation-2026-10-04.md) (CXS), [the C++ contract check](../research/cxx-plus-plus-contract-check-2026-10-04.md) (CXP), [large-repository benchmark](../research/large-repository-benchmark-2026-10-04.md) (LRB), [query routing](../research/query-routing-and-retrieval-classification-2026-10-04.md) §7 (QRC-07))
- **F22.3**, T5-D, sibling project-understanding indexes beside the maps, composed when their inputs exist and never fields of the structural record: the test relationship index (test to paths, symbols or components and the check lane, weaker path/name evidence without semantic facts, never making a test required), the constraint locator index (locators and terms for oracle rules, invariant-index ids, schema fields, guardrails, ADR sections, requirements-ledger ids and amendment-index entries, never rewritten prose), the semantic public-surface projection, and untrusted-string projection tests (source: [project maps v0.5](../design/project-maps-design-v0.5.md) §9, §4.9, §16 T5-D (ledger PMP-22, PMP-45, PMP-59 to PMP-61, PMP-72); [project understanding and impact analysis](../research/project-understanding-and-impact-analysis-2026-10-04.md) §7, §8 (ledger PUI-19, PUI-20))
- **F30**, Requirement impact analysis and the Project Profile: `aew impact <work-id>`, one deterministic operation with two consumers (an inspectable Lead command, and Plan Assurance calling it at Story creation) that computes a surface from the requirement's seeds through the maps (symbols, files and units at radius 1 by default, radius 2 only when budgeted), the test index and the constraint locators, labelled by how each entry was found and with a coverage statement of what was unavailable; its judgement part fills plan assurance v0.4's first-pass artefact and premise list, never a record kind of its own; Epics run on structural directory roles with declared reduced coverage until `components[]` exist; Tickets inherit and narrow the Story's surface; the Project Profile is KC §8's maps plus WC §16.15 guardrails as evidence-bound records with per-claim freshness, not a new layer or document set (source: [project understanding and impact analysis](../research/project-understanding-and-impact-analysis-2026-10-04.md) (research, the designer's third brief; ledger PUI; its §10 holds the designer's decisions of 2026-10-05); plan assurance v0.4 §7, §8; KC §8, §13; ADR-0008; ADR-0013)
- **F41.7**, The overlap projection: read-only and advisory, coverage and unknowns first; signals from exact file overlap, declared blocking and interface dependencies, accepted interface digests, allocated identifiers and namespaces (from project policy data, not an AEW-global list), shared register, schema and config surfaces, build and test surfaces and qualified structural and symbol relationships; mechanically mergeable paths identified separately; unsupported Python import and symbol coverage reported as unknown; the advisory publish-overlap wake (§11 trigger 2) (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §10, §11 (ledger CFI-39, CFI-45 to CFI-47, CFI-49); acceptance check 13 (CFI-83))

*Later notes: `notes.d/HOLD-14/`, oldest first (`python tools/register.py show HOLD-14`).*

### HOLD-15

**Work:** The register rows held on the adopted position A-15, resource and progress supervision: 5 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-15; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F11**, Dynamic scheduler (source: Workflow Contract; `implementation-status.md`)
- **F36**, Weak-worker continuity (R2-B), platform-owned: the bounded handoff note (R2: an optional, worker-authored note of at most 2 KiB in the role report, a claim with references, never authority, citing paths and evidence ids, delivered to a replacement invocation's pack as labelled reference data, never automatically Knowledge), then the recitation (a zero-model-cost restatement AEW assembles from canonical and derived state: the goal or active criterion, the remaining criteria, plan tasks, changed files against the planned scope, checks performed, open findings and blockers, the latest handoff note; delivered on sufficiently long or complex runs through the run's inbox on an operational trigger and recorded like `harness send`) (source: [agent-effectiveness adoption](../design/decisions-2026-10-09-agent-effectiveness-adoption.md) §6, §11 (ledger AEA-06, AEA-22 to AEA-24); [agent-effectiveness synthesis](../research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md) §4, §7 (ledger AES-05, AES-06, AES-12); the R2 recommendation of the external-workflow research of 2026-10-05, which is not in this repository)
- **F41.8**, Two run-health fields (U1/H1): `current_or_longest_child_process`, sanitized (no command line, environment or model-authored arguments; a safe process or tool label, pid or identity where policy permits, age and status), and `age_of_last_durable_progress` (source: [cross-feature integration design v0.5](../design/cross-feature-integration-design-v0.5.md) §12 (ledger CFI-52); acceptance checks 16 and 17 (CFI-86, CFI-87))
- **U1**, Stall detection in `aew harness wait`: return `stalled`, naming the tool and how long, when a tool call has run N minutes with no events (source: review finding 2; run R-INV-0006-1 hung 20 minutes on a truncated PowerShell here-string; [run health projection design v0.1](../design/run-health-projection-design-v0.1.md) (approved 2026-10-05; ledger RHP-01 to RHP-11), as amended by [H1, run health projection implementation note](../design/run-health-projection-implementation-note-v0.1.md) (approved 2026-10-05; ledger RHN-01 to RHN-10); [pre-F15.2 amendment set v0.1](../design/pre-f15-2-amendment-set-v0.1.md) §1, §4 (PFS-01, PFS-03))
- **U7**, Automatic stall recovery (interrupt plus a standard nudge) (source: review finding 2)

*Later notes: `notes.d/HOLD-15/`, oldest first (`python tools/register.py show HOLD-15`).*

### HOLD-17

**Work:** The register rows held on the adopted position A-17, portable hosting and deployment: 16 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-17; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **D2**, An installer, and deeper harness integration (installed commands, one control surface) (source: M3 plan §8)
- **E21**, `aew init` proposes the test command it discovers (`pyproject.toml`, `package.json`, `Makefile`), never configuring it silently (source: architecture review I8; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05)); note: with F18.1
- **F18**, Operator bootstrap and host integration: setting up AEW and its harness on a host, and starting and attaching the operator's session within the hosting boundary Q12 decided (2026-10-06) (source: Designer and operator, 2026-10-01; provider research §5 ([`aew-phase6-airgap-capability-research-2026-10-01.md`](../research/aew-phase6-airgap-capability-research-2026-10-01.md)); **two adopted designs sit alongside each other:** [install, bootstrap and first-run UX v0.3](../design/install-bootstrap-ux-design-v0.3.md) (`aew init`, `aew doctor`, preflight; ledger IBU) and [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) (Lead hosting, security principals, the attachment and generation lifecycle, the gateway, broker binding, host modes, detach and drain, harness qualification; adopted 2026-10-06, v0.6 a hygiene correction; ledger HAA))
- **F18.1**, `aew init` proposes, the operator applies: the proposal file (`.aew/local/init-proposal.yaml`, with `proposal_id` and `inputs_sha256`), `init --apply` as one atomic attributable apply that refuses stale or expanded proposals, `--accept-proposal` for non-interactive use, static-before-trust repository inspection through the T5 generator, and the configuration ownership model (AEW edits no user or project harness file; supported Lead sessions use isolated generated configuration) (source: [install and bootstrap UX v0.3](../design/install-bootstrap-ux-design-v0.3.md) §3, §4, §7, §10 (ledger IBU-03, IBU-09, IBU-10, IBU-11, IBU-16))
- **F18.2**, `aew doctor` with ERROR/WARN/INFO rows, a remedy per row, `--todo`, `--json` with stable finding ids, the harness dry start and schema probe under isolated configuration by default, `--online` for gateway checks, the conflict-detection row for ambient harness files, and never auto-fixing (source: [install and bootstrap UX v0.3](../design/install-bootstrap-ux-design-v0.3.md) §6, §6.1, §7 (ledger IBU-14 to IBU-16)); note: doctor's capability lines are STG-15's (CAPR-03)
- **F18.3**, The air-gap bundle, three side-by-side artifacts: `aew-bundle-<version>-rl8-py311.tar` with the wheelhouse and qualified harness pins, its canonical manifest `aew-bundle-<version>-rl8-py311.json` (committing to the archive's name, size and SHA-256 and to every member), and `aew-bundle-<version>-rl8-py311.json.sig`, a detached signature over the manifest from a release identity with an independently provisioned trust root; a verifier that rejects traversal, duplicates and mismatches before anything is consumed; `aew doctor --bundle --json` as the host acceptance record; tool upgrade separate from project migration with a declared restore point (source: [install and bootstrap UX v0.3](../design/install-bootstrap-ux-design-v0.3.md) §5 (air-gapped), §5.1 (ledger IBU-12, IBU-13); airgap research §7); note: the bundle import is shared with E35's H-3 and CAPR-04
- **F18.4**, Organization launch and provider-access seams: the harness launch provider (`direct_binary`, `airgap_bundle` or `organization`) selecting a qualified pin that AEW independently verifies after launch; the `aew/harness-qualification/v1` manifest (AEW-shipped or organization-approved, the same mandatory conformance); the `provider_access` profile whose mTLS and PKI material stays supervisor-side behind the F28 relay; and the seven-point live qualification gate before the integration is called supported (source: [install and bootstrap UX v0.3](../design/install-bootstrap-ux-design-v0.3.md) §3.1, §10 (ledger IBU-04 to IBU-08, IBU-20))
- **F18.5**, F18-A, contract and state: attachment states (NO_ATTACHMENT, PREPARING, FAILED, ACTIVE, SUSPENDED, DETACHED) and reason codes; the protected-set registry; the support manifest and executable content identity; hot and cold generation records (ADR-0011); guarantee labels (`guarantee: dev`); the operator-only lifecycle contract (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §1, §2.2, §2.3, §3, §8, §16, §18, §19, §21 (ledger HAA))
- **F18.6**, F18-B0, deployment security-principal proof and ergonomics: a dedicated Lead and worker principal or an SELinux-equivalent boundary; an operator-only supervisor socket authorized by peer credentials; supervisor-owned protected state; the group, ACL, git and TUI ergonomic path; refusing a same-principal deployment (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §2.1 to §2.3, §6.1, §20.1, §21 (ledger HAA))
- **F18.7**, F18-B1, bootstrap: a bootstrap-only broker; explicit managed or registered-host selection; managed launch by default; PREPARING cleanup; the conversation-taint record and the reattach delta (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §5, §6, §7, §8.2, §9, §20.2, §20.4 (ledger HAA))
- **F18.9**, F18-D, detached child handling: close acknowledgement; detached-run attention; bounded credentials; the hard-deadline order; drain semantics, with the drain deadline as a stop condition; StageIntent stale-owner handling (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §10 to §15, §20.5, §24.3 (ledger HAA))
- **F18.10**, F18-E, production attachment enablement: F18.6, F18.7, F18.8 and F18.9 combined into managed project attach; existing-host attach enabled only where the forced gateway path is proven (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §5.2, §9, §21 (the development-mode rule) (ledger HAA))
- **F18.12**, F18-G, Codex qualification: qualifying the intended pin with the same versioned suite, plus Codex's request, delegation and ambient-context checks (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §3, §16, §17.2 (ledger HAA))
- **F18.13**, F18-H, reference topology smoke: the Astra Lead with the Laguna default worker, and GPT-5.4 and open-source overrides where available (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §1.1, §20.6 (ledger HAA))
- **F18.14**, F18-I, production-hosting ergonomics observation: measuring principal, ACL, git and TUI friction and operator workarounds before production rollout; M4-H may contribute optional early observations (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §6.1, §20.7, §24.2 (ledger HAA))
- **F31**, The Q12 attachment lifecycle: an AEW project attachment separate from the harness session (`aew open` attaches, by a fresh managed launch by default or an opt-in registered existing host, and `aew close` detaches it while the harness keeps running), a fresh Lead generation and fresh broker authority per attachment, re-hydration from canonical state on attach, stale authority for every older generation, no AEW project authority and no AEW-mediated project access through the detached attachment (read and query commands refused to that generation), a harness crash or host loss that revokes and stales the attachment's generation, the Lead attachment's requested and effective execution profile recorded, and the operator's disposition of running children when an attachment ends (close, crash, host loss, takeover or an uncarried handoff): drain by default (finish within a time limit, results held until a current Lead or the operator accepts them, any of the designer's stop conditions stops the run at once with an error report, while a legitimate negative result is held like any other), or, by the operator only at the operator terminal, stop now or release to manual; the integration custodian surviving an attachment's end with its lease held, its post-integration verifier draining, and no publish on a held result until the current generation accepts it (source: Q12 [decision record of 2026-10-06](../design/decisions-2026-10-06-q12-hosting-and-lead-attachment.md) §4 to §9, §13 and §14 (ledger HSD); ADR-0004, ADR-0005, ADR-0009 and ADR-0010, amendments of 2026-10-06)

*Later notes: `notes.d/HOLD-17/`, oldest first (`python tools/register.py show HOLD-17`).*

### HOLD-19

**Work:** The register rows held on the adopted position A-19, operator intent: steering, confirmation and settings: 6 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-19; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F15.5**, Crawl / Walk / Run steering over `ActionProjection`, with its operator authority boundary: `aew confirm`, autonomy increases and `PUBLISH_IF_CLEAN` grants only through an operator capability structurally absent from agent shells and model tools (the Lead may request, lower and continue); attributable mode-change records; Walk auto-runs only actions whose declared side effects are all in the allow-list `{control_state}`, with catalog conformance (observed effects within declared); the auto-run envelope (budget, admission, repetition N = 2, the loop deadline) and the invocation hard deadline as an authority-reducing safety action; an out-of-band operator notifier for unattended Run (source: [Crawl/Walk/Run steering design v0.1](../design/crawl-walk-run-steering-design-v0.1.md) (approved 2026-10-05; ledger CWR-01 to CWR-12), as amended by [A1, steering authority and execution envelope](../design/steering-authority-execution-envelope-amendment-v0.1.md) (approved 2026-10-05; ledger SAE-01 to SAE-15); [pre-F15.2 amendment set v0.1](../design/pre-f15-2-amendment-set-v0.1.md) (ledger PFS-01 to PFS-04)); note: its confirmation is G3's (A-37)
- **F46**, The Operator Settings Surface: every operator-editable setting (marked by an explicit schema or registry annotation) has a dashboard editor showing its current value, description, valid values, classification, effective boundary, proposed value, validation result, diff and authority and effect; a generic schema renderer, custom editors where needed, and a completeness test proving every such setting has one (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §3.16, §3.17, §6.1 to §6.3, §6.7 (ledger AIR-65 to AIR-73, AIR-78 to AIR-80, AIR-84); the operator's request of 2026-10-11); note: the operator wants it; CAPR-13's register editor is its first case
- **F46.1**, The configuration read projection, first: the selected project's execution profiles and model routing as an engine read projection with its F20 HTTP adapter, carrying the digest a later Save binds to (source: the operator's approval of the F46 work breakdown and the aligned configuration page direction (2026-10-11); F46)
- **F46.2**, Validate, preview and apply inside the operator session: `aew settings set` and the dashboard's Save call `settings_apply` as the operator principal, which validates, previews the change bound to F46.1's digest, classifies it with F15.4 (a loosening re-authenticates), then writes, re-pins and records in one transaction with no pending-adoption window (source: the operator's approval of the F46 work breakdown (2026-10-11) and its authorized refinement of the same day; F47.3)
- **F46.3**, The model catalog, direct-provider first: a direct OpenAI-compatible provider's catalog (`GET /v1/models`) and the chooser built on it, through the adapter-owned model-id mapping (F47.4) that binds a catalog entry exactly to AEW's separate provider and model fields; the supplied exact model identity, capabilities shown as not supplied where the provider gives none, and a configured model the catalog lacks shown as an unavailable reference (source: the operator's approval of the F46 work breakdown (2026-10-11); F46 (models per role))
- **F46.4**, The web integration: the dashboard's configuration page on F46.1 to F46.3's accepted contracts and merged routes, with a compact, backend-supplied "What changes when I save?" explanation, and invocation pins, existing and future, accepted unchanged; the remaining configuration documents reuse the same workflow (source: the operator's approval of the F46 work breakdown and the aligned configuration page direction, with its authorized refinement (2026-10-11); F46)

*Later notes: `notes.d/HOLD-19/`, oldest first (`python tools/register.py show HOLD-19`).*

### HOLD-20

**Work:** The register rows held on the adopted position A-20, model access and provider delivery: 5 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-20; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **D5**, Model optimization and routing policy (source: M3 plan §8)
- **F18.8**, F18-C, the load-bearing gateway and broker binding: the gateway principal and provider-credential custody; forced egress; the normalized structural-surface parser; pre-egress enforcement; server-side binding of a response's `tool_call_id` and argument hash, single-use with expiry; SUSPENDED behaviour; the fail-closed gateway outage policy (source: [F18 harness hosting and attachment authority v0.6](../design/f18-harness-hosting-attachment-authority-design-v0.6.md) §4, §20.3 (ledger HAA)); note: the gate before a client-certificate provider stays in section 1
- **F18.15**, Gateway usage convergence: one accounting hook in the AEW Provider Gateway emits the authoritative provider-usage event; F19's slice S18 is an evaluator client of it, never a second, permanent metering proxy; F25 projects and cross-checks it, with a gateway trust and source value in its usage vocabulary (source: [decision record](../design/decisions-2026-10-11-architecture-integration.md) §1 Q5, §3.5, §3.13 (ledger AIR-06, AIR-24, AIR-60); the architecture audit of 2026-10-11, AX-09)
- **F32**, The reference execution profiles: the Lead on GPT-6 Astra, Laguna S2.1 as the default worker, GPT-5.4 and approved open-source models as selectable workers, each qualified through the pinned harness (exact provider and model ids, effort variants, a live-lane run) before it is relied on; no workflow semantics keyed to a model's name (source: Q12 [decision record of 2026-10-06](../design/decisions-2026-10-06-q12-hosting-and-lead-attachment.md) §3 (ledger HSD); ADR-0010, amendment of 2026-10-06)
- **V5**, A rotated provider key without restarting `aew opencode`: the Lead broker picks up a new value of the variables `provider_env` names when it launches a run (source: the 2026-10-10 incident (a daily key expired; relaunches from the Lead session kept failing until `aew opencode` restarted); PR #165, which closed V1 by reporting the failure)

*Later notes: `notes.d/HOLD-20/`, oldest first (`python tools/register.py show HOLD-20`).*

### HOLD-21

**Work:** The register rows held on the adopted position A-21, resource accounting: cost and usage: 2 rows from before the rebaseline, each with its old title and source in Notes

**Source (governing):** the adopted position A-21; the register rebaseline (design workspace, `b598fdc`), section 5

**Belongs to or gated by:** **After the trace.** The group leaves the hold only as the preamble's *Keeping it current* says

**Notes:** Members, each as the register held it at `b879f6bd` (its full row is there; the design documents it cites stay as inputs, not authority):
- **F25**, An engine-owned cost and usage ledger: per run (model/profile, token categories, wall time, provider-reported and price-table cost), rolled up per invocation, Ticket and parent (source: architecture review G7, F-D; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05); **the design is [the cost and usage ledger v0.2](../design/cost-usage-ledger-design-v0.2.md)** (adopted by the designer 2026-10-06 after a narrow revision; ledger CUL)); note: the run ledger is built; the Lead part waits
- **U4**, Lead usage, provider and cost observable in AEW (source: review finding 5); note: with F25

*Later notes: `notes.d/HOLD-21/`, oldest first (`python tools/register.py show HOLD-21`).*

## 3. Deferred by the M3 plan (out of M3 scope)

<!-- columns: # | Work | Source | Target and notes -->

(none, since the rebaseline)

## 4. Open questions awaiting a decision

<!-- columns: # | Question | Owner | Source -->

(none, since the rebaseline)

## 5. Dogfood findings left open (small)

<!-- columns: # | Finding | Source | Target and notes -->

### O2

**Finding:** The headless Lead's shell allow-list refused `git -C <dir>`, `git branch` and chained commands (`a; b`)

**Source:** M3 dogfood

**Target and notes:** **Unscheduled** (Lead UX). By design for the TUI, where the operator is asked. For headless use, consider a read-only allow-list that fits Lead investigation.

*Later notes: `notes.d/O2/`, oldest first (`python tools/register.py show O2`).*

## 6. Engineering follow-ups (the M3 audits)

From `m3-audit-findings.md` and `m3-independent-audit-2026-09-29.md`, with the operator's and designer's dispositions of 2026-09-29. The findings fixed before the M3 review are recorded in those documents, not here.

<!-- columns: # | Work | Source | When | Notes -->

### E16

**Work:** Dashboard page-density and progressive-disclosure review

**Source:** Operator, 2026-10-03; `web/docs/design/plans/w03-journal.md`; [Work review](../../web/docs/reviews/page-density-2026-10-04.md), 2026-10-04; [cleanup plan](../../web/docs/design/plans/work-density-cleanup.md)

**When:** **Unscheduled** (the web developer's bounded passes): work checkpoint 1 merged (PR #52, 2026-10-04); further density work remains planned

**Notes:** Operator authorized incremental improvements, 2026-10-04. First checkpoint implements PD-04 child-results navigation/out-of-page labeling and small PD-01/02 content-first/disclosed metadata/copy ownership improvements. Independent review requested two phone focus/scroll corrections (F1/F2); corrections and exact-source evidence are in `web/docs/reviews/work-density-checkpoint-1-correction.md`. Operator reported reviewer approval, 2026-10-04; all CI passed and PR #52 merged at `4f0a710`. Original reviewer reports are preserved without manufacturing a new review artifact. PD-03 results setup and further detail organization remain separately planned; broader dashboard review Unscheduled, ownership pending. Preserve all features/contracts. Deferred from W03; no Engine records.

*Later notes: `notes.d/E16/`, oldest first (`python tools/register.py show E16`).*

### E3

**Work:** Watch CI for load-sensitive timing

**Source:** audit T2

**When:** **Unscheduled** (ongoing)

**Notes:** The step-3 case was a real race (M3-D11, fixed), and so was a run reported `lost` while it ended, on `main` after PR #7 (fixed: ADR-0009 amendment 2026-10-01, the heartbeat continues while a run ends). The launch acknowledgement wait (`AEW_LAUNCH_ACK_S`, 90 s) has timed out once, under two concurrent suites. `test_a_run_that_takes_long_to_end_is_not_reported_lost` failed once under coverage on 16 workers (M4-A, 2026-10-03): its 2 s stale window left 1 s over the 1 s beat; widened to 4 s, with the wait at 8 s. A run reported `lost` while it started (Windows, PR #132, 2026-10-09) was a real race too: its first record came before its first heartbeat (fixed: ADR-0009 amendment 2026-10-09). A single-run `aew harness wait` that returned a run still `running` (four CI failures in three adversarial tests, 2026-10-06 to 10-08, Linux and Windows) was a regression from wait-any (M4-D6, PR #79): its control lane, meant for `--any`, ended a single-run wait before the supervisor had written the run's end (fixed 2026-10-09: the control lane is `--any`'s only). A supervisor wedged while starting kept its heartbeat fresh with no limit, so a single-run wait read `starting` until its own timeout (noted by the independent review of PR #147, not seen in CI). The start now has a deadline, by default the sandbox self-test's and the harness adapter's own launch bounds plus 60 s (620 s for OpenCode at its defaults; `AEW_RUN_START_S` overrides it), so a wedged start reads `lost` within the deadline plus 10 s and never becomes `running` (ADR-0009 amendment 2026-10-09, a run's start has a deadline). A failed harness test now reports and keeps its runs' record and logs (testing strategy §3, 2026-10-09), so the next such failure names a stall (`lost`) or a crash. `test_a_waiter_parses_no_control_state_between_commits` (OBX-38) failed on a loaded Windows host, alone at `main` and once under 8 workers in PR #149's review (2026-10-09): its 4 s wait closed before the Ticket's commits landed, so only the initial read was counted. Fixed test-side: the commits land after the waiter's initial read, the test waits until the waiter has parsed the last of them, then ends the wait through a run's record; it counts parses against the commits' revisions, with no time window. Raise or restructure test-side timing, never the product's.

*Later notes: `notes.d/E3/`, oldest first (`python tools/register.py show E3`).*

### E4

**Work:** A scheduled live smoke run against the pinned OpenCode

**Source:** audit T4

**When:** **Unscheduled** (the operator's choice)

**Notes:** Launch-time capability probes already fail closed on drift within V2.

*Later notes: `notes.d/E4/`, oldest first (`python tools/register.py show E4`).*

### E6

**Work:** Let `whoami` through a run's bridge while a long `check.run` holds it

**Source:** audit A3

**When:** **On measured need**

**Notes:** Serializing a run's requests is conservative and correct.

*Later notes: `notes.d/E6/`, oldest first (`python tools/register.py show E6`).*

### E14

**Work:** CLI fixed cost: import `jsonschema` lazily, so commands that validate nothing do not pay for it

**Source:** a follow-up recorded during M3; `m3-performance.md` (the libyaml half is done there, P1)

**When:** **On measured need**

**Notes:** The bare CLI floor (`aew --version`) is 0.10 s on the M3 machine.

*Later notes: `notes.d/E14/`, oldest first (`python tools/register.py show E14`).*

### E18

**Work:** Transaction outbox: committed events atomic with the commit, durable consumer cursors, at-least-once idempotent consumers, bounded retention under ADR-0011; consumers wait-any (E1), the dashboard, knowledge capture, the scheduler

**Source:** [ADR-0012](adr/0012-transaction-outbox.md) (accepted 2026-10-04; ledger OBX); architecture review G11, K2; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05) D-AR3

**When:** **Unscheduled** (M4-D)

**Notes:** The transition log is the outbox: typed events derived in the store (so direct `Session.commit` sites are covered), `aew history log --since R` with the revision as the cursor, an advisory wake file, a 4,096-revision window sealed into 256-transition segments and never discarded, a hash chain. It meets the lead developer's review: an oversized transaction's full event list goes to an immutable staged sidecar that `last_transition` names and hashes. Ships with M4-D's schema decision (D10). **Status (2026-10-05):** partly built. Slice D1 (PR #53): typed events, the overflow sidecar, `aew history log` and its reader, the wake file, the hash chain. Slice D2 (PR #60): sealing into segments and `aew history compact`, doctor's window check, readers that resolve sealed segments, oracle rules 27 and 28, the git-cost measurement, and the fixes from the independent review of D1. The consumers (E1's wait-any, the dashboard endpoint, capture, the scheduler) and the `queue.*` kinds remain

*Later notes: `notes.d/E18/`, oldest first (`python tools/register.py show E18`).*

### E19

**Work:** A machine-readable amendment index beside `spec-pin.yaml` (each amendment, the sections it replaces, adoption date, a test that citing texts cite the amendment); after M4 a consolidated WC/KC re-freeze that also retires documents the ADRs absorbed

**Source:** architecture review G6, §9; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05) D-AR7; [spec amendment index design v0.2](../design/proposals/spec-amendment-index-design-v0.2.md) (design frozen, proposed; ledger SAI)

**When:** **Unscheduled** (the index); the re-freeze after M4-E and before internal alpha

**Notes:** The design (its [T7 index](../archive/reviews/architecture-review-2026-10-04/t7-amendment-index.md) and the [citation test run](../archive/reviews/architecture-review-2026-10-04/t7-citation-test-results.md) are archived: the index touches a third of all contract citations; the naive rule is noise, the refined topic rule found exactly one real defect, the acceptance guide's AT-9 row, closed as E38): `docs/spec-amendments.yaml` resolves the effective WC/KC section (frozen base plus adopted overlays; `design_frozen` never counts), unversioned citations mean the effective section, structural tests in `test_spec_amendments.py`. Its first slice also writes the missing Ticket-revision contract amendment (F4). **Designer (2026-10-05):** the re-freeze also consolidates WC §15.6 with the governing typed Lead surface v0.2 (MCP as the first normal transport; the CLI as parity, recovery and conformance). ARV-03, retiring the documents the ADRs absorbed at the re-freeze, is this row's (operator, 2026-10-05). **The index part is done (PR #73):** [`spec-amendments.yaml`](../spec-amendments.yaml) indexes three adopted overlays (the Class 0 amendment and its §9, replacing WC §7.4's Class 0 bullet and example, WC §7.5's Class 0 path and KC §26's parent-risk case; the typed Lead surface v0.2, extending WC §15.6), the effective sections and the Ticket-revision debt, and `test_spec_amendments.py` checks it structurally and that every citation names a real frozen section (SAI-14: no topic heuristic). **The Ticket-revision contract amendment is adopted (E19-B v0.4, operator, 2026-10-06, [amendment](../design/workflow-contract-amendment-ticket-revisions-2026-10-06.md)):** a fourth overlay extending WC §7, §8 and invariant 7 and KC §12, so the index's pending debt is empty. The row stays open for the re-freeze, which also replaces an external example project's name in the frozen texts with neutral wording (operator, 2026-10-06). **Editorial lines for the re-freeze ([agent-effectiveness adoption](../design/decisions-2026-10-09-agent-effectiveness-adoption.md), 2026-10-09; synthesis §7, AES-14; record §15, AEA-41 to AEA-43):** the KC §15.4 locations delivered as labelled locators; independent review excludes the implementer's working state; a role's handoff note is a bounded claim for its successor; and the designer's F4 ruling that moving a committed Ticket to another parent needs a replacement, while KC §9.4 promotion is a distinct operation

*Later notes: `notes.d/E19/`, oldest first (`python tools/register.py show E19`).*

### E22

**Work:** A `doctor` check that the supervisor heartbeat's staleness limit exceeds the measured re-parse on this host

**Source:** architecture review I9; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05)

**When:** **On measured need**: after large-host re-parse bounds are measured

**Notes:** |

*Later notes: `notes.d/E22/`, oldest first (`python tools/register.py show E22`).*

### E23

**Work:** Measure Windows coverage too and combine it with Linux, in the nightly `reference` run, not the merge gate

**Source:** architecture review I10; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05); [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) P5.2, §5

**When:** **Unscheduled** (decided: the nightly, by the operator, CI redesign P5.2, 2026-10-06); to build

**Notes:** Job objects, console and file-replace retries are outside the number today. The merge gate would roughly double the Windows lanes and time out integration (measured on PR #69, closed); a shard has no room for it. A temporary placement for today's cost, revisited after P3 (E42)

*Later notes: `notes.d/E23/`, oldest first (`python tools/register.py show E23`).*

### E24

**Work:** Typed record models generated from the JSON schemas at build time, or checked `TypedDict`s

**Source:** architecture review §4.1; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05) 5.3

**When:** **Unscheduled**

**Notes:** No runtime dependency

*Later notes: `notes.d/E24/`, oldest first (`python tools/register.py show E24`).*

### E25

**Work:** A real Rocky 8 CI and live lane (self-hosted, real 4.18 kernel) for the containment lane and the live smoke run

**Source:** architecture review §4.1; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05) 5.5

**When:** **Unscheduled** (depends on available infrastructure)

**Notes:** Run by hand on the operator's VM today

*Later notes: `notes.d/E25/`, oldest first (`python tools/register.py show E25`).*

### E27

**Work:** OpenTelemetry-shaped local spans for commands and runs

**Source:** architecture review §4.1; [architecture review response](../design/architecture-review-response-2026-10-04.md) (accepted 2026-10-05) 5.8

**When:** **Unscheduled** (probe): only with a concrete consumer and an air-gap-safe retention plan

**Notes:** |

*Later notes: `notes.d/E27/`, oldest first (`python tools/register.py show E27`).*

### E31

**Work:** An in-process `Engine` test driver for the non-CLI parts of the dispatch and integration flows, so those lanes stop paying a process per step

**Source:** independent reviews of dispatch legality (note 6) and of integration and publication (note 10), 2026-10-03

**When:** **Unscheduled** (efficiency)

**Notes:** One driver serves both; the dispatch set took 5 minutes and the integration set 7 on Windows. The CLI conformance tests stay as they are

*Later notes: `notes.d/E31/`, oldest first (`python tools/register.py show E31`).*

### E33

**Work:** Consider credentials written as UTF-16 (transcripts on Windows) in the end-of-run credential scan

**Source:** independent review of authority and custody, note 5, 2026-10-03

**When:** **On measured need**

**Notes:** The streaming half is closed (§9, 2026-10-09); the scan matches the credential's ASCII bytes only

*Later notes: `notes.d/E33/`, oldest first (`python tools/register.py show E33`).*

### E35

**Work:** OpenCode support qualification and adapter seams: `codemode: false` on the Lead's AEW MCP server, with readiness checked through the broker (a missing server fails the Lead closed, never a session without AEW's control surface); `execute` and the desktop `browser` namespace denied explicitly in worker runs; a probe of whether `OPENCODE_DISABLE_PROJECT_CONFIG` also excludes `.opencode/` plugins and the remote `.well-known` layer; a "nothing else loaded" conformance scenario on the model-visible request; `tool_output` limits; `HarnessAdapter.capabilities()`, named `LaunchContract` fields (`skills`, `tools_allowed`, `native_sandbox`) and a native-sandbox label line

**Source:** [harness-native integration research v0.3](../research/harness-native-integration-research-v0.3.md) (ledger HNI)

**When:** **Now**: the worker-run parts; the Lead MCP parts land with F15's typed surface

**Notes:** Codex qualification is F24; the capability registry is F13. ARV-05 (operator, 2026-10-05): whether the current OpenCode release still fits is this row's question. **M6a native edit/write decision (v0.9 §7, approved by the designer, D1 2026-10-10 (MCD-01, MCD-02); takes effect at M6; F40):** whether OpenCode's native `edit` and `write` can be hidden or denied in the worker's model-visible schema, not only refused when called, is first established in the worker profile here; shell writes are stopped by the read-only source, and the shell is kept; a cross-reference, not new scope

*Later notes: `notes.d/E35/`, oldest first (`python tools/register.py show E35`).*

### E39

**Work:** The requirements-ledger gate identifies a source's sections by document plus a hierarchical or explicit anchor instead of requiring every heading string in a document to be unique, so a repeated heading no longer forces an editorial rename

**Source:** Designer, 2026-10-05 (on the two heading disambiguations of the documentation consolidation, accepted as editorial)

**When:** **On measured need** (the next repeated heading in a source)

**Notes:** The gate is `tests/unit/test_requirements_ledger.py`; the ledger's `section:` field is the heading text today

*Later notes: `notes.d/E39/`, oldest first (`python tools/register.py show E39`).*

### E42

**Work:** CI redesign P3, shared setup: an in-process CLI driver for setup steps (isolated per invocation: the guards that fail a test leaking `AEW_*` variables or a changed working directory apply to every invocation, and it saves and restores cwd, environment, standard streams, logging, parser and module globals, thread locals and context variables, non-project caches, proven by its own tests) and snapshotted starting states (an immutable per-worker template from a declared, checked quiescent and relocatable state; each test an independent copy, worktrees repaired and paths rebound), each helper switched only after one semantic-equivalence oracle shows the same state both ways; then the expensive families migrated one at a time

**Source:** [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) P3, §5 (ledger CRD-05 to CRD-09)

**When:** **Unscheduled**: after E43 and E44 (design §5, steps 4 and 5, then P3 as step 6)

**Notes:** The strategy rule it needs is amended in `testing-and-ci-strategy.md` §6 (2026-10-06). Expected 40 to 50% off the slow scenario files; it is what stops the suite's cost growing faster than the product. The integration lanes ran 21 to 26 of their 30 minutes, and `main`'s run for `389e32d` timed one out (30m45s, 2026-10-06)

*Later notes: `notes.d/E42/`, oldest first (`python tools/register.py show E42`).*

### E46

**Work:** Sweep the current fast-lane outliers (a 33.5 s randomized crash test, several 5 to 7 s surface-runner tests) and investigate the store crash slowdown (1 to 7 minutes before the outbox, over 60 after) as a performance regression, never by a bigger budget

**Source:** [cost-detection investigation](../research/ci-cost-detection-investigation-2026-10-06.md) §5.3; [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) §4 (ledger CCI-03, CRD-14)

**When:** **Unscheduled**, after E43, from its record

**Notes:** `CLAUDE.md`: a slower test is a regression to find, not a timeout to raise

*Later notes: `notes.d/E46/`, oldest first (`python tools/register.py show E46`).*

### E52

**Work:** Stop rebuilding a module-scoped fixture in every shard that runs one of its tests. The row's first part, finding why Windows serial tests became 1.75 to 1.9 times slower in the nightly `reference` run from 2026-10-05, is answered (Notes)

**Source:** [Testing and CI strategy](testing-and-ci-strategy.md) §8 and §12 (measured on the 2026-10-04 to 10-09 nightlies)

**When:** **Unscheduled**

**Notes:** First part answered (investigated 2026-10-09, A/B collected 2026-10-10): host variation plus code growth, not a dependency. The 10-04 baseline ran on an unusually fast runner (`westus3`): roughly 1.32 (that host) × 1.26 (code growth, also in the PR lanes) × 1.12 (variation between nightly hosts) ≈ 1.87. Against the PR runs at the same commits the nightly moved only within host variation (median per-test nightly/PR ratio 0.62 to 0.66 before, 0.66 to 0.82 after: about 1.14 on average, up to 1.3 on one night), nowhere near 1.87. The suspected `rpds-py` upgrade (2026.6.3 to 2026.9.1) is cleared: a CI A/B ran both versions on each of 3 Windows runners (run 38017570085) and measured a same-host ratio of 1.06 (95% CI 0.99 to 1.14; 1.04 adjusted for run order), inside one host's run-to-run spread of up to 12 %, while the hosts differed by up to 1.29 times. No pin. **From now on, compare Windows `reference` timings against the PR run at the same commit, or against the median of several nightlies, never against a single nightly.** A follow-up is merged: #157 removed the runtime `check_schema` of AEW's own schemas (about 220 ms per CLI call). The second part stays open: a module-scoped fixture is still rebuilt in every shard (testing strategy §12)

*Later notes: `notes.d/E52/`, oldest first (`python tools/register.py show E52`).*

### E53

**Work:** PR test selection (operator, 2026-10-09): pull requests run less only fail-closed, `main`'s push run and the nightly stay full. Phase 1a, the `fast` tier (docs plus fast-lane test modules and `tests/durations.json`: `core`, `static`, `web`'s gate, `fastbase` and `assurance`, no heavy lane), is **built in shadow**: the tier, the runtime lane check and the same-run coverage premise are computed and reported on every eligible run, which stays full. Still to do: enforce it (PR 1b, `tier.MODE = "enforce"`)

**Source:** [Testing and CI strategy](testing-and-ci-strategy.md) §3 (CI plan v7, reviewed CLEAR 2026-10-10)

**When:** **Unscheduled**: PR 1b once at least 5 eligible shadow runs decided correctly, the premise check ran in each with no unexplained loss, and the unit-isolation audit (`unit-isolation-audit.yml`, dispatched once) is clean

**Notes:** Deferred behind their gates (plan v7 §9): Phase 1b, heavy-closure selection (Phase 1a enforced for four weeks with no confirmed miss, and PR runs whose only non-`fast` changes are heavy test modules or helpers saving at least 3 % of PR runner-minutes; then the v2 review's entry conditions V2-1, V2-2, V2-3, V2-5, V2-7 and V2-10), and Phase 2, the coverage map (the earlier phases in service with no miss, queue delay above 10 minutes, a refreshed marginal estimate of at least 8 %; entry condition V2-8). Expected saving of Phase 1a: about 12.5 % of PR runner-minutes on the 27-PR sample (#117, #119, #120 and #145)

*Later notes: `notes.d/E53/`, oldest first (`python tools/register.py show E53`).*

### E54

**Work:** OpenCode 2.0.18's `steps` resets at each promoted input (`harness send`, F9 messages): the operator-adopted `max_steps` (a legality-classed key) bounds each delivered input, not the run. Options: accept for now (the run's deadline is run-wide and binds every run), or have the adapter enforce a run-wide count (count `session.step.started` and interrupt at `max_steps`) under its own plan

**Source:** F9-A MS0 probe, 2026-10-10 (`p2-steps-none` against `p2-steps-steer`; [evidence](adr/evidence/f9a-delivery-probe-2026-10-10/probe-results.md)); [ADR-0010](adr/0010-execution-profiles.md); [harness conformance](harness-conformance.md) §5; [ADR-0017](adr/0017-coordination-messages.md) D8, the step-limit residual (ledger CMG-31)

**When:** **On measured need**: the operator decided 2026-10-10 to accept the behaviour for now, with no cumulative hard step cap yet; revisit under ADR-0010

**Notes:** Not an F9 question: F9-A adds no new capability (`harness send` has restarted the counter since M3), only volume, which its caps bound weakly; U1 is observation-only, so it cannot host enforcement. AEW already treats a changed step limit as access-widening (the adapter's projection check refuses one), so the gap belongs to ADR-0010 and the harness. F9-A did not wait for the answer

*Later notes: `notes.d/E54/`, oldest first (`python tools/register.py show E54`).*

### E71

**Work:** The M4 operator guide: a guide under `docs/guides/` for what M4 built, which today's guides (M1 to M3) do not cover: the typed Lead tools and `aew lead tool`; the operator endpoint, steering (Crawl/Walk/Run, the steering loop) and the operator notifier; concurrency and the integration queue (`defer`, `requeue`, `reorder`, the breaker); VALIDATE_ONLY and the custody worker; checks-mode validation (Linux only); `aew stage continue|abandon` and dispositions; `aew map`, raw-history search and F9 messaging; the containment labels per platform; usage (no `aew usage` command yet, and a price table needs a `policy.pricing` entry that `aew init` does not write); and a dashboard guide, of which there is none. It also corrects what is wrong today: `opencode.md`'s containment section still says every run is workdir separation only, stale for Linux; the dashboard's default port (4280) is undocumented; and Class 0 integration needs the CLI (`ticket_draft` cannot create a Class 0 Ticket, and `ticket_prepare` requires Ticket-level verification evidence), which no guide says

**Source:** The operator's request of 2026-10-11; `docs/guides/` (M1 to M3 only)

**When:** **V-01.** At M4-E's closeout, written after the operator's M4 UAT round (2026-10-11) so that it covers what confused the operator there. Owner: the lead developer

**Notes:** The guide row owns the `opencode.md` correction, so no other change fixes it first. F20 has no dashboard guide; this row writes it

*Later notes: `notes.d/E71/`, oldest first (`python tools/register.py show E71`).*

### E72

**Work:** The Windows integration shards run close to their bound: a fifth Windows integration shard, or a faster integration suite, so that a slow runner does not reach the session deadline. Each of the four shards has a job timeout of 34 minutes (the pre-G3a 30 plus the session deadline's clearance), and its pytest session deadline is 1800 s after the job starts (`--session-deadline 1800`)

**Source:** `main`'s push runs: the job wall times from the Actions API, and the per-shard pytest session times from each run's `cost-record` artifact (`platforms.win32.shards[].session_wall_s`); `.github/workflows/ci.yml` (`lanes`, the `windows-latest` integration entries, the 34-minute timeout and the 1800 s session deadline)

**When:** **Unscheduled**: waits for the operator's decision (decisions-due). Owner: CI capacity. The Lead recommends a fifth shard

**Notes:** Confirmed by the review of #223 from the Actions API and `ci.yml`: the Windows integration jobs took 17.0 to 26.6 minutes across runs 38271888021 (`938772c`), 38261462556 (`e69313b`), 38285596692 (`2129ac1`) and 38291227264 (`977d685`), against a 34-minute job timeout and an 1800 s session deadline. Per-shard pytest session times, from the `cost-record` artifacts (copied here because the artifacts expire after 7 days), in minutes: 17.1 to 25.3 on `938772c`, 20.9 to 25.5 on `e69313b`, 16.5 to 26.0 on `2129ac1` and 18.7 to 25.8 on `977d685`. A fifth shard adds one job per full run under the 40-job cap, so it falls under the operator's CI-capacity decisions. A faster suite is the other route ("a slower test is a regression to find, not a timeout to raise")

*Later notes: `notes.d/E72/`, oldest first (`python tools/register.py show E72`).*

### E73

**Work:** The dashboard's registry reader treats `FileNotFoundError` as absent at once: `MapsReader.registry()` in `src/aew/dashboard/reader.py` (lines 224 to 250 at `977d685`) returns `NONE` on the first `FileNotFoundError` (lines 236 and 237), although it already retries a `PermissionError` on Windows (lines 242 to 246). On Windows a file in the middle of a writer's replace can be reported missing, so a present registry reads as absent. The fix is to converge on the store's one owner of lock-free reads, `aew.engine.store.read_lock_free`, which #220 adds with its retry of a missing file gated to Windows, once #220 merges, instead of keeping a second retry here

**Source:** The review of #220 (F46.1 slice F1a): under a real replace loop, the configuration projection's lock-free reads reported a present file missing in 314 to 726 of about 24,000 reads per run until the owner retried `FileNotFoundError` as well

**When:** **Unscheduled.** Owner: the dashboard API lane; after #220 merges

**Notes:** The reader-side member of one class: readers and scanners that do not go through the one owner. E76 is its test-side twin, the writer's replace racing a raw read; E74 is the same class in the code-registry scan

*Later notes: `notes.d/E73/`, oldest first (`python tools/register.py show E73`).*

### E74

**Work:** G2's code-registry scan resolves a module constant's name only where a code is passed as a call argument, so a code written through a constant anywhere else is invisible to it. `code_write_sites` in `tests/unit/test_discovery_registry.py` (at `977d685`) resolves names only for the arguments of callables that take a code (lines 65 to 76). A dict literal's `"code"` value, a `code=` keyword elsewhere, a class's `code =` and an `x.code =` assignment are read only as literals (lines 79 to 93), and `module_constants` binds only plain assignments (`ast.Assign`), so it misses constants assigned by tuple unpacking (`A, B = "A", "B"`) and annotated constants (`NAME: str = "X"`). The class is open on `main`, not only in #220. Five codes on `main` are written only through a module constant in a dict's `"code"` value; the scan does not see them, and the registry has no row for any: `GUARD_QUERY_DEFECT` (`src/aew/engine/guards.py:133`, constant at `:45`); `UNVERIFIED_ENTRIES_OVER_POLICY`, `UNVERIFIED_AGE_OVER_POLICY` and `FULL_VERIFICATION_OVERDUE` (`src/aew/engine/history_ops.py:550`, `:554`, `:567`, bound by tuple unpacking at `:65`, so both forms at once); and `RESOLVE_STAGE` (`src/aew/surface/availability.py:263`, constant at `:35`). G2 brings each into the scan and the registry, or excludes it explicitly. The fix is to resolve constant names wherever a code is written, proved by a planted test for each form: a dict value, a `code=` keyword, a class's `code =`, an `x.code =` assignment, a tuple-unpacked constant and an annotated constant

**Source:** The review of #223: an AST enumeration of every non-literal `code` write and every module string constant `module_constants` does not bind, over `src/aew` at `977d685`, then the merged scan (`code_write_sites`) and the registry run against the codes it found. The other non-literal forms it found are out of the class: attribute reads (`exc.code`) re-emit a code written as a literal where it is defined, and dynamic values (variables, `x["code"]`, `.get(...)`) carry no constant. Also #220 (F46.1 slice F1a), whose data codes add more members once it merges: `UNPROCESSABLE` in a dict literal's value, `NO_SUCH_PROFILE` and `NO_DEFAULT_ROUTE` bound by tuple unpacking, and the schema-keyword codes. #218 (G2) closed the same class for the call-argument form

**When:** **Unscheduled.** Owner: G2 (the discovery lane)

**Notes:** A silent gap: a code the scan cannot see fails no test, so a code missing from the registry passes. The same class as E73 and E76 (a reader that does not go through the one owner)

*Later notes: `notes.d/E74/`, oldest first (`python tools/register.py show E74`).*

### E75

**Work:** A wall-clock flake: `tests/integration/test_notifier.py::test_broker_liveness_is_local_and_beats_every_poll[wedged_watchdog_is_stale]` failed its healthy, pre-wedge assertion (line 258): `broker_liveness.judge()` returned stale ("the broker's watchdog has not completed an iteration for 1.2s (past 1.0s, its lock timeout plus 2 x POLL_S)"). The wedged case sets the store's `lock_timeout` to 0.5 s, so a healthy watchdog iteration that takes longer than 1.0 s on a loaded runner reads as stale. The fix is to prove the ordering with events or a controlled clock, never by comparing wall time with a threshold

**Source:** Run 38291135208, attempt 1 (`aa7e4d7`, the run of #221), `core (windows-latest)`, the serial lane; attempt 2 passed

**When:** **Unscheduled.** Owner: the hang-and-flake diagnosis plan, as the first wall-clock entry of its flake register (G3c); E3 holds it until that register exists

**Notes:** A test that fails and then passes on a re-run is a defect to investigate. The flake register closes an entry only with a named root cause and a test that reproduces it deterministically, by event or fault injection

*Later notes: `notes.d/E75/`, oldest first (`python tools/register.py show E75`).*

### E76

**Work:** A test helper reads control state raw while the engine replaces it: `tests/helpers/invariants.py`'s `load_control` (lines 39 to 41 at `977d685`) calls `Path.read_bytes` on `.aew/state/control.yaml`. That is a raw read racing the writer's replace, the Windows sharing-violation class. The fix is to route every test-helper read of control state through the one owner, the store's lock-free reader: `Store.read_committed` (`src/aew/engine/store.py:343-360`) today, which already retries a read that collides with the replace on Windows, and `read_lock_free` once #220 merges, for `project.yaml` and for reads that need the bytes. The hang-and-flake plan's test-helper retry (G3b, W1) is only for files outside the store's ownership. **Boundary: `tests/helpers`**, where the list is complete: `invariants.py:41` and `vertical/scripted_operator.py`'s `stage_intents` (lines 428 to 430: `exists()`, then `read_text`, of `state/control.yaml`), and the same shape outside `state/`, `invariants.py:138`, which reads `.aew/project.yaml`. **Test modules outside `tests/helpers`** hold 30 more raw `control.yaml` reads and 7 raw `project.yaml` reads. The rule for them is the row's own: a read moves to the owner only when a writer of the file can run during it. Three can, and move: `tests/integration/test_notifier.py:142` and `:146` (the operator endpoint `serve()` started holds an engine and can commit) and `tests/integration/test_harness_send_when.py:75` (around `harness send`, with the run's supervisor live). They compare bytes to prove nothing was written, so they take the owner's bytes reader (`read_lock_free`). The other 27 `control.yaml` reads stay raw, because no writer runs during them: `tests/integration/test_notifier.py:304` (after `broker.close()`); `tests/unit/test_notify.py:308` (before `watcher.start()`) and `:319` (after `watcher.close()`, and the watcher never commits); reads of a quiescent project or a bare store, `tests/acceptance/test_at4a_at7.py:57`, `tests/integration/test_authority.py:19` and `:398`, `tests/integration/test_coordination_store.py:95`, `tests/integration/test_guard_queries.py:610`, `tests/integration/test_migration.py:223`, `tests/integration/test_dashboard_api.py:536`, and `tests/unit/test_store.py:51`, `:55`, `:177`, `:186`, `:244` and `:254`; deliberate edits of the state (rewriting it to v1, corrupting it, injecting garbage), `tests/integration/test_dashboard_history_search.py:294` and `:362`, `tests/unit/test_store_cache.py:48` and `tests/integration/test_history_search.py:233`; beside a read-only dashboard server while the test holds the control lock, `tests/integration/test_dashboard_history_search.py:776` and `:780`; and before and after in-process commands, `tests/integration/test_history_search.py:632` and `:634` and `tests/integration/test_map_context.py:283`, `:285` and `:289`. The 7 `project.yaml` reads are manifest edits or reads of a quiescent project and stay raw: `tests/integration/test_authority.py:66` and `:294`, `tests/integration/test_history_search.py:216`, `tests/integration/test_stage_intent.py:162`, `tests/integration/test_usage_ledger.py:56` and `tests/regression/test_m4_control_state.py:28` and `:33`

**Source:** `main`'s push run 38291227264 (`977d685`), attempt 1, `integration 3/4 (windows-latest)`: `tests/integration/test_integration_stages.py::test_broker_spawned_custody_worker_registers` failed with `PermissionError: [Errno 13]` on `.aew/state/control.yaml`. Call path: `test_integration_stages.py:590` (the `_wait_for` condition, line 572), then `control` (line 81), then `invariants.py:41` `load_control`, then `Path.read_bytes`. The inventory comes from the review of #223, at `977d685`: a syntax-tree pass over every `.py` under `tests/` for `control.yaml` and `project.yaml`. For each `read_bytes`, `read_text` or `open` call, it resolves a bare-name receiver to its last assignment earlier in the same function. Its limits: it does not follow a path across functions (one passed in or returned is found only where it is built) or through containers. It found 40 reads: 3 in `tests/helpers` (2 of `control.yaml`, 1 of `project.yaml`) and, in test modules, 30 of `control.yaml` and 7 of `project.yaml`. An earlier one-line search had found only 15, because it missed every read through a variable

**When:** **Unscheduled.** Owner: the test helpers; the reads that need the bytes wait for #220

**Notes:** The test-side twin of E73: the same class, readers that do not go through the one owner. E74 is the same class in the code-registry scan

*Later notes: `notes.d/E76/`, oldest first (`python tools/register.py show E76`).*

### E79

**Work:** Enumerated-domain guards: a change to an enumerated domain triggers every applicable domain guard. The guards' dependencies are derived and validated from the authoritative domain owners and the actual consumers, using F44's owner registry where appropriate. An existing test enumeration alone is not proof of complete coverage

**Source:** Designer ruling, 2026-10-12, C3 (approved with amendment)

**When:** **Unscheduled.** Owners: the domain owners and their guards, with F44 (the consequential-fact owner registry). Under the ruling's S1, it is not an A1 vertical-recovery gate dependency

**Notes:** F44 records each fact's owner and consumers; this row uses that record to decide which guards a domain change must run, rather than restating the dependencies by hand. The derived and validated "pins" relationships between tests and what they cover, with demonstrated detection of a missing or stale relationship, are already placed under E53 (affected-test selection) and F22.3's test relationship index (batch-3 ruling #30); this row builds on them and does not restate them

*Later notes: `notes.d/E79/`, oldest first (`python tools/register.py show E79`).*

### E81

**Work:** One bytes-level reader for kernel and OS text files (`/proc` and `/sys` records, mount tables, routing tables): it reads bytes, splits on `b"\n"` only, validates each record against its source's fixed format, and fails closed on a record it cannot parse. #250's mode check extends to the split. The method that closes the class, after three findings of it in one night

**Source:** Review findings #250 M1 and M2 (a comm read with `str.splitlines` could forge a line), a finding of the same class in #243 (closed unmerged), and #244's inventory (2026-10-24)

**When:** **After the trace.** Until it is built, containment builder briefs carry the rule: read such files as bytes and split on `b"\n"` only

**Notes:** Parked by the Lead on 2026-10-24 during the build freeze; the triage of stranded insights (design workspace, ST-10) asked for this row

*Later notes: `notes.d/E81/`, oldest first (`python tools/register.py show E81`).*

### E82

**Work:** Prove the command set's fingerprint and its per-member order (CS-03, CS-05): a known-answer test of the SW-02 fingerprint, which G3-C binds consent to, and a two-member continuation set. Tests only

**Source:** STG-12's S12-4 trace, FIX claim "the set fingerprint and the per-member order are unproven" (`CLAIMS.yaml` at design workspace `18cdf63`, pack `290d5bca540f`); the claim's deviation is the brief

**When:** **Internal alpha**, one of the trace's FIX rows (S12-6). Before G3-C binds consent to the fingerprint

**Notes:** The designer asked for this row on 2026-10-25, with family 6's claims

*Later notes: `notes.d/E82/`, oldest first (`python tools/register.py show E82`).*

### E83

**Work:** Only the two declared steps auto-run, and only under RUN (R01-38, R-DEC-04): declare the set (`ticket_start` and `ticket_request_review`, under RUN only), and test that `classify.auto_runnable`'s set equals it

**Source:** STG-12's S12-4 trace, FIX claim "only the two declared steps auto-run, and only under run" (`CLAIMS.yaml` at design workspace `18cdf63`, pack `290d5bca540f`); the claim's deviation is the brief; the set is the operator's R-DEC-04 decision of 2026-10-25 (design workspace `e1f1920`)

**When:** **Internal alpha**, one of the trace's FIX rows (S12-6)

**Notes:** The designer asked for this row on 2026-10-25, with family 6's claims

*Later notes: `notes.d/E83/`, oldest first (`python tools/register.py show E83`).*

### E86

**Work:** The order of collection decides which `conftest` a helper imports. `tests/conftest.py` and `tests/discovery/conftest.py` both load as the module `conftest`, so a helper that runs `from conftest import ...` (`tests/helpers/vertical/scripted_operator.py`) gets the discovery one when `tests/discovery` is collected first in a session, and fails with an `ImportError`

**Source:** Seen locally on 2026-10-25, with `tests/unit/test_ci_tools.py` and `tests/discovery/test_static_texts.py` under `-n 4` in one session; reproduced at #277's head and at its base by #277's review (N4)

**When:** **Unscheduled**: no required lane collects `tests/discovery` with the other directories (`test_no_required_lane_collects_the_discovery_lane`), so only a local run that mixes them meets it

**Notes:** Filed by the Lead with #277, as its review's N4 asked

*Later notes: `notes.d/E86/`, oldest first (`python tools/register.py show E86`).*

### E87

**Work:** A promotion carries a dropped parent's obligations onto the promoted unit (`carried_obligations`) instead of being refused, as F4's plan v8 designs it (sections 3.3, 3.12 and 3.12a, which cover a Story or Epic move too). Since E84 (#274), such a promotion is refused, with the remedies its refusal names

**Source:** The designer's follow-on after E84, from the operator's decision on S12-4's first flags batch (design workspace `fb1fabe`, "a link the Lead needs"); FLAG-12 keeps `carried_obligations` for it under `EW-U05.g` (the second batch, design workspace `ca01a32`)

**When:** **Internal alpha**, beside the trace's flag work (S12-6): FLAG-12 clears when it is built

**Notes:** Filed by the Lead after #274 merged. The plan's design is its starting point, not its authority: F4 is held in HOLD-08

*Later notes: `notes.d/E87/`, oldest first (`python tools/register.py show E87`).*

### E88

**Work:** Remove nine reserved keys from `src/aew/schemas/ticket-field-registry.v1.json`'s bookkeeping list, as one change: FLAG-08's seven (`recorded_digests`, `revisions`, `revision_events`, `revision_impact_holds`, `revision_pending`, `revision_refusals`, `ticket_revision`) and FLAG-11's two (`hierarchy_baseline`, `coverage_obligations`). Check first that `coordination-message.schema.json`'s required `ticket_revision` field, which `coordination_ops` writes as null, does not rely on the registry's entry

**Source:** The operator's decisions on S12-4's flags: the first batch with its correction (design workspace `fb1fabe`) and the second batch (`ca01a32`)

**When:** **Internal alpha**, one of the trace's removals (S12-6)

**Notes:** Removing the reserved keys leaves F4 held in HOLD-08: removing the keys does not remove F4. Its registry, its digest functions, its plan and E19-B stay, and the registry's meta-test (invariant 50) makes each later F4 slice add its key back before writing it

*Later notes: `notes.d/E88/`, oldest first (`python tools/register.py show E88`).*

### E89

**Work:** Re-point `spec_set` at the published contracts once D-A's first publication lands (FLAG-09). Retiring it instead would need a schema change, since `control.schema.json` requires it, and a read-as for old state

**Source:** The operator's decision on S12-4's first flags batch (design workspace `fb1fabe`)

**When:** **Internal alpha**, one of the trace's changes (S12-6), once D-A's first publication lands

**Notes:** Filed by the Lead from the decision record

*Later notes: `notes.d/E89/`, oldest first (`python tools/register.py show E89`).*

### E90

**Work:** An authority check must not read a failed check as "authority held". `LeadBroker._authority_lost` and `SteeringLoop._authority_lost` both catch `AEWError` and answer "still the Lead", so a lock timeout hides a lost seat until a check succeeds. Find every such handler mechanically (a check over the `_authority_lost`-style handlers that catch `AEWError`, not one instance at a time), and surface the last swallowed error in the beat or heartbeat that R-DEC-03's supervision reads

**Source:** The root-cause analysis behind #276 (the notifier's superseded case); the second instance, found on 2026-10-25 and checked on `main`; R-DEC-03, the built supervision set (the operator, 2026-10-25, design workspace `e1f1920`); the designer's ask that the row say how every instance is found

**When:** **V-01**: its unattended mission relies on R-DEC-03's supervision

**Notes:** The engine still refuses a superseded broker's requests, so no authority is gained: the defect is a seat loss that goes unseen and unrecorded

*Later notes: `notes.d/E90/`, oldest first (`python tools/register.py show E90`).*

### E91

**Work:** A static check that every pin in `tests/platform-skips.yaml` sits under the platform its module's or test's `skipif` skips. A pin under the wrong platform turns `assurance` red only in CI

**Source:** The quick check of #269, which found skip pins under `linux` for tests skipped on `win32`; its reviewer proposed the check as the class's mechanism

**When:** **Internal alpha**

**Notes:** Filed by the Lead

*Later notes: `notes.d/E91/`, oldest first (`python tools/register.py show E91`).*

### E92

**Work:** Forward plain `http://` requests through the contained egress under the same R-6 host check, instead of refusing them. The proxy is CONNECT only, so CS-4 refuses them and names the https form

**Source:** CS-4's hand-off, addendum 1, section 4 (design workspace `146f204`); the designer accepted the refusal as a limit for CS-4 on the condition that this row is filed (2026-10-25); its target is the designer's ruling of 2026-10-25 on #280's targets

**When:** **Internal alpha**, after CS-4 merges: V-01's matrix names no step that needs plain `http://`, and the refusal already names the https form

**Notes:** It restricts nothing the threat model asks for (the designer)

*Later notes: `notes.d/E92/`, oldest first (`python tools/register.py show E92`).*

### E93

**Work:** Serve a stored OpenCode (Zen) key to the contained Lead: map each `opencode/*` model's catalogue address from a pinned copy of the catalogue, never the live one. Each such model carries its own address, so a provider-level override does not catch it, and AEW cannot see the live catalogue

**Source:** CS-4's hand-off, addendum 2, ruling 2 (design workspace `655930b`); its target is the designer's ruling of 2026-10-25 on #280's targets, which replaces addendum 2's

**When:** **Internal alpha**, if the need is measured by then: its ambiguity report marks it in scope only if a stored Zen key is in use, and deferred otherwise, with that reason. Until then CS-4 fails closed, with a message naming the provider

**Notes:** The builder's start line is its input (addendum 2); the Lead adds it as a note when the builder sends it

*Later notes: `notes.d/E93/`, oldest first (`python tools/register.py show E93`).*

### E94

**Work:** The web package refresh (S3), from a source commit the web developer picks

**Source:** The operator's decision of 2026-10-25 on the triage's ST-07 (design workspace `0d6292f`): it stays a target, as one row held in HOLD-12

**When:** **After the trace**, held in HOLD-12 (A-12). Not built before V-01, unless the operator moves it

**Notes:** Owned by the web developer. Its acceptance follows their S3 preparation checklist of 2026-10-11

*Later notes: `notes.d/E94/`, oldest first (`python tools/register.py show E94`).*

### E95

**Work:** `tools/register.py check` refuses a new row whose target is not a milestone (Contained, V-01 or Internal alpha) or After the trace, as the preamble's rule for a new row says. A row is new when its id is above a high-water id recorded from the rebaseline

**Source:** The review of #280 (M1), which found five new rows off the rule that `check` does not test; its reviewer proposed the check as the class's mechanism

**When:** **Internal alpha**

**Notes:** Filed by the Lead

*Later notes: `notes.d/E95/`, oldest first (`python tools/register.py show E95`).*

### E96

**Work:** A rework round never starts without recorded findings, by any route of Lead transitions out of a failed review (R1-D2), with the check that finds the class: over the transition table, every path of Lead-chosen edges from an origin whose direct edge to a target carries a named guard, through hubs and phase states alike and with no discharging engine event on it, runs that guard or its discharge. A planted path is found, and the run shows what it found

**Source:** The designer's ruling of 2026-10-25 on an observation from #279's review (E85), which reads R1-D2 as covering a route to its end; the record stays private

**When:** **Internal alpha**, the same milestone as E85. E85's named outcome, "the rework round runs with no recorded findings", is closed only when this row lands, and S12-4's E85 claim closes with both

**Notes:** The designer asked for this row on 2026-10-25

*Later notes: `notes.d/E96/`, oldest first (`python tools/register.py show E96`).*

### E97

**Work:** The provider relay's meter, one of A-42's two build items (MSN-00, MSN-R03): every paid route a mission's run can reach is metered from outside the metered lineage, and each paid call the relay observes is bound to the operation it was admitted under, so that usage is taken from the meter (MSN-12, R01-08; the rule's second half is MSN-12's)

**Source:** A-42, the bounded unattended mission, with the operator's option (a) (adopted on 2026-10-25, design workspace `b2ade18`; MSN-R03, MSN-Q10); R01-08, IF10-13

**When:** **V-01**, one of its build items. In the build order, after I-6 (STG-14), and before the qualification (E98), which judges it. Until both land, a built mission's cap is issued `COOPERATIVE` and reads `NOT_ESTABLISHED` (MSN-05); and until the build serves `MSN-00` to `MSN-12`, only `MSN-Q01`'s attended runs are missions (A-42, Not claimed)

**Notes:** Filed by the Lead. Held work on the same usage path: HOLD-20's F18.15 (gateway usage convergence) and HOLD-21's F25 (the cost ledger)

*Later notes: `notes.d/E97/`, oldest first (`python tools/register.py show E97`).*

### E98

**Work:** R-01's qualification of the paid class on a host and provider, one of A-42's two build items (MSN-00, MSN-05; R01-08, R01-09, R01-42, R01-43): where the class qualifies, a mission's cap is issued `MANDATORY_HARD`; elsewhere it reads `NOT_ESTABLISHED`

**Source:** A-42 with option (a) (design workspace `b2ade18`; MSN-00, MSN-05, MSN-R03, MSN-Q10); R01-08, R01-09, R01-42, R01-43, IF10-13

**When:** **V-01**, one of its build items, after the relay's meter (E97) and I-6 (STG-14)

**Notes:** Filed by the Lead

*Later notes: `notes.d/E98/`, oldest first (`python tools/register.py show E98`).*

### E99

**Work:** The offline install bundle. One manifest names every requirement: the Python wheels, the system packages per target operating system (for example `gtk3` and `python3-gobject` for the G3 confirmer), the pinned OpenCode build, ripgrep and the other base tools. Packaging downloads all of them into the bundle, built per target, and the install needs no network. A build's new prerequisite goes into the manifest. The intended install, one guided sequence that asks for root once: (1) unpack and verify the signed manifest (ADR-0014), then install AEW into its own environment and run a preflight that lists each prerequisite as found or missing, with the exact command, offline; (2) the system part as root (the bundle's system packages, then G3, its confirmer and their units: `g3/install.sh`, called for the operator); (3) the operator sets the PIN at their own terminal, handed to `aew-g3 set-pin`, which the installer never sees; (4) the self-tests, ending in one screen with each piece green or red. It resumes at the first unfinished step, refuses its root and PIN steps inside an AEW-contained session and names the operator's step to run at their own terminal instead, and ends with what was installed, where, and how to undo it

**Source:** The install and bootstrap UX v0.3, sections 5 and 5.1 (ledger IBU-12, IBU-13), and ADR-0014 (the signed manifest, verified before anything is consumed), whose build is held in HOLD-17 as F18.3 and D2; brought forward to Internal alpha by the operator's decision of 2026-10-25, in chat, on G3-B's system packages (packaging bundles every requirement for an install with no internet), and extended by the per-target system packages and the guided sequence, the Lead's sketch of the same day

**When:** **Internal alpha**, as its packaging (the milestone's "an install the operator can run on their own machine and on a managed Linux host"). The designer designs it, by Internal alpha. F18.3 and D2 stay held in HOLD-17; E99's design takes IBU-12, IBU-13 and ADR-0014 as its inputs, and names at the group's exit how F18.3 and D2 are absorbed

**Notes:** Filed by the Lead. `g3/requirements-offline.txt` is the offline manifest the bundle's one manifest absorbs. Closest mechanisms today: CAP-1's capability register (STG-15) and H-3's bundle import (E35). Its decisions-due item waits until `test_register` admits a new item (#285's review, m5): the next register batch

*Later notes: `notes.d/E99/`, oldest first (`python tools/register.py show E99`).*

### E100

**Work:** An explicit `required` containment mode on a host that cannot meet it refuses the launch, on every platform. An unset mode still runs weaker, and its label's `weaker_because` names the platform

**Source:** The designer's decision of 2026-10-25, `30-stages/STG-05-agent-containment-build/handoff/RESPONSE-E100-required-on-an-unqualified-host-designer.md` in the design workspace

**When:** **Internal alpha**, before the Windows trial: a build row; it needs a builder after CS-4 merges

**Notes:** Filed by the Lead. Its decisions-due item waits until `test_register` admits a new item (#285's review, m5): the next register batch

*Later notes: `notes.d/E100/`, oldest first (`python tools/register.py show E100`).*

### E47

**Work:** Triage every failed `main` run by cause: a job that timed out raises attention (as #92 made the nightly do), a superseded run does not; a red full run after a reduced-tier merge is a tier-classification defect, fixed in the classifier with a test pinning the case; repeated wall-clock violations on `main` open or update a CI-health issue

**Source:** [cost-detection investigation](../research/ci-cost-detection-investigation-2026-10-06.md) §5.4; [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) P1, P4 (ledger CCI-04, CRD-03, CRD-11)

**When:** **Unscheduled**, with E43

**Notes:** `main`'s run for `389e32d` failed on an integration timeout on 2026-10-06 and was visible only as `failure` in the run list

*Later notes: `notes.d/E47/`, oldest first (`python tools/register.py show E47`).*

### E51

**Work:** Decide whether CI wall-clock ever becomes a hard gate (CRD-11's deferred question): today the cost record reports budgets and shard times as warnings and the job timeout is the only hard bound

**Source:** [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) P4 (ledger CRD-11)

**When:** **On measured need**: after runner variance is measured from the cost record's history

**Notes:** Split from E43 when it closed (2026-10-07); a wall-clock gate must never fail a correct change for runner speed (operator, 2026-10-06)

*Later notes: `notes.d/E51/`, oldest first (`python tools/register.py show E51`).*

### E48

**Work:** CI redesign P5.1: full lanes on one OS per pull request, both OSes on `main` and the nightly, the second OS running `core` plus its platform-specific lanes

**Source:** [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) P5.1, §5 (ledger CRD-16)

**When:** **Unscheduled**: deferred (operator, 2026-10-06), revisited only with post-redesign measurements if CI is still too expensive

**Notes:** Trades per-PR proof for throughput: a one-OS regression would be caught after merge

*Later notes: `notes.d/E48/`, oldest first (`python tools/register.py show E48`).*

### E49

**Work:** CI redesign P5.3: larger runners (8 vCPUs) for the scenario lanes, as an experiment

**Source:** [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) P5.3, §5 (ledger CRD-18)

**When:** **On measured need**: deferred until P2 and P3 are measured (operator, 2026-10-06)

**Notes:** Needs an organization or a Team plan; P3 first shows what stays CPU-bound

*Later notes: `notes.d/E49/`, oldest first (`python tools/register.py show E49`).*

### E41

**Work:** CI redesign P2, the rest: import each command group's module when its command runs, not when `aew` starts (`build_parser()` still imports `work_commands`, `history_commands` and `dashboard_commands`, and so the `aew.dashboard` package, for every command; `aew.history.index` loads through `aew.engine.api`)

**Source:** [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) P2, §5 (ledger CRD-04)

**When:** **On measured need**: P2's measurement put the remaining import cost mostly in fixed work every command needs (the JSON-schema library, the engine), so P3 comes first

**Notes:** **Partly built (PR #96, 2026-10-06):** the dashboard's server stack and the doctor are imported only when used, about 10% off every CLI call (`aew status` about 920 to 825 ms), pinned by `tests/unit/test_cli_imports.py`. The 200 ms import target is a measured objective, never a CI assertion

*Later notes: `notes.d/E41/`, oldest first (`python tools/register.py show E41`).*

## 7. Operator acceptance session (UAT, 2026-09-30)

One operator-driven `aew opencode` session: an investigation of SPT (Lead GPT 6.1 Sol, roles mostly GPT 5.6 Luna), accepted as D-0017 in 47 minutes. The review, with the evidence for each item, and the operator's priorities: https://claude.ai/artifact/6FQhB6ihqHDTRTd5DYpqjE. The Lead's own debrief independently raised the plan-and-gate divergence (fixed below) and verification traceability (U2), and added the check-result guidance (fixed below) and U8 to U10.

Fixed before the M3 freeze (operator P0), with regressions in `tests/regression/test_uat_2026_09_30.py`: every plan revision declares its assurance (`--review`, `--verify` or `--assurance none`), and accepting it makes the declared cards required gates that only a new revision changes; cross-file policy consistency (`aew.policy.consistency`) in `aew doctor`, in the next actions of `status` and `resume`, and at the gate; next actions no longer offer a run's check results for `ingest`; each role's briefing names only the `aew` commands it may use.

<!-- columns: # | Work | Source | When | Notes -->

(none, since the rebaseline)

## 8. AEW-Lead review of the M3 tag (dogfood, 2026-10-01)

AEW ran the independent review's own prompt as AEW work, with the same model (GPT 6 Sol), on a scratch clone of `aew-m3-freeze-2026-09-30`. It found one new defect (plan acceptance order, fixed: ADR-0006 amendment) and the R2 class. It missed R1, which the independent review found: it stated the primitive but did not trace its consequence, the pattern F17 addresses. The run also showed these operational gaps:

<!-- columns: # | Work | Source | When | Notes -->

### V4

**Work:** Long checks inside an agent shell: the full suite (about 15 minutes) cannot finish in one shell command, so the verifier ended inconclusive

**Source:** the run (T-0003)

**When:** **Unscheduled** (run UX)

**Notes:** Inconclusive was the honest result. Running long checks through `aew check run` with the policy's timeout would avoid it.

*Later notes: `notes.d/V4/`, oldest first (`python tools/register.py show V4`).*

## 9. Closed

Entries leave the tables above when their work is accepted or another entry absorbs them. Their full text stays in the history (for those closed at M3's acceptance: the tag `aew-m3-accepted-2026-10-01`).

<!-- columns: # | Was | Closed | By -->

### Gate

**Was:** M3 acceptance: the dogfood and docs complete, then an independent review, before M4

**Closed:** 2026-10-01

**By:** The operator accepted M3 after the review fixes (PR #6; `review-response-2026-10-01.md`), without a re-review; merged by PR #5 (`169af1d`), tag `aew-m3-accepted-2026-10-01`

### Gate

**Was:** Before M4: ADR-0011 (hot and cold control state) implemented and accepted against H1 to H4, A1 and historical access, with E5 first

**Closed:** 2026-10-03

**By:** ADR-0011's implementation plan ([`adr-0011-implementation-plan.md`](../archive/milestones/adr-0011-implementation-plan.md)): P3's gate (H1 to H4) passed on Windows, Rocky 8.10 (WSL kernel) and Ubuntu (§7.4); the independent review's findings (P3-1, P3-2) and the re-review's (P3-R1, P3-R2) fixed in PR #24; merged by the operator as `42239e1`

### Gate

**Was:** Before M4-E: the designer promotes the F15 direction to governing

**Closed:** 2026-10-05

**By:** The typed Lead surface v0.2 moved from `docs/design/proposals/` to `docs/design/` as a governing design, text unchanged (the promotion PR of 2026-10-05); the idea note v0.4 stays adopted direction and governs only what the design defers to it; its requirements the design carries are marked absorbed in the ledger (TIS, LWE); the design's first-transport decision closes Q13's transport part; the Workflow Contract §15.6 consolidation goes to the re-freeze (E19)

### Gate

**Was:** Before feature work resumes, and before any release: the vertical UAT, the release gate (designer, 2026-10-11), runs in `enforce` on Linux (F47.5)

**Closed:** 2026-10-24

**By:** Replaced by the V-01 milestone (§1): the release gate is V-01's oracle, as the vertical-UAT ruling of 2026-10-23 re-derives it, and feature work stays paused until then (register rebaseline, design workspace, `b598fdc`)

### Gate

**Was:** Before internal alpha: network containment on Linux (F28) passes its live lane before any internal-alpha security claim calls Linux runs network-contained (designer, 2026-10-04)

**Closed:** 2026-10-24

**By:** Replaced by the Contained milestone (§1): CS-3b and CS-4 merged with their live lanes on Rocky 8; the security depth reset of 2026-10-24 narrows the claim to what a contained agent can reach (register rebaseline, design workspace, `b598fdc`)

### Gate

**Was:** Before internal alpha: the F18 and F28 canonical-state and credential boundaries hold on Rocky/Linux (operator, 2026-10-07, the F23 decision)

**Closed:** 2026-10-24

**By:** Replaced by the Contained milestone (§1): the security depth reset of 2026-10-24 narrows the claim to what a contained agent can reach (faking an approval or forging an owner fact, reading a credential, escaping) (register rebaseline, design workspace, `b598fdc`)

### Gate

**Was:** Before any real-repository dogfood, personal or internal alpha: real filesystem containment (F2) passes the containment regression gate

**Closed:** 2026-10-24

**By:** Met in M4-B (2026-10-03); folded into the Met row of §1 (register rebaseline, design workspace, `b598fdc`)

### Gate

**Was:** Before Linux runs rely on stop: POSIX process ownership (E13)

**Closed:** 2026-10-24

**By:** Met for contained runs in M4-B (2026-10-03); folded into the Met row of §1 (register rebaseline, design workspace, `b598fdc`)

### D1

**Was:** Bridge hardening by the peer process's ancestry

**Closed:** 2026-10-24

**By:** the operator's security depth reset of 2026-10-24, point 1: nothing a contained agent cannot reach is filed; and the operator's threat model of 2026-10-19: malicious host code is out of scope (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/D1/`, oldest first (`python tools/register.py show D1`).*

### D2

**Was:** An installer, and deeper harness integration (installed commands, one control surface)

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/D2/`, oldest first (`python tools/register.py show D2`).*

### D3

**Was:** Skills for AEW agents (Lead and role skills), made reachable through the capability registry

**Closed:** 2026-10-24

**By:** absorbed into STG-15

*Later notes: `notes.d/D3/`, oldest first (`python tools/register.py show D3`).*

### D4

**Was:** A deterministic `checks` adapter for integration-scope verifiers

**Closed:** 2026-10-05

**By:** M4-D5: `aew integrate validate` runs the policy's post-integration checks on the candidate under the lease, contained, with no model, when `gates.post_integration.validation` resolves to `checks` (by the Ticket's local class; an inherited verifier obligation overrides); engine-produced `check_result` evidence bound to the run's exact identity; fail-closed without immutable-source containment; a hard deadline; bounded infrastructure handling with a circuit breaker (ADR-0004's and ADR-0003's amendments of 2026-10-05). `verifier` stays the default; switching it is an evaluation (F19)

*Later notes: `notes.d/D4/`, oldest first (`python tools/register.py show D4`).*

### D5

**Was:** Model optimization and routing policy

**Closed:** 2026-10-24

**By:** held in HOLD-20

*Later notes: `notes.d/D5/`, oldest first (`python tools/register.py show D5`).*

### E1

**Was:** `aew harness wait` on any of several runs, woken by the supervisor instead of polled

**Closed:** 2026-10-05

**By:** M4-D6: `aew harness wait R1 R2 … --any` blocks on the wake file, checks the run records and the committed control state on each wake (ADR-0012 D5), parses no control state between commits, and returns the first run to end with its next action; median wake 42.2 ms on Windows (`tools/perf/wake_latency.py`), Rocky 8 owed

*Later notes: `notes.d/E1/`, oldest first (`python tools/register.py show E1`).*

### E2

**Was:** Subprocess-aware coverage of the harness code (supervisor, bridge, broker, adapter)

**Closed:** 2026-10-03

**By:** M4-A: coverage.py measures `src/aew` and every subprocess the Linux lanes start, line and branch, with the other OS's code excluded by marker; `assurance` combines the shards and holds a ratchet against `tests/coverage-baseline.json` (`testing-and-ci-strategy.md` §3, "Coverage")

*Later notes: `notes.d/E2/`, oldest first (`python tools/register.py show E2`).*

### E5

**Was:** Explicit collaborators for the Engine's hook points, instead of 13 mixins

**Closed:** 2026-10-03

**By:** P1 of the ADR-0011 plan, PR #15 (`Kernel`, the collaborators, `engine/ports.py`, `engine/seams.py`), with its independent review fixed in the PR

*Later notes: `notes.d/E5/`, oldest first (`python tools/register.py show E5`).*

### E7

**Was:** Lint cleanup with a shared flake8 and pylint configuration

**Closed:** 2026-10-03

**By:** The tooling phase between M4-A and M4-B, replacing flake8 and pylint as decided: Ruff (lint, bugbear, Bandit security rules), Pyright (as Linux and as Windows) and pip-audit, each fixed to clean and required by `assurance` through the new `static` job; Pylint is a manual, advisory run (`testing-and-ci-strategy.md`, "Static checks")

*Later notes: `notes.d/E7/`, oldest first (`python tools/register.py show E7`).*

### E8

**Was:** Next actions that read the evidence (a failing report or check names `aew gate show`)

**Closed:** 2026-09-30

**By:** Done in M3; merged by PR #5

*Later notes: `notes.d/E8/`, oldest first (`python tools/register.py show E8`).*

### E9

**Was:** A remedy in the `outside_ticket_scope` refusal

**Closed:** 2026-09-30

**By:** Done in M3; merged by PR #5

*Later notes: `notes.d/E9/`, oldest first (`python tools/register.py show E9`).*

### E10

**Was:** Scope feedback at `aew work create` (globs that match no file)

**Closed:** 2026-09-30

**By:** Done in M3; merged by PR #5

*Later notes: `notes.d/E10/`, oldest first (`python tools/register.py show E10`).*

### E11

**Was:** Telling the Lead how it can read the project, and that scope is fixed

**Closed:** 2026-09-30

**By:** Done in M3; merged by PR #5

*Later notes: `notes.d/E11/`, oldest first (`python tools/register.py show E11`).*

### E12

**Was:** `aew evidence show <id>`, the canonical detailed Evidence read surface, through the existing projection layer with structured output for the typed Lead surface and bounded bodies; normal workflow surfaces keep the record's conclusion and Evidence ID

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/E12/`, oldest first (`python tools/register.py show E12`).*

### E13

**Was:** POSIX process ownership (`setsid` escaped the process group)

**Closed:** 2026-10-03

**By:** M4-B: contained runs live in a PID namespace; killing bubblewrap ends it, `setsid` included. Agent-reported pids are translated through `NSpid` (`procs.host_pid`)

*Later notes: `notes.d/E13/`, oldest first (`python tools/register.py show E13`).*

### E15

**Was:** GitHub Action majors behind (Node 20 runtimes; CodeQL Action v3 deprecated December 2026)

**Closed:** 2026-10-01

**By:** The post-M3 cleanup: checkout v7, setup-python v7, upload-artifact v7, download-artifact v8, codeql-action v4

*Later notes: `notes.d/E15/`, oldest first (`python tools/register.py show E15`).*

### E17

**Was:** OpenCode upgrades without a PR per patch release: the projection check compares meaning, not the literal rule tail (AEW's rules in order; anything OpenCode appends after them may only deny), then 2.0.22 on the live lane and into `TESTED_VERSIONS`

**Closed:** 2026-10-24

**By:** absorbed into E35

*Later notes: `notes.d/E17/`, oldest first (`python tools/register.py show E17`).*

### E20

**Was:** `--json` output on read commands, so the typed action surface wraps structured results, not prose

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/E20/`, oldest first (`python tools/register.py show E20`).*

### E21

**Was:** `aew init` proposes the test command it discovers (`pyproject.toml`, `package.json`, `Makefile`), never configuring it silently

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/E21/`, oldest first (`python tools/register.py show E21`).*

### E26

**Was:** The Windows serial nightly `reference` job, split instead of its timeout raised (it had grown to 150 minutes)

**Closed:** 2026-10-05

**By:** Sharded: Linux 3 and Windows 6 serial shards (`--shard k/N`), each under a 60 minute timeout, and a `reference-assurance` aggregate (`check_assurance.py`, now also failing on a missing shard) that `report` waits for (PR #70)

*Later notes: `notes.d/E26/`, oldest first (`python tools/register.py show E26`).*

### E28

**Was:** Structured `check.run` results: counts, first failures with locations, an artifact reference; the full log stays expandable evidence

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/E28/`, oldest first (`python tools/register.py show E28`).*

### E29

**Was:** Context packs reserve context in a fixed order (constraints; work, authority and guardrails; source and evidence; then optional recall), written into the pack generator before any recall exists

**Closed:** 2026-10-05

**By:** `knowledge/context.py`: every section of a pack has a tier and `assemble(pack_inputs, budget)` spends a character budget tier by tier (the first two tiers are never cut, a lower tier is cut first, and every cut is written into the pack's budget notice and `Pack.truncations`); without a budget the pack is byte-identical. The engine passes no budget yet: wiring one in waits for a measured budget, and recall fills the last tier when it exists (PR #68)

*Later notes: `notes.d/E29/`, oldest first (`python tools/register.py show E29`).*

### E30

**Was:** Keep the register as structured data (YAML with a rendered view the dashboard can show), so milestone-start triage is mechanical

**Closed:** 2026-10-24

**By:** built: the register is YAML with a rendered view (register.py) (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/E30/`, oldest first (`python tools/register.py show E30`).*

### E32

**Was:** Integration hardening: `_interrupt_invocations` changes state through `set_state` (the single state-change path ADR-0004 relies on; `dependencies.py` and `hierarchy.py` do the same for derived states), and `aew doctor` lists worktrees under the workspaces root that no hot record references (a crash between DONE and the worktree removals leaves them)

**Closed:** 2026-10-24

**By:** the designer's family-5 ruling of 2026-10-24 (design workspace, ceaedbb): the direct state writes are by design; set_state's docstring is corrected in family 5's PR (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/E32/`, oldest first (`python tools/register.py show E32`).*

### E33 (part)

**Was:** Stream the credential scan of run state in chunks with overlap, instead of reading each file whole

**Closed:** 2026-10-09

**By:** PR #139: the end-of-run scan walks the run directory iteratively without entering links or reparse points, reads only regular files without following a link or blocking, in overlapping chunks with holes skipped, within one byte and entry budget; what it cannot read makes `credential_scan` incomplete (`unscanned`), never clean. The UTF-16 half stays as E33

### E34

**Was:** M4-D design inputs from the integration review: the worktree-sync classifier assumed one publisher, and a large publish's control-lock hold had no bound

**Closed:** 2026-10-05

**By:** M4-D3: the classifier accepts a path any commit between the candidate and the ref settled (up to 256); `gates.yaml` `max_publish_paths` (default 2,000) refuses a larger candidate at prepare. Measured with `tools/perf/publish_sync.py` on the Windows reference machine: about 4.5 to 5.5 ms a changed path after checking each path with one `lstat` instead of four, so 2,000 paths hold the lock about 10 s. Batched plumbing was not needed for that bound; the remaining cost is git's own hashing of the working copy

*Later notes: `notes.d/E34/`, oldest first (`python tools/register.py show E34`).*

### E36

**Was:** One definition of the v2-only control-state keys (the schema's v1 rule, `aew init` and the v1 test fixtures each spelled the set out)

**Closed:** 2026-10-04

**By:** PR #51: `engine.base.V2_ONLY_KEYS` and `as_v1`, with a test that the schema's v1 rule refuses exactly that set; source: the knowledge-manifest prototype lessons §3 (ledger KMP-02)

*Later notes: `notes.d/E36/`, oldest first (`python tools/register.py show E36`).*

### E37

**Was:** The service-credential amendments: ADR-0005 gains the `service` kind (scope `{service, family, issued_by}}`, no generation; Lead-issued, rotated and revoked; one live credential per principal; one closed family enforced by the store as `TRANSACTION_CLOSURE`; the Lead's custody rules; no mandatory expiry in v1); ADR-0009 gains the custody sentence and an environment-trust row for `AEW_SERVICE_TOKEN`; ADR-0013 D9 names the kind, states that a service transaction archives nothing, and gains oracle rule 33

**Closed:** 2026-10-05

**By:** The texts landed as amendments (designed, not built; the implementation is M6b's, F21); the closure rule the spike called 28 is ADR-0013's rule 29, its rule 30 is ADR-0013's 33

*Later notes: `notes.d/E37/`, oldest first (`python tools/register.py show E37`).*

### E38

**Was:** The acceptance guide's AT-9 row described the frozen KC §26 case (a locally Class 0 Ticket under a Class 3 Story keeps Class 0 and inherits the gate), which the Class 0 amendment §9.2 replaced and the row's own test refuses

**Closed:** 2026-10-05

**By:** Found by the architecture review's citation test ([T7 results](../archive/reviews/architecture-review-2026-10-04/t7-citation-test-results.md) §3); the row now states the amended behaviour (refused with `CLASS0_INHERITED_ELEVATED_OBLIGATION`, reclassified to Class 1, the gate still required), in the documentation consolidation

*Later notes: `notes.d/E38/`, oldest first (`python tools/register.py show E38`).*

### E40

**Was:** CI redesign P1: a merge gate tiered by what changed (`docs`, `web`, `full`), decided fail closed, with an always-full `main` run as the compensating control for the reduced tiers

**Closed:** 2026-10-06

**By:** PR #99 (`tools/ci/tier.py`, `assurance` recomputing the tier; `testing-and-ci-strategy.md` §3), tracked retroactively when the [CI redesign v0.2](../design/ci-redesign-design-v0.2.md) was ingested

*Later notes: `notes.d/E40/`, oldest first (`python tools/register.py show E40`).*

### E43

**Was:** CI redesign P4, the cost record: `assurance` writes, from the lane reports it already downloads, queue delay and wall clock, runner-minutes and wall time per lane and shard against `testing-and-ci-strategy.md` §8's budgets, total pytest time, the slowest 20 tests, each test's share of its lane, CLI calls per test and the share of collected tests in `durations.json`, as a job summary and an artifact; each lane also prints `--durations=20`; a shard over 20 minutes warns, over 25 is a CI-health violation; the job timeout stays the only hard bound; a PR's summary shows its new tests' cost, and the reviewer brief asks about it

**Closed:** 2026-10-07

**By:** `tools/ci/cost_record.py`, run by `assurance` after the assurance check (`if: always()`, `continue-on-error`: reported, never gated) from the lane reports and the run's jobs (GitHub API, `actions: read`): queue delay and end-to-end wall clock, runner-minutes per OS, wall time per job, total pytest time and per lane and shard, the slowest 20 tests with each one's share of its lane and its `aew` calls through the test helper (counted by `conftest.run_aew`; direct `python -m aew` starts and fake agents' calls are not counted, carried in the lane report's new `cli_calls`), the share of collected tests in `tests/durations.json`; a job summary plus the `cost-record` artifact; every lane and both core steps print `--durations=20`; a test job over 20 minutes warns, over 25 is a CI-health violation, the 30-minute timeout stays the only hard bound; §8's budgets are compared as warnings, as §8 defines them (Linux `core` within 3 minutes, the Linux fast lane's test time within 3, the run from its first job's creation to its last job done within 15); the time a run waits as pending before its first job is reported as a fact, not judged; on a re-run only that attempt's jobs count (carried-over jobs are listed and count for nothing). A PR's summary shows its new tests (in the files it touches and unknown to `tests/durations.json`) and every test in those files. The lead developer's reviewer brief asks about a change's test cost from 2026-10-07 (CCI-06). Repeated violations opening an issue stay E47; whether wall-clock ever becomes a hard gate is E51

*Later notes: `notes.d/E43/`, oldest first (`python tools/register.py show E43`).*

### E44

**Was:** Refresh and rebalance the shards from E43's record; duration history influences placement only, never which tests run: a missing, stale or corrupt cache falls back to balancing by test count, and the committed `tests/durations.json` is refreshed by an automated PR when drift passes a threshold

**Closed:** 2026-10-23

**By:** PR #235: every green push to `main` adds its lane reports to a rolling history in the Actions cache (`update_durations.py --history`, each test's last five durations), and every run balances its shards on the history's medians and sizes the `lanes` matrix from them (`tools/ci/shard_plan.py`: the fewest shards that fit on a runner twice as slow, the job's setup included; reported, never gating). The committed `tests/durations.json` is a run's table as the sizer writes it, with each lane's count, which is also that lane's floor (today's from `main`'s run 39900909868, sized as a first history would be). A run without a usable history (missing, unreadable or not of a history's shape) balances on it at twice its counts, the nightly reads the history so it does not expire, and every run warns when the committed table falls behind; the refresh is a copy of a green `main` run's `shard-durations` table in an ordinary pull request (the operator's ruling on CRD-13, 2026-10-23; `testing-and-ci-strategy.md` §7, §8). Exactly-once assurance still proves membership independently of the history

*Later notes: `notes.d/E44/`, oldest first (`python tools/register.py show E44`).*

### E45

**Was:** A per-test cost check: a test over a set share of its lane's time (for example 25%), or a fast-lane test over a set number of seconds, is a CI-health violation reported in the cost record; it **warns and never fails the gate** (operator, 2026-10-06). Any later performance gate is on metrics AEW controls (aggregate pytest time, CLI starts, expensive fixture constructions, the slow-test aggregate, cost per family), judged against baselines with their variance

**Closed:** 2026-10-07

**By:** Built with E43: a test over 25% of its lane's test time (in a lane of at least a minute), or a fast-lane test over 30 s, is a CI-health violation in the cost record, warned and never failing the gate (operator, 2026-10-06)

*Later notes: `notes.d/E45/`, oldest first (`python tools/register.py show E45`).*

### E50

**Was:** Lead inactivity expiry: after long inactivity a Lead attachment is staled or revoked and a fresh attachment and generation are required, under Q12's semantics; for abandonment cleanup (an attachment left over a long absence), not short-session policing; it never silently kills independently admitted child work

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/E50/`, oldest first (`python tools/register.py show E50`).*

### E55

**Was:** `--when next-step|turn-end` on `aew harness send` (the designer's decision of 2026-10-10)

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E55/`, oldest first (`python tools/register.py show E55`).*

### E56

**Was:** Integration debt, audit AX-06 (P2): a `follow_up` disposition is not linked to the follow-up Ticket it promises (no back-link, and no anomaly when the follow-up is abandoned)

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E56/`, oldest first (`python tools/register.py show E56`).*

### E57

**Was:** Integration debt, audit AX-07 (P2): an adopted plan's source freshness never reaches the dispatch predicate, so a plan premise is not rechecked

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E57/`, oldest first (`python tools/register.py show E57`).*

### E58

**Was:** Integration debt, audit AX-08 (P2): an ancestor plan's invalidation produces no event, no Lead decision and nothing for the worker

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E58/`, oldest first (`python tools/register.py show E58`).*

### E59

**Was:** Integration debt, audit AX-12 (P4): the published commit names no integration record or evidence (no trailers), so joining a commit back to its Ticket relies on commit subjects

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E59/`, oldest first (`python tools/register.py show E59`).*

### E60

**Was:** Integration debt, audit AX-13 (P3): `coordination_unseen` is not read by the projections, which blocks F9's worker-reply slice

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E60/`, oldest first (`python tools/register.py show E60`).*

### E61

**Was:** Integration debt, audit AX-14 (P3): a re-review gets no delta against the prior review

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/E61/`, oldest first (`python tools/register.py show E61`).*

### E62

**Was:** Integration debt, audit AX-15 (P4): project maps reach only the investigator's pack, not the planner's, and are not regenerated on publish

**Closed:** 2026-10-24

**By:** held in HOLD-14

*Later notes: `notes.d/E62/`, oldest first (`python tools/register.py show E62`).*

### E63

**Was:** A fix round names the review it answers: a minimal `answers` link on the repair or re-dispatch record, so review and fix rounds can be counted as cycles (observability inventory gap 3)

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/E63/`, oldest first (`python tools/register.py show E63`).*

### E64

**Was:** Identity-bearing block and queue-wait events: blocked time produced by the dependency engine, queue-wait time by the queue, each as canonical process facts that F42 aggregates (observability inventory gap 8)

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E64/`, oldest first (`python tools/register.py show E64`).*

### E65

**Was:** The second composition audit: a narrow, fresh-context, report-only audit of the new actors and control seams since `1dd89d5`, failure and recovery composed across owners, and credential, security and authority flow across the joins; for every recovery path what authority survived or was revoked, what is reconstructed, what evidence stays admissible, which generation or revision owns the result, what wakes whom, and whether stale authority can be resurrected

**Closed:** 2026-10-24

**By:** STG-12: the as-built reconciliation and its trace are the composition audit now (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/E65/`, oldest first (`python tools/register.py show E65`).*

### E66

**Was:** Platform asymmetry of the joins: check that packs, wakes and usage behave the same on Linux, where containment is real, and on Windows, where it is a label

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/E66/`, oldest first (`python tools/register.py show E66`).*

### E67

**Was:** Audit coverage debt: the first audit's UNKNOWN areas (F4 beyond S1, M6a Gates A and B, K1 and K2 capture, F36, F30 and F18's attachment, the queue with more than one lane on the real Rocky host)

**Closed:** 2026-10-24

**By:** STG-12: S12-4 traces every requirement and every module mechanically; M6a's gates are closed (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/E67/`, oldest first (`python tools/register.py show E67`).*

### E68

**Was:** Built-claim conformance: a machine check that the actual built claims (the free-text `status: done` entries of the requirements ledger and the "Implemented" or "Built" paragraphs of `implementation-status.md`) resolve to a test or path anchor

**Closed:** 2026-10-24

**By:** STG-12: the generated, CI-checked reference replaces free-text built claims (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/E68/`, oldest first (`python tools/register.py show E68`).*

### E69

**Was:** One canonical reason vocabulary for externally projected liveness outcomes where their meanings coincide (`lost`, `stale`, `wedged`, `gone`), used by the operator notifier and the projections; the run heartbeat, the broker's beat and the custody worker's identity keep their own mechanisms and thresholds

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/E69/`, oldest first (`python tools/register.py show E69`).*

### E70

**Was:** The hard deadline as one semantic fact: canonical in the error and reason vocabulary and projected into the spool, anomaly and steering-loop surfaces, replacing three independent spellings of it

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/E70/`, oldest first (`python tools/register.py show E70`).*

### E77

**Was:** Recurring finding classes across review rounds: a future AEW mechanism that detects a finding class recurring across review rounds and prompts method-level rework instead of repeated instance fixes

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/E77/`, oldest first (`python tools/register.py show E77`).*

### E78

**Was:** Head-bound CI status in the product: the existing engine evidence and projection owners surface the CI status bound to the exact head in hand-backs, verdict records and the Lead projection

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/E78/`, oldest first (`python tools/register.py show E78`).*

### E84

**Was:** A move or a promotion keeps the moved work's inherited obligations, or is refused (EW-U05.g): a reorganization preserves the applicable proof obligations. One of the trace's FIX rows (S12-6), taken ahead of its milestone

**Closed:** 2026-10-25

**By:** #274 (`c81eb233`): a move or a promotion that would lower what a moved unit still to be proven inherits is refused (`OBLIGATIONS_DROPPED`), as ADR-0007's amendment of 2026-10-25 states. Carrying the obligations instead is E87

*Later notes: `notes.d/E84/`, oldest first (`python tools/register.py show E84`).*

### E85

**Was:** A return from escalation rechecks the gates of the phase it returns to (EW-U06.f). One of the trace's FIX rows (S12-6), taken ahead of its milestone

**Closed:** 2026-10-26

**By:** #279 (`32fc4ea3`): a return from escalation meets the gates of the phase it enters, and a reconcile the guard of its direct edge, as ADR-0003's amendment of 2026-10-25 states. The class by any route is E96, and E85's named outcome closes only when E96 lands (designer, 2026-10-25)

*Later notes: `notes.d/E85/`, oldest first (`python tools/register.py show E85`).*

### F1

**Was:** Hot and cold control state (archival of terminal records)

**Closed:** 2026-10-03

**By:** ADR-0011 implemented: P1 #15, P2a #17 (cold-store core), P2b #18 (archival), P2c #20 (history surface and audit), P2d #21 (migration), P3 #24 (acceptance gate)

*Later notes: `notes.d/F1/`, oldest first (`python tools/register.py show F1`).*

### F2

**Was:** Real filesystem containment (protected writable roots, enforced by the OS)

**Closed:** 2026-10-03

**By:** M4-B: a bubblewrap sandbox per run, built from the role (exhaustive table, fail closed), applied by the run's process tree to every spawn and to its checks; run-private git state with the real metadata read-only; a launch self-test on the exact layout; truthful labels (filesystem integrity only; the host stays readable; network not provided). The designer's open questions settled as built: agents run no git write commands (the metadata is read-only), reviewers and verifiers get read-only source, network containment is not provided. ADR-0009, M4-B amendment; `m4-ambiguity-report.md`, "M4-B as built"

*Later notes: `notes.d/F2/`, oldest first (`python tools/register.py show F2`).*

### F3

**Was:** Workspace strategy abstraction, role-sensitive isolation, repository-scale benchmarks

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F3/`, oldest first (`python tools/register.py show F3`).*

### F4

**Was:** Ticket supersession lineage, and a first-class goal-revision path

**Closed:** 2026-10-24

**By:** held in HOLD-08

*Later notes: `notes.d/F4/`, oldest first (`python tools/register.py show F4`).*

### F5

**Was:** Hierarchy revision semantics: EDITORIAL, CLARIFICATION and MATERIAL; Story and Epic revision; approved-baseline drift; admissibility as a Knowledge Contract concept

**Closed:** 2026-10-24

**By:** held in HOLD-08

*Later notes: `notes.d/F5/`, oldest first (`python tools/register.py show F5`).*

### F6

**Was:** Fail-closed classification applied to existing classifiers: the downgrade rule for `verify classify`, and risk-class choice

**Closed:** 2026-10-24

**By:** held in HOLD-05

*Later notes: `notes.d/F6/`, oldest first (`python tools/register.py show F6`).*

### F7

**Was:** Delegation and resource governance: bounded nested-delegation grants, duplicate-work detection, fanout, retry and interruption budgets, exact-match permission aggregation, cancellation propagation across fanout

**Closed:** 2026-10-24

**By:** held in HOLD-05

*Later notes: `notes.d/F7/`, oldest first (`python tools/register.py show F7`).*

### F8

**Was:** Lead and operator interaction: reconnaissance, elicitation, project maps and freshness, durable stakeholder decisions, checkpoints

**Closed:** 2026-10-24

**By:** held in HOLD-02

*Later notes: `notes.d/F8/`, oldest first (`python tools/register.py show F8`).*

### F9

**Was:** Live coordination and assumption propagation

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F9/`, oldest first (`python tools/register.py show F9`).*

### F9.1

**Was:** Typed worker consultation and feedback messages

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F9.1/`, oldest first (`python tools/register.py show F9.1`).*

### F9.2

**Was:** Admitted Lead instructions in review and verification context (audit AX-02): a bounded, engine-owned, immutable content record for each admitted Lead-to-worker send, one canonical content object referenced by both paths (`harness send` with messaging off, the F9 thread with messaging on), never two histories; a small durable body limit aligned with F9's message discipline (about 4,000 characters), larger material by referenced artifact; reviewer and verifier packs carry each admitted instruction that materially applies to the reviewed attempt, with its message id, kind, admission time, Ticket, revision and attempt binding, canonical sanitized content and provenance, and show explicitly when content is redacted

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F9.2/`, oldest first (`python tools/register.py show F9.2`).*

### F10

**Was:** Mutating concurrency above 1: integration queue, merge revalidation

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F10/`, oldest first (`python tools/register.py show F10`).*

### F11

**Was:** Dynamic scheduler

**Closed:** 2026-10-24

**By:** held in HOLD-15

*Later notes: `notes.d/F11/`, oldest first (`python tools/register.py show F11`).*

### F12

**Was:** Workbench capability manifests, resolver, provider health in `doctor`, an MCP adapter over the Engine API

**Closed:** 2026-10-24

**By:** absorbed into STG-15

*Later notes: `notes.d/F12/`, oldest first (`python tools/register.py show F12`).*

### F13

**Was:** Capability discovery and progressive disclosure: an Effective Capability Manifest per invocation that keeps available, authorized and active apart; lazy expansion from L0 awareness to L3 exact schema; adapters advertising harness-native capabilities (sandbox, compaction, native review or orchestration, resume); skills that name abstract capability classes; manifests and schemas recorded by reference and hash; a context-economy acceptance test (a large, unrelated MCP server must not inflate baseline context)

**Closed:** 2026-10-24

**By:** absorbed into STG-15

*Later notes: `notes.d/F13/`, oldest first (`python tools/register.py show F13`).*

### F14

**Was:** Plan assurance and premise validation before mutating dispatch: raw stakeholder intent kept apart from derived interpretation, with statements typed (requirement, observation, diagnosis, inference, decision); acceptance reconstructed independently by a fresh role *before* it sees the proposed plan; decision-sensitive premises tested by discriminating probes; typed pre-implementation baselines (`EXPECTED_FAILURE`, `UNEXPECTED_PASS`, `INVALID_MEASUREMENT`, …); negative controls; subject kept apart from acceptance inputs, oracle, evaluator and environment, with protected acceptance conditions enforced through final verification; a Plan Challenge with bounded outcomes and disagreement budgets; assurance bound to the whole dependency set by canonical hash; `ASSURED` as one derived gate predicate at plan acceptance and at every dispatch path; deterministic plan lint; hierarchical inheritance of parent obligations; proportional tiers A–E with hard triggers; strong models at interpretation points

**Closed:** 2026-10-24

**By:** held in HOLD-04

*Later notes: `notes.d/F14/`, oldest first (`python tools/register.py show F14`).*

### F14.1

**Was:** Parent-plan `interactions[]` and the composition rule: a parent plan lists structured interactions between sibling work units wherever a material interaction exists (`between`, dependency and interface refs, shared surfaces, allocated identifiers, `parallelism` PARALLEL_ALLOWED|SERIAL_REQUIRED|CONDITIONAL, conditions, rationale refs), the reviewed parallelism verdict of Q4; `SERIAL_REQUIRED` compiles to the existing blocking dependency; `PARALLEL_ALLOWED` is permission only; `CONDITIONAL` governs only through closed, engine-evaluable predicates (an interface digest still current, an overlap set still empty, a named dependency state), free text explaining only; no model-generated coupling score: the engine supplies deterministic dependency, interface and overlap evidence and plan review judges; parent-plan lint at acceptance

**Closed:** 2026-10-24

**By:** held in HOLD-04

*Later notes: `notes.d/F14.1/`, oldest first (`python tools/register.py show F14.1`).*

### F15

**Was:** Lead workflow efficiency: stage commands named for the Lead's judgment (`draft`, `start`, `request-review`, `request-verification`, `prepare`), each a guarded sequence of existing operations with its own durable records, returning completed steps, revision, runs and a typed next action; publish stays a separate decision; exit-code instrumentation of the command log; a paired replay against the M3 dogfood baseline

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F15/`, oldest first (`python tools/register.py show F15`).*

### F15.1

**Was:** The typed Lead surface's read-only and transport slice (typed Lead surface v0.2 §3 to §5, §7, §8, §11's M4-D row): the catalog and runner, `lead.tool`, the `aew-lead` MCP transport, the query tools, `harness_wait`, `checkpoint`, `aew lead tool`, surface profiles, conformance and the `lead_mcp` channel

**Closed:** 2026-10-06

**By:** PRs #88, #93 and #95. #88 the contract: `aew.surface` (the v1 catalog with the stages designed and refused, the effective class, one runner, a tri-state `ActionProjection` with availability, callability and auto-run eligibility kept apart), `schemas/surface.schema.json` with A3's `policy_binding`. #93 the broker: `lead.tool` (cooperative, so a typed wait never holds the broker), the fail-closed Lead reachability classification, the recovery-only `cli` escape and `aew lead tool`. #95 the transport: `aew lead mcp` (no credential, no direct mode, never an engine), the Lead projection and probe against the pinned 2.0.18 (MCP timeouts in ms, default 12 h; tools named `<server>_<tool>`). Still open for F15.2: TLS-07, TLS-16 (`ticket_draft` equivalence), TLS-26, TLS-28; for E18: TLS-25's dashboard half

*Later notes: `notes.d/F15.1/`, oldest first (`python tools/register.py show F15.1`).*

### F15.2

**Was:** Governed mutating stages: the `StageIntent` journal (hot while active, cold when terminal), the policy/dependency digest and `STALE_POLICY`, effective-class promotion, queryable transition and ingest guards, policy-resolved review and verification card sets, `ticket_draft`/`ticket_start`/`ticket_request_review`/`ticket_request_verification`/`ticket_prepare` as governed stages, the typed `integration_publish` decision tool, stage/primitive equivalence tests and a live OpenCode 2.0.18 MCP spawn check

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F15.2/`, oldest first (`python tools/register.py show F15.2`).*

### F15.3

**Was:** The `aew-run` role server (the run bridge's `whoami`, `check.run` and typed `submit` as tools inside the sandbox, the supervisor keeping the credential) and `aew-knowledge` as a separate capability namespace over the shared transport library

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F15.3/`, oldest first (`python tools/register.py show F15.3`).*

### F15.4

**Was:** Policy digest separation: every execution-policy field classified `legality_affecting` or `operational` (an unclassified field fails schema validation); each staged action records `legality_digest`, `operational_digest`, the revision, the authority generation and any action-specific authorization digest; only a legality mismatch is `STALE_POLICY`, an operational change takes effect at the next safe boundary, and a recovery action snapshots the operational settings it depends on

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F15.4/`, oldest first (`python tools/register.py show F15.4`).*

### F15.5

**Was:** Crawl / Walk / Run steering over `ActionProjection`, with its operator authority boundary: `aew confirm`, autonomy increases and `PUBLISH_IF_CLEAN` grants only through an operator capability structurally absent from agent shells and model tools (the Lead may request, lower and continue); attributable mode-change records; Walk auto-runs only actions whose declared side effects are all in the allow-list `{control_state}`, with catalog conformance (observed effects within declared); the auto-run envelope (budget, admission, repetition N = 2, the loop deadline) and the invocation hard deadline as an authority-reducing safety action; an out-of-band operator notifier for unattended Run

**Closed:** 2026-10-24

**By:** held in HOLD-19

*Later notes: `notes.d/F15.5/`, oldest first (`python tools/register.py show F15.5`).*

### F15.6

**Was:** Bounded recovery, the approved limited slice: R5-1, one `STALE_REVISION` retry of a non-judgment step with legality recomputed and a durable `retried_after_stale_revision` marker; and R5-3, one relaunch of a `launch_failed` run (`recovery.relaunch_launch_failed: 1`, default 0), fail-closed: a termination proof from every custody mechanism, the old credential revoked and confirmed before a fresh one is bound to the new run id, a positive no-side-effect proof over every effect channel, an implementation-owned allow-list of transient reasons (unknown fails closed), a circuit breaker (recommended 3 in 5 minutes per endpoint, or project-wide; operator reset), and a relaunch record binding all of it

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F15.6/`, oldest first (`python tools/register.py show F15.6`).*

### F15.7

**Was:** The deferred recovery rows: row 4 `REDISPATCH_IF_LOST` (a pre-authorized re-dispatch of a lost clean run, a sibling of `PUBLISH_IF_CLEAN`), row 6 a policy-resolved Investigator after a blocked report, row 8 `max_fix_attempts` (the fix-loop cap)

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F15.7/`, oldest first (`python tools/register.py show F15.7`).*

### F15.8

**Was:** The `aew-run` read half, ahead of M6a: the role-side server inside the sandbox over the existing run bridge (credentials stay supervisor-side), `whoami` and `check.run` as tools, and typed read operations as `bridge.OPERATIONS` rows: map search with exact resolution first and a workspace-rooted lexical fallback, `map.symbol`, `map.callers` and `map.callees` (`NOT_SUPPORTED` until a semantic extension covers the language), `map.tests_for`, `map.constraints`, `map.changed`, `evidence.show` and `check.suggest`, under one result envelope (terminal state, coverage, freshness, evidence locators, omitted counts); the execution profile's `tools.presentation` (raw-first, neutral or typed-first); raw tools unchanged

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F15.8/`, oldest first (`python tools/register.py show F15.8`).*

### F15.9

**Was:** Delta-first Lead attention (E2): one typed read query on the Lead surface, changes since a cursor (`changes {since_revision, since_observed?}`), over the outbox's committed transitions and the projection's derived deltas, with the decisions required, blockers and supervision candidates always present, one line per item with an expansion reference, and a size cap; `status` and `resume` stay the full view; no second event or state store

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F15.9/`, oldest first (`python tools/register.py show F15.9`).*

### F16

**Was:** Explain AEW to the model Lead instead of leaving it to trial and error (operator, 2026-09-30)

**Closed:** 2026-10-24

**By:** held in HOLD-02

*Later notes: `notes.d/F16/`, oldest first (`python tools/register.py show F16`).*

### F17

**Was:** Consequence tracing and evidence depth ("shallow finding termination"): a role finds a consequential fact, capability or boundary condition but closes before establishing what it leads to

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/F17/`, oldest first (`python tools/register.py show F17`).*

### F18

**Was:** Operator bootstrap and host integration: setting up AEW and its harness on a host, and starting and attaching the operator's session within the hosting boundary Q12 decided (2026-10-06)

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18/`, oldest first (`python tools/register.py show F18`).*

### F18.1

**Was:** `aew init` proposes, the operator applies: the proposal file (`.aew/local/init-proposal.yaml`, with `proposal_id` and `inputs_sha256`), `init --apply` as one atomic attributable apply that refuses stale or expanded proposals, `--accept-proposal` for non-interactive use, static-before-trust repository inspection through the T5 generator, and the configuration ownership model (AEW edits no user or project harness file; supported Lead sessions use isolated generated configuration)

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.1/`, oldest first (`python tools/register.py show F18.1`).*

### F18.2

**Was:** `aew doctor` with ERROR/WARN/INFO rows, a remedy per row, `--todo`, `--json` with stable finding ids, the harness dry start and schema probe under isolated configuration by default, `--online` for gateway checks, the conflict-detection row for ambient harness files, and never auto-fixing

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.2/`, oldest first (`python tools/register.py show F18.2`).*

### F18.3

**Was:** The air-gap bundle, three side-by-side artifacts: `aew-bundle-<version>-rl8-py311.tar` with the wheelhouse and qualified harness pins, its canonical manifest `aew-bundle-<version>-rl8-py311.json` (committing to the archive's name, size and SHA-256 and to every member), and `aew-bundle-<version>-rl8-py311.json.sig`, a detached signature over the manifest from a release identity with an independently provisioned trust root; a verifier that rejects traversal, duplicates and mismatches before anything is consumed; `aew doctor --bundle --json` as the host acceptance record; tool upgrade separate from project migration with a declared restore point

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.3/`, oldest first (`python tools/register.py show F18.3`).*

### F18.4

**Was:** Organization launch and provider-access seams: the harness launch provider (`direct_binary`, `airgap_bundle` or `organization`) selecting a qualified pin that AEW independently verifies after launch; the `aew/harness-qualification/v1` manifest (AEW-shipped or organization-approved, the same mandatory conformance); the `provider_access` profile whose mTLS and PKI material stays supervisor-side behind the F28 relay; and the seven-point live qualification gate before the integration is called supported

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.4/`, oldest first (`python tools/register.py show F18.4`).*

### F18.5

**Was:** F18-A, contract and state: attachment states (NO_ATTACHMENT, PREPARING, FAILED, ACTIVE, SUSPENDED, DETACHED) and reason codes; the protected-set registry; the support manifest and executable content identity; hot and cold generation records (ADR-0011); guarantee labels (`guarantee: dev`); the operator-only lifecycle contract

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.5/`, oldest first (`python tools/register.py show F18.5`).*

### F18.6

**Was:** F18-B0, deployment security-principal proof and ergonomics: a dedicated Lead and worker principal or an SELinux-equivalent boundary; an operator-only supervisor socket authorized by peer credentials; supervisor-owned protected state; the group, ACL, git and TUI ergonomic path; refusing a same-principal deployment

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.6/`, oldest first (`python tools/register.py show F18.6`).*

### F18.7

**Was:** F18-B1, bootstrap: a bootstrap-only broker; explicit managed or registered-host selection; managed launch by default; PREPARING cleanup; the conversation-taint record and the reattach delta

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.7/`, oldest first (`python tools/register.py show F18.7`).*

### F18.8

**Was:** F18-C, the load-bearing gateway and broker binding: the gateway principal and provider-credential custody; forced egress; the normalized structural-surface parser; pre-egress enforcement; server-side binding of a response's `tool_call_id` and argument hash, single-use with expiry; SUSPENDED behaviour; the fail-closed gateway outage policy

**Closed:** 2026-10-24

**By:** held in HOLD-20

*Later notes: `notes.d/F18.8/`, oldest first (`python tools/register.py show F18.8`).*

### F18.9

**Was:** F18-D, detached child handling: close acknowledgement; detached-run attention; bounded credentials; the hard-deadline order; drain semantics, with the drain deadline as a stop condition; StageIntent stale-owner handling

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.9/`, oldest first (`python tools/register.py show F18.9`).*

### F18.10

**Was:** F18-E, production attachment enablement: F18.6, F18.7, F18.8 and F18.9 combined into managed project attach; existing-host attach enabled only where the forced gateway path is proven

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.10/`, oldest first (`python tools/register.py show F18.10`).*

### F18.11

**Was:** F18-F, OpenCode qualification: T9's remaining broker-only, configuration-isolation and model-visible conformance, plus the normalized-surface false-drift test

**Closed:** 2026-10-24

**By:** absorbed into E35

*Later notes: `notes.d/F18.11/`, oldest first (`python tools/register.py show F18.11`).*

### F18.12

**Was:** F18-G, Codex qualification: qualifying the intended pin with the same versioned suite, plus Codex's request, delegation and ambient-context checks

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.12/`, oldest first (`python tools/register.py show F18.12`).*

### F18.13

**Was:** F18-H, reference topology smoke: the Astra Lead with the Laguna default worker, and GPT-5.4 and open-source overrides where available

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.13/`, oldest first (`python tools/register.py show F18.13`).*

### F18.14

**Was:** F18-I, production-hosting ergonomics observation: measuring principal, ACL, git and TUI friction and operator workarounds before production rollout; M4-H may contribute optional early observations

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F18.14/`, oldest first (`python tools/register.py show F18.14`).*

### F18.15

**Was:** Gateway usage convergence: one accounting hook in the AEW Provider Gateway emits the authoritative provider-usage event; F19's slice S18 is an evaluator client of it, never a second, permanent metering proxy; F25 projects and cross-checks it, with a gateway trust and source value in its usage vocabulary

**Closed:** 2026-10-24

**By:** held in HOLD-20

*Later notes: `notes.d/F18.15/`, oldest first (`python tools/register.py show F18.15`).*

### F20

**Was:** Read-only operator dashboard, main-line integration

**Closed:** 2026-10-24

**By:** held in HOLD-12

*Later notes: `notes.d/F20/`, oldest first (`python tools/register.py show F20`).*

### F20.1

**Was:** Frontend merge and CI integration (`web.yml` called from `ci.yml`, folded into `assurance`; CodeQL `javascript-typescript`)

**Closed:** 2026-10-03

**By:** PR #26

*Later notes: `notes.d/F20.1/`, oldest first (`python tools/register.py show F20.1`).*

### F20.2

**Was:** Read-only API and conformance: the GET/HEAD projections of contract 0.1.2 with bounded cursors and filters, every response validated against the contract in Python tests

**Closed:** 2026-10-05

**By:** PR #67: `aew.dashboard` (server, lock-free reader, projections, cursors, contract, reasons), the additive engine reads (`read_committed`, `control_identity`, the History bounds, `over_policy_detail`); design note §4.5 to §4.11, §5.1

*Later notes: `notes.d/F20.2/`, oldest first (`python tools/register.py show F20.2`).*

### F20.3

**Was:** Dashboard session: the operator credential minted at the operator's terminal, the one-time URL exchanged for an `HttpOnly`, `SameSite=Strict` cookie; `aew dashboard serve`, `open` and `status`

**Closed:** 2026-10-05

**By:** PR #71: the `operator_session` credential kind (ADR-0005 amendment), the server-console challenge for `open`, one server per project under the endpoint lock, the security acceptance with its negative controls; design note §4.1 to §4.4, §5.2

*Later notes: `notes.d/F20.3/`, oldest first (`python tools/register.py show F20.3`).*

### F20.4

**Was:** Conditional requests and caching: ETags cover the whole envelope, `control_revision` and the session's scope included; 200 and 304 behaviour checked against live projections

**Closed:** 2026-10-05

**By:** PR #87: `aew.dashboard.etag`, a strong validator over the representation less the snapshot's time, in the request scope (path, project, normalized query); `If-None-Match` as a list, `W/` and `*` never matching; a `304` with the validator sent, no body, after authentication; tested against live projections (a commit, a revision-only commit, telemetry alone); design note §4.12, §5.3

*Later notes: `notes.d/F20.4/`, oldest first (`python tools/register.py show F20.4`).*

### F20.5

**Was:** Static serving and server security: the static build in the Python package with an SPA fallback for deep links; CSP and security headers; Host and Origin checks (DNS rebinding); request bounds; `127.0.0.1` only

**Closed:** 2026-10-05

**By:** PR #90: the frontend built from `4f0a710` (agreed with the web developer and the operator) by the pinned offline builder and committed under `src/aew/dashboard/static/` with `BUILD.json` (`tools/dashboard/import_build.py`); `aew.dashboard.frontend` (the SPA fallback, traversal refused); R21's header set on every response; the exact Host (`421`) and Origin and `Sec-Fetch-Site` (`403`) rules; methods (`405`) and request bounds (`400`, `414`, `431`, `503`); the redacted request log; `serve --static DIR`; design note §4.13, §4.14, §5.4

*Later notes: `notes.d/F20.5/`, oldest first (`python tools/register.py show F20.5`).*

### F20.6

**Was:** Integrated acceptance: the browser and security checks against authenticated live state, recorded separately from the frontend's acceptance

**Closed:** 2026-10-24

**By:** held in HOLD-12

*Later notes: `notes.d/F20.6/`, oldest first (`python tools/register.py show F20.6`).*

### F20.7

**Was:** The dashboard event endpoint (ADR-0012 D8): `GET /api/v1/events?since=R` as a bounded long poll on the revision cursor over the outbox's typed events, waking on `local/wake` through F20.2's lock-free reader; the reply names only which revisions changed which kinds and ids, and the frontend refetches the projections with their ETags

**Closed:** 2026-10-24

**By:** held in HOLD-12

*Later notes: `notes.d/F20.7/`, oldest first (`python tools/register.py show F20.7`).*

### F20.8

**Was:** Dashboard maps and raw-history search: contract 0.1.3

**Closed:** 2026-10-24

**By:** held in HOLD-12

*Later notes: `notes.d/F20.8/`, oldest first (`python tools/register.py show F20.8`).*

### F21

**Was:** The M6b knowledge system: capture and admission of reusable knowledge (K0 references, K1 Cases, K2 Lessons, K3 held), guarded recall and context routing, and their shared semantics (identity, provenance, orthogonal state, receipts, visibility composition, provider boundary)

**Closed:** 2026-10-24

**By:** held in HOLD-13

*Later notes: `notes.d/F21/`, oldest first (`python tools/register.py show F21`).*

### F22

**Was:** Project maps: the deterministic structural codebase map, language-specific semantic extensions (C/C++ first) that add qualified facts without redefining it, sibling derived indexes, and the attributable architecture map, composed into one navigation/context view that never becomes an authority source

**Closed:** 2026-10-24

**By:** held in HOLD-14

*Later notes: `notes.d/F22/`, oldest first (`python tools/register.py show F22`).*

### F22.1

**Was:** T5-A, the structural core (project maps v0.5 §2, §3, §10, §11, §16 T5-A): the structural codebase map from Git objects with mechanically tracked inputs, its registry with its own `map_revision`, `aew map generate/show/diff`, architecture-reference selection and the bounded pack slices, as a parallel lane to M4-H (SMQ-01)

**Closed:** 2026-10-09

**By:** Two pull requests of the lead developer's plan (v4, independently reviewed CLEAR). PR #126 built the structural core and [ADR-0015](adr/0015-project-map-storage-and-registry.md) (ledger MSR). The second built `aew map select-architecture`, the execution policy's `maps.pack_slices` switch (`"off"` by default, written quoted because YAML reads a bare off as a boolean: packs and the resume view are then byte-identical to a project without maps, so the Q7/M4-H treatment is unchanged), the bounded slice in the packs of roles whose context names `codebase_map` (only the investigator: the operator decided on 2026-10-07 that role packs are not broadened for M4-H, implementer and reviewer packs keep their role-specific source and evidence inputs, and wider map serving must earn itself through later evaluation), pack provenance with pinned regeneration (a map removed or damaged after dispatch never changes the pack, so it never refuses a launch, relaunch or rotation), the resume row, the no-authority walk and `tools/perf/structural_map.py` (measured on Windows: 0.67 s at 10,000 paths and 3.0 s at 100,000, four git processes each; no very-large-repository support is claimed beyond 100,000 paths), with ADR-0015's amendment of 2026-10-07. Turning the switch on for M4-H is the operator's decision (SMQ-01). Ledger notes: PMP-17 and PMP-18 are carried by this slicing (T5-A only); PMP-73 is T5-E, evaluated with F19; PUI-20 is absorbed by PMP-07. The Q7 cold-start attestation checks `.aew/local/maps/`

*Later notes: `notes.d/F22.1/`, oldest first (`python tools/register.py show F22.1`).*

### F22.2

**Was:** T5-B then T5-C

**Closed:** 2026-10-24

**By:** held in HOLD-14

*Later notes: `notes.d/F22.2/`, oldest first (`python tools/register.py show F22.2`).*

### F22.3

**Was:** T5-D, sibling project-understanding indexes beside the maps, composed when their inputs exist and never fields of the structural record: the test relationship index (test to paths, symbols or components and the check lane, weaker path/name evidence without semantic facts, never making a test required), the constraint locator index (locators and terms for oracle rules, invariant-index ids, schema fields, guardrails, ADR sections, requirements-ledger ids and amendment-index entries, never rewritten prose), the semantic public-surface projection, and untrusted-string projection tests

**Closed:** 2026-10-24

**By:** held in HOLD-14

*Later notes: `notes.d/F22.3/`, oldest first (`python tools/register.py show F22.3`).*

### F23

**Was:** Pre-internal-alpha hardening candidates: a two-account deployment profile, WSL-hosted runs for Windows operators, a remote PR integration target (`DONE` on an observed merge), terminal-authenticated operator attribution for consequential decisions, Lead lease expiry

**Closed:** 2026-10-07

**By:** The operator's internal-alpha threat-model decision ([decision record](../design/decisions-2026-10-07-f23-internal-alpha-threat-model.md); ledger IAT): F18/F28 canonical-state and credential boundaries and the Linux/Rocky target REQUIRED; trusted-engineer use and Windows/WSL development with truthful weaker labels ALLOWED; local OS and session operator attribution SUFFICIENT; a separate full model OS account NOT REQUIRED; Lead inactivity expiry DEFERRED (E50); an operator-approved exact-commit push ALLOWED as a delivery capability (F33); automated PR and merge-provider integration DEFERRED, and Q14 no longer an internal-alpha gate

*Later notes: `notes.d/F23/`, oldest first (`python tools/register.py show F23`).*

### F24

**Was:** A second real harness adapter (Codex app-server or Claude Code headless) through the existing conformance suite and the live lane

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F24/`, oldest first (`python tools/register.py show F24`).*

### F24.1

**Was:** Codex runtime-semantics probe, the first slice of any Codex adapter work: the pinned Codex app-server against a scripted loopback model, on Windows and AEW_RL8 under AEW's own containment, with no real provider or credential

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F24.1/`, oldest first (`python tools/register.py show F24.1`).*

### F24.2

**Was:** Claude Code headless as a further harness adapter, a stretch goal after the Codex adapter: the same F24.1-style runtime probe first, then the conformance suite and the live lane

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F24.2/`, oldest first (`python tools/register.py show F24.2`).*

### F25

**Was:** An engine-owned cost and usage ledger: per run (model/profile, token categories, wall time, provider-reported and price-table cost), rolled up per invocation, Ticket and parent

**Closed:** 2026-10-24

**By:** held in HOLD-21

*Later notes: `notes.d/F25/`, oldest first (`python tools/register.py show F25`).*

### F26

**Was:** A minimal skill delivery path before the full registry: a project catalog, hash-pinned on the invocation, copied into the run's private harness state, as the smallest subset of the future F13 registry

**Closed:** 2026-10-24

**By:** absorbed into STG-15

*Later notes: `notes.d/F26/`, oldest first (`python tools/register.py show F26`).*

### F27

**Was:** Dogfood AEW on AEW: the register and AEW's own backlog as the real-repository dogfood

**Closed:** 2026-10-24

**By:** held in HOLD-02

*Later notes: `notes.d/F27/`, oldest first (`python tools/register.py show F27`).*

### F28

**Was:** Network containment on Linux (F-F): model-controlled runs, the Lead's included, in a private network namespace; provider traffic through a secretless in-sandbox shim to a supervisor-owned credentialing reverse relay with a fixed upstream, so the provider key never enters the sandbox; optional non-provider egress through a separate credentialless allowlist proxy; the supervisor reaches the harness server through the same shim; labels `proxy_only`, `isolated`, `shared`, `not_provided`; a self-test for egress denial, the bridge and server paths and secret absence; checks default to `isolated` and never widen past policy; a sanitized, checksum-pinned OpenCode catalog seed for air-gapped bundles

**Closed:** 2026-10-24

**By:** absorbed into STG-05

*Later notes: `notes.d/F28/`, oldest first (`python tools/register.py show F28`).*

### F28.1

**Was:** R-6, a check that a proxied connection did not end on this host, whatever the host's own network configuration does with it: after the handshake and before any byte is relayed, the proxy confirms the connection did not end on this host, in both families and every TCP state; a failed or incomplete check refuses

**Closed:** 2026-10-24

**By:** the operator's security depth reset of 2026-10-24, point 1: nothing a contained agent cannot reach is filed; host network configuration; the operator's deferral of the same day can reopen it (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F28.1/`, oldest first (`python tools/register.py show F28.1`).*

### F30

**Was:** Requirement impact analysis and the Project Profile: `aew impact <work-id>`, one deterministic operation with two consumers (an inspectable Lead command, and Plan Assurance calling it at Story creation) that computes a surface from the requirement's seeds through the maps (symbols, files and units at radius 1 by default, radius 2 only when budgeted), the test index and the constraint locators, labelled by how each entry was found and with a coverage statement of what was unavailable; its judgement part fills plan assurance v0.4's first-pass artefact and premise list, never a record kind of its own; Epics run on structural directory roles with declared reduced coverage until `components[]` exist; Tickets inherit and narrow the Story's surface; the Project Profile is KC §8's maps plus WC §16.15 guardrails as evidence-bound records with per-claim freshness, not a new layer or document set

**Closed:** 2026-10-24

**By:** held in HOLD-14

*Later notes: `notes.d/F30/`, oldest first (`python tools/register.py show F30`).*

### F31

**Was:** The Q12 attachment lifecycle: an AEW project attachment separate from the harness session (`aew open` attaches, by a fresh managed launch by default or an opt-in registered existing host, and `aew close` detaches it while the harness keeps running), a fresh Lead generation and fresh broker authority per attachment, re-hydration from canonical state on attach, stale authority for every older generation, no AEW project authority and no AEW-mediated project access through the detached attachment (read and query commands refused to that generation), a harness crash or host loss that revokes and stales the attachment's generation, the Lead attachment's requested and effective execution profile recorded, and the operator's disposition of running children when an attachment ends (close, crash, host loss, takeover or an uncarried handoff): drain by default (finish within a time limit, results held until a current Lead or the operator accepts them, any of the designer's stop conditions stops the run at once with an error report, while a legitimate negative result is held like any other), or, by the operator only at the operator terminal, stop now or release to manual; the integration custodian surviving an attachment's end with its lease held, its post-integration verifier draining, and no publish on a held result until the current generation accepts it

**Closed:** 2026-10-24

**By:** held in HOLD-17

*Later notes: `notes.d/F31/`, oldest first (`python tools/register.py show F31`).*

### F32

**Was:** The reference execution profiles: the Lead on GPT-6 Astra, Laguna S2.1 as the default worker, GPT-5.4 and approved open-source models as selectable workers, each qualified through the pinned harness (exact provider and model ids, effort variants, a live-lane run) before it is relied on; no workflow semantics keyed to a model's name

**Closed:** 2026-10-24

**By:** held in HOLD-20

*Later notes: `notes.d/F32/`, oldest first (`python tools/register.py show F32`).*

### F33

**Was:** Operator-approved exact-commit push, a delivery capability: after a Ticket is accepted on its verified local result, the operator approves pushing that exact commit to an explicit remote and ref, never forced; AEW records an attributable receipt (the accepted local commit, the requested remote and ref, the resulting remote SHA and ref) and checks the pushed remote object resolves to the exact accepted commit; push is never part of correctness or `DONE`, needs no second verification for crossing the network, and its failure is a delivery failure, never a retroactive `VERIFICATION_FAILED`

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F33/`, oldest first (`python tools/register.py show F33`).*

### F34

**Was:** Deterministic work conservation, the cross-cutting requirement's own obligations: the design review question (is the model being asked to do something AEW could safely and deterministically do itself?) asked of every significant feature or workflow, and the measurement that it works: navigation, workflow-ceremony and multi-agent metrics and the useful-reasoning ratio, on F25's usage substrate and F19's evaluation program

**Closed:** 2026-10-24

**By:** held in HOLD-04

*Later notes: `notes.d/F34/`, oldest first (`python tools/register.py show F34`).*

### F35

**Was:** Context-pack serving (R8), in the existing `ContextPacks` and `knowledge/context.py`, with no new component: a per-role, per-tier serving-policy table as archetype data (mandatory, opportunistic, on-demand, prohibited) with a conformance test per role; the derived-section rendering convention (source, revision, freshness and coverage or limitations in the heading, one item per line with an expansion reference, a degraded section as one labelled line); the execution profile's `context.budget_chars`, `context.orientation_max_chars` and `context.orientation` (minimal, standard or explicit) passed to the pack, the wiring E29 deferred; the criteria repeated last under explicit orientation if evaluation supports it; the reviewer's layout row; the pack's independence filter for reviewers and verifiers, with sentinel tests

**Closed:** 2026-10-24

**By:** held in HOLD-13

*Later notes: `notes.d/F35/`, oldest first (`python tools/register.py show F35`).*

### F36

**Was:** Weak-worker continuity (R2-B), platform-owned: the bounded handoff note (R2: an optional, worker-authored note of at most 2 KiB in the role report, a claim with references, never authority, citing paths and evidence ids, delivered to a replacement invocation's pack as labelled reference data, never automatically Knowledge), then the recitation (a zero-model-cost restatement AEW assembles from canonical and derived state: the goal or active criterion, the remaining criteria, plan tasks, changed files against the planned scope, checks performed, open findings and blockers, the latest handoff note; delivered on sufficiently long or complex runs through the run's inbox on an operational trigger and recorded like `harness send`)

**Closed:** 2026-10-24

**By:** held in HOLD-15

*Later notes: `notes.d/F36/`, oldest first (`python tools/register.py show F36`).*

### F37

**Was:** Field diagnostics, so that an operator running a released AEW elsewhere can find out what went wrong in a run and hand the evidence to AEW's maintainers safely: correlation IDs and timing carried across the CLI, engine, supervisor, harness and bridge, so one run's events line up end to end; an `aew debug bundle` command that gathers a run's diagnostic material (logs, state and timings) into one archive; and work-safe sharing: a metadata-only mode, a manifest of every item that the operator reviews before anything leaves the machine, and scrubbing of secrets, paths, internal names and content

**Closed:** 2026-10-24

**By:** held in HOLD-02

*Later notes: `notes.d/F37/`, oldest first (`python tools/register.py show F37`).*

### F38

**Was:** M6a Gate A, machine-policy closure: the M6a authorization model encoded as single-sourced machine data, and a checker that fails closed on any missing input (v0.9 §18's fifteen: the principal/status tuple table, the selector table, the implication table, the active grant-family mapping, the reserved-family registry, the active role-to-family table, the operator-approved named profile catalog, the shipped operation/projection catalog generated from the runtime definitions, the target and endpoint registries with canonical resource identities, the enforcement-path declaration table, the combination predicates, project policy overlays, pinned provider and harness projection hashes) and demonstrates every invariant over the actual shipped catalog: a total status with default `ILLEGAL`, deterministic attribution with its floors, implication closure, the active-family bijection with the reserved registry kept apart, selector coverage, profile safety and role liveness, operation catalog closure, one enforcement declaration per shipped tuple and delivery mechanism, registry consistency, and the Gate A fixtures

**Closed:** 2026-10-24

**By:** the operator's decision of 2026-10-24: M6a's rows close (design workspace, b9d6d01) (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F38/`, oldest first (`python tools/register.py show F38`).*

### F39

**Was:** M6a Gate B, deployed bypass-freedom: proof, against the exact pinned deployment (harness, providers, containment), that every model-reachable effect has a real enforcement owner, mediator and containment coverage is complete, no alternate harness or provider path bypasses policy, resource aliases cannot cross classes, project-authored code borrows no parent authority, and escape surfaces are absent or modeled; its preconditions (worker native authoritative edit/write hidden, F40; provider relay completeness; bridge and broker IPC isolation; the project-code process namespace; real mount and network containment; real target and endpoint canonicalization; filtered-shell enforcement; native child suppression or scoping; session-resume authority) and adversarial fixtures, with the written mediator-completeness argument for that deployment

**Closed:** 2026-10-24

**By:** the operator's decision of 2026-10-24: M6a's rows close (design workspace, b9d6d01) (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F39/`, oldest first (`python tools/register.py show F39`).*

### F40

**Was:** Worker source mutation only through an AEW source-mutation mediator (v0.9 §7, the designer's decision): harness-native authoritative source edit/write tools disabled in AEW worker profiles, the Implementer's included; a candidate delta or patch goes through the mediator, which checks the ticket revision, workspace and root before `write(source_tree)`; project-authored tools write only to the copy-on-write overlay or scratch and yield attributable candidate deltas; native `edit`, `write` and equivalents hidden or denied in the worker's model-visible schema, and provider and harness conformance proving them absent or unable to reach authoritative source; fixtures `native_source_edit_hidden`, `source_mutation_bypasses_mediator` and `source_tool_direct_write_blocked`

**Closed:** 2026-10-24

**By:** the operator's decision of 2026-10-24: M6a's rows close (design workspace, b9d6d01); MCD-01 and MCD-02 lapse with it (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F40/`, oldest first (`python tools/register.py show F40`).*

### F41

**Was:** Cross-feature integration, the activation gate: the design that connects the adopted owners (plans as governed parent work, section binding, a non-blocking interface-dependency edge, overlap, health, operator validation, delta review, plan underspecification) with no second lifecycle, invalidation, review-proof, health or coordination system; the activation gate that checks the required WC/F14 and WC §8 amendments are present (acceptance check 26); the field-log disposition table kept complete (check 25)

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41/`, oldest first (`python tools/register.py show F41`).*

### F41.1

**Was:** The Workflow Contract / F14 amendment for mandatory reviewed parent plans: every ancestor Epic and Story, Class 0 included, has a reviewed accepted plan, which changes `parent_paths["0"]` (the Class-0 parent path); the parent-plan guard as an input to F14 §17.1's single `DispatchDecision`, not a second dispatch engine; the reviewed-plan record contract (proposal, independent R1 review bound to the proposal's sha256, adoption by someone other than the proposer); the minimal Class-0 parent plan

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41.1/`, oldest first (`python tools/register.py show F41.1`).*

### F41.2

**Was:** The reviewed-plan contract, built: a derived `plan_phase` (no new stored parent work state); the parent-plan guard in `DispatchDecision`; plan proposal, review and adoption with the proposer barred from the reviewer and adopter slots (operator adoption or a Lead generation with a different admitted identity when the Lead proposed); the engine-derived planning/research child exemption (admitted purpose and the resolved effect envelope against the allow-list, never a label); the planner's own plan obligation met by its assignment; the migration of in-flight parents; Ticket planning kept conditional; `design_decision_required` as an attention reason, never a transition

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41.2/`, oldest first (`python tools/register.py show F41.2`).*

### F41.3

**Was:** The `non_mutating_paths` migration: the planning-child exemption changes the existing `non_mutating_paths` default, so adoption migrates project policy in `policy/gates.yaml` and no existing project silently keeps the old rule

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41.3/`, oldest first (`python tools/register.py show F41.3`).*

### F41.4

**Was:** Section-digest plan binding (E19-B with F5): every mutating descendant dispatch records the ancestor plan id and revision, the consumed section ids and an engine-computed normalized digest of each; the default consumed set (objective, requirements and acceptance criteria, the interfaces it names, its decomposition entry), narrowed only by the parent plan's structured decomposition; a governed, versioned normalization algorithm; staleness iff a consumed digest changes; the replacement-plan rules; `plan reconfirm --subtree` as an explicit recovery action that makes no evidence admissible

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41.4/`, oldest first (`python tools/register.py show F41.4`).*

### F41.5

**Was:** The Workflow Contract §8 amendment for the `interface_dependency` edge (V-1(b)): a new non-blocking edge kind for a contract or assumption dependency between work that may run in parallel, blocking edges keeping their meaning; the same amendment extends E19-B §7.5's `revision_impact_hold` trigger to accepted interface revisions on `interface_dependency` edges

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41.5/`, oldest first (`python tools/register.py show F41.5`).*

### F41.6

**Was:** The interface-dependency edge, built (E19-B with F9): the edge's fields; dispatch of a consumer while its provider is active when the accepted contract is current and the consumer is bound to its digest; engine-computed interface digests, never author-supplied, rename or removal counting as a change; the `INTERFACE_CONTRACT_DRIFT` integration and publish refusal; the E19-B `revision_impact_hold` on direct named consumers (dispatch, forward gates, publish; no recursive fan-out); hold clearing only by the Lead's F9 disposition (`RECONTEXTUALIZE` or `TICKET_REPLAN`) plus the engine's rebinding; the held worker can neither clear its own hold nor record either of those authority-bearing actions; a new attempt against the new digest

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41.6/`, oldest first (`python tools/register.py show F41.6`).*

### F41.7

**Was:** The overlap projection: read-only and advisory, coverage and unknowns first; signals from exact file overlap, declared blocking and interface dependencies, accepted interface digests, allocated identifiers and namespaces (from project policy data, not an AEW-global list), shared register, schema and config surfaces, build and test surfaces and qualified structural and symbol relationships; mechanically mergeable paths identified separately; unsupported Python import and symbol coverage reported as unknown; the advisory publish-overlap wake (§11 trigger 2)

**Closed:** 2026-10-24

**By:** held in HOLD-14

*Later notes: `notes.d/F41.7/`, oldest first (`python tools/register.py show F41.7`).*

### F41.8

**Was:** Two run-health fields (U1/H1): `current_or_longest_child_process`, sanitized (no command line, environment or model-authored arguments; a safe process or tool label, pid or identity where policy permits, age and status), and `age_of_last_durable_progress`

**Closed:** 2026-10-24

**By:** held in HOLD-15

*Later notes: `notes.d/F41.8/`, oldest first (`python tools/register.py show F41.8`).*

### F41.9

**Was:** `operator_validation` evidence: a new evidence kind integrated with the operator queue, verification observation evidence (not review evidence, never a substitute for required independent verification); a model-proposed script runs only after the operator approves the target host (resolved through the operator-pinned host registry), the full rendered content, the intended action and the capture schema; secrets only through secret-input channels and never persisted; only capture-schema fields persisted; a requirement-to-step coverage check that never claims adequacy

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/F41.9/`, oldest first (`python tools/register.py show F41.9`).*

### F41.10

**Was:** The delta-review packet: engine-derived facts (prior finding ids and status, base and reviewed revision, the engine-computed diff, files changed), qualified-derived facts with provenance only where a qualified T5/F30 source supports them, and claims (the implementer's finding-to-fix map, claimed assumptions and intent) labelled as claims and never promoted to evidence

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/F41.10/`, oldest first (`python tools/register.py show F41.10`).*

### F41.11

**Was:** The nit/observation fast path: the canonical severity vocabulary, with project `nit` presentation-only and an operator-pinned mapping to canonical `observation` that never remaps blocker, major or minor downward; after a CLEAR, eligible observation corrections get one cheap delta review over the full engine-computed delta; any blocker, major or minor finding, an unexpected behavioural change or a further cycle returns the work to the normal review path

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/F41.11/`, oldest first (`python tools/register.py show F41.11`).*

### F41.12

**Was:** Plan underspecification signals (F14): no plan-length score; structured `mechanisms[]` fields filled or `n/a: reason` (an advisory author claim review may challenge); review finding a material schema, registry key, reason code, error class, authority owner or mechanism invented during implementation and absent from the accepted plan; a worker's `design_decision_required`

**Closed:** 2026-10-24

**By:** held in HOLD-04

*Later notes: `notes.d/F41.12/`, oldest first (`python tools/register.py show F41.12`).*

### F41.13

**Was:** The engine-behavior citation rule: a claim about current engine behaviour used as a premise for a fix or a designer decision cites its code basis; AEW checks mechanically only that the cited path, symbol, test and revision resolve at the cited base commit; whether the code supports the claim stays a review judgment

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/F41.13/`, oldest first (`python tools/register.py show F41.13`).*

### F41.14

**Was:** The cross-feature integration design's field-log dispositions that hand work to owners outside F41's own rows, each to be taken up by its owner: #4 test scope (the launch-contract / test-policy owner); #10 public/private review (a review-artifact policy follow-up); #12 operator waiting queue (the existing operator-attention / dashboard owner: F15.5 for the operator-attention half, F20 for the dashboard half); #15 disk budget (the doctor / workspace-retirement owner, F18.2); #16 CI external check (an external-check / `wait --any` integration candidate, F9); #20 PR lifetime (an evaluator / process metric candidate, F19)

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F41.14/`, oldest first (`python tools/register.py show F41.14`).*

### F42

**Was:** Observability and Feedback, the first cross-cutting integration note (Q1, Q2): attribute, aggregate, detect, triage and verify over one process-event model; detectors and their candidates advisory; an accepted improvement verified on the same metric it was meant to move

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F42/`, oldest first (`python tools/register.py show F42`).*

### F42.1

**Was:** The canonical process-event model: one read-time schema and vocabulary with common ids (a pull request opened, ready or merged; a review round opened or settled; a fix round; CI queued, started or settled; a merge-main round; a conflict and its resolution; a lane blocked or unblocked; an integration wait); the native producer derives events from the transition log, as F25 derives its projections; check and validation durations are elapsed resource use, never F25 model usage

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F42.1/`, oldest first (`python tools/register.py show F42.1`).*

### F42.2

**Was:** The repository-process adapter: ingests pull request, CI, merge, review and blocking events from the repository host into F42.1's model, in its own append-only store outside control state, with a project id and a mapping from pull request to work unit for AEW's own development

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F42.2/`, oldest first (`python tools/register.py show F42.2`).*

### F42.3

**Was:** Structured role-context and skill feedback: bounded feedback from each role, under the existing Observability and Feedback design, capturing the role, the task, the pack and skill versions, missing, wrong or noisy information, and rule candidates when applicable

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F42.3/`, oldest first (`python tools/register.py show F42.3`).*

### F43

**Was:** The attention spine, three ordered slices; S1 and S2 together absorb every duplicate derivation of next actions, as consumers or producers where appropriate

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F43/`, oldest first (`python tools/register.py show F43`).*

### F44

**Was:** The consequential-fact owner registry: one row per semantic control fact or evidence kind that may influence dispatch, `ActionProjection`, a gate, progression, evidence admissibility, publication, Lead or operator attention, or reviewer, verifier or model context; each row records the fact, owner, producers, authoritative or advisory, the A3 classification reference (never restated), outbox consequences, the Lead or operator projection, consuming packs, the staleness or freshness rule, the data and redaction class and the schema version; it covers the top-level control keys and a declared unit-key inventory; CI and static checks fail on a fact with no complete row

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/F44/`, oldest first (`python tools/register.py show F44`).*

### F45

**Was:** Base-drift integration validation (AX-01): at prepare and rebuild the engine computes the drift between the Ticket's base and the integration base from Git and records its changed paths and their overlap with the Ticket's; the validation obligation consumes the recorded overlap under a legality-affecting key, `gates.post_integration.base_drift_overlap`; the integration verifier's pack gains an engine-derived section, the work integrated since this Ticket's base

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/F45/`, oldest first (`python tools/register.py show F45`).*

### F46

**Was:** The Operator Settings Surface: every operator-editable setting (marked by an explicit schema or registry annotation) has a dashboard editor showing its current value, description, valid values, classification, effective boundary, proposed value, validation result, diff and authority and effect; a generic schema renderer, custom editors where needed, and a completeness test proving every such setting has one

**Closed:** 2026-10-24

**By:** held in HOLD-19

*Later notes: `notes.d/F46/`, oldest first (`python tools/register.py show F46`).*

### F46.1

**Was:** The configuration read projection, first: the selected project's execution profiles and model routing as an engine read projection with its F20 HTTP adapter, carrying the digest a later Save binds to

**Closed:** 2026-10-24

**By:** held in HOLD-19

*Later notes: `notes.d/F46.1/`, oldest first (`python tools/register.py show F46.1`).*

### F46.2

**Was:** Validate, preview and apply inside the operator session: `aew settings set` and the dashboard's Save call `settings_apply` as the operator principal, which validates, previews the change bound to F46.1's digest, classifies it with F15.4 (a loosening re-authenticates), then writes, re-pins and records in one transaction with no pending-adoption window

**Closed:** 2026-10-24

**By:** held in HOLD-19

*Later notes: `notes.d/F46.2/`, oldest first (`python tools/register.py show F46.2`).*

### F46.3

**Was:** The model catalog, direct-provider first: a direct OpenAI-compatible provider's catalog (`GET /v1/models`) and the chooser built on it, through the adapter-owned model-id mapping (F47.4) that binds a catalog entry exactly to AEW's separate provider and model fields; the supplied exact model identity, capabilities shown as not supplied where the provider gives none, and a configured model the catalog lacks shown as an unavailable reference

**Closed:** 2026-10-24

**By:** held in HOLD-19

*Later notes: `notes.d/F46.3/`, oldest first (`python tools/register.py show F46.3`).*

### F46.4

**Was:** The web integration: the dashboard's configuration page on F46.1 to F46.3's accepted contracts and merged routes, with a compact, backend-supplied "What changes when I save?" explanation, and invocation pins, existing and future, accepted unchanged; the remaining configuration documents reuse the same workflow

**Closed:** 2026-10-24

**By:** held in HOLD-19

*Later notes: `notes.d/F46.4/`, oldest first (`python tools/register.py show F46.4`).*

### F47

**Was:** The vertical path: the shifts the designer approved on 2026-10-11 after the M4 operator acceptance session, so that on a fresh project the operator authenticates at most once, asks for a fix and gets it published while handling none of AEW's machinery, and the Lead spends no attention rediscovering AEW, as measured by the vertical UAT ([`vertical-uat.md`](vertical-uat.md)), the release gate

**Closed:** 2026-10-24

**By:** the designer's vertical-UAT ruling of 2026-10-23 (V-UAT-1 to -6): re-derived as V-01's oracle, its table places each slice; the vertical path's outcomes are V-01's (STG-13) (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F47/`, oldest first (`python tools/register.py show F47`).*

### F47.1

**Was:** Shift 1, one door for the Lead

**Closed:** 2026-10-24

**By:** the designer's vertical-UAT ruling of 2026-10-23 (V-UAT-1 to -6): re-derived as V-01's oracle, its table places each slice; A1: D-01 and O-01 (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F47.1/`, oldest first (`python tools/register.py show F47.1`).*

### F47.2

**Was:** Shift 2, the engine owns its bookkeeping

**Closed:** 2026-10-24

**By:** the designer's vertical-UAT ruling of 2026-10-23 (V-UAT-1 to -6): re-derived as V-01's oracle, its table places each slice; A3: D-01 and O-01; A2 not placed (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F47.2/`, oldest first (`python tools/register.py show F47.2`).*

### F47.3

**Was:** Shift 3, one operator session; containment mandatory

**Closed:** 2026-10-24

**By:** the designer's vertical-UAT ruling of 2026-10-23 (V-UAT-1 to -6): re-derived as V-01's oracle, its table places each slice; B4: CS-4; B1: G3; B2: A-25 and A-28; B3: I-6 (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F47.3/`, oldest first (`python tools/register.py show F47.3`).*

### F47.4

**Was:** Shift 4, doctor, preflight and live preflight

**Closed:** 2026-10-24

**By:** the designer's vertical-UAT ruling of 2026-10-23 (V-UAT-1 to -6): re-derived as V-01's oracle, its table places each slice; C1: P04; C2: the capabilities read P03 (A-25) (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F47.4/`, oldest first (`python tools/register.py show F47.4`).*

### F47.5

**Was:** The vertical UAT enforced

**Closed:** 2026-10-24

**By:** the designer's vertical-UAT ruling of 2026-10-23 (V-UAT-1 to -6): re-derived as V-01's oracle, its table places each slice; the enforce step is the V-01 milestone (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F47.5/`, oldest first (`python tools/register.py show F47.5`).*

### F47.6

**Was:** The discovery layer: mechanisms that find a whole class of problem without being pointed at it, over the vertical UAT

**Closed:** 2026-10-24

**By:** held in HOLD-02

*Later notes: `notes.d/F47.6/`, oldest first (`python tools/register.py show F47.6`).*

### F48

**Was:** The Windows containment backend for the Lead and the workers, so Windows can qualify

**Closed:** 2026-10-24

**By:** held in HOLD-06

*Later notes: `notes.d/F48/`, oldest first (`python tools/register.py show F48`).*

### F49

**Was:** Scoped fix briefs, as a product feature

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/F49/`, oldest first (`python tools/register.py show F49`).*

### F50

**Was:** Operator rules, the record contract: standing guidance the operator makes binding, as a **new governed record kind**, outside Knowledge's authority (not a Knowledge subtype)

**Closed:** 2026-10-24

**By:** held in HOLD-05

*Later notes: `notes.d/F50/`, oldest first (`python tools/register.py show F50`).*

### F51

**Was:** The network-egress qualification gap: the vertical gate qualifies authenticated publication only

**Closed:** 2026-10-24

**By:** absorbed into STG-05

*Later notes: `notes.d/F51/`, oldest first (`python tools/register.py show F51`).*

### F52

**Was:** The masks' host-only residuals: every socket a contained process can reach is masked, or found and judged, also on the hosts where the four known limits of ADR-0009's CS-2 amendment apply (the GSS-API proxy set up another way, socket names and the launcher's locale, shared listening sockets, a socket linked into place)

**Closed:** 2026-10-24

**By:** the operator's security depth reset of 2026-10-24, point 1: nothing a contained agent cannot reach is filed; every precondition is the host's own (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/F52/`, oldest first (`python tools/register.py show F52`).*

### O1

**Was:** A file named `nul` failed the fingerprint with git's raw error

**Closed:** 2026-10-01

**By:** The post-M3 cleanup: the snapshot refuses it by name, with the cause and the remedy (`snapshot/fingerprint.py`; `tests/integration/test_fingerprint.py`)

*Later notes: `notes.d/O1/`, oldest first (`python tools/register.py show O1`).*

### O3

**Was:** A goal met by changing its own inputs: AEW integrated a wrong T4 change after the implementer edited the sample data the goal was stated against

**Closed:** 2026-10-24

**By:** held in HOLD-04

*Later notes: `notes.d/O3/`, oldest first (`python tools/register.py show O3`).*

### O4

**Was:** The Lead is about 40% of AEW's cost

**Closed:** 2026-10-24

**By:** held in HOLD-10

*Later notes: `notes.d/O4/`, oldest first (`python tools/register.py show O4`).*

### O5

**Was:** The dogfood brief misstated the Lead's shell and read tools

**Closed:** 2026-09-30

**By:** Brief corrected (rubric A7); merged by PR #5

*Later notes: `notes.d/O5/`, oldest first (`python tools/register.py show O5`).*

### Q1

**Was:** The completion thresholds for ADR-0011 (H1 to H4, A1)

**Closed:** 2026-10-01

**By:** Approved by the operator and designer: H1, H3 and A1 kept; H2 measured at fixed output cardinality; H4 replaced by a history-independent `resume` (ADR-0011)

*Later notes: `notes.d/Q1/`, oldest first (`python tools/register.py show Q1`).*

### Q2

**Was:** Whether `resume` should keep sweeping all historical evidence

**Closed:** 2026-10-01

**By:** No: `resume` is an active-state operation; full cold-history verification is an explicit audit, and cold history stays first-class and discoverable (ADR-0011)

*Later notes: `notes.d/Q2/`, oldest first (`python tools/register.py show Q2`).*

### Q3

**Was:** Whether containment is required for personal real-project dogfood, or only for internal alpha

**Closed:** 2026-10-01

**By:** Required for both; unprivileged bubblewrap is enough for personal dogfood once its Rocky 8 probes pass, and internal alpha also needs isolation performance and operability acceptance (designer; see F2 and [`containment-and-process-ownership-rocky8-research-2026-10-01.md`](../research/containment-and-process-ownership-rocky8-research-2026-10-01.md) §8)

*Later notes: `notes.d/Q3/`, oldest first (`python tools/register.py show Q3`).*

### Q4

**Was:** Fail-closed rules for `verify classify` and risk class

**Closed:** 2026-10-24

**By:** held in HOLD-05

*Later notes: `notes.d/Q4/`, oldest first (`python tools/register.py show Q4`).*

### Q5

**Was:** The open questions each design lists

**Closed:** 2026-10-24

**By:** the rebaseline: designs are re-derived from the adopted requirements (D1), and their open questions with them (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/Q5/`, oldest first (`python tools/register.py show Q5`).*

### Q6

**Was:** Whether "a goal met by changing its inputs" (O3) becomes a registry failure class

**Closed:** 2026-10-01

**By:** Yes: `ACCEPTANCE_CONDITION_MUTATION` is canonical, with `PROTECTED_ACCEPTANCE_OVERLAP` ([`plan-assurance-and-classification-decisions-2026-10-01.md`](../design/plan-assurance-and-classification-decisions-2026-10-01.md) §3.1). O3 stays open until F14's fix is accepted

*Later notes: `notes.d/Q6/`, oldest first (`python tools/register.py show Q6`).*

### Q7

**Was:** What the next dogfood should use: tasks where one model session fails or regresses, since this one's tasks hit a ceiling. The plan assurance design's §28 proposes task families (T4 replay, diagnosis contrast pairs, oracle weakening, vacuous red, …) and configurations A–F.

**Closed:** 2026-10-07

**By:** [Q7 v0.3.1](../design/q7-m4h-value-gate-experiment-v0.3.1.md), adopted and design frozen by the operator (ledger VGX): M4-H is a real value gate in the B+ design, six fixed F1 to F3 cells x 12 runs per arm (144 primary R versus A runs), 30 descriptive R+ runs, 20 separately reported F4 premise runs; the equal-weight fixed-cell risk difference as the estimand, under a Jeffreys-binomial model with a 90% posterior credible interval (benefit needs mean at least +10 points and lower bound above 0); evaluator-side held-out isolation (F19's rule); cold-start attestation; two blinded mergeability reviewers. Prerequisites before execution: F15.5/F15.6 unattended PUBLISH_IF_CLEAN, F19's evaluator/arm-host split and release runner, F25 live run-usage telemetry for the evaluator's experiment-local USD cap

*Later notes: `notes.d/Q7/`, oldest first (`python tools/register.py show Q7`).*

### Q8

**Was:** Reconcile the capability design's six candidate failure classes (`CAPABILITY_CONTEXT_BLOAT`, `CAPABILITY_DISCOVERY_FAILURE`, `CAPABILITY_AUTHORITY_CONFUSION`, `CAPABILITY_SCHEMA_OVEREXPOSURE`, `HARNESS_FEATURE_SUPPRESSION`, `HARNESS_AUTHORITY_LEAK`) with the failure-class registry, and add its invariants (§16) to the invariant index, before F13 is implemented

**Closed:** 2026-10-24

**By:** STG-15: CAPR-03's statuses replace the candidate failure classes (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/Q8/`, oldest first (`python tools/register.py show Q8`).*

### Q9 (decisions)

**Was:** The plan assurance design's §33 decisions and its order relative to ADR-0011 and M4

**Closed:** 2026-10-01

**By:** Adopted as the post-M3 direction; see F14 for the decisions. It does not block M4 after ADR-0011; assurance-compatible extension points and deterministic primitives land early enough that M4 creates no conflicting workflow semantics

### Q9 (reconciliation)

**Was:** Reconciling plan assurance's 15 candidate failure classes and its invariants with the registry and the invariant index

**Closed:** 2026-10-01

**By:** 12 canonical classes, 3 merged or represented as detail, refusal codes kept separate from class names, 10 new invariants ([`plan-assurance-and-classification-decisions-2026-10-01.md`](../design/plan-assurance-and-classification-decisions-2026-10-01.md) §3.1); the index edits are the designer's

### Q10

**Was:** Risk-class calibration (Class 0 unreachable for test-backed fixes; example anchoring; missing positive criteria)

**Closed:** 2026-10-01

**By:** One Class 0–4 system; Class 0 is defined by an engine-enforced eligibility predicate (structural checks, recorded semantic assertions, no active hard trigger), and a failing Class 0 request is refused with reasons, never silently reclassified ([`plan-assurance-and-classification-decisions-2026-10-01.md`](../design/plan-assurance-and-classification-decisions-2026-10-01.md) §2, §3.2); the Workflow Contract amendment is adopted ([`workflow-contract-amendment-class0-2026-10-01.md`](../design/workflow-contract-amendment-class0-2026-10-01.md))

*Later notes: `notes.d/Q10/`, oldest first (`python tools/register.py show Q10`).*

### Q11

**Was:** Reconcile the provider research (`../design/aew-phase6-airgap-capability-research-2026-10-01.md`) with M3's rules before F12 and F13 are designed further

**Closed:** 2026-10-24

**By:** STG-15: FIRST-BUNDLE.md and COVERAGE.md reconcile the research with the register (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/Q11/`, oldest first (`python tools/register.py show Q11`).*

### Q12

**Was:** Harness hosting, the operator session and native-feature integration: startup, the seat and session lifecycle, execution-profile resolution, wrapper ownership, hosting, and which native harness features are integrated (architecture review D-AR5)

**Closed:** 2026-10-06

**By:** The designer's decision, adopted with the operator ([decision record of 2026-10-06](../design/decisions-2026-10-06-q12-hosting-and-lead-attachment.md)): AEW owns the project attachment, the Lead seat, generations, profile selection and provenance, and the harness owns model execution. An attachment opens and closes (`aew open`, `aew close`) independently of the harness; closing or losing it revokes AEW authority and stales its generation without ending the model, the harness, its context or admitted child work; every attachment is a fresh generation that re-hydrates from canonical state. Reference models: GPT-6 Astra for the Lead, Laguna S2.1 the default worker, GPT-5.4 and approved open-source models selectable. Amends ADR-0004, ADR-0005, ADR-0009 and ADR-0010; F31 builds the lifecycle, F32 the reference profiles; F18, Q11 and U6 are unblocked. Where the knowledge, capability and dashboard services run goes to the F18 hosting design (record §12)

*Later notes: `notes.d/Q12/`, oldest first (`python tools/register.py show Q12`).*

### Q13

**Was:** Accept the architecture review response after the lead developer's review; promote its decisions to their homes; decide the five items it did not disposition (ARV-01 to ARV-05)

**Closed:** 2026-10-05

**By:** Accepted by the operator after the designer reconciled the three differences (MCP first; I1 and I2 built; the outbox sequencing per ADR-0012 and the M4-D split). The response moves to `docs/design/` as a decision record. Its decisions already have homes: ADR-0012, ADR-0013, the typed Lead surface v0.2, F21 to F27, E18 to E30. ARV-01: the review's "do not build yet" list accepted (F9, F3's sparse workspaces, F20's write actions: on measured need); ARV-02: E30 accepted as work; ARV-03: E19's; ARV-04: F15 and F8; ARV-05: F19 and E35

*Later notes: `notes.d/Q13/`, oldest first (`python tools/register.py show Q13`).*

### Q14

**Was:** The remote integration target's scope (not before internal alpha, the operator decided on 2026-10-07, F23): when the provider's merge commit differs from the candidate, does `DONE` need a second post-integration verification on it or is verification on the candidate plus containment enough? Also undecided: the first provider, whether AEW ever merges through the provider's API with a precondition, and how the proposal's CI checks relate to AEW's verification

**Closed:** 2026-10-24

**By:** held in HOLD-09

*Later notes: `notes.d/Q14/`, oldest first (`python tools/register.py show Q14`).*

### Q15

**Was:** The nit-rule divergence (cross-feature integration v0.5 §21): the product's rule (§15) needs one bounded delta review after nit corrections, while AGENTS.md (PR #181) had the author fix nits with no new review; the operator was to align AGENTS.md or keep an explicit, documented project-policy exception

**Closed:** 2026-10-10

**By:** The operator aligned AGENTS.md with the product rule in PR #193 (2026-10-10): after a CLEAR whose only open points are nits, the author fixes them and one short delta review covers the whole diff since the CLEAR, once per CLEAR (AGENTS.md §1, "Nits after a CLEAR get one short delta review"); no project-policy exception remains (ledger CFI-97, CFI-98). Recorded with the [architecture integration decision record](../design/decisions-2026-10-11-architecture-integration.md) §5

*Later notes: `notes.d/Q15/`, oldest first (`python tools/register.py show Q15`).*

### U1

**Was:** Stall detection in `aew harness wait`: return `stalled`, naming the tool and how long, when a tool call has run N minutes with no events

**Closed:** 2026-10-24

**By:** held in HOLD-15

*Later notes: `notes.d/U1/`, oldest first (`python tools/register.py show U1`).*

### U2

**Was:** An investigation-review coverage contract

**Closed:** 2026-10-01

**By:** Absorbed into F17 (designer; `8eac795`, PR #6)

*Later notes: `notes.d/U2/`, oldest first (`python tools/register.py show U2`).*

### U3

**Was:** F14 addendum: operator-provided factual premises can be decision-sensitive, not only explicit diagnoses

**Closed:** 2026-10-24

**By:** held in HOLD-04

*Later notes: `notes.d/U3/`, oldest first (`python tools/register.py show U3`).*

### U4

**Was:** Lead usage, provider and cost observable in AEW

**Closed:** 2026-10-24

**By:** held in HOLD-21

*Later notes: `notes.d/U4/`, oldest first (`python tools/register.py show U4`).*

### U5

**Was:** Generated per-archetype command references in role briefings and the Lead's guide

**Closed:** 2026-10-24

**By:** held in HOLD-02

*Later notes: `notes.d/U5/`, oldest first (`python tools/register.py show U5`).*

### U6

**Was:** A decision on Lead state isolation

**Closed:** 2026-10-24

**By:** decided by the F18 hosting design v0.6 section 5; its build is in HOLD-17 (register rebaseline, design workspace `b598fdc`)

*Later notes: `notes.d/U6/`, oldest first (`python tools/register.py show U6`).*

### U7

**Was:** Automatic stall recovery (interrupt plus a standard nudge)

**Closed:** 2026-10-24

**By:** held in HOLD-15

*Later notes: `notes.d/U7/`, oldest first (`python tools/register.py show U7`).*

### U8

**Was:** Make a run that ended without its expected output conspicuous in `aew harness wait`

**Closed:** 2026-10-10

**By:** `aew harness wait` exits 20 (documented in its help; distinct from every error's 1 to 10) when the run it returns ended `ended_without_evidence`, and its result starts with a one-line `headline`; the result is printed as before, and a timed-out wait and every other ending still exit 0. The typed surface's `harness_wait` keeps its StageResult shape and description; its result carries the same headline (PR #165). `tests/regression/test_uat_2026_09_30.py`. Lands before the M4-H treatment freeze, so it is in the treatment: Lead guide +67 bytes; wait's headline and exit 20; reason_code on wait and status rows; new next-action wording. The typed surface is unchanged.

*Later notes: `notes.d/U8/`, oldest first (`python tools/register.py show U8`).*

### U9

**Was:** Review skills unavailable: reviewer cards request `code-review`, and nothing provides it to the run

**Closed:** 2026-10-24

**By:** absorbed into STG-15

*Later notes: `notes.d/U9/`, oldest first (`python tools/register.py show U9`).*

### U10

**Was:** A small correction to an accepted record needs a full replacement record

**Closed:** 2026-10-24

**By:** held in HOLD-07

*Later notes: `notes.d/U10/`, oldest first (`python tools/register.py show U10`).*

### V1

**Was:** A provider key that expires mid-run: relaunch should re-read the key, or report the auth failure as its own status

**Closed:** 2026-10-10

**By:** The OpenCode adapter classifies a turn that failed with 2.0.18's `provider.auth` (401, no retry) as `reason_code: provider_auth_failed` on the run record, in the existing `crashed` status (no new status); `harness status`, `harness wait` (with a headline) and the next action name the provider_env variables, never a value. AEW's own records (the run record, the event log, the snapshot, and the status, wait and next-action output) drop a provider message that may concern a credential (an auth-like type, or 401, 403 or 407), which can quote part of the key, and redact key-shaped text from any other; the harness's private state under the run's `harness/` directory keeps what the harness itself stores. A relaunch starts a new server whose environment is built from the launcher's at launch, so it reads the key as it is then; inside a Lead session the launcher is the session's broker, whose environment is fixed when `aew opencode` starts, so the next action says to restart it with the new key first, and V5 tracks picking the key up without the restart (PR #165). `tests/integration/test_opencode_adapter.py`. Lands before the M4-H treatment freeze, so it is in the treatment: Lead guide +67 bytes; wait's headline and exit 20; reason_code on wait and status rows; new next-action wording. The typed surface is unchanged.

*Later notes: `notes.d/V1/`, oldest first (`python tools/register.py show V1`).*

### V2

**Was:** A clearer path when the Lead wrapper exits with an invocation active: the seat stays held, the credential is gone with the wrapper, and re-acquiring is refused

**Closed:** 2026-10-05

**By:** `aew lead acquire`'s refusal names the holder (generation, session, acquired at), says that a gone session means `aew lead takeover` at an operator terminal, and derives what a takeover would do by running its interruption on a copy of the state: the active invocations it interrupts, the Tickets that become INTERRUPTED (recovered as `aew resume` lists), and only a lease that survives, for `aew integrate reconcile`; `next: aew lead takeover` in its details. Q12 keeps the wider seat lifecycle

*Later notes: `notes.d/V2/`, oldest first (`python tools/register.py show V2`).*

### V3

**Was:** Whether review-type work should default to a plan-bound reviewer

**Closed:** 2026-10-24

**By:** held in HOLD-04

*Later notes: `notes.d/V3/`, oldest first (`python tools/register.py show V3`).*

### V5

**Was:** A rotated provider key without restarting `aew opencode`: the Lead broker picks up a new value of the variables `provider_env` names when it launches a run

**Closed:** 2026-10-24

**By:** held in HOLD-20

*Later notes: `notes.d/V5/`, oldest first (`python tools/register.py show V5`).*
