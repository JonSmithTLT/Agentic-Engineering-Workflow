# AEW ProjectArchitect Concept Research and Evaluation Plan

**Version:** 0.1  
**Date:** November 25, 2026  
**Audience:** AEW operator, Lead, and owners of context, mapping, evaluation, and continuation  
**Status:** Research proposal. Findings below support evaluation; they do not record adoption of a product change.  
**Scope:** Study useful concepts and implement any justified improvement independently within AEW. No ProjectArchitect code, prompts, hooks, templates, or runtime integration are proposed for import.

## 1. Recommendation

ProjectArchitect contains ideas worth testing in AEW, especially how it narrows retrieval questions, assembles task briefs, evaluates a brief through the work it enables, and records enough state for another agent to continue. The strongest opportunity is to improve the quality and efficiency of AEW's existing agent workflow through a small set of controlled evaluations.

The recommended next action is to establish the current AEW baseline and prepare three experiments:

1. **Brief effectiveness:** Does a more explicit, deterministically assembled handoff improve the next worker's verified outcome?
2. **Question-scoped retrieval:** When does delegating a bounded research question improve on direct use of AEW's existing map and source tools?
3. **Continuation quality:** Can a more complete progress record reduce lost work, repeated investigation, and incorrect resumption after interruptions?

The evaluation method is itself one of the most useful concepts: judge a brief by what the recipient successfully accomplishes, including the cost of both producing and using it. ProjectArchitect implements that relationship in its expert benchmark, where a second worker acts on the brief and held-out checks grade the resulting work. [PA-04]

**Keep semantic mapping on its existing track.** ProjectArchitect's inspected source-outline tool uses regular expressions and text structure. It does not provide the AST, resolved symbols, or semantic relationships needed to answer the broader AEW codebase-understanding goal. [PA-09]

Each experiment should end with one of four decisions: existing AEW behavior is sufficient; a narrowly scoped change is justified; evidence is inconclusive and needs a specified follow-up; or the concept is not useful for the tested task class. A finding that the current implementation is sufficient is a successful research outcome.

## 2. Research basis and limits

### 2.1 Pinned sources

| Project | Inspected revision | Role in this review |
| --- | --- | --- |
| ProjectArchitect | `cac77da62f0e2b81b3c8f60ba3f70742471ca609` | Source of candidate concepts and published benchmark evidence. |
| AEW | `eece01e5499f2249084e34b229cd2bc4a0428a19` | Comparison baseline for the current mapping implementation and recently completed work. |

The ProjectArchitect review used a complete repository path inventory and 33 selected source, agent, template, test, and benchmark files. The selected file contents were checked against their Git blob identities. The AEW comparison used the mapping query implementation, adapters, structural/slice code, and implementation notes at the revision above.

This is a source-based concept assessment, not a new execution of ProjectArchitect or a completed AEW experiment. Published ProjectArchitect results establish what its records report; they do not establish an AEW performance improvement. Proposed benefit statements below are hypotheses.

The review is bounded to agent context, code discovery, evaluation, and recovery. Relay credential storage and renewal are separate AEW workstreams. The source repository's [license][PA-15] is retained in the evidence record for provenance; this plan proposes independent AEW design from the observed concepts.

### 2.2 Evidence language

- **Observed:** A behavior, instruction, or result present in the pinned source.
- **Inference:** A conclusion about likely fit or a limitation derived from that source.
- **Proposal:** An AEW-specific behavior or experiment to evaluate.

These distinctions matter because a prompt asking for a short answer does not establish an enforced output limit, and a well-designed benchmark does not establish effectiveness for a different codebase or workflow.

## 3. AEW baseline to preserve

The comparison must start from the newer AEW implementation. Earlier observations that workers lacked map reads, or that a globally capped directory list could hide a task's small directory, are historical for this baseline.

| Area | State at the inspected AEW revision | Consequence for this research |
| --- | --- | --- |
| Shared map queries | `aew.maps.query` supplies a common `aew/map-answer/v1` envelope with basis, evidence class, observation, coverage, freshness, omissions, limits, locators, and a next step. [AEW-01] | Build on this contract. A research helper does not need a second map-answer format. |
| Worker access | F15.8's map-read slice provides `map.show` and `map.search` through the worker bridge. Reads are tied to the invocation basis and do not refresh or select a map. [AEW-02] | Evaluate how agents use the tools already available. Do not propose worker access as a new PA-inspired feature. |
| Scoped structural views | E293 corrects the capped-directory case by recovering scoped rows from the map's source tree, with identity checks and stated limits. Pinned slice content is preserved during pack regeneration. [AEW-03] | Include the case in qualification, while recognizing that the original defect has already been addressed. |
| Search evidence | Exact path/directory lookup uses the source basis; the lexical fallback observes the workspace at query time. These are explicitly different observations. [AEW-01] | Preserve that distinction in retrieved answers. A commit label alone must not imply that dirty workspace text came from that commit. |
| Negative answers | The query contract reserves `NOT_FOUND` for a completely searched domain and records omissions and unsupported capability. [AEW-01] | Retrieval must preserve these distinctions instead of collapsing all unsuccessful searches into “not found.” |
| Semantic capability | The capability declaration reports relations and codefacts as `NOT_SUPPORTED (not built)` and evaluation as unevaluated. [AEW-01] | Do not claim that a retrieval agent or outline supplies resolved semantic relationships. |
| Broader map surface | The F15.8 note identifies symbol/caller/callee and other follow-on operations as outside its completed read slice. [AEW-02] | Separate completed map reads from the remaining mapping roadmap. |

Before running experiments, record the exact AEW revision and execution-policy settings used by each arm. If AEW advances, either keep the frozen experimental baseline or explicitly re-baseline all compared arms. A product default changing must not silently change a treatment.

## 4. Concept disposition

The labels below identify concepts within this research document. They are not new AEW register entries.

| Concept | Value to investigate | Fit and overlap | Recommended disposition |
| --- | --- | --- | --- |
| C1. Grade a brief through downstream work | Detect briefs that sound useful but cause an incorrect implementation or excessive rediscovery. | A method for the existing evaluation and context work. | **First priority:** establish this as the evaluation approach. |
| C2. Question-scoped retrieval | Return only evidence needed to answer one bounded question; keep deeper source access available. | Uses current F15.8 queries and ordinary source reads. | **Pilot:** compare against direct tools by task class. |
| C3. Deterministic task and role brief assembly | Preserve mandatory objectives and constraints while selecting relevant context reproducibly. | A refinement of existing context packs, subject to an overlap check. | **Pilot with C1:** change only a demonstrated deficiency. |
| C4. Continuation records with evidence and rejected hypotheses | Help a successor resume without repeating failed investigations or confusing unfinished work with completed work. | Fits the existing continuation and custody lifecycle. | **Pilot:** exercise planned and unexpected interruptions. |
| C5. Outline followed by bounded source reads | Make source navigation easier without reading an entire file. | Useful interaction pattern; PA's implementation is heuristic, not a semantic index. | **Defer implementation:** consider as a view over AEW's mapping work. |
| C6. Compact running-task digest | Let an operator or supervising agent see current work and pending handbacks. | Likely overlaps current task/status presentation. | **Inspect first:** add only missing, useful fields. |
| C7. Decision retrieval with supersession | Retrieve the current decision, provenance, and replaced decisions together. | A presentation/use pattern for existing authoritative records. | **Inspect first:** avoid a second decision store. |
| C8. Review repeated reads and context waste | Find avoidable rediscovery and test better context selection. | Fits evaluation and usage telemetry. | **Use diagnostically:** measured improvements must follow. |

The concepts come from PA's retriever definitions, card/brief construction, benchmark, continuation template, task hooks, decision guidance, and phase-close method. The priorities and dispositions are AEW-specific recommendations. [PA-01] [PA-02] [PA-03] [PA-04] [PA-07] [PA-10] [PA-11] [PA-12]

## 5. Priority concepts and AEW adaptations

### 5.1 Briefs that are judged by their consequences

**Observed in ProjectArchitect.** The expert benchmark first produces a brief. A fixed benchmark coder receives that brief in a fresh fixture checkout, implements the change, and is evaluated with hidden behavioral checks. The expert outcome incorporates the coder's result, and the reported arm cost includes the consequence run. [PA-04]

**Hypothesis for AEW.** A handoff that explicitly preserves the objective, acceptance conditions, settled constraints, and relevant source evidence can improve correct completion while reducing the recipient's need to rediscover context. The improvement is not established by making the brief shorter or more polished.

PA also constructs role-relevant context from document sections and assembles task information such as reads, scope, dependencies, verification, progress, and return requirements. That deterministic assembly is a more concrete concept than simply instructing a model to “write a good summary.” [PA-03] [PA-03b]

**Proposed adaptation.** Inspect an actual AEW context pack and worker handoff first. For each missing or unreliable field, define a minimal change in the existing pack mechanism:

| Brief element | Purpose |
| --- | --- |
| Task objective and explicit exclusions | Preserve what the recipient is being asked to accomplish. |
| Acceptance conditions and verification method | Make completion assessable independently of the recipient's prose. |
| Relevant settled constraints | Prevent context reduction from dropping requirements. |
| Source basis and evidence locators | Let the recipient verify important claims against the correct state. |
| Dependency outcomes and their status | Distinguish a dependency's assertion from accepted evidence. |
| Open questions and known limitations | Expose uncertainty before the recipient acts on it. |
| Selection and omission manifest | Explain which context was included, what was omitted, and why. |
| Required return information | Support the existing handback and review process. |

Do not add fields solely because PA has an equivalent. If AEW already supplies them reliably, retain the current format and measure it.

For the first comparison, keep the worker model, tools, task, source basis, policy, and budget constant. Change only the brief assembly or explicitly named fields. Evaluate the produced implementation or answer, not merely the brief's structure. Any later comparison of worker models should be a separate experiment.

### 5.2 Question-scoped retrieval

**Observed in ProjectArchitect.** Its code retriever is instructed to answer one question within an explicit scope, use targeted searches and bounded source reads, return source locations, and produce a short answer. Larger investigations can leave a durable report. These are agent instructions; the selected definition does not by itself prove enforcement of every stated budget or evidence-quality property. [PA-01]

**Hypothesis for AEW.** A small research task can reduce the supervising agent's context load for questions requiring several source reads. An extra agent can also add latency, cost, and another opportunity for error. Direct lookup is likely the better baseline for simple path and symbol-location questions.

**Proposed adaptation.** Use a question-scoped helper only where synthesis is needed. It should consume the current map contract and ordinary source tools rather than maintain a separate index.

The request should identify the question, permitted scope, relevant source/working-state identity, answer intent, and resource budget. The response should provide:

- The concise answer, with facts separated from hypotheses.
- Source spans and the source identity needed to reproduce each consequential claim.
- The domain actually searched and any excluded or unsupported areas.
- The existing terminal/status distinctions, including incomplete searches.
- A useful next step when the answer cannot be supported within the available scope.

Preserve AEW's current distinction between commit-based structural observations and workspace-based lexical observations. A changed workspace may require a new observation or explicit content identity before the parent relies on its source span. [AEW-01]

The parent must remain able to inspect the source behind a consequential claim. Returning a report pointer should not become a rule forbidding evidence inspection. Reports that are later useful belong in the existing knowledge-admission process; filing a report does not make its conclusions authoritative.

Keep the mandatory scope, authority, and task constraints in a helper's context. The useful idea is selective context; removing essential rules to make the prompt smaller would defeat the task.

### 5.3 Continuation and recovery records

**Observed in ProjectArchitect.** The progress template distinguishes verified work, unfinished edits, commands and results, rejected hypotheses with evidence, the current hypothesis, next actions, exact identifiers, prior coder runs, and commissioned reports. Its instructions preserve earlier attempts instead of overwriting them, and call for updates after meaningful reports as well as at planned handoff. [PA-07] [PA-07b]

PA's recovery hooks also contain handling for reconstructed progress and unread child reports. These are useful examples of failure cases to test, even where AEW already has a different lifecycle implementation. [PA-10] [PA-10b]

**Hypothesis for AEW.** A successor can resume more accurately when the record explains both the current state and why earlier approaches failed. A list of completed commands alone may lose the investigation that made those commands meaningful.

**Proposed adaptation.** Extend only missing fields in the existing continuation record. Bind each record to task, attempt, source state, and relevant work/custody identities. Keep the following categories explicit:

| Category | Required distinction |
| --- | --- |
| Verified completion | What was checked, against which state, with an available result or artifact. |
| Unfinished work | Which files or actions remain incomplete and what the next agent must inspect. |
| Investigation state | Current hypothesis versus rejected hypotheses and their supporting evidence. |
| Pending work | Active children, queued handbacks, unread results, and unresolved external dependencies. |
| Recovery observation | State reconstructed from logs or the checkout versus state recorded by the prior agent. |
| Next action | A concrete continuation step, subject to current custody and constraints. |

A handoff must cover relevant staged, unstaged, and untracked work, or explicitly identify what was not preserved. PA's suggested plain `git diff` patch is not a complete representation of all three categories; AEW should define and verify the needed recovery manifest for its own workspace model. [PA-08]

Recovery must reconcile actual custody before creating another worker or claiming completion. A closed parent attachment does not establish that a child stopped. A reconstructed narrative cannot supply missing approval or accepted evidence. This work should operate within AEW's current lifecycle rather than adopt PA's session-ownership assumptions.

Record explicit decisions, evidence, and progress. Private model reasoning traces are not required for this concept.

## 6. Relationship to semantic codebase mapping

The user's broader goal is a tool any supported agent can use to understand a codebase accurately. A useful decomposition is:

| Layer | What it can establish | Role in the AEW plan |
| --- | --- | --- |
| Structural map | Files, directories, source basis, and bounded orientation. | Current foundation. |
| Lexical navigation | Matching text and candidate locations. | Current search capability; text matches require interpretation. |
| Parsed syntax | Declarations, scopes, signatures, and source ranges recognized by a parser. | A potential semantic-roadmap input. |
| Resolved semantics | References and relationships resolved under a language/build configuration. | Needed for stronger symbol, caller, callee, type, and impact claims. |
| Behavioral evidence | What tests or observed execution demonstrate in a stated environment. | Complements static evidence; does not prove all possible behavior. |

The observed PA outline provides navigational rows and snippets of documentation using regular expressions and indentation/brace handling. Its listed file extensions cover Markdown, Python, C#, and JavaScript/TypeScript variants; C and C++ are not listed. It is therefore a reference for the **outline → source range → source inspection** interaction, not evidence of a completed semantic mapping system. [PA-09]

For AEW, evaluate that interaction over the existing query surface as language support develops. A future result should state the language/profile, source identity, observation method, supported relationship kinds, resolution limitations, and omissions. Keep a textual mention, parsed reference, resolved call, and observed runtime call distinguishable.

For C/C++ in particular, the research questions include which build configuration is represented, how conditional compilation and macros affect observations, and how unresolved indirect calls are reported. These questions belong to the semantic-provider design; a short outline does not answer them.

**Scope decision:** The three proposed experiments can begin with current structural and lexical capabilities. They should neither block on a complete semantic index nor be presented as completion of that index. F15.8 is the existing query surface, and the shared query implementation identifies F22.2 as a future extension path. [AEW-01] [AEW-02]

## 7. What the published PA evaluation establishes

PA provides useful evaluation mechanics, including pinned fixtures, clean checkouts, preserved outputs, behavioral grading, and grading tests that exercise known solutions and defective variants. Those mechanics are concepts AEW can implement independently using its own fixtures and requirements. [PA-04] [PA-06] [PA-06b]

The inspected published results have narrower meaning than a general claim of agent productivity:

| Published record | Reported coverage | Interpretation |
| --- | --- | --- |
| November 23, 2026 full run | Coder 28/28; expert 12/12; retriever 28/28; partner 10/10. | Successful results under the record's particular tasks and graders. |
| November 25, 2026 canary | Coder 4/4; expert 2/2; partner 1/1; retriever not run. | A smaller check; not equivalent to repeating the full suite. |
| Both inspected records | One repeat; hooks disabled. | Limited evidence about run-to-run variation or the complete operational hook/lifecycle behavior. |

These figures are reported in PA's result files; they were not reproduced as part of this review. The full run and canary also use different agent versions. The role totals must not be added together and described as independent coding tasks. [PA-05] [PA-05b]

Two grader limitations matter when designing AEW's experiment:

- The retriever grader checks expected citation coverage and token presence. That does not establish that every answer claim is entailed by its cited source, that numeric values and units are correct, or that additional false statements are absent.
- The partner grader checks routing behavior such as the first selected agent/effort or a no-delegation response. It does not establish successful completion by the delegated worker. [PA-06]

PA's savings calculation also includes a counterfactual cost model and assumptions about context/cache behavior. Its fitted quota model addresses provider usage/cost relationships. These may suggest diagnostics, but they do not supply an AEW savings forecast or prove that a proposed workflow causes a productivity gain. [PA-13] [PA-13b]

**Research implication:** Use the benchmark's consequence-based design, strengthen the evidence grader where needed, and measure AEW's actual outcomes. Do not adopt a published savings multiplier as an expected benefit.

## 8. Experiment design

### 8.1 Common protocol

Begin with existing AEW fixtures, evaluation runners, and context-pack comparisons. The first deliverable is an overlap assessment: which required measurements and cases already exist, and which small additions are necessary?

For each comparison, freeze:

- Repository revision and any intentional workspace changes.
- Task text, permitted scope, acceptance conditions, and held-out oracle.
- Supervising and worker model/version, settings, tools, execution policy, and supported capabilities.
- Context assembly version and input artifacts.
- Total cost, elapsed-time, and tool-use allowances, including helpers.
- Retry, timeout, escalation, and infrastructure-failure handling.

Use independent workspaces and no cross-arm result sharing. A known solution should pass the oracle; a deliberately incomplete solution should fail it. Hidden checks must reflect requirements the task actually communicated. A hidden test should not penalize the worker for an undisclosed requirement.

Generate candidate context from the permitted source through the declared extraction policy, never from the answer key. Use separate unscored tasks to tune the harness and keep scored fixtures out of prompt tuning. Where practical, reviewers should score final answers and handoffs without knowing their arm.

As a **planning starting point**, select eight representative fixtures for an experiment and run three repetitions per arm: 24 top-level attempts per arm. Adjust the size to the available budget and task diversity before execution. This is exploratory evidence, not a claim of statistical sufficiency. Count all helper and downstream calls separately as well.

Counterbalance execution order where possible. Keep context-treatment comparisons separate from provider/model comparisons. Record provider or infrastructure changes that could affect comparability.

### 8.2 Experiment A: brief effectiveness

**Question:** Does a specific brief-assembly change help an otherwise unchanged worker complete the task?

**Arms:** A0 uses the current AEW pack and handoff. A1 changes only the named brief fields or selection procedure. Both retain mandatory constraints and equivalent access to allowed evidence. First exclude a trivial explanation such as a broken baseline omitting an already-required artifact.

**Fixtures:** Choose real AEW-style changes with reviewable results: a local fix, a change spanning modules, a regression involving a prior decision, and a task with a relevant dependency handback. Include a case where excessive or stale context could mislead the recipient. Use fresh AEW-authored fixtures or existing AEW fixtures.

**Measure:** Correct completion, acceptance-check results, constraint preservation, unsupported claims, additional source discovery, retries, operator intervention, total latency, and all-attempt cost. Retain the exact brief, resulting patch/answer, and verification artifacts.

**Decision rule:** Prefer A1 only if it preserves required quality and produces a worthwhile improvement in at least one preselected operational measure. A shorter brief alone is insufficient. If both arms already succeed easily, increase task discrimination before making a broad claim.

### 8.3 Experiment B: direct tools versus question-scoped retrieval

**Question:** For which question classes is a helper worth its overhead?

**Arms:** B0 uses current map/source tools directly. B1 adds a bounded retrieval helper over the same allowed evidence and capabilities. Keep the supervising and downstream worker configurations fixed. Include helper time, retries, synthesis, and any parent verification reads in B1's totals.

**Fixture matrix:**

| Case | Required behavior |
| --- | --- |
| Simple exact path or local fact | Direct tools should remain available; determine whether delegation adds only overhead. |
| Question requiring several source files | Synthesize with evidence from every necessary location. |
| Small directory beyond the structural record's global cap | Find it through the corrected scoped route or report a genuine limitation. |
| Complete search with no match | Support a negative only within the completely searched domain. |
| Capped or exhausted search | Report incompleteness; do not turn it into absence. |
| Stale map or modified workspace | Preserve the observation's real basis and verify consequential source facts. |
| Unsupported semantic relation | State that the available tools do not establish the relation; offer a bounded source investigation if appropriate. |
| Numeric/configuration fact | Return the exact value, unit, and relevant configuration, not merely a matching token. |

**Measure:** Supported-answer accuracy, evidence entailment, relevant evidence coverage, false-negative rate, unsupported-claim rate, latency, cost, and usefulness to the subsequent task. Score citation correctness separately from answer correctness.

**Decision rule:** Adopt a helper only for question classes showing a measured benefit without unacceptable quality loss. It is valid to keep direct lookup as the default and recommend a helper for a narrower multi-file class.

### 8.4 Experiment C: continuation and recovery

**Question:** Does an enhanced record let a successor continue accurately after materially different interruptions?

**Arms:** C0 uses current AEW continuation behavior. C1 adds only the missing record fields or update points identified during baseline inspection. Use existing recovery fixtures where they cover the required state.

**Interruption cases:**

1. Planned rollover after meaningful progress.
2. Parent termination before consuming a completed child's report.
3. Restart while a child is still active or its status is uncertain.
4. Interruption with relevant staged, unstaged, and untracked work.
5. A rejected hypothesis whose evidence would otherwise be lost.
6. Multiple continuation attempts, verifying that an earlier record remains available.

**Measure:** Correct reconstruction of work state, preservation of pending results and user constraints, repeated investigation, time to a verified continuation, duplicate execution/effects, lost work, and false completion claims.

**Decision rule:** The candidate must preserve custody and evidence boundaries and recover the required fixture state. Any false completion, lost required work, or unauthorized duplicate action blocks promotion of the candidate. If the baseline has the same failure, record it separately for the existing owner; a shared defect is not a pass.

A recovered narrative may help explain a task. Acceptance still depends on the actual state and verification evidence.

### 8.5 Metrics and interpretation

| Measure | Definition or reporting rule |
| --- | --- |
| Verified completion | An attempt satisfies the task oracle and required constraints. Report counts and denominator by task family. |
| Supported answer | Consequential claims are supported by the cited evidence at the stated basis. Report unsupported extra claims separately. |
| Total effort | All parent, helper, worker, retry, escalation, and verification activity. Do not exclude failed attempts. |
| Cost per verified completion | Total cost across all attempts divided by the number of verified completions. If none complete, report undefined with total cost and zero completions. |
| Latency | End-to-end elapsed time, including waiting and recovery. Show distribution and outliers, not only the mean. |
| Recovery quality | Preserved state and evidence, successful continuation, duplicate effects, and lost results/work. |
| Resource reduction | Fewer reads/tokens or smaller context. A diagnostic measure, conditional on acceptable outcomes. |
| Failure attribution | Agent, harness, grader, provider, or infrastructure where supported by evidence. Retain all attempts and explain exclusions. |

Keep actual billed cost, token usage, price-equivalent estimates, and hypothetical counterfactual savings in separate fields. Missing price information is unknown, not zero. Report preparation/indexing cost separately from warmed execution, include it in the applicable total, and state any amortization assumption. Record observed cache usage rather than assuming a fresh conversation has uncached billing.

Specify the minimum useful benefit and acceptable quality tolerance before examining treatment results. Mandatory constraints and evidence/custody requirements are pass/fail. For variable success rates, report per-task results and uncertainty; a small pilot may justify a second trial without justifying broad deployment.

## 9. Work packages and ownership

These are proposed research work packages, not new register rows or implementation commitments. Use the current register to resolve owners before assignment.

| Package | Action and deliverable | Existing owner to consult | Exit condition |
| --- | --- | --- | --- |
| R0. Baseline and overlap | Produce a capability/field checklist with links to current packs, query results, continuation records, and existing evaluations. | Context, mapping, evaluation, and lifecycle owners. | Each proposed change is classified as already present, deficient, or unverified. |
| R1. Evaluation preparation | Select fixtures; freeze configurations; define the oracle, accounting, and decision rules. | Existing evaluation owner; context-pack experiment owner where applicable. | Fixtures discriminate correct/incomplete outcomes and the protocol is reproducible. |
| R2. Brief comparison | Run Experiment A with the smallest justified variant. Retain briefs, outputs, costs, and failure explanations. | Context owner with evaluation support. | Decision recorded for C1/C3 with evidence and limitations. |
| R3. Retrieval comparison | Run Experiment B using the current map/source tools. Analyze by question class. | F15.8 query surface owner and evaluation owner. | Decision identifies exactly which questions, if any, benefit from a helper. |
| R4. Recovery comparison | Exercise Experiment C using current custody/continuation mechanisms. | Existing lifecycle/custody and context owners. | Required states recover correctly; any improvement and remaining failures are documented. |
| R5. Disposition and routing | File a short results memo linking each finding to an existing owner/row or a justified new request. | Lead and operator. | Each concept is retained as-is, proposed as a narrow change, deferred with a reason, or rejected. |

Run R0 before adding implementation. R1 establishes the common evaluation method. R2 and R3 can proceed independently once their fixtures are ready. R4 can reuse functional recovery tests before any model-based trial is necessary. R5 follows actual evidence.

For mapping, preserve the current shared-query direction under F15.8/F22.2. Resolve any evaluation, knowledge, cost, or lifecycle register identifiers from the current register rather than creating duplicates based on this document.

### Lead's first assignable task

**Prepare the baseline and experimental protocol.** Inspect one representative current pack/handoff, one multi-file retrieval task, and one interrupted task record. Return the overlap checklist, proposed fixture set, exact candidate deltas, run accounting, resource cap, and predeclared decision criteria.

This is enough to make the next action concrete without committing to a new retrieval service, semantic provider, controller, or memory system.

## 10. Boundaries and deferred ideas

### 10.1 Keep useful ideas without duplicating architecture

The adaptation target is an AEW-owned behavior with a clear outcome. Do not turn PA's role names, task files, orchestration, or memory arrangement into a parallel AEW system. The inspected PA installation is tightly integrated with Claude Code settings, agents, hooks, and workflow conventions; independently adopting a concept does not require adopting that environment. [PA-14]

Preserve the following boundaries in any eventual change:

- Repository content and retrieved summaries remain evidence/data, not new instructions or authority.
- A helper can recommend wider investigation; it cannot silently enlarge task scope or spending authority.
- Summaries do not replace the source where verification is consequential.
- Saved observations and hypotheses do not become adopted decisions by being remembered.
- A checkpoint does not establish worker death, accepted completion, or permission for a duplicate effect.
- Structural and heuristic observations retain their stated limits.

### 10.2 Defer until a gap is demonstrated

A compact status digest may be valuable, but first compare it with AEW's existing task/status surface. Decision retrieval may benefit from showing supersession and the user's decision wording, but should read existing records. A context-waste review can generate hypotheses from repeated reads, yet each proposed change still needs an outcome-based evaluation. [PA-10] [PA-11] [PA-12]

Do not carry PA-specific line caps, context-window percentages, cache timing, provider/model selections, or quota formulas into AEW as defaults. Treat each as a parameter with an underlying purpose to investigate. The resulting AEW design should remain usable across supported agents and providers.

The source-outline interaction can be revisited with the semantic roadmap. It should not create a new heuristic index that later competes with the shared query contract.

## 11. Filing and completion criteria

Keep this research record with the AEW research/design materials and link subsequent experiment results to it. A suggested repository destination, if the Lead files it there, is:

`docs/research/projectarchitect-concepts-and-evaluation-2026-11-25.md`

That is a proposed destination, not a claim that a repository commit or register update has been made.

The research can be closed when:

- The current capability/overlap checklist is complete.
- Each priority concept has a documented result or a specific reason for deferral.
- Measurements include unsuccessful attempts and all participating agents.
- Findings distinguish observed behavior from inferred benefit and remaining uncertainty.
- Any recommended implementation is a narrow, independently designed change routed to its existing owner.
- Semantic mapping remains correctly identified as a separate capability effort.

### Results record template

| Field | Content to record |
| --- | --- |
| Concept and question | Which concept was evaluated and what improvement was predicted. |
| Baseline and candidate | Revisions, settings, allowed capabilities, and the exact difference between arms. |
| Fixtures and oracle | Task families, source identities, repetition count, and verification criteria. |
| Results | Success, evidence quality, costs, latency, recovery effects, and all failures. |
| Interpretation | What the observations support, what they do not support, and likely confounders. |
| Decision | Existing behavior sufficient; narrow change justified; inconclusive follow-up; or reject for the tested scope. |
| Follow-on | Existing owner/row, proposed delta, and any additional qualification required. |

## 12. Source index

All repository links below are pinned to the inspected revisions. The filenames and observations identify the basis of the assessment; the AEW experiments are original proposals in this document.

### AEW

| Reference | Source and relevance |
| --- | --- |
| [AEW-01] | `src/aew/maps/query.py` — common answer contract, observation basis, coverage, terminal states, and unsupported semantic capability. |
| [AEW-02] | F15.8 implementation note — completed map-read slice, worker access, policy behavior, and remaining work. |
| [AEW-03] | E293 implementation note — structural profile, scoped-cap correction, source checks, and pinned slices. |
| [AEW-04] | `src/aew/harness/bridge.py` — worker bridge integration for map operations. |

### ProjectArchitect

| Reference | Source and relevance |
| --- | --- |
| [PA-01] | `agents/retriever-code.md` — question, scope, bounded reads, answer cap, and durable report instructions. |
| [PA-02] | `agents/retriever-digest.md` — document/research retrieval and report-oriented answers. |
| [PA-03] | `tools/card.py` and `mod/pa/hooks/brief.ts` — deterministic selection and task brief construction. |
| [PA-04] | `tools/bench.py` — fresh fixtures, consequence runs, result retention, and total cost aggregation. |
| [PA-05] | Published full and canary result files — reported coverage, repeats, and hook settings. |
| [PA-06] | `tools/_bench_grade.py` and `tests/test_bench_grade.py` — grading logic and grader qualification. |
| [PA-07] | `templates/TASK_PROGRESS.template.md` and `agents/pa-expert.md` — continuation content, attempt history, and update points. |
| [PA-08] | `pa/handoff.py` — threshold-triggered handoff and suggested patch handling. |
| [PA-09] | `tools/outline.py` — heuristic source outline and supported extensions. |
| [PA-10] | `mod/pa/hooks/digest.ts` and `mod/pa/hooks/loop.ts` — status/recovery digests and child-report lifecycle cases. |
| [PA-11] | `agents/pa-claude.md` — decision and conversation-retrieval practices. |
| [PA-12] | `project-architect-3.0.md` — workflow and phase-close context review. |
| [PA-13] | `pa/savings.py` and `pa/fit.py` — counterfactual savings and provider usage modeling. |
| [PA-14] | `INSTALL.md` — runtime and workflow integration. |
| [PA-15] | `LICENSE` — source provenance for the reviewed project. |

Companion source links: [brief construction][PA-03b], [canary results][PA-05b], [grader tests][PA-06b], [expert continuation instructions][PA-07b], [loop lifecycle handling][PA-10b], and [usage fitting][PA-13b].

[AEW-01]: https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/eece01e5499f2249084e34b229cd2bc4a0428a19/src/aew/maps/query.py
[AEW-02]: https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/eece01e5499f2249084e34b229cd2bc4a0428a19/docs/implementation/notes.d/F15.8/2026-11-25-f15-8-map-reads.md
[AEW-03]: https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/eece01e5499f2249084e34b229cd2bc4a0428a19/docs/implementation/notes.d/E293/2026-11-25-e293-maps-profile.md
[AEW-04]: https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/eece01e5499f2249084e34b229cd2bc4a0428a19/src/aew/harness/bridge.py
[PA-01]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/agents/retriever-code.md
[PA-02]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/agents/retriever-digest.md
[PA-03]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/tools/card.py
[PA-03b]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/mod/pa/hooks/brief.ts
[PA-04]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/tools/bench.py
[PA-05]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/bench/results/2026-11-23.json
[PA-05b]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/bench/results/2026-11-25.json
[PA-06]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/tools/_bench_grade.py
[PA-06b]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/tests/test_bench_grade.py
[PA-07]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/templates/TASK_PROGRESS.template.md
[PA-07b]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/agents/pa-expert.md
[PA-08]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/pa/handoff.py
[PA-09]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/tools/outline.py
[PA-10]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/mod/pa/hooks/digest.ts
[PA-10b]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/mod/pa/hooks/loop.ts
[PA-11]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/agents/pa-claude.md
[PA-12]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/project-architect-3.0.md
[PA-13]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/pa/savings.py
[PA-13b]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/pa/fit.py
[PA-14]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/project-architect-3.0/INSTALL.md
[PA-15]: https://github.com/Druthulu/ProjectArchitect/blob/cac77da62f0e2b81b3c8f60ba3f70742471ca609/LICENSE
