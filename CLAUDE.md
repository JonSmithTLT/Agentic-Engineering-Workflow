@AGENTS.md

# AEW for coding agents: what to know before you change anything

AEW (Agentic Engineering Workflow) is a provider-neutral, contract-first engineering workflow for AI coding agents:
durable project state, Ticket/Story/Epic orchestration, review and verification gates, provenance, and resumable
execution. It is a Python package (`src/aew`, CLI `aew`) plus a dashboard (`web/`).

## Where things are

- **Start at [`docs/README.md`](docs/README.md).** It says what governs, the status of every document, and where the
  project is going (current milestone, next, open gates). Do not search 80 documents for the answer; if the map does
  not answer it, the map needs fixing.
- **What is built:** [`docs/implementation/implementation-status.md`](docs/implementation/implementation-status.md).
  **What is deferred and why:** the register, `docs/implementation/future-work.md`.
- **Implementation decisions:** `docs/implementation/adr/`. A decision changed after adoption is an amendment section
  in the ADR, never a silent edit.
- **Code:** `src/aew/` — `engine/` (the control engine: transitions, gates, dispatch, the integration queue,
  validation), `harness/` (supervisors, process ownership, containment), `policy/`, `knowledge/` (evidence, context),
  `workspace/`, `cli/`, `dashboard/` (the read API), `schemas/`.
- **Tools:** `tools/register.py` (the register), `tools/ci/` (lanes, assurance), `tools/perf/`.

## Authority and escalation

- The **operator** decides product and process; the **designer** writes the designs. The frozen specification in
  `docs/` is pinned (`tests/test_spec_pin.py`) and changes only by adopted amendment.
- Do not reopen an approved design or plan. Escalate only for a contradiction with the frozen contract, a missing
  authority boundary, an unsafe state transition, or an unsatisfiable invariant. Libraries, ids, paths, schemas,
  locking and git plumbing are implementation choices.
- A CLI flag, boolean or reason string is never authorization: a model can produce one. Authority comes from the
  operator's out-of-band channel.
- `web/` belongs to the web developer. Do not change it or chase its CI failures unless asked.

## Docs, the ledger and the register (all test-enforced)

- **Every `.md` and `.yaml` under `docs/`** (except `skills/`) is linked from `docs/README.md`
  (`tests/unit/test_docs_links.py`).
- **Ingesting a design is a hard gate, not a file move.** Every document under `docs/design/` and `docs/research/` is a
  source in `docs/design/requirements-ledger.yaml`, and every heading is accounted for: requirements with stable ids,
  `no_requirements`, or `carried`. A requirement dropped between versions needs an explicit disposition
  (`superseded-by:`, `absorbed-by:`, `rejected:`), never silence. ADRs from 0012 on are ledger sources too.
- **Adopted amendments** are listed in `docs/spec-amendments.yaml` (as an overlay or under `considered`).
- **The register is data.** Edit `docs/implementation/future-work.yaml`, then run `python tools/register.py render`.
  Never edit `future-work.md` by hand. Closed rows move to §9 with the date and what closed them; nothing is deleted.
  What the operator or designer still owes is `docs/implementation/decisions-due.yaml` (rendered by the same
  command; `check` fails when an item goes stale or a question or **Designer** row has none). When a merge stops on
  the register, run `python tools/register.py resolve` (it re-merges the YAML row by row and renders), not a hand
  merge; only the same cell changed on both sides is left to fix.
- **Changes to different rows merge**, so keep the layouts that make it so: the register's pages are rendered as one
  block per row, and `implementation-status.md` is one section per capability with a blank line between every two
  lines, no table and no "last updated" line (`tests/unit/test_docs_merge.py`). The exception is two insertions at one
  place, which git always conflicts on: two rows closed into the same gap of §9's id order, two new rows or
  decisions-due items added at one place, two new capabilities side by side. For the register, `resolve` settles them.
- Before committing docs work: `pytest tests/unit/test_docs_links.py tests/unit/test_requirements_ledger.py
  tests/unit/test_spec_amendments.py tests/unit/test_register.py tests/unit/test_docs_merge.py tests/test_spec_pin.py`.

## Tests

- Lanes, markers and the merge gate: [`docs/implementation/testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md).
  `python -m pytest --lane <lane> -n auto -q` runs one CI lane; `-m acceptance` selects the acceptance scenarios.
- **CI is the matrix** (Linux and Windows, sharded, with a coverage ratchet). Locally, run the tests you touched and
  their neighbours, then push. A full local run is for risky engine changes only.
- **Run long suites from a separate worktree** at the commit under test, so the checkout you edit stays free. Do not
  edit a checkout while its test run is in progress.
- **A worktree's tests need an absolute `PYTHONPATH`** to that worktree's `src` when the venv's `aew` is an editable
  install of another checkout. A relative `PYTHONPATH=src` silently runs the other checkout's code in every test that
  starts `aew` from another directory.
- **On Windows, never open console windows.** Background and test processes use `subprocess.CREATE_NO_WINDOW`; tests
  that need a terminal run on Linux only.
- **Never mark a test xfail or skip it to get green.** A test that fails and then passes on re-run is a defect to
  investigate. A slower test is a regression to find, not a timeout to raise.
- **New behaviour comes with the test that proves it**, named for the guarantee (`test_a_diagnostic_run_never_...`).
  Engine invariants live in `tests/helpers/invariants.py`; extend them when a new state appears.
- Static checks run in CI: Ruff, Pyright and pip-audit (`pip install -e ".[lint]"`). Fix what they report; do not
  silence a rule without a reason in the line's comment.

## Code

- Match the surrounding code: its comment density, naming and idiom. Comments say why, and cite the decision (ADR,
  plan, register id, review finding) when the reason lives elsewhere.
- Errors are typed (`src/aew/errors.py`): a stable `code`, plus a reason code in `details` where one error class covers
  several causes. Tests and operators rely on both. A refusal says what was refused, why, and what to do instead.
- **Reuse work product, not proof.** Evidence is bound to the snapshot it was produced on; a change invalidates the
  proof even when it keeps the work.
- External harness facts: trust the pinned fixture (for example `tests/fixtures/opencode/openapi-2.0.18.min.json`) over
  a harness's current online documentation.

## Git

- Commit and push only when asked. Never rewrite published history; never force-push `main`.
- Never use a bare `git stash`: other sessions share the stash stack. Use a WIP commit instead.
- Use `git -C <path>` rather than `cd` when several checkouts or worktrees are in play.
- **Secret scan before every commit and push, as a gate.** Run gitleaks on its own, never piped and never in the same
  command as the commit, and check its exit code: each changed file before committing
  (`gitleaks dir --no-banner --redact <file>`), and the branch's own commits before pushing
  (`gitleaks git --no-banner --redact --log-opts="origin/main..HEAD --no-merges" .`).
