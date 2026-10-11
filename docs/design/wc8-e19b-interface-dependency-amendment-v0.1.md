# Workflow Contract §8 / E19-B amendment: the non-blocking interface_dependency edge and its revision-impact trigger

**Version:** v0.1

**Status:** Proposed for designer adoption, 2026-10-11. Not governing: it replaces no Workflow Contract text, and
changes no text of the Ticket-revision amendment, until the designer adopts it. Written now by the designer's Q6a of
2026-10-11 ("ACTIVATION AMENDMENTS: DO NOW"; [AIR](decisions-2026-10-11-architecture-integration.md) §1, ledger
AIR-07), and reviewed together with its companion, the
[WC/F14 parent-planning amendment](wc-f14-parent-planning-amendment-v0.1.md).

**Date:** 2026-10-11

**Amends (on adoption):** Workflow Contract v0.7 §8 (the work graph: dependency edges and their satisfaction); the
adopted [Ticket-revision amendment](workflow-contract-amendment-ticket-revisions-2026-10-06.md) (E19-B v0.4) §2.3 (field
groups) and §7.5 (downstream impact propagation), which are themselves the effective WC §7 and §8.

**Basis:** the [cross-feature integration design v0.5](cross-feature-integration-design-v0.5.md) (frozen 2026-10-10)
§7 to §9, §11, §19 and §20; its [freeze record](decisions-2026-10-10-cross-feature-integration-freeze.md) §2 and §3
(V-1(b)); AIR §1 Q4 and Q6a, §3.1, §3.7 and §3.19.

**Register:** F41.5 (this amendment); built by F41.6.

## 1. Purpose and scope

The designer chose V-1(b): blocking dependency edges keep their meaning, and AEW adds a separate, non-blocking edge kind,
`interface_dependency`, for a contract or assumption dependency between work that may run in parallel (v0.5 §7). v0.5
says the edge needs a Workflow Contract §8 amendment before activation, and that the same amendment extends E19-B §7.5's
`revision_impact_hold` trigger to accepted interface revisions on such edges (v0.5 §7, §19). This document is that
amendment. It also states how a `CONDITIONAL` parallelism verdict (the companion amendment, its §6) can depend on an
interface, through a condition the engine evaluates over this edge.

It writes into the governing texts what v0.5 and AIR already decided, and decides nothing new. Where they leave a
material choice open, §12 asks the designer.

E19-B stays the sole authority-bearing invalidation mechanism; no second invalidation system, lifecycle or coordination
channel is created (v0.5 §1, §8).

## 2. Activation condition

The cross-feature integration design v0.5 activates only when all of these hold, and its activation gate (v0.5 §20
check 26, register F41) verifies them:

1. **both** Q6a amendments exist as adopted governing amendments: this one and the companion WC/F14 parent-planning
   amendment. The designer's ruling: "Review together, activate v0.5 only after both exist" (AIR §1 Q6a, AIR-07; the
   freeze ruling, v0.5 §19);
2. **F45, base-drift integration validation, is built and its policy is adopted.** AX-01 is a precondition of
   activation (AIR §3.1, AIR-09). This amendment's hard protection covers declared interfaces only; undeclared
   relationships rely on integration validation and parent verification (v0.5 §9), and that reliance holds only when
   the validation obligation receives the base drift. A project activated under v0.5 may not leave
   `gates.post_integration.base_drift_overlap` absent or disabled; migrating a project to v0.5 needs the explicit
   adoption of that value, and the activation gate verifies the protection is on (AIR §3.1, AIR-12; AIR §3.19,
   AIR-75).

The other preconditions the register already tracks stand unchanged (section-digest binding, F41.4; the planning-child
policy migration, F41.3; the order of AIR §3.19). This amendment adds none and removes none. Until activation, nothing here changes how AEW behaves.

## 3. Amended WC §8: two kinds of dependency edge

### 3.1 Blocking edges keep their meaning

WC §8 says:

> A dependency is satisfied only when the upstream output required by the downstream assignment is durably accepted and
> actually available in the downstream assignment's recorded input/source snapshot.

That sentence, and everything WC §8 and §8.1 derive from it (a mutating dependency is satisfied only by integration,
`COMMIT_READY` does not unblock dependent mutation, `READY` follows satisfied dependencies), now applies to **blocking
dependency edges**, which are every dependency edge that exists today. Their meaning does not change:

```text
blocking dependency:
    consumer waits for provider DONE
```

### 3.2 The `interface_dependency` edge

A new paragraph after the one quoted above:

> **Interface dependencies.** A second kind of edge, `interface_dependency`, records that a consumer relies on an
> interface contract another unit provides, while the two may execute in parallel. It is never satisfied or unsatisfied
> in the sense above: it imposes no execution ordering, never keeps a consumer out of `READY`, and never counts towards
> the dependencies a downstream source snapshot must contain. It binds the consumer to the interface contract's current
> engine-computed digest, and the Ticket-revision rules hold the consumer when an accepted revision changes that digest.

The edge records (v0.5 §7.1):

```text
provider_work_id
consumer_work_id
interface_id
engine_computed_interface_digest
interface_source
```

The digest is computed by the engine, never supplied by an author (§4). The edge is declared on the consumer by the
existing dependency-edit authority, and it is part of the consumer's dependency field group (§5).

### 3.3 Dispatch of an interface consumer

The consumer may be dispatched while its provider is active when (v0.5 §7.1):

- the interface contract is current and accepted;
- the consumer is bound to its digest, and no `revision_impact_hold` on the edge is open (§6);
- every other dispatch requirement passes.

This is checked inside the single shared dispatch predicate (F14 §17.1's `DispatchDecision`), never by a second engine.

### 3.4 Publish: contract drift

If the provider's implementation changes the governed interface content so that the engine-computed digest differs from
the accepted interface contract, and no accepted interface revision exists, integration and publication of the
provider's work are refused (v0.5 §7.3):

```text
INTERFACE_CONTRACT_DRIFT
    -> integration/publish refusal
```

Implementation cannot silently change the contract under active consumers. Workspace-level likely interface changes may
produce advisory overlap candidates, but only committed or accepted contract facts change authority (v0.5 §7.3). How the
engine locates the governed interface content in the provider's change is §12's question I2.

## 4. The interface digest and its source

Digests are engine-computed from the canonical interface content and never author-supplied (v0.5 §7.2). The canonical
source may be an accepted parent-plan interface section, or another explicitly governed interface artifact (v0.5 §7.2;
which other artifacts qualify is §12's question I1). For a parent-plan section the digest uses the governed, versioned
section normalization of v0.5 §6.

An **accepted interface revision** is an accepted change of the canonical source that changes the digest of an interface
id: for a parent-plan section, the adoption of a plan revision under the companion amendment's reviewed-plan contract.
Renaming or removing an interface id is an interface change and affects every named consumer (v0.5 §7.2).

## 5. Amended E19-B §2.3: the edge in the consumer's dependency field group

E19-B §2.3 already puts declared dependencies in a governed field group "regardless of whether they are stored in the
Ticket file or control state". It is extended: an `interface_dependency` edge, with its bound digest, belongs to the
**consumer's** dependency field group.

Therefore rebinding an edge to a new digest is an E19-B revision of the consumer's dependency field group, not a free edge
edit; if the consumer has an active attempt, the revision follows E19-B §7.2's quiesce and commit before the new binding
becomes authoritative (v0.5 §8.2). Adding or removing an edge is the same kind of revision.

## 6. Amended E19-B §7.5: the trigger extended to accepted interface revisions

### 6.1 Trigger

E19-B §7.5 begins:

> A revision that changes acceptance, scope, or dependencies MUST produce a durable revision-impact record.

It is extended by a new paragraph after that sentence:

> An accepted interface revision (an accepted change of an interface contract's canonical source that changes the
> engine-computed digest of an interface id, or renames or removes it) also produces a durable revision-impact record,
> and applies `revision_impact_hold` to each **direct named consumer**: each consumer whose `interface_dependency` edge
> names that interface id and is bound to a digest other than the new one.

Its first bullet, "the overlay is applied only to a **direct explicit dependent** whose declared dependency binding could
be affected by the changed upstream revision", reads, for an interface revision, as the direct named consumer above. The
hold records the interface source and its accepted revision, the interface id, the consumer's bound digest and the new
one, the edge, the creation time and the exact obligation that clears it, in place of the upstream Ticket revision and
changed groups.

E19-B §7.5's existing rule for Ticket revisions also applies to a provider: a provider Ticket revision that leaves the
accepted interface's digest unchanged is mechanically proven to leave the consumer's bound input unchanged, so it holds no
interface consumer.

### 6.2 What the hold blocks

As E19-B §7.5 provides: the consumer's workflow state is unchanged, and the hold blocks new dispatch, forward gates and
publish that would rely on the affected interface (v0.5 §8). Active consumer invocations are not cancelled because the
hold exists; their results stay bound to the old digest and cannot satisfy affected progression. The hold does not fan
out: further propagation happens only if resolving it changes the consumer's own governed inputs.

### 6.3 Clearing and rebinding

The held worker can neither clear its own hold nor record either action that clears it (v0.5 §8.2). The hold clears when
both are recorded:

1. the Lead records the applicable disposition: `RECONTEXTUALIZE` when the Ticket can continue against the new interface
   with no change of plan or goal, `TICKET_REPLAN` when the new interface changes its plan or design assumptions (v0.5
   §8.1; `ADOPT_NEW_VERSION` is only a description of the action, not a new category); and
2. the engine records the consumer's binding to the new digest as E19-B §7.5's **attributable dependent update** (§5).

Clearing the hold makes no evidence current. Results of attempts admitted under the old digest stay bound to it.
Progression needs a new attempt admitted against the new digest; it may carry the prior workspace forward as input only
(E19-B §5.4), and needs fresh required review and verification under E19-B §5.2 (v0.5 §8.2). Whether the disposition
can be recorded when F9 messaging is off is §12's question I4.

## 7. The `interface_digest_current` condition

The companion amendment (its §6.3) lets a `CONDITIONAL` parallelism verdict govern only through closed, engine-evaluable
conditions, one of which is "an accepted interface digest is still current" (AIR §3.7, AIR-30). This edge is what makes
that condition evaluable.

### 7.1 Definition

```text
interface_digest_current(interface_id, consumer_entry)
```

Both refs are in plan terms (the companion amendment, its §6.1 and §6.3): `interface_id` is an interface the parent plan
declares, and `consumer_entry` is the id of the decomposition entry whose work consumes it. A parent plan is first
accepted before its children exist, so the companion's lint checks only that both resolve within the plan; it never
requires the edge (the Lead's proposal, for adoption: the companion's P8).

At dispatch the engine resolves `consumer_entry` to the child created from that entry, and the condition holds exactly
when all of these hold, each a fact the engine records:

1. exactly one child records `consumer_entry`, and it has an `interface_dependency` edge naming `interface_id`;
2. the edge's bound digest equals the engine-computed digest of `interface_id` in the currently accepted canonical
   source (§4);
3. no `revision_impact_hold` is open on that edge (§6).

A provider's `INTERFACE_CONTRACT_DRIFT` refusal (§3.4) does not change it: the refusal keeps the provider's change out,
and the accepted digest stays current.

It is false if any part is false, and false if any part cannot be evaluated (fail closed). In particular, an entry with
no created child, or a child with no edge for `interface_id`, makes it false at dispatch; it is never skipped and never
passes. Whether the edge is declared by the Lead or compiled from the plan's `interface_refs` when the child is created
is §12's I6; the condition fails closed under either answer.

### 7.2 Evaluation

The condition is evaluated inside `DispatchDecision`, at each dispatch of either entry's work, against the current
revision and generation; an ALLOW is never cached (F14 §17.1). Every input is recorded state: no model judgment, no
workspace-level guess, no coupling score.

### 7.3 Mid-flight

When an accepted interface revision makes the condition false while both entries' work is running, the consumer is
already held by §6: it cannot pass a forward gate or publish until the hold clears. The condition therefore needs no
separate mid-flight mechanism for interfaces. (For the other conditions the question is the companion's P3.)

## 8. Wakes

A wake is a nudge and never authority; losing one cannot make stale work valid (v0.5 §11). An accepted interface revision
that changes a digest a direct consumer names is an authoritative wake trigger (v0.5 §11, trigger 1), coalesced per
`(dependent, subject)` and delivered through the one decision-keyed Lead-attention lane of `wait --any`, whether or not
F9 messaging is on (v0.5 §11.1; AIR §3.3: that lane is F43's S3). This amendment adds no wake mechanism; the wake's owner
stays F9 and F43.

## 9. Invariants

1. A blocking edge's meaning is unchanged: the consumer waits for the provider's `DONE`.
2. An `interface_dependency` edge never orders execution and never keeps a consumer out of `READY`.
3. Interface digests are engine-computed from canonical content, never author-supplied.
4. A provider publish that changes the governed interface without an accepted interface revision is refused.
5. An accepted interface revision holds exactly the direct named consumers whose bound digest differs; it never fans out
   recursively.
6. A held worker cannot clear its own hold or record either action that clears it.
7. Clearing a hold makes no evidence current; progression needs a new attempt bound to the new digest.
8. Rebinding an edge is an E19-B revision of the consumer's dependency field group, quiesced when an attempt is active.
9. `interface_digest_current` is computed from recorded facts only and fails closed.
10. Hard interface protection covers declared interfaces only; undeclared relationships rely on integration validation
    (with F45) and parent verification, and publish overlap stays advisory (v0.5 §9).

## 10. Acceptance checks

v0.5's §20 checks 9 to 13 and 15 apply as written (ledger CFI-79 to CFI-83, CFI-85). This amendment adds:

| # | Check |
|---|---|
| B1 | Fixture: a consumer with only an `interface_dependency` edge on an active provider is `READY` and dispatches when the digest is current; the same pair with a blocking edge waits for `DONE` |
| B2 | Fixture: a downstream snapshot check ignores `interface_dependency` edges |
| B3 | Fixture: an author-supplied digest is ignored; the engine computes it |
| B4 | Fixture: an accepted plan revision changing an interface section holds exactly the consumers bound to the old digest, not their dependents |
| B5 | Fixture: a provider Ticket revision that leaves the interface digest unchanged holds no interface consumer |
| B6 | Fixture: the held worker's attempt to record the disposition or the rebinding is refused; the Lead's disposition alone does not clear the hold; with the engine's rebinding it does |
| B7 | Fixture: after the hold clears, a result admitted under the old digest does not satisfy a gate |
| B8 | Fixture: rebinding while a consumer attempt is active goes through E19-B quiesce and commit |
| B9 | Fixture: `interface_digest_current` is false when the edge is missing, the digest differs, a hold is open, or an input is unreadable; true otherwise |
| B10 | Fixture, plan-first: a parent plan declaring interface X and a `CONDITIONAL` pair on `interface_digest_current(X, E2)` is accepted before any child exists; the children are created from entries E1 and E2 and E2's child gets its edge on X; the pair dispatches in parallel while the condition holds, and the second start is refused after an accepted interface revision |
| B11 | Fixture: the same plan, with E2's child created without an edge on X (or with no child for E2): at dispatch `interface_digest_current(X, E2)` is false and the concurrent start is refused |

## 11. What stays unchanged

- Every existing dependency edge, its kinds and its satisfaction rule (WC §8), the Ticket states, and controlled
  integration.
- WC §8.1: concurrent mutating Tickets still need isolated workspaces; an interface edge never substitutes for isolation.
- E19-B's Ticket-revision trigger, its hold semantics for Ticket revisions, quiesce and commit, admissibility and
  carry-forward (§5.2, §5.4, §7.2): the interface trigger reuses them unchanged.
- Section-digest binding (v0.5 §6, F41.4): a consumer that consumes the interface section is also subject to it (§12's
  question I5).
- The overlap projection stays advisory (v0.5 §10), and v0.5 §11's publish-overlap wake (trigger 2) creates no hold.
- F9's dispositions keep their meaning; no new F9 category is created.

## 12. For the designer

v0.5 and AIR leave I1 to I6 open; each is a question, not a decision taken here. I7 points at the Lead's proposal,
written into §7.1, for the designer to adopt or change.

- **I1. Which interface sources are governed in v1.** v0.5 §7.2 allows "an accepted parent-plan interface section or
  another explicitly governed interface artifact". Is v1 limited to parent-plan interface sections? If not, what makes
  another artifact "explicitly governed", and what is its accepted revision?
- **I2. How drift is detected in the provider's change.** `INTERFACE_CONTRACT_DRIFT` compares "the governed interface
  content" after the provider's implementation with the accepted contract. When the canonical source is a parent-plan
  section, the provider's code does not change the plan text. Does an interface declare the source content its digest
  covers (paths or symbols in the tree), and if it declares none, is the drift check not applicable or is the interface
  refused?
- **I3. Who may be a provider or consumer.** May a Story or Epic be the provider or consumer of an `interface_dependency`
  edge, as blocking edges may (ADR-0007)? May two units hold interface edges on each other (non-blocking, so no cycle
  hazard)?
- **I4. The disposition without F9 messaging.** E19-B §7.5 "does not adopt F9 or depend on F9 becoming governing", while
  v0.5 §8.1 and §8.2 clear the hold through F9's `RECONTEXTUALIZE` and `TICKET_REPLAN`. Is the Lead's disposition an
  engine decision record available with messaging off (as the hold's wake is, v0.5 §11.1), or does clearing an interface
  hold need F9's disposition machinery to be built first?
- **I5. The hold and the section binding together.** An interface consumer that consumes the parent plan's interface
  section (v0.5 §6) is both held (§6) and stale-bound when that section changes. Here each clears by its own path. Should
  the hold's rebinding also count as the consumer's reconfirmation of that consumed section, or must both be recorded?
- **I6. Declaring the edge.** Is an `interface_dependency` edge declared only by the Lead's dependency-edit authority on
  the consumer, or also compiled from an accepted parent plan's `interactions[]` `interface_refs` when the child is
  created (the companion's question P2 for blocking edges)?
- **I7. Plan-term refs for `interface_digest_current` (the Lead's proposal, for adoption).** §7.1 takes the condition's
  refs in plan terms (a plan-declared interface and a decomposition entry), lints them within the plan at acceptance,
  and resolves them to the child and its edge at dispatch, false when they do not resolve. It is the companion's P8
  applied here; see also I6.

## 13. Governing disposition

On adoption, this amendment becomes an overlay of the effective-spec index (`docs/spec-amendments.yaml`). Its target on
the frozen set is an extension that replaces no frozen text:

| Target | Part | Kind | By |
|---|---|---|---|
| WC §8 | dependency edges: blocking and `interface_dependency`; the interface trigger of `revision_impact_hold` | extends | §3, §5, §6 |

Because E19-B's §2.3 and §7.5 are an adopted overlay (`ticket-revisions-2026-10-06`), the index entry for this amendment
names that overlay where it extends it. Until adoption it is a proposal: listed in `docs/README.md`'s proposals table,
and neither an overlay nor `considered` in the index.
