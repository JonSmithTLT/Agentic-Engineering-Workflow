# AEW Implementation Status

This is operational metadata (WC Appendix C). It does not replace the workflow state of any project that uses AEW. It uses the three states from WC §"Status and authority": **Implemented**, **Staged** and **Designed**. A row is Implemented only when the listed evidence exists and passes on both Windows (Python 3.13) and Linux (Python 3.11). The acceptance IDs are listed in `acceptance.md`.

**Spec set:** `aew-frozen-2026-09-25`. **Last updated:** 2026-09-26. M1 is complete. All findings of the independent M1 review, and of the focused re-review of its remediation, are resolved (`review-response-2026-09-26.md`). All three reviewers' probe files pass unchanged (22/22) and are preserved as regressions in `tests/regression/`. Full suites: Linux/Python 3.11 603 passed; Windows/Python 3.13 598 passed, plus 5 pinned POSIX-only skips. Since 2026-09-27 CI runs the suite as parallel lanes per OS behind a single `assurance` merge gate, which proves every collected test ran exactly once and passed. It takes about 5 minutes, down from about 46; see `testing-and-ci-strategy.md`.

| Capability | Status | Acceptance evidence / next action |
|---|---|---|
| AEW v0.7 design + KC v0.4 | Implemented (frozen, pinned) | Tag `aew-spec-frozen-2026-09-25`, `docs/spec-pin.yaml`, `tests/test_spec_pin.py` |
| Persistent Lead + reconstruction | Implemented | AT-1 (session destroyed mid-flight, caches deleted, `aew resume`, operator takeover, reconcile, completion) |
| Crash-safe, stale-writer-resistant control state | Implemented | AT-4a/4b; ADR-0001, ADR-0005; review probes M1/M8; seeded adversarial walk with the invariant oracle (`tests/regression/`) |
| Command/skill interaction layer | Staged | Complete CLI primitives. The `/aew …` harness commands come with the OpenCode adapter (M3). |
| AEW Knowledge Contract | Implemented (M1 slice) | Manifest, logical names, current state, handoff/checkpoint, Ticket/Story/Epic records, plan revisions, provenance, guardrail/build-test policy, `init`/`status`/`resume`, cache loss, existing-authority project |
| Ticket/Story/Epic work model | Mutating Ticket Implemented; non-mutating Ticket and Story/Epic Staged | Story/Epic records, parent links, derived roll-up, inherited-policy representation. Non-mutating Tickets can be recorded but are not assigned or integrated in M1. Their dispatch path, Story gates, closeout and promotion come in M2. |
| Role archetypes + role-card catalog | Implemented (M1 scope) | ADR-0006; `tests/unit/test_roles.py`, `test_role_cards.py`; review probes M7 (operator pins). Dispatch of investigator/researcher/planner cards comes in M2; per-card output contracts after M1. |
| Card-level path restriction (`restrict.paths`) | Designed | Review N1: the schema rejects it (fail closed); in M1, path limits come from Ticket scope + guardrails |
| Project-control adapter | Designed | M3 (OpenCode) |
| R1 Reviewer | Implemented (scripted roles) | AT-1, AT-5; reviewer packs exclude implementer reasoning |
| Independent Verifier | Implemented (scripted roles) | AT-1, AT-3, AT-6 |
| OpenCode provider path | Designed | M3; the operator will install OpenCode locally (preferably in WSL) |
| Specialist skills | Staged | Cards name skills; loading them is harness work (M3) |
| Host/container tools | Designed | SPT Epic "Toolchain Readiness" (dogfood) |
| Workbench Capability Contract | Staged | Cards and archetypes carry capability names; authority-sensitive capabilities are enforced. Provider resolution and health come in M6. |
| Remote validation provider | Designed | — |
| Work graph / dynamic scheduler | Graph Implemented; scheduler Designed | AT-2; the scheduler comes in M5 |
| Concurrent mutation isolation | Staged | Per-Ticket worktrees and a serialized, CAS-published integration exist. The cap is hard 1 until M5, and counts live workspaces whatever their state (review M2). |
| Controlled integration | Implemented | AT-2, AT-4a (publish crashes), ADR-0004 (+ 2026-09-26 amendment); review probes B1/B2/M1/M6; `tests/integration/test_worktree_sync.py` |
| Verification-failure classification | Implemented | AT-6 |
| Validation provenance | Implemented | AT-1, AT-3; evidence records what/who/when/against/how/result/evidence plus role card |
| Project guardrails | Implemented (deterministic subset) | Protected/generated paths, Ticket scope, review triggers (optionally naming a card); dependency rules are representable but not enforced |
| Build/test impact analysis | Designed | — |
| SCM/Jira enforcement | Designed | — |
| Model-diverse review | Designed | R2/R3 are recordable in review evidence; policy and evaluation are later work |
| Lease-expiry automatic Lead takeover | Designed | Future ADR (ambiguity report A2) |
