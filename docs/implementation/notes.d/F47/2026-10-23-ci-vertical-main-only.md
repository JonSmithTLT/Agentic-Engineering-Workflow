**The vertical UAT is frozen as a baseline, and its workflow no longer runs on pull requests** (the designer's ruling
of 2026-10-23; the trigger change is the operator's, the same day).

- **The outcome stays.** [`vertical-uat.md`](../../vertical-uat.md) §1 is a release requirement. The instrument is to
  be re-derived from the adopted actions, with each ideal-path step citing the action and the surface that serves it.
  The workflow and the test module are retired in the pull request that lands the re-derived one, not before.
- **Until then nothing amends `IDEAL_PATH` or the fallbacks for the old surfaces.** The exception is a row that
  `tests/unit/test_surface_map.py` moves to EXISTS once its proposed command is built.
- **The Lead's reading, not the ruling's words:** two clauses no longer bind new work:
  - this row's "each slice re-runs the `vertical` lane and puts its ledger diff in its pull request";
  - the register's §1 gate "Before feature work resumes, and before any release", in its clause "every vertical-path
    slice having re-run the `vertical` lane and shown its ledger diff".

  The plan they belong to (vertical-path plan v15) is history. A slice that wants its ledger diff can still dispatch
  `vertical` on its branch. The gate itself is the operator's to restate when the re-derived instrument lands.
- **`vertical.yml` runs on pushes to `main` and on dispatch only.** It is red on `main`, so on a pull request its
  result said nothing about that pull request. `main`'s runs keep the ledger's time series:
  - a running one is never cancelled;
  - when pushes land close together, GitHub keeps only the newest pending one, as for every push run on `main`.
- **`VERTICAL_MODE` stays `shadow`,** and the page's thresholds are unchanged.
