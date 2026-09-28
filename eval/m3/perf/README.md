# M3 control-plane measurements (step 7)

Raw output of `tools/perf/control_plane.py run --sizes 50,500,3000 --reps 3`, summarized in `docs/implementation/m3-performance.md`:

- `before.json`: the code as of step 6 (pure-Python YAML, per-unit `git rev-parse`, no parse reuse).
- `after.json`: the step-7 fixes.

Each file lists, per project size, the project (`units`, `invocations`, `tokens`, `control_bytes`, `build_s`), `micro` (one YAML load or dump, schema validation, deep copy of that project's control state), and `ops` (per command: median wall time, in-process time, phase medians and the last run's counts).

In `after.json`, `micro.yaml_dump_python_s` timed AEW's own `dump_yaml`, which uses libyaml after the fix, so it is not a pure-Python figure. The tool was corrected afterwards; the pure-Python write times are those in `before.json`.
