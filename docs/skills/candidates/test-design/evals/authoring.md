# Authoring and evaluation notes

Evaluator only. Do not expose this directory to workers. Version 0.1.0 is an unevaluated candidate; no target-worker benefit is claimed.

## Authority and interfaces

Implementers may design and write tests within scope; reviewers and verifiers may assess their adequacy without acquiring mutation authority. Tests do not accept their own implementation. Role cards supply responsibilities and authority, context supplies current project facts, and capabilities govern permitted operations. This skill supplies reusable technique for AEW and other projects. It grants no credentials, tools, state transitions, or new evidence kinds. Follow the invocation's output contract.

## Evaluation

Hypothesis: Improve fault detection and correct test oracles without increasing false failures, flakiness, or needless execution cost. Conditional TDD may add benefit beyond test-design guidance alone.

Primary outcome: Tests reject seeded incorrect behavior and accept conforming behavior using independently justified expected results.

Compare the same target worker with and without the frozen skill using the shared evaluation guide (`docs/skills/evaluation-guide.md` in this repository). Record model/settings, source and runtime-file digests, task/environment identity, outcomes, total input/output tokens including skill text, tool calls, elapsed time, and human questions. Freeze correctness floors, regression margins, and economic limits before trials. Unauthorized actions or fabricated evidence veto adoption. Equal quality with added cost is not a demonstrated quality gain.

Use [cases](cases.yaml), [rubric](rubric.md), and [research rationale](sources.md). Public cases are development material, never unseen holdouts. Author and sequester fresh variants for adoption decisions. Structural validation and author inspection are not worker trials.

For TDD, compare three independent conditions: baseline; test-design core; test-design core plus the TDD reference. Record exactly which files were exposed and read. For the core-only ablation, explicitly disable the reference route without changing other guidance and digest that experimental variant. Report the intervention accurately. Use equivalent hidden behavioral checks across arms and measure total cost including repairs, not only first-attempt success.

## Comparative guarantee refinement

Version 0.2.0 adds a conditional seeded-differential reference and non-narrowing case, motivated by supplied worker evidence. It separates characterization from correctness and preserves limits on untested inputs. This revision needs a worker pilot.

## Settings field-report refinement

Version 0.3.0 incorporates an author-side field report for frontend-design 0.2.0, whose entrypoint digest was `69e52feb459bba5e13c2dbf2ee006f9e8cdd340eb4bf0fafe7080aa18c39a4f0`. Reported useful behavior included preserving uncertainty, respecting maintained identity, and requiring rendered inspection. Independent review of that implementation exposed lifecycle and fixture gaps, motivating the new conditional guidance and synthetic cases. No premium/upstream skill was loaded in that reported use. These are reported observations, not independently replayed trials or evidence of comparative superiority. Project-specific ownership and acceptance details remain in context packs.
