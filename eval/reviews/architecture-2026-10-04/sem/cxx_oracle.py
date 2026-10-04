"""Oracle for the C/C++ extraction probe: check the libclang-derived facts against what the compiler actually produced.

  python cxx_oracle.py extraction.json --db BUILD/compile_commands.json [--out oracle.json]

Four truths the build already holds, none of them derived from our own parse:

1. `llvm-nm` on each TU's object: which functions the TU *defines* and with which linkage (T external / t local),
   and which symbols it leaves *undefined* (the cross-TU references the linker must resolve).
2. `llvm-objdump -d -r` on the object: the direct `call` instructions per function with their relocation targets
   (external and same-section callees) and the indirect `call *reg` sites. At -O0 every C call is one instruction, so
   this is the compiler's own call graph for the TU.
3. `clang -MM` with the TU's arguments: the header set the preprocessor read.
4. `clang -dM -E`: the macro definitions in effect at the end of the TU.

For each, the probe's record is scored: missing (truth has it, extraction does not), extra (extraction has it, truth
does not), with samples, so the note can say where the compiler-known boundary lies and how often static inference
gets an edge wrong. Read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter

CALL_RE = re.compile(r"^\s*[0-9a-f]+:\s+call[q]?\s+(.*)$")
LABEL_RE = re.compile(r"^[0-9a-f]+ <([^>]+)>:$")
RELOC_RE = re.compile(r"^\s*[0-9a-f]+:\s+R_X86_64_(PLT32|PC32|GOTPCREL\w*)\s+([^\s+-]+)")
INLINE_TARGET_RE = re.compile(r"<([^>+]+)(?:\+0x[0-9a-f]+)?>")


def run(argv: list[str], cwd: str | None = None) -> str:
    return subprocess.run(argv, capture_output=True, text=True, cwd=cwd, errors="replace").stdout


def nm_facts(obj: str) -> tuple[dict[str, str], set[str]]:
    """{symbol: 'T'|'t'|'W'} for text symbols (W: weak, i.e. C++ inline definitions and template instantiations,
    emitted in every TU that uses them), and the undefined symbol set."""
    defined: dict[str, str] = {}
    undefined: set[str] = set()
    for line in run(["llvm-nm", "-f", "posix", obj]).split("\n"):
        parts = line.split()
        if len(parts) < 2:
            continue
        name, typ = parts[0], parts[1]
        if typ in ("T", "t"):
            defined[name] = typ
        elif typ in ("W", "w", "V", "v"):
            defined[name] = "W"
        elif typ == "U":
            undefined.add(name)
    return defined, undefined


_DEMANGLED: dict[str, str] = {}


def demangle(names: list[str]) -> dict[str, str]:
    todo = [n for n in names if n not in _DEMANGLED]
    if todo:
        out = run(["llvm-cxxfilt", *todo]).split("\n")
        for n, d in zip(todo, out):
            _DEMANGLED[n] = d
    return {n: _DEMANGLED.get(n, n) for n in names}


def classify_symbol(name: str) -> str:
    """What kind of thing an emitted symbol the AST did not define is: a template instantiation (the AST has the
    template, codegen has the instance), a standard-library instantiation, a compiler artefact, or a plain miss."""
    d = demangle([name])[name]
    if name.startswith(("_ZSt", "_ZNSt", "_ZNKSt", "_ZN9__gnu_cxx", "__cxx", "__cxa", "_GLOBAL__", "_ZTV", "_ZTI", "_ZTS")):
        return "library_or_rtti"
    if "<" in d:
        return "template_instantiation"
    if d.startswith(("std::", "__")):
        return "library_or_rtti"
    m = re.search(r"(\w+)::~?(\w+)\(", d)
    if m and m.group(1) == m.group(2):
        return "constructor_or_destructor"  # implicitly defined or inherited special members have no AST definition
    return "plain"


def objdump_calls(obj: str) -> tuple[dict[str, Counter], dict[str, int]]:
    """Per function: Counter of direct callee names; and the count of indirect call sites."""
    direct: dict[str, Counter] = {}
    indirect: dict[str, int] = {}
    cur: str | None = None
    lines = run(["llvm-objdump", "-d", "-r", "--no-show-raw-insn", obj]).split("\n")
    for i, line in enumerate(lines):
        m = LABEL_RE.match(line)
        if m:
            cur = m.group(1)
            direct.setdefault(cur, Counter())
            indirect.setdefault(cur, 0)
            continue
        if cur is None:
            continue
        m = CALL_RE.match(line)
        if not m:
            continue
        operand = m.group(1)
        if operand.startswith("*"):
            indirect[cur] += 1
            continue
        target = None
        if i + 1 < len(lines):
            r = RELOC_RE.match(lines[i + 1])
            if r:
                target = r.group(2)
        if target is None:
            t = INLINE_TARGET_RE.search(operand)
            if t:
                target = t.group(1)
        if target:
            direct[cur][target] += 1
        else:
            indirect[cur] += 1  # a call we could not symbolize counts as not-direct, conservatively
    return direct, indirect


def compile_argv(entry: dict) -> tuple[list[str], str]:
    argv = entry.get("arguments") or shlex.split(entry["command"])
    src = entry["file"]
    out: list[str] = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "-c" or a == src or os.path.abspath(os.path.join(entry["directory"], a)) == os.path.abspath(src):
            pass
        elif a == "-o":
            i += 1
        elif a.startswith("-o") and len(a) > 2:
            pass
        else:
            out.append(a)
        i += 1
    return out, src


def mm_headers(entry: dict) -> set[str]:
    args, src = compile_argv(entry)
    text = run(["clang", *args, "-M", "-MG", src], cwd=entry["directory"])  # -M: system headers too (-MM omits them)
    deps = text.replace("\\\n", " ").split(":", 1)[-1].split()
    return {os.path.normpath(os.path.join(entry["directory"], d)) for d in deps
            if os.path.normpath(os.path.join(entry["directory"], d)) != os.path.normpath(src)}


def dm_macros(entry: dict) -> set[str]:
    args, src = compile_argv(entry)
    text = run(["clang", *args, "-dM", "-E", src], cwd=entry["directory"])
    return {ln.split()[1].split("(")[0] for ln in text.split("\n") if ln.startswith("#define ")}


def usr_name(usr: str) -> str:
    """The symbol name a USR denotes (c:@F@name, c:file.c@F@name, c:@name...)."""
    m = re.search(r"@F@([^#]+)", usr)
    return m.group(1) if m else usr.rsplit("@", 1)[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("extraction")
    ap.add_argument("--db", required=True)
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    ex = json.load(open(a.extraction, encoding="utf-8"))
    root, build = ex["root"], ex["build"]
    db = {os.path.normpath(e["file"]): e for e in json.load(open(a.db, encoding="utf-8"))}

    def abspath(r: str | None) -> str | None:
        if r is None:
            return None
        return os.path.normpath(os.path.join(build, r[7:]) if r.startswith("$BUILD/") else os.path.join(root, r))

    totals = Counter()
    per_tu = []
    samples: dict[str, list] = {"def_missing": [], "def_extra": [], "linkage_disagree": [], "call_missing": [],
                                "call_extra": [], "undefined_unexplained": [], "include_missing": [], "include_extra": [],
                                "macro_missing": [], "macro_extra": []}
    tus = [t for t in ex["tus"] if "error" not in t and t.get("object")]
    if a.limit:
        tus = tus[:a.limit]
    for t in tus:
        obj = abspath(t["object"])
        src = abspath(t["file"])
        if not obj or not os.path.exists(obj) or src not in db:
            totals["tus_without_object"] += 1
            continue
        entry = db[src]
        row = {"file": t["file"]}
        # 1. definitions and linkage --------------------------------------------------------------------------
        nm_defined, nm_undefined = nm_facts(obj)
        ex_defs = {(s.get("symbol") or s["name"]): s for s in t["symbols"]
                   if s["kind"] == "function" and s["is_definition"]}
        missing_all = sorted(set(nm_defined) - set(ex_defs))
        missing_class = Counter(classify_symbol(n) for n in missing_all)
        missing = [n for n in missing_all if classify_symbol(n) == "plain"]
        extra = sorted(set(ex_defs) - set(nm_defined))
        extra_unused_static = [n for n in extra if ex_defs[n]["linkage"] == "INTERNAL"]
        extra_inline = [n for n in extra if ex_defs[n].get("inline") or ex_defs[n].get("templated")]
        linkage_dis = [n for n in set(nm_defined) & set(ex_defs) if nm_defined[n] != "W"
                       and (nm_defined[n] == "T") != (ex_defs[n]["linkage"] != "INTERNAL")]
        row["definitions"] = {"nm": len(nm_defined), "nm_weak": sum(1 for v in nm_defined.values() if v == "W"),
                              "extracted": len(ex_defs), "missing_plain": len(missing),
                              "missing_template_instantiation": missing_class.get("template_instantiation", 0),
                              "missing_library_or_rtti": missing_class.get("library_or_rtti", 0),
                              "extra": len(extra), "extra_internal_linkage": len(extra_unused_static),
                              "extra_inline_or_templated_unused": len(extra_inline),
                              "linkage_disagreements": len(linkage_dis)}
        totals["def_nm"] += len(nm_defined); totals["def_nm_weak"] += row["definitions"]["nm_weak"]
        totals["def_extracted"] += len(ex_defs)
        totals["def_missing"] += len(missing); totals["def_extra"] += len(extra)
        totals["def_missing_template_inst"] += missing_class.get("template_instantiation", 0)
        totals["def_missing_library"] += missing_class.get("library_or_rtti", 0)
        totals["def_missing_ctor_dtor"] += missing_class.get("constructor_or_destructor", 0)
        totals["def_extra_internal"] += len(extra_unused_static); totals["def_extra_inline"] += len(extra_inline)
        totals["linkage_disagree"] += len(linkage_dis)
        samples["def_missing"] += [(t["file"], demangle([n])[n][:90]) for n in missing[:2]]
        samples["def_extra"] += [(t["file"], n, ex_defs[n]["linkage"]) for n in extra[:2]]
        samples["linkage_disagree"] += [(t["file"], n) for n in linkage_dis[:2]]
        # 2. direct call edges ----------------------------------------------------------------------------------
        od_direct, od_indirect = objdump_calls(obj)
        ex_direct: dict[str, Counter] = {}
        ex_indirect: Counter = Counter()
        for c in t["calls"]:
            caller = c.get("caller_symbol") or usr_name(c["caller"])
            if c["kind"] in ("direct", "template"):
                ex_direct.setdefault(caller, Counter())[c.get("callee_symbol") or c["callee_name"]] += 1
            elif c["kind"] == "builtin":
                continue  # not an edge: the compiler expands it
            else:
                ex_indirect[caller] += 1  # indirect through a pointer, virtual through a vtable, or unresolved
                totals["call_virtual_sites"] += 1 if c["kind"] == "virtual" else 0
        callers = set(od_direct) & set(ex_direct.keys() | set(nm_defined))
        c_missing = c_extra = c_agree = 0
        for fn in sorted(set(od_direct) | set(ex_direct)):
            if fn not in nm_defined:
                continue  # a label that is not a function we know (e.g. a local label) is skipped
            od = set(od_direct.get(fn, Counter()))
            exs = set(ex_direct.get(fn, Counter()))
            od_clean = {x for x in od if not x.startswith(("__", "llvm.", ".L"))}  # compiler-rt / builtins / labels
            miss = od_clean - exs
            ext = exs - od
            c_missing += len(miss); c_extra += len(ext); c_agree += len(od_clean & exs)
            samples["call_missing"] += [(t["file"], fn, x) for x in sorted(miss)[:1]]
            samples["call_extra"] += [(t["file"], fn, x) for x in sorted(ext)[:1]]
        od_ind_total = sum(od_indirect.get(fn, 0) for fn in nm_defined)
        row["calls"] = {"objdump_direct_edges": sum(len(set(v)) for k, v in od_direct.items() if k in nm_defined),
                        "extracted_direct_edges": sum(len(set(v)) for v in ex_direct.values()),
                        "agree": c_agree, "missing": c_missing, "extra": c_extra,
                        "objdump_indirect_sites": od_ind_total, "extracted_indirect_sites": sum(ex_indirect.values())}
        for k, v in row["calls"].items():
            totals["call_" + k] += v
        # 3. undefined symbols explained by extraction -------------------------------------------------------------
        referenced_external = {c.get("callee_symbol") or c["callee_name"] for c in t["calls"]
                               if c["kind"] == "direct" and not c["callee_defined_in_tu"]}
        referenced_external |= {r.get("callee_symbol") or r["callee_name"] for r in t["address_taken"]}
        referenced_external |= {r.get("callee_symbol") or r["callee_name"] for r in t.get("table_refs", [])}
        ext_vars = {s["name"] for s in t["symbols"] if s["kind"] == "variable" and not s["is_definition"]}
        ext_vars |= set(t.get("extern_vars", []))
        unexplained = sorted(u for u in nm_undefined if u not in referenced_external and u not in ext_vars
                             and not u.startswith(("__", "llvm.")))
        row["undefined"] = {"nm": len(nm_undefined), "explained_by_extraction": len(nm_undefined) - len(unexplained)
                            - len([u for u in nm_undefined if u.startswith(("__", "llvm."))]),
                            "compiler_runtime": len([u for u in nm_undefined if u.startswith(("__", "llvm."))]),
                            "unexplained": len(unexplained)}
        totals["undef_nm"] += len(nm_undefined); totals["undef_unexplained"] += len(unexplained)
        samples["undefined_unexplained"] += [(t["file"], u) for u in unexplained[:2]]
        # 4. includes ---------------------------------------------------------------------------------------------
        truth_inc = {os.path.realpath(p) for p in mm_headers(entry)}  # -M and libclang may spell a header through
        ex_inc = {os.path.realpath(abspath(i["path"])) for i in t["includes"] if i["path"]}  # different symlinks
        inc_missing = sorted(truth_inc - ex_inc)
        inc_extra = sorted(ex_inc - truth_inc)
        row["includes"] = {"mm": len(truth_inc), "extracted": len(ex_inc), "missing": len(inc_missing),
                           "extra": len(inc_extra)}
        totals["inc_mm"] += len(truth_inc); totals["inc_missing"] += len(inc_missing); totals["inc_extra"] += len(inc_extra)
        samples["include_missing"] += [(t["file"], os.path.basename(p)) for p in inc_missing[:2]]
        samples["include_extra"] += [(t["file"], os.path.basename(p)) for p in inc_extra[:2]]
        # 5. macros -----------------------------------------------------------------------------------------------
        truth_mac = dm_macros(entry)
        row["macros"] = {"dM": len(truth_mac), "extracted_definitions_visible": t["macro_definitions_visible"],
                         "extracted_names_distinct": t.get("macro_definition_names_distinct")}
        totals["mac_dM"] += len(truth_mac); totals["mac_extracted"] += t["macro_definitions_visible"]
        totals["mac_extracted_distinct"] += t.get("macro_definition_names_distinct") or 0
        totals["tus"] += 1
        per_tu.append(row)

    out = {"project": ex["project"], "commit": ex["commit"], "totals": dict(totals),
           "samples": {k: v[:8] for k, v in samples.items()}, "per_tu": per_tu}
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)
    T = totals
    print(f"{ex['project']} @ {ex['commit']}: {T['tus']} TUs with objects ({T['tus_without_object']} without)")
    print(f"function definitions: nm {T['def_nm']} (weak {T['def_nm_weak']}), extracted {T['def_extracted']}, "
          f"missing plain {T['def_missing']}, missing template instantiations {T['def_missing_template_inst']}, "
          f"missing library/rtti {T['def_missing_library']}, missing implicit ctor/dtor {T['def_missing_ctor_dtor']}, "
          f"extra {T['def_extra']} (internal linkage "
          f"{T['def_extra_internal']}, inline/templated unused {T['def_extra_inline']}); linkage disagreements "
          f"{T['linkage_disagree']}")
    print(f"direct call edges (per caller, distinct callees): objdump {T['call_objdump_direct_edges']}, extracted "
          f"{T['call_extracted_direct_edges']}, agree {T['call_agree']}, missing {T['call_missing']}, extra {T['call_extra']}")
    print(f"indirect call sites: objdump {T['call_objdump_indirect_sites']}, extracted {T['call_extracted_indirect_sites']} "
          f"(of which virtual {T['call_virtual_sites']})")
    print(f"undefined symbols: nm {T['undef_nm']}, unexplained by extraction {T['undef_unexplained']}")
    print(f"includes: -MM {T['inc_mm']}, missing {T['inc_missing']}, extra {T['inc_extra']}")
    print(f"macros: -dM {T['mac_dM']}, extracted visible definitions {T['mac_extracted']} "
          f"(distinct names {T['mac_extracted_distinct']})")
    for k, v in out["samples"].items():
        if v:
            print(f"  sample {k}: {v[:4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
