"""A ``StageResult`` as the MCP ``text`` block: short for a person, whole for the Lead (E121; ITEMS 53).

OpenCode 2.0.18 shows a person this text and never ``structuredContent``: nothing while the tool's row is closed, and
all of it when the row is opened, with the view pinned to the bottom, so a tall row lands on its last lines
(``routes/session/index.tsx:2551-2601``; watched on the pinned TUI, 2026-11-04). Its model reads the same text and
nothing else (``core/src/session/runner/to-llm-message.ts:125-139``). The operator's measure, 2026-11-04: a person has
to take in what happened at the speed the Lead works. So the text is, in order:

* the head: the outcome, the next step, what happened, and only what holds the work up. An outcome says what the call
  got: a wait says how its run ended, or that it timed out, and ``done`` is said only of a call with no run status;
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

from aew.harness.contract import WAIT_RULE, redact, wake_step
from aew.surface import contract
from aew.surface.scrubbing import scrub

ROW = 72  # the columns the TUI gives a tool's output in a 130-column terminal, beside its sidebar (watched, 2026-11-04)
ROWS = 3  # a value takes at most this many, so one long value cannot fill the view: room for why a call stopped, or a
#           hint (one ran to five rows, 362 characters, in the sizing corpus); the JSON keeps all of it
WHY_ROWS = 2 * ROWS  # the reason, up to this many rows, when the outcome line had to shorten it
# What the content needs: the longest stage's steps, from the catalog. Only a stage repeating steps per card goes past
# it; such a list keeps this many lines and says how many it left out. The other lists below the head borrow the number:
# none has a catalog of its own, and a list longer than a stage's steps is not read at the Lead's speed. All are in the
# JSON.
MAX_LISTED = max(len(t.expands_to) for t in contract.TOOLS.values())
CUT_BYTES = 50 * 1024  # OpenCode's cut (`core/src/tool-output.ts:14`): over it, the JSON's line does not arrive
JSON_MARKER = "For the Lead, the result as JSON on the next line."
# Only a text over the cut says how to reach the rest, so that no other call pays for it. `read` clamps a line to 2,000
# characters (`core/src/tool/read-filesystem.ts:18, 327`), and `for_the_lead` starts the line with what it acts on.
JSON_OVER_THE_CUT = (f"{JSON_MARKER} It is over OpenCode's {CUT_BYTES // 1024} KiB: if it is missing below, OpenCode's "
                     "note names the file holding it. OpenCode's `read` shows 2,000 characters of a line, which start "
                     "with the stop and the projection; the shell reads the rest.")
# Top-level fields no Lead call takes and no guide, role text, hint or refusal asks it to quote (E121's sweep): the
# surface's constant, the two operation classes, and the policy digests the runner already bound. `structuredContent`
# keeps them. A field not named here stays, so a new field reaches the Lead by default.
_NOT_ACTED_ON = frozenset({"surface", "base_operation_class", "effective_operation_class", "policy_binding"})
_LEAD_READS_FIRST = ("ok", "tool", "revision", "generation", "stage_intent_id", "stopped", "projection")
# The payload's digests, by the field that holds one: no tool input or CLI flag takes them, and they cost a mean of 87
# tokens a call in the sizing corpus. A digest under any other name stays, so a new one (a stored map's root, say, which
# `aew map --root` does take) reaches the Lead by default.
_DIGEST_FIELDS = frozenset({"sha256", "record_sha256", "legality_digest", "operational_digest", "gates", "guardrails",
                            "checks"})
_DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_NOT_A_NEXT_STEP = ("query", "wait")
_BREAKS = ("Cc", "Zl", "Zp")  # a control character or a line separator: a space, so the words either side stay apart


def render(result: dict[str, Any]) -> str:
    """The ``text`` block for one result."""
    shown = scrub(result)
    ending = [_outcome(shown), _next(shown)]
    capabilities = _capability_summary(shown)
    body = [line for section in _SECTIONS for line in section(shown)]
    lead = json.dumps(for_the_lead(shown), separators=(",", ":"))

    def text(marker: str) -> str:
        return "\n".join([*ending, *capabilities, *_steps(shown), *body, "", marker, lead, "", *capabilities, *ending])

    return text(JSON_MARKER) if len(text(JSON_MARKER).encode()) <= CUT_BYTES else text(JSON_OVER_THE_CUT)


def for_the_lead(result: dict[str, Any]) -> dict[str, Any]:
    """The result without what no Lead call takes, what it acts on first. It leaves the projection and the stop whole,
    so a digest there stays. In the payload a named field holding a digest goes, except under ``arguments``, which a
    call may be made from."""
    kept = {k: v for k, v in result.items() if k not in _NOT_ACTED_ON}
    if "completed_steps" in kept:
        kept["completed_steps"] = [{k: v for k, v in s.items() if k != "operation_class"}
                                   for s in kept["completed_steps"]]
    if isinstance(kept.get("result"), dict):
        kept["result"] = _without_digests(kept["result"])
    return {**{k: kept[k] for k in _LEAD_READS_FIRST if k in kept}, **kept}


def _without_digests(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: v if k == "arguments" else _without_digests(v) for k, v in value.items()
                if not (k in _DIGEST_FIELDS and isinstance(v, str) and _DIGEST.fullmatch(v))}
    if isinstance(value, list):
        return [_without_digests(v) for v in value]
    return value


def _one_line(value: Any, rows: int | None = ROWS) -> str:
    """``value`` on one line, as it will be shown, shortened to what wraps to ``rows`` (``None``: never, for a call or a
    command that must run as printed). Authored text can hold anything: a line break or a terminal control in it would
    forge a line of this text or reach the person's terminal raw (JSON used to escape them), and a fenced command some
    messages end in would not run on one line. The JSON has all of it."""
    words = str(value) if rows is None else str(value).split("```", 1)[0]
    words = " ".join("".join(" " if unicodedata.category(c) in _BREAKS else "" if unicodedata.category(c)[0] == "C"
                             else c for c in words).split())
    text = redact(words)
    wrapped = textwrap.wrap(text, ROW)
    if rows is None or len(wrapped) <= rows:
        return text
    kept = text[:sum(len(line) for line in wrapped[:rows]) + rows - 2].rstrip()
    if kept.count("`") % 2:  # half of a printed command would read as a whole one
        kept = kept[:kept.rindex("`")].rstrip(" `")
    return kept + "…"


def _projection(result: dict[str, Any]) -> dict[str, Any]:
    return result.get("projection") or {}


def _outcome(result: dict[str, Any]) -> str:
    tool, stopped = result.get("tool"), result.get("stopped")
    if stopped:
        error = stopped.get("error") or {}
        return _one_line(f"{tool}: stopped at {stopped.get('at')} ({stopped.get('boundary')}): "
                         f"{error.get('message')}")
    payload = _payload(result)
    if payload.get("headline"):  # the engine's own first line for a run that ended without its output (register U8)
        return _one_line(f"{tool}: {payload['headline']}")
    if payload.get("timed_out"):
        runs = payload.get("statuses") or {payload.get("run"): payload.get("status")}
        return _one_line(f"{tool}: timed out: " + ", ".join(f"{run} still {status}" for run, status in runs.items()))
    if payload.get("triggers"):  # a run that still works and needs the Lead (steering PR 1)
        return _one_line(f"{tool}: {payload.get('run')} needs you: " + ", ".join(payload.get("why") or []))
    if payload.get("run") and payload.get("status"):  # how the run ended, which `done` would misstate
        why = (payload.get("ended_by") or {}).get("reason")  # the run's own record may still show it running
        return _one_line(f"{tool}: {payload['run']}: {why}" if why else f"{tool}: {payload['run']} {payload['status']}")
    projection = _projection(result)
    where = ": ".join(str(v) for v in (projection.get("subject"), projection.get("state")) if v)
    return _one_line(f"{tool}: done" + (f" ({where})" if where else ""))


def _payload(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("result")
    return payload if isinstance(payload, dict) else {}


def _command(argv: list[str]) -> str:
    """An argv the projection offers, as a reader runs it (``tests/helpers/printed_commands.py`` parses it so)."""
    return "aew " + shlex.join(argv[1:] if argv[0] == "aew" else argv)


def _call(name: Any, arguments: Any) -> str:
    fields = (f"{k}={json.dumps(v) if isinstance(v, dict | list) else v}" for k, v in (arguments or {}).items())
    return " ".join([str(name), *fields])


def _next(result: dict[str, Any]) -> str:
    """The one next step: what the engine says follows this call, or what the projection offers, in order a decision
    that is the Lead's, an action that moves the work, a wait, the engine's own hint, or what blocks it. A call or a
    printed command is never shortened: it must run as printed."""
    projection = _projection(result)
    scope = _scope(result)
    if _payload(result).get("next_action"):
        return _one_line(f"next: {_payload(result)['next_action']}")
    for decision in projection.get("decisions_required") or []:
        if decision.get("availability") == "AVAILABLE":
            what = f"decide {_one_line(decision.get('decision'))} on {_one_line(decision.get('subject'))}"
            if decision.get("tool"):
                return f"{what}: " + _whole(_call(decision["tool"], decision.get("arguments")))
            return f"{what}: " + _whole(_command(decision["cli_fallback"])) if decision.get("cli_fallback") else what
    offered = [a for a in projection.get("actions") or [] if a.get("availability") == "AVAILABLE"]
    for action in [a for a in offered if a.get("kind") not in _NOT_A_NEXT_STEP] or \
            [a for a in offered if a.get("kind") == "wait"]:
        if action.get("woken"):
            return _one_line(f"next: {wake_step(action['arguments']['runs'])}")
        label = "next" if action.get("kind") == "wait" else f"next{scope}"  # a wait's arguments name its own runs
        rule = f" ({WAIT_RULE})" if action.get("kind") == "wait" else ""  # how a wait is followed (E122)
        if action.get("callable"):
            return f"{label}: " + _whole(_call(action.get("action"), action.get("arguments"))) + rule
        if action.get("cli_fallback"):
            return f"{label}: " + _whole(_command(action["cli_fallback"])) + rule
    for hint in projection.get("hints") or []:
        return _one_line(f"next{scope}: {hint}")
    for blocker in projection.get("blockers") or []:
        return _one_line(f"blocked{scope}: {blocker.get('code')}: {blocker.get('message')}")
    return f"next{scope}: nothing offered"


def _scope(result: dict[str, Any]) -> str:
    """What a project-level projection offers is said to be the project's. A stopped call's projection is always one
    (``surface/run.py``, ``_run_tool``), and so is a wait's: its first hint must not read as the way on from it."""
    return " for the project" if _projection(result).get("subject") == "project" else ""


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
    """The reason, up to ``WHY_ROWS``, only when the outcome line had to shorten it."""
    stopped = result.get("stopped")
    message = _one_line(((stopped or {}).get("error") or {}).get("message"), WHY_ROWS)
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
    return [*_listed("decision", decisions), *_listed(f"blocker{_scope(result)}", problems),
            *_listed("anomaly", anomalies), *_listed("run", runs)]


def _capability_runs(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Recorded lists only: status's run rows, wait's per-run collection, and the older single-run wait shape.

    A wait repeats its ended run at the top level: project it once, without counting it twice. Never read progress
    digests as capability facts, nor guess from the projection's liveness rows.
    """
    payload = _payload(result)
    nested = payload.get("run_capabilities")
    runs = {r: entry for r, entry in nested.items() if isinstance(entry, dict)} if isinstance(nested, dict) else {}
    rows = payload.get("runs")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("run"), str):
                runs.setdefault(row["run"], row)
    if isinstance(payload.get("run"), str):
        runs.setdefault(payload["run"], payload)
    return {r: entry for r, entry in runs.items() if any(_capability_items(entry, field)
            for field in ("missing_tools", "missing_skills"))}


def _capability_items(entry: dict[str, Any], field: str) -> list[dict[str, Any]]:
    items = entry.get(field)
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _capability_summary(result: dict[str, Any]) -> list[str]:
    runs = _capability_runs(result)
    if not runs:
        return []
    tools = sum(len(_capability_items(entry, "missing_tools")) for entry in runs.values())
    skills = sum(len(_capability_items(entry, "missing_skills")) for entry in runs.values())
    return [f"Missing run capabilities (advisory): tools: {tools}; skills: {skills}; runs: {len(runs)}."]


def _capabilities(result: dict[str, Any]) -> list[str]:
    """Reasons and attribution before the JSON cut. Bound each category across all runs, not once per run; the
    summary counts the whole collection and is repeated where the view lands. Full lists stay in the JSON.
    """
    runs = _capability_runs(result)
    tools, skills = [], []
    for run, entry in runs.items():
        who = _one_line(run, 1)
        tools.extend(f"{who}: {_one_line(t.get('command'), 1)}; got {_one_line(t.get('got'), 1)}; "
                     f"{_one_line(t.get('why'), 1)}" for t in _capability_items(entry, "missing_tools"))
        skills.extend(f"{who}: {_one_line(s.get('name'), 1)}; {_one_line(s.get('reason'), 1)}"
                      for s in _capability_items(entry, "missing_skills"))
    return [*_listed("missing tool", tools), *_listed("missing skill", skills)]


_SECTIONS: tuple[Callable[[dict[str, Any]], list[str]], ...] = (_capabilities, _stopped, _waiting)
