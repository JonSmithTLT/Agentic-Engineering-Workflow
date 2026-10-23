**The vertical UAT is frozen as a baseline, and its workflow no longer runs on pull requests** (the designer's ruling
of 2026-10-23; the trigger change is the operator's, the same day).

- **The outcome stays.** [`vertical-uat.md`](../../vertical-uat.md) §1 is a release requirement. The instrument is to
  be re-derived from the adopted actions, with each ideal-path step citing the action and the surface that serves it.
  The workflow and the test module are retired in the pull request that lands the re-derived one, not before.
- **Until then nothing amends `IDEAL_PATH` or the fallbacks.** So this row's "each slice re-runs the `vertical` lane
  and puts its ledger diff in its pull request" no longer applies to new work.
- **`vertical.yml` runs on pushes to `main` and on dispatch only.** It is red on `main`, so on a pull request its
  result said nothing about that pull request. `main`'s runs keep the ledger's time series, and they are never
  cancelled.
- **`VERTICAL_MODE` stays `shadow`,** and the page's thresholds are unchanged.
