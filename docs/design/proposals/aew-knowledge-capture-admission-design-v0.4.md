# AEW Knowledge Capture & Admission Design v0.4

**Date:** 2026-10-04  
**Status:** Revised design proposal for joint review; not yet a governing contract, ADR, or implementation authorization  
**Revision:** v0.4 — incorporates developer review: authenticated provenance is separated from semantic validity, K1 source-class coverage becomes a pre-build gate, Arm B becomes the first stop/go implementation, receipt ownership is narrowed, and knowledge/workflow disposition terminology is qualified
**Target:** M6 knowledge system  
**Primary research basis:** `aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md`  
**Related current artifacts:** `docs/aew-knowledge-contract-v0.4.md`, M6 dashboard/Journal handoff, W05 Evidence inspection plan, M6 capability work (F12/F13)  
**Terminology note:** This is the **knowledge capture/admission path**. It is intentionally not called "Evidence ingestion", because AEW already ingests role/evidence records through a separate existing path.

## 1. Purpose

AEW already retains durable engineering history and evidence, and M6 is intended to make prior engineering experience useful to later agents through recall, context routing, MCP/query surfaces, and the Knowledge Journal.

The missing producer-side contract is:

> How does AEW decide that something observed during engineering work is safe and useful enough to retain as reusable knowledge?

This design specifies that path.

It does **not** assume that every useful engineering experience should become a generalized lesson, and it does not grant a distiller or memory provider authority to decide project truth.

The central design choice is:

> **Retain evidence-backed engineering cases first. Distill semantic lessons selectively. Keep raw canonical history searchable even when distillation abstains or is disabled.**

## 2. Goals

The capture/admission path must:

1. retain useful engineering experience without converting model impressions into project truth;
2. preserve exact provenance back to existing canonical Evidence and work identities;
3. allow safe automatic retention where semantics are mechanically bounded;
4. permit semantic abstraction only where evaluation and policy justify it;
5. make abstention and "no candidate" successful outcomes;
6. preserve contradictions, refinements, and supersession without rewriting history;
7. avoid multiplying evidential weight when many derived records share one root source;
8. resist memory poisoning and instruction laundering from logs, reports, retrieved text, and provider output;
9. remain provider-neutral and air-gap compatible;
10. degrade to raw-history/case recall if semantic distillation is unavailable or untrustworthy;
11. avoid requiring the operator to curate ordinary low-risk retained experience;
12. remain compatible with the recall/delivery path through the shared semantics defined in the companion document.

## 3. Non-goals

This design does not:

- replace existing Evidence identity, evidence submission, review, verification, or project authority paths;
- make a model summary authoritative;
- require a general knowledge graph platform;
- require vectors, Qdrant, Engram, Claude-Mem, or any other provider;
- permit knowledge text to change permissions, workflow state, completion, accepted plans, decisions, or requirements;
- require a generalized lesson for every Ticket, Story, attempt, or role submission;
- require human approval for every observed case;
- define the final physical storage layout or ID prefix;
- define the final dashboard wire contract;
- make retrieval frequency or agent preference a truth signal;
- require the recall/delivery system to be online for capture to succeed.

## 3.1 Terminology collision guard

AEW already uses the word `disposition` in several domains. This design therefore uses qualified terms in normative fields and schemas:

- **`workflow_disposition`** — an existing work/review/observation outcome such as `known_limit`, `accepted_open`, follow-up, waiver, or closeout decision;
- **`knowledge_disposition`** — admission/hold/reject/supersession/serving-state events for reusable Knowledge;
- **evidence admissibility** — whether Evidence is acceptable for a particular gate or purpose; this is not a Knowledge disposition.

Unqualified `disposition` may appear in explanatory prose, but implementation fields should use the qualified name appropriate to the domain.

## 4. Knowledge layers

### 4.1 Canonical engineering history and evidence

Existing AEW work records, decisions, Evidence, attempts, reviews, verification, receipts, source revisions, and canonical project references remain the root material.

This layer is useful even without any knowledge distillation.

### 4.2 Reusable Case

A **Case** is a compact, bounded representation of an observed engineering situation.

A Case records concrete facts such as:

- problem/signature observed;
- exact relevant conditions;
- action or change that occurred;
- observed outcome;
- source/work/attempt/environment bindings;
- exact Evidence and artifact references;
- known limitations and unknowns.

A Case may **structurally compress** source material only by selecting, normalizing, or grouping approved typed fields. It must not semantically summarize or paraphrase untrusted prose, invent a causal explanation, or generalize beyond the admitted template. Semantic compression belongs in the Conditional Lesson tier.

A safe Case can usually be constructed deterministically from approved source classes and templates.

### 4.3 Conditional Lesson

A **Conditional Lesson** is an explicitly justified interpretation or diagnostic recommendation derived from one or more Cases and/or canonical evidence.

It may say what a future engineer should consider checking, but only with:

- explicit applicability;
- limitations;
- claim-level support;
- counterevidence or unresolved alternatives when material;
- a recorded `knowledge_disposition`.

A Lesson is advisory knowledge. It is not a project decision, requirement, permission, or proof.

### 4.4 Derived recall/index state

FTS, SQLite catalogs, vectors, Qdrant collections, relation indexes, provider databases, embeddings, generated topic lenses, and other accelerators are rebuildable projections.

Losing them may reduce convenience or speed. It must not destroy the durable knowledge or its provenance.

## 5. Evidence identity is unchanged

This redesign does **not** change existing Evidence identity.

A future Case or Lesson gets its own Knowledge identity/version and references existing Evidence IDs/hashes. It does not replace, rename, absorb, or recreate the Evidence identity.

Conceptually:

```text
E-871 --------┐
              ├──> Case K-17
E-875 --------┘        |
                       └──> Lesson K-31
```

The knowledge layer may add richer bindings such as:

```text
lesson claim component 1
    supported_by -> E-871 / artifact A-4 / exact range

lesson claim component 2
    supported_by -> E-875 / typed verification receipt
```

but `E-871` and `E-875` remain the canonical Evidence identities.

Multiple knowledge records derived from the same Evidence do not create multiple independent evidential roots.

## 6. Authority model

### 6.1 Project authority remains with its current owner

Contracts, ADRs, source, API specifications, schemas, accepted procedures, and other project-authoritative material keep their existing authority.

Knowledge should reference them by canonical identity rather than copy them into an alternate authority.

### 6.2 Evidence producers still own their evidence content

Investigators, researchers, implementers, reviewers, and verifiers continue to produce evidence through existing role paths.

Capture/admission consumes that evidence. It does not retroactively change what the producing role submitted.

### 6.3 Knowledge publication is its own bounded authority

AEW may create durable advisory Knowledge records through an explicitly authorized admission operation.

"Canonical Knowledge record" means canonical identity/version **within AEW's advisory knowledge domain**. It does not mean project authority.

### 6.4 Providers have no publication authority

A distiller, challenger, semantic matcher, Engram-like service, Claude-Mem-like service, or other provider may return proposals only.

Provider output cannot directly:

- publish knowledge;
- resolve a contradiction;
- declare supersession;
- broaden visibility;
- change workflow state;
- create binding decisions;
- grant permissions;
- alter project configuration.

AEW re-validates and admits through its own policy and authority path.

## 7. Capture triggers

Capture begins from **committed AEW events or validated durable records**, not from conversational claims that work is "done."

Candidate opportunities include:

| Event/opportunity | Capture behavior |
|---|---|
| Typed decision/requirement accepted | Project a canonical reference; no semantic rewrite needed |
| Evidence/test receipt committed | Record structural identity/signature/environment for later bundling |
| Investigator/researcher submission | Permit bounded nomination after source validation |
| Failed/recovered attempt | Capture concrete failure/attempt/outcome case when sufficient evidence exists |
| Review/verification disposition | Add support/counterevidence and reassess affected held candidates |
| Ticket closeout | One bounded consolidation opportunity; no mandatory lesson |
| Story closeout | Evaluate bounded cross-case pattern opportunities |
| Dependency/supersession change | Selective reassessment of affected knowledge |
| Archival | Ensure pinned capture work is not lost; archival is not the primary capture trigger |
| Crash/recovery | Recover capture jobs after AEW recovery; crash is not evidence of a lesson |

Several related events may be debounced into one bounded evidence bundle.

**`NO_CANDIDATE` is a successful capture outcome.**

Candidate caps are maximums, never quotas.

## 8. Capture job lifecycle

Capture work is asynchronous to ordinary engineering completion.

A distiller outage, delayed challenger, or recall provider failure must not block a Ticket from completing when existing workflow gates are satisfied.

A capture job has a **job-processing status** that is separate from the `knowledge_disposition` of each candidate produced by that job. One evidence bundle may legitimately yield two admitted Cases, one held Lesson, one rejected candidate, and one assessment that must retry. The whole job therefore cannot be represented by a single `ADMITTED | HELD | REJECTED` value.

A minimal job-processing lifecycle is:

```text
PENDING
  -> BUNDLE_READY
  -> GENERATING
  -> EVALUATING
  -> COMPLETE | PARTIAL | RETRYABLE_FAILURE | PERMANENT_FAILURE
```

Each candidate produced by the job receives its own `knowledge_disposition`, for example:

```text
PROPOSED
  -> ADMITTED | HELD | REJECTED | SUPERSEDED_PROPOSAL
```

Source/integrity conditions may additionally record:

```text
SOURCE_UNAVAILABLE
INTEGRITY_FAILURE
```

Job-processing state and candidate `knowledge_disposition` records are capture-domain records, not project/workflow truth. `COMPLETE` means the bounded job finished processing; it does not mean every candidate was admitted. `PARTIAL` means some candidate work reached a durable disposition while other candidate work remains retryable or otherwise incomplete.

Requirements:

- job identity binds the exact committed event/work/attempt/source;
- retries are idempotent;
- duplicate capture of the same event returns the prior receipt;
- accepted provider output is persisted; a retry does not silently regenerate a different answer and pretend it is the same proposal;
- extractor/model/prompt/policy revisions are recorded;
- source changes before publication cause recheck/reassessment rather than stale publication;
- capture lag is visible.

## 9. EvidenceEnvelope

AEW constructs the evidence input. The model does not self-declare its source identity.

A conceptual `EvidenceEnvelope` contains:

```text
job_id
project_id
origin_event_ref
work_id
attempt_id?
invocation_id?
run_id?
source_snapshot
source_hashes[]
source_types[]
evidence_refs[]
artifact_refs[]
typed_receipts[]
environment_binding
current_relevant_authority_refs[]
visibility_scope
source_authentication_classes[]
derived_visibility_rule
collection_policy_version
truncation_flags
missing_source_flags
```

Each source excerpt or structured field retains an exact binding sufficient to re-resolve the source where authorized.

The envelope is:

- bounded;
- pinned;
- authorized;
- attributable;
- replayable as input;
- treated as untrusted content where it contains model/user/tool prose.

The envelope is not a permission grant. Its `environment_binding` and other applicability-critical fields retain their provenance (`engine_observed_contained`, weaker engine boundary, role-reported, or unknown); presence alone is not evidence quality. Source authentication proves provenance/integrity of the recorded observation, **not** that the observation answers the right engineering question, that the oracle is adequate, or that the resulting conclusion is semantically valid.

## 10. Safe deterministic Case projection

K1 Cases use approved templates and literal/normalized source fields. **Typed does not mean trustworthy.** A role or model can fabricate syntactically valid structured data, and a log string can contain hostile instructions while still being an authentic log string.

AEW therefore records the **source class and authentication boundary** for every K1 field. Initial classes are conceptual and may map to existing provenance vocabulary:

- `ENGINE_OBSERVED_CONTAINED` — AEW directly observed/bound the receipt or execution result and the producing worker could not forge the receipt/store under the established containment boundary;
- `ENGINE_OBSERVED_WEAK_BOUNDARY` — AEW produced/bound the receipt, but current containment does not yet justify treating the worker as unable to forge or tamper with the relevant path;
- `ROLE_ATTESTED` — a bounded role submitted structured fields describing what it observed/did;
- `EXTERNAL_UNTRUSTED` — arbitrary tool/log/source/external-document prose or data whose content is not authenticated as an engineering fact.

These classes authenticate **where an observation came from and how strongly AEW can trust its integrity**. They do **not** authenticate its meaning. An `ENGINE_OBSERVED_CONTAINED` check receipt can faithfully prove that check X returned PASS against revision/environment Y while still failing to establish the intended engineering proposition because the acceptance input was mutable, the oracle was inadequate, the wrong subject was tested, or the test simply did not cover the relevant failure. T4-style failure remains possible even with perfect receipt provenance.

"Engine-observed" is only as strong as the containment and credential boundary that establishes it. Before M4-B/F2-style containment is accepted for the relevant path, AEW must represent the weaker guarantee rather than claim worker-proof authentication. Knowledge-admission service credentials and durable-store mutation credentials must be unreachable from worker shells.

K1 templates declare:

```text
allowed source classes
allowed source fields
what each field literally establishes
what the field explicitly does NOT establish where ambiguity is material
required provenance/authentication level
default serving envelope
maximum literal excerpt size
```

A K1 Case may contain:

- observed condition;
- exact action/change;
- exact result;
- exact environment facts and how each was established;
- exact source/work revision;
- exact Evidence and artifact references;
- event ordering;
- source `workflow_disposition` where relevant;
- known missing/unknown fields;
- explicit negative observations.

It must not infer:

- root cause;
- human/model intent;
- universal behavior;
- a recommended fix;
- applicability outside recorded conditions;
- a future expected result;
- authority not present in the source;
- that a closed observation was disproven, harmless, or permanently accepted merely because work proceeded.

Example safe K1 Case:

> Attempt A, revision X: with environment fields E1/E2 and compilation database H1, the recorded reference query returned zero results. After regeneration produced H2, the recorded query returned N results. Evidence: E-871/E-875. Source `workflow_disposition`: the earlier removal observation was later closed as `accepted_open`.

The Case does **not** add the conclusion that the first result failed to establish absence of callers; that is an evidential interpretation and belongs in a policy explanation, assessment, or K2 claim.

Serving follows source class, but **default eligibility is not semantic settlement**. Even the strongest source class is served as a bounded observation with its subject, oracle/check identity, conditions, and limitations; it must not be rendered as "the implementation is correct" or equivalent unless an independent authoritative rule actually establishes that proposition.

- K1 Cases composed entirely from policy-approved `ENGINE_OBSERVED_CONTAINED` fields may be eligible for default Case recall;
- `ENGINE_OBSERVED_WEAK_BOUNDARY` requires an explicit policy decision for default serving and otherwise begins `explicit_investigation_only`;
- Cases containing `ROLE_ATTESTED` or `EXTERNAL_UNTRUSTED` assertions begin `explicit_investigation_only` unless later validation/disposition promotes their serving envelope;
- literal excerpts from untrusted content are bounded and delivered as clearly delimited data, never as instruction text.

A mixed-source Case inherits the most restrictive relevant serving/source treatment unless an attributable authorized knowledge-visibility decision widens it.

## 11. CandidateKnowledge contract

A semantic distiller may propose `CandidateKnowledge`.

Conceptual fields:

```text
candidate_id
proposed_kind
concise_claim
claim_components[]
future_use_question
proposed_diagnostic_action?
subject_refs[]
proposed_lens_tags[]
observed_conditions
proposed_applicability
exclusions[]
unknowns[]
support_bindings[]
counterevidence_refs[]
unresolved_alternatives[]
evidence_basis
proposed_causal_strength
proposed_relations[]
producer_model
producer_provider
prompt_hash
extraction_version
input_snapshot
origin_binding
visibility_proposal
content_fingerprint
```

Rules:

- a model may abstain;
- unknown is not a wildcard;
- every claim component must identify its basis;
- model confidence is not evidential support;
- proposed actions are advisory text, not executable permission;
- proposed subject/topic grouping is not authoritative;
- provider output cannot self-expand visibility or scope;
- provider-supplied `proposed_kind`, `proposed_causal_strength`, and `proposed_applicability` are proposals only;
- AEW assigns the admission class and required ceremony from deterministic template/policy matching. A producer cannot classify its own output into K1 or choose a weaker path.

## 12. Admission classes

### K0 — Canonical Reference

A pointer to an existing decision, requirement, Evidence item, accepted procedure, contract, or other canonical source.

Automatic admission is permitted when constructed from typed committed identities.

Requirements:

- exact canonical ID/hash/scope;
- no copied parallel authority;
- no semantic rewriting required.

### K1 — Observed Case

A narrow structured problem/action/outcome record with exact evidence.

Automatic admission is permitted only when AEW itself matches the input to an approved deterministic template and its source-class requirements.

Requirements:

- literal source fields;
- exact provenance;
- completeness/scope checks;
- no invented cause, generalization, or advice.

### K2 — Assessed Conditional Lesson

A semantic interpretation or bounded diagnostic heuristic.

Automatic admission/default serving is **disabled initially**.

It may later be enabled for specific policy classes only after held-out evaluation demonstrates acceptable write quality and downstream behavior.

Requirements include:

- claim-level grounding;
- applicability and exclusions;
- focused challenge where policy requires it;
- counterevidence handling;
- conflict hold;
- admission receipt;
- source-precondition recheck;
- sampled audit/disable path.

### K3 — Broad or High-Impact Knowledge

Includes broad procedures, cross-project generalizations, security-sensitive advice, authority-sensitive claims, and unresolved conflict resolution.

M6 v1 does **not** automatically admit K3 knowledge.

A K3 proposal may be retained in a pending/held state, but admission requires an explicit existing Lead/operator-authorized judgment path plus appropriate targeted validation. K3 has no default decision. The dashboard candidate inbox remains read-only until a separate mutation/control design is accepted.

### KH — Held/Rejected/Quarantined

Hypotheses, unsupported candidates, conflicts, poisoned inputs, rejected generalizations, and other material not eligible for default established-lesson delivery.

These may remain inspectable/searchable under controlled investigation modes without being served as established knowledge.

`HELD` is not a permanent active-review queue. Policy may age an unresolved candidate from `HELD_ACTIVE` to `HELD_DORMANT` with an attributable receipt and optional backlog/attention tripwire. Age alone never means `REJECTED`; rejection requires an attributable semantic/policy disposition. A dormant held item can be reopened when new evidence or an authorized reviewer makes it relevant.

## 13. Deterministic validation

Before semantic admission, AEW validates at least:

- schema;
- source identities;
- source hashes;
- visibility/scope;
- origin/work/attempt binding;
- evidence resolvability;
- required fields for the tier;
- candidate size/budget;
- permitted relation types;
- no authority-changing fields;
- no forbidden instruction/configuration mutation;
- source/current-policy preconditions;
- AEW-owned admission-class assignment from approved templates/policy;
- source-class requirements and permitted evidential meaning;
- derived visibility no broader than the most restrictive root unless an authorized widening exists.

A structurally valid candidate is not necessarily semantically justified. Semantic matching/duplicate analysis is performed only within the caller/service identity's authorized visibility scope; concealed records cannot leak through duplicate hints.

## 14. Duplicate and relation handling

Perform exact comparisons **within the authorized comparison scope** first:

1. same origin/event/content fingerprint;
2. same canonical source reference;
3. same structured Case fields and conditions;
4. then bounded same-subject search;
5. semantic matching only as a proposal mechanism.

A matcher may suggest records to compare. It does **not** establish semantic relations by similarity threshold. Matching must be scope-filtered before concealed result metadata is exposed; "possible duplicate" or "possible contradiction" hints must not reveal a record the caller/service identity cannot see.

Initial semantic relation vocabulary:

- `derived_from` — origin/extraction basis;
- `supports` — specified evidence supports a proposition under stated conditions;
- `challenges` — counterevidence or unresolved same-condition conflict;
- `refines` — more precise conditions/explanation without declaring the predecessor wholly false;
- `supersedes` — authorized replacement for default use within explicit scope;
- existing canonical `references` — pointer to decisions/requirements/evidence/etc.

If AEW already retains `contradicts`, keep it with a stricter confirmed-conflict meaning rather than introducing overlapping synonyms.

Rules:

- exact replay does not republish;
- paraphrase with the same claim/conditions/evidence does not create another default-serving copy;
- new independent evidence may increase support without erasing distinct roots;
- same claim under different conditions may remain separate;
- semantic conflict may cause a protective serving hold;
- supersession is a `knowledge_disposition`, not a timestamp rule;
- old versions remain historically addressable.

## 15. Anti-laundering and evidential roots

AEW must preserve root evidence identity.

A model report proves only that the model reported the statement.

A quoted document proves that the document contains the assertion.

A test receipt proves only the tested property under its recorded conditions.

Derived repetition is not independent support.

Example:

```text
E-12 -> Lesson K-1
K-1 -> closeout summary A
K-1 -> closeout summary B
K-1 -> review note C
```

This is still one original evidential root unless A/B/C introduce genuinely new independent evidence.

Knowledge support metrics and challenge logic must deduplicate evidential roots.

A `workflow_disposition` is also not proof of the underlying engineering proposition. Labels such as `known_limit`, `accepted_open`, `waived`, or equivalent mean AEW decided how to proceed with the work; they do not establish that the observation was disproven, harmless, universal, or permanently acceptable. Captured knowledge carries the source observation's `workflow_disposition` and serving must preserve that distinction.

## 16. Applicability and generalization

Start with observed conditions.

Unknown values remain unknown.

A broader applicability claim requires a recorded basis such as:

- distinct additional Cases;
- controlled tests;
- inspected source/API contract;
- an authorized reviewed argument.

Do not infer:

- a version range from endpoint observations;
- platform portability from one distro;
- unchanged semantics from matching version labels alone;
- universality from missing applicability fields.

Distinguish:

- descriptive Case;
- plausible diagnostic heuristic;
- mechanism-supported finding;
- validated procedure.

Broadened claims become new proposals/versions. Limitations are not silently removed from an existing Lesson.

## 17. Semantic challenge

A challenger/evaluator is selective, not mandatory for every capture.

The evaluator should answer focused questions such as:

- Which claim components are unsupported?
- What conditions are missing?
- Is causal language stronger than the evidence?
- Is there material counterevidence?
- Are alternate explanations unresolved?
- What evidence would discriminate them?
- Does the proposed applicability exceed the observed basis?

`INSUFFICIENT_EVIDENCE` is valid.

A second model is not independent proof merely because it agrees.

When practical, challenge with source/evidence without the original author's persuasive narrative.

Targeted tests, reproductions, or additional inspections use the ordinary authorized engineering workflow. Candidate text cannot grant the evaluator permission to execute commands.

## 18. Admission operation

Conceptually:

```text
AdmissionPolicy.decide(candidate, structural_report, assessment?, current_binding)
    -> Disposition
```

The commit operation then performs a final atomic recheck:

```text
KnowledgeStore.commit(knowledge_disposition, expected_source_versions, expected_policy_version)
    -> DurableReceipt
```

The final recheck covers:

- the pinned source identity/content and the disposition prerequisites remain valid; **"valid" does not mean "latest"** — newer evidence may coexist and does not automatically invalidate an older observation;
- visibility remains permitted;
- conflict/supersession preconditions;
- policy version;
- required assessment/validation receipts;
- target record version for refine/supersede;
- authority of the actor/service identity.

Expensive generation and challenge happen outside control-state locks.

Knowledge content versions are immutable once admitted. Admission, hold, challenge, serving, supersession, and reassessment changes are recorded as **append-only disposition events**, not by rewriting the Knowledge version. Current operational state is a fold over those events.

Each `knowledge_disposition` event has both:

- a per-record/version `knowledge_disposition_seq` for optimistic concurrency/current-state checks; and
- a global monotonic `knowledge_event_seq` for incremental projections, Journal/API cursors, cache/index invalidation, and recovery.

Capture jobs, candidate outputs, admission receipts, and `knowledge_disposition` events live in the knowledge/history domain, not hot workflow control state. Dependency/source changes trigger **indexed affected-record lookup** through subject/dependency/source reverse indexes; they must not require a full knowledge-store scan.

## 19. Service identity and automation

AEW may authorize a service identity to perform specifically enumerated knowledge operations.

It must not receive Lead credentials, and its capture/admission credentials must be unreachable from worker shells and worker-visible environment/filesystem state.

Possible bounded capabilities include:

- create capture job;
- publish K0 reference;
- publish approved-template K1 Case;
- place candidate in HOLD;
- request reassessment;
- write capture receipt.

K2/K3 operations are policy-specific and require their defined authority path.

No new ambient authority is implied by running in the background.

### Judgment boundary / Two Surfaces

K2/K3 admission is judgment-bearing. It must appear in AEW's decisions-required/action projection with no silent default.

- K0/K1 operations may be policy-resolved when their exact deterministic prerequisites are satisfied.
- K2 may become policy-resolved only for explicitly evaluated/approved classes; otherwise it requires attributable disposition.
- K3 always requires attributable Lead/operator-authorized disposition in M6 v1.
- A timeout, provider confidence score, or absence of operator response never means "admit."

## 20. Trust/lifecycle dimensions

Do not overload one `CURRENT` or `CONFIDENCE` field.

Durable Knowledge should support orthogonal dimensions such as:

### Admission
Current admission is a projection over append-only `knowledge_disposition` events, e.g. `candidate | admitted | rejected | held_active | held_dormant`. The immutable Knowledge content version is separate from this current `knowledge_disposition`.

### Support
Support is **compositional**, not one mutually exclusive enum. A Lesson can simultaneously have targeted-test support and be challenged by counterevidence. Represent support as typed assertions/facets or another structure that preserves simultaneous facts, for example:

```text
observed_basis: literal_observation
assessments: [assessed_interpretation]
validation: [targeted_test_support]
challenge_state: challenged
```

The final schema is open, but updating one support fact must not discard another.

### Conflict
`none_known | possible | unresolved | disposition_recorded`

### Lifecycle
`active | superseded_within_scope | archived | quarantined`

### Serving eligibility
`direct_reference | case_recall | default_lesson_eligible | explicit_investigation_only | suppressed`

### Applicability
The record stores its **declared/observed applicability basis**.

Whether that knowledge applies to a particular current request is computed at query/delivery time against the current work/environment binding and should be receipted where consequential.

An admitted Lesson may be challenged.

A historically valid Case may be inapplicable to the current tool version.

Fresh index generation does not make the knowledge true.

## 21. Capture/delivery coupling

Capture/admission and recall/delivery are distinct paths but must not become separate semantic systems.

They share the canonical Knowledge record identity/version and the fields defined by the companion shared-semantics document.

Capture must persist enough identity/provenance/applicability information that future delivery can:

- identify the exact admitted version;
- resolve root Evidence/canonical sources;
- qualify applicability;
- honor conflict/lifecycle/serving state;
- explain why the item was eligible or suppressed.

Admission does **not** imply default serving.

Derived visibility is no broader than the most restrictive contributing root unless an explicit authorized knowledge-visibility widening record exists.

Serving does **not** mutate admission.

Raw canonical-history recall remains valid without semantic Knowledge admission.

## 22. Security and poisoning

Treat all candidate source prose as untrusted data, including:

- model reports;
- tool output;
- test logs;
- source comments;
- external research text;
- historical recalled knowledge;
- user-provided documentation.

Required protections:

- instructions in source text cannot mutate role/tool permissions;
- candidate text cannot define its own authority;
- typed receipts outrank prose descriptions of receipts;
- visibility cannot be widened by the distiller; derived records inherit the most restrictive root visibility unless an authorized widening is recorded;
- canonical decisions must be resolved by ID, not reconstructed from prose;
- malicious "remember this" instructions are not privileged;
- provider output is schema-constrained and validated;
- historical knowledge remains data, not instruction authority;
- high-impact security advice cannot enter ordinary K1 automation.

## 23. Failure and recovery

Distiller failure must not block AEW engineering recovery.

Required behaviors:

- capture jobs are replayable from pinned sources;
- provider outage leaves raw/case recall available;
- acknowledgement is idempotent;
- crash after provider output but before AEW commit does not duplicate publication;
- missing/corrupt source evidence yields explicit integrity failure/hold;
- a new extractor version creates a new proposal/reassessment rather than rewriting prior generated output;
- capture queue loss is not allowed to erase an acknowledged admitted record;
- failed semantic distillation does not delete source Evidence.

## 24. Evaluation gates

Build the adversarial corpus before enabling automatic semantic Lesson admission.

Minimum evaluation dimensions:

- candidate precision;
- candidate recall;
- admission precision;
- unsupported-claim rate;
- over-generalization rate;
- duplicate serving rate;
- correct applicability decisions;
- contradiction handling;
- provenance resolvability;
- authority confusion;
- capture lag/loss/replay;
- operator burden;
- cost per useful admitted item;
- downstream accepted-task correctness;
- repeated investigation avoided;
- inappropriate adherence to stale/misleading knowledge.

Evaluate diagnostic stages separately, but phase the initial product experiment to fit the team:

**Phase 1a:** establish A/B first — no recall versus guarded explicit raw-history recall. Arm B is the first implementation and the first stop/go gate.  
**Phase 1b:** only after B is measured, use the K1 history replay plus a minimal/prototype Case arm C to test whether structured Cases materially improve correctness, safety, context efficiency, retrieval precision, or investigation cost.  
**Phase 2:** add K2 Lessons and automatic-discovery arms only if K1/C itself demonstrates incremental value.

The broader diagnostic decomposition remains:

1. oracle useful knowledge supplied;
2. actual writer + oracle selection;
3. actual writer + retrieval;
4. actual router/harness + voluntary lookup;
5. full temporal write/read loop across generations.

Before implementing K1 broadly, replay candidate K1 templates over existing M1–M3 history and representative incidents (for example acceptance-input mutation, malformed-goal handling, containment/verifier escape, stale handover/review failures, and the subagent-explosion incident where source material is available).

The replay must report at least:

```text
useful candidate observations by source class:
    ENGINE_OBSERVED_CONTAINED
    ENGINE_OBSERVED_WEAK_BOUNDARY
    ROLE_ATTESTED
    EXTERNAL_UNTRUSTED
    UNKNOWN

serving envelope:
    default-eligible
    explicit-investigation-only
    held/unusable

applicability-critical environment binding:
    engine-observed-contained
    engine-observed-weak-boundary
    role-reported
    unknown
```

This measurement is a **pre-build gate**, not merely telemetry. Because much current AEW development occurs under weaker Windows/workdir-separation guarantees, do not assume the practical corpus will contain enough default-eligible K1 material to justify a large Case subsystem. If the safe/default-eligible share is small, the design must either show that explicit-investigation Cases still add measurable value or defer K1 investment.

A system that publishes nothing can fake precision. A system that publishes everything can fake recall. Report both misses and bad admissions.

Critical authority, poisoning, or cross-scope failures are stop conditions.

### Agent-use acceptance gate

The knowledge capability is not accepted merely because records can be written and retrieved. Before treating the normal agent-facing path as successful, demonstrate:

> **With the capability ordinarily discoverable and no task-specific instruction to use memory, agents find and appropriately use relevant prior experience, improve independently verified task outcomes, and abstain when history is irrelevant or misleading.**

Test in phases:

1. **A — no memory**;
2. **B — guarded explicit raw canonical-history recall**;
3. evaluate B and the K1 source-class replay before authorizing production K1 machinery;
4. **C — K0/K1 structured Case recall**, initially as the smallest implementation/prototype sufficient for comparison;
5. only if C materially outperforms B on independently verified outcome quality, safety/misuse, context efficiency, retrieval precision, or investigation cost, proceed to admitted K2 Lessons;
6. automatic discovery remains a separate later arm and is never evidence of voluntary lookup.

If B performs approximately as well as C on the dimensions that matter, **stop**: retain B as the simple baseline and defer the K1/K2 machinery rather than building it because the design exists.

Measure independently verified task correctness first. Also record unprompted search/expansion, appropriate abstention, inappropriate adherence, repeated investigation, tool steps, latency, tokens/cost, and authority/freshness mistakes. A store agents rarely consult under ordinary discoverability has failed an important product objective even if its internal records are correct.

## 25. Initial M6 implementation sequence

1. Freeze reference/Case/Lesson semantics and authority boundaries, including the glossary-qualified names (`workflow_disposition`, `knowledge_disposition`, evidence admissibility).
2. Freeze the shared capture/recall semantics companion contract.
3. Build the F19-compatible adversarial evaluation fixtures.
4. Implement **Arm B first**: guarded explicit canonical-history search and exact expansion over a derived FTS5 index in the existing history SQLite path; raw history remains untrusted data and this adds no new authority.
5. Measure A versus B under ordinary discoverability.
6. Replay proposed K1 templates over M1–M3 history and report source-class/default-serving eligibility before freezing templates.
7. Only if B leaves a measurable gap and the replay shows a plausible safe Case substrate, implement the smallest K0/K1 arm C needed for comparison.
8. Compare B versus C. If C does not materially improve independently verified outcomes, safety, context efficiency, retrieval precision, or investigation cost, defer production K1/K2.
9. Only after C earns its complexity, implement full K1 projection/idempotency/receipts and run semantic Candidate generation in shadow mode.
10. Add duplicate/relation proposal and focused challenge.
11. Enable selected K2 policy classes only after held-out gates and demonstrated incremental value beyond B/C.
12. Add context-router/default-serving policy and measure automatic discovery separately from voluntary lookup.
13. Evaluate external providers only behind these interfaces.
14. Extend Journal/API projections to actual capture/admission/evolution receipts.

## 26. Required M6 design changes

Compared with the prior direction:

- Capture/admission becomes a first-class M6 deliverable.
- Structured Cases become the safest reusable knowledge primitive.
- Semantic Lessons are an evaluated higher-order layer, not the default retained form.
- Raw canonical-history search is a permanent baseline/fallback.
- Initial runtime delivery receipts stop at engine-observable `MATCHED → SELECTED → PREPARED → DELIVERY_ACKNOWLEDGED`; citation is canonical only when directly observed through a structured mechanism, and benefit evaluation belongs to F19.
- Retention, admission, serving eligibility, and automatic delivery are separate.
- Claim-level support and root-evidence deduplication are required.
- Applicability is explicit and request-specific matching is query-time.
- Model semantic relations are proposals until admitted or given an attributable `knowledge_disposition`.
- The Journal must distinguish Case from Lesson semantics.
- Candidate/distiller UI remains inspection-only until this mutation path is accepted.
- External memory providers cannot bypass AEW admission.

## 27. Review questions

### Knowledge/research reviewer
- Are Case/Lesson semantics sufficiently separated?
- Can the system abstain without losing useful history?
- Does generalization require enough basis?
- Does the evaluation isolate writer, retriever, and reader failures?

### Engine/workflow reviewer
- Is the capture job lifecycle compatible with AEW durability/recovery?
- Are all mutations routed through existing authority/guard patterns?
- Does capture remain non-blocking to ordinary completion?
- Are publication preconditions atomically rechecked?

### Evidence/provenance reviewer
- Are existing Evidence identities preserved?
- Can every admitted claim resolve its support roots?
- Can derived repetition accidentally inflate support?

### Security reviewer
- Can untrusted prose inject instructions or widen authority?
- Can visibility/scope leak during matching/challenge?
- Are K2/K3 boundaries strong enough?

### API/dashboard reviewer
- Can the future API project Case/Lesson/admission/evidence bindings without changing Evidence ownership?
- Are states supplied rather than inferred by the browser?
- Are versioned identities sufficient for pinned navigation?

### Capability/provider reviewer
- Can external providers be replaced without changing AEW semantics?
- Are provider outputs proposals only?
- Does provider outage degrade cleanly?

## 28. Invariant requirements for the existing invariant index

Do **not** create a separate `KINV` namespace. Consolidate these requirements into AEW's existing invariant index, deduplicating overlap with Shared/Recall requirements:

- provider output cannot create binding decisions, completion, requirements, permissions, or recovery state;
- every admitted claim resolves to permitted pinned source evidence or an explicit assessed-interpretation basis;
- origin/visibility claims state their actual containment/authentication level;
- model prose is not an execution/test receipt;
- derived repetition cannot increase independent evidential support;
- generalization or visibility widening requires a recorded authorized basis;
- supersession never silently deletes prior understanding or follows recency alone;
- default delivery excludes held/quarantined/unsupported Lessons;
- source/policy/conflict preconditions are rechecked at publication;
- lost providers/jobs cannot change AEW truth or block recovery;
- at-least-once capture yields idempotent admission;
- guarded raw-history recall survives distiller abstention/outage;
- historical text cannot alter tools, permissions, configuration, or publication rules;
- use frequency/evaluator confidence never becomes evidential truth;
- new extractor versions do not overwrite previous admitted generated output without an attributable `knowledge_disposition`;
- corrupt/missing evidence degrades eligibility rather than reconstructing proof;
- recall/index lag and applicability uncertainty remain visible;
- default context delivery is bounded and owned by one AEW routing authority;
- existing Evidence identity survives capture/admission;
- `NO_CANDIDATE` is successful and candidate count is never an output quota;
- derived visibility is no broader than the most restrictive root absent authorized widening;
- K1 default serving is constrained by source/authentication class;
- immutable Knowledge content and mutable `knowledge_disposition` state remain separate;
- K2/K3 judgment-bearing admission has no silent default.

## 29. Review disposition

This document is intended for joint review with:

1. `aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md` — research basis;
2. `aew-knowledge-capture-recall-shared-semantics-v0.4.md` — shared write/read semantic contract;
3. current Knowledge Contract v0.4 — existing authority/provenance baseline;
4. current M6 Journal/dashboard handoff — human-facing projection direction;
5. W05 Evidence inspection plan — Evidence identity/navigation expectations;
6. `aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md` — consumer/read-path contract.

Approval of this document should approve the **design direction**, not implementation, schemas, wire contracts, or automatic K2 policy classes. Those require their own accepted implementation/design artifacts.
