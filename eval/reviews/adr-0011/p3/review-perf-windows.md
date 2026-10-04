| Criterion | Measured | Verdict |
|---|---|---|
| H1 flat: hot state at 3,000 / at 250 completed | 1.048x (<= 1.25x) | pass |
| H1 flat: history share of hot state at 3,000 | 7.6% (<= 20%) | pass |
| H2 flat: `lead show`, 3,000 minus 250 | +0.178 s (<= +0.25 s) | report |
| H2 flat: `status`, 3,000 minus 250 | +0.255 s (<= +0.25 s) | report |
| H2 flat: `work tree`, 3,000 minus 250 | +0.220 s (<= +0.25 s) | report |
| H2 flat: `resume`, 3,000 minus 250 | +0.371 s (<= +0.25 s) | report |
| H2 flat: `gate show`, 3,000 minus 250 | +0.155 s (<= +0.25 s) | report |
| H2 flat: `context pack`, 3,000 minus 250 | +0.074 s (<= +0.25 s) | report |
| H2 flat: `harness status`, 3,000 minus 250 | +0.022 s (<= +0.25 s) | report |
| H2 flat: `checkpoint (commit path)`, 3,000 minus 250 | +0.025 s (<= +0.25 s) | report |
| H2 flat: `dispatch (work dispatch)`, 3,000 minus 250 | +0.036 s (<= +0.25 s) | report |
| H2 flat: `review ingest`, 3,000 minus 250 | +0.059 s (<= +0.25 s) | report |
| H2 flat, paired (6 rounds): `lead show`, 3,000 minus 250 | +0.011 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `status`, 3,000 minus 250 | +0.004 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `work tree`, 3,000 minus 250 | +0.007 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `resume`, 3,000 minus 250 | -0.002 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `gate show`, 3,000 minus 250 | -0.001 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `context pack`, 3,000 minus 250 | +0.006 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `harness status`, 3,000 minus 250 | -0.000 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `checkpoint (commit path)`, 3,000 minus 250 | +0.013 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `dispatch (work dispatch)`, 3,000 minus 250 | +0.015 s (<= +0.25 s) | pass |
| H2 flat, paired (6 rounds): `review ingest`, 3,000 minus 250 | +0.024 s (<= +0.25 s) | pass |
| Bound flat: `work tree` at 3,000 | 0.52 s (<= 2.0 s) | pass |
| Bound flat: `context pack` at 3,000 | 0.43 s (<= 2.0 s) | pass |
| Bound flat: `lead show` at 3,000 | 0.48 s (<= 2.0 s) | pass |
| Bound flat: `gate show` at 3,000 | 0.62 s (<= 2.0 s) | pass |
| Bound flat: `status` at 3,000 | 0.61 s (<= 2.0 s) | pass |
| Bound flat: `harness status` at 3,000 | 0.51 s (<= 2.0 s) | pass |
| Bound flat: `checkpoint (commit path)` at 3,000 | 0.36 s (<= 4.0 s) | pass |
| Bound flat: `dispatch (work dispatch)` at 3,000 | 0.55 s (<= 4.0 s) | pass |
| Bound flat: `review ingest` at 3,000 | 0.67 s (<= 4.0 s) | pass |
| Bound flat: `resume` at 3,000 | 0.93 s (<= 8.0 s) | pass |
| H3 flat: re-parse of a changed hot state at 3,000 | 13.3 ms (<= 0.25 s) | pass |
| Heartbeat bound flat | 13.3 ms (<= 2.5 s) | pass |
| H4 flat: `resume` does the same reads and scans at 250 and 3,000 | identical counters | pass |
| A1: hot bytes per open unit, 20 to 1,000 open | 1.03 KB (M3 baseline 0.9-1.3 KB) | report |
| A1: `lead show` per open unit | 0.27 ms (M3 baseline 0-2 ms) | report |
| A1: `status` per open unit | 0.92 ms (M3 baseline 0-2 ms) | report |
| A1: `work tree` per open unit | 0.27 ms (M3 baseline 0-2 ms) | report |
| A1: `resume` per open unit | 3.10 ms (M3 baseline 0-2 ms) | report |
| A1: `gate show` per open unit | 0.29 ms (M3 baseline 0-2 ms) | report |
| A1: `context pack` per open unit | 0.27 ms (M3 baseline 0-2 ms) | report |
| A1: `harness status` per open unit | 0.33 ms (M3 baseline 0-2 ms) | report |
| A1: `checkpoint (commit path)` per open unit | 0.49 ms (M3 baseline 0-2 ms) | report |
| A1: `dispatch (work dispatch)` per open unit | 0.51 ms (M3 baseline 0-2 ms) | report |
| A1: `review ingest` per open unit | 0.52 ms (M3 baseline 0-2 ms) | report |
| A1: `resume` along the series (look for a knee) | 20: 0.56 s, 200: 1.09 s, 500: 2.03 s, 1000: 3.59 s | report |
| H1 hierarchy: hot state at 3,000 / at 250 completed | 1.080x (<= 1.25x) | pass |
| H1 hierarchy: history share of hot state at 3,000 | 12.6% (<= 20%) | pass |
| H2 hierarchy: `lead show`, 3,000 minus 250 | +0.007 s (<= +0.25 s) | pass |
| H2 hierarchy: `status`, 3,000 minus 250 | +0.008 s (<= +0.25 s) | pass |
| H2 hierarchy: `work tree`, 3,000 minus 250 | -0.000 s (<= +0.25 s) | pass |
| H2 hierarchy: `resume`, 3,000 minus 250 | +0.003 s (<= +0.25 s) | pass |
| H2 hierarchy: `gate show`, 3,000 minus 250 | -0.005 s (<= +0.25 s) | pass |
| H2 hierarchy: `context pack`, 3,000 minus 250 | +0.011 s (<= +0.25 s) | pass |
| H2 hierarchy: `harness status`, 3,000 minus 250 | +0.007 s (<= +0.25 s) | pass |
| H2 hierarchy: `checkpoint (commit path)`, 3,000 minus 250 | -0.003 s (<= +0.25 s) | pass |
| H2 hierarchy: `dispatch (work dispatch)`, 3,000 minus 250 | +0.036 s (<= +0.25 s) | pass |
| H2 hierarchy: `review ingest`, 3,000 minus 250 | +0.028 s (<= +0.25 s) | pass |
| Bound hierarchy: `work tree` at 3,000 | 0.30 s (<= 2.0 s) | pass |
| Bound hierarchy: `context pack` at 3,000 | 0.36 s (<= 2.0 s) | pass |
| Bound hierarchy: `lead show` at 3,000 | 0.31 s (<= 2.0 s) | pass |
| Bound hierarchy: `gate show` at 3,000 | 0.47 s (<= 2.0 s) | pass |
| Bound hierarchy: `status` at 3,000 | 0.36 s (<= 2.0 s) | pass |
| Bound hierarchy: `harness status` at 3,000 | 0.49 s (<= 2.0 s) | pass |
| Bound hierarchy: `checkpoint (commit path)` at 3,000 | 0.34 s (<= 4.0 s) | pass |
| Bound hierarchy: `dispatch (work dispatch)` at 3,000 | 0.55 s (<= 4.0 s) | pass |
| Bound hierarchy: `review ingest` at 3,000 | 0.64 s (<= 4.0 s) | pass |
| Bound hierarchy: `resume` at 3,000 | 0.52 s (<= 8.0 s) | pass |
| H3 hierarchy: re-parse of a changed hot state at 3,000 | 7.4 ms (<= 0.25 s) | pass |
| Heartbeat bound hierarchy | 7.4 ms (<= 2.5 s) | pass |
| H4 hierarchy: `resume` does the same reads and scans at 250 and 3,000 | identical counters | pass |
