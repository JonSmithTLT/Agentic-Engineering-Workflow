<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-51
source: 30-stages/STG-26-A05-section-5-rows/adopted/ap5-r4/AP5-POSITION.md
source-sha256: e1448944c1a4677b5e49c1b7078f4a155d3ddbb6bcf25a879257afef362e0ab2
edits-sha256: none
-->

# AP5: four of A-05 §5's parameter rows, defined for V-01's path (PROPOSED, revision 4)

**Namespace:** `AP5-`
**Status:** proposed.
- **What it answers:** A-48's second item that blocks the outcome by design: "A-05 §5's parameter rows that V1's path needs". Two hold W09 (`I4-06`), and two hold step 6a's delegation (`I3-09`). No decision record has adopted any A-05 §5 row, so this position also sets the form an adopted row takes.
- **How it amends:** by addition. Adopted copies keep their bytes, and no O-01 byte moves.
  - It defines four rows. A-05's frozen bytes, and the hold tables of A-30 (`I3-09`), A-31 (`I4-06`) and A-34 (`I2-08`), keep theirs (`AP5-02` to `AP5-06`).
  - It reads A-39's host qualification as what makes a profile meet a row (`AP5-01`). `IF13-06`, `IF13-07`, `IF13-09`, `IF13-14` and `I6-08` keep their text.
  - It adds to A-49's `TB01-04`: HEB's admission record also names the qualified assessment each producing invocation was admitted under (`AP5-02`, `AP5-R05`).
  - It changes no O-01 type. The types whose effects it touches without holding them are listed in the Interfaces, `SWITCH_ACTIVE_WORK_CONTEXT` (A-28's `I1-02`) among them (`AP5-R06`).
  - It adds, to HEB's record of the switch that `I1-08` makes the owner evidence of its confirmed outcome, the context's entry in `HEB-10.a`'s activation determination (`AP5-R06`).
- **What it leaves:** A-05 §5's other ten rows stay unadopted, and everything they are "Required before" stays held. One of them, the resource-ceilings row, also holds step 6a's delegation (`AP5-R07`).

**Authority:** the operator's decision to draft it (`00-governance/decisions/2026-11-01-operator-start-STG-26-A05-section-5-rows.md`), under A-48 (`00-governance/decisions/2026-11-01-operator-adoption-V01-matrix-r4.md`).
**Threat model:** the operator's G3 threat model (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`), under the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`).
**Research consulted:** none. `tools/research_index.py lookup` returned no hits for `ADC-04.m`, `ADC-04.n`, `ADC-04.o`, `ADC-08.b`, `ADC-08.j`, `I3-09`, `I4-06` or `I2-08`.
**Files:** this file, and its gate, `check_ap5.py`, a derivation check with no model.

## What the adopted text already decides

- **A row is a definition, not a value** (A-05 §5): its rows "are **not decided values**". Its undefined-parameter rule says "no new protected effect obtains permission merely because a contract remains incomplete". Its preservation rule keeps "Current effective authority, classification, containment, revocation and evidence controls" effective.
- **A row holds only what it is "Required before"** (`I3-09`, `I4-06`, `I2-08`): the owner holds that effect with `POLICY_UNAVAILABLE`, allocating nothing and consuming no consent. "Holds are per §5 row, not per type. Adopting a row releases what that row is required before, and nothing else."
- **Launch and isolation** (A-05):
  - `ADC-04.m`: an approved launch capability profile, denying agent-creation paths outside AEW's coordination, before any source-mutating agent, the Lead included;
  - `ADC-04.n`: no source-mutating agent is activated where assignment-workspace isolation cannot protect other assignments, authority records and downstream consumers across every path;
  - `ADC-04.o`: no workspace or build result with an unreconciled unauthorized write is released or consumed as trusted;
  - the effect-enforcement boundary: the deployment inventories every consequential channel, and the minimum isolation "is an enforceable outcome".
- **The minimum isolation profile** (A-06 §3.4):
  - six denial classes, C1 to C6: workspace writes, protected and secret reads, inference and delegation, network and external effects, process and IPC, and agent-written execution;
  - each is qualified on the profile actually deployed, from the actual Lead or worker identity, and is not transferable between harness versions;
  - "Missing class qualification refuses the *affected* mutable capability rather than all unrelated safely qualified operations".
- **The supporting atoms** (A-06):
  - `HEB-01.c`: the effective execution profile is established before each protected attachment or mutable context activation. `HEB-01.f`: a qualification is scoped to the tested host and harness version, identity, configuration and channels. `HEB-01.h`: the enforcing executables, configuration and policy are protected from every confined identity;
  - `HEB-02.f`: worktrees and directories are not proof of isolation. `HEB-02.i`: mutable activation is refused wherever §3.4's denials are not demonstrated, "including for a directly implementing Lead". `HEB-02.j`: the Lead base identity is inspection-oriented, and source-changing paths run through separately confined contexts. `HEB-02.h`: an always-ready inspection path. `HEB-02.g`: shared Git state is protected;
  - `HEB-03.a` inventories each profile's consequential paths; `HEB-03.b` and `HEB-03.q` enforce containment over every path; `HEB-03.g` qualifies the denial classes before activation; `HEB-03.h` blocks trusted downstream use of contaminated work; `HEB-03.i`: receipts are built by a trusted boundary apart from confined output; `HEB-03.o`: a material change invalidates the affected qualification;
  - `HEB-07.h`: authority termination, process termination and residual effects are reported apart. `HEB-07.j`: on trust revocation, descendant execution is stopped or contained;
  - `HEB-10.a`: an inspectable per-deployment activation determination, naming unmet prerequisites. `HEB-10.g`: a negative probe is evidence only with reachability, the exercised path, a positive control, the denial cause and independent post-effect verification;
  - A-06 §3.6 lists the evidence required before a mutable deployment is declared supported. A-06 §3.1: "A separate workspace directory or Git worktree is not an OS boundary."
- **Host qualification** (A-39, restating A-17 and A-18):
  - a host or capability qualification is an outside-lineage assessor's record (`IF13-06`, `IF13-07`, `S01-09`, `S01-18`). An operator's label never qualifies (`IF13-07`);
  - holding owners re-evaluate at each consequential effect (`IF13-09`);
  - the operator's `REVOKE_HOST_QUALIFICATION` invalidates one profile's assessments, and only a newer assessor's record naming the revocation qualifies it again (`I6-08.b`, `IF13-14`). It never withdraws G3, and the operator's other protective stops, `SUSPEND_GRANT` and `STOP_CHILD_NOW`, keep their G3 origin (`I6-08.d`);
  - a profile definition's revision is the operator's, by IF-13's `ADOPT_MANIFEST_EDIT` and `REQUEST_PROFILE_CHANGE`.
- **Mediation and revocation** (A-05 `ADC-08`):
  - `ADC-08.a`: a current effective grant before any mediated consequential effect;
  - `ADC-08.b`: no protected execution without minimum mediation and revocation coverage over AEW-protected authority state, records and credentials;
  - `ADC-08.c`: no new mediated protected effect from a revoked, suspended or superseded generation;
  - `ADC-08.d`: an effective revocation that needs no agreement from the affected agent;
  - `ADC-08.e`: every effect path's mediation status is disclosed;
  - `ADC-08.j`: the deployment identifies the minimum channels it must actually mediate, and disclosure is not enforcement.
- **Delegation** (A-30 `I3-03`):
  - the roles are `IMPLEMENTER`, `INVESTIGATOR`, `ADVISOR` and `DIAGNOSTIC`, and an advisor or investigator grant permits no protected or source-mutating effect;
  - a derived grant sits within the current Lead generation's own grant, is allowed by its autonomy (`I3-05`), and fits the resource policy issuer's hard limits (`ADC-08.f`), which are §5's resource-ceilings row read per delegation;
  - its expiry is finite and no later than its parent's (`VALIDITY_INVALID`), and it names the work's current accepted revision (`WORK_REVISION_STALE`);
  - it launches nothing; HEB launches the worker under the enforced profile (`ADC-04.m`, `ADC-04.n`).
- **Handover and revocation** (A-06 §3.3's table):
  - a routine Lead handover, compaction or harness failure is not trust revocation: eligible grants may be reaffirmed by the successor, and results are "Held until current authority qualifies";
  - trust revocation is "Default STOP/contain" for affected descendants.
  - The lineage and its revocation are A-30's `I3-04`. Reaffirmation is A-25's `REAFFIRM_ELIGIBLE_CHILD_GRANTS`, whose fields `I3-03`'s grant record carries. A generation fence and a handover are A-28's (`I1-04`, `I1-05`), and the transition's class is ADC's (`ADC-02.l`). The trust state a readiness relies on is A-31's `I4-01c`, extended by A-49.
- **Work reassignment** (A-05): reassigning work implicitly grants no write rights (§2.2); a derived grant is never transferred (`ADC-04.b`); original work and evidence are preserved (`ADC-09.c`), and the objective and obligations are not silently changed (`ADC-09.d`).
- **The operator's host facts:**
  - AEW supports Linux and Windows (`00-governance/decisions/2026-11-01-operator-supported-platforms-Linux-and-Windows.md`);
  - the Lead's measured containment is `os_readonly_roots` on Linux and `workdir_separation_only` on Windows (`00-governance/decisions/2026-10-30-operator-Lead-containment-minimums.md`).

## The parts

- **The operator** adopts a row, and so defines its parameter. The operator does not qualify a host by adopting a row, and approves a profile definition only by IF-13's types.
- **The host assessor,** outside every agent lineage, records whether a deployed profile meets a row (`AP5-01`).
- **HEB** launches, contains and mediates. It runs the installed suite whose results are the assessor's evidence, records on each admission the assessment it admitted under, and shows its activation determination (`HEB-10.a`).
- **ADC** owns grants, roles, lineages, their revocation, and the class of a Lead transition.
- **Each owner that holds a type** (ADC for `I3-09`, CNI and AEV for `I4-06`, HEB for `I2-08`) reads whether the row is adopted, and met under `AP5-01`.

## Rules

**AP5-00. Precondition: A-05 §5's undefined-parameter and preservation rules, `I3-09`, `I4-06` and `I2-08`, A-39's `IF13-06`, `IF13-07`, `IF13-09`, `IF13-14` and `I6-08`, and A-49's `TB01-04`, hold as adopted, except where a rule here adds to them.** Nothing here narrows a control.

**AP5-01. An adopted row has two parts, its definition and its host test; and one meaning of "met".**
- **The definition** is the adopted clauses the row's rule names, with this position's rulings. It cites them, and restates none.
- **The host test** says what a deployed profile must demonstrate for the row.
- **What "met" means, everywhere in this position:** a profile meets a row only while all of these hold:
  - **the assessor's record:** the host assessor's current capability assessment for that row's host test, on that profile, is qualified (`IF13-06`, `IF13-07`, `S01-09`, `S01-18`). An operator's label, and a confined process's own output, never qualify;
  - **its evidence:** a run of the installed, protected suite (`HEB-01.h`) on that host, from the actual identities, before activation (`HEB-03.g`). Each negative case meets `HEB-10.g`'s five conditions, and the receipt is built outside the confined identity (`HEB-03.i`). The assessment names the suite's bytes by hash, and the independent review record that covers that hash (`AP5-R01`). A hash with no such record qualifies nothing;
  - **it is current:** no material change since (`HEB-03.o`, `HEB-01.f`), including a change to the suite's bytes, and no revocation (`I6-08.b`, `IF13-14`);
  - **it is read where it is relied on:** each holding owner reads it at each effect (`IF13-09`), for the profile under which the effect, or the output it relies on, was produced (`AP5-R05`).
- **An adopted row that a profile does not meet still holds there:** the owner holds each O-01 type the row is "Required before" with `POLICY_UNAVAILABLE`, exactly as for an unadopted row. HEB's own activations the row is required before, a worker's launch and the Lead's source-changing context, have no O-01 outcome: HEB refuses them under `HEB-02.i` (`AP5-R02`, `AP5-R06`). This extends `I3-09`'s rule by addition. No wire byte moves.
- **The hold says why:** an O-01 hold's `owner_evidence_ref`, and HEB's refusal of its own activation, each name one record, the entry in `HEB-10.a`'s activation determination for that profile and effect. That entry names the row, the profile, and either that the row is unadopted, or the assessment, or the producing invocation and its assessment, that does not meet it. The attention item names the row and the profile. So "adopted but not met" is never read as "unadopted".
- **Adopting a row releases** only what the frozen hold tables name for it (`AP5-06`), and only where it is met (`AP5-01`). It holds nothing that A-05 §5's undefined-parameter rule does not already hold today.

**AP5-02. The launch row.** A-05's text: "All mutable-agent launch permissions (including Lead), assignment-workspace isolation, build consumption quarantine and source effect coverage", required before "Activating any source-mutating agent or trusting shared outputs".
- **Its definition:**
  - **launch permissions** are `ADC-04.m`'s profile. Its approval is the operator's profile definition, by IF-13's `ADOPT_MANIFEST_EDIT` and `REQUEST_PROFILE_CHANGE`; its qualification is the assessor's (`AP5-01`);
  - **assignment-workspace isolation** is `ADC-04.n`, as A-06 §3.4's classes C1 to C6;
  - **build consumption quarantine** is `ADC-04.o`, `HEB-03.h` and `HEB-02.g`;
  - **source effect coverage** is `HEB-03.a`'s inventory, with enforcement over every path (`HEB-03.b`, `HEB-03.q`). Disclosure alone is not coverage (`ADC-08.j`);
  - **requalification** is `HEB-03.o`'s, with `HEB-01.f`'s scope;
  - **activating a source-mutating agent** is any mutable context activation: an implementer's or a diagnostic's launch, and the Lead's own separately confined source-changing context (`AP5-R06`);
  - **trusting shared outputs** is relying on an output produced under the row: `APPROVE_INTEGRATION` is released only where every producing invocation the readiness rests on was admitted under an assessment that met this row at admission (`AP5-01`, `AP5-R05`).
- **Its host test:** the deployed profile passes classes C1 to C6 from the actual Lead and worker identities, with A-06 §3.6's evidence (`HEB-03.g`), as `AP5-01` defines the evidence.
- **Residue:** what counts as the independent negative conformance A-06 §3.5 asks for (`AP5-R01`); the Lead's activation (`AP5-R06`).

**AP5-03. The mediation row.** A-05's text: "Minimum mediated effect channels, effect acceptance, emergency revocation and stale-authority handling", required before "Protected execution and claims of effective revocation".
- **Its definition:**
  - **the minimum mediated channels** (`ADC-08.j`): every path to AEW-protected authority state, records and credentials (`ADC-08.b`). A contained context reaches them only through an owner's admission, never directly;
  - **effect acceptance:** an owner admits a mediated effect only under a current effective grant (`ADC-08.a`), one effect per member, bound to its requester (`HEB-01.d`);
  - **emergency revocation:** ADC's `REVOKE_LINEAGE` (`I3-04`), the operator's `SUSPEND_GRANT` and `STOP_CHILD_NOW` (`I6-08.d`), and HEB's stop and containment of the lineage's running work, which needs no agreement from the agent (`ADC-08.d`, `HEB-07.j`);
  - **stale-authority handling:** no new mediated protected effect from a revoked, suspended or fenced generation (`ADC-08.c`, `I1-04`).
- **Its host test:** each case from the actual worker identity:
  - the profile's inventory (`HEB-03.a`) names every consequential channel with its mediation status (`ADC-08.e`), and all six classes, C1 to C6, pass for every channel to protected state. That includes C3, the credentials and provider reach `ADC-08.b` names, and C6, since agent code run under a privileged identity is a path to protected records;
  - a running lineage with background and detached descendants is stopped by HEB without the agent's cooperation;
  - after the stop, or the generation's fence, no mediated request from that lineage or generation is admitted (`ADC-08.c`, `HEB-01.d`);
  - termination and residual effects are reported apart (`HEB-07.h`, `HEB-07.j`, A-06 §5's trust-revocation case).

  This matters on its own because the mediation row alone releases A09. A claim that a revocation or a stop is effective is made only on a profile that meets this row (`AP5-01`).
- **Residue:** none beyond `AP5-R01`.

**AP5-04. The helper-roles row.** A-05's text: "Allowed helper/advisor roles, budget allocation and grant procedure", required before "Delegating assistance with protected effects".
- **Its definition:** `I3-03` as adopted.
  - **The roles:** its four, with an advisor or investigator grant permitting no protected or source-mutating effect.
  - **Budget allocation:** each delegation fits the resource policy issuer's hard limits (`ADC-08.f`), and holds when they are unavailable (`RESOURCE_LIMITS_UNAVAILABLE`). For `IMPLEMENTER` and `DIAGNOSTIC` the limits are the resource-ceilings row's; for an advisor or investigator, the issuer's current limits (`AP5-R07`).
  - **The grant procedure:** `I3-03`'s checks and record, with the delegation allowed by the Lead grant's autonomy (`I3-05`).
- **Its host test:** none of its own. The worker's launch is the launch row's (`AP5-02`).
- **Residue:** the resource-ceilings row (`AP5-R07`).

**AP5-05. The handover row.** A-05's text: "Issuer-authorized routine handover versus trust revocation, grant lineage, reassignment and policy-defined expiry", required before "Any admission or continuity of delegated protected effects".
- **Its definition:**
  - **issuer-authorized routine handover versus trust revocation:** A-06 §3.3's table, whose dispositions A-34's I-2 types serve, with A-28's handover and fence (`I1-05`, `I1-04`). Whether a transition is routine or a trust revocation is ADC's classification, issued by ADC or a previously authorized trusted platform rule (`I1-05`, `I3-04`, `ADC-02.l`), never either Lead's;
  - **grant lineage:** ADC's derived grant within its parent (`I3-03`), revoked as a lineage (`I3-04`);
  - **reassignment:**
    - **of work, to another worker:** the old derived grant is revoked or lapses, and a new `DELEGATE_NEW_WORKER` issues the new one. A grant is never transferred (`ADC-04.b`), and reassignment grants no write rights implicitly (A-05 §2.2). Original work and evidence are preserved (`ADC-09.c`), and the objective and obligations do not change (`ADC-09.d`);
    - **across a routine handover:** a derived grant is reaffirmed by the successor through A-25's `REAFFIRM_ELIGIBLE_CHILD_GRANTS`, or it lapses.

    Either way historical evidence is kept, and it makes no current proof for a changed subject (A-05's work and evidence boundary);
  - **policy-defined expiry:** the delegating Lead sets each derived grant's expiry in `DELEGATE_NEW_WORKER`'s target, finite and within the parent's validity (`I3-03`). The grant also ends at its ending conditions: the generation's fence (`I1-04`), the work's accepted revision moving (`WORK_REVISION_STALE`), and revocation (`I3-04`). Those conditions are the policy (`AP5-R03`).
- **Its host test:** none of its own.
- **Residue:** none. In particular this position adds no AEW-wide maximum grant lifetime (`AP5-R03`).

**AP5-06. What each row releases, and only that.** The table below is derived from the frozen `I3-09`, `I4-06` and `I2-08` tables. The gate requires its pairs to equal theirs, and each cell's opening words to follow from every A-05 §5 row the frozen line names. It lists O-01 types and owner acts only. Holds are per effect: an effect held by more than one row is released only when all of its rows are adopted and met (`AP5-01`).

**The openings:** "never held" where the frozen line never holds the type, and the registry marks it `REDUCING`; "released by this row alone"; "released with" the other AP5 rows that also hold it; "not released" where a row outside this position also holds it, naming that row.

| Type or owner act | Rule | Frozen clause | What adoption changes |
|---|---|---|---|
| `DELEGATE_NEW_WORKER` | `AP5-02` | `I3-09` | not released: it also waits for the resource-ceilings row, and for `DIAGNOSTIC` the diagnostic row. This row holds HEB's launch of the worker, never ADC's admission of the delegation |
| `DELEGATE_NEW_WORKER` | `AP5-04` | `I3-09` | not released: it also waits for the resource-ceilings row, and for `DIAGNOSTIC` the diagnostic row. With `AP5-05`, this row holds ADC's admission for `IMPLEMENTER` and `DIAGNOSTIC` |
| `DELEGATE_NEW_WORKER` | `AP5-05` | `I3-09` | not released: it also waits for the resource-ceilings row, and for `DIAGNOSTIC` the diagnostic row. With `AP5-04`, as above |
| `AUTHORIZE_EXTERNAL_EFFECT` | `AP5-03` | `I3-09` | released by this row alone from the §5 hold: A09, an operator-consented exact external effect. It still waits for G3, I5-08a's read and the held content (`I3-09`) |
| `REVOKE_LINEAGE` | `AP5-03` | `I3-09` | never held; ADC's `EFFECT_CONFIRMED` may then be read with HEB's claim that the lineage's effects stopped, on a profile that meets this row (`AP5-01`) |
| `APPROVE_INTEGRATION` | `AP5-02` | `I4-06` | released with `AP5-03`: W09, where every producing invocation met this row at admission (`AP5-01`, `AP5-R05`). It still waits for G3 and I5-08a's read |
| `APPROVE_INTEGRATION` | `AP5-03` | `I4-06` | released with `AP5-02`: W09, as above |
| `STOP_CHILD_NOW` | `AP5-03` | `I2-08` | never held; HEB may then claim that effects stopped, on a profile that meets this row (`AP5-01`) |
| `RELEASE_CHILD_TO_MANUAL` | `AP5-03` | `I2-08` | never held; as above |
| `CANCEL_CHILD_OPERATION` | `AP5-03` | `I2-08` | never held; as above |
| `DISCARD_HELD_RESULT` | `AP5-03` | `I2-08` | never held; as above |
| `ABANDON_INTERRUPTED_EXECUTION` | `AP5-03` | `I2-08` | never held; as above |
| `REQUEST_BACKGROUND_RERUN` | `AP5-03` | `I2-08` | not released: it also waits for the resource-ceilings row |
| `REQUEST_BACKGROUND_RERUN` | `AP5-02` | `I2-08` | not released: it also waits for the resource-ceilings row. This row holds it only for a prior operation whose definition mutates source |

**Not in the table, and not a leak:**
- **The Lead's attachment and its switch of context:** `ATTACH_LEAD`, `REATTACH_LEAD`, `TAKEOVER_LEAD`, `HANDOVER_LEAD` and `SWITCH_ACTIVE_WORK_CONTEXT` are admitted under their adopted checks, unchanged. The Lead's separately confined source-changing context is HEB's own activation after the switch, not an O-01 effect, and HEB refuses it under `HEB-02.i` where the launch row is not met (`AP5-01`, `AP5-R06`).
- **`REAFFIRM_ELIGIBLE_CHILD_GRANTS` and `CONTINUE_ELIGIBLE_WORK`** are continuity of delegated protected effects, which the handover row is required before. They are in no frozen hold table, and neither maps `POLICY_UNAVAILABLE`. Neither can reach a protected role's grant before `DELEGATE_NEW_WORKER` is released for it, which needs the handover row, so nothing passes through them first.

**AP5-07. A-48's step 6a and W09 are read with `AP5-01` to `AP5-06`.** A built owner conforms to the hold tables and this position together, as A-49 extended A-31.

## Interfaces

- **No O-01 schema byte changes.**
  - `POLICY_UNAVAILABLE` is already mapped for every type `AP5-06` says a row holds, so `AP5-01`'s "adopted but not met" hold needs no new refusal.
  - The outcome's `owner_evidence_ref` already exists on the 0.9 wire, so naming the hold's cause needs no new field.
  - The Lead's attachment types keep their adopted refusals (`AP5-R06`).
- **The activation determination** that `HEB-10.a` requires shows which rows a profile meets (`AP5-01`). **Candidate (D-01):** a read of it beside the attention item a held type raises. This is a read, not a wire change.
- **The O-01 types whose effects this position touches, held or not:**
  - held, as `AP5-06` lists: `DELEGATE_NEW_WORKER`, `AUTHORIZE_EXTERNAL_EFFECT`, `APPROVE_INTEGRATION` and `REQUEST_BACKGROUND_RERUN`;
  - never held, as `AP5-06` lists: `REVOKE_LINEAGE` and the five reducing I-2 types;
  - touched and not held: `ATTACH_LEAD`, `REATTACH_LEAD`, `TAKEOVER_LEAD`, `HANDOVER_LEAD` and `SWITCH_ACTIVE_WORK_CONTEXT` (`AP5-R06`); `REAFFIRM_ELIGIBLE_CHILD_GRANTS` and `CONTINUE_ELIGIBLE_WORK` (`AP5-06`); `REVOKE_HOST_QUALIFICATION`, `SUSPEND_GRANT` and `STOP_CHILD_NOW`, read as they are (`AP5-01`, `AP5-03`).
- **HEB's admission record** names the qualified assessment each invocation was admitted under, as an addition to `TB01-04`'s admission record (`AP5-R05`).

## The gate

`check_ap5.py` is a derivation check: it reads the frozen bytes and this file, and builds no model.

| Check | What it shows | Pass |
|---|---|---|
| **AP5-Q01** | The A-05 text that `AP5-02` to `AP5-05` quote, each row's parameter and its "Required before", equals A-05 §5's frozen bytes. | exact match, four rows |
| **AP5-Q02** | `AP5-06`'s table equals the pairs of row and type parsed from the frozen `I3-09`, `I4-06` and `I2-08` tables. Each cell's opening follows from every A-05 §5 row the frozen lines for its type name, each row matched by its first two words with punctuation normalised, so a row named in short counts: "not released", naming each row outside this position and no other, with a role-bound row named for its role; "released with" each other AP5 row; or "released by this row alone". A condition a cell takes from its rule (W09's `AP5-R05`) is read too. | the same set, both ways; every opening as derived |
| **AP5-Q03** | Every requirement ID this file cites resolves in D1, as a requirement or a named cross-reference. | none unresolved |
| **AP5-Q04** | A cell says "never held" exactly where the frozen line never holds the type and A-43's registry marks it `REDUCING`. `POLICY_UNAVAILABLE` is mapped, in A-43's frozen refusal map, for every other type `AP5-06` names. | both ways; every held type |
| **AP5-Q05** | Each of `AP5-02` to `AP5-05` names a definition, a host test and a residue, and every residue it names is a ruling in this file. The launch and mediation rows' host tests name C1 to C6, and the mediation row's names its stop, staleness and reporting cases. | each rule |
| **AP5-Q06** | Every sentence of the rules, scenarios and rulings that says a profile meets, does not meet, is unmet for or qualifies for a row cites `AP5-01`, apart from `AP5-01` itself. It reads those words only. | none uncited |

## Scenarios

**AP5-X01.** The operator adopts all four rows. The host assessor has qualified a Linux host's deployed profile for the launch and mediation rows' host tests (`AP5-01`). An external effect the operator consents to under G3, with its content read, is admitted there (A09). The Lead's delegation of an implementer for a one-line fix (step 6a) still waits for the resource-ceilings row (`AP5-R07`). Once that row is adopted too, HEB launches the implementer, records the assessment it admitted under, AEV's readiness is clear, and the operator approves W09 under G3 with the package read. On a Windows host, which meets neither row (`AP5-01`, `AP5-R02`), W09 is `POLICY_UNAVAILABLE`, and its `owner_evidence_ref` names the unmet assessment.

**AP5-X02.** The operator adopts the helper-roles and handover rows only. ADC's admission of an implementer delegation still waits for the resource-ceilings row; once that is adopted, the delegation is admitted, but its launch waits for the launch row, so no implementer runs. An advisor or investigator delegation is never held by a §5 row; it is admitted within the issuer's current limits, or held with `RESOURCE_LIMITS_UNAVAILABLE` where none are stated (`I3-03`, `AP5-R07`).

**AP5-X03.** A package was produced on a Linux host whose assessment the operator then revokes (`I6-08`). The host is requalified the next day. W09 for that package is held: a producing invocation was admitted under the revoked assessment (`AP5-01`, `AP5-R05`), and the hold's evidence names the route back. The Lead re-produces the change in a fresh workspace on the requalified host, its checks run there, and W09 for the new package is not held for that reason.

## Rulings

**AP5-R01. Independent negative conformance (the operator's question at adoption).**
- **The question:** A-06 §3.5 asks for "independent negative conformance" of C1 to C6. What satisfies it?
- **Recommended:** the host assessor's record for each deployed profile (`IF13-07`), as `AP5-01` defines it.
  - It rests on a run of the installed, protected suite on that host, before activation and again at every `HEB-03.o` trigger, from the actual identities.
  - The assessment names the suite's bytes by hash, so a change to the suite stales it.
  - Each negative case satisfies `HEB-10.g`.
  - The suite's case set and its oracle are reviewed by an independent reviewer when the suite is adopted, and at every change to a case or its oracle. The assessment names the review record that covers the suite's hash (`AP5-01`). A green run alone never shows a weakened case.
  - CI runs the same suite on reference profiles as a regression check only. CI is not a deployed profile, and qualifies none.
- **The alternative:** an independent run per release and profile, which costs a reviewer slot each time. It too names the review record that covers the suite's hash.

**AP5-R02. Until an assessment qualifies it, every profile is unmet; Windows is the profile known to fail** (`AP5-01`).
- **The reason:** a row is met only by the assessor's record (`AP5-01`). None exists today, for any profile, Linux at `os_readonly_roots` included (A-06 §5: no full mutable profile is demonstrated). The Windows Lead's measured containment is `workdir_separation_only`, and a separate directory is not isolation (A-06 §3.1, `HEB-02.f`); `HEB-02.i`'s own witness is this case. So C1 is not met there (`AP5-01`).
- **The consequence after adoption,** on every profile until the assessor qualifies it (`AP5-01`):
  - W09 and A09 stay `POLICY_UNAVAILABLE`;
  - an implementer's or a diagnostic's launch is refused by HEB (`HEB-02.i`), and HEB's report of the delegated child to the Lead names `HEB-10.a`'s entry saying why;
  - the Lead's separately confined source-changing context is refused by HEB (`HEB-02.i`), with `HEB-10.a`'s entry saying why, named in HEB's record of the switch (`AP5-R06`).
  - Adoption changes nothing about the Lead's attachment: it attaches where its own adopted checks pass (`HEB-01.c`, `HEB-02.j`, I-1's claim check).
  - This is no more than A-05 §5's undefined-parameter rule holds today: adoption adds the path to release, and holds nothing new.
- **What would change it:** an assessor's record for a profile that passes the host tests. On Windows that needs a profile that passes C1 to C6, such as a low-integrity token backend. Accepting a weaker profile would loosen A-06, and is out of this position's scope. No Windows worker profile has been measured.

**AP5-R03. No new maximum grant lifetime.** A derived grant's expiry is set by the delegating Lead, finite and within its parent's validity (`I3-03`), and the grant ends at its ending conditions: the generation's fence, the work's revision moving, and revocation. A fixed AEW-wide maximum would be a magic limit with no measured source, so none is added.

**AP5-R04. The four rows are defined together, and adopted row by row.** The operator may adopt any of them. Holds are per effect, so `AP5-06` says what each adoption releases.

**AP5-R05. Trusting shared outputs is read for the profile each output was produced under.**
- **The reason:** the launch row's quarantine part acts on a *detected* unauthorized write (`ADC-04.o`, `HEB-03.h`). An output produced on a profile that did not then meet the row (`AP5-01`) had no enforcement, so nothing could be detected. So W09 asks whether every producing invocation the readiness rests on, as HEB's admission records name them (`TB01-04`), was admitted under an assessment that met the launch row at admission (`AP5-01`, `HEB-01.c`).
- **What HEB records:** on each admission, the assessment it admitted under. This adds to `TB01-04`'s admission record.
- **Revocation and staleness differ, by the record each leaves:**
  - **revoked:** IF-13's revocation record (`I6-08`) names the assessment. It states that the host's containment is not trusted, so output produced under that assessment stays untrusted after any later requalification (`AP5-X03`);
  - **stale:** an assessment invalidated by a material change (`HEB-03.o`) did not fail before the change. The change dates it, not its detection: output produced after the change is already unmet (`AP5-01`'s "no material change since"), and output produced before it is unaffected.
- **The route back from a revocation:** the output is re-produced under a current assessment: the change re-applied in a fresh workspace, with its checks run there, by a new delegation or by the rerun once it is released. This is `ADC-04.o`'s reconciliation disposition for an output that had no enforcement. AEV's re-establishment (`TB01-06`) re-establishes determinations, not output, so it does not apply.
- **Where it fails:** W09 is held with `POLICY_UNAVAILABLE`. Its `owner_evidence_ref` names `HEB-10.a`'s entry for the producing invocation, which names its assessment, the revocation or the change, and the route back (`AP5-01`).

**AP5-R06. The Lead's attachment and its switch of context are not mutable activations; its source-changing context is HEB's own activation.**
- **The attachment:** `HEB-02.j` makes the Lead base identity inspection-oriented, and runs every source-changing path through a separately confined context. So `ATTACH_LEAD`, `REATTACH_LEAD`, `TAKEOVER_LEAD` and `HANDOVER_LEAD` establish an inspection-oriented base, where the profile enforces `HEB-02.j`, under their adopted checks, including `INVALID_INSTALLATION_OR_PROFILE` where it is mapped (`HEB-01.c`). A base not demonstrated inspection-oriented gives no trusted output: its output is no HEB-admitted invocation, so it has no attribution (`I4-01c`, `AEV-09.d`), and `HEB-10.a` shows it.
- **The switch:** `SWITCH_ACTIVE_WORK_CONTEXT` (`I1-02`) selects one of the Lead's granted assignments as the active context, and is admitted under `I1-02`'s checks, unchanged. It activates nothing mutable by itself.
- **The source-changing context:** HEB activates the Lead's separately confined context for the active assignment when the Lead first needs it, reading the launch row at each activation (`AP5-01`, `IF13-09`). That activation is HEB's own, not an O-01 effect, and it is the launch row's, as `ADC-04.m`'s "including the Lead" and `HEB-02.i`'s "directly implementing Lead" say. Where the row is not met (`AP5-01`), HEB refuses it under `HEB-02.i`, and each source-changing attempt from the Lead in that assignment is refused at the base, naming `HEB-10.a`'s entry for the context. Once the row is met there (`AP5-01`), the next attempt activates the context; no second switch is needed.
- **What the switch's outcome names:** its `owner_evidence_ref` names one record, HEB's record of the switch, which `I1-08` makes the owner evidence of its confirmed outcome (`CS-09`). That record names `HEB-10.a`'s entry for the context, met or not (`AP5-01`). So the evidence keeps its one meaning, and the entry is reachable from it. Until `AP5-B1`'s read exists, the Lead learns the entry at its first refused attempt.
- **The writable scope:** `I1-02`'s outcome, that the Lead's writable effects are exactly the new assignment's, is the scope of the context HEB activates. Where the activation is refused, the Lead has no writable effect, which `HEB-02.c`'s ceiling allows. The switch and the activation are the two events `HEB-01.c` names.
- No wire byte moves: the field already exists, and `I1-02`'s admission list is unchanged.
- **The alternatives rejected:**
  - holding the four attachment types would leave no Lead at all on an unmet profile (`AP5-01`), even for inspection, against `HEB-02.h`, and `REATTACH_LEAD` maps neither `POLICY_UNAVAILABLE` nor a profile refusal;
  - holding `SWITCH_ACTIVE_WORK_CONTEXT` would add `POLICY_UNAVAILABLE` to its refusal map and a condition to `I1-02`'s admission list: a wire change, for a switch that changes no source by itself.

**AP5-R07. Step 6a's delegation also waits for the resource-ceilings row.**
- **The reason:** the frozen `I3-09` line for `DELEGATE_NEW_WORKER`, for the roles it holds, `IMPLEMENTER` and `DIAGNOSTIC`, names it: "The hard limits are §5's 'Resource hard ceilings', read per delegation (I3-03)". That row is "Required before" "Controlled multi-agent execution". The frozen line is the whole ground; this position does not extend it to other roles.
- **An advisor or investigator:** the frozen `I3-09` line never holds it (I3R1-6). `I3-03` still requires the resource policy issuer's hard limits for every delegation (`ADC-08.f`): an advisor or investigator delegation is admitted within the issuer's current limits, which §5's preservation rule keeps effective, and held with `RESOURCE_LIMITS_UNAVAILABLE` where the issuer states none. That is `I3-03`'s hold, not a §5 row's.
- **The consequence:** adopting these four rows releases A09 and, with a delegated package, W09, but not step 6a's implementer, until the resource-ceilings row is adopted as well.
- **Not defined here:** that row is outside this position's four. Whether it is defined next is the operator's call (`AP5-B2`).

## Backlog

**AP5-B1.** The D-01 read of `HEB-10.a`'s activation determination (Interfaces).

**AP5-B2.** A-05 §5's other ten rows, each when a selected step needs it. The resource-ceilings row is next, because step 6a's delegation and the rerun both wait for it (`AP5-R07`).

## Not covered

- **G3.** Every protected step waits for G3 wherever it is not established.
- **I5-08a's content read,** which W09 and A09 also wait for.
- **The build of TB01 (A-49)** and of AEV's assurance.
- **The assessor's build,** and any profile's assessment.
- **A Windows profile** that meets C1 to C6.
- **A-05 §5's other ten rows,** the resource-ceilings row among them.

## Changes

- **Revision 1 (2026-11-01):** the first text, after the advisor check on STG-26's shape (`STAGE.md`).
- **Revision 2 (2026-11-01):** round 1's sixteen findings, mapped in `CHANGES-r2.md`:
  - one meaning of "met", the assessor's current qualified record, in `AP5-01`, cited everywhere else;
  - `AP5-R01` recommends the assessor's record from the installed suite, with case review at every change;
  - the mediation row's host test covers stopping, staleness and reporting;
  - the Lead's attachment is not a mutable activation (`AP5-R06`);
  - step 6a also waits for the resource-ceilings row (`AP5-R07`);
  - trusting shared outputs reads each producing invocation's assessment (`AP5-R05`);
  - the hold names its cause;
  - the gate derives `AP5-06`'s openings, and gains `AP5-Q06`;
  - holds are per effect; reassignment, requalification, expiry and the transition's classifier are named; `AP5-R02` covers every profile.
- **Revision 3 (2026-11-01):** the quick check's eight items, mapped in `CHANGES-r3.md`:
  - `AP5-R06` names `SWITCH_ACTIVE_WORK_CONTEXT`: admitted unchanged; the Lead's source-changing context is HEB's own activation, refused under `HEB-02.i` and named in the switch's outcome; no wire change;
  - `AP5-R02` says what adoption changes for the Lead, and what it does not;
  - `AP5-R07` rests on the frozen `I3-09` line alone, and says where an advisor's limits come from;
  - `AP5-R05` names the records that tell revoked from stale, dates staleness by the change, and gives the route back;
  - the assessment names the review record that covers the suite's hash;
  - the gate matches abbreviated row names, checks openings both ways and per role, reads W09's condition, and widens `AP5-Q06`;
  - the Interfaces list every O-01 type the position touches; `owner_evidence_ref` names one record.
- **Revision 4 (2026-11-01):** the narrow check's five riding items, mapped in `CHANGES-r4.md`:
  - the switch's `owner_evidence_ref` keeps its one meaning, HEB's record of the switch, which names the context's entry;
  - a worker's launch is refused by HEB, not held with a wire reason, and the Lead sees it on the child;
  - HEB activates the Lead's context when first needed, reading the row each time;
  - `AP5-Q06` reads sentence by sentence;
  - `I1-02`'s writable scope is reconciled with a refused context.
