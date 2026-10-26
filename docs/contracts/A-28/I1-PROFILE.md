<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-28
source: 30-stages/STG-06-I1-lead-seat-lifecycle/adopted/o01-0.3-i1/I1-PROFILE.md
source-sha256: 416bec868e91bbb60bed689964e73a09db132fe34d224c4cb3e5ab76b44f5b59
edits-sha256: none
-->

# I-1: the HEB Lead seat lifecycle, selection profile (PROPOSED contract pass, revision 2.1, 2026-10-21)

**Wire:** O-01 `o01-command-0.3-candidate`, in `wire/`. It is A-25's 0.2 wire plus six action types, generated from A-25's bytes by `tools/build_i1_wire.py`.
**Stage:** `STAGE.md`. **Why I-1:** map v1.19 section 9.
**Revision 2.1** adds one line for the confirmation's side note (`reviews/2026-10-21-I1-confirmation-r2.md`, I1C2-N1), in I1-05. **Revision 2** answers review round 1 (`reviews/2026-10-21-I1-review-round-1.md`, `Review: FINDINGS at 7084e11`) at design altitude. `CHANGES-r2.md` maps each finding to its answer.
**How to read it:** each rule states an outcome: what must hold, who owns it, what is refused, and the adopted rule it must not contradict. Text marked **Candidate** is a starting point for the build. The gate, and the builders, may meet the outcome another way (the operator's decision on design altitude, 2026-10-21).

## I1-00. What this pass selects, and what it inherits

- **Six action types,** with HEB as the sole admitting owner of each:

  | Row | Action type | Origin class (CS-02) | Registry `protection_direction` |
  |---|---|---|---|
  | L08 | `SWITCH_ACTIVE_WORK_CONTEXT` | current Lead session (I1-01) | `PRESERVING_OR_INCREASING` |
  | L11 | `PREPARE_CONTEXT_HANDOFF` | current Lead session (I1-01) | `PRESERVING_OR_INCREASING` |
  | L14 | `LEAD_RELEASE_OWN_SEAT` | current Lead session (I1-01) | `REDUCING` |
  | L05 | `HANDOVER_LEAD` | protected G3 (CS-06) | `PRESERVING_OR_INCREASING` |
  | L06 | `TAKEOVER_LEAD` | protected G3 (CS-06) | `PRESERVING_OR_INCREASING` (it fences, then establishes a successor) |
  | L13 | `CANCEL_PENDING_LEAD_HANDOFF` | protected G3 (CS-06) | `REDUCING` |

- **Everything in A-25 is inherited unchanged:**
  - the ten 0.2 action types, their targets and their registry rows;
  - the command-set rules CS-01 to CS-09;
  - the receipt, the owner-operation GET, and the reason codes. `ReasonCode` stays closed; each new owner reason maps to an adopted code (`wire/refusal-reasons-0.3.json`, I1-11).
- **The version is an exact successor,** as A-25's profile rule 2 sets for 0.2:
  - a 0.3 endpoint refuses a 0.2 header or body, and never transforms it;
  - a provider may host a 0.2 endpoint separately, unchanged;
  - no protected action is activated by version support alone.
- **The G3 consent is A-26's.** The rendering covers every leaf of the new targets (G3-03), so the operator sees the exact predecessor, successor, classification and validity they approve.

## I1-01. The origin of the three delegated rows: the current Lead's authenticated session

**The ruling:** L08, L11 and L14 use A-25's `CURRENT_SUCCESSOR_GENERATION` origin class: CS-07's authenticated session, with both proof slots `null`.
- **The check:** the session principal is issued by a trusted authenticator outside the request body. It must equal `actor_ref`, or the result is `ORIGIN_NOT_ESTABLISHED`, decided before any HEB state is read.
- **Then HEB checks** that the principal is the Lead of the subject attachment's current generation. Otherwise the result is `ACTOR_NOT_CURRENT_LEAD`, allocated.
- **These rows share CS-07's origin proof only** (review I1R1-5). Each has its own owner check, and A04 keeps CS-07's unchanged: HEB's current successor Lead, `ACTOR_NOT_CURRENT_SUCCESSOR`.

**Why not `CURRENT_DELEGATED_GRANT`** (the classification's label for these rows):
- That class proves a delegation bound to the exact intent's digest (A-24 SW-04). An ADC issuer would then mint a new delegation for every context switch.
- **The Lead acting on its own seat has no separate grant to prove.** Its authority is its own seat, plus grants HEB already holds facts for. HEB reads those as owner state after origin.
- The classification's `DELEGATED_GRANT` means "no operator origin needed"; which wire class carries that is this pass's to choose. The classification stays proposed, and is not changed by this.

**What follows for an unqualified host** (this corrects map v1.19 section 9, which said these rows are "usable before G3 qualifies"):
- **They need no consent of their own.** But they act on an HEB-qualified Lead generation, and establishing one takes `ATTACH_LEAD` or `REATTACH_LEAD`, which are G3-protected.
- **So on a host where G3 is not qualified,** the wire refuses them, as A-25 refuses its protected rows. The functional CLI serves the preview, as A-25's profile already says.
- **What they save once G3 qualifies:** a G3 approval for every routine switch, handoff note and release.
- Registry value: `ONLY_WHEN_CURRENT_LEAD_SESSION_ACTUALLY_QUALIFIES`.

**Sets (CS-02):**
- These rows may share a set with each other and with A04.
- They never share one with a protected row.
- **A target outside the Lead's current grants is an owner refusal, never a promotion** (I1-02).

## I1-02. `SWITCH_ACTIVE_WORK_CONTEXT` (L08)

**Outcome:** the Lead of the current generation makes another of its granted assignments the active work context.
- **The target names** the expected current context (or `null` when none is active), and the new context: `work_ref`, `work_revision`, and the ADC `grant_ref` it runs under.
- **HEB admits it only if:**
  - the generation is current and not fenced;
  - the expected context is the active one (`CONTEXT_STALE` otherwise);
  - ADC's current grant fact names this generation and this exact work and revision (`TARGET_NOT_GRANTED`, or `GRANT_NOT_CURRENT` when the grant has expired or been revoked).
- **Switching to the context already active** confirms with no change.

**What must hold after the switch** (adopted HEB guarantees, restated as the outcome the gate checks):
- **HEB-02.c:** the Lead's writable effects are exactly the new assignment's. They never span both, and never exceed the grant.
- **HEB-02.d:** the previous assignment's unfinished work is preserved. A clean working tree is not a precondition.
- **HEB-03.f:** the previous assignment's background processes keep their own isolation, and gain no access to the new one.
- **HEB-01.i:** nothing agent-writable in either assignment enables or enlarges a capability during the switch.

**Crossing a grant or scope is refused** (`TARGET_NOT_GRANTED`). The Lead gets a new grant through ADC's own operations, never through a switch.

**Candidate:** the switch is one HEB state transition recorded with the generation, so an owner-operation read shows which context was active when.

## I1-03. `PREPARE_CONTEXT_HANDOFF` (L11)

**Outcome:** the Lead records a context handoff package, for the operator or for a named successor to read later.
- **The target names:**
  - the context it describes: the expected active `work_ref` and `work_revision`;
  - the audience: `audience_ref`, with `null` meaning the operator.
- **HEB issues the package** as the result of an owner operation. It has its own identity, the generation that made it, a creation time and a finite validity.
- **Its contents are references to owner-issued facts,** each carrying its own owner's source stamp: WIS work facts, K-01 knowledge disclosures with their provenance, and HEB's own context state. HEB stamps only HEB's facts (A-25's owner pins, OP-01). A copy inside the package is never the authority for a fact.

**What it never does:**
- **It transfers no grant,** and changes no seat.
- **It creates no reliance or acceptance.** Delivering a package is not qualified acceptance (K-01; L12's owner text).
- **It is not `aew lead handoff`,** and does not alias it (the catalogue's L11 owner text). That CLI command keeps its meaning.

**Refusals:** `CONTEXT_STALE`, or `GENERATION_FENCED`. A referenced owner fact that is unavailable holds the request (`SOURCE_FACT_UNAVAILABLE`, mapped to `SOURCE_UNAVAILABLE`): the package is never issued with a gap it does not show.

**How it is read** (review I1R1-2):
- **On the 0.3 wire:** the package's identity is its `(HEB, operation_ref)`. A-25's owner-operation GET shows that it was issued (I1-08's mapping), not its contents.
- **Its contents:** a later read pass (L12, a D-01 read outside this pass).

## I1-04. `LEAD_RELEASE_OWN_SEAT` (L14)

**Outcome:** the Lead of the current generation gives up its seat.
- **The target names** the expected seat version (`SEAT_STALE` otherwise).
- **HEB fences the generation:**
  - it takes no new protected effect;
  - ADC-08.c then denies its grants new effects, unless they are reaffirmed under a later generation (A04).
- **The seat becomes vacant.**

**Children follow the governing default** (HEB-07.i):
- An eligible admitted child with no operator-selected disposition follows the bounded-drain default.
- Its results are held for current authority. They are never accepted under the released generation (HEB-07.e).

**What it cannot do** (HEB-07.b: no Lead self-certifies a close):
- **It selects no disposition:** the target has no disposition field.
- **It closes no attachment record.** Stop-now, release-to-manual and the attachment's close stay the operator's, through `CLOSE_ATTACHMENT` (L04, protected).
- **It hands the seat to nobody.** Only L02, L03, L05 or L06 establish a next generation.

**Refusals:** a second release of a fenced generation is `GENERATION_FENCED`, allocated.

## I1-05. `HANDOVER_LEAD` (L05): an offer, then the successor's claim

**Outcome:** with the operator's consent, the seat passes from the current generation to a named successor, which then takes it.

**The offer.** The target names:
- the predecessor's seat version;
- the successor Lead;
- its profile binding;
- ADC's transition classification;
- the offer's finite validity.

The operator's G3 consent covers all of it. HEB admits the offer only if:
- **the predecessor is current:** its seat version matches, and it is not fenced (`PREDECESSOR_STALE`);
- **there is no other open offer** on the seat (`OFFER_ALREADY_OPEN`);
- **the successor differs from the current Lead,** and the profile binding is valid (`SUCCESSOR_INVALID`, `INVALID_INSTALLATION_OR_PROFILE`);
- **ADC's classification** of the transition, issued by ADC or by a previously authorized trusted platform rule, is current and `ROUTINE`. The record the target names must be ADC's, and **ADC's current classification of the transition** (its newest) must be `ROUTINE` too (review I1R1-1):
  - `CLASSIFICATION_NOT_ROUTINE` means a takeover is needed (L06);
  - if it is unavailable, the request holds (`CLASSIFICATION_UNAVAILABLE`);
  - a label from either Lead is not a classification (ADC-02.l; `CLASSIFICATION_ISSUER_INVALID`).

An admitted offer is an HEB operation in state `OFFERED`. **The current Lead keeps its seat and works on** until the claim.

**An offer or reservation expires by time** (review I1R1-4): once its validity passes it is `EXPIRED`, whether or not anyone tries to claim it. An expired offer is not open, so it does not block a new one.

**Establishing a new generation on the seat closes the old generation's open offers and reservations** (`CANCELLED`; review I1C2-N1). That holds whether a claim establishes it, or A-25's `ATTACH_LEAD` or `REATTACH_LEAD`. So an offer left over after a release and a reattach blocks no new offer, and reads as I1-08's cancelled row.

**The claim** is the step that completes the handover. **Candidate:** HEB's own attach path, not an O-01 command. It is made under the operator's one consent, with no second approval. It succeeds only if:
- **the claimant is the offer's named successor,** proven by the same trusted session authenticator as I1-01;
- **the offer is still `OFFERED` and unexpired;**
- **the predecessor generation is unchanged, and no fence has been applied to it other than its own Lead's release (L14)** (compare-and-fence; review I1R1-1). A takeover's fence closes the offer (I1-06), and any other fence defeats the claim;
- **ADC's current classification of the transition is `ROUTINE`:** its newest, not only the record the offer named. A trust-revocation finding at any time before the claim defeats it (A-19 O01-13: a protected negative observation fences a stale approval at the effect boundary);
- **the successor's profile binding is valid, and its HEB-01.c qualification is current, at the claim** (`INVALID_INSTALLATION_OR_PROFILE`; A-19 O01-05; review I1R1-3);
- **G3's qualification still holds at the claim.** The claim is the consumed consent's effect, so G3-12's "only while" applies at the claim as well as at the offer.

**When the claim succeeds,** in one atomic step:
- the predecessor generation is fenced, and exactly one successor generation is established;
- the offer becomes `CLAIMED`;
- the successor's child grants stay inactive until A04 reaffirms them (ADC-02.i);
- the predecessor's children follow HEB-07.i.

**When it fails,** the offer is unchanged. It stays `OFFERED` until it is claimed, cancelled (L13) or taken over (I1-06), or until it expires.

**The functional preview:** an unqualified host's functional offer and accept stay outside this wire. They mint no successor grant (the catalogue's L05 owner text).

## I1-06. `TAKEOVER_LEAD` (L06)

**Outcome:** with the operator's consent, the current generation is fenced at once, without its cooperation, and the seat is reserved for a named successor.
- **The target names** the predecessor's seat version, the successor Lead, its profile binding, ADC's transition classification (or `null`), and the reservation's finite validity.
- **HEB checks that the predecessor is current** (`PREDECESSOR_STALE`). Taking over a generation that is already fenced is `PREDECESSOR_STALE`: the seat is vacant, so use `REATTACH_LEAD`.

**The fence never waits for a classification.** Fencing is reducing, and a compromised Lead must be stoppable. So:
- **At admission:** the predecessor is fenced, and the operation is `RESERVED` for the successor.
- **Admitting a takeover closes every open offer on the seat** (`CANCELLED`; review I1R1-1). This only reduces, as I1-07 does. The operator's later decision fences the earlier approval (A-19 O01-13).
- **The claim:** the successor claims as in I1-05: the named successor, unexpired, the same generation, its profile and G3's qualification current. For a reservation, the takeover's own fence is the one fence allowed. A reservation needs no routine classification. Exactly one successor generation is established.
- **What ADC's classification decides,** when it arrives, at admission or later. HEB applies ADC's current classification, whenever ADC issues it:
  - **trust revocation:** the predecessor's descendants are stopped or contained (HEB-07.j), and A04 can reaffirm nothing (ADC-02.f);
  - **routine:** descendants follow HEB-07.i, and A04 may reaffirm eligible grants;
  - **not available:** there is no trust-revocation finding, so HEB-07.i's default applies, and A04 holds until a classification exists (A-25's L03 rule).
- **An interactive same-UID terminal is not origin.** Only the G3 consent is (the catalogue's L06 owner text).

## I1-07. `CANCEL_PENDING_LEAD_HANDOFF` (L13)

**Outcome:** with the operator's consent, HEB closes an open offer (I1-05) or reservation (I1-06) before it is claimed.
- **The target names** the pending operation's `operation_ref`. Its owner is always HEB. **`subject.generation_ref` is the generation the pending operation was made on** (review I1R1-6). A mismatch is `OFFER_UNKNOWN`, so a cancel after a claim still meets `TRANSFER_ALREADY_ADMITTED`.
- **If it is still `OFFERED` or `RESERVED`,** HEB makes it `CANCELLED`, and no claim succeeds after it.
- **Cancelling a reservation does not unfence the predecessor:** a cancel only reduces. The seat stays vacant, for `REATTACH_LEAD`.
- **A claimed operation is not erased** (the catalogue's L13 owner text). Cancelling one is `TRANSFER_ALREADY_ADMITTED`, allocated, and the transfer stands.
- **Other refusals:** an expired or cancelled operation is `OFFER_CLOSED`. One the operator's recipient cannot see is `OFFER_UNKNOWN`.
- **Requested is not confirmed:** the cancellation is HEB's operation result, read from the owner (CS-08), never the carrier's receipt.

**Why HEB owns it** (assigned by the designer, the classification's `*`): the offer and the reservation are HEB operations on HEB's seat. ADC's classification is an input HEB reads, as A04 splits HEB's transition from ADC's grants. No ADC grant changes.

## I1-08. HEB's owner facts this pass adds

HEB issues each of these, with its own source stamp (OP-01):
- **per attachment generation:** whether it is fenced, its seat version and its Lead;
- **the active work context:** `work_ref`, `work_revision`, `grant_ref`, or none;
- **each handoff package** (I1-03);
- **each pending offer or reservation,** with its state (`OFFERED`, `RESERVED`, `CLAIMED`, `EXPIRED`, `CANCELLED`), its successor and its validity.

ADC issues the grants and the transition classification; HEB only reads them. How either stores them is the build's.

**What the 0.3 wire shows of them** (review I1R1-2). The 0.3 owner-operation GET carries one `IntentResult` per operation and nothing else, so these facts are not readable on it. Reading them is a later pass:
- the package's contents: L12;
- an offer's successor and validity, and the seat facts: a D-01 change;
- the Lead and generation in place now: already D-01's attachment read (L07, `/v1/read/attachments`).

Each operation's `IntentResult` reports its state through A-25's existing fields, so no reading can take an open offer for a handover that happened:

| Action | At admission | Later |
|---|---|---|
| L08, L14 | `ADMITTED`, `EFFECT_CONFIRMED` | — |
| L11 | `ADMITTED`, `EFFECT_CONFIRMED`: the package is issued; its identity is the `operation_ref` | — |
| L05 | `ADMITTED`, **`EXECUTING`**: the offer is open, and nothing has moved | claimed: `EFFECT_CONFIRMED`. Expired: `FAILED_CONFIRMED_NO_EFFECT`. Cancelled, or closed by a takeover: `FAILED_CONFIRMED_NO_EFFECT` with `cancellation_state: CANCEL_CONFIRMED` |
| L06 | `ADMITTED`, `EFFECT_CONFIRMED`: the fence, the effect that cannot wait | the successor's generation shows on D-01's attachment read. A cancelled reservation: `cancellation_state: CANCEL_CONFIRMED`, and the fence's `EFFECT_CONFIRMED` stands |
| L13 | `ADMITTED`, `EFFECT_CONFIRMED`: the cancellation took effect | the cancelled operation reports as its own row says |

`residual_remote_effect` and the rest follow A-24 SW-06 and CS-09, as for every action.

## I1-09. Ordering and atomicity

- **One admission path:** origin, then owner state, then at most one owner effect per member (CS-05). No HEB state is read before origin.
- **Every seat transition is compare-and-fence atomic** in HEB's linearizable state: the switch, the release, the fence at takeover, and the claim. This is A-25's attach and reattach rule, applied to these rows.
- **A lost response is reconciled** from the original `(HEB, operation_ref)`, never by redispatch (CS-04, CS-08). This includes a claim whose result was lost.

## I1-10. The wire

`tools/build_i1_wire.py` generates `wire/` from A-25's frozen bytes:
- **`o01-command-0.3.schema.json`:** A-25's schema, with six Intent branches and six Target definitions added, and the version constant `o01-command-0.3-candidate`.
  - Each Intent branch fixes `authority_class` and `owner_hint`, and requires a non-null `subject.attachment_ref` and `subject.generation_ref`: the seat it acts on. The target does not repeat them.
  - The three delegated rows also require both proof slots to be `null` (CS-07).
  - **`Intent.predecessor` keeps A-25's meaning,** as for every action, and the set digest covers it. This pass gives it no new meaning. HEB decides staleness for these rows from the target's expected fields: the context, the seat version, and the predecessor's seat version (I1-02 to I1-07).
- **`openapi-o01-0.3.yaml`:** the same definitions as OpenAPI components. The script checks that the two forms are equal.
- **`action-registry-0.3.json`:** A-25's ten rows, unchanged, plus six.
- **`refusal-reasons-0.3.json`:** A-25's map, plus the six actions' owner reasons.
- **`PREDECESSOR-PINS.json`:** the sealed A-25 ZIP's digest, and each member read from it. `SHA256SUMS` covers the folder, and `--check` regenerates and compares.

## I1-11. Refusals and holds

- **Each owner reason in I1-02 to I1-07 maps to an adopted reason code.** The map is complete and fail-closed: a reason outside it is a defect, never a default code. (Each reason's mapping is in `wire/refusal-reasons-0.3.json`.)
- **Refusals before the owner step allocate nothing,** and carry `operation_ref: null`.
- **An owner refusal is an allocated operation,** with HEB's `operation_ref`.
- **A hold allocates nothing** (A-24 SW-06). Unknown owner state, an unavailable classification for L05, and an unavailable referenced fact for L11 are holds.

## I1-12. Not claimed

- **This selects interface architecture.** It qualifies no host, builds nothing, and activates no action. Protected rows stay held wherever G3 is not established (O01-10). The delegated rows need a qualified Lead generation (I1-01).
- **D-01's owner-operations index** lists A-25's ten actions only, so I-1's operations are found by `(HEB, operation_ref)` until a D-01 change lists them (review I1R1-2).
- **The claim's mechanism is a Candidate** (I1-05). So are how HEB enforces HEB-02.c, HEB-02.d, HEB-03.f and HEB-01.i, and how it stores its facts.
- **Out of scope:** L12, D-01 changes, the contained Lead's layout (STG-05 CS-4), and A04, which is unchanged.
