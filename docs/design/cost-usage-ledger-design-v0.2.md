# The cost and usage ledger: the design note for F25 (v0.2)

- **Status:** **Adopted** (2026-10-06) by the designer, after a narrow revision made in this version (§10): R8 is revised from Lead-session to attachment and generation accounting (Q12), R7 and R9 gain an explicit projection scope and completeness, and PR numbers in the sequencing are implementation notes, not requirements; the other decisions of §8 are approved as asked. Earlier history: **Proposed** (2026-10-05) for the designer's and operator's decision; the eight questions it asks are §8. **Revised 2026-10-05 after the designer's review** (REQUEST CHANGES: R1, R2, R3, R5, R6, R7, R9 and R10 kept; R4 and R8 revised): the reported counters are priced only after being mapped onto non-overlapping billable buckets (§5.3); a missing price is `unpriced`, never zero; a derived cost binds to an immutable pricing snapshot recorded at copy time, with the current-price figure a separate projection; an effective-model mismatch or mix is unpriced unless usage is partitioned per model; the Lead session's usage is archived into the existing cold lead history, the ring of 32 being only the hot projection (§5.7). **Second round (lead developer, 2026-10-05):** a Lead session's usage is its own `history/lead/` record written in its own commit, because one credential spans every session of a seat started without `--acquire` and a slot on the credential would overwrite them; and the semantics of the reported token counters are the adapter's declaration (`token_semantics`), pinned by the harness conformance tests, not a price-row setting (§5.3). Returned for adoption.
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
- One record per **Lead attachment** (U4): what the Lead used while an AEW attachment and its generation were active,
  kept apart from the units' work (revised 2026-10-06, §5.7).
- A **price table** the project owns (flat prices per billable bucket), applied through the adapter's declared token
  semantics, from which a derived cost is computed at read time under the pricing snapshot recorded when the run was
  copied, and never stored as a fact.
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
tokens_by_model: null             # optional: [{provider, model, tokens: {…the same categories…}}] when the harness partitions usage per model; else null
token_semantics: input_includes_cache_read_output_includes_reasoning   # the adapter's declaration of how the reported counters overlap, from knowledge pinned by the conformance tests; unknown when it cannot say
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
unpriced (R7). A derived cost (R4) is labelled by the pricing snapshot's digest and the record's token semantics, never by a trust
word, because its trust is the table's. `tokens` are the harness's **reported** counters, kept as reported: whether they
overlap (a provider that counts cached tokens inside `input`, or reasoning tokens inside `output`) depends on the harness
and its version as much as on the provider, so the **adapter** states it in `token_semantics`, from knowledge the harness
conformance tests pin against the qualified harness version (R2); the record never guesses it, and no hand-edited price
row carries it, because such a row would silently misprice after a harness upgrade.

### 5.3 The price table, the token semantics, the pricing snapshot and the derived cost

**R4.** The project owns a price table, `policy/pricing.yaml`, schema `aew/pricing/v1`, pointed at by the manifest's
`policy.pricing` (optional; a project without one has no derived cost, and every surface says `unpriced`):

```yaml
schema: aew/pricing/v1
currency: USD
as_of: 2026-10-01
source: "the provider's published list prices on the date above, as the operator recorded them"
prices:                       # USD per million tokens, by `<provider>/<model>`, per billable bucket; nothing else
  openai/gpt-6.1:      {input: 2.0, output: 8.0, cache_read: 0.5, cache_write: 2.0}
  openai/gpt-6.1-mini: {input: 0.4, output: 1.6, cache_read: 0.1, cache_write: 0.4}
```

Four rules, each a correction the designer's review required (2026-10-05), the first restated after the lead
developer's review of the revision (the same day):

1. **Non-overlapping billing buckets, declared by the adapter, not by policy.** The harness's token categories are
   *reported* counters and are not guaranteed to be mutually exclusive (cached tokens are a subset of `input` for some
   providers; reasoning tokens sit inside `output` for some), and **how they overlap depends on the harness version
   as much as on the provider**. That knowledge therefore lives where the harness is known: the adapter's
   `normalize()` (R2) declares `token_semantics` in the record, one of a closed enumeration AEW defines in
   `harness/usage.py` (`disjoint`, `input_includes_cache_read`, `input_includes_cache_read_output_includes_reasoning`,
   `output_includes_reasoning`, `unknown`), chosen per provider from a mapping table pinned to the qualified harness
   version by the harness conformance tests (the pinned OpenCode 2.0.18 OpenAPI fixture is one input; a harness
   version with no pinned mapping yields `unknown`, never a guess). The derivation maps the reported categories onto
   billable buckets by the record's declared semantics before any multiplication. `unknown` prices nothing
   (`unpriced_token_semantics_unknown`); a mapping that would make a bucket negative (`cache_read` > `input`) prices
   nothing (`unpriced_inconsistent_counters`). The price table carries **no** semantics: a hand-edited row cannot know
   what a harness upgrade changed, and would silently misprice when it does. New semantics are a schema addition with
   a conformance fixture, never a formula in policy.
2. **A missing price is unpriced, never zero.** A row must price every bucket the record's semantics bills. A run with
   a non-zero count in a bucket the row does not price is `unpriced` with reason `unpriced_category:<bucket>`; a zero
   count in an unpriced bucket is fine. Nothing defaults to `0`: the `zero_with_tokens` lesson (R3) applies to prices
   as much as to reported costs.
3. **A derived cost binds to an immutable pricing snapshot.** The first time a table digest is used by a usage copy
   (R5), the engine writes the table's exact bytes, content-addressed, to `.aew/pricing/<sha256>.yaml` (project
   data beside `policy/`, immutable, never rewritten, never pruned; `aew doctor` checks that every digest a record
   names is present and matches). Each copied usage carries `pricing_sha256`, the digest of the table in effect
   **when AEW recorded the run**, or `null` when the project had none. A surface therefore computes and labels two
   figures, both derived, neither stored: `estimated_at_record` (under the snapshot the record names: "what did we
   estimate this run cost when we recorded it", reproducible for ever) and `estimated_under_current_prices` (under
   `policy/pricing.yaml` as it is now: "what would these tokens cost today"). The evaluation component's
   `pricing_snapshot_sha256` (EVC-14) is the snapshot digest the preregistration froze; its runs report the figure
   under that snapshot. A corrected table changes `estimated_under_current_prices` on the next read and nothing
   else; `estimated_at_record` never moves, and the usage facts are never rewritten.
4. **A model mismatch or a model mix is unpriced unless usage is partitioned.** The derived cost uses the
   **effective** model and only when the usage is attributable to one model: `model_check` is `match`, or
   `effective` has one entry, or the harness partitioned the counters per model (`tokens_by_model`, optional in R1's
   record and bounded by the same 8-entry cap), in which case each partition is priced on its own row and summed.
   Otherwise the run is `unpriced` with reason `unpriced_effective_model_mix` (several effective models, counters not
   partitioned) or `unpriced_model` (no row for the effective model). The requested model is **never** used to price
   a run: a precise-looking estimate on a model that may not have been billed is worse than `unpriced`. A
   provider-reported cost with `provider_cost_trust: reported` is shown beside the derived figure regardless.

The derived cost of a priceable run is `Σ buckets[b] × prices[provider/model][b] / 1e6` over the billable buckets the
record's `token_semantics` yields. It is computed at **read time** by every surface and never written into the record
or into control state. `aew init` writes no price table (it cannot know prices); `aew doctor` reports a missing one as
INFO, and a malformed one or a missing snapshot named by a record as ERROR.

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

- per **run**: the record, `pricing_sha256` as recorded at copy, `estimated_at_record` and
  `estimated_under_current_prices` (each a figure or `unpriced` with its reason), and the provider-reported cost with its
  trust label;
- per **invocation**: the sum over its runs, with counts `runs`, `reported`, `provisional`, `missing`, `unpriced`,
  `zero_with_tokens`, and the unpriced reasons tallied; per effective model (a mixed run counts under
  `unpriced_effective_model_mix`, never under the requested model). An invocation
  with no runs is normal, not a gap: the custody invocations of M4-D3 (`integration_attempt`) never run a harness,
  and a dispatched invocation may not have launched yet. They are counted as `invocations_without_runs` at every
  level and contribute nothing else; no roll-up expects a run under every invocation;
- per **unit**: the sum over its invocations (hot or rehydrated), then over its children by the hierarchy (a Story
  sums its Tickets, an Epic its Stories), each level reporting its own and its descendants' totals separately;
- per **project**: the hot units plus the `recent` ring by default; `--all` walks the history index for archived
  units (bounded by `--since`/`--until`, newest first, as `aew history list` pages) and rehydrates them one at a time.
  Every project-level projection says what it covers (designer, 2026-10-06), so the default view can never be read as
  a lifetime total: the default carries `scope: recent` and `archive_complete: false`; an unbounded `--all` carries
  `scope: all`, with `archive_complete: true` only when the walk covered every archived unit. A bounded `--all` (with
  `--since` or `--until`) carries `scope: window` and echoes its bounds, so a windowed total is never read as a lifetime
  one (lead developer, from the review of this version).

Totals are never written back anywhere (not to control state, not to a cache file): a changed price table changes
`estimated_under_current_prices` on the next read and nothing else, and a late-copied record joins the next read. Wall time sums are labelled `wall_s_sum` (runs overlap;
the sum is not elapsed time).

### 5.7 The Lead attachment's usage (U4): its own ledger line, never summed into units, one cold record per attachment

**R8, revised by the designer on 2026-10-06 for Q12.** The accounting boundary is the AEW attachment and its
generation, not the native TUI or harness session. A harness conversation may exist before an attachment, survive
`aew close`, hold ordinary non-AEW work, and later receive another generation, so recording the whole native session
would charge non-AEW work to AEW and could conflate generations. (The first two versions of R8 recorded one record per
Lead session, committed by the broker when the session ended; that is superseded.)

- **One record per accounting segment:** `aew/lead-attachment-usage/v1`, holding `harness_session` (provenance only),
  `project`, `generation`, `attached_at`, `detached_at`, `usage_delta` (R1's normalized fields: `tokens`,
  `tokens_trust`, `provider_cost_usd`, `provider_cost_trust`, `effective`, `token_semantics`, `source`),
  `pricing_sha256` and `completeness` (`complete | partial | unavailable`).
- **A baseline, then a delta:** a usage baseline is taken and bound when the attachment becomes active, and the
  attributable delta is finalized at a normal detach or close. A normal close finalizes the attachment's record before
  revoking its generation. An unexpected loss yields `partial` or `unavailable`; usage is never manufactured.
- **Kept from the earlier R8:** one immutable cold record per segment, through the staged cold writer
  (`archive_ops._write_record`) as `history/lead/NNNNNN.yaml`, kind `lead`, indexed by the history manifest and never
  discarded; a bounded hot projection, the ring `state["lead"]["attachments"]` (the last 32: the same objects, never
  the only copy); the model cannot write it (the bridge refuses the transition from the model side, as it refuses
  credential-emitting commands); the Lead's usage is reported beside the units' totals and never added to any unit,
  Ticket or parent; `aew usage lead --all` walks the durable records.
- **No authority from a late exit:** a stale or detached generation must not later gain authority merely because the
  underlying TUI eventually exits. A normal close finalizes the record before the generation is revoked.
- **The source** is the harness's own usage data (for OpenCode, the standalone `session list` or `stats` output; the
  fields are a probe, §7), read at the baseline and again at detach; its derived cost follows R4 exactly (declared
  semantics, snapshot at record, mismatch unpriced).
- **Before the attachment lifecycle exists (open, for the designer):** F25 is on M4's main lane and F31 is not, so
  F25's Lead line would ship before `aew open` and `aew close` exist. The lead developer's proposal is to bound a
  segment by the span in which one Lead session's broker holds one generation's credential. That is close to the
  per-native-session boundary this revision moved away from, and on a takeover it leaves nobody with current authority
  assigned to write the superseded segment's `partial` or `unavailable` record. The designer decides the pre-F31
  boundary, and who writes an interrupted segment's record, before F25's Lead part is built (decisions-due, F25); the
  run usage of §5.1 to §5.6 does not wait for it.

### 5.8 Surfaces

**R9.** `aew usage show [WORK-ID] [--all] [--since UTC] [--until UTC] [--json]` (a unit's tree, or the project), `aew
usage runs [--invocation INV] [--json]` (one row per run with its record and derived cost), `aew usage lead [--json]`
(the Lead attachments). Text output is a table per level; JSON is the projection of R7 with every count and label. The
same `usage_ops` functions are what F19's collector calls for `aew/eval-run/v1`'s `cost` block and what a later
dashboard projection would read; nothing is computed twice in two places. `aew status --json` gains one bounded
`usage` summary for the hot state (runs counted, tokens summed, unpriced count), nothing more. Every project-level
projection, text and JSON, carries R7's `scope` and `archive_complete` (designer, 2026-10-06).

### 5.9 Non-goals and later work

**R10.** No budget refusal anywhere in this note (G7's modification). No dashboard route (contract 0.1.2 is frozen;
a `usage` projection is a 0.2 contract with a C0 review). No pruning of `local/harness/runs` (unrelated housekeeping;
after R5 the run record's usage survives pruning, which is a precondition for pruning ever being safe). No per-step
records in control state (bounded objects only; the raw snapshot stays in the run record). No prices from AEW (the
table is the project's, dated and sourced).

## 6. Engine edits, and the sequencing against M4-D

Additive edits, each with its own unit test:

1. `harness/usage.py` (new): `normalize(raw_usage, raw_assistant, effective, semantics) -> usage_record` and the closed
   `TOKEN_SEMANTICS` enumeration; the OpenCode adapter's `collect()` fills `usage_record`, choosing `token_semantics` per
   provider from its mapping table pinned to the qualified harness version (a version without a pinned mapping yields
   `unknown`); `base.py`'s docstring names both; the harness conformance suite gains the mapping's fixture test.
2. `harness/supervisor.py`: writes `result.usage_record` (one line beside the existing `result`).
3. `schemas/control.schema.json`: `invocations.*.runs[]` declared; `usage` optional with `pricing_sha256` and
   `token_semantics`; `lead.attachments` optional ring; `schemas/pricing.schema.json` (new: flat prices per billable bucket,
   no semantics); `schemas/lead-attachment-usage.schema.json` (new, the cold record); the manifest's optional `policy.pricing`.
4. `engine/usage_ops.py` (new): `copy_run_usage(state, inv_id, aew_root)` (R5's idempotent copy, called by the three
   paths, which also records `pricing_sha256` and writes the content-addressed snapshot `.aew/pricing/<sha256>.yaml`
   on first use), the projections of R7 with both derived figures, the price table reader, the bucket mapping by the
   record's `token_semantics` and the derivation (R4).
5. `engine/evidence_ops.py` (ingestion and `invoke cancel`), `engine/harness_ops.py` (relaunch), `engine/archive_ops.py`
   (the bundle finalizer): one call each to `copy_run_usage`.
6. `engine/lead_ops.py` and `harness/lead_broker.py`: the baseline bound when an attachment becomes active and the
   `lead.attachment_usage` transition at detach or close (one `history/lead/` record through
   `archive_ops._write_record` plus the ring entry, in one commit, before the generation is revoked); the bridge's
   refusal of it from the model side; `archive_ops._lead_entry` untouched.
7. `cli/usage_commands.py` (new) and its registration; `status_ops` gains the bounded summary.

**Sequencing.** M4-D's work changes `engine/api.py`, `evidence_ops.py`, `archive_ops.py`, `lead_ops.py`,
`workspace_ops.py`, `ports.py`, the control schema and the invariants (#65, D3), and D6 rewrites `aew harness wait`
over the run records. Edits 3, 5 and 6 touch those files, so the build starts after the overlapping M4-D work has merged and
coordinates D6's run-record reads with the lead developer (both read `runlog.read_record`; neither changes the run
record's existing keys). Edits 1, 2, 4 and 7 collide with nothing and may be built first on the same branch. PR numbers named here and in §8 (#60, #65) are implementation notes from 2026-10-05, not
requirements (designer, 2026-10-06); both have since merged.

## 7. The build plan and its tests (F25, after approval)

- **Slice 1 (no engine collision):** `harness/usage.py` with fixtures from the pinned OpenCode OpenAPI (a session with
  all categories; one with `cost: 0` and tokens; one with no usage; a truncated paging run); the supervisor writing
  `result.usage_record`; `usage_ops` projections over hand-built states with every label and count exercised; the
  price table schema (flat buckets; a row carrying semantics is refused), the adapter's `token_semantics` mapping pinned
  against the 2.0.18 OpenAPI fixture in the harness conformance suite (a fixture of another version with no pinned
  mapping yields `unknown`, and `unknown` is `unpriced_token_semantics_unknown`), each semantics value against
  hand-computed figures including the overlap cases (cached inside input, reasoning inside output), a negative bucket
  (`unpriced_inconsistent_counters`), a bucket with tokens and no price (`unpriced_category`), `match` versus
  `mismatch` versus a partitioned `tokens_by_model` run (priced per partition) versus an unpartitioned mix
  (`unpriced_effective_model_mix`, never the requested model), `unpriced_model`; the snapshot: the first copy under a
  digest writes `.aew/pricing/<sha256>.yaml`, a second never rewrites it, a changed `policy/pricing.yaml` changes
  `estimated_under_current_prices` and leaves `estimated_at_record` byte-identical, a missing snapshot is a doctor
  ERROR; property test: for any set of runs, the unit total equals the sum of invocation totals equals the sum of run
  figures, and the counts (including every unpriced reason) partition the runs.
- **Slice 2 (after the overlapping M4-D work):** the three copy paths, each shown to copy exactly once and to write an `absent`
  record for a run without a usage record; **a usage copy derives no event** (the transition's typed events are
  empty for that invocation: no `run.added`, no `invocation.status`) and ADR-0012's oracle rules 24 to 26 hold across
  it, with a wait-any consumer woken by its commit (every commit bumps the wake file) still waiting and returning
  nothing for it; **the size bound**: a record over 2 KiB or
  with a ninth distinct `effective` entry is refused by the schema and the invariants, and
  `tools/perf/control_plane.py` gains the usage copy in its series with H2 re-measured at 20 open and 3,000 completed
  units with every open run carrying a 2 KiB record (at most 10 ms derivation plus hash per commit, the ADR-0011
  bound), on the Windows reference machine and the Rocky 8 host; archival carries usage into the bundle and
  rehydration reads it back; a custody invocation without runs rolls up as `invocations_without_runs`;
  `aew usage show` on a project driven to archival (the dashboard suite's world is reusable) equals the sum computed
  from the run directories while they exist, and still answers after `local/harness/runs` is deleted; `--all` pages
  the archive; the Lead attachment's usage: a baseline bound at activation and the delta finalized at a normal close as its own
  `history/lead/` record plus the ring entry in one commit, before the generation is revoked, refused through the bridge
  (with a negative control); two attachments over one still-running harness conversation leave two records whose
  deltas exclude the non-AEW use between them; an unexpected loss leaves `partial` or `unavailable`, never an
  invented figure; a detached generation's TUI exiting later writes nothing and gains no authority; **40
  attachments** leave 40 cold records while the ring holds 32, and `aew usage lead --all` sums all 40;
  `_lead_entry` archives the ended credential unchanged.
- **Probe (before slice 2's Lead part):** OpenCode's standalone session or stats output on the pinned 2.0.18, read
  while the conversation is still running and again later in the same conversation (an attachment's baseline and its
  detach both happen while the harness keeps running), as well as after a TUI exit, to confirm which fields exist,
  whether per-conversation totals can be differenced, and whether cost is `0` under a subscription login (U4). Recorded with
  the design's evidence; if no readable source exists, the Lead line records `tokens_trust: absent` and says so.
- **Evidence for the designer's gate:** `tests/unit/test_usage_*.py`, `tests/integration/test_usage_ledger.py`; the
  invariants file gains "every `inv.runs[].usage`, when present, is a well-formed `aew/run-usage/v1` whose `run`
  matches its entry"; the credential scans unchanged (the record holds no secret and no path).

## 8. Decisions asked of the designer and operator

1. **R5, placement:** usage copied into `inv.runs[].usage` at the Lead's next transaction on the invocation (ingest,
   cancel, relaunch, archival), never by the supervisor. Alternative: a supervisor-initiated engine operation at the
   run's end, which would reopen OBX-45.
2. **R4, revised after the designer's review (2026-10-05):** the derived cost is never stored; it is computed at read
   under the pricing snapshot recorded at copy (`estimated_at_record`, reproducible) and, separately, under today's
   table (`estimated_under_current_prices`); priced only over the non-overlapping buckets the adapter's declared
   `token_semantics` yields (pinned by the conformance tests, never a price-row setting); a missing price or unknown
   semantics is `unpriced`, never zero; a model mismatch or mix is `unpriced` unless usage is
   partitioned per model. Alternative rejected: freezing a dollar figure into the record (authority would hold a
   number that was never a fact).
3. **R3, the trust labels** and the rule that `zero_with_tokens` is unpriced, not free.
4. **R7, roll-ups as projections**, including `--all` over the archive through the history index, and no stored
   totals.
5. **R8, revised after the designer's review (2026-10-05):** the Lead session's usage as a broker-committed
   `lead.session_usage` transition that writes one `history/lead/` cold record per session (durable, never discarded)
   **and** the bounded hot ring entry in the same commit; `aew usage lead --all` sums every session; refused from the
   model side; never summed into units. Alternative: no Lead line in v1 (U4 stays open). *Superseded by the designer's revision of
   2026-10-06: usage per AEW attachment and generation (§5.7, §10).*
6. **R9, the surface names** (`aew usage show|runs|lead`) and the one bounded summary in `aew status --json`.
7. **R10, non-goals:** no budget refusal, no dashboard route, no pruning, no per-step records.
8. **§6 sequencing:** slice 1 may start now; slice 2 after #60 and #65, coordinated with D6.

## 9. Register and ledger

Every requirement here is in `docs/design/requirements-ledger.yaml` under the prefix CUL, tracked by F25 (and U4 for
the Lead line). The register's F25 row points at this note; U4's note already says F25 absorbs it. The status line
records the decisions when they are made; the build's PRs link back to the sections they build.

## 10. The designer's disposition (2026-10-06)

The designer's answer to §8, recorded as given. This version (v0.2) makes the edits it asks for: R8 in §5.7, the
scope and completeness of R7 and R9 in §5.6 and §5.8, and the non-normative PR numbers in §6 and §7. With them, F25 is
adopted and implementation-ready.

> F25 — REQUEST NARROW REVISION, then ADOPT
>
> The design is sound. No new design cycle is needed. Seven of the eight §8 decisions are accepted; R8 needs one post-Q12 correction, and R7/R9 need one presentation clarification.
>
> 1. R5 placement — APPROVE.
> Copy run usage into `inv.runs[].usage` at the next legitimate Lead transaction on that invocation. Do not reopen OBX-45 by introducing supervisor-initiated accounting commits. Preserve `provisional` / `missing` states until the durable copy occurs.
>
> 2. R4 pricing — APPROVE.
> Keep usage facts immutable and derive dollar estimates at read time. Preserve:
>    * adapter-declared/pin-qualified `token_semantics`;
>    * non-overlapping billable bucket conversion;
>    * missing price = `unpriced`, never zero;
>    * immutable pricing snapshot for `estimated_at_record`;
>    * current table separately for `estimated_under_current_prices`;
>    * effective-model mismatch/mix unpriced unless usage is partitioned per model;
>    * requested model is never substituted for effective model when pricing.
>
> 3. R3 trust labels — APPROVE.
> In particular, `zero_with_tokens` means unpriced/unknown economic cost, not free.
>
> 4. R7 roll-ups — APPROVE WITH CLARIFICATION.
> Roll-ups remain projections and are never stored totals.
> Add an explicit scope/completeness field to project-level projections so the default hot + recent-history view cannot be mistaken for a lifetime project total. Equivalent semantics are sufficient, e.g.:
>
> ```
> scope: recent
> archive_complete: false
> ```
>
> `--all` is the archive-backed/lifetime projection.
>
> 5. R8 Lead usage — REVISE.
> Q12 makes the AEW attachment/generation, not the native TUI/harness session, the accounting boundary.
> A harness conversation may exist before attachment, survive `aew close`, contain ordinary non-AEW work, and later receive another AEW generation. Recording the whole native session would therefore attribute non-AEW work to AEW and can conflate generations.
> Replace “one Lead-session usage record” with an attachment-scoped record, conceptually:
>
> ```
> aew/lead-attachment-usage/v1
>
> harness_session: <provenance only>
> project: ...
> generation: ...
> attached_at: ...
> detached_at: ...
> usage_delta: ...
> pricing_sha256: ...
> completeness: complete | partial | unavailable
> ```
>
> Take/bind a usage baseline when the attachment becomes active and finalize the attributable delta at normal detach/close. Unexpected loss may produce `partial` or `unavailable`; do not manufacture usage.
> Preserve the good parts of R8:
>    * one immutable cold record per accounting segment;
>    * bounded hot projection;
>    * model cannot write it;
>    * Lead usage never joins Ticket/unit totals;
>    * `aew usage lead --all` walks the durable records.
> Normal close should finalize the attachment record before revoking that generation. A stale/detached generation must not later gain authority merely because the underlying TUI eventually exits.
>
> 6. R9 surfaces — APPROVE.
> Keep `aew usage show|runs|lead`, JSON from the same projection code, and the bounded `aew status --json` summary. Propagate the R7 scope/completeness metadata.
>
> 7. R10 non-goals — APPROVE.
> No budget refusal, dashboard route, local-run pruning, or per-step ledger records in F25. Measurement first; budget enforcement remains later policy work.
>
> 8. §6 sequencing — APPROVE, but keep repository scheduling non-normative.
> Collision-free work may proceed independently. The engine/schema integration slice follows the overlapping M4-D work and coordinates with D6. PR numbers such as `#60/#65` may remain implementation notes, but should not become durable architectural requirements.
>
> Disposition
> Revise R8 to attachment/generation accounting, add explicit projection scope/completeness to R7/R9, and keep PR-number dependencies non-governing.
> After those edits:
> F25 is ADOPTED and implementation-ready.

