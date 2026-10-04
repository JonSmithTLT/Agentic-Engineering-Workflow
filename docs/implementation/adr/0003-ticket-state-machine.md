# ADR-0003 — Ticket transition table

- **Status:** Accepted (M1); amended for M2 (2026-09-27)
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
- **Interruption never erases a pending obligation (M5).**
  - When a Lead handoff or takeover interrupts an in-flight invocation, the invocation is always revoked and marked `interrupted`.
  - The Ticket becomes INTERRUPTED only if its current phase is **waiting on that invocation**:

    | Ticket state | Waiting on |
    |---|---|
    | ASSIGNED, RUNNING | implementer |
    | REVIEW_PENDING | reviewer |
    | VERIFY_PENDING | Ticket-scope verifier |
    | COMMIT_READY, candidate `prepared` | integration verifier |

  - Every other state is already determined by ingested evidence or by a Lead decision, and is retained. These include VERIFICATION_FAILED (which still requires the Lead's classification), REVIEW_FAILED/PASSED, VERIFIED, INCONCLUSIVE, REPLAN_REQUIRED, ESCALATED, and COMMIT_READY while `publishing`. The revocation is recorded in the Ticket's history.
  - Interruption transitions are now recorded in history as well.
  - Reconciliation still returns only to the interrupted phase or an earlier one. Since VERIFICATION_FAILED is never interrupted, no reconcile path reaches mutation or replanning without a classification.

### Addendum 2026-09-26 — focused re-review

- **A finished Ticket leaves no live credentials.** Entering a terminal state (DONE or CANCELLED) cancels every remaining active invocation of the Ticket and revokes its credential, enforced in the single state-change path. Before this, stragglers (dispatched, never used) kept live credentials past DONE. They could not write, because their workspace was no longer live, but their authority outlived the work.
- Found by the extended adversarial walk, which now also dispatches stragglers, submits reports it never ingests, submits late with any credential ever issued, and replays ingestion of any earlier report. The invariant oracle checks after every step that no report was accepted for another plan, attempt or candidate, and that no evidence postdates its credential's revocation.
- **M1 assigns mutating Tickets only (foundation review).** Assignment allocates a mutation workspace and an implementer. A `--non-mutating` (evidence-only) Ticket that received them bypassed the serial cap, which counts only mutating Tickets, and could publish source. M1 now refuses to assign or integrate a non-mutating Ticket. Its dispatch path (investigator/researcher/planner cards, no mutation workspace) arrives in M2.

## Amendment 2026-09-27 — M2: non-mutating Tickets and parents (ADR-0007, ADR-0008)

The M1 rows are unchanged, and the table-driven test still pins exactly one `via` per state pair.

- **Dispatch reuses `assign`.** `aew work dispatch` (non-mutating Tickets) performs READY → ASSIGNED through the existing `assign` rule. It allocates an executor and a read-only observation instead of a mutation workspace. `work assign` still refuses non-mutating Tickets and names `work dispatch`.
- **New rule `accept`.** RUNNING / REVIEW_PASSED / VERIFIED → DONE, guard `evidence_only_complete`, performed only by `aew work accept`:
  - It refuses mutating Tickets; they reach DONE only through `integrate.publish`.
  - It requires every effective gate CURRENT, including `execute_record` of the pinned kind for the current attempt.
  - Required findings must be resolved or waived.
- **Non-mutating Tickets are never COMMIT_READY.** Every guard into COMMIT_READY refuses them, and `integrate prepare` refuses them.
- **Phase waits generalize (M5 amendment above).**

  | Non-mutating Ticket state | Waiting on |
  |---|---|
  | ASSIGNED, RUNNING | the current attempt's executor (investigator, researcher or planner, observation scope) |
  | REVIEW_PENDING | a reviewer of the record |
  | VERIFY_PENDING | a verifier of the record |

  A parent's phase is derived, so losing a parent reviewer or verifier leaves a gate missing and interrupts nothing.
- **Attempts are explicit.** A new attempt starts only through `work redispatch`, which is a recorded decision. Reconciling an INTERRUPTED non-mutating Ticket records an inspection of the attempt (executor, its status, records submitted); it never ingests or accepts anything.
- **Parents never use this table.** `work transition <Story|Epic>` stays refused (M1 test unchanged). Parent state is derived (ADR-0007); the Lead acts through `work close` and `work cancel`.

## Amendment 2026-10-04 — the cap is the policy's (M4-C)

The serial cap of B6 becomes the policy's cap. A mutating Ticket counts while it holds a live workspace, whatever its state (as amended in M2); the number allowed is `gates.yaml` `mutating_concurrency`, default 1. M4-A read the value but clamped it to 1. The cap governs **admission**: lowering it never makes admitted work illegal, the live workspaces drain, and no new mutating workspace is admitted until occupancy is below the new cap (operator, 2026-10-04). Each Ticket has its own worktree, and integration stays serialized through ADR-0004, so nothing else in the state machine changes.

