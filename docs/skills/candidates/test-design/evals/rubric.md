# Test design rubric

Evaluator only. Materialize one case's artifact strings in an isolated directory; supply only its `worker` mapping. Keep purpose, oracle, rubric, source notes, and other cases hidden. Enforce declared capabilities. These fixtures are inputs to a pilot, not an executable harness.

Assess semantic discrimination, not exact assertions or test counts. Run submitted tests on conforming and faulty variants where capabilities permit. Confirm the intended pre-fix failure, not just a nonzero exit from broken setup. Check deterministic synchronization and cleanup. The tests-only control should preserve valid production code and need not manufacture a red phase.

Record each required oracle item as present, partial, or missing; list false claims separately. Accept equivalent correct reasoning, output formats, and methods. A blocked case succeeds by naming the precise missing prerequisite and preserving supported partial results, not by guessing. Non-use controls should complete the narrow request without procedural expansion.

For execution cases, distinguish commands actually run from proposed checks and associate outputs with the relevant snapshot. Inspect resulting artifacts as well as reports. For static cases, do not demand execution that the worker was forbidden to perform. If the evaluator cannot supply declared capabilities, record an environment deviation rather than treating it as worker failure.

Use the primary measure and preregistered floors in [authoring notes](authoring.md). No points for verbosity, extra findings, or automatic tool use. Repeat independent trials and unseen variants before recommending adoption; this package currently establishes no measured benefit.

## Comparative guarantee regression

For tests-non-narrowing, combine a frozen-base differential with the independent contract. The new function loses token-marker protection. Require shared reproducible inputs, semantic comparison and distinct controls, not output-length equality or claims of seed-based completeness.

## Read-heavy lifecycle feedback cases

Require post-await retirement checks before follow-up reads/publication, immediate exclusion of replaced-source display, and noncooperative late completion/rejection coverage. Do not accept cancellation alone or eventual screenshots as proof. Preserve host ownership and same-source refresh policy. Fixture cases must preserve both bounds and dependent identities without inventing stricter acceptance. Environment planning must distinguish typecheck from build/browser support and preserve other services. Judge only obligations applicable to each case.
