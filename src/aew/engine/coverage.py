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
from typing import TYPE_CHECKING, Any

from aew.errors import IntegrityError
from aew.harness import runlog
from aew.harness.contract import redact
from aew.knowledge import evidence as E
from aew.policy import checks as C
from aew.util import load_yaml, sha256_file

if TYPE_CHECKING:
    from aew.engine.base import Kernel

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


def checks_at_pin(kernel: Kernel) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Resolve the declaration and its digest from the same adopted bytes."""
    from aew.engine.base import check_policy_bytes

    raw, digest = kernel.policy_bytes_with_pin("checks")
    policy = check_policy_bytes("checks", raw, source=kernel.manifest["policy"]["checks"])
    declaration = policy.get("coverage")
    return policy, None if declaration is None or digest is None else {"declaration": declaration, "sha256": digest}


def _ci_present(root: Path) -> bool:
    if (root / ".github" / "workflows").is_dir():
        return True
    from aew.maps import rules, structural
    from aew.workspace import git

    labels = rules.load().data["directory_labels"]
    ci_dirs = {name for name, label in labels.items() if label == "ci"}
    paths = git.git("ls-files", "-z", cwd=root).stdout.decode("utf-8", errors="replace")
    return any(part.lower() in ci_dirs for path in paths.split("\0") if not path.startswith(".aew/")
               for part in path.split("/")[:-1][:structural.DIRECTORY_DEPTH])


def doctor_rows(policy: dict[str, Any], declaration: dict[str, Any], root: Path) -> list[tuple[str, str]]:
    ci_present = any(key not in declaration for key in ("ci_tools", "affected_tests")) and _ci_present(root)
    rows = []
    for key, label in (("ci_tools", "Project CI tools"), ("affected_tests", "Affected tests")):
        if key in declaration:
            rows.append(("PASS", f"{label}: declared"))
        elif ci_present:
            rows.append(("WARN", f"{label}: the project has CI configuration but this list is not declared. "
                         "Validations state 'not known'. See 'Declare project CI coverage' in the quickstart."))
        else:
            rows.append(("PASS", f"{label}: not declared; validations state 'not known'"))
    configured = C.current_definitions(policy, {})
    rows.extend(("WARN", f"CI runs {_text(tool['name'])}; no configured check runs it")
                for tool in declaration.get("ci_tools", []) if configured.keys().isdisjoint(tool["covered_by"]))
    if "affected_tests" in declaration:
        checks = policy.get("checks", {})
        if not any(C.takes_selection(checks.get(name, {})) for name in configured):
            fixed = ", ".join(_text(name) for name in sorted(configured)) or "none"
            rows.append(("WARN", "The project's CI selects tests for each change; no check runs that selection. "
                         f"Checks with a fixed scope: {fixed}"))
    return rows


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
            "outcome": check.get("outcome"), "exit_code": check.get("exit_code"),
            "reason": check.get("reason"), "run": (meta.get("producer") or {}).get("run"), "cited": cited}


def _ci_inventory(declared: list[dict[str, Any]], configured: list[dict[str, Any]],
                  checks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    available = {c["check_id"] for c in configured}
    reasons_for: dict[str | None, str] = {"spawn_failed": "could_not_start", "timeout": "not_completed"}
    items, completed_by = [], {}
    for tool in declared:
        name = tool["name"]
        covering = available.intersection(tool["covered_by"])
        observed = [c for c in checks if c.get("check_id") in covering]
        finished = sorted({c["check_id"] for c in observed if c.get("exit_code") is not None})
        reasons = [] if finished else sorted({reasons_for.get(c.get("outcome"), "not_run_in_this_validation")
                                               for c in observed})
        if not finished and not reasons:
            reasons = ["not_run_in_this_validation" if covering else "not_configured"]
        if finished:
            completed_by[name] = finished
        items.append({"name": name, "ran": bool(finished), "reasons": reasons})
    return items, completed_by


def _affected_inventory(record: dict[str, Any], ref: dict[str, str], unit: str,
                        checks: list[dict[str, Any]]) -> dict[str, Any]:
    if record["result"] == "unknown":
        return {"known": False, "reason": record["reason"]}
    reasons_for: dict[str | None, str] = {"spawn_failed": "could_not_start", "timeout": "not_completed"}
    cited = [c for c in checks if c.get("selection_sha256") == ref["sha256"]]
    ran = any(c.get("exit_code") is not None for c in cited)
    reasons = [] if ran else sorted({reasons_for.get(c.get("outcome"), "not_run_in_this_validation")
                                    for c in cited} or {"not_run_in_this_validation"})
    items = record["items"]
    return {"known": True, "source": "selection:" + ref["sha256"], "unit": unit,
            "items": [{"name": name, "ran": ran, "reasons": reasons} for name in items[:MAX_PATHS]],
            "omitted": max(0, len(items) - MAX_PATHS)}


def build(*, subject: dict[str, Any], configured: list[dict[str, Any]], checks: list[dict[str, Any]],
          changed_files: dict[str, Any], capabilities: dict[str, Any], result: str,
          declaration_pin: dict[str, Any] | None, checkless: bool = False,
          complete: bool = True, limits: list[str] | None = None, selection_record: dict[str, Any] | None = None,
          selection_ref: dict[str, str] | None = None) -> dict[str, Any]:
    """Freeze only supplied observed facts. Incomplete execution is not proof that every absent check was unrun.
    ``declaration_pin`` has no default: a site that omitted it would record "no project source" for a project that
    declared one, so each site says which pin it read, or ``None``."""
    ran = {(c.get("check_id"), c.get("definition_sha256")) for c in checks}
    # A subject that runs no checks (integration prepare) says so first; it is also incomplete, as E120 recorded it.
    reason = ("no_checks_in_this_subject" if checkless else
              "execution_completion_not_recorded" if not complete else "no_project_source")
    affected_tests = {"known": False, "reason": reason}
    ci_tools: dict[str, Any] = {"known": False, "reason": reason}
    completed_by: dict[str, list[str]] = {}
    if complete and not checkless and declaration_pin is not None:
        declaration = declaration_pin["declaration"]
        if "affected_tests" in declaration:
            if selection_record is not None and selection_ref is not None:
                affected_tests = _affected_inventory(selection_record, selection_ref,
                                                     declaration["affected_tests"]["unit"], checks)
            else:
                affected_tests["reason"] = "selection_not_run"
        if "ci_tools" in declaration:
            items, completed_by = _ci_inventory(declaration["ci_tools"], configured, checks)
            ci_tools = {"known": True, "source": "declared:" + declaration_pin["sha256"], "items": items}
    out = {"schema": "aew/validation-coverage/v1", "subject": copy.deepcopy(subject),
           "checks": copy.deepcopy(checks),
           "configured_not_run": [{**c, "reason": "not_run_in_this_validation"} for c in configured
                                  if (c["check_id"], c["definition_sha256"]) not in ran] if complete else [],
           "changed_files": copy.deepcopy(changed_files), "run_capabilities": copy.deepcopy(capabilities),
           "affected_tests": affected_tests, "ci_tools": ci_tools,
           "observation_limits": list(limits or []) + ([] if complete else ["execution_completion_not_recorded"]),
           "result": result}
    if selection_ref is not None and complete and not checkless:
        out["selection"] = selection_ref
    out["summary"] = summarize(out, completed_by=completed_by)
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


def _bounded_summary(summary: dict[str, Any], inventories: list[str], known: list[str],
                     unknown: list[str]) -> dict[str, Any]:
    """Reserve inventory headings and unknown lines before detail. Full facts stay in the record."""
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

    inventory_kept = fit(inventories)
    unknown_kept = fit(unknown)
    known_kept = fit(known)
    omitted = (len(inventory_kept) + len(known_kept) + len(unknown_kept)
               < len(inventories) + len(known) + len(unknown))
    summary["lines"] = [*inventory_kept, *known_kept, *([note] if omitted else []), *unknown_kept]
    return summary


def summarize(value: dict[str, Any], *, completed_by: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """The same four-case rule everywhere. Future known inventories exercise this rule without a new adapter."""
    checks = value.get("checks") or []
    not_run = value.get("configured_not_run") or []
    caps = value.get("run_capabilities") or {}
    counts = {"configured_checks_not_run": len(not_run)}
    for kind in ("tools", "skills"):
        recorded = [r for r in caps.values() if r.get(f"{kind}_recorded")]
        if recorded:
            counts[f"missing_run_{kind}"] = sum(len(r.get(f"missing_{kind}") or []) for r in recorded)
    unknown, inventories, inventory_gaps = [], [], []
    for field, label in (("affected_tests", "Affected tests"), ("ci_tools", "Project CI tools")):
        item = value.get(field) or {"known": False, "reason": "coverage_not_recorded"}
        if item.get("known") is True:
            items = item.get("items") or []
            missed = [i for i in items if not i.get("ran", False)]
            counts[f"{field}_not_run"] = len(missed)
            if field == "ci_tools":
                unconfigured = sum("not_configured" in i.get("reasons", []) for i in missed)
                line = f"{label} (per the project's declaration): {len(items)} declared"
                line += f", {unconfigured} not configured, {len(missed) - unconfigured} otherwise not run"
                ran_tools = [f"{_text(name)}: ran (check {_text(', '.join(ids))})"
                             for name, ids in (completed_by or {}).items()]
                inventories.append("; ".join([line, *_listed(ran_tools)]))
            else:
                unit = f", {_text(item['unit'])}" if item.get("unit") else ""
                omitted = item.get("omitted", 0)
                count = len(items) + omitted
                # A selection-consuming check receives the whole list, so omitted items have the same outcome.
                total_missed = len(missed) + (omitted if missed else 0)
                counts[f"{field}_not_run"] = total_missed
                detail = f"{count} selected, {total_missed} not run" if count else "none selected"
                inventories.append(f"{label} (per the project's selector{unit}): {detail}")
            inventory_gaps.extend(
                f"{label}: {_text(i.get('name'))}: not run "
                f"({_text(', '.join(reason.replace('_', ' ') for reason in i.get('reasons', [])) or 'not run')})"
                for i in missed)
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
                            inventories, [*_listed(observed), *_listed(gaps), *_listed(inventory_gaps),
                             *_listed(tools), *_listed(skills)], _listed(unknown))


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
