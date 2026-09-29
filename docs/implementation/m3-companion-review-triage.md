# M3 triage of the companion design review (2026-09-28)

**Input:** the companion design review integration bundle of 2026-09-28, now in `docs/design/` (`README-review-integration-2026-09-28.md` and the documents it lists), read in its stated order:

1. `failure-class-registry.md`
2. `invariant-index.md`
3. `hierarchy-intent-revision-and-replanning-design-v0.1.md`
4. `lead-operator-interaction-design-v0.1.md`
5. `execution-workspace-and-isolation-design-v0.1.md`
6. `AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md`
7. `external-agent-workflow-lessons-2026-09-28.md`

**Decision asked for:** which findings are M3 hardening blockers, fixed before the step-9 dogfood resumes, and which are post-M3 prerequisites.

**Basis:**
- the M3 code at `55412aa`;
- the dogfood so far: a free-model shakedown and the first paid run, T1 in AEW mode on GPT-5.6 Luna;
- the rule that M1 and M2 semantics and tests stay unchanged.

Failure-class and invariant names below are the registry's and the index's. Those two files stay non-authoritative indexes (`AEW-INV-TRACE-001`).

## 1. M3 hardening blockers (before the dogfood resumes)

| # | Finding | M3 evidence | M3 change | Regression |
|---|---|---|---|---|
| B1 | **Intent ingress integrity.** `AEW-INV-INTENT-001`, `INTENT_INGRESS_CORRUPTION`. The design calls it an immediate hardening requirement (hierarchy §10.1). | **Observed in T1.** The Lead typed `--goal "... -$15.00"` in bash. The shell expanded `$1`, so the stored goal read `-5.00`. The Lead's `verify classify` reason was corrupted the same way. The goal Ticket could not be repaired and was recreated. | **(a) One ingress for every command.** `--fields FILE\|-` takes the command's option values as a YAML or JSON mapping, from a file or stdin, and applies them literally with no shell. It covers goals, contract, scope, title, reasons, notes and every other authored option. Through a Lead session, the values travel as data to the broker.<br>**(b) Guidance** so models use it: the Lead projection, its command templates, the role preamble for report submission (a quoted heredoc or a file, never text assembled into a shell string), the dogfood brief, the quickstart and `opencode.md`. | The design's Scenario G corpus: `$5.00`, `$(echo nope)`, backticks, `*`, `?`, `&`, `;`, both quote kinds, backslashes and Windows paths, a value beginning with `-`, multiline text and Unicode. Each must be stored byte-exact:<br>• through `--fields` from a file and from stdin;<br>• directly and through a Lead session;<br>• for the existing stdin payloads (plan, submission, checkpoint notes);<br>• on Windows and Linux. |
| B2 | **An honest containment label.** `AEW-INV-ISO-001`, `FALSE_CONTAINMENT_CLAIM`. Isolation design §3.1: run metadata and operator status must state the actual guarantee. | Step 8: a verifier wrote into the operator's real checkout. AEW records a private XDG state and a private scratch directory per run, and neither is filesystem containment. Nothing states the guarantee today, and the design says absence must not be read as containment. | Every run record and `aew harness status` state `containment: workdir_separation_only`. `aew doctor` states the project's guarantee. M3 documents use the same words: harness-conformance, the ADR-0009 draft, the reviewer brief and `opencode.md`. | The run record, harness status and doctor carry the label, and nothing claims more. |
| B3 | **Canonical failure names in the dogfood.** `AEW-INV-TRACE-001`, the registry's maintenance rules. | The step-9 rubric predates the registry. | The rubric is amended before the next paid run, as a recorded change: observed failures are classified by registry class. A failure no class covers is reported as unmapped, never given a local synonym. | None (a documentation change). |

The two defects the dogfood already found, M3-D8 (next actions after harness runs) and M3-D9 (a scope glob containing a comma), are fixed with regressions (`be1d6b1`, `55412aa`). M3-D9 is not `INTENT_INGRESS_CORRUPTION`: the value reached AEW intact and was misread. It stays an AEW defect with no registry class.

## 2. Already satisfied in M3 (mapped; stays pinned)

| Invariant | Why it holds in M3 | Evidence |
|---|---|---|
| `AEW-INV-DELEG-001`: workers get no dispatch capability | A worker's only AEW path is its run's bridge, which serves `check.run`, `submit` and `whoami` and nothing else. A worker never holds a Lead credential. OpenCode's `subagent` tool is denied in every run's projection. What a worker's instructions or skills say is irrelevant, because the capability is absent. | `test_an_investigator_cannot_obtain_implementer_authority` (Attack 6: `work assign`, `invoke create` and `lead acquire` from a worker are refused and no child invocation exists); projection goldens; live exposure checks. |
| `AEW-INV-CANCEL-001`: cancellation revokes descendant authority | Cancelling a Ticket ends its invocations and revokes their credentials. A parent cancel cascades to its descendants. A run's bridge closes on revocation. | M2 cascade tests; harness conformance (a revoked or retired run's bridge refuses and closes). Seen live in T1: INV-0001 was `cancelled` with T-0001. |
| `AEW-INV-AUTH-001`: only AEW authority moves state | A harness reports; only ingest and Lead decisions move state. | Conformance ("exit success is not completion"); AT-14 to AT-17. |
| `AEW-INV-SCRATCH-001`: scoped scratch, never evidence by existence | Each run has a private scratch directory (`AEW_SCRATCH`, M3-D6). Evidence exists only by `submit`. | `test_every_run_is_told_where_to_write_outside_its_workspace`. |
| `AEW-INV-INTEGRATE-001`: integration catches cross-Ticket conflict | An integration candidate, post-integration verification, an atomic ref CAS and mutating concurrency 1, all from M1. | M1 integration suites. |
| `AEW-INV-EVID-001` (the part M3 relies on) | Gates bind evidence to the evaluated fingerprint, so evidence about another snapshot never satisfies a gate. | Step-8 rework: at VERIFIED no gate was bound to the rejected attempt's evidence. |

Residual, documented and not claimed away: a worker's shell can start processes, including another harness on a free model. They run inside the run's process tree, with the run's own authority and lifetime. No new AEW invocation or authority results (the "untracked subagent" attack). Bounding that resource use is `RESOURCE_COMPOSITION_FAILURE` territory (P5).

## 3. Post-M3 prerequisites

| # | Finding | Prerequisite for | Why not M3 |
|---|---|---|---|
| P1 | **Real containment** that passes the isolation design's §12 gate (`AEW-INV-ISO-002`, `HOST_WRITE_ESCAPE`) | Real-repository dogfood and internal alpha | The design explicitly lets scratch-repository M3 evaluation continue under the weaker, labelled guarantee (B2). The M3 dogfood already runs only on scratch repositories outside the checkout, and records whether the checkout stayed untouched. That is detection, not containment. The operator's TUI session also uses a scratch project. |
| P2 | **Ticket supersession lineage and a first-class goal-revision path** (`AEW-INV-HIER-004`, `AEW-INV-HIER-005`; Scenarios A and E; `LOST_SUPERSESSION_LINEAGE`) | Hierarchy-revision work; before Leads routinely replace Tickets | It is a new control-state schema and workflow semantics, needing Workflow Contract and Knowledge Contract amendments. T1 shows the gap: T-0003 records no link to the T-0001 and T-0002 it replaced, only free-text cancel reasons. The dogfood reports it as observed. |
| P3 | **Fail-closed classification applied to existing classifiers** (`AEW-INV-CLASS-001`, `AEW-INV-VERIFY-001`; Scenario H): the downgrade rule for `verify classify`, and risk-class choice (Class 0 skips review and verification) | Reconciliation with the Workflow Contract, which is the designer's decision | It changes M1 semantics and M1 tests (the M1 walks classify `LOCAL_IMPLEMENTATION_DEFECT` freely). The design itself asks for reconciliation with the Workflow Contract and the current `verify classify` before freezing. The dogfood records how model Leads classify, as evidence for that decision. |
| P4 | **Hierarchy revision semantics**: EDITORIAL, CLARIFICATION and MATERIAL (`AEW-INV-HIER-002`, `AEW-INV-HIER-003`); approved-baseline drift (`AEW-INV-HIER-006`); admissibility as a Knowledge Contract concept (`AEW-INV-EVID-001`) | The hierarchy-revision milestone | New features on frozen contracts. |
| P5 | **Delegation and resource governance**: bounded nested-delegation grants, duplicate-work detection, fanout and interruption budgets, exact-match permission aggregation (`AEW-INV-DELEG-002`, `AEW-INV-DELEG-003`, `AEW-INV-PERM-001`, `AEW-INV-RESOURCE-001`, `AEW-INV-ATTN-001`); the standing deep-review orchestration regression | Any milestone where a Lead fans out or workers can request help (coordination) | M3 has one Lead, a shallow topology, mutating concurrency 1, and no permission prompts in role runs (every rule is allow or deny, and an ask is rejected). |
| P6 | **Workspace strategy abstraction, role-sensitive isolation and repository-scale benchmarks** (`AEW-INV-ISO-003`, `AEW-INV-ISO-004`; `ISOLATION_OVERHEAD_FAILURE`) | Choosing a project-default strategy; the large repositories on the target | Goes with P1. M3's worktree-per-Ticket strategy is unchanged and measured only at M3's scale (`m3-performance.md`). |
| P7 | **Lead and operator interaction**: reconnaissance, elicitation, maps and checkpoints (`AEW-INV-LEAD-001`, `AEW-INV-LEAD-002`) | Future Lead UX | The design says it does not expand M3 scope. The dogfood's headless Lead is a measurement instrument, not this design. |
| — | **Live coordination** | Frozen future work | The bundle's version changes only its status and review notes. It replaced the earlier copy in `docs/design/`. |

Every item in this section, and every other deferred item, is tracked in `future-work.md`.

## 4. How the dogfood changes

- **It resumes only after B1 to B3.**
- **The brief is amended.** It tells the Lead to pass authored text with `--fields` or a quoted heredoc. This is a recorded amendment in `rubric.md`, dated after the first paid run and with its reason. T1's first record stays as it is: a result on the code before hardening, identified by its `aew_commit`. It is not re-scored.
- **Failures are named by registry class** (B3). T1 so far:
  - `INTENT_INGRESS_CORRUPTION`, twice: the goal, and the classify reason;
  - `LOST_SUPERSESSION_LINEAGE`: T-0003 has no link to T-0001 and T-0002;
  - M3-D9, which is unmapped.
- **Scratch repositories only**, until P1.
