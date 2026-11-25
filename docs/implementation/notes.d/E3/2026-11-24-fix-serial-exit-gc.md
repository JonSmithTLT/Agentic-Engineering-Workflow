**The nightly's Linux reference shards ended after finishing (cause C of the 11-17 to 11-22 nightlies).** Every night
from 2026-11-17 to 11-22, Linux `reference serial` shards (one process, `-p no:xdist`) finished their session and
exited 137: the session deadline's sentinel saw `session-finished`, waited one margin (30 s), and ended a controller
that was still running (`stuck-after-finish`). In run 45037238066 (shards 2/5 and 5/5) the controller's stacks a margin
after finishing were `Garbage-collecting`, with no Python frame: interpreter finalization's collection, not test code.
Never on Windows, never under xdist.

- **The cause, a leak.** Twelve test modules that build or read a family of the generated reference each held a
  `reference_families.common.Context` in a module global, so for the rest of the session: twelve parses of the package
  (about a million tracked objects each), and some modules a parsed program of their own on top. Under xdist they are
  spread across workers; one serial process kept them all. Measured locally, those twelve modules alone ended with 12.1
  M tracked objects (2.4 GB) and took 19.7 s from the last `atexit` callback to the process's end; under
  `--session-deadline` on `main` they passed (248) and the sentinel ended the controller at 30.5 s, exit 137, as in CI.
  A shard's collection alone held 5.1 M objects and took 10.5 s to exit.
- **The fix, in two parts.** (1) The parsed tree is one per process, `tests/helpers/reference_render.context()`, as the
  rendered reference already was, and the three modules that built their own program take the shared one
  (`writers_flow.program_of`). The twelve modules now end at 1.24 M objects (0.5 GB) and 3.8 s, and run in 163 s
  rather than 247 s. (2) The controller's last act, `session_deadline.Controller.finish`, calls `gc.freeze()`, so no
  later collection walks what the session made, however large: the same modules under the session deadline exit 0.1 s
  after `session-finished`; a shard's collection with the heap frozen exits in 0.6 s rather than 10.5 s. The margin is
  unchanged. Proof: `test_a_controller_never_collects_its_sessions_heap_at_exit_so_a_large_one_exits_within_the_margin`
  (`tests/integration/test_hang_autopsy.py`), which fails without the freeze.
- **The assurance names it.** The assurance jobs download only the reports-only bundles (`lane-report-*`,
  `nightly-reference-*`), which carried no autopsy. The reports-only staging now carries exactly one autopsy file,
  `autopsy/session-*/stuck-after-finish.txt` (`evidence_files.stuck_marker`), scanned like the rest, and
  `tools/ci/check_assurance.py` reports each one as its own problem, with the session folder whose stacks are in the
  full evidence bundle, rather than only `reference=failure`. The test stages planted raw folders through the real
  staging and runs the assurance over the staged bundles
  (`test_a_session_the_sentinel_ended_after_it_finished_is_named_as_its_own_problem`; review of #553, M1).
- **Not this cause.** Shard 2/5 of run 45037238066 also had one failed test,
  `tests/unit/test_yaml_depth.py::test_a_deep_control_state_resealed_by_another_writer_is_refused_in_process`
  (`KeyError: 'reason'`: the refusal carried no reason code), seconds before the session finished. That was the libyaml
  depth error fixed by #511: the run's head, `172b5c80`, precedes #511's merge, `ec5aae96`.
- **Follow-on from #553's quick check, m2 (minor, tracked here).** `check_assurance.stuck_after_finish` reads every
  `stuck-after-finish` marker under the download root, without the attempt rule (`latest_attempts`) and the
  `-recovered` deduplication that `load_reports` applies. So a shard ended stuck-after-finish in one attempt keeps
  `assurance` red after a green re-run, and a recovered bundle names the session twice. It fails closed and never
  hides a failure. **The fix:** keep a marker only when its bundle holds a report that `latest_attempts` keeps, and skip
  a `-recovered` duplicate. A test stages two attempts through the real reports-only staging. It is owned by the next
  E3 pull request.
