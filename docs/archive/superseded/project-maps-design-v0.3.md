# T5 — Project maps: deterministic structural core and semantic extension model (v0.3)

- **Status:** **Design frozen — proposed for operator adoption**, 2026-10-04. This v0.3 preserves the deterministic structural core from v0.2 and makes the semantic-extension architecture explicit: language/build-specific enrichments augment the core map, never replace it, have independent capability/freshness/coverage contracts, and remain derived non-authoritative context.
- **Basis:** KC §8.2 (architecture map), §8.3 (codebase map: "derived and revision-bound"), §13 (freshness states); ADR-0008 and `engine/freshness.py` (source-bound records, `observed_paths`, CURRENT/STALE/UNKNOWN computed never written); `knowledge/discovery.py` (candidate rules at `aew init`); `knowledge/manifest.py` (`KNOWLEDGE_NAMES`, `architecture_map` and `codebase_map` default `null`); `knowledge/context.py` (packs carry no map); the knowledge drafts (capture §12 K0 "canonical reference", §10 K1 source classes) and `ADR-0013-knowledge-storage-placement-draft.md` (where a derived record lives).
- **Facts from the review not re-derived:** `aew init` writes `codebase_map: null`; nothing generates or refreshes a map; freshness exists only for discovery records and plan proposals; the M3 dogfood's Lead guessed seven scope globs because nothing told it where the code was (REVIEW §6.6 case).

## 1. Frozen decision

**Two maps, two mechanisms, neither an authority source.**

1. **Codebase map** — deterministic Engine output from one exact Git tree using a versioned static ruleset. It contains only repository-structural facts/candidates that the generator can reproduce without executing project code.
2. **Architecture map** — model/role-authored investigation evidence created through the existing non-mutating investigator path. It may contain bounded semantic interpretation, but every claim remains attributable to that investigation and its observed source paths.

The existing project manifest may point at the current codebase-map artifact and the selected architecture-map evidence record. A pointer means **"current project navigation reference"**, not "true", "accepted as fact", or "admitted reusable Knowledge".

Project maps do **not** enter the K0–K3 capture/admission ladder merely because they live under the project's knowledge namespace. The deterministic codebase map is a derived project artifact; the architecture map remains role-attested discovery/evidence. They are not default recall candidates and they do not receive `knowledge_disposition` semantics.

A stale/missing map never changes project authority, a workflow transition, dispatch legality, or source truth.

## 2. The codebase map record

`aew/codebase-map/v1`, YAML, stored as an immutable derived artifact under `.aew/knowledge/maps/`. The canonical filename/content address includes both the source tree identity and generator/ruleset identity so regenerating the same commit under a changed generator never overwrites an older artifact.

Required envelope:

```yaml
schema: aew/codebase-map/v1
source_revision: <commit>
source_tree: <git tree id>
generator:
  version: 1
  ruleset_sha256: ...
artifact_sha256: ...
limits:
  tracked_paths: {seen: ..., capped: false}
  metadata_bytes: {read: ..., capped: false}
sections: ...
```

The generator reads the **commit object**, not the mutable working tree/index: enumerate with `git ls-tree -r <H>` / object reads (or an equivalent Git-object API). `--commit H` therefore means exactly H even when the checkout has staged/unstaged changes.

Contents, all computed without executing project code:

| Section | Source at `source_revision` | Deterministic v1 rule |
|---|---|---|
| `directories` | tracked path list | bounded directory summary with tracked-file counts, recognized-language counts, and zero-or-more structural labels from a versioned rule table: `source`, `tests`, `docs`, `build`, `generated`, `vendor`, `config`, `ci`, `unknown` |
| `languages` | tracked path extensions | recognized extension counts/shares using the versioned extension table; unknown is explicit |
| `build_descriptors` | tracked filenames | **all** matching descriptors (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, `CMakeLists.txt`, `Makefile`, `build.gradle`, etc.) with their path; no claim that one is the repository's singular build system |
| `entry_point_candidates` | bounded static parsing of declared metadata plus conventional filenames | distinguish `declared` from `convention`; record evidence path; no semantic "main component" inference |
| `test_candidates` | tracked paths + bounded static parsing of recognized test-runner metadata | test locations/runners/possible command family as **proposal evidence only** for T10/check configuration; never writes policy |
| `generated_and_vendor` | tracked path/name rules and bounded parsing of `.gitattributes` at H | paths structurally likely to be generated/vendor; these are navigation/edit-avoidance hints, not write-deny policy |
| `semantic_prerequisites` | tracked filenames | compilation/type-analysis metadata such as `compile_commands.json`, `tsconfig.json`, `pyrightconfig.json`, `.clangd` |
| `limits_and_omissions` | generator | anything skipped because of path/file/byte caps, unsupported formats, parse failures or unknown extensions |

### 2.1 Deliberately excluded from the canonical revision-bound map

- **Untracked/ignored-but-present workspace content.** It is not part of commit H, may contain machine-local or sensitive material, and would make a supposedly revision-bound artifact checkout-dependent. If useful, `aew map show --workspace` may later display an ephemeral local overlay; it is never stored as the canonical map.
- **Python/import/dependency graph in v1.** AST import extraction is syntactically easy but repository module resolution, namespace packages, generated paths and configuration make the resulting graph easy to over-trust. The core map ships without it; F19 can evaluate a separately versioned graph extractor later.
- prose, inferred purpose, inferred ownership, call graphs, runtime behavior, or model-authored summaries.

All metadata file reads are size-bounded and parser failures are represented as omissions, not guessed results. Symlink blobs are treated as Git objects; generation does not follow repository symlinks into the host filesystem.

## 3. Freshness: tree-bound, computed, non-authoritative

The codebase map describes repository-wide structure, so its effective input is the tracked Git **tree**, including path additions/deletions/renames. A list of paths that existed when the map was generated is insufficient: it would miss a newly added tracked path outside that list.

Therefore codebase-map freshness is specialized but follows the same "computed, never written" principle:

```text
aew map generate [--commit H] [--expect-rev N]
    Generate the immutable codebase-map artifact for H.
    With project-state adoption, H must still be the authoritative head/tree at commit time;
    stale CAS/authority conditions refuse rather than moving the pointer to an old tree.

aew map show [--json]
    Show the manifest-selected map plus computed freshness, limits/omissions and stale diff summary.

aew map diff
    Generate/compare a fresh in-memory map against the selected artifact; no project-state write.

aew map architecture --from <evidence-id> [--expect-rev N]
    Select an existing accepted investigator discovery/evidence record as the current architecture reference.
    Selection does not certify its semantic claims.
```

`aew init` does **not** silently create/adopt the first map outside the T10 proposal/apply flow. Static map generation is safe enough to preview automatically, but the project pointer is created only as part of the attributable bootstrap apply (or later `aew map generate`). This keeps T5 consistent with T10's "proposal, review, apply" ownership model.

`aew doctor` reports `map: CURRENT | STALE | none` as INFO. Missing/stale maps are not launch errors.

## 5. Storage and history: derived artifact, not admitted Knowledge

The current project manifest already has `knowledge.codebase_map` / `knowledge.architecture_map` pointers. T5 uses those pointers but does **not** reinterpret them as K0 admission.

For the codebase map, the pointer records at minimum:

```yaml
codebase_map:
  path: .aew/knowledge/maps/<content-addressed-name>.yaml
  sha256: ...
  source_revision: ...
  source_tree: ...
  generator_version: 1
  ruleset_sha256: ...
```

The map file is immutable. Moving the pointer is an attributable project-state transaction and is visible in normal control/history/outbox records. Historical maps remain immutable artifacts addressable through the historical project revision/artifact hash; T5 does not require an ADR-0013 `reference`/Knowledge ID or `knowledge_disposition`.

This avoids two authority mistakes:

- a deterministic cache does not become a reusable semantic Knowledge claim merely because it is useful context;
- selecting an investigator-authored architecture reference does not launder role-attested prose into engine-observed fact.

If ADR-0013 later gains a generic derived-artifact history kind, T5 may index map artifacts through it, but that is storage/indexing convenience only and does not alter the above semantics.

## 6. The architecture map

An investigator Ticket (`--non-mutating --card investigator`) may produce an architecture-map candidate using a fixed template derived from KC §8.2: components, control/data boundaries, external services, cross-component flows, relevant contracts/ADRs, and explicit source paths/evidence for each bounded claim.

The output stays an ordinary sealed investigator discovery/evidence record. The Lead may select one record as the project's current architecture reference. Selection means **"use this attributable investigation as the current navigation reference"**, not "the Lead proved every statement true".

Its source class remains role-attested. A stale architecture reference is surfaced as a hint/candidate for a new investigation; AEW never auto-dispatches one solely because the pointer is stale.

No new architecture-map record kind, knowledge admission, or alternate acceptance path is introduced by T5.

## 7. Semantic map extensions: additive capability, not a new core

The v1 structural map answers:

```text
Where is the code?
How is the repository shaped?
What build/test/configuration artefacts exist?
Which paths are likely source/tests/docs/generated/vendor/config?
```

That core remains language-neutral, cheap, deterministic and broadly available.

Language/build-specific semantic understanding is an **extension layer**:

```text
map.structural                 required core
    +
map.semantic.c_cpp             optional extension
map.semantic.python            optional extension
map.semantic.typescript        optional extension
map.semantic.go                optional extension
...
```

An extension may enrich the current project map with semantic relationships, but it does not redefine the structural map, replace source truth, or become workflow authority.

### 7.1 Extension contract

Every semantic extension has its own versioned contract:

```yaml
extension:
  capability: map.semantic.c_cpp
  extractor_version: ...
  source_tree: ...
  inputs:
    - {kind: compile_database, sha256: ...}
    - {kind: toolchain_identity, value: ...}
    - {kind: build_configuration, sha256: ...}
  coverage:
    translation_units: {seen: ..., parsed: ..., failed: ...}
    symbols: complete|partial|unavailable
    include_graph: complete|partial|unavailable
    call_graph: complete|partial|unavailable
    macro_context: complete|bounded|unavailable
  limitations: [...]
  artifact_sha256: ...
```

Rules:

1. **Additive only.** If an extension is absent, unsupported, stale or failed, the structural map remains valid.
2. **Independent freshness.** Extension freshness is computed from the inputs that actually define its semantics, not inherited blindly from the structural map.
3. **Explicit coverage.** Partial extraction is represented as partial. Unsupported constructs, parse failures and omitted units are surfaced instead of silently appearing complete.
4. **No source replacement.** Semantic edges are derived navigation/context. Consequential claims still trace back to source/build evidence.
5. **No universal graph fiction.** Different languages may expose fundamentally different semantic structures and therefore different extension schemas.
6. **Capability-qualified serving.** Agents only receive extension output when the capability is available, current enough for the requested use, and selected by the context policy/evaluation.
7. **Versioned extractor identity.** Changing extractor semantics creates a new derived artefact even if the repository commit is unchanged.

### 7.2 C/C++ is the first semantic-extension priority

For AEW's expected codebase workload, the first semantic extension should be C/C++, not Python.

A useful C/C++ semantic map must reason from **translation/build context**, not only filenames or textual includes. Its effective identity is closer to:

```text
Git source tree
+ compile_commands.json / equivalent compilation database
+ compiler/toolchain identity
+ include paths
+ defines / target flags
+ relevant generated-header/build context
+ extractor version
```

The same Git tree compiled with materially different defines or include paths can describe a different effective program; therefore a C/C++ extension cannot claim freshness solely from `source_tree`.

The initial C/C++ extension should target, where compiler-quality tooling can support them:

- translation units;
- declarations/definitions and symbol identity;
- static versus external linkage;
- include/preprocessor relationships under the active compile command;
- type and function locations;
- resolvable caller/callee relationships;
- generated-header/build-context bindings;
- bounded macro/configuration context where it changes interpretation.

The extension must report which of these are complete, partial or unavailable.

AEW should **not implement its own C/C++ parser** for this purpose. The preferred substrate is compiler-quality tooling, e.g. Clang/LibTooling/clangd-compatible compilation-database semantics, with the exact tool/extractor identity recorded in the artefact.

### 7.3 Later language extensions

Python, TypeScript, Go and other languages can add their own semantic extractors when justified. They should model their own language/build semantics rather than being forced into the C/C++ schema.

Examples:

```text
map.semantic.python
  module/package resolution
  imports
  symbol references
  interpreter/config context

map.semantic.typescript
  tsconfig/project references
  module resolution
  symbols/references

map.semantic.go
  module/package graph
  build tags
  symbols/calls
```

These are examples, not commitments. Each extension must earn implementation complexity through an actual AEW use case and F19 evidence.

### 7.4 Storage and composition

Semantic extension artefacts are immutable derived artefacts associated with the structural map/source tree and their additional semantic inputs. They may be queried alongside the core map, but composition is explicit:

```text
structural map
    + zero or more current semantic-extension artefacts
    = effective navigation/context view
```

No combined artefact becomes a new authority source. Extension records are not automatically admitted into K0–K3 Knowledge, and extension availability never changes dispatch legality by itself.

## 8. Packs and context: interfaces now, serving policy after evaluation

T5 defines bounded **read/query interfaces**, not automatic context-serving policy.

Safe deterministic slices include:

- codebase directory rows intersecting a Ticket's already-authoritative scope globs;
- generated/vendor hints intersecting those paths;
- directory/test/build metadata for files in a reviewer diff;
- the selected map's freshness/limits metadata.

These slices may be used by F19 experiments because they are bounded by authority that already exists (Ticket scope/diff) and remain labelled derived navigation context.

Automatic full-map injection into Lead/worker packs, architecture-map injection, token budgets and role-specific serving remain evaluation questions. F19 should compare the map-assisted arm against the known M3 failure mode in which the Lead guessed scope globs. If no measurable benefit justifies context cost/complexity, the map remains an on-demand query surface.

## 9. Explicit non-goals

- Language-semantic graphs/import graphs in v1.
- Model-generated summaries in the deterministic map.
- Ownership maps and glossary generation.
- Any automatic policy/check-command application from map findings.
- Any dispatch gate based solely on codebase-map freshness.
- Treating project maps as K0/K1/K2/K3 Knowledge admission.
- Following untracked/symlinked repository content into the host filesystem.
- Full-pack serving policy before F19 evidence.
- A single universal semantic graph schema across languages.
- Making a language extension mandatory for core T5 functionality.
- Treating semantic-extension output as stronger evidence than the source/build inputs that produced it.

## 10. Frozen designer decisions

1. **First map at init:** T10 wins. `aew init` may generate a deterministic preview automatically, but adopting the project map pointer occurs only through the attributable bootstrap proposal/apply (or later explicit map generation). No consequential bootstrap state is silently added.
2. **No import graph in v1.** The core structural map already addresses the G3 scope-navigation failure with far less semantic risk. A graph extractor must earn its complexity in F19 and be separately versioned/qualified.
3. **Stale codebase map never blocks dispatch.** It is navigation only. Regenerate mechanically when useful. A separately bound architecture/discovery record may trigger ordinary input-freshness rules only when some workflow artifact explicitly declares it as a required semantic input.
4. **Freshness binds the whole Git tree.** Do not reuse ordinary `observed_paths` semantics for the deterministic repository-wide map; doing so misses newly added paths.
5. **Generate from Git objects, not the working tree/index.** `--commit H` must be reproducible regardless of staged/unstaged checkout state.
6. **Untracked/ignored workspace content is excluded from the canonical map.** A future local overlay may show it ephemerally.
7. **Maps are derived project context, not Knowledge admission.** The codebase map is an engine-derived immutable artifact; the architecture map is role-attested investigation evidence. Manifest selection does not promote either into semantic authority.
8. **Architecture selection is not truth certification.** It chooses the current attributable navigation reference and preserves source class/freshness.
9. **Serving stays measurable.** Bounded slices are allowed as F19 inputs; automatic/full-pack serving is adopted only if evaluation shows benefit.
10. **Generator limits are part of the record.** Large/monorepo inputs fail soft by explicit caps/omissions rather than silently truncating while appearing complete.
11. **Structural core + semantic extensions is the permanent composition model.** T5 core answers repository shape/location questions; language/build-specific semantics arrive as optional capabilities that enrich but never replace the core.
12. **C/C++ is semantic extension #1.** Its freshness/input identity includes compilation/build context and extractor/toolchain identity in addition to the Git tree.
13. **Compiler-quality C/C++ extraction only.** Do not build an AEW-specific parser or infer a call/include graph from regex/text scanning. Use compilation-database-aware tooling and expose coverage/limitations.
14. **Extension failure is local.** A failed/stale C/C++/Python/etc. extension degrades only that enrichment; it never invalidates the structural map or independently blocks dispatch.
15. **Language schemas may differ.** Do not force Python imports, C/C++ translation units, TypeScript project references and Go packages into one misleading universal graph model.

No further designer-level question blocks the bounded structural v1 implementation: deterministic Git-tree generator, immutable artifact + manifest pointer, current/stale query, diff, and architecture-reference selection. The semantic-extension interface is now part of the architecture, but the structural v1 does not wait on any language extension. C/C++ is the first planned semantic extractor and should be designed/implemented as its own capability when scheduled; pack policy and later language extensions remain evidence-driven.
