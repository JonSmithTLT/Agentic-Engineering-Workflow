# Response to the independent M3 review (2026-09-30) and the AEW-Lead review of the same tag

- **Reviewed:** tag `aew-m3-freeze-2026-09-30` (`9372f44`). The tag does not move; the fixes are on `fix/m3-review-findings`, after it.
- **Independent review (2026-09-30):** a plain LLM review (GPT 6 Sol) from the M3 review kit. Verdict: not accepted, on R1 (Blocker) and R2 (Major), with probes. One further item (N1) was raised as an unverified lead.
- **AEW-Lead review (2026-10-01):** the same prompt and model, run as AEW work under an AEW Lead on a scratch clone of the tag. A dogfood comparison, not a second independent review: AEW reviewing AEW cannot be the acceptance verdict. It found one new defect (B1) and the R2 class; it missed R1.
- **Adjudication:** every finding was checked against the code at the tag. No false positives. The reviewer's four probes failed at the tag as reported.
- **Fix commit:** `812b492`. Local Windows: the full suite 1023 passed, 4 skipped (POSIX-only), and the serial lane 10 passed, 1 skipped.

Every regression is in `tests/regression/test_m3_independent_review.py`. Each was seen failing at the tag (11 of 11) before its fix.

## Findings

| ID | Source | Finding | Adjudicated | Fix |
|---|---|---|---|---|
| R1 | independent review | A run's supervisor acted on any request file in its model-writable run directory, so one agent could stop another run or deliver a message to an independent reviewer without the Lead | Major (Blocker defensible) | Lead requests are recorded in control state, with the file's digest, before the file is written. The supervisor acts only on a recorded request, once; anything else is logged as `request_refused` and discarded. ADR-0009 amendment. |
| R2 | both | The capability probe's field list was incomplete and checked names only: the independent review removed assistant `content` and `agent` and the message page's `data` and `cursor`; the AEW review removed `Permission.Rule.effect` and retyped `Config.AgentEncoded.model` to a string. Health passed each time | Minor to Major (run telemetry only; no gate reads these fields) | `REQUIRED_FIELDS` lists every field the adapter reads or sends, each with the JSON type it relies on; a missing or retyped field fails health. ADR-0009 amendment. |
| B1 | AEW-Lead review | Accepting a plan superseded only the accepted plan. An older revision still marked proposed could be accepted afterwards, rebinding its own assurance and dropping the review a newer plan required. The independent review had reported no bypass of plan assurance | Minor to Major (Lead-only; undoes the UAT-1 binding silently) | A revision is acceptable only if it was proposed against the plan accepted now. This also closes a revision proposed before an acceptance skipping the reason a supersession needs. ADR-0006 amendment. |
| N1 | independent review (lead) | On Linux, `/proc/<pid>/environ` may keep `OPENCODE_PASSWORD` after the server deletes it from its environment | Open lead, unverified | Not changed. To be checked on the Q7 Rocky distro. |
| B3 | AEW-Lead review | POSIX descendants started with `setsid` can outlive a check | Already documented (E13) | None. |

## Where the fixes go beyond the findings

- **R1** also covers the stop a relaunch sends to the run it supersedes: it is recorded in the relaunch commit. A request is refused if its name is unrecorded, its content or kind differs from the record, or it was already handled; a replayed file is therefore refused. Refusals go to the event log only, so a flood of files cannot grow the run record. A message's text stays in the file; only its digest enters control state.
- **R1, trust level.** Control state is what the supervisor already trusts to end a run's authority. A same-user process that rewrites `control.yaml` and its checksum remains outside the ADR-0005 threat model; the fix closes the path that needed only an ordinary file write.
- **R1, behaviour change.** `aew harness stop`, `send` and `interrupt` now commit one control revision each (the request record). They still need no `--expect-rev`, like the Lead seat operations, and work and invocation state do not change. One M3 test that asserted an unchanged revision after a stop now asserts one more.
- **R1, teardown.** The test lab stops live runs through the Lead and, when its token no longer holds the seat, ends the supervisor process (`runlog.end_supervisor`, with the same pid-reuse check as before). The dogfood harness's teardown, which holds no Lead credential, does the same. Any same-user process can already end a process, so this adds nothing an agent lacks.
- **R2** covers more than both reviews found: tool `name` and `type`, idle `type`, and every configuration key AEW sets, each typed. A field the served schema declares without a type passes.

## Operational findings from the AEW-Lead run

Recorded as post-M3 work in `future-work.md` §8 (V1 to V4): a provider key expiring mid-run, the Lead seat held after the wrapper exits with an invocation active, the Lead declining plan-bound assurance on review work, and long checks that cannot finish inside an agent's shell.
