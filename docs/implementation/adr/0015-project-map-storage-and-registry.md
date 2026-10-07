# ADR-0015 — Project-map storage, identity and the map registry

- **Status:** **Accepted** (lead developer, 2026-10-07), with the F22.1 plan that it records, after four independent plan reviews (v4 CLEAR); the plan review's answers to its questions 1 to 3 (placement under `local/`, Lead-authenticated selection, `git_oid` with `object_format`) are adopted here. Built by register F22.1's first pull request (the structural core, T5-A).
- **Resolves:** the implementation choices project maps v0.5 leaves open for the structural slice: where artifacts and the registry live, the artifact's byte identity, how a selection is made safe without `control_revision`, who may write, and the implementation reason codes.
- **Basis:** [project maps v0.5](../../design/project-maps-design-v0.5.md) §2.2, §2.4, §3.1 to §3.3, §16 T5-A, §17 (ledger PMP-03, PMP-07, PMP-08, PMP-27, PMP-74, PMP-75); the designer's [sequencing decision of 2026-10-06](../../design/decisions-2026-10-06-f22-1-structural-map-sequencing.md) (SMQ-01, SMQ-02); KC §5.3 (`.aew/local/` is rebuildable data); ADR-0001 (atomic replace, the lock); ADR-0005 (credentials).
- **Nature:** storage and identity for derived, non-authoritative state. Nothing here creates authority: a map never grants workflow, policy, Knowledge-admission, integration or publication authority (T5-INV-01), and none of this touches control state.

## Context

Design v0.5 names the artifact namespace "conceptually" `.aew/knowledge/maps/structural/<content-addressed-name>.yaml`, gives the registry a revision domain of its own (`map_revision`, never `control_revision`), and assigns background adoption to a closed `map_service` principal whose encoding waits for an amendment to ADR-0005 (PMP-32, register F22.2). The structural slice needs a synchronous path now, a byte identity that does not depend on a YAML emitter, and a selection that two writers cannot race. It must also not put derived bytes into the project's history: a committed artifact would change the very path listing it describes.

## Decision

### D1. Placement: `.aew/local/maps/`, and deleting it means "no selection"

Artifacts are `.aew/local/maps/structural/<artifact_sha256>.json`; the registry is `.aew/local/maps/registry.json`, its log `.aew/local/maps/registry-log.jsonl`, its lock `.aew/local/maps/registry.lock`. `.aew/local/` is AEW's git-ignored home for rebuildable data (`AEW_GITIGNORE`, KC §5.3). This is design v0.5's "project-map artifact namespace" placed under `local/`, not in `knowledge/`: a map is not Knowledge (§3.4) and is never committed. Deleting `local/maps/`, or any part of it, means "no map selected", which is always safe because a map grants nothing. The project manifest's map pointer stays `null`; the registry is the selection.

### D2. Identity: canonical JSON, with `git_oid` and `object_format`

`artifact_sha256` is the sha256 of the record's canonical JSON (sorted keys, `separators=(",", ":")`, ASCII, integers only) without `artifact_sha256`; the stored file is that canonical JSON with `artifact_sha256` added, so no YAML emitter is part of the identity. `aew map show` renders YAML for people. A reader recomputes the identity and compares the stored bytes with the canonical bytes; any difference is corruption (D7).

The record adds two fields to the design's envelope: `object_format` (`sha1` or `sha256`, the repository's object format) and, on each `inputs.metadata` entry, `git_oid` beside the design's `{path, sha256}`. Freshness compares blob ids at the requested commit, and the oid is what it compares. An entry the generator considered but did not read (over the 256 KiB per-blob cap, or after the 2 MiB total) carries `read: false` and a `reason` instead of `sha256` (the schema's `oneOf` keyed on `read`): the decision depended on that blob, so it is an input too.

Generator identity is `generator.name`, `generator.version` and `generator.ruleset_sha256` (the sha256 of the packaged rule table's bytes). A code change that alters output bytes must bump `version`; committed golden records enforce it.

### D3. The closed writer

`aew.maps.store` is the only code that writes under `local/maps/`: design v0.5 §3.2's `map.artifact.*` (artifacts) and `map.registry.*` (the registry and its log) families. Today the Lead's synchronous `aew map generate` calls it. F22.2's `map_service` will call the same functions under its own principal once ADR-0005's amendment encodes that principal. This reconciles §3.2's "adoption is committed through the same closed map-service path": the closed path is this writer, and what F22.2 adds is the principal in front of it. No background or asynchronous path exists until then.

### D4. Who may write

`aew map generate` (with or without `--select`) is Lead-authenticated: the current Lead's credential, verified against the control state it only reads. It is verified where the command writes, not only when it starts: before generation, again against the committed control state before the artifact is written, and again inside the registry's lock, after the compare-and-set's check and before anything of the selection is written. A handoff or takeover committed while the map was being generated therefore refuses both the artifact and the selection (`STALE_AUTHORITY`). A handoff or takeover committed after that last check is ordered after the selection, which it does not undo: a selection grants nothing (D1). In a Lead session it is Lead-reachable through the Lead broker. An invocation credential, a superseded Lead or no credential is refused. `aew map show` and `aew map diff` are reads open to any context. No `map` command takes `--expect-rev` or commits a control transition, and none is a dispatch entrypoint. The typed Lead surface (`aew.surface`) has no map tool in this slice.

### D5. The registry's revision domain: its own lock, an epoch and a compare-and-set

`aew/map-registry/v1` is `{schema, epoch, map_revision, selection_id, selected: {structural: {root, sha256, source_revision, source_tree, object_format, generator_version, ruleset_sha256}}}`; the architecture reference joins it in F22.1's second pull request.

- A selection takes the registry's own `FileLock`, never the control lock, and compares the caller's expectation `<epoch>:<map_revision>` (as `aew map show` prints it) with the registry's. Before any registry exists the expectation is `none:0`; the first selection creates the registry, with a random 64-bit `epoch`, under the lock. A registry recreated after deletion gets a new epoch, so an expectation from before the deletion never matches again (no ABA).
- A refusal is `STALE_REVISION` with `details.domain = "map_revision"` (and `expected` and `current`), so no client mistakes it for a `control_revision` conflict.
- The registry is replaced atomically. Nothing is written to control state, and `control_revision` never moves (T5-INV-11).

### D6. The log: attributable while it is retained

Each selection appends one line to `registry-log.jsonl`: `{epoch, map_revision, selection_id, previous_selection_id, capability, previous, new, actor: {kind, id, generation}, at}`, plus the nondeterminism report when one was overridden (D7). `selection_id` is random and new for every selection; the registry holds the id of the selection in effect, and `previous_selection_id` is the id the selection replaced (null for the first).

The line is written and synced before the registry is replaced, so the registry never holds a selection the log lacks. The reverse can happen: a crash or a failed registry write after the line leaves a line for a selection that did not take effect, and the next selection then logs the same `(epoch, map_revision)` again, because the registry never moved. The ids tell the lines apart. The selections that took effect form one chain: start at the line whose `selection_id` the registry holds, then follow `previous_selection_id` back. A line off that chain is one that never took effect. (PR #126 review, F2: the ADR first said such a line's `map_revision` was one the registry never reached, which is false.)

The log is not workflow history: it is not in the history manifest, it is not a transition, and like everything under `local/` it is rebuildable. Design v0.5 §3.3 asks only for attribution, and the log gives it for as long as it is kept.

### D7. Reason codes

- `MAP_CURRENTNESS_UNPROVEN` (design §17.2), with `details.reason`: `missing_object` (a needed object, or the tree, is not in the object database; the paths are named), `partial_clone` (a partial clone on git older than 2.44, which cannot be told not to fetch lazily), `unknown_commit`. Generation never produces a record from incomplete source. Freshness reports `UNKNOWN` with this code.
- `MAP_ARTIFACT_NONDETERMINISTIC` (design §17.2): regenerating the selected map's commit with the same generator identity gave another artifact. It is reported by `map generate`; `--select` is refused with it and the registry is left as it is, unless `--replace-nondeterministic` is given, in which case the log line records both artifacts. A report, never a lock-out.
- `MAP_ARTIFACT_CORRUPT` (implementation, under `INTEGRITY_ERROR`): a stored artifact no longer hashes to its name, is not its canonical bytes, or fails its schema; also an existing name holding different bytes on write.
- `MAP_REGISTRY_INVALID` (implementation, under `INTEGRITY_ERROR`): the registry is malformed. Deleting it clears the selection.

The strict reader (`aew map show --root`) raises these. Consumers use the never-raising reader, which returns `AVAILABLE` or `UNAVAILABLE` with a reason (`none`, `missing`, `corrupt`, `registry_invalid`, `unknown`), so a damaged map can never refuse or break anything that reads it.

### D8. Freshness is computed, never stored

Freshness against a commit is computed on read from Git objects (design §2.4) and cached in process memory only, keyed by the artifact, the requested tree and the generator identity. No reader writes anything that could relabel a map.

## Consequences and limits

- **Cold start (Q7).** `.aew/local/maps/` is persisted project state that survives between runs. The Q7 cold-start attestation must check it: empty, or recorded. This holds whatever the pack switch of F22.1's second pull request says.
- **Rebuildability.** A clone has no maps until `aew map generate` runs, and that is correct: nothing depends on a map.
- **Scale.** Generation starts a constant number of git processes (one batch reader for every blob) and is bounded by its caps; the record grows with the directory count up to its caps. No very-large-repository support is claimed beyond the measured 100,000 paths (design §2.5).
- **Not decided here:** the `map_service` principal (F22.2, with ADR-0005's amendment), semantic artifacts' root and chunk storage (T5-B), retention and garbage collection of unselected artifacts (T5-B), and any typed-surface map tool.
