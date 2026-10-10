# F9-A1 — First-Class Lead–Worker Messaging and Adaptive Supervision Amendment v0.1

**Status:** PROPOSED AMENDMENT  
**Amends:** `AEW Live Coordination and Assumption-Propagation Design v0.1`  
**Register:** F9  
**Scope:** Lead↔worker communication, targeted supervision, spot-checking, and coordination visibility  
**Does not supersede:** F9 v0.1 authority, scope, impact-hold, evidence, or standup semantics

## 1. Reason for amendment

F9 v0.1 intentionally deferred implementation until real multi-agent behavior demonstrated a need.

That evidence now exists.

Observed multi-agent engineering work showed a recurring operating pattern:

```text
strong Lead model
    ↓
decomposes complex work into bounded Tickets
    ↓
lower-cost worker models execute those Tickets
    ↓
Lead has spare supervisory capacity while workers run
    ↓
targeted Lead inspection finds requirement drift or local defects
    ↓
Lead needs to correct or question the exact active worker
```

Without a first-class communication path, the Lead may resort to wasteful mechanisms such as creating an additional agent solely to relay messages and acknowledgements.

That is not an acceptable steady-state coordination model.

This amendment therefore promotes **durable Lead↔worker messaging and adaptive Lead supervision** into the intended AEW operating model.

---

## 2. Operating hypothesis

AEW should optimize for:

> **One strong Lead supervising multiple tightly bounded workers, with selective intervention where higher-capability judgment has the greatest expected value.**

The intended topology is:

```text
                      Astra-tier Lead
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
      Worker A           Worker B           Worker C
    bounded Ticket      bounded Ticket      bounded Ticket
         ↕                  ↕                  ↕
     messages           messages           messages
         │                  │                  │
         └──────────── Lead supervision ──────┘
```

AEW should not require frontier-model execution for every implementation action.

AEW should also not leave the high-capability Lead idle when valuable supervisory work exists.

The optimization target is:

> **maximize useful Lead judgment per frontier-model token, not maximize Lead utilization.**

An idle Lead is preferable to ceremonial or low-value spot checking.

---

## 3. Core requirement: first-class bidirectional messaging

AEW MUST provide a durable, bounded, low-latency communication path between:

```text
current Lead generation
        ↕
active AEW invocation
```

without requiring creation of another model invocation.

The Lead must be able to message an exact active worker.

An active worker must be able to reply to the Lead.

Initial scope is **Lead↔worker**, not unrestricted worker↔worker chat.

Worker-to-worker information normally flows through Lead routing so the Lead retains global coordination responsibility.

---

## 4. Message identity

A coordination message should have a stable AEW identity.

Illustrative shape:

```text
CoordinationMessage {
    message_id
    sender
    recipient
    ticket
    ticket_revision
    invocation
    in_reply_to?
    idempotency_key
    kind
    body
    refs[]
    created_at
}
```

### Sender / recipient

Allowed initial forms:

```text
sender:
    lead:<generation>
    invocation:<id>

recipient:
    lead:<generation>
    invocation:<id>
```

A worker may communicate only within its admitted coordination surface.

Messaging does not widen filesystem, tool, Ticket, role, or workflow authority.

---

## 5. Reply chains

`in_reply_to` is optional and references another coordination message.

This permits real conversations:

```text
MSG-101 Lead → INV-17
"Requirement 4 is not satisfied. Inspect shutdown while recv() is blocked."

MSG-102 INV-17 → Lead
in_reply_to: MSG-101
"Confirmed. join occurs before the socket closes. Correcting it."

MSG-103 Lead → INV-17
in_reply_to: MSG-102
"Also test peer disconnect independently."

MSG-104 INV-17 → Lead
in_reply_to: MSG-103
"Both paths are now covered. Evidence E-88."
```

AEW need not infer semantic agreement from the existence of a reply.

---

## 6. Idempotency

Message delivery MUST support idempotent submission.

The sender supplies or receives an `idempotency_key`.

If the Lead submits a message and loses the transport response, retrying the same request must return the existing message rather than creating a duplicate delivery.

Conceptually:

```text
send(MSG request, idempotency=K7)
    ↓
transport timeout
    ↓
retry K7
    ↓
return existing MSG-101
```

This prevents communication retries from producing duplicated work or contradictory conversational state.

---

## 7. Delivery versus durable identity

The AEW message exists independently of a specific harness session.

Preferred sequence:

```text
AEW records message
        ↓
attempt live delivery
        ↓
harness adapter
        ↓
worker session
```

Harness-native communication is transport, not authority.

Possible transports may include:

```text
OpenCode inbox/session delivery
Codex native message delivery
future harness-native transport
continuation/recontextualization fallback
```

The Lead should use one AEW operation regardless of underlying harness.

Session loss does not erase the coordination record.

If a worker invocation is relaunched, unresolved/relevant messages may be included in its continuation context according to the normal bounded-context rules.

---

## 8. Delivery facts

AEW may record bounded delivery state such as:

```text
RECORDED
DELIVERED
ACKNOWLEDGED
REPLIED_TO
UNDELIVERABLE
```

These are communication facts only.

They do not establish:

- compliance;
- correctness;
- evidence acceptance;
- workflow completion;
- successful implementation.

A reply may serve as acknowledgement, so explicit acknowledgement need not be mandatory for every message.

---

## 9. Message kinds

Suggested non-authoritative kinds:

```text
instruction
question
clarification
finding
blocker
status
acknowledgement
correction
```

Kinds aid routing and presentation.

They do not grant different workflow authority.

A `finding` in a message is still coordination knowledge until it enters the appropriate Evidence/Knowledge path.

---

## 10. References instead of payload duplication

Messages SHOULD reference existing AEW artifacts rather than copying large content.

Example:

```text
refs:
  - evidence:E-188
  - source:src/net/session.c
  - ticket:T-0042@r3
  - finding:F-22
```

The coordination layer remains bounded.

Raw worker transcripts and hidden reasoning are not coordination artifacts.

---

## 11. Messaging is not a workflow mutation channel

The governing F9 principle remains unchanged:

> **Coordination may move knowledge. Only existing AEW authority paths may move project state.**

Therefore a message may:

- clarify an existing requirement;
- ask a targeted question;
- point out an apparent miss;
- provide a new evidence reference;
- request investigation within existing scope;
- report a blocker;
- request status;
- tell a worker to stop pursuing an approach.

A message may not silently:

- change the Ticket objective;
- revise accepted acceptance criteria;
- widen scope;
- alter risk class;
- grant capabilities;
- waive a gate;
- accept evidence;
- satisfy review or verification;
- authorize publication.

If conversation reveals that the assignment materially changed, normal Ticket revision/replan/supersession rules apply.

---

## 12. Adaptive Lead supervision

Messaging enables the larger supervision loop.

AEW should support **adaptive supervision**, not mandatory periodic review of every worker.

The desired behavior is:

```text
workers execute independently
        ↓
AEW exposes potentially valuable supervision targets
        ↓
Lead chooses whether to inspect
        ↓
Lead may:
    do nothing
    spot-check
    ask worker a question
    send correction
    route a finding
    call scoped sync
    escalate/replan
    take over
```

AEW surfaces opportunities.

The Lead supplies judgment.

---

## 13. Supervision candidate projection

AEW may expose a derived read projection:

```text
SupervisionCandidate {
    ticket
    ticket_revision
    invocation
    reason
    supporting_refs[]
    suggested_action?
}
```

This is an attention projection, not an AI quality score and not authority.

Candidate reasons should initially come from observable workflow facts.

Examples:

- high Ticket risk class;
- worker has entered rework;
- repeated rework;
- long-running active invocation;
- cross-component or multi-resource scope;
- concurrency/thread/socket-sensitive work where policy or Ticket metadata identifies it;
- contradiction or blocker;
- worker explicitly reports uncertainty;
- a relevant sibling finding was published;
- weak or incomplete supplied requirement/evidence coverage;
- deterministic overlap/relevance hint;
- bounded random audit sample.

Absence from the candidate list does not prove a worker is correct or low risk.

---

## 14. Spot checking

A spot check is a Lead supervisory action.

It is **not** formal review or verification.

Typical purpose:

```text
detect drift early
challenge one critical assumption
inspect one high-risk invariant
check requirement coverage
inspect suspicious evidence
verify worker interpretation
```

A spot check may result in:

```text
no_action
message
route
sync
rework_request through normal workflow
replan/escalation
takeover
```

A spot check never satisfies an acceptance gate.

---

## 15. Lead idle-time behavior

AEW should make valuable supervision available while workers run.

The intended Lead loop is approximately:

```text
dispatch bounded workers
        ↓
wait-any / attention surface
        ↓
while no completion requires immediate action:
    inspect highest-value supervision candidate if worthwhile
        ↓
    message / route / sync when appropriate
        ↓
return to waiting
```

This does not mean AEW must keep the Lead continuously generating tokens.

If no supervision candidate has sufficient expected value, waiting is correct.

---

## 16. Adaptive collaboration target

The target interaction policy is:

### A — isolated

No proactive Lead supervision.

### B — available

Messaging exists, but all supervision is entirely Lead-initiated without AEW prompting.

### C — adaptive / encouraged

AEW surfaces high-value supervision candidates and encourages selective Lead intervention.

### D — forced

Periodic or mandatory Lead checks/standups regardless of expected value.

**F9's design target is C.**

Exact triggers, thresholds and budgets remain tunable through evaluation.

AEW should not freeze a universal spot-check frequency before measurement.

---

## 17. Routing worker discoveries

When one worker discovers information relevant to other active workers:

```text
worker A
   ↓
Lead
```

The Lead determines blast radius.

For narrow impact:

```text
Lead → worker B
Lead → worker D
```

For broad or uncertain impact:

```text
Lead → scoped standup / sync
```

The Lead remains the routing intelligence.

Direct unrestricted peer messaging is not required by this amendment.

---

## 18. Standups remain selective

A standup remains a higher-cost convergence mechanism.

Use it when a discovery affects several workers or requires shared reconciliation.

Do not turn every worker update into a standup.

Preferred escalation:

```text
single-worker issue
→ direct Lead↔worker message

few known affected workers
→ Lead routes targeted messages

broad / contradictory / uncertain impact
→ scoped standup

plan or objective invalidated
→ normal replan / authority path
```

---

## 19. Supervision telemetry

To tune adaptive supervision, AEW should preserve bounded telemetry/provenance about meaningful supervisory actions.

A lightweight record may capture:

```text
SupervisionEvent {
    ticket
    invocation
    trigger
    action
    related_messages[]
    refs[]
    timestamp
}
```

Possible actions:

```text
spot_check_no_action
message_sent
finding_routed
sync_opened
rework_triggered
takeover
```

This record is not engineering evidence.

It exists to understand coordination behavior, cost and effectiveness.

---

## 20. Evaluation

Adaptive supervision should be tested empirically.

Compare at least:

```text
A. no proactive supervision
B. messaging available only
C. AEW-recommended adaptive supervision
D. mandatory periodic supervision
```

Hold model/task/environment factors as constant as practical.

Measure:

```text
correctly accepted outcomes
requirement misses
defects caught before formal review
rework cycles
successful in-place corrections
Lead tokens
worker tokens
total cost
wall time
Lead idle time
unnecessary interventions
messages per Ticket
messages per successful correction
standups opened
worker discoveries routed to siblings
formal-review defects that earlier spot checks missed
```

F25 usage telemetry should supply the cost side where available.

The goal is to learn the intervention policy rather than assume more collaboration is always better.

---

## 21. Worker-model qualification relevance

AEW may eventually characterize execution profiles by observed supervisory needs.

Examples:

```text
profile:
    bounded_ticket_reliability
    rework_frequency
    supervision_frequency
    independent_review_qualification
    long_horizon_reliability
```

This must be empirical.

It should not become model-name folklore encoded directly in workflow logic.

---

## 22. Relationship to heterogeneous worker operation

This amendment does not retroactively block current M4 experimentation.

However, before AEW promotes substantial heterogeneous lower-tier worker fanout as a normal production operating mode, the deployment should have a qualified supervision path capable of:

```text
observe
→ target worker
→ deliver durable message
→ receive reply
→ inspect resulting work
→ route wider impact
→ open sync when needed
```

The reason is operational, not hierarchical:

> cheaper bounded workers become substantially more useful when a stronger Lead can cheaply detect drift and correct course before formal review.

---

## 23. Dashboard / workbench requirement

Coordination must be inspectable in relation to the work that caused it.

A global chat log is insufficient.

Read projections should allow navigation by:

```text
Ticket
Ticket revision
attempt
invocation
message thread
Lead generation
```

A Ticket view should be able to reconstruct something like:

```text
T-0042 r3
│
├─ INV-017 Laguna implementer
│
│  MSG-101 Lead → worker
│  "Check blocked recv shutdown behavior."
│  basis: SC-12
│
│  MSG-102 worker → Lead
│  "Confirmed ordering defect. Correcting."
│
│  MSG-103 worker → Lead
│  "Fixed; tests added."
│  refs: E-88
│
├─ review
├─ verification
└─ outcome
```

The operator should be able to answer:

> Why did this large corrective action occur?

without hunting through unrelated agent transcripts.

---

## 24. UI causality rule

The dashboard must not infer causality merely from timestamp proximity.

For example, it must not claim:

```text
MSG-101 caused commit abc123
```

unless the backend supplies that relation.

It may truthfully show:

```text
MSG-101 was sent to INV-017 for T-0042@r3.

MSG-102 explicitly replied to MSG-101.

MSG-102 referenced E-88.

The implementation attempt later produced revision X.
```

Supplied relationships are rendered.

Missing relationships remain unknown.

---

## 25. Implementation staging

This amendment refines F9 staging as follows.

### F9-A — first-class messaging

Build:

- durable Lead→worker message;
- worker→Lead reply;
- message identity;
- `in_reply_to`;
- idempotency;
- bounded refs;
- live harness delivery;
- session-loss/relaunch behavior;
- Ticket/revision/invocation bindings;
- read projections;
- resume/attention integration as appropriate.

This is the minimum useful coordination core.

### F9-B — structured worker coordination

Build the existing F9 concepts:

- progress/finding/question/blocker updates;
- Lead routing;
- relevant bounded deltas;
- scoped sync/standup;
- contradiction preservation.

### F9-C — adaptive supervision

Add:

- supervision-candidate projection;
- targeted spot-check workflow;
- Lead intervention telemetry;
- routing from spot-check result to exact worker;
- Ticket-linked dashboard presentation.

Initial mode is advisory.

The Lead remains the decision maker.

### F9-D — empirical tuning / scheduler assistance

Evaluate A/B/C/D supervision modes.

Tune:

- triggers;
- thresholds;
- sampling;
- budget;
- candidate prioritization;
- standup escalation.

Only promote stable defaults after measured results.

---

## 26. Preserved F9 invariants

This amendment does not alter the following:

1. Coordination is not authority.
2. Routed information cannot widen scope.
3. A coordination statement is not automatically Evidence.
4. Messaging cannot revise an assignment materially.
5. Material scope changes use normal revision/supersession.
6. Standup consensus cannot satisfy review or verification.
7. Contradictions remain attributable.
8. Hidden reasoning/raw transcripts are not coordination state.
9. Relevance hints remain advisory.
10. Absence of a hint does not establish independence.
11. Session loss must not erase important coordination state.
12. Lead routing remains the default mechanism for cross-worker propagation.

---

## 27. New amendment invariants

13. The Lead MUST be able to communicate with an active admitted worker without spawning another model invocation solely for message transport.

14. Message submission MUST be idempotent.

15. Every durable message MUST identify its sender, recipient and applicable work/invocation context.

16. Harness-specific messaging mechanisms are transports; AEW owns coordination identity and provenance.

17. Worker replies MUST NOT acquire Lead or workflow authority.

18. Spot checks MUST NOT satisfy formal review or verification gates.

19. Supervision recommendations MUST remain advisory.

20. AEW MUST NOT force expensive supervision merely to keep a Lead busy.

21. Coordination read projections MUST preserve enough Ticket/revision/invocation identity for an operator to understand the context of corrective actions.

22. The frontend MUST NOT infer causal relationships that the backend did not record.

---

## 28. Acceptance intent

F9-A1 succeeds when AEW can demonstrate the following end-to-end behavior:

```text
Lead dispatches multiple bounded workers
        ↓
Lead sees a worthwhile supervision target
        ↓
Lead performs targeted spot check
        ↓
Lead sends correction to exact active invocation
        ↓
worker receives it without redispatch
        ↓
worker replies
        ↓
worker corrects work
        ↓
Lead can route a discovered fact to another affected worker
        ↓
broader issue can escalate to scoped sync
        ↓
operator can later inspect the complete coordination chain from the Ticket
```

No extra relay agent is required.

No coordination message becomes workflow authority.

No worker receives unrelated global coordination context.

The effectiveness and cost of proactive supervision remain measurable and tunable.
