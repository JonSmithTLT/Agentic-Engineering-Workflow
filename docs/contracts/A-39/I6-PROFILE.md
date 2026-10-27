<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-39
source: 30-stages/STG-14-I6-resource-model-and-host-policy/adopted/o01-0.8-i6/I6-PROFILE.md
source-sha256: e7413de4a9f82a26015e90f5d92783c90f84fcd87aefb0278d73b49d66be780f
edits-sha256: none
-->

# I-6: the resource, model and host policy, selection profile (PROPOSED, revision 3)

**Namespace:** `I6-`
**Status:** proposed, revision 3, 2026-10-24, answering round 2 (`CHANGES-r3.md`; revision 2 answered round 1, `CHANGES-r2.md`), for the O-01 `o01-command-0.8-candidate` wire in `wire/`, the successor of A-34's 0.7. It amends no adopted text. Its adoption waits for the as-built trace's flags in its areas (STG-12; the start decision).
**Authority:** the operator's decision `00-governance/decisions/2026-10-24-operator-start-I-6.md`, on the adopted classification's I-6 (A-32).
**Threat model:** the operator's decision of 2026-10-19 (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`): design against steered agents and AEW bugs, not malicious code run as the operator. Proportionate containment (2026-10-21): restrict the approval, owner-fact, credential and escape routes. The security depth reset and the pass over G3 and containment (2026-10-24): G3 counts once installed, while containment's launch self-test passes; G3-12's qualification record is cut.
**Research consulted:** added at adoption, 2026-10-25, under the look-up-first rule of that day, which postdates revision 3; no rule changes for it. `tools/research_index.py lookup` on A-15, A-17, A-18, A-20, A-21, A-32, `R-DEC-03` and `R-DEC-04`: for R-01 and the steering mode, `external-workflow-2026-10-05`, `agent-effectiveness-2026-10-09`, its public synthesis and `external-agent-workflow-lessons-2026-09-28`; for the host profile, `containment-and-process-ownership-rocky8-research-2026-10-01`; for the model route, `provider-api-2026-10-11`; none for A-18, A-21 and A-32. One finding is departed from: `external-workflow-2026-10-05` recommends `WALK`, not `CRAWL`, as the default, because `CRAWL` adds a confirmation to every trivial step, while I6-06.g starts each Lead generation at `CRAWL`. The reason is I6-R01's. In V-01 the two behave the same, because `WALK` reaches nothing there (`R-DEC-04`), so the choice is reopened when an owner declares a step that `WALK` reaches.
**Files:** this profile; `wire/`, generated from A-34's frozen bytes; `verify_i6.py`, `i6-cases.json` and `verify_i6_mutation_kill.py`; `CHANGES-r2.md` and `FINDINGS.json`; the working notes `work/AS-BUILT-READ.md` and `work/FIT-CHECK-NOTES.md`, which are not normative.

## What the adopted text already decides

- A requested selection is a requested target only, and never by itself the effective or qualified state (`IF13-03`).
- An issued policy decision is immutable history. Current issuer-qualified replacement or revocation events govern at effect time, and a mandatory parent cap still applies (`O01-09`).
- The provider route is part of the deployment manifest (`S01-02`) and of a profile's identity (`IF13-02`), and changing it is a profile transition (`S01-22`).
- A configuration file or runtime setting is a projection, never an issued policy decision (`IF10-04`, `S01-14`).
- A profile may add requirements, and never relaxes the adopted portable security floors (`S01-03`). It never promotes a policy by itself (`S01-23`).
- A steering mode only decides whether an otherwise eligible, explicitly auto-runnable action waits for confirmation. It alters no risk class, grant, effect scope, assurance eligibility, hold, hard limit or judgment, and a change affects future admissions only, with version and fencing (`R01-38`).
- Releasing exposure needs comparable provider evidence, or another competent justified closure, from a meter outside the metered lineage (`IF10-13`, `IF10-15`). A requester's report never lowers exposure (`R01-08`). Only the operator's or ADC's policy owner grants headroom (`R01-05`, `R01-31`).
- Host and capability qualification is an outside-lineage assessor's record (`IF13-06`, `IF13-07`, `S01-09`, `S01-18`). An explicit revocation invalidates the affected assessments (`IF13-14`).
- Migration is U-01's own governed path, never implied by a transition (`IF13-17`).
- Hard limits are enforced on ongoing AEW-controlled execution as well as on new allocations (`ADC-08.f`), at each class's actual enforceable granularity (`R01-09`).
- G3 renders every covered leaf's exact value from records, plus at most one owner fact per member, and nothing else (`G3-03`).

## The parts

| Party | What it is | Who writes it | Who reads it |
|---|---|---|---|
| The resource policy issuer | the external issuer of standing resource policy (P05's owner, `IF10-04`) | its own decisions, on the operator's G3 consent | R-01's admission at effect time; the operator, through D-01 |
| R-01's writer | the competent writer of R-01's records: the steering mode, and the exposure and reconciliation of each original operation (`R01-01`, `R01-38`) | R-01, on qualified evidence and on the operator's G3 consent | the auto-runner; IF-10 admission; the operator |
| IF-13's configuration controller | the owner of profile definitions, their revisions and transitions (`IF13-10`, `IF13-11`) | IF-13, on the operator's G3 consent | HEB and ADC admission, R-01, IF-12 at dispatch; the operator |
| The host assessor | the qualified assessor outside every agent lineage (`IF13-07`) | its own assessment records | IF-13, and HEB's protection gate |
| The operator | the only source of G3 consent (A-26) | consents, through G3 | everything, through D-01 |
| The current Lead | the actor whose delegated actions the auto-runner may take | its own delegated actions | its own projections |

## Rules

### The fit

**I6-00. The fit: five of I-6's rows get a new type, and the other four are served by adopted types or wait for an open owner.** No row moves from operator origin to delegated, so none loosens an authority.

| Row | Catalogue symbol | Fit | Reason |
|---|---|---|---|
| P06 | `NARROW_OR_REVOKE_POLICY` | **New type `NARROW_OR_REVOKE_STANDING_POLICY`, protected, owner `RESOURCE_POLICY_ISSUER`, `REDUCING`** (I6-02) | `O01-09` keeps a replacement or revocation apart from an issuance. A registry row has one direction, and `ISSUE_STANDING_POLICY` is `PRESERVING_OR_INCREASING`. A narrowing made through it would be held, and could be blocked by churn, as an increase is. `AOI-07.f` keeps a protective reduction free of both |
| P07 | `WIDEN_RESOURCE_LIMIT` | **No new type: A-24's `ISSUE_STANDING_POLICY`,** issuing a successor revision (I6-03) | `O01-02` binds an issuance to "relevant current policy predecessor", and `O01-09` makes a newer issuance the replacement. A widening is that issuance. A limit that is not a standing policy waits for backlog I6-B1 |
| P14 | `ADOPT_MANIFEST_EDIT` | **New type `ADOPT_MANIFEST_EDIT`, protected, owner `IF13`, `PRESERVING_OR_INCREASING`** (I6-04) | It records a new revision of a profile definition, from exactly one typed change whose old and new values G3 renders. `REQUEST_PROFILE_CHANGE` selects a revision that already exists. A set member cannot name a revision that another member's admission will create, so this type also requests its own revision's transition |
| P04 | `SELECT_MODEL_PROVIDER_ROUTE` | **No new type: `ADOPT_MANIFEST_EDIT`** changing a route setting (I6-05) | The route is part of the definition (`S01-02`, `IF13-02`). Choosing one is a change to the definition, and its consequences are checked at each dispatch (`IF12-04`, `IF12-10`) |
| P08 | `SET_STEERING_MODE` | **New type `SET_STEERING_MODE`, protected, owner `R01`, `PRESERVING_OR_INCREASING`** (I6-06) | `R01-38`'s mode, with R-DEC-04's four items stated. One type covers both directions, as `I3-05`'s autonomy does. The mode reaches only actions an owner's adopted rule makes explicitly auto-runnable, and no owner has adopted one yet (I6-06.c, I6-B6) |
| P10 | `RECONCILE_UNKNOWN_CHARGE` | **New type `REQUEST_CHARGE_RECONCILIATION`, protected, owner `R01`, `PRESERVING_OR_INCREASING`** (I6-07) | It asks R-01 to reconcile one original operation's unknown exposure from qualified evidence. It never settles a charge (the catalogue: "not … manual force-settled") |
| P12 | `QUALIFY_OR_REVOKE_HOST_PROFILE` | **Split.** Qualifying is the assessor's record, with no O-01 type. **Revoking is the new type `REVOKE_HOST_QUALIFICATION`, protected, owner `IF13`, `REDUCING`** (I6-08) | An operator's label never qualifies a host (`IF13-07`; the catalogue: "not operator label"). An explicit revocation only invalidates (`IF13-14`) |
| P11 | `CHANGE_HOST_INSTALLATION` | **No type.** The profile half is `REQUEST_PROFILE_CHANGE` at the new installation; the migration half waits for U-01 (I6-09, I6-B2) | A profile change names its installation (`O01-02`). Moving a project's state is U-01's (`IF13-17`) |
| U10 | `UPGRADE_OR_ROLLBACK_AEW` | **No type: U-01 is an open domain** (I6-B2) | Its owner text: "U-01 migration/integrity … separately designed" |

**The departures from the adopted classification (A-32), which the operator confirms or refuses at adoption:**

| Row | The classification proposed | This profile | What changes for the operator |
|---|---|---|---|
| P04 | its own type, owner IF-13 | served by `ADOPT_MANIFEST_EDIT` | Choosing a model is a one-setting edit of the profile definition. The consent shows the setting, its old value and its new value |
| P07 | its own type, owner the issuer | served by `ISSUE_STANDING_POLICY` | A widening is a new revision of the standing policy. **Its consent shows the new bounds and names the revision it replaces, but not that revision's values,** because A-24's target carries none (I6-12, I6-B7). Limits other than a standing policy have no command yet (I6-B1) |
| P12 | one row, origin `OWNER_DECISION`, owner S-01 | qualifying stays the assessor's; **revoking becomes the operator's, through G3**, with IF-13 recording it | The operator gains a protective power: withdrawing a host's qualification. It only reduces, and it never withdraws G3 (I6-08.d) |
| P14 | the "governing config/manifest owner" | **IF-13, for profile definitions only.** Another owner's configuration is not adoptable through it (I6-04.c, I6-B3) | **There is no governed path at all, in either direction, for ADC's classification policy and floors, AEV's checks, CNI's messaging, or limits that are not standing policy:** the operator can neither loosen nor tighten them through configuration. Each needs its owner's own path, and until one exists it stays as adopted. **No remaining increment carries one** (I-7 is RX-01, K-01 and P-01), so whether a path gets an increment is the operator's to decide (I6-B3). **Two placements:** AEW's containment lane is the installation's, not a setting (I6-04.c). V-01's configure step sets the project's check command at setup, as part of the project's first configuration at the console, as `aew init` is (L10), so it is no O-01 command and costs no PIN. Setup ends when the project's first assignment is admitted (`AEV-01.a`). After that, the check command is AEV's governed check (`AEV-02.f`, `AEV-05.i`), and neither adding nor removing a check has a path yet (I6-B3) |
| P11, U10 | their own types | no type until U-01 exists | Neither is available yet |
| The set rule, on A-24's types | a set evaluated member by member (CS-05) | **one member per subject** (I6-11) also reaches `ISSUE_STANDING_POLICY` and `REQUEST_PROFILE_CHANGE` | A set with two of those members for one policy decision or one profile definition is `invalid_request`, where A-34 evaluated each member. It fails closed, and the outcome no longer depends on canonical order |

**Also for the operator to know at adoption:** the steering mode reaches nothing yet. Every action waits in every mode until its owner adopts a rule that makes it explicitly auto-runnable (I6-06.c, I6-B6).

**I6-00a. Inherited definitions change in one place only: the owner enums gain `R01`.** A-30 added `AEV` the same way.
- **What changes:** `owner_hint` and `IntentResult.owner` gain `R01`, for `SET_STEERING_MODE` and `REQUEST_CHARGE_RECONCILIATION`. R-01's writer is not the resource policy issuer: it issues no policy (`R01-01`).
- **What does not:** every other definition, branch, target, registry row and refusal entry of A-34's 37 actions is carried byte-equal. In particular, `ISSUE_STANDING_POLICY` gains no refusal (I6-03).
- **One behaviour of two A-24 types changes at set level, not in their definitions:** the one-member-per-subject rule (I6-11) reaches a set holding `ISSUE_STANDING_POLICY` or `REQUEST_PROFILE_CHANGE`, and the departure table records it.

**I6-00b. The protection direction is derived by the owner from the operation, never from a label** (`AOI-07.c`, `O01-03`).
- **`NARROW_OR_REVOKE_STANDING_POLICY` and `REVOKE_HOST_QUALIFICATION` are `REDUCING`.** Each ends or tightens something and enables nothing.
- **`ADOPT_MANIFEST_EDIT`, `SET_STEERING_MODE` and `REQUEST_CHARGE_RECONCILIATION` are `PRESERVING_OR_INCREASING`.** A setting can widen what runs; a mode can let more run without a confirmation; a reconciliation can release exposure on qualified evidence. Each type covers both of its directions with the stricter one, as `I3-05` does.

### Who owns what

**I6-01. Each type has one sole admitting owner, which records only its own facts and reads every other owner's fact as an input** (`AOI-07.b`).

| Type | Records the fact (the sole admitting owner) | Whose decision the origin carries | Read only, as an input |
|---|---|---|---|
| `NARROW_OR_REVOKE_STANDING_POLICY` | the issuer: a revocation, or a successor revision with narrowed values | the operator's, by A-26's consent | none |
| `ADOPT_MANIFEST_EDIT` | IF-13: a successor revision of one profile definition, and a requested transition to it | the operator's | the definition's schema; the current functional snapshot |
| `SET_STEERING_MODE` | R-01: the mode record for one Lead generation | the operator's | HEB: the current Lead generation |
| `REQUEST_CHARGE_RECONCILIATION` | R-01: a reconciliation request for one original operation | the operator's | IF-10: the provider and account evidence, at reconciliation |
| `REVOKE_HOST_QUALIFICATION` | IF-13: the invalidation of one host profile's assessments at one installation | the operator's | the assessor's records |

**I6-01a. No I-6 type writes another owner's fact.**
- **ADC's grants are unchanged.** No type issues, widens, revokes or suspends a grant (`R01-38`, `IF13-09`).
- **AEV's evidence and holds are unchanged.** No type records a PASS, clears a hold or waives a review.
- **HEB's custody is unchanged.** A narrowing, a mode change and a host revocation stop no process themselves. Stopping is `STOP_CHILD_NOW`, `SUSPEND_GRANT` or `REVOKE_LINEAGE`.
- **WIS's work is unchanged.**

**I6-01b. Currentness is the owner's own version, never arrival order or a timestamp.** Every target names the version it acts on, and a stale one is refused under its own name.

### `NARROW_OR_REVOKE_STANDING_POLICY` (P06)

**I6-02. With the operator's consent, the issuer revokes one standing policy decision, or replaces it with a successor revision that is narrower in at least one value and wider in none.**

**The target names:** the decision, its current revision and its issuer; the change, `NARROW` or `REVOKE`; the decision's current ceiling with its unit, its effective-from, expiry and enforcement, which the issuer checks, so the consent shows what is narrowed from; for `NARROW`, the new value of each changed field; and a reason reference.

**I6-02.a** The issuer admits it only if the decision is its own, at that revision and not revoked, and the named current values, unit and effective-from included, are that revision's (`POLICY_UNKNOWN`, `ISSUER_MISMATCH`, `POLICY_STALE`, `POLICY_REVOKED`, `VALUE_MISMATCH`).

**I6-02.b** A `NARROW` is a narrowing only if every new value is no wider than the current one and at least one is narrower; anything else is refused as `NOT_A_NARROWING`, and its route is `ISSUE_STANDING_POLICY` (I6-03).
- **The ceiling:** no higher, in the same unit. Zero is a valid deny-all ceiling (`IF10-05`).
- **The expiry:** no later, and not before the decision's effective-from.
- **The enforcement:** only from `COOPERATIVE` to `MANDATORY_HARD`. Where no enforceable bound qualifies for the class, that holds its paid dispatches (`IF10-10`, `S01-14`). That is narrower.
- **Scope, provider, account and recipient** are not narrowed in place, because each is one value. Ending one of them is a `REVOKE`, then a new issuance for what remains.
- A `REVOKE` names no new values. A `REVOKE` with values, or a `NARROW` without any, is `invalid_request`: a Problem, with no receipt.

**I6-02.c** What it records: a revocation record, or a successor revision with the narrowed values; the predecessor stays immutable history (`O01-09`).

**I6-02.d** From the record on, every admission compares against the new state, and work already in flight is handled at its actual enforceable boundaries, never by claiming a remote effect stopped.
- **New admissions:** every paid admission or dispatch after the record compares against it. A preflight receipt from before it authorizes nothing (`IF10-17`, `R01-39`, `O01-13`).
- **Ongoing execution under a hard bound** is held to the new bound wherever the class can enforce it: before each admission, between effects, and in flight where the call is genuinely interruptible (`ADC-08.f`, `R01-09`).
- **A dispatched paid request that cannot be halted** completes. Its exposure stays accounted under its original operation and the policy revision that admitted it (`R01-07`, `IF10-15`, `IF10-16`), and it is never reported cancelled (`IF12-14`).
- **A revoked cooperative class** admits no new dispatch.
- **Nothing settled is reopened, and nothing encumbered is released** by the narrowing (`R01-10`).

**I6-02.e** It is admitted on the operator's consent alone, without being blocked by changes to irrelevant basis members, and reads no other owner's fact.
- It only reduces, so `AOI-07.f` applies: "A protective reduction shall use its governing current authority … without being blocked solely by agent-writable changes to irrelevant or newly enumerated basis members".
- The decision it acts on is the operator's own (P05's consent).

### `ISSUE_STANDING_POLICY` for a widening (P07)

**I6-03. A widening is A-24's `ISSUE_STANDING_POLICY`, issuing a successor revision of the same decision, with `predecessor` naming the decision's current revision; the issuer admits it under A-24's rules, unchanged.**
- **This is A-24's own binding read for a successor.** `O01-02` binds "relevant current policy predecessor", and `O01-09` makes the newer issuance the replacement. Round 1 confirmed the reading.
- **A widening races a narrowing safely.** A widening whose consent names a revision that a narrowing has since replaced is refused, because an action that is not `REDUCING` is admitted only at the exact predecessor its consent names (A-24 SW-09, item 1). `verify_i6.py` checks the race against A-24's own W0 oracle, and the issuance at the narrowing's revision as the control.
- **What the operator sees:** the new bounds, and the revision the widening replaces, but not that revision's values (I6-12). Showing them needs A-24's target to change, in a later wire (I6-B7).
- **Inherited mandatory bounds still apply:** at every admission, the stricter applicable parent bound governs (`IF10-05`, `R01-05`). A wider child revision never gives headroom above its parent. That is admission-time behaviour already adopted, not a refusal added to the issuance.
- **What it does not reach:** a limit that is not a standing policy. That covers wall time, concurrency, rate and quota (`R01-04` items b to d), and an original operation's attempt ceilings (`R01-31`). They have no adopted issuance, which is backlog I6-B1, carrying I-2's `I2-B4`.

### `ADOPT_MANIFEST_EDIT` (P14)

**I6-04. With the operator's consent, IF-13 records a successor revision of one profile definition that differs from its effective revision in exactly one typed setting, and requests that revision's transition.**

**The target names:** the installation; the definition and its effective revision; the setting's path, as the definition's schema types it; the operation, `SET`, `ADD` or `REMOVE` (the last two for a set-valued setting); the setting's effective value and its new value, each a scalar; the expected functional snapshot; and a reason reference.

**I6-04.a** IF-13 admits it only if:
- **the definition is its own, on that installation, and the named revision is its effective one** (`DEFINITION_UNKNOWN`, `INSTALLATION_MISMATCH`, `DEFINITION_STALE`). A recorded revision that never became effective is never the base of an edit;
- **no transition of the definition is unsettled:** requested, checking, applying, held or of unknown effect. Otherwise the edit is held as `TRANSITION_UNSETTLED`, and the consent is not used. So nothing recorded is carried into the edit unseen, and what takes effect is what this consent showed (`G3-03`, `G3-04`, `IF13-03`).
  - **Submitting the same set again** once the transition settles needs a new `client_request_key` (A-24 SW-07: the same key only looks up the original operations) and a consent that is still valid. The set digest leaves the key out, so the consent still binds. A consent lasts minutes (`G3-06`), so an edit held longer needs a new one: one more PIN (I6-R02).
  - **A revision whose transition failed** stays history, and the next edit starts from the effective revision again (`IF13-12`).
  - **A transition settles as IF-13 settles it** (`IF13-10`, `IF13-12`):
    - one of **unknown effect** settles only through IF-13's reconciliation;
    - a **held** one settles when it ends, or when IF-13's conditional compare supersedes it. Selecting an existing revision through `REQUEST_PROFILE_CHANGE` asks for that, but does not guarantee it, since one becomes effective at most.
    - Until it settles, the edit stays held, and D-01 shows which transition holds it (`IF13-15`). Edits then resume from the effective revision;
- **the path names a setting the schema types** (`SETTING_UNKNOWN`);
- **the named current value is the effective revision's** (`VALUE_MISMATCH`);
- **the new value meets the setting's type and constraints** (`VALUE_INVALID`);
- **the change changes something** (`NO_CHANGE`). An `ADD` names no current value and a `REMOVE` no new one, which the schema checks;
- **the snapshot is current** (`SNAPSHOT_STALE`), as `REQUEST_PROFILE_CHANGE`'s is.

**I6-04.b** The new revision allocates capabilities and never qualifies one: a change that would remove a gate an adopted contract requires, or admit a protected effect without its qualified gate, is refused as `LOWERS_ADOPTED_FLOOR` (`S01-03`, `S01-23`, `IF13-04`).
- **A functional lane may still be chosen.** A run outside a qualified protected-effect gate is functional only, its protected effects stay held, and it is labelled as such (`IF13-19`).

**I6-04.c** A setting is IF-13's only where the definition's schema types it as configuration; a change that would issue another owner's fact is refused as `NOT_A_SETTING` (`IF10-04`, `S01-14`).
- **Other owners' facts include:** a resource limit or paid class (the issuer's); a steering mode (R-01's, I6-06); a grant or its autonomy (ADC's); a control floor, gate or check (ADC's and AEV's); messaging registration (CNI's).
- **Each changes through its owner's own type.** Where none exists, it stays as adopted (backlog I6-B3).
- **AEW's containment lane is not a setting either.** It is the installation's containment mode (A-33 §3.1, `required`), changed only by the operator's own install configuration, outside O-01, so an edit naming it is `NOT_A_SETTING`.
  - That keeps a consented edit from changing what G3 rests on. G3 counts only while containment's launch self-test passes for every agent context (the pass of 2026-10-24).
  - So a lane edit can never hold the operator's protective commands.
  - Whether today's `allow_weaker` lane is kept is a flag for the as-built trace (Not covered).

**I6-04.d** What it records, as one IF-13 effect:
- **an immutable successor revision:** the effective revision plus this one change, with the consent, the reason, and the change's path, old value and new value;
- **a requested transition to it,** with a controller-issued transition identity (`IF13-11`). It follows `IF13-10` and `IF13-12`, as `REQUEST_PROFILE_CHANGE`'s does: `REQUESTED`, `CHECKING`, then `EFFECTIVE`, `HELD`, `FAILED`, `UNKNOWN_EFFECT` or `SUPERSEDED`.

**I6-04.e** `EFFECT_CONFIRMED` means that IF-13 recorded the revision and the requested transition, never that the revision is effective (`IF13-03`, `IF13-15`).

**I6-04.f** A file edited on disk is not a revision: nothing in it takes effect, and the governed path is this type's typed change (the catalogue: "mere file edit not governance").

### Model routes (P04)

**I6-05. A model route is chosen by `ADOPT_MANIFEST_EDIT` changing a route setting, and every consequence of the route is checked where it acts, at each dispatch, never at the selection.**
- **In flight:** an invocation created before the transition is `EFFECTIVE` keeps the route it was pinned to (`IF13-13`).
- **Disclosure:** every dispatch on the new route meets `IF12-08` for its exact provider, account and recipient. The selection releases no source to that recipient (`IF12-10`).
- **Paid class:** a dispatch is paid under a standing policy that names the route's provider and account (`IF10-04`, `S01-14`). A route that no current policy covers holds its paid dispatches, and the route setting is never that policy (I6-04.c).
- **No carry-over:** changing a route clears no recipient restriction, cap or credential separation (`IF13-17`).
- **No silent substitution:** a route that fails withholds its calls. Nothing falls back to another provider, account or model (`IF12-19`).

### `SET_STEERING_MODE` (P08)

**I6-06. With the operator's consent, R-01 sets the steering mode for one Lead generation to `CRAWL`, `WALK` or `RUN`, and the mode only ever decides whether an eligible action waits for its actor or is auto-run.**

**The target names:** the Lead generation; the new mode; the current mode and its record's version, which R-01 checks; and a reason reference.

**I6-06.a** R-01 admits it only if the generation is the subject project's current Lead generation, the mode record and its named current mode are at that version, and the mode changes (`PROJECT_MISMATCH`, `GENERATION_NOT_CURRENT`, `MODE_STALE`, `MODE_UNCHANGED`); HEB's seat fact unavailable is a hold (`LEAD_STATE_UNAVAILABLE`).

**I6-06.b** The modes, from fewest to most actions run without a confirmation:
- **`CRAWL`:** nothing is auto-run. Every eligible action waits for its actor to take it.
- **`WALK`:** an eligible action is auto-run only if every effect it declares is within AEW's own coordination records.
- **`RUN`:** every eligible action is auto-run.

So `RUN` differs from `WALK` only in which declared effects may be auto-run, and neither reaches an action that is not eligible.

**I6-06.c** An action is eligible for auto-run only if its competent governing rule makes it explicitly auto-runnable, it declares its effects there, and each is an effect this version knows (`R01-38`; R-01's R4, "already permitted automatic actions"). That rule is the admitting owner's, except for automatic recovery, whose class `R01-30` has declared by "competent governing policy/profile". The declaration also states which A-05 §5 automation row the action falls under, or that it falls under none (I6-10). It must also be the current Lead's own delegated action under its current grant, record no judgment, and be admitted now on its owner's own checks (R-DEC-04's eligible primitives).
- **Only the owner makes an action auto-runnable.** The mode, the Lead and a label never do. An action that is not auto-runnable, or declares no effect, waits in every mode.
- **No adopted rule yet makes any action auto-runnable,** so today every action waits in every mode. Each owner's declaration of its auto-runnable actions, with their effects, is backlog I6-B6.
- **Never eligible:** `CONTINUE_ELIGIBLE_WORK`, which A-24 SW-04 makes "deliberate selection, not implicit resumption", with "no auto-run on reattach".
- **Never eligible:** an operator-origin type, whatever the mode.
- **Never eligible:** an action that records a judgment, such as a classification, a finding's disposition, a scope or acceptance decision or an adjudication (`R01-17`, `R01-29`).
- **Never advanced:** a subject with an open decision, a blocker or an availability that is unknown (`R01-35`).

**I6-06.d** After each auto-run step, what it committed is checked against what it declared, and an excess stops auto-running and is surfaced for attention (R-DEC-04's side effects).

**I6-06.e** An action the mode does not auto-run waits for the current Lead to take it itself; the mode never makes the operator confirm a delegated action, and never turns one into an operator decision (R-DEC-04's confirming actor).

**I6-06.f** The mode cannot be bypassed (R-DEC-04's non-bypass):
- **it changes only through this type.** A configuration default is not a mode (I6-04.c), and no agent can set one;
- **the auto-runner runs outside every agent's reach.** It submits each step through the same admission path as the Lead's own call, attributed as auto-run;
- **no admission check reads the mode.** What is legal never depends on it (`R01-38`).

**I6-06.g** A mode change applies to auto-run decisions made after its record, and lapses to `CRAWL` when the named generation ends (I6-R01).
- **A new generation's record:** when HEB reports a new current Lead generation, R-01 records its mode at `CRAWL`, with a version R-01 issues. A raise for that generation names that version. Until the record exists, the generation runs at `CRAWL` and no raise can name it.
- An auto-run step already admitted completes under its own admission.
- At each step, a newer mode record forces a fresh comparison (`R01-39`).

**Candidate:** the supervisor-side loop AEW has built (`work/AS-BUILT-READ.md`, P08), with its per-activation deadline, action count and repetition bound, each a tripwire a deployment may only shorten. Its bookkeeping allow-list decides eligibility in code, with no adopted declaration, so it is a flag for the as-built trace, not a candidate for I6-06.c.

### `REQUEST_CHARGE_RECONCILIATION` (P10)

**I6-07. With the operator's consent, R-01 records a request to reconcile one original operation's unknown or unpriced exposure, and settles or releases nothing except on qualified provider evidence or R-01's own competent closure.**

**The target names:** the original operation, as the admission owner derived it (`IF10-07`); R-01's exposure record and its version; the provider and account; a locator for provider evidence, or `null`; and a reason reference.

**I6-07.a** R-01 admits it only if the operation is its own and of the subject's project, the exposure is at that version and still unknown or unpriced, and the provider and account are the operation's (`OPERATION_UNKNOWN`, `PROJECT_MISMATCH`, `EXPOSURE_STALE`, `NOTHING_TO_RECONCILE`, `PROVIDER_MISMATCH`).

**I6-07.b** What it records is the request; the outcome is R-01's later observation of that operation, and follows `IF10-14`'s states.
- **`RECONCILED`, or `SETTLED_QUALIFIED`,** only on comparable complete provider and account evidence that R-01 obtains and checks itself, outside the metered lineage (`IF10-13`, `IF10-15`).
- **`RELEASED_QUALIFIED`** also on R-01's own competent closure, where no comparable evidence exists: an expressly bounded expiry that safely accounts for residual work and charges (`IF10-15`'s "another competent justified closure", `R01-10`). R-01 makes that closure. The operator's request may lead to one, but never stands in for it.
- **Otherwise the exposure stays as it was,** encumbered, with what evidence is missing (`R01-08`, `R01-10`).
- **The locator is a pointer, never evidence.** R-01 fetches and qualifies what it points at, or ignores it.
- **Late and corrected bills keep their history** (`IF10-16`).

**I6-07.c** It never dispatches again, and never settles on the operator's word.
- **No second dispatch:** reconciliation never resends the call (`IF12-13`).
- **No settlement by the operator:** a reconciliation is not a settlement (the catalogue: "not another dispatch or manual force-settled").
- **What a widening clears, and what it does not:**
  - **It clears a bounded unknown under a standing-policy limit.** A successor issuance (I6-03) adds headroom above the worst-case encumbrance `R01-09` requires.
  - **It does not clear an unknown that cannot be conservatively bounded, against a hard limit.** `R01-05`: that "precludes a positive admission against that affected hard limit", whatever the ceiling.
  - **It does not clear an original operation's own ceilings** (`R01-31`), which have no issuance (I6-B1).
  - **Each of those waits for R-01:** for qualified evidence or R-01's own competent closure, above, and for the ceilings' issuance in I6-B1.

**I6-07.d** On a host with no qualified resource-control writer it is held as `RESOURCE_WRITER_NOT_QUALIFIED`, and records nothing positive (`R01-43`).

**I6-07.e** `EFFECT_CONFIRMED` means R-01 recorded the request, never that anything was reconciled. The outcome is read as a later owner observation.

### Host profiles (P11, P12)

**I6-08. With the operator's consent, IF-13 invalidates every capability assessment of one host profile at one installation, and records the revocation under an identity of its own.**

**The target names:** the installation; the host profile; the version of its current set of assessments, which IF-13 checks; and a reason reference.

**I6-08.a** IF-13 admits it only if the installation is the subject's, the profile is one it records there, its assessments are at that version, and at least one is qualified (`INSTALLATION_MISMATCH`, `PROFILE_UNKNOWN`, `QUALIFICATION_STALE`, `NOTHING_QUALIFIED`).

**I6-08.b** What follows from the record:
- **every assessment it names reads as `STALE` or `NOT_ESTABLISHED`** (`IF13-08`, `IF13-14`);
- **every dependent protected effect is held at its next effect.** HEB and ADC re-evaluate at each consequential effect (`IF13-09`). Running work is not stopped by this: stopping it is the operator's other means;
- **functional work that depends on no revoked assessment continues** (`IF13-19`);
- **only an assessor's record that names this revocation, and rests on evidence gathered after the assessor read it, qualifies the profile again** (`IF13-07`, `IF13-14`). Until one exists, the revocation stands.
  - **What "newer" means:** the record names the revocation it follows, never an arrival order or a timestamp (I6-01b; IF-13 §3).
  - **So an assessment in flight does not undo it.** One built on evidence observed before the revocation qualifies nothing, whenever it lands, and after a second revocation a record naming the first qualifies nothing either. Neither counts as qualified for I6-08.a.
  - An operator's word never qualifies.

**I6-08.c** It only reduces, so it is admitted on the operator's consent alone, as `NARROW_OR_REVOKE_STANDING_POLICY` is (`AOI-07.f`).

**I6-08.d** It reaches IF-13's capability assessments only. G3 is established by its own install and containment's launch self-test (the pass of 2026-10-24, which cut `G3-12`'s record), never by an IF-13 assessment. So after a host revocation the operator's protected commands keep their G3 origin, including the protective ones: `NARROW_OR_REVOKE_STANDING_POLICY`, `SUSPEND_GRANT` and `STOP_CHILD_NOW`. This type never withdraws G3.

**I6-09. Qualifying a host profile, and moving a project to another installation, are not O-01 commands.**
- **A qualification is the assessor's record,** by the gate of the capability it qualifies (`S01-09`, `S01-18`, `S01-30`). An assessor is not an operator command channel, and an operator's label is not a qualification (`IF13-07`).
- **P11's profile half** is `REQUEST_PROFILE_CHANGE` naming the new installation, once the host's own install has made it. The install happens outside O-01.
- **Moving a project's state, records and credentials** to the new installation is U-01's (`IF13-17`), so it waits for U-01 (I6-B2).

### Activation, sets and refusals

**I6-10. A type is held only for the effect that an unadopted A-05 §5 row is "Required before"; none of I-6's types is such an effect in itself.**
- **The two `REDUCING` types are never held.** A-05 §5's preservation rule keeps protective controls effective.
- **`ADOPT_MANIFEST_EDIT`** records a revision and requests a transition. What the revision enables is gated where it acts (`IF13-04`, `IF13-09`, I6-05).
- **`SET_STEERING_MODE`** grants nothing, and its type is held by no row. **But an auto-run step is automation,** so A-05 §5's rows whose "Required before" is automation reach it, where they do not reach the Lead's own deliberate call to the same action (as A-34 read the stop row, `I2-PROFILE.md`: the operator's consent is not automation, and a Lead's decision is deliberate).
  - **While the row "Automated consequential stop, release and recovery" is unadopted,** an auto-run step that is a consequential stop, release or recovery is held: it is not auto-run, and waits for the Lead to take it itself.
  - **While the row "Automatic unrelated maintenance" is unadopted,** an auto-run step of maintenance unrelated to the work is held the same way.
  - **A step whose declaration does not state its row** is held while either row is unadopted (A-05's undefined-parameter rule: nothing obtains permission because a contract is incomplete). The declaration states it (I6-06.c).
  - **This applies in every mode,** to an action that is otherwise eligible (I6-06.c). Raising the mode activates nothing beyond what these rows allow.
- **`REQUEST_CHARGE_RECONCILIATION`** is held by `R01-43` where no qualified writer exists (I6-07.d), not by A-05 §5.
- **No I-6 type binds content the operator must read beyond its own leaves.** Each target names the current values it acts on, and its owner refuses a mismatch, so `I5-08a` holds none of them.

**I6-11. Sets, ordering and refusals follow the adopted path, with one rule for subjects named twice.**
- **One admission path,** as `I4-11` and `I2-11`: origin, then owner state, then the activation hold, then at most one owner effect per member.
- **One member per subject.** A set with two members acting on the same policy decision (`NARROW_OR_REVOKE_STANDING_POLICY` or `ISSUE_STANDING_POLICY`), the same profile definition (`ADOPT_MANIFEST_EDIT` or `REQUEST_PROFILE_CHANGE`), the same Lead generation's mode, or the same host profile is `invalid_request`, before any owner state is read. The outcome then never depends on canonical order.
- **Each change is compare-and-set** on its subject's version, so it happens once.
- **Unavailable state:** the admitting owner's own state is `UNKNOWN_OWNER_STATE`, and another owner's fact is a hold under its own reason: `LEAD_STATE_UNAVAILABLE` for HEB's seat fact, which `SET_STEERING_MODE` reads.
- **Each owner reason maps to an adopted reason code,** in `wire/refusal-reasons-0.8.json`. The map is complete and fails closed. No I-6 reason maps to `UNRESOLVED_NO_REDISPATCH`, which is only for a missing, corrupt or expired ledger entry (A-24 SW-07).

**I6-12. What the operator sees is A-26's consent, unchanged, and each new type renders within the 30 lines G3 allows a member.**
- `verify_i6.py` derives each member's line count from the wire, as `verify_i2.py` does.
- Every target is a closed object with scalar leaves, so G3 can render all of it (`G3-03`).
- The current values in each new target are part of its rendering, so the consent shows the change from and to. The largest, `NARROW_OR_REVOKE_STANDING_POLICY` with its unit and effective-from, renders in 29 lines.
- **For a widening the display is weaker:** A-24's `ISSUE_STANDING_POLICY` target carries the new bounds and names the predecessor revision, but not its values, so the operator sees what it widens to and which revision it replaces, not what from (I6-03, I6-B7).

## Interfaces

**The wire:** `o01-command-0.8-candidate`, generated by `tools/build_o01_wire.py` from A-34's frozen `30-stages/STG-10-I2-heb-child-execution-control/adopted/o01-0.7-i2/wire/`, pinned by its `SHA256SUMS`, and from this stage's `I6-WIRE-SPEC.json`, which `tools/o01-wire-spec.schema.json` checks.
- **The schema:** A-34's, byte-equal in every inherited definition except the two owner enums (I6-00a). It adds five Intent branches and five Target definitions: 42 actions. All five branches are protected and require a `null` seat.
- **`openapi-o01-0.8.yaml`:** the same definitions, checked equal by the generator.
- **`action-registry-0.8.json`:** A-34's 37 rows unchanged, plus five. Two of them are `REDUCING`.
- **`refusal-reasons-0.8.json`:** A-34's map, plus the five types' owner reasons.
- **`PREDECESSOR-PINS.json` and `SHA256SUMS`.** `--check` regenerates and compares. The generator is shared: rebuilt from I-2's spec, it reproduces A-34's 0.7 byte-equal.

**What a D-01 change must add,** for the operator to see what these types act on:
- the standing policies, each decision's current revision and its revocation state;
- each profile definition's revisions, and each transition's state per route (`IF13-12`, `IF13-15`);
- the steering mode, its generation and its record;
- each original operation's exposure and its reconciliation state (`IF10-14`; P09's read is partial);
- each host profile's assessments and their revocation. P03's capability read (A-25) is the place.

## Scenarios

**I6-X01.** Given a mandatory hard policy of 20 units with 12 encumbered, and a dispatched request that cannot be halted, a narrowing to 10 refuses every later paid admission, while the dispatched request completes and is accounted under its original operation and revision, and is never reported cancelled (I6-02.d).

**I6-X02.** Given an invocation running on route A, an `ADOPT_MANIFEST_EDIT` to route B leaves it on A, and the next invocation dispatches on B only once the transition is `EFFECTIVE` and its recipient and paid class pass at that dispatch (I6-05).

**I6-X03.** Given an edit that sets a spending ceiling in the profile definition, IF-13 refuses it as `NOT_A_SETTING`, and the ceiling's route is the issuer's (I6-04.c).

**I6-X04.** Given `RUN` set for Lead generation 5, a takeover that makes generation 6 starts at `CRAWL`, and only a new consent naming generation 6 raises it (I6-06.g).

**I6-X05.** Given a reconciliation request whose locator points at a file the Lead wrote, R-01 lowers no exposure, and the exposure stays unknown with its missing evidence named (I6-07.b).

**I6-X06.** Given a protected run on a host whose qualification the operator revokes, its next protected effect is held, functional work that depends on no revoked assessment continues, and only a newer assessor record qualifies the host again (I6-08.b).

**I6-X07.** Given a set holding a narrowing and an issuance for the same policy decision, the set is `invalid_request`, and nothing is read or changed (I6-11).

**I6-X08.** Given `RUN` for the current generation, and a delegated action that no owner's adopted rule makes auto-runnable, the action waits for the Lead; given one that is auto-runnable and is a consequential recovery, it waits too, while A-05 §5's automation row is unadopted (I6-06.c, I6-10).

**I6-X09.** Given a route edit whose transition `FAILED`, an effort edit named on the effective revision records a revision that changes only the effort, and the failed route change never takes effect (I6-04.a).

**I6-X10.** Given a host revocation, an assessment built on evidence from before it that lands afterwards qualifies nothing, and the operator's protected commands still carry their G3 origin (I6-08.b, I6-08.d).

## Rulings

**I6-R01.** A steering mode is bound to the Lead generation its consent names, and lapses to `CRAWL` when that generation ends. The consent was given for the generation the operator saw, and a new one may be another model, harness or actor.

**I6-R02.** A manifest edit is one typed setting per member. G3 shows exact leaf values and no prose (`G3-03`), and a set cannot chain revisions, so a several-setting edit is several consents until backlog I6-B4 settles a bounded form. The cost is more than the consents:
- **Each edit requests its own transition,** and the next waits until that one settles (I6-04.a). So the operator orders the edits so that each intermediate revision is one they are content to run.
- **Each consent is a PIN,** against STG-13's per-scenario PIN budget (F1). An edit held past its consent's life needs a new consent, so one more PIN (I6-04.a).
- **A model switch (V-01's V4) costs, by case:**
  - **one PIN** where the target route is already in the definition's inventory, a current standing policy covers its provider and account, and its recipient has a release (I6-05);
  - **one more** for each `ISSUE_STANDING_POLICY` the provider needs;
  - **one more per further edit** for a route not yet in the inventory, each waiting for the last edit's transition.

  STG-13's path names which case V4 runs, and its budget is derived from that.

**I6-R03.** An unknown charge is never settled by the operator's word. The operator can ask R-01 to reconcile it, which ends in qualified evidence or R-01's own competent closure (I6-07.b). Or the operator can widen the limit, which is an explicit authority increase, recorded as one. A widening helps only where the unknown is bounded and the limit is a standing policy (I6-07.c).

**I6-R04.** Qualifying a host is not an O-01 command; revoking one is. An outside-lineage record qualifies, and the operator's protective withdrawal only reduces.

## Backlog

**I6-B1.** Limits that are not standing policies: wall time, concurrency, rate and quota (`R01-04`), and an original operation's attempt ceilings and their headroom (`R01-31`, I-2's `I2-B4`). They need an adopted issuance: a new type, or a wider standing-policy target in a later wire. Until then, P10's remedy for an unknown charge against those ceilings is R-01's own (I6-07.c).

**I6-B2.** U-01: upgrading or rolling back AEW (U10), and moving a project's state, records and credentials to another installation (P11's migration half). Both wait for U-01's contract.

**I6-B3.** An adoption path for configuration that other owners govern: ADC's classification policy and floors, AEV's checks, R-01's limits, CNI's messaging. Until each has its owner's path, it stays as adopted, and the operator can neither loosen nor tighten it through configuration. **No remaining increment carries this:** I-7 is RX-01, K-01 and P-01. Whether it gets one is the operator's to decide at adoption.

**I6-B4.** A manifest edit of several settings in one consent. G3's per-member bound allows two: an edit renders in 25 lines, and each further path, operation and value pair adds 4.

**I6-B5.** The operator's request that a host assessor run a qualification (P12's qualifying half, as a trigger rather than a decision).

**I6-B6.** Each owner's declaration of which of its actions are explicitly auto-runnable, with the effects each declares and the A-05 §5 automation row each falls under, or none (`R01-38`; I6-10). Automatic recovery is declared by `R01-30`'s competent governing policy or profile. Until a declaration is adopted, the steering mode reaches none of those actions (I6-06.c).

**I6-B7.** A widening's consent that shows the predecessor revision's values. That needs A-24's `ISSUE_STANDING_POLICY` target to change, in a later wire (I6-12).

## Not covered

- **The as-built trace's flags in I-6's areas, pending their discussion in STG-12,** under the start decision (`work/AS-BUILT-READ.md`). They include:
  - the Lead's per-dispatch model override;
  - the Lead's own steering lowering;
  - the auto-run bounds, and the bookkeeping allow-list that decides auto-run eligibility in code with no adopted declaration (I6-06.c);
  - the breadth and side effects of today's manifest adoption, including its `allow_weaker` containment lane (I6-04.c).

  A flag that ends "keep it, with a requirement", where the requirement belongs here, goes into this profile's next revision before adoption.
- **D-01 changes:** the reads listed under Interfaces.
- **A-34's 37 actions,** which are unchanged.
- **Building I-6.** The protected types stay held wherever G3 is not established (A-26).
- **Candidate mechanisms are not claimed:** the issuer's records, IF-13's revision store and controller, R-01's mode record and reconciler, and the auto-runner.

## Changes

- Revision 1 (2026-10-24): the first text.
- Revision 2 (2026-10-24): answers round 1's twelve findings, each in `CHANGES-r2.md`. The steering mode reaches only what an owner declares auto-runnable, and an auto-run step meets A-05 §5's automation rows. An edit starts from the effective revision. A re-qualification names the revocation it follows, and a host revocation leaves G3's own qualification alone. R-01's own closure is restored. The P14 and P07 departures are restated, and backlog items I6-B6 and I6-B7 are added.
- Revision 3 (2026-10-24): answers round 2's eight findings (`CHANGES-r3.md`), under the security depth reset: round 2 was the last full round, and one quick check follows.
  - A declaration states its A-05 §5 row, and a step whose row is unstated is held.
  - The containment lane is the installation's, not a setting.
  - A transition settles as IF-13 settles it.
  - V-01's configure step and V4's PIN cases are placed.
  - G3 is established by its install and containment's self-test.
