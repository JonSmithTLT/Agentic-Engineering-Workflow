# Dashboard density review: Work first

Date: 2026-10-04. Register: `docs/implementation/future-work.md`, E16.
Disposition: Work inventory and initial desktop/phone task review complete; cleanup proposals ready for assignment. This is an implementer UX assessment, not independent acceptance or a redesign approval. Other pages have not received a complete density review.

## Evidence and boundaries

Reviewed the reusable service-worker-free demo at port 4251, built from committed W06 source `55c48ec5054a4b6830722978b36bfc4e0d55ff60`, tree `96021ffadbb182482c03d823909ce81dd371a51b`. Build provenance is in `web/docs/w06-evidence/build-provenance.json`. Merged main at review start is `ec727f3c1d4cd9cc29ce131350d061afa7531460`. A Git comparison confirmed no differences in Work.tsx, Investigation.tsx, InvestigationWorkspace.tsx, WorkTable.tsx or styles.css between that frozen source and merged main.

Browser: Codex in-app browser. Desktop 1440×1000; phone viewport 390×844; additional narrow check 720×500. Phone is a viewport review, not a physical-device test. The 720px check is narrow reflow, not a claim of actual browser 200% zoom. System appearance rendered dark; a light narrow check was also captured, then appearance restored to System. Browser actions used product controls. Read-only DOM measurements supplemented visual review; they did not establish domain conclusions.

No runtime code, visual tokens, accepted/provisional contracts, lockfiles or Engine records changed. No feature removal, new scope, authorization change, virtualization replacement or backend API proposed.

Screenshots are original browser JPEGs in `web/docs/reviews/page-density-2026-10-04/`: desktop-detail.jpg, phone-detail.jpg, phone-why.jpg, phone-results.jpg, desktop-large.jpg and narrow-light.jpg. They are baseline observations, not screenshots of a proposed redesign. Full-page captures can show sticky chrome at the current scroll position; use measured document coordinates rather than interpreting its full-page position as a layout defect.

## Feature inventory

| Surface/activity | Existing capabilities | Recommended visibility |
|---|---|---|
| Global shell | Project, backend health, navigation, Jump to ID, API panel, theme, demo case | Retain shell; demo controls are not production density |
| Workspace | Heading, selected ID, copy link, close; phone Results/Detail switch | Retain selection identity and one results/one detail layout |
| Collection | State, kind, direct parent, Table/Hierarchy/Graph, scope explanation | Keep common filter and active filter summary visible; consider advanced disclosure |
| Results | ID/title, kind, supplied state, hot/archive, parent, CLI copying, keyboard render-all option | Preserve semantic table, full-value access and keyboard fallback |
| Dataset navigation | First/Previous/Next, cursor, page record count, Since viewed | Preserve bounded pages and explicit browser-comparison labeling |
| Detail identity | Breadcrumb/ID, currentness, kind/title/state, comparison entry, CLI | Put identity and reported state before inspection utilities |
| Intent | Supplied safe-rendered summary | Primary Summary content; no inferred diagnosis |
| Blockers/reasons | Separate blocked_by and record-level reasons; field-specific Why inspector | Keep blockers visible; retain distinction between reasons and a status explanation |
| Relationships | Related records, direct children, parent, child-filter entry | One Relations activity, retaining child-preview partiality and supplied rollups |
| Projection facts | Risk, plan revision, mutating, archive, attention, integration/commit/sequence, update time | Compact relevant summary; full facts disclosed, missing values remain accessible |
| Provenance | Source project/revision/generated/contract, browser checked/state/dataset/snapshot, footer metadata | One disclosed Provenance activity, with source and browser meanings separate |
| Investigation overlay | Why and Relations tabs, bounded relation exploration, source attribution, copied inspector links | Retain explicit entry and existing focus/close behavior; avoid duplicate default metadata |
| Optional graph | Focus, zoom/pan/fit, branches, supplied page-only hierarchy, selected graph context | Keep opt-in; retain table/tree alternative and loaded-page limitation |

Work therefore has several legitimate activities, not seven dispensable features. The problem is that discovery, explanation, provenance and utility actions all compete in the default detail flow.

## Tasks performed and outcomes

| Task | Steps/identities | Outcome and friction |
|---|---|---|
| Identify blocked work | Desktop F1 table → Review cache provenance, T-0003; phone Results → State BLOCKED → Detail | Correct supplied record and selection retained. Detail title follows source/browser panels rather than leading the activity. |
| Establish supplied blocker | T-0003 → Why state: BLOCKED → close inspector; read blocked_by | Backend says waiting for cache repair review. Why correctly says no status explanation supplied and does not promote blocked_by into one. Source/browser panels precede the explanation again in the overlay. |
| Follow parent and inspect children | T-0003 parent S-0001 → story rollup and Direct children → Inspect children | Desktop filter resets to parent S-0001 and shows four supplied children. Phone remains on Detail, so the changed results are concealed until Results is pressed. |
| Preserve identity across filtering | BLOCKED results with S-0001 selected through its parent link | Selection survives, but S-0001 is absent from results with no explicit off-page/out-of-filter note. This can be mistaken for a mismatch between filters and detail. |
| Explore an alternate display | Phone parent S-0001 results → Graph on this page | Graph remains opt-in and clearly identifies outside-page parent references. Keep this boundary and the linear alternative; do not promote it to a third permanent inspector. |
| Navigate a large frontier | F6 table, 100 records on page; Enter on Projection check 1/T-1000 → Next page | Selection remains T-1000 while the cursor changes to demo-cursor-1. Keyboard selection works; page-scoped table remains bounded. Explicit out-of-page selection explanation should accompany this behavior. |
| Compare a sibling | Knowledge → Journal → J-05 | Journal exposes Summary/Evidence/Provenance activities rather than showing all metadata before the primary content. Reuse its activity pattern, not its domain fields. |

This pass did not conduct a complete historical/denied/error/hostile-content regression or an independent usability study. Those remain implementation acceptance checks, not asserted results of this review. Evidence and comparison destinations were inventoried; their full investigations were not repeated.

## Measured baseline observations

For phone F1 selected T-0003 at 390×844, before opening Why:

| Element | Document Y, CSS px |
|---|---:|
| Work investigation heading | 124 |
| Source heading | 629 |
| Browser heading | 839 |
| Ticket title | 1090 |
| Intent and context heading | 1224 |
| Backend blockers and reasons heading | 1422 |
| Related records heading | 1615 |
| Backend projection heading | 1748 |

Document height was 2564px. Five visible Copy controls existed in the phone detail: two dashboard-link controls, two CLI controls for the selected ticket, and one parent CLI control. The first four are duplicated utility actions, not four distinct user tasks.

For phone F1 parent S-0001 Results with selection retained, the first table body row began at document Y 958px. The table was 800px wide in a 390px viewport: intentional horizontal table scrolling, not evidence of document overflow. The inventory/filter/help/header stack delays scanning before any records appear.

These measurements describe one fixture, viewport and state. They are not a timing SLA, physical-device result or performance comparison.

## Proposed cleanup tickets

All proposals are frontend-only, **Unscheduled**, owner pending assignment. IDs below are local planning references, not Engine tickets. Assign and approve implementation scope at triage.

### PD-01 — Put Work identity and blockers before provenance (first priority)

Problem: default detail puts utilities and two metadata panels ahead of the title; phone blocker inspection requires substantial scrolling.

Proposal: selected ID/kind/title/state and compact currentness lead; use existing InvestigationTabs for Summary / Relations / Provenance. Summary contains intent, supplied blockers and separate record reasons; Relations contains related records, parent/children and explicit exploration entry; Provenance discloses full projection facts, source/browser metadata and response metadata. Relevant integration state, archive warning, attention and parent identity remain visible in a compact summary. Do not hide stale/refusal/partial/unknown warnings in inactive tabs.

Canonical owners: DetailView/RecordInspection through an explicit Work presentation variant; InvestigationTabs, SourceStrip, SafeContent, existing inspector and URL navigation. Do not globally reorder all accepted detail pages as an incidental effect.

Acceptance: on desktop and phone, identity and supplied blocker are encountered before full source/browser panels; all existing fields and missing-value states remain reachable; Why preserves its no-explanation semantics; direct detail links and inspector links retain behavior; tabs retain keyboard focus, copy/reload state and natural document scrolling; two permanent panes maximum. Long summary, archived, stale, unknown and integration states need explicit checks. Record before/after coordinates without imposing an arbitrary height target.

### PD-02 — Give copying one clear owner (second priority)

Problem: selected-ticket CLI and dashboard copy actions repeat before the primary content; every parent reference also adds CLI controls.

Proposal: one workspace dashboard-link control and one selected-record CLI control near identity. Keep relation-specific copying available through an accessible disclosed utility area where needed. No hover-only action or new icon-only menu. Inspectors retain copying of their distinct inspector state.

Acceptance: no duplicate copying of the same current target/state in the default detail; all existing read-only CLI targets remain available to keyboard/touch; labels identify targets; copy payloads/allowlisted navigation remain unchanged; shared EntityAnchor behavior is not weakened elsewhere.

### PD-03 — Reduce results setup overhead (third priority)

Problem: repeated workspace/collection headings, four stacked filters, explanatory paragraph and table controls precede the first phone row.

Proposal: keep State and an active-filter summary visible; disclose Kind and Direct parent through Filters, with active count and clear/reset behavior. Keep display selection accessible. Consolidate repeated introductory text/headings. Shorten default scope copy while disclosing its full archived/page-only meaning. Preserve the render-all keyboard option; do not remove it to gain space.

Acceptance: existing filters remain discoverable without hover; active parent/kind cannot be silently hidden; filter changes reset cursor and retain explicit selection; copy/reload preserves filter/view state; table/tree/graph remain equivalent projections; 100-record accepted paging and virtualization behavior remain unchanged. Compare first-row positions and task steps on desktop/phone with long labels, empty/error and narrow reflow states.

### PD-04 — Make child navigation reveal its result (correctness priority)

Problem: Inspect children changes the filter while phone Detail remains active.

Proposal: add an explicit workspace results-navigation seam so this action reveals Results and focuses its heading below the sticky header, preserving selected parent identity. Show a supplied-selection-outside-current-page/filter note whenever the selected ID is absent from the loaded results. Do not imply the record is missing or clear selection automatically.

Acceptance: desktop and phone S-0001 → Inspect children show parent-filtered results immediately; selected parent survives; browser Back/copy/reload and focus restoration are tested; off-page/filtered selection is labeled, unavailable detail is distinct; no hidden-detail polling regression or speculative API field.

## Recommended sequence and guardrails

Implement PD-04 independently, then PD-01; PD-02 can accompany the detail variant, and PD-03 remains a separate collection checkpoint. Runtime work is not authorized merely by this report. No redesign of global navigation or every page is necessary.

Retain all features, system typography/themes/borders, supplied authority and partiality, natural scrolling, accepted route restrictions, cache/refusal semantics, 10-second visible accepted-detail cadence and hidden-read rules. A disclosed provenance presentation must not imply metadata was absent or stop validation. No new dependencies, API fields, inferred relationships, workflow actions or guarantees.

Future implementation verification: W01/W02 browser regressions plus affected W03–W06 shared-host paths; desktop/phone/light/dark/200% actual zoom; keyboard/tabs/close/Back/copy/reload; empty/denied/stale/failed-refresh/unknown/long fixtures; page replacement and concealed reads; premium static audit. Commit runtime before clean exact-source evidence as established by W06. Independent acceptance remains separate.

## Checks for this documentation review

Read DESIGN.md, UX-CONTRACT.md, Work.tsx, InvestigationWorkspace.tsx, DetailView/RecordInspection, existing E16 and the Journal sibling. Strict premium audit ran with `audit_project.py web --mode strict --no-write`: exit 0, no findings (0 errors/warnings/violations). Its static result does not contradict the observed task hierarchy problems and is not usability acceptance. No runtime tests or new builds were necessary for documentation-only changes.

Work review is complete at this scope. Further dashboard-wide review and all cleanup implementation remain separately assignable.
