# AEW Live Coordination and Assumption-Propagation Design v0.1

**Status:** Designed - frozen at v0.1 pending M3 dogfood  
**Scope:** Post-M2/M3 AEW coordination primitive; no change to M1/M2 frozen contracts  
**Primary implementation window:** First usable form after the live harness exists (M3+); scheduler-driven automation may arrive later with M5  
**Purpose:** Let concurrently running agents share useful discoveries, blockers, contradictions, and partial knowledge while work is still in flight, without creating a second authority system or collapsing bounded context.

---

## 1. Problem statement

AEW already has strong mechanisms for structuring work: Epic/Story/Ticket hierarchy, role cards and archetypes, bounded invocations, durable evidence, explicit authority, review/verification gates, resumable control state, and the ability to start and stop agents according to work needs.

What AEW does not yet have is a first-class mechanism for **live team coordination**.

Today the natural interaction shape is still largely:

```text
Lead dispatches Agent A
Lead dispatches Agent B
Lead dispatches Agent C

A works in isolation -> final artifact
B works in isolation -> final artifact
C works in isolation -> final artifact

Lead reconciles the results afterwards
```

That is safe, but wasteful for work where agents are pursuing related questions. If five agents each receive 100k tokens of context and reasoning budget, AEW should not force them to rediscover facts that another agent already established 20 minutes earlier.

This is especially expensive in:

- parallel research;
- reverse engineering and behavior tracing;
- codebase mapping;
- incident/root-cause analysis;
- architecture exploration;
- vulnerability research;
- large refactors with several specialists;
- implementation work where one discovery changes assumptions for sibling Tickets.

The missing primitive is therefore not "multi-agent chat." It is **durable, bounded, authority-safe live coordination**.

---

## 2. Design objective

Add a coordination layer that lets active agents:

1. publish meaningful progress before task completion;
2. share confirmed findings and evidence references;
3. expose hypotheses and uncertainty;
4. ask targeted questions of other active roles;
5. report blockers immediately;
6. surface contradictions between agents;
7. broadcast a breakthrough that may affect sibling work;
8. receive relevant knowledge discovered by other agents;
9. participate in a Lead-facilitated coordination checkpoint ("standup" / "sync");
10. preserve useful coordination history across session loss and resume.

The coordination layer must **not**:

- let agents alter accepted plans by consensus;
- let one agent grant another authority;
- make free-form chat a new source of project truth;
- expose every agent's full context to every other agent;
- overwrite evidence or hide disagreement;
- make coordination transcripts necessary for deterministic resume;
- allow a breakthrough to silently rewrite running assignments.

---

## 3. Core principle: coordination is not authority

The central invariant is:

> **Coordination may move knowledge. Only existing AEW authority paths may move project state.**

Examples:

| Coordination event | What it may cause | What it cannot do directly |
|---|---|---|
| Investigator reports a newly discovered call path | Lead routes the finding to other agents; Investigator submits a discovery record | Change the accepted Story plan |
| Three agents agree an approach is wrong | Lead records a replan decision | Consensus does not itself replan |
| Researcher proves a previously impossible capability is viable | Lead triggers impact assessment, may revise Story/Epic plan | Researcher cannot create or accept the replacement plan |
| Implementer reports a blocker | Lead may dispatch a specialist, create a dependency, or replan | Implementer cannot unblock itself by changing control state |
| Reviewer identifies a contradiction | Lead may call a sync and require follow-up evidence | Reviewer does not resolve the contradiction by assertion |

A coordination record is working knowledge and provenance. If a fact must become accepted engineering evidence, it must still enter AEW through the existing evidence path. If a plan must change, the Lead must still use the existing planning/control path.

---

## 4. Three-layer coordination model

AEW coordination is composed of three related layers.

### 4.1 Layer A - Live coordination updates

An active invocation may publish a structured update at any useful point during execution.

Typical update types:

- `progress`
- `finding`
- `hypothesis`
- `question`
- `blocker`
- `contradiction`
- `breakthrough`
- `handoff_hint`
- `working_note`

These updates are short, attributable, append-only records. They should reference evidence/artifacts rather than copy large bodies of text.

A breakthrough does not need to wait for a standup. It can be published immediately.

### 4.2 Layer B - Routed coordination / inbox

The Lead (and later, policy/scheduler assistance) routes relevant updates to affected active invocations.

To reduce silent under-routing, AEW may also produce **non-authoritative relevance hints**. A relevance hint is a cheap structural signal that an update may matter to an active invocation because their declared references overlap. Candidate signals include:

- file/path overlap;
- symbol or entity overlap;
- shared source snapshots;
- shared evidence or authority references;
- explicit hierarchy or dependency relationships.

A relevance hint is only a nudge to the Lead. It cannot route or deliver a delta by itself, create an impact hold, alter state, widen scope, change a plan, or grant authority. The Lead decides whether to route the update, request clarification, open a sync, or ignore the hint. The hint should retain the structural reason that produced it so the Lead can assess its quality.

Absence of a relevance hint is **not** evidence that two work units are independent. Undeclared technical overlap may still exist.

Agents do **not** receive the entire coordination stream by default. They receive a bounded coordination delta containing only information relevant to their assignment.

A routed delta may say:

```text
New confirmed finding from INV-42:
The packet parser entry point is parse_frame(), not dispatch_packet().
Evidence: E-188, source snapshot abc123.

Question for your assignment:
Does this alter your current call-graph hypothesis?
```

This keeps context bounded while avoiding redundant exploration.

### 4.3 Layer C - Coordination checkpoint (standup / sync)

A sync is a scoped, Lead-facilitated convergence event for a Ticket, Story, Epic, or explicit set of related work units.

It aggregates:

- current progress;
- new evidence;
- blockers;
- contradictions;
- questions;
- assumptions under challenge;
- proposed impact on current work.

The output is not a democratic decision. The Lead closes the sync by recording normal AEW actions and decisions.

---

## 5. Why a standup is not enough by itself

A meeting-only model would recreate the same inefficiency on a shorter cycle. If Agent A makes a decisive discovery at minute 10 and the scheduled sync is at minute 45, Agents B and C can still waste 35 minutes following a now-invalid path.

Therefore:

```text
live updates / routing
        +
scoped standups when convergence is needed
        =
AEW coordination
```

Standups are the convergence mechanism, not the transport mechanism.

---

## 6. Coordination update record

Proposed conceptual schema:

```yaml
schema: aew/coordination-update/v1
id: CU-0042
scope:
  work_unit: S-0014
producer:
  invocation: INV-0031
  archetype: investigator
  card: vr_analyst
kind: breakthrough
summary: >
  Packet ownership is established before the dispatcher. The earlier
  assumption that dispatch_packet() creates packet state is false.
status: confirmed
refs:
  evidence: [E-0118]
  artifacts: [A-0041]
  source_snapshot: git-tree:abc123
questions:
  - Does this invalidate T-0081's parser-state model?
blockers: []
contradicts:
  - decision_or_plan_ref: PLAN-S14-r2
    assumption: "dispatcher creates packet state"
suggested_impact:
  scope: story
  severity: assumption_invalidated
created_at: ...
```

Important properties:

- Producer identity is engine-owned.
- Invocation, plan, and snapshot bindings are engine-owned.
- The agent may suggest impact, but the Lead determines actual impact.
- `confirmed` means the producer considers the claim supported; it does not make the update authoritative project truth.
- Large artifacts remain separate and are referenced by hash/id.

---

## 7. Coordination inbox and context deltas

Each active invocation may have a durable coordination inbox.

The inbox contains structured deltas, not raw peer contexts. Relevance hints belong to the Lead/coordinator view until the Lead actually routes an update; a hint alone does not deliver peer knowledge into an invocation.

An invocation may receive a delta only when the information is relevant to its existing scope. Delivering new information does **not** widen authority, allowed paths, capabilities, or objectives.

Every delivered delta is pinned into invocation history with:

- update id/hash;
- sender;
- delivery time;
- reason/routing source;
- affected question or assumption.

This provides a reproducible answer to:

> "What new information did this agent learn after launch?"

### 7.1 Knowledge update versus assignment change

AEW must distinguish these cases.

**Knowledge update:**

- adds relevant facts/evidence;
- does not change objective, scope, plan, authority, or expected output;
- may be delivered to the current invocation as a context delta.

**Assignment change:**

- changes objective, accepted plan, allowed scope, expected output, or governing assumption enough that the original launch contract is no longer accurate;
- must terminate/supersede the old invocation and create a new bounded invocation.

An existing invocation is never silently rewritten into a materially different job.

---

## 8. Coordination checkpoint (standup / sync)

A sync is scoped to one of:

- Ticket;
- Story;
- Epic;
- explicit related-work set.

Typical triggers:

- Lead request;
- two or more agents are pursuing the same higher-level question;
- a blocker appears;
- contradictory findings appear;
- one agent publishes a likely Story/Epic-impacting breakthrough;
- a research finding affects implementation assumptions;
- before a substantial replan;
- before Story/Epic closeout when parallel work produced divergent findings;
- later, scheduler heuristics identify high coordination value.

### 8.1 Sync flow

```text
Lead opens SYNC-17 for Story S-14
        |
        +--> Engine snapshots relevant active participants
        |
        +--> Each participant receives a bounded sync request
        |
        +--> Participants submit structured updates / responses
        |
        +--> Engine groups evidence, blockers, contradictions, questions
        |
        +--> Lead receives the combined coordination pack
        |
        +--> Lead may issue targeted follow-up questions
        |
        +--> Lead closes sync with references to normal AEW actions
```

Possible Lead actions after a sync:

- no change;
- route a new context delta;
- ingest/promote evidence;
- create a new Ticket;
- add/remove a dependency;
- dispatch a specialist;
- replan a Ticket;
- revise a Story/Epic plan;
- move/promote/cancel work;
- request another verification;
- escalate a contract/authority question.

The sync record references these actions; it does not replace them.

---

## 9. Critical case: foundational assumption invalidation

The most important coordination event is not a routine status update. It is a discovery that changes the meaning of current work.

Example:

> The team planned around the assumption that capability X was impossible. A researcher proves X is possible and provides reproducible evidence.

If AEW merely broadcasts that fact, active work may continue executing plans that are now obsolete. If AEW lets the discovering agent automatically rewrite the plan, authority collapses.

AEW therefore needs an explicit **assumption invalidation protocol**.

---

## 10. Assumption invalidation protocol

### 10.1 Step 1 - Publish the challenge

The discovering invocation publishes a `breakthrough` or `contradiction` update with:

- evidence reference;
- the challenged assumption;
- the artifact/plan/decision containing the assumption, when identifiable;
- suggested affected scope;
- confidence and unresolved questions.

The producer cannot invalidate the assumption authoritatively.

### 10.2 Step 2 - Lead impact triage

The Lead classifies the impact using named categories rather than numeric risk scores:

| Impact | Meaning |
|---|---|
| `INFORMATIONAL` | Useful knowledge; no current assignment is invalidated |
| `RECONTEXTUALIZE` | Running work remains valid, but agents should receive the new fact |
| `TICKET_REPLAN` | At least one Ticket's current plan/assignment is no longer trustworthy |
| `STORY_REPLAN` | The Story objective/approach or several descendants require reassessment |
| `EPIC_REPLAN` | The discovery changes strategy across multiple Stories |
| `PROJECT_ESCALATION` | The discovery challenges project authority, frozen contracts, or an operator-owned decision |

This classification is a Lead decision and references the breakthrough evidence.

### 10.3 Step 3 - Establish an impact hold when required

For `TICKET_REPLAN`, `STORY_REPLAN`, or `EPIC_REPLAN`, the Lead may establish a durable **impact hold** over the affected work scope.

The hold is an overlay, not a replacement work state.

While held, affected work may not:

- receive new execution dispatches;
- advance through forward completion transitions;
- prepare or publish integration;
- consume the challenged assumption as though it were current.

The Lead may explicitly allow selected active research/investigation invocations to continue **only to assess impact or gather missing evidence**.

The hold prevents expensive obsolete execution without destroying useful state.

### 10.4 Step 4 - Run an impact sync

The Lead starts a sync for the affected Ticket/Story/Epic.

Participants do not simply report status. They answer targeted impact questions such as:

- Which conclusions remain valid?
- Which planned tasks are now unnecessary?
- Which work becomes newly possible?
- Which completed evidence remains useful?
- Which active invocations are based on the invalid assumption?
- Does the discovery alter acceptance criteria or only implementation approach?
- Are there contradictions that still need evidence?

### 10.5 Step 5 - Resolve through existing AEW authority

The Lead chooses ordinary AEW actions.

**Ticket-level:**

- recontextualize the current invocation if scope/plan remain valid;
- otherwise supersede the attempt and replan/re-dispatch;
- create complementary investigation work if needed.

**Story-level:**

- revise the Story plan;
- allow M2 ancestor-plan binding rules to make affected descendant plans STALE;
- reconfirm unaffected descendants explicitly;
- replan, cancel, create, move, or promote Tickets as required.

**Epic-level:**

- revise the Epic plan;
- invalidate dependent descendant plan bindings through the normal hierarchy rules;
- add/cancel/restructure Stories and Tickets;
- retain unaffected subtrees when their assumptions remain valid.

**Project/contract-level:**

- follow existing operator/escalation rules;
- coordination cannot amend frozen contracts or project authority itself.

**Impact-scope safety rule:**

- known affected work may be held and reassessed;
- known unaffected work may continue;
- **uncertain overlap is never silently classified as unaffected**. It is surfaced to the Lead and remains conservatively held or constrained until the uncertainty is resolved enough to make a safe decision.

Narrow impact holds therefore depend on the quality of AEW's work graph and overlap discovery. Declared hierarchy/dependency edges are authoritative inputs, but they may be an incomplete description of technical overlap between files, symbols, runtime state, or external systems. Before autonomous concurrent mutating work relies heavily on narrow impact holds, AEW needs either adequate overlap/relationship discovery or conservative behavior when overlap is unknown. Coordination does not solve that lower-level discovery problem; it makes the dependency explicit.

### 10.6 Step 6 - Release the hold

The impact hold is released only after the Lead records the required resolution path, such as:

- plan revised and accepted;
- affected descendants reconfirmed or replanned;
- obsolete attempts superseded;
- new dependencies/work created;
- operator escalation completed when necessary.

The resolution record lists exactly what was invalidated, what survived, and why.

---

## 11. Why impact holds should be overlays, not new lifecycle states

AEW already has meaningful states such as RUNNING, REPLAN_REQUIRED, VERIFICATION_FAILED, BLOCKED, and INTERRUPTED.

A Story-level breakthrough may affect units in several different states simultaneously. Rewriting all of them into one new `COORDINATION_BLOCKED` state would destroy semantic information.

Instead:

```text
Ticket T1 = RUNNING + held by impact IH-7
Ticket T2 = REVIEW_PENDING + held by impact IH-7
Ticket T3 = READY + held by impact IH-7
```

The normal state remains truthful; the hold supplies an additional guard.

---

## 12. Preserving disagreement

Coordination must never optimize away contradictions by summarizing them into fake consensus.

If two agents disagree:

```text
Agent A: ownership begins in parse_frame()
Agent B: ownership begins in decode_header()
```

AEW stores both positions with evidence references and marks the contradiction unresolved.

The Lead may:

- ask each agent a targeted follow-up;
- dispatch an independent investigator;
- request a verifier;
- choose a conservative plan while recording uncertainty.

A sync summary must retain the disagreement until evidence or a Lead decision resolves it.

---

## 13. Mid-task documentation and working knowledge

Agents should not be forced to wait until the end of a 100k-token investigation to produce the first reusable artifact.

The coordination layer allows:

- short structured updates;
- working notes;
- links to partial diagrams/maps;
- provisional evidence references;
- open-question lists.

However, AEW should maintain a hierarchy of trust:

```text
coordination update / working note
        -> useful working knowledge

durable evidence record
        -> role-produced engineering evidence

Lead decision / accepted plan / authority doc
        -> authoritative control or project truth
```

Useful coordination notes may later be promoted into a normal knowledge/evidence artifact. Promotion is explicit and preserves provenance.

---

## 14. Token and context economics

Coordination exists partly to recover value from expensive parallel agent work.

If five agents each consume 100k tokens, the system should not require a sixth 500k-token context merely to combine their raw conversations.

Rules:

1. Never share raw hidden reasoning or full transcripts.
2. Updates are structured summaries plus references.
3. The Lead receives deduplicated deltas, not complete peer contexts.
4. Agents receive only updates relevant to their current assignment.
5. A sync pack contains the latest meaningful delta from each participant plus referenced evidence.
6. Older routine progress may be compacted into a checkpoint summary while preserving hashes/provenance.
7. Contradictions, blockers, breakthroughs, and decisions are never compacted away.

This makes coordination a token-saving mechanism rather than another token multiplier.

---

## 15. Proposed durable artifacts

Suggested project layout:

```text
.aew/
  coordination/
    updates/
      CU-0042.yaml
      CU-0043.yaml
    syncs/
      SYNC-0017.yaml
      SYNC-0017.md
    impacts/
      IH-0007.yaml
```

These are AEW control/coordination artifacts, not project authority documents.

### 15.1 Coordination update

Append-only producer update with immutable identity and bindings.

### 15.2 Sync record

Contains:

- scope;
- reason/trigger;
- participant invocation ids;
- update/evidence refs;
- questions asked;
- contradictions;
- blockers;
- Lead closeout summary;
- references to resulting AEW decisions/actions.

### 15.3 Impact-hold record

Contains:

- triggering update/evidence;
- Lead impact classification;
- affected units/subtree;
- allowed continuation exceptions;
- resolution requirements;
- release decision and references.

---

## 16. Proposed commands / engine operations

Names are illustrative and should be reviewed before implementation.

```text
# Publish during an active invocation
aew coord publish <scope> --kind finding|blocker|breakthrough|...

# View updates relevant to an invocation
aew coord inbox

# Lead routes an update explicitly
aew coord route CU-42 --to INV-31 --reason "changes call-path assumption"

# Open a coordination checkpoint
aew sync open <T|S|E> --reason "conflicting parser ownership findings"

# Participant response
aew sync respond SYNC-17 --update <file>

# Lead closes with references to normal AEW decisions/actions
aew sync close SYNC-17 --summary <file>

# Impact handling
aew impact assess CU-42 --scope story --classification STORY_REPLAN --reason ...
aew impact hold IH-7
aew impact release IH-7 --decision D-88
```

Agents never receive Lead-only coordination-control operations.

---

## 17. Capability and role interaction

Proposed ordinary capabilities:

- `coordination.publish`
- `coordination.read_relevant`
- `coordination.respond`

Lead-only/control capabilities:

- `coordination.route`
- `coordination.sync_open`
- `coordination.sync_close`
- `coordination.impact_assess`
- `coordination.impact_hold`
- `coordination.impact_release`

Role cards may specialize **how** a role coordinates, but cannot widen authority.

Examples:

- Reverse Engineer may publish call-graph breakthroughs.
- Security Reviewer may publish contradiction/risk updates.
- Researcher may publish newly discovered external constraints.
- Implementer may publish blockers or assumptions requiring validation.

---

## 18. Interaction with hierarchy

Hierarchy gives coordination a natural scope.

### Ticket sync

Used when multiple bounded roles contribute to one difficult Ticket, or when review/research support is attached to that Ticket.

### Story sync

Primary coordination unit for several parallel Tickets pursuing one coherent objective.

This is likely the most common "standup" scope.

### Epic sync

Used when a discovery or strategy question affects multiple Stories. It should be rarer and more expensive.

### Cross-scope routing

A Ticket finding may be routed upward when its suggested impact exceeds the Ticket. The Lead determines whether it becomes Story/Epic coordination.

---

## 19. Example: three research agents tracing behavior

Story objective: determine how packets become owned, validated, and dispatched.

The Lead dispatches:

- INV-A: source/AST trace;
- INV-B: call-graph / relationship trace;
- INV-C: runtime/log evidence trace.

At minute 12, INV-B finds that `parse_frame()` allocates packet state before the function the other two were treating as the entry point.

INV-B publishes a `breakthrough` with evidence.

The Lead routes the finding immediately:

- INV-A stops tracing the obsolete entry point and validates ownership paths around `parse_frame()`;
- INV-C searches runtime evidence for allocation before dispatch instead of repeating the earlier hypothesis.

At minute 25, a Story sync runs. Each agent contributes complementary results instead of three overlapping reports.

The final Story evidence is better **and** less total compute was wasted.

---

## 20. Example: breakthrough changes an Epic

Epic objective: build a remote binary-analysis path.

Current assumption in Epic plan: remote artifact acquisition cannot be supported in the approved environment, so every Story is structured around local-only analysis.

A Researcher discovers an already-approved transport path and provides auditable evidence that remote acquisition is permitted and technically viable.

Flow:

1. Researcher publishes `breakthrough` CU-81.
2. Lead classifies it `EPIC_REPLAN` and opens impact hold IH-12.
3. New mutating dispatch/integration in the affected Epic is paused.
4. Active Researchers/Investigators may continue only to validate impact.
5. Epic sync asks each Story owner which assumptions and planned work are affected.
6. Lead revises and accepts Epic plan r3.
7. M2 ancestor-plan bindings mark descendant plans stale.
8. Lead evaluates affected scope using declared dependencies, completion/evidence provenance, and any structural relevance/overlap hints. Descendants are reconfirmed as unaffected only when that judgment is supportable; uncertain overlap remains held for targeted validation.
9. Lead reconfirms the genuinely unaffected descendants.
10. Obsolete local-only attempts are superseded; newly possible Stories/Tickets are created.
11. Impact hold is released.

No agent silently changes the Epic. No useful completed evidence is discarded. Unaffected work survives. The breakthrough changes strategy through the same authority machinery AEW already trusts.

---

## 21. Resume and reconstruction

`aew resume` should surface coordination only when it changes what the Lead needs to know next.

Example:

```text
Story S-14: IN_PROGRESS
Active Tickets: T-81, T-82, T-84
Latest sync: SYNC-17

Coordination:
- 1 unresolved contradiction (packet ownership)
- T-82 blocker cleared by E-188
- breakthrough CU-42 triggered impact hold IH-7
- Story replanning required before affected Tickets may advance

Next actions:
1. Resolve/replan Story S-14 under IH-7.
2. Reconfirm or supersede affected descendant plans.
3. Release impact hold.
```

Routine chatter should not flood resume.

---

## 22. Coordination invariants

The implementation should make these executable invariants.

1. A coordination update never changes accepted plan, hierarchy, authority, or work state by itself.
2. Every update is bound to a producer invocation and the invocation's plan/snapshot context.
3. A routed update cannot widen the recipient's scope/capabilities.
4. Material assignment changes supersede the old invocation; they are never delivered as mere context deltas.
5. Standup consensus cannot satisfy a review/verification/evidence gate.
6. Contradictory claims remain separately attributable until explicitly resolved.
7. An impact hold blocks forward actions in its scope but does not destroy underlying lifecycle state.
8. A held unit cannot integrate/publish unless explicitly permitted by a valid resolution path.
9. A Story/Epic replan uses existing ancestor-plan invalidation semantics; coordination does not mutate descendants silently.
10. Historical coordination updates cannot become current evidence merely because they were widely distributed.
11. Session destruction does not lose open blockers, contradictions, syncs, or impact holds.
12. Coordination artifacts cannot become a second source of project authority.
13. Raw hidden reasoning/transcripts are never required or persisted by the coordination protocol.
14. Routing and compaction never erase breakthrough, blocker, contradiction, or decision provenance.
15. A relevance hint is advisory only: it cannot route knowledge, alter state, create a hold, or establish that work is related or unrelated by itself.
16. Absence of a declared dependency or overlap hint never proves work is unaffected; uncertain impact scope is surfaced and handled conservatively.

---

## 23. Tests and adversarial scenarios

At minimum:

### Unit / state tests

- update attribution and hash binding;
- routing cannot widen scope;
- context delta versus assignment-change decision;
- impact classification and hold guards;
- sync close cannot mutate state except through referenced normal operations.

### Composition tests

- one agent publishes a breakthrough while siblings are active; siblings receive only relevant deltas;
- old invocation attempts to continue after Story replan -> rejected/superseded as required;
- held Ticket attempts integration -> refused;
- held Story contains unaffected sibling subtree -> only declared affected scope blocked;
- contradictory findings survive sync summarization;
- session destruction during open sync -> deterministic resume;
- Lead takeover during impact hold -> hold and obligations persist;
- stale coordination update cannot satisfy evidence gate;
- impact release without required replan/reconfirmation -> refused;
- context delta containing information that changes scope cannot be used to avoid re-dispatch;
- an update structurally overlaps an active invocation but the Lead did not initially route it -> relevance hint appears without automatically delivering or changing state;
- no declared dependency exists but file/symbol overlap is uncertain -> affected scope cannot be silently classified as unaffected.

### Adversarial walk additions

Later scheduler-era walk should mix:

- publish update;
- route update;
- block/unblock;
- sync open/respond/close;
- assumption invalidation;
- Ticket/Story/Epic replan;
- handoff/takeover;
- cancel/move/promote;
- crash/recovery with open coordination state.

---

## 24. Implementation staging

**Freeze status:** v0.1 is intentionally frozen as **Designed** after independent review. It should not be actively refined in parallel with M2 merely to anticipate hypothetical implementation details. This design should not expand the current M2 implementation scope.

Revisit this design when implementation evidence exists, especially after:

- M2 hierarchy, staleness, resume, and non-mutating semantics are accepted;
- M3 provides real live Lead/subagent invocations;
- at least one multi-agent research or code-mapping dogfood run exposes actual coordination behavior;
- a material change lands in resume, freshness, dependency, plan-binding, or invocation-supersession semantics; or
- implementation demonstrates a concrete contradiction or missing invariant in this document.

Reopening should be driven by observed behavior or a demonstrated contract conflict, not speculative refinement.

### M2 - hierarchy and non-mutating work

Provides the natural scope and parallel research substrate. No live coordination feature required.

### M3 - live harness

Provides real active Lead/subagent invocations. Coordination becomes implementable.

Recommended first post-M3 slice:

- durable coordination updates;
- bounded inbox/context deltas;
- manual Lead routing;
- manual Story/Ticket sync;
- resume rendering.

### M3.x / M4 - assumption invalidation and impact holds

Add:

- explicit impact assessment;
- holds;
- Story/Epic sync;
- assignment supersession integration;
- adversarial coordination tests.

This should precede aggressive autonomous parallel execution.

### M5 - scheduler integration

Scheduler may **suggest** or automatically open coordination checkpoints based on deterministic triggers such as:

- unresolved blocker;
- contradiction;
- several active agents under one Story;
- breakthrough with wider suggested impact;
- prolonged duplicate investigation;
- dependency becoming satisfied.

Automatic scheduling does not gain additional authority. The Lead remains the decision maker.

---

## 25. Relationship to AEW's existing contracts

This feature should be implemented as an extension of existing principles rather than a new authority model.

It reuses:

- bounded invocations;
- durable evidence;
- role/archetype authority ceilings;
- Lead-owned decisions;
- hierarchy and ancestor-plan staleness;
- resumable state;
- deterministic context packs;
- explicit dependency edges;
- review/verification separation.

The feature's purpose is to make those isolated bounded invocations behave like a team **without ceasing to be bounded invocations**.

### Load-bearing dependency: scope and overlap quality

Coordination can propagate a known impact safely only to the extent that AEW can identify work plausibly affected by it. Hierarchy and declared dependency edges remain authoritative inputs, but they are not guaranteed to expose undeclared file, symbol, runtime, or external-system overlap.

This design therefore depends on the broader AEW work/dependency/capability layers to improve overlap and relationship discovery over time. Until that discovery is strong enough, the safe fallback is conservative: known-unaffected work may continue, known-affected work is held/reassessed, and uncertain overlap is surfaced rather than silently treated as independent. This document does not define a second dependency graph.

---

## 26. Review focus

Independent review should attack the following questions:

1. Can coordination accidentally become a parallel authority channel?
2. Can an agent use a routed update to escape its launch-contract scope?
3. Can stale/old coordination knowledge satisfy a current evidence/gate requirement?
4. Can a Story/Epic breakthrough invalidate work without the Lead noticing?
5. Can an impact hold deadlock a project with no explicit recovery path?
6. Can an impact hold be bypassed through integration/reconcile/resume/handoff?
7. Does recontextualization preserve reproducibility of what an invocation actually knew?
8. Are materially changed assignments always re-dispatched rather than silently rewritten?
9. Can contradictory agents be accidentally summarized into false consensus?
10. Can coordination volume cause context blow-up that defeats bounded-context design?
11. Can session destruction or Lead takeover lose an open sync or invalidation obligation?
12. Can a malicious or mistaken agent spam high-impact claims and cause unsafe automatic state changes? (It must not; Lead assessment is required.)
13. Can Lead-only routing silently miss a structurally relevant update, and does the advisory relevance-hint path expose that possibility without becoming authority?
14. Can the system incorrectly preserve an "unaffected" subtree merely because technical overlap was undeclared or undiscovered?

---

## 27. Design summary

AEW should evolve from:

```text
structured isolated agents
```

into:

```text
structured bounded team
```

without giving up the properties that make AEW trustworthy.

The resulting model is:

```text
active agents
    |
    +-- publish structured coordination updates continuously
    |
    +-- surface non-authoritative relevance hints when structural overlap suggests under-routing
    |
    +-- receive bounded relevant deltas from other work after Lead routing
    |
    +-- converge through scoped Lead-facilitated syncs
    |
    +-- surface blockers and contradictions while they still matter
    |
    +-- escalate breakthroughs through assumption-impact assessment
            |
            +-- informational -> distribute
            +-- recontextualize -> bounded delta
            +-- Ticket replan -> supersede/re-dispatch
            +-- Story/Epic replan -> hold, sync, normal AEW replanning
            +-- project authority impact -> existing operator escalation
```

The key idea is simple:

> **Do not make agents wait until the end of expensive work to share what they learned. Do not let sharing what they learned bypass authority.**

That gives AEW a real collaborative execution model rather than a collection of sophisticated one-shot workers.
