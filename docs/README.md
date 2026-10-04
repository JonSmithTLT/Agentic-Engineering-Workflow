# AEW documentation map

Start here. This page says what AEW is building towards, which documents govern, and where everything else lives.
Every document under `docs/` is listed below (a test enforces it), so nothing needs to be found by search.

## Where we're going

AEW lets one Lead run a team of AI agents on real engineering work through a control engine that owns the legality
of every step: what may be dispatched, what evidence a gate needs, and what reaches the authoritative branch.

| Stage | What it proves | State |
|---|---|---|
| M1 | The serial control engine: Tickets, gates, evidence, controlled integration | Done |
| M2 | Epic and Story hierarchy; non-mutating work | Done |
| M3 | A real agent harness (OpenCode V2) behind a custody boundary: no AEW credential in any model's hands | Done (tag `aew-m3-accepted-2026-10-01`) |
| ADR-0011 | Hot and cold control state: cost tracks open work, not history | Done |
| **M4** | **Mutating concurrency above 1:** parallel Tickets, one serial integration lease | **In progress** |
| M5 | A dynamic scheduler (register F11) | Planned |
| M6 | M6a: capability manifests, discovery and progressive disclosure, skills (F12, F13). M6b: the knowledge system, capture and recall (F21), guarded history recall first | Planned (the split is proposed: Q13) |

**M4, phase by phase** ([`m4-ambiguity-report.md`](implementation/m4-ambiguity-report.md) §5):

| Phase | What | State |
|---|---|---|
| M4-A | One dispatch predicate (`DispatchDecision`) for every route; Class 0 eligibility; plan lint | Built |
| M4-B | OS filesystem containment and process ownership on Linux (bubblewrap) | Built |
| M4-C | Workspaces for N > 1 concurrent mutating Tickets | Next |
| M4-D | The integration queue and lease; deterministic integration validation; wait-any | Planned |
| M4-E | Stage commands (F15) | Planned; gated on the designer promoting F15 to governing |
| M4-F | The queue's normal UX | Planned |

**Gates on the way** ([`future-work.md`](implementation/future-work.md) §1): real-repository dogfood waits on
containment (built in M4-B) and one custody-hardening item. What is implemented today, staged or only designed:
[`implementation-status.md`](implementation/implementation-status.md).

## What governs, in order

When documents disagree, the earlier one wins.

1. **The frozen specification set** `aew-frozen-2026-09-25`, pinned by tag and by `tests/test_spec_pin.py`. These four
   files never change; a change needs a migration review and a new spec set.
   - [`agent-engineering-workflow-design-v0.7.md`](agent-engineering-workflow-design-v0.7.md): the Workflow Contract (WC)
   - [`aew-knowledge-contract-v0.4.md`](aew-knowledge-contract-v0.4.md): the Knowledge Contract (KC)
   - [`spt-agent-toolchain-remediation-v0.2.md`](spt-agent-toolchain-remediation-v0.2.md): the SPT toolchain appendix
   - [`aew-spec-manifest-v0.2.yaml`](aew-spec-manifest-v0.2.yaml): the manifest; [`spec-pin.yaml`](spec-pin.yaml): the hashes
2. **Adopted amendments and decisions** ([`design/`](design/)):
   - [`workflow-contract-amendment-class0-2026-10-01.md`](design/workflow-contract-amendment-class0-2026-10-01.md): Class 0, enforced from M4-A
   - [`plan-assurance-and-classification-decisions-2026-10-01.md`](design/plan-assurance-and-classification-decisions-2026-10-01.md): Q9 and Q10
   - [`plan-assurance-and-premise-validation-design-v0.4.md`](design/plan-assurance-and-premise-validation-design-v0.4.md): the post-M3 plan-assurance direction
   - [`ticket-revision-amendment-2026-09-30.md`](design/ticket-revision-amendment-2026-09-30.md): Ticket revisions
   - [`aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md`](design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md): the F15 direction, adopted; promoted to governing before M4-E
   - the designer's decision sections of two research documents: the integration queue ([§7 and §7.1](research/m4-integration-queue-research-2026-10-01.md)) and containment ([§8](research/containment-and-process-ownership-rocky8-research-2026-10-01.md))
3. **The ADRs** ([`implementation/adr/`](implementation/adr/)), with their amendments: how the implementation meets the contracts.
4. **The current milestone's plan**: [`m4-ambiguity-report.md`](implementation/m4-ambiguity-report.md), operator-approved.
5. **Cross-document indexes** (they point, they do not decide): [`failure-class-registry.md`](design/failure-class-registry.md), [`invariant-index.md`](design/invariant-index.md), and [`requirements-ledger.yaml`](design/requirements-ledger.yaml): every requirement of every ingested design, research or review document, each tracked by register rows (a test-enforced gate).

Everything in [`design/proposals/`](design/proposals/) and [`research/`](research/) is input, not governing, except
the decision sections named above. Everything in [`archive/`](archive/) is a finished record.

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
| [`future-work.md`](implementation/future-work.md) | The register: every deferred item, its gate and its milestone |
| [`m4-ambiguity-report.md`](implementation/m4-ambiguity-report.md) | The M4 plan, its decisions and each phase "as built" |
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
[0011](implementation/adr/0011-hot-cold-control-state.md) hot and cold control state

**Contract with the dashboard:** [`dashboard-api-v1-provisional.yaml`](design/dashboard-api-v1-provisional.yaml) (provisional; the dashboard itself lives in `web/`).

## Proposals, not adopted ([`design/proposals/`](design/proposals/))

| Proposal | Register | Scheduled |
|---|---|---|
| [`execution-workspace-and-isolation-design-v0.1.md`](design/proposals/execution-workspace-and-isolation-design-v0.1.md) | F2, F3 | Input to M4-B (built) and M4-C |
| [`lead-workflow-efficiency-design-v0.1.md`](design/proposals/lead-workflow-efficiency-design-v0.1.md) | F15 inputs | Input to M4-E |
| [`hierarchy-intent-revision-and-replanning-design-v0.1.md`](design/proposals/hierarchy-intent-revision-and-replanning-design-v0.1.md) | | Unscheduled |
| [`lead-operator-interaction-design-v0.1.md`](design/proposals/lead-operator-interaction-design-v0.1.md) | F8 | Unscheduled |
| [`capability-discovery-and-progressive-disclosure-design-v0.1.md`](design/proposals/capability-discovery-and-progressive-disclosure-design-v0.1.md) | F13 | M6 |
| [`AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md`](design/proposals/AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md) | F9 | Frozen; revisit on dogfood evidence |
| [`shallow-finding-termination-proposal.md`](design/proposals/shallow-finding-termination-proposal.md) | F17 | Evaluation baseline first |
| [`aew-knowledge-capture-admission-design-v0.4.md`](design/proposals/aew-knowledge-capture-admission-design-v0.4.md) | F21 | M6b; for joint review with the two below |
| [`aew-knowledge-capture-recall-shared-semantics-v0.4.md`](design/proposals/aew-knowledge-capture-recall-shared-semantics-v0.4.md) | F21 | M6b |
| [`aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md`](design/proposals/aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md) | F21 | M6b; Arm B (guarded history recall) first |
| [`architecture-review-response-2026-10-04.md`](design/proposals/architecture-review-response-2026-10-04.md) | Q13; F21 to F27, E18 to E30 | The proposed disposition of the 2026-10-04 architecture review; awaiting the lead developer's review and acceptance |

## Research and investigations ([`research/`](research/))

| Document | Fed into |
|---|---|
| [`containment-and-process-ownership-rocky8-research-2026-10-01.md`](research/containment-and-process-ownership-rocky8-research-2026-10-01.md) | M4-B; §8 is the designer's decisions (governing) |
| [`m4-integration-queue-research-2026-10-01.md`](research/m4-integration-queue-research-2026-10-01.md) | M4-D; §7 and §7.1 are the designer's disposition (governing) |
| [`adr-0011-storage-investigation-2026-10-01.md`](research/adr-0011-storage-investigation-2026-10-01.md) | ADR-0011 |
| [`aew-phase6-airgap-capability-research-2026-10-01.md`](research/aew-phase6-airgap-capability-research-2026-10-01.md) | M6 (airgap, MCP selection) |
| [`external-agent-workflow-lessons-2026-09-28.md`](research/external-agent-workflow-lessons-2026-09-28.md) | Dogfood inputs |
| [`aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md`](research/aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md) | The M6b knowledge designs (F21) |

## Archive ([`archive/`](archive/))

Finished work, kept as the record of what was decided and why. Not edited, except to keep links working.

**Milestones** ([`archive/milestones/`](archive/milestones/)):
M1 [plan](archive/milestones/m1-implementation-plan.md) and [ambiguity report](archive/milestones/m1-ambiguity-report.md) ·
M2 [ambiguity report](archive/milestones/m2-ambiguity-report.md) ·
M3 [ambiguity report](archive/milestones/m3-ambiguity-report.md), [OpenCode V2 rebaseline](archive/milestones/m3-opencode-v2-rebaseline.md), [performance](archive/milestones/m3-performance.md), [dogfood report](archive/milestones/m3-dogfood-report.md), [evidence synthesis](archive/milestones/m3-evidence-synthesis.md) ·
ADR-0011 [implementation plan](archive/milestones/adr-0011-implementation-plan.md)

**Reviews** ([`archive/reviews/`](archive/reviews/)), oldest first:
[M1 review response](archive/reviews/review-response-2026-09-26.md) ·
[M2 reviewer brief](archive/reviews/m2-reviewer-brief.md) and [response](archive/reviews/review-response-2026-09-27.md) ·
[companion design review bundle](archive/reviews/review-integration-bundle-2026-09-28.md) ·
[M3 companion review triage](archive/reviews/m3-companion-review-triage.md) ·
[M3 reviewer brief](archive/reviews/m3-reviewer-brief.md) ·
[M3 audit findings](archive/reviews/m3-audit-findings.md) ·
[M3 independent audit](archive/reviews/m3-independent-audit-2026-09-29.md) and [response](archive/reviews/review-response-2026-09-29.md) ·
[Ticket revision amendment review](archive/reviews/ticket-revision-amendment-review-2026-09-30.md) ·
[M3 acceptance review response](archive/reviews/review-response-2026-10-01.md) ·
[ADR-0011 reviewer brief](archive/reviews/adr-0011-reviewer-brief.md) ·
[architecture review, ground up (2026-10-04)](archive/reviews/architecture-review-2026-10-04.md), dispositioned by the [proposed response](design/proposals/architecture-review-response-2026-10-04.md)

**Superseded** ([`archive/superseded/`](archive/superseded/)):
[plan assurance v0.3](archive/superseded/plan-assurance-and-premise-validation-design-v0.3.md), replaced by
[v0.4](design/plan-assurance-and-premise-validation-design-v0.4.md)

## Skills

Candidate agent skills, their specification and evaluation: [`skills/README.md`](skills/README.md).

## Keeping this map true

- A new document goes in the folder its status says, and on this page in the same change.
- A new design, research or review document is **ingested, not just placed**: every requirement goes into
  [`requirements-ledger.yaml`](design/requirements-ledger.yaml) and is tracked by a register row. A new version of a
  document is re-mapped section by section; a requirement it drops is retired with its disposition, never deleted.
  `tests/unit/test_requirements_ledger.py` enforces it.
- When a milestone finishes, its plan, reports and review responses move to `archive/`.
- `tests/unit/test_docs_links.py` fails if a relative link breaks or a document under `docs/` is missing from this page.
