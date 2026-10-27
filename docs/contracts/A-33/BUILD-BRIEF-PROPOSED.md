<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-33
source: 30-stages/STG-05-agent-containment-build/adopted/build-brief-2026-10-23/BUILD-BRIEF-PROPOSED.md
source-sha256: 60120ea70ffb685a17270567e549de41b7aeb2af3e9b4c7c28ec63c929e88c41
edits-sha256: none
-->

# AEW containment build brief, for the G3 and WIS gates (PROPOSED, design only)

**From:** the lead designer, 2026-10-21. **Status:** proposed; nothing here is built. The development hold of 2026-10-13 stands, and building any slice below needs the operator's exemption (section 7).
**AEW baseline:** `72035fb1`, read from git, every `file:line` below is at that commit. STG-02's slice server is read at `7d9de76b`, the tip of `feat/stg02-slice-backend` on 2026-10-21.
**Consumers:** G3 revision 5 (`g3-0.5-candidate`, `8165ecc`): G3-00, G3-12, G3-Q01 to G3-Q04. WIS revision 4 (`wis-issuer-0.4-candidate`, `17e0155`): WIS-00, WIS-01, WIS-12, WIS-Q01, WIS-Q02, WIS-Q05.

## 1. What this brief is for

Both gates fail today on AEW's side, before any G3 or WIS service exists:
- **G3-00:** the Lead runs uncontained; every worker can reach `/run/aew-g3/`; every worker has routes to the operator's display (a shared network namespace, a readable `~/.Xauthority`, a reachable `/run/user/<uid>/`).
- **WIS-00:** the Lead runs uncontained; no non-writer host process has a read-only view of the project's tree; non-writers do not all read lock-free; the store's files are `0600`; the workers' role binds are not checked against the store's path; STG-02's carrier and committing owner are one process.

This brief designs the AEW work that closes those failures, as one change set both gates consume. It does not change either gate. Where a gate's text needs to follow a ruling here, section 6 says so, and the change goes into that gate's next revision after its current review round.

**What is already designed, and only cited here:**
- **Network containment, F28** (`docs/design/network-containment-design-v0.2.md`, adopted by the designer 2026-10-06; landed in ADR-0009 as the amendment of 2026-10-05, designed, not built). Its frozen decision 2 includes the Lead. This brief builds it as adopted, and adds the gates' acceptance rows.
- **The Lead's containment, slice B4 of F47.3** (`docs/implementation/future-work.md`, F47.3): "The Lead is contained with a writable working tree: `.aew/` and git metadata read-only", the operator's harness login and the layout's secret masks masked, and no display, Wayland, X11 or D-Bus socket in the Lead's sandbox. B4 is one of the slices the hold stopped. This brief adds what the gates need beyond B4's text.

## 2. The trace

| Item | What the gates require | Gate checks | At `72035fb1` | Section |
|---|---|---|---|---|
| **CB-01** Lead containment | G3-00 and WIS-00: every agent lineage, the Lead included, runs contained; the Lead's containment profile hash is in both records (G3-12; WIS-Q01) | G3-Q01 to Q04 from the Lead's context; WIS-Q01's barrier from the Lead's context | `layout.py:36-41`: `WORKSPACE_ACCESS` has no Lead entry, so `for_run` refuses it (`:267-269`) and the Lead's TUI runs as the operator, uncontained (`harness/opencode/lead.py:1-17`). `WRITE_SCOPES` is `{"ticket"}` for every writing role (`:43`, checked at `:270-272`) | 3.1 |
| **CB-02** Network namespace | G3-00: no route through an abstract socket or a localhost port | G3-Q01: the namespace, the abstract sockets and ports each context sees | `layout.py:9-10, 90-91`: no `--unshare-net`; the harness server listens on the shared `127.0.0.1` (`harness/opencode/client.py:125`) | 3.2 |
| **CB-03** `/run` masked | G3-00: `/run/aew-g3/` and `/run/user/` masked with empty tmpfs; WIS-00 (R2-N5): `/run/aew-wis/` likewise | G3-Q01, G3-Q02; WIS-Q01 (the witness) | `layout.py:90-91`: `--ro-bind / /`, nothing under `/run` masked | 3.3 |
| **CB-04** Display credentials | G3-00: no credential that authenticates to the display | G3-Q01: with and without any readable X authority file | `layout.py:51-52`: `SECRET_FILES` has no `.Xauthority`; `lead.py:47` passes every `XDG_*` variable to the Lead | 3.4 |
| **CB-05** The terminal (designer addition) | G3-00's class: a host IPC route out of containment | G3-Q01 (proposed row) | no `--new-session` in the base flags (`layout.py:90-91`); the Lead's TUI holds the operator's terminal | 3.5 |
| **CB-06** Masks hold (designer addition) | both gates' "by every route" | G3-Q01, WIS-Q01 (proposed rows) | not measured | 3.6 |
| **CB-07** Role-bind check | WIS-00 (R3-N5): no role bind is `.aew/state`, under it, or an ancestor of it | WIS-Q01: the workers' own binds | `layout.py:288-292`: role binds unchecked; `:299-307`: only the policy's roots go through `_refuse_unsafe_root` | 3.7 |
| **CB-08** Store file modes | WIS-00 (WISD-2): store files group-readable, `0640` or wider; directories group-searchable | WIS-Q02: the modes as the engine wrote them; WIS-Q05 | `util.py:160-171`: `mkstemp` gives `0600`; `atomic_write` (`:188`) and `create_exclusive` (`:200`) publish those inodes | 3.8 |
| **CB-09** Lock-free reads | WIS-00 (R2-2): every non-writer reads lock-free only | WIS-Q01: every non-writer's reads work, lock-free, on a read-only store | `store.py:359-365`: `read()` takes the control lock and runs recovery; `lock.py:67-77` opens the lock read-only and still takes `LOCK_EX` | 3.9 |
| **CB-10** Non-writer read-only views | WIS-00: every non-writer runs with the whole tree that holds the project read-only; its unit manifest is in `processes` (WIS-12) | WIS-Q01: the barrier from every non-writer; WIS-Q09 | AEW installs no unit; the website backend is `aew dashboard`, publishing under `.aew/local/dashboard` (`dashboard/service.py:34-37`) | 3.10 |
| **CB-11** Carrier split | WIS-00: the carrier and the committing owner are separate processes | WIS-Q01: the inventory classifies them apart | the slice's one process serves the reads and the O-01 route (`stg02/server.py:86-90`); one SQLite file holds the carrier's keys and the owner's records (`stg02/ledger.py:1-8`) | 3.11 |
| **CB-12** Self-test and profile hash | G3-12 and WIS-Q01 record the containment profile hash; AEW fails closed before a qualifier runs | all of the above, mirrored | `harness/containment/probe.py`: filesystem rows only | 3.12 |

## 2a. Is each restriction worth it

Under the operator's decision of 2026-10-21 (`00-governance/decisions/2026-10-21-operator-R2-writable-Lead-tree-and-proportionate-containment.md`), a restriction stays only if it closes one of four routes for a steered agent: to an approval, to forging an owner's fact, to a credential, or out of containment, to run as the operator. One an agent notices also needs a clear message and a way to ask for more.

| Item | The route it closes | Does an agent notice it? | Verdict |
|---|---|---|---|
| CB-01 the Lead contained | all four: today the Lead is the operator | a little: no desktop, no browser tools; editing, git and tests unchanged (R-2) | keep |
| CB-02 network namespace | approval: the display's abstract socket and localhost ports; credential: the provider key | yes, for the web | keep, softened: see below |
| CB-03 `/run` masked | approval: `/run/aew-g3/`, the session bus; owner facts: `/run/aew-wis/` | no | keep; the socket inventory reports, and fails only on a socket that reaches the display, G3, an AEW service or a credential |
| CB-04 display credentials | approval: the X cookie | no | keep |
| CB-05 the terminal | out of containment: `TIOCSTI` into the operator's shell | the Lead's relay must be invisible | keep, only once CS-4 shows the TUI behaves exactly as before |
| CB-06 nested namespace | all of them, if a mask can be undone | no | measurement only; a seccomp filter only if a mask fails (R-2's mount held, `../STG-04-owner-source-qualification/evidence/2026-10-21-rl8-r2-mount-point-shield.txt`) |
| CB-07 to CB-11 | owner facts | no: AEW-internal | keep |

**The Lead's web access (decided by the operator, 2026-10-21: any public host).** For the gates, the network namespace needs to keep the Lead off the host's sockets and localhost ports, not off the internet. With R-6 (the egress proxy never connects to a loopback, link-local or host address), the Lead's egress policy could allow any public host, and the Lead's research would work as it does today. AEW's containment claims integrity, not confidentiality, so this closes every route the gates care about. It widens F28's adopted "bounded `host:port` allowlist", so it went to the operator, who allowed it (decision 3 in the record above). Workers keep F28's bounded allowlist. The AEW team amends F28's text when it builds F28.

## 3. The design

### 3.1 CB-01: the Lead's containment

**The split B4 already implies.** `aew lead session` (`harness/lead_broker.py`) holds the Lead credential and serves the Lead bridge; every Lead-authenticated write reaches the engine through it. So:
- **the broker stays on the host,** as a store writer (it opens `ControlStore.session` for the commands it relays). WIS-Q01 classifies it so, with that reason;
- **the TUI and everything it starts run in a Lead layout:** a `lead` entry in `WORKSPACE_ACCESS` with `write` access, built by the same `for_run` and `bwrap_argv`.
- **The write scopes become per role:** `WRITE_SCOPES` (`layout.py:43`) maps each writing role to its scopes, `implementer` to `ticket` and `lead` to `project`. An implementer still cannot write a project scope, and the Lead writes nothing but its project.
- **Git:** as for the implementer (`layout.py:289-293`), the Lead gets the private index and object store, with the real git metadata read-only (B4). Git commands that write the index then work without touching the real one.

**The Lead layout:**
- **writable:** the working tree (B4), and the Lead session's own run directory and scratch under `.aew/local/harness/runs/<run>/`, which hold its private OpenCode state (`XDG_*_HOME`, as the adapter gives workers, `opencode/adapter.py:172`);
- **read-only re-binds, after the working tree:** `.aew/` and the git metadata (B4), then the run directory bound back writable after `.aew/` (section 3.7 states the ordering rule);
- **masked:** everything workers have masked, the operator's harness login (B4: `.local/share/opencode`, `.config/opencode`), and sections 3.3 to 3.5;
- **network:** F28's `proxy_only` (its decision 2). The Lead's provider credential is the operator's existing login, read on the host side by the relay, never inside the sandbox. A login that refreshes (an OAuth subscription) is refreshed by the relay: not yet measured;
- **containment mode `required`** whenever a gate is claimed. A Lead that falls back to `allow_weaker` is labelled so, and both gates fail on that label.

**What the Lead loses, on purpose:** the operator's display, D-Bus session bus, clipboard and browser. OpenCode's Code Mode `browser` namespace (`aew-harness-external-facts`: 45 desktop tools) stops working. G3-00 requires that.

**The writable working tree and WIS-00.** The working tree contains `.aew/state`, so it is a writable ancestor of the store. Ruling R-2, kept by the operator, keeps B4's writable tree and shields the path with `.aew/` as a read-only mount point. WIS revision 5's WIS-00 states it, and it was measured on the target, a nested user namespace included (`../STG-04-owner-source-qualification/evidence/2026-10-21-rl8-r2-mount-point-shield.txt`).

### 3.2 CB-02: the network namespace

**Build F28 as adopted** (its section 3): `--unshare-net` for `proxy_only` and `isolated`; the secretless in-sandbox shim; the supervisor-owned credentialing relay with a fixed upstream; the separate credentialless egress proxy; checks `isolated` by default. Every agent context, the Lead's included.

**What it closes for G3-00:** the abstract-socket route (an abstract socket belongs to a network namespace) and the localhost-port route, `:6000+n` included. The path socket `/tmp/.X11-unix/X<n>` is already hidden by the sandbox's private `/tmp` (`layout.py:90-91`). For the gates `isolated` would be enough; agents need `proxy_only` to reach their model.

**One rule F28 leaves implicit, stated here (ruling R-6):** the egress proxy runs in the host's network namespace, so a target it connects to is a host route. **It never connects to a loopback, link-local or host-local address**, checked on the address actually connected after resolution, never on the name, and refuses those addresses even when the allowlist lists them. Otherwise a `CONNECT 127.0.0.1:6000` through the proxy reopens the display. The rule covers every target the sandbox can name. The relay's upstream is exempt: the execution profile fixes it, and the model cannot redirect it, so a host-local upstream (F18.8's AEW Provider Gateway, which the F28 register row composes with the relay) is allowed.

**Acceptance beyond F28's self-test:** G3-Q01's new rows. From the host, `/proc/<pid>/ns/net` of each context differs from PID 1's. From inside, `/proc/net/unix` lists no `@` socket the host holds, and `ss -ltnu` lists only the shim's ports.

### 3.3 CB-03: `/run` masked whole

**Ruling R-1: mask all of `/run`,** with an empty tmpfs after the root bind, and bind nothing back. The gates name three directories (`/run/aew-g3/`, `/run/aew-wis/`, `/run/user/`); masking each would close three paths and leave the next one open: the D-Bus system bus (`/run/dbus/system_bus_socket`), any later `/run/aew-*`, and whatever the site adds. `/var/run` is a symlink to `/run`, so it goes too.

**What may need `/run`:** under `--unshare-net` nothing resolves names inside the sandbox, so `/run/systemd/resolve` is not needed; `nscd` falls back to files. Anything else a harness needs from `/run` is a measured exception, bound back read-only by name, with its reason recorded in the layout.

**Filesystem sockets elsewhere: the inventory.** The self-test lists every filesystem socket reachable from the context (walking every mount it sees, the read-only root included). The inventory is recorded on the run's label. A socket that reaches the display, G3, an AEW service or a credential fails the launch; any other socket is reported, not refused (such as SSSD's pipes under `/var/lib/sss/pipes`), so a site's ordinary services never block a run. This is the output-side check: it finds the sockets nobody listed.

### 3.4 CB-04: the display's credentials

- **Masked files:** a new `DISPLAY_FILES` tuple beside `SECRET_FILES`, masked the same way (`layout.py:118-134`): `.Xauthority`, `.ICEauthority`, and the file `$XAUTHORITY` names when it is set at launch (often under `/run/user/<uid>/`, which section 3.3 masks already).
- **The environment:** contained processes get no `DISPLAY`, `WAYLAND_DISPLAY`, `XAUTHORITY`, `DBUS_SESSION_BUS_ADDRESS` or `SSH_AUTH_SOCK`. Workers already start from `POSIX_KEEP` (`agentenv.py:25`), which has none of them; the Lead's `tui_env` passes every `XDG_*` (`lead.py:47`), so it changes: `XDG_RUNTIME_DIR` points at a directory in the Lead's run directory, and the other `XDG_*` variables are AEW's, not the operator's.
- **What this adds to the namespace:** defence in depth. With F28 and section 3.3 in place no display socket is reachable; without a readable cookie, a socket that turns up later still refuses.

### 3.5 CB-05: the terminal (designer addition)

**The route.** On kernel 4.18, a process can push input into its controlling terminal (`TIOCSTI`), which the operator's shell reads after the program exits: commands run as the operator, outside every mask above. bwrap's base flags (`layout.py:90-91`) do not start a new session.
- **Workers:** add `--new-session` (bubblewrap's answer to CVE-2017-5226). bubblewrap 0.4.0 on the Rocky 8 VM lists it, and `--seccomp`, and has no `--disable-userns` (`bwrap --help`, 2026-10-21). A worker then has no controlling terminal, and `TIOCSTI` fails.
- **The Lead:** its TUI needs a terminal, so the broker gives it one: a pseudo-terminal the broker owns, relaying bytes and window-size changes between it and the operator's terminal. The TUI's controlling terminal is that relay's, so anything pushed lands back in the TUI's own input. The relay also drops terminal sequences that reach the desktop (OSC 52, which sets or queries the clipboard).

**Acceptance:** a proposed G3-Q01 row: `TIOCSTI` from each context is refused, or reaches only the Lead's own relay; an OSC 52 write does not change the clipboard.

### 3.6 CB-06: the masks hold against a nested namespace (designer addition)

A mask is a mount. bubblewrap 0.4.0 has no `--disable-userns`, so a contained process can create a user namespace (`unshare -Urm`), and with it the capability to unmount and remount inside it. The kernel should refuse: mounts a less privileged namespace inherits are locked, so they cannot be unmounted to reveal what is beneath, nor remounted writable. **That is not measured on the target.**

**Acceptance:** proposed rows for G3-Q01 and WIS-Q01. From inside each context, in a nested user and mount namespace, unmount `/run`, `/tmp`, each secret and display mask and the `.aew/` re-bind, and remount each read-only bind writable. Every attempt is refused.

**If any succeeds:** a seccomp filter (bubblewrap's `--seccomp`, which 0.4.0 has) refusing `CLONE_NEWUSER` in `clone` and `unshare`. It is designed, not chosen, until the measurement says it is needed.

### 3.7 CB-07: the role-bind check

**The predicate (ruling R-3).** For every writable bind `W` in a layout, the role's own as well as the policy's: `W` is not `.aew/state` and not under it; and if `W` contains `.aew/state`, the first component below `W` on the path to the store is a read-only re-bind applied after `W` in the same layout.
- **It is not the operator-root guard.** `_guarded` lists `.aew` itself, and `_refuse_unsafe_root` refuses both directions (`layout.py:202-256`). Run directories live under `.aew/local/harness/runs/` (`harness/runlog.py:31`), so applying that guard to role binds would refuse every run. The two predicates differ on purpose: a policy root over `.aew` would expose the control lock and every run's state; a role bind needs only to stay off the store's path.
- **The second clause serves the Lead** (ruling R-2): the working tree contains the store, and `.aew/` re-bound read-only after it is a mount point, so renaming, replacing or deleting it fails with `EBUSY`, and the read-only root bind covers the working tree's own parent. Workers meet the first clause alone: their workspaces are under `../.aew-workspaces/` by default (`engine/base.py:363-365`); the manifest can move them, which is why the check is needed.
- **The ordering rule:** a writable bind under a read-only re-bind is applied after it, so the re-bind cannot cover it. The self-test proves both: each writable bind is writable, and each re-bind is read-only.
- **Where:** `for_run`, on the final `writable` and `readonly` tuples, fail closed (`ContainmentUnavailable`). A real run without the project path is refused, since the check needs it.
- **Tests:** the default layout of every role passes; a layout whose workspace is the repository root without the re-bind, whose scratch is `.aew`, or whose harness directory is under `.aew/state` is refused. One test runs the check over `describe()` for every role in `WORKSPACE_ACCESS`, so a new role cannot skip it.

### 3.8 CB-08: the store's file modes

- **One owner for the modes:** `store.py` defines the store's file mode `0640` and directory mode `0750`, for the store directory `.aew/state` itself and everything under it, and nothing else. WISD-1's bind makes the issuer reach the store directly, so the modes of `.aew/state`'s ancestors do not matter; the home directory's `0701` stays.
- **The mechanism:** `write_temp` gains a `mode` keyword, default `0600`, so every other caller (credential files among them) is unchanged; it calls `fchmod` on the descriptor `mkstemp` returned, which the umask does not filter. `atomic_write` and `create_exclusive` pass the mode through, and publish the same inode. The store directory and every directory under it get an explicit `chmod`, since `mkdir` is filtered by the umask.
- **Every writer of the store passes the store's mode:** the control file, transition records, segments, compaction's outputs. The check is on the output side: a test runs the engine (create, commit, compact) under umask `077` and under `002`, then walks `.aew/state` and asserts every file is `0640` and every directory, the store directory included, `0750`. A new writer that forgets the mode fails it.
- **Stores that exist already:** a one-time engine migration, under the control lock, re-modes the existing files and records that it ran. `aew doctor` reports any store file below the modes.
- **The group:** the files' group is the operator's primary group. `aew doctor` checks it is a user-private group (named for the operator, with no members, and no other account's primary group). If it is not, WIS-Q02 fails on that site: AEW does not change the group, and creates none. **The work host is not measured** (section 7).

### 3.9 CB-09: lock-free reads

- **The allowlist:** a non-writer process reads only through `ControlStore.read_committed` (`store.py:377-388`), `configuration.read_committed(k)` (not `Kernel.manifest`, which may take the lock to recover), `outbox.LogView` (`outbox.py:340`) and `outbox.read_transitions` (`:442`).
- **Enforced at run time:** each AEW entry point declares its process kind, `store_writer` or `non_writer`, in one table. In a `non_writer` process, `ControlStore.read`, `session` and `create` raise before they open the lock. The same table is what WIS-Q01's inventory reads.
- **Contained agents read the same way.** Inside a sandbox, the `aew` CLI's local reads are lock-free, and anything that needs the lock goes through the bridge.
- **Found while designing (CBF-1, minor, availability):** today a contained agent can hold the engine's control lock. `FileLock._open` (`lock.py:67-77`) opens the lock file read-only on a read-only mount and still takes `LOCK_EX`, and the lock file is readable through the project's read-only bind, so `flock -x .aew/local/control.lock` stalls every engine writer up to its timeout, again and again. The fix: agent layouts mask `.aew/local/` whole (today only the runs directory, `layout.py:94-95`) and bind back the run's own directories; and the read-only fallback goes, since no reader needs the lock once reads are lock-free.
- **Tests:** each non-writer runs its reads against a store on a read-only bind, with zero `EROFS` or `EACCES`; in a `non_writer` process, `read` and `session` raise; from a worker sandbox, the lock file does not exist.

### 3.10 CB-10: non-writers' read-only views

**Ruling R-4: a qualified non-writer is a system unit,** installed by the operator as root beside the issuer, so its `FragmentPath` and `DropInPaths` are what WIS-12's `processes` hashes:
- `User=` the operator; `ProtectSystem=strict`; `ProtectHome=read-only` (or `ReadOnlyPaths=` the home tree that holds the project, WIS-00); `PrivateTmp=yes`; `NoNewPrivileges=yes`; empty capability sets;
- **its own state outside the project tree:** `StateDirectory=` and `RuntimeDirectory=`, the only writable paths. The website backend's publication moves there from `.aew/local/dashboard` (`dashboard/service.py:34-37`).
- **Any write path a non-writer has** (the website's Save, which F46.2 makes an adopt) goes to a store writer it calls. A process that must keep one is classified `store_writer`, with the reason.

**Outside a qualified host,** `aew dashboard` and the carrier keep starting from the CLI, labelled unqualified. That is a development mode, never a gate's evidence.

### 3.11 CB-11: the carrier split

**Two processes, where HEB's effects commit through the engine:**

| | The carrier (`non_writer`) | The owner (`store_writer`) |
|---|---|---|
| **Serves** | the D-01 reads and the O-01 route | one local socket, `/run/aew-owner/<store>/owner.sock` (`RuntimeDirectory=`, mode `0700`, the operator; agents cannot reach it, section 3.3) |
| **Reads** | the store lock-free (section 3.9); owner operations through the owner's read operation, never the owner's file | the store, through `ControlStore.session` |
| **Writes** | its own key ledger and receipts, in its `StateDirectory=` | the store only: each admitted effect commits through the engine |

**The fence moves to the owner (ruling R-5).** The slice made the key lookup, HEB's state check and its effect one `BEGIN IMMEDIATE` transaction over one file (`stg02/ledger.py:1-8`). Split, the owner's commit is the fence:
- the request key and its digest are recorded in the committed transition, so the engine's lock and expected revision decide, and a key commits once;
- the carrier records the key and digest before it dispatches, and never drops them (as the slice does), then the receipt;
- after a lost response or a carrier restart, the carrier asks the owner for the key's outcome, and the owner's answer stands.

**The observable behaviour does not change:** the same receipt on an identical retry, `409` on a key conflict, `409 unresolved_no_redispatch` once a receipt has expired. STG-02's conformance driver runs against the split, and every recorded case gives the same answer. Recording the key in the transition is an engine record change, tracked in the build plan with its own ledger row. Checking it against O01-04 and CS-04's text is part of that slice's review.

### 3.12 CB-12: the self-test, the label and the profile hash

**The launch self-test mirrors the gates,** so AEW fails closed before any qualifier runs (`probe.py` gains these rows):
1. the network namespace differs from the host's; direct egress fails; no host abstract socket is visible (F28's rows, and section 3.2's);
2. `/run` is an empty tmpfs; the socket inventory is inside the allowlist (section 3.3);
3. no display credential is readable; no display variable is set (section 3.4);
4. `TIOCSTI` is refused (section 3.5);
5. each writable bind is writable, and each re-bind and mask holds, in a nested namespace too, once section 3.6's measurement makes it a row;
6. the store's path is shielded: checked from the mount table inside the sandbox, never by trying to rename the real store;
7. the control lock is not reachable (section 3.9).

**The label** records each row's result, and the network mode (F28's labels).

**The containment profile hash:** the SHA-256 of the layout's canonical description, in template form (role, flags, masks and binds, with run-specific paths replaced by their kind), so every run of one role on one host has one hash. G3-12's environment and WIS-Q01's record carry the Lead's, and the qualifier compares them with what runs.

## 4. Slices and order

| Slice | Items | Depends on | Lane |
|---|---|---|---|
| **CS-1** the engine's side | CB-07, CB-08, CB-09 | — | unit tests; the modes and the lock on POSIX |
| **CS-2** the masks | CB-03, CB-04, CB-05 (workers), CB-06's measurement, CB-12 rows 2 to 5 | — | Rocky live lane |
| **CS-3** F28 | CB-02, CB-12 row 1 | — | Rocky live lane, a real streamed turn through the relay |
| **CS-4** the Lead (B4) | CB-01, CB-05 (the relay) | CS-2, CS-3 | Rocky live lane; an interactive TUI session that feels as it did before: editing, git, tests and the web, where policy allows |
| **CS-5** host processes | CB-10, CB-11 | CS-1 | the STG-02 driver against the split; a unit install on the VM, by the operator |

CS-1, CS-2, CS-3 and CS-5 touch different files and can run apart. CS-4 comes last, because the Lead's layout composes all of them.

**What CS-1 taught the later slices** (designer's rulings on the CS-1 report, `handoff/RESPONSE-CS-1-designer.md`, 2026-10-22):
- **The project root is required for every layout** (D-CS1-9).
- **The bind order is computed by depth** (`layout.bind_order`; D-CS1-3), and **a writable bind over a symlink on the store's path is refused** (D-CS1-7). So for CS-4, the Lead's R-2 tree needs `.aew` as a real directory, or CS-4 resolves the link before it binds.
- **The engine's process kinds are in one table** (`aew.process_kind.ENTRY_POINTS`). CS-5's non-writers are classified there, and a unit still qualifies them (D-CS1-4).
- **Concurrency facts the hand-off missed:** the compactor prunes log records without the control lock (`log_compact.py`).
- **Every review brief adds a forgotten-writer ablation** for each writer path a test claims to cover (D-CS1-13).

**What passes when all five land:** G3-Q01 to Q04 can pass on AEW's side, and so can the AEW rows of WIS-Q01 and WIS-Q02. Neither gate is qualified by this work alone: each still needs its own service built and qualified.

## 5. Not measured, and what could go wrong

- **An interactive TUI under bubblewrap behind the broker's relay:** OpenCode's input, resizing, mouse and paste. CS-4 proves it first.
- **OpenCode's TUI under `--unshare-net`:** the server on the sandbox's loopback, the provider through the relay. F28 measured `serve`, not the TUI.
- **The Lead's provider login through the relay,** a refreshing login included.
- **Masking `/run` whole:** what else a harness or a site needs there. The inventory names each need, and each exception carries its reason.
- **Locked mounts against a nested namespace on kernel 4.18** (section 3.6).
- **The work host:** whether the operator's primary group is user-private, whether SSSD's pipes are present, and the display stack.
- **systemd 239's sandboxing for a non-writer unit** with `User=` the operator, `ProtectHome=read-only` and `StateDirectory=`: the issuer's probes cover a `DynamicUser=` unit, not this one.

## 6. Designer rulings in this brief

| | Ruling | Why | Follow-up in a gate |
|---|---|---|---|
| **R-1** | Mask `/run` whole, and inventory every other reachable filesystem socket | Three named directories close three paths, not the class G3-00 names | G3-00's remedy can name the whole mask; WIS-00's sentence on `/run/aew-wis/` holds as it is |
| **R-2** | Keep B4's writable working tree; shield the store's path with `.aew/` as a read-only mount point | **Kept by the operator, 2026-10-21.** Renaming or deleting a mount point fails with `EBUSY`, measured on the target, a nested user namespace included | Done in WIS revision 5's WIS-00 and WIS-Q01 |
| **R-3** | The role-bind predicate is the store's path, not the operator-root guard | Run directories are under `.aew/local/` | WIS-Q01's "workers' own binds" row cites it |
| **R-4** | A qualified non-writer is a system unit installed by root | WIS-12 hashes unit files | none |
| **R-5** | The carrier split's fence is the owner's commit | Only the store writer can make "commits once" true | none; the slice's review checks O01-04 and CS-04 |
| **R-6** | No target the sandbox can name is a loopback, link-local or host address (the egress proxy); the relay's fixed upstream is exempt | The proxy sits in the host's namespace; the relay's upstream is the profile's, not the model's | G3-Q01 gains a row: a `CONNECT` to `127.0.0.1` through the proxy is refused |
| **R-7** | Workers start a new session; the Lead gets a relayed terminal | `TIOCSTI` on 4.18 | G3-Q01 gains a row |

None of these widens anyone's authority, changes adopted text, or changes scope. R-2 made a gate's precondition admit a writable Lead tree, so it went to the operator, who kept it. The rows marked as gate follow-ups go into the next revision of each gate, after its current review round.

## 7. For the operator

- **The hold:** building any slice here needs your exemption. B4 is one of the slices the hold stopped. The order section 4 proposes is CS-1, CS-2, CS-3 and CS-5 apart, then CS-4.
- **A fact only you can give:** on the work host, is your primary group user-private (named for you, with no other members)? If not, CB-08's design does not meet WIS-01 there, and the issuer's read access needs a different answer.
- **R-2: decided.** Kept, 2026-10-21. The Lead has a writable working tree.
- **The Lead's web access: decided.** Any public host, 2026-10-21 (section 2a).
- **No other question** in this brief loosens authority.

## 8. Not in scope

- G3's and WIS's own services, units and qualification;
- Windows (F48; `network: not_provided` stays);
- malicious code running as the operator (the threat model of 2026-10-19);
- F28's air-gap catalog seed and the checks' network setting, which F28 settles.
