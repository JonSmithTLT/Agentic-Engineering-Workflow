# Designer decision of 2026-10-10: steer vs queue (F9, E55)

**Status:** Decision record, governing. **Decided** by the designer on 2026-10-10 and relayed by the operator. It answers
the lead developer's question after the F9-A MS0 delivery probe ([ADR-0017](../implementation/adr/0017-coordination-messages.md)
D8, [evidence](../implementation/adr/evidence/f9a-delivery-probe-2026-10-10/probe-results.md)): OpenCode 2.0.18's `steer`
reaches a worker at its next step boundary, while `queue`, which `aew harness send` then used, waits until the turn
would end. §1 is the decision as given; §2 says where it is filed. The F9-A plan's amendment 2 builds it, with the
[G1 and G2 decisions](decisions-2026-10-10-f9-a-g1-g2.md) and the [G4 and rename decisions](decisions-2026-10-10-f9-a-g4-rename.md)
that refined it the same day.

## 1. The decision, recorded as given

The three questions: whether to expose one delivery timing or two (Q1), what happens to a report produced while a
`turn-end` message is still pending (Q2), and which timing is the default (Q3). The designer's reply:

> Q1: B — two explicit timings. OpenCode actually gives us two meaningfully different behaviors: `steer` reaches the worker at the next step boundary while `queue` waits until the turn would end, and the plan recommends exposing them as `next-step|turn-end`.
>
> Q2: refuse final ingest with a named reason, rather than ingesting and then marking the report superseded.
> I would use something along the lines of:
>
>     PENDING_TURN_END_MESSAGE
>
> A report produced while an admitted `turn-end` message remains undelivered is known not to be final. We shouldn't first admit it as final evidence and then mutate its interpretation. The submission can remain historical/run telemetry if useful, but the authoritative result-ingest transition should fail until the queued addition is handled and the worker submits again.
> The ingest check and message state need to be atomic/CAS-bound so we don't race "report accepted" against "turn-end message admitted."
>
> Q3: default `next-step`. That's the predictable current behavior for corrections and answers. `turn-end` should be deliberate because it changes evidence-finality behavior.
>
> So F9 becomes:
>
>     aew message send --when next-step|turn-end
>     aew harness send --when next-step|turn-end
>
>     default:
>         next-step
>
>     next-step:
>         steer
>
>     turn-end:
>         queue
>
>     pending turn-end message:
>         report cannot final-ingest
>
>     after queued work completes:
>         worker submits again
>
> That is cleaner than leaving `harness send` as an accidental secret second delivery mode.

## 2. Filing (lead developer)

- **Ledger:** SVQ-01 to SVQ-05. ADR-0017's CMG-34 records the same decision in the ADR.
- **`aew harness send --when`** is register E55, built by slice HS1 of the F9-A plan's amendment 2: the default
  `next-step` posts `steer`. With messaging off, `turn-end` is refused, as the [G1 decision](decisions-2026-10-10-f9-a-g1-g2.md)
  has it.
- **The Lead's message send** takes `when` as the typed `message_send` row's argument (F9-A has no `aew message send`
  command), in MS3 or MS5b, whichever is second.
- **The reason code** was renamed `PENDING_LEAD_MESSAGE`, covering both timings, by the
  [G4 and rename decisions](decisions-2026-10-10-f9-a-g4-rename.md); F9-A's MS5b builds it with the atomicity this
  decision asks for.
