# AEW phase 6: airgap capabilities, MCP selection, and harness features

Research and recommendations — October 1, 2026

## 1. Recommendation

**Ship a broad, reproducible capability bundle, expose a small relevant interface to each role, and promote providers using correct task completion per cost.** The biggest opportunities are better evidence acquisition and faster feedback: semantic source navigation, local documentation, runtime/debugger observations, browser inspection, and canonical project-state queries.

We previously selected a sensible shortlist. We did not establish a measured winner across your actual workloads. This report updates that shortlist and specifies how to finish the selection before phase 6 release.

Your report that M3 now completes Tickets at approximately bare-model quality establishes a useful starting baseline. It does not yet establish tool-stack optimality or equal performance across task families. Keep the working M3 configuration as a comparison arm.

The intended environment remains Rocky Linux 8, GPT-5.4 through an approved internal API gateway, C/Python/React development and security/reverse-engineering work, and both Codex and OpenCode adapters. Team usage and organizational standardization can differ; support both through the same capability contracts. This research does not inspect the current AEW/SPT repository, installed versions, hardware, or gateway behavior. No providers were installed or benchmarked here.

An open-ended promise that no future task will need an absent tool is impossible. A concrete replacement is: every declared workload has a tested capability path; likely specialist dependencies are transferred; unsupported capabilities are visible; every real gap becomes a reproducible fixture and a future bundle amendment.

## 2. What was already selected

The September 25 workbench design and SPT remediation appendix already covered:

| Previous decision | Updated disposition |
|---|---|
| Git, ripgrep, jq, ordinary shell tooling | Retain as inexpensive baseline. |
| ast-grep structural search | Package and teach explicitly; evaluate its current outline command too. |
| Serena with language servers | Highest-priority MCP evaluation for semantic navigation, especially Codex. Compare with native OpenCode LSP. |
| GitNexus | Retain as a candidate for relationship/impact analysis; repair and qualify existing packaging. |
| Playwright CLI plus skills | Preferred first interface for routine frontend work; MCP remains a task-specific option. |
| Compilers, tests, linters, types, sanitizers, debuggers | Make usable against real project targets, rather than merely installed. |
| Local versioned docs | Promote to an explicit release capability with query-level acceptance. |
| Optional memory service | Preserve established continuity; avoid competing stores of AEW plan/status. |
| Pinned images, native payloads, archives | Retain two compatibility targets: container execution and extracted Rocky-native execution. |
| Ghidra bridge | Retain current working provider; evaluate a headless alternative without assuming migration is necessary. |

The remediation appendix requires GitNexus writable persistent storage and Ghidra remote-artifact staging with provenance. Their current completion state is unknown here. Import remaining work into the existing AEW Work Graph; this report is a proposal and source record, not another live backlog.

The available v0.6 architecture already defines layered search, replaceable CLI/MCP providers, role grants, health states, build/test intelligence, and project-specific metadata queries. Preserve those boundaries. A previously discussed progressive-disclosure design should govern implementation; this report does not claim to validate its latest contents.

## 3. Prioritized MCP and service candidates

“Release capability” means an outcome that should be reliable before release. It does not require the specific candidate if an existing provider passes the same gate. “Benchmark” means carry a qualified candidate, compare it with the baseline, and enable it selectively.

| Capability | Preferred approach / candidate | Priority | Gate that makes it useful |
|---|---|---|---|
| Precise symbols, definitions, references | Serena over clangd/Pyright/TypeScript language server; native OpenCode LSP as alternative | Release capability; provider benchmark | Correct cross-file references, dirty-edit freshness, real include/import resolution. |
| Whole-repository relationships and impact | GitNexus, read-focused subset or its CLI | Benchmark; preserve existing SPT path | Known callers and cross-layer relationships found; incorrect/stale edges surfaced. |
| Offline documentation retrieval | Grounded Docs / `arabold/docs-mcp-server`, or lean local text/FTS provider | Release capability | Correct installed-version answer with source citation and no external service. |
| Browser interaction and regression | Playwright CLI plus existing tests; Playwright MCP selectively | Release capability for frontend | Local flow, console/network failures, screenshot, reproducible assertion. |
| Browser performance diagnosis | Chrome DevTools for agents, CLI or MCP | Specialist bundle; benchmark | Local trace explains a real UI latency issue without CrUX/public calls. |
| Binary analysis | Existing GhidraMCP; `clearbluejar/pyghidra-mcp` comparison | Release capability for RE; alternative benchmark | Known decompilation/xrefs, import/staging, restart, binary identity. |
| Stateful debugging | `ctagard/dap-mcp` candidate over debugpy/LLDB/GDB | High-value experiment | Launch, breakpoint, bounded stack/locals snapshot, resume, timeout, cleanup. |
| Canonical project metadata | The target project's existing API, or a small typed CLI/MCP adapter | Release capability where used | Identity/provenance/relationship inspection agrees with canonical state. |
| General SQL inspection | Existing SQLite/psql tools; DBHub when repeated structured discovery warrants it | Conditional | Engine-enforced access, bounded output, correct database/snapshot identity. |
| Large-output retrieval | Existing AEW artifacts first; context-mode comparison | Benchmark | Full results recoverable, failures preserved, correct resume behavior. |
| Tool discovery | Existing AEW capability registry; native support when verified; FastMCP search transform as fallback | Release capability | Small catalog plus successful discovery and authorized invocation in both harnesses. |

### Semantic source navigation

Serena supplies symbol-oriented retrieval, references, edits, and rename. Its free language-server backend differs materially from its paid JetBrains backend: some advanced refactorings and interactive debugging are JetBrains-only. Its upstream explicitly supports disabling overlapping basic utilities and memory. Use the language-server path first for portability; enable only the operations needed by a role. Agent testimonials on its README are not independent performance evidence. [S01]

For C, the real leverage is an accurate `compile_commands.json`, matching headers, generated files, compiler flags, and target configuration. clangd documents compilation-database setup; CMake export or Bear are possible acquisition routes. A language server parsing the wrong build can confidently return misleading results. [S02]

Compare these practical configurations:

| Harness | Initial candidate | Why |
|---|---|---|
| Codex | Serena retrieval subset + ordinary shell/patch tools | Supplies semantics without rebuilding an IDE layer in AEW. |
| OpenCode | Explicitly enabled native LSP, experimental navigation tool if supported by the pinned release | May cover navigation with less additional infrastructure. |
| OpenCode alternative | Serena retrieval/refactoring subset | Worth adopting if native support misses important references or transformations. |

OpenCode currently documents LSP as disabled by default, warns about stale state/resource costs, and marks its navigation tool experimental. Do not import assumptions from earlier releases; test the pinned one. [S03, S04]

### GitNexus

Current upstream offers graph context, impact, trace, change-impact queries, API-oriented analysis, and CLI equivalents. It also offers setup/indexing workflows that generate instructions, skills, and hooks. Those are integration side effects: review them before allowing the installer into AEW-owned configuration. The README's universal reliability language is a product claim, not a correctness guarantee. [S05]

Start with `query`, `context`, `impact`, `trace`, and `detect_changes` where available. Leave raw graph queries, writes, and overlapping file tools out of the default role interface. Confirm consequential graph edges in source or runtime evidence. Track worktree identity, source/dirty fingerprint, provider version, indexing configuration, and analysis readiness. Fix the earlier UID/GID, persistent mounts, and destructive-fixture concerns if still open.

Graph availability is valuable when the question spans modules. It need not be invoked for a known two-line local change. Benchmark CLI and MCP ergonomics; a graph engine does not automatically require MCP exposure.

### Local documentation: the most important airgap omission to close

Grounded Docs supports indexing local files and version-targeted queries through CLI or MCP. Embeddings are optional, so a lexical baseline can operate without a model service. Containerize its Node/runtime requirements if necessary. Qualify the exact configuration offline before adopting it. [S06, S07]

Context7's documented service/API remains an external dependency; running its client locally does not establish that the documentation corpus is hosted offline. I would not make it an airgap release dependency without an independently verified internal service. [S08]

Build documentation packs from project lockfiles and installed tools, including:

| Pack | Suggested contents |
|---|---|
| Native/Linux | Matching compiler, libc/POSIX/Linux interfaces, build system, GDB, LLVM tools, sanitizer and fuzzing guides. |
| Python | Project interpreter, pytest, type checker, framework/ORM/database drivers, dependency APIs, package source/type stubs. |
| Frontend | Installed React/TypeScript/build/test versions, MDN topics used by the project, Playwright, local UI/component guidance. |
| RE/security | Ghidra scripting/API manuals, executable-format references, analysis-library docs, current local rules and fixtures. |
| Workbench | Pinned Codex/OpenCode/MCP protocol/AEW docs, troubleshooting, known limitations and recovery procedures. |
| Project | Target-project contracts, ADRs, schemas, examples, canonical query guidance; freshness follows repository changes. |

Store origin URL/repository, upstream revision/version, acquisition date, content hash, package applicability, and redistribution metadata. Retain original pages or sources beside normalized searchable content. An arbitrary version tag on a crawl of “latest” docs does not make that crawl version-correct.

Start with lexical ranking and exact symbol/heading search. Add embeddings or reranking only if held-out queries show meaningful improvement. A local model needs its weights, tokenizer, configuration, runtime and architecture dependencies transferred; precomputed vectors alone do not supply the query encoder. An approved internal embedding endpoint is another possible provider, not an assumed dependency.

### Browser and frontend diagnostics

Microsoft now explicitly positions Playwright CLI plus skills for coding agents and describes MCP's richer inspection tradeoff. The CLI supports named persistent browser sessions too; persistence alone is not a reason to choose MCP. These are documented interface properties, not a measured saving on AEW. [S09, S10]

Use existing Playwright tests for repeatable verification. For investigation, return a bounded snapshot or targeted DOM/console/network data, with full screenshots/traces saved as artifacts. Preserve local test-account setup and service startup commands. Browser state must be isolated by ticket/worktree when concurrent jobs would otherwise interfere.

Chrome DevTools for agents adds performance traces and source-mapped browser diagnostics and has a CLI as well as MCP. For the offline profile disable usage statistics, CrUX requests, and update checks; package supported Chrome and all runtime assets. Compare it on an actual render/network performance defect before making it routine. [S11]

### Ghidra and reverse engineering

LaurieWired GhidraMCP uses a Ghidra extension and Python bridge for analysis and edits. Preserve the existing working GUI workflow if it satisfies your requirements. [S12]

PyGhidra MCP is a promising headless automation alternative, with batch decompilation/xrefs, focused outputs and an optional CLI. It is explicitly beta. Its GUI mode launches its own Ghidra process rather than attaching to an arbitrary existing instance. Ghidra analysis and MCP-side search indexing have separate readiness states. Its semantic path brings Chroma/embedding dependencies that must be investigated and packaged. [S13]

Carry the alternative for comparison if the current bridge remains difficult to automate. Do not migrate a working provider solely because the alternative has a more modern README. Measure context cost and useful findings on the same binaries. Binary hash, architecture, load address, analysis settings and database revision belong with each result; decompiled pseudo-C is derived evidence.

### Debugger interface: a useful new experiment

DAP-MCP exposes launch/attach, breakpoints, stepping, and compound state snapshots, with documented Python/C/JavaScript adapters. This makes it a candidate, not a proven best debugger MCP. `AlDanial/tdb` is another candidate if a shared human/agent debugger is valuable. [S14, S15]

Keep GDB batch commands, core inspection and debugpy available regardless. Prefer a small structured interface returning the stop reason, relevant stack frames, selected variables, and artifact references. A compound snapshot can replace several conversational round trips. Package modern DAP adapters separately: the GDB bundled with Rocky 8 may not implement the adapter expected by a new server. Test C and Python explicitly.

Debug expression evaluation can execute program code. It should inherit the debug target's allowed scope; inspection and mutation require different grants. Stateful sessions need lifecycle ownership, cancellation, port allocation, and cleanup.

### Database and project-state access

For routine work on the target project, named queries such as entity lookup, provenance traversal, relationship inspection, and ingestion-state inspection are likely more effective than repeatedly reconstructing schemas and SQL. This is an engineering recommendation consistent with the existing metadata-query capability. Keep the adapter over canonical data and return IDs and provenance; do not create another authoritative store.

DBHub is a compact general database MCP candidate with schema exploration and SQL execution. It is optional if existing project CLI/API access already works. [S16]

One concrete selection issue: DBHub's June 2026 advisory lists a read-only enforcement flaw affecting versions below 0.22.6, patched in 0.22.6. Choose a currently reviewed release including that fix, not necessarily 0.22.6 itself. Use database-level restricted credentials and functional denial checks; a tool annotation or keyword filter is insufficient evidence of read-only enforcement. [S17]

## 4. Linux utilities and specialist reserve

The following is a **proposed procurement/package inventory**, not a list of installed or fully qualified versions. Existing equivalents remain preferred. Use native binaries where reliable; use CLI shims into pinned containers for incompatible userlands. MCP adds value for semantic/stateful interaction, not for every executable.

| Group | Carry and make discoverable | Typical task |
|---|---|---|
| Core inspection | Git, ripgrep, fd, jq, one explicitly identified yq implementation, find/sed/awk/coreutils, diff/patch, file, less | Source/config/history and structured data. |
| Archives and transfer | tar, gzip/xz/zstd, unzip/zip, rsync, OpenSSH client, curl, checksum utilities | Controlled staging, fixtures and package inspection. |
| Structural/source maps | ast-grep, Universal Ctags; cscope if useful for legacy C; existing Python repo explorer | Syntax patterns, file outlines, lightweight fallback navigation. |
| Native build | Project GCC plus qualified Clang/LLVM, make, CMake, Ninja, pkg-config, ccache, Bear where needed | Build, compilation DB and iterative diagnostics. |
| C quality | clang-tidy, clang-format, chosen static analyzer, ASan/UBSan runtimes, coverage tooling | Actionable diagnostics and regressions. |
| Runtime diagnosis | GDB, LLDB where selected, strace, ltrace, procps, util-linux, iproute2, lsof | Processes, syscalls, file descriptors and cores. |
| Performance | perf, Valgrind, heaptrack if compatible, Python profiling tools | CPU/memory investigation. Kernel/permission constraints are part of qualification. |
| Python | Separate project/tool interpreters, uv/pip, pytest and actual plugins, coverage, Ruff, one primary type checker, debugpy | Repeatable tests, types and debugger feedback. |
| Frontend | Pinned Node/package manager, TypeScript, project lint/format/unit/component tools, Playwright CLI/test/browser | Builds, UI behavior and browser evidence. |
| Binary inspection | binutils or LLVM equivalents: readelf, objdump, nm, strings, addr2line; elfutils, patchelf, checksec, xxd/hexdump | ELF identity, symbols, protections and linkage. |
| RE Python libraries | Existing cryptography, pyelftools, pefile, python-magic, Capstone; YARA bindings if used | Structured binary/artifact analysis. |
| SQL/data inspection | sqlite3, appropriate database clients, Python data tools already used, optional DuckDB for large local tabular artifacts | Canonical state and bounded artifact queries. |
| Documents | man/info pages, pandoc, Poppler tools, appropriate HTML/Markdown/document parsers | Read contracts and imported references. |
| Security checks | Existing Semgrep/rules, secrets scanner, SBOM tooling, selected vulnerability scanner/database | Local deterministic review evidence. |
| Fuzzing reserve | AFL++, libFuzzer, corpora/dictionaries, Python fuzzing/property tooling if used | Parsers and input-sensitive native defects. |
| Advanced RE reserve | QEMU/Unicorn, Frida, pwntools, angr/Z3, binary-diff tools; rr only after host qualification | Emulation, instrumentation, constraints and specialized diagnosis. |

ast-grep currently documents structural search/rewrite and an outline command; qualify syntax/grammar coverage on your source languages. [S18] LLVM's clang-tidy and libFuzzer require appropriate compilation/instrumentation context and matching runtimes; installing their binaries alone is insufficient. [S19, S20]

The advanced reserve is deliberately not an always-running dependency. Preserve existing SPT fuzzing/symbolic/CodeQL/SBOM assets instead of reimporting duplicate stacks. Carry optional archives if storage permits, but label untested entries unavailable for mandatory gates.

For commercial/license-bound tools, use the organization's existing entitlement and redistribution process. For offline security scanners, ship the selected rules/database and record its freshness; do not let a disabled network update masquerade as an up-to-date assessment. For example, Grype documents offline database handling. [S21]

## 5. Harness-native features to exploit

Use native features as execution primitives under AEW. They do not acquire authority to approve plans, integrate work, or mark completion. A useful adapter vocabulary remains `USE_NATIVE`, `USE_NATIVE_BOUNDED`, `AEW_MANAGED`, `DISABLED`, and `UNSUPPORTED`.

### OpenCode

| Feature | Recommended use | Boundary / qualification |
|---|---|---|
| Built-in read/search/edit/patch/shell | Baseline operations, bounded reads and existing tool commands | Avoid duplicate generic MCP wrappers. [S04] |
| Explicit LSP configuration and experimental navigation | Semantics where benchmarked useful | Preinstall servers; measure stale state, memory and latency. [S03, S04] |
| On-demand skills | Language/domain guidance and capability recipes | Keep names/descriptions concise; full instructions load when needed. [S22] |
| Agent models/options and per-agent permissions | Realize AEW role grants and deliberate model/effort selection | Native role labels do not enforce OS isolation. [S23] |
| MCP server enablement and tool/agent filtering | Expose relevant providers to a role | Verify filtering actually removes irrelevant schemas from model requests. [S24] |
| Plugins and tool lifecycle hooks | Artifact capture, deterministic checks, health/freshness signals | Prefer one owner for each interception point. [S25] |
| Compaction auto/prune/reserved controls | Benchmark total-cost/context tradeoffs | Preserve contracts/evidence via AEW artifacts, not only a summary. [S26] |
| Experimental compaction hook | Inject concise canonical work/plan/evidence references | Version-gate it; do not inject the entire project state. [S25] |
| Server, SDK and event stream | Programmatic session start, abort, status, tool health and UI attachment | Can reduce launcher/TUI duplication; test against the existing launcher wrapper. [S27, S28] |
| Structured output | Role reports that can be schema-validated | Valid JSON does not prove factual correctness. [S28] |
| Session export/import and usage statistics | Debugging, reproducibility and cost accounting | Preserve original records and effective configuration. [S29] |

The official MCP page explicitly warns that servers add context overhead. Do not infer dynamic schema discovery merely from MCP support. Per-agent denial and server filtering need a request-level measurement. [S24]

### Codex

| Feature | Recommended use | Boundary / qualification |
|---|---|---|
| App-server | Thin AEW/launcher-wrapper integration using structured session/turn events | Pin protocol; use supported start/resume/interrupt surfaces. Fresh independent review starts with fresh context, not copied flawed history. [S30] |
| Noninteractive `codex exec` | Simple bounded jobs with JSONL events and final-output schema | Lower integration effort where live interactive control is unnecessary. [S31] |
| MCP allow/deny lists, required servers, timeouts, output budgets | Deliberate role interfaces and early detection of missing required providers | Budgeted output must have a full artifact/retrieval path. [S32] |
| MCP server instructions | Short server-wide workflow guidance | Current docs emphasize a self-contained first 512 characters. [S32] |
| Lifecycle hooks | Session/compaction recovery and tool evidence capture | Current hook trust and event coverage must be exercised; transcript formats are not stable APIs. [S33] |
| Linux sandbox and permission profiles | Protect execution scope and evaluation boundaries | Validate actual Rocky/kernel/container behavior. MCP/browser/model traffic has separate controls. [S34, S35] |
| Skills and repository instruction entry points | Reuse portable domain guidance | Keep AEW authority and evidence locations explicit. |
| Native review and bounded subagents | Execute assigned review/investigation work where the adapter supports it | AEW retains dispatch, freshness and completion decisions. |
| Provider/reasoning/verbosity configuration | Record actual GPT-5.4 configuration through the internal endpoint | A model name is not evidence that the gateway forwards every option. [S36] |

Codex's Linux sandbox uses platform/kernel facilities, including bubblewrap/seccomp on documented paths. Test it on the real host and inside the chosen runtime. A permissive container fallback must not silently become the production configuration. Crucially, native command sandboxing is not a blanket sandbox around remote MCP services. [S34, S35]

For startup integration, prefer an attachable service interface where your existing wrapper can provide one, rather than forcing every user through another launcher. OpenCode SDK can connect to an existing server; Codex app-server exposes structured threads/turns. This is a design option to assess against the existing launcher wrapper, not a claim that it is already integrated. [S28, S30]

### GPT-5.4/API features: verify separately from harness features

The Responses API documents native tool search for GPT-5.4 and later, with deferred functions/MCP definitions. This is a real opportunity for progressive disclosure. It does **not** prove that your selected OpenCode/Codex release and gateway expose it end to end. Namespace/server summaries still occupy context. [S37]

For each adapter, record support for tool search, image input, reasoning options, structured output, interruption, compaction, usage fields, and caching. Inspect one real sanitized request/result per feature. Keep local MCP execution local; an API-side remote-MCP facility is not automatically a route to an airgapped localhost service.

Current Codex configuration documentation rejects some retired tool-search switches. Do not paste historical feature flags into a new release; detect the pinned binary's actual schema. [S38]

## 6. Performance per token: where to spend engineering effort

My priority order is:

1. Correct source/runtime/docs evidence on demand.
2. Small role-specific capability and skill catalogs.
3. Deterministic structured output reduction with recoverable artifacts.
4. Stable reusable prompt/tool definitions and measured caching.
5. Build/index/service reuse keyed to the actual candidate.
6. Optional output/context tools, then stylistic compression.

This ordering is an engineering hypothesis for your workload, not a benchmark result. Short answers are not automatically cheaper successful work: they can cause extra tool calls, retries or missed conditions.

### Compact interface, broad installed capability

Reuse AEW's existing discovery layers. At startup show capability names, what problems they solve, current limitations, and where to obtain details. Resolve provider/schema details only when relevant. Preserve `AVAILABLE ≠ AUTHORIZED ≠ ACTIVE`.

FastMCP now documents search transforms with a two-tool search/call interface, including lexical BM25 discovery. It is a practical fallback where a harness cannot defer schemas natively. The documentation is explicit that hiding tools from discovery does not restrict access: enforce role authorization inside the actual execution path too. Do not stack two discovery systems without evidence that both help. [S39]

Use separate profiles such as source investigation, C implementation, Python implementation, frontend verification, binary RE, and specialist security analysis. Resolve missing required capabilities before dispatch. Profiles should support tasks that cross domains rather than rigidly disabling everything outside one language.

### Output evidence contract

For expensive/noisy actions, return a small structured record containing:

- Operation, provider/version, target/candidate identity and timestamps.
- Exit status and completion/readiness state.
- Test collection/execution/pass/fail/skip counts where applicable.
- Relevant failures/diagnostics and their locations.
- Total result count, truncation/pagination state and limitations.
- Full artifact reference/hash and an expansion/query path.

Store stdout/stderr, traces, screenshots, and machine reports outside conversational context. Paginate semantic and SQL results. Batch bounded independent queries when it avoids round trips; preserve per-item failure rather than silently dropping it.

A missing match means “not found within this query's scope and current index,” not “does not exist.” A successful wrapper exit is not proof the underlying tests executed. Protected acceptance and original intent must survive output reduction, following the plan-assurance work.

### RTK, context-mode, and Caveman

RTK filters common CLI output and offers raw passthrough/recovery-related paths. Context-mode indexes output and provides context/continuity integrations, including an OpenCode native plugin path. Both are worth controlled comparison when verbose logs are an observed cost. Upstream output-reduction percentages are not evidence of equivalent end-to-end GPT-5.4 cost savings. [S40, S41]

Start with one output owner. Test exit status, warnings, skipped tests, conflicting diagnostics, long-stack traces, and recovery of omitted output. Do not route an already compact semantic response through multiple lossy reducers. Context-mode's execution environment also should not be assumed equivalent to an OS security sandbox.

I would keep Caveman-style prose compression below these changes in priority. Exact requirements, negation, error messages and evidence should retain their meaning. A deterministic short report can save tokens without teaching the agent to compress away engineering constraints.

### Caching and runtime reuse

OpenAI documents cache reuse around matching rendered prefixes. Keep stable instruction/tool blocks stable where practical, append changing ticket/evidence data, and inspect actual cached-input usage. Gateway transformations, tool activation, effort changes and compaction can affect reuse. Do not apply later-model-only caching options to GPT-5.4 or assume public pricing applies internally. [S42]

Reuse persistent language servers, documentation indexes and graph services where they demonstrably reduce startup costs. Reuse build/test caches only with correct source/compiler/configuration keys. A reused result from another dirty candidate is not valid evidence.

## 7. Offline bundle and qualification

Use one versioned setup/source repository and separate runtime modules. Do not make every agent depend on one giant image.

| Module | Contents |
|---|---|
| Core agent runtime | Pinned harnesses, adapter configuration, approved endpoint integration, shell/tool utilities. |
| Native C profile | Target-compatible compiler/headers/build tooling; semantic/debug/diagnostic runtimes. |
| Python profile | Tool interpreter, wheelhouse, project dependencies, tests/types/debugger. |
| Frontend profile | Node packages, build/test tools, matched browsers, fonts and assets. |
| Code intelligence | Serena/LSP dependencies, GitNexus parsers/native bindings/index storage. |
| Docs | Original and normalized corpora, search indexes, optional local model assets. |
| Binary/security profile | Ghidra/JDK/bridge, staged binaries/projects, analysis rules/libraries. |
| Specialist reserve | Qualified optional emulation/fuzzing/symbolic/debug archives and recipes. |

Each release records source commit/version, image digest or payload hash, architecture/userland, dependencies, launch command, state paths, supported capabilities, network needs, limitations, doctor fixture and source/license metadata. Exact version pins must come from qualification; this report intentionally supplies no fictitious tested lockfile.

Keep tool userspace separate from the target project's deployment ABI. A modern container can run on Rocky 8 only when host kernel/runtime requirements permit; extracting its native binaries onto the host introduces different libc/library constraints. Test both targets separately.

Include transitive runtime assets: Python interpreters/wheels/build backends, Node lifecycle binaries, native parser/database extensions, LSP packages, browser binaries/fonts, JDK/plugins, embedding/tokenizer assets, scanner databases, fixture datasets, and documentation. uv cache contents are versioned implementation state; a deliberate wheel/source inventory is more reproducible than copying a warm cache. [S43]

Playwright specifically requires compatible package/browser versions; qualify the application test package against the shipped browser image. [S44]

For OpenCode, documented controls include disabling LSP downloads and model metadata fetching; also configure autoupdate and sharing deliberately in the pinned release. Preinstall plugin dependencies because plugin startup can otherwise trigger package acquisition. [S03, S25, S26, S29]

### Cold-start acceptance

Use a clean representative Rocky target, fresh runtime user and empty accidental caches. Deny public egress while preserving only approved internal routes. Separately test local-only tool operation with networking disabled and the approved model round trip with internal access enabled.

Release evidence should cover:

1. Load/import images and payloads without public registries or installers.
2. Resolve every required capability and return a meaningful fixture result.
3. Build/test C, Python and frontend samples from transferred artifacts.
4. Resolve known cross-file symbols and detect stale index after an uncommitted edit.
5. Query versioned docs without public or unapproved embedding requests.
6. Launch browser locally and capture behavior/trace evidence.
7. Stage/hash/analyze an approved binary, restart, and recover its project/index identity.
8. Start a debugger session, inspect the correct target, cancel and reclaim resources.
9. Run protected verification from the correct candidate/oracle separation.
10. Verify host ownership, mounts, persistence and replacement of containers.
11. Reconnect/resume harness sessions and restore AEW state references.
12. Record effective gateway/model options, usage and native feature support.

Health is more than a listening port. Distinguish process alive, protocol connected, data loaded, analysis complete and query semantically correct. Required-provider failure should block only tasks that require it; an optional index must not stop unrelated work.

Ship enough inputs for offline execution. If offline rebuilding is required too, additionally transfer base/build images, source/package archives and toolchain build dependencies. The two promises must remain distinct.

## 8. Measure the combinations before calling them optimal

Preserve the M3 baseline, model/gateway settings, accepted skill versions and independent acceptance evaluator. Change one substantial variable per initial comparison; compare bundles only after individual candidates establish value.

| Task family | Candidate comparison | Independent outcome |
|---|---|---|
| C lifetime/bounds defect | Baseline vs sanitizer/debugger feedback | Correct defect and fix, working reproducer, no unintended ABI change. |
| Cross-file C change | Exact/AST baseline vs LSP vs Serena | Correct owners/references, macro/build configuration coverage. |
| Python service/state defect | Baseline vs debugger and canonical queries | Correct transaction/exception behavior and persisted state. |
| C/Python/TS cross-layer change | Baseline vs GitNexus | Relevant impacts found; false edges and unnecessary edits counted. |
| Version-specific dependency task | Baseline vs local docs | Answer matches actual version/API and passes runtime check. |
| Frontend behavior | Playwright CLI vs MCP | Observable intended behavior and regression evidence. |
| UI performance | Existing tools vs DevTools candidate | Causal trace and measured change under controlled conditions. |
| Binary triage | Existing bridge vs PyGhidra MCP | Known symbols/xrefs/behavior identified with binary provenance. |
| Noisy build/test failure | Raw vs structured reducer vs RTK/context-mode | Same relevant failures, status and executed-test information. |
| False stakeholder diagnosis | M3 plus tools and plan assurance | Original intent preserved; no “success” by changing the oracle. |
| Long-ticket interruption | Native continuity vs added context tooling | Correct plan revision, candidate and next action recovered. |
| Cold offline target | Entire proposed bundle | No missing assets or surprise downloads. |

Use multiple representative fixtures, fresh sessions, balanced run order and repeated consequential tasks. Start with a small number of repeats to expose large effects; do not treat it as a statistically conclusive ranking. Spend additional runs only where they can change a selection decision.

Record correct completion, missed/false findings, unnecessary edits, retries, operator intervention, wall time, model reasoning/output tokens, cached/uncached input tokens, indexing/embedding cost, and service startup cost. Use actual internal rates if reporting money.

Primary selection rule: acceptable correctness and reliability first, then lower total cost/time per accepted completion. Include failed runs and retries in cost. Tool-output reduction alone is a diagnostic metric, not the optimization target. If the gateway omits fields, report missing accounting rather than estimating it as fact.

## 9. Suggested AEW implementation grouping

Translate these into the canonical Work Graph after reconciling existing Tickets; IDs and schema are deliberately left to the current implementation.

| Proposed Story | Initial scope | Exit evidence |
|---|---|---|
| Capability inventory and doctor | Actual providers, dependencies, roles, health/freshness and gaps | No required capability silently absent; query-level fixtures. |
| Semantic/source intelligence | Compile DB, ast-grep, native LSP/Serena comparison; GitNexus remediation | Useful source navigation and impact evidence on real project slices. |
| Offline knowledge | Versioned docs/package source packs, lexical retrieval and optional docs provider | Correct cited answers with no external services. |
| Runtime evidence | Build/test reports, debugger pilot, canonical state queries | Relevant failure state found and full evidence recoverable. |
| Frontend evidence | Browser profile, existing tests, DevTools experiment | UI behavior and performance diagnosed locally. |
| RE evidence | Existing bridge readiness, artifact staging; alternative comparison | Persistent attributable analysis and bounded tool surface. |
| Harness integration | Supported native features, wrapper attachment, structured events and role settings | Both adapters invoke the same capability contracts without another authority. |
| Context/cost evaluation | Catalog/output budgets, caching observation, optional reducer comparison | Fewer wasted tokens/retries without correctness loss. |
| Release qualification | Offline archives, clean-host drill, recovery and reserve | Complete declared workload coverage on the target. |

Start qualification before phase 6, because tool availability can improve M4/M5 work and reveal packaging problems early. Phase 6 should assemble a proven release rather than discover its dependency gaps.

## 10. Inputs that would refine final provider selection

Useful next inputs are the current sanitized SPT tool/provider manifest, current AEW capability/discovery and harness-adapter docs, harness versions, launcher-wrapper integration interface, hardware/container/kernel details, project lockfiles/build configuration, and a few representative Tickets with token/trace evidence. Credentials and private data are unnecessary for the inventory.

No conclusion in this report depends on obtaining those inputs before beginning inventory and packaging. They determine final pins, resource sizing, overlap removal and which benchmark candidates earn defaults.

## Primary sources

Retrieved October 1, 2026. Upstream documentation and main branches can change. Product docs establish advertised capabilities; this report's ranking, architecture, packaging and evaluation choices are engineering recommendations. They do not establish measured GPT-5.4 improvement.

- S01 — [Serena](https://github.com/oraios/serena)
- S02 — [clangd setup](https://clangd.llvm.org/installation)
- S03 — [OpenCode LSP](https://opencode.ai/docs/lsp/)
- S04 — [OpenCode tools](https://opencode.ai/docs/tools/)
- S05 — [GitNexus](https://github.com/abhigyanpatwari/GitNexus)
- S06 — [Grounded Docs](https://github.com/arabold/docs-mcp-server)
- S07 — [Grounded Docs local/versioned usage](https://github.com/arabold/docs-mcp-server/blob/main/docs/guides/basic-usage.md)
- S08 — [Context7 documented API](https://github.com/upstash/context7/blob/master/docs/api-guide.mdx) and [service setup](https://github.com/upstash/context7)
- S09 — [Playwright CLI](https://github.com/microsoft/playwright-cli)
- S10 — [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- S11 — [Chrome DevTools for agents](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- S12 — [GhidraMCP](https://github.com/LaurieWired/GhidraMCP)
- S13 — [PyGhidra MCP](https://github.com/clearbluejar/pyghidra-mcp)
- S14 — [DAP-MCP](https://github.com/ctagard/dap-mcp)
- S15 — [tdb debugger/MCP](https://github.com/AlDanial/tdb)
- S16 — [DBHub](https://github.com/bytebase/dbhub)
- S17 — [DBHub read-only advisory](https://github.com/bytebase/dbhub/security/advisories/GHSA-mwwr-p57h-56pf)
- S18 — [ast-grep CLI](https://ast-grep.github.io/reference/cli) and [outline](https://ast-grep.github.io/reference/cli/outline)
- S19 — [clang-tidy](https://clang.llvm.org/extra/clang-tidy/)
- S20 — [LLVM libFuzzer](https://llvm.org/docs/LibFuzzer.html)
- S21 — [Grype local database import](https://oss.anchore.com/docs/reference/grype/cli/) and [database freshness](https://oss.anchore.com/docs/guides/vulnerability/database/)
- S22 — [OpenCode skills](https://opencode.ai/docs/skills/)
- S23 — [OpenCode agents](https://opencode.ai/docs/agents/)
- S24 — [OpenCode MCP](https://opencode.ai/docs/mcp-servers/)
- S25 — [OpenCode plugins](https://opencode.ai/docs/plugins/)
- S26 — [OpenCode configuration](https://opencode.ai/docs/config/)
- S27 — [OpenCode server](https://opencode.ai/docs/server/)
- S28 — [OpenCode SDK](https://opencode.ai/docs/sdk/)
- S29 — [OpenCode CLI](https://opencode.ai/docs/cli/)
- S30 — [Codex app-server](https://learn.chatgpt.com/docs/app-server)
- S31 — [Codex noninteractive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- S32 — [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)
- S33 — [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- S34 — [Codex permissions and enforcement boundaries](https://learn.chatgpt.com/docs/permissions)
- S35 — [Codex sandbox](https://learn.chatgpt.com/docs/sandboxing)
- S36 — [Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)
- S37 — [OpenAI API tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)
- S38 — [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- S39 — [FastMCP search transforms](https://gofastmcp.com/servers/transforms/tool-search)
- S40 — [RTK](https://github.com/rtk-ai/rtk)
- S41 — [context-mode](https://github.com/mksglu/context-mode)
- S42 — [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- S43 — [uv cache semantics](https://docs.astral.sh/uv/concepts/cache/)
- S44 — [Playwright Docker/version compatibility](https://playwright.dev/docs/docker)
