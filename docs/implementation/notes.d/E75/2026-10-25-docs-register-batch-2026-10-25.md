**Two more of the class: a test's wall-clock bound.**

- **`tests/unit/test_lead_reachability.py::test_only_a_cooperative_operation_lets_another_request_through[cooperative1-True]`**
  failed once, on a Rocky 8 host under `-n 4`, on a timing bound (a builder's local run, 2026-10-25). It has not been
  seen in CI.
- **`tests/integration/test_steering_loop.py`'s activation waits** are 30 s, at lines 643, 649, 802 and 840 (at
  `c81eb233`). That is below the 60 s lock timeout the loop runs with.
  - The loop records no bound a test could derive its wait from. So the fix needs a change under `src/` to state the
    bound, as the notifier's did (#276).
  - Found by #276's review (N5); filed here, as #278's quick check asked (P3).
