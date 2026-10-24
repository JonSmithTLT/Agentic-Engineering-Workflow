"""YAML nesting is bounded (``util.YAML_MAX_DEPTH``), on both sides. libyaml's composer recurses in C with no depth
check, so a hostile document deep enough kills the process on Windows (a stack overflow, no exception); the
pure-Python composer raises RecursionError. So a document past the bound is refused before anything is composed, as a
ValidationFailed (reason ``yaml_too_deep``) on every platform and Python, the control store's own files included. AEW's
writer holds the same bound, so a document AEW wrote is never refused when it is read back."""

from __future__ import annotations

import ast
import functools
import inspect
import os
import random
import types
from collections import Counter
from pathlib import Path

import pytest
import yaml

from aew import util
from aew.cli import fields
from aew.engine.store import CHECKSUM_PREFIX, Transition, deserialize_control
from aew.errors import UsageError, ValidationFailed

ROOT = Path(__file__).resolve().parents[2]


def flow(depth: int) -> str:
    return "k: " + "[" * depth + "x" + "]" * depth + "\n"


def block(depth: int) -> str:
    return "".join(f"{'  ' * i}k{i}:\n" for i in range(depth + 1)) + f"{'  ' * (depth + 1)}v\n"


def nested(depth: int) -> object:
    """``depth`` mappings, one inside the other."""
    data: object = "x"
    for _ in range(depth):
        data = {"k": data}
    return data


@pytest.mark.parametrize("shape", [flow, block], ids=["flow", "block"])
def test_a_document_nested_past_the_bound_is_refused_and_one_at_the_bound_reads(shape):
    # flow(n) nests n sequences in one mapping, block(n) n mappings: both are n + 1 deep with the outer mapping
    at_bound = shape(util.YAML_MAX_DEPTH - 1)
    assert util.yaml_too_deep(at_bound) is None and util.load_yaml(at_bound) is not None
    with pytest.raises(ValidationFailed) as refused:
        util.load_yaml(shape(util.YAML_MAX_DEPTH), source="hostile.yaml")
    assert refused.value.details == {"reason": util.YAML_TOO_DEEP, "limit": util.YAML_MAX_DEPTH,
                                     "line": refused.value.details["line"]}
    assert refused.value.message.startswith("hostile.yaml: the YAML nests deeper than 64 levels")


def test_a_read_refusal_says_what_to_do_instead():
    with pytest.raises(ValidationFailed) as refused:
        util.load_yaml(flow(util.YAML_MAX_DEPTH), source="hostile.yaml")
    assert refused.value.message.endswith("flatten it to at most 64 levels of mappings and sequences")


def test_a_document_deep_enough_to_crash_the_composer_is_refused_in_process():
    """200,000 levels: composing this kills the interpreter on Windows (about 2,660 levels on Python 3.11), so a
    refusal here, in this process, shows the bound is checked before the document is composed."""
    with pytest.raises(ValidationFailed) as refused:
        util.load_yaml(flow(200_000))
    assert refused.value.details["reason"] == util.YAML_TOO_DEEP and refused.value.details["line"] == 1


def test_a_deep_control_state_resealed_by_another_writer_is_refused_in_process(tmp_path):
    """The checksum keeps out damage, not a writer: a same-account process, a worker on Windows or a git checkout can
    write control state and recompute the hash. 5,000 levels kill the process on Windows when composed (from about
    2,660 on Python 3.11 and 3,970 on 3.13), so a refusal here shows the store's own reads pass the bound too (review
    of #236, F1)."""
    from store_model import init

    init(tmp_path)
    raw = (tmp_path / "state" / "control.yaml").read_text(encoding="utf-8")
    body = raw[:raw.rindex(CHECKSUM_PREFIX)] + flow(5_000).replace("k:", "zz_planted:")
    resealed = (body + f"{CHECKSUM_PREFIX}{util.sha256_bytes(body.encode('utf-8'))}\n").encode("utf-8")
    with pytest.raises(ValidationFailed) as refused:
        deserialize_control(resealed, source="control.yaml")
    assert refused.value.details["reason"] == util.YAML_TOO_DEEP
    assert refused.value.message.startswith("control.yaml: the YAML nests deeper than 64 levels")


def test_a_syntax_error_is_still_invalid_yaml_and_not_a_depth_refusal():
    with pytest.raises(ValidationFailed) as refused:
        util.load_yaml("k: [unclosed\n", source="broken.yaml")
    assert "invalid YAML" in refused.value.message and "reason" not in refused.value.details


def test_a_cli_fields_value_nested_past_the_bound_is_a_usage_error_not_a_recursion_error():
    with pytest.raises(UsageError, match="nests deeper than 64 levels"):
        fields._load(flow(5_000))
    assert fields._load("title: a\ngoal: [b, c]\n") == {"title": "a", "goal": ["b", "c"]}


@pytest.mark.parametrize("dump", [util.dump_yaml, util.safe_dump_yaml], ids=["dump_yaml", "safe_dump_yaml"])
def test_aew_writes_a_document_at_the_bound_reads_it_back_and_refuses_one_past_it(dump):
    """Nothing AEW writes can be refused when it is read: control state has free-form objects, and with a bound on
    reading alone, one deep value committed there would make the project's own store unreadable."""
    at_bound = nested(util.YAML_MAX_DEPTH)
    assert util.load_yaml(dump(at_bound)) == at_bound
    with pytest.raises(ValidationFailed) as refused:
        dump(nested(util.YAML_MAX_DEPTH + 1))
    assert refused.value.details == {"reason": util.YAML_TOO_DEEP, "limit": util.YAML_MAX_DEPTH}
    assert refused.value.message.startswith("the data nests deeper than 64 levels under its top-level key 'k': ")
    with pytest.raises(ValidationFailed) as refused:
        dump([nested(util.YAML_MAX_DEPTH)])  # no top-level key to name
    assert refused.value.message.startswith("the data nests deeper than 64 levels: ")
    assert util.load_yaml(dump([nested(util.YAML_MAX_DEPTH - 1)] * 3)) == [nested(util.YAML_MAX_DEPTH - 1)] * 3


@pytest.mark.parametrize("dump", [util.dump_yaml, util.safe_dump_yaml], ids=["dump_yaml", "safe_dump_yaml"])
def test_a_write_refusal_names_the_document_and_the_top_level_key_that_nests_too_deep(dump):
    """What was refused (review of #236, F3). The key is found without recursing, so a value nested far past Python's
    recursion limit is named too."""
    data = {"shallow": {"a": [1, 2]}, "deep": nested(100_000), "after": 1}
    with pytest.raises(ValidationFailed) as refused:
        dump(data, source="control state")
    assert refused.value.message.startswith("control state: the data nests deeper than 64 levels under its top-level "
                                            "key 'deep': ")
    assert refused.value.message.endswith("give that value less nesting")
    assert refused.value.details == {"reason": util.YAML_TOO_DEEP, "limit": util.YAML_MAX_DEPTH}


def test_the_bounded_writers_write_exactly_what_they_wrote_before():
    sample = {"id": "DR-0001", "subject": {"id": "T-0001", "kind": "ticket"}, "choice": "keep", "rev": 3,
              "notes": ["a: b", "multi\nline", "üñí", "#1"], "nested": [{"k": [1, 2, {"x": None}]}], "empty": {}}

    class Unbounded(util._SafeDumperBase):  # type: ignore[valid-type,misc]
        pass

    Unbounded.add_representer(str, util._str_representer)
    assert util.dump_yaml(sample) == yaml.dump(sample, Dumper=Unbounded, sort_keys=False, allow_unicode=True,
                                               default_flow_style=False, width=100)
    assert util.safe_dump_yaml(sample) == yaml.safe_dump(sample, sort_keys=False, allow_unicode=True)


def test_a_commit_whose_state_nests_past_the_bound_is_refused_and_writes_nothing(tmp_path):
    """A token's scope is free-form in control state's schema, so a value nested that deep passes validation; the
    commit is refused when control state is serialized, before anything touches disk, and the refusal names it."""
    from store_model import check_invariants, init, one_transaction

    store = init(tmp_path)
    one_transaction(store)
    control = tmp_path / "state" / "control.yaml"
    txn = tmp_path / "state" / "txn"
    before, txns = control.read_bytes(), sorted(txn.glob("*"))
    with store.session() as s:
        s.state["tokens"]["deep"] = {"kind": "lead", "verifier": "0" * 64, "scope": nested(util.YAML_MAX_DEPTH),
                                     "issued_at": "2026-10-23T00:00:00Z", "issued_by_generation": 0}
        s.write("records/item-deep.md", "x\n")
        with pytest.raises(ValidationFailed) as refused:
            s.commit(Transition(op="deep", actor={"kind": "test"}))
    assert refused.value.details["reason"] == util.YAML_TOO_DEEP
    assert refused.value.message.startswith("control state: the data nests deeper than 64 levels under its top-level "
                                            "key 'tokens'")
    assert control.read_bytes() == before and sorted(txn.glob("*")) == txns  # no redo record either
    assert not (tmp_path / "records" / "item-deep.md").exists()
    assert check_invariants(tmp_path) == 1
    one_transaction(store)  # the store is untouched: the next commit proceeds
    assert check_invariants(tmp_path) == 2


def yaml_documents() -> list[Path]:
    """Every YAML file in the checkout (the web app's dependencies and git's own files left out)."""
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".venv", "__pycache__"}]
        found += [Path(dirpath) / f for f in filenames if f.endswith((".yaml", ".yml"))]
    return sorted(found)


def test_every_yaml_document_in_the_repository_is_within_the_bound():
    """The bound never refuses a document AEW has: the deepest is 13 levels (the dashboard contract, 2026-10-23)."""
    documents = yaml_documents()
    assert len(documents) > 50 and ROOT / ".github" / "workflows" / "ci.yml" in documents
    too_deep = {}
    for path in documents:
        try:
            line = util.yaml_too_deep(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue  # not YAML AEW parses (a template, a deliberate syntax error); its parse would be refused anyway
        if line is not None:
            too_deep[str(path.relative_to(ROOT))] = line
    assert too_deep == {}


# Every place the product composes or writes YAML outside util's bounded functions, and why it is safe, counted by
# (file, the function it is in). A new site joins a list with its reason, or goes through `util.load_yaml`,
# `util.dump_yaml` or `util.safe_dump_yaml`; a second site in a listed function is red too (review of #236, F2).
#
# What is seen, derived from the installed yaml package rather than restated (review of #236, R2-F2, R3-F2). It is a
# lower bound on the spellings in src/aew, not a proof that no site exists:
# - a chain `yaml.a.b...` written with the bare name `yaml` is resolved against the yaml module, prefix by prefix. A
#   prefix that is one of the composing or writing functions is a site, whatever follows it (`yaml.safe_load.__call__`).
#   Every function defined in `yaml/__init__` is classified once, below, and a test fails when PyYAML adds one there.
# - a class is composing when it has `get_single_node` (the composer: every loader, `Composer`, libyaml's `CParser`) and
#   writing when it has `represent`, `serialize` or `emit` (every dumper, the representers, `Serializer`, `Emitter`,
#   `CEmitter`). Such a class is a site where it is written out and driven in place: called, subclassed, or reached
#   through `__call__`/`__new__`. Passing one as an argument (`Loader=yaml.BaseLoader`) composes nothing.
# - a chain that does not resolve, reaches a namespace (`yaml.__dict__`), or is assigned to is a lookup site, and so is
#   every bare `yaml` name that is not the root of a chain: `getattr(yaml, ...)`, `vars(yaml)`, `y = yaml`, `f(yaml)`.
# - yaml is imported as `import yaml` only: `from yaml import`, an alias, a submodule import, and `__import__` or
#   `import_module` of the constant "yaml" (its name positional or keyword) are sites.
# - util's own yaml objects (`util.yaml`, `_SafeLoader`, the dumpers: every name util binds to a yaml object, derived)
#   are sites where another module reaches them by `from aew import util`, `import aew.util` or `from aew.util import`.
# Limits, not claimed. None of these is seen, and none of these spellings occurs in src/aew today (grep, 2026-10-24; its
# two computed imports, doctor.py's `__import__(module)` and harness/registry.py's `import_module(where)`, take names
# from AEW's own lists and compose nothing):
# 1. a composing or writing class bound to a name and then driven (`L = yaml.SafeLoader; L(t)`, or the backend choice
#    `yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader`); a class used as a decorator, in `type(...)`,
#    with `object.__new__` or `getattr(cls, "__call__")`; one held in a tuple or a default argument, or in `partial`;
# 2. a submodule of yaml handed on (`m = yaml.cyaml; m.CParser(t)`, `getattr(yaml.loader, "SafeLoader")`, `vars(...)`);
# 3. util reached other than by those three absolute imports: a relative import, `import aew` or `import aew.x.y` then
#    `aew.util.`, or `importlib.import_module("aew.util")`;
# 4. util's own names driven inside util.py (`_SafeLoader(t)` or `_Dumper(s)` in a new function there; only a new
#    module-level class built on them is seen, by `test_utils_own_yaml_objects_are_derived_from_util`);
# 5. another AEW module's yaml (`from aew.cli.fields import yaml as y`, `fields.yaml.safe_load`);
# 6. yaml found by name another way: `pkgutil.resolve_name`, `sys.modules["yaml"]`, `globals()["yaml"]`, or an import by
#    a computed name;
# 7. a function that `yaml/__init__` re-exports from a submodule, or a C function: the completeness test below does
#    not list it, and a call to it is counted as nothing (a new class is seen, by what it can do);
# and `exec` and `eval`, and YAML parsed inside a C extension or a dependency.
COMPOSERS = {"load", "safe_load", "full_load", "unsafe_load", "load_all", "safe_load_all", "full_load_all",
             "unsafe_load_all", "compose", "compose_all"}
DUMPERS = {"dump", "safe_dump", "dump_all", "safe_dump_all", "serialize", "serialize_all", "emit"}
NEITHER = {"scan": "tokens only", "parse": "events only: yaml_too_deep's own walk",
           "add_constructor": "registers a constructor", "add_multi_constructor": "registers a constructor",
           "add_implicit_resolver": "registers a resolver", "add_path_resolver": "registers a resolver",
           "add_representer": "registers a representer", "add_multi_representer": "registers a representer",
           "warnings": "PyYAML's deprecated warning switch"}
COMPOSING_CLASS = ("get_single_node",)
WRITING_CLASS = ("represent", "serialize", "emit")
COMPOSING = {
    ("src/aew/util.py", "load_yaml"): (1, "bounded by yaml_too_deep first"),
    ("src/aew/cli/fields.py", "_load"): (1, "bounded by yaml_too_deep first"),
    ("src/aew/dashboard/contract.py", "Contract.__init__"): (1, "the dashboard contract: a file of AEW's own, "
                                                                "not a project's"),
    ("src/aew/maps/rules.py", "parse"): (1, "the installed rule table (package data)"),
    ("src/aew/stg02/adopted.py", "load"): (1, "vendored adopted files, read only after their sealed sha256 matches"),
}
WRITING = {("src/aew/util.py", "_bounded_dump"): (1, "dump_yaml and safe_dump_yaml, through the bounded representer")}
CLASS_SITES = {("src/aew/util.py", "<module>"): (2, "_Bounded, the bounded representer, and _PyYAMLLayoutDumper, it on "
                                                    "PyYAML's dumper")}
BACKEND_LOOKUPS = {("src/aew/util.py", "<module>"): (2, "_SafeLoader and _SafeDumperBase: libyaml when present"),
                   ("src/aew/util.py", "yaml_backend"): (1, "which backend _SafeLoader is")}


def _scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    """The function (or class body) the node runs in, qualified: a decorator, a default or a base runs in the scope
    around its definition, so only a node in a definition's body is in that definition."""
    names: list[str] = []
    child, parent = node, parents.get(node)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child in parent.body:
            names.append(parent.name)
        child, parent = parent, parents.get(parent)
    return ".".join(reversed(names)) or "<module>"


def _is_yaml_object(value: object) -> bool:
    """The yaml module, or a class or function of it, or a class built on one of its classes."""
    if value is yaml:
        return True
    if inspect.isclass(value):
        return any((base.__module__ or "").split(".")[0] == "yaml" for base in value.__mro__)
    return (getattr(value, "__module__", None) or "").split(".")[0] == "yaml"


UTIL_YAML = frozenset(name for name, value in vars(util).items() if _is_yaml_object(value))
_MISSING = object()


def _chain(node: ast.Attribute) -> tuple[ast.AST, list[str]]:
    """The root of an attribute chain and its names, outermost last: ``yaml.a.b`` is (``yaml``, [a, b])."""
    names: list[str] = []
    root: ast.AST = node
    while isinstance(root, ast.Attribute):
        names.append(root.attr)
        root = root.value
    return root, names[::-1]


def _yaml_chain_site(node: ast.Attribute, parent: ast.AST | None) -> str | None:
    """The kind of site an outermost ``yaml.a.b...`` is, resolved against the yaml module, or None."""
    if not isinstance(node.ctx, ast.Load):
        return "lookup"  # yaml's own objects assigned or deleted
    _root, names = _chain(node)
    value: object = yaml
    for i, name in enumerate(names):
        value = getattr(value, name, _MISSING)
        if value is _MISSING or isinstance(value, (dict, types.MappingProxyType)):
            return "lookup"  # not resolvable here, or a namespace such as `yaml.__dict__`
        if inspect.isfunction(value) and value.__module__ == "yaml":
            return "compose" if value.__name__ in COMPOSERS else "write" if value.__name__ in DUMPERS else None
        if inspect.isclass(value) and any(hasattr(value, m) for m in COMPOSING_CLASS + WRITING_CLASS):
            rest = names[i + 1:]
            driven = (rest[:1] in (["__call__"], ["__new__"]) or not rest and (
                (isinstance(parent, ast.Call) and parent.func is node)
                or (isinstance(parent, ast.ClassDef) and node in parent.bases)))
            return "class" if driven else None
    return None


def _is_yaml_string(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.split(".")[0] == "yaml"


def yaml_sites() -> dict[str, Counter[tuple[str, str]]]:
    """Each kind of YAML site in src/aew, counted by (file, scope)."""
    return _sites_under(ROOT)


@functools.cache  # one parse of the product for the tests that read it
def _sites_under(root: Path) -> dict[str, Counter[tuple[str, str]]]:
    sites: dict[str, Counter[tuple[str, str]]] = {k: Counter() for k in ("compose", "write", "class", "lookup",
                                                                          "import")}
    for path in sorted((root / "src" / "aew").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        util_names = set() if rel == "src/aew/util.py" else _util_bindings(tree)
        for node in ast.walk(tree):
            at = (rel, _scope(node, parents))
            parent = parents.get(node)
            if isinstance(node, ast.Attribute) and not isinstance(parent, ast.Attribute):
                root_node, names = _chain(node)
                if isinstance(root_node, ast.Name) and root_node.id == "yaml":
                    kind = _yaml_chain_site(node, parent)
                    if kind:
                        sites[kind][at] += 1
                elif isinstance(root_node, ast.Name) and _reaches_util_yaml(root_node.id, names, util_names):
                    sites["import"][at] += 1  # util's yaml objects, reached from another module
            elif isinstance(node, ast.Name) and node.id == "yaml" and not isinstance(parent, ast.Attribute):
                sites["lookup"][at] += 1  # the module itself, handed on or looked into
            elif isinstance(node, ast.Import):
                sites["import"][at] += sum(a.name.split(".")[0] == "yaml" and (a.name != "yaml" or a.asname is not None)
                                           for a in node.names)
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "yaml":
                sites["import"][at] += 1
            elif isinstance(node, ast.ImportFrom) and node.module == "aew.util" and rel != "src/aew/util.py":
                sites["import"][at] += sum(a.name in UTIL_YAML for a in node.names)
            elif isinstance(node, ast.Call):
                func = node.func
                called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                named = [*node.args[:1], *(k.value for k in node.keywords if k.arg == "name")]
                if called in {"__import__", "import_module"} and any(_is_yaml_string(n) for n in named):
                    sites["import"][at] += 1
    return {kind: +counts for kind, counts in sites.items()}  # unary + drops zero counts


def _util_bindings(tree: ast.Module) -> set[str]:
    """The names a module binds to ``aew.util`` (``from aew import util``, ``import aew.util as u``), and ``aew``
    when it imports ``aew.util`` bare."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "aew":
            names |= {a.asname or a.name for a in node.names if a.name == "util"}
        elif isinstance(node, ast.Import):
            names |= {a.asname or "aew" for a in node.names if a.name == "aew.util"}
    return names


def _reaches_util_yaml(root: str, names: list[str], util_names: set[str]) -> bool:
    if root not in util_names:
        return False
    rest = names[1:] if names[:1] == ["util"] and root == "aew" else names
    return bool(rest) and rest[0] in UTIL_YAML


def _expected(listed: dict[tuple[str, str], tuple[int, str]]) -> Counter[tuple[str, str]]:
    return Counter({at: count for at, (count, _reason) in listed.items()})


def test_every_place_the_product_composes_yaml_is_bounded_or_reads_only_aews_own_files():
    assert yaml_sites()["compose"] == _expected(COMPOSING)


def test_every_place_the_product_writes_yaml_is_bounded():
    assert yaml_sites()["write"] == _expected(WRITING)


def test_no_loader_or_dumper_class_is_driven_outside_util():
    assert yaml_sites()["class"] == _expected(CLASS_SITES)


def test_every_import_of_yaml_is_the_bare_module_that_the_enumeration_sees():
    sites = yaml_sites()
    assert sites["import"] == Counter() and sites["lookup"] == _expected(BACKEND_LOOKUPS)


def test_every_function_of_the_yaml_module_is_classified_once():
    """The function lists are checked against the installed yaml package, so a function PyYAML defines in
    `yaml/__init__` is classified before it can be used unseen (review of #236, R2-F2). One it re-exports from a
    submodule, or a C function, is not listed here: limit 7 above (R3-F2)."""
    functions = {name for name, value in vars(yaml).items() if inspect.isfunction(value) and value.__module__ == "yaml"}
    assert functions == COMPOSERS | DUMPERS | set(NEITHER)
    assert not (COMPOSERS & DUMPERS or COMPOSERS & set(NEITHER) or DUMPERS & set(NEITHER))


def test_the_class_rule_finds_every_loader_and_dumper_and_the_components_they_are_built_from():
    found = {name for name, value in vars(yaml).items() if inspect.isclass(value)
             and any(hasattr(value, m) for m in COMPOSING_CLASS + WRITING_CLASS)}
    assert {"SafeLoader", "BaseLoader", "FullLoader", "UnsafeLoader", "Loader", "SafeDumper", "BaseDumper", "Dumper",
            "CSafeLoader", "CBaseLoader", "CSafeDumper", "CBaseDumper"} <= found
    assert all(hasattr(c, "get_single_node") for c in (yaml.composer.Composer, yaml.cyaml.CParser))
    assert all(any(hasattr(c, m) for m in WRITING_CLASS) for c in (
        yaml.representer.BaseRepresenter, yaml.serializer.Serializer, yaml.emitter.Emitter, yaml.cyaml.CEmitter))
    assert not any(hasattr(c, m) for c in (yaml.parser.Parser, yaml.scanner.Scanner, yaml.reader.Reader,
                                           yaml.resolver.Resolver, yaml.constructor.SafeConstructor)
                   for m in COMPOSING_CLASS + WRITING_CLASS)  # parsing, scanning or constructing composes nothing


def test_utils_own_yaml_objects_are_derived_from_util():
    assert UTIL_YAML == {"yaml", "_SafeLoader", "_SafeDumperBase", "_Bounded", "_Dumper", "_PyYAMLLayoutDumper"}


PLANTED = [  # (module source, the kind of site it must be counted as, its scope, the count): the review's probe cases
    ("import yaml as y\ndef f(t): return y.safe_load(t)\n", "import", "<module>", 1),
    ("from yaml import safe_load\n", "import", "<module>", 1),
    ("import yaml.loader as L\n", "import", "<module>", 1),
    ("def f(t): return __import__('yaml').safe_load(t)\n", "import", "f", 1),
    ("import importlib\ndef f(t): return importlib.import_module('yaml').safe_load(t)\n", "import", "f", 1),
    ("import yaml\ndef f(t): return getattr(yaml, 'safe_load')(t)\n", "lookup", "f", 1),
    ("import yaml\ndef f(): return yaml.safe_load\n", "compose", "f", 1),
    ("import yaml\ndef f(ts): return list(map(yaml.safe_load, ts))\n", "compose", "f", 1),
    ("import yaml\nclass C:\n    def m(self, t): return yaml.compose(t)\n", "compose", "C.m", 1),
    ("import yaml\ndef f(t): return yaml.CSafeLoader(t).get_single_data()\n", "class", "f", 1),
    ("import yaml\ndef f(t): return yaml.loader.SafeLoader(t).get_single_node()\n", "class", "f", 1),
    ("import yaml\nclass L(yaml.SafeLoader):\n    pass\n", "class", "<module>", 1),
    ("import yaml\ndef f(t): return yaml.safe_load(t), yaml.safe_load(t)\n", "compose", "f", 2),
    ("import yaml\ndef f(d): return yaml.safe_dump(d)\n", "write", "f", 1),
    # The second review's (R2-F2): classes the hand list missed, found by what they can do
    ("import yaml\ndef f(t): return yaml.cyaml.CParser(t).get_single_node()\n", "class", "f", 1),
    ("import yaml\nclass L(yaml.reader.Reader, yaml.scanner.Scanner, yaml.parser.Parser, yaml.composer.Composer,\n"
     "        yaml.constructor.SafeConstructor, yaml.resolver.Resolver):\n    pass\n", "class", "<module>", 1),
    ("import yaml\nclass D(yaml.BaseDumper):\n    pass\n", "class", "<module>", 1),
    ("import yaml\ndef f(s): return yaml.CBaseDumper(s)\n", "class", "f", 1),
    ("import yaml\nclass W(yaml.representer.SafeRepresenter, yaml.serializer.Serializer, yaml.emitter.Emitter):\n"
     "    pass\n", "class", "<module>", 3),
    ("import yaml\ndef f(t): return yaml.SafeLoader.__call__(t)\n", "class", "f", 1),
    # an attribute after the function's name is still a reference to it
    ("import yaml\ndef f(t): return yaml.safe_load.__call__(t)\n", "compose", "f", 1),
    ("import yaml\ndef f(t): return yaml.load.__get__(None, object)(t, yaml.SafeLoader)\n", "compose", "f", 1),
    # util's own yaml objects, reached from another module
    ("from aew.util import _SafeLoader\ndef f(t): return _SafeLoader(t).get_single_data()\n", "import", "<module>", 1),
    ("from aew import util\ndef f(t): return util.yaml.safe_load(t)\n", "import", "f", 1),
    ("from aew.util import yaml as y\n", "import", "<module>", 1),
    ("import aew.util\ndef f(t): return aew.util._Dumper\n", "import", "f", 1),
    # dynamic lookups, and the module handed on
    ("import yaml\ndef f(t): return vars(yaml)['safe_load'](t)\n", "lookup", "f", 1),
    ("import yaml\ndef f(t): return yaml.__dict__['safe_load'](t)\n", "lookup", "f", 1),
    ("import importlib\ndef f(t): return importlib.import_module(name='yaml').safe_load(t)\n", "import", "f", 1),
    ("import yaml\ny = yaml\n", "lookup", "<module>", 1),
    ("import yaml\ndef f(t): return yaml.no_such_function(t)\n", "lookup", "f", 1),
]


def _plant(root: Path, source: str) -> None:
    planted = root / "src" / "aew" / "planted.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(source, encoding="utf-8")


@pytest.mark.parametrize(("source", "kind", "scope", "count"), PLANTED, ids=range(len(PLANTED)))
def test_the_enumeration_sees_each_way_a_module_can_reach_a_composer(source, kind, scope, count, tmp_path,
                                                                      monkeypatch):
    """Each probe case of the review (#236, F2), planted in a module of its own, is counted where it is."""
    _plant(tmp_path, source)
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    assert yaml_sites()[kind] == Counter({("src/aew/planted.py", scope): count})


@pytest.mark.parametrize("source", [
    "import yaml\ndef f(t): return list(yaml.parse(t, Loader=yaml.BaseLoader))\n",  # a loader passed, not driven
    "import yaml\ndef f(t): return yaml.scan(t), yaml.YAMLError, yaml.MappingNode\n",
    "import yaml\nyaml.SafeLoader.add_constructor('!x', None)\n",  # registration composes nothing
    "from aew.util import load_yaml\nfrom aew import util\ndef f(t): return util.dump_yaml(load_yaml(t))\n",
], ids=["loader-argument", "parse-scan-and-types", "registration", "util-bounded-functions"])
def test_what_composes_and_writes_nothing_is_not_a_site(source, tmp_path, monkeypatch):
    _plant(tmp_path, source)
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    assert not any(yaml_sites().values())


def _writer_key(data: dict) -> object:
    """The truth: the top-level key the writer was representing when it refused (the review's oracle, R2-F1)."""

    class Probe(util._Dumper):  # type: ignore[misc,valid-type]
        current: object = None

        def represent_data(self, value: object) -> yaml.Node:
            if self._depth == 1 and any(value is key for key in data):
                Probe.current = value
            return super().represent_data(value)

    with pytest.raises(util._TooDeepToWrite):
        yaml.dump(data, Dumper=Probe, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)
    return Probe.current


def _named_key(data: dict) -> str | None:
    """The key the refusal names, as written in it (a repr)."""
    with pytest.raises(ValidationFailed) as refused:
        util.dump_yaml(data)
    message = refused.value.message
    return message.split("top-level key ", 1)[1].split(": AEW does not", 1)[0] if "top-level key" in message else None


def _shared_cases() -> list[dict]:
    shared, also = nested(30), nested(30)
    top: dict = {"x": nested(util.YAML_MAX_DEPTH - 1)}
    top["self"], top["z"] = top, nested(70)

    def over(n: int, leaf: object) -> object:  # n mappings around ``leaf``
        for _ in range(n):
            leaf = {"k": leaf}
        return leaf

    def tupled(n: int) -> object:  # n tuples, one inside the other
        leaf: object = "x"
        for _ in range(n):
            leaf = (leaf,)
        return leaf

    return [{"a": [shared, over(40, shared)], "c": nested(70)},  # met shallow first, then deep: the writer refuses c
            {"a": [over(40, also), also]},  # met deep first
            top,  # the top-level mapping is itself a value: an alias
            # what the writer writes beyond mappings and lists (review of #236, R3-F1):
            {"a": (nested(70),), "b": 1},  # a tuple is a sequence: the writer refuses a
            {"a": {tupled(70): 1}, "b": nested(70)},  # a mapping's key is written before its value
            {"s": 1, tupled(70): 1, "z": nested(70)},  # a top-level key is written under the mapping too
            {"a": [()], "b": over(63, ())}]  # the empty tuple is never an alias: written again at level 65


def _random_dags(count: int, seed: int = 236) -> list[dict]:
    """Data that shares objects at random, as control state does (an invocation's snapshot is its workspace's), and that
    holds what the writer also writes: tuples, the empty tuple and tuples as mapping keys (review of #236, R3-F1). The
    search is bounded and asserts what it found, so when the writer refuses none the test fails instead of looping
    (R3-F3); its depth is the bound's, so a raised bound still yields refusals."""
    rng, found = random.Random(seed), []

    def recent(pool: list) -> object:  # mostly the latest: the depth grows
        return pool[max(0, len(pool) - 1 - int(rng.expovariate(1.2)))]

    for _ in range(50 * count):
        if len(found) == count:
            break
        nodes: list = ["x", ()]
        keys: list = ["x", ()]  # tuple chains, which can be a mapping's key (a tuple's hash expands what it shares)
        for _ in range(rng.randint(util.YAML_MAX_DEPTH + 6, util.YAML_MAX_DEPTH + 46)):  # each holds 1-3 earlier ones
            kids = [recent(nodes) for _ in range(rng.randint(1, 3))]
            shape = rng.random()
            nodes.append(tuple(kids) if shape < 0.2 else
                         {(recent(keys) if rng.random() < 0.3 else f"k{i}"): c for i, c in enumerate(kids)}
                         if shape < 0.6 else kids)
            keys.append((recent(keys),))
        data = {(rng.choice(keys[len(keys) // 2:]) if rng.random() < 0.25 else f"t{i}"): rng.choice(
            nodes[len(nodes) // 2:]) for i in range(rng.randint(1, 4))}
        try:
            util.dump_yaml(data)
        except ValidationFailed:
            found.append(data)
    assert len(found) == count, f"the writer refused {len(found)} of the {count} documents that nest past the bound"
    return found


def test_a_write_refusal_names_the_key_the_writer_refused_under_when_the_data_shares_objects():
    """The writer expands an object where it first meets it and writes an alias wherever it meets it again, the
    top-level mapping included, except the empty tuple; it writes a tuple as a sequence and a mapping's key before its
    value. The key the refusal names is the one it was writing (review of #236, R2-F1, R3-F1)."""
    cases = _shared_cases() + _random_dags(60)
    assert [_writer_key(d) for d in cases[:3]] == ["c", "a", "z"]
    assert [_named_key(d) for d in cases] == [repr(_writer_key(d)) for d in cases]


def test_a_write_refusal_still_refuses_when_the_key_it_would_name_has_no_repr():
    """A tuple key nested past Python's recursion limit hashes but cannot be written as text: the refusal stays a
    ValidationFailed and leaves the key unnamed (review of #236, R3-F1)."""
    key: object = ()
    for _ in range(5_000):
        key = (key,)
    with pytest.raises(ValidationFailed) as refused:
        util.dump_yaml({"s": 1, key: 1})
    assert refused.value.message.startswith("the data nests deeper than 64 levels: ")
    assert refused.value.details == {"reason": util.YAML_TOO_DEEP, "limit": util.YAML_MAX_DEPTH}


def test_a_deep_control_state_says_to_restore_it_since_aew_never_writes_one(tmp_path):
    """Flattening control state by hand would break its checksum (review of #236, R2-F3)."""
    from store_model import init

    init(tmp_path)
    raw = (tmp_path / "state" / "control.yaml").read_text(encoding="utf-8")
    body = raw[:raw.rindex(CHECKSUM_PREFIX)] + flow(100).replace("k:", "zz_planted:")
    resealed = (body + f"{CHECKSUM_PREFIX}{util.sha256_bytes(body.encode('utf-8'))}\n").encode("utf-8")
    with pytest.raises(ValidationFailed) as refused:
        deserialize_control(resealed, source="control.yaml")
    assert refused.value.message.endswith("so this file was written outside AEW: restore it from git or a backup")
    assert refused.value.details["reason"] == util.YAML_TOO_DEEP


def test_a_deep_redo_record_is_the_damaged_record_it_is(tmp_path, monkeypatch):
    """A redo record is git-ignored, so git cannot restore it: past the bound, it takes the refusal its checksum
    already gives a damaged one, keeping the reason (review of #236, R2-F3)."""
    from store_model import init, make_store, one_transaction

    from aew.engine.faults import InjectedFault
    from aew.errors import IntegrityError

    store = init(tmp_path)
    one_transaction(store)
    monkeypatch.setenv("AEW_FAULT", "txn.after_replace")  # committed, its writes not yet applied
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        one_transaction(make_store(tmp_path))
    monkeypatch.delenv("AEW_FAULT")
    control = tmp_path / "state" / "control.yaml"
    redo = sorted((tmp_path / "state" / "txn").glob("*.yaml"))[-1]  # the interrupted one; an older one is spent
    old_sha = util.sha256_bytes(redo.read_bytes())
    deep = flow(100).encode("utf-8")
    redo.write_bytes(deep)
    raw = control.read_text(encoding="utf-8")
    body = raw[:raw.rindex(CHECKSUM_PREFIX)].replace(old_sha, util.sha256_bytes(deep))
    control.write_bytes((body + f"{CHECKSUM_PREFIX}{util.sha256_bytes(body.encode('utf-8'))}\n").encode("utf-8"))
    with pytest.raises(IntegrityError) as refused:
        make_store(tmp_path).read()
    assert refused.value.message == f"redo record state/txn/{redo.name} is damaged"
    assert refused.value.details == {"reason": util.YAML_TOO_DEEP, "limit": util.YAML_MAX_DEPTH, "line": 1}


# Every writer that names its document in a depth refusal, and the name (review of #236, R2-N2): the refusal's text is
# behaviour. `test_a_write_refusal_names_the_document_...` shows `source` leads the message.
NAMED_WRITERS = {
    ("src/aew/engine/store.py", "serialize_control"): '"control state"',
    ("src/aew/engine/store.py", "ControlStore._commit_unprofiled"): '"the transaction\'s redo record"',
    ("src/aew/engine/disposition_ops.py", "Dispositions._write"): "f\"disposition record {record['id']}\"",
    ("src/aew/engine/stage_intents.py", "StageIntents._end"): "f\"stage intent {si['id']}\"",
}


def test_each_writer_that_names_its_document_names_it_as_pinned():
    found = {}
    for path in sorted((ROOT / "src" / "aew").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) in {
                    "dump_yaml", "safe_dump_yaml"}:
                for keyword in node.keywords:
                    if keyword.arg == "source":
                        at = (path.relative_to(ROOT).as_posix(), _scope(node, parents))
                        found[at] = ast.get_source_segment(text, keyword.value)  # as written: unparse varies
    assert found == NAMED_WRITERS
