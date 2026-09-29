---
name: adversarial-review
description: Review stateful engineering changes for invariant violations across retries, crashes, concurrent operations, stale authority, identity collisions, cleanup paths, and alternate entries. Use for an assigned review with concrete contracts and artifacts; skip cosmetic-only work.
metadata:
  version: '0.3.0'
  status: candidate
---

# Adversarial review

## Purpose

Find reachable sequences of individually plausible operations that violate a stated invariant.

Produce bounded, reproducible findings with explicit evidence strength and coverage limits.

This candidate teaches review technique. Its benefit has not yet been demonstrated on target workers.

This skill adds technique only. It grants no authority, permission, capability, credential, or project-state transition.

## Use and non-use

Use when assigned to review a concrete change or bounded subsystem where a protected property depends on:

- ordering;
- identity;
- authority lifetime;
- freshness;
- persistence;
- retry behavior;
- cleanup;
- concurrency;
- shared state;
- recovery;
- alternate entry paths.

Typical subjects include:

- stateful APIs;
- persistence layers;
- authorization enforcement;
- queues and workers;
- evidence consumption;
- recovery systems;
- workflow engines;
- distributed or concurrent state transitions;
- integration boundaries.

A narrow review may require only one meaningful sequence.

Skip this skill for:

- cosmetic edits;
- pure explanations;
- documentation changes with no relevant behavioral effect;
- tasks where no protected stateful behavior is involved.

Answer the assigned question directly. Do not turn a spelling correction into an audit.

If an assigned review lacks semantics required for a defensible conclusion, follow **Abstention** rather than inventing them.

No model identity, provider, routing, or effort policy is encoded here.

## Inputs and outputs

Required inputs:

- assigned review scope;
- permitted operations;
- current artifacts and their revision or digest;
- relevant authoritative requirements;
- available capability descriptions.

A diff plus enough surrounding implementation to trace entry points and shared effects is preferable to isolated snippets.

Project-specific inputs come from the surrounding task context rather than this reusable skill.

Return the existing review format if one is supplied.

Otherwise use:

```text
Scope and observed revision:
  <revision or digest>

Exploration budget:
  <supplied budget>
  or
  default: begin with the 2-3 highest-consequence sequences

Confirmed findings
  Finding F1
    Invariant:
      <one sentence>

    Source:
      <contract / acceptance criterion / other designated authority>

    Anchors:
      Guard: <location>
      Effect or bypass: <location>

    Sequence:
      1. <operation>
         State after step: <state>
         Identity: <actor / operation / generation>
         Durable: <facts>
         Volatile: <facts>
         Next legal entry: <entry>

      2. ...

    Expected:
      <what the invariant requires>

    Actual:
      <what the reachable sequence produces>

    Evidence class:
      probe-observed | source-trace

    Evidence:
      <command, fixture revision and relevant output>
      or
      <source trace summary>

    Impact:
      <consequence if reached>

    Regression probe:
      <smallest discriminating test>
      fails on: <reviewed condition>
      passes when: <required corrected condition>


Not established
  Hypothesis H1
    Invariant or assumption:
      <statement>

    Conditional sequence:
      <reachable sequence if unresolved fact has the suspected value>

    Depends on:
      <exact missing contract, persistence guarantee, scheduler behavior,
       reachability fact, isolation level, or other assumption>

    Evidence already established:
      <source trace or observations>

    Evidence required:
      <exact fact or artifact needed>

    Decision blocked:
      <what conclusion cannot yet be made>


Coverage and limits
  Checked:
    <paths / boundaries traced>

  Budget expansion:
    <none>
    or
    <directly coupled paths followed beyond initial sequence selection,
     and why they were required>

  Not checked:
    <relevant paths not traced>
    reason: <budget / access / out of scope>
```

Confirmed defects, unresolved hypotheses, and recommendations are different things. Do not merge them.

A conditional sequence whose validity depends on an unresolved assumption belongs under **Not established**, not under **Confirmed findings**.

No findings means only that no defect was established within the stated scope and coverage.

It is not workflow approval.

## Preconditions

### 1. Establish review scope

Identify the assigned scope and permitted operations.

A tool's presence does not grant permission to use it or permission to change project state.

### 2. Pin the reviewed subject

Identify the supplied revision, artifact digest, or equivalent stable subject.

If relevant files change during inspection, conclusions derived from the old state are no longer automatically current.

Refresh within scope or explicitly report the drift.

### 3. Establish an exploration budget

Use the supplied review budget when one exists.

Otherwise begin with the two or three highest-consequence sequences.

This is an initial exploration budget, not permission to abandon a sequence before its reachability or defense can be established.

A selected sequence may be followed through directly coupled alternate paths when those paths are necessary to prove or disprove the same suspected defect.

Do not expand into unrelated subsystems merely because they exist.

Report meaningful budget expansion under **Coverage and limits**.

### 4. Confirm safe probe conditions

Before executing a probe, establish that:

- execution is permitted;
- the target is disposable or otherwise safe;
- the probe will not mutate prohibited state.

Without execution capability, use source traces and label them accurately.

Never fabricate a run.

## Procedure

### 1. Name the protected property

Write one sentence of the form:

> For resource R, property P must hold when effect E becomes visible.

Include relevant identity, version, generation, freshness, or ownership scope.

Example:

> An effect must be committed only under the current grant generation.

Source the property from the supplied:

- contract;
- acceptance criterion;
- specification;
- documented invariant;
- other designated authority.

If it is not authoritative and is instead an assumption, label it explicitly as:

```text
assumption
```

Do not claim a contract violation based only on an unresolved assumption.

The review assertion describes what is being tested. It does not create a new project rule.

### 2. Map the relevant paths

Find:

- the public or supported entry point;
- the shared mutation or externally visible effect;
- the guard protecting that effect;
- retry paths;
- recovery paths;
- cleanup/error paths;
- batch paths;
- CLI paths;
- background workers;
- other alternate entries that can reach the same effect.

Follow calls and persistence boundaries far enough to establish reachability.

Search in at least two ways.

#### Call sites

Inspect direct and indirect callers of:

- the effect;
- the guard;
- relevant state mutation.

#### Registration sites

Inspect mechanisms that may establish entry points without ordinary caller relationships, including:

- route tables;
- handler registries;
- RPC dispatch maps;
- plugin registration;
- dynamic loading;
- scheduler configuration;
- cron configuration;
- queue-consumer registration;
- callbacks;
- reflection;
- string-keyed dispatch.

Entry points wired through registration frequently do not appear in simple caller searches.

A function is an alternate entry only when supported by:

- a caller;
- registration;
- scheduler;
- worker configuration;
- supported operation;
- or explicitly supplied reachability assumption.

Absence from caller search alone does not prove that a path is unreachable.

Maintain a compact table.

`unknown` is an acceptable value.

| Operation/path | Reads or checks | Durable writes/effects | Guard at effect boundary | Failure/retry path |
|---|---|---|---|---|
| Normal entry | identity, revision | queued intent | identify exact guard | retry entry |
| Recovery entry | durable intent | shared resource | same guard or bypass? | restart cursor |

### 3. Write sequences before judging them

Choose the highest-consequence invariant and most exposed relevant boundary first.

Trace one **normal sequence** before constructing hostile sequences.

The normal trace verifies that the reviewer's model of the implementation matches actual behavior.

If the normal sequence contradicts the state table or assumptions, correct the model before relying on hostile traces.

Then trace hostile sequences crossing at least two operations.

For every sequence, record:

- state after each step;
- actor or operation identity;
- relevant generation/version where applicable;
- durable information;
- volatile information;
- next legal entry point.

This is insufficient:

> There could be a race.

This is useful:

```text
1. Operation A reads generation 4.
2. Operation B replaces generation 4 with generation 5.
3. Operation A reaches durable commit using its captured generation.
4. Commit path does not revalidate generation.
5. Effect created under retired authority becomes visible.
```

Select sequence families based on relevance rather than mechanically applying every one.

| Boundary | Concrete sequence to trace | Question at the effect |
|---|---|---|
| Authority lifetime | authorize → queue → revoke/replace → resume | Is current authority checked again where the effect commits? |
| Replay / partial commit | effect succeeds → receipt lost → retry | Can the logical action occur twice? What durably deduplicates it? |
| Identity collision | two distinct actions → same dedup key / tenant / path | Is identity scoped strongly enough to prevent suppression or misrouting? |
| Error / cleanup | effect partially applied → error → unwind | Does cleanup reverse everything already made visible? |
| Crash / reconstruction | record intent → crash → reconstruct → finish | Which facts survive, and does recovery use current facts or a captured decision? |
| Evidence freshness | test revision A → modify to B → consume A result | Is evidence bound to every input whose change matters? |
| Race | read/check A → competing write B → commit A | Is the check protected through commit, repeated, fenced, locked, or CAS-enforced? |
| Unexpected order | cancel → delayed completion; complete → cancel | Can late work resurrect or overwrite retired state? |
| Alternate entry | guarded API → same effect through batch/recovery/registered handler | Do equivalent effect paths enforce the same property? |

Expand only when a new path is directly relevant to the selected invariant or when new evidence identifies another high-consequence boundary within scope.

### 4. Try to disprove the suspected defect

Before reporting a finding, actively look for defenses that invalidate the sequence.

Inspect:

- shared effect boundaries;
- transaction semantics;
- serialization guarantees;
- locks;
- compare-and-swap behavior;
- fencing tokens;
- durable deduplication;
- database constraints;
- generation checks;
- idempotency keys;
- rollback guarantees.

An earlier missing check does not establish a defect if a later atomic boundary correctly enforces the property.

A missing local lock may be irrelevant when the database serializes the conflicting transition.

A captured generation may be a fence rather than a continuing permission.

A supposed crash point may not exist if all relevant changes belong to one atomic transaction.

If a defense closes the sequence, record the reason if useful and discard the finding.

If the sequence depends on an unresolved fact such as:

- isolation level;
- scheduler semantics;
- persistence guarantees;
- contract meaning;
- dynamic reachability;

move it to **Not established**.

Do not select the weakest imaginable environment and treat it as fact.

### 5. Construct the smallest discriminating probe

When permitted, reproduce the suspected violation in a disposable fixture with explicit initial state.

Prefer deterministic techniques such as:

- controlled pauses;
- injected errors;
- named transactions;
- explicit barriers;
- fault injection;
- deterministic replay.

Avoid relying on repeated timing attempts when a deterministic mechanism is available.

Assert:

- the relevant invariant;
- the resulting durable state;
- any externally visible effect.

Do not rely only on an exception message.

A useful probe discriminates between the suspected defective behavior and the expected safe behavior.

State:

```text
Fails when:
  <reviewed behavior>

Passes when:
  <specific defense or corrected condition>
```

Record:

- command or procedure;
- fixture revision;
- relevant output;
- result.

If execution is unavailable, a source-level counterexample can still support a finding when reachability and semantics are established.

Label it `source-trace`, not `probe-observed`.

Keep probes proportional.

Do not:

- kill live production processes;
- rotate real credentials;
- trigger deployments;
- edit review targets during a read-only review;
- mutate shared services merely to test a hypothesis;
- bypass an authority refusal through another interface.

If such action would be required, provide the smallest proposed probe and state the missing permission or capability.

### 6. Report and stop

For every confirmed finding, connect:

```text
sourced invariant
        ↓
reachable sequence
        ↓
guard/effect anchors
        ↓
observed or source-established behavior
        ↓
specific violated consequence
```

Provide the smallest useful regression probe.

When useful, identify the class of defense required.

Do not prescribe architectural redesign unless the evidence requires it.

Stop when:

- the initial budgeted high-consequence sequences have been resolved;
- directly coupled paths necessary to establish those sequences have been traced;
- confirmed findings are supported;
- unresolved sequences have been placed under **Not established**;
- remaining relevant coverage is explicitly recorded.

Discovering another adjacent subsystem is not permission for an unlimited audit.

## Verification before emitting a confirmed finding

Before reporting something under **Confirmed findings**, verify all of the following:

- The invariant comes from an identified authority.
- The claimed consequence actually violates that invariant.
- The initial state is reachable.
- Every transition in the sequence is reachable under supplied guarantees.
- Anchors identify both the relevant guard and the effect or bypass.
- Any alternate path claimed as reachable has an established caller, registration, supported entry, or explicitly labeled reachability assumption.
- Evidence class is accurate.
- `probe-observed` means the probe actually ran.
- `source-trace` means the conclusion is established from source and supplied semantics without claiming execution.
- No unresolved assumption is carrying the conclusion.
- Evidence identifies the reviewed revision.
- The review has attempted to identify defenses at the shared effect boundary.

A passing test for revision A is not evidence for revision B unless the evidence remains valid for every relevant changed input.

## Common mistakes

| Attractive mistake | Better behavior |
|---|---|
| Read only changed functions | Trace callers, registrations, the shared effect, and relevant recovery paths. |
| Call a path unreachable after a caller search | Check registration and dynamic dispatch before discarding it. |
| Start hostile reasoning before understanding normal flow | Trace one normal sequence and correct the state model first. |
| List every imaginable risk | Keep reachable violations and bounded unresolved hypotheses. |
| Report every missing local check | Inspect enforcement at the atomic effect boundary. |
| Equate a retry flag with idempotency | Locate the durable key, its scope, and atomic relationship to the effect. |
| Assume dedup identity is globally correct | Check tenant, resource, generation, namespace, and operation scoping. |
| Assume all crash points lose all state | Separate committed state, transaction-local state, and volatile memory. |
| Ignore cleanup because the main path is correct | Trace what remains visible when execution exits through error handling. |
| Treat a green result as universally current | Compare evidence subject and all relevant inputs against the consumed revision. |
| Use timing luck as a concurrency test | Prefer deterministic synchronization or injected failure. |
| Patch during a read-only review | Return evidence and the proposed regression probe or remedy. |
| Treat an unresolved assumption as a confirmed defect | Put it under **Not established** and name the exact missing fact. |
| Exhaust the nominal sequence count and abandon an unresolved trace | Follow directly coupled paths required to establish or disprove that sequence, then report budget expansion. |

## Abstention

Do not give a definitive conclusion when an essential fact is unavailable and that fact determines whether the suspected violation exists.

Examples include missing:

- authoritative requirement;
- relevant source path;
- current revision;
- persistence guarantee;
- isolation level;
- scheduler semantics;
- registration information;
- capability necessary to discriminate between hypotheses.

State:

```text
Missing:
  <exact fact>

Why it matters:
  <which transition, invariant, or conclusion depends on it>

Evidence already available:
  <what has been established independently>

Needed next:
  <smallest fact, artifact, or permitted probe that resolves it>
```

Continue independent bounded inspection where useful.

Abstention from one conclusion does not require abandoning unrelated conclusions that are already supportable.

## Authority and interfaces

This section defines the skill's **self-imposed operating boundaries**.

Actual invocation authority, permissions, identity, and capabilities come from the surrounding orchestration environment.

When installed in AEW:

- **Role card** supplies identity, responsibility, scope, and authority.
- **Context pack** supplies the current assignment, contracts, revisions, and project facts.
- **Capabilities** supply permitted inspection, search, or isolated execution facilities.
- **AEW** owns project state, transitions, credentials, routing, review disposition, verification, evidence admissibility, and integration.

This skill supplies procedural review technique within those boundaries.

It does not create a Reviewer, Lead, approval right, capability, provider, credential, or transition.

The skill never:

- directs or implies approval;
- directs acceptance or merge;
- dispatches work;
- causes or redefines project-state transitions;
- turns uncertainty into approval or blocking authority;
- forges engine-stamped identity or provenance;
- claims an unrun test passed;
- treats harness completion as verification;
- acquires credentials;
- treats availability of a CLI, MCP server, harness function, API, or other interface as permission to use it;
- retries a forbidden operation through another interface after an authority refusal.

A current authority refusal means that operation stops.

If skill guidance conflicts with the assigned role, supplied contract, resolved capability, or orchestration authority, the external authority governs.

Report the conflict rather than inventing a path around it.

## Examples

Read a worked composition review when a concrete state trace would help.

Example subjects should include:

- stale authority across queued work;
- retry after lost acknowledgement;
- partial cleanup after a durable effect;
- alternate registered entry bypassing a normal guard;
- apparent missing check disproved by an atomic effect boundary.

Negative examples should include:

- unreachable alternate paths;
- vague “possible race” reports without a sequence;
- missing-check findings invalidated by downstream enforcement;
- conditional hypotheses incorrectly presented as confirmed;
- attempts to turn engineering observations into workflow authority.

Examples may be synthetic or derived from real historical defects, but they must not silently assert that historical behavior remains true of the current project.

## Evaluation

This version is an unevaluated candidate.

Compare the same target worker on equivalent tasks:

```text
same target model
same task
same supplied project context
same capabilities
same model settings

A: without this skill
B: with this skill
```

Important measurements include:

- valid important findings;
- missed important findings;
- unsupported findings;
- correct rejection of false-positive candidates;
- correct handling of unresolved assumptions;
- evidence-class accuracy;
- correct abstention;
- correct non-activation on irrelevant work;
- scope discipline;
- exploration-budget discipline;
- authority compliance;
- quality of regression probes;
- token usage;
- tool calls;
- elapsed time.

More findings are not inherently better.

A useful skill should improve the worker's ability to establish real defects without materially increasing unsupported findings or unnecessary review effort.

Evaluation should include cases such as:

1. A real defect requiring composition of multiple individually legal operations.
2. A tempting missing-check false positive closed by a later atomic guard.
3. An alternate entry reachable only through registration or dynamic dispatch.
4. A path that appears reachable but is actually unsupported.
5. A defect involving identity or deduplication collision.
6. A partial-cleanup failure.
7. A case whose conclusion depends on an unavailable persistence or isolation guarantee.
8. A cosmetic or otherwise irrelevant change where the skill should not expand into an audit.

Evaluator-only cases, expected answers, private rubrics, and holdouts must not be exposed to the worker during the evaluation run.

The mechanism used to enforce that isolation belongs to the evaluation environment, not to this skill.

Prefer final evaluation cases derived from independently discovered real defects when available.

Synthetic cases remain useful for development and regression.

There is no measured improvement claim or trusted-baseline status until target-worker evaluation demonstrates one.