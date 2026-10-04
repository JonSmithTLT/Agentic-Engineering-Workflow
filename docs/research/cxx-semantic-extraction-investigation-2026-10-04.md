# S1 — C/C++ semantic extraction from `compile_commands.json` with Clang tooling on Rocky 8: what is compiler-known, what is inference, what is unsupported

- **Status:** investigation with live probes, independent architecture review, 2026-10-04 (semantic-map thread S1 of the designer's second brief). Not governing. Input to the semantic-extension contract (S2), the query surface (S3), incremental freshness (S4) and the architecture-map bridge (S5), each in `S2-S5-semantic-extension-framework.md`.
- **Where it ran:** the operator's Rocky Linux 8.10 VM, Clang 21.1.8 (AppStream `clang`, `clang-tools-extra`, `llvm`), CMake 3.26, the `libclang` 18 Python wheel in the review venv (the `python3-clang` rpm targets the system Python 3.6), under `~/aew-review/sem`. Targets: **zlib 1.3.1** (34 TUs, the control, every edge hand-checkable) and **curl 8.11.1** configured without TLS/compression (1,379 TUs with tests; 434 library TUs over 169 source files, compiled for several targets), both at `-O0 -g`. Probes: `repro/sem/cxx_extract_probe.py` (extraction), `repro/sem/cxx_oracle.py` (truth from the build), `repro/sem/cxx_query.py` (agent queries), `repro/sem/header_fanout.py` (dependency fan-out); outputs beside them (`*.oracle.json`, `*.out.txt`). Everything below marked **[probe]** is read from those; **[doc]** is tool documentation or source read; **[inf]** inference; **[rec]** recommendation; **[hyp]** open.
- **Headline.** Parsing each translation unit with its own compile command through libclang reproduces the compiler's facts almost exactly: 100% of function definitions and their linkage, 100% of the preprocessor's include set, 99.4–99.5% of direct call edges, with every discrepancy in three named categories. The boundary is sharp and it is not where "static analysis" folklore puts it: the AST is reliable about *declared* structure and *direct* calls; it cannot see *compiler-synthesized* calls (struct copies become `memcpy`), *constant-folded* branches, or *who calls through a pointer*. Dispatch tables in global initializers (curl's `Curl_cftype` vtables: 754 references in the library) are where C's indirection lives and a body-only call graph misses all of them; walking initializers recovers the "holds a pointer to" edges, which is as far as statics go.

## 1. Method [probe design, documented]

**Extraction.** For each entry of `compile_commands.json`: libclang parses the source with the entry's arguments (minus compiler, `-c`, `-o`, the file; plus the installed Clang's `-resource-dir`), with the detailed preprocessing record on. The probe records diagnostics; every include at every depth, classified project / generated (under the build directory) / system; every function, file-scope variable, record, enum, typedef and macro declared in project or generated files, with USR, definition-or-declaration, linkage and storage class; for each function *defined* in the TU, its call expressions, resolved to a `FUNCTION_DECL` (direct), to a variable, parameter or field (indirect, "through X"), or to nothing (unresolved); function references outside call position (address taken); function references inside file-scope initializers (dispatch tables); macro instantiations in the main file; the `-D` defines. A callee is recorded by source name and by *emitted symbol* (`mangled_name`), because glibc renames through asm labels (`fopen` → `fopen64` under `_FILE_OFFSET_BITS=64`).

**Oracle.** Four truths the build already holds, none from our parse: `llvm-nm` on the TU's object (defined text symbols and their linkage; undefined symbols); `llvm-objdump -d -r` (every `call` instruction per function, with its relocation target, or `call *reg` for indirect); `clang -M` (the header set the preprocessor read); `clang -dM -E` (the macro definitions in effect). At `-O0` one C call is one call instruction, so objdump is the compiler's own call graph for the TU.

**Three probe iterations** were needed, each a finding in itself: (1) `referenced` is `None` for a parenthesized callee (`(gzgetc)(g)`), so the callee expression must be searched; (2) emitted symbol names differ from source names (asm labels); (3) C dispatch tables live in global initializers, not function bodies. Each is now in the extractor.

## 2. Results [probe]

| Fact | zlib (34 TUs) | curl lib (171 TUs with objects) | Verdict |
|---|---|---|---|
| Function definitions: nm vs extracted | 338 / 338, 0 missing, 0 extra | 1,680 / 1,685, 0 missing, 5 extra (all internal linkage: unused `static` functions the compiler did not emit) | **compiler-known** |
| Linkage (external vs internal) | 0 disagreements | 0 disagreements | **compiler-known** |
| Direct call edges (per caller, distinct callees) | objdump 836, extracted 844; agree 832, **missing 0, extra 8** | objdump 4,766, extracted 4,761; agree 4,706, **missing 20, extra 15** | compiler-known except §3 categories |
| Indirect call sites | 92 / 92 | 1,027 / 1,027 | **compiler-known that they are indirect**; the target is not |
| Undefined symbols explained by extraction | 262 / 262 | 2,231, 8 unexplained (all compiler-synthesized `memcpy`/`memset`) | compiler-known |
| Includes (all depths) vs `clang -M` | 2,588, 0 missing, 0 extra | 28,178, 0 missing, 2 extra | **compiler-known** |
| Macro definitions vs `clang -dM` | 49,784 in effect; 49,955 distinct names seen (171 later `#undef`'d) | 472,608; 473,481 distinct | compiler-known; "visible" and "in effect" differ |
| Dispatch-table references (file-scope initializers) | 20 | 754 (937 across all 1,379 TUs) | **static fact about where pointers are stored**; not a call edge |
| Address taken inside bodies | 16 | 494 | same |
| Diagnostics | 0 errors in every TU | 0 errors in every TU; 1 of 1,379 TUs failed to load (`$BUILD/tests/libtest/lib1521.c`, a 4 MB generated test) | parse quality is measurable per TU |
| Time per TU (parse / Python walk) | 16 / 52 ms | 28 / 95 ms (117 ms over all 1,379) | 2.5 s for zlib; 63 s for the curl library; 241 s for all 1,379 TUs, single core |

Generated headers: curl's `curl_config.h` is the one generated header and every library TU reads it; the probe classifies it from the build directory, and its macro definitions are in each TU's visible set. Build defines: `-D` flags per TU (`BUILDING_LIBCURL`, `CURL_HIDDEN_SYMBOLS`, `HAVE_CONFIG_H`, `_GNU_SOURCE`); the probe lists them per TU and per symbol (`defines-for`).

**Coverage reporting** [probe]: zlib rebuilt with `-fprofile-instr-generate -fcoverage-mapping`, `example` and a `minigzip` round trip run, `llvm-profdata merge`, `llvm-cov export` (JSON): 163 functions, 108 executed, 55 never, lines 56.7%, regions 55.0%, one record per function with the same names the extraction uses (statics as `file.c:name`). Two pitfalls, both tooling facts: a shared library's functions appear only when its object is passed (`-object libz.so`), and two processes writing one `LLVM_PROFILE_FILE` corrupt it (use `%p`). Coverage joins to the symbol table by name; it is build-and-run-specific evidence, not a property of the code.

## 3. The boundary, exactly [probe → inference]

Every discrepancy the oracle found falls into one of these. Nothing else occurred in 5,600 edges.

| Category | Direction | Example | What knows the truth |
|---|---|---|---|
| **Compiler-synthesized calls.** Struct assignment, array initialization and large copies become `memcpy`/`memset` calls the source never wrote. | missing from AST (20 of 20 curl misses; the 8 unexplained undefined symbols) | `init_thread_sync_data` copies a struct → `call memcpy` | codegen only |
| **Builtin-recognized libc calls.** `memcpy`, `strlen`, `memset` with constant small sizes are inlined even at `-O0`; `__builtin_*` are expanded. | extra in AST (10 of 15 curl extras) | `on_resp_header → strlen` | codegen only |
| **Constant-folded branches.** A call under a condition the front end can evaluate (`sizeof(int) == sizeof(z_off64_t) && …`, `sizeof(uInt) > 2`) is in the AST and never emitted. | extra in AST (8 of 8 zlib extras; 5 curl extras) | `GT_OFF()` → `gz_intmax()` | codegen; the AST can flag `sizeof`-only conditions but not evaluate every one |
| **Asm-label renames.** The emitted symbol differs from the source name. | would be both | `fopen` → `fopen64` | the AST does know (`mangled_name`); the extractor must use it |
| **Unused static functions.** Defined in source, never emitted. | extra definitions (5 curl) | `curl_simple_lock_lock` | nm; harmless, and the AST can say "static, unreferenced" |
| **Indirect calls.** The site is known, the target is not. | neither | `(*cf->cft->do_cntrl)(…)` | nothing static; the probe names the pointer (`through FIELD_DECL do_cntrl`) |
| **Dispatch tables.** Where function pointers are stored. | invisible to a body-only walk | `Curl_cft_http_proxy = { …, Curl_cf_def_cntrl, … }` | the AST (initializers); recovered as `holds_pointer_to`, never as `calls` |
| **Macro-mediated calls.** A call written inside a macro expands in the TU. | none missed | `gzgetc()` | the AST (expansion location); the extractor sees the call; the *spelling* location is a separate fact worth recording |
| **Configuration.** `#if` branches not taken under this build's defines are not in the AST at all. | not an error, a scope | curl without TLS has no TLS call edges | the compile database: the map is of **this build**, and must say so |

[inf] Three tiers follow, and they are what the S2 contract has to carry per fact:

1. **Compiler-known fact**: declared symbols, definitions, linkage, includes, macros in effect, build defines, direct call *sites* and their resolved callee, indirect call *sites* and the pointer they go through, where function pointers are stored, coverage from a run. Verified against the object files at 99.4–100%.
2. **Partial static inference**: "the full set of callers of X" (complete for direct calls; incomplete whenever X's address is taken anywhere), "what X calls" (complete for direct calls; `memcpy`-class and constant-folded exceptions), "dead code" (unused statics are known; dead branches are not).
3. **Unsupported / ambiguous**: who calls through a given pointer; behaviour under a configuration that was not built; anything about a TU that did not parse (1 of 1,379 here) or parsed with errors (0 here, but a header-less checkout would produce many: the extractor marks such TUs `partial` and the contract must propagate that).

## 4. Facts about scale and shape that bear on S2–S4 [probe]

- **Per-TU records are 100× redundant.** The curl library extraction is 134 MB of JSON because every TU re-records the project headers' symbols it sees: 393,968 symbol records for **3,866 distinct USRs** (231k of the records are macros). The artifact must be a deduplicated symbol table (by USR) plus per-TU membership and per-TU facts (defines, includes, diagnostics), not per-TU dumps. The direct-edge list alone is 567 KB, about 140k tokens, which is also too large to put in any pack (S3).
- **The same source file is several TUs.** 169 curl library files produce 434 compile-database entries (libcurl, libcurlu for tests, …), each with its own defines. Facts are per TU; a query answer about a *file* must say which configuration it is quoting.
- **Fan-out** (`clang-scan-deps`, 0.75 s for 434 TUs): 158 project headers, median fan-out 21 TUs, mean 83, p90 192; six headers (`curl_setup.h`, `curl_config.h`, `curl_setup_once.h`, `system.h`, `functypes.h`, `curl_ctype.h`) reach all 434; 87 headers reach 50 or fewer; 116 of 198 system headers reach every TU. Headers per TU: median 141, max 277. This is the input-sensitivity data S4 needs: most header edits invalidate a few percent of TUs; a handful invalidate everything.
- **Cost model.** Parse 16–29 ms per TU, AST walk in Python 52–117 ms (the walk dominates and is the part a C++ or Rust extractor would make cheap); `clang-scan-deps` is 2 ms per TU. Re-extracting after a median header edit (21 TUs) is about 3 s single-core; after a `curl_setup.h` edit, about 60 s; parallel across cores it divides accordingly.

## 5. Recommendations for the design [rec]

1. **Use libclang (or clangd's index) as the extractor; do not write a parser.** The compiler's own front end under the compile database is the only thing that gets includes, macros and definitions exactly right, and it is 30 ms per TU. `clangd-indexer` is not shipped in EL8's `clang-tools-extra` (checked), so the Python bindings or a small C++ tool are the available routes; the probe's bindings-based extractor is sufficient for v1 and its walk is the only slow part.
2. **Record three edge kinds, never one.** `calls` (direct, compiler-known), `calls_through` (indirect site naming the pointer), `holds_pointer_to` (initializer or body address-taken). An agent asking "who calls X" gets the direct set *and* the holders, labelled; it never gets a merged list that pretends completeness.
3. **Label the `memcpy` class.** Edges to libc memory/string functions and `__builtin_*` are marked `codegen-variable`; they are the one place the AST and the object disagree in both directions.
4. **Every fact carries its TU and that TU's configuration identity** (compile-command hash, defines, generated-header hashes), because the map is of a build, and curl without TLS is a different program from curl with it.
5. **Mark parse quality per TU** (`partial` with the diagnostic count) and propagate it to every answer drawn from that TU. A checkout without system headers is the common failure, and it is detectable.
6. **Coverage is an optional overlay** joined by symbol name, bound to a run (binary, profile, inputs), not part of the static map.

## 6. Not shown [hyp]

- C++ (templates, overloads, inline methods, ODR): the extractor handles `mangled_name` and USRs, but no C++ project was run; template instantiations and implicit members will add a fourth category ("compiler-instantiated"). The designer's list named C/C++; C is measured, C++ is not.
- Optimized builds: at `-O2` the objdump oracle stops being the truth about the source (inlining removes call instructions), which is why the probe used `-O0`; a map built from an optimized compile database still parses the same AST, so extraction is unaffected, only the oracle is.
- Scale beyond 1,400 TUs: linear by construction (one TU at a time); S7 extrapolates.
- Whether `clang-scan-deps`' dependency sets equal libclang's include sets for every TU (they agreed on counts; not diffed path by path).
