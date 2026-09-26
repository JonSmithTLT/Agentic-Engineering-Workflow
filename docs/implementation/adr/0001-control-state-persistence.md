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
