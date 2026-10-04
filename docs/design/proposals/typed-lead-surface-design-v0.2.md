# T1 — The typed Lead surface: one stage/action contract below transport, MCP as the first normal transport

- **Status:** **Design frozen — proposed for operator adoption**, v0.2, 2026-10-04. Not governing until accepted/merged. This version incorporates design-authority decisions on judgment binding, effective operation class, ActionProjection truthfulness, recovery-only primitive escape, broker-only MCP custody, stage-intent requirements, and server naming.
- **Prototype:** branch `review/t1-typed-lead-surface` of `tree/` (the frozen clone at `dcd43f1`; one commit, `af72ec5`), exported as `T1-typed-lead-surface.patch` beside this note. It is evidence that the seams are implementable; it is **not** merge-authorized and predates several v0.2 decisions below (§9).
- **Spec basis:**
  - WC §15.6: "An optional MCP adapter may expose the same engine later. CLI and MCP must never implement separate state authorities"; invariant 21, "No transport becomes an authority."
  - WC §16.4 (MCP providers) and §16.12 (adapter rule: a typed tool is an adapter over a provider, never a new provider class).
  - ADR-0005 and ADR-0009: credential custody; the Lead broker; "the Lead is symmetric".
  - F15 idea note v0.4 (`aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md`): §3 to §5 (operation classes, `PrimitiveSpec`, two surfaces), §7 (stages are non-blocking), §8 (policy drift), §9 to §11 (stage intents, crash and takeover), §12 to §13 (one legality source, incremental guard migration), §15 (`ActionProjection`), §17 (conditional publication), §20 to §21 (equivalence, gates). The designer adopted its direction on 2026-10-01 (register F15).
  - F15 design proposal v0.1 (`lead-workflow-efficiency-design-v0.1.md`): the stage table and the pilot.
  - `m4-ambiguity-report.md` §2.1 (`DispatchDecision`), §2.10 (stage commands, M4-E); `engine/dispatch.py`, `engine/primitives.py`, `engine/reasons.py`.
  - This review: `REVIEW.md` G2, §4.2, F-A; `ADR-0012-transaction-outbox-draft.md` D8 (what the outbox gives this surface).
- **Evidence:**
  - The dogfood (audit L1, T3, X1, X2): a median of 20 workflow commands and 34 model steps per Lead session; 261,000 cached tokens re-read per session; 51 of 887 `aew` commands refused, `ILLEGAL_TRANSITION` 32, argparse usage 8, `USAGE` 7; 37 `--help` lookups; `harness wait` in 110-second slices, 4 per session.
  - The prototype's tests, run in this directory's venv against the branch: 17 unit tests (`tests/unit/test_surface.py`), 2 end-to-end tests inside a real `aew lead session` with the fake harness (`tests/integration/test_lead_mcp.py`), the existing Lead-session, dispatch-conformance and harness suites (47), and the whole unit lane with the OpenCode, M3-defect and M4-dispatch regressions (808 passed, 1 skipped). Ruff clean; Pyright reports no errors.
  - Context cost, measured: the advertised tool list is 12 tools, 11,711 bytes compact JSON, about 2,900 tokens; the largest tool (`ticket_draft`) is 3,108 bytes. The result schema (5,521 bytes) is deliberately not advertised per tool.
  - The pinned OpenCode 2.0.18 OpenAPI (`tests/fixtures/opencode/openapi-2.0.18.min.json`) spells MCP configuration as `Config.InfoEncoded.mcp.servers.<name> = {type: "local", command: [...]}` with `Mcp.Protocol` "legacy" speaking revisions up to 2025-11-25. The public documentation describes a newer shape (`mcp.<name>.enabled`, no `servers` level); AEW follows the pinned schema, and the capability probe now checks the keys it relies on.
- **Nature:** an implementation of F15's interaction-surface direction. No transition, gate, authority rule or piece of provenance changes. What is added: a catalog (data), a runner that composes existing guarded operations, a result contract, and two adapters over them. Custody is unchanged in mechanism and strengthened in reach.

## 1. The decision, in one paragraph

The Lead's interface is a **catalog of typed actions** defined once below transport as data plus one runner. Each action names its argument schema, the engine primitives it expands to, the judgment-bearing inputs it carries, and its base operation class. The runner computes an **effective operation class per invocation** so an otherwise policy-resolved action becomes judgment-bearing when the Lead supplies a judgment-bearing override.

Every valid action call returns the same **`StageResult`**: committed revision, stage-intent identity where applicable, completed steps, exact stop boundary, payload, and an **`ActionProjection`** describing what is known to be available, blocked, or not yet queryable.

**MCP is the first normal Lead transport.** The Lead harness spawns `aew lead mcp`, a process with no AEW Lead credential, which forwards calls to the existing Lead broker. The broker retains credential custody and executes the common action runner. The MCP server is registered as **`aew-lead`**. `aew-run` and `aew-knowledge` remain separate capability namespaces even when they reuse the same transport library.

The CLI is a parity, recovery, conformance, and operator/debug adapter over the same catalog. The generic primitive `cli(argv)` escape exists in the catalog but is **not advertised to the model in the normal Lead surface**; it is enabled only by an explicit recovery/debug surface profile. Common consequential actions needed on the normal path receive dedicated typed tools rather than forcing the model back through a generic CLI escape. Existing primitive `aew` commands remain available to the operator and for recovery/conformance.

No transport decides legality, retries judgment, widens authority, or invents next actions. The Engine remains the sole legality and workflow authority.

## 2. Layering

```text
                  Lead's harness (OpenCode TUI)                 operator's shell / tests
                  tools: aew_lead_status, aew_lead_ticket_start, …        aew lead tool <name> --arguments …
                           │  MCP, newline JSON-RPC over stdio            │ argv
                           ▼                                              ▼
   Transport A   aew lead mcp  (server: aew-lead; holds NO AEW Lead credential)     Transport B  (aew.cli: _lead_tool)
                           │  bridge op  lead.tool {name, arguments}       │ inside a session: routed to the
                           ▼                                              │ broker as every Lead command is
                  Lead broker  (aew.harness.lead_broker; holds the Lead credential)
                           │
                  the contract   aew.surface.contract (catalog) + aew.surface.run (one runner, effective-class resolution)
                           │       StageResult + ActionProjection  (schemas/surface.schema.json)
                           ▼
                  Engine API  (every operation individually guarded: Lead, expected revision, gates, DispatchDecision)
```

The runner is the only module that knows a tool's steps. A transport never composes, retries or interprets; it carries arguments in and a `StageResult` out. This is what makes WC §15.6's rule checkable: one conformance test enumerates the catalog against the dispatch registry, one golden pins the harness projection, and the CLI enumeration test classifies the two new commands.

## 3. The contract (`aew.surface`)

### 3.1 The catalog, v1

| Tool | Kind | Class | Expands to (in order) | Judgment inputs | Launches | Status |
|---|---|---|---|---|---|---|
| `status {work_id?}` | query | MECHANICAL | — | — | | built |
| `resume {}` | query | MECHANICAL | — | — | | built |
| `work_show {work_id}` | query | MECHANICAL | — | — | | built |
| `explain {work_id?, entrypoint?, role?, card?, scope?, invocation?}` | query | MECHANICAL | `Dispatch.decide` on committed state | — | | built |
| `harness_status {invocation?}` | query | MECHANICAL | — | — | | built |
| `harness_wait {runs[], timeout_s?}` | wait | MECHANICAL | local run telemetry + committed-event wake | — | | built (one run; `--any` with ADR-0012) |
| `checkpoint {expect_rev, note?, next?}` | stage | MECHANICAL | `checkpoint` | — | | built |
| `ticket_draft {expect_rev, title, risk_class, scope[], goal[], contract[], plan?, …}` | stage | JUDGMENT_BEARING | `work.create`, `plan.propose` | `ticket_proposition`, `plan_proposal` | | built |
| `ticket_start {expect_rev, work_id, execution?}` | stage | POLICY_RESOLVED base | `work.assign` (+launch), `dispatch.launch`, `work.transition → RUNNING` | `execution_override` when supplied | yes | built prototype |
| `ticket_request_review {expect_rev, work_id, execution?}` | stage | POLICY_RESOLVED base | `work.transition → REVIEW_PENDING`, policy-resolved reviewer invocation(s), `dispatch.launch` | `execution_override` when supplied | yes | built prototype |
| `ticket_request_verification {expect_rev, work_id, review_evidence, execution?}` | stage | JUDGMENT_BEARING | `review.ingest`, `work.transition → VERIFY_PENDING`, policy-resolved verifier invocation(s), `dispatch.launch` | `accept_review_evidence`, plus `execution_override` when supplied | yes | built prototype |
| `ticket_prepare {expect_rev, work_id, verification_evidence, execution?}` | stage | JUDGMENT_BEARING | `verify.ingest`, queue/lease-aware prepare path, post-integration verification | `accept_verification`, plus `execution_override` when supplied | yes | **designed**; unavailable until M4-D/M4-E dependencies land |
| `integration_publish {expect_rev, work_id, prepared_candidate}` | decision tool | JUDGMENT_BEARING | `integrate.publish` | `publish_candidate` | no | **designed**; normal-surface replacement for generic CLI publication once M4-D integration semantics land |
| `cli {argv[], stdin?}` | primitive escape | JUDGMENT_BEARING default | one `aew` command | `undeclared` | | built prototype; **recovery/debug profile only**, not normal advertisement |

Publication is **not a stage** and is never automatic merely because preparation succeeded. In the frozen design, the normal typed surface gains `integration_publish`, a single-primitive **judgment-bearing decision tool**. Calling it is the Lead's attributable publication decision; the Engine still rechecks the lease, candidate, guards, and revision. The later conditional `ticket_submit_integration --publish-if-clean` remains separate future work and may exist only if F15 §17's conditional authorization semantics are accepted.

The generic `cli` escape remains available for recovery/debug/conformance profiles but is not the normal way to publish.

Why this catalog: the F15 proposal's five clean-path rows plus the three reads a Lead makes between steps, the wait, the checkpoint the handoff needs, and the escape hatch. The catalog is small on purpose (§4.5): stages, not primitives, are listed; the primitive command surface stays behind one recovery/debug escape rather than being advertised as normal workflow.

### 3.2 Argument conventions

- **Closed schemas.** Every object schema is `additionalProperties: false` (tested). A wrong option is a schema violation the harness and the server both see; it cannot reach the engine as a refusal. This is how the argparse and `USAGE` share of the refusal taxonomy (15 of 51) disappears.
- **`expect_rev` is required on every stage and absent on every query.** It is the CAS the engine already demands; the value is the `revision` of the caller's last result, so no status read is needed to obtain it (X2, L1). The tool description says so in one sentence.
- **Free text is data.** Titles, goals, contract clauses, scopes, plan bodies, notes and reasons arrive as JSON strings and are passed to the engine as values. No shell is ever between the model and the engine, so the whole ingress hardening class (B1 `--fields`, I5 YAML pitfalls, M3-D2 byte-order marks, PowerShell here-strings) has nothing to defend against on this path. `--fields` stays for the CLI transport.
- **Execution overrides** (`--profile`, `--model`, `--effort`, ADR-0010) are one optional `execution` object on every dispatching stage, recorded by the engine as `selected_by: lead` exactly as today.
- **Effective operation class is per call.** A catalog row has a base class, but supplying a judgment-bearing override (including `execution`) promotes that invocation to `JUDGMENT_BEARING`. The effective class is recorded in `StageResult`, governs retry/auto-run behavior, and never silently drops back to the base class.
- **No credential is ever an argument.** The schemas have no such field; `cli` refuses `--token` through the broker's existing rule; results are scrubbed of credential-bearing keys before they leave the runner, and the bridge redacts credential strings on top.

### 3.3 `StageResult` and `ActionProjection` (`schemas/surface.schema.json`, closed)

```text
StageResult {
  ok
  surface            "aew/surface/v1"
  tool
  base_operation_class
  effective_operation_class
  revision
  generation
  stage_intent_id | null
  policy_digest | null
  completed_steps[]  {primitive, operation_class, revision | null, summary, refs[],
                      retried_after_stale_revision?}
  stopped | null     {at, boundary, error: {code, message, details}}
  result
  projection         ActionProjection
}

boundary ∈ {
  refused, stale_revision, stale_authority, stale_policy, permission,
  launch_failed, not_found, judgment_required, unavailable, error
}

ActionProjection {
  revision
  generation
  subject (unit id | "project")
  state

  actions[] {
    action
    arguments
    operation_class
    availability      AVAILABLE | BLOCKED | UNKNOWN
    auto_runnable
    reason_codes[]
    cli_fallback | null
  }

  decisions_required[] {
    decision
    subject
    evidence[]
    tool | null
    arguments | null
    availability      AVAILABLE | BLOCKED | UNKNOWN
    default: "NONE"
    cli_fallback | null
  }

  blockers[]          {code, message, details?}
  anomalies[]
  hints[]             reader-only prose; never parsed
  runs[]              local telemetry with explicit source/currentness
}
```

`availability` is deliberately tri-state. `BLOCKED` means an accepted queryable guard says no. `UNKNOWN` means AEW cannot yet answer without execution because the relevant guard has not been migrated to the common query substrate. `UNKNOWN` must never be rendered or treated as `BLOCKED`, and `auto_runnable` is false unless availability is `AVAILABLE` and the **effective** operation class is non-judgment-bearing.

Every **well-formed** tool call that reaches the runner returns a `StageResult`, including Engine refusals and partial-stage stops. JSON-schema/transport validation failures occur before the runner and are adapter/protocol input errors; they commit nothing and do not pretend to be Engine refusals. This distinction is part of transport conformance.

For a valid call, the model receives the Engine's own refusal code/message, any steps that already committed, and the current projection. Only an implementation defect escapes as an unstructured server error. The MCP adapter sets `isError` from `StageResult.ok` without discarding the structured content.

The projection is derived in `aew.surface.projection` from accepted query surfaces and explicit local telemetry. For a mutating Ticket in READY it asks the dispatch predicate and can report `ticket_start` as `AVAILABLE`; RUNNING with an ended run may name `ticket_request_review`; REVIEW_PENDING with a named review report may require `ACCEPT_REVIEW_EVIDENCE`; VERIFY_PENDING may require `ACCEPT_VERIFICATION`; verification failure may require `CLASSIFY_FAILURE`; COMMIT_READY may require `PUBLISH`; INTERRUPTED may require `RECONCILE`.

Until transition/ingest guards are queryable, those actions remain present only as `availability: UNKNOWN`, never falsely blocked or auto-runnable. A live run adds `harness_wait` with bound run identities. Decisions never carry a default.

The projection is not a second planner. It exposes what accepted Engine/query semantics can establish now, plus explicit `UNKNOWN` where the Engine cannot yet answer.

### 3.4 Stop and retry rules

A stage is one tool call, **not one atomic commit**. Each primitive step remains its own durable legal transition. Because a multi-step stage can be interrupted between those transitions, **mutating stages are not enabled on the normal Lead surface until the stage-intent journal is implemented**.

The frozen rules are:

1. **Caller CAS.** The stage begins by opening a durable `StageIntent` against `expect_rev`. If `expect_rev` is stale, no intent and no workflow mutation commit.
2. **Intent first.** Creating the intent is the stage's first controlled commit and records the tool, bound arguments/judgment inputs, effective operation class, starting revision, policy/dependency digest, Lead generation, and planned primitive sequence. Subsequent stage steps advance from the revision returned by the intent commit; intent creation must not manufacture a self-inflicted stale-revision failure.
3. **First refusal stops.** A refused primitive stops the bundle. Completed steps remain committed and the intent records the stop boundary; nothing is rolled back.
4. **Later stale revision.** A later `STALE_REVISION` may be retried **once** only when the affected step is `MECHANICAL` or `POLICY_RESOLVED`, the stage's **effective** operation class is non-judgment-bearing, the bound policy/dependency digest is unchanged, and the Engine recomputes legality against the current revision. Otherwise the stage stops for renewed Lead judgment.
5. **Judgment is never replayed.** Any stage invocation carrying judgment-bearing input—including an execution override—is never automatically retried after intervening state/policy movement.
6. **Policy drift.** A changed bound policy/dependency digest stops as `STALE_POLICY`; the runner never silently expands the old stage under new policy.
7. **Launch failure after committed dispatch.** The stage stops as `launch_failed`; committed dispatch/run identity remains authoritative and is surfaced by the intent/result.
8. **Crash/takeover.** `resume` surfaces nonterminal intents and their committed steps. A replacement Lead explicitly chooses `CONTINUE_STAGE` or `ABANDON_STAGE`; recovery does not infer intent from current state alone.

The prototype's current partial-stage behavior remains useful evidence, but normal mutating-stage dogfood waits for these journal/drift rules.

### 3.5 Classification and conformance

A catalog entry has a **base operation class**, while every invocation has an **effective operation class**.

- Any explicit judgment input promotes the call to `JUDGMENT_BEARING`.
- A stage containing a judgment-bearing primitive or requiring a Lead acceptance is judgment-bearing regardless of other steps.
- A policy-resolved stage remains `POLICY_RESOLVED` only when every consequential choice is actually resolved by accepted policy for that invocation.
- A `MECHANICAL` stage contains no unresolved choice and no policy-selected discretionary branch.
- Unknown classification fails closed to `JUDGMENT_BEARING`.

Accordingly, `ticket_start` and `ticket_request_review` are policy-resolved only without Lead execution overrides. `ticket_request_verification` and `ticket_prepare` remain judgment-bearing because they accept named reports. `integration_publish` is judgment-bearing because invoking it is the publication decision. The recovery `cli` escape is judgment-bearing by default.

The projection never marks a judgment-bearing invocation auto-runnable, and retry logic uses the effective class, not the catalog label.

Tests pin the catalog's structure: every schema valid and closed; every dispatching tool names at least one registered dispatch entrypoint and always `dispatch.launch` (custody), and no non-dispatching tool names one; every always-judgment-bearing tool names its judgments; conditionally judgment-bearing fields are declared and tested to promote the effective class; every built tool has a runner and every runner a tool; designed tools are never listed and are refused if called; the **normal advertised** tool list stays under a byte budget and excludes recovery/debug-only tools; the equivalence of `ticket_draft` with its primitive sequence on two identical projects (v0.4 §20); the CLI transport returns the same contract.

### 3.6 What moves into the engine for M4-E

The prototype composes **existing** operations and does not touch the engine. Four things the idea note requires belong in the engine, and the contract already has their seams:

- **The stage-intent journal (§9 to §11) — required before normal mutating-stage enablement.** Before any workflow mutation, the Engine creates a `StageIntent` bound to the caller's `expect_rev`, Lead generation, arguments/judgment inputs, effective class, policy/dependency digest, and planned primitive sequence. It is hot only while active and cold when terminal under ADR-0011. `resume` surfaces nonterminal intents; a replacement Lead chooses `CONTINUE_STAGE` or `ABANDON_STAGE`. The intent is the durable source for partial-stage recovery; `StageResult.completed_steps` is only the call-result projection of that durable record.
- **Policy drift (§8) — required with the journal.** The intent records the policy/dependency digest it expanded under (`DispatchDecision.dependency_digests` supplies the material); a change mid-bundle stops with `STALE_POLICY`.
- **Queryable transition and ingest guards (§13).** Today `auto_runnable` is truthful only for dispatches, because only `DispatchDecision` has a query form. Migrating the transition and ingest guards onto the same substrate makes `ticket_request_review` and `ticket_request_verification` answerable before they run, and makes `explain` cover them.
- **Policy-resolved review and verification sets.** The prototype launches the role's default card; the stage must resolve the cards the effective gates require (`review_r1`, the verification gates) and launch each, returning every invocation and run (the F15 proposal's row 3 and 4).

Also for M4-E: `requires_disposition` as a gate input (F15 decision, 2026-10-01); `ticket_prepare` built once M4-D's lease exists; `ticket_submit_integration --publish-if-clean` (§17) on the queue.

## 4. Transport A: MCP, broker-side

### 4.1 Where the process runs, and custody

OpenCode's Lead projection declares one local MCP server, **`aew-lead`**, with the command `aew lead mcp`. OpenCode spawns it **in the TUI's curated environment** (ADR-0009: operating-system basics, `PATH` with `aew` first, broker coordinates/transport material required by the existing bridge, and the projection; **no AEW Lead credential and no provider key**). Any bridge-authentication material is transport/session capability only and must not itself be accepted by Engine mutation paths as a Lead credential.

The MCP process forwards each valid `tools/call` as broker operation `lead.tool {name, arguments}` over the existing bridge. The broker runs the common action runner with the Lead credential it already holds, under `dispatch.channel("lead_mcp")`, so every dispatch records the ingress surface without creating a second authority.

This is the custody model unchanged: the model exercises the Lead's operations without possessing, printing or inheriting the credential. The end-to-end test checks it the way the Lead-session tests do: the transcript, the session's output and the server's environment carry no credential string, and `AEW_LEAD_TOKEN` is absent from the environment the probe sees. The broker's refusals apply to the `cli` tool because that tool runs through the same `run_cli` function the `lead.cli` operation uses (now a module function both call): credential-emitting commands, `--token`, dispatch without `--launch`, read-only commands and other projects are refused with the same codes (tested).

When the broker closes (takeover, handoff, release elsewhere), every tool call returns the bridge's `STALE_AUTHORITY` as a tool outcome; the harness keeps running read-only, as today.

**No direct MCP authority mode.** `aew lead mcp` always requires a live broker/session and never consumes `AEW_LEAD_TOKEN` to execute tools in-process. If no broker is available it fails closed. The operator already has the primitive CLI/recovery surface; duplicating Lead credential custody inside an MCP child would add a second security mode for no required capability.

### 4.2 Projection and probe changes (`harness/opencode/projection.py`, `capabilities.py`)

- `lead_config()` gains `mcp: {servers: {"aew-lead": {type: "local", command: ["aew", "lead", "mcp"]}}}`, spelled as the pinned 2.0.18 schema spells it (a unit test validates the whole Lead configuration against `Config.InfoEncoded` from the fixture).
- `LEAD_RULES` allows the `aew-lead` tool namespace required by the normal surface: the operator is present and every tool is engine-refused or engine-committed, exactly like the `shell aew *` allow it sits beside.
- The Lead's system text names the typed surface as the normal workflow path. Primitive shell/CLI mutation is described as recovery/debug behavior, not as an equivalent default workflow. Read-only diagnostic shell access may remain available under the existing policy.
- The capability probe requires `Config.InfoEncoded.mcp` and `Mcp.LocalConfigEncoded.{type, command}` from a served server's OpenAPI, so a release that respells MCP configuration fails closed at launch instead of silently ignoring the server.

The projection golden (`projection-lead.golden.json`) was regenerated; its diff is exactly these three additions.

### 4.3 The protocol layer (`aew.surface.mcp`)

Dependency-free and small by intent (AEW pins what it speaks and a probe can check a harness against it): newline-delimited JSON-RPC 2.0 over stdio; `initialize` echoing a known protocol revision (2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05) or answering with the newest; `notifications/initialized`; `ping`; `tools/list` rendered from the **surface-profile-filtered** catalog with MCP annotations (`readOnlyHint`, `idempotentHint`); normal mode excludes `cli` and any designed/unavailable tool. `tools/call` returns `StageResult` as `structuredContent` (plus a compact text rendering) with `isError = not ok`. JSON-schema-invalid arguments, unknown tools, designed/unavailable tools, and profile-concealed tools are adapter input errors and commit nothing; unknown methods remain protocol errors. Empty resources/prompts are fine. Logging goes to stderr only; stdout is protocol only.

### 4.4 Context cost

The prototype measured 12 catalog tools at 11,711 bytes compact JSON (about 2,900 tokens), before v0.2's normal/recovery split. Acceptance measures the **normal advertised surface**, not the internal catalog. The normal surface must remain under the existing 12,000-byte budget and 16-tool ceiling; recovery/debug-only `cli` does not consume normal prompt context.

Stages/queries are advertised instead of primitive commands, and the result schema is not repeated per tool. Progressive disclosure/tool filtering may reduce cost further, but any claimed saving must be measured against the pinned harness rather than inferred.

## 5. Transport B: CLI parity, recovery, and conformance

`aew lead tool <name> [--arguments JSON | --fields -]` invokes the **same catalog and runner** and returns the same `StageResult`. `--list` can show the catalog with visibility/profile metadata for debugging/conformance.

Inside a Lead session the command routes through the broker. Outside a model harness, operator-authorized CLI use follows existing ADR-0005 credential rules.

The generic `cli {argv[], stdin?}` action remains in the catalog as a recovery/debug primitive escape, but normal MCP `tools/list` does not advertise it. A recovery/debug surface profile may expose it explicitly. This preserves the primitive surface without training the normal Lead back onto the shell choreography F15 is meant to remove.

Stage commands as first-class CLI verbs (`aew ticket draft …`) are not required. If later desired, they are generated adapters over catalog schemas and never become a second semantic implementation.

## 6. The role surface (`aew-run`), designed only

The separate **`aew-run`** server exposes the run bridge's three operations (`whoami`, `check.run`, `submit`) become three tools served by a thin stdio client **inside the sandbox**, forwarding to the supervisor's bridge exactly as the `aew` CLI client does today; the supervisor keeps the credential. The one design gain beyond ergonomics: `submit` takes the report as a typed object whose schema is the evidence schema, which ends the YAML-frontmatter failure class (M3-D2, D5, D7, I5). Same code shape as `aew.surface.mcp` with a different operation table; not prototyped (it needs the role projection, the per-run OpenCode config and a containment check that the server runs inside the bubblewrap boundary).

## 7. Dispatch conformance

- Dispatches made through the typed MCP surface are carried by channel `lead_mcp`; parity/recovery CLI calls retain their existing CLI/Lead-broker channels. Channel records ingress provenance only; it never changes legality. The provenance recorded on invocations and runs (M4-A) therefore says which surface dispatched; `test_dispatch_conformance` should gain the `lead_mcp` channel alongside `lead_broker.relay` (not added in the prototype).
- The CLI enumeration (`test_dispatch_decision`) classifies `lead tool` and `lead mcp` as non-dispatching **commands**: neither is a dispatch route of its own; a dispatching stage reaches the registry through `work_assign` and `invoke_create`, and the catalog test proves every dispatching tool names a registered entrypoint.
- `explain` is `Dispatch.decide` on committed state: query equals execution, as the conformance test already proves for the CLI.

## 8. What ADR-0012 gives this surface

- `harness_wait {runs[]}` already has the wait-any shape; the runner refuses more than one run until the wake file exists, then blocks on it and checks both lanes (run records and committed events that end a run). The tool's contract does not change.
- The `ActionProjection` behind the dashboard's `/attention` is recomputed when an affecting event lands, not per poll; the same projection module serves `StageResult`, `status`, the dashboard and later the scheduler (v0.4 §12: one legality source).
- A session's cursor is the revision every result already carries.

## 9. The prototype: what is there, what it proves, what it does not

**Files** (branch `review/t1-typed-lead-surface`, one commit): `src/aew/surface/{__init__,contract,run,projection,mcp}.py`; `src/aew/schemas/surface.schema.json` and its registration; `harness/lead_broker.py` (the `lead.tool` operation; `run_cli` as a shared module function); `cli/commands.py` (`aew lead tool`, `aew lead mcp`); `harness/opencode/{projection,capabilities}.py`; `tests/unit/test_surface.py`; `tests/integration/test_lead_mcp.py`; `tests/helpers/mcp_probe_agent.py` (a scripted MCP client standing in for the Lead's harness); the regenerated Lead projection golden; the CLI enumeration classification.

**What the tests prove.**
- End to end, inside a real `aew lead session` with the fake harness: the probe spawns `aew lead mcp`, completes the handshake, lists the tools, and in one session runs `status`, `ticket_draft` (two steps, revision +2), `cli` (`plan accept`), `explain` (allowed, `work.assign`), `ticket_start` (assign, **launch of a real supervised run**, transition to RUNNING; the launch step records no revision of its own), `harness_wait` (the run ends), and `status` (RUNNING). The projection on the `plan accept` result already named `ticket_start` as auto-runnable from the dispatch predicate. No credential anywhere; the invariant oracle passes afterwards.
- The `cli` tool keeps every broker refusal, with the engine's codes and messages, and commits nothing.
- The contract: closed schemas, catalog conformance, equivalence with the primitive sequence, the three stop rules, result validation on every call, credential scrubbing, the CLI transport's parity, the MCP framing including malformed input and batches, and the projection's validity against the pinned OpenCode schema.
- Nothing else moved: the unit lane and the regressions named above pass unchanged apart from the regenerated golden and two classified commands.

**Not built in the prototype, and therefore required before the corresponding frozen behavior ships:** `ticket_prepare`; `integration_publish`; the stage-intent journal and `STALE_POLICY`; effective-class promotion for judgment-bearing overrides; tri-state projection availability; queryable transition/ingest guards; policy-resolved review/verification card sets; wait-any via ADR-0012; the `aew-run` role server; broker-only/no-direct MCP enforcement; recovery-profile filtering of `cli`; the `aew-lead` server rename; takeover-mid-session coverage; a live OpenCode 2.0.18 MCP spawn/list check; and `lead_mcp` dispatch-channel conformance.

**To run it:** `.venv` in this directory has the branch installed editable. `python -m pytest tests/unit/test_surface.py tests/integration/test_lead_mcp.py` from `tree/`.

## 10. Evaluation and completion criteria (for M4-E, from F15 §21)

Hard gates: no false advance in the seeded corpus; every consequential judgment has an attributable durable record before the dependent transition; no normal mutating stage without a durable `StageIntent`; no automatic retry of judgment-bearing invocations; anomaly catch at least equal to the primitive baseline; recovery correctness across crash, retry, policy drift, takeover and mixed-mode walks. Conformance prerequisites: stage/primitive equivalence for every built stage (the prototype has it for `ticket_draft`; `ticket_start` and the two request stages need the fake-harness form); query/execute equivalence for every migrated guard; `PrimitiveSpec` coverage for every staged primitive; ADR-0011 bounded hot state for journal and anomalies.

Reported, never traded against the gates: workflow-command steps per Ticket (target from the proposal: at least 25% fewer on matched single-Ticket runs, the median from 20 toward 15), refusals per session (the taxonomy should lose its usage and argparse share entirely), reads between mutations (should approach zero), `--help` lookups, cached input tokens per session, wall-clock, time to consequential decision. Measured by the preregistered dogfood with the instrumented command log (T3 of the audit, already done) against the M3 baseline, with the primitive path as the control arm. Context: the tool list's bytes per prompt, compared with the Lead guide's.

## 11. Sequencing

- **M4-D:** land the common catalog/runner skeleton, broker `lead.tool`, broker-only `aew-lead` MCP transport, read/query tools, ADR-0012-backed wait-any, CLI parity adapter, and conformance/profile filtering. These do not create new multi-step mutation semantics.
- **M4-E:** land the stage-intent journal, policy/dependency drift binding, effective-class promotion, queryable transition/ingest guards, policy-resolved review/verification sets, governed mutating stages, `ticket_prepare`, typed `integration_publish`, primitive/stage equivalence tests, `lead_mcp` channel conformance, and live OpenCode 2.0.18 MCP spawning.
- **M4-H:** run the paired F19 evaluation against the primitive baseline.
- **M6:** add `aew-knowledge` as a separate capability namespace/server over shared transport libraries; F13 disclosure decides which tools are advertised to each role/context.

## 12. Frozen designer decisions

1. **Review acceptance and verification dispatch stay one typed stage.** `ticket_request_verification` explicitly means: accept the named bound review evidence, durably record that Lead judgment through `review.ingest`, then—only after that commit succeeds—advance/dispatch verification. A separate acceptance tool would add ceremony without adding an authority boundary. The same rule applies to `ticket_prepare` and named verification evidence.
2. **Generic `cli` is not a normal model tool.** It is catalogued for recovery/debug/conformance and exposed only under an explicit recovery/debug surface profile. Normal consequential paths that need a primitive decision receive dedicated typed tools such as `integration_publish`.
3. **Unqueryable actions remain visible as `availability: UNKNOWN`.** They are neither omitted nor represented as blocked. They cannot be auto-runnable until the corresponding guard is queryable.
4. **No direct MCP credential mode.** `aew lead mcp` always uses a live Lead broker and never consumes `AEW_LEAD_TOKEN` to execute tools in-process.
5. **StageIntent is mandatory before normal mutating-stage dogfood.** Read/query/wait transport work may ship earlier; multi-step mutating stages remain unavailable until durable intent/policy-drift recovery exists.
6. **Lead MCP server name is `aew-lead`.** `aew-run` and `aew-knowledge` are separate capability namespaces/servers. They may reuse the same transport implementation but do not share authority or advertisement by accident.
7. **Effective operation class is invocation-specific.** Judgment-bearing overrides promote policy-resolved actions to judgment-bearing and disable automatic retry/auto-run.
8. **Transport validation and Engine refusal are distinct.** Invalid tool arguments are adapter/protocol input errors; a valid call refused by the Engine returns a structured `StageResult`.
9. **Publication gets a typed judgment tool.** Normal workflow does not depend on the generic CLI escape to publish.

There are no remaining designer-level questions in T1 v0.2. Operator adoption remains the approval step; implementation may return a concrete contradiction as a design defect rather than silently changing these semantics.

## 13. Alternatives considered

- **The broker itself speaking MCP over its socket** (no child process). Rejected for now: OpenCode 2.0.18 configures local servers by command; a remote (HTTP) server would need the TUI to reach a loopback port, and the bridge's HMAC challenge does not map onto MCP's HTTP auth. The child-process form keeps the bridge as the one custody protocol and costs one small process.
- **Stage commands as CLI verbs first.** Rejected. The semantic contract lives below transport; MCP is the first normal Lead vehicle. CLI remains parity/recovery/conformance and may generate typed adapters from the same catalog later.
- **An MCP SDK dependency.** Rejected: the pinned release's protocol revisions are a fact to probe, the needed subset is small, and the airgap bundle should not grow for a transport layer AEW can own in two hundred lines.
- **Advertising the result schema per tool.** Rejected on measurement (66 KB per prompt); the result is structured content either way.
- **A generic `advance` tool** ("take the next step the engine computes"). Rejected: it can cross judgment boundaries without an attributable judgment. `ActionProjection` names what is known; the Lead invokes a specific typed action.
- **Generic `cli` advertised in normal mode.** Rejected: it preserves the shell choreography and ingress path F15 is intended to remove, and gives the model an easy bypass around typed stages. It remains explicitly available in recovery/debug profiles.
- **Direct MCP mode with a Lead token in the MCP process.** Rejected: it creates a second credential-custody mode for no required normal capability.
- **Boolean action availability.** Rejected: before all guards are queryable, `false` conflates known-blocked with unknown. The contract uses `AVAILABLE | BLOCKED | UNKNOWN`.
