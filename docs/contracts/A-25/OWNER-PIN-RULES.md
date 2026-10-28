<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-25
source: 30-stages/STG-01-first-release-expansion/sealed/v0.5.4/STG-01-v0.5.4.zip!00-DESIGN/OWNER-PIN-RULES.md
source-sha256: f7292e6784d3792426d29dc5937a79392fb475a29efcaac6ba48e41877cd15c6
edits-sha256: none
-->

# STG-01 owner-pin and source-consistency invariants (proposed, v0.5.2)

**Status:** proposed selected-wire rules for the three new D-01 reads and the O-01 owner GET. Nothing here is adopted.

**Machine-readable form:** `00-DESIGN/owner-pins.json`. The rule IDs below and in that file are the same.

**How these rules are written:**
- They are stated **separately from the oracle**, and each one cites its adopted anchor.
- The oracle reads `owner-pins.json`. Hand-written fixtures with explicit expected outcomes test the oracle against these rules.
- If a pin is weakened in the table, those fixtures fail. That is the obligation-linked mutation check in STAGE gate 6.

**Scope:** these rules are additive to inherited A-12/A-22/A-23 semantics on the 17 inherited routes. They do not reinterpret those routes.

## Pins: who owns each field

| Resource | Item `source.owner` | Field path | Pinned owner |
|---|---|---|---|
| `continuation_vector` | HEB | `data.axes.<X>`, for X in HEB, ADC, WIS, AEV, R01, IF10 | X |
| | | `data.work_ref`, `data.work_revision` | WIS |
| | | `data.generation_ref`, `data.binding_ref`, `data.operation`, `data.informational_only` | HEB |
| `hold_recovery` | AEV | every field | AEV |
| `owner_operation_index` item | `data.owner` | every field | `data.owner` |
| `owner_operation_index` `collection_basis` | CNI (aggregation only) | `closures[].owner` | each owner in the recipient's owner set |
| O-01 owner GET | | `body.owner` | `registry[action].sole_admitting_owner` |

**Index items:** `data.owner` must itself equal `registry[data.action].sole_admitting_owner`.

**Continuation item source:** the item-level `source` is HEB because the subject (attachment, generation) is HEB's. It confers no authority over the other axes (C18 is informational, never C17).

**Collection basis:** CNI may qualify the aggregation. It never qualifies an underlying operation, which is governed by OP-07 and the anchors A-09 CNI-05 and A-12 D01-WR-15.

## Invariants

**OP-01. Namespace pin.**
- Every stamp's `owner` equals the pinned owner for its position.
- Anchor: A-12 D01-WR-10, D01-WR-12.

**OP-02. Governing owner for qualified claims.**
- A stamp with `qualification=qualified` on a pinned field has `governing_owner` equal to the pinned owner **when the pinned owner is a governing-owner namespace of the inherited A-23 `SourceStamp` type**. Today those are ADC, AEV, CNI, HEB, WIS and RESEARCH. The oracle reads the list from the schema; it does not restate it.
- For any other pinned owner, `governing_owner` is null. IF10 and R01 are examples: they produce qualified observations, but the adopted type does not give them a governing namespace. Attribution is then carried by `owner` (OP-01) and by the producer's own renewal (OP-04).
- It is never another owner.
- Anchor: D01-WR-12: "if the required governing authority is absent, report `not_established`, not an invented owner". Also the inherited A-23 `SourceStamp` type. Widening that enum would change a type shared by all 17 inherited routes, and is out of STG-01 scope.

**OP-03. Unqualified stays unqualified.**
- A stamp with `qualification≠qualified` must not be `observation_state=present_current`.
- Its `governing_owner` is null or the pinned owner.
- An unavailable producer is a legitimate state. It is projected as `not_established` with the transport reason `SOURCE_UNAVAILABLE`.
- Anchor: D01-WR-12, D01-WR-15, A-10 AOI-12.

**OP-04. Renewal is by the producer.**
- On every stamp of the new STG-01 resources, a non-null `renewal.qualified_owner` equals `stamp.owner`, whatever the renewal `kind`.
- The inherited delegated source-validity pairs (KNOWLEDGE/HEB and RELEASE/CNI) stay as they are, but only on the inherited routes.
- Anchor: A-23 §4 "Qualified-continuity renewal authority", and the A-23 v0.1.4 correction 3, "a different source owner must issue its own separately stamped fact".

**OP-05. Renewal epoch comparability is explicit.**
- `renewal.source_epoch` may differ from `stamp.source_epoch` only if the owner's own world record lists that renewal epoch as comparable to the source epoch (`comparable_renewal_epochs`).
- Otherwise the positive claim fails. Epoch equality is not required in general; it simply cannot be assumed.
- Anchor: D01-WR-13 ("epochs cease comparing → downgrade"), D01-WR-14 ("client cannot synthesize missing equality"), AB05-R01.

**OP-06. Renewal is finite and bounded.**
- A present-current stamp has a finite `renewal.valid_until`.
- That value is no later than the owner's recorded maximum.
- `observed_at` and `checked_at` are both no later than `valid_until` and no later than the read's `projection_as_of`.
- `valid_until` is later than the world's `now`.
- Anchor: D01-WR-13, D01-WR-14.

**OP-07. Collection closure is per owner.**
- A `qualified_scoped` owner-operations page has exactly one closure entry per owner in the recipient's owner set for the effective query.
- Each entry's epoch and coverage equals that owner's own world record.
- A filtered query's owner set is the filter. CNI's basis covers only the aggregation.
- Anchor: D01-WR-14, D01-WR-15, A-22 D01-EXT-10, AB05-R02, V03B-N4.

**OP-08. The owner GET owner is the admitting owner.**
- The O-01 owner GET's `owner` equals the registry's sole admitting owner for the operation's action.
- Its currentness is checked as in OP-06, against the owner's observation.
- Anchor: A-19 O01-12, O01-16–18; A-24 owner-record currentness; AB05-R04.

**OP-09. The stamp is the owner's fact.**
- A qualified stamp equals, field by field, the fact derived from its pinned owner's **own record**: `fact_ref`, `source_epoch`, `source_version`, `issuer_ref`, `coverage_ref`, `authority_class`, `owner_coverage_class` and `observed_at`.
- Each stamp's owner record comes from one place:

  | Stamp | Owner record |
  |---|---|
  | Continuation axes and fields | `owner_axes[pin]` |
  | Hold | `hold` |
  | Collection basis | the CNI roster record |
  | Index items | the operation record in `operation_roster`, with its `operation_source_issuers` entry |

- The canonical fact identity of an index item is `op-record:<operation_ref>`.
- Per-owner coverage, class and renewal-proof metadata come from `source_metadata[owner]`.
- A qualified owner record supports exactly `observation_state=present_current`. A qualified stamp with any other state (for example `stale`) contradicts its own fact. An honest downgrade is unqualified, under OP-03.
- A qualified stamp for an owner whose record is absent or unavailable is `PIN_UNQUALIFIED_CLAIM`.
- Anchor: D01-WR-12, D01-WR-13, AB05-R01.

**OP-10. A qualified claim needs its own basis.**
- On `hold_recovery`, the fields `data.options`, `data.options_completeness` and `data.options_source_basis` are backed by AEV's **options basis**, not by the hold record.
- When `data.options_source_basis` is null, all three fields carry unqualified stamps. A current hold record does not qualify options that AEV has not issued.
- Code: `HOLD_OPTIONS_OVERCLAIM`. Anchor: D01-WR-12, A-10 AOI-05.d, V03B-N6, LEAD-F17.

**Read-level rule (all three new reads).**
- A read whose items carry any unqualified stamp is not `outcome=provided` with `continuity=source_qualified`.
- Code: `READ_FALSE_FULL_QUALIFICATION`. The continuation-specific `VECTOR_FALSE_FULL_QUALIFICATION` remains, covering the case where an owner is unavailable.

**Index item identity (AB05-R05, cross-wire).**
- The outer ResourceRef of an owner-operations index item has kind owner_operation_index and id ownerop:<owner>:<operation_ref>.
- Its detail link is the O-01 owner GET for the same pair, and must pass O-01's own path-parameter schemas unencoded.
- Code: INDEX_RESOURCE_ID (link: INDEX_LINK_OWNER).

## World consistency: checked before any response

These invariants apply to the synthetic **world**, which holds owner-native facts only. A world that breaks one is **contradictory**, and the gate rejects it as malformed test data. A world in which an owner is simply unavailable is **not** contradictory.

**OW-01.** Each owner record names itself. `owner_axes[X]` describes X, and the `operation_source_issuers` and closure records name the owner they cover.

**OW-02.** A record with `qualified=true` has a non-null epoch, version, issuer, basis, `observed_at` and finite `valid_until`, with `observed_at` no later than `valid_until`.

**OW-03.** A record with `qualified=false` is **unavailable**. It carries no positive state, and every response stamp for that owner must be unqualified under OP-03.

**OW-04.** The renewal entitlements and the stamp attestations held by the world agree with OP-01, OP-02 and OP-04. A world cannot entitle a renewal by another owner, and it cannot name a governing owner other than the pin.

**OW-05.**
- The HEB transition record is single-valued: one current successor, and one predecessor generation.
- It agrees with the A04 view of the same transition.

## Decision noted

**OP-04 turns one v0.5.1 positive into a negative.**
- **The fixture:** v0.5.1 accepted a renewal by an invented namespace, `RENEWAL_AUTHORITY`, on the ADC axis, as the case "VALID independent renewal owner and epoch".
- **Why it changes:**
  - D01-WR-12 forbids inventing owners.
  - A-23 says another owner must issue its own fact rather than renew.
- **What replaces it:** two positives, a same-owner renewal under a **different but explicitly comparable epoch** (OP-05), and a same-owner refreshed stamp. Both keep the legitimate behavior AB05-R01 asked to preserve.
- **What is unaffected:** the inherited KNOWLEDGE/HEB and RELEASE/CNI delegations.

**Fixture defects the v0.5.1 copy-world hid, found by applying these rules (LEAD-F14):**
- One HEB fact, `basis:HEB`, carried two different source epochs in different positions.
- Index item stamps cited unrelated facts (`basis:one` and `basis:HEB`) instead of the operation record.
- An ADC operation was stamped with an HEB governing owner and an HEB renewal owner.
- Renewals used a template epoch, `epoch:one`.

All of these are normalized by `tools/migrations/stg01_w2_normalize.py` in the design workspace, and the world no longer holds response copies.

**A refinement, also recorded:** at first OP-02 required a non-null governing owner on every qualified stamp, and IF10/R01 were reported as defects (LEAD-F9). The inherited type shows that their null is correct, so LEAD-F9 is withdrawn.
