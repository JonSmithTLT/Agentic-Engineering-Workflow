# Lower-bound qualification: scoring rubric (lbq-1)

Fixed before any run and hashed into the preregistration (`scoring.rubric_sha256`). Governing text: the
agent-effectiveness synthesis §13.4 (the lower-bound lane and its eight behaviours) and the implementation delta's D3,
on the agent-effectiveness adoption branch (PR #150). Metric names and versions here are the ones the preregistration
lists; the F19 metric module (delta D2) implements them as defined below, and a later change to a definition is a new
version and a new experiment.

## 1. What qualifies a lower bound

A profile qualifies as the lane's lower bound when it passes a **floor** and does not exceed a **ceiling**:

- **Floor** (§2): it completes AEW's bridge handshake and the typed submit path through the pinned harness. A model
  that cannot do this cannot take part in any AEW arm, so measuring it tells AEW nothing.
- **Ceiling** (§4): it still shows the weak-worker behaviours. A model that shows none of the eight on the seeded
  tasks cannot tell AEW whether its scaffolding helps a weak worker: it is `not_a_lower_bound`, and the next-cheaper
  profile is tried (synthesis §13.4).

The result is the profile record's `qualification_state` (`profiles.yaml`; `eval/aew_eval/profiles.py` derives it):
`unavailable` → `unqualified` → `floor_failed` | `floor_passed` → `not_a_lower_bound` | `qualified`.

## 2. The floor

The live lane's real-model test, `tests/live/test_opencode_model_live.py::test_a_free_model_carries_out_real_launch_contracts`,
with the profile's model (`AEW_LIVE_OPENCODE_MODEL`) and, for a paid profile, its provider variable
(`AEW_LIVE_PROVIDER_KEY_ENV`). Each trial dispatches a real implementer run of a planned Ticket through the production
OpenCode adapter: the model receives AEW's launch contract and acts through the run's bridge with `aew` commands.

- **A trial passes** when its implementer run ends `ended_with_evidence`, its evidence includes an
  `implementation_report` (the typed submit path), and the run's bridge recorded at least one request (the handshake).
- **The floor passes** when at least one of two trials passes. AEW's own assertions in the test (credential custody,
  the effective model, invariants) must hold in every trial; a trial that breaks one is an AEW defect, not the
  model's result, and leaves the floor not established (`qualify.py floor` reports `aew_side_failure`).
- The trials' records (`AEW_LIVE_RESULTS`) and their harness state (the test's `--basetemp`) are kept.

The floor is F32's live-lane qualification of the profile, not an F19 cell: it is recorded in the profile record, and
the ceiling cells run only for a profile whose floor passed.

## 3. The oracles are exercised before freezing

`qualify.py check` scores each case's hidden oracle twice before the preregistration can freeze: on the seeded
starting point, where exactly the case's criteria fail and every other check passes, and on the reference solution
(private, next to the oracle), where every check passes. It also records the upstream suite's result on the seeded
starting point: the seeded unrelated failure (`test_wikilinks_spaces`) is expected; anything else is recorded as the
environment's before any run.

## 4. The ceiling: the eight behaviours

Each run is one raw cell (`prereg.yaml`). A behaviour is **shown** by a profile when its threshold is met in at least
one valid run. Two kinds of observation:

- **T** (tree-observable): from the run record (its changed paths and the oracle's named checks). `qualify.py score`
  computes these now, using `behaviours.yaml` for the paths.
- **S** (session-observable): from the run's retained harness session database, over the preregistered fields only
  (`arms[raw].config.session_db.fields`: tool names, paths, patterns, the first 300 characters of shell commands, the
  hashes of edit strings; never message text or tool output). The F19 reader (delta D2) computes these.

### Definitions used below

- A **call** is one tool part of the session, in order. A **read** is a `read` call, or a shell command that prints a
  file (`cat`, `type`, `Get-Content`, `head`, `tail`, `more`, `less`, `sed -n`). A **search** is a `grep`, `glob` or
  `list` call, or a shell `grep`, `rg`, `findstr`, `find`, `ls`, `dir`, `Get-ChildItem` or `Select-String`. An **edit**
  is an `edit`, `write` or `patch` call (or a shell redirection into a file).
- **Relevant sources** R: LBQ-1 `markdown/extensions/linkpolicy/rules.py` and `.../__init__.py`; LBQ-2 `.../schema.py`,
  `.../__init__.py`, `.../rules.py`; LBQ-3 `.../__init__.py` and `markdown/core.py`.
- **Test surfaces** T: `tests/test_syntax/extensions/test_link_policy.py` and `.../linkpolicy_support.py` (and
  `.../test_link_policy_docs.py` for LBQ-2).
- **Plausibly useful** U: everything under `markdown/extensions/linkpolicy/`, `docs/extensions/link_policy.md`,
  `docs/extensions/api.md`, `markdown/core.py`, `markdown/extensions/__init__.py`, `markdown/treeprocessors.py`,
  `markdown/util.py`, `markdown/test_tools.py`.
- The **decoy root** is `tools/linkpolicy/`; the **distractors** are the failing `test_wikilinks_spaces.py`, the code it
  is about (`markdown/extensions/wikilinks.py`) and the stale TODO in `markdown/extensions/linkpolicy/__init__.py`.

| # | Behaviour (synthesis §13.4) | Seeded in | Kind | Metric (lbq-1) | Shown when |
|---|---|---|---|---|---|
| 1 | poor repository navigation | all (symptom, not file; code three directories deep) | S | `tool_calls_before_first_relevant_source`: calls before the first read of a file in R (all calls if none); `irrelevant_files_opened`: distinct files read outside R, T and U | ≥ 15 calls before the first relevant read, or ≥ 8 irrelevant files opened |
| 2 | bad search-root selection | all (`tools/linkpolicy/` shares the module names, nearer the root) | T + S | `wrong_root_or_unbounded_search_count`: edits under the decoy root (T); reads under it before the first read under `markdown/extensions/linkpolicy/` (S); searches with no path or the repository root as path (S) | any edit under the decoy root, or ≥ 2 decoy reads before the real module, or ≥ 6 unbounded searches |
| 3 | failure to locate tests/mocks | all (the tests reach the code only through `linkpolicy_support.py`) | S | `tests_found_before_first_edit`: whether a file in T was read before the first edit of a non-test file | false, in a run that edits a non-test file |
| 4 | incomplete cross-file changes | LBQ-2 (option table, validation, processor, docs table, tests) | T | `missed_required_sites`: required sites (`behaviours.yaml`) left unchanged by a run that changed at least one | ≥ 1 |
| 5 | requirement loss on longer tasks | LBQ-3 (four criteria; criterion 1 needs `Markdown.reset()`/`registerExtension`, criterion 4 is documentation) | T | `forgotten_criteria`: LBQ-3 criteria the oracle fails, in a run that ended on its own (not deadline, cost cap or step limit) and met at least one criterion | ≥ 1 |
| 6 | repeated exploration | all (an early `grep` hit in the decoy; definitions split over three modules) | S | `repeated_file_reads`: reads of the same file and range beyond the second; `repeated_tool_ngrams`: distinct 3-grams of consecutive (tool, normalized input) occurring at least twice without overlap | ≥ 1 repeated read, or ≥ 2 repeated 3-grams |
| 7 | weak tool selection | all (every question has a dedicated harness tool) | S | `shell_inspection_share`: share of reads and searches made through the shell rather than `read`/`grep`/`glob` | ≥ 0.5, with at least 6 reads and searches |
| 8 | difficulty recovering after distraction | all (the failing unrelated test; the stale TODO naming the wrong fix) | T + S | `distractor_or_stale_note_actions`: edits to a distractor path (T), and the oracle's `structure: the link policy runs after the inline processor` failing (the stale TODO followed, T); `contradictory_edits`: an edit restoring a file region an earlier edit of the run replaced (equal hashes), or deleting a file the run created (S) | ≥ 1 of either |

The raw arm has no AEW typed helpers, so behaviour 7 is measured as the shell-for-everything pattern; the assisted
arms of the later lanes measure `voluntary_typed_use_rate` instead (synthesis §9).

## 5. Task correctness (secondary)

A run is **task-correct** when its hidden oracle passes and every path it changed (ignoring bytecode and caches,
`behaviours.yaml` `ignored_paths`) is inside the task's scope (`allowed_paths`: the extension, its tests, its
documentation). Correctness is reported per run and per case. It does not decide qualification: a weak model is
expected to fail tasks; the lane needs it to fail them in the ways §4 measures.

## 6. The verdict and the profile record

- Floor failed → `floor_failed`; no ceiling cell runs.
- Floor passed, and at least one behaviour shown (T now, S once the F19 reader scores the retained databases) →
  `ceiling.state: behaviours_shown` with the behaviours named → `qualified`.
- Floor passed, every behaviour's metric computed for every valid run, none shown → `none_shown` →
  `not_a_lower_bound`; the next-cheaper profile is tried under a new experiment id.
- Floor passed, no T behaviour shown and the S metrics not yet computed → the ceiling stays `not_run` (pending) and
  the profile is `floor_passed`.

## 7. Never measured, never kept

No message text or tool output is extracted from a session database; a database is kept for `retention_days`
(180) after its run and then purged by the F19 retention step. No result here is reported as M4-H or treatment-effect
evidence.
