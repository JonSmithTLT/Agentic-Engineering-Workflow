PR 2 foundation checkpoint, not the completed messaging feature: fresh status/resume/action projections carry a
verified, bounded worker-reply view, independent of revision-keyed control caching and generation-local receipts.
Live replies are read from their verified threads; settled replies use only the hot unseen list and pinned seals,
not a history walk. Readable worker bodies escape control/bidi characters and cannot close their data fences.

The local told-ID primitive uses util.atomic_write under the separate stable lock
local/lead/told-messages.lock and its .queue turnstile. Normal updates union IDs without pruning within a generation;
invalid records suppress nothing, and an old generation cannot replace a newer one. Authority is checked after
the lock wait and before replacement, together with lock identity. Tests cover concurrent real processes, crashes
before/after rename and authority changing while a process waits for the lock. These receipts are not durable
shown facts and do not clear a worker's durable inbox cap.

Still owed in PR 2: verified result extraction at broker boundaries, relayed told-only versus typed durable
consumption, wake posted-ID reconciliation and wait suppression, run-less settled news, switch-aware shared guidance
and its independent oracle/goldens, and full capability/residual documentation. This checkpoint does not claim those
routes work yet. Linux runtime qualification and Windows NOT RUN/GAP remain unchanged; no new probe or transport.
