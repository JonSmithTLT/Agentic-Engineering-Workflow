<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-52
source: 30-stages/STG-27-A05-resource-ceilings-row/adopted/rhc-r4/RHC-POSITION.md
source-sha256: fc9ff906eeaefa5d19eeddf23bd9f9faabe716295ce428f4d568d348e8eafa10
edits-sha256: none
-->

# RHC: A-05 §5's resource-ceilings row, defined for V-01's path (PROPOSED, revision 4)

**Namespace:** `RHC-`
**Status:** proposed.
- **What it answers:** A-51's `AP5-R07` and `AP5-B2`. Step 6a's delegation of an implementer, and the rerun, wait for the row "Resource hard ceilings and ongoing limit enforcement". The frozen `I3-09` line for `DELEGATE_NEW_WORKER` names it ("The hard limits are §5's 'Resource hard ceilings', read per delegation (I3-03)"), and so does the frozen `I2-08` line for `REQUEST_BACKGROUND_RERUN`.
- **How it amends:** by addition. Adopted copies keep their bytes, and no O-01 byte moves.
  - It defines one row. A-05's frozen bytes, and the hold tables of A-30 (`I3-09`) and A-34 (`I2-08`), keep theirs (`RHC-01`, `RHC-04`).
  - It takes A-51's form of an adopted row and its one meaning of "met" (`AP5-01`), and refines it by addition: for this row, "met" is read per metered unit (`RHC-02`, `RHC-R01`).
  - It reads `I3-03`'s check that "the allocation fits the hard limits", and the rerun's resource check, for this row (`RHC-03`). Their refusal maps are unchanged.
  - Like `AP5-01`, it departs from `I3-12`'s "Every activation hold is decided from the target alone": the hold reads the assessor's record and the profile's route inventory (`RHC-03`).
  - It reads I-6's standing policy (A-39) as the ceiling's issuance, and R-01's and IF-10's semantics as adopted. It changes none of them.
- **What it leaves:** A-05 §5's other nine unadopted rows, the diagnostic row among them, which still holds a diagnostic's delegation. Ceilings other than spend have no issuance (`I6-B1`), and this position invents none (`RHC-R02`).

**Authority:** the operator's decision to draft it (`00-governance/decisions/2026-11-01-operator-start-STG-27-A05-resource-ceilings-row.md`), on A-51 (`00-governance/decisions/2026-11-01-operator-adoption-AP5-r4.md`), under A-48 (`00-governance/decisions/2026-11-01-operator-adoption-V01-matrix-r4.md`).
**Threat model:** the operator's G3 threat model (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`), under the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`).
**Research consulted:** `tools/research_index.py lookup`, 2026-11-01. `ADC-08.f`, `ADC-08.i`, A-21, `R01-09`, `IF10-20`, `I6-B1` and `AEW-FR-10` returned none. A-15 returned four studies, of which one bears on this row: `external-agent-workflow-lessons-2026-09-28`, filed under R-DEC-02. It records two incidents under an external workflow: about 43 recursive review subagents, and worktree overhead that made a million-file repository unusable. It asks that recursive delegation fail at the capability layer, and that fan-out be budgeted together with workspace cost. `RHC-R02` says where this position follows it and where it departs.
**Files:** this file, and its gate, `check_rhc.py`, a derivation check with no model.

## What the adopted text already decides

- **A row is a definition, and an adopted row has a host test** (A-05 §5; `AP5-01`): a profile meets a row only by the host assessor's current qualified record, read at each effect for the profile the effect or output was produced under. An adopted row that a profile does not meet still holds with `POLICY_UNAVAILABLE`, and the hold names its cause (`AP5-01`).
- **A row holds only what it is "Required before"** (`I3-09`, `I2-08`): "Holds are per §5 row, not per type. Adopting a row releases what that row is required before, and nothing else."
- **The obligation** (A-05, A-01):
  - `ADC-08.f`: hard concurrency, usage, rate and spending limits are enforced on ongoing AEW-controlled execution as well as on new allocations;
  - `ADC-08.i`: only the effect that cannot satisfy a mandatory control within the hard limits is withheld, and the limit is not exceeded;
  - `ADC-08.k`: affected work resumes under its existing authorization once resources are available, with no needless operator decision;
  - `AEW-FR-10.a`: allocations above operator-authorized limits are refused. `AEW-FR-10.b`: the Lead allocates workers within authorized limits without a separate approval for each. `AEW-FR-10.f`: limits are enforced against continuing execution, within declared and supported boundaries;
  - A-01's AS-28: an already running mediated worker does not keep spending past an enforceable ceiling. A-01's `AEW-INV-RESOURCE-001`: individually legal delegation, isolation, retry and parallelism choices must not compose into globally pathological behaviour, a partial anchor.
- **Native fan-out** (A-05, A-06):
  - `ADC-04.b`: a worker-originated assignment is never recognized as authorized. It withholds authority, and it refuses nothing;
  - `ADC-04.m`: before admitting an agent with source-mutation capability, AEW enforces a launch profile that denies native agent creation outside AEW's coordination;
  - `HEB-03.c` and class C3 (A-06 §3.4): a qualified profile boundary denies any model-controlled actor an unauthorized agentic assignment, and default-denies unapproved provider reach and credentials;
  - `HEB-02.i`: the §3.4 denials must be demonstrated before mutable activation. No adopted rule requires them to be demonstrated before an advisor or investigator runs.
- **The semantics** (R-01, A-15; IF-10, A-21):
  - limits are the operator's or ADC's policy; R-01 defines the reservation and usage records; a protected writer qualifies admissions (`R01-01`, `R01-03`);
  - cost, time, concurrency and rate are four dimensions, and none substitutes for another (`R01-04`);
  - a resource class is declared per selected provider (`R01-09`), qualified per class with no omnibus flag (`IF10-06`), and a provider account's own cap is a separate scope (`IF10-12`);
  - a policy binds its scope and ancestors, its resource class, and the applicable work and revision; every child charges each enclosing limit, and a new generation, a handover or a nested advisor mints no budget (`IF10-02`, `R01-05`). Concurrent admissions against one parent are serialized (`R01-07`, `IF10-09`);
  - consumption and attribution that enforce a hard limit come from a meter outside the metered lineage's reach to write, substitute or bypass (`R01-08`, `IF10-13`). Without one, a hard-limit claim is `NOT_ESTABLISHED` (`IF10-20`, `R01-43`);
  - a broken connection, a timeout or a lost receipt never turns outstanding spend into zero (`R01-08`, `R01-10`, `IF10-15`). A requester's alias or lineage tag creates no charge capacity and moves no attribution (`IF10-07`);
  - a request that cannot be halted once dispatched is encumbered at its enforceable worst case before dispatch, or its class is `RESOURCE_UNSUPPORTED_FOR_HARD_LIMIT` (`R01-09`, `IF10-10`);
  - ongoing effects are "stopped/withheld at actual enforceable boundaries without falsely claiming remote cancellation" (`R01-09`);
  - each operation passes IF-10's typed gate, `HOLD` or `DENY` among its results, with its source, scope and currentness basis, compared against the current policy at effect time (`IF10-08`, `IF10-17`, `R01-39`);
  - each operation's chargeability is `MANDATORY_HARD`, `EXPRESS_COOPERATIVE`, provider-bound `NO_CHARGE`, `LOCAL_NO_EXTERNAL_EFFECT_FIXTURE` or `UNSUPPORTED_OR_UNKNOWN`, from the competent policy and a qualified producer (`IF10-03`). A mandatory-hard limit has a finite, enforceable bound, zero being a valid deny-all value (`IF10-05`). A cooperative class asserts no enforced cap (`IF10-11`). A changed route inventory invalidates the affected metering claims (`IF10-21`);
  - decisions route to the competent Lead or operator (`R01-35`); every release profile enumerates its hard-limit classes, its meter and its bypass coverage (`R01-42`).
- **The issuance** (I-6, A-39): a ceiling is a standing policy of the resource policy issuer, on the operator's G3 consent. On the 0.9 wire its target keys it by scope, provider, account, recipient and unit, with `enforcement` `MANDATORY_HARD` or `COOPERATIVE`, and names no resource class. A widening is `ISSUE_STANDING_POLICY` (`I6-03`). A narrowing or revocation is `NARROW_OR_REVOKE_STANDING_POLICY` (`I6-02`), whose enforcement narrows only from `COOPERATIVE` to `MANDATORY_HARD` (`I6-02.b`), and after which ongoing execution under a hard bound is held to the new bound at the class's enforceable boundaries, a dispatched request that cannot be halted completing and never reported cancelled (`I6-02.d`). Wall time, concurrency, rate and quota ceilings, and attempt ceilings, have no issuance (`I6-B1`), nor has headroom for an exhausted intent (`I2-B4`).
- **The two reads the frozen lines name:**
  - `I3-03`: ADC admits a delegation only if "the allocation fits the hard limits the resource policy issuer states", or "it holds when they are unavailable". A-43's refusal map gives those `RESOURCE_LIMIT_EXCEEDED` and `RESOURCE_LIMITS_UNAVAILABLE`. The 0.9 `DELEGATE_NEW_WORKER` target carries no amount;
  - the rerun: HEB admits it only if "R-01 shows headroom for one more attempt of the intent" (`ATTEMPT_LIMIT_REACHED`; `RESOURCE_STATE_UNAVAILABLE`, a hold), and a rerun never resets a ceiling (`I2-05`).
- **Ordering:** ADC's and HEB's admission paths read origin, then owner state, then the activation hold, then the owner's effect (`I3-12`, `I2-11`).
- **The Lead's autonomy** decides whether the Lead may delegate at all: `helper_delegation` is `NONE` or `WITHIN_GRANT`, set by the operator's `ADJUST_LEAD_AUTONOMY` (`I3-05`). Only the operator stops a delegated worker: `STOP_CHILD_NOW` and `SUSPEND_GRANT` are G3-protected, and the Lead's `DELEGATED_CANCEL` reaches only its own invocations.
- **The operator's selection of 2026-10-24** (`00-governance/decisions/2026-10-24-operator-first-selections-research-maps-knowledge.md`): model usage is R-01's first metered class. Its cap is an I-6 hard limit, metered at CS-3b's provider relay, which runs outside the metered lineage.

## The parts

- **The operator** adopts the row, and so defines its parameter. The operator sets a ceiling only through the issuer's standing policy, on G3 consent, and never qualifies a meter by adopting the row.
- **The resource policy issuer** holds each ceiling, and its `enforcement`, as a standing policy decision (`I6-02`, `I6-03`).
- **R-01's writer** keeps each unit's reservations, encumbrances and headroom (`R01-01`, `R01-05`).
- **The meter** for a unit observes consumption outside the metered lineage. For model usage it is the provider relay, which also asks IF-10's gate at each dispatch (`IF10-08`, `IF10-13`).
- **The host assessor,** outside every agent lineage, records whether a deployed profile meets the row for a unit (`AP5-01`). It qualifies the unit's meter, writer and bypass coverage, and never a unit's chargeability.
- **ADC** reads the row at a delegation (`I3-09`, `I3-03`); **HEB** reads it at a rerun (`I2-08`).

## Rules

**RHC-00. Precondition: A-05 §5's undefined-parameter and preservation rules, `I3-09`, `I3-03`, `I3-12`, `I2-05`, `I2-08`, `I2-11`, A-51's `AP5-01` to `AP5-07`, and A-39's `I6-02`, `I6-03` and `I6-08`, hold as adopted, except where a rule here adds to them.** Nothing here narrows a control, and nothing here is a new policy, spending or grant authority (`R01-01`, `IF10-01`).

**RHC-01. The resource-ceilings row.** A-05's text: "Resource hard ceilings and ongoing limit enforcement", required before "Controlled multi-agent execution".
- **Its definition:**
  - **the unit, a metered unit:** R-01's resource class for one selected provider and account (`R01-09`, `IF10-06`, `IF10-12`). A standing policy keys it by its provider, account and unit, within its scope and recipient. The 0.9 target names no resource class, so for V-01's one class, model usage, those keys identify the unit; a second class needs the target to name its class (`RHC-B4`). The units a worker can reach are the provider routes in its profile's route inventory (`IF10-21`, `HEB-03.a`). A local fixture with no external effect is no provider route, and this row reads nothing for it;
  - **a hard ceiling** is an operator-authorized hard limit (`ADC-08.f`, `AEW-FR-10.a`): a current standing policy decision of the resource policy issuer (`I6-03`), with `enforcement` `MANDATORY_HARD` and a finite maximum in its unit (`IF10-05`), bound to its scope and every ancestor scope, and to the work it applies to where it names one (`IF10-02`). A zero ceiling denies every positive-priced effect (`IF10-05`). Where a parent's ceiling is stricter, the parent's governs (`R01-05`);
  - **chargeability is the issuer's, never the assessor's:** each standing policy's `enforcement` is the issuer's field, one unit may have several policies at different scopes, and each operation's chargeability comes from the competent policy and a qualified producer (`IF10-03`). Of each unit a worker can reach:
    - a unit whose operations can carry a positive price needs the row met for it (`AP5-01`), and at least one current standing policy with `MANDATORY_HARD` enforcement covering the work's scope. A covering policy with `COOPERATIVE` enforcement is no hard ceiling: it neither counts as one nor blocks one, and its ceiling is still charged (`IF10-02`, `RHC-R03`);
    - a unit whose operations are established `NO_CHARGE` needs no spend ceiling, and still needs the row met for it (`AP5-01`) by the two cases of `RHC-02` that presuppose no charge: the meter outside the lineage, and every route metered. That a call is free is `IF10-03`'s qualified proof, not an `RHC-02` case; the meter seeing every route is what keeps a call outside that proof from passing as free;
    - a unit whose chargeability is unknown is read as one that can carry a positive price (`IF10-03`, `IF10-08`);
  - **the dimensions:** `R01-04`'s four. A spend ceiling has an issuance (`I6-03`). Wall time, concurrency, rate and quota ceilings apply where an issuance states them, and none can yet (`I6-B1`). This position adds no numeric ceiling of its own (`RHC-R02`);
  - **conservation:** a delegated worker, a nested advisor and a rerun each charge every enclosing ceiling, and reset none (`IF10-02`, `R01-05`). Two concurrent admissions never spend the same headroom (`IF10-09`, `R01-07`). An aborted request stays encumbered, and a requester's alias moves no charge (`R01-08`, `IF10-07`);
  - **ongoing limit enforcement** (`ADC-08.f`, `AEW-FR-10.f`): each further dispatch of a running worker passes IF-10's gate against the current ceiling and qualified headroom (`IF10-08`, `IF10-17`), at the class's declared granularity (`R01-09`). A dispatch that does not fit is withheld. A request that cannot be halted is encumbered at its enforceable worst case before it is sent (`IF10-10`), completes, and is never reported cancelled (`I6-02.d`). Withholding a dispatch stops no process (`RHC-R04`). What the withheld dispatch tells the worker and the Lead is `RHC-03`'s;
  - **controlled multi-agent execution** is what the frozen lines name for this row, and only that: a delegation of an `IMPLEMENTER` or a `DIAGNOSTIC` (`I3-09`), and a rerun (`I2-08`). The Lead's own dispatches pass IF-10's gate as every dispatch does, and this row holds none of them.
- **Its host test:** `RHC-02`.
- **Residue:** the dimensions with no issuance (`RHC-R02`); the cooperative policy (`RHC-R03`); what ongoing enforcement does to a running worker (`RHC-R04`); the rerun's attempt ceilings (`RHC-R06`).

**RHC-02. The host test, for each metered unit a worker's profile can reach.** A profile meets the row for a unit only as `AP5-01` defines it, from the installed suite run on that host from the actual worker identity, where the unit shows all of these:
- **the meter is outside the lineage:** the unit's writer and meter cannot be written, substituted or bypassed by the worker (`IF10-13`, `R01-08`, `IF10-20`);
- **every route is metered:** the profile's route inventory has no route to the unit that skips the meter (`IF10-21`). The worker's direct reach to a provider is denied by class C3, as qualified on that profile by the host test of the row the released effect rests on: the launch row for a delegation, and the launch or the mediation row for a rerun (`AP5-02`, `AP5-03`). This case cites that assessment and does not test it again, and it is current only while that assessment is (`AP5-01`);
- **conservation holds under contention:** two concurrent admissions against one ceiling with headroom for one never both proceed (`IF10-09`);
- **a request that cannot be halted is bounded:** it is encumbered at its enforceable worst case before dispatch, or the class reports `RESOURCE_UNSUPPORTED_FOR_HARD_LIMIT` (`IF10-10`, `R01-09`);
- **an aborted request stays encumbered:** a worker that drops the connection or ends its own process mid-request releases no encumbrance until qualified settlement (`R01-08`, `R01-10`, `IF10-15`);
- **a worker's own attribution moves nothing:** a request header, intent key or lineage tag the worker supplies moves no charge to another scope and adds no capacity (`IF10-07`, `R01-02`);
- **enforcement reaches a running worker:** once the ceiling is reached, or narrowed below what is spent (`I6-02.d`), the running worker's next dispatch of the unit is withheld, as A-01's AS-28 asks.

Each negative case meets `HEB-10.g`'s five conditions, as `AP5-01` requires. These are product tests, that the product refuses what it should, not attack probes.

**RHC-03. The row is read per delegation, and per rerun, by the owner that holds the type; each hold names one record.**
- **The units read:** the units the route inventory of the profile the worker or the rerun would run under reaches (`RHC-01`), for a delegation and a rerun alike. A profile whose qualified inventory reaches no provider route releases on that inventory alone, with no assessment for this row and no ceiling to read; the inventory is qualified by the launch or the mediation row's assessment (`HEB-03.a`, `AP5-01`).
- **ADC, at `DELEGATE_NEW_WORKER` for `IMPLEMENTER` or `DIAGNOSTIC`,** after owner state, as its activation hold (`I3-12`):
  - where the row is not met for every unit (`AP5-01`), the delegation is held with `POLICY_UNAVAILABLE`, and its `owner_evidence_ref` names `HEB-10.a`'s one entry for that profile and effect, which lists each unit not met;
  - where it is met (`AP5-01`), `I3-03`'s check reads this row's ceilings. A positive-priced unit with no current `MANDATORY_HARD` ceiling covering the work's scope holds the delegation with `RESOURCE_LIMITS_UNAVAILABLE`, its `owner_evidence_ref` naming the issuer's current-policy record for that unit's key, which shows any `COOPERATIVE` policy that covers it (`RHC-R03`). Headroom whose state is unknown holds it the same way, naming R-01's headroom record;
  - an enclosing ceiling with no qualified headroom left refuses it (`RESOURCE_LIMIT_EXCEEDED`), naming R-01's headroom record;
  - otherwise the allocation fits. The delegation carries no amount and mints no ceiling of its own: its worker charges every enclosing ceiling (`IF10-02`), so "fits" means some qualified headroom is left in each.
- **HEB, at `REQUEST_BACKGROUND_RERUN`,** after owner state, as its activation hold (`I2-11`):
  - where the row is not met for every unit (`AP5-01`), the rerun is held with `POLICY_UNAVAILABLE`, naming `HEB-10.a`'s entry as above;
  - where it is met (`AP5-01`), the rerun's resource check also reads this row's ceilings. A positive-priced unit with no current `MANDATORY_HARD` ceiling, unknown headroom, or no qualified headroom left holds it with `RESOURCE_STATE_UNAVAILABLE`, naming the issuer's record or R-01's, as `I2-05` names R-01's own fact. The rerun's refusal map has no reason for an exhausted ceiling, so that reason covers exhaustion too: a held, waiting decision (`R01-31`), told apart by the record it names;
  - the attempt check is `I2-05`'s, unchanged: no attempt headroom is `ATTEMPT_LIMIT_REACHED`, and R-01's attempt state unavailable is `RESOURCE_STATE_UNAVAILABLE`. With no attempt ceiling issued, the rerun is held (`RHC-R06`).
- **A withheld dispatch says why** (the reset's rule that a refusal says what happened and what to do instead): IF-10's `HOLD` for a running worker's dispatch carries the unit, the ceiling's policy record and R-01's headroom record (`IF10-08`), and the route back: the operator's widening (`ISSUE_STANDING_POLICY`), or a qualified release (`REQUEST_CHARGE_RECONCILIATION`). Each party sees what it is entitled to (`IF10-19`):
  - **the worker** sees the narrowed status: that the unit's ceiling is reached, and that the route back is the operator's. It sees no record reference, amount or other consumer's usage;
  - **the operator,** and the Lead as far as its D-01 entitlement reaches, see the records and amounts, the Lead in HEB's report of the delegated child. A Lead whose own dispatches are under the same exhausted ceiling is withheld too; the decision then goes to the operator (`R01-35`), who alone widens (`R01-05`).
- **An `ADVISOR` or `INVESTIGATOR` delegation** is never held by this row (`AP5-R07`).

**RHC-04. What the row releases, and only that.** The table below is derived from the frozen `I3-09` and `I2-08` tables. The gate requires its pairs to equal theirs, each cell's opening words to follow from every A-05 §5 row the frozen lines for its type name, and each line's own condition to be stated. Holds are per effect: an effect held by more than one row is released only when all of its rows are adopted and met (`AP5-01`).

**The openings:** "released with A-51's" rows, naming each, where every other row on the type's frozen lines is adopted in A-51; "not released" for a role whose frozen line names a row that is not adopted, naming that row; "released by this row alone" where no other row holds the type.

| Type or owner act | Rule | Frozen clause | What adoption changes |
|---|---|---|---|
| `DELEGATE_NEW_WORKER` | `RHC-01` | `I3-09` | released with A-51's `AP5-02`, `AP5-04` and `AP5-05`, where each is met (`AP5-01`): every `IMPLEMENTER` delegation, step 6a's among them. HEB's launch reads `AP5-02`; ADC's admission reads `AP5-04`, `AP5-05` and this row. For `DIAGNOSTIC`, not released: the diagnostic row |
| `REQUEST_BACKGROUND_RERUN` | `RHC-01` | `I2-08` | released with A-51's `AP5-03` and `AP5-02`, where each is met (`AP5-01`): `AP5-02` reaches only a prior operation whose definition mutates source. It still waits for an attempt ceiling, which nothing issues yet (`RHC-R06`) |

**Not in the table, and not a leak:**
- **The Lead's own dispatches** are not controlled multi-agent execution, and no frozen line holds the Lead's attachment for this row. They pass IF-10's gate, and the ceilings that bind them bind them there (`IF10-08`).
- **`REAFFIRM_ELIGIBLE_CHILD_GRANTS` and `CONTINUE_ELIGIBLE_WORK`** are in no frozen hold table. A reaffirmed or continued worker charges the same enclosing ceilings (`IF10-02`), and every dispatch passes IF-10's gate.
- **Advisors and investigators,** and any harness-native child, are no O-01 hold of this row. Their consequence is stated in `RHC-R02`.

**RHC-05. A-48's step 6a and the rerun are read with `RHC-01` to `RHC-04` and with A-51.** A built owner conforms to the hold tables, A-51 and this position together.

## Interfaces

- **No O-01 schema byte changes.**
  - `POLICY_UNAVAILABLE` is already mapped for both held types, so "adopted but not met" needs no new refusal (`AP5-01`).
  - `DELEGATE_NEW_WORKER`'s `RESOURCE_LIMITS_UNAVAILABLE` and `RESOURCE_LIMIT_EXCEEDED`, and `REQUEST_BACKGROUND_RERUN`'s `ATTEMPT_LIMIT_REACHED` and `RESOURCE_STATE_UNAVAILABLE`, are already mapped on the 0.9 wire.
  - On 0.9, `POLICY_UNAVAILABLE` and `RESOURCE_LIMITS_UNAVAILABLE` both map to `SOURCE_UNAVAILABLE`, so the outcome's `owner_evidence_ref`, one record per hold, is what tells them apart (`RHC-03`). The field already exists.
- **The O-01 types whose effects this position touches:**
  - held, as `RHC-04` lists: `DELEGATE_NEW_WORKER` and `REQUEST_BACKGROUND_RERUN`;
  - read as they are: `ISSUE_STANDING_POLICY` and `NARROW_OR_REVOKE_STANDING_POLICY`, which set the ceilings and their enforcement; `REQUEST_CHARGE_RECONCILIATION`, which reconciles an unknown charge against them; `REVOKE_HOST_QUALIFICATION`, which reaches this row's assessments; `ADOPT_MANIFEST_EDIT` and `REQUEST_PROFILE_CHANGE`, whose route changes change the units a worker can reach (`IF10-21`); `ADJUST_LEAD_AUTONOMY`, whose `helper_delegation` decides whether the Lead may delegate (`I3-05`); `STOP_CHILD_NOW` and `SUSPEND_GRANT`, the operator's stops (`RHC-R04`);
  - touched and not held: `REAFFIRM_ELIGIBLE_CHILD_GRANTS` and `CONTINUE_ELIGIBLE_WORK` (`RHC-04`).
- **The activation determination** that `HEB-10.a` requires gains, in its one entry per profile and effect, the units this row is not met for (`AP5-01`). **Candidate (D-01):** with `AP5-B1`'s read, each unit's ceiling and headroom, read from the issuer's and R-01's own records, and whether the row is met for it (`AP5-01`, `RHC-B1`). HEB copies neither fact.
- **The governance clauses:** this position adds to A-30's `I3-09`, `I3-03` and `I3-12` reading and to A-34's `I2-05`, `I2-08` and `I2-11` by addition, and refines A-51's `AP5-01` by addition. A-51's Q3 answered A-51's own additions, not these, so the adoption proposal asks again. A-51's record has no wire clause.

## The gate

`check_rhc.py` is a derivation check: it reads the frozen bytes and this file, and builds no model. Each row states what it reads; the scope column is its limit.

| Check | What it shows | Scope and vocabulary | Pass |
|---|---|---|---|
| **RHC-Q01** | The A-05 text `RHC-01` quotes, the row's parameter and its "Required before", equals A-05 §5's frozen bytes. | `RHC-01`'s quotation | exact match |
| **RHC-Q02** | `RHC-04`'s table equals the pairs of this row and a type parsed from the frozen `I3-09`, `I4-06` and `I2-08` tables. Each cell's opening follows from every A-05 §5 row the frozen lines for its type name: "released with A-51's" naming each row A-51 adopted, read from A-51's frozen copy; "not released" naming each row that is not adopted, a role-bound row for its role; or "released by this row alone". Each frozen line's own condition is stated in the cell: the roles it names, and, for a line that does not name this row, the last words of its condition. | the table's cells; rows matched by their first two words, punctuation normalised | the same set, both ways; every opening and condition as derived |
| **RHC-Q03** | Every requirement ID this file cites resolves in D1, as a requirement or a named cross-reference. | backticked IDs in the ID grammar, and plain-text A-01 scenario IDs (`AS-` and a number) | none unresolved |
| **RHC-Q04** | Every owner reason named for a type is mapped for that type in A-43's frozen refusal map, and `POLICY_UNAVAILABLE` is mapped for every type `RHC-04` names. | the Interfaces' "type's reason" pairs; `RHC-03`'s ADC and HEB bullets; each scenario, for the held types it names | every pair |
| **RHC-Q05** | `RHC-01` names its definition, its host test and its residue, and every residue it names is a ruling here. Each of `RHC-02`'s seven cases is a bullet that cites its clause. | `RHC-01`, and `RHC-02`'s bullets by their bold lead | each |
| **RHC-Q06** | Every clause that says a profile meets, does not meet, is unmet for, satisfies, passes or qualifies for the row cites `AP5-01`. | Rules, Scenarios, Rulings and Interfaces, split into clauses at full stops and semicolons; the verbs meet, met, unmet, satisf…, and "pass… for" or "qualif… for" within 30 characters of "row" | none uncited |
| **RHC-Q07** | `RHC-03` reads one set of units for a delegation and a rerun alike. | the "units read" bullet; in each owner bullet, the words after "for every unit" up to the next comma or full stop, citations in brackets removed | one set |
| **RHC-Q08** | This table lists every check `check_rhc.py` runs, and no other. | the table's first column, and the script's own check names | the same set |

## Scenarios

**RHC-X01.** The operator adopts the row. The issuer holds two `MANDATORY_HARD` model-usage ceilings for one provider and account: one for the project, and one scoped to a Ticket (`IF10-02`). The host assessor has qualified a Linux host's profile for the launch and mediation rows, and for this row's model-usage unit (`AP5-01`). The Lead delegates an implementer for a one-line fix on that Ticket (step 6a): ADC admits it, and HEB launches it. Midway, the Ticket's ceiling is reached. The request already sent completes, encumbered at its worst case. The worker's next dispatch is withheld at the relay, with a hold naming the Ticket's policy, R-01's headroom record and the route back, and nothing stops the worker. The Lead, whose dispatches charge only the project's ceiling, sees the same records on the child. The operator widens the Ticket's ceiling with `ISSUE_STANDING_POLICY`, and the worker's next dispatch passes, under its existing grant (`ADC-08.k`), with no new delegation.

**RHC-X02.** On a profile the assessor has not qualified for this row (`AP5-01`), the same delegation is held with `POLICY_UNAVAILABLE`, and its `owner_evidence_ref` names `HEB-10.a`'s entry, which lists the model-usage unit. On a qualified profile (`AP5-01`) where the issuer states no model-usage ceiling for the project, it is held with `RESOURCE_LIMITS_UNAVAILABLE`, naming the issuer's current-policy record for that key. The Lead can tell the two apart: one needs the assessor, the other a ceiling.

**RHC-X03.** Two implementers run under one ceiling whose headroom covers one more worst-case request. Both ask to dispatch at once: one request is encumbered and sent, and the other is withheld (`IF10-09`). One implementer then drops its connection mid-request; the encumbrance stays (`R01-08`). Neither implementer is recognized as delegating further (`ADC-04.b`), and the launch row's profile denies them native agent creation (`ADC-04.m`, `HEB-03.c`).

**RHC-X04.** A worker profile's route inventory also reaches a second provider, whose only standing policy covering the project has `COOPERATIVE` enforcement. That unit has no hard ceiling (`RHC-R03`), so an implementer's delegation under that profile is held with `RESOURCE_LIMITS_UNAVAILABLE`, naming the issuer's current-policy record for that key. The route back: the operator narrows that policy to `MANDATORY_HARD` (`NARROW_OR_REVOKE_STANDING_POLICY`, `I6-02.b`) or issues a hard ceiling for the scope, and the host assessor records the unit's meter for that profile (`AP5-01`). Or the operator removes the route with `ADOPT_MANIFEST_EDIT`. Either way the delegation is then admitted. Had a hard Ticket ceiling also covered the work, the cooperative project policy would have blocked nothing.

## Rulings

**RHC-R01. "Met" is `AP5-01`'s, read per metered unit.**
- **The reason:** `AP5-01` gives an adopted row one meaning of "met", and IF-10 qualifies resource control per class, with "no omnibus `hard_budget_supported` boolean" (`IF10-06`). A class is declared per provider (`R01-09`), and a provider account's cap is its own scope (`IF10-12`). So the assessor's record for this row names the unit, and a profile meets the row for one unit and not another (`AP5-01`).
- **The consequence:** a delegation or rerun is released only where the row is met for every unit the profile can reach (`AP5-01`, `RHC-03`). A unit a worker cannot reach does not hold it.

**RHC-R02. The dimensions with no issuance (the operator's question at adoption).**
- **The question:** `ADC-08.f` names concurrency, usage, rate and spending limits. Only spend has an issuance (`I6-03`). Wall time, concurrency, rate and quota have none, and neither have attempt ceilings or headroom for an exhausted intent (`I6-B1`, `I2-B4`), nor the advisor caps R-01 states for a root lineage: simultaneous consultations, rate, cumulative attempts and recursion depth (`R01-22`, `R01-23`). Does a `MANDATORY_HARD` spend ceiling on every positive-priced unit a worker can reach, with conservation across every nested agent, define the row for V-01?
- **What a yes means, stated plainly:**
  - the only hard ceiling under this row is a spend cap per issued standing policy, metered at the provider relay, and effective only once the host assessor qualifies that meter on a profile (`AP5-01`, `RHC-R05`). Adoption releases nothing on any profile until then;
  - every `IMPLEMENTER` delegation is released where the rows are met (`AP5-01`), not one. Nothing bounds how many implementers the Lead delegates, how many run at once, how fast they call, or how long they run. The Lead's autonomy decides only whether it may delegate at all (`I3-05`);
  - a delegation carries no amount, so one worker can use up headroom that its siblings, and the Lead where its dispatches share the scope, also use. A ceiling scoped to a Ticket (`IF10-02`) keeps one Ticket's workers from the rest of the pool. At exhaustion the remedies are the operator's: a widening, a qualified release, or a stop (`RHC-R04`);
  - a unit established `NO_CHARGE` runs with no ceiling in any dimension, though `IF10-03` and `IF10-08` subject it to any applicable request, rate, quota and concurrency policy, of which none can yet be issued;
  - a rerun's attempt check reads attempt ceilings that nothing issues (`I6-B1`). With none issued, R-01 cannot show headroom for one more attempt, so every rerun stays held with `RESOURCE_STATE_UNAVAILABLE` until an attempt ceiling exists: adopting this row lifts the rerun's §5 hold, and releases no rerun in practice yet (`RHC-R06`);
  - workspace cost, disk among it, is no metered unit and has no issuance, so this row does not bound it;
  - advisors and investigators: no §5 row holds them (`AP5-R07`). R-01 requires an advisor's profile to be non-delegating (`R01-21`) and caps a root lineage's consultations, rate, attempts and recursion depth (`R01-22`, `R01-23`). But no adopted rule requires the profile to demonstrate C3 before an advisor runs (`HEB-02.i` is for mutable activation), and no cap can be issued. So a harness-native fan-out they start is not refused: it draws on the same pool. It is capped only where a `MANDATORY_HARD` ceiling covers their work's scope and the route passes the meter. Under cooperative coverage only, nothing enforces a cap (`IF10-11`, `AP5-R07`), and where a route skips the meter, its spend is under no ceiling (`R01-43`).
- **Recommended:** yes.
  - `ADC-08.f` enforces "operator-authorized" limits. Where the operator can authorize none, there is none to enforce. An AEW numeric maximum added here would be a limit with no measured source, which A-51 refused for grant lifetimes on the same ground (`AP5-R03`).
  - Native fan-out by an implementer is denied by the launch row's profile, not by a limit: `ADC-04.m` and `HEB-03.c`, with C3, demonstrated before mutable activation (`HEB-02.i`). That is the capability-layer refusal the study asks for, for implementers. The study's recursive incident was review agents spawning review agents, which in AEW are advisor or investigator delegations: the case this departure leaves bounded by spend only, and the one alternative 2 would refuse.
  - **Why yes still stands for that case:** an advisor's or investigator's grant permits no protected or source-mutating effect (`I3-03`), and its native children get no authority (`ADC-04.b`). So what the incident's shape can cost here is spend. Where a `MANDATORY_HARD` ceiling covers their work's scope and their routes pass the meter, the spend ceiling bounds it: every dispatch of every child is charged and withheld at the ceiling (`IF10-02`, `IF10-08`), and a Ticket-scoped ceiling bounds one Ticket's share. Under cooperative coverage only, or where a route skips the meter, nothing in this row bounds it (`IF10-11`, `R01-43`). Refusing the shape at the capability layer too is alternative 2, which amends adopted text and so is the operator's to choose.
  - **The advisor caps R-01 already states** (`R01-22`, `R01-23`) are the adopted clauses closest to the study's case, and their absence holds nothing on an adopted path today. That differs from the rerun's attempt ceiling (`RHC-R06`) for one reason: `I2-05` is a selected, adopted admission check that requires R-01 to show headroom, while R-01's advisor authorization stages are deferred to selected-profile work (R-DEC-05) and no adopted profile has selected them. A-30's delegation check reads only the issuer's hard limits (`I3-03`), and its grant record binds no recursion or attempt count. When a profile selects them, a missing cap holds there as `RHC-R06` reads `I2-05`. `R01-23`'s "a missing bound holds affected paid admission" is the worst-case bound for unpriced usage, which `IF10-10` and this row already hold. Whether `R01-22` holds an advisor's invocation before then is ADC's and R-01's owner's reading, which this row neither makes nor relies on (`RHC-B6`).
  - **Where it departs from the study:** for advisors and investigators the study's capability-layer refusal is not demonstrated, and their fan-out is bounded by spend only. Fan-out is not budgeted together with workspace cost, and `AEW-INV-RESOURCE-001`'s composition stays a partial anchor. V-01 selects no concurrent missions (the selection of 2026-10-24), and a spend ceiling bounds every metered dispatch whatever the fan-out.
  - When a concurrency, rate, quota or attempt ceiling gains an issuance (`I6-B1`), it is a hard ceiling under `RHC-01` from then on, with no change to this position.
- **The alternatives:**
  - **wait for `I6-B1`:** the row waits for an issuance of at least a concurrency ceiling. That is a new I-6 type or a wider standing-policy target, so a new O-01 wire and its own stage, and step 6a waits for both;
  - **also hold advisors and investigators** under this row, read for their profiles. That amends A-30's frozen `I3-09` line, which never holds them (I3R1-6), so it is the operator's (`RHC-B5`). It holds more, and releases nothing.

**RHC-R03. A cooperative policy is never a hard ceiling.**
- **The reason:** the row asks for hard ceilings. A mandatory-hard limit has a finite, enforceable bound (`IF10-05`), and a cooperative class "SHALL NOT assert protected `RESERVED`, enforced Ticket cap or guaranteed remaining capacity" (`IF10-11`). On an unqualified host every class reads that way (`R01-43`).
- **Read per policy, as the issuer's fact:** `enforcement` belongs to each standing policy, and one unit may have several. A positive-priced unit needs at least one covering `MANDATORY_HARD` ceiling. A covering `COOPERATIVE` policy neither counts nor blocks, and its ceiling is still charged (`IF10-02`). "Met" stays the assessor's alone (`AP5-01`), so a unit covered only by cooperative policies is held with `RESOURCE_LIMITS_UNAVAILABLE`, naming the issuer's record, never with `POLICY_UNAVAILABLE` (`RHC-03`).
- **The route back** is the issuer's: the operator's narrowing to `MANDATORY_HARD` (`I6-02.b`), or a hard ceiling issued for the scope. The assessor never makes a policy hard. The operator's standing cooperative decision (`IF10-04`) still serves the dispatches it covers outside this row, the Lead's among them; it never releases a held delegation.

**RHC-R04. Ongoing enforcement withholds dispatches; it stops no worker.**
- **The reason:** `R01-09` enforces at "actual enforceable boundaries without falsely claiming remote cancellation", and `I6-02.d` holds ongoing execution to a narrowed bound the same way. Withholding a dispatch is IF-10's refusal of one effect (`IF10-08`). Stopping a worker automatically is a consequential stop, which the unadopted row "Hold/provisional hold qualification …" is required before; I-6 reads it so (`I6-10`).
- **The consequence:** at the ceiling a worker's dispatches of that unit are withheld, and its other permitted work goes on (`ADC-08.i`). Stopping it is the operator's, by `STOP_CHILD_NOW` or `SUSPEND_GRANT`; the Lead may ask the operator for one, and otherwise the worker's grant ends at its finite expiry (`I3-03`). When headroom returns, by a widening or a qualified release, the worker continues under its existing grant (`ADC-08.k`).

**RHC-R05. Model usage at the provider relay is the first class, by design, not by qualification.** The operator's selection of 2026-10-24 places the meter. The relay qualifies nothing until the host assessor records it for a profile (`AP5-01`, `IF10-20`, `R01-43`), and every route a worker can reach must pass it (`RHC-02`).

**RHC-R06. With no attempt ceiling issued, a rerun stays held.**
- **The reason:** `I2-05` admits a rerun only where "R-01 shows headroom for one more attempt of the intent", and attempt ceilings are keyed per intent (`R01-31`). None can be issued (`I6-B1`, `I2-B4`). A bound that no competent policy states is `NOT_SPECIFIED`, and "no AEW numeric maximum" is meaningful only "when competent policy actually permits it" (`IF10-05`). So R-01 cannot show headroom, and its attempt state is unavailable.
- **The consequence:** every rerun is held with `RESOURCE_STATE_UNAVAILABLE`, naming R-01's record that no attempt ceiling is held, until one exists. `ATTEMPT_LIMIT_REACHED` applies once a ceiling exists and is exhausted. Adopting this row lifts the rerun's §5 hold and nothing more.
- **The route back from a host revocation** (`AP5-R05`) is therefore a new delegation until an attempt ceiling exists; its rerun half is empty until then.
- **The alternative rejected:** reading no attempt ceiling as unbounded attempts would treat a missing limit as permission, which A-05 §5's undefined-parameter rule forbids.

## Backlog

**RHC-B1.** The D-01 read of each unit's ceiling and headroom, from the issuer's and R-01's records, and the row's state for it, joined to `AP5-B1`'s read and to I-6's standing-policy read.

**RHC-B2.** Ceilings other than spend, if the operator takes `RHC-R02`'s first alternative or a later selection needs one: `I6-B1`'s issuance, with attempt headroom (`I2-B4`).

**RHC-B3.** A-05 §5's other nine unadopted rows, each when a selected step needs it. The diagnostic row holds a diagnostic's delegation.

**RHC-B4.** A standing-policy target that names its resource class, needed before a second metered class: a later wire.

**RHC-B5.** Holding advisor and investigator delegations under this row, if the operator takes `RHC-R02`'s second alternative: an amendment of A-30's `I3-09` line.

**RHC-B6.** For ADC's and R-01's owner: `R01-22` binds an advisor's recursion and attempt count before its invocation, and A-30's grant record carries neither. The reading owed is whether an advisor's invocation holds until R-DEC-05 selects R-01's advisor stages and `I6-B1` can issue the caps, or waits for that selection.

## Not covered

- **G3.** Every protected step waits for G3 wherever it is not established.
- **I5-08a's content read,** which W09 and A09 also wait for.
- **The build** of the provider relay's meter, R-01's writer, IF-10's gate, and the assessor's suite cases for this row.
- **Any profile's assessment** for this row.
- **Ceilings other than spend** (`I6-B1`), and workspace cost.

## Changes

- **Revision 1 (2026-11-01):** the first text, after the advisor's check on STG-27's shape (`STAGE.md`).
- **Revision 2 (2026-11-01):** round 1's eight findings, mapped in `CHANGES-r2.md`:
  - `RHC-R02` cites what denies native fan-out (`ADC-04.m`, `HEB-03.c`, C3) and says where it is demonstrated, states plainly what a yes leaves unbounded, and offers two alternatives;
  - the unit is defined: R-01's resource class per provider and account, keyed as the 0.9 policy keys it; chargeability is the issuer's; the assessor qualifies the meter only; a `NO_CHARGE` unit still needs the row met;
  - the rerun reads the same units as a delegation, with the empty case and a ceiling read;
  - each hold names one record, and a withheld dispatch says why and what to do;
  - the host test gains the aborted-request and attribution cases, and cites C3 from the row the released effect rests on;
  - `RHC-R04` names the operator's stops; the Interfaces list them and `ADJUST_LEAD_AUTONOMY`;
  - the gate states each row's scope, and reads line conditions, plain scenario IDs, scenarios' reasons, clauses and more verbs;
  - citations: `I3-12` and `I2-11`, the departure from "the target alone", `AP5-R03`, A-43's map.
- **Revision 3 (2026-11-01):** the quick check's five items, mapped in `CHANGES-r3.md`:
  - `RHC-R02` places the study's recursive incident correctly, as advisor or investigator delegations, and says why yes still stands for that case;
  - a cooperative policy is read per policy and is never a hard ceiling; "met" stays the assessor's alone (`RHC-R03`);
  - the worker sees `IF10-19`'s narrowed status of a withheld dispatch;
  - with no attempt ceiling issued, a rerun stays held (`RHC-R06`), and the attempt reasons are named rightly;
  - the gate table gains `RHC-Q07` and `RHC-Q08`; the `NO_CHARGE` unit's cases are named; exhaustion under `RESOURCE_STATE_UNAVAILABLE` is said.
- **Revision 4 (2026-11-01):** the narrow check's three riding items, in the adoption pass, mapped in `CHANGES-r4.md`:
  - `RHC-R02` names R-01's advisor caps (`R01-22`, `R01-23`) as unissuable, and says why their absence holds nothing on an adopted path where `RHC-R06`'s does (new backlog item `RHC-B6`);
  - the advisor bullets say the ceiling bounds them only where a `MANDATORY_HARD` ceiling covers their work;
  - `RHC-R06` says the route back from a host revocation is a new delegation until an attempt ceiling exists.
