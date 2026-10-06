# A2 — Launch-Failure Recovery Safety Amendment v0.1

**Status:** APPROVED AMENDMENT  
**Date:** 2026-10-05  
**Amends:** `AEW_Bounded_Recovery_Policy_Design_v0.1`, R5-3 only

## 1. Core correction

`launch_failed` is not sufficient evidence that no process started and no side effects occurred.

R5-3 may relaunch only after AEW positively establishes that the previous run cannot continue and did not perform meaningful work.

The relaunch rule is therefore fail-closed.

## 2. Required termination proof

Before a relaunch, the supervisor must establish that the failed run is no longer live.

Acceptable proof requires all applicable supervisor/custody mechanisms to agree that the process/session is terminated or never acquired execution custody.

A timeout, stale heartbeat, missing poll response, or `launch_failed` label alone is not proof.

If termination cannot be established, R5-3 is ineligible and the Lead receives attention.

## 3. Credential rotation

Before creating the replacement run:

1. revoke the failed run's credential/capability;
2. confirm revocation is effective according to the normal credential mechanism;
3. mint a fresh credential for the new run;
4. bind the new credential to the new run id.

A credential must never be shared by the failed and replacement runs.

Failure to confirm revocation blocks automatic relaunch.

## 4. Positive no-side-effect proof

Automatic relaunch requires positive evidence that the failed run did not cross the "work began" boundary.

At minimum, all of the following must hold:

- no tool invocation/event beyond startup/control-plane initialization;
- no successful credential-authorized project action;
- no evidence/report/discovery output;
- no workspace mutation;
- no authoritative-ref mutation;
- no external side effect recorded by a declared primitive/tool channel;
- workspace digest/base binding matches dispatch.

If AEW cannot observe a relevant effect channel, automatic relaunch is not permitted for a failure that may have reached that channel.

The proof is recorded with the recovery decision/result.

## 5. Transient reason allow-list

R5-3 no longer means:

> retry `launch_failed` except named forbidden reasons.

It means:

> retry only an explicitly allow-listed transient failure reason.

The initial allow-list must be narrow and implementation-owned. Examples MAY include a supervisor/process-start race or a temporary local harness startup transport failure where termination and no-side-effect proof are both available.

The following classes are not automatically relaunchable unless separately adopted:

- containment/security refusal;
- credential denial or capability mismatch;
- policy/configuration error;
- quota/budget exhaustion;
- authentication/authorization failure;
- provider-wide or endpoint-wide outage;
- incompatible harness/model configuration;
- unknown reason.

Unknown reasons fail closed.

## 6. Circuit breaker

Automatic relaunch is additionally subject to a circuit breaker.

The breaker trips when the same launch-failure reason exceeds a configured threshold across a bounded window, either:

- per harness/provider endpoint; or
- project-wide when the cause is shared.

Recommended initial behavior:

```text
trip after 3 eligible launch failures in 5 minutes
```

Once tripped:

- `relaunch_launch_failed` is treated as disabled for the affected scope;
- no extra dispatch/load is generated automatically;
- an operator/Lead attention item names the reason and affected scope;
- recovery resumes only after explicit operator reset or a later adopted health rule.

The breaker state is operational safety state, not project workflow authority.

## 7. Relaunch history

The relaunch record must bind:

- failed run id;
- termination proof;
- credential revocation reference;
- no-side-effect proof;
- transient reason code;
- circuit-breaker state;
- new run id.

Both runs remain visible in invocation history.

## 8. Tests

Release tests must prove:

- a still-live old process prevents relaunch;
- a stale heartbeat alone cannot authorize relaunch;
- old credential is revoked before a new credential is minted;
- any project-side tool event makes R5-3 ineligible unless classified as startup-only by an explicit contract;
- workspace mutation prevents relaunch;
- unknown failure reason prevents relaunch;
- credential/config/quota/security failures do not auto-relaunch;
- the circuit breaker prevents repeated automatic load amplification;
- the replacement run always gets a new run id and credential.
