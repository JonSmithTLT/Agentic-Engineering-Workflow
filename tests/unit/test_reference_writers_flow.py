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
import re
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
        from reference_families import common, writers, writers_flow, writers_reach, writers_roles, writers_text
    finally:
        sys.path.remove(here)
    return common, writers, writers_flow, writers_reach, writers_roles, writers_text


C, W, F, R, K, T = _tools()
TOP = frozenset({"state", "local", "work", "evidence", "records", "project.yaml"})
KINDS = {"aew": "store_writer", "aew lead mcp": "non_writer", "aew (worker run)": "non_writer",
         "aew.harness.supervisor": "store_writer", "aew.stg02.server": "non_writer"}
HEAD = ("import os\nimport shutil\nimport sqlite3\nimport tempfile\nfrom pathlib import Path\n"
        "from aew.util import atomic_write, create_exclusive\n")


def program(sources: dict[str, str]) -> Any:
    return F.Program.of({name: (ast.parse(text), False) for name, text in sources.items()})


def analysed(source: str, *, extra: dict[str, str] | None = None, top=TOP, roots=None) -> Any:
    return W.analyse(program({"aew.m": HEAD + source, **(extra or {})}), top, roots or {}, KINDS)


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
    # F3 (review of #254): a mode or flags that is a local name is read through the function's assignments
    ("def f(p):\n    flags = os.O_WRONLY | os.O_CREAT\n    os.open(p, flags, 0o644)", {"os.open": 1}),
    ("def f(p):\n    flags = os.O_RDONLY\n    flags |= os.O_CREAT\n    os.open(p, flags)", {"os.open": 1}),
    ("def f(p):\n    mode = 'w'\n    open(p, mode)", {"open": 1}),
    ("def f(p, x):\n    mode = 'w' if x else 'r'\n    open(p, mode)", {"open": 1}),
    ("def f(p, x):\n    p.open('w' if x else 'r')", {"Path.open": 1}),
    ("from os import O_CREAT\nos.open(p, O_CREAT)", {"os.open": 1}),
    # ... and one that cannot be read is marked, never taken for a read
    ("def f(p, flags):\n    os.open(p, flags)", {"os.open?": 1}),
    ("def f(p, mode):\n    open(p, mode)", {"open?": 1}),
    ("def f(p, mode):\n    open(p, mode=mode)", {"open?": 1}),
    ("def f(p, m):\n    p.open(mode=m)", {"Path.open?": 1}),
    ("def f(p):\n    flags = os.O_RDONLY | extra\n    os.open(p, flags)", {"os.open?": 1}),
    # P1 (quick check of #254): a name that is only augmented started as something the function does not show
    ("def f(p, flags):\n    flags |= os.O_NOFOLLOW\n    os.open(p, flags)", {"os.open?": 1}),
    ("def f(p, mode):\n    mode += 'b'\n    open(p, mode)", {"open?": 1}),
]
NOT_WRITES = [
    "text.replace('a', 'b')",                    # str.replace takes two arguments
    "when.replace(tzinfo=None)",                 # datetime.replace takes keywords only
    "open(p)", "open(p, 'r')", "open(p, 'rb')",  # reads
    "p.open()", "p.open('rb')",
    "def f(p):\n    mode = 'r'\n    open(p, mode)",
    "def f(p):\n    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)\n    flags |= os.O_NONBLOCK\n"
    "    os.open(p, flags)",
    # a flags name is read in its own function: the write flags of another function's `flags` are not this one's
    "def a(p):\n    flags = os.O_WRONLY\n\ndef b(p):\n    flags = os.O_RDONLY\n    os.open(p, flags)",
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


PROBES = {
    # the classes of the family's `cannot see` list that are about a primitive: both readers find nothing
    "conditional-callee": "(create_exclusive if x else atomic_write)(p, 'x')",
    "local-name-primitive": "put = atomic_write\nput(p, 'x')",
    "computed-method": "getattr(p, 'write_text')('x')",
    "subprocess": "subprocess.run(['cp', a, b])",
    "other-openers": "codecs.open(p, 'w')",
    "tempfile-in-aew": "tempfile.mkstemp(dir=d)",
    "keyword-target": "a.rename(target=b)",
    "other-session-spelling": "s.write('work/x', 'y')",
    "positional-open-mode": "def f(p, req):\n    OPENER.open(req, timeout=3)",
    "metadata-calls": "os.utime(p)\nos.chmod(p, 0o700)\nfsync_dir(d)",
}
THE_REST = {"cross-function-path", "handler-by-name"}  # about a destination or a handler: probed below


def test_the_cannot_see_list_has_a_probe_for_each_class_and_nothing_else():
    assert set(PROBES) | THE_REST == {name for name, _ in W.CANNOT_SEE}
    assert len({name for name, _ in W.CANNOT_SEE}) == len(W.CANNOT_SEE)


@pytest.mark.parametrize("name", sorted(PROBES))
def test_what_neither_reader_can_see_is_pinned_by_a_probe_each(name):
    """Each class is missed by both readers, so they agree and the tree check cannot flag it: it is listed on the page
    (from the one tuple the probes read) and pinned here."""
    ast_found, text_found = counts("from aew.util import atomic_write, create_exclusive\nimport subprocess\n"
                                   + PROBES[name] + "\n")
    assert (dict(ast_found), dict(text_found)) == ({}, {}), name


def test_a_path_written_where_it_was_not_built_is_an_unresolved_record_not_a_miss():
    a = analysed("def f(a):\n    (a.run_dir / 'x').write_text('x')\n")
    assert a.writers == {} and any("not a value this reading can follow" in r for r in reasons(a))


def test_the_page_says_each_class_of_what_it_cannot_see_and_names_the_primitives_it_reads():
    a = analysed("REL = 'state/x.yaml'\n\ndef f(aew_root):\n    atomic_write(aew_root / REL, 'x')\n")
    page = W.page(a, W.records_of(a), tuple(sorted(TOP)))
    assert all(text in page for _, text in W.CANNOT_SEE)
    assert all(f"`{label}`" in page for label in W.primitive_labels()) and "`session.write`" in page


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


def test_a_sibling_with_a_computed_name_is_the_same_path_so_a_write_protocol_is_one_record():
    """A temporary file named by the process (`f".s.{os.getpid()}.tmp"`) is part of the write protocol of its target."""
    a = analysed("def f(aew_root):\n"
                 "    path = aew_root / 'local' / 's.json'\n"
                 "    tmp = path.with_name(f'.s.{os.getpid()}.tmp')\n"
                 "    tmp.write_text('x')\n"
                 "    os.replace(tmp, path)\n"
                 "    twin = path.with_name(f'.{path.name}.{os.getpid()}.tmp')\n"
                 "    twin.write_text('x')\n")
    assert sorted(a.writers) == ["local/s.json"]
    assert writers_of(a, "local/s.json") == [("aew.m", "f", W.DIRECT, ("Path.write_text", "os.replace"))]


def test_a_sibling_with_a_fixed_name_is_a_file_of_its_own():
    """Review of #254, F2: `with_name("endpoint.lock")`, a fixed `with_suffix`, and the path's own name plus a fixed
    suffix (the turnstile's `.queue`) name files that are not the path they came from."""
    a = analysed("LOCK_NAME = 'endpoint.lock'\n\n"
                 "def f(aew_root):\n"
                 "    locator = aew_root / 'local' / 'operator' / 'endpoint.json'\n"
                 "    locator.with_name(LOCK_NAME).write_text('x')\n"
                 "    locator.with_suffix('.tmp').write_text('x')\n"
                 "    locator.with_stem('endpoint2').write_text('x')\n"
                 "    open(locator.with_name(locator.name + '.queue'), 'a+b')\n")
    assert sorted(a.writers) == ["local/operator/endpoint.json.queue", "local/operator/endpoint.lock",
                                 "local/operator/endpoint.tmp", "local/operator/endpoint2.json"]


def test_a_sibling_named_from_the_paths_own_name_suffix_or_stem_with_a_fixed_end_is_a_file_of_its_own():
    """Quick check of #254, P2: the f-string and `.suffix +` spellings of the forms the fixed-name rule already has."""
    a = analysed("def f(aew_root):\n"
                 "    p = aew_root / 'local' / 'operator' / 'endpoint.json'\n"
                 "    open(p.with_name(f'{p.name}.queue'), 'a+b')\n"
                 "    p.with_suffix(p.suffix + '.bak').write_text('x')\n"
                 "    p.with_suffix(f'{p.suffix}.old').write_text('x')\n"
                 "    p.with_stem(p.stem + '2').write_text('x')\n")
    assert sorted(a.writers) == ["local/operator/endpoint.json.bak", "local/operator/endpoint.json.old",
                                 "local/operator/endpoint.json.queue", "local/operator/endpoint2.json"]


def test_many_own_name_siblings_are_each_a_record_whatever_the_allocator_does():
    """The fixed end of an own-name sibling is a node the evaluator makes; its memo is keyed by node id, so a node freed
    early lets a later one be answered with the earlier one's value (found by a flaky ablation: 15 of 200 records were
    lost). The nodes are kept."""
    n = 200
    src = "def f(aew_root):\n    p = aew_root / 'local' / 'endpoint.json'\n" + "".join(
        f"    p.with_name(f'{{p.name}}.s{i}').write_text('x')\n" for i in range(n))
    a = analysed(src)
    assert sorted(a.writers) == sorted(f"local/endpoint.json.s{i}" for i in range(n))


def test_a_sibling_named_by_a_value_that_is_neither_fixed_nor_made_by_the_process_cannot_be_placed():
    """Quick check of #254, P2: a name held in a parameter used to fold into the path it came from, which hid a file of
    its own. One built from the process (through a local name too) is still the write protocol of its path."""
    a = analysed("def f(aew_root, name):\n    p = aew_root / 'local' / 's.json'\n"
                 "    p.with_name(name).write_text('x')\n")
    assert a.writers == {} and any("neither fixed nor made by the process" in r for r in reasons(a))
    b = analysed("def f(aew_root):\n    p = aew_root / 'local' / 's.json'\n    suffix = f'.{os.getpid()}.tmp'\n"
                 "    p.with_name(p.name + suffix).write_text('x')\n")
    assert sorted(b.writers) == ["local/s.json"] and b.unresolved == {}


def test_the_page_states_the_rule_for_siblings():
    a = analysed("def f(aew_root):\n    (aew_root / 'local' / 'x').write_text('x')\n")
    assert "A sibling of a path" in W.page(a, W.records_of(a), tuple(sorted(TOP)))


def test_a_with_statements_implicit_calls_are_not_followed_and_an_explicit_call_is():
    """Review of #258, F1: the limit the reach states and the page names. `with Lock():` runs `Lock.__enter__`, which
    no call names; `Lock().__enter__()` is a call."""
    src = ("def lock_write(aew_root):\n    (aew_root / 'local' / 'l').write_text('x')\n\n"
           "class Lock:\n    def __enter__(self):\n        lock_write(None)\n        return self\n\n"
           "    def __exit__(self, *a):\n        pass\n\n"
           "def by_with():\n    with Lock():\n        pass\n\n"
           "def by_name():\n    Lock().__enter__()\n\n"
           "def main():\n    by_with()\n\ndef main2():\n    by_name()\n")
    a = analysed(src, roots={("aew.m", "main"): {"aew.harness.supervisor"}, ("aew.m", "main2"): {"aew.stg02.server"}})
    assert a.reach[("aew.m", "lock_write")] == {"aew.stg02.server"}
    assert ("aew.m", "Lock.__enter__") not in {k for k, v in a.reach.items() if "aew.harness.supervisor" in v}


def test_the_page_states_the_with_limit_and_names_its_live_case():
    a = analysed("def f(aew_root):\n    (aew_root / 'local' / 'x').write_text('x')\n")
    page = W.page(a, W.records_of(a), tuple(sorted(TOP)))
    assert "`with` statement's implicit `__enter__` and `__exit__` calls are not followed" in page
    assert f"`{W.WITH_CASE[0]}:{W.WITH_CASE[1]}`" in page and all(f"`{key}`" in page for key in W.WITH_CASE[2])
    assert "The counts of writer functions reached below are lower bounds." in page, "review of #258, N5"
    assert ("a write whose destination is not placed (the unresolved records) carries no role reach and is not "
            "checked") in page, "the designer's stated limit: the unresolved records are not checked"


def test_a_sibling_of_a_path_that_is_a_parameter_follows_every_path_the_callers_pass():
    a = analysed("class Lock:\n    def __init__(self, path):\n        self.path = path\n"
                 "    def open_queue(self):\n        open(self.path.with_name(self.path.name + '.queue'), 'a+b')\n\n"
                 "def f(aew_root):\n    Lock(aew_root / 'local' / 'a.lock').open_queue()\n"
                 "    Lock(aew_root / 'local' / 'b.lock').open_queue()\n")
    assert sorted(a.writers) == ["local/a.lock.queue", "local/b.lock.queue"]


def test_a_path_that_joins_the_dot_aew_directory_is_the_root_whatever_the_left_side_is():
    a = analysed("def f(repo_root):\n    (repo_root / '.aew' / 'state' / 'x').write_text('x')\n")
    assert sorted(a.writers) == ["state/x"] and a.outside == {}


def test_the_parent_of_the_dot_aew_directory_is_the_repository_not_the_root():
    """Review of #254, N1: `aew_root.parent / "state"` is a path in the repository's tree, not a record under `.aew`."""
    a = analysed("def f(aew_root):\n    (aew_root.parent / 'state' / 'x').write_text('x')\n")
    assert a.writers == {} and "the repository's working tree" in a.outside


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


def test_a_function_annotated_with_a_class_types_its_result_even_when_its_returns_do_not_show_one():
    a = analysed("class Box:\n    def put(self, aew_root):\n        (aew_root / 'local' / 'b').write_text('x')\n\n"
                 "def make(registry) -> Box:\n    return registry.get('box')\n\n"
                 "def main(aew_root, registry):\n    make(registry).put(aew_root)\n",
                 roots={("aew.m", "main"): {"aew"}})
    assert a.reach[("aew.m", "Box.put")] == {"aew"}
    unannotated = ("class Box:\n    def put(self, aew_root):\n        pass\n\n"
                   "def make(registry):\n    return registry.get('box')\n\n"
                   "def main(aew_root, registry):\n    make(registry).put(aew_root)\n")
    bare = analysed(unannotated, roots={("aew.m", "main"): {"aew"}})
    assert ("aew.m", "Box.put") not in bare.reach, "without the annotation nothing types the result"


def test_the_caps_on_callers_and_on_values_make_a_name_unknown_rather_than_slow_or_wrong():
    callers = ("def put(path):\n    path.write_text('x')\n\n"
               + "".join(f"def c{i}(aew_root):\n    put(aew_root / 'local' / 'f{i}')\n\n"
                         for i in range(F.CALLERS + 1)))
    a = analysed(callers)
    assert a.writers == {} and any(f"more than {F.CALLERS} call sites" in r for r in reasons(a))
    values = ("def f(aew_root, n):\n"
              + "".join(f"    if n == {i}:\n        p = aew_root / 'local' / 'v{i}'\n" for i in range(F.VALUES + 1))
              + "    p.write_text('x')\n")
    b = analysed(values)
    assert b.writers == {} and any(f"more than {F.VALUES} possible values" in r for r in reasons(b))


def chained(n):
    src = "def h0(p):\n    p.write_text('x')\n\n" + "".join(f"def h{k}(p):\n    h{k - 1}(p)\n\n" for k in range(1, n))
    return src + f"def top(aew_root):\n    h{n - 1}(aew_root / 'local' / 'd')\n"


def test_a_parameter_passed_down_more_calls_than_the_depth_limit_is_unknown_and_one_within_it_is_placed():
    assert sorted(analysed(chained(3)).writers) == ["local/d"]
    deep = analysed(chained(F.DEPTH + 2))
    assert deep.writers == {} and any(f"resolution depth limit ({F.DEPTH} calls or parameters)" in r
                                      for r in reasons(deep))


# -------------------------------------------------------------------------------------------------------- the caps
# The designer's rule (workspace e350605): past a cap the reading gives a marked item or fails the check, never silence,
# with one planted case per kind of cap. The value, caller and depth caps mark the unresolved write; the typing depth
# marks the writer that only it could reach; the parser reader's two caps mark the registration (the roles module's
# tests). The keys of a mapping parameter read the first callers only until the cap was made to mark (review of the cap
# sweep): the case below is that one.

def keyed(n: int) -> str:
    calls = "".join(f"def c{i}(aew_root):\n    put(aew_root, {{'local/a{i}': 'x'}})\n\n" for i in range(n))
    put = ("def put(aew_root, files):\n    for rel, text in files.items():\n"
           "        (aew_root / rel).write_text(text)\n\n")
    return put + calls


def test_the_keys_of_a_mapping_passed_from_more_call_sites_than_the_cap_are_unknown_and_not_the_first_few():
    assert sorted(analysed(keyed(F.CALLERS)).writers) == sorted(f"local/a{i}" for i in range(F.CALLERS))  # at the cap
    over = analysed(keyed(F.CALLERS + 1))
    assert over.writers == {}, "a partial answer that looks complete is the silence the cap must not make"
    assert [site for site in over.unresolved] == [("aew.m", "put", "Path.write_text")], "the site is marked"


def typed_chain(links: int) -> str:
    """`L0().nxt().nxt()...put(aew_root)`: each link's class is known only by the previous link's result annotation."""
    src = "".join(f"class L{k}:\n    def nxt(self) -> L{k + 1}:\n        return L{k + 1}()\n\n" for k in range(links))
    src += f"class L{links}:\n    def put(self, aew_root):\n        (aew_root / 'local' / 'end').write_text('x')\n\n"
    return src + "def main(aew_root):\n    L0()" + ".nxt()" * links + ".put(aew_root)\n"


def test_a_receiver_typed_through_more_receivers_than_the_cap_is_not_followed_and_its_writer_says_so():
    short, long = F.TYPING_DEPTH - 1, F.TYPING_DEPTH
    reached = analysed(typed_chain(short), roots={("aew.m", "main"): {"aew"}})
    assert reached.reach[("aew.m", f"L{short}.put")] == {"aew"}
    cut = analysed(typed_chain(long), roots={("aew.m", "main"): {"aew"}})
    assert ("aew.m", f"L{long}.put") not in cut.reach
    [record] = W.records_of(cut)
    assert any(item["why"] == W.NO_CHAIN for item in record.fact_coverage["writers"]["unresolved"])  # type: ignore[index]


def test_a_cap_reason_names_the_cap_and_a_value_set_past_it_is_all_or_nothing():
    values = ("def f(aew_root, n):\n"
              + "".join(f"    if n == {i}:\n        p = aew_root / 'local' / 'v{i}'\n" for i in range(F.VALUES + 1))
              + "    p.write_text('x')\n")
    over = analysed(values)
    assert over.writers == {}, "not the first VALUES of them: the set is unknown, and the site is an unresolved write"
    named = f"more than {F.VALUES} possible values of one expression (the cap on values)"
    assert any(named in r for r in reasons(over))


def test_a_refusal_that_lists_problems_says_how_many_it_left_out():
    assert C.shown(["a", "b"], 5) == ["a", "b"]
    assert C.shown(["a", "b", "c"], 2) == ["a", "b", "... and 1 more"]
    assert C.shown([f"p{i}" for i in range(25)]) == [*(f"p{i}" for i in range(20)), "... and 5 more"]


def test_the_page_lists_each_cap_with_its_value_its_source_and_what_happens_past_it():
    a = analysed("def f(aew_root):\n    (aew_root / 'local' / 'x').write_text('x')\n")
    page = W.page(a, W.records_of(a), tuple(sorted(TOP)))
    assert "## Caps of the reading" in page
    for cap in (*F.caps(), *K.caps()):
        assert f"`{cap.name}` = {cap.value}: {cap.bounds}; source: {cap.source}; past it: {cap.past}." in page
    measured = W.page(a, W.records_of(a), tuple(sorted(TOP)), F.caps({"values": 7}))
    assert "The largest in this tree: 7." in measured


def test_every_cap_and_every_cut_slice_of_the_generator_is_listed_or_excused_one_by_one():
    """The sweep, made mechanical: a module-level integer named like a cap, and a slice cut at a number or a
    constant, in `tools/reference_families`. Each is a cap of `caps()` (and so on the page, with its source and what the
    reading does past it) or a display truncation named here with the reason it cuts no analysis. A new one fails this
    test until it is decided."""
    cap_names = re.compile(r"(DEPTH|CALLERS|VALUES|LIMIT|MAX|CAP|BOUND|BUDGET)")
    constants: set[str] = set()
    slices: set[str] = set()
    for path in sorted((ROOT / "tools" / "reference_families").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and type(node.value.value) is int:
                constants |= {f"{path.stem}.{t.id}" for t in node.targets
                              if isinstance(t, ast.Name) and cap_names.search(t.id)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice) and node.slice.upper is not None:
                upper = node.slice.upper
                if (isinstance(upper, ast.Constant) and type(upper.value) is int) or (
                        isinstance(upper, ast.Name) and upper.id.isupper()):
                    slices.add(f"{path.stem}:{ast.unparse(node)}")
    assert constants == {cap.name for cap in (*F.caps(), *K.caps())}
    assert slices == set(DISPLAY_TRUNCATIONS), "decide each new cut: a cap is listed in caps(), a display cut below"


# A slice of the generator that cuts what it shows and nothing it follows: the text of an expression quoted in a reason
# (the cut is marked by `...`). The refusals that list problems cut through `common.shown`, which says how many it left
# out; the parameter `limit` is not a constant, so the sweep does not see those cuts, and the test above holds them.
DISPLAY_TRUNCATIONS = {"writers_flow:text[:57]": "an expression quoted in a reason, cut with `...`"}


def test_the_token_reader_imports_nothing_of_the_package_and_not_the_ast():
    """The second reader is independent only if it shares no code with the first: standard library tokenizing alone."""
    tree = ast.parse((ROOT / "tools" / "reference_families" / "writers_text.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"__future__", "io", "tokenize", "collections", "collections.abc"}, imported


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


def test_a_value_cut_short_by_the_depth_limit_is_not_reused_where_there_was_depth_to_spare():
    """The memo keys the depth left: an answer given with none (unknown, at the depth limit) must not be the answer of
    the same expression asked later with plenty, or a result would depend on the order the sites are read in."""
    prog = program({"aew.m": HEAD + "def helper(aew_root):\n    return aew_root / 'local' / 'h'\n\n"
                                    "def f(aew_root):\n    p = helper(aew_root)\n    p.write_text('x')\n"})
    evaluator = F.Evaluator(prog)
    func = prog.modules["aew.m"].funcs["f"]
    expr, env = func.assigns["p"][0], F.Env("aew.m", func.key)
    shallow = evaluator._ev(expr, env, 0, frozenset())
    deep = evaluator._ev(expr, env, F.DEPTH, frozenset())
    assert any(v.kind == F.UNK for v in shallow) and {(v.kind, v.text) for v in deep} == {(F.TPL, "local/h")}


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


# --------------------------------------------------------- values through destructuring, returns and the command line

def test_a_tuple_assignment_binds_each_target_to_its_own_element():
    """Placement PR: `a, b = x, y` is `a = x; b = y`, not both names to both values."""
    a = analysed("def f(aew_root):\n    first, second = 'one', 'two'\n"
                 "    (aew_root / 'state' / first).write_text('x')\n"
                 "    (aew_root / 'local' / second).write_text('x')\n")
    assert sorted(a.writers) == ["local/two", "state/one"] and a.unresolved == {}


def test_a_tuple_assignment_to_self_attributes_is_what_the_class_assigns():
    """`self.state_path, self.live_path = Path(state_path), Path(live_path) if ... else None` (the usage meter)."""
    a = analysed("class M:\n    def __init__(self, state_path, live_path=None):\n"
                 "        self.state_path, self.live_path = Path(state_path), live_path\n"
                 "    def save(self):\n        atomic_write(self.state_path, 'x')\n\n"
                 "def f(aew_root):\n    M(aew_root / 'local' / 'meter.json').save()\n")
    assert sorted(a.writers) == ["local/meter.json"] and a.unresolved == {}


def test_a_name_bound_by_a_starred_or_unreadable_destructuring_is_unknown_not_a_guess():
    a = analysed("def f(aew_root, rows):\n    first, *rest = rows\n    (aew_root / 'state' / first).write_text('x')\n"
                 "    one, two = mystery()\n    (aew_root / 'local' / two).write_text('x')\n")
    assert sorted(a.writers) == ["local/{}", "state/{}"], "the unknown element is a computed segment, not a value"


def test_the_element_of_a_tuple_a_call_returns_is_read_in_the_function_that_returns_it():
    a = analysed("def mk(wid):\n    return wid, f'work/{wid}/record.md'\n\n"
                 "def f(aew_root):\n    wid, rel = mk('W1')\n    (aew_root / rel).write_text('x')\n")
    assert sorted(a.writers) == ["work/W1/record.md"] and a.unresolved == {}


def test_a_function_that_returns_something_else_than_a_tuple_leaves_its_element_unknown():
    a = analysed("def mk():\n    return 'state/x'\n\ndef f(aew_root):\n    first, second = mk()\n"
                 "    (aew_root / second).write_text('x')\n")
    assert a.writers == {} and any("first directory or file name is computed" in r for r in reasons(a))


def test_a_key_of_a_dict_a_call_returns_is_its_value_whether_the_dict_is_named_or_returned_in_a_tuple():
    a = analysed("def draft(wid):\n    unit: dict = {'record': f'work/{wid}/record.md', 'other': 'state/o'}\n"
                 "    return wid, unit, 'text'\n\n"
                 "def solo():\n    return {'path': 'local/p'}\n\n"
                 "def f(aew_root):\n    wid, unit, text = draft('W1')\n"
                 "    (aew_root / unit['record']).write_text(text)\n"
                 "    (aew_root / solo()['path']).write_text('x')\n")
    assert sorted(a.writers) == ["local/p", "work/W1/record.md"] and a.unresolved == {}


def test_a_computed_key_of_a_dict_constant_is_each_of_its_values():
    a = analysed("NAMES = {'a': 'ticket.md', 'b': 'story.md'}\n\n"
                 "def f(aew_root, kind):\n    (aew_root / 'work' / NAMES[kind]).write_text('x')\n")
    assert sorted(a.writers) == ["work/story.md", "work/ticket.md"]


def test_a_dict_from_a_parameter_is_not_read():
    a = analysed("def f(aew_root, unit):\n    (aew_root / unit['record']).write_text('x')\n")
    assert a.writers == {} and any("first directory or file name is computed" in r for r in reasons(a))


def test_a_loop_over_literal_rows_takes_the_element_of_each_row_for_each_target():
    a = analysed("def f(aew_root):\n    for name, text in (('a', '1'), ('b', '2')):\n"
                 "        (aew_root / 'state' / name).write_text(text)\n")
    assert sorted(a.writers) == ["state/a", "state/b"]


DROP = "def drop(paths):\n    for path in paths:\n        path.unlink()\n\n"


def test_a_loop_over_a_list_passed_as_an_argument_takes_the_elements_the_caller_built():
    """Placement PR: the signal files `finalize` collects and hands to `_unlink`: a conditional, a slice, `sorted` and a
    glob on the way, and a local list built with `append`."""
    a = analysed(DROP + "def f(aew_root):\n    spool = aew_root / 'local' / 'signals'\n    folded = []\n"
                 "    for entry in sorted(spool.glob('*.json'))[:5] if spool.is_dir() else []:\n"
                 "        folded.append(entry)\n    drop(folded)\n")
    assert sorted(a.writers) == ["local/signals/{}"] and a.unresolved == {}


def test_a_conditional_iterable_is_the_elements_of_either_arm():
    a = analysed("def f(aew_root, cond):\n    for name in ('a', 'b') if cond else ('c',):\n"
                 "        (aew_root / 'state' / name).write_text('x')\n")
    assert sorted(a.writers) == ["state/a", "state/b", "state/c"]


@pytest.mark.parametrize("calls", [
    "",                                                     # nothing calls it
    "def f():\n    drop(load())\n",                         # a list from a call this reading cannot read
    "def f(aew_root):\n    drop(aew_root / 'local')\n",     # not a list at all
])
def test_a_list_argument_this_reading_cannot_read_leaves_the_loop_variable_unknown(calls):
    a = analysed(DROP + calls)
    assert a.writers == {} and a.unresolved


# A value on the command line: the supervisor reads `--run-dir`, and the start of it spells the value.
SUPERVISOR = ("import argparse\nfrom pathlib import Path\n\n"
              "def write_it(run_dir):\n    (run_dir / 'heartbeat').write_text('x')\n\n"
              "def main():\n    parser = argparse.ArgumentParser()\n    parser.add_argument('--run-dir')\n"
              "    args = parser.parse_args()\n    write_it(Path(args.run_dir))\n")
START = ("import sys\n\ndef launch(aew_root):\n    directory = aew_root / 'local' / 'runs' / 'r'\n"
         "    spawn([sys.executable, '-m', 'aew.sup', '--run-dir', str(directory)])\n")


def test_a_value_on_the_command_line_is_what_the_start_of_that_process_spells():
    a = analysed(START, extra={"aew.sup": SUPERVISOR})
    assert sorted(a.writers) == ["local/runs/r/heartbeat"] and a.unresolved == {}
    again = "\ndef again(aew_root):\n    spawn(['-m', 'aew.sup', '--run-dir', str(aew_root / 'local' / 's')])\n"
    two = analysed(START + again, extra={"aew.sup": SUPERVISOR})
    assert sorted(two.writers) == ["local/runs/r/heartbeat", "local/s/heartbeat"]


STARTS = {
    "another process": "spawn(['-m', 'aew.other', '--run-dir', str(aew_root / 'local' / 'r')])",
    "another flag": "spawn(['-m', 'aew.sup', '--state-dir', str(aew_root / 'local' / 'r')])",
    "no flag": "spawn(['-m', 'aew.sup'])",
    "no start": "pass",
}


@pytest.mark.parametrize("start", [f"def launch(aew_root):\n    {body}\n" for body in STARTS.values()],
                         ids=list(STARTS))
def test_a_command_line_value_no_start_of_the_process_passes_is_named_by_its_starter_and_unresolved(start):
    a = analysed(start, extra={"aew.sup": SUPERVISOR})
    assert a.writers == {} and any("which no AEW start of it passes" in r for r in reasons(a))


def test_an_attribute_of_something_that_is_not_parsed_arguments_is_not_a_command_line_value():
    a = analysed("def f(aew_root, args):\n    (aew_root / args.name).write_text('x')\n")
    assert a.writers == {} and all("no AEW start" not in r for r in reasons(a))


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
         "    helper(ROOT)\n\ndef main2():\n    inner_user()\n")


def test_a_writer_is_reached_by_a_chain_of_calls_from_the_function_that_declares_an_entry_point():
    a = analysed(REACH, roots={("aew.m", "main"): {"aew.harness.supervisor"}, ("aew.m", "main2"): {"aew.stg02.server"}})
    assert a.reach[("aew.m", "w")] == {"aew.harness.supervisor"}
    assert ("aew.m", "lonely") not in a.reach, "a writer nothing calls is unreached"
    assert ("aew.m", "w") not in {k for k, v in a.reach.items() if "aew.stg02.server" in v}, "a name is not a call"
    assert a.reach[("aew.m", "inner_user.helper")] == {"aew.stg02.server"}, "a nested function is reached by its name"


def test_a_writer_no_chain_reaches_is_unresolved_on_its_records_and_a_reached_one_is_not():
    a = analysed(REACH, roots={("aew.m", "main"): {"aew"}})
    by_key = {r.key: r for r in W.records_of(a) if not r.key.startswith("unresolved")}
    lonely, reached = by_key["local/l"], by_key["local/w"]
    assert W.NO_CHAIN in [i["why"] for i in lonely.fact_coverage["writers"]["unresolved"]]  # type: ignore[index]
    assert W.NO_CHAIN not in [i["why"] for i in reached.fact_coverage["writers"]["unresolved"]]  # type: ignore[index]


# ------------------------------------------------------------------------------- the CLI cut per role (addendum 4)

GENERAL, NAMED, WORKER = "aew", "aew lead mcp", "aew (worker run)"
CLI_ROOT = ("aew.m", "cli_main")
CLI = ("import argparse\n\n"
       "def store_write(aew_root):\n    (aew_root / 'state' / 's').write_text('x')\n\n"
       "def local_write(aew_root):\n    (aew_root / 'local' / 'l').write_text('x')\n\n"
       "def common_write(aew_root):\n    (aew_root / 'state' / 'c').write_text('x')\n\n"
       "def cmd_store(a):\n    store_write(None)\n\n"
       "def cmd_mcp(a):\n    local_write(None)\n    store_write(None)\n\n"
       "def register(sub):\n"
       "    p = sub.add_parser('init')\n    p.set_defaults(handler=cmd_store)\n"
       "    lead = sub.add_parser('lead')\n    lsub = lead.add_subparsers(dest='x')\n"
       "    q = lsub.add_parser('mcp')\n    q.set_defaults(handler=lambda a: cmd_mcp(a))\n\n"
       "def build():\n    parser = argparse.ArgumentParser(prog='aew')\n"
       "    register(parser.add_subparsers(dest='command'))\n    common_write(None)\n    return parser\n\n"
       "def cli_main(argv):\n    build()\n")


def role_of(path: tuple[str, ...]) -> str:
    return NAMED if tuple(path[:2]) == ("lead", "mcp") else GENERAL


def cli_analysis(source: str = CLI) -> Any:
    prog = program({"aew.m": HEAD + source})
    roles = K.Roles(GENERAL, frozenset({NAMED}), WORKER)
    cli = ({CLI_ROOT}, roles, K.cut_of(prog, role_of))
    return W.analyse(prog, TOP, {CLI_ROOT: {GENERAL, NAMED, WORKER}}, KINDS, cli)


def test_a_handler_is_reached_by_the_role_of_its_command_and_the_clis_own_calls_by_every_role():
    a = cli_analysis()
    assert a.reach[("aew.m", "cmd_store")] == {GENERAL}
    assert a.reach[("aew.m", "cmd_mcp")] == {NAMED}
    assert a.reach[("aew.m", "register.<handler1>")] == {NAMED}, "a lambda handler is a function of its own"
    assert a.reach[("aew.m", "local_write")] == {NAMED}
    assert a.reach[("aew.m", "store_write")] == {GENERAL, NAMED}
    assert a.reach[("aew.m", "register")] == {GENERAL, NAMED, WORKER}, "the parser's construction is every role's"
    assert a.reach[("aew.m", "common_write")] == {GENERAL, NAMED, WORKER}
    assert WORKER not in a.reach[("aew.m", "cmd_store")], "the environment's role is reached by no command"


def test_a_lambda_handler_does_not_put_its_calls_on_the_path_every_command_shares():
    """The lambda is called by the CLI's dispatch, not by the function that registers it: else the engine would be
    on the common path and every role would reach every writer."""
    funcs = program({"aew.m": HEAD + CLI}).modules["aew.m"].funcs
    assert [ast.unparse(c.func) for c in funcs["register.<handler1>"].calls] == ["cmd_mcp"]
    assert "cmd_mcp" not in {ast.unparse(c.func) for c in funcs["register"].calls}


def test_the_store_writes_a_non_writer_role_reaches_are_the_finding_and_its_local_writes_are_permitted():
    a = cli_analysis()
    records = W.records_of(a)
    store, local = W.role_reach(a, records)
    assert store[NAMED] == {("aew.m", "store_write"), ("aew.m", "common_write")}
    assert local[NAMED] == {("aew.m", "local_write")}
    assert store[WORKER] == {("aew.m", "common_write")} and local[WORKER] == set()
    lines = W.page(a, records, tuple(sorted(TOP))).splitlines()
    checked = next(line for line in lines if line.startswith("**Checked:**"))
    permitted = next(line for line in lines if line.startswith("**Permitted:**"))
    assert "`aew.m:store_write`" in checked and "`aew.m:common_write`" in checked
    assert "`aew.m:local_write`" in permitted and "`aew.m:local_write`" not in checked


@pytest.mark.parametrize(("directory", "mechanism", "store"), [
    ("state", W.DIRECT, True), ("state", W.STORE_TRANSACTION, True), ("local", W.DIRECT, False),
    ("local", W.STORE_TRANSACTION, True), (".gitignore", W.DIRECT, True)])
def test_a_write_is_to_the_store_by_its_prefix_and_its_mechanism(directory, mechanism, store):
    assert W.store_class(directory, mechanism) is store


def test_a_store_transaction_write_under_local_that_a_non_writer_role_reaches_is_the_finding():
    a = cli_analysis(CLI + "\ndef txn_local(session):\n    session.write('local/z', 'x')\n\n"
                     "def cmd_txn(a):\n    txn_local(None)\n\n"
                     "def more(sub):\n    lsub = sub.add_parser('lead').add_subparsers()\n"
                     "    lsub.add_parser('mcp').set_defaults(handler=cmd_txn)\n\n"
                     "def build2():\n    more(argparse.ArgumentParser().add_subparsers())\n")
    store, local = W.role_reach(a, W.records_of(a))
    assert ("aew.m", "txn_local") in store[NAMED] and ("aew.m", "txn_local") not in local[NAMED]


def test_a_writer_a_cli_command_reaches_says_the_worker_role_is_given_nothing_by_the_call_graph():
    """The call graph attributes nothing to the environment's role, so a writer any CLI command's handler reaches (the
    named roles' too: every command runs as the worker run when the environment says so) carries one item that says its
    absence from `entry_points` is no evidence and where a non-writer's write is refused, whatever the writer writes;
    one the common path gives every role, and one no CLI command reaches, do not (addendum 5)."""
    a = cli_analysis(CLI + "\ndef local_only(aew_root):\n    (aew_root / 'local' / 'g').write_text('x')\n\n"
                     "def cmd_local(a):\n    local_only(None)\n\n"
                     "def more(sub):\n    sub.add_parser('other').set_defaults(handler=cmd_local)\n\n"
                     "def build2():\n    more(argparse.ArgumentParser().add_subparsers())\n")
    by_key = {r.key: r for r in W.records_of(a) if not r.key.startswith("unresolved")}
    gate = W.gate_item(a.roles)
    listed = {k: r.fact_coverage["writers"]["unresolved"] for k, r in by_key.items()}  # type: ignore[index]
    assert gate in listed["state/s"], "a store write the general handlers reach"
    assert gate in listed["local/g"], "and a local write they reach: the item is not about the lock alone"
    assert gate in listed["local/l"], "a writer only a non-aew command's handler reaches (addendum 5)"
    assert gate not in listed["state/c"], "the common path gives the worker role this one"
    assert (gate["module"], gate["symbol"]) == W.GATE_SYMBOL and W.GATE_TEST in gate["why"]
    records = {r.id: r.as_json() for r in W.records_of(a)}
    assert W.record_problems(records, KINDS, a.roles, a.undecided) == []
    cut = copy.deepcopy(records)
    cut["writers:state/s"]["fact_coverage"]["writers"]["unresolved"] = [W.pointer_item()]
    problems = W.record_problems(cut, KINDS, a.roles, a.undecided)
    assert any("the call graph gives that role nothing" in p for p in problems), problems


UNREAD = CLI.replace("    lead = sub.add_parser('lead')\n", "    lead = mystery(sub)\n")


def test_a_handler_of_a_command_that_cannot_be_read_is_run_by_every_role_and_its_writers_say_so():
    """Fail closed: the registration's parser comes from a call this reading cannot follow, so its handler may be a
    non-writer's. Its writers list every role and name the function that registers it."""
    assert cli_analysis().undecided == {}
    a = cli_analysis(UNREAD)
    assert a.reach[("aew.m", "cmd_mcp")] == {GENERAL, NAMED, WORKER}
    assert a.undecided[("aew.m", "cmd_mcp")] == {("aew.m", "register")}
    item = W.undecided_item(("aew.m", "register"))
    by_key = {r.key: r for r in W.records_of(a) if not r.key.startswith("unresolved")}
    assert item in by_key["local/l"].fact_coverage["writers"]["unresolved"]  # type: ignore[index]
    store, _ = W.role_reach(a, W.records_of(a))
    assert ("aew.m", "store_write") in store[WORKER], "a handler of no known command is every role's"
    records = {r.id: r.as_json() for r in W.records_of(a)}
    assert W.record_problems(records, KINDS, a.roles, a.undecided) == []
    cut = copy.deepcopy(records)
    cut["writers:local/l"]["fact_coverage"]["writers"]["unresolved"] = [W.pointer_item()]
    problems = W.record_problems(cut, KINDS, a.roles, a.undecided)
    assert any("for a command this reading could not read" in p for p in problems), problems


def test_a_root_that_is_not_the_clis_does_not_reach_the_handler_of_a_command_that_cannot_be_read():
    """Review of #258, N2: the handlers of an unread command are run by every role the CLI declares, and by no other
    entry point (a second, non-CLI root must not be given them)."""
    prog = program({"aew.m": HEAD + UNREAD + "\ndef sup_main():\n    pass\n"})
    roles = K.Roles(GENERAL, frozenset({NAMED}), WORKER)
    cli = ({CLI_ROOT}, roles, K.cut_of(prog, role_of))
    roots = {CLI_ROOT: {GENERAL, NAMED, WORKER}, ("aew.m", "sup_main"): {"aew.harness.supervisor"}}
    a = W.analyse(prog, TOP, roots, KINDS, cli)
    assert a.reach[("aew.m", "cmd_mcp")] == {GENERAL, NAMED, WORKER}
    assert all("aew.harness.supervisor" not in keys for keys in a.reach.values() if keys != {"aew.harness.supervisor"})


BOTH = ("def both(aew_root):\n    (aew_root / 'state' / 'b').write_text('x')\n"
        "    (aew_root / 'local' / 'b').write_text('x')\n\n"
        "def cmd_both(a):\n    both(None)\n\n"
        "def more(sub):\n    lsub = sub.add_parser('lead').add_subparsers()\n"
        "    lsub.add_parser('mcp').set_defaults(handler=cmd_both)\n\n"
        "def build2():\n    more(argparse.ArgumentParser().add_subparsers())\n")


def test_a_function_that_writes_both_the_store_and_local_is_a_store_writer_only():
    """Review of #258, N3: it counts once, as a store writer; it is not also listed as permitted."""
    a = cli_analysis(CLI + "\n" + BOTH)
    store, local = W.role_reach(a, W.records_of(a))
    assert ("aew.m", "both") in store[NAMED] and ("aew.m", "both") not in local[NAMED]
    lines = W.page(a, W.records_of(a), tuple(sorted(TOP))).splitlines()
    permitted = next(line for line in lines if line.startswith("**Permitted:**"))
    assert "`aew.m:both`" not in permitted


BYNAME = ("class Eng:\n    def publish(self, aew_root):\n        (aew_root / 'state' / 'p').write_text('x')\n\n"
          "def eng(a) -> Eng:\n    return Eng()\n\n"
          "def register(sub):\n    for name, method in (('publish', 'publish'),):\n"
          "        sub.add_parser(name).set_defaults(handler=lambda a, m=method: getattr(eng(a), m)(None))\n\n"
          "def build():\n    register(argparse.ArgumentParser().add_subparsers())\n\n"
          "def cli_main(argv):\n    build()\n")


def test_a_handler_that_calls_its_engine_method_by_a_name_held_in_a_variable_is_the_pinned_limit():
    """The `handler-by-name` class of the page's `cannot see` list: the command is read (its lambda is a function of its
    own, reached by its role), the method behind `getattr(...)` is not, so its writer has no chain."""
    a = cli_analysis(BYNAME)
    assert a.cut.handlers == {GENERAL: {("aew.m", "register.<handler1>")}}
    assert a.reach[("aew.m", "register.<handler1>")] == {GENERAL}
    assert ("aew.m", "Eng.publish") not in a.reach
    by_key = {r.key: r for r in W.records_of(a) if not r.key.startswith("unresolved")}
    assert W.NO_CHAIN in [i["why"] for i in by_key["state/p"].fact_coverage["writers"]["unresolved"]]  # type: ignore[index]


def test_the_page_says_how_many_registrations_and_which_it_could_not_read():
    page = W.page(cli_analysis(), W.records_of(cli_analysis()), tuple(sorted(TOP)))
    assert "2 registrations of a command handler" in page
    line = page.split("The parser cut:")[1].splitlines()[0]
    assert "cannot read: none. " in line and line.endswith("can name: none.")
    unread = W.page(cli_analysis(UNREAD), W.records_of(cli_analysis(UNREAD)), tuple(sorted(TOP)))
    said = unread.split("The parser cut:")[1].splitlines()[0]
    assert "cannot read: `aew.m:register` (" in said and said.endswith("can name: none.")
    nameless = cli_analysis(CLI.replace("handler=cmd_store", "handler=mystery"))
    said = W.page(nameless, W.records_of(nameless), tuple(sorted(TOP))).split("The parser cut:")[1].splitlines()[0]
    assert "cannot read: none. " in said and said.endswith("can name: `aew.m:register`."), said


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
    ("a path record whose writers do not point at the unresolved writes", PATH_ID,
     ["fact_coverage", "writers", "unresolved"], [], "its writers do not point at the unresolved writes"),
    ("an unresolved write with a mechanism that is neither", UNRESOLVED_ID, ["fact", "mechanism"], "other",
     "is not one of the two"),
    ("named_by without its coverage", PATH_ID, ["fact_coverage", "named_by"], Ellipsis,
     "no fact_coverage for named_by"),
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
