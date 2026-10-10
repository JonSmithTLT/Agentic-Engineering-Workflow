# Designer decisions of 2026-10-10: the M6a conflicts and the Codex adapter (F38, F40, F24)

**Status:** Decision record, governing for what it decides. **Approved** by the designer on 2026-10-10, relayed by the
operator. Five decisions answer the lead developer's brief of the same day. D1 to D3 settle the three points where the
M6a authorization model ([v0.8](proposals/m6a-capability-and-effect-authorization-model-v0.8.md), overlaid by
[v0.9](proposals/m6a-authorization-model-v0.9-gate-a-encoding-candidate.md); ledger CEA, GAE; ingested in PR #174)
differs from accepted or adopted text. D4 and D5 answer two questions the Codex runtime-semantics probe (register F24.1,
Codex app-server 0.162.1) raised for a future Codex adapter. §1 is the decisions as given; §2 gives the context of each;
§3 says where they are filed.

The decisions do not adopt the M6a model as governing: that is still the operator's adoption item for F38 in
[decisions due](../implementation/decisions-due.md). They settle how its conflicts resolve when it is adopted.

## 1. The decisions, recorded as given

The designer's text, verbatim:

```text
D1  APPROVE
    M6 supersedes ADR-0009/0006 native source mutation.
    Source RO + writable scratch + mediated authoritative mutation.
    Keep shell.

D2  APPROVE adoption over v0.8 table.
    Knowledge + safe navigation = C for every admitted role.
    Independence remains selector-controlled.

D3  APPROVE.
    Messaging-enabled operator switch is an approved authorization
    overlay/profile carrying G_AEW_COORDINATE.

D4  APPROVE WITH QUALIFICATION.
    Prefer AEW-owned proactive budget if Codex can be qualified for it.
    Otherwise accept Codex-native compaction as a recorded adapter residual.
    Do not reject Codex solely for mandatory compaction.

D5  APPROVE.
    Codex cancel-and-restart satisfies next-step semantics.
    Held-session staging without message identity is refused.
```

## 2. Context for each decision

The questions, the facts behind them and the lead developer's recommendation, as put in the brief. The decisions in
§1 govern; this section only explains them.

### D1. Native source mutation against ADR-0009 and ADR-0006

v0.9 §7 (GAE-12 to GAE-14; register F40) disables harness-native authoritative source edit and write tools in every
AEW worker profile, the Implementer's included: authoritative source changes only through the AEW source-mutation
mediator. Accepted text says otherwise today: ADR-0009 projects OpenCode's native `edit` for implementers, and
ADR-0006 maps the implementer's `source_mutation` capability to it. ADR-0009 also records an `edit` deny bypassed
through the shell, so hiding the tool does not by itself stop writes. The Codex probe showed the same on a second
harness: Codex's native `apply_patch` can be removed from the model-visible tools and is then refused, but its shell
still writes unless the shell is removed or the source is mounted read-only.

The questions were whether §7 supersedes ADR-0009 and ADR-0006 at M6, and whether shell writes are stopped by a
shell-less worker or by a read-only source mount with every authoritative write through the mediator. The lead
developer recommended both: supersession at M6, and a read-only mount that keeps the shell for builds and tests,
as v0.8 §26 (CEA-55) already gives project-code children read-only source. D1 approves: the source is read-only to
the worker, scratch stays writable, authoritative mutation is mediated, and the worker keeps its shell. The ADR
amendments are due when M6 lands (F40); until then ADR-0009 and ADR-0006 govern the current build unchanged.

### D2. Knowledge and navigation reads for the Reviewer and the Verifier

v0.8's role table (CEA-36) puts `G_KNOWLEDGE_READ` at P* for the Reviewer and the Verifier (an operator-approved
named profile with plan-visible independence selectors) and `G_DERIVED_READ` (map and index reads) at P for the
Verifier. The knowledge adoption of 2026-10-09 (KAD-03, KAD-06), the agent-effectiveness record (AEA-40) and the
designer's reviewer-independence ruling (KDR-03 to KDR-05) make knowledge lookup and project navigation a base
capability of every admitted role, with reviewer and verifier lookup filtered rather than excluded.

D2 approves the adoption over v0.8's table: knowledge lookup and safe navigation are C for every admitted role, and
reviewer and verifier independence stays a matter of plan selectors (CEA-54, CEA-63), not of withholding the grant:
for the Reviewer and the Verifier the cells keep v0.8's * (plan-visible independence selectors). Which derived
reads count as safe navigation is for F38's encoding to state, and until then the Verifier's P stands for the rest;
the brief proposed keeping P for anything wider than lookup, such as bulk reads or another unit's private material.

### D3. Worker coordination writes and the messaging switch

v0.8 puts `G_AEW_COORDINATE` at P for the four worker roles, which v0.8 §12 allows only through an operator-approved
named profile (CEA-34, CEA-35). ADR-0017 (ledger CMG) lets a worker reply to the Lead once the operator switches
messaging on (`coordination.messaging: enabled`, CMG-11). The question was whether that switch counts as such a
profile. D3 approves: the messaging-enabled operator switch is an approved authorization overlay or profile that
carries `G_AEW_COORDINATE`. v0.8's P cell stands; M6a's profile catalog models the switch as that profile.

### D4. Codex compaction with no off switch

C1, the context-continuity design, runs OpenCode with `compaction.auto=false` and handles overflow itself, by
relaunching or reinjecting. The probe found no way to switch off Codex's automatic compaction: it compacts mid-turn
when reported usage crosses about 90% of the model's context window, and its token-limit setting can only lower that
threshold. Codex keeps the first user message (the launch contract) verbatim through compaction and drops tool calls
and their outputs. The brief proposed first testing one lever, declaring a context window larger than the
provider's real one so that AEW's own path runs first, and otherwise accepting Codex's compaction with the residual
recorded.

D4 approves with a qualification: an AEW-owned proactive budget is preferred if Codex can be qualified for it;
otherwise Codex-native compaction is accepted as a recorded adapter residual; Codex is not rejected solely because
its compaction is mandatory.

### D5. Codex steer cancels a model call; held-session staging

Two differences from OpenCode under F9-A's `--when next-step` contract. A Codex steer posted while a model call is in
flight aborts that call and re-sends the request with the input included (OpenCode lets the call finish first);
running tools are not interrupted. And Codex can stage an input for a held or idle session without waking it only
through a path that carries no client message id and emits no item event, so admission of that message cannot be
confirmed. The brief recommended accepting the cancel and having the adapter refuse held-session delivery rather
than stage messages it cannot confirm.

D5 approves both: cancel-and-restart satisfies next-step semantics, and held-session staging without message identity
is refused.

## 3. Filing (lead developer)

- **Ledger:** MCD-01 to MCD-12.
- **D1 to D3** answer the reconciliation points of F38's adoption item in decisions due; the item now asks only for
  the adoption itself. The ledger marks v0.8's role-table entry (CEA-36) `superseded-by:` MCD-04 for its
  `G_KNOWLEDGE_READ` cells and, as far as safe navigation goes, its `G_DERIVED_READ` cells (the * kept for the
  Reviewer and the Verifier), beside its existing supersession by GAE-17, and notes D1 on GAE-12
  and CEA-55, D2 on GAE-17 and CEA-54, and D3 on ADR-0017's switch (CMG-11). Register: F40 (D1), F21 (D2), F9 and
  F38 (D3).
- **ADR-0009, ADR-0006 and ADR-0017 are not amended now.** D1 takes effect at M6: the amendments of ADR-0009 and
  ADR-0006 for native source mutation are due with F40. D3 needs no ADR-0017 change; it is M6a profile-catalog work
  (F38).
- **D4 and D5** are filed on F24 (the Codex adapter) and F24.1 (its probe), and D5 on F9 (F9-A's delivery contract).
  C1 has no register row; its compaction policy is named on F24.1.
