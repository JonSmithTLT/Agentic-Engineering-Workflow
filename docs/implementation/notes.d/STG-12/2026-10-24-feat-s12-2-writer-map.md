**S12-2, pull request 2 of 8 (2026-10-24): the writer map, the `writers` family of the generated reference.**
For each path under `.aew` that AEW code writes, the module and function that writes it, how (a store transaction or a
direct write), and the entry points that can reach it. [`docs/reference/writers.md`](../../../reference/writers.md) is the
page; `index.json` holds the records (`writers:<path as a template>`, such as `writers:work/{}/completion.md`).

- **How it reads.** From the write end, with `ast` and nothing run: a write primitive is a call identified by where its
  callee was imported from (`aew.util.atomic_write`, `os.replace`, `shutil.rmtree`, `sqlite3.connect`) or, for a
  method with no import source, by what it is (`Path.write_text`, a one-argument `.replace(target)`, `open` in a
  write mode, `session.write(path, content)`). The destination expression is followed to a path under `.aew` through
  assignments, constants (by import source), `self` attributes and base classes, parameters (the arguments of every
  static call), loops over a directory or a mapping's keys, and the functions that build paths. `aew.util` and the
  store's `write_file` are the write mechanism: their callers are the writers.
- **What it states.** A path is a template (`{}` is a computed segment). A destination that is not provably under
  `.aew` and not provably outside it is its own record, `writers:unresolved:<module>:<symbol>:<primitive>`, with the
  reason; every path record points at those, since any may write it. A destination provably outside `.aew` (a
  temporary directory, the console, the repository's working tree) is listed on the page and is no record. The set of
  entries directly under `.aew` is declared in the generator and pinned both ways by a test, so a new directory is a
  decision and not a silent record. Every list is a lower bound, and says what it could not resolve.
- **Reach.** A writer carries the entry points whose declaring function reaches it by a chain of resolved calls (the
  CLI's registered handlers included). The CLI's four roles share one declaring function, so a writer it reaches is
  reached from all four; the page says what that checks and what it does not, and a cut per role is a decision for the
  design side.
- **Two readers.** A second detector, written over tokens and sharing no code with the first, finds the write-primitive
  calls, and the two agree on every module of the tree. What neither sees (a primitive chosen by a conditional callee,
  a local name bound to a primitive, a computed method name, a subprocess) is pinned by a probe each.
- **What a change to writing code does.** A pull request that adds a writer, or changes where one writes, runs
  `python tools/reference.py render` and commits `docs/reference/`. A new directory directly under `.aew` fails
  `tests/integration/test_reference_writers.py` until it is declared (`TOP_LEVEL` in
  `tools/reference_families/writers.py`), and a write at module level is refused with a reason.
