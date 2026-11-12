AEW's Git wrapper drops inherited repository-local variables before invoking Git, including when it checks driver configuration. Explicit per-call settings still work for operations such as snapshotting with a temporary index. A regression test runs Git against a target repository while the parent environment points at a decoy and verifies that only the target index changes.

AEW's Git commands ignore settings injected through repository-local `GIT_CONFIG` variables. Put settings such as `safe.directory` in the global or system Git configuration file.
