# H1 — Run Health Projection Implementation Note v0.1

**Status:** REQUIRED IMPLEMENTATION NOTE  
**Date:** 2026-10-05  
**Applies to:** `AEW_Run_Health_Projection_Design_v0.1`

This note tightens implementation details without changing the approved architectural decision that health is a projection over existing telemetry and is not project authority.

## 1. Terminal vocabulary passes through

Health must not create a second vocabulary for terminal run outcomes.

For terminal/non-running conditions, render the existing run status/outcome directly.

Examples:

```text
launch_failed
crashed
lost
ended_with_evidence
ended_without_evidence
terminated
```

`health.state` is primarily for non-terminal interpretation:

```text
unknown
starting
active
blocked
stalled
unresponsive
```

Consumers must tolerate future/unknown health values by rendering `unknown` plus raw status/detail rather than failing closed into a misleading known state.

### 1.1 Startup grace

`unknown` during startup grace means run metadata exists but custody/status is not yet established.

After startup grace expires:

- if existing observer rules prove the supervisor/run was never established or is gone, surface the existing `lost`/unconfirmed failure outcome;
- otherwise keep `health.state=unknown` with explicit reason until a deterministic source resolves it.

Do not invent a new terminal state solely to leave UNKNOWN.

## 2. ACTIVE semantics

`active` means:

> the run is live and no stronger blocked/stalled/unresponsive condition currently applies.

It does **not** mean the agent is semantically making useful progress.

Health output adds:

```text
last_progress_at
last_event_at
```

The distinction must be visible to the operator.

## 3. Robust stall calibration

Do not derive `T_tool` from the single longest recent check duration.

Use a bounded healthy sample, excluding runs/checks that:

- ended by kill;
- ended by timeout;
- were manually aborted as hung;
- are otherwise marked invalid for calibration.

Recommended estimator:

```text
baseline = p95(healthy_check_durations over last 50 valid checks)
T_tool = clamp(
    max(tool_floor_s, check_duration_multiplier * baseline),
    min=tool_floor_s,
    max=tool_cap_s
)
```

Initial suggested values:

```yaml
health:
  stalled:
    tool_floor_s: 300
    step_s: 600
    check_duration_multiplier: 2.0
    calibration_window: 50
    calibration_percentile: 95
    tool_cap_s: 1800
```

The exact defaults remain tunable operational policy, not legality policy.

No single hung historical check may permanently inflate the threshold.

## 4. Incremental projection computation

The dashboard/status path must not reparse the full event stream every poll.

Implementation should maintain an in-process/local cache keyed by run id with:

- event-file offset or event sequence watermark;
- last parsed event;
- derived open tool/step state;
- `last_event_at`;
- `last_progress_at`;
- poll-error counters/source revision.

On read:

1. stat/check the source;
2. parse only events after the watermark;
3. update the derived cache;
4. recompute the projection.

The cache is disposable local acceleration. It is not project state and may be rebuilt from the underlying telemetry.

## 5. Durable source for poll failures and `since`

The projection must name the existing local run record/adapter counters that own `poll_errors`.

If the current adapter counter is not persisted with enough timestamp information to derive `since`, add an additive local telemetry field/event such as:

```text
poll_error_started_at
last_poll_error_at
```

or an equivalent adapter event.

`since` must come from recorded telemetry, not from "the first dashboard poll that noticed it."

Likewise, state-entry time for STALLED/BLOCKED should be derivable from event timestamps plus the threshold, not from UI observation time.

## 6. Edge-triggered STALLED wake

`harness wait` wakes at most once per transition into a medium/high-confidence STALLED condition.

Required behavior:

- ACTIVE -> STALLED(tool-level, medium confidence): emit one non-terminal wake;
- repeated polls while still STALLED: no duplicate wake;
- STALLED -> ACTIVE -> STALLED: a new wake is allowed;
- low-confidence step-level stall: render attention/detail but do not wake the Lead automatically.

This reduces premature model intervention on long thinking.

## 7. Tool vs step stall confidence

Tool-level stall detection may produce `stalled` when the configured tool threshold is crossed.

Step-level silence remains lower confidence and should be rendered as:

```text
thinking for N min
```

until a separately configured stronger threshold/criterion is met.

A low-confidence step-level heuristic must not be phrased to a model Lead as a definitive "agent stalled" command-like instruction.

## 8. Unattended Run interaction

Health detection does not itself authorize recovery of a Run-mode invocation.

For unattended Run deployments:

- STALLED/UNRESPONSIVE attention must feed the operator notification channel required by Steering Amendment A1;
- the invocation remains subject to A1's pre-authorized hard lifetime deadline;
- expiry of that hard deadline may terminate the process and revoke its credential as an authority-reducing safety action;
- no lease is released because of stall or deadline timeout;
- no run is relaunched because of stall or deadline timeout;
- any future automatic nudge/recovery remains a separate U7 adoption.

## 9. Tests

Production tests must cover:

- robust percentile calibration with one poisoned/hung historical check;
- calibration cap;
- cache rebuild gives the same projection as incremental parsing;
- repeated dashboard polls do not reread the full stream;
- `since` survives process/UI restart because it derives from telemetry;
- ACTIVE exposes `last_progress_at`;
- tool-level STALLED wakes once per entry;
- low-confidence step-level stall does not wake;
- unknown future `health.state` renders safely;
- terminal run outcomes are passed through rather than renamed into a second taxonomy.
