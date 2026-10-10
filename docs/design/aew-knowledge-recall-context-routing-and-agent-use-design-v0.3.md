# AEW Knowledge Recall, Context Routing, and Agent Use Design v0.3

**Date:** 2026-10-04  
**Revision:** v0.3 — incorporates developer review: Arm B is the first implementation/stop-go gate, source authentication is explicitly non-semantic, receipt implementation stops at engine-observable delivery, and disposition vocabulary is qualified
**Status:** **Adopted** by the operator, 2026-10-09, as part of the governing M6b knowledge-system direction, together with its two companions and ADR-0013 ([decision record](decisions-2026-10-09-knowledge-system-adoption.md)); it moved from `design/proposals/` that day. Adoption does not authorize K1/K2 production machinery ahead of the evidence-driven sequence (Arm B first; record §7). Until then this line read "Design proposal for joint M6 review; not yet a governing contract, API schema, ranking policy, or implementation authorization". The text below is unchanged  
**Target:** M6 knowledge read/delivery path  
**Companions:** `aew-knowledge-capture-admission-design-v0.4.md`, `aew-knowledge-capture-recall-shared-semantics-v0.4.md`  
**Research basis:** `aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md`

## 1. Purpose

AEW's knowledge system needs a consumer path that makes prior engineering experience cheap and useful enough that agents consult it under ordinary operation, without turning historical text into authority or flooding every invocation with memory.

This document owns the read side:

```text
canonical history + admitted Knowledge
        -> query/trigger
        -> guarded candidate retrieval
        -> applicability qualification
        -> ranking
        -> selection/budgeting
        -> preparation
        -> final serving recheck
        -> delivery/expansion
        -> receipts and outcome evaluation
```

It does not define how Knowledge is admitted. That belongs to Capture & Admission. It does not redefine the shared identity/provenance semantics. Those belong to the Shared Semantics companion.

The product objective is not "make agents call a memory tool." It is:

> **Relevant prior experience should be easier for an agent to obtain and trust than rediscovering it, while irrelevant, stale, challenged, or misleading history is easy to ignore or inspect rather than blindly follow.**

## 2. Primary acceptance objective

M6's agent-facing knowledge path is not accepted merely because search returns records.

The explicit acceptance gate is:

> **With the capability ordinarily discoverable and no task-specific instruction to use memory, agents find and appropriately use relevant prior experience, improve independently verified task outcomes, and abstain when history is irrelevant or misleading.**

Evaluate raw history, structured Cases, and Cases-plus-Lessons separately. Evaluate automatic discovery notices in a separate arm; automatic injection or notification is not evidence of voluntary agent preference.

Primary outcome: independently verified accepted-task correctness.

Secondary outcomes include repeated investigation avoided, time/tool steps, tokens/cost, latency, unnecessary edits, authority/freshness mistakes, unprompted lookup/expansion, helpful uptake, inappropriate adherence, and justified abstention.

## 3. Design principles

1. **One owner of delivery semantics.** AEW owns visibility, serving eligibility, applicability qualification, context selection, and delivery receipts. Providers may rank or retrieve candidates but do not decide authority.
2. **Exact first, semantic second.** Resolve exact IDs, typed subjects, canonical references, failure signatures, paths, components, environments, and explicit relations before paying for semantic matching.
3. **Progressive disclosure.** Advertise the capability cheaply, return compact qualified hits, expand exact records/evidence only on demand or when policy explicitly routes them.
4. **Raw history is first-class.** Useful canonical history remains searchable without semantic distillation.
5. **Admission is not serving.** A retained item may be ineligible for default delivery.
6. **Match is not applicability.** Retrieval similarity is only a candidate signal.
7. **Delivery is not use.** Prepared, delivered, cited, and beneficial are distinct events.
8. **Historical text is data.** Retrieved content cannot grant tool, workflow, or publication authority.
9. **Counterevidence travels with consequential advice.** Do not serve a persuasive Lesson while silently hiding a material active challenge.
10. **Abstention is success when appropriate.** No-hit, inapplicable, or uncertain results should remain explicit rather than forcing a memory answer.

## 4. Recall source universe

The recall facade may search multiple source classes while preserving their identity and semantics.

### 4.1 Canonical project authority references

Examples: accepted decisions, contracts, requirements, schemas, accepted procedures, source/API references.

Return these as references to their canonical owner. Do not clone their authority into Knowledge prose.

### 4.2 Canonical engineering history/Evidence

Examples: discovery/research records, attempts, check receipts, implementation reports, reviews, verification, decisions, archived work, and evidence artifacts.

These may be recalled directly through the guarded raw-history path.

### 4.3 Admitted K0/K1/K2/K3 Knowledge

References, Cases, and Lessons are returned according to serving eligibility, visibility, lifecycle/conflict state, and request-specific applicability.

### 4.4 Held/challenged/historical material

May be exposed in explicit investigation/debug modes when authorized. It is not silently mixed into established/default advice.

### 4.5 Derived indexes

FTS, SQLite catalogs, vectors, Qdrant collections, provider indexes, relation caches, and topic lenses are accelerators only. Their loss may degrade search but cannot erase durable history/Knowledge.

## 5. Request binding

Every recall operation has an AEW-owned request binding sufficient to decide scope and qualification.

Conceptually:

```text
RecallRequestBinding:
    project_id
    request_id
    actor/role/invocation?
    work_id?
    attempt/run?
    current_source_snapshot?
    environment_binding?
    visibility_scope
    request_mode
    query_text?
    exact_refs[]?
    subject_refs[]?
    failure_signatures[]?
    relation_constraints[]?
    result_budget
    context_budget
    policy_revision
```

The provider does not self-declare the request's visibility or permissions.

`request_mode` matters, but **request mode is never a permission grant**. Every mode still passes the caller/invocation capability, visibility, source-class, and policy checks. At minimum distinguish:

- `EXPLICIT_LOOKUP` — model/operator intentionally queries prior knowledge;
- `AUTOMATIC_DISCOVERY` — AEW advertises/selects likely relevant IDs or summaries;
- `CONTEXT_ROUTING` — AEW prepares bounded context for an invocation;
- `INVESTIGATION_HISTORY` — explicitly permits challenged/held/historical sources subject to labels/guards;
- `DEBUG_EVALUATION` — exposes additional ranking/provenance metadata for diagnosis.

The final names are open; the semantic separation is not.

## 6. Recall pipeline

The normal read path is staged so expensive or semantic work is used only when needed.

```text
request binding
    ↓
access / visibility guard
    ↓
exact resolution
    ↓
structured / lexical candidate generation
    ↓
optional relation + semantic candidate generation
    ↓
source/version/disposition qualification
    ↓
request-specific applicability assessment
    ↓
ranking
    ↓
selection + context budget
    ↓
PREPARED
    ↓
final delivery recheck
    ↓
DELIVERY_ACKNOWLEDGED
    ↓
optional expansion / citation / outcome evaluation
```

A stage may return no candidates. No stage is required to invent a result.

## 7. Access and visibility guard

Authorization precedes meaningful retrieval exposure.

The recall facade must prevent provider/query behavior from leaking:

- existence of inaccessible Knowledge;
- hidden source titles/paths;
- secret artifact metadata;
- cross-project records;
- cross-attempt data not authorized for the caller;
- provider-side similarity hints about concealed material.

Retrieval should be scoped to the authorized corpus **before provider top-k/result limits** whenever possible. Filtering a global top-k after retrieval can both leak metadata and starve authorized useful results.

Where a provider cannot guarantee scoped search, AEW must use one of:

1. a properly partitioned/scoped index;
2. bounded over-fetch followed by silent authorization filtering, with an explicit `coverage_incomplete` qualification when the authorized top set cannot be established; or
3. refusal of that provider/mode.

Duplicate detection, relation matching, topic/group projections, and reverse Evidence→Knowledge lookups follow the same rule. No "possible match" hint may reveal concealed records.

Visibility is engine-bound and cannot be widened by query text, request mode, retrieved prose, topic grouping, or provider output. Derived Knowledge visibility defaults to the most restrictive root unless an authorized widening disposition exists.

## 8. Guarded raw-history recall

Raw-history recall bypasses **semantic Knowledge creation**, not AEW delivery/security protections.

Raw role reports, historical prose, and rejected/held candidate source text are available only through **explicit authorized lookup/investigation modes**. They are not eligible for automatic/default context delivery.

```text
canonical Evidence/history
    -> explicit guarded exact/structured search
    -> qualified raw-history result
    -> bounded expansion
```

It still enforces:

- caller/invocation capability and visibility;
- source identity/integrity where applicable;
- request mode as query intent, not authority;
- bounded result/context sizes;
- source disposition;
- untrusted-data treatment and explicit delimiting;
- current protective holds/serving exclusions.

Default/automatic context routing uses only:

- admitted Knowledge within its current serving envelope; and
- canonical authority references resolved from their owning source.

This avoids the difficult and unsafe requirement to suppress individual rejected prose ranges from otherwise searchable role reports.

Example:

- explicit investigation may retrieve a historical reviewer hypothesis labeled as role-reported and challenged;
- default context routing must not present that hypothesis as established advice after its semantic candidate was rejected/held.

Raw history is a fallback and research surface, not a policy bypass.

It is also the **first M6b implementation baseline**. The intended initial operation is equivalent to `aew history search` over a derived FTS5 index in the existing `local/history.sqlite` path, with exact expansion back to canonical history/evidence. FTS is rebuildable acceleration only: it adds no authority, no new runtime dependency, and no automatic delivery.

## 9. Exact resolution and structured retrieval

Prefer deterministic, high-signal operations before semantic search.

Examples:

- exact Knowledge ID/version;
- exact Evidence ID;
- canonical decision/requirement ID;
- component/module/tool/dependency/environment subject;
- work/Ticket/Story relation;
- failure signature;
- source path/symbol locator;
- known relation traversal (`derived_from`, `supports`, `challenges`, `refines`, `supersedes`, `references`).

Exact lookup should be the cheapest and most predictable path.

Structured query fields should be exposed to the agent where useful instead of forcing natural-language search for identities AEW already knows.

## 10. Lexical and semantic candidate generation

Native lexical/structured recall is the required baseline.

Semantic/vector retrieval is optional and replaceable. It may improve candidate generation but does not decide:

- applicability;
- contradiction;
- supersession;
- evidential support;
- authority;
- serving eligibility.

Similarity results are candidates for AEW qualification.

Do not merge records or establish semantic relations solely from a cosine/vector threshold.

Provider scores may be retained as diagnostic/ranking metadata with provider/index-generation identity.

## 11. Applicability qualification

The durable record stores observed conditions and admitted applicability. The current request has its own work/environment binding.

Recall computes a request-specific assessment such as:

```text
MATCH
QUALIFIED_MISMATCH
UNKNOWN
INAPPLICABLE
```

with reasons.

Environment/work-binding fields retain provenance such as engine-observed-contained, engine-observed-weak-boundary, role-reported, or unknown. A syntactically present environment value is not automatically trusted.

Likewise, `ENGINE_OBSERVED_CONTAINED` authenticates provenance/integrity of the observation; it does **not** prove oracle adequacy, semantic correctness, or that the tested proposition was the right one. Retrieval must present contained receipts as bounded observations (`check X returned Y under conditions Z`), not as broader conclusions such as `the implementation is correct` unless a separate authoritative rule establishes that meaning.

Examples of useful reasons:

- same component and compatible tool version;
- source/API unchanged across revisions;
- dependency version differs in a materially unknown way;
- prior Case is Windows-only while current work is Rocky 8;
- Lesson explicitly excludes the current configuration;
- environment fields needed to judge applicability are missing.

`UNKNOWN` is not `MATCH` and is not necessarily `INAPPLICABLE`.

A qualified mismatch may still be useful as a diagnostic prior in explicit lookup, but should not be phrased as applicable advice.

## 12. Current serving disposition versus pinned content

Knowledge content/version and current serving eligibility are separate.

A prepared item pins:

```text
knowledge_id + version
```

but actual delivery must recheck the current:

```text
visibility
serving eligibility
protective holds
conflict state
applicable serving policy/disposition revision
```

Example:

```text
PREPARED: K-17 v1
later: protective hold H-9 placed on K-17 v1
DELIVERY: refuse/qualify under H-9
```

The historical prepared packet remains reconstructable, but its existence cannot authorize later delivery.

A successful delivery receipt records both the exact Knowledge version and the governing current `knowledge_disposition_seq`/serving-policy revision. Current serving state is a fold over append-only `knowledge_disposition` events; it does not mutate the immutable Knowledge content version.

If a consequential protective hold appears **after delivery**, AEW cannot retract already supplied context. The delivery-receipt index should surface an attention projection listing active invocations and unmerged work that received the affected `knowledge_id + version`. The Lead then decides whether review, restart, or revalidation is required; AEW does not silently invalidate completed work.

## 13. Ranking

Ranking optimizes likely engineering usefulness under policy. It does not define truth.

Candidate ranking may use bounded features such as:

- exact subject/component match;
- canonical relation distance;
- failure-signature match;
- applicability result;
- support basis;
- active challenge/conflict qualification;
- lifecycle/serving eligibility;
- source revision/environment compatibility;
- lexical score;
- optional semantic score;
- prior explicitly measured usefulness signals.

Ranking must not automatically treat these as truth signals:

- number of previous recalls;
- citation frequency;
- provider/model confidence;
- recency alone;
- number of derived summaries sharing one evidence root;
- a model saying a memory was helpful.

Rare catastrophic-failure knowledge must not disappear merely because it is infrequently used.

## 14. Ranking and policy separation

Prefer a two-step mental model:

```text
eligibility/qualification
        ↓
ranking among eligible candidates
```

Do not ask a ranking model to silently perform authority, visibility, or protective-hold decisions.

A candidate suppressed by policy should not become deliverable because it ranked highly.

A provider may suggest an ordering; AEW produces the final qualified order and reason metadata.

## 15. Counterevidence and challenged knowledge

When a returned Lesson has material counterevidence or active challenge, the agent-facing projection must make that visible within the bounded result.

Possible behavior by mode:

- default context: suppress if policy marks unresolved conflict unsafe for default serving;
- explicit lookup: return the Lesson with a clear challenge qualification and expandable counterevidence;
- investigation mode: permit authorized held/challenged records and side-by-side competing Cases/evidence;
- historical mode: allow authorized superseded material with explicit lifecycle scope.

Do not rank only the most persuasive supportive excerpt while hiding a known material challenge.

## 16. Progressive disclosure

The agent should not need the entire knowledge graph in context to know that useful history exists.

A practical initial disclosure ladder is:

### L0 — capability awareness

A small stable description tells the agent:

- what AEW knowledge contains;
- when lookup can save work;
- how to search by subject/failure/exact ID;
- that results are evidence-qualified advisory history, not authority.

### L1 — compact qualified hit

Return only what is needed to decide whether to inspect:

```text
ID/version
Case vs Lesson vs canonical/raw source
one-line claim/outcome
key conditions
support/conflict qualification
source/authentication class where material
why matched
one useful next expansion
```

### L2 — record detail

Expand applicability, limitations, root evidence summary, relations, counterevidence, admission/serving metadata, and exact canonical references.

### L3 — exact source/evidence

Expand through W05-style Evidence inspection or canonical source readers to exact artifacts/ranges/receipts.

The model can stop at any level.

This is semantic progressive disclosure; exact wire formats and token budgets remain to be measured.

## 17. Agent-facing operations

The final names are open, but the capability should support operations equivalent to:

```text
knowledge.search(...)
knowledge.get(id, version?)
knowledge.related(id, relation?, filters?)
knowledge.evidence(id, claim_component?)
knowledge.explain_selection(packet_item)
```

Useful search inputs include:

- query text;
- subject/component/tool/dependency;
- path/symbol locator;
- failure signature;
- environment constraints;
- record kind;
- support/conflict/lifecycle filters;
- current/historical mode.

Do not expose raw provider databases or require provider-specific query syntax from the agent.

## 18. Ordinary discoverability

The capability must be available without bloating every invocation.

AEW should advertise a small, stable capability description through the normal capability/skill discovery system and expand schemas only when needed.

The description should make the value proposition concrete, e.g. prior failures, diagnostic checks, environment constraints, accepted decision references, and exact evidence expansion.

Avoid instructions like "always search memory before working." That optimizes tool-call count rather than engineering outcome.

If agents rarely use a demonstrably useful tool, investigate:

- capability wording;
- schema complexity;
- latency;
- result size/noise;
- weak subject/failure inputs;
- harness/tool integration;
- poor trust signals;
- excessive expansion cost.

Do not immediately solve low adoption by forcing a lookup.

## 19. Automatic discovery and context routing

Automatic delivery is a separate capability from voluntary lookup.

Useful triggers may include:

- related-work start with strong exact subject/failure match;
- recurrence of a known failure signature;
- a governing canonical decision/reference directly linked to the work;
- a previously failed approach under closely matching conditions;
- context reconstruction after restart when prior relevant work was explicitly pinned.

Automatic discovery should normally begin with compact IDs/qualified summaries, not large invisible memory dumps.

Context routing owns:

- which eligible items enter an invocation;
- ordering;
- total memory/context budget;
- expansion level;
- contrary-evidence inclusion;
- omission/truncation reasons.

The router cannot widen tool permissions or substitute remembered prose for current authority.

## 20. Context packet semantics

A routed packet item should bind at least:

```text
knowledge/source identity
exact version/snapshot
selection policy revision
current serving/knowledge-disposition revision
applicability assessment
selection reasons
support/conflict qualification
expansion reference
```

Packets use the conceptual observation ladder:

```text
MATCHED
SELECTED
PREPARED
DELIVERY_ACKNOWLEDGED
CITED_OR_REFERENCED
BENEFIT_EVALUATED
```

These are not synonyms and are not all runtime Engine receipts.

Initial backend implementation creates authoritative receipts only for the directly observable delivery stages:

```text
MATCHED
SELECTED
PREPARED
DELIVERY_ACKNOWLEDGED
```

`CITED_OR_REFERENCED` is authoritative only when a structured harness/tool event directly binds the citation/reference to the delivered item. Free-form output parsing may produce heuristic telemetry but not a canonical receipt.

`BENEFIT_EVALUATED` is owned by F19/evaluation and must bind independently evaluated task outcomes to the relevant delivery receipts. Runtime self-report is insufficient.

W04's packet/receipt direction should remain compatible with the complete conceptual ladder while initially implementing only the first four engine-observable stages.

## 21. Context budgeting

Recall is **optional context** and may not crowd out mandatory current context.

Allocate in this order:

1. mandatory system/role instructions and capability constraints;
2. current work identity, accepted intent/plan, authority references, guardrails, and required acceptance/gate context;
3. current source/diff/evidence required for the role;
4. only then the remaining recall budget.

Within the recall budget prefer:

- compact high-signal summaries;
- exact IDs with expansion on demand;
- deduplicated evidence roots;
- omission of unrelated historical chatter;
- explicit truncation/omission metadata.

A Lesson is an atomic qualified unit for budgeting purposes: if its applicability caveat, material challenge, or source qualification cannot fit, omit the Lesson or return a compact reference that requires expansion. Do **not** strip the caveat to save tokens.

A larger context window is not permission to dump the store.

Budgeting must not make a partial result look complete or displace mandatory current instructions/constraints.

## 22. Source expansion and W05

Evidence inspection remains the canonical human/debug path for Evidence artifacts.

M6 recall may link:

```text
Knowledge claim component
    -> RootEvidenceBinding
    -> Evidence ID
    -> artifact/revision/range
```

but does not take ownership of Evidence identity.

Agent expansion can use an equivalent backend read surface rather than the browser itself.

A retrieved Case/Lesson should make exact evidence expansion cheap enough that a skeptical agent can verify consequential claims without manually hunting files.

## 23. Security and instruction isolation

Retrieved history is untrusted content.

Required behavior:

- source text cannot override system/role/AEW policy;
- "remember/do this" text is not executable instruction authority;
- code/log/Markdown content is presented as data;
- canonical decisions are resolved from canonical IDs, not reconstructed from memory prose;
- hidden/denied source metadata is not leaked through search;
- semantic providers cannot broaden visibility;
- automatic/default context excludes held/quarantined/unadmitted raw prose according to policy;
- K1 Case serving honors source/authentication class; role-reported or external-untrusted literal content is explicit-investigation-only unless validated/promoted;
- literal untrusted excerpts are bounded and clearly delimited as data;
- prompt/tool injection found in historical artifacts is treated as source content, not agent instruction.

## 24. Failure and degraded modes

### Distiller unavailable

Raw history and already-admitted Cases/Lessons remain recallable.

### Semantic/vector provider unavailable

Fall back to exact/structured/lexical retrieval where possible; surface degraded capability.

### Index stale/unavailable

Do not silently claim complete search. Exact durable-ID expansion should continue where the durable store is accessible.

### Source/evidence missing or corrupt

Qualify/suppress according to policy; never reconstruct missing proof from a derived summary.

### Protective hold appears after preparation

Recheck at delivery and refuse/qualify; do not rely on stale prepared allow.

### Consequential hold appears after delivery

Do not pretend the model can "unsee" it. Use delivery receipts to identify active invocations/unmerged work that received the held version and surface an attention item for Lead disposition.

### No useful result

Return explicit no-hit/insufficient-applicability state. Do not fabricate a Lesson.

## 25. Performance and latency

Agent adoption depends partly on economics and friction.

Measure on the target air-gapped environment:

- exact lookup latency;
- lexical/structured search latency;
- semantic search latency when enabled;
- expansion latency;
- context-router overhead;
- cache/index generation costs;
- token size of L0/L1/L2/L3 outputs;
- provider startup and failure behavior.

Do not invent a universal latency SLA before target measurements.

The important product question is whether lookup is cheaper/faster than avoidable rediscovery on the tasks where history should help.

## 26. Provider boundary

Providers may implement candidate retrieval/ranking behind AEW interfaces.

Examples include native FTS/SQLite, Qdrant/vector retrieval, QMD/Engram-style providers, or future alternatives.

Provider replacement must not change:

- Knowledge/Evidence identity;
- visibility;
- authority class;
- serving eligibility;
- relation truth;
- context permissions;
- packet receipt semantics.

Provider-specific fields remain metadata.

## 27. Evaluation architecture

Separate writer quality from retriever quality from agent behavior.

### 27.1 Diagnostic stages

1. **Oracle useful record supplied** — can the target agent benefit from ideal prior experience?
2. **Actual capture, oracle selection** — did the writer preserve the useful information?
3. **Actual capture + actual retrieval** — can AEW find the right material?
4. **Actual routing/harness + voluntary lookup** — does the agent appropriately use the capability without task-specific prompting?
5. **Full temporal loop** — do repeated write/read generations improve or corrupt later engineering?

### 27.2 Agent-use arms

Phase the evaluation and implementation so the simplest viable system gets a fair chance to win:

```text
PHASE 1a
A  no recall
B  guarded explicit raw canonical-history recall

PRE-BUILD K1 GATE
replay K1 templates over historical incidents and measure source-class/default-serving eligibility

PHASE 1b (only if B leaves a measurable gap and K1 has a plausible safe substrate)
C  K0/K1 structured Case recall

PHASE 2 (only if C earns incremental value)
D  Cases + admitted K2 conditional Lessons
E  D + bounded automatic discovery notices
O  expert-selected prior experience (diagnostic upper comparator)
```

In B/C/D, use ordinary capability discoverability only. Do not tell the model "use memory." B still requires the model to choose the explicit history operation.

The B→C decision is evidence-driven. If B performs approximately as well as C on independently verified correctness, harmful adherence, retrieval precision, context/tokens, repeated investigation, latency/tool steps, and authority/freshness mistakes, **stop at B** and defer production K1/K2 machinery.

E measures routing/automatic discovery and must not be reported as voluntary preference.

Seed the corpus first from real AEW incidents with durable source material, including acceptance-input mutation, malformed-goal handling, containment/verifier escape, stale review/handover issues, and the subagent-explosion incident where applicable. Add held-out cases as new incidents occur. Repeated runs are directional engineering evidence, not claims of statistical certainty.

Include tasks with:

- genuinely useful history;
- no useful history;
- misleading plausible history;
- changed environment/dependencies;
- active challenged knowledge;
- raw history containing rejected advice;
- provider/index outage;
- rare high-impact prior failure.

## 28. Ranking/retrieval metrics

Measure at least:

- relevant candidate recall;
- irrelevant candidate rate;
- correct applicability qualification;
- challenged/counterevidence surfacing;
- exact-source resolvability;
- duplicate result rate;
- serving-policy violation rate;
- hidden-scope leakage rate;
- retrieval latency and token cost;
- no-hit correctness;
- downstream accepted-task correctness;
- repeated investigation avoided;
- inappropriate adherence;
- justified abstention;
- unprompted search/expansion rate under ordinary discoverability.

Do not optimize unprompted lookup in isolation. High voluntary call rate with worse outcomes is failure.

## 29. Harness/model conformance

A capability that works only because one harness hardcodes special behavior is not semantically portable.

Conformance should verify across supported harness/model combinations that:

- the capability is discoverable;
- schema/progressive disclosure works;
- exact IDs survive transport;
- status/qualification labels survive transport;
- denied records are never exposed;
- held records are excluded from default/automatic delivery but can be inspected in an authorized investigation mode with their held/challenged status;
- expansion references resolve;
- packet receipts distinguish matched/selected/prepared/delivery-acknowledged; structured citation is optional/directly observed, and benefit is evaluated by F19;
- historical text cannot become instruction authority.

Model-specific usage differences may justify profile/routing policy, but not different knowledge truth.

## 30. API/dashboard implications

The read API should eventually expose backend-supplied fields sufficient to debug:

- query/request binding;
- exact result identity/version;
- record/source kind;
- support/conflict/lifecycle;
- current serving/knowledge-disposition revision;
- applicability assessment;
- ranking/match reasons;
- index generation;
- selection/omission/truncation reasons;
- exact expansion refs;
- packet/delivery receipts.

The browser does not infer truth, contradiction, supersession, applicability, or causal benefit.

The retrieval debugger and "why is this in context?" views should be projections over these backend semantics.

## 31. Initial implementation sequence

1. Freeze this read-path design together with Capture/Admission v0.4 and Shared Semantics v0.4, including the qualified glossary terms.
2. Build F19-compatible retrieval/agent-use evaluation fixtures before choosing a semantic provider.
3. Implement **Arm B first**: exact ID/source expansion plus guarded explicit-mode `history search` using FTS5 in the existing derived history SQLite path; raw source text is untrusted and remains project-scoped.
4. Run A/B evaluation under ordinary discoverability.
5. Replay proposed K1 templates over historical incidents and measure source-class distribution, default-serving eligibility, and environment-binding quality before authorizing production K1 work.
6. Only if B leaves a measurable gap and the K1 replay shows a plausible safe substrate, implement the smallest K0/K1 arm C needed for comparison.
7. Implement request-specific applicability and current serving/knowledge-disposition recheck for C.
8. Implement progressive disclosure and stable agent-facing query/get operations.
9. Implement authoritative runtime receipts only for `MATCHED`, `SELECTED`, `PREPARED`, and `DELIVERY_ACKNOWLEDGED`, plus context budgets.
10. Compare B versus C. If C does not materially improve independently verified outcomes, safety, context efficiency, retrieval precision, or investigation cost, stop and defer K1/K2.
11. Only if C earns its complexity, add K2 Lessons in shadow/qualified evaluation.
12. Add automatic discovery as a separate E-arm capability after K2 behavior is understood.
13. Evaluate semantic/vector provider benefit versus lexical/structured baseline.
14. Enable broader Lesson serving only where Capture/Admission policy has passed its own held-out gates.
15. Wire Journal/retrieval-debugger/API projections to real backend semantics; structured citation telemetry and F19 benefit evaluation remain separately owned.

## 32. Decisions intentionally left open

This v0.3 does not freeze:

- final ranking formula;
- vector/semantic provider;
- exact L0-L3 token budgets;
- automatic-discovery trigger thresholds;
- latency SLA;
- exact MCP/CLI operation names;
- query-rewrite model use;
- reranker model choice;
- how many counterevidence items fit default context;
- model-specific routing differences;
- final API endpoint shapes.

Those should be resolved by the evaluation harness and implementation probes rather than guesswork.

## 33. Invariant requirements for the existing invariant index

Do **not** create a separate `KR` invariant namespace. Merge/deduplicate these requirements with Capture/Shared in AEW's existing invariant index:

- retrieval never upgrades authority or evidential support;
- visibility/scope are enforced before concealed metadata or provider limits can affect caller-visible results;
- raw-history recall bypasses semantic creation only and is explicit-mode only for unadmitted prose;
- rejected/held semantic advice cannot silently re-enter automatic/default context through raw source prose;
- request modes never grant capability/visibility;
- match/similarity does not establish applicability or semantic relations;
- every delivered admitted item pins exact content version plus governing disposition/policy revision;
- protective holds are rechecked before delivery;
- consequential post-delivery holds surface affected active/unmerged recipients;
- prepared/delivered/cited/beneficial remain distinct;
- no-hit/abstention can be correct;
- material counterevidence/challenge cannot be silently stripped from delivered advice;
- raw canonical-history lookup survives semantic distiller failure;
- provider failure cannot mutate durable Knowledge/authority;
- exact Knowledge/Evidence IDs survive provider/harness boundaries;
- topic/similarity clusters are navigation aids, not authority;
- recall frequency/citation/model-reported helpfulness does not increase truth;
- context budgets/truncation remain explicit and optional memory cannot displace mandatory current context;
- historical text cannot widen tools/permissions/workflow/context authorization;
- automatic discovery and voluntary lookup are measured separately;
- normal agent-use acceptance requires improved independently verified outcomes plus appropriate abstention under ordinary discoverability;
- K1 default serving respects source/authentication class;
- derived visibility defaults to the most restrictive root.

## 34. Joint review questions

### Knowledge/capture reviewers

- Does read-side qualification preserve the exact meaning of Case/Lesson admission?
- Can raw history bypass semantics without laundering rejected advice?
- Are challenged/held states represented honestly?

### Engine/context reviewers

- Is final serving recheck placed at the correct authority boundary?
- Can packet preparation and delivery remain reconstructable after policy/hold changes?
- Does the router have one owner for budgets/selection?

### Agent/harness reviewers

- Is L0 discoverability sufficient without forcing memory calls?
- Can models cheaply move from compact hit to exact evidence?
- Are tool outputs small and stable enough for ordinary use?

### Retrieval/provider reviewers

- Can lexical/structured baseline operate independently of semantic providers?
- Can provider ranking be swapped without changing semantics?
- Are hidden-scope leaks prevented?

### Evidence/API/dashboard reviewers

- Do exact Evidence/Knowledge identities remain navigable?
- Can W04/W05 and Journal/retrieval-debugger projections consume the receipts without inventing semantics?

### Evaluation reviewers

- Do experiments separate writer, retriever, router, and reader failures?
- Is voluntary agent use measured without task-specific prompting?
- Are irrelevant/misleading histories included?

## 35. Approval boundary

Approve this document only as the **retrieval/context-routing/agent-use design direction**.

Approval means:

- guarded raw history, Cases, and Lessons are distinct recall sources;
- request-specific applicability and current serving/`knowledge_disposition` state are read-time concerns;
- progressive disclosure and exact evidence expansion are required product properties;
- automatic discovery and voluntary lookup remain distinct;
- the agent-use acceptance gate is required;
- retrieval/ranking providers remain replaceable accelerators under AEW semantics.

Review this document together with:

- `aew-knowledge-capture-admission-design-v0.4.md`;
- `aew-knowledge-capture-recall-shared-semantics-v0.4.md`;
- `aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md`;
- current Knowledge Contract v0.4;
- W04 context/receipt design;
- W05 Evidence inspection design;
- current M6 Journal/dashboard handoff.

Approval does not approve a ranking model, vector database, context budget, automatic-trigger threshold, final tool/API schema, automatic K2/K3 admission, or production rollout.
