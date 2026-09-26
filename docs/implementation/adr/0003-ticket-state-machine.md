# ADR-0003 — Ticket transition table

- **Status:** Accepted (M1)
- **Spec basis:** WC §8 ("a typical Ticket state model" plus mandatory transition rules); ambiguity report B1–B6
- **Nature:** The mandatory rules are normative. The unlisted transitions are conservative implementation choices.

## Decision

`aew/engine/transitions.py` is a table of `(from, to) → Rule(via, reason_required, guard)`. `via` names the only operation allowed to perform the transition:

| via | transitions |
|---|---|
| `recompute` | BLOCKED ⇄ READY (engine, inside every Lead commit) |
| `assign` | READY → ASSIGNED |
| `review.ingest` | REVIEW_PENDING → REVIEW_PASSED / REVIEW_FAILED (from the Reviewer's disposition) |
| `verify.ingest` | VERIFY_PENDING → VERIFIED / VERIFICATION_FAILED / VERIFICATION_INCONCLUSIVE; COMMIT_READY → VERIFICATION_FAILED (post-integration) |
| `verify.classify` | VERIFICATION_FAILED → RUNNING / REPLAN_REQUIRED / VERIFICATION_INCONCLUSIVE (Lead classification only) |
| `integrate.publish` | COMMIT_READY → DONE |
| `plan.accept` | REPLAN_REQUIRED → BLOCKED / READY |
| `reconcile` | INTERRUPTED → a phase no later than the interrupted one |
| `transition` | Lead moves with guards: start, advance to review/verify/commit-ready, regressions (reason required), cancel/escalate/replan (reason required) |

Conservative fills:

- Every regression needs a recorded reason and writes a decision.
- VERIFICATION_FAILED cannot be escalated around its classification.
- INTERRUPTED work is reconciled only after an inspection record, and never forward of its phase.
- A mutating Ticket counts against the serial cap while it holds a live, unintegrated workspace.
- Phases are skipped only when the effective gates do not require them: RUNNING → COMMIT_READY applies only if neither review nor verification is required.

Bounded role invocations are retired once their artifact is accepted (WC §5). Work returning to RUNNING gets a fresh implementer whose pack carries the findings or failure evidence.

## Consequences

A generic `aew work transition` cannot impersonate ingest, classification, assignment or integration. A table-driven test checks every state pair against every operation.
