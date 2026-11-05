"""A ``StageResult`` as the MCP ``text`` block: short for a person, whole for the Lead (E121; ITEMS 53).

OpenCode 2.0.18 shows a person this text and never ``structuredContent``: nothing while the tool's row is closed, and
all of it when the row is opened, with the view pinned to the bottom, so a tall row lands on its last lines
(``routes/session/index.tsx:2551-2601``; watched on the pinned TUI, 2026-11-04). Its model reads the same text and
nothing else (``core/src/session/runner/to-llm-message.ts:125-139``). The operator's measure, 2026-11-04: a person has
to take in what happened at the speed the Lead works. So the text is, in order:

* the head: the outcome, the next step, what happened, and only what holds the work up;
* the marked line and the result as JSON for the Lead, on one line, without what no Lead call takes
  (:func:`for_the_lead`);
* the outcome and the next step again, where the view lands.

Every value is put on one line here, so a value can never forge a line of this text, and OpenCode's cut, which keeps
whole lines up to 50 KiB and then says so (``core/src/tool-output.ts:13-14, 76-88``), takes the JSON and what follows it
and leaves the head. A result that was one line of JSON over 50 KiB reached person and model as OpenCode's note alone
(watched).

:func:`render` derives everything from the result, with no wording of its own beyond the labels. To add what a later
row needs a person to see, add a function to ``_SECTIONS``.
"""

from __future__ import annotations

import json
import re
import shlex
import textwrap
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any

from aew.surface import contract
from aew.surface.scrubbing import scrub

ROW = 72  # the columns the TUI gives a tool's output in a 130-column terminal, beside its sidebar (watched, 2026-11-04)
ROWS = 3  # a value takes at most this many, so one long value cannot fill the view: room for why a call stopped, or a
#           hint (one ran to five rows, 362 characters, in the sizing corpus); the JSON keeps all of it
WHY_ROWS = 2 * ROWS  # the whole reason, when the outcome line had to shorten it
# What the content needs: the longest stage's steps, from the catalog. Only a stage repeating steps per card goes past
# it; such a list, and any other, keeps this many lines and says how many it left out (all are in the JSON).
MAX_LISTED = max(len(t.expands_to) for t in contract.TOOLS.values())
JSON_MARKER = ("For the Lead, the result as JSON on the next line. If it is missing, OpenCode cut it: "
               "its note names the file holding it.")
# Top-level fields no Lead call takes and no guide, role text, hint or refusal asks it to quote (E121's sweep): the
# surface's constant, the two operation classes, and the policy digests the runner already bound. `structuredContent`
# keeps them. A field not named here stays, so a new field reaches the Lead by default.
_NOT_ACTED_ON = frozenset({"surface", "base_operation_class", "effective_operation_class", "policy_binding"})
_DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_NOT_A_NEXT_STEP = ("query", "wait")
_BREAKS = ("Cc", "Zl", "Zp")  # a control character or a line separator: a space, so the words either side stay apart


def render(result: dict[str, Any]) -> str:
    """The ``text`` block for one result."""
    shown = scrub(result)
    ending = [_outcome(shown), _next(shown)]
    body = [line for section in _SECTIONS for line in section(shown)]
    return "\n".join([*ending, *_steps(shown), *body, "", JSON_MARKER,
                      json.dumps(for_the_lead(shown), separators=(",", ":")), "", *ending])


def for_the_lead(result: dict[str, Any]) -> dict[str, Any]:
    """The result without what no Lead call takes. It leaves the projection and the stop whole: they are what the Lead
    acts on, so a digest there stays. In the payload a dict's digest value goes, except under ``arguments``, which a
    call may be made from; a list's items stay, since a list can hold the ids a decision binds."""
    kept = {k: v for k, v in result.items() if k not in _NOT_ACTED_ON}
    if "completed_steps" in kept:
        kept["completed_steps"] = [{k: v for k, v in s.items() if k != "operation_class"}
                                   for s in kept["completed_steps"]]
    if isinstance(kept.get("result"), dict):
        kept["result"] = _without_digests(kept["result"])
    return kept


def _without_digests(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: v if k == "arguments" else _without_digests(v) for k, v in value.items()
                if not (isinstance(v, str) and _DIGEST.fullmatch(v))}
    if isinstance(value, list):
        return [_without_digests(v) for v in value]
    return value


def _one_line(value: Any, rows: int | None = ROWS) -> str:
    """``value`` on one line, shortened to what wraps to ``rows`` (``None``: never): authored text can hold anything,
    and a line break or a terminal control in it would forge a line of this text or reach the person's terminal raw
    (JSON used to escape them)."""
    text = " ".join("".join(" " if unicodedata.category(c) in _BREAKS else "" if unicodedata.category(c)[0] == "C"
                            else c for c in str(value)).split())
    wrapped = textwrap.wrap(text, ROW)
    if rows is None or len(wrapped) <= rows:
        return text
    kept = text[:sum(len(line) for line in wrapped[:rows]) + rows - 2].rstrip()
    if kept.count("`") % 2:  # half of a printed command would read as a whole one; the JSON has all of it
        kept = kept[:kept.rindex("`")].rstrip()
    return kept + "…"


def _prose(message: Any) -> str:
    """A refusal's words without the fenced command some end in: on one line it would not run, and the JSON has it."""
    return str(message).split("```", 1)[0]


def _projection(result: dict[str, Any]) -> dict[str, Any]:
    return result.get("projection") or {}


def _outcome(result: dict[str, Any]) -> str:
    tool, stopped = result.get("tool"), result.get("stopped")
    if stopped:
        error = stopped.get("error") or {}
        return _one_line(f"{tool}: stopped at {stopped.get('at')} ({stopped.get('boundary')}): "
                         f"{_prose(error.get('message'))}")
    projection = _projection(result)
    where = ": ".join(str(v) for v in (projection.get("subject"), projection.get("state")) if v)
    return _one_line(f"{tool}: done" + (f" ({where})" if where else ""))


def _command(argv: list[str]) -> str:
    """An argv the projection offers, as a reader runs it (``tests/helpers/printed_commands.py`` parses it so)."""
    return "aew " + shlex.join(argv[1:] if argv[0] == "aew" else argv)


def _call(name: Any, arguments: Any) -> str:
    fields = (f"{k}={json.dumps(v) if isinstance(v, dict | list) else v}" for k, v in (arguments or {}).items())
    return " ".join([str(name), *fields])


def _next(result: dict[str, Any]) -> str:
    """The one next step the projection offers: a decision that is the Lead's, an action that moves the work, a wait,
    the engine's own hint, or what blocks it. A call or a printed command is never shortened: it must run as printed."""
    projection = _projection(result)
    for decision in projection.get("decisions_required") or []:
        if decision.get("availability") == "AVAILABLE":
            what = f"decide {_one_line(decision.get('decision'))} on {_one_line(decision.get('subject'))}"
            if decision.get("tool"):
                return f"{what}: " + _whole(_call(decision["tool"], decision.get("arguments")))
            return f"{what}: " + _whole(_command(decision["cli_fallback"])) if decision.get("cli_fallback") else what
    offered = [a for a in projection.get("actions") or [] if a.get("availability") == "AVAILABLE"]
    for action in [a for a in offered if a.get("kind") not in _NOT_A_NEXT_STEP] or \
            [a for a in offered if a.get("kind") == "wait"]:
        if action.get("callable"):
            return "next: " + _whole(_call(action.get("action"), action.get("arguments")))
        if action.get("cli_fallback"):
            return "next: " + _whole(_command(action["cli_fallback"]))
    for hint in projection.get("hints") or []:
        return _one_line(f"next: {hint}")
    for blocker in projection.get("blockers") or []:
        return _one_line(f"blocked: {blocker.get('code')}: {blocker.get('message')}")
    return "next: nothing offered"


def _whole(call: str) -> str:
    return _one_line(call, None)


def _steps(result: dict[str, Any]) -> list[str]:
    """What happened, latest last. A long list keeps its latest steps, the ones nearest the outcome."""
    summaries = [str(s.get("summary") or s.get("primitive")) for s in result.get("completed_steps") or []]
    left_out = len(summaries) - MAX_LISTED
    return [*([f"({left_out} earlier {'step' if left_out == 1 else 'steps'} left out)"] if left_out > 0 else []),
            *(f"- {_one_line(s)}" for s in summaries[-MAX_LISTED:])]


def _listed(label: str, items: Iterable[str]) -> list[str]:
    listed = list(items)
    more = len(listed) - MAX_LISTED
    return [*(f"{label}: {_one_line(i)}" for i in listed[:MAX_LISTED]),
            *([f"{label}: ({more} more left out)"] if more > 0 else [])]


def _stopped(result: dict[str, Any]) -> list[str]:
    """The whole reason, only when the outcome line had to shorten it."""
    stopped = result.get("stopped")
    message = _one_line(_prose(((stopped or {}).get("error") or {}).get("message")), WHY_ROWS)
    return [f"why: {message}"] if stopped and message not in _outcome(result) else []


def _waiting(result: dict[str, Any]) -> list[str]:
    """What holds the work up. Decisions are the Lead's or the operator's and have no default, so they are always
    named. Everything else a person can ask for is in the JSON: other actions, other hints, ids and states."""
    projection = _projection(result)
    decisions = [f"{d.get('decision')} on {d.get('subject')} ({d.get('availability')})"
                 for d in projection.get("decisions_required") or []]
    problems = [f"{b.get('code')}: {b.get('message')}" for b in projection.get("blockers") or []]
    anomalies = [f"{a.get('code')}: {a.get('message')}" for a in projection.get("anomalies") or []]
    runs = [f"{r.get('run')} {r.get('role')} {r.get('work_unit')}: {r.get('status')}"
            for r in projection.get("runs") or []]
    return [*_listed("decision", decisions), *_listed("blocker", problems), *_listed("anomaly", anomalies),
            *_listed("run", runs)]


_SECTIONS: tuple[Callable[[dict[str, Any]], list[str]], ...] = (_stopped, _waiting)
