**R3 held only on Linux with Python 3.11; now YAML nesting is bounded on every read and write (2026-10-23).** The
hostile corpus's `deep_nesting_3000` document is 3,000 levels deep. libyaml's composer recurses in C with no depth
check, so on Windows it overflowed the stack and killed the test worker with no exception to catch (from about 2,660
levels on Python 3.11 and 3,970 on 3.13, PyYAML 6.0.3). On Linux with Python 3.13 it composed, and the read gave schema
violations rather than `UNPROCESSABLE`. The nightly's extra Python job had failed on these tests every night since
F46.1 merged.

- **Reading.** `util.load_yaml` reads the event stream first, which neither backend parses recursively, and refuses a
  document nested deeper than `util.YAML_MAX_DEPTH` (64) as a ValidationFailed with reason `yaml_too_deep`. The
  configuration projection maps that reason to `UNPROCESSABLE`, so R3 holds on every platform and Python. `--fields`
  checks the same bound before it composes, so a deep value is a usage error, not a RecursionError.
- **Writing.** `util.dump_yaml` and the new `util.safe_dump_yaml` (PyYAML's own layout, for the disposition records and
  ended stage intents, byte for byte as before) refuse to write past the same bound. A read bound alone would have let
  one deep value in a free-form object of control state make the project's own store unreadable. A commit whose state
  nests too deep is refused before anything touches disk. The refusal names the document and the top-level key the
  writer refused under, shared objects, tuples and mapping keys included (review of #236, R2-F1, R3-F1). The bound
  costs about 6% of a dump.
- **The store's own reads too.** Control state and redo records pass the bound like every other read. Their checksums
  keep out damage, not a writer: a same-account process, a worker on Windows or a git checkout can write them and
  recompute the hash, so skipping the pass would have turned a deep file into a process killed with no error, `aew
  doctor` included (review of #236, F1). AEW never writes either that deep, so a deep control state says to restore it
  from git or a backup, and a deep redo record, which git ignores, is refused as damaged (R2-F3). The pass costs 39 ms
  at 50 units and 379 ms at 500, 28-43% of a parse, once per version of a file a process parses: once per CLI
  command, and again after each commit for a long-lived reader (control state's parse is 89 ms and 1.34 s).
- **Tests.** `tests/unit/test_yaml_depth.py` keeps every YAML file in the repository within the bound (the deepest is
  13 levels). It counts every place in `src/aew` that composes or writes YAML, or drives a loader or dumper class,
  outside `util`'s bounded functions, by file and function, with the reason each is safe. Sites are found from the
  installed yaml package, not a hand list (R2-F2): each `yaml.` chain is resolved against the module, a class is
  composing or writing by what it can do and is a site where it is called or subclassed, and every function defined in
  `yaml/__init__` is classified, so a test fails when PyYAML adds one there. It also requires every import of yaml to be
  `import yaml`, counts every bare `yaml` name and every `getattr`, `vars` or `__dict__` lookup on it, and refuses
  another module reaching `util`'s own yaml objects by an absolute import of `aew.util`. This is a lower bound on the
  spellings, not a proof (R3-F2). Not seen, and stated beside the tests: a class
  bound to a name and then driven, or held in a data structure; a submodule of yaml handed on; `util` reached by a
  relative import, `import aew` or `import_module`; `util`'s own names driven inside `util.py`; another AEW module's
  `yaml`; yaml found by `pkgutil.resolve_name`, `sys.modules`, `globals()` or a computed import name; a function that
  `yaml/__init__` re-exports from a submodule, or a C function; `exec` and `eval`; and YAML parsed inside a C extension
  or a dependency. None of these spellings reaches yaml in `src/aew` today (grep, 2026-10-24): its `import aew`
  (`harness/procs.py`, for `aew.__file__`) and its two computed imports (`doctor.py`, `harness/registry.py`, names from
  AEW's own lists) compose nothing.
