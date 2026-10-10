# Designer decision of 2026-10-10: the cross-feature integration design v0.5 frozen, activation gated (F41)

**Status:** Decision record, governing for what it decides. The designer froze the
[cross-feature integration design v0.5](cross-feature-integration-design-v0.5.md) on 2026-10-10 (disposition FREEZE
WITH CORRECTIONS, the corrections applied). The concept is frozen; activation is gated by the governing amendments and
the activation gate of its §19 and §20. This record says what was frozen, records the decisions the freeze carries, and
says where each is filed. The design's own text governs; where this record and the design differ, the design wins.

## 1. What was frozen

The design connects adopted AEW owners and introduces no second lifecycle, invalidation system, review-proof system,
health system or coordination channel (its §1). Its new surface is limited to: a reviewed-plan contract for parent
work; section-level plan binding; a non-blocking interface-dependency edge with engine-computed interface digests; an
advisory overlap projection; two U1 health fields; `operator_validation` evidence; a delta-review packet; and
deterministic plan-underspecification signals. Everything else lands under existing owners.

Its central decisions (§22): every Epic and Story, Class 0 included, has a reviewed accepted plan; the planning/research
child exemption is engine-derived from admitted purpose and non-mutating authority, never from a label; section-digest
binding is mandatory; parallel assumption relationships use a new non-blocking `interface_dependency` edge; E19-B stays
the sole authority-bearing invalidation mechanism; wakes are advisory delivery only; held workers cannot clear their
own holds; operator validation cannot launder model authority; delta review keeps engine facts apart from claims; and
the field log (§18, entries #1 to #20 and W1 to W8) is fully dispositioned and owner-linked. The field-log table stays
in the design.

## 2. V-1(b): a non-blocking interface_dependency edge

The designer chose V-1(b) (§7). Blocking dependency edges keep their meaning: the consumer waits for the provider's
`DONE`. AEW adds a separate edge kind, `interface_dependency`, for a contract or assumption dependency between work that
may run in parallel. The consumer may dispatch while its provider is active when the interface contract is current and
accepted and the consumer is bound to its engine-computed digest. A provider publish that changes the governed interface
without an accepted interface revision is refused (`INTERFACE_CONTRACT_DRIFT`). An accepted interface revision holds
the direct named consumers through E19-B's `revision_impact_hold`. The held worker cannot clear its own hold, and cannot record either authority-bearing action that clears it: the Lead's F9 disposition or the engine's rebinding to the new digest (§8.2).

The edge needs a Workflow Contract §8 amendment before activation, and that amendment also extends E19-B §7.5's
`revision_impact_hold` trigger to accepted interface revisions on `interface_dependency` edges (register F41.5).

## 3. Freeze versus activation: the designer's ruling

The designer's ruling (§19, last paragraph): the design may freeze before the WC/F14 and WC §8 amendments are merged.
The affected behaviour is not activatable until the required governing amendment exists and the activation gate
verifies it. This supersedes the earlier v0.3 review's suggestion that the amendment must exist before conceptual
freeze.

So the freeze is a design state, not an activation. What must exist before activation, from the §19 owner table:

- the Workflow Contract / F14 amendment for the mandatory reviewed Story/Epic plan, including the Class-0 parent path
  (`parent_paths["0"]`), with the reviewed-plan record contract (register F41.1);
- the Workflow Contract §8 amendment for the `interface_dependency` edge, with the E19-B §7.5 trigger extension
  (register F41.5);
- section-digest binding, a prerequisite (register F41.4);
- for the planning-child exemption, the migration of project policy in `policy/gates.yaml` for the changed
  `non_mutating_paths` default (§3.1; register F41.3).

The remaining §19 rows are pending implementation under their existing owners (register F41.2 and F41.6 to F41.13); the
Lead wake stays with F9. The §18 dispositions that hand work to owners outside these rows (field-log #4, #10, #12, #15, #16 and #20) are tracked together on F41.14. Because the WC/F14 and WC §8 amendments are not yet written, neither this record nor the design
is an overlay on the Workflow Contract: `docs/spec-amendments.yaml` lists both as considered, replacing no WC/KC text.

## 4. The 26 acceptance checks

The design's §20 makes its acceptance checkable. Each check is a ledger row (CFI-71 to CFI-96), tracked on the register
row that owns it:

| # | Check | Ledger | Register |
|---|---|---|---|
| 1 | No duplicate lifecycle: no new parent work-state enum; `plan_phase` derived only | CFI-71 | F41.2 |
| 2 | No planner recursion: a qualifying planning child launches with its assignment as plan | CFI-72 | F41.2 |
| 3 | No label bypass: a planner label with a mutating effect set is denied the exemption | CFI-73 | F41.2 |
| 4 | Mandatory parent planning: Class-0/1/2+ Story/Epic mutating child dispatch refused without a reviewed plan | CFI-74 | F41.2, F41.1 |
| 5 | Independent plan review: the proposer cannot fill the reviewer or adopter slot | CFI-75 | F41.2 |
| 6 | Plan review binding: review sha differing from proposal sha refuses adoption | CFI-76 | F41.2 |
| 7 | Section binding: an unconsumed section change leaves the child current; a consumed digest change stales it | CFI-77 | F41.4 |
| 8 | Reconfirm safety: subtree reconfirm carries no evidence; integrated affected work needs reverification | CFI-78 | F41.4 |
| 9 | Parallel interface edge: a consumer dispatches before provider `DONE` when the digest is current | CFI-79 | F41.6 |
| 10 | Contract drift: a provider publish changing the interface without an accepted revision is refused | CFI-80 | F41.6 |
| 11 | Hold authority: a held worker cannot clear its own hold | CFI-81 | F41.6 |
| 12 | Interface rename/remove: holds all named consumers | CFI-82 | F41.6 |
| 13 | Undeclared residual: hard protection for declared interfaces only; publish-overlap stays advisory | CFI-83 | F41.6, F41.7 |
| 14 | Wake coalescing: the latest fact coalesces; a later fact after acknowledgement wakes again | CFI-84 | F9 |
| 15 | Wake not authority: a lost wake does not clear a hold | CFI-85 | F9, F41.6 |
| 16 | Health no authority: the health advisory cannot transition, kill or relaunch | CFI-86 | F41.8 |
| 17 | Health sanitization: secrets and arguments absent from the process field | CFI-87 | F41.8 |
| 18 | Operator validation authority: a model-authored script cannot run before full operator approval | CFI-88 | F41.9 |
| 19 | Operator validation capture: only capture-schema fields persist | CFI-89 | F41.9 |
| 20 | Requirement-step claim bound: coverage only, never adequacy | CFI-90 | F41.9 |
| 21 | Delta provenance: engine, qualified-derived and claim fields kept apart | CFI-91 | F41.10 |
| 22 | Nit loop bounded: a second correction cycle returns to normal review | CFI-92 | F41.11 |
| 23 | Design-decision reason: a worker report wakes the Lead but cannot transition state | CFI-93 | F41.2, F41.12 |
| 24 | Citation rule: a cited path or symbol must resolve; semantic support remains review | CFI-94 | F41.13 |
| 25 | Every field-log item disposed: static coverage of #1 to #20 and W1 to W8 | CFI-95 | F41 |
| 26 | Governing amendments present: the activation gate checks the WC/F14 and WC §8 amendments | CFI-96 | F41, F41.1, F41.5 |

## 5. The nit-rule divergence from the repository process

The design's product rule for nits (§15) is intentionally stricter than this repository's process in AGENTS.md, adopted
in PR #181 (§21). In AEW the product, a project's `nit` maps only to the canonical `observation` severity, and after a
CLEAR the author's observation corrections get one bounded delta review over the full engine-computed delta; anything
more serious, or a second cycle, returns to normal review. In this repository, after a CLEAR the author fixes nits and
posts "Nits fixed at <sha>" with no new review.

The divergence is deliberate and recorded as such, pending the operator's choice when the product rule ships (register
F41.11): either align AGENTS.md to the product rule, or keep the difference through an explicit, documented
project-policy exception. It must not remain an accidental mismatch. The choice is the operator's open question Q15 in
the register, with its item in [decisions due](../implementation/decisions-due.md). This ingestion does not change
AGENTS.md.

## 6. History

v0.1 had an independent review; v0.2 and v0.4 were re-reviewed; the designer reviewed v0.3. The closure review returned
FREEZE WITH CORRECTIONS, and v0.5 incorporates the corrections. Those reviews are outside this repository; v0.5 is the
first version in it, so no earlier version is retired from the ledger.

## 7. Filing (lead developer)

- **The design:** [`cross-feature-integration-design-v0.5.md`](cross-feature-integration-design-v0.5.md), the
  designer's frozen text unchanged, with one header line pointing here.
- **Ledger:** CFI-01 to CFI-106, every requirement, decision and acceptance criterion of v0.5 with its section; this
  record's sections carry CFI ids (ledger CFD).
- **Register:** F41 (the activation gate) and F41.1 to F41.13, one per §19 owner or amendment; F41.14, the §18 dispositions owned outside those rows; Q15 (the nit-rule
  divergence, the operator's). Activation-gating rows: F41.1 and F41.5 (amendments, the designer's, each with a
  decisions-due item), F41.4 (the prerequisite) and F41.3 (for the planning-child exemption). Cross-references on F5,
  F9, F14, F22.3, F36, F38 and U1.
- **Spec amendment index:** this record and the design are `considered`, not overlays: they replace no WC/KC text until
  the amendments in F41.1 and F41.5 are written and adopted.
