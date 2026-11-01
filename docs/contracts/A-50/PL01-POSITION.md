<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-50
source: 30-stages/STG-25-PoC-request-link-carrier/adopted/pl01-r3/PL01-POSITION.md
source-sha256: 6180835b42ef0c5c8109dedfbc7c7b64c48322a6cbe9a0110a00081e17a395b0
edits-sha256: none
-->

# PL01: the PoC request link's carrier (PROPOSED, revision 3)

**Namespace:** `PL01-`
**Status:** proposed.
- **What it answers:** A-48's row 3, finding F8, from V-01's first review round. At O-01 0.9 a Ticket proposal names no asker, so an inquiry cannot ask for a PoC Ticket, and `WISR-Q11` cannot pass.
- **How it amends:** by addition, as A-46 extended A-45's `O02-07.a`. Adopted copies keep their bytes, and no O-01 byte moves.
  - It extends A-43's `I7-04.a` and its gate row `I7-Q07` (`PL01-01`).
  - It adds the request link to the record change of A-29's three acceptance paths, `I5-03`'s decision, `I5-03`'s in-scope acceptance and `I5-04`'s `REPLACE` (`PL01-02`).
  - It adds the close to the record change of every adopted rule that moves an asker: `I5-03`, `I5-04`, `I7-02`, `I7-03`, `I7-05`, `I7-09` and `WISR-02.b`'s stop at a window's or a holding scope's end (`PL01-03`).

**Authority:** the operator's decision that STG-25 goes ahead (`00-governance/decisions/2026-11-01-operator-start-STG-25-PoC-request-link.md`), under A-48 (`00-governance/decisions/2026-11-01-operator-adoption-V01-matrix-r4.md`).
**Threat model:** the operator's G3 threat model (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`), under the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`).
**Research consulted:** none. `tools/research_index.py lookup` returned no hits for `I7-04.a`, `WISR-05`, `CNIL-R07` or `I5-03`.
**Files:** this file, and the gate in two files:
- `verify_pl01.py`, derived from A-43's `verify_i7.py` (SHA-256 `2ad4a4a9172b74ad7102c20d1a74867e56f9d7f7c773466ab9c98ab989a1d586`), with its changes listed in its header;
- `pl01-cases.json`, the gate's snapshot.

The gate passes 994 checks, A-43's included. `python -I -B verify_pl01.py --mutate` kills all 143 mutants: A-43's, the new owner checks, and the seven PL01 rules, each of which must fail on a PL01 row.

## What the adopted text already decides

- **The request link** (A-40's `WISR-04`, `WISR-05`): a link runs from the asking work to the requested work, including an inquiry asking a Ticket for a PoC in the real project. It is recorded with the requested work's acceptance or opening, as part of its provenance, and names the asking work and that work's accepted revision. A PoC Ticket an inquiry requests is engineering work, accepted and reviewed as any Ticket is.
- **A link conveys nothing** (`WISR-04.a`): no authority, parentage, obligation, evidence or lifecycle coupling. A request never makes a child (`CNIL-Q02`).
- **A held inquiry's revision:** an inquiry held under a Ticket's scope has no accepted revision of its own. For links, its revision is the Lead's record under the Ticket's accepted revision, which counts as accepted for links, and reads as held (A-40).
- **What a `request` may ask** (A-41's `CNIL-R07`): a question of research, or a PoC. The requested work is an inquiry, or a PoC Ticket an inquiry asks for.
- **Waits that cycle through a request** (`CNIL-Q15`): a Ticket waiting on an inquiry that asks for a PoC Ticket depending on the first Ticket is detected, and gets `CNI-03.h`'s accountable disposition.
- **The proposal wire** (A-43's `I7-04`): `CREATE_PROPOSED_WORK`'s `asked_by` names the asking work (an Epic, a Story, a Ticket or an inquiry), its reference and accepted revision, or `null`. The 0.9 schema makes it required and nullable for every `work_kind`, with no condition on the kind.
- **The limit** (`I7-04.a`): "An Epic, a Story or a Ticket names none of the three new fields (`PROPOSAL_SHAPE_INVALID`), and its origins stay `I5-02`'s." So no Ticket can carry an asker. This is the gap.
- **The three paths that accept a Ticket proposal** (A-29):
  - `I5-03`'s decision: the operator's `DECIDE_WORK_PROPOSAL` accepts or declines one exact proposal, every compared leaf as WIS recorded it (`RECORD_MISMATCH`). A closed or superseded proposal is `PROPOSAL_CLOSED`. Its refusal map has no `ASKER_NOT_CURRENT`;
  - `I5-03`'s in-scope acceptance: WIS accepts a child proposal without the decision only on ADC's current in-scope determination for exactly that proposal. Never a root, a revision, an intake, or a declined or closed proposal;
  - `I5-04`'s `REPLACE`: with the operator's consent, an open new-identity Ticket proposal is accepted as an accepted Ticket's successor, landing where the Ticket was. A closed proposal is `PROPOSAL_CLOSED`.
- **A proposal cannot be edited** (`I5-02`, `X9`): the Lead replaces one only by superseding it, which closes it.

## The parts

- **The Lead** proposes the PoC Ticket by `CREATE_PROPOSED_WORK`, naming the asking inquiry.
- **WIS** admits the proposal and records it. When the Ticket is accepted, on any of the three paths, it records the Ticket with its request link. When the asker moves first, it closes the proposal. It alone writes these records.
- **What accepts the Ticket** is what accepts any Ticket: the operator's `DECIDE_WORK_PROPOSAL` under G3, ADC's in-scope determination for a child within its parent's accepted scope, or the operator's `REPLACE` under G3.
- **The asking inquiry** is research work. The request changes nothing about it, and the PoC's result returns to it by its consumption (`WISR-06`).

## Rules

**PL01-00. Precondition: A-43's `I7-02`, `I7-03`, `I7-04`, `I7-04.a`, `I7-05`, `I7-06` and `I7-09`, A-29's `I5-02`, `I5-03` and `I5-04`, and A-40's `WISR-02.b`, hold as adopted, except where a rule here adds to them.** Nothing here narrows them.

**PL01-01. A new Ticket proposal may name an inquiry as its asker: a PoC request.** This extends `I7-04.a` by one case (`CNIL-R07`).
- **The asker:** an inquiry of the subject's project, at the revision the proposal names (`ASKER_NOT_CURRENT`, as `I7-04.a` already requires).
- **The asker is open:** accepted, or held under a Ticket's scope at its held revision. A completed, stopped or unknown inquiry is `ASKER_NOT_CURRENT`.
- **A new Ticket only:** a PoC request is a new-identity Ticket proposal, a child or a root. A proposal that revises a Ticket and names an asker is `PROPOSAL_SHAPE_INVALID`. So a request never turns an existing Ticket into a PoC Ticket, or gives a PoC Ticket a second link; an engineering change asked of an existing Ticket stays a scope change (`CNIL-R07`).
- **Nothing else gains an asker:** an Epic, a Story, or a Ticket asked by anything other than an inquiry still names none of the three new fields (`PROPOSAL_SHAPE_INVALID`). A PoC Ticket names no window's or drain's end.
- **Its origins stay `I5-02`'s:** a PoC Ticket has an ordinary parent, or the operator's instruction, as any Ticket. The request is never its origin or its parent (`CNIL-Q02`).
- **What WIS records with the proposal:** the asker and the revision named; and for a held asker, that it is held, with its holding Ticket and that Ticket's accepted revision at the proposal.

**PL01-02. WIS records the request link with the Ticket's acceptance, on whichever path accepts it.** The paths are the three A-29 has: `DECIDE_WORK_PROPOSAL`'s `ACCEPT`; an in-scope acceptance under ADC's determination; and a `REPLACE` that accepts the proposal as its successor. On each, WIS records as the Ticket's provenance (`WISR-05`):
- the asking inquiry, and the revision the proposal named;
- whether the asker was held. A held asker's link reads as held, never as accepted (A-40, `PL01-R04`);
- **the proposer's attribution:** the link is the Lead's provenance, kept apart from what accepted the Ticket, as `I5-02` keeps the proposer apart from the instruction. No reader takes the link as something the operator or ADC decided.

**What binds it:** WIS takes the link from its own record of the proposal that `proposal_ref` names. The Lead cannot edit that record; superseding it closes the proposal (`X9`). So the acceptance always covers the asker the proposal was made with. `RECORD_MISMATCH` compares the decided leaves, and the asker is not one of them (`PL01-R02`).
- A declined proposal records no Ticket and no link; it reads as declined (`I5-03`).
- A proposal closed by `PL01-03` is accepted on no path, and records nothing.
- A Ticket proposed with no asker is accepted with no link, as now.
- **Candidate:** a field named `requested_by` on the accepted Ticket's record, holding the asking work's reference, the revision named, whether it reads as held (with the holding Ticket and revision), and the proposer. `WISR-05` asks for the first two. A-43's model records only the reference on an accepted inquiry; that is A-43's model, not its rule, and this position does not change it.

**PL01-03. When its asker moves, WIS closes the PoC proposal at once, and records why.** This is WIS's owner rule on any record change that moves an asking inquiry: in that same change, WIS closes each open PoC proposal the inquiry asks, as `I5-03` closes a superseded proposal at the event. The proposal's state becomes `CLOSED_ASKER_MOVED`, with the cause and the asker's current revision. The causes, and the adopted rules whose record changes make them:
- `REVISED`: the asker gets a new accepted revision (`I7-05`);
- `COMPLETED`: its disposition completes it (`I7-09`);
- `STOPPED`: the operator stops it (`I7-02`), the Lead stops a held one (`I7-03`), or host code stops it at its window's end or its holding scope's end (`WISR-02.b`, including a holding Ticket's `I5-04` cancel or replace);
- **for a held asker,** `HOLDER_REVISED`: the Ticket holding it gets a new accepted revision (`I5-03`), since the held revision is the Lead's record under that Ticket's accepted revision;
- **for a held asker,** `TAKEN_ON`: the operator takes it on (`I7-05`, `I7-R07`), so that it no longer reads as held;
- `UNKNOWN`: the asker no longer resolves. No adopted rule removes an inquiry, so this cause only keeps the read total.

**The order within one change:** admission reads the state before the change. A proposal the change itself accepts is not open, so the close does not reach it. So when the operator's `REPLACE` of the Ticket holding the asker takes the PoC proposal as its successor, the successor is accepted, its link reads as held under the replaced Ticket's last accepted revision, and the asker's stop then follows as `WISR-02.b`'s (`PL01-X04`). Refusing that successor (`SUCCESSOR_INVALID`) would spend the operator's consent on a refusal, for a link that conveys nothing (`WISR-04.a`).

The closed proposal is readable, with its cause, before any consent, so the Lead can propose again from the inquiry's current revision before the operator spends one. Every path then refuses it, as each already refuses a closed proposal: the decision and `REPLACE` with `PROPOSAL_CLOSED`, the in-scope acceptance by its "never a closed proposal". So a PoC asked for by a question that has since changed is never accepted on the old question, on any path.

**PL01-04. The link conveys nothing.** The accepted Ticket's parent is its proposal's, and the asking inquiry is unchanged by the acceptance (`WISR-04.a`). The PoC's result returns to the inquiry by the inquiry's consumption, and stays provisional (`WISR-06`). A wait that cycles through the request is found by `CNIL-Q15`. The close in `PL01-03` is not a lifecycle coupling: no link exists before the acceptance.

**PL01-05. The adopted rules PL01 adds to are read with `PL01-01` to `PL01-04`.** They are `I7-04.a` and `I7-Q07`; `I5-03` and `I5-04`, for the link and the close; and `I7-02`, `I7-03`, `I7-05`, `I7-09` and `WISR-02.b`, for the close. A built WIS conforms to each with PL01 together, as A-46 extended A-45's `O02-07.a`.

## Interfaces

- **No O-01 schema byte changes.**
  - `CREATE_PROPOSED_WORK`'s `asked_by` already admits an inquiry for every `work_kind`. Refusing an asker on an Epic, a Story or a revision is WIS's owner rule, not the schema's.
  - `DECIDE_WORK_PROPOSAL`'s and `CANCEL_OR_REPLACE_TICKET`'s targets are unchanged, with no asker leaf (`PL01-R02`).
  - Every refusal PL01 uses is already mapped: `ASKER_NOT_CURRENT` and `PROPOSAL_SHAPE_INVALID` for `CREATE_PROPOSED_WORK`, and `PROPOSAL_CLOSED` for `DECIDE_WORK_PROPOSAL` and `CANCEL_OR_REPLACE_TICKET`.
- **The wire version:** A-43's adoption record has no clause requiring a new pinned wire version for a change, unlike A-31's. So no route question arises: adoption is by hash.
- **The link and the close are WIS's records,** as `WISR-05` says of the link. **Candidate (D-01):** the proposal's read shows its `asked_by`, and a closed PoC proposal's cause. This is a read, not a wire change.

## The gate

`verify_pl01.py` derives from A-43's `verify_i7.py`. Its header states the source hash and lists every change. It reads A-43's wire, wire spec and profile from A-43's frozen copy. The PL01 cases run first. `--mutate` disables each PL01 rule in turn, and requires it to fail on a PL01 check.

**A labelled model of A-29's three acceptance paths:** A-43's model has none. The gate adds them only as far as PL01 needs them:
- `DECIDE_WORK_PROPOSAL`: the proposal is known and open, the record matches, and `ACCEPT` records the Ticket;
- the in-scope acceptance, as an owner-to-owner step: the proposal is open, a child, and ADC's determination names exactly it;
- `REPLACE`: the Ticket is open at its revision, the successor proposal is open, its digest matches, and it lands where the Ticket was.

Competence, `CANCEL`, and A-29's other checks are not re-modelled. The model makes `PL01-03`'s move and close one WIS step: a case applies the move, then WIS's close.

| Check | What it shows | Pass |
|---|---|---|
| **PL01-Q01** | An accepted inquiry, and an inquiry held under a Ticket's scope at its held revision, each ask for a PoC Ticket with an ordinary parent (`PL01-01`). | admitted; WIS records the asker, the parent and, for the held asker, its holding Ticket and revision |
| **PL01-Q02** | A Ticket asked by a Ticket; a Ticket asked by a Story; a Story asked by an inquiry; an Epic asked by an inquiry; a PoC Ticket with a window; a revision of a Ticket asked by an inquiry (`PL01-01`, `I7-04.a`). | each `PROPOSAL_SHAPE_INVALID` |
| **PL01-Q03** | An asking inquiry at a stale revision, completed, stopped, of another project, or unknown (`PL01-01`). | each `ASKER_NOT_CURRENT` |
| **PL01-Q04** | After another work moves, the operator accepts a PoC Ticket asked by an accepted inquiry, and one asked by a held inquiry; WIS accepts a PoC Ticket in scope; the operator replaces a Ticket with a PoC Ticket; the operator replaces the Ticket holding the asker with that PoC Ticket, and the asker's stop follows; the operator declines one; the operator accepts an ordinary Ticket asked by no one (`PL01-02`). | the two decided proposals stayed open after the other work moved; every accepted PoC Ticket records the inquiry, its revision and the proposer, and the held ones read as held, the replaced holder's under its last revision; a decline records no Ticket and no link; the ordinary Ticket has no link |
| **PL01-Q05** | After the proposal, the asking inquiry is revised, completes or is stopped; a held asker is stopped; the Ticket holding the asker gets a new accepted revision; the operator takes a held asker on (`PL01-03`). | each proposal is `CLOSED_ASKER_MOVED` at once, with its cause, before any consent; its acceptance is `PROPOSAL_CLOSED`, with nothing accepted; and a closed proposal is accepted neither in scope nor as a successor |
| **PL01-Q06** | The labelled model's own checks: an unknown proposal, a leaf or a parent differing from WIS's record, a proposal already decided; an in-scope acceptance with no determination, with one for another digest, with one at a stale parent revision, and of a root proposal (`I5-03`). | `PROPOSAL_UNKNOWN`, `RECORD_MISMATCH`, `PROPOSAL_CLOSED`, nothing accepted |
| **PL01-Q07** | No wire byte moves: `asked_by` is required, nullable and unconditioned, and admits an inquiry; `DECIDE_WORK_PROPOSAL` and `CANCEL_OR_REPLACE_TICKET` name no asker; every refusal used is mapped, and neither maps `ASKER_NOT_CURRENT`. | as stated, read from A-43's frozen schema and refusal map |
| **PL01-Q08** | The link conveys nothing (`PL01-04`). | the Ticket's parent is its proposal's; the asking inquiry is unchanged; the link's attribution is the proposer's, apart from what accepted the Ticket |
| **PL01-Q09** | A-43's fixtures are A-43's. A-43's frozen `SHA256SUMS` is the header's, and every file it lists has its bytes; the script, snapshot, wire spec and profile are the ones A-43's record pins. The definitions that differ, decorators included, are exactly `Model.create_proposed_work`, `mutants` and `main`, with none removed, and every added one is PL01's. The top-level statements compare both ways: the A-43 ones that differ are exactly the three paths, and the added ones bind only PL01's names. Every A-43 case runs, in A-43's order, with as many checks as A-43's frozen script makes. Every outcome in A-43's `i7-cases.json` is recorded again, unchanged. | exact match |

**The A-43 row amended by addition:** `I7-Q07`'s "an Epic, a Story or a Ticket behaves as in `I5-02`" now reads with "except that a new Ticket may be a PoC request (`PL01-Q01` to `PL01-Q05`)".

## Scenarios

**PL01-X01.** The accepted inquiry `inq:op` asks whether parser 2 handles CRLF, and wants a PoC in the real project. The Lead proposes a PoC Ticket under Story `story:s1`, asked by `inq:op` at its accepted revision. The operator accepts it under G3. WIS records the Ticket with its request link: `inq:op` at that revision, the Lead's provenance. The PoC runs as any Ticket does, and `inq:op` consumes its result as provisional evidence (`WISR-Q11`, A-48's row 3).

**PL01-X02.** The same, but the operator revises `inq:op`'s question before deciding. WIS closes the PoC proposal in the same change, recording that `inq:op` was revised and its new revision. The Lead's read shows this before the operator spends a consent, and the Lead proposes again from `inq:op`'s new revision.

**PL01-X03.** The same as X01, but the PoC is ordinary decomposition within `story:s1`'s accepted scope, and ADC issues its in-scope determination for exactly the proposal. WIS accepts the Ticket in scope, and records the same request link.

**PL01-X04.** The held inquiry `inq:held`, held under `ticket:t1`, asks for a PoC Ticket under `t1`'s parent. The operator replaces `t1` with that PoC Ticket as its successor. The replacement is admitted on the state before it: the PoC Ticket is accepted, with its link reading as held under `t1`'s last accepted revision. `t1`'s scope has ended, so `inq:held` is then stopped (`WISR-02.b`), and its stop closes nothing, since the proposal is already accepted.

## Rulings

**PL01-R01. No `I7-14` line.** `I7-14` lists what rides accepted content. The request link rides the proposal's `asked_by`, and WIS records it on acceptance from its own record of the proposal, which the Lead cannot edit (`PL01-02`). So accepted content needs no new item.

**PL01-R02. The asker is not a G3 leaf.**
- `I5-03`'s leaves are the facts the operator decides on. `WISR-04.a` says a request conveys nothing, so the asker is provenance, not a decided fact. `PL01-02` records it with the proposer's attribution for that reason.
- The operator sees it through the proposal's read, a D-01 candidate (Interfaces), not through the decision.
- `DECIDE_WORK_PROPOSAL`'s render budget is untouched: 28 of 30 lines. A typed asker's three leaves would take it to 31 and break `G3-03`'s bound, which is why A-43 gave inquiries their own acceptance (`I7-R01`).
- A leaf would also be a wire change, which this position avoids.

**PL01-R03. A moved asker closes the proposal; it is not a new refusal.**
- At an inquiry's acceptance, `I7-05.a` re-checks the asker. Mirroring that on a Ticket's acceptance would add `ASKER_NOT_CURRENT` to `DECIDE_WORK_PROPOSAL`'s refusal map, and to `CANCEL_OR_REPLACE_TICKET`'s: a wire change.
- `PROPOSAL_CLOSED` is already mapped, to `PRECONDITION_STALE`, and tells the Lead the same thing: propose again.
- **Eager, with its cause** (revision 2): the close happens when the asker moves, not at the decision. A lazy close would let the operator spend a consent on a dead proposal, and get a refusal that looks the same as "already decided". The friction is a security cost under the reset.

**PL01-R04. A held inquiry may ask, and its link reads as held.** A-40 gives a held inquiry a revision for links, the Lead's record under the Ticket's accepted revision. So a held inquiry asks with that revision, and the link records that it reads as held. Since the held revision rests on the holding Ticket's accepted revision, a new accepted revision of that Ticket moves it (`PL01-03`). A-40 leaves this open; this ruling settles it for PoC proposals only, and `PL01-B2` takes it to A-40's owner for every link kind.

**PL01-R05. Every acceptance path records the link; none is closed to a PoC Ticket.** The alternative was a WIS owner rule that a proposal naming an asker is never accepted in scope or as a successor. That costs no wire byte, but it would make every PoC Ticket take the operator's consent, even ordinary decomposition within an accepted scope. That is the friction the reset counts as a cost, so it is rejected.

## Backlog

**PL01-B1.** If the operator wants the asking inquiry shown in the decision itself, that is a `DECIDE_WORK_PROPOSAL` leaf and a wire change. It is not needed for `WISR-Q11` (`PL01-R02`).

**PL01-B2.** Whether a holding Ticket's new accepted revision moves a held inquiry's revision for links is A-40's fact (`WISR-07`). `PL01-R04` rules it for a PoC proposal's asker only. A-40's owner rules it once for every link kind, including a consumption that reads as held (`I7-09.b`, `CNIL-09.a`) and held reliance (`I7-11`), so that one held revision never reads two ways.

## Not covered

- **The PoC's execution and its result's consumption:** `WISR-06`, A-43's `I7-09` to `I7-13`.
- **The three acceptance paths' competence and their other checks, and `CANCEL`:** A-29's, unchanged and not re-modelled.
- **ADC's issuance of an in-scope determination** (I-3): what it assesses is ADC's. A proposal that names an asker is assessed as any child proposal is.
- **The cycle's disposition:** `CNIL-Q15`, `CNI-03.h`.
- **A-48's other three items that block the outcome by design.**

## Changes

- **Revision 1 (2026-11-01):** the first text, after the advisor check on STG-25's direction (`STAGE.md`).
- **Revision 2 (2026-11-01):** round 1's seven findings, mapped in `CHANGES-r2.md`:
  - the link is recorded on all three acceptance paths, and the model has the in-scope acceptance and `REPLACE`;
  - `PL01-Q09` pins A-43's whole snapshot;
  - a held asker's link reads as held, and the holding Ticket's new revision moves it;
  - the close is eager, with its cause;
  - a revision may not name an asker;
  - the binding is `proposal_ref` and the proposal's immutability, and the link carries the proposer's attribution;
  - Q04's pass cell;
  - new ruling `PL01-R05`.
- **Revision 3 (2026-11-01):** the quick check's five non-blocking items, mapped in `CHANGES-r3.md`:
  - "How it amends", `PL01-00` and `PL01-05` name every adopted rule the link and the close add to, and `PL01-03` states the close once as WIS's owner rule;
  - `PL01-03` states the order within one change, with scenario `PL01-X04` and a `PL01-Q04` row;
  - backlog line `PL01-B2`;
  - `PL01-Q06` tests each in-scope guard;
  - `PL01-03` names the closed state and its causes.
