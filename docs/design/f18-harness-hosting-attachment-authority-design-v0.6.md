# F18 — Harness Hosting & Attachment Authority Design

**Version:** v0.6  
**Date:** 2026-10-06  
**Status:** **ADOPTED — governing F18 harness-hosting / attachment-authority design**  
**Authority basis:** Q12 adopted/closed; T9 v0.3 accepted implementation input

This document defines the **F18 harness-hosting and attachment-authority contract**. It does **not** replace the previously adopted install/bootstrap design that governs `aew init` and `aew doctor`; that design remains authoritative for those surfaces.

The two documents sit alongside one another:

- the adopted install/bootstrap design governs installation, `aew init`, `aew doctor`, preflight/bootstrap UX and related setup behavior;
- this document governs Lead hosting, security principals, attachment/generation lifecycle, gateway/attestation, broker binding, host modes, detach/drain behavior and harness qualification.

Where the two touch, this document supplies the hosting/authority invariants that `aew doctor` and bootstrap implementation must validate. It does not silently delete or supersede existing `init`/`doctor` requirements.

This document does not reopen Q12, the typed Lead surface, custody, workflow authority, Knowledge/Evidence authority, or recovery semantics.

## 0. Adoption disposition and final amendments

F18 harness-hosting / attachment-authority v0.6 is **ADOPTED** alongside the existing adopted install/bootstrap design.

The second review closed the remaining deployment-boundary issues, and the final review identified one new architectural concentration: the request gateway/attestor is now a **load-bearing security component**. This adopted design makes that explicit and settles its custody, availability and broker-binding contract.

Final amendments incorporated:

1. broker authorization is bound server-side to an attested response's exact single-use `tool_call_id` + argument hash; the model-controlled host never holds or chooses an authorization token;
2. the gateway runs under its own security principal, holds provider credentials, stores only verdict metadata/hashes, and fails closed for both Lead and workers;
3. managed harness/worker principals are network-confined so provider endpoints are reachable only through the gateway;
4. request-surface attestation distinguishes stable/templated system + developer instructions and tool definitions from untrusted dynamic message content;
5. B0 includes the ergonomic UID/group/ACL setup needed to keep operators from collapsing the boundary back to same-UID operation;
6. `aew open` refuses a full attachment when the harness and operator/supervisor principals collapse to the same unsupported identity;
7. development-mode outputs are explicitly tagged `guarantee: dev` and are ineligible for production-grade Evidence/Knowledge admission unless re-established under an accepted production path;
8. the protected-set treatment of T5 is narrowed to supervisor-owned manifest/reference metadata plus hash verification of content-addressed map artifacts; the maps themselves do not become authority;
9. document hygiene/version references are corrected.

The model capability/cost assumptions for GPT-6 Astra and Laguna S2.1 remain reference deployment assumptions to qualify empirically, not architectural facts.

---

## 1. Governing decision

AEW owns:

- project attachment;
- Lead-seat authority;
- generation lifecycle;
- canonical control state;
- requested/effective execution-profile binding;
- broker/project capability;
- provenance and authoritative workflow mutation.

The harness owns:

- the interactive host;
- model execution;
- native UI and execution mechanisms that pass adapter qualification.

An AEW attachment can be opened or closed independently of the harness/model conversation.

Closing or losing the attachment revokes AEW authority and stales/revokes its generation. It does **not** inherently terminate:

- the harness;
- GPT-6 Astra or another Lead model;
- the model conversation;
- retained conversational context;
- already-admitted child invocations.

Reattachment always creates **fresh AEW authority** and refreshes canonical AEW state.

### 1.1 Reference topology

| Role | Reference target | Contract meaning |
|---|---|---|
| Lead | GPT-6 Astra | Hard reference target unless the operator changes it; qualification remains empirical. |
| Default worker | Laguna S2.1 | Normal delegated-role target. |
| Worker alternatives | GPT-5.4 and approved open-source models | Selected through normal attributable execution profiles. |
| Lead host | Long-lived interactive harness | May outlive an AEW attachment. |
| Worker host | Private AEW-custodied invocation/run instance by default | Native delegation is not baseline authority. |

No workflow rule branches on these model names. AEW selects and attributes profiles; the adapter realizes them through harness-native mechanisms.

---

## 2. Non-negotiable authority boundary

### 2.1 Security-principal separation is required

A same-UID deployment in which the model-controlled Lead host and the AEW supervisor/operator authority run with the same effective filesystem/process authority **does not satisfy this contract**.

Moving canonical files outside the repository is insufficient if the Lead host can still read/write them as the same OS user. Likewise, a TTY/PTY check is not an absent capability.

A supported deployment therefore requires a kernel-enforced separation such as:

- a dedicated OS identity for the model-controlled harness plus supervisor-owned state under a distinct identity;
- an SELinux-confined domain with equivalent guarantees;
- or another mechanism that demonstrably prevents the Lead-host identity from mutating supervisor-owned authority state or invoking operator-only lifecycle endpoints.

F18-B's first deployment exit criterion is a negative test executed as the **actual Lead-host identity** on the real Rocky 8 deployment model.

Deployments that cannot pass that test are unsupported for full AEW attachment and must say so explicitly.

### 2.2 Canonical protected set

The supervisor-owned protected set includes, at minimum:

- canonical control/workflow state;
- execution policy, including steering/recovery/authority-affecting configuration;
- support manifests and harness qualification/conformance results;
- canonical Evidence and evidence-association records;
- admitted Knowledge records and admission history;
- supervisor-owned T5/map manifest pointers, identities and expected artifact hashes; T5 map content itself remains non-authoritative and content-addressed artifacts are verified by hash before use;
- hot and cold generation/authority history;
- broker configuration, capability material and operator-only endpoint configuration;
- gateway/attestor policy, verdict metadata and request-binding state;
- adapter qualification/configuration records that can change what counts as supported or authorized.

Each protected class has a negative write test from the actual Lead-host security principal.

A project-tree read-only projection is allowed only as a derived cache/projection. Anything that consumes it as authoritative must verify it against the supervisor-owned canonical source or a supervisor-issued digest/identity before use.

### 2.3 Operator-only lifecycle capability

The following are operator-only:

- `aew open` / attach;
- `aew close` / detach;
- takeover / seat replacement;
- any operation that increases attachment authority.

Operator authority is enforced by the security-principal boundary and an operator-only supervisor endpoint, such as a Unix-domain socket whose peer credentials are verified against the authorized operator identity.

These operations must not be reachable from:

- the Lead-host security principal;
- worker security principals;
- AEW typed model tools;
- recovery `cli` escapes.

A command name, TTY presence or user-interface convention is not the authority boundary.

`aew open` MUST detect the effective deployment identities. A full production attachment is refused when the Lead-host principal is the same unsupported security principal as the operator/supervisor authority boundary. Development/test bypasses, if any, must be explicit, labeled and unable to claim the production F18 guarantee.

---

## 3. Support identity and qualification

A supported harness is identified by a qualified tuple, not a product name:

```text
adapter
+ artifact/binary content identity
+ reported version
+ protocol/schema hash
+ request-surface probe identity
+ conformance-suite version/hash
+ conformance result
```

### 3.1 Content identity

Version strings are descriptive only.

The support manifest MUST record cryptographic digest(s) for the qualified harness artifact/binary and any support-critical companion artifact whose substitution could alter the model-visible surface.

F18.1 defines identity and qualification. F18.3 / ADR-0014 later defines signed release-bundle authenticity and `release_epoch`.

### 3.2 Versioned conformance artifact

The harness conformance suite is a versioned support artifact.

A new Codex/OpenCode pin is supported only by running the same declared suite (plus pin-specific additions where required) and publishing the resulting qualification identity.

Product-wide statements such as “Codex supports direct AEW tools” are prohibited.

---

## 4. Load-bearing request gateway, attestation and broker binding

The request gateway/attestor is a **load-bearing security component** of the F18 production architecture.

It is not telemetry middleware. It is part of the authority chain that ensures the model receiving AEW context and the tool call reaching the broker are the model/surface that AEW actually qualified.

### 4.1 Gateway threat model and custody

The gateway:

- runs under its own security principal, distinct from the model-controlled harness/worker principal;
- holds the provider credential(s);
- exposes only a gateway-scoped client credential/interface to the harness;
- is the only permitted network path from a managed harness/worker to qualified provider endpoints;
- parses outbound requests and provider responses for qualification/binding purposes;
- writes attestation verdict metadata and broker-binding state;
- does **not** become workflow authority and cannot accept evidence, advance Tickets, release leases or make gate decisions.

Provider credentials MUST NOT be present in:

- the Lead-host environment;
- worker-host environments;
- model-readable files;
- harness-native shared login/config state.

Verdict storage records only the minimum authority metadata needed for enforcement, such as:

- request ID;
- generation/session identity;
- qualified adapter/pin identity;
- provider/model/profile identity;
- normalized surface digests;
- verdict/reason;
- response/tool-call binding metadata;
- timestamps/expiry.

It MUST NOT persist plaintext request or response bodies merely for attestation, so the verdict store does not become a second corpus of project data. Separate explicitly-authorized diagnostics may capture sanitized fixtures under their own retention rules.

### 4.2 Network enforcement

For managed Lead and worker execution, provider egress is deny-by-default.

The deployment must enforce that the model-controlled harness/worker principal cannot reach provider endpoints directly and can communicate only with the gateway path required by its qualified profile.

The exact kernel/network mechanism is deployment-specific, but it must be independently testable (for example, uid/domain-scoped firewalling or equivalent namespace/SELinux enforcement).

Acceptance includes a negative direct-connection attempt executed as the actual harness/worker principal.

### 4.3 Authoritative fact sources

Effective facts MUST name their source.

Order of preference:

1. gateway observation of the actual outbound request and provider response;
2. adapter observation of the actual harness request immediately before gateway submission;
3. provider response metadata where it independently confirms model identity;
4. harness-reported effective configuration as supporting telemetry.

Model self-report is never authoritative.

### 4.4 Normalized request-surface contract

Not every byte of a model request is expected to be stable.

The support manifest for each qualified pin defines a request-surface parser and normalized surface contract that partitions the request into:

**Attested structural surface**
- tool/function definitions and schemas;
- system instruction blocks;
- developer instruction blocks;
- harness-native capability/delegation declarations;
- support-critical injected skill/instruction blocks;
- provider/model/profile routing fields;
- other pin-specific fields that can alter model capability or authority.

**Allowed variable slots**
- explicitly named fields within the structural surface whose values legitimately vary, such as date/time, working directory identity, bounded run identifiers or qualified compaction metadata;
- normalization rules are explicit per pin and included in the support manifest.

**Untrusted dynamic content**
- operator/user messages;
- assistant history;
- tool outputs;
- retrieved/project content;
- agent-authored summaries/deltas;
- other conversational payload.

Dynamic message content is not treated as trusted configuration and is not required to hash identically across requests.

If a harness injects dynamic material into a system/developer block, the per-pin parser must either:
- classify and normalize the permitted variable slot precisely; or
- treat the change as structural drift.

Each pin is qualified against representative long-running traffic to measure false-drift/nuisance suspension rate. A pin whose surface cannot be normalized precisely enough without weakening the boundary is unsupported.

### 4.5 Pre-egress enforcement

Before a request is forwarded to the provider, the gateway verifies at least:

- active attachment/run identity;
- generation/session identity;
- qualified adapter/pin/content identity;
- provider and model/profile;
- reasoning/effort binding where applicable;
- normalized tool/schema surface;
- normalized system/developer structural surface;
- relevant delegation/capability exposure.

The verdict is written before forwarding.

Observation after project context has already been sent to an unapproved provider/model is insufficient.

Existing-host attach is supported only if its model traffic can be forced through the same gateway/enforcement path. Otherwise existing-host attach is unsupported for full AEW mode.

### 4.6 Forgery-resistant broker binding

A model-controlled host MUST NOT receive an AEW authorization token representing an attested model request.

Instead, authorization is server-side state:

1. the gateway accepts and attests request `R`;
2. the provider returns a response for `R`;
3. for each model-emitted AEW tool call, the gateway records server-side:
   - attachment/run generation;
   - qualified host/session identity;
   - response/request identity;
   - provider-emitted `tool_call_id` (or qualified equivalent);
   - exact canonicalized tool name;
   - cryptographic hash of canonicalized arguments;
   - single-use state;
   - short expiry;
4. the harness may relay the normal tool call, but it does not possess a separate authority credential for that call;
5. the broker receives the relayed call and looks up `(generation, tool_call_id)` in gateway-owned binding state;
6. the broker canonicalizes the received tool name/arguments and compares them to the recorded name/hash;
7. only an exact, unexpired, unused match is admitted;
8. admission atomically consumes the binding so replay fails.

Missing, expired, reused, wrong-generation, wrong-tool or wrong-argument bindings are refused.

If a provider/harness does not expose a stable tool-call identity suitable for this contract, that pin/transport must define and qualify an equivalent gateway-created response-call identity that is never selectable or forgeable by the model-controlled host.

### 4.7 Drift and SUSPENDED behavior

If required structural/model/profile facts drift:

1. the outbound request is denied before forwarding where visible pre-egress;
2. bindings from any invalid/unattested response are never created;
3. later broker calls with no valid server-side binding are refused;
4. the attachment enters `SUSPENDED`;
5. the reason is recorded (`drift`, `model_mismatch`, `surface_mismatch`, etc.);
6. the generation is not silently resumed;
7. returning to ACTIVE requires a new generation and readiness qualification.

`SUSPENDED` refuses AEW reads and mutations.

### 4.8 Gateway availability policy

Gateway failure is fail-closed.

For **Lead execution**:
- new model requests stop;
- no new broker bindings are issued;
- the attachment becomes SUSPENDED or host-lost-equivalent according to the detected failure;
- no direct provider fallback is permitted.

For **worker execution**:
- new model requests stop;
- the worker remains under its existing invocation custody;
- supervisor hard deadlines and containment still apply;
- the failure is recorded/raised through the normal run/attention path;
- no direct provider fallback is permitted.

Gateway outage is therefore intentionally capable of stopping all model-backed AEW execution. Availability work may add redundancy later, but redundancy must preserve one logical enforcement boundary and cannot bypass the attestation/binding contract.

## 5. Host modes and guarantee levels

### 5.1 Managed launch — default

Managed launch is the default supported mode.

AEW/supervisor creates a qualified harness environment with:

- private config/home where required;
- curated environment;
- qualified binary/artifact;
- known model-visible tool/instruction surface;
- forced gateway routing, pre-egress request enforcement and server-side tool-call binding;
- supervisor-owned canonical control state;
- broker-only AEW authority.

This is the reference guarantee.

### 5.2 Existing-host attach — opt-in

Existing-host attach is permitted only when project policy enables it and the operator explicitly selects a supervisor-registered host.

It is **not** equivalent to a fresh managed launch.

A previously-running conversation can contain:

- ambient instructions;
- operator conversation;
- project data from an earlier attachment;
- provider/harness environment inherited before AEW was involved.

That history cannot be proven clean retroactively.

Therefore an existing-host attachment carries a guarantee such as:

```text
host_mode: existing_host
context_isolation: tainted_prior_context
control_state_isolation: required
request_surface_attestation: required
```

Full control-state isolation, forced gateway routing, request-level surface enforcement and server-side broker binding remain mandatory. Prior conversational cleanliness is the degraded property.

### 5.3 Conversation taint

Taint attaches to the **conversation/session identity**, not merely to the harness process.

The supervisor's taint record is explicitly a **lower bound**: AEW can prove which projects it attached, but cannot prove that the operator did not paste other project material or that native harness file access did not expose additional content outside AEW.

- Same-project reattachment is allowed subject to normal readiness and fresh generation.
- Attaching a conversation tainted by project A to project B is refused by default.
- Cross-project reuse requires explicit operator override and is recorded as a reduced context-isolation guarantee.
- A managed launch that resumes/imports a native prior conversation inherits that conversation's taint and is not considered fresh.
- The reference clean path creates a new harness conversation/session under managed launch.

### 5.4 Reattach delta

On same-project reattachment, AEW provides an explicit canonical delta since the prior generation where available, plus the current revision/state.

Agent-authored/free-text material in the delta is treated as delimited data, never as trusted instructions.

If an exact delta cannot be produced, AEW performs full canonical rehydration and marks the attachment context with an explicit `delta_unavailable` / stale-context indicator.

All mutating actions remain bound to current revision / `expect_rev`; stale conversational assumptions cannot commit.

---

## 6. Explicit host selection

No automatic local-process discovery may create an attachment.

The operator chooses one of:

```text
aew open --managed ...
aew open --attach <registered-host-id> ...
```

or equivalent operator-only UI actions.

Only hosts registered with / known to the supervisor may be selected.

A random local process that speaks a compatible protocol is not attachable merely because it is discoverable.

---

## 6.1 Security-principal ergonomics

The production boundary must be usable enough that operators do not defeat it by reverting to same-UID operation.

F18-B0 therefore includes the reference ergonomic setup for the target deployment, including as applicable:

- dedicated harness/worker service identities;
- operator/supervisor identity;
- shared source-tree group membership where safe;
- default ACLs / group-write rules for ordinary source editing;
- git safe-directory / ownership configuration that does not grant access to supervisor-owned AEW authority state;
- TUI/terminal launch helpers that enter the harness identity without exposing operator lifecycle credentials;
- clear diagnostics when ownership/ACL configuration is wrong.

`aew open` verifies the effective identities and refuses production attachment if the security-principal boundary has collapsed.

M4-H is **not blocked on completion of F18 production hosting** and does not become a new F18 implementation milestone by adoption of this document.

The existing M4-H dogfood may run on the already-existing Lead-session mechanism under its existing guarantees. It must not be relabeled as satisfying this production F18 hosting contract.

If B0 or later F18 hosting slices are available in time, M4-H may additionally exercise them as explicitly labeled experimental/development observations and record setup failures, ownership/permission incidents and manual workarounds. That observation is useful but optional for M4-H completion.

A later production-hosting dogfood/qualification run must measure operator friction before F18 production rollout. Repeated friction is a design signal to improve the deployment mechanism, not permission to weaken the authority invariant.

## 7. Bootstrap authority

### 7.1 PREPARING has bootstrap-only capability

Before readiness passes, the attachment is `PREPARING`.

Its bootstrap capability may expose only what is required to prove readiness, such as:

- harness identity/version/content hash;
- protocol/schema;
- control-surface catalog/readiness;
- effective model/profile;
- request-surface probe;
- configuration/environment conformance.

It MUST NOT expose canonical project data or ordinary AEW project actions.

Bootstrap capability has a short TTL.

### 7.2 Activation

Only after all required readiness checks pass does one atomic step:

- activate the attachment;
- make the new generation current;
- enable the normal project-scoped AEW surface.

### 7.3 PREPARING failure

Failure produces a typed reason such as:

- `readiness_failed`;
- `model_mismatch`;
- `surface_mismatch`;
- `unsupported_pin`;
- `bootstrap_timeout`;
- `host_lost`.

On failure:

- pending authority is revoked;
- broker/bootstrap endpoints are closed;
- credentials are revoked;
- temporary configuration is removed;
- a managed process launched solely for the failed attachment is terminated;
- existing-host modifications are unwound where supported.

Cleanup failure is recorded as `cleanup_failed` attention, but it never causes authority to become active.

---

## 8. Attachment state model

Authoritative attachment states:

```text
NO_ATTACHMENT
    |
    | operator open / attach
    v
PREPARING
    | \
    |  \ readiness failure
    |   -> FAILED (attempt record; no authority)
    |
    | readiness succeeds
    v
ACTIVE
    |
    | required model/tool/instruction/custody drift
    v
SUSPENDED
    |
    | close / replace / requalify
    v
DETACHED

ACTIVE -- operator close ----------> DETACHED
ACTIVE -- takeover ---------------> DETACHED (old generation)
ACTIVE -- host lost --------------> DETACHED
ACTIVE -- control surface lost ---> SUSPENDED
```

`DEGRADED` is a **guarantee/capability property**, not an authority state. An ACTIVE attachment may truthfully report an optional capability as degraded/unsupported while still satisfying all required authority invariants.

### 8.1 Reason codes

At minimum:

- `operator_close`
- `takeover`
- `host_lost`
- `readiness_failed`
- `bootstrap_timeout`
- `unsupported_pin`
- `model_mismatch`
- `surface_mismatch`
- `control_surface_lost`
- `custody_failure`
- `cleanup_failed`

### 8.2 Host-loss detection

Managed hosts use supervisor process ownership and existing harness health mechanisms.

Existing hosts must provide a qualified liveness/identity mechanism through their adapter. If AEW cannot reliably distinguish the registered host from a replacement or dead host, existing-host attachment is unsupported.

---

## 9. `aew open`

The operator-only sequence is:

1. resolve project and canonical AEW state;
2. select managed launch or explicit registered host;
3. resolve requested Lead profile;
4. verify support-manifest artifact/content identity;
5. enter PREPARING with bootstrap-only capability;
6. establish supervisor-exclusive canonical control-state mutation;
7. configure/attach the harness according to its host mode;
8. prove effective model and request-visible surface through non-self-reported observation;
9. prove broker/control-surface readiness and required custody/configuration invariants;
10. create the project-scoped attachment/generation atomically;
11. deliver current canonical state and, on reattach, the canonical delta;
12. begin per-request drift attestation.

No project authority exists before step 10.

---

## 10. `aew close`

`aew close` is operator-only.

It MUST:

- revoke project-scoped AEW authority;
- stale/revoke the current generation;
- close the project broker/capability for that generation;
- refuse all subsequent AEW read and mutation commands from the detached generation;
- record detach reason and continuing child runs;
- remove the AEW model-visible surface live where the adapter supports it.

It MUST NOT implicitly:

- terminate the harness;
- terminate Astra or another Lead model;
- erase conversation/context;
- prohibit ordinary non-AEW file/git/shell work that the harness is otherwise allowed to perform;
- cancel already-admitted child invocations;
- release a load-bearing lease merely because the Lead detached;
- accept/classify/advance child results.

The precise wording is:

> After close, the Lead has no AEW project authority and no AEW-mediated project access through the detached attachment.

This is **not** a claim that the persistent harness is sandboxed away from ordinary project files.

Canonical AEW control state remains supervisor-protected from direct model writes even after detach.

---

## 11. Closing with active children: drain custody and attention

Already-admitted child invocations retain their own invocation custody and may continue after Lead detach.

### 11.1 Close acknowledgment

If active child runs exist, `aew close` lists them and requires operator acknowledgement before detaching.

Acknowledgement means:

> continue these already-admitted runs without an attached Lead

It does not broaden their authority.

### 11.2 Detached-run record

Each continuing run is marked/projection-visible as detached from a current Lead attachment and retains:

- invocation/run identity;
- parent relationship;
- credential/custody scope;
- hard execution deadline;
- drain deadline where applicable;
- result/attention state.

### 11.3 Credentials and hard deadline

The invocation's approved execution hard deadline governs process lifetime.

If the hard deadline is reached:

1. the supervisor stops the process as an authority-reducing safety action;
2. the supervisor revokes the invocation credential after/with termination;
3. the result is recorded through the existing interrupted/terminated reconciliation path;
4. no lease is released merely because time expired;
5. no workflow progress is manufactured.

Credential TTL must extend only far enough to support the approved invocation/drain window and MUST NOT expire while the process is still intentionally allowed to execute.

The supervisor therefore terminates/stops the process before or atomically with credential revocation.

A **drain deadline is a stop condition**, not merely an attention threshold.

If the drain deadline is reached before a usable held result is obtained:

1. the drain has failed;
2. the draining verifier/invocation is stopped;
3. the integration custodian is explicitly cancelled;
4. the integration lease is marked for reconciliation, not silently released;
5. the existing `aew integrate reconcile` path retires the integration attempt and returns the Ticket to the appropriate queue state;
6. operator attention is raised with the drain-deadline reason.

This is distinct from an **orphan/attention deadline**, which may raise notification without itself cancelling otherwise-valid work.

The invocation execution hard deadline remains the absolute process-lifetime ceiling. Reaching it also stops the process as an authority-reducing safety action. Neither deadline manufactures success or releases a load-bearing lease directly.

### 11.4 Attention and notifier

A detached child that:

- completes;
- blocks on a Lead/operator decision;
- reaches an orphan/drain deadline;
- encounters an infrastructure/custody fault

creates an operator-visible attention item.

Unattended deployments require the operator-only/out-of-band notifier already required by the steering/health amendments.

An **orphan/attention timeout** raises attention and does not automatically cancel the child or release a lease. By contrast, the adopted **drain deadline** is a stop condition: hitting it stops the drain, cancels the integration custodian, and sends the integration attempt through normal reconciliation.

### 11.5 Permission behavior

Worker runs must not rely on an interactive Lead approval prompt for ordinary execution. Harness `ask`/auto-review authority remains disallowed for runs.

If a run reaches an AEW decision-required condition while no Lead is attached, it records/holds the condition for later authoritative disposition.

---

## 12. Child completion after generation change

Loss of the Lead attachment is not loss of an already-admitted child invocation's custody.

A child admitted under generation N may finish after generation N+1 exists.

Its hand-in may create only records permitted by its invocation contract, such as:

- result/report;
- evidence;
- run/invocation telemetry;
- typed blocked/failure observation.

It may not perform the authoritative acceptance/control mutation that consumes that result.

The current Lead generation performs any later:

- evidence acceptance;
- classification;
- Ticket/control transition;
- integration/publication decision.

Thus:

> result production/hand-in is invocation authority; result acceptance and workflow advancement use current control authority.

No WC/KC amendment is required unless implementation currently couples hand-in directly to a control transition.

Acceptance test: a child started under generation N completes after generation N+1 becomes current. Its result/evidence records are committed, but the authoritative Ticket/control revision does not advance until an action under current authority explicitly accepts/consumes the result.

---

## 13. Drain stop conditions

A drain **stops** on:

- an existing supervisor stop condition;
- abnormal harness/process exit where applicable;
- execution hard deadline or step limit;
- containment failure;
- supervisor failure;
- relevant custody/lease/integrity failure;
- drain hard deadline;
- operator `stop now`;
- operator `release to manual`;
- inability to durably record or verify result/drain state;
- unclassified fault, fail closed.

These do **not** constitute drain infrastructure failure by themselves:

- a new Lead generation attaches;
- an old Lead generation becomes stale;
- project/control revision changes;
- a child returns a legitimate FAIL/BLOCKED/inconclusive/domain result;
- a result requires later Lead classification.

A valid negative result is recorded and held.

A timeout never releases a lease merely because time expired.

A separate orphan/attention timer may notify without cancelling. It is not the drain deadline and must not be named or treated as one.

---

## 14. StageIntent ownership across generations

An open StageIntent owned by a stale/revoked Lead generation does not continue automatically.

On generation loss it becomes non-runnable under the old owner.

A new generation may continue equivalent work only after:

- current revision recheck;
- current legality digest recheck;
- current authority/gate recheck;
- stage-contract re-resolution;
- explicit adoption/rebinding or creation of a fresh StageIntent according to the StageIntent contract.

No old-generation intent silently inherits new-generation authority.

---

## 15. Lead versus worker hosting

| Concern | Lead | Worker/subagent |
|---|---|---|
| Lifetime | Interactive harness may outlive AEW attachment. | Bounded invocation/run. |
| Reference model | GPT-6 Astra. | Laguna S2.1 default; GPT-5.4 / approved OSS alternatives. |
| Authority | Attachment generation + broker/project capability. | Independent invocation credential/custody. |
| Host | Managed launch by default; opt-in qualified existing host. | Private per-run host by default. |
| Delegation | Requests work through AEW. | No uncontrolled recursive native delegation. |
| On Lead close | Loses AEW authority; harness may remain alive. | Continues if already admitted unless separately cancelled. |

Native delegation is unavailable unless a qualified adapter path preserves all of:

- invocation identity;
- role;
- parent relationship;
- execution profile;
- bounded capability;
- custody;
- limits;
- evidence/provenance;
- model-visible conformance.

---

## 16. Executable identity and support-critical artifacts

Qualification checks the artifact that is actually executed, not merely a path/version reported before launch.

The supervisor:

- verifies the content hash immediately before exec;
- executes from a supervisor-owned read-only/immutable path or equivalent protected location;
- refuses if the executable or required companion artifact changes identity between qualification and launch;
- preserves the qualified artifact identity in the attachment/run provenance.

Each support manifest enumerates support-critical companion artifacts per pin, including as applicable:

- adapter implementation/build identity;
- harness executable;
- config templates;
- MCP server executable/build;
- bundled skills/instructions that are intentionally part of the qualified request surface;
- request-surface fixture/probe;
- conformance suite artifact;
- protocol/schema fixture.

The list is explicit per supported pin.

## 17. Harness-specific disposition

### 17.1 OpenCode

OpenCode 2.0.18 remains the qualified research baseline from T9, including:

- direct typed AEW tool presentation with `codemode:false`;
- measured request-level tool-schema filtering.

Support still requires the remaining broker-only readiness and config/ambient-surface conformance.

### 17.2 Codex

Codex CLI 0.160.0 remains **not support-ready**.

The architecture remains valid; the intended deployment pin must pass the versioned qualification suite.

A supported Codex pin must prove at least:

- direct typed AEW action presentation or explicitly accepted equivalent;
- request-level observed model identity;
- request-level tool/instruction surface attestation;
- suppression of ungranted collaboration/subagent facilities;
- suppression/replacement of unapproved ambient bundled skills/instructions;
- private config/home and curated environment where required;
- broker-only custody;
- supervisor-owned canonical AEW control state;
- no model-controlled direct control-state mutation;
- continuing drift detection.

This is a bounded implementation/qualification spike, not an architecture redesign.

---

## 18. Storage and ADR-0011

Only the current attachment/generation remains in hot control state.

Prior generations/attachment attempts are retained through ADR-0011's hot/cold model as immutable history sufficient for:

- provenance;
- stale-writer diagnosis;
- takeover/restart investigation;
- support/conformance audit.

Historical generations are not independently mutable authorities.

---

## 19. Dashboard projection

The authenticated read-only dashboard may render Engine-supplied attachment facts including:

- attachment state;
- current generation;
- detach/suspend reason;
- requested model/profile;
- observed/effective model/profile;
- fact source / attestation status;
- host mode (`managed` / `existing_host`);
- context-isolation/guarantee level;
- adapter/pin/support identity;
- active detached child count;
- gateway/attestation status;
- attachment/output guarantee (`production` / `dev` / other adopted level);
- attention state.

The dashboard does not infer authority or trust level from model names, process presence or timestamps.

---

## 20. Acceptance criteria

### 20.1 Authority

- a real Rocky 8 negative test executed as the actual Lead-host identity cannot mutate any protected-set entry;
- lifecycle commands are accepted only from the authorized operator security principal / peer credential;
- a surviving transport key is never Lead authority;
- stale or SUSPENDED generations cannot read or mutate through AEW project surfaces;
- direct harness filesystem access does not bypass canonical control-state authority;
- unsupported same-UID deployment models are rejected/documented rather than silently weakened.

### 20.2 Bootstrap

- PREPARING has no project data and only readiness capability;
- bootstrap authority expires;
- failed preparation cleans endpoints, credentials and temporary config;
- cleanup failure never activates authority;
- host selection is explicit and supervisor-registered.

### 20.3 Gateway and continuous qualification

- gateway runs under its own principal and is the only holder of provider credentials for managed execution;
- actual harness/worker principal cannot directly connect to qualified provider endpoints;
- every provider request in managed launch is forced through the enforcement gateway;
- existing-host mode cannot become ACTIVE unless the same forced gateway path is proven;
- actual request model identity is observed independently of model self-report;
- deny-by-default model/provider/normalized-surface checks occur before provider egress;
- normalized structural-surface parsing distinguishes allowed variable slots from untrusted message content;
- each supported pin passes representative false-drift/nuisance-suspension testing;
- broker calls are admitted only by single-use gateway-owned `(generation, tool_call_id, tool, argument-hash)` binding or a qualified equivalent;
- replay, altered-argument, wrong-generation and missing-binding calls are refused;
- gateway verdict storage contains enforcement metadata/hashes rather than plaintext project request bodies;
- gateway outage stops model-backed Lead/worker requests without direct-provider fallback;
- model/tool/instruction drift SUSPENDS the attachment;
- SUSPENDED refuses AEW reads and mutations;
- return to ACTIVE requires a new generation;
- conformance-suite and support-manifest identities are recorded.

### 20.4 Existing-host mode

- project policy must opt in;
- the operator must explicitly select the registered host;
- project taint is recorded;
- cross-project reuse is refused by default;
- same-project reattach receives current canonical state/delta;
- context-isolation guarantee is visibly lower than managed launch;
- control-state isolation and request attestation remain mandatory.

### 20.5 Lifecycle

- close revokes AEW authority without killing the harness/model;
- close with active children lists them and requires acknowledgement;
- children retain bounded independent custody;
- detached completions/blocks/deadlines raise attention;
- host loss revokes authority;
- takeover stales the prior generation immediately;
- old StageIntents cannot continue without revalidation/rebinding.

### 20.6 Model/profile

- reference Astra/Laguna behavior is measured, not assumed;
- requested vs observed effective model/provider/effort are attributable;
- GPT-5.4 / OSS worker overrides remain explicit;
- model/profile mismatch fails closed.

---


### 20.7 Development guarantee and operator ergonomics

- development attachments and their admission-relevant outputs are typed/provenanced as `guarantee: dev`;
- `guarantee: dev` outputs cannot silently enter production-grade Evidence/Knowledge admission;
- `aew open` refuses production attachment when harness and operator/supervisor identities collapse to an unsupported same principal;
- the reference Rocky 8 group/ACL/git/TUI setup is exercised in dogfood;
- the later production-hosting qualification/dogfood records permission/ownership friction and attempted workarounds; M4-H may contribute optional early observations if relevant F18 slices are available.

## 21. Implementation slices

| Slice | Contents | Exit criterion |
|---|---|---|
| **F18-A — contract/state** | attachment states/reasons; protected-set registry; support manifest; executable/content identity; hot/cold generation records; guarantee labels; operator-only lifecycle contract | authority/state tests pass; protected set and unsupported deployment modes are explicit |
| **F18-B0 — deployment security-principal proof + ergonomics** | dedicated Lead/worker principal or SELinux-equivalent boundary; operator-only supervisor socket with peer-credential authorization; supervisor-owned protected state; group/ACL/git/TUI ergonomic path; same-principal refusal | **first hard gate:** on real Rocky 8, actual Lead-host identity cannot mutate protected set or invoke lifecycle controls, while ordinary source workflow remains usable |
| **F18-B1 — bootstrap** | bootstrap-only broker; explicit managed/attach selection; managed launch default; PREPARING cleanup; conversation-taint record | no real project attachment yet unless C and D prerequisites are also satisfied |
| **F18-C — load-bearing gateway + broker binding** | gateway principal; provider credential custody; forced egress; normalized structural-surface parser; pre-egress enforcement; response `tool_call_id` + argument-hash binding; single-use/expiry; SUSPENDED behavior; gateway outage policy | direct-provider attempt fails; model switch/tool injection is denied; altered/replayed/unbound tool calls fail; outage fails closed |
| **F18-D — detached child handling** | close acknowledgement; detached-run attention; bounded credentials; hard-deadline order; drain semantics; StageIntent stale-owner handling | live child survives close safely; credentials/process lifecycle is bounded; completion cannot mutate control state |
| **F18-E — production attachment enablement** | combines B0/B1/C/D into managed project attach; existing-host attach enabled only where forced gateway path is proven | first non-dev attachment may become ACTIVE |
| **F18-F — OpenCode qualification** | remaining T9 broker-only/config-isolation/model-visible conformance plus normalized-surface false-drift test | pin passes full F18 suite or remains unsupported |
| **F18-G — Codex qualification** | intended pin qualification using same versioned suite plus Codex-specific request/delegation/ambient-context checks | pin passes without architecture exception or remains unsupported |
| **F18-H — reference topology smoke** | Astra Lead + Laguna default worker; 5.4/OSS explicit override where available | open/work/close/reattach end-to-end with correct provenance and authority behavior |
| **F18-I — production-hosting ergonomics observation** | measure principal/ACL/git/TUI friction and operator workarounds before production rollout; M4-H may contribute optional early observations if slices are available | issues feed deployment UX improvements without weakening authority |

**Development-mode rule:** before F18-E exits, only explicitly labeled development/test attachments may be created, against disposable/non-production projects, and they must not be represented as satisfying the production F18 guarantee.

All Evidence, Knowledge candidates, reports and other admission-relevant artifacts produced under such an attachment carry `guarantee: dev` (or an equivalent typed guarantee field) in provenance. `guarantee: dev` material may be inspected and used for engineering/debugging, but cannot be admitted as production-grade Evidence/Knowledge solely on that provenance. Production admission requires re-establishment/reproduction through an accepted production path or an explicitly adopted admission rule that proves equivalent assurance.

## 22. Deferred / downstream

- F18.3 release signing and `release_epoch` — after ADR-0014 adoption.
- Native harness delegation optimization — only after bounded-invocation equivalence is proven and separately adopted.
- Native sandbox enhancement — after baseline hosting support.
- Hooks, harness memories, native planning and harness approval systems — not baseline authority.
- Gateway high availability/redundancy — optional later work; any redundancy must preserve one logical attestation/binding boundary and cannot introduce a direct-provider bypass.
- Persistent Lead filesystem sandboxing of ordinary project source — separate containment decision; F18 requires canonical control-state protection but does not claim full project-file isolation.
- Q14 remote/PR integration target — independent alpha decision.

---

## 23. Adoption

**v0.6 is a hygiene-only correction to v0.5.** It removes three stale contradictory passages and does not change any adopted authority, lifecycle, milestone, or drain semantics.


**F18 harness-hosting / attachment-authority v0.6 is ADOPTED alongside the existing install/bootstrap design.**

Q12 remains closed.

T9 remains versioned implementation evidence.

OpenCode/Codex pin qualification is an implementation gate, not an architecture blocker.

The load-bearing gateway/attestor and broker-binding contract in §4 are part of the production hosting authority boundary.

The reference target remains GPT-6 Astra Lead with Laguna S2.1 as the default worker, with GPT-5.4 and approved open-source workers available through attributable execution-profile selection.

Any implementation that cannot satisfy the production principal separation, forced gateway routing, protected-set isolation or broker-binding invariants must identify itself as unsupported or development-only rather than weakening the adopted contract.


## 24. Register and milestone filing

### 24.1 Filing relationship

This document sits **alongside**, not in place of, the adopted install/bootstrap design.

The register should therefore preserve the existing `aew init` / `aew doctor` design references and add the hosting workstream/slices from this document as separate implementation rows or child rows under F18.

No requirement from the earlier install/bootstrap design is discarded by adoption of this document.

### 24.2 M4-H sequencing

Adoption of this hosting contract does **not** move F18-A through F18-E in front of M4-H.

M4-H may run on the existing Lead-session mechanism under its existing pre-F18 guarantees. That run is not evidence that the production F18 hosting contract has been implemented.

F18 production attachment remains gated by the slices in this document. When those slices are implemented, a dedicated production-hosting qualification/dogfood run must exercise the real security-principal, gateway and operator-ergonomics path.

### 24.3 Drain deadline semantics

For F31/Q12 queue-side behavior:

> A drain deadline is a failure/stop condition. Hitting it stops the draining work, cancels the integration custodian, marks the integration attempt for reconciliation, and raises operator attention. It does not merely pause and notify.

A separate orphan/attention deadline may notify without cancellation. The two concepts must use distinct names and typed reasons.
