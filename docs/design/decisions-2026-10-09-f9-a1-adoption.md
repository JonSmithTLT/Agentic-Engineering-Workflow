# Operator and designer decision of 2026-10-09: F9-A1 adopted, F9-A first, messaging off in M4-H (F9)

**Status:** Decision record, governing. **Adopted** by the operator and the designer on 2026-10-09. It answers the F9
decisions-due item (the adoption of the F9-A1 amendment) and the lead developer's ask that came with it. §1 is what was
asked; §2 is the decision recorded as given; §3 lists the implementation choices it accepts, as the ask listed them;
§4 says where it is filed.

## 1. What was asked

On 2026-10-09 the lead developer asked the operator and the designer to adopt
[F9-A1 v0.1](f9-a1-lead-worker-messaging-and-adaptive-supervision-amendment-v0.1.md), first-class Lead-worker messaging
and adaptive supervision, which had been ingested as a proposal that day (PR #145, ledger LWM), and to answer two
questions. **Q1:** adopt F9-A1 as governing and build F9-A, the messaging core, first? The recommendation was yes,
adopting the whole amendment so its semantics are fixed, with F9-B, F9-C and F9-D following only after F9-A is
measured, as the amendment's own staging (§25) has it. **Q2:** is messaging part of M4-H's frozen treatment, or off?
The recommendation was off: build it behind a switch, absent while off, with a byte-identity test, and measure it
afterwards as its own F19 arm, so that the frozen treatment is never silently altered (the agent-effectiveness
adoption's Revision B). The tradeoff put with it: an M4-H without messaging measures a weaker AEW than the one the
operator will use; the alternative was to amend M4-H's preregistration to include F9-A before calibration, a recorded
treatment change that delays the freeze until F9-A is built and qualified. The ask's **§4** listed eight choices
already made at implementation level (§3 below), put forward only so that they could be objected to; silence meant
they stand. Its §5 proposed the sequencing if adopted: the F9-A plan written now and taken through independent review
to CLEAR; its build planned to start after M4-E's E4 merges, when the typed-surface catalog shape is stable, with its
catalog rows switch-registered; independent of F4, Arm B and the dashboard work.

## 2. The decision, recorded as given

> Q1 — YES. Adopt F9-A1 v0.1 as governing. Build F9-A first. F9-B may proceed after F9-A technical qualification; F9-C is evidence-gated; F9-D remains empirical tuning.
>
> Q2 — Keep F9 messaging OFF in frozen M4-H. Do not amend the treatment. Build behind a switch with disabled-state identity tests, then evaluate messaging separately in F19 using the F9 A/B/C/D supervision arms.
>
> §4 — No blocking objections. Transport is provisional on the planned OpenCode live-delivery probe. “No polling” means no model-driven polling; implementation-level event/wait mechanics remain implementation-local. All other listed choices stand.

## 3. The implementation choices it accepts (the ask's §4)

As the ask listed them (lead developer, 2026-10-09). The decision makes the first provisional on the planned OpenCode
live-delivery probe and says what the sixth's "no polling" means; the others stand as written.

> 1. **Transport.** On the pinned OpenCode 2.0.18, live delivery uses the server's `POST /api/session/{sessionID}/prompt` on the worker's own session, which is in the pinned OpenAPI fixture. A probe will confirm behaviour while the worker is mid-turn. The default is delivery at the next turn boundary, never a forced interrupt.
> 2. **"Stop this approach" is a message; stopping the invocation is not.** Ending a worker stays on the existing `invoke cancel` and relaunch paths, so a message never doubles as an authority action (§11).
> 3. **The worker's reply path** is a new `aew-run` bridge operation, so requests go through the supervisor and the credential stays supervisor-side. This applies the designer's 2026-10-09 ruling on worker tool delivery: no new worker credential surface.
> 4. **The Lead's send path** is a typed-surface tool, `message.send`, classified non-dispatching and authority-free, bound to the current Lead generation. A superseded generation's message is refused, not delivered.
> 5. **Storage.** Messages are append-only coordination records beside control state, not in the hot control document. They are bound to invocation, work unit and, on F4-enabled projects, Ticket revision. They are bounded in size and count, with references rather than payloads (§10).
> 6. **The Lead learns of replies** through the attention and resume projections and, once M4-E's E7 lands, the broker's notifier. There's no polling.
> 7. **Untrusted text.** Worker replies are model-authored data, rendered fenced and escaped like all model text, and never instructions to the Lead's tooling.
> 8. **Dashboard (§23, §24).** Read projections are added after F9-A through a dashboard contract bump, the same pattern as the maps/search plan. The UI is the web developer's.

The section numbers in the list (§10, §11, §23, §24) are F9-A1's. The designer's ruling in item 3 is
[KDR-01 and KDR-02](decisions-2026-10-09-knowledge-tool-delivery-and-reviewer-independence.md).

## 4. Filing (lead developer)

- **Ledger:** LWA-01 to LWA-19. F9-A1's source (LWM) is now an amendment at its new path, and LWM-01 no longer reads
  "Proposed".
- **F9-A1** moved from `design/proposals/` to `design/` with only its status line changed. F9 v0.1, the live
  coordination design it amends, stays in `design/proposals/`, frozen at v0.1: the decision adopts F9-A1, which keeps
  F9 v0.1's invariants (its §26) and whose F9-B builds F9 v0.1's concepts (its §25).
- **Register F9:** the row records the adoption and the staging: F9-A first, behind a switch with disabled-state
  identity tests; F9-B may proceed after F9-A technical qualification (Q1 recommended "only after F9-A is measured"; the
  decision sets technical qualification); F9-C evidence-gated; F9-D empirical tuning; off in frozen M4-H; transport
  provisional on the live-delivery probe. The F9 decisions-due item is removed.
- **Register F19:** messaging is evaluated there, separately, using the F9 A/B/C/D supervision arms (F9-A1 §16 and §20:
  A no proactive supervision, B messaging available only, C AEW-recommended adaptive supervision, D mandatory periodic
  supervision).
- **M4-H:** unchanged. Q7's frozen design ([v0.3.1](q7-m4h-value-gate-experiment-v0.3.1.md)) and its preregistration
  are not amended.
- **WC/KC:** neither F9-A1 nor this decision replaces Workflow Contract or Knowledge Contract text; both are listed in
  `spec-amendments.yaml` under `considered`.
