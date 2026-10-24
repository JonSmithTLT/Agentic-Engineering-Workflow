**The store is owner-only again (operator, 2026-10-24).** The operator cut the WIS issuer (the work-identity contract
stays), so nothing reads the store as the operator's group, and whether the operator's primary group is shared no
longer matters to it. This reverses CS-1's CB-08 modes
([`2026-10-21-feat-stg05-cs1-store-modes.md`](2026-10-21-feat-stg05-cs1-store-modes.md), #230):
- Every file in `.aew/state` is `0600` and every directory `0700`, whatever the umask (`STORE_FILE_MODE` and
  `STORE_DIR_MODE` in `aew.engine.store`). `util.write_temp` no longer takes a mode: `mkstemp` gives `0600`.
- A store written group-readable (`0640`/`0750`), or one from before CS-1 whose directories the umask left wider, is
  narrowed once, in recovery under the control lock. The store directory's and the control file's own modes record
  that it ran. A path it may not change is left for `aew doctor` to name, and never stops a command. It follows no
  link, and leaves a control file that is one for doctor to name. Where the control file stays wide after it is
  narrowed (a file system that keeps no permission bits: drvfs without `metadata`, vfat, CIFS without Unix
  extensions), it stops there rather than walk the store at every open, and doctor says so once.
- `aew doctor`'s `store-modes` names the store paths with a group or other permission bit, with the remedy `chmod -R
  go-rwx .aew/state`. The `primary-group` and `store-group` checks are gone.
- Kept as merged: CB-07's role-bind check and CB-09's lock-free reads (#231). The CB-08 store-group follow-up (#243)
  was closed without merging.
