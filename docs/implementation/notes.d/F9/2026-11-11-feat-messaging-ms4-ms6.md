**MS4/MS6 built (PR 2, still off by default).** Worker bridges expose own-thread reply/read/wait only for enabled
launch snapshots; foreground wait lifetime checks and successful-send worker receipts are implemented. Lead status,
resume and typed projections overlay verified live/sealed attention. Existing wait/wake checks deliver bounded
framed bodies, including run-less settled replies, using one reason owner and no extra poller. A typed StageResult
shares the 20-body budget across payload/projection. Typed/own-shell typed reads record durable shown after output;
relayed reads record only generation-local told IDs. Wake posted identities and immutable in-flight envelopes stay
in the existing local queue record; neither local suppressor prunes durable attention. ADR-0009 and ADR-0017 record
the exact boundaries, files and re-listing/uncertain-admission residuals.

Evidence: worker_messages/worker_message_engine/worker_wait_connections; message_attention/message_delivery_view/
message_result_receipts/message_wait_delivery/message_wakes; delivery_record_contract/told_message_processes;
message_start_snapshot and messaging_guidance tests. Qualification evidence remains the committed isolated Linux
2.2.6 record/pin, not these fake/process tests. Windows runtime remains NOT RUN/GAP; waits are refused there.

MS3 follow-ons resolved: stable-lock atomic told unions; shared snapshot-derived guide/system/on golden; independent
expected standard-text and wire/prose naming oracles (n-a); explicit catalog()/check_call()/alias/dynamic/wrapper and
same-count syntax-detector limits with controls/inventory (n-b); obsolete pre-MS4 snapshot wording corrected.
Accepted listing budget stays 11,900 B / 16 on and 11,830 B / 15 off, with no cap raise. Explain's historical 936 B
was its compact entry, not standard metadata. PR 3 owns live transport and F-3 retry-body/changed-metadata coverage;
PR 4 owns finality, both timings, recorded harness send and default-on. MS7 provider evidence stays owed separately.
