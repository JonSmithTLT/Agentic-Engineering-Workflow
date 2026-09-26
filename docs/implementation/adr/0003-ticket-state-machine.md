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

## Amendment 2026-09-26 — independent review (M2, M5)

The table above is unchanged. The review found two places where cross-state obligations were enforced by state *names* instead of by what the state carries.

- **Replacing the plan ends the attempt (M2).**
  - When `plan.accept` takes a Ticket out of REPLAN_REQUIRED, the Ticket's workspace stops being live (`released (replanned: …)`) and every active invocation of the Ticket is cancelled, which revokes its credential.
  - The next assignment allocates a fresh attempt from the authoritative ref. The old branch and worktree are kept for provenance and inspection.
- **The serial cap counts live workspaces (M2).** Disposition B6 is unchanged in intent: a mutating Ticket counts while it holds a live workspace (`workspace.status == active`), **whatever its state**. A READY or BLOCKED Ticket can no longer hide one. Assigning a Ticket that still holds its own live workspace is refused.
- **Invocations stay bound to their workspace (M2).** Each invocation records the workspace (or integration candidate) it was dispatched for, and every check run and report submission resolves *that* workspace, and only while it is still live. An invocation is never retargeted to a later attempt of the same Ticket.
