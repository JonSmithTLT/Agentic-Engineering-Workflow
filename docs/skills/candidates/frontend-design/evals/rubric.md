# Frontend design evaluation

Evaluator-only. Materialize only each case's worker artifacts in an isolated workspace and give the worker only its worker payload plus the selected runtime arm. Supply the declared browser/preview capabilities consistently; do not expose this rubric or the oracle. Do not execute skill-linked external launchers.

Score each dimension 0 (missed), 1 (partial), 2 (satisfied):

- Scope and factual fidelity: preserve constraints, actual product facts, and existing identity where required.
- Visual purpose: coherent hierarchy and composition supporting the supplied audience/task, with content-specific decisions.
- Interaction completeness: requested actions and relevant failures work without losing data or reporting false success.
- Adaptation/accessibility: usable narrow layout, content variation, semantics, keyboard focus, and applicable motion handling.
- Evidence: reproducible checks tied to route/state/viewports; honest distinction between static, simulated, and live verification.

Judge completed build cases at 1280 and 390 CSS pixels, plus 320 where applicable to reflow; exercise keyboard and failure paths separately from screenshots. Inspect computed styles/DOM and relevant console failures. Do not reward a specific font, palette, framework, fashionable layout, or gratuitous animation. Do not award accessibility conformance from these limited checks.

For visual comparisons, use blinded paired judgments tied to the brief: priority comprehension, legibility, coherence, and subject fit. Require judges to identify the observed reason for preference; a taste-only verdict does not establish a regression. A worker need not choose the oracle's illustrative composition if an alternative serves the same constraints.

Record primary-flow failures, unauthorized redesigns, fabricated evidence or claims, false activation, and context/tool cost separately from the score. A high visual score cannot offset one of those failures. Case assertions are conjunctive where applicable. Unavailable capabilities must be reported, not treated as a pass. Repeat equivalent private cases across relevant worker profiles before adoption.

## Shared-component case FD-09

Use all three supplied screens, not a separately recreated component demo. Preserve identical starting fixtures across arms. Before and after the patch, inspect all 18 route/theme/viewport-zoom combinations: three routes, two themes, and wide 100%, wide-window 200% browser zoom, narrow 100%. Capture actual viewport dimensions and zoom. Browser zoom is distinct from CSS scale or viewport narrowing; record unavailable capability as missing evidence.

Check readable contrast and full status content, keyboard access, navigation, and the acknowledgement result. Confirm only shared.css changed and every consumer uses the shared owner. A good first screen cannot offset a broken sibling. Converting unknown to zero, dropping uncertainty/freshness/provenance, or rewriting a contract is a fidelity failure even if the visual result improves.

For composition trials, compare frozen base-only and base-plus-premium arms on FD-09 and the existing read-only/missing-capability controls. Pin all loaded runtime references in both packages; track additional context and tool cost. Keep premium-specific operational requirements in that arm, record conflicts or missing capabilities, and do not silently relax either arm's contract to obtain a pass. No composition pilot is claimed by these authoring checks.

## Read-heavy lifecycle feedback cases

Require post-await retirement checks before follow-up reads/publication, immediate exclusion of replaced-source display, and noncooperative late completion/rejection coverage. Do not accept cancellation alone or eventual screenshots as proof. Preserve host ownership and same-source refresh policy. Fixture cases must preserve both bounds and dependent identities without inventing stricter acceptance. Environment planning must distinguish typecheck from build/browser support and preserve other services. Judge only obligations applicable to each case.
