---
title: "Agent Engineering Workflow"
subtitle: "Design Specification — v0.7"
date: "September 25, 2026"
---

# Status and authority

**Status:** Frozen design specification, v0.7.  
**Working name:** Agent Engineering Workflow (AEW). The project may be renamed without changing this design.  
**Purpose:** Define the authoritative engineering process for LLM-assisted software development.  
**Primary implementation target:** OpenCode on the Rocky Linux 8 development VM, with GPT-5.4 as the initial general-purpose model and a provider-independent architecture.  
**Reference influences:** GSD and Superpowers are useful prior art and possible implementation adapters. They are not authoritative specifications for this project.

This document defines the workflow we intend to build. Where a framework or tool disagrees with this document, the framework or tool must be configured, adapted, replaced, or omitted. The project must not inherit process rules merely because an upstream framework happens to implement them.

**Design authority is intentionally ahead of implementation.** v0.7 specifies the target operating model even where automation, adapters, or enforcement do not yet exist. A workflow capability may therefore be in one of three states: **implemented**, **staged** (required tooling/configuration/artifacts are present but orchestration is not yet automated), or **designed** (specified here but deferred). The September cutover does not require every section of this specification to be implemented. It requires a safe minimum operational slice plus the repository/image foundations needed to implement the remainder without another architecture reset.

# 1. Problem statement

Modern coding models are strong at local software tasks but have two recurring weaknesses that become serious on large brownfield systems.

First, they lose the project-level thread. They may understand an individual file while failing to maintain a durable model of what the system is trying to accomplish, which component owns a behavior, which architectural decisions already exist, or why the current work item matters. This creates premature implementation, duplicate abstractions, incorrect ownership, and solutions that are locally plausible but globally wrong.

Second, even when the high-level plan is correct, models often lack disciplined low-level engineering behavior. A statement such as "implement this work item and verify it" does not define how the code should be written, how changes should be decomposed, when a reproducer should be created, what tests are required, how error paths should be considered, how code should be reviewed, or how independent validation should occur before the change is considered complete.

The workflow therefore needs two complementary control layers:

1. **Project control:** preserve the problem, architecture, decisions, plan, and completion criteria across a long-running effort.
2. **Engineering execution:** define how an individual planned Ticket/work item is implemented, debugged, reviewed, verified, and promoted to a completed change.

A strong coding model should operate inside this structure rather than replacing it.

# 2. Design objective

Create a provider- and harness-independent engineering workflow that behaves more like a disciplined software team than a single unconstrained coding assistant.

The workflow must:

- force understanding before implementation;
- distinguish investigation from design and design from coding;
- preserve one authoritative plan and project-state lineage;
- make architectural and ownership constraints explicit;
- give implementers a defined low-level development discipline;
- separate implementation from independent review;
- separate code review from system-level verification;
- treat failed validation as evidence requiring diagnosis, not an invitation to patch blindly;
- scale its ceremony to the risk and ambiguity of the work;
- externalize important state into durable artifacts rather than relying on chat history;
- support multiple models, harnesses, tools, and specialists without creating competing authorities;
- be **workflow-portable but environment-aware**, so a known workbench can expose richer capabilities without hard-coding specific tool products into lifecycle semantics;
- remain useful if OpenCode, GPT-5.4, GSD, Superpowers, or any other current dependency is later replaced.

# 3. Non-goals

Version 0.7 does not attempt to:

- build a new model runtime or coding-agent harness;
- create a swarm of autonomous agents for every work item;
- replace human engineering judgment or organizational approval;
- require every role to be a separate concurrent process;
- mandate test-driven development where it is inappropriate;
- require a heavyweight process for trivial edits;
- make memory systems authoritative over repository documentation;
- make a derived code index authoritative over source;
- reproduce every feature of GSD or Superpowers;
- encode one vendor's model assumptions into the project lifecycle;
- redesign the development projects that use this workflow;
- claim that the full target workflow must be automated before the September cutover.

The immediate cutover goal is an **implementation-ready design plus a minimum operational slice**. Where time does not permit full orchestration, required runtime tooling, skills, image recipes, manifests, adapters, and acceptance fixtures should still be staged in the agent-toolchain repository so later implementation does not require another discovery or packaging effort.

# 4. Foundational model: two coordinated planes

The workflow is divided into a **Project Control Plane** and an **Engineering Execution Plane**.

## 4.1 Project Control Plane

The Project Control Plane prevents the model from losing the larger objective. Its canonical lifecycle is:

**Understand → Research → Design/Plan → Execute → Validate → Complete or Replan**

Each stage has an explicit purpose.

### Understand

Establish what problem is being solved and what success means before proposing an implementation.

Questions include:

- What behavior is desired?
- Why is it desired?
- What is in scope and out of scope?
- Which constraints are already known?
- Which decisions remain unresolved?
- What observable result would demonstrate success?

### Research

Build an evidence-backed model of the relevant system before designing the change.

Research may include:

- codebase discovery;
- current ownership and call paths;
- tests and existing behavior;
- architecture and contract documents;
- dependency and library capabilities;
- relevant external or local documentation;
- prior decisions and implementation history;
- runtime evidence where static inspection is insufficient.

Research must distinguish observed facts from hypotheses.

### Design / Plan

Translate the problem and research into an explicit implementation contract.

The plan must identify:

- objective;
- governing constraints and contracts;
- current architecture relevant to the change;
- chosen approach;
- important rejected alternatives where useful;
- affected components;
- ordered implementation tasks;
- required tests;
- required verification evidence;
- risks and escalation triggers.

The accepted plan is revisioned. New evidence does not silently rewrite history. If the plan changes materially, a new plan revision records why.

### Execute

Assign planned work to the Engineering Execution Plane. Execution follows the accepted plan unless evidence proves the plan invalid or incomplete.

### Validate

Determine whether the requested behavior actually exists in the relevant system, not merely whether the implementer reports success.

Validation may inspect tests, persisted state, APIs, logs, graph relationships, vector stores, UI behavior, binaries, performance, or other domain-specific evidence.

### Complete or Replan

Only the Project Control Plane may mark the work complete. A failure returns evidence to diagnosis and, when needed, design/replanning.

## 4.2 Engineering Execution Plane

The Engineering Execution Plane governs how a planned Ticket/work item becomes trustworthy code.

Its default lifecycle is:

**Prepare → Reproduce/Specify → Implement Incrementally → Local Checks → Self-Review → Independent Review → Fix Loop → Independent Verification → Commit-Ready**

This layer is intentionally more prescriptive than the high-level project plan.

### Prepare

Before editing, the implementer must understand:

- the assigned Ticket/work item;
- the accepted plan revision;
- relevant contracts;
- the intended files/components;
- applicable specialist guidance;
- success and failure criteria.

If these inputs contradict the observed code, the implementer reports a plan contradiction rather than silently changing the design.

### Reproduce or specify the failure/behavior

When repairing a defect, produce a reliable reproducer before patching when practical.

When implementing new behavior, establish an executable or otherwise observable acceptance condition before declaring the work complete.

This may be a failing test, integration fixture, diagnostic command, captured state query, or another deterministic check.

### Implement incrementally

Prefer bounded, reviewable changes over large speculative rewrites.

The implementer should:

- modify only the scope justified by the plan;
- preserve existing ownership boundaries;
- avoid opportunistic unrelated cleanup;
- consider error and cleanup paths, not only happy paths;
- keep API/ABI/schema compatibility in view where applicable;
- run focused feedback frequently enough to catch mistakes near their source.

### Local checks

Run the cheapest checks capable of detecting likely defects before requesting review. Examples include compilation, targeted tests, linters, static analysis, sanitizers, type checking, browser checks, or project-specific validators.

### Self-review

Before handing work to an independent reviewer, the implementer inspects the diff against the plan and checks for scope drift, missing error handling, accidental changes, stale tests, and unresolved TODOs.

Self-review does not replace independent review.

### Independent review

A reviewer receives a fresh or deliberately bounded context. The reviewer evaluates the change against the requirement, contracts, accepted plan, diff, and actual test output rather than inheriting the implementer's full conversational rationale.

The reviewer reports findings. The reviewer should not silently fix its own findings in the same review step.

### Fix loop

Review findings return to implementation. Significant findings may trigger renewed investigation or a new plan revision.

### Independent verification

Verification answers a different question from review:

- Review asks, **"Is this implementation technically sound and consistent with the plan?"**
- Verification asks, **"Did this change actually produce the required behavior in the relevant system?"**

Verification should be independent of the implementer's claim of success.

### Commit-ready

A meaningful change becomes commit-ready only after required review and verification gates pass. Whether the agent may create the actual commit is a separate configurable policy.

# 5. Roles

Roles define **authority and context contracts**, not persistent agent identities. A role is a reusable execution template that specifies:

- authority;
- responsibilities;
- required inputs;
- allowed actions;
- prohibited actions;
- required outputs/artifacts;
- context policy;
- independence requirements.

A concrete run is an **invocation of a role**. The same underlying model may perform different roles in separate invocations where policy allows it. Conversely, the same role may later be executed by a different model, harness, or human without changing workflow semantics. The project should therefore store role definitions as durable workflow artifacts rather than treating long-lived agent identities as architecture.

AEW does, however, define one intentional persistence pattern: the **Engineering Lead / Project Controller is the default persistent agent context for an active project or work lineage**. The Lead owns coordination continuity and may remain active across multiple subordinate invocations. Investigator, Researcher, Planner, Implementer, Reviewer, Verifier, Specialist, and Frontier Advisor are normally created as bounded subagents/contexts when the workflow requires them and are retired after returning their artifact or result.

Persistence does not make the Lead a hidden source of truth. The Lead must be reconstructible from durable AEW artifacts. If the session is lost, a new Lead invocation must be able to rebuild the active objective, state, accepted plan, unresolved findings, and next action from repository/project artifacts rather than depending on inaccessible chat history.

**Single-authoritative-Lead rule:** at most one Lead context may hold coordination authority for a given active project/work lineage at a time. Additional Lead-like sessions are observers, assistants, or proposed successors until an explicit handoff/authority transfer is recorded. A successor must reconstruct state from durable artifacts before assuming authority. Concurrent independent Leads must not silently mutate the same active control-state lineage.

**Crash-safe control-authority rule:** authoritative control-state updates must be version-aware and atomic from AEW's perspective. Each mutating control operation must be conditioned on the current control-state revision and current Lead authority generation (or an equivalent stale-writer guard). An explicit Lead handoff advances authority so that a superseded Lead/session cannot later overwrite accepted state. Interrupted writes must recover to either the previous valid state or the new valid state, never a partially applied hybrid. Copies of control artifacts inside isolated Ticket workspaces are contextual snapshots only and must never become independent control authorities. The concrete locking/CAS/atomic-write mechanism is an implementation choice.

For example, `Reviewer` is a role definition. `Review Invocation #184 using GPT-5.4 in fresh context` is one execution of that definition. `Lead Session #12` may persist across those invocations, but its durable authority is the workflow state and accepted artifacts it reads and writes.

## 5.1 Engineering Lead / Project Controller

The Lead is the single owner of workflow coordination state and the **only role that is persistent by default**. It is the user-facing engineering coordinator for an active project or work lineage. Other roles are normally invoked as bounded subagents by the Lead and return structured artifacts/evidence to it.

The Lead should remain lightweight enough to survive long-running work without becoming an implementation scratchpad. It should prefer delegating substantial investigation, implementation, review, and verification so that those activities can use focused contexts and so that the Lead retains a clean model of objective, state, decisions, and unresolved risk.

Authority:

- active objective;
- work-unit and risk classification;
- requirement decisions;
- lifecycle/work-state transitions;
- accepted plan revision;
- assignment and dispatch;
- escalation decisions;
- final completion decision.

The Lead may coordinate work but should normally avoid implementing substantial changes itself because doing so collapses decision authority and execution into one context. For trivial Class 0/1 work it may perform a reduced path when policy allows, but that is an optimization, not the default for substantial work.

On startup or resume, the Lead must reconstruct its context from the authoritative artifact set: requirement/problem record, active workflow state, accepted plan revision, current handoff, open review/verification findings, and relevant project contracts. Memory may help locate these artifacts but may not replace them.

## 5.2 Investigator

Default posture: read-only.

Purpose: determine how the existing system actually works.

Responsibilities:

- locate owners and entry points;
- trace relevant relationships;
- inspect tests and existing behavior;
- identify governing contracts;
- gather runtime evidence when needed;
- separate facts from hypotheses;
- identify unresolved questions.

The Investigator does not choose the final design merely because it discovered the relevant code.

## 5.3 Researcher

Purpose: resolve questions about technologies, dependencies, APIs, protocols, standards, or other knowledge external to the current codebase.

Researcher and Investigator may be the same execution context for small tasks, but the conceptual distinction remains useful:

- Investigator: **What does our system do?**
- Researcher: **What does the external technology actually support?**

## 5.4 Planner / Designer

Purpose: convert requirements and evidence into the accepted implementation design.

The Planner must make dependencies, risks, affected components, validation requirements, and plan assumptions explicit.

The Planner does not mark its own plan complete merely because it is internally coherent; the Lead accepts the plan.

## 5.5 Implementer

Purpose: execute assigned Tickets/work items from the accepted plan.

Authority:

- modify source and tests within assigned scope;
- invoke development tools;
- produce implementation evidence;
- report contradictions or blockers.

The Implementer may not silently:

- redefine architecture;
- broaden the requirement;
- change project completion state;
- override repository contracts;
- claim independent verification.

## 5.6 Reviewer

Default posture: context-independent and read-only with respect to the reviewed change.

Two different forms of independence must be distinguished:

- **Context independence:** the reviewer did not participate in implementation and receives a deliberately bounded review package rather than the implementer's full conversational history.
- **Model independence:** the reviewer uses a different model/model family or other independent human/tool source, reducing some correlated model blind spots.

AEW requires context independence for routine independent review (Class 1+) unless an explicit exception is recorded. Class 1 review may use a deliberately narrow package; Class 2+ review is broader by default. Model independence is supported and should be evaluated for higher-risk/high-volume work, but it is not a v0.7 baseline requirement.

Purpose: identify defects, plan violations, missing tests, ownership mistakes, security issues, error-path problems, and unnecessary scope.

Inputs should normally include:

- requirement;
- governing contracts;
- accepted plan revision;
- diff/change set;
- relevant test and analysis output.

The review artifact must classify findings by severity and disposition.

## 5.7 Verifier

Purpose: independently evaluate acceptance criteria against the actual system or artifact.

The Verifier may inspect:

- runtime behavior;
- authoritative persisted state;
- integration/API behavior;
- graph/vector state;
- UI behavior;
- binary/runtime characteristics;
- logs and provenance;
- performance or operational evidence.

The Verifier reports pass/fail/inconclusive with evidence. It does not decide project completion; the Lead consumes the verification result.

## 5.8 Specialist

A Specialist supplies domain-specific engineering guidance within another role. Examples include C reviewer, Python reviewer, frontend specialist, security reviewer, database specialist, or release engineer.

Specialists do not create parallel workflow authority.

## 5.9 Frontier Advisor

A Frontier Advisor is an escalation role for problems whose correct design or root cause is not becoming clear through the normal workflow.

The escalation package must include:

- objective;
- constraints;
- relevant architecture;
- evidence gathered;
- failed hypotheses;
- unresolved questions;
- current plan revision if one exists.

The Frontier Advisor returns analysis and proposals to the same Project Control Plane. It does not start a separate project lineage.

# 6. Authority model

The workflow follows a strict single-authority principle.

| Concern | Authority | Supporting inputs |
|---|---|---|
| Requirement and objective | Engineering Lead / accepted project artifact | User/stakeholder decisions |
| Existing system facts | Source, runtime evidence, authoritative project data | Investigator, tools, indexes |
| Architectural contracts | Repository contract/ADR/design documents | Memory and research may locate them |
| Accepted implementation plan | Project Control Plane | Planner, Investigator, Researcher |
| Code modification | Assigned Implementer | Specialist skills and tools |
| Review findings | Reviewer | Static/dynamic analysis and specialist guidance |
| Acceptance evidence | Verifier | Tests, state queries, runtime observations |
| Verification-failure classification | Engineering Lead | Verifier evidence; Reviewer/Specialist input when warranted |
| Concurrent-work integration decision | Engineering Lead | Ticket results, isolation state, conflict/integration evidence |
| Authoritative control-state mutation | Current Engineering Lead through state engine | Expected state revision + current authority generation/stale-writer guard |
| Completion | Engineering Lead | Review + verification evidence |
| Historical recollection | Memory system | Never overrides current authoritative artifacts |
| Derived code relationships | Search/index service | Must be confirmed against source when consequential |

The Verifier establishes whether acceptance evidence passes, fails, is inconclusive, or is blocked. The Verifier may describe a suspected cause, but it does **not** decide whether a failed verification is a local implementation defect, a plan/design defect, a contract violation, or an environment/evidence problem. That classification belongs to the Lead because it controls whether work returns to implementation, replans, or remains blocked.

No tool, memory service, code index, reviewer, verifier, implementer, or subordinate agent may become an accidental second project-management system.

# 7. Work units, risk classes, and proportional ceremony

AEW separates **what kind of work is being managed** from **how risky or ambiguous that work is**. The earlier generic term `task` is retired as the primary user-facing work-unit name because it overloaded too many meanings.

The durable work hierarchy is:

**Project → Epic → Story → Ticket**

A **Ticket** is the smallest independently executable engineering work item. A **Story** is a coherent engineering objective normally decomposed into a small dependency graph of Tickets. An **Epic** is a larger feature or initiative composed of multiple Stories and normally receives the full Project Control lifecycle.

Review and verification are gates on work units. They are not automatically represented as synthetic Tickets merely to inflate the graph. A review becomes its own Ticket only when the review itself is substantial engineering work, such as a formal security audit, broad compatibility assessment, or performance characterization.

`Phase` is not a fourth executable work-unit type. Projects may use phases, releases, or milestones as roadmap/time groupings, but AEW scheduling and durable engineering state operate on Epic/Story/Ticket identities.

## 7.1 Ticket

A Ticket has one bounded objective and one natural completion boundary.

Typical properties:

- normally executable by one bounded Implementer invocation;
- explicit dependencies when applicable;
- explicit completion criteria;
- proportionate local checks;
- review and verification gates determined by policy/risk;
- may originate directly from a user command or be generated by Story planning;
- may be promoted to a Story if investigation reveals hidden scope.

Examples include adding one counter field and update path, adding one API field, correcting one bounded parser defect, or adding a targeted regression test.

## 7.2 Story

A Story is one meaningful behavioral/subsystem objective that requires a small set of Tickets, commonly around two to five implementation Tickets though AEW does not enforce a numeric limit.

A Story owns a local Ticket dependency graph. Independent READY Tickets may execute concurrently only when the concurrency-isolation rules in §8 are satisfied. Story completion requires both child-work completion and Story-level acceptance/review gates.

Example: `Add transaction accounting to the protocol connection lifecycle` may decompose into Tickets for state fields, initialization/reset, update paths, reporting exposure, and regression coverage.

## 7.3 Epic

An Epic is a larger feature or engineering initiative composed of multiple Stories. It normally receives the full Understand → Research → Design/Plan → Execute → Validate lifecycle and may span multiple sessions or calendar periods.

Example: `Implement end-to-end protocol observability` may contain Stories for connection counters, structured event logging, API exposure, UI visualization, and operational validation.

## 7.4 Risk / complexity classes

Risk classes are orthogonal to the work-unit hierarchy.

- **Class 0 — trivial/mechanical:** obvious bounded change with little behavioral ambiguity.
- **Class 1 — routine engineering:** ownership/design understood; bounded normal work.
- **Class 2 — substantial brownfield:** meaningful codebase understanding or cross-component effects required.
- **Class 3 — architectural/high-risk:** ownership, security, compatibility, or design choices need explicit resolution.
- **Class 4 — frontier:** normal workflow cannot confidently resolve the design/root cause or repeated attempts fail without new evidence.

Examples:

- Ticket + Class 0: one obvious mechanical edit.
- Ticket + Class 2: tiny diff on a public ABI or security boundary.
- Story + Class 1: several straightforward related Tickets.
- Story + Class 3: bounded objective with architectural ambiguity.
- Epic + Class 3/4: cross-layer feature or unresolved architecture.

Classification may increase whenever evidence exposes additional risk. Demotion requires an explicit Lead decision with rationale.

### Parent/child risk and inherited policy

Risk classes do **not** numerically inherit by default. A Class-3 Story does not automatically turn every mechanical child Ticket into Class 3; each work unit is classified according to its own change surface, ambiguity, and risk so proportional ceremony is preserved.

However, non-waivable policies and gates triggered by an ancestor apply to descendants. For example, a Story that crosses a security boundary may require security review for all affected child Tickets even where one child is locally Class 0/1. A parent may also declare a **minimum descendant class** when the work cannot safely be decomposed below that level; the Lead must record the rationale.

Therefore a Ticket's effective execution obligations are:

```text
local risk-class path
+ inherited non-waivable ancestor gates/guardrails
+ any explicit parent minimum-class floor
```

## 7.5 Minimum paths

Typical paths are:

**Ticket / Class 0:** Implement → focused check → complete, plus any inherited mandatory gates.

**Ticket / Class 1:** Assignment/mini-plan → Implement → incremental/local checks → Self-review → lightweight independent review → goal-backwards + contract verification → complete, plus any inherited mandatory gates.

**Class 2 work:** Understand/Investigate → Plan → Implement → independent review → independent verification.

**Class 3 work:** Understand → Investigate + Research → Design discussion → accepted plan → implementation graph → specialist/independent review(s) → independent verification.

**Class 4 work:** normal evidence package → Frontier Advisor → revised design/plan → normal execution/review/verification.

# 8. Work graph and workflow state machine

AEW execution is represented as a **dependency-aware work graph**, not a purely linear checklist. A linear plan is simply a degenerate graph.

The Lead/Planner decomposes accepted work into Epic/Story/Ticket records with explicit dependencies. A dependency is satisfied only when the upstream output required by the downstream assignment is durably accepted and actually available in the downstream assignment's recorded input/source snapshot. For an evidence-only dependency, an accepted durable artifact may be sufficient. For a **mutating dependency**, local success in an isolated workspace is not sufficient: the accepted output must be integrated into the authoritative source lineage and the required post-integration checks must pass. Therefore a mutating Ticket at `COMMIT_READY` does **not** unblock dependent mutation; by default it reaches `DONE` only after controlled integration and required integration validation. Tickets whose dependencies are satisfied enter `READY`. The Lead may assign multiple READY Tickets concurrently only when configured resource limits **and the isolation rules in §8.1** are satisfied.

A typical Ticket state model is:

1. `BLOCKED`
2. `READY`
3. `ASSIGNED`
4. `RUNNING`
5. `REVIEW_PENDING`
6. `REVIEW_FAILED` or `REVIEW_PASSED`
7. `VERIFY_PENDING`
8. `VERIFICATION_FAILED`, `VERIFICATION_INCONCLUSIVE`, or `VERIFIED`
9. `COMMIT_READY`
10. `DONE`

Cross-cutting states:

- `INTERRUPTED` — execution identity/session lost; reconciliation required;
- `REPLAN_REQUIRED` — evidence invalidated the governing plan/dependency assumptions;
- `ESCALATED` — frontier/specialist escalation active;
- `CANCELLED` — work intentionally abandoned.

Story/Epic state is derived from child work plus Story/Epic-specific gates. Parent state must not be independently hand-maintained where it can be computed safely.

Example:

```text
Story S-14
  T1 DONE
  T2 DONE
  T3 RUNNING
  T4 BLOCKED -> T3
  T5 READY
```

The Lead may assign T5 while T3 continues only if concurrent mutation is safely isolated. When T3 completes, T4 may transition to READY immediately.

This is **dependency-aware dynamic scheduling**. A future executor may use queues or work-stealing algorithms internally, but those are implementation techniques beneath AEW semantics. Subagents do not independently redefine priorities or claim arbitrary work outside Lead scheduling authority.

Important transition rules:

- a mutating Ticket may start only when its dependencies and governing plan/assignment are accepted;
- `REVIEW_FAILED → RUNNING` requires recorded findings;
- the Verifier records `VERIFICATION_FAILED`, `VERIFICATION_INCONCLUSIVE`, or `VERIFIED` with evidence but does not choose the remediation path;
- after `VERIFICATION_FAILED`, the Lead classifies the failure as `LOCAL_IMPLEMENTATION_DEFECT`, `PLAN_OR_DESIGN_DEFECT`, `CONTRACT_VIOLATION`, or `ENVIRONMENT_OR_EVIDENCE_BLOCKED`;
- `LOCAL_IMPLEMENTATION_DEFECT → RUNNING` is permitted with the failure evidence attached;
- `PLAN_OR_DESIGN_DEFECT` or `CONTRACT_VIOLATION → REPLAN_REQUIRED` unless a higher-authority project process dictates a stricter transition;
- `ENVIRONMENT_OR_EVIDENCE_BLOCKED` remains blocked/inconclusive until the environment/evidence issue is resolved; it must not be disguised as an implementation success or design failure;
- `VERIFIED → COMMIT_READY` requires mandatory review findings resolved or explicitly waived by policy;
- `COMMIT_READY` means the isolated implementation is an accepted **integration candidate**; it does not imply that a Git commit exists, that integration has occurred, or that downstream mutating dependencies are satisfied;
- a mutating Ticket reaches `DONE` only after Lead-controlled integration makes its accepted output available in the authoritative source lineage and all policy-required post-integration checks/reviews/verification have passed for the integrated snapshot;
- only the Lead may close a Story/Epic or mark a work lineage complete;
- completion of children alone does not prove parent acceptance; Story/Epic-level goal-backwards and contract checks still apply.

## 8.1 Concurrent mutation isolation

Dependency independence is not sufficient to make two mutating Tickets safe to execute in the same workspace. Independent Tickets can still touch overlapping files/functions, generated artifacts, build directories, databases, ports, services, or other shared state that was not represented in the dependency graph.

AEW therefore uses these rules:

- read-only investigation/research may share a repository/worktree when provider/tool semantics are safe;
- **concurrent mutating Tickets require isolated worktrees/branches or an equivalent isolated mutation workspace**;
- build/runtime/test state must also be isolated where shared state could corrupt results or cause cross-talk;
- detected file/path overlap may be used as an additional scheduling signal, but zero detected overlap is **not** a substitute for isolation;
- if safe mutation isolation is unavailable, configured mutating concurrency is effectively `1`;
- each mutating assignment records its workspace/worktree identity;
- integration into the authoritative branch/worktree is controlled and serialized under Lead coordination;
- `COMMIT_READY` work remains unintegrated and cannot satisfy a mutating dependency merely because it passed isolated checks;
- integration changes the evaluated source snapshot: impacted checks/reviews/verification are rerun according to project policy before the Ticket becomes `DONE` and before dependent mutating work can become `READY`;
- downstream assignments must record a source/evaluated snapshot that actually contains all satisfied mutating dependencies.

The implementation may use Git worktrees, branches, disposable clones, containers, or another mechanism. The semantic requirement is isolation, attributable workspace identity, controlled integration, and revalidation of the integrated result.

## 8.2 Checkpoint and crash semantics

AEW should write durable checkpoints around consequential state transitions, including accepted plans, Ticket transitions, review/verification results, major artifact writes, parallel dispatch, integration, and explicit handoffs.

A checkpoint preserves workflow state and references to durable artifacts/workspaces. It does not attempt to serialize hidden model reasoning.

Authoritative control transitions must be committed atomically and with a stale-writer precondition. A transition therefore either leaves the previous valid state intact or publishes the complete new valid state. A process crash must not expose a half-applied transition. After Lead handoff, updates from the superseded Lead/session must be rejected rather than merged opportunistically.

If a crash occurs with in-flight assignments, those assignments are reconciled as `INTERRUPTED`/unknown until their worktree/artifacts/results are inspected. AEW must never infer success from the fact that an invocation was previously running.

## 8.3 Human-facing work views

The work graph is also AEW's canonical to-do system. `/status` should be able to render projections such as:

```text
NOW
  T-104 RUNNING @ worktree/T-104

READY
  T-105
  T-108

BLOCKED
  T-106 -> T-105

REVIEW
  T-102

VERIFY
  T-103
```

A separate informal to-do list must not become a second scheduling authority.

# 9. Required artifacts and provenance

The workflow communicates important state through durable artifacts rather than relying on hidden model context. Not every work unit needs a separate physical file for every artifact, but the information model must exist.

Every consequential artifact should be attributable where practical to:

- producer role/invocation;
- parent Project/Epic/Story/Ticket;
- **evaluated snapshot identity** (not merely a commit/worktree name);
- governing plan revision;
- relevant input evidence;
- creation/update time;
- supersedes/superseded-by relationships where applicable;
- review and verification linkage.

## 9.1 Work-unit record

Epic, Story, and Ticket records carry identity, objective, risk class, parent/dependency relationships, state, governing references, completion criteria, and current review/verification disposition.

## 9.2 Problem / Requirement Record

Contains objective, motivation, scope, constraints, acceptance criteria, unresolved questions, and external issue/SCM references when present.

## 9.3 Discovery Record

Contains code/components inspected, observed ownership, relevant relationships, tests/current behavior, governing documents, factual evidence, and hypotheses requiring confirmation.

## 9.4 Research Record

Contains relevant external/local documentation conclusions, version information, constraints, and uncertainties.

## 9.5 Decision Record

Captures consequential accepted decisions and rejected alternatives when the rationale matters beyond the immediate work unit.

## 9.6 Plan Revision

Contains the implementation contract and dependency graph. Accepted revisions are immutable. Material changes produce a new revision with reason, new evidence, changed work/dependencies, and effect on validation.

## 9.7 Implementation Report

Contains assigned Ticket(s) implemented, files/components changed, incremental checks executed, unexpected findings, deviations/remaining concerns, and diff/worktree/commit reference when available.

## 9.8 Review Report

Contains reviewed requirement/plan/revision, independence level, findings by severity, evidence/location, required versus optional changes, and final disposition.

## 9.9 Validation / Verification Record

Validation results must be more than `PASS`/`FAIL`. A consequential result should record:

```text
what      claim/check being validated
who       role/invocation/model/provider where relevant
when      timestamp
against   evaluated snapshot + plan/artifact revision
how       capability/provider/command/environment
result    pass / fail / inconclusive / blocked
evidence  log/state/trace/report references
```

An **evaluated snapshot** identifies the actual engineering inputs or built artifact that were evaluated, including relevant uncommitted changes. A commit ID or worktree name alone is insufficient when the evaluated state is dirty. The implementation may use content hashes, dirty-file manifests, synthesized tree IDs, build artifact digests, or another deterministic fingerprint. Where relevant, the snapshot should include the base repository revision, workspace identity, relevant uncommitted/generated/config inputs, and evaluated build artifact digest(s).

AEW control/evidence/report files are excluded from the engineering-input fingerprint unless they are themselves the subject of the check; otherwise writing the validation record would invalidate its own evidence. If any relevant engineering input changes after a passing result, that result remains historical evidence but no longer satisfies the current gate until revalidated against the new snapshot.

## 9.10 Handoff / Checkpoint Record

Contains active objective, current work graph state, accepted plan, completed work, in-flight/interrupted work, outstanding findings, blockers, next action, and evidence locations.

## 9.11 Completion Record

Summarizes the accepted result and links final work-unit state, plan, review, goal-backwards verification, contract checks, implementation revision, and any external SCM/issue identifiers.

# 10. Review design

Independent review is a core engineering gate, scaled to work-unit risk rather than treated as an end-of-phase summary.

## 10.1 Baseline review package

A context-independent reviewer receives the minimum context necessary to evaluate the result independently:

- work objective/requirement;
- governing contracts/ADRs/project guardrails;
- accepted plan/assignment;
- implementation revision/diff;
- relevant source context;
- tests/static/dynamic analysis output;
- explicit review scope.

The implementation reasoning transcript is excluded by default.

Review dimensions may include correctness, ownership, API/ABI/schema compatibility, error/cleanup paths, concurrency/state transitions, security, provenance/identity, test adequacy, unnecessary scope, maintainability, and performance risk.

Finding levels remain Blocker, Major, Minor, and Observation.

## 10.2 Independence levels and review modes

AEW declares review independence explicitly:

- **R0 — Self-review:** same implementation context; never independent.
- **R1 — Context-independent review:** fresh/bounded context; same model allowed. Baseline independent review.
- **R2 — Model-diverse review:** fresh review by a different model/lab or independent human.
- **R3 — Multi-party/specialist review:** multiple independent reviewers and/or specialists.

For this environment, self-hosted secondary-model token volume is not treated as a major design constraint. R2 is therefore a strong candidate for routine/high-volume evaluation if the alternate reviewer demonstrates acceptable quality and noise. A different-lab coding model such as Poolside Laguna may be evaluated, but AEW does not hard-code any specific reviewer model.

Multiple-review output preserves:

- `consensus_findings`;
- `reviewer_specific_findings`;
- `contradictions`;
- `unresolved_questions`.

Disagreement is evidence and must not be averaged away automatically.

## 10.3 Triggered specialist reviews

Specialist reviews are added when work crosses relevant boundaries:

```text
crosses ownership/bounded context -> architecture review
auth/authz/crypto/secrets/security boundary -> security review
schema/persistence/migration -> data/schema review
public ABI/protocol/compatibility surface -> compatibility review
```

Security-sensitive-code detection may help trigger review by identifying cryptographic primitives, hashing, TLS configuration, key/nonce/IV handling, credential/token handling, explicit zeroization such as `memset_s`, custom crypto, or attacker-controlled parsing paths. Detection is a trigger/evidence source, not proof of security.

# 11. Validation and verification design

AEW separates **incremental validation**, **implementation validation**, **goal-backwards acceptance verification**, and **contract-based verification**.

## 11.1 Incremental validation

After each meaningful atomic change, run the cheapest relevant invariant/check. Examples include compile of the affected target, a focused unit test, type/static check, parser fixture, sanitizer repro, or narrow browser/API check.

If a newly introduced or relevant required check fails, stop forward mutation and diagnose before continuing. Known baseline failures, flaky tests, unavailable services, or unrelated failures must be distinguished and recorded rather than treated as equivalent regressions.

## 11.2 Implementation validation

When an assigned Ticket is complete, run the targeted checks required by its project/profile policy. Test/build impact analysis should help determine affected build targets, relevant tests, and an efficient cheap-first validation order.

## 11.3 Goal-backwards acceptance verification

Goal-backwards verification starts from the claimed outcome:

> If this outcome is truly complete, what observable evidence and system state must exist?

The Verifier derives those conditions and walks backward through the system to demonstrate them. This is stronger than merely checking that the plan's tasks were executed.

Examples:

- authoritative persisted/runtime state contains the expected value;
- API/UI behavior exposes the expected result;
- successful paths cause the intended transition exactly once;
- failure paths do not produce forbidden side effects;
- required source/runtime relationships exist;
- the behavior can be reproduced on the relevant environment.

## 11.4 Contract-based verification

Contract-based verification establishes that the successful outcome does not violate governing contracts, architecture, ownership rules, dependency direction, schemas, security constraints, ABI/protocol obligations, or other project invariants.

AEW completion requires both goal-backwards evidence and contract conformance. Neither substitutes for the other.

## 11.5 Verification environments and provenance

Verification may inspect tests, persisted state, APIs, logs, graph relationships, vector stores, UI behavior, binaries, remote/test hosts, performance, or other domain evidence. Every consequential result must identify the target environment/revision and retain evidence references.

Remote validation is a capability, not an authority shortcut. A remote result must identify the target and artifact/build revision being tested.

# 12. Failure and debugging protocol

Failure is evidence, not a prompt to patch repeatedly.

The default loop is:

**Failure → Reproduce → Gather evidence → Form/refine hypothesis → Apply smallest justified change → Incremental check → Re-run targeted validation → Review/verify when appropriate**

Rules:

- stop forward mutation on a newly introduced/relevant failing invariant;
- compare failures against known baseline state when possible;
- repeated patches without improved evidence are prohibited;
- when verification fails, the Verifier reports the failure/evidence and the **Lead** classifies it before further mutation: local implementation defects may return to `RUNNING`; plan/design defects and contract violations transition to `REPLAN_REQUIRED`; environment/evidence failures remain blocked/inconclusive until resolved;
- if evidence contradicts the accepted design/plan, transition to `REPLAN_REQUIRED` rather than forcing implementation to fit the old plan;
- systematic debugging/TDD techniques may be supplied by skills, but they do not own workflow state;
- long-running debugging should checkpoint evidence and current hypotheses so a replacement subagent can resume without reconstructing the entire conversation.

Speculative evidence gathering is allowed. Speculative mutation must occur in an explicitly isolated disposable worktree/environment and cannot become authoritative without normal plan/review/verification gates.

# 13. Git, SCM, and change promotion

AEW distinguishes logical workflow readiness from repository/organizational enforcement.

A change becomes `COMMIT_READY` only after the project/profile's required engineering gates pass. Possible gates include:

- formatting/lint;
- type/static checking;
- compile/build;
- targeted/regression tests;
- project-defined coverage policy;
- triggered security/static analysis;
- schema/artifact checks;
- commit hygiene.

AEW does not define a universal coverage percentage or force expensive security scans on every tiny Ticket. Policies are project/profile/work-risk specific. Coverage is evidence, not proof of correctness.

Atomic commits are the preferred default: a new commit should represent one coherent logical change and satisfy the checks required by project policy for that commit, accounting explicitly for known baseline failures.

Layered enforcement may be implemented as:

```text
AEW incremental discipline
  -> COMMIT_READY policy gates
  -> pre-commit fast deterministic hooks
  -> pre-push / CI heavier checks
  -> PR / SCM / issue-management policy
```

`COMMIT_READY` is not proof that a commit/PR/ticket/CI/merge approval exists. External Bitbucket/Jira/SCM state is recorded through identifiers/status adapters and remains a separate authority boundary.

For concurrently executed mutating Tickets, individual workspaces are **integration candidates**, not automatically authoritative project state. The Lead controls/authorizes serialized integration into the target branch/worktree. Merge/conflict resolution and the integrated revision are new evidence-producing events; project policy determines which impacted local checks, review findings, and verification steps must be rerun before Story/Epic acceptance.

# 14. Context, memory, and authority

The workflow must survive interruption without making historical memory a source of truth.

Authoritative homes are:

| Context | Authoritative home |
|---|---|
| Durable system facts/contracts | Repository documentation and source |
| Accepted architectural decisions | ADR/design/decision records |
| Active work-unit state | Workflow artifacts |
| Accepted plan | Revisioned plan artifact |
| Actual implementation | Git/source revision |
| Acceptance evidence | Verification artifacts and authoritative system state |
| Historical recollection | Memory service, Git history, prior artifacts |

Memory is a retrieval aid. A remembered claim that conflicts with current source or accepted documents must be treated as stale until revalidated.

# 14.5 Knowledge contract boundary

AEW workflow state must be reconstructible from durable, human-readable project knowledge rather than conversation history. The companion **AEW Knowledge Contract** defines the required knowledge classes, authority levels, project/global storage boundary, context-assembly rules, artifact ownership, freshness semantics, work-unit records, and derived-cache behavior.

AEW core specifies **what knowledge must exist and what authority it carries**. The implementation agent may choose an appropriate physical directory/file layout so long as it conforms to that contract. In particular, the existence of a `CODEBASE.md`, `ROADMAP.md`, or similarly named file is not itself an AEW requirement; the corresponding information class and deterministic reconstruction behavior are.

The Knowledge Contract is therefore a companion design authority, not an optional documentation convention.

# 15. Interaction surface: commands, skills, and resumability

Workflow usability is architectural. AEW must expose simple commands that map to durable state transitions and can reconstruct context from artifacts rather than relying on hidden chat history.

## 15.1 Work creation commands

The primary work-unit commands are:

```text
/aew ticket <objective>
/aew story <objective>
/aew epic <objective>
```

The Lead may promote `Ticket → Story → Epic` when evidence shows the original scope was insufficient. Promotion preserves identity/provenance and records the reason. Silent demotion is conservative once accepted dependencies/artifacts exist.

Projects may optionally provide convenience aliases such as `/aew quick`, but aliases must resolve to the same underlying work-unit semantics rather than create a separate freestyle path.

## 15.2 Lifecycle commands

Expected user-facing operations include:

```text
/aew status [work-id]
/aew resume [work-id]
/aew understand [work-id]
/aew investigate [work-id]
/aew research [work-id]
/aew plan [work-id]
/aew execute [work-id] [--concurrency N]
/aew review [work-id]
/aew verify [work-id]
/aew debug [work-id]
/aew checkpoint [work-id]
/aew handoff [work-id]
/aew escalate [work-id]
/aew close [work-id]
```

`--concurrency N` is a ceiling on concurrently assigned READY work; it never overrides dependency constraints or review/verification gates.

## 15.3 Skills as reusable engineering capabilities

Skills encode language/domain technique (C/Python/frontend review, systematic debugging, validation practice, documentation lookup, etc.) and are loaded only when relevant. They are not workflow authorities.

## 15.4 Subagent launch ergonomics

The Lead should spawn bounded subagents from a generated launch contract rather than manually rebuilding prompts. A launch contract should provide:

- role;
- work-unit ID;
- objective;
- accepted plan/assignment slice;
- required knowledge topics;
- required capabilities/providers;
- project/profile guardrails;
- allowed mutations and prohibited actions;
- expected output schema;
- writeback destination;
- completion criteria.

Subagent results should be structured enough to retry, replace, cancel, or adjudicate an invocation without rereading its entire transcript.

## 15.5 Artifact-driven continuation

`/resume` reconstructs the Lead from durable artifacts and the current work graph. It should load the project manifest/control state, active work unit, accepted plan, latest checkpoint/handoff, unresolved review/verification findings, governing project rules, and relevant focused knowledge before proposing the next action.

## 15.6 State query/update interface

AEW needs a deterministic machine-queryable state interface. The first implementation should favor a local CLI/typed state engine such as:

```text
aew status
aew work show T-104
aew work ready
aew checkpoint
aew plan accept ...
```

An optional MCP adapter may expose the same engine later. CLI and MCP must never implement separate state authorities. The state engine must also enforce atomic control updates, expected-state revision checks, and current Lead authority so stale/superseded writers are rejected regardless of which adapter calls it.

## 15.7 Project initialization

`/aew init` should discover/map existing project authority, create the project Knowledge Contract state, establish guardrails/build-test policy references, and record missing knowledge rather than fabricating it.

# 16. Tooling and extension model

The engineering workflow is independent of physical packaging, but the deployed workbench is expected to know what tools are actually installed and to use them deliberately. AEW therefore separates **workflow capabilities** from **extension providers**.

Roles and skills request capabilities such as `exact_code_search`, `symbol_navigation`, `relationship_discovery`, or `remote_validation`. The workbench resolves those capabilities to installed providers. The lifecycle does not depend on the provider name.

The Workbench Capability Contract is **not load-bearing for the September cutover slice**. Initial adapters may bind known capabilities directly to known providers (for example `exact_code_search -> rg`) while the manifest/resolver layer is only staged or designed. This is a permitted implementation shortcut because it preserves capability semantics and can later be replaced by declarative resolution without changing role or lifecycle behavior.

AEW v0.7 intentionally defines only **two provider classes**:

1. **CLI provider** — an executable operation available to the host agent through a command surface.
2. **MCP provider** — a structured MCP server exposing one or more tools/resources.

This is deliberately simpler than modeling CLI, LSP, HTTP, SSH, local services, remote services, and containers as separate workflow extension types. Those distinctions still matter operationally, but they are provider implementation details rather than new AEW concepts.

Conceptually:

```text
Role / Skill
    |
    | requests capability
    v
Workbench Capability Contract
    |
    +-- CLI provider
    |      +-- native binary
    |      +-- script
    |      +-- language-server executable / adapter
    |      +-- container-backed command shim
    |
    +-- MCP provider
           +-- local MCP server
           +-- containerized MCP server
           +-- remote MCP server
```

The model should use the cheapest reliable provider that answers the question. Derived indexes and memories must not become authoritative alternatives to source or project state.

## 16.1 Workbench Capability Contract

AEW is **workflow-portable but environment-aware**. The lifecycle and role semantics must remain valid on a different harness or toolchain, but a deployed workbench should take deliberate advantage of the tools, MCP servers, services, local documentation, validation environments, and specialist utilities that are known to exist.

The integration boundary is a human-readable **Workbench Capability Contract**. Roles and skills request stable capabilities; the workbench resolves those capabilities to concrete CLI or MCP providers. This prevents the workflow from being hard-coded to a product while still allowing specialized behavior that a generic public workflow cannot safely assume.

For example:

- an Investigator requests `exact_code_search`; the workbench may resolve it to the `ripgrep` CLI provider;
- an Investigator requests `relationship_discovery`; the workbench may resolve it to the GitNexus MCP provider;
- a Verifier requests `remote_validation`; one installation may resolve it to an `ssh-test-vm` CLI provider while another may resolve it to a structured test-environment MCP provider.

Changing the provider must not require rewriting Investigator or Verifier semantics.

## 16.2 Human-readable manifests

The capability contract should be stored in version-controlled, human-readable configuration such as YAML or TOML and validated by a machine-readable schema. The configuration should remain understandable without reading orchestration code.

A reasonable initial layout is:

```text
workbench/
  capabilities.yaml
  providers/
    cli.yaml
    mcp.yaml
  grants/
    roles.yaml
    profiles.yaml
  policies/
    evidence.yaml
    permissions.yaml
    validation.yaml
  profiles/
    base.yaml
    c.yaml
    python.yaml
    frontend.yaml
    re.yaml
    revelations.yaml
```

The exact physical layout is an implementation decision. The important distinction is:

- **capabilities** describe what engineering function is required;
- **providers** describe how the installed workbench supplies that function;
- **grants/profiles** describe which roles may use it and under what constraints;
- **policies** describe evidence, authority, mutation, and validation expectations.

An engineer should be able to add, disable, inspect, or replace a provider by editing a small declarative record and supplying any required package, image, or configuration.

## 16.3 CLI providers

A CLI provider represents an executable command surface. AEW does not care whether the command is implemented as a native Rocky-compatible binary, shell/Python script, language-server adapter, or container-backed shim as long as the provider contract is stable and testable.

CLI providers should be able to declare at least:

- provider ID and human-readable description;
- command or wrapper path;
- version/source/package information;
- capabilities supplied;
- supported roles/profiles;
- read-only versus mutating behavior;
- health/version check;
- evidence/authority class;
- required environment/runtime configuration;
- offline package/payload requirements;
- permission constraints;
- timeout/resource expectations where relevant.

Illustrative provider records:

```yaml
providers:
  ripgrep:
    type: cli
    command: rg
    capabilities:
      - exact_code_search
      - text_search
    evidence: source_text
    health_check: "rg --version"

  ast-grep:
    type: cli
    command: sg
    capabilities:
      - structural_code_search
    evidence: parsed_source
    health_check: "sg --version"

  clangd:
    type: cli
    command: clangd
    protocol: lsp
    capabilities:
      - symbol_navigation
      - semantic_references
    profiles: [c]
    evidence: compiler_semantic
    prerequisites:
      - compile_commands

  remote-rocky-test:
    type: cli
    command: aew-test-vm
    implementation: ssh-wrapper
    capabilities:
      - remote_execution
      - remote_validation
      - retrieve_remote_logs
    roles: [verifier]
    mutating: controlled
    evidence: target_runtime
```

`protocol: lsp`, `implementation: ssh-wrapper`, or `implementation: container-shim` describe how the CLI provider works. They do not create new extension classes.

A tool that cannot run natively on Rocky 8 may still appear to AEW as an ordinary CLI provider if a host command transparently invokes a pinned container image. The workflow should not need to care that the implementation crosses a container boundary.

## 16.4 MCP providers

An MCP provider represents a structured MCP server. It is appropriate when persistent state, structured semantic operations, resources, specialized service interaction, or a richer tool contract provides clear value over raw command execution.

MCP providers should be able to declare at least:

- provider/server ID and description;
- server/version/source information;
- launch or connection reference;
- capabilities supplied;
- exposed tools/resources relevant to AEW;
- supported roles/profiles;
- read-only versus mutating behavior;
- health/connectivity check;
- evidence/authority class;
- persistence/freshness semantics;
- required image/package/configuration;
- permission and credential requirements;
- timeout/resource constraints where relevant.

Illustrative records:

```yaml
providers:
  gitnexus:
    type: mcp
    server: gitnexus
    capabilities:
      - relationship_discovery
      - impact_analysis
      - symbol_context
    evidence: derived_index
    authoritative: false
    freshness: repository_revision_bound

  ghidra:
    type: mcp
    server: ghidra
    capabilities:
      - binary_analysis
      - binary_references
      - decompilation_context
    evidence: reverse_engineering_observation

  test-environment:
    type: mcp
    server: test-environment
    capabilities:
      - remote_execution
      - deploy_test_build
      - remote_validation
      - retrieve_remote_logs
    roles: [verifier]
    mutating: controlled
    evidence: target_runtime
```

An MCP server may be local, containerized, or remote. That deployment choice belongs to the workbench packaging/runtime configuration rather than to AEW lifecycle semantics.

## 16.5 Capability definitions and resolution

Capabilities are stable names for useful engineering functions. They should be narrower than roles and broader than a particular product invocation.

Illustrative configuration:

```yaml
capabilities:
  exact_code_search:
    description: Locate exact identifiers, strings, and configuration references.
    preferred: ripgrep

  structural_code_search:
    description: Locate syntax-aware source patterns.
    preferred: ast-grep

  symbol_navigation:
    description: Resolve definitions and references using project semantics.
    preferred: clangd
    fallback: source-search

  relationship_discovery:
    description: Discover broader code relationships and impact hypotheses.
    preferred: gitnexus

  binary_analysis:
    description: Inspect binary functions, references, and decompilation evidence.
    preferred: ghidra

  remote_validation:
    description: Execute validation in an approved target/test environment.
    preferred: test-environment
    fallback: remote-rocky-test
```

Capability resolution should consider provider health, profile compatibility, permissions, work-unit policy, and freshness. A preferred provider is not used merely because it exists.

## 16.6 Role capability grants

Roles receive the capabilities needed for their job rather than the entire workbench inventory. Profiles can narrow or extend those capabilities by language, project, or environment.

Examples:

- an Investigator may receive exact search, structural search, symbol navigation, relationship discovery, Git history, documentation, and binary analysis when relevant;
- an Implementer may additionally receive source mutation, build, test, static-analysis, debugger, and formatter capabilities;
- a Reviewer should normally receive read-only inspection plus review/static-analysis capabilities;
- a Verifier may receive project-state inspection, browser validation, database/vector queries, or remote-validation capabilities according to the acceptance criteria.

The persistent Lead may know the full capability catalog so it can dispatch intelligently, but subordinate contexts should receive only the relevant resolved providers and usage guidance. This reduces context/tool noise and limits accidental authority.

Illustrative grant model:

```yaml
roles:
  investigator:
    capabilities:
      - exact_code_search
      - structural_code_search
      - symbol_navigation
      - relationship_discovery

  implementer:
    capabilities:
      - exact_code_search
      - symbol_navigation
      - build
      - targeted_test
      - source_mutation

  verifier:
    capabilities:
      - execute_tests
      - inspect_authoritative_state
      - remote_validation
```

## 16.7 Tool-selection policy

Tool choice should be policy-guided rather than improvised from whichever provider sounds most sophisticated. A default investigation hierarchy is:

1. exact source/config search when the question is textual;
2. structural search when syntax shape matters;
3. language-server/compiler semantics when symbol identity matters;
4. derived relationship/index tools for broader impact hypotheses;
5. source inspection to confirm consequential derived relationships;
6. runtime tests, traces, logs, state inspection, or target execution when actual behavior matters.

The workbench may encode project-specific policies beyond this baseline. For example, REVELATIONS verification can prefer authoritative relational state over inferred graph/index results when establishing identity or completion.

## 16.8 Evidence and authority metadata

Every provider should declare the kind of evidence it returns so roles know what conclusions are justified. The exact taxonomy may evolve, but the initial ordering should distinguish at least:

- authoritative source/contracts/project state;
- target/runtime observations and persisted authoritative state;
- compiler/language-server semantics;
- deterministic test/debug/analysis results;
- parsed/structural source results;
- derived indexes/relationship graphs;
- reverse-engineering observations;
- memory/historical observations.

This is not a universal numeric confidence score. It is an authority/freshness hint that prevents a convenient provider from silently becoming project truth.

## 16.9 Extension lifecycle

Adding an extension should be additive whenever possible. The normal path is:

```text
install / deploy provider
        ↓
register provider manifest
        ↓
run doctor / provider acceptance check
        ↓
capability becomes AVAILABLE
        ↓
grant capability to role/profile where appropriate
        ↓
add skill guidance and evaluation fixture if needed
        ↓
promote to preferred/default only after evidence shows value
```

A new provider should not require changing AEW lifecycle code merely because it supplies a new implementation of an existing capability.

Examples:

### Add ripgrep

1. install/package the Rocky-compatible binary;
2. register the `ripgrep` CLI provider;
3. validate `rg --version` and a fixture query;
4. map it to `exact_code_search`;
5. grant that capability to relevant roles/profiles.

### Add a testing VM

A new testing VM can initially be exposed as a CLI provider through a controlled SSH wrapper:

```text
Verifier
   ↓ remote_validation
remote-rocky-test CLI provider
   ↓
controlled SSH execution
   ↓
target VM evidence
```

If a richer structured service is later useful, the same `remote_validation` capability can be remapped to a test-environment MCP provider without changing the Verifier role.

This is a central extensibility requirement: **providers are replaceable; capabilities and role semantics are stable.**

## 16.10 Provider health and capability state

Provider absence must be visible rather than silently ignored. Providers should expose a health state such as:

- `unavailable` — provider is not installed/configured or cannot be reached;
- `installed` — provider artifacts exist but functional validation has not passed;
- `healthy` — provider passed its required health/compatibility check;
- `degraded` — provider is usable with explicit limitations;
- `disabled` — provider intentionally excluded by policy/operator choice.

Capability resolution can then expose:

- `available` — an approved healthy provider satisfies the capability;
- `fallback` — preferred provider unavailable, approved fallback selected;
- `degraded` — only a degraded provider is available and limitations are surfaced to the Lead;
- `blocked` — no provider can satisfy a required capability under current policy.

`doctor` should validate provider installation, versions, role grants, offline artifacts, permissions, connectivity where applicable, and capability resolution. A role must not claim to have performed an unavailable validation.

A useful human-facing status surface should be able to produce something equivalent to:

```text
Capability                  State      Provider
exact_code_search           AVAILABLE  ripgrep
structural_code_search      AVAILABLE  ast-grep
symbol_navigation           AVAILABLE  clangd
relationship_discovery      DEGRADED   gitnexus (index stale)
remote_validation           AVAILABLE  remote-rocky-test
browser_validation          BLOCKED    no healthy provider
```

## 16.11 Security and authority boundaries

Capability extensibility must not turn tool discovery into unrestricted authority.

- Provider definitions expose only actions needed for the granted role/capability.
- Remote or mutating providers require explicit permission policy.
- Secrets remain runtime configuration, not workbench manifests.
- CLI wrappers must not hide privilege escalation or broad filesystem/network access.
- MCP providers must declare mutating operations and persistence boundaries.
- Remote validation must record target identity, revision, action/command, and returned evidence.
- A provider is not authoritative merely because it is remote or sophisticated; authority follows project policy and evidence type.

## 16.12 Adapter rule

OpenCode custom tools, harness-specific wrappers, or typed helper interfaces may improve model ergonomics, but they do **not** create additional AEW provider classes. They are adapters over a CLI or MCP provider.

For example, a typed `validate_finding(finding_id)` OpenCode tool may call a host CLI, which may itself invoke a container. AEW still records the underlying provider as CLI. Likewise, a harness-specific wrapper around GitNexus remains an adapter over an MCP provider.

Keeping the provider model this small is intentional: the extension system should be easy enough that an engineer can understand and extend it from the manifests without first learning orchestration internals.

## 16.13 Code-intelligence and impact-analysis capabilities

AEW should provide a layered code-intelligence path rather than relying on one universal index:

```text
exact/text search
  -> structural search
  -> symbol/LSP/compiler semantics
  -> relationship/call-graph/impact discovery
  -> source confirmation of consequential edges
  -> runtime evidence when behavior matters
```

Useful capabilities include `repository_exploration`, `exact_code_search`, `structural_code_search`, `symbol_navigation`, `relationship_discovery`, `call_graph_query`, `call_graph_export`, and `interprocedural_impact_analysis`.

The existing lightweight Python repository explorer should be formalized as a complementary/fallback `repository_exploration` provider. It is not a separate "GitNexus Lite" product and must not pretend to supply richer graph semantics it does not have.

GitNexus remains a richer derived relationship/impact provider. Ghidra or other binary tools may satisfy call-graph/function-analysis capabilities for binaries. NetworkX or similar libraries are implementation choices for graph processing/export, not AEW semantics.

## 16.14 Build/test intelligence

AEW should support capabilities such as:

- `build_discovery`;
- `build_target_analysis`;
- `build_execution`;
- `test_discovery`;
- `test_impact_analysis`;
- `targeted_test_execution`;
- `baseline_failure_comparison`.

The aim is to determine what actually needs to build/test, run cheap/high-signal checks first, understand failures, and widen validation scope when risk/evidence warrants it.

## 16.15 Project guardrails

Project profiles/knowledge may declare machine-readable guardrails including ownership/directory boundaries, dependency directions, layering, generated-file policy, authoritative contract/schema locations, naming conventions, public/private interfaces, build/test expectations, and review triggers.

Guardrails should be available to Planner/Implementer/Reviewer and rechecked during contract-based verification. Deterministic enforcement is preferred where practical.

## 16.16 Security/RE profile capabilities

Security/native/RE profiles may additionally expose capabilities such as:

- `security_sensitive_code_detection`;
- `remote_artifact_acquisition` — retrieve an attributable artifact from an approved remote/test target;
- `binary_artifact_staging` — normalize/hash/stage a binary for local analysis while preserving source identity/provenance;
- `binary_analysis` — analyze a staged/local binary through Ghidra or another registered provider;
- `binary_diff`;
- `symbol_cache`/symbol lookup;
- `call_graph_export`;
- `interprocedural_impact_analysis`;
- `function_analysis` once its exact semantics/provider are defined.

The SPT Ghidra remediation maps to `remote_artifact_acquisition` + `binary_artifact_staging` + `binary_analysis`; it does **not** depend on the unresolved definition of `function_analysis`.

Caches are derived, revision/tool-version keyed, stale-detectable, rebuildable, and never authoritative.

## 16.17 Project-specific structured capabilities

Projects may register structured capabilities without making them AEW-core semantics. REVELATIONS, for example, should evaluate a first-class metadata-query capability that returns canonical entity/relationship/evidence metadata without forcing the model to synthesize raw SQL for routine inspection. The provider must remain an access/query layer over canonical state rather than a second store or authority.

# 17. Model and harness independence

The lifecycle must not depend on a particular model name, harness, or concrete tool provider. Workbench capabilities form the tool-equivalent portability boundary.

Initial intended implementation:

- OpenCode as primary runtime;
- GPT-5.4 as general engineering model;
- stronger approved frontier model for explicit escalations;
- GSD as an initial adapter/source for portions of project-control behavior;
- selected Superpowers techniques as possible implementations of low-level engineering disciplines;
- existing specialist skills for language/domain practice.

This mapping is implementation detail, not architecture.

A future model or runtime change should require:

1. a new adapter/configuration;
2. capability validation;
3. evaluation runs;
4. no rewrite of lifecycle, roles, states, or authority rules.

# 18. Initial model and review routing policy

Initial role routing is policy rather than architecture:

- Lead / Investigator / Researcher / Planner: GPT-5.4 high reasoning by default;
- routine Implementer: GPT-5.4 medium/high according to complexity;
- Reviewer: GPT-5.4 fresh-context R1 baseline;
- Verifier: GPT-5.4 high reasoning with acceptance-focused context;
- pathological diagnosis: GPT-5.4 higher reasoning or explicit frontier escalation;
- Frontier Advisor: strongest approved model only when normal workflow cannot resolve the design/root cause.

AEW should support a second-lab/self-hosted reviewer for R2 without making one model permanent. In this environment, marginal token volume for self-hosted review is not a meaningful constraint; promotion should be based on unique defect yield, false positives/noise, latency/availability, and Lead adjudication burden.

Review level/model choice should be recorded in consequential review artifacts.

# 19. GSD and Superpowers relationship

GSD and Superpowers are reference implementations and reusable components, not governing methodologies.

## 19.1 What we intentionally retain from GSD

The project values GSD's high-level project-management behavior because it directly mitigates a major LLM weakness: losing the purpose and structure of a large codebase.

The useful pattern is:

**Understand → Research → Plan → Execute → Validate → Replan/Complete**

Useful GSD implementation concepts may include codebase mapping, discussion artifacts, phase planning, state persistence, and resumability.

## 19.2 What is insufficient by itself

High-level project management does not define enough about how individual code changes should be engineered.

A statement that a planned work item was implemented and its tests pass does not establish:

- disciplined reproduction of a defect;
- appropriate test construction;
- incremental implementation quality;
- error-path handling;
- independent review;
- review/fix cycles;
- system-level verification;
- commit readiness.

This design therefore adds the Engineering Execution Plane as a first-class concern.

## 19.3 What we may reuse from Superpowers

Superpowers contains useful techniques in areas such as systematic debugging, test-driven work, review, and verification-before-completion.

Individual techniques may be adopted when they satisfy this design and improve measured outcomes.

We do not inherit its lifecycle, state model, or ordering simply because it provides those techniques.

## 19.4 Adapter direction

The architectural direction is:

```text
OUR WORKFLOW SPECIFICATION
        |
        +-- GSD adapter / reusable project-control pieces
        +-- Superpowers adapter / selected execution disciplines
        +-- existing specialist skills
        +-- OpenCode runtime adapter
        +-- future runtime/model adapters
```

not:

```text
GSD/Superpowers
        |
     our customizations
```

This inversion preserves ownership of the engineering process.

# 20. Evaluation strategy

The workflow must be evaluated against actual engineering outcomes, not whether agents follow prompts verbosely.

Core metrics include:

- correctness of final behavior;
- architectural/contract violations;
- defects caught before human intervention;
- defects missed by review;
- false-positive review findings;
- unnecessary edits;
- number of speculative fix loops;
- time to useful evidence;
- operator interventions;
- recovery after interruption;
- stale-context mistakes;
- wall time and API usage where measurable;
- ability to reject a plausible but architecturally wrong plan.

Representative scenarios should include:

- routine bounded implementation;
- C defect diagnosis;
- Python service/state change;
- cross-layer brownfield change;
- frontend behavior defect;
- failed validation requiring diagnosis/replan;
- fresh-session resume;
- bad-plan detection;
- frontier escalation and return.

## 20.1 Promotion rule for optional techniques and tools

A model, tool, role variant, or engineering technique moves from experiment to default AEW policy only when a recorded evaluation shows a meaningful improvement in the outcome it is intended to improve. The evaluation should consider at least:

- defects uniquely caught;
- false-positive/noise rate;
- implementation/review quality;
- time to relevant evidence;
- operator intervention;
- latency and API/runtime cost where measurable;
- maintenance/offline-packaging burden.

A single successful demo is a smoke test, not promotion evidence.

# 21. Implementation strategy and cutover scope

The authoritative design may be ahead of automation. Capabilities are tracked as **implemented**, **staged**, or **designed**.

## 21.1 September cutover slice

The cutover must provide a safe usable core, not every advanced orchestration feature.

Required/high priority:

- OpenCode + approved provider/model path proven;
- persistent/reconstructible Lead with crash-safe, stale-writer-resistant control updates;
- project Knowledge Contract initialization/resume;
- Ticket/Story/Epic identifiers and durable work records (a minimal implementation may start with Ticket + Story while preserving Epic schema);
- accepted-plan revision/reference;
- independent review path;
- incremental checks + targeted verification bound to an evaluated snapshot that includes relevant uncommitted inputs;
- explicit Lead-owned verification-failure classification;
- deterministic `/status`/`/resume`/state query surface;
- existing specialist skills and core CLI/MCP providers;
- toolchain packaging/doctor foundations.

May remain staged/designed without blocking cutover:

- fully generic dynamic scheduler implementation if current GSD-style dispatch can temporarily implement the same dependency semantics;
- declarative capability resolver beyond hard-bound initial providers;
- model-diverse review default policy;
- automatic security-trigger detection;
- sophisticated build/test impact analysis;
- full SCM/Jira enforcement;
- work-graph analytics/critical-path UI;
- advanced caches/indexes.

**Concurrency safety is not optional:** until isolated mutation workspaces and controlled integration are implemented, mutating concurrency is restricted to `1`. Existing parallel dispatch may still be used for read-only work or for mutating work only where equivalent isolation already exists.

## 21.2 Implementation sequence

1. Freeze AEW v0.7 + Knowledge Contract v0.4 + compatible specification manifest and pin the repository revision.
2. Have an implementation agent produce an ambiguity report and build plan from only those documents plus the workbench/toolchain spec.
3. Bootstrap repository schemas/state engine/role templates/commands with atomic/version-aware control transitions and stale-Lead rejection.
4. Prove one complete **serial Ticket vertical slice**: initialize → accept plan → implement → independently review → verify against an evaluated snapshot → integrate → run required post-integration checks → close → destroy session → reconstruct from durable state.
5. Include three adversarial foundation cases in that slice: (a) an upstream mutating Ticket passes locally but is not integrated, so its dependent remains BLOCKED; (b) relevant uncommitted source changes after validation, so old evidence becomes stale without being deleted; (c) a crash or superseded Lead attempts a control update, which must recover/reject without corrupting accepted state.
6. Implement minimum Story path with checkpoint/resume, Lead-owned failure classification, and dependency resolution based on accepted integrated outputs.
7. Implement isolated mutation workspace/integration semantics before enabling mutating concurrency >1.
8. Add dependency-aware dynamic scheduling once the state engine/isolation layer is stable.
9. Add capability/guardrail/build-test intelligence incrementally.
10. Import remaining bootstrap toolchain remediation into the AEW Work Graph once the minimum slice is operational.
11. Evaluate model-diverse review and optional advanced providers empirically.

## 21.3 Design-artifact acceptance test

A clean implementation agent unfamiliar with this conversation must be able to identify authority boundaries, work hierarchy, dependency-satisfaction/integration semantics, state transitions, crash-safe control-update rules, evaluated-snapshot/evidence semantics, knowledge responsibilities, provider semantics, review/verification requirements, concurrency isolation, failure-classification authority, and cutover scope without inventing missing architecture. Questions that reflect legitimate implementation choices are acceptable; questions exposing architectural ambiguity are design defects to fix before freeze.

# 22. Open design questions for post-v0.7 evaluation

The following are intentionally not frozen as assumptions:

1. At what risk/work-unit levels should R2 model-diverse review become the default after evaluation?
2. Which alternate reviewer best complements GPT-5.4 in real defect yield and false-positive rate?
3. Should Epics be optionally grouped into organization-specific releases/milestones/phases, and how should those external groupings map without becoming a second AEW scheduler?
4. What exact Ticket schema fields are necessary for robust dynamic scheduling without making simple work bureaucratic?
5. How aggressive should automatic checkpointing be during very long mutating work?
6. Which build/test impact-analysis provider(s) are worth maintaining for each language/project profile?
7. What exact capability is intended by the remaining ambiguous `function_analysis` request?
8. What external SCM/Jira enforcement points should be wired first?
9. Which guardrails deserve deterministic enforcement versus prompt/policy guidance?
10. When does a derived SQLite/full-text/vector index become worthwhile versus plain artifact resolution?

# 23. Design invariants

1. **There is one coordination authority.** The Lead owns accepted-plan state, scheduling, failure classification, escalation, integration decisions, and completion.
2. **Control-state writes are atomic and reject stale authority.** A crash or superseded Lead cannot publish partial or stale accepted state; workspace copies never become control authorities.
3. **Verification evidence and remediation authority are separate.** The Verifier establishes pass/fail/inconclusive evidence; the Lead classifies a verification failure and chooses the workflow transition.
4. **Mutating dependencies require accepted integrated outputs.** `COMMIT_READY` is an integration candidate; a downstream mutating dependency is satisfied only when the accepted output is in its recorded source snapshot and required integration checks have passed.
5. **Concurrent mutation is isolated.** No two mutating Tickets share an authoritative mutation workspace; if isolation is unavailable, mutating concurrency is one.
6. **Integrated state is revalidated.** Isolated Ticket success never silently validates the post-integration revision.
7. **Evidence binds to the evaluated snapshot.** Relevant uncommitted engineering inputs are part of evidence identity; subsequent relevant mutation makes prior passing evidence stale for the current gate without erasing history.
8. **Risk and work size are separate.** Ticket/Story/Epic type does not determine risk class.
9. **Ancestor policy propagates without automatic numeric inflation.** Child work keeps local risk classification while inheriting non-waivable parent gates/guardrails and any explicit minimum-class floor.
10. **Incremental checks stop bad forward mutation.** Relevant regressions are diagnosed near their source.
11. **Review and verification are distinct.** Passing tests never substitutes for independent code review where required.
12. **Goal-backwards and contract checks are both required for completion.** Outcome evidence without conformance, or conformance without outcome, is insufficient.
13. **Disagreement is preserved.** Multiple reviewers do not get automatically averaged into false consensus.
11. **Validation is attributable.** What/who/when/against/how/evidence are retained for consequential checks.
12. **Project truth stays with its owner.** Derived indexes, memory, code graphs, and caches never silently become authority.
13. **The work graph is the to-do authority.** Human status views project canonical state rather than a parallel checklist.
14. **Subagents are bounded.** Role, context, capabilities, mutation rights, workspace identity, output schema, and writeback destination are explicit.
15. **Capabilities are replaceable.** CLI/MCP providers can change without redefining workflow semantics.
16. **Guardrails are project knowledge/policy.** Structure/ownership/security/build-test rules are discoverable and enforced where practical.
17. **Checkpoints are durable, not opaque.** Recovery depends on artifacts/state rather than hidden model internals.
18. **Automation may lag design without lying about it.** Implemented/Staged/Designed status remains explicit.
19. **Small work stays small.** Ticket paths do not require fake Epics or milestones.
20. **Large work decomposes explicitly.** Stories/Epics expose dependency graphs rather than hiding them in prose.
21. **No transport becomes an authority.** CLI/MCP/adapters call the same underlying state/policy semantics.
22. **Specification compatibility is explicit.** Workflow, Knowledge Contract, and implementation appendices are versioned as a compatible set rather than assumed to match by filename proximity.

# 24. Definition of success

This specification is successful as a **design artifact** when Codex or another implementation agent can build AEW without needing to infer missing authority boundaries, lifecycle semantics, review independence, state rules, or packaging expectations from GSD/Superpowers behavior.

Before the design is considered frozen, perform a **clean implementation-readiness review**: give the specification and its companion contracts to an implementation agent that has no access to the design conversation, ask it to produce an implementation plan and enumerate blocking ambiguities, and treat any question that reflects a missing authority/lifecycle/knowledge semantic as a design defect. Questions that are merely reasonable physical-layout or library choices remain implementation choices.

The implemented project ultimately succeeds when an engineer can hand the system a meaningful brownfield engineering problem and the workflow reliably:

1. establishes what is actually being requested;
2. discovers how the relevant system currently works;
3. produces a reasoned and reviewable design/plan;
4. implements that plan using disciplined low-level engineering practices;
5. independently reviews the code against requirements and contracts;
6. independently verifies the requested behavior using real evidence;
7. diagnoses and replans when evidence contradicts assumptions;
8. preserves enough durable state for the persistent Lead to resume accurately or for a new Lead to be reconstructed after session loss;
9. exposes simple commands/skills for status, resume, Ticket/Story/Epic start, review, verification, checkpoint, and handoff so the process remains usable in daily work;
10. lets a small Ticket remain a small durable work unit while promoting it to Story/Epic when evidence reveals broader scope;
11. reconstructs project and work-unit context through the AEW Knowledge Contract rather than hidden chat history or guessed file locations;
12. produces a commit-ready result without losing project ownership, provenance, or architectural intent;
13. resolves role needs through a human-readable capability contract so known local/MCP/remote tools improve the workflow without becoming hard-coded lifecycle dependencies;
14. continues to work when the underlying model, agent harness, or concrete tool provider changes.

The goal is not to imitate a human development organization for appearance's sake. The goal is to introduce the separations of responsibility, evidence, review, and authority that compensate for known weaknesses of long-running LLM software development while preserving the speed and flexibility that make agentic coding useful.

# Appendix A — Immediate mapping to the planned workbench

The initial implementation is expected to map approximately as follows:

| Design concept | Initial implementation candidate |
|---|---|
| Engineering Lead / work state | Persistent OpenCode Lead context + AEW state/work-graph artifacts; GSD-derived project-control pieces may implement parts |
| Investigator | OpenCode read-only/fresh role + search/LSP/index tools |
| Researcher | OpenCode role + local documentation/research tooling |
| Planner | GSD-derived planning artifacts + project design template |
| Implementer | OpenCode writer + existing language developer skills |
| Reviewer | R1 fresh/bounded OpenCode role + C/Python/frontend reviewers; R2/R3 optional later |
| Verifier | Fresh role + project validation tools/state queries |
| Debugging protocol | Owned project protocol, potentially using Superpowers techniques |
| TDD/regression discipline | Owned project protocol, potentially using Superpowers techniques |
| Memory | Claude-Mem if retained, otherwise explicit continuity adapter |
| Tool discovery | Skills/instructions + Workbench Capability Contract / tool registry |
| Capability resolution | Human-readable capability manifests + role/profile grants + provider health checks |
| Remote validation | Optional registered provider (for example SSH/MCP-backed test VM) granted to Verifier when project policy allows |
| Workflow UX / resume | AEW-owned commands/skills that reconstruct the Lead from durable artifacts |
| Knowledge system | AEW Knowledge Contract + per-project manifest/artifacts; physical layout selected by implementation |
| Work hierarchy | AEW `/aew ticket`, `/aew story`, `/aew epic` + durable records/DAGs + promotion behavior |
| Runtime | OpenCode primary; Codex reference/fallback/build-time adapter |
| General model | GPT-5.4 initially |
| Frontier escalation | Approved frontier model when available |
| SCM/work management | Future Bitbucket/Jira/CI adapter; existing review hooks are candidate enforcement points |

# Appendix B — Source design inputs

This specification synthesizes decisions and research from:

- the Claude Code → GPT-5.4 workflow migration matrix and gated migration plan;
- the GPT-5.4 coding workbench target design and evaluation plan;
- the existing GSD workflow experience on REVELATIONS;
- the proposed hybrid Rocky 8 host/container toolchain design;
- the Workbench Capability Contract concept for environment-aware, provider-independent tool integration;
- existing C, Python, frontend, review, and project-specific skills;
- GSD and Superpowers as non-authoritative reference implementations;
- external reviews of AEW v0.1 and v0.3 plus the subsequent multi-model feedback synthesis incorporated into v0.5;
- the fresh-eyes implementation-readiness review of AEW v0.5 / Knowledge Contract v0.2 that drove the v0.6 authority, risk-inheritance, concurrency-isolation, and capability-mapping fixes.

# Appendix C — Implementation-status record

The agent-toolchain repository should maintain a simple status table for major AEW capabilities so design intent is not confused with current availability.

| Capability | State | Acceptance evidence / next action |
|---|---|---|
| AEW v0.7 design | Implemented when versioned/accepted | Repository document + review disposition |
| Persistent Lead + reconstruction | Implemented / Staged / Designed | Resume from artifacts after fresh session / lost context |
| Command/skill interaction layer | Implemented / Staged / Designed | ticket/story/epic/status/resume/review/verify commands on a real project |
| AEW Knowledge Contract | Implemented / Staged / Designed | Project manifest + work-unit artifacts + fresh-session Lead reconstruction |
| Ticket/Story/Epic work model | Implemented / Staged / Designed | Small Ticket stays bounded; Story DAG schedules correctly; promotion preserves provenance |
| Project-control adapter | Implemented / Staged / Designed | End-to-end Epic/Story/Ticket + handoff evidence |
| R1 Reviewer | Implemented / Staged / Designed | Fresh-context review of a real Class 1+ change |
| Independent Verifier | Implemented / Staged / Designed | Verification report tied to actual revision/environment |
| OpenCode provider path | Implemented / Staged / Designed | Real GPT-5.4 tool-call continuation through organizational gateway |
| Specialist skills | Implemented / Staged / Designed | Discovery + representative invocation |
| Host/container tools | Implemented / Staged / Designed | `doctor` + offline availability checks |
| Workbench Capability Contract | Implemented / Staged / Designed | Human-readable manifests resolve role capability to provider; add/replace provider without lifecycle change |
| Remote validation provider | Implemented / Staged / Designed | Registered test environment, health check, controlled permissions, revision-bound evidence |
| Work graph / dynamic scheduler | Implemented / Staged / Designed | Dependency transitions READY/BLOCKED and bounded concurrency on a real Story |
| Concurrent mutation isolation | Implemented / Staged / Designed | Two mutating READY Tickets use distinct attributable workspaces; integration serialized; integrated revision revalidated |
| Verification-failure classification | Implemented / Staged / Designed | Verifier reports failure; Lead records classification and correct transition |
| Validation provenance | Implemented / Staged / Designed | Revision-bound validation provenance record |
| Project guardrails | Implemented / Staged / Designed | Planner/Implementer/Reviewer load and enforce project policy |
| Build/test impact analysis | Implemented / Staged / Designed | Relevant targets/tests selected and baseline failures distinguished |
| SCM/Jira enforcement | Implemented / Staged / Designed | External IDs/statuses and gate behavior |
| Model-diverse review | Implemented / Staged / Designed | Different-lab pilot results; promote only on unique defect yield/noise evidence |

The status record is operational metadata. It does not replace the workflow state of any project using AEW.
