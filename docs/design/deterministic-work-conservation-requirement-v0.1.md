# AEW Deterministic Work Conservation Requirement v0.1

**Status:** **Adopted** by the operator, 2026-10-09; the [knowledge system adoption decision](decisions-2026-10-09-knowledge-system-adoption.md) of the same day (§6) cites it as adopted. Until then this line read "Draft requirement for operator adoption". The text below is unchanged  
**Type:** Product / system north-star requirement  
**Applies to:** AEW as a whole  
**Primary concern:** Reduce unnecessary model inference, tool ceremony, repeated discovery, and frontier-model usage without weakening correctness, authority, provenance, or recoverability  
**Related work:** T5 project maps, F15 stage/action surface, F9 coordination, F21 knowledge/recall, F25 usage ledger, M5 scheduler, capability registry

---

## 1. BLUF

AEW already exists to keep engineering workflows controlled, consistent, recoverable, attributable, and correct.

The next foundational requirement is:

> **If AEW can answer a question, derive a fact, select a tool, route information, or perform a workflow action deterministically and safely without model inference, AEW should prefer to do so rather than require an LLM to rediscover or reproduce that work.**

Model reasoning is a scarce resource.

AEW should preserve it for work that actually requires judgment, synthesis, ambiguity resolution, planning, interpretation, or novel reasoning.

The platform should do everything else it can prove how to do reliably.

---

## 2. Product objective

AEW should maximize the fraction of model effort spent on the engineering problem itself.

A model should not routinely spend reasoning capacity on:

- rediscovering repository structure;
- locating source, tests, mocks, fixtures, or configuration that AEW can index;
- repeatedly searching for known symbols or relationships;
- reconstructing workflow state that AEW already owns;
- deciding which mechanically runnable action comes next;
- choosing among tools when AEW can resolve the appropriate capability;
- rediscovering durable findings already produced by other workers;
- reconstructing prior project knowledge that AEW can retrieve directly;
- repeating deterministic impact analysis;
- polling or waiting for state changes that AEW can observe itself.

The desired division is:

```text
AEW
    deterministic facts
    deterministic navigation
    deterministic retrieval
    deterministic routing
    deterministic workflow mechanics
    deterministic capability resolution
    deterministic scheduling/admission
    deterministic derived context
             ↓
          model
    judgment
    planning
    interpretation
    synthesis
    exception handling
    novel reasoning
```

The system should make model intelligence more useful by removing work that does not require intelligence.

---

## 3. Core requirement

### DWC-1 — Deterministic-first resolution

Before asking a model to perform reasoning or exploratory tool use for a problem, AEW SHOULD determine whether the requested result can be produced from trusted deterministic inputs and qualified deterministic capabilities.

When an adequate deterministic answer is available, AEW SHOULD provide that answer directly or expose it through a typed capability.

A model MAY still inspect underlying source or evidence when needed.

Deterministic assistance does not replace source truth, evidence, review, verification, or model judgment where those are required.

---

## 4. Inference is an escalation, not the default

The preferred resolution order is:

```text
1. exact deterministic fact
2. deterministic derived fact / locator
3. bounded deterministic relationship or impact query
4. qualified search/index fallback
5. bounded model-assisted synthesis
6. broader investigation
7. judgment
```

AEW should not invoke a more expensive layer merely because it exists.

If a lower layer produces a complete and sufficiently qualified answer, stop there.

If a lower layer is stale, partial, unsupported, ambiguous, or insufficient, escalate explicitly.

---

## 5. Repository navigation is the flagship requirement

Repository orientation is a primary application of this requirement.

For ordinary bounded work, an LLM should not need to rediscover the repository through repeated shell exploration.

Questions such as:

```text
Where is this implemented?
Where are the tests?
Where are the mocks or fixtures?
Which module owns this symbol?
What files are likely related?
What constraints apply here?
What changed in this worker's workspace?
What else may be affected by this edit?
```

are often answerable from deterministic repository state, project maps, semantic indexes, Git state, test relationships, constraint locators, or qualified search tools.

AEW SHOULD make those answers available directly.

The target worker experience is:

```text
Ticket
  ↓
AEW supplies bounded orientation
  ↓
worker reaches relevant source
  ↓
worker performs task-specific reasoning
```

not:

```text
Ticket
  ↓
pwd
ls
find
grep
rg
open unrelated files
find tests
find mocks
reconstruct structure
  ↓
eventually begin the task
```

---

## 6. Repository navigation target

For ordinary bounded Tickets:

> **A worker should normally reach task-relevant source without performing repository-wide exploratory filesystem search.**

Repository-wide `find`, `grep`, `rg`, recursive directory traversal, or equivalent discovery should be a fallback path, not the standard initialization ritual of every invocation.

This is an optimization target, not an immediate correctness gate.

The platform should measure whether it is being achieved.

---

## 7. Typed intent over shell ceremony

Models SHOULD be able to ask for intent-level operations such as:

```text
repo.locate("mock harness")
repo.symbol("HarnessAdapter.send")
repo.tests_for("src/aew/engine/harness_ops.py")
repo.impact(<changed set>)
repo.constraints("harness messaging")
repo.search("credential_exposed")
```

The model should not need to know which concrete backend implements the request.

The capability layer may resolve the operation through:

- project maps;
- semantic indexes;
- language servers;
- Git;
- deterministic relationship indexes;
- ripgrep;
- other qualified providers.

The model asks the engineering question.

AEW chooses the qualified mechanism.

---

## 8. Workspace-bounded search

When AEW does fall back to search, search scope SHOULD be structurally bounded to the invocation's authorized project/workspace scope by default.

A worker should not need to correctly construct repository roots or shell paths merely to search its own assignment.

This reduces:

- accidental traversal outside the project;
- unbounded `find` operations;
- searches across unrelated corporate trees;
- unnecessary tool latency;
- context pollution;
- dependence on model shell skill.

Explicit expansion outside the normal workspace remains a separate capability/policy decision.

---

## 9. Deterministic change-impact assistance

Repository orientation alone is insufficient.

After a worker changes code, AEW SHOULD make a bounded deterministic impact view available when qualified data exists.

Potential impact surfaces include:

```text
changed files / symbols
related modules
direct dependents
implementations
tests
mocks / fixtures
schemas
configuration
constraints / invariants
generated/public surfaces
```

The impact view is advisory unless an existing authority contract says otherwise.

It does not prove that every related item requires modification.

It exists so a model does not silently omit related surfaces merely because it did not know they existed.

---

## 10. Do not duplicate deterministic knowledge across agents

When several agents operate on the same project, stable project facts SHOULD be computed once and reused where safely applicable.

AEW should avoid paying repeatedly for independent discovery of:

- repository structure;
- entry points;
- test locations;
- build system;
- project constraints;
- dependency relationships;
- already-established findings;
- current workflow state;
- known execution capabilities.

Parallel model execution should multiply useful engineering work, not multiply rediscovery of the same foundational facts.

---

## 11. Workflow ceremony is the same problem

Deterministic work conservation applies beyond repository search.

If AEW can determine that:

- a Ticket is runnable;
- a dependency is satisfied;
- a review may be requested;
- a verifier should be launched;
- an integration queue entry is mechanically ready;
- a stage transition is legal;
- worker capacity exists;
- a budget permits another worker;
- a known event should wake a waiting process;

then a model should not be required to spend a reasoning turn reproducing that determination.

F15 and M5 are examples of this requirement applied to workflow mechanics.

---

## 12. Coordination is the same problem

If one worker has already established a relevant finding, another worker should not have to rediscover it merely because the workers are isolated.

AEW SHOULD route or make available bounded relevant findings through the approved coordination path when the expected value justifies doing so.

F9 is an application of deterministic work conservation to multi-agent coordination.

Coordination still does not become authority.

---

## 13. Knowledge recall is the same problem

If AEW has durable, qualified prior knowledge that directly applies to a current task, the model should not have to independently rediscover the same lesson.

AEW SHOULD retrieve bounded relevant prior knowledge when doing so is safe, measurable, and does not displace more important current authority/source context.

F21 and the knowledge system are applications of this requirement to repeated engineering experience.

---

## 14. Capability selection is the same problem

A model should not need to reason extensively about which installed tool, MCP server, CLI, provider, or harness feature should answer a common structured request.

Where AEW has qualified capability metadata, the platform SHOULD resolve intent to the cheapest adequate authorized capability.

The model should reason about the engineering problem, not the plumbing.

---

## 15. Preserve authority and truth

Deterministic work conservation MUST NOT weaken existing AEW guarantees.

Specifically:

1. Derived answers do not become authority merely because they are deterministic.
2. Source remains source truth.
3. Evidence requirements remain evidence requirements.
4. Review and verification remain separate where required.
5. Stale, partial, unsupported, or ambiguous derived data must remain visibly qualified.
6. Absence from a map/index does not prove absence when coverage is incomplete.
7. Deterministic routing may not widen role, Ticket, filesystem, network, or workflow authority.
8. A deterministic system may not manufacture judgment.
9. Mechanical automation may not silently cross a Lead/operator decision boundary.
10. Model inspection of underlying evidence remains available when consequential judgment requires it.

Correctness and authority take precedence over cost reduction.

---

## 16. Deterministic work must earn trust

AEW SHOULD prefer deterministic machinery only when its behavior is:

- bounded;
- reproducible where appropriate;
- provenance-aware;
- source/revision bound where required;
- freshness-aware;
- qualified for the current environment;
- failure-explicit;
- measurably more useful than asking the model to reproduce the same work.

A bad deterministic answer is not an optimization.

When AEW cannot answer confidently enough, it should expose the limitation and escalate.

---

## 17. Cost is broader than dollars

The requirement treats all of the following as costs:

```text
model input tokens
model output/reasoning tokens
frontier-model quota
rate-limit capacity
tool calls
wall-clock time
duplicate investigation
context-window consumption
worker stalls
retries
rework
operator attention
unnecessary model invocations
```

A feature may therefore be valuable even if provider-dollar savings are small.

Preserving scarce frontier-model capacity is itself a major objective.

---

## 18. Frontier-model conservation

AEW SHOULD preferentially preserve frontier-tier model effort for:

- decomposition;
- architecture;
- premise validation;
- difficult interpretation;
- high-consequence judgment;
- cross-work synthesis;
- selective supervision;
- exception handling;
- replanning;
- work that cannot be economically decomposed.

Frontier-model effort SHOULD NOT routinely be consumed by deterministic repository discovery, workflow choreography, polling, capability selection, or repeated retrieval of facts AEW already knows.

---

## 19. Heterogeneous-worker objective

Deterministic work conservation supports AEW's intended heterogeneous execution model.

The platform should enable:

```text
frontier Lead
    +
lower-cost bounded workers
    +
middle-tier workers
    +
frontier specialists when necessary
```

by reducing how much repository/tool/workflow competence every subordinate model must independently possess.

A weaker model does not need to become a frontier model.

AEW should remove avoidable work so the weaker model can spend more of its limited reasoning capacity on the bounded engineering assignment.

---

## 20. Success condition for repository tooling

Project-map and repository-navigation work should be considered successful when even a frontier-tier model rationally prefers AEW's navigation/query surfaces over repeated manual shell search for ordinary repository questions.

The goal is not merely:

> "weaker models can use the map."

The stronger target is:

> **AEW's repository tooling is faster, safer, more complete, and more convenient than several ad hoc `rg`/`find`/`grep` operations for supported questions.**

Manual search remains available as an escape hatch and discovery fallback.

---

## 21. Required evaluation metrics

AEW SHOULD measure deterministic work conservation rather than assume it.

For repository/navigation work, useful metrics include:

```text
tool calls before first relevant source access
tokens before first relevant source access
tokens before first meaningful edit/finding
wall time spent on orientation
repo-wide searches per Ticket
irrelevant files opened
fallback-to-search rate
missed related files
missed tests/mocks/fixtures
impact-query usefulness
correctly accepted outcome rate
```

For workflow and orchestration:

```text
Lead turns spent on mechanical progression
manual stage commands per Ticket
wait/poll operations
scheduler decisions requiring no judgment
frontier-model tokens spent on workflow ceremony
```

For multi-agent work:

```text
duplicate discovery rate
repeated repository-orientation work
cross-worker finding reuse
corrections without redispatch
frontier-model supervision tokens
```

F25 should provide the usage/cost substrate where applicable.

---

## 22. Primary derived metric

AEW should attempt to estimate a **useful-reasoning ratio**:

```text
task-specific model effort
--------------------------
total model effort
```

This does not need to be perfectly measurable to be useful.

Proxy measures may include navigation calls, mechanical workflow turns, duplicate discovery, rework, and time-to-first-relevant-action.

The desired trend is upward.

---

## 23. Design review question

Every significant future AEW feature or workflow should be reviewed against the following question:

> **Is the model being asked to do something AEW could safely and deterministically do itself?**

If yes, the design should at least evaluate moving that work into the platform.

This is an evaluation requirement, not an unconditional automation mandate.

The answer may still be "leave it to the model" when:

- deterministic implementation would be brittle;
- coverage is insufficient;
- inference is cheaper than maintaining the machinery;
- the result requires judgment;
- the deterministic path would weaken authority/provenance;
- empirical evaluation shows no meaningful benefit.

But the question must be asked.

---

## 24. Non-goals

This requirement does not require AEW to:

- deterministically solve every engineering question;
- eliminate shell access;
- eliminate `rg`, `grep`, or `find`;
- replace model judgment with heuristics;
- build indexes for facts nobody needs;
- precompute every possible code relationship;
- optimize cost at the expense of correctness;
- hide uncertainty from the model;
- force automatic context injection when on-demand query is cheaper;
- use one fixed implementation for navigation or search;
- prevent expert models from inspecting raw source or using manual tools when useful.

The requirement is **deterministic-first**, not **deterministic-only**.

---

## 25. Relationship to current AEW work

This requirement is cross-cutting.

### T5 — project maps

Primary owner for deterministic repository orientation, locators, semantic relationships, test/constraint indexes, and impact assistance.

### F15 / M5 — stage actions and scheduler

Primary owners for removing workflow choreography and mechanically advancing legal work.

### F9 — coordination

Primary owner for avoiding duplicate discovery and enabling targeted reuse of worker findings.

### F21 / knowledge system

Primary owner for avoiding rediscovery of useful prior project experience.

### Capability registry

Primary owner for resolving intent to qualified tools/providers without requiring models to understand plumbing.

### F25 — usage/cost ledger

Primary measurement substrate for whether deterministic work conservation actually reduces model usage, time, and expensive-model dependence.

No one subsystem owns the requirement itself.

---

## 26. North-star statement

AEW's first foundation is:

> **Make engineering work controlled, attributable, recoverable, and correct.**

Its second foundation should be:

> **Do not spend model intelligence on work the platform can already solve.**

Together:

> **AEW should preserve model reasoning for the parts of engineering that actually require reasoning, while deterministically handling everything else it can prove how to handle safely.**

The intended result is not merely lower token cost.

The intended result is a more capable engineering system:

```text
better deterministic context
+ less ceremony
+ less rediscovery
+ better routing
+ stronger supervision
+ more model effort spent on actual engineering
=
higher effective system intelligence
```

That is the north star.
