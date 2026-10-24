"""The writers family of the generated reference (STG-12 S12-2, DOC-01), on planted sources.

The family reads write primitives with ``ast`` (``tools/reference_families/writers.py``), follows each destination
(``writers_flow.py``), finds which entry points can reach each writer (``writers_reach.py``), and is cross-checked by a
second detector written over tokens (``writers_text.py``). Every rule here has its planted right case, wrong case and
missing case, so a rule that stopped working would fail; the tree-wide guarantees (the two detectors agreeing on every
module, the declared set of top-level entries, the conventions the reading relies on) are in
``tests/integration/test_reference_writers.py``.
"""

from __future__ import annotations

import ast
import copy
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, writers, writers_flow, writers_reach, writers_text
    finally:
        sys.path.remove(here)
    return common, writers, writers_flow, writers_reach, writers_text


C, W, F, R, T = _tools()
TOP = frozenset({"state", "local", "work", "evidence", "records", "project.yaml"})
KINDS = {"aew": "store_writer", "aew lead mcp": "non_writer", "aew.harness.supervisor": "store_writer",
         "aew.stg02.server": "non_writer"}
HEAD = ("import os\nimport shutil\nimport sqlite3\nimport tempfile\nfrom pathlib import Path\n"
        "from aew.util import atomic_write, create_exclusive\n")


def program(sources: dict[str, str]) -> Any:
    return F.Program.of({name: (ast.parse(text), False) for name, text in sources.items()})


def analysed(source: str, *, extra: dict[str, str] | None = None, top=TOP, roots=None, dispatchers=None) -> Any:
    return W.analyse(program({"aew.m": HEAD + source, **(extra or {})}), top, roots or {}, KINDS, dispatchers or set())


def writers_of(a: Any, template: str) -> list[tuple[str, str, str, tuple[str, ...]]]:
    return [(w.module, w.symbol, w.mechanism, w.via) for w in a.writers.get(template, [])]


def reasons(a: Any) -> list[str]:
    return [reason for _, reason in a.unresolved.values()]


# ----------------------------------------------------------------------------------- the write primitives, both readers

def counts(source: str) -> tuple[Counter[str], Counter[str]]:
    """(the AST reading's primitive calls, the token reading's) of one module's source."""
    return W.primitive_counts(program({"aew.m": source}))["aew.m"], T.sites(source)


PRIMITIVES = [
    # (source, the labels both readers find)
    ("Path(p).write_text('x')", {"Path.write_text": 1}),
    ("p.write_bytes(b'x')", {"Path.write_bytes": 1}),
    ("p.mkdir(parents=True, exist_ok=True)", {"Path.mkdir": 1}),
    ("p.unlink(missing_ok=True)", {"Path.unlink": 1}),
    ("p.touch()", {"Path.touch": 1}),
    ("p.rmdir()", {"Path.rmdir": 1}),
    ("a.replace(b)", {"Path.replace": 1}),
    ("a.rename(b)", {"Path.rename": 1}),
    ("open(p, 'w')", {"open": 1}),
    ("open(p, mode='ab')", {"open": 1}),
    ("open(p, 'r+b')", {"open": 1}),
    ("p.open('w')", {"Path.open": 1}),
    ("os.open(p, os.O_WRONLY | os.O_CREAT)", {"os.open": 1}),
    ("os.replace(a, b)", {"os.replace": 1}),
    ("os.makedirs(d, exist_ok=True)", {"os.makedirs": 1}),
    ("shutil.rmtree(d)", {"shutil.rmtree": 1}),
    ("shutil.copy2(a, b)", {"shutil.copy2": 1}),
    ("sqlite3.connect(p)", {"sqlite3.connect": 1}),
    ("atomic_write(p, 'x')", {"atomic_write": 1}),
    ("create_exclusive(p, 'x')", {"create_exclusive": 1}),
    ("write_file(store, p, 'x')", {"write_file": 1}),
    ("session.write('work/x', 'y')", {"session.write": 1}),
    ("ctx.session.write(rel, text)", {"session.write": 1}),
    ("a.replace(b); a.rename(c); open(p, 'a')", {"Path.replace": 1, "Path.rename": 1, "open": 1}),
]
NOT_WRITES = [
    "text.replace('a', 'b')",                    # str.replace takes two arguments
    "when.replace(tzinfo=None)",                 # datetime.replace takes keywords only
    "open(p)", "open(p, 'r')", "open(p, 'rb')",  # reads
    "p.open()", "p.open('rb')",
    "os.open(p, os.O_RDONLY)",                   # a read
    "os.write(fd, b'x')", "fh.write('x')", "out.write('x')",   # a descriptor or a stream, not a path
    "os.chmod(p, 0o700)", "fsync_dir(d)",        # permission and durability, not writes
    "p.read_text()", "p.exists()",
    "'os.replace(a, b)'", "# os.replace(a, b)", "'''open(p, \"w\")'''",  # a string and a comment are not code
]


@pytest.mark.parametrize(("source", "expected"), PRIMITIVES)
def test_a_write_primitive_is_found_by_both_readers_with_the_same_label(source, expected):
    imports = "from aew.util import atomic_write, create_exclusive\nfrom aew.engine.store import write_file\n"
    ast_found, text_found = counts(imports + source + "\n")
    assert dict(ast_found) == expected, source
    assert dict(text_found) == expected, source


@pytest.mark.parametrize("source", NOT_WRITES)
def test_what_is_not_a_write_is_found_by_neither_reader(source):
    ast_found, text_found = counts(source + "\n")
    assert (dict(ast_found), dict(text_found)) == ({}, {}), source


def test_a_primitive_called_through_an_alias_is_the_ast_readings_alone_and_pinned_as_such():
    """The asymmetry the two readers have by construction: tokens cannot follow an import alias, so the AST reading
    finds `mv(a, b)` as `os.replace` and the token reading does not. The agreement test over the tree holds the two to
    equal counts, so a tree that used an alias would fail it until this is decided."""
    ast_found, text_found = counts("from os import replace as mv\nmv(a, b)\n")
    assert dict(ast_found) == {"os.replace": 1} and dict(text_found) == {}


CANNOT_SEE = [
    # a primitive that the call's own expression chooses, bound to a name, or built by a computed callee
    "(create_exclusive if x else atomic_write)(p, 'x')",
    "put = atomic_write\nput(p, 'x')",
    "getattr(p, 'write_text')('x')",
    "subprocess.run(['cp', a, b])",
]


@pytest.mark.parametrize("source", CANNOT_SEE)
def test_what_neither_reader_can_see_is_pinned_by_a_probe_each(source):
    """The family's 'cannot see' list: a primitive reached through a conditional callee (the store's `write_file` does
    this), a local name bound to a primitive, a computed method name, and a subprocess. Each is missed by both readers,
    so they agree and the tree check cannot flag it: it is listed here, and on the family's page."""
    ast_found, text_found = counts("from aew.util import atomic_write, create_exclusive\nimport subprocess\n"
                                   + source + "\n")
    assert (dict(ast_found), dict(text_found)) == ({}, {}), source


def test_a_one_argument_replace_is_a_path_move_and_a_two_argument_one_is_not():
    for source, label in (("a.replace(b)", "Path.replace"), ("a.replace(b, c)", None), ("a.replace(*b)", None),
                          ("a.replace(x=b)", None)):
        found, _ = counts(source + "\n")
        assert (dict(found) == {label: 1}) if label else (dict(found) == {}), source


# ------------------------------------------------------------------------------------------- destinations, resolved

def test_a_constant_joined_to_the_root_is_a_record_and_the_constant_names_it():
    a = analysed("REL = 'state/x.yaml'\n\ndef f(aew_root):\n    atomic_write(aew_root / REL, 'x')\n")
    assert writers_of(a, "state/x.yaml") == [("aew.m", "f", W.DIRECT, ("atomic_write",))]
    assert a.named == {"state/x.yaml": [("aew.m", "REL")]}


def test_a_constant_that_is_not_used_to_build_a_path_does_not_name_it():
    """`named_by` holds constants that are joined, interpolated or passed to a path call; a label that merely holds
    the same text (a key, a state name) does not name the path."""
    a = analysed("LABEL = 'state/x.yaml'\nREL = 'state/x.yaml'\n\n"
                 "def f(aew_root):\n    atomic_write(aew_root / REL, 'x')\n")
    assert a.named == {"state/x.yaml": [("aew.m", "REL")]}


def test_a_computed_segment_is_a_placeholder_and_a_literal_one_is_kept():
    a = analysed("def f(aew_root, wid):\n"
                 "    create_exclusive(aew_root / f'evidence/{wid}/x.md', 'x')\n"
                 "    create_exclusive(aew_root / 'evidence' / wid, 'x')\n")
    assert sorted(a.writers) == ["evidence/{}", "evidence/{}/x.md"]


def test_a_store_transaction_path_is_relative_to_the_root_by_construction():
    a = analysed("def f(session, wid):\n    session.write(f'work/{wid}/done.md', 'x')\n")
    assert writers_of(a, "work/{}/done.md") == [("aew.m", "f", W.STORE_TRANSACTION, ("session.write",))]


def test_a_move_writes_its_destination_and_not_its_source():
    a = analysed("def f(aew_root):\n    tmp = aew_root / 'local' / 'x.tmp'\n"
                 "    os.replace(tmp, aew_root / 'local' / 'x.json')\n")
    assert sorted(a.writers) == ["local/x.json"]


def test_a_sibling_of_a_path_is_taken_as_the_same_path_so_a_write_protocol_is_one_record():
    a = analysed("def f(aew_root):\n"
                 "    path = aew_root / 'local' / 's.json'\n"
                 "    tmp = path.with_suffix('.tmp')\n"
                 "    tmp.write_text('x')\n"
                 "    os.replace(tmp, path)\n")
    assert sorted(a.writers) == ["local/s.json"]
    assert writers_of(a, "local/s.json") == [("aew.m", "f", W.DIRECT, ("Path.write_text", "os.replace"))]


def test_a_path_that_joins_the_dot_aew_directory_is_the_root_whatever_the_left_side_is():
    a = analysed("def f(repo_root):\n    (repo_root / '.aew' / 'state' / 'x').write_text('x')\n")
    assert sorted(a.writers) == ["state/x"] and a.outside == {}


def test_the_repositorys_own_tree_is_outside_and_listed_not_a_record():
    a = analysed("def f(repo_root):\n    (repo_root / 'src' / 'x').write_text('x')\n")
    assert a.writers == {} and "the repository's working tree" in a.outside


@pytest.mark.parametrize(("source", "why"), [
    ("def f():\n    d = tempfile.mkdtemp()\n    (Path(d) / 'x').write_text('x')\n", "a temporary directory"),
    ("def f():\n    open(os.devnull, 'w')\n", "the null device"),
    ("def f():\n    os.open('/dev/tty', os.O_WRONLY)\n", "an absolute path"),
    ("def f():\n    open('CONOUT$', 'w')\n", "the Windows console"),
    ("def f():\n    sqlite3.connect(':memory:')\n", "an in-memory database"),
])
def test_a_destination_provably_outside_aew_is_listed_and_is_no_record_and_no_gap(source, why):
    a = analysed(source)
    assert why in a.outside and a.writers == {} and a.unresolved == {}


def test_a_value_flows_through_assignments_parameters_and_a_helper_that_builds_the_path():
    a = analysed("def build(wid):\n    return f'work/{wid}/x.md'\n\n"
                 "def _put(path):\n    path.write_text('x')\n\n"
                 "def f(aew_root, wid):\n    _put(aew_root / build(wid))\n")
    assert writers_of(a, "work/{}/x.md") == [("aew.m", "_put", W.DIRECT, ("Path.write_text",))]


def test_a_self_attribute_takes_the_argument_of_every_construction():
    a = analysed("class Log:\n    def __init__(self, path):\n        self.path = path\n"
                 "    def add(self):\n        self.path.write_text('x')\n\n"
                 "def f(aew_root):\n    Log(aew_root / 'local' / 'log').add()\n")
    assert writers_of(a, "local/log") == [("aew.m", "Log.add", W.DIRECT, ("Path.write_text",))]


def test_a_dataclass_field_is_the_constructors_argument_and_a_base_class_attribute_is_inherited():
    a = analysed("from dataclasses import dataclass\n\n"
                 "@dataclass\nclass Run:\n    run_dir: Path\n\n"
                 "class Base:\n    def __init__(self, d):\n        self.d = d\n\n"
                 "class Sub(Base):\n    def go(self):\n        (self.d / 'a').write_text('x')\n\n"
                 "def g(r: Run):\n    (r.run_dir / 'b').write_text('x')\n\n"
                 "def f(aew_root):\n    Sub(aew_root / 'local' / 'sub').go()\n    g(Run(aew_root / 'local' / 'run'))\n")
    assert sorted(a.writers) == ["local/run/b", "local/sub/a"]


def test_a_loop_over_a_directorys_entries_or_a_mappings_keys_takes_them_as_the_path():
    a = analysed("def f(aew_root):\n    for p in (aew_root / 'state').iterdir():\n        p.unlink()\n\n"
                 "def put(root, files):\n    for rel, text in files.items():\n        (root / rel).write_text(text)\n\n"
                 "def g(aew_root):\n    put(aew_root, {'local/a.md': 'x', 'work/b.md': 'y'})\n")
    assert sorted(a.writers) == ["local/a.md", "state/{}", "work/b.md"]


def test_a_method_of_a_receiver_whose_class_is_evident_is_followed_and_one_of_an_unknown_class_is_not():
    a = analysed("class Box:\n    def put(self, aew_root):\n        (aew_root / 'local' / 'b').write_text('x')\n\n"
                 "def make() -> Box:\n    return Box()\n\n"
                 "def f(aew_root, other):\n    make().put(aew_root)\n    other.put(aew_root)\n",
                 roots={("aew.m", "f"): {"aew"}})
    assert a.reach[("aew.m", "Box.put")] == {"aew"}
    assert W.records_of(a)[0].fact["writers"][0]["entry_points"] == ["aew"]  # type: ignore[index]


def test_a_super_constructor_and_a_facade_attribute_built_from_a_local_are_followed():
    a = analysed("class Base:\n    def __init__(self, d):\n        self.d = d\n\n"
                 "class Sub(Base):\n    def __init__(self, d):\n        super().__init__(d)\n"
                 "    def go(self):\n        (self.d / 'x').write_text('x')\n\n"
                 "class Hier:\n    def close(self, aew_root):\n        (aew_root / 'work' / 'c').write_text('x')\n\n"
                 "class Facade:\n    def __init__(self):\n        h = Hier()\n        self._h = h\n"
                 "    def close(self, aew_root):\n        return self._h.close(aew_root)\n\n"
                 "def main(aew_root):\n    Sub(aew_root / 'local' / 'sub').go()\n    Facade().close(aew_root)\n",
                 roots={("aew.m", "main"): {"aew"}})
    assert sorted(a.writers) == ["local/sub/x", "work/c"]
    assert a.reach[("aew.m", "Hier.close")] == {"aew"} and a.reach[("aew.m", "Sub.go")] == {"aew"}


def test_a_function_whose_returns_build_one_class_types_its_result_without_an_annotation():
    a = analysed("class E:\n    @classmethod\n    def find(cls):\n        return cls()\n"
                 "    def put(self, aew_root):\n        (aew_root / 'local' / 'e').write_text('x')\n\n"
                 "def _e():\n    return E.find()\n\n"
                 "def main(aew_root):\n    _e().put(aew_root)\n", roots={("aew.m", "main"): {"aew"}})
    assert a.reach[("aew.m", "E.put")] == {"aew"}


def test_an_attribute_of_a_local_built_from_a_class_takes_the_constructors_arguments():
    a = analysed("class Index:\n    def __init__(self, aew_root):\n        self.path = aew_root / 'local' / 'idx'\n\n"
                 "def f(aew_root):\n    index = Index(aew_root)\n    index.path.unlink()\n")
    assert writers_of(a, "local/idx") == [("aew.m", "f", W.DIRECT, ("Path.unlink",))]


def test_the_keys_of_a_mapping_passed_to_a_method_of_a_constructed_class_are_the_paths_it_writes():
    a = analysed("class Store:\n    def __init__(self, root):\n        self.root = root\n"
                 "    def create(self, files):\n        for rel, text in files.items():\n"
                 "            (self.root / rel).write_text(text)\n\n"
                 "def init(aew_root):\n    files = {'knowledge/P.md': 'a', 'policy/g.yaml': 'b'}\n"
                 "    Store(aew_root).create(files)\n", top=TOP | {"knowledge", "policy"})
    assert sorted(a.writers) == ["knowledge/P.md", "policy/g.yaml"]


def test_a_temporary_directory_bound_by_with_is_outside():
    a = analysed("def f():\n    with tempfile.TemporaryDirectory() as d:\n        (Path(d) / 'x').write_text('x')\n")
    assert "a temporary directory" in a.outside and a.writers == {} and a.unresolved == {}


# ----------------------------------------------------------------------------------------- destinations, unresolved

@pytest.mark.parametrize(("source", "fragment"), [
    ("def f(path):\n    path.write_text('x')\n", "which no static call binds"),
    ("def f():\n    open(os.environ.get('P'), 'w')\n", "a callee this reading cannot name"),
    ("def f(thing):\n    thing.where().write_text('x')\n", "a callee this reading cannot name"),
    ("def f():\n    Path('x.txt').write_text('x')\n", "a relative path"),
    ("def f(aew_root, name):\n    (aew_root / name).write_text('x')\n", "first directory or file name is computed"),
    ("def f(aew_root):\n    (aew_root / 'newdir' / 'x').write_text('x')\n", "not in the declared set"),
    ("def f(a):\n    (a.run_dir / 'x').write_text('x')\n", "is not a value this reading can follow"),
])
def test_a_destination_this_reading_cannot_place_is_an_unresolved_record_with_its_reason(source, fragment):
    a = analysed(source)
    assert a.writers == {} and any(fragment in r for r in reasons(a)), (source, reasons(a))
    records = W.records_of(a)
    assert [r.key for r in records] == [f"unresolved:aew.m:f:{(r.fact or {})['primitive']}" for r in records]
    assert all(fragment in r.coverage["unresolved"][0]["why"] for r in records if r.key.startswith("unresolved"))


def test_a_destination_with_a_placed_alternative_and_an_unplaced_one_is_both():
    a = analysed("def f(aew_root, other, flag):\n    p = aew_root / 'local' / 'a' if flag else other\n"
                 "    p.write_text('x')\n")
    assert sorted(a.writers) == ["local/a"] and a.unresolved


def test_a_write_at_module_level_is_refused_rather_than_given_a_fake_anchor():
    with pytest.raises(C.ReferenceError, match="writes at import time"):
        analysed("open('x', 'w')\n")


def test_the_write_mechanism_is_not_a_writer_and_its_callers_are():
    extra = {"aew.util": "import os\n\ndef atomic_write(path, data):\n    os.replace(str(path) + '.t', path)\n",
             "aew.engine.store": "def write_file(store, path, data):\n    path.write_text(data)\n"}
    a = analysed("from aew.engine.store import write_file\n\n"
                 "def f(aew_root):\n    write_file(aew_root, aew_root / 'state' / 'k', 'x')\n"
                 "    atomic_write(aew_root / 'local' / 'j', 'x')\n", extra=extra)
    assert sorted(a.writers) == ["local/j", "state/k"] and a.unresolved == {}
    assert {w.module for ws in a.writers.values() for w in ws} == {"aew.m"}


# ------------------------------------------------------------------------------------------------ the declared set

def test_the_first_entry_of_every_placed_path_is_what_the_declared_set_is_held_to():
    src = ("def f(aew_root):\n    (aew_root / 'state' / 'a').write_text('x')\n"
           "    (aew_root / 'local' / 'b').write_text('x')\n")
    a = analysed(src)
    assert W.derived_top_level(a.sites) == {"state", "local"}
    narrow = analysed(src, top=frozenset({"state"}))
    assert sorted(narrow.writers) == ["state/a"] and any("`local`" in r for r in reasons(narrow))


# ---------------------------------------------------------------------------------------------------------- reach

REACH = ("def w(aew_root):\n    (aew_root / 'local' / 'w').write_text('x')\n\n"
         "def mid():\n    w(ROOT)\n\ndef main():\n    mid()\n\n"
         "def lonely(aew_root):\n    (aew_root / 'local' / 'l').write_text('x')\n\n"
         "def names_only():\n    cb = w\n    return cb\n\ndef root_b():\n    names_only()\n\n"
         "def inner_user():\n    def helper(aew_root):\n        (aew_root / 'local' / 'i').write_text('x')\n"
         "    helper(ROOT)\n\ndef main2():\n    inner_user()\n\n"
         "def command(a):\n    (ROOT / 'local' / 'c').write_text('x')\n\n"
         "def build(p):\n    p.set_defaults(handler=command)\n\ndef cli_main():\n    build(None)\n")


def test_a_writer_is_reached_by_a_chain_of_calls_from_the_function_that_declares_an_entry_point():
    a = analysed(REACH, roots={("aew.m", "main"): {"aew.harness.supervisor"}, ("aew.m", "main2"): {"aew.stg02.server"}})
    assert a.reach[("aew.m", "w")] == {"aew.harness.supervisor"}
    assert ("aew.m", "lonely") not in a.reach, "a writer nothing calls is unreached"
    assert ("aew.m", "w") not in {k for k, v in a.reach.items() if "aew.stg02.server" in v}, "a name is not a call"
    assert a.reach[("aew.m", "inner_user.helper")] == {"aew.stg02.server"}, "a nested function is reached by its name"


def test_a_registered_cli_handler_is_reached_from_the_function_that_declares_the_clis_roles():
    a = analysed(REACH, roots={("aew.m", "cli_main"): {"aew", "aew lead mcp"}}, dispatchers={("aew.m", "cli_main")})
    assert a.reach[("aew.m", "command")] == {"aew", "aew lead mcp"}
    plain = analysed(REACH, roots={("aew.m", "cli_main"): {"aew", "aew lead mcp"}})
    assert ("aew.m", "command") not in plain.reach, "without the dispatch edge the handler is not reached"
    wrapped = analysed(REACH.replace("handler=command", "handler=lambda a: command(a)"),
                       roots={("aew.m", "cli_main"): {"aew"}}, dispatchers={("aew.m", "cli_main")})
    assert wrapped.reach[("aew.m", "command")] == {"aew"}, "a lambda handler registers the function it names"


def test_a_writer_no_chain_reaches_is_unresolved_on_its_records_and_a_reached_one_is_not():
    a = analysed(REACH, roots={("aew.m", "main"): {"aew"}})
    by_key = {r.key: r for r in W.records_of(a) if not r.key.startswith("unresolved")}
    lonely, reached = by_key["local/l"], by_key["local/w"]
    assert W.NO_CHAIN in [i["why"] for i in lonely.fact_coverage["writers"]["unresolved"]]  # type: ignore[index]
    assert W.NO_CHAIN not in [i["why"] for i in reached.fact_coverage["writers"]["unresolved"]]  # type: ignore[index]


def test_a_non_writer_root_is_exclusive_only_when_its_function_declares_no_store_writer():
    roots = {("aew.cli", "main"): {"aew", "aew lead mcp"}, ("aew.stg", "main"): {"aew.stg02.server"},
             ("aew.sup", "main"): {"aew.harness.supervisor"}}
    assert W.exclusive_non_writers(roots, KINDS) == {"aew.stg02.server"}


# ----------------------------------------------------------------------- the family's own record rules, planted

def real_records() -> dict[str, dict[str, Any]]:
    a = analysed("REL = 'state/x.yaml'\n\ndef f(aew_root):\n    atomic_write(aew_root / REL, 'x')\n\n"
                 "def g(a):\n    open(a.p, 'w')\n", roots={("aew.m", "f"): {"aew"}})
    return {r.id: r.as_json() for r in W.records_of(a)}


def test_the_family_records_of_a_sound_analysis_have_no_problem():
    assert W.record_problems(real_records(), KINDS) == []


def mutate(records: dict[str, Any], rid: str, path: list[Any], value: Any) -> dict[str, Any]:
    out = copy.deepcopy(records)
    node = out[rid]
    for step in path[:-1]:
        node = node[step]
    if value is Ellipsis:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return out


PATH_ID, UNRESOLVED_ID = "writers:state/x.yaml", "writers:unresolved:aew.m:g:open"
FAULTS = [
    ("a mechanism that is neither", PATH_ID, ["fact", "writers", 0, "mechanism"], "other", "has mechanism 'other'"),
    ("a writer without its entry kinds", PATH_ID, ["fact", "writers", 0, "entry_kinds"], Ellipsis, "is not ["),
    ("an entry point that is not a row of the table", PATH_ID, ["fact", "writers", 0, "entry_points"], ["aew.nope"],
     "is not in the table"),
    ("entry kinds that are not the entry points' kinds", PATH_ID, ["fact", "writers", 0, "entry_kinds"], ["non_writer"],
     "entry kinds that are not"),
    ("a writer that names no primitive", PATH_ID, ["fact", "writers", 0, "via"], [], "names no primitives"),
    ("a path record with no writer", PATH_ID, ["fact", "writers"], [], "at least one writer"),
    ("a prefix that is not the key", PATH_ID, ["fact", "prefix"], "state/y.yaml", "prefix and directory"),
    ("a path record that does not point at the unresolved writes", PATH_ID, ["coverage", "unresolved"], [],
     "coverage does not point"),
    ("writers without their coverage", PATH_ID, ["fact_coverage", "writers"], Ellipsis, "no fact_coverage for writers"),
    ("an unresolved write with an empty reason", UNRESOLVED_ID, ["fact", "reason"], "", "all non-empty"),
    ("an unresolved write whose key is not its anchor", UNRESOLVED_ID, ["anchor", "symbol"], "h", "the key is not"),
    ("an unresolved write that carries another reason", UNRESOLVED_ID, ["coverage", "unresolved", 0, "why"], "x",
     "does not carry its own reason"),
]


@pytest.mark.parametrize(("what", "rid", "path", "value", "fragment"), FAULTS, ids=[f[0] for f in FAULTS])
def test_each_planted_fault_in_a_family_record_is_refused_by_its_own_rule(what, rid, path, value, fragment):
    records = real_records()
    assert W.record_problems(records, KINDS) == []
    problems = W.record_problems(mutate(records, rid, path, value), KINDS)
    assert problems and any(fragment in p for p in problems), (what, problems)
