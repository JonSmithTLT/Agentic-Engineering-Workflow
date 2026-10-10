# AEW M6a Capability and Effect Authorization Model v0.8 — Gate A Closure Candidate

**Date:** 2026-10-10  
**Status:** Designer candidate for **Gate A machine-policy closure** — **not yet governing**  
**Supersedes:** `AEW_M6a_Capability_and_Effect_Authorization_Model_v0.7.md`  
**In this repository (ingested 2026-10-10):** a designer candidate, not yet governing; concept frozen at v0.9. The [v0.9 Gate A encoding candidate](m6a-authorization-model-v0.9-gate-a-encoding-candidate.md) overlays this text for Gate A encoding details: where they differ, v0.9 controls (requirements ledger: this document is CEA, v0.9 is GAE; register F38 to F40). v0.7, v0.6 and the Canonical Capability Inventory v0.1 to v0.5 that it supersedes were never in this repository. The text below is unchanged  
**Scope:** M6a semantic discovery, provider qualification, deterministic principal attribution, closed legal effects, implication closure, grant derivation, role/profile admission, selector coverage, operation-level closure, and the policy/deployment proof boundary.

---

# 1. Permanent split: policy closure versus deployment enforcement

AEW keeps two independent acceptance gates.

## Gate A — machine-policy closure

Gate A proves:

1. status is total with default `ILLEGAL`;
2. principal attribution is deterministic;
3. every shipped operation expands to legal effects;
4. implication closure is complete;
5. every grantable tuple has exactly one canonical family;
6. families and role-table rows are bijective;
7. every legal tuple has an explicit selector schema;
8. target/destination classes are operator-pinned;
9. combination predicates are satisfiable by admitted profiles;
10. operation/profile expansion cannot widen authority.

Passing Gate A permits the claim:

> **The M6a authorization policy is internally consistent, closed, and machine-checkable.**

## Gate B — deployed bypass-freedom

Gate B separately proves:

1. every model-reachable effect has a real enforcement owner;
2. mediator/containment coverage is complete;
3. no alternate harness/provider path bypasses policy;
4. resource aliases cannot bypass class separation;
5. project-authored code cannot borrow parent authority;
6. escape surfaces are absent or fully modeled;
7. adversarial fixtures pass against the pinned real deployment.

Passing Gate B permits the claim:

> **The qualified deployment enforces the closed M6a policy without a known bypass path.**

Gate A does not imply Gate B.

---

# 2. Scope boundary

M6a governs **engineering/workbench capabilities** and their effects.

It does **not** replace the existing Lead/operator workflow command authority model.

Examples outside the M6a capability registry:

```text
ticket creation
plan acceptance
workflow transition approval
project close
operator lifecycle controls
```

Those are governed through the existing typed AEW control-plane authority/custody model.

Invariant:

> **No capability/provider projection may reach generic project-control mutation.**

Therefore:

```text
MODEL write(project_control_state)
    -> UNASSIGNABLE within M6a
```

while specific Lead/operator workflow commands remain governed control-plane operations outside this capability taxonomy.

Permanent fixture:

```text
capability_cannot_reach_control_plane
```

The Gate A claim is therefore:

> every **M6a-governed model-attributable engineering effect** has one legal home.

---

# 3. Semantic labels remain non-authoritative

Labels and operations remain planning/presentation surfaces only.

Examples:

```text
repository_exploration
symbol_navigation
test_intelligence
binary_re
remote_validation
```

and:

```text
map.find
map.symbol
check.run
knowledge.search
evidence.show
```

Authority derives from the resolved operation projection's effects, not label names.

---

# 4. Principals

```text
MODEL
PROVIDER_INFRA
EXECUTION_CONTROL
EVALUATOR
```

Harness infrastructure is represented as qualified `PROVIDER_INFRA` through the pinned harness-adapter projection.

The status function is:

```text
status(
    principal,
    action,
    target_class=None,
    destination_class=None
)
```

and returns exactly one of:

```text
GRANTABLE(family)
PROVIDER_INFRA_ONLY
EXECUTION_CONTROL_ONLY
EVALUATOR_ONLY
UNASSIGNABLE
ILLEGAL
```

Anything not enumerated is `ILLEGAL`.

Uninstantiated portable vocabulary is also `ILLEGAL` at admission.

---

# 5. Deterministic attribution

Attribution is derived from projection metadata.

Each parameter slot declares whether it influences:

```text
argv
resource_path
target_identity
destination
content_selection
code_loading
```

Missing metadata defaults toward `MODEL`.

## 5.1 Information-flow floor

Any read whose returned information is visible to the model is always:

```text
principal = MODEL
```

regardless of whether the underlying provider command is fixed.

Examples:

```text
T5 query returning map rows
rg returning source matches
Git history returning commit data
evidence.show
knowledge.search
remote log retrieval
```

The provider process may have its own `PROVIDER_INFRA` implementation effects, but the information-flow effect delivered to the model remains a `MODEL read(...)`.

This fixes the read-attribution hole.

## 5.2 Execution attribution floors

When a model-requested operation causes the following, they remain model-attributed even with fixed argv:

```text
MODEL execute_project_code(...)
MODEL execute_tool(hostile_analysis_runtime)
MODEL debug_attach(process_state)
MODEL process_control(process_state)
```

## 5.3 Provider-infrastructure attribution

A non-floor implementation effect may be `PROVIDER_INFRA` only when:

1. the provider projection fixes the operation;
2. target/destination classes are fixed by operator-pinned registries;
3. typed argument grammar prevents authority-class widening;
4. no model parameter selects a broader executable, plugin/config source, mutation mode, destination or target class;
5. the effect is an implementation consequence rather than information returned to or authority exercised on behalf of the model.

## 5.4 Execution-control attribution

`EXECUTION_CONTROL` requires all authority-bearing selectors to derive from **operator-admitted/sealed AEW definitions**, not arbitrary work-product files.

Accepted provenance includes:

```text
operator-admitted verification definition
accepted governing check definition
artifact digest selected by AEW from admitted revision
environment digest from admitted provisioning definition
operator-pinned target registry
operator-pinned endpoint registry
```

A model-authored script/check file does not become trusted merely because AEW later seals its bytes.

If a model controls target/artifact/destination semantics outside the admitted definition, attribution is `MODEL`.

---

# 6. Closed actions, targets and destinations

## Actions

```text
read
write
execute_tool
execute_project_code
debug_attach
process_control
remote_execute
deploy
external_state_write
network_connect
```

## Target classes

```text
source_tree
workspace_scratch
other_workspace
build_output

derived_project_index
evidence_store
knowledge_store
evaluation_corpus

invocation_state
coordination_store
result_store
project_control_state
operator_control_state

provider_runtime
hostile_analysis_runtime
process_state

test_sandbox
acceptance_environment
remote_target
browser_session
external_service

dependency_store
symbol_cache
analysis_project

credential_store
host_system
```

## Destination classes

```text
loopback
internal_service
test_sandbox_net
acceptance_net
approved_mirror
external_network
```

`external_network` is uninstantiated in the air-gapped baseline and therefore illegal at admission.

---

# 7. Operator-pinned physical resource registries

Logical IDs are not enough.

Each registered target/endpoint carries a canonical physical resource identity.

Conceptually:

```text
target_registry:
    target_id
    target_class
    canonical_resource_identity:
        address_set
        host_key_fingerprint?
        service_identity?
        database_instance_id?
        filesystem_or_vm_identity?

endpoint_registry:
    endpoint_id
    destination_class
    canonical_resource_identity:
        address_set
        tls/service identity?
        host key?
        logical service instance?
```

Rules:

1. each logical ID belongs to exactly one class;
2. one canonical physical resource identity may not appear in conflicting classes;
3. aliases, DNS names, IPs, jump-host paths and shared DB identities are normalized before disjointness checks;
4. provider projections reference registry IDs rather than self-classifying resources;
5. unknown resources fail admission.

Gate A checks registry consistency.

Gate B proves the deployment's canonicalization is sufficient against real aliases/routes.

Fixtures:

```text
target_class_double_registered
endpoint_class_double_registered
alias_to_acceptance_host
```

---

# 8. Selector schema is total

Every legal tuple has exactly one selector schema row.

A row may explicitly state:

```text
selectors: none
```

Missing selector-schema row is a Gate A failure.

Examples:

| Tuple | Required selectors |
|---|---|
| `read(source_tree)` | revision, root |
| `read(workspace_scratch)` | owner=self, root |
| `write(workspace_scratch)` | owner=self, root |
| `read(build_output)` | invocation_id or artifact_digest, root |
| `write(build_output)` | invocation_id, root |
| `read(derived_project_index)` | source_revision, index_identity |
| `read(symbol_cache)` | cache_identity, artifact/build identity |
| `read(evidence_store)` | project_id, work_scope, independence selector |
| `read(knowledge_store)` | project_id, source_kind_policy, independence selector |
| `read(coordination_store)` | conversation/work-unit scope |
| `write(coordination_store)` | recipient/invocation binding |
| `read(result_store)` | work-unit/invocation scope |
| `write(result_store)` | invocation_id, result kind |
| `read(external_service)` | service_id, resource/query scope |
| `external_state_write(test_sandbox)` | target_id, action projection |
| `external_state_write(acceptance_environment)` | target_id, bound verification definition |
| `external_state_write(remote_target)` | target_id, action projection |
| `external_state_write(browser_session)` | session_id, origin/action scope |
| `execute_tool(hostile_analysis_runtime)` | artifact_digest, projection_id |
| `execute_project_code(workspace_scratch)` | containment_id, code_origin, source/environment digest |
| `execute_project_code(hostile_analysis_runtime)` | containment_id, artifact_digest, projection_id |
| `network_connect(loopback)` | endpoint_id or explicit local service |
| `network_connect(internal_service)` | endpoint_id |
| `network_connect(test_sandbox_net)` | endpoint_id, target_id |
| `network_connect(acceptance_net)` | endpoint_id, target_id, bound verification definition |
| `debug_attach(process_state)` | containment_id, process_id |
| `process_control(process_state)` | containment_id, process_id |

Machine fixture:

```text
selector_schema_coverage
```

---

# 9. Canonical grant families

## Read

```text
G_SOURCE_READ
G_OWN_SCRATCH_READ
G_BUILD_OUTPUT_READ
G_DERIVED_READ
G_EVIDENCE_READ
G_KNOWLEDGE_READ
G_AEW_CONTEXT_READ
G_AEW_RESULT_READ
G_AEW_LEAD_READ

G_TEST_SANDBOX_OBSERVE
G_ACCEPTANCE_OBSERVE
G_REMOTE_TARGET_OBSERVE

G_BROWSER_OBSERVE
G_EXTERNAL_OBSERVE

G_ENV_READ
G_BINARY_PROJECT_READ
G_PROCESS_OBSERVE
```

## Write / local state

```text
G_SCRATCH_WRITE
G_SOURCE_MUTATE
G_AEW_COORDINATE
G_AEW_RESULT_SUBMIT
G_BINARY_ENRICH
G_LIVE_DEBUG
```

## Execution

```text
G_HOSTILE_ANALYSIS
G_PROJECT_CODE_EXEC
G_BINARY_ADVANCED_EXEC
```

## Remote

```text
G_TEST_SANDBOX_EXEC
G_ACCEPTANCE_EXEC
G_REMOTE_TARGET_EXEC

G_TEST_SANDBOX_MUTATE
G_ACCEPTANCE_MUTATE
G_REMOTE_TARGET_MUTATE

G_BROWSER_STATE
G_EXTERNAL_MUTATE
```

## Network

```text
G_LOOPBACK_NET
G_INTERNAL_NET
G_TEST_SANDBOX_NET
G_ACCEPTANCE_NET
```

Every grant family owns at least one tuple, and every grant family has exactly one role-table row.

---

# 10. Non-model effects

## Provider infrastructure

Examples:

```text
PROVIDER_INFRA execute_tool(provider_runtime)
PROVIDER_INFRA write(derived_project_index)
PROVIDER_INFRA write(symbol_cache)
PROVIDER_INFRA write(invocation_state)
PROVIDER_INFRA write(evidence_store)
PROVIDER_INFRA write(knowledge_store)
PROVIDER_INFRA network_connect(loopback)
PROVIDER_INFRA network_connect(internal_service)
```

Information returned to the model still creates the corresponding `MODEL read(...)` due to the information-flow floor.

## Execution control

Legal execution-control tuples include:

```text
EXECUTION_CONTROL read(source_tree)
    selectors from admitted revision

EXECUTION_CONTROL read(build_output)
    selectors from admitted artifact digest

EXECUTION_CONTROL read(dependency_store)
    selectors from admitted environment digest

EXECUTION_CONTROL execute_tool(provider_runtime)
    fixed provisioning/deployment/check tool projection

EXECUTION_CONTROL execute_project_code(workspace_scratch)
    only for admitted provisioning/setup hooks under contained environment

EXECUTION_CONTROL network_connect(approved_mirror)

EXECUTION_CONTROL network_connect(test_sandbox_net)
    when required by sealed deployment/check definition

EXECUTION_CONTROL network_connect(acceptance_net)
    when required by operator-admitted verification definition

EXECUTION_CONTROL deploy(test_sandbox)
EXECUTION_CONTROL deploy(acceptance_environment)

EXECUTION_CONTROL external_state_write(test_sandbox)
EXECUTION_CONTROL external_state_write(acceptance_environment)

EXECUTION_CONTROL remote_execute(acceptance_environment)
    only fixed-command, operator-admitted verification projection

EXECUTION_CONTROL remote_execute(test_sandbox)
    only when defined by admitted execution-control operation
```

Package/provisioning hooks remain contained and never gain model stores/credentials.

## Evaluator

```text
EVALUATOR read(evaluation_corpus)
```

## Unassignable model effects

```text
MODEL read/write(other_workspace)
MODEL read/write(operator_control_state)
MODEL read/write(credential_store)
MODEL read/write(host_system)
MODEL write(project_control_state)
```

---

# 11. Implication table

The implication table is explicit and operator-pinned.

## Remote environment implications

```text
MODEL read(test_sandbox)
    => MODEL network_connect(test_sandbox_net)

MODEL read(acceptance_environment)
    => MODEL network_connect(acceptance_net)

MODEL remote_execute(test_sandbox)
    => MODEL network_connect(test_sandbox_net)
    => MODEL external_state_write(test_sandbox) BY DEFAULT

MODEL remote_execute(acceptance_environment)
    => MODEL network_connect(acceptance_net)
    => MODEL external_state_write(acceptance_environment) BY DEFAULT
```

For `remote_target`, the provider projection must declare a registered endpoint whose destination class is resolved from the endpoint registry:

```text
MODEL read(remote_target)
    => MODEL network_connect(resolved_destination)

MODEL remote_execute(remote_target)
    => MODEL network_connect(resolved_destination)
    => MODEL external_state_write(remote_target) BY DEFAULT
```

## Browser implications

A browser session binds origins to registered targets/endpoints.

If an action mutates acceptance state:

```text
MODEL external_state_write(browser_session)
    => MODEL network_connect(acceptance_net)
    => MODEL external_state_write(acceptance_environment)
```

Therefore interactive acceptance mutation is not authorized merely by `G_BROWSER_STATE`.

## Execution-control deployment

```text
EXECUTION_CONTROL deploy(test_sandbox)
    => EXECUTION_CONTROL network_connect(test_sandbox_net)
    => EXECUTION_CONTROL external_state_write(test_sandbox)

EXECUTION_CONTROL deploy(acceptance_environment)
    => EXECUTION_CONTROL network_connect(acceptance_net)
    => EXECUTION_CONTROL external_state_write(acceptance_environment)
```

## Implication exemptions

Mutation implications may be removed only with qualification evidence proving:

```text
fixed command
read-only operation
fixed/typed argv grammar
no plugin/config escape
no mutation path
projection/schema hash
```

Fixture:

```text
implication_closure_gap
effect_implication_escape
```

---

# 12. C/P/N/X semantics

```text
C
    normal role ceiling; if the semantic operation is available and relevant,
    required implied families must also be C or infrastructure/control-owned

P
    may be added only through an operator-pre-approved named profile

N
    cannot be granted through ordinary task/profile selection;
    changing N requires a legality/policy revision

X
    not model-grantable
```

There is no free-form model-authored `P` expansion.

The Lead may:

```text
select among operator-approved profiles
narrow a profile
decline optional grants
```

The Lead may not broaden beyond a pre-approved profile.

Named profiles and their grant sets are operator-pinned legality inputs.

---

# 13. Role table

| Grant family | Investigator | Implementer | Reviewer | Verifier | Lead |
|---|---:|---:|---:|---:|---:|
| `G_SOURCE_READ` | C | C | C | C | C |
| `G_OWN_SCRATCH_READ` | C | C | C | C | C |
| `G_BUILD_OUTPUT_READ` | P | C | P | C | P |
| `G_DERIVED_READ` | C | C | C* | P | C |
| `G_EVIDENCE_READ` | C | C | C | C | C |
| `G_KNOWLEDGE_READ` | C | C | P* | P* | C |
| `G_AEW_CONTEXT_READ` | C | C | C | C | C |
| `G_AEW_RESULT_READ` | C | C | C | C | C |
| `G_AEW_RESULT_SUBMIT` | C | C | C | C | P |
| `G_AEW_COORDINATE` | P | P | P | P | C |
| `G_AEW_LEAD_READ` | N | N | N | N | C |
| `G_TEST_SANDBOX_OBSERVE` | P | P | P | P | P |
| `G_ACCEPTANCE_OBSERVE` | N | N | P | C | N |
| `G_REMOTE_TARGET_OBSERVE` | P | P | P | P | P |
| `G_BROWSER_OBSERVE` | P | P | P | P | P |
| `G_EXTERNAL_OBSERVE` | N | N | N | N | N |
| `G_ENV_READ` | P | P | P | C | P |
| `G_BINARY_PROJECT_READ` | P | P | P | P | P |
| `G_PROCESS_OBSERVE` | P | P | P | P | P |
| `G_SCRATCH_WRITE` | P | C | P | C | P |
| `G_SOURCE_MUTATE` | N | C | N | N | N |
| `G_PROJECT_CODE_EXEC` | P | C | P | C | N |
| `G_HOSTILE_ANALYSIS` | P | P | P | P | P |
| `G_BINARY_ADVANCED_EXEC` | N | P | N | N | N |
| `G_LIVE_DEBUG` | P | P | N | P | N |
| `G_LOOPBACK_NET` | P | P | P | P | P |
| `G_INTERNAL_NET` | P | P | N | P | P |
| `G_TEST_SANDBOX_NET` | P | P | N | P | P |
| `G_ACCEPTANCE_NET` | N | N | N | C | N |
| `G_TEST_SANDBOX_EXEC` | P | P | N | P | N |
| `G_ACCEPTANCE_EXEC` | N | N | N | N | N |
| `G_REMOTE_TARGET_EXEC` | P | P | N | P | N |
| `G_TEST_SANDBOX_MUTATE` | N | P | N | P | N |
| `G_ACCEPTANCE_MUTATE` | N | N | N | N | N |
| `G_REMOTE_TARGET_MUTATE` | N | P | N | P | N |
| `G_BROWSER_STATE` | N | P | N | P | N |
| `G_EXTERNAL_MUTATE` | N | N | N | N | N |
| `G_BINARY_ENRICH` | N | P | N | N | N |

`*` requires plan-visible independence selectors.

Important consequences:

- `G_ACCEPTANCE_OBSERVE = C` for Verifier now has `G_ACCEPTANCE_NET = C`, satisfying implication closure.
- `G_ACCEPTANCE_EXEC = N`: ordinary model remote execution in acceptance is not a Verifier grant.
- acceptance execution occurs through `EXECUTION_CONTROL remote_execute(acceptance_environment)` using an operator-admitted fixed command projection.
- interactive browser mutation of acceptance state is therefore also not a normal model grant; acceptance interaction is execution-control-owned sealed automation unless a future policy explicitly changes that model.

---

# 14. Dead-cell and implication-consistency checks

Gate A computes:

```text
implied_families(family)
```

from the implication table.

Checks:

1. every `C` family has all required implied model families at `C`, or those implications are non-model execution-control/provider effects;
2. every `P` family is reachable in at least one operator-approved named profile;
3. no `P` cell is permanently impossible because all necessary implied families are `N`;
4. no `C` cell is dead because an implication requires a merely optional `P`.

Fixtures:

```text
dead_role_cell
c_depends_on_p
```

---

# 15. Operation → expanded-effects golden table

Gate A is checked over the shipped operation catalog, not only abstract tuples.

Every typed operation has a golden entry:

```text
operation
projection
principal-attribution result
declared effects
expanded effects after implication
required selectors
derived families
allowed roles/profiles
```

Representative examples:

## `map.find`

```text
MODEL read(source_tree)
or
MODEL read(derived_project_index)
```

plus provider-infra implementation effects.

## `evidence.show`

```text
MODEL read(evidence_store)
```

## `knowledge.search`

```text
MODEL read(knowledge_store)
```

## `check.run`

varies by admitted provider projection, e.g.:

```text
MODEL execute_project_code(workspace_scratch)
```

or a sealed execution-control acceptance check.

## `remote log retrieval`

```text
MODEL read(test_sandbox)
=> MODEL network_connect(test_sandbox_net)
```

The golden table is generated/validated from the same operation/projection definitions used at runtime.

Gate A invariant:

> every shipped projection's expanded effect set is legal and selector-complete.

Fixture:

```text
operation_effect_catalog_closure
reviewer_without_tool_exec_can_search
```

---

# 16. `execute_project_code` domains

Effects carry an execution domain identifier for combination-policy evaluation.

Conceptually:

```text
EffectInstance:
    principal
    action
    target_or_destination
    domain
    selectors
```

Canonical domain classes include:

```text
harness
provider:<projection>
broker:<service>
child:<check-or-run-id>
hostile_runtime:<session-id>
```

Combination predicates operate over `(domain, effect)`.

This distinguishes:

```text
Verifier model may have G_ACCEPTANCE_NET through provider-brokered operations
```

from:

```text
child:test-123 may not have acceptance_net
```

Project-code child domains remain fixed/minimal as defined below.

---

# 17. Project-code child namespace

Project-authored code never inherits parent-model information/network grants.

Each `child:<id>` receives only:

```text
read(source_tree, exact revision)
read/write(workspace_scratch)
read/write(build_output as scoped)
read(dependency_store, exact environment digest)
declared fixtures
loopback only if the check definition requires it
```

It does not receive:

```text
evidence_store
knowledge_store
coordination_store
result_store
project_control_state
operator_control_state
credential_store
other_workspace
internal_service
test_sandbox_net
acceptance_net
external network
provider/broker credentials
```

IPC/process isolation also blocks:

```text
provider relay socket
AEW bridge socket
broker/supervisor sockets
parent secret environment
shared privileged tmp
shared memory outside namespace
host /proc outside allowed namespace
ptrace outside child containment
```

Fixtures include:

```text
project_code_reads_evidence
project_code_reads_knowledge
project_code_reads_control_state
project_code_reaches_acceptance_env
project_code_reaches_provider_relay
project_code_reads_parent_env
project_code_ptrace_parent
```

---

# 18. Typed-operation argument grammar

Every projection defines:

```text
fixed executable / operation
fixed argv/request template
typed parameter slots
parameter influence metadata
resource selectors
forbidden flags/modes
effect mapping
schema/projection hash
```

Read projections do not permit arbitrary flags.

Fixture:

```text
typed_op_argument_injection
```

Git read projections additionally neutralize:

```text
core.fsmonitor
external diff
textconv
filters
hooks
upload-pack substitution
remote helper substitution
user/global/system config inheritance
```

Fixture:

```text
git_repo_config_executes
```

---

# 19. Enforcement-path schema

Gate A stores an enforcement-path row for every legal `MODEL` tuple **per projection/delivery mechanism**, because the same abstract tuple may be reachable differently.

Key:

```text
(model_effect_tuple, projection_or_delivery_mechanism)
```

Value:

```text
path_class:
    MEDIATOR_PER_CALL
    MEDIATOR_PER_SESSION
    STATIC_CONTAINMENT

owner
selector_check_location
fixture
```

Examples:

```text
MODEL write(source_tree)
via source-mutation provider
    -> MEDIATOR_PER_CALL

MODEL read(source_tree)
via harness-native read
    -> STATIC_CONTAINMENT

MODEL read(source_tree)
via T5/rg provider
    -> MEDIATOR_PER_CALL or PER_SESSION depending projection
```

`ticket_revision` for `write(source_tree)` is checked by the AEW source-mutation mediator, not merely by a filesystem mount.

Gate A proves every shipped model-effect/projection pair has one declared enforcement row.

Gate B proves those rows correspond to complete real mediation.

---

# 20. Resolved plans and plan store

Plans live in AEW-owned, worker-unwritable state.

They bind:

```text
operation
principal
domain
provider projection/version/hash
expanded effect instances
selectors
grant families
profile identity
combination result
enforcement path
source/workspace revision
artifact digest
environment digest
target/endpoint IDs
credential scope
```

The plan hash is checked at the actual enforcement owner.

Fixture:

```text
plan_store_tamper
```

---

# 21. Plan granularity and TOCTOU

## Invocation-level

```text
source reads
map/index reads
evidence/Knowledge reads
bounded source mutation
AEW context/result/coordination operations
```

## Session-level

```text
artifact-bound binary RE session
qualified LSP/index session
```

## Per-effectful-call

```text
check.run execution
remote operation
acceptance operation
browser mutation
debug
artifact acquisition
advanced RE
deployment
environment provisioning
```

Fallback/provider-health changes that alter projection/effects/targets/credential scope require a new plan.

Fixtures:

```text
provider_health_TOCTOU
plan_execution_deviation
fallback_widening
```

---

# 22. Role/profile combination policy

`P` additions come only from operator-approved named profiles.

Combination predicates operate over **domain-scoped expanded effects**.

Examples:

```text
FORBID in same child domain:
    execute_project_code
    AND network_connect(acceptance_net)

FORBID in hostile_runtime domain:
    hostile analysis / binary advanced execution
    AND any network_connect

FORBID:
    Implementer domain -> acceptance_net

FORBID:
    MODEL external_state_write(acceptance_environment)
    except an explicitly admitted future policy;
    baseline uses execution-control fixed checks

FORBID:
    debug_attach(process_state)
    when target containment != admitted containment
```

Because project-code child namespaces exclude evidence/Knowledge/control stores structurally, those combinations are prevented by namespace construction rather than role-set arithmetic.

Fixtures:

```text
grant_combination_forbidden
combination_max_set
```

---

# 23. Interactive acceptance browser policy

Baseline ruling:

> **Model-driven browser mutation of the acceptance environment is not enabled.**

Verifier may observe acceptance-browser state, but acceptance mutations are performed by operator-admitted execution-control automation whose exact script/steps and target binding are part of the verification definition.

A browser action that would mutate acceptance state expands to:

```text
MODEL external_state_write(browser_session)
MODEL network_connect(acceptance_net)
MODEL external_state_write(acceptance_environment)
```

and fails baseline model authorization because `G_ACCEPTANCE_MUTATE = N`.

Fixture:

```text
browser_mutates_acceptance
```

---

# 24. Credentials

Credentials remain dependencies, not effects.

Provider projection records:

```text
credential kind
broker/custody owner
target privilege
target scope
```

Target privilege must fit the admitted projection.

Fixture:

```text
credential_scope_widening
```

---

# 25. Independence

Reviewer/Verifier independence restrictions are selectors in the plan.

Examples:

```text
excluded_source_kinds
permitted_ticket
independence_class
reviewed_revision
```

Fixture:

```text
reviewer_reads_implementer_scratch
```

---

# 26. Source isolation and implementer mutation flow

Reviewer/Verifier source is read-only with disposable COW overlay.

Project-code subprocesses for **all roles**, including Implementer, see authoritative source read-only.

Formatters/codegen/lockfile tools write candidate changes to overlay/scratch.

AEW applies accepted delta through the source-mutation mediator under `G_SOURCE_MUTATE`.

Fixtures:

```text
in_tree_write_by_verifier
source_tool_direct_write_blocked
```

---

# 27. Binary sessions

Baseline:

```text
one binary-re session -> one exact artifact digest
```

Cross-artifact load requires a new/revised plan.

Fixture:

```text
hostile_session_cross_artifact
```

---

# 28. Debug attach

Target selectors require:

```text
containment_id
process_id
```

Foreign harness/supervisor/broker/provider/host processes are forbidden.

Fixture:

```text
debug_attach_foreign_process
```

The runtime selector comparison belongs to Gate B enforcement testing; Gate A verifies the selector is required and the predicate exists.

---

# 29. Legality digest

Operator-pinned legality inputs include:

```text
principal enum
attribution rules/floors
action/target/destination vocabularies
physical resource registries
tuple-status table
selector schemas
implication table
tuple -> family mapping
named role/profile grants
combination predicates
operation -> effect golden catalog
enforcement-path table
project overlays
extension definitions
provider projection hashes where pinned
```

Changes affect F18 legality/staleness.

---

# 30. Project extensions

Extensions may add:

```text
namespaced semantic labels
namespaced operations
provider projections using existing legal effects
operator-created extension families over existing tuple vocabulary
```

They may not add new actions/targets/destinations without a governing schema revision.

They cannot shadow core IDs or inherit grants by name.

Fixture restored:

```text
project_extension_shadow
```

---

# 31. Gate A fixtures

```text
grant_family_coverage
tuple_without_owner
family_without_tuple
family_missing_role_row

attribution_floor_conflict
information_flow_read_floor
implication_closure_gap
effect_implication_escape

target_class_double_registered
endpoint_class_double_registered
alias_to_acceptance_host

selector_schema_coverage

operation_effect_catalog_closure
reviewer_without_tool_exec_can_search

typed_op_argument_injection
provider_extra_tool
schema_drift
fallback_widening
objective_widening
legacy_alias_grant

dead_role_cell
c_depends_on_p
combination_max_set
grant_combination_forbidden

project_extension_shadow
browser_mutates_acceptance
credential_scope_widening
reviewer_reads_implementer_scratch
dependency_environment_digest_mismatch
verifier_wrong_revision_deploy

role_table_edit
tuple_table_edit
implication_table_edit
target_registry_edit
operation_catalog_edit
enforcement_path_edit
```

---

# 32. Gate B fixtures

```text
plan_store_tamper
provider_health_TOCTOU
plan_execution_deviation

shell_reachability
filtered_shell_unknown_command
native_child_grant_widening
session_resume_without_readmission

static_analyzer_plugin_exec
build_discovery_executes_configure
lsp_executes_project_code
git_repo_config_executes

project_code_reaches_provider_relay
project_code_reaches_bridge
project_code_reads_parent_env
project_code_ptrace_parent

project_code_reads_evidence
project_code_reads_knowledge
project_code_reads_control_state
project_code_reaches_acceptance_env

debug_attach_foreign_process

in_tree_write_by_verifier
source_tool_direct_write_blocked
hostile_session_cross_artifact
```

Gate B additionally requires the written mediator-completeness argument for the exact pinned deployment.

---

# 33. Gate A acceptance claim

If all Gate A invariants and fixtures pass, AEW may freeze v0.8 with the claim:

> **The M6a engineering-capability authorization schema is total, closed under implication, operation-complete, selector-complete, profile-consistent, and machine-checkable.**

It may **not** yet claim bypass-resistant deployment enforcement.

---

# 34. Designer disposition

**APPROVE THE REVIEW.**

The review correctly found that v0.7 still proved closure over an abstract effect table rather than the shipped operation/projection catalog.

v0.8 makes shipped operations, attribution, selectors, implication closure, profiles, resource classes and enforcement declarations part of the same single-sourced machine policy.

The remaining Gate A task is mechanical:

> encode the tables and demonstrate every invariant over the actual shipped operation catalog.

The remaining Gate B task is empirical:

> prove the declared enforcement paths are complete against the real harness/provider/containment deployment.
