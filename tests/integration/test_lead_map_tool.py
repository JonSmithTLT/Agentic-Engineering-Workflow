"""The Lead's typed `map` tool (register F15.8, the mapping series' PR A2): the same answers as `aew map search` and
`aew map show --scope ticket`, from the one query module, by its own route; offered only while `maps.reads` is on; and a
read that never refreshes or selects a map."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from aewflow import create_investigation, sample_project

from aew.engine.api import Engine
from aew.maps import query, store
from aew.surface import contract
from aew.surface.context import switches_for

IS_WINDOWS = sys.platform == "win32"


def g(*args: str, cwd: Path) -> str:
    kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}  # no console window
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, timeout=120,
                          stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, **kw)
    return proc.stdout.decode("utf-8", "surrogateescape").strip()


def tool(project: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """The tool through its CLI transport outside a session: the same runner the broker runs (TLS-22)."""
    out = project.ok("lead", "tool", "map", "--arguments", json.dumps(arguments))
    assert out["ok"] and out["tool"] == "map" and out["base_operation_class"] == contract.MECHANICAL, out["stopped"]
    assert out["completed_steps"] == [] and out["stage_intent_id"] is None
    return out["result"]


def by_route(answer: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """``answer`` as the other route gets it: only the basis's recipient names the route a read came by."""
    return {**answer, "basis": {**answer["basis"], "recipient": route}}


def maps_state(aew: Path) -> dict[str, str]:
    """Every file under the project's map store, by its digest: what a refresh or a selection would change."""
    root = aew / "local" / "maps"
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_the_leads_map_tool_answers_exactly_what_aew_map_search_answers_but_its_route(tmp_path):
    """One query path: the tool's search and scope reads are `aew map search`'s and `aew map show --scope ticket
    --work`'s answers, envelope and all (`aew/map-answer/v1`), at the authoritative head; only the recipient differs,
    naming the route (`query.TOOL_RECIPIENT`), which a read authenticates no better than the CLI's."""
    project = sample_project(tmp_path)
    wid = create_investigation(project, tmp_path)
    cases = [
        ({"read": "search", "text": "core.py", "kind": "path", "limit": "5"},
         ("map", "search", "core.py", "--kind", "path", "--limit", "5", "--json")),
        ({"read": "search", "text": "README.md"}, ("map", "search", "README.md", "--json")),
        ({"read": "show", "scope": "ticket", "work_id": wid},
         ("map", "show", "--scope", "ticket", "--work", wid, "--json")),
    ]
    for arguments, argv in cases:
        typed, cli = tool(project, arguments), project.ok(*argv)
        assert typed["schema"] == query.SCHEMA == cli["schema"] and typed["items"], arguments
        assert typed["basis"]["recipient"] == query.TOOL_RECIPIENT and cli["basis"]["recipient"] == query.CLI_RECIPIENT
        assert by_route(typed, query.CLI_RECIPIENT) == cli, arguments
        assert typed["basis"]["chosen_by"] == query.AUTHORITATIVE_HEAD
    # The orientation and a section are the worker rows' answers (`map.show`), the module's `status` and `section`.
    engine = Engine.discover(project.root)
    from aew.maps import service

    here = service.read_context(engine, recipient=query.TOOL_RECIPIENT)
    assert tool(project, {"read": "show"}) == query.serve(here, "map.show", {"section": "", "scope": ""})
    assert tool(project, {"read": "show", "section": "languages"}) == query.section(here, "languages")


def test_the_map_tool_never_refreshes_or_selects_a_map(tmp_path):
    """A read writes no map state: with the selected map STALE against a moved head, every read of the tool leaves the
    map store byte for byte as it was (no new artifact, no selection, no registry revision) and says it is STALE."""
    project = sample_project(tmp_path)
    wid = create_investigation(project, tmp_path)
    aew = project.root / ".aew"
    (project.root / "calc" / "added.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    g("add", "calc/added.py", cwd=project.root)
    g("commit", "-q", "-m", "move the head", cwd=project.root)
    before, registry = maps_state(aew), store.read_registry(aew)
    reads = [{"read": "show"}, {"read": "show", "section": "directories"},
             {"read": "show", "scope": "ticket", "work_id": wid}, {"read": "search", "text": "added.py"},
             {"read": "search", "text": "no such text anywhere", "kind": "any"}]
    for arguments in reads:
        answer = tool(project, arguments)
        assert answer["freshness"]["structural"]["status"] == "STALE", arguments
        assert maps_state(aew) == before and store.read_registry(aew) == registry, arguments
    assert [i["path"] for i in tool(project, {"read": "search", "text": "added.py"})["items"]] == ["calc/added.py"]


def turn_maps_reads_off(project: Any) -> None:
    """A project whose policy has `maps.reads` off, as one initialized before O1 reads it."""
    execution = project.root / ".aew" / "policy" / "execution.yaml"
    text, on = execution.read_text(encoding="utf-8"), "\n  reads: structural\n"
    assert text.count(on) == 1, "the template's maps.reads line moved"
    execution.write_text(text.replace(on, '\n  reads: "off"\n'), encoding="utf-8", newline="\n")
    project.pin_policy()


def test_the_leads_map_tool_is_offered_exactly_while_maps_reads_is_on(tmp_path):
    """The tool is the switch's: a new project (`maps.reads: structural`) lists and answers it; with the switch off its
    session snapshot (``switches_for``) holds no `maps.reads`, the listing omits the tool, and a call naming it is an
    input error that never reaches the runner (UNKNOWN_TOOL). The relayed `aew map search` still answers either way."""
    project = sample_project(tmp_path)
    assert contract.MAPS in switches_for(Engine.discover(project.root))
    assert "map" in [t["name"] for t in project.ok("lead", "tool", "--list")["tools"]]
    turn_maps_reads_off(project)
    assert contract.MAPS not in switches_for(Engine.discover(project.root))
    assert "map" not in [t["name"] for t in project.ok("lead", "tool", "--list")["tools"]]
    refused = project.aew("lead", "tool", "map", "--arguments", json.dumps({"read": "search", "text": "core.py"}))
    assert refused.returncode != 0 and refused.error["code"] == "UNKNOWN_TOOL"
    assert project.ok("map", "search", "core.py", "--json")["schema"] == query.SCHEMA
