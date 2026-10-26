**D-A's first publication (2026-10-26):** the adopted design text is published, sanitised and generated, under
[`docs/contracts/`](../../../contracts/README.md): 50 copies, each listed in its `MANIFEST.json` and each markdown or YAML
copy headed with its position and source. `tests/unit/test_contracts_published.py` checks every copy against the
manifest; the generator and its own check stay in the private design workspace, which runs them against `main`. Nobody
edits a copy by hand: a later adoption joins the set in a publication pull request of its own.
