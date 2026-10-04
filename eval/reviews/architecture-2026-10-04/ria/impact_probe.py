"""Requirement impact-surface probe (architecture review, third brief Part C): how much of a change's real surface can a
deterministic pass predict from the requirement's seed terms and the repository's facts, before anyone plans?

  python impact_probe.py TREE --case 1|2|3 [--json OUT]

For each case: a requirement (from a real commit's message), its base commit, and the ground truth (the src/ and tests/
files the commits actually changed). The probe reads the base commit's tree from Git objects only (no checkout), builds
a Python symbol/call index with `ast`, resolves seed terms to symbols, files, transition ops, error codes, schema keys,
oracle rules (tests/helpers/invariants.py) and ADR mentions, expands one hop of callers/callees by name, and scores the
predicted file set against the truth at three levels: seeds only, plus radius 1, plus tests that name the symbols.
It also lists the constraints it surfaced (rules, ADRs, schema fields, ops), which a reviewer judges by hand.

Deterministic, read-only, no model. What it cannot do is the point of the note: it predicts *where*, not *what* or *why*.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict

CASES = {
    "1": {"name": "integration recovery", "base": "ce794fb", "commits": ["9102b9b"],
          "requirement": "A later operator commit never strands a publish; integration failures are named rightly.",
          "seeds": [r"integrat", r"publish", r"recover", r"resume", r"strand"]},
    "2": {"name": "mutating concurrency above 1 (M4-C)", "base": "ce794fb", "commits": ["e91ab4f", "c2cf8be", "a98556e"],
          "requirement": "Mutating concurrency above 1: parallel Ticket execution with a single serial integration lease; "
                         "both concurrency caps are admission rules checked by the walks; doctor reports the enforced cap.",
          "seeds": [r"concurren", r"serial", r"(^|_)cap(s|_|$)", r"workspace", r"worktree", r"mutating", r"lease"]},
    "3": {"name": "one dispatch predicate (M4-A)", "base": "4cc8bd8", "commits": ["a149563", "6746033"],
          "requirement": "One dispatch predicate (DispatchDecision) on every dispatch route; Class 0 eligibility enforced "
                         "at dispatch; acceptance checks gate completion.",
          "seeds": [r"dispatch", r"assign", r"eligib", r"class_?0|risk_class", r"predicate", r"admission|admit",
                    r"acceptance_check"]},
}
GENERIC_NAMES = {"get", "set", "run", "read", "write", "commit", "update", "load", "save", "main", "state", "ok", "error",
                 "items", "append", "add", "pop", "keys", "values", "join", "split", "format", "copy", "exists", "open",
                 "close", "start", "stop", "wait", "check", "validate", "render", "parse", "dump", "list", "dict", "str",
                 "int", "len", "sorted", "any", "all", "isinstance", "repr", "print", "path", "name", "id", "kind"}


def git(tree: str, *args: str) -> str:
    return subprocess.run(["git", "-C", tree, *args], capture_output=True, text=True, check=True,
                          encoding="utf-8", errors="replace").stdout


def truth_files(tree: str, commits: list[str]) -> set[str]:
    files: set[str] = set()
    for c in commits:
        for f in git(tree, "show", "--name-only", "--format=", c).split("\n"):
            if f.startswith(("src/", "tests/")) and f.endswith(".py"):
                files.add(f)
    return files


class Index:
    def __init__(self, tree: str, base: str) -> None:
        self.tree, self.base = tree, base
        listing = git(tree, "ls-tree", "-r", "--name-only", "--full-tree", base).split("\n")
        self.files = [f for f in listing if f]
        self.py = [f for f in self.files if f.endswith(".py") and f.startswith(("src/", "tests/"))]
        self.text: dict[str, str] = {}
        self.symbols: dict[str, dict] = {}            # qualname -> {file, line, kind}
        self.by_name: dict[str, list[str]] = defaultdict(list)  # simple name -> qualnames
        self.calls: dict[str, set[str]] = defaultdict(set)      # qualname -> simple names called
        self.ops: dict[str, set[str]] = defaultdict(set)        # op string -> files
        self.errors: dict[str, str] = {}              # error class -> file
        self._load()

    def show(self, path: str) -> str:
        if path not in self.text:
            self.text[path] = git(self.tree, "show", f"{self.base}:{path}")
        return self.text[path]

    def _load(self) -> None:
        for f in self.py:
            try:
                tree = ast.parse(self.show(f))
            except SyntaxError:
                continue
            self._walk_module(f, tree)

    def _walk_module(self, f: str, tree: ast.Module) -> None:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add(f, node.name, node, "function")
            elif isinstance(node, ast.ClassDef):
                self.symbols[node.name] = {"file": f, "line": node.lineno, "kind": "class"}
                self.by_name[node.name].append(node.name)
                if f.endswith("errors.py"):
                    self.errors[node.name] = f
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._add(f, f"{node.name}.{sub.name}", sub, "method")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"[a-z_]+\.[a-z_.]+", node.value):
                self.ops[node.value].add(f)

    def _add(self, f: str, qual: str, node: ast.AST, kind: str) -> None:
        self.symbols[qual] = {"file": f, "line": node.lineno, "kind": kind}
        self.by_name[qual.rsplit(".", 1)[-1]].append(qual)
        called: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        self.calls[qual] = called

    def callers_of(self, qual: str) -> set[str]:
        name = qual.rsplit(".", 1)[-1]
        if name in GENERIC_NAMES:
            return set()
        return {q for q, called in self.calls.items() if name in called and q != qual}

    def callees_of(self, qual: str) -> set[str]:
        out: set[str] = set()
        for name in self.calls.get(qual, ()):
            if name in GENERIC_NAMES:
                continue
            out.update(self.by_name.get(name, []))
        return out


def analyse(ix: Index, case: dict) -> dict:
    seeds = [re.compile(s, re.I) for s in case["seeds"]]

    def hit(text: str) -> bool:
        return any(s.search(text) for s in seeds)

    seed_syms = {q for q in ix.symbols if hit(q) and ix.symbols[q]["file"].startswith("src/")}
    seed_files = {ix.symbols[q]["file"] for q in seed_syms} | {f for f in ix.files if f.startswith("src/") and hit(f.rsplit("/", 1)[-1])}
    seed_ops = {op: sorted(fs) for op, fs in ix.ops.items() if hit(op)}
    for fs in seed_ops.values():
        seed_files.update(f for f in fs if f.startswith("src/"))
    r1_syms: set[str] = set()
    for q in seed_syms:
        r1_syms |= ix.callers_of(q) | ix.callees_of(q)
    r1_syms -= seed_syms
    r1_files = {ix.symbols[q]["file"] for q in r1_syms if ix.symbols[q]["file"].startswith("src/")} - seed_files
    names = {q.rsplit(".", 1)[-1] for q in seed_syms | r1_syms} - GENERIC_NAMES
    test_files = set()
    for f in ix.py:
        if f.startswith("tests/") and f != "tests/helpers/invariants.py":
            text = ix.show(f)
            if hit(f.rsplit("/", 1)[-1]) or any(re.search(rf"\b{re.escape(n)}\b", text) for n in names if len(n) > 6):
                test_files.add(f)
    rules = [ln.strip()[:140] for ln in ix.show("tests/helpers/invariants.py").split("\n")
             if "problems.append" in ln and hit(ln)] if "tests/helpers/invariants.py" in ix.py else []
    schema_hits = {}
    for f in ix.files:
        if f.startswith("src/aew/schemas/") and f.endswith(".json"):
            keys = sorted({k for k in re.findall(r'"([a-zA-Z_]+)"\s*:', ix.show(f)) if hit(k)})
            if keys:
                schema_hits[f] = keys[:8]
    adrs = {}
    for f in ix.files:
        if "/adr/" in f and f.endswith(".md"):
            n = sum(1 for ln in ix.show(f).split("\n") if hit(ln))
            if n:
                adrs[f.rsplit("/", 1)[-1]] = n
    errors = sorted(e for e in ix.errors if hit(e))
    return {"seed_symbols": sorted(seed_syms), "seed_files": sorted(seed_files), "seed_ops": seed_ops,
            "r1_symbols": len(r1_syms), "r1_files": sorted(r1_files), "test_files": sorted(test_files),
            "constraints": {"oracle_rules": rules, "schema_keys": schema_hits, "adr_mentions": dict(sorted(adrs.items(), key=lambda x: -x[1])),
                            "error_codes": errors}}


def score(pred: set[str], truth: set[str]) -> dict:
    tp = pred & truth
    return {"predicted": len(pred), "truth": len(truth), "hit": len(tp), "recall": round(len(tp) / max(1, len(truth)), 2),
            "precision": round(len(tp) / max(1, len(pred)), 2), "missed": sorted(truth - pred), "extra": sorted(pred - truth)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree")
    ap.add_argument("--case", required=True, choices=sorted(CASES))
    ap.add_argument("--json")
    a = ap.parse_args()
    case = CASES[a.case]
    truth = truth_files(a.tree, case["commits"])
    ix = Index(a.tree, case["base"])
    existing = set(ix.files)
    created = sorted(truth - existing)  # files the change created: no location-based prediction can name them
    truth_src = {f for f in truth if f.startswith("src/") and f in existing}
    truth_tests = {f for f in truth if f.startswith("tests/") and f in existing}
    r = analyse(ix, case)
    seeds = set(r["seed_files"])
    r1 = seeds | set(r["r1_files"])
    out = {"case": case["name"], "requirement": case["requirement"], "base": case["base"], "commits": case["commits"],
           "index": {"python_files": len(ix.py), "symbols": len(ix.symbols)},
           "analysis": r,
           "scores": {"src: seeds only": score(seeds, truth_src), "src: seeds + radius 1": score(r1, truth_src),
                      "tests: named symbols": score(set(r["test_files"]), truth_tests)}}
    out["created_files"] = created
    print(f"== case {a.case}: {case['name']} (base {case['base']}, truth {len(truth_src)} existing src + {len(truth_tests)} "
          f"existing test files; {len(created)} files created by the change: {[c.rsplit('/', 1)[-1] for c in created]})")
    print(f"requirement: {case['requirement']}")
    print(f"index: {len(ix.py)} python files, {len(ix.symbols)} symbols; seed symbols {len(r['seed_symbols'])}, "
          f"seed ops {len(r['seed_ops'])}, radius-1 symbols {r['r1_symbols']}")
    for label, sc in out["scores"].items():
        print(f"  {label:26s} predicted {sc['predicted']:3d} truth {sc['truth']:3d} hit {sc['hit']:3d} "
              f"recall {sc['recall']:.2f} precision {sc['precision']:.2f}")
        if sc["missed"]:
            print(f"     missed: {sc['missed']}")
    c = r["constraints"]
    print(f"  constraints surfaced: {len(c['oracle_rules'])} oracle rules, {len(c['schema_keys'])} schema files, "
          f"{len(c['adr_mentions'])} ADRs ({list(c['adr_mentions'].items())[:4]}), error codes {c['error_codes'][:6]}")
    for ln in c["oracle_rules"][:6]:
        print(f"     rule: {ln}")
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
