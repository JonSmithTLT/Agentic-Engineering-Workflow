"""Measurements over the scripted model's captured request bodies."""

from __future__ import annotations

import io
import json
import re
import shlex
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from harness_qualify.opencode import SYNTHETIC_KEY

from aew.harness.contract import CREDENTIAL_RE
from aew.harness.opencode.projection import LEAD_MCP_SERVER

LEAD_PREFIXES = (f"{LEAD_MCP_SERVER}_", f"{LEAD_MCP_SERVER.replace('-', '_')}_")


def size(value: Any, *, ascii_only: bool = False) -> int:
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=ascii_only).encode("utf-8"))


def text_of(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content or [] if isinstance(p, dict))


def tool_name(tool: dict) -> str:
    return (tool.get("function") or tool)["name"]


def lead_name(name: str) -> str | None:
    return next((name.removeprefix(prefix) for prefix in LEAD_PREFIXES if name.startswith(prefix)), None)


def schema_features(value: Any) -> set[str]:
    if isinstance(value, list):
        return set().union(*(schema_features(item) for item in value))
    if isinstance(value, dict):
        return value.keys() & {"annotations", "$defs", "$ref"} | set().union(
            *(schema_features(child) for child in value.values()))
    return set()


def instructions_parts(text: str, guide: str, system: str) -> dict[str, int]:
    if not guide or not system or f"{system}\n\n{guide}" not in text:
        raise ValueError("rendered Lead system and guide do not match the provider request")
    remaining = text.replace(system, "", 1).replace(guide, "", 1)
    parts = {"aew_system": size(system) - 2, "guide": size(guide) - 2}
    model = re.search(r"(?im)^#+\s+Your Model[^\n]*\n[^\n]*(?:\n(?!\s*(?:#|\n))[^\n]*)*", remaining)
    if model:
        parts["your_model"] = size(model[0]) - 2
        remaining = remaining[:model.start()] + remaining[model.end():]
    code = re.search(
        r"(?ims)^#+[^\n]*Code Mode[^\n]*\n.*?(?=^<(?:mcp_instructions|available_skills|env)\b|\Z)", remaining,
    )
    if code:
        parts["code_mode"] = size(code[0]) - 2
        remaining = remaining[:code.start()] + remaining[code.end():]
    for tag, part in (("mcp_instructions", "mcp_instructions"), ("available_skills", "skills"), ("env", "environment")):
        pattern = rf"<{tag}(?:\s[^>]*)?>.*?</{tag}>"
        matches = re.findall(pattern, remaining, re.DOTALL)
        parts[part] = sum(size(match) - 2 for match in matches)
        remaining = re.sub(pattern, "", remaining, flags=re.DOTALL)
    parts["other_instruction_text"] = size(remaining) - 2
    return parts


def request_parts(request: dict, *, guide: str = "", system: str = "") -> dict:
    body = request["body"]
    instructions = body.get("instructions", "")
    groups = instructions_parts(instructions, guide, system) if guide else {"instructions": size(instructions) - 2}
    aew, builtin, features = {}, {}, {}
    for tool in body.get("tools") or []:
        name = tool_name(tool)
        local = lead_name(name)
        if local is None:
            builtin[name] = size(tool)
        else:
            aew[local] = size(tool)
            present = schema_features(tool)
            features[local] = {key: key in present for key in ("annotations", "$defs", "$ref")}
    input_parts = {"first_user": 0, "system_or_developer": 0, "other": 0}
    for item in body.get("input") or []:
        role = item.get("role")
        if role == "user" and not input_parts["first_user"]:
            input_parts["first_user"] = size(item)
        elif role in {"system", "developer"}:
            input_parts["system_or_developer"] += size(item)
        else:
            input_parts["other"] += size(item)
    other = sum(size(value) for key, value in body.items() if key not in {"tools", "instructions", "input"})
    counted = sum(groups.values()) + sum(aew.values()) + sum(builtin.values()) + sum(input_parts.values()) + other
    return {
        "raw_bytes": request["raw_bytes"], "instruction_bytes": groups, "aew_tool_bytes": aew,
        "builtin_tool_bytes": builtin, "aew_tool_features": features, "input_bytes": input_parts,
        "other_field_bytes": other,
        "wire_framing_and_encoding_bytes": request["raw_bytes"] - counted,
    }


def shell_route(command: str) -> str:
    from aew.cli.main import build_parser
    from aew.harness import lead_broker

    try:
        argv = shlex.split(command)
        if not argv or argv[0] != "aew":
            return "other"
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            args = build_parser(recall_search=True, coordination_reads=True).parse_args(argv[1:])
    except (ValueError, SystemExit):
        return "other"
    path = lead_broker.command_path(args)
    if path in lead_broker.RELAYED_READS:
        return "relayed"
    if path in lead_broker.CONTAINED_LOCAL:
        return "contained-local"
    return "other"


def results(requests: list[dict]) -> list[dict]:
    """Each distinct call and output, joined by its protocol ID across snapshots."""
    calls, outputs = {}, {}
    for request in requests:
        for item in request["body"].get("input") or []:
            if item.get("type") == "function_call":
                calls[item["call_id"]] = item
            elif item.get("type") == "function_call_output":
                outputs[item["call_id"]] = item
    rows = []
    for call_id, call in calls.items():
        item = outputs.get(call_id)
        output = item.get("output") if item is not None else None
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        arguments = json.loads(call.get("arguments") or "{}")
        name = call["name"]
        typed = lead_name(name)
        shell = arguments.get("command", "")
        rows.append({
            "call_id": call_id, "tool": typed or name, "command": shell or None,
            "route": "typed" if typed else shell_route(shell),
            "output_bytes": len(text.encode("utf-8")) if item is not None else None,
            "output_item_bytes": size(item) if item is not None else None,
            "traceback": "Traceback (most recent call last)" in text,
            "missing_git": "No such file or directory: 'git'" in text,
        })
    return rows


def save_requests(path: Path, requests: list[dict], lead_credential: str = "") -> None:
    path.mkdir(mode=0o700)
    for index, request in enumerate(requests):
        wire = request.get("wire")
        if wire is None:
            continue
        decoded = json.dumps(request["body"], ensure_ascii=False)
        for text in (wire, decoded):
            if SYNTHETIC_KEY in text or (lead_credential and lead_credential in text) or CREDENTIAL_RE.search(text):
                raise ValueError(f"credential found in request {index}; body withheld")
        (path / f"{index:03}.json").write_bytes(wire.encode("utf-8"))


def lead_measurements(requests: list[dict], guide: str, system: str) -> dict:
    rows = results(requests)
    if len(rows) != 6 or any(row["output_bytes"] is None for row in rows):
        raise ValueError("did not capture all six scripted read results")
    raw = [r["raw_bytes"] for r in requests]
    return {"first_request": request_parts(requests[0], guide=guide, system=system),
            "per_request_raw_bytes": raw, "growth_bytes": [b - a for a, b in zip(raw, raw[1:], strict=False)],
            "results": rows}


def reanalyse(capture: Path, out: Path, *, analysed_with: str) -> None:
    """Retain the measured commit and derive the split, rows and route labels with the verified analysing commit."""
    result = json.loads((capture / "record.json").read_bytes())
    lead = result.get("legs", {}).get("lead")
    if result.get("schema") != "aew/lead-probe/v1" or not result.get("aew_commit") or not lead:
        raise ValueError("expected a probe record with a saved Lead leg")
    directory = capture / "lead"
    texts = [directory / "guide.txt", directory / "system.txt"]
    if all(path.is_file() for path in texts):
        guide, system = (path.read_bytes().decode("utf-8") for path in texts)
    else:
        # The first capture retained the fixture but did not yet save the rendered text.
        from types import SimpleNamespace

        from aew.harness import runlog

        from .session import calibration, worker_facts

        guide, system, _, containment = calibration(SimpleNamespace(root=directory / "fixture/repo"))
        lead["containment"] = containment
        lead.pop("contained", None)
        for name in ("lead", "worker"):
            leg = result["legs"].get(name)
            if leg is None:
                continue
            project = capture / name / "fixture/repo/.aew"
            [saved_run] = (project / runlog.RUNS_REL).glob(f"*/{runlog.RECORD}")
            facts = worker_facts(saved_run.parent)
            if name == "lead":
                lead["worker"] = facts
            else:
                leg.pop("keyless_provider_denies", None)
                leg.update(facts)

    requests = []
    start = lead.get("request_start")
    for path in sorted((directory / "requests").glob("*.json")):
        if start is not None and int(path.stem) < start:
            continue
        wire = path.read_bytes()
        body = json.loads(wire)
        if not body.get("tools"):
            continue
        if start is None and not requests and not any(lead_name(tool_name(tool)) for tool in body["tools"]):
            continue
        requests.append({"body": body, "raw_bytes": len(wire)})
    lead.update(lead_measurements(requests, guide, system))
    result["analysed_with"] = analysed_with
    out.mkdir(mode=0o700)
    (out / "record.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
