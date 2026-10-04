# T1 — The typed Lead surface: one stage/action contract below transport, MCP as the first normal transport

- **Status:** **Design note v0.1 with a working prototype**, written by the architecture review (thread T1 of `HANDOFF.md`), 2026-10-04. Not accepted. Direction given by the operator for this thread: MCP may be the first normal F15 transport; stage commands need not ship as CLI first; the contract is defined below transport; the CLI is a thin parity and fallback adapter, never the semantic source.
- **Prototype:** branch `review/t1-typed-lead-surface` of `tree/` (the frozen clone at `dcd43f1`; one commit, `af72ec5`), exported as `T1-typed-lead-surface.patch` beside this note. It is a prototype of the design, built to prove the seams and the custody argument, not a change proposed for merge as it stands (§9).
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

The Lead's interface is a **catalog of typed tools** defined once, below any transport, as data plus one runner: each tool names its argument schema, the engine primitives it expands to, the judgments its arguments must carry, and its operation class. Every call returns the same **`StageResult`**: the committed revision, the steps that completed, where and why a bundle stopped, the tool's payload, and an **`ActionProjection`** of what is open next. **MCP is the first normal transport**: the Lead's harness spawns `aew lead mcp`, a credential-less process that forwards each call to the Lead broker, which runs the tool with the credential it already holds. **The CLI is a parity adapter**: `aew lead tool <name> --arguments {...}` runs the same catalog through the same runner, and the existing `aew` command set stays the primitive and recovery surface, reachable from both transports as the `cli` tool. Nothing in either transport decides legality; the engine does, at every step, exactly as today.

## 2. Layering

```text
                  Lead's harness (OpenCode TUI)                 operator's shell / tests
                  tools: aew_status, aew_ticket_start, …        aew lead tool <name> --arguments …
                           │  MCP, newline JSON-RPC over stdio            │ argv
                           ▼                                              ▼
   Transport A   aew lead mcp  (aew.surface.mcp; holds NO credential)     Transport B  (aew.cli: _lead_tool)
                           │  bridge op  lead.tool {name, arguments}       │ inside a session: routed to the
                           ▼                                              │ broker as every Lead command is
                  Lead broker  (aew.harness.lead_broker; holds the Lead credential)
                           │
                  the contract   aew.surface.contract  (catalog)  +  aew.surface.run  (one runner)
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
| `harness_wait {runs[], timeout_s?}` | wait | MECHANICAL | local run telemetry | — | | built (one run; `--any` with the outbox, §8) |
| `checkpoint {expect_rev, note?, next?}` | stage | MECHANICAL | `checkpoint` | — | | built |
| `ticket_draft {expect_rev, title, risk_class, scope[], goal[], contract[], plan?, …}` | stage | JUDGMENT_BEARING | `work.create`, `plan.propose` | `ticket_proposition`, `plan_proposal` (the arguments) | | built |
| `ticket_start {expect_rev, work_id, execution?}` | stage | POLICY_RESOLVED | `work.assign` (+launch), `dispatch.launch`, `work.transition → RUNNING` | — | yes | built |
| `ticket_request_review {expect_rev, work_id, execution?}` | stage | POLICY_RESOLVED | `work.transition → REVIEW_PENDING`, `invoke.create.mutating` (reviewer, +launch), `dispatch.launch` | — | yes | built |
| `ticket_request_verification {expect_rev, work_id, review_evidence, execution?}` | stage | JUDGMENT_BEARING | `review.ingest`, `work.transition → VERIFY_PENDING`, `invoke.create.mutating` (verifier, +launch), `dispatch.launch` | `accept_review_evidence` (the named report) | yes | built |
| `ticket_prepare {expect_rev, work_id, verification_evidence, execution?}` | stage | JUDGMENT_BEARING | `verify.ingest`, `work.transition → COMMIT_READY`, `integrate.prepare`, post-integration verifier (+launch) | `accept_verification` | yes | **designed**: in the catalog, never listed to a model, refused if called |
| `cli {argv[], stdin?}` | primitive | JUDGMENT_BEARING (default) | one `aew` command | `undeclared` | | built |

Publication is **not** a stage. `integrate publish` stays an explicit decision through `cli` (the F15 proposal's choice for the first release; the idea note's §17 conditional authorization is the later `ticket_submit_integration --publish-if-clean`, which needs M4-D's queue and lease). Lead acquisition, handoff, takeover and release have no tool and never will: they are operator actions at the operator's terminal (ADR-0005), and the broker refuses them through `cli` as it refuses them through the shell.

Why these twelve: the F15 proposal's five clean-path rows plus the three reads a Lead makes between steps, the wait, the checkpoint the handoff needs, and the escape hatch. The catalog is small on purpose (§4.5): stages, not primitives, are listed; the seventy primitive commands sit behind one tool.

### 3.2 Argument conventions

- **Closed schemas.** Every object schema is `additionalProperties: false` (tested). A wrong option is a schema violation the harness and the server both see; it cannot reach the engine as a refusal. This is how the argparse and `USAGE` share of the refusal taxonomy (15 of 51) disappears.
- **`expect_rev` is required on every stage and absent on every query.** It is the CAS the engine already demands; the value is the `revision` of the caller's last result, so no status read is needed to obtain it (X2, L1). The tool description says so in one sentence.
- **Free text is data.** Titles, goals, contract clauses, scopes, plan bodies, notes and reasons arrive as JSON strings and are passed to the engine as values. No shell is ever between the model and the engine, so the whole ingress hardening class (B1 `--fields`, I5 YAML pitfalls, M3-D2 byte-order marks, PowerShell here-strings) has nothing to defend against on this path. `--fields` stays for the CLI transport.
- **Execution overrides** (`--profile`, `--model`, `--effort`, ADR-0010) are one optional `execution` object on every dispatching stage, recorded by the engine as `selected_by: lead` exactly as today.
- **No credential is ever an argument.** The schemas have no such field; `cli` refuses `--token` through the broker's existing rule; results are scrubbed of credential-bearing keys before they leave the runner, and the bridge redacts credential strings on top.

### 3.3 `StageResult` and `ActionProjection` (`schemas/surface.schema.json`, closed)

```text
StageResult {
  ok                 the whole tool completed (false when it stopped, whether or not steps committed)
  surface            "aew/surface/v1"
  tool, revision, generation
  completed_steps[]  {primitive, operation_class, revision | null, summary, refs[], retried_after_stale_revision?}
  stopped | null     {at: primitive, boundary, error: the engine's own {code, message, details}}
  result             the tool's payload (a query's report, a stage's ids, a cli command's output)
  projection         ActionProjection for the unit acted on (or created), else the project
}
boundary ∈ {refused, stale_revision, stale_authority, permission, launch_failed, not_found, usage,
            judgment_required, unavailable, error}

ActionProjection {                                 (F15 v0.4 §15)
  revision, generation, subject (unit id | "project"), state
  mechanical_actions[]   {action (tool), arguments (prefilled), operation_class, auto_runnable, reason_codes[],
                          available, cli | null}
  decisions_required[]   {decision, subject, evidence[], tool | null, arguments | null, default: "NONE",
                          available, cli | null}
  blockers[]             {code, message, details?}          (reason codes from the registry where they exist)
  anomalies[]            (v0.4 §19; empty in the prototype)
  hints[]                the engine's prose next actions for the subject, for a reader, never parsed
  runs[]                 the subject's runs with status and evidence (local telemetry)
}
```

Every refusal the engine makes, and every argument error, is a **tool outcome** (`ok: false`, `stopped`), not a protocol error: the model reads the engine's own code and message, the steps that did commit, and what is open now. Only a bug raises. The MCP adapter sets `isError` from `ok` so a harness renders it as a failed tool call without losing the structure.

The projection is derived in `aew.surface.projection`: for a mutating Ticket in READY it asks the dispatch predicate (`dispatch_explain`) and reports `ticket_start` with `auto_runnable: allowed` and the decision's blocking conditions as blockers (the end-to-end test observes `auto_runnable: true` on the result of `plan accept`, before the start); RUNNING with an ended run that produced evidence offers `ticket_request_review`; REVIEW_PENDING with review evidence raises `ACCEPT_REVIEW_EVIDENCE` with `ticket_request_verification` prefilled; VERIFY_PENDING raises `ACCEPT_VERIFICATION` pointing at `ticket_prepare` with `available: false` and the `cli` path; VERIFICATION_FAILED raises `CLASSIFY_FAILURE`; COMMIT_READY with a prepared candidate raises `PUBLISH`; INTERRUPTED raises `RECONCILE`. A live run always adds `harness_wait` with the run ids prefilled. Decisions never carry a default (§15: "default: NONE").

### 3.4 Stop and retry rules

A stage is one tool call, **not one atomic commit**: each step is its own durable transition with its own `via`, so every intermediate state is a legal, primitive-reachable state (v0.4 §9) and the recovery surface always applies.

1. **The first step's `STALE_REVISION` is the caller's CAS and stops the bundle** with nothing committed (tested: `completed_steps == []`, revision unchanged).
2. **The first refusal stops the bundle.** Completed steps are reported; nothing is undone (tested: a plan assurance naming an unknown card leaves the created Ticket, reports `stopped.at == "plan.propose"`, and projects the new unit).
3. **A `STALE_REVISION` on a later step** means another writer committed between two of our steps. A `MECHANICAL` or `POLICY_RESOLVED` step is re-run **once** against the current revision; the engine re-evaluates its guards, nothing is cached (M4-A: no old ALLOW). A `JUDGMENT_BEARING` step is never re-run: the judgment was made against a state that moved. The retry is recorded on the step (`retried_after_stale_revision`).
4. **Launch failure after a committed dispatch** stops with boundary `launch_failed`; the dispatch stands (the engine's own rule: "never raises after the launch commit without saying which run was recorded").
5. Policy drift (`STALE_POLICY`, §8) and the stage-intent journal (§9 to §11) are **engine** work for M4-E (§3.6); the runner does not emulate them.

### 3.5 Classification and conformance

A stage's class is the class of the judgment it stands for. `ticket_draft` is `JUDGMENT_BEARING` with its judgments carried as arguments; `ticket_request_verification` is `JUDGMENT_BEARING` because it accepts a report, and the report's id is the required input; `ticket_start` and `ticket_request_review` are `POLICY_RESOLVED` (the engine chooses card and profile from policy; an override is an attributable decision). `cli` is `JUDGMENT_BEARING` by the fail-closed default (v0.4 §3). The projection therefore never marks a judgment-bearing tool `auto_runnable`.

Tests pin the catalog's structure: every schema valid and closed; every dispatching tool names at least one registered dispatch entrypoint and always `dispatch.launch` (custody), and no non-dispatching tool names one; every judgment-bearing tool names its judgments and no other tool does; every built tool has a runner and every runner a tool; designed tools are never listed and are refused if called; the tool list stays under a byte budget; the equivalence of `ticket_draft` with its primitive sequence on two identical projects (v0.4 §20); the CLI transport returns the same contract.

### 3.6 What moves into the engine for M4-E

The prototype composes **existing** operations and does not touch the engine. Four things the idea note requires belong in the engine, and the contract already has their seams:

- **The stage-intent journal (§9 to §11).** Before a stage's first mutation, a `StageIntent` record (hot while active, cold when terminal, per ADR-0011 §10); `resume` surfaces dangling intents with `safe_to_continue`; a replacement Lead chooses `CONTINUE_STAGE` or `ABANDON_STAGE`. In the contract this appears as `stopped.boundary: judgment_required` and two more tools; `completed_steps` is already the journal's shape.
- **Policy drift (§8).** The stage records the policy digest it expanded under (`DispatchDecision.dependency_digests` has it); a change mid-bundle stops with `STALE_POLICY`.
- **Queryable transition and ingest guards (§13).** Today `auto_runnable` is truthful only for dispatches, because only `DispatchDecision` has a query form. Migrating the transition and ingest guards onto the same substrate makes `ticket_request_review` and `ticket_request_verification` answerable before they run, and makes `explain` cover them.
- **Policy-resolved review and verification sets.** The prototype launches the role's default card; the stage must resolve the cards the effective gates require (`review_r1`, the verification gates) and launch each, returning every invocation and run (the F15 proposal's row 3 and 4).

Also for M4-E: `requires_disposition` as a gate input (F15 decision, 2026-10-01); `ticket_prepare` built once M4-D's lease exists; `ticket_submit_integration --publish-if-clean` (§17) on the queue.

## 4. Transport A: MCP, broker-side

### 4.1 Where the process runs, and custody

OpenCode's Lead projection declares one local MCP server, `aew`, with the command `aew lead mcp`. OpenCode spawns it **in the TUI's curated environment** (ADR-0009: operating-system basics, `PATH` with `aew` first, the broker's coordinates, the projection; no AEW credential, no provider key). The server therefore holds nothing: it forwards each `tools/call` as the broker operation `lead.tool {name, arguments}` over the existing bridge (JSON only, HMAC key challenge, exact arguments, redaction, drain), and the broker runs the tool with the credential it holds, under `dispatch.channel("lead_mcp")`, so every dispatch records that the typed surface carried it.

This is the custody model unchanged: the model exercises the Lead's operations without possessing, printing or inheriting the credential. The end-to-end test checks it the way the Lead-session tests do: the transcript, the session's output and the server's environment carry no credential string, and `AEW_LEAD_TOKEN` is absent from the environment the probe sees. The broker's refusals apply to the `cli` tool because that tool runs through the same `run_cli` function the `lead.cli` operation uses (now a module function both call): credential-emitting commands, `--token`, dispatch without `--launch`, read-only commands and other projects are refused with the same codes (tested).

When the broker closes (takeover, handoff, release elsewhere), every tool call returns the bridge's `STALE_AUTHORITY` as a tool outcome; the harness keeps running read-only, as today.

**Direct mode.** Outside a session, with `AEW_LEAD_TOKEN` in the operator's own environment, `aew lead mcp` runs tools in-process with that credential. The operator's terminal legitimately holds it (ADR-0005), so an MCP client there (an IDE, another agent) gets the same surface. A harness-launched server never has that variable: `aew opencode` strips it.

### 4.2 Projection and probe changes (`harness/opencode/projection.py`, `capabilities.py`)

- `lead_config()` gains `mcp: {servers: {aew: {type: "local", command: ["aew", "lead", "mcp"]}}}`, spelled as the pinned 2.0.18 schema spells it (a unit test validates the whole Lead configuration against `Config.InfoEncoded` from the fixture).
- `LEAD_RULES` gains `aew_*: allow`: the operator is present and every tool is engine-refused or engine-committed, exactly like the `shell aew *` allow it sits beside.
- The Lead's system text gains one bullet naming the tools and what every result carries; the shell path remains described for parity.
- The capability probe requires `Config.InfoEncoded.mcp` and `Mcp.LocalConfigEncoded.{type, command}` from a served server's OpenAPI, so a release that respells MCP configuration fails closed at launch instead of silently ignoring the server.

The projection golden (`projection-lead.golden.json`) was regenerated; its diff is exactly these three additions.

### 4.3 The protocol layer (`aew.surface.mcp`)

Dependency-free and small by intent (AEW pins what it speaks and a probe can check a harness against it): newline-delimited JSON-RPC 2.0 over stdio; `initialize` echoing a known protocol revision (2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05) or answering with the newest; `notifications/initialized`; `ping`; `tools/list` rendered from the catalog with MCP annotations (`readOnlyHint`, `idempotentHint`); `tools/call` returning the `StageResult` as `structuredContent` and as text, `isError = not ok`; empty `resources/list` and `prompts/list`; batches; malformed messages answered without ending the session. Unknown or designed tools are `-32602` protocol errors (a model should never see them listed); unknown methods `-32601`. Logging goes to stderr only; stdout is the protocol.

### 4.4 Context cost

Measured: 12 tools, 11,711 bytes compact JSON (about 2,900 tokens), with `ticket_draft` the largest at 3,108 bytes. A test holds the list under 12,000 bytes and 16 tools so the surface cannot grow by accretion. Two deliberate choices keep it there: stages, not primitives, are listed (the primitive surface is one tool), and the 5.5 KB result schema is **not** advertised per tool (it would have added 66 KB to every prompt). Progressive disclosure (F13) and OpenCode's per-agent tool filtering are the next step when the knowledge tools (`aew-knowledge`, review §4.2) join; the research's own warning stands: measure the per-request overhead on the pinned release (S24), do not infer it.

## 5. Transport B: the CLI as a parity and fallback adapter

`aew lead tool <name> [--arguments JSON | --fields -]` runs one catalog tool through the same runner and returns the same `StageResult`; `aew lead tool --list` prints the catalog as the MCP server advertises it. Inside a Lead session the command routes to the broker like every Lead-authenticated command, so the parity holds there too. The `cli` tool and the shell `aew` command remain the primitive surface (v0.4 surface B): recovery, debugging, conformance, forensics.

Stage commands as first-class CLI verbs (`aew ticket draft …`) are **not** needed for parity and are not built. If they are wanted later, they are generated from the catalog's schemas (argparse from JSON Schema, `--fields` for text), never hand-written, so the CLI cannot acquire semantics the catalog lacks. The existing `--fields` ingress stays for the shell path.

## 6. The role surface (`aew-run`), designed only

The run bridge's three operations (`whoami`, `check.run`, `submit`) become three tools served by a thin stdio client **inside the sandbox**, forwarding to the supervisor's bridge exactly as the `aew` CLI client does today; the supervisor keeps the credential. The one design gain beyond ergonomics: `submit` takes the report as a typed object whose schema is the evidence schema, which ends the YAML-frontmatter failure class (M3-D2, D5, D7, I5). Same code shape as `aew.surface.mcp` with a different operation table; not prototyped (it needs the role projection, the per-run OpenCode config and a containment check that the server runs inside the bubblewrap boundary).

## 7. Dispatch conformance

- Dispatches made through the surface are carried by channel `lead_mcp` (MCP) or `cli` (the CLI transport); the `cli` tool inside a session is carried by `lead_broker` as before. The provenance recorded on invocations and runs (M4-A) therefore says which surface dispatched; `test_dispatch_conformance` should gain the `lead_mcp` channel alongside `lead_broker.relay` (not added in the prototype).
- The CLI enumeration (`test_dispatch_decision`) classifies `lead tool` and `lead mcp` as non-dispatching **commands**: neither is a dispatch route of its own; a dispatching stage reaches the registry through `work_assign` and `invoke_create`, and the catalog test proves every dispatching tool names a registered entrypoint.
- `explain` is `Dispatch.decide` on committed state: query equals execution, as the conformance test already proves for the CLI.

## 8. What the outbox gives this surface (ADR-0012 draft, D8)

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

**Not built, by design** (each is stated where it belongs in §3.6, §6, §8): `ticket_prepare`; the stage-intent journal and `STALE_POLICY`; queryable transition and ingest guards (so `auto_runnable` is truthful only for dispatches); policy-resolved review and verification card sets (the prototype launches the role's default card); wait-any; the `aew-run` role server; a takeover-mid-session test for the MCP path (the Lead-session suite covers the broker's behaviour, which the server inherits); OpenCode's actual spawning of the server (a live-lane check against 2.0.18; the configuration is validated against its schema, not against a running TUI); the `lead_mcp` channel in the conformance test.

**To run it:** `.venv` in this directory has the branch installed editable. `python -m pytest tests/unit/test_surface.py tests/integration/test_lead_mcp.py` from `tree/`.

## 10. Evaluation and completion criteria (for M4-E, from F15 §21)

Hard gates, unchanged from the idea note: no false advance in the seeded corpus; every consequential judgment has an attributable durable decision before the transition; anomaly catch under the stage surface at least equal to the primitive baseline; recovery correctness across crash, retry, takeover and mixed-mode walks. Conformance prerequisites: stage/primitive equivalence for every built stage (the prototype has it for `ticket_draft`; `ticket_start` and the two request stages need the fake-harness form); query/execute equivalence for every migrated guard; `PrimitiveSpec` coverage for every staged primitive; ADR-0011 bounded hot state for journal and anomalies.

Reported, never traded against the gates: workflow-command steps per Ticket (target from the proposal: at least 25% fewer on matched single-Ticket runs, the median from 20 toward 15), refusals per session (the taxonomy should lose its usage and argparse share entirely), reads between mutations (should approach zero), `--help` lookups, cached input tokens per session, wall-clock, time to consequential decision. Measured by the preregistered dogfood with the instrumented command log (T3 of the audit, already done) against the M3 baseline, with the primitive path as the control arm. Context: the tool list's bytes per prompt, compared with the Lead guide's.

## 11. Sequencing

- **M4-D:** the broker operation, the MCP server and the query, wait and `cli` tools can land with wait-any: they touch no engine semantics and give the dogfood its instrument early. `harness_wait --any` arrives with the outbox.
- **M4-E:** the engine work of §3.6, the four stages as governed design (F15 promoted to a design document), `ticket_prepare`, the equivalence tests with the fake harness, the conformance channel, the live-lane check that 2.0.18 spawns and lists the server.
- **M4-H:** the paired evaluation above.
- **M6:** `aew-knowledge` tools join the same server; F13 disclosure decides what each role sees.

## 12. Questions for the designer

1. Is `ticket_request_verification`'s acceptance of the review report correctly modelled as the Lead's judgment carried by `review_evidence`, or must acceptance remain a separate call from the request (two tools) so the judgment is never adjacent to a dispatch?
2. Should `cli` be exposed to the Lead's model at all in the normal surface, or only in a recovery profile? The prototype exposes it (the proposal keeps low-level commands available); hiding it would make the surface strictly stages and queries.
3. The projection marks transition-guarded actions `auto_runnable: false` until those guards are queryable. Is that the right default, or should such actions be omitted until M4-E's migration?
4. Direct mode (`aew lead mcp` with `AEW_LEAD_TOKEN` in an operator shell): keep, or require the broker always?
5. Does the stage-intent journal (§3.6) belong to M4-E's first delivery, or may the first dogfood run stages without it, relying on `completed_steps` and primitive-reachable intermediate states?
6. Tool naming: `aew_<name>` is OpenCode's prefixing of the server name; is `aew` the right server name once `aew-run` and `aew-knowledge` exist, or should the Lead server be `aew-lead`?

## 13. Alternatives considered

- **The broker itself speaking MCP over its socket** (no child process). Rejected for now: OpenCode 2.0.18 configures local servers by command; a remote (HTTP) server would need the TUI to reach a loopback port, and the bridge's HMAC challenge does not map onto MCP's HTTP auth. The child-process form keeps the bridge as the one custody protocol and costs one small process.
- **Stage commands as CLI verbs first** (the F15 proposal's pilot path). Not chosen, by the operator's direction; and G2's argument stands: more CLI keeps the untyped arguments, text results and shell that produce the refusals. The CLI remains a parity adapter generated from the catalog if ever wanted.
- **An MCP SDK dependency.** Rejected: the pinned release's protocol revisions are a fact to probe, the needed subset is small, and the airgap bundle should not grow for a transport layer AEW can own in two hundred lines.
- **Advertising the result schema per tool.** Rejected on measurement (66 KB per prompt); the result is structured content either way.
- **A generic `advance` tool** ("take the next step the engine computes"). Rejected: it crosses judgment boundaries without an argument carrying the judgment (v0.4 §3, fail closed). The projection names the next action; the Lead calls it.

## 14. Addendum 2026-10-04: the live spawn against OpenCode 2.0.18, and `codemode`

The live check §9 left open was run on the Rocky 8.10 VM (`T9-live-probe-1-results.md`; `repro/t9/`). OpenCode 2.0.18 spawned `aew lead mcp` from the Lead projection, but under its default **Code Mode** the twelve tools never reached the model as function tools: the request carried the nine built-ins plus `execute` (a JavaScript runtime) and the instructions listed five of twelve `aew` signatures in a partial catalog. With `codemode: false` on the server entry all twelve tools are function tools in the request, at 11,178 bytes (the estimate in §4.4 was 11,711; `aew_ticket_draft` alone is 3,212). A permission `deny` removes a tool's schema from the request, so §4.4's mitigation is real. The review branch therefore gains a second commit: the projection sets `codemode: false`, the capability probe requires the key, the Lead golden is regenerated. Two consequences for §12: question 7, **how `aew opencode` should report an MCP server that failed to start** (the probe showed a failed server is silent to the session); and question 8, **whether the Lead's `* ask` rule should name OpenCode's built-in `browser` namespace (45 desktop tools, reachable through `execute`) explicitly**, since runs hide it only because their rules deny everything unnamed.
