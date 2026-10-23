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
  nests too deep is refused before anything touches disk. The bound costs about 6% of a dump.
- **The store's own reads.** Control state and redo records are read with `util.load_own_yaml`, without the pass. Only
  `dump_yaml` writes them, and each is checked against its recorded hash first. The pass would add 39 ms to every
  command at 50 units and 379 ms at 500 (control state's parse is 89 ms and 1.34 s).
- **Tests.** `tests/unit/test_yaml_depth.py` keeps every YAML file in the repository within the bound (the deepest is
  13 levels). It lists every place in `src/aew` that composes or writes YAML outside `util`'s bounded functions, with
  the reason each is safe, and the store's reads that skip the pass.
