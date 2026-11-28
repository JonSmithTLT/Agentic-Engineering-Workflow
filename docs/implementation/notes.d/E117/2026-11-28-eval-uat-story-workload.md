**The UAT's main scenario, a story-sized workload (2026-11-28).** The operator asked for "enough tasks and complexity
to be a story at least because we have over half a dozen features to test", run once through AEW and once through
OpenCode alone on the same model, same tree and same request, for a manual comparison.
[`eval/experiments/uat-story/`](../../../../eval/experiments/uat-story/README.md) holds it: one opening request for one
Story of eight items on the lower-bound lane's Python-Markdown fixture (LBQ-1 to LBQ-3 reused, five new), with real
dependencies and parallel items, a scope trap, same-function integration, declared and undeclared review and
verification, a symptom-only bug, a long task with lettered requirements, and a branch review (E168) of a seeded
contributor branch. Four escape traps (approved by the operator, 2026-11-28) make the comparison count wrong work that
gets through, not visible pass rate: a mid-tier worker passes the visible tests almost every time. `materialize.py`
builds the identical starting repository for both arms. The oracles, their
validation, the reference solution and the scorer are private (F19's hidden-evaluator channel). The seeded ledger kit
stays as the UAT's smoke test. Evaluation material only: no product code changes, and nothing here is evidence for
M4-H.
