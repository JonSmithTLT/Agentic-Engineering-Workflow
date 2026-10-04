# T7 — Effective-spec overlay index, citation resolution, and re-freeze plan (v0.2)

- **Status:** **Design frozen — proposed for operator adoption**, 2026-10-04. This v0.2 accepts the need for a machine-readable overlay index but tightens its authority model, citation semantics, scope, and re-freeze/migration rules. It deliberately does not make research notes a governing authority source.
- **Basis:** `docs/README.md` "What governs, in order"; `docs/spec-pin.yaml` and `docs/aew-spec-manifest-v0.2.yaml` (`freeze_rule`, `compatibility_rule`); the two amendments in `docs/design/`; the ADR amendment sections; `tests/test_spec_pin.py` and `tests/unit/test_docs_links.py`; a grep of every `WC §` and `KC §` citation in the living documents at `dcd43f1`.
- **Classification of statements:** everything in §1–§3 is read from the repository (documented fact). §4 and §5 are the proposal.

## 1. How the governing order works today, and the gap

The frozen set (`aew-frozen-2026-09-25`) is pinned by content hash; `tests/test_spec_pin.py` fails if any of the four files changes. The manifest's `freeze_rule` says discoveries are "tracked as implementation issues or ADRs/amendments" and the contract version is bumped only when normative semantics change. `docs/README.md` ranks: frozen set, then "adopted amendments and decisions", then ADRs, then the milestone plan, then indexes. "When documents disagree, the earlier one wins" is stated for that order, and the map lists the amendments by hand.

Two things the machinery does not do:

1. **Nothing records, in machine-readable form, which frozen sections an amendment replaces.** The Class 0 amendment says "**Amends:** Workflow Contract v0.7 §7.4 and §7.5" in prose; its §9 later also replaces a KC §26 acceptance case; the Ticket-revision review §7 lists KC §12 and WC §7, §8 and invariant 7 as needing "a spec amendment with an ADR, like ADR-0002's", which has not been written. A reader of WC §7.4 in the frozen file has no pointer to the amendment.
2. **Nothing checks citations.** `test_docs_links.py` checks that relative links resolve and that the map lists every document; it does not parse section citations. The living documents cite 36 distinct contract sections (`WC §…`, `KC §…`) 80 times at `dcd43f1`; a citation of an amended section without the amendment is undetectable today.

The handoff's REVIEW G6 called the re-freeze a question of *when*; this note's contribution is to make its *size* visible: the index below is the diff a v0.8/v0.5 re-freeze would consolidate.

## 1.1 Frozen governance model

The index is an **overlay resolver for the frozen WC/KC set**, not a second specification and not a general document-version database.

Authority states are explicit:

```text
proposed
design_frozen
adopted
superseded
```

Only `adopted` overlays participate in effective-spec resolution. `design_frozen` means the design authority considers the text ready for operator adoption; it does **not** override the frozen set. `adopted` requires an attributable operator/repository adoption reference (for example an accepted decision + merge/tag/commit according to project practice). `superseded` remains in history but is not effective.

This distinction is required because a designer freeze, an implementation that already enforces a behavior, and operator adoption are three different facts. The index must not collapse them into one `status: adopted`.

The overlay index may name:

- exact frozen WC/KC sections/cases that an adopted overlay **replaces**;
- exact frozen sections that an adopted overlay **extends** without replacing;
- **pending consolidation debt** where an accepted design explicitly requires a frozen-contract amendment that has not yet been written.

ADR self-amendments that only revise an ADR's implementation mechanism do **not** belong here unless they alter/extend the effective WC/KC semantics or create consolidation debt. Their own ADR history remains their source of truth.

## 2. Every amendment on the map, and the sections it touches

Read from the documents. "Replaces" means the amendment supplies text that supersedes the frozen text; "extends" means it adds obligations without contradicting it; "decision" means a designer or operator ruling recorded outside the contracts.

| Amendment document | Kind | Adopted | Replaces | Extends or decides |
|---|---|---|---|---|
| `design/workflow-contract-amendment-class0-2026-10-01.md` | WC amendment | 2026-10-01 (designer); enforced since M4-A 2026-10-03 | **WC §7.4** (the Class 0 bullet and examples; a new paragraph after the class list), **WC §7.5** (the Class 0 path, tightened again in its §9); **KC §26 "Parent risk policy propagation"** (the acceptance case, replaced in its §9) | reclassification as a recorded decision (WC §7.4 "classification may increase…" given a record shape); enforcement scope limited to mutating Tickets |
| `design/plan-assurance-and-classification-decisions-2026-10-01.md` | decisions record | 2026-10-01 | nothing in the frozen text directly | Q9, Q10 closed; one classification system (§2); F19 one evaluation program (§3.6); "a new attributable acceptance revision is an F4 Ticket revision" (§3.3) |
| `design/plan-assurance-and-premise-validation-design-v0.4.md` | adopted design | 2026-10-01 | nothing directly; v0.3 superseded (archive) | the hard assurance triggers (§22), `DispatchDecision` (§17.1), failure classes merged into the registry |
| `design/ticket-revision-amendment-2026-09-30.md` + `archive/reviews/ticket-revision-amendment-review-2026-09-30.md` §7 | amendment to a proposal, with a designer review | 2026-09-30 | **hierarchy revision design** §1–§3, §8, §9, §13, §14, §17, §18.1, §20, §21, §24 (a proposal, not frozen) | the review's §7 names **KC §12** (frozen) and **WC §7, §8 and invariant 7** (frozen) as needing "a spec amendment with an ADR, like ADR-0002's": **not written** |
| `design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md` | adopted direction; "promoted to governing before M4-E" | 2026-10-01 | nothing yet | WC §15.6 (state query/update interface) gains stages and `ActionProjection`; invariant 21 unchanged; §14 fixes the M4/F15 ordering |
| `research/containment-and-process-ownership-rocky8-research-2026-10-01.md` §8 | designer decisions inside a research note | 2026-10-01 | nothing | Q3, E13, F2 scheduling, Q7 classification; isolation design §12 made a gate |
| `research/m4-integration-queue-research-2026-10-01.md` §7, §7.1 | designer disposition inside a research note | 2026-10-01 | nothing | the M4-D queue dispositions |
| ADR-0002 amendment (2026-09-29) | ADR amendment | 2026-09-29 | ADR-0002's own text (check results bound to definitions) | KC §11 provenance extended |
| ADR-0003 (amended for M2, 2026-09-27; "M5 amendment" on phase waits) | ADR amendment | 2026-09-27 | ADR-0003's transition table | WC §8 state machine extended with hierarchy states |
| ADR-0004 amendment (2026-09-26) and addendum | ADR amendment | 2026-09-26 | ADR-0004's mechanism | WC §8.1, §13 unchanged in meaning |
| ADR-0005 (amended for M3, 2026-09-29) | ADR amendment | 2026-09-29 | ADR-0005 custody and rotation | WC §6 authority unchanged; adds custody |
| ADR-0006 (operator clarification 2026-09-25; amended for M2) | ADR amendment | 2026-09-27 | ADR-0006 | WC §5.8, §16.6 |
| ADR-0009 amendments ×3 (2026-10-01) and the M4-B containment amendment | ADR amendments | 2026-10-01, M4-B | ADR-0009 | WC §16.10 (provider health), §16.12 (adapter rule) |
| ADR-0011 amendments ×3 (2026-09-27, 2026-10-01 ×2) | ADR amendments | as dated | ADR-0011's success criterion and Q1/Q2 | KC §12.3 (control state durability), KC §15.1, KC §21 (indexes rebuildable) |

**Frozen sections with replaced text today:** WC §7.4, WC §7.5, KC §26 (one case). **Frozen sections an adopted decision says must be amended and are not:** KC §12, WC §7, WC §8, WC invariant 7 (Ticket revisions). **Frozen sections an adopted direction will amend before M4-E:** WC §15.6 (stages, `ActionProjection`), and WC §22's open questions where F15 §14 settles ordering.

**Most-cited frozen sections in living documents** (the ones a citation test would exercise first): KC §26 (9 citations), WC §5 (6), WC §7 and §8 (4 each), WC §7.4 (3), WC §8.1, §8.2, §9.9, §16.10 (3 each), KC §11 (3), KC §12.3 (2). KC §26 and WC §7.4 are both amended; every one of those twelve citations should name the amendment or be shown not to depend on the replaced text.

## 3. What a v0.8 / v0.5 re-freeze would consolidate

From §2, the re-freeze is **small in text and large in bookkeeping**:

- WC v0.8: §7.4 and §7.5 as amended (Class 0); §7, §8 and invariant 7 with Ticket revisions (the amendment the review asked for); §15.6 with stages and the action projection once F15 is governing; §22 pruned of the questions the decisions record closed.
- KC v0.5: §12 with Ticket revisions beside plan revisions; §12.3 with the hot/cold split (ADR-0011); §21 stating that indexes are derived and rebuildable (already KC's position; ADR-0011 made it binding); §26 with the amended acceptance case.
- The manifest gets a new `spec_set`, `spec-pin.yaml` new hashes and a new tag, `aew/__init__.py` `SPEC_SET` changes, and every project's `control.yaml` `spec_set` field is touched by `aew migrate` (the manifest's `compatibility_rule`: no mixing without a migration review).

The timing question is therefore: is M4-E (F15 governing) the right moment, so that WC §15.6 is amended once, not twice? This note recommends **after M4-E, before internal alpha**, with the index below carrying the load until then.

## 4. The index: `docs/spec-amendments.yaml` (frozen candidate)

`docs/spec-amendments.yaml` is a machine-readable sibling of `spec-pin.yaml`. It does not repeat amendment prose; it resolves effective authority.

```yaml
schema: aew/spec-amendments/v1
base_spec_set: aew-frozen-2026-09-25

overlays:
  - id: class0-2026-10-01
    path: docs/design/workflow-contract-amendment-class0-2026-10-01.md
    status: adopted
    adoption:
      at: 2026-10-01
      ref: <operator/repository adoption reference>
    replaces:
      - {doc: WC, section: "7.4", anchor: "#2-amended-74-the-class-0-bullet"}
      - {doc: WC, section: "7.4", anchor: "#3-amended-74-examples"}
      - {doc: WC, section: "7.5", anchor: "#5-amended-75-the-class-0-path"}
      - {doc: KC, section: "26", case: "Parent risk policy propagation", anchor: "#9-..."}
    extends:
      - {doc: WC, section: "7.4", note: "reclassification is an attributable recorded decision"}

  - id: ticket-revisions-2026-09-30
    path: docs/design/ticket-revision-amendment-2026-09-30.md
    status: adopted
    adoption:
      at: 2026-09-30
      ref: <operator/repository adoption reference>
    replaces: []
    pending:
      - {doc: KC, section: "12", reason: "Ticket revisions beside plan revisions"}
      - {doc: WC, section: "7", reason: "Ticket-revision semantics"}
      - {doc: WC, section: "8", reason: "Ticket-revision state transitions"}
      - {doc: WC, section: "invariant 7", reason: "Ticket-revision authority boundary"}

  - id: two-surfaces-v0.4
    path: docs/design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md
    status: design_frozen
    adoption: null
    pending:
      - {doc: WC, section: "15.6", reason: "stages and ActionProjection"}

  - id: <later-overlay>
    path: ...
    status: superseded
    superseded_by: <newer-overlay-id>
```

### 4.1 Required index invariants

1. Every effective `replaces`/`extends` target identifies a real frozen WC/KC section or named acceptance case.
2. At most one **effective replacement head** exists for a target. If one amendment replaces another, the chain is explicit with `superseded_by`; ambiguity fails closed.
3. `design_frozen` and `proposed` entries never affect effective resolution.
4. An `adopted` entry has an attributable adoption reference.
5. `pending` creates visible consolidation debt but does not invent replacement text.
6. Superseded overlays remain indexed for historical resolution.
7. Research/proposal files may be cited as evidence, but **must not be the effective target of an adopted overlay**. A decision that currently exists only inside `research/` is extracted to `design/` or the relevant ADR before it can participate in the effective spec.

### 4.2 Citation semantics

Living documentation gets one simple rule:

> **An unversioned citation such as `WC §7.4` means the effective section: the frozen base plus the adopted overlay chain resolved by `spec-amendments.yaml`.**

A citation that intentionally discusses historical frozen text must be version-qualified, for example:

```text
WC v0.7 §7.4 (historical frozen text)
```

This avoids requiring every living paragraph to repeat an amendment filename while still making stale raw-text citations distinguishable. `docs/README.md` states this convention next to the governing-order rule.

For humans/tools that need the concrete source, the resolver can report:

```text
WC §7.4
  base: workflow-contract-v0.7.md §7.4
  effective replacement: class0-2026-10-01
  effective source: docs/design/workflow-contract-amendment-class0-2026-10-01.md#...
```

A later `aew docs resolve "WC §7.4"` command is useful but not required for the first Ticket; the Python resolver used by tests is enough.

## 5. Tests: `tests/unit/test_spec_amendments.py`

The first implementation stays deterministic and structural. Do **not** use the original proposal's paragraph-level heuristic ("the word amend appears nearby"); that is easy to satisfy accidentally and does not prove the citation is semantically current.

The unit test suite instead proves:

1. **Index integrity.** Every indexed path exists; ids are unique; statuses are valid; adopted entries carry adoption refs; supersession chains are acyclic; targets resolve to known WC/KC sections/cases.
2. **Single effective head.** No frozen target has two simultaneously adopted replacement heads.
3. **Map/index coverage.** Every adopted normative overlay listed by `docs/README.md` that affects WC/KC is indexed, and every adopted index entry is present in the governing-doc map. ADR-only mechanism amendments are not forced into the spec overlay index.
4. **Living citations resolve.** Parse `WC §…` / `KC §…` citations in living normative/guidance documents. An unversioned citation resolves through the effective overlay chain. An explicitly historical citation resolves against the named contract version.
5. **No research authority.** An adopted overlay's effective source cannot live under `research/`, `proposals/` or `archive/`.
6. **Pending debt is visible.** `pending` targets are emitted in one deterministic test/report section so the Ticket-revision and F15 consolidation debts cannot disappear. They are not treated as effective replacement text.
7. **Frozen files stay frozen.** Existing `test_spec_pin.py` continues to hash/pin the base set; the overlay test never mutates or rewrites it.

The citation resolver may reuse one closed regex for the repository's existing citation convention. It should not attempt natural-language interpretation of whether a paragraph "depends on" replaced wording.

## 6. Re-freeze and migration

The re-freeze remains scheduled **after M4-E makes F15 governing and before internal alpha**, because doing it earlier would predictably amend WC §15.6 twice.

Before that re-freeze:

1. write the missing Ticket-revision WC/KC amendment;
2. promote any governing decisions currently stranded inside `research/` into a design decision record or relevant ADR;
3. adopt/finalize the F15 overlay;
4. run the overlay resolver and clear every `pending` debt intended for the new base set;
5. fold the **effective adopted overlay heads** into WC v0.8 / KC v0.5;
6. create a new immutable spec manifest/pin/tag while preserving the old frozen set for historical resolution.

A new spec set does **not** silently rewrite existing projects. Migration is explicit and attributable:

```text
old spec_set
   ↓ aew migrate-spec / approved migration path
migration review + compatibility checks
   ↓
new spec_set
```

Existing old-spec projects remain readable/inspectable. Mutating under the new spec requires the migration rule to pass; the runtime must not silently mix old and new authority semantics in one active project.

The overlay index for the new frozen base starts clean for items consolidated into WC v0.8/KC v0.5; historical overlay entries remain available in the prior spec-set manifest/history rather than being re-applied to the new base.

## 7. Frozen designer disposition

**T7 — DESIGN FROZEN / PROPOSED FOR OPERATOR ADOPTION.**

Accepted:

- a machine-readable effective-spec overlay index;
- exact `replaces` / `extends` / `pending` targets;
- deterministic structural tests;
- re-freeze after M4-E and before internal alpha;
- explicit spec-set migration rather than mixed authority.

Modified from the research proposal:

- distinguish `design_frozen` from operator/repository `adopted`;
- index only overlays that affect WC/KC semantics, not every ADR self-amendment;
- bare living citations resolve through the overlay chain instead of requiring amendment words/ids in every paragraph;
- historical raw-text citations are version-qualified;
- no paragraph-level semantic heuristic in the test;
- no governing authority may remain only in `research/`;
- old spec sets remain historically resolvable after re-freeze.

Immediate implementation work is small: add the index schema/file, resolver/tests, populate it from the current repository, and write the missing Ticket-revision contract amendment. No further external research is required.
