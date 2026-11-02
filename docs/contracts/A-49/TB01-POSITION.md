<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-49
source: 30-stages/STG-24-I4B7-determination-producers-in-the-trust-basis/adopted/tb01-r4/TB01-POSITION.md
source-sha256: 211878604f7b34f0cc6304143904a4455318de01f66dfbd43279983be7435444
edits-sha256: none
-->

# TB01: the producers of determinations in a readiness's trust basis (PROPOSED, revision 4)

**Namespace:** `TB01-`
**Status:** proposed.
- **What it answers:** A-31's backlog `I4-B7` and `I4-B8`, which A-31's trim requires together, and A-28's `I2-B5`, which joins them.
- **How it amends:** it extends A-31's `I4-01c` and `I4-07` by addition, and A-31's frozen copy keeps its bytes.
- **A-31's governance clause** says a change to A-31's normative files needs a new pinned wire version, and that answering `I4-B7` is such a change. So the route is the operator's question at adoption (`TB01-R01`). No rule below depends on the answer.

**Authority:** the operator's decision to start I4-B7 (`00-governance/decisions/2026-11-01-operator-start-I4-B7.md`).
**Threat model:** the operator's G3 threat model (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`), under the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`).
**Research consulted:** none. `tools/research_index.py lookup` returned no hits for `I4-01c`, `I4-07`, `AEV-09.d`, `WIS-06.a`, `AEV-06.c`, `AEV-10.j` or `I2-B5`.
**Files:** this file, and the gate in three files:
- `verify_tb01.py`, derived from A-31's `verify_i4.py` (SHA-256 `973d7bf2b12e8266e13ce3f7d364a1ae898c50d18d22d90c74dc38bbeeca950f`), with its changes listed in its header;
- `tb01-cases.json`, the gate's snapshot;
- `verify_tb01_mutation_kill.py`.

The gate passes 324 named checks, A-31's included. All 27 mutants in the companion are killed, each on its own TB01 row.

## What the adopted text already decides

- **The basis reads the cited items.** A readiness's trust basis is the trust state of the producing lineage of every item its determinations cite, each read from the item's own attribution (A-31's `I4-01c`). A readiness states that basis (`I4-07`).
- **What a trust state is.** A producing lineage is named by its generation and the grant its producing invocation was admitted under. Its trust state is the generation's classification version, plus whether the grant lineage is revoked (`I4-01c`).
- **What a change in it does.** `APPROVE_INTEGRATION` and HEB's effect-time recheck compare every basis entry with ADC's current facts. Any change gives `ASSURANCE_STALE` until AEV reassesses (`AEV-10.j`). An unreadable state is the hold `CLASSIFICATION_UNAVAILABLE` (`I4-01c`, `I4-05`).
- **An untrusted contribution.** Where a readiness relies on an item whose producing lineage is revoked, AEV takes that contribution as untrusted, and the readiness does not count it as trusted evidence (`I4-07`, `AEV-09.d`).
- **Attribution and identification.** Every assurance-relevant observation keeps its producer's attribution (`AEV-05.a`). A qualified disposition identifies its package, and the obligations and evidence that support it (`AEV-06.a`). An item whose producer cannot be attributed is not trusted evidence (`AEV-09.d`, as `I4-01c` applies it). Corrected work needs no extra operator step for reverification already authorized (`AEV-09.f`).
- **Grants.** ADC governs grants, and A-07 establishes no new grant mechanism (A-07's scope).
- **The limit `I4-B7` names.** The basis does not read the producers of the determinations themselves (finding `I4C5-1`). Before W09 is activated, A-31's trim requires:
  - "the producing lineage of every determination the readiness rests on (WIS-06.b, WIS-06.c, AEV-02.a), and of every item those determinations cite";
  - that `I4-10`'s owed D-01 addition grows to match.
- **What `I2-B5` needs.** A cited item's lineages, and C15's lineage read, are every lineage in its attribution, because a rerun's attribution is a list of lineages (A-28's `I2-05`).
- **What `I4-B8` requires with `I4-B7`:** one attribution shape for every AEV and HEB record that names an actor, which D6 enforces; a cited check per path; and D6 run last (A-31's trim, finding `I4C5-2`).

## The parts

- **AEV** owns the determinations, the readiness and its trust basis. It alone writes them. The Lead and the operator read them through AEV's reads.
- **HEB** admits every producing invocation, and states the grant lineages each was admitted under. That statement is the attribution (`TB01-04`).
- **The producers** are the contexts whose work a determination records: a verifier, a reviewer, an adjudicator, an owner service. Each runs under a grant ADC issued. A producer writes nothing into AEV's records, and states nothing about its own attribution.
- **ADC** owns every grant and every trust state: classifications and grant revocations. AEV, CNI and HEB read them.
- **CNI's `APPROVE_INTEGRATION` and HEB's promotion** read the readiness and its basis, and compare the basis with ADC's facts. Neither writes either.

## Rules

**TB01-00. Precondition: A-31's `I4-01c` and `I4-07` hold as adopted, except where a rule here adds to them.** Nothing here narrows them.

**TB01-01. A readiness identifies every determination it rests on.** This is `AEV-06.a`'s identification, made explicit for determinations. The kinds:
- a per-obligation PASS (`WIS-06.b`);
- a hold's resolution (`I4-07`);
- an applicability assessment for carried-forward evidence (`AEV-06.c`);
- a dispute's disposition (`AEV-10.h`);
- a review's result (`AEV-05.b`, `AEV-06.g`).

A readiness that cannot name a determination it needs does not rely on it, and is not issued as qualified.

**TB01-01.a** A determination carried forward into the review is one the readiness rests on, exactly as one made in the current review is.

**TB01-01.b** A determination that a determination the readiness rests on cites as support it relies on (`AEV-06.a`) is itself one the readiness rests on, and the readiness identifies it.
- **Not support:** a link to a superseded or historical record, such as the link a re-establishing determination keeps to the one it replaces (`AEV-10.j`, `AEV-05.b`).
- **Read as current:** a citation of a superseded determination reads as the determination that superseded it (`TB01-06`).

**TB01-02. The trust basis covers the producing lineage of every determination the readiness rests on, and of every other item those determinations cite.** This is the trim's sentence, and it extends `I4-01c`'s "the lineages a readiness rests on". Each lineage comes from the determination's or the item's own attribution (`TB01-04`).

**TB01-02.a** A carried-forward determination is read as a live one. Its producer is in the basis, and so are the producers of the items it cites. Revoking any of them stales the readiness, as for a live determination. That removes the inconsistency `I4C5-1` names.

**TB01-02.b** The reach is fixed by identification, not by depth. The determinations are those `TB01-01` and `TB01-01.b` identify, through any chain of citation. The items are the non-determination items any of them cites. An item adds its own producers, and nothing it cites in turn.

**TB01-02.c** A finding, and a request's own record, are never basis entries, even where a determination cites them.
- A readiness relies on the determination that disposes of a finding, not on the finding's producer (`AEV-10.b`, `AEV-10.h`).
- A request is never evidence (`I4-01a`).

**TB01-03. Every lineage in an attribution counts.** This is `I2-B5`'s outcome.
- The basis has an entry for each lineage in each attribution it reads.
- `REFER_HELD_RESULT` reads every lineage in the result's attribution. If any is revoked, or any generation it names is newest-classified `TRUST_REVOCATION`, the result is `RESULT_FROM_REVOKED_LINEAGE`, as in `I4-01c`.

**TB01-04. One attribution shape, and whose fact it is.** Every AEV and HEB record that names an actor attributes its producer as a list of lineages. This answers `I4-B8`'s shape, and `I2-B5`'s list is that shape's content.
- **A lineage** is a generation and a grant that the record's production rests on: the producing invocation's admission, and, for a rerun, every lineage `I2-05` lists.
- **A producer outside any Lead generation's lineage** has no generation: an owner service, or an adjudicator under an independently authorized grant (`I4-03`). Its lineage is its grant alone. No generation's classification or end touches it, and only its grant lineage's revocation does.
- **An attribution is the admitting owner's fact:** HEB's statement of the grant lineages each producing invocation was admitted under (`I4-01c`). AEV copies it into the record. No producer supplies it, adds to it or removes from it.
- **The invocation is HEB's fact too:** the invocation through which HEB returned the producer's output, which HEB records on its return path. AEV copies that link into the determination with the attribution. No producer supplies it.
- **Roles are not attribution.** A role or eligibility a record also carries, such as a determination's eligible producer or a finding's reviewer, is not its attribution. The basis reads the attribution only. Eligibility itself (`AEV-02.a`) is outside this position (see "Not covered").
- **Candidate:** a field named `attribution` and a field naming the invocation on each such record, with HEB's admission and return records as their source.

**TB01-05. A determination whose producer cannot be attributed is not trusted evidence.** This is `AEV-09.d` and `AEV-05.a`, applied to determinations as `I4-01c` applies them to items.
- **A determination is unattributed** when any of these holds:
  - it names no attribution;
  - it names no invocation, or an invocation other than the one HEB's return path records as having returned it;
  - HEB records no return of it;
  - its attribution differs from HEB's admission record of that invocation.
- **What follows:** the readiness does not count it as trusted, and a readiness that needs it is not issued as qualified.
- **No exemption:** no determination is exempt because AEW's own code produced it (`TB01-R03`).

**TB01-06. A revocation stales the readiness, and an untrusted determination no longer satisfies its obligation.**
- **Stale:** a revocation of any lineage in the extended basis gives `ASSURANCE_STALE`, at `APPROVE_INTEGRATION` and at HEB's recheck, until AEV reassesses. An unreadable state is `CLASSIFICATION_UNAVAILABLE`, a hold.
- **Untrusted:** a determination whose producing lineage is revoked, or whose generation is newest-classified `TRUST_REVOCATION`, is taken as untrusted (`I4-07`, `AEV-09.d`). It no longer satisfies its obligation. A reissued readiness that needs it is not qualified until AEV re-establishes it.
- **Re-establishment, for every kind and route:** AEV re-establishes by a new determination of the same kind on the same subject, whose attribution is trusted. That is a new PASS on the obligation, a new resolution of the hold, a new applicability assessment, a re-adjudication, or a new review. The new determination supersedes the untrusted one, whether that was live, carried forward or cited. A readiness rests on the current determination only.
- **Under its kind's rules:** the new determination is made under its kind's adopted rules. A resolution is made under `I4-07`, linked to the hold's current version, and is refused where `I4-06` refuses one, as when the reviewer-independence row is unavailable. A re-adjudication names the finding version it disposes of. A refused one supersedes nothing.
- **Once:** a determination is superseded at most once, by a later determination of the same kind on the same subject, and AEV never reuses a reference.
- **Proportionate:** nothing is deleted or reopened. The superseded determination stays as a record (`AEV-05.b`, `AEV-06.g`). It is not rested on, and it and what it cites leave the basis. AEV re-establishes on its own path, with no operator step (`AEV-09.f`).
- **Items:** for an item a determination cites, `I4-07` applies as adopted. AEV judges whether the determination still holds without the untrusted item (`AEV-06.e`). This position does not change that.

**TB01-07. `I4-01c`'s list of what the determinations cite, and `I4-07`'s readiness line, are read with `TB01-01` to `TB01-06`.** A built AEV conforms to both texts together, as A-46 extended A-45's `O02-07.a`.

## Interfaces

- **No O-01 schema byte changes.** The trust basis is AEV's record, not an O-01 field (`I4-10`), so neither the selected command wire nor its action registry moves.
- **The D-01 addition that `I4-10` owes grows to match** (the trim):
  - on every item a determination cites: its attribution, a list of lineages, where `I4-10` says its producing lineage;
  - on a held-result read: its attribution, a list of lineages, where `I4-10` says its producing lineage;
  - on every determination the readiness rests on: its reference, its attribution, and the invocation HEB returned it through;
  - when `AssuranceData` gains the trust basis, each entry names its source (a determination, or an item a determination cites), that source's reference, and the lineage and trust state relied on. A lineage outside any Lead generation has a null generation and no classification version (`TB01-04`).

  This states the owed D-01 change. It is not a D-01 edit now.

## The gate

`verify_tb01.py` derives from A-31's `verify_i4.py`. Its header states the source hash and lists every change. TB01's own rows run first, on their own worlds. `verify_tb01_mutation_kill.py` requires each mutant to fail on the TB01 row that names its rule. `TB01-02.b`'s item limit is a stated fate: no item in the model cites anything (`TB01-B1`).

| Check | What it shows | Pass |
|---|---|---|
| **TB01-Q01** | The package's material is wholly inherited. A current-review PASS by a current-generation worker is revoked with its grant lineage (`TB01-02`). | `APPROVE_INTEGRATION` gives `ASSURANCE_STALE`, and HEB does not promote |
| **TB01-Q02** | The same case, with the current Lead root revoked, and separately with the producing generation classified `TRUST_REVOCATION`. | `ASSURANCE_STALE` in both cases; HEB does not promote |
| **TB01-Q03** | The same PASS, live and then carried forward, with its producer revoked; and a carried PASS whose cited item's producer is revoked (`TB01-01.a`, `TB01-02.a`). | both name the PASS and give the same outcome; the cited item stales the readiness |
| **TB01-Q04** | An attribution of two lineages, where only the second is revoked (`TB01-03`). | the readiness is stale, and `REFER_HELD_RESULT` gives `RESULT_FROM_REVOKED_LINEAGE` |
| **TB01-Q05** | A determination with no attribution (`TB01-05`). | it is not counted as trusted, and a readiness that needs it is not qualified |
| **TB01-Q06** | After `TB01-Q01`, AEV reassesses with nothing re-established. Then it re-establishes by a superseding PASS from a trusted producer, and reassesses again. This is run twice: once where the new PASS links the one it replaces, and once where it also cites it (`TB01-06`, `TB01-01.b`). | first not qualified, `ASSURANCE_NOT_CLEAR`; then admitted, resting on the new PASS only, with the old one kept as a record and out of the basis |
| **TB01-Q07** | Three revocations the readiness does not rest on: a worker that produced nothing cited; a verifier whose determinations this readiness does not rest on; and a Lead generation's classification and end, for a readiness resting on a producer outside it (`TB01-04`). A fourth: the reviewer of a finding that a dispute's disposition overturned (`TB01-02.c`). | the readiness stays current: the basis does not over-reach, and holds no finding's reviewer |
| **TB01-Q08** | D6's converse, record by record, run last, on every fixture's state, X20's included (`TB01-04`, `TB01-02.c`). Every part of AEV's and HEB's state is either a declared record collection or a declared non-record. Every record carries the one attribution shape, and nothing outside the declared records names an actor. The declared collections split three ways: cited sources, request and review records, and HEB's admission records. Every cited source is cited, path by path. A-31's PASS ledger, a declared non-record, stays empty, and the walk reads tuples as lists. | each check holds, with planted controls killed |
| **TB01-Q09** | A readiness identifies its determinations (`TB01-01`). One it cannot name is not in its basis, and a readiness that needs it is not qualified. | as stated |
| **TB01-Q10** | A-31's checks run and pass in the derived script. The checks whose expression differs from the frozen `verify_i4.py` are exactly the listed ones, compared by their source. | exact match |
| **TB01-Q11** | Every determination kind (`TB01-01`) on every route: live, carried forward, and reached through another determination's citation (`TB01-01.b`). Each cell is a fixture, or a stated fate. Each fixture then re-establishes (`TB01-06`). Two more cases: a re-establishing resolution that needs the unavailable reviewer-independence row; and a planted superseder of another kind. AEV's refusal to supersede twice or reuse a reference is checked too. | a fixture revokes the producer and gets `ASSURANCE_STALE`; the reissued readiness is not qualified; AEV's superseding determination of the same kind then admits it, the old one kept as a record and out of the basis. The resolution needing the unavailable row is `POLICY_UNAVAILABLE`, supersedes nothing, and stays not qualified; the other-kind superseder is not followed. The one fate is a hold's resolution carried forward, which never happens (`I4-01b`) |
| **TB01-Q12** | Six determinations (`TB01-04`, `TB01-05`): one whose attribution is HEB's admission record; one that substitutes it; one that narrows it; one that names no invocation; one that names another admitted invocation, with that invocation's lineages, after the worker HEB returned it through is revoked; and one HEB records no return of. | the first is admitted; the other five are unattributed, so not qualified |

## Scenarios

**TB01-X01.** The material is wholly inherited from generation 0. A gen-1 worker makes the current review's per-obligation PASS, and the readiness is `qualified_clear`. ADC revokes that worker's grant lineage. Under A-31 alone, W09 stays admitted and HEB promotes. Under TB01, the basis holds the PASS's producing lineage, so `APPROVE_INTEGRATION` gives `ASSURANCE_STALE`. A reassessment is not qualified until AEV re-establishes the obligation with a trusted producer (`TB01-02`, `TB01-06`, finding `I4C5-1`).

**TB01-X02.** The same PASS is carried forward from an earlier review instead, citing that review's evidence. The readiness names it, and revoking its producer, or an evidence item's producer, stales the readiness (`TB01-01.a`, `TB01-02.a`). AEV re-establishes by a new PASS that supersedes the carried one, and the carried one leaves the basis (`TB01-06`).

## Rulings

**TB01-R01.** The route is the operator's question at adoption, as U-01's Q2 was for A-45.
- **The question:** TB01 extends A-31 by addition, and no O-01 byte moves. Does that answer A-31's governance clause, or is a new pinned wire version cut as well?
- **Recommended: no new version.** It would re-pin identical wire bytes under a new number.
- **The alternative stays mechanical:** cut a new O-01 version at adoption, equal to the current selected wire apart from its version, with TB01 as its profile. The current selected wire is O-01 0.9 (`00-governance/decisions/2026-10-25-operator-adoption-I7-o01-0.9.md`).
- **Under either answer, TB01 binds every endpoint that admits `APPROVE_INTEGRATION`, at any wire version** (`TB01-07`).

**TB01-R02.** The reach is set by identification (`TB01-02.b`). The readiness identifies every determination it rests on, whatever the chain of citation, so the basis follows a history the readiness names. An item adds only its own producers, as `I4-01c` reads it, and the trim asks for no more.

**TB01-R03.** No determination is exempt as host code.
- **The authority:** ADC governs every grant, and A-07 adds no grant mechanism (A-07's scope). So every producer, AEW's own owner services and protected observers included, holds an ADC grant that ADC can revoke.
- **No producer without a grant:** no adopted text defines one, so the adopted rule applies as written. A producer that cannot be attributed is not trusted (`TB01-05`).
- **What is owed:** an adopted text that gives AEW's own producers their ADC grants (`TB01-B3`).
- **The gate's fixture:** its service grants stand in for that text. They are not the authority.

**TB01-R04.** `I4-B8` is in full scope. The start record read it as "in scope only where B7 needs it", which was narrower than A-31's trim. The record carries a pointer line to this ruling.

## Backlog

**TB01-B1.** A reach for items beyond their own producers, if a review finds an item whose own citations carry a revocable lineage the readiness depends on.

**TB01-B2.** The D-01 `AssuranceData` trust basis and attribution reads, as named under "Interfaces". It is owed with `I4-10`'s addition.

**TB01-B3.** ADC issues, and can revoke, a grant for each AEW owner service and protected observer that produces determinations. Required before W09 is activated.

## Not covered

- **W09's other conditions:** G3, and A-05 §5's output-trust and mediated-effects rows. W09 stays held until they hold too.
- **The reviewer-independence row** and its eligibility rules, including what a determination's eligibility (`AEV-02.a`) is judged on.
- **The D-01 change itself** (`TB01-B2`), and the ADC grants for AEW's own producers (`TB01-B3`).
- **HEB's and R-01's hold variants** (A-31's `I4-B3`).

## Changes

- **Revision 4 (2026-11-01):** answers the narrow look's minor and nit (`CHANGES-r4.md`). A re-establishing determination is made under its kind's rules, a resolution through `I4-07`. A determination is superseded at most once, only by one of the same kind on the same subject (`TB01-06`). The gate adds two `TB01-Q11` cases and two mutants.
- **Revision 3 (2026-11-01):** answers the quick check's two minors and four nits (`CHANGES-r3.md`). The main changes:
  - re-establishment is a superseding determination of the same kind, for every kind and route; a readiness rests on the current one only (`TB01-06`, `TB01-01.b`);
  - the invocation a determination came back through is HEB's fact, and a determination naming none, or another, is unattributed (`TB01-04`, `TB01-05`);
  - items stay under `I4-07` as adopted; eligibility moves to "Not covered"; the D-01 line allows a null generation.
  - **Gate changes:** a re-establish column in `TB01-Q11`, two `TB01-Q06` variants, three `TB01-Q12` cases, a finding case in `TB01-Q07`, and `TB01-Q08`'s ledger and tuple checks. Six new mutants.
- **Revision 2 (2026-11-01):** answers all eleven of round 1's findings (`CHANGES-r2.md`). The main changes:
  - an untrusted determination no longer satisfies its obligation (`TB01-06`, the round's major);
  - the reach is set by identification (`TB01-01.b`, `TB01-02.b`);
  - findings and requests are never basis entries (`TB01-02.c`);
  - an attribution is HEB's fact, and a producer outside a Lead generation has no generation (`TB01-04`);
  - the ADC grant for AEW's own producers is owed (`TB01-B3`).
  - **Gate changes:** a kind × route table (`TB01-Q11`), an attribution check (`TB01-Q12`), a record-by-record `TB01-Q08`, an exact `TB01-Q10`, and TB01's rows run first.
- **Revision 1 (2026-11-01):** the first text, after the advisor check on STG-24's direction.
