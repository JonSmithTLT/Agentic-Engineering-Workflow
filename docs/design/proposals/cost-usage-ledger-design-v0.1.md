# The cost and usage ledger: the design note for F25 (v0.1)

- **Status:** **Proposed** (2026-10-05) for the designer's and operator's decision; the eight questions it asks are §8.
  Register F25 (absorbs U4 when built); ledger prefix CUL. Written by the lead developer of the main AEW repository.
  The build is a separate task after approval (the register's model split: this note by Fable, the build by Opus),
  and it waits for M4-D's open PRs (§6).
- **Owns:** what AEW records about the usage and cost of its model work, where that record lives, how it is rolled
  up, and how it is read: by the Lead and the operator (`aew usage`), by the evaluation component (F19), by the
  efficiency comparisons (F15), and later by the dashboard (a contract change, not this note).
- **Does not own:** budget enforcement (G7's modification: a policy decision with F7 and M5, after calibration); the
  dashboard contract 0.1.2 (a `usage` projection is a later contract version with a renewed C0 review); the harness
  adapters' event handling; pricing data itself (the price table is the project's policy, not AEW's knowledge).
- **Reads:** the architecture review G7 and F-D with their accepted dispositions (ledger ARR-07, ARR-46); the M4
  report §"F25 in scope, before M4-H"; the evaluation component v0.2 §3 (`aew/eval-run/v1`'s `cost` block, EVC-14);
  the register rows F25, U4, E1, F7, F19; ADR-0009 (run records, custody, "a pid is never trusted alone"); ADR-0010
  (execution profiles, the pinned model and effort); ADR-0011 (hot and cold state; archived bundles hold the unit's
  invocations); ADR-0012 (the frozen decision "supervisor commits not authorized", OBX-45; wait-any); the code:
  `harness/base.py` (`collect`), `harness/opencode/adapter.py` (`_take_snapshot`, `collect`), `harness/supervisor.py`
  (`_compare_effective`, the run record), `harness/runlog.py`, `engine/harness_ops.py` (`inv.runs[]`,
  `harness_status`), `engine/evidence_ops.py` (ingestion), `engine/archive_ops.py` (the bundle), the control schema,
  `eval/m3/dogfood/dogfood.py` (how the M3 dogfood summed cost), OpenCode 2.0.18's `TokenUsage.Info` and
  `Session.Info.cost` in the pinned OpenAPI fixture.

## 1. Scope

- One record per **harness run**, normalized across harnesses, with the model and profile it ran under, token
  categories, wall time, steps, the provider's reported cost when it exists, and a trust label for each of those.
- One record per **Lead session** (U4): what the operator's own Lead TUI session used, kept apart from the units'
  work.
- A **price table** the project owns, from which a derived cost is computed at read time and never stored as a fact.
- **Roll-ups** from run to invocation to unit to parent, and to the project, as projections of the records, never as
  stored totals.
- A **surface** to read them: `aew usage show`, `aew usage runs`, `--json`, and the same functions for F19's
  collector.

Out of scope, by decision already made or by placement elsewhere: refusing a dispatch on a USD budget (F7, M5);
dashboard routes (contract change, F20.x); pruning the local run directories; usage of anything that is not a model
run (git, checks).

## 2. What is already settled

- **G7, accepted with modification (2026-10-05):** build the ledger before any budget enforcement; it records
  model/provider/profile, token categories where available, wall time, reported/provider cost when trustworthy, a
  policy-price-table-derived estimated cost, and run → invocation → Ticket → parent roll-ups; USD budget refusals are
  a later policy decision. Needed by F19, routing comparisons, F15's efficiency claims and dashboard observability.
- **EVC-14 (F19):** the evaluation run record's `cost` block is `{provider_reported_usd, tokens{input, output,
  cached_input, reasoning, …}, pricing_snapshot_sha256, derived_usd}`: a derived dollar figure binds to a frozen
  price table. The ledger is that block's source.
- **ADR-0009:** the supervisor's run record is non-authoritative; the harness adapter's `collect()` reports usage,
  sessions, context sizes and `effective` models, and the supervisor flags a pinned-versus-effective mismatch
  (`model_check`). Nothing a harness reports is evidence.
- **ADR-0012 (OBX-45, frozen):** supervisor commits are not authorized. A run's end is observed, not committed.
- **ADR-0011:** finished work leaves the hot state in a bundle that holds the unit's invocations; the archive is
  rehydrated for reads of recent or named work.
- **U4:** the Lead TUI's usage lives only in OpenCode's own database and reports cost `$0` under a subscription
  login; readable after the TUI exits with OpenCode's standalone commands, fields to be probed; absorbed by F25.

## 3. Sources

The documents and code listed under "Reads" above. Facts about what exists today are in §4; nothing in this note
changes the harness contract, the custody rules or the hot/cold model.

## 4. What exists today

- **Per run, in `local/harness/runs/<R>/record.json`** (`aew/harness-run/v1`, written by the supervisor, disposable
  `local/` state, never authority): `execution_profile` (the pin: harness, provider, model, effort, limits),
  `started_at`, `status`, `exit_code`, `result` (the adapter's `collect()`: for OpenCode `sessions`, `turn`, `prompts`,
  `steps`, `tools_called`, `first_step_input_tokens`, `effective` (`[{provider, model, effort}]`), `usage` (the
  session's `{outcome, tokens, cost}`), `foreign_sessions`), `model_check` (`match | mismatch | effort_unreported |
  no_model_step | unreported`, with `requested`, `effective`, `mismatches`), `evidence`, `credential_scan`, the
  `timeline`.
- **OpenCode 2.0.18's usage**, per the pinned OpenAPI: `TokenUsage.Info {input, output, reasoning, cache{read,
  write}}` per assistant message and per session; `Session.Info.cost` in USD (`Money.USD`); per-message `cost` too.
  The M3 dogfood summed `usage.cost` across runs and the Lead session and found it `0` under a subscription login.
- **In control state, `inv.runs[] = {run, harness, token_id, launched_at, kind, generation}`**: launch facts only.
  Nothing about usage reaches control state, so nothing about usage is archived, and when `local/` is cleared the
  usage is gone.
- **Readers:** `aew harness status` reads the run directory for each run (status, model check, foreign sessions);
  the dashboard's `/runs` reads the same; the dogfood instrument read `usage.cost` from run records while they
  existed.

## 5. Decisions

### 5.1 The run-usage record: one bounded, normalized object per run

**R1.** A run's usage is one object, `aew/run-usage/v1`, with no free text and a bounded size (no per-message
arrays):

```yaml
schema: aew/run-usage/v1
run: R-0007                       # the run id; the invocation and unit are the record's parents
source: harness:opencode          # which adapter normalized it (harness name)
recorded_at: 2026-10-05T12:00:00Z # when the engine copied it (R5), not when the run ended
status: ended_with_evidence       # the run's terminal status as observed when copied
requested: {provider: openai, model: gpt-6.1, effort: high, profile: implementer}   # the pin (ADR-0010)
effective: [{provider: openai, model: gpt-6.1, effort: high}]                      # what ran (ADR-0009)
model_check: match                # match | mismatch | effort_unreported | no_model_step | unreported
wall_s: 412.6                     # started_at to the terminal status
steps: 23                         # assistant messages (model calls) in the run's session
tokens: {input: 184210, output: 9120, reasoning: 30011, cache_read: 151000, cache_write: 12000, unknown: 0}
tokens_trust: harness_reported    # harness_reported | partial | absent
provider_cost_usd: 0.0            # as reported, or null
provider_cost_trust: zero_with_tokens   # reported | zero_with_tokens | absent
foreign_sessions: 1               # other sessions in the run's private state (subagents or stray): counted, not summed
truncated: false                  # the adapter stopped paging messages before the end
```

Token categories are normalized to `input`, `output`, `reasoning`, `cache_read`, `cache_write` and `unknown` (any
category the harness reports that AEW does not name, summed). A harness that reports fewer categories leaves the
rest `0` with `tokens_trust: partial`; one that reports none gives `absent` and all zeros. `effective` is the
supervisor's list as it stands, **capped at 8 distinct entries** (a ninth distinct model is counted in
`effective_truncated`, an integer); `model_check` is its status word. Nothing in the record is a dollar figure AEW
computed: `provider_cost_usd` is the provider's own number, labelled.

**The bound is a number, not an adjective.** The field list is closed (the schema has `additionalProperties:
false`), every string is an enumeration or an identifier, every number is an integer or a float, and the serialized
record is **at most 2 KiB** (the schema's string lengths and the `effective` cap make that a consequence, and the
invariants check it directly). ADR-0011's H1 is measured at 20 open and 3,000 completed units; a usage record lives in
hot state only while its unit is open and leaves with the bundle, so at most the open units' runs carry one. The build
adds the usage copy to `tools/perf/control_plane.py`'s series and re-measures ADR-0011's H2 (derivation plus hash at
most 10 ms per commit) with every run of every open invocation carrying a 2 KiB record (§7).

**R2.** The adapter normalizes; the supervisor records; the engine copies. `HarnessAdapter.collect()` gains a
normalized `usage_record` (the fields above minus `run`, `recorded_at`, `status`, `requested`, `model_check`), built
by a shared helper `harness/usage.py` from the adapter's raw snapshot, so a second adapter (Codex, F-E) fills the same
shape. The supervisor writes it into the run record as `result.usage_record` beside the raw `usage` it keeps today
(raw facts stay for diagnosis; the record is what the ledger consumes).

### 5.2 Trust labels: a number is only as good as its source says

**R3.** Every dollar or token figure carries where it came from. `tokens_trust` is `harness_reported` when the
harness gave every category AEW names, `partial` otherwise, `absent` when none. `provider_cost_trust` is `reported`
when the harness gave a non-zero cost or a zero with zero tokens, `zero_with_tokens` when it reported `0` against
non-zero tokens (the subscription-login case the M3 dogfood hit: the number is not a price), `absent` when it gave
none. Roll-ups never add a `zero_with_tokens` or `absent` provider cost into a reported total; they count it as
unpriced (R7). A derived cost (R4) is labelled by the price table's digest, never by a trust word, because its trust
is the table's.

### 5.3 The price table and the derived cost

**R4.** The project owns a price table, `policy/pricing.yaml`, schema `aew/pricing/v1`, pointed at by the manifest's
`policy.pricing` (optional; a project without one has no derived cost, and every surface says `unpriced`):

```yaml
schema: aew/pricing/v1
currency: USD
as_of: 2026-10-01
source: "the provider's published list prices on the date above, as the operator recorded them"
prices:                       # USD per million tokens, by `<provider>/<model>`; a missing category is 0
  openai/gpt-6.1: {input: 2.0, output: 8.0, reasoning: 8.0, cache_read: 0.5, cache_write: 2.0}
  openai/gpt-6.1-mini: {input: 0.4, output: 1.6, reasoning: 1.6, cache_read: 0.1, cache_write: 0.4}
```

The derived cost of a run is `Σ tokens[c] × prices[provider/model][c] / 1e6` over the categories, using the
**effective** model when `model_check` is `match` and the **requested** one otherwise (with the derivation marked
`estimated_on_requested_model`), and `null` with reason `unpriced_model` when the table has no row. It is computed
at **read time** by every surface and never written into the record or into control state: a corrected price table
corrects every past figure on the next read, and nothing in authority ever disagreed with a price. Every derived
figure is reported with `pricing_sha256` (the table's digest), so the evaluation component's `pricing_snapshot_sha256`
(EVC-14) is this digest, frozen by the preregistration's copy of the table. `aew init` writes no price table (it
cannot know prices); `aew doctor` reports a missing one as INFO, a malformed one as ERROR.

### 5.4 Placement: the record lands in control state at the Lead's next transaction on the invocation

**R5.** The run-usage record is copied from the run directory into control state as `inv.runs[i].usage` by the
**engine**, inside a Lead transaction that already touches the invocation, and never by the supervisor (OBX-45):

- at **evidence ingestion** (`review.ingest`, `verify.ingest`, and the implementation report's acceptance path), for
  the run that produced the evidence and for any earlier run of the same invocation whose usage is not yet copied;
- at **`invoke cancel`** and at a **relaunch** (`harness launch --replace` rotates the credential and starts a new run:
  the previous run's usage is copied in the same commit);
- at **archival** (the finalizer that bundles a finished unit), for every run of every invocation of the unit that
  still lacks it: the bundle then carries the unit's complete usage into the cold state.

Each copy reads the run record once (`runlog.read_record`), takes `result.usage_record` if present and otherwise
writes `{schema, run, tokens_trust: absent, provider_cost_trust: absent, …}` with `status` as observed, so a run
that crashed before reporting is counted as a run with unknown usage, never silently omitted. The copy is idempotent
(a run with `usage` present is never rewritten) and bounded (one object per run; the record has no arrays that grow).
`inv.runs[]` is declared in the control schema with this optional field (it is written today and not declared).

**A usage copy derives no event.** ADR-0012 D2 derives `run.added` by comparing the run ids of `inv.runs[]` before and
after the commit (`outbox.py`: a run is new when its `run` id was not in the previous list), and `invocation.status`
from the status field; a new field on an existing run changes neither, so a commit whose only effect on an invocation
is a usage copy publishes no `run.added`, no `invocation.status`, and no event of any kind for it. No new kind is
added: a wait-any consumer (D6) must never read a usage copy as a new run, and nothing waits on usage. The build's
tests state this directly (§7), and ADR-0012's oracle rules 24 to 26 hold across a usage copy.

Why not a supervisor-initiated commit at the run's end: ADR-0012 froze that supervisors do not commit, the run's
credential may already be revoked when the run ends (superseded, cancelled), and every path that makes a run's
result matter to the workflow is a Lead transaction anyway. Why not a cold record of its own: a usage object is a
property of a run, which is a property of an invocation, which the bundle already archives; a new history entry kind
would be a contract change (ADR-0011's closed enum) for data that has a home.

### 5.5 The gap between a run's end and its copy is observable, not hidden

**R6.** Until the copy, the usage exists only in `local/`. `aew usage` and the collector read both: control state
(`inv.runs[].usage`, hot or rehydrated) first, and for runs without it the run directory's `result.usage_record`,
labelling those rows `provisional` (they can still change: a crashed harness's supervisor may finish writing, and a
cleared `local/` loses them). A `provisional` row that has no run directory either is `missing`, counted and shown.
No surface sums a `missing` run into a total without saying how many it skipped.

### 5.6 Roll-ups are projections, computed from the records, never stored

**R7.** `engine/usage_ops.py` computes, from the hot state plus whatever archived units a query names or the
`recent` ring holds:

- per **run**: the record, plus the derived cost and its `pricing_sha256`;
- per **invocation**: the sum over its runs, with counts `runs`, `reported`, `provisional`, `missing`, `unpriced`,
  `zero_with_tokens`; per model (`provider/model` from `effective`, or `requested` when unmatched). An invocation
  with no runs is normal, not a gap: the custody invocations of M4-D3 (`integration_attempt`) never run a harness,
  and a dispatched invocation may not have launched yet. They are counted as `invocations_without_runs` at every
  level and contribute nothing else; no roll-up expects a run under every invocation;
- per **unit**: the sum over its invocations (hot or rehydrated), then over its children by the hierarchy (a Story
  sums its Tickets, an Epic its Stories), each level reporting its own and its descendants' totals separately;
- per **project**: the hot units plus the `recent` ring by default; `--all` walks the history index for archived
  units (bounded by `--since`/`--until`, newest first, as `aew history list` pages) and rehydrates them one at a time.

Totals are never written back anywhere (not to control state, not to a cache file): a changed price table or a
late-copied record changes the next read and nothing else. Wall time sums are labelled `wall_s_sum` (runs overlap;
the sum is not elapsed time).

### 5.7 The Lead session's usage (U4): its own ledger line, never summed into units

**R8.** `aew lead session` and `aew opencode` (the Lead broker) record the Lead session's usage when the session
ends, as `aew/lead-session-usage/v1` (`session_label`, `generation`, `started_at`, `ended_at`, `tokens`,
`tokens_trust`, `provider_cost_usd`, `provider_cost_trust`, `effective`, `source`), committed by the broker with the
Lead credential it holds, as the broker's own transition `lead.session_usage`, into a bounded ring
`state["lead"]["sessions"]` (the last 32; the `lead` record is schema-versioned for additions, ADR-0005). The source
is OpenCode's own session data read by the broker after the TUI exits (U4's note: the standalone `session list` or
`stats` output; the fields are a probe, §7). This transition is initiated by the broker process on exit, not by a
model request: `lead.cli` through the bridge refuses `lead session_usage` as it refuses credential-emitting commands,
so the Lead's model cannot write its own usage. The Lead's usage is reported beside the units' totals and never added
to any unit, Ticket or parent: it is the operator's seat, not a unit's work.

### 5.8 Surfaces

**R9.** `aew usage show [WORK-ID] [--all] [--since UTC] [--until UTC] [--json]` (a unit's tree, or the project), `aew
usage runs [--invocation INV] [--json]` (one row per run with its record and derived cost), `aew usage lead [--json]`
(the Lead sessions). Text output is a table per level; JSON is the projection of R7 with every count and label. The
same `usage_ops` functions are what F19's collector calls for `aew/eval-run/v1`'s `cost` block and what a later
dashboard projection would read; nothing is computed twice in two places. `aew status --json` gains one bounded
`usage` summary for the hot state (runs counted, tokens summed, unpriced count), nothing more.

### 5.9 Non-goals and later work

**R10.** No budget refusal anywhere in this note (G7's modification). No dashboard route (contract 0.1.2 is frozen;
a `usage` projection is a 0.2 contract with a C0 review). No pruning of `local/harness/runs` (unrelated housekeeping;
after R5 the run record's usage survives pruning, which is a precondition for pruning ever being safe). No per-step
records in control state (bounded objects only; the raw snapshot stays in the run record). No prices from AEW (the
table is the project's, dated and sourced).

## 6. Engine edits, and the sequencing against M4-D

Additive edits, each with its own unit test:

1. `harness/usage.py` (new): `normalize(raw_usage, raw_assistant, effective) -> usage_record`; the OpenCode adapter's
   `collect()` fills `usage_record`; `base.py`'s docstring names it.
2. `harness/supervisor.py`: writes `result.usage_record` (one line beside the existing `result`).
3. `schemas/control.schema.json`: `invocations.*.runs[]` declared; `usage` optional; `lead.sessions` optional ring;
   `schemas/pricing.schema.json` (new); the manifest's optional `policy.pricing`.
4. `engine/usage_ops.py` (new): `copy_run_usage(state, inv_id, aew_root)` (R5's idempotent copy, called by the three
   paths), the projections of R7, the price table reader and derivation (R4).
5. `engine/evidence_ops.py` (ingestion and `invoke cancel`), `engine/harness_ops.py` (relaunch), `engine/archive_ops.py`
   (the bundle finalizer): one call each to `copy_run_usage`.
6. `engine/lead_ops.py` and `harness/lead_broker.py`: the `lead.session_usage` transition and the broker's exit hook;
   the bridge's refusal of it from the model side.
7. `cli/usage_commands.py` (new) and its registration; `status_ops` gains the bounded summary.

**Sequencing.** M4-D's open PRs change `engine/api.py`, `evidence_ops.py`, `archive_ops.py`, `lead_ops.py`,
`workspace_ops.py`, `ports.py`, the control schema and the invariants (#65, D3), and D6 rewrites `aew harness wait`
over the run records. Edits 3, 5 and 6 touch those files, so the build starts after #60 and #65 merge and
coordinates D6's run-record reads with the lead developer (both read `runlog.read_record`; neither changes the run
record's existing keys). Edits 1, 2, 4 and 7 collide with nothing and may be built first on the same branch.

## 7. The build plan and its tests (F25, after approval)

- **Slice 1 (no engine collision):** `harness/usage.py` with fixtures from the pinned OpenCode OpenAPI (a session with
  all categories; one with `cost: 0` and tokens; one with no usage; a truncated paging run); the supervisor writing
  `result.usage_record`; `usage_ops` projections over hand-built states with every label and count exercised; the
  price table schema, the derivation with `match` versus `mismatch` runs, `unpriced_model`, and the digest; property
  test: for any set of runs, the unit total equals the sum of invocation totals equals the sum of run figures, and
  the counts partition the runs.
- **Slice 2 (after #60 and #65):** the three copy paths, each shown to copy exactly once and to write an `absent`
  record for a run without a usage record; **a usage copy derives no event** (the transition's typed events are
  empty for that invocation: no `run.added`, no `invocation.status`) and ADR-0012's oracle rules 24 to 26 hold across
  it, with a wait-any consumer blocked on the wake file not woken by it; **the size bound**: a record over 2 KiB or
  with a ninth distinct `effective` entry is refused by the schema and the invariants, and
  `tools/perf/control_plane.py` gains the usage copy in its series with H2 re-measured at 20 open and 3,000 completed
  units with every open run carrying a 2 KiB record (at most 10 ms derivation plus hash per commit, the ADR-0011
  bound), on the Windows reference machine and the Rocky 8 host; archival carries usage into the bundle and
  rehydration reads it back; a custody invocation without runs rolls up as `invocations_without_runs`;
  `aew usage show` on a project driven to archival (the dashboard suite's world is reusable) equals the sum computed
  from the run directories while they exist, and still answers after `local/harness/runs` is deleted; `--all` pages
  the archive; the Lead session's usage written at session end by the broker and refused through the bridge; the
  bridge's refusal has a negative control.
- **Probe (before slice 2's Lead part):** OpenCode's standalone session or stats output after a TUI exit, on the
  pinned 2.0.18, to confirm which fields exist and whether cost is `0` under a subscription login (U4). Recorded with
  the design's evidence; if no readable source exists, the Lead line records `tokens_trust: absent` and says so.
- **Evidence for the designer's gate:** `tests/unit/test_usage_*.py`, `tests/integration/test_usage_ledger.py`; the
  invariants file gains "every `inv.runs[].usage`, when present, is a well-formed `aew/run-usage/v1` whose `run`
  matches its entry"; the credential scans unchanged (the record holds no secret and no path).

## 8. Decisions asked of the designer and operator

1. **R5, placement:** usage copied into `inv.runs[].usage` at the Lead's next transaction on the invocation (ingest,
   cancel, relaunch, archival), never by the supervisor. Alternative: a supervisor-initiated engine operation at the
   run's end, which would reopen OBX-45.
2. **R4, the derived cost is never stored:** computed at read from the project's dated price table and reported with
   the table's digest. Alternative: freeze a derived figure into the record at copy time (simpler reads, but a price
   correction then needs a migration and authority would hold a number that was never a fact).
3. **R3, the trust labels** and the rule that `zero_with_tokens` is unpriced, not free.
4. **R7, roll-ups as projections**, including `--all` over the archive through the history index, and no stored
   totals.
5. **R8, the Lead session's usage** as a broker-committed `lead.session_usage` transition into a bounded ring on the
   `lead` record, refused from the model side, never summed into units. Alternative: no Lead line in v1 (U4 stays
   open).
6. **R9, the surface names** (`aew usage show|runs|lead`) and the one bounded summary in `aew status --json`.
7. **R10, non-goals:** no budget refusal, no dashboard route, no pruning, no per-step records.
8. **§6 sequencing:** slice 1 may start now; slice 2 after #60 and #65, coordinated with D6.

## 9. Register and ledger

Every requirement here is in `docs/design/requirements-ledger.yaml` under the prefix CUL, tracked by F25 (and U4 for
the Lead line). The register's F25 row points at this note; U4's note already says F25 absorbs it. The status line
records the decisions when they are made; the build's PRs link back to the sections they build.
