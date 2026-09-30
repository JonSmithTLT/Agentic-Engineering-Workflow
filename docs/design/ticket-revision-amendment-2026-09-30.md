# Ticket revisions: an amendment to the hierarchy revision design

**Status:** proposed 2026-09-30; reviewed in `ticket-revision-amendment-review-2026-09-30.md`, where the designer's decisions on it are recorded. Amends `hierarchy-intent-revision-and-replanning-design-v0.1.md`. The text below is the proposal as the operator posted it, unedited.

---

I think we want to amend the hierarchy revision design around Ticket mutability.

The original rule was roughly:

- Epics/Stories can evolve more freely.
- Tickets preserve proof.
- Once execution/evidence is bound, a material Ticket change should normally cancel/supersede the Ticket and create a replacement.

After thinking through the authority model more, I think that over-associates **proof preservation** with **Ticket-ID immutability**.

The actual invariant we care about is:

> Evidence must never silently cross a semantic revision boundary.

A Lead can already achieve the equivalent of “changing a Ticket” by cancelling it and creating a replacement Ticket with the wording/scope it wants. So forbidding first-class Ticket revision does not meaningfully constrain Lead authority; it mostly adds ceremony and fragments the work graph.

I think the better model is:

```text
Epic / Story
= approved purpose / execution envelope
= comparatively stable
= material changes may require stakeholder involvement

Ticket
= Lead-owned decomposition of that approved work
= expected to evolve as engineering understanding improves
= normally revisable by the Lead without stakeholder involvement

Ticket revision
= immutable historical snapshot

Evidence / plans / reviews / verification
= bound to the exact Ticket revision and dependency set they support
```

So a Ticket could remain `T-17`, but have:

```text
T-17@r1
T-17@r2
T-17@r3
```

with only one current revision.

When the Lead revises the Ticket, AEW performs impact analysis over everything attached to the previous revision.

Each dependent artifact should become something like:

```text
UNCHANGED
still admissible because it did not depend on changed semantics

REVALIDATE
may still apply, but AEW must establish that explicitly

INVALIDATED
cannot satisfy current gates

SUPERSEDED
replaced by a newer artifact

HISTORICAL
retained for provenance but not currently admissible
```

Typical consequences of a material Ticket revision:

```text
plan
→ normally invalidated

plan assurance
→ invalidated if the assured proposition/dependency set changed

review
→ invalid if it reviewed the old proposition

verification
→ invalid if acceptance changed

implementation evidence
→ historical unless explicitly revalidated

investigation/source evidence
→ may remain admissible if its claim is unaffected

baseline / protected conditions
→ revalidate according to changed acceptance dependencies

active invocation
→ hold/revoke if its assignment no longer matches

downstream dependencies
→ recompute impact
```

This is closely aligned with the newer Plan Assurance design, where assurance is already bound to a versioned dependency set rather than just a plan hash.

The Lead should be able to revise Tickets autonomously as long as the new Ticket revision remains inside:

- the parent Story/Epic objective;
- accepted stakeholder decisions;
- governing contracts;
- approved security/compatibility/reliability commitments;
- the approved scope/cost envelope.

If the proposed Ticket revision crosses that boundary, AEW should refuse to hide it as a Ticket edit and instead require parent revision and/or stakeholder involvement.

That gives us the boundary I think we actually want:

> The stakeholder owns purpose.  
> The Lead owns decomposition and execution strategy inside that purpose.  
> AEW preserves revision history and prevents stale evidence from silently following semantic changes.

I would therefore change the old rule:

> “Material Ticket changes after evidence require replacement Ticket.”

to:

> “Material Ticket changes require a new acceptance-bearing Ticket revision. Existing evidence does not automatically remain admissible across that boundary.”

A replacement Ticket should still be available when the new work is genuinely a different bounded unit, but it should not be mandatory just because the Lead corrected or materially refined its decomposition of the same work.

I also think the Lead should get an explicit first-class revision path rather than arbitrary state editing, something conceptually like:

```text
aew ticket revise T-17 ...
```

AEW would record the new immutable revision, run impact analysis, invalidate/revalidate dependent artifacts, hold affected active work, and preserve the previous revision as history.

The guiding principle may need to evolve from:

> Parents preserve purpose. Tickets preserve proof.

to something closer to:

> Parents define the approved purpose. Ticket revisions preserve the history of how AEW pursued it. Evidence binds to revisions, not mutable labels.

Can you review this against the current hierarchy revision design, evidence-freshness semantics, dependency binding, active invocation handling, and closeout rules, and identify what would need to change if we adopt it?
