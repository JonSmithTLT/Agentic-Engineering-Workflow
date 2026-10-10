# F9-A MS0: the OpenCode 2.0.18 live-delivery probe, evidence

The evidence behind [ADR-0017](../../0017-coordination-messages.md) D8's transport section: how OpenCode 2.0.18
admits a Lead input posted to a running session, measured on 2026-10-09 and 2026-10-10 on both MS0 hosts (Windows, and
the Rocky 8 reference host under AEW's bubblewrap layout). The findings are in [`probe-results.md`](probe-results.md).

| File | What it is |
|---|---|
| [`probe-results.md`](probe-results.md) | The findings, case by case (P1 to P9), the decision rule applied, and P5's response bodies as an id-only table |
| [`table-windows.md`](table-windows.md), [`table-rocky8.md`](table-rocky8.md) | Per run, per host: admission against the step in flight (P1, P2), delivered order and statuses (P3 to P7), the shell tool's timeout (P9) |
| `summary-windows.json`, `summary-rocky8.json` | Per-run metrics, one object per run (62 per host): each post's times, status and admission, the delivered order, the tools' fates, the session-loss reads |
| `src-excerpts.txt` | OpenCode 2.0.18's own source around the delivery-relevant definitions, extracted from the pinned Windows binary (named by its version and sha256) |

**How they were made.** The probe is `tests/live/f9a_delivery_probe/` (run by hand, case by case; never collected in
CI). `summarize.py --json` wrote the two JSON files, `table.py` the two tables, `p5_table.py` the P5 table in
`probe-results.md`, and `src_excerpts.py` the excerpts. The probe ran outside the repository, on a frozen export of AEW at
`2baf431`. The copy in `tests/live/` keeps its cases and drivers unchanged; it differs in how it is run (it imports the
installed `aew`, finds the binary through the adapter, and writes under an output directory it is given) and in naming
the binary by its sha256 in each run's result. Its summarizers reproduce the JSON files and tables here from the raw
runs.

**What is not here, by design.** The raw run trees (about 400 MB per host): each run's event stream, posts with their
full bodies, model requests, adapter telemetry, server log and private OpenCode state. They carry host paths (every
event's location, the run directories, the binary's path), so only the summaries, tables and excerpts above are
committed. A fuller copy of the raw data, with at least every run's posts and event stream, is kept privately.

**Sanitized.** These files hold no host path and no user name. `tests/unit/test_f9a_probe_evidence.py` checks them
and the probe's source, in CI's fast tier: no drive path, no UNC prefix, no home or user directory (POSIX `home`,
macOS `Users`, `root`, a home-relative path, or the Windows `APPDATA` and `USERPROFILE` variables), no path under a
POSIX system root (`tmp`, `var`, `opt`, `srv`, `mnt`, `run`, `etc`), and no `location`, `directory` or `binary` key.
The test's `HOST_PATHS` lists the exact patterns. Locally before committing, it also checks
for no word of the local account's name, nor of any other account the probe ran under that the author names in
`AEW_EVIDENCE_PRIVATE_WORDS`.
