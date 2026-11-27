**Cited, not implemented.** Three gaps in the hosted evidence proof (`.github/workflows/evidence-proof.yml`), seen on
2026-11-26 on #612, #615, #616, #617 and #625 (and #623 for the third). This note records them; it fixes none. Each
is meant to be fixed by a future E3 pull request.

- **(a) A re-run of failed jobs only can never pass `verify`.** `verify` downloads the plants' artifacts with
  `pattern: '*plant-*-attempt-${{ github.run_attempt }}*'` (`evidence-proof.yml:310`), and each plant names its
  artifact by the attempt it ran in (`:141`, `:166`). A re-run of failed jobs re-runs the controls and `verify` but not
  the plants that passed, so `verify` finds no plant of its own attempt (`FileNotFoundError: ... 'published'`). Seen on
  run 45800512984 (#615) and run 45801371845 (#617), attempt 2 of each: the controls passed, `verify` failed. Only a
  full re-run passes (45801371845's attempt 3; 45800512984's attempt 4). Meant to fix it: `verify` reads the newest
  attempt of each plant, or the proof refuses a partial re-run and says to re-run all jobs.
- **(b) The cancel controls' 20-minute wait for hosted runners fails under ordinary contention.**
  `tools/ci/prove_cancel_evidence.py` waits at most `RUNNER_ALLOCATION_SECONDS` (20 minutes) for runners to be
  assigned to both controlled lanes, then fails with "timed out waiting for a hosted runner to be assigned to both
  controlled lanes". Seen on #615 (run 45791565649, job 139811616529; run 45800512984, attempts 1 and 3), #616 (run
  45806007100; run 45819492026, attempts 1 and 2), #617 (run 45801371845, attempt 1) and #625 (run 45881517239,
  `run-cancel-control (manual)`). The same controls passed once the queue was quiet: 45801371845's attempt 3 (#617,
  18:15 to 19:03 UTC), 45800512984's attempt 4 (#615, 22:44 UTC) and 45819492026's attempt 3 (#616, 23:31 UTC). Meant
  to fix it: a wait that tells runner contention from a stuck target, and says so, rather than failing the proof as if
  a control had failed.
- **(c) A full re-run of a `ci.yml` run leaves `assurance` failing.** After the re-run, the attempt-1 `lane-report-*`
  artifacts stay listed but their stored file returns 404 (`Failed to GetSignedArtifactURL: ... (404) Not Found:
  artifact not found`), and `assurance` downloads every `lane-report-*` (`ci.yml:459`, `:464`), so it stops on that
  one every time. Seen on run 45831204645 (#612; attempts 2 and 3, artifact 15135839858,
  `lane-report-evidence-lane-report-Linux-integration-8-step-5-attempt-1`) and run 45838021798 (#623, attempt 2).
  The fix there was a fresh run, through a merge of `main` with the operator's go-ahead. Meant to fix it: `assurance`
  reads only the reports of each lane's newest attempt.
