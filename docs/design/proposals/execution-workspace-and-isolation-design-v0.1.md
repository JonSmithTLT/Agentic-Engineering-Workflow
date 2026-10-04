# AEW Execution Workspace and Isolation Design v0.1

**Status:** Proposed design  
**Scope:** Filesystem/workspace isolation, repository-scale constraints, task mutability, workspace strategy selection, and deployment boundaries  
**Origin:** M3 live-model containment observation plus external large-repository GSD/worktree failure  
**Implementation status:** Post-M3 design/hardening; exact mechanism is not frozen
**Current guarantee:** `workdir separation only`; AEW does not yet provide OS-level filesystem containment. This must be surfaced honestly in run metadata/operator status until a stronger mechanism is implemented.
**Review integration:** 2026-09-28 companion-design review incorporated. Strong containment is a prerequisite for real-repository dogfood/internal alpha, while scratch-repository M3 evaluation may continue under the explicitly weaker guarantee.

## 1. Purpose

AEW requires strong separation between agent work and protected host/project state, but filesystem isolation must remain usable on real repositories.

A single isolation mechanism must not be assumed to work for every project.

In particular, very large repositories may make per-agent worktree or full-checkout strategies prohibitively expensive in:

- setup latency;
- file materialization;
- disk consumption;
- filesystem metadata pressure;
- cleanup time;
- build/bootstrap duplication.

AEW must preserve required safety properties without turning isolation into a reason the system cannot be used.

## 2. Important distinction

AEW must distinguish:

```text
logical isolation
vs
filesystem/process isolation
```

### Logical isolation

Includes:

- invocation identity;
- credentials;
- authority;
- evidence binding;
- revision binding;
- role boundaries;
- workflow state;
- review/verification semantics.

AEW owns these semantics.

### Filesystem/process isolation

Includes:

- what paths a worker can read;
- what paths a worker can write;
- where scratch/build output lives;
- whether host paths are visible;
- whether one worker can mutate another worker's state;
- whether a worker can mutate the real checkout.

Filesystem isolation is an execution/deployment mechanism and must not be conflated with AEW logical authority.

## 3. Evidence motivating this design

### 3.1 M3 live-model containment observation

During a live M3 trial, a verifier derived a path outside its assigned workspace and wrote into the real AEW repository before deleting the file.

AEW logical authority safeguards held, but the shell process could access host filesystem paths available to the user.

The immediate cause was reduced by providing each run an explicit private scratch location.

This does **not** establish OS-level containment.

Until stronger containment exists, AEW must record and surface the actual guarantee as **workdir separation only** (or equivalent explicit wording). Absence of a containment claim must not be mistaken for containment by omission.

The observed lesson is:

> Harness permission rules and workspace conventions are not equivalent to filesystem containment.

### 3.2 External GSD large-repository observation

In a GPT-5.4 + GSD workflow outside AEW, worktree/isolation behavior made a very large full-stack repository effectively unusable until worktree isolation was patched/disabled.

The relevant real projects may contain on the order of one million files.

The lesson is:

> Mandatory per-agent worktree/full-checkout isolation may be operationally unacceptable at realistic repository scale.

This is an external observation, not an AEW defect.

## 4. Design goal

AEW should provide an isolation abstraction whose concrete strategy depends on:

- required mutability;
- concurrency;
- repository scale;
- task scope;
- setup/build cost;
- deployment environment;
- desired containment strength.

The system should choose or constrain an appropriate strategy rather than equating "isolated" with "new Git worktree".

## 5. Required invariants

Regardless of strategy:

1. Workers must not gain AEW authority merely through filesystem access.
2. Evidence and state must remain revision-bound.
3. Reviewer/verifier mutation rules remain enforceable.
4. Scratch/build output must have explicit authorized locations.
5. The real/protected checkout must not be silently mutated by workers when policy requires isolation.
6. Workspace setup cost must not grow without bound relative to task value.
7. Isolation strategy must be inspectable and recorded per invocation/run where relevant.
8. Strategy selection must fail closed if the requested safety property cannot be provided.
9. Cleanup must not destroy or mutate unrelated project state.
10. Isolation guarantees must be described accurately; "workdir separation" must not be presented as OS containment.

## 6. Candidate isolation strategies

Exact strategy names are not frozen.

### 6.1 WORKTREE

A dedicated Git worktree per mutating unit/run.

Advantages:

- straightforward Git revision isolation;
- familiar semantics;
- convenient independent mutation.

Risks/costs:

- expensive on repositories with huge file counts;
- metadata/disk/setup pressure;
- cleanup complexity;
- can compose badly with high parallelism.

Appropriate when repository scale and bootstrap cost are modest.

### 6.2 SHARED_READONLY

Workers inspect a shared source tree that is physically or effectively read-only.

Useful for:

- investigators;
- many reviewer tasks;
- source-only verification;
- codebase mapping.

Scratch/build output must live elsewhere.

This may avoid unnecessary per-role checkout creation.

### 6.3 SHARED_MUTABLE_SERIAL

One mutable checkout is used for implementation work, with AEW enforcing serial mutation.

Useful when:

- worktree setup is prohibitively expensive;
- parallel mutation is unnecessary or unsafe;
- logical AEW sequencing is sufficient.

This strategy must not be confused with strong filesystem containment.

Its serialization lock is load-bearing. The lock must be bound to an owning invocation/run. After a crash, resume/reconciliation must first classify the stale owner consistently with AEW interruption semantics (for example `INTERRUPTED`) and reconcile its workspace/authority before the lock is released to a new mutator. A stale lock may not simply be deleted and ignored.

### 6.4 OVERLAY / COPY-ON-WRITE

Workers see a shared read-only lower source tree plus a private writable overlay.

Conceptually:

```text
shared source tree
read-only lower layer
      │
 ┌────┼────┐
 ▼    ▼    ▼
A     B    reviewer
COW   COW  readonly/scratch
```

Potential benefits:

- full-tree visibility;
- private changes;
- lower duplication than full materialization;
- stronger protection of host checkout.

Implementation feasibility depends on deployment OS/container/runtime.

### 6.5 SPARSE WORKSPACE / PARTIAL MATERIALIZATION

Only relevant project regions are materialized.

Potentially useful when repository structure and dependency boundaries make partial checkout safe.

Risks:

- missing dynamic/config/build dependencies;
- false confidence in incomplete context;
- complexity deciding what must be present.

This should not be used where completeness cannot be established.

### 6.6 CONTAINER / SANDBOX

Run the worker in a process/container boundary with controlled mounts.

Potentially combines:

- protected host checkout;
- scoped writable roots;
- private scratch;
- bounded runtime/tool access.

This may become the preferred approach for strong containment, but the exact mechanism is not yet frozen.

A mechanism that actually enforces protected writable roots at the OS/runtime boundary is a **prerequisite for real-repository dogfood/internal alpha**. The design does not pre-select containers over another mechanism; it does require that the chosen mechanism pass the containment regression gate in §12.

## 7. Strategy selection inputs

Selection should consider measurable facts, not assumptions.

Potential inputs:

```text
tracked file count
filesystem entry count
repository size
worktree creation latency
workspace cleanup latency
disk usage
bootstrap/build cost
task mutability
parallel mutation need
review/verification role
task scope
required containment strength
```

Repository size alone is not sufficient.

A small repository with extremely expensive bootstrap may make worktrees undesirable.

A large repository with cheap COW/overlay support may still permit strong isolation efficiently.

## 8. Lead and AEW responsibilities

The Lead decides whether parallelism is useful.

AEW policy determines which isolation/concurrency combinations are permitted.

Example:

```text
Lead:
"These four Tickets could run in parallel."

AEW policy:
"This project's isolation profile permits only one mutable workspace."

Lead:
"Serialize mutating work; run read-only investigation concurrently."
```

The Lead should adapt the execution plan to resource constraints instead of fighting them.

## 9. Project isolation profile

Projects should be able to declare or derive isolation constraints.

Conceptual example:

```yaml
workspace:
  isolation:
    preferred: shared_mutable_serial
    worktree:
      allowed: false
      reason: repository scale makes per-agent materialization prohibitive
```

Exact schema is not frozen.

Where possible, measured performance should inform configuration.

## 10. Role-sensitive isolation

Different roles should not automatically receive identical workspace strategies.

### Implementer

Usually requires a writable view.

Possible strategies:

- worktree;
- overlay/COW;
- shared mutable serial.

### Reviewer

Often requires:

- exact reviewed revision;
- read access;
- safe scratch;
- possibly bounded test/probe execution.

A full writable worktree should not be assumed necessary.

### Verifier

Requires:

- exact revision;
- verification capability;
- isolated scratch/build state;
- protection against mutation of authoritative review target where applicable.

### Investigator/Researcher/Planner

Often read-only.

These roles are strong candidates for shared read-only source plus private scratch.

## 11. Scratch directories

Every run requiring temporary output should receive an explicit scratch location.

Scratch must be:

- clearly communicated;
- scoped to the run/invocation;
- outside protected project state where appropriate;
- cleaned safely;
- not treated as authoritative evidence merely because it exists.

Ambiguous guidance such as "write outside the workspace" is insufficient.

## 12. Containment regression requirements

When AEW claims filesystem containment, tests should include exact known outside paths.

Attempt at least:

- absolute-path write;
- `..` traversal;
- symlink escape;
- rename/move across boundary;
- mkdir outside writable roots;
- temporary-file creation outside allowed scratch;
- Python `open()` to outside path;
- shell redirect to outside path;
- tool invocation referencing another worktree/checkout.

Required result under a strong containment profile:

```text
OS/runtime-level write failure
and
no external filesystem mutation
```

This suite is an **acceptance gate** for any mechanism advertised as stronger than workdir separation and must pass before that mechanism is enabled for real projects.

Detection after the fact is defense in depth, not the primary containment guarantee.

## 13. Performance acceptance

Isolation must be benchmarked on representative repositories.

At minimum:

```text
small repository
medium repository
large/revelations-scale repository
```

Measure:

- workspace setup latency;
- disk growth;
- first useful command latency;
- cleanup latency;
- concurrency pressure;
- failure/retry cleanup behavior.

A strategy that is safe but makes normal work operationally unusable is not an acceptable default for that project class.

Benchmark acceptance is a **selection gate** for choosing a strategy as a project default, not merely an evaluation activity.

## 14. Interaction with delegation/resource governance

Isolation cost multiplies with agent fanout.

AEW must consider resource composition.

Pathological example:

```text
dozens of recursively spawned agents
×
full worktree per agent
×
million-file repository
```

may create:

- extreme disk pressure;
- filesystem metadata pressure;
- Git lock/contention issues;
- long startup times;
- cleanup failures.

Agent-count policy and workspace policy therefore cannot be designed independently.

### 14.1 Filesystem isolation does not prove semantic independence

Separate worktrees, overlays, or sandboxes prevent some live filesystem collisions. They do **not** prove that two Tickets are semantically independent.

Two independently valid changes can still:

- alter the same behavior through different files;
- rely on incompatible assumptions;
- conflict through generated/configured interfaces;
- merge cleanly while violating one side's requirement.

Therefore integration-stage checks at `COMMIT_READY` (or the governing integration gate) remain responsible for detecting cross-Ticket semantic overlap/conflict. Per-Ticket review plus filesystem isolation is insufficient.

Isolation may make these conflicts quieter, which makes integration-stage checks more important, not less.

## 15. Failure classes

Canonical failure definitions live in `failure-class-registry.md`.

This document owns or primarily motivates:

```text
HOST_WRITE_ESCAPE
ISOLATION_OVERHEAD_FAILURE
WORKSPACE_LEAK
CLEANUP_DAMAGE
FALSE_CONTAINMENT_CLAIM
RESOURCE_COMPOSITION_FAILURE
```

`RESOURCE_COMPOSITION_FAILURE` replaces the earlier local alias `RESOURCE_MULTIPLICATION` so the same cross-system phenomenon has one name.

## 16. Open questions

- Which isolation strategies are required for the first production dogfood release?
- Is OS/container containment a prerequisite for personal real-project dogfood or only internal alpha?
- Can overlayfs/container mounts be used reliably on target Rocky 8 environments?
- How are build outputs/caches shared without violating isolation?
- Can reviewers/verifiers safely use read-only shared source plus private build/scratch?
- How should workspace strategy interact with mutating concurrency?
- What exact measurements trigger "worktrees not recommended"?
- How should environment/toolchain directories be exposed?
- What filesystem resources need read-only visibility versus complete hiding?
- How should Windows development/test environments map onto Linux production semantics?

## 17. ADR candidates

This document intentionally does not freeze the following decisions yet.

Potential future ADRs:

1. **Delegated filesystem containment model**
   - which execution-layer mechanism provides protected writable roots.

2. **Workspace strategy abstraction**
   - AEW supports multiple workspace strategies rather than equating isolation with Git worktrees.

3. **Role-sensitive workspace policy**
   - reviewers/verifiers/investigators need not receive full writable worktrees.

These should become ADRs only after implementation experiments establish the appropriate semantics.

## 18. Summary principle

```text
Isolation is a required property.
A Git worktree is only one possible mechanism.
```

AEW should preserve safety while remaining usable on the repositories it is actually intended to engineer.


## 19. Cross-document registries

See `failure-class-registry.md` and `invariant-index.md`.

The current containment truth must remain visible in both implementation metadata and these indexes:

```text
workdir separation != OS-level containment
```
