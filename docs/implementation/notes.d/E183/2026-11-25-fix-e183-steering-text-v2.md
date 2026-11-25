**The wake question is decided (the operator, 2026-11-25, on #577):** the crawl and walk stop does not wake the Lead.
The behaviour stays as built: the stop is quiet, never notified, and kept from the Lead's `loop_waiting` wake by
`LEADS_OWN_STEP`, as QC-1 (c) on E228's fourth PR had it. This settles the question the earlier note left open ("the
stop's wake hold waits on the operator's confirmation"); SYS-04's switch text and the closed row now say it is decided.
