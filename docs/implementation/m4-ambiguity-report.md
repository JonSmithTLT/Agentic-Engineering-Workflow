# AEW M4: ambiguity report and plan (mutating concurrency above 1)

- **Status:** approved by the operator and designer (2026-10-03) and in progress; see the last bullet of this list for the phase state. Earlier: a draft for plan review; the planning plan was approved by the operator on 2026-10-03, with the four decisions and three clarifications recorded in §3, and no M4 code was written until the plan was approved.
- **Engine baseline:** `42239e1`, the ADR-0011 P3 merge (PR #24). This document is written on `main` at `0424c61` (PR #27, test and CI only, on top).
- **Register housekeeping first:** PR #29 closes the before-M4 gate, F1, E5 and F20.1 in `future-work.md` §9. The triage in §R assumes it.
- **§0 spike done** (variant A, engine-only, 2026-10-03). It does not change the plan (§0).
- **Approved and in progress.** M4-A is built (§2, "M4-A as built"). The static checks (Ruff, Pyright, pip-audit; register E7) followed as their own change. M4-B is built (§2, "M4-B as built"). M4-C is built (§2, "M4-C as built"); M4-D (the queue engine) is next.

## Context

M1 to M3 proved the serial control engine, the hierarchy and non-mutating work, and a real harness behind a custody boundary. ADR-0011 made hot-state cost track open work instead of completed history, which was M4's prerequisite: concurrency raises the open frontier, and `resume` costs about 3 ms per open unit on Windows (ADR-0011 plan §7.3).

M4 lets mutating Tickets run in parallel while integration stays serial: **parallel Ticket execution with one serial integration lease** (the designer's queue disposition, 2026-10-01). It must show with evidence that:
1. **Legality has one source.** Every dispatch route asks one queryable predicate, and a queue position never carries a stale ALLOW.
2. **Parallel work integrates safely.** The authoritative branch only ever moves to a validated candidate built on the current head. A conflict or a moved head never auto-resolves past the Lead.
3. **Parallel agents are contained.** On Linux, a run cannot write outside its writable roots, and stopping a run ends every process it started. Windows stays labelled `workdir separation only`, and is never presented as equivalent.
4. **The Lead's cost does not grow with the queue.** Stage commands and a queue view replace choreography, as F15 proposes.

**Basis (governing):**
- WC v0.7 and KC v0.4 (the frozen set `aew-frozen-2026-09-25`);
- ADR-0001 to ADR-0011 and their amendments;
- the designer's queue disposition: [`m4-integration-queue-research-2026-10-01.md`](../research/m4-integration-queue-research-2026-10-01.md) §7 and §7.1, with the review revision that makes the queue entry, not the candidate, the lease owner;
- [`plan-assurance-and-classification-decisions-2026-10-01.md`](../design/plan-assurance-and-classification-decisions-2026-10-01.md) §3.1, §3.2 and §3.5 ("M4's first step");
- [`workflow-contract-amendment-class0-2026-10-01.md`](../design/workflow-contract-amendment-class0-2026-10-01.md) (adopted; enforced from M4-A);
- containment research §8 ([`containment-and-process-ownership-rocky8-research-2026-10-01.md`](../research/containment-and-process-ownership-rocky8-research-2026-10-01.md));
- the F15 direction (the v0.4 idea note §14 sequence, [`aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md`](../design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md)): adopted, and promoted to governing on 2026-10-05 as the [typed Lead surface v0.2](../design/typed-lead-surface-design-v0.2.md) (§3, decision 1; the gate is met).

**Not governing (inputs):** [`execution-workspace-and-isolation-design-v0.1.md`](../design/proposals/execution-workspace-and-isolation-design-v0.1.md) (proposed), [`lead-workflow-efficiency-design-v0.1.md`](../design/proposals/lead-workflow-efficiency-design-v0.1.md), the dashboard contract 0.1.2 and `web/docs/reference/integration-checklist.md`.

---

## Current code (what M4 changes)

Found by reading the code at the baseline, so that the plan builds on what exists:

| Area | Today | Where |
|---|---|---|
| Mutating cap | `EFFECTIVE_MUTATING_CAP = 1`, checked inline in `Assignment.work_assign`; not a guard. Its comment still says "M5". `gates.yaml` `mutating_concurrency` is in the schema with default 1 but never read; only `doctor` warns above 1 | `engine/workspace_ops.py:27-29,249-257`; `engine/api.py:199-202` |
| Dispatch legality | No single predicate. Eight routes each repeat their own mix of transition check, readiness, dependency, plan binding, inputs and cap: `work assign`, `work dispatch`, `work redispatch`, `invoke create` (mutating, non-mutating, parent), `--launch`, `harness launch`/relaunch, and the Lead broker's relay. The `assign` rule has no guard | `workspace_ops.py`, `nonmutating_ops.py`, `evidence_ops.py:453-520`, `hierarchy_ops.py:127-172`, `harness_ops.py:74-118`, `harness/lead_broker.py` |
| Integration | Per Ticket, driven by the Lead: `prepare` (commit, detached candidate at H, `merge --no-ff`, conflict recorded), validation by an integration-scope verifier, `publish` (CAS `update-ref ref M H`, then sync), `reconcile`. There is no queue or lease, though several candidates can already exist on disk | `engine/integration_ops.py`, `workspace/integration.py` |
| Serialization | The only lock is the control-state file lock. `AEW-INV-ISO-004` exists only in the invariant index. Syncing a published commit into the authoritative checkout is shared mutable state | `engine/store.py`, `engine/lock.py`; `integration.py:266,321` |
| Assurance | No `DispatchDecision`, no Class 0 checker and no plan lint in `src/`. `aew guide` still says Class 0 is undefined. `protected_paths` exists as guardrail policy only | `engine/guide.py:135`; `policy/guardrails.py` |
| Post-integration validation | Needs a verifier report that cites passing check evidence bound to the candidate (D4's hook) | `integration_ops.py:162-213` |
| `harness wait` | One run, polled every 0.2 s | `harness_ops.py:327-349` |
| Composition | A new collaborator needs a port, wiring in the composition root and updated composition tests | `engine/ports.py`; `api.py:217-256`; `tests/unit/test_engine_composition.py` |
| Control schema | `aew/control/v2`, validated on **every** load with `additionalProperties: false` | `schemas/control.schema.json`; `store.py:118` |
| Oracle | Rule 1 asserts at most one live mutating workspace. Four tests assert the cap | `tests/helpers/invariants.py:139-144`; `test_workspaces.py:55`, `test_compositions.py:175`, `test_m2_review_2026_09_27.py:220`, `test_at8_at13_hierarchy.py:213` |

## 0. Spike (variant A: engine-only, synthetic)

**Containment condition** (operator, 2026-10-03). A spike before M4-B may run only if it is engine-only and starts no uncontained model or harness process, or if it runs in a genuinely disposable environment with nothing writable and non-disposable, and no secrets, within host-level reach. A throwaway worktree or clone on the normal development host does not qualify. Any harness-backed spike waits for M4-B's Rocky probes.

**What ran.**
- The scripted CLI role drivers (`tests/helpers/aewflow.py`) drove sample projects in temporary directories.
- The cap was raised to 2 in each `aew` subprocess by a local `sitecustomize`; nothing in the checkout changed.
- No harness and no model ran.
- The spike was not committed.

| # | Scenario | Result |
|---|---|---|
| S1 | Two disjoint Tickets live at once. T1 publishes after T2 reaches COMMIT_READY | Both assign. The oracle flags only rule 1 (`serial cap exceeded`), as expected. T2's `prepare` merges onto the new H, validates and publishes. The authoritative tree stays clean and the oracle is clean at the end. T2's `base_commit` stays the old H |
| S2 | Both candidates validated at the same H; publish T1, then T2 | T2's publish is refused with `STALE_CANDIDATE` (expected H, current H). Re-prepare, revalidate and publish succeed. This is the manual form of the queue's one automatic rebuild |
| S3 | Overlapping edits: T1 publishes, T2 conflicts | T2's `prepare` records `conflict` and T2 stays COMMIT_READY. The next action is "return to RUNNING (rebase) or REPLAN_REQUIRED". An implementer can't be redispatched from COMMIT_READY; COMMIT_READY to RUNNING needs `--reason`. After that, a redispatched implementer ran **`git merge main` inside its worktree**, resolved the conflict and committed. The gates reran and T2 published. The oracle is clean |
| S4 | H moves while T2 is RUNNING on the old base | Review, verification and integration all succeed. Evidence bound to T2's snapshot stays valid, and the candidate is built on the current H |
| S5 | Two validated candidates published at once by the same Lead | One publishes. The other is refused at the **control revision** (`STALE_REVISION`) before it reaches the ref CAS. The tree is clean and the oracle is clean |

**Conclusions.**
- The engine does not break at N = 2. Every safety property held, apart from the cap's own oracle rule.
- What is missing is machinery: queue records, a lease, the bounded automatic rebuild, recorded conflict dispositions, and one legality predicate.

**Four facts the plan uses:**
1. Conflict resolution today happens in the **same** workspace, with an agent running git write commands there. M4 makes it a new implementation attempt (decision 4), and the private object store (decision 2) is where those git writes land.
2. The control revision already serializes the Lead's own commands. With parallel runs, the Lead will see more `STALE_REVISION` refusals. M4-H measures this, and the stage commands (M4-E) must re-read and retry only where their guards allow it.
3. A Ticket's `base_commit` is never refreshed. That is correct under "reuse work product, not proof", but the queue view must show base age.
4. Windows path length bit the spike's deep temp path (`'$GIT_DIR' too big`). M4-C's workspace naming must keep paths short, or fail with a named cause.

## 1. Already fixed by the contracts and ADRs

- **The branch moves only by CAS to a validated candidate** (ADR-0004). A moved ref is `stale_candidate`, and an ambiguous publish goes through `reconcile`. The queue builds on this and adds no second publication path.
- **Gates bind to fingerprints** (ADR-0002). Evidence is current for a snapshot, not a moment, which is what makes "reuse work product, not proof" checkable.
- **Identity and custody** (ADR-0005, ADR-0009): invocation credentials, the custody bridge and runs with rotation. A lease custodian is an existing invocation, never a new kind of authority.
- **Hot and cold state** (ADR-0011): finished units leave the hot state. Queue entries of archived Tickets must leave it too (§2.6).
- **Class 0** (WC amendment): Class 0 is an engine-checked eligibility predicate. A failing request is refused with reasons and never silently reclassified.

## 2. Architecture

### 2.1 `DispatchDecision`, one legality source (M4-A)
- A typed, side-effect-free predicate: `DispatchDecision {allowed, effective_obligations, blocking_conditions, reason_codes, dependency_digests}` (decisions §3.5).
- **Query equals execution.** `--explain` and dry runs call the same function that the execution path calls inside its transaction, against the current revision and Lead generation.
- **Never cached.** "Candidate runnable" may be cached for display. Every dispatch recomputes, and an old ALLOW is never reused (invariant #7: every dispatch path uses one computed predicate).
- **It starts permissive,** apart from what is enforced today (transition legality, readiness, dependencies, plan binding, inputs, the cap), hard protected-condition failures, and Class 0 eligibility when Class 0 is requested. F14's assurance package becomes another input later; it is not called `ASSURED` during evaluation.
- **All eight routes** call it, through a **declared dispatch-entrypoint registry**. Every way to dispatch, whether a CLI command or an internal, harness or Lead-broker entrypoint (harness launch and relaunch, `--launch`, the broker's relay), must register itself.
  - The conformance test drives every registered entrypoint and proves each one reaches `DispatchDecision`.
  - A second check enumerates the CLI command table and proves no CLI dispatch command bypasses the registry.
  - The invariant is: a new way to dispatch must register itself, and the conformance test then proves it reaches the predicate. A new CLI command is not assumed to be the only new path.
- **Durable reason codes:** one registry, refusal codes kept apart from failure-class names (decisions §3.1). Refusals, `status`, `resume`, next actions and the future `ActionProjection` all print the same codes.
- **The cap becomes a guard** inside the predicate, read from `gates.yaml` `mutating_concurrency` (and `non_mutating_concurrency`).

### 2.2 `PrimitiveSpec` (M4-A, first declarations)
- Each primitive the queue engine uses gets a declaration: `{primitive_id, operation_class, required_judgments, required_policy_inputs, required_evidence, side_effect_class, idempotency_scope, guard_id}` (idea note §4).
- An undeclared primitive defaults to judgment-bearing.
- M4-A declares the integration primitives and the dispatch routes. The remaining Lead operations migrate one at a time (§12–§13). The queue never invents a separate action abstraction.

### 2.3 Protected conditions, the Class 0 checker, plan lint (M4-A)
- **Protected-condition records and checks:** for example, a protected acceptance input inside a Ticket's mutation scope refuses dispatch (`PROTECTED_CONDITION_OVERLAP`, failure class `PROTECTED_ACCEPTANCE_OVERLAP`). Protection is not path-only (plan assurance v0.4 §10).
- **The Class 0 eligibility checker:** the engine-checked conditions of v0.4 §22 plus recorded semantic assertions, with no active hard trigger. `aew guide` then states the rule.
- **Deterministic plan lint:** the v0.4 §18 checks that need no model.

### M4-A as built (2026-10-03)
- **The registry** (`engine/dispatch.py`) declares nine entrypoints: `work.assign`, `work.dispatch`, `work.redispatch`, `invoke.create.mutating`, `invoke.create.non_mutating`, `invoke.create.parent`, `harness.launch`, and the internal `dispatch.launch` (run 1 of `--launch`, admitted by its dispatch's decision) and `lead_broker.relay`. Each names its guards in order. The pre-M4 checks moved in unchanged, with the same error codes and order; they stop at the first refusal. The M4 guards (`protected.overlap`, `assurance.triggers`, `class0.eligible`) run last and report every condition at once.
- **Enforcement at commit, not by convention.** The `Dispatch.finalize` transaction finalizer, which runs before archival, refuses a commit that creates an invocation or a harness run without an allowed decision computed in that transaction at that revision (`DISPATCH_UNDECIDED`). It records the admitting decision's provenance (entrypoint, channel, revision, Lead generation, decision digest, obligations) on the invocation and on each run. Admission is bound to what the decision checked (PR #32 review, P2): an invocation needs a decision for its unit whose guards resolved its role, its card (id and hash) and its scope (each creating entrypoint declares the scope it creates, `CREATES_SCOPE`; on a mutating Ticket the decision's scope chooses the Ticket or its integration candidate); one decision admits one invocation; a run needs a `harness.launch` decision for its own invocation. The wrapper entrypoints (`dispatch.launch`, `lead_broker.relay`) are provenance labels only and cannot be decided on their own.
- **Query equals execution.** `aew dispatch explain <unit>` calls the same `decide` on the committed state. The conformance test (`tests/integration/test_dispatch_conformance.py`) drives every entrypoint, checks the recorded provenance, compares explain with execution, and proves an ALLOW is not reused after a policy change. `tests/unit/test_dispatch_decision.py` enumerates the CLI command table against the registry and the broker's relayed commands.
- **Reason codes** (`engine/reasons.py`): one registry with each code's summary, failure class and whether it blocks. **`PrimitiveSpec`** (`engine/primitives.py`) declares the dispatch entrypoints and the integration primitives (`integrate.publish` is judgment-bearing); anything undeclared defaults to judgment-bearing.
- **Protected conditions** (`engine/assurance.py`, `assurance_ops.py`): a protected path inside a Ticket's mutation scope, or named in its accepted plan, refuses dispatch (`PROTECTED_CONDITION_OVERLAP`, `LINT_AFFECTED_PROTECTED`). **Deviation from §2.3:** an acceptance input (`--acceptance-input`) inside the scope is an obligation (`ACCEPTANCE_INPUT_IN_SCOPE`), recorded with the decision, and a hard trigger for Class 0. It does not refuse a Class 1+ dispatch, because the predicate starts permissive (§2.1) and v0.4 makes refusal there the job of the later assurance package. Guardrails also report it as a violation at integration.
- **Class 0 eligibility** for mutating Tickets, as the amendment's §9 records: a bounded scope (matching tracked files; measured by §9 item 5: no leading `**`, at most 50 tracked files and, in a tree of 40 files or more, a quarter of it, all in policy), a goal and a configured acceptance check, no acceptance input in scope, no protected path, no review trigger reached, no inherited elevated obligation (`CLASS0_INHERITED_ELEVATED_OBLIGATION`), a clean plan lint (warnings included), and the Lead's three recorded assertions (`--class0-assert`). A refused Class 0 Ticket is never reclassified by the engine; the Lead raises it with `aew work reclassify` (raise-only, never below an inherited floor, a recorded decision with `from_class`, `to_class`, the reason, the actor and its generation, and `effective_minimum_at_decision`). KC §26's acceptance case is amended to match (AT-9).
- **A Ticket's own acceptance checks are a gate** (PR #32 review, P1). A check the Ticket declares with `--acceptance-check` becomes the `acceptance_checks` gate, on any class and whatever the policy's path lists name. It belongs to a mutating Ticket: on a non-mutating one it is refused at creation (§9 item 6). It is evaluated like `local_checks` (current definition, current snapshot), required before review and at COMMIT_READY, re-evaluated at publication, and non-waivable: it is the Ticket's definition of acceptance, and Class 0 eligibility rests on it.
- **Plan lint:** `aew plan lint <T>`, also run as a dispatch guard: errors refuse, warnings (an affected path outside the scope) become obligations.
- **The cap** is the `cap.mutating` guard. It reads `gates.yaml` `mutating_concurrency`, clamped to `EFFECTIVE_MUTATING_CAP = 1` until M4-C. The non-mutating cap is the `cap.non_mutating` guard.
- **Coverage (E2)** came with M4-A: line and branch coverage of `src/aew` and its subprocesses on the Linux lanes, with a ratchet in `assurance` (`testing-and-ci-strategy.md` §3, "Coverage"). Baseline at M4-A: about 92% of lines and 82% of branches.

### 2.4 Containment on Linux (M4-B; F2 and E13)
- **Unprivileged bubblewrap** with a PID namespace and `--die-with-parent`. It wraps each run's harness tree, and its launch self-test fails closed.
- **Mutating workers get a private git object store.** Their git operations land in the run's store, never through a writable route back to the authoritative repository (decision 2). The engine adds that store as an alternate when it fingerprints or inspects the workspace (research §9). M4-B decides the store's lifetime: import the objects at the end of the run, or reset the index. Either way it is proven by the fingerprint and `prepare` tests.
- **Reviewer and verifier source is read-only,** with explicit writable scratch, build and temp locations, subject to the Rocky probe. If the probe shows legitimate verification breaking, they keep an isolated writable workspace plus `WORKSPACE_MUTATED` detection until the correct carve-outs exist. F2 is never weakened to make the label read better.
- **Network isolation is not part of F2.** It is reported truthfully as `network isolation: NOT PROVIDED` until it has its own design.
- **E13:** process ownership through the same PID namespace. The live test translates namespace PIDs to host PIDs (`NSpid`). Until that test passes on a real Rocky 8 kernel, process-group mode is never described as complete process ownership.
- **Acceptance:** the isolation §12 regression list (absolute path, `..`, symlink, rename, mkdir, temp file, `open()`, redirect, another worktree) produces OS-level write failures. Then come the research §6 probes on a **real Rocky 8 kernel**; WSL's kernel is not enough.
- **Windows:** the guarantee stays `workdir separation only`. `doctor`, run records and the dashboard state the guarantee each platform actually gives.

### M4-B as built (2026-10-03)
- **Where it is specified:** ADR-0009, "Amendment 2026-10-03 — OS filesystem containment and process ownership on Linux".
- **Deviation: private git state replaces the engine-side alternate.**
  - The designer's correction made the real git metadata read-only to the agent. The agent's git uses a private index (seeded from the real one) and a private object store.
  - Staging is scratch: AEW commits the working-tree content, as it always did. So the engine never reads the private store, needs no alternate, and imports nothing. The private state is removed when the run ends.
  - This supersedes "import at run end" (the operator's answer before the correction). The constraints for a future import are recorded in the approved plan.
- **Deviation: reviewer and verifier source is read-only,** as decided. The Rocky probe did not show legitimate verification breaking: AEW's own harness suites, run contained, pass with read-only source plus writable scratch and caches. The fallback (an isolated writable workspace plus detection) was not needed.
- **Added: the project and runs.**
  - The project is bound read-only, so it stays visible even under `/tmp`.
  - Every run's directory is hidden, so one run never reads another's harness state. The bridge socket always lives under `/tmp`, private per sandbox.
  - Agent tools' own sign-in stores are masked.
  - These came from the independent review of authority and custody (area 2), which also found a check could outlive its run. That is fixed: the supervisor kills running checks when the run ends, and records nothing from them.
- **Added: a residual stated and tested.** The harness server's environment (provider key, server password) is readable from the agent's shell, as the same user in the same PID namespace. ADR-0009 states it, and a Linux test asserts it.
- **Labels:** `{filesystem, process_ownership, network: not_provided, mechanism, self_test, layout}`; `aew doctor` probes it live. The dashboard contract (0.1.2) does not project containment, so no contract note is needed now.
- **Verification:**
  - **CI (Linux):** bubblewrap installed, with Ubuntu's AppArmor user-namespace restriction lifted in the setup action. Every harness suite runs contained, plus `tests/integration/test_containment.py` and `tests/unit/test_containment_layout.py`.
  - **Rocky 8 (SELinux enforcing):** the same suites, then one full run.
  - **Operator-assisted, on the Rocky 8 host (2026-10-03):**
    - The live OpenCode lane passed contained, under the real per-run layout: OpenCode 2.0.18 with free models, 23 passed and 1 skipped by design (`effective_override`, not drivable live). One test's probe called `python`, which EL8 does not have; it now falls back to `python3`.
    - With `user.max_user_namespaces=0`, a launch ended `launch_failed` with `CONTAINMENT_UNAVAILABLE` and no harness process; `allow_weaker` launched with the weaker label and its reason; `doctor` reported FAIL.
    - OpenCode 2.0.22 (the current Desktop build) is refused at launch, `HARNESS_INCOMPATIBLE`: it appends a default `browser: deny` rule after AEW's, and the adapter requires AEW's rules last. That refusal is correct as the check stands; a meaning-based check (rules OpenCode appends after AEW's may only deny) is planned separately.
  - **Two independent reviews (2026-10-04), four findings, all fixed in M4-B** (ADR-0009 amendment):
    - **AEW's own git ran programs git configuration names** (filters, diff and merge drivers, hooks, fsmonitor, signing) over files agents wrote, so a configured command pointing at a workspace script ran agent-edited code outside every sandbox. Every AEW git call now switches them off unless `containment.trusted_git_drivers` trusts the driver; a base that needs an untrusted filter is refused with `GIT_DRIVER_UNTRUSTED`, and `aew doctor` lists every driver (operator decision: trust by name, with a refusal that says exactly what to do).
    - **An operator `writable` root over the project or `/tmp`** passed the self-test while exposing control state and other runs' bridge credentials. Such roots are refused at launch, and the self-test now also probes `.aew`, the host's `/tmp` and a sibling run.
    - **A check registered just before its run ended could start after it.** A killed process tree now starts nothing, and ending a run and registering a check are atomic.
    - **`procs.host_pid`** returned an unmatched pid as if it were a host pid, and read only the innermost namespace. It now reads the run's namespace level and raises when nothing matches.
    - Notes fixed too: an explicit `mode: required` refuses on a non-Linux POSIX platform; unresolvable git metadata fails the launch instead of leaving nothing to protect; the residual that masks are computed at launch is documented.

### 2.5 Workspaces for N > 1 (M4-C; F3, the concurrency part)
- The engine reads `mutating_concurrency`. Live mutating workspaces are at most the policy cap, enforced as a `DispatchDecision` guard.
- The role-sensitive workspaces of §2.4. Workspace paths stay short on Windows (spike fact 4).
- **`AEW-INV-ISO-004`** (moved to M4-D, operator 2026-10-04; see "M4-C as built"): an invocation-bound serialization lock for shared mutable steps, such as syncing a published commit into the authoritative checkout. A stale owner is reconciled before release.
- **That lock is serialization only, never eligibility or authority.** Holding it never makes an operation legal; `DispatchDecision` alone decides legality, so the lock cannot become a second integration-authority path. A test proves that holding the lock without an ALLOW changes nothing. The wording is proposed to the designer for the invariant index, which the designer owns.
- Repository-scale workspace benchmarks (isolation §13) stay a selection gate for project defaults. M4 records worktree setup and cleanup cost at concurrency 1, 2 and 4 on the sample and AEW repositories, not on a large monorepo.

### M4-C as built (2026-10-04)
- **The cap is the policy's.** `cap.mutating` reads `gates.yaml` `mutating_concurrency` (default 1) with no clamp. The refusal (`CONCURRENCY_LIMIT`) names the cap and the Tickets holding live workspaces. Each mutating Ticket works in its own worktree (`<workspaces.root>/<T>-<attempt>`), and integration stays the serialized, CAS-published path of ADR-0004. A later candidate is built on the head its predecessors moved, and two Tickets that change the same lines conflict at `prepare`, with nothing published.
- **The cap is an admission rule, not a state invariant** (operator, 2026-10-04). Lowering `mutating_concurrency` (say from 4 to 1) never makes admitted work illegal: the live workspaces keep working and drain, and `cap.mutating` refuses new mutating workspaces until occupancy is below the new cap. Valid running work is never cancelled because the operator tightened future concurrency.
- **Oracle rule 1** now reads: no two live mutating workspaces share a path. The cap is checked where it applies, at admission, by the guard (`test_workspaces.py`: cap 4, four live, lowered to 1, the four stay legal, new assignments refused while draining, admission resumes below the cap). **Correction to §4:** its proposed second clause ("every live one is bound to an active invocation") does not hold. A COMMIT_READY or INTERRUPTED Ticket keeps its workspace with no active invocation, which the walks showed. The implication runs the other way: rule 2 binds every active invocation to its Ticket's current live workspace.
- **Short paths.** Workspace names were already short. A path git rejects as too long (spike fact 4) is now a `GitError` naming the path, its length, and what to change: `workspaces.root`, or long-path support.
- **Cost** (`tools/perf/workspaces.py`, Windows, median of 3; setting up and cleaning up one workspace at each level):

  | Repository | Tracked files | Set up one workspace | Clean up one | N = 1, 2, 4 in total |
  |---|---|---|---|---|
  | sample | 6 | 0.16 to 0.18 s | 0.04 s | 0.22, 0.40, 0.81 s |
  | AEW (`ce794fb`) | 930 | 1.08 to 1.11 s | 0.30 s | 1.43, 2.82, 5.79 s |

  The per-workspace cost does not change with concurrency. Totals grow linearly, because assignments are sequential. The repository-scale benchmark stays a selection gate (isolation §13).
- **`AEW-INV-ISO-004` moves to M4-D** (operator, 2026-10-04). M4-C's shared mutable step, syncing a published commit into the authoritative checkout, already runs inside the control-state lock, held from the CAS through DONE (ADR-0004), so no M4-C operation needs a second lock. The lease is the first thing that gives the lock a real custodian and lifetime (M4-B10, M4-B7); building it here would freeze M4-D's semantics early. It lands with the lease, keeping "serialization only, never eligibility" (M4-B6) and its test (holding the lock without an ALLOW changes nothing).

### 2.6 The integration queue and lease (M4-D; F10)

**Records.** Each COMMIT_READY mutating Ticket gets one queue entry in control state:
```
queue:
  next_seq: 5
  lease: {entry: Q-0003, custodian: INV-0042, generation: 7, granted_at: …} | null
  entries:
    Q-0003: {work: T-0011, seq: 3, state: LEASED, commit_ready_seq: 19,
             attempts: [{candidate: <M>, base: <H>, result: …}], rebuilds_used: 0,
             disposition: null}
```
- **Names.** Entry states are `QUEUED`, `LEASED`, `DEFERRED`, `AWAITING_DISPOSITION` and `RETIRED`. They match the vocabulary the dashboard design already assumes, so a later contract can project them unchanged.
- **The lease is owned by the queue entry,** not by the candidate or attempt. A rebuild or a new attempt replaces the candidate under the same lease.
- **The custodian** is an active, attributable invocation for every load-bearing part of the lease's life: acquire, prepare, validation, conditional publish or park, and release.
  - The proposal is the live integration invocation: the integration-scope verifier, or D4's deterministic validator.
  - The verifier does not exist until after `prepare` and may end before publication. So M4-D must prove that the chosen custodian covers prepare through release.
  - If the verifier's or validator's lifetime does not cover it, M4-D uses a dedicated integration-attempt invocation instead. A load-bearing lease is never left without a live custodian.
- A dead custodian is reconciled before the lease is transferred or released, no timeout alone releases a load-bearing lease, and an ambiguous publish goes through ADR-0004 `reconcile`. Custodian death revokes the custodian's authority immediately and marks reconciliation required (idea note §16).
- **Order.** Runnable entries are served FIFO by `seq`. The work graph decides dependency legality, and the Lead may explicitly reorder or defer. There is no head-of-line blocking: a DEFERRED or AWAITING_DISPOSITION entry never holds up an independent runnable one.
- **Queue state is scheduling, never eligibility.** The Ticket may remain COMMIT_READY while its entry is DEFERRED. Every grant computes `DispatchDecision` and binds the attempt to the current authoritative head.
- **One automatic rebuild.** When the head moves while the lease is held, the engine first proves nothing was published, then recomputes legality, rebuilds the candidate on the new H, and reruns integration validation. A second head move, a conflict, failed validation or changed legality moves the entry to AWAITING_DISPOSITION, after reconciliation releases the lease.
- **A conflict** releases the lease and returns the entry to the Lead. It is never auto-resolved and never sent straight to an Implementer. Resolution is a new implementation attempt (§2.7).
- **Retirement.** An entry is RETIRED when its Ticket is DONE, CANCELLED or leaves COMMIT_READY, in the same transaction. Archival (ADR-0011) moves retired entries with the unit's cold record, so the hot queue holds only live entries.
- **No batching** and no shared post-integration evidence in M4. Out of scope, not forbidden by the contract.

**The schema choice is decided by downgrade safety** (clarification 2). Queue and lease state carry authority. If an older engine could open the control file, ignore that state and act, the schema must move to v3. Older engines validate control state on every load with `additionalProperties: false` (`store.py:118`). An M4 control file with a `queue` key is therefore refused outright by the `42239e1` engine and by any earlier v2 engine: it fails closed and can neither read nor write.

Proposal: keep `aew/control/v2` with an additive `queue` key, closed with `additionalProperties: false` at every level. An M4-D test proves the baseline engine refuses an M4 control file. If review prefers an explicit `MIGRATION_REQUIRED` refusal over a schema error for operators, v3 plus a no-op `aew migrate` step is the alternative. The safety argument is the same either way.

### M4-D3 as built (2026-10-05)

Built as §2.6 and the M4-D plan say, with these specifics. The ADR text is in ADR-0004's and ADR-0003's amendments of 2026-10-05.

- **The custodian is a custody invocation**, `kind: integration_attempt`. It is executed by the engine and has no harness, model, role or credential. Its ids are a series of their own (`IA-0001`).
  - The `integrate.prepare` dispatch decision admits it. That decision migrates prepare's checks into guards (`integrate.ticket`, `integrate.gates`) and adds `queue.order` and `queue.lease`.
  - The post-integration verifier records it as `custodian`.
- **Consistency is a transaction finalizer** (`Queue.finalize`, between the dispatch check and archival), not a set of hooks. So a Ticket that leaves COMMIT_READY by any route, including a takeover's direct INTERRUPTED write, retires its entry in the same commit. The Lead's direct commits call it explicitly.
- **D3's answers to moved heads and conflicts, before D4:**
  - a stale or superseded candidate releases the lease, and the entry keeps its place in QUEUED: the Lead prepares again, as before M4-D;
  - a conflict sends the entry to AWAITING_DISPOSITION;
  - the Lead disposes of it by returning the Ticket to RUNNING or REPLAN_REQUIRED, which retires the entry. D4's disposition commands come later.
- **Withdrawn publish:** it keeps the lease.
- **Projects:**
  - **v1:** no queue; integrates as before until migrated.
  - **v2 from before M4-D** (no `queue` key): its COMMIT_READY Tickets are enqueued by the next Lead transaction, ordered by id.
- **E34.** The publish bound is a path-count limit (`max_publish_paths`, default 2,000), chosen after measuring. Checking each path with one `lstat` instead of four brought the sync to about 4.5 to 5.5 ms a path on Windows; git's own hashing is the rest.
- **Tests:**
  - `tests/integration/test_queue.py`;
  - the conformance case for `integrate.prepare`;
  - `tests/regression/test_m4_schema_downgrade.py`;
  - the later-commit sync case in `test_worktree_sync.py`;
  - the seeded walk `tests/regression/test_m4_queue_walk.py`, whose acceptance budget is 3 seeds × 500 steps.

### 2.7 What survives a head move: reuse work product, not proof (decision 4)
- **Head moved, Ticket work product unchanged:** existing Ticket evidence may stay current if every binding it depends on is unchanged. The integration candidate is still rebuilt against the new H, integration validation always reruns, and `DispatchDecision` recomputes.
- **Conflict resolution or changed implementation:** a new implementation attempt and fingerprint. Snapshot-bound review and verification do not carry forward, the effective gates for the Ticket's class and policy rerun, and plan/assurance applicability is recomputed from its bindings.
- This answers plan assurance §32 question 5, and it is what makes the one automatic rebuild safe. Spike S4 shows the first half already holds for Ticket evidence. M4 adds the new-attempt rule: today's resolution reuses the attempt (S3).

### 2.8 Deterministic integration validation (M4-D; D4)
- A policy-selectable path: `gates.post_integration.validation: verifier | checks`. With `checks`, a deterministic adapter runs the policy's integration checks against the candidate under the lease, and records bound `check_result` evidence that satisfies validation without a model.
- The default stays `verifier` until evaluation supports cheaper routing.

### 2.9 Wait-any (M4-D; E1, the wait-any part of O4)
- `aew harness wait --any R1 R2 …`, woken through a per-project wake file instead of 0.2 s polling (ADR-0012 D4 decided the file: `local/wake`, bumped by the store after each commit's log record and by the supervisor after each run-record write; built in M4-D slice D1). Polling remains the fallback.
- It returns the first run to end, with its next action.

### M4-D6 as built (2026-10-05)

- **`aew harness wait R1 R2 … --any`** returns the first run to end, with its next action and the runs still running. Several runs without `--any` are refused, which leaves room for an `--all`; the single-run form is unchanged.
- **Waking:** the 0.2 s poll is gone. The wait blocks on `local/wake` (a stat every 25 ms, a coarse re-check every 2 s) through `outbox.wait_for`, the same loop as `history log --follow`.
- **Two lanes on each wake (ADR-0012 D5):**
  - the runs' own records: did one end;
  - committed control state: did an invocation one of the runs serves stop being active, cancelled, interrupted by a takeover or completed. Such a result carries `ended_by: {lane: control, why}`.
- **No parse between commits:** control state is parsed only when `control.yaml`'s identity changed. A wait parses nothing between commits, however often the wake file changes (OBX-38).
- **Wake latency** (`tools/perf/wake_latency.py`, two processes, 60 commits, Windows reference machine):
  - median 42.2 ms from the start of the commit (p90 47.6 ms), within the 50 ms budget;
  - median 13.3 ms from the commit's return.
  - The Rocky 8 measurement is still owed (OBX-37).
- **Tests:** `tests/integration/test_harness_wait_any.py`: the first to end, a control-side end, the refusals and the timeout shape, the parse count under spurious wakes and under a commit; and, from the independent review: an invocation already ended when the wait starts (the initial snapshot is examined), a commit between the initial read and its identity (the identity is taken first), and `still_running` naming only runs live in both lanes.

### 2.10 Stage commands (M4-E; F15)
Gated on the designer promoting F15 v0.4 to a governing design (decision 1; met 2026-10-05: the typed Lead surface v0.2 governs). Then:
- `ActionProjection`;
- the stage-intent journal (hot while active, cold once finished, per ADR-0011);
- `draft`, `start`, `request-review`, `request-verification` and `submit-integration`;
- the `requires_disposition` policy property;
- `PUBLISH_IF_CLEAN` (an advance authorization that survives only the one automatic rebuild caused by a head move);
- `VALIDATE_ONLY` (validate, release the lease, wait for the Lead's publication decision).

Stages refuse with `STALE_POLICY` on policy drift. A replacement Lead explicitly continues or abandons an active stage.

### 2.11 The queue's normal UX (M4-F)
- `aew integrate next`, plus the queue in `status`, `resume`, next actions and `aew guide`.
- Each entry shows its state, wait time, base age (spike fact 3) and the reason it is not runnable.

### 2.12 The dashboard track (F20.2 to F20.6, parallel)
**A parallel workflow track that cannot change engineering state, not a read-only implementation** (clarification 3).
- **F20.2:** the contract's GET/HEAD projections on stdlib `http.server`, validated against contract 0.1.2 with `jsonschema`. History needs new seq-pinned cursors. There are no new runtime dependencies, to keep the offline Rocky 8 wheelhouse.
- **F20.3:** a new operator-session credential kind in `engine/authority.py`, the first real use of `expires_at`. It reuses `operator.authorize`'s typed-back code. The one-time URL is exchanged for an `HttpOnly`, `SameSite=Strict` cookie, and nothing is written to control state. **This has its own security acceptance:** bootstrap, cookie handling, expiry, invalidation when the server stops, and replay of the one-time URL, each with a negative test, and its own review. It does not inherit "it's only reads".
- **F20.4:** ETags cover the whole response envelope. A valid 304 keeps the cached payload, its `control_revision` and `generated_at`, and advances only the client's successful-check time (`last_checked_at`), as W01 behaves. Any change to the envelope or the revision changes the validator, so it gets a fresh 200, never a 304.
- **F20.5:** static assets in a new `aew.dashboard` package, CSP and security headers, Host and Origin checks, request bounds, `127.0.0.1` only.
- **F20.6:** integrated acceptance against authenticated live state, recorded separately.
- **Before F20.2:** the contract YAML's header still reads `PENDING_REVIEW` although its approval is ACCEPTED. The web agent corrects it. The web agent's backend question ledger (Q01 to Q06) is answered in F20.2 and F20.3.
- **Queue state stays UNSUPPORTED** in 0.1.2. Projecting the M4 queue is a later contract version with a renewed C0 review.

## 3. Decisions

| # | Topic | Decision | By |
|---|---|---|---|
| M4-B1 | Milestone shape | One M4 in phases A to H, one PR each, one acceptance gate (M4-H). F20.2 to F20.6 is a parallel track | Operator, 2026-10-03 |
| M4-B2 | F15 v0.4 | Promoted to governing **before M4-E**, not before M4 begins. It gates E and F, not A to D. Order: A foundation → D queue engine through primitives → promote F15 → E stages → F queue UX. **Met 2026-10-05:** the typed Lead surface v0.2 is governing | Operator/designer, 2026-10-03 |
| M4-B3 | F2 scope | A private object store for mutating workers. Read-only reviewer and verifier source with writable scratch/build/temp, subject to the Rocky probe, with `WORKSPACE_MUTATED` as the fallback and F2 never weakened. Network isolation out of F2, reported as NOT PROVIDED | Operator/designer, 2026-10-03 |
| M4-B4 | Platforms | Real-repository mutating dogfood runs on Linux/Rocky only. Windows covers CI, conformance and scratch or disposable evaluation under `workdir separation only` | Operator/designer, 2026-10-03 |
| M4-B5 | Invalidation | Reuse work product, not proof (§2.7) | Operator/designer, 2026-10-03 |
| M4-B6 | `AEW-INV-ISO-004` | Serialization only, never eligibility or authority | Operator/designer, 2026-10-03 |
| M4-B7 | Queue schema | Decided by downgrade safety. Proposal: additive v2 (older engines fail closed), proven by a test (§2.6) | Proposal |
| M4-B8 | F20.3 | Its own security acceptance and review | Operator/designer, 2026-10-03 |
| M4-B9 | Spikes before containment | Engine-only synthetic, or a genuinely disposable environment. Never a throwaway worktree on the development host | Operator, 2026-10-03 |
| M4-B10 | Lease custodian | An active attributable invocation for the whole lease: acquire, prepare, validation, publish or park, release. The proposal is the integration verifier or D4 validator. M4-D proves it covers prepare through release, or uses a dedicated integration-attempt invocation | Proposal, with the reviewer's condition (2026-10-03) |
| M4-B11 | Queue state names | `QUEUED`, `LEASED`, `DEFERRED`, `AWAITING_DISPOSITION`, `RETIRED`, matching the dashboard design's vocabulary | Proposal |

## 4. Compatibility with M1 to M3 and ADR-0011

- **One declared, non-additive oracle change.** Rule 1 ("at most one live mutating workspace") becomes "live mutating workspaces ≤ the policy cap, and every live one is bound to an active invocation". *(As built in M4-C, revised: the cap is an admission rule enforced by the guard, and the rule is path uniqueness; the second clause does not hold. See "M4-C as built".)* The four tests that assert the serial cap change, with the reason recorded in each. With the default policy (cap 1) every M1 to M3 behaviour is unchanged, and the full suite proves it.
- **Everything else is additive:** new oracle rules for the queue and lease (§6), new guards inside `DispatchDecision`, new commands.
- **Existing refusals keep their codes** (`CONCURRENCY_LIMIT`, `STALE_CANDIDATE`, `STALE_REVISION`, …). New ones are added to the registry.
- **The default policy keeps today's behaviour.** `mutating_concurrency: 1`, `post_integration.validation: verifier`. Concurrency is opt-in per project.
- ADR-0004 gets an amendment for the queue and lease, ADR-0003 for the new-attempt-on-conflict rule, and ADR-0009 for the containment mode and the guarantee label. These are amendments in the ADRs, not new semantics.

## R. Register triage (milestone-start rule)

Every open entry whose *When* names M4 or an earlier gate, every M4 candidate, and every other open entry, each marked **in scope**, **deferred** (with the reason) or **closed**. For the operator to ratify at plan review.

| Entry | Target before | Disposition | Phase or reason |
|---|---|---|---|
| Gate: before real-repository dogfood | Gate | **In scope** | M4-B: F2 containment acceptance on a real Rocky 8 kernel; Linux only (M4-B4) |
| Gate: before Linux runs rely on stop | Gate | **In scope** | M4-B: E13 |
| F2 | M4 (early) | **In scope** | M4-B |
| E13 | Gate | **In scope** | M4-B, with F2 |
| F3 | M4 | **In scope**: the concurrency part | M4-C. Large-repository benchmarks and other strategies (overlay, sparse) deferred: the selection gate for project defaults needs repositories M4 does not run on |
| F10 | M4 | **In scope** | M4-D |
| D4 | M4 | **In scope** | M4-D |
| E1 | M4 | **In scope** | M4-D |
| O4 | M4 | **In scope**: the wait-any part | M4-D (E1). The choreography part is F15 (M4-E) |
| F14 | Post-M3 direction; M4 for its extension points | **In scope**: `DispatchDecision`, protected conditions, the Class 0 checker, plan lint | M4-A. Phases 1 to 4 stay Evaluation (F19). Gating dispatch on `ASSURED` needs its WC amendment (Phase 5): deferred |
| F15 | M4 | **In scope** | Foundation in M4-A, stages in M4-E after promotion (M4-B2, met 2026-10-05) |
| E2 | M4 (early reconnaissance) | **In scope** | M4-A: subprocess-aware coverage of the harness code, as evidence for where M4's tests are thin; not a gate |
| F20 | M4 | **In scope** | F track |
| F20.2 to F20.6 | M4 | **In scope** | F track; F20.3 with its own security acceptance (M4-B8) |
| U1 | M4 candidate | **In scope** | M4-G: stall detection in `harness wait`; needed before the Q7 hard dogfood |
| U8 | M4 candidate | **In scope** | M4-G: a run ended without its output, made conspicuous |
| V1 | M4 candidate | **In scope** | M4-G: relaunch re-reads the provider key, or reports the auth failure as its own status |
| V2 | M4 candidate | **In scope** | M4-G: the refusal names takeover as the next step |
| V4 | M4 candidate | **In scope** | M4-G: long checks through `aew check run` with the policy's timeout |
| E12 | M4 candidate | **In scope**, form for the designer | M4-G: `aew evidence show`, unless the designer picks the next-action form |
| U5 | M4 candidate | **Deferred** | Stage commands (M4-E) change the command references. Generate them after M4-E, as part of the guide (F16) |
| O2 | M4 candidate | **Deferred** | The headless Lead's allow-list follows the git-write decision (M4-B3) and the stage commands. Revisit at M4-E |
| F4, F5 | Hierarchy revision | **Deferred** | Their own milestone. M4-B5 creates new attempts, not Ticket revisions |
| F6, O3, U3, U10, V3 | Designer | **Deferred** | They wait for designer decisions. O3 stays open until F14's fix is accepted |
| F7, F11 | M5 | **Deferred** | The scheduler and delegation governance consume M4's `DispatchDecision` and `ActionProjection` |
| F12, F13, D3, U9 | M6 | **Deferred** | Capabilities and skills |
| F16 | Evaluation | **Deferred** | Its content follows F15's stages. The next measurement is M4-H's dogfood |
| F17, F19 | Evaluation | **Deferred** | Evaluation program, no product code. M4-H's dogfood uses F19's format where it exists |
| F8, F9, F18, D1, D2, D5, E3, E4, U4, U6 | Unscheduled | **Deferred** | Nothing in M4 depends on them. F9's wait-any part is E1. E7 (lint) was built between M4-A and M4-B as the static checks (`testing-and-ci-strategy.md`) |
| E6, E14, U7 | On measured need | **Deferred** | No measured need yet. U7 needs U1 observed first |
| Q4, Q5, Q7, Q8, Q11, Q12 | Designer | **Deferred** | Open questions. Q7's scratch rule binds every M4 dogfood run (M4-B9) |

### R.2 M4-C start: entries added since M4 began (milestone-start rule)

The register gained entries after the M4 triage above: from the architecture review and its proposed response (Q13), and from the four independent area reviews of M4-A and M4-B. Each is marked for the operator to ratify. **Proposed** marks a disposition the response itself leaves to Q13. Rows were updated after the operator's review of this phase (2026-10-04) against design decisions made since: E18, F23, F24, F25, E21, Q13, E30 and ISO-004.

| Entry | Disposition | Phase or reason |
|---|---|---|
| F3 (the concurrency part) | **In scope** | M4-C: this phase |
| F21 the M6b knowledge system | **Deferred** | M6b. The response affirms the drafts as the direction; its storage and identity questions are D-AR4 |
| F22 project maps | **Deferred** | After M4, or a bounded deterministic slice in M4-G/H if it does not put approved scope at risk (response §12). Not an M4 gate |
| F23 pre-internal-alpha hardening | **Deferred** (implementation) | Implementation stays pre-internal-alpha. Network-containment research (architecture thread T6) is active now and informs it |
| F24 a second harness adapter | **Deferred** (production adapter) | M5, or earlier if OpenCode drift blocks operation (G4). OpenCode/Codex integration research (thread T9) is active now |
| F25 the cost and usage ledger | **In scope, before M4-H** | With the evaluation component (thread T2, F19), its first consumer, and available before M4-H's evaluation |
| F26 minimal skill delivery | **Deferred** | Needs design or a probe (response §7); M6a |
| F27 dogfood AEW on AEW | **Deferred** | A strategic goal once containment, real-repository and integration conditions hold |
| Q13 accept the review response | **Closed** (not M4 scope) | Accepted by the operator on 2026-10-05 after the designer reconciled the three differences; the response is a decision record in `docs/design/`; ARV-01 to ARV-05 dispositioned (register §9) |
| E17 OpenCode upgrades | **In progress** | Part 1 (meaning comparison, stored-credential check) in its own PR; part 2 (2.0.22 on the live lane, `TESTED_VERSIONS`) needs the operator's binary and provider key |
| E18 transaction outbox | **In scope** | M4-D, the full design: ADR-0012 (frozen) makes the transaction log the outbox, with typed events, complete overflow handling, sealing and a hash chain |
| E19 amendment index | **In scope** (proposed) | M4-G: the machine-readable index now; the consolidated WC/KC re-freeze after M4 |
| E20 `--json` on read commands | **In scope** | M4-E/F, with F15 and D-AR2 |
| E21 `aew init` proposes the test command | **In scope** (proposed) | M4-G, informed by the bootstrap and install UX work (thread T10), not designed on its own |
| E22 heartbeat `doctor` check | **Deferred** | On measured need: large-host re-parse bounds first |
| E23 Windows coverage | **In scope** (proposed) | M4-G |
| E24 typed record models | **Deferred** | Unscheduled; no runtime dependency, no consumer yet |
| E25 a real Rocky 8 CI lane | **Deferred** | Depends on infrastructure; the VM remains the per-phase acceptance host |
| E26 split the Windows serial job | **In scope** (proposed) | M4-G (CI hygiene); never by raising the timeout |
| E27 OpenTelemetry-shaped spans | **Deferred** | A probe, only with a concrete consumer and an air-gap-safe retention plan |
| E28 structured `check.run` results | **In scope** | M4-E, with F15 and D-AR2 |
| E29 context-pack budget order | **In scope** (proposed) | M4-G: a pack-generator invariant, before any recall exists |
| E30 the register as structured data | **Deferred** | Until a real machine consumer justifies structured-register work |
| Area 2, T6 (custody check independent of card operations) | **In scope** | A small PR alongside M4-C |
| Area 2, T8 (streaming credential scan) | **Deferred** | A register E-item, on measured need |
| Area 3, D9 and area 4, I9 (an in-process `Engine` test driver) | **Deferred** | A register E-item (efficiency); one driver serves both |
| Area 4, I6 (the sync classifier under concurrent publishers; bounded lock hold for large publishes) | **In scope** | M4-D's plan: publication stays serialized under the control lock in M4-C, so one publisher at a time still holds |
| Area 4, I8 (`_interrupt_invocations` through `set_state`; `doctor` lists orphan worktrees) | **In scope** (proposed) | M4-G (hardening) |
| `AEW-INV-ISO-004` lock | **Moved to M4-D** (operator, 2026-10-04) | No M4-C operation needs it; it lands with the lease, its first consumer (see "M4-C as built") |

## 5. Phases

One PR per phase, each with its own tests, the local lanes green on Windows and Linux (WSL), and CI's `assurance` green. The F track interleaves wherever it is ready.

| Phase | Work | Exit criteria |
|---|---|---|
| **M4-A** Foundation | §2.1 to §2.3, E2 | Every entrypoint in the declared dispatch-entrypoint registry, CLI and internal (harness launch and relaunch, `--launch`, the Lead broker), reaches `DispatchDecision`, proven by the conformance test. The CLI enumeration proves no CLI dispatch command bypasses the registry; query equals execution, per migrated route; no cached ALLOW (a seeded revision change between query and execute refuses); reason-code registry; `PrimitiveSpec` for the integration primitives; protected-condition, Class 0 and plan-lint regressions from v0.4 §31; the cap as a guard reading policy, default 1; full suite unchanged |
| **M4-B** Containment (Linux) | §2.4 | Isolation §12 list fails at the OS level; E13 passes with `NSpid` translation; fingerprint and `prepare` hold with the private store; the launch self-test fails closed; the research §6 probes pass on a **real Rocky 8 kernel** (needs a Rocky 8 host, see "Remaining open items"); guarantee labels truthful on both platforms, network `NOT PROVIDED` |
| **M4-C** Workspaces N > 1 | §2.5 | Two and four concurrent mutating Tickets on the scripted drivers; the oracle with the new rule 1; the cap as an admission rule (lowering it drains, never evicts); worktree setup and cleanup costs recorded |
| **M4-D** Queue engine | §2.6 to §2.9 | Records, transitions and oracle rules for the queue and lease; every §7.1 disposition as a regression (lease owner, a live custodian across acquire to release (M4-B10), dead custodian, no timeout release, one rebuild, second move to disposition, conflict to the Lead, no head-of-line blocking, retirement with archival); fault points inside the lease transitions killed by real processes; downgrade test (the baseline engine refuses an M4 control file); D4 path; wait-any; ISO-004 lock tests (stale owner reconciled; the lock without an ALLOW moves nothing; moved from M4-C) |
| *(gate)* | The designer promotes F15 v0.4 | **Met 2026-10-05:** the typed Lead surface v0.2 merged as a governing design |
| **M4-E** Stages | §2.10 | Stage and primitive equivalence; mixed-mode walks; seeded policy drift; `PUBLISH_IF_CLEAN` across exactly one head-move rebuild; `VALIDATE_ONLY`; takeover with an active stage |
| **M4-F** Queue UX | §2.11 | `integrate next`; the queue in `status`, `resume` and the guide; `lead-guide.md` regenerated |
| **M4-G** Candidates | U1, U8, V1, V2, V4, E12 | One regression each |
| **M4-H** Acceptance | §7 | Metrics at concurrency 1, 2 and 4; the preregistered dogfood; reviewer brief; independent review; fixes in that PR |
| **F20.2 to F20.6** | §2.12 | Per the register rows. F20.3's security acceptance before F20.5; F20.6 last |

## 6. Test coverage (new oracle rules and where they live)

| Property | Where |
|---|---|
| Every registered dispatch entrypoint (CLI, harness, Lead broker) reaches `DispatchDecision`; no CLI dispatch command is missing from the registry | `tests/unit/test_dispatch_decision.py` (the registry and the CLI enumeration), `tests/integration/test_engine_dispatch.py`, `tests/integration/test_lead_session.py` (the broker path) |
| Query equals execution; no cached ALLOW | `tests/regression/test_m4_dispatch.py` |
| The lease has a live custodian from acquire to release | `tests/integration/test_queue.py` |
| A valid 304 keeps the cached envelope; any envelope or revision change returns 200 | `tests/integration/test_dashboard_api.py` |
| No two live mutating workspaces share a path (rule 1, revised); the cap is enforced at admission, and lowering it drains | `tests/helpers/invariants.py`, `tests/integration/test_workspaces.py` |
| At most one lease; its owner is a live entry; its custodian is an active invocation or reconciliation is pending (new rule) | `invariants.py`, `tests/integration/test_queue.py` |
| No publication without the lease, a current ALLOW and validation bound to the current head (new rule) | `invariants.py`, `tests/regression/test_m4_queue_walk.py` (seeded adversarial walk, like the M1 to M3 walks) |
| Queue state never grants eligibility | `test_queue.py` |
| One automatic rebuild; the second goes to disposition | `test_queue.py` |
| A conflict makes a new attempt; snapshot proof does not carry | `tests/regression/test_m4_invalidation.py` |
| ISO-004 is serialization only (M4-D) | `tests/integration/test_queue.py` |
| Containment (Linux) | `tests/live/` and a new `containment` marker, run on Rocky 8 and WSL; never on Windows |
| Downgrade safety | `tests/regression/test_m4_schema_downgrade.py` |
| F20.3 security | `tests/integration/test_dashboard_session.py` (each negative case) |

Real concurrency (two `aew` processes racing a lease grant) runs in the `serial` lane.

## 7. Evaluation and dogfood (M4-H)

- **Metrics** (queue research §5), at concurrency 1, 2 and 4:
  - queue wait;
  - time per tail phase (prepare, validate, publish);
  - rebuild rate by cause;
  - post-integration verdicts that differ from Ticket-scope verdicts;
  - Lead cost per integrated Ticket;
  - the Lead's `STALE_REVISION` rate (spike fact 2);
  - `resume` time against open units.
- **Dogfood:**
  - preregistered, in F19's format where it exists;
  - real-repository mutating runs on Linux/Rocky only, inside M4-B's containment (M4-B4);
  - it evaluates `PUBLISH_IF_CLEAN` (idea note §17);
  - hidden material lives in `aew-private`, as before.
- **Hard gates:** no false advance, judgment captured at every boundary, anomalies caught, recovery correct (idea note §21). Queue wait is reported, not gated.

## 8. Out of scope

- Batching or speculative stacking (queue options B and C).
- Shared post-integration evidence.
- Gating dispatch on `ASSURED` (needs F14's WC amendment).
- Network isolation.
- Containment on Windows hosts.
- The M5 scheduler.
- Overlay, sparse and large-repository workspace strategies.
- Projecting the queue in the dashboard contract.
- Dashboard write actions.

## 9. Verification

- **Each PR:** fast, integration, regression, adversarial and serial lanes on Windows (Python 3.13) and WSL Ubuntu (Python 3.11); CI's `assurance` green; a secret scan before each commit.
- **M4-B:** the containment lane on WSL Rocky (`aew-q7`, in its own clone and venv, never `~/aew`) and then on a real Rocky 8 kernel.
- **M4-D:** the seeded adversarial queue walk at 3 seeds × 500 steps, and the downgrade test against `42239e1`.
- **M4-H:** the metrics above, the dogfood report, and the independent review from a reviewer brief, with fixes in that PR.

## 10. Critical files

- **New:**
  - `src/aew/engine/dispatch.py` (`DispatchDecision`, reason codes);
  - `src/aew/engine/primitives.py`;
  - `src/aew/engine/queue_ops.py`;
  - `src/aew/engine/protected.py`;
  - `src/aew/engine/class0.py`;
  - `src/aew/policy/plan_lint.py`;
  - `src/aew/harness/containment/` (bubblewrap launcher, `NSpid`);
  - `src/aew/dashboard/` (server, session, static assets);
  - the tests in §6.
- **Changed:**
  - `engine/workspace_ops.py` (cap to guard);
  - `engine/integration_ops.py` (lease-bound prepare, validate, publish);
  - `engine/evidence_ops.py`, `engine/nonmutating_ops.py`, `engine/hierarchy_ops.py`, `engine/harness_ops.py` (routes through the predicate);
  - `engine/archive_ops.py` (retiring queue entries);
  - `engine/authority.py` (the session credential);
  - `engine/ports.py`, `engine/api.py`;
  - `schemas/control.schema.json`;
  - `tests/helpers/invariants.py`;
  - `engine/guide.py`.
- **ADR amendments:** 0003, 0004, 0009.
- **Reused:**
  - `transitions.py` and `seams.GuardTable` (guards);
  - `KindRegistry`;
  - `integration.cas_publish`, `merge_candidate`, `allocate_detached`;
  - `policy/checks.py` (D4);
  - `runlog.observed_status` (wait-any);
  - `operator.authorize` (F20.3);
  - `history/index.py` (F20.2 cursors);
  - `harness/contract.py` credential redaction.

## Remaining open items (not designer questions)

- **A real Rocky 8 host** for M4-B's kernel regression: a VM or machine with no secrets or real project state within reach, reachable over SSH. The operator provides it before M4-B's exit.
- **The form of E12** (an evidence view or next actions carrying conclusions): the designer's call, raised at M4-G.
- **The invariant index wording for ISO-004** (M4-B6): the designer owns the index.
