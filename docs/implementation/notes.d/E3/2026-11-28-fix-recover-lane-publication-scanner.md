**A passing lane retries an unavailable evidence scanner before it prepares its report (2026-11-28, PR #562).** The
2026-11-27 note (PR #659) left one case: a cold cache (the first jobs after a pin change, which all start together and
miss, eviction, or a restore that times out after its 1-minute bound) while the release host refuses or stalls for
the whole of the installer's bounded window at job start. A failing lane already had a second chance, through
`publish-evidence`'s own `--scanner-only` install; a passing lane had none, so it withheld its report and `assurance`
failed with every test passed. The lane action now runs `install_evidence.py --scanner-only` once more after pytest
and collection both succeeded and only when the first install reported no scanner, roughly the pytest run's length
later. It goes through the same cache path and digest check as every install, so it adds no source and no bypass; it
is `continue-on-error`, so it cannot fail a lane, and its time comes from the publication budget the priority and full
bundles would have spent (`PUBLICATION_BUDGET_S`, `tests/helpers/bounds.py`), whose steps never run on a passing lane.
`SCANNER_AVAILABLE` takes the retry's result when it ran and the first install's otherwise. A scanner the retry
recovered is saved to the Actions cache like one the first install got after a miss (review of #562, m1), so the cold
cache it exists for does not stay cold. Test:
`test_passing_lane_retries_an_unavailable_scanner_before_preparing_its_report`
(`tests/unit/test_ci_tools.py`).

**What remains**: as the 2026-11-27 note says, E3 stays open for load-sensitive timing. Of this defect, a cold cache
with the release host down both at job start and after pytest; a second pinned and checksum-verified source is still
the next step if that is ever seen.
