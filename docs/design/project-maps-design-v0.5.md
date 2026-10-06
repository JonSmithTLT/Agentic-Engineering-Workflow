# T5 — Project Maps: Structural Core, Semantic Extensions, and Bounded Project-Understanding Substrates (v0.5)

- **Status:** **Adopted** by the designer and the operator, 2026-10-05; the implementation contract for project maps (register F22, F22.1 to F22.3; ledger PMP). The text is the designer's frozen v0.5, unchanged apart from this line and the next, which read "Design frozen — proposed for operator adoption, 2026-10-05" and "Supersedes: `T5-project-maps-v0.4.md`".
- **Supersedes:** the designer's v0.4, which was not committed; in this repository it supersedes [`project-maps-design-v0.4.md`](../archive/superseded/project-maps-design-v0.4.md), the consolidation proposed for that freeze, and v0.3 before it.
- **Scope:** This refreeze preserves v0.4's structural/semantic model and incorporates the accepted independent hardening review covering semantic-extractor containment, exact source materialization, negative dependency freshness, compile-database provenance, scalable immutable storage, derived-map revision/custody, mechanical structural input tracking, repository-controlled text safety, assurance monotonicity, configuration-qualified queries, and registry-ready invariants/failure classes.
- **Authority boundary:** This document defines derived project-navigation/context artifacts and their query contracts. It does **not** create workflow authority, Knowledge admission, policy, acceptance, or a second project specification.
- **Primary rule:** **Project maps accelerate finding and understanding evidence. Source, build inputs, governing contracts, project policy, and normal AEW authority paths remain truth.**

## 1. Frozen architecture

AEW has three distinct project-understanding mechanisms, composed but not conflated:

```text
AUTHORITATIVE PROJECT SOURCES / BUILD INPUTS / POLICY
                    │
                    ▼
        deterministic structural map
                    │
                    ├──────────────┐
                    ▼              ▼
        semantic extensions   sibling derived indexes
        (language/build)      (tests / constraint locators)
                    │              │
                    └──────┬───────┘
                           ▼
                typed map/query surface
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
      bounded role context      investigator synthesis
                                / architecture map
```

The mechanisms are:

1. **Structural codebase map** — deterministic Engine output from an exact Git commit plus the bounded metadata inputs actually parsed by the generator.
2. **Semantic extensions** — optional language/build-specific derived artifacts over exact source/build/toolchain inputs. They add symbol, relationship, configuration and quality facts without redefining the structural core.
3. **Architecture map** — attributable investigator synthesis over evidence. It remains role-attested discovery/evidence, not compiler- or engine-known truth.

A stale, missing, partial or unsupported map never changes workflow authority, dispatch legality, gate satisfaction, publication legality, or source truth.

The permanent composition rule is:

> **Structural core + zero or more qualified semantic extensions + optional sibling derived indexes = effective project navigation/context view.**

No composed view becomes a new authority source.

---

## 2. Structural codebase map

### 2.1 Purpose

The structural map answers cheap repository-shape questions without executing project code:

```text
Where is the code?
How is the repository shaped?
Which languages and build descriptors are present?
Where are likely source, tests, docs, config, generated and vendor areas?
What declared/conventional entry-point and test candidates exist?
What semantic-analysis prerequisites are present?
```

It deliberately does **not** answer semantic questions such as callers, ownership, runtime behavior, architecture purpose, or inferred component meaning.

### 2.2 Canonical record

Schema:

```text
aew/codebase-map/v1
```

The artifact is immutable and content-addressed under the project-map artifact namespace, conceptually:

```text
.aew/knowledge/maps/structural/<content-addressed-name>.yaml
```

Required envelope:

```yaml
schema: aew/codebase-map/v1
source_revision: <git commit>
source_tree: <git tree id>

generator:
  name: structural
  version: 1
  ruleset_sha256: ...

inputs:
  path_listing_sha256: ...
  metadata:
    - {path: pyproject.toml, sha256: ...}
    - {path: .gitattributes, sha256: ...}
    # only files actually parsed by this artifact

artifact_sha256: ...

limits:
  tracked_paths: {seen: ..., capped: false}
  metadata_bytes: {read: ..., capped: false}

sections: ...
```

The generator reads **Git objects**, not the mutable checkout or index:

```text
git ls-tree -r <H>
git show <H>:<path>
git cat-file ...
```

or an equivalent Git-object API.

`--commit H` therefore means exactly commit `H`, regardless of the branch checked out, staged changes, unstaged changes, or the invoking worktree.

### 2.3 Structural sections

The v1 structural artifact contains bounded deterministic sections:

| Section | Deterministic source | Meaning |
|---|---|---|
| `directories` | tracked path listing | bounded directory summaries and structural labels |
| `languages` | tracked path extensions | recognized/unknown language counts |
| `build_descriptors` | tracked filenames + bounded parsing | all recognized build descriptors, never a guessed singular build system |
| `entry_point_candidates` | bounded metadata + conventions | candidates labelled `declared` or `convention` |
| `test_candidates` | paths + bounded test-runner metadata | candidate test locations/runners/command families; proposal evidence only |
| `generated_and_vendor` | paths/names + `.gitattributes` | navigation/edit-avoidance hints, not write-deny policy |
| `semantic_prerequisites` | tracked metadata filenames | compile databases, tsconfig, pyright config, `.clangd`, etc. |
| `limits_and_omissions` | generator | caps, parse failures, unsupported inputs, unknown extensions |

The canonical structural artifact excludes:

- untracked or ignored-but-present workspace material;
- model-authored prose;
- inferred purpose or ownership;
- call/import/dependency graphs;
- runtime behavior;
- semantic public-surface counts;
- semantic test-to-symbol relationships;
- constraint text copied out of governing authority.

Symlink blobs are treated as Git objects; generation does not follow repository symlinks into the host filesystem.

### 2.4 Structural freshness — input-sensitive, mechanically enforced

This v0.5 decision preserves v0.4's input-sensitive freshness and adds an enforcement rule: **the declared input set comes from the generator's actual reads, not from a hand-maintained list.**

The structural map does **not** become stale merely because any source file content changed. Its actual inputs are:

1. the tracked **path listing** for the commit; and
2. the contents of the bounded metadata/configuration blobs that the generator actually opened through the structural input-tracking API.

Therefore:

```text
path added/deleted/renamed
    → structural map stale

recorded metadata blob changed
    → affected structural section stale / map needs regeneration

ordinary source-content-only edit with identical path listing
and no recorded structural metadata change
    → structural map remains current
```

The generator must not open repository blobs through an untracked side path. Every repository blob read while producing the canonical structural artifact flows through one input-tracking read API. The artifact's metadata-input list is emitted from that tracker.

Acceptance includes a differential oracle:

```text
for every repository blob not present in the recorded input set:
    mutate only that blob at an otherwise equivalent test revision
    regenerate
    require byte-identical structural output
```

A changed output from an unrecorded input is an invariant failure, not a reason to widen the list by hand.

The tracked **path listing itself** is an input, so newly added files cannot hide outside the pre-existing metadata list.

Freshness between selected source tree `A` and requested tree `B` is computed from Git tree/object differences and cached by the pair `(A, B)`; ordinary query handling does not repeatedly relist or reparse the repository.

Repository edge cases:

- **Submodules:** a Gitlink is represented as a tracked path plus object identity. T5 does not recursively traverse the submodule unless that repository is mounted as a separately declared source/capability with its own revision binding.
- **Git LFS:** the canonical structural map sees the Git-stored pointer blob. Materialized LFS content is used only by a separately declared capability whose content identity/provenance is bound explicitly.
- **Symlinks:** remain Git blobs; canonical structural generation never follows them into the host filesystem.

Freshness remains computed, never written back into the immutable artifact.

### 2.5 Scale

Measured structural behavior is sufficient for v1 without sharding or a dedicated structural index:

- approximately 0.11 s / 3.5 KB on the measured AEW repository without semantic imports;
- approximately 0.28 s / 18 KB at 10,000 synthetic files;
- approximately 2.1 s / 162 KB at 100,000 synthetic files;
- Git diff/listing operations remained tens to hundreds of milliseconds at that scale.

Directory output remains bounded; large/deep repositories summarize rather than emitting an unbounded directory catalog.

The 100,000-file benchmark is the **measured** support point, not a claim that one-million-file repositories have been validated. Before T5-A declares very-large-repository support, acceptance includes a one-million-path structural benchmark or a representative repository at that scale. Failure to meet the bound changes the implementation strategy, not the structural contract.

---

## 3. Project-map selection, derived revision, and storage

### 3.1 Dedicated map registry

Map selection is durable derived state with its **own revision domain**. It does not bump workflow `control_revision`.

Conceptually:

```yaml
schema: aew/map-registry/v1
map_revision: 42

selected:
  structural:
    root: .aew/knowledge/maps/structural/<root>.yaml
    sha256: ...
    source_revision: ...
    source_tree: ...
    generator_version: 1
    ruleset_sha256: ...

  semantic:
    c_cpp:
      root: .aew/knowledge/maps/semantic/c_cpp/<root>.yaml
      sha256: ...
      source_revision: ...
      source_tree: ...
      extractor_identity_sha256: ...
      configuration_set_sha256: ...

  architecture:
    evidence_id: ...
```

The existing project manifest may project or locate this registry, but **selection CAS is `map_revision`, not `control_revision`**. Map refreshes therefore do not create workflow revision churn, invalidate unrelated dashboard envelopes, or masquerade as engineering-state transitions.

### 3.2 Map-service custody

Background or asynchronous map generation/adoption uses a project-scoped, non-model **`map_service`** principal following the closed-service pattern already used elsewhere in AEW.

`map_service` may write only the closed derived-map operation family:

```text
map.artifact.*
map.registry.*
map.index.*
```

It has zero authority to mutate:

```text
work
plans
Lead generation
invocations
credentials
gates
integration/publication
Knowledge admission/disposition
```

A Lead/operator may request generation, but adoption is committed through the same closed map-service path. Service-principal encoding belongs in the appropriate authority/credential ADR amendment; T5 freezes only the authority boundary.

### 3.3 Selection is not truth

A project-map pointer means:

> **“This is the current project navigation/context artifact for this capability.”**

It does **not** mean:

- the artifact is project authority;
- every statement is accepted as fact;
- the artifact satisfies a workflow gate;
- the artifact has been admitted as reusable Knowledge.

Historical artifacts remain immutable and addressable by root digest/source binding. Map-registry history is attributable without becoming workflow history.

### 3.4 Semantic artifacts are not ADR-0013 K0 references

A structural or semantic map artifact is a **derived project-map artifact**, not an ADR-0013 `reference` Knowledge record merely because it is useful or content-addressed.

Therefore semantic maps:

- live under the project-map artifact namespace;
- are selected through the dedicated map registry;
- receive **no `knowledge_disposition` lifecycle** merely for being maps;
- do not enter K0–K3 admission automatically;
- may be indexed or mentioned by history as a storage/audit convenience without changing those semantics.

ADR-0013 remains the storage contract for actual Knowledge records. T5 does not use K0 as a generic bucket for reproducible caches.

### 3.5 Composition alignment

A composed effective view must never silently combine incompatible revisions.

Structural and semantic components compose as one effective view only when the query's required bindings are compatible, including at minimum:

```text
requested source_tree
semantic source_tree
configuration identity where relevant
extractor/toolchain identity where relevant
```

If structural is selected at `H2` and semantic remains at `H1`, both may be shown individually with explicit revision/freshness labels, but AEW must not present them as one current view.

A composition mismatch is an explicit degraded result/reason, not an inferred merge.

---

## 4. Semantic-extension contract

### 4.1 Purpose and capability model

Semantic extensions answer questions structural paths cannot:

```text
Where is symbol X defined?
Who directly calls X?
What does X directly call?
Where is a function pointer to X stored?
Which translation units include header H?
Under which build configuration does this fact exist?
Which implementation overrides this interface?
What evidence site supports this edge?
```

Each extension declares a capability matrix. Facts use the shared confidence vocabulary:

```text
compiler_known
static_inference
unsupported
```

An unsupported relation is explicit. It is never rendered as an empty factual answer.

### 4.2 Shared fact model

Shared fact families:

```text
symbol
containment
reference
configuration
quality
coverage       # optional runtime overlay, not part of static truth
```

Common relation kinds include:

```text
calls
calls_through
holds_pointer_to
imports
includes
uses_type
expands_macro
dependent
virtual
overrides
```

Language extensions emit only the relations they can support honestly.

### 4.3 Unit identity, compile-database provenance, and resolution context

Facts bind to the unit under which they were interpreted.

For C/C++ the unit is a **translation unit under one exact compilation and resolution context**, not merely a source file.

Conceptually:

```text
unit identity =
    source path
  + compile-command identity
  + compile-database provenance
  + ordered search/include roots
  + positive dependency identity
  + negative-resolution witness identity
  + toolchain/sysroot identity
  + configuration/generated-input identity
  + extractor identity
```

A file is a view over one or more units.

The same source file compiled under materially different defines/include paths is allowed to yield different semantic facts.

#### 4.3.1 Compile-database provenance

A compile-command hash is not enough. Every compilation database/input command records where it came from.

Conceptually:

```yaml
compile_database:
  sha256: ...
  provenance:
    kind: generated_from_revision | observed_build | operator_supplied_unbound
    source_revision: <H|null>
    build_receipt: <id|null>
    generator_identity: <id|null>
```

- `generated_from_revision` means AEW generated/observed the database through a bound operation over exact source revision `H`.
- `observed_build` means it came from an attributable build observation whose inputs/receipt are retained.
- `operator_supplied_unbound` is useful navigation input but is **not** treated as proven to describe `H`.

Queries and freshness propagate this qualification.

`compiler_known` means:

> **known to the recorded compiler/toolchain under the recorded compile command and resolution context.**

It does **not** mean that a shipped/deployed binary was built from that configuration. Binary/build provenance is a separate evidence claim.

#### 4.3.2 Negative dependencies and search-order freshness

Positive dependency lists alone are insufficient because resolution can change when a previously absent file appears earlier in a search path.

For languages/toolchains with path resolution, unit freshness therefore records an addition-sensitive resolution context. For C/C++ this includes:

```text
ordered project/generated include roots
directory/listing digests sufficient to detect newly shadowing candidates
known absent/probed resolution witnesses where the extractor exposes them
toolchain/sysroot identity for external roots
```

A new project/generated path that could resolve earlier than a previously selected header invalidates affected units even if none of their positive input blobs changed.

System/toolchain roots may be summarized by a bound toolchain/sysroot identity. If AEW cannot establish the stability of a required external search root, affected units are `UNKNOWN`, not `CURRENT`.

The exact optimized representation may vary, but the invariant is fixed: **CURRENT means both positive inputs and resolution-negative context remain valid.**

### 4.4 Stable symbol identity and instances

Each language chooses a stable identity scheme appropriate to its semantics. For C/C++, use compiler-quality identity such as Clang USR for source-level symbols.

The shared symbol shape supports emitted realizations:

```yaml
symbol:
  id: <stable source-level identity>
  ...
  instances:
    - mangled: <emitted symbol>
      units: [...]
```

`instances[]` represents codegen realizations of templates, inline definitions, constructors/destructors with multiple emitted forms, or analogous language features. It is empty where not applicable.

### 4.5 Composite extractor identity

A published semantic artifact has **one extractor identity**, even when production extraction uses multiple compiler views.

For C++ the preferred shape is a composite extractor:

```yaml
extractor:
  name: clang-cxx-semantic
  version: ...

  toolchain:
    tool: clang
    version: ...
    gcc_toolchain: ...        # or sysroot
    resource_dir_sha256: ...

  components:
    ast:
      implementation: ...
      version: ...
      options_sha256: ...
    codegen:
      implementation: llvm-ir   # or equivalent accepted source
      version: ...
      options_sha256: ...
```

Facts then record their immediate source:

```text
fact.source = ast | codegen
```

This resolves the apparent S2/S1b contradiction. AST and codegen are **components of one versioned extractor identity**, not two independently versioned extractor identities whose facts are silently merged.

Changing any material component/toolchain/options produces a new extractor identity and therefore a new immutable artifact.

### 4.6 Semantic root manifest and immutable chunks

A semantic-map version is an immutable **root manifest over reusable content-addressed chunks**, not necessarily one monolithic rewritten file.

Conceptually:

```yaml
schema: aew/semantic-map/v1
capability: map.semantic.c_cpp

source_revision: <commit>
source_tree: <tree>

extractor: ...

compile_database:
  sha256: ...
  provenance: ...

configurations:
  - id: cfg-...
    compile_command_sha256: ...
    search_context_sha256: ...
    defines_sha256: ...
    generated_inputs: [...]

chunks:
  units:
    - {id: u-..., sha256: ..., path: ...}
  symbols:
    - {range: ..., sha256: ..., path: ...}
  references:
    - {range: ..., sha256: ..., path: ...}

capabilities:
  calls: compiler_known
  calls_through: compiler_known
  holds_pointer_to: compiler_known
  dependent: compiler_known | static_inference
  virtual: compiler_known
  overrides: compiler_known
  ...

limitations: [...]

root_sha256: ...
```

Chunk layout is an implementation choice, but these properties are frozen:

1. unchanged units/fact chunks are reused by hash;
2. a localized rebuild does not require rewriting a full 50k-unit artifact;
3. root publication is atomic;
4. canonical ordering/serialization makes identical semantic inputs under the same extractor identity produce a byte-identical root and identical chunk identities, independent of worker completion order.

Deduplication by stable symbol identity remains part of the representation contract, not merely an optimization.

### 4.7 Coverage and quality

Two different notions remain distinct:

**Extraction coverage**

```text
how many intended units were extracted?
which failed?
which are partial?
what relation families are available?
```

**Execution coverage**

```text
which symbols/lines were exercised by a particular recorded run?
```

Execution coverage is an optional overlay bound to that run/binary/input/profile. It is not a static property of the semantic map.

Every query answer carries the extraction quality/coverage needed to interpret it.

### 4.8 Extractor execution boundary and source materialization

Semantic extraction is a **code-execution-adjacent, repository-controlled workload**. It never runs directly against the authoritative checkout.

For source revision `H`, AEW provides an exact source view through an isolation strategy allowed by the execution-workspace design:

```text
full read-only materialization
overlay / copy-on-write over an exact read-only source
proven-complete sparse/partial materialization
```

Sparse/partial materialization is permitted only when completeness for the requested extractor can be established. Otherwise extraction degrades/refuses rather than claiming complete coverage.

The semantic extractor runs under a declared containment level. On Linux the intended production profile uses the established containment/`ProcessTree` choke point with:

- source view read-only;
- private writable scratch/build/temp;
- outputs redirected into scratch;
- network policy declared explicitly;
- no writable bind of the authoritative checkout or real Git metadata.

Windows/dev environments retain their truthful weaker containment label rather than claiming Linux guarantees.

#### Compile-command normalization

`compile_commands.json` is parsed as data. AEW never executes a compile database's `command` string through a shell.

The Engine/extractor builds a normalized argv from approved shapes and:

- strips or rewrites output/dependency/temp destinations such as `-o`, depfiles, diagnostics, profiles and other side-effecting outputs into private scratch;
- refuses dynamic compiler/plugin loading and equivalent code-injection flags by default, including `-fplugin` and `-Xclang -load`;
- refuses unsupported wrappers or shell metacharacter semantics rather than guessing;
- preserves semantic flags only when their meaning is understood and represented in extractor identity/configuration;
- records normalization/refusal decisions in the extraction receipt.

The safety rule is semantic, not a finite blacklist:

> **Project-supplied compile metadata may describe how code was compiled; it may not grant arbitrary host execution or arbitrary write destinations to the extractor.**

A containment/source-view failure prevents satisfying semantic evidence. It is never papered over by running the compiler against the real checkout.

### 4.9 Map content is untrusted reference data

Repository-controlled paths, symbol names, compiler diagnostics, comments, metadata strings and candidate command text remain **untrusted data** through every projection.

When map content reaches a model or UI:

- it is delimited/typed as reference data, not instruction;
- hostile strings do not become prompt instructions;
- commands are produced only from approved typed command/check shapes;
- repository strings are never interpolated into shell commands;
- `test_candidates` / “command families” remain candidates unless an existing policy/check definition authorizes an executable command;
- dashboard “Copy CLI” or similar affordances must render from typed operations with escaped data arguments, never concatenate map strings into command text.

---

## 5. C/C++ semantic extension

### 5.1 First implementation priority

C/C++ remains the first semantic extension because it materially improves AEW's expected codebase-navigation and impact-analysis workload and has been probed on Rocky 8.

Use compiler-quality tooling. Do **not** build an AEW-specific C/C++ parser or infer call relationships from regular expressions/text scanning.

### 5.2 C boundary

The measured C probe established that, under the exact compile command:

- definitions and linkage were reproduced at effectively compiler-level accuracy;
- includes agreed with compiler dependency output;
- direct call edges agreed at roughly 99.4–99.5%;
- indirect call **sites** are knowable, while dynamic targets generally are not;
- dispatch-table/address-taken relationships are important separate facts;
- compiler-synthesized calls, builtin folding and constant-folded branches create a precise AST/codegen boundary.

Therefore C answers must distinguish:

```text
direct calls
calls through pointer/member
holds pointer to
codegen-variable/synthesized effects
```

rather than flattening them into a misleading single “call graph.”

### 5.3 C++ additions

The C++ probe confirmed the generic representation survives C++ with the shared additions already frozen here:

```text
symbol.instances[]
reference.kind += dependent | virtual | overrides
extractor.toolchain = mandatory
fact.source += codegen
```

C++ adds an important second level:

```text
AST/source definition
        versus
emitted/instantiated realization
```

For C++ instantiation-level edge fidelity, the production extractor should use a codegen-adjacent source such as LLVM IR/object information alongside the AST component. AST remains responsible for declarations, scopes, source ranges, override relations and classification of virtual/dependent sites.

Toolchain alignment is part of correctness, not metadata trivia.

### 5.4 Known limits stay visible

Examples of limitations that must remain explicit:

- dynamic target of a general function-pointer/member-pointer call may be unknown;
- dependent template calls are not fully resolved until instantiation;
- a partial/failed translation unit weakens answers touching it;
- unbuilt configurations are not silently inferred;
- AST and emitted code can differ for compiler-synthesized/folded behavior.

Partial truth is preferred to convincing overstatement.

---

## 6. Incremental freshness, rebuild, determinism, and retention

### 6.1 Semantic freshness is per unit

Semantic artifacts do not inherit one repository-wide freshness bit.

Each unit records the exact identity that gave its facts meaning, including as applicable:

```text
source
positive transitive includes/imports
ordered search/include roots
negative-resolution witnesses or addition-sensitive root digests
compile command
compile-database provenance
defines/features
generated inputs
toolchain/sysroot identity
extractor identity
configuration
```

Freshness states are:

```text
CURRENT
STALE
UNKNOWN
PARTIAL
```

`PARTIAL` means the last extraction completed with known extraction limitations/errors. `UNKNOWN` includes cases where AEW cannot prove that an external resolution root/toolchain context remains equivalent.

### 6.2 Artifact freshness is a summary

For realistic repositories, some units will often be stale while most remain useful.

Report counts, for example:

```text
49,963 CURRENT
37 STALE
0 UNKNOWN
0 PARTIAL
```

rather than reducing the whole semantic map to one `STALE` bit.

A query carries freshness for the **units and resolution contexts it actually touched**.

### 6.3 Incremental rebuild

The dependency/resolution index determines affected units.

Rebuild flow:

```text
changed positive input
or changed resolution/search context
or changed compile/toolchain/extractor identity
      ↓
identify affected units
      ↓
re-extract only affected units
      ↓
write/reuse immutable content-addressed chunks
      ↓
canonically assemble a new immutable root manifest
      ↓
atomically advance map_registry if adoption conditions still hold
```

A partially rewritten current root is never exposed.

The new root reuses unchanged chunks by content hash; one-file changes do not imply rewriting the full semantic store.

### 6.4 Deterministic publication

For fixed:

```text
source/build inputs
resolution context
extractor/toolchain identity
configuration set
```

the semantic root and reachable chunks must be canonically ordered and byte-deterministic.

Parallel worker completion order, process scheduling, temporary filenames and filesystem enumeration order must not affect artifact identity.

Acceptance regenerates representative artifacts under reordered/parallel schedules and requires identical root/chunk hashes.

### 6.5 Scale consequences

The structural map does not need sharding or an index at measured 100k-file scale.

The semantic map needs from v1:

- per-unit incremental invalidation;
- negative-dependency/search-context invalidation;
- content-addressed chunk reuse;
- deduplication;
- an efficient derived query index;
- scheduled/background first-build semantics for very large repositories.

S7's extrapolation is retained as planning evidence, not a guarantee:

```text
~10k TUs   → order-of-tens-of-MB deduplicated semantic facts
~50k TUs   → order-of-100-MB
~500k TUs  → order-of-GB
```

Exact production size depends on language/extractor/site retention and must be measured.

The derived query index may use SQLite or another local structure for:

```text
symbols
relations
unit membership
header/include fan-out
resolution/search roots
name/path search
```

It is disposable and non-authoritative. Query results resolve/authenticate back to the immutable root/chunks/source evidence.

### 6.6 Retention and garbage collection

Derived map artifacts are reproducible and do not require indefinite retention merely because they once existed.

Protected roots include:

- every currently selected map-registry root;
- roots explicitly pinned by evaluation/evidence/debug records;
- roots protected by the configured derived-artifact retention window/grace period.

Content-addressed chunks reachable from protected roots are retained.

Unreachable derived chunks/roots may be garbage-collected after the grace period. GC never deletes project authority, Knowledge records, source history, or evidence merely because a map can be regenerated.

---

## 7. Typed project-map query surface

Agents query facts; they are not handed a graph dump.

The shared surface is:

```text
map.symbol(name|id)
map.callers(id, configuration?)
map.callees(id, configuration?)
map.includers(path)
map.configuration(id|unit)
map.evidence(from, to)
map.neighborhood(id, radius=1, budget?)
map.search(text|pattern)
```

Language extensions add facts/capabilities, not bespoke agent APIs unless a genuinely different semantic shape cannot be represented honestly.

### 7.1 Configuration-qualified default behavior

References and relationship facts are configuration-qualified.

If a query omits `configuration`:

- when exactly one relevant configuration exists, AEW returns it and names it;
- when multiple configurations exist, AEW returns **partitioned per-configuration results**;
- an explicitly labelled `union`/`intersection` view may be requested or rendered as derived convenience, but it never masquerades as the result for one program configuration.

`map.callers(X)` therefore never silently unions TLS/no-TLS or other materially different builds into one caller set.

### 7.2 Answer contract

Every answer carries enough qualification to avoid false certainty:

```text
resolved subject
facts
evidence locators
fact tier/source
configuration
units touched
freshness
coverage/quality
limitations/boundary
terminal state
```

Terminal states are:

```text
SATISFIED
EXHAUSTED_BUDGET
NOT_FOUND
NOT_SUPPORTED
```

A resolved symbol with zero direct callers under complete covered facts is different from a language for which callers are unsupported.

### 7.3 Radius policy

The default neighborhood radius is **1**.

Radius 2 or larger requires an explicit budget/expansion request.

This is frozen because measured answer sizes showed single-hop queries in the tens/hundreds of tokens while radius 2 on connected functions jumped into multi-thousand-token answers.

The whole graph is never ambient model context.

### 7.4 Search is candidates-only

`map.search` locates candidate symbols/paths. A search hit is not itself a fact about behavior.

Candidates become anchors through exact resolution and then use the typed relation/query surface.

---

## 8. Query routing and disclosure

The reusable routing principle is:

> **Bind the target and requested answer shape; run the cheapest deterministic query; expand only on a measured gap.**

The router may choose queries. It never manufactures facts.

Broad classes are:

```text
exact / locator
relation
local explanation
bounded neighborhood / trace
discovery
judgment
```

The first useful path is deterministic whenever possible. Model reasoning is reserved for synthesis, bounded expansion choices when deterministic routing stalls, or actual judgment.

Escalation is driven by observed gaps such as:

- unresolved anchor;
- unsupported requested relation;
- conflicting substrates;
- radius-1 failure to connect requested anchors;
- stale/partial touched evidence;
- flat/noisy discovery candidate set.

No learned/model classifier is required in front of cheap exact queries.

---

## 9. Sibling derived indexes for project understanding

S8 identified useful deterministic inputs that do **not** belong inside the structural repository-shape artifact.

v0.4 therefore freezes them as **sibling/composed derived views**, not structural-map fields.

### 9.1 Test relationship index

A rebuildable derived index may map:

```text
test file / test id
    → referenced paths/symbols/components
    → configured check lane where known
```

When semantic facts exist, symbol relationships may be used. Without semantic coverage, path/name evidence remains explicitly weaker.

This does not make a test “required”; policy/check configuration remains authority.

### 9.2 Constraint locator index

A deterministic locator index may cover:

```text
oracle-rule ids
invariant-index ids
schema fields
guardrail entries
ADR sections
requirements-ledger ids
amendment-index entries
```

It stores **locators and searchable terms**, not rewritten constraint prose.

Authority remains the underlying contract/ADR/policy/document.

### 9.3 Public-surface projection

Per-directory/component public-surface counts or lists are derived from semantic facts when available.

They are a semantic projection, not a required field of the language-neutral structural artifact.

---

## 10. Architecture map

The architecture map remains an investigator-produced discovery/evidence record.

A bounded template may cover:

```text
components
control/data boundaries
external services
cross-component flows
ownership candidates
relevant contracts/ADRs
evidence for each claim
```

Every claim is attributable and evidence-bound.

The Lead may select one record as the current architecture navigation reference. Selection means:

> **“Use this attributable investigation as the current navigation reference.”**

It does not certify every semantic statement as engine-observed truth.

A stale architecture reference is surfaced as stale navigation/evidence. Staleness alone does not auto-dispatch an investigator or block workflow.

No separate architecture-map authority or K0 admission path is introduced.

---

## 11. Context-pack policy

T5 freezes the interfaces and safe bounds, not universal automatic injection.

### 11.1 Safe bounded context

Potential bounded context includes:

- relevant structural directory rows;
- generated/vendor hints for paths already in scope;
- selected map freshness/coverage summary;
- L0 semantic capability matrix;
- small L1 answers for already-declared subject symbols;
- relevant test/constraint locators.

### 11.2 Default serving rule

The semantic graph is **not** injected wholesale.

Packs use cheap exact/local information only. Trace/neighborhood expansion is deferred to typed tools.

Automatic serving of additional map/profile information must earn its cost through F19/evaluation.

A stale map may still be used for labelled navigation where policy allows, but consequential claims must be re-established against current source/evidence.

All map-derived strings entering context are rendered as delimited reference data under the same untrusted-content rules as §4.9.

---

## 12. Relationship to project profile and requirement impact

T5 is the substrate. It does **not** create a new Project Profile authority layer or a second Plan Assurance artifact family.

The frozen architectural relationship is:

```text
authoritative project sources
        ↓
structural map
        ↓
semantic extensions + test/constraint locators
        ↓
existing KC §8 maps / WC §16.15 guardrails
        ↓
deterministic requirement impact surface
        ↓
Plan Assurance premises / first-pass reasoning
        ↓
investigation when evidence gaps require it
```

### 12.1 Impact is downstream, not a map artifact

The useful new downstream capability is a **deterministic impact surface**, not another semantic-authority document.

Its deterministic inputs may include:

```text
resolved requirement seeds
radius-1 affected units
tests
constraint locators
configurations
writer/ownership candidates
coverage/limitations
NOT_FOUND items
```

Judgment about risk, scope, unknowns and load-bearing premises belongs in existing Plan Assurance/Lead mechanisms.

### 12.2 Frozen downstream dispositions from S8

For the later impact design:

- `aew impact` is one deterministic operation usable explicitly by the Lead **and** automatically by Plan Assurance; one implementation, two consumers.
- radius 1 is the default; radius 2 is explicit and budgeted.
- Epic-level analysis may use structural directory roles before synthesized component records exist, reporting reduced coverage.
- new impact-derived investigator triggers remain **advisory during evaluation**; existing Plan Assurance hard triggers/protected conditions remain independently hard.
- an initial promotion decision may use roughly **20–30 stratified real historical changes**, including genuinely cross-cutting cases.
- created files are reported separately as an inherent ceiling of location-based prediction.

These decisions do not require the Profile/Impact implementation to land with T5.

### 12.3 Assurance monotonicity

Maps are navigation/evidence suppliers, not self-classification authority.

A map-derived **absence**, narrow radius result, lack of relation, partial coverage, unsupported language/configuration, or `NOT_FOUND` result may **not by itself**:

- lower a Ticket/Story risk class;
- waive or remove a required gate;
- narrow a protected/preservation obligation;
- establish that no broader impact exists;
- convert an unknown premise into a safe premise.

Positive map evidence may add investigation triggers, expose contradictions, or support a Lead decision to raise assurance.

Down-classification or removal of obligations remains an explicit Lead/policy-authorized judgment through existing authority paths and must be supported by sufficient evidence beyond a map's absence result.

Deterministic impact output presents its uncertainty before its attractive result set:

```text
coverage / configurations examined
unsupported capabilities
STALE / PARTIAL / UNKNOWN units
unresolved seeds / NOT_FOUND items
then affected units and relationships
```

This prevents “radius 1 found three units” from being read as “only three units can matter.”

---

## 13. Evaluation and product gate relationship

### 13.1 Mapping evaluation

Structural evaluation covers:

- deterministic output for the same commit across checkouts;
- exact Git-object source binding;
- input-sensitive freshness;
- bounded record size and generation time;
- omissions/caps surfaced explicitly.

Semantic evaluation covers:

- symbol/definition accuracy;
- relation precision/coverage by fact kind;
- build/configuration identity correctness;
- unit freshness and partial extraction behavior;
- query answer qualification;
- rebuild cost after localized and high-fan-out edits;
- C/C++ extractor oracle on every material extractor/toolchain change.

Serving evaluation covers:

- tokens retrieved/shown;
- model calls;
- task success;
- scope mistakes/rework;
- stale/unsupported hallucination rate;
- whether map-assisted roles outperform source-search/grep-only baselines.

### 13.2 F19 / M4-H

T5 implementation must not become an excuse to postpone AEW's product-value gate.

The structural map and any minimal navigation support needed to make the M4-H experiment representative may land before the gate. Full semantic mapping, Project Profile, impact analysis, or Knowledge expansion are **not prerequisites** unless the experiment itself establishes that they are required for representativeness.

After the value gate, semantic/project-understanding features should earn product inclusion by ablation where practical:

```text
core AEW
  + structural map
  + semantic map
  + impact surface
  + knowledge recall
  + other intelligence
```

Measure each meaningful increment rather than assuming architectural usefulness implies mandatory product complexity.

---

## 14. Non-goals

This v0.5 does not authorize or require:

- a universal cross-language semantic graph schema;
- an AEW-written C/C++ parser;
- semantic facts as workflow authority;
- K0/K1/K2/K3 admission of project maps by default;
- full semantic graphs in context packs;
- automatic architecture-map truth certification;
- automatic policy/check creation from map observations;
- dispatch refusal solely because a map is stale/missing/partial;
- a new “Project Profile” document family duplicating KC §8;
- a new Requirement Impact judgment artifact duplicating Plan Assurance;
- a third-language research cycle before implementation/evaluation;
- structural sharding or a structural SQLite index at currently measured scale;
- pretending a derived index is evidence.

---

## 15. Frozen designer decisions

1. **Structural core remains language-neutral.** Semantic information is additive and independently qualified.
2. **Git objects are the source for revision-bound structural generation.** The checkout/index is never substituted for the claimed commit.
3. **Structural freshness follows actual structural inputs and is mechanically tracked.** The generator's read API, not a hand-written list, defines metadata inputs.
4. **Path listing changes remain structural inputs.** Newly added/deleted/renamed tracked paths cannot hide outside a pre-existing observed-path list.
5. **Submodules, LFS and symlinks remain explicitly bounded.** No hidden recursive/materialized dependency is silently treated as part of the canonical structural map.
6. **Untracked/ignored workspace state is excluded from the canonical revision-bound map.**
7. **Map selection has its own `map_revision`.** Background map refresh does not bump workflow `control_revision`.
8. **A project-scoped `map_service` owns asynchronous derived-map commits under a closed `map.*` operation family and has zero workflow/Knowledge authority.**
9. **Structural and semantic artifacts are derived project-map artifacts, not ADR-0013 K0 records merely by existing.**
10. **Components compose silently only under compatible source/configuration bindings.** Mixed revisions are explicit degraded state.
11. **One semantic capability may have its own selected current root.** There is no monolithic semantic pointer coupling unrelated extensions.
12. **Semantic extraction is a contained, code-execution-adjacent workload.** It never executes against the authoritative checkout.
13. **Compile commands are data, not shell programs.** AEW normalizes approved argv shapes, redirects side effects to scratch, and refuses dynamic compiler/plugin loading by default.
14. **Semantic source materialization is exact and policy-selected.** Full read-only, overlay/COW, or proven-complete sparse materialization are allowed; incomplete sparse views never claim full coverage.
15. **Compile-database provenance is part of semantic qualification.** Unbound operator-supplied databases remain visibly unbound.
16. **`compiler_known` means compiler-known under the recorded command/toolchain/context, not proven provenance of a shipped binary.**
17. **Semantic unit identity includes positive inputs and negative resolution/search context.** A file alone is insufficient.
18. **Fact tiers are `compiler_known | static_inference | unsupported`; `PARTIAL`/`UNKNOWN` remain visible.**
19. **C/C++ is semantic extension #1 and must use compiler-quality tooling.**
20. **C++ uses one composite extractor identity with AST and codegen components.** `fact.source` identifies the component; material changes create a new extractor identity.
21. **The shared semantic contract includes `symbol.instances[]` and `dependent`, `virtual`, `overrides` relations.**
22. **Semantic map versions are immutable root manifests over reusable content-addressed chunks.** Localized rebuilds do not rewrite the entire fact store.
23. **Canonical serialization is mandatory.** Identical semantic inputs/extractor identity produce byte-identical root/chunk identities regardless of parallel completion order.
24. **Semantic freshness is per unit plus resolution context.** Artifact status is a qualified count/summary, not one repository-wide stale bit.
25. **Semantic implementation is incremental and indexed from v1.** The local query index is rebuildable and non-authoritative.
26. **Derived-map retention is bounded.** Current/pinned/grace-period roots protect chunks; unreachable derived data may be garbage-collected.
27. **The graph is never ambient context.** Typed answers expose bounded facts with evidence, coverage, freshness and limitations.
28. **Relationship queries are configuration-qualified.** Omitting configuration with multiple relevant configurations returns partitioned results, not a silent union.
29. **Radius 1 is the normal neighborhood operation. Radius ≥2 is explicit and budgeted.**
30. **`NOT_FOUND`, `NOT_SUPPORTED`, `EXHAUSTED_BUDGET`, and qualified empty answers are distinct.**
31. **Search produces candidates, not semantic facts.**
32. **Repository-controlled map text is untrusted reference data.** It never becomes executable command/prompt authority through interpolation.
33. **Map-derived negative/absence evidence cannot by itself lower assurance.** Maps may expose reasons to raise/investigate; lowering remains an explicit existing authority-path judgment.
34. **Test relationships, constraint locators and semantic public-surface projections are sibling/composed derived indexes/views, not mandatory structural-map fields.**
35. **Architecture maps remain attributable investigator evidence; selection is navigation, not truth certification.**
36. **Serving remains evidence-driven.** Small structural/L0/L1 slices may be evaluated; full-map or broad semantic injection is not a default.
37. **T5 feeds Plan Assurance/project understanding but does not create a duplicate Profile or Impact authority layer.**
38. **No additional language research blocks implementation.** C and C++ have closed the representation question sufficiently for the first production extension.
39. **The M4-H value gate takes precedence over expanding mapping infrastructure.** Only mapping work needed for correctness or representative evaluation may block it.

---

## 16. Implementation slices implied by this freeze

This design permits implementation to be sequenced without reopening architecture.

### T5-A — Structural core

- `aew/codebase-map/v1`;
- Git-object generation;
- input-tracking structural read API;
- path-listing + tracked-metadata freshness;
- submodule/LFS/symlink behavior;
- immutable structural artifact + map-registry selection;
- `map show/diff/generate`;
- deterministic caps/omissions;
- differential unrecorded-input oracle;
- existing 100k regression plus a 1M-path/representative very-large-repo acceptance measurement before claiming that scale.

### T5-B — Common semantic substrate

- `aew/semantic-map/v1`;
- capability/fact/quality schemas;
- `aew/map-registry/v1` and `map_revision`;
- closed `map_service` writer boundary;
- root-manifest + content-addressed chunk publication;
- canonical serialization/determinism oracle;
- unit/configuration/extractor/compile-database provenance schema;
- derived local query index;
- retention/GC reachability;
- typed `map.*` query surface, configuration partitioning and terminal-state semantics.

**T5-B must settle the root/chunk storage and map-registry semantics before T5-C writes production semantic artifacts.**

### T5-C — C/C++ extension

- exact semantic source-view materialization;
- containment profile through the existing isolation/`ProcessTree` choke point;
- compile-command argv parser/normalizer with side-effect redirection and plugin-load refusal;
- compilation-database discovery **and provenance binding**;
- positive dependency + negative-resolution/search-context index;
- composite AST + codegen extractor identity;
- USR symbols + emitted instances;
- C/C++ relation kinds;
- per-unit/resolution-context freshness and incremental rebuild;
- C and C++ oracle suites;
- hostile compile-command and authoritative-checkout mutation tests.

**T5-C may not start implementation until containment/source-view rules, compile-database provenance, negative-dependency freshness and map-registry revision/custody are adopted.**

### T5-D — Sibling project-understanding indexes

- bounded test relationship index;
- constraint locator index;
- semantic public-surface projection;
- untrusted-string projection tests;
- no new authority semantics.

### T5-E — Evaluation / serving experiments

- map-assisted vs source-search baselines;
- pack L0/L1 experiments;
- configuration/mixed-revision/degraded-answer cases;
- F19-compatible measurements;
- later impact-surface evaluation without making it a T5 authority artifact.

---

## 17. T5 invariants and stable failure classes

These invariants are intended for the X1/X2-style registries and implementation oracles.

### 17.1 Invariants

**T5-INV-01 — No map authority.** Map state never grants workflow, policy, Knowledge-admission, integration or publication authority.

**T5-INV-02 — Authenticated currentness.** A structural/semantic result labelled `CURRENT` must be derivable from the complete declared/tracked positive and negative input identity for that result.

**T5-INV-03 — Contained extraction.** Semantic extraction may not mutate the authoritative checkout/source lineage or use it as an uncontrolled writable build target.

**T5-INV-04 — Unsupported is not empty.** An unsupported relation/capability may never be rendered as a factual empty result.

**T5-INV-05 — No silent mixed view.** Components with incompatible source/configuration bindings may never be presented as one current effective view.

**T5-INV-06 — Negative evidence cannot lower assurance.** Map absence, narrow radius, unsupported coverage, or no-hit results may not by themselves waive/lower risk, gates or preservation obligations.

**T5-INV-07 — Map text is data.** Repository-controlled map strings never become executable instruction, shell syntax, policy or prompt authority through interpolation.

**T5-INV-08 — Deterministic artifact identity.** Identical semantic inputs and extractor identity produce identical canonical root/chunk hashes independent of extraction concurrency/order.

**T5-INV-09 — Configuration identity survives.** Every configuration-sensitive semantic relation retains the configuration binding through storage, query and projection.

**T5-INV-10 — Qualification survives projection.** STALE/PARTIAL/UNKNOWN status, coverage limitations and unsupported relations remain visible through API, context and dashboard projections.

**T5-INV-11 — Closed map writer.** `map_service` commits cannot mutate workflow/Lead/invocation/credential/Knowledge authority domains.

**T5-INV-12 — Compile metadata cannot grant host execution.** Repository-supplied compile metadata cannot cause arbitrary plugin/code loading, shell execution or uncontrolled output destinations.

### 17.2 Stable failures / reason codes

Initial stable codes:

```text
SEMANTIC_SOURCE_MISMATCH
SEMANTIC_INPUT_UNBOUND
SEMANTIC_UNSAFE_COMPILE_OPTION
SEMANTIC_CONTAINMENT_UNAVAILABLE
SEMANTIC_SOURCE_VIEW_INCOMPLETE
SEMANTIC_INPUT_CHANGED
SEMANTIC_RESOLUTION_CONTEXT_STALE
MAP_UNSUPPORTED_RELATION
MAP_MIXED_REVISION
MAP_CONFIGURATION_REQUIRED
MAP_ARTIFACT_NONDETERMINISTIC
MAP_UNTRUSTED_EXECUTION_ATTEMPT
MAP_ASSURANCE_DOWNGRADE_FORBIDDEN
MAP_SERVICE_SCOPE_VIOLATION
MAP_CURRENTNESS_UNPROVEN
```

Exact HTTP/CLI presentation is a surface detail; these semantic meanings remain stable.

---

## 18. Research disposition

The mapping research cycle is closed for this freeze.

The following are implementation/evaluation questions, not reasons to reopen T5 architecture:

- exact production C++ extractor implementation language;
- performance tuning beyond the measured bounds;
- later Python/TypeScript/Go semantic extensions;
- whether broad automatic serving earns its token cost;
- how much the downstream impact surface improves real planning;
- whether a learned classifier ever earns a place ahead of deterministic routing.

A concrete implementation contradiction may return as a design defect. Otherwise, v0.5 is the implementation contract for project maps.
