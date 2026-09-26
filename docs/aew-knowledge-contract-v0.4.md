---
title: "AEW Knowledge Contract"
subtitle: "Companion Design Specification — v0.4"
date: "September 25, 2026"
---

# Status and authority

**Status:** Frozen companion design specification, v0.4.  
**Parent specification:** Agent Engineering Workflow (AEW) Design Specification v0.7.  
**Purpose:** Define how AEW stores, finds, reconstructs, scopes, and reasons about durable project knowledge.  
**Primary storage model:** Human-readable Markdown/YAML in or adjacent to the project repository, with non-authoritative caches and indexes stored separately.  
**Primary consumers:** The persistent Lead and bounded AEW role invocations.

This document defines the **knowledge semantics** of AEW. It does not require one exact directory tree or filename set. An implementation may choose a different physical layout if it preserves the information classes, authority rules, reconstruction behavior, provenance, freshness, and human readability defined here.

The Knowledge Contract is a design authority. Chat history, agent memory, code indexes, search services, and model-generated summaries are supporting mechanisms and must not silently replace the durable knowledge classes described below.

# 1. Problem statement

AEW can define a disciplined workflow and a rich tool environment and still fail if a new session cannot reliably answer basic questions such as:

- What is this project trying to do?
- What is the architecture today?
- Which documents are authoritative?
- What Epic/Story/Ticket is active?
- Which plan revision is accepted?
- What has already been tried?
- Which review findings remain open?
- What did verification actually establish?
- What should happen next?
- Which codebase maps are stale versus current?

LLM conversation history is not sufficient as the primary store for this knowledge. Sessions are compacted, replaced, interrupted, or moved between models and harnesses. Memory systems may retrieve stale or incomplete observations. Derived code indexes may lag the actual repository. Project documentation may already exist in a different structure and should not be duplicated merely to satisfy AEW.

AEW therefore requires a small, explicit knowledge system that:

1. stores project-control state durably;
2. references existing project authority instead of copying it unnecessarily;
3. separates authoritative knowledge from derived summaries and caches;
4. supports deterministic Lead reconstruction;
5. assembles bounded context for subordinate roles;
6. scales from a one-line Ticket to a multi-Epic project;
7. remains human-readable and editable;
8. remains portable across models and harnesses;
9. can later be accelerated by indexes/databases without making those accelerators authoritative.

# 2. Design objectives

The Knowledge Contract must provide:

- a clear global-versus-project storage boundary;
- a project manifest that identifies the AEW knowledge root and existing authoritative project documents;
- durable project, roadmap, state, Epic, Story, Ticket, review, verification, decision, and handoff information classes;
- deterministic context reconstruction after session loss;
- explicit read/write authority for roles;
- freshness and source-revision metadata for derived knowledge;
- revision history for accepted plans and other consequential artifacts;
- lightweight Ticket records for Class 0/1 work;
- richer Story/Epic records for larger or promoted work;
- a human-readable format suitable for Git review;
- stable logical names so roles request knowledge semantically rather than hard-coding paths;
- clean separation between durable knowledge and disposable indexes/caches.

# 3. Non-goals

The v0.4 Knowledge Contract does not require:

- a vector database;
- a graph database;
- an embeddings pipeline;
- a single mandatory file/directory layout;
- duplication of existing ADRs, contracts, schemas, READMEs, or design documents;
- automatic generation of every codebase map;
- replacement of Git history;
- replacement of issue trackers, SCM systems, or CI;
- storing secrets, credentials, SSH keys, or API tokens;
- storing raw chat transcripts as project truth;
- maintaining every historical role invocation forever;
- perfect automatic conflict resolution between stale knowledge artifacts.

Implementations may add indexes, search databases, memory services, or generated summaries later. Those are accelerators around this contract, not substitutes for it.

# 4. Conceptual model

AEW has three complementary contracts:

```text
AEW Workflow Contract
    what should happen

AEW Knowledge Contract
    what is known, where it lives, and what is authoritative

Workbench Capability Contract
    what tools/services are available to do the work
```

Roles use both knowledge and capabilities:

```text
Role invocation
    |
    +-- requests knowledge classes ---> Knowledge Resolver ---> durable source/artifact
    |
    +-- requests capabilities --------> Capability Resolver --> CLI/MCP provider
```

The Lead coordinates both. Subordinate roles receive only the knowledge and capabilities required for their bounded assignment.

# 5. Storage boundary

AEW uses three storage scopes.

## 5.1 Global AEW configuration

Global configuration describes **how AEW behaves on this workbench**, not the truth of an individual project.

Suggested location:

```text
~/.config/aew/
```

Typical contents:

- schema versions;
- default profiles;
- default command behavior;
- global policy defaults;
- locations of installed AEW skills/templates;
- workbench capability registry location;
- optional global documentation packs;
- local user preferences;
- project discovery rules.

Example:

```yaml
schema_version: 1

workspace:
  project_marker: .aew/project.yaml

knowledge:
  global_docs:
    - /opt/aew/docs
  default_resume_depth: focused

policy:
  preserve_plan_revisions: true
  require_handoff_on_authority_transfer: true
```

Project facts, active plans, roadmap state, and verification evidence do **not** belong here.

## 5.2 Project durable knowledge

Project knowledge is stored with the project whenever practical so it travels with the repository and participates in normal version control/review.

Suggested marker:

```text
<project-root>/.aew/project.yaml
```

A project may keep most AEW artifacts under `.aew/`, or may point the manifest at an existing project documentation structure. AEW must not require teams to move authoritative documents merely to fit one layout.

## 5.3 Local derived/runtime data

Large, disposable, generated, machine-specific, or rebuildable data belongs outside durable project knowledge.

Examples:

- GitNexus indexes;
- embeddings;
- SQLite/full-text indexes;
- parsed AST caches;
- model caches;
- browser traces not retained as evidence;
- temporary context bundles;
- role runtime logs;
- memory/index service state that can be reconstructed.

Suggested locations:

```text
~/.local/share/aew/projects/<project-id>/
```

or a project-local ignored area such as:

```text
.aew/local/
```

These stores must be safely deletable without destroying the ability to reconstruct authoritative AEW state.

# 6. Project manifest

Every AEW-enabled project has a small manifest that identifies project identity, knowledge sources, authority locations, and AEW state roots.

The exact schema may evolve, but it should be human-readable and versioned.

Example:

```yaml
schema_version: 1

project:
  id: revelations
  name: REVELATIONS
  profile: revelations

repository:
  root: ..
  vcs: git

authority:
  contracts:
    - ../docs/contracts/
  decisions:
    - ../docs/adrs/
  schemas:
    - ../docs/schema/
  source:
    - ../backend/
    - ../frontend/

knowledge:
  project_overview: knowledge/PROJECT.md
  architecture: knowledge/ARCHITECTURE.md
  codebase_map: knowledge/CODEBASE.md
  ownership_map: knowledge/OWNERSHIP.md
  glossary: knowledge/GLOSSARY.md

control_state:
  current: state/CURRENT.md
  roadmap: state/ROADMAP.md
  handoff: state/HANDOFF.md

records:
  work: work/
  decisions: decisions/
```

The manifest is a resolver/index. It does not make everything it references equally authoritative.

# 7. Knowledge authority classes

Every durable knowledge source belongs to an authority class.

## 7.1 Project authority

Existing project artifacts remain authoritative for the domain they already own.

Examples:

- ratified contracts;
- ADRs;
- source code;
- database schemas;
- API specifications;
- canonical configuration;
- organization-approved issue/SCM state where applicable.

AEW should reference these sources instead of copying their contents into parallel documents unless a project deliberately chooses otherwise.

## 7.2 AEW control authority

AEW owns workflow-control information.

Examples:

- active objective;
- work-unit classification;
- current workflow state;
- accepted plan pointer;
- Lead authority record;
- current blockers;
- roadmap execution state;
- work-unit completion record;
- handoff/resume state.

Only the Lead, or an explicit authority-transfer mechanism acting for the Lead, may mutate authoritative control state.

## 7.3 Engineering evidence

Bounded roles produce evidence artifacts.

Examples:

- investigation findings;
- external research;
- implementation report;
- review findings;
- verification report;
- debugger traces retained as evidence;
- test outputs retained as evidence.

The producing role owns the content of its report. The Lead controls how that evidence affects project/work-unit state.

## 7.4 Derived knowledge

Derived knowledge improves understanding but is not project truth.

Examples:

- codebase summaries;
- generated architecture maps;
- GitNexus relationship graphs;
- symbol indexes;
- memory summaries;
- model-generated ownership maps;
- generated dependency summaries.

Derived knowledge must record enough provenance/freshness metadata to determine whether it is still safe to rely on.

# 8. Required knowledge classes

AEW specifies logical information classes rather than mandatory filenames.

## 8.1 Project overview

Answers:

- What is this project?
- What problem does it solve?
- What are its major components?
- What environment does it assume?
- Which documents are authoritative?
- What are the high-level constraints?

This is orientation material, not a replacement for project contracts.

## 8.2 Architecture map

Describes high-level system shape:

- major components;
- control/data boundaries;
- external services;
- important cross-component flows;
- architectural ownership;
- relevant contracts/ADRs.

It may be partially derived but must clearly identify what is summary versus authoritative source.

## 8.3 Codebase map

Provides practical navigation:

- major directories;
- entry points;
- build/test locations;
- important subsystems;
- language/toolchain boundaries;
- common investigation starting points;
- generated/source directories to avoid editing;
- semantic-analysis prerequisites such as compilation databases.

A codebase map is derived and revision-bound.

## 8.4 Ownership map

Records which component/document/system is expected to own important behaviors or data.

It should prefer references to existing project authority rather than inventing ownership rules.

## 8.5 Glossary

Captures project-specific terms, abbreviations, and identity distinctions that commonly cause agent confusion.

## 8.6 Roadmap

Represents planned project/Epic sequencing at the level needed for Lead coordination.

The roadmap is not required for a tiny standalone repository but is valuable for long-running projects.

## 8.7 Current state

A compact control document answering:

- What is active?
- Who/what currently holds Lead authority?
- Which Epic/Story/Ticket is active?
- What class is it?
- What workflow state is it in?
- What plan revision is accepted?
- What blockers/open findings remain?
- What is the next expected action?

`CURRENT` should stay small enough to read on every resume.

## 8.8 Handoff

A concise reconstruction artifact for session/model/runtime changes.

It should contain:

- active objective;
- current state;
- accepted plan/revision;
- work completed since last handoff;
- open findings/blockers;
- relevant evidence references;
- next action;
- authority-transfer status if applicable.

A handoff summarizes state; it does not replace the artifacts it references.

## 8.9 Decisions

Consequential decisions should be durable and refer back to authoritative ADRs/contracts when those already exist.

AEW-local decisions may include:

- work-unit/risk classification rationale;
- plan acceptance/rejection;
- work-unit promotion;
- waiver of a required gate;
- model/tool escalation;
- authority transfer.

## 8.10 Open questions

A project/aew epic may retain unresolved questions that future investigation must not accidentally treat as settled facts.

## 8.11 Project policy / guardrails

Projects should expose human-readable, machine-queryable engineering guardrails where relevant, including:

- ownership/directory boundaries;
- allowed dependency directions/layering;
- generated-file policy;
- authoritative contract/schema/API locations;
- naming/interface conventions;
- build/test commands and expected environments;
- known baseline failures/flaky checks;
- review triggers (architecture, security, data, compatibility);
- commit/coverage/security-scan policy.

Guardrails are referenced by Planner, Implementer, Reviewer, and Verifier and participate in contract-based verification. They should be deterministically enforceable where practical without requiring every rule to become code immediately.

# 9. Hierarchical work-unit records

AEW durable state follows the engineering hierarchy:

**Project → Epic → Story → Ticket**

`Phase` is not a separate executable work-unit type in the Knowledge Contract. A project may map organizational releases/milestones/phases to Epics or collections of Epics, but the canonical AEW work graph uses the hierarchy above.

## 9.1 Ticket record

A Ticket is the smallest independently executable work item. It should minimally contain:

- Ticket ID;
- title/objective;
- parent Story/Epic when present;
- external issue/reference IDs when available;
- risk/complexity class;
- dependencies;
- scope and governing authority references;
- assignment/mini-plan or accepted plan slice;
- required capabilities/profile;
- current state;
- incremental validation obligations/results;
- review level/status;
- goal-backwards and contract verification criteria/results;
- blockers/findings;
- implementation/evidence references;
- completion decision.

A compact Ticket may live in one human-readable record with linked evidence. The physical file split is not normative.

## 9.2 Story record

A Story contains one coherent engineering objective and a local Ticket dependency graph.

It should minimally contain:

- Story ID/objective;
- parent Epic when present;
- acceptance criteria;
- Ticket graph and dependencies;
- accepted Story-level plan/decomposition;
- current roll-up state;
- aggregate review/verification requirements;
- unresolved cross-Ticket findings;
- closeout result.

Parent state should be derived from child state plus Story-specific gates rather than duplicated manually.

## 9.3 Epic record

An Epic is a larger feature/initiative containing Stories. It normally owns the full Project Control lifecycle and roadmap-level state.

It should contain:

- Epic objective/scope;
- governing contracts/constraints;
- research/design records;
- Story dependency relationships;
- accepted plan/design revisions;
- cross-Story risks/decisions;
- Epic-level validation/acceptance criteria;
- closeout/completion decision.

## 9.4 Promotion

Work may be promoted when evidence reveals the original unit is too small:

```text
Ticket -> Story -> Epic
```

Promotion triggers include unclear ownership, cross-component effects, unresolved design/security/compatibility questions, repeated plan failure, or scope expansion.

Promotion preserves the original identity/evidence and records the reason. The original record is not discarded or silently rewritten into a larger unit.

## 9.5 Work graph state

Dependencies and current state are durable knowledge. A checkpoint may show:

```text
Story S-14
  T1 DONE
  T2 DONE
  T3 RUNNING @ worktree/T3
  T4 BLOCKED -> T3
  T5 READY
```

Resume must reconstruct this state precisely enough for the Lead to continue scheduling without conversational memory.

A dependency is satisfied only when the upstream output required by the downstream work is durably accepted and present in the downstream assignment's recorded input/source snapshot. Evidence-only dependencies may be satisfied by accepted durable artifacts. A **mutating dependency is not satisfied by an isolated `COMMIT_READY` result**: the accepted output must first be integrated into the authoritative source lineage and complete the required post-integration checks. By default, that mutating Ticket reaches `DONE` only after those conditions hold; until then, dependent mutating work remains `BLOCKED`.

For mutating work, the state record must also preserve enough workspace/integration identity to prevent two concurrent Tickets from silently sharing mutation state. Where mutating concurrency is enabled, a Ticket record should identify its isolated workspace/worktree/branch (or equivalent), integration disposition, and the **evaluated snapshot identity** against which validation/review evidence was produced.

Risk classification is local to each work unit. Ancestor-triggered non-waivable gates/guardrails and any explicit minimum-descendant-class floor are referenced by descendants so that inherited policy is machine-queryable without rewriting the child's local classification.

# 10. Work creation command contract

AEW exposes distinct commands so bounded work is not confused with feature-scale work:

```text
/aew ticket <objective>
/aew story <objective>
/aew epic <objective>
```

## 10.1 `/aew ticket`

Creates or resumes a bounded Ticket. It should:

1. locate/init the AEW project root;
2. load focused project authority/guardrails;
3. assign a Ticket ID;
4. classify risk/complexity;
5. establish dependencies/completion criteria;
6. assemble a bounded context pack;
7. execute incremental checks and required review/verification;
8. close or promote the Ticket when evidence demands more scope.

A trivial counter/member edit can therefore remain a Ticket without creating an artificial milestone.

## 10.2 `/aew story`

Creates a coherent objective that is decomposed into a Ticket graph. Planning identifies dependencies, required capability/profile, and Story-level acceptance criteria. READY Tickets may execute concurrently under Lead scheduling authority.

## 10.3 `/aew epic`

Creates a feature/initiative requiring the full Project Control lifecycle. Epic planning normally produces Stories, cross-Story dependencies, and Epic-level acceptance/contract checks.

## 10.4 No hidden bypass

Starting small must not suppress necessary investigation. The Lead may promote work whenever evidence no longer supports the smaller unit. Convenience aliases must resolve to these same semantics rather than create an untracked freestyle path.

# 11. Artifact and validation provenance

Durable AEW artifacts should carry lightweight metadata where it improves reconstruction and stale-evidence detection.

Preferred metadata includes:

- schema/artifact type;
- project/work-unit identity;
- authority class;
- status/freshness;
- **evaluated snapshot identity** for engineering evidence;
- governing plan revision;
- producer role/invocation/model/provider where relevant;
- creation/update timestamp;
- input/source references;
- supersedes/superseded-by links.

For consequential validation, record:

```yaml
validation_id: V-...
work_unit: T-...
claim: ...
validator_role: verifier
model: ...
provider: ...
timestamp: ...
evaluated_snapshot:
  base_revision: ...
  workspace_id: ...
  relevant_inputs_fingerprint: ...
  artifact_digests: []
plan_revision: ...
method:
  capability: targeted_test_execution
  provider: ...
result: pass
evidence:
  - ...
```

The evaluated snapshot identifies the **actual engineering inputs or built artifact evaluated**, including relevant uncommitted changes. A commit hash/worktree name alone is insufficient for dirty state. The fingerprinting mechanism is an implementation choice, but it must distinguish a materially changed engineering input from the previously validated snapshot. AEW control-state and evidence/report files are excluded unless they are themselves the subject of validation, so writing a report cannot invalidate its own evidence.

When verification fails, the Verifier owns the failure evidence but **not** the remediation classification. The Lead records a separate classification such as `LOCAL_IMPLEMENTATION_DEFECT`, `PLAN_OR_DESIGN_DEFECT`, `CONTRACT_VIOLATION`, or `ENVIRONMENT_OR_EVIDENCE_BLOCKED`, together with the resulting state transition and supporting evidence/reference. This prevents an Implementer or Verifier from silently choosing its own path back into mutation.

The semantic minimum is **what / who / when / against / how / result / evidence**.

A passing validation tied to evaluated snapshot A never silently validates evaluated snapshot B. If relevant source/config/generated/build inputs change, the old result remains historical evidence but no longer satisfies the current gate.

# 12. Revision and immutability rules

Consequential accepted artifacts must not be invisibly rewritten.

## 12.1 Plans

Plans are revisioned.

Example:

```text
PLAN-v1
PLAN-v2
PLAN-v3  <- accepted
```

If runtime evidence invalidates the accepted plan, create a new revision:

```yaml
revision: 4
supersedes: 3
reason: "Runtime validation disproved assumption X"
status: proposed
```

Only the Lead may update the accepted-plan pointer.

## 12.2 Review and verification

Review/verification records should be additive or revisioned when the underlying implementation revision changes.

A passing report tied to evaluated snapshot A must not silently validate evaluated snapshot B.

## 12.3 Control state

Compact mutable pointers such as `CURRENT` may be updated in place, but consequential transitions should remain reconstructible through Git history and referenced work-unit artifacts.

Authoritative control updates must be **atomic and stale-writer-resistant**. Each mutating transition must be conditioned on the expected current control-state revision and current Lead authority generation (or an equivalent guard). An explicit Lead handoff invalidates the superseded writer for future authoritative updates. A crash during persistence must recover to the prior valid state or the fully published new state, never a partially written hybrid. Copies of control artifacts inside Ticket workspaces are contextual snapshots and may not become independent control authorities. Locking, CAS, transactional file replacement, or another mechanism may implement this behavior.

## 12.4 Automatic checkpoints

Checkpoint state should be written around consequential transitions such as accepted plans, Ticket state changes, parallel dispatch, workspace allocation, integration, review/verification results, major artifact writes, and explicit handoffs.

A checkpoint records durable work-graph/control references rather than opaque model internals.

For concurrent work, it records each in-flight Ticket's execution identity and isolated workspace/integration status where applicable. After a crash, in-flight subagents/workspaces are marked `INTERRUPTED`/unknown until artifacts and revisions are inspected; prior invocation status never proves completion.

# 13. Freshness and staleness

Derived knowledge must communicate freshness.

Possible states:

- `CURRENT` — generated/validated against the active relevant revision;
- `STALE` — known to lag source or environment changes;
- `UNKNOWN` — freshness cannot be established;
- `REBUILDING` — refresh in progress;
- `UNAVAILABLE` — source/provider required to refresh is unavailable.

Revision-bound knowledge should record the source revision.

Example:

```yaml
artifact_type: codebase_map
source_revision: a842be3
freshness: revision-bound
```

AEW may still use stale derived knowledge for navigation, but must verify consequential claims against current authoritative sources.

# 14. Knowledge resolution

Roles should request logical knowledge names rather than physical paths wherever practical.

Example logical names:

```text
project_overview
current_state
roadmap
architecture_map
codebase_map
ownership_map
active_requirement
accepted_plan
open_review_findings
open_verification_findings
canonical_contracts
current_work
current_ticket
current_story
current_epic
```

A knowledge index or project manifest maps those names to real sources.

Conceptually:

```text
role asks for "accepted_plan"
    -> Knowledge Resolver
    -> project manifest/current state
    -> PLAN-v3.md
```

This permits projects to use different physical documentation layouts without changing role behavior.

# 15. Role context assembly

The Lead should assemble context packs from durable knowledge rather than forwarding entire conversation histories.

## 15.1 Lead resume pack

Minimum conceptual order:

1. project manifest;
2. current AEW control state;
3. active work-unit brief;
4. accepted plan or Ticket assignment;
5. latest handoff;
6. unresolved review findings;
7. unresolved verification failures/blockers;
8. relevant authoritative project documents;
9. relevant derived architecture/codebase knowledge;
10. proposed next action.

The Lead should detect contradictions rather than silently choose whichever file it read last.

## 15.2 Investigator pack

Typical inputs:

- objective/question;
- relevant authority references;
- codebase/architecture map if fresh enough;
- affected area hints;
- allowed discovery capabilities;
- required evidence/report format.

Default write target: investigation/discovery artifact only.

## 15.3 Planner pack

Typical inputs:

- requirement/objective;
- discovery/research evidence;
- governing contracts/ADRs;
- architecture/ownership knowledge;
- validation requirements;
- unresolved questions.

The Planner should not receive unrelated historical implementation chatter.

## 15.4 Implementer pack

Typical inputs:

- assigned Ticket/plan section;
- accepted design constraints;
- relevant source locations;
- language/project skill;
- applicable tests/checks;
- required implementation report/evidence;
- prohibited scope expansion rules.

## 15.5 Reviewer pack

Typical inputs:

- original requirement/work objective;
- accepted plan/design where applicable;
- governing project rules/contracts;
- implementation revision/diff;
- relevant source context;
- test/check outputs.

The implementation reasoning transcript is excluded by default to preserve context independence.

## 15.6 Verifier pack

Typical inputs:

- acceptance criteria;
- expected observable state;
- implementation revision;
- relevant architecture/authority references;
- available verification capabilities/environments;
- unresolved review findings that affect verification.

The verifier should not accept implementer claims as evidence merely because they appear in the implementation report.

# 16. Read/write authority

Default write ownership:

| Information | Default writer/authority |
|---|---|
| Project authoritative contracts/source | Existing project process |
| Project manifest | Lead / project setup tooling |
| Current control state | Lead |
| Roadmap execution state | Lead |
| Handoff | Lead |
| Investigation/discovery | Investigator |
| External research | Researcher |
| Plan draft | Planner |
| Accepted-plan pointer | Lead |
| Implementation report | Implementer |
| Review report | Reviewer |
| Verification report/evidence | Verifier |
| Verification-failure classification / remediation transition | Lead |
| Work-unit classification | Lead |
| Work-unit promotion | Lead |
| Concurrent workspace assignment / integration disposition | Lead |
| Control-state revision / Lead-authority generation | Current Lead through state engine |
| Derived maps | Relevant generator/role; never project authority by default |

Subagents should normally write their own report/artifact rather than directly mutating shared control documents. Implementers and Verifiers may report suspected causes, but they do not own verification-failure classification or the transition back to mutation/replan. Likewise, an isolated Ticket workspace does not become authoritative project state until Lead-controlled integration occurs. State-engine adapters must reject stale/superseded Lead writes rather than reconciling two competing control authorities.

# 17. Context-size and loading policy

AEW should not solve continuity by loading the entire project knowledge store into every prompt.

Context should be assembled progressively:

```text
small orientation/context
 -> identify relevant authority/area
 -> load focused supporting knowledge
 -> inspect source/runtime evidence as needed
```

The Lead may maintain a broader project view than subordinate roles, but even the Lead should rely on indexes/manifests and selective loading instead of accumulating an unbounded transcript.

# 18. Knowledge status, work graph, and `/status`

`/status` should surface workflow state, work-graph/to-do projections, and knowledge health without requiring the user to understand the physical storage tree.

Example:

```text
Project: REVELATIONS
Lead authority: active
Epic: E-04
Story: S-14

NOW
  T-104 RUNNING

READY
  T-105
  T-108

BLOCKED
  T-106 -> T-105

REVIEW
  T-102

VERIFY
  T-103

Knowledge
  Project overview       CURRENT
  Architecture map       CURRENT
  Codebase map           STALE (14 commits behind)
  Accepted plan          CURRENT
  Handoff/checkpoint     CURRENT
  GitNexus index         STALE

Next action
  Dispatch T-105 and T-108; keep T-106 blocked.
```

The Work Graph is the canonical actionable to-do source. A separate manually maintained todo list must not become a competing authority.

# 19. Initialization and migration

## 19.1 `/init`

Project initialization should:

1. locate repository root;
2. create or identify the AEW knowledge root;
3. assign/confirm project identity;
4. discover existing documentation/authority sources;
5. create a project manifest;
6. create minimal project overview/current-state records;
7. optionally generate an initial codebase map;
8. record unresolved discovery needs rather than fabricating missing architecture knowledge.

## 19.2 Existing mature projects

For a project such as REVELATIONS, initialization should primarily **map existing authoritative documents into the manifest** rather than regenerate them.

## 19.3 Small repositories

For a small utility, initialization may produce only:

- project manifest;
- compact project overview;
- codebase map;
- current state;
- work directory / Ticket records.

The knowledge system scales with project complexity.

# 20. Global/project customization and guardrails

Global configuration may provide default schemas, role templates, capability names, artifact templates, and safe behavior.

Projects may override or extend:

- knowledge source locations;
- required artifact types;
- Ticket/Story/Epic retention policy;
- review/verification evidence requirements;
- freshness thresholds;
- profile-specific documentation;
- project-specific authority categories;
- build/test policy;
- ownership/directory/dependency guardrails;
- security/architecture/data/compatibility review triggers.

A project override must not silently weaken a core AEW invariant. Waivers are explicit and attributable.

Guardrails should be readable by humans and queryable by tools/roles. Deterministic enforcement is preferred where practical, but the contract permits staged implementation while retaining the rule as durable policy.

# 21. Indexes, memory, and search accelerators

AEW may later build fast retrieval layers around durable knowledge.

Possible accelerators:

- full-text index;
- SQLite metadata catalog;
- vector index;
- Qdrant collection;
- graph relationships;
- Claude-Mem or replacement memory service;
- local documentation search service.

Rules:

1. accelerators are rebuildable;
2. every returned item retains a path/reference to durable source where applicable;
3. staleness can be detected or surfaced;
4. derived retrieval cannot override higher-authority knowledge;
5. losing the accelerator must degrade speed/convenience, not destroy project state.

# 22. Suggested physical layout

The following is illustrative rather than normative. It demonstrates the intended hierarchy and separation between durable source and local derived state:

```text
.aew/
├── project.yaml
├── INDEX.md
│
├── knowledge/
│   ├── PROJECT.md
│   ├── ARCHITECTURE.md
│   ├── CODEBASE.md
│   ├── OWNERSHIP.md
│   ├── GUARDRAILS.md
│   ├── GLOSSARY.md
│   └── OPEN-QUESTIONS.md
│
├── state/
│   ├── CURRENT.md
│   ├── ROADMAP.md
│   └── HANDOFF.md
│
├── work/
│   └── E-<epic>/
│       ├── EPIC.md
│       ├── PLAN-v1.md
│       └── S-<story>/
│           ├── STORY.md
│           └── T-<ticket>/
│               ├── TICKET.md
│               ├── IMPLEMENTATION.md
│               ├── REVIEW.md
│               └── VERIFICATION.md
│
├── decisions/
├── research/
├── evidence/
└── local/        # ignored / rebuildable caches/indexes/runtime data
```

A project with existing authoritative docs may reference them rather than duplicate them under `.aew/`.

Codex or another implementation agent may improve the physical layout if logical identities, authority, freshness, provenance, and reconstruction semantics remain intact.

# 23. Schema strategy

Prefer small versioned schemas over one giant state schema.

Likely families:

- project manifest;
- current control-state/checkpoint metadata;
- Epic metadata;
- Story metadata;
- Ticket metadata;
- dependency/work-graph edges;
- plan metadata;
- review/validation evidence metadata;
- derived-knowledge metadata;
- project guardrail/build-test policy.

Schema validation should catch structural errors while allowing Markdown bodies to remain natural engineering prose.

# 24. Implementation readiness requirements

An implementation agent unfamiliar with this design conversation should be able to determine from this contract:

- global versus project-local state;
- durable versus rebuildable data;
- authority classes;
- Project/Epic/Story/Ticket identity and dependency semantics;
- promotion rules;
- checkpoint/crash recovery semantics, including atomic state persistence and stale/superseded writer rejection;
- Lead reconstruction/authority-transfer order;
- which role writes which artifact;
- plan/review/verification revision rules;
- validation provenance and evaluated-snapshot identity, including relevant uncommitted inputs;
- verification-failure classification authority and transition semantics;
- concurrent mutation workspace/isolation, integration identity, and mutating-dependency satisfaction semantics;
- freshness/staleness handling;
- project guardrail/build-test policy locations;
- role context-pack assembly;
- human-readable and machine-queryable state requirements.

Physical names/layouts and storage/index implementation choices that preserve these semantics remain implementation decisions.

# 25. Initial implementation slice

For cutover, the Knowledge Contract implementation may be intentionally narrow while preserving the target semantics.

**Required / high priority**

- project manifest/reference map;
- project overview/current-state record;
- durable Ticket and Story records;
- Epic schema/record support even if initial usage is sparse;
- explicit dependency graph/state;
- accepted-plan pointer/revisions;
- checkpoint/handoff/resume with atomic/version-aware control-state updates and superseded-Lead rejection;
- `/aew ticket`, `/aew story`, `/aew status`, `/aew resume`;
- basic Lead/subagent read/write boundaries;
- validation provenance fields with evaluated-snapshot identity for relevant uncommitted inputs;
- verification-failure classification record/transition;
- project guardrail/build-test references.

Mutating concurrency greater than one is **not** required for the initial slice. If workspace isolation/integration semantics are not implemented, the state engine must cap mutating concurrency at one rather than approximate safety.

**Staged/designed if time is limited**

- generic schema registry/validator;
- automatic freshness calculation;
- automatic codebase/architecture map generation;
- SQLite/vector/full-text index;
- sophisticated work-graph analytics/critical-path UI;
- automatic stale-map rebuild;
- advanced conflict detection;
- MCP adapter for state engine.

A hard-bound clean initial resolver is acceptable if logical names/contracts remain stable and migration to declarative resolution does not require redesign.

# 26. Acceptance tests

## Serial foundation path

Prove one complete Ticket lifecycle before adding scheduling sophistication: initialize project/work state; create/accept a Ticket plan; implement; independently review; verify against an evaluated snapshot; integrate; perform policy-required post-integration validation; mark the Ticket DONE; close the work; destroy the Lead session; then reconstruct the completed result from durable state.

## Fresh-session reconstruction

Destroy the Lead session. A new Lead must recover active Epic/Story/Ticket, graph state, accepted plan, open findings, guardrails, and next action without conversational memory.

## Tiny Ticket

Run `/aew ticket` for a one-field/one-location Class 0/1 change. It must create durable bounded state and complete proportionate gates without creating an artificial Story/Epic.

## Ticket promotion

Begin a Ticket; inject evidence showing hidden cross-component ambiguity. The Lead must promote it to Story while preserving the original Ticket/evidence/reason.

## Dynamic scheduling, integration, and concurrent-mutation isolation

Create a Story with dependency graph `T1,T2 -> T3` and independent `T4`. Make T1 mutating. Let T1 pass isolated checks and reach `COMMIT_READY` but leave it unintegrated: T3 must remain BLOCKED. Only after T1's accepted output is integrated into the authoritative source lineage and policy-required post-integration checks pass may T1 become `DONE` and satisfy its mutating dependency. T3's assignment must record a source/evaluated snapshot containing T1 and T2's satisfied outputs. If T1/T2/T4 are mutating and concurrency >1 is enabled, each concurrent mutating Ticket must receive an isolated attributable workspace. If isolation is unavailable, mutating dispatch must remain serial.

## Verification-failure classification

Force a verification failure after implementation. The Verifier must record failure evidence without selecting the remediation transition. The Lead must classify the failure. A local implementation defect may return to RUNNING; a design/plan defect or contract violation must replan; an environment/evidence failure remains blocked/inconclusive until resolved.

## Parent risk policy propagation

Create a Class-3 Story with a locally Class-0 Ticket and a Story-level mandatory security-review gate. The Ticket should retain its local Class-0 classification while inheriting the mandatory security gate. Also verify that an explicit parent minimum descendant class raises the Ticket's effective minimum only when recorded with Lead rationale.

## Crash-safe control update and superseded Lead

Exercise two cases: (1) interrupt persistence halfway through a control-state transition; recovery must expose either the previous valid state or the complete new state, never a hybrid; (2) hand authority from Lead A to Lead B, then attempt an authoritative update from Lead A using its stale revision/authority generation. The state engine must reject the stale write. In-flight work remains reconcilable rather than assumed complete.

## Validation staleness with uncommitted inputs

Run validation against a dirty/uncommitted evaluated snapshot and record its fingerprint. Modify a relevant engineering source/config/generated input without committing. The prior result must remain historical evidence but no longer satisfy the current gate. Updating AEW's own validation/report artifact must not invalidate the engineering snapshot by itself.

## Existing-authority project

Initialize AEW on a mature project with contracts/ADRs. The manifest references them without creating duplicate authority.

## Cache loss

Delete local indexes/caches. Durable project/work state survives and accelerators can be rebuilt.

# 27. Design invariants

1. **Project truth stays with its owner.** AEW references existing authoritative docs/source rather than cloning authority casually.
2. **Control state is durable.** Lead reconstruction does not require chat history.
3. **Human readability is required.** Core state is inspectable without opaque databases.
4. **Machine queryability is also required.** Schemas/state engine/CLI can query/update the same durable semantics.
5. **Work identity is explicit.** Project/Epic/Story/Ticket are distinct durable units.
6. **Dependencies are durable state.** Scheduling is driven by the work graph, not a prose todo list.
7. **Small work stays small.** A bounded Ticket never requires a fake Epic.
8. **Promotion preserves provenance.** Ticket→Story→Epic escalation retains origin/evidence/reason.
9. **Risk remains local; mandatory policy can inherit.** Parent class does not automatically inflate child class, but non-waivable ancestor gates/guardrails and explicit minimum floors apply.
10. **Concurrent mutation is isolated.** A mutating Ticket records its isolated workspace identity when mutating concurrency >1 is enabled; otherwise mutation is serial.
11. **Integration is explicit and attributable.** Isolated work does not silently become project truth; the integrated revision receives appropriate revalidation.
12. **Failure classification belongs to the Lead.** Verifier evidence does not authorize the Verifier/Implementer to choose RUNNING versus REPLAN_REQUIRED.
13. **Derived knowledge declares freshness.** Maps/indexes/caches never masquerade as current source truth.
14. **Validation is revision-bound and attributable.** What/who/when/against/how/evidence are retained where consequential.
15. **Role context is assembled, not inherited wholesale.** Subagents receive bounded context packs.
16. **Write authority is explicit.** Evidence producers do not silently mutate coordination state.
17. **Plans are revisioned.** Accepted intent cannot be invisibly rewritten.
18. **Caches are disposable.** Cache loss reduces convenience, not project continuity.
19. **Logical knowledge names outlive physical paths.** Resolver semantics survive layout changes.
20. **Guardrails are durable project knowledge/policy.** Ownership/structure/build-test/security rules are discoverable.
21. **The work graph is the canonical to-do source.** Status views project it; they do not duplicate it.
22. **Secrets are external.** Knowledge storage is never a credential vault.
23. **The system scales down and up.** Tiny repos and long-lived brownfield systems use the same semantics with different ceremony.

# 28. Open implementation questions

1. Exact ID scheme for Epic/Story/Ticket and mapping to Jira/Bitbucket identifiers.
2. Whether compact Tickets default to one file or split evidence/review/verification files.
3. Frontmatter versus YAML index boundaries.
4. Markdown+YAML versus YAML-only representation for mutable `CURRENT`/checkpoint state.
5. How existing GSD artifacts map during migration without duplicating state.
6. How much codebase mapping `/aew init` should perform automatically.
7. Freshness thresholds for scope-limited derived maps.
8. When a lightweight SQLite/full-text catalog becomes worthwhile.
9. Retention/compaction policy for large volumes of closed Tickets.
10. How optional organization-specific release/milestone/aew epic groupings map to Epics without becoming a second scheduler.

# 29. Definition of success

The Knowledge Contract succeeds when AEW can move between sessions, models, harnesses, users, and work sizes without losing project intent or requiring manual reconstruction.

A fresh Lead can determine what is authoritative, discover active Epic/Story/Ticket state, identify READY/BLOCKED work, load only relevant knowledge/guardrails, dispatch bounded subagents, interpret revision-bound evidence, and continue scheduling with provenance intact.

A tiny engineering Ticket remains tiny. A Story gains a clear Ticket DAG. An Epic receives full project-control structure. All three inhabit one coherent, human-readable and machine-queryable knowledge system.

