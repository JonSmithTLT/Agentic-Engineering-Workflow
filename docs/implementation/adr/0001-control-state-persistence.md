# ADR-0001 — Control-state persistence: single commit point, redo staging, advisory lock

- **Status:** Accepted (M1)
- **Spec basis:** WC §5 (crash-safe control-authority rule), §8.2; KC §12.3, §27.3–4
- **Nature:** Implementation choice. The spec fixes the semantics and leaves the mechanism open: "Locking, CAS, transactional file replacement, or another mechanism may implement this behavior."

## Decision

- `.aew/state/control.yaml` is the **only** authoritative mutable control document and the **single atomic commit point**. It is written as temp → fsync → `os.replace` → directory fsync (POSIX).
- The file ends with `# aew-checksum sha256:<hex>`. Truncation or an out-of-band edit fails closed (`INTEGRITY_ERROR`) instead of being parsed as a smaller valid state.
- A transition that also creates or replaces other files first **stages** them in a redo record `state/txn/<rev>.yaml`. The new control state references that record by hash, and the writes are applied only after commit. Recovery then:
  - rolls a committed-but-unapplied transaction forward;
  - discards staged records newer than the committed revision.
- Roll-forward writes a target only if it is at its recorded before-hash or already at its after-hash. Anything else is an out-of-band edit and fails closed; it is never clobbered.
- Every engine operation, read or write, holds an OS advisory lock (`flock`, or `msvcrt.locking` on Windows) and runs recovery first. The OS releases the lock on process death, so a crash never leaves a stale lock. The expected revision is checked inside the lock, which makes each transition a compare-and-swap.
- The transition log (`state/log/<rev>.yaml`) and views such as `CURRENT.md` and `HANDOFF.md` are rebuilt from committed state. They are never authoritative.

## Consequences

- A crash at any point exposes revision N or N+1, never a hybrid. This is proven by fault injection at 8 points, both in-process and by `os._exit` in a real subprocess, plus 200 randomized crashes.
- Two concurrent writers cannot lose updates (tested with 2 processes × 50 transitions).
- Subagent evidence is immutable, create-if-absent, and outside control state, so evidence writes never race Lead transitions.
- Limits: `flock` over NFS is not relied on; the project root is expected on local disk. Windows `os.replace` is retried briefly when another process holds the file open.

## Amendment 2026-09-26 — independent review (M8)

A transition can rewrite files other than `control.yaml`; `authority accept` rewrites the project manifest. The engine used to load `project.yaml` once, when it was constructed, **before** store recovery replayed a committed-but-unapplied rewrite. After a crash at `txn.after_replace`, the first `aew resume` therefore showed control revision N+1 with the manifest of revision N: a mixed view of authoritative state. A long-lived engine could also keep serving a manifest older than the control state it had just read.

- `ControlStore` takes an `after_apply(state)` hook. It runs **inside the lock**, once the state's writes are known to be on disk (after redo recovery, and after each commit's apply), and before the post-commit render.
- The engine registers `_refresh_manifest` there. `manifest` is a property whose first access runs a store read, so recovery always comes first, and every later session refreshes it.
- The renderer never re-enters the property under the lock.
- An unreadable manifest is remembered and raised on use; `aew doctor` reports it as a `manifest` check instead of crashing.
- Pin mismatches are still refused for mutations and reported as contradictions.
- Tested: the first `resume` after a crash at `txn.after_replace` (review probe M8) and at `txn.mid_apply` of a manifest-changing transaction; a long-lived engine sees another engine's committed authority change.

### Addendum 2026-09-26 — focused re-review (M8 residual)

The hook covered every store session, but a public read that opens no session (for example `role_list()`) still served the cached manifest after another process adopted a new one.

- The `manifest` property now revalidates on every use outside a session. It compares the cheap identity (mtime, size, inode) of `control.yaml` and `project.yaml` with the identity recorded when the manifest was last loaded under the lock. On any difference (a commit, a pending recovery, an adoption), it reloads through a recovered store read.
- Both files are only ever replaced atomically, so every committed change alters the identity.
- Inside a session (`store.held`), the manifest loaded at session start is used, so the lock is never re-entered.
- Tested: the re-review's long-lived `role_list()` probe; session-free project reads after another process's adoption; a manifest read inside a session.

## Amendment 2026-09-27 — M3 step 7 (control-plane performance)

Measured in `m3-performance.md`. The design is unchanged; three implementation refinements:

- **Parse reuse for identical bytes.** A store keeps its last parse of `control.yaml` with the SHA-256 of the bytes it parsed.
  - Every read still takes the lock, runs recovery and reads the file.
  - Only bytes identical to those already parsed and verified reuse the parse. Parsing is deterministic, so this is exactly a re-parse. Any other bytes (a commit by any process, recovery, damage, an edit outside AEW) get the full parse with checksum and schema validation.
  - The parse is never handed out: `read()` returns a copy, and a session changes its own copy.
  - Long-lived processes (a run's supervisor, the Lead broker) poll the state. At 500 units, a repeated read of an unchanged state went from 1.65 s to 0.10 s.
  - Tested: `tests/unit/test_store_cache.py`. `test_no_engine_operation_changes_the_shared_parse` checks every load of a real workload against a fresh parse.
- **libyaml.** YAML is read and written through libyaml where PyYAML has it. The same Python constructors and representers run, so values and bytes are identical: checked on 4,442 real documents, and pinned in `tests/unit/test_yaml_backends.py`. At 500 units, parsing dropped from 7.5 s to 1.8 s and writing from 4.4 s to 1.3 s.
- **Profiling.** `AEW_PROFILE=<file>` records each command's phases (lock, recover, parse, render, commit, git, scan) and counts.

**Consequence, decided:** every command still costs time linear in the size of `control.yaml`, and the file grows with completed work, about 20 KB per DONE Ticket with its invocations. The operator and designer chose hot/cold control state (**ADR-0011**, 2026-09-27): terminal records move into cold records pinned by hash. That will amend this ADR's model. It is a prerequisite for M4, after M3's acceptance.

## Amendment 2026-10-04 — independent review of control-state persistence

- **Applied marker.** Once a committed transaction's staged writes are all in place, the store writes `state/txn/<rev>.applied` (by commit, or by the recovery that finished it). Recovery rolls forward only a transaction without its marker. A file the last transition staged and that changes afterwards is an ordinary out-of-band edit: the pin checks report it, and `aew manifest adopt` resolves a manifest edit. Before this, every read failed with "modified outside AEW while a transition was being applied". A crash before the marker keeps the roll-forward and its fail-closed rule.
- **The lock is the file at its path.** On POSIX, removing `local/control.lock` under a holder let a second process lock a new file at the same path. Now:
  - a taker proceeds only when the file it locked is the file at the path (inode and device), and otherwise reopens;
  - a holder checks the same before it stages anything, and refuses to commit when the file was removed or replaced.

  Windows refuses to remove an open file. `.aew/local` is disposable only while no AEW process runs (ADR-0011).
- **A derived index never fails a commit.** A transaction that needs a cold fact waits briefly (2 s) for a busy `local/history.sqlite`, then builds a private index from the history. Before this, it held the control lock for 30 s and failed with `LOCK_TIMEOUT`.
