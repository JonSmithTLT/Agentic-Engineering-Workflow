"""Judging a hooked render's spans (the pack-truth plan, reviewed CLEAR, §2.2 and §2.3): every span of the pattern must
trace to exactly one source.

A span's source is the innermost marker that holds it (``pt_hook.trace``):
- a **unit** (a code constant or a YAML prose leaf), with its inventory key ``(file, scope, hash)``;
- a **fenced** authored input (the requirement, plan, guardrails, project configuration, evidence records);
- a **registered value**: an interpolation whose site the closed registry below names, and whose value that entry's
  accessor confirms.
Text with no marker is traced only where the closed registry has an accessor for it: a JSON result's field names and
the values of named fields (§2.2: decoded first), and the CLI identifiers of the help texts, read from the live parser
(V11-2). Anything else is untraced, and the gate fails.
"""

from __future__ import annotations

import ast
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pt_hook

# The closed value registry (§2.2): an interpolation site, (file, function, expression), and the class of value it
# holds. A site that renders a span and is not listed here fails the gate. Hand-listed: keys are distinct by
# construction (a dict) and each class must have an accessor (checked by the tests).
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
# The delivery points the CLI prints as JSON (its `emit`); decoded before tracing (§2.2).
JSON_TEXTS = frozenset({"whoami", "check run", "context pack", "submit"})
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
    """What a cell's accessors read: its own state copy, the role's data and the live parser."""

    role: str
    root: Path
    workspace: str
    operations: frozenset[str]
    kinds: frozenset[str]
    role_ids: frozenset[str]
    field_names: frozenset[str]
    cli_identifiers: tuple[str, ...]


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


def field_names() -> frozenset[str]:
    """Every dict key the product writes as a constant, and every property its schemas define: the names a JSON result
    can carry."""
    names: set[str] = set()
    for p in sorted(pt_hook.PKG.rglob("*.py")):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Dict):
                names |= {k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    for p in sorted((pt_hook.PKG / "schemas").glob("*.json")):
        def props(o: Any) -> None:
            if isinstance(o, dict):
                names.update(k for k in (o.get("properties") or {}) if isinstance(k, str))
                for v in o.values():
                    props(v)
            elif isinstance(o, list):
                for v in o:
                    props(v)
        props(json.loads(p.read_text(encoding="utf-8")))
    return frozenset(names)


def cli_identifiers() -> tuple[str, ...]:
    """The CLI identifiers registry entry (V11-2), read from the live parser: every parser's prog, option strings,
    metavars and choices (subcommand names among them), and the text argparse itself gives its help and version
    actions."""
    import argparse

    from aew.cli.main import build_parser

    out: set[str] = set()

    def walk(parser: argparse.ArgumentParser) -> None:
        out.add(parser.prog)
        for a in parser._actions:
            out.update(a.option_strings)
            if a.metavar:
                out.update(str(m) for m in (a.metavar if isinstance(a.metavar, tuple) else (a.metavar,)))
            if a.choices:
                out.update(str(c) for c in a.choices)
            if isinstance(a, (argparse._HelpAction, argparse._VersionAction)) and a.help:
                out.add(a.help)
            if isinstance(a, argparse._SubParsersAction):
                for sub in a.choices.values():
                    walk(sub)

    walk(build_parser())
    return tuple(sorted(x for x in out if x))


def facts(spec: dict[str, Any], pristine: Path, *, fields: frozenset[str], cli: tuple[str, ...]) -> Facts:
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
    return Facts(role, Path(spec["root"]), spec["workspace"], frozenset(ROLE_OPERATIONS.get(role, ())),
                 frozenset(ROLE_KINDS.get(role, ())), frozenset(ids), fields, cli)


@dataclass(frozen=True)
class Judged:
    text: str  # the delivery point
    span: str
    source: str  # unit | fence | value | json-field | field-name | cli-identifier | untraced
    detail: str  # the key, the fence, the class, or why it is untraced
    context: str
    chain: tuple[str, ...] = ()  # the markers holding it, innermost first


def _json_lines(entry: dict[str, Any]) -> tuple[str, list[tuple[int, int, str, str]]]:
    """A JSON result decoded (§2.2), one key or value per line, with each line's (start, end, kind, key path)."""
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


def _cli_cover(text: str, cli: tuple[str, ...]) -> list[tuple[int, int]]:
    cover = []
    for ident in cli:
        rx = r"(?<![\w-])" + r"\s+".join(map(re.escape, ident.split())) + r"(?![\w-])"
        cover += [m.span() for m in re.finditer(rx, text)]
    return cover


def judge(name: str, entry: dict[str, Any], registry: dict[str, Any], f: Facts) -> list[Judged]:
    """Every span of one delivery point's text, with its source."""
    json_text = name in JSON_TEXTS and entry["code"] == 0
    if json_text:
        text, lines = _json_lines(entry)
    else:
        text, lines = entry["stdout"] + ("\n" + entry["stderr"] if entry["stderr"] else ""), []
    stripped, spans = pt_hook.trace(text)
    cover = _cli_cover(stripped, f.cli_identifiers) if name.startswith("help ") else []
    out = []
    for s in spans:
        ctx = stripped[max(0, s.start - 40):s.end + 40]
        if s.source is not None:
            chain = tuple(f"{m.kind}:{m.ident}" for m in pt_hook.chain(s.source))
            if s.source.kind == "unit":
                u = registry["units"][s.source.ident]
                out.append(Judged(name, s.text, "unit", f"{u['file']}|{u['scope']}|{u['hash']}", ctx, chain))
                continue
            v = registry["values"][s.source.ident]
            if "fence" in v:
                out.append(Judged(name, s.text, "fence", v["fence"], ctx, chain))
                continue
            cls = VALUE_SITES.get((v["file"], v["function"], v["expr"]))
            value = stripped[s.source.start:s.source.end]
            if cls is None:
                out.append(Judged(name, s.text, "untraced", f"an unregistered value {v['file']}:{v['line']} "
                                  f"{v['function']} {v['expr']}", ctx, chain))
            elif not CLASSES[cls](value, f):
                out.append(Judged(name, s.text, "untraced", f"a {cls} value its accessor refuses: {value!r}", ctx,
                                  chain))
            else:
                out.append(Judged(name, s.text, "value", cls, ctx, chain))
            continue
        if s.why == "straddles":
            out.append(Judged(name, s.text, "untraced", "straddles a marker boundary", ctx))
            continue
        line = next((ln for ln in lines if ln[0] <= s.start and s.end <= ln[1]), None)
        if line is not None:
            _, _, kind, path = line
            key = path.rsplit("/", 1)[-1]
            if kind == "key" and key in f.field_names:
                out.append(Judged(name, s.text, "field-name", key, ctx))
                continue
            cls = JSON_FIELDS.get((name, path)) if kind == "value" else None
            value = stripped[line[0]:line[1]]
            if cls is not None and CLASSES[cls](value, f):
                out.append(Judged(name, s.text, "json-field", f"{path}: {cls}", ctx))
                continue
            out.append(Judged(name, s.text, "untraced", f"JSON {kind} {path}", ctx))
            continue
        if any(a <= s.start and s.end <= b for a, b in cover):
            out.append(Judged(name, s.text, "cli-identifier", "the live parser", ctx))
            continue
        out.append(Judged(name, s.text, "untraced", "outside every marker", ctx))
    return out


def judge_render(hooked: dict[str, Any], f: Facts) -> list[Judged]:
    out = []
    for name, entry in hooked["texts"].items():
        out += judge(name, entry, hooked["registry"], f)
    return out
