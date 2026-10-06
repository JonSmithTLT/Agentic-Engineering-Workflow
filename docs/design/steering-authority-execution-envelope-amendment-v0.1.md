# A1 — Steering Authority and Execution Envelope Amendment v0.1

**Status:** APPROVED AMENDMENT  
**Date:** 2026-10-05  
**Amends:** `AEW_Crawl_Walk_Run_Steering_Design_v0.1`

## 1. Operator-only authority boundary

The commands/effects described as `aew confirm` and `aew lead mode` are not ordinary Lead tools.

A model Lead must not be able to confirm an action whose execution is waiting for operator confirmation. Otherwise Crawl and Walk collapse into self-approval.

A model Lead must not be able to increase its own autonomy.

### 1.1 Capability rule

The following operations require an **operator capability that is absent from agent shells and model tool surfaces**:

- confirm a pending steering action;
- increase autonomy (`crawl -> walk`, `crawl -> run`, `walk -> run`);
- grant an unattended conditional publication authorization such as `PUBLISH_IF_CLEAN`;
- grant any future authorization whose purpose is to let execution continue without a contemporaneous human decision.

Possession of ordinary repository, shell, policy, or Lead authority is insufficient.

The operator capability SHOULD be delivered over a channel that an invoked agent cannot reach, such as a TTY-bound operator broker, separate operator credential, or equivalent out-of-band channel.

A policy check that asks "is caller the Lead?" is not sufficient. The capability must be structurally absent.

### 1.2 What the Lead may do

The Lead may:

- request an autonomy increase for the operator to approve;
- lower autonomy without operator approval;
- request confirmation with rationale;
- continue operating at the current or lower mode.

Mode ordering is:

```text
crawl < walk < run
```

Moving left is a restriction and may be Lead-initiated. Moving right is an authority increase and is operator-only.

### 1.3 Recorded decisions

A mode increase record must name:

- operator identity/capability source;
- previous mode;
- new mode;
- Lead generation;
- policy/operational digests;
- revision at which the change became effective.

A Lead-requested increase is a request, not authority, until operator approval is recorded.

## 2. Fail-closed Walk classification

The original Walk rule is amended from a deny-list of side-effect classes to an allow-list.

Walk auto-runs an eligible action **only if every declared side effect is in the explicit bookkeeping allow-list**.

Initial allow-list:

```text
{control_state}
```

Walk requires operator confirmation when:

- any effect is outside the allow-list;
- the primitive declares no side-effect class;
- an effect class is unknown to the running engine version;
- declared effects are incomplete or fail validation.

Therefore new classes such as network access, knowledge publication, capability grant, external service mutation, or future classes fail closed.

### 2.1 Declaration conformance

Primitive catalog tests must check both:

1. every staged primitive declares side effects; and
2. observed implementation effects are a subset of declared effects.

An under-declared primitive is a release-blocking catalog defect.

## 3. Auto-run execution envelope

The auto-run loop gains independent stop conditions for resource and repetition safety.

Before each auto-executed action, the runner must check:

- execution-envelope remaining time;
- approved token/cost/tool budget where applicable;
- concurrency/admission limits;
- action repetition;
- stage wall-clock deadline.

The loop stops and surfaces attention when any bound is exhausted.

### 3.1 Repetition detector

The runner must stop if the same projected action reference or same semantic action key executes more than `N` times without a state/revision/projection change that justifies repetition.

Default:

```text
N = 2
```

The exact key may be implementation-defined, but it must be stable enough to detect a no-progress loop.

A repetition stop is not itself a workflow-state transition.

### 3.2 Wall-clock deadlines

Two bounds are required:

1. **auto-run loop deadline** — bounds how long the runner may continue selecting new actions without returning control/attention;
2. **invocation hard deadline** — bounds the lifetime of an unattended harness run.

Expiry of the auto-run loop deadline stops further auto-execution and creates operator attention.

Expiry of the invocation hard deadline is a pre-authorized **authority-reducing safety action**. The supervisor may mechanically:

- terminate the run/process;
- revoke the run credential/capability;
- mark the run interrupted/terminated through the existing run mechanism;
- require the existing reconciliation path.

Hard-deadline termination MUST NOT:

- release a load-bearing lease merely because time expired;
- mark work verified, accepted, integrated, or published;
- create a new attempt or relaunch;
- infer that the workspace is clean.

The hard deadline and its scope must be set before unattended execution begins and must be attributable to operator-approved execution policy/envelope.

## 4. Unattended Run behavior

Run mode is permitted to continue without contemporaneous operator confirmation only inside the approved execution envelope.

A STALLED or otherwise live-but-silent run does not receive new authority merely because Run is enabled.

Such a run ends only by one of:

- normal run completion;
- an explicit operator/Lead stop under existing authority;
- the pre-authorized invocation hard deadline in §3.2, which may terminate and revoke authority but may not advance workflow or release a lease.

The system must define an out-of-band operator notification path for unattended Run deployments. Dashboard attention alone is insufficient when no operator is polling the dashboard.

The notifier may be implementation-specific, but its failure must be visible. Notification does not itself stop, relaunch, or advance the run.

## 5. Unattended publication

`Run + PUBLISH_IF_CLEAN` can result in publication without a contemporaneous human.

Therefore:

- the Lead may request `PUBLISH_IF_CLEAN`;
- only the operator capability may grant it;
- the authorization must bind to the same legality inputs as publication itself;
- steering mode must never synthesize the authorization;
- changing to Run does not upgrade a non-publishable projection into a publishable one.

## 6. Tests

Release tests must prove:

- an agent shell cannot invoke the operator confirmation capability;
- a model Lead cannot raise its mode without operator approval;
- a Lead can lower its mode;
- a model Lead cannot grant `PUBLISH_IF_CLEAN`;
- unknown/missing/new side-effect classes require confirmation in Walk;
- observed primitive effects cannot exceed declarations unnoticed;
- budget/envelope/deadline exhaustion stops auto-run;
- repeated no-progress actions stop auto-run;
- changing steering mode still does not change legality/gates/transitions.
