# Agentic-Engineering-Workflow
Provider-neutral, contract-first engineering workflow for AI coding agents. AEW adds durable project state, Ticket/Story/Epic orchestration, review and verification gates, provenance, resumable execution, and pluggable tool/model capabilities without coupling the process to a single harness.

## Status

- **Specification:** frozen set `aew-frozen-2026-09-25` in `docs/` (Workflow Contract v0.7, Knowledge Contract v0.4, manifest, SPT remediation appendix). It is pinned by the tag `aew-spec-frozen-2026-09-25` and guarded by `tests/test_spec_pin.py`.
- **Implementation:**
  - **M1** (a deterministic state engine and CLI, `aew`: one serial Ticket lifecycle through controlled integration, Lead-session loss and reconstruction from durable state) and **M2** (Epic/Story hierarchy, non-mutating Tickets, Investigator/Researcher/Planner roles) are accepted and merged.
  - **M3** (OpenCode V2 as the first agent harness: roles run as harness sessions, with no AEW credential in any model's hands) is implemented and documented on `impl/m3-opencode` (PR #5); the operator's own TUI session and the independent review remain. Start with [`m3-reviewer-brief.md`](docs/implementation/m3-reviewer-brief.md).
  - What is implemented, staged or only designed: [`implementation-status.md`](docs/implementation/implementation-status.md). Deferred work: [`future-work.md`](docs/implementation/future-work.md).

| Document | Contents |
|---|---|
| [`docs/implementation/quickstart.md`](docs/implementation/quickstart.md) | Install, initialize, run one Ticket end to end |
| [`docs/implementation/lead-guide.md`](docs/implementation/lead-guide.md) | How work flows in AEW, for a Lead: risk classes and their gates, the Ticket lifecycle, the command for each step (`aew guide`) |
| [`docs/implementation/opencode.md`](docs/implementation/opencode.md) | Running AEW with OpenCode: configuration, the Lead's TUI, harness runs, containment |
| [`docs/implementation/acceptance.md`](docs/implementation/acceptance.md) | Acceptance scenarios and how to run them |
| [`docs/implementation/implementation-status.md`](docs/implementation/implementation-status.md) | Implemented / Staged / Designed |
| [`docs/implementation/adr/`](docs/implementation/adr/) | Implementation decisions (persistence, snapshots, state machine, integration, authority, role cards, hierarchy, non-mutating work, the harness boundary, execution profiles, hot/cold control state) |
| [`docs/implementation/ambiguity-report.md`](docs/implementation/ambiguity-report.md) | Spec gaps and their operator-approved dispositions |
| [`docs/implementation/review-response-2026-09-26.md`](docs/implementation/review-response-2026-09-26.md) | Independent M1 review: every finding, its fix, commit and regression evidence |
| [`docs/implementation/review-response-2026-09-27.md`](docs/implementation/review-response-2026-09-27.md) | Independent M2 review: every finding, its fix, commit and regression evidence |
| [`docs/implementation/m3-reviewer-brief.md`](docs/implementation/m3-reviewer-brief.md) | M3 independent review brief: claims, evidence, risk areas, known limits |
| [`docs/implementation/testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md) | Test lanes, what CI requires before merge, concurrency and isolation rules, nightly lane, budgets |

## Development

```bash
python -m venv .venv && . .venv/bin/activate   # Python >= 3.11
pip install -e ".[dev,parallel]"    # `parallel` (pytest-xdist) is optional
python -m pytest -q                  # all tests, serially (always valid)
python -m pytest -m acceptance -q    # acceptance scenarios only
python -m pytest -n auto -m "not serial" -q && python -m pytest --lane serial -q   # all tests, in parallel
python -m pytest --lane regression -n auto -q                                   # one CI lane
```

Test lanes, the CI merge gate and the rules for adding tests are in [`docs/implementation/testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md).
