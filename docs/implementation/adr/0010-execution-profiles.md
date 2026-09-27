# ADR-0010 — Execution profiles: model, provider and effort pinned per invocation

- **Status:** Proposed (M3 step 0, 2026-09-27); finalized at M3 closeout.
- **Spec basis:**
  - WC §18: model routing is policy, not architecture.
  - WC §9.9 and KC §11: validation provenance "who" includes model/provider.
  - WC §17: a model change needs configuration and evaluation, never a lifecycle change.
  - KC §20: project overrides never weaken an invariant.
- **Nature:** an implementation choice. It adds a policy file, a pin on the invocation, and engine-owned provenance fields.

## Decision

### Policy
`.aew/policy/execution.yaml` (schema `aew/execution/v1`) holds:

```yaml
schema: aew/execution/v1
configured: false            # launch is refused until the operator configures it (the checks.yaml pattern)
harness: opencode            # default harness for launches
profiles:                    # harness-neutral names; `effort` maps to a harness variant
  standard: {provider: <p>, model: <m>, effort: <e>}
routing:
  default: standard
  archetypes: {reviewer: standard}
  cards: {}
  classes: {}
provider_env: []             # names of env vars the harness *server* needs (never values; never the agent shell)
```

- There is **no built-in provider or model**. `aew init` writes the unconfigured template.
- Resolution precedence, most specific first: card, then class, then archetype, then default.

### Pinning at dispatch
- The single invocation factory (`_new_invocation`) pins:

  ```text
  inv.execution = {profile, harness, provider, model, effort, selected_by: policy|lead, policy_sha256}
  ```

- The Lead may override on dispatch with `--profile`, or `--model` and `--effort`. The override is recorded as `selected_by: lead`.
- `aew harness launch` has **no** model flags. A relaunch reuses the pin, and a change needs a new invocation.
- An invocation dispatched while the policy is unconfigured records `execution: null`, and its launch is refused. Scripted roles, which never launch a harness, are unaffected.

### Provenance
- `submit` and `check run` stamp these **engine-owned** fields, which are added to `ENGINE_OWNED` so submitters cannot supply them:
  - `producer.execution` (the pin);
  - `producer.run`;
  - `producer.credential` (the token id).
- A self-declared `producer.model` stays accepted and is labelled *declared*.

### Effective model
- **The adapter reads the model and variant actually used** from the harness and records them in the run record. A mismatch with the pin is flagged.
- **For OpenCode V2**, the adapter checks `providerID/id#variant` against `GET /api/model` before prompting, because an invalid variant is accepted at session create and fails only at execution. It then reads the effective model from `session.step.started` and from assistant messages.

## Consequences

- Model and effort choices are auditable per invocation and per evidence record. Changing the policy never changes an in-flight invocation.
- **Model-diverse review (R2)** becomes expressible as a routing entry with no engine change. Evaluating it stays future work (WC §22).
