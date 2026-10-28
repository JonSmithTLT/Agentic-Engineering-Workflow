**D-A's first publication (2026-10-26):** the adopted design text is published, sanitised and generated, under
[`docs/contracts/`](../../../contracts/README.md): 50 copies, each listed in its `MANIFEST.json` and each markdown or
YAML copy headed with its position and source. `tests/unit/test_contracts_published.py` checks every copy against the
manifest; the generator and its own check stay in the private design workspace, which runs them against `main`. Nobody
edits a copy by hand: a later adoption joins the set in a publication pull request of its own.

The row's "No requirement ids or text in the repository" is the generated reference's rule (`AGENTS.md` §7), which
`tests/unit/test_reference.py` still holds for `docs/reference/`. The adopted text, its requirement ids included, is now
published under `docs/contracts/`, by the operator's decision D-A.

**A follow-on from #288's quick check** (CLEAR at `1b4bf54b`), for the next publication pull request to fix and list:
m1, the planted test `test_discoverys_conventions_are_not_ours_only_where_listed` (`tests/unit/test_ci_tools.py`)
checks a third file one layer below the `NOT_OURS` filter, so it does not fail when the exemption is widened. The fix:
extract the filter as `ours(label, refs)`, call it from `reduced_readers`, and assert in the planted test that
`ours("tests/integration/test_sample.py", refs)` keeps a `docs/contracts` reference while `ours` for
`tests/integration/test_resume.py` drops it.
