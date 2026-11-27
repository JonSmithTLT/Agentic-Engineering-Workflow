**A-44 slice S1 is built** (`feat/e101-approvals-view`). The G3 client keeps a per-host record of each approval it
starts (`aew.g3records`, in `$XDG_STATE_HOME/aew/g3/requests/`, directory 0700, files 0600, each write atomic and each
write pruning what has passed its expiry plus G3-06's window). A contained launch refuses an operator's writable
root that would expose that directory, as it does for AEW's host state. Both G3 clients write it: `aew g3 request`, and the
operator endpoint's G3 path (G3-C's C3), which came after A-44 named the command alone. `aew g3 request` now keeps
reading through no answer and a 503 until the approval's expiry, saying so once; the endpoint's G3 path keeps holding
on either, as the designer's ruling 1 on G3-C says. One attention module (`aew.engine.attention`) gives every item its
tier, lane, order and occurrence key from one table. The overview lists its items on contract 0.1.3 unchanged, waiting
approvals first and FYI items in no count, and `aew status` prints the same items with the dashboard stopped,
except other projects' approvals. **The operator's ruling (2026-11-27):** asked whether `aew status`, and so the
Lead's relayed read, should show only the current project's G3 approvals, with the operator's dashboard keeping the
host-wide view, the operator answered "For approvals yes that makes sense". The record's own `project` field
decides (`g3records.of_project`). The
outage reader takes the module's committed items only, so an approval is never an outage item. The `/attention` 403
reason now names the dashboard half of the typed-surface projection, which E18 tracks. Nothing in it decides, answers
or approves, and the dashboard never connects to G3: it only checks that `request.sock`'s path exists.

**What remains.** Three choices for the review to confirm, each the builder's reading of the slice. The overview shows
an approval's expiry time, not its time left, so its validator does not change every second (`aew status` shows the
time left). The FYI approval states show as contract kind `anomaly`, severity `info`, since 0.1.3's known kinds have
no FYI one. The existing alert events name no answer home from BOY-06's set. The /waiting read, with each source's read time, the agent lane
and the `operator_endpoint` home stay with E102.
