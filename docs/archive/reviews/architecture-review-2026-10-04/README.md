# The architecture review engagement, 2026-10-04: the record

The ground-up architecture review ([`architecture-review-2026-10-04.md`](../architecture-review-2026-10-04.md),
delivered as `REVIEW.md`) was followed by two days of design threads, probes and prototypes on a frozen clone at
`dcd43f1`. This folder is the record of that engagement: what was asked, what was delivered, and how each piece was
superseded or absorbed. Nothing here governs. Every document that is still a live input moved to `docs/design/proposals/`
or `docs/research/` and is ingested in the requirements ledger; everything in this folder is finished.

Probes, result files and the three prototype patches are in [`eval/reviews/architecture-2026-10-04/`](../../../../eval/reviews/architecture-2026-10-04/).

## How the threads were run

| Record | What it is |
|---|---|
| [`handoff.md`](handoff.md) | The review's own handoff: what the directory held, the facts established (dogfood numbers, ADR-0011 verdicts, code shape), the ten threads T1 to T10 and what each delivered, the eight questions put to the designer, and per-thread fact sections (§8 to §21). Paths in it refer to the review directory, not this repository |
| [`handoff-addendum-designer.md`](handoff-addendum-designer.md) | The designer's addendum, verbatim: T9 and T10 added, and a triage of the remaining threads requested |
| [`triage.md`](triage.md) | The answer: every remaining thread classified (bounded design, targeted research, governance cleanup, wait for dependency) and ranked, with its status at the end of the session |
| [`developer-review.md`](developer-review.md) | The lead developer's review of the [architecture review response](../../../design/proposals/architecture-review-response-2026-10-04.md): **CONCUR WITH MODIFICATION**, five modifications (no event cap where a consumer needs them; CLI relay before MCP as the first typed transport; commit invariants in the store's commit path; the outbox in two steps; the knowledge service identity as a new credential kind). Reconciled under register item Q13 (designer, 2026-10-05): MCP stays the first transport and the CLI-first recommendation is historical input; I1 and I2 are built; the outbox sequencing follows the accepted ADR-0012 and M4-D split |

## What each thread delivered, and where it went

| Thread | Delivered here | Superseded or absorbed by |
|---|---|---|
| T1 typed Lead surface | [`t1-typed-lead-surface-design-v0.1.md`](t1-typed-lead-surface-design-v0.1.md) with the prototype patch | [v0.2](../../../design/proposals/typed-lead-surface-design-v0.2.md) (design frozen, proposed), ledger TLS |
| T2 evaluation component | [`t2-evaluation-component-plan.md`](t2-evaluation-component-plan.md) | [evaluation component v0.2](../../../design/proposals/evaluation-component-design-v0.2.md), ledger EVC |
| T3 transaction outbox | [`adr-0012-transaction-outbox-draft.md`](adr-0012-transaction-outbox-draft.md) | [ADR-0012](../../../implementation/adr/0012-transaction-outbox.md), accepted; ledger OBX |
| T4 knowledge storage placement | [`adr-0013-knowledge-storage-placement-draft.md`](adr-0013-knowledge-storage-placement-draft.md); [`t4-knowledge-manifest-prototype.md`](t4-knowledge-manifest-prototype.md) with its patch | [ADR-0013](../../../implementation/adr/0013-knowledge-storage-placement.md), accepted; ledger KST; the prototype's lessons in [`knowledge-manifest-prototype-lessons-2026-10-04.md`](../../../research/knowledge-manifest-prototype-lessons-2026-10-04.md), ledger KMP |
| T4 question 1, the D9 spike | moved to research as it is still a live input | [knowledge service identity spike](../../../research/knowledge-service-identity-spike-2026-10-04.md), ledger KSI |
| T5 project maps | [`t5-project-maps-v0.1.md`](t5-project-maps-v0.1.md); [`t5-codebase-map-probe-results.md`](t5-codebase-map-probe-results.md) (the `ls-tree` and tree-bound freshness corrections) | [project maps v0.3](../../../design/proposals/project-maps-design-v0.3.md) (design frozen, proposed; it carries both corrections), ledger PMP |
| T6 network containment | [`t6-network-containment.md`](t6-network-containment.md) (the Rocky 8.10 probes); [`t6-register-entry-and-adr-0009-amendment-draft.md`](t6-register-entry-and-adr-0009-amendment-draft.md) (the register row and an earlier ADR-0009 amendment text built on a single credential-injecting proxy; direction accepted by the designer, text superseded) | [network containment v0.2](../../../design/proposals/network-containment-design-v0.2.md), ledger NET; register F28. The ADR-0009 amendment text to land is v0.2's §3 (designer, 2026-10-05); it is still to be written into ADR-0009 (F28) |
| T7 re-freeze and amendment index | [`t7-amendment-index.md`](t7-amendment-index.md); [`t7-citation-test-results.md`](t7-citation-test-results.md) (the refined topic rule flags exactly one real defect: the AT-9 row of the acceptance guide, fixed by the consolidation of 2026-10-05) | [spec amendment index v0.2](../../../design/proposals/spec-amendment-index-design-v0.2.md), ledger SAI; register E19 |
| T8 remote integration target | moved to proposals as a sketch awaiting the designer's scope question | [remote integration target sketch](../../../design/proposals/remote-integration-target-sketch-2026-10-04.md), ledger RIT; register F23, Q14 |
| T9 harness-native integration | [`t9-harness-native-integration-v0.1.md`](t9-harness-native-integration-v0.1.md); [`t9-live-probe-1-opencode.md`](t9-live-probe-1-opencode.md) (what reaches the model from OpenCode 2.0.18; `codemode: false`); [`t9-live-probe-2-codex.md`](t9-live-probe-2-codex.md) (the Codex app-server 0.160.0). The raw model-request captures both probes examined are not published (mostly the harnesses' own system prompts, carrying prompt-cache keys); the probe scripts and console output are in `eval/reviews/architecture-2026-10-04/t9/` | [harness-native integration research v0.3](../../../research/harness-native-integration-research-v0.3.md), which folds in both probes; ledger HNI; register E35, F24 |
| T10 install, bootstrap and first-run UX | [`t10-install-bootstrap-ux-v0.1.md`](t10-install-bootstrap-ux-v0.1.md) | [install and bootstrap UX v0.3](../../../design/proposals/install-bootstrap-ux-design-v0.3.md) (design frozen, proposed), ledger IBU |
| S1 to S8 semantic maps, routing, project understanding | moved to research as live inputs | the seven notes in `docs/research/` dated 2026-10-04 (ledger CXS, CXP, SEF, QRC, LRB, PUI); register F22, F29, F30 |

The three M6 knowledge drafts the review read (capture/admission v0.3, recall/routing v0.2, shared semantics v0.3) are
not kept: their current versions are in `docs/design/proposals/`, and the archived review names the digests it read.
