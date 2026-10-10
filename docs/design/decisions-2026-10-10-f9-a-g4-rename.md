# F9-A amendment 2: G4 and the reason-code rename decided (2026-10-10; F9, E55)

**Status:** Decision record, governing. **Decided** by the designer on 2026-10-10 and relayed by the operator. G4 asked
whether `aew harness send` stays an unrecorded path while messaging is on; the rename gives the finality refusal of the
[steer vs queue decision](decisions-2026-10-10-f9-steer-vs-queue.md) a name that covers both timings, as the
[G2 decision](decisions-2026-10-10-f9-a-g1-g2.md) made it. §1 is the decisions as given; §2 says where they are filed.

## 1. The decisions, recorded as given

> For G4: APPROVE.
> While F9 messaging is enabled, every `harness send` should be admitted through the same message store as F9 messages, regardless of `--when next-step|turn-end`.
> That closes the exact hidden-path problem we rejected in G1. Otherwise we would have:
>
>     message send
>         recorded
>         ordered
>         evidence-aware
>         bounded
>
>     harness send
>         unrecorded escape hatch
>
> which would make the F9 evidence rules incomplete.
> So the rule should be:
>
>     messaging OFF:
>         harness send follows the non-F9 treatment rules
>         M4-H remains next-step-only as already decided
>
>     messaging ON:
>         every harness send
>             -> creates a message-store record
>             -> receives stable message identity
>             -> participates in ordering
>             -> uses --when next-step|turn-end
>             -> participates in report-finality checks
>             -> obeys the same payload limits
>
> And yes, that means the 4,000-character message-store limit applies to `harness send` while messaging is enabled. I think that is a feature rather than an inconvenience. If somebody needs to send more than 4,000 characters, it is probably no longer a coordination message; it should be a durable artifact/reference with a short message pointing to it.
> I would also make this fail closed: `harness send` must not silently fall back to the old direct/unrecorded delivery path if message-store admission fails.
>
> On the reason-code rename: APPROVE `PENDING_LEAD_MESSAGE`.
> That is better than the timing-specific name I suggested earlier because the finality rule now covers either timing:
>
>     Lead message admitted before report submission
>         + message not yet incorporated into a replacement report
>             -> PENDING_LEAD_MESSAGE
>
> The exact delivery mechanism is secondary: next-step, turn-end. The important fact is that there is admitted Lead input that the submitted report does not yet cover.
> I'd define it narrowly as:
> `PENDING_LEAD_MESSAGE` — the run submitted a report while a previously admitted Lead message remained unincorporated into a subsequent worker result.
> Then:
>
>     message admitted before report
>         -> report final-ingest refused: PENDING_LEAD_MESSAGE
>
>     message admitted after report
>         -> existing report remains valid
>         -> optional advisory about follow-on work
>
> That keeps the admission-time rule we settled earlier and avoids coupling the evidence model to OpenCode's `steer`/`queue` terminology.
> So the F9 delivery model is now pleasantly clean:
>
>     messaging enabled
>         +-- message send
>         +-- harness send
>                +--> same durable message store
>                         +-- next-step
>                         +-- turn-end
>                         +-- 4,000-char limit
>                         +-- ordering/provenance
>                         +-- evidence-finality rule
>
>     report submitted with earlier unincorporated Lead message
>         -> PENDING_LEAD_MESSAGE
>
> I'd consider G4 settled on that basis.

## 2. Filing (lead developer)

- **Ledger:** MGR-01 to MGR-07.
- **Messaging off** is built by slice HS1 (register E55): the request-file `next-step` path, with its 1 MiB limit, is
  reachable only while both the project's switch and the run's launch snapshot of it are off.
- **Messaging on: fail closed from HS1 on.** Until F9-A's MS5b builds the store path, HS1 refuses every `harness send`
  while messaging is on (`HARNESS_SEND_NEEDS_STORE`), and a run whose launch snapshot disagrees with the project's switch
  (`MESSAGING_SNAPSHOT_MISMATCH`); either way nothing is written and nothing falls back to the unrecorded path. HS1's help
  states the limit for both configurations: "up to 1 MiB (4,000 characters when coordination messaging is on)".
- **MS5b** records every `harness send` while messaging is on, with identity, ordering, `--when`, finality and the
  4,000-character limit, and posts it so that it still wakes a held session; it builds `PENDING_LEAD_MESSAGE` with the
  definition above, carried into the code, the refusal and ADR-0017.
