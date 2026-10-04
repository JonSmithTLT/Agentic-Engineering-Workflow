| Criterion | Measured | Verdict |
|---|---|---|
| H1 flat: hot state at 3,000 / at 250 completed | 1.048x (<= 1.25x) | pass |
| H1 flat: history share of hot state at 3,000 | 7.7% (<= 20%) | pass |
| H2 flat: `lead show`, 3,000 minus 250 | +0.016 s (<= +0.25 s) | pass |
| H2 flat: `status`, 3,000 minus 250 | +0.024 s (<= +0.25 s) | pass |
| H2 flat: `work tree`, 3,000 minus 250 | +0.010 s (<= +0.25 s) | pass |
| H2 flat: `resume`, 3,000 minus 250 | +0.017 s (<= +0.25 s) | pass |
| H2 flat: `gate show`, 3,000 minus 250 | +0.017 s (<= +0.25 s) | pass |
| H2 flat: `context pack`, 3,000 minus 250 | +0.025 s (<= +0.25 s) | pass |
| H2 flat: `harness status`, 3,000 minus 250 | +0.004 s (<= +0.25 s) | pass |
| H2 flat: `checkpoint (commit path)`, 3,000 minus 250 | +0.013 s (<= +0.25 s) | pass |
| H2 flat: `dispatch (work dispatch)`, 3,000 minus 250 | +0.018 s (<= +0.25 s) | pass |
| H2 flat: `review ingest`, 3,000 minus 250 | +0.004 s (<= +0.25 s) | pass |
| Bound flat: `work tree` at 3,000 | 0.15 s (<= 2.0 s) | pass |
| Bound flat: `context pack` at 3,000 | 0.20 s (<= 2.0 s) | pass |
| Bound flat: `lead show` at 3,000 | 0.15 s (<= 2.0 s) | pass |
| Bound flat: `gate show` at 3,000 | 0.21 s (<= 2.0 s) | pass |
| Bound flat: `status` at 3,000 | 0.20 s (<= 2.0 s) | pass |
| Bound flat: `harness status` at 3,000 | 0.25 s (<= 2.0 s) | pass |
| Bound flat: `checkpoint (commit path)` at 3,000 | 0.20 s (<= 4.0 s) | pass |
| Bound flat: `dispatch (work dispatch)` at 3,000 | 0.26 s (<= 4.0 s) | pass |
| Bound flat: `review ingest` at 3,000 | 0.26 s (<= 4.0 s) | pass |
| Bound flat: `resume` at 3,000 | 0.25 s (<= 8.0 s) | pass |
| H3 flat: re-parse of a changed hot state at 3,000 | 6.4 ms (<= 0.25 s) | pass |
| Heartbeat bound flat | 6.4 ms (<= 2.5 s) | pass |
| H4 flat: `resume` does the same reads and scans at 250 and 3,000 | identical counters | pass |
| A1: hot bytes per open unit, 20 to 1,000 open | 1.03 KB (M3 baseline 0.9-1.3 KB) | report |
| A1: `lead show` per open unit | 0.32 ms (M3 baseline 0-2 ms) | report |
| A1: `status` per open unit | 0.35 ms (M3 baseline 0-2 ms) | report |
| A1: `work tree` per open unit | 0.29 ms (M3 baseline 0-2 ms) | report |
| A1: `resume` per open unit | 1.24 ms (M3 baseline 0-2 ms) | report |
| A1: `gate show` per open unit | 0.29 ms (M3 baseline 0-2 ms) | report |
| A1: `context pack` per open unit | 0.29 ms (M3 baseline 0-2 ms) | report |
| A1: `harness status` per open unit | 0.28 ms (M3 baseline 0-2 ms) | report |
| A1: `checkpoint (commit path)` per open unit | 0.47 ms (M3 baseline 0-2 ms) | report |
| A1: `dispatch (work dispatch)` per open unit | 0.47 ms (M3 baseline 0-2 ms) | report |
| A1: `review ingest` per open unit | 0.51 ms (M3 baseline 0-2 ms) | report |
| A1: `resume` along the series (look for a knee) | 20: 0.23 s, 200: 0.45 s, 500: 0.82 s, 1000: 1.45 s | report |
| H1 hierarchy: hot state at 3,000 / at 250 completed | 1.082x (<= 1.25x) | pass |
| H1 hierarchy: history share of hot state at 3,000 | 12.8% (<= 20%) | pass |
| H2 hierarchy: `lead show`, 3,000 minus 250 | +0.011 s (<= +0.25 s) | pass |
| H2 hierarchy: `status`, 3,000 minus 250 | +0.013 s (<= +0.25 s) | pass |
| H2 hierarchy: `work tree`, 3,000 minus 250 | +0.009 s (<= +0.25 s) | pass |
| H2 hierarchy: `resume`, 3,000 minus 250 | +0.032 s (<= +0.25 s) | pass |
| H2 hierarchy: `gate show`, 3,000 minus 250 | +0.010 s (<= +0.25 s) | pass |
| H2 hierarchy: `context pack`, 3,000 minus 250 | +0.008 s (<= +0.25 s) | pass |
| H2 hierarchy: `harness status`, 3,000 minus 250 | +0.007 s (<= +0.25 s) | pass |
| H2 hierarchy: `checkpoint (commit path)`, 3,000 minus 250 | +0.009 s (<= +0.25 s) | pass |
| H2 hierarchy: `dispatch (work dispatch)`, 3,000 minus 250 | +0.010 s (<= +0.25 s) | pass |
| H2 hierarchy: `review ingest`, 3,000 minus 250 | +0.076 s (<= +0.25 s) | pass |
| Bound hierarchy: `work tree` at 3,000 | 0.14 s (<= 2.0 s) | pass |
| Bound hierarchy: `context pack` at 3,000 | 0.18 s (<= 2.0 s) | pass |
| Bound hierarchy: `lead show` at 3,000 | 0.14 s (<= 2.0 s) | pass |
| Bound hierarchy: `gate show` at 3,000 | 0.20 s (<= 2.0 s) | pass |
| Bound hierarchy: `status` at 3,000 | 0.19 s (<= 2.0 s) | pass |
| Bound hierarchy: `harness status` at 3,000 | 0.25 s (<= 2.0 s) | pass |
| Bound hierarchy: `checkpoint (commit path)` at 3,000 | 0.19 s (<= 4.0 s) | pass |
| Bound hierarchy: `dispatch (work dispatch)` at 3,000 | 0.24 s (<= 4.0 s) | pass |
| Bound hierarchy: `review ingest` at 3,000 | 0.32 s (<= 4.0 s) | pass |
| Bound hierarchy: `resume` at 3,000 | 0.24 s (<= 8.0 s) | pass |
| H3 hierarchy: re-parse of a changed hot state at 3,000 | 3.6 ms (<= 0.25 s) | pass |
| Heartbeat bound hierarchy | 3.6 ms (<= 2.5 s) | pass |
| H4 hierarchy: `resume` does the same reads and scans at 250 and 3,000 | identical counters | pass |
