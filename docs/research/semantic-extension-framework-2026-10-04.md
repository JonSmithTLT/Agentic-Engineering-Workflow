# S2–S5 — The semantic-extension contract, the agent-facing query surface, incremental freshness, and the bridge to the architecture map

- **Status:** design note from the independent architecture review, 2026-10-04, written against the C/C++ investigation (`S1-cxx-semantic-extraction-investigation.md`) and the structural map probe (`T5-codebase-map-probe-results.md`), so that the contract is tested by C before it is shaped by Python. Not governing. Threads S2–S5 of the designer's brief: the plugin contract, the code-intelligence surface, incremental freshness, and architecture-map augmentation. Register home: F22 (project maps); the semantic extension is the "separate" item ARR-70 names.
- **Basis [doc]:** KC §8.2–§8.5 and §13 (maps, derived knowledge, freshness); ADR-0013 (knowledge records in the manifest; `reference` kind); the recall/context-routing design v0.3 §9 (exact resolution first), §16 (L0–L3 disclosure), §17 (agent operations), §21 (budgeting), §26 (provider boundary); the review response G3 ("derived project knowledge with freshness/provenance, may contain K0 references") and §6 ("language-server providers first" as a priority hypothesis). **[probe]** marks a number from S1 or T5.
- **The one sentence:** every extension produces *facts with a tier, a scope and a locator* into one deduplicated store keyed by stable symbol identity, and the agent asks that store questions through a typed surface that returns a few hundred tokens with evidence, never the graph.

## S2. What every extension shares, and what stays language-specific

The designer's eight headings, each decided from what C forced and Python allowed.

### 1. Capability

Shared: an extension declares which **fact kinds** it can emit, each with a **tier** (the S1 three tiers made general):

```text
tier: compiler_known | static_inference | unsupported
```

and the fact kinds themselves are a closed, shared vocabulary:

```text
symbol        (identity, kind, name, declared_at[], defined_at[], linkage/visibility, type_text)
containment   (symbol belongs to unit; unit belongs to module/file/package)
reference     (from, to, kind: calls | calls_through | holds_pointer_to | imports | includes | uses_type | expands_macro, site)
configuration (unit, defines/flags/features, generated inputs)
quality       (unit, parse_status: ok | partial | failed, diagnostics)
coverage      (symbol, run_id, executed, counts)       -- optional overlay
```

Language-specific: *which* kinds a language can fill and at which tier. C fills `symbol`, `containment`, `reference` (all seven kinds), `configuration`, `quality` at `compiler_known`, with the S1 exceptions declared as `static_inference` on the `calls` kind for the `memcpy` class. Python (the T5 probe's `ast` import graph) fills `symbol`, `containment`, `reference.imports` at `compiler_known` (it is the interpreter's own parser) and nothing about calls or types without a type checker (which would be a second extension, `static_inference`). TypeScript or Go without a toolchain fill nothing. **The matrix is data, so a pack or a query can say "no call facts for this language" instead of returning an empty list that reads as "no callers".**

### 2. Source and build inputs

Shared: an extension names its **input set** per unit, because freshness (S4) is computed from it: the unit's source, the files it transitively reads, its configuration (flags, defines, feature set), its generated inputs, and the **toolchain identity** (tool, version, resource dir).

Language-specific: C's input set per TU is the `clang-scan-deps` set (median 141 files [probe]) plus the compile command and the toolchain. Python's is the file alone (imports are resolved by name, and resolution is a separate, cheaper fact). Rust's would be the crate.

What C forced: **the unit is the translation unit, not the file.** 169 curl files are 434 TUs [probe]. A contract that keys facts by file is wrong for C from the first query ("what does X do under which configuration?"). Shared rule: facts are keyed by `(unit_id, symbol_id)` where `unit_id` hashes the input set's identity (source path + compile command + toolchain), and a file is a *view* over its units.

### 3. Extractor identity

Shared: `extractor: {name, version, toolchain: {tool, version, resource_dir_hash}, options}` on every produced artifact, and a rule: **facts from two extractor identities are never merged into one record**; a new identity produces a new artifact version, and the old one stays readable (ADR-0013 D3: versions, not rewrites). Why: Clang 21 and Clang 18 disagree on diagnostics and on a few macro facts; the libclang wheel and the system compiler are two identities already [probe].

### 4. Freshness

Shared, and this is the S4 result (below): freshness is **per unit, from the unit's input set**, three states as `engine/freshness.py` already has them (CURRENT / STALE / UNKNOWN), plus a fourth the structural map does not need: **`PARTIAL`** for a unit whose last extraction had errors. The artifact's freshness is the worst of its units' and the number of stale units, never a single flag.

Language-specific: how the input set is computed (`clang-scan-deps`; Python's `ast` import list; the structural map's "listing plus two files").

### 5. Coverage

Two meanings, kept apart because S1 needed both words:

- **Extraction coverage**: of the units the build names, how many were extracted and at what quality (`1 of 1,379 failed; 0 partial` [probe]). Shared; every answer can be qualified with it ("answered from 433 of 434 library units").
- **Execution coverage**: which symbols a recorded run executed (`llvm-cov`: 108 of 163 zlib functions [probe]). Optional overlay bound to a run; joins by symbol identity; never a property of the static map.

### 6. Artifact identity

Shared: the artifact is a **knowledge record** in the ADR-0013 sense: immutable, content-addressed, pinned by a manifest entry of kind `reference` (the review response's "derived project knowledge with freshness/provenance, may contain K0 references"), with `source_revision`, the extractor identity, the configuration identities it covers, and its input-set digest. Many units, one artifact per (revision, extractor, configuration set); S4 explains why the artifact is *incrementally* rebuilt but *atomically* published.

What C forced: **deduplication is not an optimization, it is the artifact.** Per-TU dumps of curl's library are 134 MB; the distinct symbols are 3,866 [probe]. The artifact stores symbols once by stable identity (USR for C/C++; module-qualified name for Python), per-unit membership, and edges by identity.

### 7. Queries

Shared: the S3 surface below, over the shared fact kinds. An extension adds no query of its own; it adds facts, and a fact kind it cannot fill makes the shared query answer "not available for `<language>` (`<extension>` emits no `calls` facts)".

### 8. Limitations

Shared: a **limitations block in the artifact and echoed in answers**, generated from the capability matrix and the quality facts, not hand-written: "direct callers complete; address-taken holders listed; calls through pointers not resolved; `memcpy`-class edges codegen-variable; 1 unit failed to parse". S1 §3 is the C instance; Python's is "imports only; no calls, no types".

### What must stay language-specific, named

The extractor itself; the unit definition; the input-set computation; symbol identity scheme (USR vs qualified name); which `reference.kind`s exist (C has `holds_pointer_to`, Python has `imports`, neither has the other's); the tier exceptions. Everything else above is shared, and the C run did not need a shared field Python would break.

### `map.semantic.*` shape (candidate, not decided)

```yaml
schema: aew/semantic-map/v1
source_revision: <commit>
extractor: {name: cxx-libclang, version: 0.1, toolchain: {tool: clang, version: 21.1.8, resource_dir_sha256: …}}
configurations:            # one per distinct compile-command shape
  - {id: cfg-a1b2, defines: [...], flags_sha256: …, generated_inputs: [{path, sha256}]}
units:                     # translation units / modules
  - {id: u-…, file: lib/altsvc.c, configuration: cfg-a1b2, inputs_sha256: …, quality: ok, diagnostics: 0}
symbols:                   # deduplicated by identity
  - {id: "c:@F@Curl_altsvc_parse", name: Curl_altsvc_parse, kind: function, linkage: external,
     defined_at: [{unit: u-…, file: lib/altsvc.c, line: 487}], declared_at: [...], type: "..."}
references:
  - {from: "c:@F@Curl_altsvc_parse", to: "c:@F@Curl_dyn_add", kind: calls, tier: compiler_known, sites: [{unit, line}]}
  - {from: "c:@F@cf_socket_active", to: "c:@F@memcpy", kind: calls, tier: static_inference, note: codegen-variable}
  - {from: "c:@Curl_cft_http_proxy", to: "c:@F@Curl_cf_def_cntrl", kind: holds_pointer_to, tier: compiler_known, sites: [...]}
  - {from: "c:@F@Curl_conn_cf_cntrl", to: null, kind: calls_through, through: "field do_cntrl", tier: compiler_known}
capabilities: {calls: compiler_known, calls_through: compiler_known, holds_pointer_to: compiler_known, imports: n/a, uses_type: compiler_known}
limitations: ["…generated from capabilities and quality…"]
coverage_overlays: []      # optional, by run
```

Size estimate from S1: curl's library deduplicated is a few MB of YAML (3.9k symbols, ~17k edges with sites); still never a pack item.

## S3. The agent-facing code-intelligence surface

**Finding first [probe]:** the designer's eight questions were run against curl's extraction (`repro/sem/cxx_query.sample.out.txt`). Answer sizes: `define` 75–100 tokens; `callers` 55–345; `callees` 65–215; `neighborhood` radius 1 80–450; **radius 2 jumps to 6,700–10,800 tokens** for a well-connected function (`Curl_altsvc_parse`, `Curl_dyn_add`) and stays under 400 for a leaf. The whole extraction is 33 M tokens; the direct-edge list alone 140k. So: every single-hop question fits in a few hundred tokens with evidence; the graph never fits; and radius is the budget knob, with a cliff between 1 and 2.

**Design [rec].** A typed tool surface (T1's MCP shape, F13's capability registry) with these operations, mapped to the shared fact kinds:

```text
map.symbol(name|id)             -> definitions, declarations, kind, linkage, type, units; status defined|declared_only|unknown
map.callers(id)                 -> direct_callers[], address_taken_in[] (holders), each with unit:line; completeness note
map.callees(id)                 -> direct[], indirect[] (through what), builtins[]; completeness note
map.includers(path)             -> units that read the header; count first, list on demand
map.configuration(id|unit)      -> defines/flags/generated inputs of the units that see the symbol
map.evidence(from, to)          -> the sites (unit, line, kind, emitted symbol) behind one edge; L3 is the source range
map.neighborhood(id, radius=1)  -> nodes with one definition locator each, edge list, size; radius 2 requires an explicit budget
map.search(text|pattern)        -> lexical over names and paths; a candidate generator, never an answer (routing §10 rule)
```

Rules the probe justifies:

1. **Every answer carries its boundary.** The probe's answers end with a `boundary` sentence generated from the fact tiers ("direct callers are compiler-known; address-taken holders show where a pointer is stored; who calls through it is not statically known"). This is the recall design's "support/conflict qualification" applied to code facts, and it is what stops "who calls X → []" from reading as "nobody".
2. **Evidence is a locator, not a voucher** (ADR-0011 P3-1 again): `unit:line`, resolvable to the source range at L3; the agent that needs certainty reads the line.
3. **Disclosure levels, as the recall design's L0–L3**: L0 the capability matrix for this project ("C: calls, holders, includes; Python: imports"); L1 a `symbol`/`callers` answer; L2 `neighborhood` radius 1 or `evidence`; L3 source ranges and radius ≥ 2 under an explicit budget. The model stops at any level.
4. **Not in packs by default.** The structural map's few KB may enter a pack (F22); the semantic map enters only as L0 (what can be asked) plus, at most, the L1 answers for the Ticket's declared subject symbols, which the T5 probe and S1 put at a few hundred tokens each. A 50k-token graph in every run is exactly what the designer said not to assume, and the measurements agree.
5. **Configuration is a parameter, not a surprise.** `map.callers(X, configuration=cfg-…)` or the answer says "in 2 of 3 configurations"; curl-without-TLS and curl-with-TLS are different graphs.

What S6 adds: the choice *between* `map.*`, source search, structural map, history and knowledge recall is the routing problem, and these operations are the cheap deterministic tier of it (§S6 note).

## S4. Incremental freshness and rebuild

**Data [probe]:** `clang-scan-deps` gives each TU's exact input set in 2 ms per TU. On curl's library: median header fan-out 21 TUs, mean 83, p90 192; six headers reach all 434; 87 of 158 reach ≤ 50; 116 of 198 system headers reach every TU. Re-extraction costs 30 ms parse + 50–120 ms walk per TU.

**Rule [rec]:** freshness and rebuild are **per unit, from the unit's input set**, and the input set has six parts the designer listed, each with a known invalidation scope:

| Change | Detect by | Invalidates |
|---|---|---|
| source file changed | `git diff` on the unit's source | that unit (and any unit that *includes* it, rare for `.c`) |
| header changed | the header's fan-out set from the dependency index | its fan-out: median 21 TUs, worst case all |
| compile command changed (flags, `-I`, `-D`) | compile-database diff per entry | that unit; a global flag change is every unit |
| define changed | same as compile command, or a generated header | per unit |
| generated header changed | hash of the build-dir inputs (`curl_config.h`) | its fan-out: all 434 for `curl_config.h` |
| toolchain changed | extractor identity (tool, version, resource dir) | every unit, **and** a new artifact version rather than an update |

The dependency index itself (header → units) is the first thing to persist; it is 2 ms/TU to rebuild from scratch and it is what turns "a header changed" into "these 21 units", so the structural map's "listing plus config" rule (T5) generalizes: **a semantic unit is STALE when any file in its recorded input set changed, CURRENT otherwise**, and the artifact's status is the count of stale units.

**Why atomic publication still matters.** Units are re-extracted incrementally, but the published artifact is one immutable knowledge record per revision (S2 §6): a partially-updated map would make `callers(X)` mix two revisions' edges. Rebuild the stale units, assemble, publish one record; the previous record stays for the audit. Cost at curl's scale: a typical commit touching one `.c` and one leaf header is a few units, a second; a `curl_setup.h` touch is a full minute single-core, or seconds on eight cores.

**At 50k–500k files** [inf, from the measured constants]: parse+walk ≈ 0.1 s/TU → 50k TUs ≈ 1.5 h single-core for the first build, minutes incrementally; the dependency index ≈ 100 s; the deduplicated artifact tens of MB. The incremental path is the only viable one, and it needs the unit-level input sets from day one. S7 has the structural-side numbers.

**Freshness of a query answer.** An answer is assembled from units; it carries the staleness of the units it touched ("2 of 5 units STALE since <commit>"). A STALE semantic fact is navigation, as KC §13 says of stale derived knowledge; consequential claims are re-verified at L3.

## S5. Architecture-map augmentation from semantic evidence

**The bridge the designer named:** `deterministic map → semantic extension → investigator synthesis`, with evidence links, instead of the investigator rediscovering the repository through grep.

**What the deterministic layers can hand the investigator [inf, grounded in the probe]:**

- From the structural map (T5): directory roles, entry points, build systems, test locations, generated boundaries, languages. Cheap, exact, a few KB.
- From the semantic map (S1/S2): module boundaries as *units and their inclusion*, the public surface (external-linkage definitions per directory: curl's `Curl_*` by file), dispatch tables (`Curl_cftype` instances: who implements the connection-filter interface, from `holds_pointer_to`), the cross-module call density (edges between directories, from `calls`), the configuration variants (what differs between `cfg-*`), the headers everything depends on (fan-out ≥ 90%: the "platform" layer). Each is a deterministic query over the artifact with evidence sites.

**The investigator's job becomes synthesis over named evidence**, not discovery: given "here are the 12 `Curl_cftype` tables and their 9 implementers, here are the 6 headers every unit reads, here are the directory-to-directory call counts", write the architecture map's prose (components, boundaries, flows, ownership) and bind each statement to the query results it rests on. ADR-0008's discovery record already carries evidence bindings; the only new thing is that the bound evidence is a `map.*` answer (a knowledge record locator plus the query) rather than a grep transcript.

**Rules [rec]:**

1. The investigator receives L1/L2 answers, never the graph; its launch contract lists the queries it may run (`map.*`, `history`, source read), and the pack carries the L0 capability matrix and the structural map.
2. Every architecture-map statement has an evidence binding to a `map.*` answer or a source range; a statement without one is labelled inference, as the knowledge drafts label `ROLE_ATTESTED`.
3. The architecture map stays a discovery record (T5 §6): model-authored, Lead-accepted, freshness by its bound evidence; the semantic artifact's revision is one of its observed inputs, so a semantic rebuild makes the architecture map STALE in the parts bound to changed facts.
4. Measure before believing: the K-arm evaluation (F19) should compare an investigator with `map.*` against one with grep on the same repository and question set, on evidence-binding density and on tokens consumed; S6's routing evaluation shares the harness.

## Decisions for the designer [Q]

1. Confirm the three-tier fact vocabulary (`compiler_known | static_inference | unsupported`) and the seven `reference.kind`s as the shared contract; Python's extension then declares `imports` only.
2. Unit identity: `(source, compile-command hash, toolchain)` as proposed, with a file as a view, or a file-first model with configurations attached (simpler for Python, wrong for C).
3. The extractor language for v1: Python bindings (slow walk, 0.1 s/TU, zero new toolchain) or a small C++ tool against libclang (fast, one more build artifact). The data says bindings suffice up to tens of thousands of TUs with parallelism.
4. Whether `map.neighborhood` radius ≥ 2 exists at all on the agent surface, or only radius 1 plus explicit `callers`/`callees` steps (the probe's cliff suggests the latter keeps budgets honest).
5. Whether semantic facts may enter packs beyond L0 and the Ticket's declared subject symbols.
