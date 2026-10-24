@AGENTS.md

# AEW for coding agents: what to know before you change anything

AEW (Agentic Engineering Workflow) is a provider-neutral, contract-first engineering workflow for AI coding agents:
durable project state, Ticket/Story/Epic orchestration, review and verification gates, provenance, and resumable
execution. It is a Python package (`src/aew`, CLI `aew`) plus a dashboard (`web/`).

## Where things are

- **Start at [`docs/README.md`](docs/README.md).** It says what governs, the status of every document, and where the
  project is going. Do not search 80 documents for the answer; if the map does not answer it, the map needs fixing.
- **What is built:** [`implementation-status.md`](docs/implementation/implementation-status.md). **What is deferred and
  why:** the register, [`future-work.md`](docs/implementation/future-work.md). **What the code is:** the generated
  reference, [`docs/reference/`](docs/reference/README.md).
- **Implementation decisions:** `docs/implementation/adr/`. A decision changed after adoption is an amendment section
  in the ADR, never a silent edit.
- **Code:** `src/aew/` — `engine/` (the control engine: transitions, gates, dispatch, the integration queue,
  validation), `harness/` (supervisors, process ownership, containment), `policy/`, `knowledge/` (evidence, context),
  `workspace/`, `cli/`, `dashboard/` (the read API), `schemas/`. **Tools:** `tools/register.py` (the register),
  `tools/reference.py` (the generated reference), `tools/ci/` (lanes, assurance), `tools/perf/`.

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

How each of these is done is in [`docs/README.md`](docs/README.md), "Keeping this map true".
- **Every `.md` and `.yaml` under `docs/`** (except `skills/`) is linked from `docs/README.md`.
- **Ingesting a design is a hard gate, not a file move:** every requirement goes into the requirements ledger, and a
  dropped one gets an explicit disposition, never silence.
- **The register is data.** Edit `future-work.yaml` and run `python tools/register.py render`; never edit the rendered
  pages by hand. A note on an existing row is a file (`python tools/register.py note <id>`), never an edit of its
  Notes cell. A merge that stops on the register is settled with `python tools/register.py resolve`, not by hand.
  `python tools/register.py show <id>` prints a row with its notes.
- **`docs/reference/` is generated from the code.** A pull request that changes what it enumerates runs
  `python tools/reference.py render` and commits the result ([its README](docs/reference/README.md)).

## Tests

The lanes, the CI tiers, the static checks and the local commands are in
[`testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md).
- **CI is the matrix.** Locally, run the tests you touched and their neighbours, then push. Do not edit a checkout
  while its test run is in progress.
- **Never mark a test xfail or skip it to get green.** A test that fails and then passes on re-run is a defect to
  investigate. A slower test is a regression to find, not a timeout to raise.
- **Fix what the static checks report;** do not silence a rule without a reason in the line's comment.
- **New behaviour comes with the test that proves it**, named for the guarantee (`test_a_diagnostic_run_never_...`).
  Engine invariants live in `tests/helpers/invariants.py`; extend them when a new state appears.
- **A worktree's tests, and `tools/reference.py`, need an absolute `PYTHONPATH`** to that worktree's `src` when the
  venv's `aew` is an editable install of another checkout. A relative `PYTHONPATH=src` silently runs the other
  checkout's code.
- **On Windows, never open console windows** (`subprocess.CREATE_NO_WINDOW`).

## Code

- Match the surrounding code: its comment density, naming and idiom. Comments say why, and cite the decision (ADR,
  plan, register id, review finding) when the reason lives elsewhere.
- Errors are typed (`src/aew/errors.py`): a stable `code`, plus a reason code in `details` where one error class covers
  several causes. Tests and operators rely on both. A refusal says what was refused, why, and what to do instead.
- **Reuse work product, not proof.** Evidence is bound to the snapshot it was produced on; a change invalidates the
  proof even when it keeps the work.
- **A new command or typed tool ships with its surface-map entry and honours it** in the same pull request (operator,
  2026-10-12). What the entry holds and how the test proves it are in
  [`surface-map.md`](docs/implementation/surface-map.md).
- **Derive, don't restate** (operator, 2026-10-12). Every fact has one owner. Its consumers derive it from the owner's
  accessor and never restate it by hand: restating a fact is a defect. Every plan names the facts it consumes and their
  owners.
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
