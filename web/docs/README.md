# Dashboard documentation map

The read-only operator dashboard lives in `web/`. Its documents are kept here, apart from the engine's `docs/`, because
the dashboard has its own review cadence (C0 contract reviews, D0/D1 and the W01 to W06 work packets). This page is the
index. The engine-side record of the dashboard's integration is register item F20 in
[`docs/implementation/future-work.md`](../../docs/implementation/future-work.md), and the wire contract is
[`docs/design/dashboard-api-v1-provisional.yaml`](../../docs/design/dashboard-api-v1-provisional.yaml).

This is a light index written during the documentation consolidation of 2026-10-05. The dashboard's own cleanup
(archiving the evidence bundles, consolidating the review packets) is the web developer's; a later pass will fold it
into the same structure as `docs/`.

## Governing for the dashboard

| Document | What it is |
|---|---|
| [`../UX-CONTRACT.md`](../UX-CONTRACT.md) | The frontend behaviour contract |
| [`../DESIGN.md`](../DESIGN.md) | Design tokens |
| [`design-direction.md`](design-direction.md) | The visual direction of the core candidate |
| [`integration-checklist.md`](integration-checklist.md) | What the main line still has to do to serve the dashboard (F20.2 to F20.6) |
| [`pinned-web-builder.md`](pinned-web-builder.md), [`builder-provenance.json`](builder-provenance.json) | The pinned offline build image |

## Design and planning

| Document | What it is |
|---|---|
| [`aew-readonly-dashboard-design-v0.2.md`](aew-readonly-dashboard-design-v0.2.md) | The parallel frontend design the dashboard was built from |
| [`aew-dashboard-second-llm-handoff-v0.2.md`](aew-dashboard-second-llm-handoff-v0.2.md), [`main-agent-handoff.md`](main-agent-handoff.md), [`design/aew-dashboard-api-waiting-work-and-m6-preview-handoff-v3.md`](design/aew-dashboard-api-waiting-work-and-m6-preview-handoff-v3.md) | Handoff prompts between the builders |
| [`design/aew-dashboard-research-and-parallel-work-backlog-2026-10-02-v2.md`](design/aew-dashboard-research-and-parallel-work-backlog-2026-10-02-v2.md), [`design/dashboard-workbench-milestones-and-tickets.md`](design/dashboard-workbench-milestones-and-tickets.md) | The backlog and the W01 to W06 milestone plan |
| `design/plans/w01-foundation.md` … `w06-execution-investigation.md`, with their `*-approval.json` | One plan per work packet and the operator's approval record |
| `design/w0x-backend-question-ledger.md` | Questions each packet raised for the engine; answered or carried in F20 |
| `design/*-fixtures.manifest.json`, `*-preview-0.1.0.json`, `scenario-config.*` | Preview fixture schemas the frontend builds against. They are frontend previews: the engine's accepted vocabulary governs (architecture review response K6) |

## Reviews, acceptance and validation records

Oldest first. Each packet is the frozen state a reviewer saw; each main-line review is the independent verdict; each
fix response is the builder's answer.

- C0, the API contract: [`c0-review-packet.md`](c0-review-packet.md), [`c0-review-main-line.md`](c0-review-main-line.md) (0.1.0), [`c0-review-main-line-0.1.1.md`](c0-review-main-line-0.1.1.md), [`c0-review-main-line-0.1.2.md`](c0-review-main-line-0.1.2.md), [`c0-approval.json`](c0-approval.json); validations [`validation-c0-amend.md`](validation-c0-amend.md), [`validation-c0-012.md`](validation-c0-012.md)
- The frontend core (D0 to D4): [`frontend-core-review-packet.md`](frontend-core-review-packet.md), [`frontend-core-review-main-line.md`](frontend-core-review-main-line.md), [`frontend-core-review-fix-response.md`](frontend-core-review-fix-response.md), [`d1-visual-review.md`](d1-visual-review.md); validations [`validation-d0.md`](validation-d0.md), [`validation-d1.md`](validation-d1.md), [`validation-core.md`](validation-core.md); browser reports `browser-*-report.json`, [`frontend-core-status.json`](frontend-core-status.json)
- Optional tools and the Work graph: [`optional-developer-tools.md`](optional-developer-tools.md), [`optional-tools-review-main-line.md`](optional-tools-review-main-line.md), [`work-graph-preview.md`](work-graph-preview.md), [`validation-work-graph.md`](validation-work-graph.md), [`work-graph-follow-up.md`](work-graph-follow-up.md), [`http-demo.md`](http-demo.md)
- W01: [`w01-review-packet.md`](w01-review-packet.md), [`w01-review-main-line.md`](w01-review-main-line.md), [`w01-review-fix-response.md`](w01-review-fix-response.md); evidence `w01-evidence/`, `w01-review-fixes-evidence/`; [`design/w01-ci-integration-handoff.md`](design/w01-ci-integration-handoff.md)
- W02: [`w02-review-packet.md`](w02-review-packet.md), [`w02-review-main-line.md`](w02-review-main-line.md), [`w02-review-fix-response.md`](w02-review-fix-response.md), [`w02-ci-repair.md`](w02-ci-repair.md); evidence `w02-evidence/`, `w02-review-fixes-evidence/`, `w02-ci-repair-evidence/`
- W03: [`w03-review-packet.md`](w03-review-packet.md), [`w03-review-main-line.md`](w03-review-main-line.md), [`w03-review-fix-response.md`](w03-review-fix-response.md), [`w03-independent-task-review-template.md`](w03-independent-task-review-template.md), [`design/w03-topic-evolution-assessment.md`](design/w03-topic-evolution-assessment.md); evidence `w03-evidence/`, `w03-followup-evidence/`, `w03-focus-fix-evidence/`
- W04: [`w04-review-packet.md`](w04-review-packet.md), [`w04-review-main-line.md`](w04-review-main-line.md), [`w04-review-fix-response.md`](w04-review-fix-response.md), [`w04-implementation-notes.md`](w04-implementation-notes.md), [`w04-independent-task-review-template.md`](w04-independent-task-review-template.md); evidence `w04-evidence/`, `w04-review-fixes-evidence/`, `w04-ci-repair-evidence/`
- W05: [`w05-review-packet.md`](w05-review-packet.md), [`w05-independent-review/w05-review-main-line.md`](w05-independent-review/w05-review-main-line.md), [`w05-review-fixes.md`](w05-review-fixes.md); evidence `w05-evidence/`, `w05-review-fixes-evidence/`, `w05-independent-review/`
- W06: [`w06-review-packet.md`](w06-review-packet.md), [`w06-review-main-line.md`](w06-review-main-line.md), [`w06-re-review-55c48ec.md`](w06-re-review-55c48ec.md), [`w06-review-corrections.md`](w06-review-corrections.md), [`w06-overnight-review.md`](w06-overnight-review.md)
- Screenshots: `screenshots/`

## Lessons for other work

[`frontend-verification-lessons.md`](frontend-verification-lessons.md) and
[`frontend-verification-skill-handoff.md`](frontend-verification-skill-handoff.md) feed the skills package in
`docs/skills/`; [`spt-toolchain-feedback.md`](spt-toolchain-feedback.md) is feedback to the SPT toolchain.
