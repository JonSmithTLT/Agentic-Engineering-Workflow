<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-43
source: 30-stages/STG-19-I7-research-links-and-mission-wire/adopted/o01-0.9-i7/I7-PROFILE.md
source-sha256: 5bf054e44617fcdb4991f96e5e9c79ed3ec37255cee01db2773fe9dd7cda6ee6
edits-sha256: none
-->

# I-7: the wire for research, links and the mission, selection profile (PROPOSED, revision 3)

**Namespace:** `I7-`
**Status:** proposed, revision 3, 2026-10-25, for the O-01 `o01-command-0.9-candidate` wire in `wire/`, the successor of A-39's 0.8. Revision 2 answered round 1's eighteen findings (`CHANGES-r2.md`); revision 3 answers the quick check's reopened finding and its four new ones (`CHANGES-r3.md`).
- It serves A-32's `W11`, and the commands that A-40, A-41 and A-42 hand to I-7.
- **It amends, for the operator to confirm at adoption** (`I7-00`'s departure table):
  - the targets of two carried types: `CREATE_PROPOSED_WORK` (A-29) gains two work kinds, a typed asking work and a mission's bounds (`I7-04`), and `SET_STEERING_MODE` (A-39) gains the mission a raise is bound to (`I7-07.c`);
  - A-39's `I6-06.a`, `I6-06.f` and `I6-06.g`: the bound raise's admission condition, its coming into force when its mission opens, and its lapse (`I7-07.c`);
  - the set rules beside `I6-11`, by three rules for a mission's consent (`I7-15`);
  - A-32's classification: `W13` needs no command, and ten new types have no catalogue row yet (`I7-R06`).
- **It carries erratum E-1,** the operator's decision on the as-built trace's flag on HEB's interim refusal codes: three of HEB's own refusals join A-34's `CONTINUE_ELIGIBLE_WORK` reason map (`I7-00.a`).
- No other adopted byte changes.
**Authority:** the operator's instruction of 2026-10-25, "Start I-7, the wire track's next step, briefed from A-40, A-41 and A-42", under the wire-track decision (`00-governance/decisions/2026-10-25-operator-wire-track-ahead-of-publication-tooling.md`) and the selection before I-7 (`00-governance/decisions/2026-10-25-operator-selection-before-I-7.md`). Revision 2: the operator's instruction of 2026-10-25, "File I-7's round 1, register I71 in FINDINGS.json, and write revision 2". Revision 3: the operator's instruction of 2026-10-25, "File the quick check, register I72 [...] in FINDINGS.json, and write revision 3 with CHANGES-r3.md".
**Threat model:** the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`): a contained agent cannot fake an approval, forge an owner fact, read a credential or escape. Malicious code running as the operator is out of scope (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`). Here the approvals at stake are the acceptances of an inquiry and a mission, the operator's stop, and the continuation. The owner facts are who accepted, stopped, recorded or relied on what.
**Research consulted:**
- **For `CNI-07`:** the software research workflow study (`software-research-workflow-2026-10-15`, `private:software-research-workflow-2026-10-15/`, partly adopted), which A-40 and A-41 already took in. This profile adds nothing from it.
- **For `P-DEC-02`:** the project-understanding and impact-analysis study and the semantic extension framework study (both 2026-10-04), which decided that maps are derived. `I7-00`'s row for `W13` follows them.
- **For A-24, A-29, A-32, A-37, `RX01-03`, `RX01-05`, `RX01-19`, `WIS-02`, `CNI-03`, `I6-06`, `G3-08` and `K-DEC-04`:** none.
**Files:** this profile; `I7-WIRE-SPEC.json` and `wire/`, generated from A-39's frozen 0.8 bytes; `verify_i7.py` and `i7-cases.json`; the working notes `work/AS-BUILT-READ.md` and `work/FIT-CHECK-NOTES.md`, which are not normative.

## What the adopted text already decides

- **The research types** (A-40): an inquiry is WIS work of its own kind, completed by one of six dispositions, never by a PASS (`WISR-01`, `WISR-02`). A disposition carries its grounds, by hash and path, or a reason; each open question carries a next check, an owner or a reason to stop (`WISR-02.a`). AEW reads a cited path only as the citing agent could, and hashes the bytes itself (`WISR-03.a`). An author revises a claim in one step (`WISR-03.d`). A request link records who asked, and a consumption link records reliance (`WISR-05`, `WISR-06`).
- **Who accepts and who stops an inquiry** (`WISR-R03`, `WISR-02.b`): a standalone inquiry, or one beyond a Ticket's scope, is the operator's choice of research direction, `W11`, through G3. One inside a Ticket's scope is the Lead's record under that Ticket's acceptance, which accepts nothing new. The operator stops one it accepted through G3; the Lead or the Ticket's accepting authority stops a held one.
- **The link vocabulary** (A-41): five kinds, written by AEW's host code from an authenticated command, an owner's decision or canonical facts (`CNIL-01`, `CNIL-02`). An end is resolved by content within the recorder's view, and a link to an unresolved, ambiguous, unaccepted or mismatched end is refused, saying which end and why (`CNIL-02.a`). A document is never an end (`CNIL-09`). Held reliance is one step (`CNIL-02.b`); an own-work dependency holds only its own side, and is recorded by an agent AEW observes assigned to the dependent work (`CNIL-01.b`); a proposal is advisory (`CNIL-05`). Cross-project links are backlog (`CNIL-B1`).
- **The mission** (A-42): accepted through G3 with one consent of its acceptance, its cap and its mode, and if the acceptance or the cap fails, nothing of the set is in force for it (`MSN-04`, `MSN-Q08`); at most one open per project (`MSN-01.b`); bounded by a window and its drain within a day, which the operator may lower in the consent (`MSN-R06`); stopped by the operator through a reducing type (`MSN-06`); continued after a stop by one G3 action (`MSN-06`). The cap is issued `COOPERATIVE` unless R-01 qualifies the class (`MSN-05`).
- **The adopted path for proposals** (A-29): `CREATE_PROPOSED_WORK` from the Lead's seat records a provisional proposal, with the proposer's generation, and grants nothing (`I5-02`). `DECIDE_WORK_PROPOSAL` accepts one exact proposal, every leaf equal to WIS's record (`I5-03`). A root names an operator-authored instruction (`ADC-01.c`).
- **Sets and consents** (A-24, A-25, A-37, A-39): one origin class per set (`CS-02`). Members are evaluated in canonical order, each against owner state as earlier members left it (`CS-05`). Consent to one member never authorizes another (`CS-06`). One member per subject (`I6-11`). G3 issues one consent record per approval, bound to one set digest and current for at most 15 minutes (`G3-06`); each protected member is admitted, and consumed once, against it (`CS-06`); and each owner admission binds that set digest (A-24's owner-set coupling, the second correction of its first-slice protocol). An identical retry is a lookup of the stored receipt, and a held member progresses only under a new key and, for a protected action, a new consent (`CS-04`, `CS-08`).
- **What the operator sees** (A-37): G3 renders every covered leaf of a member from records, plus at most one owner fact, and a protected intent is a closed object of scalar leaves (`G3-03`). The largest member is 30 lines (`I6-12`).
- **Directions:** a protective reduction is admitted on its consent alone, not blocked by irrelevant basis changes (`AOI-07.f`). The owner derives the direction from the operation (`AOI-07.c`).
- **Resource scopes** (A-21): every resource policy binds "root and ancestor project/mission/provider/pool/window scopes" (`IF10-02`), so a mission's work is an admitted scope for its cap.

**What is missing:** no O-01 type serves an inquiry, a mission, a link record or a researcher's record; `CREATE_PROPOSED_WORK` knows only Epics, Stories and Tickets; and no adopted rule binds a mode raise to a mission.

## The parts

| Party | What it is | Who writes it | Who reads it |
|---|---|---|---|
| WIS | the owner of work identity: inquiries, missions, their acceptances, stops and continuations, dispositions, claim links and consumption links | WIS, on the operator's G3 consent, the Lead's seat or a researcher's delegated invocation | every owner; the operator, through D-01 |
| Coordination (CNI) | the owner of dependencies and proposed impacts | CNI, from the Lead's seat or accepted content | WIS, HEB, R-01; the operator |
| R-01 | the steering mode's owner, and the cap's admission at effect time | R-01, on the operator's consent | the auto-runner; the operator |
| The resource policy issuer | the cap's issuer (`ISSUE_STANDING_POLICY`) | the issuer, on the operator's consent | R-01, WIS |
| ADC | the in-scope determination for a held inquiry, and the lineage of an author | ADC | WIS |
| The researcher | a worker run dispatched on an inquiry, under its own delegated invocation (as built: a non-mutating Ticket's executor) | its disposition and claim revisions, through WIS | WIS; the inquiry's readers |
| The Lead | the project's current Lead generation | its proposals and its one-step records, through WIS and CNI | WIS, CNI |

## Rules

### The fit

**I7-00. The fit: `W11` gets a new type, `W13` needs no command, `W12` and `W14` wait for K-01, and ten more new types serve the rest of A-40's, A-41's and A-42's candidates.** No row moves from operator origin to delegated. One row leaves operator origin: `W13`, which A-32 classed `OPERATOR_ORIGIN_G3`, needs no command here, and the departure table puts that to the operator. Each decision, with the reading that decided it, is in `work/FIT-CHECK-NOTES.md`.

| Row | Catalogue symbol | Fit | Reason |
|---|---|---|---|
| W11 | `CHOOSE_RESEARCH_DIRECTION` | **New type `ACCEPT_INQUIRY`, protected, owner `WIS`, `PRESERVING_OR_INCREASING`** (`I7-05`) | `WISR-R03`: an inquiry beyond a Ticket's scope is the operator's choice. `DECIDE_WORK_PROPOSAL` renders at 28 of G3's 30 lines, and the typed asker takes three leaves more (`I7-R01`) |
| W12 | `ADMIT_KNOWLEDGE_CLAIM` | **No type: K-01's own increment, after V-01** (the selection before I-7, choice 1) | Knowledge admission is K-01's, and its increment follows V-01 |
| W13 | `SELECT_MAP_SOURCE_OR_DIFF` | **No O-01 command:** a map is derived, and selecting one protects nothing (`P-DEC-02`) | Maps are derived and reachable by agents, with no protected writer. The built `aew map select-architecture` is the Lead's, and a map's diff is a read |
| W14 | `ACCEPT_OR_REJECT_SOURCE_AUTHORITY` | **No type: K-01's own increment, after V-01** (the selection before I-7, choice 1) | Source authority is K-01's, and its increment follows V-01 |

**The new types no catalogue row names**, each from an adopted candidate:

| Type | From | Owner | Origin | Direction |
|---|---|---|---|---|
| `STOP_INQUIRY_OR_MISSION` (`I7-02`) | A-40's and A-42's operator stops (`WISR-02.b`, `MSN-06`) | WIS | `PROTECTED_G3` | `REDUCING` |
| `STOP_HELD_INQUIRY` (`I7-03`) | A-40's held-inquiry stop (`WISR-02.b`) | WIS | the Lead's seat | `REDUCING` |
| `OPEN_HELD_INQUIRY` (`I7-06`) | A-40's held inquiry (`WISR-R03`) | WIS | the Lead's seat | `PRESERVING_OR_INCREASING` |
| `ACCEPT_MISSION` (`I7-07`) | A-42's acceptance (`MSN-01`, `MSN-04`) | WIS | `PROTECTED_G3` | `PRESERVING_OR_INCREASING` |
| `CONTINUE_AFTER_MISSION_STOP` (`I7-08`) | A-42's continuation (`MSN-06`) | WIS | `PROTECTED_G3` | `PRESERVING_OR_INCREASING` |
| `RECORD_INQUIRY_DISPOSITION` (`I7-09`) | A-40's disposition (`WISR-02`) | WIS | `CURRENT_DELEGATED_GRANT` | `PRESERVING_OR_INCREASING` |
| `REVISE_CLAIM` (`I7-10`) | A-40's claim revision (`WISR-03.d`) | WIS | `CURRENT_DELEGATED_GRANT` | `PRESERVING_OR_INCREASING` |
| `RECORD_HELD_CONSUMPTION` (`I7-11`) | A-41's held reliance (`CNIL-02.b`) | WIS | the Lead's seat | `PRESERVING_OR_INCREASING` |
| `RECORD_OWN_WORK_DEPENDENCY` (`I7-12`) | A-41's own-work dependency (`CNIL-01.b`) | CNI | the Lead's seat | `PRESERVING_OR_INCREASING` |
| `PROPOSE_IMPACT` (`I7-13`) | A-41's proposed impact (`CNIL-05`) | CNI | the Lead's seat | `PRESERVING_OR_INCREASING` |

**No type:**
- **the dependency record and the consumer binding,** a consumption recorded at an acceptance, and the mission's lists, which ride accepted content (`I7-14`);
- **the mode's lapse at a stop,** which is R-01's record on WIS's record of the stop (`MSN-04.a`);
- **`STOPPED` recorded by AEW's host code** at a window's or a scope's end (`WISR-02.b`).

**The departures from the adopted text, which the operator confirms or refuses at adoption:**

| What | The adopted text | This profile | What changes for the operator |
|---|---|---|---|
| `W13` | its own type, origin `OPERATOR_ORIGIN_G3` (A-32) | no O-01 command (`P-DEC-02`) | Choosing a map is not an approval. A map changes no authority, and the Lead's choice is visible and reversible |
| `CREATE_PROPOSED_WORK` (A-29) | Epics, Stories and Tickets, with a parent | also inquiries and missions, which have no parent, with an optional asking work and a window's and a drain's end (`I7-04`) | The Lead proposes research and missions on the path it proposes work on. An Epic, a Story or a Ticket is proposed as before, with `asked_by`, `window_end` and `drain_end` sent as `null` |
| `SET_STEERING_MODE` (A-39) | the mode for a Lead generation, until that generation ends (`I6-06.g`); it changes only through this type (`I6-06.f`) | **One added field,** `mission_ref`, sent as `null` for A-39's raise. A raise bound to a mission comes into force when that mission opens in the raise's own consent, or at its admission if the mission is already open, and lapses at its stop (`I7-07.c`). **This is outside `MSN-04`'s two named options** (A-24's set rule, or `I6-06.a`'s admission conditions): it is a target leaf, an admission condition on `I6-06.a`, a force condition on `I6-06.g`, and a raising path on `I6-06.f` limited to the raise's own consent (`I7-R03`) | A `RUN` raised to start a mission comes into force only with that mission, in that one consent, and never outlives it. A raise bound to a mission already open is in force at once, until that mission's stop. A raise outside a mission is as A-39 has it |
| The set rules (A-24, A-39) | members evaluated one by one (`CS-05`), and one member per subject (`I6-11`) | three set-level rules for a mission's consent, read from the members' leaves, like `I6-11` (`I7-15`) | A mission's consent that would leave its raise or its cap unbound, or carries two mission acceptances, is refused before the PIN, saying why |
| A-32's catalogue | 86 rows | ten new types with no row yet (`I7-R06`) | The operator confirms the rows, or leaves the types unrowed |

**I7-00.a. Inherited definitions change in four places only:**
- **`CREATE_PROPOSED_WORK`'s target:** two added kinds (`inquiry`, `mission`), and three added fields (`asked_by`, `window_end`, `drain_end`), each required and nullable; and one added reason (`ASKER_NOT_CURRENT`) (`I7-04`);
- **`SET_STEERING_MODE`'s target:** one added field (`mission_ref`), required and nullable, and four added reasons (`I7-07.c`).

  Both branches and registry rows are carried byte-equal, and `PREDECESSOR-PINS.json` lists both;
- **`CONTINUE_ELIGIBLE_WORK`'s reason map** (A-34, carried by A-39), by erratum E-1: `HEB_STALE_PREDECESSOR` and `WORK_NOT_CURRENTLY_ELIGIBLE` (`PRECONDITION_STALE`) and `HEB_STATE_UNKNOWN` (`SOURCE_UNAVAILABLE`), HEB's own refusals, in the categories the as-built slice reports them under. Its target, branch and registry row are unchanged. This is the operator's decision on the as-built trace's flag on HEB's interim refusal codes (`00-governance/decisions/2026-10-25-operator-S12-4-flags-batch-1.md`), which puts E-1 in the wire track's next O-01 revision, and answers the first gap STG-02's backend recorded (`30-stages/STG-02-first-vertical-slice/gap-entries/backend-080010f1-GAP-ENTRIES.md`). `PREDECESSOR-PINS.json` lists it, as changing its refusals only;
- **the generator,** which learns to emit A-24's `CURRENT_DELEGATED_GRANT` class, in the shape `DELEGATED_CANCEL` has: the target names the invocation and its grant, and the subject and proof slots are A-24's.

The owner enums are unchanged: WIS and CNI are already in them.

**I7-00.b. The direction is derived by the owner from the operation, never from a label** (`AOI-07.c`).
- **The two stops are `REDUCING`:** each ends an inquiry or a mission, and enables nothing.
- **Every other new type is `PRESERVING_OR_INCREASING`:** an acceptance or a continuation enables runs, and a record adds a fact others act on.

### Who owns what

**I7-01. Each type has one sole admitting owner, which records only its own facts, and owner facts are AEW's observation** (as `I6-01` states for I-6).
- **Who accepted, stopped, continued, recorded or relied** is taken from the authenticated command and the owners' records, never from a value the caller supplies (`WISR-09`, `CNIL-02`, `MSN-12`). No target has a field for a recorder, a decider or an acceptance, so a command naming one is `invalid_request`, naming the field.
- **Every other owner's fact is read as an input:** ADC's in-scope determination and lineage, the issuer's cap, HEB's seat and dispatches, R-01's mode, and the G3 consent record each protected member was admitted under (`G3-06`, `CS-06`).
- **The Lead's view** is its own project's subjects, and a researcher's is its inquiry's project's. A subject of another project resolves exactly as an absent one (`CNIL-02.a`): a Lead record naming another project's work is `WORK_UNKNOWN`, and a link end of another project is `END_UNRESOLVED`, so a refusal never tells an agent that the reference exists elsewhere. The operator sees every project, so the operator's types refuse another project's work as `PROJECT_MISMATCH`. Cross-project links wait for `CNIL-B1`.
- **A refusal says what happened and what to do instead** (the security depth reset, point 7). Each refusal that has another path names it, as this table lists; the others say what is missing or stale.

**The refusals that name another path:**

| Type | Refusal | Names instead |
|---|---|---|
| `STOP_INQUIRY_OR_MISSION` | `NOT_WORK_AUTHORITY` | the Lead's `STOP_HELD_INQUIRY`, then cancelling the Ticket, `CANCEL_OR_REPLACE_TICKET` |
| `STOP_HELD_INQUIRY` | `NOT_HELD_INQUIRY` | the operator's `STOP_INQUIRY_OR_MISSION` |
| `OPEN_HELD_INQUIRY` | `OUT_OF_TICKET_SCOPE` | the operator's path: `CREATE_PROPOSED_WORK`, then `ACCEPT_INQUIRY` |
| `ACCEPT_MISSION` | `MISSION_ALREADY_OPEN` | the open mission's stop, `STOP_INQUIRY_OR_MISSION` |
| `RECORD_INQUIRY_DISPOSITION` | `STOP_NOT_RESEARCHERS` | the researcher's own `DEFERRED`, with a reason, or asking the inquiry's authority |
| `RECORD_INQUIRY_DISPOSITION` | `REVISION_STALE` | the Lead's redispatch of the inquiry at its current revision |
| `RECORD_OWN_WORK_DEPENDENCY` | `NOT_ASSIGNED` | the advisory `PROPOSE_IMPACT` |
| `SET_STEERING_MODE` | `BOUND_CHANGE_NOT_A_RAISE` | an unbound `SET_STEERING_MODE`, with `mission_ref` null |
| `SET_STEERING_MODE` | `MISSION_CLOSED` | a new mission, `CREATE_PROPOSED_WORK`, or an unbound `SET_STEERING_MODE` |

### The stops

**I7-02. With the operator's consent, WIS stops one inquiry or one mission, and the stop only reduces.**
- **The target names:** the work's kind (`inquiry` or `mission`), the work, and a reason reference. It names no revision: the stop ends the work, whatever its revision.
- **What it records:**
  - for an inquiry, the disposition `STOPPED`, attributed to the operator. What it found stays (`WISR-02.g`);
  - for an open mission, the stop, with its cause "the operator's stop". The stop's hold and the mode's lapse follow from WIS's record (`MSN-06`, `MSN-04.a`);
  - for a mission still opening, which only a concurrent set can meet (`I7-07.b`), "never opened", with no stop, no hold and no lapse: nothing ran under it.

**I7-02.a** WIS admits it only if:
- the work is of the kind named and of the subject's project (`WORK_UNKNOWN`, `WORK_KIND_MISMATCH`, `PROJECT_MISMATCH`);
- it is not already stopped, completed or never opened (`WORK_CLOSED`);
- the operator is the work's authority, from WIS's own records (`WISR-02.b`; `NOT_WORK_AUTHORITY`):
  - a mission;
  - an inquiry the operator accepted;
  - an inquiry held under a Ticket whose accepting authority is the operator. For a Ticket accepted in scope (`I5-03`), that is the authority of the acceptance its in-scope determination rests on, followed up to the first acceptance that was not in scope.

It is admitted on the operator's consent alone. It reads no competence and no other owner's fact, so no change to irrelevant basis members blocks it (`AOI-07.f`), as `STOP_CHILD_NOW` is admitted.

**I7-03. The Lead stops an inquiry held under a Ticket's scope, from its own seat.** The target names the inquiry and a reason reference.
- **WIS admits it only if:**
  - the actor is the project's current Lead generation (`ACTOR_NOT_CURRENT_LEAD`, `GENERATION_FENCED`). `WISR-02.b`'s "the Lead who opened it" is read as the project's Lead seat, so a successor generation after a takeover may stop it (`HEB-08.f`);
  - the inquiry is of the subject's project, another project's resolving as absent (`WORK_UNKNOWN`, `I7-01`), and held under a Ticket's scope (`NOT_HELD_INQUIRY`);
  - it is still open (`WORK_CLOSED`).
- **What it records:** `STOPPED`, attributed to the Lead (`WISR-02.b`).

### Proposals and acceptances

**I7-04. `CREATE_PROPOSED_WORK` also proposes an inquiry or a mission, and names who asked and the mission's bounds.**
- **The amended target:**
  - `work_kind` gains `inquiry` and `mission`;
  - `asked_by` names the asking work: its kind (an Epic, a Story, a Ticket or an inquiry), its reference and its accepted revision, or `null`;
  - `window_end` and `drain_end` name a mission's window's end and drain's end, and an inquiry's window's end as its stop condition, or `null`.
- **Everything else** in `I5-02` is unchanged: the proposal is provisional, grants nothing, records the proposer's generation, and is accepted only by a competent acceptance.

**I7-04.a** WIS admits an inquiry or a mission proposal only if:
- it names no parent: an inquiry and a mission are never children, and a request never makes one (`CNIL-Q02`; `PARENTAGE_INVALID`);
- `asked_by`, where given, names work of the subject's project at its current accepted revision (`ASKER_NOT_CURRENT`);
- a mission names no asker, and names both ends, the drain's after the window's; an inquiry names no drain's end (`PROPOSAL_SHAPE_INVALID`);
- a root names the operator's instruction (`ADC-01.c`; `ORIGIN_SOURCE_MISSING`), unless an inquiry names its asker, whose request is its origin (`WISR-05`).

An Epic, a Story or a Ticket names none of the three new fields (`PROPOSAL_SHAPE_INVALID`), and its origins stay `I5-02`'s.

**I7-05. With the operator's consent, WIS accepts or declines one exact inquiry proposal: A-32's W11, the operator's choice of research direction.**
- **The target names:**
  - the proposal and its content's SHA-256: the question, its boundaries and governing sources;
  - the work, and its expected and original accepted revisions, or `null`;
  - the asker's kind, reference and accepted revision, all three or none;
  - the originating instruction, or `null`, and the provenance;
  - the window's end set as its stop condition, or `null`;
  - `ACCEPT` or `DECLINE`, and an external authority's decision, or `null`.
- **On `ACCEPT`,** WIS records the inquiry's accepted revision, attributed to the consent and the competent authority, and the request link from the asker (`WISR-05`). Every other open proposal at the same expected revision is superseded, as `I5-03` does.
- **On `DECLINE`,** it records only that.

**I7-05.a** WIS admits it only on `I5-03`'s checks (the proposal known and open, the revisions current, competence, and every leaf equal to WIS's record of the proposal, `RECORD_MISMATCH`), and only if:
- the proposal is an inquiry's (`WORK_KIND_MISMATCH`);
- the asker is still at its named accepted revision (`ASKER_NOT_CURRENT`);
- a window's end is the proposal's, or earlier, or set where the proposal names none, and after the admission (`WINDOW_INVALID`). An earlier or a newly set one is the operator's own lowering in the consent (`MSN-R06`'s tripwire, read for an inquiry too); a later one, or none where the proposal names one, is `RECORD_MISMATCH`.

The content is held for the operator's read before consent, or the member is held (`CONTENT_READ_UNAVAILABLE`, as `I5-08` has it). An inquiry that a Ticket's scope covers may still be accepted here: the operator's acceptance takes it on as the operator's, and accepts more than the Lead's record would (`I7-R07`).

**I7-06. The Lead records an inquiry held under a Ticket's accepted scope, and accepts nothing new** (`WISR-R03`).
- **The target names:** the Ticket and its accepted revision, the inquiry's content SHA-256, and the window's end as its stop condition, or `null`.
- **WIS admits it only if:**
  - the actor is the project's current Lead generation (`ACTOR_NOT_CURRENT_LEAD`, `GENERATION_FENCED`);
  - the work is a Ticket of the subject's project, open at that accepted revision (`WORK_UNKNOWN`, another project's resolving as absent; `WORK_KIND_MISMATCH`, `REVISION_STALE`, `WORK_CLOSED`);
  - the content is held (`CONTENT_UNAVAILABLE`), and a window's end, where named, is after the admission (`WINDOW_INVALID`);
  - ADC determines the inquiry within the Ticket's accepted scope (`ADC-03.a`), read as an input, as `I5-03`'s in-scope acceptance reads it. Outside it, the refusal names the operator's path (`OUT_OF_TICKET_SCOPE`). With the determination unavailable, the member is held (`SCOPE_DETERMINATION_UNAVAILABLE`).
- **What it records:** the inquiry, held under the Ticket's acceptance, with the request link from the Ticket. It reads as held, never as accepted, and never as the operator's (`WISR-07`). It ends when the Ticket's scope ends (`WISR-02.b`).

**I7-07. With the operator's consent, WIS accepts or declines one exact mission proposal.**
- **The target names:**
  - from the proposal: the proposal and its content's SHA-256 (the objective, the coverage, the stop conditions, the reserved decisions and the report point, which the operator reads before consenting, `MSN-01`); the work and its expected accepted revision, or `null`; the originating instruction; the provenance; and the window's end and the drain's end;
  - the operator's own: `ACCEPT` or `DECLINE`; the Lead generation it starts under, checked against HEB's seat; the cap's policy decision, bound to the consent's cap member (`I7-15`); and the preflight's SHA-256, so that what the operator saw is part of what was approved (`MSN-03`).
- Its rendering fits within G3's 30 lines (`I7-16`).

**I7-07.a** WIS admits it only on `I5-03`'s record checks of the proposal's leaves, and only if:
- the proposal is a mission's (`WORK_KIND_MISMATCH`);
- no other mission of the project is open or opening (`MSN-01.b`; `MISSION_ALREADY_OPEN`, naming it). A mission is opening only while its own set is being admitted (`I7-07.b`), so this meets one only in a concurrent set;
- the window's end and the drain's end are each the proposal's, or earlier, the operator's own lowering in the consent (`MSN-R06`); a later one is `RECORD_MISMATCH`;
- the window's end is after the admission, the drain's end is after the window's end, and both are within 24 hours of the admission, the mission's start (`MSN-R06`; `WINDOW_INVALID`);
- the Lead generation is the project's current one (`GENERATION_NOT_CURRENT`; `LEAD_STATE_UNAVAILABLE` holds);
- the preflight digest is WIS's record of the preflight read for that proposal (`PREFLIGHT_MISMATCH`).

The content is held for the operator's read before consent, or the member is held (`CONTENT_READ_UNAVAILABLE`).

**I7-07.b** **The one consent opens the mission, or nothing does** (`MSN-04`, `MSN-Q08`).
- **The rule:** a mission opens only when its acceptance and its cap are both admitted in the admission of the one set the operator consented to. Otherwise it never opens: WIS records it as "never opened", with no stop, no hold and no lapse; it blocks no later acceptance; and a raise bound to it never comes into force. "Never opened" is final: nothing admitted later opens it.
- **Once open,** it stays open until a stop (`MSN-06`). A later narrowing or revocation of its cap changes which paid routes are eligible under it, never whether it is open (`MSN-05`). After a revocation, every paid admission under the open mission is held, whatever other policy covers it, as at a reached cap (`MSN-05`, `MSN-01.c`). The end of the Lead's generation does not end it (`MSN-06.a`).
- **How WIS tells, in any member order:** the acceptance and the cap are each admitted against a G3 consent record, which G3 issues once per approval and binds to one set digest (`G3-06`, `CS-06`); each owner admission binds that digest (A-24's owner-set coupling). WIS reads the record its acceptance and the issuer's admission of the cap were admitted under, as owner facts. The client's `request_set_ref` decides nothing here: no adopted rule makes it unique across sets.
  - **Opening:** accepted, while that set's admission (`CS-05`) is under way, and no longer: its receipt is then stored under its key (`CS-08`).
  - **Open:** within that admission, an issuance of the mission's named cap, scoped to its work, was admitted under the same consent record.
  - **Never opened:** that admission completed without it. An identical retry returns the stored receipt (`CS-04`), and a held member progresses only under a new key and a new consent (`CS-08`). Should a held cap member still be admitted under the same record, by a new key within its 15 minutes (`CS-06` consumes a member only when its owner operation is allocated), the mission stays never opened, and that issuance counts for nothing.
- **On `ACCEPT`,** WIS records the mission's accepted revision and its attachment identity: the project, the Lead generation and the grant in force, observed, never supplied (`MSN-01`, `MSN-12`).

**I7-07.c** **What the other members do, in any order** (`MSN-04`, `CS-05`):
- **The cap:** its `ISSUE_STANDING_POLICY` names the mission's work as its `resource_scope_ref`, a scope `IF10-02` admits. It counts, and makes a paid route eligible, only for admissions under the open mission (`MSN-01.c`). Its expiry is the drain's end (`MSN-05`). Its target is unchanged.
- **The mode:** `SET_STEERING_MODE` gains `mission_ref`, the mission a raise is bound to, or `null`.
  - **Its admission (`I6-06.a`'s added condition):** R-01 reads the named mission from WIS as an accepted mission, or an open mission proposal, of the subject's project (`MISSION_UNKNOWN` is neither). A stopped or never-opened one is `MISSION_CLOSED`. The change must be a raise above the mode in force (`BOUND_CHANGE_NOT_A_RAISE`). With WIS's state unavailable, the member is held (`MISSION_STATE_UNAVAILABLE`).
  - **Its force (`I6-06.g`'s added condition, and `I6-06.f`'s added path):** a bound raise is in force only while its mission is open, and only if it was admitted under the consent record its mission opened under, or its mission was already open when it was admitted. It lapses to `CRAWL` at the mission's stop. Until it comes into force, the mode in force is as it was.
  - **The mode in force is R-01's record:** the newest of R-01's records that is in force, being an unbound raise from its admission, a bound raise while its conditions hold, or the lapse R-01 records at a stop (`MSN-04.a`). The current mode a consent names, and G3 renders, is that mode at that record's version, as `I6-06.a` checks it (`MODE_STALE`).
  - **A `null` mission** is A-39's raise, unchanged.
- **The continuation,** where the set carries one, is the operator's own act, and stands whether or not the mission opens (`MSN-04`).

So in every canonical order:
- with the acceptance refused, the cap counts nothing and the raise never comes into force;
- with the cap refused, the mission never opens and the raise never comes into force;
- nothing admitted later opens a mission that never opened, or brings a raise bound to it into force: not a later consent of the cap alone, not an acceptance alone (`invalid_request`, `I7-15`), and not a held member admitted later under the same consent record.

### The continuation

**I7-08. With the operator's consent, WIS continues after a mission's stop, and clears its hold.**
- **The target names:** the mission, the stop record it clears, and a reason reference.
- **WIS admits it only if:**
  - the mission is a mission of the subject's project (`WORK_UNKNOWN`, `WORK_KIND_MISMATCH`, `PROJECT_MISMATCH`);
  - it has stopped, it names that stop, and that stop's hold is in force (`RECORD_MISMATCH`, `STOP_NOT_IN_FORCE`).
- **What it records:** the continuation, attributed to the consent. From then on, run and paid admissions in the project are not held by that stop (`MSN-06`). It restarts nothing and renews nothing (`HEB-08.h`).

### The researcher's records

**I7-09. A researcher records an inquiry's disposition, from its own delegated invocation.**
- **The target names:**
  - the invocation and its grant, and the inquiry and its accepted revision, as A-24's delegated types name theirs;
  - the disposition;
  - its grounds: the claim artifacts it rests on, each by path with an expected SHA-256 or `null`, and a reason reference, or `null`;
  - its open questions, each a reference naming the question, the artifact holding its text by path with an expected SHA-256 or `null`, and its next check, its owner or its reason to stop, each a reference or `null`;
  - the consumptions recorded with it, each a claim or a PoC result by path, with an expected SHA-256 or `null`.
- A path is at most 4,096 characters, Linux's `PATH_MAX`, the bound of the hosts AEW contains.

**I7-09.a** WIS admits it only if:
- the invocation is current, of the grant named, and dispatched on that inquiry at that revision (`DELEGATED_GRANT_UNVERIFIED`, `DELEGATION_EXPIRED`, `INVOCATION_NOT_OF_INQUIRY`);
- the inquiry is open at that revision (`REVISION_STALE`, `WORK_CLOSED`). A run dispatched on an earlier revision answers an earlier question (`WISR-01`), and is `REVISION_STALE`, naming the Lead's redispatch;
- the grounds are present: an artifact for `SUPPORTED`, `REFUTED`, `LIMITED` and `UNRESOLVED`, and a reason for `DEFERRED`; and `LIMITED` and `UNRESOLVED` list at least one open question, each with a next check, an owner or a reason to stop (`WISR-02.a`; `GROUNDS_MISSING`, `OPEN_QUESTIONS_MISSING`, each naming what is missing);
- each cited path, a ground's or an open question's, is readable as the researcher could read it, and its bytes match any expected hash (`WISR-03.a`; `PATH_UNREADABLE`, `HASH_MISMATCH`, naming the path and the hash there);
- each consumption resolves as `I7-11`'s end does, within the researcher's view, its inquiry's project (`I7-01`): to one claim or PoC result, at an accepted revision, or under the Lead's held record (`WISR-07`), with its bytes matching. A document is never an end (`CNIL-09`). Otherwise `END_UNRESOLVED`, `END_AMBIGUOUS` or `END_NOT_ACCEPTED`, naming the consumption.

**`STOPPED` is refused here,** naming the researcher's own path (`WISR-02.b`; `STOP_NOT_RESEARCHERS`). It is on the wire so that the refusal can say so.

**I7-09.b** **What it records:** the disposition, attributed to the researcher's run. AEW's host code computes and keeps each cited artifact's hash and bytes (`WISR-03.b`). Each open question is recorded with its next check, its owner or its reason to stop, and its text's artifact, kept as the grounds are, so that it stays attributable and reconstructable, and a later run on the inquiry recovers it (`RX01-04`, `RX01-09`). Each consumption records its end and the end owner's qualification at consumption (`WISR-06`), and reads as held under the inquiry's accepted revision (`CNIL-09.a`).

**I7-10. An author revises a cited claim, or asks for its withdrawal, from its own delegated invocation** (`WISR-03.d`).
- **The target names:** the invocation and its grant, the work it is dispatched on and that work's revision, the inquiry the claim was cited from, the earlier artifact's SHA-256, `REVISE` or `WITHDRAWAL_REQUEST`, and for `REVISE` the new artifact by path with an expected SHA-256 or `null`.
- **WIS admits it only if:**
  - the invocation is current and of the grant named, at that work's revision;
  - the earlier artifact was cited from that inquiry (`CLAIM_UNKNOWN`), by this invocation's lineage, read from ADC (`NOT_AUTHOR`; `LINEAGE_UNAVAILABLE` holds);
  - the new path is readable as for `I7-09.a`.
- **What it records:** the revision link or the withdrawal request. The change reaches every consumer through the reverse listing (`CNI-07.c`). The claim's qualification stays its owner's (`RX01-05`).

### The Lead's records

**I7-11. The Lead records held reliance found mid-work, in one step** (`CNIL-02.b`).
- **The target names:** the work and its current accepted revision; the consumed end's kind, which is a claim or a PoC result by path, a Knowledge item by reference at its content version, or a determination by reference; and the decision's own text, by path, with an expected SHA-256 or `null`.
- **WIS admits it only if:**
  - the actor is the project's current Lead generation, and the work is of the subject's project, another project's resolving as absent (`WORK_UNKNOWN`), and open at that revision (`REVISION_STALE`, `WORK_CLOSED`);
  - the end resolves within the Lead's view, to one subject of the kind named, at an accepted revision, and its bytes match (`CNIL-02.a`; `END_UNRESOLVED`, `END_AMBIGUOUS`, `END_NOT_ACCEPTED`, `HASH_MISMATCH`);
  - the end's standing supports the use (`K01-22`, `WIS-06.b`; `END_NOT_SUPPORTING`; `END_STANDING_UNAVAILABLE` holds);
  - the decision's text is readable as the Lead could read it (`PATH_UNREADABLE`).
- **What it records:** a `consumption` from the work to its end, which reads as held, never as accepted, and routes impact at once (`CNIL-02.b`). It accepts nothing and moves nothing from G3.

**I7-12. The Lead records an unclassified or contested dependency of its own work** (`CNIL-01.b`).
- **The target names:** the dependent work and its accepted revision, the prerequisite work, the class (`UNCLASSIFIED` or `CONTESTED`) and a reason reference.
- **CNI admits it only if:**
  - the actor is the project's current Lead generation;
  - the dependent work is of the subject's project, another project's resolving as absent, as the prerequisite's does (`END_UNRESOLVED`); open at that revision (`REVISION_STALE`, `WORK_CLOSED`); and the Lead's own: not a Ticket HEB has dispatched to another executor, which AEW observes as that executor's (`CNIL-01.b`; `NOT_ASSIGNED`, naming `PROPOSE_IMPACT`);
  - both ends resolve to one subject within the Lead's view (`END_UNRESOLVED`, `END_AMBIGUOUS`).
- **What it records:** the dependency, which holds only the dependent work's restrictive-class effects until an authorized clarification (`CNI-02.d`). It never holds, satisfies or releases anything on the other end. The record says that only a new accepted revision of the dependent work, or the contested class's owner, clears it: neither the Lead nor its recorder lifts it.

**I7-13. The Lead records an advisory proposed impact between two subjects** (`CNIL-05`).
- **The target names** the two subjects, either a proposal at its digest, and the proposer's label as an inert reference, or `null`.
- **CNI admits it only if** both ends resolve to one subject within the Lead's view, and a named digest is that proposal's own content (`END_UNRESOLVED`, `END_AMBIGUOUS`, `HASH_MISMATCH`).
- **What it records:** the proposal, attributed to the Lead. It holds, admits, satisfies, releases and cancels nothing, whatever its label (`CNI-04.c`).

### What rides content, sets, and what the operator sees

**I7-14. What rides accepted content needs no type.**
- **A dependency and an interface commitment** ride the accepted revision's content, which WIS holds by digest, and which the acceptance's `content_sha256` leaf binds. When the acceptance is admitted, Coordination records the `dependency` and `interface_commitment` links from that content (`CNIL-R06`, `CNI-02.a`).
- **A consumption recorded at an acceptance** rides the same content, and reads as accepted only when that acceptance is the accepting authority's (`CNIL-02`).
- **The mission's lists** ride its proposal's content (`I7-07`).

**I7-15. Sets follow the adopted rules, with three added for a mission's consent.**
- **One origin class per set** (`CS-02`): the mission's one consent is all protected (`ACCEPT_MISSION`, the cap's `ISSUE_STANDING_POLICY`, `SET_STEERING_MODE` and, where present, `CONTINUE_AFTER_MISSION_STOP`).
- **One member per subject** (`I6-11`): a set with two members for one mission, one inquiry or one stop is `invalid_request`.
- **A mission's consent binds its members,** read from the members' own leaves, as `I6-11` is, so no owner reads another member. A set carrying `ACCEPT_MISSION` with `ACCEPT` is `invalid_request`, and is not offered for consent, unless:
  - it carries one mission acceptance only;
  - it carries the `ISSUE_STANDING_POLICY` that the acceptance's cap names, with the mission's work as its `resource_scope_ref`. So a mission always issues its cap in its own consent. A later mission issues a new decision, or a successor revision (`I6-03`) of an earlier mission's decision only after that mission's drain's end, so that no draining run's cap is re-scoped under it;
  - every `SET_STEERING_MODE` in it names that mission's work as its `mission_ref`.
- **Each refusal** takes its name in O-01's refusal registry, under the wire categories it already uses.

**I7-16. What the operator sees is G3's consent, unchanged, and each new protected member renders within 30 lines.**
- **No new protected target carries an array or an open object.** Lists ride content by digest (`I7-14`). The researcher's and the Lead's types carry lists of citations and open questions, and G3 renders none of them.
- **The preflight is a read** the operator sees before consenting. The acceptance binds its digest (`I7-07`).

## Interfaces

- **The wire:** `o01-command-0.9-candidate` in `wire/`, generated by `tools/build_o01_wire.py` from A-39's frozen 0.8 (`30-stages/STG-14-I6-resource-model-and-host-policy/adopted/o01-0.8-i6/wire/`), with predecessor pins.
  - 53 actions: 0.8's 42, with two targets amended and erratum E-1's three reasons added, and the 11 new types.
  - `PREDECESSOR-PINS.json` lists the two amended actions and E-1, each with what it changes, its predecessor target's digest and the rule that changes it.
- **Reads.** **Candidate:** in D-01's next revision, with the shared read wire (A-40's, A-41's and A-42's Interfaces). D-01 0.3.4 already names `inquiry`, `research_claim` and `premise_use` among its subject kinds. A mission's read shows "opening", "open", "never opened" or "stopped" (`I7-07.b`).
- **The consent record an admission was made under** (`I7-07.b`): WIS reads it, for its own acceptance and for the issuer's admission of the cap, as an owner-to-owner fact under A-24's owner-set coupling and `CS-06`. O-01's owner-operation read is not that read: it carries `request_set_ref` only. **Candidate:** the owner-to-owner read's wire is D-01's, with the shared read wire above.
- **Refusals:** each type's refusal names, with their wire categories, are in `I7-WIRE-SPEC.json`, and generated into `wire/refusal-reasons-0.9.json`.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **I7-Q01** | Every candidate has a fit (`I7-00`) | each of A-40's six command candidates, A-41's five items, A-42's five items, and W11 to W14, maps to one type or to a named no-type reason |
| **I7-Q02** | Inherited definitions change in four places (`I7-00.a`) | 0.9 carries 0.8's definitions, branches, registry rows and refusal entries byte-equal, except the two amended targets, whose delta is exactly the added kinds and fields, and their added reasons, and erratum E-1's three reasons; `--parity` rebuilds 0.7 byte for byte |
| **I7-Q03** | One owner, owner facts observed, the Lead's view, refusals that name a path (`I7-01`) | each new type has one sole admitting owner; no target has a recorder, decider or acceptance field; every refusal the table lists names its path |
| **I7-Q04** | The operator's stop only reduces (`I7-02`) | it is registered `REDUCING`; an inquiry reads `STOPPED`, attributed to the operator; an open mission's stop holds new runs; an opening mission's stop holds nothing |
| **I7-Q05** | The stop's checks (`I7-02.a`) | a wrong kind or project, a closed work or a non-authority is refused; the operator stops a held inquiry under an in-scope Ticket its acceptance rests on; a new revision, or an unavailable competence source, does not block it |
| **I7-Q06** | The Lead's stop (`I7-03`) | the current Lead stops its project's held inquiry; another project's resolves as absent; an operator-accepted inquiry is refused, naming the protected stop |
| **I7-Q07** | The amended proposal (`I7-04`) | an inquiry and a mission can be proposed, and accepted end to end; an Epic, a Story or a Ticket behaves as in `I5-02` |
| **I7-Q08** | Inquiry and mission proposals (`I7-04.a`) | a parent, a stale asker, a mission with an asker or without its bounds, and a root without the operator's instruction (unless asked) are refused |
| **I7-Q09** | Accepting an inquiry (`I7-05`) | `ACCEPT` records the accepted revision and the request link; `DECLINE` records only that |
| **I7-Q10** | The acceptance's checks (`I7-05.a`) | a leaf differing from WIS's record, a stale asker, or a window's end later than proposed or already past is refused; an earlier one is admitted; an asker named in part is `invalid_request` |
| **I7-Q11** | The held inquiry (`I7-06`) | it needs ADC's in-scope determination; outside it, the refusal names the operator's path; another project's Ticket resolves as absent; it reads as held, never as the operator's |
| **I7-Q12** | Accepting a mission (`I7-07`) | the proposal's leaves equal WIS's record; the generation, the cap and the preflight are the operator's, each checked; the rendering is within 30 lines |
| **I7-Q13** | The mission's checks (`I7-07.a`) | a second open mission, a window beyond 24 hours, a drain before the window's end, a bound later than proposed, a stale generation or a differing preflight digest is refused; so is an acceptance while another mission is opening in a concurrent set |
| **I7-Q14** | The mission opens in one consent, or never (`I7-07.b`) | the attachment identity is observed; the mission opens only when its cap is admitted under its acceptance's consent record, within that set's admission; otherwise it reads never opened, finally, with no hold, and blocks no retry; an identical retry returns the stored receipt; a later cap (even one reusing the request set's reference), an issuance from another consent, or a held cap admitted later under the same record opens nothing; a revoked cap leaves an open mission open, its paid admissions held |
| **I7-Q15** | The one consent needs no order (`I7-07.c`) | in every canonical order, with the mode member first or last: with the acceptance refused, the cap counts nothing and the raise is never in force; with the cap refused, the mission never opens and the raise is never in force; with both admitted, the raise is in force until the stop, then lapses; a continuation in the set stands either way |
| **I7-Q16** | The bound raise (`I7-07.c`) | a bound lowering, an unknown, stopped or never-opened mission, or another project's mission is refused; a raise bound to an already-open mission in a later consent is in force; the mode in force after a stop is the lapse's record, and `RUN` can be raised again; a `null` mission is A-39's raise |
| **I7-Q17** | The continuation (`I7-08`) | it clears only the named stop's hold, restarts nothing, and is refused for a non-mission or when no hold is in force |
| **I7-Q18** | The researcher's disposition (`I7-09`) | it comes from an invocation dispatched on the inquiry at its revision; missing grounds, a `DEFERRED` without a reason, an incomplete open question, an unreadable path, a differing hash, or a consumption of an unresolved (another project's included), ambiguous or unaccepted end is refused, naming it; each open question's text is read and kept; `STOPPED` is refused, naming the researcher's path |
| **I7-Q19** | A claim's revision (`I7-10`) | only the author's lineage revises or asks for withdrawal; the qualification stays its owner's |
| **I7-Q20** | Held reliance (`I7-11`) | it is one Lead command, reads as held, records its end, and an end that is of another kind or project, unresolved, ambiguous, unaccepted, mismatched or not supporting is refused, naming it |
| **I7-Q21** | An own-work dependency (`I7-12`) | it holds only the dependent's restrictive-class effects, and nothing on the other end; a Ticket dispatched to another executor is refused, and another project's work resolves as absent at either end |
| **I7-Q22** | A proposed impact (`I7-13`) | it holds, cancels and satisfies nothing, whatever its label; a digest that is not the named proposal's is refused |
| **I7-Q23** | What rides content (`I7-14`) | no type carries a dependency or an interface commitment of its own |
| **I7-Q24** | Sets (`I7-15`) | a mixed-origin set, a set with two members for one subject, and a mission's consent with two acceptances, without its scoped cap, or with a raise naming another mission or none, are refused before any owner reads |
| **I7-Q25** | What the operator sees (`I7-16`) | no new protected target has an array or an open object; every protected member renders within 30 lines |

## Scenarios

**I7-X01.** Given a Story that asks a research question, the Lead proposes an inquiry naming the Story as its asker, and the operator accepts it through `ACCEPT_INQUIRY`. The request link runs from the Story (`I7-04`, `I7-05`).

**I7-X02.** Given a Ticket whose scope covers fact-finding, the Lead opens a held inquiry under it with no PIN, and stops it later from its own seat (`I7-06`, `I7-03`).

**I7-X03.** Given the operator starting a mission on Friday evening, one consent carries the acceptance, the cap scoped to the mission and `RUN` bound to it. The issuer holds the cap, so the set's admission completes without it. The mission reads "never opened", nothing ran or is held, and `RUN` never came into force. On Saturday a consent of the cap alone, even one reusing Friday's request set reference, opens nothing and brings no `RUN` in. The operator retries with a fresh proposal and a new consent, and is not refused (`I7-07.b`, `I7-07.c`).

**I7-X04.** Given an earlier mission's stop still holding the project's runs, the operator's next mission consent carries the continuation, and one PIN starts the new mission (`I7-07.c`, `I7-08`).

**I7-X05.** Given a research worker that records `REFUTED` citing a claim file outside its own sandbox's view, the disposition is refused as unreadable, naming the path, and nothing is hashed (`I7-09.a`).

**I7-X06.** Given the Lead choosing a library mid-work because of a claim, it records a held consumption in one step; when the claim's author revises it, the Lead's Ticket is listed from the claim at once (`I7-11`, `I7-10`).

**I7-X07.** Given a worker's label "blocking" on a proposed impact, nothing holds (`I7-13`).

**I7-X08.** Given a mission open since Friday under its cap, the operator narrows the cap on Saturday. Paid routes under the mission follow the narrowed cap, and the mission stays open, with its `RUN` in force, until its window ends (`I7-07.b`, `MSN-05`).

## Rulings

**I7-R01. Inquiries and missions get acceptances of their own.** A-40 and A-42 proposed adding their kinds to `DECIDE_WORK_PROPOSAL`. That type already renders at 28 of G3's 30 lines, so the typed asker's three leaves would take it to 31, and break `G3-03`'s bound, which `verify_g3.py` derives. And an inquiry names an asker, not a parent, so reusing the parent leaves would make a request look like a child, which `CNIL-Q02` forbids. Two new protected types keep `DECIDE_WORK_PROPOSAL` unchanged.

**I7-R02. The researcher records from its own delegated invocation.** As built, research runs as a non-mutating Ticket's dispatched executor (`work/AS-BUILT-READ.md`). A-24's `CURRENT_DELEGATED_GRANT` class is a worker's action on its own invocation, as `DELEGATED_CANCEL` is. So a disposition and a claim revision come from the researching run, attributed to it, and the Lead does not stand in for it. Where the Lead researches an inquiry itself, it has no invocation of its own; whether V-01 needs a twin from the Lead's seat stays open (`I7-B1`).

**I7-R03. The one consent's outcome is held by leaves and the consent record, not by order.** `CS-05` evaluates members in canonical order, and `I6-11` already moved I-6 away from outcomes that depend on it. A rule that one owner reads another member of the set would depend on what each owner is handed. So each member names the mission on its own leaf: the cap through the `resource_scope_ref` it already has, a scope `IF10-02` admits, and the mode through one added field. The outcome is then decided by owner facts the adopted text already records: the G3 consent record each member was admitted under, and the set digest each owner admission binds (`I7-07.b`). The operator sees the binding on both members.
- **This is outside `MSN-04`'s two named options,** A-24's set rule or `I6-06.a`'s admission conditions. It is a leaf, an admission condition on `I6-06.a`, a force condition on `I6-06.g`, and a raising path on `I6-06.f` limited to the raise's own consent. A raise bound to a mission already open needs no such path: it is in force from its admission, as an unbound raise is, and only lapses earlier. The departure table says so, and the operator's adoption covers it.
- **A reading of `MSN-04.a`:** it says the mode's target is unchanged, for the lapse at a stop. This profile reads that as governing the lapse only, as `MSN-R05` ties it, since `MSN-04` left the mechanism of the one consent to I-7.

**I7-R04. Dependencies and bindings ride accepted content.** A-41 allowed either a command or the accepted content. The content is already bound by `content_sha256` in the acceptance the operator sees, and Coordination records the links when it is admitted. A command of their own would add a second path to the same fact.

**I7-R05. The agents' records are one step each, and protect nothing.** The Lead's held reliance, own-work dependency and proposed impact, and the researcher's disposition and claim revision, each take one command. None accepts, holds another's work or moves a decision from G3 (`CNIL-R08`, `CNIL-R09`, `WISR-08`).

**I7-R06. Ten new types have no catalogue row, and their rows are the operator's.** A-32's 86 rows are the operator's adopted scope. Ten new types serve candidates the adopted positions named, but no row: the two stops, the held inquiry, the mission's acceptance, the continuation, and the five agents' records. Their registry rows carry an empty catalogue list, and `tools/classify_actions.py` regenerates A-32 unchanged by them. At adoption the operator either adds the rows, or leaves the types unrowed. Minting rows here would change the operator's scope index without the operator.

**I7-R07. The operator's stop names no revision, and the operator may accept what a Ticket's scope covers.** Two walls are left out, as the reset asks. A stop naming a revision would be refused when the inquiry's question had been revised since the consent, though the operator still wants it stopped (`AOI-07.f`). And refusing the operator's acceptance of an inquiry a Ticket's scope covers would refuse an approval the operator has already given. That acceptance makes the inquiry the operator's, with the operator's stop.

**I7-R08. A mission that never opened leaves nothing behind.** `MSN-04` says that if the acceptance or the cap fails, nothing of the set is in force for the mission. A mission whose openness was read from its cap at any later time would come into force through a later consent that renders neither its acceptance nor its raise, and a stuck one would block the retry and hold the project's runs. So the outcome is decided within the admission of the one set the operator consented to, keyed on G3's consent record, never on a reference the client chooses, and it is final: a mission that did not open reads "never opened", with no stop, no hold and no lapse, and nothing admitted later opens it. A mission is opening only during its own set's admission, so no later acceptance needs to supersede one; one in a concurrent set is refused, naming it (`MSN-01.b`).

**I7-R09. The Lead's dependency is on its own work only.** `CNIL-01.b` gives the record to "an agent that AEW observes assigned to the dependent work". A Ticket HEB has dispatched to another executor is that executor's, observed through its dispatch, so the Lead's record there is refused, naming the advisory `PROPOSE_IMPACT`. The Lead's own work is what has no dispatch to another executor. A worker's own-work dependency waits for `I7-B2`.

## Backlog

**I7-B1.** A disposition and a claim revision from the Lead's seat, where the Lead researches an inquiry itself (`I7-R02`).

**I7-B2.** A worker's own-work dependency and a worker's proposed impact, from the worker's delegated invocation (`CNIL-01.b` and `CNIL-05` allow both; V-01 gives them to the Lead, on its own work, `I7-R09`).

**I7-B3.** A researcher's held reliance mid-work, apart from the disposition (`CNIL-02.b`; V-01 records it with the disposition, `I7-09`).

## Not covered

- **The host settings layer for check commands** (`K-DEC-04`): its own pass, beside I-7.
- **W12 and W14:** K-01's own increment, after V-01.
- **D-01's reads:** the shared read wire, matched with the wire track.
- **The relay's meter and the class's qualification:** the build's, under A-42's option (a).
- **Cross-project links:** `CNIL-B1`, after the sharing groups.
- **The build:** the Lead's, after adoption. Protected types stay held wherever G3 is not established.

## Changes

- Revision 1 (2026-10-25): the first text.
- Revision 2 (2026-10-25): answers round 1's eighteen findings (`CHANGES-r2.md`). The mission opens in one consent or never (`I7-07.b`, `I7-R08`); the proposal carries a mission's bounds (`I7-04`); the bound raise's force follows request sets, and the mode in force is R-01's record (`I7-07.c`); the researcher's consumptions resolve their ends (`I7-09.a`); the Lead's records are bound to its project (`I7-01`); a refusal table (`I7-01`); three set rules for a mission's consent (`I7-15`); the departure table states the mode binding's extent. Revision 1's fourth backlog item, the cap's scope, is closed by `IF10-02`.
- Revision 3 (2026-10-25): answers the quick check's reopened finding and its four new ones (`CHANGES-r3.md`). The mission's opening is keyed on G3's consent record and decided within its set's admission, and "never opened" is final; an identical retry is a lookup (`I7-07.b`, `I7-R08`); another project's work resolves as absent for the Lead and the researcher (`I7-01`); each open question's text is read and kept (`I7-09`); a successor cap revision waits for the earlier drain (`I7-15`); a revoked cap holds the open mission's paid admissions (`I7-07.b`). Then, before the adoption proposal and not reviewed: erratum E-1, the operator's decision on the as-built trace's flag on HEB's interim refusal codes, in `CONTINUE_ELIGIBLE_WORK`'s reason map (`I7-00.a`).
