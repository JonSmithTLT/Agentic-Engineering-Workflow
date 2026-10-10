# AEW Knowledge Capture ↔ Recall Shared Semantics v0.4

**Date:** 2026-10-04  
**Status:** **Adopted** by the operator, 2026-10-09, as part of the governing M6b knowledge-system direction, together with its two companions and ADR-0013 ([decision record](decisions-2026-10-09-knowledge-system-adoption.md)); it moved from `design/proposals/` that day. Adoption does not authorize K1/K2 production machinery ahead of the evidence-driven sequence (Arm B first; record §7). Until then this line read "Revised cross-path design proposal for joint review; not yet a governing contract or API schema". The text below is unchanged  
**Revision:** v0.4 — incorporates developer review: provenance authentication is separated from semantic validity, disposition vocabulary is qualified, and only the engine-observable portion of the receipt ladder is initially authoritative
**Purpose:** Prevent the M6 knowledge write path and read/delivery path from becoming two independent semantic systems  
**Companion:** `aew-knowledge-capture-admission-design-v0.4.md`

## 1. Problem

AEW needs two directions:

```text
engineering work/evidence
        -> capture/admission
        -> durable reusable knowledge

durable reusable knowledge
        -> recall/selection
        -> context/tool/UI delivery
        -> later engineering work
```

These paths must remain independently operable:

- capture must not require recall providers to be online;
- raw/canonical recall must work even when semantic distillation is disabled;
- admitted knowledge may exist without being eligible for automatic delivery;
- delivery must not mutate admission state merely because an item was retrieved or used.

But they must not evolve into separate interpretations of knowledge.

The shared center is the durable Knowledge record identity/version and its common semantics.

## 2. Naming

This document uses:

- **capture/admission** for the producer/write path;
- **recall/delivery** for the consumer/read path;
- **delivery** to include CLI/MCP lookup results, context routing, API projections, and Journal/debug views where appropriate;
- **Evidence ingestion** only for AEW's existing evidence submission/ingest machinery.

"Import" and "export" may be useful conversational shorthand, but implementation artifacts should prefer the terms above to avoid confusion with file transfer or existing Evidence ingestion.

## 3. Core principle

> **Capture decides what durable advisory knowledge AEW is willing to retain. Recall/delivery decides what retained or canonical material is appropriate to expose for a particular request. They share identity, provenance, applicability vocabulary, and policy semantics, but neither is an alias for the other.**

Corollaries:

1. admitted does not mean automatically served;
2. served does not mean believed, cited, or beneficial;
3. retrieval match does not establish applicability;
4. recall cannot upgrade support or authority;
5. capture cannot predict every future retrieval need;
6. direct canonical-history recall may bypass semantic Knowledge creation entirely;
7. every delivered Knowledge item must remain traceable to the exact record version and root source/evidence.

## 3.1 Qualified disposition vocabulary

This contract avoids using `disposition` as a single cross-domain term:

- `workflow_disposition` — an existing work/review/observation outcome;
- `knowledge_disposition` — admission/hold/reject/supersession/serving-state events for reusable Knowledge;
- evidence admissibility — separate evidence/gate semantics.

Normative fields use qualified names. UI prose may shorten them only where the domain is unambiguous.

## 4. Stable identity domains

### 4.1 Evidence identity

Existing Evidence IDs/hashes remain canonical.

Capture/admission references them.

Recall/delivery expands/navigates them.

Neither path creates a substitute Evidence identity.

### 4.2 Knowledge identity

Every admitted reusable Case/Lesson/reference has:

```text
knowledge_id
version
content_fingerprint
record_kind
created/admitted timestamps
```

Examples in design material may use `R-*` or `K-*`, but the final prefix is not decided here.

A Knowledge ID is stable across projections. A changed semantic claim/applicability is a new version or new record according to the accepted revision rules; it is not an invisible in-place rewrite.

Mutable operational knowledge state is **not** part of the immutable content-version identity. Admission/hold/challenge/serving/supersession changes are append-only `knowledge_disposition` events. Each has a per-record/version `knowledge_disposition_seq` and a global `knowledge_event_seq`; current state is a fold over those events.

### 4.3 Canonical project references

Decision, requirement, contract, source, accepted-procedure, and other project-authoritative identities remain owned by their source domain.

Knowledge records reference them.

Delivery displays them as references, not copied authority.

### 4.4 Subject identity

Where possible, both paths use existing stable identities:

- component/module;
- tool/capability;
- source artifact;
- dependency;
- environment;
- canonical contract/decision;
- work item.

Paths/symbols may be locators when stable identity is unavailable.

Derived topic lenses may group records but do not become publication authority by default.

## 5. Shared durable fields

Capture/admission is responsible for persisting the common fields future recall/delivery relies on.

A conceptual common Knowledge header includes:

```text
knowledge_id
version
record_kind                  # reference | case | lesson | hypothesis/held etc.
authority_class              # advisory/reference semantics, never inferred by UI
origin_binding
subject_refs[]
canonical_refs[]
root_evidence_bindings[]
observed_conditions
declared_applicability
limitations[]
unknowns[]
admission
support
conflict
lifecycle
serving_eligibility
visibility_scope
source_authentication_classes[]
current_knowledge_disposition_ref
producer/admission_receipts
content_fingerprint
created_at
published_at?
reassessed_at?
```

The final schema may split these into subobjects. The semantic ownership is what matters here.

Source/authentication class is part of the serving semantics, not merely provenance decoration. A K1 Case does not gain default-serving standing solely because its fields are syntactically typed.

## 6. RootEvidenceBinding

Knowledge-to-Evidence linkage should support richer claim provenance without changing Evidence identity.

Conceptually:

```text
RootEvidenceBinding:
    evidence_id
    evidence_hash?
    source_snapshot
    artifact_id?
    artifact_revision?
    byte_range?
    line_range?
    excerpt_digest?
    structured_field_path?
    claim_component_ids[]
    relation                # derived_from/supports/challenges etc.
    basis                   # literal outcome/inspection/test/inference
```

Not every source needs every field.

The binding must be sufficient to answer:

> What exact source supports this part of the Knowledge record?

The binding is not itself proof that the semantic claim is correct; it is the claimed support mapping plus source identity.

## 7. Shared state dimensions

Do not collapse these into one "current/trusted" flag.

### 7.1 Admission

Current admission is a projection over append-only `knowledge_disposition` events, for example:

```text
candidate
admitted
held_active
held_dormant
rejected
```

The immutable Knowledge version does not change when this projection changes. Capture owns durable `knowledge_disposition` events; delivery consumes the current fold plus the exact disposition/policy revision governing a delivery.

### 7.2 Support

Support semantics are **orthogonal/compositional**, not one exclusive state. A record may simultaneously have literal observational basis, an assessed interpretation, targeted-test support, and an active challenge. Implementations must preserve those facts rather than overwriting one with another.

Conceptually:

```text
support:
  observed_basis: literal_observation | none
  assessments: [...]
  validation_receipts: [...]
  unresolved_questions: [...]
  challenge_refs: [...]
```

The exact schema is open. Capture/admission updates support facts only through accepted evidence/assessment rules. Recall does not upgrade support because an item was returned or frequently used.

### 7.3 Conflict

```text
none_known
possible
unresolved
disposition_recorded
```

A matcher may discover a possible conflict; an accepted disposition determines the durable semantic state.

### 7.4 Lifecycle

```text
active
superseded_within_scope
archived
quarantined
```

Supersession is scoped.

Older records remain addressable subject to retention/visibility.

### 7.5 Serving eligibility

Examples:

```text
direct_reference
case_recall
default_lesson_eligible
explicit_investigation_only
suppressed
```

Admission policy establishes the durable serving envelope.

For K1 Cases, serving eligibility is also constrained by source/authentication class: engine-observed-contained fields may be default Case-recall eligible under policy; role-attested/untrusted assertions begin explicit-investigation-only unless validated/promoted.

Source/authentication class establishes **provenance and integrity of the observation**, not semantic validity of the engineering proposition. A contained check receipt can prove that a named check returned a named result under pinned conditions without proving that the check was adequate, that the acceptance input was sound, or that the implementation is correct. Default serving must preserve the literal subject/check/conditions and must not upgrade the observation into a broader conclusion.

The router still decides whether an eligible item is relevant enough for a particular request.

### 7.6 Applicability

The durable record stores:

- observed conditions;
- admitted applicability claim;
- exclusions;
- unknowns;
- basis for any generalization.

The **applicability of that record to a current request** is query-time state.

Conceptually:

```text
ApplicabilityAssessment:
    knowledge_id
    version
    work_binding
    environment_binding
    result                  # match | qualified_mismatch | unknown | inapplicable
    reasons[]
    evidence/policy_version
```

This result may be ephemeral or receipted depending on consequence.

It must not silently rewrite the record's admitted applicability.

### 7.7 Visibility composition

A derived Case/Lesson/reference is no more visible than its most restrictive contributing root unless an attributable authorized widening disposition exists.

This applies to:

- publication;
- duplicate/contradiction matching;
- relation discovery;
- reverse Evidence→Knowledge projections;
- topic/group views;
- API/Journal projections;
- recall candidate generation.

Concealed records must not leak through counts, "possible duplicate" hints, similarity scores, reverse-link existence, or provider metadata.

## 8. Shared relation semantics

Initial relations:

### `derived_from`

The target record/source is part of the origin basis.

Does not imply independent confirmation.

### `supports`

Specified source/evidence supports a specified proposition under stated conditions.

Should be claim-scoped where practical.

### `challenges`

Counterevidence or unresolved same-condition conflict exists.

May trigger serving qualification/hold under policy.

### `refines`

New knowledge narrows or more precisely describes predecessor scope/conditions without declaring the predecessor wholly false.

### `supersedes`

An authorized disposition identifies the new record/version as the default replacement within an explicit scope.

Supersession is not derived from recency, popularity, or vector similarity.

### `references`

Points to an external canonical authority/evidence/work identity without copying that authority.

If `contradicts` remains part of accepted AEW vocabulary, reserve it for a confirmed contradiction semantics distinct from the broader unresolved `challenges`.

## 9. Capture-side responsibilities for future delivery

Capture/admission must write enough durable data for recall to work honestly later.

It owns:

- exact Knowledge identity/version;
- record kind;
- root source/evidence binding;
- authority/advisory class;
- observed conditions;
- admitted applicability;
- limitations/unknowns;
- subject identities;
- canonical references;
- support/conflict/lifecycle;
- serving eligibility;
- relation knowledge-dispositions;
- admission receipts;
- producer/extractor identity;
- content fingerprint.

Capture must **not** precompute:

- whether the record applies to every future task;
- a permanent retrieval score;
- model-specific usefulness;
- causal benefit;
- future context budget decisions.

## 10. Recall/delivery-side responsibilities

Recall/delivery owns query-time operations such as:

- exact-ID lookup;
- lexical/structured search;
- relation traversal;
- optional semantic candidate retrieval;
- current work/environment matching;
- ranking;
- budget/truncation;
- automatic-discovery trigger;
- context packet selection;
- expansion;
- delivery receipts.

It must honor capture/admission semantics rather than recreate them.

It may compute:

```text
selection_score
match_reasons[]
applicability_assessment
ranking_provider
index_generation
truncation_reason
selection_policy
```

These are delivery/query semantics, not retroactive truth.

Retrieval/matching should operate over the authorized corpus **before** top-k/limit selection whenever the provider supports it. Where that is impossible, AEW must bounded-overfetch, filter without exposing concealed metadata, and report incomplete authorized coverage rather than pretend the post-filtered top-k is complete.

## 11. QualifiedRecallItem

A recall result should preserve the durable identity plus query-time qualification.

Conceptually:

```text
QualifiedRecallItem:
    knowledge_id
    version
    kind
    concise_content
    subject_refs[]
    canonical_refs[]
    support_summary
    conflict_summary
    lifecycle
    serving_eligibility
    applicability_assessment
    root_evidence_summary
    match_reasons[]
    ranking_metadata
    exact_expansion_ref
    source/index_generation
```

For raw canonical-history recall, the item may point directly to the canonical source instead of a Knowledge record.

The UI/model must be able to distinguish those cases.

## 12. Selection does not imply delivery or use

Keep the conceptual observation ladder:

```text
MATCHED
SELECTED
PREPARED
DELIVERY_ACKNOWLEDGED
CITED_OR_REFERENCED
BENEFIT_EVALUATED
```

These are not interchangeable, and **they do not all have the same owner or evidential strength**.

Initial implementation responsibility is deliberately narrower:

### Engine-observable delivery receipts

AEW may create authoritative runtime receipts for:

```text
MATCHED
SELECTED
PREPARED
DELIVERY_ACKNOWLEDGED
```

when those events are directly observed by the retrieval/router/delivery path.

### Citation/reference observation

`CITED_OR_REFERENCED` becomes an authoritative receipt only when the harness/tool protocol provides a structured, directly observed citation/reference event bound to the delivered item. Parsing free-form model output for IDs or prose references is heuristic telemetry and must not be promoted to a canonical citation receipt.

### Benefit evaluation

`BENEFIT_EVALUATED` belongs to F19/evaluation. It references the relevant delivery/runtime receipts plus independently evaluated task outcomes. It is not emitted merely because a runtime model claimed the memory was helpful.

Examples:

- an item can rank highly but be omitted by budget;
- an item can enter a prepared packet without confirmed delivery;
- delivery does not establish that the model attended to it;
- a structured citation does not establish that it improved the outcome;
- evaluated benefit requires independent evaluation evidence.

W04's context/receipt direction should remain compatible with the ladder, but backend implementation should initially build only the first four engine-observable stages.

## 13. Pinned content identity versus current serving disposition

Every consequential delivery of admitted Knowledge identifies the exact immutable `knowledge_id + version` **and** the current serving/knowledge-disposition state under which delivery was permitted. These are separate identities.

The Knowledge version answers:

> What exact content/provenance was selected?

The serving/knowledge-disposition binding answers:

> Was that pinned version currently eligible to be delivered in this mode, under which policy/revision, and with what holds/qualifications?

A packet may accurately pin `K-17 v1` while a later protective hold makes `K-17 v1` unsafe for a new default delivery. Therefore:

- preparation pins the immutable Knowledge version;
- actual delivery rechecks visibility, protective holds, serving eligibility, and applicable policy/disposition revision;
- the delivery receipt records both the Knowledge version and governing knowledge-disposition/policy revision;
- a historical packet remains reconstructable even if the record later becomes suppressed/superseded;
- a stale prepared packet is never justified merely because its pinned content still exists.

Do not silently mean "latest" unless the request explicitly uses a current-mode query and the response records which concrete version was resolved.

If a record is superseded after a packet was prepared:

- the historical packet/receipt still points to the exact version that was prepared/delivered;
- a not-yet-delivered prepared item must pass the current serving recheck;
- later current-mode lookup may resolve to the successor;
- the old packet is not rewritten;
- debug/UI can show that the pinned version is now superseded or held.

This preserves both reconstruction and current safety.

## 14. Knowledge ↔ Evidence navigation

Ordinary Knowledge → Evidence navigation remains a stable primitive.

The future richer path is additive:

```text
Knowledge record
    -> claim component
    -> RootEvidenceBinding
    -> canonical Evidence ID
    -> artifact/revision/range
```

W05 Evidence inspection can remain the evidence reader.

M6 may add:

- relation reason;
- support role;
- claim component;
- admission receipt;
- counterevidence role.

It should not force W05 to adopt Knowledge ownership.

Evidence → Knowledge reverse navigation may be provided as a backend-supplied index/projection:

```text
E-871
  used_as_support_by -> K-17 v1
  challenged_by      -> K-44 v2
```

This reverse index is derived. Evidence itself does not need to mutate to list every future consumer. Reverse links are visibility-filtered before result limits and must not reveal private Knowledge merely because the underlying Evidence is visible.

## 15. Capture and delivery policy linkage

Both paths should resolve policy from one versioned knowledge-policy domain, even if the policy has separate sections.

Conceptually:

```text
knowledge_policy:
    admission:
        ...
    serving:
        ...
    applicability:
        ...
    relations:
        ...
    budgets:
        ...
```

Capture records the admission policy version.

Delivery records the serving/ranking/applicability policy version and the current disposition/hold revision used for the final delivery decision.

This permits reconstruction without forcing the policies to be identical.

A later policy revision may change serving eligibility or trigger reassessment without rewriting original Evidence.

## 16. Shared precondition model

Both paths recheck the things that matter at the point of action. "Current" means the pinned source/disposition prerequisites still satisfy policy; it does not require the source to be the newest evidence in existence.

### Admission preconditions

Examples:

- the pinned source identity/content is still resolvable and the disposition prerequisites remain valid; an older source is not invalid merely because newer evidence exists;
- candidate sources still resolvable;
- visibility still authorized;
- conflicting-state assumptions still valid;
- relation target version still expected;
- required assessment/validation receipts present.

### Delivery preconditions

Examples:

- record/version still visible to the request scope;
- serving eligibility still allows this delivery mode;
- unresolved protective hold has not appeared;
- index projection is not silently ahead/behind its represented source state;
- current request applicability is not falsely represented as known.

Neither path trusts a cached ALLOW forever.

## 17. Provider boundary

External providers may implement:

- lexical/semantic retrieval;
- embedding/indexing;
- candidate extraction;
- duplicate candidate search;
- relation proposals;
- challenge/evaluation;
- ranking.

But the provider never owns:

- durable Knowledge identity;
- Evidence identity;
- admission;
- authority class;
- final semantic relation knowledge-disposition;
- serving policy;
- workflow state;
- visibility;
- context permission.

Provider-specific scores may be exposed as metadata. They do not become truth.

Capture jobs, candidate outputs, disposition events, and delivery receipts should live in dedicated durable/cold knowledge-history structures and incremental indexes rather than hot workflow control state. Dependency/source reassessment uses reverse indexes, not whole-store scans.

## 18. Topic/subject linkage

Subjects are shared durable anchors.

Topic lenses are initially derived recall/navigation aids.

Capture may propose `proposed_lens_tags`, but durable automatic topic grouping must not become equivalent to semantic admission.

Recall may create dynamic groupings for exploration.

The Journal may show topic/component filters supplied by the backend.

No browser/provider should infer a binding semantic relation merely from similarity.

## 19. Guarded raw-history bypass path

The shared model permits raw history to bypass **semantic Knowledge creation**, but not admission/serving security.

```text
canonical Evidence/history
    -> explicit lookup / investigation mode
    -> guarded qualified raw result
    -> bounded expansion
```

Raw role reports, historical prose, rejected/held candidate sources, and other unadmitted history are **not eligible for automatic/default context delivery** merely because they are searchable.

Default/automatic delivery uses:

- admitted Knowledge records within their current serving envelope; and
- canonical project-authority references resolved from their owning source.

Raw-history access still enforces:

- capability/visibility checks;
- source integrity/identity;
- request-mode authorization;
- bounded results and excerpts;
- untrusted-data presentation/delimiting;
- source `workflow_dispositions` and known knowledge holds;
- no instruction authority.

A request mode such as `INVESTIGATION_HISTORY` or `DEBUG_EVALUATION` is a query intent, not a permission grant.

The absence of a Lesson never implies absence of useful history; explicit authorized investigation can still reach the roots.

This guarded raw-history path is also the **first implementation baseline**. The system should measure it before committing to production K1/K2 machinery. If explicit lexical history recall performs approximately as well as structured Cases on independently verified outcome quality, safety, context efficiency, retrieval precision, and investigation cost, retaining the simpler path is an acceptable and preferred result.

## 20. Telemetry and feedback

Recall/use telemetry is not evidence for the underlying engineering claim.

Safe telemetry examples:

- searched;
- returned;
- expanded;
- selected into packet;
- delivery acknowledged;
- cited;
- ignored;
- task outcome later passed/failed;
- evaluator later judged the item helpful/harmful.

These may inform UX, ranking experiments, or maintenance.

They must not automatically:

- raise evidential support;
- broaden applicability;
- resolve conflict;
- supersede another record;
- convert advisory material into authority.

## 21. Failure behavior

### Capture failure

- does not erase canonical history;
- does not block raw-history recall;
- does not fabricate a replacement Lesson.

### Index failure

- does not destroy durable Knowledge;
- exact expansion remains possible where the durable store is available;
- degraded state is visible.

### Applicability uncertainty

- may yield qualified retrieval;
- must not be rendered as confirmed applicability.

### Conflict discovered after admission

- may suppress default serving through accepted protective policy;
- does not rewrite the original source/evidence;
- does not imply automatic falsity.

### Delivery provider outage

- may reduce automatic/semantic recall;
- must not change admission state.

## 22. API/projection implications

Future read APIs should preserve:

- exact record version;
- authority/advisory class;
- source/evidence references;
- supplied applicability/conflict/lifecycle/serving fields;
- response/index generation;
- unknowns explicitly.

The browser must not infer:

- truth;
- contradiction;
- supersession;
- applicability;
- ranking policy;
- authority;
- missing-event conclusions.

Preview schemas remain proposals until the main-line backend accepts them.

## 23. Journal implications

The Journal should eventually distinguish at least:

### Case

> This happened under these recorded conditions.

### Lesson

> AEW admitted this bounded interpretation/recommendation from specified evidence.

The Journal may project compact human labels such as CURRENT/SUPERSEDED/CHALLENGED, but those labels should be backed by the orthogonal shared dimensions rather than become the source model.

The Journal remains a human-facing projection, not the mutation authority.

## 24. MCP/CLI implications

The agent-facing knowledge capability should make useful operations cheap:

```text
knowledge.search(...)
knowledge.get(id, version?)
knowledge.related(id, relation?)
knowledge.evidence(id)
knowledge.explain_selection(packet_item)
```

Exact operation names are not decided here.

The tool should return qualified, expandable results rather than dumping the entire knowledge store.

A model may explicitly request historical hypotheses or challenged material, but such results must retain their status.

## 25. Invariant requirements for the existing invariant index

Do **not** establish a separate `KS` invariant namespace. Merge/deduplicate these requirements into AEW's existing invariant index together with Capture and Recall:

- Evidence identity is stable across capture and recall;
- Knowledge identity/version is stable across CLI/MCP/API/Journal projections;
- every delivered item identifies exact content version plus governing knowledge-disposition/policy revision;
- admission does not imply serving;
- serving does not mutate admission/support/authority;
- query-time applicability does not rewrite durable applicability;
- retrieval scores do not establish semantic relations;
- multiple derived records do not multiply one root evidential source;
- supersession is scoped and attributable;
- guarded raw-history recall remains possible without semantic distillation but is explicit-mode only for unadmitted prose;
- canonical project references remain references, not copied authority;
- selection/preparation/delivery/citation/benefit remain distinct;
- capture and delivery record policy versions independently;
- visibility is most-restrictive-root by default and enforced before matching/result limits;
- provider outage cannot mutate durable semantics;
- reverse Evidence→Knowledge links are derived and scope-filtered;
- topic lenses/groupings do not establish truth or authority;
- Knowledge text cannot grant execution/workflow authority;
- current-mode resolution records the concrete version returned;
- protective serving hold is not equivalent to declaring content false;
- immutable Knowledge content and append-only knowledge-disposition state remain separate;
- request modes never grant capabilities/visibility;
- consequential post-delivery holds surface affected active/unmerged recipients via delivery receipts.

## 26. Decisions intentionally left open

This shared-semantics proposal does not choose:

- final Knowledge ID prefix;
- physical storage path;
- whether versions are separate files or revision objects;
- final API endpoint shapes;
- recall ranking algorithm;
- lexical/vector provider;
- exact context budget;
- whether some relation metadata is stored as first-class records or embedded knowledge-disposition receipts;
- final UI compact-label vocabulary;
- final service identity capability names.

Those choices must preserve the semantics above.

## 27. Joint review questions

### Capture/admission owners
- Is every field required by future delivery actually persisted?
- Are we accidentally precomputing query-time judgments?
- Can capture run safely without the recall provider?

### Recall/context owners
- Can the router make request-specific applicability/ranking decisions without inventing source semantics?
- Can it explain why an item was selected/suppressed?
- Can it degrade to raw history?

### Evidence owners
- Does richer claim binding preserve current Evidence identity and storage ownership?
- Is reverse Evidence→Knowledge navigation safely derived?

### API/dashboard owners
- Can projections expose the shared dimensions without browser inference?
- Are exact version/source identities sufficient for deep links and debugging?

### Security/authority owners
- Is there any path where retrieved text, provider scores, or repeated use upgrades authority?
- Can scope/visibility leak through matching or reverse links?

### Evaluation owners
- Can experiments independently score write quality, retrieval quality, and downstream use?

## 28. Review set and approval boundary

Review this document together with:

- `aew-knowledge-capture-admission-design-v0.4.md`;
- `aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md`;
- `aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md`;
- current Knowledge Contract v0.4;
- M6 Journal/dashboard handoff;
- W04 context/receipt design;
- W05 Evidence inspection design.

Approval means:

- capture and delivery share these semantics;
- Evidence identity remains stable;
- Case/Lesson/reference distinction is accepted as M6 direction;
- read/write paths are linked by common durable identity/provenance but remain independently operable.

Approval does **not** approve final storage schemas, wire contracts, providers, ranking, automatic K2 rollout, or implementation.
