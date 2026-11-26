**Cited, not implemented: R0's finding on this row, a replacement worker is told nothing of its predecessor.**
[R0](../../../research/projectarchitect-r0-baseline-2026-11-26.md) of the ProjectArchitect research (E389) interrupted
an implementer that had left staged, unstaged and untracked work, reconciled the Ticket and dispatched a replacement.
The replacement's pack was identical to its predecessor's apart from two lines, the invocation id and the inputs
fingerprint. Nothing in it said that a predecessor existed, how it ended, or what it left in the workspace (R0's K2 and
K7, at `eece01e5`). The Lead is told only to "inspect workspace/artifacts and reconcile".

R0's candidate fix is D1: a short recovery section that AEW assembles in a replacement invocation's pack. It names the
predecessor invocation, how it ended and why, its evidence ids, and the workspace's paths changed against the base and
untracked at dispatch, labelled as an observation and never a claim. It is a narrow slice of this row's recitation
("changed files against the planned scope").

The operator's view, 2026-11-26: "There is benefit to starting fresh cintext workers. That case above does not seem to
be one kf them. Aew kind of forces replacement or follow on workers to kind of rediscover whats already been done which
ks not optimal". Whether D1 is built directly or tested first in E389's Experiment C is pending the operator's decision.
This note builds nothing and changes nothing of this row.
