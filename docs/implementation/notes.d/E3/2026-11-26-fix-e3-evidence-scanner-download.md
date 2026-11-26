**The evidence scanner's download is retried, bounded (2026-11-26).** Each lane installs gitleaks in
`tools/ci/install_evidence.py`, from its pinned release, with one `curl` attempt. On 2026-11-26 that attempt stalled
with 0 bytes for its whole 20 s on three Windows shards: run 45831204645, `regression 1/3 (windows-latest)`, and run
45838021798, `integration 10/14` and `integration 12/14 (windows-latest)`. Each lane then had no scanner and rightly
withheld its lane report, so `assurance` failed closed ("shard N/M has no report") although every test had passed.

The fix keeps the gate and makes getting the scanner reliable: up to 3 attempts, 2 s and 4 s apart. Each attempt ends
after 10 s below 1 KiB/s (a stall) or 20 s in all, and is bounded at 25 s, so the whole is at most 81 s. In a lane it
comes out of the job's absolute test deadline; the scanner-only installs of `publish-evidence` and the cancel record
have no such deadline, so there it adds to the step's run time. Whatever is finally downloaded is still checked against the pinned digest, a mismatch is not retried, and
a scanner that fails every attempt is still reported unavailable, so the lane still withholds its report. Tests:
`test_a_scanner_download_that_times_out_once_is_retried_and_still_checksum_verified` and
`test_a_scanner_download_that_fails_every_bounded_attempt_still_reports_the_scanner_unavailable`
(`tests/unit/test_evidence_states.py`). These are setup failures before pytest, so they stay out of the flake register,
which records tests and sessions (the 2026-11-11 note).

**What remains**: E3 stays open, as it watches CI for load-sensitive timing, which is ongoing. Of this defect, nothing:
if a lane still finds no scanner after every attempt, a cache of the verified binary across jobs (`actions/cache`,
keyed on the version and digest) is the next step, and it was not built because the observed failure was a stall
that a bounded retry ends.
