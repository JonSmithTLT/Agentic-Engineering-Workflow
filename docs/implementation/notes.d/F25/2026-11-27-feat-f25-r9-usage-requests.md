**R9's last part, requests built** (2026-11-27, the operator's queue of that day): `aew usage show` gives each run's
requests on the run's own line and as a `requests` line under every total, and its JSON adds `requests` to each run row
and `requests_unknown_runs` and `requests_floor_runs` to each total (`usage_ops.requests`, the rate-limit unit's ruling
2). The figure is the model calls in the run's messages (the run-usage record's `steps`, its assistant messages), and
the text says so each time: compaction, title and retried calls are not counted (#644 review, M1). A run's requests are
unknown, counted beside the sum and never as a zero in it, by cause: a missing run (usage lost), a run that reported
nothing (a run whose harness was gone), and a run with tokens but no call in its messages (its only calls were
compaction or title calls); a run whose calls the adapter stopped paging is a floor (`at least`). Nothing existing
changes meaning: a total's `steps` is still the calls counted, and `aew status`'s summary keys and line are unchanged.

**Not built, and why.** Tokens in the declared rate basis: a provider profile's `rate_basis` (ruling 1) is not in
`src`; it is the wire track's (STG-14, I-6, and E97's meter), so no basis is declared anywhere to show tokens in. The
largest request: the run-usage record holds no per-call size. The live sample's `max_step_tokens` is each counter's
largest call separately, in local, deletable telemetry, so it is not one request's context and not a ledger figure.
Showing it needs a per-run field in `aew/run-usage/v1`, computed by the adapter from its per-call counters under the
declared token semantics (unknown semantics, unknown size): a schema change for the operator and designer to approve.
Compaction, title and retried calls: the record does not carry them (its `steps` are the assistant messages; a
compaction is its own message kind, title usage is on no message, and a retry is folded into its message), so counting
them needs the record to carry them, in the same `aew/run-usage/v1` change as the largest request. Whether ruling 2's
requests include them is the designer's call; this change does not decide it by its wording.

**What remains** (2026-11-27): of R9, tokens in the declared rate basis (after provider profiles declare `rate_basis`,
STG-14), the largest request (after the record carries it), and, if the designer rules that ruling 2's requests include
them, compaction, title and retried calls (after the record carries them, in the same schema change); U4, the Lead's own
usage (`aew usage lead`), waiting for the designer's Lead part; L3 and L4, which feed the frozen F19; exact tier pricing
and fencing the `/aew-usage` report (#385's follow-ons); and U2's live-lane test (E239). SYS-11's R9 slice is narrowed
to those parts with this note.
