**Built (`feat/e368-worker-packs-core-pointers`): what every worker is sent, as a core plus a pointer, on the
operator's go-ahead before the UAT of 2026-11-28** ("the lead plus core also hasn't been run yet so no im less sold on
the worker core plus pointers being dangerous"). It claims delivery, not effect: no model has run the new texts.

**One owner for each line.** A run is sent three texts: its system text (which a compaction keeps), its first
message's own text (`contract.preamble`) and the pack.
- The first message's own text is now its heading and one sentence: the run's rules are in the system text, and the
  contract below is authoritative. Every rule it said again (the `aew` command and the credential, submitted
  evidence, the workspace, report text as data, the scratch directory) is said once, in the system text.
- What only a run has moved to the system text (`contract.run_rules`): coordination, map reads, and the pointer.
- The pack's role card no longer sends the Lead's selection guidance (`use_when`), a list with nothing in it, or an
  "Expected outputs" line equal to the write-back's kind; the contract's "Capabilities" line is printed only for a
  pack with no card. A parent reviewer's duties no longer repeat the list of what to look for.
- The optional skills have one instruction, `context.SKILL_FIT` ("load each one whose description matches your
  task"), in the pack and the system text (ADR-0006, amendment 2026-11-28). The "Skills to load" line and the system
  text's qualifying clause are unchanged.

**The pointer.** The system text says `aew context show <invocation> --section <heading>` reads a section of the
contract again, by the start of its `##` heading (`--section Contract` always resolves), and without `--section` all
of it. A `##` line inside a fence is data, never a section (`context.section_text`). Its limit: a document the pack
prints whole as Markdown (a requirement's body, an ancestor's, the accepted plan) can hold a heading of its own, which
reads as a section; E401 decides how those are printed.

**A run reads its own contract, and only its own** (ADR-0009, amendment 2026-11-28). The layout binds the run's pinned
pack, read-only and alone, over the `.aew/local` mask (`layout.for_run`'s `pack`; the supervisor writes the pinned text
there first, `supervisor.own_pack`). `aew context show` in a run reads only a stored pack, and any other id is refused,
`PERMISSION_DENIED` with reason `not_own_invocation`, before anything of it is read. Which pack is the run's own is what
the sandbox shows, not a variable. The operator's, the Lead's and the contained Lead's reads are unchanged.

**Bytes**, on `tests/unit/test_pack_truth.py`'s synthetic inputs, every built-in card at every scope it is dispatched
at, with every switch off and on (system text, first message's own text and pack, summed): 488,780 B to 412,546 B over
the 50 cases, 14.2% to 17.5% less per run by card. The audit estimated 36 to 42%; the cuts here keep every mandatory
line (the report format, the responsibilities, the prohibitions, the guardrails, the open findings), so they do not
reach it. The system text grows (the pointer and the moved rules); the first message shrinks by 1,300 to 2,100 B.

**Pack-truth extensions** (`tests/unit/test_pack_truth.py`), each with planted right, wrong and missing cases, each
failing with its fix undone:
- restated text: no sentence of 40 characters or more is sent twice across a run's three texts, with every switch off
  and on; no card line restates a value the contract says;
- every switch on: the three texts agree (the credential said once, in the system text; every printed command on the
  run's bridge or the role's local read; one skills instruction; what the first message holds);
- a size budget: `context.ALWAYS_SENT_PROSE_BUDGET` (8,100 B), the prose a run is sent whatever its data, raised by
  measured amounts only;
- references that resolve: the pointer's example section and every section of every pack read back by their heading.
Scope fit and the wrong mechanism were already held (E366, #613).

**What remains** on this row:
- **The measurement:** whether a worker does better or worse with these texts, judged as R0 proposes (verified
  completion, constraint preservation, additional source discovery), not by bytes. Whether it waits for the refined
  F19 is the operator's.
- **A production budget that cuts:** packs are still rendered without a budget at dispatch (`context_ops.build_pack`).
  Passing one changes what a dispatched pack holds, which this change does not; the budget here is a guard on prose.
- **The skills' own texts:** not changed. They are loaded on demand, not always sent, and change only by a re-hashing
  pull request.
- **R0's D3** (the pointers name what is not delivered and why): not taken; it is the operator's.
