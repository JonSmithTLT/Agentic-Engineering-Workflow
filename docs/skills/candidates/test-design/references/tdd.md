# TDD for an implementation assignment

Read only when implementing settled behavior using test design. This is an execution technique, not a separate approval or orchestration workflow. Keep existing project rules and the assigned mutation boundary.

1. **Choose a behavioral slice.** Identify one contract-backed outcome and an observable check. Include error semantics when they define the slice. Do not design the oracle around a planned implementation detail.
2. **Observe red.** Write the check before implementing that behavior and run it. Verify the failure mechanism: an incorrect result or explicitly missing interface, not a typo, missing test dependency, or unrelated import failure. If it passes already, investigate whether the behavior exists or the test misses the defect; do not break valid code to obtain red.
3. **Implement the contract.** Make the smallest coherent change that satisfies the intended behavior across the applicable input class. Passing one example is not permission to hard-code its answer. Check related paths for the same defect within scope.
4. **Observe green.** Run the regression and relevant existing tests; inspect actual assertions and diagnostics. If the test was wrong, correct it from the requirement and repeat the meaningful red/green evidence where possible. Do not alter the requirement or relax the oracle merely to pass.
5. **Refactor with protection.** Improve structure within scope while preserving the contract. Re-run affected and required checks after the final change. Record before/after source and test identities, commands, intended failure, passing result, and remaining gaps.

Use this mode preferentially for executable behavioral requirements and repairs. For concurrency and lifecycle fixes, before/after regression evidence is required; use deterministic synchronization. If the old implementation is unavailable, report that verification gap rather than calling the cycle complete.

For test-only work or an already implemented change, use an isolated pre-fix version or permitted targeted mutant when needed to establish discrimination. A mutant demonstrates fault detection, not proof that a historical bug reproduced. Never erase existing work or reset another contributor's changes to enforce the sequence.

Exploration with unsettled semantics can produce labelled probes first; settle the oracle before treating a probe as a regression test. Pure refactors normally preserve already-passing behavior. Editorial changes without behavioral impact do not need a contrived red/green cycle.

Synthetic example: a TTL contract expires entries when age is at least the limit. With an injected clock, the exact-limit assertion fails against the old strict-greater comparison and passes after correcting it; below-limit still succeeds. A failure caused by an unavailable clock library would not establish this regression.
