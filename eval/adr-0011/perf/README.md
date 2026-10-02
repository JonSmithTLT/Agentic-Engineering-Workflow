# ADR-0011 control-plane baseline: Linux supplement

`baseline-linux.json` is the before-ADR-0011 baseline, taken from a Linux cloud container on 2026-10-02 at `main` `0eb8ecf`. It is a **supplement, not the reference**: ADR-0011's completion criteria are measured on the Windows reference machine (`m3-performance.md`).

## Command

```text
python tools/perf/control_plane.py sweep --points 20:250,20:1000,20:3000,200:250,500:250,1000:250 --reps 3 --work <scratch> --json eval/adr-0011/perf/baseline-linux.json
```

The points are the M3 sweep (`eval/m3/perf/sweep.json`) plus the ADR-0011 active series up to 1,000 open units (A1). The hierarchy-history and cold-write series do not exist in the tool yet. P2a adds them, and those series are then run against this same commit.

## Conditions

- A cloud container with 4 CPUs.
- Ubuntu's Python 3.11.15, in a venv, with PyYAML 6.0.3 from the PyPI wheel, which includes libyaml (`yaml.__with_libyaml__` checked before the run).
- git 2.43.0.
- Load average 0.07 at the start of the run. Nothing else ran during it except editors and git commits.
- Cloud CPUs are noisier than a dedicated machine. Read slopes, not absolute numbers.

## Results

| | 20 open, 250 completed | 20 open, 1,000 completed | 20 open, 3,000 completed | 200 open, 250 completed | 500 open, 250 completed | 1,000 open, 250 completed |
|---|---|---|---|---|---|---|
| `control.yaml` | 5.20 MB | 20.70 MB | 62.07 MB | 5.38 MB | 5.69 MB | 6.21 MB |
| live part | 27 KB | 27 KB | 27 KB | 213 KB | 523 KB | 1,040 KB |
| `lead show` | 2.82 s | 14.28 s | 42.81 s | 2.78 s | 2.90 s | 3.77 s |
| `status` | 2.71 s | 14.66 s | 40.75 s | 2.80 s | 2.89 s | 3.91 s |
| `resume` | 4.60 s | 20.78 s | 59.98 s | 4.89 s | 5.32 s | 6.96 s |
| `checkpoint` | 4.04 s | 19.23 s | 62.68 s | 4.19 s | 4.75 s | 5.59 s |
| `work dispatch` | 4.11 s | 19.37 s | 63.34 s | 4.52 s | 5.04 s | 5.59 s |
| `review ingest` | 4.15 s | 19.22 s | 65.77 s | 4.65 s | 4.97 s | 5.99 s |

The JSON also holds `work tree`, `gate show`, `context pack`, `harness status`, the CLI floor, and per-phase and micro timings.

## Reading

- **Same shape as the Windows baseline.** Each completed Ticket adds about 20.7 KB to the control file. Each open or planned unit adds about 1.03 KB, and that stays linear up to 1,000 open, with no knee.
- **This container is about 2.4× slower at YAML parsing** than the Windows reference: a libyaml load of the 20/250 file takes 2.49 s here against 1.04 s there. Command latencies scale accordingly; `lead show` at 20/250 is 2.82 s here and 1.44 s there. Builds run about 1.8× faster here, because git and filesystem calls cost less on Linux. Compare against Windows numbers by slope.
- **The active series** adds about 1 s of read latency from 20 to 1,000 open units at 250 completed (`lead show` goes from 2.82 s to 3.77 s, mostly parsing about 1 MB of open units). ADR-0011's A1 asks for this slope. Against the Windows absolute bounds it is not a problem, but it matters for H3's 0.25 s heartbeat budget, which investigation §7 also flags.
