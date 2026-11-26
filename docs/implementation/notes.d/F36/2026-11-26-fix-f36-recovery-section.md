**Partly built: the recovery section of a replacement invocation's pack** (the recitation's part for a replacement).
The operator, 2026-11-26, on the finding that a replacement worker is told nothing about its predecessor: "There is
benefit to starting fresh cintext workers. That case above does not seem to be one kf them. Aew kind of forces
replacement or follow on workers to kind of rediscover whats already been done which ks not optimal". Asked whether to
build the recovery section now as a direct fix: "Yes recovery for replacement workers is a defect in current aew. Or i
guess the mkre correct phrasing is it is an oversight". So it is on for every project, with no switch: the "off by
default" of this row's design stays with the handoff note and the recitation on a trigger.

**What this delivers.** When an invocation is dispatched in the place of one that ended without completing (the unit's
latest earlier invocation of the same role and scope, with a status other than active or completed), AEW assembles a
"Recovery reference" section in its pack, after the accepted plan. No model writes any of it, and it is labelled as
reference data: never an instruction, authority or Knowledge.
- **Each fact from its owner, read at dispatch:** the predecessor's id, role, scope and status (its invocation); the
  recorded reason its credential ended (its token record, which now also keeps the Lead's reason for `invoke cancel`
  and for a superseded attempt); the ids and kinds of the evidence it produced (the evidence store); and, for an
  implementer, the workspace's paths that differ from its base, each marked staged or untracked
  (`fingerprint.workspace_paths`).
- **Bounded, and a cut is said:** 30 paths, 20 evidence ids, and 160 characters of a reason or a path as the pack
  prints it, each cut with its count ("and N more"). A reason and a path are each one JSON-quoted line.
- **Pinned on the invocation** (`recovery`, and a `recovery:<predecessor>` entry in the pack's sources), so a
  regenerated pack is the dispatched one whatever the workspace does next.
- **Proof stays with its snapshot:** the section lists an evidence id and kind, never a result, and says none of it is
  proof for the replacement's snapshot.
- **Independence:** a reviewer or a verifier never replaces an implementer. It replaces only a reviewer or verifier
  of the same card, snapshot and record under review that did not complete, and is then told the predecessor's id,
  status and evidence ids, and neither the recorded reason (it may be the Lead's words about that predecessor's work)
  nor any workspace path. An executor of a non-mutating Ticket gets the reason and no workspace: its observation is
  new.
- A first invocation, and one that follows completed work (a rework after a review, a re-review), gets no section,
  and its pack and its record are unchanged.

It claims no effect on a worker. How much it helps is what Experiment C of the ProjectArchitect research measures
(the row E389 that pull request #604 adds; this section is C1's treatment there, its candidate delta D1).

**What remains** on this row:
- the worker-authored handoff note (delta item D6), and its delivery to a replacement beside this section;
- the rest of the recitation (delta item D11): the goal or active criterion, the remaining criteria, plan tasks,
  changed files against the planned scope, checks performed, open findings and blockers, delivered through the run's
  inbox on `recitation.calls`, `recitation.elapsed_s` or `recitation.every`;
- in this section: the predecessor's last harness run and how it ended (the run log is local telemetry, and the Lead's
  recorded reason carries it today); changed files set against the planned scope; and a follow-on worker after a
  predecessor that completed, which gets nothing from this section.

Not this row's: the shell text of `aew resume` still omits the latest checkpoint note that its JSON and the typed
tool carry (the R0 baseline's D5). It is the Lead's view, not a replacement worker's pack, and is left for F8.
