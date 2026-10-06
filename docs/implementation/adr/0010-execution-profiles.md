# ADR-0010 — Execution profiles: model, provider and effort pinned per invocation

- **Status:** Accepted (M3, 2026-09-29). Operator-approved plan: `m3-ambiguity-report.md` §2.4.
  - Proposed in M3 step 0 and implemented in step 1. Subject to the M3 independent review (`m3-reviewer-brief.md`).
  - Amended 2026-10-06: Q12, the Lead attachment's profile and the reference models (designed, not built; register F31, F32).
- **Spec basis:**
  - WC §18: model routing is policy, not architecture.
  - WC §9.9 and KC §11: validation provenance "who" includes model/provider.
  - WC §17: a model change needs configuration and evaluation, never a lifecycle change.
  - KC §20: project overrides never weaken an invariant.
- **Evidence:**
  - `tests/unit/test_execution_policy.py` and the dispatch and provenance tests of step 1;
  - AT-14: the reviewer routed to its own profile, requested and effective model both recorded;
  - step 8 (`harness-conformance.md` §6): the first live runs of a pinned effort variant, and per-role routing through the policy alone;
  - step 9 (`m3-dogfood-report.md` §5): the model comparison routed a cheap implementer with strong reviewers and verifiers, and the reverse, by editing `routing.archetypes` only. All 147 role runs recorded in the dogfood and the comparison have `model_check: match`.
- **Nature:** an implementation choice. It adds a policy file, a pin on the invocation, and engine-owned provenance fields. It adds no authority: a model choice never changes what an invocation may do.

## Decision

### Policy
`.aew/policy/execution.yaml` (schema `aew/execution/v1`, `src/aew/policy/execution.py`) holds:

```yaml
schema: aew/execution/v1
configured: false            # no policy-selected execution until the operator configures it
harness: opencode            # default harness; a profile may name its own
profiles:                    # harness-neutral names; `effort` maps to a harness variant
  standard: {provider: <p>, model: <m>, effort: <e>, max_steps: <n>?, deadline_s: <s>?}
routing:
  default: standard
  archetypes: {reviewer: standard}
  classes: {"0": light}
  cards: {}
provider_env: []             # NAMES of env vars the harness *server* needs; never values; never the agent shell
```

**Location.**
- The file is at `policy.execution` in `project.yaml` when that key is present, and otherwise at the conventional path.
- Projects initialized before M3 have neither the key nor the file, and behave as **unconfigured**.
- Their hash-pinned manifest therefore needs no change.

**What `aew init` writes.** An unconfigured, commented template. There is **no built-in provider or model**.

**Validation.** The schema rejects:
- unknown fields, including any `api_key`-like entry or sampling knob in a profile;
- `provider_env` entries that are not bare variable names.

A consistency check refuses:
- routes to undefined profiles;
- a configured policy without a default route.

**Fail closed.** An invalid file makes every dispatch fail with `VALIDATION_FAILED`, and nothing is committed. `aew doctor` reports `policy:execution` as:
- WARN when unconfigured;
- PASS when configured;
- FAIL when invalid.

**Resolution precedence**, most specific first:
1. card id;
2. **effective** risk class (ancestor `min_descendant_class` floors apply);
3. archetype;
4. default.

### Pinning at dispatch
The single invocation factory (`Invocations.new_invocation`) pins the following on every invocation it creates, including observers and executors:

```text
inv.execution_profile = {profile, harness, provider, model, effort, max_steps, deadline_s,
                         selected_by: policy|lead, rule, policy_sha256}
```

- `rule` names the route that matched: `card:<id>`, `class:<n>`, `archetype:<name>`, `default`, `lead:profile`, `lead:model`, or `…+lead:effort`.
- **The field name.** It is `execution_profile`, not `execution`, because a non-mutating Ticket's `unit.execution` already names its attempt record (ADR-0008).
- **Lead overrides.** `work assign`, `work dispatch`, `work redispatch` and `invoke create` accept `--profile NAME`, or `--model PROVIDER/MODEL [--effort E]`, or `--effort E` alone to adjust the routed profile. These are recorded as `selected_by: lead`.
  - An explicit `--profile` or `--model` works even when the policy is unconfigured: the Lead deliberately chose.
  - `--effort` alone does not, because there is nothing to adjust.
- `aew harness launch` has **no** model flags. A relaunch reuses the pin, and a change needs a new invocation.
- **Unconfigured policy.** An invocation dispatched while the policy is unconfigured, with no override, records `execution_profile: null`, and a later launch is refused. Scripted roles, which never launch a harness, are unaffected.
- Editing the policy never changes an existing pin.

### Provenance
`submit` and `check run` stamp these **engine-owned** producer fields, taken from control state:
- `producer.execution_profile` (the pin);
- `producer.credential` (the id of the presenting credential);
- `producer.run` (the harness run in `inv.runs[]` holding that credential; `null` for a scripted role).

`ENGINE_OWNED_PRODUCER` (`role`, `invocation`, `role_card`, `execution_profile`, `run`, `credential`) is refused in submissions with `VALIDATION_FAILED`, naming the `producer.<field>`.

A self-declared `producer.model`, `provider` or `harness` stays accepted. The evidence schema describes these three as **declared, not verified**; only `execution_profile` is the engine's pin.

### Effective model
- **The adapter reads the model and variant actually used** from the harness and records them in the run record. A mismatch with the pin is flagged.
- **For OpenCode V2**, the adapter checks `providerID/id#variant` against `GET /api/model` before prompting, because an invalid variant is accepted at session create and fails only at execution. It then reads the effective model from `session.step.started` and from assistant messages.

## Consequences

- Model and effort choices are auditable per invocation and per evidence record. Changing the policy never changes an in-flight invocation.
- **Model-diverse review (R2)** becomes expressible as a routing entry with no engine change. Evaluating it stays future work (WC §22).
- **Routing is now measurable.** The dogfood's comparison showed that cost follows where the invocations are: review and verification were three of four runs, so a strong reviewer and verifier cost more than a strong implementer (`m3-dogfood-report.md` §5). Choosing a routing policy is model optimization (`future-work.md` D5), not part of this ADR.
- **Additive changes.**
  - Existing evidence is not rewritten.
  - New evidence gains three producer fields.
  - Dispatch output is unchanged; `invoke show` gains `execution_profile`.

## Amendment 2026-10-06 — Q12: the Lead's profile and the reference models (designed, not built)

The designer's Q12 decision (decision record [`decisions-2026-10-06-q12-hosting-and-lead-attachment.md`](../../design/decisions-2026-10-06-q12-hosting-and-lead-attachment.md)) extends this ADR; register F31 and F32 build it.

- **The Lead has a profile too.** AEW owns the requested and effective execution profile of each Lead attachment, as it
  does each invocation's, and records it with the attachment's provenance.
- **No silent override.** A harness-native setting that changes the model or profile must never cause AEW to record a
  different model or profile from the one that actually ran. Today a mismatch between the pin and the effective model
  is flagged; under Q12 what is recorded is what ran, with the mismatch attributable.
- **Reference models, not semantics.** The reference topology is GPT-6 Astra for the Lead, Laguna S2.1 as the default
  worker, and GPT-5.4 and approved open-source models as selectable workers (GPT-5.4 where its capability justifies
  the cost and rate-limit pressure). These are profiles in `policy/execution.yaml` like any other: no workflow
  semantics may depend on a model's name, and selection stays capability- and profile-based and attributable.
- **Qualification (the lead developer's addition, decision record §12, not the decision's text).** Each reference
  model is qualified through the pinned harness (exact provider and model ids, effort variants, a live-lane run) before
  it is relied on, as every profile is (F32).
