<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-30
source: 30-stages/STG-08-I3-adc-authority-and-grants/adopted/o01-0.5-i3/I3-PROFILE.md
source-sha256: 8cd78123a1063cd6ed4ca79ded32a16a7e36f592fb2087732109e26b7c24176e
edits-sha256: none
-->

# I-3: ADC authority and grants, selection profile (PROPOSED contract pass, revision 2.2, 2026-10-22)

**Wire:** O-01 `o01-command-0.5-candidate`, in `wire/`. It is A-29's 0.4 wire plus six action types, generated from A-29's frozen bytes by `tools/build_i3_wire.py`.
**Stage:** `STAGE.md`. **Start:** `00-governance/decisions/2026-10-22-operator-start-I-3.md`.
**How to read it:** as I-1's and I-5's profiles. Each rule states an outcome: what must hold, who owns it, what is refused, and the adopted rule it must not contradict. Text marked **Candidate** is a starting point for the build, which may meet the outcome another way.
**Rule names:**
- `ADC-02.f` and the like are A-05's guarantees.
- `I1-05` and `I5-03` are the adopted I-1 (A-28) and I-5 (A-29) profiles.

## I3-00. The fit: which rows need a new O-01 type

| Row | Catalogue symbol | Kind letters | Fit | Reason |
|---|---|---|---|---|
| W07 | `DECIDE_DISCRETIONARY_REVIEW` | D | **New type, delegated, owner AEV** (I3-02) | Its owner text: "Delegated Lead if within authority; rationale retained, mandatory defect cannot be waved away". The fact that changes is a finding's disposition, which is AEV's (AEV-10.a, AEV-10.c). The finding's class, mandatory or discretionary, is AEV's too (AEV-01.b, ADC-07.g). ADC's part is whether the Lead acts within its delegated authority (ADC-07.a), and AEV reads that as ADC's grant fact. This is I-5's split (I5-01): the fact's owner admits it, and reads the authority owner's fact. |
| W10 | `DELEGATE_NEW_WORKER` | D | **New type, delegated, owner ADC** (I3-03) | Its owner text: "Authorized Lead/ADC coordinator; worker cannot spawn independent grant". It records a derived grant (ADC-02.a, ADC-02.b, ADC-04.d). No existing type issues a grant. |
| A01 | `REVOKE_LINEAGE` | O | **New type, protected, owner ADC, the only `REDUCING` one** (I3-04) | It is not `SUSPEND_GRANT` with `STABLE_ROOT_DESCENDANTS`. A revocation is final, with no lift. It denies descendants new protected effects (ADC-02.f), ends custodian grants derived only from it (ADC-02.j), and lets A04 reaffirm nothing. A suspension is lifted by `LIFT_OPERATOR_SUSPENSION`. |
| A05 | `ADJUST_LEAD_AUTONOMY` | O | **New type, protected, owner ADC** (I3-05) | Its owner text: "ADC operator-approved grant/policy future effects, not retroactive review waivers". It sets new values for the Lead grant's closed autonomy parameters. `ISSUE_STANDING_POLICY` is the resource policy issuer's, and covers no ADC grant. |
| A06 | `OVERRIDE_RISK_FLOOR` | O/Q | **New type, protected, owner ADC** (I3-06) | Its owner text: "Governing adopted authority/ADC; cannot casually waive mandatory independent verification". **The operator's consent alone is not enough** to lower a mandatory control. ADC must also qualify an independent assessment (ADC-06.c, ADC-06.j, ADC-05.h). That is the Q letter. |
| A09 | `AUTHORIZE_EXTERNAL_EFFECT` | O/Q | **New type, protected, owner ADC** (I3-07) | Its owner text: "Original domain effect owner with exact consent, source recipient and ADC/HEB authority; not blanket tool whitelist". It authorizes one exact effect, single use. HEB admits the effect at its own boundary (HEB-04.g). |

**All six rows need a new type.** The classification's figures stand: six command rows in I-3.

**I3-00a. The one change to inherited definitions: the closed owner enums gain `AEV`.** This is the same additive change as I5-00a, at the same four sites: `Intent.owner_hint`, `IntentResult.owner`, the receipt's result `owner` and `OwnerOperationRead.owner`.
- D-01 already names AEV as a governing owner (`SourceStamp`).
- Under rule 2's exact version marker, a 0.4 consumer never meets the new value.

**The protection direction is set per type, by I5-00's rule** (a type with both directions takes the one that gates harder):
- `REVOKE_LINEAGE` only reduces, so it is `REDUCING`.
- The other five are `PRESERVING_OR_INCREASING`. `ADJUST_LEAD_AUTONOMY` and `OVERRIDE_RISK_FLOOR` can widen, and a decision on a finding can decline it.

## I3-01. Who owns what

| Type | Records the fact (sole admitting owner) | Whose decision the origin carries | Read only, as an input |
|---|---|---|---|
| `DECIDE_DISCRETIONARY_REVIEW` | **AEV:** the finding's disposition, with its rationale | the Lead's, within its delegated authority (ADC-07.a) | AEV's own class of the finding. ADC: the Lead's current grant. HEB: the principal is the seat's current Lead |
| `DELEGATE_NEW_WORKER` | **ADC:** the derived grant | the Lead's (ADC-02.b) | HEB: the current Lead. WIS: the work's current accepted revision. The resource policy issuer: the hard limits (ADC-08.f) |
| `REVOKE_LINEAGE` | **ADC:** the revocation, and, for a Lead's root grant, the trust-revocation classification of its generation | the operator's | none |
| `ADJUST_LEAD_AUTONOMY` | **ADC:** the Lead grant's new version | the operator's | none |
| `OVERRIDE_RISK_FLOOR` | **ADC:** the override, with the floor before and after | for a `LOWER`, the competent authority's for the work's project boundary: the operator's, as ADC's competent authority, or an external authority's decision that ADC qualifies (ADC-01.a, in I5-01's form). Qualified by an independent assessment when a mandatory control is lowered. A `RAISE` is the operator's (ADC-06.a) | ADC's own competence fact, floor computation and the assessment's qualification. WIS: the work's revision and project |
| `AUTHORIZE_EXTERNAL_EFFECT` | **ADC:** a single-use authorization of one exact effect | the competent authority's for the work's project boundary, as for `OVERRIDE_RISK_FLOOR`: for an external boundary, the original domain effect owner's (A09's text) | ADC: its own competence fact, and the grant the effect runs under. WIS: the work's revision and project |

**Competence (I3R1-1).** A06 and A09 act on a work's project boundary, so ADC reads its own competence fact for **the work's own project**, never the request's `subject.project_ref` (`PROJECT_MISMATCH`), exactly as A-29's I5-01 and I5-03 do.
- Where the fact names the operator, the operator's consent decides and the target cites no external decision (`AUTHORITY_DECISION_INVALID` if it does).
- Where it names an external authority, the operator's consent alone is `AUTHORITY_NOT_COMPETENT`. The target must cite that authority's decision, qualified by ADC, for exactly this change or effect (`AUTHORITY_DECISION_INVALID`).
- No competence record is a hold (`COMPETENCE_UNAVAILABLE`), consuming no consent.
- **An external decision is spent** with the override or authorization it qualifies, atomically (I3C2-2). A second use is `AUTHORITY_DECISION_INVALID`: a new override or effect needs a new decision.
- **A06 reads competence for a `LOWER` only** (I3C2-3). A `RAISE`, which by I3-06 keeps every mandatory control (I3C21-1), adds protection and adopts or amends none of an external authority's requirements (ADC-01.b, ADC-06.a), so the operator's consent decides it. Its target cites no external decision (`AUTHORITY_DECISION_INVALID` if it does).
- **A09's "original domain effect owner" is the work's project authority** (I3C2-4). A destination that another party owns is a matter for that destination's own control, at HEB's effect boundary (HEB-04.g); the consent renders `destination_ref`. If an owner later states a competence fact for a destination's boundary (A-29's "finer boundaries later"), ADC reads it too. That is backlog I3C2-B1.
- **A01 and A05 do not read competence.** A revocation only reduces, and ADC-08.d gives the responsible authority an effective means to revoke. An autonomy adjustment acts on the Lead grant that the operator's own consent established (A-25 L02 and L03). Neither target names a work.

**Consequences belong to their own owners, and are never this operation's effect:**
- **HEB:** launching a worker under the enforced launch profile (ADC-04.m, ADC-04.n); stopping or containing a revoked lineage's descendants (HEB-07.j); and admitting, at its effect boundary, the one effect an authorization names (HEB-04.g).
- **AEV:** reassessing a finding when the package changes (AEV-10.c).

## I3-02. `DECIDE_DISCRETIONARY_REVIEW` (W07), a delegated row, owner AEV

**Outcome:** the Lead records how it disposes of a discretionary review finding: `ADDRESS`, `DEFER` or `DECLINE`, with its rationale (ADC-07.a, ADC-07.b, AEV-10.c).

**Origin:** I1-01's class, `CURRENT_SUCCESSOR_GENERATION`: CS-07's authenticated session, with both proof slots `null`, decided before any owner state is read. The subject names the Lead's seat. AEV reads HEB's fact that the principal is that generation's Lead, as I5-02 does. The results are `ACTOR_NOT_CURRENT_LEAD` or `GENERATION_FENCED`, or a hold when the fact is unavailable.

**The target names:**
- the finding and its version;
- the assessed package the finding is about;
- the disposition;
- the rationale's SHA-256;
- the work and its accepted revision;
- the Lead's grant.

**AEV admits it only if:**
- **the finding is AEV's, at that version, and about that package** (`FINDING_UNKNOWN`, `FINDING_STALE`, `PACKAGE_MISMATCH`);
- **AEV's current class of the finding is discretionary.** A mandatory finding is `MANDATORY_FINDING`, and no disposition is recorded: a Lead's disagreement never turns a mandatory finding into a PASS (ADC-07.c). Its dispute path is W06, in I-4. An unknown class is a hold (`FINDING_CLASS_UNAVAILABLE`), never read as discretionary (ADC-05.c);
- **ADC's grant fact shows the Lead acting within its delegated authority** (ADC-07.a). The grant is the Lead's own: a Lead grant of this generation, held by the session principal (I3R1-8). It names this exact work and revision, and is neither revoked, suspended, ended nor expired. Otherwise the result is `GRANT_NOT_COVERING` or `GRANT_NOT_CURRENT`, or a hold when ADC's fact is unavailable;
- **the rationale is held under its digest** (otherwise it holds: `CONTENT_UNAVAILABLE`).

**What it records:**
- the disposition, attributed to the generation, with the rationale's digest;
- **the reviewer can read the rationale** (ADC-07.b);
- the finding's new version, so a second disposition of the old version is `FINDING_STALE`.

**What it never does:**
- **`DECLINE` and `DEFER` pass nothing.** No check passes and no hold clears.
- **`ADDRESS` records an intent only.** The fix arrives as a later package.
- **A disposition does not carry to a changed package.** AEV reassesses whether it still applies (AEV-10.c, WIS-04.d).

## I3-03. `DELEGATE_NEW_WORKER` (W10), a delegated row, owner ADC

**Outcome:** the Lead has ADC record a derived grant for a new worker, within the Lead's own grant (ADC-02.a, ADC-02.b, ADC-04.d).

**Origin:** as I3-02. **The actor is always the Lead's session principal.** A worker's session is never the Lead of the seat, so a worker cannot delegate (ADC-04.b): its request is `ACTOR_NOT_CURRENT_LEAD`.

**The target names:**
- the parent grant and its version;
- the work and its accepted revision;
- the worker's role, one of `IMPLEMENTER`, `INVESTIGATOR`, `ADVISOR` or `DIAGNOSTIC`. An independent reviewer or adjudicator is never delegated by the Lead: they are chosen by a preauthorized rule that excludes the Lead's lineage (ADC-07.h, ADC-06.j). **An `ADVISOR` or `INVESTIGATOR` grant permits no protected or source-mutating effect** (A-05 §2.2), and ADC's grant fact records that (I3C2-1). So it backs no external effect (I3-07);
- the derived scope's digest, and its constraints' digest, in A-25's `sha256:` form, as A04's child carries them;
- the launch profile binding;
- the grant's finite expiry.

**ADC admits it only if:**
- **the parent is the current Lead generation's own grant.** It must not be a derived grant (`PARENT_NOT_LEAD_GRANT`, ADC-04.b). It must be at the named version, and neither revoked, suspended nor expired (`PARENT_GRANT_STALE`, `PARENT_GRANT_NOT_CURRENT`);
- **the Lead grant's autonomy allows delegation** (I3-05; `DELEGATION_NOT_PERMITTED`);
- **WIS's current accepted revision of the work is the one named** (`WORK_REVISION_STALE`, ADC-02.d). A proposal with no accepted revision cannot be delegated;
- **ADC determines the derived scope is within the parent's** (`SCOPE_EXCEEDS_PARENT`, ADC-02.b). **Candidate:** ADC holds both scopes by digest;
- **the allocation fits the hard limits** the resource policy issuer states (`RESOURCE_LIMIT_EXCEEDED`, ADC-08.f), or it holds when they are unavailable;
- **the expiry is finite and no later than the parent's** (`VALIDITY_INVALID`).

**What it records:** one derived grant, with:
- its own identity and version;
- the parent;
- the holder (the worker, as ADC names it);
- the Lead's generation;
- the work and accepted revision;
- the scope and constraints digests;
- the role;
- the profile binding;
- the expiry.

**These are the fields A-25's `REAFFIRM_ELIGIBLE_CHILD_GRANTS` names**, so a routine successor can reaffirm the grant (ADC-02.i).

**What it never does:**
- **it launches nothing.** HEB launches the worker, under the enforced launch profile and workspace isolation (ADC-04.m, ADC-04.n);
- **it gives the worker no right to delegate** (ADC-04.b), and no autonomy of its own (I3-05);
- **it grants nothing beyond the parent** (ADC-02.b, ADC-02.c).

## I3-04. `REVOKE_LINEAGE` (A01), protected, owner ADC, `REDUCING`

**Outcome:** with the operator's consent, ADC revokes a grant and its whole lineage, finally (ADC-02.f, ADC-02.j, ADC-08.d).

**The target names:** the grant, its version, and a reason reference.

**ADC admits it only if:** the grant exists at that version (`GRANT_UNKNOWN`, `GRANT_STALE`), and is not already revoked (`ALREADY_REVOKED`).
- **A suspended grant can be revoked:** revocation is more protective.
- **An ended grant can be revoked** (I3R1-2): an earlier generation's root grant, after a routine transition. A compromise found later is still a trust revocation, never a routine handover (A-05 §2.2).

**What it records, in one step:**
- the grant is revoked, finally;
- **every grant derived from it, transitively, is revoked** for new protected effects (ADC-02.f). That includes custodian grants issued only under it (ADC-02.j);
- **every grant A04 reaffirmed from that lineage is revoked too, transitively, with its own descendants** (I3R1-2).
  - A reaffirmation is not "an independently current governing authorization" (ADC-02.f's exception). A04 names the prior grant, and its eligibility rested on the `ROUTINE` classification this revocation replaces.
  - A-05 §2.2 forbids treating a compromised revocation as a routine handover;
- **any other grant is untouched,** whoever holds it. "Independently authorized exceptions" survive by lineage, not by a list in the target;
- **for a Lead generation's root grant, ADC records that generation's transition as `TRUST_REVOCATION`**, the issuing authority's decision (ADC-02.l). That classification is the newest, so:
  - an open handover offer can no longer be claimed (I1-05's claim needs it `ROUTINE`);
  - A04 reaffirms nothing (ADC-02.f);
  - HEB applies HEB-07.j to the descendants (I1-06);
  - **ADC ends that generation's pending in-scope determinations, in the same step** (I3-08, I3R1-3).

**What it never does:**
- **no lift restores it.** A revocation is its own ADC record. `LIFT_OPERATOR_SUSPENSION` removes only a suspension, and ADC-08.c denies effects from a revoked grant whatever its suspension state;
- **no later action re-grants a revoked grant.** New authority is a new grant (ADC-02.k);
- **it does not itself claim that every running effect has stopped.** `EFFECT_CONFIRMED` means ADC has recorded the revocation. Stopping and containing the lineage's running work is HEB's (HEB-07.j), and so is the claim that it is effective, which A-05 §5 makes depend on the minimum mediated effect channels (I3-09).

## I3-05. `ADJUST_LEAD_AUTONOMY` (A05), protected, owner ADC

**Outcome:** with the operator's consent, ADC records a new version of the Lead's grant with new values for its closed autonomy parameters. The new values apply to future effects only (A05's text).

**The parameters, each a closed value the confirmer renders in full:**
- `incidental_maintenance`: `NONE` or `NONBEHAVIORAL_LOCALIZED` (ADC-03.i, ADC-03.k);
- `in_scope_approach_change`: `NOTIFY` or `ASK_FIRST`. ADC-03.g makes notice the default; `ASK_FIRST` is the operator's stricter choice;
- `helper_delegation`: `NONE` or `WITHIN_GRANT` (I3-03).

**Each starts at `NONE`, `NOTIFY` and `WITHIN_GRANT` respectively:** the values ADC's Lead grant carries until the operator adjusts it (I3R1-5). So only `NONBEHAVIORAL_LOCALIZED` is above its start.

**The target names** the Lead's grant, its expected version, and the three values.

**ADC admits it only if:** the grant is a Lead grant (`NOT_LEAD_GRANT`), at that version (`GRANT_STALE`), and neither revoked nor expired (`GRANT_NOT_CURRENT`). A suspended grant may be adjusted; the new values act only after a lift. ADC needs no other owner's fact for this: an earlier generation's Lead grant ends with its transition (I-1).

**What it records:** a new version of the grant. Then:
- **Nothing already recorded changes:** dispositions, findings, floors, derived grants and accepted work all stay as they are. This is "not retroactive review waivers".
- **No parameter can lower a mandatory floor or waive a review.** Those are I3-06's, and AEV's.
- **A value above its start affects active work only after ADC reassesses that work** (ADC-02.d).
- **Any other value applies at once,** to new effects: a narrowing, or a return to the start. ADC-03.g keeps notice from becoming "an unnecessary approval gate".
- **A derived grant has no autonomy of its own** (I3R1-4). Its effective values are always its parent Lead grant's current ones (ADC-02.b). So a narrowing reaches every worker at once, and a worker never keeps a wider value.
- **Narrowing `helper_delegation` to `NONE` refuses new delegations.** It does not end existing derived grants; ending them is `SUSPEND_GRANT` or I3-04.

## I3-06. `OVERRIDE_RISK_FLOOR` (A06), protected, owner ADC

**Outcome:** with the operator's consent, ADC records an override of one work revision's computed control floor (ADC-05, ADC-06).

**The target names:**
- the work and its accepted revision;
- ADC's current floor record, and the requested floor record;
- the direction, `RAISE` or `LOWER`;
- `assessment_ref`: an independent assessment, or `null`;
- `authority_decision_ref`: the external authority's decision, or `null` for the operator (I3-01).

**ADC admits it only if:**
- **for a `LOWER`, the authority deciding is the one competent for the work's own project boundary** (I3-01, ADC-01.a). An external authority's decision covers exactly this change: the two floor records on this revision. A `RAISE` is the operator's, and cites no external decision (I3C2-3);
- **the floor record is ADC's current one, for that exact revision** (`FLOOR_STALE`). Both floors are computed by the same adopted rules (ADC-06.g);
- **what makes each direction** (I3C21-1). A `RAISE` keeps every mandatory control of the current floor, relaxes none, and is ranked higher. A requested floor that removes or relaxes any mandatory control is a `LOWER` whatever its rank: sent as a `RAISE`, it is `DIRECTION_MISMATCH`. So every rule for a `LOWER` applies to it: competence, the assessment, the §5 hold and the floor read;
- **a `RAISE` needs no assessment.** Raising is always permitted (ADC-06.a);
- **a `LOWER` that removes or relaxes a mandatory control needs a qualified independent assessment of that exact change** (`ASSESSMENT_REQUIRED`, `ASSESSMENT_INVALID`):
  - the assessor is independent of the requester and the original classifier, and chosen by the authorized selection rule (ADC-06.c, ADC-06.j, ADC-05.h). It excludes every holder in the work's Lead grant lineage: the Lead, its workers and their custodians. A holder of an independently authorized grant on the same work is not excluded for that alone;
  - the competent authority's decision authorizes the change, and the assessment qualifies it. Neither is enough alone (A06's text: "cannot casually waive mandatory independent verification");
  - **an external authority's decision is not the assessment.** On an external boundary, a mandatory lowering needs both.

- **A `LOWER` that keeps every mandatory control needs no assessment.** It is still recorded as an exception unless corrected inputs support it.

**What it records:** the override, with both floor records, the assessment and the consent.
- **While a lowering is unresolved, the existing protections stay** (ADC-06.d).
- **A lowering unsupported by corrected inputs is recorded as an exception, not as a correction** (ADC-06.f).

**What it never does:**
- **it never changes the classification rules themselves** (ADC-06.h). That is the policy authority's, outside this pass;
- **it never carries to another revision.** A new accepted revision gets a new floor, computed by ADC.

## I3-07. `AUTHORIZE_EXTERNAL_EFFECT` (A09), protected, owner ADC

**Outcome:** with the operator's consent, ADC records a single-use authorization for one exact external effect, such as a push, a pull request or a publication (HEB-04.g, ADC-08.a). This is how AEW keeps the operator's rule that it never pushes or opens a pull request without sign-off.

**The target names:**
- the work and its accepted revision;
- the grant the effect runs under, and its version (`GRANT_STALE`, I3R1-9);
- the effect class, from a closed enum: `PUSH`, `OPEN_PULL_REQUEST`, `PUBLISH` or `SEND_EXTERNAL_MESSAGE`;
- the exact destination;
- the effect content's SHA-256;
- the authorization's finite validity;
- `authority_decision_ref`: the original domain effect owner's decision, or `null` for the operator (I3-01).

**ADC admits it only if:**
- the grant is current, at that version, and covers that work and revision (`GRANT_NOT_CURRENT`, `GRANT_STALE`, `GRANT_NOT_COVERING`);
- the grant permits protected effects. An `ADVISOR` or `INVESTIGATOR` grant does not (`GRANT_NOT_COVERING`, I3C2-1);
- the authority deciding is the one competent for the work's own project boundary (I3-01, ADC-01.a). An external decision covers exactly this effect: its class, destination and content digest, on this revision;
- WIS's current accepted revision is the one named (`WORK_REVISION_STALE`);
- the validity is finite and in the future (`VALIDITY_INVALID`);
- the exact payload is held under its digest (`CONTENT_UNAVAILABLE`, a hold; I3-09).

**What it records:** one authorization, bound to the grant, the work revision, the class, the destination and the content digest.

**What HEB does with it,** at its effect boundary (a consequence, not this operation's effect):
- HEB admits exactly one effect whose class, destination and content digest all equal the authorization's, while it is unexpired and its grant is current. The authorization is then spent;
- any other effect is not covered.

**It is never a blanket tool whitelist** (A09's text).

## I3-08. ADC's in-scope determination (I-5's I5R1-B1; an owner fact, not a command)

**What I-5 (A-29) already fixes:** WIS accepts a child proposal without the operator only on "a current in-scope determination for exactly that proposal: its digest, and its parent's accepted revision" (I5-03). It is never for a root, a revision or an intake.

**When ADC may issue one** (ADC-03.b):
- **the impact, ownership, dependency and assurance checks are satisfied** for the child;
- **the child inherits its parent's mandatory obligations unchanged** (ADC-09.d);
- **the child needs no grant beyond the proposing Lead generation's current grants.** So no determination is issued for a proposal from a revoked or ended generation;
- **it is issued by an adopted ADC rule, or by an assessor who is not the Lead** (ADC-05.a, ADC-05.h). A Lead's own claim of scope is a label (ADC-05.g).

**What it carries:**
- the proposal reference and its content digest;
- the parent work and its accepted revision;
- the issuer;
- its finite validity;
- the proposing generation. That is ADC's own field: I5-03 does not read it.

**It stays current only while the proposing generation's newest classification is `ROUTINE`** (I3R1-3).
- A trust revocation of that generation's root grant ends it, in the same step (I3-04). So WIS, reading it under I5-03, finds none.
- **A suspension does not end it.** A suspension is reversible, acceptance grants nothing, and ADC-08.c already denies effects.

`verify_i3.py` checks that a determination issued under these rules has the fields I5-03 reads.

**Candidate:** the Lead requests a determination through ADC's own interface.

## I3-09. Activation needs the adopted parameters (A-05 §5)

**A-05 §5's undefined-parameter rule:** "no new protected effect obtains permission merely because a contract remains incomplete". Each §5 row says what its parameter is "Required before". So a type is held only for the effect that row names, and nothing more.
- The owner holds it with `POLICY_UNAVAILABLE` (`SOURCE_UNAVAILABLE`), allocating nothing and consuming no consent, as I5-08a's hold does.
- What a row is not required before is not held. §5's own words: missing parameters "do not prohibit permitted research, status reads or unrelated work".

| Type | When it is held | A-05 §5's row, and what it is "Required before" |
|---|---|---|
| `DELEGATE_NEW_WORKER` | **only for a role with a protected or source-mutating effect:** `IMPLEMENTER` and `DIAGNOSTIC`. `ADVISOR` and `INVESTIGATOR` are never held (I3R1-6) | "Allowed helper/advisor roles, budget allocation and grant procedure": "Delegating assistance with protected effects". And "Issuer-authorized routine handover versus trust revocation, grant lineage, reassignment and policy-defined expiry": "Any admission or continuity of delegated protected effects". For `DIAGNOSTIC`, also "Diagnostic write boundaries and admission/evidence separation": "Diagnostic privileges". The hard limits are §5's "Resource hard ceilings", read per delegation (I3-03). The launch itself is HEB's, under "All mutable-agent launch permissions" |
| `AUTHORIZE_EXTERNAL_EFFECT` | always | "Minimum mediated effect channels, effect acceptance, emergency revocation and stale-authority handling": "Protected execution" |
| `ADJUST_LEAD_AUTONOMY` | **only for a value above its start** (`NONBEHAVIORAL_LOCALIZED`), while that parameter's own row is unadopted. A narrowing, or a return to the start, is never held (I3R1-5) | "Standing incidental-maintenance allowance and criteria for nonbehavioral change": "Automatic unrelated maintenance". The binding-versus-preference row and the helper-roles row govern the other two parameters, but no value of theirs is above its start |
| `OVERRIDE_RISK_FLOOR` | **only for a `LOWER`.** A raise is never held (ADC-06.a). A `LOWER` also waits for the floor read (below) | "Classification categories, minimum observable triggers and protective fallback": "Any classification-based admission or removal of controls". And "Reviewer independence, mandatory/discretionary finding classification": "downgrades removing protection" |
| `DECIDE_DISCRETIONARY_REVIEW` | **never as a type.** AEV states a finding's class only under its adopted mandatory or discretionary classification. Without one, every finding's class is unavailable, and I3-02 holds that finding (`FINDING_CLASS_UNAVAILABLE`) | "Reviewer independence, mandatory/discretionary finding classification and technical adjudication" |
| `REVOKE_LINEAGE` | **never.** It only reduces, and A-05 §5's preservation rule keeps "Current effective ... revocation ... controls" effective | Its §5 row, minimum mediated effect channels, is required before "claims of effective revocation". So `EFFECT_CONFIRMED` means ADC recorded the revocation. That HEB has stopped every running effect is HEB's claim, made only where that parameter is adopted (I3-04) |

**Holds are per §5 row, not per type.** Adopting a row releases what that row is required before, and nothing else.

**Two members bind content the operator must read, so I5-08a applies to them.** Each is held with `CONTENT_READ_UNAVAILABLE` until a selected read shows that content.
- **`AUTHORIZE_EXTERNAL_EFFECT`:** the exact diff or payload. It must also be held under its digest (`CONTENT_UNAVAILABLE`, a hold): a read cannot show content that no owner holds. **Candidate:** HEB holds it, at its effect boundary.
- **`OVERRIDE_RISK_FLOOR` with `LOWER`** (I3R1-7): both floor records and the assessment, so the operator sees which controls a lowering removes (ADC-06.g). A `RAISE` is not held.

## I3-10. What the operator sees, and what is readable

- **The consent is A-26's, unchanged.** G3-03 renders every target leaf. Each new protected target has at most 9 leaves (A09's), and the largest member renders in 25 of the 30 lines allowed (`verify_i3.py` derives this).
- **The consequence fact.** D-01 has no ADC item read: `owner-pins.json` gives ADC an axis of `continuation` only. So, as for W04, the four protected ADC types have no consequence fact until an ADC grant read exists.
- **`IntentResult`:** every type reports `ADMITTED`, `EFFECT_CONFIRMED` at admission, owner `ADC` or `AEV`. A derived grant, an override or an authorization being confirmed never means that the effect it covers has happened.
- **What a D-01 change must add:**
  - an ADC grant read: lineage, version, holder, autonomy, and revocation and suspension state;
  - floor records and overrides;
  - effect authorizations and whether each is spent;
  - an AEV finding read: class, dispositions and rationale.

## I3-11. Cross-row interactions, as a matrix

**Every pair below touches the same subject. A cell marked † has a fixture in `verify_i3.py`.**

**The grant subject:**

| Then ↓ / after → | `REVOKE_LINEAGE` (I3-04) | `SUSPEND_GRANT` (A-25) | `ADJUST_LEAD_AUTONOMY` (I3-05) |
|---|---|---|---|
| `LIFT_OPERATOR_SUSPENSION` (A-25) | **R1†** the lift removes the suspension only; the grant stays revoked | the lift's own rule | no interaction: autonomy is not a suspension |
| `REAFFIRM_ELIGIBLE_CHILD_GRANTS` (A04) | **R2†** nothing reaffirmed: the generation is `TRUST_REVOCATION` | A-25's rule (a suspended child is refused) | no interaction: the Lead grant's version is not a child's prior grant |
| the I-1 handover claim | **R3†** defeated: the classification is not `ROUTINE` | A-28's rule | no interaction |
| `SWITCH_ACTIVE_WORK_CONTEXT` (I1-02) | **R4†** `GRANT_NOT_CURRENT` | `GRANT_NOT_CURRENT` (A-28) | no interaction: the same grant reference, at a new version |
| `CONTINUE_ELIGIBLE_WORK`, `DELEGATED_CANCEL` (A-25) | **R5** refused, because the grant is not current. HEB has already stopped the descendants (HEB-07.j), so this fails closed | A-25's rule | no interaction |
| `DELEGATE_NEW_WORKER` (I3-03) | **R6†** parent revoked: `PARENT_GRANT_NOT_CURRENT`. A worker grant issued before is a descendant, so revoked | **R7†** parent suspended: `PARENT_GRANT_NOT_CURRENT` | **R8†** `helper_delegation: NONE` gives `DELEGATION_NOT_PERMITTED`; an old parent version gives `PARENT_GRANT_STALE`; existing derived grants are not ended, but their effective autonomy follows the Lead grant at once (I3-05) |
| `DECIDE_DISCRETIONARY_REVIEW` (I3-02) | **R9†** `GRANT_NOT_CURRENT` | **R9†** `GRANT_NOT_CURRENT` | no interaction: autonomy does not change a finding's class |
| `AUTHORIZE_EXTERNAL_EFFECT` (I3-07) | **R10†** refused at issue. An unspent authorization is void with its grant, and HEB admits no effect under it | the effect waits: HEB admits none while the grant is suspended (ADC-08.c) | no interaction |
| `ADJUST_LEAD_AUTONOMY` (I3-05) | **R11†** a revoked grant: `GRANT_NOT_CURRENT` | adjusting a suspended grant is allowed, and takes effect only after a lift | two adjustments: the second must name the first's version (`GRANT_STALE`) |
| `REVOKE_LINEAGE` (I3-04) | **R12†** `ALREADY_REVOKED` | **R13†** revoking a suspended grant: allowed | no interaction |

**More grant cells (revision 2):**
- **R15†** `REVOKE_LINEAGE` of an earlier, ended generation's root grant, after A04 reaffirmed its children: the reaffirmed grants are revoked with the lineage (I3-04, I3R1-2). The current generation's own grants and classification are untouched.
- **R16†** `ADJUST_LEAD_AUTONOMY` crossed with an existing derived grant: the worker's effective values follow the Lead grant at once (I3-05, I3R1-4).
- **R17** the revoked generation's own delegated rows (I3R1-10): `CREATE_PROPOSED_WORK` (I5-02) and I-1's L11 and L14 read only HEB's seat fact, so a revoked Lead can still record a proposal or a context handoff. Each fails closed: a proposal grants nothing, no determination is issued for it (P1), and I1-05's claim is defeated (R3). Fencing a revoked generation is HEB's (I1-06, HEB-07.j).

**The boundary subject (I3R1-1):**

| When | Then |
|---|---|
| **C1†** A06 or A09 on an external authority's boundary, on the operator's consent alone | `AUTHORITY_NOT_COMPETENT`; nothing recorded |
| **C2† to C5†** with that authority's qualified decision for exactly this change or effect; for another one; naming the external work under the operator's project; citing an external decision on the operator's boundary | admitted; `AUTHORITY_DECISION_INVALID`; `PROJECT_MISMATCH`; `AUTHORITY_DECISION_INVALID` |
| **C6†** no competence record for the boundary | a hold (`COMPETENCE_UNAVAILABLE`); no consent consumed |
| **C7†** a mandatory lowering on an external boundary, with the authority's decision and no assessment | `ASSESSMENT_REQUIRED`: the decision is not the assessment |
| **C8†** the same external decision used a second time, for A09 or A06 (I3C2-2) | `AUTHORITY_DECISION_INVALID`: it was spent with its first use |
| **C9†** a `RAISE` on an external boundary, on the operator's consent; and one citing an external decision (I3C2-3) | admitted; `AUTHORITY_DECISION_INVALID` |
| **C10†** a higher-ranked floor that drops a mandatory control, sent as a `RAISE`, on either boundary (I3C21-1) | `DIRECTION_MISMATCH`. Sent as a `LOWER`, it takes every `LOWER` rule: `AUTHORITY_NOT_COMPETENT` on an external boundary, `ASSESSMENT_REQUIRED` on the operator's |
| **G3†** an external effect under an `ADVISOR`'s grant, issued while the helper rows were unadopted (I3C2-1) | `GRANT_NOT_COVERING`. An `IMPLEMENTER`'s grant may back one |

**The work revision subject:**

| When | Then |
|---|---|
| **V1†** a new accepted revision (I5-03) after `DELEGATE_NEW_WORKER`, `OVERRIDE_RISK_FLOOR` or `AUTHORIZE_EXTERNAL_EFFECT` named the old one | a new delegation naming the old revision is `WORK_REVISION_STALE`. One naming the new revision is `SCOPE_EXCEEDS_PARENT` until ADC reassesses the Lead's grant (ADC-02.d). An override does not carry: ADC computes a new floor. An authorization covers no effect on the new revision |
| **V2†** `DELEGATE_NEW_WORKER` on work that has only a proposal (I5-02) | refused, `WORK_REVISION_STALE`. A proposal grants nothing |

**The finding subject:**

| When | Then |
|---|---|
| **F1†** two dispositions of one finding version | the second is `FINDING_STALE` |
| **F2†** a disposition on a mandatory finding | `MANDATORY_FINDING`; nothing recorded |
| **F3** a changed package after a disposition | AEV reassesses whether it applies; it does not carry (AEV-10.c) |
| **F4** `OVERRIDE_RISK_FLOOR` lowers a floor so that a check is no longer mandatory | AEV's class of the finding changes only by AEV's own reassessment. `DECIDE_DISCRETIONARY_REVIEW` reads AEV's current class, never the override |

**The effect subject:**

| When | Then |
|---|---|
| **E1†** a second effect under one authorization | not covered: the authorization is spent |
| **E2†** an effect whose content, class or destination differs | not covered |

**The proposal subject:**

| When | Then |
|---|---|
| **P1†** an in-scope determination asked for a proposal from a revoked generation | none issued (I3-08) |
| **P2†** a determination issued before the generation's root grant is revoked (I3R1-3) | the revocation ends it, so WIS finds none under I5-03. A suspension does not end it |

## I3-12. Ordering, atomicity and refusals

- **One admission path:** origin, then owner state, then the activation hold (I3-09), then at most one owner effect per member (CS-05).
  - Every activation hold is decided from the target alone (I3-09): the role, the value set, the direction. It allocates nothing.
- **A revocation and its lineage's revocation are one atomic step.** So is the trust-revocation classification it records.
- **A delegation is compare-and-set** on the parent grant's version.
- **A grant that is not current is reported as not current, whatever version the target names.** That means revoked, suspended or expired. A revoked grant is `ALREADY_REVOKED` to `REVOKE_LINEAGE`, and `GRANT_NOT_CURRENT` or `PARENT_GRANT_NOT_CURRENT` to the others; a stale version comes second. A revocation moves the grant's version.
- **An authorization is spent atomically** with the effect HEB admits under it.
- **ADC's own grant state is the admitting owner's state** for the five ADC types: unavailable, it is `UNKNOWN_OWNER_STATE`. Only AEV, for W07, reads it as another owner's fact (`GRANT_STATE_UNAVAILABLE`, a hold).
- **Each owner reason maps to an adopted reason code** in `wire/refusal-reasons-0.5.json`. The map is complete and fail-closed. Refusals before the owner step allocate nothing; an owner refusal is allocated; a hold allocates nothing and consumes no consent.

## I3-13. The wire

`tools/build_i3_wire.py` generates `wire/` from A-29's frozen `adopted/o01-0.4-i5/wire/`, pinned by its `SHA256SUMS`:
- **`o01-command-0.5.schema.json`:** A-29's schema, plus six Intent branches and six Target definitions, with the owner enums gaining `AEV` (I3-00a). The version is `o01-command-0.5-candidate`.
  - The two delegated branches require the seat, and both proof slots `null` (I1-01, I5-02).
  - The four protected branches require a `null` seat (I5-12).
- **`openapi-o01-0.5.yaml`:** the same definitions, checked equal by the script.
- **`action-registry-0.5.json`:** A-29's 21 rows unchanged, plus six.
- **`refusal-reasons-0.5.json`:** A-29's map, plus the six types' owner reasons.
- **`PREDECESSOR-PINS.json` and `SHA256SUMS`.** `--check` regenerates and compares.

## I3-14. Questions for the reviewer

- **Q1 (I3-00):** does W07 belong to AEV, with ADC's grant read? Or does ADC own it, as the classification said?
- **Q2 (I3-04):** is recording `TRUST_REVOCATION` for a revoked Lead generation the issuing authority's decision under ADC-02.l? Or does it need a separate classification act?
- **Q3 (I3-05):** are the three closed autonomy parameters the right set? Do any of them change what an adopted rule already fixes?
- **Q4 (I3-06):** does requiring an assessment for a mandatory lowering contradict the operator's authority under ADC-01.a? Or is it exactly what ADC-06.c says?
- **Q5 (I3-09):** each type is held only for the effect its A-05 §5 row is "Required before": W10 only for `IMPLEMENTER` and `DIAGNOSTIC`, A09 always, A05 only above its start, A06 only when lowering, W07 per finding, A01 never (revision 2). Is that proportionate? And is it all that A-05 requires?

## I3-15. Not claimed

- **This selects interface architecture.** It qualifies no host, builds nothing, and activates no action. Protected rows stay held wherever G3 is not established, and I3-09 holds what A-05 §5's parameters are required before, until they are adopted.
- **Candidate mechanisms are not claimed:** scope containment by digest, rationale and effect-content intake (HEB holding the payload), the determination request, and HEB's spend at its effect boundary.
- **Out of scope:**
  - D-01 changes;
  - W06, the dispute path (I-4);
  - classification rule changes (ADC-06.h);
  - the A-05 §5 parameters themselves;
  - A-29's 21 actions, which are unchanged.
