"""The layout family of the generated reference (STG-12 S12-2, DOC-04), on planted sources and owners.

``tools/reference_families/layout_reads.py`` and ``layout_reads_text.py`` find the read sites (two readers that share no
code), ``layout.py`` turns the writers family's placed writes and the placed reads into one record per ``.aew`` entry.
Every rule has its planted right case, wrong case and missing case; the tree-wide guarantees (the readers agree on every
module, the records equal what git, the store and the containment layout say) are in
``tests/integration/test_reference_layout.py``.
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
        from reference_families import common, layout, layout_reads, layout_reads_text, writers_flow
    finally:
        sys.path.remove(here)
    return common, layout, layout_reads, layout_reads_text, writers_flow


C, LY, L, LT, F = _tools()
TOP = frozenset({"state", "local", "work", "project.yaml"})
HEAD = ("import os\nimport shutil\nimport sqlite3\nfrom pathlib import Path\n"
        "from aew.util import read_yaml, sha256_file\n")


def program(sources: dict[str, str]) -> Any:
    return F.Program.of({name: (ast.parse(text), False) for name, text in sources.items()})


def placed(source: str, *, extra: dict[str, str] | None = None) -> Any:
    prog = program({"aew.m": HEAD + source, **(extra or {})})
    return L.place(L.read_sites(prog, F.Evaluator(prog)), TOP)


def counts(source: str) -> tuple[Counter[str], Counter[str]]:
    """(the AST reading's read-primitive calls, the token reading's) of one module's source."""
    return L.read_counts(program({"aew.m": source}))["aew.m"], LT.sites(source)


# ------------------------------------------------------------------------------------ the read primitives, both readers

READS = [
    # (source, the labels both readers find)
    ("p.read_text()", {"Path.read_text": 1}),
    ("p.read_bytes()", {"Path.read_bytes": 1}),
    ("p.exists()", {"Path.exists": 1}),
    ("p.is_file()", {"Path.is_file": 1}),
    ("p.is_dir()", {"Path.is_dir": 1}),
    ("p.is_symlink()", {"Path.is_symlink": 1}),
    ("p.stat()", {"Path.stat": 1}),
    ("p.lstat()", {"Path.lstat": 1}),
    ("p.iterdir()", {"Path.iterdir": 1}),
    ("p.glob('*.json')", {"Path.glob": 1}),
    ("p.rglob('*.json')", {"Path.rglob": 1}),
    ("open(p)", {"open": 1}),
    ("open(p, 'r')", {"open": 1}),
    ("open(p, 'rb')", {"open": 1}),
    ("open(p, mode='rb')", {"open": 1}),
    ("p.open()", {"Path.open": 1}),
    ("p.open('rb')", {"Path.open": 1}),
    ("p.open(mode='rb')", {"Path.open": 1}),
    ("os.open(p, os.O_RDONLY)", {"os.open": 1}),
    ("os.open(p, flags=os.O_RDONLY)", {"os.open": 1}),
    ("os.stat(p)", {"os.stat": 1}),
    ("os.lstat(p)", {"os.lstat": 1}),
    ("os.listdir(p)", {"os.listdir": 1}),
    ("os.scandir(p)", {"os.scandir": 1}),
    ("os.path.exists(p)", {"os.path.exists": 1}),
    ("os.path.isfile(p)", {"os.path.isfile": 1}),
    ("os.path.isdir(p)", {"os.path.isdir": 1}),
    ("os.path.getsize(p)", {"os.path.getsize": 1}),
    ("os.path.getmtime(p)", {"os.path.getmtime": 1}),
    ("os.path.islink(p)", {"os.path.islink": 1}),
    ("shutil.copy(a, b)", {"shutil.copy": 1}),
    ("shutil.copy2(a, b)", {"shutil.copy2": 1}),
    ("shutil.copyfile(a, b)", {"shutil.copyfile": 1}),
    ("shutil.copytree(a, b)", {"shutil.copytree": 1}),
    ("read_yaml(p)", {"read_yaml": 1}),
    ("sha256_file(p)", {"sha256_file": 1}),
    ("p.exists(); p.read_text(); open(p)", {"Path.exists": 1, "Path.read_text": 1, "open": 1}),
    # a mode or flags that is a local name is read through the function's assignments
    ("def f(p):\n    mode = 'r'\n    open(p, mode)", {"open": 1}),
    ("def f(p):\n    flags = os.O_RDONLY\n    os.open(p, flags)", {"os.open": 1}),
]
NOT_READS = [
    "open(p, 'w')", "open(p, 'a')", "open(p, 'wb')", "open(p, mode='x')", "p.open('w')", "p.open(mode='x')",
    "os.open(p, os.O_WRONLY | os.O_CREAT)", "os.open(p, flags=os.O_WRONLY)",
    "exists(p)", "glob(p)",                                   # a bare call named like a method is no method call
    "p.write_text('x')", "p.write_bytes(b'x')", "p.mkdir()", "p.unlink()",
    "fh.read()", "fh.readline()", "json.load(fh)",           # a handle, not a path
    "os.path.join(a, b)", "os.getcwd()", "os.fspath(p)",     # path arithmetic, not a read
    "text.replace('a', 'b')", "d.get('exists')",
    "'p.read_text()'", "# p.read_text()", "'''open(p)'''",     # a string and a comment are not code
]


@pytest.mark.parametrize(("source", "expected"), READS)
def test_a_read_primitive_is_found_by_both_readers_with_the_same_label(source, expected):
    ast_found, text_found = counts(HEAD + source + "\n")
    assert dict(ast_found) == expected, source
    assert dict(text_found) == expected, source


@pytest.mark.parametrize("source", NOT_READS)
def test_what_is_not_a_read_is_found_by_neither_reader(source):
    ast_found, text_found = counts(HEAD + source + "\n")
    assert (dict(ast_found), dict(text_found)) == ({}, {}), source


def test_a_primitive_called_through_an_alias_is_the_ast_readings_alone_and_pinned_as_such():
    """The asymmetry the two readers have by construction: tokens cannot follow an import alias, so the AST reading
    finds `st(p)` as `os.stat` and the token reading does not. The agreement test over the tree holds the two to equal
    counts, so a tree that used an alias would fail it until this is decided."""
    ast_found, text_found = counts("from os import stat as st\nst(p)\n")
    assert dict(ast_found) == {"os.stat": 1} and dict(text_found) == {}


def test_a_method_named_like_a_read_primitive_is_a_read_of_its_receiver_whatever_the_receiver_is():
    """Pinned because the page states it: a name is all a method has (it has no import source)."""
    ast_found, text_found = counts("conn.stat()\nsession.glob('x')\n")
    assert dict(ast_found) == dict(text_found) == {"Path.stat": 1, "Path.glob": 1}


PROBES = {
    # the classes of the `cannot see` list: both readers find nothing, so they agree and the tree check cannot flag them
    "subprocess": "subprocess.run(['cat', p])",
    "computed-method": "getattr(p, 'read_text')()",
    "local-name-primitive": "get = read_yaml\nget(p)",
    "other-openers": "codecs.open(p, 'r')\ntarfile.open(p)\nsqlite3.connect(p)\nzipfile.ZipFile(p)\nfh.read()",
    "update-mode": "open(p, 'r+')",
    "unreadable-mode": "def f(p, mode):\n    open(p, mode)",
    "directory-walk": "os.walk(p)\nos.fstat(fd)\nos.access(p, os.R_OK)\nos.readlink(p)\nos.path.lexists(p)\n"
                      "os.path.realpath(p)",
}


def test_the_cannot_see_list_has_a_probe_for_each_class_and_nothing_else():
    assert set(PROBES) == {name for name, _ in L.CANNOT_SEE}
    assert len({name for name, _ in L.CANNOT_SEE}) == len(L.CANNOT_SEE)


@pytest.mark.parametrize("name", sorted(PROBES))
def test_what_neither_reader_can_see_is_pinned_by_a_probe_each(name):
    ast_found, text_found = counts(HEAD + "import subprocess\n" + PROBES[name] + "\n")
    assert (dict(ast_found), dict(text_found)) == ({}, {}), name


def test_the_token_reader_imports_nothing_of_the_package_and_not_the_ast():
    tree = ast.parse((ROOT / "tools" / "reference_families" / "layout_reads_text.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "ast" not in imported
    assert {i for i in imported if i.startswith("reference_families")} == {"reference_families.writers_text"}


# --------------------------------------------------------------------------------------- where a read reads

def classes(got: Any) -> tuple[int, int, int, int]:
    """(sites, placed under `.aew`, outside it or the directory itself, not placed): the last three add up to the
    first."""
    assert got.placed_sites + got.outside_sites + got.unplaced_sites == got.sites
    return got.sites, got.placed_sites, got.outside_sites, got.unplaced_sites


def test_a_read_of_a_path_under_a_declared_entry_is_that_paths_read_by_the_function_that_makes_it():
    got = placed("def f(aew_root):\n    return (aew_root / 'state' / 'x.yaml').read_text()\n")
    assert got.reads == {"state/x.yaml": {("aew.m", "f")}} and got.unplaced == [] and classes(got) == (1, 1, 0, 0)


def test_a_read_through_the_util_mechanism_is_the_callers_and_the_mechanism_itself_is_not_a_reader():
    got = placed("def f(aew_root):\n    return read_yaml(aew_root / 'project.yaml')\n",
                 extra={"aew.util": "def read_yaml(p):\n    return p.read_text()\n"})
    assert got.reads == {"project.yaml": {("aew.m", "f")}} and got.unplaced == []


def test_a_path_a_helper_reads_is_the_helpers_read_and_the_caller_only_passes_it():
    got = placed("def _get(path):\n    return path.read_text()\n\n"
                 "def f(aew_root):\n    return _get(aew_root / 'state' / 'x')\n")
    assert got.reads == {"state/x": {("aew.m", "_get")}}


def test_a_computed_segment_is_a_placeholder_and_a_literal_one_is_kept():
    got = placed("def f(aew_root, wid):\n    return (aew_root / 'work' / wid / 'x.md').read_text()\n")
    assert sorted(got.reads) == ["work/{}/x.md"]


def test_a_directory_listing_and_a_stat_are_reads_of_the_directory():
    got = placed("def f(aew_root):\n    os.stat(aew_root / 'state')\n"
                 "    list((aew_root / 'local' / 'events').glob('*'))\n")
    assert sorted(got.reads) == ["local/events", "state"]


def test_the_path_a_copy_reads_is_its_first_argument_and_never_its_destination():
    """Review of the layout pull request, N-8: which argument of `shutil.copy*` is the path read."""
    got = placed("def f(aew_root, other):\n    shutil.copy(aew_root / 'state' / 'a', other)\n"
                 "    shutil.copy(other, aew_root / 'state' / 'b')\n    shutil.copytree(aew_root / 'work', other)\n")
    assert sorted(got.reads) == ["state/a", "work"]


def test_a_write_mode_open_is_no_read():
    got = placed("def f(aew_root):\n    open(aew_root / 'state' / 'x', 'w')\n")
    assert got.reads == {} and classes(got) == (0, 0, 0, 0)


@pytest.mark.parametrize("source", [
    "def f(repo_root):\n    return (repo_root / 'src' / 'x').read_text()\n",
    "def f(aew_root):\n    return (aew_root.parent / 'state' / 'x').read_text()\n",
    "def f():\n    return Path('/etc/hosts').read_text()\n",
])
def test_a_read_provably_outside_aew_is_no_entry_and_not_unplaced(source):
    got = placed(source)
    assert got.reads == {} and got.unplaced == [] and classes(got) == (1, 0, 1, 0)


def test_a_read_of_the_aew_directory_itself_is_no_entry_and_not_unplaced():
    got = placed("def f(aew_root):\n    return aew_root.exists()\n")
    assert got.reads == {} and got.unplaced == [] and classes(got) == (1, 0, 1, 0)


@pytest.mark.parametrize(("source", "primitive"), [
    ("def f(p):\n    return p.read_text()\n", "Path.read_text"),                                       # a parameter
    ("def f(aew_root):\n    return (aew_root / 'brand-new-dir' / 'x').read_text()\n", "Path.read_text"),  # undeclared
    ("def f(aew_root, d):\n    return (aew_root / d / 'x').read_text()\n", "Path.read_text"),           # computed first
    ("def f(args):\n    return open(args.path)\n", "open"),                                              # command line
])
def test_a_read_of_a_path_this_reading_cannot_place_is_listed_as_unplaced_and_no_entry(source, primitive):
    got = placed(source)
    assert got.reads == {} and got.unplaced == [("aew.m", "f", primitive)] and classes(got) == (1, 0, 0, 1)


def test_a_site_with_one_placed_value_and_one_unplaced_is_both_an_entrys_reader_and_unplaced():
    got = placed("def f(aew_root, p, x):\n    q = (aew_root / 'state' / 'a') if x else p\n    return q.read_text()\n")
    assert got.reads == {"state/a": {("aew.m", "f")}} and got.unplaced == [("aew.m", "f", "Path.read_text")]
    assert classes(got) == (1, 0, 0, 1), "a site with any value unplaced is counted once, as unplaced"


def test_the_site_classes_add_up_over_several_sites():
    got = placed("def f(aew_root, p):\n    (aew_root / 'state' / 'a').read_text()\n    Path('/etc/x').exists()\n"
                 "    p.read_text()\n    aew_root.is_dir()\n    (aew_root / 'work' / 'b').stat()\n")
    assert classes(got) == (5, 2, 2, 1)


def test_a_read_at_import_time_is_refused_and_not_dropped():
    prog = program({"aew.m": HEAD + "TEXT = (aew_root / 'state' / 'x').read_text()\n"})
    with pytest.raises(C.ReferenceError, match="reads at import time"):
        L.read_sites(prog, F.Evaluator(prog))


# ------------------------------------------------------------------------------------------ the records

W1, W2, R1, R2 = ("m.a", "write_one"), ("m.b", "write_two"), ("m.c", "read_one"), ("m.d", "read_two")


def inputs(writers: dict[str, list[Any]] | None = None, reads: dict[str, list[Any]] | None = None, *,
           named: dict[str, list[Any]] | None = None, gitignore: str = "local/\nstate/txn/\n", store: str = "state",
           hidden: tuple[str, ...] = ("local",), top: tuple[str, ...] = ("local", "state", "work")) -> Any:
    return LY.Inputs(top, writers or {}, reads or {}, named or {}, gitignore, store, frozenset(hidden))


def by_key(records: list[Any]) -> dict[str, Any]:
    return {r.key: r for r in records}


def anchor(record: Any) -> tuple[str, str | None]:
    return record.module, record.symbol


def test_the_entries_are_the_declared_top_level_and_every_directory_above_a_placed_path():
    got = by_key(LY.records_of(inputs({"work/{}/x.md": [W1], "state/log/a.json": [W1]}, {"local/a/b.json": [R1]})))
    assert sorted(got) == ["local", "local/a", "state", "state/log", "work", "work/{}"]


def test_an_entry_nothing_names_writes_or_reads_is_refused_not_invented():
    with pytest.raises(C.ReferenceError, match="nothing names, writes or reads it"):
        LY.records_of(inputs({"work/{}/x.md": [W1]}))  # `state` and `local` are declared, and nothing is in them


def test_a_path_directly_in_an_entry_is_its_writers_and_readers_and_one_deeper_is_the_next_entrys():
    got = by_key(LY.records_of(inputs({"work/{}/x.md": [W1], "work/{}": [W2], "work/{}/sub/y": [W2], "state/s": [W1],
                                      "local/l": [W1]}, {"work/{}/x.md": [R1], "work/{}/sub/y": [R2]})))
    assert got["work/{}"].fact["writers"] == [{"module": "m.a", "symbol": "write_one"},
                                              {"module": "m.b", "symbol": "write_two"}]
    assert got["work/{}"].fact["readers"] == [{"module": "m.c", "symbol": "read_one"}]
    assert got["work/{}/sub"].fact["writers"] == [{"module": "m.b", "symbol": "write_two"}]
    assert got["work/{}/sub"].fact["readers"] == [{"module": "m.d", "symbol": "read_two"}]
    assert got["work"].fact["writers"] == [{"module": "m.b", "symbol": "write_two"}], "`work/{}` is directly in `work`"
    assert got["work"].fact["readers"] == []


def test_a_list_fact_is_sorted_and_names_a_function_once():
    """One path per list, so the order in which the paths are visited cannot hide a missing sort."""
    got = by_key(LY.records_of(inputs({"work/a": [W2, W1, W2], "state/s": [W1], "local/l": [W1]},
                                      {"work/a": [R2, R1, R2]})))
    assert got["work"].fact["writers"] == [{"module": "m.a", "symbol": "write_one"},
                                           {"module": "m.b", "symbol": "write_two"}]
    assert got["work"].fact["readers"] == [{"module": "m.c", "symbol": "read_one"},
                                           {"module": "m.d", "symbol": "read_two"}]


def test_the_anchor_is_the_constant_then_a_writer_then_a_reader_then_one_below():
    got = by_key(LY.records_of(inputs(
        writers={"work/x": [W2, W1], "state/a/b": [W2], "local/l": [W2, W1]},
        reads={"work/x": [R1], "state/s": [R2, R1]},
        named={"work": [("m.layout", "WORK_DIR")], "state/a": [("m.layout", "A_DIR")]})))
    assert anchor(got["work"]) == ("m.layout", "WORK_DIR"), "the constant that spells it wins"
    assert anchor(got["state"]) == R1, "no constant, no direct writer: the first direct reader, by sorted order"
    assert anchor(got["local"]) == W1, "no constant: the first writer, by sorted order"
    assert anchor(got["state/a"]) == ("m.layout", "A_DIR")
    got = by_key(LY.records_of(inputs(writers={"work/p/q/r": [W2], "state/s": [W1], "local/l": [W1]})))
    assert anchor(got["work"]) == W2, "nothing direct: a function that writes or reads below it"


@pytest.mark.parametrize(("entry", "ignored"), [("local", True), ("local/a", True), ("state", False),
                                                ("state/txn", True), ("state/txn/x", True), ("state/txnx", False),
                                                ("work", False)])
def test_an_entry_is_git_ignored_when_it_is_or_lies_under_a_path_the_gitignore_names(entry, ignored):
    writers = {f"{entry}/leaf": [W1], "state/s": [W1], "local/l": [W1], "work/w": [W1]}
    assert by_key(LY.records_of(inputs(writers)))[entry].fact["git_ignored"] is ignored


@pytest.mark.parametrize("line", ["*.log", "/local", "!keep", "loc?l", "dir/[ab]"])
def test_a_gitignore_line_that_is_not_a_plain_path_is_refused_and_not_guessed(line):
    with pytest.raises(C.ReferenceError, match="does not understand"):
        LY.ignored_prefixes(f"local/\n{line}\n")


def test_comments_and_blank_lines_of_a_gitignore_name_nothing():
    assert LY.ignored_prefixes("# a comment\n\nlocal/\n  state/txn/  \n") == ["local", "state/txn"]


def test_the_store_is_the_store_directory_and_what_is_under_it_and_not_a_name_that_starts_with_it():
    got = by_key(LY.records_of(inputs({"state/log/x": [W1], "statement/x": [W1], "local/l": [W1], "work/w": [W1]},
                                      store="state", top=("local", "state", "statement", "work"))))
    assert [k for k, r in got.items() if r.fact["store"]] == ["state", "state/log"]


def test_an_entry_is_masked_when_it_is_or_lies_under_an_entry_the_containment_layout_masks():
    got = by_key(LY.records_of(inputs({"local/a/b": [W1], "state/s": [W1], "work/w": [W1]}, hidden=("local",))))
    assert [k for k, r in got.items() if r.fact["masked_by_containment"]] == ["local", "local/a"]


def test_the_pointer_to_the_unresolved_writes_names_the_writers_family_and_the_key_it_gives_them():
    """Review of #261, N-2: the layout family points at records that are the writers family's, so a reader looking
    for `layout:unresolved:*` is told where they are."""
    record = by_key(LY.records_of(inputs({"work/w": [W1], "state/s": [W1], "local/l": [W1]})))["work"]
    [pointer] = [i for i in record.coverage["unresolved"] if "write sites" in i["why"]]
    assert "records of the writers family keyed `writers:unresolved:<module>:<symbol>:<primitive>`" in pointer["why"]


def test_the_page_and_the_docstring_do_not_gloss_what_git_keeps_and_state_the_rule_for_named_by():
    """Review of #261, N-6 (the gloss restated `AEW_GITIGNORE`'s comment) and N-12 (the list is a lower bound with
    nothing listed unresolved, so the rule for what it finds is stated where a reader looks)."""
    page = LY.page(LY.records_of(inputs({"work/w": [W1], "state/s": [W1], "local/l": [W1]})), NO_READS)
    doc = " ".join((LY.__doc__ or "").split())
    for text in (page, doc):
        assert "spent redo records" not in text and "runtime data" not in text
    assert "a constant spelled another way, or holding the same text for another purpose, is not found" in page
    assert "A constant spelled another way, or one that holds the same text for another purpose, is not found" in doc


def test_the_mask_fact_says_it_is_a_mask_and_the_page_and_the_docstring_state_the_bind_back():
    """Review of the layout pull request, N-1: the field is read by the trace and not the page, so its name says what it
    holds, and the limit (a run's own directories are bound back into the mask) is stated where the fact is defined."""
    got = by_key(LY.records_of(inputs({"local/a/b": [W1], "state/s": [W1], "work/w": [W1]}, hidden=("local",))))
    assert "hidden_from_contained" not in got["local"].fact and "masked_by_containment" in got["local"].fact
    page = LY.page(list(got.values()), NO_READS)
    assert "bound back into the mask" in page and "that run sees them" in page
    assert " ".join((LY.__doc__ or "").split()).count("back into the mask") == 1


def test_each_record_is_a_lower_bound_that_points_at_the_unresolved_writes_and_the_unplaced_reads():
    [rec] = [r for r in LY.records_of(inputs({"work/w": [W1], "state/s": [W1], "local/l": [W1]})) if r.key == "work"]
    assert rec.coverage["label"] == C.LOWER and set(rec.fact_coverage) == set(LY.LISTS)
    assert W_POINTER in rec.coverage["unresolved"] and LY.reads_pointer() in rec.coverage["unresolved"]
    assert rec.fact_coverage["writers"]["unresolved"] == [W_POINTER]
    assert rec.fact_coverage["readers"]["unresolved"] == [LY.reads_pointer()]
    assert rec.fact_coverage["named_by"]["unresolved"] == []


W_POINTER = LY.W.pointer_item()


def records_json(**kw: Any) -> dict[str, Any]:
    base = {"work/w": [W1], "state/s": [W1], "local/l": [W1]}
    return {r.id: r.as_json() for r in LY.records_of(inputs(kw.pop("writers", base), **kw))}


def test_the_records_of_a_sound_input_break_none_of_their_own_rules():
    assert LY.problems(records_json()) == []


@pytest.mark.parametrize(("what", "mutate", "message"), [
    ("the key is not the prefix", lambda rs: rs["layout:work"]["fact"].update(prefix="other"), "prefix is not the key"),
    ("an extra fact", lambda rs: rs["layout:work"]["fact"].update(kind="directory"), "the fact is not"),
    ("a flag that is not a boolean", lambda rs: rs["layout:work"]["fact"].update(store="yes"),
     "store is not a boolean"),
    ("a list fact without coverage", lambda rs: rs["layout:work"]["fact_coverage"].pop("readers"),
     "no fact_coverage for readers"),
    ("an unsorted list", lambda rs: rs["layout:work"]["fact"].update(
        writers=[{"module": "z", "symbol": "a"}, {"module": "a", "symbol": "a"}]), "writers is not sorted"),
    ("a record that does not point at the unplaced reads",
     lambda rs: rs["layout:work"]["coverage"].update(unresolved=[]), "does not point at the unresolved writes"),
])
def test_the_family_refuses_a_record_that_breaks_its_own_rules(what, mutate, message):
    records = copy.deepcopy(records_json())
    mutate(records)
    assert any(message in p for p in LY.problems(records)), what


@pytest.mark.parametrize("flag", LY.FLAGS)
def test_a_flag_that_holds_for_an_entry_must_hold_for_what_is_under_it(flag):
    """Each flag of `FLAGS` (review of the layout pull request, N-10): all three hold for `local` here."""
    records = copy.deepcopy(records_json(writers={"local/a/b": [W1], "state/s": [W1], "work/w": [W1]}, store="local"))
    assert LY.problems(records) == [] and records["layout:local"]["fact"][flag]
    records["layout:local/a"]["fact"][flag] = False
    [problem] = LY.problems(records)
    assert f"{flag} holds for 'local' and not for what is under it" in problem


@pytest.mark.parametrize("flag", LY.FLAGS)
def test_a_flag_that_is_not_a_boolean_is_refused(flag):
    records = copy.deepcopy(records_json())
    records["layout:work"]["fact"][flag] = "yes"
    assert any(f"{flag} is not a boolean" in p for p in LY.problems(records))


def test_an_entry_whose_name_starts_like_another_is_not_directly_that_one():
    """Review of the layout pull request, N-13 (C6): `work2` is not in `work`."""
    got = by_key(LY.records_of(inputs({"work2/x": [W1], "work/y": [W2], "state/s": [W1], "local/l": [W1]},
                                      top=("local", "state", "work", "work2"))))
    assert got["work"].fact["writers"] == [{"module": "m.b", "symbol": "write_two"}]
    assert got["work2"].fact["writers"] == [{"module": "m.a", "symbol": "write_one"}]


def test_another_familys_records_are_not_this_familys_to_check():
    records = copy.deepcopy(records_json())
    records["writers:work/w"] = {"family": "writers", "fact": {"nothing": "in common"}}
    assert LY.problems(records) == []


# ----------------------------------------------------------------------------------------- the owners it reads

HIDE = ("from pathlib import Path\n\n"
        "def for_run(repo_root, runs=None):\n"
        "    local = Path(repo_root) / '.aew' / 'local'\n"
        "    hide_runs = [local]\n"
        "    if runs is not None:\n"
        "        hide_runs.append(runs)\n"
        "    return Layout(hide_runs=tuple(hide_runs))\n")


def hidden(layout_source: str, extra: dict[str, str] | None = None) -> set[str]:
    prog = program({LY.CONTAINMENT[0]: layout_source, **(extra or {})})
    return LY.hidden_dirs(prog, F.Evaluator(prog), TOP)


def test_the_hidden_entries_are_the_paths_under_aew_the_hide_runs_list_is_built_from():
    assert hidden(HIDE) == {"local"}


def test_a_masked_path_under_a_first_entry_nobody_declared_is_no_entry():
    """Review of the layout pull request, N-13 (C7)."""
    source = ("def for_run(repo_root):\n    local = Path(repo_root) / '.aew' / 'local'\n"
              "    odd = Path(repo_root) / '.aew' / 'brand-new'\n    return Layout(hide_runs=(local, odd))\n")
    assert hidden(source) == {"local"}


def test_a_path_a_caller_passes_into_the_hide_runs_list_is_hidden_too():
    caller = ("from aew.harness.containment.layout import for_run\n\n"
              "def g(aew_root, repo_root):\n    for_run(repo_root, aew_root / 'local' / 'validation')\n")
    assert hidden(HIDE, {"aew.caller": caller}) == {"local", "local/validation"}


def test_a_hidden_path_outside_aew_is_no_entry_and_a_layout_that_hides_none_under_aew_is_refused():
    source = ("def for_run(repo_root):\n    out = Path('/somewhere/else')\n"
              "    local = Path(repo_root) / '.aew' / 'local'\n    return Layout(hide_runs=(out, local))\n")
    assert hidden(source) == {"local"}
    with pytest.raises(C.ReferenceError, match="no path this reading can place under `.aew`"):
        hidden("def for_run(repo_root):\n    out = Path('/somewhere/else')\n    return Layout(hide_runs=(out,))\n")


def test_a_layout_with_no_hide_runs_keyword_is_refused_not_read_as_hiding_nothing():
    with pytest.raises(C.ReferenceError, match="no longer builds a layout with a `hide_runs` keyword"):
        hidden("def for_run(project):\n    return Layout(hide_dirs=())\n")


# ----------------------------------------------------------------------------------------------------------- the page

NO_READS = L.Placed({}, [], 0, 0, 0, 0)


def test_the_page_names_every_class_of_what_it_cannot_see_and_the_primitives_it_reads():
    page = LY.page(LY.records_of(inputs({"work/w": [W1], "state/s": [W1], "local/l": [W1]})), NO_READS)
    assert all(text in page for _, text in L.CANNOT_SEE)
    assert all(f"`{label}`" in page for label in L.read_labels())


def test_the_page_lists_each_entry_under_its_top_level_with_what_holds_of_it_and_the_unplaced_reads_by_module():
    records = LY.records_of(inputs({"local/a/b": [W1], "state/log/x": [R1], "work/w": [W1]}, {"local/a/b": [R2]}))
    reads = L.Placed({}, [("m.z", "reader", "Path.read_text"), ("m.z", "other", "open")], 6, 2, 1, 3)
    page = LY.page(records, reads)
    assert "## `local`\n" in page and "## `state`\n" in page and "## `work`\n" in page
    assert "- `local/a` (git-ignored, masked by containment)" in page
    assert "- `state/log` (store)" in page and "- `work` (kept in git)" in page
    assert "read by `m.d`: `read_two`" in page
    assert "- `m.z`: `reader` (Path.read_text), `other` (open)" in page
    assert ("Read sites found: 6; placed under `.aew`: 2; provably outside it or the directory itself: 1; "
            "not placed: 3.") in page


def test_a_page_with_every_read_placed_says_so():
    page = LY.page(LY.records_of(inputs({"work/w": [W1], "state/s": [W1], "local/l": [W1]})), NO_READS)
    assert "not placed: 0" in page and "\nNone.\n" in page
