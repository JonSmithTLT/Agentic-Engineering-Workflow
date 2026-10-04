# Work density cleanup — bounded improvement plan

2026-10-04. Operator authorized planning and incremental improvements while Knowledge Capture & Admission and the forthcoming API settle. Source assessment: `web/docs/reviews/page-density-2026-10-04.md`; register E16 in `docs/implementation/future-work.md`. Start from merged W06/main `ec727f3c1d4cd9cc29ce131350d061afa7531460`.

## Outcome and limits

Make supplied Work identity, intent and blockers easier to find, reduce duplicate utilities, and make phone child navigation reveal its result. Preserve every existing feature and the distinction between record reasons, blocked_by and a status explanation. No Knowledge redesign, new backend/preview contract, Engine work record, dependency or lockfile change. Production remains read-only against accepted API 0.1.2.

## Reviewable checkpoints

1. **Navigation and immediate hierarchy:** Inspect children reveals Results without clearing the selected parent; identify a selected record outside the loaded page/filter. Allowlisted `work_pane=results|detail` restores phone presentation only, never enters API routes, and invalid values reject before dependent reads. Work's content precedes inspection utilities through an explicit DetailView variant. Source/browser metadata is disclosed; currentness/errors remain visible. Remove the duplicate selected-record CLI and embedded dashboard-link control; direct detail still supports copying. Preserve legacy links without the new parameter.
2. **Results setup:** separately assess a Filters disclosure for Kind/Direct parent, an always-visible active-filter summary, and reduced repeated introductory copy. Preserve State, display choices, full scope explanations, cursor behavior, render-all keyboard fallback and accepted 100-record pages. Do not implement this until checkpoint 1 is validated.
3. **Further detail organization:** assess whether Summary/Relations/Provenance tabs materially improve tasks after checkpoint 1. The review's tabs were a proposal, not a required redesign. Prefer the smallest change supported by a repeat task review; preserve direct links, Why/Relations overlay, child partiality, rollups and all missing-value states. No third permanent pane or viewport lock.

Frontend implementation ownership for this bounded pass: current web agent. Broader dashboard review and any later cleanup remain unscheduled. No claim of independent acceptance.

## Canonical owners

InvestigationWorkspace owns Results/Detail and selected identity; api/navigation owns copied/entity presentation links; WorkResultsPage/workRoute owns loaded membership and accepted queries; DetailView and RecordInspection own the explicit Work presentation variant; SourceStrip owns disclosed source/browser meanings. Existing native disclosures, safe content, tabs, themes, borders and natural document scrolling remain canonical. Other record pages retain their default variant.

## Verification and evidence

Cover phone/desktop child navigation, parent selection, off-page notes, Back/copy/reload, selecting the same record from Results, malformed pane values and API query isolation. Confirm supplied intent/blockers lead and all provenance remains accessible; verify direct detail copying and unaffected sibling layouts. Check long/archived/unknown/refresh-failure states, keyboard/focus, light/dark, narrow reflow and actual zoom where feasible; distinguish viewport checks from actual browser zoom.

Run pinned Node 22 offline gate (types, lint, tests, artifacts, both builds and production exclusion), W01/W02 and affected shared-host W03–W06 browser regressions, and strict premium audit. Runtime is committed before evidence generation. Build/test a clean detached checkout of that exact commit and retain source/tree/build hashes and browser artifacts before publishing corrections. Repository-relative evidence only. Independent review remains separate from implementer verification.

Keep future improvements small and independently revertible while the operator supplies Knowledge/API updates; revisit assumptions when those updates arrive rather than extending speculative contracts.
