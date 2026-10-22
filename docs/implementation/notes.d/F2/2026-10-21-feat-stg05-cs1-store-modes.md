**STG-05 CS-1, CB-08 (2026-10-21): the store is group-readable whatever the umask.** Every file the engine writes in
`.aew/state` is `0640` and every directory there `0750` (`STORE_FILE_MODE`, `STORE_DIR_MODE`, owned by
`aew.engine.store`); every other file AEW writes keeps `0600`. `util.write_temp` takes a `mode` (default `0600`)
applied with `fchmod` on the descriptor, which the umask does not filter, and `atomic_write` and `create_exclusive`
pass it through; the store's one writer, `store.write_file`, picks the mode from the path, so a transition's writes
outside the store keep `0600`. A store from before this gets the modes once, in recovery under the control lock; the
control file's own mode records that it ran. `aew doctor` reports store paths below the modes (`store-modes`) and
whether the operator's primary group is user-private (`primary-group`); AEW changes no group. The output-side test
(`tests/integration/test_store_modes.py`) runs the engine under umask `077` and `002` and walks the store.
