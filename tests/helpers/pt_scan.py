"""The pack-truth render-set scan, as far as the hook needs it (the pack-truth plan, reviewed CLEAR, §2.1): the hook
functions, derived from the tree on every run rather than listed by hand.

The candidates, by kind:
- **renderer:** a module-level function under harness/ or knowledge/ with a parameter annotated ``LaunchContract`` or
  ``PackInputs``;
- **producer:** every function reached, to a fixed point, from the expressions that compute a ``PackInputs`` or
  ``LaunchContract`` constructor's arguments (calls resolved by import), in engine/, maps/, knowledge/ or harness/,
  that makes text (prose in an output position, an f-string, or a ``dump_yaml``/``dumps``/``join`` call);
- **manual-delivery:** ``ContextPacks.context_pack`` and ``context_show``;
- **parser-builder:** every cli/ function that calls a parser builder;
- **result-method:** ``check_run``, ``submit`` and ``invocation_whoami`` in the engine modules behind the worker
  commands.

A producer is a hook function only if its disposition (``PRODUCER_DISPOSITIONS``, the plan's producer file) is worker
text or fenced (V11-1). A producer the scan finds and the table does not name fails closed, and so does a stale entry.

What it can't see (the plan's §2.1): a producer reached only through a callback, or by a name defined nowhere in
src/aew; a delivery point outside these shapes.
"""

from __future__ import annotations

import ast
from functools import cache

import pt_hook

# The disposition of every producer the scan reaches at the plan's base (the plan's producer file, §2.1 and V11-4):
# worker text and fenced producers are hook functions; not-worker-text producers never are.
PRODUCER_DISPOSITIONS: dict[tuple[str, str], str] = {
    ("engine/archive_ops.py", "held_evidence"): "not worker text",
    ("engine/archive_ops.py", "Archive._index"): "not worker text",
    ("engine/archive_ops.py", "Archive.record"): "not worker text",
    ("engine/archive_ops.py", "Archive._load"): "not worker text",
    ("engine/archive_ops.py", "reference_summary"): "fenced",
    ("engine/archive_ops.py", "evidence_reference"): "fenced",
    ("engine/base.py", "Kernel._pinned_bytes"): "not worker text",
    ("engine/context_ops.py", "ContextPacks._input_summaries"): "worker text",
    ("engine/context_ops.py", "ContextPacks._m2_pack_extras"): "worker text",
    ("engine/context_ops.py", "ContextPacks._history_refs"): "fenced",
    ("engine/context_ops.py", "ContextPacks.pack_rel"): "not worker text",
    ("engine/disposition_ops.py", "Dispositions.read"): "not worker text",
    ("engine/disposition_ops.py", "Dispositions._load"): "not worker text",
    ("engine/gates.py", "effective_obligations"): "worker text",
    ("engine/outbox.py", "overflow_path"): "not worker text",
    ("engine/outbox.py", "record_path"): "not worker text",
    ("engine/outbox.py", "segment_path"): "not worker text",
    ("engine/outbox.py", "payload_events"): "not worker text",
    ("engine/outbox.py", "verify_segment"): "not worker text",
    ("engine/outbox.py", "load_segment"): "not worker text",
    ("engine/outbox.py", "LogView._sealed_copy"): "not worker text",
    ("engine/outbox.py", "LogView.record"): "not worker text",
    ("engine/outbox.py", "bump_wake"): "not worker text",
    ("engine/role_ops.py", "Roles.slot_ok"): "not worker text",
    ("engine/role_ops.py", "Roles.effective_role_plan"): "worker text",
    ("engine/role_ops.py", "Roles._specialty_requirement"): "worker text",
    ("engine/role_ops.py", "Roles.resolve_card"): "not worker text",
    ("engine/role_ops.py", "Roles._require_operator_pin"): "not worker text",
    ("engine/role_ops.py", "Roles._card_gate_current"): "not worker text",
    ("engine/seams.py", "GuardTable.resolve"): "not worker text",
    ("engine/stage_intents.py", "StageIntents.read"): "not worker text",
    ("engine/stage_intents.py", "StageIntents._load"): "not worker text",
    ("engine/stage_intents.py", "StageIntents._validate"): "not worker text",
    ("engine/store.py", "deserialize_control"): "not worker text",
    ("engine/store.py", "_applied_marker"): "not worker text",
    ("engine/store.py", "ControlStore._abs"): "not worker text",
    ("engine/store.py", "ControlStore._load"): "not worker text",
    ("engine/store.py", "ControlStore._load_txn"): "not worker text",
    ("engine/store.py", "ControlStore._apply"): "not worker text",
    ("engine/store.py", "ControlStore._post_commit"): "not worker text",
    ("engine/work_ops.py", "WorkUnits.unit"): "not worker text",
    ("engine/workspace_ops.py", "Invocations.invocation_workspace"): "not worker text",
    ("knowledge/context.py", "_bullets"): "worker text",
    ("knowledge/context.py", "_lines_section"): "worker text",
    ("knowledge/context.py", "_cut_marker"): "worker text",
    ("knowledge/context.py", "_notice"): "worker text",
    ("knowledge/evidence.py", "parse_sealed"): "not worker text",
    ("knowledge/evidence.py", "_scan"): "worker text",
    ("maps/canonical.py", "_escape_char"): "not worker text",
    ("maps/canonical.py", "render_bytes"): "not worker text",
    ("maps/canonical.py", "render_text"): "not worker text",
    ("maps/canonical.py", "_check"): "not worker text",
    ("maps/canonical.py", "canonical_json"): "not worker text",
    ("maps/canonical.py", "listing_sha256"): "not worker text",
    ("maps/freshness.py", "_compute"): "not worker text",
    ("maps/gitobjects.py", "_refuse_option"): "not worker text",
    ("maps/gitobjects.py", "resolve"): "not worker text",
    ("maps/gitobjects.py", "list_tree"): "not worker text",
    ("maps/gitobjects.py", "missing_blobs"): "not worker text",
    ("maps/rules.py", "parse"): "not worker text",
    ("maps/slices.py", "lines"): "worker text",
    ("maps/slices.py", "_unavailable"): "worker text",
    ("maps/slices.py", "static_prefix"): "worker text",
    ("maps/slices.py", "_freshness_line"): "worker text",
    ("maps/slices.py", "body"): "worker text",
    ("maps/slices.py", "frame"): "worker text",
    ("maps/store.py", "artifact_rel"): "not worker text",
    ("maps/store.py", "_check_sha"): "not worker text",
    ("maps/store.py", "read_artifact"): "not worker text",
    ("maps/store.py", "parse_artifact"): "worker text",
    ("maps/store.py", "parse_artifact.<locals>.corrupt"): "worker text",
    ("maps/store.py", "read_registry"): "not worker text",
    ("maps/structural.py", "_ancestors"): "not worker text",
}
DISPOSITIONS = frozenset({"worker text", "fenced", "not worker text"})
PARSER_CALLS = ("add_parser", "add_argument", "add_subparsers", "add_argument_group", "ArgumentParser")
CTORS = ("PackInputs", "LaunchContract")
RESULT_METHODS = ("check_run", "submit", "invocation_whoami")


class ScanError(Exception):
    """The scan and the producer dispositions disagree: a producer with no disposition, or a stale disposition."""


def _trees() -> dict[str, ast.Module]:
    return {f.relative_to(pt_hook.PKG).as_posix(): ast.parse(pt_hook._read(f))
            for f in sorted(pt_hook.PKG.rglob("*.py"))}


def _prose_out(fn: ast.AST) -> list[ast.Constant]:
    """String constants with a space in an output position: not a docstring, not inside a raise or a log call, not a
    subscript key, a comparand or a lookup method's first argument."""
    keys = pt_hook.node_keys(fn)
    skip: set[pt_hook.Key] = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            skip.add(keys[id(n.body[0].value)])
        cands: list[ast.AST] = []
        if isinstance(n, ast.Raise):
            cands.append(n)
        elif isinstance(n, ast.Subscript):
            cands.append(n.slice)
        elif isinstance(n, ast.Compare):
            cands += [n.left, *n.comparators]
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in pt_hook.LOOKUP:
            cands += n.args[:1]
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in pt_hook.LOGGING:
            cands += n.args
        for c in cands:
            skip |= {keys[id(k)] for k in ast.walk(c) if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return [c for c in ast.walk(fn) if isinstance(c, ast.Constant) and isinstance(c.value, str) and " " in c.value
            and keys[id(c)] not in skip]


def _makes_text(fn: ast.AST) -> bool:
    if _prose_out(fn):
        return True
    return any(isinstance(c, ast.JoinedStr) or (isinstance(c, ast.Call) and (getattr(c.func, "attr", None) or
               getattr(c.func, "id", None)) in ("dump_yaml", "dumps", "join")) for c in ast.walk(fn))


@cache
def candidates() -> dict[tuple[str, str], str]:
    """Every hook-function candidate, (module, qualified name) -> kind (producers are "producer")."""
    trees = _trees()
    quals = {rel: {id(fn): q for q, fn in pt_hook.qualnames(tree, strict=False).items()}
             for rel, tree in trees.items()}
    defs: dict[tuple[str, str], list[ast.AST]] = {}
    for rel, tree in trees.items():
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.setdefault((rel, n.name), []).append(n)
    modfile = {"aew." + r[:-3].replace("/", ".").removesuffix(".__init__"): r for r in trees}

    def imports_of(rel: str) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
        mods, funcs = {}, {}
        for n in ast.walk(trees[rel]):
            if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                for a in n.names:
                    full = f"{n.module}.{a.name}"
                    if full in modfile:
                        mods[a.asname or a.name] = modfile[full]
                    elif n.module in modfile:
                        funcs[a.asname or a.name] = (modfile[n.module], a.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name in modfile:
                        mods[a.asname or a.name.split(".")[-1]] = modfile[a.name]
        return mods, funcs

    imports = {rel: imports_of(rel) for rel in trees}

    def resolved_calls(rel: str, fn: ast.AST) -> list[tuple[str, ast.AST]]:
        mods, funcs = imports[rel]
        out: list[tuple[str, ast.AST]] = []
        for c in ast.walk(fn):
            if not isinstance(c, ast.Call):
                continue
            f = c.func
            if isinstance(f, ast.Name):
                if f.id in funcs:
                    out += [(funcs[f.id][0], d) for d in defs.get(funcs[f.id], [])]
                out += [(rel, d) for d in defs.get((rel, f.id), [])]
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                if f.value.id == "self":
                    out += [(rel, d) for d in defs.get((rel, f.attr), [])]
                elif f.value.id in mods:
                    out += [(mods[f.value.id], d) for d in defs.get((mods[f.value.id], f.attr), [])]
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute):
                out += [(r, d) for (r, nm), ds in defs.items() if nm == f.attr and r.startswith("engine/") for d in ds]
        return out

    def names_in(expr: ast.AST) -> set[str]:
        return {n.id for n in ast.walk(expr) if isinstance(n, ast.Name)}

    def kwarg_exprs(fn: ast.AST) -> list[ast.expr]:
        """The constructors' argument expressions, with the function's local assignments followed back."""
        exprs = [e for c in ast.walk(fn) if isinstance(c, ast.Call)
                 and (getattr(c.func, "id", None) or getattr(c.func, "attr", None)) in CTORS
                 for e in [*(kw.value for kw in c.keywords), *c.args]]
        assigns = [(t.id, n.value) for n in ast.walk(fn) if isinstance(n, (ast.Assign, ast.AnnAssign))
                   and n.value is not None for tt in (n.targets if isinstance(n, ast.Assign) else [n.target])
                   for t in ast.walk(tt) if isinstance(t, ast.Name)]
        wanted = set().union(*(names_in(e) for e in exprs)) if exprs else set()
        grew = True
        while grew:
            grew = False
            for name, value in assigns:
                if name in wanted and all(value is not e for e in exprs):
                    exprs.append(value)
                    wanted |= names_in(value)
                    grew = True
        return exprs

    out: dict[tuple[str, str], str] = {}

    def add(rel: str, fn: ast.AST, kind: str) -> None:
        out.setdefault((rel, quals[rel][id(fn)]), kind)

    renderers = set()
    for rel, tree in trees.items():
        if rel.startswith(("harness/", "knowledge/")):
            for st in tree.body:
                if isinstance(st, ast.FunctionDef) and any(
                        ast.unparse(a.annotation).strip("'\"") in CTORS for a in st.args.args
                        if a.annotation is not None):
                    add(rel, st, "renderer")
                    renderers.add((rel, id(st)))
    start = [(rel, d) for (rel, _), ds in defs.items() for d in ds
             if any(isinstance(c, ast.Call) and (getattr(c.func, "id", None) or getattr(c.func, "attr", None)) in CTORS
                    for c in ast.walk(d))]
    seen = {(r, id(f)) for r, f in start}
    frontier: list[tuple[str, ast.AST]] = []
    for rel, fn in start:
        frontier += resolved_calls(rel, ast.Module(body=[ast.Expr(e) for e in kwarg_exprs(fn)], type_ignores=[]))
    reach = []
    while frontier:  # to a fixed point (V10-1)
        nxt = []
        for rel, fn in frontier:
            if (rel, id(fn)) in seen or not rel.startswith(("engine/", "maps/", "knowledge/", "harness/")):
                continue
            seen.add((rel, id(fn)))
            reach.append((rel, fn))
            nxt += resolved_calls(rel, fn)
        frontier = nxt
    for rel, fn in reach:
        if (rel, id(fn)) not in renderers and _makes_text(fn):
            add(rel, fn, "producer")
    for n in trees["engine/context_ops.py"].body:
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef) and m.name in ("context_show", "context_pack"):
                    add("engine/context_ops.py", m, "manual-delivery")
    for rel, tree in trees.items():
        if rel.startswith("cli/"):
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                        isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in PARSER_CALLS
                        for c in ast.walk(n)):
                    add(rel, n, "parser-builder")
    for rel in ("engine/evidence_ops.py", "engine/harness_ops.py"):
        for n in ast.walk(trees[rel]):
            if isinstance(n, ast.FunctionDef) and n.name in RESULT_METHODS:
                add(rel, n, "result-method")
    return out


@cache
def hook_functions() -> dict[tuple[str, str], str]:
    """The hook functions (§2.1, V11-1): every candidate but the not-worker-text producers, with its kind. Raises
    :class:`ScanError` if the scan and the producer dispositions disagree."""
    cands = candidates()
    producers = {k for k, kind in cands.items() if kind == "producer"}
    missing = sorted(producers - set(PRODUCER_DISPOSITIONS))
    stale = sorted(set(PRODUCER_DISPOSITIONS) - producers)
    unknown = sorted(k for k, d in PRODUCER_DISPOSITIONS.items() if d not in DISPOSITIONS)
    if missing or stale or unknown:
        raise ScanError(f"producers without a disposition {missing}; stale dispositions {stale}; unknown {unknown}")
    out = {}
    for k, kind in cands.items():
        if kind == "producer":
            if PRODUCER_DISPOSITIONS[k] == "not worker text":
                continue
            kind = f"producer:{PRODUCER_DISPOSITIONS[k]}"
        out[k] = kind
    return out
