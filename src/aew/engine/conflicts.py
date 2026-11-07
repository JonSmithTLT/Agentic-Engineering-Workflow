"""The launch conflict check for concurrent workers' files (register E151; A-09 ``CNI-03.a``, ``CNI-03.g``).

Before a worker is given mutation authority over a Ticket (an assignment, a new implementer, or a harness run holding
an implementer's credential), its Ticket's declared scope is compared with every other live mutating Ticket's
declared scope and the paths that Ticket has already changed in its workspace. A Ticket is live while it holds an
active mutation workspace: the same set the ``mutating_concurrency`` cap counts, since an unintegrated change still
meets the other's at integration. The dispatch is held, not warned, when:

* the two declared scopes can name a common path (an exact glob intersection, so two Tickets that both create files
  in a directory nothing tracks yet still meet);
* a path the live Ticket has changed lies inside the new Ticket's scope (it may have strayed outside its own);
* either scope is unbounded (no scope declared: it may change any file);
* the live Ticket's changed paths cannot be read: an inability to establish non-interference is a conflict, never a
  clearance (``CNI-03.a``).

The check runs in the dispatch predicate, inside the transaction that makes the dispatch effective and bound to its
revision, and again at each harness launch (``CNI-03.g``): two admissions racing on one state cannot both commit, and
a launch sees what the other worker has changed since the assignment. Other resource kinds (ports, services, external
effects) are not checked here.

Pure functions only; ``Assurance.guard_conflict`` gathers the inputs and turns a conflict into a blocker.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from aew.util import glob_any, to_posix

SHOWN = 5  # paths or scope pairs named in a hold message; the details carry them all


def live_mutating_tickets(state: dict[str, Any]) -> list[str]:
    """Mutating Tickets holding a live workspace, whatever their state (M4-C review M2). The concurrency cap counts
    these, and the conflict check compares against them."""
    return sorted(
        wid for wid, u in state["work"].items()
        if u["kind"] == "ticket" and u["mutating"] and (u.get("workspace") or {}).get("status") == "active"
    )


# ------------------------------------------------------------------------------------- glob intersection
# ``aew.util.glob_match``'s language, token for token: ``**/`` is ``(?:.*/)?``, ``**`` is ``.*``, ``*`` is ``[^/]*``,
# ``?`` is ``[^/]`` and every other character is itself. Two patterns intersect when some path matches both; that is
# decided exactly on the product of their automata, never by sampling tracked files.

_LIT, _ONE, _STAR, _ANY, _DIRS = "lit", "one", "star", "any", "dirs"


def _tokens(pattern: str) -> tuple[tuple[str, str], ...]:
    p, i, out = to_posix(pattern), 0, []
    while i < len(p):
        if p.startswith("**/", i):
            out.append((_DIRS, ""))
            i += 3
        elif p.startswith("**", i):
            out.append((_ANY, ""))
            i += 2
        elif p[i] == "*":
            out.append((_STAR, ""))
            i += 1
        elif p[i] == "?":
            out.append((_ONE, ""))
            i += 1
        else:
            out.append((_LIT, p[i]))
            i += 1
    return tuple(out)


# A state is (token index, inside): ``inside`` marks a ``**/`` that has consumed characters and still needs its ``/``.
_State = tuple[int, bool]


def _closure(tokens: tuple[tuple[str, str], ...], states: set[_State]) -> frozenset[_State]:
    todo, seen = list(states), set(states)
    while todo:
        k, inside = todo.pop()
        if not inside and k < len(tokens) and tokens[k][0] in (_STAR, _ANY, _DIRS):
            nxt = (k + 1, False)  # zero repetitions, or the optional ``**/`` skipped
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return frozenset(seen)


def _step(tokens: tuple[tuple[str, str], ...], states: frozenset[_State], c: str) -> frozenset[_State]:
    out: set[_State] = set()
    for k, inside in states:
        if inside:
            out.add((k, True))
            if c == "/":
                out.add((k + 1, False))
            continue
        if k == len(tokens):
            continue
        kind, lit = tokens[k]
        if kind == _LIT:
            if c == lit:
                out.add((k + 1, False))
        elif kind == _ONE:
            if c != "/":
                out.add((k + 1, False))
        elif kind == _STAR:
            if c != "/":
                out.add((k, False))
        elif kind == _ANY:
            out.add((k, False))
        else:  # _DIRS
            out.add((k, True))
            if c == "/":
                out.add((k + 1, False))
    return _closure(tokens, out)


def globs_intersect(a: str, b: str) -> bool:
    """Whether some path matches both glob ``a`` and glob ``b`` (``aew.util.glob_match``'s language)."""
    ta, tb = _tokens(a), _tokens(b)
    literals = {lit for kind, lit in ta + tb if kind == _LIT}
    other = next(chr(c) for c in range(0x21, 0x110000) if chr(c) not in literals and chr(c) != "/")
    alphabet = sorted(literals | {"/", other})  # every other character behaves as ``other`` in both automata
    start = (_closure(ta, {(0, False)}), _closure(tb, {(0, False)}))
    seen, todo = {start}, deque([start])
    while todo:
        sa, sb = todo.popleft()
        if (len(ta), False) in sa and (len(tb), False) in sb:
            return True
        for c in alphabet:
            nxt = (_step(ta, sa, c), _step(tb, sb, c))
            if nxt[0] and nxt[1] and nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return False


def overlapping_scopes(a: list[str], b: list[str]) -> list[list[str]]:
    """Each pair ``[pattern of a, pattern of b]`` that can name a common path."""
    return [[x, y] for x in a for y in b if globs_intersect(x, y)]


# ------------------------------------------------------------------------------------- the check

@dataclass(frozen=True)
class LiveTicket:
    """What the check needs of one live mutating Ticket."""

    work_id: str
    invocation: str | None
    workspace: str | None
    scope: tuple[str, ...] | None  # empty: unbounded; None: its record could not be read
    touched: tuple[str, ...] | None  # None: the changed paths could not be established
    unreadable: str | None = None  # why the scope or the paths could not be read


def find_conflict(work_id: str, scope: list[str], live: LiveTicket) -> dict[str, Any] | None:
    """The conflict between dispatching ``work_id`` with ``scope`` and ``live``, or None when they cannot meet.

    The result carries ``reasons`` (every condition found, in the order a hold message names them), the changed paths
    inside the new scope, and the scope pairs that can meet."""
    reasons: list[str] = []
    touched_hits: list[str] = []
    pairs: list[list[str]] = []
    if live.touched is None or live.scope is None:
        reasons.append("paths_unknown")
    if not scope:
        reasons.append("scope_unbounded")
    if live.scope is not None and not live.scope:
        reasons.append("live_scope_unbounded")
    if scope and live.touched:
        touched_hits = sorted(p for p in live.touched if glob_any(p, scope))
        if touched_hits:
            reasons.append("touched_in_scope")
    if scope and live.scope:
        pairs = overlapping_scopes(scope, list(live.scope))
        if pairs:
            reasons.append("scopes_overlap")
    if not reasons:
        return None
    return {"work_id": live.work_id, "invocation": live.invocation, "workspace": live.workspace,
            "reasons": reasons, "scope": None if live.scope is None else list(live.scope),
            "touched_in_scope": touched_hits, "scope_pairs": pairs,
            **({"unreadable": live.unreadable} if "paths_unknown" in reasons else {})}


def _some(items: list[str]) -> str:
    shown = ", ".join(items[:SHOWN])
    return shown + (f" and {len(items) - SHOWN} more" if len(items) > SHOWN else "")


def hold_message(work_id: str, scope: list[str], c: dict[str, Any]) -> str:
    """What the Lead reads, and tells the operator: that the dispatch is held, why, and what it waits on."""
    other = c["work_id"]
    where = ", ".join(x for x in (c.get("invocation"), c.get("workspace") and f"workspace {c['workspace']}") if x)
    head = f"{work_id} is held, not started: {other} is live" + (f" ({where})" if where else "")
    why: list[str] = []
    reasons = c["reasons"]
    if "paths_unknown" in reasons:
        why.append(f"AEW cannot read which files {other} has changed ({c.get('unreadable') or 'unknown error'}), so "
                   f"it cannot show the two would not touch the same files")
    if "scope_unbounded" in reasons:
        why.append(f"{work_id} declares no scope, so it may change any file, {other}'s included")
    if "live_scope_unbounded" in reasons:
        why.append(f"{other} declares no scope, so it may change any file, {work_id}'s included")
    if "touched_in_scope" in reasons:
        why.append(f"{other} has already changed {_some(c['touched_in_scope'])}, inside {work_id}'s scope "
                   f"{', '.join(scope)}")
    if "scopes_overlap" in reasons:
        pairs = [f"{a} with {b}" for a, b in c["scope_pairs"]]
        why.append(f"the two scopes can name the same files ({work_id}'s {_some(pairs)} of {other}'s)")
    waits = (f"{work_id} waits until {other} is integrated or cancelled, either of which releases its "
             "workspace")
    if "paths_unknown" in reasons:
        waits += f", or until {other}'s workspace can be read"
    if "scope_unbounded" in reasons:
        waits += f"; to run beside {other}, {work_id} needs a scope that avoids {other}'s files"
    elif "scopes_overlap" in reasons or "touched_in_scope" in reasons:
        waits += "; to run them at once, split the work so their scopes cannot meet"
    return f"{head}, and " + "; ".join(why) + f". {waits}."
