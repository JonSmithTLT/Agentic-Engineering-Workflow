# Lower-bound qualification lane (`lbq-v1`)

**Status:** prepared and dry-run on 2026-10-10; **the run is the operator's** (it needs a provider credential and
spends money, see "Operator steps"). Experiment id `lbq-v1-deepseek-v4-flash`, `purpose: qualification`.

**Governs:** the agent-effectiveness adoption record
([decisions-2026-10-09](../../../docs/design/decisions-2026-10-09-agent-effectiveness-adoption.md) §9 "Lower-bound
pre-M4-H fixture", §10.3), the synthesis
([§13.4](../../../docs/research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md), the lane and its
eight behaviours; §13.1 profiles as capability classes), the implementation delta's D3 (and D2, the session-database
reader it relies on), and the F19 instrument ([evaluation component design v0.2](../../../docs/design/evaluation-component-design-v0.2.md):
preregistration, attempt ledger, hidden oracles, immutable runs).

## What it establishes

Whether a cheap OpenCode model can serve as the **lower bound** of the agent-effectiveness lanes: the profile
against which "does AEW's deterministic scaffolding amplify a weak worker" is measured later (raw against assisted,
after the M4-H gate). It produces a reusable **profile record** (`profiles.yaml`, `aew/eval-profile/v1`) whose
`qualification_state` is derived from three facts:

1. **availability**: the pinned harness (OpenCode 2.0.18) offers the model;
2. **floor**: the model completes AEW's bridge handshake and the typed submit path (rubric §2: the live lane's
   real-model implementer run ends with an accepted `implementation_report` after at least one bridge request);
3. **ceiling**: it still shows the weak-worker behaviours on seeded tasks (rubric §4: at least one of the eight; a
   model that shows none is `not_a_lower_bound`, and the next-cheaper profile is tried).

Results are qualification and instrumentation evidence only, never M4-H or treatment-effect evidence; Q7's sealed
tasks and the held-out corpus are not used.

## Profiles (and what the dry run found)

Chosen by the lead developer (2026-10-09): lower bound `opencode/deepseek-v4-flash-free` with its stable paid twin
`opencode/deepseek-v4-flash`; backup `opencode/minimax-m2.5-free`; middle profile `openai/gpt-6-luna`. Laguna is a note.

**On 2026-10-10 none of the chosen free models is offered by OpenCode 2.0.18.** The models.dev catalog OpenCode serves
marks `deepseek-v4-flash-free`, `minimax-m2.5-free` and `laguna-s-2.1-free` `deprecated`, and the served catalog
(without a key: 11 free Zen models) does not list them; 2.0.22 behaves the same. Their paid twins and `gpt-6-luna` are
offered. Following the lead's own rule for this case (the paid twin keeps results reproducible when the free tier
goes), the preregistration pins **`opencode/deepseek-v4-flash`** ($0.14 / $0.28 per million input / output tokens,
$0.028 cached). If the operator does not opt in to a paid profile, the alternative is a currently offered free model
picked by the lead (a new experiment id); none of the 11 has a paid twin under the `opencode` provider, and most are
previews or unnamed models.

| Profile | Class | Offered by 2.0.18 | Credential variable | State |
|---|---|---|---|---|
| `lb-deepseek-v4-flash-free` | lower-bound | no (deprecated) | none | `unavailable` |
| `lb-deepseek-v4-flash` (pinned) | lower-bound | yes (variants low, high, max) | `OPENCODE_API_KEY` | `unqualified` |
| `lb-minimax-m2.5-free` | lower-bound | no (deprecated) | none | `unavailable` |
| `lb-minimax-m2.5` | lower-bound | yes | `OPENCODE_API_KEY` | `unqualified` |
| `mid-gpt-6-luna` | mid | yes (variants none to max) | `OPENAI_API_KEY` | `unqualified` |
| `note-laguna-s-2.1-free` | lower-bound (note) | no (deprecated) | none | `unavailable` |

The pinned harness binary: OpenCode 2.0.18 at `%APPDATA%/ai.opencode.desktop/cli/2.0.18/opencode-cli.exe` on the
Windows reference host (sha256 `78f454c0…`), and on the Rocky 8 VM (`~/opencode-2.0.18/…/opencode-cli`, `67d82756…`);
both report `opencode v2.0.18`. The desktop app's bundled 2.0.22 is not used.

## The fixture

**Python-Markdown 3.11.0** (`upstream.yaml`: commit `0ffbf00c`, tree `a4ef60af`, BSD-3-Clause, 480 files, 2.5 MB).
Chosen because it is:

- **independent and public**: nothing of AEW's or of any private project; a provider that retains prompts sees only
  this public code and the seeded files;
- **permissively licensed** (BSD-3-Clause), so the seeded copy can be built and shared freely;
- **the size and shape §13.4 asks for**: several hundred files, with more than one plausible search root for every
  question (`markdown/extensions/`, `docs/extensions/`, `tests/test_syntax/extensions/`, the legacy `tests/extensions/`
  data), and a test helper that lives in the package (`markdown/test_tools.py`);
- **runnable anywhere AEW runs**: standard library only (Python 3.11+), tests with `python -m unittest`, so a model's
  test runs and the hidden oracles need nothing installed.

The base is fetched, never committed (`qualify.py fetch` clones the tag, refuses any other commit or tree, and exports
the tracked files). The seeded files (`fixture/overlay/`, 11 files) are added beside it and never replace an upstream
file: a link-policy extension three directories deep (`markdown/extensions/linkpolicy/`: the extension, its rules,
its option table), its documentation, its tests reaching the code only through a support module, a same-named decoy
nearer the root (`tools/linkpolicy/`), an unrelated failing test (`test_wikilinks_spaces.py`) and a stale TODO
naming the wrong fix.

## The cases

| Case | Family | The task (symptom, not file) | Seeds behaviours |
|---|---|---|---|
| `LBQ-1` | navigation | mixed-case and whitespace-prefixed `javascript:` links get through; fix and add a regression test | 1, 2, 3, 6, 7, 8 |
| `LBQ-2` | cross-file | add a `rel_external` option: option table, validation, processor, documentation, tests | 3, 4, 7 (+1, 2, 8) |
| `LBQ-3` | long horizon | four criteria for `report()` and strict mode; one needs `Markdown.reset()`/`registerExtension`, one is documentation | 5, 6, 8 (+1, 2, 7) |

Each case's hidden oracle lives in the private evaluation root (`cases/<id>/oracle/checks.py`), with a reference
solution beside it; the manifest commits to the oracle's content hash. The oracles are exercised on the seeded start
(exactly the case's criteria fail) and on the reference (every check passes) before freezing.

## Procedure

1. `check`: the dry run (no provider call).
2. `fetch` (a download, with the operator's approval) and `check` again: the oracles validated against the real
   fixture, the upstream suite's baseline recorded, the preregistration's schema checked with real case hashes.
3. `freeze --by NAME`: case, oracle and rubric hashes filled in, the schedule materialized from the seed, written to
   `prereg.frozen.yaml` (commit it with the results).
4. `floor`: two live-lane trials (rubric §2). A profile that fails the floor runs no ceiling cell.
5. `ceiling`: the six preregistered raw cells (3 cases × 2), in schedule order, each registered in the attempt ledger
   before it runs; retries only under the frozen policy; the run stops before the budget would be exceeded.
6. `score`: the tree-observable behaviours now (rubric §4 "T"); the session-observable ones (§4 "S") when the F19
   reader (delta D2) scores the retained session databases.

`qualify.py run --by NAME` does all six in order and stops at the first gate that fails. Run state (the ledger, every
run's scratch directory and **its harness session database**, the floor's records) goes to
`%LOCALAPPDATA%/aew-eval/lbq-v1-deepseek-v4-flash/`, outside every repository; the databases are kept for the
preregistered 180 days for the F19 reader, which may extract only the preregistered fields (tool names, paths,
patterns, command prefixes, edit-string hashes; never message text or tool output).

**Containment.** On Windows the runs are not contained (the scores record `contained: false`): OpenCode's own
permission flow rejects reads outside the work tree (nobody answers its requests), but a shell command could still
read other files of the user. The scratch tree holds only the public fixture, the hidden root is removed from the
environment before anything starts, and the agent's shell gets the curated environment (no provider key). A host
without private material removes the remaining exposure.

## Cost (USD)

| Part | Expected | Bound |
|---|---|---|
| Ceiling: 6 raw runs of `deepseek-v4-flash`, ≤ 80 steps each | ≈ 0.10–0.35 per run, ≈ 0.7–2 in all | 0.75 per run (`cap_usd`); 5.00 for the lane (`budget_usd`, retries included) |
| Floor: 2 live-lane trials (implementer, reviewer, verifier; ≤ 40 steps each) | ≈ 0.1–0.35 per trial | bounded by steps, about 0.7 |
| Optional: the middle profile's floor (`gpt-6-luna`, 2 trials) | ≈ 0.1–0.3 per trial | about 0.6 |

The free tier would have cost nothing, but it is no longer offered.

## Operator steps

See the pull request's description for the exact commands (they name local paths). In short: approve the fixture
download, set `OPENCODE_API_KEY` (an OpenCode Zen key) and `AEW_EVAL_HIDDEN_ROOT` in the shell that runs it, and run
`qualify.py run --by <name>`. Nothing else needs a credential; the agent never sees one.

## Files

| File | What it is |
|---|---|
| `prereg.yaml` | the preregistration (`aew/eval-prereg/v1`), unfrozen |
| `profiles.yaml` | the profile records (`aew/eval-profile/v1`) |
| `rubric.md` | floor, ceiling (the eight behaviours, their metrics and thresholds), correctness, verdict |
| `behaviours.yaml` | the paths the tree-observable behaviours and the scope use |
| `upstream.yaml` | the pinned upstream fixture |
| `fixture/LBQ-*.yaml`, `fixture/overlay/` | the case manifests (`aew/eval-case/v1`) and the seeded files |
| `qualify.py` | the driver: check, fetch, freeze, floor, ceiling, score, run |
