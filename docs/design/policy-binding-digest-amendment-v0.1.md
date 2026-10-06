# A3 — Policy Binding and Digest Amendment v0.1

**Status:** APPROVED AMENDMENT — REQUIRED BEFORE F15.2  
**Date:** 2026-10-05  
**Amends:** Health §5, Steering §6/§8, Recovery §5, and any typed-surface rule that treats the entire execution-policy digest as one staleness binding.

## 1. Problem

Execution policy currently contains settings with different semantic effects:

- legality/authority-affecting policy;
- operator steering/confirmation policy;
- recovery enablement policy;
- health/telemetry thresholds.

Treating all of them as one staleness digest causes operational changes to invalidate in-flight legal work.

That is too broad.

## 2. Two digest classes

AEW SHALL distinguish:

### 2.1 `legality_digest`

Contains only inputs whose change may alter whether an action is legal, gated, authorized, or judgment-bearing.

A mismatch may produce `STALE_POLICY` and requires legality recomputation before execution.

Examples include, where applicable:

- gate policy;
- risk/assurance policy;
- authority/capability bindings;
- review/verification obligations;
- conditional authorization predicates;
- primitive legality rules;
- other policy explicitly declared legality-affecting.

### 2.2 `operational_digest`

Contains settings that control execution behavior or observation but do not themselves change workflow legality.

Examples:

- health thresholds;
- health calibration/caching parameters;
- steering mode;
- operator notification settings;
- auto-run envelope/budget parameters that stop execution but do not make an illegal action legal;
- `recovery.relaunch_launch_failed` enablement and circuit-breaker parameters, except where a specific recovery action snapshots the setting as part of its own authorization.

Operational changes are recorded for attribution and consumed on the next safe evaluation boundary. They do not by themselves generate `STALE_POLICY` for an already-committed legal stage step.

## 3. Per-action binding

Every staged action records:

- `legality_digest`;
- `operational_digest`;
- revision;
- authority generation;
- any action-specific conditional authorization digest.

Before execution:

- legality digest mismatch => recompute legality / `STALE_POLICY` under existing rules;
- operational digest mismatch => recompute operational behavior at the next safe boundary and record the new digest;
- action-specific authorization mismatch => stop according to that authorization's contract.

## 4. Safe boundary

A safe boundary is after the current committed primitive finishes and before selection/execution of the next primitive.

Operational changes do not retroactively alter a committed primitive.

Examples:

- changing `walk -> run` does not interrupt an executing action; it changes confirmation behavior on the next projection tick;
- changing a health threshold changes future health interpretation without invalidating an in-flight stage;
- disabling launch-failure relaunch prevents a future relaunch attempt but does not invalidate the legal stage action that was already running.

## 5. Recovery nuance

A recovery action that depends on an operational setting must snapshot and attribute that setting when the recovery decision is made.

For example, R5-3 may execute only if:

- `recovery.relaunch_launch_failed == 1` at recovery evaluation time; and
- all R5-3 eligibility predicates pass.

If the operational setting changes before the relaunch primitive commits, reevaluate the recovery action. This reevaluation is not a general stage `STALE_POLICY`; it is recovery-policy invalidation for that pending recovery action.

## 6. Steering nuance

Steering mode is never part of legality.

A mode change:

- affects the next confirmation decision;
- never changes `AVAILABLE`, `BLOCKED`, `UNKNOWN`, or `auto_runnable`;
- never invalidates an already-running primitive merely because its operational digest changed.

An autonomy increase still requires operator capability under A1.

## 7. Health nuance

Health thresholds and calibration parameters are operational/observational only.

Changing them:

- may change the next computed health projection;
- must not invalidate workflow legality;
- must not abort a stage bundle;
- must be visible in the health object's attribution.

## 8. Schema requirement

Policy schema must classify every field as one of:

```text
legality_affecting
operational
```

Unclassified new policy fields fail schema validation until explicitly classified.

A field cannot silently default to operational merely because its semantics are unknown.

## 9. Tests

Release tests must prove:

- health threshold changes do not generate stage `STALE_POLICY`;
- steering mode changes do not invalidate an in-flight primitive;
- gate/authority policy changes do generate legality staleness;
- recovery setting changes affect only pending recovery behavior;
- every policy field is classified;
- new unclassified fields fail validation;
- history records both digests for attribution.
