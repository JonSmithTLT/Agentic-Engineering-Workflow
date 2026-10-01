# AEW Capability Discovery and Progressive Disclosure Design v0.1

**Status:** Proposed companion design  
**Scope:** Workbench Capability Contract / capability registry discovery, effective capability manifests, harness-native capabilities, and context-efficient lazy expansion  
**Implementation timing:** Post-M3 capability-registry work; does not expand current M3 scope  
**Authority:** This design does not create a new authority path. Capability discovery is descriptive; existing role grants, project policy, execution envelopes, and AEW control paths remain authoritative.

## 1. Purpose

AEW should let a Lead or worker understand what the engineering environment can do **without loading the full documentation and schemas for every installed capability into every model context**.

The capability system has three jobs:

1. **Discovery** — what can this environment do?
2. **Authorization** — what is this invocation allowed to do?
3. **Context economy** — what does this invocation actually need to know right now?

The explicit context goal is:

> **Advertise capabilities broadly; describe them narrowly; expand them only on demand.**

A role should know that a useful capability exists, what class of problem it solves, and how to request more detail without paying the context cost of the full provider manual until it is actually needed.

## 2. Motivation

Large MCP servers, utility suites, skills, and harness-native feature sets can consume a substantial fraction of an invocation's context merely by advertising everything they support.

This creates several problems:

- less context remains for project/source evidence;
- compaction occurs earlier;
- irrelevant tool descriptions create choice noise;
- weaker models must reason over many irrelevant operations;
- every invocation repeatedly pays for infrastructure documentation it may never use;
- adding capabilities makes the system progressively harder to use even when those capabilities are unrelated to the task.

AEW already requires bounded context and role-specific capability grants. Progressive disclosure makes those principles operational for the capability layer.

## 3. Capability model

The registry may describe multiple kinds of engineering capability:

```text
procedural
  skills / reusable engineering procedures

tool/service
  MCP servers
  local CLI utilities
  remote providers
  test/validation environments

harness-native
  sandboxing
  context compaction
  native review
  native orchestration
  subagent/workflow features
  session/resume features

AEW-native
  workflow/control operations exposed to the role
```

These are different implementation sources but participate in one discovery model.

The registry should not normalize providers to the lowest common denominator.

A harness-native capability may be used when it improves execution while remaining inside AEW authority and policy.

## 4. Available, authorized, and active are different

The system must distinguish:

```text
AVAILABLE
= this workbench/provider can supply the capability

AUTHORIZED
= role + project policy + execution envelope permit this invocation to use it

ACTIVE / RESOLVED
= a concrete healthy provider has been selected for this invocation
```

Discovery does not grant authority.

> **Discovery is not authority.**

A model learning that Ultracode, Codex native orchestration, Ghidra, or a remote validation provider exists does not gain permission to use it.

## 5. Effective Capability Manifest

The global registry may contain hundreds of entries.

An invocation receives a small **Effective Capability Manifest** derived from:

```text
global capability registry
        +
installed/healthy providers
        +
selected harness and adapter
        +
role/archetype grants
        +
project profile/policy
        +
work-unit/objective
        +
approved execution envelope
        ↓
effective capability manifest
```

The manifest should contain only capabilities relevant or plausibly useful to the bounded assignment.

Example:

```text
Role: Reviewer
Harness: Claude Code

Available to this invocation:

code-search
  Search source, symbols, and references.
  More: capability://code-search

binary-re
  Read-only binary analysis through approved RE provider.
  More: capability://binary-re

adversarial-review
  Procedural review guidance for composed-operation failures.
  More: skill://adversarial-review

native-parallel-review
  Bounded harness-native independent review is available.
  Constraints: max 3 children, depth 1, read-only.
  More: capability://native-parallel-review
```

The initial manifest should be small enough that adding a large MCP server does not materially consume task context unless the invocation chooses to use it.

## 6. Progressive disclosure levels

Capability information should be expandable in layers.

### L0 — Awareness

Answers:

```text
What broad capabilities exist for my task?
Why might I use them?
Where do I ask for more?
```

Example:

```text
binary-re
  Decompilation, xrefs, callers/callees, symbols.
  More: capability://binary-re
```

No full operation schemas.

### L1 — Capability detail

Answers:

```text
What is this capability good for?
What important limitations/authority boundaries apply?
Which operations or sub-capabilities exist?
```

Example:

```text
binary-re

Good for:
- function decompilation
- callers/callees
- references
- symbol search

Provider:
ghidra-mcp

Restrictions:
read-only
no project-state authority

Operations:
inspect-function
references
callers
callees
search-symbols
```

### L2 — Operation detail

Answers:

```text
What does this operation do?
When should I use it?
What are its important inputs/outputs?
```

Still avoid unrelated provider operations.

### L3 — Exact invocation schema

Only when the operation is actually selected does AEW expose the exact schema/tool contract required to invoke it correctly.

```text
capability schema binary-re.references
```

The exact syntax is not frozen in this design.

## 7. Harness-native capabilities

Harness adapters participate in the capability registry.

An adapter should advertise capabilities such as:

```text
sandbox
context-compaction
native-orchestration
native-review
native-subagents
session-resume
workspace-isolation
```

with enough metadata for AEW to decide how they may be used.

AEW combines provider support with policy and role authority.

Harness-neutrality therefore means:

> **portable engineering semantics with capability-aware execution backends**

not:

> disable every feature that another harness lacks.

## 8. Harness-native orchestration boundary

Harness-native child agents/workflows may be useful execution machinery without becoming independent AEW workers.

Example:

```text
AEW Reviewer invocation INV-17
        │
        └── bounded native review workflow
             ├── helper A
             ├── helper B
             └── helper C
```

Unless AEW explicitly creates separate authority-bearing invocations, those helpers:

- receive no independent AEW identity/authority;
- receive no independent AEW credentials;
- cannot transition project state;
- cannot independently satisfy AEW gates;
- cannot grant capabilities;
- cannot independently prompt the stakeholder;
- cannot outlive the parent invocation's authority boundary;
- return results attributable to the parent invocation.

Native orchestration increases execution power.

It does not implicitly increase AEW authority.

## 9. Skills and abstract capability requirements

Skills should prefer abstract capability needs over concrete provider names where practical.

Example:

```text
Adversarial-review skill:

For binary-backed claims, use an available
reverse-engineering capability to confirm
call/reference behavior.
```

AEW may resolve that requirement to Ghidra MCP, another RE provider, or a future harness-native capability.

A skill may also conditionally exploit a capability:

```text
If bounded native parallel review is authorized,
consider independent specialist passes.

Otherwise perform the passes sequentially
or request Lead-managed parallel review.
```

## 10. Lead planning surface

The Lead usually needs capability topology rather than full operation schemas.

Example:

```text
Investigation
- repository search
- source graph
- binary reverse engineering

Execution
- C/C++ build/test
- Python
- shell

Review
- adversarial-review skill
- bounded native parallel review

Infrastructure
- Codex sandbox
- Ghidra MCP
- remote Rocky validation
```

This is enough to plan work.

Workers receive more detailed manifests only for their bounded assignments.

## 11. Context-pack integration

Capability disclosure is part of bounded context construction.

Conceptually:

```text
Lead
  receives high-level capability topology

Worker
  receives role/task-specific Effective Capability Manifest

Worker selects capability
  receives capability detail

Worker selects operation
  receives exact operation schema
```

The context pack should not automatically contain the complete global registry or complete tool schemas.

## 12. Deterministic reconstruction and provenance

AEW should be able to reconstruct what capability knowledge an invocation actually had.

Record references/hashes to items such as:

```text
effective capability manifest version/hash
capability summaries exposed
operation schemas expanded
skill versions exposed
provider identity/version
relevant adapter feature flags
```

This need not mean storing duplicate manuals in every invocation record.

Stable references and content hashes are preferred.

## 13. Context-economy acceptance criteria

The implementation should demonstrate that capability growth does not force proportional baseline-context growth.

Representative evaluation:

```text
Workbench A:
10 capabilities

Workbench B:
100 capabilities including a large MCP server

Task:
localized source review not requiring that MCP server
```

Expected:

- initial effective-manifest context remains approximately task/role proportional;
- full MCP schemas are not injected;
- the model can discover that the MCP capability exists if relevant;
- selecting the capability exposes progressively more detail;
- exact tool schemas appear only when selected/needed.

For a task that genuinely requires the MCP server:

- the model can discover it from the summary;
- navigate to useful operations;
- obtain the exact schema;
- invoke it without requiring the full provider manual in initial context.

## 14. Choice-noise goal

This design is not only about token count.

Large flat tool surfaces create decision noise.

AEW should prefer:

```text
small semantic capability categories
        ↓
selected capability
        ↓
small operation set
        ↓
exact schema
```

over:

```text
dozens/hundreds of unrelated operations
presented simultaneously
```

Target-model evaluation should test both context/token cost and task performance.

## 15. Failure classes

Candidate classes:

- `CAPABILITY_CONTEXT_BLOAT`
- `CAPABILITY_DISCOVERY_FAILURE`
- `CAPABILITY_AUTHORITY_CONFUSION`
- `CAPABILITY_SCHEMA_OVEREXPOSURE`
- `HARNESS_FEATURE_SUPPRESSION`
- `HARNESS_AUTHORITY_LEAK`

These should be reconciled with the canonical failure-class registry before implementation.

## 16. Invariants

```text
Discovery is not authority.

The global registry is not the invocation manifest.

Roles receive an effective capability view, not the entire workbench manual.

Advertise capabilities broadly; describe them narrowly; expand them only on demand.

Exact operation schemas are lazy-loaded when selected/needed.

Capability expansion must not silently widen role authority.

Harness-native features may increase execution power but never implicitly increase AEW authority.

Skills may request abstract capability classes without hard-coding a provider.

Capability/provider details used by an invocation are reconstructible by reference/hash.

Adding unrelated capabilities should not linearly inflate baseline invocation context.
```

## 17. Relationship to existing AEW design

This design extends the existing Workbench Capability Contract direction.

Existing AEW design already establishes:

- a workbench capability registry;
- human-readable capability manifests;
- role/profile capability grants;
- provider health/resolution;
- role-specific capabilities rather than the entire workbench inventory.

This companion design makes two goals explicit:

1. **progressive capability disclosure is a context-management requirement**, not merely UI convenience;
2. **harness-native features are capability providers** that should be safely exploited rather than globally disabled for portability.

It does not change existing AEW workflow authority.

## 18. Implementation sequencing

Do not expand M3 to implement this entire design.

Recommended sequencing:

```text
finish/accept M3
    ↓
stabilize capability registry/contract
    ↓
add Effective Capability Manifest
    ↓
add lazy capability/operation/schema expansion
    ↓
teach adapters to advertise harness-native capabilities
    ↓
Codex adapter uses the same contract
    ↓
evaluate capability context cost and task performance
```

## 19. Summary

AEW should let an invocation know:

```text
what it can do
what it is allowed to do
why a capability might help
where to learn more
```

without forcing it to preload:

```text
everything every installed tool, MCP server,
skill, utility, and harness feature can possibly do.
```

> **Know that it exists. Know why it matters. Know where to expand it. Pay for the full manual only when you need it.**
