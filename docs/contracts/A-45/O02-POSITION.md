<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-45
source: 30-stages/STG-21-O02-independent-outage-reader/adopted/o02-r2.1/O02-POSITION.md
source-sha256: d6d40c4aa7e442dfdf02839a0dca087982b7d0012bca2b250c2c294fd230b7a5
edits-sha256: none
-->

# The independent outage reader, O-02 (PROPOSED, revision 2.1)

**Namespace:** `O02-`
**Status:** proposed; nothing here is adopted.
- It is a read profile on D-01 0.3.4 (A-25) for a new channel, the operator's outage reader.
- It amends no adopted text, and adds no D-01 route, field or value.
- Its adoption answers the open half of `S-DEC-03`.

**Authority:** the operator's decision to start O-02 (`00-governance/decisions/2026-10-28-operator-start-O-02-now.md`), in
the wire track's order (`00-governance/decisions/2026-10-25-operator-wire-track-ahead-of-publication-tooling.md`).
**Threat model:** the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`): a
contained agent cannot fake an approval, forge an owner fact, read a credential or escape. Malicious code running as the
operator is out of scope (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`).
- **What is at stake here:** an agent reading what is the operator's, or an outage read presenting a stale or forged
  record as current.

**Research consulted:** `tools/research_index.py lookup`, by position and requirement.
- **A-17:** the containment study (`containment-and-process-ownership-rocky8-research-2026-10-01`). Its launch self-test
  is what `O02-02.a` relies on. Its finding that Windows has no equivalent containment is behind `O02-09`.
- **A-09:** the harness study (`harness-native-integration-research-v0.3`). It does not bear.
- **None:** the lookups for `AEW-FR-30`, `AEW-FR-29`, `AOI-09.a`, `AOI-03.d`, `IM-G04`, `CNI-08.d`, `S01-16`, `S01-17`,
  `HEB-01.e`, `AS-38` and `OI-X08`, and for the terms "outage" and "independent reader".

**Files:**
- this file;
- the regression aid for the gate, not normative: `verify_o02.py` and `o02-cases.json`;
- the inputs: `inputs/fact-map-2026-10-28.md` and `inputs/design-comparison-2026-10-28.md`;
- the answers to round 1: `CHANGES-r2.md`; and to the quick check: `CHANGES-r2.1.md`.

## What the adopted text already decides

- **The need:**
  - an authorized, non-LLM-dependent read of persisted project information during a gateway or Lead outage
    (`AEW-FR-30.a`);
  - a path that does not need the main live orchestration service (`AEW-FR-30.b`);
  - status labelled last-known when current state cannot be established (`AEW-FR-30.c`);
  - confidentiality, integrity and mutation restrictions kept (`AEW-FR-30.d`);
  - a routine status view with no live Lead (`AEW-FR-29.a`), which `O02-01` meets;
  - assignment, disposition, blockers and pending decisions (`AEW-FR-29.b`), which the work, waiting, attention and
    runs rows meet. Its resource allocation is not served: continuation-state's `IF10` and `R01` axes are `unknown`;
  - observed state kept apart from inferred activity (`AEW-FR-29.c`), which `O02-04.b` meets: a run's phase is
    agent-reported;
  - recency shown (`AEW-FR-29.d`);
  - current, stale, unavailable, unsupported and historical told apart, with an explicit destination for a subject
    that is not available (`OI-FR-03`), which `O02-05` and `O02-08.c` meet;
  - A-32's `U07` (`OUTAGE_READ`), which `O02-01` meets;
  - the scenarios `AS-16`, `AS-38` and `OI-X08`.
- **The rules:**
  - an outage read qualifies three things separately: integrity and as-of, present entitlement, and the disclosure
    subset. It declares its safe minimal discovery profile (`AOI-09.a`);
  - historical data proves only what it covered (`AOI-09.b`);
  - no outage surface admits or queues an effect (`AOI-09.c`);
  - a reader that cannot qualify present entitlement fails closed for protected details (`AOI-03.d`);
  - holds and required decisions stay discoverable through it (`CNI-08.d`);
  - opening a view resumes nothing (`HEB-08.g`);
  - read-only status goes only through an independently safe path (`HEB-01.e`);
  - a missing service creates no alternate effect path and no live status (`S01-16`);
  - a valid D-01 response certifies nothing (`S01-17`);
  - each channel gets its own conformance (`AOI-12.b`);
  - an outage read need not go through the API or the site (`OI-FR-02`), which `O02-R04` relies on;
  - Knowledge's answer in an outage is an explicit degraded or unknown one, never a fabricated fallback (`K01-11`),
    which `O02-08.b` meets;
  - a requested target is not an effective one (`IF13-03`): the reader shows a recorded request as recorded, and
    `O02-03` keeps reading from making it effective;
  - a release capability that needs a human answer has a discover and respond path (`AOI-09.d`). This channel only
    discovers; the response is each owner's own path (`O02-03`).
- **The gate:** outage results disclose integrity, currency, set coverage and disclosure restrictions. They claim no
  exhaustive current absence (`IM-G04`). Each host's release gate is recorded (`S01-30`).
  - **Conformance** runs the shared fixtures on each channel, and synthetic or schema-only evidence qualifies none of
    G1 to G4 (`S01-27`, `IF12-20`). So `O02-Q03` checks conformance, and only `O02-09`'s host record moves G4.
  - **Coverage** can be declared qualified only by a competent evaluating owner, never by a RELEASE stamp
    (`D01-WR-21`), which bears on `O02-B2`.
- **The wire:** D-01 0.3.4's `ReadResult`, `SourceStamp`, `Renewal`, `Disclosure`, `PageInfo` and `Problem`, with their
  enums and each route's own response schema (A-25). What a stamp may claim:
  - a present-current conclusion derived from an owner carries that governing owner's qualified renewal (`AOI-04.a`),
    and the `SourceStamp` schema admits `present_current` only as `qualified`, with a renewal that names its source
    proof;
  - historical data proves only what it covered, and read-only delivery does not make an agent-writable source
    authoritative (`AOI-09.b`);
  - on the three routes STG-01 added (continuation-state, hold recovery and owner operations), A-25's owner-pin rules
    add more: an unqualified stamp is never `present_current` (`OP-03`); a renewal is the producer's own (`OP-04`);
    a current renewal is finite, later than now, and within the owner's recorded maximum (`OP-06`); a qualified stamp
    is exactly the owner's own fact (`OP-09`). They do not reach the seventeen inherited routes.
- **Containment:**
  - every agent context runs contained only where every agent's launch path runs the self-test, the Lead's included, and
    that needs CS-4 (`G3-12`, `CB-01`);
  - no writable bind reaches the store (`CB-07`).

## The parts

| Part | What it is | Writer | Reader |
|---|---|---|---|
| The store | `.aew/state`: the control file with its checksum, the redo records, and the transition log with its hash chain | AEW's host code, under the control lock | AEW's host code; every contained context, read-only |
| The pinned records | the records the control state pins by hash, in the git-kept `.aew/` tree: each work unit's record, plans, evidence, completion record, stage intents, dispositions and sealed threads, the manifest and the policy files | AEW's host code | as the store |
| The local state | `.aew/local`: the Lead's beat, run harness state, the notify spool and the notifier's summary, the operator endpoint, steering state, packs and the recall index | AEW's host code and its services; each run writes its own harness state, which is among its writable roots (`src/aew/harness/containment/layout.py:16-20, 28-29`) | the operator's account outside the sandbox; masked from every contained run but for the run's own directories |
| The live services | the Lead broker, run supervisors, the dashboard server, the operator endpoint, G3's service and the provider relay | their own processes | not needed by this channel |
| The outage reader | the channel this position defines: one read-only `aew` subcommand | writes nothing | the operator |

## Rules

**O02-00. Precondition: AEW's records are files.** The outage reader needs no live service because the store and the records it pins are files that AEW's host code writes.
- A fact held outside AEW's store, in a service's memory or in another program's host records, is never an item here
  (`O02-06.b`).
- If a future store needs a service before it can be read, this position is revised before that store ships.

**O02-01. The channel: one read-only command, always available.** The operator's outage reader is one `aew` subcommand that answers this position's profile with D-01 0.3.4 results and needs no live service.
- **Candidate:** `aew read <route>`, which prints the result as JSON, with a human rendering derived from it.
- It is the same command whether or not any service is up. It detects no outage, and it has no outage mode.

**O02-01.a** It is declared a non-writer: it takes no lock, runs no recovery, and works on a store it cannot write.

**O02-01.b** It writes nothing: not the store, not the pinned records, not `.aew/local`, not the repository, and no service.

**O02-01.c** A human rendering says no more than the result it renders. It adds only three things the wire cannot carry: the sources the reader did not read (`O02-06.b`); why a result is partial, which `partial_source` alone does not say; and, for an `unsupported` route, where its fact is read instead (`O02-08.c`, `O02-R09`).
- **It always states the result's outcome and each limitation,** an empty list included.
- **An empty list read from the store,** `historical` or `partial`, reads "none committed as of" the read's time,
  never "none pending". An empty `partial` list says that it is partial, and why.
- **A result that read nothing claims nothing about what is committed:**
  - an `unavailable` one reads "the store could not be read as of" the read's time;
  - an `unsupported` one reads "not read on this channel", with where its fact is read instead.

**O02-02. Who may read: the operator's own process, outside AEW's sandbox.** Any other caller gets D-01's `authentication_unqualified` problem, with the fixed text of `O02-02.e`, and nothing else.

**O02-02.a** Only a process outside every AEW sandbox passes. An environment variable can only refuse a read, never permit one.
- **Candidate:** the check sees what AEW's sandbox keeps out of every contained run: the control lock of the project
  whose store it reads, in that project's real `.aew/local`. As built, the lock is `.aew/local/control.lock`
  (`src/aew/engine/store.py:110`), so the two are one observable.

**O02-02.b** It is refused inside a Lead session, locally and without forwarding to the broker, since there the CLI forwards to the broker (`src/aew/cli/main.py:128-147`). It is refused inside a worker run too, whose CLI surface is the run's bridge (`docs/reference/entry-points.md:17` at `main`).

**O02-02.c** Where containment is not established (`G3-12`), the check in `O02-02.a` is vacuous: an uncontained agent passes it.
- That discloses nothing the agent cannot already read (`O02-04`).
- Every result there carries `G4_unqualified` (`O02-09`).

**O02-02.d** No revocation applies to the operator's own reading: AEW's grants and their revocations bind agents.

**O02-02.e** The refusal says what to do instead, in one fixed text for every refused caller, so it reveals nothing about the caller. The text is in `Problem.title` and in the rendering.
- **Candidate:** "This is the operator's outage read, run outside AEW's sandbox. In a Lead session use `aew status`; in a
  worker run use `aew check run`. Outside a sandbox, run an `aew` command that writes, such as `aew status`, once to
  restore `.aew/local`."
- **Why the last sentence:** the lock file is made only when a writer opens it (`src/aew/engine/lock.py:108-109`), so
  a project whose `.aew/local` was cleared refuses the operator too, until a writer runs. The operator's `aew status`
  is a store writer; this reader is not (`O02-01.a`).
- D-01 fixes this problem's `retry` to `reauthenticate` (`O02-R08`).

**O02-03. No effect, ever.** No route admits, queues or authorizes an effect, and reading resumes, launches, reruns or restores nothing (`AOI-09.c`, `HEB-08.g`).
- An action the operator takes after reading goes through its owner's own path, with that path's checks at that time.

**O02-04. What it discloses: committed records, and the live observations `O02-04.b` names.** The reader reads the store, the pinned records and the transition log. From `.aew/local` it reads only what `O02-04.b` names.
- **Never read:** transcripts, tool-call logs, a run's bridge key, requests, scratch and private git state, packs, the
  notify spool and the notifier's summary, the operator endpoint, steering state, credentials and the recall index.
- **Narrative fields are inert text** (`AOI-04.f`).

**O02-04.a** The safe minimal discovery profile (`AOI-09.a`) is declared for both conditions a host can be in.
- **Where containment holds** (`G3-12`), present entitlement is `O02-02`'s check. The refused caller's profile is
  empty: it learns only `O02-02.e`'s fixed text.
- **Where it does not,** present entitlement cannot qualify, since an uncontained agent passes the check
  (`O02-02.c`). The whole served profile is then `AOI-09.a`'s owner-permitted historical discovery:
  - committed records, and the live observations `O02-04.b` names;
  - every stamp unqualified, and `historical` or `stale`;
  - every result carrying `G4_unqualified`.
- **Adopting this position is that permission.** It discloses nothing the account cannot already read, and it needs
  no new principal (`O02-R07`).
- **Every item's disclosure,** and every result's effective recipient, are as the Interfaces section states. Neither
  names the operator, since no read qualifies who the caller is.

**O02-04.b** From `.aew/local`, the reader reads exactly these, each stamped `stale` at its own time (`O02-05.b`):
- the Lead's beat time, from its liveness file under `local/lead`, and never the tool-call log beside it;
- for each run a committed invocation names, its run record's `status` field and its heartbeat's age, as
  `runlog.observed_status` reads them (`src/aew/harness/runlog.py:184-197`).

A run's phase from these is agent-reported, never observed (`O02-R11`):
- `REPORTED_ACTIVE`, `REPORTED_FINISHED` or `UNKNOWN`, with `phase_observation_class` `AGENT_REPORTED`, as STG-02's
  slice stamps it (`src/aew/stg02/reads.py:260-263`);
- a run's harness state is among its own writable roots, and read-only delivery does not make it authoritative
  (`AOI-09.b`).

A stopped heartbeat is carried in D-01's own values. A run recorded as running whose heartbeat is older than the
lock-free reader's staleness limit (`src/aew/harness/runlog.py:37`, 195) reads `phase` `UNKNOWN`, `stall_assessment`
`POSSIBLE_STALL`, with a `stall_basis_ref` naming the run, and the `RunData` limitation `progress_suspected`. These are
agent-reported too.
- D-01's phase has no finer value for an ending: a crashed run and one that ended with its evidence both read
  `REPORTED_FINISHED`.

**O02-05. Currency: never current, never qualified.** No stamp on this channel is `present_current` or `qualified`.
- **Why:** a present-current conclusion needs its governing owner's qualified renewal (`AOI-04.a`, and the
  `SourceStamp` schema's own condition), and no owner issues one for AEW's store records.
- **Historical data** proves only what it covered (`AOI-09.b`).
- **On STG-01's three routes,** `OP-04`, `OP-06` and `OP-09` say the same.

**O02-05.a** A committed record is `historical`, with these values:
- `observed_at`: the time of the read;
- `source_version`: the store's revision;
- `qualification`: `unqualified`;
- `authority_class`: `unqualified_report`;
- `owner_coverage_class`: `not_established`;
- `renewal`: `none`.

**O02-05.b** A live observation is `stale`, with `observed_at` the time it was made. It is last-known (`AEW-FR-30.c`).

**O02-05.c** A result's `continuity` depends on its items, and is never `source_qualified`, which would need every item to be `present_current`:
- `revalidate_required` when the result holds items;
- `unknown` when it holds none.

**O02-05.d** Every result carries the limitations `historical_only` and `source_unqualified`.

**O02-05.e** A complete read answers `historical`, never `provided`, which would read as complete and current.
- A list's `page.membership` is `unknown`, never `qualified_scoped`, which needs a `present_current` collection basis.
- Every result's `collection_basis` is null.

**O02-06. Absence: an empty list proves only what was committed.** A list states what the store held at the time of the read, and claims no current absence (`AOI-09.b`, `IM-G04`).

**O02-06.a** A list is `partial`, with `partial_source`, while a committed record names a writer that may still be running: an active invocation, or an attached Lead.

**O02-06.b** A source outside AEW's store that may hold an operator need is never shown as absent. Where such a source exists on the host, the result is `partial`, with `partial_source` and `source_unavailable`, and the rendering names the source.
- **The reader checks only that the source exists.** It never reads it: such a source carries no pin, as `knowledge/`
  carries none (`O02-R05`).
- **Today the sources are these,** each on the read whose items it would hold:
  - **on the waiting read, G3's:** an approval pending in G3's memory, and the G3 client's per-host approval records,
    which STG-20 keeps outside the store (`O02-R06`). Where G3 is not on the host, neither exists;
  - **on the attention read, the notifier's:** the notify spool and the notifier's summary in `.aew/local`, which
    `O02-04` never reads (`O02-10`).
- **A committed record of the same need,** where one exists, is an item under `O02-05.a`.

**O02-07. Integrity: checked at every read, reported, never repaired.** Each read checks the control file's checksum, each record's pin and the log's chain before it answers.

**O02-07.a** If the control file is missing, cannot be opened after the reader's bounded retry, or fails its checksum, the read is `unavailable`, with `continuity` `unknown` and no items. A route whose schema needs one item answers the problem `O02-08.b` names instead.
- The retry is the one the lock-free reader already makes for a Windows sharing violation
  (`src/aew/engine/store.py:477-480`).

**O02-07.b** A record that does not match its pin is reported, not trusted: every stamp drawn from it is `stale`, the item's own and each of its field sources, in whichever item it is drawn into, and the result is `partial`, with `partial_source`.
- So a run whose work unit's record fails its pin makes the runs read `partial`, and a continuation vector gives the
  failed pin as a reason beside its missing axes.
- This is the committed-but-unapplied window. Only the store's writers close it.

**O02-07.c** A gap in the transition log's hash chain makes any history the reader shows `partial`, with `partial_source`. A gap is never skipped.

**O02-07.d** A history-audit result is shown only from an attributable audit run (`D01-EXT-09`).

**O02-07.e** A pinned record that is missing, rather than mismatched, is reported as missing (`src/aew/engine/store.py:474-475`). Its item is built from the control state and is `stale`. Each field drawn from the record, in whichever item, has a field source that is `unavailable` and `not_established`, and the result is `partial`, with `partial_source`.

**O02-08. The profile: twenty routes, as the Interfaces table states.** The reader answers D-01 0.3.4's twenty GETs and nothing else, each with a body its route's own response schema admits. A route outside them is D-01's `invalid_request`.
- **The order of the answer:** the caller (`O02-02`), then the route (`O02-08`), then an `unsupported` row
  (`O02-08.a`, `O02-08.b`), then the store (`O02-07`).

**O02-08.a** A route the table marks `unsupported` reads nothing, so it answers the same whatever the store's state: `unsupported`, with no items and no stamp, where its route's schema admits a body with no items, and otherwise as `O02-08.b` names.

**O02-08.b** Three routes' schemas need what a body with no items lacks, and the table names their answers:
- **`/v1/read/knowledge`:** `unsupported`, with a `journal_selection` that states no qualified selection exists:
  `selection_kind` `aev_finalized_adverse_determination`, `status` `not_established`, `owner_source` null, and
  `scope_ref` `aew:project:<project id>` (`K01-11`);
- **`/v1/read/holds/{hold_id}/recovery`:** D-01's `not_found_or_not_disclosable` for every hold id, since no AEV hold
  record is built (`O02-R10`);
- **`/v1/read/continuation-state/{work_id}`:** served. Where the store cannot be read (`O02-07.a`), it answers D-01's
  `owner_unavailable` problem, as STG-02's slice does (`src/aew/stg02/reads.py:290-293`).

**O02-08.c** An `unsupported` route's rendering says where its fact is read instead, as the table's Answer column names. `aew read` with no route lists the profile, and what each route answers (`OI-FR-03`).

**O02-09. G4: recorded per host, and never where an agent can write the store.** Every result carries `G4_unqualified` until the host's G4 record exists.
- **The host's G4 record needs both of these:**
  - a built reader has passed this position's gate on that host, recorded with `S01-30`'s fields;
  - `G3-12`'s containment condition holds there.
- **Why the second:** an agent that can write the store can rewrite its checksum and its pins too, so the checks in
  `O02-07` then show only that nothing was damaged by accident.
- **So on Windows,** which is outside the enforced gate, and on every host until CS-4, every result carries
  `G4_unqualified`.

**O02-10. Waiting and attention in an outage: the producer's items, this position's stamps.** The two reads answer from committed records, under `O02-05` to `O02-07`. Which records become items, and in which category, is the normal producer's mapping, which this position cites and does not restate.
- **Today** that mapping is the dashboard's derivation at `main` (the Interfaces table), minus anything it sources
  from `.aew/local` beyond what `O02-04.b` names. STG-20's position replaces it once adopted.
  - So a run's recorded status and heartbeat are there for the mapping to use. Which category an item takes, if any,
    is the mapping's.
  - **Attention held only in `.aew/local`,** the notify spool and the notifier's summary, is not read, and the
    attention read answers under `O02-06.b` wherever either exists.
- **The agent lane** (`agent_attention`) is `unsupported` until an agent's raise is a committed record.

**O02-11. What other builds must record: an operator need that an outage must show is a committed store record.** `CNI-08.d` requires such a need to stay discoverable. Outside the store, `O02-04` reads only the observations `O02-04.b` names, and none of them is an operator need.
- **O-01's owner operations,** which A-32's row `SCOPE/U05` reads through `/v1/read/owner-operations`, are committed
  store records once the O-01 carrier is built. Until then the route is `unsupported`.
- **STG-20's blocked-on-you items** that an outage must show are committed store records, the Lead's open question
  among them. STG-20 keeps a G3 approval's record per host instead, so an outage read answers it under `O02-06.b`.
  Whether that meets `CNI-08.d` is STG-20's ruling (`O02-R06`).

## Interfaces

### The command

- **Candidate:** `aew read <route>` prints one D-01 0.3.4 `ReadResult` or `Problem` as JSON, and `--human` renders it.
  The exit code is zero for a `ReadResult`.
- **With no route,** or with `--help`, it lists the profile below and what each route answers (`O02-08.c`).
- It is declared in `aew.process_kind`'s registry as a non-writer, as `aew dashboard serve` is
  (`docs/reference/entry-points.md` at `main`). Its surface-map entry ships with it.

### Every stamp

Every stamp is checked against this whole table: the item's own, and each of its field sources.

| Field | Value on this channel |
|---|---|
| `owner` | the owner D-01 fixes for the route's resource |
| `fact_ref` | `aew:<kind>:<id>` |
| `source_epoch` and `coverage_ref` | `aew:project:<project id>` |
| `source_version` | `aew:rev:<revision>` |
| `observed_at` | the time of the read for a committed record; the observation's own time for a live one |
| `qualification` | `unqualified`; `not_established` with `observation_state` `unavailable` |
| `observation_state` | `historical`, `stale` or `unavailable`; `stale` for every stamp drawn from a record that fails its pin (`O02-07.b`) |
| `renewal` | kind `none`, every field null |
| `authority_class` | `unqualified_report` |
| `governing_owner` | null |
| `owner_coverage_class` | `not_established` |
| `issuer_ref` | `aew:engine` |

### Every item's disclosure, and every result's recipient

| Field | Value on this channel |
|---|---|
| `form` | `full`: the served subset is the committed record itself, with nothing withheld inside it. `qualified_coarse` and `redacted` would each say that a qualified release shaped it, and none did |
| `policy_ref` | `o02:outage-historical-discovery` (`O02-04.a`) |
| `scope_ref` | `aew:project:<project id>` |
| `effective_recipient_ref` | `aew:local-account`: a process of the account, outside AEW's sandbox. No read qualifies it as the operator (`O02-04.a`, `O02-R12`) |
| `qualified_release` | false |

The `ReadResult`'s own `effective_recipient_ref` is `aew:local-account` too.

### The profile

The as-built column reads AEW at `main` `21ea8674`. "Live" marks a field taken from a live observation, stamped under
`O02-05.b`. Each `unsupported` answer names where its fact is read instead, and the rendering says so (`O02-08.c`).

| Route | Owner | As built | Integrity | Answer |
|---|---|---|---|---|
| `/v1/read/coverage` | RELEASE | none | none | `unsupported`. D-01's coverage `channel` has no value for this channel (`O02-B2`). Instead: `aew read` with no route lists what this channel covers |
| `/v1/read/waiting` | CNI | work units in a waiting state, in the control state (`src/aew/stg02/world.py:32`, `src/aew/stg02/reads.py:117-174`); G3's approvals are per host, outside the store | the checksum | served (`O02-10`); a G3 approval is never an item, and where G3 is on the host the read is `partial`, with `source_unavailable`, naming the G3 client's records (`O02-06.b`) |
| `/v1/read/attention` | CNI | no D-01 producer; the dashboard derives attention from unit states, contradictions and run observations, and adds the notifier's summary (`src/aew/dashboard/projections.py:494-542`) | the checksum; a run's status and heartbeat are live | the owner lane served from the mapping minus anything sourced from `.aew/local` beyond `O02-04.b`; where the notify spool or the notifier's summary exists, `partial`, with `source_unavailable`, naming it (`O02-06.b`, `O02-10`); the agent lane `unsupported` |
| `/v1/read/attachments` | HEB | the Lead's record: status, generation and session label (`src/aew/engine/resume_ops.py:581-587`); its beat under `.aew/local/lead` | the checksum; the beat is live | served: the record `historical`, the harness state `stale` |
| `/v1/read/attachments/{attachment_id}` | HEB | as the list | as the list | as the list |
| `/v1/read/work` | CNI, with WIS for `accepted_revision` | the control state's work (`src/aew/engine/resume_ops.py:590-592`) | the checksum and the record pins (`src/aew/engine/archive_ops.py:101-110`) | served |
| `/v1/read/work/{work_kind}/{work_id}` | as the list | a hot unit, or an archived one as it stands (`src/aew/engine/resume_ops.py:576-580`) | the checksum, the pins, and the archive index's hashes | served; history is read here (`O02-R05`) |
| `/v1/read/work/{work_kind}/{work_id}/packages` | WIS, with AEV for `g1` | the unit's pinned evidence (`src/aew/engine/archive_ops.py:104`) | the evidence pins | served |
| `/v1/read/assurance/{subject_kind}/{subject_id}` | AEV | the gates and their pinned records (`src/aew/engine/assurance_ops.py:45-79`) | the checksum and the pins | served |
| `/v1/read/research/claims/{claim_id}` | RESEARCH | not built | none | `unsupported`. Instead: none on this channel until research claims are built (`O02-B4`) |
| `/v1/read/knowledge` | KNOWLEDGE | `knowledge/`, with no pin | none | `unsupported`, with `journal_selection` `not_established` (`O02-08.b`, `O02-R05`). Instead: lessons are read through archived work units, under `/v1/read/work/{work_kind}/{work_id}` |
| `/v1/read/knowledge/{knowledge_id}/versions/{version_id}` | KNOWLEDGE | as the list | none | `unsupported`. Instead: as the list |
| `/v1/read/knowledge/{knowledge_id}/versions/{version_id}/activity` | KNOWLEDGE | as the list | none | `unsupported`. Instead: as the list |
| `/v1/read/resolve` | the target's owner | targets within this profile | as the target | served for a target in the profile; any other is `not_found_or_not_disclosable` |
| `/v1/read/capabilities` | none fixed | the capability register, outside the store's pins | none | `unsupported`. Instead: none on this channel until the register's records are pinned (`O02-B4`) |
| `/v1/read/runs` | none fixed | invocations in the control state (`src/aew/stg02/reads.py:175-280`); each run's record `status` and heartbeat under `.aew/local/harness/runs` (`src/aew/harness/runlog.py:184-197`) | the checksum; a run's status and heartbeat are live and agent-written | served: the invocation `historical`; the phase agent-reported and `stale`; a stopped heartbeat `POSSIBLE_STALL`, with `progress_suspected` (`O02-04.b`, `O02-R11`) |
| `/v1/read/runs/{execution_id}` | as the list | as the list | as the list | as the list |
| `/v1/read/continuation-state/{work_id}` | each axis's own owner, as A-25 pins it | the axes from the control state (`src/aew/stg02/reads.py:282-362`) | per axis | served. Every axis is `state` `unknown`, since `ok` and `blocked` need a qualified fact. An axis the store records is `unqualified`, with its epoch, version, basis and time, reason `SOURCE_UNQUALIFIED`; a missing axis is `not_established`, reason `SOURCE_UNAVAILABLE`. Each axis's field source is `historical` or `unavailable`, as STG-02's slice states them (`src/aew/stg02/reads.py:304-315`). While any axis is missing, which at `main` is all but WIS's, the result is `partial`, with `partial_source` and `source_unavailable`. Where the store cannot be read, `owner_unavailable` (`O02-08.b`) |
| `/v1/read/owner-operations` | the entry's owner | STG-02's slice ledger, outside the store (`src/aew/stg02/server.py:80-86`) | none | `unsupported` until `O02-11`. Instead: none on this channel until O-01's owner operations are committed records |
| `/v1/read/holds/{hold_id}/recovery` | AEV | no AEV hold record is built | none | `not_found_or_not_disclosable` for every hold id (`O02-08.b`, `O02-R10`). Instead: the unit a hold would bind is read under work and assurance |

Twelve routes are served and eight are `unsupported`. Hold recovery's `unsupported` answer is a problem, since its
schema needs one item (`O02-08.b`).

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **O02-Q01** | The reader needs no service: every live service is stopped and the store is mounted read-only, and each served route still answers (`O02-01`, `O02-01.a`) | every served route answers, and none waits on a service |
| **O02-Q02** | Nothing changes: the hashes of `.aew/state`, `.aew/local` and the git-kept `.aew/` tree are byte-identical before and after every route runs (`O02-01.b`, `O02-03`) | identical |
| **O02-Q03** | Every result validates against its route's own response schema in D-01 0.3.4's frozen OpenAPI file, and every stamp and disclosure against this position's tables, on the shared fixture inventory (`O02-05`, `O02-08`, `AOI-12.b`, `S01-27`) | every result valid |
| **O02-Q04** | Who may read: a Lead session, a worker run and a contained process are each refused with `authentication_unqualified`, `O02-02.e`'s fixed text and nothing else (`O02-02`) | refused. It runs only where `G3-12` holds, and is recorded as not run elsewhere |
| **O02-Q05** | Integrity: a missing control file, a damaged checksum, a pin mismatch, a missing pinned record and a chain gap each give the answer `O02-07` states, on a list route, a detail route and continuation-state | as stated |
| **O02-Q06** | Currency and absence (`O02-05`, `O02-06`): no `present_current`, `qualified` or `source_qualified` anywhere; a complete read `historical`, with `membership` `unknown`; a list with a running writer `partial`; every rendering stating its outcome and limitations, and an empty list's claiming nothing current | as stated |
| **O02-Q07** | Disclosure: a planted marker in each never-read part of `.aew/local`, a run's transcript and tool-call log among them, and in the G3 client's records, appears in no output and no rendering (`O02-04`, `O02-06.b`) | absent from every output |
| **O02-Q08** | The host record: the host's G4 record names `S01-30`'s fields, and `G4_unqualified` drops only where it exists (`O02-09`) | recorded |

## Scenarios

**O02-X01.** The gateway, the Lead and the site are down, and the operator reads the persisted Tickets, findings and history. Every answer is marked historical (`AS-16`, `OI-X08`; `O02-01`, `O02-05`).

**O02-X02.** A contained agent runs the read, and it is refused with `authentication_unqualified` (`AS-38`; `O02-02`).

**O02-X03.** A unit's review has failed, and the site shows a cached green status. The reader shows the unit's committed state and claims no clearance (`CNI-X38`, `IF-11`; `O02-05`, `O02-06`).

**O02-X04.** A client tries to use the read to authorize a resume, and nothing is admitted (`CNI-X47`; `O02-03`).

**O02-X05.** On Windows, an agent's shell has edited a work record and recomputed its pin. The read shows the record, carrying `G4_unqualified` (`IF-20`; `O02-09`).

**O02-X06.** A crashed writer has left a committed revision whose staged record is not applied. That item is `stale`, and the list is `partial` (`O02-07.b`).

**O02-X07.** G3 is on the host, and an approval is pending only in G3's memory. The waiting list is `partial`, with `source_unavailable`, and never "none pending" (`O02-06.b`).

**O02-X08.** An approval's record is the G3 client's, per host and outside AEW's store. The waiting list is `partial`, with `source_unavailable`, the rendering names the G3 client's records, and nothing from them appears in the output (`O02-06.b`, `O02-04`).

**O02-X09.** The gateway fails and the operator revokes a grant. The reader is unaffected and admits nothing (`HEB-X18`; `O02-03`, `O02-02.d`).

**O02-X10.** The CLI channel is tested for its own semantics, not the website's (`IF-44`; `O02-Q03`).

**O02-X11.** An old snapshot holds a since-revoked entitlement. The case does not arise: the reader keeps no snapshot and no stored rights (`IF-40`; `O02-02.d`, `O02-05.a`).

**O02-X12.** A run's supervisor died while the operator was away. The runs read shows the invocation `historical`, and the run's last recorded status agent-reported and `stale` at its heartbeat's time. Nothing of its transcript or its tool-call log appears (`AEW-FR-29.c`; `O02-04.b`).

**O02-X13.** A pinned record's file is missing, or the control file itself is. The unit is shown from the control state, `stale`, with the record's fields `unavailable`, and the list is `partial`. Without the control file, the read is `unavailable`, and continuation-state answers `owner_unavailable` (`O02-07.a`, `O02-07.e`).

## Rulings

**O02-R01.** Entitlement comes from what the sandbox hides, not from a new principal.
- **The options rejected:**
  - a separate read account is not available on every host the operator uses;
  - a read socket needs a running service, which is what an outage takes away;
  - plain file access would make the operator's channel an agent's.
- **Where containment is not established,** the check is vacuous, and `O02-02.c` says why that costs nothing.

**O02-R02.** No stamp on this channel is current, and this departs from the design comparison. The comparison would have stamped a committed record `present_current`, with a renewal valid only at the read.
- **Why not:** a present-current conclusion derived from an owner carries that governing owner's qualified renewal
  (`AOI-04.a`). The reader is not the owner and issues none, and the `SourceStamp` schema admits `present_current`
  only as `qualified`.
- **On STG-01's three routes,** `OP-06` refuses a renewal valid only at the read too: a current stamp's `valid_until`
  is later than now, and within a maximum the owner records.
- **Precedent:** STG-02's slice stamps AEW's records as unqualified reports for the same reason
  (`src/aew/stg02/wire.py:102-110`).
- **Why `historical`, not the slice's `unknown`:** the reader knows when it read, and `AEW-FR-30.c` and `AEW-FR-29.d` ask
  for the time to show.
- **The operator's list stays empty:** the channel now claims less than the comparison had it claim.

**O02-R03.** There is one command, always available, with no outage mode. It is exercised every day, so it cannot rot unseen. It needs no outage detection, and it is tested against the same fixtures as any other D-01 channel (`AOI-12.b`).

**O02-R04.** The site is not an outage channel. Its server is one of the services that go down. Its cached page is its own, and `CNI-X38` binds what that page may imply.

**O02-R05.** Five more routes are `unsupported` than in the design comparison, each for a reason.
- **Knowledge:** `knowledge/` carries no pin, and Knowledge waits for K-01's own increment, after V-01
  (`00-governance/decisions/2026-10-25-operator-selection-before-I-7.md`). Lessons (`AS-16`) are read through archived
  work units, whose bundles the archive index pins.
  - Its `unsupported` answer carries a `journal_selection` that is `not_established`, as `ReadKnowledge` requires,
    which states that no qualified selection exists (`O02-08.b`, `K01-11`).
- **Hold recovery:** no AEV hold record is built, and its answer is a problem (`O02-R10`).
- **Coverage:** D-01's coverage `channel` has no value for this channel.

**O02-R06.** STG-20 was sent the waiting and attention rows on 2026-10-28, before this revision settled them. The mapping of records to items is the producer's, and this position adds only the outage stamps.
- **STG-20 answered on 2026-10-28,** correcting its earlier agreement that a G3 approval's record would be committed:
  - it has no objection to the split;
  - a G3 approval's record is per host, outside AEW's store, because G3 and its confirmer are per host and
    `aew g3 request` takes no project;
  - the Lead's open question is a committed store record, read under `O02-05.a`;
  - how an outage read answers an approval is this position's.
- **STG-20 offered two answers:** read the client's records lock-free, stamped `stale`, or name them unread. This
  position names them unread (`O02-06.b`): they carry no pin, and in an AEW outage G3's own confirmer still lists and
  notifies pending approvals, with no AEW service. STG-20 took that reading: the approval is never an item, and the
  result, not an item, carries `source_unavailable`.
- **Whether this meets `CNI-08.d`** together with the confirmer is STG-20's ruling, and this position cites it.
- **The expiry rule moved to the backlog** (`O02-B6`): nothing committed in STG-20 expires, and no committed O-01
  record was found that carries an expiry.

**O02-R07.** `S-DEC-03`'s open half, the "safe independent reader", is answered by `O02-02`: the operator's own uncontained process, reading the store lock-free, with no new principal.

**O02-R08.** The refusal is D-01's own `authentication_unqualified` problem, so no new refusal name is needed.
- D-01 fixes its `retry` to `reauthenticate`, which would misdirect a Lead or a worker. So `O02-02.e`'s fixed text, in
  `Problem.title`, says what to do instead. It is one text for every refused caller, so it reveals nothing.

**O02-R09.** The rendering names a source the reader did not read, because the wire cannot. `limitations` is a closed enum, and `collection_basis` is one stamp for the collection's own basis. Naming the source states the reader's own coverage, not a fact of the store, so `O02-01.c` permits it.
- **For the same reason,** an `unsupported` route's rendering says where its fact is read instead (`O02-08.c`).

**O02-R10.** Hold recovery answers `not_found_or_not_disclosable` (404, `retry` `never`), not `owner_unavailable` (503, `retry` `when_source_recovers`).
- **Its schema** needs exactly one item, so `unsupported` with none is not a valid body.
- **No AEV hold record is built,** so no hold id names one. A 404 is true, and it is D-01's answer for a hidden subject
  and a nonexistent one alike. A 503 would promise a recovery that no producer will make.
- **When AEV builds hold records,** this row is revised (`O02-B4`).

**O02-R11.** `O02-04` is widened to name what the runs and attention rows need, rather than dropping phase and the run anomalies from them.
- **Why:** in an outage, which runs were going and which were lost is what the operator most needs to know
  (`AEW-FR-29.b`). The posture favours showing it.
- **What keeps it safe:** the reader reads two named fields of a run's record, never its transcript, tool-call log,
  bridge key, requests or scratch (`O02-04`). The phase is labelled agent-reported, since the run can write its own
  harness state (`AEW-FR-29.c`, `AOI-09.b`).
- **How far D-01 shows it:** a run that is going reads `REPORTED_ACTIVE`; a lost one reads `UNKNOWN` with
  `POSSIBLE_STALL` and `progress_suspected`. A crashed run reads `REPORTED_FINISHED`, the same as one that ended with
  its evidence, because D-01's phase has no finer value, and the stale stamp's time says when it last reported.

**O02-R12.** Every disclosure names `aew:local-account` as the effective recipient, not the operator, and its form is `full` with `qualified_release` false.
- **The recipient:** no read qualifies the caller as the operator. `O02-02`'s check says only that the caller is
  outside AEW's sandbox, and where containment does not hold it says nothing (`O02-04.a`).
- **The form:** what is served is the committed record itself, so nothing inside the served subset is withheld. The
  release is not qualified, which `qualified_release` false says.

## Backlog

**O02-B1.** Qualified stamps on this channel, once an owner issues renewals for store records (`OP-04`, `OP-06`).

**O02-B2.** A coverage value for the outage channel. D-01's coverage `channel` enum has no value for it, and adding one changes D-01, which is the operator's.

**O02-B3.** Knowledge reads, with K-01's own increment.

**O02-B4.** Research claims, capabilities and AEV's hold recovery, once their records are built. Hold recovery's 404 answer is revised then (`O02-R10`).

**O02-B5.** Items for packages, assurance and resolve in the verifier, which builds every other served row's items. Until then, those three rows are the built reader's conformance (`O02-Q03`).

**O02-B6.** An expiry on a committed record of an operator need. Once such a record carries one (O-01's owner operations under `O02-11`, or STG-20's), a passed expiry reads `action_status` `no_qualified_response_path`.

## Not covered

- **Building the reader and recording G4:** the register's order, and the Lead's.
- **The site's cached display during an outage:** the site's own, under `CNI-X38`.
- **Recovery and repair:** U-01, and the store's writers.
- **Blocked-on-you's normal behaviour:** STG-20.
- **The human rendering's layout.**

## Changes

- **Revision 1 (2026-10-28):** the first text, written from the fact map and the design comparison. It departs from the
  comparison twice: currency (`O02-R02`), and five more routes `unsupported` (`O02-R05`). It follows STG-20's answer on
  G3 approvals, which are kept outside the store (`O02-R06`).
- **Revision 2 (2026-10-28):** the answers to round 1's 13 findings (`OUT1`), finding by finding in `CHANGES-r2.md`.
  - It adds `O02-02.e`, `O02-04.b`, `O02-05.e`, `O02-07.e`, `O02-08.b`, `O02-08.c`, the disclosure table, the
    scenarios `O02-X12` and `O02-X13`, and the rulings `O02-R10` to `O02-R12`.
  - It rewrites `O02-01.a`, `O02-01.c`, `O02-02.a`, `O02-02.b`, `O02-04`, `O02-04.a`, `O02-05`, `O02-07.a`, `O02-07.b`,
    `O02-08.a`, `O02-10` and the runs, attention, knowledge, continuation-state and hold-recovery rows.
  - Every rule ID of revision 1 keeps its meaning. `O02-06.b`, `O02-R06` and `O02-R09`, which STG-20 cites, gain only
    the notifier as a second source.
- **Revision 2.1 (2026-10-28):** the quick check's four items (`OUT2`), applied with no further check
  (`CHANGES-r2.1.md`): a failed pin in any item makes the result `partial` (`O02-07.b`, `O02-07.e`); a result that
  read nothing claims nothing committed (`O02-01.c`); the refusal names a writing command (`O02-02.e`); and a stopped
  heartbeat reads `POSSIBLE_STALL` (`O02-04.b`, `O02-R11`).
