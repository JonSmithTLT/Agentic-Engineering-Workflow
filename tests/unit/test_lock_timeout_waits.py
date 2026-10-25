"""A test that injects a lock timeout never waits for what that lock delays with a literal at or below its bound.

The class (main's push run at f41b001e, the Windows serial lane): a polled wait whose window is at or below the code's
own bound on the event's latency, where that bound includes a lock wait whose timeout is swallowed. A Lead broker's
watchdog read that waits out the control lock raises ``LockTimeout``, which ``LeadBroker._authority_lost`` takes as
"still the Lead", so one watchdog iteration may take ``broker_liveness.wedge_threshold_s(lock_timeout, POLL_S)``: the
``wedge_after_s`` the broker records, which ``judge`` holds to. The superseded case waited 10 s for ``closed_at`` with
a lock timeout of 10.0, so one read that waited out the lock failed it. Such a wait derives its window from the bound
the code records: ``watchdog_wait_s(first, poll)`` (tests/helpers/notifier.py).

The invariant, as a scan sees it: in a test function that injects a lock timeout ``T``, no polled wait's window is a
literal at or below ``wedge_threshold_s(T, POLL_S)``, unless ``EXCUSED`` lists the wait with the reason it is right.
- **An injection** is ``x.lock_timeout = T``, a ``lock_timeout=T`` keyword in a call, or ``setattr(x, "lock_timeout",
  T)`` (``monkeypatch.setattr`` too). Two detectors find them over every test file, and must agree: an AST walk, and a
  regular expression over each line. ``T`` is the larger value an injection can take (``0.5 if wedged else 10.0`` is
  10.0), so the bound is never too small. A ``T`` that does not fold to a number from the function's own literals is
  unknown, and fails the scan rather than passing it.
- **``POLL_S``** is the larger value the function patches it to (``monkeypatch.setattr(lead_broker, "POLL_S", poll)``),
  else ``lead_broker.POLL_S``.
- **A polled wait** is a call of a helper named in ``test_polling_predicates.POLLERS``, the list that check owns. Its
  window is the parameter its definitions under tests/ name ``timeout`` or ``seconds``, at its position or by keyword,
  and the smallest default they give when the call omits it (``window_params``). A window is a literal when it folds to
  a number from the function's own literals (``10``, ``w`` bound once to ``10``, ``5 + 5``, the smaller branch of
  ``20 if slow else 10``); a window read at run time (``first["wedge_after_s"] + 2 * poll``) is derived, and passes.
- **One function** is a module-level function or a method of a module-level class, with the functions nested in it.

What the scan does not see (pinned below), each a defect the reviewer reads for:
- an injection in a helper the test calls, or in a fixture (test_reference_concurrency.py's ``_held`` injects 0.2 for
  its callers, whose one poll is on a constant);
- a wait on a component with the default lock timeout, 60 s, which no test injects: test_steering_loop.py, for one,
  gives the steering loop's activations 30 s;
- a poller not in ``POLLERS``, a window given through ``**kwargs``, or at a position its definitions under tests/ do
  not give (src's ``outbox.wait_for`` takes it third);
- a ``POLL_S`` patched by a fixture, or a component whose poll is not ``POLL_S`` (the steering loop's ``poll_s``);
- a ``T`` changed by augmented assignment (``x.lock_timeout += 1``).
The text detector also sees what is not an injection: a local variable or a default named ``lock_timeout``, and a
mention in a string or a comment. The agreement test then fails, which is how a new spelling gets looked at. An
injection spread over lines (``setattr(`` on one, ``"lock_timeout"`` on the next), or an annotated one, is the AST
detector's alone. This module plants injections as strings, so the text detector skips it (``EXEMPT``); the AST one
reads it like any other file.

The scan bounds the window, not the event's latency: a window above the bound passes, and one at or below it whose
event never waits on that lock is listed in ``EXCUSED``, with a reason the reviewer checks against the code.
"""

from __future__ import annotations

import ast
import functools
import operator
import re
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple

import pytest
from test_polling_predicates import POLLERS  # the polling helpers, by name: that check owns the list

from aew.harness import broker_liveness, lead_broker

ROOT = Path(__file__).resolve().parents[2]
EXEMPT = {Path(__file__).resolve()}  # this module plants injections as strings: the text detector skips it
WINDOWS = ("timeout", "seconds")  # how a poller's definition names its window
DEF_TEXT = re.compile(rf"\bdef (?:{'|'.join(sorted(POLLERS))})\(")  # a cheap filter: parse only files that define one
INJECTION_TEXT = re.compile(r"\block_timeout\s*=(?!=)|\bsetattr\([^\n]*?[\"']lock_timeout[\"']")
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

NOTIFIER = "tests/integration/test_notifier.py"
LIVENESS = "test_broker_liveness_is_local_and_beats_every_poll"
_BEAT = "the beat thread writes the record every POLL_S and never reads the store (broker_liveness.Beat, R2-m3)"
_WEDGED = ("it runs in the wedged case only, whose lock timeout is 0.5: wedge_threshold_s(0.5, 0.25) is 1.0 s, far "
           "below its 10 s (the scan bounds the function by the larger timeout it injects, the other cases' 10.0)")
# The waits at or below the scan's bound that are right, and why: {(path, function, what): (how many sites, why)}.
EXCUSED = {
    (NOTIFIER, LIVENESS, "a second beat"): (1, _BEAT),
    (NOTIFIER, LIVENESS, "a whole liveness record"): (2, _BEAT),  # the slow read's and the wedged case's
    (NOTIFIER, LIVENESS, "the watchdog to wedge"): (1, _WEDGED),
    (NOTIFIER, LIVENESS, "the wedge to be judged"): (1, _WEDGED),
    (NOTIFIER, LIVENESS, "the watchdog to recover"): (1, _WEDGED),
}


class Site(NamedTuple):
    """A polled wait with a literal window at or below its function's bound."""

    path: str
    function: str
    line: int
    what: str
    window: float
    lock_timeout: float
    poll_s: float

    @property
    def bound(self) -> float:
        return broker_liveness.wedge_threshold_s(self.lock_timeout, self.poll_s)

    def __str__(self) -> str:
        return (f"{self.path}:{self.line} ({self.function}) waits {self.window:g}s for {self.what!r}, at or below "
                f"{self.bound:g}s = wedge_threshold_s(lock_timeout {self.lock_timeout:g}, POLL_S {self.poll_s:g})")


def _called_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _setattr_of(call: ast.Call, attr: str) -> bool:
    """``setattr(x, attr, v)``, or a method of that name (``monkeypatch.setattr(x, attr, v)``)."""
    return (_called_name(call) == "setattr" and len(call.args) >= 3 and isinstance(call.args[1], ast.Constant)
            and call.args[1].value == attr)


def _fold(node: ast.expr | None, names: dict[str, ast.expr], pick: Callable[[float, float], float] = max,
          depth: int = 0) -> float | None:
    """The number ``node`` folds to from the function's own literals, or None: read at run time. Of a conditional's
    two branches ``pick`` takes one: the larger for a lock timeout, the smaller for a window (never the lenient one)."""
    if node is None or depth > 32:
        return None
    if isinstance(node, ast.Constant):
        value = node.value
        return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _fold(node.operand, names, pick, depth + 1)
        return None if inner is None else -inner
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        left, right = _fold(node.left, names, pick, depth + 1), _fold(node.right, names, pick, depth + 1)
        if left is None or right is None or (isinstance(node.op, ast.Div) and right == 0):
            return None
        return OPS[type(node.op)](left, right)
    if isinstance(node, ast.IfExp):
        body, orelse = _fold(node.body, names, pick, depth + 1), _fold(node.orelse, names, pick, depth + 1)
        return None if body is None or orelse is None else pick(body, orelse)
    if isinstance(node, ast.Name) and node.id in names:
        return _fold(names[node.id], names, pick, depth + 1)
    return None


def _functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Each module-level function, and each method of a module-level class; a nested function is part of its own."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node
        elif isinstance(node, ast.ClassDef):
            yield from (n for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))


def _bindings(fn: ast.AST) -> dict[str, ast.expr]:
    """Each name the function binds exactly once, by a plain ``name = value``: what a literal bound to a name folds
    through. A name bound twice, or also as a parameter or a loop variable, is not folded."""
    stores = Counter(n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store))
    stores.update(a.arg for a in ast.walk(fn) if isinstance(a, ast.arg))
    return {node.targets[0].id: node.value for node in ast.walk(fn)
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and stores[node.targets[0].id] == 1}


def _injections(node: ast.AST) -> list[tuple[int, ast.expr]]:
    """Each lock timeout injected under ``node``: ``(line, value)``, the line where ``lock_timeout`` is written."""
    found = []
    for n in ast.walk(node):
        if isinstance(n, ast.Assign | ast.AnnAssign) and n.value is not None:
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            found += [(t.lineno, n.value) for t in targets if isinstance(t, ast.Attribute) and t.attr == "lock_timeout"]
        elif isinstance(n, ast.Call):
            found += [(k.lineno, k.value) for k in n.keywords if k.arg == "lock_timeout"]
            if _setattr_of(n, "lock_timeout"):
                found.append((n.args[1].lineno, n.args[2]))
    return found


def _polls(fn: ast.AST) -> list[ast.expr]:
    """The values the function patches ``POLL_S`` to."""
    found = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and _setattr_of(n, "POLL_S"):
            found.append(n.args[2])
        elif isinstance(n, ast.Assign):
            found += [n.value for t in n.targets if isinstance(t, ast.Attribute) and t.attr == "POLL_S"]
    return found


@functools.cache
def window_params() -> dict[str, tuple[frozenset[int], frozenset[str], float | None]]:
    """Where each polling helper takes its window, read from its definitions under tests/: ``{name: (positions,
    keywords, the smallest default)}``. A method's ``self`` is not counted, as a call does not pass it."""
    positions: dict[str, set[int]] = {name: set() for name in POLLERS}
    keywords: dict[str, set[str]] = {name: set() for name in POLLERS}
    defaults: dict[str, list[float]] = {name: [] for name in POLLERS}
    for path in sorted((ROOT / "tests").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if not DEF_TEXT.search(source):
            continue
        for fn in ast.walk(ast.parse(source)):
            if not (isinstance(fn, ast.FunctionDef) and fn.name in POLLERS):
                continue
            positional = [a.arg for a in (*fn.args.posonlyargs, *fn.args.args)]
            if positional[:1] in (["self"], ["cls"]):
                positional = positional[1:]
            given = dict(zip(positional[len(positional) - len(fn.args.defaults):], fn.args.defaults, strict=True))
            given.update((a.arg, d) for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults, strict=True) if d)
            positions[fn.name] |= {i for i, name in enumerate(positional) if name in WINDOWS}
            named = (*positional, *(a.arg for a in fn.args.kwonlyargs))
            keywords[fn.name] |= {name for name in named if name in WINDOWS}
            defaults[fn.name] += [v for name, d in given.items() if name in WINDOWS and (v := _fold(d, {})) is not None]
    return {name: (frozenset(positions[name]), frozenset(keywords[name]), min(defaults[name], default=None))
            for name in POLLERS}


def _window(call: ast.Call, names: dict[str, ast.expr]) -> float | None:
    """The call's window when it is a literal (the smallest, if given twice), or None: derived, or no window."""
    positions, keywords, default = window_params()[_called_name(call)]
    given = [call.args[i] for i in sorted(positions) if i < len(call.args)]
    given += [k.value for k in call.keywords if k.arg in keywords]
    if not given:
        return default
    folded = [_fold(g, names, min) for g in given]
    return None if None in folded else min(v for v in folded if v is not None)


def _what(call: ast.Call) -> str:
    """What the wait is for: its first string argument (``until``'s ``what``, ``bounded_wait``'s ``name``)."""
    for node in (*call.args, *(k.value for k in call.keywords)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
    return ""


def scan(source: str, path: str = "<planted>") -> tuple[list[Site], list[str]]:
    """Each polled wait in a function that injects a lock timeout whose literal window is at or below that function's
    bound, and each such function whose lock timeout or ``POLL_S`` does not fold (unknown: never a pass)."""
    sites, unknown = [], []
    for fn in _functions(ast.parse(source)):
        injected = _injections(fn)
        if not injected:
            continue
        names = _bindings(fn)
        timeouts = [(_fold(value, names, max), line) for line, value in injected]
        polls = [_fold(value, names, max) for value in _polls(fn)]
        unknown += [f"{path}:{line} ({fn.name}): its lock timeout does not fold to a number" for v, line in timeouts
                    if v is None]
        if None in polls:
            unknown.append(f"{path}:{fn.lineno} ({fn.name}): the POLL_S it patches does not fold to a number")
        if any(v is None for v, _ in timeouts) or None in polls:
            continue
        lock_timeout = max(v for v, _ in timeouts if v is not None)
        poll_s = max((p for p in polls if p is not None), default=float(lead_broker.POLL_S))
        bound = broker_liveness.wedge_threshold_s(lock_timeout, poll_s)
        for call in ast.walk(fn):
            if isinstance(call, ast.Call) and _called_name(call) in POLLERS:
                window = _window(call, names)
                if window is not None and window <= bound:
                    sites.append(Site(path, fn.name, call.lineno, _what(call), window, lock_timeout, poll_s))
    return sites, unknown


def ast_injection_lines(source: str) -> set[int]:
    return {line for line, _ in _injections(ast.parse(source))}


def text_injection_lines(source: str) -> set[int]:
    return {source.count("\n", 0, m.start()) + 1 for m in INJECTION_TEXT.finditer(source)}


@functools.cache
def _live() -> tuple[list[Site], list[str], dict[str, tuple[set[int], set[int]]]]:
    """Every test file: its sites, its unknowns, and its injection lines by each detector (the text one skips
    ``EXEMPT``)."""
    sites, unknown, injections = [], [], {}
    for path in sorted((ROOT / "tests").rglob("*.py")):
        source, rel = path.read_text(encoding="utf-8"), path.relative_to(ROOT).as_posix()
        found, unresolved = scan(source, rel)
        sites += found
        unknown += unresolved
        by_text = set() if path.resolve() in EXEMPT else text_injection_lines(source)
        injections[rel] = (ast_injection_lines(source), by_text)
    return sites, unknown, injections


def excuse_mismatches(sites: list[Site], excused: dict[tuple[str, str, str], tuple[int, str]]) -> dict[str, int]:
    """Each excuse whose count is not its live sites' (a stale or a collapsed entry), by its key: the live count."""
    counts = Counter((s.path, s.function, s.what) for s in sites)
    return {"::".join(key): counts[key] for key, (n, _) in excused.items() if counts[key] != n}


def test_no_wait_in_a_test_that_injects_a_lock_timeout_is_a_literal_at_or_below_its_bound():
    sites, unknown, _ = _live()
    assert not unknown, ("a lock timeout or POLL_S that does not fold cannot be bounded: make it a literal, or derive "
                         f"every wait in the function from the bound the code records: {unknown}")
    unexcused = [str(s) for s in sites if (s.path, s.function, s.what) not in EXCUSED]
    assert not unexcused, (
        "a polled wait in a test that injects a lock timeout has a literal window at or below the bound one lock wait "
        "sets: derive it from the bound the code records (a Lead broker's wedge_after_s: watchdog_wait_s(first, poll), "
        "tests/helpers/notifier.py), or, for a wait that is right as it is, list it in EXCUSED with why: "
        + "; ".join(unexcused))


def test_each_excuse_names_live_sites_counted_exactly():
    assert excuse_mismatches(_live()[0], EXCUSED) == {}


def test_the_two_detectors_agree_on_every_injection():
    disagree = {path: (sorted(by_ast), sorted(by_text)) for path, (by_ast, by_text) in _live()[2].items()
                if by_ast != by_text}
    assert not disagree


# ---------------------------------------------------------------------------------------------- planted controls


def planted(body: str) -> str:
    """A test function holding ``body``; its last line is the line a wrong body's one site is on."""
    return "def test_planted(engine, monkeypatch, root, lab, case, slow):\n" + "".join(
        f"    {line}\n" for line in body.split("\n"))


WRONG = [  # one site each, on the body's last line
    # main's superseded wait at f41b001e: the larger branch of a conditional injection bounds it
    'poll = 0.25\nmonkeypatch.setattr(lead_broker, "POLL_S", poll)\n'
    'engine.store.lock_timeout = 0.5 if case == "wedged" else 10.0\n'
    "until(lambda: ready(), 10, \"the superseded broker's closed_at\")",
    'engine.store.lock_timeout = 10.0\nuntil(lambda: ready(), timeout=10, what="x")',  # the window by keyword
    'store = ControlStore(root, lock_timeout=10)\nuntil(lambda: ready(), 5, "x")',  # the injection by keyword
    'monkeypatch.setattr(engine.store, "lock_timeout", 10.0)\nuntil(lambda: ready(), 5, "x")',
    't = 10.0\nengine.store.lock_timeout = t\nw = 5 + 5\nuntil(lambda: ready(), w, "x")',  # through names, arithmetic
    'engine.store.lock_timeout = 30.0\nuntil(lambda: ready(), what="x")',  # until's default, 30 s, under 32 s
    'engine.store.lock_timeout = 10.0\nmonkeypatch.setattr(lead_broker, "POLL_S", 0.25)\n'
    'until(lambda: ready(), 10.5, "x")',  # at the bound itself
    'engine.store.lock_timeout = 10.0\nuntil(lambda: ready(), 20 if slow else 10, "x")',  # the smaller window
    'engine.store.lock_timeout = 10.0\n_wait_for(lambda: ready(), "x", 10)',  # the other pollers' windows
    'engine.store.lock_timeout = 10.0\nbounded_wait("x", ready, seconds=5)',
    'engine.store.lock_timeout = 10.0\nlab.until(lambda: ready(), 10, "x")',
    'engine.store.lock_timeout = 10.0\nwait_for(lambda: ready(), 9)',
]
RIGHT = [
    'engine.store.lock_timeout = 10.0\nuntil(lambda: ready(), first["wedge_after_s"] + 2 * poll, "x")',  # derived
    'engine.store.lock_timeout = 10.0\nuntil(lambda: ready(), watchdog_wait_s(first, poll), "x")',
    'engine.store.lock_timeout = 10.0\nmonkeypatch.setattr(lead_broker, "POLL_S", 0.25)\n'
    'until(lambda: ready(), 10.6, "x")',  # just above the bound
    'engine.store.lock_timeout = 0.5\nuntil(lambda: ready(), 10, "x")',  # above 0.5's bound, 2.5 s
    'until(lambda: ready(), 1, "x")',  # no injection
    'assert engine.store.lock_timeout == 10.0\nuntil(lambda: ready(), 1, "x")',  # a comparison, not an injection
    'with FileLock(root / LOCK_REL, timeout=10):\n    until(lambda: ready(), 5, "x")',  # the test's own taker
    'engine.store.lock_timeout = 10.0\nwaiting(lambda: ready())\nheld.wait(5)',  # no window; not a poller
]
MISSED = [  # what the scan does not see: no site, and no unknown
    'engine.store.lock_timeout = 10.0\nchat.receive(5, gone=lambda: ready())',  # a poller not in POLLERS
    'engine.store.lock_timeout = 10.0\nuntil(lambda: ready(), **{"timeout": 5})',  # a window through **kwargs
    'engine.store.lock_timeout = 10.0\noutbox.wait_for(lambda: ready(), root, 5)',  # src's wait_for: its window third
    'engine.store.lock_timeout += 10\nuntil(lambda: ready(), 5, "x")',  # an augmented injection
    'engine.store.lock_timeout = 10.0\nuntil(lambda: ready(), 13, "x")',  # POLL_S patched to 2.0 by a fixture
    'until(lambda: len(loop.executed) == 2, 30, "the first activation")',  # the default lock timeout, 60 s
]
UNKNOWN = [  # reported as unknown, never passed
    'engine.store.lock_timeout = case\nuntil(lambda: ready(), 5, "x")',  # a parameter
    'engine.store.lock_timeout = config["lock"]\nuntil(lambda: ready(), 5, "x")',
    'engine.store.lock_timeout = 1.0\nmonkeypatch.setattr(lead_broker, "POLL_S", poll())\nuntil(lambda: ready(), 1)',
]
TEXT_ONLY = [  # injection lines the text detector alone reports: the agreement test fails on them
    "lock_timeout = 5",  # a local variable
    "pass  # a store with lock_timeout = 1 times out at once",  # a comment
    'ready = "lock_timeout=1"',
]
AST_ONLY = [
    'monkeypatch.setattr(\n    engine.store,\n    "lock_timeout", 1.0)',  # spread over lines
    "engine.store.lock_timeout: float = 1.0",  # annotated
]


@pytest.mark.parametrize("body", WRONG)
def test_a_literal_window_at_or_below_the_bound_is_found(body):
    source = planted(body)
    sites, unknown = scan(source)
    assert ([s.line for s in sites], unknown) == ([source.count("\n")], []), sites


@pytest.mark.parametrize("body", RIGHT)
def test_a_derived_window_or_one_above_the_bound_or_no_injection_is_not_flagged(body):
    assert scan(planted(body)) == ([], [])


@pytest.mark.parametrize("body", MISSED)
def test_what_the_scan_misses_is_pinned(body):
    assert scan(planted(body)) == ([], [])


@pytest.mark.parametrize("body", UNKNOWN)
def test_a_lock_timeout_or_poll_that_does_not_fold_is_unknown_never_a_pass(body):
    sites, unknown = scan(planted(body))
    assert sites == [] and len(unknown) == 1, unknown


def test_the_message_names_the_bound_to_derive_from():
    [site] = scan(planted(WRONG[0]), "tests/integration/test_x.py")[0]
    assert str(site) == ("tests/integration/test_x.py:5 (test_planted) waits 10s for \"the superseded broker's "
                         "closed_at\", at or below 10.5s = wedge_threshold_s(lock_timeout 10, POLL_S 0.25)")


def test_a_function_is_bounded_by_its_own_injections_only():
    source = ("def _held(engine):\n    engine.store.lock_timeout = 0.2\n\n\ndef test_y(engine):\n    _held(engine)\n"
              "    until(lambda: ready(), 0.1, 'x')\n")  # test_reference_concurrency.py's shape, with a poll: unseen
    assert scan(source) == ([], [])


@pytest.mark.parametrize("body", [*WRONG, *RIGHT, *UNKNOWN])
def test_the_two_detectors_agree_on_each_planted_injection(body):
    source = planted(body)
    assert ast_injection_lines(source) == text_injection_lines(source)


@pytest.mark.parametrize("body", TEXT_ONLY)
def test_what_only_the_text_detector_reports_is_pinned(body):
    source = planted(body)
    assert (ast_injection_lines(source), text_injection_lines(source)) == (set(), {2})


@pytest.mark.parametrize("body", AST_ONLY)
def test_what_only_the_ast_detector_reports_is_pinned(body):
    source = planted(body)
    assert ast_injection_lines(source) == {source.count("\n")} and text_injection_lines(source) == set()


def test_a_stale_or_collapsed_excuse_is_found():
    sites, _ = scan(planted('engine.store.lock_timeout = 10.0\nuntil(lambda: a(), 5, "x")\nuntil(lambda: b(), 5, "x")'))
    key = ("<planted>", "test_planted", "x")
    assert excuse_mismatches(sites, {key: (2, "right")}) == {}
    assert excuse_mismatches(sites, {key: (1, "collapsed")}) == {"<planted>::test_planted::x": 2}
    assert excuse_mismatches(sites, {("<planted>", "test_planted", "gone"): (1, "stale")}) == {
        "<planted>::test_planted::gone": 0}


def test_each_poller_takes_its_window_where_its_definition_names_it():
    """Read from the definitions under tests/, so a window that moves moves the scan with it. This pins the result:
    a poller added, or one whose window moves, has to update it."""
    assert window_params() == {
        "until": (frozenset({1}), frozenset({"timeout"}), 30.0),  # notifier's (30 s) and HarnessLab's (60 s)
        "wait_for": (frozenset({1}), frozenset({"timeout"}), 10.0),
        "wait_until": (frozenset(), frozenset(), None),  # no test defines it
        "_wait_for": (frozenset({2}), frozenset({"timeout"}), 90.0),
        "bounded_wait": (frozenset(), frozenset({"seconds"}), None),  # keyword-only, and its default is None
        "waiting": (frozenset(), frozenset(), None),  # no window
        "_retrying": (frozenset(), frozenset(), None),
    }


def test_the_exempt_module_is_skipped_by_the_text_detector_only(tmp_path, monkeypatch):
    """An injection planted in the exempt module is still found by the AST detector, so the agreement test fails."""
    window_params()  # derived from the real tree before ROOT moves
    plants = tmp_path / "tests" / "unit" / "plants.py"
    plants.parent.mkdir(parents=True)
    plants.write_text("def test_z(engine):\n    engine.store.lock_timeout = 1.0\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "EXEMPT", {plants.resolve()})
    assert _live.__wrapped__()[2] == {"tests/unit/plants.py": ({2}, set())}
