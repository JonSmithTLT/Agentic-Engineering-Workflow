"""Engine-owned execution coverage: observations, known gaps and unknown inventories never share a count.

This is disclosure, not a gate. No argv parsing can establish a project's affected tests or CI-tool inventory. The
record's writer freezes inputs; readers project its summary, never today's policy, tool install or workspace.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from aew.errors import IntegrityError
from aew.harness import runlog
from aew.harness.contract import redact
from aew.knowledge import evidence as E
from aew.policy import checks as C
from aew.util import load_yaml, sha256_file

# Display choices for E120's bounded hot-state projection, not execution limits: 50 paths give a small diff sample;
# ten entries per category give a useful scan; 500 characters bound one authored field. Full facts stay in records.
MAX_PATHS = 50
SUMMARY_ITEMS = 10
SUMMARY_CHARS = 500
# An 8 KiB serialized summary leaves room for the other head sections below readable's 50 KiB whole-line cut.
# This is a per-record storage/display budget, not a promise about a project view containing many records.
SUMMARY_BYTES = 8 * 1024
# A 600-byte line lets ten observed checks plus the inventory unknowns fit that budget even with wide characters.
SUMMARY_LINE_BYTES = 600


def inventory(checks: dict[str, Any], guardrails: dict[str, Any]) -> list[dict[str, Any]]:
    """The configured inventory at the observation's pin, not a list inferred from its command text."""
    return [{"check_id": cid, "definition_sha256": digest}
            for cid, digest in sorted(C.current_definitions(checks, guardrails).items())]


def files(paths: list[str] | None, *, source: str, reason: str = "source_diff_not_recorded") -> dict[str, Any]:
    if paths is None:
        return {"known": False, "reason": reason}
    ordered = sorted(set(paths))
    return {"known": True, "source": source, "count": len(ordered), "paths": ordered[:MAX_PATHS],
            "omitted": max(0, len(ordered) - MAX_PATHS)}


def run_capabilities(aew_root: Path, runs: list[str]) -> dict[str, Any]:
    # Local import keeps the pure formatter usable without loading the harness engine. Same closed-word/name rules
    # as status and wait, including the per-list recorded flags (PR 2 review m1).
    from aew.engine.harness_ops import _missing_capabilities

    return {run: _missing_capabilities(runlog.read_record(runlog.run_dir(aew_root, run))) for run in sorted(set(runs))}


def observation(meta: dict[str, Any], *, cwd: str | None = None, cited: bool = False) -> dict[str, Any]:
    check, method = meta.get("check") or {}, meta.get("method") or {}
    return {"evidence": meta.get("id"), "check_id": check.get("check_id"),
            "command": copy.deepcopy(method.get("command")), "cwd": cwd if cwd is not None else method.get("cwd"),
            "definition_sha256": check.get("definition_sha256"),
            "evaluated_snapshot": copy.deepcopy(meta.get("evaluated_snapshot")), "result": meta.get("result"),
            "reason": check.get("reason"), "run": (meta.get("producer") or {}).get("run"), "cited": cited}


def build(*, subject: dict[str, Any], configured: list[dict[str, Any]], checks: list[dict[str, Any]],
          changed_files: dict[str, Any], capabilities: dict[str, Any], result: str,
          complete: bool = True, limits: list[str] | None = None) -> dict[str, Any]:
    """Freeze only supplied observed facts. Incomplete execution is not proof that every absent check was unrun."""
    ran = {(c.get("check_id"), c.get("definition_sha256")) for c in checks}
    out = {"schema": "aew/validation-coverage/v1", "subject": copy.deepcopy(subject),
           "checks": copy.deepcopy(checks),
           "configured_not_run": [{**c, "reason": "not_run_in_this_validation"} for c in configured
                                  if (c["check_id"], c["definition_sha256"]) not in ran] if complete else [],
           "changed_files": copy.deepcopy(changed_files), "run_capabilities": copy.deepcopy(capabilities),
           "affected_tests": {"known": False, "reason": "no_project_source"},
           "ci_tools": {"known": False, "reason": "no_project_source"},
           "observation_limits": list(limits or []) + ([] if complete else ["execution_completion_not_recorded"]),
           "result": result}
    out["summary"] = summarize(out)
    return out


def _text(value: Any) -> str:
    text = " ".join("".join(" " if unicodedata.category(c)[0] == "C" or c in "\u2028\u2029" else c
                            for c in str(value)).split())
    text = redact(text)
    return text if len(text) <= SUMMARY_CHARS else text[:SUMMARY_CHARS] + "…"


def _listed(lines: list[str]) -> list[str]:
    return [*lines[:SUMMARY_ITEMS], *([f"({len(lines) - SUMMARY_ITEMS} more entries omitted; see coverage record)"]
                                     if len(lines) > SUMMARY_ITEMS else [])]


def _execution_data(command: Any) -> str:
    """Host-local argv stays in the structured record, not in a git-kept completion body. Never infer test scope."""
    if not isinstance(command, list):
        return "not recorded"
    shown = []
    for index, part in enumerate(command):
        if index == 0 and part == sys.executable:
            shown.append(f"Python {sys.version.split()[0]}")
        elif re.search(r"(?:^|[\s=\"'])(?:/|[A-Za-z]:[\\/]|\\\\)", str(part)):
            shown.append("<host-local argument; see coverage record>")
        else:
            shown.append(part)
    return _text(json.dumps(shown, ensure_ascii=False))


def _bounded_summary(summary: dict[str, Any], known: list[str], unknown: list[str]) -> dict[str, Any]:
    """Reserve unknown lines first, then fit known detail; truncation is explicit and full facts stay immutable."""
    note = "(summary detail omitted to fit byte budget; see coverage record)"
    summary["lines"] = []
    # JSON's default separators match durable records' consumers; UTF-8 bytes, not Unicode character counts.
    remaining = SUMMARY_BYTES - len(json.dumps(summary, ensure_ascii=False).encode("utf-8"))
    remaining -= len(json.dumps(note).encode("utf-8")) + 2

    def fit(lines: list[str]) -> list[str]:
        nonlocal remaining
        kept = []
        for line in lines:
            if len(line.encode("utf-8")) > SUMMARY_LINE_BYTES:
                suffix = "… (line shortened; see coverage record)"
                line = line.encode("utf-8")[:SUMMARY_LINE_BYTES - len(suffix.encode("utf-8"))].decode(
                    "utf-8", errors="ignore") + suffix
            size = len(json.dumps(line, ensure_ascii=False).encode("utf-8")) + 2
            if size <= remaining:
                kept.append(line)
                remaining -= size
        return kept

    unknown_kept = fit(unknown)
    known_kept = fit(known)
    omitted = len(known_kept) + len(unknown_kept) < len(known) + len(unknown)
    summary["lines"] = [*known_kept, *([note] if omitted else []), *unknown_kept]
    return summary


def summarize(value: dict[str, Any]) -> dict[str, Any]:
    """The same four-case rule everywhere. Future known inventories exercise this rule without a new adapter."""
    checks = value.get("checks") or []
    not_run = value.get("configured_not_run") or []
    caps = value.get("run_capabilities") or {}
    counts = {"configured_checks_not_run": len(not_run)}
    for kind in ("tools", "skills"):
        recorded = [r for r in caps.values() if r.get(f"{kind}_recorded")]
        if recorded:
            counts[f"missing_run_{kind}"] = sum(len(r.get(f"missing_{kind}") or []) for r in recorded)
    unknown, inventory_gaps = [], []
    for field, label in (("affected_tests", "Affected tests"), ("ci_tools", "Project CI tools")):
        item = value.get(field) or {"known": False, "reason": "coverage_not_recorded"}
        if item.get("known") is True:
            counts[f"{field}_not_run"] = sum(not i.get("ran", False) for i in item.get("items") or [])
            inventory_gaps.extend(f"{label}: {_text(i.get('name'))}: not run ({_text(i.get('reason', 'not run'))})"
                                  for i in item.get("items") or [] if not i.get("ran", False))
        else:
            unknown.append(f"{label}: not known ({_text(str(item.get('reason')).replace('_', ' '))})")
    for run, entry in caps.items():
        for kind in ("tools", "skills"):
            if not entry.get(f"{kind}_recorded"):
                unknown.append(f"Run {_text(run)} {kind} delivery: not known (delivery not recorded)")
    if not caps:
        unknown.append("Run capability delivery: not known (no harness delivery record)")
    changed = value.get("changed_files") or {}
    if not changed.get("known"):
        unknown.append(f"Changed files: not known ({_text(changed.get('reason'))})")
    if any(c.get("cwd") is None for c in checks):
        unknown.append("Check cwd: not known (legacy execution scope not recorded)")
    unknown.extend(f"Observation: not known ({_text(reason)})" for reason in value.get("observation_limits") or [])
    result = value.get("result")
    verdict = ("validated within its scope" if unknown or any(counts.values()) else "validated") if result == "pass" \
        else "advisory (not validation)" if result == "advisory" else str(result or "not validated")
    observed = [f"Check {_text(c.get('check_id'))}: {_text(c.get('result'))}; execution data: "
                f"{_execution_data(c.get('command'))}; cwd: see coverage record; "
                f"snapshot {_text((c.get('evaluated_snapshot') or {}).get('relevant_inputs_fingerprint'))}"
                for c in checks]
    gaps = [f"Configured check {_text(c['check_id'])}: not run ({_text(c['reason'])})" for c in not_run]
    tools, skills = [], []
    for run, entry in caps.items():
        tools.extend(f"Run {_text(run)} missing pinned tool: {_text(t['command'])}; "
                     f"{_text(t['got'])}; {_text(t['why'])}"
                     for t in entry.get("missing_tools") or [] if entry.get("tools_recorded"))
        skills.extend(f"Run {_text(run)} missing skill: {_text(s['name'])}; {_text(s['reason'])}"
                      for s in entry.get("missing_skills") or [] if entry.get("skills_recorded"))
    counts_text = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in counts.items()
                            if not k.startswith("missing_run_"))
    for kind in ("tools", "skills"):
        count = counts.get(f"missing_run_{kind}")
        known = bool(caps) and all(r.get(f"{kind}_recorded") for r in caps.values())
        detail = str(count) if known else "not known" + (f" (recorded gaps: {count})" if count else "")
        counts_text += f"; missing run {kind}: {detail}"
    single = (value.get("subject") or {}).get("scope") == "check"
    if single and result == "pass":
        verdict = "pass within its recorded scope"
    return _bounded_summary({"verdict": verdict, "known_gaps": counts,
                             "headline": f"{'Check' if single else 'Validation'}: {verdict}; {counts_text}"},
                            [*_listed(observed), *_listed(gaps), *_listed(inventory_gaps), *_listed(tools),
                             *_listed(skills)], _listed(unknown))


def legacy() -> dict[str, Any]:
    return {"summary": {"verdict": "coverage not recorded (legacy record)",
                        "headline": "Validation: coverage not recorded (legacy record)",
                        "known_gaps": {}, "lines": ["Affected tests: not known (no recorded coverage)",
                                                   "Project CI tools: not known (no recorded coverage)"]}}


def not_validated(*, result: str = "not yet validated") -> dict[str, Any]:
    """No validation record exists; this is not a historical record missing its coverage field."""
    return {"summary": {"verdict": result, "headline": f"Validation: {result}", "known_gaps": {}, "lines": []}}


def pin(path: str, digest: str, value: dict[str, Any] | None) -> dict[str, Any]:
    return {"record": {"path": path, "sha256": digest}, "summary": copy.deepcopy((value or legacy())["summary"])}


def load(aew_root: Path, reference: dict[str, Any]) -> dict[str, Any]:
    record = reference.get("record")
    if not record:
        return copy.deepcopy(reference) if reference else legacy()
    path = aew_root / record["path"]
    if not path.resolve().is_relative_to(aew_root.resolve()) or sha256_file(path) != record["sha256"]:
        raise IntegrityError("the pinned validation coverage record is missing or changed")
    meta = E.read(path)[0] if path.suffix == ".md" else load_yaml(path.read_text(encoding="utf-8"))
    return meta.get("coverage") or legacy()


def for_unit(aew_root: Path, unit: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    """Use the selected subject's pin. Project views use its bounded summary, with no per-unit record reads."""
    integ = unit.get("integration") or {}
    current = integ.get("current_validation_run") or {}
    ref = (current.get("coverage") if current.get("state") == "running" else None) \
        or integ.get("coverage") or (unit.get("last_verification") or {}).get("coverage") \
        or (legacy() if unit.get("last_verification") or current else not_validated())
    return load(aew_root, ref) if full else {"summary": copy.deepcopy(ref["summary"])}
