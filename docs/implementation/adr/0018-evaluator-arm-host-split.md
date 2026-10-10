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
  payload: a tar for `release` and `collect`, nothing otherwise. Both sides validate every frame against the schema
  before reading it; a JSON line over the bound, a payload over its bound or not the size it declares, and a reply for
  another verb are refused with stable codes (`REPLY_TOO_LARGE`, `PAYLOAD_TOO_LARGE`, `REPLY_MALFORMED`).
- **The verbs,** each run once per run and in order (`OUT_OF_ORDER` otherwise): `hello`, `preflight`, `release`,
  `run`, `collect`. The agent keeps one directory per released run, `runs/<experiment>/<name>/`, and refuses a second
  release of a run.
- **Every call is bounded** by its own timeout (`TIMEOUT`), and the reading side stops at its byte bound and says so.
- **Errors are typed:** a refused request is a reply with `ok: false` and `error: {code, message}`; a transport
  failure is a `TransferError` with its `code`.

### D3. The release order: preflight, register, then release

1. **Refuse before anything is counted:** the frozen inputs, as the single-host runner checks them; the arm kind
   (D1); a case with an oracle must have the committed one on the evaluator.
2. **Preflight** the arm host, bound to the run id, the treatment hash, the base's content hash and the snapshot UUID;
   the reply must echo that binding. A **held-out case is never released on a preflight that is not established**
   (HOC-11): the refusal is appended to the release ledger with its reason, nothing is registered and nothing is
   released. Until S5 adds the arm-host rule's checks and the attestation, the agent establishes nothing, so only
   public and synthetic cases are released.
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
- **The result bundle** is the final work tree under `tree/`, read without git and never following a link: `.git` at
  the root is left out, a link is a data entry, and anything else that is not a regular file (a FIFO, a socket, a
  device) or whose name another platform cannot hold, or differs from an earlier one only in case, is listed by path in
  the reply's `other` and never read.
- **Hostile receive** (both directions): a stream tar parser accepting only regular files, directories and link data
  entries (a hard link, device or FIFO refuses the bundle, `ENTRY_TYPE_REFUSED`); relative, normalized paths only
  (`UNSAFE_PATH`), no duplicate, no name differing from another only in case and nothing under a file or a link
  (`PATH_CONFLICT`); each file written with `O_EXCL` (and `O_NOFOLLOW` where the platform has it) under a fresh
  directory; a link recorded, never created; the bounds (64 MiB per file, 2 GiB in total, 200,000 entries:
  `FILE_TOO_LARGE`, `TOTAL_TOO_LARGE`, `TOO_MANY_ENTRIES`) and a deadline (`RECEIVE_TIMEOUT`); the manifest recomputed
  from what arrived, compared byte for byte, and its hash compared with the one the sender recorded
  (`TRANSFER_CORRUPT`). A refusal removes what it wrote. The packer applies the same rules, so a sound packer never
  sends what the receiver refuses (`OVER_BOUNDS`).
- **The bounds are floors.** S12 seals the campaign's values, raised to the sealed deliverable bound plus the session
  databases' calibration maximum when that is larger.

### D6. The release ledger, `releases.jsonl`

Beside `attempts.jsonl`, one `aew/m4h-release-event/v1` line per protocol step: `preflight` or `preflight_refused`,
`registered`, `released`, `ran`, `collected` or `failed`, `finalized`. It is written with the attempt ledger's
durability (the same append function: one synced, newline-terminated line under the experiment's release lock, a torn
tail ignored by readers and truncated by the next append). Each line carries its sequence number and the SHA-256 of
the line before it (the first names the genesis hash of the schema id), so an edited, inserted or removed line breaks
the chain. The run record names the chain's head after its collection (`outcome.release.chain_sha256`), which also
catches a removed last line; `verify(heads)` reports every break and every named head no longer in the chain.

### D7. The run record: `score_run`'s shape, the arm host's facts, and who attests each fact

- **Scoring is deferred and evaluator-side:** `outcome.scoring` is `{deferred: true, export, export_sha256,
  oracle_commitment}`, the export being the received tree on the evaluator, so `runner.score_run` scores a released
  run exactly as it scores a deferred single-host run.
- **The record describes the arm host:** `environment` is the agent's (platform, Python, process) with the host's
  name, `harness`, `started_at`, `ended_at` and `wall_s` are the agent's, and `outcome.safety.checkout_untouched` is
  null (the arm host holds no AEW checkout). `outcome.release` holds the registered release block, the run manifest's
  and the task's hashes and the chain head.
- **The arm host's own outcome is kept under `outcome.arm_outcome`.** Nothing the agent reports can stand in for a
  fact the evaluator records: a forged `scoring` block or host name stays the guest's claim, under its own key.
- **`outcome.attested_by`** labels each fact with who attests it (plan v5 §4): the `evaluator` (the case, arm,
  assignment, release, changed paths, scoring and validity), the `guest_agent` (the environment, harness, times, base
  commit and arm outcome), the `hypervisor` (the snapshot UUID) and `model_influenced` (the delivered tree).

### D8. Provisional validity verdicts, until the frozen classifier (S7)

Every failure after registration is a counted `invalid_measurement` with its reason code, never a vanished sample:
`TRANSFER_CORRUPT`; `TRANSPORT_ERROR:<code>`; `ARMHOST_REFUSED:<code>`; `RESULT_REFUSED:<code>` (a hostile-receive
refusal other than the manifest); `ARMHOST_ARM_ERROR` (the arm raised on the arm host); `EVALUATOR_ERROR:<type>`.
These are the instrument's own verdicts for the scripted arm, where no model can produce any of them. S7's frozen,
outcome-blind classifier replaces them before any model arm is released (plan v5 §2.5: a retryable code needs a fact
no arm-uid process can produce or prevent).

### D9. The local stand-in transport

`LocalTransport` runs the agent as a separate local process, rooted in its own directory, with an allow-listed
environment (nothing the evaluator holds, the hidden root above all, is inherited) and `CREATE_NO_WINDOW` on Windows:
the stand-in for S6's SSH transport in tests and on Windows CI, which run the whole release protocol through it.
`RecordingTransport` wraps another transport and keeps every byte that crosses it, both ways, for the canary tests.
S6's `SshTransport` implements the same `exchange` with the plan's pinned SSH argv and generated configuration.

## Build status

- **S4 (2026-10-10):** D1 to D9 on the scripted arm through `LocalTransport`; `tests/unit/test_eval_release.py`.
- **Not built:** S5 (the preflight's checks and the attestation, so the agent establishes nothing yet), S6 (SSH and
  the hypervisor), S7 (the classifier), S8 (the supervisor and the model arms), and the slices after them.

## Consequences

- Held-out cases still cannot run on a model arm: the single-host runner refuses them, and a released cell refuses
  them until S5's preflight can establish isolation and S8 can run a model arm. Public and synthetic cases can be
  released now, which is how the protocol is exercised before any paid run.
- The attempt ledger gains an optional `release` block; a record without it (the single-host runner) is unchanged, and
  so is `runner.py`'s behaviour.
- Every released run has a durable, verifiable trail of its steps, and its record names the head of that trail.
