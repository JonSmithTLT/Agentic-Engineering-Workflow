# M3 control-plane measurements (steps 7 and 8)

Raw output of `tools/perf/control_plane.py run --sizes 50,500,3000 --reps 3`, summarized in `docs/implementation/m3-performance.md`:

- `before.json`: the code as of step 6 (pure-Python YAML, per-unit `git rev-parse`, no parse reuse).
- `after.json`: the step-7 fixes.

Each file lists, per project size, the project (`units`, `invocations`, `tokens`, `control_bytes`, `build_s`), `micro` (one YAML load or dump, schema validation, deep copy of that project's control state), and `ops` (per command: median wall time, in-process time, phase medians and the last run's counts).

`sweep.json` (step 8, the baseline for ADR-0011): `tools/perf/control_plane.py sweep --points 20:250,20:1000,20:3000,200:250 --reps 3`, on the step-8 code (no change to the control plane since step 7). Per point: `point` (open and completed units), `project`, `footprint` (bytes of `control.yaml` attributed to open units, to history, and to neither; per open unit and per completed Ticket; the live part ADR-0011 would keep), `micro` and `ops` as above. Summarized in `m3-performance.md` §7.

In `after.json`, `micro.yaml_dump_python_s` timed AEW's own `dump_yaml`, which uses libyaml after the fix, so it is not a pure-Python figure. The tool was corrected afterwards; the pure-Python write times are those in `before.json`.
