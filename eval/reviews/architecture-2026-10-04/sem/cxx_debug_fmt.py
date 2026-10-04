"""Debug helper for the fmt C++ run: why do definitions and includes disagree with the oracle on format.cc?"""
import json
import os
import re
import subprocess

ex = json.load(open("fmt.extraction.json"))
tu = next(t for t in ex["tus"] if t["file"] == "src/format.cc")
obj = os.path.join(ex["build"], tu["object"][7:])
nm = {}
for ln in subprocess.run(["llvm-nm", "-f", "posix", obj], capture_output=True, text=True).stdout.split("\n"):
    p = ln.split()
    if len(p) >= 2 and p[1] in "TtWwVv":
        nm[p[0]] = p[1]
ex_defs = {(s.get("symbol") or s["name"]): s for s in tu["symbols"] if s["kind"] == "function" and s["is_definition"]}


def dem(names):
    out = subprocess.run(["llvm-cxxfilt", *names], capture_output=True, text=True).stdout.split("\n")
    return dict(zip(names, out))


missing = sorted(set(nm) - set(ex_defs))
extra = sorted(set(ex_defs) - set(nm))
dm, de = dem(missing), dem(extra)
plain_missing = [n for n in missing if "<" not in dm[n] and not dm[n].startswith(("std::", "__"))]
print(f"format.cc: nm {len(nm)}, extracted {len(ex_defs)}, missing {len(missing)} (plain {len(plain_missing)}), extra {len(extra)}")
# same function, different mangling variant? (C1/C2 constructors, D0/D1/D2 destructors)
norm = lambda s: re.sub(r"(C[123]|D[0-5])E", "CXE", s)
missing_norm = {norm(n) for n in missing}
extra_matched = [n for n in extra if norm(n) in missing_norm]
print(f"extra whose C1/C2-D0/D1/D2 variant is among the missing: {len(extra_matched)} of {len(extra)}")
print("plain missing samples (demangled):")
for n in plain_missing[:8]:
    print("   ", dm[n][:110], "| in extraction by name?",
          any(s["name"] == dm[n].split("(")[0].rsplit("::", 1)[-1] for s in tu["symbols"]))
print("extra samples (demangled, templated?):")
for n in extra[:6]:
    print("   ", de[n][:100], "| templated", ex_defs[n].get("templated"), "inline", ex_defs[n].get("inline"), ex_defs[n]["file"])
# includes
cc = next(e for e in json.load(open(os.path.join(ex["build"], "compile_commands.json"))) if e["file"].endswith("src/format.cc"))
args = [a for a in (cc.get("arguments") or []) or __import__("shlex").split(cc["command"])][1:]
args = [a for i, a in enumerate(args) if a not in ("-c",) and not a.endswith("format.cc") and not (i > 0 and args[i - 1] == "-o") and a != "-o"]
text = subprocess.run(["clang", *args, "-M", cc["file"]], cwd=cc["directory"], capture_output=True, text=True).stdout
deps = {os.path.realpath(os.path.join(cc["directory"], d)) for d in text.replace("\\\n", " ").split(":", 1)[1].split()}
root, build = ex["root"], ex["build"]
exinc = set()
for i in tu["includes"]:
    p = i["path"]
    p = os.path.join(build, p[7:]) if p.startswith("$BUILD/") else (p if os.path.isabs(p) else os.path.join(root, p))
    exinc.add(os.path.realpath(p))
print(f"includes: -M {len(deps)}, extraction {len(exinc)}, common {len(deps & exinc)}")
print("  -M only:", sorted(deps - exinc)[:3])
print("  extraction only:", sorted(exinc - deps)[:3])
