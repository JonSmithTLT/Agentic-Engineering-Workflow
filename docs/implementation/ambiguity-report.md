# AEW M1 — Specification Ambiguity Report

**Basis:** frozen spec set `aew-frozen-2026-09-25` (tag `aew-spec-frozen-2026-09-25`):
Workflow Contract v0.7 (**WC**), Knowledge Contract v0.4 (**KC**), manifest v0.2,
SPT remediation appendix v0.2 (**SPT-R**).
**Status:** reviewed by the operator on 2026-09-25. Plan approved to begin Step 0.

These dispositions are implementation-level decisions. None of them changes normative
workflow, authority, state or knowledge semantics, so no contract version bump is needed
(manifest `freeze_rule`). Each decision will be recorded as an ADR under `adr/`, and as an
AEW Decision record once the engine exists.

**Verdict:** no architecture blockers for the M1 serial vertical slice.

## A. Semantic gaps, resolved by operator decision

| ID | Gap | Spec refs | Disposition |
|---|---|---|---|
| A1 | The failure path when post-integration validation fails or integration conflicts is undefined. | WC §8, §8.1, §13 | **Validate, then publish.** Build candidate M from authoritative commit H in an integration workspace. Verify M. Publish with an **atomic ref compare-and-swap** H→M; if the ref has moved, the candidate is stale and must be rebuilt and revalidated. A failure becomes VERIFICATION_FAILED(scope = integration), which the Lead classifies. A conflict produces an integration-failed record, and the Lead chooses RUNNING or REPLAN_REQUIRED. |
| A2 | No one is named as able to authorize a non-cooperative Lead takeover (the prior Lead is lost). | WC §5; KC §7.2 | **Out-of-band operator authorization only.** In M1 this is a challenge answered on the controlling terminal. A flag, boolean, env var or reason never counts as authorization. Takeover advances the authority generation and revokes all prior Lead and invocation tokens. **Designed (future):** an operator-issued one-time token, an approval artifact, or a formally defined expired Lead lease with an atomic new authority epoch. **Candidate amendment for the next spec version:** state in the contract who may authorize a takeover. |

## B. Wording tensions, resolved without new semantics

| ID | Tension | Spec refs | Resolution |
|---|---|---|---|
| B1 | WC §8 says the "Verifier records VERIFIED/…", but control state is Lead-only. | WC §5, §8; KC §7.2, §16 | The Verifier owns the result inside its evidence. When the Lead ingests it, the engine applies the state that result mechanically determines. The Lead cannot change the result. |
| B2 | Verification result `blocked` has no matching Ticket state. | WC §6, §9.9 | It maps to VERIFICATION_INCONCLUSIVE(result = blocked), and never to the dependency state BLOCKED. |
| B3 | ENVIRONMENT_OR_EVIDENCE_BLOCKED "remains blocked/inconclusive". | WC §8, §12 | It goes to VERIFICATION_INCONCLUSIVE with the classification attached. Its only exit is VERIFY_PENDING. |
| B4 | WC §8 says a mutating Ticket reaches DONE "by default" only after integration, but the transition list states it unconditionally. | WC §8 | Treated as unconditional for mutating Tickets. |
| B5 | The "typical" state model leaves out some transitions, such as regressions on stale evidence and exits from INTERRUPTED. | WC §8 | Filled in conservatively. Every regression is Lead-initiated and needs a reason, and success is never inferred. The full table is in ADR-0003. |
| B6 | What "mutating concurrency = 1" counts is not defined. | WC §8.1, §21.1; KC §25 | A mutating Ticket counts while it holds a live, unintegrated workspace. |
| B7 | SPT-R §9 step 4 says "mark imported items here as migrated", but the spec set is frozen. | SPT-R §9; manifest `freeze_rule` | The frozen appendix is not edited. The migration is recorded in `spt-remediation-migration.md` plus the provenance of the AEW Epic. |
| B8 | WC §23 numbers invariants 11–13 twice. | WC §23 | Editorial only. Invariants are cited by title. |

## C. Environment and input items (SPT only; none block AEW M1)

| ID | Item | Disposition |
|---|---|---|
| C1 | The spec says `spt-agent-toolchain`; the local repo is `security-platform-toolchain`. | **Resolved:** it is the same target. |
| C2 | The lightweight Python repository explorer is not in the external SPT repo. | **Resolved:** it exists only internally. An internal LLM built it and it was never committed externally. SPT Ticket A5 evaluates it, then adopts it as-is, generalizes/ports it, or replaces it. Until then `repository_exploration` has the Git CLI as the guaranteed fallback, the internal explorer as a candidate provider, and GitNexus as the richer relationship/impact provider. The explorer is never called "GitNexus Lite". |
| C3 | The Ghidra bridge environment variables must come from the audited environment, which is not in the repo. | **Open.** SPT-R P0-4 stays BLOCKED until the operator supplies it. Variable names must not be invented. |
| C4 | The SPT working tree has uncommitted WIP on branch `python-whl-1.2`. | No SPT changes until the operator commits or stashes it. |
| C5 | OpenCode, GPT-5.4 and Rocky 8 are not available on the development host. | The M1 core is harness-neutral. OpenCode is the first adapter target (M3); the operator will install it locally. Rocky 8 validation is SPT B2/B4. |

## Other review corrections incorporated (not spec ambiguities)

- **Token verification across processes:** only verifiers are stored durably: the sha256 of a 256-bit secret plus its scope, revocation and expiry. The raw secret is never written to durable state.
- **`aew init`:** discovers **candidate** authority sources only. A Lead or operator acceptance is what records a source as authoritative in `project.yaml`. Uncertain classifications go to OPEN-QUESTIONS.
