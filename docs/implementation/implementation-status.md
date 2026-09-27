# AEW Implementation Status

This is operational metadata (WC Appendix C). It does not replace the workflow state of any project that uses AEW. It uses the three states from WC §"Status and authority": **Implemented**, **Staged** and **Designed**. A row is Implemented only when the listed evidence exists and passes on both Windows (Python 3.13) and Linux (Python 3.11). The acceptance IDs are listed in `acceptance.md`.

**Spec set:** `aew-frozen-2026-09-25`. **Last updated:** 2026-09-27. **M2 (Epic/Story hierarchy, non-mutating Tickets, Investigator/Researcher/Planner dispatch) is implemented on `impl/m2-hierarchy` and awaits independent review** (`m2-reviewer-brief.md`; ADR-0007, ADR-0008). M2 local verification: Windows/Python 3.13 649 collected, 644 passed, 5 pinned skips, assurance PASS (Linux via CI); the M1 suites, probes and walk are unchanged and green. M3 (OpenCode) has not started. M1 is complete. All findings of the independent M1 review, and of the focused re-review of its remediation, are resolved (`review-response-2026-09-26.md`). All three reviewers' probe files pass unchanged (22/22) and are preserved as regressions in `tests/regression/`. Full suites: Linux/Python 3.11 603 passed; Windows/Python 3.13 598 passed, plus 5 pinned POSIX-only skips. Since 2026-09-27 CI runs the suite as parallel lanes per OS behind a single `assurance` merge gate, which proves every collected test ran exactly once and passed. It takes about 5 minutes, down from about 46; see `testing-and-ci-strategy.md`.

| Capability | Status | Acceptance evidence / next action |
|---|---|---|
| AEW v0.7 design + KC v0.4 | Implemented (frozen, pinned) | Tag `aew-spec-frozen-2026-09-25`, `docs/spec-pin.yaml`, `tests/test_spec_pin.py` |
| Persistent Lead + reconstruction | Implemented | AT-1 (session destroyed mid-flight, caches deleted, `aew resume`, operator takeover, reconcile, completion) |
| Crash-safe, stale-writer-resistant control state | Implemented | AT-4a/4b; ADR-0001, ADR-0005; review probes M1/M8; seeded adversarial walk with the invariant oracle (`tests/regression/`) |
| Command/skill interaction layer | Staged | Complete CLI primitives. The `/aew …` harness commands come with the OpenCode adapter (M3). |
| AEW Knowledge Contract | Implemented (M1 slice + M2 hierarchy) | Manifest, logical names, current state, handoff/checkpoint, Ticket/Story/Epic records, plan revisions, provenance, guardrail/build-test policy, `init`/`status`/`resume`, cache loss, existing-authority project |
| Ticket/Story/Epic work model | Implemented (M2) | ADR-0007, ADR-0008; AT-8..AT-13; `tests/integration/test_hierarchy.py`, `test_non_mutating.py`; `tests/regression/test_m2_compositions.py`, `test_hierarchy_walk.py`; oracle rules 6–13. The parent state is derived; closeout and cancellation are Lead decisions; parent gates are evaluated against the parent snapshot; the non-mutating path (dispatch, attempts, observation workspaces, record freshness, `INPUT_STALE`, evidence-only completion); moves, promotion, dependency edits; fail-closed ancestor plan bindings |
| Role archetypes + role-card catalog | Implemented (M2 scope) | ADR-0006 (+ M2 amendment): investigator/researcher/planner dispatchable with built-in default cards; the executor card and `expected_kind` are pinned at dispatch. Per-card output-contract payload schemas: Designed |
| Hierarchical context packs, resume and status | Implemented (M2) | Hierarchy section in every pack; investigator/researcher/planner packs; parent reviewer/verifier packs with every child's own integrated change; `aew work tree`; resume shows attempts, inputs, acknowledgements and per-parent next actions (AT-11) |
| Read-only concurrency | Implemented (observation workspaces) | One detached observation per read-only invocation; optional `non_mutating_concurrency` policy (AT-12). Shared observations: not used (stricter than WC §8.1 permits) |
| Plan-driven child materialization | Designed | Children are created by the Lead; a plan does not generate them |
| Backlog import (SPT remediation backlog) | Staged | AT-13 proves a generic backlog of that shape is representable and executable; importing the real backlog follows M2's acceptance |
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
