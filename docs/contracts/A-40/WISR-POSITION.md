<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-40
source: 30-stages/STG-16-WIS-research-statements/adopted/wisr-r2.2/WISR-POSITION.md
source-sha256: 5e3d7e0c6a46a55027997b9a7af634ba242bff68687863168450991e8877a6e4
edits-sha256: none
-->

# WIS's research statements: completion from an answer, claim artifacts, and the Ticket and inquiry links (PROPOSED, revision 2.2)

**Namespace:** `WISR-`
**Status:** proposed, revision 2.2. It amends A-08 (WIS, the work-identity and scope contract) by addition: three statements A-08 does not make, which the rest of research's selection builds on. No adopted byte changes, and no WIS rule changes its meaning.
**Authority:** the operator's decisions:
- 2026-10-24 (`00-governance/decisions/2026-10-24-operator-first-selections-research-maps-knowledge.md`): flag 1, research gets its own path; research's minimum slice in V-01; and its "Order" line, which puts these three statements before CNI fixes its link vocabulary;
- 2026-10-25 (`00-governance/decisions/2026-10-25-operator-wire-track-ahead-of-publication-tooling.md`): the wire track's design starts now, and this is its first step.

**Threat model:** the operator's decision of 2026-10-19, as the security depth reset of 2026-10-24 narrows it: only what a contained agent can reach on its own counts.
**Research consulted:** `tools/research_index.py lookup`, run on each ID this position serves:
- `RX01-01`, `RX01-03`, `RX01-04`, `RX01-30` and `RX01-34`: none. The index files the study below under A-03's and WIS's requirements and RX-01's decision points, not under A-16's own IDs.
- `WIS-01.c`, `WIS-01.d`, `AEW-FR-40.a`, `AEW-FR-40.e`, `CNI-07.a` and `RX-DEC-01`: one study, `software-research-workflow-2026-10-15` (`private:software-research-workflow-2026-10-15/`, partly adopted). What this position takes from it:
  - an inquiry is a work unit that forces no Epic, Story or Ticket lifecycle, and no seventh identity is needed (pass 2, section 3 and section 4, case (b));
  - a research branch's result returns to the inquiry by hash, and accepting it as production is a separate engineering path (pass 2, section 4, case (c));
  - a non-PASS outcome is a complete research outcome, and a capped or non-discriminating instrument is a finding about the instrument, not the subject (pass 2, section 7, item 2);
  - the minimal durable link is a hash and a path, checked by content, not by label (pass 2, section 3, Coordination);
  - its deferred item, which this position is: Work Identity states answer-derived completion, claim artifacts as packages and two link kinds before any research guarantee is written (pass 2, section 7, "Critical missing consumer guarantees").

  Where this position departs from it, `WISR-R02` says why. `WISR-R04` takes up its note that no specimen had a Ticket as the asker.
- Flag 1 (STG-12's trace, `FLAGS.md`): none.

**Files:** this file. The stage's `STAGE.md`, `FINDINGS.json`, `CHANGES-r2.md`, `CHANGES-r2.1.md`, `CHANGES-r2.2.md`, `ADOPTION-PROPOSAL.md`, `reviews/` and `handoff/`.

## What the adopted text already decides

- **Research has work identity of its own:**
  - an authorized inquiry is referenceable work, with no mandatory Epic, Story or Ticket membership, no predetermined deliverable and no engineering completion lifecycle (`WIS-01.c`, `AEW-FR-40.a`);
  - work kinds share reference, lineage and scope semantics without sharing one progress machine or acceptance outcome (`WIS-01.d`);
  - an inquiry is accepted with its question, boundaries and governing sources (`RX01-01`), and refined within them without a new revision (`WIS-02.e`, `RX01-02`).
- **Its outcomes are its own:**
  - supported, refuted, limited, unresolved, deferred and stopped stay reportable without translation into PASS or FAIL (`RX01-03`, `AEW-FR-40.c`, `AEW-FR-40.e`);
  - three statements stay apart: the inquiry's disposition, a claim's qualification, and a hypothesis's conclusion (A-03, section 2, point 1); so do evidence qualification and experiment disposition, and none is inferred from another (`WIS-05.f`);
  - open questions keep a next check, an owner or a reason to stop (`RX01-09`, `AEW-FR-40.f`), and grounds are attributable at proportionate cost (`RX01-04`);
  - interrupted or exhausted research keeps its progress, unknown outcomes, residual effects and operator-relevant decisions, without a false termination or self-renewing authority (`CNI-07.e`, `RX01-21`, `RX01-29`), and cost reads as measured, estimated or unavailable (`RX01-27`).
- **Claims:**
  - A-03 leaves claim, research-artifact and experiment identity, and ordered determinations, to Work Identity, and warns against making every hypothesis a package by assertion alone (A-03, section 7, point 1);
  - claims are referenceable within their inquiries without becoming assignments (`WIS-05.b`), and name their proposition, subject and conditions (`WIS-05.c`);
  - an author's proposition, an observation and a competent judgment stay apart, and without competent qualification a claim is `NOT_ESTABLISHED` (`RX01-05`);
  - an experimental artifact is never an accepted production package (`WIS-04.f`);
  - research projections respect the reader's entitlement (`RX01-36`).
- **Ordering:**
  - a determination supersedes another only through an explicit resolution link, never by time or arrival (`WIS-06.b`, `CNI-05.b`);
  - history stays a truthful statement about its own subject (`AEV-06.g`, `WIS-06.d`), and evidence carries to a new subject only through an applicability assessment (`AEV-06.c`), with a reduced-impact claim corroborated as `AEV-01.g` asks;
  - a contradiction after consumption keeps the history and reassesses the dependents (`AEV-10.j`, `CNI-07.c`).
- **Links and waiting:**
  - a consumed claim's consumer is referenceable in reverse (`WIS-05.c`, `WIS-06.c`, `WIS-07.d`);
  - research-to-engineering relationships keep origin, limits and lineage, and convert nothing into a Ticket, convey no authority and transfer no proof (`WIS-05.g`);
  - a consuming decision records its premise when it is accepted (`CNI-07.b`);
  - a claim offered to engineering carries its version and whether a consumer accepted it as a premise (`RX01-30`);
  - a hand-off keeps "question answered" apart from "dependency satisfied", and recovers from lost, late and repeated messages (`RX01-34`);
  - a dependency is classified from the accepted revision, satisfied from canonical facts and never from mere provider completion, and reconstructable from durable records (`CNI-03.b`, `CNI-03.c`, `CNI-03.f`);
  - an experiment inside an inquiry keeps both identities, and its result stays provisional (`RX01-19`).
- **Coordination** supports inquiries with no Epic, Story or Ticket, and never reads their dispositions as engineering completion (`CNI-07.a`).
- **Authority:**
  - WIS records referents and provenance; authorizing is ADC's (`WIS-07.a`);
  - the Lead may do proportionate fact-finding within its existing investigative authority (`ADC-03.a`), and diagnostics run without a Ticket (`HEB-04.b`);
  - permission to investigate is apart from permission to implement (`EW-U01.b`);
  - A-32 holds every WIS acceptance at G3 (`DECIDE_WORK_PROPOSAL`), and the Lead only proposes (`CREATE_PROPOSED_WORK`);
  - a limit is widened only as an explicit authority increase: A-39's `ISSUE_STANDING_POLICY`, from G3 (`I6-03`, `I6-R03`). Limits that are not standing policies have no issuance yet (`I6-B1`).
- **The wire today:**
  - D-01 0.3.4 reads `inquiry`, `research_claim`, `experiment` and `premise_use` as subject kinds, each reference with an optional package digest. Its claim read (`D01-0.3.4/GET /v1/read/research/claims/{claim_id}`) gives a claim's qualification, conditions, limits, evidence and premise uses. Its work read knows only Epic, Story and Ticket;
  - O-01 0.8 (A-39) is the current command wire, and its work kinds are Epic, Story and Ticket.

### What it leaves open

- **What completes an inquiry.** `WIS-01.c` says it has no engineering lifecycle, but not what its completion is.
- **Whether a claim's versions get a package's ordering.** `WIS-01.e` makes claims and packages distinct subjects, and `WIS-06.b` orders determinations, but no text makes a claim's bytes the subject a determination names.
- **The links between a Ticket and an inquiry.** No text names the request. The consumption is `CNI-07.b`'s premise, with no shape for the claim it cites, and nothing covers the other direction, an inquiry that asks for a PoC Ticket.

## The parts

| Part | What it is | Who writes it | Who reads it |
|---|---|---|---|
| An inquiry | WIS work of kind `inquiry`: its accepted question, boundaries and governing sources, and its revisions | its accepting authority's acceptance (ADC), or, inside a Ticket's scope, the Lead's record under that Ticket's acceptance (`WISR-R03`); recorded by AEW's host code | the researcher, the Lead, the operator, Coordination |
| Its disposition | the inquiry's completion: one of six, with its grounds and open questions | the researcher, for the first five; for `STOPPED`, the inquiry's authority, or AEW's host code carrying out that authority's decision (`WISR-02.b`) | everyone entitled to read the inquiry |
| A claim artifact | the immutable bytes stating one or more claims, at a path, identified by their SHA-256; with the artifacts it cites, kept the same way | the research author: an agent's file, an attributed proposition and never an owner fact | readers entitled to its inquiry, by hash (`WISR-03.b`) |
| A determination about a claim | a qualification, a challenge or a narrowing, naming the claim and its artifact's hash | its competent owner (`RX01-05`, `RX01-06`) | consumers |
| A request link | the asking work to the requested work | AEW's host code, at the requested work's acceptance or opening | both ends' owners, Coordination, the operator |
| A consumption link | the consuming work to what it consumed, by hash and path | AEW's host code, at the consuming decision's acceptance | both ends' owners, Coordination, the operator |
| The store | WIS's canonical source for every record above except an artifact's own bytes (`WIS-01.f`): host state, shielded from every agent | AEW's host code only | AEW's host code, and the reads it serves |

## Rules

**WISR-01. An inquiry is WIS work of its own kind.** Beside Epic, Story and Ticket, `inquiry` is a work kind with WIS's identity, accepted-revision and lineage semantics (`WIS-01.a`, `WIS-02.b`), with no mandatory parent (`WIS-01.c`), and with no Ticket state or engineering acceptance.
- Its accepted revision holds its question, its boundaries and its governing sources (`RX01-01`). Refining hypotheses inside them needs no new revision (`WIS-02.e`).
- A parent, where one is accepted, is `WIS-03.a`'s, and conveys nothing (`WISR-04.a`).
- No Ticket state, guard or transition applies to an inquiry, the Ticket machine's accept transition and its evidence-only guard among them.
- A refusal of an engineering step on an inquiry says that it is an inquiry, and names the step that applies instead.

**WISR-02. An inquiry's completion is derived from its answer.** An inquiry is open from its acceptance until its disposition is recorded, and its disposition, one of `RX01-03`'s six outcomes, completes it. The disposition answers the accepted question as a whole.
- **`SUPPORTED`:** the evidence supports an answer to the accepted question, within the conditions its claims state.
- **`REFUTED`:** the evidence refutes what the question tested. An answer of no is complete, never a failure of the inquiry (`AEW-FR-40.c`).
- **`LIMITED`:** an answer holds only within narrower conditions or coverage than the question asked, and its claims state those limits (`RX01-08`).
- **`UNRESOLVED`:** the evidence does not decide the question, including where an instrument was capped or could not discriminate. That is a finding about the instrument, never about the subject.
- **`DEFERRED`:** the work stops on a recommendation to resume later, with its reason and what would restart it.
- **`STOPPED`:** the work ended before an answer, by a decision of the inquiry's authority (`WISR-02.b`). What it found stays (`WISR-02.g`).

No verification PASS or FAIL, engineering acceptance or engineering completion (`EW-U08.h`) is needed to complete an inquiry, and completing one produces none.

**WISR-02.a** A disposition carries its grounds: the claim artifacts it rests on, by hash and path (`WISR-03`), or, for `DEFERRED` and `STOPPED`, its reason. Any disposition may list open questions, each with a next check, an owner or a reason to stop (`RX01-09`); `LIMITED` and `UNRESOLVED` list at least one. A disposition missing any of these is refused, naming what is missing, and the inquiry stays open.

**WISR-02.b** The researcher records any of the first five dispositions. `STOPPED` is recorded by the inquiry's authority, through its own command. **The inquiry's authority** is defined here, once:
- for an inquiry the operator accepted, the operator, whose stop goes through G3, as cancelling a Ticket does (`CANCEL_OR_REPLACE_TICKET`);
- for one held under a Ticket's scope (`WISR-R03`), both the Lead who opened it and the Ticket's accepting authority, either of whom may stop it.

AEW's host code records `STOPPED` in two cases only, naming the authority whose decision it carries out:
- at the end of a window the inquiry's authority set as its stop condition;
- when the Ticket scope an inquiry is held under ends (`WISR-R03`).

**WISR-02.c** A disposition is the researcher's attributed statement about the question as a whole, and is kept apart from three other statements (`WIS-05.f`, `AEW-FR-40.e`, A-03, section 2, point 1):
- each claim's qualification, which stays its competent owner's, `NOT_ESTABLISHED` until that owner acts (`RX01-05`);
- each hypothesis's conclusion, which stays in the claims that state it;
- each experiment's disposition.

None is read from, or sets, another. A read shows each beside the others, never one for another.

**WISR-02.d** No read, status or consumer maps a disposition to an engineering verdict or to engineering completion (`EW-U08.h`), in either direction: no disposition reads as PASS, FAIL, or an engineering work item's completion, and no engineering state completes an inquiry (`WIS-01.d`, `CNI-07.a`).

**WISR-02.e** A completed inquiry is reopened only as a new accepted revision (`WIS-02.b`). Its earlier disposition stays as history (`WIS-06.d`), and every link to its earlier claims is unchanged.

**WISR-02.f** Exhaustion holds; it never completes. When an inquiry reaches a budget or effect limit, its affected effects hold, as they do for a revoked grant (`RX01-26`), and it stays open (`CNI-07.e`).
- Attention goes to the inquiry's authority, which may stop the inquiry, and to the limit's owner.
- **A limit is widened only through its owner's own path,** never by the inquiry's authority as such and never through the inquiry: A-39's `ISSUE_STANDING_POLICY`, from G3, for a standing policy (`I6-03`, `I6-R03`); for a boundary in the inquiry's own accepted revision, a new accepted revision through its acceptance path (`DECIDE_WORK_PROPOSAL`, from G3; `WIS-02.d`); for any other limit, the issuance `I6-B1` waits for. Until that issuance exists, such a limit is not widened, and the inquiry's authority may stop the inquiry.
- Meanwhile the researcher may still record a disposition from what it has, and independent safe work goes on (`RX01-38`).
- AEW's host code acts on a budget only from a qualified meter reading. An estimate or an unavailable meter is shown as such, and stops nothing (`RX01-27`).

**WISR-02.g** A `STOPPED` keeps what the inquiry found:
- **its record:** every artifact it cited or declared, and every working artifact the researcher has listed, hashed and kept as cited artifacts are (`WISR-03.b`). They are read as the researcher could read them (`WISR-03.a`). Where the researcher's confinement no longer exists, nothing more is read, and the stop says so;
- each experiment whose outcome is unknown;
- the residual effects that HEB's observations record, or `NOT_ESTABLISHED` where none is qualified (`RX01-21`);
- the reserved decisions still pending and the approvals still needed (`CNI-07.e`, `RX01-29`).

**WISR-03. A claim artifact is the package of a research claim's versions.** A claim artifact is the immutable bytes that state one or more of an inquiry's claims, identified by their SHA-256 and found at a path. A claim keeps its own stable reference within its inquiry (`WIS-05.b`), and its versions take a package's identity and ordering through their artifacts' hashes, as successive packages do for one accepted work revision (`WIS-04.b`). So a claim's versions are distinguishable subjects (`WIS-01.e`), and a determination about a claim names the claim and its artifact's hash, and is ordered as a determination about a package is (`WIS-06.a`, `WIS-06.b`). A hypothesis is a package only through the artifact that states it, never by assertion (A-03, section 7, point 1).
- **A changed claim** is a new claim artifact, with a new hash, linked to the one it revises. The earlier bytes, and every determination about them, stay (`AEV-06.g`). Nothing carries from the earlier artifact to the new one without its own assessment (`AEV-06.b`).
- **Carrying forward:** a determination carries to a revising artifact through `AEV-06.c`'s applicability assessment. A claim whose statement is byte-identical in both artifacts is a qualified mechanical comparison in `AEV-01.g`'s sense, which the assessor may accept without redoing the claim. The assessor's acceptance covers the conditions the claim states, wherever they sit in the artifact, not only a span its author marked. **Candidate:** a claim artifact marks each claim's span, and AEW's host code hashes the spans too.
- **What AEW records with it:** with each citation, AEW's host code records the inquiry's accepted revision, which holds the governing sources in force (`RX01-01`, `AEW-FR-40.d`). A later change of a governing source then reads as a change of applicability, not as an error in the claim. Whether the artifact states what `RX01-05` and `RX01-08` ask of a claim is its qualification's to judge.
- **A package for identity and ordering only.** A claim artifact is never an implementation package or production input (`WIS-04.f`). `WIS-04.a`'s closure rule binds implementation and integration packages, so it does not bind a claim artifact. Its identity covers its own bytes and the artifacts it cites (`WISR-03.b`); whether that evidence is complete is its qualification's (`RX01-05`, `RX01-17`).

**WISR-03.a** The hash is AEW's, and AEW reads only what the citing agent could. When a disposition or a link cites an artifact by path, AEW's host code reads it only as the agent that names it could read it under its current confinement: through that agent's own view, with links resolved the same way. It then computes the bytes' SHA-256 and records both.
- **A path the agent could not read** is refused as unreadable. The refusal says nothing about the bytes or whether they exist, and nothing is hashed or kept.
- **An expected hash:** the agent may give the hash it expects. For a readable path, a hash that differs is refused, naming the hash of the bytes there.
- **At an acceptance:** a link recorded when a decision is accepted, such as the operator's acceptance through G3, cites artifacts already kept, by hash. A path not yet kept is read as the agent that wrote it into the proposal could read it, never with the accepting principal's rights or the host's.
- **Candidate:** the read runs inside the citing context's own sandbox.

**WISR-03.b** The bytes of every cited artifact, and of the artifacts it declares it cites, stay retrievable by their hash for as long as anything cites them, whatever later happens at the path. Each declared artifact is read under `WISR-03.a`. A kept artifact is served only to a reader entitled to read its inquiry, as D-01's reads are (`RX01-36`). **Candidate:** AEW's host code copies them into its evidence store when they are first cited, and the citation step takes an optional list of the artifacts the claim artifact cites, so it stays one step.

**WISR-03.c** A consumer reads by hash. A consumer that relies on a cited claim reads its bytes by their hash (`WISR-03.b`); a label, a title or a path alone never identifies a claim.
- **Not established** applies only when the bytes cannot be retrieved by their hash, or what is retrieved does not match it (`RX01-30`, `RX01-38`). The mismatch is shown.
- **A path whose bytes now differ** reads as a newer artifact at that path: a new subject (`WISR-03`). It reaches the claim's consumers for reassessment only through a revision link (`WISR-03.d`) or a determination that names the consumed claim (`WISR-06`), never through the edit alone.

**WISR-03.d** An author revises a cited claim, or asks for its withdrawal, in one step, with no reopen (`RX01-06`). The revised artifact is cited, and read, under `WISR-03.a`. AEW's host code records the revision link from the earlier artifact to the new one, or the withdrawal request, and the change reaches every consumer through `WISR-06`'s reverse listing (`CNI-07.c`, `RX01-32`).
- The inquiry's disposition stays as recorded. A read shows beside it that a claim it rests on was revised, or that its withdrawal was asked.
- The claim's qualification stays its owner's (`RX01-05`). A withdrawal request is the author's statement, and does not by itself settle the claim.

**WISR-04. Two link kinds join a Ticket and an inquiry, each usable in either direction.**
- **A request link** runs from the asking work to the requested work: a Ticket asking an inquiry a research question, or an inquiry asking a Ticket for a PoC in the real project (the operator's selection of 2026-10-24).
- **A consumption link** runs from the consuming work to what it consumed: a Ticket relying on an inquiry's claim, or an inquiry taking back a PoC Ticket's result.

Each names both ends by their WIS identity and accepted revision, and is a record in the store (`WIS-01.f`), written by AEW's host code. An experiment inside an inquiry is linked by `RX01-19`, as before.

**WISR-04.a** A link conveys nothing beyond what it records: no authority, effect grant or acceptance; no parentage, inherited obligation or classification floor (`WIS-03.a`); no evidence or proof (`WIS-05.g`); and no coupling of lifecycles. Neither end's completion, cancellation or reopening changes the other. The one exception is an inquiry held under its asking Ticket's scope, which ends with that scope (`WISR-02.b`, `WISR-R03`): the acceptance it rests on ends it, not the link.

**WISR-05. A request link records who asked.** It is recorded with the requested work's acceptance or opening, as part of its provenance, and names the asking work and that work's accepted revision.
- **The request accepts nothing:** the requested work is accepted by its own competent authority, or held under the asking Ticket's acceptance (`WIS-07.a`, `WISR-R03`).
- **A Ticket-requested inquiry** is not the Ticket's child.
- **A PoC Ticket an inquiry requests** is engineering work, accepted and reviewed as any Ticket is. Engineering's own review is the check outside the benefiting researcher (the operator's selection of 2026-10-24).
- **Waiting on the answer:** where the asking work needs the answer before it proceeds, it waits on the requested work under Coordination's dependency rules (`CNI-03.b`, `CNI-03.c`, `CNI-03.f`). The requested work's completion answers the question, or returns the result, and never by itself satisfies an engineering dependency: the asker proceeds only by its own decision, which records what it consumed (`WISR-06`, `RX01-34`).

**WISR-06. A consumption link records reliance, citing a claim by hash and path.** When a consuming decision is accepted, it records each claim or result it relies on (`CNI-07.b`):
- the consumed claim's reference, or the PoC Ticket's result, cited by hash and path (`WISR-03`);
- the work it came from, at its accepted revision;
- the qualification the claim's owner records at that moment, which AEW's host code reads from the owner's record (`WISR-09`).

What follows from it:
- **Never edited.** A later version, challenge or narrowing of what a link cites is a new subject or a new determination. It is found through the link (`WIS-06.c`), and the consumer's owner reassesses (`CNI-07.c`, `AEV-10.j`).
- **Listed both ways:** from a claim, every work that consumed it, with the hash each consumed; from a work, everything it consumed and every work it asked (`WIS-05.c`, `WIS-07.d`).
- **Then and now:** a read shows the qualification recorded at consumption beside the claim's current qualification, never one for the other.
- **A PoC's result** rejoins the inquiry as evidence for its claims, cited by hash and path. It stays provisional, and is no accepted package for any other work until a separate engineering decision (`RX01-19`, `WIS-04.f`).

**WISR-07. A link survives lost and repeated messages.** The link is the store's record, never the message that announced it.
- Recording the same link twice gives one link.
- A consumer that missed a message reads the store before it progresses (`RX01-34`).
- A link that names an unknown end, an end at an unaccepted revision, or a claim whose bytes do not match its hash is refused, saying which, and changes nothing.
- An inquiry held under a Ticket's scope has no accepted revision of its own. For links, its revision is the Lead's record under the Ticket's accepted revision, which counts as accepted here, and reads as held, not accepted (`WISR-09`, `WISR-R03`).

**WISR-08. The governed path is the light one.** Recording a disposition, citing a claim and recording a link each take an agent one step: it names the inquiry, the claim and the path, and AEW's host code computes the hash, keeps the bytes and writes the record.
- **No inquiry is needed** for fact-finding inside a Ticket's accepted scope (`ADC-03.a`, `HEB-04.b`, `WIS-08.c`). An inquiry is for a question whose answer someone will rely on or revisit.
- **No more steps than the path it replaces:** from the question being raised (a proposal or a request) to its disposition, an inquiry takes no more agent commands or operator approvals than a non-mutating Ticket takes from its proposal to done.

**WISR-09. Owner facts are AEW's observation, never the caller's.** Every fact these records hold about who accepted, who decided, why a stop happened, or which qualification held is taken by AEW's host code from the authenticated command or from the owner's own record, never from a value the caller supplies (`WIS-01.f`). An agent supplies only the content of its own statement (a disposition, its reason and open questions, a claim artifact) and the references it cites: the inquiry, the claim, the path, the asking work, the artifacts it declares, and an expected hash if it wants (`WISR-08`). The accepted revisions of a link's ends are AEW's reads when the link is recorded.
- A command that names a decider other than its own authenticated principal is refused, saying so.
- An inquiry's read names its accepting authority, or the Ticket acceptance it is held under, and the basis (`WISR-R03`). An inquiry the Lead holds never reads as the operator's choice of research direction.

## Interfaces

- **Reads.** **Candidate:** in D-01's next revision, in the wire track:
  - an inquiry reads as work of kind `inquiry`, with a disposition field of its own, and with `WorkData.completion` absent or not applicable for that kind; the read names its accepting authority and basis (`WISR-09`);
  - a claim reads through the existing claim read, its `research_claim` reference carrying the artifact's hash as its package digest;
  - a consumption link reads as a `premise_use` reference. That kind has no data schema today; it needs one, carrying the consumed hash, the consuming work's revision and the qualification recorded at consumption;
  - the request link is new, and needs a reference kind of its own;
  - a work item's read lists what it consumed and what it asked, and a claim's read lists its consumers.
- **Commands.** **Candidate:** in the wire track, with I-7:
  - accepting an inquiry through the work-proposal path, with `inquiry` added to its work kinds;
  - the Lead's record of an inquiry held under a Ticket's scope, which accepts nothing new (`WISR-R03`). It is a new action, owned by WIS, whose expected origin class is `CURRENT_SUCCESSOR_GENERATION`, as `CREATE_PROPOSED_WORK`'s (A-32's W15) is; I-7's pass classifies it;
  - the inquiry's authority's stop (`WISR-02.b`), through G3 where the operator is that authority, as cancelling a Ticket is;
  - recording a disposition;
  - an author's revision of a cited claim, or its withdrawal request (`WISR-03.d`);
  - recording each link with the acceptance it belongs to. That needs a typed asking work and its accepted revision on `CREATE_PROPOSED_WORK` and `DECIDE_WORK_PROPOSAL`, whose `originating_instruction_ref` is an untyped string today, so the wire track amends those adopted types.
- **Refusals:** the refusals of `WISR-01`, `WISR-02.a`, `WISR-02.f`, `WISR-03.a`, `WISR-07` and `WISR-09` take their names in O-01's refusal registry, with the wire track.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **WISR-Q01** | An inquiry needs no Ticket (`WISR-01`; `WIS-01.c`, `AEW-FR-40.a`, `CNI-07.a`) | an inquiry is accepted, worked and completed `REFUTED` with no Epic, Story or Ticket created, and no Ticket state, guard or transition applies to it at any point; an engineering step tried on it is refused, saying it is an inquiry and naming the step that applies |
| **WISR-Q02** | Every disposition completes an inquiry, and none is a verification result (`WISR-02`, `WISR-02.d`; `WIS-01.d`, `AEW-FR-40.e`, `RX01-03`) | each of the six completes an inquiry; no read, status or projection shows one as PASS, FAIL or an engineering work item's completion (`EW-U08.h`); no engineering state completes an inquiry |
| **WISR-Q03** | A disposition carries its grounds (`WISR-02.a`; `RX01-04`, `RX01-09`) | a disposition with no claim artifact or reason is refused, naming what is missing; `LIMITED` or `UNRESOLVED` with no open question is refused; an open question listed on any disposition, `SUPPORTED` included, with no next check, owner or reason is refused; the inquiry stays open each time |
| **WISR-Q04** | AEW computes the hash, keeps the bytes, and reads only what the agent could (`WISR-03.a`, `WISR-03.b`) | a claim cited by path gets the SHA-256 of the bytes there; a wrong expected hash for a readable path is refused with the real one; after the file, or an artifact it declares, is edited or deleted, the bytes are still retrieved by their hash; a citation of a path the citing agent cannot read, directly or through a link, is refused as unreadable, saying nothing of its bytes, and nothing is hashed, kept or retrievable; a reader not entitled to the inquiry cannot retrieve a kept artifact |
| **WISR-Q05** | A changed claim is a new subject, and carries only by assessment (`WISR-03`; `WIS-01.e`, `AEV-06.b`, `AEV-06.c`) | after a claim's file changes, a determination about the earlier artifact does not apply to the new one by itself, and the earlier artifact keeps it; a claim whose statement is byte-identical in the revising artifact keeps its qualification through an applicability assessment that accepts that comparison |
| **WISR-Q06** | Determinations about a claim are ordered by resolution, never by arrival (`WISR-03`; `WIS-06.b`) | a challenge that narrows a claim artifact stays current when an older qualification of the same artifact arrives later; only a determination that names and resolves the challenge clears it |
| **WISR-Q07** | A consumer reads by hash, an edit is a newer artifact, and an author's revision reaches the consumers (`WISR-03.c`, `WISR-03.d`) | after the file at a cited path is edited, a consumer reads the consumed bytes by their hash and its reliance stands; the edit shows as a newer artifact at that path; only bytes that cannot be retrieved by their hash, or do not match it, make the use not established; after the inquiry is complete, its author's revision of a consumed claim takes one step and no reopen, lists the claim's consumers for reassessment, and the disposition shows that a claim it rests on was revised |
| **WISR-Q08** | A request conveys nothing (`WISR-04.a`, `WISR-05`) | a Ticket-requested inquiry has no parent, and inherits none of the Ticket's obligations, grants or effects; when the Ticket is cancelled or completes, an inquiry the operator accepted goes on as it was, and one held under the Ticket's scope ends `STOPPED`, its cause the asking scope's end; that held inquiry's claims can still be consumed, its revision reading as held, not accepted |
| **WISR-Q09** | An answered question is not a satisfied dependency (`WISR-05`; `RX01-34`) | a Ticket waiting on its requested inquiry sees the question answered when the disposition is recorded, and stays waiting until its own decision records a consumption |
| **WISR-Q10** | Reliance is found both ways, then and now (`WISR-06`; `WIS-05.c`, `CNI-07.b`) | from a claim, every consuming Ticket is listed with the hash it consumed; from a Ticket, every claim it consumed and every inquiry it asked; after a narrowing, every consumer of the narrowed artifact is listed for reassessment; a read shows the qualification recorded at consumption beside the current one |
| **WISR-Q11** | A PoC's result returns to its inquiry, and stays provisional (`WISR-05`, `WISR-06`; `RX01-19`, `WIS-04.f`) | an inquiry requests a PoC Ticket; the PoC's result is consumed by the inquiry by hash and path, and no other Ticket can take the PoC as an accepted package without a separate engineering decision |
| **WISR-Q12** | Links survive lost and repeated messages (`WISR-07`; `RX01-34`) | recording a link twice gives one link; a consumer that missed the message finds the link in the store; a link with an unknown end or a mismatched hash is refused, saying which, and changes nothing |
| **WISR-Q13** | The inquiry path is the light one (`WISR-08`, `WISR-R05`) | on the same build, an inquiry from the question being raised to its disposition takes no more agent commands or operator approvals than a non-mutating Ticket from its proposal to done |
| **WISR-Q14** | The trace's research gap closes, and flag 1 clears (`WISR-R05`) | at the build's pack, STG-12's trace claims `WIS-01.c`, `WIS-01.d`, `AEW-FR-40.a`, `AEW-FR-40.e`, and `CNI-07.a` for inquiries (its mission outcomes are `WISR-B2`'s), as served by the inquiry's records, and flag 1's four records as kept for `EW-U08.h`, with engineering's evidence-only tests unchanged |
| **WISR-Q15** | Owner facts are AEW's, and a stop is its authority's (`WISR-02.b`, `WISR-09`) | a researcher's `STOPPED` is refused, unless the researcher is the inquiry's authority; for a held inquiry, both the Lead and the Ticket's accepting authority can stop it; a command that names a decider other than its own principal is refused; the operator's stop of an operator-accepted inquiry is a G3 decision; a consumption records the owner's qualification at acceptance whatever the command says; an inquiry's read names its accepting authority and basis, and a Lead-held one never reads as the operator's |
| **WISR-Q16** | The disposition stands apart from the other statements (`WISR-02.c`; `WIS-05.f`, `AEW-FR-40.e`) | an inquiry with one hypothesis refuted, another unresolved and a probe that failed to run records its disposition for the question as a whole; each hypothesis's conclusion, each claim's qualification and the probe's disposition read as they are, and none sets, or shows as, another |
| **WISR-Q17** | Reopening keeps the history (`WISR-02.e`) | a completed inquiry reopened as a new accepted revision keeps its earlier disposition as history, and every consumption link to its earlier claims is unchanged |
| **WISR-Q18** | Exhaustion holds, and a stop keeps what was found (`WISR-02.f`, `WISR-02.g`; `CNI-07.e`) | at a qualified budget limit, the inquiry's affected effects hold and it stays open, and its researcher can still record a disposition; a Lead's widening of a held inquiry's limit is refused, and the inquiry stays held; a limit widens only through its owner's own path; an estimated or unavailable meter stops nothing; a `STOPPED`, by its authority or at the window it set, keeps the inquiry's record by hash, and names each experiment whose outcome is unknown, the residual effects (or `NOT_ESTABLISHED`), and the pending reserved decisions |

## Scenarios

**WISR-X01.** Given an operator-accepted inquiry into whether a parser approach can work, which a researcher answers no from source reading alone, the inquiry completes `REFUTED` with its claim artifact, and no Ticket exists (`WISR-01`, `WISR-02`).

**WISR-X02.** Given a Ticket whose plan needs to know whether a library is safe under its build flags, the Ticket requests an inquiry, which completes `LIMITED`: safe under two of the three flags. The Ticket's accepted plan records consuming that claim. When a later determination narrows the claim, the Ticket is listed for reassessment from the claim, and its consumption link is unchanged (`WISR-05`, `WISR-06`).

**WISR-X03.** Given an inquiry whose open question needs a PoC in the real project, the inquiry requests a PoC Ticket, which engineering reviews as any Ticket. Its result returns to the inquiry by a consumption link, and no other Ticket can use the PoC as an accepted package (`WISR-05`, `WISR-06`).

**WISR-X04.** Given a researcher who fixes a typo in its report after a Ticket consumed a claim in it, the Ticket's reliance stands on the consumed bytes, retrieved by their hash. The edited file shows as a newer artifact at that path, and reaches the Ticket only if a revision link or a determination names the consumed claim (`WISR-03.c`).

**WISR-X05.** Given a capped search that found nothing in the subsystem, the inquiry completes `UNRESOLVED`, with the cap and the total in its claim artifact, and not `REFUTED` (`WISR-02`).

**WISR-X06.** Given an inquiry the Lead holds under a Ticket's scope, which reaches its qualified budget limit half-way, its affected effects hold and it stays open. The Lead's attempt to widen the limit is refused; the operator may widen it through the limit owner's own path (`ISSUE_STANDING_POLICY`, from G3), and the Lead or the Ticket's accepting authority may stop the inquiry. Meanwhile its researcher records `LIMITED` from what it has (`WISR-02.f`).

**WISR-X07.** Given a Lead that checks a function's callers while planning its Ticket, no inquiry is opened, and none is asked for (`WISR-08`).

**WISR-X08.** Given a Ticket cancelled while an inquiry it requested runs, an inquiry the operator accepted goes on under its own acceptance. Only the operator may stop it, or AEW's host code at a window the operator set (`WISR-04.a`, `WISR-02.b`).

**WISR-X09.** Given an inquiry the Lead opened under a Ticket's scope, when the operator cancels that Ticket, AEW's host code records `STOPPED`, its cause the asking scope's end, and what it found stays. The operator may take the question on as a W11 inquiry (`WISR-02.b`, `WISR-R03`).

**WISR-X10.** Given an inquiry whose favoured hypothesis is refuted, a rival left unresolved, and a probe that never ran, the researcher records `UNRESOLVED` for the question, with an open question naming the probe. Each hypothesis's conclusion stays in its claims, and the probe's disposition stays its own (`WISR-02.c`).

**WISR-X11.** Given a researcher that cites, as its claim artifact, a file outside its own sandbox's view, the citation is refused as unreadable, and nothing is hashed or kept (`WISR-03.a`).

## Rulings

**WISR-R01. No seventh identity: an inquiry is a work kind, and a claim's versions take a package's identity and ordering through their artifact.** The study found that an inquiry fits WIS's existing work identity, and that a claim artifact is the research analogue of a package (pass 2, section 3). It left open whether a claim is a package or needs an identity of its own. A claim keeps its own reference, and its versions are packaged by their artifacts' hashes: that gives them AEV's ordering (`WIS-06.b`) with no new authority or store. D-01 0.3.4 already models it so, as a `research_claim` reference with a package digest, and A-03 leaves exactly this to Work Identity (section 7, point 1).

**WISR-R02. The six dispositions are `RX01-03`'s words, not AEV's terminals.** The study proposed reusing AEV's terminal vocabulary for research outcomes. `RX01-03`, adopted after it, chose the six and keeps research out of PASS and FAIL, so this position follows the adopted text.
- **Beside A-03's three statements** (section 2, point 1): the six are the inquiry's disposition, A-03's first statement. A-03 gives a hypothesis's conclusion some of the same words (supported, refuted, unresolved, deferred); `WISR-02.c` keeps the two apart, and the disposition answers the question as a whole.
- **AEV's terminals** stay for what they already govern: an experiment's or a probe's own result, such as an invalid test (`AEV-07.b`).
- **The study's point about instruments** holds within the six: a capped or non-discriminating instrument gives `UNRESOLVED`, or `LIMITED` for what it did cover, never a finding about the subject.

**WISR-R03. Accepting an inquiry is ADC's, and an in-scope inquiry accepts nothing new.** WIS records an acceptance and never makes one (`WIS-07.a`). A-32 holds every WIS acceptance at G3 (`DECIDE_WORK_PROPOSAL`), and the Lead only proposes.
- **Inside a Ticket's scope:** an inquiry a Ticket asks for, whose question and effects stay inside that Ticket's accepted scope and delegated effects, is the Lead's fact-finding (`ADC-03.a`, `HEB-04.b`).
  - The Lead's record opens it under that Ticket's acceptance. Its accepting authority is whoever accepted the Ticket, and its basis is `ADC-03.a` with the Ticket's accepted revision.
  - It accepts nothing new, so it needs no operator decision, and moves nothing from G3 to the Lead.
  - Its authority is both the Lead and the Ticket's accepting authority, and either may stop it (`WISR-02.b`). Neither widens its limits through it (`WISR-02.f`).
  - It ends when the Ticket is cancelled, replaced or completes. A new accepted revision of the Ticket is assessed for it as for the Ticket's grants (`WIS-02.d`), and where that assessment finds it outside the new scope, it ends the same way. In either case the operator may take the question on under W11.
- **Every other inquiry,** standalone, or needing effects or a reserved decision beyond the asking Ticket's, is the operator's choice of research direction: A-32's W11, `CHOOSE_RESEARCH_DIRECTION` (origin class `OPERATOR_ORIGIN_G3`), which I-7 wires.
- **The rest of RX-01's selection** confirms the commands before I-7, with `RX-DEC-01`.

**WISR-R04. The request link is composed, not observed.** No specimen in the study had a Ticket as the asker (pass 2, section 4, case (b)), so the request link records only what a consumer needs: who asked, at which revision. V-01's research slice runs it first. If that run shows the link short of what a consumer needs, it is revised from that evidence.

**WISR-R05. The inquiry path is no heavier than the flagged one, so flag 1 clears by use, and nothing is removed.** The posture's question (the security depth reset, point 7) is whether the governed path is the easiest way for an agent. Today an investigation completes through a non-mutating Ticket's states, which flag 1 holds contrary to `WIS-01.c`. If the inquiry path cost more, agents would keep taking the Ticket path, so `WISR-08` and `WISR-Q13` make the inquiry path no heavier, measured from the question being raised.
- The flag's four records stay for engineering's evidence-only units (`EW-U08.h`). Nothing new is built on research as a Ticket (the operator, 2026-10-24).
- **The measure:** V-01's research-slice run records which path each investigation took, as the operator's data. The flag is reported cleared from that count, beside `WISR-Q01` and `WISR-Q14`, not from the trace alone.

**WISR-R06. The hash is SHA-256,** the form of D-01 0.3.4's package digest: `sha256:` and 64 hexadecimal digits. Its source is adopted (A-25).

## Backlog

**WISR-B1.** Links with other ends: a Story or an Epic, an inquiry consuming another inquiry's claim, a design decision, or a Knowledge nomination. CNI's link vocabulary, the wire track's next design step after this one, takes them.

**WISR-B2.** An unattended mission's episodes and report (`RX-DEC-03`, `WIS-05.h`), with `CNI-07.a`'s mission outcomes, in the rest of RX-01's selection.

**WISR-B3.** The qualification profiles for claims at each consequence level (`RX-DEC-04`).

## Not covered

- **The wire.** O-01 0.8 (A-39), the current command wire, has work kinds Epic, Story and Ticket only, and no command to record a disposition or a link. D-01 0.3.4's work read has the same three kinds and an engineering completion field. The wire track adds what the Interfaces list:
  - an inquiry's work kind and disposition field;
  - the Lead's record of an in-scope inquiry, the inquiry's authority's stop, and an author's revision step;
  - a data schema for `premise_use`, and the consumed and asked lists;
  - a request link's reference kind, and a typed asking work on the adopted I-5 types `CREATE_PROPOSED_WORK` and `DECIDE_WORK_PROPOSAL`, which the wire track amends;
  - the refusals' names.

  The commands come with I-7, which follows O-01 0.8 and carries its erratum E-1. The reads come with the register's hold group for the shared read wire, which is matched with the wire track.
- **CNI's link vocabulary:** fixed after this position, with these two link kinds native in it (the "Order" line of the operator's decision of 2026-10-24).
- **Experiments in contained scratch:** `RX01-14` and `RX01-19`, under `RX-DEC-02`'s selection, unchanged.
- **Unattended missions:** `WISR-B2`.
- **The as-built.** Investigations run today as non-mutating Tickets, and the knowledge pack's record kinds carry results of their own. The build's hand-off maps them to this position; nothing here adopts their shapes.
- **STG-12's trace:** at this position's adoption, the research gap's `closed_by` names it. The gap closes when the build serves `WISR-01` to `WISR-09`, as `WISR-Q14` shows.

## Changes

- **Revision 2.2 (2026-10-25):** the three nits of the check of WISR2-1's fix, which was CONFIRMED (`reviews/2026-10-25-WISR-check-revision-2.1.md`; `CHANGES-r2.2.md`), applied with no further check under the reset: `WISR-X06` names the limit owner's path (WISR3-1); `WISR-02.f` names a boundary in the inquiry's own accepted revision (WISR3-2); and `WISR-03.d` reads the revised artifact under `WISR-03.a` (WISR3-3).
- **Revision 2.1 (2026-10-25):** the answers to the quick check of revision 2 (`reviews/2026-10-25-WISR-check-revision-2.md`; every finding, in `CHANGES-r2.1.md`).
  - **`WISR-02.b`** defines the inquiry's authority once, and **`WISR-02.f`** widens a limit only through its owner's own path, never through the inquiry (WISR2-1; its fix gets one more quick check). `WISR-X06`, `WISR-Q18`, `WISR-R03` and the Interfaces' stop follow.
  - **`WISR-03.d`, new:** an author's one-step revision or withdrawal request (WISR2-2).
  - **Also:** `WISR-03.a` covers links recorded at an acceptance (WISR2-3); an in-scope inquiry ends when its Ticket completes, and has a held revision for links (WISR2-4); `WISR-02.g` keeps the pending decisions and defines its record (WISR2-5); and four nits in `WISR-09`, `WISR-Q04`, `WISR-03` and the Interfaces.
- **Revision 2 (2026-10-25):** the answers to round 1 (`reviews/2026-10-25-WISR-review-round-1.md`; every finding, in `CHANGES-r2.md`).
  - **`WISR-03.a` and `WISR-03.b`:** AEW reads a cited path only as the citing agent could, and serves kept bytes only to entitled readers (WISR1-1).
  - **`WISR-09`, new:** owner facts are AEW's observation; `WISR-02.b` gives `STOPPED` to the authority the inquiry is held under (WISR1-2).
  - **`WISR-R03`:** an in-scope inquiry is held under its Ticket's acceptance and ends with that scope (WISR1-3).
  - **`WISR-02.f` and `WISR-02.g`, new:** exhaustion holds, and a stop keeps what was found (WISR1-4).
  - **`WISR-03.c`:** a consumer reads by hash, and an edit is a newer artifact (WISR1-5).
  - **Also:** carry-forward and kept evidence in `WISR-03`; `WISR-02.c` keeps hypothesis conclusions and experiment dispositions apart; engineering completion in `WISR-02.d`; no mandatory parent in `WISR-01`; the Interfaces and "Not covered" list the wire delta; `WISR-Q13` measures from the question being raised; and the governing source is recorded with each citation.
  - **Gate and scenarios:** checks `Q15` to `Q18` and scenarios `X09` to `X11` are new, and `Q01`, `Q02`, `Q03`, `Q04`, `Q05`, `Q07`, `Q08`, `Q10`, `Q13`, `Q14`, `X04`, `X06` and `X08` change.
  - **From A-39:** O-01 0.8 is the current wire.
- **Revision 1 (2026-10-25):** the first text.
