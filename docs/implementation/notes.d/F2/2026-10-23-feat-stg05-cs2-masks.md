**STG-05 CS-2, the masks (2026-10-23): `/run` masked whole, the display's credentials, no controlling terminal, the
socket inventory and the self-test's rows 2 to 5; and the reader git gap closed (D-CS2-1).** ADR-0009's amendment of
2026-10-23 and ADR-0002's amendment of the same date hold the decisions.

- **The reader git gap is closed** (the 2026-10-23 note above, D-CS2-1, CS-2's outcome 7).
  - A non-writer process computes a fingerprint without writing any object, inside a sandbox and outside one.
  - A store writer keeps storing what it hashes, with the same values. The engine reads a writer's snapshot tree
    from the store: the reviewer's pack and a mutated workspace's refusal.
  - `READER_GIT_GAP` is empty. The worker-surface tests judge the real object store by digest on both faces.
  - `working_diff` is flagged: nothing in `src` calls it, and its keep-or-remove question is with the designer and
    the operator.
- **Every contained process, eval's included:**
  - `/run` is masked whole (ruling R-1). The one host-derived exception is the target of `/etc/resolv.conf` when it
    lies under `/run`, bound back read-only for name resolution until CS-3 (the operator, 2026-10-24). A project on
    removable media under `/run` is bound back with its workspace (operator ruling 2026-10-23: a project under /run
    is bound back, on five conditions, R-1), and nothing under `aew-*`, `user`, `dbus` or `systemd` ever is. An
    operator's writable root under `/run` is refused.
  - The display's credential files and the file `XAUTHORITY` names are masked. So are git's credential cache and its
    store helper's file.
  - The display, session-bus and ssh-agent variables are unset, and every process starts in a new session.
- **The launch self-test records CB-12's rows 2 to 5 on the label,** pass or fail, and fails closed in `required`:
  - row 2, `/run` and the socket inventory (`aew.harness.containment.sockets`);
  - row 3, the display;
  - row 4, no controlling terminal, read on the started process;
  - row 5, the binds and masks.
- **Waiting on a ruling:** `working_diff`'s keep-or-remove question, for a later batch of flagged code, never a
  containment slice (the designer, 2026-10-23).
- **Not measured here:** the work host. Measure the socket walk there before relying on `required` mode.
