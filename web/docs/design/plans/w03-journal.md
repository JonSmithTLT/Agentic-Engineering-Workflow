# W03 — Knowledge Journal flagship

Revision: 1.1 · Operator approved 2026-10-03 by explicitly requesting implementation of this revised plan, including the seven review tightenings. Approval is bound to this file's digest in `w03-approval.json`.

## Outcome and scope

Deliver W03-01–03: compact journal, in-place detail inspector, bounded origin exploration. Use the documented fictional clangd story: stale compilation data → mistaken hypothesis → failed removal → discovery → conditional lesson. The acceptance task is to trace that story, inspect supporting/opposing evidence, and identify canonical references through the UI.

Start from merged W02 `43c5a8f961ff18f9249d62c0ad7f8790f2b33eaf` in the existing frontend checkout on `feat/aew-dashboard-w03`. Preserve local files and other checkouts. Exclude Work redesign, evolution/comparison, retrieval/context-packet inspection, backend implementation and live acceptance. No new dependencies.

## Experience and density

Demo Knowledge defaults to Journal; Records retains the accepted Knowledge collection. Production and existing accepted record-detail links retain their behavior.

```text
Knowledge                 [Journal] [Records]
Journal preview · provisional contract
[Component: All] [Type: All]       [Stream | Table]
Journal stream                 Selected lesson
UTC publication date           ID · kind · applicability
Discovery · concise title      [Summary] [Evidence] [Provenance]
Failed approach · title         One active detail panel
Lesson · title                  Close detail · Copy link
Previous / Next page
```

Two permanent desktop panes; below1024px Stream/Detail switching. Close restores entry focus or stream heading. Entries show kind/title/ID/publication/applicability/origin. Type accents do not encode truth. Semantic table alternative; cursor pages50, no infinite accumulation/new virtualization. Selection survives paging, filtering and display changes; out-of-results selection is labeled.

Summary: claim, supplied retention explanation, applicability, conditions, limitations. Missing explanation reads exactly “No retention explanation supplied.” No synthesized reason. Evidence: explicit supporting/opposing roles. Provenance: exact origin/environment/revision, producer metadata, canonical references and expandable response metadata. Graph/list live within Provenance. Preserve palette/system typography/themes/borders/scrolling; avoid duplicate metadata, stacked graphs or a third permanent pane.

## Preview contract

Journal preview0.1.0 PROVISIONAL is separate from acceptedAPI0.1.2; canonical artifact, strict runtime schemas, inferred types, fixture manifest and SHA-256 registration. Accepted artifact/types/dependency lock unchanged.

Required supplied fields: component identity string|null; published_at UTC timestamp|null; supporting_evidence and opposing_evidence arrays; producer identity metadata; model_id, prompt_id, prompt_version and prompt_digest nullable metadata strings. Raw prompts are excluded and require a separate interface. Other fields: identity/kind/title/claim, separately labeled observed/derived timestamps, applicability/explanation states, conditions/limits, exact origin, canonical references and typed relations. Unknown semantics display raw warnings; invalid structure fails validation.

Ordering is published_at DESC, id ASC. Null publication timestamps form a final Undated group ordered id ASC. Observation/derivation timestamps never substitute. Component filters exact supplied identity; Not supplied matches null. Evidence roles come only from named arrays; empty arrays mean no references supplied in that role, never proof of absence.

## Implementation

Demo-only GET/HEAD proposals: `/api/preview/journal/v0.1/entries` and `/entries/{id}`, bounded cursors and component/type filters. Dynamic demo-only UI/registration/handlers/schemas/fixtures. Contract selector extends existing Playground; no backend adoption claim.

Reuse W01 transport under explicit preview policy/separate context. Project bootstrap first; isolate validators/payloads by digest/dataset/case/project/session. Retire pending reads on scope change. Refusal removes affected data/validator; ordinary refresh failure retains marked valid data. Reuse W02 workspace/source/safe content/navigation/graph through typed adapters; preserve accepted restrictions.

No collection interval; visible detail10seconds, hidden detail stops. 304 preserves payload revision/generation. Explicit graph expansion:3levels/24nodes/80edges; relation-list pages100, exact edge source, unknown types terminal. Display: “The graph contains only loaded supplied relations within the displayed bounds. Absence of a relationship is not evidence that no relationship exists.”

Allowlisted URL presentation restores display/filters/cursor/selection/tab/case on copy/reload, never speculative API fields. Unsupported historical requests are explicit.

Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.

## Verification and review

Checkpoints: schema/story → stream/inspector → origin exploration → final validation; compiled desktop/phone visual check after inspector. Cover tracing, parity, pages/selection, copy/reload/back, keyboard/focus, themes, narrow/long/200%zoom, missing/denied/stale/contradictory/unknown/malformed/empty/refresh failures. Verify isolation/late reads/304/hidden polling, explicit roles/no fabricated explanations, prompt rejection, graph limits/cycles/partiality/source and hostile content under CSP.

Measure large fixtures/requests against frozenW02; no arbitrary timing promise. Pinned Node22 offline gate, W01/W02 and new CHROMIUM_PATH-capable W03 browser suite. Production excludes preview schemas/handlers/fixtures/initialization. Record frozen commit/digest/commands/screenshots/measurements/backend questions. No Engine test suite.

Add “Dashboard page-density and progressive-disclosure review” to `docs/implementation/future-work.md`: Unscheduled, frontendUX owner pending assignment, begin with Work, inventory features and task-review desktop/phone before cleanup tickets. Deferred from W03; no Engine records. Committed references are repository-relative, never machine paths.

Independent reviewer completes mistaken hypothesis → failed removal → discovery → conditional lesson → supporting/opposing evidence → canonical references in desktop AND phone UI, records sourceIDs/steps/outcomes/usability failures, without developer tools/fixture source or arbitrary time target. Frontend acceptance requires that independent review; backend adoption/live integration remain separately pending.
