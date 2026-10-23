**STG-05 CS-1, CB-07, CB-09 and CBF-1 (2026-10-21): the store's path, the control lock and non-writers.** Writable binds and
read-only re-binds are applied ancestors first (`layout.bind_order`), and `for_run` refuses a layout whose writable
bind is the store or under it, or contains it without the next directory on its path re-bound read-only after it
(ruling R-3). A contained run needs its project. Agent layouts hide the project's whole `.aew/local`, so the control
lock is not in the sandbox, and `FileLock` no longer opens the lock read-only. `aew.process_kind` lists AEW's entry
points and their kinds: in a non-writer (the CLI inside a worker's run, `aew lead mcp`, `aew dashboard serve`, the
STG-02 server) `ControlStore.read`, `session` and `create` are refused before the lock is opened, and reads are
lock-free. Every engine read goes through `ControlStore.current` (`read` in a writer, `read_committed` in a
non-writer), and the lock has one opener (`ControlStore.control_lock`). A non-writer writes neither the store nor
the lock. Under `.aew/local` it writes only the derived history index's catch-up, which every reader makes, and the
commands whose purpose is a write there (`context pack`, `history reindex`) are refused.
ADR-0009, amendment 2026-10-21.
