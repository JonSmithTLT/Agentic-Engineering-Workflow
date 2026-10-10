# Maps and raw-history search — web implementation plan 1.0

Date: 2026-10-10. Preparation baseline: merged main `7e944fffc6080db16094485911f456f37b8e7de7`. Operator signed off the independently CLEAR dashboard contract plan v6, then instructed the web agent to start. This document makes the web implementation concrete; it does not claim C0 renewal, backend implementation, a new package baseline or live acceptance.

## Authority and delivery order

Source handoff: `dashboard-maps-search-contract-plan-v6-CLEAR.md`, independently reviewed as `dashboard-plan-v6`. Its repository successor will be `docs/design/proposals/dashboard-maps-and-history-search-v0.1.md` in S0. That note is not present at this baseline. #143 is merged; #148 remains open at preparation time. Preserve the original handoff/review externally; do not claim a draft file is an adopted repository contract.

The operator's approval covers this workflow, including operator-only Arm B search. Model-visible recall, production Cases/Lessons and Q7 treatment changes remain excluded.

1. Preparation now: grounded UI plan and ownership inventory, independent plan review. No accepted contract edits or new runtime modules before the required prerequisites.
2. **W1 only after S0 merges:** adopt contract additions through fresh-context C0 review, parsers/types/capabilities and fixtures. Start from the merged S0 baseline, not an unmerged branch.
3. **Maps UI after S1 merges; Search UI after S2 merges:** separate independently reversible checkpoints, each from merged dependencies. The handoff's dependency graph puts the web UI after served routes; fixtures can exercise the approved contract but do not remove that gate.
4. **S3 after both pages merge:** propose an exact frontend commit, obtain explicit packaged-baseline agreement, clean pinned build/import and authenticated live acceptance with search on/off. Preserve `4f0a710` until then.

No backend implementation, dependencies, existing preview wire models, Engine work records or unrelated checkout changes. Review/CI failures take priority; main red blocks merges. Refreshed prerequisite status and exact runtime baseline are recorded at each checkpoint.

## Operator tasks and density

Maps answers: what stored structural map am I looking at, against which commit is it current, what is omitted, and how do two explicitly chosen roots differ? Raw-history search answers: which authenticated historical references match my explicit request, and how incomplete might this result be?

```text
Maps — derived navigation context
Registry state · map revision · compared-against commit
[Selected map] [Stored maps] [Compare maps]
Selected root / source commit · freshness and supplied reasons
[Sections] [Inputs] [Provenance]
One active table/activity · supplied truncation/omission counts

History → Raw history (not admitted Knowledge)
Terms [                         ] [Clear]
[Kinds] [Since UTC] [Until UTC] [Limit] [Search]
Raw-history trust label · complete/incomplete coverage + reasons
Result ID · kind · recorded time · trust label
Plain-text framed snippet · supplied expansion link · Copy CLI
```

No third pane, extra graph, overview score, automatic map generation, test execution or inferred acceptance. System typography, light/dark tokens, restrained borders and natural document scrolling follow [DESIGN.md](../../../DESIGN.md) and [UX-CONTRACT.md](../../../UX-CONTRACT.md). Native controls retain their established OS popup ownership. Desktop semantic tables become labeled rows or bounded panel scrolling on phone; IDs remain inspectable in full. Below 1024px use existing Results/Detail where selection actually replaces content.

Only one map section is displayed at a time; Inputs is cursor-paged, never accumulated. Comparisons require two explicit roots, with clear A/B source identity and typed differences. Differences beyond a supplied cap remain unknown, never “no changes.” Architecture reference navigation uses its supplied Evidence link, not artifact paths.

## W1 — contract and client readiness

- Apply the merged S0 appendix; preserve every existing 0.1.2 response wire shape and envelope constant. New maps/search responses use 0.1.3. Open capability maps may gain the exact declared capability entries; strict response objects are not loosened.
- Generalize the envelope constructor to a route-specific version; retain explicit existing parser constants. A latest-contract global constant must not cause old 0.1.2 payloads to fail. Keep all preview digest/schema contexts separate.
- Regenerate accepted types from the adopted canonical artifact. Update contract checks/registry and approval provenance only with actual C0 review. Retain 0.1.2 as an ACCEPT predecessor. Record actual version/digest after adoption, never before review.
- Include `integrated` in the reviewed open-string known-value annotation and frontend vocabulary if confirmed by C0; this does not expand a closed enum or change the response shape. Unknown strings still warn.
- Extend transport routes, query builders and capability gating explicitly. Full map object IDs/roots and query bounds are checked before reads. No arbitrary path/ref/revspec enters an API query or copied command.
- Fixture envelopes are per route, matching accepted types. Capabilities distinguish maps with no selected data from absent history_search. Worker and HTTP adapters share projectors; new accepted-contract fixture modules remain excluded from production response data.
- S0 compatibility tests must preserve response-property names literally named `description` or `x-*`; stripping annotations cannot strip properties. Check readiness evidence for the v6 review's implementation note rather than changing backend code in W1.

## Shared behavior owners and changes

| Capability | Existing owner | Scoped extension |
|---|---|---|
| Routes/bootstrap/capabilities | main router, Shell, client/dashboard, api/links | Maps route and a capability-gated History search route; project bootstrap first |
| Transport/query identity | ReadTransport, ReadContext, client/queries | Explicit maps route policy, per-route envelope parsing, repeatable parameter builder, manual read policy |
| Tables/paging | CollectionView/Pager, existing responsive table CSS | Root selection and input pages with endpoint-specific limits; no all-results selection |
| Tabs/focus/panes | InvestigationTabs, InvestigationWorkspace, focusBelowHeader | Maps active section and responsive selection; selected root remains visible |
| Safe source and provenance | SafeContent/Content, SourceStrip, Reasons, PageSnapshot | Map data rendered as escaped text; search snippet framed as plain text, never Markdown |
| Copy CLI/navigation | api/cli, CopyCli, EntityAnchor, navigation/reference-return | Shared allowlisted argv formatter if needed; accept only the documented `aew history show <id>` template, never arbitrary supplied commands |
| Search form | No canonical submitted-search form exists | One small domain form with noValidate, associated inline errors, native controls, explicit Search/Clear and stable busy feedback |

Maintain DESIGN/UX contracts with the runtime checkpoint. Do not replace existing native selects, add a UI library or duplicate transport/cache machinery.

## Read scheduling, scope and restoration

- `/maps` summary: 30-second cadence only while its page is displayed, plus foreground revalidation through the established coordinator. No hidden summary reads.
- Detail, inputs and diff: navigation/manual refresh only. Disable all automatic paths, including interval, focus and revision reconciliation; do not merely remove a timer.
- Search: **explicit submit/retry only**, never interval, focus, revision reconciliation, mount, reload, typeahead or prefetch. Supplied read may append derived search batches, which is why generic debounce defaults do not apply. Repeat submissions may be needed to progress bounded coverage.
- Keep draft input distinct from the submitted query. Disable duplicate submission while pending, permit cancellation through Clear, and retire obsolete results when the submitted identity changes. Clear immediately resets draft/submitted result and validator ownership, then focuses the input; it never issues an empty search.
- Search terms stay in memory, not URL/localStorage or copied dashboard links, to avoid storing operator-entered possibly sensitive text and to avoid search execution on reload. Back within the current in-memory session can restore the submitted result with no read; reload starts an empty form. This documented search-specific override leaves existing global navigation behavior intact.
- Query builders preserve repeated `term` and `kind` values and their declared ordering. Other params remain single-valued. Do not use the current generic get/set copy helper for repeated search arrays. Search limits/date validation follow the adopted contract and encoded query-size ceiling, including non-ASCII input and IME composition.
- Maps links allowlist selected root, section, input cursor, explicit compared-against commit and comparison roots. Restoration never substitutes current for a pinned root. Browser Back restores active activity/cursor/scroll and originating focus. Unknown/deprecated historical parameters yield an explicit unsupported result before reads.
- Query and validator ownership includes accepted contract identity, project/session, route plus all explicit filters/roots/cursors. Map revision is separate from control revision; do not treat a map selection as a workflow change. Preserve valid 304 payload/generation, refusal clearing and obsolete-response exclusion. Retain only active map detail/input/diff pages and one active submitted search representation; page bodies do not accumulate.
- When history_search disappears, retire/remove its requests/data/validators and remove navigation. A direct search link then shows “not offered on this project,” without requesting the route. Offered-but-unavailable remains a capability result. Stale or partial search coverage is not equivalent to no hits.

## States and acceptance

Maps: NONE registry, INVALID registry, missing/corrupt selected artifact, unavailable detail, current/stale/unknown freshness, capped scan, dropped/cut items, input paging, differing roots and beyond-cap changes. Unknown semantic values remain raw warnings unless the accepted projector has already dropped invalid values with counts. A derived map or selected architecture reference blocks nothing.

Search: off/absent, on/available, on/unavailable, empty valid result, incomplete coverage, moved history, foreign/stale/unusable substrate, deadline/build/candidate budgets and unverified count. Trust labels/authority fence stay visible per hit and per response. Use exact supplied links only; null expansion means no product link. Clipboard failure gives selectable command text. No Knowledge admission, truth, semantic ranking or benefit inference.

Both: loading, ordinary refresh failure with visibly retained valid data, refusal clearing, malformed/binding rejection, hostile strings and session/project switch. Desktop selection preserves row focus; phone replacement or direct navigation focuses the relevant heading below sticky chrome. Arrow/Home/End tabs retain tab focus. No generic banner hides the only error or completeness result.

## Verification and review checkpoints

1. **Preparation:** independent review of this plan against v6, shared owners and current code. Resolve findings before W1.
2. **W1:** pinned Node 22 offline gate, artifact/docs checks, canonical contract compatibility, generated types, parser rejection tests, old 0.1.2/preview regression tests and renewed independent C0 review. No UI/live acceptance claim.
3. **Maps:** compiled desktop/phone inspection; keyboard/theme/200% zoom, paging/selection/copy/Back and malicious maps; count intervals/hidden/manual-only reads and bounded retained bodies. Measure representative large bounded responses; no invented timing SLA.
4. **Search:** component and compiled worker/HTTP tests for explicit request counts, Clear/IME/obsolete responses, capability disappearance, partial coverage and inert snippets; verify no implicit reads even after focus/visibility/revision/reload. No terms in public evidence/log fixtures beyond explicitly fictional test input.
5. **Live:** extend the CHROMIUM_PATH-capable authenticated runner for both pages; actual server with search on and off, production bytes/CSP, real conditional requests and exact old/new contract envelopes. Backend owners provide the authorized project/session and retention guarantees. Preserve F20.6 as its own acceptance item.
6. **Freeze/package:** commit runtime before clean detached pinned build/tests; complete source/tree/contract/lock/builder/build hashes and screenshots. Verify unchanged source/build afterward. Fresh-context exact-head AGENTS review, green assurance and normal merge gates. Propose S3 source explicitly; operator approval of this plan does not pick a package commit.

Each checkpoint can be reverted independently. New routes cannot be claimed usable until their backend slices and capability policy are merged. Revalidate this plan against the exact merged S0 appendix; material contract/authority changes require renewed review rather than assumptions.

## W1 prerequisite update (2026-10-10)

S0 merged as `6f8cc28`; W1 starts from merged main `60a26c398dfd37dd2e5101d4e4ab09633838db99`. Preparation plan 1.0 received independent CLEAR at SHA-256 `d93aef31c08f721964abc2bc75e8cdfbe2b8287c2b2e88f7f6035fa6ad28afff`. The original preparation status above is historical. See [W1 adoption](../../implementation/maps-history-contract-adoption.md) for current scope and gates. Maps/Search UI still waits for served S1/S2 dependencies.
