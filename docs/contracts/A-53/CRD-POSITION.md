<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-53
source: 30-stages/STG-28-I5-08a-content-read/adopted/crd-r3.1/CRD-POSITION.md
source-sha256: b23667ca3831123fd7fa383c15eeecb2d8fb59f060490aba5f019a48d4a18256
edits-sha256: none
-->

# CRD: I5-08a's content read, defined for V-01's path (PROPOSED, revision 3.1)

**Namespace:** `CRD-`
**Status:** proposed.
- **What it answers:** A-48's fourth item that blocks V-01's outcome by design, "I5-08a's content read". I5-08a (A-29) holds each type that binds content the operator must read with `CONTENT_READ_UNAVAILABLE`, "until a selected read shows the operator that content, by the digest or ref its target binds". A-30, A-31, A-34 and A-43 apply it to their own types. No adopted text says what "selected" and "shows" mean, or on what record an owner lifts the hold.
- **How it amends:** by addition. Adopted copies keep their bytes, and no O-01 or D-01 schema byte moves.
  - It defines the release condition once (`CRD-01`).
  - It derives, for every type that maps `CONTENT_READ_UNAVAILABLE` on O-01 0.9, how each field its target binds is shown: returned by a read, or checked by the owner with a named refusal (`CRD-02`).
  - It names, at field altitude, the reads D-01 0.3.4 lacks (`CRD-03`). Their wire is a D-01 revision of its own, because A-23 selects D-01 by exact version (`CRD-R03`).
  - It reads the shared capabilities read, under A-38's field mapping, as the record that says a read is served (`CRD-R02`).
- **What it leaves:** the D-01 revision itself (`CRD-B1`); the read surface's rendering beyond what a read returns (`CRD-B2`); and the types `CRD-02` names out of I5-08a.

**Authority:** the operator's decision to draft it (`00-governance/decisions/2026-11-01-operator-start-STG-28-I5-08a-content-read.md`), under A-48 (`00-governance/decisions/2026-11-01-operator-adoption-V01-matrix-r4.md`).
**Threat model:** the operator's G3 threat model (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`), under the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`).
**Research consulted:** `tools/research_index.py lookup`, 2026-11-01: `I5-08a`, A-23, A-12, A-22, D-01, `ADC-03.n` and `I4-06` returned none.
**Files:** this file, and its gate, `check_crd.py`, a derivation check with no model.

## What the adopted text already decides

- **The hold** (A-29 `I5-08a`): each content-binding type "is activated only once a selected read shows the operator that content, by the digest or ref its target binds. That read is I5-09's D-01 change, or a named functional read." Until then the owner holds with `CONTENT_READ_UNAVAILABLE`, allocating nothing and consuming no consent. Within `CANCEL_OR_REPLACE_TICKET`, only `REPLACE` is held.
- **Why** (A-29 `I5-08`; A-05 `ADC-03.n`): decision-bearing commitments are visible to the approver at approval time. G3 never shows agent text as prose (`G3-03`), so the content is read on the read surface, and the consent binds its digest. The owner refuses a leaf that differs from its record (`I5-03`), so what is accepted is what was readable. The residual risk is an AEW host-code bug that shows other content than the bound digest.
- **The other owners' applications:**
  - A-30 `I3-09`: `AUTHORIZE_EXTERNAL_EFFECT`'s exact diff or payload, also held under its digest (`CONTENT_UNAVAILABLE`), since "a read cannot show content that no owner holds"; and `OVERRIDE_RISK_FLOOR` with `LOWER` only: both floor records and the assessment;
  - A-31 `I4-06`: `APPROVE_INTEGRATION`'s package, its digest and closure reference, and its readiness. "D-01 0.3.4 has both reads", and "a deployment that does not serve them holds the type";
  - A-34 `I2-06`: `DISCARD_HELD_RESULT`'s held result. "D-01 0.3.4 has no held-result read";
  - A-43 `I7-05.a` and `I7-07.a`: an inquiry's and a mission's content, and the mission's preflight digest, "held for the operator's read before consent".
- **What D-01 0.3.4 shows and lacks** (A-29 `I5-09`): it shows a work item's accepted revision and composition, and a decision need's existence on the attention read. A D-01 change must add proposals with their content, state and author; a need's options; replacement lineage; the original accepted revision; and a CNI interface read.
- **Selection** (A-23): a D-01 wire is selected by exact version, and a client or server serves exactly the version it names. So a read is selected only as part of a selected D-01 version.
- **The capabilities read** (D-01 0.3.4 `/v1/read/capabilities`, `CapabilityData`): one shared capability source, which nobody silently reinterprets (`S01-21`).
  - IF-13 owns an installation's effective capability (A-18): the capability's role (`IF13-04`), its `effective_state` and its `binding_epoch`. Holding owners re-evaluate at each consequential effect (`IF13-09`).
  - A-38 puts its register's tool capabilities on the read, and maps their status (`CAPR-03`): the register's status is `observed_status`, and `assessment_status` stays `NOT_ESTABLISHED` unless a qualification record gives `QUALIFIED`. Nothing in A-38 makes the register the read's only source.
  - The read's effect is `NOT_AN_EFFECT_GRANT`.
- **An activation hold's inputs:** `I3-12`, `I4-11` and `I2-11` decide an activation hold from the type and the target (and, for HEB, its own record of the prior operation). A-51's `AP5-01` already has each holding owner read a record at each effect, by addition.

## The parts

- **The operator** reads the content on the read surface, and consents to its digest or ref through G3.
- **Each content owner** (WIS, CNI, HEB, ADC, AEV) produces its read, computes its digests, and holds its type until the read is served.
- **The capabilities read** carries A-38's register entries and IF-13's installation capabilities, with one field mapping. IF-13 owns the content-read capabilities (`CRD-R02`).
- **D-01** carries the reads, by exact version (A-23).

## Rules

**CRD-00. Precondition: A-29's `I5-08` and `I5-08a`, A-30's `I3-09`, A-31's `I4-06`, A-34's `I2-06` and `I2-08`, A-43's `I7-05.a` and `I7-07.a`, A-23's exact version selection, A-18's `IF13-04`, and A-38's `CAPR-03` hold as adopted, except where a rule here adds to them.** Nothing here narrows a control.

**CRD-01. A selected read shows the operator the content when all of these hold, and the owner lifts `CONTENT_READ_UNAVAILABLE` only then.**
- **Selected:** each read the type's row names (`CRD-02`) is part of the D-01 version the installation selects, by A-23's exact version.
- **Served:** for each content-read capability the row needs (`CRD-C0`), the capabilities read's current `CapabilityData` for the installation has `effective_state` `EFFECTIVE` at the installation's current `binding_epoch`, and either `observed_status` `FUNCTIONAL_ONLY` or `assessment_status` `QUALIFIED`. That is the shared read's own mapping (`CAPR-03`, `S01-21`). No entry, or any other value, is not served.
- **Shown, per bound field:** a bound field is one `CRD-02` lists for the type. Each is in exactly one of two classes.
  - **Returned:** the named read returns it. For a digest, the read returns the digest the producing owner computed, with the content the frozen clause names: the bytes, for a proposal, a candidate, a payload or a preflight; for a package, its digest and closure reference, as `I4-06` names them. For a ref, the read returns the record the ref names.
  - **Checked:** the read does not return it, and the owner refuses a target whose field differs from its record, with the named refusal.
- **A ref with no version** names an immutable record, or the owner refuses it when stale. A proposal is immutable (`I5-08`, `WIS-02.b`). A requested floor and an assessment are immutable as their owner's records. A need and its options are refused when stale at the target's `work_revision` (`NEED_STALE`), and the current floor when it is no longer current (`FLOOR_STALE`).
- **A bound field that differs from the owner's record is refused** by the owner: `RECORD_MISMATCH` (`I5-03`, `I5-04`, `I5-06`, `I7-05.a`, `I7-07.a`); `PREFLIGHT_MISMATCH` (`I7-07.a`); `PACKAGE_MISMATCH` and `PACKAGE_CLOSURE_INVALID` (`I4-05`); `RESULT_STALE` (`I2-06`); `FLOOR_STALE` (`I3-06`); `NEED_STALE` (`I5-05`). The exception is `AUTHORIZE_EXTERNAL_EFFECT`'s `content_sha256` and `destination_ref`. There ADC holds no content to compare, so `CRD-C4`'s read is addressed by both. What is shown is then, by construction, what is bound, and HEB admits only an effect whose class, destination and digest equal the authorization's (`I3-07`).
- **What the owner reads:** only the capabilities read. "Shown" and "reaches the operator" are what that record's status attests, because the capability's functional check is the read's conformance cases (`CRD-C0`).
- **The hold names its cause:**
  - the outcome's `owner_evidence_ref` names the snapshot the owner read: the installation's `effective_profile_ref` at its current `binding_epoch`;
  - the owner's hold record names the `CRD-02` row, and each capability ID not served, as `AP5-01`'s hold names its row;
  - a route withdrawn, a status lost or a selected version changed holds the type again at its next effect.

**CRD-02. The content-binding types, and how each bound field is shown.** The table is derived from the O-01 0.9 refusal map: every type that maps `CONTENT_READ_UNAVAILABLE` has one row. A returned field names the read's field (`Component.field`) where the read is in D-01 0.3.4; otherwise its candidate in `CRD-03` returns it. A checked field names its refusal. The gate checks every column.

| Type | Held when | Returned by the read | Checked by the owner | Read in D-01 0.3.4 | Gap |
|---|---|---|---|---|---|
| `APPROVE_INTEGRATION` | always | `package_digest` (`PackageData.digest`), `source_closure_ref` (`PackageData.source_closure_ref`) | `package_ref` (`PACKAGE_MISMATCH`), `readiness_ref` (`ASSURANCE_STALE`, `ASSURANCE_NOT_CLEAR`) | `/v1/read/work/{work_kind}/{work_id}/packages`, `/v1/read/assurance/{subject_kind}/{subject_id}` | none |
| `DECIDE_WORK_PROPOSAL` | always | `proposal_ref`, `content_sha256` | none | none | `CRD-C1` |
| `CANCEL_OR_REPLACE_TICKET` | `REPLACE` only | `successor_proposal_ref`, `successor_content_sha256` | none | none | `CRD-C1` |
| `ANSWER_DECISION_NEED` | always | `need_ref`, `option_ref` | none | none: the attention read shows only the need's existence | `CRD-C2` |
| `APPROVE_INTERFACE_CHANGE` | always | `candidate_ref`, `candidate_content_sha256` | none | none | `CRD-C3` |
| `AUTHORIZE_EXTERNAL_EFFECT` | always | `content_sha256`, `destination_ref` | none | none | `CRD-C4` |
| `OVERRIDE_RISK_FLOOR` | `LOWER` only | `current_floor_ref`, `requested_floor_ref`, `assessment_ref` | none | none | `CRD-C5` |
| `DISCARD_HELD_RESULT` | always | `result_ref`, `result_version` | none | none | `CRD-C6` |
| `ACCEPT_INQUIRY` | always | `proposal_ref`, `content_sha256` | none | none | `CRD-C1` |
| `ACCEPT_MISSION` | always | `proposal_ref`, `content_sha256`, `preflight_sha256` | none | none | `CRD-C1`, `CRD-C7` |

`APPROVE_INTEGRATION`'s assurance read returns the readiness state (`AssuranceData.readiness`), which the operator reads. Its `readiness_ref` is the owner's to check.

**Not in the table, and not a leak:** the types that map only `CONTENT_UNAVAILABLE` on 0.9: `CREATE_PROPOSED_WORK`, `DECIDE_DISCRETIONARY_REVIEW`, `OPEN_HELD_INQUIRY`, `REQUEST_HOLD_RESOLUTION` and `REQUEST_INDEPENDENT_REASSESSMENT`. Each is the Lead's, not the operator's: its owner holds the request until the content is held under its digest. Nobody is asked to read and consent to it, so I5-08a does not reach it. `ISSUE_STANDING_POLICY` binds `policy_body_sha256`, the operator's own policy body, rendered as its leaves, and no agent's content (`I6-10`: no I-6 type binds content the operator must read beyond its own leaves). `AUTHORIZE_EXTERNAL_EFFECT` maps both reasons (`CRD-R04`).

**CRD-03. What a D-01 revision must add, at field altitude.** Each candidate is read by the owner of its content, and each digest is computed by that owner.

**CRD-C1.** **Proposals:** a proposal's `proposal_ref`, its content and its `content_sha256`; or, for a successor, its `successor_proposal_ref`, content and `successor_content_sha256`, with the Ticket it replaces (I5-09's replacement lineage). With them: its kind (a Ticket, an inquiry, a mission or a successor); its author; its state; the expected and the original accepted revisions it is judged against (`I5-09`, `I5-03`); its decision-bearing commitments, as WIS marked them at proposal time (`I5-08`); and its asker where it has one. For an inquiry: its question, boundaries and governing sources (`I7-05`). For a mission: its objective, coverage, stop conditions, reserved decisions and report point (`I7-07`). WIS's.

**CRD-C2.** **A decision need's options:** the need's `need_ref`, and each `option_ref` with its consequence, at the target's `work_revision` (`NEED_STALE`). WIS's.

**CRD-C3.** **A CNI interface candidate:** its `candidate_ref`, its content and `candidate_content_sha256`, and the commitment it changes. CNI's.

**CRD-C4.** **A held external effect,** addressed by the target's `content_sha256` and `destination_ref`: the exact diff or payload HEB holds under that digest, for that destination. HEB's.

**CRD-C5.** **A risk floor lowering:** the `current_floor_ref` and `requested_floor_ref` records, and the assessment by `assessment_ref` where the target names one (`I3-06`), so the operator sees which controls a lowering removes (`ADC-06.g`). ADC's.

**CRD-C6.** **A held result:** the result by `result_ref` at its `result_version`; its producing lineages; why HEB holds it; and its acceptance (`I4-10`, as A-49 reads the lineage). It is shown as discarded after a discard (`I2-06`). HEB's.

**CRD-C7.** **A mission's preflight:** the preflight WIS recorded for the proposal, and its `preflight_sha256`. WIS's.

**CRD-C0.** **The content-read capabilities:** one capability ID per content-read route, on the capabilities read.
- **Its role:** each is allocated `OPTIONAL` in the installation's profile definition (`IF13-04`). An optional capability imposes no activation requirement and confers no authority, and its failure holds only the effects that depend on it (`IF13-19`). So a content read that is missing, `STALE` or `UNAVAILABLE` holds only its `CRD-02` types, through `CRD-01`, and never the installation's binding or any other agent activation (`CRD-R01`). The allocation is a profile-definition change, made through the operator's manifest adoption, not only a new value.
- **Its minimum:** `CRD-01` is the dependent effect's release condition, so the owner reads `FUNCTIONAL_ONLY` or `QUALIFIED` there, not in the profile's activation predicate.
- **Its functional check:** the read's conformance cases (`CRD-B1`). They exercise each returned field of each row the route is for, and delivery to the operator's `effective_recipient_ref` (`D01-WR-08.a`). Their result is the capability's independent observation and per-capability assessment (`IF13-05`, `IF13-06`), and so the read's `observed_status`, with the meaning `CAPR-03` gives that field.
- **Its owner:** IF-13, as one of the installation's own capabilities, not a register entry. A content-read route is no tool an agent is granted (`CAPR-01`), so no role's catalog lists it, and A-38 is not amended.

**CRD-04. What adoption releases, and only that.**
- **Today:** nothing. No installation has a content-read capability entry, so no row is served (`CRD-01`). On D-01 0.3.4, adoption activates nothing.
- **W09** (`APPROVE_INTEGRATION`): its two reads are in D-01 0.3.4. Its content hold lifts where the capabilities read shows both capabilities served (`CRD-01`). Their functional check is `CRD-B1`'s conformance cases (`CRD-C0`), which may run against 0.3.4's two routes, so the lift waits for those cases, through the status they set. That lifts one hold, and activates nothing on its own. W09 also waits for:
  - G3;
  - its own `I4-06` rows;
  - A-31's adoption trim: `I4-10`'s D-01 addition, the trust basis on `AssuranceData` (A-49's `TB01-B2`), which needs the same D-01 revision as the other rows (`CRD-B1`);
  - ADC's grants for each owner service that produces determinations (`TB01-B3`).
- **Every other row** stays held until the D-01 revision carrying its candidate is adopted, built and served (`CRD-01`).

**CRD-05. The holds of A-29, A-30, A-31, A-34 and A-43 are read with `CRD-01` to `CRD-04`.**
- `I3-12`, `I4-11` and `I2-11` are read by addition, as `AP5-01` extends `I3-09`: the content-read hold is decided from the type, the target and the capabilities read's current record (`CRD-01`), at the activation-hold step.
- A capabilities read that cannot be read holds the type with `CONTENT_READ_UNAVAILABLE`, as `I4-11` holds another owner's unavailable fact under its own reason.
- A built owner conforms to its hold and to this position together.

## Interfaces

- **No O-01 or D-01 schema byte changes.**
  - `CONTENT_READ_UNAVAILABLE` is already mapped for every type `CRD-02` lists, and `CONTENT_UNAVAILABLE` for `AUTHORIZE_EXTERNAL_EFFECT`. Every refusal `CRD-02` names is already mapped for its type.
  - The outcome's `owner_evidence_ref` is an existing nullable ref, with no constraint tied to a hold, so naming a profile snapshot needs no new field.
  - The capabilities read already exists in 0.3.4. Its `capability_id` admits new IDs, and `capability_role` already has `OPTIONAL`.
- **One definition change:** `CRD-C0`'s role allocation lands in a profile definition (`IF13-04`), through the operator's manifest adoption.
- **The O-01 types whose effects this position touches:** the ten `CRD-02` lists, held; the types it names out, untouched.
- **The D-01 revision** (`CRD-B1`) carries `CRD-C1` to `CRD-C7` and the conformance cases for `CRD-C0`, at a new exact version (A-23).
- **The governance clauses:** this position adds to A-29's `I5-08a`, A-30's `I3-07`, `I3-09` and `I3-12`, A-31's `I4-06` and `I4-11`, A-34's `I2-06` and `I2-11`, and A-43's `I7-05.a` and `I7-07.a`, by addition. The adoption proposal asks whether that answers their records' wire clauses with no new pinned O-01 version, as A-51's and A-52's did.

## The gate

`check_crd.py` is a derivation check: it reads the frozen bytes and this file, and builds no model. Each row states what it reads. Rows that assert a derived count fail closed when frozen text changes.

| Check | What it shows | Scope | Pass |
|---|---|---|---|
| **CRD-Q01** | `CRD-02`'s rows are exactly the types that map `CONTENT_READ_UNAVAILABLE` in A-43's frozen 0.9 refusal map. | the table's first column | the same set |
| **CRD-Q02** | Each row's bound fields (both its "Returned" and its "Checked" columns) exist in that type's 0.9 target, and include every target field that ends `_sha256` or `_digest`. A bound `<x>_ref` whose target also has `<x>_version` binds the version too. Which other refs name the content is the designer's reading of the frozen clause, and is not checked. | the two field columns | every row |
| **CRD-Q03** | Each 0.3.4 path a row cites is a path of the sealed D-01 0.3.4 OpenAPI. A row with gap "none" is one a frozen line says 0.3.4 has reads for, and cites exactly those paths. A row whose frozen line says 0.3.4 has no read cites none. A row that cites none names a candidate. | the "Read in D-01 0.3.4" and "Gap" columns; the frozen lines that contain "D-01 0.3.4 has" | every row |
| **CRD-Q04** | A row's "Held when" says "only" with the branch exactly where a frozen line holds the type only for one branch (`only \`X\``, `only for a \`X\``), and "always" otherwise. | the frozen lines that name the type and say "held" | every row |
| **CRD-Q05** | "Not in the table" names exactly the types that map only `CONTENT_UNAVAILABLE` on 0.9, and every other `PROTECTED_G3` type whose 0.9 target binds a digest; `CRD-R04` names the type that maps both. | that paragraph, `CRD-R04`, the 0.9 registry and targets | the same sets |
| **CRD-Q06** | Every requirement ID this file cites resolves in D1, as a requirement or a named cross-reference; every `CRD-` ID is defined here; and every candidate a row names is defined in `CRD-03`. | backticked IDs; `CRD-C` names | none unresolved |
| **CRD-Q07** | Every clause after `CRD-01`, in the rules, scenarios, rulings and interfaces, that says a read is served, or not served, cites `CRD-01`. The word forms read: serve, serves, served, serving, unserved. | those sections, split at full stops and semicolons | none uncited |
| **CRD-Q08** | This table lists every check `check_crd.py` runs, and no other. | the table's first column, and the script's check names | the same set |
| **CRD-Q09** | Every bound field is in exactly one class. A returned field of a 0.3.4 row names a field of the sealed 0.3.4 schema's component that is that field, or the component's prefix plus it (`package_digest`, `PackageData.digest`); a returned field of a candidate row is named in that row's candidates. A checked field names a refusal the 0.9 map gives its type. | the two field columns; `CRD-03`; the sealed 0.3.4 schema; the 0.9 refusal map | every field |
| **CRD-Q11** | The two majors' fixes stay fixed. `CRD-C0`'s role line allocates `OPTIONAL` and no other `IF13-04` role. `CRD-01`'s exception, and `CRD-R04`'s `CONTENT_UNAVAILABLE` hold, name both `content_sha256` and `destination_ref`, or the bound digest for the bound destination. | `CRD-C0`; `CRD-01`; `CRD-R04` | each line |
| **CRD-Q10** | `CRD-01`'s "Served" names exactly the three field and value pairs `CAPR-03` and `IF13-12` give: `effective_state` `EFFECTIVE`, `observed_status` `FUNCTIONAL_ONLY`, `assessment_status` `QUALIFIED`, with `binding_epoch`. Each field is a `CapabilityData` property of the sealed 0.3.4 schema, and each value is in its enum. | `CRD-01`'s "Served" bullet | every field and value |

## Scenarios

**CRD-X01.** An installation selects D-01 0.3.4. `CRD-B1`'s conformance cases for the packages and assurance routes pass against 0.3.4's routes, so IF-13 records both capabilities `EFFECTIVE` at the current `binding_epoch`, with `observed_status` `FUNCTIONAL_ONLY`. Both are then served (`CRD-01`), and W09's content hold is lifted. The operator reads the package's digest and closure reference, and the readiness state. W09 is still not activated: it waits for G3, its `I4-06` rows, the trust basis read and the producers' grants (`CRD-04`). Had the assurance capability been `UNAVAILABLE`, W09 would be held with `CONTENT_READ_UNAVAILABLE`, its `owner_evidence_ref` naming the profile snapshot, and its hold record naming the row and that capability. The capability is `OPTIONAL`, so nothing else is held (`IF13-19`).

**CRD-X02.** The Lead proposes a Ticket. The operator's `DECIDE_WORK_PROPOSAL` is held with `CONTENT_READ_UNAVAILABLE`: 0.3.4 has no proposals read, so no capability is served (`CRD-01`). Once the D-01 revision carrying `CRD-C1` is adopted, built and served (`CRD-01`), the operator reads the proposal, its revisions and its decision-bearing commitments, and the consent binds its digest.

**CRD-X03.** The Lead asks for an external effect whose payload HEB does not yet hold. `AUTHORIZE_EXTERNAL_EFFECT` is held with `CONTENT_UNAVAILABLE`, naming HEB's record. Once HEB holds the payload under its digest for that destination, the member is held with `CONTENT_READ_UNAVAILABLE` instead, until `CRD-C4`'s capability is served (`CRD-01`). The read is addressed by the target's digest and destination, so the operator reads exactly the bound payload.

**CRD-X04.** The operator upgrades the harness. The packages capability's assessment is invalidated (`IF13-14`), so it reads `STALE` until it is checked again (`CAPR-03`), and is not served (`CRD-01`). The next W09 is held again until it is. The capability is `OPTIONAL`, so the installation's binding and every other activation stand (`IF13-19`).

## Rulings

**CRD-R01. A content read is served at `FUNCTIONAL_ONLY` or `QUALIFIED` (`CRD-01`); no outside assessor is needed.**
- **The role:** each content-read capability is `OPTIONAL` (`IF13-04`).
  - Not a `FUNCTIONAL_PREREQUISITE`: a prerequisite's failure holds the whole release binding (`IF13-19`), so one read going `STALE` after an upgrade would stop every agent activation, not only the approvals that need it.
  - Not a `PROTECTED_EFFECT_GATE`: the read is not the protected effect's gate, because G3's consent and the owner's record check are; and an unqualified gate admits no dependent protected effect (`IF13-04`), so W09 would wait for `QUALIFIED`.
  - The protected effect is gated elsewhere: by G3's consent, and by the owner's check of every bound field against its own record (`CRD-01`).
- **Against `IF13-10`:** a functional record by a controller whose qualification is not established claims no agent-resistant control. None is needed here. A wrong "served" status (`CRD-01`) only lifts this hold. It creates no consent, and the owner still refuses a mismatched field, or, for `AUTHORIZE_EXTERNAL_EFFECT`, the read is addressed by the bound digest and destination (`CRD-C4`).
- **The residual:** host code showing other content than the bound digest is the residual `I5-08` already names, and the threat model leaves out malicious host code.
- **What a contained agent can reach:** the read's producer is a protected executable (`HEB-01.h`, `S01-18`). IF-13's record for the content-read capabilities is host state outside every sandbox, as A-38's register is. Its profile definition changes only through the operator's manifest adoption.
- **The alternative:** `QUALIFIED` only, an outside-lineage assessor's record per capability. No such assessor exists today, so it would hold every operator decision that binds content, with no protection gained against the threat model.

**CRD-R02. The capabilities read, under A-38's mapping, is what says a read is served (`CRD-01`).**
- **One read, one field mapping, two fact owners:** the capabilities read is one shared source (`S01-21`). A-38's register owns the agents' tool capabilities on it. IF-13 owns the installation's own capabilities, the content-read ones among them, and those entries' effective-state fields (`effective_state`, `binding_epoch`, `capability_role`). Every entry's status fields mean the same thing: `observed_status` is the observed basis, and `assessment_status` is `QUALIFIED` only with a qualification record (`CAPR-03`, `IF13-07`). So `CRD-01` reads a content-read entry as every other entry is read, and nobody reinterprets a field.
- **No amendment:** `CAPR-03` is applied as adopted, and A-38's register gains no entry.
- **A record, not words:** the owner reads a record, never the designer's word or the wire's text, as `AP5-01`'s owner does. The grade differs: `AP5-01` reads a qualified assessor's record, and this reads a functional status.

**CRD-R03. The D-01 revision is a stage of its own.** A-23 selects D-01 by exact version, so every candidate in `CRD-03` is a new D-01 version. That revision is already shared with blocked-on-you's three D-01 gaps (A-44), V-01's backlog item B1, and the trust basis read W09 needs (`TB01-B2`). It has no generator yet. This position defines what it must carry for I5-08a, and leaves its bytes to it (`CRD-B1`).

**CRD-R04. `AUTHORIZE_EXTERNAL_EFFECT` has two holds, each with its own record.** `CONTENT_UNAVAILABLE` holds it while HEB holds no payload under the bound digest for the bound destination, naming HEB's record. That reads `I3-07`'s held payload by addition, as `CRD-C4`'s address does: `I3-07` records the destination with the digest. `CONTENT_READ_UNAVAILABLE` holds it while HEB holds the payload but its read is not served (`CRD-01`), naming the profile snapshot. The first comes first, because "a read cannot show content that no owner holds" (`I3-09`).

**CRD-R05. `DISCARD_HELD_RESULT` is reducing, and still held for its read.** A discard ends a held result's path to integration. The operator must see what is discarded, and why HEB holds it, and a discard never removes it from what can be read (`I2-06`). So its read shows the result at its version, and shows it as discarded afterwards (`CRD-C6`).

## Backlog

**CRD-B1.** The D-01 revision, at a new exact version under A-23, with its generator. It carries:
- the candidates `CRD-C1` to `CRD-C7`, and `CRD-C0`'s conformance cases;
- blocked-on-you's three D-01 gaps and V-01's backlog item B1, its result reads;
- the trust basis read (`TB01-B2`);
- the other D-01 items `I3-10`, `I4-10`, `I2-10` and `I5-09` list. They stay owed here, and are not dropped.

**CRD-B2.** The read surface's rendering: `I5-08`'s candidate that the confirmer and the read surface show the same digest prefix, long enough that two contents cannot match by chance.

**CRD-B3.** Reads for the delegated `CONTENT_UNAVAILABLE` types, for the Lead's own view, if a selected step needs them.

## Not covered

- **G3.** Every protected step waits for G3 wherever it is not established.
- **The D-01 revision's bytes** and its build (`CRD-B1`).
- **The build of the content-read capability entries,** their profile-definition allocation and their conformance cases (`CRD-C0`).

## Changes

- **Revision 1 (2026-11-01):** the first text, after the advisor's check on STG-28's shape (`STAGE.md`).
- **Revision 2 (2026-11-01):** answers round 1's thirteen findings (`CHANGES-r2.md`).
- **Revision 3 (2026-11-01):** answers the quick check's six findings (`CHANGES-r3.md`).
- **Revision 3.1 (2026-11-01):** the narrow check's four follow-ons (`CHANGES-r3.1.md`).
