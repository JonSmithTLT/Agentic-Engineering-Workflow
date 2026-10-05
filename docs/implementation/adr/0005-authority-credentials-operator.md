# ADR-0005 — Lead authority, credentials, and operator-authorized takeover

- **Status:** Accepted (M1). Amended for M3 (2026-09-29): credential custody and rotation. Amended 2026-10-05: a fourth credential kind, `service`, for project-scoped service principals (ADR-0013 D9; designed, built with M6b).
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

## Amendment 2026-10-05 — a fourth credential kind, `service`, for project-scoped service principals (ADR-0013 D9)

ADR-0013 D9 accepted one non-Lead committer: a project-scoped `knowledge_service` principal that may commit a closed
`knowledge.*` transaction family and nothing else. This amendment gives it a credential. The scheme is unchanged:
same form, same verifier, same issuance and revocation fields, same custody rules. The text follows the D9 spike
(`docs/research/knowledge-service-identity-spike-2026-10-04.md`), which proved the boundary on a review branch on
Windows and on Rocky 8.10, the operator takeover through a real pty included; the designer approved the direction on
2026-10-05 and decided the one open question (expiry). **Designed, not built:** the implementation lands with M6b
(register F21). Until then nothing issues a `service` credential.

- **Kind.** `tokens[*].kind` gains `service`, beside `lead`, `invocation` and `handoff_offer`. Same form
  `aew1.<token_id>.<secret>`, same verifier, same `issued_at`, `expires_at`, `revoked_at` and `revoke_reason`.
- **Scope `{service, family, issued_by}`, and no generation.** `service` names the principal
  (`knowledge_service`), `family` the one transaction family it may commit (`knowledge`), `issued_by` the Lead actor
  that issued it (kind, session label, generation). The credential carries no Lead generation because it grants no
  Lead authority: handoff and takeover revoke the `lead` and `handoff_offer` kinds and leave it alone, and the new
  Lead may revoke it. The registry of principals and their families is a table in code (`SERVICE_FAMILIES`), never
  data the credential carries, so no issuance can widen a family.
- **Issued, rotated and revoked only by the Lead.** `aew service issue <principal>` (Lead credential, `--expect-rev`)
  is a Lead transition `service.issue`: it revokes the principal's previous credential (`rotated by the Lead`) and
  issues the new one in the same commit, printing the secret once, to the terminal, as every credential-emitting
  command does (ADR-0009, amendment of 2026-10-04). `aew service revoke` ends it; `aew service show` shows the token
  id, issuance and issuing generation, never the secret. At most one live credential per principal (ADR-0013 oracle
  rule 33). The principal cannot mint, extend or rotate itself: `service.issue` and `service.revoke` are Lead
  transitions, `require_lead` and `require_invocation` refuse a service credential, and it cannot acquire, offer,
  accept, take over or release the seat.
- **One closed transaction family, enforced by the store.** A service credential admits exactly one family.
  `Kernel.service_txn`, beside `lead_txn`, checks the kind, the family and `--expect-rev`, requires a v2 project and
  the manifest pin, and commits once. The control store refuses at commit, before validation and before anything
  touches disk, any transition under a service actor that changes state outside the family: only the family's keys
  (`knowledge` and its counters, `cold` through the one history append, `revision` and `last_transition`) may differ
  between the committed state and the proposed one, every staged or pre-written path must lie under the family's
  directories (`knowledge/`, `history/`), and the op must carry the family prefix. The refusal is
  `TRANSACTION_CLOSURE`; `control.yaml` is unchanged and no redo record is staged. Because the store compares states
  rather than trusting the caller, a bug in a higher-level operation or a hostile call site reaching `Session.commit`
  fails the same way as a command-layer attempt. ADR-0013's oracle rule 29 (the closed service transaction) is
  thereby an enforced property, not only a tested one.
- **A service transaction archives nothing.** It runs none of the Lead transaction's finalizers (archival, and
  from M4-D3 the queue step, which may write `queue` on a project created before the queue existed, a write outside
  the knowledge family that the store would refuse): it appends its own history entries and archives no unit, ends no
  credential and prunes no observation. Finished work waits for the
  next Lead commit, so a service commit is never mistakable for the Lead's in effect.
- **Custody is the Lead's.** No raw service credential enters a model-controlled process. The Lead broker refuses
  `service issue` as it refuses the Lead's credential-emitting commands (ADR-0009); the agent environment allowlist
  never carries `AEW_SERVICE_TOKEN`; the secret is never written to a file (the store holds the verifier); outputs
  are redacted. `AEW_SERVICE_TOKEN` is the explicit-credential path for the service's own process, as
  `AEW_LEAD_TOKEN` is for the operator's shell. Where the capture service's process keeps its credential is an M6b
  decision (an `aew knowledge serve` broker like `aew lead session`, or a supervisor-held stdin handoff as for runs);
  either reuses an existing custody pattern.
- **No mandatory expiry in v1 (designer, 2026-10-05).** `expires_at` exists on the record and stays unused for service
  credentials. A forgotten principal is ended by the Lead (`service revoke`), by the next Lead after a handoff or
  takeover, or by operator policy. A later version may set an expiry without changing the record's form.
- **Threat model unchanged.** The credential is a scoped capability inside this ADR's same-UID model, not an OS
  boundary. What it adds is a second durable committer whose every commit the store confines to one family; what it
  does not add is a second workflow authority, a second state machine or a Lead substitute (ADR-0013 D9).
- **Evidence (the spike, not yet the main line):** `tests/integration/test_service_identity.py` on the review branch:
  issue, rotate and revoke; a knowledge commit that changes nothing outside the family; closure enforced by the store
  whatever layer asked, including a commit straight through `store.session()`; the credential refused everywhere
  outside its family; a cooperative handoff and an operator takeover leave the principal valid and the new Lead able
  to revoke it; the secret in no file, output or agent environment; `MIGRATION_REQUIRED` on a v1 project.
