# T5 — Project maps: a deterministic codebase map with revision-bound freshness

- **Status:** bounded design note from the independent architecture review (thread T5 of `HANDOFF.md`; `REVIEW.md` G3, F-B), 2026-10-04. Not governing. Smaller than the handoff asked: it decides the generator, the record, freshness and the commands; it leaves pack sections and budgets to the evaluation the recall draft requires (K-arms) and lists them as questions.
- **Basis:** KC §8.2 (architecture map), §8.3 (codebase map: "derived and revision-bound"), §13 (freshness states); ADR-0008 and `engine/freshness.py` (source-bound records, `observed_paths`, CURRENT/STALE/UNKNOWN computed never written); `knowledge/discovery.py` (candidate rules at `aew init`); `knowledge/manifest.py` (`KNOWLEDGE_NAMES`, `architecture_map` and `codebase_map` default `null`); `knowledge/context.py` (packs carry no map); the knowledge drafts (capture §12 K0 "canonical reference", §10 K1 source classes) and `ADR-0013-knowledge-storage-placement-draft.md` (where a derived record lives).
- **Facts from the review not re-derived:** `aew init` writes `codebase_map: null`; nothing generates or refreshes a map; freshness exists only for discovery records and plan proposals; the M3 dogfood's Lead guessed seven scope globs because nothing told it where the code was (REVIEW §6.6 case).

## 1. Decision

**Two maps, two mechanisms.** The **codebase map** is derived deterministically by the engine from the repository at a commit, stored as an immutable record with that commit, and reported CURRENT or STALE by the same rule discovery records use. The **architecture map** is not derived: it is produced by an investigator Ticket (ADR-0008 non-mutating work) as a discovery record, accepted by the Lead, and pointed to by the manifest; its freshness is the discovery record's. Neither is authority (KC §7.4 "derived knowledge"); both are K0-class references in the drafts' terms.

## 2. The codebase map record

`aew/codebase-map/v1`, YAML, under `.aew/knowledge/maps/codebase-<commit12>.yaml`, immutable, pinned by SHA-256 from the manifest entry that points at it (`knowledge.codebase_map`). Contents, all computed without running project code:

| Section | Source | Deterministic rule |
|---|---|---|
| `source_revision` | `git rev-parse HEAD` of the authoritative branch | the commit it describes |
| `directories` | `git ls-files` top two levels | each directory with file count, dominant language (by extension table), and a role from a fixed rule table: `source`, `tests`, `docs`, `build`, `generated`, `vendor`, `config`, `ci`, `unknown` |
| `languages` | extension counts over tracked files | the top five with shares |
| `build_system` | presence of `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, `CMakeLists.txt`, `Makefile`, `build.gradle` | one or more detected systems with the file that proves it |
| `entry_points` | `pyproject` `[project.scripts]`, `package.json` `bin`/`main`, `main.go`, `src/main.rs`, `__main__.py`, `Program.cs` | the declared or conventional entry files |
| `test_locations` | directories named `test`, `tests`, `spec`, `__tests__`, files matching `test_*.py`, `*_test.go`, `*.spec.ts` | directories and the discovered test runner (`pytest.ini`/`pyproject [tool.pytest]`, `jest.config`, `go test`) **as a proposal for `policy/checks.yaml`, never written into it** |
| `generated_and_vendor` | `.gitattributes` `linguist-generated`, directories named `vendor`, `node_modules`, `dist`, `build`, `target`, `*_pb2.py`, `*.generated.*` | paths to avoid editing (KC §8.3 "generated/source directories to avoid editing") |
| `ignored_but_present` | `.gitignore` patterns that match existing directories | what a role will see on disk that is not source |
| `semantic_prerequisites` | `compile_commands.json`, `tsconfig.json`, `pyrightconfig.json`, `.clangd` | KC §8.3 "compilation databases" |
| `imports` (optional) | Python: `ast` over tracked `.py` files, module → imported modules (intra-repo only); TypeScript/Go: none in v1 | an intra-repository import graph when a stdlib parser exists; absent otherwise, and the record says so |
| `observed_paths` | the union of everything the sections read | the freshness scope (below) |

The record is a few KB for a repository like AEW's (about 20 k lines, 14 schemas, 78 test files); the import graph is the only part that grows with code size and is capped (at 500 nodes the record keeps the module list and drops edges, saying so).

**What it never contains:** prose, inferred purpose, ownership, or anything a model wrote. That is the architecture map's job and it goes through evidence.

## 3. Freshness, exactly as discovery records

`engine/freshness.py` already implements the rule: a source-bound record is CURRENT while `git diff --name-only <observed> <authoritative> -- <observed_paths>` is empty, STALE when it is not, UNKNOWN when the observed commit left the lineage. The codebase map joins `SOURCE_BOUND` with `declared_paths(record) = record["observed_paths"]`. A map whose `observed_paths` is the whole tracked tree goes STALE on any commit, which is correct and cheap to regenerate (the generator is a few hundred milliseconds of `git ls-files` and file reads). Freshness is computed at pack time and at `aew map show`, never written (ADR-0008).

A STALE map is still usable for navigation (KC §13: "may still use stale derived knowledge for navigation"); a pack carries it labelled `STALE since <commit>` with the changed paths' count, and a consequential claim about the code is re-verified against the source, which is what roles do anyway.

## 4. Commands

```text
aew map generate [--commit H] [--expect-rev N]   Lead: generate the codebase map at H (default: the authoritative head);
                                                 writes the record, points knowledge.codebase_map at it (manifest adopt
                                                 semantics: the manifest hash changes, so this is a Lead transaction)
aew map show [--json]                            the current map with its freshness; STALE shows changed paths
aew map diff                                     what changed between the current map and a fresh generation (no write)
aew map architecture --from <evidence id>        Lead: point knowledge.architecture_map at an accepted discovery record
```

`aew init` runs the generator once (read-only against the repository; the record is written with the manifest) so that `codebase_map` is no longer `null` on day one. `aew doctor` reports `map: CURRENT | STALE (n paths) | none` as INFO.

## 5. Storage: a knowledge record, in the ADR-0013 manifest

The map is derived, revision-bound, immutable per generation, and a reference, which is exactly ADR-0013's `reference` kind (K0): entry `{kind: reference, id: MAP-nnnn, version: 1, source: engine, links: {subject: ["repo"], revision: ["<commit>"]}}`, record under `knowledge/maps/`. Regeneration appends a new record and entry and moves the manifest pointer; old maps remain addressable (`aew history show MAP-0003`) for "what did the Lead see at the time". If ADR-0013 Q2 decides that K0 references are derived and never stored, the map is the counter-example: it is a computed artifact that must be pinned per commit, so it stays a stored record either way.

## 6. The architecture map

An investigator Ticket (`--non-mutating --card investigator`) with a fixed template in its launch contract: components, control and data boundaries, external services, cross-component flows, ownership, relevant contracts and ADRs (KC §8.2's list), each with the paths it is drawn from in `observed_paths`. The discovery record is sealed evidence (engine-owned bindings), the Lead ingests and accepts it, and `aew map architecture --from <E>` points the manifest at it. Its freshness is the discovery record's; a STALE architecture map is a candidate for a new investigator Ticket, surfaced by `status` as a hint, never automatically dispatched.

This is deliberately the existing ADR-0008 path with a template, not a new record kind: the knowledge drafts classify an investigator's prose as `ROLE_ATTESTED`, so it starts `explicit_investigation_only` for recall (capture §10) and enters packs only by the Lead's choice (`history load` or the manifest pointer), labelled as reference.

## 7. Packs: the part this note does not decide

Where the map goes in packs, how much of it, and for which roles, is the question the recall draft's context-budgeting rule (REVIEW §6.3: mandatory instructions, current work and authority, current evidence, then recall) and the K-arm evaluation exist to answer. What can be said now:

- The **implementer** pack's `scope` section can carry the map's `directories` rows that intersect the Ticket's scope globs (bounded by the scope, so no budget question), with `generated_and_vendor` flagged. That is the G3 case: scope globs with a map.
- The **reviewer** pack can carry the directory roles of the diff's paths (bounded by the diff).
- The **Lead** resume pack's item 9 ("relevant derived architecture/codebase knowledge", KC §15.1) is where the whole map or the architecture map belongs; the budget there is a Lead-pack question.
- A measurement comes first: the map's token cost against the dogfood's "guessed seven globs" failure class (REVIEW G3), in the F19 program (T2), as an arm.

## 8. Not built, not decided

- Language coverage beyond the extension table and the Python import graph.
- Ownership maps (KC §8.4) and the glossary (§8.5): different sources (CODEOWNERS, people), out of scope.
- Any model-generated summary of the codebase map; that is the architecture map's path.
- Pack budgets (§7).

## Questions for the designer

1. Should `aew init` generate the first map automatically (this note: yes, it is read-only and deterministic), or only propose it?
2. Is the Python import graph worth its size in v1, or should v1 ship without any graph and let the K-arm evaluation decide?
3. Does a STALE codebase map ever block a dispatch (as a STALE discovery input does, `INPUT_STALE`), or is it navigation only? This note: navigation only; a map is never a declared input.
