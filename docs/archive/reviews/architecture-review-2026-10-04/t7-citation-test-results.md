# T7 citation test, run once: what the amendment index catches in the living documents

- **Status:** probed fact for `T7-amendment-index.md` §5 (the test sketch), 2026-10-04. Read-only over two checkouts: this review's frozen `tree/` at `dcd43f1` (the map layout) and the live `Agentic-Engineering-Workflow` checkout at `56b85ad` on `impl/m4-b-containment` (the flat layout; `dcd43f1` is not an ancestor of it). The probe is `repro/t7/citation_probe.py`; its outputs are `repro/t7/citation_probe.dcd43f1.out.txt` and `repro/t7/citation_probe.live-56b85ad.out.txt`. The live checkout had untracked `docs/T7-amendment-index-v0.2.md` and sibling files (the designer's edited copies of this review's notes); they were not read and were not scanned.
- **Answer to TRIAGE §3 item 4.** The index touches a third of all contract citations. The naive test from the sketch (a citing paragraph must name the amendment) flags 13 of 18 citations of replaced sections, and 12 of those 13 are noise. With one refinement the index already anticipates (the `case`/topic field: a citation must name the amendment only when its paragraph is about the replaced text), the test flags exactly one citation on both checkouts, and that one is a real defect: `docs/guides/acceptance.md`'s AT-9 row still describes the frozen KC §26 case that the amendment replaced, while the test it points to implements the amended case. Check 3 (pending sections cited as settled) is noise in every instance and should be dropped.
- **Recommendation.** Build check 1 and the refined check 2 as the documentation Ticket `T7-amendment-index.md` §6 proposes; drop check 3; fix the AT-9 row. The re-freeze question is unchanged by this run.

## 1. Method

Documented fact, probe design. A citation is an explicit contract reference (`WC §7.4`, `KC §26`, `Workflow Contract §7.4`, `Knowledge Contract §26`, possessives and parentheses allowed) or `invariant N`. Bare `§N` without a contract name is counted, not judged (363 at `dcd43f1`; almost all are a document's own sections). Fenced code is ignored. A paragraph is a blank-line block; a table row or list item is its own paragraph.

The living set follows `docs/README.md` "What governs": `docs/**` minus the frozen set (`spec-pin.yaml`), minus `archive/`, `research/`, `design/proposals/` and `skills/`. Research is scanned and reported separately (its decision sections govern). On the flat live branch the same set is approximated by excluding files whose basename the map files under archive, research or proposals (`repro/t7/nonliving-basenames-dcd43f1.txt`); untracked files are ignored.

Index as in `T7-amendment-index.md` §2 and §4. Replaced: WC §7.4, WC §7.5, KC §26. Pending: KC §12, WC §7, WC §8, WC invariant 7, WC §15.6.

- **Check 2, naive** (the sketch): a citation of a replaced section passes if the paragraph contains "amend", "as amended", "class0" or the amendment's file name.
- **Check 2, refined**: as naive, but the paragraph has to be about the replaced text for the rule to apply. Topics: §7.4 → "Class 0", "eligib", "mechanical"; §7.5 → "Class 0"; KC §26 → "parent risk". The amendment document itself is not a citer.
- **Check 3**: a citation of a pending section passes if the paragraph carries a hedge ("pending", "not yet", "amend", "debt", "re-freeze", "Ticket revision").

## 2. Numbers

| | `dcd43f1` (map layout) | live `56b85ad` (flat layout) |
|---|---|---|
| Living documents scanned | 28 | 29 |
| Explicit contract citations (distinct sections) | 81 (39) | 98 (41) |
| WC / KC / of which invariants | 54 / 27 / 3 | 68 / 30 / 3 |
| Citations touching an indexed section | 27 (33%) | 33 (34%) |
| …of replaced sections / of pending sections | 18 / 9 | 18 / 15 |
| Check 2 naive: pass / fail | 5 / 13 | 5 / 13 |
| Check 2 refined: pass / fail | 17 / **1** | 17 / **1** |
| Check 3: hedged / cited as settled | 1 / 8 | 2 / 13 |

The live branch cites more because the pre-restructure layout keeps `ambiguity-report.md` and the M3 reports as living documents; the map archives them. Both branches flag the same 13 paragraphs under the naive rule and the same single row under the refined rule. Most cited (both): KC §26 (10), WC §7.4 (6), WC §5 (6 and 8), WC §8 (4 and 10), WC §7 (4 and 5). The counts at `dcd43f1` match the hand count in `T7-amendment-index.md` §1 (36 sections, 80 citations) within the regex's slightly wider net.

## 3. Every naive failure, judged by hand (probed fact, then inference)

| Citation | Paragraph | Depends on the replaced text? | Verdict |
|---|---|---|---|
| `guides/acceptance.md:33` (live: `implementation/acceptance.md:33`), KC §26 | AT-9 row: "its locally Class-0 Ticket keeps class 0, inherits the non-waivable gate… needs the security review before COMMIT_READY" | **Yes.** This is the frozen case verbatim in spirit. The amendment's §9.2 replaced it: Class 0 eligibility is *refused* with an inherited-elevated-obligation reason and the Lead reclassifies. `tests/acceptance/test_at8_at13_hierarchy.py::test_parent_risk_policy_propagation` (the row's own test) asserts the amended behaviour: `DISPATCH_REFUSED`, reason `CLASS0_INHERITED_ELEVATED_OBLIGATION`, reclassification to Class 1, the gate still required. The guide describes behaviour the code refuses. | **Defect, true positive** (both rules) |
| `acceptance.md:3, :24, :34, :35, :37`; `testing-and-ci-strategy.md:23`, KC §26 | "KC §26 scenarios", the existing-authority, promotion, fresh-session and backlog cases | No: other acceptance cases in the same section | Noise (naive only) |
| `guides/lead-guide.md:15, :23`, WC §7.4 | "a risk class is about the change's surface…"; the classification rules | No, and the guide's Class 0 bullet two lines later already states the amended definition ("work for which the Class 0 eligibility predicate holds") without naming the amendment | Noise (naive only); a one-phrase "as amended" would make the naive rule pass too |
| `adr/0007-epic-story-hierarchy.md:36`, WC §7.4 | "a unit's own `mandatory_gates` apply to its descendants" | No: inheritance, unchanged by the amendment | Noise (naive only) |
| `design/invariant-index.md:81`, WC §7.5 | "the gates themselves are the Workflow Contract's (§7.5)" | No: gates in general | Noise (naive only) |
| `design/plan-assurance-…-v0.4.md:1134`, WC §7.5 | "§7.5 paths remain the baseline execution obligations for Classes 1–4" | No: it excludes Class 0 explicitly | Noise (naive only) |
| `design/workflow-contract-amendment-class0-2026-10-01.md:99`, WC §7.4 | the amendment quoting the text it amends | By construction | Exempt the amendment's own file |

Check 3, all nine (`dcd43f1`) and thirteen (live) "cited as settled" hits: ADR spec-basis lines ("WC §8: a typical Ticket state model"), ADR-0006/0007 summaries of §7, and the live branch's ambiguity-report rows. Every one cites frozen text that is still in force; the pending amendment (Ticket revisions) would *add* to §7, §8 and KC §12, not replace what these paragraphs rely on. Nothing can be said about a citation of a pending section until the amendment exists and says which sentences change. Verdict: drop check 3 from the test; keep `pending` entries in the index as the re-freeze's debt list, which is what they are for.

## 4. What this settles for `T7-amendment-index.md`

1. **The test is worth building, in its refined form.** One regex, 28 files, a few milliseconds; on the first run it finds one real contradiction between a guide and the code, which `test_docs_links.py` cannot see. The index's `case` field is not optional: without a topic per replaced entry the test has 8% precision; with it, 100% on this corpus (one flag, one defect).
2. **The index needs one more field per `replaces` entry: `topic`** (a short pattern or word list that marks a paragraph as being about the replaced text), beside `anchor`. The candidate in §4 of the design note gains `topic: ["Class 0", "eligib", "mechanical"]` for §7.4, `["Class 0"]` for §7.5, `["parent risk"]` for KC §26. A `replaces` entry without a topic falls back to the naive rule, so the field can be filled lazily.
3. **The amendment's own file is exempt**, and so is any file the index lists as an amendment.
4. **Drop check 3.** `pending` stays in the index as data for the re-freeze, not as a test input.
5. **One documentation fix now, independent of the test:** `docs/guides/acceptance.md` AT-9 row should describe the amended case (refused eligibility, reclassification, the gate still required) and cite `workflow-contract-amendment-class0-2026-10-01.md` §9, as its test's docstring already does. On the live branch the file is `docs/implementation/acceptance.md`.
6. **Smaller:** `docs/guides/lead-guide.md` "Choosing a risk class" could say "(WC §7.4, as amended)" where its Class 0 bullet already follows the amendment. Not a defect; it makes the guide's provenance visible.

The re-freeze question (handoff question 7) is not moved by this run: the citations that would need rewriting at a v0.8/v0.5 re-freeze are the 18 of replaced sections, all in six files, and the pending debt is the Ticket-revision amendment, still unwritten.

## 5. Hypotheses, unverified

- The same probe over the M3-era archive documents (not run; they are finished records) would show the frozen KC §26 case described several more times; that is history, not drift.
- A `topic` match is a proxy for "depends on the replaced text". A paragraph that discusses Class 0 and cites §7.4 for something else would be a false flag; none occurs in this corpus. The failure mode is a flag a human dismisses in a minute, not a missed contradiction.

## 6. How to rerun

```bash
.venv/Scripts/python repro/t7/citation_probe.py tree --layout map
.venv/Scripts/python repro/t7/citation_probe.py <live checkout> --layout flat --nonliving repro/t7/nonliving-basenames-dcd43f1.txt
```

The probe reads the checkout and writes nothing into it.
