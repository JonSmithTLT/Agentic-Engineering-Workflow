**STG-05 CS-1, the CB-08 store-group follow-up (2026-10-24): the store's group, as STG-11 amends CB-08 (A-36).**
The store (`.aew/state`) now has one target group and modes at a time: the store's group with `0640` files and `0750`
directories where WIS-01a's group is private to the operator and every running store writer holds it, and otherwise
`0600`/`0700` under the operator's primary group (D-CS1-10 and D-CS1-11 as amended). The rule is
`aew.engine.store_group.answer`, a port of the reference model's `wis01a`, checked against the model on every host it
builds; the model is vendored in `tests/fixtures/stg11-wis-r9/` with its synthetic operator name renamed. The host is
read through one seam, `store_group.HOST`; nothing in `store_group` or `store_writers` reads an environment variable,
and a test checks it.
- **The record and the walk (D-CS1-1 as extended, with its erratum and the erratum's second amendment, 2026-10-24).**
  The record is the group and mode of the store directory, of every directory under it and of the control file. Under
  the control lock, at every open and again before every commit, it is compared with the target, and where they differ
  the whole store is walked first: the control file to a mode no target has (`0400`), then the store directory, the
  other directories and the files, and the control file last to the target. So an interrupted walk always leaves the
  store marked for repair, and a store any earlier version left is brought within WIS-00's bound at its first open.
  Each path narrows, re-groups, then widens (`store_group.steps`), so no step grants anything its start or its end
  does not, and a path above WIS-00's bound is brought down. The walk changes a path only through a descriptor on the
  file it listed, and only a directory or a file the store holds alone. Every write into the store goes through the
  holder of the control lock (`store.write_file` refuses one without it), new files get their group on the descriptor
  before they are published, and new directories are made `0700` before they get their group and mode, so nothing is
  ever above the bound, even for a moment.
- **Running store writers.** Each process that opens the control lock registers in `.aew/local/writers/` (`0700`, entries
  `0600`) and holds an `flock` on its entry; an entry whose lock is free belongs to an exited process and is removed. A
  writer's own answer comes from its own credentials. A file system that refuses the group (`EPERM`) makes the process
  count as lacking it. `aew doctor` reports the store's group and its kind, root's group record and what it says, which
  part of WIS-01a fails, each running writer that lacks the group, the paths off the target with the commands that set
  each by hand in the walk's order, and whether WIS can be qualified here as far as the store goes (`store-group`,
  `store-writers`, `store-modes`, `wis-store`; the environment check `primary-group` is gone, its facts are in
  `store-group`).
- **A configured name-service source counts, running or not** (the Lead's confirmation of the plan's reading, 2026-10-23,
  under D-CS1-11 as amended: "The engine applies WIS-01a to what the host lists, and to root's group record, and to no
  signal of its own"). The listing reads every name-service database that supplies an account's groups, each line as
  glibc reads it. Every source outside the local ones cannot be listed, whether its daemon runs or not, and only a
  signal in root's record that covers the group's ID speaks for it. **This reverses the PASS that #230's m7 gave an
  idle `sss`:** a host whose nsswitch lists `sss` without running sssd (a Rocky 8 host's default authselect profile)
  keeps its stores owner-only until root's record carries a `Signal=sss ...` line covering the group's ID. `aew
  doctor`'s remedy prints the record root writes.
- **Root's group record, for the issuer's installer.** It is an `[X-AEW-Store-Group]` section (`Group=<name> <gid>`, one
  `Signal=<source> <IDs> <what shows it>` per source that cannot be listed) in the issuer instance's store-path drop-in,
  `/etc/systemd/system/aew-wis-issuer@<id>.service.d/store.conf`, where `<id>` is the 32 hex characters of the store's
  `store_ref` (`store:` and 32 hex). A record that is not root's along its whole path is ignored, and so is one that
  names the user-private group's ID under another name than the operator's (D-CS1-16). **The issuer's installer (the
  WIS issuer build) must call `aew.engine.store_group.record_path`, `parse_record` and `store_ref` (and
  `instance_id`), never restate them.** The module imports only the standard library (a test keeps it so), so a
  root-owned install can take it as it is.
