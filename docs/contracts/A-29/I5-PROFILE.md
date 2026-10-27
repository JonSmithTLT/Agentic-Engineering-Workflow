<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-29
source: 30-stages/STG-07-I5-work-and-scope-decisions/adopted/o01-0.4-i5/I5-PROFILE.md
source-sha256: ce8817316924c6b5413a6604fd7264c3a6a2735716f6a7d09f9a890d3edf9801
edits-sha256: none
-->

# I-5: WIS and CNI work and scope decisions, selection profile (PROPOSED contract pass, revision 2.1, 2026-10-21)

**Wire:** O-01 `o01-command-0.4-candidate`, in `wire/`. It is A-28's 0.3 wire plus five action types, generated from A-28's frozen bytes by `tools/build_i5_wire.py`.
**Stage:** `STAGE.md`. **Start:** `00-governance/decisions/2026-10-21-operator-start-I-5.md`.
**How to read it:** as I-1's profile. Each rule states an outcome: what must hold, who owns it, what is refused, and the adopted rule it must not contradict. Text marked **Candidate** is a starting point for the build, which may meet the outcome another way.
**Rule names.** `WIS-01.a` and the like are A-08's guarantees. A-27's issuer rules are written `A-27 WIS-11`, so the two families never collide.
**Revision 2.1** answers the short check of revision 2 (`reviews/2026-10-21-I5-check-r2.md`, `Check: FINDINGS at c5caacf`; nothing blocked). It changes three things:
- a root ticket can be replaced (I5-04);
- intake attribution is authenticated (I5-03);
- the I5-08a hold is reported as an owner hold.
`CHANGES-r21.md` maps them.
**Revision 2** answers review round 1 (`reviews/2026-10-21-I5-review-round-1.md`, `Review: FINDINGS at 01bfa06`; nothing blocked). `CHANGES-r2.md` maps each finding to its answer.
**Revision 1.1** was the designer's own correction before review:
- in-scope acceptance covers new children only (ADC-03.b). WIS-02.d's no-ceremony path for a harmless edit is AEV-01.g's, and it relieves the reassessment, not the acceptance (I5-03);
- the consequence fact comes only from the sole admitting owner, so W04 has none until CNI has a D-01 read (I5-08);
- the protection direction is stated (I5-00);
- the seat rule (I5-12) and the owner-enum change (I5-00) are stated as new rules;
- L10's removal rests on the catalogue text (I5-07).

## I5-00. The fit: which rows need a new O-01 type

The classification's caveat sets this step first: a row may fit an existing type, belong to an owner's own interface, or need a new type. This is that check for all nine rows.

| Row | Catalogue symbol | Kind letters | Fit | Reason |
|---|---|---|---|---|
| L10 | `INIT_OR_REGISTER_PROJECT` | F/Q | **No O-01 command** (I5-07) | Its owner text: "WIS/installation owners; exact accepted project subject distinct from host attachment/Lead grant". That makes it an installation owner's act, made at the console the way root anchors a WIS store (A-27 WIS-11), plus the functional `aew init`. The kind letters (no `O`) agree, but they are the designer's reading, not adopted text. |
| W15 | `CREATE_PROPOSED_WORK` | F/D/Q | **New type `CREATE_PROPOSED_WORK`**, delegated (I5-02) | A Lead records a proposal. No existing type records WIS facts. |
| W16 | `ACCEPT_WORK_SCOPE` | O/Q | **New shared type `DECIDE_WORK_PROPOSAL`**, protected (I5-03) | All four rows are one decision: accept or decline one exact WIS proposal. The proposal's own facts tell them apart (a new child, a revision, a root objective, an intake), and the operator sees those facts as leaves. A-25 already serves `CLOSE_ATTACHMENT` → L04, C02, C05 the same way. |
| W02 | `APPROVE_PLAN_OR_SCOPE_CHANGE` | O/Q | the same | |
| W01 | `ACCEPT_PROJECT_OBJECTIVE` | O/Q | the same | |
| W17 | `RESPOND_WORK_INTAKE` | O/D/Q | the same, for its O part. Its D part needs no command (I5-03, "In-scope acceptance") | |
| W03 | `CANCEL_OR_REPLACE_TICKET` | O/D | **New type `CANCEL_OR_REPLACE_TICKET`**, protected (I5-04) | It ends an accepted identity, or replaces it. A decision on a proposal cannot do that. |
| W05 | `ANSWER_DECISION_NEED` | O/Q | **New type `ANSWER_DECISION_NEED`**, protected (I5-05) | It answers an owner-issued need, and creates no work fact of its own. |
| W04 | `APPROVE_INTERFACE_CHANGE` | O/Q | **New type `APPROVE_INTERFACE_CHANGE`**, protected, owner CNI (I5-06) | An interface commitment is CNI's subject (CNI-02.b), not a work revision. |

**What this changes in the classification** (corrected there, in its own note, and not restated here):
- **49 actions need a command,** not 50: L10 does not.
- **I-5 adds five types for eight rows.**
- The classification stays proposed.

**Everything in A-28 is inherited unchanged:**
- its sixteen action types, their targets and registry rows;
- CS-01 to CS-09, the receipt, the owner-operation GET and the reason codes.

**I5-00a. The one change to inherited definitions: the closed owner enums gain `WIS` and `CNI`.**
- **Where:** `Intent.owner_hint`, `IntentResult.owner`, the receipt's result `owner` and OpenAPI's `OwnerOperationRead.owner`.
- **Why:** without it, no WIS or CNI result could be reported. D-01 already names both as governing owners (`SourceStamp`).
- **This departs from "carried unchanged"** (I1-00's wording for 0.3). It is additive: every 0.3 value keeps its meaning.
- **A 0.3 consumer never meets the new values.** Under rule 2's exact version marker, only a 0.4 endpoint emits them, and a 0.3 endpoint refuses a 0.4 body.

**The protection direction is set per type.** A type that can act in both directions takes the one that gates harder:
- `CANCEL_OR_REPLACE_TICKET` can accept a successor;
- the two decision types can accept.

So all five are `PRESERVING_OR_INCREASING`. A decline or a plain cancel only reduces, but it travels in the same type.

**The version is an exact successor,** under A-25's rule 2, as I1-00 sets for 0.3:
- a 0.4 endpoint refuses a 0.3 or 0.2 header or body;
- 0.3 may still be hosted separately;
- version support activates nothing.

## I5-01. Who owns what

| Type | Records the fact (sole admitting owner) | Whose decision the origin carries | Read only, as an input |
|---|---|---|---|
| `CREATE_PROPOSED_WORK` | **WIS:** the proposal, its stable work ID and its proposed revision | the Lead's. A proposal is not a decision (ADC-01.d) | HEB: the principal is the current Lead of the subject seat. WIS: the parent's or predecessor's accepted revision |
| `DECIDE_WORK_PROPOSAL` | **WIS:** the accepted revision, or the decline | the operator's, as ADC's competent authority for the boundary, or an external authority's decision that ADC qualifies (ADC-01.a, ADC-01.b) | ADC: the competence fact, and any external decision |
| `CANCEL_OR_REPLACE_TICKET` | **WIS:** the ticket's cancellation, or its replacement and lineage | the same | ADC: competence |
| `ANSWER_DECISION_NEED` | **WIS:** the need's answer. WIS issued the need | the same | ADC: competence |
| `APPROVE_INTERFACE_CHANGE` | **CNI:** the accepted interface commitment, and which consumer bindings it leaves needing reconciliation | the same | ADC: competence. WIS: the accepted revision of the work the interface belongs to |

**Why WIS records an acceptance, not ADC** (this recasts the classification's W01 owner). The fact that changes is WIS's own: an accepted revision, immutable and attributable (WIS-02.a, WIS-02.b), with one canonical source (WIS-01.f). WIS is not the owner of the *authorization* decision (WIS-07.a), and it does not decide here who may accept: it reads ADC's competence fact, as HEB reads ADC's classification in I-1. The classification's caveat leaves the competent owner to the pass. W01's ADC is the competence input, not the admitting owner.

**Consequences belong to their own owners, and are never this operation's effect** (I5-09):
- whether existing grants still cover the new revision: ADC and HEB (WIS-02.d, ADC-02.d, WIS-07.b);
- the assurance basis against the new criteria: AEV (WIS-02.d, AEV-01.a);
- reconciling known consumers of a changed interface: CNI's own hold on each binding (CNI-02.d).

**What ADC's competence fact is.** For a project boundary, the competence fact is ADC's current statement of who decides there:
- the operator; or
- a named external authority, whose own decision ADC must qualify (ADC-01.a, ADC-01.b).

A Lead's statement of who is competent is not this fact. **Candidate:** a project-level record that ADC issues, with finer boundaries later.

## I5-02. `CREATE_PROPOSED_WORK` (W15), the delegated row

**Outcome:** the current Lead records a provisional proposal: either a new work identity, or a new revision of existing work.

**Origin:** I1-01's class, `CURRENT_SUCCESSOR_GENERATION`: CS-07's authenticated session, with both proof slots `null`, decided before any owner state is read.
- **The subject names the Lead's seat** (`attachment_ref`, `generation_ref`).
- **WIS reads HEB's fact** that the principal is that generation's Lead. Otherwise the result is `ACTOR_NOT_CURRENT_LEAD`, or `GENERATION_FENCED`. If HEB's fact is unavailable, the request holds.
- The same consequence as I1-01 follows: on a host where G3 is not qualified there is no qualified Lead generation, so the wire refuses it, and the functional CLI serves the preview.

**The target names:**
- the work kind (`epic`, `story` or `ticket`);
- exactly one of these:
  - `parent`: a new child, with the parent's accepted revision;
  - `revises`: a new revision, with the work's expected accepted revision;
  - neither: a new root objective;
- for a root objective, the originating instruction: the operator's attributable record (ADC-01.c);
- the content's SHA-256;
- `supersedes_proposal_ref`, or `null`;
- the proposal's finite validity.

**WIS admits it only if:**
- the project is registered (I5-07);
- the parent or predecessor revision is the current accepted one (`PARENT_NOT_CURRENT`, `REVISION_STALE`);
- the kinds nest: a ticket has no children, and a child is below its parent's kind (WIS-01.b; `PARENTAGE_INVALID`);
- a root names an operator-authored instruction. A Lead's summary is not one (ADC-01.c; `ORIGIN_SOURCE_MISSING`);
- the content is already held under that digest (otherwise it holds: `CONTENT_UNAVAILABLE`);
- the work is not cancelled or replaced (`WORK_CLOSED`);
- a superseded proposal is still open, and was made by this same Lead generation (`SUPERSEDED_PROPOSAL_INVALID`).

**What it records:**
- a proposal in state `PROPOSED`, with WIS's stable work ID (new, or the existing one) and a proposed revision ID;
- the proposer's generation as its attribution, kept separate from the originating instruction (ADC-01.c);
- its provenance `LEAD_PROPOSAL`.

A superseded proposal becomes `SUPERSEDED`. **Candidate:** the content reaches WIS through its own content interface, keyed by digest, before the command; the wire carries only scalars.

**What it never does** (W15's text; ADC-01.d, ADC-03.c, ADC-03.m, WIS-03.a, WIS-08.b):
- **it grants nothing.** No execution right, no ownership for the proposer, no acceptance;
- **parentage is not a grant;**
- **the proposal stays provisional** until a competent acceptance (I5-03).

**Sets:** it may share a set with A-28's delegated rows, and never with a protected row (CS-02).

## I5-03. `DECIDE_WORK_PROPOSAL` (W01, W02, W16, W17), protected

**Outcome:** with the operator's G3 consent, under ADC's competence fact, WIS accepts or declines one exact proposal.

**The target carries every fact the operator decides on, as leaves.** G3-03 renders each one:
- `proposal_ref`, and the content's SHA-256;
- `work_ref`, and `work_kind` (`epic`, `story` or `ticket`; review I5R1-3);
- `expected_accepted_revision` (`null` for a new identity);
- `original_accepted_revision`: the first accepted revision, so cumulative change is judged against it, not only against the predecessor (WIS-02.a, WIS-02.c, WIS-02.f; `null` for a new identity);
- `parent_work_ref` and `parent_accepted_revision`: where the work lands (both `null` for a root or a revision; review I5R1-3);
- `originating_instruction_ref` (non-null for a root);
- `provenance`: `LEAD_PROPOSAL`, `EXTERNAL_INTAKE` or `MANUAL_INTAKE` (WIS-08.b);
- `decision`: `ACCEPT` or `DECLINE`;
- `authority_decision_ref`: an external authority's decision, or `null` (I5-01).

**WIS admits it only if:**
- the proposal exists and is `PROPOSED`, and not expired (`PROPOSAL_UNKNOWN`, `PROPOSAL_CLOSED`);
- **every leaf equals WIS's own record of the proposal** (`RECORD_MISMATCH`). So what the operator approved is the proposal WIS holds, never a description of it;
- the expected revision and the parent's revision are still the current accepted ones (`REVISION_STALE`, `PARENT_NOT_CURRENT`);
- ADC's competence fact is available (otherwise it holds: `COMPETENCE_UNAVAILABLE`), and:
  - for the operator, `authority_decision_ref` is `null`;
  - for an external authority, it names that authority's decision on this exact proposal, and ADC qualifies it (`AUTHORITY_NOT_COMPETENT`, `AUTHORITY_DECISION_INVALID`).

**`ACCEPT` records:**
- a new immutable accepted revision, attributed to the consent, the competent authority and any external decision (WIS-02.b). Its ID is WIS's, never the Lead's;
- the proposal becomes `ACCEPTED`;
- every other open proposal that named the same expected revision becomes `SUPERSEDED`. Each was a change to a revision that is no longer current;
- for a root, it is the work's original accepted source (WIS-02.a).

**`DECLINE` records** the proposal as `DECLINED`, and nothing else.

**Kept apart** (W16's text; ADC-03.m): accepting a scope is not an execution grant, and not HEB effect admission.

**Where an intake proposal comes from** (W17; review I5R1-4). `CREATE_PROPOSED_WORK` records only `LEAD_PROPOSAL`. So WIS records an intake proposal through **its own intake interface** (Candidate, like content intake by digest), never through an O-01 command. The interface:
- records the provenance `EXTERNAL_INTAKE` or `MANUAL_INTAKE`, and the intake's source attribution. The proposal stays provisional and untrusted until decided (WIS-08.b);
- **takes that attribution from an authenticated source outside every agent's reach** (review I5C2-2). A submission from any agent lineage, the Lead included, is never an intake: a Lead's proposal is a `LEAD_PROPOSAL`, made through I5-02. So no agent can give its own proposal an external or manual source;
- takes the project from the project the intake names. **An intake that names no registered project is not recorded.** The project is never inferred (W17's text: "mandatory project scope never inferred");
- grants nothing and accepts nothing, as I5-02 does.

W17's operator part is served for intakes recorded this way. An intake is accepted only by `DECIDE_WORK_PROPOSAL`, never in scope.

**In-scope acceptance: W17's "ordinary in-grant delegation preserved."** This needs no operator consent and no new command:
- **The case:** the Lead decomposes accepted work into children within its accepted scope. ADC-03.b permits this after the stated checks; asking the operator for each child would be the ceremony WIS-08.c forbids.
- **The rule:** WIS accepts a **child proposal** without `DECIDE_WORK_PROPOSAL` only when **ADC issues a current in-scope determination for exactly that proposal:** its digest, and its parent's accepted revision.
  - WIS records the accepted revision attributed to that determination.
  - A Lead's own claim of scope is a label, never a determination (ADC-05.a, ADC-05.g; the same pattern as ADC-02.l; `SCOPE_LABEL_NOT_DETERMINATION`; review I5R1-8).
- **Never this way:**
  - a root objective (W01's text: "no inference from conversation");
  - a revision of existing work (see below);
  - an intake (W17's text: "mandatory project scope never inferred");
  - a declined or closed proposal.
- **What the determination assesses** is ADC's (I-3), including whether the child stays within the parent's accepted purpose (WIS-03.a, WIS-03.d). **Candidate:** an owner-to-owner step, like I-1's claim, not an O-01 command.

**A revision always takes a decision.** WIS-02.c: an *authorized* clarification may keep the identity through a new accepted revision. WIS-02.d gives harmless edits a no-ceremony path, but that path is AEV-01.g's qualified unchanged-effect disposition for the **reassessment** that follows acceptance. It does not accept the revision itself. So in this pass every revision is accepted through `DECIDE_WORK_PROPOSAL` (review question Q2).

## I5-04. `CANCEL_OR_REPLACE_TICKET` (W03), protected

**Outcome:** with the operator's consent, WIS ends an accepted ticket, or replaces it with a successor identity.

**The target names:**
- the ticket and its expected accepted revision;
- `CANCEL` or `REPLACE`;
- for `REPLACE`, the successor proposal and its digest;
- `authority_decision_ref`.

**WIS admits it only if:**
- it is a ticket (`NOT_A_TICKET`), still open (`WORK_CLOSED`), at the expected revision (`REVISION_STALE`);
- a `REPLACE` names an open new-identity ticket proposal whose digest matches (`PROPOSAL_UNKNOWN`, `PROPOSAL_CLOSED`, `RECORD_MISMATCH`, `SUCCESSOR_INVALID`), and a `CANCEL` names none (`SHAPE_INVALID`);
- **the successor lands where the ticket was** (review I5R1-3):
  - its proposal's parent is the ticket's own parent, at that parent's current accepted revision (`SUCCESSOR_INVALID`);
  - **a root ticket's successor is a root ticket proposal with its own operator-authored instruction** (ADC-01.c; review I5C2-1). So a root ticket keeps the `replaces` lineage and WIS-03.b's carry;
  - a replacement never re-parents. Re-parenting is a restructuring decision, outside this pass (WIS-03.a, WIS-03.b);
  - so the operator's consent, which shows the ticket, also fixes where its successor goes;
- competence holds as in I5-03.

**What it records:**
- **The ticket's identity and accepted revisions are never mutated** (W03's text, WIS-06.d).
  - It becomes `CANCELLED` or `REPLACED`, and stays readable, with its findings.
- **On `REPLACE`, the successor is accepted under this one consent,** with lineage `replaces`.
  - It carries the predecessor's parent obligations, classification floor, composition requirements and unresolved adverse findings, unless a separate authorized disposition changes their applicability (WIS-03.b).
  - Carrying them is WIS's, not the proposal's: a proposal that leaves one out does not drop it.
- **Open proposals to revise the ticket** become `CLOSED_BY_CANCEL`.
- **Its open WIS decision needs:**
  - on `CANCEL`, they close unanswered, and stay readable;
  - on `REPLACE`, they are re-issued on the successor (WIS-03.b).

**The D letter.** The kind letters give W03 a delegated part. This pass gives the Lead no cancel. A Lead withdraws its own unaccepted proposal by superseding it (I5-02), or lets it expire. Ending accepted work stays the operator's. (Review question Q3.)

## I5-05. `ANSWER_DECISION_NEED` (W05), protected

**Outcome:** with the operator's consent, the need's issuer records the operator's answer.

**Scope:** decision needs that **WIS** issues. The example is a collision or ambiguity to reconcile (WIS-08.e).
- **WIS-02.c's continuation-versus-successor choice is not a need** (review I5R1-5). It is made by the decision that enacts it:
  - `DECIDE_WORK_PROPOSAL` on a revision, whose `original_accepted_revision` leaf exists for that judgement;
  - or `REPLACE`.
- **A need another owner issued** is answered through that owner's increment. Here it is `NEED_NOT_WIS` (review I5R1-7): the need exists, but WIS is not its issuer (review question Q4).

**The target names:**
- the need;
- the work and the revision it was issued on;
- one option from the need's closed set;
- `authority_decision_ref`.

**WIS admits it only if:**
- the need is open (`NEED_CLOSED`);
- the work's accepted revision is still the one the need was issued on (`NEED_STALE`);
- the option is one of the need's own options (`OPTION_UNKNOWN`);
- competence holds as in I5-03.

**What an answer can do** (W05's text: "does not create unrelated grant/effect"):
- the need is `ANSWERED`;
- the option's stated consequence applies, within WIS's own facts only. For example, two references are recorded as distinct subjects, or as the same one.
- **An option whose consequence would accept a revision, create or end an identity, or grant anything is not answerable** (`OPTION_NOT_ANSWERABLE`). Those go through I5-03, I5-04 or ADC. So the answer cannot bypass their checks.

## I5-06. `APPROVE_INTERFACE_CHANGE` (W04), protected, owner CNI

**Outcome:** with the operator's consent, CNI accepts or declines an interface commitment for consumer use, as a new commitment or a change to one.

**The target names:**
- the interface;
- its expected current commitment (`null` for a new interface);
- the candidate and its content digest;
- the work it belongs to, with that work's accepted revision;
- `ACCEPT` or `DECLINE`;
- `authority_decision_ref`.

**CNI admits it only if:**
- the expected commitment is current (`INTERFACE_STALE`);
- the candidate is open and matches its digest (`CANDIDATE_UNKNOWN`, `CANDIDATE_CLOSED`, `RECORD_MISMATCH`);
- **the scope work is open, and the revision named is its current accepted one** (`SCOPE_NOT_CURRENT`; if WIS's fact is unavailable, it holds: `SCOPE_UNAVAILABLE`). A cancelled or replaced work has no current revision, though its last accepted revision is never mutated (review I5R1-2);
- competence holds as in I5-03.

**`ACCEPT` records:**
- **a new accepted commitment with its own content identity** (CNI-02.b). A changed interface never inherits acceptance through its old name. The earlier commitment stays identifiable.
- **every recorded consumer binding to the earlier commitment needing reconciliation** (CNI-02.d). That is CNI's hold on each binding, not this operation's effect. Unrelated valid work is untouched.

**It never records** (W04's text: "adoption ≠ implementation"):
- an implementation;
- an integration;
- a package acceptance.

**Candidate:** a provider submits the candidate through CNI's own interface, keyed by digest.

## I5-07. `INIT_OR_REGISTER_PROJECT` (L10): no O-01 command

**Ruling:** registering a project is the installation owners' act, not an operator-origin command. L10's owner text names "WIS/installation owners" and an "exact accepted project subject distinct from host attachment/Lead grant". The kind letters (F/Q, with no O) agree, as the designer's reading.
- **The functional `aew init` serves the preview,** as A-25's profile has the CLI do.
- **The qualified registration is made at the console.** This is the pattern of A-27 WIS-11, where root anchors the WIS store. It records the exact project subject: `project_ref`, the store it is anchored to, and the installation.
- **That subject is distinct from any host attachment or Lead grant** (L10's text). Registering a project grants nothing, and attaches no Lead.

**What the wire needs from it:** every I-5 type requires the subject's `project_ref` to be a registered project (`PROJECT_UNKNOWN`). It does not register one.

## I5-08. What the operator sees when deciding

**The consent is A-26's, unchanged.**
- G3-03 renders every target leaf of I5-03 to I5-06: identities, digests, the decision, and, for a revision, the original accepted revision too.
- **G3-03's consequence fact comes only from the action's sole admitting owner's D-01 read,** and is at most one, so it may be absent:
  - for WIS's four protected types, it is WIS's work read of the subject work: the work revised, the ticket cancelled, or the need's work. For a new child it is the parent's work read;
  - a root objective has no work resource until it is accepted, so it has no fact;
  - **`APPROVE_INTERFACE_CHANGE` has none.** Its owner is CNI, and D-01 has no CNI item read (`owner-pins.json` names CNI only as the index's collection-basis owner). A WIS fact would come from the wrong owner. A CNI interface read is a D-01 change (I5-09).
- **G3's 243-line limit holds unchanged.** A member's rendering is 1 template line, its 14 common intent leaves, its target leaves and 1 owner fact. `ISSUE_STANDING_POLICY` has 30 lines, so a new target may have at most 14 leaves; I-5's largest, `DECIDE_WORK_PROPOSAL`, has 12. `verify_i5.py` derives this from the wire, the way `verify_g3.py` does.

**The content is read; its identity is consented** (ADC-03.n: decision-bearing commitments visible to the approver at approval time):
- **The proposal's content is agent-authored text.** G3-03 never shows agent text as prose, so the rendering cannot carry it.
- **The operator reads it on the read surface:** the proposal, its author, its decision-bearing commitments marked as such, and its digest.
- **The consent binds that digest,** and WIS refuses any leaf that differs from its record (I5-03). So what is accepted is exactly what was readable.
- **Decision-bearing commitments are fixed at proposal time.** The proposal is immutable, and so is the accepted revision (WIS-02.b). Nothing can relabel them afterwards.
- **Candidate:** both the confirmer and the read surface show the same digest prefix, long enough that two different contents cannot match it by chance.
- **The residual risk is an AEW host-code bug** that shows the operator other content than the bound digest. That is in the threat model, and is review question Q1.

**I5-08a. Activation needs the read** (review I5R1-1). Four types bind content the operator must be able to read. Each is activated only once a selected read shows the operator that content, by the digest or ref its target binds:
- `DECIDE_WORK_PROPOSAL`: the proposal's content;
- `CANCEL_OR_REPLACE_TICKET` with `REPLACE`: the successor's content;
- `ANSWER_DECISION_NEED`: the need's options, each with its consequence;
- `APPROVE_INTERFACE_CHANGE`: the candidate's content.

That read is I5-09's D-01 change, or a named functional read.
- **Until it exists, the owner holds these requests** with `CONTENT_READ_UNAVAILABLE` (review I5C2-3). A hold allocates nothing and consumes no consent, as I5-11's holds do.
- **Within `CANCEL_OR_REPLACE_TICKET`, only `REPLACE` is held.** A plain `CANCEL` binds no new content, so it needs no such read.

## I5-09. What each operation reports, and what is readable

**What the 0.4 owner-operation GET's `IntentResult` reports**, using A-28's existing fields:

| Action | At admission |
|---|---|
| `CREATE_PROPOSED_WORK` | `ADMITTED`, `EFFECT_CONFIRMED`: the proposal is recorded. Its identity is `(WIS, operation_ref)` |
| `DECIDE_WORK_PROPOSAL` | `ADMITTED`, `EFFECT_CONFIRMED`: the acceptance or decline is recorded |
| `CANCEL_OR_REPLACE_TICKET` | `ADMITTED`, `EFFECT_CONFIRMED` |
| `ANSWER_DECISION_NEED` | `ADMITTED`, `EFFECT_CONFIRMED` |
| `APPROVE_INTERFACE_CHANGE` | `ADMITTED`, `EFFECT_CONFIRMED` (owner `CNI`) |

**Grant reassessment, assurance and consumer reconciliation are other owners' holds** (I5-01). So a confirmed acceptance never reads as "the work may now run".

**What D-01 0.3.4 already shows:**
- the work read (`/v1/read/work/{work_kind}/{work_id}`): `accepted_revision`, `parent`, `child_refs`, `accepted_interface_refs`, and `composition`, including `provisional`;
- the attention read: a decision need's existence, as an `owner_issued` item with category `decision_need`.

**What a D-01 change must add** (as I1-08 says for I-1):
- proposals and their content, state and author;
- a need's options;
- replacement lineage;
- the original accepted revision;
- a CNI interface read: commitments, candidates, and consumer bindings that need reconciliation. Until it exists, W04's consent has no consequence fact (I5-08).

D-01's owner-operations index lists A-25's ten actions only, so I-5's operations are found by `(owner, operation_ref)` until that change.

## I5-10. Cross-row interactions

Every pair of operations that touches the same subject has a stated rule. A cell marked † has a fixture in `verify_i5.py`.

| # | When | Then |
|---|---|---|
| X1† | two decisions on one proposal | the first closes it; the second is `PROPOSAL_CLOSED` |
| X2† | one of several revision proposals on the same expected revision is accepted | the others become `SUPERSEDED`; deciding one is `PROPOSAL_CLOSED` |
| X3† | a ticket is cancelled or replaced while proposals to revise it are open | they become `CLOSED_BY_CANCEL`; deciding one is `PROPOSAL_CLOSED` |
| X4† | a ticket is cancelled or replaced while WIS needs on it are open | `CANCEL`: they close unanswered (answering is `NEED_CLOSED`). `REPLACE`: they are re-issued on the successor |
| X5† | a revision is accepted while ADC grants name its predecessor | no grant changes. WIS signals ADC to reassess; until ADC issues a grant naming the new revision, I-1's switch to it is `TARGET_NOT_GRANTED` (WIS-07.b) |
| X6† | an interface change is accepted while consumers are bound to the old commitment | each recorded binding needs reconciliation; the old commitment stays identifiable; no implementation is recorded |
| X7† | the parent's accepted revision changes before a child proposal is decided | `PARENT_NOT_CURRENT`; never re-attached silently |
| X8† | a replacement takes a successor proposal that also awaits its own decision | the replacement accepts it; the separate decision is `PROPOSAL_CLOSED` |
| X9† | a Lead supersedes a proposal while the operator's decision on it is pending | the decision is `PROPOSAL_CLOSED`; the consent binds the old proposal, so no content can be swapped in |
| X10† | a need was issued on revision N, and revision N+1 is accepted | answering is `NEED_STALE` |
| X11† | ADC's in-scope determination arrives for a proposal already declined | nothing is accepted: a closed proposal stays closed |
| X12† | a cancelled ticket | its identity, accepted revisions and findings stay readable (WIS-06.d) |
| X13† | an interface change whose scope work has a newer accepted revision | `SCOPE_NOT_CURRENT` |
| X14 | a cancelled ticket is a Lead's active work context | the context's grant is ADC's to reassess, as in X5. HEB holds new effects under it. That is HEB's and ADC's outcome, so a WIS and CNI model cannot hold it: it is pinned by A-28's I1-02 fixtures (review I5R1-9) |
| X15† | an interface change is pending, scoped to a ticket that is then cancelled or replaced | `SCOPE_NOT_CURRENT`; the candidate stays open, for a decision scoped to the successor (review I5R1-2) |
| X16† | ADC's in-scope determination for a child proposal arrives while the operator's decision on it is pending | whichever reaches WIS first stands. The other is `PROPOSAL_CLOSED` (for the decision, an allocated refusal that consumes its consent, CS-06), and nothing else is accepted (review I5R1-6) |
| X17† | the successor proposal is accepted on its own before a `REPLACE` naming it | the `REPLACE` is `PROPOSAL_CLOSED`; the ticket stays open, and the separately accepted ticket carries none of its obligations. Ending the old ticket is a separate `CANCEL` (review I5R1-6) |
| X18† | a `REPLACE` names a successor under another parent | `SUCCESSOR_INVALID`: a replacement never re-parents (I5-04; review I5R1-3) |
| X19† | a root ticket is replaced | the successor must be a root ticket proposal with an operator-authored instruction. It carries the ticket's obligations and open findings, with `replaces` lineage. A successor under a parent, one citing a Lead's instruction, or a revision proposal is `SUCCESSOR_INVALID` (review I5C2-1) |

## I5-11. Ordering, atomicity and refusals

**Ordering and atomicity:**
- **One admission path:** origin, then owner state, then at most one owner effect per member (CS-05). No WIS or CNI state is read before origin.
- **Each operation is compare-and-set atomic** in its owner's state: a decision and the closing of the proposals it supersedes, a cancel and the closing of its proposals and needs, a replacement and its successor's acceptance.
- **A lost response is reconciled** from `(owner, operation_ref)`, never by redispatch (CS-04, CS-08).

**Refusals and holds:**
- **Each owner reason maps to an adopted reason code** in `wire/refusal-reasons-0.4.json`. The map is complete and fail-closed.
- **Refusals before the owner step allocate nothing.** An owner refusal is an allocated operation.
- **A hold allocates nothing, and consumes no consent** (A-24 SW-06). These are holds: unknown owner state, unavailable competence, unavailable content, an unavailable HEB Lead fact, an unavailable scope revision, and a missing content read (I5-08a).

## I5-12. The wire

`tools/build_i5_wire.py` generates `wire/` from A-28's frozen `adopted/o01-0.3-i1/wire/`, pinned by its `SHA256SUMS`:
- **`o01-command-0.4.schema.json`:** A-28's schema, with five Intent branches and five Target definitions added, the owner enums extended (I5-00a), and the version `o01-command-0.4-candidate`.
  - The delegated branch requires the seat in the subject, and both proof slots `null`.
  - **The protected branches require `attachment_ref` and `generation_ref` to be `null`,** because an operator decision is not made from a seat. This is a new rule: A-25's and A-28's branches leave the seat unconstrained. It applies to I-5's branches only.
- **`openapi-o01-0.4.yaml`:** the same definitions. The script checks that the two forms are equal.
- **`action-registry-0.4.json`:** A-28's sixteen rows unchanged, plus five, with their catalogue IDs.
- **`refusal-reasons-0.4.json`:** A-28's map, plus the five types' owner reasons.
- **`PREDECESSOR-PINS.json` and `SHA256SUMS`;** `--check` regenerates and compares.

## I5-13. Questions for the reviewer

- **Q1 (I5-08):** does binding the content digest, with the content read on the read surface, meet ADC-03.n? Or does G3 need a rendered, attributed content leaf? That would change adopted text (A-26), so it is the operator's.
- **Q2 (I5-03):** is ADC the competent owner of the in-scope determination that preserves W17's in-grant delegation for new children (ADC-03.b)? Is "a later ADC pass (I-3) specifies its issuance" an acceptable deferral, given that nothing in this pass accepts without it? And is it right that every revision, however small, takes the operator's decision? WIS-02.d's AEV-01.g path relieves only the reassessment that follows.
- **Q3 (I5-04):** is giving W03's D letter no Lead cancel, and serving it by supersession and expiry, right? Or does the Lead need a delegated cancel of an in-scope ticket?
- **Q4 (I5-05):** is scoping `ANSWER_DECISION_NEED` to WIS-issued needs right? Or should one type carry the issuer as its owner, which the registry's single `sole_admitting_owner` does not allow today?
- **Q5 (I5-00):** does one `DECIDE_WORK_PROPOSAL` type for W01, W02, W16 and W17 lose a distinction the operator or an owner needs?

## I5-14. Not claimed

- **This selects interface architecture.** It qualifies no host, builds nothing, and activates no action. Protected rows stay held wherever G3 is not established. The four content-binding types also wait for their read (I5-08a). The delegated row needs a qualified Lead generation (I5-02).
- **The mechanisms marked Candidate.** These are:
  - content intake by digest;
  - WIS's intake interface (I5-03);
  - ADC's competence fact and in-scope determination;
  - CNI's candidate intake;
  - the registration console step.
- **Out of scope:**
  - D-01 changes (I5-09);
  - ADC's determinations themselves (I-3);
  - needs issued by other owners;
  - cancelling epics and stories, which are not in the catalogue's rows;
  - A-28's sixteen actions, which are unchanged.
