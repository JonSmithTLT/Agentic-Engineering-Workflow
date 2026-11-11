Full product review at 5573dab3: M1-M4, m1-m3 and n1. Authority checks passed; these fixes do not change authority.

M1: ADR-0009 owns a 60-second uncertain admission hold, persisted from the first POSTING time. Pinned-session 404
or expiry abandons only the selection, marking no IDs posted and advancing no news marks; status names the hold's
deadline. Tests exercise relayed consumption, /new, broker restart and 404 release. Re-listing/duplicate news after
the recovery bound is allowed, not proof the earlier request could not land. The merged steering-loop wake path
must use this same recovery boundary.

M2: pin eight FileLock sites, name local/lead/told-messages.lock and its record opener/taker, and pin its non-writer
refusal (unlike the other auxiliary locks). All tests/integration/test_reference_*.py belong in subsequent q7 gates.

M3: remove the duplicate worker_message guide row, retaining the single reason owner/system explanation and the
accepted cost line. Main merge must feed its render_pool the same selected switches, measure the actual on/off
delta and record it against the unchanged 200-byte messaging allocation. Any excess is for the Lead/operator,
not permission for this branch to raise its cap.

M4: automatic attention has one rendered, attributed, escaped/framed body per ID, not raw plus rendered copies.
Typed results quote selected bodies once in projection.coordination; payload and wait/wake messages fields use
ID references. Wake JSON contains the bodies once, not repeated as appended readable frames. The 20-ID maximum
also has a 32 KiB serialized-body budget beneath the 50 KiB output cut: twenty 4,000-character bodies cannot fit
there even once each. Count/byte omissions retain recovery and produce no receipt. Typed output over the cut for
unrelated content records no shown receipt. Tests count exact body copies and check twenty-reply statuses (short
and 3.9 KiB bodies), omissions and over-cut non-consumption.

m1: worker wait ticks call message_waiting on committed state and open a delivery session only for actual pending
messages. A real-engine idle-wait test fails on any session acquisition. Final send/authority/lifetime checks remain.
m2: worker preamble offers waiting only on the qualified harness/platform; unsupported hosts are told to reply and
end the turn, not to try a refused wait. Runtime version still independently controls adapter support.
m3: a real launched worker with messaging-on snapshot is driven through an adopted off switch; read/reply/wait
all return MESSAGING_SNAPSHOT_MISMATCH and leave the thread unchanged.
n1: told_messages cites ADR-0009's delivery-record contract as owner, not the private amendment review.

No push of the product branch; hand back after the main merge and exact-head validation for the Lead's quick check.
MS4 qualification publication remains separate (#448). No new runtime/provider probe or qualification pin rewrite.

Main integration: retain both steering-loop and message gathering, projection and broker callbacks. Production's
pinned post applies with messaging off too. The immutable selection includes the loop occurrence key, so a later
occurrence with identical public payload cannot authorize retrying an obsolete uncertain envelope. Mixed and loop-only
restart tests cover both expiry and pinned-session 404; abandoned occurrences are never marked told.
Generated conflicts were settled by tools/reference.py resolve, not taking either generated side.

M3 measurement after main integration: messaging on system/guide/join/MCP = 9,279/16,611/2/11,900 B, total 37,792 B;
off = 9,023/16,433/2/11,830 B, total 37,288 B. On/off delta = 504 B. Net growth against the recorded 37,355 B baseline
(which already includes the on catalog) = 437 B. Replace the 200 B estimate with that measured net delta, preserving
all approval words and the 42,555 B cap. Baseline plus allocations now totals 42,792 B: **237 B over the cap**.
The pool gate deliberately remains red; the Lead must take this excess to the operator. No raise is authorized here.
Catalog listing baseline remains 11,900 B / 16 tools on and 11,830 B / 15 off. Windows runtime remains NOT RUN / GAP.
