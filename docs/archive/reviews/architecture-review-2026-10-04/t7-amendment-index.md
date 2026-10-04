# T7 — The amendment index: what the frozen contracts no longer say, and a test for citations

- **Status:** governance cleanup proposal from the independent architecture review (thread T7 of `HANDOFF.md`; `REVIEW.md` G6 and I-recommendation "amendment index"), 2026-10-04. Not governing. Produces a machine-readable index candidate, the list of amended sections, and a test sketch; the designer decides the v0.8/v0.5 re-freeze (handoff question 7).
- **Basis:** `docs/README.md` "What governs, in order"; `docs/spec-pin.yaml` and `docs/aew-spec-manifest-v0.2.yaml` (`freeze_rule`, `compatibility_rule`); the two amendments in `docs/design/`; the ADR amendment sections; `tests/test_spec_pin.py` and `tests/unit/test_docs_links.py`; a grep of every `WC §` and `KC §` citation in the living documents at `dcd43f1`.
- **Classification of statements:** everything in §1–§3 is read from the repository (documented fact). §4 and §5 are the proposal.

## 1. How the governing order works today, and the gap

The frozen set (`aew-frozen-2026-09-25`) is pinned by content hash; `tests/test_spec_pin.py` fails if any of the four files changes. The manifest's `freeze_rule` says discoveries are "tracked as implementation issues or ADRs/amendments" and the contract version is bumped only when normative semantics change. `docs/README.md` ranks: frozen set, then "adopted amendments and decisions", then ADRs, then the milestone plan, then indexes. "When documents disagree, the earlier one wins" is stated for that order, and the map lists the amendments by hand.

Two things the machinery does not do:

1. **Nothing records, in machine-readable form, which frozen sections an amendment replaces.** The Class 0 amendment says "**Amends:** Workflow Contract v0.7 §7.4 and §7.5" in prose; its §9 later also replaces a KC §26 acceptance case; the Ticket-revision review §7 lists KC §12 and WC §7, §8 and invariant 7 as needing "a spec amendment with an ADR, like ADR-0002's", which has not been written. A reader of WC §7.4 in the frozen file has no pointer to the amendment.
2. **Nothing checks citations.** `test_docs_links.py` checks that relative links resolve and that the map lists every document; it does not parse section citations. The living documents cite 36 distinct contract sections (`WC §…`, `KC §…`) 80 times at `dcd43f1`; a citation of an amended section without the amendment is undetectable today.

The handoff's REVIEW G6 called the re-freeze a question of *when*; this note's contribution is to make its *size* visible: the index below is the diff a v0.8/v0.5 re-freeze would consolidate.

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

## 4. The index: `docs/spec-amendments.yaml` (candidate)

A machine-readable sibling of `spec-pin.yaml`, listing every amendment on the map and the frozen sections it touches. Prose stays where it is; the index points.

```yaml
schema: aew/spec-amendments/v1
spec_set: aew-frozen-2026-09-25
amendments:
  - id: class0-2026-10-01
    path: docs/design/workflow-contract-amendment-class0-2026-10-01.md
    adopted: 2026-10-01
    status: adopted            # proposed | adopted | superseded
    enforced_since: M4-A
    replaces:                  # frozen sections whose text this document supersedes
      - {doc: WC, section: "7.4", anchor: "#2-amended-74-the-class-0-bullet"}
      - {doc: WC, section: "7.4", anchor: "#3-amended-74-examples"}
      - {doc: WC, section: "7.5", anchor: "#5-amended-75-the-class-0-path"}
      - {doc: KC, section: "26", case: "Parent risk policy propagation", anchor: "#9-..."}
    extends:                   # sections given new obligations, text unchanged
      - {doc: WC, section: "7.4", note: "reclassification is a recorded decision"}
  - id: ticket-revisions-2026-09-30
    path: docs/design/ticket-revision-amendment-2026-09-30.md
    review: docs/archive/reviews/ticket-revision-amendment-review-2026-09-30.md
    adopted: 2026-09-30
    status: adopted
    replaces: []               # it amends a proposal, not the frozen set
    pending:                   # frozen sections the adoption says must be amended, with no amendment yet
      - {doc: KC, section: "12", reason: "Ticket revisions beside plan revisions (review §7)"}
      - {doc: WC, section: "7",  reason: "review §7"}
      - {doc: WC, section: "8",  reason: "review §7"}
      - {doc: WC, section: "invariant 7", reason: "review §7"}
  - id: two-surfaces-v0.4
    path: docs/design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md
    adopted: 2026-10-01
    status: adopted            # "promoted to governing before M4-E"
    pending:
      - {doc: WC, section: "15.6", reason: "stages and ActionProjection (F15 §5, §15)"}
  - id: adr-0011
    path: docs/implementation/adr/0011-hot-cold-control-state.md
    adopted: 2026-10-03
    status: adopted
    extends:
      - {doc: KC, section: "12.3"}
      - {doc: KC, section: "15.1"}
      - {doc: KC, section: "21"}
  # one entry per ADR amendment section follows the same shape (ADR-0002, 0003, 0004, 0005, 0006, 0009)
```

Rules the file states: a `replaces` entry means "cite the amendment, not the frozen text, for this section"; a `pending` entry is a debt the re-freeze pays; `status: superseded` keeps history when an amendment is itself replaced (plan assurance v0.3 → v0.4 is the precedent).

## 5. Test sketch: `tests/unit/test_spec_amendments.py`

Three checks, none of which parses prose beyond a regular expression the repository already uses by convention (`WC §7.4`, `KC §26`):

1. **Every amendment on the map is in the index, and every index entry is on the map.** `docs/README.md` section 2 ("Adopted amendments and decisions") and the ADR list are the source; the test cross-references file paths, as `test_the_docs_map_lists_every_document` does for the whole tree.
2. **A citation of a replaced section names its amendment.** For every `replaces` entry, scan the living documents (the map's sets: guides, implementation, ADRs, design decisions; not the frozen set, not `archive/`, not `research/` and `proposals/`) for `WC §7.4`-style citations of that section. A citing paragraph passes if it also contains the amendment's path, id, or the word "amend" within the same paragraph; otherwise it fails naming the file and line. Expected on `dcd43f1`: the ADR-0003 and `lead-guide.md` citations of WC §7.4 pass (they cite the amendment); the KC §26 citations in `test_dispatch_decision`-era documents need checking; the result tells the designer how much the map's "by hand" discipline has held.
3. **No pending section is cited as settled.** For every `pending` entry, a citation of that section in a living document must carry a hedge marker the index defines (for example the amendment id in parentheses). This is the weakest check and may be dropped if it produces noise; it exists to make the Ticket-revision debt visible in `test` output, not only in a review §7.

The test runs in the unit lane (milliseconds: a few hundred files, one regex). It never reads the frozen files, so it cannot conflict with `test_spec_pin.py`.

**Expected failures on first run** (to be confirmed in the live repository, which this review does not write): citations of KC §26 and WC §7.4 that predate the Class 0 amendment's §9 (the parent-risk case changed on 2026-10-03), and any guide text that quotes WC §7.5's original Class 0 path.

## 6. Recommendation

1. Add `docs/spec-amendments.yaml` with the entries of §2, and the test of §5, as a documentation Ticket (Class 0 by the amended definition: a bounded subject, deterministic acceptance, no protected acceptance resource).
2. Write the Ticket-revision spec amendment the 2026-09-30 review asked for (KC §12, WC §7, §8, invariant 7) before M4-E, so that F15's WC §15.6 amendment is the last one before the re-freeze.
3. Schedule the v0.8/v0.5 re-freeze after M4-E and before internal alpha (handoff question 7), with the index as its change list and the manifest migration review as its gate.

## Not decided here

Whether `research/` decision sections (§8 of the containment note, §7 of the queue note) should move into `design/` as decisions records; the map treats them as governing in place, and the index can point at them either way.
