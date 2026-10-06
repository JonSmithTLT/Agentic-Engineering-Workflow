# AEW documentation map

Start here. This page says what AEW is building towards, which documents govern, and where everything else lives.
Every document under `docs/` is listed below (a test enforces it), so nothing needs to be found by search. Each document
carries its own status line; where a status line and this page disagree, fix both in the same change.

## Where we're going

AEW lets one Lead run a team of AI agents on real engineering work through a control engine that owns the legality
of every step: what may be dispatched, what evidence a gate needs, and what reaches the authoritative branch.

| Stage | What it proves | State |
|---|---|---|
| M1 | The serial control engine: Tickets, gates, evidence, controlled integration | Done |
| M2 | Epic and Story hierarchy; non-mutating work | Done |
| M3 | A real agent harness (OpenCode V2) behind a custody boundary: no AEW credential in any model's hands | Done (tag `aew-m3-accepted-2026-10-01`) |
| ADR-0011 | Hot and cold control state: cost tracks open work, not history | Done |
| **M4** | **Mutating concurrency above 1:** parallel Tickets, one serial integration lease, a typed Lead surface | **In progress** |
| M5 | A dynamic scheduler (register F11), a second harness adapter (F24) | Planned |
| M6 | M6a: capability manifests, discovery and progressive disclosure, skills (F12, F13). M6b: the knowledge system, capture and recall (F21), guarded history recall first; the semantic map extension (F22.2) | Planned (the split accepted with the review response, Q13, 2026-10-05) |

**M4, phase by phase** ([`m4-ambiguity-report.md`](implementation/m4-ambiguity-report.md) §5):

| Phase | What | State |
|---|---|---|
| M4-A | One dispatch predicate (`DispatchDecision`) for every route; Class 0 eligibility; plan lint | Built |
| M4-B | OS filesystem containment and process ownership on Linux (bubblewrap) | Built |
| M4-C | Workspaces for N > 1 concurrent mutating Tickets | Built |
| M4-D | The integration queue and lease; the transaction outbox (ADR-0012); deterministic integration validation; wait-any; the typed surface's read-only slice (F15.1) | In progress |
| *(gate)* | The F15 direction promoted to governing: the typed Lead surface v0.2 adopted (designer and operator, 2026-10-05) | Met |
| M4-E | Stage commands on the typed surface (F15.2) | Planned |
| M4-F | The queue's normal UX | Planned |
| M4-G | Candidates: Lead and run UX items, the amendment index, Windows coverage, the structural map slice | Planned |
| M4-H | Acceptance: metrics, the preregistered dogfood, independent review | Planned |

**Gates on the way** ([`future-work.md`](implementation/future-work.md) §1): real-repository dogfood waited on containment
(built in M4-B) and the custody-hardening item (closed); network containment (F28) before internal alpha; the F15
promotion before M4-E (met 2026-10-05). What is implemented today, staged or only designed: [`implementation-status.md`](implementation/implementation-status.md).

## What governs, in order

When documents disagree, the earlier one wins.

An unversioned citation of a contract section (`WC §7.4`, `KC §26`) means the **effective** section: the frozen text
plus the adopted amendments that [`spec-amendments.yaml`](spec-amendments.yaml) lists for it, in adoption order. A
citation of the frozen text as it was is version-qualified (`WC v0.7 §7.4`). `tests/unit/test_spec_amendments.py`
checks the index, and that every citation names a real section of the frozen version.

1. **The frozen specification set** `aew-frozen-2026-09-25`, pinned by tag and by `tests/test_spec_pin.py`. These four
   files never change; a change needs a migration review and a new spec set.
   - [`agent-engineering-workflow-design-v0.7.md`](agent-engineering-workflow-design-v0.7.md): the Workflow Contract (WC)
   - [`aew-knowledge-contract-v0.4.md`](aew-knowledge-contract-v0.4.md): the Knowledge Contract (KC)
   - [`spt-agent-toolchain-remediation-v0.2.md`](spt-agent-toolchain-remediation-v0.2.md): the SPT toolchain appendix
   - [`aew-spec-manifest-v0.2.yaml`](aew-spec-manifest-v0.2.yaml): the manifest; [`spec-pin.yaml`](spec-pin.yaml): the hashes
2. **Adopted amendments and decision records** ([`design/`](design/)):
   - [`workflow-contract-amendment-class0-2026-10-01.md`](design/workflow-contract-amendment-class0-2026-10-01.md): Class 0, enforced from M4-A; its §9 amends the KC §26 acceptance case
   - [`plan-assurance-and-classification-decisions-2026-10-01.md`](design/plan-assurance-and-classification-decisions-2026-10-01.md): Q9 and Q10
   - [`decisions-2026-10-01-containment-and-integration-queue.md`](design/decisions-2026-10-01-containment-and-integration-queue.md): containment and process ownership (Q3, F2, E13, the scratch rule), the integration queue (F10, D4)
   - [`architecture-review-response-2026-10-04.md`](design/architecture-review-response-2026-10-04.md): the disposition of the ground-up architecture review, accepted 2026-10-05 (Q13); each item it dispositions is tracked in the register or lives in the ADR or design it names
   - [`plan-assurance-and-premise-validation-design-v0.4.md`](design/plan-assurance-and-premise-validation-design-v0.4.md): the post-M3 plan-assurance direction
   - [`ticket-revision-amendment-2026-09-30.md`](design/ticket-revision-amendment-2026-09-30.md): Ticket revisions
   - [`typed-lead-surface-design-v0.2.md`](design/typed-lead-surface-design-v0.2.md): the typed Lead surface (F15), governing since 2026-10-05: one catalog of typed actions below transport, one runner, `StageResult` and a tri-state `ActionProjection`, MCP (`aew-lead`, broker-side) as the first normal transport and the CLI as parity and recovery; its §11 sequences M4-D, M4-E and M6
   - [`evaluation-component-design-v0.2.md`](design/evaluation-component-design-v0.2.md): the shared evaluation instrument (F19), adopted 2026-10-05: preregistration, the append-only attempt ledger, immutable runs, the hidden-evaluator channel; evaluation-only, never workflow authority; its first slice comes before M4-H's preregistration
   - [`project-maps-design-v0.5.md`](design/project-maps-design-v0.5.md): project maps (T5; F22, F22.1 to F22.3), adopted 2026-10-05, the implementation contract: the deterministic structural core from Git objects with mechanically tracked inputs, the map registry with its own `map_revision` and the closed `map_service` writer, contained semantic extensions (C/C++ first) over exact source views, sibling indexes, typed configuration-qualified queries, untrusted map text, assurance monotonicity, T5-INV-01 to 12; slices T5-A to T5-E
   - [`install-bootstrap-ux-design-v0.3.md`](design/install-bootstrap-ux-design-v0.3.md): installation, bootstrap and first-run UX (T10; F18, F18.1 to F18.4, E21), adopted 2026-10-05: `aew init` proposes and the operator applies, atomically and bound to the proposal; static inspection before trust; isolated generated harness configuration; `aew doctor` diagnoses and never mutates; support follows a qualified pin; host topology still waits for Q12
   - [`aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md`](design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md): the F15 direction, adopted 2026-10-01; where it overlaps the typed Lead surface above, the design governs; it still governs what the design defers to it (§16, §17, the F17 and anomaly obligations)
3. **The ADRs** ([`implementation/adr/`](implementation/adr/)), with their amendments: how the implementation meets the contracts.
4. **The current milestone's plan**: [`m4-ambiguity-report.md`](implementation/m4-ambiguity-report.md), operator-approved.
5. **Cross-document indexes** (they point, they do not decide): [`spec-amendments.yaml`](spec-amendments.yaml): every adopted amendment to the frozen WC and KC, the sections it replaces or extends, the effective section, and the pending consolidation debt (register E19); [`failure-class-registry.md`](design/failure-class-registry.md), [`invariant-index.md`](design/invariant-index.md), and [`requirements-ledger.yaml`](design/requirements-ledger.yaml): every requirement of every ingested design, research or review document, each tracked by register rows (a test-enforced gate).

Everything in [`design/proposals/`](design/proposals/) and [`research/`](research/) is input, not governing. Everything
in [`archive/`](archive/) is a finished record. A "frozen designer decisions" section inside a proposal binds the
proposal's own content; it governs the project only once the proposal is adopted.

## Using AEW ([`guides/`](guides/))

| Guide | For |
|---|---|
| [`quickstart.md`](guides/quickstart.md) | Install, initialize, run one Ticket end to end |
| [`lead-guide.md`](guides/lead-guide.md) | How work flows, for a Lead: risk classes and their gates, the Ticket lifecycle, the command for each step (`aew guide`) |
| [`opencode.md`](guides/opencode.md) | Running AEW with OpenCode: configuration, the Lead's TUI, harness runs, containment |
| [`acceptance.md`](guides/acceptance.md) | The acceptance scenarios and how to run them |

## Living implementation documents ([`implementation/`](implementation/))

| Document | What it is |
|---|---|
| [`implementation-status.md`](implementation/implementation-status.md) | Implemented, staged or designed, capability by capability |
| [`future-work.md`](implementation/future-work.md) | The register: every deferred item, its gate and its milestone. The one place work is tracked; the ledger points into it |
| [`future-work.yaml`](implementation/future-work.yaml) | The register's source (E30): the same preamble, sections and rows as structured data. `future-work.md` is rendered from it by `tools/register.py`; `tests/unit/test_register.py` keeps the two identical |
| [`m4-ambiguity-report.md`](implementation/m4-ambiguity-report.md) | The M4 plan, its decisions, its register triage and each phase "as built" |
| [`testing-and-ci-strategy.md`](implementation/testing-and-ci-strategy.md) | Test lanes, the CI merge gate, static checks, the containment lane |
| [`harness-conformance.md`](implementation/harness-conformance.md) | The harness conformance suite: what every agent harness must pass |

**ADRs:**
[0001](implementation/adr/0001-control-state-persistence.md) control-state persistence ·
[0002](implementation/adr/0002-evaluated-snapshot-fingerprint.md) evaluated-snapshot fingerprint ·
[0003](implementation/adr/0003-ticket-state-machine.md) Ticket state machine ·
[0004](implementation/adr/0004-controlled-integration.md) controlled integration ·
[0005](implementation/adr/0005-authority-credentials-operator.md) authority, credentials and the operator ·
[0006](implementation/adr/0006-role-archetypes-and-cards.md) role archetypes and cards ·
[0007](implementation/adr/0007-epic-story-hierarchy.md) Epic and Story hierarchy ·
[0008](implementation/adr/0008-non-mutating-tickets.md) non-mutating Tickets ·
[0009](implementation/adr/0009-harness-boundary-and-opencode-v2.md) the harness boundary and OpenCode V2 (and containment) ·
[0010](implementation/adr/0010-execution-profiles.md) execution profiles ·
[0011](implementation/adr/0011-hot-cold-control-state.md) hot and cold control state ·
[0012](implementation/adr/0012-transaction-outbox.md) the transaction outbox (accepted; M4-D, first slice PR #53) ·
[0013](implementation/adr/0013-knowledge-storage-placement.md) knowledge storage placement (accepted; M6b) ·
[0014](implementation/adr/0014-release-signing-air-gap-bundle.md) release signing for the air-gap bundle (proposed; the designer asked for one narrow change before adoption, 2026-10-05; F18.3)

Two amendments of 2026-10-05 are designed, not built, and the register tracks their implementation: network containment (ADR-0009; F28, before internal alpha) and the `service` credential kind (ADR-0005, ADR-0009 and ADR-0013 D9; built with M6b, F21).

**Contract with the dashboard:** [`dashboard-api-v1-provisional.yaml`](design/dashboard-api-v1-provisional.yaml) (accepted API 0.1.2; the retained filename is historical). Separate frontend fixture preview contracts remain provisional. The dashboard lives in `web/`, indexed by [`web/docs/README.md`](../web/docs/README.md); its Engine-side integration is register F20; the server's design note is [`dashboard-main-line-api-design-v0.1.md`](design/proposals/dashboard-main-line-api-design-v0.1.md) (approved 2026-10-05).

## Proposals, not adopted ([`design/proposals/`](design/proposals/))

A proposal's adoption state is in its status line and here. "Design frozen, proposed" means the designer has settled its
content and the operator has not yet adopted it; "direction adopted" means the register took its direction but the
text is not governing.

| Proposal | Register | Adoption state | Scheduled |
|---|---|---|---|
| [`spec-amendment-index-design-v0.2.md`](design/proposals/spec-amendment-index-design-v0.2.md) | E19 | Design frozen, proposed | The index now (M4-G); the WC/KC re-freeze after M4-E |
| [`network-containment-design-v0.2.md`](design/proposals/network-containment-design-v0.2.md) | F28 | Design frozen, proposed; direction accepted by the designer | Gate: before internal alpha |
| [`remote-integration-target-sketch-2026-10-04.md`](design/proposals/remote-integration-target-sketch-2026-10-04.md) | F23, Q14 | Sketch, waiting on the designer's scope question (Q14) | Deferred until a team repository requires it; M4-D must not foreclose it |
| [`aew-knowledge-capture-admission-design-v0.4.md`](design/proposals/aew-knowledge-capture-admission-design-v0.4.md) | F21 | Proposed, for joint review with the two below | M6b |
| [`aew-knowledge-capture-recall-shared-semantics-v0.4.md`](design/proposals/aew-knowledge-capture-recall-shared-semantics-v0.4.md) | F21 | Proposed | M6b |
| [`aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md`](design/proposals/aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md) | F21 | Proposed; Arm B (guarded history recall) first | M6b |
| [`execution-workspace-and-isolation-design-v0.1.md`](design/proposals/execution-workspace-and-isolation-design-v0.1.md) | F2 (built), F3 | Proposed; its containment part is built | Input to M4-B (built) and M4-C (built); the strategy abstraction and benchmarks remain |
| [`lead-workflow-efficiency-design-v0.1.md`](design/proposals/lead-workflow-efficiency-design-v0.1.md) | F15 | Proposed; superseded by the governing typed Lead surface v0.2 (2026-10-05; ledger LWE-01, LWE-02 and LWE-04 absorbed or superseded) | Historical input to M4-E |
| [`hierarchy-intent-revision-and-replanning-design-v0.1.md`](design/proposals/hierarchy-intent-revision-and-replanning-design-v0.1.md) | F4, F5 | Proposed; amended by the adopted Ticket-revision amendment | Hierarchy revision milestone, unscheduled |
| [`lead-operator-interaction-design-v0.1.md`](design/proposals/lead-operator-interaction-design-v0.1.md) | F7, F8 | Proposed | Unscheduled |
| [`capability-discovery-and-progressive-disclosure-design-v0.1.md`](design/proposals/capability-discovery-and-progressive-disclosure-design-v0.1.md) | F13 | Proposed | M6a |
| [`AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md`](design/proposals/AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md) | F9 | Frozen at v0.1 | Revisit on dogfood evidence |
| [`shallow-finding-termination-proposal.md`](design/proposals/shallow-finding-termination-proposal.md) | F17 | Proposed (v0.2) | Evaluation baseline first |
| [`dashboard-main-line-api-design-v0.1.md`](design/proposals/dashboard-main-line-api-design-v0.1.md) | F20.2 to F20.7 | Approved with modifications (designer and operator, 2026-10-05; its §7): every decision F20.2 to F20.6 needed, with a recommendation and disposition each, and the slice plan | M4's dashboard track, being built one PR per slice |
| [`cost-usage-ledger-design-v0.1.md`](design/proposals/cost-usage-ledger-design-v0.1.md) | F25, U4 | Proposed; **changes requested** by the designer (2026-10-05): billing semantics (R4) and durable Lead usage (R8) before adoption, the rest of the direction kept | G7's accepted ledger, before any budget enforcement; the build after M4-D's open PRs |

## Research and investigations ([`research/`](research/))

Inputs, not governing. Where a research note once carried a designer decision, the decision now has its own record in
`design/` and the note points at it.

| Document | Fed into |
|---|---|
| [`containment-and-process-ownership-rocky8-research-2026-10-01.md`](research/containment-and-process-ownership-rocky8-research-2026-10-01.md) | M4-B; its §8 decisions are recorded in [`decisions-2026-10-01-containment-and-integration-queue.md`](design/decisions-2026-10-01-containment-and-integration-queue.md) |
| [`m4-integration-queue-research-2026-10-01.md`](research/m4-integration-queue-research-2026-10-01.md) | M4-D; its §7 and §7.1 dispositions are recorded in the same decision record |
| [`adr-0011-storage-investigation-2026-10-01.md`](research/adr-0011-storage-investigation-2026-10-01.md) | ADR-0011 |
| [`aew-phase6-airgap-capability-research-2026-10-01.md`](research/aew-phase6-airgap-capability-research-2026-10-01.md) | M6 (airgap, MCP selection); Q11, Q12 |
| [`external-agent-workflow-lessons-2026-09-28.md`](research/external-agent-workflow-lessons-2026-09-28.md) | Dogfood inputs |
| [`aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md`](research/aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md) | The M6b knowledge designs (F21) |
| [`knowledge-manifest-prototype-lessons-2026-10-04.md`](research/knowledge-manifest-prototype-lessons-2026-10-04.md) | ADR-0013's implementation (F21): what the prototype proved, and the defects not to inherit; E36 |
| [`knowledge-service-identity-spike-2026-10-04.md`](research/knowledge-service-identity-spike-2026-10-04.md) | ADR-0013 D9 proven on a review branch; the ADR-0005/ADR-0009 amendment text (E37); the capture service (F21) |
| [`harness-native-integration-research-v0.3.md`](research/harness-native-integration-research-v0.3.md) | OpenCode qualification (E35), a second adapter (F24), the capability registry (F13) |
| [`cxx-semantic-extraction-investigation-2026-10-04.md`](research/cxx-semantic-extraction-investigation-2026-10-04.md) | The semantic-extension contract (F22.2): what C extraction knows for certain, measured against the build's objects |
| [`cxx-plus-plus-contract-check-2026-10-04.md`](research/cxx-plus-plus-contract-check-2026-10-04.md) | F22.2: the contract holds for C++ with two shared additions (`instances[]`; the edge kinds `dependent`, `virtual` and `overrides`) |
| [`semantic-extension-framework-2026-10-04.md`](research/semantic-extension-framework-2026-10-04.md) | F22.2: the shared contract, the `map.*` query surface, incremental freshness, the architecture-map bridge; the contract freeze's checklist |
| [`query-routing-and-retrieval-classification-2026-10-04.md`](research/query-routing-and-retrieval-classification-2026-10-04.md) | F21 (recall and context routing), F22.2: route by binding and answer shape, measured-gap escalation, four terminal states |
| [`large-repository-benchmark-2026-10-04.md`](research/large-repository-benchmark-2026-10-04.md) | F22.1 (no sharding needed for the structural map), F22.2 (incremental model and a derived index from day one) |
| [`project-understanding-and-impact-analysis-2026-10-04.md`](research/project-understanding-and-impact-analysis-2026-10-04.md) | F30 (the deterministic impact surface feeding plan assurance; the Profile as KC §8 records), F22.3; its §10 holds the designer's decisions of 2026-10-05 |

## Evidence ([`../eval/`](../eval/))

Measurements and probes, kept beside the documents that cite them: the M3 dogfood, live trials and performance runs
(`eval/m3/`), the ADR-0011 baselines and acceptance measurements (`eval/adr-0011/perf/`), and every independent review's
probes and result files ([`eval/reviews/README.md`](../eval/reviews/README.md)).

## Archive ([`archive/`](archive/))

Finished work, kept as the record of what was decided and why. Not edited, except to keep links working.

**Milestones** ([`archive/milestones/`](archive/milestones/)):
M1 [plan](archive/milestones/m1-implementation-plan.md) and [ambiguity report](archive/milestones/m1-ambiguity-report.md) ·
M2 [ambiguity report](archive/milestones/m2-ambiguity-report.md) ·
M3 [ambiguity report](archive/milestones/m3-ambiguity-report.md), [OpenCode V2 rebaseline](archive/milestones/m3-opencode-v2-rebaseline.md), [performance](archive/milestones/m3-performance.md), [dogfood report](archive/milestones/m3-dogfood-report.md), [evidence synthesis](archive/milestones/m3-evidence-synthesis.md) ·
ADR-0011 [implementation plan](archive/milestones/adr-0011-implementation-plan.md)

**Reviews** ([`archive/reviews/`](archive/reviews/)), oldest first. A brief is what the implementer handed the reviewer; a review is the independent verdict; a response is the implementer's answer.

- M1: [independent review](archive/reviews/m1-independent-review-2026-09-26.md) (do not merge: two blockers), the [remediation re-review](archive/reviews/m1-remediation-re-review-2026-09-26.md), and the [response](archive/reviews/review-response-2026-09-26.md)
- M2: [reviewer brief](archive/reviews/m2-reviewer-brief.md) and [response](archive/reviews/review-response-2026-09-27.md)
- The companion designs: [review integration bundle](archive/reviews/review-integration-bundle-2026-09-28.md) and the [M3 companion review triage](archive/reviews/m3-companion-review-triage.md)
- M3: [reviewer brief](archive/reviews/m3-reviewer-brief.md), [audit findings](archive/reviews/m3-audit-findings.md), the [independent audit of temporal boundaries and intent fidelity](archive/reviews/m3-independent-audit-2026-09-29.md) and its [response](archive/reviews/review-response-2026-09-29.md), the [independent review of the freeze](archive/reviews/m3-independent-review-2026-09-30.md) (not accepted over R1 and R2) and the [acceptance review response](archive/reviews/review-response-2026-10-01.md)
- [Ticket revision amendment review](archive/reviews/ticket-revision-amendment-review-2026-09-30.md)
- ADR-0011: [reviewer brief](archive/reviews/adr-0011-reviewer-brief.md); the phase reviews [P2a](archive/reviews/adr-0011-p2a-review.md), [P2b](archive/reviews/adr-0011-p2b-review.md), [P2c](archive/reviews/adr-0011-p2c-review.md), [P2d](archive/reviews/adr-0011-p2d-review.md); the [P3 acceptance-gate review](archive/reviews/adr-0011-p3-review.md) (request changes: P1, P2) and the [fix re-review](archive/reviews/adr-0011-p3-re-review.md)
- M4 area reviews (2026-10-03/04), each with its reproduction in `eval/reviews/`: [area 1, containment and process ownership](archive/reviews/m4-area1-containment-review-2026-10-04.md) · [area 2, authority and credential custody](archive/reviews/m4-area2-authority-custody-review-2026-10-03.md) · [area 3, dispatch legality](archive/reviews/m4-area3-dispatch-legality-review-2026-10-03.md) · [area 4, integration and publication](archive/reviews/m4-area4-integration-publication-review-2026-10-03.md) · [area 5, control-state persistence](archive/reviews/m4-area5-control-state-persistence-review-2026-10-03.md). Their findings are register E31 to E34 and the Lead-custody amendment of ADR-0009
- The architecture review, ground up (2026-10-04): [the review](archive/reviews/architecture-review-2026-10-04.md), dispositioned by the [accepted response](design/architecture-review-response-2026-10-04.md); the engagement that followed it is recorded in [`architecture-review-2026-10-04/`](archive/reviews/architecture-review-2026-10-04/README.md): the [handoff](archive/reviews/architecture-review-2026-10-04/handoff.md), the designer's [addendum](archive/reviews/architecture-review-2026-10-04/handoff-addendum-designer.md), the [triage](archive/reviews/architecture-review-2026-10-04/triage.md), the lead developer's [review of the response](archive/reviews/architecture-review-2026-10-04/developer-review.md), and the threads as delivered before their current versions: [ADR-0012 draft](archive/reviews/architecture-review-2026-10-04/adr-0012-transaction-outbox-draft.md), [ADR-0013 draft](archive/reviews/architecture-review-2026-10-04/adr-0013-knowledge-storage-placement-draft.md), [T1 typed surface v0.1](archive/reviews/architecture-review-2026-10-04/t1-typed-lead-surface-design-v0.1.md), [T2 evaluation plan](archive/reviews/architecture-review-2026-10-04/t2-evaluation-component-plan.md), [T4 prototype](archive/reviews/architecture-review-2026-10-04/t4-knowledge-manifest-prototype.md), [T5 maps v0.1](archive/reviews/architecture-review-2026-10-04/t5-project-maps-v0.1.md) and [probe](archive/reviews/architecture-review-2026-10-04/t5-codebase-map-probe-results.md), [T6 network containment](archive/reviews/architecture-review-2026-10-04/t6-network-containment.md) and its [register entry and ADR-0009 amendment draft](archive/reviews/architecture-review-2026-10-04/t6-register-entry-and-adr-0009-amendment-draft.md), [T7 amendment index](archive/reviews/architecture-review-2026-10-04/t7-amendment-index.md) and [citation test](archive/reviews/architecture-review-2026-10-04/t7-citation-test-results.md), [T9 harness-native integration v0.1](archive/reviews/architecture-review-2026-10-04/t9-harness-native-integration-v0.1.md) with live probes [1, OpenCode](archive/reviews/architecture-review-2026-10-04/t9-live-probe-1-opencode.md) and [2, Codex](archive/reviews/architecture-review-2026-10-04/t9-live-probe-2-codex.md), [T10 install UX v0.1](archive/reviews/architecture-review-2026-10-04/t10-install-bootstrap-ux-v0.1.md)

**Records** ([`archive/`](archive/)): the register's [change log to 2026-10-05](archive/register-changelog-to-2026-10-05.md), the *Last updated* line the preamble carried before concurrent register changes were made to merge.

**Superseded** ([`archive/superseded/`](archive/superseded/)):
[plan assurance v0.3](archive/superseded/plan-assurance-and-premise-validation-design-v0.3.md), replaced by
[v0.4](design/plan-assurance-and-premise-validation-design-v0.4.md);
[project maps v0.3](archive/superseded/project-maps-design-v0.3.md) (design frozen 2026-10-04) and
[v0.4](archive/superseded/project-maps-design-v0.4.md) (the consolidation proposed for the freeze, 2026-10-05), replaced by
[v0.5](design/project-maps-design-v0.5.md), adopted 2026-10-05

## Skills

Candidate agent skills, their specification and evaluation: [`skills/README.md`](skills/README.md).

## Keeping this map true

- A new document goes in the folder its status says, and on this page in the same change. Status lines say what a
  document is (governing, adopted direction, design frozen and proposed, proposed, research, record) and the date that
  was last true.
- A new design, research or review document is **ingested, not just placed**: every requirement goes into
  [`requirements-ledger.yaml`](design/requirements-ledger.yaml) and is tracked by a register row. A new version of a
  document is re-mapped section by section; a requirement it drops is retired with its disposition, never deleted.
  `tests/unit/test_requirements_ledger.py` enforces it.
- A designer decision belongs in a decision record or an ADR under `design/` or `implementation/adr/`, never only in a
  research note or a proposal; a research note that received one points at the record.
- Work is tracked in one place, the register ([`future-work.md`](implementation/future-work.md)): a design's work items
  are its rows, a review's findings are its rows, and a closed item moves to §9 with what closed it.
- The register is edited as data: change [`future-work.yaml`](implementation/future-work.yaml), then run
  `python tools/register.py render`; the markdown is the view and `tests/unit/test_register.py` fails when it drifts.
  Every open row's target column starts with one bold target from the register's own table.
- The register merges: its preamble carries no per-change log (the history is `git log` on the YAML and each row's
  own dates; the log to 2026-10-05 is [archived](archive/register-changelog-to-2026-10-05.md)), and §9 *Closed* is kept in id
  order, which `render` applies and `check` enforces, so append a closed row anywhere. After every sync with main,
  run `render`, conflict or not: a clean merge can still leave §9 unsorted and the markdown stale, which `check` and
  CI refuse. When a merge conflicts, resolve `future-work.yaml` only, then run `render`: the markdown is derived and
  is never merged by hand.
- When a milestone finishes, its plan, reports and review responses move to `archive/`. An independent review's record
  moves to `archive/reviews/` and its probes to `eval/reviews/` when the review is delivered.
- `tests/unit/test_docs_links.py` fails if a relative link breaks or a document under `docs/` is missing from this page.
