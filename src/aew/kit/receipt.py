"""Project an alpha receipt from AEW records without running the project's commands."""

from __future__ import annotations

import getpass
import json
import re
import socket
import subprocess
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, distribution
from itertools import combinations
from pathlib import Path
from typing import Any

from aew import __version__
from aew.engine import coverage
from aew.engine.api import Engine
from aew.engine.harness_ops import _missing_capabilities
from aew.errors import AEWError, UsageError
from aew.harness import runlog
from aew.harness.models import free_model_id
from aew.harness.opencode.capabilities import TESTED_VERSIONS
from aew.kit import KIT_RECORD, git
from aew.maps.slices import HEADING
from aew.util import atomic_write, glob_any, parse_frontmatter

SCHEMA = "aew/alpha-receipt/v1"
FIELDS = ("no_wake", "validation_width", "scope", "dead_end_gates", "readability", "containment")
SYSTEMS = ("SYS-02", "SYS-05", "SYS-06", "SYS-07", "SYS-08", "SYS-09", "SYS-19", "SYS-22", "SYS-39")
ID = re.compile(r"(?:T|INV|SI|Q)-\d{4,}|R-INV-\d{4,}-\d+")
SHA = re.compile(r"[0-9a-f]{40,64}")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?")
LABELS = {"os_readonly_roots", "workdir_separation_only"}
MODEL = re.compile(r"[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.:+-]+)+")


def _missing(why: str) -> str:
    return f"not recorded: {why}"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(runlog.read_regular(path).decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}


def _commit() -> str:
    root = Path(__file__).resolve().parents[3]
    if (root / ".git").exists() and (root / "pyproject.toml").is_file():
        try:
            found = git(root, "rev-parse", "HEAD")
            if SHA.fullmatch(found):
                return found
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        metadata = json.loads(distribution("aew").read_text("direct_url.json") or "{}")
        found = (metadata.get("vcs_info") or {}).get("commit_id", "")
        if SHA.fullmatch(found):
            return found
    except (PackageNotFoundError, ValueError, TypeError):
        pass
    return _missing("the installed distribution has no source commit")


def _records(engine: Engine) -> list[dict[str, Any]]:
    cursor = 0
    found: list[dict[str, Any]] = []
    while True:
        page = engine.history_log(since=cursor)
        found.extend(page["transitions"])
        cursor = page["next"]
        if cursor >= page["revision"]:
            return found


def _time(text: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(text)
        return value if value.tzinfo else None
    except (TypeError, ValueError):
        return None


def _paths(values: Any) -> list[str]:
    """Publish only project-relative path syntax, with local account and host identifiers withheld."""
    identifiers = {getpass.getuser().casefold(), Path.home().name.casefold(), socket.gethostname().casefold()} - {""}
    return sorted({
        path for path in values or ()
        if isinstance(path, str) and re.fullmatch(r"[\w.*?\[\]/-]+", path)
        and not path.startswith("/") and ".." not in path.split("/")
        and not any(part.casefold() in identifiers for part in path.split("/"))
    })


def _id(value: Any) -> bool:
    return isinstance(value, str) and ID.fullmatch(value) is not None


def _label(record: dict[str, Any]) -> str | None:
    label = record.get("filesystem")
    return label if isinstance(label, str) and label in LABELS else None


def _coverage(aew_root: Path, unit: dict[str, Any]) -> tuple[Any, list[str] | None]:
    try:
        record = coverage.for_unit(aew_root, unit, full=True)
    except (AEWError, OSError):
        record = {}
    changed = record.get("changed_files") or {}
    integrated = (unit.get("integration") or {}).get("changed_paths")
    paths = _paths(integrated) if isinstance(integrated, list) else (
        _paths(changed.get("paths")) if changed.get("known") else None)
    if record.get("schema") != "aew/validation-coverage/v1" or not record.get("subject"):
        return _missing("no bound E120 coverage record"), paths

    checks = []
    for check in record.get("checks") or []:
        check_id = check.get("check_id")
        if isinstance(check_id, str) and re.fullmatch(r"[a-z][a-z0-9_-]*", check_id):
            checks.append({"check": check_id, "result": check.get("result") in ("pass", "fail") and check["result"]
                           or _missing("check outcome unavailable")})

    def observed(field: str, path: str) -> Any:
        inventory = record.get(field) or {}
        for item in inventory.get("items") or []:
            if inventory.get("known") and item.get("name") == path and isinstance(item.get("ran"), bool):
                return item["ran"]
        return _missing("the coverage record does not name this probe")

    return {"checks": checks, "neighbour_test": observed("affected_tests", "tests/neighbour/test_statement.py"),
            "lint": observed("ci_tools", "tools/lint.py")}, paths


def _slice_bytes(aew_root: Path, invocation: Any) -> int | None:
    if not _id(invocation) or not invocation.startswith("INV-"):
        return None
    try:
        path = aew_root / "local/packs" / invocation / "pack.md"
        if not path.resolve().is_relative_to(aew_root.resolve()):
            return None
        text = runlog.read_regular(path).decode("utf-8")
    except (OSError, ValueError):
        return None
    heading = re.search(rf"(?m)^{re.escape(HEADING)}\r?$", text)
    if heading is None:
        return None
    section = re.match(r"\s*[^\r\n]*\r?\n\s*(`{3,})text\r?\n[\s\S]*?^\1\r?$",
                       text[heading.end():], re.MULTILINE)
    return len(text[heading.start():heading.end() + section.end()].encode("utf-8")) if section else None


def _system_facts(aew_root: Path, runs: list[dict[str, Any]], transitions: list[dict[str, Any]],
                  lead_labels: list[dict[str, Any]], version: Any, intents: dict[str, Any],
                  widths: dict[str, Any]) -> dict[str, Any]:
    systems: dict[str, Any] = dict.fromkeys(SYSTEMS, "not seen")
    if runs or lead_labels:
        systems["SYS-02"] = {"workers": {r["run"]: _label(r.get("containment") or {}) for r in runs},
                             "lead": [_label(label) for label in lead_labels]}
    if isinstance(version, dict):
        systems["SYS-05"] = version
    if intents:
        systems["SYS-06"] = {"typed_stage_intents": sorted(intents)}
        systems["SYS-08"] = {"stage_intents": sorted(intents)}
    packs, capabilities, plans = {}, {}, {}
    for record in runs:
        run = record["run"]
        contract = record.get("contract") or {}
        if (size := _slice_bytes(aew_root, contract.get("invocation"))) is not None:
            packs[run] = {"slice_bytes": size}
        facts = _missing_capabilities(record)
        if facts["tools_recorded"]:
            capabilities[run] = {"missing_tools": len(facts["missing_tools"])}
        plan = (contract.get("extra") or {}).get("skills") or {}
        if plan:
            plans[run] = {name: _paths(plan.get(name)) for name in ("requested", "offered", "exposed", "delivered")}
    if packs:
        systems["SYS-07"] = {"used_when_on": True, "packs": packs}
    if capabilities or lead_labels:
        systems["SYS-09"] = {"init_tools_screen": "not shown", "run_capabilities": capabilities,
                             "lead_start_consent": _missing("Lead-start screen output is not persisted")}
    if plans:
        systems["SYS-22"] = {"runs": plans, "loaded": _missing("the skills plan records delivery only")}
    if covered := sorted(ticket for ticket, width in widths.items() if isinstance(width, dict)):
        systems["SYS-19"] = {"tickets_with_validation_coverage": covered}
    pairs = []
    workers = [r for r in runs if (r.get("contract") or {}).get("role") == "implementer"]
    for left, right in combinations(workers, 2):
        one, two = left["contract"].get("work_unit"), right["contract"].get("work_unit")
        intervals = [(_time(r.get("started_at")), _time(r.get("ended_at"))) for r in (left, right)]
        (start_one, end_one), (start_two, end_two) = intervals
        if one != two and start_one and end_one and start_two and end_two and max(start_one, start_two) < min(
            end_one, end_two
        ):
            pairs.append([left["run"], right["run"]])
    publications = []
    for transition in transitions:
        events = transition.get("events") or []
        if transition["op"] == "integrate.publish" and any(e["kind"] == "queue.entry" for e in events):
            publications.extend(e["id"] for e in events if e["kind"] == "work.state" and e.get("to") == "DONE"
                                and _id(e.get("id")))
    if pairs or publications:
        systems["SYS-39"] = {"overlapping_mutating_runs": pairs, "queue_publications": sorted(set(publications))}
    return systems


def write_receipt(dest: Path, *, readable: str | None = None) -> Path:
    if readable not in (None, "yes", "no"):
        raise UsageError("readability must be yes or no")
    dest = dest.resolve()
    kit = _json(dest / KIT_RECORD)
    if not kit:
        raise UsageError("the destination has no kit record")
    engine = Engine.discover(dest / "repo")
    aew_root = engine.aew_root
    root = aew_root / runlog.RUNS_REL
    runs = [record for path in sorted(root.glob("R-INV-*")) if _id(path.name)
            if (record := runlog.read_record(path)) and record.get("run") == path.name]
    lead_labels = [label for path in sorted(root.glob("lead-*/label.json")) if (label := _json(path))]
    transitions = _records(engine)
    intent_ids = {ref for transition in transitions if transition["op"].startswith("stage.")
                  for ref in transition.get("refs") or [] if _id(ref) and ref.startswith("SI-")}
    intents = {}
    for intent in sorted(intent_ids):
        try:
            intents[intent] = engine.stage_intent(intent)
        except AEWError:
            continue
    gate_refusals = sorted(intent for intent, record in intents.items()
                           if ((record.get("stopped") or {}).get("error") or {}).get("code") == "GATE_UNSATISFIED")
    tickets = sorted({event["id"] for t in transitions for event in t.get("events") or []
                      if event["kind"] == "work.state" and event.get("unit") == "ticket" and _id(event.get("id"))})
    versions = sorted({v for r in runs if (r.get("launch") or {}).get("harness") == "opencode"
                       if isinstance(v := r["launch"].get("version"), str) and VERSION.fullmatch(v)})
    pinned = (engine.execution_policy()[0] or {}).get("harness")
    version = {"recorded": versions, "tested": list(TESTED_VERSIONS),
               "qualified": all(v in TESTED_VERSIONS for v in versions)} if versions else _missing(
                   "no OpenCode launch version")
    observed_models = {}
    for key in ("workers_model", "lead_model"):
        model = kit.get(key)
        observed_models[key] = (model if isinstance(model, str) and MODEL.fullmatch(model)
                                and not free_model_id(model) else _missing("no publishable model reference"))
    widths, scopes = {}, {}
    for ticket in tickets:
        shown = engine.work_show(ticket)
        meta = parse_frontmatter(shown["record"])[0] if shown.get("record") else {}
        scope = _paths((meta.get("scope") or {}).get("paths"))
        widths[ticket], changed = _coverage(aew_root, shown["control"])
        scopes[ticket] = {"paths": scope, "changed": changed if changed is not None else _missing("no changed paths"),
                          "outside": [p for p in changed if not glob_any(p, scope)] if changed is not None
                          else _missing("no changed paths")}
    lead_times = [stamp for t in transitions if (t.get("actor") or {}).get("kind") == "lead"
                  if (stamp := _time(t.get("at"))) is not None]
    no_step = [r["run"] for r in runs if (end := _time(r.get("ended_at"))) is not None
               and not any(stamp > end for stamp in lead_times)]
    seed_digest = kit.get("seed_digest")
    receipt = {
        "schema": SCHEMA, "kind": "real" if pinned == "opencode" and versions else "dry_run",
        "header": {"aew_version": __version__, "aew_commit": _commit(),
                   "seed_digest": seed_digest if isinstance(seed_digest, str) and SHA.fullmatch(seed_digest) else
                   _missing("no seed digest"), "platform": sys.platform,
                   "qualification": "UNQUALIFIED" if sys.platform == "win32" else "Linux" if sys.platform == "linux"
                   else "outside the enforced platforms", "opencode": version, **observed_models,
                   "lead_ran_on": _missing("E212 has no Lead model record"),
                   "free": "not ruled out (id rule only; catalog not read)"},
        "no_wake": {"wakes_reach_lead_now": engine.wakes_reach_lead(), "ended_without_later_lead_commit": no_step,
                    "non_committing_steps": _missing("the transition log records committed steps only")},
        "validation_width": widths or _missing("no Tickets"),
        "scope": {"tickets": scopes, "scope_changes": "scope is fixed at Ticket creation",
                  "created_tickets": tickets},
        "dead_end_gates": {"recorded_gate_refusals": gate_refusals,
                           "legal_next_steps_at_refusal": _missing("no contemporaneous projection is kept")},
        "readability": readable or "not asked",
        "containment": {"workers": {r["run"]: _label(r.get("containment") or {}) for r in runs},
                        "lead": [_label(label) for label in lead_labels]},
        "systems": _system_facts(aew_root, runs, transitions, lead_labels, version, intents, widths),
    }
    path = dest / "receipt/alpha-receipt.json"
    path.parent.mkdir(exist_ok=True)
    atomic_write(path, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return path
