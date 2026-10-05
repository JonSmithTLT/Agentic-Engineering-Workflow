# Handoff Prompt — AEW Dashboard Work While the Real API Is Pending (v3)

**Status:** parallel frontend work only  
**Audience:** AEW dashboard/web implementer  
**Purpose:** keep useful frontend progress moving while M4 is responsible for the real read API and integration surface

## Approved planning constraints — 2026-10-03

The operator approved the four tightenings below and authorized backlog organization. This approves the constraints, not individual milestone implementation plans. The [milestone and ticket backlog](../dashboard-workbench-milestones-and-tickets.md) now governs sequencing and coverage; sections A–T remain the feature requirements. Plan each milestone separately and obtain operator approval of its exact plan revision before implementing it.

1. **Accepted API versus preview schemas.** Preserve accepted contract `0.1.2` and its recorded digest. Fields absent from it belong to separate versioned preview contracts with runtime validation, matching fixtures, and visible demo labeling. Exclude preview fixtures, handlers, and unsupported preview behavior from normal production builds. A working preview does not amend the live API: live wire shapes require main-line review and explicit acceptance. Reuse existing parsers where applicable without weakening them to accommodate speculative fields.
2. **Verification begins with the foundation.** Scenario Lab and Contract Playground share one fixture catalog, transport controls, real boundary parsers, and replay harness. Accessibility, hostile-display/CSP checks, refresh regression, and scope isolation begin in the first milestone and continue in every relevant ticket. They are not end-of-backlog cleanup.
3. **Scope isolation precedes comparisons.** Query keys, transport payload caches, and conditional validators must distinguish every supported response-changing scope, snapshot, and authorization context. Do not store credentials in cache keys. Cancel or reject obsolete responses; clear inaccessible cached data on identity/authorization changes; test old responses returning after a scope switch. No cross-scope previous-data placeholders. The backend still owns authorization and must filter payloads before delivery. Proposed scope fields are preview-only until accepted.
4. **Missing explanations and receipts stay missing.** The Why inspector shows reasons supplied for the selected record/status, or an explicit missing/unknown/denied explanation. Never manufacture reasons from unrelated fields. Context preparation, delivery acknowledgment, output citation, and independently evaluated benefit are separate claims. Rename “Recently Used” to “Included in context” unless stronger usage receipts exist. Neither HTTP success nor record type establishes semantic truth, applicability, or use.

Continue feature implementation in the separate optional frontend worktree/branch after each plan is approved. Preserve the accepted core and the main AEW checkout/running suite. Frontend fixture acceptance, independent frontend review, and integrated-system acceptance remain separate gates.

## 1. Current situation

The core dashboard is already substantially built against mocks. The real API is intentionally not available yet because the main AEW line will provide the authoritative read/query adapter later.

Already implemented in the frontend:

- API developer drawer with ETags, control revisions, timing, and exact validation fields;
- verified **Copy CLI** actions for Work, invocations, and History;
- **Ctrl/Cmd+K** jump-to-ID;
- bounded History link graph;
- labeled **Since you last looked** comparisons for Work and Runs.

Tracked gaps already known:

- Timeline support;
- Evidence CLI support.

Do **not** block waiting for the real API. Continue only with features that can be correctly expressed against fixtures and a backend-supplied read contract.

## 2. Non-negotiable architectural boundary

The dashboard remains a read-only projection.

The frontend does not decide:

- workflow legality;
- gate state;
- current/stale evidence semantics;
- plan assurance;
- queue runnability;
- publication legality;
- whether a historical decision currently binds;
- whether a lesson is authoritative;
- recall ranking truth;
- recovery state.

It may render backend-supplied conclusions, reason codes, provenance, rankings, freshness, relationships, and context-selection explanations.

Do not:

- parse `.aew/` files;
- open AEW SQLite databases directly in the browser;
- add mutation routes or mutation controls;
- create an alternate memory database in frontend code;
- infer graph edges from prose;
- invent currentness, applicability, or authority from timestamps or HTTP success.

Mock-only features must be obviously labeled as fixture/demo data.

## 3. Highest-value work while blocked

### A. Scenario / Chaos Lab

Turn the existing F0–F11 fixture worlds into a developer-visible scenario selector.

Examples:

- empty/new project;
- normal active project;
- attention-heavy project;
- history integrity problem;
- M4 queue congestion;
- 1,000 active units;
- very large paginated history;
- backend unavailable;
- stale cached data;
- mixed control revisions;
- capability downgrade;
- malformed response;
- unknown future enum;
- malicious Markdown;
- delayed/304-heavy polling.

Useful controls:

- fixture world;
- simulated response delay;
- forced 304;
- forced disconnect;
- mixed-revision injection;
- capability presence/absence;
- viewport preset.

This is a developer tool and executable API specification, not a production operator feature.

### B. Universal “Why?” Inspector

Any meaningful backend-supplied status should be inspectable.

Examples:

- `VERIFY_PENDING`;
- `STALE`;
- `ASSURED`;
- `AWAITING_DISPOSITION`;
- backend health;
- history integrity;
- queue state;
- attention item;
- currentness;
- capability unavailable.

The inspector should show only supplied facts:

- reason codes;
- human-readable explanation;
- controlling `control_revision`;
- `generated_at`;
- source references;
- evidence references;
- relevant policy/contract references if supplied;
- provenance links.

Goal:

> The operator should be able to click a state and answer “why does AEW currently say this?”

Do not reimplement the answer in frontend logic.

### C. Revision Compare / Time Machine

Generalize “Since you last looked” into a reusable comparison UI.

Support fixture-driven comparison of two backend-supplied snapshots or diffs:

- Work state changes;
- new/removed evidence;
- decision changes;
- runs started/completed;
- queue movement;
- history-root/integrity changes;
- attention changes;
- capability changes;
- context packet changes when M6 preview fixtures are used.

Suggested UX:

```text
Compare:
  rev 843  →  rev 851

Changed:
  T-142        VERIFY_PENDING → COMMIT_READY
  E-203        added
  R-77         reviewer completed
  Queue        +1 LEASED
  Attention    blocker B-12 resolved
```

Do not compute authoritative semantic diffs from raw AEW storage. The eventual backend may supply snapshots, change records, or a diff projection.

### D. Provenance Path Explorer

Expand the existing bounded History graph into a generic bounded provenance explorer.

Useful backend-supplied relation types may include:

```text
requirement
    ↓
plan
    ↓
attempt
    ↓
evidence
    ↓
review
    ↓
verification
    ↓
integration
```

Other useful relations:

- parent/child;
- depends_on;
- produced_by;
- supports;
- contradicts;
- supersedes;
- moved_to;
- promoted_to;
- lineage;
- sourced_from;
- evaluated_by.

Features:

- select start entity;
- bounded depth;
- path-to-entity;
- highlight direct supporting chain;
- inspect edge provenance;
- jump to entity detail;
- copy deep link.

All edges are backend/fixture supplied. Never infer an edge from text similarity.

### E. Run / Invocation Comparison

Add a comparison surface for two model runs or invocations.

Show backend-supplied differences such as:

- role;
- provider/model;
- reasoning/effort profile;
- role-card version/hash;
- work revision;
- source revision;
- context packet fingerprint;
- capability manifest/hash;
- selected evidence;
- selected recall items;
- duration;
- result;
- review/verification outcome.

This should become useful for questions like:

> Why did Run B behave differently from Run A?

The dashboard shows the differences. It does not diagnose causality unless the backend later supplies that diagnosis.

### F. Failure Archaeology

Build a read-only exploration view around a failure or repeated problem.

Fixture-driven shape:

```text
Current failure
    ↓
Prior attempts with same/matching signature
    ↓
Relevant evidence
    ↓
Known failed approaches
    ↓
Related lessons/discoveries
    ↓
Current source/revision differences
```

Useful filters:

- component;
- failure signature;
- dependency/environment;
- source revision;
- work item;
- model/run;
- result kind.

This is a natural bridge to M6 recall later.

## 4. M6 Preview: Knowledge Journal / Memory Stream

M6 is moving toward **AEW-owned recall and contextual learning over AEW's existing durable knowledge**, not a second memory authority.

The research direction is:

- AEW remains the authoritative durable store;
- recall indexes are derived/disposable;
- advisory lessons/discoveries can be published through AEW;
- an AEW-owned context router chooses what enters model context;
- external systems such as Engram, QMD, Claude-Mem, or context-mode are optional providers/comparators, not sources of project truth.

The frontend can express a surprising amount of this **before the API exists**, using fixtures only.

The primary human-facing concept should be a **Knowledge Journal / Memory Stream**, not a database table. The goal is a visual journal of how AEW's understanding evolves over time, with every important insight traceable backward to its evidence and forward to later work it influenced.

A simple scrolling memory product can answer:

> What did the observer store?

AEW's journal should eventually answer:

> What did AEW learn, where did it come from, is it still applicable, how did that understanding change, and where was it later reused?

That richer relationship to authoritative work/evidence is the reason to build this as an AEW-native experience rather than imitate a generic memory database viewer.

### G. Knowledge Journal / Memory Stream — flagship M6 preview

Make this the default human-facing recall view.

The default presentation is a dense, chronological, color-coded stream of retained knowledge:

```text
Today

  DISCOVERY                                      18:42
  Parser initialization depends on config_load()
  T-184 · A-3 · E-882
  current · project-wide

  FAILED APPROACH                                17:51
  Rebuilding the generated header did not fix
  the missing clangd references.
  T-181 · A-2
  valid for clangd 19 / rev a319...
  └─ later contributed to Lesson R-72

  LESSON                                         17:58
  Refresh compile_commands before treating
  missing clangd references as evidence.
  R-72
  supported by E-871, E-875
  current

  DECISION REFERENCE                             15:20
  D-42 — Generated protocol definitions remain
  source-controlled.
  authoritative source → D-42
```

Use restrained color as **type coding**, not truth coding. A lesson, discovery, failed approach, decision reference, environment constraint, and hypothesis may each have distinct accents, but applicability/currentness must always be represented explicitly with text/iconography such as:

```text
CURRENT
HISTORICALLY_VALID
STALE_FOR_ENVIRONMENT
SUPERSEDED
CONTRADICTORY
UNCHECKED
```

Unknown values must render visibly as unknown.

Useful record kinds:

- Fact;
- Discovery;
- Conditional lesson;
- Failed approach;
- Environment constraint;
- Hypothesis;
- Decision reference;
- Requirement reference;
- Evidence reference.

Each stream item should show a compact subset of:

- ID;
- kind;
- concise claim/title;
- origin work;
- origin attempt;
- source revision/environment;
- visibility;
- evidence/applicability state;
- observed/published time;
- relationship hints such as “derived from”, “supersedes”, “recalled for”, or “used in context”.

Do not overload the stream with every provenance field. The stream is for scanning; details belong in the inspector.

### G1. Knowledge detail / provenance drawer

Selecting a journal item opens an in-place detail panel rather than forcing navigation away.

Example:

```text
R-72 — CONDITIONAL LESSON

Claim
Refresh compile_commands before treating missing
clangd references as evidence of no caller.

Why AEW retained it
Verified failure/fix pair

Origin
T-181
Attempt A-2
Run R-A2-4

Evidence
E-871
E-875

Environment
Rocky 8
clangd 19
source rev a319...

Applicability
CURRENT

Derived
2026-10-02 17:58
GPT-5.4
prompt version distill/v2

Relationships
derived_from → E-871
derived_from → E-875
supersedes → R-51
recalled_for → T-203
included_in_context → RUN-992
```

The detail view should support:

- claim;
- applicability conditions;
- limitations;
- positive evidence;
- negative evidence;
- canonical source references;
- exact origin binding;
- producer/model/prompt identity when distilled;
- supersession/contradiction links;
- index/projection metadata;
- raw provenance IDs;
- “where was this reused?” links.

Important: a recalled decision must visibly be a **reference to a canonical decision**, not a second copy presented as authority.

### G2. Journal modes

The same records should support several useful modes rather than only a chronological feed.

**Chronological**
- Default.
- Human-readable stream of what AEW learned and when.

**Evolution**
- Shows how understanding changed over time.
- Example:

```text
OBSERVATION
"clangd shows no callers"
      ↓
HYPOTHESIS
"function is dead"
      ↓
FAILED APPROACH
removal breaks generated build
      ↓
DISCOVERY
compile_commands was stale
      ↓
LESSON
refresh compilation DB before using
missing references as evidence
```

**Included in context**
- Knowledge included in a prepared packet; show delivery acknowledgment separately when supplied.
- Answers: “What prior experience was included, and what delivery/use evidence exists?”
- Output citations and independently evaluated benefit require their own supplied receipts.

**By Component**
- Group/filter by subsystem, path, capability, dependency, or backend-supplied component identity.

**By Type**
- Lessons / Discoveries / Failed approaches / Constraints / Hypotheses / References.

**Needs Attention**
- Contradictory, stale, unchecked, superseded, or otherwise backend-flagged knowledge.

All grouping/relationship semantics are fixture/backend supplied. The browser does not infer evolution or contradiction from prose.

### H. Recall / Provenance Relationship Graph

The graph is a companion to the Knowledge Journal, not a separate novelty page.

When a journal item is selected, allow a bounded graph panel to show how it came to exist and how it was later used.

Potential node kinds:

```text
Ticket
Attempt
Evidence
Decision
Requirement
Lesson
Discovery
FailedApproach
EnvironmentConstraint
Run
ContextPacket
```

Potential backend-supplied edges:

```text
derived_from
supported_by
contradicted_by
supersedes
related_to
applies_to
originated_in
references
recalled_for
included_in_context
```

Useful graph modes:

1. **Origin graph**
   - lesson/discovery → source attempt → evidence → ticket.

2. **Supersession graph**
   - old advisory → contradiction/new evidence → replacement advisory.

3. **Context graph**
   - work item → recall hits → canonical sources → context packet → run.

4. **Failure graph**
   - failure signature → attempts → failed approaches → later successful evidence.

A desirable split-view interaction:

```text
┌──────────────────────────────┬───────────────────────────────┐
│ Knowledge Journal            │ Provenance                    │
│                              │                               │
│ [Discovery] ...              │       T-181                   │
│ [Failed Approach] ...        │         │                     │
│ [Lesson] R-72 selected       │       A-2                     │
│ [Decision Ref] ...           │      /   \                    │
│                              │   E-871 E-875                 │
│                              │      \   /                    │
│                              │      R-72                     │
│                              │        │                      │
│                              │      T-203                    │
└──────────────────────────────┴───────────────────────────────┘
```

Features:

- bounded depth;
- path-to-entity;
- highlight direct supporting chain;
- inspect edge provenance;
- jump to entity detail;
- deep link selected record/view;
- preserve stream selection when graph opens/closes.

Do not create semantic edges from similarity scores in the browser. A similarity score may be displayed, but relation membership must come from fixtures/backend.

### I. Recall Search / Retrieval Debugger

Build a developer-facing retrieval debugger now.

Mock inputs:

```text
query
project/work scope
component
attempt/worktree
failure signature
token/result budget
```

Mock output:

```text
R-17   CONDITIONAL_LESSON   score 12.84
R-42   DECISION_REFERENCE   exact ID/path match
R-55   FAILED_APPROACH      component + lexical match
```

For each hit show:

- retrieval score as a **ranking score, not truth probability**;
- source kind;
- scope/visibility;
- freshness/applicability;
- canonical source hash/ref;
- index generation;
- reason/match fields if supplied;
- expandable exact source.

This can later be wired to the M6 `RecallIndex`/MCP surface.

### J. “Why is this in context?” Inspector

This is one of the highest-value M6-facing views.

Given a mocked run/context packet, show:

```text
PREPARED CONTEXT PACKET
Delivery acknowledgment: show supplied receipt or UNKNOWN

Current work
  T-142 @ rev 843

Trusted current context
  Objective
  Accepted constraints
  Plan
  Current evidence
  Capabilities

Historical recall
  R-17  failed approach
  R-42  decision reference
  R-55  conditional lesson

Budget
  18,420 / 32,000 tokens

Selection
  trigger: RELATED_WORK_START
  policy: recall/v1
  selected: 3
  omitted: 12
  truncated: 1

Packet
  fingerprint: ...
```

Each recall item should answer:

> Why was this selected?

Possible backend-supplied reasons:

- exact source ID;
- same component;
- matching failure signature;
- linked decision;
- same dependency/environment;
- explicit operator/model recall;
- recent related work.

This directly supports debugging the future automatic-recall UX.

### K. Context Packet Diff

Compare two context packets:

```text
Run A
vs
Run B
```

Show:

- current constraints added/removed;
- evidence changed;
- recall hits added/removed;
- capabilities changed;
- source revision changed;
- truncation changed;
- packet fingerprint changed;
- token/byte budget changed.

This can eventually explain why two otherwise similar model runs diverged without claiming causation.

### L. Recall Freshness / Contradiction Explorer

Create a fixture-driven view for advisory knowledge state.

Examples:

```text
R-18 CURRENT
R-21 HISTORICALLY_VALID
R-34 STALE_FOR_ENVIRONMENT
R-55 SUPERSEDED
R-61 CONTRADICTORY
R-72 UNCHECKED
```

Show:

- source revision/environment;
- current revision/environment;
- superseding records;
- contradictory evidence;
- canonical source references.

Never compute these states from timestamps in the frontend.

### M. Recall Index / Generation Inspector

Developer-facing only.

Show mocked backend data for:

- projection generation;
- indexed root/revision;
- projection schema version;
- tokenizer/chunker version;
- provider name/config;
- source count;
- lag;
- last successful rebuild/catch-up;
- degraded/rebuilding state.

If external providers are later evaluated, this view can compare:

```text
AEW-native FTS
QMD
Engram
```

without making any provider authoritative.

Do **not** show or manipulate raw provider DB tables.

### N. Candidate Distillation Inbox — Read Only

A future M6 distiller may produce candidate facts/lessons/discoveries.

Build a read-only fixture view now:

```text
Candidate C-17
kind: CONDITIONAL_LESSON

claim:
  Refresh compile_commands before treating missing clangd
  references as evidence of no caller.

sources:
  T-142 / A-17 / E-203

producer:
  GPT-5.4 / prompt hash ...

limitations:
  observed on environment ...

possible duplicate:
  R-12

status:
  PENDING_REVIEW
```

No approve/reject/publish controls in the current dashboard. It is inspection only until a separate mutation design exists.


## 4A. Additional Safety / Operations Surfaces

These ideas expose known AEW failure modes and future authority boundaries. They are valuable precisely because they make limitations and unresolved obligations visible rather than merely adding more navigation.

### O. Execution Guarantee Badge / Guarantee Strip

Every run should eventually display a backend-supplied statement of the guarantees that actually held for that execution.

Examples:

```text
Execution guarantees

Filesystem containment    VERIFIED
Process containment       VERIFIED
Network isolation         NOT PROVIDED
Harness edit restriction  DEFENSE_IN_DEPTH
Worktree separation       VERIFIED

Validated on
Rocky 8 / containment profile B3
receipt C-881
```

At minimum distinguish:

- verified strong containment;
- workdir/worktree separation only;
- defense-in-depth harness restriction;
- explicitly not provided;
- unknown/unlabeled.

**Unknown/unlabeled must be loud.** Never inherit a friendly "sandboxed" label because a harness or worktree exists.

This can appear:

- on Run detail;
- in the Run Flight Recorder;
- in Run comparisons;
- in capability/environment detail;
- optionally as a compact project-level guarantee strip when the backend supplies an aggregate/current statement.

The frontend never derives a guarantee from tool configuration. It renders backend-supplied guarantee class, validation environment, receipt/evidence reference, and age/currentness.

### P. Open Consequential Observations Board

Future F17/consequence-tracing projections can drive a read-only board of unresolved or consciously accepted consequential observations.

Possible backend-supplied states include:

```text
AWAITING_DISPOSITION
ACCEPTED_OPEN
KNOWN_LIMIT
RESOLVED
SUPERSEDED
```

Useful summary:

```text
Open consequential observations   17
Accepted open                       8
Known limitations                   4
Awaiting disposition                5
Oldest unresolved              19 days
New this week                       3
Resolved this week                  2
```

Do **not** turn `accepted_open` share or any count into a red/green quality score. More accepted-open items can represent more honest accounting rather than worse engineering.

Detail should answer:

- what was observed;
- why it is consequential;
- disposition;
- source/evidence;
- affected trust surface/component;
- age;
- owner/actor if supplied;
- related decision or follow-up work;
- whether closure evidence exists.

This should make silent termination and silent closure hard to miss.

### Q. Judgment Queue / Stage-Intent Inspector

When F15 / Two Surfaces read projections exist, provide a first-class view of work that crossed from mechanical choreography into unresolved judgment.

Example:

```text
Requires Lead judgment

T-142
  unexpected review finding
  next action cannot be policy-resolved

T-161
  integration candidate changed after validation

Stage intent SI-91
  operation: publish
  state: interrupted
  recovery: disposition required

Anomaly A-17
  verifier workspace mutation
```

Show separately:

- pending judgment-bearing items;
- stage intents;
- dangling/interrupted intents after recovery;
- anomalies that required disposition;
- exactly what evidence/reason codes were surfaced to the Lead.

The frontend must not decide that an item requires judgment. It renders the backend `ActionProjection`/stage-intent/anomaly result.

This should reuse the Investigation Workspace / Why / Evidence panes rather than become an isolated page.

### R. Fanout Tree / Execution Budget View

Visualize the execution tree caused by a Lead/run, including registered harness-native helpers when the backend exposes them.

Example:

```text
Lead R-100
├─ Implementer R-101
│  ├─ helper H-1
│  ├─ helper H-2
│  └─ helper H-3
├─ Researcher R-102
│  ├─ helper H-4
│  └─ helper H-5
└─ Reviewer R-103
   └─ helper H-6

Fanout budget     12
Observed           7
Active             3
Unattributed       0
Max depth          2
```

Useful execution classes when supplied:

- AEW invocation;
- harness-native helper;
- provider/internal child;
- unknown/unregistered execution.

If a future incident produces 43 children against a budget of 8, the dashboard should make it obvious without implying that the browser itself detected or enforced the violation.

Integrate this with:

- Run Flight Recorder;
- Attempt Isolation;
- Run comparison;
- cost/usage inspection where supplied.

### S. Seeded Bad-Review Training World

Extend guided training/scenario worlds with deliberately suspicious review fixtures.

Do **not** teach the heuristic "short review = bad."

Use contrasted cases:

```text
Review A
30 seconds
0 findings
3 substantial files supposedly inspected
0 evidence opened
large source change

Review B
42 seconds
0 findings
small 3-line doc-only change
all required evidence opened
mechanical checks passed
```

Ask the operator which deserves investigation and require exact evidence/reasoning from the fixture.

Useful adversarial variants:

- zero findings after a large source change;
- reviewer never opened required evidence;
- stale context packet;
- reviewer inspected a different revision;
- review claims broad coverage but traversal/excerpts were partial;
- fast but legitimate mechanical review as a control.

Measure operator detection accuracy, not just completion speed.

### T. Optional Project-Level Guarantees / Obligations Strip

If the backend can provide a coherent aggregate snapshot, a compact top-level strip may summarize important guarantees and unresolved obligations:

```text
Execution containment     VERIFIED
History integrity         VERIFIED
Consequential obs open    17
Judgment required          3
Active fanout           8 / 12
Recall index lag           0
Mixed revisions          NONE
```

Every value must be clickable and backend-supplied. `UNKNOWN`/`UNAVAILABLE` must be explicit. Do not synthesize project health from these values and do not show an aggregate "green" score.


## 5. Developer Contract Playground

Extend the API developer drawer into a small contract workbench.

Capabilities:

- paste/load a fixture response;
- show Zod validation result;
- show exact failure path;
- show unknown fields;
- show unknown enum handling;
- show `ETag`;
- show `control_revision`;
- show `generated_at`;
- show cached revision;
- simulate 304;
- simulate timeout/disconnect;
- show resulting rendered-state classification.

This should become very useful when the M4 adapter starts landing.

## 6. Deep-link and Navigation Improvements

Continue making everything linkable.

Examples:

```text
/work/T-142?tab=evidence&rev=844
/runs?work=T-142&role=reviewer
/history/H-981?view=links
/recall/R-55?tab=provenance
/compare?left=843&right=851
```

Add **Copy dashboard link** where useful.

Cmd/Ctrl+K can grow from jump-to-ID into a fixture-backed navigation/search palette, but do not build a full semantic search engine in the browser.

## 7. Continuous engineering quality

These checks begin with the shared foundation and accompany each relevant feature. Use spare capacity to deepen them rather than invent backend semantics.

Recommended order:

1. accessibility / keyboard-only pass;
2. compiled-CSP validation;
3. hostile Markdown and external-resource regression;
4. bundle-size/dependency audit;
5. remove unused packages;
6. large-list and graph performance profiling;
7. React Query cache/degraded-state review;
8. visual regression screenshots;
9. responsive-density cleanup;
10. component/API-boundary review for assumptions that leaked outside `src/api`.

Architecture review questions:

- Is every semantic conclusion backend-supplied?
- Can unknown enum values ever render as normal/success?
- Can capability absence ever look like empty/healthy?
- Can stale cached content ever look current?
- Does any page know `.aew` storage layout?
- Does any graph infer an edge?
- Does any optional feature add a dependency before it is used?
- Are mock-only pathways excluded from the production build?
- Could the real API replace the mock transport without rewriting pages?

## 8. Milestone sequencing and approval

Use the [milestone and ticket backlog](../dashboard-workbench-milestones-and-tickets.md). It consolidates this handoff and research D01–D25 without treating the whole backlog as one sprint:

1. W01: preview contracts, scope isolation, Scenario Lab/Contract Playground, regression foundation.
2. W02: shared investigation shell, Why, provenance, and navigation.
3. W03: flagship Knowledge Journal, detail drawer, and bounded origin graph.
4. W04: independently scoped comparisons and context inspection.
5. W05: evidence reader, existing CLI/timeline gaps, and benchmark views.
6. W06: flight recorder, fanout, and execution/capability receipts.
7. W07: deeper recall, evolution, reuse, and failure investigation.
8. W08: F15/F17 operational projections and supplied project aggregates.
9. W09: dossier viewer, guided training, and bounded experiments.

The detailed backlog specifies prerequisites and conditional parallel opportunities; this is not a promise to implement unavailable live projections. Each milestone requires a concrete plan, approval record, fixture evidence, independent review, and a separate integration disposition. Backend-dependent tickets may be previewed against reviewed versioned fixture proposals after plan approval.

## 9. Stop conditions

Stop and ask rather than inventing semantics if implementation appears to require:

- defining whether a record is authoritative;
- defining whether a lesson currently applies;
- computing evidence currentness;
- defining queue legality;
- defining plan assurance;
- mutating candidate/recall state;
- reading AEW SQLite directly;
- parsing `.aew/`;
- inventing a new durable memory schema;
- deciding recall ranking policy that is meant to be backend-controlled;
- creating a privileged automatic-injection channel that changes instruction authority.

Mock the missing backend result instead.

## 10. Deliverable

Continue on the separate optional frontend worktree/branch only after the relevant milestone plan is approved. Deliver reviewable increments; do not change the accepted core merely to host future previews.

For the M6 preview specifically, the expected product direction is now:

> **Knowledge Journal / Memory Stream** as the primary human interface to accumulated AEW learning, with an in-place provenance inspector, evolution views, reuse/context history, and bounded graph exploration.

A plain table-only recall browser does not satisfy this product direction, although a dense table may exist as an alternate mode.

The best outcome is not “more pages.” It is:

> When M4 and later M6 provide real read projections, the dashboard already has mature ways to inspect state, provenance, revisions, context, recall, degradation, and developer-contract behavior without forcing backend semantics into React.

Treat every M6-facing screen as a **preview of backend-supplied semantics**, not an implementation of the M6 engine.
