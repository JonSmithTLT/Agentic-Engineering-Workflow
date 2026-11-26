**Cited, not implemented: R0's finding on this row, open questions never reach the pack.**
[R0](../../../research/projectarchitect-r0-baseline-2026-11-26.md) of the ProjectArchitect research (E389) confirms
this row's follow-on at `eece01e5` and widens it by one field. `_input_summaries`
(`src/aew/engine/context_ops.py:74-89`) keeps a consumed record's facts, hypotheses, conclusions and subjects. It drops
a discovery record's `unresolved_questions` and a research record's `uncertainties`, which this row already names, and
also a research record's `constraints`. No pack section holds open questions or known limitations (R0's B6).

R0's candidate fix is D2: consumed inputs keep those three fields as labelled lines, and the pack gets an
open-questions section. E389's Experiment A would test it on fixtures A-F4 and A-F5.

The operator's view of R0's findings, 2026-11-26, said of the replacement-worker case on F36: "There is benefit to
starting fresh cintext workers. That case above does not seem to be one kf them. Aew kind of forces replacement or
follow on workers to kind of rediscover whats already been done which ks not optimal". Whether D2 is built directly or
tested first is pending the operator's decision. This note builds nothing and changes nothing of this row.
