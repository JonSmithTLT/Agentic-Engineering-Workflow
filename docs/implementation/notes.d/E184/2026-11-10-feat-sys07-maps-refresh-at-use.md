**Refreshed at use, not at publish (ADR-0015, amended 2026-11-11).** This supersedes the 2026-11-08 note's "the PR that turns the switch on at init and regenerates at each publish": nothing regenerates a map at publish. A Lead's dispatch whose selected map is STALE or absent against the work's base makes the base's map first, under that Lead's own transaction, bounded by `REFRESH_S` (10 s), and selects it at the authoritative head. A failure or timeout is one line in the pinned slice, never a failed dispatch. The added latency is the generation's: 0.67 s at 10,000 paths and 3.0 s at 100,000 (re-measure: `python tools/perf/structural_map.py --paths 10000,100000 --work DIR`), paid only on the first pack after a base change.

The 2026-11-08 note's owed items, as this step lands them:
- **The slice's reach:** the pin stays. Returning `pack` without the slice body moves to the step that turns the switch on, since the dispatch result is built in a module that step's chain owns.
- **The size record:** a byte bound (`SLICE_MAX_BYTES`, 9 KiB), `ROWS` and `HINTS` with their named source, the measured figures, and `python tools/perf/map_slice_bytes.py` to re-measure them.
- **`.aew/` and init's map:** the listing leaves `.aew/` out (generator version 2), so committing the project's state changes no map, and every existing map is STALE once.
- **A project already switched on:** moves to the step that turns the switch on, with the shared switch offer.
- **Init's time on the map:** stated in the amendment, and the quickstart's "may run again" corrected.
- **The CLI proof:** `aew init` in a repository with no commit exits 0 with `map.reason == "no_commit"`.
- **The pack's pointer to `aew map show`:** dropped.
- **`already_selected`:** now labels only a registry that selects a structural map.
