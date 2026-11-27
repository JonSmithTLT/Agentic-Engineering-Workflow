**The evidence scanner's verified archive is kept in the Actions cache (2026-11-27).** `main`'s push run
46048405164 (head `92dfe68`) went red with every test passed: in job 140676088838, `regression 2/3 (ubuntu-latest)`,
all three bounded attempts to download gitleaks 8.28.0 from its release host were refused with HTTP 403 within 6 s,
the lane had no scanner, and `tools/ci/stage_evidence.py --reports-only` rightly withheld its unscanned report, so
`assurance` failed ("linux: regression: shard 2/3 has no report", then "never ran" for its 108 passing tests). The
bundle is that job's log and its 217-byte `lane-report` artifact, which holds only the inventory saying the scan was
unavailable. Shards 1 and 3 downloaded normally. It did not recur: of 442 scanner installs in the lane jobs of 12 `ci`
runs on 2026-11-27 (494 job logs searched for "evidence scanner download attempt"), this job's was the only one that
retried. A refusal is not a stall, so the bounded retry of 2026-11-26 could not end it; the next step that note named
is now built.

The lane action asks the installer for a cache entry (`install_evidence.py --cache-entry`: a directory under
`RUNNER_TEMP` and a key naming the platform, the archive with its version, and the pinned digest), restores it before
the installer runs, and after a miss saves it once the installer reported the scanner available. A warm job downloads
nothing. The cache is trusted no more than the release host: the installer checks the cached bytes against the pinned
digest on every install, extracts only the bytes it checked, discards a mismatch and downloads afresh, and never keeps
bytes that failed the check. A lane with no verified scanner still withholds its report. A cold cache (the first run
after the pin changes, or after eviction) still downloads, with the bounded retry. Tests:
`test_a_cached_scanner_archive_is_installed_only_when_it_matches_the_pinned_digest`
(`tests/unit/test_evidence_states.py`) and
`test_a_lane_restores_the_pinned_scanner_from_the_cache_before_installing_and_saves_only_a_verified_one`
(`tests/unit/test_ci_tools.py`). This is a setup failure before pytest, so it stays out of the flake register, as the
2026-11-26 note says.

**What remains**: E3 stays open, as it watches CI for load-sensitive timing. Of this defect, nothing; if a cold job's
download is refused again, a second pinned and checksum-verified source is the next step.
