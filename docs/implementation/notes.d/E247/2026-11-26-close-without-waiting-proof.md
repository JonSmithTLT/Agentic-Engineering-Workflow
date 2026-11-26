**The zombie-group test infers "closes without waiting"; it does not observe it (#608 quick check at `23e62fce`, minor).**

- **What:** `tests/unit/test_process_tree.py::test_a_tree_whose_group_holds_only_a_zombie_is_not_active_and_closes_without_waiting`
  asserts `tree.active() == 0` and `tree.close(EXIT_S) == 0`. That `close` then does not wait its bound follows from
  reading `ProcessTree.close`, whose polling loop runs only while `active()` is not zero. A later change that made
  `close` wait on another reading would pass this test, slowly.
- **Why it is not asserted by time:** an elapsed-time assertion outside the serial lane is refused
  (`test_no_test_outside_the_serial_lane_asserts_how_long_something_took`), and it failed CI at `706cf95a`.
- **Why it is not asserted by counting sleeps:** tried and dropped. `close` also waits for its sentinel process with
  `Popen.wait(timeout)`, which sleeps by design, so a count of `time.sleep` calls is not zero on a correct `close`.
- **What is meant to fix it:** E394's pull request, which changes the same reading and the same tests. It either gives
  `close` an observable for "polled for members" (for example the number of polls it made) and asserts zero here, or
  moves a timed version of this test to the serial lane, or renames the test and its key in
  `tests/platform-skips.yaml` to what it proves.
