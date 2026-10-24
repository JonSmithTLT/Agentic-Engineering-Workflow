**S12-2, pull request 1 of 8 (2026-10-24): the generated as-built reference exists, with its first two families.**
The slice builds [`docs/reference/`](../../../reference/README.md) one family at a time, each in its own pull request,
each reviewed independently before the next starts (the documentation recovery plan v0.3, as adopted).

- **The generator.** `python tools/reference.py render` writes `docs/reference/` from the code; `python
  tools/reference.py check` regenerates it in memory and fails on any difference, naming the first one and the command
  that settles it. CI runs `check` as a fast-lane test (`tests/unit/test_reference.py`), so Linux and Windows must
  produce the same committed bytes. The output is deterministic (sorted, POSIX paths, LF, no timestamp, no absolute
  path), proved by rendering twice and across hash seeds; it states what the code is and holds no requirement.
- **The index.** `index.json` holds `records` keyed `<family>:<key>`, each with its `family`, `anchor` (module and
  symbol), `basis`, `coverage` and an optional `fact`; a list fact a detector found says how complete it is in the
  record's `fact_coverage`, beside `coverage`. `gaps` is a summary computed from the records. `counts` carries a
  `digest`, so two pull requests that both change the records conflict on one line instead of merging into stale
  totals; after such a conflict take either side and run `render`.
- **Built so far.** `modules` (one record per module under `src/aew`, with its AEW imports; static, lower-bound) and
  `entry-points` (DOC-02: one record per row of `aew.process_kind.ENTRY_POINTS`, with where it declares itself and every
  place the product starts it; complete-by-construction for the set of entry points, lower-bound for the two lists).
  The spawn-site test (every `python -m aew...` spawn names a listed entry point) is in
  `tests/integration/test_reference_entry_points.py`, read by two independent detectors.
- **Still to come, in this order.** The writer map (DOC-01), the `.aew/` layout and the control-state keys (DOC-04), concurrency
  (DOC-03), the state machines, the interfaces (routes, tools, schemas, tables, then the STG-02 command and refusal
  families), and last the module page, the generated maps and an AGENTS.md rule that a pull request adding a record
  names, in its description, the requirements the record serves (operator-merged).
- **What a change to enumerated code does.** A pull request that adds or removes a module, changes its imports, an entry
  point or a spawn site runs `render` and commits `docs/reference/`; the `check` failure says so. `render` and `check`
  need an absolute `PYTHONPATH` to the tree's `src` in a worktree, and refuse to run otherwise.
