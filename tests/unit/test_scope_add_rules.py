"""Register E126: the scope add's pure rules, and the one accessor every reader of a Ticket's scope goes through."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aew.engine import scope_ops as SC
from aew.harness import contract as K
from aew.surface import contract
from aew.surface.validate import check_call

SRC = Path(SC.__file__).resolve().parents[1]

# The functions that read a unit's record (``read_record(..., "work-unit")``), and whether each hands its scope on.
# A scope reader applies the accessor; ``_hierarchy_context`` reads only an ancestor's acceptance.
RECORD_READERS = {("engine/evidence_ops.py", "record_meta"): True, ("engine/context_ops.py", "_pack_base"): True,
                  ("engine/context_ops.py", "_hierarchy_context"): False}


def _record_readers() -> dict[tuple[str, str], ast.FunctionDef]:
    found = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for call in ast.walk(fn):
                if (isinstance(call, ast.Call) and getattr(call.func, "id", getattr(call.func, "attr", None))
                        == "read_record" and any(isinstance(a, ast.Constant) and a.value == "work-unit"
                                                 for a in call.args)):
                    found[(path.relative_to(SRC).as_posix(), fn.name)] = fn
    return found


def test_every_reader_of_a_tickets_scope_reads_the_effective_scope_through_the_one_accessor():
    """Derive, don't restate (the designer's decisions of 2026-11-03, §2): a new function that reads a unit's record
    fails here until it is listed, and a listed scope reader that stops applying ``effective_meta`` fails too.

    What it cannot see: a reader that parses the record's text itself (``parse_frontmatter``), or takes ``work_show``'s
    raw ``record`` instead of its ``effective_scope``. Those are found by review (PR #540 review)."""
    readers = _record_readers()
    assert set(readers) == set(RECORD_READERS), sorted(set(readers) ^ set(RECORD_READERS))
    for key, scope_reader in RECORD_READERS.items():
        names = {n.attr if isinstance(n, ast.Attribute) else n.id for n in ast.walk(readers[key])
                 if isinstance(n, (ast.Attribute, ast.Name))}
        if scope_reader:
            assert "effective_meta" in names, key
        else:
            assert "scope" not in ast.unparse(readers[key]), key


def test_the_accessor_adds_the_recorded_paths_after_the_declared_ones_and_leaves_the_record_meta_alone():
    meta = {"scope": {"paths": ["calc/core.py"]}, "title": "t"}
    assert SC.effective_meta(meta, {}) is meta
    unit = {SC.UNIT_KEY: [{"added": "tests/test_core.py"}, {"added": "calc/core.py"}]}
    out = SC.effective_meta(meta, unit)
    assert out["scope"]["paths"] == ["calc/core.py", "tests/test_core.py"]
    assert meta["scope"]["paths"] == ["calc/core.py"]


@pytest.mark.parametrize(("path", "exact"), [
    ("tests/test_a.py", True), ("tests/*.py", False), ("tests/test_[ab].py", False), ("/tests/test_a.py", False),
    ("../x/test_a.py", False), ("tests//test_a.py", False), ("tests\\test_a.py", False), ("tests/", False),
    (" tests/test_a.py", False), ("", False),
    # One printable line (PR #545 review, m1): a newline, a carriage return, another C0 control or DEL is refused.
    ("tests/test_a\n.py", False), ("tests/test_a.py\nx", False), ("tests/test_\r.py", False),
    ("tests/test_\x1b.py", False), ("tests/test_\x7f.py", False)])
def test_only_one_exact_repository_relative_path_is_added(path, exact):
    assert (SC.exact_path_problem(path) is None) == exact


def test_test_definitions_are_counted_by_extension_and_an_unknown_one_is_named_unchecked():
    assert SC.test_definitions("t/test_a.py", "def test_a():\n    pass\nasync def test_b():\n    pass\n") == 2
    assert SC.test_definitions("t/a_test.go", "func TestA(t *testing.T) {}\nfunc helper() {}\n") == 1
    assert SC.test_definitions("t/a.test.ts", "it('a', () => {});\ntest.skip('b', () => {});\n") == 2
    assert SC.test_definitions("t/test_a.c", "TEST(a, b) {}\nTEST_F(c, d) {}\n") == 2
    assert SC.test_definitions("t/a.feature", "Scenario: a\n") is None
    texts = {"a.py": ("def test_a(): pass\ndef test_b(): pass\n", "def test_a(): pass\n"),
             "b.py": (None, "def test_b(): pass\n"), "c.feature": ("x", "y")}  # b.py is new: it counts 0 before
    stops, unchecked = SC.removal_stops(list(texts), lambda p: texts[p][0], lambda p: texts[p][1])
    assert stops == [] and unchecked == ["c.feature"]  # a test moved between added paths is neutral
    stops, _ = SC.removal_stops(["a.py"], lambda p: texts[p][0], lambda p: None)
    assert [s["stop"] for s in stops] == ["test_removed", "fewer_test_definitions"]


def test_the_kind_of_path_raises_its_stop():
    rules = SC._rules()
    assert [s["stop"] for s in SC.static_stops("tests/conftest.py", False, rules)] == ["runner_config"]
    assert [s["stop"] for s in SC.static_stops("tests/helpers.py", True, rules)] == ["shared_test_file"]
    assert SC.static_stops("tests/helpers.py", False, rules) == []  # a new helper is not a shared file yet
    assert SC.static_stops("tests/test_core.py", True, rules) == []


def test_a_signoff_cites_a_plan_revision_of_the_ticket_or_quotes_the_operator():
    assert SC.signoff_source("signed off in plan v2", {1, 2}) == {"source": "plan", "plan_revision": 2}
    assert SC.signoff_source("signed off in plan v3", {1, 2}) is None
    assert SC.signoff_source('operator: "go ahead and replace the mocks"', set()) == {"source": "operator_quote"}
    assert SC.signoff_source("the operator agreed", {1}) is None


def test_a_module_is_named_only_as_a_whole_word():
    assert SC.names_module("from calc.core import add\n", ["core"]) == "core"
    assert SC.names_module("from calc.coreutils import add\n", ["core"]) is None


def test_a_file_whose_tests_the_table_does_not_recognize_is_unchecked_not_counted_as_zero():
    """PR #540 review, m1: C with Unity style counts 0 at base, so removing every test would raise no stop."""
    unity = "void test_a(void) {}\nvoid test_b(void) {}\n"
    stops, unchecked = SC.removal_stops(["tests/test_a.c"], lambda p: unity, lambda p: "")
    assert stops == [] and unchecked == ["tests/test_a.c"]
    assert "unchecked" in SC.DEFINITION_LIMIT and "commented-out" in SC.DEFINITION_LIMIT


def test_rule_three_never_takes_a_dunder_stem_for_a_module():
    """PR #540 review, m6: `__init__` names a language hook in any test, not the package."""
    assert SC.module_stems(["pkg/__init__.py", "pkg/core.py", "pkg/__main__.py"]) == ["core"]
    assert SC.names_module("class A:\n    def __init__(self): pass\n", SC.module_stems(["pkg/__init__.py"])) is None


def test_a_live_implementer_is_told_with_harness_send_and_a_reader_is_redispatched():
    """PR #540 review, m5: the add exists to save the implementer's run, so its result never cancels it."""
    state = {"revision": 7, "work": {"T-0001": {"kind": "ticket", "mutating": True}},
             "invocations": {"INV-0001": {"status": "active", "work_unit": "T-0001", "role": "implementer",
                                          "runs": [{"run": "R-INV-0001-1"}]},
                             "INV-0002": {"status": "active", "work_unit": "T-0001", "role": "reviewer",
                                          "card": {"id": "code_reviewer"}}}}
    impl, reader = SC.ScopeCorrections.stale_invocations(state, "T-0001", "tests/test_a.py", lambda run: K.RUNNING)
    assert impl["commands"] == ["aew harness send R-INV-0001-1 --fields -"] and "text" in impl["fields"]
    assert reader["commands"][0].startswith("aew invoke cancel INV-0002") and "reason" in reader["fields"]
    # With coordination messaging on, `harness send` is always refused: a message is recorded for the live implementer
    # with `message_send` to its invocation, as the wake advice says, with arguments its schema admits as printed
    # (PR #545 review, m2; quick check, m6).
    impl, reader = SC.ScopeCorrections.stale_invocations(state, "T-0001", "tests/test_a.py", lambda run: K.RUNNING,
                                                         messaging=True)
    assert impl["commands"] == ["aew lead tool message_send --arguments -"], impl
    assert impl["fields"]["to"] == "INV-0001" and "tests/test_a.py" in impl["fields"]["body"], impl
    assert impl["fields"]["expect_rev"] == 8  # the revision the add commits
    check_call("message_send", impl["fields"], "normal", frozenset({contract.MESSAGING}))
    assert not any("harness send" in c for c in impl["commands"] + reader["commands"])
    assert reader["commands"][0].startswith("aew invoke cancel INV-0002")


def test_the_live_runs_harness_send_takes_have_one_owner():
    """PR #545 review, m2: the add names `harness send` for exactly the runs `harness_send` admits."""
    import inspect

    from aew.engine import harness_ops

    assert K.LIVE_RUNS == (K.STARTING, K.RUNNING)
    assert "K.LIVE_RUNS" in inspect.getsource(harness_ops.Harness._lead_request)
    assert "K.LIVE_RUNS" in inspect.getsource(SC.ScopeCorrections.stale_invocations)


@pytest.mark.parametrize("status", [K.ENDED_WITH_EVIDENCE, K.ENDED_WITHOUT_EVIDENCE, K.CRASHED, K.LOST, K.UNREADABLE,
                                    K.UNCONFIRMED])
def test_an_implementer_whose_run_is_not_live_is_redispatched_never_told_with_harness_send(status):
    """PR #540 quick check, m-b: `harness send` refuses a run that is not STARTING or RUNNING, so an ended run's
    implementer is named the re-dispatch commands: a fresh invocation on the kept workspace."""
    state = {"work": {"T-0001": {"kind": "ticket", "mutating": True}},
             "invocations": {"INV-0001": {"status": "active", "work_unit": "T-0001", "role": "implementer",
                                          "card": {"id": "engineer"}, "runs": [{"run": "R-INV-0001-1"}]}}}
    [impl] = SC.ScopeCorrections.stale_invocations(state, "T-0001", "tests/test_a.py", lambda run: status)
    assert not any("harness send" in c for c in impl["commands"]), impl
    assert impl["commands"][0].startswith("aew invoke cancel INV-0001") and "reason" in impl["fields"], impl


def test_the_lines_changed_are_split_by_declared_scope_and_added_paths():
    """PR #540 quick check, m-c: an added path counts as added even where a declared glob matches it; a path in neither
    is left out; a binary file is a file with no lines."""
    numstat = ("3\t1\tcalc/core.py\0" "12\t0\ttests/test_core.py\0" "-\t-\tcalc/logo.png\0"
               "5\t5\tdocs/other.md\0")
    assert SC.lines_changed(numstat, ["calc/**", "tests/test_core.py"], ["tests/test_core.py"]) == {
        "declared": {"files": 2, "added": 3, "removed": 1}, "added": {"files": 1, "added": 12, "removed": 0}}


def test_the_lead_guide_and_the_review_card_carry_the_same_three_lines_on_test_work():
    """The designer's decisions of 2026-11-03, §2: removing tests, a suite's flow or shared setup, and its overall
    mocking or a wholesale refactor need a sign-off, for all test work; the guide and the review card both say so, and
    the guide no longer reads as if a scope could never change."""
    from aew import roles
    from aew.engine import guide
    from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
    from aew.surface import lead_text

    text = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS)
    assert guide.TEST_WORK in text and f"`{SC.CHOICE}`" in text
    card = " ".join(roles.builtin_cards()["code_reviewer"].meta["responsibilities"])
    for words in ("removed tests", "flow or shared setup", "overall mocking", "wholesale refactor", "sign-off",
                  "proportion"):
        assert words in card, words
    for words in ("remove tests", "flow or shared setup", "overall mocking", "wholesale", "sign-off", "proportion"):
        assert words in guide.TEST_WORK, words
