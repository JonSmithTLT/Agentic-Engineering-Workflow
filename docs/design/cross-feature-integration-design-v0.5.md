# AEW Cross-Feature Integration Design v0.5 — FROZEN

> Ingested 2026-10-10. The designer's frozen text follows unchanged. Decision record: [`decisions-2026-10-10-cross-feature-integration-freeze.md`](decisions-2026-10-10-cross-feature-integration-freeze.md); requirements ledger CFI; register F41 to F41.14 and Q15.

**Date:** 2026-10-10  
**Status:** **FROZEN DESIGN** — activation remains gated by governing amendments and implementation qualification  
**Supersedes:** `AEW_Cross_Feature_Integration_Design_v0.4.md`  
**Disposition:** FREEZE WITH CORRECTIONS applied. No new features or redesign. V-1(b) remains adopted: a non-blocking interface-dependency edge.

---

## 1. Principle and ownership

This design connects adopted AEW owners. It does not introduce a second lifecycle, invalidation system, review-proof system, health system, or coordination channel.

New surface is limited to:

- a reviewed-plan contract for parent work;
- section-level plan binding;
- a non-blocking interface-dependency edge;
- interface digests on those edges;
- an overlap projection;
- two U1 health fields;
- `operator_validation` evidence;
- a delta-review packet;
- deterministic plan-underspecification signals.

Everything else lands under existing owners.

---

## 2. Mandatory planning for every Epic and Story

Planning is mandatory for **every ancestor Epic and Story, including Class 0**.

This is deliberate.

Story/Epic identity means governed multi-step work. The place where AEW avoids unnecessary planning ceremony is Ticket granularity, not by allowing planless parent work.

This requirement changes `parent_paths["0"]` and therefore requires the Workflow Contract / F14 amendment before activation. The parent-plan guard is an input to **F14 §17.1's single `DispatchDecision`**, not a second dispatch engine.

No new stored parent work states are introduced.

Parent state remains derived. Planning is derived from durable plan records.

### 2.1 Derived plan phase

```text
no_plan
plan_proposed
plan_under_review
plan_rejected
plan_accepted_current
plan_accepted_stale
plan_superseded
```

`plan_accepted_current` requires a reviewed, adopted `plan_proposal`.

An accepted plan becomes non-current when:

- a newer plan is adopted;
- a governing requirement/revision change invalidates it;
- a consumed parent/interface binding makes it stale under existing revision rules;
- the unit is cancelled/superseded under existing lifecycle authority.

Draft or under-review replacement plans do not by themselves revoke the currently accepted plan.

Unless an existing authority explicitly suspends the unit, descendants already bound to the current accepted plan continue under that binding while a replacement proposal is under review.

---

## 3. Planning/research child exemption is engine-derived

A Lead/worker label such as “research” or “planning” cannot bypass planning requirements.

A child receives the planning-phase exemption only when **both** are true:

1. its admitted purpose is one of the governing planning/research purposes; and
2. its resolved capability/effect envelope satisfies the planning-child allow-list.

The engine derives the exemption at dispatch.

### 3.1 Planning-child allow-list

A planning/research child may receive bounded capabilities needed to investigate and produce plan evidence, for example:

```text
source/navigation reads
derived-map reads
Knowledge/evidence reads subject to normal visibility
own scratch write
plan/result submission
bounded coordination
G_REMOTE_TARGET_OBSERVE where policy allows
G_TEST_SANDBOX_OBSERVE where policy allows
G_BROWSER_OBSERVE where policy allows
```

`G_EXTERNAL_OBSERVE` is reserved in M6a v0.9 §8 and is not part of this active planning-child allowance.

Until dedicated Planner/Researcher role rows exist, planning/research children resolve against the **M6a Investigator row** plus the planning-child narrowing above. Dedicated Planner/Researcher rows, if desired, are an **F38 input**, not an implicit new authority surface.

This changes the existing `non_mutating_paths` default. Adoption requires a migration of project policy in `policy/gates.yaml` so existing projects do not silently retain the old rule.

It may not receive effects that make it an implementation child, including:

```text
authoritative source mutation
deployment
acceptance mutation
remote mutation
binary enrichment
project-code execution that can mutate authoritative source
other governing mutation effects
```

The exact allowed effect set is represented by the resolved M6a/launch profile and checked at dispatch.

Before M6a enforcement is available, this exemption may activate only for dedicated planner/research launch profiles whose containment provides the equivalent non-mutating guarantee.

### 3.2 Planner's own plan obligation

A planning-phase non-mutating child satisfies its own plan obligation with its assignment.

It never needs a separately accepted plan merely to create or review the parent's plan.

This prevents recursive “the plan needs a plan” behavior.

---

## 4. Parent plan proposal, review and adoption

A plan is governed evidence/artifact, not a child Ticket lifecycle.

A Story/Epic plan may be proposed by:

- a dedicated planner child; or
- the unit's Lead through the unit's plan-proposal path.

### 4.1 What counts as reviewed

A plan proposal is reviewed only when:

```text
R1 review = PASS
open required findings = 0
review is bound to proposal sha256
```

`R1` uses the existing independent-review visibility rules.

The reviewer must be independent under the existing reviewer visibility rules and cannot be the proposer.

Additional review multiplicity remains governed by the existing WC/F17/D5 risk policy.

### 4.2 Adoption

The adopter cannot be the proposer.

Normal path:

```text
planner child proposes
independent reviewer passes
Lead adopts
```

If the Lead itself proposed the plan, adoption requires either:

```text
operator adoption
```

or:

```text
a Lead generation whose admitted identity differs from the proposer's,
as recorded by the governing control model
```

A takeover/re-attach that re-admits the same agent identity does not satisfy this separation.

The engine never treats proposal + self-review/self-adoption as sufficient.

### 4.3 Minimal Class-0 parent plan

Class-0 Stories/Epics may use a thin plan, but it must still state at minimum:

```text
objective
governing requirements / acceptance criteria
intended decomposition or execution sequence
known dependencies/interfaces
verification method
```

Fields may be concise. Length is never a quality signal.

### 4.4 Migration for in-flight parents

At adoption of this contract:

- already-active admitted descendant attempts may continue work under their existing attempt authority;
- their forward gates and publish wait for the parent's reviewed plan and a recorded binding under §6;
- no new mutating descendant dispatch occurs until the parent has a reviewed accepted plan;
- research/planning children remain dispatchable to produce the missing plan.

---

## 5. Ticket planning remains conditional

A separate Ticket research/plan step is required iff:

```text
effective risk class >= 2
OR F14 hard trigger is active
OR accepted parent plan marks Ticket: plan_required
OR a recorded raise-only decision requires planning
```

Otherwise:

```text
Class 0:
    no separate plan

Class 1:
    assignment/contract is the plan
```

Length/token count never enters this decision.

### 5.1 Design decision discovered during execution

`design_decision_required` is a worker-reported **attention/reason**, not a lifecycle transition.

Flow:

```text
worker reports design_decision_required
    -> attention to Lead
    -> Lead evaluates
    -> Lead may perform the existing REPLAN_REQUIRED transition
```

The engine never transitions to `REPLAN_REQUIRED` solely because a worker asserted the reason.

`REPLAN_REQUIRED` remains the existing lifecycle state; `design_decision_required` is a governed reason/attention code under F14.

---

## 6. Plan sections and descendant binding

Section-digest binding is a prerequisite for activation of this integration.

It is not “where available.”

Every mutating descendant dispatch records:

```text
ancestor plan id/revision
consumed section ids
engine-computed normalized digest for each consumed section
```

A descendant consumes every governing section by default:

```text
objective
requirements / acceptance criteria
interfaces it names
its structured decomposition entry
```

The parent plan's structured decomposition may narrow the consumed set. A worker/Lead may not freely declare a narrower consumed set at dispatch.

The normalization algorithm is governed/versioned.

### 6.1 Staleness

A descendant's plan binding becomes stale iff an accepted plan revision changes the **engine-computed normalized digest** of a section that descendant consumes.

The engine decides whether the consumed section changed.

No Lead/author “editorial” label can preserve currency.

Until F5 supplies governed change classes and the section-binding implementation exists, every accepted revision affecting the parent plan stales the applicable binding and requires explicit reconfirmation.

Once F5 governs change classes, `EDITORIAL` may preserve binding only where the engine-computed consumed-section digest is unchanged and F5 policy permits it.

### 6.2 Replacement plan under review

While a replacement plan is proposed/reviewed:

- the old accepted plan remains current;
- descendants already bound to it remain governed by it;
- new dispatch may continue under it unless an existing authority explicitly suspends work;
- only adoption of the replacement changes the current plan binding.

### 6.3 `plan reconfirm --subtree`

Bulk reconfirm remains an explicit recovery/administrative action, not the normal substitute for section binding.

It must show, per affected descendant:

```text
old plan/section digest
new plan/section digest
changed consumed sections
current descendant status
whether work has already integrated/published
```

Authority:

```text
effective class 0-1:
    Lead may request/record reconfirmation

effective class >=2:
    existing risk policy must provide independent confirmation
    before reconfirmation is recorded
```

Effects:

- rebinding affects future dispatch/forward authority only;
- reconfirmation makes **no evidence admissible by itself**;
- admissibility of existing evidence is computed against the new binding under E19-B §5.2;
- already-integrated work affected by the change requires fresh verification under the new binding;
- it cannot make stale proof current.

---

## 7. V-1 decision: non-blocking interface-dependency edges

**Decision: V-1(b).**

Current blocking dependency edges retain their existing meaning:

```text
blocking dependency:
    consumer waits for provider DONE
```

AEW adds a separate edge kind:

```text
interface_dependency
```

Purpose:

> represent a contract/assumption dependency between work that may execute in parallel.

This requires a Workflow Contract §8 amendment before activation.

That amendment also extends **E19-B §7.5's `revision_impact_hold` trigger** to accepted interface revisions on `interface_dependency` edges.

### 7.1 Interface dependency semantics

An interface-dependency edge contains:

```text
provider_work_id
consumer_work_id
interface_id
engine_computed_interface_digest
interface_source
```

It does **not** impose execution ordering.

The consumer may dispatch while the provider is active if:

- the interface contract is current and accepted;
- the consumer is bound to its digest;
- all other normal dispatch requirements pass.

### 7.2 Interface digest source

Digests are engine-computed from the canonical interface content.

They are never author-supplied.

Canonical sources may include an accepted parent-plan interface section or another explicitly governed interface artifact.

Rename or removal of a referenced interface ID counts as an interface change and affects every named consumer.

### 7.3 Contract drift at publish

If provider implementation changes the governed interface content such that the engine-computed digest differs from the accepted interface contract, but no accepted interface revision exists:

```text
INTERFACE_CONTRACT_DRIFT
    -> integration/publish refusal
```

This prevents implementation from silently changing the contract underneath active consumers.

Workspace-level likely interface changes may generate advisory overlap candidates, but only committed/accepted contract facts change authority.

---

## 8. Interface invalidation uses E19-B + F9

No second invalidation subsystem exists.

When an accepted interface revision changes an interface digest:

```text
E19-B revision_impact_hold
    -> direct named consumers
```

The hold blocks:

```text
dispatch
forward gates
publish
```

and does not recursively fan out.

### 8.1 Resolution vocabulary

`ADOPT_NEW_VERSION` is not a new F9 category.

It is a UI/action description that resolves through existing F9 terms:

```text
RECONTEXTUALIZE
    when the Ticket can continue against the new interface without plan/goal change

TICKET_REPLAN
    when the new interface changes the Ticket's plan/design assumptions
```

### 8.2 Hold clearing and rebinding

The held worker cannot clear its own hold.

The hold clears when:

1. the Lead records the applicable F9 disposition (`RECONTEXTUALIZE` or `TICKET_REPLAN`); and
2. the engine records the consumer's binding to the new interface digest as the E19-B §7.5 **attributable dependent update**.

The held worker cannot record either authority-bearing action.

Clearing the hold makes no evidence current. Results of attempts admitted under the old digest remain bound to that digest.

Progression therefore requires:

```text
new attempt admitted against the new digest
```

That attempt may carry prior workspace contents forward **as input only** under E19-B §5.4, and must obtain fresh required review/verification under E19-B §5.2 admissibility.

Rebinding an interface edge's digest is an **E19-B revision of the consumer's dependency field group**, not a free edge edit. If an active attempt exists, the revision follows E19-B §7.2 quiescence before the new binding becomes authoritative.

---

## 9. Undeclared-consumer residual

Hard interface protection applies only to **declared interfaces / interface-dependency edges**.

A semantic consumer that fails to declare the relationship remains a known residual.

Mitigations include:

```text
integration validation
parent verification
publish-overlap advisory
overlap projection
review
future dependency discovery where qualified
```

The hold reduces latency and protects declared relationships; it does not guarantee global consistency for undeclared relationships. Undeclared relationships rely on integration validation and parent verification for safety; the hold mechanism only reduces detection/reaction latency where the dependency is declared.

---

## 10. Overlap projection

The overlap projection remains advisory.

It reports coverage and unknowns first.

Signals include:

```text
exact file overlap
declared blocking/interface dependencies
accepted interface ids/digests
allocated identifiers / namespaces
shared register/schema/config surfaces
known build/test surfaces
qualified structural-map relationships
qualified symbol relationships where available
```

Allocated-identifier namespaces come from **project policy data**, not a fixed AEW-global list. A project may declare namespaces such as ADR/invariant numbers, ledger prefixes, schema enums, register IDs, or other reserved identifiers.

Mechanically mergeable paths are identified separately.

Unsupported Python import/symbol coverage is reported as unknown, not inferred.

---

## 11. Wake rules

The hold is authority.

A wake is only a nudge.

Losing a wake cannot make stale work valid.

Initial authoritative wake triggers:

1. an accepted interface revision changes a digest named by a direct consumer;
2. `integrate.publish` produces a committed diff overlapping another active Ticket's admitted scope **or another active Ticket's current workspace diff at the publish commit**.

Trigger 2 is advisory only; it does not create a hold.

### 11.1 Coalescing

Wake key:

```text
(dependent, subject)
```

A wake points to the latest committed fact/version.

If a later committed change arrives after the prior wake was delivered/acknowledged, a new wake is emitted.

Multiple undispatched facts may coalesce to the latest version while preserving the hold/state record.

These are outbox events delivered through the existing D5/F9 Lead coordination lane in `wait --any` **whether or not the F9 messaging switch is enabled**. M4-H may therefore keep messaging off without disabling these wakes.

Reference: designer decision D5, 2026-10-10 (evening).

---

## 12. Run health

Owned by U1/H1.

New dogfood-justified fields:

```text
current_or_longest_child_process
age_of_last_durable_progress
```

`current_or_longest_child_process` is sanitized:

- no full command line;
- no environment;
- no model-authored arguments;
- only a safe process/tool label, pid/identity where policy permits, and age/status.

Health remains advisory and has no lifecycle authority.

---

## 13. Operator validation evidence

Add evidence kind:

```text
operator_validation
```

integrated with the existing operator queue.

This is **verification observation evidence**, not review evidence and not a substitute for required independent verification.

### 13.1 Authoring and authority

A model may propose the validation script/procedure.

Before execution, the operator must approve:

- the target host;
- the full rendered script/procedure content;
- the intended action;
- the capture schema.

Approval of a digest alone is insufficient.

`target_host` must resolve through the operator-pinned host/target registry.

The operator channel transports operator intent; executing a model-proposed script is not authorized until that content is explicitly approved.

### 13.2 Secrets and capture

Secret inputs are supplied through explicit secret-input channels/placeholders and are never persisted in evidence.

AEW persists **only** fields explicitly listed in the result-capture schema.

Raw stdout/stderr is not persisted by default.

Unrecognized/unstructured output remains transient unless separately admitted.

Captured values are treated as untrusted data.

### 13.3 Requirement-to-step map

The engine may deterministically check:

```text
every required requirement id has >=1 mapped validation step
```

It does **not** claim that the mapped step actually proves the requirement.

Adequacy remains subject to review/verification judgment.

---

## 14. Delta-review packet

Separate deterministic/derived data from claims.

### Engine-derived

```text
prior finding ids/status
base/reviewed revision
engine-computed diff/hunks
files/locations changed
```

### Qualified derived, with provenance

```text
known callers/dependencies affected
structural impact
```

only where a qualified T5/F30 source supports them.

There is no engine-derived `assumptions touched` field unless assumptions are themselves represented as structured, engine-addressable plan/interface records. Otherwise it is omitted from engine-derived output.

### Claims

```text
implementer finding-to-fix map
claimed assumptions affected
claimed semantic intent
```

Claims are labelled as such and never promoted to evidence merely by inclusion.

Harness-native reviewer continuation remains optional/F24-qualified.

---

## 15. Nit / observation correction loop

AEW uses the canonical engine severity vocabulary.

Project-local `nit` is presentation terminology only.

An operator-pinned mapping may map project `nit` to canonical:

```text
observation
```

and may never remap blocker/major/minor downward.

The cheap post-CLEAR path applies only when all remaining requested corrections are canonical `observation` findings permitted by policy.

Flow:

```text
CLEAR + eligible observation corrections
    -> author applies corrections
    -> one cheap delta review
```

The delta review examines the full engine-computed delta, not merely named lines.

If the delta review discovers:

- any blocker/major/minor finding;
- a behavioral change outside the expected correction;
- another required correction cycle;

the work returns to the normal review path.

This fast path is bounded to one post-CLEAR correction/re-review cycle.

No executable/non-executable evidence carry-forward shortcut is introduced by this design.

---

## 16. Plan underspecification

Owned by F14.

No plan-length score exists.

Initial signals:

1. structured `mechanisms[]` fields filled or `n/a: reason`;
2. review discovers a material schema, registry key, reason code, error class, authority owner, or mechanism invented during implementation but absent from the accepted plan;
3. worker reports `design_decision_required`.

`n/a: reason` is an author claim/advisory field, not authoritative proof that a dimension is irrelevant.

Review may challenge it.

---

## 17. Engine-behavior citation rule

Claims about current engine behavior used as premises for implementation fixes or designer decisions must cite the current code basis.

Mechanically AEW may verify only that the referenced:

```text
path
symbol
test
revision
```

exists/resolves at the cited base commit.

Whether the cited code actually supports the prose claim remains a review/judgment question.

Owners:

```text
builder / fix claims
    -> launch-contract / role-card + review protocol

designer brief current-state claims
    -> designer-brief process
```

---

## 18. Field-log disposition table

Every source field-log item receives an explicit disposition.

| Entry | Disposition / owner |
|---|---|
| #1 review nits | Review protocol; canonical observation + bounded delta re-review |
| #2 zombie outside AEW | Corrected: outside AEW; E13 already owns AEW process-tree reaping |
| #3 progress signal | U1/H1; add two fields |
| #4 test scope | Launch-contract / test-policy owner |
| #5 concurrency forecast | Overlap projection |
| #6 merge collisions | Overlap projection + mechanical merge where qualified |
| #7 plans as governed work | WC/F14 reviewed-plan contract |
| #8 cross-plan drift | Section binding + interface dependencies |
| #9 reviewer posting | Built as typed review submission; no new work |
| #10 public/private review | Review-artifact policy follow-up |
| #11 operator steps | `operator_validation` + operator queue |
| #12 operator waiting queue | Existing operator-attention / dashboard owner |
| #13 context compaction reconstruction | Fine as designed under **C1 Context Continuity / designer ruling of 2026-10-10**; no new work |
| #14 config/security masks | Built/owned by containment masks; no new work |
| #15 disk budget | Doctor/workspace-retirement owner |
| #16 CI external check | External-check / `wait --any` integration candidate |
| #17 thin plan / invented semantics | F14 underspecification signals |
| #18 engine-behavior claim in fix | Served engine facts + citation rule / review protocol |
| #19 engine-behavior claim in designer brief | Designer-brief citation rule |
| #20 PR lifetime | Evaluator/process metric candidate |
| W1 fresh reviewers | Existing independence design validated |
| W2 reviewer continuity | Delta-review packet / F36 extension; harness resume optional |
| W3 stable finding ids/fix map | Existing review protocol + delta packet |
| W4 frozen review tree/repros | Existing evidence/review design |
| W5 operator scripts | `operator_validation` |
| W6 notifications | Existing `wait --any` direction |
| W7 live worker messaging | F9-A |
| W8 dependency-based slicing | Plan/dependency graph + overlap projection |

No entry is silently dropped.

---

## 19. Owner / amendment table

| Behavior | Authoritative owner | Required change | Freeze/activation status |
|---|---|---|---|
| Mandatory reviewed Story/Epic plan, including Class 0 | Workflow Contract + F14 | WC/F14 amendment incl. Class-0 parent path | **Must exist before activation** |
| Planning-child exemption | WC/F14 + M6a/launch policy | Engine-derived purpose/effect allow-list | Design frozen; implementation pending |
| Plan proposal/review/adoption | WC/F14 + review protocol | Reviewed-plan record contract | Must be specified before activation |
| Section-level plan binding | E19-B + F5 | Section digest binding | **Prerequisite** |
| Interface-dependency edge | Workflow Contract §8 + E19-B | New non-blocking edge kind | **WC amendment required** |
| Interface digest/hold | E19-B + F9 | Engine-computed interface digest on edge | Pending implementation |
| Overlap projection | F22.3/T5 + work graph | New read-only projection | Pending |
| Lead wake | F9 / D5 | Existing coordination lane integration | Existing owner |
| Run health | U1/H1 | Two sanitized fields | Pending |
| Operator validation | Evidence + operator queue | New evidence kind/schema | Pending |
| Delta review | Review protocol + F36 | Delta packet | Pending |
| Nit/observation fast path | Review protocol | Canonical mapping + bounded delta review | Pending |
| Underspecification | F14 | Three deterministic/advisory signals | Pending |
| Engine behavior citations | Role/brief/review process | Citation requirement | Pending |

**Designer ruling on freeze vs activation:** this design may freeze before the WC/F14/WC§8 amendments are merged. However, the affected behavior is **not activatable** until the required governing amendment exists and the activation gate verifies it. This supersedes the earlier v0.3 review suggestion that the amendment must exist before conceptual freeze.

---

## 20. Checkable acceptance criteria

| # | Requirement | Check |
|---|---|---|
| 1 | No duplicate lifecycle | Schema test: no new parent work-state enum; `plan_phase` derived only |
| 2 | No planner recursion | Dispatch fixture: qualifying planning child launches with assignment as plan |
| 3 | No label bypass | Fixture: child labelled planner but mutating effect set -> exemption denied |
| 4 | Mandatory parent planning | Fixture: Class-0/1/2+ Story/Epic mutating child dispatch refused without reviewed plan |
| 5 | Independent plan review | Fixture: proposer cannot satisfy reviewer/adopter slots |
| 6 | Plan review binding | Fixture: review sha != proposal sha -> adoption refused |
| 7 | Section binding | Fixture: unconsumed section change leaves child current; consumed digest change stales |
| 8 | Reconfirm safety | Fixture: subtree reconfirm carries no evidence; integrated affected work needs reverify |
| 9 | Parallel interface edge | Fixture: interface consumer dispatches before provider DONE when digest current |
| 10 | Contract drift | Fixture: provider publish changes interface without accepted contract revision -> refuse |
| 11 | Hold authority | Fixture: held worker cannot clear its own hold |
| 12 | Interface rename/remove | Fixture: rename/removal holds all named consumers |
| 13 | Undeclared residual | Documentation + test proving hard protection applies to **declared interfaces** only; undeclared relationships rely on integration validation and parent verification, and publish-overlap remains advisory |
| 14 | Wake coalescing | Fixture: latest fact coalesces; post-ack later fact produces new wake |
| 15 | Wake not authority | Fixture: lost wake does not clear hold |
| 16 | Health no authority | Fixture: health advisory cannot transition/kill/relaunch |
| 17 | Health sanitization | Fixture: secrets/args absent from process field |
| 18 | Operator validation authority | Fixture: model-authored script cannot run before full operator approval |
| 19 | Operator validation capture | Fixture: only capture-schema fields persist; raw output/secret absent |
| 20 | Requirement-step claim bound | Check only coverage, never adequacy |
| 21 | Delta provenance | Schema test separates engine/qualified-derived/claim fields |
| 22 | Nit loop bounded | Fixture: second correction cycle returns normal review |
| 23 | Design-decision reason | Fixture: worker report wakes Lead but cannot transition state |
| 24 | Citation rule | Fixture: cited path/symbol must resolve; semantic support remains review |
| 25 | Every field-log item disposed | Static table coverage #1-#20 and W1-W8 |
| 26 | Governing amendments present | Activation gate checks required WC/F14/WC§8 amendments |

---

## 21. Repository-process divergence: nit handling

The AEW product rule in §15 is intentionally stricter than the repository's current AGENTS.md process adopted in PR #181.

Current repository process may allow:

```text
CLEAR + nits
    -> author fixes
    -> "Nits fixed at <sha>"
    -> no new review
```

AEW product behavior requires one bounded delta review.

This divergence is deliberate for now and must be recorded as such. When the AEW product rule ships, the repository dogfood process should either:

1. align AGENTS.md to the product rule; or
2. retain the difference through an explicit documented project-policy exception.

It must not remain an accidental mismatch.

---

## 22. Freeze disposition

**Concept: FROZEN.** The closure review returned FREEZE WITH CORRECTIONS, and those corrections are incorporated here. Activation remains gated by the amendments and qualification conditions named in §19–§20.

The central decisions are now explicit:

1. every Epic/Story, including Class 0, has a reviewed accepted plan;
2. planning/research children cannot bypass this via labels—the exemption is engine-derived from admitted purpose and non-mutating authority;
3. section-digest binding is mandatory;
4. parallel assumption relationships use a new non-blocking `interface_dependency` edge;
5. E19-B remains the sole authority-bearing invalidation mechanism;
6. wakes are advisory delivery only;
7. held workers cannot clear their own holds;
8. operator validation cannot launder model authority;
9. delta review keeps engine facts separate from claims;
10. the field log is fully dispositioned and owner-linked.
