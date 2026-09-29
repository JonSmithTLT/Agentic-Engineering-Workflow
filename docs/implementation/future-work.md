# AEW future work register

**What this is:** the one place that lists AEW's deferred work, so that nothing designed or decided is forgotten. Each entry points to its source and names the gate it must pass before, or the milestone it belongs to.

**Authority:** none. This is an index, like `docs/design/invariant-index.md` (`AEW-INV-TRACE-001`). The governing texts are the design documents, contracts and ADRs it points to. When one of them changes, update this register in the same change. Never reinterpret a design from its entry here.

**Keeping it current:** add an entry whenever work is deferred, whether a design is accepted, a review defers a finding, or a dogfood finding is left open. Remove an entry when its work is accepted, and name the commit or document that closed it.

*Last updated: 2026-09-28, during M3 step 9.*

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
| F12 | Workbench capability manifests, resolver, provider health in `doctor`, an MCP adapter over the Engine API | `m1-implementation-plan.md`; `m2-ambiguity-report.md` | M6 | |

## 3. Deferred by the M3 plan (out of M3 scope)

| # | Work | Source | Notes |
|---|---|---|---|
| D1 | Bridge hardening by the peer process's ancestry | M3 plan §2.3 and §8 | Documented as possible, not built. |
| D2 | An installer, and deeper harness integration (installed commands, one control surface) | M3 plan §8 | Discussed with the operator during M3; a follow-up for the designer. |
| D3 | Skills for AEW agents (Lead and role skills), made reachable through the capability registry | M3 plan §8; `docs/skills/` (the operator's proposal package and candidates, added over time); Workflow Contract §15.3 | The operator adds skills to `docs/skills/` periodically, and they are committed as the operator writes them. The goal: the capability registry (F12, M6) resolves them, so agents can reach them when a card calls for one. Until then, M3 reports requested skills as unavailable (WC §16.10). The dogfood's Lead brief is a stand-in. |
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
| Q6 | Whether "a goal met by changing its inputs" (O3) becomes a registry failure class | Designer | `failure-class-registry.md` §5; `m3-dogfood-report.md` §7 |
| Q7 | What the next dogfood should use: tasks where one model session fails or regresses, since this one's tasks hit a ceiling | Designer | `m3-dogfood-report.md` §11 and §12 |

## 5. Dogfood findings left open (small)

| # | Finding | Source | Notes |
|---|---|---|---|
| O1 | A file named `nul` in a workspace makes AEW's fingerprint fail with git's raw error. `nul` is a reserved device name on Windows, created by a Windows-style `> nul` redirect in bash. | M3 dogfood shakedown | A clearer refusal that names the file and the cause. Low severity. |
| O2 | The headless Lead's shell allow-list refused `git -C <dir>`, `git branch` and chained commands (`a; b`) | M3 dogfood | By design for the TUI, where the operator is asked. For headless use, consider a read-only allow-list that fits Lead investigation. |
| O3 | A goal met by changing its own inputs: AEW integrated a wrong T4 change after the implementer edited the sample data the goal was stated against. Review and verification passed it. | `m3-dogfood-report.md` §6.2 | Options for the designer: goals that refer only to unchanged inputs (Lead guidance), protected paths for data that goals refer to, and a reviewer item that flags changed acceptance inputs. Registry: see Q6. |
| O4 | The Lead is about 40% of AEW's cost, much of it waiting in `aew harness wait` slices that re-send the whole context | `m3-dogfood-report.md` §6.3 | A push-style wait, or the coordination design's event delivery (F9). |
