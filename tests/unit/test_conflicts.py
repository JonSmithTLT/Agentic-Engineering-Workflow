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


RECREATE = "a scope is fixed when a Ticket is created, so cancel T-0002 and create it again with"


@pytest.mark.parametrize(("other", "scope", "says", "never"), [
    # unreadable paths: wait for integration, cancellation, or a readable workspace
    (live(touched=None, unreadable="no such directory"), ["calc/two.py"],
     ["AEW cannot read which files T-0001 has changed (no such directory)", "or until T-0001's workspace can be read"],
     ["split the work"]),
    # an unbounded new scope: recreate it with a scope
    (live(), [], ["T-0002 declares no scope", "T-0002 needs a scope that avoids T-0001's files",
                  f"{RECREATE} `--scope`"], ["split the work"]),
    # an unbounded live scope: wait only
    (live(scope=()), ["calc/two.py"], ["T-0001 declares no scope, so it may change any file",
                                       "integrated or cancelled"], ["split the work", RECREATE]),
    # overlapping scopes: wait, or split the work by recreating with a narrower scope
    (live(scope=("calc/**",)), ["calc/two.py"], ["the two scopes can name the same files", "integrated or cancelled",
                                                 f"split the work so their scopes cannot meet: {RECREATE} a narrower"
                                                 " `--scope`"], []),
    # only a stray write outside the live Ticket's own scope: its removal (or a cancel) frees it, not integration
    (live(scope=("calc/one.py",), touched=("calc/one.py", "calc/two.py")), ["calc/two.py"],
     ["T-0001 has changed calc/two.py, outside its own scope and inside T-0002's (calc/two.py); T-0001's integration "
      "will refuse that change",
      "T-0002 waits until that change is removed from T-0001's workspace, or T-0001 is cancelled, which releases its "
      "workspace"],
     ["integrated or cancelled", "split the work", RECREATE, "has already changed"]),
])
def test_every_reason_is_named_in_plain_words_with_what_to_do(other, scope, says, never):
    """Each branch of the hold's what-to-do text (#350 review m1): a stray write is not told to split the work."""
    text = C.hold_message("T-0002", scope, C.find_conflict("T-0002", scope, other))
    for s in says:
        assert s in text, (s, text)
    for s in never:
        assert s not in text, (s, text)


def test_a_stray_write_is_named_apart_from_a_change_inside_both_scopes():
    found = C.find_conflict("T-0002", ["calc/**"], live(scope=("calc/one.py",), touched=("calc/one.py", "calc/x.py")))
    assert found["touched_in_scope"] == ["calc/one.py", "calc/x.py"] and found["outside_own_scope"] == ["calc/x.py"]
    text = C.hold_message("T-0002", ["calc/**"], found)
    assert "T-0001 has already changed calc/one.py, inside T-0002's scope" in text
    assert "T-0001 has changed calc/x.py, outside its own scope" in text
    assert "integrated or cancelled" in text  # the change inside both scopes still waits on integration


# ---------------------------------------------------------------- letter case (#350 review m2)


def test_in_a_case_insensitive_repository_two_spellings_of_one_path_meet():
    """Folded only when the repository is case-insensitive; the planted control is the same pair, case-sensitive."""
    assert C.find_conflict("T-0002", ["calc/one.py"], live(scope=("calc/One.py",))) is None
    found = C.find_conflict("T-0002", ["calc/one.py"], live(scope=("calc/One.py",)), fold=True)
    assert found["reasons"] == ["scopes_overlap"] and found["scope_pairs"] == [["calc/one.py", "calc/One.py"]]
    assert C.find_conflict("T-0002", ["calc/two.py"], live(touched=("Calc/Two.py",))) is None
    found = C.find_conflict("T-0002", ["calc/two.py"], live(touched=("Calc/Two.py",)), fold=True)
    assert found["touched_in_scope"] == ["Calc/Two.py"] and found["outside_own_scope"] == ["Calc/Two.py"]


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
