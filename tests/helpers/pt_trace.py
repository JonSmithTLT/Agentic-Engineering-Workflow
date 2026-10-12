"""Judging a hooked render's spans (the pack-truth plan, reviewed CLEAR, §2.2 and §2.3): every span of the pattern must
trace to exactly one source, and each way of tracing one checks where its text came from.

A span's source is the innermost marker that holds it (``pt_hook.trace``). The judge's branches, each with the check
that keeps it from accepting a whole position (F1-F4 of the prototype's review), and its negative control
(``pt_negatives``):
- **unit** (a code constant, a name bound to one, a module display's leaf, a YAML prose leaf): its key is the
  inventory's ``(file, scope, hash)``. A name or a display leaf is a unit only when its runtime value equals the
  literal. (The inventory and disposition lookup is check 11's, PT-1's remainder: F7.)
- **fence** (an authored input): the fenced text must equal its authored source, read from the cell's pristine state
  copy (``authored``); a span inside a verbatim occurrence of a product string constant in it is that constant's unit.
- **value** (an interpolation): its site must be in the closed registry, and the site's class accessor must accept
  the value.
- **CLI identifier**: positional only. argparse's own output is marked where argparse makes it (pt_hook); within it a
  span must lie in an identifier of the live parser, and argparse's built-in help must be the live parser's.
- **JSON** (decoded first, §2.2): a key must be in its delivery point's closed key list, derived from the result
  method's returned dict (and the schema of a nested record), and hold no whitespace; a value must be in a field the
  registry names, and that class's accessor must accept it.
Anything else is untraced, and the gate fails.

Invariant and scope (M1): every span in a cell's texts is judged; the branches are the only ways to "traced", and each
has a negative control. Coverage limits: fences have authored sources for the fields the cells render (title, the
record's meta and body, the plan, guardrails, checks, authority, the change, the evidence records); the rest
(findings, failure evidence, hierarchy, subject, children, aggregate diffstat) have none yet, so their spans are
untraced. The product-constant check sees string constants (f-string constant parts by their f-string's unit) and the
role YAML; it cannot see prose built from parts at run time.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pt_hook

# The closed value registry (§2.2): an interpolation site, (file, function, expression), and the class of value it
# holds. A site that renders a span and is not listed here fails the gate. Each class must have an accessor.
VALUE_SITES: dict[tuple[str, str, str], str] = {
    ("src/aew/knowledge/context.py", "_bullets", "i"): "role data id",
    ("src/aew/knowledge/context.py", "_launch_contract", "p.workspace"): "workspace path",
    ("src/aew/knowledge/context.py", "_card_section",
     '", ".join(card.get("outputs", [])) or "the archetype\'s standard output"'): "role data id",
    ("src/aew/harness/contract.py", "preamble", "c.workspace"): "workspace path",
    ("src/aew/harness/contract.py", "preamble", "c.scratch"): "path in the cell",
    ("src/aew/harness/contract.py", "preamble", "kinds"): "expected kinds",
    ("src/aew/harness/opencode/projection.py", "system_text", "contract.workspace"): "workspace path",
    ("src/aew/harness/opencode/projection.py", "system_text", "contract.scratch"): "path in the cell",
}
# The delivery points the CLI prints as JSON (its `emit`); decoded before tracing (§2.2), and the result method each
# returns, whose returned dict's keys are that point's closed key list.
JSON_RESULTS: dict[str, tuple[str, str]] = {
    "whoami": ("engine/harness_ops.py", "Harness.invocation_whoami"),
    "check run": ("engine/evidence_ops.py", "EvidenceCommands.check_run"),
    "submit": ("engine/evidence_ops.py", "EvidenceCommands.submit"),
    "context pack": ("engine/context_ops.py", "ContextPacks.context_pack"),
}
JSON_TEXTS = frozenset(JSON_RESULTS)
# A key whose value is a record with a schema: its keys are that schema's properties (schema file, JSON pointer).
NESTED_RECORDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "evaluated_snapshot": ("evidence.schema.json", ("$defs", "snapshot")),
}
# A JSON result's fields whose values are registry values, by (text, key path with list indexes as []).
JSON_FIELDS: dict[tuple[str, str], str] = {
    ("whoami", "/workspace"): "workspace path",
    ("whoami", "/operations[]"): "operation id",
    ("whoami", "/expected_kinds[]"): "expected kinds",
    ("context pack", "/path"): "path in the cell",
    ("submit", "/path"): "path in the cell",
    ("check run", "/log"): "path in the cell",
}


@dataclass
class Facts:
    """What a cell's accessors read: its own pristine state copy, the role's data, the product and the live parser."""

    role: str
    root: Path
    workspace: str
    operations: frozenset[str]
    kinds: frozenset[str]
    role_ids: frozenset[str]
    authored: dict[str, frozenset[str]]
    json_keys: dict[str, frozenset[str]]
    cli_identifiers: tuple[str, ...]
    builtin_help: frozenset[str]


def _inside(path: str, root: Path) -> bool:
    p = os.path.normcase(os.path.realpath(path))
    top = os.path.normcase(os.path.realpath(root))
    return p == top or p.startswith(top + os.sep)


CLASSES: dict[str, Callable[[str, Facts], bool]] = {
    "workspace path": lambda v, f: os.path.normcase(v) == os.path.normcase(f.workspace),
    "path in the cell": lambda v, f: _inside(v, f.root),
    "operation id": lambda v, f: v in f.operations,
    "expected kinds": lambda v, f: all(k in f.kinds for k in v.split(", ")),
    "role data id": lambda v, f: all(x in f.role_ids for x in v.split(", ")),
}


def _spaceless_leaves(obj: Any) -> set[str]:
    return {text for _, text in pt_hook.yaml_leaves(obj) if " " not in text}


@cache
def json_keys() -> dict[str, frozenset[str]]:
    """Each JSON delivery point's closed key list (F2): the constant keys of the dict its result method returns, and
    for a key whose value is a schema'd record, that record's properties. A key with whitespace is never in it."""
    out: dict[str, frozenset[str]] = {}
    for text, (rel, qual) in JSON_RESULTS.items():
        fn = pt_hook.qualnames(ast.parse(pt_hook._read(pt_hook.PKG / rel)))[qual]
        top = {k.value for r in ast.walk(fn) if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict)
               for k in r.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        paths = {f"/{k}" for k in top}
        for key, (schema, pointer) in NESTED_RECORDS.items():
            if key in top:
                node: Any = json.loads(pt_hook._read(pt_hook.PKG / "schemas" / schema))
                for part in pointer:
                    node = node[part]
                paths |= {f"/{key}/{p}" for p in node.get("properties", {})}
        out[text] = frozenset(p for p in paths if not any(c.isspace() for c in p))
    return out


@cache
def product_constants() -> tuple[tuple[str, str], ...]:
    """Every product string constant with a space, as (text, inventory key): src/aew's constants (an f-string's
    constant part keyed by its f-string's unit) and the role YAML's leaves. Longest first."""
    import yaml

    out: dict[str, str] = {}
    for p in sorted(pt_hook.PKG.rglob("*.py")):
        source = pt_hook._read(p)
        tree = ast.parse(source)
        rel = p.relative_to(pt_hook.SRC.parent).as_posix()
        mod = pt_hook._module_name(p)
        local = pt_hook._module_constants(tree)
        names, mods = pt_hook._import_map(tree, mod)
        scopes = pt_hook._outer_scopes(tree)
        keys = pt_hook.node_keys(tree)
        owner: dict[pt_hook.Key, ast.JoinedStr] = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.JoinedStr):
                for m in ast.walk(n):
                    if isinstance(m, ast.Constant):
                        owner.setdefault(keys[id(m)], n)
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and " " in n.value:
                js = owner.get(keys[id(n)])
                text = pt_hook._render_fstring(js, source, local, names, mods) if js is not None else n.value
                at = (js.lineno, js.col_offset) if js is not None else (n.lineno, n.col_offset)
                out.setdefault(n.value, f"{rel}|{scopes.get(at, '<module>')}|{pt_hook.key_hash(text)}")
    for p in sorted((pt_hook.PKG / "roles").rglob("*.yaml")):
        rel = p.relative_to(pt_hook.SRC.parent).as_posix()
        for path, text in pt_hook.yaml_leaves(yaml.safe_load(pt_hook._read(p))):
            if " " in text:
                out.setdefault(text, f"{rel}|{path}|{pt_hook.key_hash(text)}")
    return tuple(sorted(out.items(), key=lambda kv: -len(kv[0])))


@cache
def cli_identifiers() -> tuple[tuple[str, ...], frozenset[str]]:
    """The live parser's identifiers (V11-2): every parser's prog, option strings, metavars and choices; and the text
    argparse gives its own -h and --version actions. Read from argparse, never matched outside its own output."""
    import argparse

    from aew.cli.main import build_parser

    idents: set[str] = set()
    builtin: set[str] = set()

    def walk(parser: argparse.ArgumentParser) -> None:
        idents.add(parser.prog)
        for a in parser._actions:
            idents.update(a.option_strings)
            if a.metavar:
                idents.update(str(m) for m in (a.metavar if isinstance(a.metavar, tuple) else (a.metavar,)))
            if a.choices:
                idents.update(str(c) for c in a.choices)
            if isinstance(a, (argparse._HelpAction, argparse._VersionAction)) and a.help:
                builtin.add(a.help)
            if isinstance(a, argparse._SubParsersAction):
                for sub in a.choices.values():
                    walk(sub)

    walk(build_parser())
    return tuple(sorted(x for x in idents if x)), frozenset(builtin)


def _git(repo: Path, *args: str) -> str:
    kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, **kw).stdout.decode(
        "utf-8", "replace")


def authored_sources(spec: dict[str, Any], pristine: Path) -> dict[str, frozenset[str]]:
    """Each fenced field's authored source (F1), read from the cell's pristine state copy, as the set of texts its
    fenced leaves may be (each stripped, as the fence wraps a leaf's core)."""
    from aew.util import load_yaml, parse_frontmatter

    repo = pristine / Path(spec["repo"]).relative_to(spec["root"])
    aew = repo / ".aew"
    state = load_yaml((aew / "state/control.yaml").read_text(encoding="utf-8"))
    unit = state["work"][spec["work_unit"]]
    inv = state["invocations"][spec["invocation"]]
    meta, body = parse_frontmatter((aew / unit["record"]).read_text(encoding="utf-8"))
    leaves = lambda o: {t.strip() for _, t in pt_hook.yaml_leaves(o) if t.strip()}  # noqa: E731
    out: dict[str, set[str]] = {
        "title": {str(meta.get("title", "")).strip()},
        "record_body": {body.strip()},
        "record_meta": leaves(meta),
        "plan_text": set(),
        "guardrails_text": {(aew / "policy/guardrails.yaml").read_text(encoding="utf-8").strip()},
        "checks": {str(c.get("description", "")).strip() for c in (load_yaml(
            (aew / "policy/checks.yaml").read_text(encoding="utf-8")).get("checks") or {}).values()},
        "authority": {str(a.get("path", "")).strip() for a in (load_yaml(
            (aew / "project.yaml").read_text(encoding="utf-8")).get("authority") or {}).get("accepted") or []},
        "diff": set(), "diffstat": set(), "implementation_summary": set(),
    }
    if unit.get("plan"):
        out["plan_text"] = {parse_frontmatter((aew / unit["plan"]["path"]).read_text(encoding="utf-8"))[1].strip()}
    for p in sorted((aew / "evidence" / spec["work_unit"]).glob("*.md")):
        out["implementation_summary"] |= leaves(parse_frontmatter(p.read_text(encoding="utf-8"))[0])
    base = (unit.get("workspace") or {}).get("base_commit")
    tree = inv["snapshot"]["relevant_inputs_fingerprint"].split(":", 1)[1]
    if base:  # the change, as the pack computes it from the snapshot's tree (context_ops: AEW_EXCLUDE)
        paths = ("--", ".", ":(exclude).aew")
        out["diff"] = {_git(repo, "diff", "--no-color", "--no-renames", base, tree, *paths).strip()}
        out["diffstat"] = {_git(repo, "diff", "--stat", "--no-renames", base, tree, *paths).strip()}
    return {k: frozenset(v - {""}) for k, v in out.items()}


def facts(spec: dict[str, Any], pristine: Path) -> Facts:
    """The cell's accessor data. Its state is read from the pristine copy (``pristine`` mirrors ``spec["root"]``),
    which no render touches."""
    from aew.engine.authority import ROLE_OPERATIONS
    from aew.knowledge.evidence import ROLE_KINDS
    from aew.util import load_yaml

    role = spec["role"]
    repo = pristine / Path(spec["repo"]).relative_to(spec["root"])
    state = load_yaml((repo / ".aew/state/control.yaml").read_text(encoding="utf-8"))
    card = state["invocations"][spec["invocation"]].get("card") or {}
    data = load_yaml((pt_hook.PKG / "roles/archetypes" / f"{role}.yaml").read_text(encoding="utf-8"))
    ids = _spaceless_leaves(data) | _spaceless_leaves(card.get("content") or {})
    idents, builtin = cli_identifiers()
    return Facts(role, Path(spec["root"]), spec["workspace"], frozenset(ROLE_OPERATIONS.get(role, ())),
                 frozenset(ROLE_KINDS.get(role, ())), frozenset(ids), authored_sources(spec, pristine), json_keys(),
                 idents, builtin)


@dataclass(frozen=True)
class Judged:
    text: str  # the delivery point
    span: str
    source: str  # unit | fence | value | json-field | field-name | cli-identifier | untraced
    detail: str  # the key, the fence, the class, or why it is untraced
    context: str
    chain: tuple[str, ...] = ()  # the markers holding it, innermost first
    start: int = 0  # in the delivery point's judged (stripped) text
    end: int = 0


def judged_text(name: str, entry: dict[str, Any]) -> tuple[str, list[tuple[int, int, str, str]]]:
    """The marked text the judge reads, and for a JSON result (decoded first, §2.2: one key or value per line) each
    line's (start, end, kind, key path)."""
    if not (name in JSON_TEXTS and entry["code"] == 0):
        return entry["stdout"] + ("\n" + entry["stderr"] if entry["stderr"] else ""), []
    lines: list[str] = []
    spans: list[tuple[int, int, str, str]] = []
    pos = 0

    def add(text: str, kind: str, path: str) -> None:
        nonlocal pos
        lines.append(text)
        spans.append((pos, pos + len(pt_hook.strip(text)), kind, path))
        pos += len(pt_hook.strip(text)) + 1

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                add(k, "key", f"{path}/{k}")
                walk(v, f"{path}/{k}")
        elif isinstance(obj, list):
            for v in obj:
                walk(v, f"{path}[]")
        else:
            add(obj if isinstance(obj, str) else json.dumps(obj), "value", path)

    walk(json.loads(entry["stdout"]), "")
    return "\n".join(lines), spans


def _in_identifier(value: str, start: int, end: int, idents: tuple[str, ...]) -> bool:
    """Whether [start, end) of ``value`` (argparse's own marked output) lies in an identifier of the live parser."""
    for ident in idents:
        rx = r"(?<![\w-])" + r"\s+".join(map(re.escape, ident.split())) + r"(?![\w-])"
        if any(m.start() <= start and end <= m.end() for m in re.finditer(rx, value)):
            return True
    return False


def judge(name: str, entry: dict[str, Any], registry: dict[str, Any], f: Facts) -> list[Judged]:
    """Every span of one delivery point's text, with its source."""
    text, lines = judged_text(name, entry)
    stripped, spans = pt_hook.trace(text)
    out = []
    for s in spans:
        ctx = stripped[max(0, s.start - 40):s.end + 40]

        def say(source: str, detail: str, chain: tuple[str, ...] = (), _s: Any = s, _c: str = ctx) -> None:
            out.append(Judged(name, _s.text, source, detail, _c, chain, _s.start, _s.end))

        if s.source is not None:
            chain = tuple(f"{m.kind}:{m.ident}" for m in pt_hook.chain(s.source))
            if s.source.kind == "unit":
                u = registry["units"][s.source.ident]
                say("unit", f"{u['file']}|{u['scope']}|{u['hash']}", chain)
                continue
            v = registry["values"][s.source.ident]
            value = stripped[s.source.start:s.source.end]
            rel_start, rel_end = s.start - s.source.start, s.end - s.source.start
            if "fence" in v:
                field = re.split(r"[.\[]", v["fence"], maxsplit=1)[0]
                if value not in f.authored.get(field, frozenset()):
                    say("untraced", f"fenced {v['fence']} is not its authored source", chain)
                    continue
                const = next((key for c, key in product_constants() for i in _occurrences(value, c)
                              if i <= rel_start and rel_end <= i + len(c)), None)
                if const is not None:  # product prose kept in an authored file is still product prose (F1a)
                    say("unit", const, chain)
                else:
                    say("fence", v["fence"], chain)
                continue
            if "cli" in v:
                if v["cli"] == pt_hook.CLI_BUILTIN_HELP:
                    ok = value in f.builtin_help
                else:
                    ok = _in_identifier(value, rel_start, rel_end, f.cli_identifiers)
                say("cli-identifier" if ok else "untraced",
                    v["cli"] if ok else f"argparse {v['cli']} text not of the live parser", chain)
                continue
            cls = VALUE_SITES.get((v["file"], v["function"], v["expr"]))
            if cls is None:
                say("untraced", f"an unregistered value {v['file']}:{v['line']} {v['function']} {v['expr']}", chain)
            elif not CLASSES[cls](value, f):
                say("untraced", f"a {cls} value its accessor refuses: {value!r}", chain)
            else:
                say("value", cls, chain)
            continue
        if s.why == "straddles":
            say("untraced", "straddles a marker boundary")
            continue
        line = next((ln for ln in lines if ln[0] <= s.start and s.end <= ln[1]), None)
        if line is not None:
            _, _, kind, path = line
            if kind == "key":
                if path in f.json_keys.get(name, frozenset()):
                    say("field-name", path)
                else:
                    say("untraced", f"JSON key {path} is not in {name}'s closed key list")
                continue
            cls = JSON_FIELDS.get((name, path))
            if cls is not None and CLASSES[cls](stripped[line[0]:line[1]], f):
                say("json-field", f"{path}: {cls}")
            else:
                say("untraced", f"JSON value {path}")
            continue
        say("untraced", "outside every marker")
    return out


def _occurrences(text: str, sub: str) -> list[int]:
    out, i = [], text.find(sub)
    while i >= 0:
        out.append(i)
        i = text.find(sub, i + 1)
    return out


def judge_render(hooked: dict[str, Any], f: Facts) -> list[Judged]:
    out = []
    for name, entry in hooked["texts"].items():
        out += judge(name, entry, hooked["registry"], f)
    return out


DATA_KINDS = frozenset({"yaml", "fence", "operand"})


def whitespace_inside(hooked: dict[str, Any]) -> list[str]:
    """Data markers (a YAML leaf, a fence, a ``+`` value) whose text starts or ends with whitespace: a renderer's
    ``strip()`` of the value would no longer strip it (item 6 of the review). The invariant: none, in every cell."""
    out = []
    for name, entry in hooked["texts"].items():
        text, _ = judged_text(name, entry)
        stripped, roots = pt_hook.parse(text)
        todo = list(roots)
        while todo:
            m = todo.pop()
            todo += m.children
            info = (hooked["registry"]["units"] if m.kind == "unit" else hooked["registry"]["values"])[m.ident]
            body = stripped[m.start:m.end]
            if info.get("kind") in DATA_KINDS and body != body.strip():
                out.append(f"{name}: {info.get('kind')} {m.ident} {body[:60]!r}")
    return out
