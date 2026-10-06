# Designer decision of 2026-10-06: harness hosting, the AEW attachment and the Lead seat (Q12)

**Status:** Decision record, governing. **Adopted** by the designer and the operator on 2026-10-06; it closes register
question Q12 (harness hosting, the operator session and native-feature integration; architecture review D-AR5). §1 to
§10 are the decision recorded as given. §11 is the lead developer's account of what it changes in AEW as built, and §12
what it leaves to later designs. Where this record and an earlier text differ on the Lead seat, the attachment or the
hosting boundary, this record wins; ADR-0005, ADR-0009 and ADR-0010 carry amendments that point here.

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
  project access". Authority is withdrawn today; access is not. What "access" means for a harness whose working
  directory is the project (read commands, the files, the dashboard) is for the designer to settle before F31 is
  built (§12).
- **Takeover interrupts children.** `aew lead takeover` revokes every in-flight invocation's credential and marks a
  Ticket waiting on one `INTERRUPTED` (ADR-0005; `lead_ops._interrupt_invocations`); invocation credentials are scoped
  to the Lead generation. The decision gives admitted invocations custody independent of the Lead attachment: losing,
  closing or taking over the attachment does not end them, and a later generation reconciles what they deposit (§7,
  §8). Cancelling them stays an explicit control operation.
- **Release refuses active invocations.** `aew lead release` is refused while any invocation is active. `aew close`
  detaches without cancelling admitted child work (§5).
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
  specification. The designer confirms the reading before F31 is built.

## 12. Not decided here

- **Where AEW's own services run.** The architecture review asked Q12 to cover the knowledge and capability service
  identities and the dashboard (ARR-69). The decision fixes the boundary those services sit inside (AEW and its
  supervisor own broker and project capabilities and the curated environment, §9) but not their processes:
  - the knowledge service principal's authority is already fixed by ADR-0013 D9 (project-bound, independent of the
    Lead generation), and its hosting goes to the hosting design under F18 with F21;
  - the dashboard server's process placement stays with F18 and F20;
  - multi-project knowledge visibility (K3), which ADR-0013 left to Q12, is not decided by it and stays with F21.
- **What "no AEW project access" covers.** §5 removes the closed attachment's AEW project access as well as its
  authority. Whether that means refusing `aew` read commands, keeping the harness from the project's files (which needs
  containment of the Lead's harness), or both, is the designer's to settle before F31 is built (decisions-due, F31).
- **Concrete mechanisms.** Command names beyond `aew open` and `aew close`, the attach handshake, how a child's
  credential outlives the generation it was admitted under, and the configuration and state isolation of the Lead's
  harness (U6) are implementation choices for F31 and the F18 hosting design, within §10's limit.
- **Exact model identifiers.** The provider and model ids, effort variants and qualification of the reference models
  through the pinned harness are F32's.
