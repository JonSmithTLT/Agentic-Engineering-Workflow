# AEW Implementation Status

This is operational metadata (WC Appendix C). It does not replace the workflow state of any
project that uses AEW. It uses the three states from WC §"Status and authority":
**Implemented**, **Staged** and **Designed**. A row moves to Implemented only when the listed
acceptance evidence exists and passes.

**Spec set:** `aew-frozen-2026-09-25`. **Last updated:** 2026-09-25 (Step 0: spec set pinned).

| Capability | Current | M1 target | Acceptance evidence / next action |
|---|---|---|---|
| AEW v0.7 design + KC v0.4 | Implemented (versioned, frozen, pinned) | — | Tag `aew-spec-frozen-2026-09-25`, `docs/spec-pin.yaml`, `tests/test_spec_pin.py` |
| Persistent Lead + reconstruction | Designed | Implemented | AT-1 (resume after session destruction), AT-4a/4b |
| Crash-safe, stale-writer-resistant control state | Designed | Implemented | Step 3 fault-injection and race suite; AT-4a/4b |
| Command/skill interaction layer | Designed | Staged (CLI primitives) | OpenCode adapter in M3 |
| AEW Knowledge Contract | Designed | Implemented | init/status/resume on fixtures; cache-loss test |
| Ticket/Story/Epic work model | Designed | Ticket Implemented; Story/Epic Staged | Story roll-up, gates and promotion in M2 |
| Project-control adapter | Designed | Designed | M3 (OpenCode) |
| R1 Reviewer | Designed | Implemented (scripted roles) | AT-1, AT-5 |
| Independent Verifier | Designed | Implemented (scripted roles) | AT-1, AT-3, AT-6 |
| OpenCode provider path | Designed | Designed | M3 |
| Specialist skills | Designed | Designed | — |
| Host/container tools | Designed | Designed | SPT Epic "Toolchain Readiness" |
| Workbench Capability Contract | Designed | Designed | M6 plus SPT D2 manifests |
| Remote validation provider | Designed | Designed | — |
| Work graph / dynamic scheduler | Designed | Graph Implemented; scheduler Designed | AT-2; scheduler in M5 |
| Concurrent mutation isolation | Designed | Staged (per-Ticket worktrees, cap = 1) | M5 |
| Verification-failure classification | Designed | Implemented | AT-6 |
| Validation provenance | Designed | Implemented | AT-1, AT-3 |
| Project guardrails | Designed | Implemented (deterministic subset) | Step 7, AT-7 |
| Build/test impact analysis | Designed | Designed | — |
| SCM/Jira enforcement | Designed | Designed | — |
| Model-diverse review | Designed | Designed | — |
| Lease-expiry automatic Lead takeover | Designed | Designed | Future ADR (ambiguity report A2) |
