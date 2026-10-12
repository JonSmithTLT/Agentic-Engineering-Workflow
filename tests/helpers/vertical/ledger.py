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
HARD_LIMITS = ("semantic_conflict", "evidence_mismatch", "publish_needs_decision", "containment")
# Publish (spec v2, from the operator's Q3 answer): from B1, the limit also checks that the publish record is
# console-approved and attributed to the operator. Until B1 builds that channel the limit stays "main moved only after
# the operator's yes", and this stays False; B1 flips it together with the check (vertical-uat.md, the hard limits).
PUBLISH_CONSOLE_ATTRIBUTION = False

# Containment (spec v2): every run's label and the Lead's, each at or above its platform's minimum. The order runs from
# weakest to strongest; `None` is no label recorded (today's Lead, uncontained on every platform). The minimums only
# ratchet up: `tests/unit/test_vertical_ledger.py` pins every earlier value and fails if one is ever lowered.
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
    def __init__(self, scenario: str, *, steering: bool = False, platform: str | None = None) -> None:
        self.scenario = scenario
        self.steering = steering
        self.platform = platform or ("win32" if sys.platform == "win32" else "linux")
        self.entries: list[dict[str, Any]] = []
        self.pins: dict[str, int] = {}  # PIN entries per endpoint lifetime
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

    def pin_entered(self, endpoint: str, *, step: str) -> None:
        """The operator typed the PIN into the console of ``endpoint`` (one endpoint lifetime: one project, one login
        session). "Authenticate at most once": the first entry in that lifetime is allowed and recorded; every further
        one is counted (``pin_reentries``). Never under ``credentials``: the PIN is the operator's own secret, not an
        AEW credential (spec v2). The auto-opened console itself is not a step and is never counted."""
        n = self.pins.get(endpoint, 0) + 1
        self.pins[endpoint] = n
        if n == 1:
            self.observe("pin_entered", step=step, endpoint=endpoint, note="the first in this endpoint's lifetime")
        else:
            self.count("pin_reentries", {"endpoint": endpoint, "entry": n}, actor="operator", step=step,
                       note="the PIN again while the same endpoint lives")

    def console_challenge(self, operation: str, *, step: str) -> None:
        """A per-action challenge at the operator console (a one-time code typed back at the requesting terminal) that
        stands in for "authenticate once": an operator-principal operation that is not a decision (configure, open).
        On Windows it is ``windows_console_challenges`` (spec v2). On Linux, where the PIN authenticates once, it is
        an authentication beyond the once, counted under ``pin_reentries``. A decision confirmed at the console (the
        steering raise, every Q9 item) is a decision on every platform and never comes here."""
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
                "thresholds": THRESHOLDS, "decisions": self.decisions, "hard_limits": self.hard_limits,
                "entries": self.entries, "observations": self.observations}

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
                  "decisions: " + ("; ".join(decision_line(d) for d in self.decisions) or "none")]
        if others:
            lines.append("not the operator's: " + "; ".join(f"{o.get('decision')} [owner {o.get('owner')}]"
                                                             for o in others))
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
