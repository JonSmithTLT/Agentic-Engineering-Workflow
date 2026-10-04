# AEW architecture review response and disposition

**Date:** 2026-10-04  
**Status:** Proposed designer/operator response for joint review; not governing until accepted. The lead developer's review requested in §15 is delivered ([developer review](../../archive/reviews/architecture-review-2026-10-04/developer-review.md), 2026-10-04: CONCUR WITH MODIFICATION); acceptance and the reconciliation of its modifications are register item Q13.  
**Source review:** [`architecture-review-2026-10-04.md`](../../archive/reviews/architecture-review-2026-10-04.md) — *AEW architecture review, ground up* (delivered as `REVIEW.md`; this response calls it that)  
**Purpose:** Convert the wide-ranging architecture review into controlled project input without turning the review itself into a replacement roadmap or design authority.

## 1. Disposition model

`REVIEW.md` remains intact as architecture-review evidence.

This response does **not** adopt the review wholesale. Each finding is routed using one of these dispositions:

- **ACCEPT** — direction is sound and should enter the relevant existing work/design.
- **ACCEPT WITH MODIFICATION** — underlying finding is sound, but the proposed mechanism or sequencing should change.
- **NEEDS DESIGN/DECISION** — review identified a real architectural question; resolve it explicitly before implementation.
- **DEFER** — useful idea, but not a current architecture correction or milestone gate.
- **PROBE / EVALUATE** — evidence is insufficient to select the mechanism; test before policy/design freeze.
- **NO ACTION — AFFIRMED** — review confirms an existing architecture that should remain stable.
- **REJECT AS WRITTEN** — finding may be useful, but the proposed mechanism would create the wrong semantics or coupling.

The intended flow is:

```text
REVIEW.md
    ↓
this disposition response
    ↓
explicit decisions / ADRs / accepted design amendments
    ↓
existing roadmap / future-work / Tickets
    ↓
implementation
```

Not:

```text
REVIEW.md
    ↓
new master roadmap
```

The review is an overlay and decision input. It does not silently replace approved M4 sequencing.

---

## 2. Executive outcome

The review's central architectural diagnosis is accepted:

> AEW's control plane, authority model, evidence binding, legality model, containment direction, and hot/cold history are substantially more mature than its evaluation, project-knowledge, and operator/product surfaces.

The most important outcome is **not** to add every proposed feature. It is to promote a small set of cross-cutting primitives and decisions that several future systems already need:

1. **Evaluation becomes a first-class AEW component**, not an experiment-specific script.
2. **The Lead/operator surface becomes typed**, with the Engine remaining the authority and MCP/CLI/dashboard acting as transports.
3. **AEW gets a durable transaction outbox/event substrate** for committed-state notifications; consumers are at-least-once and idempotent.
4. **Knowledge durability/integrity placement is decided explicitly** before M6 knowledge implementation.
5. **Knowledge v1 stays project-scoped** instead of introducing an unused multi-scope security model.
6. **Knowledge vocabulary receives a glossary pass** before schema freeze.
7. **M6 is split conceptually into capability/skills work and knowledge work** so one milestone label does not hide multiple programmes.
8. **Q12 hosting/session ownership is resolved earlier**, because too many later surfaces depend on it.
9. **The existing authority/evidence/hot-cold/dispatch foundations are affirmed and are not reopened.**

Everything else is routed below.

# 3. Ranked architecture findings G1–G12

## G1 — Evaluation is the critical path and not yet a component

**Disposition: ACCEPT.**

The finding is correct. Too many design hypotheses now depend on an evaluation mechanism that exists only as M3-specific machinery.

Promote F19 into a reusable evaluation component with:

- versioned fixture and run-record schemas;
- preregistration pinned before paid/model execution;
- evaluator/hidden-test material outside worker reach;
- metrics collection from AEW run/usage/evidence records;
- preserved failed/invalid runs;
- support for AEW incident-derived fixtures;
- model/harness/configuration identity sufficient for comparison.

Seed with real AEW incidents where durable evidence exists. External benchmark slices are useful comparators if they fit the air-gap/gateway constraints, but selection is a probe rather than an architecture decision.

**Sequencing:** evaluation infrastructure should exist before M4-H's consequential dogfood/evaluation claims. It does not become a reason to stop unrelated already-approved M4 implementation.

**Design work required:** yes — evaluation component contract and schemas.

## G2 — The Lead surface is a shell and the shell carries measured cost/defects

**Disposition: ACCEPT WITH MODIFICATION.**

Accept the need for a typed action surface. Do **not** define MCP itself as the authority surface.

Target architecture:

```text
typed AEW action/service surface
        ↓
same Engine operations
same DispatchDecision
same PrimitiveSpec / guards
        ↓
transport adapters:
    MCP
    CLI
    dashboard
    scheduler
```

F15 stage operations should be the small normal surface. Primitive CLI remains recovery/debug/conformance.

The typed surface should return structured `ActionProjection`-style results including revision, completed steps, runs, blockers, and decisions required.

MCP is the leading harness transport because it removes shell quoting/YAML/frontmatter failure classes and supports progressive tool disclosure, but the semantics must remain usable by other transports/harnesses.

Mechanical retry after stale revision is allowed only where the existing primitive semantics explicitly permit it. Judgment-bearing actions never retry into a decision.

**Sequencing:** align with F15/M4-E. Transport-specific implementation may trail the semantic stage surface if needed.

**Design work required:** yes — typed action surface + transport boundary.

## G3 — Project-knowledge maps are specified but largely unimplemented

**Disposition: ACCEPT WITH MODIFICATION.**

The gap is real and distinct from experiential M6 Cases/Lessons.

Split the work:

### Deterministic project map
Candidate for earlier work:

- directory/build/test topology;
- generated/source boundaries;
- entry points where deterministic;
- language/package boundaries;
- source revision and affected paths;
- freshness derived from current source state.

### Semantic architecture/ownership/glossary material
Later and explicitly derived/model-authored where necessary.

Bounded relevant map fragments should eventually enter role/context packs.

**Modification:** do not call a generated codebase map `K0` merely because it is deterministic. K0 in the knowledge design is a canonical-reference class. A generated map is **derived project knowledge with freshness/provenance** and may contain K0 references.

**Design work required:** bounded project-map design, but not a blocker for the knowledge capture architecture.

## G4 — Only one real harness adapter

**Disposition: ACCEPT RISK; DEFER AS A GATE.**

A second real adapter is strategically valuable because it validates the abstraction and reduces dependency on OpenCode's protocol.

It is **not** currently evidence that the harness abstraction is wrong, and it should not automatically expand M4.

Target: second adapter by M5/M6 capability work or earlier if OpenCode drift becomes an operational blocker. The existing conformance suite remains the acceptance mechanism.

**Probe required:** current Codex/Claude/OpenCode protocol behavior against the organization's actual environment.

## G5 — Containment does not provide network isolation and Windows is weaker

**Disposition: ACCEPT RISK; DEFER TO PRE-ALPHA SECURITY DESIGN.**

The current design is truthful about its guarantees. That remains the minimum requirement.

Network egress control, provider-key isolation via proxy, two-account deployment, and WSL-based Windows execution are credible future hardening directions, but require explicit threat-model and operability work.

Do not silently expand the current F2 claim.

**Design/research required:** before internal alpha if the deployment threat model requires network containment or cross-UID isolation.

## G6 — Contract amendments are becoming a second specification

**Disposition: ACCEPT.**

Near term:

- create a machine-readable amendment index beside the spec pins;
- record what section is replaced/amended and adoption date;
- keep research documents out of the governing chain by copying accepted decisions into the proper decision/ADR records.

After M4:

- plan a consolidated WC/KC re-freeze so readers do not need a long override chain.

**Design work required:** small consolidation/migration plan, not a new architecture.

## G7 — Cost is not an AEW-owned engineering fact

**Disposition: ACCEPT WITH MODIFICATION.**

Build the **cost/usage ledger** before trying to enforce budgets.

Ledger should capture/roll up at least:

- model/provider/profile;
- token categories where available;
- wall time;
- reported/provider cost when trustworthy;
- policy-price-table derived estimated cost;
- run → invocation → Ticket → parent rollups.

This is needed by F19, routing/model comparison, F15 efficiency claims, and dashboard observability.

**Modification:** do not make USD budget a DispatchDecision refusal merely because the ledger exists. Budget enforcement is a policy decision and should follow measurement/calibration, likely with M5/F7 unless a concrete earlier need appears.

## G8 — Q12 blocks too many downstream surfaces

**Disposition: ACCEPT.**

Resolve the hosting/Lead-session/wrapper-ownership shape during the M4-D/M4-E window rather than leaving it as an indefinite future decision.

This decision should explicitly address:

- who owns the long-lived harness/service process;
- Lead seat acquisition/loss/recovery;
- wrapper/session lifecycle;
- dashboard/session attachment;
- how capability and knowledge service identities attach;
- which state is harness-private versus AEW-owned.

**Design/decision required:** yes.

## G9 — Knowledge drafts introduce visibility semantics AEW does not currently need

**Disposition: ACCEPT SIMPLIFICATION.**

For M6 knowledge v1:

```text
visibility_scope = project
```

Retain the invariant:

> derived visibility cannot exceed its contributing roots without an explicit authorized widening.

Retain scoped-before-limit behavior in the schema/contract so future team/org scopes are not foreclosed.

Do **not** implement multi-scope/multi-tenant visibility until Q12/deployment requirements create a real consumer.

## G10 — No team/remote integration target

**Disposition: DEFER.**

The issue is real for eventual team use, but remote-PR integration is a deployment/product feature rather than a defect in the current local-authority model.

Design when the first team repository/internal-alpha target requires it. At that point the external SCM remains a separate authority and `DONE` semantics require explicit contract/ADR work.

Do not add it to M4 by default.

## G11 — No durable committed-event/outbox model

**Disposition: ACCEPT.**

This is the strongest new shared primitive in the review.

Queue/wait-any, dashboard updates, scheduler work, and knowledge capture all need to observe committed AEW changes without independently polling/reconstructing them.

Design a transaction outbox such that:

- event append is atomic with the state commit/revision;
- event identity includes revision, kind, and relevant durable IDs;
- consumers have durable cursors/checkpoints where needed;
- consumers are **at-least-once**, idempotent, and replay-safe;
- event retention is bounded/archived consistently with ADR-0011;
- the outbox is not a second workflow authority.

Do **not** promise exactly-once consumer processing. The commit can contain one durable event identity; downstream handling remains at-least-once.

**Design work required:** yes — likely ADR-level because several subsystems will depend on it.

## G12 — Operator attribution through Lead is attribution, not cryptographic proof

**Disposition: ACCEPT DIRECTION; POLICY-DEPENDENT.**

For consequential operator-only actions, reuse the terminal-authenticated/operator-session mechanism where the project policy requires stronger attribution.

Do not require this ceremony for every ordinary operator annotation.

Candidate uses before internal alpha:

- high-impact waiver;
- operator pin;
- security-sensitive `accepted_open`;
- authority/visibility widening;
- other explicitly classified consequential decisions.

# 4. Bounded mechanism improvements I1–I12

| ID | Disposition | Response |
|---|---|---|
| **I1 writable-root validation** | **ACCEPT / HIGH PRIORITY** | Validate operator-declared writable roots against protected AEW/git/run/bridge/interpreter/mask roots and include them in containment self-test. This is an implementation hole, not a redesign. |
| **I2 `host_pid` matching** | **ACCEPT** | Fail clearly when no valid mapping exists; use the full `NSpid` chain required by E13 semantics. |
| **I3 evidence/read JSON** | **ACCEPT DIRECTION** | `evidence show` and structured/JSON read surfaces support both humans and the typed service surface. Avoid designing the typed surface as a wrapper around unstable prose. |
| **I4 Lead read-only git allow-list** | **ACCEPT** | Expand only bounded read-only reconnaissance operations proven useful. |
| **I5 pin acceptance inputs** | **ACCEPT** | This is the deterministic part of F14 and directly closes the known acceptance-input mutation path for repository-local inputs. |
| **I6 executable `consumer_search`** | **ACCEPT DIRECTION** | Good deterministic F17 mechanism. Implement when the obligation design is active rather than as unrelated M4 scope. |
| **I7 plan-bound reviewer default** | **PROBE / NEEDS POLICY** | Plausible, but avoid adding automatic review ceremony by label alone. Test against real review Tickets and F14/F15 semantics. |
| **I8 init discovers tests/maps** | **ACCEPT DIRECTION** | Propose discovered test commands; never silently configure. Deterministic map portion depends on G3 design. |
| **I9 supervisor heartbeat doctor check** | **ACCEPT AFTER MEASUREMENT** | Useful truthful diagnostic once large-host reparse bounds are measured. |
| **I10 Windows coverage** | **ACCEPT** | Windows-specific containment/process code should not stay outside the coverage picture. |
| **I11 generated archetype command refs** | **ACCEPT** | Land after F15/typed action names stabilize. |
| **I12 SSE dashboard transport** | **ACCEPT DIRECTION** | Prefer outbox-fed updates once G11 exists; exact HTTP/SSE contract remains F20 work. |

# 5. Tech-stack recommendations

## 5.1 Hot state

**NO ACTION — AFFIRMED.**

Keep YAML/human-readable hot authority. ADR-0011 addressed the measured scale problem.

## 5.2 FTS over history/evidence/decisions

**ACCEPT DIRECTION.**

FTS5 on the existing derived SQLite history/index layer is the correct lexical baseline for guarded history recall.

Do not let the FTS index become authority. Rebuildability and source identity remain required.

## 5.3 Generated/static typed Python record models

**ACCEPT DIRECTION.**

Build-time generation or checked `TypedDict`/equivalent can reduce `dict[str, Any]` ambiguity without adding runtime authority/dependencies.

Implementation choice remains open.

## 5.4 Release packaging / offline artifact

**ACCEPT DIRECTION.**

Fits F18/release engineering. Does not alter architecture.

## 5.5 Real Rocky 8 CI/live lane

**ACCEPT GOAL; ENVIRONMENT-DEPENDENT.**

The current target/kernel acceptance cannot be proven by generic hosted CI. Exact infrastructure depends on organizational availability.

## 5.6 Split oversized Windows serial job

**ACCEPT.**

Follow the existing testing strategy; do not hide cost by merely raising timeouts.

## 5.7 Dashboard lifecycle timeline / ActionProjection

**ACCEPT DIRECTION.**

The dashboard should project Engine-owned lifecycle/action semantics rather than invent them.

## 5.8 OpenTelemetry-shaped local spans

**DEFER / PROBE.**

Potentially useful for F19 and dashboard observability, but do not add telemetry machinery without a concrete consumer and air-gap-safe storage/retention plan.

# 6. MCP / typed tool surfaces

## `aew` Lead surface

**ACCEPT DIRECTION**, subject to G2.

Semantics live in the typed AEW action/service surface. MCP is a preferred adapter, not the owner.

## `aew-run` role surface

**ACCEPT DIRECTION.**

The existing custody boundary should remain: credentials stay supervisor-side; role tools forward typed operations through the bridge.

Do not widen role authority simply because submission becomes typed.

## `aew-knowledge`

**ACCEPT AS M6b DIRECTION.**

Initial operations should sit over guarded exact/lexical history and later K0/K1 knowledge. Final tool names are not frozen.

## Structured `check.run`

**ACCEPT.**

Return bounded structured results plus artifact references; full logs remain expandable evidence, not ambient prompt text.

## External docs and language-server providers first

**ACCEPT AS PRIORITY HYPOTHESIS**, not governing sequencing.

Evaluate against real air-gap usefulness/cost once F19 exists.

# 7. Skills recommendations

## Minimal delivery path before full capability registry

**NEEDS DESIGN / PROBE.**

The current problem is real: skill cards can request skills that are always unavailable.

A minimal hash-pinned project skill delivery path may be valuable before the full M6 registry, but it must not accidentally become a second capability-resolution system that F13 later has to replace.

Design it as the smallest compatible subset of the future registry.

## Lead skills

**ACCEPT AS EVALUATION CANDIDATES.**

Scope/reconnaissance, protected-goal-input thinking, and classification calibration come directly from observed Lead failures.

Do not promote them by intuition; run through F19.

## Role skills

**ACCEPT AS CANDIDATES.**

Verification-evidence, report-authoring, and scope/reconnaissance are grounded in observed failures.

## Evaluation

**ACCEPT.**

All skill claims should use the same F19 component rather than a separate eval framework.

## Language manuals / generic skill expansion

**DEFER.**

No measured need yet.

# 8. Whole-feature ideas F-A–F-K

These remain **feature candidates**, not adopted roadmap entries merely because they appear in the review.

| Feature | Disposition | Response |
|---|---|---|
| **F-A typed Lead surface/operator inbox** | **ACCEPT DIRECTION** | Absorbed into G2 + G11 + F15. |
| **F-B project maps** | **ACCEPT DIRECTION** | Split deterministic map from semantic architecture knowledge; see G3. |
| **F-C replay** | **ACCEPT NARROWER DIRECTION** | Prioritize deterministic historical **state/context reconstruction**. Full execution replay is not assumed cheap or deterministic across providers/tools/environments. |
| **F-D cost ledger/budgets** | **ACCEPT LEDGER; DEFER ENFORCEMENT** | See G7. |
| **F-E second harness adapter** | **ACCEPT STRATEGICALLY; DEFER GATE** | See G4. |
| **F-F network containment** | **DEFER TO PRE-ALPHA DESIGN** | See G5. |
| **F-G remote integration target** | **DEFER UNTIL TEAM REPO REQUIRES IT** | See G10. |
| **F-H hash-pinned acceptance inputs/oracles** | **ACCEPT DETERMINISTIC HALF** | Repository-local acceptance-input digests now; broader protected evaluator remains F14 work. |
| **F-I model-diverse review** | **PROBE / EVALUATE** | Expressible today; adopt only if unique-defect yield justifies cost/noise. |
| **F-J dogfood AEW on AEW** | **ACCEPT AS STRATEGIC GOAL** | Appropriate once containment/real-repo/integration conditions are met and cost is tolerable. Not an immediate implementation item. |
| **F-K lease expiry/automatic takeover** | **DEFER / NEEDS DESIGN** | Automatic authority/session turnover can create subtle custody/recovery semantics. Do not infer it from current lease friction. |

# 9. Knowledge-system findings K1–K9

The three knowledge design documents remain the preferred architecture direction. These findings are primarily **integration decisions**, not reasons to reopen Case/Lesson/admission/recall fundamentals.

## K1 — Knowledge storage/integrity is unplaced

**Disposition: NEEDS ADR / DESIGN.**

Accept the reviewer's requirement for **one integrity story**, but not the literal proposal that every capture-job/retry object become an ADR-0011 history entry.

Recommended split:

### Existing audited/history integrity domain
Belongs under the ADR-0011 integrity/audit story:

- admitted K0/K1/K2/K3 durable Knowledge content;
- durable knowledge dispositions;
- consequential relation/supersession decisions;
- consequential delivery/admission receipts needed for reconstruction/audit.

### Operational job/outbox domain
May be separately durable but is not project/history authority:

- capture queue state;
- retry timers;
- provider retry bookkeeping;
- transient candidate-processing status;
- worker cursors.

Consequential results are archived/pinned into the audited knowledge/history domain.

Required decision:

> Does admitted knowledge extend the existing history manifest as new entry kinds, or share its integrity primitive through a sibling manifest under the same audited root?

Prefer one audit/integrity mechanism. Avoid turning the history manifest into a background-work queue.

## K2 — Capture triggers need a durable event source

**Disposition: ACCEPT.**

Use G11's transaction outbox.

Capture consumers are at-least-once and idempotent.

## K3 — Visibility is a new security model

**Disposition: ACCEPT SIMPLIFICATION.**

M6b v1 is project-scoped only.

Keep the most-restrictive-root composition invariant and schema extension points for later hosting/team scopes.

## K4 — Knowledge service identity

**Disposition: NEEDS DESIGN; ACCEPT PRINCIPLE.**

Create a new bounded credential subject/kind through the existing credential-verifier/custody architecture.

Do **not** automatically make it a Lead credential or place it semantically under Lead authority.

Requirements:

- enumerated operations only;
- credentials unreachable from worker shells;
- rotation/revocation rules explicit;
- project/session/hosting binding defined by Q12;
- no authority to mutate workflow truth outside its declared knowledge operations.

Whether Lead takeover revokes it depends on whether Lead generation is part of the credential's authority basis; do not assume it is.

## K5 — Vocabulary collisions

**Disposition: ACCEPT.**

Before schema freeze, perform a glossary pass across:

- workflow/closeout dispositions;
- knowledge dispositions;
- evidence admissibility;
- supersession variants;
- serving eligibility;
- review-independence levels;
- knowledge admission classes.

Prefer qualified names where shared words already have established meanings, e.g. `knowledge_disposition`.

This should feed the project's long-missing glossary rather than become another local terminology table.

## K6 — Frontend preview schemas must not become backend semantics by familiarity

**Disposition: ACCEPT.**

Engine/domain semantics own:

```text
MATCHED
SELECTED
PREPARED
DELIVERY_ACKNOWLEDGED
CITED_OR_REFERENCED
BENEFIT_EVALUATED
```

or whatever final accepted vocabulary results.

Frontend preview contracts adapt to the accepted backend/domain model.

W04/W05 remain valuable product/fixture design and must not silently become the source of backend authority.

## K7 — Research basis is missing from repository

**Disposition: ACCEPT.**

Add the research basis and the three design drafts to the documentation map under their actual non-governing status before joint adoption review.

Preserve provenance/digests.

## K8 — M6 is overloaded

**Disposition: ACCEPT CONCEPTUAL SPLIT.**

Use:

### M6a — Capabilities and skills
- capability registry/manifests;
- progressive disclosure;
- provider health/resolution;
- skill delivery/registry;
- harness-native capability integration.

### M6b — Knowledge and recall
- guarded explicit history recall;
- lexical baseline;
- K0/K1 capture/admission;
- knowledge durability/dispositions;
- agent-use evaluation;
- K2 shadow/evaluation;
- context routing/automatic discovery only after evidence.

Release/toolchain work can support both rather than becoming a third semantic M6 programme.

Whether the milestone files are literally renamed/split is an implementation-planning decision; the conceptual separation should be preserved.

## K9 — Guarded raw-history recall is the cheapest knowledge increment

**Disposition: ACCEPT.**

First M6b implementation experiment:

```text
explicit guarded history search
+ exact expansion
+ project scope
+ source identity/provenance
+ untrusted-data framing
+ FTS lexical baseline
```

This is arm B, not automatic context delivery.

In parallel/next, replay proposed K1 templates over M1–M3 history to measure how much useful experience is representable as safe Cases before freezing those templates.

# 10. Knowledge-specific follow-ups from §6.3

## Recall context-budget order

**Disposition: ACCEPT AS A CURRENT PACK INVARIANT.**

Reserve context in this order:

1. mandatory role/system/capability constraints;
2. current work/accepted intent/authority/guardrails;
3. current source/evidence required for the role;
4. optional historical recall.

This rule can enter pack-generation semantics before recall exists.

## Workflow disposition is not proof

**Disposition: ACCEPT.**

Cross-reference F17 and the knowledge contract/design.

`accepted_open`, `known_limit`, etc. describe how work proceeded; they do not prove the observation false, harmless, or universally acceptable.

These outcomes are useful K1 Case material **with the source disposition preserved**.

# 11. Architecture explicitly affirmed — no redesign

The review's §7 is accepted.

The following foundations should be treated as stable inputs to future work unless new empirical evidence reveals a defect:

- single authority/commit model and custody design;
- generation fencing and takeover semantics;
- evidence binding to plan/attempt/snapshot/check definition;
- ADR-0011 hot/cold state and history independence;
- one dispatch-legality predicate and registered entrypoints;
- failure/reason/primitive registries;
- deterministic regression/test lane discipline;
- truthful containment labels;
- harness rule that adapters/telemetry do not become workflow authority.

Future designs should consume these rather than reopen them for convenience.

# 12. Sequencing response

Do **not** copy REVIEW.md §8 wholesale into the roadmap.

The following items are allowed to affect near-term sequencing because they are shared primitives or gates:

### M4-B/C immediate corrections
- I1 writable-root validation;
- I2 host-PID correctness;
- other accepted M4-B review fixes already in scope.

### M4-D/E shared architecture work
- G11 outbox design/implementation;
- Q12 decision;
- G2 typed action-surface design aligned with F15;
- wait-any consuming the accepted event/outbox primitive where feasible.

### M4-G/H
- cost **ledger** if bounded;
- deterministic project-map slice if it does not jeopardize approved M4 scope;
- F19 evaluation component before consequential M4-H dogfood claims;
- accepted deterministic F14/I5 protections.

### After M4 / M5
- contract re-freeze;
- second real harness adapter;
- wider resource/budget enforcement;
- scheduler on existing legality/action surfaces.

### M6a
- capabilities/progressive disclosure/skills.

### M6b
- guarded history recall first;
- knowledge storage/integrity + service identity;
- K0/K1;
- agent-use evaluation;
- K2 shadow/evaluation;
- automatic discovery after evidence.

### Pre-internal-alpha candidates, not current M4 gates
- network containment;
- two-account deployment;
- remote SCM/PR integration;
- stronger operator-attribution policy.

Any of these may move if a current implementation dependency proves the assumed ordering wrong, but REVIEW.md alone does not authorize milestone expansion.

# 13. New design/decision work created by this review

The review does identify additional design work. Create only the pieces that resolve shared architecture, not one design document per idea.

## D-AR1 — Evaluation component design

Resolve:

- fixture identity/versioning;
- preregistration;
- protected evaluator material;
- run record;
- metrics;
- incident corpus;
- comparator integration;
- replay/context-reconstruction needs.

Target: before M4-H evaluation claims.

## D-AR2 — Typed AEW action surface / F15 transport design

Resolve:

- semantic action surface versus transport;
- stage operations;
- ActionProjection;
- mechanical retry rules;
- MCP/CLI/dashboard adapters;
- role bridge typed submission.

Target: M4-E/F15.

## D-AR3 — Transaction outbox ADR/design

Resolve:

- commit atomicity;
- event identity/schema;
- cursor/consumer contract;
- retention/archive;
- idempotency/replay;
- consumers: wait-any, dashboard, capture, later scheduler.

Target: M4-D.

## D-AR4 — Knowledge durability and automation integration ADR

Resolve:

- admitted knowledge placement under ADR-0011 integrity;
- transient capture-job durability;
- disposition/event indexing;
- FTS/source expansion;
- service credential kind/custody;
- project-only v1 visibility;
- Q12 dependency.

Target: before M6b implementation beyond guarded raw history.

## D-AR5 — Q12 hosting/session decision

Resolve the process/service/session ownership assumptions needed by Lead, dashboard, capability, and knowledge services.

Target: M4-D/E window.

## D-AR6 — Project-map design

Resolve deterministic map schema/freshness and bounded pack inclusion; keep semantic architecture-map authoring separate.

Target: bounded slice when useful; not a mandatory M4 blocker.

## D-AR7 — Contract consolidation/re-freeze plan

Amendment index now; consolidated WC/KC after M4.

# 14. Items that should *not* create new design work yet

Do not start dedicated designs for these solely because the review proposed them:

- network egress proxy;
- two-account deployment;
- remote PR integration;
- automatic Lead lease expiry/takeover;
- full execution replay;
- organization/team knowledge visibility;
- generic OpenTelemetry integration;
- broad language/manual skill library.

They remain candidate future work until deployment pressure, experiments, or accepted milestones create a concrete requirement.

# 15. Requested developer review

The next reviewer/lead developer should review **both** `REVIEW.md` and this response.

Please do not merely vote on the review's ideas. Challenge this disposition from an implementer's perspective.

Focus on:

1. **Hidden implementation coupling:** which accepted directions require changes lower in the stack than this response assumes?
2. **State growth:** do outbox, evaluation, knowledge dispositions, receipts, or cost ledger accidentally recreate hot-state/history-growth problems ADR-0011 removed?
3. **Authority seams:** does the typed action surface, outbox consumer, knowledge service identity, or dashboard path create a second way to mutate authoritative state?
4. **Failure/recovery:** what happens across crash between commit, outbox consumption, capture processing, indexing, and delivery?
5. **Sequencing:** which proposed near-term items truly block approved M4 work, and which should remain later even if architecturally attractive?
6. **Complexity:** where is the response solving a future problem the current AEW deployment does not yet have?
7. **Reuse:** can existing Engine/ADR-0011/index/credential primitives satisfy these needs without new subsystems?
8. **Testability:** can each new shared primitive be given deterministic acceptance tests before real-provider dogfood?
9. **Knowledge implementation:** is the proposed split between audited admitted knowledge and operational capture-job state practical and coherent?
10. **Typed surface:** is MCP actually the right first adapter, or should the typed service contract be implemented behind another transport first?

Requested disposition from the developer:

```text
CONCUR
CONCUR WITH MODIFICATION
OBJECT — ALTERNATIVE PROPOSED
NEEDS PROBE
DEFER
```

For any objection, identify which existing invariant/contract, code seam, recovery property, or measured cost makes the proposed disposition wrong.

# 16. Proposed acceptance boundary

If this response is accepted after developer review:

- `REVIEW.md` remains architecture-review evidence.
- This response becomes the authoritative **disposition of the review**, not a replacement Workflow/Knowledge Contract.
- Accepted architecture decisions are copied/promoted into their proper ADR/decision/design artifacts.
- Accepted bounded implementation improvements are added to existing milestone/future-work tracking.
- Deferred feature ideas remain non-governing candidates.
- Explicitly affirmed foundations stay closed unless new evidence reopens them.

The response itself should not become another permanent layer of normative specification. Once its decisions are promoted to their proper homes, it serves as an audit trail explaining how the review was processed.
