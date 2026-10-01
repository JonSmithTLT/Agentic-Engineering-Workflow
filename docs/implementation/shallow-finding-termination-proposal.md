# Shallow finding termination: design proposal (F17)

- **Version:** v0.2, 2026-10-01. A proposal, not adopted design. The designer and a second reviewer reviewed v0.1 the same day. Their decisions are in §10 and §11 and are folded into the text.
- **Status:** phase 1, an evaluation baseline, comes before any implementation (designer). Tracked as [`future-work.md`](future-work.md) F17, which absorbs U2.
- **The pattern** (designer and operator, 2026-10-01; provisional name `SHALLOW_FINDING_TERMINATION`): a role discovers a relevant observation, claim, anomaly, capability or boundary condition. It then closes its assignment without tracing it far enough to establish whether it has a consequential effect. This is a candidate for the failure-class registry, which the designer owns.
- **Goal:** when AEW encounters a consequential clue, it reliably determines whether the clue leads somewhere important before declaring the work complete. Longer reviews are not the goal.

## 1. Summary

**Make stopping visible, not reviews longer.** Add one concept to the evidence model, the *open consequential observation*. This is a finding on a declared consequential surface whose consequence is neither established nor bounded. If the experiments show it is needed, it becomes an obligation, like a plan-bound gate: closing the work needs a recorded disposition (traced, bounded, inside a documented limit, a follow-up, or accepted open).

Every other part of the design consumes that one concept, each adding one bounded step:

- the author takes one hop;
- the reviewer goes one hop past the author and fills an ask-level coverage matrix;
- the verifier samples outside what was already traced;
- a project-level join pairs what was left open across tickets.

**Why this shape.** The run records show three different stopping points, not one generic shallowness: closure by a known-limit label, a trust surface checked by its name rather than by what can write it, and runtime claims checked at the cited line rather than at the produced artifact. In every case the stop was silent: nothing in AEW recorded that a consequential thread had been left open. B1 was found precisely because plan and gate relationships are explicit in AEW; the proposal makes the observation-to-consequence relationship explicit in the same way.

**The split.**

- **The contract** owns the finding's shape and status, the closeout obligation, the coverage matrix and the depth limits.
- **A skill** owns how to trace well: enumerating consumers of a surface, testing a known-limit claim, and grounding a claim in the produced artifact.

**Order of work.** Build the evaluation corpus and measure today's AEW first. Then run skill-only and schema-only experiments, the schema including deterministic path tagging. Add the obligation, and its Workflow Contract amendment, last and only if those fall short.

## 2. What the runs show

Sources:

- the AEW-Lead review of the M3 tag (2026-10-01), with T-0001 and T-0003 sealed records;
- the operator's SPT investigation (2026-09-30), with the UAT review of its synthesis.

| Case | What the role established | Where it stopped | Mechanism |
|---|---|---|---|
| R1, T-0001 (investigator; Class 2 security ticket; 9 of 200 steps; no review) | "An agent shell may also write any operator-writable file", cited at `src/aew/harness/contract.py:15-23` | Closed as "known limit... not a novel escape", because the containment label `workdir_separation_only` names it | **Closure by label.** The reviewer brief's control ("nothing that decides anything may read [run records]") was in its reading set, but it never checked that control against the primitive |
| R1, T-0003 (investigator and verifier; priority 8, model-writable run records, explicitly assigned) | `run.json` is writable; status and wait read evidence from the store; relaunch liveness reads `run.json` | At the readers of `run.json`. The verifier re-inspected `runlog.py:77-111`; the request queue starts at line 114 | **Surface by name.** "Run records" was read as one file, not as everything an agent can write under the run directory. The verifier repeated the author's path |
| SPT headless claim | "MCP selects smoke, bridge or headless (first filename-matched JAR)", validated at `run-ghidra-mcp.sh:16-29` | At the launch script. The headless JAR it selects is never built at the pinned version, and the operator's "I run it in Docker as the headless server" went unchallenged | **Grounding at the citation.** A runtime claim was checked against the line that asserts it, not the artifact that runs |
| SPT item 9 (version swap, local ZIP) | Scattered version inputs; a mirror lane and a local-ZIP lane proposed | Missed `.dockerignore` excluding `*.zip` (a supplied ZIP never reaches the build) and Kaiju's per-version, date-pinned download (a version change breaks it) | **Consequence not followed through the build.** The proposal's effect on its consumers was never traced |

- **Structural factor 1: the R1 chain was split across top-level tickets.** The primitive was in T-0001 and the control to check in T-0003, and no step joined them. T-0001 was accepted 78 seconds after its record, with `--assurance none`, although it was a Class 2 security ticket.
- **Structural factor 2: review confirmed rather than extended.** In SPT, three reviews of an 82 KB synthesis took about 30 seconds each and spot-checked about five claims. In the M3 run, the T-0003 verifier cited the same line ranges as the author.
- **Coverage is not depth.** SPT's synthesis had an item 9 section, so an item-level coverage check would have passed. Both misses sat under asks that item 9 states directly ("shouldn't break everything", "hand the build a Ghidra zip myself").

## 3. Thesis: the stop is silent because the relationship is not represented

A discovery record that stopped at an observation is indistinguishable from one that traced it:

- **Facts** need a statement and citations. A cited primitive is a complete fact, whether or not anyone asked what it enables.
- **Hypotheses** carry a `confirm_by`, but nothing obliges anyone to confirm them.
- **Unresolved questions** are free text. No gate reads them.
- **Review findings** already have an `observation` severity, but it carries no obligation.
- **Completion gates** check that the accepted plan and the execute record are current. They never look at what a record leaves open.

AEW is reliable where a relationship is explicit and gated, which is why the AEW arm found B1. A consequence chain (fact, consumer, trust, effect, control) is represented nowhere, so neither roles nor the engine follow it.

The design therefore represents the one link that matters: from a consequential observation to its established consequence, or to its bounded absence. AEW cannot judge whether an impact trace is correct. It can make sure a consequential observation is never closed by silence.

## 4. Approaches compared

| Approach | Stops it addresses | What AEW can enforce | Cost on benign work | Fan-out risk | Verdict |
|---|---|---|---|---|---|
| Finding schema (observation vs impact established) | All become visible; none is fixed by it alone | Presence, status, citations resolve, closeout obligation | None for untagged findings | None | **Core** |
| Role contract (consequence questions) | T-0001 label closure; SPT item 9 | That the answers exist | One bounded hop per tagged finding | Low with a hop limit | **Yes, as the author's single hop**, driven by the schema |
| Reviewer goes past the author | T-0003 repeat; SPT shallow reviews | A count of traced-further items; the coverage matrix | Proportional to class | Low | **Yes.** Does nothing where no review runs (T-0001), so not the only layer |
| Follow-up investigation | Long chains that would bloat one role | Depth and budget limits | Only when chosen | High without limits | **Yes, as one disposition**, depth 1, budgeted |
| Graph of fact, consumer, effect | The cross-ticket split in R1 | Typed links in the finding; a project-level join | Small | Low | **Lightweight only**; no project-wide graph |
| Skill or prompt scaffold | All, softly; helps weaker models most | Nothing | Context in every run | None | **Yes, for how to trace**; compact card text until skills reach runs (U9, F13) |
| Budget or depth floor | T-0001's 9 of 200 steps | Step or time floors | High, and misdirected | None | **No as a primary lever**; duration stays a measured signal |

## 5. Proposed design

### 5.1 Consequential surfaces and tagging

**The surfaces:**

- authority;
- trust boundaries (who can write or reach what);
- credentials and secrets;
- evidence and gate admissibility;
- persisted state;
- public behaviour and compatibility;
- the build and runtime chain (what is actually produced and run).

**Tag sources:**

- **Project policy.** A `surfaces` map of path globs tags every finding that cites a matching path. This is deterministic, needs no model judgement, and ships in phase 2. The operator owns or approves the list, and the Lead may propose changes, because otherwise the Lead could shrink the list that binds it. For AEW itself, tagging `src/aew/harness/**` as a trust boundary would have tagged T-0001's primitive, which cites `src/aew/harness/contract.py`.
- **The role** that wrote the finding.
- **A reviewer**, who may add tags.
- **Operator-stated premises** enter as observations when they materially constrain the plan or the investigation, as the SPT headless premise did. Other operator sentences do not.

Untagged findings carry no obligations, so benign observations stay free. Tagging is now the single point of failure (second review), so tag recall and tag rate are measured separately (§8.4). If broad surfaces such as persisted state, public behaviour or the build chain tag too much benign work, they become policy-only: tagged by path globs, never by default.

### 5.2 Finding fields

These are additive to discovery facts, review findings and verification claims.

| Field | Meaning |
|---|---|
| `surface` | One or more tags from §5.1 |
| `established` | `observation`, `traced` (a cited chain to a consequence) or `demonstrated` (a probe, test or execution shows it) |
| `trace` | **Consumer:** what reads, trusts or builds from this, cited. **Effect:** what that makes possible. **Control:** what should prevent it, cited. **Control verified by:** a test, probe, code read, or none |
| `consumer_search` | The executable query that found the consumers, not a description. For example `{"tool": "git-grep", "pattern": "run_dir(", "paths": ["src"]}`. A verifier can re-run it, and AEW can re-run `git grep` queries itself (§5.3) |
| `disposition` | When not traced: `bounded`, `known_limit`, `follow_up` or `accepted_open` (§5.3) |

### 5.3 Dispositions

- **`bounded`.** The recorded query found no consumer, or every consumer it found was examined and none gives a consequence. At ingest, AEW re-runs a `git grep` query against the evaluated commit. Every file it hits must appear among the examined consumers. This makes `bounded` partly mechanical: AEW checks the search, though not whether the query was the right one.
- **`known_limit`.** Cites the documented limit, says why this consequence is inside the limit's scope, and names the control that bounds it. This targets T-0001's stop. "An agent can write operator-writable files" is a documented limit; "the supervisor decides on files an agent can write" is not inside it, because it breaks the control the brief documents.
- **`follow_up`.** A Ticket with `origin: <finding>` and depth 1. It cannot spawn another follow-up without the operator, and each parent has a follow-up budget (F7).
- **`accepted_open`.** The Lead accepts the observation open, with a reason. On an authority, credential or trust-boundary surface at Class 2 or above, a reviewer or the operator must concur. A tripwire watches the share of `accepted_open` among dispositions: above a threshold set from the baseline, `status` and `doctor` report it and the operator reviews. This is the cheap exit the second review warned of, the same pattern as self-classification.
- **Verifier sampling.** Any `known_limit` or `bounded` disposition on an authority or trust-boundary surface automatically enters the verifier's sample, in addition to the set difference in §5.5. Closure by label can recur as a well-formed but wrong argument that passes every presence check.
- **Deduplication with a guard.** Open observations are deduplicated by (surface, consumer), so three roles seeing the same primitive create one obligation. A disposition covers only the consumers it names, so one `known_limit` can never silently cover a later, different consumer of the same surface.

### 5.4 The obligation (phase 3, only if needed)

At ingest, every tagged finding left at `observation` with no disposition becomes an open consequential observation on its unit. It shows in `gate show`, `status` and the resume next action, and closing the unit is refused while any remain open. One accepted open goes to the project-level join (§5.5) and, when the unit has a parent, to the parent, which cannot close until its synthesis has considered it.

The obligation follows the record's content, not the plan's assurance. A Class 2 security ticket accepted with `--assurance none` (T-0001) would still have stopped at its open observation. This changes when work may close, so it needs a Workflow Contract amendment. That amendment comes last, and only if the skill-only and schema-only experiments fall short (designer and second reviewer).

### 5.5 The layers

- **Author (investigator, implementer).** Tag, then take one hop for each tagged finding. That means enumerating consumers of the whole surface (everything the actor can write or reach, not the named file), recording the query, then tracing, bounding, or applying the known-limit test.
- **Reviewer.**
  - Fill a coverage matrix at the granularity of the request's asks, not its numbered items: SPT item 9 had a section but missed two of its asks.
  - Extend *k* tagged findings one hop past the author's last hop, recorded as `extends: <finding>`. *k* starts at 1, 2 and 3 for Classes 1 to 3 and is a tunable value set by evaluation, not a contract constant.
  - Add tags and findings where the author missed them.
- **Verifier.** The engine lists the findings and claims already traced by the author and the reviewer; the verifier includes at least one outside that set, plus every `known_limit` and `bounded` on an authority or trust surface (§5.3). Runtime claims on the build and runtime surface are checked against the produced artifact or by execution, or reported inconclusive.
- **Join across tickets.** Two parts, decided after review:
  - The Lead guide requires a parent Story when one request is split into several tickets. AEW cannot detect a split on its own, so this is a rule for the Lead.
  - The deterministic backstop is a project-level query over all accepted-open observations. It proposes candidate pairs by shared surface tag or cited path against every other record's consumers, and the model judges each pair. The fix does not depend on the Lead remembering to group tickets; R1's tickets were top-level.
- **Follow-ups.** Depth 1 and budgeted (§5.3).

### 5.6 Lifecycle

1. A role records a finding. A policy glob, the role or a reviewer tags it with a consequential surface.
2. The author takes one hop. If it is traced, bounded or inside a known limit, it is closed by the author. Bounded and known-limit dispositions on authority or trust surfaces still go to the verifier.
3. Otherwise it is an open consequential observation, and closeout is refused until it is disposed of (phase 3).
4. If a review runs, the reviewer extends it one hop past the author and may add findings.
5. The Lead disposes of it: trace, follow-up (depth 1), or accept open with a reason (with concurrence on trust surfaces at Class 2 and above).
6. An observation accepted open goes to the project-level join and, if the unit has one, its parent.

### 5.7 How the four stops would have gone

- **T-0001.** The primitive cites a trust-boundary path and is tagged by policy. A `known_limit` disposition must explain why a supervisor acting on agent-written files is in scope. It cannot, so the role checks readers of agent-writable directories, or leaves the observation open for the Lead. Even then, verifier sampling would select that disposition.
- **T-0003.** The surface is "everything an agent can write under its run directory". A recorded query for callers of the run directory hits `runlog.py`, and the hits must all be examined, which reaches `take_requests`.
- **SPT headless.** A build-and-runtime claim at the citation level is flagged, and the verifier must ground it in the image. The headless JAR is not there.
- **SPT item 9.** The proposal changes the build surface. Consumers of `GHIDRA_VERSION` and of the build context include Kaiju's download and `.dockerignore`.

## 6. Contract vs skill

The contract owns *whether* a thread was closed and *how* it was closed; the skill owns *how to trace well*. AEW never judges whether an impact is real.

| Element | Lives in | Why |
|---|---|---|
| Surface list; policy `surfaces` path globs (operator-owned) | Contract (policy schema) | A closed vocabulary is checkable; path tagging is deterministic |
| `established`, `trace`, `consumer_search`, `disposition` | Contract (evidence schema, additive) | Makes observation vs impact structural |
| Trace citations resolve against the evaluated snapshot | Engine | Already done for evidence paths |
| `git grep` queries re-run at ingest; hits covered by the examined consumers | Engine | Makes `bounded` partly mechanical |
| Open observation blocks closeout until disposed (phase 3) | Engine, with a Workflow Contract amendment | Changes when work may close |
| `accepted_open` concurrence on trust surfaces at Class 2+; the share tripwire | Engine | A count and a rule, not a judgement |
| Coverage matrix has a row per ticket-level ask | Engine | The asks are in the ticket's acceptance list |
| Reviewer extends at least min(*k*, open findings) | Engine; *k* is tunable policy | A count, not a quality |
| Verifier samples outside the traced set, plus trust-surface bounds and limits | Engine | Set operations over finding ids |
| Follow-up depth and budget; dedup guard | Engine | Prevents fan-out and silent coverage mechanically |
| Project-level candidate pairs for the join | Engine proposes, model judges | Pairing by tag or path is mechanical; relevance is not |
| Sub-asks inside a stakeholder item; whether an untagged observation is consequential; completeness of a consumer list; correctness of an impact; the known-limit scope argument | Model; sampled by review and verification | Cannot be checked mechanically |

Skill content (compact card text until skills reach runs, U9 and F13):

1. Follow the writer, not the name: enumerate everything an actor can write or reach, then who reads it.
2. A limit label is a claim: say what the limit covers, and test whether this consequence is inside it.
3. Ground runtime claims in what is produced and run, not in the line that asserts it.
4. For a proposed change, list the consumers of every input it changes.
5. Record the query, not a description of it.
6. Stop rule: one hop, then trace, bound, or hand back as open. Never an essay.

## 7. Tradeoffs

- **Recursive explosion.** Depth is capped in three places: the author takes one hop, the reviewer one more, and anything longer becomes a depth-1 follow-up within a per-parent budget. Deduplication by surface and consumer keeps three sightings to one obligation, and its guard keeps one disposition from covering new consumers.
- **Class 0 stays cheap.** Obligations attach only to tagged findings. A Class 0 change touching a policy surface path is tagged, which existing hard triggers would usually lift out of Class 0 anyway. Class 0 has no reviewer *k*.
- **No threat-model essays.** A trace is four short fields with citations, and `bounded` needs only the recorded query.
- **Role independence.** The reviewer must see the author's traces to go past them, but its coverage matrix comes from the ticket's asks, not the author's framing. The verifier samples outside both. For the highest class, F14's acceptance-first idea applies: a reviewer seals its expected surfaces before reading the record.
- **Where tracing belongs.** At every layer, each with one bounded job. No layer is asked to finish the chain alone.
- **Tag volume.** Measured on benign real work (§8.4). If it is too high, broad surfaces become policy-only. The aim is that the Lead never learns to rubber-stamp.
- **Deterministic vs judgement.** AEW checks that every consequential thread ends in a recorded state, and re-runs the searches it can. Models decide what the state is.

## 8. Evaluation

### 8.1 Corpus

Each consequence case has a control where the right answer is "bounded, control verified", so that over-reporting is measured as well as reach.

| Case | Setup | Measures | Pass |
|---|---|---|---|
| R1-given | AEW at the freeze tag; the ticket states the primitive and asks whether reviewer isolation holds | Expansion alone | Reaches "the supervisor acts on unauthenticated request files, so one run can stop or message another" |
| R1-discover | T-0001's ticket as written | Discovery plus expansion | As above, or an open observation the Lead must dispose of |
| R1-split | T-0001 and T-0003 as decomposed, then the Lead's synthesis | The cross-ticket join | The synthesis connects the primitive to the request queue |
| R1-control | The same tickets on the fixed commit (`812b492`) | False alarms and essay length | Bounded: requests are recorded in control state and checked |
| R1-synthetic | A small job runner: workers can write a spool directory and a daemon acts on its files | Memorisation (the fix is now public) | The same chain on unfamiliar names |
| SPT-headless | SPT at the UAT commit: "does headless MCP run as configured?" | Grounding in the produced artifact | Finds that the selected JAR is never built. Control: a variant that builds it |
| SPT-item9 | Item 9 as asked | Consequences of a change through the build | Finds `.dockerignore` excluding `*.zip` and Kaiju's per-version download. Control: both fixed |
| Coverage | A request with six asks and an author record seeded to miss two | Review coverage | The review reports both missing asks |

**Held-out cases.** All eight cases come from the two misses the design was built to catch, which is a selection-bias risk. Each new incident becomes a held-out case, never used to tune prompts, *k* or surfaces. A decision to proceed to phase 3 must hold on the held-out cases too.

### 8.2 Arms

All on the same model:

- the plain LLM;
- AEW today;
- skill-only (the card scaffold);
- schema-only (the fields, policy path tagging and recorded queries, no obligation).

Then, only if those fall short:

- the schema with the obligation;
- the full design.

Comparing skill-only with schema-only separates the prompt's effect from the structure's.

### 8.3 Protocol

- **Runs:** at least five per case and arm. At that size results are directional: 2 of 5 against 4 of 5 is a signal, not proof.
- **Rubric:** fixed before running.
- **Hidden material:** answers, controls and held-out cases stay outside the distribution during tested runs, as for the dogfood.

### 8.4 Metrics

- **Tag recall:** the share of the rubric's consequential findings that were tagged at all, by any source. This is measured separately from reach, since tagging is the new single point of failure.
- **Reach:** for tagged findings, the share of runs that reach the consequence.
- **False consequences:** the rate on controls.
- **Tag rate on benign real work:** tags and obligations per ticket on ordinary dogfood tickets in a large real repository, not only on the controls.
- **Size and spend:** words per trace on benign findings; cost, tokens and wall time.
- **Depth and fan-out:** hops taken and follow-ups created.
- **Lead behaviour:** the mix of dispositions, and the `accepted_open` share the tripwire watches.

## 9. Phasing and cost

1. **Corpus and baseline.** Build the cases and run AEW today and the plain LLM. Nothing is implemented first (designer).
2. **Skill-only and schema-only experiments.** Run separately:
   - **skill-only:** the compact scaffold in the investigator, reviewer and verifier cards;
   - **schema-only:** the new fields with no obligation, policy path tagging (moved here from phase 5 at the second review, because it is cheap and needs no model judgement) and recorded queries.
3. **The obligation, only if needed.** Open observations, dispositions with concurrence and the tripwire, the dedup guard, and the project-level join. It needs a Workflow Contract amendment, which comes last.
4. **Review changes.** Reviewer `extends` and verifier sampling. The ask-level coverage matrix (formerly U2) is independent of everything else and can ship on its own schedule.
5. **Backstops.** Sealed reviewer expectations for the highest class.

**Expected cost (an estimate to measure).** Near zero on untagged work. On tagged findings, one hop is typically a recorded search and a few reads; T-0003 was a few calls away from the request queue. In the M3 run, role invocations cost $0.24 to $0.47 each, so even a doubling on tagged findings is small next to a missed Blocker. Tag volume is the cost to watch.

**Where it fits.** F17 absorbs U2 and links F14 (plan and premise assurance, a different mechanism) and U3 (premises). It shares F7's budgets. It belongs after M3's acceptance.

## 10. Decisions (2026-10-01)

| # | Question | Decision |
|---|---|---|
| 1 | Who owns a project's `surfaces` policy? | The operator owns or approves it; the Lead may propose changes (second reviewer) |
| 2 | Does `accepted_open` need concurrence? | Yes, from a reviewer or the operator, on authority, credential and all trust-boundary surfaces at Class 2 and above, plus a tripwire on the `accepted_open` share (second reviewer) |
| 3 | Placement | A distinct future-work item, F17, that absorbs U2 and links F14 and U3, not inside F14 (designer). The coverage-matrix work must be able to ship independently (second reviewer) |
| 4 | Reviewer *k* | 1, 2 and 3 for Classes 1 to 3 as a starting point; a tunable evaluation parameter, not a contract truth (both) |
| 5 | Operator premises (U3) | They enter as observations, but only when they materially constrain the plan or investigation (designer); the SPT headless premise would have been caught (both) |
| 6 | Baseline first? | Yes: run phase 1 before implementing or freezing anything (both) |
| 7 | Workflow Contract amendment | Last, and only if the baseline and the skill-only and schema-only experiments show the obligation is needed (both) |
| 8 | Parent for split requests? | Yes, require a parent Story, and make candidate-pair generation a project-level query over all accepted-open observations, so the fix does not depend on the Lead remembering to group tickets (second reviewer) |

## 11. Second review: changes adopted

| Point | Change in v0.2 |
|---|---|
| Tagging is the new single point of failure | Tag recall is a separate metric (§8.4). Policy path tagging moved from phase 5 to phase 2 |
| `accepted_open` is a cheap exit for the Lead | Concurrence is widened to all trust-boundary surfaces at Class 2+, with a tripwire on the share (§5.3) |
| `known_limit` can recur as a well-formed but wrong argument | `known_limit` and `bounded` on authority or trust surfaces always enter the verifier's sample (§5.3, §5.5) |
| `consumer_search` free text cannot be re-checked | It records the executable query. AEW re-runs `git grep` queries at ingest, and the hits must be covered (§5.2, §5.3) |
| Tag volume could swamp the Lead | Tag rate is measured on benign real work; broad surfaces can become policy-only (§5.1, §8.4) |
| Deduplication needs a guard | A disposition covers only the consumers it names (§5.3) |
| Corpus overfit | New incidents become held-out cases; five runs per cell is directional only (§8.1, §8.3) |

## 12. Still to settle by evaluation

- the tripwire threshold for the `accepted_open` share;
- the tag-rate budget per ticket, and which surfaces become policy-only;
- an operational test for "materially constrains" for operator premises;
- the reviewer *k* values.
