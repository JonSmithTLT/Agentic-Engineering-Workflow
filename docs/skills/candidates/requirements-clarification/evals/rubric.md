# Requirements clarification rubric

Evaluator only. Materialize one case's artifact strings in an isolated directory; supply only its `worker` mapping. Keep purpose, oracle, rubric, source notes, and other cases hidden. Enforce declared capabilities. These fixtures are inputs to a pilot, not an executable harness.

Grade whether questions discriminate materially different outcomes, supplied facts are reused, and unresolved product decisions remain explicit. Asking more questions is not inherently better. In the supplied-default control, no question is needed; in the conflict case, a well-supported partial result is the intended outcome.

Record each required oracle item as present, partial, or missing; list false claims separately. Accept equivalent correct reasoning, output formats, and methods. A blocked case succeeds by naming the precise missing prerequisite and preserving supported partial results, not by guessing. Non-use controls should complete the narrow request without procedural expansion.

For execution cases, distinguish commands actually run from proposed checks and associate outputs with the relevant snapshot. Inspect resulting artifacts as well as reports. For static cases, do not demand execution that the worker was forbidden to perform. If the evaluator cannot supply declared capabilities, record an environment deviation rather than treating it as worker failure.

Use the primary measure and preregistered floors in [authoring notes](authoring.md). No points for verbosity, extra findings, or automatic tool use. Repeat independent trials and unseen variants before recommending adoption; this package currently establishes no measured benefit.

## Feedback regression cases

For exact-answer and conflict cases, score qualifier preservation, separation of quotation from interpretation, explicit supersession versus mere recency, and decision-ready measured tradeoffs. Extra approval loops for already settled scope are a regression.
