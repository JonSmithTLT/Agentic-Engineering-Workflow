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
| `integrate.validate` | COMMIT_READY → VERIFICATION_FAILED (post-integration, checks mode: the same edge, from the engine's own check evidence; M4-D5) |
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


## Amendment 2026-10-05 — engine custody invocations (M4-D3)

Until now every invocation was a role invocation: a role, a credential, an execution profile, and usually a harness run. M4-D adds a second **kind** of invocation (the M4-D plan §1.2, operator 2026-10-04):

```text
invocation kind: integration_attempt
execution: engine (non-model)
harness: none
model: none
```

- **What it is.** The integration queue lease's custodian. It is created in the transaction that grants the lease (`aew integrate prepare`, through the `integrate.prepare` dispatch decision, which admits it) and ended in the transaction that releases it.
- **What it is not.** It is not a role invocation and is never modelled as one:
  - it has no role, credential, execution profile or run;
  - its ids are a series of their own (`IA-0001`), so role invocations keep their numbering;
  - `integrator` may appear as a label, never as a role.
- **Its records.** It is on its Ticket's invocation list and is archived with the Ticket. The post-integration verifier records it as `custodian`: the verifier is its child.
- **Its statuses.** It uses the existing invocation statuses:
  - `completed` when its lease ends normally (published, a conflict, a stale candidate);
  - `cancelled` when its Ticket leaves COMMIT_READY or the Lead cancels it;
  - `interrupted` by a takeover or an uncarried handoff.
- **What does not end it.** The state hooks that cancel a Ticket's invocations (terminal states, a released workspace) leave it to the queue, which ends it in the same transaction.
- **Death means reconciliation.** When it stops being active while its lease is held, the lease is marked for reconciliation and its children are cancelled. ADR-0004's amendment of today says what reconciliation does.
- **No Ticket state changes.** A Ticket waits on its custodian in no phase, so losing one never makes a Ticket INTERRUPTED.

## Amendment 2026-10-05 (2) — engine-produced check evidence (M4-D5)

AEW's deterministic machinery may produce check evidence under a custody invocation. That evidence names `producer.kind: engine` and its validation run (`producer.validation_run`). It is never judgment evidence, and the custodian still never implies a role.

- **The producer.** `producer.kind` is new and optional: `engine` or `role_invocation`. A record without it is a role's, as every earlier record is, and keeps its meaning; nothing is migrated.
  - `role` is required only for a role's record. The schema refuses it on an engine record.
  - An engine record is only ever a `check_result`, names its validation run, and was produced under one of its Ticket's `integration_attempt` custodians (oracle rule 41).
  - A submitter can never supply `kind` or `validation_run`: like the rest of the producer, they are the engine's.
- **The custodian hosts the run, it does not perform it.** The IA invocation is where the checks ran, under which lease. It gains a counter of its validation runs, and nothing else: still no role, credential, execution profile or harness run (oracle rule 36).
- **The transition.** In checks mode, a failed check moves the Ticket COMMIT_READY → VERIFICATION_FAILED through `integrate.validate`: the edge `verify.ingest` takes for a failed verifier, taken from the engine's own `check_result` evidence. No verifier or verification evidence is written, and `verify.ingest` is not called. The table's rule for that edge now names both operations; every other edge keeps exactly one.
- **Gate evaluation.** Ticket-scope gates count only role evidence, so engine evidence never satisfies a Ticket gate. The inherited gate `post_integration_verifier` is an integration-scope obligation: the Ticket's own gates report it CURRENT, and `integrate validate` and `publish` enforce it (ADR-0004's third amendment of today).
