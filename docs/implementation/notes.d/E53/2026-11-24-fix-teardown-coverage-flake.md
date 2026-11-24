**A worker that coverage never started no longer reads as a lost save (2026-11-24).** A local run failed both cases of
`test_a_worker_killed_at_teardown_keeps_its_coverage_and_names_what_held_it` (only the controller's data file), then
passed. The cause was the run's environment, not timing: coverage was reached only through `PYTHONPATH` (installed with
`pip install --target`), so the `.pth` file that starts it in a subprocess (`patch = subprocess`) never ran in the xdist
worker, and `worker_coverage` had nothing to save. That setup fails the test every time (6 of 6, pinned coverage 7.17.5,
pytest 9.1.1, pytest-xdist 3.8.0), and coverage installed into site-packages passes it every time (22 of 22). It
"passed on re-run" because coverage was installed into site-packages in between. The test now checks, from inside the
worker, that coverage was started there, and says so when it was not. No flake-register entry: nothing is
nondeterministic.
