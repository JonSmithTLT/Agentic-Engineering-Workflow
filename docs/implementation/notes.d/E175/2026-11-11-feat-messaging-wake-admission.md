PR 2 wake checkpoint: the same queue gather now includes verified worker-message IDs, including sealed/archived
run-less hot-list entries, without fake runs. It selects at most the shared 20 bodies, counts omissions, and uses
the same explicit ended-run facts as the wait through a no-return-record read. Durable attention ignores posted
and told sets. Confirmed posted IDs are scoped to generation and pruned only when durable shown/dead/out-of-view;
retention verification covers live inbox bounds plus the bounded settled list, not only the public first 20 bodies.

Before admission the queue records immutable selected IDs, target session, post ID and scrubbed post bytes in its
existing local wake record. The final verified eligibility check shares broker serialization with read completion;
neither that serialization nor a control lock spans the post. Targeted poster calls use the recorded session even
after the newest-viewed session changes. Only successful admission or exact-ID inbox/message reconciliation records
posted IDs. No wake calls the durable shown writer. Failed/malformed/unavailable reads are not admission evidence.

A timeout keeps its exact identity/target/bytes, including after restart. An absent GET result is not proof a timed-out
request cannot later land: if a read has meanwhile consumed the selected IDs, or the session/reason changed, the
uncertain envelope stays for reconciliation and is not replaced by a new ID. This can hold automatic wakes while
uncertainty persists; explicit reads/waits and durable attention remain available. An explicit non-admission HTTP
rejection releases the selection. The poster distinguishes these rejections from conflicts/server errors/timeouts.

Deterministic tests use real engine threads/seals, actual typed/relayed bridge reads during the post, and scripted
admission outcomes. They cover both read/post orders, identity-preserving retry, unavailable/late admission,
restart, same-generation new-session resume, real generation handoff, batch omission, archived run-less sources,
injection framing and post-before-explicit-wait with identical end facts. They are not a runtime/provider probe.

Still owed: full six-condition delivery-record plants and ablations, more lifecycle/bounds/process coverage,
shared switch-aware guidance/system/on golden and independent guide/catalog oracle, final capability/residual
wording and independent product review. No live transport or default-on change; Windows runtime remains NOT RUN/GAP.
