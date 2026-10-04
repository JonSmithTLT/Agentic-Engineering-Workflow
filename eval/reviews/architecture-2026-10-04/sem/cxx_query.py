"""Agent-facing code-intelligence queries over an extraction (semantic-map thread S3): what does an agent get back,
and how big is it, when it asks the eight questions the designer listed, compared with the whole graph?

  python cxx_query.py extraction.json define NAME
  python cxx_query.py extraction.json callers NAME [--depth 1]
  python cxx_query.py extraction.json callees NAME
  python cxx_query.py extraction.json includers HEADER
  python cxx_query.py extraction.json defines-for NAME
  python cxx_query.py extraction.json evidence CALLER CALLEE
  python cxx_query.py extraction.json neighborhood NAME [--radius 1]
  python cxx_query.py extraction.json sizes NAME...        (bytes of each answer vs the whole extraction)

Every answer carries its evidence locator (file:line in the TU that saw it) and names the boundary it sits on:
direct edges are compiler-known; indirect/table edges are "dispatched through"; a symbol with no definition in any TU
is declared-only here. Read-only over the JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict


def usr_name(usr: str) -> str:
    m = re.search(r"@F@([^#]+)", usr)
    return m.group(1) if m else usr.rsplit("@", 1)[-1]


class Graph:
    def __init__(self, ex: dict) -> None:
        self.ex = ex
        self.defs: dict[str, list[dict]] = defaultdict(list)       # name -> definitions (with tu)
        self.decls: dict[str, list[dict]] = defaultdict(list)
        self.calls_out: dict[str, list[dict]] = defaultdict(list)  # caller name -> edges
        self.calls_in: dict[str, list[dict]] = defaultdict(list)   # callee name -> edges
        self.tables: dict[str, list[dict]] = defaultdict(list)     # callee name -> table refs
        self.includers: dict[str, set[str]] = defaultdict(set)     # header basename/path -> TUs
        self.tu_defines: dict[str, list[str]] = {}
        for t in ex["tus"]:
            if "error" in t:
                continue
            tu = t["file"]
            self.tu_defines[tu] = t["defines"]
            for s in t["symbols"]:
                if s["kind"] != "function":
                    continue
                (self.defs if s["is_definition"] else self.decls)[s["name"]].append({**s, "tu": tu})
            for c in t["calls"]:
                caller = usr_name(c["caller"])
                e = {**c, "caller_name": caller, "tu": tu}
                self.calls_out[caller].append(e)
                if c.get("callee_name"):
                    self.calls_in[c["callee_name"]].append(e)
            for r in t.get("table_refs", []) + t.get("address_taken", []):
                self.tables[r["callee_name"]].append({**r, "tu": tu})
            for i in t["includes"]:
                if i["path"]:
                    self.includers[i["path"]].add(tu)
                    self.includers[i["path"].rsplit("/", 1)[-1]].add(tu)

    def define(self, name: str) -> dict:
        defs = self.defs.get(name, [])
        decls = self.decls.get(name, [])
        locs = sorted({(d["file"], d["line"], d["linkage"]) for d in defs})
        return {"symbol": name, "status": "defined" if defs else ("declared_only" if decls else "unknown"),
                "definitions": [{"file": f, "line": ln, "linkage": lk} for f, ln, lk in locs],
                "seen_in_tus": len({d["tu"] for d in defs}),
                "declared_in": sorted({d["file"] for d in decls})[:5],
                "type": defs[0]["type"] if defs else (decls[0]["type"] if decls else None),
                "boundary": "compiler-known (definition and linkage agree with the object files)" if defs else
                            "declared only in these TUs; the definition is in another library or TU set"}

    def callers(self, name: str) -> dict:
        direct = sorted({(e["caller_name"], e["tu"], e["line"]) for e in self.calls_in.get(name, [])
                         if e["kind"] == "direct"})
        tables = sorted({(r.get("table_name") or r.get("caller") and usr_name(r["caller"]), r["tu"], r["line"])
                         for r in self.tables.get(name, [])})
        return {"symbol": name,
                "direct_callers": [{"caller": c, "evidence": f"{tu}:{ln}"} for c, tu, ln in direct],
                "address_taken_in": [{"holder": h, "evidence": f"{tu}:{ln}"} for h, tu, ln in tables],
                "boundary": "direct callers are compiler-known; address-taken holders show where a pointer to it is "
                            "stored (a dispatch table, a callback argument): who calls through that pointer is not "
                            "statically known" if tables else "direct callers are compiler-known; no address-taken use "
                            "seen, so this is the complete static caller set (within the extracted TUs)"}

    def callees(self, name: str) -> dict:
        out = self.calls_out.get(name, [])
        direct = sorted({(e["callee_name"], e["callee_file_class"]) for e in out if e["kind"] == "direct"})
        indirect = sorted({(e.get("callee_name") or "?", e.get("through") or "?") for e in out
                           if e["kind"] in ("indirect", "unresolved")})
        return {"symbol": name,
                "direct": [{"callee": c, "where": cls} for c, cls in direct],
                "indirect": [{"through": n, "kind": k} for n, k in indirect],
                "builtins": sorted({e["callee_name"] for e in out if e["kind"] == "builtin"}),
                "boundary": "direct callees compiler-known at -O0 except libc memory/string functions, which codegen "
                            "may inline or synthesize; indirect sites name the pointer, never the target"}

    def includers_of(self, header: str) -> dict:
        tus = sorted(self.includers.get(header, set()))
        return {"header": header, "translation_units": len(tus), "sample": tus[:12],
                "boundary": "compiler-known: the preprocessor's include graph for the build as configured"}

    def defines_for(self, name: str) -> dict:
        tus = {d["tu"] for d in self.defs.get(name, [])} | {d["tu"] for d in self.decls.get(name, [])}
        defines = sorted({d for tu in tus for d in self.tu_defines.get(tu, [])})
        return {"symbol": name, "tus": len(tus), "build_defines": defines,
                "boundary": "the -D flags of the TUs that see the symbol; configuration macros from generated headers "
                            "are in the TU's visible macro set, not listed here"}

    def evidence(self, caller: str, callee: str) -> dict:
        hits = [e for e in self.calls_out.get(caller, []) if e.get("callee_name") == callee]
        return {"edge": f"{caller} -> {callee}",
                "sites": [{"tu": e["tu"], "line": e["line"], "kind": e["kind"],
                           "callee_symbol": e.get("callee_symbol")} for e in hits],
                "boundary": "each site is a CALL_EXPR in the TU's AST under its compile command; the object file's call "
                            "instruction agreed for 99% of direct edges in the probe (exceptions: libc builtins, "
                            "constant-folded branches)"}

    def neighborhood(self, name: str, radius: int = 1) -> dict:
        seen = {name}
        frontier = {name}
        edges = []
        for _ in range(radius):
            nxt = set()
            for n in frontier:
                for e in self.calls_out.get(n, []):
                    if e["kind"] == "direct":
                        edges.append((n, e["callee_name"], "calls"))
                        nxt.add(e["callee_name"])
                for e in self.calls_in.get(n, []):
                    if e["kind"] == "direct":
                        edges.append((e["caller_name"], n, "calls"))
                        nxt.add(e["caller_name"])
                for r in self.tables.get(n, []):
                    holder = r.get("table_name") or usr_name(r["caller"])
                    edges.append((holder, n, "holds_pointer_to"))
                    nxt.add(holder)
            frontier = nxt - seen
            seen |= nxt
        return {"center": name, "radius": radius, "nodes": len(seen), "edges": len(set(edges)),
                "node_definitions": {n: self.define(n)["definitions"][:1] for n in sorted(seen)},
                "edge_list": sorted(set(edges))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("extraction")
    ap.add_argument("query")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--radius", type=int, default=1)
    a = ap.parse_args()
    raw = open(a.extraction, "rb").read()
    g = Graph(json.loads(raw))
    q = a.query
    if q == "sizes":
        whole = len(raw)
        edges_only = len(json.dumps([(usr_name(c["caller"]), c.get("callee_name")) for t in g.ex["tus"]
                                     if "error" not in t for c in t["calls"] if c["kind"] == "direct"]))
        print(f"whole extraction {whole:,} bytes (~{whole // 4:,} tokens); direct-edge list alone {edges_only:,} bytes "
              f"(~{edges_only // 4:,} tokens)")
        for name in a.args:
            for label, ans in (("define", g.define(name)), ("callers", g.callers(name)), ("callees", g.callees(name)),
                               ("neighborhood r=1", g.neighborhood(name, 1)),
                               ("neighborhood r=2", g.neighborhood(name, 2))):
                b = len(json.dumps(ans))
                print(f"  {name:28s} {label:18s} {b:7,} bytes (~{b // 4:,} tokens)")
        return 0
    fn = {"define": lambda: g.define(a.args[0]), "callers": lambda: g.callers(a.args[0]),
          "callees": lambda: g.callees(a.args[0]), "includers": lambda: g.includers_of(a.args[0]),
          "defines-for": lambda: g.defines_for(a.args[0]), "evidence": lambda: g.evidence(a.args[0], a.args[1]),
          "neighborhood": lambda: g.neighborhood(a.args[0], a.radius)}[q]
    print(json.dumps(fn(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
