# ADR-0005 — Lead authority, credentials, and operator-authorized takeover

- **Status:** Accepted (M1)
- **Spec basis:** WC §5 (single-authoritative-Lead, crash-safe authority), §6; KC §7.2, §16; decision D-op-3; plan review §1, §3
- **Nature:** Resolves semantic gap A2 by operator decision. The mechanism is an implementation choice.

## Decision

- **Credentials** have the form `aew1.<token_id>.<secret>`, where the secret is 256-bit random. Control state stores only a verifier (`sha256(secret)`) plus scope, issuance, expiry and revocation. Any separate process can verify a presented credential, and the raw secret is never written to disk: packs carry only a placeholder, and a test scans the files for leaked secrets.
- **Lead generation** increases on every acquire, handoff accept or takeover. Each of those atomically revokes every superseded credential. A stale Lead write fails `STALE_AUTHORITY` before any state-dependent answer is given. Every control mutation also requires `--expect-rev` (compare-and-swap).
- **Invocation credentials** are scoped to (invocation, archetype, work unit, generation) and to the operations of the archetype's role table. They are revoked on completion, cancellation, takeover, or a handoff that does not carry them.
- **Takeover** requires out-of-band operator authorization. The engine itself reads a one-time challenge answer from the controlling terminal (`/dev/tty`, or the Windows console). There is no flag, environment variable, stdin input or API parameter that authorizes. Without a terminal it fails with `OPERATOR_AUTHORIZATION_REQUIRED`.

## Consequences and limits

- Credentials guard against accidental cross-role writes and stale writers. They are **not** an OS security boundary: all roles run as the same OS user.
- A same-UID agent that deliberately fakes a pseudo-terminal or patches the process is outside the M1 threat model (accepted by review).
- Designed follow-ups:
  - an operator-issued one-time token held outside the agent's reach;
  - an approval artifact;
  - formal Lead-lease expiry with an atomic new authority epoch.

  The `lead` record is schema-versioned, so these can be added without migrating state.
- Test-runner note: on Windows, CLI test processes use `CREATE_NO_WINDOW`. An earlier `DETACHED_PROCESS` run made console windows flash and put a real operator prompt on the developer's screen.
