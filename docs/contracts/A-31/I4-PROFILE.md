<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-31
source: 30-stages/STG-09-I4-aev-assurance-and-holds/adopted/o01-0.6-i4/I4-PROFILE.md
source-sha256: 99ab4cc70c459b4798ce541f40e90963311be1ed7a29644aaa1963cf080d4028
edits-sha256: none
-->

# I-4: AEV assurance and holds, selection profile (PROPOSED contract pass, revision 2.3, 2026-10-22)

**Wire:** O-01 `o01-command-0.6-candidate`, in `wire/`. It is A-30's 0.5 wire plus four action types, generated from A-30's frozen bytes by `tools/build_i4_wire.py`.
**Stage:** `STAGE.md`. **Start:** `00-governance/decisions/2026-10-22-operator-start-I-4.md`. **Revision 2** answers round 1 (`reviews/2026-10-22-I4-review-round-1.md`, `FINDINGS.json` source `I4R1`); what changed is in `CHANGES-r2.md`. **Revision 2.1** answers the targeted check (`reviews/2026-10-22-I4-check-r2.md`, source `I4C2`), in `CHANGES-r21.md`. **Revision 2.2** answers the delta check (`reviews/2026-10-22-I4-check-r21.md`, source `I4C3`), in `CHANGES-r22.md`. **Revision 2.3** answers the targeted check of 2.2 (`reviews/2026-10-22-I4-check-r22.md`, source `I4C4`), in `CHANGES-r23.md`.
**How to read it:** as I-3's profile. Each rule states an outcome: what must hold, who owns it, what is refused, and the adopted rule it must not contradict. Text marked **Candidate** is a starting point for the build, which may meet the outcome another way.
**Rule names:**
- `AEV-05.a` and the like are A-07's guarantees; `HEB-07.e` A-06's; `CNI-05.e` A-09's; `AOI-07.c` A-10's; `WIS-06.b` A-08's; `ADC-07.h` A-05's.
- `I1-05`, `I5-03` and `I3-06` are the adopted I-1 (A-28), I-5 (A-29) and I-3 (A-30) profiles.

## I4-00. The fit: which rows need a new O-01 type

**The departures from the proposed classification come first,** each with the adopted text it rests on. The operator confirms or refuses each at adoption.

| Row | The classification proposed | This profile | The adopted text | What changes for the operator |
|---|---|---|---|---|
| W06 | `OPERATOR_ORIGIN_G3` | delegated, owner AEV | ADC-07.d: "AEW shall permit **the Lead** to submit counterevidence and request reassessment of a disputed mandatory review finding" | **The operator's half of `O/D` is dropped** (I4R1-9): the operator is never a disputing party, and AEV-10.f rules out "operator permission to ignore the dispute". An operator request for reassessment is backlog I4-B5 |
| C15 | `OPERATOR_ORIGIN_G3`, owner AEV | **delegated, owner HEB** | HEB-07.e: "hold post-detach drain results for **current-authority acceptance**". A-06 §5's disposition table: after a routine handover, results are "Held until current authority qualifies". HEB-X11: "normal handover remains cheap" | The current Lead, not the operator, takes a routine generation's held result into current review. **This loosens the classification's proposal** and needs the operator's confirmation. A result from a revoked producing lineage is never taken in this way (I4-04). **HEB-07.b** reserves "authority-increasing lifecycle operations" to the operator or the governing issuer (I4C2-4). Accepting a held result into review is not one: it changes no grant, attachment or seat, and ends one custody hold, leaving the result review input only (I4-01a). It is the act HEB-07.e itself names, "current-authority acceptance", and HEB-07.i says the same: "held for current authority rather than automatically accepted" |
| W09 | owner AEV | owner CNI; integration only | CNI-05.a: Coordination claims integration readiness and "consumes rather than authors the AEV basis or determinations". CNI-03.g enforces the promotion on the mediated path | `RELEASE` is not selected (I4R1-5): no adopted owner fact defines it. Backlog I4-B2 |
| C16 | its own type, owner AEV | **no type: served by A12's AEV variant** | A result held in the current generation is a result under an AEV hold, and A12 answers that hold with AEV's own recovery options (D-01 `FR_HoldRecoveryProjection`, `request_review`) | The Lead's path is A12's, under its option discipline (I4R1-3). **The operator's half of `O/D/Q` is dropped** (I4C2-5): an operator request for re-evaluation joins backlog I4-B5 |
| C10 | its own type, owner AEV | **no type: integration is served by C15, then AEV's own determination, then W09.** An external publication is A-30's A09 | HEB-07.e holds drain results against "publication, integration advancement, or evidence acceptance". A-06 §5: "earlier publish-if-clean authorization never transfers". IF13-13: no change may "retroactively publish held results" | **Integration** of a held result needs C15, AEV's determination and W09, in that order, each under current authority (I4R1-2). **An external publication** is A-30's A09: an operator-consented exact effect, and **not ordered after C15 or AEV** (I4C2-3). A09 reads neither HEB's custody nor the producing lineage's trust. That is backlog I4-B4, widened accordingly. A fresh operator consent is not publication "merely because an old invocation finished" (HEB-07.e) |

**The fit for all eight rows:**

| Row | Catalogue symbol | Kind letters | Fit | Reason |
|---|---|---|---|---|
| A12 | `RESOLVE_OWNER_IMPOSED_HOLD` | Q/D | **New type `REQUEST_HOLD_RESOLUTION`, delegated, owner AEV: the AEV variant** (I4-02). It also serves C16 | Its owner text: "Exact imposing owner (AEV/HEB/R-01-specific typed variant in the selected registry) independently confirms resolution; operator G3 does not replace AEV PASS or release mandatory guard. No in-product operator-lift button for an owner HOLD". Releasing a hold is authority-increasing whatever it is called (AOI-07.c), so no request releases one. The hold clears only by the imposing owner's own determination (CNI-05.e, WIS-06.b). One registry row has one sole admitting owner (AOI-07.b), so each imposing owner gets its own variant. **This pass defines AEV's;** HEB's and R-01's are I4-B3 |
| W06 | `REQUEST_INDEPENDENT_REASSESSMENT` | O/D | **New type, delegated, owner AEV** (I4-03) | As in the departures table. AEV owns the finding and the dispute record; **ADC owns the adjudicator's selection** (ADC-07.h; A-07 §6.1 question 1). The target has no field for an arbiter |
| C15 | `REFER_HELD_FOR_CURRENT_REVIEW` | O/Q | **New type `REFER_HELD_RESULT`, delegated, owner HEB** (I4-04) | As in the departures table |
| C16 | `REQUEST_HELD_REEVALUATION` | O/D/Q | **Served by `REQUEST_HOLD_RESOLUTION`** (its `catalog_ids` list C16) | As in the departures table. "May create a new review operation, not replace original receipt": A12's `request_review` submission does exactly that (AEV-05.b, AEV-06.g) |
| C10 | `REQUEST_RESULT_PUBLICATION` | O/Q | **No type: integration served by C15, AEV, then W09; external publication is A09** | As in the departures table. "Old publish intent does not carry forward" holds by construction: the old generation's W09 and A09 consents are bound to its revision and its grants, which ended with it (I3-07) |
| W09 | `APPROVE_INTEGRATION_OR_RELEASE` | O/Q | **New type `APPROVE_INTEGRATION`, protected, owner CNI: integration only** (I4-05) | As in the departures table. CNI-06.d keeps technical assurance, operator acceptance, deployment permission and production publication apart: production publication is A09's exact effect; operator acceptance and deployment permission have no adopted owner fact on the wire (I4-B2) |
| A10 | `RESET_INTEGRATION_BREAKER` | O/Q | **No type: no adopted owner fact to act on** (I4-B1) | No adopted source defines an integration breaker. The catalogue itself hedges the owner ("Governing integration/assurance owner"). Defining one here would invent an owner fact and its limits (the operator's no-magic-limits rule) |
| W08 | `ADMIT_EVIDENCE_OR_FINDING` | Q | **No type: an owner decision** (I4-08) | Origin class `OWNER_DECISION`, as L10 was for I-5. "Neither UI nor operator click forges check proof": admission is each evidence owner's own act under AEV-05 |

**Four rows get a type, two are served by those types and adopted ones, and two need none.** Three of the four types are delegated (A12, W06, C15); one is protected (W09).

**I4-00a. No inherited definition changes.** The closed owner enums already list `HEB`, `CNI` and `AEV`. A-30's 27 actions, branches, targets, registry rows and refusal entries are carried byte-equal.

**The protection direction, by I5-00's rule:** every I-4 type is `PRESERVING_OR_INCREASING`.
- `REFER_HELD_RESULT` ends HEB's hold on one result, and `APPROVE_INTEGRATION` promotes a package: both are authority-increasing (AOI-07.c). The adopted text gives the first to the current authority (HEB-07.e), and the second needs G3.
- The two AEV request types release nothing and reduce nothing.

## I4-01. Who owns what, and the one rule for every Q row

| Type | Records the fact (sole admitting owner) | Whose decision the origin carries | Read only, as an input |
|---|---|---|---|
| `REQUEST_HOLD_RESOLUTION` | **AEV:** a recovery submission against one hold version | the Lead's, within its delegated authority | AEV's own hold and its options. ADC: the Lead's grant. HEB: the principal is the seat's current Lead |
| `REQUEST_INDEPENDENT_REASSESSMENT` | **AEV:** a dispute of one finding version, with the counterevidence | the Lead's (ADC-07.d) | AEV's own class of the finding. ADC: the Lead's grant, and later the adjudicator's selection. HEB: the current Lead |
| `REFER_HELD_RESULT` | **HEB:** the current authority's acceptance of one held result into current review (HEB-07.e) | the current Lead's | HEB's own custody of the result and the seat. ADC: the Lead's grant, and the trust state of the result's producing lineage. WIS: the work's current accepted revision |
| `APPROVE_INTEGRATION` | **CNI:** one exact package promoted to accepted input | the competent authority's for the work's project boundary (I3-01's form) | AEV: the package's current readiness, with its trust basis. ADC: the current trust state of every lineage in that basis, and its competence fact. WIS: the revision and project |

**I4-01a. Consent never stands in for an owner's qualified determination.** For every I-4 type:
- **no consent, Lead request or click records a PASS, an evidence admission, a hold's resolution or a finding's disposition** (AEV-05.g, CNI-05.e, ADC-07.c; A12's "operator G3 does not replace AEV PASS"; W08's "neither UI nor operator click forges check proof");
- **a request type records a request.** The owner's later determination is the owner's own act (I4-07), never this operation's effect;
- **`REFER_HELD_RESULT` ends a custody hold only.** The result becomes input evidence for an AEV review, and nothing more: completion, integration, publication and evidence admission stay with their own owners (HEB-07.e's four);
- **`APPROVE_INTEGRATION` requires AEV's qualified readiness to exist already,** and names its version. It never creates it.

**I4-01b. Order and currentness.** Every target names the version it acts on: `HOLD_STALE`, `FINDING_STALE`, `RESULT_STALE`, `ASSURANCE_STALE`. Currentness is the owner's explicit resolution relationship, never arrival order or a timestamp (WIS-06.b, CNI-05.b, AEV-05.a).

**I4-01c. Every authority-increasing type rechecks the trust of every producing lineage it relies on (I4R1-1, I4C2-1, I4C2-2, I4C3-1, I4C4-1).** AOI-07.f: "every attempted protected effect shall recheck current protected state (including grants, revision, generation, basis …)". AEV-09.d: reuse does not "retrospectively confer missing … trustworthy provenance".

**A producing lineage's trust state** has two parts, both ADC's facts:
- **the producing generation's classification version:** A-30's I3-04 records `TRUST_REVOCATION` when a Lead generation's root grant is revoked, even after it ended (I3R1-2);
- **whether the producing grant lineage is revoked:** the grant under which the producing invocation was admitted, or any grant it derives from. A-30's `REVOKE_LINEAGE` of a worker's or custodian's grant revokes that lineage and leaves the generation's classification as it was (HEB-07.d).

**A producing lineage** is named by its generation and the grant under which the producing invocation was admitted. That of a held result is the one its admitted invocation ran under; HEB states it.

**The lineages a readiness rests on are read from its output:** the producing lineage of every item its determinations cite (I4C3-1, I4C4-1). WIS-06.a: determinations identify "the supporting observations". AEV-06.a: a disposition identifies "the applicable obligations and evidence supporting the disposition". Each lineage comes from the cited item's own attribution. What the determinations cite includes:
- **the material in the package's observed material closure** (CNI-06.b), attributed by the package's qualified lineage (WIS-06.c). That includes a predecessor generation's work the package inherits (AEV-09.b). Source changes run in separately confined, authorized contexts, never under the Lead's base execution identity (HEB-02.j). So a material's lineage is the grant of the context that produced it, and a write the Lead makes itself is in its own bounded write context (HEB-X01);
- **every record carried forward into its review** (AEV-06.c), attributed to its producer (AEV-05.a);
- **every held result accepted into its review** (I4-04), whose lineage HEB states;
- **evidence admitted in the review itself** (AEV-05.c), attributed to its producer (AEV-05.a). Examples are the Lead's submission or counterevidence once an evidence owner admits it, which an adjudicator weighs as a party's "attributable primary evidence" (ADC-07.i), and non-mandatory observations. An agent-controlled log alone never satisfies a mandatory obligation (AEV-05.g), but a cited item is in the basis whatever it is weighed for.

**The list gives instances; the rule is every cited item.** `verify_i4.py` also guards it the other way round (D6): every producer-attributed item that any fixture puts into AEV's or HEB's state must be in a source the basis reads.

**An item whose producer cannot be attributed is not trusted evidence** (AEV-09.d). That covers material the package's qualified lineage does not attribute (WIS-06.c), and a record or observation without attribution (AEV-05.a). An artifact from operator-directed external development has no AEW lineage: it is an untrusted external contribution (HEB-02.l).

**So any revocation of a lineage a readiness rests on makes it stale** (A-06 §5's trust-revocation row: "prevent downstream trust"), whether that lineage is a predecessor's, a carried-forward record's producer's, a producing worker's or custodian's, or the current Lead root under which a cited item was produced. Revoking a current worker leaves its generation `ROUTINE`, and still stales every readiness whose determinations cite an item it produced. A worker or custodian that produced nothing cited is not in the basis.

**This is proportionate** (A-06 §5: "Preserve existing qualified evidence"). A revocation deletes no evidence and reopens no work. It makes the readiness stale until AEV reassesses (AEV-10.j), and AEV may reissue it at once: it takes the revoked lineage's contribution as untrusted (AEV-09.d), or re-establishes it. A promotion is a new protected effect, so it rechecks the lineages it rests on (AOI-07.f).

**The rules:**
- **`REFER_HELD_RESULT` reads the result's producing lineage.** If its generation's newest classification is `TRUST_REVOCATION`, or its grant lineage is revoked, the result is `RESULT_FROM_REVOKED_LINEAGE`. It stays held, as preserved evidence. A-06 §5's trust-revocation row: "pending results not self-accepted", and "prevent downstream trust". HEB-07.j stops or contains the revoked lineage's descendant execution;
- **a readiness states its trust basis:** the trust state it relied on for every lineage it rests on, as defined above (I4-07);
- **`APPROVE_INTEGRATION` compares every entry of the readiness's trust basis with ADC's current facts.** Any change gives `ASSURANCE_STALE` until AEV reassesses (AEV-10.j) and issues a readiness that relies on the new state: a newer classification, or a lineage revoked since. HEB's effect-time recheck compares the same basis (I4-05);
- **an unreadable classification or lineage state is a hold** (`CLASSIFICATION_UNAVAILABLE`).

**Competence (I3-01's form).** `APPROVE_INTEGRATION` reads ADC's competence fact for the work's own project, never the request's `subject.project_ref` (`PROJECT_MISMATCH`), and carries `authority_decision_ref`. An external decision covers exactly this promotion and is spent with it. The delegated types act within the Lead's grant, which names the work.

**Consequences belong to their own owners, and are never this operation's effect:**
- **ADC:** selecting the adjudicator for a dispute (ADC-07.h).
- **AEV:** every determination, resolution, disposition and readiness (I4-07); reviewing an accepted held result (AEV-06.c).
- **HEB:** performing the promotion on the mediated path, rechecking at effect time (CNI-03.g, AOI-07.f, AOI-07.g).

## I4-02. `REQUEST_HOLD_RESOLUTION` (A12, the AEV variant; also C16), a delegated row, owner AEV

**Outcome:** the Lead submits a recovery request for one AEV-imposed hold. It picks one of the recovery options AEV issued for that hold, and names the package and its submission (D-01's `FR_HoldRecoveryProjection`). AEV records it. **The hold stays held.**

**Origin:** I1-01's class, `CURRENT_SUCCESSOR_GENERATION`, as I3-02: CS-07's authenticated session, both proof slots `null`, the subject naming the Lead's seat. AEV reads HEB's seat fact (`ACTOR_NOT_CURRENT_LEAD`, `GENERATION_FENCED`, a hold when unavailable). **No operator-origin type releases an owner hold.** A-25's `LIFT_OPERATOR_SUSPENSION` target fixes `imposing_owner` to `OPERATOR_VIA_ADC`, so it cannot name one.

**The target names:**
- the hold and its version;
- `option_ref`: one recovery option AEV issued for that hold version;
- the package the request offers: for `request_review`, the held package; for `request_remediation`, a corrected package of the same accepted revision;
- the submission's SHA-256: counterevidence, rationale or a remediation note;
- the work and its accepted revision;
- the Lead's grant.

**AEV admits it only if:**
- **the hold is AEV's** (`HOLD_UNKNOWN`). A hold another owner imposed is `HOLD_OWNER_MISMATCH`: that owner's variant answers it;
- **the hold is held, at that version** (`HOLD_NOT_HELD`, `HOLD_STALE`);
- **the option is one AEV issued for that hold version, to this recipient, and unexpired** (`OPTION_INVALID`, `OPTION_EXPIRED`). A `wait_for_external_event` option is not a submission (`OPTION_INVALID`). Every option has `executable_authority: false` (D-01), and this type never changes that;
- **the package fits the option** (`PACKAGE_MISMATCH`);
- **no submission is open on this hold version** (`SUBMISSION_OPEN`);
- **ADC's grant fact shows the Lead acting within its delegated authority,** as I3-02 reads it: the Lead's own grant of this generation, current, on the named work and revision, and the hold is on that work (`GRANT_UNKNOWN`, `GRANT_NOT_CURRENT`, `GRANT_NOT_COVERING`, `GRANT_STATE_UNAVAILABLE`);
- **the submission is held under its digest** (`CONTENT_UNAVAILABLE`, a hold).

**What it records:** the submission, attributed to the generation: the hold and its version, the option, the package and the digest.

**What it never does:**
- **it never clears, lowers or re-scopes the hold.** The hold clears only by AEV's own determination with an explicit resolution link to it (I4-07);
- **it never makes the submission evidence.** The digest's content is a claim until an evidence owner admits it (I4-08, AEV-05.c);
- **it never binds AEV's sufficiency conclusion** (AEV-06.e).

**When AEV moves the hold's version** (new evidence, a new option set), AEV closes any submission open on the old version in the same step. The submission stays a record; the Lead may submit against the new version (I4-09, cell X21).

## I4-03. `REQUEST_INDEPENDENT_REASSESSMENT` (W06), a delegated row, owner AEV

**Outcome:** the Lead disputes a finding that AEV does not class as discretionary, with its counterevidence, and AEV opens the independent adjudication path (ADC-07.d, ADC-07.e, ADC-07.g, AEV-10.f).

**Origin:** as I4-02.

**The target names:** the finding and its version; the assessed package; the counterevidence's SHA-256; the work and its accepted revision; the Lead's grant. **There is no adjudicator field** (ADC-07.h).

**AEV admits it only if:**
- **the finding is AEV's, at that version, about that package** (`FINDING_UNKNOWN`, `FINDING_STALE`, `PACKAGE_MISMATCH`);
- **AEV's current class of the finding is not discretionary.** A discretionary finding is `DISCRETIONARY_FINDING`: the Lead decides it by W07 (I3-02, ADC-07.a). **A finding whose class AEV cannot yet state is disputable** (I4R1-6): a dispute record releases nothing, and ADC-07.g sends "an unresolved disagreement about applicability" to the independent path. Its disposition waits for the class and the adjudication rows (I4-06);
- **no dispute is open on this finding version** (`REASSESSMENT_OPEN`);
- **the grant reads as I4-02's;**
- **the counterevidence is held under its digest** (`CONTENT_UNAVAILABLE`, a hold).

**What it records:** the dispute: the finding and its version, the counterevidence digest, the requesting generation.

**What follows, each by its own owner:**
- **ADC selects the adjudicator** by the preauthorized rule (ADC-07.h). It excludes the finding's reviewer, the requester, and every holder in the work's Lead grant lineages: the Lead, its workers and their custodians, and an earlier generation's Lead on the work, as I3-06's assessor rule does (ADC-09.j). A holder of an independently authorized grant is not excluded for that alone;
- **AEV delivers the original finding, the governing criterion and both parties' primary evidence,** never a Lead-authored summary (ADC-07.i);
- **AEV notifies the operator** when the adjudication starts and when it ends, saying whether any operator decision is needed (AEV-10.g).

**What it never does:**
- **the finding stays in force.** A dispute is not a PASS (ADC-07.c), and adjudication "shall not manufacture evidence, add criteria … or establish PASS by choosing a winner" (AEV-10.h);
- **attempt counts settle nothing** (AEV-10.f): a second dispute of the same version is `REASSESSMENT_OPEN`;
- **it blocks no unrelated work** (ADC-07.n).

**When AEV reassesses the finding** on a changed package (AEV-10.c), it moves the finding's version and closes the open dispute in the same step. The dispute and its evidence stay a record; the Lead may dispute the new version (cell X22).

## I4-04. `REFER_HELD_RESULT` (C15), a delegated row, owner HEB

**Outcome:** the current Lead accepts one result that HEB holds under HEB-07.e (it arrived after its generation ended) into the current generation's review. HEB records the acceptance and ends its custody hold. The result becomes input evidence for a new AEV review, and nothing more.

**Origin:** as I4-02. HEB reads its own seat fact.

**The target names:** the held result and its version; the work and its current accepted revision; the package the current review assesses; the Lead's grant.

**HEB admits it only if:**
- **the result is one HEB holds, at that version** (`RESULT_UNKNOWN`, `RESULT_NOT_HELD`, `RESULT_STALE`). A result produced in the current generation is never held under HEB-07.e, so it is `RESULT_NOT_HELD`;
- **the result is of the named work** (`PACKAGE_MISMATCH`), and **WIS's current accepted revision is the one named** (`WORK_REVISION_STALE`, a hold when unavailable). The package is one of that revision's (`PACKAGE_MISMATCH`);
- **the result's producing lineage is not revoked:** its generation's newest classification is not `TRUST_REVOCATION`, and its grant lineage is not revoked (`RESULT_FROM_REVOKED_LINEAGE`; `CLASSIFICATION_UNAVAILABLE`, a hold). I4-01c;
- **ADC's grant fact shows the Lead acting within its delegated authority,** as I4-02 reads it, on the result's work.

**What it records:** the acceptance, attributed to the current generation: the result and its version, the package, the revision. The result is no longer held; a second acceptance is `RESULT_NOT_HELD`.

**What follows, by its own owner:** AEV reviews the result in the current generation, on the named package, and decides its applicability explicitly (AEV-06.c). If that generation ends before the review concludes, the review's own result is held by HEB in its turn, and this type applies again.

**What it never does:**
- **no PASS, admission, integration or publication.** HEB-07.e's four stay with their owners: AEV's determination, W09, A09. "No automatic PASS or old publish-intent carryover" (C15's text): "earlier publish-if-clean authorization never transfers" (A-06 §5);
- **the result's history is unchanged** (AEV-05.b, AEV-06.g);
- **a revoked lineage's result is never accepted this way.** It stays held, as preserved evidence. An operator path for it is backlog I4-B6.

## I4-05. `APPROVE_INTEGRATION` (W09), protected, owner CNI

**Outcome:** with the consent of the authority competent for the work's project, CNI promotes one exact package to accepted input that consumers resolve (CNI-05.a, CNI-03.g).

**The target names:**
- the work and its accepted revision;
- the package, its digest and its source closure reference, as D-01's packages read shows them (`PackageData.digest`, `source_closure_ref`) (I4R1-11);
- `readiness_ref`: AEV's assurance readiness for that package that the consent showed;
- `authority_decision_ref`: an external authority's decision, or `null` for the operator (I3-01).

**CNI admits it only if:**
- **WIS's current accepted revision is the one named,** and the package is one of that revision's, of that work (`WORK_REVISION_STALE`, a hold when unavailable; `PACKAGE_MISMATCH`, I4R1-10);
- **`readiness_ref` is AEV's current readiness for the package** (`ASSURANCE_STALE`). An older PASS shown before a newer hold never restores readiness (CNI-05.b, AEV-X35). AEV's fact unavailable is a hold (`ASSURANCE_UNAVAILABLE`);
- **the readiness is `qualified_clear` for this revision,** with both closures qualified complete, as D-01's `AssuranceData` defines it. Otherwise `ASSURANCE_NOT_CLEAR`. "Unexecuted, missing, unavailable and unqualified mandatory obligations are unsatisfied even when no HOLD has arrived" (CNI-05.a);
- **ADC's current trust state of every lineage in the readiness's trust basis is the one the readiness relied on:** every lineage the readiness rests on (`ASSURANCE_STALE`; `CLASSIFICATION_UNAVAILABLE`, a hold). I4-01c;
- **the digest and closure are CNI's own observation of that package** (`PACKAGE_CLOSURE_INVALID`, CNI-06.b);
- **the package is not already accepted input** (`ALREADY_ACCEPTED`);
- **competence** reads as I4-01.

**What it records:** the promotion, bound to the package, its digest and closure, the revision, the readiness it relied on and the consent.

**What follows, by its own owner:** HEB performs the promotion on the mediated path, rechecking current state at effect time (AOI-07.f): the readiness, the revision and every entry of the readiness's trust basis. If any moved after the record, HEB does not promote (CNI-X39; cells Y2 to Y4, Y8 and Y14). Where the mediated path or the accepted-input resolver is not qualified, AEW represents the promotion as unsupported, never as done (AOI-07.g).

**What it never does:**
- **it records no assurance.** CNI consumes AEV's readiness and never authors it (CNI-05.a);
- **it grants no deployment permission, records no operator acceptance, and makes no production publication** (CNI-06.d, AEV-10.i). Publication outside AEW is A09's exact effect and still needs one;
- **it never carries to another package or revision.**

## I4-06. Activation needs the adopted parameters (A-05 §5 and A-07 §6)

**I3-09's rule, unchanged:** a type is held only for the effect that an unadopted A-05 §5 row is "Required before", with `POLICY_UNAVAILABLE` (`SOURCE_UNAVAILABLE`), allocating nothing and consuming no consent. A-07 §6 adds that assurance-class rules must define "specific floors, actor selection and policy parameters before the corresponding mode is admitted".

| Type or owner act | When it is held | The row, and what it is "Required before" |
|---|---|---|
| `REQUEST_HOLD_RESOLUTION`, `REQUEST_INDEPENDENT_REASSESSMENT` | **never as a type.** A submission or a dispute record releases nothing | — |
| `REFER_HELD_RESULT` | **never as a type.** It takes a result into review; carrying its proof to the current package is AEV's review decision, held below | — |
| `APPROVE_INTEGRATION` | **always** | "All mutable-agent launch permissions …, build consumption quarantine and source effect coverage": "trusting shared outputs". And "Minimum mediated effect channels, effect acceptance …": "Protected execution" |
| **AEV's resolution of its own hold** (I4-07), by an eligible producer with an explicit link (I4R1-7) | **where the hold's obligation needs independent assessment,** until that row is adopted. **Otherwise not held** | "Reviewer independence, mandatory/discretionary finding classification and technical adjudication": "Accepting contested mandatory review or downgrades removing protection". A-07 §6: actor selection "before the corresponding mode is admitted" (AEV-02.a) |
| **any automated release or recovery of a hold** not made by an eligible producer's linked determination | until that row is adopted | "Hold/provisional hold qualification, fallback effect scope, protected deadlines, affected-work mapping and resumption": "Automated consequential stop, release and recovery" |
| the dispute's disposition (I4-07) | until both rows are adopted | "Independent finding-adjudicator selection and primary record delivery": "Disposition of unresolved mandatory findings". "Reviewer independence …": "Accepting contested mandatory review" |
| AEV's review of an accepted held result, where it carries the result's proof to the current package | until that row is adopted | "Record and evidence applicability across changed assignments/revisions": "Carry-forward of previously accepted proof" |

**The consequence for A12** (I4R1-7): an AEV hold whose obligation needs no independent assessment can be resolved in the first release by an eligible producer's linked determination, so the submissions A12 records can be answered. One that needs independence waits for the reviewer-independence row, and AEV states no resolution until then: AEV's fail-closed state, not a hold on A12.

**Holds are per row, not per type,** as I3-09.

**`APPROVE_INTEGRATION` binds content the operator must read, so I5-08a applies.** It is held with `CONTENT_READ_UNAVAILABLE` until a selected read shows the package, its digest and closure reference, and its assurance readiness. D-01 0.3.4 has both reads (`/v1/read/work/{work_kind}/{work_id}/packages`: `digest`, `source_closure_ref`; `/v1/read/assurance/{subject_kind}/{subject_id}`); a deployment that does not serve them holds the type. The readiness's trust basis is not yet on D-01's `AssuranceData` (I4-10).

## I4-07. The owners' own determinations (not commands)

**What every I-4 request waits on is an owner's act, under its owner's adopted rules:**
- **a hold's resolution** is an AEV determination with an explicit resolution link to that hold version, by an eligible AEV producer (WIS-06.b, CNI-05.e, AEV-02.a). Where the hold's obligation needs independent assessment, the producer is independent of the requesting lineage (AEV-06.e). A later unlinked PASS never clears a hold;
- **a dispute's disposition** is the selected adjudicator's, recorded by AEV: sustained, overturned, or evidence insufficient (AEV-10.h);
- **a review's result** is a new AEV determination, linked to the original (AEV-05.b, AEV-06.g);
- **a readiness** names the package, its revision, and its trust basis: for every lineage it rests on (I4-01c), the classification version and lineage state it relied on. AEV takes those lineages from what its determinations cite, each from the item's own attribution (I4-01c). Where it relies on an item whose producing lineage is revoked, AEV takes that contribution as untrusted, and the readiness does not count it as trusted evidence (AEV-09.d).

**Each waits for its row (I4-06),** and none is established by this pass.

## I4-08. Evidence admission is the evidence owner's act (W08)

**W08 is not a command.** An evidence owner, AEV, Knowledge or WIS, each for what it owns, admits an observation or finding under its own adopted rules: provenance, subject, check identity and conditions (AEV-05.a, AEV-05.i); a protected or independently qualified observer for a mandatory result (AEV-05.g); a submitted artifact stays a claim until admitted (AEV-05.c). Knowledge admission is K-01's, in I-7.

**What this pass fixes:**
- **no I-4 type records an admission, a PASS, a readiness, or a finding's class or disposition.** `verify_i4.py` checks the recorded fields of every type against that list (X20);
- **a digest in a request target is a claim** (I4-02, I4-03).

## I4-09. Pending artifacts and crossings, derived (I4R1-4)

**The method, not a list of instances.** Each pending artifact names the subjects it depends on; each crossing names the subjects it moves. Every artifact × crossing that shares a subject is a cell, in both orders: the crossing before the request, and the request recorded before the crossing. Every cell has a fixture in `verify_i4.py`, or a stated fate from a closed set:
- **refused:** the request after the crossing is refused, under the reason named;
- **record:** the artifact stays a record, and nothing it asked for happens by it;
- **closed by its owner:** the owner closes it in the same step as the crossing; it stays a record;
- **not effective:** the effect it recorded is never performed, because its owner rechecks at effect time;
- **unaffected:** the crossing moves a subject the artifact names only through another owner's fact that still holds; the request is admitted as before, and a recorded one stays a record. `verify_i4.py` admits this fate only where it is declared: on an artifact that is not authority-increasing, naming the other owner's fact and a fixture that shows the request still admitted (D5, U1; I4C3-3).

`verify_i4.py` derives the cells from the two tables below and fails if any cell has neither a fixture nor a fate.

**The pending artifacts and what each depends on:**

| Artifact | Depends on |
|---|---|
| a hold submission (I4-02) | the hold's version; the revision; the Lead's grant; the generation |
| a dispute (I4-03) | the finding's version; the revision; the Lead's grant; the generation |
| an acceptance of a held result (I4-04) | the result's version; the revision; the Lead's grant; the generation; the producing lineage's trust |
| a promotion (I4-05) | the readiness; the revision; the trust of every producing lineage in the readiness's basis |

**The crossings and what each moves:**

| Crossing | Moves |
|---|---|
| `REVOKE_LINEAGE` of the current Lead (I3-04) | the grant; the generation |
| `REVOKE_LINEAGE` of any producing lineage: a generation's root, ended (I3R1-2) or current, or a worker's or custodian's grant (HEB-07.d) | the producing lineage's trust |
| a routine generation end (I-1) | the grant; the generation |
| `SUSPEND_GRANT` of the Lead's grant (A-25) | the grant |
| a new accepted revision (I5-03) | the revision |
| AEV reassesses on a changed package (AEV-10.c) | the finding's version |
| a newer AEV hold, or a new hold version | the hold's version; the readiness |

**The cells.** *Before* means the crossing happens first; *after*, that the artifact is recorded first.

| Artifact | Crossing | Before | After |
|---|---|---|---|
| submission, dispute, acceptance | revoke the current Lead | **X1†** `GRANT_NOT_CURRENT` | **X4†** record: the hold stays held, the finding in force; for an acceptance, AEV takes the current classification into its review (AEV-09.d) |
| submission, dispute, acceptance | routine generation end | **X2†** `ACTOR_NOT_CURRENT_LEAD` | record: AEV's and HEB's determinations never depended on who asked (I4-07) |
| submission, dispute, acceptance | suspend the Lead's grant | **X3†** `GRANT_NOT_CURRENT` | record: a suspension is reversible, and a request grants nothing |
| submission, dispute | new accepted revision | **U1†** unaffected: the revision is read only through the Lead's grant, which ADC reassesses (ADC-02.d) | record: neither releases anything |
| acceptance | revoke a producing lineage | **K1†** (a generation's root), **K3†** (a worker's grant), **K4†** (the generation's classification alone): `RESULT_FROM_REVOKED_LINEAGE` | record: any readiness that relies on the result carries its lineage in its trust basis, so a later promotion rechecks it (I4-01c) |
| acceptance | new accepted revision | **K2†** `WORK_REVISION_STALE` | record: AEV decides the result's applicability to the current package (AEV-06.c) |
| submission | newer hold version | **X10†** `HOLD_STALE` | **X21†** closed by its owner (I4-02) |
| dispute | AEV reassesses the finding | **B4†** `FINDING_STALE` | **X22†** closed by its owner (I4-03) |
| promotion | revoke a producing lineage | **Y1†** (the current Lead root), **Y6†** (an accepted held result's generation), **Y7†** (its worker grant), **Y10†** (its generation's classification alone), **Y11†** (a predecessor's inherited work), **Y12†** (a carried-forward record's producer), **Y13†** (the current worker that produced the package), **Y15†** (the second of two accepted results), **Y17†** (the current Lead root, under which an admitted item was produced, with wholly inherited material), **Y18†** (the producer of an admitted observation alone): `ASSURANCE_STALE` | **Y2†** (the current Lead root), **Y8†** (an accepted held result's), **Y14†** (inherited work, a carried-forward record, the current worker), **Y19†** (an admitted item's producer): not effective, HEB rechecks the trust basis and does not promote |
| promotion | new accepted revision | **X18†** `WORK_REVISION_STALE` | **Y4†** not effective: HEB rechecks the revision |
| promotion | newer AEV hold | **X16†** `ASSURANCE_STALE` | **Y3†** not effective: HEB rechecks the readiness (CNI-X39) |

**A promotion depends on no Lead grant or seat as the requester's:** it is operator-consented and CNI's, so a generation end or a suspension moves nothing it depends on. A revocation moves it only as a producing lineage's (I4-01c). That includes the current Lead root's, because every current worker's grant derives from it (Y1, Y2).

**More cells, outside the derivation:**
- **Y5†** AEV reassesses after a producing lineage's revocation and issues a readiness whose trust basis relies on the new state: a promotion naming that readiness is admitted. **Y9†** is the same for an accepted held result's lineage.
- **Y16†** a held result accepted, a record carried forward, and an item admitted into another package's review are not in this readiness's basis: their lineage's revocation leaves a promotion of this package admitted.
- **Y20†** with wholly inherited material and nothing from the current generation cited, revoking a current worker leaves the promotion admitted: the basis is what the readiness cites, and no more.
- **X9†** a submission on an HEB-imposed hold: `HOLD_OWNER_MISMATCH`. `LIFT_OPERATOR_SUSPENSION` naming an AEV hold is schema-invalid.
- **X10†** a second submission on one hold version: `SUBMISSION_OPEN`.
- **X11†** a dispute of a discretionary finding: `DISCRETIONARY_FINDING`; W07 of a mandatory one is `MANDATORY_FINDING` (I3-02). A finding of unknown class is disputable and W07 holds it, so the two never overlap.
- **X12†** a second dispute of one finding version: `REASSESSMENT_OPEN`.
- **X15†** a promotion with readiness `blocked`, or `qualified_clear` with an incomplete closure: `ASSURANCE_NOT_CLEAR`.
- **X17†** a second promotion of one package: `ALREADY_ACCEPTED`.
- **X19†** a promotion on an external authority's boundary, on the operator's consent alone: `AUTHORITY_NOT_COMPETENT`; with that authority's decision: admitted, and the decision is spent.
- **X20†** no I-4 type records a PASS, an admission, a resolution, a readiness or a disposition (I4-01a, I4-08).

## I4-10. What the operator sees, and what is readable

- **The consent is A-26's, unchanged.** `APPROVE_INTEGRATION` has 7 leaves, and renders within the 30 lines G3 allows (`verify_i4.py` derives this).
- **`IntentResult`:** every type reports `ADMITTED` and `EFFECT_CONFIRMED` at admission, owner `AEV`, `HEB` or `CNI`. A confirmed submission, dispute or acceptance never means the hold cleared, the finding fell or the result passed. A confirmed promotion means CNI recorded it; HEB's promotion is its own effect.
- **What a D-01 change must add:**
  - on `AssuranceData`: the readiness's trust basis, each lineage it rests on with the classification version and lineage state relied on (I4-01c);
  - on every item a determination cites: its producing lineage, from its own attribution (WIS-06.a, AEV-05.a). On `PackageData`, that is each material's producing lineage in the observed closure (WIS-06.c, CNI-06.b);
  - a held-result read: the result, its producing lineage, why HEB holds it, and its acceptance;
  - an AEV finding read with disputes and their adjudication state (I3-10 already asks for the finding read);
  - the submissions on a hold.

## I4-11. Ordering, atomicity and refusals

- **One admission path, as I3-12:** origin, then owner state, then the activation hold (I4-06), then at most one owner effect per member (CS-05). Every activation hold is decided from the type and the target alone.
- **A submission, dispute or acceptance is compare-and-set** on its subject's version. At most one submission or dispute is open per subject version; an acceptance ends the hold, so it happens once.
- **A promotion happens once per package** (`ALREADY_ACCEPTED`).
- **The admitting owner's own state** unavailable is `UNKNOWN_OWNER_STATE`. Another owner's fact unavailable is a hold under its own reason.
- **Each owner reason maps to an adopted reason code** in `wire/refusal-reasons-0.6.json`. The map is complete and fail-closed.

## I4-12. The wire

`tools/build_i4_wire.py` generates `wire/` from A-30's frozen `STG-08 adopted/o01-0.5-i3/wire/`, pinned by its `SHA256SUMS` (`86ea0ef2…88a5`):
- **`o01-command-0.6-candidate`:** A-30's schema, byte-equal in every inherited definition, plus four Intent branches and four Target definitions: 31 actions.
  - The three delegated branches require the seat, and both proof slots `null` (I1-01).
  - The protected branch requires a `null` seat.
- **`openapi-o01-0.6.yaml`:** the same definitions, checked equal by the script.
- **`action-registry-0.6.json`:** A-30's 27 rows unchanged, plus four. `REQUEST_HOLD_RESOLUTION` lists `A12` and `C16`.
- **`refusal-reasons-0.6.json`:** A-30's map, plus the four types' owner reasons.
- **`PREDECESSOR-PINS.json` and `SHA256SUMS`.** `--check` regenerates and compares.

## I4-13. Backlog

- **I4-B1, the integration breaker (A10).** An adopted owner fact would need what trips it, who owns it, and what clearing "the exact cause" means. The candidates are a CNI amendment or R-01 (I-7).
- **I4-B2, release, operator acceptance and deployment permission (W09's remaining part).** CNI-06.d names them apart from integration. No adopted owner fact defines them. A release type would bind the milestone scope's identity and version (AOI-07.a).
- **I4-B3, HEB's and R-01's hold variants (A12).** I-2 and I-7.
- **I4-B4, A-30's A09 and a revoked producing lineage.** The I4R1-1 shape may also exist for A09: a current grant authorizing content that a revoked lineage produced. A-30 is not reopened here. A later A09 amendment should read HEB's custody of, and the producing lineage's trust in, content it publishes; until then an external publication of a held result is not ordered after C15 or AEV (I4-00, I4C2-3).
- **I4-B5, an operator request for reassessment or re-evaluation** (the `O` of W06 and of C16).
- **I4-B6, an operator path for a revoked lineage's held result** (I4-04): for example, the operator taking it in as an untrusted contribution (AEV-09.d).

## I4-14. Questions for the targeted check

**Revision 2.3** answers the targeted check of 2.2 (`reviews/2026-10-22-I4-check-r22.md`, source `I4C4`); see `CHANGES-r23.md`. For the targeted check:
- **Q1 (I4-01c):** does the output-side basis (every item its determinations cite) close I4C4-1, in both orders: wholly inherited material, with an admitted item produced under the current Lead root or under a worker that produced no material?
- **Q2 (I4-01c, D6):** is the rule now stated as every cited item rather than a list, and does D6 find a new kind of attributed evidence that the basis does not read? Is it still proportionate (Y16, Y20)?
- **Q3:** are I4C4-2's wording fixes right, and is any adopted text stretched?

## I4-15. Not claimed

- **This selects interface architecture.** It qualifies no host, builds nothing, and activates no action. The protected row stays held wherever G3 is not established, and I4-06 holds what the parameters are required before, until they are adopted.
- **Candidate mechanisms are not claimed:** the submission intake, AEV's determination interface, HEB's held-result custody, and HEB's promotion path.
- **Out of scope:** D-01 changes; A-30's 27 actions, which are unchanged; AEV's own determination rules, ADC's adjudicator-selection rule, and the A-05 §5 parameters themselves; the backlog above.
