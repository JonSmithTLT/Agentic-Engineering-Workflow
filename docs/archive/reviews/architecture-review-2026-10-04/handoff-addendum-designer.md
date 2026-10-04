# Addendum to HANDOFF — two additional research/design threads and triage request

Received from the operator (relaying the designer) on 2026-10-04, after T1 and T3 were accepted at the design-authority level. Saved verbatim so a later session has it on disk. The review's response is `TRIAGE.md` in this directory.

---

We have now substantially resolved T1 (Typed Lead surface) and T3 (Transaction outbox) at the design-authority level.

* T1 is frozen as a design candidate with the semantic action/stage contract below transport, MCP as the first normal Lead transport, CLI as parity/recovery/conformance, broker-held credential custody, and harness-specific capability allowed above the semantic boundary.
* T3 / ADR-0012 is likewise converging around the existing transition log as the complete consumable outbox, not a second authority/store.

Do not reopen those architectural decisions unless new external evidence demonstrates a concrete contradiction.
The remaining handoff threads are currently:

* T2 Evaluation component
* T4 Knowledge storage placement
* T5 Project maps
* T6 Network containment
* T7 Re-freeze / amendment index
* T8 Remote integration target

Add the following two threads:

## T9 — Harness-native integration strategy

### Objective
Determine how deeply AEW should integrate with the first supported coding harnesses, initially OpenCode and Codex, while preserving the frozen AEW boundary:
AEW owns engineering workflow and authority. Harnesses are replaceable execution infrastructure. Harness-neutral means semantic portability, not lowest-common-denominator behavior.
The question is not whether OpenCode or Codex should own workflow. They should not.
The question is:
Given the frozen typed AEW action surface, what native capabilities of each harness should AEW exploit because they improve execution, UX, context efficiency, containment, observability, or reliability without creating a second authority path?

### Research
Use current primary documentation, protocol/schema material, and live/probe evidence where practical. Current behavior matters; do not rely on remembered capabilities where the products have changed.
For OpenCode and Codex, investigate at least:

* MCP/tool registration and discovery;
* deferred/progressive tool disclosure or filtering;
* structured tool results;
* session creation, persistence, attach/resume and lifecycle;
* hooks/event streams/callbacks;
* native sandbox and permission systems;
* approval modes and operator interaction;
* model/provider selection;
* reasoning/effort controls;
* skills/instructions/project-guidance mechanisms;
* context injection and context-budget controls;
* subagents/tasks/delegation primitives;
* native planning/work modes;
* filesystem/edit APIs;
* shell/tool execution;
* process lifecycle;
* streaming and long-running calls;
* cancellation/interruption;
* structured output support;
* logging/telemetry;
* configuration scoping: global/project/session;
* environment/credential handling;
* capability probing/version negotiation;
* extension/plugin systems;
* native UI affordances AEW could surface through rather than recreate.

For each capability determine:

1. Is it documented/stable, undocumented, experimental, or version-sensitive?
2. Does AEW gain meaningful value by using it?
3. Is it merely transport/execution power, or could it accidentally become workflow authority?
4. Can it be represented in the planned harness capability registry?
5. What is the semantic fallback on a harness that lacks it?
6. Does using it alter custody, provenance, containment, or recovery?
7. Does it require a live compatibility probe?

### Important architectural constraints
Do not redesign T1.
In particular:

* AEW actions/stages remain defined below transport.
* MCP may be the first normal Lead transport.
* Engine legality remains authoritative.
* Harness-native approval/workflow state does not become AEW workflow state.
* Native sandboxing may strengthen containment but does not silently replace AEW's declared containment semantics.
* Native memory/session restoration does not replace AEW recovery/context authority.
* Native subagent systems must not reintroduce uncontrolled recursive delegation.
* Harness-native model/provider controls may be used only through attributable AEW execution selection semantics.

We explicitly want harness-specific advantages where safe. Do not recommend disabling a useful Codex/OpenCode feature simply because another harness lacks it.

### Deliverable
Produce a design/research note containing:

A. Capability matrix

```
capability
OpenCode support
Codex support
stability/version evidence
AEW value
authority/security risk
proposed AEW capability-registry representation
generic fallback
live probe required?
recommendation
```

B. Recommended integration profile. For each harness:

```
MUST USE
SHOULD USE
OPTIONAL
DELIBERATELY DO NOT USE
NEEDS LIVE PROBE
```

C. Adapter implications. Identify any genuine leakage or missing abstraction in:

* HarnessAdapter
* LaunchContract
* typed Lead/MCP surface
* containment
* session lifecycle
* capability registry

Do not redesign these preemptively. Name the exact seam and evidence.

D. Initial support target. Define what "AEW supports OpenCode/Codex" should mean for the first real support level:

* minimum conformance;
* optional enhanced capabilities;
* degraded-but-correct behavior;
* version/protocol compatibility;
* live smoke requirements.

## T10 — Installation, bootstrap, and integration UX

### Objective
Research modern developer-tool / coding-agent onboarding and design what AEW's installation and first-run experience should become.
AEW has spent substantial effort making its internal authority model rigorous. Do not let installation/configuration turn into:

```
install package
edit several YAML files
manually copy harness JSON
export several environment variables
guess test commands
launch separate services
debug an undocumented mismatch
```

The desired direction is closer to:

```
install AEW
    ↓
aew init
    ↓
inspect repository + available harnesses
    ↓
propose configuration
    ↓
operator approves
    ↓
generate isolated integration artifacts
    ↓
aew doctor
    ↓
launch chosen harness
    ↓
first useful Ticket
```

Research current good UX from relevant modern coding agents, developer CLIs and local engineering platforms. Focus on concrete workflows rather than visual polish.

### Investigate
Installation

* package/wheel/binary/install-script patterns;
* version pinning;
* signed artifacts;
* reproducible/offline packages;
* dependency checks;
* upgrades and downgrade behavior;
* migration UX;
* uninstall/cleanup;
* multiple AEW versions/projects if relevant.

Project bootstrap

* repository discovery;
* language/build-system detection;
* test-command discovery;
* source/generated/vendor directory detection;
* harness discovery;
* existing project configuration;
* proposed versus automatically applied settings;
* initial project map generation where appropriate;
* safe defaults;
* noninteractive/CI setup.

Harness integration. Determine the safest ownership model for generated integration configuration:

* AEW-owned project fragment;
* generated include;
* wrapper config;
* patching user configuration;
* global config;
* per-session generated config.

Prefer isolated and inspectable ownership. AEW should not silently seize ownership of a developer's global OpenCode/Codex configuration.
Study:

* installation of MCP/tool configuration;
* version/capability checks;
* conflict detection;
* preserving user customizations;
* removal/rollback;
* regeneration when AEW or a harness changes.

`aew doctor`. Define what doctor should verify before the first real run:

* supported OS/kernel;
* Python/runtime;
* filesystem;
* Git;
* harness version;
* required protocol shape;
* containment capability;
* credentials/gateway reachability without printing secrets;
* build/test configuration;
* AEW project/schema version;
* stale generated integration config;
* offline dependency completeness;
* permissions/account layout where relevant.

Separate:

```
ERROR — cannot safely operate
WARN — degraded capability
INFO — optional enhancement unavailable
```

First-run UX. Design the shortest safe path from install to a successful AEW-controlled engineering operation.
Identify:

* what the operator must explicitly decide;
* what AEW can derive;
* what AEW should merely propose;
* what can happen automatically;
* when a restart/relaunch is necessary;
* how failures explain exactly what remains to be fixed.

Connected vs air-gapped deployment. Treat these as equally real modes:

Connected developer environment

* conventional package/update experience;
* direct harness installation where appropriate;
* normal provider/gateway setup.

Rocky 8 / air-gapped deployment

* prebuilt wheelhouse / release bundle;
* all required runtime assets;
* image/archive import where applicable;
* signed/checksummed manifest;
* no hidden network fetches;
* deterministic preflight;
* upgrade/migration bundle;
* rollback path;
* doctor capable of proving the bundle is complete.

Offline operation is not a secondary degraded mode.

### Deliverable
Produce:

1. A short comparative survey of strong onboarding/integration patterns worth borrowing.
2. An AEW proposed install → init → doctor → harness-launch workflow.
3. A configuration-ownership model.
4. Connected and air-gap installation profiles.
5. Upgrade/migration/rollback workflow.
6. First-run failure/recovery UX.
7. Which parts belong in F18/bootstrap, harness adapters, `aew init`, `aew doctor`, packaging/release work, or later UI.
8. Explicit non-goals so this does not become an installer platform project.

## Triage all eight remaining threads

Before performing eight equal deep dives, reassess the current queue:

```
T2  Evaluation component
T4  Knowledge storage placement
T5  Project maps
T6  Network containment
T7  Re-freeze / amendment index
T8  Remote integration target
T9  Harness-native integration strategy
T10 Installation/bootstrap/integration UX
```

You are encouraged to change their execution order based on what you discover.
For each thread classify:

```
DEEP DESIGN NOW
TARGETED RESEARCH / LIVE PROBE
BOUNDED DESIGN
GOVERNANCE CLEANUP
WAIT FOR DEPENDENCY
DEFER
```

Rank using:

* dependency pressure on current M4 work;
* probability that getting it wrong creates architectural rework;
* amount of genuine external uncertainty;
* empirical evidence already available;
* leverage across later milestones;
* whether the answer is needed before implementation begins;
* whether a live probe is more informative than more design prose.

Do not turn the architecture review into an obligation to build every idea it found.
For each thread state:

```
why now / why not now
exact uncertainty remaining
expected artifact
blocker it clears
cheapest way to answer it
stop condition
```

Then recommend the next 2–4 pieces of work, not eight simultaneous efforts.

## Evidence and design discipline
Prefer current primary documentation, source/schema evidence, and reproducible probes.
Clearly separate:

* documented fact;
* observed/probed fact;
* architectural inference;
* recommendation;
* unresolved hypothesis.

A research finding does not become governing AEW design merely because it is persuasive. Produce research/design candidates for review by the design authority and operator.
Do not silently reopen accepted authority, custody, DispatchDecision, ADR-0011, ADR-0012, or T1 semantics.
Challenge them only if new evidence demonstrates a concrete contradiction.
The goal is not more documentation. The goal is to eliminate uncertainty cheaply enough that the next implementation Tickets are based on stable architecture.
