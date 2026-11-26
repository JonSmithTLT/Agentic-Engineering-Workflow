**The operator on R0, 2026-11-26: "Yes start R1 prep, ship truth fixes now, cap is fine but will only be able to be
done when I get back home anyways".** For this row, that decides one thing: its truth fixes ship now. They are the
corrections of what the worker texts say (the verifier's shell, the system text's "first message" line, the skills'
contradictions): the texts are wrong today, so the fixes need no experiment.

**The rewrite waits. This is the Lead's recommendation, not an operator ruling.** The Lead recommended to the operator
"ship the truth fixes now and hold the rewrite as the experiment's treatment", and the operator answered "ship truth
fixes now". So the truth fixes are the operator's decision. Holding the rewrite is the Lead's recommendation, which the
reply did not contradict. The operator decided later that day that E389 refines F19 and is not a separate system
(F19's note of 2026-11-26), so there is no separate Experiment A to wait for. "Held" now means the core-plus-pointers
rewrite is kept as a held draft, not merged, until the refined F19 can measure it as a treatment. Until then this
row's pull requests carry the truth fixes only, and claim delivery, not effectiveness.

**Proposed, not decided:** [R0](../../../research/projectarchitect-r0-baseline-2026-11-26.md) (its last section)
recommends judging the rewrite by C1 of the
[ProjectArchitect concept research plan](../../../research/projectarchitect-concepts-and-evaluation-2026-11-25.md),
that is, by what a worker achieves with the new pack and not by the bytes it saves. These are the operator's to take:
- the rewrite would be measured as a treatment against today's pack, with worker, model, task and budget fixed,
  measured by verified completion, constraint preservation and additional source discovery. The audit's 36 to 42%
  would be a diagnostic, counted only when those hold;
- from R0's checklist: the contract's "Required knowledge (included below)" drops undelivered items silently
  (`src/aew/knowledge/context.py:363-364`). R0's D3 proposes that the pointers name what is not delivered and why. It
  adds nothing to this row's scope unless the operator takes it;
- the mandatory constraints would stay in the core, never behind a pointer.

**What remains:** all of this row's work. The truth fixes are being built in their own pull request. Nothing here
changes this row's place in the Now list or its order after E367: the truth fixes keep that place, and the rewrite
waits as said above.
