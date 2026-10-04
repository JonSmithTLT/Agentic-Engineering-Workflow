"""C/C++ semantic extraction probe (architecture review, semantic-map thread S1).

  python cxx_extract_probe.py --db BUILD/compile_commands.json --root PROJECT --build BUILD --out extraction.json
                              [--only SUBSTR] [--limit N]

For every translation unit in the compile database, parse it with libclang using the exact compile command (the
compiler's own view: defines, include paths, language standard, the generated headers in the build directory) and
record what the compiler knows:

- diagnostics (a TU with errors is a *partial* fact source and is marked so);
- includes, every depth, classified project / generated (under the build dir) / system / external;
- symbols declared or defined in project files: functions, file-scope variables, records, enums, typedefs, macros,
  with USR, definition-vs-declaration, linkage and storage class;
- call edges from each function defined in the TU: direct (callee resolved to a FUNCTION_DECL), indirect (through a
  pointer: a variable, parameter or field), unresolved (libclang gives no referenced cursor);
- function references that are not calls (address taken: callbacks, tables), which is where static call graphs lose
  edges by construction;
- macro instantiations in the main file and the build's `-D` defines.

Output: one JSON with per-TU records and a summary. Read-only: nothing is written into the project or the build.
The companion `cxx_oracle.py` checks these records against the compiler's object files and preprocessor output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter

import clang.cindex as cx

CK = cx.CursorKind
FUNCTION_KINDS = {CK.FUNCTION_DECL, CK.CXX_METHOD, CK.CONSTRUCTOR, CK.DESTRUCTOR, CK.CONVERSION_FUNCTION,
                  CK.FUNCTION_TEMPLATE}
SYMBOL_KINDS = {CK.FUNCTION_DECL: "function", CK.CXX_METHOD: "function", CK.CONSTRUCTOR: "function",
                CK.DESTRUCTOR: "function", CK.CONVERSION_FUNCTION: "function", CK.FUNCTION_TEMPLATE: "function_template",
                CK.VAR_DECL: "variable", CK.STRUCT_DECL: "struct", CK.CLASS_DECL: "struct", CK.CLASS_TEMPLATE: "class_template",
                CK.UNION_DECL: "union", CK.ENUM_DECL: "enum", CK.TYPEDEF_DECL: "typedef", CK.TYPE_ALIAS_DECL: "typedef",
                CK.MACRO_DEFINITION: "macro"}
# C++: symbols nest in namespaces and class bodies; the walk descends into these containers.
CONTAINER_KINDS = {CK.NAMESPACE, CK.STRUCT_DECL, CK.CLASS_DECL, CK.CLASS_TEMPLATE, CK.UNION_DECL, CK.LINKAGE_SPEC,
                   CK.FRIEND_DECL}  # a friend function defined in-class hangs under FRIEND_DECL
EXTRA_ARGS: list[str] = []  # the compiler's own toolchain selection, so libclang reads the same libstdc++ it did
POINTER_REF_KINDS = {CK.VAR_DECL, CK.PARM_DECL, CK.FIELD_DECL, CK.MEMBER_REF_EXPR}


def compile_args(entry: dict, resource_dir: str) -> tuple[list[str], str, str | None]:
    """The parser's arguments from a compile command: everything but the compiler, -c, -o and the source file."""
    argv = entry.get("arguments") or shlex.split(entry["command"])
    src = entry["file"]
    out = None
    args: list[str] = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "-c":
            pass
        elif a == "-o":
            out = argv[i + 1]
            i += 1
        elif a.startswith("-o") and len(a) > 2:
            out = a[2:]
        elif a == src or os.path.abspath(os.path.join(entry["directory"], a)) == os.path.abspath(src):
            pass
        else:
            args.append(a)
        i += 1
    args += ["-resource-dir", resource_dir, *EXTRA_ARGS]
    obj = os.path.normpath(os.path.join(entry["directory"], out)) if out else None
    return args, src, obj


CWD = [os.getcwd()]  # the current TU's compile directory: libclang spells a header the way the -I flag did


def absolute(path: str) -> str:
    p = path if os.path.isabs(path) else os.path.join(CWD[0], path)
    return os.path.normpath(os.path.realpath(p))


def classify_path(path: str, root: str, build: str, resource_dir: str) -> str:
    p = absolute(path)
    if p.startswith(build + os.sep):
        return "generated"
    if p.startswith(root + os.sep):
        return "project"
    if p.startswith(("/usr/", resource_dir)):
        return "system"
    return "external"


def rel(path: str | None, root: str, build: str) -> str | None:
    if path is None:
        return None
    p = absolute(path)
    for base, tag in ((build, "$BUILD/"), (root, "")):
        if p.startswith(base + os.sep):
            return tag + os.path.relpath(p, base).replace(os.sep, "/")
    return p


def extract(index: cx.Index, entry: dict, root: str, build: str, resource_dir: str) -> dict:
    args, src, obj = compile_args(entry, resource_dir)
    CWD[0] = entry["directory"]
    t0 = time.perf_counter()
    tu = index.parse(src, args=args, options=cx.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    parse_ms = round((time.perf_counter() - t0) * 1000, 1)
    rec: dict = {"file": rel(src, root, build), "object": rel(obj, root, build), "parse_ms": parse_ms,
                 "defines": [a[2:] for a in args if a.startswith("-D")]}
    sev = Counter(d.severity for d in tu.diagnostics)
    rec["diagnostics"] = {"errors": sev.get(3, 0) + sev.get(4, 0), "fatal": sev.get(4, 0), "warnings": sev.get(2, 0),
                         "samples": [d.spelling[:120] for d in tu.diagnostics if d.severity >= 3][:3]}
    rec["partial"] = rec["diagnostics"]["errors"] > 0

    includes = []
    for inc in tu.get_includes():
        path = inc.include.name
        includes.append({"path": rel(path, root, build), "depth": inc.depth,
                         "class": classify_path(path, root, build, resource_dir),
                         "from": rel(inc.source.name if inc.source else None, root, build)})
    rec["includes"] = includes

    symbols: list[dict] = []
    calls: list[dict] = []
    fn_refs: list[dict] = []
    table_refs: list[dict] = []
    extern_vars: set[str] = set()
    macro_uses: Counter = Counter()
    main = absolute(src)
    t1 = time.perf_counter()

    def in_project(cur: cx.Cursor) -> str | None:
        loc = cur.location
        if loc.file is None:
            return None
        cls = classify_path(loc.file.name, root, build, resource_dir)
        return cls if cls in ("project", "generated") else None

    def callee_of(call: cx.Cursor) -> cx.Cursor | None:
        """libclang's `referenced` is None when the callee is parenthesized or cast (`(gzgetc)(g)`, `((fn_t)p)(x)`):
        look through the callee expression for the declaration it names."""
        ref = call.referenced
        if ref is not None:
            return ref
        children = list(call.get_children())
        node = children[0] if children else None
        for _ in range(6):
            if node is None:
                return None
            if node.kind == CK.DECL_REF_EXPR or node.kind == CK.MEMBER_REF_EXPR:
                return node.referenced
            if node.kind in (CK.PAREN_EXPR, CK.UNEXPOSED_EXPR, CK.CSTYLE_CAST_EXPR):
                sub = list(node.get_children())
                node = sub[0] if sub else None
                continue
            return None
        return None

    def walk_body(fn: cx.Cursor, fn_usr: str, fn_symbol: str) -> None:
        for cur in fn.walk_preorder():
            if cur.kind == CK.CALL_EXPR:
                ref = callee_of(cur)
                if ref is not None and ref.kind in FUNCTION_KINDS:
                    rf = ref.location.file
                    # The emitted symbol can differ from the source name (glibc's asm-label redirects: fopen -> fopen64
                    # under _FILE_OFFSET_BITS=64; C++ mangling); libclang knows it as the mangled name. A builtin is not
                    # an edge. A call to a template is a call to whichever instantiation the compiler emits.
                    symbol = ref.mangled_name or ref.spelling
                    # A virtual call's static target is the declared method; the dynamic target is a vtable lookup
                    # (codegen: an indirect call). Recorded as its own kind: known interface, unknown implementation.
                    if ref.spelling.startswith("__builtin_"):
                        kind = "builtin"
                    elif ref.kind == CK.CXX_METHOD and ref.is_virtual_method():
                        kind = "virtual"
                    elif ref.kind == CK.FUNCTION_TEMPLATE:
                        kind = "template"
                    else:
                        kind = "direct"
                    calls.append({"caller": fn_usr, "caller_symbol": fn_symbol, "callee": ref.get_usr(),
                                  "callee_name": ref.spelling,
                                  "callee_symbol": symbol, "kind": kind, "line": cur.location.line,
                                  "callee_defined_in_tu": bool(ref.get_definition()),
                                  "callee_file_class": classify_path(rf.name, root, build, resource_dir) if rf else None})
                elif ref is not None and ref.kind in POINTER_REF_KINDS:
                    calls.append({"caller": fn_usr, "caller_symbol": fn_symbol, "callee": None,
                                  "callee_name": ref.spelling, "kind": "indirect",
                                  "through": ref.kind.name, "line": cur.location.line})
                else:
                    # In a template body a call on a dependent name has no referent until instantiation; libclang
                    # reports no referenced cursor. That is C++'s own category, not an extractor failure.
                    kind = "dependent" if (ref is None and depth_templated[0] > 0) else "unresolved"
                    calls.append({"caller": fn_usr, "caller_symbol": fn_symbol, "callee": None,
                                  "callee_name": cur.spelling or None,
                                  "kind": kind, "through": ref.kind.name if ref else None,
                                  "line": cur.location.line})
            elif cur.kind == CK.DECL_REF_EXPR:
                ref = cur.referenced
                if ref is not None and ref.kind in FUNCTION_KINDS:
                    fn_refs.append({"caller": fn_usr, "callee": ref.get_usr(), "callee_name": ref.spelling,
                                    "callee_symbol": ref.mangled_name or ref.spelling, "line": cur.location.line})
                elif ref is not None and ref.kind == CK.VAR_DECL and ref.linkage.name == "EXTERNAL" \
                        and not ref.get_definition():
                    extern_vars.add(ref.mangled_name or ref.spelling)  # stderr, errno-like globals: linker references

    def visit(cur: cx.Cursor, depth: int) -> None:
        if cur.kind == CK.MACRO_INSTANTIATION:
            if cur.location.file and absolute(cur.location.file.name) == main:
                macro_uses[cur.spelling] += 1
            return
        kind = SYMBOL_KINDS.get(cur.kind)
        if kind is None and cur.kind not in CONTAINER_KINDS:
            return
        where = in_project(cur)
        if where is None:
            return
        if kind is not None:
            sym = {"usr": cur.get_usr(), "name": cur.spelling, "kind": kind,
                   "symbol": cur.mangled_name or cur.spelling if cur.kind in FUNCTION_KINDS | {CK.VAR_DECL} else None,
                   "file": rel(cur.location.file.name, root, build), "line": cur.location.line,
                   "in_main_file": absolute(cur.location.file.name) == main,
                   "is_definition": cur.is_definition(), "linkage": cur.linkage.name,
                   "storage": cur.storage_class.name if cur.kind in FUNCTION_KINDS | {CK.VAR_DECL} else None,
                   "templated": cur.kind in (CK.FUNCTION_TEMPLATE, CK.CLASS_TEMPLATE) or depth_templated[0] > 0}
            if cur.kind in FUNCTION_KINDS:
                sym["type"] = cur.type.spelling
                # `inline` keyword, or a definition inside a class body (implicitly inline in C++): emitted only in
                # TUs that use it, as a weak symbol
                sym["inline"] = "inline" in " ".join(t.spelling for t in cur.get_tokens()
                                                     if t.kind == cx.TokenKind.KEYWORD) \
                    or (cur.is_definition() and cur.semantic_parent is not None
                        and cur.semantic_parent.kind in (CK.STRUCT_DECL, CK.CLASS_DECL, CK.CLASS_TEMPLATE, CK.UNION_DECL))
                if cur.is_definition():
                    if cur.kind == CK.FUNCTION_TEMPLATE:
                        depth_templated[0] += 1
                    walk_body(cur, sym["usr"], sym["symbol"] or sym["name"])
                    if cur.kind == CK.FUNCTION_TEMPLATE:
                        depth_templated[0] -= 1
            if cur.kind in (CK.STRUCT_DECL, CK.UNION_DECL, CK.CLASS_DECL) and cur.is_definition():
                sym["fields"] = sum(1 for c in cur.get_children() if c.kind == CK.FIELD_DECL)
            if cur.kind == CK.VAR_DECL and cur.is_definition():
                # Function references in a file-scope initializer: C's dispatch tables (struct-of-function-pointers
                # "vtables", callback arrays). These are the edges a body-only call graph never sees.
                for sub in cur.walk_preorder():
                    if sub.kind == CK.DECL_REF_EXPR and sub.referenced is not None \
                            and sub.referenced.kind in FUNCTION_KINDS:
                        r = sub.referenced
                        table_refs.append({"table": sym["usr"], "table_name": sym["name"], "callee": r.get_usr(),
                                           "callee_name": r.spelling, "callee_symbol": r.mangled_name or r.spelling,
                                           "line": sub.location.line})
            symbols.append(sym)
        if cur.kind in CONTAINER_KINDS:  # namespaces, classes, templates: C++ nests its symbols
            if cur.kind == CK.CLASS_TEMPLATE:
                depth_templated[0] += 1
            for child in cur.get_children():
                visit(child, depth + 1)
            if cur.kind == CK.CLASS_TEMPLATE:
                depth_templated[0] -= 1

    depth_templated = [0]
    for cur in tu.cursor.get_children():
        visit(cur, 0)

    # Address-taken references: function references outside a call's callee position (approximation: references
    # whose (caller, callee, line) is not also a direct call at that line).
    call_sites = {(c["caller"], c["callee"], c["line"]) for c in calls if c["kind"] == "direct"}
    address_taken = [r for r in fn_refs if (r["caller"], r["callee"], r["line"]) not in call_sites]

    rec["walk_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    rec["symbols"] = symbols
    rec["calls"] = calls
    rec["address_taken"] = address_taken
    rec["table_refs"] = table_refs
    rec["macro_uses"] = dict(macro_uses.most_common())
    rec["extern_vars"] = sorted(extern_vars)
    macro_defs = [c.spelling for c in tu.cursor.get_children() if c.kind == CK.MACRO_DEFINITION]
    rec["macro_definitions_visible"] = len(macro_defs)  # every definition the TU saw, including ones later #undef'd
    rec["macro_definition_names_distinct"] = len(set(macro_defs))
    rec["counts"] = {
        "includes": len(includes),
        "includes_by_class": dict(Counter(i["class"] for i in includes)),
        "symbols": len(symbols),
        "function_definitions": sum(1 for s in symbols if s["kind"] == "function" and s["is_definition"]),
        "function_declarations_only": sum(1 for s in symbols if s["kind"] == "function" and not s["is_definition"]),
        "calls_direct": sum(1 for c in calls if c["kind"] == "direct"),
        "calls_indirect": sum(1 for c in calls if c["kind"] == "indirect"),
        "calls_unresolved": sum(1 for c in calls if c["kind"] == "unresolved"),
        "calls_dependent": sum(1 for c in calls if c["kind"] == "dependent"),
        "calls_virtual": sum(1 for c in calls if c["kind"] == "virtual"),
        "calls_template": sum(1 for c in calls if c["kind"] == "template"),
        "address_taken": len(address_taken),
        "table_refs": len(table_refs),
        "macro_uses_main": sum(macro_uses.values()),
        "macro_names_main": len(macro_uses),
    }
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="only TUs whose path contains this substring")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    root, build = os.path.realpath(os.path.abspath(a.root)), os.path.realpath(os.path.abspath(a.build))
    resource_dir = subprocess.run(["clang", "-print-resource-dir"], capture_output=True, text=True,
                                  check=True).stdout.strip()
    # The compiler that built the objects may have selected a different GCC installation (and libstdc++) than the
    # libclang wheel's driver does; parse against the same one, or the two disagree on every system header.
    probe = subprocess.run(["clang++", "-v", "-E", "-x", "c++", os.devnull], capture_output=True, text=True).stderr
    m = re.search(r"Selected GCC installation: (.*?)/lib/gcc/", probe)
    if m:
        EXTRA_ARGS.append(f"--gcc-toolchain={os.path.normpath(m.group(1))}")
        print(f"toolchain: {EXTRA_ARGS[-1]}", file=sys.stderr)
    entries = json.load(open(a.db, encoding="utf-8"))
    if a.only:
        entries = [e for e in entries if a.only in e["file"]]
    if a.limit:
        entries = entries[:a.limit]
    index = cx.Index.create()
    tus = []
    t0 = time.perf_counter()
    for n, e in enumerate(entries, 1):
        try:
            tus.append(extract(index, e, root, build, resource_dir))
        except Exception as ex:  # noqa: BLE001 - a probe records the failure and goes on
            tus.append({"file": rel(e["file"], root, build), "error": f"{type(ex).__name__}: {ex}"[:200]})
        if n % 100 == 0:
            print(f"  {n}/{len(entries)} TUs, {time.perf_counter() - t0:.1f}s", file=sys.stderr)
    total_s = round(time.perf_counter() - t0, 2)
    ok = [t for t in tus if "error" not in t]
    summary = {
        "tus": len(tus), "tus_failed": len(tus) - len(ok), "tus_partial": sum(1 for t in ok if t["partial"]),
        "total_s": total_s, "parse_ms_mean": round(sum(t["parse_ms"] for t in ok) / max(1, len(ok)), 1),
        "walk_ms_mean": round(sum(t["walk_ms"] for t in ok) / max(1, len(ok)), 1),
    }
    for key in ("includes", "symbols", "function_definitions", "function_declarations_only", "calls_direct",
                "calls_indirect", "calls_unresolved", "calls_dependent", "calls_virtual", "calls_template",
                "address_taken", "table_refs", "macro_uses_main"):
        summary[key] = sum(t["counts"][key] for t in ok)
    summary["includes_by_class"] = dict(sum((Counter(t["counts"]["includes_by_class"]) for t in ok), Counter()))
    defs = Counter(s["usr"] for t in ok for s in t["symbols"] if s["kind"] == "function" and s["is_definition"])
    summary["distinct_function_definitions"] = len(defs)
    summary["function_definitions_seen_in_several_tus"] = sum(1 for n in defs.values() if n > 1)
    summary["defines_distinct"] = sorted({d for t in ok for d in t["defines"]})[:40]
    commit = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump({"project": os.path.basename(root), "commit": commit, "root": root, "build": build,
               "summary": summary, "tus": tus}, open(a.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
