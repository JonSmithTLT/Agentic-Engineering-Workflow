# Agentic-Engineering-Workflow
Provider-neutral, contract-first engineering workflow for AI coding agents. AEW adds durable project state, Ticket/Story/Epic orchestration, review and verification gates, provenance, resumable execution, and pluggable tool/model capabilities without coupling the process to a single harness.

## Status

- **Specification:** frozen set `aew-frozen-2026-09-25` in `docs/` (Workflow Contract v0.7, Knowledge Contract v0.4, manifest, SPT remediation appendix). It is pinned by the tag `aew-spec-frozen-2026-09-25` and guarded by `tests/test_spec_pin.py`.
- **Implementation:** milestone M1, the first serial vertical slice. It is a deterministic state engine and CLI (`aew`) that proves one complete serial Ticket lifecycle through controlled integration, destruction of the Lead session, and reconstruction from durable state. It includes the adversarial cases: an unintegrated dependency, stale evidence, and crash/superseded-Lead safety.

| Document | Contents |
|---|---|
| [`docs/implementation/quickstart.md`](docs/implementation/quickstart.md) | Install, initialize, run one Ticket end to end |
| [`docs/implementation/acceptance.md`](docs/implementation/acceptance.md) | Acceptance scenarios and how to run them |
| [`docs/implementation/implementation-status.md`](docs/implementation/implementation-status.md) | Implemented / Staged / Designed |
| [`docs/implementation/adr/`](docs/implementation/adr/) | Implementation decisions (persistence, snapshots, state machine, integration, authority, role cards) |
| [`docs/implementation/ambiguity-report.md`](docs/implementation/ambiguity-report.md) | Spec gaps and their operator-approved dispositions |
| [`docs/implementation/review-response-2026-09-26.md`](docs/implementation/review-response-2026-09-26.md) | Independent M1 review: every finding, its fix, commit and regression evidence |
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
