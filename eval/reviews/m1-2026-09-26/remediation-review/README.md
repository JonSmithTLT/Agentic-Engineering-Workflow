# Remediation re-review evidence

Reviewed revision: e7e723c9ff4d5dbcd1d9c11af374e170e86758a1.

The original external probe file in ../reproductions/ was run unchanged. Its SHA-256 is recorded in REPORT.md. Follow-up probes are separate in test_neighbor_paths.py; they assert safe expected behavior and use only disposable temporary repositories.

Run with Python >=3.11 and the declared dev dependencies, setting PYTHONPATH to the target repository's src, tests, and tests/helpers directories. Use `python -m pytest -q -p no:cacheprovider test_neighbor_paths.py`.

Logs:
- suite.txt: complete remediated repository suite.
- original-probes.txt: the original 12 reviewer probes.
- neighbors.txt: initial five neighboring cases (including two directory-to-file variants).
- retired-invocation.txt: sixth neighboring case, retiring a live integration verifier.
- replayed-publication.txt: strengthened replay probe, confirming DONE/publication.
- baseline-comparison.txt: replacement sequence against original 1d914cb, rejected at second candidate preparation.

Some logs precede the replay probe's final strengthening. Disposable fixture credentials printed by pytest are redacted. No implementation source or original probe was changed.
