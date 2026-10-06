# AEW Run Health Projection Design v0.1

**Status:** APPROVED  
**Date:** 2026-10-05  
**Owner:** `engine/harness_ops.harness_status` plus existing renderers  
**Implements:** R3 / U1  
**Authority class:** Additive observability projection. No new workflow state machine, store, or authority path.

## 1. Purpose

Provide one truthful, bounded view of run health so the Lead and operator can distinguish active work, waiting, stalls, harness unresponsiveness, crashes, and completed runs without creating an autonomous supervisor.

Health is recomputed from existing local telemetry on read. It is advisory wherever the source is heuristic. Only already-deterministic run/liveness facts may drive existing mechanical reactions.

## 2. Non-goals

This design does not:

- create `agent status` as a separate subsystem;
- persist a health store;
- make STALLED an engine authority state;
- automatically interrupt, nudge, relaunch, or redispatch a stalled run;
- infer semantic progress from model reasoning;
- replace run status, invocation state, or Ticket state.

U7 automatic stall recovery remains deferred.

## 3. Health vocabulary

`health.state` is one of:

| State | Basis | Confidence |
|---|---|---|
| `UNKNOWN` | invocation names a run but no `run.json` exists inside the existing startup grace | high |
| `STARTING` | run status is starting, or start observed before execution begins | high |
| `ACTIVE` | run is running, heartbeat is fresh, and no blocking/stall condition wins | high |
| `BLOCKED` | deterministic wait on permission/inbox/disposition or a blocked role report | high |
| `STALLED` | running with a fresh heartbeat but an open tool/step exceeds policy threshold | medium for tool; low for step |
| `UNRESPONSIVE` | heartbeat remains fresh while harness API polling fails and events stop | medium |
| `CRASHED` | terminal crash/launch failure; observer-level `lost` remains surfaced as its existing run status/attention reason | high |
| `ENDED` | ended with evidence, ended without evidence, or terminated | high |

Precedence for rendering a running run is:

`BLOCKED` > `STALLED` > `UNRESPONSIVE` > `ACTIVE`.

Existing terminal/lost status remains authoritative over advisory running-health interpretations.

## 4. Progress and stall interpretation

Meaningful activity is derived from the adapter event stream: tool activity, step boundaries, inbox delivery, permission reply, and equivalent existing run events.

A long tool call and a long model step are distinct:

- open tool call: `tool.called` without a subsequent completion/progress event;
- open model step: `step.started` without `step.ended` and without a tool call that explains the silence.

A long model step is rendered as `thinking for N min` before the step threshold. Silence alone must not be treated as proof that the model is stuck.

## 5. Policy

Health thresholds live in execution policy and are part of the policy digest.

Recommended v1 shape:

```yaml
health:
  stalled:
    tool_floor_s: 300
    step_s: 600
    check_duration_multiplier: 2.0
```

Effective tool threshold:

`T_tool = max(tool_floor_s, check_duration_multiplier × longest_recent_configured_check_duration_s)`

Until a project has calibrated healthy check durations, STALLED is advisory and reports low confidence.

The execution policy may tighten or loosen thresholds, but threshold changes do not alter engine legality or Ticket state.

## 6. Projection contract

`harness_ops.harness_status()` is the single computation point. Each run gains:

```json
{
  "health": {
    "state": "ACTIVE | BLOCKED | STALLED | UNRESPONSIVE | ...",
    "confidence": "high | medium | low",
    "source": ["run_status", "heartbeat", "events"],
    "since": "<timestamp>",
    "detail": {
      "tool": "<optional tool name>",
      "duration_s": 0,
      "pending_permission": "<optional>",
      "poll_errors": 0,
      "threshold_s": 0
    }
  }
}
```

Fields may be omitted when not applicable. Consumers must not recompute a competing answer.

## 7. Consumers

The same health object is rendered through:

1. `aew harness status`;
2. typed `harness_status`;
3. `aew harness wait`;
4. `resume`;
5. dashboard `/runs` and `/overview.attention`;
6. `ActionProjection.runs[]`.

`harness wait` must wake non-terminally when a waited run first becomes STALLED and return the tool/duration reason. A caller may choose to continue waiting. A STALLED wake does not terminate or revoke the run.

`resume` and dashboard attention include STALLED, UNRESPONSIVE, CRASHED, lost, and ended-without-evidence conditions using existing attention semantics.

## 8. Reactions

| Observation | Automatic behavior | Judgment owner |
|---|---|---|
| lost / crash / launch failure | existing credential revocation and reconciliation only | Lead decides relaunch/redispatch |
| blocked permission | wake wait + attention | Lead/operator replies or sends |
| STALLED | wake wait + attention only | Lead may stop, nudge, or continue waiting |
| UNRESPONSIVE | attention only, plus existing supervisor deadlines | Lead may stop |
| long think below threshold | render only | none |

Heuristic health must never directly advance workflow or create/release authority.

## 9. Telemetry

No new telemetry is required for v1.

Two additive improvements are permitted:

- sub-second event timestamp `t`;
- explicit `tool.ended` using the harness tool-call id.

Neither field becomes project authority.

## 10. Conformance tests

The implementation must demonstrate:

- the historical healthy corpus produces zero false STALLED events at the configured production threshold;
- a seeded long healthy check below `T_tool` remains ACTIVE with explanatory detail;
- a seeded long think below `T_step` renders thinking, not STALLED;
- the known long shell hang is detected and names the tool/duration;
- crash/lost observations still use existing deterministic status behavior;
- every surface returns/renders the same computed health object;
- no engine transition, guard, or gate branches on heuristic STALLED.

## 11. Evaluation and future use

M4-H/F19 may use health as a measured signal. M5 adaptive concurrency may later consume it as one contraction signal, but this design grants no scheduler authority.

Automatic stall recovery requires a separate later adoption after U1 is observed in real use.
