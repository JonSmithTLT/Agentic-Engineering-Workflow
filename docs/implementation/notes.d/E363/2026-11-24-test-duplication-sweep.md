**The sweep's first pull request: the owner, the guard, and the clear cases.** Measured on Python 3.13 and 3.11 in a
4-CPU Linux container, 2026-11-24, with #553 applied (it shares the reference families' parse; this change builds on it).

- **The owner.** `tests/helpers/shared_setup.py`: `once` is `functools.cache` that records what each first build kept,
  so the guard charges it to the shared setup, not to the module that asked first. `reference_render`'s render and
  parse go through it; the parse's lazy parts (the sources, each module's index, each `Context.once` analysis) are
  recorded as shared when first built.
- **The guard.** `tests/helpers/module_heap.py`, registered by `tests/conftest.py`. Budget: 300,000 allocated memory
  blocks (`sys.getallocatedblocks`: allocations, about 30 MB over small objects) per test module; a parse of `src/aew` keeps about 2.2 M blocks (1.0 M
  tracked objects) on 3.11 and 3.13 alike (2,179,471 and 2,188,154). It checks each module's import in every session
  and lane (a module over budget fails its collection, naming itself) and, in a serial session, what a module's tests
  left (the session fails at its end, naming the module). Session-scoped fixtures and `once` builds are credited as
  shared; module-scoped fixtures are torn down before the module is measured. Proof: `tests/unit/test_module_heap.py`.
  On `main` without #553 it fails the reference families' modules on both versions: 4 at import
  (`test_reference_concurrency`, `_control_keys`, `_layout`, `_writers`, 2.4 to 2.7 M blocks) and 7 after their tests
  (`_dashboard_routes`, `_entry_points`, `_interfaces`, `_machine_writes`, `_machines`, `_stg02`, and the unit
  `test_reference_machine_controls`, 2.2 to 2.3 M blocks each). With #553 and this change they pass (1,306 tests, 3.11
  and 3.13), and the fast lane passes it in serial (6 chunks, 10,016 tests; its only failures were the container's known root-account baseline): no module kept more than 27,376 tracked
  objects after its tests (`test_discovery_rules`), and the largest import a module kept for itself was 91,656 blocks
  (`tests/acceptance/test_at14_at17_harness.py`).

| What | Where | Copies | Cost | Required? | Now |
|---|---|---|---|---|---|
| A parse of `src/aew` (`Context`) in a module global | the 12 reference-family modules | 12 per serial process | 2.2 M blocks each; 12.1 M objects, 2.4 GB together | No | One per process (#553), credited as shared here |
| Every Unicode character as a list, in a module global | `tests/unit/test_discovery_rules.py` | 1 per process that collects it (every xdist worker of every lane) | 1.14 M blocks (about 100 MB) | No: only the two lists derived from it are read | Walked, not kept: 36 k blocks |
| The shared parse, built at import | the first reference-family module collected | 1 per process that collects (every worker of every lane, though most run no reference test) | 2.45 M blocks and about 5 s of collection per process | No | **Follow-on:** build it on first use (the modules' `CTX`, `PROGRAM`, `BUILT` globals behind `once` functions or module fixtures), in the reference modules #553 touches |
| The register's YAML parsed at import | `test_register.py`, `test_docs_merge.py` | 2 per process | 0.47 s each; 5.6 k blocks | No | **Follow-on:** one `once` owner; both read it and deep-copy before changing it, which the change must show for every use |
| A planned Ticket built per test (`sample_project` from the template, then `create_planned_ticket`: three Lead calls) | 125 fixture sites in 182 files (`test_surface_runner.py`, `test_guard_queries.py`, ...) | 1 per test | 1.3 to 1.9 s setup per test | The copy is (each test mutates its project); the rebuild is not | **Follow-on, E42:** a snapshotted planned-Ticket starting state, under P3's snapshot-safety and equivalence rules |
| Module-scoped worlds (dashboard API, conditional, maps, ...) | 9 integration modules | 1 per shard and per worker that runs one of their tests | 6 to 75 s each (strategy §12) | Beneficial: built once per module, torn down after it | Unchanged |
| The project and sample-repository templates | `conftest.copy_test_repository` | 1 per variant per worker | one build | Beneficial | Unchanged |
| The hostile repository | `tests/regression/test_m4b_review.py` | 1 per test | per test | Required: each test mutates it | Unchanged |

The `serial` lane, run as CI runs it (`-p no:xdist`), passes the guard too (96 tests; its 3 failures are the G3
service's refusal to run as root, which fail the same way on a clean `main` here).

**Not measured here.** The integration, regression and acceptance lanes' modules after their tests in serial (only the
reference families' modules and the `serial` lane were run serially); the nightly `reference` run is the first to
measure them all, and its failure names any module over budget.
