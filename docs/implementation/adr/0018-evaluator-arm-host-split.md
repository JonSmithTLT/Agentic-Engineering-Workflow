# ADR-0018 — Evaluator/arm-host split: one task released to a corpus-free arm host (F19, M4-H)

- **Status:** **Accepted** (lead developer, 2026-10-10), with the F19 M4-H instrument plan v5 that it records (CLEAR
  at its fifth independent review round, 2026-10-10). Built in that plan's slices: **S4 built** (2026-10-10, this ADR's
  slice): D1 to D9 as written, on the scripted arm, through the local stand-in transport. The preflight's checks (S5),
  the SSH transport and hypervisor (S6), the frozen validity classifier (S7) and the run supervisor (S8) land with
  their slices, each adding a dated amendment section here where it changes a decision. Number: the next free one on
  `main` when S4's pull request opened.
- **Resolves:** how the evaluation instrument keeps the held-out corpus off every host a model-controlled process
  runs on, while still running and scoring one preregistered cell end to end: the code split, the protocol between the
  two sides, the order of the release, the bundle and its integrity, the audit trail, and the shape of the run record.
- **Basis:** the designer's [held-out corpus isolation decision](../../design/decisions-2026-10-06-f19-held-out-corpus-isolation.md)
  of 2026-10-06 (ledger HOC; its §3 is the arm-host rule); [Q7 v0.3.1](../../design/q7-m4h-value-gate-experiment-v0.3.1.md)
  §8, §8.1, §9.2 (ledger VGX); the [evaluation component design v0.2](../../design/evaluation-component-design-v0.2.md)
  §2, §3, §5 (ledger EVC); the F19 M4-H instrument plan v5 (§2.1 to §2.3, §2.8, §4; slice S4), which is a working plan
  and not in this repository.
- **Nature:** evaluation tooling under `eval/aew_eval/`, never workflow authority. Nothing here changes AEW's product
  code, its control state or any gate.

## Context

The single-host runner (`runner.py`, F19 slices 2 and 3) builds a case's fixture, runs the arm and scores it in one
process on one host, and that host holds the hidden root. The held-out corpus decision requires instead that no
model-controlled process can read unreleased corpus material, satisfied for M4-H by keeping the corpus off the arm
hosts entirely: the evaluator keeps the corpus, the preregistration, the ledgers and the oracles, and releases only the
selected task at the trial's start. The runner as built refuses every held-out case for a model arm until that split
exists. M4-H also needs every step of a release on an audit trail, an attempt counted before any task leaves, and a
run record that describes the arm host it ran on, not the evaluator.

## Decision

### D1. Two sides, and the evaluator never runs an arm

The evaluator side is `campaign.py` (one released cell), `release.py` (the bundle, the run manifest and the release
ledger), the attempt ledger, the preregistration and `hidden.py`. The arm-host side is `armhost.py`, the agent the
evaluator reaches through one forced command (`python -I -m aew_eval.armhost`). They share only `transport.py` (the
frames and the bundle format), `fixture.py`, `arms.py`, `canonical.py` and `schemas.py`.

- **The campaign path never runs an arm.** `campaign.py` imports no arm runner and calls none (no `run`, `build`,
  `run_cell` or `arm_for`); the arm runs in the agent's process, in the agent's own directory.
- **The agent imports nothing that reads the corpus or the ledgers:** not `hidden`, `ledger`, `prereg`, `release`,
  `campaign`, `runner`, `raw` or `score_child`, and nothing of AEW's product package.
- **Deny by default.** A released cell runs the `scripted` arm only, refused before registration otherwise; the agent
  refuses any other kind too (`ARM_KIND_REFUSED`). The model arms are released only when the run supervisor (S8) and
  the `raw` arm under it (S9) exist.

### D2. The protocol: one bounded request and one bounded reply per call

- **The evaluator initiates every call;** the arm host runs no listener.
- **A frame** is one line of canonical JSON (`aew/m4h-armhost/v1`, at most 1 MiB), then exactly `payload_bytes` of
  payload and nothing after it: a tar for `release` and `collect`, nothing otherwise. Both sides parse strict JSON (no
  `NaN` or `Infinity`) and validate every frame against the schema before reading it. A JSON line over the bound, a
  payload over its bound or not the size it declares, bytes after the payload, and a reply for another verb are
  refused with stable codes (`REPLY_TOO_LARGE`, `PAYLOAD_TOO_LARGE`, `REPLY_MALFORMED`, `REQUEST_MALFORMED`). An
  `ok: false` reply for another verb (the agent refused a request it could not read) is `REQUEST_REFUSED`, with the
  agent's own code in its text only: a code the guest chooses never stands for one the evaluator classifies.
- **The verbs.** `hello` and `preflight` keep no state on the agent; the order of a release (a preflight before the
  release) is the evaluator's (D3). Per run, the agent keeps one directory, `runs/<experiment>/<name>/`, and enforces
  the rest (`OUT_OF_ORDER` otherwise): `release` once, `run` once after it, and `collect` after `run`. **`collect` is
  repeatable:** the first one keeps its bundle and reply, and a later one (after a reply lost in transit) returns the
  same bytes, so a lost reply never loses the deliverable (plan v5 §2.4, "Restart").
- **Every call is bounded** by its own timeout (`TIMEOUT`), and the reading side stops at its byte bound and says so.
- **Errors are typed:** a refused request is a reply with `ok: false` and `error: {code, message}`; a transport
  failure is a `TransferError` with its `code`. A reply the agent cannot encode is still answered, as a fixed
  `ARMHOST_ERROR` reply.

### D3. The release order: preflight, register, then release

1. **Refuse before anything is counted:** the frozen inputs, as the single-host runner checks them; the arm kind
   (D1); a case with an oracle must have the committed one on the evaluator; and a retry (D8).
2. **Preflight** the arm host, bound to the run id, the treatment hash, the base's content hash and the snapshot UUID;
   the reply must echo that binding. A preflight is **established** only when it says so **and** it carries checks
   that all passed; one that claims isolation without them is refused outright. **No task is released to a model arm,
   and no held-out case is released, on a preflight that is not established** (HOC-06, HOC-07, HOC-11): the refusal
   is appended to the release ledger with its reason, nothing is registered and nothing is released. The one
   exception is a `scripted` cell of a case that is not held out, where no model-controlled process exists to reach
   anything. Until S5 adds the arm-host rule's checks and the attestation, the agent establishes nothing, so only
   scripted cells of public and synthetic cases are released.
3. **Register** the attempt with a `release` block, `{host, snapshot_uuid, preflight_sha256, bundle_sha256}`, in the
   attempt line (`aew/eval-attempt/v1`), synced **before the bundle leaves**. `snapshot_uuid` is null for a host with
   no hypervisor snapshot (the local stand-in).
4. **Release** the bundle; the agent verifies it (D5) and answers with its hash, which must be the registered one.
5. **Run** the arm there. 6. **Collect** the final tree under hostile receive. 7. **Finalize** once (D7).

### D4. The run manifest, `aew/m4h-run-manifest/v1`

Interface I2 between F19 and M4-E: `seal_sha256`, `run_id`, `cell`, `task_input_sha256` (the SHA-256 of the released
task statement's bytes: UTF-8 with LF line ends, empty when the case has none), `caps` (`usd`, `wall_s`),
`treatment_sha256`, and the pre-grant bounds `max_publications` and `envelope_duration_s`. Nothing else: no oracle,
no other case, no preregistration content beyond the seal's hash. It travels in the release bundle as
`run-manifest.json` (its canonical bytes), and M4-E's `aew operator grant-publication --manifest` verifies its
SHA-256. The run record names that hash. S12 seals the values; S4 builds and validates the record.

### D5. Bundles, and hostile receive on both sides

- **A bundle** is a tar of regular files, and of links carried as data entries (their target text), with
  `MANIFEST.json` (`aew/m4h-bundle-manifest/v1`) listing every entry sorted by path: a file's SHA-256 and size, a
  link's target. The bundle's hash is the SHA-256 of the manifest's canonical bytes.
- **The release bundle** is built from typed inputs only: the case snapshot's starting files (`files/`), the task's
  bytes (`task.md`), the arm's frozen id, kind and configuration with the run id, the case id and whether it is seeded
  (`task.json`), and the run manifest. No preregistration, no case manifest (so no hidden commitment), no oracle, no
  other case.
- **The result bundle** is the final work tree under `tree/` and nothing else, read without git and never following
  a link: `.git` at the root is left out and a link is a data entry. Everything that is not collected is listed by path
  in the reply's `other` and never read: a FIFO, socket or device (`special`); a name another platform cannot hold,
  that is not valid UTF-8, or that differs from an earlier one only in case, and a link whose target is not valid
  UTF-8 (`unsafe-name`); a directory the agent cannot list (`unreadable`). Each path is carried escaped where it is not
  valid UTF-8, and the list is bounded by its serialized size (256 KiB, with paths over 1,024 characters and the rest
  counted in `other_omitted`), so the reply stays under its JSON bound whatever names the arm makes. The rest of the
  deliverable is always collected. The agent sizes each file before reading it.
- **Hostile receive** (both directions): a stream tar parser accepting only regular files, directories and link data
  entries (a hard link, device, FIFO or sparse file refuses the bundle, `ENTRY_TYPE_REFUSED`); relative, normalized,
  valid UTF-8 paths with no component over 255 bytes (`UNSAFE_PATH`), no duplicate, no name differing from another
  only in case and nothing under a file or a link (`PATH_CONFLICT`); each file written with `O_EXCL` (and `O_NOFOLLOW`
  where the platform has it) under a fresh directory, a write the host refuses being `WRITE_REFUSED`; a link recorded,
  never created; the bounds (64 MiB per file, 2 GiB in total, 200,000 entries, and the manifest within the per-file
  bound: `FILE_TOO_LARGE`, `TOTAL_TOO_LARGE`, `TOO_MANY_ENTRIES`, `MANIFEST_TOO_LARGE`) and a deadline
  (`RECEIVE_TIMEOUT`); the manifest recomputed from what arrived, compared byte for byte, and its hash compared with the
  one the sender recorded (`TRANSFER_CORRUPT`). A refusal removes what it wrote. The packer applies the same rules,
  the manifest's size and the tar's size on the wire included, so a sound packer never sends what the receiver refuses
  (`OVER_BOUNDS`). The evaluator also refuses a result bundle with any entry outside `tree/`
  (`UNEXPECTED_ENTRY`) or an `other` path that is also a received one (`OTHER_CONFLICT`).
- **The bounds are floors, and each side reads its own.** S12 seals the campaign's values, raised to the sealed
  deliverable bound plus the session databases' calibration maximum when that is larger. The evaluator passes them to
  its transport; the agent reads them from its host record (`--limits`, a root-owned file on an arm host, S17), never
  from a request.

### D6. The release ledger, `releases.jsonl`

Beside `attempts.jsonl`, one `aew/m4h-release-event/v1` line per protocol step: `preflight` or `preflight_refused`,
`registered`, `released`, `ran`, `collected` or `failed`, `finalized`. It is written with the attempt ledger's
durability (the same append function: one synced, newline-terminated line under the experiment's release lock, a torn
tail ignored by readers and truncated by the next append). Each line carries its sequence number and the SHA-256 of
the line before it (the first names the genesis hash of the schema id), so an edited, inserted or removed line breaks
the chain. The run record names the chain's head after its collection (`outcome.release.chain_sha256`). The trailing
lines, which no later line and no record names (a run's `finalized` event, a `preflight_refused` refusal), are
anchored twice: every append writes the new head to `releases.head` (replaced atomically and synced, under the same
lock), and `verify` cross-checks the attempt ledger (every attempt registered with a release has its `registered`
event, and every finalized one its `finalized` event naming the same result hash). `verify(heads, attempts)` reports
every break, a chain that does not end at its anchor, every named head no longer in the chain and every missing or
mismatched event. A crash between an append and its anchor leaves the anchor one line behind, which `verify` reports
for the operator to inspect.

### D7. The run record: `score_run`'s shape, the arm host's facts, and who attests each fact

- **Scoring is deferred and evaluator-side:** `outcome.scoring` is `{deferred: true, export, export_sha256,
  oracle_commitment}`, the export being the received tree on the evaluator (under the resolved collection root, so a
  linked or short-name root still scores), so `runner.score_run` scores a released run exactly as it scores a
  deferred single-host run.
- **The record describes the arm host:** `environment` is the agent's (platform, Python, process) with the host's
  name, `harness`, `started_at`, `ended_at` and `wall_s` are the agent's, and `outcome.safety.checkout_untouched` is
  null (the arm host holds no AEW checkout). `outcome.release` holds the registered release block, the run manifest's
  and the task's hashes and the chain head.
- **The arm host's own words are kept under their own keys.** Nothing the agent reports can stand in for a fact the
  evaluator records: its outcome is `outcome.arm_outcome` (a forged `scoring` block or host name stays the guest's
  claim), its error text `outcome.arm_error`, and the paths it did not read `outcome.unread_paths` (with
  `unread_paths_omitted`). `outcome.changed_paths` is the evaluator's, computed from the files and links it received;
  `outcome.error` is the evaluator's own text.
- **`outcome.attested_by`** labels each fact with who attests it (plan v5 §4). A fact's attester is that of its
  longest labelled path prefix, and every leaf of the record has one: the `evaluator` (the case, arm, assignment,
  profile, limits, release, changed paths, scoring, score, safety, validity and the record's own fields), the
  `guest_agent` (the environment except the host name, harness, times, base commit, arm outcome, arm error and unread
  paths) and `model_influenced` (the delivered tree). The snapshot UUID is the evaluator's own host record until S6
  checks it against the hypervisor; the `hypervisor` label is used from then.

### D8. Provisional validity verdicts, until the frozen classifier (S7)

Every failure after registration is a counted `invalid_measurement` with its reason code, never a vanished sample. The
code says which direction failed: a bare `TRANSFER_CORRUPT` only when the agent finds the evaluator's own release
bundle corrupt (or answers for another bundle); `RESULT_REFUSED:<code>` for anything wrong with what the arm host sends
back (a collect refusal by the agent, a reply or bundle the evaluator refuses, `TRANSFER_CORRUPT` included);
`ARMHOST_REFUSED:<code>` for another refused verb; `TRANSPORT_ERROR:<code>` for a call that failed (`TIMEOUT`,
`HOST_FAILED`, a malformed frame); `ARMHOST_ARM_ERROR` (the arm raised on the arm host); `EVALUATOR_ERROR:<type>`.
These are the instrument's own verdicts for the scripted arm. **A released run is never retried while they are
provisional:** `run_released_cell` refuses `retry_of` before anything is counted, so no failure an arm could cause
becomes a retry before S7's frozen, outcome-blind classifier decides which may (plan v5 §2.5: a retryable code needs a
fact no arm-uid process can produce or prevent). S7 replaces these verdicts before any model arm is released.

### D9. The local stand-in transport

`LocalTransport` runs the agent as a separate local process, rooted in its own directory, with an allow-listed
environment (nothing the evaluator holds, the hidden root above all, is inherited) and `CREATE_NO_WINDOW` on Windows:
the stand-in for S6's SSH transport in tests and on Windows CI, which run the whole release protocol through it. It
writes the agent's host record of its bounds and passes it with `--limits`, and reads the agent's standard error to
its end, keeping the last 64 KiB, so a chatty agent never blocks on a full pipe. `RecordingTransport` wraps another
transport and keeps every byte that crosses it, both ways, for the canary tests. S6's `SshTransport` implements the
same `exchange` with the plan's pinned SSH argv and generated configuration, and ends the request with the end of its
standard input, as the agent requires nothing after the payload.

## Build status

- **S4 (2026-10-10):** D1 to D9 on the scripted arm through `LocalTransport`; `tests/unit/test_eval_release.py`.
- **Not built:** S5 (the preflight's checks and the attestation, so the agent establishes nothing yet), S6 (SSH and
  the hypervisor), S7 (the classifier), S8 (the supervisor and the model arms), and the slices after them.

## Consequences

- No model arm runs on any released cell yet, and no held-out case is released: the single-host runner refuses held-out
  cases for a model arm, and a released cell refuses a model arm or a held-out case until S5's preflight can establish
  isolation and S8 can run a model arm. Scripted cells of public and synthetic cases can be released now, which is how
  the protocol is exercised before any paid run.
- The attempt ledger gains an optional `release` block; a record without it (the single-host runner) is unchanged, and
  so is `runner.py`'s behaviour.
- Every released run has a durable, verifiable trail of its steps, and its record names the head of that trail.
