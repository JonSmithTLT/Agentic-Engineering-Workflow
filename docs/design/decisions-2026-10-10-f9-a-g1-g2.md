# F9-A amendment 2: G1 and G2 decided (2026-10-10; F9, E55)

**Status:** Decision record, governing. **Decided** on 2026-10-10 and relayed by the operator: G1 approves the lead
developer's recommendation for M4-H, and G2 is the designer's rule for report finality. Both answer questions the F9-A
plan's amendment 2 raised while building the [steer vs queue decision](decisions-2026-10-10-f9-steer-vs-queue.md). §1 is
the decisions as given; §2 says where they are filed.

## 1. The decisions, recorded as given

G1 asked whether M4-H's frozen treatment, which keeps messaging off, may lose the "after you finish" path that
`harness send` had through `queue`. G2 asked what a message admitted after a report's submission does to that report.
The reply:

> For G1: APPROVE the recommendation. Keep M4-H messaging off, and accept that this means there is no deliberate `turn-end` / "after you finish" path in that treatment.
> That is actually cleaner experimentally. Turning messaging on solely to preserve today's accidental queued `harness send` behavior would add a treatment feature just to maintain an incidental harness quirk. M4-H should instead freeze the simpler behavior:
>
>     messaging: off
>
>     available worker delivery:
>         next-step only
>
>     turn-end / queued delivery:
>         unavailable
>
>     reason:
>         requires message store / F9 messaging treatment
>
> So yes: M4-H measures the simpler predictable behavior. Do not turn messaging on. The accidental current queue path should not be preserved as a hidden exception.
>
> On G2, I would adopt the recommended advisory behavior, but with one important distinction:
>
>     message admitted BEFORE report submission
>         -> report is stale / not final
>         -> final ingest should refuse until resubmission
>
>     next-step message admitted AFTER report submission
>         -> report was valid for the state at submission time
>         -> do NOT invalidate it
>         -> return an advisory that follow-on in-scope work is pending
>
> So I would build the advisory only if we want the UX, not make it a gating requirement for F9-A.
> Something like:
>
>     post_report_message_pending
>
> in the ingest/result view is enough.
> That distinction should key off message admission time, not delivery time, because a message already admitted before the report but delivered just afterward is still work the report failed to account for.
> That gives us clean semantics:
>
>     turn-end message pending at submission
>         -> report cannot final-ingest
>
>     next-step message already pending at submission
>         -> same: report cannot final-ingest
>
>     message admitted only after submission
>         -> report remains valid
>         -> advisory follow-on-work note
>
> The underlying F9 reason is still the measured OpenCode behavior: `steer` reaches the next step boundary, while `queue` waits until the turn ends; queued work can therefore arrive after a report unless AEW explicitly protects evidence finality. The proposed two-timing design already identifies report staleness as the central evidence problem for `turn-end`.

## 2. Filing (lead developer)

- **Ledger:** MGT-01 to MGT-06.
- **G1** is built by slice HS1 (register E55): with messaging off, `aew harness send` is `next-step` only and
  `--when turn-end` is refused `TURN_END_NEEDS_MESSAGING`; the old `queue` default is removed, not kept for M4-H. HS1's
  pull request states M4-H's frozen treatment in these words.
- **G2** is built by F9-A's MS5b, for both timings, keyed on AEW's recording of the message (the admission the decision
  names). The plan owner made the advisory `post_report_message_pending` a committed part of MS5b, because an ingest
  seals the invocation's thread and a message admitted after the report would otherwise be lost silently.
