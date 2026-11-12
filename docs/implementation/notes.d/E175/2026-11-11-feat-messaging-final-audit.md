PR 2 final author audit (not an independent review). Found and reproduced a filtered typed harness-status read
carrying 20 bodies in its payload and a different 20 in its project projection. The runner now applies the shared
UNSEEN_CAP budget across these fixed envelopes, prioritizing the requested payload and counting each envelope's
omissions. Exact carried-body verification/receipts leave the other batch unseen and recoverable. The leaf bound's
owner and accepted MCP listing budget are unchanged. This applies to typed query and wait results, not only wakes.

Requirements/test audit, with renamed or split tests grouped by their actual boundary:

| Obligation | Evidence |
|---|---|
| MS4 own-thread address/refusal, no new authority, reply idempotency and inbox limits | worker_message_cli, worker_messages, worker_message_engine, coordination_store |
| Enabled-only launch/relaunch snapshot and run/project mismatch | worker_messages, harness_send_when, harness_conformance; message_start_snapshot for Lead presentation |
| Foreground call/step/parallel/reconnect safety, grace, max bound, EOF and send failure | message_wait_binding, worker_message_lifetime, worker_wait_connections; real fake-V2 orphan shell-timeout test in worker_messages |
| Live/sealed attention, cache freshness, final reply/submit/ingest/seal, cancellation and archival | message_attention, worker_messages, coordination_lifecycle |
| Durable typed/own-shell shown; plain reads non-consuming; next commit prunes sealed seen | message_result_receipts, coordination_lifecycle |
| Relayed readable/JSON receipt scope, all local-only conditions and failure boundary | message_result_receipts, delivery_record_contract, message_wait_delivery, lead_relayed_reads |
| Stable-lock union/crash, stale/future generation, nonwriter child, reset and malformed records | told_messages, told_message_processes, message_delivery_view |
| Both wait/wake deliveries, produced reasons/holds, handler ablation, missing digest and own-shell cursor | message_holds, message_wait_delivery, message_wakes |
| Posted/told suppression, both read/post orders including own-shell typed, uncertain admission/restart, old-session resume and generation handoff | message_wakes, message_wait_delivery |
| Shared body and posted bounds, omission/recovery, two real workers exceeding 20 replies | message_wait_delivery, message_result_receipts, message_wakes, coordination_lifecycle |
| Worker data cannot spoof framing/IDs/actions/hints/blockers | message_attention, message_wakes, coordination_store credential/body bounds |
| Off identity and on-only guidance; unchanged permissions/listing cap | messaging_off_outputs, messaging_guidance, message_catalog, message_send, opencode_units and existing off launch/progress tests |
| Capability platform limits and committed qualification evidence | harness_capabilities, message_wait_binding, harness_qualify and its scripted plants; retained Linux 2.2.6 record/pin |

The consolidated off JSON/text/StageResult golden was captured using the clean pre-worker/attention source
eea24ef1, not regenerated from the implementation under test. It covers absent and explicit-disabled policy seeds
with an active assignment and no run (including the actual no-run wait refusal). Volatile paths/times/token IDs/
digests/durations are normalized; instructions, field names, body shapes and ordering are pinned. It does not prove
every project state or real ended-run output: those are separately exercised by existing progress/relayed tests.
Original system/catalog/wake pins and policy/init identity tests remain, with no fixture cap or tolerance increase.

Limits retained rather than relabelled as proof: deterministic fake/process coverage is not Windows/runtime or
provider qualification; only the approved Linux 2.2.6 record is runtime evidence. The syntax catalog reader guard
does not enumerate catalog()/check_call(), aliases, wrappers, dynamic access or same-count substitutions; controls
and the separate independent wire/prose oracle state their limits. .aew snapshot and named fault tests do not
enumerate arbitrary host I/O, every race schedule or model understanding. A crash after successful output may
re-list; an uncertain wake can hold automatic news while explicit reads/waits and durable attention remain usable.

As-built status is recorded on F9 and in ADR-0017's Build status, not by rewriting the historical implementation-status
paragraphs. No AGENTS.md/review-guide/ruleset changes. No new runtime/provider run; no qualification pin regeneration.
Live transport/F-3 stay PR 3; finality/both timings/recorded harness send/default-on stay PR 4; independent product
review is still required before a PR/merge-ready claim.
