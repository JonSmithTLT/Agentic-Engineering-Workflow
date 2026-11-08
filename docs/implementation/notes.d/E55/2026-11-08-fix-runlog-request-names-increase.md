**A request file's name is unique and ordered within a process.** Two requests of one kind on one clock tick (about
15.6 ms on Windows before Python 3.13) once shared a name, so the second's file replaced the first's. No product path
could reach that, since `aew harness send`, `stop` and `interrupt` each run in their own process and the name holds the
pid, but a test did. Across processes the limit stands: two requests on one tick from two processes sort by pid, not by
issue order. Each keeps its own file, so neither is lost.
