# Workflow Contract / F14 amendment: mandatory reviewed parent plans, Class 0 included, and parent-plan interactions

**Version:** v0.1

**Status:** Proposed for designer adoption, 2026-10-11. Not governing: it replaces no Workflow Contract text, and
changes no F14 text, until the designer adopts it. Written now by the designer's Q6a of 2026-10-11 ("ACTIVATION
AMENDMENTS: DO NOW"; [AIR](decisions-2026-10-11-architecture-integration.md) §1, ledger AIR-07), and reviewed together
with its companion, the [WC §8 / E19-B interface-dependency amendment](wc8-e19b-interface-dependency-amendment-v0.1.md).

**Date:** 2026-10-11

**Amends (on adoption):** Workflow Contract v0.7 §7.5 (minimum paths), §8 (the transition rule on starting mutating
work) and §9.6 (plan revision); the [plan assurance design v0.4](plan-assurance-and-premise-validation-design-v0.4.md)
(F14) its **Authority** header line, §5 (the Lead's authority over accepted plan revisions), §13, §17, §17.1, §18 and
§21. ADR-0007's `parent_paths` default and the meaning of its `accepted_plan` gate change with it, and need an amendment
section in ADR-0007 when F41.2 builds them (§10).

**Basis:** the [cross-feature integration design v0.5](cross-feature-integration-design-v0.5.md) (frozen 2026-10-10)
§2 to §4, §6, §19 and §20; its [freeze record](decisions-2026-10-10-cross-feature-integration-freeze.md) §3; the
[architecture integration decisions](decisions-2026-10-11-architecture-integration.md) (AIR) §1 Q4 and Q6a, §3.1,
§3.7, §3.18 and §3.19.

**Register:** F41.1 (this amendment), F14.1 (the parent plan's `interactions[]` and the composition rule); built by
F41.2.

## 1. Purpose and scope

v0.5 makes a reviewed, accepted plan mandatory for every ancestor Epic and Story, Class 0 included (v0.5 §2), and says
that this changes `parent_paths["0"]` and needs a Workflow Contract / F14 amendment before activation (v0.5 §2, §19).
The designer's Q4 and its acceptance (AIR §3.7) put the reviewed parallelism verdict and the permanent composition rule
into the same parent-plan contract. This document is that amendment. It writes into the governing texts what v0.5 and
AIR already decided; it decides nothing new. Where they leave a material choice open, §14 asks the designer.

It covers:

- the parent path: a Story or Epic of any class, Class 0 included, has a reviewed accepted plan (§3);
- the dispatch guard: no mutating descendant starts without it, as one input to the single `DispatchDecision` (§4);
- the reviewed parent-plan record: proposal, independent review bound to the proposal, adoption by someone other than
  the proposer, and the minimal plan (§5);
- the parent plan's `interactions[]`, carrying the parallelism verdict (§6), the lint that runs when a parent plan is
  accepted (§7), and the composition rule (§8);
- the matching F14 text (§9), policy and migration (§10).

It does not cover the `interface_dependency` edge or its hold; those are the companion amendment's. Section-digest
binding (v0.5 §6, register F41.4) is referenced, not amended here.

## 2. Activation condition

The cross-feature integration design v0.5 activates only when all of these hold, and its activation gate (v0.5 §20
check 26, register F41) verifies them:

1. **both** Q6a amendments exist as adopted governing amendments: this one and the companion WC §8 / E19-B
   amendment. The designer's ruling: "Review together, activate v0.5 only after both exist" (AIR §1 Q6a, AIR-07; the
   freeze ruling, v0.5 §19, requires that "the required governing amendment exists and the activation gate verifies
   it");
2. **F45, base-drift integration validation, is built and its policy is adopted.** AX-01 is a precondition of
   activation (AIR §3.1, AIR-09): v0.5 §9's claim that integration validation covers undeclared relationships holds only
   with F45. A project activated under v0.5 may not leave `gates.post_integration.base_drift_overlap` absent or
   disabled; migrating a project to v0.5 needs the explicit adoption of that policy value, and the activation gate
   verifies that the protection is on (AIR §3.1, "Migration and activation", AIR-12; the order of work, AIR §3.19,
   AIR-75).

The other preconditions the register already tracks stand unchanged: section-digest binding (F41.4, a prerequisite,
v0.5 §6), the `non_mutating_paths` policy migration for the planning-child exemption (F41.3, v0.5 §3.1) and the order
of AIR §3.19 (F44, then F43, then F45). This amendment adds none and removes none.

Until activation, nothing here changes how AEW behaves.

## 3. Amended WC §7.5: parent paths

WC §7.5 lists the Ticket paths and the class paths; it has no Story or Epic path, and today's parent gates live in the
engine's `parent_paths` policy (ADR-0007: Class 0 `[children_complete]`; Classes 1 to 4 add `accepted_plan`, review and
verification). This is an extension of WC §7.5. A new paragraph after the Class 4 path:

> **Story / Epic, any class, Class 0 included:** a reviewed, accepted plan → children dispatched under it → children
> complete → the Story's or Epic's own acceptance gates for its class → closed by the Lead. The plan is mandatory at
> every class because Story and Epic identity means governed multi-step work: AEW avoids planning ceremony at Ticket
> granularity, never by planless parent work. A Class-0 Story or Epic may use a thin plan (§9.6). No mutating
> descendant is dispatched while an ancestor Story or Epic has no current reviewed, accepted plan (§8).

"Reviewed, accepted" has one meaning for every class: the plan phase is `plan_accepted_current` (§5.5). Today's
`accepted_plan` gate on a Class 1 to 4 parent is satisfied by the Lead's own `plan accept` with no review; after this
amendment it is satisfied only by a reviewed, adopted plan (v0.5 §2.1, §4.1, §4.2), so the change reaches every class,
not only Class 0. Ticket planning is unchanged: a separate Ticket plan stays conditional (v0.5 §5).

The planning-phase exemption keeps this from recursing: a planning or research child whose admitted purpose and resolved
effect envelope qualify (v0.5 §3, engine-derived, never a label) is dispatchable without the parent's plan, and its
assignment is its own plan (v0.5 §3.2). The exemption's policy migration is register F41.3, not this amendment.

## 4. Amended WC §8: starting mutating work

WC §8's first transition rule reads:

> - a mutating Ticket may start only when its dependencies and governing plan/assignment are accepted;

It is extended by a new rule directly after it:

> - "governing plan" includes the plan of every ancestor Story and Epic: a mutating Ticket may start only when each
>   ancestor's plan phase is `plan_accepted_current` and the Ticket's dispatch records its binding to those plans (the
>   section binding of the cross-feature integration design v0.5 §6). The check is one input to the single shared
>   dispatch predicate (F14 §17.1's `DispatchDecision`), never a second dispatch engine, and every dispatch route
>   reaches it.

A Story's or Epic's state stays derived (WC §8: "Parent state must not be independently hand-maintained"). The plan
phase is derived from durable plan records too; no parent work state is added (v0.5 §2, §20 check 1).

## 5. Amended WC §9.6: the reviewed parent-plan record

WC §9.6 says: "Contains the implementation contract and dependency graph. Accepted revisions are immutable." That
stands. For a Story or Epic it is extended with the record contract of v0.5 §4, which a plan revision follows from
proposal to adoption. A plan is governed evidence, never a child Ticket lifecycle (v0.5 §4).

### 5.1 Proposal

A parent plan revision is proposed by a planning child (the existing Planner `plan_proposal`, adopted onto the unit as a
proposed revision) or by the unit's Lead through the unit's plan-proposal path (v0.5 §4). The engine records the
proposer's admitted identity and the proposal's sha256 over its canonical content.

### 5.2 Review

A proposal is reviewed only when all three hold (v0.5 §4.1):

```text
R1 review = PASS
open required findings = 0
review bound to the proposal's sha256
```

The reviewer is independent under the existing reviewer-visibility rules and is never the proposer. Additional review
multiplicity stays with the existing risk policy (v0.5 §4.1). A review bound to a different sha256 does not count
(v0.5 §20 check 6).

### 5.3 Adoption

The adopter is never the proposer (v0.5 §4.2). The normal path is: a planning child proposes, an independent reviewer
passes, the Lead adopts. A plan the Lead proposed is adopted by the operator, or by a Lead generation whose admitted
identity differs from the proposer's as the control model records it; a takeover or re-attach that re-admits the same
agent identity does not count. The engine never treats proposal plus self-review or self-adoption as sufficient.

### 5.4 Minimal content, Class 0 included

Every parent plan states at least (v0.5 §4.3):

```text
objective
governing requirements / acceptance criteria
intended decomposition or execution sequence
known dependencies/interfaces
verification method
```

A Class-0 Story or Epic may state them thinly. Length is never a quality signal. The decomposition is structured: each
entry has a stable id within the plan, and a child created from an entry records it (v0.5 §6's "its structured
decomposition entry"). **One decomposition entry creates exactly one child**; work that needs several children is
written as several entries. A ref to an entry resolves to that one child at dispatch (§6.3), so an entry with two or
more children would make every condition naming it false (§14's P8). Where the plan introduces or changes a material interaction between entries, it carries
`interactions[]` (§6).

### 5.5 Derived plan phase

The phase is derived, never stored as a work state (v0.5 §2.1):

```text
no_plan | plan_proposed | plan_under_review | plan_rejected |
plan_accepted_current | plan_accepted_stale | plan_superseded
```

`plan_accepted_current` needs a reviewed, adopted proposal (§5.2, §5.3) that has not become non-current under v0.5
§2.1. A replacement under review does not revoke the current plan; descendants bound to it continue under it unless an
existing authority suspends the unit (v0.5 §2.1, §6.2).

## 6. The parent plan's `interactions[]` (F14.1)

F14's permanent composition-prevention rule is represented in the parent plan, inside this same parent-plan contract,
never a second plan contract (AIR §3.7, AIR-29). It is where Q4's reviewed parallelism verdict lives (AIR §1 Q4,
AIR-05).

### 6.1 Field shape

A parent plan lists structured `interactions[]` between sibling slices or work units wherever a material interaction
exists. The shape, as the acceptance gives it (AIR §3.7):

```text
interactions:
  - between: [T-A, T-B]
    dependency_refs: [...]
    interface_refs: [...]
    shared_surfaces: [...]
    allocated_identifiers: [...]
    parallelism: PARALLEL_ALLOWED | SERIAL_REQUIRED | CONDITIONAL
    conditions: [...]
    rationale_refs: [...]
```

Every ref is written in **plan terms**, because a plan is first accepted before the children it decomposes into exist
(§5.4: children are created from entries after adoption):

- `between` names two sibling slices or work units (AIR §3.7): each is an entry of this plan's structured
  decomposition (§5.4) or an existing child work unit of this Story or Epic, such as an in-flight child with no entry
  id (§10). An entry resolves within the plan; an existing child must exist when the plan is accepted. Both are resolved
  again at dispatch, and one that no longer resolves then (a cancelled or moved child) makes every condition naming it
  false, as §6.3 provides;
- `dependency_refs` name dependencies the plan declares between its entries (its "known dependencies" content, §5.4),
  or an existing work unit or edge outside this plan's decomposition, which exists when the plan is accepted;
- `interface_refs` name interfaces by their canonical source (v0.5 §7.2). An interface the plan declares resolves within
  the plan. Whether another explicitly governed interface artifact may be named, and how it resolves, is the companion
  amendment's open question I1; this amendment does not answer it, and until it is answered only plan-declared
  interfaces resolve;
- `shared_surfaces` name paths, globs or project-policy surfaces (v0.5 §10's register, schema and config surfaces); a
  surface may be one the plan's work will create, so it is checked for form and policy membership, never for
  existence in the tree;
- `allocated_identifiers` name namespaces the project's policy declares (v0.5 §10: project policy data, not an
  AEW-global list);
- a condition's refs follow §6.3.

The engine resolves a plan-term ref to the created child, or to its edge, only when it evaluates it at dispatch (§6.3).
Nothing else is added to the shape. A disposition that an engine-detected interaction is not
material (§7 check 6, §8) is a separate plan-level record that names the pair and its rationale; it is not an
`interactions[]` entry and not a fourth `parallelism` value, and its field shape is an implementation choice (F41.2).

### 6.2 The parallelism verdict

- **`SERIAL_REQUIRED`** is a governing scheduling constraint. It compiles to the existing blocking dependency semantics
  (WC §8: the consumer waits for the provider's `DONE`); it adds no new kind of ordering.
- **`PARALLEL_ALLOWED`** is permission only. It never forces concurrency, and it relaxes nothing: WC §8.1's isolation
  rules, every dependency and every gate still apply.
- **`CONDITIONAL`** permits concurrency only while its named conditions hold (§6.3).

A pair of entries with no `interactions[]` entry keeps today's behaviour: the Lead may run them concurrently when the
dependency graph and WC §8.1 allow it.

### 6.3 Closed conditions

A `CONDITIONAL` verdict governs only through conditions that are closed, engine-evaluable predicates (AIR §3.7, AIR-30).
A condition is a typed record, `{kind, refs}`, whose `kind` is one of a registered, versioned set. Its `refs` are in
plan terms (§6.1): a decomposition entry id or an existing child named in `between`, an interface `interface_refs` may
name, a named path set or allocated-identifier namespace, or an existing work unit outside the plan. The acceptance names three:

```text
interface_digest_current   an accepted interface digest is still current
                           (defined by the companion amendment, its §7)
overlap_set_empty          a specified overlap set is still empty
dependency_state           a named dependency state holds
```

`overlap_set_empty` evaluates, from committed and admitted facts only, whether a named set of paths or allocated
identifiers is disjoint from what the named unit's work (an entry's child or an existing child) has admitted or published (v0.5 §7.3: only committed or
accepted facts change authority; workspace-level likely changes are advisory). `dependency_state` evaluates whether a
named unit's work (an entry's child or an existing child), or a named existing unit outside the plan, is in a named
workflow state.

**Two-phase resolution** (the Lead's proposal, for adoption: §14's P8):

- **At plan acceptance,** lint checks only that each ref resolves *in plan terms* (§6.1): an entry is in the plan's
  decomposition, an existing child named in `between` is a child of this unit, the interface is one `interface_refs`
  may name, the namespace is one the project's policy declares, a path set is well formed. A ref to an existing unit,
  inside or outside the plan's decomposition, must exist then. No ref has to name a child or an edge, which do not exist yet.
- **At dispatch,** the engine resolves each ref to engine records: an entry id to the child created from that entry
  (§5.4: the child records its entry), an existing child to itself if it is still a child of this unit, an interface to
  that child's `interface_dependency` edge (the companion
  amendment, its §7.1). How children and edges come to exist is unchanged by this: the Lead creates them, or the
  engine compiles them from the accepted plan, as §14's P2 and the companion's I6 ask.
- **A ref that does not resolve at dispatch makes its condition false.** It is never skipped and never passes: an entry
  with no created child, more than one child for one entry (§5.4 forbids it), an existing child that was cancelled or
  moved, a child with no edge for the named interface, or an
  unreadable record each evaluates false.

The predicate stays closed and engine-evaluable (AIR §3.7): its kinds are registered, its refs are typed, and its value
is computed from recorded state. An unknown or unevaluable condition counts as not holding (fail closed). Free text in `conditions` is refused; an
explanation goes in `rationale_refs`, which may explain a plan but never governs scheduling.

The engine evaluates a `CONDITIONAL` interaction when either side's work is dispatched, as part of the same
`DispatchDecision`, recomputed against the current revision and never cached (F14 §17.1). While a condition does not
hold, concurrency is not permitted: the side's work that would start while the other's is dispatched and neither
`DONE` nor `CANCELLED` is refused, with the failing condition as its reason. What happens when a condition stops
holding after both have started is §14's question P3.

### 6.4 No coupling score

There is no model-generated coupling score, in any field (AIR §1 Q4, AIR §3.7). The engine supplies deterministic
dependency, interface and overlap evidence; plan review judges the verdict.

## 7. Parent-plan lint at acceptance

Parent-plan lint runs when a parent plan is accepted, not only when a descendant is dispatched (AIR §3.7, AIR-31;
today plan acceptance runs no lint, register F14.1). Adoption is refused while a lint finding stands. The deterministic
checks are at least:

1. the plan has the minimal content of §5.4, and its decomposition entries have unique ids;
2. every `interactions[]` entry is well formed: `between` names two distinct sibling slices or work units in plan terms
   (§6.1: entries of this plan's decomposition or existing children of this unit);
   `parallelism` is one of the three values; every ref resolves in plan terms (§6.1), never by requiring a child or an
   edge that is created after adoption;
3. a `CONDITIONAL` entry has at least one condition, and every condition has a registered kind and refs that resolve
   in plan terms (§6.3); none is free text;
4. the `SERIAL_REQUIRED` constraints, together with the existing blocking dependencies they meet, form no cycle;
5. every `allocated_identifiers` entry names a namespace the project's policy declares;
6. every pair of sibling units in plan terms (entries, or existing children) for which the engine finds deterministic evidence of interaction (overlapping declared scopes,
   a shared allocated-identifier namespace, or an interface one names and the other provides, all in plan terms, with
   no dependency the plan declares between them) has an `interactions[]` entry or an explicit disposition in the plan that it is not material, with its
   rationale (§8).

Where an entry or an existing child declares no scope, the engine reports its overlap coverage as unknown to the plan's reviewer, never as
empty (v0.5 §10). The lint reports evidence; the reviewer judges whether an interaction is material and whether the
verdict is right.

## 8. The composition rule

**A Story or Epic is not plan-complete until every material cross-feature interaction its plan introduces or changes is
connected to an existing owner or explicitly dispositioned** (AIR §3.7, AIR-32). Connected means an `interactions[]`
entry whose refs reach an existing owner, in plan terms (§6.1): a dependency the plan declares or an existing edge, an
interface the plan declares (which the companion amendment's edge binds once the consumer exists), a shared surface,
or an allocated-identifier namespace. Dispositioned means the plan records that the interaction is not
material, with its rationale, and the plan's independent review accepts it.

It is enforced through F14's parent-plan assurance (the lint of §7 and the review of §5.2), not on ordinary Tickets.
A plan that is not plan-complete cannot reach `plan_accepted_current`.

It is the first of the four layers of composition enforcement (AIR §3.18): plan (this rule), structural (F44's owner
registry), independent audit, operational feedback (F42). No cross-cutting authority owner is created.

## 9. Amended F14 (plan assurance design v0.4)

- **The Authority header line and §5, the Lead:** "The Engineering Lead remains the sole authority for accepted plan
  revisions" and §5's "accepted plan revision" under the Lead are amended for a Story's or Epic's plan: the Lead adopts a
  plan someone else proposed (the normal path), but a plan the Lead proposed is adopted by the operator or by a Lead
  generation with a different admitted identity (§5.3, v0.5 §4.2). The Lead still owns workflow state and dispatch; no
  assurance role gains planning authority. This is an authority change, and §14's P9 asks the designer to confirm it.
- **§13, plan construction:** for a Story or Epic plan, the minimum content adds the structured decomposition with
  entry ids (§5.4) and `interactions[]` where a material interaction exists (§6).
- **§17, the derived predicate:** item 2, "required parent obligations are referenced", is extended: every ancestor
  Story's or Epic's plan phase is `plan_accepted_current` and the dispatch binds to it (§4); and, for work governed by a
  `CONDITIONAL` interaction, its conditions hold (§6.3). Plan acceptance, which §17 already names as a point of
  evaluation, runs the parent-plan lint (§7).
- **§17.1, `DispatchDecision`:** the parent-plan guard and the interaction checks are among its `blocking_conditions`,
  with durable reason codes (named by the implementation, F41.2). They are inputs to the one predicate every dispatch
  route calls, not a second engine. An old ALLOW is never cached.
- **§18, deterministic plan lint:** the checks of §7 are added, and they run at parent-plan acceptance.
- **§21, hierarchical assurance, "Parent level":** a Story or Epic also establishes the interactions between its
  children and their verdicts; parent closeout still verifies composed behaviour (§21: "Passing children do not prove the
  composition is correct").

## 10. Policy and migration

- **The parent path policy.** The engine's `parent_paths` gains `accepted_plan` at Class 0 (v0.5 §2:
  `parent_paths["0"]`), and `accepted_plan` on every parent path is satisfied only by `plan_accepted_current` (§3).
  ADR-0007 documents today's default and the Lead-accepted meaning of the gate; when F41.2 builds this, ADR-0007 gets an
  amendment section saying so, never a silent edit.
- **Projects.** A project activated under v0.5 has `accepted_plan` on its parent path at every class; the activation
  gate verifies it, and a project policy that omits it cannot be activated. A project not activated keeps its current
  policy and behaviour. How a new project gets the value is §14's question P5.
- **In-flight parents** (v0.5 §4.4): at adoption, already-active admitted descendant attempts continue under their
  attempt authority; their forward gates and publish wait for the parent's reviewed plan and a recorded binding (v0.5
  §6); no new mutating descendant is dispatched until the parent has a reviewed accepted plan; planning and research
  children stay dispatchable to produce it.

## 11. Invariants

1. Every ancestor Story and Epic of a dispatched mutating Ticket, at every class, has a reviewed accepted plan, and the
   dispatch records its binding to it.
2. The plan phase is derived; no parent work state is added.
3. The proposer of a parent plan never fills its reviewer or adopter slot; a review counts only when bound to the
   proposal's sha256.
4. One dispatch predicate: the parent-plan guard and the interaction checks are inputs to `DispatchDecision`.
5. `SERIAL_REQUIRED` adds no ordering beyond the existing blocking dependency; `PARALLEL_ALLOWED` relaxes nothing;
   `CONDITIONAL` governs only through closed, engine-evaluable conditions, and an unknown condition does not hold.
6. No model-generated coupling score exists, and free text never governs scheduling.
7. A Story or Epic is not plan-complete while a material interaction its plan introduces or changes is neither connected
   to an existing owner nor dispositioned.
8. A label never grants the planning exemption; it is engine-derived (v0.5 §3).

## 12. Acceptance checks

v0.5's §20 checks 1 to 6 and 26 apply as written (ledger CFI-71 to CFI-76, CFI-96). This amendment adds:

| # | Check |
|---|---|
| A1 | Fixture: a Class-0 Story with no plan: mutating child dispatch refused; with a Lead-proposed, Lead-accepted, unreviewed plan: still refused |
| A2 | Fixture: a Class-2 Story whose plan was accepted by the Lead without review: `accepted_plan` is not met |
| A3 | Fixture: a planning child under a planless Story dispatches; a child labelled planner whose effect set mutates does not |
| A4 | Fixture: a review bound to an earlier proposal sha256 does not make the plan reviewed |
| A5 | Fixture: a takeover that re-admits the proposer's identity cannot adopt the proposer's plan |
| A6 | Lint fixture: a `CONDITIONAL` entry with only free-text conditions is refused at acceptance |
| A7 | Lint fixture: `SERIAL_REQUIRED` constraints forming a cycle with existing dependencies are refused |
| A8 | Lint fixture: two entries with overlapping declared scopes and neither an `interactions[]` entry nor a disposition are refused; with either, accepted |
| A9 | Fixture: a `SERIAL_REQUIRED` pair: the second entry's work is refused dispatch until the first is `DONE`, with the same reason a blocking dependency gives |
| A10 | Fixture: a `PARALLEL_ALLOWED` pair does not bypass WC §8.1 isolation or any gate |
| A11 | Fixture, plan-first: a parent plan with a `CONDITIONAL` pair on `dependency_state` (naming an entry) is accepted before any child exists; after the children are created, the condition false or unevaluable at dispatch refuses the second start; when it holds, allowed; an ALLOW computed earlier is not reused |
| A12 | Schema test: no field of `interactions[]` or the plan record carries a numeric coupling score |
| A13 | Lint fixture, plan-first: a first acceptance whose interactions and conditions name only decomposition entries, plan-declared interfaces, policy namespaces and new paths passes lint with no child in existence; a ref to an entry or interface the plan does not declare is refused |
| A14 | Fixture: a condition whose ref does not resolve at dispatch (an entry with no created child, a child with no edge for the named interface) evaluates false and the concurrent start is refused; it is never skipped |
| A15 | Lint fixture, in-flight parent: a plan whose `between` and conditions name an existing child alongside an entry passes lint; a `between` naming a unit that is not a child of this Story or Epic is refused; creating a second child from one entry is refused |

## 13. What stays unchanged

- WC §7.4: the classes, Class 0 eligibility and the Class 0 amendment. The Class 0 amendment's §9 item 4 stands: Class 0
  eligibility is still enforced for mutating Tickets only, and Stories keep their Class 0 paths for eligibility. This
  amendment adds the plan obligation to the Story and Epic path; it defines no Class 0 eligibility for a Story.
- WC §8: blocking dependency semantics, the Ticket states, controlled integration and `DONE`, and that only the Lead
  closes a Story or Epic.
- WC §8.1: concurrent mutation isolation. An interaction verdict never substitutes for isolation.
- Ticket planning (v0.5 §5) and the Ticket paths of WC §7.5.
- A parent's closeout gates other than `accepted_plan` (ADR-0007, whose `accepted_plan` gate and Class 0 default this
  amendment changes, §10), and parent review and verification of composed
  behaviour.
- Section-digest binding (v0.5 §6, F41.4), the planning-child policy migration (F41.3) and the interface edge (the
  companion amendment): each keeps its own owner.
- F14's `ASSURED` direction, classes and triggers.

## 14. For the designer

v0.5 and AIR leave P1 to P7 open; each is a question, not a decision taken here. P8 is the Lead's proposal, written into
§6.1, §6.3 and §7, for the designer to adopt or change; it is not settled until then. P9 asks the designer to confirm the
authority change of §9.

- **P1. The direction of `SERIAL_REQUIRED`.** `between: [T-A, T-B]` is a pair; a blocking dependency has a direction.
  Is the order of `between` significant (the first precedes the second), or does a `SERIAL_REQUIRED` entry name its
  order in another field? A candidate within AIR §3.7's shape is `dependency_refs`: a `SERIAL_REQUIRED` entry could name
  the directed dependency (declared in the plan or existing) it compiles to, so that its direction is the dependency's.
- **P2. How the compiled constraint follows plan revisions.** Is `SERIAL_REQUIRED` materialized as a declared blocking
  edge when the child is created (and then changed only by the existing edge-edit authority, which ADR-0007 limits to
  `BLOCKED`, `READY` and `REPLAN_REQUIRED` Tickets), or re-derived from the current accepted plan at each dispatch? The
  two differ when an adopted plan revision adds or removes a `SERIAL_REQUIRED` entry between children already started.
- **P3. A condition that stops holding mid-flight.** AIR §3.7 permits concurrency "only while its named conditions
  hold", so once both sides' work has started and a condition becomes false, the concurrency may no longer rely on
  it; v0.5 §11's advisory wake alone would not satisfy that. §6.3 defines only the refusal of a start. Which mechanism
  stops the reliance: a refusal of forward gates and progression for the side whose work started second (as if
  `SERIAL_REQUIRED` applied until the condition holds again), or an E19-B §7.5-style hold on forward gates and publish?
  For `interface_digest_current` the companion's hold already applies; the question is the overlap and
  dependency-state conditions.
- **P4. Is `interactions[]` a consumed section?** v0.5 §6 says a descendant "consumes every governing section by
  default", then lists the objective, the requirements, the interfaces it names and its own decomposition entry.
  `SERIAL_REQUIRED` is "a governing scheduling constraint" (AIR §3.7), which bears on the answer. Does it also consume the `interactions[]` entries
  that name it, so that a changed verdict stales its binding?
- **P5. The policy default for new projects.** AIR §3.1 settles F45's key: absent stays absent, `aew init` writes the
  governing value, activation requires its explicit adoption. Does the same rule apply to `parent_paths["0"]` and to
  `accepted_plan`'s stronger meaning, or does the built-in default change for every project at activation?
- **P6. Scope on decomposition entries.** The minimal plan (v0.5 §4.3) does not require an entry to declare a scope, so
  the overlap evidence of §7 check 6 is often unknown. Should a parent plan's entries declare scopes where they are
  known, or does lint coverage stay best effort with the reviewer judging the rest?
- **P7. The closed condition set.** The acceptance lists three conditions "for example". Is v1's registered set exactly
  those three, with any addition by amendment, or may project policy register more?
- **P8. Plan-term refs, resolved at dispatch (the Lead's proposal, for adoption).** A plan is first accepted before its
  children exist, so a ref that had to name a child or an edge at acceptance would make `interface_digest_current` and
  `dependency_state` on an entry unusable in the normal plan-first flow. Proposed (§6.1, §6.3, §7): refs are written in
  plan terms (a decomposition entry id or an existing child, a plan-declared interface, a policy namespace, a path set);
  lint at acceptance checks that they resolve in plan terms; at dispatch the engine resolves them to the child and its
  edge, and a ref that does not resolve then makes its condition false, never true. It needs one decomposition entry to
  create exactly one child (§5.4): if the designer allowed an entry to yield several children, every condition naming
  that entry would be permanently false under this rule, and refs would need another way to name the children. It interacts with P2 and the companion's I6
  (whether edges are compiled from the plan), not with whether a ref may fail open: under either answer it fails closed.
- **P9. The Lead's authority over parent plans.** F14's Authority line makes the Lead "the sole authority for accepted
  plan revisions"; v0.5 §4.2, written in here (§5.3, §9), has a Lead-proposed parent plan adopted by the operator or by
  another Lead generation. Is that the intended amendment of F14's header and §5 for parent plans, and is the
  operator's adoption of a parent plan made through the operator's existing out-of-band adoption channel?

## 15. Governing disposition

On adoption, this amendment becomes an overlay of the effective-spec index (`docs/spec-amendments.yaml`), with these
targets, each an extension that replaces no frozen text:

| Target | Part | Kind | By |
|---|---|---|---|
| WC §7.5 | Story / Epic paths, Class 0 included | extends | §3 |
| WC §8 | starting mutating work: the ancestor plans | extends | §4 |
| WC §9.6 | the reviewed parent-plan record, `interactions[]` | extends | §5, §6 |

The F14 changes of §9 amend an adopted design, not the frozen set; they are noted on F14 and F14.1, and ADR-0007 gets
its amendment section when F41.2 builds the change (§10). Until adoption it is a proposal: listed in `docs/README.md`'s
proposals table, and neither an overlay nor `considered` in the index.
