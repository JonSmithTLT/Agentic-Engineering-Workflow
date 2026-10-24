"""YAML nesting is bounded (``util.YAML_MAX_DEPTH``), on both sides. libyaml's composer recurses in C with no depth
check, so a hostile document deep enough kills the process on Windows (a stack overflow, no exception); the
pure-Python composer raises RecursionError. So a document past the bound is refused before anything is composed, as a
ValidationFailed (reason ``yaml_too_deep``) on every platform and Python, the control store's own files included. AEW's
writer holds the same bound, so a document AEW wrote is never refused when it is read back."""

from __future__ import annotations

import ast
import functools
import os
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
# (file, the function it is in). `yaml.parse` (events only) composes nothing and is allowed anywhere. A new site joins a
# list with its reason, or goes through `util.load_yaml`, `util.dump_yaml` or `util.safe_dump_yaml`; a second site in
# a listed function is red too (review of #236, F2).
#
# What is enumerated: every reference `yaml.<name>` (or `yaml.<submodule>.<name>`) to a composing or writing function,
# called or not; every loader or dumper class instantiated or subclassed (passing one as an argument, such as
# `Loader=yaml.BaseLoader`, composes nothing); and, as the precondition all of that rests on, every import of yaml is a
# bare `import yaml`, with no `from yaml import`, alias, `__import__`, `import_module` or `getattr(yaml, ...)` beyond
# util's backend lookups. Limits, not claimed: the module or a class bound to another name at run time (`y = yaml`, a
# loader held in a data structure and instantiated elsewhere), and YAML parsed inside a C extension or a dependency.
COMPOSERS = {"load", "safe_load", "full_load", "unsafe_load", "load_all", "safe_load_all", "full_load_all",
             "unsafe_load_all", "compose", "compose_all"}
DUMPERS = {"dump", "safe_dump", "dump_all", "safe_dump_all", "serialize", "serialize_all", "emit"}
CLASSES = {"Loader", "SafeLoader", "CSafeLoader", "BaseLoader", "CBaseLoader", "FullLoader", "CFullLoader",
           "UnsafeLoader", "CUnsafeLoader", "CLoader", "Dumper", "SafeDumper", "CSafeDumper", "CDumper"}
COMPOSING = {
    ("src/aew/util.py", "load_yaml"): (1, "bounded by yaml_too_deep first"),
    ("src/aew/cli/fields.py", "_load"): (1, "bounded by yaml_too_deep first"),
    ("src/aew/dashboard/contract.py", "Contract.__init__"): (1, "the dashboard contract: a file of AEW's own, "
                                                                "not a project's"),
    ("src/aew/maps/rules.py", "parse"): (1, "the installed rule table (package data)"),
    ("src/aew/stg02/adopted.py", "load"): (1, "vendored adopted files, read only after their sealed sha256 matches"),
}
WRITING = {("src/aew/util.py", "_bounded_dump"): (1, "dump_yaml and safe_dump_yaml, through the bounded representer")}
CLASS_SITES = {("src/aew/util.py", "<module>"): (1, "_PyYAMLLayoutDumper: the bounded representer on PyYAML's dumper")}
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


def _yaml_name(node: ast.Attribute) -> str | None:
    """``name`` for an outermost ``yaml.name`` or ``yaml.<submodule>.name``, read (not assigned), else None."""
    root: ast.AST = node
    while isinstance(root, ast.Attribute):
        root = root.value
    return node.attr if isinstance(root, ast.Name) and root.id == "yaml" and isinstance(node.ctx, ast.Load) else None


def _is_yaml_string(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.split(".")[0] == "yaml"


def yaml_sites() -> dict[str, Counter[tuple[str, str]]]:
    """Each kind of YAML site in src/aew, counted by (file, scope)."""
    return _sites_under(ROOT)


@functools.cache  # one parse of the product for the four tests that read it
def _sites_under(root: Path) -> dict[str, Counter[tuple[str, str]]]:
    sites: dict[str, Counter[tuple[str, str]]] = {k: Counter() for k in ("compose", "write", "class", "lookup",
                                                                          "import")}
    for path in sorted((root / "src" / "aew").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            at = (rel, _scope(node, parents))
            if isinstance(node, ast.Attribute) and not isinstance(parents.get(node), ast.Attribute):
                name = _yaml_name(node)
                parent = parents.get(node)
                if name in COMPOSERS:
                    sites["compose"][at] += 1
                elif name in DUMPERS:
                    sites["write"][at] += 1
                elif name in CLASSES and ((isinstance(parent, ast.Call) and parent.func is node)
                                          or (isinstance(parent, ast.ClassDef) and node in parent.bases)):
                    sites["class"][at] += 1
            elif isinstance(node, ast.Import):
                sites["import"][at] += sum(a.name.split(".")[0] == "yaml" and (a.name != "yaml" or a.asname is not None)
                                           for a in node.names)
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "yaml":
                sites["import"][at] += 1
            elif isinstance(node, ast.Call):
                func, first = node.func, node.args[0] if node.args else None
                called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                if called in {"__import__", "import_module"} and _is_yaml_string(first):
                    sites["import"][at] += 1
                elif called == "getattr" and isinstance(first, ast.Name) and first.id == "yaml":
                    sites["lookup"][at] += 1
    return {kind: +counts for kind, counts in sites.items()}  # unary + drops zero counts


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


def test_passing_a_loader_class_as_an_argument_is_not_a_site(tmp_path, monkeypatch):
    _plant(tmp_path, "import yaml\ndef f(t): return list(yaml.parse(t, Loader=yaml.BaseLoader))\n")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    assert not any(yaml_sites().values())
