# ADR-0005 — Lead authority, credentials, and operator-authorized takeover

- **Status:** Accepted (M1). Amended for M3 (2026-09-29): credential custody and rotation.
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

## Amendment 2026-09-29 — M3: credential custody, stdin handoff and rotation (ADR-0009)

The credential scheme is unchanged: same form, same verifier, same scopes. What M3 adds is where a credential may live, and one way to re-issue it.

- **Custody (operator requirement).** No raw AEW credential ever enters a model-controlled process, whether an invocation's or the Lead's.
  - A harness run's credential is written to its supervisor's **stdin pipe**, never through argv, an environment variable or a file. The supervisor holds it in memory and serves a run-scoped bridge. The agent acts through the bridge and never possesses the credential.
  - The Lead's credential is held by a **Lead broker** (`aew lead session`, `aew opencode`): taken in-process with `--acquire`, or from `AEW_LEAD_TOKEN` in the operator's own shell, which is removed from the session's environment.
  - The broker **refuses credential-emitting commands** (`lead acquire|takeover|release`, `lead handoff offer|accept`) and dispatch without `--launch`, and redacts credential strings from everything it returns.
  - The explicit-credential path (`AEW_INVOCATION_TOKEN`, `AEW_LEAD_TOKEN`, `--token`) remains for scripted roles, tests and the operator's own terminal.
- **Dispatch with `--launch` withholds the credential.** It is removed from the command's output and handed to the run's supervisor. A dispatch without `--launch` still prints it (M1 behaviour), and that credential dies at the invocation's first launch.
- **Rotation is re-issuance, not new authority.** Every `aew harness launch` of an existing invocation revokes its current credential with reason `rotated: R-…` and issues a new one with **the same scope**, in the commit that records the new run (`rotate_invocation_token`). At most one run can act for an invocation.
  - A rotated credential presented to the engine is `STALE_AUTHORITY`, naming the rotation.
  - Oracle rule 17: no evidence postdates the revocation of its own credential. Rule 18: at most one live run per invocation, and while the invocation is active its latest run holds its credential.
- **Takeover is unchanged.** It stays operator-at-terminal; no broker or harness can perform it.
- **Threat model unchanged.** Custody closes inheritance, printing, transcripts and files, the accidental and persistent exposure paths. It is not an OS boundary: a same-UID process can still read the supervisor's memory on Windows (ADR-0009, "Residual risk"). On Linux the supervisor is non-dumpable.
- **Evidence:** the five custody properties, on both the invocation and the Lead side (`harness-conformance.md` §3); AT-17; the step-2 focus cases (`m3-ambiguity-report.md`); the dogfood's credential scans, clean in all 47 runs (`m3-dogfood-report.md`).
