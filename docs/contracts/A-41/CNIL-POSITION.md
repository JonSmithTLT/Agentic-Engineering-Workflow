<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-41
source: 30-stages/STG-17-selection-and-CNI-link-vocabulary/adopted/cnil-r2.1/CNIL-POSITION.md
source-sha256: 3daf281783d37848f71cb180f0feea2cf43b0e1f99b72f359143819db5ab574c
edits-sha256: none
-->

# CNI's link vocabulary (PROPOSED, revision 2.1)

**Namespace:** `CNIL-`
**Status:** proposed. It amends A-09 (CNI) by addition, and extends A-40's two link kinds beyond a Ticket and an inquiry. No adopted byte changes.
**Authority:**
- the operator's decision of 2026-10-25 (`00-governance/decisions/2026-10-25-operator-wire-track-ahead-of-publication-tooling.md`): the wire track's design comes first;
- the "Order" line of the first selections (`00-governance/decisions/2026-10-24-operator-first-selections-research-maps-knowledge.md`): WIS's three statements come first, then CNI fixes its link vocabulary, so that the links are native;
- the operator's instruction of 2026-10-25 to start the wire track's step 2.
**Threat model:** the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`): a contained agent cannot fake an approval, forge an owner fact, read a credential or escape. Malicious code running as the operator is out of scope (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`). Here, the owner facts are who recorded a link, under which acceptance, at which revisions, and whether it is accepted or held. An agent can propose a link, record reliance under its own work, and hold its own effects; none of these holds anyone else's work or reads as an acceptance.
**Research consulted:**
- **None** for `CNI-01` to `CNI-06` and `CNI-08`, `WIS-02` to `WIS-07`, `RX01-31`, `RX01-32`, `RX01-34`, `RX01-36`, `K01-10`, `K01-12`, `K01-16`, `K01-22`, `K01-34`, `K01-35`, `K01-43`, `P01-06`, `P01-42`, `A-25` and `A-40`.
- **For `CNI-07`, `HEB-02` and `ADC-03`:** one study, `software-research-workflow-2026-10-15` (`private:software-research-workflow-2026-10-15/`, partly adopted). What this position takes from it:
  - the minimal durable link it observed is a hash and a path cited in the consumer's record (its pass 2, section 3);
  - a link is checked by content, not by label, since the study's own first version cited the wrong one of two artifacts sharing a label (pass 2, section 5);
  - in its specimens the consuming records were design documents and designer decisions (pass 2, sections 3 and 4). `CNIL-R03` departs from that, and says why.
- **For `A-13`:** five studies. Two bear on what this position settles:
  - the knowledge capture and admission study (2026-10-04): admission, support and conflict are separate dimensions, and many reports citing one lesson are one evidential root;
  - the knowledge manifest prototype lessons (2026-10-04): dispositions target exact versions.

  So Knowledge's relations stay K-01's, and a consumed Knowledge item is named at its content version (`CNIL-R04`). The service identity spike, the query-routing study and the agent-effectiveness study bear on nothing here.
- **For `RX-DEC-05`:** the agent-effectiveness study and its synthesis (2026-10-09) propose impact relations of high precision that are never a gate, as `CNIL-05` keeps them.
- **For `A-09`:** the harness native-integration research, whose findings are on harness capability, says nothing about links.
**Files:** this file. Its coverage of A-09, `CNIL-COVERAGE.md`, and that file's checker, `check_coverage.py`, are stage evidence for `CNIL-Q02`, not adopted text.

## What the adopted text already decides

- **One source per relationship:** each identity-bearing relationship has one canonical source, and no projection defines one (`WIS-01.f`). Coordination consumes WIS's referents without defining rival ones (`CNI-01.a`), and governs progression over them, not their meaning (A-09, section 1.1).
- **Parentage grants nothing** (`WIS-03.a`).
- **Reliance is kept and read in reverse:**
  - a claim consumed as a premise is referenceable from the consumer back (`WIS-05.c`);
  - lineage keeps consumed-as-premise links (`WIS-06.c`);
  - Knowledge consumers keep who relied on what (`WIS-07.d`);
  - a determination supersedes another only through an explicit resolution relationship (`WIS-06.b`).
- **Dependencies:**
  - classified from the accepted revision or composition commitment, in four constraint classes, and an unclassified or contested one holds conservatively only the affected effects (`CNI-03.b`, and `CNI-X35`: "unknown material edges hold affected action");
  - satisfied from canonical facts, never from an assertion or a provider's completion (`CNI-03.c`);
  - reconstructable from durable records (`CNI-03.f`), and rechecked when an action takes effect (`CNI-03.g`);
  - an unsatisfiable wait gets an accountable disposition (`CNI-03.h`).
- **Interface commitments:**
  - allocated from requirements (`CNI-02.a`);
  - identified by content, so a changed interface cannot keep acceptance through its old label (`CNI-02.b`);
  - a consumer may proceed against an accepted commitment (`CNI-02.c`);
  - a change is assessed against the recorded consumers, and the newly discovered ones (`CNI-02.d`).
- **Proposed impact links are advisory "until qualified as sufficient for a consequential hold, scope change, or completion decision",** and an absent match proves nothing (`CNI-04.c`). A newly discovered affected consumer triggers a qualified impact assessment and proportionate holds (`CNI-05.c`). Routed notes stay untrusted data (`CNI-04.b`).
- **Premises are recorded at acceptance:** a consuming decision records its premise when it is accepted, and one not recorded then cannot later justify progression until reconciled (`CNI-07.b`). A changed claim reaches its consumers (`CNI-07.c`).
- **History is kept, not rewritten** (`CNI-01.d`), and routine coordination stays light (`CNI-01.e`).
- **A-40's two link kinds:**
  - request and consumption join a Ticket and an inquiry (`WISR-04` to `WISR-07`);
  - a link conveys nothing beyond its record (`WISR-04.a`);
  - owner facts are AEW's observation, and a command naming another decider is refused (`WISR-09`);
  - a Lead's record under a Ticket's accepted revision "counts as accepted here, and reads as held, not accepted" (`WISR-07`);
  - the path is light (`WISR-08`), and an author's revision of a claim is linked (`WISR-03.d`);
  - links with other ends are left to this vocabulary (`WISR-B1`).
- **Knowledge** (A-13):
  - Knowledge has its own relations among sources (section 3), and cannot adopt a premise (section 2);
  - consequential reliance is only an accepted WIS or CNI decision record (`K01-34`), whose premise the WIS and CNI owners register (`K01-22`);
  - a nomination stays a candidate until admitted (`K01-04`, `RX01-31`);
  - context delivered before any acceptance gets bounded attention of its own (`K01-10`, `P01-42`).
- **An experiment belongs to its inquiry** (`RX01-19`, `WIS-05.d`).
- **The wire as adopted:**
  - D-01 0.3.4's links are `Link` relations (`parent`, `child`, `depends_on`, `claim`, `knowledge`, `determination`, `accepted_interface` and others). "Restricted/unknown targets have no Link object and no per-hidden placeholder", and member lists carry their visibility (`MemberView`: `complete_visible`, `partial_visible`, `members_withheld`, `unknown`).
  - O-01 0.4 and 0.8 have no dependency record and no consumer-binding command. `APPROVE_INTERFACE_CHANGE` records a commitment (A-29).

**What is missing:**
- no adopted text lists the link kinds Coordination's records may carry;
- dependencies, interface commitments and advisory links are stated apart, with no common rules for how a link is recorded, read from both ends, refused and changed;
- A-40's two kinds cover only a Ticket and an inquiry;
- reliance found mid-work has no recording moment short of a new acceptance.

## The parts

| Part | What it is | Written by | Read by |
|---|---|---|---|
| A link | a record in the store: its kind, its two ends, its recorder, and the acceptance it belongs to, accepted or held | AEW's host code, from an authenticated command, an owner's decision or Coordination's own canonical facts | both ends' owners, Coordination, and the operator's views, within each reader's recipient rules |
| A proposer | an agent (the Lead, a worker, a researcher) or a heuristic | proposes; AEW's host code writes the record, attributed to it | as the link's readers |
| A recorder of held reliance | the work's Lead, or an inquiry's researcher, recording reliance under the work's accepted revision (`CNIL-02.b`) | records; AEW's host code writes the record, attributed to it | as the link's readers |
| Coordination | the owner of progression, reading links to hold, admit and release | the `dependency` it records from canonical facts (`CNIL-01.b`) | all of them |

**The ends, per kind:**

| Kind | From | To | Recorded with |
|---|---|---|---|
| `request` | the asking work: an Epic, a Story, a Ticket or an inquiry | an inquiry, or a PoC Ticket an inquiry asks for | the requested work's acceptance or opening (`WISR-05`) |
| `consumption` | the consuming work: an Epic, a Story, a Ticket or an inquiry | a claim, or a PoC Ticket's result, by hash and path; an admitted Knowledge item at its content version; a determination | the consuming decision's acceptance; or held, mid-work (`CNIL-02.b`) or with an inquiry's disposition (`CNIL-09.a`) |
| `dependency` | the dependent work | its prerequisite work, or a requested inquiry | the accepted revision or composition commitment that classifies it; or, unclassified or contested, as `CNIL-01.b` says |
| `interface_commitment` | the consuming work | the accepted interface commitment it builds against | the accepted revision or composition commitment (`CNI-02.a`) |
| `proposed_impact` | any subject, a proposal at its digest included | any subject, a proposal at its digest included | its proposal, attributed to its proposer |

## Rules

**CNIL-01. Coordination's links have five kinds, and a record of no other kind is text.** The vocabulary is closed:
- **`request`:** from the asking work to the requested work (`WISR-05`);
- **`consumption`:** from the consuming work, at the decision that records it, to what it relies on (`WISR-06`, `CNI-07.b`);
- **`dependency`:** from the dependent work to its prerequisite, in one of the four classes of `CNI-03.b`, or `unclassified` or `contested` (`CNIL-01.b`);
- **`interface_commitment`:** from the consuming work to the accepted interface commitment it builds against (`CNI-02.a`, `CNI-02.b`);
- **`proposed_impact`:** an advisory link between two subjects, which anyone authorized may propose (`CNIL-05`).

A record of no listed kind is text. Coordination routes it as an attributable note (`CNI-04.b`), and holds, admits, satisfies or releases nothing on it. Every other relationship Coordination acts on is one an adopted owner records, which `CNIL-01.a` names.

**CNIL-01.a** Relationships that other contracts own are named here, never redefined and never stored as links. Coordination reads each from its owner:
- **`accepted-revision`:** a work item's accepted revision, its accepted scope and milestone, and its successor and consolidation lineage (`WIS-02.c`, `WIS-02.d`, `WIS-03.b`; `CNI-03.e`, `CNI-02.f`);
- **`parentage`** (`WIS-03.a`);
- **`package-closure`:** a package, its accepted revision and its material inputs (`WIS-04.a`, `WIS-04.c`; `CNI-06.b`);
- **`determination`:** a determination's subject, obligation, basis and resolution (`WIS-06.a`, `WIS-06.b`);
- **`composition`:** the requirements-derived allocation, criteria and integration-evidence owner, recorded with the accepted revision (`CNI-02.a`, `WIS-03.f`);
- **`claim-revision`:** a claim's revision (`WISR-03.d`);
- **`experiment`:** an experiment's place in its inquiry (`RX01-19`);
- **`grant`:** grants and attachments (ADC, HEB);
- **`accepted-input`:** the accepted-input designation and its resolver, HEB's protected metadata (`CNI-05.a`, `HEB-02.g`);
- **`hold`:** a hold, which its owner records and resolves (`CNI-05.e`);
- **`held-question`:** a decision need or reserved question, owned by its issuer: WIS's are answered through `ANSWER_DECISION_NEED` (A-29), and another owner's through its own type (A-32). Coordination holds the affected work and routes the question to a supported response path (`CNI-05.f`, `CNI-08.b`, `RX01-24`);
- **`delivered-context`:** context delivered before any acceptance (`K01-10`, `P01-42`);
- **`knowledge-relation`:** Knowledge's relations among its sources (A-13, section 3);
- **`effect-conflict`:** a conflict between concurrent effects, which is no link. Coordination checks it when an effect is admitted (`CNI-03.a`, `CNI-03.g`), and the hold it records then is a `hold`. A refusal is the admission's own outcome.

The list ends with any other relationship an adopted owner records, under the same rule. `CNIL-Q02` checks that every A-09 clause maps onto a link kind or one of these names.

**CNIL-01.b** An unclassified or contested dependency holds conservatively, and only its own side.
- **Who records it:** Coordination, from canonical facts (for example, a package that consumes another work's unaccepted output, `WIS-04.c`); or an agent that AEW observes assigned to the dependent work, for the dependent work's effects (`CNIL-02`).
- **What it holds:** only the dependent work's effects to which the restrictive class may apply, until an authorized clarification classifies it: a new accepted revision, or the owner of the contested class (`CNI-03.b`, `CNI-05.e`). Neither its recorder nor the Lead lifts it, since a newly discovered necessary relationship follows the change control of `CNI-02.d`.
- **What it never does:** hold anything on the other end, or satisfy or release anything. An agent's claim about another's work stays a `proposed_impact` (`CNI-05.d`).

**CNIL-02. Every link is a store record, written by AEW's host code, naming its kind and both ends.**
- **The ends:** for each kind, those the parts' table of ends gives. A work subject is named by its WIS identity at its accepted revision; a claim or a result by hash and path (`WISR-03`); a Knowledge item at its content version; a determination by its identity (`WIS-06.a`).
- **Owner facts are AEW's observation:** who recorded the link, the acceptance it belongs to and whether that is accepted or held, the ends' accepted revisions, a consumed claim's qualification, a consumed Knowledge item's current disposition and applicability, and a consumed determination's current standing. Each is taken from the authenticated command or the owner's own record, when the link is recorded, never from a value the caller supplies.
- **A consumed end that does not support the use** is refused or held, saying which: a Knowledge item whose current disposition does not support it (`K01-22`), or a determination that is superseded or unresolved (`WIS-06.b`, `WIS-06.e`).
- **A command that names a recorder, a decider or an acceptance** other than its own authenticated principal and the acceptance AEW observes is refused, naming the field, as `WISR-09` refuses for A-40's links.
- **Recorded with its decision,** as the table of ends gives it. A link that claims an acceptance it was not recorded with is refused, saying so, and changes nothing.

**CNIL-02.a** An end is resolved by its content, within what the recording principal may see, never by its label. A title, label, branch name, file name, or human-facing number or alias is a lookup aid only. A hidden subject resolves exactly as an absent one. A link is refused, saying which end and why, and changes nothing, when an end:
- does not resolve;
- resolves to more than one subject the recorder may see;
- for the four typed kinds, is at a revision that is not accepted (for an inquiry held under a Ticket's scope, the Lead's record under that Ticket's accepted revision counts, `WISR-07`);
- cites bytes that do not match their hash (`WISR-07`, `CNI-02.b`).

A `proposed_impact` may name a proposal at its digest.

**CNIL-02.b** Reliance found mid-work is recorded in one step, held under the work's accepted revision.
- **Who:** the work's Lead, or an inquiry's researcher. One records a `consumption` from the work, under its current accepted revision. It cites what the work relies on, and the decision's own text (a design note, or a disposition) by hash and path.
- **What it is:** the record of a consequential decision made within the work's delegated scope, at that decision (`CNI-07.b`'s "at decision acceptance", for a decision the scope already allows: `ADC-03.f`, bounded by `ADC-03.l`, with `ADC-03.g`'s notice). It accepts nothing new, needs no operator decision and moves nothing from G3. It reads as held, not accepted (`WISR-07`, `WISR-09`).
- **What it does:** impact routing uses it at once (`CNI-07.c`, `WIS-05.c`, `WIS-07.d`).
- **What it is not:** qualified justification for assurance, adjudication or dependent progression. It becomes that only when the accepting authority takes it up: in the decision summary of the work's next acceptance (`ADC-03.n`), or by its explicit reconciliation (`CNI-07.b`). Until then it stays held, carried forward or not (`CNIL-06`).

**CNIL-03. A link conveys nothing beyond what it records.** As `WISR-04.a` states for A-40's two kinds, and now for all five: no authority, effect grant or acceptance; no parentage, inherited obligation or classification floor; no evidence or proof; and no coupling of the two ends' lifecycles.
- **A kind acts only through its owner's rule:**
  - a `dependency` holds its dependent's affected effects until it is satisfied from canonical facts (`CNI-03.b`, `CNI-03.c`), or, unclassified or contested, until it is clarified (`CNIL-01.b`);
  - an `interface_commitment` lets its consumer proceed against the accepted commitment, where `CNI-02.c` allows;
  - a `request` and a `consumption` act on nothing (`WISR-04.a`);
  - a `proposed_impact` acts on nothing (`CNIL-05`).
- **Waiting on an answer is a `dependency`.** Where the asker needs the answer before it proceeds, it waits through a `dependency` from the waiting work to the requested work. That dependency is classified at the waiting work's acceptance, or held as `unclassified` until then (`CNIL-01.b`). Its satisfying canonical fact is the asker's own recorded decision on the answer, never the requested work's disposition (`WISR-05`). Any of an inquiry's six dispositions is an answer, and none of them is a satisfied dependency.

**CNIL-04. Every link is listed from both of its ends.** From any subject, a read lists the links that start at it and those that end at it (`WIS-05.c`, `WIS-06.c`, `WIS-07.d`). Each shows:
- its kind;
- the other end, at the revision or hash it named;
- who recorded it;
- the acceptance it belongs to, and whether that is accepted or held.

What the listing never leaks:
- **A link whose other end the reader may not see is not listed,** and leaves no placeholder (D-01 0.3.4's `Link`).
- **A listing that may be incomplete says so:** whenever the reader's entitlement does not cover the whole domain, the listing says it may be incomplete, whether or not a hidden link exists (D-01 0.3.4's `MemberView`, `partial_visible`). Counts, order and absence leak nothing (`RX01-36`, `P01-06`, `K01-12`).
- **A held link never reads as accepted,** and one the Lead holds never reads as the operator's (`WISR-07`, `WISR-09`).
- **The Knowledge candidates that cite a claim** are listed from the claim by reading K-01's records (`knowledge-relation`), not as links.

**CNIL-05. A proposed link is advisory, and only informs an owner's own decision.** An authorized agent, or a heuristic, may record a `proposed_impact` between two subjects, a proposal at its digest included (`CNI-04.a`). The proposal itself holds, admits, satisfies, releases and cancels nothing, and its absence shows no subject unaffected (`CNI-04.c`).
- **It becomes consequential only through an owner's decision, which cites it.** That decision is one of:
  - a typed link through its kind's own decision;
  - a hold that the hold's owner records on a qualified impact assessment (`CNI-05.c`, `CNI-05.e`);
  - a scope or completion decision by its competent authority (`CNI-04.c`).

  The proposal is kept.
- **A proposer's label** (such as "blocking" or "duplicate") reads as inert attributed text (D-01 0.3.4's `Attribution`; `CNI-04.b`), and changes nothing (`CNI-03.b`).

**CNIL-06. A link is never edited; a change is a new record.**
- **What a link names stays what it named:** when an end changes (a new accepted revision, a new claim version, a narrowing or challenge, a changed interface commitment), the existing link keeps the revision or hash it recorded, and the change is found through it (`WIS-06.c`).
- **The other end's owner reassesses:** a consumer, its premise (`CNI-07.c`, `AEV-10.j`); a dependent, its dependency's class and satisfaction (`CNI-03.b`, `CNI-03.g`); an interface's consumer, its binding (`CNI-02.d`).
- **A link carries forward:** it carries to each later accepted revision of the same work, unless that acceptance drops it explicitly, and the assessment of the new revision lists it (`WIS-02.d`). A link that an acceptance drops ends from that revision on. The record stays, as history (`CNI-01.d`).
- **A carried link keeps its standing:** a held link carried into a later revision stays held until `CNIL-02.b`'s taking-up, whoever accepted that revision.

**CNIL-07. A link survives lost, late and repeated messages.** The link is the store's record, never the message that announced it (as `WISR-07` states for A-40's links).
- Recording the same link twice gives one link.
- A late message never undoes a newer record (`CNI-05.b`).
- A consumer that missed a message reads the store before it progresses (`CNI-03.f`, `RX01-34`).

**CNIL-08. Recording a link is one step, and no link is needed where nothing relies.**
- **One step:** the agent names the kind, the ends and, for a claim or a result, the path. AEW's host code resolves the ends, computes the hash, reads the owner facts and writes the record (`WISR-08`). That includes held reliance (`CNIL-02.b`).
- **Nothing for ordinary work:** work with no request, dependency, interface or reliance records no link, and takes no extra step for this vocabulary (`CNI-01.e`).
- **Reliance is not optional:** a consequential decision that relies on something records its `consumption` at that decision, at an acceptance or held mid-work (`CNIL-02.b`), under `CNI-07.b`'s rule.

**CNIL-09. A request or a consumption may join any two work subjects the research slice needs, not only a Ticket and an inquiry.**
- **A `request`:**
  - the asker may be an Epic, a Story, a Ticket or an inquiry, and the requested work is an inquiry, or a PoC Ticket that an inquiry asks for (A-40);
  - **a requested inquiry is held under its asker's scope only when the asker is a Ticket** (`WISR-R03`). For any other asker, it is accepted through W11, from G3.
- **A `consumption`:** the consumer may be an Epic, a Story, a Ticket or an inquiry. What it relies on may be:
  - a claim, or a PoC Ticket's result, cited by hash and path;
  - an admitted Knowledge item, at its content version;
  - a determination (`K01-22`, `K01-34`, `WIS-07.d`, `WIS-06.c`).
- **A design decision is the work's own:** recorded at the work's acceptance, or held mid-work (`CNIL-02.b`). The document that states it is cited by hash and path, as the decision's text. A document is never an end (`CNIL-R03`).
- **A Knowledge nomination is not an end.**
  - Its citation of a claim is K-01's own source relation, recorded and owned by K-01 (`knowledge-relation`).
  - The claim's listing shows it through K-01's records (`CNIL-04`).
  - A change to the claim reaches it through K-01's own source-change path and, for context delivered before acceptance, through `K01-10` and `P01-42` (`delivered-context`).

**CNIL-09.a** An inquiry that consumes another inquiry's claim follows the same rules as a Ticket that does.
- **When it is recorded:** with the inquiry's disposition, or mid-work. Either way it is the researcher's, and reads as held under the inquiry's accepted revision (`CNIL-02.b`).
- **What it records:** the claim, by hash and path. Its read shows the qualification recorded at consumption beside the current one.
- **A narrowing** of the claim reaches the consuming inquiry's authority (`WISR-02.b`, `WISR-06`).

## Interfaces

- **Reads.** **Candidate:** in D-01's next revision, with the shared read wire, matched with the wire track. Each kind reads as a D-01 0.3.4 `Link` relation, with its reverse:
  - **`consumption`:** the relation `claim`, `knowledge` or `determination`, by the consumed end. Its reverse, from a claim, is `ClaimData.premise_use_refs`, which needs the data schema A-40 names (the consumed hash, the consuming work's revision, the qualification at consumption, and held or accepted). From a work, the `claim`, `knowledge` and `determination` relations mean a consumption, distinct from an inquiry's own claims or a package's determinations. D-01's next revision says so, and adds the reverses from a Knowledge item and a determination, which `KnowledgeData` and `AssuranceData` lack;
  - **`dependency`:** the relation `depends_on`, with a new reverse. A held dependency reads through `WaitingData` (`cause: dependency`), and shows an `unclassified` or `contested` class;
  - **`interface_commitment`:** the relation `accepted_interface` (`WorkData.accepted_interface_refs`), with a new reverse;
  - **`request`:** a new relation, with its reverse;
  - **`proposed_impact`:** a new relation, if its read is selected for V-01.

  `dependency_conflict` is an admission's conflict (`effect-conflict`), not a link. Listings carry `MemberView`'s visibility (`CNIL-04`).
- **Commands.** **Candidate:** in O-01, with I-7. O-01 0.4 and 0.8 have no dependency record and no consumer-binding command. I-7 adds them, or carries them in `CREATE_PROPOSED_WORK`'s and `DECIDE_WORK_PROPOSAL`'s content, as A-40's links are carried:
  - a `request` or a `consumption` rides the decision it belongs to, with the typed asking work and accepted revision that A-40 already gives I-7;
  - a `dependency` and an `interface_commitment` ride the accepted revision or composition commitment that classifies them;
  - **three agent actions that protect nothing:** held reliance (`CNIL-02.b`), an `unclassified` or `contested` dependency on the agent's own work (`CNIL-01.b`), and a `proposed_impact`. I-7 classifies them.
- **Refusals:** the refusals of `CNIL-01.b`, `CNIL-02` and `CNIL-02.a` take their names in O-01's refusal registry with I-7.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **CNIL-Q01** | The vocabulary is closed (`CNIL-01`) | a record of no listed kind, sent through any command, is stored as a note or refused; no hold, admission, satisfaction or release follows from it at any point |
| **CNIL-Q02** | Every relationship Coordination acts on has an owner or a kind (`CNIL-01.a`) | every A-09 clause in which Coordination holds, admits, satisfies, releases or routes maps onto one of the five kinds or one of `CNIL-01.a`'s names, with none unmapped (`check_coverage.py`); each owned relationship reads from its owner's record; no link kind duplicates one (a `request` never makes a child, and a `consumption` never supersedes a determination); a conflict between concurrent effects is checked at admission, and never read from a stored link; a row mapped `conduct` is a clause over no relationship between subjects |
| **CNIL-Q03** | AEW's host code writes every link with its decision (`CNIL-02`) | each link names its kind, both ends, its recorder and its acceptance; a command naming another recorder, decider or acceptance is refused, naming the field; a link claiming an acceptance it was not recorded with is refused and changes nothing |
| **CNIL-Q04** | Ends resolve by content, within the recorder's view (`CNIL-02.a`) | with two visible subjects sharing a label, a link naming the label alone is refused; a label matching one visible and one hidden subject resolves to the visible one, and the refusal or result is the same as with the hidden one absent; a typed link naming an unaccepted revision, or bytes that do not match their hash, is refused; a `proposed_impact` naming a proposal at its digest is recorded |
| **CNIL-Q05** | A link conveys nothing (`CNIL-03`) | for each kind, recording it changes no grant, acceptance, classification, inherited obligation, evidence or lifecycle state of either end; only a `dependency` holds, and only an `interface_commitment` lets a consumer proceed, each under its owner's rule; an asker that needs an answer waits through a `dependency`, which none of an inquiry's six dispositions satisfies until the asker records its decision |
| **CNIL-Q06** | Links list from both ends, and leak nothing (`CNIL-04`) | from each end, every visible link reads with its kind, other end, recorder and acceptance; a link to an end the reader may not see is not listed and leaves no placeholder; a reader whose entitlement does not cover the domain sees "may be incomplete" whether or not a hidden link exists; a held link never reads as accepted; a claim lists the K-01 candidates citing it from K-01's records |
| **CNIL-Q07** | A proposal stays advisory (`CNIL-05`) | an agent's or a heuristic's `proposed_impact`, whatever its label, holds, cancels and satisfies nothing; with no proposal recorded, no subject reads as unaffected; a proposal leads to a typed link, a hold on a qualified assessment, or a scope or completion decision only through that owner's own decision, which cites it, and the proposal stays |
| **CNIL-Q08** | Links are never edited, and carry forward (`CNIL-06`) | after a new claim version, a narrowing or a changed interface commitment, each existing link reads what it recorded, and the other end's owner is listed for reassessment; a new accepted revision that does not mention a link keeps it; one that drops it explicitly ends it from then on, and the record stays |
| **CNIL-Q09** | Links survive the messages (`CNIL-07`) | recording the same link twice gives one; a late message for an older record leaves a newer one unchanged; a consumer that missed the message reads the link from the store before it progresses |
| **CNIL-Q10** | One step, and nothing for ordinary work (`CNIL-08`) | recording a link takes one agent command; reliance found mid-work is recorded in one agent command, with no operator decision, and is listed from what it relies on at once; an ordinary Ticket with no request, dependency, interface or reliance completes with no link and no step added; a decision that relied on a claim without recording its `consumption` cannot later offer the claim as justification until reconciled (`CNI-07.b`) |
| **CNIL-Q11** | The other ends work (`CNIL-09`) | a Story asks an inquiry, which is then accepted only through W11; a Ticket's in-scope inquiry is held under the Ticket; an Epic consumes a claim; a decision consumes an admitted Knowledge item at its content version, and a determination; a consumption of a Knowledge item whose current disposition does not support the use, or of a superseded determination, is refused or held, saying which; a Knowledge nomination citing a claim records no `consumption`, is listed from the claim through K-01's records, and is reached through K-01's path when the claim narrows; a design note that cites a claim becomes reliance only once the work records it |
| **CNIL-Q12** | An inquiry may consume another's claim (`CNIL-09.a`) | the `consumption` is recorded with the disposition or mid-work, reads as held, and cites the claim by hash and path; its read shows the qualification at consumption beside the current one; a narrowing of the claim reaches the consuming inquiry's authority |
| **CNIL-Q13** | An unclassified or contested dependency holds its own side (`CNIL-01.b`) | a dependency the accepted revision does not name, recorded by the dependent's own agent or by Coordination from canonical facts, holds only the dependent's restrictive-class effects; it holds nothing on the other end, satisfies nothing, and clears only on an authorized clarification; an agent's claim about another's work records only a `proposed_impact` |
| **CNIL-Q14** | Held reliance is recorded, and stays held (`CNIL-02.b`) | a held `consumption`, recorded mid-work or with a disposition, reads as held, never as accepted or as the operator's; it routes impact at once; it is refused as justification for assurance or dependent progression until the accepting authority takes it up, in its next acceptance's decision summary or by explicit reconciliation; carried into a later accepted revision, it stays held |
| **CNIL-Q15** | Waits that cannot end are found (`CNIL-03`) | a wait that cycles through a `request` and a `dependency` (a Ticket waiting on an inquiry that asks for a PoC Ticket depending on the first Ticket) is detected, and gets `CNI-03.h`'s accountable disposition; a harmless cycle of development or final-integration relationships is not reported as one |

## Scenarios

**CNIL-X01.** Given two visible artifacts that share a label, when a Ticket's acceptance cites one by its label alone, the `consumption` is refused, naming the ambiguous end, and the acceptance records no premise (`CNIL-02.a`).

**CNIL-X02.** Given a worker's heuristic that finds two Tickets alike and records a `proposed_impact` labelled "duplicate", nothing is cancelled or held. The Lead may raise it, but cancelling either Ticket stays its accepting authority's decision, through G3, which cites the proposal (`CNIL-05`, `CNI-04.c`).

**CNIL-X03.** Given a Story that asked an inquiry, and a Ticket in it that waits on the answer through a `dependency`, when the inquiry ends `REFUTED`, the Ticket still waits. It proceeds when the Story's owner records its decision on the answer (`CNIL-03`, `WISR-05`).

**CNIL-X04.** Given a claim consumed by a Ticket and by an inquiry, and cited by a K-01 candidate, when the claim's author narrows it, the Ticket and the inquiry are listed from the claim, each with the hash it consumed, and each owner reassesses. The candidate is reached through K-01's own path (`CNIL-04`, `CNIL-06`, `CNIL-09`).

**CNIL-X05.** Given a dependency that a newer accepted revision dropped explicitly, when a late message announcing the dependency arrives, nothing changes. The record shows the dependency ending at the newer revision (`CNIL-06`, `CNIL-07`).

**CNIL-X06.** Given a consumer building against an accepted interface commitment, when the provider changes the interface's content under the same name, the consumer's link still names the old commitment, and the consumer is listed for reassessment (`CNIL-06`, `CNI-02.b`).

**CNIL-X07.** Given an agent's command that records a link with "accepted by the operator" in its body, the command is refused, naming the field, and nothing is recorded (`CNIL-02`, `WISR-09`).

**CNIL-X08.** Given an agent that wants to record "inspired by" between two Tickets, there is no such kind: it is routed as a note, and nothing holds or waits on it (`CNIL-01`).

**CNIL-X09.** Given a reader who may not see one of a claim's three consumers, the claim's listing shows two consumers and says it may be incomplete. A reader with the same entitlement over a claim with only two consumers sees the same words (`CNIL-04`).

**CNIL-X10.** Given a worker on Ticket A who finds that A's publish step depends on Ticket B's fix, which A's accepted revision does not name, the worker records an `unclassified` dependency for A's own publish. A's publish holds, and nothing on B changes. A new accepted revision of A classifies it, or drops it (`CNIL-01.b`, `CNI-X35`).

**CNIL-X11.** Given the Lead choosing a parser library mid-work because claim C says it is safe, and writing a design note that cites C by hash and path, the Lead records a held `consumption` in one step. When C narrows, the Ticket is listed from C at once. At the Ticket's next acceptance, its decision summary shows the held reliance, and the accepting authority takes it up or leaves it held (`CNIL-02.b`).

**CNIL-X12.** Given a Ticket whose revision 3 consumed claim C, when the operator accepts revision 4 to fix a typo in its criteria, the consumption carries to revision 4, and a later narrowing of C still reaches the Ticket (`CNIL-06`).

## Rulings

**CNIL-R01. The vocabulary is closed, at five kinds.** It closes the kinds a link record may carry, not every relationship. Every fact has one owner, and `CNI-04.c` already makes every untyped relationship advisory. An open vocabulary would let a new label become a hold, which is the case of a worker relabelling a required dependency advisory (`CNI-X35`). The closure keeps `CNI-X35`'s protective half through `CNIL-01.b`. The relationships other owners record are named (`CNIL-01.a`), and `CNIL-Q02` checks mechanically that every A-09 clause maps onto a kind or an owner. A sixth kind needs an amendment.

**CNIL-R02. Relationships other contracts own are pointed at, not defined.** Each one in `CNIL-01.a`'s list has an owner, and restating one here would give it two. A conflict between concurrent effects is no link at all: `CNI-03.g` checks it when the effect is admitted, so a stored link would go stale.

**CNIL-R03. A document is a decision's text, never a link's end.** A design note in the repository is cited by hash and path as the text of a decision the work makes. Its reliance becomes a link once it is recorded under that work, at an acceptance or held mid-work (`CNIL-02.b`).
- **This departs from the research study,** whose specimens' consuming records were design documents and designer decisions. The study observed where reliance was written down. This position records it against the work, because only a WIS subject can be listed, reassessed and reached when the claim changes (`WIS-07.d`).
- **What the study observed is kept:** the document stays cited by hash and path as the decision's text. Only where the reliance is recorded moves.
- **Making a document an end would need an identity of its own.** That is the designer's reading of A-40's refusal of a seventh identity (`WISR-R01`), extended from claims and inquiries to documents.
- **The cost to an agent is one step,** so the document path gains nothing by going unrecorded (`CNIL-R08`).

**CNIL-R04. Knowledge reliance runs from a decision to a Knowledge item, and K-01 reads it under its own name, with its standing.** K-01 names that relation `accepted_premise_use` (A-13, section 3). It is the store's `consumption` from a decision to an admitted Knowledge item at its content version: one record with one owner (`CNI-07.b`, `K01-34`), which K-01 reads. K-01 reads each with its standing, accepted or held, and a held one never reads as accepted (`CNIL-Q14`). The item's current disposition is checked when the link is recorded (`CNIL-02`, `K01-22`). A nomination's citation of a claim is K-01's own source relation, and never a `consumption`. That keeps an agent's candidate from reading as accepted reliance, and takes nothing from K-01. The Knowledge studies support it: dispositions target exact versions, and citations do not add up to independent support.

**CNIL-R05. Ends resolve by content, not by label.** This is the research study's finding: the minimal durable link is a hash and a path, and a label can name the wrong artifact (`CNIL-02.a`). `CNI-02.b` says the same for interfaces.

**CNIL-R06. Dependencies and interface commitments keep their adopted rules, and this position adds common rules to them, which the wire track builds.** The build is:
- in O-01, a dependency record and a consumer-binding command, which I-7 adds;
- in D-01's next revision, the reverse relations, plus a relation for `request` and for `proposed_impact`;
- for both kinds, the store records, named refusals, two-way listing and never-edited records that `CNIL-02`, `CNIL-02.a`, `CNIL-04` and `CNIL-06` require.

"Not covered" lists the same.

**CNIL-R07. A `request` asks research a question, or asks for a PoC.** The requested work is an inquiry, or a PoC Ticket an inquiry asks for. One piece of engineering work asks another through decomposition (`WIS-03.a`), a `dependency` (`CNI-03.b`), a scope change, or AEV's reassessment request, never through a `request`. That keeps one path for each kind of ask.

**CNIL-R08. The posture: the vocabulary costs ordinary work nothing, and reliance one step.** The governed path must be the easiest (the security depth reset, point 7). Work with no reliance records no link (`CNIL-08`). Reliance found mid-work is one step with no operator decision (`CNIL-02.b`), so an unrecorded design note saves an agent nothing.

**CNIL-R09. An agent's own unclassified dependency is a self-restriction.** Recording it holds only the recorder's own work's effects. So it loosens no authority, and no agent alone holds another's work (`CNIL-01.b`, `CNI-05.d`).

## Backlog

**CNIL-B1.** Links across projects, under the sharing groups of `K-DEC-04`: a `consumption` of another project's claim. Not before the sharing groups are built.

**CNIL-B2.** The unattended mission's episodes and report (`WISR-B2`), in the mission's own position (STG-18).

**CNIL-B3.** Withdrawn in revision 2. A wait on an answer is a `dependency` (`CNIL-03`), and `CNI-03.h`'s detection is the gate check `CNIL-Q15`.

## Not covered

- **The wire,** with the build `CNIL-R06` lists:
  - O-01's commands come with I-7: a dependency record, a consumer-binding command, and the three agent actions;
  - D-01's reads come with the shared read wire, matched with the wire track: the reverse relations, two new relations, and `premise_use`'s data schema.
- **Knowledge admission:** K-01's, and not in V-01 (`00-governance/decisions/2026-10-25-operator-selection-before-I-7.md`, choice 1, workspace commit `a8a5efc`).
- **The unattended mission:** `CNIL-B2`.
- **The host settings layer for check commands:** designed beside I-7.
- **A-09's bytes:** unchanged. This position adds to them.

## Changes

- Revision 2.1 (2026-10-25): applies the quick check's three minors and four nits, with no further check (`CHANGES-r2.1.md`).
  - **Held reliance** becomes justification only when the accepting authority takes it up, and stays held when carried (`CNIL-02.b`, `CNIL-06`, `CNIL-09.a`).
  - **A consumed Knowledge item or determination** is checked when the link is recorded (`CNIL-02`).
  - **A held question** is its issuer's (`CNIL-01.a`).
  - **Five coverage rows** are tightened.
- Revision 2 (2026-10-25): answers round 1 (`CNIL1`, 18 findings) and the designer's own item (`CHANGES-r2.md`).
  - **The closure:** it covers the kinds a link may carry. Owned relationships are listed, with A-09's coverage (`CNIL-01`, `CNIL-01.a`, `CNIL-Q02`).
  - **New rules:** the unclassified or contested dependency (`CNIL-01.b`) and held reliance (`CNIL-02.b`).
  - **Changed rules:**
    - a proposal's three routes (`CNIL-05`);
    - a nomination is no end, and Knowledge items and determinations can be consumed (`CNIL-09`, `CNIL-R04`);
    - honest wire reads (Interfaces, `CNIL-R06`);
    - no placeholders for hidden ends (`CNIL-04`, `CNIL-02.a`);
    - a refusal for a named decider (`CNIL-02`);
    - links carry forward (`CNIL-06`);
    - W11 for non-Ticket askers (`CNIL-09`);
    - held or accepted in listings (`CNIL-04`);
    - one table of ends;
    - waits are dependencies, with `CNIL-Q15`;
    - the look-ups in full.
- Revision 1 (2026-10-25): the first text. Before the pack was sent, it placed holds and effect conflicts among the owned relationships.
