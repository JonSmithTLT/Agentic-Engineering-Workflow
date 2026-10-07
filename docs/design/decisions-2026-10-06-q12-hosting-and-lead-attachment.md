# Designer decision of 2026-10-06: harness hosting, the AEW attachment and the Lead seat (Q12)

**Status:** Decision record, governing. **Adopted** by the designer and the operator on 2026-10-06; it closes register
question Q12 (harness hosting, the operator session and native-feature integration; architecture review D-AR5). §1 to
§10 are the decision recorded as given. §11 is the lead developer's account of what it changes in AEW as built, and §12
what it leaves to later designs. §13 is the operator's decision of the same day on what happens to in-flight work when
an attachment ends, which refines §5 and §8. §14 is the designer's clarifications of the same day, which settle what
§11 to §13 left for the designer. Where this record and an earlier text differ on the Lead seat, the attachment or the
hosting boundary, this record wins; ADR-0004, ADR-0005, ADR-0009 and ADR-0010 carry amendments that point here.

**What depends on it:** register F31 (the attachment lifecycle, to build) and F32 (the reference execution profiles);
F18, F18.1 and F18.2 (bootstrap and hosting, now unblocked); Q11 (provider and harness feature reconciliation, whose
hosting part this settles); U6 (Lead state isolation); F13 (native harness features); ledger ARR-08 and ARR-69.

## 1. The governing statement

Recorded as given:

> AEW owns project attachment and Lead authority; the harness owns model execution. An AEW attachment can be opened or
> closed independently of the harness. Closing or losing the attachment revokes AEW authority and stales its
> generation, but does not terminate the model, harness, conversational context, or already-admitted child work.
> Reattachment creates fresh AEW authority and refreshes canonical project state. GPT-6 Astra is the reference Lead,
> Laguna S2.1 the default worker, with GPT-5.4 and approved open-source workers available through normal
> execution-profile selection.

## 2. Ownership

> AEW owns the AEW project attachment, Lead-seat authority, generation lifecycle, model/profile selection policy, and
> provenance. The harness owns the interactive host and actually runs the model. The harness does not become workflow
> authority.

## 3. Reference model topology

> The hard reference target is:
>
> - Lead: GPT-6 Astra
> - Default/recommended subagent: Laguna S2.1
> - Other supported subagents: GPT-5.4 and approved open-source models
>
> Laguna is the normal worker choice because it is the strongest practical broadly available option. GPT-5.4 may be
> selected for work where its additional capability justifies higher cost/rate-limit pressure. Other approved models
> remain valid.
>
> Do not hard-code workflow semantics around these model names. AEW owns the requested/effective execution profile and
> selection policy; the harness adapter realizes that profile using its native model/configuration mechanisms and
> reports what actually ran. Model selection remains capability/profile-based and attributable.
>
> A harness-native override must never silently cause AEW to record a different model/profile from the one that
> actually executed.

## 4. The AEW attachment and the harness lifecycle are separate

> An AEW attachment is not the harness session itself.
>
> ```text
> Harness / model session
>         |
>         +-- ordinary harness/model use
>         |
>         +-- AEW project attachment
>                 - project
>                 - Lead session/seat
>                 - generation
>                 - effective execution profile
>                 - broker/project capability
> ```
>
> The harness and model may exist before an AEW attachment, remain alive after one closes, and later attach again.

## 5. `aew close`

> `aew close` means:
>
> - detach the current AEW project context;
> - revoke the current Lead's AEW capability;
> - make the current AEW Lead generation stale;
> - close/revoke the broker/project authority associated with that attachment.
>
> It does not mean:
>
> - terminate GPT-6 Astra;
> - terminate Codex/OpenCode/the harness;
> - erase the model conversation;
> - erase the model's conversational context;
> - prevent the model from continuing ordinary non-AEW work;
> - implicitly cancel already-admitted child/subagent invocations.
>
> After `aew close`, Astra may continue running in the harness with its existing conversational context. It simply has
> no AEW project authority or AEW project access.
>
> Cancellation of running child work is a separate explicit control operation.

*Wording clarified by the designer (§14.4):* read "no AEW project access" as "no AEW-mediated project access through
the detached attachment". Every project-scoped AEW surface, read and query commands included, is unavailable to that
generation. It is not a filesystem sandbox of the harness.

## 6. Reattachment

> A later `aew open`/attach may use the same still-running harness/model conversation, but it establishes:
>
> - a fresh AEW attachment;
> - a fresh Lead generation;
> - fresh broker/project authority;
> - a refresh/re-hydration from canonical AEW project state.
>
> The model's retained conversational context is advisory convenience only. Canonical AEW state wins if anything changed
> while the harness was detached.
>
> Every host attachment gets a fresh generation. Old generations never regain mutation authority.

## 7. Crash, exit and takeover

> A harness crash or host loss revokes/stales that attachment's generation but does not destroy persistent AEW
> project/session state.
>
> A replacement/restarted host attaches with a new generation.
>
> Takeover is likewise generation-based and fail-closed: once a newer generation is current, calls from the prior one
> receive stale-authority behavior.
>
> Normal model-turn completion has no effect on the AEW seat.

## 8. Child and subagent execution

> Already-admitted subagent/role invocations have independent invocation custody.
>
> Loss or closure of the Lead attachment does not automatically terminate them. They may finish and deposit their
> normal outputs/evidence. A later Lead generation reconciles the resulting state.
>
> Harness-native subagent functionality may be used only when an adapter can preserve AEW's required invocation
> identity, role, custody, execution profile, parent relationship, limits and evidence/provenance. Otherwise AEW uses
> its own dispatch path.
>
> No native harness feature may bypass AEW dispatch or create uncontrolled subagents.

## 9. The hosting boundary

> AEW/supervisor owns:
>
> - Lead attachment/session authority;
> - generation creation and revocation;
> - broker/project capabilities;
> - curated environment;
> - requested/effective execution profiles;
> - harness configuration inputs;
> - capability negotiation;
> - lifecycle observation and provenance.
>
> The harness adapter owns translation into harness-native configuration and lifecycle mechanisms.
>
> The harness owns model execution.
>
> The launcher/wrapper may perform setup, launch, supervision and teardown mechanics, but must not decide workflow
> progression, evidence acceptance, retries, gates, or other AEW semantics.

## 10. Consequences downstream

> Q12 should now be marked ADOPTED/CLOSED.
>
> Its settled boundary should unblock:
>
> - F18.1/F18.2 install/bootstrap and hosting design;
> - Q11 provider/harness feature reconciliation;
> - U6/V2 work that needed a stable session/seat model.
>
> Those downstream designs may choose concrete implementation details, but they must not reopen AEW ownership of the
> Lead seat or merge the harness lifecycle back together with AEW authority lifecycle.

## 11. What this changes in AEW as built (lead developer, 2026-10-06)

Not part of the decision; recorded so the build (register F31) starts from the differences. Each item is today's
behaviour, then what the decision requires.

- **The Lead session is the harness process.** `aew lead session -- <harness>` and `aew opencode` (ADR-0009) hold the
  Lead credential in a broker whose lifetime is the wrapped harness process. With `--acquire` the seat is taken when
  the harness starts and, if nothing is active, released when it exits; with the operator's `AEW_LEAD_TOKEN` the
  authority outlives the session, and only the broker ends with it. Neither is an attachment that opens and closes
  while the harness keeps running; the decision makes it one (`aew open`, `aew close`; §4 to §6).
- **A superseded session keeps reading.** When the broker's credential stops being current, it closes its bridge and
  the Lead's harness keeps running as a read-only session (`harness/lead_broker.py`): it can still run `aew`'s read
  commands and read the project's files. §5 says that after `aew close` the model has "no AEW project authority or AEW
  project access". Authority is withdrawn today; AEW's read commands are not. The designer settled it (§14.4): the
  detached Lead has no AEW project authority and no AEW-mediated project access through the detached attachment, so AEW's read and query commands are refused to that
  generation too; the harness is not sandboxed away from the project's files.
- **Takeover interrupts children.** `aew lead takeover` revokes every in-flight invocation's credential and marks a
  Ticket waiting on one `INTERRUPTED` (ADR-0005; `lead_ops._interrupt_invocations`); invocation credentials are scoped
  to the Lead generation. The decision gives admitted invocations custody independent of the Lead attachment: losing,
  closing or taking over the attachment does not by itself end them, and a later generation reconciles what they
  deposit (§7, §8). §13 makes what happens to them the operator's choice, with drain the default; stop now keeps
  today's behaviour as an operator choice. Cancelling them stays an explicit control operation.
- **Handoff interrupts what it does not carry.** `aew lead handoff accept` moves the invocations the offer carries to
  the new generation and interrupts every other one (`lead_ops.lead_handoff_accept`). Under §8 and §13 the invocations
  it does not carry go through the same disposition as any other ended attachment.
- **The integration custodian dies with the Lead.** The integration lease is held by an engine custody invocation
  (`integration_attempt`: no model, no harness, no credential), and the post-integration verifier is its child. A
  takeover or an uncarried handoff ends the custodian; the lease is then marked `reconcile` and its children are
  cancelled in the same transaction (ADR-0004, M4-D3 amendment; `engine/queue_ops.py`). That is stop now, applied
  automatically. §13 point 5 replaces it.
- **Release refuses active invocations.** `aew lead release` is refused while any invocation is active. `aew close`
  detaches without cancelling admitted child work (§5); §13 says what happens to that work.
- **Every control write is guarded by the current generation.** WC §5 (crash-safe authority, and its authority table)
  requires control mutations to be guarded by the current Lead generation or an equivalent stale-writer guard, and
  `require_invocation` applies that guard to child invocations today. Under §13's drain, a child admitted under an
  older generation hands in after a newer one is current. Its hand-in is only recorded and held; the write that moves a
  Ticket is the acceptance, made by the current generation (§13). The lead developer read that as satisfying WC §5's
  guard, and the designer confirmed it (§14.2): no amendment to the frozen specification is needed.
- **A lost harness holds the seat.** When the wrapper exits with an invocation active, the seat stays held and only
  `aew lead takeover` recovers it (register V2, closed with a clearer refusal). The decision makes a harness crash or
  host loss revoke and stale that attachment's generation, with a new attachment taking a new generation (§7).
- **The Lead has no recorded execution profile.** ADR-0010 pins a requested profile per invocation, and the adapter
  records the effective model and flags a mismatch. The decision makes AEW own the Lead attachment's requested and
  effective profile too, and forbids a harness-native override from silently recording a different one (§3, §4).
- **The frozen specification.** WC §8.2 reconciles in-flight assignments as `INTERRUPTED`/unknown after a crash, and
  KC §12.4 says the same of in-flight subagents. The lead developer reads these as applying when an invocation's own
  custody is lost (its supervisor or the AEW host is gone), not when only the Lead's attachment is lost: an invocation
  whose supervisor still runs has not crashed. Under that reading the decision needs no change to the frozen
  specification. The designer confirmed the reading (§14.1).

## 12. Not decided here

- **Where AEW's own services run.** The architecture review asked Q12 to cover the knowledge and capability service
  identities and the dashboard (ARR-69). The decision fixes the boundary those services sit inside (AEW and its
  supervisor own broker and project capabilities and the curated environment, §9) but not their processes:
  - the knowledge service principal's authority is already fixed by ADR-0013 D9 (project-bound, independent of the
    Lead generation), and its hosting goes to the hosting design under F18 with F21;
  - the dashboard server's process placement stays with F18 and F20;
  - multi-project knowledge visibility (K3), which ADR-0013 left to Q12, is not decided by it and stays with F21.
- **Sandboxing the persistent Lead harness.** Keeping the Lead's harness away from the project's files is a separate
  containment decision, not introduced by Q12 or F31 (§14.4).
- **Concrete mechanisms.** Command names beyond `aew open` and `aew close`, the attach handshake, how a child's
  credential outlives the generation it was admitted under, and the configuration and state isolation of the Lead's
  harness (U6) are implementation choices for F31 and the F18 hosting design, within §10's limit.
- **Exact model identifiers.** The provider and model ids, effort variants and qualification of the reference models
  through the pinned harness are F32's.

## 13. Operator decisions of 2026-10-06: in-flight work when an attachment ends

The operator decided these on 2026-10-06, after discussing with the lead developer what revoking a child's credential
does in AEW as built. Unlike §1 to §10, this section is not recorded as given: it is the lead developer's account of
decisions the operator gave in conversation, and the operator confirms its wording by approving the pull request that
adds it. They refine §5 and §8: the work is never discarded, but whether AEW keeps governing it is the
operator's decision, and a decision with the operator's name on it is one the operator actually made (the operator's
attribution rule, ADR-0006 amendment).

**What revocation means.** Revoking a child's credential does not destroy its work. Its files stay in its workspace
and its run's logs stay readable. What ends is AEW's governance: AEW refuses the child's hand-ins, so they are never
evidence, no gate passes on them and no Ticket moves on them. The work can still re-enter AEW through the gates (a new
attempt starting from it) or leave it for an ordinary development cycle.

**The disposition.** When a Lead attachment ends with children running, by `aew close`, harness crash, host loss,
takeover or a handoff that does not carry them, the operator chooses at the operator terminal what happens to them:

| Choice | The children | Their results |
|---|---|---|
| **Drain** (the default) | keep their own narrow credential, finish within a time limit, hand in, and stop | recorded as evidence and **held**: nothing moves a Ticket until a current Lead or the operator accepts it; discarding it sends the work back through the gates |
| **Stop now** | stopped at once | work product on disk and in logs; the Tickets are `INTERRUPTED` and reconciled after inspection |
| **Release to manual** | stopped, with their AEW credentials revoked together with the stop (revised, below) | work product on disk and in logs, handed to the operator outside AEW, for an ordinary development cycle |

1. **Drain is the default.** It applies whenever no operator choice is made, such as a crash or host loss with
   nobody at the terminal.
2. **Anything going wrong during a drain stops it at once.** The run is stopped immediately (the plug is pulled) and an
   error is reported to the operator. What counts as going wrong is the designer's stop set (§14.3); a legitimate
   negative result is not one of them.
3. **A Lead asks; the operator closes** (revised, below). A Lead that wants its attachment closed prompts the
   operator, who runs `aew close` and makes the choice for its children. A Lead never chooses **Stop now** or
   **Release to manual** for its children when its attachment ends: those take work out of AEW's governance, so they
   are the operator's. This governs only what happens when an attachment ends. While attached, a
   Lead keeps its existing per-invocation controls (`aew invoke cancel`, `aew harness stop`; §5's explicit control
   operation): each is a recorded Lead decision about one invocation under the Lead's own name, never the operator's.
4. **Held results are the next generation's to accept.** On the next attachment, the operator or the new Lead accepts
   the held results, which then move their Tickets under the normal rules, or discards them, sending the work back
   through the gates. A held result names the run that produced it and the generation that admitted it.
5. **The integration custodian survives an attachment's end, and its verifier drains.** The custodian is an
   already-admitted invocation, so the Lead attachment ending does not end it (§8, §14.1), and its lease stays held.
   The post-integration verifier drains like any other child, and its result is held. Nothing is published on a held
   result: publishing consumes it, so it waits for the current generation's acceptance (§14.2), even under an advance
   publish-if-clean bound to an earlier generation. On acceptance the current generation publishes under the normal
   rules. Every other way out ends the custodian as an explicit cancel does: a discard of the held result, a drain
   stop condition ending the verifier (§14.3), and the operator's **Stop now** or **Release to manual** for it. Ending
   the custodian marks the lease `reconcile` as today, and the existing `aew integrate reconcile` then retires the
   candidate and returns the entry to the queue. The queue waits meanwhile, which costs nothing while no Lead is attached, and the drain's hard
   deadline bounds the verifier. Chosen by the operator over keeping today's cancellation as a named exception to the
   drain; the designer confirmed the queue side (§14.5).

**Revised by the operator later on 2026-10-06, to agree with the F18 hosting design v0.6.** The independent review of
v0.6's ingestion found two points where v0.6 and this section disagreed; the operator decided both:

- **Only the operator runs `aew close`.** v0.6 §2.3 makes `aew close` operator-only and unreachable from the Lead host
  and its typed tools. A Lead that wants to close prompts the operator. This was the intent of point 3 ("a Lead that
  closes its attachment probably does so on the operator's decision"). At a close the operator runs, v0.6 §11.1
  requires the operator to acknowledge any running children; the drain, stop now or release to manual choice is made
  there. Drain stays the default whenever no operator choice is made.
- **Release to manual stops the run.** v0.6 §11.3 and §13 never leave a process running with a revoked credential:
  the supervisor stops it before or together with the revocation. So release to manual stops the children and hands
  their work product (files and logs) to the operator outside AEW, rather than letting them run on unattended. The
  operator chose this over asking for an exception.
- **Unchanged, and the point that matters to the operator:** `aew close` never forces the Lead's own harness session
  to close. It removes AEW authority and AEW-mediated access only (§5, §14.4; v0.6 §10).

## 14. Designer clarifications of 2026-10-06 (F31)

The designer answered §11's two readings, §13's stop conditions and §12's question on project access on 2026-10-06,
and then the queue side of §13 point 5 (point 5).
These are Q12 and F31 clarifications, not amendments to the frozen WC or KC, unless implementation evidence shows the
existing contracts behave differently. Recorded as given:

> **1. WC §8.2 / KC §12.4 crash reconciliation**
>
> Crash/interruption is scoped to the invocation whose custody is lost.
> Loss or closure of the Lead attachment does not imply that already-admitted child invocations are interrupted. A
> child whose own supervisor/custody remains valid continues running under its invocation authority.
> The existing `INTERRUPTED/unknown` reconciliation rule applies when that child's own custody is lost: e.g. its
> supervisor/owned execution context dies or another existing custody-loss condition applies.
> Add an F31 clarification:
> Loss of a parent/Lead attachment is not loss of an already-admitted child invocation's custody.
> No WC/KC amendment is needed for this interpretation.
>
> **2. WC §5 stale-writer guard**
>
> The proposed interpretation is also correct.
> A child admitted under an older Lead generation may finish later and hand in its result under its own invocation
> authority. That hand-in may create only the invocation/result/evidence records already permitted by its invocation
> contract.
> It does not perform the authoritative acceptance/control mutation that consumes the result.
> If a newer Lead generation is current, that generation performs any later acceptance, classification or
> Ticket/control-state transition.
> Thus:
> result production/hand-in is invocation authority; result acceptance and workflow advancement use current control
> authority.
> WC §5 remains intact. No amendment is needed unless the current implementation couples hand-in directly to a control
> transition.
>
> **3. Drain stop conditions**
>
> Use the proposed stop set, with two additions:
>
> - loss of a custody/lease/integrity condition required for that invocation to continue safely;
> - inability to durably record or verify the drain/result state.
>
> The complete intended set is therefore:
>
> - an existing supervisor stop condition, including abnormal harness/process exit where applicable;
> - execution deadline or step limit;
> - containment failure;
> - supervisor failure;
> - relevant custody/lease/integrity failure;
> - drain hard deadline;
> - operator stop;
> - durable result/drain-state recording or integrity failure;
> - any unclassified fault, fail closed.
>
> These are not drain failures by themselves:
>
> - a new Lead generation attaching;
> - the old Lead generation becoming stale;
> - a project/control revision changing;
> - a child completing with a legitimate FAIL, BLOCKED, inconclusive or other domain result;
> - a result requiring later Lead classification.
>
> Those results are recorded and held. A valid negative result is not an infrastructure failure of the drain.
>
> **4. Meaning of "no AEW project access" after `aew close`**
>
> Use a third formulation.
> After `aew close`, the stale/detached Lead has:
> no AEW project authority and no AEW-mediated project access through the closed attachment.
> That means all project-scoped AEW surfaces for that Lead generation are unavailable, including AEW read/query
> commands as well as mutations.
> It does not mean the persistent harness is filesystem-sandboxed away from the project.
> The harness/model may remain alive, retain its conversation/context and, if its ordinary harness permissions allow
> it, continue normal non-AEW filesystem/git/editing work in the project.
> Sandboxing the persistent Lead harness away from project files is a separate containment decision and is not
> introduced by Q12/F31.
> Please replace wording that simply says "no AEW project access" with "no AEW-mediated project access through the
> detached attachment" so we do not imply a filesystem containment guarantee we have not adopted.

>
> **5. The queue side of §13 point 5**
>
> Confirmed. Use the first interpretation.
>
> 1. Pre-authorized publish does not survive a Lead generation change.
>
> A `publish-if-clean` or equivalent advance publish authorization is bound to the generation/authority context that
> granted it.
> When that Lead attachment ends:
>
> - the integration custodian survives;
> - the integration lease remains held;
> - an already-started post-integration verifier may drain;
> - its result may be recorded and held;
> - but the old generation's publish authorization is stale.
>
> Nothing publishes merely because the held result is clean.
> The current Lead generation must inspect/accept the held verification result and issue whatever current-authority
> publish decision is required.
> A clean held result does not inherently require verification to run again; if the current generation accepts that
> result as still applicable, it may proceed under fresh current authority.
>
> 2. All non-success exits end the custodian and reconcile the integration attempt.
>
> While a verification result is merely held awaiting current authority, the custodian remains alive and the
> integration lease remains held.
> Once the path is abandoned, however, the custodian ends as an explicit cancellation would.
> This includes:
>
> - the current authority discarding/rejecting the held result;
> - a verifier/drain stop that prevents obtaining a usable held result;
> - operator `stop now`;
> - operator `release to manual`;
> - another explicit abandonment/cancel decision.
>
> On that transition:
>
> - terminate/cancel the integration custodian;
> - do not silently release the integration lease as though integration succeeded;
> - mark the lease/attempt as requiring reconciliation;
> - use the existing `aew integrate reconcile` path;
> - reconciliation retires the integration attempt and returns the Ticket to the appropriate queue state under the
>   existing contract.
>
> This is preferable to retaining the lease and automatically rerunning verification.
> An automatic rerun would introduce a new retry/recovery policy, could retain a load-bearing integration lease
> indefinitely, and blurs the distinction between a held valid result and an integration attempt whose completion path
> has failed.
> If a future design wants a bounded "retry verifier while retaining integration custody" operation, it should be an
> explicit separately governed recovery action rather than F31's default behavior.
> So the queue-side rule is:
> Lead detach preserves the custodian and lease only while already-admitted post-integration work drains and its result
> awaits current authority. Fresh publish authority is always required. If that result/path is discarded, stopped, or
> manually abandoned, the custodian is cancelled and the integration attempt goes through normal reconcile; F31 does
> not automatically rerun verification while holding the lease.

**The condition in point 2, checked (lead developer, 2026-10-06).** A child's hand-in does not move a Ticket in AEW as
built. `submit` (`engine/evidence_ops.py`) validates the submission and writes an evidence record only; the Ticket
moves in a separate Lead operation that consumes it (for example `review ingest`, which checks the Ticket is
`REVIEW_PENDING` and applies the transition). So no WC §5 amendment is needed. §5's quoted wording stays as given;
everywhere else this record and its amendments use point 4's formulation.
