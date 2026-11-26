Batch 3 builds what the adopted skills design already places, and nothing else (ADR-0006, amendment 2026-11-26).

- **`technical-writing` ships** from AEW's install, labelled unevaluated, after its public-text check, byte for byte from its public candidate (`SKILL.md` and `references/`, without `evals/`); its files match the candidate's own `evals/runtime-manifest-0.2.1.json`.
- **`code_reviewer` offers three more** as `optional_skills`: `technical-writing` (the designer's decision of 2026-11-06 on the Lead's skills and document work, (c); E167) and `python-development` and `c-development` (the Lead's two items, accepted in that decision; this row's Work). The `c_reviewer` card is unchanged.
- **The `technical_writer` card** (E167, closed by the same pull request) is on the implementer archetype with `technical-writing` in `skills:`.
- **Measured, not capped** (bytes, before and after, on the built-in cards):
  - a `code_reviewer` run's copy grows from 33,147 to 68,951 bytes, for five skills where it had two; its system text's skill lines grow from 273 to 333 bytes; the three descriptions the `skill` tool now also lists are 729 bytes together;
  - a `technical_writer` run's copy is 15,995 bytes, of which `SKILL.md`, which the run is told to load, is 7,138;
  - the Lead guide's staffing section grows from 571 to 739 bytes (read on demand, not in the core), and the typed `resume`'s result by 50 bytes for the twelfth card (7,228 to 7,278 on the seeded project of `tests/integration/test_messaging_off_outputs.py`).
  - No budget or cap exists for worker packs yet (E368), so these are recorded and not held to one.
  - The listing's and a load's cost in tokens is not measured here: that takes a model run (the live test, `tests/live/test_skills_live.py`), and E135 takes cost from paired runs.

**What remains** on this row, each waiting on the operator:

- **`agent-security-review` and `security-control-validation`.** The designer's decision of 2026-11-04 (`designer-decisions-2026-11-04-skills-by-fit.md`, section 4, a record outside this repository) gives their fit as `security_reviewer`; no line in this repository places them, and the fit is judged in the pull request that builds it. They are held by #563's N2, recorded in this row's note of 2026-11-25: each one's runtime reference says the 2026-10-19 ruling file "was not located", and those bytes are pinned by its 0.2.0 runtime manifest, so the wording changes with the operator's update from the final drafts before either ships.
- **`empirical-evaluation` and `ci-evidence-triage`.** Neither the operator's mapping nor the designer's decisions say which card offers them; batch 2's mapping covered the planning and testing group only. No card is invented here.
- **`frontend-design`.** No built-in card fits it, as this row's Notes say.
- **A foundational skill in `skills:` for each role whose job has a method.** The designer's decision of 2026-11-06 (`designer-decisions-2026-11-06-lead-skills-mcp-and-document-work-v2.md`) accepts the idea and names no skill for any role, and its cost, in every run of that card, is to be measured first, which takes a model run.

None of what was built, and none of what remains, waits on E135's evaluation runner: qualification is owed before anything beyond the personal alpha and gates no batch.
