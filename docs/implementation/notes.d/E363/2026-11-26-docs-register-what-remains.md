**What remains** (2026-11-26): the shared reference parse built on first use, not at import (the reference modules'
`CTX = reference_render.context()`); one `once` owner for the register's YAML (`tests/unit/test_register.py` and
`tests/unit/test_docs_merge.py` each parse it at import); and the integration, regression and acceptance lanes
measured in serial. The snapshotted planned-Ticket state is E42's. **Done:** one parse of `src/aew` per process, #553;
the owner, the module heap guard and the clear cases, #559.
