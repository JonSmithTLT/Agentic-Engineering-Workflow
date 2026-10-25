"""The concurrency family of the generated reference (STG-12 S12-2, DOC-03), on planted sources and owners.

``tools/reference_families/concurrency.py`` finds the ``FileLock`` constructions of the program, who takes each lock,
and the functions that work without the control lock; ``concurrency_text.py`` is the second detector of the
constructions and the opener calls. Every rule has its planted right case, wrong case and missing case; the tree-wide
guarantees (the two detectors agree on every module, the control lock's opener and takers are what the store and a
non-writer's refusal say, every lock-free member takes no lock while the control lock is held) are in
``tests/integration/test_reference_concurrency.py``.
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
        from reference_families import common, concurrency, concurrency_text, writers, writers_flow
    finally:
        sys.path.remove(here)
    return common, concurrency, concurrency_text, writers, writers_flow


C, CO, CT, W, F = _tools()
HEAD = "from aew import process_kind\nfrom aew.engine.lock import FileLock\n"
KINDS = {"aew": "store_writer", "aew dashboard serve": "non_writer", "aew.harness.supervisor": "store_writer"}


def program(sources: dict[str, str]) -> Any:
    return F.Program.of({name: (ast.parse(text), False) for name, text in sources.items()})


def sites_of(source: str, extra: dict[str, str] | None = None, head: str = HEAD) -> tuple[list[Any], Any]:
    prog = program({"aew.m": head + source, **(extra or {})})
    return CO.lock_sites(prog, F.Evaluator(prog)), prog


# A store-like class: the opener returns the lock after the gate, its callers hold it.
STORE = (
    "class S:\n"
    "    def lock(self, op, aew_root):\n"
    "        process_kind.require_writer(op)\n"
    "        return FileLock(aew_root / 'local' / 'a.lock', timeout=self.wait)\n\n"
    "    def go(self, aew_root):\n"
    "        with self.lock('S.go', aew_root):\n"
    "            pass\n\n"
    "    def other(self, aew_root, name):\n"
    "        with self.lock(name, aew_root):\n"
    "            pass\n")


# ------------------------------------------------------------------------------------------- the lock constructions

def test_a_lock_is_a_filelock_construction_found_by_import_source_with_its_path():
    sites, _ = sites_of("def f(aew_root):\n    return FileLock(aew_root / 'local' / 'a.lock')\n")
    assert [(s.module, s.symbol, s.path, s.timeout) for s in sites] == [("aew.m", "f", "local/a.lock", None)]


def test_a_class_of_that_name_that_is_not_the_locks_is_no_lock():
    sites, _ = sites_of("class FileLock:\n    pass\n\ndef f(aew_root):\n    FileLock(aew_root / 'local' / 'a.lock')\n",
                        head="")
    assert sites == []


def test_a_construction_under_another_import_name_is_found_by_import_source():
    sites, _ = sites_of("def f(aew_root):\n    return FL(aew_root / 'local' / 'a.lock')\n",
                        head="from aew.engine.lock import FileLock as FL\n")
    assert [s.symbol for s in sites] == ["f"]


def test_a_path_this_reading_cannot_place_is_marked_with_why_and_not_guessed():
    sites, _ = sites_of("def f(path):\n    return FileLock(path)\n")
    [site] = sites
    assert site.path is None and "no static call binds" in (site.why or "")


@pytest.mark.parametrize(("call", "timeout"), [
    ("FileLock(p, timeout=WAIT)", "WAIT"), ("FileLock(p, 5.0)", "5.0"), ("FileLock(p, timeout=self.wait)", "self.wait"),
    ("FileLock(p)", None)])
def test_the_timeout_is_the_source_of_the_keyword_or_the_second_argument_else_none(call, timeout):
    sites, _ = sites_of(f"def f(aew_root):\n    p = aew_root / 'local' / 'a.lock'\n    return {call}\n")
    assert [s.timeout for s in sites] == [timeout]


@pytest.mark.parametrize(("body", "gated"), [
    ("process_kind.require_writer(op)\n    return FileLock(aew_root / 'local' / 'a.lock')", True),
    ("return FileLock(aew_root / 'local' / 'a.lock')", False),
    ("lock = FileLock(aew_root / 'local' / 'a.lock')\n    process_kind.require_writer(op)\n    return lock", False),
])
def test_an_opener_is_gated_when_it_calls_require_writer_before_it_constructs_the_lock(body, gated):
    sites, _ = sites_of(f"def f(op, aew_root):\n    {body}\n")
    assert [s.gated for s in sites] == [gated]


@pytest.mark.parametrize(("body", "returned"), [
    ("return FileLock(aew_root / 'local' / 'a.lock')", True),
    ("lock = FileLock(aew_root / 'local' / 'a.lock')\n    return lock", True),
    ("with FileLock(aew_root / 'local' / 'a.lock'):\n        pass", False),
    ("lock = FileLock(aew_root / 'local' / 'a.lock')\n    return aew_root", False),
])
def test_a_construction_is_returned_when_it_is_the_value_or_the_name_that_holds_only_it(body, returned):
    sites, _ = sites_of(f"def f(aew_root):\n    {body}\n")
    assert [s.returned for s in sites] == [returned]


# ----------------------------------------------------------------------------------------------------------- takers

def test_the_takers_of_a_returned_lock_are_the_opener_s_callers_with_the_operation_they_pass():
    sites, prog = sites_of(STORE, {"aew.n": "from aew.m import S\n\ndef g(s: S, aew_root):\n"
                                            "    with s.lock('g op', aew_root):\n        pass\n"})
    got = [(t.module, t.symbol, t.operation) for t in CO.takers_of(prog, sites)]
    assert got == [("aew.m", "S.go", "S.go"), ("aew.m", "S.other", None), ("aew.n", "g", "g op")]


def test_the_taker_of_a_lock_nothing_returns_is_the_function_that_constructs_it():
    sites, prog = sites_of("def f(aew_root):\n    with FileLock(aew_root / 'local' / 'b.lock'):\n        pass\n")
    assert [(t.module, t.symbol, t.operation) for t in CO.takers_of(prog, sites)] == [("aew.m", "f", None)]


# ---------------------------------------------------------------------------------------------------------- records

def inputs(source: str = STORE, *, control: str = "local/a.lock", reach: dict | None = None, members=(),
           extra: dict[str, str] | None = None, classes: dict | None = None) -> Any:
    sites, prog = sites_of(source, extra)
    return CO.Inputs(sites, CO.takers_of(prog, sites), control, list(members), reach or {}, KINDS, classes or {})


def lock_record(inp: Any, path: str = "local/a.lock") -> Any:
    return {r.key: r for r in CO.records_of(inp)}[f"lock:{path}"]


def test_the_control_lock_is_complete_by_construction_with_its_one_opener_and_the_others_are_lower_bounds():
    control = lock_record(inputs())
    assert control.coverage["label"] == C.COMPLETE and list(control.coverage["check"]) == sorted(CO.CONTROL_CHECKS)
    assert control.fact["control"] and control.fact["openers"] == [{"module": "aew.m", "symbol": "S.lock"}]
    other = lock_record(inputs(control="state/elsewhere.lock"))
    assert other.coverage["label"] == C.LOWER and not other.fact["control"]
    assert other.coverage["unresolved"], "what the reading does not see is listed"


def test_a_control_lock_opened_in_two_places_is_refused_not_labelled_complete():
    two = STORE + "\ndef second(aew_root):\n    return FileLock(aew_root / 'local' / 'a.lock')\n"
    with pytest.raises(C.ReferenceError, match="opened in 2 places"):
        CO.records_of(inputs(two))


def test_a_lock_the_reading_could_not_place_is_a_record_keyed_by_its_opener_with_why():
    inp = inputs("def f(path):\n    return FileLock(path)\n")
    [record] = [r for r in CO.records_of(inp) if r.key.startswith("lock:")]
    assert record.key == "lock:unplaced:aew.m:f" and "no static call binds" in record.fact["unplaced_why"]


def test_a_lock_is_refused_in_a_non_writer_only_when_every_opener_of_it_is_gated():
    two = ("def a(op, aew_root):\n    process_kind.require_writer(op)\n"
           "    return FileLock(aew_root / 'local' / 'b.lock')\n\n"
           "def b(aew_root):\n    return FileLock(aew_root / 'local' / 'b.lock')\n")
    inp = inputs(two, control="local/a.lock")
    assert lock_record(inp, "local/b.lock").fact["refused_in_non_writer"] is False
    assert [s.gated for s in inp.sites] == [True, False]


def test_the_takers_carry_the_entry_points_that_reach_them_and_their_kinds_and_the_gate():
    reach = {("aew.m", "S.go"): {"aew"}, ("aew.m", "S.other"): {"aew", "aew dashboard serve"}}
    fact = lock_record(inputs(reach=reach)).fact
    assert fact["refused_in_non_writer"] is True and fact["timeout"] == "self.wait"
    by_symbol = {t["symbol"]: t for t in fact["takers"]}
    assert by_symbol["S.go"]["entry_points"] == ["aew"] and by_symbol["S.go"]["entry_kinds"] == ["store_writer"]
    assert by_symbol["S.other"]["entry_kinds"] == ["non_writer", "store_writer"]


def test_a_taker_no_entry_point_reaches_says_so_in_the_takers_coverage():
    record = lock_record(inputs(reach={("aew.m", "S.go"): {"aew"}}))
    unreached = [i for i in record.fact_coverage["takers"]["unresolved"] if i["why"] == W.NO_CHAIN]
    assert [i["symbol"] for i in unreached] == ["S.other"]


def test_a_closure_that_takes_the_lock_is_attributed_what_reaches_the_function_that_defines_it():
    source = STORE + ("\ndef run(s: S, aew_root):\n    def inner():\n        return s.lock('run op', aew_root)\n"
                      "    return inner\n")
    fact = lock_record(inputs(source, reach={("aew.m", "run"): {"aew"}})).fact
    [inner] = [t for t in fact["takers"] if t["symbol"] == "run.inner"]
    assert inner["entry_points"] == ["aew"] and inner["operation"] == "run op"


# -------------------------------------------------------------------------------- the members that need no control lock

PK_DOC = ("A non-writer reads only lock-free: ``S.peek``, ``util.snap`` and ``S``. These take no lock and run no "
          "recovery, so they work on a read-only store.")


def test_the_names_process_kind_gives_its_non_writers_are_read_from_its_docstring():
    assert CO.process_kind_names(PK_DOC) == ["S.peek", "util.snap", "S"]


@pytest.mark.parametrize("doc", ["no marker here, ``S.peek``.", "reads only lock-free: ``S.peek`` and never an end",
                                 "reads only lock-free: nothing in backticks. These take no lock"])
def test_a_docstring_that_no_longer_names_the_lock_free_readers_is_refused_not_read_as_none(doc):
    with pytest.raises(C.ReferenceError):
        CO.process_kind_names(doc)


MODULE_DOC = ('"""Module: the snapshot readers work without the control lock, whoever else holds it.\n\n'
              'Another paragraph that says nothing of locks."""\n')
MEMBERS = ("class S:\n"
           '    """A reader. It takes no lock and never repairs."""\n\n'
           "    def peek(self):\n"
           '        """A committed view, without the control lock."""\n'
           "        return self._load()\n\n"
           "    def _load(self):\n        return 1\n\n"
           "    def mutate(self, aew_root):\n"
           "        with FileLock(aew_root / 'local' / 'a.lock'):\n            pass\n")
UTIL = "from aew.m import S\n\ndef snap():\n    return 1\n\ndef sink(s: S, aew_root):\n    s.mutate(aew_root)\n"


def members(monkeypatch, declared=(), doc: str = PK_DOC, utils: str = UTIL) -> list[Any]:
    monkeypatch.setattr(CO, "DECLARED", tuple(declared))
    prog = program({"aew.m": MODULE_DOC + HEAD + MEMBERS, "aew.util": utils})
    sites = CO.lock_sites(prog, F.Evaluator(prog))
    taking = {(s.module, s.symbol) for s in sites}
    return CO.members_of(prog, doc, taking)


def test_a_named_member_is_resolved_to_its_class_or_module_and_carries_its_own_docstring(monkeypatch):
    got = {m.symbol: m for m in members(monkeypatch)}
    assert sorted(got) == ["S", "S.peek", "snap"]
    assert got["S.peek"].module == "aew.m" and got["snap"].module == "aew.util"
    assert got["S.peek"].observes == "A committed view, without the control lock."
    assert got["S.peek"].source == "process_kind" and got["S.peek"].says_in == "symbol"


def test_a_class_name_two_modules_both_define_is_refused_and_not_resolved_to_the_first():
    prog = program({"aew.a": "class S:\n    def peek(self):\n        return 1\n",
                    "aew.b": "class S:\n    def peek(self):\n        return 2\n"})
    with pytest.raises(C.ReferenceError, match=r"`S\.peek`"):
        CO.resolve_name(prog, "S.peek")


def test_a_name_that_is_no_class_and_no_module_is_refused_not_guessed(monkeypatch):
    with pytest.raises(C.ReferenceError, match="names `nothing.here`"):
        members(monkeypatch, doc="reads only lock-free: ``nothing.here``. These take no lock")


def test_a_class_member_is_checked_over_all_its_methods_and_a_function_over_its_own_closure(monkeypatch):
    got = {m.symbol: m for m in members(monkeypatch)}
    assert got["S.peek"].takes_no_lock and got["snap"].takes_no_lock
    assert not got["S"].takes_no_lock, "the class has a method that locks"
    assert got["S"].lock_takers == [("aew.m", "S.mutate")]


def test_a_member_whose_closure_reaches_a_function_that_takes_a_lock_is_not_lock_free(monkeypatch):
    got = {m.symbol: m for m in members(monkeypatch, declared=[("aew.util", "sink", "a sink", ())])}
    assert not got["sink"].takes_no_lock and got["sink"].lock_takers == [("aew.m", "S.mutate")]


def test_the_module_docstring_is_where_a_declared_member_says_it_only_when_the_declaration_names_its_work(monkeypatch):
    declared = [("aew.m", "S._load", "a loader inside the module", ("snapshot",)),
                ("aew.util", "snap", "a snapshot", ())]
    got = {m.symbol: m for m in members(monkeypatch, declared=declared)}
    assert got["S._load"].says_in == "module" and len(got["S._load"].says) == 1
    assert "without the control lock" in got["S._load"].says[0]
    assert got["snap"].says == [] and got["snap"].says_in is None, "a member's silence is not the module's statement"


def test_a_sentence_of_the_module_docstring_is_quoted_for_a_member_only_if_it_names_that_members_work(monkeypatch):
    """Review of #267, C-4: the compactor's module says its readers are lockless, which is not its build's statement."""
    declared = [("aew.m", "S._load", "a loader", ("snapshot",)), ("aew.m", "S.mutate", "a mutator", ("compaction",))]
    got = {m.symbol: m for m in members(monkeypatch, declared=declared)}
    assert got["S._load"].says and got["S.mutate"].says == [] and got["S.mutate"].says_in is None


def test_a_declared_member_that_is_no_function_or_class_of_the_module_is_refused(monkeypatch):
    with pytest.raises(C.ReferenceError, match="neither a function nor a class"):
        members(monkeypatch, declared=[("aew.m", "nothing", "x", False)])


def member_records(monkeypatch) -> list[Any]:
    found = members(monkeypatch)
    inp = CO.Inputs([], [], "local/a.lock", found, {("aew.m", "S.peek"): {"aew dashboard serve"}}, KINDS,
                    {("aew.m", "S"): [("aew.m", "S.peek"), ("aew.m", "S.mutate")]})
    return CO.records_of(inp)


def test_a_member_record_carries_its_facts_its_entry_points_and_kinds_and_is_a_lower_bound(monkeypatch):
    got = {r.key: r for r in member_records(monkeypatch)}
    peek = got["lock-free:aew.m:S.peek"]
    assert peek.coverage["label"] == C.LOWER and peek.fact["entry_points"] == ["aew dashboard serve"]
    assert peek.fact["entry_kinds"] == ["non_writer"] and peek.fact["takes_no_lock"] is True
    assert set(peek.fact_coverage) == {"says", "lock_takers", "entry_points", "entry_kinds"}
    assert any(i["why"] == W.NO_CHAIN for i in peek.fact_coverage["entry_points"]["unresolved"]) is False
    snap = got["lock-free:aew.util:snap"]
    assert snap.fact["entry_points"] == [] and any(i["why"] == W.NO_CHAIN
                                                   for i in snap.fact_coverage["entry_points"]["unresolved"])


# ------------------------------------------------------------------------------ the typing cap, from a lock-free member

TYPED_DOC = "A non-writer reads only lock-free: ``M.run``. These take no lock and run no recovery."


def lock_through_attributes(hops: int) -> str:
    """`self.a1.a2...aN.take(root)` where `take` returns a lock: a lock-free member that reaches the opener."""
    src = HEAD + "class T:\n    def take(self, root):\n        process_kind.require_writer('x')\n"
    src += "        return FileLock(root / 'local' / 't.lock')\n\n"
    for k in range(hops - 1, 0, -1):
        held = "T()" if k + 1 == hops else f"A{k + 1}()"
        src += f"class A{k}:\n    def __init__(self):\n        self.a{k + 1} = {held}\n\n"
    path = "self.a1" + "".join(f".a{k}" for k in range(2, hops + 1))
    first = "T()" if hops == 1 else "A1()"
    run = f"    def run(self, root):\n        {path}.take(root)\n"
    return src + f"class M:\n    def __init__(self):\n        self.a1 = {first}\n" + run


def test_a_member_that_reaches_a_lock_through_more_attributes_than_the_typing_cap_fails_the_reading(monkeypatch):
    """Review of #267, addendum 7 for `TYPING_DEPTH`: the dropped edge read as `takes_no_lock=True`, with no mark."""
    monkeypatch.setattr(F, "TYPING_DEPTH", 3)
    monkeypatch.setattr(CO, "DECLARED", ())
    prog = program({"aew.m": lock_through_attributes(3)})
    sites = CO.lock_sites(prog, F.Evaluator(prog))
    [member] = CO.members_of(prog, TYPED_DOC, {(s.module, s.symbol) for s in sites})
    assert not member.takes_no_lock and member.lock_takers == [("aew.m", "T.take")], "at the cap the edge is followed"
    with pytest.raises(C.ReferenceError) as refused:
        program({"aew.m": lock_through_attributes(4)})
    assert "(cap `writers_flow.TYPING_DEPTH` = 3:" in str(refused.value)


# ----------------------------------------------------------- what a docstring is quoted for, without its citations

@pytest.mark.parametrize(("sentence", "kept"), [
    ("A reader's view (ADR-0012 D3 and invariant 4; the dashboard, register F20.2).", "A reader's view."),
    ("One lockless view of the log (D3): each revision resolves from its record.",
     "One lockless view of the log: each revision resolves from its record."),
    ("It reads ``read_committed`` (a stat and a read).", "It reads ``read_committed`` (a stat and a read)."),
    ("Never fsynced, within ADR-0012's H2 budget.", None),
    ("The stage STG-05 CB-09 decided this.", None),
    ("It keeps no lock.", "It keeps no lock."),
])
def test_a_citation_is_elided_from_a_parenthetical_and_a_bare_one_drops_the_sentence(sentence, kept):
    assert CO.plain(sentence) == kept


def test_a_sentence_that_introduces_a_list_is_cut_at_its_last_comma_and_one_with_no_comma_is_left_out():
    """Review of #267, C-4: a quote must not end on a dangling clause ("... and that is safe:")."""
    listing = "Build runs without the lock, so a commit never waits (a segment costs seconds), and that is safe:"
    assert CO.plain(listing) == "Build runs without the lock, so a commit never waits (a segment costs seconds)."
    assert CO.plain("These hold:") is None
    assert CO.says_of("Build runs without the lock, and that is safe:") == ["Build runs without the lock."]


def test_a_docstring_is_split_into_sentences_across_lines_and_paragraphs():
    doc = "First line of one\nsentence. Second one has ``a.b`` in it.\n\nThird, in another paragraph!  Fourth?"
    assert CO.sentences(doc) == ["First line of one sentence.", "Second one has ``a.b`` in it.",
                                 "Third, in another paragraph!", "Fourth?"]
    assert CO.sentences(None) == [] and CO.sentences("") == []


def test_what_a_symbol_observes_is_its_first_sentence_that_names_no_bare_citation():
    assert CO.observes_of("Within ADR-0012's H2 budget. A committed view (D3), read without the lock. More.") == (
        "A committed view, read without the lock.")
    assert CO.observes_of(None) == "" and CO.observes_of("Only H2 here.") == ""


def test_what_a_docstring_says_of_the_lock_is_the_sentences_that_state_it_and_not_the_others():
    doc = ("Reads the file. It takes no lock (D3) and never repairs. Writers use the lock. "
           "Lockless readers stay correct.")
    assert CO.says_of(doc) == ["It takes no lock and never repairs.", "Lockless readers stay correct."]
    assert CO.says_of("It needs the lock, per H2.") == [] and CO.says_of(None) == []


# ----------------------------------------------------------------------------------------- the family's own rules

def records_json(monkeypatch) -> dict[str, Any]:
    inp = inputs(STORE, reach={("aew.m", "S.go"): {"aew"}})
    found = members(monkeypatch)
    inp = CO.Inputs(inp.sites, inp.takers, inp.control_path, found, inp.reach, KINDS, {})
    return {r.id: r.as_json() for r in CO.records_of(inp)}


def test_the_records_of_a_sound_input_break_none_of_their_own_rules(monkeypatch):
    assert CO.problems(records_json(monkeypatch), KINDS) == []


LOCK_ID, FREE_ID = "concurrency:lock:local/a.lock", "concurrency:lock-free:aew.m:S.peek"
FAULTS = [
    ("a lock without its takers", LOCK_ID, ["fact", "takers"], Ellipsis, "a lock's fact is"),
    ("a lock whose key is not its path", LOCK_ID, ["fact", "lock"], "local/b.lock", "the lock is not the key"),
    ("a control lock that is a lower bound", LOCK_ID, ["coverage", "label"], "lower-bound", "complete-by-construction"),
    ("a control lock with two openers", LOCK_ID, ["fact", "openers"],
     [{"module": "a", "symbol": "b"}, {"module": "c", "symbol": "d"}], "complete-by-construction with one opener"),
    ("a lock with no opener", LOCK_ID, ["fact", "openers"], [], "a lock has an opener"),
    ("a taker with no operation field", LOCK_ID, ["fact", "takers", 0, "operation"], Ellipsis, "a taker is a module"),
    ("a taker reached from an entry point that is no row", LOCK_ID, ["fact", "takers", 0, "entry_points"], ["aew.nope"],
     "is no row of the table"),
    ("takers without their coverage", LOCK_ID, ["fact_coverage", "takers"], Ellipsis, "no fact_coverage for takers"),
    ("a member that takes no lock and lists one", FREE_ID, ["fact", "lock_takers"], [{"module": "a", "symbol": "b"}],
     "takes_no_lock and lock_takers disagree"),
    ("a member with paragraphs and no place they are in", FREE_ID, ["fact", "says_in"], None, "says_in names where"),
    ("a member with a place and no paragraphs", FREE_ID, ["fact", "says"], [], "says_in names where"),
    ("a member that is complete-by-construction", FREE_ID, ["coverage", "label"], "complete-by-construction",
     "a lock-free member is a lower bound"),
    ("a member whose key is not its symbol", FREE_ID, ["fact", "symbol"], "peek", "the key is not the member"),
    ("a member with an extra fact", FREE_ID, ["fact", "extra"], 1, "a lock-free member's fact is"),
]


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


@pytest.mark.parametrize(("what", "rid", "path", "value", "fragment"), FAULTS, ids=[f[0] for f in FAULTS])
def test_each_planted_fault_in_a_record_is_refused_by_its_own_rule(monkeypatch, what, rid, path, value, fragment):
    good = records_json(monkeypatch)
    assert CO.problems(good, KINDS) == []
    bad = CO.problems(mutate(good, rid, path, value), KINDS)
    assert any(fragment in p for p in bad), (what, bad)


def test_a_tree_with_no_control_lock_record_is_refused_and_another_familys_records_are_not_checked(monkeypatch):
    good = records_json(monkeypatch)
    no_control = {k: v for k, v in good.items() if k != LOCK_ID}
    assert any("exactly one lock is the control lock" in p for p in CO.problems(no_control, KINDS))
    good["writers:state/x"] = {"family": "writers", "fact": {"nothing": "in common"}}
    assert CO.problems(good, KINDS) == []


# --------------------------------------------------------------------------------------------------- the page

def test_the_page_lists_each_lock_with_its_opener_and_takers_and_each_member_with_what_it_observes(monkeypatch):
    page = CO.page(member_records(monkeypatch) + CO.records_of(inputs(STORE, reach={("aew.m", "S.go"): {"aew"}})))
    assert "### `local/a.lock` (control lock)" in page and "opener `aew.m:S.lock`" in page
    assert "taker `aew.m:S.go` (`S.go`): reached from `aew`" in page
    assert "taker `aew.m:S.other`: reached from no static chain from any entry point" in page
    assert "### `aew.m:S.peek`" in page and "observes: A committed view, without the control lock." in page
    assert "## What the reading does not see" in page and all(text in page for _, text in CO.CANNOT_SEE)


# ------------------------------------------------------------------------- the two detectors and what neither sees

COUNTED = [
    # (source, the counts both detectors give for ('control_lock',))
    ("FileLock(p)", {"FileLock": 1}),
    ("with FileLock(p):\n    pass", {"FileLock": 1}),
    ("store.control_lock('op')", {"control_lock": 1}),
    ("self.control_lock('op')\nself.control_lock('op')", {"control_lock": 2}),
    ("control_lock('op')", {"control_lock": 1}),
    ("FileLock(a)\nFileLock(b)\nstore.control_lock('x')", {"FileLock": 2, "control_lock": 1}),
]
NOT_COUNTED = ["def control_lock():\n    pass", "class FileLock:\n    pass", "x = control_lock", "f(FileLock)",
               "'FileLock(p)'", "# FileLock(p)", "unrelated(p)"]


def counts(source: str) -> tuple[Counter[str], Counter[str]]:
    text = HEAD + source + "\n"
    prog = program({"aew.m": text})
    return CO.call_counts(prog, ["control_lock"])["aew.m"], CT.counts(text, ["control_lock"])


@pytest.mark.parametrize(("source", "expected"), COUNTED)
def test_the_two_detectors_find_the_same_lock_calls_with_the_same_names(source, expected):
    ast_found, text_found = counts("def f(p, store, a, b):\n    " + source.replace("\n", "\n    "))
    assert dict(ast_found) == expected and dict(text_found) == expected, source


def test_a_call_at_module_level_is_counted_by_both_detectors():
    """Review of #267, C-10: the module scope is held, not only a function's."""
    text = HEAD + "lock = FileLock(p)\nheld = store.control_lock('op')\n"
    found = CO.call_counts(program({"aew.m": text}), ["control_lock"])["aew.m"]
    assert dict(found) == {"FileLock": 1, "control_lock": 1}
    assert dict(CT.counts(text, ["control_lock"])) == {"FileLock": 1, "control_lock": 1}


@pytest.mark.parametrize("source", NOT_COUNTED)
def test_what_is_no_lock_call_is_found_by_neither_detector(source):
    ast_found, text_found = counts(source)
    assert (dict(ast_found), dict(text_found)) == ({}, {}), source


def test_a_construction_under_another_import_name_is_the_ast_readings_alone_and_pinned_as_such():
    """The asymmetry the two readers have by construction: tokens cannot follow an import alias. The agreement test over
    the tree holds the two to equal counts, so a tree that renamed the import would fail it until this is decided."""
    text = "from aew.engine.lock import FileLock as FL\n\ndef f(p):\n    return FL(p)\n"
    assert dict(CO.call_counts(program({"aew.m": text}), [])["aew.m"]) == {"FileLock": 1}
    assert dict(CT.counts(text, [])) == {}


PROBES = {
    "thread-lock": "lock = threading.Lock()\nwith lock:\n    pass\ncond = threading.Condition()\n"
                   "ev = threading.Event()",
    "exclusive-create": "fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)",
    "other-lock-class": "OtherLock(path)",
    "computed-callee": "getattr(store, 'control_lock')('op')",
    "lock-in-a-variable": "make = FileLock\nmake(path)",
}


def test_the_cannot_see_list_has_a_probe_for_each_class_and_nothing_else():
    assert set(PROBES) == {name for name, _ in CO.CANNOT_SEE}
    assert len({name for name, _ in CO.CANNOT_SEE}) == len(CO.CANNOT_SEE)


@pytest.mark.parametrize("name", sorted(PROBES))
def test_what_neither_detector_can_see_is_pinned_by_a_probe_each(name):
    ast_found, text_found = counts("import threading\nimport os\n\ndef f(path, store):\n    "
                                   + PROBES[name].replace("\n", "\n    "))
    assert (dict(ast_found), dict(text_found)) == ({}, {}), name


def test_the_token_detector_imports_nothing_of_the_package_but_the_write_sides_token_helpers():
    tree = ast.parse((ROOT / "tools" / "reference_families" / "concurrency_text.py").read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "ast" not in imported
    assert {i for i in imported if i.startswith("reference_families")} == {"reference_families.writers_text"}
