<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-18
source: 10-adopted/RECONCILED-SOURCE-BASELINE/01-ADOPTED-SOURCE-BYTES/A-18__AEW-IF13-Profile-State-and-Transition-Contract-candidate-v0.2.md
source-sha256: 39a00d7bd733cd70fc9f93f1c8096ab6d1a647130e7b809643eb1ac447b8aff9
edits-sha256: none
-->

# AEW IF-13 — Selected Profile Definition, Capability Assessment and Effective Transition Boundary

**Version:** v0.2 CANDIDATE · **2026-10-17** · **Normative status:** PROPOSED, NOT ADOPTED. The 17 existing adopted originals in this pack remain controlling.

## 1. Scope, authority and release applicability

IF-13 specifies the **shared selected-configuration semantics and logical interchange** consumed by independent AEW host/profile providers, Lead/harness selectors, protected HEB/ADC admission, R-01, operator CLI and website. It is not a new grant issuer, entitlement issuer, model-access gateway, OS isolation mechanism, deployment-release selector or G3 origin service. Its profile IDs are identifiers, **not a permission class**. `GENERAL-LOCAL` and `WORK-ROCKY8-MTLS` are proposed bindings, not independently selected or qualified live releases. IF-13 is coupled to O-01's intent/receipt/reconciliation contract. Adopted S01-01–31, HEB-01/03/07/08, ADC-08, AOI-03/04/06, R-01, WIS, CNI and D-01 control wherever applicable.

**Source ownership and authority (no replacement):** The operator (through a separately qualified decision path when required) owns intended selection and policy; host/harness/provider observables have their own identified producer; outside-lineage qualified observers issue bounded capability evidence; HEB/ADC decide protected eligibility and grant; R-01 owns resource policy; CNI owns conflicting-effect admission; AOI governs presentation; qualified configuration controller owns current effective transition. D-01 remains GET-only. A complete state wire record is not itself an issuer credential.

**Due-scope:** v0.2 freezes a candidate portable *logical record contract*, not a URL, auth scheme or protected transport. A release profile must later select exact issuer verification, host security, effective adapter, backend and website fixtures. Functional-only and protected-evidenced transitions must not be conflated.

## 2. Candidate obligations (exact IDs)

**IF13-01 — Typed domains.** `profile_definition`, `basis_observation`, `capability_assessment`, `profile_snapshot` and `transition_receipt` SHALL retain their different owners, version and source. A definition, request, observation, qualification and effective activation are not interchangeable.

**IF13-02 — Canonical identity.** Profile ID/version, host installation and actual effective principal, harness/provider/plugin/tool/route inventories, work/attachment/authority generation, applicable release binding and configuration revision SHALL be separately identifiable; user-supplied aliases are not owner-issued change or operation identities.

**IF13-03 — Desired is not effective.** A requester-specified selection SHALL create an attributable requested target only. A website save/CLI mutation SHALL NOT by itself change sourced `effective` or `qualified` state; `requested` may differ from `effective` indefinitely, including failure and outage.

**IF13-04 — Typed profile activation predicate. Each versioned `profile_definition` SHALL allocate each capability exactly once to one of `FUNCTIONAL_PREREQUISITE`, `PROTECTED_EFFECT_GATE`, or `OPTIONAL`. A functional prerequisite declares a minimum measurable status, subject/route scope and owner-qualified or observed basis; only `FUNCTIONAL_ONLY` or `QUALIFIED` is sufficient when functional is the minimum, and only `QUALIFIED` with the applicable independent evidence is sufficient where qualification is explicitly required. Missing, `NOT_ESTABLISHED`, `STALE`, `UNAVAILABLE`, `UNSUPPORTED`, or incomparable evidence fails a prerequisite. Protected-effect gates may remain unqualified without blocking an otherwise eligible functional profile from becoming `EFFECTIVE`, but no dependent protected effect may be admitted. Optional capabilities impose no activation requirement and confer no authority. Duplicated/conflicting roles, absent typed requirements, unresolvable governing constraints or agent-authored policy strings interpreted as security rules SHALL reject/hold definition activation; compatibility facts SHALL be typed/versioned or resolve to a competent governing source. (S01-02/04/05/19/21/22/24; HEB-01.c.)

**IF13-05 — Independent observation.** Observed actual host/process/effect-surface, provider and harness facts SHALL name source, coverage, epoch and expiration; claims of protected effects require independently bounded *complete* effective route population outside measured agent lineage (S01-02/09). An agent-authored reachability digest never qualifies completeness.

**IF13-06 — Qualification, not boolean.** Every per-capability assessment SHALL specify exact capability class, actor/effect/work and recipient scope, governing issuer basis, evidence/coverage/source epoch/expiry, and one of `QUALIFIED`, `NOT_ESTABLISHED`, `UNAVAILABLE`, `STALE`, `FUNCTIONAL_ONLY`, `UNSUPPORTED`. No aggregate `secure` or unconditional `ready` status.

**IF13-07 — Positive proof.** `QUALIFIED` SHALL require independently qualified, current, applicable evidence plus authority/route coverage not writable by the measured lineage. No raw JSON status or provider signature field independently proves source authenticity.

**IF13-08 — Noncomparable basis.** Missing, contradictory, expired, changed or incomparable host/principal/SDK/tool/effect-route identity SHALL downgrade affected claims to `STALE` or `NOT_ESTABLISHED` before affected protected effects; do not corrupt unrelated qualified source-only or permitted functional operations.

**IF13-09 — Protected effect composition.** A profile assessment or functional effective commit SHALL NOT grant execution. At each actual consequential effect, HEB/ADC must re-evaluate applicable generation/grant and selected qualified route, R-01 controls for resource effects, CNI interference where relevant, and owner-governed model/source disclosure for external egress.

**IF13-10 — Functional versus qualified effective commit. The accountable configuration controller SHALL compare the exact selected definition, typed functional prerequisites, requested target, predecessor revision, current observed adapter/route reality, and known incompatibilities before recording a *functional* effective configuration. Functional `EFFECTIVE` MAY be recorded by a controller whose actual write/custody qualification is `NOT_ESTABLISHED`, but the record SHALL identify `controller_qualification=NOT_ESTABLISHED`, provenance, observed basis and bounded status; it SHALL NOT grant protected effects, claim agent-resistant transition control or evidence-qualified currentness. Any claim to a *protected* transition or resulting protected effect requires independently qualified owner/controller/result custody and applicable ADC/HEB/R-01/CNI/source checks. On incomplete or conflicting observations only affected routes SHALL remain `UNKNOWN_EFFECT`/held pending reconciliation; a local CAS or acknowledged request alone is not proof of external application. (S01-04/22/24; HEB-01/03; ADC-08.)

**IF13-11 — Durable transition identity.** A controller-issued transition ID SHALL bind a single canonical request fingerprint, current effective predecessor revision, exact target and source generation; retries with the same origin intent reconcile to that transition. Changed arguments or newer policy cannot reuse an earlier admission.

**IF13-12 — Transition state and partial-effect truth. States `REQUESTED`, `CHECKING`, `HELD`, `APPLYING`, `EFFECTIVE`, `FAILED`, `UNKNOWN_EFFECT`, and `SUPERSEDED` SHALL remain distinct. `EFFECTIVE` means the selected functional binding is actually observed and conditionally committed with nonnull exact snapshot and controller qualification disclosed; it never means every capability is qualified. A multi-route transition SHALL represent each affected adapter's applied/unknown/failed condition; a split between the stored revision and actual provider/model route is `UNKNOWN_EFFECT` for the affected route until reconciled, even if a local compare-and-swap succeeded. Other independent routes may continue. Blind external reexecution and false old-profile-current claims are prohibited. (S01-22; HEB-06/08; AOI-07.e.)

**IF13-13 — Cross-generation policy.** In-flight granted work and drained background operations SHALL remain bound to original authority/profile/generation and original effect intents; profile change does not revise old grants, retroactively publish held results, release unknown charges or replay an external effect.

**IF13-14 — Revocation and invalidation.** Host/harness/plugin/container/config identity change, credential/route replacement, source entitlement correction, policy change, qualifier expiry, loss of independent evidence, or explicit revocation SHALL invalidate only affected assessments; a positive cached report may not override a later qualified negative/challenge.

**IF13-15 — Site and CLI projection.** Independent consumers SHALL show requested/effective separately, truthful capability evidence class, source/coverage/freshness, transition state and recipient-safe blocked reason. A `PENDING`/`HELD` UI is not an approval, and no frontend may synthesize G3.

**IF13-16 — Disclosure and absence.** A profile read SHALL be a permitted projection from source-qualified facts. Missing profile/hidden subject/nonentitlement SHALL not leak the existence of private verifier activities, alternate work, credentials or sources via status or timing-sensitive response differences; use the adopted D-01 projection rules where exposed there.

**IF13-17 — No work/general laundering.** Switching profile names, mode, model account, issuer string or host does not clear source/work recipient restrictions, resource parent scopes, grant generation, provenance or credential separation. Data migration has an independently governed owner path (U-01), never implied by transition.

**IF13-18 — Startup unlock separation.** A normal single operator startup unlock MAY prepare enabled AEW services and model gateway under S01-31; it SHALL NOT certify G3 human origin, protected writer isolation, hard metering or activate an operator-reserved change.

**IF13-19 — Selective availability and positive functional path. A release binding meeting its typed functional prerequisites MAY become functionally `EFFECTIVE` on an unqualified shared-UID host, explicitly with `controller_qualification=NOT_ESTABLISHED`, independently observed limited functionality and protected effect gates held. General Local source inspection and no-charge deterministic mocks, and eligible Work functional model transport, need not await host protection or G3 if their *actual* effects separately satisfy governing resource/disclosure/authorization policy. A required prerequisite failure holds that binding; an optional or protected-gate failure holds only dependent effects. (S01-04/05/14/19/24; R01-43.)

**IF13-20 — Independent substitutability.** The selected interface profile SHALL freeze wire version, schema/issuer verification, field absence/null/unknown, compare-and-transition atomicity, access/negative projection, invalidation events plus reconciliation polling, and provider/consumer independent conformance fixtures. The present v0.2 schemas are candidate logical interchange, not a qualified hosted wire.

## 3. Cross-owner information flow

`O-01 attributable operator intent → classified operator-origin requirement or non-authoritative functional request → IF-13 controller-request → owner-qualified observed host/harness facts → outside-lineage capability evidence → HEB/ADC/R-01/CNI eligible effect comparison → sourced effective snapshot → existing D-01 entitled read projection → CLI / separately implemented website.`

No new security authority lies in the profile controller: it coordinates existing owner results. Every producer emits its qualified scope and source epoch so the consumer can independently compare. Lost change events require reread/reconciliation; timestamps alone neither impose ordering nor clear a qualified challenge. Profile origin/fingerprint identity differs from model operation identity and from policy decision identity.

## 4. Case behavior and semantics profile

| Input or condition | Controller action | Reader-visible outcome |
|---|---|---|
| Valid target and independently current applicable proof | Conditional effective commit after admission; only supported lanes | `EFFECTIVE` with exact revision, controller_qualification and separately scoped capability statuses |
| User selected target for operator-only protected authority change; G3 route unqualified | No protected change | `HELD`, `G3_NOT_ESTABLISHED`; old effective unchanged |
| Worker edits projection to `QUALIFIED` | Do not consume as source or issuer | Real issuer status unchanged or `NOT_ESTABLISHED` |
| Version/route/process changed after observation | Invalidate affected assessment before effect | `STALE`/held; permitted unrelated functions continue |
| Duplicate request after receipt lost | Reconcile original transition by owner-bound fingerprint | No second transition/effect for the same intent |
| Contradictory or hidden entitlement/source | Hold affected comparison, recipient-safe projection | `NOT_ESTABLISHED` or bounded denial, not counterfeit CLEAR |
| Concurrent profile changes from same predecessor | Owner conditional compare; one becomes effective at most | Other `SUPERSEDED` or `HELD`, not two winners |
| Work↔general account change with work-restricted prompt context | No implicit egress or credential migration | Recipient-specific hold; safe metadata path may continue |

## 5. Interface and release hold

Logical payloads in `02-WIRE/` provide exact versioned candidate schema and examples. Deployment-specific transport, origin verification, host observer, allowed release scope and typed protected effect execution **remain unselected and unqualified**. No D-01 GET route is changed. IF-12 and IF-10 are not defined by these records. S-DEC-01/02/03/06, G1–G4 and W1–W5 remain open; S-DEC-04/05 topology and accounting intent are recorded only at their actual evidential level.
