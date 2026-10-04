# AEW Lead / Operator Interaction Design v0.1

**Status:** Proposed design  
**Scope:** Human–Lead interaction, requirements elicitation, planning, project reconnaissance, stakeholder intervention, progress reporting, delegation/resource governance, and coordination-facing UX  
**Implementation status:** Future work; this document does not expand M3 scope
**Review integration:** 2026-09-28 companion-design review incorporated. Canonical cross-document failure classes and invariants are indexed in `failure-class-registry.md` and `invariant-index.md`.

## 1. Purpose

AEW should allow a human stakeholder to direct engineering work without forcing that stakeholder either to micromanage individual agents or surrender meaningful control over the result.

The normal interaction model is:

```text
stakeholder
    ↓
   Lead
    ↓
AEW engineering system
    ↓
workers / reviewers / verifiers / researchers
```

The stakeholder primarily interacts with the Lead.

The Lead is responsible for:

- understanding the objective;
- investigating the project before asking unnecessary questions;
- identifying consequential ambiguity;
- eliciting stakeholder requirements when needed;
- proposing an execution plan;
- obtaining approval for meaningful work;
- managing execution inside the approved envelope;
- governing global work shape and resource use;
- coordinating workers;
- propagating new information;
- surfacing meaningful progress and problems;
- escalating decisions that belong to the stakeholder;
- remaining fully traceable to underlying AEW state and evidence.

AEW should feel like directing a capable engineering Lead, not administering a collection of agents.

## 2. Core UX principle

AEW must not make the stakeholder choose between:

```text
"Trust me, I'm working."
```

and:

```text
"Here are 187 internal agent events."
```

The intended experience is:

```text
Here is what matters.
Here is what changed.
Here is why.
Here is what I need from you.
Everything else is proceeding inside the plan you approved.
```

Detailed project state, invocation history, evidence, decisions, provenance, and resource allocation remain available on demand.

The default experience uses progressive disclosure rather than hiding rigor.

## 3. The stakeholder relationship

For the current intended AEW usage model, the human operator is the primary stakeholder whose requirements and preferences drive the engineering objective.

The Lead must distinguish between stakeholder-owned information and engineering-derivable information.

### Stakeholder-owned information

Examples:

- desired externally visible behavior;
- compatibility expectations;
- product tradeoffs;
- acceptable scope;
- priorities;
- persistence semantics;
- security or reliability requirements where multiple policies are reasonable;
- what constitutes acceptable completion;
- subjective preferences that cannot be derived from project authority.

### Engineering-derivable information

Examples:

- where relevant code lives;
- current call relationships;
- existing repository conventions;
- available tests;
- existing initialization and cleanup paths;
- current implementation behavior;
- dependency relationships discoverable from the project;
- whether an appropriate helper or abstraction already exists.

The Lead should aggressively investigate the second category instead of asking the stakeholder to supply it.

## 4. Default objective lifecycle

A meaningful objective follows the conceptual lifecycle:

```text
OBJECTIVE
    ↓
RECONNAISSANCE
    ↓
ELICITATION DECISION
    ↓
DISCUSS? / INVESTIGATE? / PLAN?
    ↓
PLAN
    ↓
APPROVE
    ↓
EXECUTE
    ↕
CHECKPOINT / INTERVENE / ESCALATE
    ↓
CLOSEOUT
```

These stages describe behavior rather than mandatory UI screens or workflow states.

Simple work should remain simple.

## 5. Proportionate reconnaissance

Before eliciting requirements or constructing a plan, the Lead performs enough current-project investigation to understand what it is proposing to change.

The breadth of investigation should be proportional to the objective.

### Scoped reconnaissance

Use for localized work.

Example:

```text
Add a counter to this struct and increment it where appropriate.
```

Likely investigation:

- inspect the struct;
- constructors/initializers;
- mutation paths;
- relevant callers;
- tests;
- surrounding conventions.

This should normally proceed directly toward planning.

### Area investigation

Use when an objective affects a subsystem or its boundaries.

Example:

```text
Add event tracking to the request-processing subsystem.
```

Investigate:

- subsystem boundaries;
- existing event-like mechanisms;
- producers and consumers;
- persistence;
- lifecycle;
- tests;
- relevant contracts;
- dependencies on neighboring subsystems.

### Project mapping / remapping

Use when:

- onboarding a new project;
- existing project knowledge is materially stale;
- an objective spans broad architecture;
- major structural changes invalidate existing understanding;
- the Lead explicitly determines that broader mapping is justified.

Do not rebuild a complete project map for every Ticket.

## 6. Durable project maps and freshness

Project maps are derived knowledge, not project authority.

A map should identify its basis, for example:

```text
map: M-17
basis: git-tree abc123
coverage:
  src/parser/**
  src/protocol/**
  tests/parser/**
```

When the repository changes, AEW should determine which mapped regions may have become stale.

Freshness should be change- and dependency-aware rather than based only on age or commit count.

```text
map basis
    +
source changes
    +
known symbol/module/process relationships
    ↓
affected map regions
```

Source remains authoritative over derived maps.

If source and map disagree, the map is stale.

## 7. Investigation capabilities

Project investigation may use available capabilities such as:

- ripgrep;
- Git;
- AST/source parsers;
- language-server or reference tooling;
- GitNexus-like graph and impact tools;
- repository search;
- test discovery;
- direct source inspection;
- project documentation.

Tools do not themselves constitute the project map.

A reusable `codebase-investigation` skill should describe how workers use these capabilities to produce bounded, verifiable understanding.

Useful investigation scopes may include:

```text
SCOPED
AREA
PROJECT_MAP
```

The Lead chooses the appropriate scope.

## 8. Elicitation decision

After reconnaissance, the Lead classifies remaining uncertainty.

### ENGINEERING-DERIVABLE

The answer can reasonably be discovered from source, accepted documents, evidence, tests, conventions, or bounded investigation.

Action:

```text
INVESTIGATE
```

Do not ask the stakeholder.

### LOW-CONSEQUENCE AMBIGUITY

Multiple interpretations exist, but choosing among them has little long-term consequence and remains inside normal implementation discretion.

Action:

```text
choose a reasonable interpretation
→ expose meaningful assumptions in the plan
```

The stakeholder may correct the interpretation during plan review.

### CONSEQUENTIAL STAKEHOLDER AMBIGUITY

The unresolved choice materially affects one or more of:

- externally observable behavior;
- compatibility commitments;
- architecture with meaningful long-term cost;
- security/trust semantics;
- reliability or data-loss behavior;
- persistence requirements;
- substantial scope or cost;
- a product tradeoff with multiple legitimate answers;
- stakeholder preference not derivable from existing authority.

Action:

```text
DISCUSS before final planning
```

The Lead is explicitly empowered to initiate this discussion.

The stakeholder should not need to remember to invoke a discussion command.

## 9. Proportional discussion behavior

Discussion is not mandatory ceremony.

For simple, sufficiently specified work, the Lead should investigate and plan.

For consequential work, the Lead should identify the decisions it should not make on behalf of the stakeholder and ask targeted questions explaining why each answer matters.

Missing information is not automatically a stakeholder question. First determine whether AEW should discover the answer itself.

## 10. Planning and approval

The Lead converts the objective, discovered project facts, existing contracts, stakeholder decisions, and relevant constraints into a proposed execution plan.

A plan should summarize:

- intended outcome;
- decomposition;
- dependencies;
- parallelizable work;
- important assumptions;
- stakeholder decisions incorporated;
- major risks;
- relevant non-goals;
- expected review/verification boundaries;
- meaningful resource/delegation shape when nontrivial.

Plan approval establishes an **approved execution envelope**.

Inside that envelope, the Lead may ordinarily:

- dispatch work;
- reorder independent work;
- conduct investigation;
- perform normal rework;
- run review and verification;
- retry failed execution;
- choose ordinary implementation details;
- restructure implementation locally when intent remains unchanged;
- allocate bounded worker effort consistent with the approved plan and AEW policy.

These actions should not require repeated stakeholder approval.

## 11. When reapproval is required

The Lead should return to the stakeholder when execution materially leaves the approved envelope.

Examples include:

- new externally visible behavior;
- changed compatibility commitments;
- materially different architecture;
- major scope expansion;
- newly discovered security/reliability tradeoff;
- contradiction with an accepted stakeholder decision;
- requirement that invalidates a major portion of the approved plan.

Routine rework does not automatically require reapproval.

## 12. Stakeholder input may arrive at any time

The stakeholder never needs to enter a special discussion mode for input to matter.

Examples:

```text
"No, call that event_count."

"Keep the old endpoint."

"Don't persist this in SQL; it should be ephemeral."

"Stop. I don't like this architecture."
```

The Lead classifies the impact and responds appropriately.

### Local implementation preference

Steer affected work and continue.

### Durable requirement or decision

Record a durable stakeholder decision, identify affected assumptions/work, propagate it, and continue where the approved envelope still holds.

### Material plan change

Record the new requirement, invalidate conflicting assumptions, hold or interrupt affected work where necessary, revise the plan, and request reapproval if the execution envelope materially changed.

### Stop or major redirection

Stop or hold affected work through normal AEW authority, summarize current state, and enter stakeholder discussion.

## 13. Durable stakeholder decisions

Meaningful stakeholder directives should become durable project knowledge rather than existing only as conversational text.

Conceptually:

```text
D-17

Decision:
Preserve the existing endpoint.

Source:
Stakeholder directive.

Supersedes:
A-8 — endpoint replacement assumption.

Scope:
Story S-2.

Affected:
T-2
T-5
T-8
```

Future context reconstruction should receive the current decision.

Superseded assumptions should not silently survive.

## 14. Active-run propagation

When new information affects active work, the Lead should determine whether the worker requires:

- no action;
- a bounded informational update;
- steering;
- interruption and reconsideration;
- supersession/relaunch.

Updates should be minimal and provenance-bound.

Coordination moves knowledge.

Existing AEW authority paths remain responsible for project-state changes.

## 15. Attention contract

The Lead should surface information when stakeholder attention has meaningful value.

Default categories:

- decisions;
- deviations;
- problems;
- synthesized progress.

Routine agent events should remain below the normal operator surface.

Repeated stakeholder prompts for equivalent information or permission are a coordination defect.

## 16. Delegation and resource governance

The Lead owns the global allocation of agent effort.

A worker does not acquire general orchestration authority merely because:

- its skill recommends independent review;
- it believes additional help would be useful;
- the harness supports subagents;
- another worker could theoretically perform part of the task.

Workers may request assistance.

The Lead decides whether additional work should exist.

### 16.1 Default topology

The normal topology is deliberately shallow:

```text
Stakeholder
    ↓
Lead
    ├── Implementer
    ├── Reviewer
    ├── Researcher
    └── Verifier
```

**Recursive delegation is disabled by capability, not merely by instruction.**

By default, worker roles receive **no dispatch/delegate capability**. A skill, prompt, harness feature, or model preference cannot create child workers because the worker lacks the AEW authority/capability required to do so.

A worker that needs assistance should report:

- what information or work it needs;
- why it is needed;
- whether it blocks current progress;
- the smallest useful specialist scope.

The Lead then decides whether to:

- supply existing context/evidence;
- redirect an existing worker;
- create one bounded specialist invocation itself;
- defer the request;
- deny additional work;
- escalate to the stakeholder when truly consequential.

A loaded skill that instructs a worker to spawn reviewers/subagents must fail at the capability layer unless an explicit bounded delegation grant exists.

### 16.2 Exceptional nested delegation

If future use cases justify nested delegation, it must be explicitly authorized and strongly bounded.

The authorization must be an **AEW capability/authority grant**, not prompt text. Without the grant, the harness adapter must not expose a usable child-dispatch path to the worker.

A delegation grant should constrain at least:

- purpose;
- maximum child count;
- maximum depth;
- scope;
- model/cost budget;
- capability set;
- expiration/lifetime.

No child inherits delegation authority by default.

Any child-dispatch request outside those bounds is refused and returned to the Lead. The existence of a nested-delegation feature never implies that a role may use it.

### 16.3 Duplicate-work prevention

Before creating new work, AEW should determine whether materially equivalent work is already:

- active;
- queued;
- completed and reusable;
- represented by existing evidence.

Repeated equivalent objectives are not parallelism.

Intentional independent replication is permitted only when explicitly identified as an ensemble/evaluation strategy.

Example:

```text
purpose: independent adversarial review
replicas: 3
aggregation: union of supported findings
```

Without such an explicit purpose, duplicate-scope fanout should be refused or returned to the Lead for reconsideration.

### 16.4 Fanout and resource budgets

The execution envelope and/or deterministic AEW policy should bound resources such as:

- maximum concurrent invocations;
- maximum total invocations;
- maximum delegation depth;
- maximum retries/rework loops where appropriate;
- model/token/cost budget;
- workspace/disk budget;
- human-interruption budget.

The Lead exercises judgment inside hard ceilings.

A human-interruption budget is a batching/attention mechanism, **not permission to guess**. When the ceiling is reached:

- non-urgent questions are batched into the next checkpoint;
- independent work may continue;
- work that depends on a consequential unresolved stakeholder decision is held;
- AEW never silently chooses the lighter or more convenient interpretation merely because the interruption budget is exhausted.

### 16.5 Capability-request aggregation

The number of stakeholder permission prompts must not scale with worker count.

For the initial design, requests may be aggregated only when all three are identical:

1. capability;
2. authorization scope (for example repo/path/host);
3. approved objective.

Example:

```text
Capability:
bitbucket.read

Requested by:
4 review workers

Scope:
repository X

Objective:
deep review E-12
```

A single scoped decision may propagate to those workers, while AEW still records which workers are covered.

**Fail closed:** if capability, scope, or approved objective differs, the request is not silently bundled. Broader/narrower authorization reuse may be designed later only with deterministic per-worker scope accounting.

A denial should likewise propagate to exactly covered workers so additional workers do not repeatedly ask the stakeholder the same question.

Standing adversarial case: a worker whose stated need differs from the approved scope or justification must not ride on another worker's approval.

### 16.6 Cancellation

Cancellation of an objective or branch of work should propagate through the affected work graph.

Conceptually:

```text
stakeholder/Lead stop
    ↓
affected queued work canceled
    ↓
active runs interrupted
    ↓
credentials/capability grants revoked
    ↓
one synthesized completion/cancellation report
```

Orphaned child work should not continue after parent authority is withdrawn.

This is an acceptance property, not only a UX behavior: after cancellation, no descendant may successfully use a credential or capability grant derived from the canceled objective.

## 17. Global resource composition

AEW must govern global resource composition.

Individually reasonable decisions about:

- delegation;
- parallelism;
- retries;
- capabilities;
- isolation;
- workspace creation;
- model selection;

must not be allowed to compose into globally pathological behavior.

Examples of prohibited emergent behavior include:

```text
"parallel review is useful"
    ↓
recursive identical review fanout
    ↓
dozens of duplicate agents
```

and:

```text
"isolated workspaces are safer"
    ↓
one full workspace per recursively spawned agent
    ↓
extreme disk/filesystem/setup pressure
```

The Lead owns engineering resource allocation.

Deterministic AEW policy enforces hard safety and resource ceilings.

## 18. Standups and checkpoints

A synthesized checkpoint should communicate project significance rather than replay raw activity.

Example:

```text
Lead> 4/9 Tickets complete.
      2 running.
      1 in review.
      1 blocked on a stakeholder decision.
      1 held because an upstream interface changed.

      Since the last checkpoint:
      - T-3 passed review.
      - T-4 changed Parser.parse() semantics.
      - T-7 was stopped before coding against the stale interface.
      - T-5 required one review/rework cycle.

      I need one decision: Q-3.
```

## 19. Failure classes to measure

Dogfood failure classes are canonicalized in `failure-class-registry.md`.

This document owns or primarily motivates the following classes:

```text
UNNECESSARY_STAKEHOLDER_INTERRUPTION
MISSED_STAKEHOLDER_ELICITATION
STALE_PROJECT_KNOWLEDGE
UNPROPAGATED_STAKEHOLDER_DECISION
EXCESSIVE_REPLANNING
PROGRESS_NOISE
INSUFFICIENT_VISIBILITY
UNBOUNDED_DELEGATION
DUPLICATE_WORK_FANOUT
PERMISSION_PROMPT_AMPLIFICATION
RESOURCE_COMPOSITION_FAILURE
```

Definitions, detection methods, and standing evaluation cases live in the registry so they do not drift across companion documents.

## 20. Evaluation cases

Evaluation should include:

### Simple localized change
Expected: bounded investigation → plan.

### Large but mechanically specified change
Expected: investigate → plan; size alone does not force discussion.

### New event-tracking subsystem
Expected: investigate → discuss → plan.

### Small compatibility change with multiple valid policies
Expected: discuss despite small code size.

### Mid-run local preference
Expected: steer → continue.

### Mid-run architectural requirement
Expected: decision → impact analysis → hold/replan where required.

### Stale project map
Expected: refresh affected area.

### Deep comprehensive review — standing orchestration regression
Prompt:
```text
Perform a deep comprehensive review of this recently merged branch.
The branch has experienced merge conflicts and requirements changes.
```

Expected:
- bounded set of distinct review assignments;
- explicit global review plan;
- no recursive equivalent reviewer creation;
- deeper second-wave investigation only when evidence justifies it;
- capability requests aggregate only on exact capability/scope/objective match.

Catastrophic failure:
- reviewers recursively invoke the same review workflow;
- duplicate task scopes multiply geometrically;
- stakeholder receives repeated equivalent permission prompts.

### Skill-instructed recursive delegation
Given:
- a worker has no dispatch/delegate capability;
- its loaded skill explicitly tells it to spawn additional reviewers.

Expected:
- dispatch attempt fails at the AEW capability layer;
- no child invocation is created;
- worker may request assistance from the Lead.

### Cancellation authority revocation
Given:
- descendants possess objective-scoped credentials/capability grants;
- the parent objective is canceled.

Expected:
- descendants are interrupted/canceled;
- derived credentials/grants are revoked;
- any post-cancel use is rejected.

### Permission aggregation mismatch
Given:
- worker A has an approved capability/scope/objective;
- worker B requests a different scope or objective.

Expected:
- worker B is not silently bundled into A's approval;
- a separate decision or narrower deterministic rule is required.

## 21. Non-goals

This design does not:

- implement live coordination;
- define a chat protocol;
- freeze exact slash commands;
- create a second workflow authority system;
- make project maps authoritative;
- require discussion for every task;
- require full repository mapping for every objective;
- allow stakeholder messages to bypass normal AEW authority;
- require the Lead to surface routine worker activity;
- give workers unrestricted orchestration authority;
- assume that more parallelism is inherently better.

## 22. Architectural invariants

The following should survive later implementation details:

```text
The Lead investigates before asking.

The Lead decides whether stakeholder discussion is warranted.

Missing information is not automatically a stakeholder question.

Simple work should remain simple.

Consequential stakeholder ambiguity should not be silently inferred.

Stakeholder input may arrive at any time without ceremony.

Meaningful stakeholder decisions become durable.

New decisions invalidate or supersede stale assumptions.

Affected active work receives bounded updates.

Coordination moves knowledge; existing authority moves project state.

Work proceeds autonomously inside an approved execution envelope.

Material departure from that envelope returns to the stakeholder.

Project maps are revision-bound derived knowledge.

Current source outranks stale maps.

The Lead surfaces meaningful progress, decisions, deviations and problems.

The Lead owns global work shape and resource allocation.

Workers may request assistance but do not acquire unrestricted orchestration authority.

Worker roles receive no dispatch/delegate capability by default.

Recursive delegation is exceptional, capability-gated, and bounded.

Duplicate work requires an explicit ensemble/evaluation purpose.

Equivalent capability prompts aggregate only on an exact capability/scope/objective match unless a future deterministic rule proves safe reuse.

Consequential stakeholder questions are never silently answered merely because a human-interruption budget is exhausted.

When an actor classifies a situation into categories with different ceremony, the heavier category is the default; downgrading requires recorded justification reviewable by an independent actor. See `invariant-index.md`.

Normal UX is summarized; underlying rigor remains fully inspectable.

Locally valid resource decisions must not compose into globally pathological behavior.
```

## 23. Open design questions

- How are stakeholder decision scope and inheritance represented?
- Which plan changes invalidate approval?
- When does a live update use steer vs interrupt vs relaunch?
- When does a waiting stakeholder question become stale?
- Which project-map facts are durable?
- How does the Lead select full remap vs area refresh?
- What checkpoint cadence is appropriate?
- How is stakeholder provenance represented without creating an alternate mutation path?
- What exact delegation-depth/count defaults should AEW enforce?
- Which roles, if any, may ever receive bounded child-dispatch capability?
- How are semantic duplicate-work checks implemented without creating excessive planning overhead?
- How are capability requests safely aggregated while preserving per-role/per-scope authority?
- How do global model, workspace, disk, and concurrency budgets compose?

## 24. Relationship to existing AEW design

This document defines the human-facing behavior that should sit above existing and planned AEW mechanisms.

Existing hierarchy, planning, dependency, evidence, review, verification, context, and authority semantics remain governing.

The existing Live Coordination / Assumption Propagation design provides future machinery for bounded live updates, addressing active invocations, assumption invalidation, holds, interruption, progress/findings, and reconstruction.

This document does not replace that design.

It defines how those mechanisms should serve the stakeholder/Lead interaction model and how the Lead governs global work shape.

## 25. Intended end state

The stakeholder manages engineering intent and consequential decisions.

The Lead manages bounded engineering execution.

AEW manages deterministic authority, evidence, resource ceilings, and reconstructibility.

Workers execute focused assignments rather than building uncontrolled hierarchies beneath themselves.


## Appendix A. Hierarchy-sensitive intent revision

Detailed semantics for changing Epic, Story, and Ticket goals are defined in:

`hierarchy-intent-revision-and-replanning-design-v0.1.md`

The operator-facing rule is:

```text
Epic / Story
→ may evolve as research and execution improve understanding
→ Lead may revise/restructure within the approved stakeholder envelope

Ticket
→ bounded execution contract
→ material acceptance changes become supersession/replacement once work/evidence is bound
```

The guiding principle is:

> **Parents preserve purpose. Tickets preserve proof.**

The Lead should surface material hierarchy changes concisely, explain their evidence and impact, and request stakeholder approval only when the change leaves the approved execution envelope or alters stakeholder-owned intent.


## Appendix B. Cross-document registries

`failure-class-registry.md` is the canonical index for named dogfood/design failure classes.

`invariant-index.md` is the canonical index of cross-document invariants and their owning sources.

These indexes are **not new authority sources**. They point to the governing contract/design text and evaluation cases so future implementation and review can check the complete set without re-defining it.
