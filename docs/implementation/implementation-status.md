# AEW Implementation Status

This is operational metadata (WC Appendix C). It does not replace the workflow state of any project that uses AEW. It uses the three states from WC §"Status and authority": **Implemented**, **Staged** and **Designed**. A row is Implemented only when the listed evidence exists and passes on both Windows (Python 3.13) and Linux (Python 3.11). The acceptance IDs are listed in `acceptance.md`.

**Spec set:** `aew-frozen-2026-09-25`. **Last updated:** 2026-09-25, M1 complete through step 11.

| Capability | Status | Acceptance evidence / next action |
|---|---|---|
| AEW v0.7 design + KC v0.4 | Implemented (frozen, pinned) | Tag `aew-spec-frozen-2026-09-25`, `docs/spec-pin.yaml`, `tests/test_spec_pin.py` |
| Persistent Lead + reconstruction | Implemented | AT-1 (session destroyed mid-flight, caches deleted, `aew resume`, operator takeover, reconcile, completion) |
| Crash-safe, stale-writer-resistant control state | Implemented | AT-4a/4b; ADR-0001, ADR-0005 |
| Command/skill interaction layer | Staged | Complete CLI primitives. The `/aew …` harness commands come with the OpenCode adapter (M3). |
| AEW Knowledge Contract | Implemented (M1 slice) | Manifest, logical names, current state, handoff/checkpoint, Ticket/Story/Epic records, plan revisions, provenance, guardrail/build-test policy, `init`/`status`/`resume`, cache loss, existing-authority project |
| Ticket/Story/Epic work model | Ticket Implemented; Story/Epic Staged | Story/Epic records, parent links, derived roll-up, inherited-policy representation. Story gates, closeout and promotion come in M2. |
| Role archetypes + role-card catalog | Implemented (M1 scope) | ADR-0006; `tests/unit/test_roles.py`, `test_role_cards.py`. Dispatch of investigator/researcher/planner cards comes in M2; per-card output contracts after M1. |
| Project-control adapter | Designed | M3 (OpenCode) |
| R1 Reviewer | Implemented (scripted roles) | AT-1, AT-5; reviewer packs exclude implementer reasoning |
| Independent Verifier | Implemented (scripted roles) | AT-1, AT-3, AT-6 |
| OpenCode provider path | Designed | M3; the operator will install OpenCode locally (preferably in WSL) |
| Specialist skills | Staged | Cards name skills; loading them is harness work (M3) |
| Host/container tools | Designed | SPT Epic "Toolchain Readiness" (dogfood) |
| Workbench Capability Contract | Staged | Cards and archetypes carry capability names; authority-sensitive capabilities are enforced. Provider resolution and health come in M6. |
| Remote validation provider | Designed | — |
| Work graph / dynamic scheduler | Graph Implemented; scheduler Designed | AT-2; the scheduler comes in M5 |
| Concurrent mutation isolation | Staged | Per-Ticket worktrees and a serialized, CAS-published integration exist. The cap is hard 1 until M5. |
| Controlled integration | Implemented | AT-2, AT-4a (publish crashes), ADR-0004 |
| Verification-failure classification | Implemented | AT-6 |
| Validation provenance | Implemented | AT-1, AT-3; evidence records what/who/when/against/how/result/evidence plus role card |
| Project guardrails | Implemented (deterministic subset) | Protected/generated paths, Ticket scope, review triggers (optionally naming a card); dependency rules are representable but not enforced |
| Build/test impact analysis | Designed | — |
| SCM/Jira enforcement | Designed | — |
| Model-diverse review | Designed | R2/R3 are recordable in review evidence; policy and evaluation are later work |
| Lease-expiry automatic Lead takeover | Designed | Future ADR (ambiguity report A2) |
