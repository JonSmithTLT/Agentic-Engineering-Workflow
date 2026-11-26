A serial lane cancelled before its first test was typed as a test interrupted: `[death-record] cancel: no pre-cleanup
worker observation` and `[running] missing running test name`.

- **The sighting.** PR #608's run 45782924831 (2026-11-26, evidence check 139802356185), job 139788422783, `serial 1/1
  (ubuntu-latest)`: its lane step started at 08:55:21.99Z and its pytest was killed at 08:55:24.41Z, 2.4 s in, having
  printed nothing. No test had begun, so there was no worker to observe and no name to give.
- **The cause.** #579's stated limit. `worker_evidence.before_tests` records a session that is still starting only
  from a lifecycle receipt read from its live writer, and only xdist workers kept one; a session with no
  `worker-count` was refused as "not shown to be an xdist session". The lane was then typed `cancel`.
- **The fix.** The receipt has one owner, `session_deadline.PhaseReceipt`, which a worker and a serial session's
  controller (one that runs its tests itself; an xdist controller still keeps none) both use: the same three phases
  at the same hooks, on one held descriptor, in `controller-<pid>-<start>-lifecycle.txt`
  (`evidence_files.lifecycle_receipt`). `phases_at_signal` reads a controller that has a receipt as a row named
  `controller`. `before_tests` records a session with no worker roster only when no worker is registered and that row,
  read from the live controller, stands before its first test; the record lists the controller by pid and start,
  with `serial: true`. `before_tests_problems` accepts it only while the bundle bears it out: the published
  `controller-pid` and `controller-start` match, the receipt reached the recorded phase and never execution, and a
  session with no roster that had not finished lists its controller at all. A finished session's own controller
  receipt, where it kept one, must stop before its first test too (`finished_without_tests`). The controller releases
  the receipt once it has written `session-finished`.
- **The other side.** A serial controller in a test is never recorded, whatever the rows say: its watchdog header
  (`hang-main-<pid>.txt`) or a running name refuses the record, and a receipt at `execution-started` or one with no
  live writer does too. Such a lane is still typed `cancel` and still owes its observation and its running name.
- **Tests.** `test_a_serial_lane_cancelled_while_its_controller_collects_is_typed_before_tests`,
  `test_a_serial_controller_without_a_receipt_or_past_collection_still_owes_its_observation`,
  `test_a_serial_controller_in_a_test_is_never_recorded_as_before_tests`,
  `test_a_serial_before_tests_record_the_bundle_contradicts_is_a_defect`,
  `test_a_serial_controllers_receipt_is_read_from_its_live_writer_and_an_xdist_controller_has_none`, and, on a real
  serial pytest session (POSIX), `test_a_real_serial_session_is_typed_before_tests_only_until_its_first_test`:
  interrupted or killed while it collects, its published bundle is typed `before tests` with no defect; killed inside
  a test, it is typed `cancel` and owes its observation.
- **The proof.** The evidence proof gains a serial twin of its start-up control: `run-cancel-control (start-serial)`
  dispatches a target whose two plants (`cancel-start-serial`, `-p no:xdist`) hold the controller's own collection in
  `evidence_plants/startup.py`, cancels it once both lanes have run `START_READY_SECONDS`, and requires both jobs
  typed `before tests` with A2 yes and no defect. It costs one more control job and two more plant runners per proof
  run. It has not yet run on a hosted runner: on Windows the cancellation collection must find the controller still
  holding its receipt, which only that run shows.
- **The Windows serial job cancelled in the same second raised no defect** because its lane never started: job
  139788422843 was cancelled during `actions/checkout` (08:55:11Z to 08:55:24Z), and its serial lane step was
  skipped. A job cancelled before its lane owes no lane evidence.
- **Limits.** A controller that has registered its session and not yet entered `pytest_collection` has no receipt, so
  a cancellation in that window (and an xdist session's before its roster, which cannot be told from it) stays a
  defect. Measured locally on one serial session: the controller registered 0.58 s after its process started and
  entered its collection 0.19 s later, while a serial lane's collection of the whole suite takes far longer, so the
  window is small beside the state now recorded. The serial bundle of the sighting (artifact 15100712677) could not
  be read, so which side of that window its 2.4 s fell on is not established.

**What remains** (2026-11-26): E3 stays a standing watch. The first hosted `start-serial` control is the proof on
both platforms. `linux-cancel-live-stack` (`tests/flake-register.yaml`) stays open; its fix is a separate change.
