# AEW Pre-F15.2 Amendment Set v0.1

**Status:** APPROVED AMENDMENT SET  
**Date:** 2026-10-05  
**Applies to:**  
- `AEW_Crawl_Walk_Run_Steering_Design_v0.1`
- `AEW_Bounded_Recovery_Policy_Design_v0.1`
- `AEW_Run_Health_Projection_Design_v0.1`

## 1. Authority and precedence

This amendment set refines the approved designs without reopening their core architectural decisions.

Where this set conflicts with the approved v0.1 documents, this set controls.

The following are **required before F15.2 ships**:

1. operator-only authority for confirmations and autonomy increases;
2. relaunch safety that positively excludes a still-live or side-effecting prior run;
3. separation of legality binding from operational attribution so operational tuning does not create false `STALE_POLICY`.

The steering and recovery hardening in Amendments A1 and A2 are also release requirements for their respective features. The health items in H1 are required before health is treated as production-grade operator telemetry, but they do not block unrelated F15.2 work unless F15.2 consumes health.

## 2. Preserved architectural decisions

This set does not change the previously approved principles:

- health remains a projection, not a store or workflow authority;
- steering remains one confirmation predicate over already-legal `auto_runnable` actions;
- recovery remains bounded and does not create a new failure taxonomy;
- no model may manufacture authority by changing policy or confirming its own constrained action;
- heuristics do not advance workflow;
- no timeout releases a lease by itself;
- deferred R5 recovery rows remain deferred.

## 3. Documents

- **A1 — Steering Authority and Execution Envelope Amendment**
- **A2 — Launch-Failure Recovery Safety Amendment**
- **A3 — Policy Binding and Digest Amendment**
- **H1 — Run Health Projection Implementation Note**

## 4. Required implementation order

1. Implement A3 digest separation first, because A1 and A2 depend on the distinction between legality binding and operational attribution.
2. Implement A1 operator capability separation before exposing `aew confirm`, `aew lead mode`, or unattended Run behavior.
3. Implement A2 termination/credential/side-effect proof before enabling `recovery.relaunch_launch_failed: 1`.
4. Implement H1 before relying on STALLED/UNRESPONSIVE as a production operator signal.

## 5. Release gates

F15.2 must not ship a mode-changing or confirmation surface reachable from an agent shell.

Automatic launch-failure relaunch must not ship until the implementation can prove the previous run is terminated and non-side-effecting.

Operational policy changes must not invalidate in-flight stage legality merely because an attribution/telemetry setting changed.
