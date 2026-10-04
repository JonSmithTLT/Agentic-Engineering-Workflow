# Review: Ticket revisions (amendment to the hierarchy revision design)

**Date:** 2026-09-30  
**Reviews:** `ticket-revision-amendment-2026-09-30.md`, against `hierarchy-intent-revision-and-replanning-design-v0.1.md`, the invariant index, the failure-class registry, the plan assurance design v0.3, the Knowledge Contract v0.4 §12, and the M2/M3 engine as built.  
**Verdict:** adopt it. The invariant it names is the right one, and most of the machinery exists already. Seven decisions were needed before it is built (§9); the three that matter most are how evidence binds to a revision (§2), whether a revision may carry the workspace forward (§4), and whether adverse evidence follows a revision (§6).  
**Decided:** the designer took all seven recommendations the same day (§10).

## 1. The case for it, from this week's dogfood

In rubric A4's T1, trial 2 (`m3-dogfood-report.md` §6.6), the Lead gave its Ticket a scope that missed the code (`src/**`, `lib/**`, … but not `ledger/**`). The implementer fixed `ledger/money.py` correctly, saw the guardrail check fail on scope, and reported `blocked`. The gate refused the Ticket. Because a Ticket's scope is fixed at creation, the Lead did what the current design prescribes: REPLAN_REQUIRED, CANCELLED ("Superseded because its immutable scope omitted ledger/**"), a replacement Ticket, and a second implementer. A correct implementation was discarded, and the replacement links to the original only through free text (`LOST_SUPERSESSION_LINEAGE`).

Nothing was unsafe; everything was recorded. It was ceremony with a cost, and it shows the amendment's point: cancelling and recreating is always available to the Lead, so forbidding revision constrains nothing and fragments the graph. Under the amendment this is `T-0001@r2` with `ledger/**` added: the implementation evidence of r1 is historical, the checks are re-run against r2, and the work continues on the same Ticket.

It is the second time. In the first dogfood, two Leads wrote a Ticket's scope as one comma-separated glob that matched nothing (M3-D9, now refused at creation), and the correct change was again discarded with its Ticket.

## 2. Evidence binding and freshness

**Today.** A gate counts passing evidence whose evaluated-snapshot fingerprint equals the workspace's current one, whose plan revision equals the accepted one (WC §9.9, invariant 7), and, for a check, whose definition digest is current (I1). Review and verification count only ingested reports, pinned by id and sha256. Non-mutating records have their own freshness contracts (ADR-0008): source-bound records are CURRENT, STALE or UNKNOWN against the authoritative source. In every case **staleness is computed, never written**: records stay byte-identical.

**What changes.** Evidence must also bind to the Ticket revision it supports. Two ways to do it:

- **(a) A revision number,** like `plan_revision`. Simple, but coarse: every revision invalidates everything bound to it, a title fix included, unless something rebinds it.
- **(b) Digests of the fields the evidence depends on** (recommended). This is what plan assurance v0.3 §16 already does: `objective_digest`, `acceptance_contract_digest`, protected conditions, parent obligations and policy revision. A Ticket revision records a digest per field group: acceptance (goal, contract, body), scope, gate set (risk class and inherited gates), dependencies, card and kind. Each artifact kind binds to the groups it depends on, and the amendment's impact table becomes computed instead of declared:

| Artifact | Binds to | After a goal change | After a scope-only change |
|---|---|---|---|
| accepted plan | acceptance, scope, dependencies | invalidated | revalidate (the plan may still hold) |
| check result (`unit`) | snapshot, check definition | unchanged | unchanged |
| guardrail result | snapshot, scope | unchanged | recomputed (the gate already recomputes it live) |
| implementation report | acceptance, scope, plan | historical | historical (its claim or its result may depend on the scope, as in §1) |
| review | acceptance, scope, snapshot | invalidated | revalidate |
| verification | acceptance, snapshot | invalidated | unchanged |
| discovery or research record | its own Ticket's question; source freshness | unchanged unless the question changed | unchanged |

Checks show why (b) matters: a `unit` result proves "the tests pass on snapshot X". A goal edit does not change that, yet today a new plan revision would stale it, because the plan-revision binding is coarse.

**REVALIDATE needs an operational meaning,** or it becomes a status nobody resolves. It should resolve only through a new record, never by relabelling an old one:

1. **mechanically,** when every input an artifact is bound to is unchanged (AEW decides, and records it);
2. **by an independent fresh-context confirmation,** the hierarchy design's CLARIFICATION rule (§4.2), which produces a new record referencing the old one;
3. **by a recorded Lead decision,** like `aew work acknowledge-input` today, but only for evidence whose claim lies outside the changed fields, and never for a review or verification of acceptance.

**Keep admissibility computed.** UNCHANGED, REVALIDATE, INVALIDATED, SUPERSEDED and HISTORICAL should be derived from bindings at read time, as freshness and gate status are, never stamped into records. The system then has one vocabulary per question: artifact admissibility (these five), gate status (CURRENT, STALE, MISSING, FAILED, WAIVED) and source freshness (CURRENT, STALE, UNKNOWN). The hierarchy design's §14 labels (UNCHANGED, CONTEXT_UPDATE, REPLAN, HOLD, SUPERSEDE) classify *work*, not artifacts, and should be named as such.

## 3. Dependency binding

**Today.** An `evidence` edge is satisfied when the upstream unit is DONE. A `mutating` edge also needs the upstream's integrated commit in the downstream base. A started attempt is bound to the effective edges it was dispatched with: an edge change on started work forces a new dispatch (M2 B2), and edges may change only in BLOCKED, READY or REPLAN_REQUIRED. Consumed records are rechecked for freshness at every dispatch, with `acknowledge-input` as the recorded override.

**What changes:**

- **No revisions after DONE** (or CANCELLED). Downstream work has consumed a DONE Ticket's accepted evidence and integrated commit. Changing it later is a new Ticket, a follow-up. Allowing it would make every consumer's bindings retroactively uncertain.
- **Revising an upstream that is not DONE** does not affect edge satisfaction (edges wait for DONE anyway). It does affect downstream *plans* that assumed the upstream's proposition. A consumer's accepted plan should record the upstream revisions or digests it relied on, as it records its ancestors' plans (`ancestor_plans`), so that a later upstream revision stales the consumer's plan binding. `aew plan reconfirm` already resolves exactly this case for ancestors.
- **A revision that changes the Ticket's own dependencies** follows the existing rule unchanged: on started work it ends the attempt, and the next dispatch checks the new edges.

## 4. Active invocations

**Today.** An invocation pins its card, execution profile, context pack sha (the pack carries the Ticket and its plan), workspace or observation, and expected output. A change means a new invocation (M3 plan §2.2). Credentials are revoked when a Ticket reaches a terminal state, when the implementer's work is accepted (RUNNING → REVIEW/VERIFY), and when a replanned Ticket's new plan is accepted, which also releases the workspace ("the next assignment starts fresh", M2 review). **RUNNING → REPLAN_REQUIRED revokes nothing**: the implementer stays live until the new plan is accepted or the Ticket is cancelled. Anything it submits in that window is bound to the old plan and can satisfy nothing, so it is safe, but a credential outlives its proposition.

**What changes:**

- **A material revision ends every active invocation of the Ticket in the same commit.** Every pinned pack contains the changed Ticket. M3's watchdog then closes their bridges, and their runs end as `terminated: invocation_ended`. Revoke and redispatch rather than inventing a "held" invocation status: pins are immutable by design, and a relaunch rebuilds the pack. INTERRUPTED stays tied to authority changes (ADR-0003); a revision is a Lead decision, not an interruption.
- **Whether a revision may carry the workspace forward is the largest decision** (§9, D3), because it reverses the M2 "start fresh" rule. The benefit in §1 exists only if it does. A safe form: the next attempt starts from the revised Ticket's workspace as *input*, not as proof. Every r1 artifact is historical, the new implementer re-runs the checks and submits its own report, and M3's continuation section (the diff against base, earlier evidence, open findings) is already the shape of that handover.
- **Later:** a compatible revision could be delivered to a running invocation as a coordination delta (the Live Coordination design; M3 plan §2.11) instead of a revoke. That is out of scope now, but the run model leaves room for it.

## 5. Closeout

**Today.** A mutating Ticket completes by `integrate publish`, and a non-mutating one by `work accept`; each writes a completion record. A parent closes only when every child is DONE or CANCELLED, its own gates are CURRENT against the parent snapshot (the authoritative commit plus a digest of the children's completion records), its findings are resolved, and every superseded descendant has an explicit disposition (AEW-INV-HIER-005).

**What changes:**

- **Completion records name the final revision** (and its digests). Every piece of evidence in the record's gate basis must be bound to that revision.
- **Integration.** Leaving COMMIT_READY already retires the integration candidate. A revision should be refused while a publish is in progress, as `work cancel` is today.
- **Parents.** The children digest should include each child's final revision. Because a DONE child is not revisable (§3), the digest stays stable once children finish. HIER-005 still applies to replacements. Revisions need no disposition, because identity is preserved, but the closeout record should list children revised materially after the parent's plan was accepted: the Ticket-level form of §18.1's cumulative drift.

## 6. Authority, the envelope, and what AEW can actually refuse

The amendment's boundary is right: the stakeholder owns purpose, and the Lead owns decomposition. AEW can enforce only part of it mechanically, and the design should say which part, so that it does not promise a guarantee it cannot keep.

- **Refusable by AEW:**
  - a class below the parent's minimum descendant class;
  - dropping a mandatory gate inherited from an ancestor;
  - protected paths (guardrails);
  - dependency cycles;
  - revising a DONE, CANCELLED or publishing Ticket;
  - lowering the class without a recorded decision (WC §7.4, as today);
  - scope outside the parent's scope, *if* parents declare a scope (today only Tickets do).
- **Not decidable by AEW:** alignment with the parent's objective, stakeholder decisions, governing contracts, commitments, cost. These must be a recorded Lead assertion in the revision decision. They are surfaced in `status`, `resume` and checkpoints, challenged by plan assurance (F14) when it exists, and judged at the parent's review. "AEW refuses to hide it as a Ticket edit" holds for the first list only.

**Two abuse paths, to close in the rules:**

- **Revision laundering.** A failed review or verification at r1, then a revision, and the adverse evidence is "invalidated". Adverse findings are about the code, not the wording: open required findings of r1 must stay open in r2 until they are resolved or waived, and r2's review pack must carry them (M3's continuation section already carries open findings). Proposed registry class: `REVISION_LAUNDERING`.
- **Gate shedding.** Lowering the class in a revision after a gate failed. Keep WC §7.4's recorded decision, and make a class reduction after an adverse result need the independent confirmation that §11.1 already requires for verifier-classification downgrades.

## 7. What changes in the documents

| Document | Change |
|---|---|
| Hierarchy design §1, §3, §24; invariant index AEW-INV-HIER-001; the Lead/operator design (the same line) | the principle: "Parents define the approved purpose. Ticket revisions preserve the history of how AEW pursued it. Evidence binds to revisions, not mutable labels." |
| Hierarchy design §2 (Ticket), §8, §9 | Ticket as Lead-owned decomposition; MATERIAL → a new acceptance-bearing revision plus impact analysis, not a replacement; a replacement stays available for a different bounded unit (still with the supersession link, post-M3 P2) |
| §4 change classes | unchanged in substance; they now classify *revisions*, and CLARIFICATION's independent confirmation becomes one of REVALIDATE's resolutions (§2) |
| §13, AEW-INV-EVID-001 | carries the weight; add "admissibility is computed from bindings, never written" |
| §14 | distinguish work impact (its labels) from artifact admissibility (the amendment's) |
| §17 | the Lead's "may not" list: add that it may not use a revision to escape adverse evidence or shed gates (§6) |
| §18.1 | cumulative drift applies to Ticket revisions too: rN against r1 and against the parent's envelope |
| §20 scenarios | A becomes a revision; add: scope correction after implementation (§1), revision after a failed review, revision with a live run, revision of a Ticket others depend on, class lowering in a revision |
| §21 open questions | 1, 3, 5 and 12 are answered or narrowed by this amendment |
| Failure-class registry | `EXCESSIVE_HIERARCHY_RECREATION` covers Tickets too (the §1 case); add `REVISION_LAUNDERING` |
| Invariant index | add: evidence binds to a Ticket revision (or its field digests) and never crosses a material revision without a recorded revalidation; no revision after DONE or CANCELLED; no active invocation for a non-current revision |
| Knowledge Contract §12 (frozen) and WC §7/§8 and invariant 7 (frozen) | Ticket revisions beside plan revisions, and the extra binding: a spec amendment with an ADR, like ADR-0002's |
| Plan assurance §21 | "Tickets preserve bounded execution propositions" becomes "each Ticket revision preserves one" |

## 8. What changes in the engine (for sizing, not now)

- **Records.** `work/<T>/ticket-rN.md`, immutable, plus a current-revision pointer in control state (the plan pattern: `plan-vN.md`, `status`, `supersedes`, `reason`). Existing Tickets become r1.
- **Command.** `aew work revise <T> --fields - --reason ... --expect-rev N` (in the `work` group, beside `create`), with `--impact` to print the impact analysis without committing. The Lead should see what a revision invalidates before making it.
- **The revision decision** records the changed fields, their change class, the computed impact, the ended invocations, and the Lead's envelope assertion.
- **Evidence.** An engine-owned `ticket_revision` (or digest) binding in `ENGINE_OWNED`; gates add it to the `_matches` test.
- **Packs, status, resume, the guide** show the current revision and what the last revision invalidated. Next actions follow from it: "T-17@r2: plan invalidated → propose or reconfirm".
- **Oracle rules** (`tests/helpers/invariants.py`):
  - no gate is satisfied by evidence bound to a non-current revision without a recorded revalidation;
  - no active invocation exists for a non-current revision;
  - every revision has a decision;
  - no revision follows DONE or CANCELLED.
- **Dogfood.** §1 becomes a scenario with a measure: no discarded implementation, and fewer Lead steps than cancel-and-recreate.

## 9. Decisions needed (designer)

| # | Decision | Recommendation |
|---|---|---|
| D1 | Bind evidence to revision numbers or to field-group digests | digests, as plan assurance already does |
| D2 | Which states allow a revision | any non-terminal state except while publishing; COMMIT_READY retires the candidate |
| D3 | May a revision carry the workspace forward, reversing M2's "start fresh" | yes, as input only: all r1 evidence historical, and the checks and the report redone |
| D4 | How REVALIDATE resolves | mechanically, by independent confirmation, or by a Lead decision, each producing a record, as in §2 |
| D5 | Do r1's adverse findings stay open in r2 | yes (§6) |
| D6 | Which envelope crossings AEW refuses, and which are recorded assertions | the two lists in §6, stated in the design |
| D7 | When a replacement is still required | a change of kind (mutating or not), a move to another parent, or a Ticket whose goal no longer overlaps the old one; otherwise a revision |

## 10. Decisions (designer, 2026-09-30)

| # | Decision | Designer's choice |
|---|---|---|
| D1 | Evidence binding | field-group digests |
| D2 | States that allow a revision | any non-terminal state except while publishing |
| D3 | Carrying the workspace forward | yes, as input only: all proof regenerated or revalidated |
| D4 | How REVALIDATE resolves | the three mechanisms of §2 |
| D5 | Adverse findings | carried forward until explicitly resolved |
| D6 | Envelope enforcement | the mechanical-versus-semantic split of §6 |
| D7 | When a replacement is required | a change of kind, a move to another parent, or an essentially non-overlapping goal |

**What follows from them:**

- The hierarchy design's next revision, the invariant index and the failure-class registry are the designer's (§7).
- The amendment of the frozen specs, Knowledge Contract §12, Workflow Contract §7 and §8, and invariant 7, needs an ADR.
- The engine work (§8) belongs to the hierarchy-revision milestone (`future-work.md` F4 and F5), not to M3.
- §1's scope correction becomes one of its acceptance scenarios.
