# AEW future work register

**What this is:** the one place that lists AEW's deferred work, so that nothing designed or decided is forgotten. Each entry points to its source and names the gate it must pass before, or the milestone it belongs to.

**Authority:** none. This is an index, like `docs/design/invariant-index.md` (`AEW-INV-TRACE-001`). The governing texts are the design documents, contracts and ADRs it points to. When one of them changes, update this register in the same change. Never reinterpret a design from its entry here.

**Keeping it current:** add an entry whenever work is deferred, whether a design is accepted, a review defers a finding, or a dogfood finding is left open. Remove an entry when its work is accepted, and name the commit or document that closed it.

*Last updated: 2026-09-29, during M3 step 10 (the plan assurance design added as F14 and Q9; O3, Q6 and Q7 point to it).*

## 1. Gates on the way (in order)

| Gate | Condition | Source |
|---|---|---|
| **M3 acceptance** | Step 9 (the dogfood) and step 10 (the docs) are complete, then an independent review. M4 does not begin before that review. | the M3 plan; `implementation-status.md` |
| **Before M4** | ADR-0011 (hot and cold control state) is implemented and accepted against its completion criteria, H1 to H4 and A1. The thresholds await the designer's confirmation. | `adr/0011-hot-cold-control-state.md`; `m3-performance.md` §5 and §7 |
| **Before real-repository dogfood or internal alpha** | Real filesystem containment passes the containment regression gate. Until then the guarantee is labelled `workdir separation only`, and the dogfood uses scratch repositories only. | `docs/design/execution-workspace-and-isolation-design-v0.1.md` §6.6 and §12; `m3-companion-review-triage.md` P1 and B2 |

## 2. Designed, not implemented

| # | Work | Source (governing) | Belongs to or gated by | Notes |
|---|---|---|---|---|
| F1 | Hot and cold control state (archival of terminal records) | ADR-0011 | Before M4 | History independence is the criterion. The `resume` evidence sweep is the designer's decision. |
| F2 | Real filesystem containment (protected writable roots, enforced by the OS or runtime) | isolation design §3, §6.6, §12 | Before real-repository dogfood or internal alpha | The mechanism is not chosen yet (containers, sandbox, overlay). Rocky 8 feasibility is an open question (§16). |
| F3 | Workspace strategy abstraction, role-sensitive isolation, repository-scale benchmarks | isolation design §4 to §14; lessons note, Incident B | With F2, and with M4 (concurrency above 1) | Isolation is a property, not a worktree. Benchmarks gate the choice of a project default. Mutable-serial locks are bound to an invocation (`AEW-INV-ISO-004`). |
| F4 | Ticket supersession lineage, and a first-class goal-revision path | hierarchy design §8 to §10, §20 (Scenarios A and E) | The hierarchy-revision milestone; before Leads routinely replace Tickets | Needs Workflow Contract and Knowledge Contract amendments. Observed in the M3 dogfood (T1: a recreated Ticket with no lineage). |
| F5 | Hierarchy revision semantics: EDITORIAL, CLARIFICATION and MATERIAL; Story and Epic revision; approved-baseline drift; admissibility as a Knowledge Contract concept | hierarchy design §4 to §7, §12 to §18 | The hierarchy-revision milestone | "Parents preserve purpose. Tickets preserve proof." Open questions in §21. |
| F6 | Fail-closed classification applied to existing classifiers: the downgrade rule for `verify classify`, and risk-class choice | invariant index `AEW-INV-CLASS-001` and `AEW-INV-VERIFY-001`; hierarchy design §11.1 (Scenario H) | The designer's decision, with a Workflow Contract amendment | Changes M1 semantics. The M3 dogfood records how model Leads classify. |
| F7 | Delegation and resource governance: bounded nested-delegation grants, duplicate-work detection, fanout, retry and interruption budgets, exact-match permission aggregation, cancellation propagation across fanout | lead/operator design §16 and §17; lessons note, Incident A | Any milestone where a Lead fans out or workers request help (with coordination, and with M5) | Workers already have no dispatch capability (M3). Includes the standing deep-review orchestration regression and its skill-instructed variant. |
| F8 | Lead and operator interaction: reconnaissance, elicitation, project maps and freshness, durable stakeholder decisions, checkpoints | `docs/design/lead-operator-interaction-design-v0.1.md` §3 to §15, §18 | Future Lead UX (not M3) | Open questions in §23. |
| F9 | Live coordination and assumption propagation | `docs/design/AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md` | Frozen. Revisit when M3 dogfood evidence justifies it; staging in its §24 (M3.x or M4 holds, then the M5 scheduler) | M3 kept the extension points (runs, `send`, continuations). |
| F10 | Mutating concurrency above 1: integration queue, merge revalidation | `m1-implementation-plan.md`; `implementation-status.md` | M4 (after F1) | Interacts with F3. |
| F11 | Dynamic scheduler | Workflow Contract; `implementation-status.md` | M5 | |
| F12 | Workbench capability manifests, resolver, provider health in `doctor`, an MCP adapter over the Engine API | `m1-implementation-plan.md`; `m2-ambiguity-report.md` | M6 | Extended by F13. |
| F13 | Capability discovery and progressive disclosure: an Effective Capability Manifest per invocation that keeps available, authorized and active apart; lazy expansion from L0 awareness to L3 exact schema; adapters advertising harness-native capabilities (sandbox, compaction, native review or orchestration, resume); skills that name abstract capability classes; manifests and schemas recorded by reference and hash; a context-economy acceptance test (a large, unrelated MCP server must not inflate baseline context) | `docs/design/capability-discovery-and-progressive-disclosure-design-v0.1.md` | After M3's acceptance, with or after F12 (M6). Sequence in §18: the registry and contract, then the manifest, then lazy expansion, then harness-native capabilities, then a Codex adapter on the same contract, then evaluation. | Does not expand M3. Today M3 gives runs no skills (reported unavailable) and denies OpenCode's `subagent` outright. The design would allow bounded harness-native orchestration under a capability grant, with no AEW identity, credential or authority for the helpers (§8). M3's custody bridge is the boundary that makes that safe. Candidate failure classes and invariants: Q8. |
| F14 | Plan assurance and premise validation before mutating dispatch: raw stakeholder intent kept apart from derived interpretation, with statements typed (requirement, observation, diagnosis, inference, decision); acceptance reconstructed independently by a fresh role *before* it sees the proposed plan; decision-sensitive premises tested by discriminating probes; typed pre-implementation baselines (`EXPECTED_FAILURE`, `UNEXPECTED_PASS`, `INVALID_MEASUREMENT`, …); negative controls; subject kept apart from acceptance inputs, oracle, evaluator and environment, with protected acceptance conditions enforced through final verification; a Plan Challenge with bounded outcomes and disagreement budgets; assurance bound to the whole dependency set by canonical hash; `ASSURED` as one derived gate predicate at plan acceptance and at every dispatch path; deterministic plan lint; hierarchical inheritance of parent obligations; proportional tiers A–E with hard triggers; strong models at interpretation points | `docs/design/plan-assurance-and-premise-validation-design-v0.3.md` | After M3's acceptance. Changes when a mutating plan becomes dispatchable, so it needs a Workflow Contract amendment (its Phase 5). Phases 1–4 (the T4 replay fixture, the deterministic gaps, a pilot on existing reviewer and verifier infrastructure, evaluation) can be dogfooded before that. Order relative to ADR-0011 and M4: Q9. | Motivated by the M3 dogfood's T4 failure (O3). Already in the code to build on: `guardrails.yaml` `protected_paths`; review and verification of planner proposals by policy alone (`non_mutating_paths`); fail-closed ancestor plan bindings (ADR-0007); source-bound freshness of plan proposals (ADR-0008); `min_descendant_class` floors. What is new: the acceptance-first role, baselines, the challenge, the assurance predicate and evaluator protection. Relates to F5 (hierarchy revision: accepted baselines, admissibility), F6 (fail-closed classification), F8 (reconnaissance and stakeholder decisions). |

## 3. Deferred by the M3 plan (out of M3 scope)

| # | Work | Source | Notes |
|---|---|---|---|
| D1 | Bridge hardening by the peer process's ancestry | M3 plan §2.3 and §8 | Documented as possible, not built. |
| D2 | An installer, and deeper harness integration (installed commands, one control surface) | M3 plan §8 | Discussed with the operator during M3; a follow-up for the designer. |
| D3 | Skills for AEW agents (Lead and role skills), made reachable through the capability registry | M3 plan §8; `docs/skills/` (the operator's proposal package and candidates, added over time); Workflow Contract §15.3 | The operator adds skills to `docs/skills/` periodically, and they are committed as the operator writes them. The goal: the capability registry (F12, M6) resolves them, so agents can reach them when a card calls for one. Skills should name abstract capability classes, not concrete providers, and are disclosed progressively (F13 §9, §11). Until then, M3 reports requested skills as unavailable (WC §16.10). The dogfood's Lead brief is a stand-in. |
| D4 | A deterministic `checks` adapter for integration-scope verifiers | M3 plan §7 | Only if the dogfood shows the LLM post-integration verifier dominates. In T1 it cost USD 0.0025. |
| D5 | Model optimization and routing policy | M3 plan §8 | The dogfood's model comparison is evidence for it. |

## 4. Open questions awaiting a decision

| # | Question | Owner | Source |
|---|---|---|---|
| Q1 | The completion thresholds for ADR-0011 (H1 to H4, A1) | Designer | ADR-0011 |
| Q2 | Whether `resume` should keep sweeping all historical evidence | Designer | ADR-0011 |
| Q3 | Whether containment is required for personal real-project dogfood, or only for internal alpha | Designer | isolation design §16 |
| Q4 | Fail-closed rules for `verify classify` and risk class | Designer | F6 |
| Q5 | The open questions each design lists | Designer | hierarchy §21; lead/operator §23; isolation §16 |
| Q6 | Whether "a goal met by changing its inputs" (O3) becomes a registry failure class. The plan assurance design proposes `ACCEPTANCE_CONDITION_MUTATION` and `PROTECTED_ACCEPTANCE_OVERLAP` for it (Q9). | Designer | `failure-class-registry.md` §5; `m3-dogfood-report.md` §7; plan assurance design §26 |
| Q7 | What the next dogfood should use: tasks where one model session fails or regresses, since this one's tasks hit a ceiling. The plan assurance design's §28 proposes task families (T4 replay, diagnosis contrast pairs, oracle weakening, vacuous red, …) and configurations A–F. | Designer | `m3-dogfood-report.md` §11 and §12; plan assurance design §28 and §29 |
| Q8 | Reconcile the capability design's six candidate failure classes (`CAPABILITY_CONTEXT_BLOAT`, `CAPABILITY_DISCOVERY_FAILURE`, `CAPABILITY_AUTHORITY_CONFUSION`, `CAPABILITY_SCHEMA_OVEREXPOSURE`, `HARNESS_FEATURE_SUPPRESSION`, `HARNESS_AUTHORITY_LEAK`) with the failure-class registry, and add its invariants (§16) to the invariant index, before F13 is implemented | Designer (owner of both indexes) | capability design §15 and §16 |
| Q9 | The plan assurance design's decisions (its §33): whether it becomes the post-M3 direction; `ASSURED` as a derived predicate, not a state; reusing reviewer and verifier modes rather than a new role; whether a mechanical exemption exists at first; whether protected-condition violations are non-waivable without a new acceptance revision; mandatory strong models for the Lead and the challenge during evaluation; the evidence threshold for freezing tiers. Also: its order relative to ADR-0011 and M4, and reconciling its 15 candidate failure classes (§26) and invariants (§27) with the registry and the invariant index | Designer | plan assurance design §26, §27, §33 |

## 5. Dogfood findings left open (small)

| # | Finding | Source | Notes |
|---|---|---|---|
| O1 | A file named `nul` in a workspace makes AEW's fingerprint fail with git's raw error. `nul` is a reserved device name on Windows, created by a Windows-style `> nul` redirect in bash. | M3 dogfood shakedown | A clearer refusal that names the file and the cause. Low severity. |
| O2 | The headless Lead's shell allow-list refused `git -C <dir>`, `git branch` and chained commands (`a; b`) | M3 dogfood | By design for the TUI, where the operator is asked. For headless use, consider a read-only allow-list that fits Lead investigation. |
| O3 | A goal met by changing its own inputs: AEW integrated a wrong T4 change after the implementer edited the sample data the goal was stated against. Review and verification passed it. | `m3-dogfood-report.md` §6.2 | Options for the designer: goals that refer only to unchanged inputs (Lead guidance), protected paths for data that goals refer to, and a reviewer item that flags changed acceptance inputs. Registry: see Q6. **Addressed by the plan assurance design (F14)**; its Phase 1 makes this run a replayable fixture. Stays open until F14's fix is accepted. |
| O4 | The Lead is about 40% of AEW's cost, much of it waiting in `aew harness wait` slices that re-send the whole context | `m3-dogfood-report.md` §6.3 | A push-style wait, or the coordination design's event delivery (F9). |
