# T5 — Project maps: deterministic structural core, listing-bound freshness and the semantic-extension contract (v0.4)

- **Status:** **Proposed consolidation for the designer's freeze**, 2026-10-05. Not governing; v0.3 (design frozen, proposed, 2026-10-04) governs until the designer adopts this version. v0.4 changes v0.3 in exactly the ways the designer asked for when the research round closed (2026-10-05): the freshness rule narrows to what the probe showed the map depends on (§3), and the semantic-extension layer becomes a contract consolidated from the review's research notes (§6), with the C++ additions that the contract check required; the designer's decision of 2026-10-05 on where semantic artefacts are pinned (§4, decision 18) closes the one storage question the research left open. §0 lists every change; §9 keeps v0.3's fifteen decisions, one amended; §10 is what the research asks the designer to freeze; §11 is what stays open at the freeze.
- **Basis:** v0.3 (`docs/archive/superseded/project-maps-design-v0.3.md`); the T5 probe (`docs/archive/reviews/architecture-review-2026-10-04/t5-codebase-map-probe-results.md`: `ls-tree`, listing-bound freshness); the semantic research in `docs/research/`: the C extraction investigation (CXS), the C++ contract check (CXP), the semantic-extension framework S2 to S5 (SEF), the query-routing note §7 (QRC), the large-repository benchmark (LRB) and the project-understanding note §8 and §10 (PUI); KC §8.2 to §8.5 and §13; ADR-0008 and `engine/freshness.py`; ADR-0011 (derived indexes are locators, never vouchers); ADR-0012 (a scheduled extraction is a job with a receipt); ADR-0013 (where a derived record may be pinned).
- **Facts from the probes, not re-derived:** the structural map of AEW is 0.1 s and 3.5 KB and byte-identical across checkouts once it reads the commit's tree; a listing-plus-config rule would have kept it CURRENT through 21 of the last 30 commits instead of 0 of 30; at 100,000 files the generator takes 2.1 s and 162 KB with no sharding; libclang under the compile database reproduces the compiler's definitions, linkage and includes at 100% and direct call edges at 99.4 to 99.5%, with every discrepancy in named categories; fmt's C++ build emits 62,865 text symbols of which 59,972 are weak, and 59% of them have no AST definition cursor.

## 0. What changed from v0.3

| Where | v0.3 | v0.4 | Why |
|---|---|---|---|
| §3 freshness | binds the whole tracked tree: STALE on any commit (decision 4) | binds the **tree listing plus the configuration blobs the generator read**: STALE on an add, delete or rename, or a change to a file it read; CURRENT through content-only commits | the map depends on names and on two or three metadata files, not on every file's content; measured 21 of 30 recent commits CURRENT instead of 0 (T5 probe §3). Designer, 2026-10-05: the evidence supports the change; v0.3 governs until this version is adopted |
| §2 record | `directories` a bounded summary | the bound is stated: two levels plus a per-top-level summary | at 100,000 files the record grows with directory count (750 leaves: 162 KB); the cap keeps it in tens of KB at any size (LRB §1) |
| §2 record | the generator reads the commit object | unchanged, plus a conformance test: the map of a commit does not depend on the branch checked out | `ls-files` produced different maps of the same commit in two checkouts (T5 probe §3) |
| §6.1 contract | a per-extension capability, inputs, coverage and limitations envelope | the shared contract: fact kinds with tiers, the unit as the translation unit, per-unit input sets and freshness, mandatory toolchain identity, two coverages, deduplicated identity, generated limitations, and the C++ additions (`instances[]`, `dependent`, `virtual`, `overrides`, `source: codegen`) | S2 shaped it from C and S1b checked it against C++ with no language-specific hack (SEF, CXP §4) |
| §6.2 C/C++ first | priority and substrate | plus what the probes established: the three tiers and the exact boundary, the oracle, the codegen-adjacent edge extractor C++ needs | CXS §2, §3; CXP §3 |
| §4, §6.4 pinning | (implicit) | semantic artefacts are pinned per extension by the project-map manifest beside the structural map, never as ADR-0013 `reference` records | the framework note drifted toward a K0 `reference`; a compiler-derived call or index artifact must not become K0 because the history manifest is a convenient integrity mechanism (designer, 2026-10-05) |
| §6.4 storage | immutable derived artefacts, explicit composition | plus the derived rebuildable index and the scheduled first extraction | LRB §2, §3 |
| §6.5 query surface | (packs §8 only) | the typed `map.*` surface, radius 1 free and radius 2 budgeted, the boundary sentence, disclosure levels | SEF S3; QRC §7; designer 2026-10-05 (PUI §10, decision 2) |
| §6.6 incremental freshness | (extension freshness "from its inputs") | per-unit invalidation scopes, the dependency index first, atomic publication | SEF S4 |
| §6.7 architecture bridge | (none) | the investigator synthesizes over named `map.*` evidence | SEF S5 |
| §7.1 sibling indexes | (none) | the test index, public-surface counts and the constraint locator index as derived siblings, never structural fields | PUI §8, as corrected by the designer |
| §9 decisions | fifteen | fifteen, decision 4 amended; new decisions from the designer's 2026-10-05 round (radius; research capped) | this consolidation |
| §10, §11 | (none) | what the research asks the designer to freeze; what stays open | the freeze is the designer's act |

Nothing in §1, §4, §5, §8 changed in substance.

## 1. Frozen decision

**Two maps, two mechanisms, neither an authority source.**

1. **Codebase map** — deterministic Engine output from one exact Git tree using a versioned static ruleset. It contains only repository-structural facts and candidates that the generator can reproduce without executing project code.
2. **Architecture map** — model- or role-authored investigation evidence created through the existing non-mutating investigator path. It may contain bounded semantic interpretation, but every claim remains attributable to that investigation and its observed source paths.

The project manifest may point at the current codebase-map artifact and the selected architecture-map evidence record. A pointer means **"current project navigation reference"**, not "true", "accepted as fact" or "admitted reusable Knowledge".

Project maps do **not** enter the K0 to K3 capture and admission ladder because they live under the project's knowledge namespace. The deterministic codebase map is a derived project artifact; the architecture map remains role-attested discovery evidence. They are not default recall candidates and they receive no `knowledge_disposition` semantics.

A stale or missing map never changes project authority, a workflow transition, dispatch legality or source truth.

## 2. The codebase map record

`aew/codebase-map/v1`, YAML, stored as an immutable derived artifact under `.aew/knowledge/maps/`. The canonical filename and content address include both the source-tree identity and the generator and ruleset identity, so regenerating the same commit under a changed generator never overwrites an older artifact.

Required envelope:

```yaml
schema: aew/codebase-map/v1
source_revision: <commit>
source_tree: <git tree id>
generator:
  version: 1
  ruleset_sha256: ...
observed:                       # what freshness binds (§3)
  listing: <git tree id>        # the tracked path listing, as the tree id
  blobs: [{path, sha256}, ...]  # the configuration files the generator read
artifact_sha256: ...
limits:
  tracked_paths: {seen: ..., capped: false}
  metadata_bytes: {read: ..., capped: false}
  directories: {depth: 2, listed: ..., summarized: ...}
sections: ...
```

The generator reads the **commit object**, not the mutable working tree or index: it enumerates with `git ls-tree -r <H>` and object reads (or an equivalent Git-object API). `--commit H` therefore means exactly H even when the checkout has staged or unstaged changes, and the map can be generated for the authoritative commit while a role's workspace is checked out elsewhere. A conformance test asserts that the map of a commit does not depend on the branch checked out: the probe's first run used `ls-files` and produced 809 files in one checkout and 930 in another for the same commit.

Contents, all computed without executing project code:

| Section | Source at `source_revision` | Deterministic v1 rule |
|---|---|---|
| `directories` | tracked path list | bounded directory summary with tracked-file counts, recognized-language counts and zero or more structural labels from a versioned rule table (`source`, `tests`, `docs`, `build`, `generated`, `vendor`, `config`, `ci`, `unknown`); **two levels listed, deeper levels summarized per top-level directory**, so the record stays in tens of KB whatever the repository's size |
| `languages` | tracked path extensions | recognized extension counts and shares using the versioned extension table; unknown is explicit |
| `build_descriptors` | tracked filenames | **all** matching descriptors (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, `CMakeLists.txt`, `Makefile`, `build.gradle`, …) with their path; no claim that one is the repository's singular build system |
| `entry_point_candidates` | bounded static parsing of declared metadata plus conventional filenames | `declared` distinguished from `convention`; the evidence path recorded; no semantic "main component" inference |
| `test_candidates` | tracked paths plus bounded static parsing of recognized test-runner metadata | test locations, runners and a possible command family as **proposal evidence only** for T10 and check configuration; never writes policy |
| `generated_and_vendor` | tracked path and name rules and bounded parsing of `.gitattributes` at H | paths structurally likely to be generated or vendored; navigation and edit-avoidance hints, not write-deny policy |
| `semantic_prerequisites` | tracked filenames | compilation and type-analysis metadata such as `compile_commands.json`, `tsconfig.json`, `pyrightconfig.json`, `.clangd`: what a semantic extension (§6) could be built from |
| `limits_and_omissions` | generator | anything skipped because of path, file or byte caps, unsupported formats, parse failures or unknown extensions |

The fixed role table is the weak section by design: on AEW it labels two of seven top-level directories `unknown`, on the SPT repository eight of thirteen. That is the honest output of a table that never guesses, and it is what KC §8.3 asks for; what `rules/` or `queries/` are is the architecture map's job (§5). The table may widen (`examples`, `images`, `data`, `assets`, `requirements`) when the labels are argued, as a new ruleset version.

### 2.1 Deliberately excluded from the canonical revision-bound map

- **Untracked or ignored-but-present workspace content.** It is not part of commit H, may contain machine-local or sensitive material, and cannot be computed from Git objects. If useful, `aew map show --workspace` may later display an ephemeral local overlay for the role's workspace, labelled as such; it is never stored as the canonical map.
- **The Python import or dependency graph in v1.** It is the whole cost of the probe's generator (six times the time, eight times the bytes) and the easiest part to over-trust. The core map ships without it; a module graph is a semantic extension (§6.3) with its own identity, which F19 evaluates on its own merit. The probe shows it can be added without touching the rest of the generator.
- Prose, inferred purpose, inferred ownership, call graphs, runtime behaviour or model-authored summaries.

All metadata file reads are size-bounded and parser failures are represented as omissions, not guessed results. Symlink blobs are treated as Git objects; generation does not follow repository symlinks into the host filesystem.

## 3. Freshness: listing-bound, computed, non-authoritative

The codebase map describes repository-wide structure without reading most files' contents. Its effective input is therefore two things, and freshness binds exactly those (amended decision 4):

1. **the tracked path listing** at `source_revision`: names, which change only when a path is added, deleted or renamed;
2. **the configuration blobs the generator read**: the build descriptors, test-runner metadata and `.gitattributes` it parsed, recorded as `observed.blobs` with their digests.

The map is **STALE** when `git diff --name-status --diff-filter=ADR <observed tree> <authoritative tree>` is non-empty, or when any blob in `observed.blobs` differs at the authoritative tree; **CURRENT** otherwise; **UNKNOWN** when the authoritative tree cannot be read. Freshness is computed on read and never written, as ADR-0008 has it for discovery records; the computation is one change-proportional Git diff (18 ms at 100,000 files) plus a handful of blob comparisons.

Why not the whole tree: of the last 30 commits on `main`, 9 changed the listing and 21 changed contents only, so a whole-tree rule reported every map STALE while a listing-plus-config rule would have kept it CURRENT through 21 of them. STALE is rarer and therefore means something when it appears. Why not ordinary `observed_paths`: a list of the paths that existed at generation misses a newly added path; the listing marker is what catches additions. A semantic extension that reads file contents (a module graph, a C extractor) binds those contents through its own per-unit input sets (§6.6), never through this rule.

```text
aew map generate [--commit H] [--expect-rev N]
    Generate the immutable codebase-map artifact for H.
    With project-state adoption, H must still be the authoritative head at commit time;
    stale CAS or authority conditions refuse rather than moving the pointer to an old tree.

aew map show [--json]
    Show the manifest-selected map plus computed freshness, limits and omissions, and the stale diff summary
    (the added, deleted and renamed paths, and the changed blobs).

aew map diff
    Generate and compare a fresh in-memory map against the selected artifact; no project-state write.

aew map architecture --from <evidence-id> [--expect-rev N]
    Select an existing accepted investigator discovery or evidence record as the current architecture reference.
    Selection does not certify its semantic claims.
```

`aew init` does **not** silently create or adopt the first map outside the T10 proposal-and-apply flow. Static map generation is safe enough to preview automatically (0.1 s, no code executed, no working-tree reads), but the project pointer is created only as part of the attributable bootstrap apply or a later `aew map generate`. `aew doctor` reports `map: CURRENT | STALE | none` as INFO; a missing or stale map is never a launch error.

## 4. Storage and history: derived artifact, not admitted Knowledge

The project manifest's `knowledge.codebase_map` and `knowledge.architecture_map` pointers are used, not reinterpreted as K0 admission.

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

The map file is immutable. Moving the pointer is an attributable project-state transaction, visible in control, history and the outbox. Historical maps remain immutable artifacts addressable through the historical project revision and artifact hash; T5 requires no ADR-0013 `reference` id and no `knowledge_disposition`.

Semantic artefacts (§6) are pinned by the same mechanism, one pointer per extension, never as ADR-0013 `reference` records (designer, 2026-10-05): ADR-0013 gives `reference` the K0 meaning of a durable reusable Knowledge identity, and a compiler-derived call or index artifact must not become K0 because the history manifest is a convenient integrity mechanism. The layout and the manifest, conceptually:

```text
.aew/knowledge/maps/
    structural/<content-addressed artifact>
    semantic/c/<content-addressed artifact>
    semantic/cpp/<content-addressed artifact>
    semantic/python/<...>
```

```yaml
semantic_maps:
  c_cpp:
    path: .aew/knowledge/maps/semantic/<extension>/<content-addressed-name>.yaml
    sha256: ...
    source_revision: ...
    extractor_identity: ...
    configuration_set_digest: ...
    input_set_digest: ...
```

A pointer means "the semantic extension currently selected for this project and capability": not admission, not truth, no knowledge-disposition lifecycle. Each extension has its own pointer, never one monolithic `semantic_map`, because extensions have independent freshness, coverage, extractor identities and failure domains (decisions 14 and 15), even where C and C++ share one extractor implementation. A semantic artifact is a reproducible cache: its identity binds source revision, configuration set, extractor and toolchain identity, input-set digest and artifact hash, so it can be regenerated from them and needs none of the lifecycle semantics of Cases, Lessons or dispositions. If an audited record that artifact X was selected at project revision Y is wanted, a normal control or history event records the selection; that still does not make X Knowledge.

This avoids two authority mistakes: a deterministic cache does not become a reusable semantic Knowledge claim because it is useful context; and selecting an investigator-authored architecture reference does not launder role-attested prose into engine-observed fact. If ADR-0013 later gains a generic derived-artifact history kind, map artifacts may be indexed through it as storage convenience only.

## 5. The architecture map

An investigator Ticket (`--non-mutating --card investigator`) may produce an architecture-map candidate using a fixed template derived from KC §8.2: components, control and data boundaries, external services, cross-component flows, relevant contracts and ADRs, and explicit source paths or evidence for each bounded claim. With a semantic extension present, the investigator synthesizes over named `map.*` evidence instead of rediscovering the repository by search (§6.7).

The output stays an ordinary sealed investigator discovery or evidence record. The Lead may select one record as the project's current architecture reference. Selection means **"use this attributable investigation as the current navigation reference"**, not "the Lead proved every statement true". Its source class remains role-attested; a stale architecture reference is surfaced as a hint for a new investigation, never auto-dispatched.

No new architecture-map record kind, knowledge admission or alternate acceptance path is introduced by T5.

## 6. Semantic map extensions: additive capability, not a new core

The v1 structural map answers: where is the code, how is the repository shaped, what build, test and configuration artefacts exist, which paths are likely source, tests, docs, generated, vendor or config. That core remains language-neutral, cheap, deterministic and broadly available.

Language- and build-specific semantic understanding is an **extension layer**:

```text
map.structural                 required core
    +
map.semantic.c_cpp             optional extension
map.semantic.python            optional extension
map.semantic.typescript        optional extension
...
```

An extension enriches the current project map with semantic facts; it does not redefine the structural map, replace source truth or become workflow authority. The rules every extension obeys are the contract below; the measured C and C++ runs are what shaped it.

### 6.1 The semantic-extension contract

Consolidated from S2 (shaped by C) and S1b (checked against C++ with no language-specific hack). Shared means every extension, in every language, does this; language-specific means the extension declares it.

**Facts, with tiers.** An extension emits facts of a closed, shared vocabulary, each carrying a tier:

```text
tier: compiler_known | static_inference | unsupported

symbol        identity, kind, name, declared_at[], defined_at[], linkage or visibility, type_text,
              instances[] = {mangled, units[]}          (realizations of a template or inline definition; empty for C)
containment   symbol belongs to unit; unit belongs to module, file or package
reference     from, to, kind, site, tier, with kind one of:
              calls | calls_through | holds_pointer_to | imports | includes | uses_type | expands_macro
              | dependent | virtual | overrides
configuration unit: defines, flags, features, generated inputs
quality       unit: parse_status ok | partial | failed, diagnostics
coverage      symbol, run_id, executed, counts                  (optional overlay, bound to a run)
```

Each fact names its `source: ast | codegen`; facts with no source range (implicitly defined members, vtables, instantiations) are `codegen`. Language-specific: *which* kinds a language fills and at which tier. C fills `symbol`, `containment`, every `reference` kind but `imports`, `dependent`, `virtual` and `overrides`, `configuration` and `quality` at `compiler_known`, with `calls` to the `memcpy` class declared `static_inference` (codegen-variable). C++ adds `dependent` (a call on a dependent name inside a template body, resolved per instantiation), `virtual` (the interface is known, the implementation is a vtable lookup: the analogue of C's `holds_pointer_to` plus `calls_through`) and `overrides` (compiler-known). Python fills `symbol`, `containment` and `reference.imports` at `compiler_known` and nothing about calls or types without a type checker, which would be a second extension at `static_inference`. The matrix is data, so an answer can say "no call facts for this language" instead of returning an empty list that reads as "no callers".

**The unit is the translation unit, not the file.** 169 curl source files are 434 compilation-database entries, each with its own defines; curl without TLS is a different program from curl with it. Facts are keyed by `(unit_id, symbol_id)` where `unit_id` hashes the unit's identity (source path, compile command, toolchain); a file is a *view* over its units. Python's unit is the module; Rust's would be the crate.

**Input set, per unit.** Every extension names each unit's input set, because freshness (§6.6) is computed from it: the unit's source, the files it transitively reads, its configuration (flags, defines, features), its generated inputs, and the toolchain identity. C's is the `clang-scan-deps` set (median 141 files per unit) plus the compile command; Python's is the file alone.

**Extractor identity, with the toolchain mandatory.** `extractor: {name, version, toolchain: {tool, version, gcc_toolchain | sysroot, resource_dir_sha256}, options}` on every artifact, derived from the compiler, not configured by hand: libclang's driver selecting GCC 8's standard library while the build used GCC 15's produced a 50% include disagreement until the toolchain was aligned. Facts from two extractor identities are never merged into one record; a new identity produces a new artifact version and the old one stays readable.

**Freshness, per unit.** CURRENT, STALE and UNKNOWN as `engine/freshness.py` has them, plus **PARTIAL** for a unit whose last extraction had errors. The artifact's freshness is the worst of its units' plus the count of stale units, never one flag (§6.6).

**Two coverages, kept apart.** *Extraction coverage*: of the units the build names, how many were extracted and at what quality ("433 of 434 library units; 1 failed, 0 partial"), so every answer can be qualified. *Execution coverage*: which symbols a recorded run executed (`llvm-cov`: 108 of 163 zlib functions), an optional overlay bound to a run, joined by symbol identity, never a property of the static map.

**Artifact identity and deduplication.** One immutable, content-addressed artifact per (revision, extractor identity, configuration set), carrying `source_revision`, the extractor identity, the configuration identities it covers and its input-set digest. Deduplication is the artifact, not an optimization: per-unit dumps of curl's library are 134 MB for 3,866 distinct symbols, and C++ repeats each header-defined symbol in every including unit. Symbols are stored once by stable identity (USR for C and C++, the module-qualified name for Python), with per-unit membership and edges by identity.

**Limitations, generated.** A limitations block in the artifact, echoed in every answer, generated from the capability matrix and the quality facts, never hand-written: "direct callers complete; address-taken holders listed; calls through pointers not resolved; `memcpy`-class edges codegen-variable; 1 unit failed to parse".

**Extensions add facts, never queries.** The shared query surface (§6.5) answers over the shared fact kinds; a kind an extension cannot fill makes the answer say so for that language.

**Language-specific by design, and nothing else:** the extractor; the unit definition; the input-set computation; the symbol identity scheme; which `reference.kind`s exist; the tier exceptions.

The candidate record shape:

```yaml
schema: aew/semantic-map/v1
source_revision: <commit>
extractor: {name: cxx-libclang, version: 0.1,
            toolchain: {tool: clang, version: 21.1.8, gcc_toolchain: /usr, resource_dir_sha256: …}}
configurations:            # one per distinct compile-command shape
  - {id: cfg-a1b2, defines: [...], flags_sha256: …, generated_inputs: [{path, sha256}]}
units:                     # translation units or modules
  - {id: u-…, file: lib/altsvc.c, configuration: cfg-a1b2, inputs_sha256: …, quality: ok, diagnostics: 0}
symbols:                   # deduplicated by identity
  - {id: "c:@F@Curl_altsvc_parse", name: Curl_altsvc_parse, kind: function, linkage: external,
     defined_at: [{unit: u-…, file: lib/altsvc.c, line: 487}], declared_at: [...], type: "...", instances: []}
references:
  - {from: "c:@F@Curl_altsvc_parse", to: "c:@F@Curl_dyn_add", kind: calls, tier: compiler_known, sites: [{unit, line}]}
  - {from: "c:@F@cf_socket_active", to: "c:@F@memcpy", kind: calls, tier: static_inference, note: codegen-variable}
  - {from: "c:@Curl_cft_http_proxy", to: "c:@F@Curl_cf_def_cntrl", kind: holds_pointer_to, tier: compiler_known, sites: [...]}
  - {from: "c:@F@Curl_conn_cf_cntrl", to: null, kind: calls_through, through: "field do_cntrl", tier: compiler_known}
capabilities: {calls: compiler_known, calls_through: compiler_known, holds_pointer_to: compiler_known, imports: n/a, ...}
limitations: ["…generated from capabilities and quality…"]
coverage_overlays: []      # optional, by run
```

### 6.2 C/C++ is the first semantic extension, and what the probes established

For AEW's expected workload the first semantic extension is C/C++, not Python. Its effective identity is the Git tree plus the compilation database, the toolchain identity, include paths, defines, generated-header context and the extractor version; the same tree compiled with materially different defines describes a different program, so a C/C++ extension never claims freshness from `source_tree` alone.

**The boundary, measured.** Parsing each translation unit with its own compile command through libclang reproduces the compiler's facts: 100% of function definitions and their linkage (338 of 338 on zlib; 1,680 of 1,685 on curl's library, the five extras unused statics the compiler did not emit), 100% of the preprocessor's include set, 99.4 to 99.5% of direct call edges. Every discrepancy falls in a named category: compiler-synthesized calls (a struct copy becomes `memcpy`), builtin-recognized libc calls inlined at `-O0`, constant-folded branches, asm-label renames (`fopen` → `fopen64`, which the AST does know through `mangled_name`), unused statics, indirect calls (the site is known, the target is not), dispatch tables in global initializers (where C's indirection lives: 754 references in curl's library, invisible to a body-only walk, recovered as `holds_pointer_to`), macro-mediated calls, and configuration (`#if` branches not taken under this build's defines are not in the AST at all). The three tiers of §6.1 are these categories made general.

**The oracle is the build.** A C extractor's acceptance test is the objects the build already produced: `llvm-nm` for definitions and linkage, `llvm-objdump -d -r` at `-O0` for direct call edges, `clang -M` for includes, `clang -dM -E` for macros. The extractor ships with this oracle, not with hand-written expectations.

**C++ adds a second level of existence.** The AST has templates and inline definitions; the objects have instantiations and emitted copies (fmt: 37,197 instantiation symbols with no AST definition cursor; 59,972 weak symbols, 95% of all defined text; 2,518 implicitly defined special members). libclang's cursor API does not expose implicit instantiations, implicit members or compiler-generated symbols, so **the C++ edge extractor reads codegen** (`clang -S -emit-llvm -O0` per unit, or the object's relocations as the oracle does) and demangles instances back to the template's identity, while the AST walk keeps what it is good at: declarations, scopes, source ranges, `overrides`, which call sites are virtual or dependent, and the evidence locators. Two extractor identities, one artifact, both inside the contract. Identity by USR held across templates, overloads, namespaces, inline and ODR definitions, methods, member pointers and cross-unit identity with zero collisions.

**Substrate and cost.** AEW implements no parser of its own: libclang or clangd's index under the compilation database, with the exact tool and extractor identity recorded. Parse is 16 to 29 ms per C unit and the Python cursor walk 52 to 117 ms; for C++ the walk is 5 s per unit, so the Python walk is the v1 extractor for C and not the production extractor for C++ (§11).

### 6.3 Later language extensions

Python, TypeScript, Go and others add their own extractors when an AEW use case and F19 evidence justify them, modelling their own language and build semantics rather than the C/C++ schema: Python declares `imports` only until a type checker gives it `static_inference` facts; TypeScript's unit is the project reference; Go's the package with its build tags. These are examples, not commitments.

### 6.4 Storage, composition and the derived index

Semantic-extension artefacts are immutable derived artefacts associated with the structural map, the source tree and their semantic inputs, stored and pointed at like the structural map (§4): a content-addressed file under the project's maps directory and one attributable manifest pointer per extension, not a K0 admission and never an ADR-0013 `reference` record (decision 18). Composition is explicit:

```text
structural map
    + zero or more current semantic-extension artefacts
    = effective navigation and context view
```

No combined artefact becomes a new authority source; extension availability never changes dispatch legality by itself.

Two consequences of scale, from the benchmark: **a derived, rebuildable index** (symbols, edges, unit membership, header fan-out, FTS over names, in the pattern of ADR-0011's `local/history.sqlite`: a locator, never a voucher), because at 100 MB to 1 GB of facts `callers(X)` is an index lookup, not a file scan; and **a whole-repository first extraction is a scheduled job, not a command** (a 50,000-unit first build is about two hours single-core, a quarter-hour on eight cores), with a receipt per job in ADR-0013's capture pattern and the ADR-0012 outbox as its signal. `aew map generate` stays synchronous for the structural map only.

### 6.5 The agent-facing query surface

The designer's eight questions were run against curl's extraction. Single-hop answers fit in a few hundred tokens with evidence (`define` 75 to 100; `callers` 55 to 345; `callees` 65 to 215; `neighborhood` at radius 1, 80 to 450); **radius 2 jumps to 6,700 to 10,800 tokens** for a well-connected function; the whole extraction is 33 million tokens and the direct-edge list alone 140,000. The graph never fits; radius is the budget knob with a cliff between 1 and 2.

The surface is a typed tool set in the typed Lead surface's shape, registered through the capability registry (F13), over the shared fact kinds:

```text
map.symbol(name|id)             definitions, declarations, kind, linkage, type, units; status defined | declared_only | unknown
map.callers(id)                 direct_callers[], address_taken_in[] (holders), each with unit:line; completeness note
map.callees(id)                 direct[], indirect[] (through what), builtins[]; completeness note
map.includers(path)             units that read the header; count first, list on demand
map.configuration(id|unit)      defines, flags and generated inputs of the units that see the symbol
map.evidence(from, to)          the sites (unit, line, kind, emitted symbol) behind one edge; L3 is the source range
map.neighborhood(id, radius=1)  nodes with one definition locator each, edge list, size
map.search(text|pattern)        lexical over names and paths; a candidate generator, never an answer
```

Rules:

1. **Radius 1 by default; radius 2 only when explicitly requested and budgeted** (designer, 2026-10-05). An agent that wants the second hop takes it as explicit `callers` and `callees` steps or names a budget.
2. **Every answer carries its boundary**, a sentence generated from the fact tiers ("direct callers are compiler-known; address-taken holders show where a pointer is stored; who calls through it is not statically known"). This is what stops "who calls X: none" from reading as "nobody".
3. **Evidence is a locator, not a voucher**: `unit:line`, resolvable to the source range; the agent that needs certainty reads the line.
4. **Disclosure levels** as the recall design's L0 to L3: L0 the capability matrix for this project; L1 a `symbol` or `callers` answer; L2 `neighborhood` at radius 1 or `evidence`; L3 source ranges and radius 2 under a budget. The model stops at any level.
5. **Configuration is a parameter, not a surprise**: `map.callers(X, configuration=cfg-…)`, or the answer says "in 2 of 3 configurations".
6. **Coverage statements make empty answers meaningful**: `NOT_FOUND`, `NOT_SUPPORTED` ("this extension emits no `calls` facts") and "none, and the substrate is complete here" are three different answers, possible only because the capability matrix and per-unit quality exist.
7. **An agent that calls a relation operation has classified its own question.** The typed surface is the exact stage of query routing; discovery for an unanchored question starts with the structural map, then lexical search; vector search over code is optional and candidates-only.

### 6.6 Incremental freshness and rebuild

Freshness and rebuild are **per unit, from the unit's input set**. Each kind of change has a known invalidation scope, measured on curl (`clang-scan-deps` gives each unit's exact input set in 2 ms; 158 project headers with median fan-out 21 units, mean 83, p90 192; six headers reach all 434 units; re-extraction costs 30 ms parse plus 50 to 120 ms walk per unit):

| Change | Detected by | Invalidates |
|---|---|---|
| a unit's source file | `git diff` on the unit's source | that unit (and any unit that includes it, rare for `.c`) |
| a header | the header's fan-out set from the dependency index | its fan-out: median 21 units, worst case all |
| a compile command (flags, `-I`, `-D`) | compile-database diff per entry | that unit; a global flag change is every unit |
| a generated header | the hash of the build-directory inputs | its fan-out: all 434 for `curl_config.h` |
| the toolchain | the extractor identity | every unit, **and** a new artifact version rather than an update |

**The dependency index (header to units) is the first thing to persist**: 2 ms per unit to rebuild from scratch, and what turns "a header changed" into "these 21 units". A semantic unit is STALE when any file in its recorded input set changed, CURRENT otherwise; the artifact's status is the count of stale units, because on a 50,000-unit repository a few units are STALE after every commit and a single flag would read STALE forever and be ignored.

**Publication stays atomic.** Units are re-extracted incrementally, but the published artifact is one immutable record per revision; a partially updated map would make `callers(X)` mix two revisions' edges. Rebuild the stale units, assemble, publish one record; the previous record stays for the audit. A typical commit touching one `.c` and one leaf header costs a few units and a second; a `curl_setup.h` touch costs a minute single-core.

**An answer carries the staleness of the units it touched** ("2 of 5 units STALE since <commit>"). A STALE semantic fact is navigation, as KC §13 says of stale derived knowledge; consequential claims are re-verified at L3.

### 6.7 Architecture-map augmentation from semantic evidence

The bridge is `deterministic map → semantic extension → investigator synthesis`, with evidence links, instead of the investigator rediscovering the repository through search. The deterministic layers hand the investigator: from the structural map, directory roles, entry points, build systems, test locations, generated boundaries and languages; from the semantic map, module boundaries as units and their inclusion, the public surface (external-linkage definitions per directory), dispatch tables and their implementers (from `holds_pointer_to`), cross-module call density (edges between directories), the configuration variants, and the headers everything depends on. Each is a deterministic query with evidence sites.

Rules: the investigator receives L1 and L2 answers, never the graph, and its launch contract lists the queries it may run; every architecture-map statement has an evidence binding to a `map.*` answer or a source range, and a statement without one is labelled inference; the architecture map stays a discovery record (§5), and the semantic artifact's revision is one of its observed inputs, so a semantic rebuild makes the architecture map STALE in the parts bound to changed facts; the K-arm evaluation (F19) compares an investigator with `map.*` against one with search on the same repository and questions, on evidence-binding density and tokens consumed, before anyone believes the bridge.

## 7. Packs and context: interfaces now, serving policy after evaluation

T5 defines bounded **read and query interfaces**, not automatic context-serving policy. Safe deterministic slices: codebase directory rows intersecting a Ticket's already-authoritative scope globs; generated and vendor hints intersecting those paths; directory, test and build metadata for the files in a reviewer diff; the selected map's freshness and limits metadata. These are bounded by authority that already exists and remain labelled derived navigation context, so F19 may use them.

The semantic map enters a pack only as L0 (what can be asked) plus, at most, the L1 answers for the Ticket's declared subject symbols, a few hundred tokens each; the structural map's few KB may enter a pack. Automatic full-map injection, architecture-map injection, token budgets and role-specific serving remain evaluation questions: F19 compares the map-assisted arm against the M3 failure mode in which the Lead guessed scope globs, and if no measurable benefit justifies the context cost, the maps remain on-demand query surfaces.

### 7.1 Sibling project-understanding indexes

Three derived indexes belong beside the maps, composed when their inputs exist and declared in the consumer's coverage, never fields of the structural record (PUI §8, as corrected by the designer):

- **The test index**: test file → the directories it exercises (structural, from paths) and, when a semantic extension exists, → the symbols it names. It degrades to its structural half without semantic data and says so.
- **Public-surface counts per directory**: external-linkage definitions per directory, available only when a semantic extension covers the language; absent otherwise, never a required structural field.
- **The constraint locator index**: oracle rules, invariant-index ids, schema keys, guardrail entries, ADR sections and requirements-ledger ids, each with the terms they mention: deterministic text indexing over authority, a project-understanding index beside the maps because contract and ADR text is not repository structure.

Each carries its own freshness. Their consumer is the deterministic impact surface of a later Profile and Impact design (register F30), which composes them and declares which were available; T5 states that it is that design's substrate and goes no further.

## 8. Explicit non-goals

- Language-semantic graphs or import graphs in the v1 structural map.
- Model-generated summaries in the deterministic map.
- Ownership maps and glossary generation.
- Any automatic policy or check-command application from map findings.
- Any dispatch gate based on codebase-map freshness.
- Treating project maps or semantic artefacts as K0 to K3 Knowledge admission.
- Following untracked or symlinked repository content into the host filesystem.
- Full-pack serving policy before F19 evidence; semantic facts in packs beyond L0 and the declared subject symbols.
- A single universal semantic graph schema across languages, or forcing one language's units into another's.
- Making a language extension mandatory for core T5 functionality.
- Treating semantic-extension output as stronger evidence than the source and build inputs that produced it.
- A parser of AEW's own for any language.
- The Profile record family, `aew impact`, plan-assurance slot filling, investigator triggers, the Ticket narrowing rule and the evaluation corpus of real changes: a later design (F30), for which T5 is the substrate.

## 9. Frozen designer decisions

Decisions 1 to 15 are v0.3's (2026-10-04), carried unchanged except decision 4, amended on 2026-10-05; decisions 16 to 18 are the designer's of 2026-10-05.

1. **First map at init:** T10 wins. `aew init` may generate a deterministic preview automatically, but adopting the project map pointer occurs only through the attributable bootstrap proposal and apply, or a later explicit map generation.
2. **No import graph in v1.** The structural map addresses the scope-navigation failure with far less semantic risk; a graph extractor earns its complexity in F19 and is separately versioned and qualified.
3. **A stale codebase map never blocks dispatch.** Navigation only; regenerate mechanically when useful. A separately bound architecture or discovery record triggers ordinary input-freshness rules only when a workflow artifact explicitly declares it a required semantic input.
4. **Freshness binds the tree listing plus the configuration blobs the generator read** (amended 2026-10-05; v0.3 bound the whole tree). STALE on an add, delete or rename, or a change to a file the generator read; CURRENT through content-only commits; never ordinary `observed_paths`, which would miss added paths. Until this version is adopted, v0.3's whole-tree rule governs.
5. **Generate from Git objects, not the working tree or index.** `--commit H` is reproducible regardless of the checkout's state, and a test asserts it.
6. **Untracked or ignored workspace content is excluded from the canonical map.** A future local overlay may show it ephemerally.
7. **Maps are derived project context, not Knowledge admission.** Manifest selection promotes neither map into semantic authority.
8. **Architecture selection is not truth certification.** It chooses the current attributable navigation reference and preserves source class and freshness.
9. **Serving stays measurable.** Bounded slices are allowed as F19 inputs; automatic or full-pack serving is adopted only if evaluation shows benefit.
10. **Generator limits are part of the record.** Large inputs fail soft by explicit caps and omissions, never by silent truncation that appears complete.
11. **Structural core plus semantic extensions is the permanent composition model.**
12. **C/C++ is semantic extension number one.** Its freshness and input identity include compilation and build context and extractor and toolchain identity in addition to the Git tree.
13. **Compiler-quality C/C++ extraction only.** No AEW-specific parser; no call or include graph inferred from text scanning; compilation-database-aware tooling with coverage and limitations exposed.
14. **Extension failure is local.** A failed or stale extension degrades only that enrichment; it never invalidates the structural map or blocks dispatch.
15. **Language schemas may differ.** Python imports, C/C++ translation units, TypeScript project references and Go packages are not forced into one graph model.
16. **Radius 1 by default; radius 2 only when explicitly requested and budgeted** (2026-10-05).
17. **The research round is closed** (2026-10-05): T5 plus the semantic research consolidate into this version and the contract of §6.1; the C++ production extractor is an implementation item with its own oracle, not a research question; project understanding uses existing KC machinery, and the impact surface is a later design that feeds existing Plan Assurance.
18. **Semantic artefacts are pinned by the project-map manifest, one pointer per extension** (2026-10-05): immutable, content-addressed derived project-map artefacts whose identity binds source revision, configuration set, extractor and toolchain identity, input-set digest and artifact hash; never ADR-0013 K0 `reference` records; no monolithic `semantic_map` pointer; selection history, if wanted, is a normal control or history event.

## 10. Proposed for the contract freeze

What the research asks the designer to confirm or edit when adopting this version; each is in the body above and would otherwise be an implementer's guess.

1. The fact vocabulary and its tiers (§6.1): `compiler_known | static_inference | unsupported`; the ten `reference.kind`s, the seven from C plus `dependent`, `virtual` and `overrides` from C++; `symbol.instances[]`; `source: ast | codegen`; Python declares `imports` only.
2. Unit identity as `(source, compile-command hash, toolchain)` with a file as a view over its units, rather than a file-first model with configurations attached (simpler for Python, wrong for C).
3. Toolchain identity mandatory in the extractor identity and derived from the compiler.
4. Per-unit freshness with the fourth state `PARTIAL`, the artifact's status as a count, and the dependency index as the first persisted structure.
5. Deduplication by stable identity as the artifact's form, with a derived rebuildable index beside it and the whole-repository first extraction as a scheduled job with a receipt.
6. Extensions add facts, never queries; the `map.*` surface of §6.5 with its seven rules.
7. The listing-plus-config freshness rule of §3 and the two-level directory cap of §2 for the structural map.

## 11. Open at the freeze

1. **The extractor for v1.** Python bindings over libclang (zero new toolchain; sufficient to tens of thousands of C units with parallelism; 5 s per unit for C++) or a small C++ tool against libclang (fast; one more build artifact). The data says bindings for C, codegen for C++ edges; the choice is the implementer's unless the designer wants it fixed.
2. **Semantic facts in packs beyond L0 and the declared subject symbols**, after F19's first measurement (§7).
3. **The `directories` role table's width** (§2): widen for the SPT repository's eight unknowns, as a new ruleset version, or leave it to the architecture map.

## 12. Evidence

The T5 probe and its result files (`eval/reviews/architecture-2026-10-04/t5/`: the generator, the two-checkout comparison, the listing-versus-content commit counts); the synthetic 10,000- and 100,000-file benchmark (`eval/reviews/architecture-2026-10-04/t5/synth-bench.out.txt`); the C and C++ extraction probes, oracles and query samples (`eval/reviews/architecture-2026-10-04/sem/`, run on Rocky Linux 8.10 with Clang 21.1.8 against zlib 1.3.1, curl 8.11.1 and fmt 11.0.2). Every number in this document is read from those files; nothing was re-derived.
