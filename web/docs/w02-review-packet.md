# W02 frozen frontend review packet

**Disposition: implemented and locally validated; independent review and frontend acceptance pending.**

- Source freeze: `0e64b31b892a43b05560e13ba0944ad80482269f`, `feat/aew-dashboard-w02`.
- Integration/diff base: fetched `main` at `2e0bf40cfeb49e0ef02a7a16d47ee2b2cb393ac5` (PR #26). W02 began at approved W01 `ab6ab98`, checkpointed at `3872c2c`, then consumed main in merge `7f06be5` without conflicts. Original/main checkouts and Engine tests were untouched. Subsequent documentation/evidence commits do not alter frontend source.
- Approved [plan 1.1](design/plans/w02-workspace.md), SHA-256 `64a89abbc9ea4ecd753d81c6cff9f403ef2e13f61cd013af310db6e7efe1ec4d`. [Approval record](design/plans/w02-approval.json) includes the operator's implementation authorization and later main/CI steering.
- Accepted API 0.1.2, SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`; canonical YAML, generated types and runtime schemas unchanged.
- Frontend lock SHA-256 `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2`; no packages added or dependency changes.

## Implemented tickets

| Ticket | Delivered behavior | Main review focus |
|---|---|---|
| W02-01 | Work/Runs results/detail pilots reuse standalone renderers; presentation selection, bounded paging, mobile Results/Detail controls, desktop inspector and native modal drawer/sheet | Results/graph retention, focus/Escape, concealed-query policy, session-generation reset |
| W02-02 | Shared Why actions on core details, health, Attention, integrity and unavailable capabilities; separately labeled Source and Browser sections | Reasons remain exactly sourced and unbound where contract supplies no status binding; opaque codes; unknown values; access-refusal eviction |
| W02-03 | Shared explicit provenance expansion; 3 levels / 24 nodes / 80 edges; 100-row local relation pages; exact source field and projection metadata | No inferred relationships or completeness; unknown targets terminal; History links distinguish current lookups from archived source |
| W02-04 | Central allowlisted entity/dashboard links, workspace URL selection/inspector/field, clipboard fallback, existing Jump and legacy routes | Malformed syntax versus unknown valid IDs; no presentation wire fields; historical snapshot requests never silently display current data |

New types are **internal frontend presentation adapters**, not AEW wire shapes. `ProjectionHttpError` classifies HTTP status without treating error bodies as authoritative explanation. Observed 401/403 hides and removes the affected query payload and transport validator; ordinary failed/malformed refreshes retain marked valid content. This narrow access-refusal exception does not detect arbitrary cookie or permission changes and does not replace backend authorization.

Work links inside the workspace retain current filters/page/view and change `selected`. Unknown namespaces are not rejected: the user/router chooses an accepted read interface, then the backend resolves the syntactically valid ID. Unknown entity **types** still remain unresolved references because they provide no accepted route. No namespace guessing is added to Jump.

Source contains supplied project, response revision, generation time and contract. Browser separately contains last-check time, per-projection refresh result, dataset and supported snapshot identity. “CURRENT (this projection)” is a browser check result, not backend health or whole-page atomicity. Existing page-level CURRENT/UPDATING/STALE and 30-visible-second rules remain intact.

Record reasons never become a field-specific explanation. Evidence findings/deviations and Work blocked_by remain named sections. Reason codes remain opaque. Knowledge state, integrity status and Attention severity have no accepted known vocabulary; raw warnings, including `WARNING`, remain intentional. Annotation.object has no target-type field: it is terminal rather than assigned a namespace from its relation name. Annotation decision references use the accepted Knowledge destination. Edge inspection includes supplied annotation metadata where relevant.

Provenance graph reads happen only on Expand. The graph retains its loaded sources and shows their revisions; Reset replaces exploration with the latest selected source. Fit-to-width still allows pointer and keyboard pan. List/graph and inspector close/reopen preserve exploration within the session; reload starts from the URL-selected root. Resize across modal/docked modes rebuilds inspector presentation; pan/expansion is not a shareable snapshot. Overall relation completeness remains unknown even when a bounded field has no entries.

## Validation evidence

[Machine-readable result and provenance](w02-evidence/result.json), [offline command log](w02-evidence/offline-command.log), [W02 browser report](w02-evidence/w02-browser-report.json), [W01 regression report](w02-evidence/w01-browser-report.json), [static checksums](w02-evidence/static-manifest.json).

- Immutable Linux/amd64 carrier `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, Node 22.22.2 / npm 10.9.7, empty modules, networking disabled: 395-package offline installation, accepted checksum, generated API types/lab artifacts, typecheck, lint, **116 tests in 14 files**, production guard and separate normal/demo builds PASS.
- **Six detector probes** execute the actual merged workflow detection block. Git is the documented host/CI prerequisite outside the Node carrier; these are not part of the container test count.
- Matched Playwright 1.59.1 / Chromium 1217 (147.0.7727.15): **16 W01 regression groups plus 9 W02 groups PASS** against compiled assets under the proposed CSP. Captured keyboard/modal focus, both themes, phone overflow, deep-link reload, explicit graph/read bounds, hostile content, clipboard failure, dataset-switch cleanup and post-load access refusal. Concealed phone detail was observed over a full 10-second interval and refetched upon reveal.
- No unexpected console/page/CSP errors, external requests, or mutation API traffic. W02 deliberately produced one Not Found 404 for an unfamiliar valid ID and one refused refresh 403; these are individually recorded. W01's authored failed-refresh cases remain individually recorded in its report.
- Unit/component coverage includes the explicit read-session reset with an old graph expansion whose fetch ignores abort. It cannot repopulate the remounted graph. W01 retains old 200/304 context-isolation and normal/manual refresh tests.

Offline execution immediately preceded the source freeze with identical frontend bytes. Frozen compiled-browser execution used that commit. Browser launcher is host Node 24.21.0 with staged OS libraries; application compilation/typechecking/tests are pinned Node 22.22.2. Visibility/focus/PageTransition checks use authored browser events, not OS background-tab or Firefox back-cache acceptance. A synthetic same-origin fixture adapter exercises the normal production bundle; it is not AEW authentication or live integration. No Engine suite was invoked, and no GitHub workflow execution is claimed.

Reproduction from `web/`:

```bash
# Host/CI probe; Git required.
node --test scripts/ci-paths.test.mjs
# Compiled assets and matching browser must already be staged.
node scripts/ci-browser.mjs
node scripts/browser-w02.mjs
```

Offline reproduction from repository root:

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh
```

Screenshots: [Work Why, light](w02-evidence/screenshots/work-why-light.png), [dark](w02-evidence/screenshots/work-why-dark.png), [Work relations](w02-evidence/screenshots/work-relations.png), [Invocation Why](w02-evidence/screenshots/runs-why.png), [phone inspector](w02-evidence/screenshots/work-phone-inspector.png), [History relations](w02-evidence/screenshots/history-relations.png). These are implementer visual checks; operator/main-line visual approval is not claimed.

Historical harness failures are retained with traces: graph pan assertion targeted a clipped part of the canvas; it was corrected to a visible blank area. A tab assertion read before React committed navigation; it now waits for the selected state. Both were harness fixes, not changes to API semantics. Earlier obsolete History selectors and lint issues were fixed before the final gate. Final reports, not partial iterations, determine the current execution result.

[Performance samples and caveats](w02-evidence/performance-summary.json): F6 remains 20 DOM rows and F7 100; four initial API requests in each sample for both frozen W01 and candidate. No observed rendering/request-count regression. Samples were gathered at different wall times and do not establish a causal speedup. Production bundle size grows modestly; the existing >500 KiB advisory is retained, not suppressed or relabeled a new SPT failure.

## CI and integration handoff

Main PR #26 completed the frontend merge/assurance wiring. W02 consumes it. The only CI change authored here is in `web.yml`: run W02 compiled-browser checks alongside W01 and retain both failure-evidence directories. Stable job names, `workflow_call`/manual triggers, contents-read permission, fail-closed changes detection and the single assurance gate remain intact. No W02 edits to `ci.yml`, CodeQL or Python/Engine sources relative to merged main. Branch is local and has not been pushed; future PR targets main.

Remaining integration dependencies link the existing [backend question ledger](design/w01-backend-question-ledger.md) and main registry F20: authoritative session resets, authorization before delivery, supported scopes/snapshots, full-envelope validators, server CSP/security/static serving and live acceptance. W02 does not duplicate their tickets or resolve them using fixtures. No Journal/context/Why preview schema was introduced.

The main AEW reviewer should inspect the frozen code diff independently and distinguish implementer execution evidence from any tests they rerun. Record the review next to this packet, disposition findings, then explicitly accept W02 frontend behavior. Test success alone does not grant acceptance.

## Main-line review amendment — 2026-10-03

Main-line review: AMEND, W02-1. The inherited History relation lookup finding is fixed in `7a18fa3`; see [fixing diff and retest](w02-review-fix-response.md). This addendum supersedes the original pending-review disposition: Lead fixing-diff confirmation and green PR CI remain required. The original source freeze and evidence above remain historical records of the reviewed implementation.
