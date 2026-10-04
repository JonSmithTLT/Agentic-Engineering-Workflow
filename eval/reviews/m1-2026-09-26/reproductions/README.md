# Running the independent regression probes

The assertions express safe expected behavior. On reviewed commit `1d914cb`, all twelve probes fail for the defects documented in `../REPORT.md`. They are deliberately separate from the repository's existing tests.

Use Python >=3.11 with the repository's declared development dependencies. Point the environment at the exact source revision and its existing test helpers:

```bash
AEW_REVIEW_REPO=/path/to/Agentic-Engineering-Workflow
export PYTHONPATH="$AEW_REVIEW_REPO/src:$AEW_REVIEW_REPO/tests:$AEW_REVIEW_REPO/tests/helpers${PYTHONPATH:+:$PYTHONPATH}"
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider /path/to/AEW-M1-review-2026-09-26/reproductions/test_review_regressions.py
```

All mutations and forced process crashes operate on temporary fixture repositories. The tests do not change implementation files. Linux filemode behavior is required for the executable-bit probe. The saved output redacts disposable fixture credentials printed by pytest's assertion diagnostics.

The review used a local clone in `/tmp/aew-review-checkout`, with Python 3.11 dependencies installed separately in `/tmp/aew-review-deps`; these temporary paths need to be recreated after an environment reset.
