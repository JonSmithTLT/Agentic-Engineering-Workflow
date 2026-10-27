<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-37
source: 30-stages/STG-03-G3-trusted-origin/adopted/g3-r7.1/G3-PROFILE.md
source-sha256: 701e7d3fd8c17d92b35450f14dd6177b7e77cdbd36af8b0e6254edf458f037e9
edits-sha256: c2fef5fb122a5bfa59e7f858fbc9ff15bfe42691d594bd6c5111afacc986ee3b
-->

# G3 trusted operator origin: Linux profile (PROPOSED, revision 7.1, 2026-10-24)

**Status:** revision 7.1 consolidates A-26 (revision 6.1, `g3-0.6.1-candidate`) with the operator's decisions of 2026-10-24. Those are the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`) and the pass over G3 and containment (`00-governance/reviews/2026-10-24-reset-pass-G3-and-containment.md`, adopted in `00-governance/decisions/2026-10-24-operator-adopt-the-G3-and-containment-pass.md`).
- **It makes no new decision.** Every change below is one of theirs, so a builder reads this one text instead of 6.1 and the decisions together.
- **It is proposed for exact-byte adoption.** Once adopted, it replaces 6.1 as G3's current text, and 6.1 stays adopted history.
- **Revision 7.1** applies the quick check of revision 7 (an independent review, NOT CONFIRMED at `b135347`):
  - C1: G3-05 restores 6.1's raised-minimum lock and the confirmer's input-source rule. The pass cut neither.
  - C2: G3-12 drops a key bullet that gave G3-08's case a second reason code.
  - N1: G3-12 states that G3 is not established until every agent's launch path runs the self-test.
  - N2: G3-00 names the sandbox's private `/tmp`.
  - Under the reset, these wording and faithfulness fixes take no further check.

**What changed from 6.1:**
- **G3-00:** the precondition is held by containment's launch self-test, not by qualification probes.
- **G3-01:** the boundaries are provided by containment, the PIN rule and the service's account.
- **G3-03:** the consequence fact is optional.
- **G3-05:** the clipboard, primary-selection and drag-and-drop rule, and the distinct-PIN confirmation, go.
- **G3-09:** a P-256 key file on every host, with no TPM path.
- **G3-10:** callers are checked by UID only. The confirmer's `/proc` identity check, `CAP_SYS_PTRACE`, the SELinux module, the system-call filter and the native-executable rule go.
- **G3-12:** G3 counts once installed, while every agent runs contained. The qualification record goes.
- **G3-14:** a root-owned install and a checked deployment file. The manifest, the directive allowlist and the file-open trace go.
- **The qualification gate** (`QUALIFICATION-GATE.md`, G3-Q01 to G3-Q11) is retired. Containment's self-test and the build's ordinary tests take its place.
- **Erratum:** the Interfaces line names the wire `g3-0.6.1-candidate`.
- **Unchanged, byte for byte:** G3-02, G3-04, G3-06, G3-07, G3-08, G3-11 and G3-13, and the wire (`g3-wire.schema.json`, `g3-0.6.1-candidate`). The wire's `QualificationRecord` is no longer used.

**Threat model:** the operator's decisions of 2026-10-19 and 2026-10-24.
- **G3 stops two things:** a contained agent faking the operator's approval, and AEW's own host code approving because of a bug or a manipulated request.
- **Out of scope:** malicious code running as the operator.
- **The PIN, the key and the sockets** follow ordinary practice.

**How the operator approves.** In a small confirmer window on the normal desktop, by entering a **PIN only the operator knows**:
- **agents,** every lineage including the Lead, cannot see the window or reach the service (G3-00);
- **AEW's host code** cannot approve, because it never handles the PIN (G3-05).

**Satisfies:** AOI-03.e (A-10), O01-04 and O01-10 (A-19), S01-15 (A-17), and A-24's pending items: the consent-set verifier, the one-use ledger handoff and issuer custody.

**Changes nothing adopted** beyond the decisions above:
- O-01 0.2 already carries `consent_set_ref` and each member's `origin_proof_ref`.
- The adopted A-24 SW-02 `set_digest` covers `request_set_ref`, `recipient_ref`, `installation_ref` and `intents`, but not `consent_set_ref`.
- The owner's consent reasons are kept as they are: `ORIGIN_NOT_ESTABLISHED`, `CONSENT_ISSUER_UNVERIFIED`, `CONSENT_EXPIRED`, `CONSENT_SCOPE_MISMATCH`, `CONSENT_ALREADY_USED`.

## Parts

| Part | Runs as | Reachable by | Never reachable by |
|---|---|---|---|
| **G3 service** `aew-g3.service`: issuer, verifier, one-use ledger, the PIN's hash and the key | systemd `DynamicUser=yes`, `StateDirectory=aew-g3`, no capabilities. Both sockets come from `aew-g3.socket` (`SocketUser=` the operator, `SocketMode=0600`) | the confirmer (`confirm.sock`); owners and clients (`request.sock`) | any agent sandbox; its state, the PIN hash and the key, from any other account |
| **Confirmer** `aew-g3-confirm`: the approval window | the operator, on the normal desktop, outside every sandbox; installed root-owned (G3-14) | the operator's display, keyboard and PIN | agents |
| **Owners** (HEB, ADC, ...): protected admission | the AEW engine, outside the sandbox, as the operator's UID | `request.sock` | none of the G3 state is writable by them |
| **Clients:** the website backend and the CLI | the operator's UID, outside the sandbox | `request.sock` | the PIN |
| **Agents,** every lineage including the Lead | the bubblewrap sandbox (G3-00) | their own workspace and model gateway | `/run/aew-g3/`, the display, G3's state and key |

## Rules

**G3-00, precondition: every agent lineage is contained.** G3 is established only on a host where every agent lineage, **the Lead included**, runs contained, with no route to the display or to G3:
- **no filesystem socket** of the display's or under `/run/aew-g3/` is reachable through any bind: `/run` is masked whole (A-33 CB-03), and the sandbox's private `/tmp` hides the X socket's path;
- **no abstract socket or listening port of the host's is reachable:** every agent context has its own network namespace, whose only egress is AEW's model relay and egress proxy, and the proxy never connects to a loopback, link-local or host address (CB-02, ruling R-6). A shared network namespace does not qualify;
- **no credential that authenticates to the display** is readable (CB-04), and no agent shares the operator's controlling terminal (CB-05);
- **no agent can read or write G3's state or key:** they belong to the service's own account (G3-09).

**Containment's launch self-test checks these for every agent context, and AEW refuses to launch an agent whose self-test fails** (A-33 CB-12, rows 1 to 6). So while G3 is installed, no agent that could reach it runs.

**G3-01, the boundaries.** A G3 approval is valid only if all three of these are outside the reach of every agent and of AEW's host code acting through its APIs:
- **the confirmer's display, its input and the PIN**;
- **the issuing key**;
- **the verifier and ledger**.

Containment (G3-00), the PIN rule (G3-05) and the service's own account (G3-09) provide them. Malicious code running as the operator's UID is outside the threat model, and so is a process the operator runs as root: administration is not an approval path.

**G3-02, approval request.** A client (the website backend or the CLI, outside the sandbox) submits the exact canonical O-01 command set to `POST /g3/v1/approval-requests` on `request.sock`. This is an `ApprovalRequest`, sent without `consent_set_ref`, and **every member already carries its `origin_proof_ref`**. The client makes each proof itself:
- the form is `proof:` followed by 32 to 64 lowercase hex characters;
- it comes from a cryptographically secure random source;
- it is fresh for each member.

The service then:
1. validates the set against the O-01 0.2 schema;
2. refuses a set containing a non-protected action: `MIXED_AUTHORITY_SET_UNSELECTED`, as CS-02;
3. refuses a proof that is malformed, repeated within the set, or already seen by this service in any earlier request: `MEMBER_PROOF_INVALID`. The service records every proof it accepts, **durably, as part of its ledger**: a restart keeps them (G3-11, R2-5);
4. computes `set_digest` with the adopted A-24 SW-02 algorithm, over the set as submitted;
5. creates a `PendingApproval` whose `expires_at` is no more than 10 minutes ahead. This is a **tripwire, not a measured value**; the deployment file may only shorten it (G3-14).

Because the proofs are part of the approved set, and `consent_set_ref` is outside the digest, the digest the operator approves is the digest of the exact set the owner later receives (G3-07).

**G3-03, rendering from records, never from text, and complete.** The service builds `PendingApproval.rendering` from exactly three sources:
1. **One `TEMPLATE` line per member,** naming its action.
2. **One `TYPED_FIELD` line for every leaf the SW-02 digest covers,** in canonical order, each showing its exact value. That means the set-level fields `request_set_ref`, `recipient_ref` and `installation_ref`, and every leaf of every intent: action, actor, authority class, owner hint, every subject and predecessor field, every target field, and the proof references.
3. **Optionally, at most one consequence fact per member, from its action's sole admitting owner** (review R3-N1; optional since the pass of 2026-10-24), read by the service itself from that owner's D-01 read, and shown with its `SourceStamp` owner and `observed_at`. A fact whose state is not `present_current` is shown with its observation state.

The service refuses two kinds of rendering, and creates no pending approval for either:
- a line without one of those sources, or whose value is not the set's: `RENDERING_UNDERIVED`;
- a rendering that leaves out any covered leaf: `RENDERING_INCOMPLETE`.

No string supplied by the client or an agent is displayed as prose. The confirmer shows the rendering exactly as served. Every covered leaf is shown, so two sets with different digests never render alike.

**A complete rendering always fits the wire (R2-1).** Every protected intent is a closed object with scalar leaves, so a member's rendering is bounded: 1 template line, its covered leaves, and at most 1 owner fact. The largest is `ISSUE_STANDING_POLICY`, at 30 lines. With O-01's 8-member limit, the largest rendering any admitted set needs is 3 + 8 × 30 = **243 lines**, which is `PendingApproval.rendering.maxItems`.
- `verify_g3.py` derives that number from the sealed O-01 schema, and fails if the wire's number differs. It also fails on an open object or an array anywhere in a protected intent, which would make the rendering unbounded.
- The other copies of the 8-member limit (`intent_refs`, `member_proofs` and the `field_path` pattern) are checked against O-01's limit the same way.

**G3-04, binding digest.** `rendering_digest` is the SHA-256 of the canonical JSON of the rendering, using the A-24 SW-02 canonicalization. The consent record binds both `set_digest` and `rendering_digest`, so what was shown is part of what was approved.

**G3-05, approval input: the operator's PIN.**
- **The PIN:**
  - root sets and resets it on the service (for example `sudo aew-g3 set-pin`);
  - it is at least 6 characters, and the deployment file may raise the minimum (G3-14). `set-pin` records the minimum the PIN was set under. **While that is below the deployment's minimum, the service treats the PIN as locked** (`PIN_LOCKED`) until root sets a new one, so a raised minimum is never only on paper (review R4-N2);
  - the service stores only a salted hash from a memory-hard function (scrypt or Argon2id), in its `StateDirectory`, mode 0600, owned by its dynamic UID. The PIN itself is never stored, logged or returned.
- **Approving:**
  - the operator approves a pending approval by entering the PIN in the confirmer, which sends it once, in the `ApprovalDecision`, over `confirm.sock`;
  - the service compares it in constant time;
  - a wrong PIN issues nothing: `PIN_INCORRECT`;
  - after 5 consecutive wrong PINs (the deployment file may lower the count, G3-14), the service refuses every approval with `PIN_LOCKED` until root resets the PIN.
- **Declining** needs no PIN. A declined or expired approval yields no consent record.

**AEW host code never asks for the PIN, receives it or stores it.** The confirmer takes the PIN only from its own window's keyboard input, never from its arguments, its environment, its standard input or any IPC, and sends it only to `confirm.sock`.

**G3-06, consent record.** On approval, the service issues one `ConsentRecord`. It has the adopted W0 consent shape (`consent_set_ref`, `issuer_ref`, `set_digest`, `recipient_ref`, `installation_ref`, `intent_refs`, `member_proofs`, `valid_from`/`valid_until`, `qualified`), plus `approval_ref`, `rendering_digest`, `issued_at`, `key_id` and `signature`.
- **`issuer_ref`** is the service's own `g3:<host-installation>` identity.
- **`intent_refs`** lists the members in set order, with no repeats.
- **`member_proofs`** maps each member to the `origin_proof_ref` it carried in the approved set. **Its keys are exactly `intent_refs`.**
- **`valid_until`** is no more than 15 minutes after approval. Like G3-02's limit, this is a tripwire (G3-14).
- **`signature`** is made with the service key (G3-09), over the canonical JSON of every other field.

**G3-07, submission.** The client fetches the record with `GET /g3/v1/approval-requests/{approval_ref}`. It then submits the approved set **unchanged** (byte for byte, after canonicalization), with `consent_set_ref` set to the record's. The invariant: **the record's `set_digest` equals the SW-02 digest of the set the owner receives.** Nothing else about O-01 submission changes.

**G3-08, consume at allocation (the one-use ledger).** At the moment the owner would allocate the member's operation (CS-06), it calls `POST /g3/v1/consume` with a `ConsumeRequest`. That request carries the SW-02 digest of **the set the owner received**, and the member's own `origin_proof_ref`. The service checks the following in order, and returns the first failure as a `ConsumeResult`:
1. **The record is genuine:** it exists, this service issued it under a current key, and it is well formed (`member_proofs` keys equal `intent_refs`, with no repeats). Otherwise: `CONSENT_ISSUER_UNVERIFIED`.
2. **The record is current:** `valid_from <= now < valid_until`. Otherwise: `CONSENT_EXPIRED`.
3. **The request matches the record:** otherwise `CONSENT_SCOPE_MISMATCH`. Each of these must hold:
   - `set_digest`, `recipient_ref` and `installation_ref` match;
   - `intent_ref` is a member of `intent_refs`;
   - `origin_proof_ref` equals that member's proof;
   - `owner` is the `sole_admitting_owner` of that member's action, in the adopted action registry, for the set the service approved.
4. **The member has not been consumed.** Otherwise: `CONSENT_ALREADY_USED`.

Otherwise the service records the member as consumed against `(owner, operation_ref)`, durably (written and flushed before the reply), and returns `CONSUMED`.
- **Each member is consumed at most once,** under concurrent calls too.
- **A refused call consumes nothing.**
- **A missing consent record** is `ORIGIN_NOT_ESTABLISHED`.

The owner maps each result to its existing refusal; that mapping is unchanged from CS-06.

**G3-09, key custody.** The signing key is a P-256 ECDSA key file in the service's `StateDirectory`, mode 0600, owned by its dynamic UID, on every host (the security depth reset of 2026-10-24: no TPM path). `key_id` is the SHA-256 of its public key.

The public key is published read-only at `/run/aew-g3/keys/<key_id>.pub`, so records can be audited independently. Rotating the key adds a new `key_id`. Records signed with a retired key stay verifiable for audit, but are no longer consumable: `CONSENT_ISSUER_UNVERIFIED`.

**G3-10, who may call.** Both sockets are filesystem sockets under `/run/aew-g3/`, never abstract sockets, created by `aew-g3.socket` with `SocketUser=` the operator and `SocketMode=0600`. On every connection the service reads the peer's credentials (`SO_PEERCRED`, which needs no privilege), and refuses `PEER_NOT_PERMITTED` unless the peer's UID is the operator's.
- **That does not separate agents from AEW's host code,** which share the operator's UID. What keeps every agent off both sockets is G3-00: `/run/aew-g3/` is not reachable from any of them.
- **AEW's host code cannot approve through `confirm.sock`,** because it never has the PIN (G3-05).
- **An identity the service cannot read is refused** `PEER_NOT_PERMITTED` (G3-11).

**G3-11, failure.** Nothing is consumed or approved in any of these cases:
- the service is unavailable;
- its ledger cannot be written;
- the clock cannot be read;
- the PIN hash cannot be read.

In each case the owner holds the protected action (`ORIGIN_NOT_ESTABLISHED` / `HELD`, O01-10), and never falls back to any other origin.

**A peer whose identity cannot be read** (G3-10) is refused `PEER_NOT_PERMITTED`, never admitted.

**A restart keeps the durable ledger:** the consent records, the consumed members, **every accepted member proof** (G3-02, R2-5), and the lockout state. Pending approvals do not survive a restart; they are lost and must be requested again.

**G3-12, when G3 is established.** Owners accept a `CONSUMED` result as G3 origin while all of these hold:
- **the service and the confirmer are installed** (G3-14), and the service answers on `request.sock`;
- **every agent context runs contained,** which AEW enforces by refusing to launch an agent whose launch self-test fails (G3-00).
  - **That needs every agent's launch path to run the self-test,** the Lead's included.
  - **G3 is not established until it does:** until CS-4 contains the Lead (A-33 CB-01), G3 is not established on any host.

If any of these fails, owners refuse with `ORIGIN_NOT_ESTABLISHED`, every protected action stays held (O01-10), and D-01 keeps the `G3_unqualified` limitation. No qualification record, independent qualifier or environment hash is required (the pass over G3 and containment, adopted 2026-10-24). A record that does not verify is G3-08's `CONSENT_ISSUER_UNVERIFIED`, not this rule's.

**G3-13, what is never G3:**
- the startup unlock (S01-31);
- an OS login;
- a website session or click;
- a CLI flag;
- a token or a gateway identity;
- a local process stop (O01-10);
- any approval that did not come through the confirmer with the PIN.

A record that only contains `qualified: true` is not G3 either. Only a G3-08 `CONSUMED` result under G3-12 is.

**G3-14, the install.** The service, the confirmer and their support files are installed root-owned under one path, which the deployment pins (for example `/opt/aew-g3/`). Nothing there is writable by the operator's UID.
- **The deployment file,** `/opt/aew-g3/etc/deployment.json`, holds the deployment values:
  - the approval expiry, at most 10 minutes (G3-02);
  - the consent validity, at most 15 minutes (G3-06);
  - the PIN's minimum length, at least 6, and the lockout count, at most 5 (G3-05).
- **The service checks them at start,** and refuses to start if a value is missing or beyond its limit. A value beyond a limit is an error, never clamped.
- **Changing the install or the deployment file** is root's administration.

## Interfaces (HTTP over the Unix sockets; bodies in `g3-wire.schema.json`)

| Method and path | Socket | Body in, out | Errors |
|---|---|---|---|
| `POST /g3/v1/approval-requests` | `request.sock` | `ApprovalRequest`, then `PendingApproval` (201) | 400 `STRUCTURAL`, `MIXED_AUTHORITY_SET_UNSELECTED`, `MEMBER_PROOF_INVALID`; 422 `RENDERING_UNDERIVED`, `RENDERING_INCOMPLETE`; 403 `PEER_NOT_PERMITTED`; 503 `G3_UNAVAILABLE` |
| `GET /g3/v1/approval-requests/{approval_ref}` | `request.sock` | `PendingApproval` with `state`, plus a `ConsentRecord` once approved | 404, 403, 503 |
| `GET /g3/v1/pending` | `confirm.sock` | a list of `PendingApproval` | 403, 503 |
| `POST /g3/v1/approvals/{approval_ref}` | `confirm.sock` | `ApprovalDecision` (with the PIN to approve), then `ConsentRecord` (approve) or 204 (decline) | 404, 409 `APPROVAL_EXPIRED`, 422 `PIN_INCORRECT`, 423 `PIN_LOCKED`, 403, 503 |
| `POST /g3/v1/consume` | `request.sock` | `ConsumeRequest`, then `ConsumeResult` | 403, 503 |

Every response carries `X-AEW-G3-Wire: g3-0.6.1-candidate`.

## Fixtures

**`g3-cases.json`, `verify_g3.py` and `verify_g3_mutation_kill.py`** are revision 6.1's, kept as a regression aid.
- **Still current:** their cases for G3-02 to G3-08.
- **Not normative:** the cases for G3-10's identity check, G3-12's record and G3-14's manifest test rules this revision cuts.
- **What replaces them:** the service build's own tests.

The reference signs with HMAC-SHA256, a labelled stand-in for the real key (G3-09).

## Out of this text

- **The build:** the G3 service starts beside STG-05's CS-4 (operator, 2026-10-23), briefed from this text.
- **The confirmer's exact layout,** beyond G3-03 and G3-05.
- **How the operator is notified** that an approval is waiting.
- **How the website shows "waiting for approval":** it uses the existing `ORIGIN_PENDING` / `HELD` states.
