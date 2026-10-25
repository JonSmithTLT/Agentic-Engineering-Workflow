**The dashboard wrong-answer flakes (2026-10-25, branch `fix/probe-upstream-teardown`).** Five CI rows got an
answer that was not their dashboard server's:
- #262's run 40152522675, `integration 2/12` and `integration 4/12` (ubuntu);
- `main` at `290d5bca`, run 40171024681 attempt 1, `integration 11/12` (ubuntu), which left `main` red for about 7 hours;
- `main` at `6eec6f10`, run 40158679984, `integration 11/16` (windows);
- a branch at `79c2f4e6`, run 40119161810, `integration 12/16` (windows).

**Linux, the source proven:** the containment probe's `_network` left its provider upstream's listener open after
every run. A `close()` from another thread does not wake a blocked `accept()`, so the port stayed in `LISTEN` and its
thread answered one more request, whatever it was, with `200` and the 32-hex token, the rows' signature. The diagnosis
reproduced it in 20 of 20 in-process runs. Fixed in `0eccb69d`: the upstream is an `egress.Service`, which wakes and
joins its accept thread.
`tests/unit/test_containment_probe.py::test_the_probes_network_stand_ins_leave_no_listener_socket_or_thread_behind`
fails on `290d5bca` and passes with the fix.

**Open:** how a dashboard client's connection to its own server's port reached that listener. The kernel refused two
listeners on one port in every experiment. In `c640c2f6`, the three dashboard World clients' requests fail on any
answer without the dashboard's marks, with the port's listening and connected sockets and their owners, this process's
socket inodes and its threads. The next occurrence then names the process and the socket. Note that the leaked
listener frees its port once it has answered, so by then it is gone from the table.

**Windows, a separate cause, supported but not proven:** two sockets that both set `SO_REUSEADDR` can listen on one
port there, and the dashboard's listener set it (http.server's default). `75e03a0f` gives it `ExclusiveServer`'s rule,
now owned by `aew/exclusive_server.py`, and `tests/unit/test_exclusive_server.py` enumerates every listener in `src`.
No explicit bind on a port another dashboard holds was found in the tree, so rows 4 and 5's mechanism stays open. This
entry closes only once a test reproduces each cause deterministically, as the row says. The Linux one has such a test;
the open link and the Windows rows do not.
