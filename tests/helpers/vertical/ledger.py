"""The burden ledger of the vertical UAT (docs/implementation/vertical-uat.md, "The burden ledger").

One entry per counted event, each with its evidence (the exact input or call, credentials redacted). The counters,
their thresholds and the hard limits are pinned here; ``tests/unit/test_vertical_ledger.py`` checks that they equal
the tables in ``vertical-uat.md``, so a threshold changes only with that document (which needs the operator).

The ledger also lists the operator's decisions (every question put to the operator, with the answer), the hard-limit
results (each kept apart as "did not refuse", a safety regression, or "refused without naming", an explanation gap),
and observations: setup steps that are not counted, the gaps a fallback covered, and facts a reviewer needs.

Classification lives here, in one place: the actors only report what they typed or called.
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
                     "takeovers", "seat_operations", "lifecycle_steps", "manifest_adopts")
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
HARD_LIMITS = ("semantic_conflict", "evidence_mismatch", "publish_needs_decision", "containment")
# Each harness run's containment label, unchanged from today's minimum per platform (the test never weakens it).
CONTAINMENT_MINIMUM = {"win32": "workdir_separation_only", "linux": "os_readonly_roots"}
# Hard-limit outcomes. Every one but `held` fails the test; the ledger keeps them apart: `did_not_refuse` is a safety
# regression, `refused_without_naming` an explanation gap, `rebuilt_not_published` a conflicting change AEW carried on
# with (rebuilt and re-verifying) instead of refusing, and `not_observed` a sub-scenario that never reached its step.
HELD, NOT_REFUSED, UNNAMED = "held", "did_not_refuse", "refused_without_naming"
REBUILT, NOT_OBSERVED = "rebuilt_not_published", "not_observed"
OUTCOMES = (HELD, NOT_REFUSED, UNNAMED, REBUILT, NOT_OBSERVED)

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


class Ledger:
    def __init__(self, scenario: str, *, steering: bool = False) -> None:
        self.scenario = scenario
        self.steering = steering
        self.platform = "win32" if sys.platform == "win32" else "linux"
        self.entries: list[dict[str, Any]] = []
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
        return {"schema": "aew/vertical-ledger/v1", "scenario": self.scenario, "mode": VERTICAL_MODE,
                "platform": self.platform, "steering": self.steering, "counts": self.counts(),
                "thresholds": THRESHOLDS, "decisions": self.decisions, "hard_limits": self.hard_limits,
                "entries": self.entries, "observations": self.observations}

    def summary(self) -> str:
        c = self.counts()
        lines = [f"vertical UAT {self.scenario} ({self.platform}, steering {'on' if self.steering else 'off'}, "
                 f"mode {VERTICAL_MODE})",
                 "operator: " + "  ".join(f"{k} {c[k]}" for k in OPERATOR_COUNTERS),
                 "lead:     " + "  ".join(f"{k} {c[k]}" for k in LEAD_COUNTERS),
                 "decisions: " + (", ".join(f"{d['label']} -> {d['answer']}" for d in self.decisions) or "none")]
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
