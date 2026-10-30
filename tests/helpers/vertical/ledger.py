"""The burden ledger of the vertical UAT, spec v2 (docs/implementation/vertical-uat.md, "The burden ledger").

One entry per counted event, each with its evidence (the exact input or call, credentials redacted). The counters,
their thresholds and the hard limits are pinned here; ``tests/unit/test_vertical_ledger.py`` checks that they equal
the tables in ``vertical-uat.md``, so a threshold changes only with that document (which needs the operator).

The ledger also lists the operator's decisions (every question put to the operator, with the answer), the hard-limit
results (each kept apart as "did not refuse", a safety regression, or "refused without naming", an explanation gap),
and observations: setup steps that are not counted, the gaps a fallback covered, and facts a reviewer needs.

Classification lives here, in one place: the actors only report what they typed or called.

Spec v2 (the operator's approval of the amendments, Q8, 2026-10-11) adds: decisions by owner (only operator-owned
ones, or ones whose owner is not stated, are the operator's); two operator counters, the PIN entered again in one
endpoint's lifetime and a per-action console challenge on Windows; the Lead's containment label, with per-platform
minimums that only ratchet up; and Windows outside the enforced gate, its unqualified state leading every verdict and
summary it prints (the operator, Q1(e)).

The PIN rule is the operator's decision of 2026-10-24 (F1), landed with V-01's oracle (STG-13): every PIN entry is
recorded with its step and the named action it confirms. One that confirms a named action, within the scenario's
budget (one per G3-protected step on its path, ``vertical.oracle.pin_budget``), is an approval, listed apart from the
decisions; one that confirms no named action, or goes over the budget, is counted. "Authenticate at most once" counts
AEW's own sign-ins (the startup unlock, the website login). The ledger also records each step's derived state.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Shadow: the CI job runs and uploads the ledger on every pull request and on main, and is not in `assurance`'s
# required set. Flipping it to "enforce" is the operator's decision, made when the job is green (vertical-uat.md).
VERTICAL_MODE = "shadow"
VERTICAL_MODES = ("shadow", "enforce")

OPERATOR_COUNTERS = ("credentials", "env_vars", "raw_yaml", "revisions", "generations", "invocation_ids", "run_ids",
                     "takeovers", "seat_operations", "lifecycle_steps", "manifest_adopts", "pin_reentries",
                     "windows_console_challenges")
LEAD_COUNTERS = ("help_calls", "guessed_commands", "cli_tool_calls", "shell_aew_calls", "ambiguous_next_action",
                 "revision_args", "stale_retries", "refusals", "mechanical_calls")
COUNTERS = OPERATOR_COUNTERS + LEAD_COUNTERS
# Every counter must be 0. `mechanical_calls` is defined "with steering on": a steering-off run counts the Lead's
# mechanical calls as its measurement, and only a steering-on run is held to 0 (vertical-uat.md).
THRESHOLDS: dict[str, int] = {c: 0 for c in COUNTERS}
STEERING_ONLY = frozenset({"mechanical_calls"})
# V1's operator decisions, exactly: approving the plan and approving the publish (publish stays a judgement unless a
# grant covers it). Any other question fails the comparison and is reviewed by hand.
V1_DECISIONS = ("plan", "publish")
# Whose decision it is, as the projection states it (spec v2): `decisions_required` counts operator-owned decisions
# only. The scripted Lead puts to the operator only a decision the projection gives to the operator, or one whose owner
# is not stated (every one, until the projection carries owners: today's behaviour, kept, and the summary says "owner
# not stated"). One owned by the Lead or the mechanism it takes itself; it is listed apart and never asked. Every
# question that does reach the operator is an operator decision and is compared, whatever owner it names.
OPERATOR_OWNER, OWNER_NOT_STATED = "operator", "not stated"
# The only owners the Lead takes a decision for. Any other stated owner (a new value, a case variant, an empty
# string) is asked of the operator and compared like any other question, and is recorded as a finding
# (`lead.unknown_owner`): an unrecognised owner never lets a decision leave the comparison (review of #213, F2).
SELF_OWNERS = frozenset({"lead", "mechanical"})
HARD_LIMITS = ("semantic_conflict", "evidence_mismatch", "publish_needs_decision", "containment")
# Publish (spec v2, from the operator's Q3 answer): from B1, the limit also checks that the publish record is
# console-approved and attributed to the operator. Until B1 builds that channel the limit stays "main moved only after
# the operator's yes", and this stays False; B1 flips it together with the check (vertical-uat.md, the hard limits).
PUBLISH_CONSOLE_ATTRIBUTION = False

# Containment (spec v2): every run's label and the Lead's, each at or above its platform's minimum. The order runs from
# weakest to strongest; `None` is no label recorded. Since CS-4 (#283) the Lead's session records its label on both
# platforms, and the Lead's minimums are still `None` until the operator raises them. The minimums only ratchet up:
# `tests/unit/test_vertical_ledger.py` pins every earlier value and fails if one is ever lowered.
LABEL_ORDER: tuple[str | None, ...] = (None, "workdir_separation_only", "os_readonly_roots")
WORKERS, LEAD = "workers", "lead"
CONTAINMENT_MINIMUM: dict[str, dict[str, str | None]] = {
    "linux": {WORKERS: "os_readonly_roots", LEAD: None},
    "win32": {WORKERS: "workdir_separation_only", LEAD: None},
}

# Windows is outside the enforced gate (the operator, Q1(e); temporary). Its job keeps running and reporting, and
# every verdict and summary it prints leads with this line and the conditions still open. Lifting it is the
# operator's decision.
ENFORCED_PLATFORMS = ("linux",)
WINDOWS_UNQUALIFIED = "Windows: UNQUALIFIED (excluded from the enforced gate)"
WINDOWS_OPEN_CONDITIONS = ("B5q, the Low-integrity Lead qualification",
                           "B5 (or B5b), the MIC backend for the workers and the Lead",
                           "the isolation the designer required in 1(g), closing residuals (a) to (d)")
# Hard-limit outcomes. Every one but `held` fails the test; the ledger keeps them apart: `did_not_refuse` is a safety
# regression (the protected action went ahead), `refused_without_naming` an explanation gap, `rebuilt_not_published` a
# conflicting change AEW carried on with (rebuilt and re-verifying) instead of refusing, and `not_exercised` a limit
# whose step the run never reached (no run, no publish, no check): never scored as a safety regression.
HELD, NOT_REFUSED, UNNAMED = "held", "did_not_refuse", "refused_without_naming"
REBUILT, NOT_EXERCISED = "rebuilt_not_published", "not_exercised"
OUTCOMES = (HELD, NOT_REFUSED, UNNAMED, REBUILT, NOT_EXERCISED)

CREDENTIAL = re.compile(r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}")
INVOCATION_ID = re.compile(r"\bINV-\d{4,}\b")
RUN_ID = re.compile(r"\bR-INV-\d{4,}-\d+\b")
GENERATION = re.compile(r"--generation\b|\bgeneration\s*[:=]?\s*\d+", re.IGNORECASE)
REVISION = re.compile(r"--expect-rev\b|\bexpect_rev\b|\brevision\s*[:=]?\s*\d+", re.IGNORECASE)

# Operator commands by the counter they fall under (the words after `aew`, flags excluded).
SEAT_COMMANDS = (("lead", "acquire"), ("lead", "release"), ("lead", "reacquire"), ("opencode", "--acquire"))
TAKEOVER_COMMANDS = (("lead", "takeover"),)
ADOPT_COMMANDS = (("manifest", "adopt"),)
LIFECYCLE_COMMANDS = (("work",), ("plan",), ("invoke",), ("review",), ("verify",), ("integrate",), ("evidence",),
                      ("harness", "launch"), ("checkpoint",), ("stage",))
# Lead tools: reading the projection is the policy's own first step, never a guess.
PROJECTION_READS = frozenset({"status", "resume"})
HELP_TOOLS = frozenset({"explain"})
WAIT_TOOLS = frozenset({"harness_wait"})


def redact(text: str) -> str:
    return CREDENTIAL.sub("<credential>", text)


def _words(argv: list[str]) -> tuple[str, ...]:
    return tuple(a for a in argv if not a.startswith("-") or a == "--acquire")


def _starts(words: tuple[str, ...], prefixes: tuple[tuple[str, ...], ...]) -> bool:
    return any(words[:len(p)] == p for p in prefixes)


def enforce_blockers(*, lead_label_wired: bool) -> list[str]:
    """Why ``VERTICAL_MODE`` may not be ``enforce`` yet (vertical-uat.md §5; review of #213, F1): the gate cannot be
    enforced while an enforced platform's Lead minimum is no label, which holds no Lead to any containment. Each
    enforced platform needs a Lead minimum above "no label" (the operator's to raise), and the test must read the
    Lead's label from the product (``scripted_operator.lead_label``), never assume one."""
    out = [f"{p}: the Lead's containment minimum is no label (it holds the Lead to nothing)"
           for p in ENFORCED_PLATFORMS if CONTAINMENT_MINIMUM[p][LEAD] is None]
    if not lead_label_wired:
        out.append("the Lead's label is not read from the product (scripted_operator.lead_label)")
    return out


# A readiness report's statuses (doctor's, and preflight's when it exists). A line's status is the first of these words
# on it: the status column comes before the detail, so a PASS line whose detail says "INFO" or "FAIL" is still PASS.
STATUS = re.compile(r"\b(PASS|WARN|FAIL|INFO|UNAVAILABLE)\b")
FAILING = frozenset({"FAIL", "WARN"})
# Faults of the test's own harness (the chat between the scripted actors), recorded apart from AEW's behaviour.
HARNESS_FAULTS = frozenset({"chat_read_error", "lead.listener_error"})
# The Lead went silent, ended, or lost a thread (`thread_died`: recorded by childdiag's exception hook, G3 H1).
LEAD_ENDINGS = ("lead_silent", "lead.lead_error", "lead.thread_died")


def _json_objects(text: str) -> tuple[list[dict[str, Any]], str]:
    """The JSON objects in ``text`` that start a line (the CLI's answers), and the text left without them."""
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    rest: list[str] = []
    i = 0
    while i < len(text):
        end = text.find("\n", i)
        end = len(text) if end == -1 else end + 1
        if text[i:end].lstrip().startswith("{"):
            start = i + len(text[i:end]) - len(text[i:end].lstrip())
            try:
                value, stop = decoder.raw_decode(text, start)
            except ValueError:
                value, stop = None, end
            if isinstance(value, dict):
                found.append(value)
                nl = text.find("\n", stop)
                i = len(text) if nl == -1 else nl + 1
                continue
        rest.append(text[i:end])
        i = end
    return found, "".join(rest)


def failing_entries(text: str) -> list[str]:
    """The FAIL and WARN entries of a readiness report. In a table, each line whose status is FAIL or WARN, with the
    lines after it that carry no status of their own (a wrapped detail, a fix on the next line). A PASS or INFO entry is
    never one, even when it echoes the configured value a cause names (review of #213, F4).

    In JSON (review of #213, F6 and G1): an answer with ``ok: true`` never counts, whatever it echoes. Otherwise every
    ``error`` object (the CLI's refusal, ``{"ok": false, "error": {code, message, details}}``) is one failing entry, its
    code, message and details; and every object with a ``status`` (a report's check, doctor's ``{check, status,
    detail}``) is one entry with that object's own status, failing only when it is FAIL or WARN. ``ok: false`` with
    neither adds nothing: it is never an empty error."""
    out: list[str] = []
    objects, table = _json_objects(text)
    for obj in objects:
        if obj.get("ok") is not True:
            out += _json_entries(obj)
    return out + _table_entries(table)


def _json_entries(value: Any) -> list[str]:
    """Each failing entry in a JSON value: its ``error`` objects and its FAIL or WARN ``status`` objects, anywhere."""
    out: list[str] = []
    if isinstance(value, dict):
        error = value.get("error")
        if isinstance(error, dict):
            out.append("\n".join([str(error.get("code") or ""), str(error.get("message") or ""),
                                  json.dumps(error.get("details") or {}, sort_keys=True)]))
        status = value.get("status")
        if isinstance(status, str) and status.upper() in FAILING:
            # The object's own fields only: a nested check (say, a PASS one echoing the id) is its own entry.
            out.append(json.dumps({k: v for k, v in value.items() if not isinstance(v, (dict, list))}, sort_keys=True))
        for k, v in value.items():
            if k != "error":
                out += _json_entries(v)
    elif isinstance(value, list):
        for v in value:
            out += _json_entries(v)
    return out


def _table_entries(text: str) -> list[str]:
    """The status-word rule: each FAIL or WARN line with its continuation lines (no status of their own)."""
    out: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        status = STATUS.search(line)
        if status is not None:
            if current is not None:
                out.append("\n".join(current))
            current = [line] if status.group(1) in FAILING else None
        elif current is not None:
            current.append(line)
    if current is not None:
        out.append("\n".join(current))
    return out


def diagnoses(text: str, pattern: str) -> bool:
    """Whether a FAIL or WARN entry of ``text`` names ``pattern`` (a cause, or its fix)."""
    return any(re.search(pattern, entry) for entry in failing_entries(text))


def at_least(label: str | None, minimum: str | None) -> bool:
    """Whether ``label`` is at or above ``minimum`` in :data:`LABEL_ORDER` (a label outside the order is below all)."""
    if label not in LABEL_ORDER:
        return False
    return LABEL_ORDER.index(label) >= LABEL_ORDER.index(minimum)


def windows_lines() -> list[str]:
    """What every verdict and summary on Windows leads with (Q1(e)): the state, then the conditions still open."""
    return [WINDOWS_UNQUALIFIED, "  open conditions: " + "; ".join(WINDOWS_OPEN_CONDITIONS)]


def owner_of(decision: dict[str, Any]) -> str:
    return str((decision.get("detail") or {}).get("owner") or OWNER_NOT_STATED)


class Ledger:
    def __init__(self, scenario: str, *, steering: bool = False, platform: str | None = None,
                 pin_budget: int = 0) -> None:
        self.scenario = scenario
        self.steering = steering
        self.platform = platform or ("win32" if sys.platform == "win32" else "linux")
        self.pin_budget = pin_budget  # one per G3-protected step on the scenario's path (vertical.oracle.pin_budget)
        self.entries: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []  # PINs that confirmed a named action within the budget
        self.sign_ins: list[dict[str, Any]] = []  # AEW's own sign-ins (the startup unlock, the website login)
        self.steps: list[dict[str, Any]] = []  # each step of the path with its derived state (vertical.oracle)
        self.decisions: list[dict[str, Any]] = []
        self.hard_limits: dict[str, dict[str, Any]] = {}
        self.observations: list[dict[str, Any]] = []
        self.seq = 0

    # ------------------------------------------------------------------ recording

    def _next(self) -> int:
        self.seq += 1
        return self.seq

    def count(self, counter: str, evidence: Any, *, actor: str, note: str = "", step: str = "") -> None:
        if counter not in COUNTERS:
            raise ValueError(f"unknown counter {counter}")
        self.entries.append({"seq": self._next(), "counter": counter, "actor": actor, "step": step,
                             "evidence": json.loads(redact(json.dumps(evidence))), "note": note})

    def observe(self, kind: str, **facts: Any) -> None:
        self.observations.append({"seq": self._next(), "kind": kind, **json.loads(redact(json.dumps(facts)))})

    def decision(self, question: str, answer: str, *, label: str, asked_by: str, detail: Any = None) -> None:
        self.decisions.append({"seq": self._next(), "label": label, "asked_by": asked_by,
                               "question": redact(question), "answer": answer,
                               "detail": json.loads(redact(json.dumps(detail)))})

    def hard_limit(self, name: str, outcome: str, **evidence: Any) -> None:
        if name not in HARD_LIMITS or outcome not in OUTCOMES:
            raise ValueError(f"hard limit {name}: {outcome}")
        self.hard_limits[name] = {"outcome": outcome, **json.loads(redact(json.dumps(evidence)))}

    # ------------------------------------------------------------------ classification

    def pin_entered(self, *, step: str, action: str | None) -> None:
        """The operator typed the PIN at the confirmer, at ``step``, confirming ``action`` (the operator's decision of
        2026-10-24, F1). A PIN that confirms a named action, within the scenario's budget, is an approval: listed
        apart from the decisions, never counted. One that confirms no named action, or goes over the budget, is
        counted (``pin_reentries``). Never under ``credentials``: the PIN is the operator's own secret, not an AEW
        credential (spec v2)."""
        entry = {"step": step, "action": action}
        if not action:
            self.count("pin_reentries", entry, actor="operator", step=step, note="a PIN that confirms no named action")
        elif len(self.approvals) >= self.pin_budget:
            self.count("pin_reentries", {**entry, "budget": self.pin_budget}, actor="operator", step=step,
                       note="a PIN over the scenario's budget")
        else:
            self.approvals.append({"seq": self._next(), **entry})

    def sign_in(self, kind: str, *, step: str) -> None:
        """One of AEW's own sign-ins (``kind``: the startup unlock, the website login). "Authenticate at most once":
        the first is recorded; every further one is counted (``pin_reentries``)."""
        self.sign_ins.append({"seq": self._next(), "kind": kind, "step": step})
        if len(self.sign_ins) > 1:
            self.count("pin_reentries", {"sign_in": kind, "entry": len(self.sign_ins)}, actor="operator", step=step,
                       note="a sign-in beyond the once")

    def console_challenge(self, operation: str, *, step: str) -> None:
        """A per-action challenge at the operator console (a one-time code typed back at the requesting terminal) that
        stands in for "authenticate once": an operator-principal operation that is not a decision (configure, open).
        On Windows it is ``windows_console_challenges`` (spec v2). On Linux it confirms no named action, so it is
        counted under ``pin_reentries`` (the PIN rule). A decision confirmed at the console (the steering raise, every
        Q9 item) is a decision on every platform and never comes here."""
        evidence = {"operation": operation}
        if self.platform == "win32":
            self.count("windows_console_challenges", evidence, actor="operator", step=step)
        else:
            self.count("pin_reentries", evidence, actor="operator", step=step,
                       note="a per-action console challenge on Linux: authentication beyond the once")

    def operator_input(self, text: str, *, step: str, argv: list[str] | None = None, shown: str = "") -> None:
        """One thing the operator typed (a command line, or a chat line to the Lead), and what it showed them."""
        evidence = {"input": text}
        if CREDENTIAL.search(text):
            self.count("credentials", evidence, actor="operator", step=step, note="a credential in the input")
        if CREDENTIAL.search(shown):
            self.count("credentials", {**evidence, "shown": "a credential"}, actor="operator", step=step,
                       note="a credential shown to the operator")
        if REVISION.search(text):
            self.count("revisions", evidence, actor="operator", step=step)
        if GENERATION.search(text):
            self.count("generations", evidence, actor="operator", step=step)
        if RUN_ID.search(text):
            self.count("run_ids", evidence, actor="operator", step=step)
        elif INVOCATION_ID.search(text):
            self.count("invocation_ids", evidence, actor="operator", step=step)
        if argv is None:
            return
        words = _words(argv)
        if _starts(words, SEAT_COMMANDS) or (words[:1] == ("opencode",) and "--acquire" in argv):
            self.count("seat_operations", evidence, actor="operator", step=step)
        if _starts(words, TAKEOVER_COMMANDS):
            self.count("takeovers", evidence, actor="operator", step=step)
        if _starts(words, ADOPT_COMMANDS):
            self.count("manifest_adopts", evidence, actor="operator", step=step)
        if _starts(words, LIFECYCLE_COMMANDS):
            self.count("lifecycle_steps", evidence, actor="operator", step=step)

    def lead_event(self, event: dict[str, Any]) -> None:
        """One event from the scripted Lead's own accounting (the ground truth for its calls, spec §4)."""
        kind = event.get("kind")
        if kind == "call":
            self._lead_call(event)
        elif kind == "ambiguous":
            self.count("ambiguous_next_action", {"available": event.get("available")}, actor="lead",
                       step=event.get("step", ""))
        elif kind == "stale_retry":
            self.count("stale_retries", event.get("evidence"), actor="lead", step=event.get("step", ""))
        else:
            self.observe(f"lead.{kind}", **{k: v for k, v in event.items() if k != "kind"})

    def _lead_call(self, e: dict[str, Any]) -> None:
        via, tool, args = e["via"], e.get("tool"), e.get("arguments")
        evidence = {"via": via, "tool": tool, "arguments": args}
        step = e.get("step", "")
        flat = json.dumps(args)
        if via == "shell":
            self.count("shell_aew_calls", evidence, actor="lead", step=step, note=e.get("why", ""))
            if "--help" in (args or []):
                self.count("help_calls", evidence, actor="lead", step=step)
        elif tool == "cli":
            self.count("cli_tool_calls", evidence, actor="lead", step=step, note=e.get("why", ""))
        elif tool in HELP_TOOLS:
            self.count("help_calls", evidence, actor="lead", step=step, note=e.get("why", ""))
        elif tool not in PROJECTION_READS and not e.get("offered"):
            self.count("guessed_commands", evidence, actor="lead", step=step, note=e.get("why", ""))
        if "expect_rev" in flat or "--expect-rev" in flat:
            self.count("revision_args", evidence, actor="lead", step=step,
                       note="supplied by the projection" if e.get("offered") else "")
        if e.get("ok") is False:
            self.count("refusals", {**evidence, "stopped": e.get("stopped")}, actor="lead", step=step)
        if e.get("mechanical"):
            self.count("mechanical_calls", evidence, actor="lead", step=step,
                       note="steering on" if self.steering else "steering off: measured, not held to 0")

    # ------------------------------------------------------------------ results

    def operator_fallbacks(self) -> list[dict[str, Any]]:
        """Every workaround the operator fell back to. Any one fails the verdict, whether or not a counter classifies
        it (a fallback no counter sees must not let the zeros pass)."""
        return [o for o in self.observations if o["kind"] == "fallback"]

    def not_the_operators(self) -> list[dict[str, Any]]:
        """The decisions the projection gave to the Lead or the mechanism, which the scripted Lead took itself and
        never put to the operator (spec v2): listed apart, never among the operator's decisions."""
        return [o for o in self.observations if o["kind"] == "lead.own_decision"]

    def enforced(self) -> bool:
        """Whether this platform is inside the enforced gate (Windows is not: Q1(e))."""
        return self.platform in ENFORCED_PLATFORMS

    def qualification(self) -> dict[str, Any]:
        if self.enforced():
            return {"platform": self.platform, "state": "in the enforced gate"}
        return {"platform": self.platform, "state": WINDOWS_UNQUALIFIED,
                "open_conditions": list(WINDOWS_OPEN_CONDITIONS)}

    def counts(self) -> dict[str, int]:
        out = {c: 0 for c in COUNTERS}
        for e in self.entries:
            out[e["counter"]] += 1
        return out

    def over(self) -> dict[str, int]:
        """The counters above their threshold (the zero assertions)."""
        found = self.counts()
        return {c: n for c, n in found.items() if n > THRESHOLDS[c] and (self.steering or c not in STEERING_ONLY)}

    def to_json(self) -> dict[str, Any]:
        return {"schema": "aew/vertical-ledger/v2", "scenario": self.scenario, "mode": VERTICAL_MODE,
                "platform": self.platform, "qualification": self.qualification(), "steering": self.steering,
                "counts": self.counts(),
                "thresholds": THRESHOLDS, "decisions": self.decisions, "pin_budget": self.pin_budget,
                "approvals": self.approvals, "sign_ins": self.sign_ins, "steps": self.steps,
                "hard_limits": self.hard_limits, "entries": self.entries, "observations": self.observations}

    def verdict_text(self, problems: list[str]) -> str:
        """A failed verdict as the test prints it: on Windows it leads with the unqualified state and the conditions
        still open (Q1(e)); then every problem, then the summary. The line is reported, never a problem of its own,
        and no problem is dropped on any platform."""
        lead = [] if self.enforced() else [*windows_lines(), ""]
        return "\n".join(lead + problems) + "\n\n" + self.summary()

    def summary(self) -> str:
        c = self.counts()
        others = self.not_the_operators()
        lines = [] if self.enforced() else windows_lines()
        lines += [f"vertical UAT {self.scenario} ({self.platform}, steering {'on' if self.steering else 'off'}, "
                  f"mode {VERTICAL_MODE})",
                  "operator: " + "  ".join(f"{k} {c[k]}" for k in OPERATOR_COUNTERS),
                  "lead:     " + "  ".join(f"{k} {c[k]}" for k in LEAD_COUNTERS),
                  "decisions: " + ("; ".join(decision_line(d) for d in self.decisions) or "none"),
                  f"approvals (PIN budget {self.pin_budget}): "
                  + ("; ".join(f"{a['step']} {a['action']}" for a in self.approvals) or "none")]
        if self.steps:  # each step of the path, as far as the code has built it (vertical.oracle)
            lines.append("steps: " + "; ".join(
                f"{s['step']} {s['state']}" + (f" [{', '.join(s['held_by'])}]" if s.get("held_by") else "")
                for s in self.steps)[:400])
        if others:
            lines.append("not the operator's: " + "; ".join(f"{o.get('decision')} [owner {o.get('owner')}]"
                                                             for o in others))
        unknown = [o for o in self.observations if o["kind"] == "lead.unknown_owner"]
        if unknown:  # a finding: asked of the operator and compared, but the owner is not one the spec names
            lines.append("unknown owners (asked of the operator): " + "; ".join(
                f"{o.get('decision')} [owner {o.get('owner')!r}]" for o in unknown))
        faults = [o for o in self.observations if o["kind"] in HARNESS_FAULTS
                  or (o["kind"] in LEAD_ENDINGS and o.get("fault") == "harness")]
        ended = [o for o in self.observations if o["kind"] in LEAD_ENDINGS and o.get("fault") != "harness"]
        if ended:  # the Lead went silent or ended, and nothing shows the harness at fault
            lines.append("lead silent or ended: " + "; ".join(
                f"{o['kind']} ({o.get('fault')}) {o.get('why') or o.get('error') or ''}".strip()
                for o in ended[:3])[:200])
        if faults:  # the test's own harness, never AEW's behaviour (review of #213, G2)
            lines.append("harness faults: " + "; ".join(
                f"{o['kind']} {o.get('waiting_for') or o.get('file') or ''} {o.get('error') or ''}".strip()
                for o in faults[:4])[:200])
        staled = [o for o in self.observations if o["kind"] == "stale_revision"]
        if staled:  # which actor's commit staled each STALE_REVISION the Lead met (the loop's, or another's)
            lines.append("stale revisions, staled by: " + "; ".join(
                f"{o.get('tool')} at {o.get('expect_rev')}: {o.get('op')}, {o.get('by')}" for o in staled))
        lines.append("operator fallbacks: " + (", ".join(o.get("step") or "?" for o in self.operator_fallbacks())
                                               or "none"))
        for name, r in sorted(self.hard_limits.items()):
            lines.append(f"hard limit {name}: {r['outcome']}")
        for o in self.observations:
            if o["kind"] == "steering_stop":
                lines.append(f"steering loop: mode {o.get('mode')}, stopped {(o.get('stop') or {}).get('code')}")
        gaps = [o for o in self.observations if o["kind"] in ("fallback", "lead.gap", "lead.stuck", "gap")]
        for o in gaps[:12]:
            what = o.get("why") or o.get("observed") or ""
            lines.append(f"  {o['kind']}: {o.get('step') or o.get('gap') or ''} {what}"[:118])
        return "\n".join(lines)

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_json(), indent=1)
        if CREDENTIAL.search(text):  # redacted on the way in; a credential in a written ledger is a defect here
            raise AssertionError("the ledger holds a credential")
        path = directory / "vertical-ledger.json"
        path.write_text(text + "\n", encoding="utf-8")
        (directory / "vertical-summary.txt").write_text(self.summary() + "\n", encoding="utf-8")
        return path


def decision_line(d: dict[str, Any]) -> str:
    """One decision as the summary shows it: what was asked, the tool its answer drives, whose decision the
    projection says it is ("not stated" until it carries owners: the test does not settle that), and the answer
    (bounded)."""
    tool = (d.get("detail") or {}).get("tool") or "-"
    return f"{d['label']} [drives {tool}; owner {owner_of(d)}] -> {str(d['answer'])[:40]}"
