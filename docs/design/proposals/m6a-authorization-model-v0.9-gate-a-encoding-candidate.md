# AEW M6a Authorization Model v0.9 — Gate A Encoding Candidate

**Date:** 2026-10-10  
**Status:** **Concept frozen; encoding candidate for Gate A** — not yet governing  
**Supersedes:** `AEW_M6a_Capability_and_Effect_Authorization_Model_v0.8.md` for Gate A encoding details.  
**In this repository (ingested 2026-10-10):** a designer candidate, not yet governing; concept frozen at v0.9. It overlays [v0.8](m6a-capability-and-effect-authorization-model-v0.8.md) (the file named on the line above) for Gate A encoding only; v0.8 keeps the conceptual model wherever this text is silent (requirements ledger: this document is GAE, v0.8 is CEA; register F38 to F40). The text below is unchanged  
**Design intent:** No new conceptual model is introduced here. This revision resolves first-encode contradictions found during closure review and specifies the machine inputs required by the checker.

---

# 1. Freeze boundary

The conceptual model from v0.8 is frozen:

```text
semantic/discovery label
    -> typed operation
    -> qualified provider projection
    -> principal attribution
    -> declared + implied scoped effects
    -> selector validation
    -> canonical grant-family derivation
    -> role/profile + combination legality
    -> AEW-owned plan
    -> declared enforcement path
```

Two acceptance gates remain permanent:

```text
Gate A
    machine-policy closure

Gate B
    deployed bypass-freedom
```

Gate A proves table/catalog consistency.

Gate B proves the real pinned harness/provider/containment deployment actually enforces it.

---

# 2. Gate A checks: safety and liveness

Replace ambiguous "combination predicates are satisfiable" wording with two checks.

## 2.1 Safety

For every admitted named profile:

```text
expanded_effect_set(profile)
```

after implication expansion, selector binding and domain assignment must satisfy every `FORBID` predicate.

## 2.2 Liveness

For every role:

1. the role's `C`-only baseline is admissible;
2. every `C` family has all required implied model families at `C`, unless the implication is explicitly provider-infra / execution-control owned;
3. every `P` cell intended for use appears in at least one operator-approved named profile;
4. no named profile contains a dead `P` combination.

Fixtures:

```text
combination_profile_safety
role_baseline_liveness
dead_role_cell
c_depends_on_p
```

---

# 3. Information-flow floor and provider-infra reads

The information-flow floor remains:

> Any information returned to the model is represented as a `MODEL read(...)`, even when a fixed provider performed the underlying read.

Provider implementation reads are **also** represented when they matter to provider qualification.

This is not double authority; the two effects describe different principals.

Examples:

```text
rg fixed projection:
    PROVIDER_INFRA read(source_tree)
    MODEL read(source_tree)       # information delivered to model

T5 query:
    PROVIDER_INFRA read(derived_project_index)
    MODEL read(derived_project_index)

evidence.show:
    PROVIDER_INFRA read(evidence_store)
    MODEL read(evidence_store)
```

Add legal `PROVIDER_INFRA` read rows as required by shipped providers, including at least:

```text
PROVIDER_INFRA read(source_tree)
PROVIDER_INFRA read(workspace_scratch)
PROVIDER_INFRA read(build_output)
PROVIDER_INFRA read(derived_project_index)
PROVIDER_INFRA read(evidence_store)
PROVIDER_INFRA read(result_store)
PROVIDER_INFRA read(knowledge_store)
PROVIDER_INFRA read(dependency_store)
PROVIDER_INFRA read(symbol_cache)
PROVIDER_INFRA read(analysis_project)
```

Each is bounded by the qualified provider projection and provider containment.

Gate A invariant:

> Every shipped projection's provider-infra effects and model-visible information-flow effects are both legal.

Restore fixture:

```text
reviewer_without_tool_exec_can_search
```

---

# 4. Reviewer remote-observation closure

Remote observation is useful to Reviewer only if its network implication is also eligible.

Resolve the v0.8 dead cells by making matching observation-network families `P` for Reviewer:

```text
Reviewer:
    G_TEST_SANDBOX_OBSERVE = P
    G_TEST_SANDBOX_NET     = P

    G_ACCEPTANCE_OBSERVE   = P
    G_ACCEPTANCE_NET       = P

    G_REMOTE_TARGET_OBSERVE = P
```

For `remote_target`, the matching network family is determined by the registered endpoint destination and must be present in the same named profile.

These grants are **provider-domain only**. They do not enter project-code child domains.

Therefore a reviewer remote-observation named profile may contain:

```text
G_ACCEPTANCE_OBSERVE
G_ACCEPTANCE_NET
```

while the Reviewer child process remains network-isolated.

## 4.1 Browser observation implication

Add:

```text
MODEL read(browser_session)
    => MODEL network_connect(resolved destination of origin_set)
```

The browser session registry binds each admitted origin to a registered endpoint/destination class.

Thus browser observation is not a network-free capability.

---

# 5. Provisioning domain

Provisioning hooks are not ordinary project-code child processes.

Add execution domain:

```text
provision:<provisioning-id>
```

Its fixed namespace is:

```text
dependency_store:
    read-write, exact provisioning root

package/source inputs:
    read-only, digest-pinned

approved_mirror:
    network only when required by the admitted provisioning definition

workspace_scratch:
    bounded temporary write if required

everything else:
    denied
```

It does not receive:

```text
source_tree write
evidence_store
knowledge_store
coordination/result/control stores
acceptance_net
test_sandbox_net
credential_store
operator state
other workspaces
```

Legal execution-control provisioning effects include:

```text
EXECUTION_CONTROL read(dependency_store)
EXECUTION_CONTROL write(dependency_store)

EXECUTION_CONTROL execute_tool(provider_runtime)

EXECUTION_CONTROL execute_project_code(workspace_scratch)
    domain=provision:<id>

EXECUTION_CONTROL network_connect(approved_mirror)
```

Selectors must originate from the operator-admitted provisioning definition.

Fixture:

```text
provisioning_namespace
provisioning_cannot_reach_project_control
```

---

# 6. Exhaustive selector table

The selector schema is a single machine table, not prose examples.

For **every legal tuple/status row**, the encoding contains exactly one selector entry:

```text
selector_schema[
    principal,
    action,
    target_or_destination
] = {
    required_keys: [...],
    optional_keys: [...],
    constraints: [...]
}
```

A tuple may explicitly use:

```text
required_keys: []
```

Missing selector-table entry is a Gate A failure.

The exhaustive table must cover model, provider-infra, execution-control and evaluator tuples.

At minimum it includes all previously named rows, including:

```text
read/write(workspace_scratch)
read/write(build_output)
read/write(coordination_store)
read/write(result_store)

read(source_tree)
read(derived_project_index)
read(symbol_cache)
read(evidence_store)
read(knowledge_store)
read(dependency_store)
read(analysis_project)
read(process_state)
read(browser_session)
read(external_service)

write(source_tree)
write(analysis_project)

external_state_write(test_sandbox)
external_state_write(acceptance_environment)
external_state_write(remote_target)
external_state_write(browser_session)
external_state_write(external_service)

execute_tool(provider_runtime)
execute_tool(hostile_analysis_runtime)
execute_project_code(workspace_scratch)
execute_project_code(hostile_analysis_runtime)

remote_execute(test_sandbox)
remote_execute(acceptance_environment)
remote_execute(remote_target)

deploy(test_sandbox)
deploy(acceptance_environment)

network_connect(loopback)
network_connect(internal_service)
network_connect(test_sandbox_net)
network_connect(acceptance_net)
network_connect(approved_mirror)

debug_attach(process_state)
process_control(process_state)
```

Permanent check:

```text
selector_schema_coverage
```

---

# 7. Native edit/write decision

**Decision: disable harness-native authoritative source edit/write tools in AEW worker profiles.**

Authoritative source mutation uses one path:

```text
candidate delta / patch
    -> AEW source-mutation mediator
    -> ticket-revision / workspace / root checks
    -> write(source_tree)
```

This includes Implementer work.

Project-authored tools continue to write only to the COW/overlay and produce attributable candidate deltas.

Consequences:

1. `MODEL write(source_tree)` has a single normal worker delivery mechanism:
   ```text
   source_mutation_provider
       -> MEDIATOR_PER_CALL
   ```
2. `ticket_revision` is checked by that mediator.
3. harness-native `edit` / `write` / equivalent direct authoritative-source tools are hidden/denied in worker model-visible schemas.
4. provider/harness conformance must prove those native tools are absent or cannot reach authoritative source.

This is a **Gate B precondition** for the qualified worker harness pin.

Fixtures:

```text
native_source_edit_hidden
source_mutation_bypasses_mediator
source_tool_direct_write_blocked
```

A future harness-native edit path may be qualified only if it is itself bound to the same AEW mutation contract and becomes an explicitly modeled delivery mechanism.

---

# 8. Reserved families

The following families are defined for portable/future policy but are not active grant families in the current baseline:

```text
G_ACCEPTANCE_EXEC
G_ACCEPTANCE_MUTATE
G_EXTERNAL_OBSERVE
G_EXTERNAL_MUTATE
```

They live in:

```text
reserved_family_registry
```

not the active role/family bijection.

Rules:

1. reserved family owns its future legal tuple mapping;
2. it has no active role-table row;
3. no named profile may contain it;
4. activating it requires an operator-pinned legality revision;
5. Gate A active-family bijection ignores reserved families but separately validates the reserved registry.

Checks:

```text
reserved_family_not_in_profile
reserved_family_not_in_active_role_table
reserved_family_has_tuple_definition
```

Acceptance execution in the baseline remains:

```text
EXECUTION_CONTROL remote_execute(acceptance_environment)
```

through operator-admitted fixed-command verification projections.

Acceptance mutation/deploy remains execution-control-owned.

---

# 9. Revised active role table deltas

Relative to v0.8:

```text
Reviewer:
    G_TEST_SANDBOX_NET = P
    G_ACCEPTANCE_NET   = P
    G_INTERNAL_NET     = P only through a named remote-observation profile
                         whose endpoint registry resolves the observed remote target there

Reserved rows removed:
    G_ACCEPTANCE_EXEC
    G_ACCEPTANCE_MUTATE
    G_EXTERNAL_OBSERVE
    G_EXTERNAL_MUTATE
```

All `P` additions remain selectable only through operator-pre-approved named profiles.

Lead may select a named profile or narrow it; Lead cannot author a new grant set.

---

# 10. Named profile catalog is a required Gate A input

Gate A consumes an operator-pinned named profile catalog.

Conceptual schema:

```text
profile:
    id
    role
    grants
    permitted semantic operation families
    target/destination selectors
    domain restrictions
    provider projection restrictions
    combination-policy annotations if needed
```

Examples are deployment/project data, not hard-coded architecture.

A `P` role-table cell is not usable until at least one admitted named profile contains it with all implied grants.

Gate A checks:

```text
profile.references_only_C_or_P
profile.contains_no_N_or_X
profile.contains_no_reserved_family
profile.implication_closed
profile.combination_safe
profile.selector_complete
```

---

# 11. Shipped operation/projection catalog is a required Gate A input

The checker consumes the **same generated operation/projection definitions the runtime uses**.

For each shipped projection:

```text
operation_id
projection_id
provider_id/version/hash
parameter grammar
attribution metadata
declared effects
expanded effects
selectors
derived families
enforcement declaration
allowed named profiles
```

The catalog includes only qualified providers.

Therefore REA / bethington projections appear only after their exact subsets qualify.

Gate A fixture:

```text
operation_effect_catalog_closure
```

---

# 12. Exhaustive implication table is a required Gate A input

Implication rules are single-sourced machine data.

Required implications include at least:

```text
MODEL read(test_sandbox)
    => MODEL network_connect(test_sandbox_net)

MODEL read(acceptance_environment)
    => MODEL network_connect(acceptance_net)

MODEL read(remote_target)
    => MODEL network_connect(resolved_endpoint_destination)

MODEL read(browser_session)
    => MODEL network_connect(resolved_origin_destination)

MODEL remote_execute(test_sandbox)
    => MODEL network_connect(test_sandbox_net)
    => MODEL external_state_write(test_sandbox) by default

MODEL remote_execute(acceptance_environment)
    => MODEL network_connect(acceptance_net)
    => MODEL external_state_write(acceptance_environment) by default

MODEL remote_execute(remote_target)
    => MODEL network_connect(resolved_endpoint_destination)
    => MODEL external_state_write(remote_target) by default

MODEL external_state_write(browser_session)
    => MODEL network_connect(resolved_origin_destination)
    => MODEL external_state_write(backing target) where registered

EXECUTION_CONTROL deploy(test_sandbox)
    => EXECUTION_CONTROL network_connect(test_sandbox_net)
    => EXECUTION_CONTROL external_state_write(test_sandbox)

EXECUTION_CONTROL deploy(acceptance_environment)
    => EXECUTION_CONTROL network_connect(acceptance_net)
    => EXECUTION_CONTROL external_state_write(acceptance_environment)
```

Gate A machine check:

```text
for every legal input tuple:
    every implied tuple must itself have a legal status
    under the same principal unless the implication explicitly transforms principal by governing rule
```

No provider self-asserted implication exemptions.

---

# 13. Operation-domain effects

Effect instances include:

```text
principal
action
target_or_destination
domain
selectors
```

Domains:

```text
harness
provider:<projection-id>
broker:<service-id>
child:<check-id>
hostile_runtime:<session-id>
provision:<provision-id>
```

Combination predicates are evaluated over domain-scoped effects.

This preserves the distinction between:

```text
Reviewer model/provider can use acceptance observation network
```

and:

```text
Reviewer project-code child cannot use acceptance network
```

---

# 14. Project-code child namespace remains fixed

`child:<id>` receives:

```text
source_tree read-only
own scratch/build output read-write
dependency_store read-only at exact environment digest
declared fixtures
loopback only when required
```

It receives no:

```text
evidence
knowledge
coordination
result/control state
credentials
provider/broker sockets
test-sandbox network
acceptance network
internal service network
external network
```

This is independent of parent role grants.

---

# 15. Enforcement-path table

Gate A encodes an exhaustive table keyed by:

```text
(model_effect_tuple, projection_or_delivery_mechanism)
```

with:

```text
path_class
owner
selector_check_location
expected_fixture
```

Possible path classes:

```text
MEDIATOR_PER_CALL
MEDIATOR_PER_SESSION
STATIC_CONTAINMENT
```

Gate A proves one declared path per shipped tuple/mechanism pair.

Gate B proves that the declared real path is complete and bypass-resistant.

The worker source-mutation decision in §7 removes harness-native authoritative edit/write as a competing normal path.

---

# 16. Resource registries

Gate A input includes the operator-pinned real deployment registries:

```text
target_registry
endpoint_registry
canonical_resource_identity
```

Gate A proves logical/class consistency.

Gate B proves canonicalization catches real aliases/routes.

Fixtures:

```text
target_class_double_registered
endpoint_class_double_registered
alias_to_acceptance_host
```

---

# 17. Gate A active-family coverage

Machine checks:

```text
every active grantable tuple -> exactly one active family

every active family -> >=1 active grantable tuple

active family set <-> active role-table rows is bijective

reserved family set is disjoint from active family set

no named profile contains reserved family
```

---

# 18. Gate A inputs checklist

Gate A cannot execute without:

1. exhaustive principal/status tuple table;
2. exhaustive selector table;
3. exhaustive implication table;
4. active grant-family mapping;
5. reserved-family registry;
6. active role-to-family table;
7. operator-approved named profile catalog;
8. shipped operation/projection catalog generated from runtime definitions;
9. target registry;
10. endpoint registry;
11. canonical resource identities;
12. enforcement-path declaration table;
13. combination predicates;
14. project policy overlays;
15. provider/harness projection hashes where pinned.

Missing an input is a Gate A failure, not a warning.

---

# 19. Gate A fixtures

Required policy-evaluable fixtures include:

```text
grant_family_coverage
tuple_without_owner
family_without_tuple
family_missing_role_row

reserved_family_not_in_profile
reserved_family_not_in_active_role_table

information_flow_read_floor
attribution_floor_conflict

implication_closure_gap
effect_implication_escape

selector_schema_coverage

operation_effect_catalog_closure
reviewer_without_tool_exec_can_search

dead_role_cell
c_depends_on_p
combination_profile_safety
role_baseline_liveness

typed_op_argument_injection
provider_extra_tool
schema_drift
fallback_widening
objective_widening
legacy_alias_grant

project_extension_shadow
browser_mutates_acceptance
credential_scope_widening
reviewer_reads_implementer_scratch
dependency_environment_digest_mismatch
verifier_wrong_revision_deploy

target_class_double_registered
endpoint_class_double_registered
alias_to_acceptance_host

role_table_edit
tuple_table_edit
implication_table_edit
target_registry_edit
profile_catalog_edit
operation_catalog_edit
enforcement_path_edit
```

---

# 20. Gate B preconditions and fixtures

The schema records, but Gate A does not prove, deployment completeness.

Gate B requires:

```text
worker native authoritative edit/write hidden
provider relay completeness
bridge/broker IPC isolation
project-code process namespace
real mount/network containment
real target/endpoint canonicalization
filtered-shell enforcement
native child suppression/scoping
session-resume authority behavior
```

Fixtures include:

```text
native_source_edit_hidden
source_mutation_bypasses_mediator
source_tool_direct_write_blocked

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
hostile_session_cross_artifact
```

Gate B also requires the written mediator-completeness argument for the exact pinned deployment.

---

# 21. Encoding disposition

**Concept: FROZEN.**

The remaining work is encoding and proof.

The first encoding should be expected to fail loudly on any:

```text
missing tuple row
missing selector row
missing implication closure
dead profile grant
unqualified shipped projection
unregistered resource
missing enforcement declaration
reserved family use
```

Those are implementation/schema defects unless they expose a new authority distinction.

The design is reopened only if encoding reveals an effect, principal, target, destination, domain, grant boundary or enforcement class that the frozen model cannot represent truthfully.

---

# 22. Gate A freeze claim

When the machine representation passes the checks above, AEW may state:

> **The M6a engineering authorization model is total over its admitted operation catalog, closed under attribution and implication, selector-complete, profile-consistent, and internally machine-verifiable.**

The stronger deployment statement remains Gate B only.
