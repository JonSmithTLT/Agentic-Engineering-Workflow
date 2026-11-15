PR 2 wait checkpoint: a shared verified delivery view suppresses generation-local told and confirmed posted IDs
before the total body cap. Durable status/resume/StageResult attention continues to ignore both suppressors. A
message-ID receipt is verified against its exact returned bodies rather than a possibly different current top-20
batch, so a locally suppressed first batch cannot strand the next one.

Lead waits now carry bounded verified bodies, including with a missing digest. Worker-message holds needs an explicit
verified eligible-ID set; run-ended holds needs the record lane's explicit fact. A brokerless own-shell wait takes a
verified entry cursor for live wake eligibility. Broker waits use eligible unseen bodies, and an explicitly requested
ended run carries eligible unseen replies regardless of that cursor or a previously reported end. Local suppression
still applies to those replies. The existing end/evidence/result facts and explicit repeated end are preserved.
Messages are not consumed by digest sequence advancement. Relayed live waits record only their named-run bodies in
the broker's local told set, retaining durable unseen. Tests use real fake-V2 worker replies and bridge/CLI waits,
not handwritten owner facts; a separate planted malformed/old local posted reader test claims no admission evidence.

Still owed: the wake writer's generation-bound posted set and in-flight admission reconciliation, run-less settled
gather and final read/post race checks, full delivery-record planted cases/ablations/bounds coverage, shared on-only
guidance/goldens/oracle, final capability and residual wording. No live transport/default-on change or runtime probe.
