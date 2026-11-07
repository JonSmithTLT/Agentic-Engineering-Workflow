"""The launch conflict check's pure parts (register E151; ``aew.engine.conflicts``): the exact glob intersection, the
conflict each pair of Tickets yields, and the hold message the Lead reads. The engine path is driven end to end in
``tests/integration/test_launch_conflict.py``."""

from __future__ import annotations

import itertools
import random

import pytest

from aew.engine import conflicts as C
from aew.engine.dispatch import ENTRYPOINTS, MUTATION
from aew.engine.reasons import REASONS
from aew.util import glob_match

# ---------------------------------------------------------------- the glob intersection


@pytest.mark.parametrize(("a", "b", "meet"), [
    ("calc/**", "calc/core.py", True),
    ("calc/**", "tests/**", False),
    ("calc/one.py", "calc/two.py", False),
    ("calc/*.py", "calc/*.md", False),  # a shared directory is not a shared file
    ("calc/*.py", "calc/c*", True),
    ("calc/new/**", "calc/**/x.py", True),  # a directory nothing tracks yet still meets
    ("**/*.py", "docs/README.md", False),
    ("**/*.py", "docs/a.py", True),
    ("calc/*", "calc/sub/x.py", False),  # `*` never crosses a `/`
    ("calc/**/", "calc/", True),
    ("src/?.py", "src/ab.py", False),
    ("src\\a.py", "src/a.py", True),  # glob_match reads both separators as `/`
])
def test_two_scopes_meet_exactly_when_some_path_matches_both(a, b, meet):
    assert C.globs_intersect(a, b) is meet
    assert C.globs_intersect(b, a) is meet


def _brute(x: str, y: str, alphabet: str = "ab/", longest: int = 7) -> bool:
    return any(glob_match(s, x) and glob_match(s, y)
               for k in range(longest + 1) for s in map("".join, itertools.product(alphabet, repeat=k)))


def test_the_intersection_agrees_with_glob_match_on_every_path_it_could_name():
    """A second, independent detector: every path over a small alphabet, matched by ``aew.util.glob_match`` itself.
    Patterns of at most four pieces need no path longer than seven characters to meet."""
    rng = random.Random(151)
    pieces = ["a", "b", "/", "*", "?", "**", "**/"]
    met = 0
    for _ in range(600):
        x = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 4)))
        y = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 4)))
        want = _brute(x, y)
        assert C.globs_intersect(x, y) is want, (x, y)
        met += want
    assert 100 < met < 500  # both answers were exercised


# ---------------------------------------------------------------- the conflict


def live(scope=("calc/one.py",), touched=(), **kw) -> C.LiveTicket:
    return C.LiveTicket(work_id="T-0001", invocation="INV-0001", workspace="ws-T-0001-1", scope=scope,
                        touched=touched, **kw)


def test_disjoint_scopes_and_changes_are_no_conflict():
    assert C.find_conflict("T-0002", ["calc/two.py"], live(touched=("calc/one.py",))) is None


@pytest.mark.parametrize(("scope", "other", "reasons"), [
    (["calc/**"], live(), ["scopes_overlap"]),
    (["calc/two.py"], live(touched=("calc/two.py",)), ["touched_in_scope"]),
    ([], live(), ["scope_unbounded"]),
    (["calc/two.py"], live(scope=()), ["live_scope_unbounded"]),
    (["calc/two.py"], live(touched=None, unreadable="gone"), ["paths_unknown"]),
    (["calc/two.py"], live(scope=None, unreadable="gone"), ["paths_unknown"]),
])
def test_each_condition_is_a_conflict(scope, other, reasons):
    found = C.find_conflict("T-0002", scope, other)
    assert found is not None and found["reasons"] == reasons
    assert found["work_id"] == "T-0001" and found["invocation"] == "INV-0001"


def test_unreadable_paths_are_a_conflict_never_an_empty_change():
    """``CNI-03.a``: an inability to establish non-interference is a conflict. The planted control is the same Ticket
    read as having changed nothing, which is clear."""
    assert C.find_conflict("T-0002", ["calc/two.py"], live(touched=())) is None
    found = C.find_conflict("T-0002", ["calc/two.py"], live(touched=None, unreadable="no such directory"))
    assert found["reasons"] == ["paths_unknown"] and found["unreadable"] == "no such directory"


# ---------------------------------------------------------------- what the Lead reads


def test_the_hold_message_says_it_is_held_why_and_what_it_waits_on():
    scope = ["calc/two.py", "calc/*.md"]
    found = C.find_conflict("T-0002", scope, live(scope=("calc/**",), touched=("calc/two.py",)))
    text = C.hold_message("T-0002", scope, found)
    assert text.startswith("T-0002 is held, not started: T-0001 is live (INV-0001, workspace ws-T-0001-1)")
    assert "T-0001 has already changed calc/two.py, inside T-0002's scope calc/two.py, calc/*.md" in text
    assert "calc/two.py with calc/**" in text and "calc/*.md with calc/**" in text
    assert "T-0002 waits until T-0001 is integrated or cancelled, either of which releases its workspace" in text


@pytest.mark.parametrize(("other", "scope", "says"), [
    (live(touched=None, unreadable="no such directory"), ["calc/two.py"],
     ["AEW cannot read which files T-0001 has changed (no such directory)", "or until T-0001's workspace can be read"]),
    (live(), [], ["T-0002 declares no scope", "T-0002 needs a scope that avoids T-0001's files"]),
    (live(scope=()), ["calc/two.py"], ["T-0001 declares no scope, so it may change any file"]),
])
def test_every_reason_is_named_in_plain_words(other, scope, says):
    text = C.hold_message("T-0002", scope, C.find_conflict("T-0002", scope, other))
    for s in says:
        assert s in text


def test_a_long_list_is_cut_to_a_few_with_the_rest_counted():
    touched = tuple(f"calc/f{i}.py" for i in range(8))
    found = C.find_conflict("T-0002", ["calc/f*.py"], live(scope=("calc/one.py",), touched=touched))
    assert "and 3 more" in C.hold_message("T-0002", ["calc/f*.py"], found)
    assert len(found["touched_in_scope"]) == 8  # the details carry them all


# ---------------------------------------------------------------- where it runs


def test_the_check_runs_wherever_mutation_is_granted_and_its_code_is_registered():
    assert "conflict.files" in MUTATION
    for name in ("work.assign", "invoke.create.mutating", "harness.launch"):
        assert "conflict.files" in ENTRYPOINTS[name].guards
    assert REASONS["FILES_CONFLICT"].blocking


def test_the_live_set_is_the_one_the_concurrency_cap_counts():
    state = {"work": {
        "T-1": {"kind": "ticket", "mutating": True, "workspace": {"status": "active"}},
        "T-2": {"kind": "ticket", "mutating": True, "workspace": {"status": "released"}},
        "T-3": {"kind": "ticket", "mutating": False, "workspace": {"status": "active"}},
        "S-1": {"kind": "story", "mutating": True, "workspace": {"status": "active"}},
        "T-4": {"kind": "ticket", "mutating": True},
    }}
    assert C.live_mutating_tickets(state) == ["T-1"]
