# S1b — The C++ check: does the semantic-extension contract survive what C does not stress?

- **Status:** probed fact and verdict, independent architecture review, 2026-10-05. The designer's acceptance question: *can we represent C++ accurately with the same identity, provenance, coverage, freshness, evidence and relation model, without language-specific hacks that break the generic extension contract?* Target: **fmt 11.0.2** (header-heavy, template-heavy; 49 TUs including its gtest-based tests; Clang 21, Debug) on the Rocky 8 VM, with the S1 probes extended for C++ (`repro/sem/cxx_extract_probe.py`, `cxx_oracle.py`); outputs `repro/sem/fmt.oracle.json`, `fmt.extraction.out.txt`, `fmt.oracle.out.txt`. zlib was re-run after every change and still agrees with its objects (338/338 definitions, 832 of 836 edges), so the C++ additions did not disturb C.
- **Verdict.** **Yes for the representation, with two shared additions and one extractor-identity decision; no hacks.** Identity (USR), provenance (unit:line), coverage (per-unit quality), freshness (per-unit input set), evidence (locator) and the relation model all hold for namespaces, overloads, methods, inline/ODR definitions, member pointers, virtual dispatch and cross-TU identity. What C++ adds is a **second level of existence**: the AST has *templates and inline definitions*, the object files have *instantiations and emitted copies*. The contract needs (1) `instances[]` under a symbol (emitted mangled symbols that realize a template or an inline definition) and (2) two edge kinds, `dependent` (a call on a dependent name inside a template body; resolved per instantiation) and `virtual` (static target known, dynamic target a vtable). Both are generic fields: Rust generics, Java generics after erasure, and C's own asm-label renames all fit the same slot. **Extraction fidelity** for instantiation-level facts through libclang's cursor API is low by construction (it does not expose implicit instantiations); the honest C++ extractor for *edges* reads a codegen-adjacent source (LLVM IR at `-O0`, or the object's relocations as the oracle does), which is an extractor identity choice inside the contract, not a change to it. The research thread can stop here and move to consolidation.

## 1. The run [probe]

| Measure | fmt (49 TUs, C++) | curl lib (171 TUs, C), for contrast |
|---|---|---|
| Parse / Python walk per TU | 1.27 s / 5.2 s | 0.03 s / 0.1 s |
| Symbol records / distinct USRs (functions, definitions) | 146,551 / 4,226 definitions (11× repetition) | 393,968 / 3,866 |
| Function definitions in the AST, by TU | 46,500 (1,665 seen in several TUs: inline and template definitions in headers) | 3,909 |
| **Text symbols the objects define** (`llvm-nm`) | **62,865, of which 59,972 weak (95%)** | 1,680, 0 weak |
| Emitted symbols with no AST definition cursor | **template instantiations 37,197 (59%)**, standard-library/RTTI 17,759 (28%), **implicitly-defined special members 2,518 (4%)**, plain 485 (0.8%) | 0 |
| AST definitions never emitted in that TU | 31,145, of which inline or templated and unused 29,789 (96%) | 5 unused statics |
| Direct call edges: objdump / AST / agree | 164,387 / 67,351 / 14,582 | 4,766 / 4,761 / 4,706 |
| Calls on dependent names in template bodies | 35,642 | 0 |
| Virtual call sites (AST) / indirect sites (objdump) | 1,257 (+4,366 pointer-indirect) / 1,418 | 0 / 1,027 |
| Includes vs `clang -M`, **after aligning the toolchain** | 15,918; missing 86, extra 48 (99.2%) | 28,178; 0 / 2 |
| Includes **before** aligning the toolchain | missing 8,365, extra 7,672 (50%) | — |

## 2. The designer's nine items, each with what the probe showed and what the contract needs

| Item | What C++ does | What the probe measured | Contract: fits / needs a shared field / language-specific |
|---|---|---|---|
| **Templates / instantiations** | the AST holds the template definition once; codegen emits one weak symbol per instantiation, in every TU that uses it | 37,197 instantiation symbols with no AST definition; 29,789 AST definitions not emitted where seen; call edges agree only for non-template callers (14.6k of 164k) because codegen's callers *are* instantiations | **needs a shared field**: `symbol.instances[] = {mangled, units[]}` realizing a template (or an inline definition); edges from a template body are facts about the template with `tier: static_inference`; instantiation-level edges come from an IR/object-level extractor identity. No hack: "a definition realized by N emitted copies" is exactly ODR below |
| **Overloads** | same name, different signatures | USR distinguishes them (`c:@N@fmt@N@v11@S@format_int@F@format_int#I#` vs `#j#`); mangled names distinguish them in objects; 0 collisions | **fits** (identity = USR; emitted name = `symbol`) |
| **Namespaces** (incl. `inline namespace v11`) | nested scopes | USRs carry the scope; the walk descends `NAMESPACE`, `LINKAGE_SPEC`; cross-TU identity by USR held (1,665 definitions seen in several TUs collapse to one symbol each) | **fits** |
| **Inline definitions / ODR** | one definition in a header, one weak emitted copy per TU that uses it | 59,972 weak symbols (95% of all defined text); the AST sees the definition in every including TU with the same USR | **fits**, with `instances[]` carrying the per-unit emission; freshness is per unit anyway, so an ODR definition changed in a header invalidates exactly the units whose input set contains the header (S4) |
| **Class methods** (incl. special members) | in-class definitions are implicitly inline; constructors/destructors have several mangled variants (C1/C2, D0/D1/D2); implicitly-defined members have no AST definition | `CXX_METHOD`/`CONSTRUCTOR`/`DESTRUCTOR` walked; implicit inline recognized; 2,518 implicitly-defined special members emitted with no cursor; variant mangling confirmed (the extractor records one mangled name, the object may hold two) | **fits with `instances[]`** (a constructor is one symbol with two emitted names); implicit members are `tier: compiler_known, source: codegen` facts with no source range, which the record shape already allows (`defined_at: []`, `instances: [...]`) |
| **Virtual dispatch / vtables** | static target = the declared virtual method; dynamic target = vtable slot | 1,257 virtual call sites identified in the AST (`is_virtual_method`); objdump counts them among 1,418 indirect calls; vtables (`_ZTV…`) and RTTI (`_ZTI/_ZTS`) are emitted symbols with no source cursor | **needs a shared edge kind**: `virtual` = "calls the interface, implementation unknown statically", the exact analogue of C's `holds_pointer_to` + `calls_through` pair (a class's overrides are the "holders"); `overrides` is a compiler-known relation libclang exposes and should be a `reference.kind` |
| **Member-function pointers** | `&C::m` taken, called through a pointer-to-member | address-taken references to `CXX_METHOD` recorded (5,020 address-taken across TUs, mostly templates' functors); calls through them are `indirect through FIELD_DECL/VAR_DECL` | **fits** (same two edge kinds as C) |
| **Template-heavy headers** | thousands of definitions per TU, most never emitted | 146k symbol records for 4.2k distinct symbols; 5 s walk per TU; `fmt/base.h` and `format.h` contribute 900 records to every TU | **fits** (deduplication by USR is already mandatory, S2 §6); the cost says the Python walk is not the production extractor for C++ (S7's row shifts right by 50×) |
| **Cross-TU symbol identity** | the same declaration in N TUs | USR identical across TUs for every header-defined symbol; emitted names identical per instantiation; `function_definitions_seen_in_several_tus = 1,665` is the dedup test and passes | **fits** |

Two further facts the run produced that the contract already covers:

- **Toolchain identity is not optional.** libclang's driver selected GCC 8's libstdc++, the compiler GCC 15's: 50% include disagreement and thousands of different standard-library instantiations until `--gcc-toolchain` was passed. S2 §3's `extractor.toolchain` field exists for this; the probe now derives it from the compiler ("Selected GCC installation").
- **Includes agree at 99.2% once aligned**; the residual 86/48 are per-TU `__has_include`/version-conditional headers (`tsan_interface.h`, `format-inl.h` in header-only TUs) where the two drivers still differ slightly. Recorded as a known residual, not hidden.

## 3. What libclang's cursor API cannot give for C++ [probe → inference]

1. **Instantiation-level definitions and edges.** libclang does not expose implicit template instantiations as cursors; the 37k instantiation symbols and the 150k instantiation-level call edges are invisible to a cursor walk. Dependent calls (35,642) resolve only per instantiation.
2. **Implicitly-defined members** (2,518): no cursor, emitted anyway.
3. **Compiler-generated symbols**: vtables, RTTI, thunks, exception landing pads (`_Unwind_Resume` is 2 of the 1,781 unexplained undefined symbols; the rest are standard-library instantiations referenced from template code).
4. **One real gap in this probe's walk**: a friend function *defined* inside a class body (`friend auto add_compare(...) {...}` in fmt's `bigint`) was not surfaced even after adding `FRIEND_DECL` to the walk; 485 plain-missing definitions include these. Recorded as a probe limitation to resolve in the production extractor (clang's own AST, not libclang's cursor projection, has them).

[rec] **The C++ edge extractor should read codegen, not cursors.** `clang -S -emit-llvm -O0` per TU yields every instantiation as a function with its mangled name and every `call` with its target (direct) or `call %ptr` (indirect, with the virtual load pattern recognizable), for the price of a compile without optimization; the oracle's objdump pass is the same information one step later. Demangling maps instances back to the template's USR (`instances[]`). The AST walk keeps what it is good at: declarations, scopes, source ranges, `overrides`, which call sites are virtual or dependent, and the evidence locators. Two extractor identities, one artifact, both inside the S2 contract.

## 4. Decision for the consolidation [rec]

Freeze the contract with these C++-driven, language-neutral additions and nothing else:

```text
symbol.instances[]        {mangled, units[]}          realizations of a template or inline definition; empty for C
reference.kind += dependent | virtual | overrides     dependent: resolved per instantiation; virtual: interface known,
                                                      implementation a vtable lookup; overrides: compiler-known relation
extractor.toolchain       {tool, version, gcc_toolchain|sysroot, resource_dir_sha256}   mandatory, from the compiler
fact.source += codegen    beside ast, for facts with no source range (implicit members, vtables, instantiations)
```

Then T5 v0.4 (structural, with S8 §8's four hooks) and the contract freeze can close for the implementer; the C++ production extractor is an implementation item with its own oracle (this one), not a research question.
