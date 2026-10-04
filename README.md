# Agentic-Engineering-Workflow
Provider-neutral, contract-first engineering workflow for AI coding agents. AEW adds durable project state, Ticket/Story/Epic orchestration, review and verification gates, provenance, resumable execution, and pluggable tool/model capabilities without coupling the process to a single harness.

## Status

**Documentation map: [`docs/README.md`](docs/README.md).** It says what AEW is building towards, which documents govern, and where everything else lives.

- **Specification:** the frozen set `aew-frozen-2026-09-25` in `docs/` (Workflow Contract v0.7, Knowledge Contract v0.4, manifest, SPT remediation appendix), pinned by the tag `aew-spec-frozen-2026-09-25` and guarded by `tests/test_spec_pin.py`.
- **Done:** M1 (the serial control engine and CLI, `aew`), M2 (Epic/Story hierarchy, non-mutating Tickets), M3 (OpenCode V2 as the first agent harness, with no AEW credential in any model's hands; tag `aew-m3-accepted-2026-10-01`) and ADR-0011 (hot and cold control state).
- **In progress: M4**, mutating concurrency above 1 ([`m4-ambiguity-report.md`](docs/implementation/m4-ambiguity-report.md)). M4-A (one dispatch predicate), M4-B (OS filesystem containment on Linux) and M4-C (workspaces for N > 1) are built; M4-D (the integration queue and the transaction outbox) is in progress.
- What is implemented, staged or only designed: [`implementation-status.md`](docs/implementation/implementation-status.md). Deferred work and its gates: [`future-work.md`](docs/implementation/future-work.md).

| Start with | For |
|---|---|
| [`docs/guides/quickstart.md`](docs/guides/quickstart.md) | Install, initialize, run one Ticket end to end |
| [`docs/guides/lead-guide.md`](docs/guides/lead-guide.md) | How work flows in AEW, for a Lead: risk classes and their gates, the Ticket lifecycle, the command for each step (`aew guide`) |
| [`docs/guides/opencode.md`](docs/guides/opencode.md) | Running AEW with OpenCode: configuration, the Lead's TUI, harness runs, containment |
| [`docs/implementation/adr/`](docs/implementation/adr/) | Implementation decisions (ADR-0001 to ADR-0013) |
| [`docs/implementation/testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md) | Test lanes, what CI requires before merge, the containment lane |

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
