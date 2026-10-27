<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-34
source: 30-stages/STG-10-I2-heb-child-execution-control/adopted/o01-0.7-i2/I2-PROFILE.md
source-sha256: 7923362bb9d2cc839d23fd12af7d6a36be9650d013680ec8a5ab8098d87e2ffe
edits-sha256: none
-->

# I-2: the HEB child execution control, selection profile (PROPOSED contract pass, revision 3, 2026-10-23)

**Revision 2** answers round 1's thirteen findings (`reviews/2026-10-23-I2-review-round-1.md`; `CHANGES-r2.md` says what changed, finding by finding).
**Revision 3** answers the targeted check of revision 2 (`reviews/2026-10-23-I2-check-revision-2.md`: I2C2-1 to I2C2-4, and the noted refusal mapping, I2C2-N1). `CHANGES-r3.md` says what changed.

**Wire:** O-01 `o01-command-0.7-candidate`, in `wire/`. It is A-31's 0.6 wire plus six action types, generated from A-31's frozen bytes by `tools/build_i2_wire.py`.
**Stage:** `STAGE.md`. **Start:** `00-governance/decisions/2026-10-23-operator-start-I-2.md`. The working notes behind the fit are `work/FIT-CHECK-NOTES.md`.
**How to read it:** as I-4's profile. Each rule states an outcome: what must hold, who owns it, what is refused, and the adopted rule it must not contradict. Text marked **Candidate** is a starting point for the build, which may meet the outcome another way.
**Rule names:**
- `HEB-07.c` and the like are A-06's guarantees; `ADC-02.f` A-05's; `AOI-07.c` A-10's; `R01-31` A-15's; `WIS-06.b` A-08's; `AEV-09.d` A-07's.
- `I1-01`, `I3-04` and `I4-04` are the adopted I-1 (A-28), I-3 (A-30) and I-4 (A-31) profiles.
- "A-06 §3.3" is HEB's lifecycle table: drain, Stop now, Release to manual, routine handover, trust revocation and host loss.

## I2-00. The fit: which rows need a new O-01 type

**The departures from the adopted classification (A-32) come first,** each with the adopted text it rests on. None moves a row from operator origin to delegated, so none loosens an authority. The operator confirms or refuses each at adoption.

| Row | The classification proposed | This profile | The adopted text | What changes for the operator |
|---|---|---|---|---|
| C07, C20 | origin `DELEGATED_GRANT` | the wire class `CURRENT_SUCCESSOR_GENERATION` | I1-01: the classification's `DELEGATED_GRANT` "means 'no operator origin needed'; which wire class carries that is this pass's to choose". The Lead acts on its own work with its own grant, which HEB and ADC read as owner state | Nothing. A label only, as for every delegated row since I-1 |
| C20 | owner "HEB/WIS competent stage owner"; the symbol says "stage" | **owner HEB.** "Stage" is read as **an interrupted child execution:** an assignment execution context whose process ended before completion, with its continuation still undecided | No adopted text defines a stage that can be abandoned (`work/FIT-CHECK-NOTES.md`, fact 6). HEB-07.a separates "an assignment execution context" from the work. HEB-08.h requires "deliberate authorized continuation … before restarting previously interrupted mutable execution", and C17's `CONTINUE_ELIGIBLE_WORK` is that continuation. The catalogue itself sets abandonment apart from "immutable Ticket cancellation/revision" (W03, WIS) | **This is the designer's reading of the catalogue's word.** The operator confirms it, or names the unit they meant |
| C03, C04 with `CLOSE_ATTACHMENT` (I2R1-4) | A-24 selected close "close-only": "explicit `STOP(X)+CLOSE` is **not** part of this selection" | **a protected set may hold a close with a stop or a release of a child of that attachment** (I2-09). The close's target and wire definition are unchanged, and so is its drain of every child with no member of its own | HEB-07.i: the drain default is for "an eligible admitted child with no operator-selected disposition". HEB-07.c: Stop now and Release to manual are the dispositions an operator may choose at close. A-24's decision: "Any substantive future machine-wire change requires a newly pinned version and separate selection". 0.7 is that version, and this pass is that selection | **The operator can now close and stop or release named children in one consent.** A child whose member is refused or held drains, as before. The operator confirms this extension of A-24's selection, or refuses it |
| C12, C13 | their own types | **no type: no adopted owner fact** (backlog I2-B1) | No adopted text defines a quiesced execution (fact 5). The nearest texts do not reach an operator request. R01-25's yield is "a blocked invocation" relinquishing capacity "under a competent HEB execution/custody transition". R01-19's "safe yield" is one option in an intervention record for "nonemergency degradation". What the operator can already do is adopted: A-25's `SUSPEND_GRANT` (A02) denies new protected effects under a grant, and `LIFT_OPERATOR_SUSPENSION` (A03) lifts it. A02 stops no process, so it is not a quiesce. C13's own text says it is "separate from … A03" | A pause that keeps the process alive waits for an owner fact. Meanwhile the operator has A02 (no new protected effects), C03 (stop now) and C06 (cancel one operation) |

**The fit for all eight rows:**

| Row | Catalogue symbol | Kind letters | Fit | Reason |
|---|---|---|---|---|
| C03 | `STOP_CHILD_NOW` | O | **New type `STOP_CHILD_NOW`, protected, owner HEB, `REDUCING`** (I2-02) | A-06 §3.3's "Operator chooses **Stop now**" row: the child's execution stops, and its files and logs are preserved but not admitted. **It is not A-30's `REVOKE_LINEAGE` (A01):** that revokes "finally" and transitively (I3-04), and a revoked lineage's results are not trusted (I4-01c). §3.3 keeps Stop now apart from its trust-revocation row, which alone says "prevent downstream trust". **It is not A02:** a suspension denies new protected effects, and HEB stops no process for it. **It is not `CLOSE_ATTACHMENT`:** A-24 selected close "close-only", and "explicit `STOP(X)+CLOSE` is not part of this selection" (`work/FIT-CHECK-NOTES.md`, fact 1). I2-09 now extends that selection (the third departure), and the stop stays a type of its own. HEB-07.c requires that stop-now be supported |
| C04 | `RELEASE_CHILD_TO_MANUAL` | O | **New type `RELEASE_CHILD_TO_MANUAL`, protected, owner HEB, `REDUCING`** (I2-03) | A-06 §3.3's "Operator chooses **Release to manual**" row, and HEB-07.c. A-06 §1.1: release-to-manual is a lifecycle disposition, "not the same event" as operator-directed external development |
| C06 | `OPERATOR_CANCEL_CHILD` | O | **New type `CANCEL_CHILD_OPERATION`, protected, owner HEB, `REDUCING`** (I2-04) | **Its subject is one admitted operation, not the child.** HEB-07.a separates "an assignment execution context" from "each admitted background operation". HEB-06.e cancels "a pending operation". §3.3 stops "the affected child execution grant". So C03 and C06 act on different subjects. **It is not C19's `DELEGATED_CANCEL`:** that type's `cancel_scope` is `OWN_DELEGATED_INVOCATION` and its origin is a delegated grant. A registry row has one origin (CS-02) |
| C07 | `REQUEST_BACKGROUND_RERUN` | D | **New type `REQUEST_BACKGROUND_RERUN`, delegated, owner HEB, `PRESERVING_OR_INCREASING`** (I2-05) | HEB-06.e: "authorized cancellation and rerun". HEB-08.d: no "automatic replay of consequential non-idempotent effects when execution completion is uncertain". **It is not C17's `CONTINUE_ELIGIBLE_WORK`:** that target names work, a revision, a grant and an eligibility basis, and no prior operation. Adding one would change an inherited definition (I2-00a) |
| C12 | `REQUEST_INFLIGHT_QUIESCENCE` | O/Q | **No type** (I2-B1) | As in the departures table |
| C13 | `RESUME_QUIESCED_EXECUTION` | O/D | **No type** (I2-B1) | Nothing to resume without C12's state |
| C14 | `DISCARD_HELD_ACTIVE_USE` | O/Q | **New type `DISCARD_HELD_RESULT`, protected, owner HEB, `REDUCING`** (I2-06) | HEB-07.e holds a result "for current-authority acceptance". A-31's `REFER_HELD_RESULT` (C15) accepts one; this forecloses acceptance. It is a type of its own, not a branch of C15's, so no inherited definition changes. **The origin stays operator, as proposed** (I2-06 says why) |
| C20 | `ABANDON_SELECTED_STAGE` | D/Q | **New type `ABANDON_INTERRUPTED_EXECUTION`, delegated, owner HEB, `REDUCING`** (I2-07) | As in the departures table |

**Six rows get a type, and two get none.** Four types are protected (C03, C04, C06, C14), and two are delegated (C07, C20). HEB is the sole admitting owner of all six (AOI-07.b).

**What this pass also settles from A-31's backlog:**
- **I4-B3, HEB's half** (HEB's variant of A12's hold answer). The hold HEB imposes in adopted text is the held result (HEB-07.e). C15 accepts it and C14 discards it, so no request type is needed for it. HEB's other hold is an uncertain consequential effect awaiting reconciliation (HEB-08.d; A-06 §3.5: "Hold unknown consequential effect"). Its release is HEB's own reconciliation, which C07 waits for (I2-05). A Lead request to reconcile is not one of I-2's rows, so it stays backlog, as **I2-B2**. R-01's half stays with I-7.
- **I4-B6, narrowed:** the operator can now discard a revoked lineage's held result (C14). Taking it in as an untrusted contribution stays I4-B6.

**I2-00a. No inherited definition changes.** The closed owner enums already list `HEB`. A-31's 31 actions, branches, targets, registry rows and refusal entries are carried byte-equal. What the third departure extends is which sets may hold a close (I2-09), not the close's definition.

**The protection direction, by I5-00's rule, derived by the owner from the operation (AOI-07.c), never from its label:**
- **The five `REDUCING` types each end something and enable nothing.**
  - `STOP_CHILD_NOW` ends a child's custody, and so its mediated effects.
  - `RELEASE_CHILD_TO_MANUAL` ends AEW's child execution authority. The artifacts it hands over leave AEW governance unaccepted, so nothing AEW contains is released into AEW's trust.
  - `CANCEL_CHILD_OPERATION` ends one operation.
  - `DISCARD_HELD_RESULT` ends a hold **by foreclosing the acceptance it held back,** never by releasing what it held. AOI-07.c: "releasing, cancelling or overriding an effective HOLD … is authority-increasing, irrespective of labels". Discarding releases nothing.
  - `ABANDON_INTERRUPTED_EXECUTION` ends a continuation.
- **`REQUEST_BACKGROUND_RERUN` starts execution,** so it is `PRESERVING_OR_INCREASING`.

## I2-01. Who owns what

**The subjects, in adopted terms:**
- **A child:** an admitted execution under HEB's custody, apart from the Lead's own seat. That is a worker's assignment execution context, or a custodian's, each running under its own grant (HEB-07.a, HEB-07.d, HEB-07.i). HEB records its custody: the grant it runs under, that grant's generation, its work, its state and its version. The states are `RUNNING`, `DRAINING` (§3.3's drain), `INTERRUPTED`, `STOPPED`, `RELEASED`, `ABANDONED` and `ENDED`.
- **An operation:** one admitted background operation (HEB-06.a, HEB-07.a), with its own state and version, in a custody HEB holds: a child's, or one HEB admits for a rerun (I2-05). **A rerun's custody is not a child** (I2C2-2): it runs under the Lead's grant alone, and ends at the Lead's detachment or at the end of its seat generation (I2-05). HEB records:
  - its admitted definition, and the lineage that admitted it (its generation and grant);
  - its attribution: every lineage it rests on (I2-05);
  - whether its completion and effects are known;
  - whether its definition is qualified idempotent or non-effecting, and by what (I2-05);
  - its original operation intent and its attempt number (R01-31).
- **An interrupted child:** one whose process ended before completion (host loss, harness failure, a stop condition: HEB-08.b), whose continuation is undecided. C17 continues its work; C20 abandons it. **A child the operator stopped is not one** (I2R1-5): its continuation ended with the stop (I2-02).

| Type | Records the fact (HEB, the sole admitting owner) | Whose decision the origin carries | Read only, as an input |
|---|---|---|---|
| `STOP_CHILD_NOW` | the child's stop: custody ended, continuation ended, processes stopped (observed apart) | the operator's, by A-26's consent | WIS: the work's project |
| `RELEASE_CHILD_TO_MANUAL` | the child's release: custody ended, artifacts handed over outside AEW | the operator's | WIS: the work's project |
| `CANCEL_CHILD_OPERATION` | the cancellation request for one operation, then its observed outcome | the operator's | WIS: the work's project |
| `DISCARD_HELD_RESULT` | the end of HEB's hold on one result, by discard | the operator's | WIS: the work's project |
| `REQUEST_BACKGROUND_RERUN` | a new operation: one more attempt of the original operation intent's admitted definition, in a new custody under the Lead's current grant | the current Lead's | HEB's own seat fact and every attempt of the intent. ADC: the Lead's grant, and the trust state of every lineage that admitted an attempt of the intent. WIS: the current accepted revision. R-01: the intent's attempt ceilings, and its held/waiting decision at exhaustion |
| `ABANDON_INTERRUPTED_EXECUTION` | the interrupted child's end, by abandonment | the current Lead's | HEB's own seat fact. ADC: the Lead's grant |

**I2-01a. A disposition is not proof of its consequences** (AOI-07.e, HEB-07.h):
- **`EFFECT_CONFIRMED` means HEB recorded the disposition, and admits no further mediated request through that custody, or for that operation** (HEB-01.d). Any claim that running effects have stopped stays with A-05 §5's mediated-effects row, as I3-04 keeps it (I2R1-9).
- **That its processes have stopped is a separate observation,** reported as requested, confirmed or unknown. "A lost remote acknowledgement or host loss cannot become 'stopped' or 'completed'" (AOI-07.e).
- **No disposition claims that an external effect was reversed** (HEB-07.h). Residual effects stay reported for reconciliation.
- **Where A-05 §5's mediated-effects row is unadopted,** HEB makes no claim that every running effect stopped. That is I3-04's rule for revocation, applied to HEB (I2-08).

**I2-01b. Order and currentness.** Every target names the version it acts on: `CHILD_STALE`, `OPERATION_STALE`, `RESULT_STALE`. Currentness is the owner's own version, never arrival order or a timestamp (WIS-06.b).

**I2-01c. No I-2 type touches another owner's fact:**
- **ADC's grants are unchanged.** A stopped, released or abandoned child's grant is not revoked, suspended or ended by this. With its custody ended, no mediated request can bind to it (HEB-01.d: a request is bound to "its originating current actor, grant, assignment, effect, and admissible execution channel"). Revoking the lineage is A01 (trust revocation), and suspending it is A02.
- **WIS's work is unchanged.** Cancelling or replacing a Ticket is W03.
- **AEV's evidence is unchanged.** Nothing here records a PASS, an admission or a disposition. Files and logs preserved by a stop are "not automatically admitted" (§3.3).
- **Results produced before a stop keep their trust.** A stop is not a trust revocation (I2-00). Only A01 makes a lineage's results untrusted (I4-01c).

## I2-02. `STOP_CHILD_NOW` (C03), protected, owner HEB

**Outcome:** with the operator's consent, HEB stops one child now. Its custody and its continuation end, HEB admits no further mediated request through it, and its processes are stopped.

**The target names:** the child and its custody version; the child's work; a reason reference (the operator's recorded reason, R01-19).

**HEB admits it only if:**
- **the child is HEB's, at that version, of the named work** (`CHILD_UNKNOWN`, `CHILD_STALE`, `CHILD_NOT_OF_WORK`);
- **the work's project is the subject's** (`PROJECT_MISMATCH`);
- **the child is `RUNNING` or `DRAINING`** (`CHILD_NOT_RUNNING`). A draining child can be stopped: a drain is a default, not a choice the operator has lost (HEB-07.c, HEB-07.f).

**What it records, in one step** (A-06 §3.3, "Operator chooses Stop now"):
- **the child's custody ends:** state `STOPPED`, and no further effects through it;
- **the supervisor stops the child's processes before, or together with, ending its invocation credentials** (§3.3: "Supervisor stops before/with revocation");
- **each of its open operations is cancelled with it,** each reported as requested, confirmed or unknown (AOI-07.e). Each stays open until its cancellation is confirmed, so no rerun of it is admitted before then (I2-05);
- **its continuation ends** (I2R1-5). §3.3: "No continued child effects through stopped grant". C17 cannot continue it, and HEB admits no further execution through its custody or under its grant. HEB-08.h's continuation is for an interrupted child; a stopped one is the operator's choice not to go on. The Lead goes on with the work through a fresh admission;
- **its interruption is recorded for reconciliation** (§3.3: "record interruption/reconcile"). That is the reconciliation of its effects, which is HEB's and R-01's. It is not a continuation;
- **its files and logs are preserved, and not admitted** (§3.3);
- **its held results stay held** (I2R1-11). C15 and C14 decide them.

**What it never does:** everything in I2-01c. In particular, it never revokes the child's grant, and never makes its earlier results untrusted.

**It does not bar a later rerun, or a fresh admission of the work** (I2C2-3). A stop reaches the child's grant, not the work (A-06 §3.3). Once its cancellations are confirmed, and reconciled for a non-idempotent definition, the Lead may rerun the stopped child's operations in a new custody under its own grant (I2-05), or admit the work afresh. The operator's means to bar that is A02, suspending the Lead's grant, or A01, revoking the child's lineage, which every rerun of its definitions reads (I2-05). C03's template line says so (I2-10).

**No competence read** (I2R1-7). A stop only reduces, and ADC-08.d requires that AEW "provide the responsible authority an effective means to revoke controlled execution without requiring agreement by the affected agent". So it is admitted on the operator's consent alone, on I3-01's ground ("A revocation only reduces, and ADC-08.d gives the responsible authority an effective means to revoke"), as A-25's `SUSPEND_GRANT` and A-30's `REVOKE_LINEAGE` are. AOI-07.f does not block it either: "A protective reduction shall use its governing **current** authority and exact already-consented protective scope without being blocked solely by agent-writable changes to irrelevant or newly enumerated basis members".

**R01-19** (I2C2-4). The target's reason reference records the operator's reason. R01-19's ladder of non-destructive options governs the response to "nonemergency degradation": R-01's supervision. An operator's Stop now is not that response. It is HEB-07.c's operator disposition, and ADC-08.d requires it to be effective "without requiring agreement by the affected agent". So the ladder does not gate it. R01-19's last sentence is not relied on: its subject is "qualified safety-critical protection or a separately authorized emergency", which a routine Stop now is not.

## I2-03. `RELEASE_CHILD_TO_MANUAL` (C04), protected, owner HEB

**Outcome:** with the operator's consent, HEB ends AEW's execution authority over one child, and hands its artifacts to the operator outside AEW governance.

**The target names:** as I2-02.

**HEB admits it only if:** as I2-02, except the state. **The child is `RUNNING`, `DRAINING`, `INTERRUPTED` or `STOPPED`:** there are artifacts to hand over. `RELEASED`, `ABANDONED` and `ENDED` are `CHILD_NOT_RELEASABLE`.

**What it records, in one step** (A-06 §3.3, "Operator chooses Release to manual"):
- **a running or draining child is stopped first,** as I2-02: "Stop child before/together with credential revocation";
- **the child's state is `RELEASED`.** "No further AEW child execution": its continuation eligibility ends, so C17 cannot continue it (as I2-07, HEB-08.h);
- **its artifacts (files and logs) pass to the operator outside AEW governance.** HEB records their identity, by digest, so that a later return is recognized as an untrusted external contribution (HEB-02.l, AEV-09.d). They are "not automatically accepted as evidence";
- **its held results stay held** (I2R1-11). A draining child may already have held drain results (HEB-07.e). The artifacts handed over are outside AEW governance; the held results' records, and their decisions, stay with C15 and C14.

**What it never does:**
- **it is not external development** (A-06 §1.1). It reenables nothing, grants no authority to run external tools, and certifies nothing about the operator's environment;
- everything in I2-01c.

## I2-04. `CANCEL_CHILD_OPERATION` (C06), protected, owner HEB

**Outcome:** with the operator's consent, HEB cancels one admitted operation: a child's, or a rerun's (I2C2-2). For a child's operation, the child, its custody and its other operations go on. A rerun's custody holds its one operation, so it ends with the cancellation's outcome.

**The target names:** the operation and its version; the operation's work; a reason reference.

**HEB admits it only if:**
- **the operation is HEB's, at that version, of the named work** (`OPERATION_UNKNOWN`, `OPERATION_STALE`, `OPERATION_NOT_OF_WORK`);
- **the work's project is the subject's** (`PROJECT_MISMATCH`);
- **the operation is pending or running** (`OPERATION_NOT_ACTIVE`).

**What it records:** the cancellation, requested. The operation is `CANCEL_REQUESTED` until HEB observes its end (`CANCEL_CONFIRMED`) or reports it unknown (AOI-07.e). Its partial diagnostics are kept (HEB-06.e: "without erasing useful partial diagnostics").

**What it never does:**
- **a cancelled operation is never a PASS** (HEB-06.e's witness: "A cancelled test is displayed as PASS");
- **it cancels no parent authority, and overrides no separately governed hold** (C19's text, which holds for the operator's cancel too);
- everything in I2-01c.

## I2-05. `REQUEST_BACKGROUND_RERUN` (C07), a delegated row, owner HEB

**Outcome:** the current Lead asks HEB to run one prior operation's admitted definition again, against the work's current accepted revision, under the Lead's current grant. HEB admits it as a new operation, in a new custody: one more attempt of the same original operation intent.

**Origin:** I1-01's class, `CURRENT_SUCCESSOR_GENERATION`, as I4-02: CS-07's authenticated session, both proof slots `null`, and the subject naming the Lead's seat. HEB reads its own seat fact (`ACTOR_NOT_CURRENT_LEAD`, `GENERATION_FENCED`; a hold when unavailable).

**The target names:** the prior operation and its version; the work and its current accepted revision; the Lead's grant.

**The unit is the original operation intent, not the named attempt** (I2R1-1, I2R1-2). R01-31 keys the attempts to "the stable work identity and owner-qualified original operation intent", and a rerun is one more attempt of it. So every rule below reads **every attempt of that intent,** whichever attempt the target names. Reading only the named one would let a rerun of attempt 1 step around attempt 2.

**What a rerun rests on, all of it, from the start:**
1. **the definition, and so every lineage that admitted an attempt of the intent:** the original admission's lineage, which the definition keeps however many reruns follow, and each later attempt's;
2. **the subject it runs against:** the work's current accepted revision, from WIS;
3. **the authority it runs under:** the Lead's current grant;
4. **the intent's attempt ceilings,** from R-01 (R01-31);
5. **every attempt's state and outcome:** whether any is still open, and whether each one's completion and effects are known (HEB-08.d).

**HEB admits it only if:**
- **the operation is HEB's, at that version, of the named work** (`OPERATION_UNKNOWN`, `OPERATION_STALE`, `OPERATION_NOT_OF_WORK`);
- **no attempt of the intent is open** (`ATTEMPT_OPEN`): none is pending, running or cancel-requested.
  - A cancellation settles only when HEB observes its end (`CANCEL_CONFIRMED`), never when it is requested (AOI-07.e). So "the Lead cancels it first", by C19 for its own or by the operator's C06, means the cancellation is confirmed.
  - A stop's cancellations (I2-02) stay open in the same way. So no rerun of a stopped child's operation is admitted until they are confirmed, and, for a non-idempotent definition, reconciled. A stop does not bar a rerun after that (I2-02, I2C2-3).
- **every attempt's completion and effects are known, or the definition is qualified idempotent or non-effecting** (`PRIOR_OUTCOME_UNKNOWN`, reason `PRECONDITION_STALE`; I2-11).
  - HEB-08.d: no automatic replay "pending qualified reconciliation and fresh authorization where required". R01-30: "If a material effect remains unknown, use original-intent reconciliation or request competent disposition rather than replay."
  - A confirmed cancellation of a non-idempotent attempt leaves its effects unknown until HEB records them reconciled.
  - **Who qualifies idempotency** (I2R1-3). HEB records, at the original admission, the governing policy's qualification of the definition's effect class: R01-30's "declared idempotent or non-effecting by competent governing policy/profile".
  - **It is never the requester's label.** AOI-07.a: "a caller-supplied direction or action label is not authoritative". ADC-05.g: no control is lowered "on the strength of an interested actor's unsupported assertion". Unknown or unqualified means non-idempotent.
  - That policy is part of the effect acceptance that A-05 §5's mediated-effects row is required before. The rerun is held for that row until it is adopted (I2-08).
- **no lineage that admitted an attempt of the intent is revoked** (`OPERATION_FROM_REVOKED_LINEAGE`; `CLASSIFICATION_UNAVAILABLE`, a hold). For each one, its generation's newest classification is not `TRUST_REVOCATION`, and its grant lineage is not revoked. This is I4-01c's trust rule, read over the whole attempt series:
  - **the original admission's lineage, which is the definition's.** A rerun never changes the definition, so a revoked lineage's definition is not re-executed on its say-so through any later attempt (ADC-02.f);
  - **each later attempt's lineage, to fail closed.** Reading it costs only what the refusal already offers: the Lead admits a fresh operation through the normal path;
- **WIS's current accepted revision is the one named** (`WORK_REVISION_STALE`; `WORK_STATE_UNAVAILABLE`, a hold). A rerun against an older revision, for diagnosis, is backlog I2-B3;
- **ADC's grant fact shows the Lead acting within its delegated authority,** as I4-02 reads it, on that work and revision;
- **R-01 shows headroom for one more attempt of the intent** (`ATTEMPT_LIMIT_REACHED`; `RESOURCE_STATE_UNAVAILABLE`, a hold). A rerun never resets the ceilings, and the attempt count runs from the original.
  - **On exhaustion** (I2R1-6), R01-31 applies: "Exhaustion leads to a held/waiting decision, not a new identity to reset a cap. Only an attributable competent authorization may grant extra headroom".
  - That held/waiting decision is R-01's fact. The refusal's `owner_evidence_ref` names it, so the Lead sees what is waiting, and on whom. HEB records nothing for it (I2-01c).
  - Once R-01 shows headroom, a later rerun is admitted. Granting headroom is none of the 86 actions (backlog I2-B4).

**What it records:**
- **a new attempt, in a new custody** (I2R1-5). It is an admitted background operation under the Lead's current grant and seat generation, in a custody HEB admits for it.
  - It is never admitted into the prior operation's child custody, whether running or ended, and never under that child's grant. No execution re-enters a custody that ended (`STOPPED`, `RELEASED`, `ABANDONED`, `ENDED`).
  - **It is confined no less than the original attempt.** A-06 §3.2: "Untrusted build/test execution takes place in an appropriately confined actor". A worker-admitted definition never gains the Lead's wider egress (the operator's decision of 2026-10-21) by being rerun under the Lead's grant;
- **the prior operation, the original intent and the attempt number;**
- **its attribution: every lineage it rests on** (I2R1-1). That is every lineage that admitted an attempt of the intent, the original admission's first, then its own.
  - **Nothing of the prior operation's authority carries over:** it is admitted under the Lead's current grant alone. **Nothing of its trust is shed either:** the attribution keeps the definition's lineage.
  - **What A-31 reads of it, as written** (I2C2-1). A-31 names one producing lineage per item: I4-01c, "the grant under which the producing invocation was admitted", and C15's read of "the result's producing lineage" (I4-04). For a rerun, that is the Lead's grant. The attribution's other lineages reach a readiness's trust basis, and C15's lineage read, only when A-31 reads every lineage in a cited item's attribution. That is backlog I2-B5, joined to I4-B7.
  - **Until then:**
    - W09 stays held (I4-06), and I4-B7 must be answered before it is activated, so no readiness acts on the gap;
    - C15 can accept a held rerun result into review as input evidence after its definition's admitting lineage was revoked. That is **the C15 residual**, shown to the operator at adoption (I2-15). It is "into review and nothing more" (I4-04): no PASS, integration or publication;
    - no HEB refusal is added to C15 here: that would rewrite I4-04;
  - The attribution is a list of lineages. Its shape joins I4-B8, and its reach joins I4-B7 (backlog I2-B5);
- **the prior attempts' records stay unchanged:** "Preserve all prior attempts … adverse findings" (R01-31), and each result keeps its diagnostic value (HEB-06.h).

**Its custody lives no longer than the Lead's authority** (I2C2-2). A rerun runs under the Lead's current grant alone, with no independently bounded invocation authority of its own. HEB-07.d: already-admitted operations survive ordinary detachment "only under their valid independently bounded invocation/custodian authority". So at the Lead's detachment (its attachment's close), or at the end of its seat generation, whichever comes first:
- **HEB stops it.** Its cancellation is requested and observed apart (AOI-07.e). Its interruption is recorded for reconciliation, and its effects stay reported (HEB-07.h). It is never drained: a drain is for a child with its own authority (HEB-07.i);
- **the close surfaces it** (HEB-07.c), as outstanding work that ends with the close. Its one disposition at the close is that stop. Drain and Release to manual are a child's, and a rerun is not one;
- **C03, C04 and I2-09's set do not name it.** The operator's means to stop it sooner is C06 (I2-04);
- **a later rerun of the intent** meets the open and outcome checks above, so a non-idempotent one waits for the reconciliation.

This is HEB-07.d's rule for a custody that has no authority of its own, not a change to the close.

**What it does not check, and why:**
- **the lineages that produced the revision's material.** The rerun runs that material confined, as any execution does (A-06 §3.2), and its result's evidence value is AEV's to assess, through the readiness's own trust basis (I4-01c);
- **whether a repeat is useful.** That is R-01's observation (R01-16), and never a refusal by itself (R01-20).

**It is held for A-05 §5** (I2-08): it is a new execution.

## I2-06. `DISCARD_HELD_RESULT` (C14), protected, owner HEB

**Outcome:** with the operator's consent, HEB ends its hold on one result by discarding it from active use. The result can no longer be accepted into current review. Its record stays.

**The target names:** the held result and its version; the result's work; a reason reference.

**HEB admits it only if:**
- **the result is one HEB holds, at that version, of the named work** (`RESULT_UNKNOWN`, `RESULT_NOT_HELD`, `RESULT_STALE`, `RESULT_NOT_OF_WORK`);
- **the work's project is the subject's** (`PROJECT_MISMATCH`).

A result from a revoked lineage may be discarded: that is protective (I2-00, I4-B6).

**What it records:** the discard: the result, its version, the reason and the consent. The result is no longer held. A later C15 for it is `RESULT_NOT_HELD`.

**What the record keeps, and who can still see it:**
- **the result, its diagnostics, its producing lineage and the discard all stay recorded** (HEB-06.e; R01-31: "Preserve all prior attempts … adverse findings");
- **a discard never removes the result from what AEV and the operator can read.** A held-result read shows it as discarded. An adverse result stays visible as a record. It is never admitted, integrated or published by this;
- **a discard is nobody's resolution of the adverse evidence it held** (I2R1-12). It never counts as an owner's "qualified absence or resolution of applicable adverse evidence" (R01-30). So neither R-01's recovery nor AEV can treat a discarded adverse result as settled. It stays referenceable as a material adverse record (WIS-06.d).

**Why the origin stays the operator's, as the classification proposed:**
- C15's acceptance brings a result into review, where AEV assesses it. A discard keeps it out of current review.
- If the Lead could discard, a steered Lead could keep an adverse held result out of the current review of its own work.
- The operator's origin closes that route, which the operator's proportionate-containment decision of 2026-10-21 keeps: an owner-fact route. A result the Lead neither accepts nor the operator discards stays held, and visible.

**It binds content the operator must read, so I5-08a applies:** it is held with `CONTENT_READ_UNAVAILABLE` until a selected read shows the operator the held result. D-01 0.3.4 has no held-result read. I4-10 already asks for one.

## I2-07. `ABANDON_INTERRUPTED_EXECUTION` (C20), a delegated row, owner HEB

**Outcome:** the current Lead decides that one interrupted child of its work will not be continued. HEB records the abandonment and ends the child. The work itself, and everything the child left, stay as they are.

**Origin:** as I2-05.

**The target names:** the child and its version; the work and its current accepted revision; the Lead's grant; a reason reference.

**HEB admits it only if:**
- **the child is HEB's, at that version, of the named work** (`CHILD_UNKNOWN`, `CHILD_STALE`, `CHILD_NOT_OF_WORK`). The child may have run on an earlier revision of the work: abandoning it is protective;
- **the child is `INTERRUPTED`** (`CHILD_NOT_INTERRUPTED`). A running or draining child is stopped by the operator's C03, or by its own drain and stop conditions (HEB-07.f), not abandoned;
- **ADC's grant fact shows the Lead acting within its delegated authority,** as I4-02 reads it, on that work and its current revision.

**What it records, in one step:**
- the child is `ABANDONED`. Its continuation eligibility ends, so C17 cannot continue it (HEB-08.h);
- **HEB releases the capacity the child held** (I2R1-8), in R01-25's sense: compute and advisor capacity. It releases no quarantine or containment of what the child left (HEB-03.h; AOI-07.c);
- **its partial results and diagnostics are kept** (HEB-06.e, HEB-06.h);
- **its held results stay held.** C15 and C14 decide them;
- **the reason is recorded.** R01-20: a context-destroying response never has "solely a stall … heuristic as its recorded competent basis". The Lead's decision under its grant is the basis, and the record carries it.

**What it never does:**
- **it is not a Ticket's cancellation or revision.** WIS's work is unchanged (W03 is WIS's);
- **it is not external-effect settlement.** The child's uncertain or residual effects stay reported for reconciliation (HEB-07.h);
- **it gains no authority** (the catalogue: "no retained grant escalation"). Everything in I2-01c.

## I2-08. Activation needs the adopted parameters (A-05 §5)

**I3-09's rule, unchanged:** a type is held only for the effect that an unadopted A-05 §5 row is "Required before", with `POLICY_UNAVAILABLE` (`SOURCE_UNAVAILABLE`), allocating nothing and consuming no consent.

| Type | When it is held | The row, and what it is "Required before" |
|---|---|---|
| `STOP_CHILD_NOW`, `RELEASE_CHILD_TO_MANUAL`, `CANCEL_CHILD_OPERATION`, `DISCARD_HELD_RESULT`, `ABANDON_INTERRUPTED_EXECUTION` | **never.** Each only reduces. A-05 §5's preservation rule keeps "current effective … containment, revocation … controls" effective | "Minimum mediated effect channels …" is required before "claims of effective revocation". So `EFFECT_CONFIRMED` means HEB recorded the disposition, and admits no further mediated request through that custody (HEB-01.d). Any claim that effects stopped stays with that row (I2-01a, as I3-04). "Hold/provisional hold qualification …" is required before "**Automated** consequential stop, release and recovery". For the four protected types, the operator's consent is not automation. **The abandon is not the operator's** (I2R1-8): it is a deliberate Lead decision under a current grant, recorded with its basis (R01-20). It stops no process and releases no hold, so that row does not reach it either |
| `REQUEST_BACKGROUND_RERUN` | **always,** for the first two rows | "Minimum mediated effect channels, effect acceptance …": "Protected execution". "Resource hard ceilings and ongoing limit enforcement": "Controlled multi-agent execution". A rerun is new execution under a delegated grant, which is what that effect is (I2R1-9) |
| `REQUEST_BACKGROUND_RERUN` | **also, for a prior operation whose definition mutates source** | "All mutable-agent launch permissions …, assignment-workspace isolation …": "Activating any source-mutating agent" |

**Holds are per row, not per type,** as I3-09.

**I5-08a holds `DISCARD_HELD_RESULT`** until the held-result read exists (I2-06).

## I2-09. Sets, and a close with explicit child dispositions

- **A protected set may hold `CLOSE_ATTACHMENT` with `STOP_CHILD_NOW` and `RELEASE_CHILD_TO_MANUAL` members** for that attachment's children. This extends A-24's close-only selection: it is I2-00's third departure (I2R1-4). CS-02 allows it, because the set has one origin class. CS-06 binds one consent to the exact member list.
- **One disposition per child** (I2R1-4). A set with two stop or release members for one child is `invalid_request`: a Problem, with no receipt. Nothing is read, nothing changes, and no consent is used. The operator's choice for a child is one.
- **Each member is admitted on its own** (CS-05, AOI-07.b), and its result is its own. Consent to one member authorizes no other (CS-06).
- **The close's target and its wire definition are unchanged, and so is its drain of every child with no member of its own** (HEB-07.c: "applying the preserved default"). HEB-07.i's default is for "an eligible admitted child with no operator-selected disposition", and a child with a stop or release member in the set has one. That is how C05's "separate atomic child intents … no caller-supplied default and no undisclosed child targets" becomes explicit.
- **A running rerun of the closing Lead's generation ends with the close** (I2-05, I2C2-2). It is surfaced and stopped, never drained, and no member names it. That is HEB-07.d's, so the close is unchanged.
- **The set rule, stated outcome-first** (I2R1-4). HEB settles the close's drain of a child that has a member once that member's outcome is known. That holds whichever of the two CS-01's canonical order (ascending `intent_ref`) evaluates first.
  - **If the member takes effect,** the close leaves the child to it, and the member acts on the version the operator consented to.
  - **If the member is refused or held,** the child drains as any other. That is the preserved protective default, never a child left running after its attachment closed.
  - **Until the member's outcome is known,** nothing else in the set acts on that child.
- **So the outcome does not depend on canonical order:** the close spares exactly the children whose own member takes effect, and drains the rest.
- **The display warns** (AOI-07.a: the trusted display shall "explicitly warn that partial/refused/unknown outcomes are possible"). G3-03 renders "one `TEMPLATE` line per member, naming its action", from records, never from client text. I-2 states what the two actions' fixed template text must say, whatever else is in the set: "if this member is refused or held, the child is not stopped (or released); when its attachment closes, it takes the close's default". The text is fixed per action, so it depends on nothing outside the member. It is still the member's one template line, so I2-10's bound is unchanged, and A-26 is unchanged.
- **The delegated two share a set with each other and with the other `CURRENT_SUCCESSOR_GENERATION` rows** (I2R1-10). They never share one with a protected row, nor with C17 or C19, which are `CURRENT_DELEGATED_GRANT` (CS-02). So the Lead's cancel of its own invocation (C19) and a rerun are two sets.

## I2-10. What the operator sees, and what is readable

- **The consent is A-26's, unchanged.** Each protected member renders within the 30 lines G3 allows (`verify_i2.py` derives this).
- **C03's fixed template text** (I2C2-3) also says that a stop does not bar a later rerun of the child's operations, or a fresh admission of its work. It is still the member's one template line.
- **`IntentResult`:** every type reports `ADMITTED` and `EFFECT_CONFIRMED` at admission, owner `HEB`, with I2-01a's meaning. A confirmed rerun means HEB admitted the new operation, never that it passed. A rerun refused at an exhausted ceiling carries R-01's held/waiting decision in `owner_evidence_ref` (I2-05).
- **What a D-01 change must add:**
  - on the runs read: each child's custody state and version, and its continuation; each operation's state, version, custody, original intent, attempt number, attribution and process outcome (requested, confirmed or unknown);
  - the held-result read (I4-10), with a discarded result shown as discarded;
  - a release's artifact identities;
  - on the continuation state (C18): whether an interrupted child was abandoned;
  - at a close: each running rerun that ends with it (I2C2-2).

## I2-11. Ordering, atomicity and refusals

- **One admission path, as I4-11:** origin, then owner state, then the activation hold (I2-08), then at most one owner effect per member (CS-05). Every activation hold is decided from the type, the target and HEB's own record of the prior operation.
- **Each disposition is compare-and-set** on its subject's version, so it happens once. A rerun creates one new attempt. While any attempt of the intent is open, another rerun is `ATTEMPT_OPEN` (I2-05).
- **A set with two dispositions for one child** is `invalid_request`, before any owner state is read (I2-09).
- **The admitting owner's own state** unavailable is `UNKNOWN_OWNER_STATE`. Another owner's fact unavailable is a hold under its own reason: `GRANT_STATE_UNAVAILABLE`, `LEAD_STATE_UNAVAILABLE`, `WORK_STATE_UNAVAILABLE`, `RESOURCE_STATE_UNAVAILABLE`, `CLASSIFICATION_UNAVAILABLE`.
- **Each owner reason maps to an adopted reason code** in `wire/refusal-reasons-0.7.json`. The map is complete and fail-closed. **`PRIOR_OUTCOME_UNKNOWN` maps to `PRECONDITION_STALE`** (I2C2-N1). CS-04: "`UNRESOLVED_NO_REDISPATCH` means only a missing, corrupt or expired entry". And A04's owner-state repeat is "`PRECONDITION_STALE` … never `UNRESOLVED_NO_REDISPATCH`". No I-2 reason maps to `UNRESOLVED_NO_REDISPATCH`.
- **Two shared entries are unreachable for these HEB types, and stay for uniformity with A-31's delegated rows:**
  - `LEAD_STATE_UNAVAILABLE`: HEB is the admitting owner, so its own seat fact unavailable is `UNKNOWN_OWNER_STATE`;
  - for the rerun, `GRANT_STATE_UNAVAILABLE`: an unavailable ADC is reported first as `CLASSIFICATION_UNAVAILABLE`.

  Both are holds, so neither can admit anything.

## I2-12. The wire

`tools/build_i2_wire.py` generates `wire/` from A-31's frozen `STG-09 adopted/o01-0.6-i4/wire/`, pinned by its `SHA256SUMS`:
- **`o01-command-0.7-candidate`:** A-31's schema, byte-equal in every inherited definition, plus six Intent branches and six Target definitions: 37 actions.
  - The two delegated branches require the seat, and both proof slots `null` (I1-01).
  - The four protected branches require a `null` seat.
- **`openapi-o01-0.7.yaml`:** the same definitions, checked equal by the script.
- **`action-registry-0.7.json`:** A-31's 31 rows unchanged, plus six, five of them `REDUCING`.
- **`refusal-reasons-0.7.json`:** A-31's map, plus the six types' owner reasons.
- **`PREDECESSOR-PINS.json` and `SHA256SUMS`.** `--check` regenerates and compares.

## I2-13. Backlog

- **I2-B1, a quiesced execution (C12, C13).** An adopted owner fact would say what quiescence is (a safe point at which a child's process pauses, keeping its context), who records it (HEB, with R-01's process state), and what resuming needs: AOI-07.c makes releasing a containment authority-increasing. The candidates are an HEB amendment, or R-01's wait and yield (R01-25) widened to an operator request.
- **I2-B2, HEB's request for reconciliation of an uncertain effect** (I4-B3's HEB half, narrowed). HEB-08.d's hold clears by HEB's own qualified reconciliation.
- **I2-B3, a diagnostic rerun against an earlier revision.** HEB-06.h keeps such a result's diagnostic value apart from verification. It needs a grant that covers the earlier revision, and a profile of its own.
- **I2-B4, headroom for an exhausted intent** (I2R1-6). R01-31: "Only an attributable competent authorization may grant extra headroom". None of the 86 actions grants it. It belongs with resource policy (I-6), or with R-01's own competent authority.
- **I2-B5, the attribution's reach and shape** (joins I4-B7, and I4-B8 for the shape; I2C2-1). The rerun's attribution is a list of lineages (I2-05). **The outcome I-2 needs from I4-B7:** a cited item's lineages, and C15's lineage read, are every lineage in its attribution. I4-B7 already reopens I4-01c, and must be answered before W09 is activated. When I4-B8 settles one attribution shape for every AEV and HEB record that names an actor, the list is that shape's content. Until I4-B7 is answered, the C15 residual stands (I2-15).

## I2-14. Questions for the review

Round 1 answered these (`reviews/2026-10-23-I2-review-round-1.md`, section 3). `CHANGES-r2.md` says how revision 2 takes each answer, and what the targeted check is asked. The targeted check answered its seven questions (`reviews/2026-10-23-I2-check-revision-2.md`, section 4), and `CHANGES-r3.md` says how revision 3 takes its findings.

- **Q1 (I2-00):** is the fit right? In particular: C03 against A01 and A02; C06 against C19 and C03, by subject; and C12 and C13 as no type.
- **Q2 (I2-00, I2-07):** is "stage" read correctly as an interrupted child, and is HEB its owner rather than WIS?
- **Q3 (I2-06):** is C14's origin right to stay the operator's, and does a discard keep an adverse result visible in every read that matters?
- **Q4 (I2-05):** is the rerun's rule stated over everything it rests on, from the start (I-4's lesson)? Is any check missing, or any check more than proportionate?
- **Q5 (I2-09):** is a close with explicit stop and release members right: HEB-07.i's drain applies only to the children with no member that takes effect, `CLOSE_ATTACHMENT` is otherwise unchanged, and the outcome is independent of member order?
- **Q6 (I2-00, I2-08):** are the five `REDUCING` directions and the activation holds right?

## I2-15. Not claimed

- **This selects interface architecture.** It qualifies no host, builds nothing, and activates no action. The protected rows stay held wherever G3 is not established. The rerun waits for its A-05 §5 rows (I2-08), and the delegated rows need an HEB-qualified Lead generation (I1-01).
- **A correction for the adoption record** (I2R1-13). The start decision and map v1.19's increment table said C07 and C20 are "usable before G3 qualifies". I1-01 corrected that for every delegated row: they need no G3 consent per command, but an HEB-qualified Lead generation needs G3-protected attach. The map's table is corrected with this revision. The start decision is append-only, so I-2's adoption record notes the correction.
- **The C15 residual, for the adoption record, as a trim item** (I2C2-1; the I-4 adoption's pattern). Until A-31 reads every lineage in an item's attribution (I2-B5, with I4-B7), C15 accepts a held rerun result into review as input evidence, even if its definition's admitting lineage was revoked after the rerun's admission. A revocation before the rerun's admission is refused by I2-05. Into review and nothing more: W09 stays held (I4-06).
- **Candidate mechanisms are not claimed:** HEB's custody record, the process stop, the credential ending, the artifact hand-over, and the rerun's admission.
- **Out of scope:** D-01 changes; A-31's 31 actions, which are unchanged; R-01's ceilings themselves; the backlog above.
