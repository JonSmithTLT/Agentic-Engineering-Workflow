"""Live lane, register E35's probe (harness ruling 11, W14): what a project can load into a real OpenCode server.

AEW starts every OpenCode server, a worker run's (``adapter.server_env``) and the Lead's (``lead.py``), with
``OPENCODE_DISABLE_PROJECT_CONFIG=1``. The probe measures whether that also keeps out the two layers the flag's name
does not promise: (a) a project's ``.opencode/`` directory (its config file, agents, commands, skills, tools and
plugins, whose module code runs when loaded) and (b) the remote ``.well-known/opencode`` layer.

Model-free and keyless: a real private ``serve --stdio`` per measurement, on AEW's server environment and private XDG
state, in a throwaway project planted with markers. Each measurement is made twice by the same procedure, with the
flag as AEW sets it and with the flag removed (the control), so the probe cannot pass vacuously: the control must show
the markers loaded through every channel it asserts on. The servers are told nothing else: their configuration
(``OPENCODE_CONFIG_CONTENT``) holds only a control plugin outside the project, whose own sentinel is the clock both runs
wait on (a project plugin activates in the same pass). Results per version are in the register's E35 notes; to
measure another binary::

    AEW_OPENCODE_BIN=<path to opencode> pytest --live tests/live/test_opencode_project_config_live.py -p no:xdist -q

``AEW_LIVE_RESULTS``, if set, gets one JSON line per measurement: what each channel showed.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from aew.harness import procs
from aew.harness.opencode import adapter
from aew.harness.opencode.client import Client, OpenCodeError, Server, location

pytestmark = [pytest.mark.skipif(not os.environ.get(adapter.BIN_ENV) and adapter.default_binary() is None,
                                 reason="no OpenCode binary (set AEW_OPENCODE_BIN)"),
              pytest.mark.skipif(sys.platform == "win32", reason="the markers are POSIX: `touch`, and `/` in paths")]

FLAG = "OPENCODE_DISABLE_PROJECT_CONFIG"
MARK = "aew-probe"
GATE_S = 60.0  # the control plugin has activated well within this on 2.0.18 and 2.2.6 (about 8 s)
SETTLE_S = 5.0  # after the gate, before reading: the same for both runs, and the control must load within it
CHANNELS = ("/api/agent", "/api/command", "/api/skill", "/api/plugin", "/api/mcp")


def plugin_source(sentinel: Path, name: str, plugin_id: str) -> str:
    """A plugin that writes its sentinel as soon as its module is imported, before OpenCode validates its shape."""
    return (f"import fs from 'fs';\nfs.writeFileSync({json.dumps(str(sentinel / name))}, 'loaded');\n"
            f"export default {{ id: '{plugin_id}', setup: async () => {{}} }};\n")


def plant_project(project: Path, sentinel: Path) -> None:
    """The project layers 2.2.6's bundle reads: ``opencode.json`` and ``opencode.jsonc`` at the root and in
    ``.opencode/`` (agents and commands, and at the root a local MCP server whose command writes a sentinel), the
    singular and plural agent, command, mode and plugin directories, skills under ``.opencode/``, ``.claude/`` and
    ``.agents/``, and tools. The instruction files (``AGENTS.md``, ``CLAUDE.md``, ``instructions``) reach only the
    model-visible request, so they are not planted here (E35's "nothing else loaded" scenario, item 14)."""
    def write(rel: str, text: str) -> None:
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    agent = {"prompt": MARK, "description": MARK}
    write("opencode.json", json.dumps({
        "agent": {f"{MARK}-root-agent": agent}, "command": {f"{MARK}-root-command": {"template": MARK}},
        "mcp": {f"{MARK}-mcp": {"type": "local", "command": ["touch", str(sentinel / "project-mcp")]}}}))
    write(".opencode/opencode.json", json.dumps({
        "agent": {f"{MARK}-dir-agent": agent}, "command": {f"{MARK}-dir-command": {"template": MARK}}}))
    # comments are what make a .jsonc file one: OpenCode must read past them
    write("opencode.jsonc", "// " + MARK + "\n" + json.dumps({"agent": {f"{MARK}-jsonc-agent": agent}}))
    write(".opencode/opencode.jsonc", "// " + MARK + "\n" + json.dumps(
        {"command": {f"{MARK}-jsonc-command": {"template": MARK}}}))
    for kind in ("agent", "agents", "command", "commands", "mode", "modes"):
        write(f".opencode/{kind}/{MARK}-md-{kind}.md", f"---\ndescription: {MARK}\n---\n{MARK}\n")
    for kind in ("plugin", "plugins", "tool", "tools"):
        write(f".opencode/{kind}/probe.js", plugin_source(sentinel, f"project-{kind}", f"{MARK}-{kind}"))
    for base in (".opencode/skill", ".opencode/skills", ".claude/skills", ".agents/skills"):
        name = f"{MARK}-{base.strip('.').replace('/', '-')}"
        write(f"{base}/{name}/SKILL.md", f"---\nname: {name}\ndescription: {MARK}\n---\n{MARK}\n")


def control_config(tmp_path: Path, sentinel: Path) -> dict[str, Any]:
    """The servers' only configuration: a plugin outside the project (OpenCode loads a configured plugin from a
    directory), so its sentinel shows the plugin pass has run."""
    plugin = tmp_path / "control-plugin"
    plugin.mkdir()
    (plugin / "index.js").write_text(plugin_source(sentinel, "control", "aew-control"), encoding="utf-8")
    (plugin / "package.json").write_text(json.dumps({"name": "control", "main": "index.js", "type": "module"}))
    return {"plugin": [str(plugin)]}


def get(client: Client, path: str, where: dict[str, str]) -> Any:
    """A read that waits out OpenCode's "plugins still activating" 503, within the gate."""
    deadline = time.monotonic() + GATE_S
    while True:
        try:
            return client.get(path, where)
        except OpenCodeError as exc:
            if not adapter.plugins_activating(exc) or time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def started(tmp_path: Path, name: str, project: Path, config: dict[str, Any], *, flag: bool):
    """A private server on AEW's own server environment, with the flag as AEW sets it, or removed (the control)."""
    env = adapter.server_env(dict(os.environ), tmp_path / f"state-{name}", provider_env=[], config=config,
                             password=os.urandom(16).hex())
    if not flag:
        env.pop(FLAG)
    assert env.get(FLAG, "") == ("1" if flag else "")
    tree = procs.ProcessTree()
    server = Server.start(tree.spawn, adapter.binary_command(), env=env, cwd=str(project),
                          log_path=tmp_path / f"server-{name}.log")
    return tree, server


def gate(server: Server, sentinel: Path, where: dict[str, str]) -> str:
    """Open the project's location (OpenCode loads a location's configuration and plugins on its first request), wait
    for the control plugin's sentinel, then the settle time. The version read."""
    get(server.client, "/api/config", where)
    deadline = time.monotonic() + GATE_S
    while not (sentinel / "control").exists():
        assert time.monotonic() < deadline, "the control plugin never activated: nothing below would be measured"
        time.sleep(0.25)
    time.sleep(SETTLE_S)
    return str((server.client.get("/api/info") or {}).get("version"))


def record(result: dict[str, Any], tmp_path: Path) -> None:
    (tmp_path / f"{result['run']}.json").write_text(json.dumps(result, indent=1, sort_keys=True))
    if os.environ.get("AEW_LIVE_RESULTS"):
        with open(os.environ["AEW_LIVE_RESULTS"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(result, sort_keys=True) + "\n")


def measure_project(tmp_path: Path, *, flag: bool) -> dict[str, Any]:
    run = "flag" if flag else "control"
    project, sentinel = tmp_path / f"project-{run}", tmp_path / f"sentinel-{run}"
    project.mkdir()
    sentinel.mkdir()
    plant_project(project, sentinel)
    (tmp_path / run).mkdir()
    where = location(os.path.realpath(project))
    tree, server = started(tmp_path, run, project, control_config(tmp_path / run, sentinel), flag=flag)
    try:
        version = gate(server, sentinel, where)
        documents = get(server.client, "/api/config", where) or []
        listed = {path: (get(server.client, path, where) or {}).get("data") or [] for path in CHANNELS}
    finally:
        tree.kill()
    root = os.path.realpath(project)
    result = {
        "run": run, "version": version,
        # the configuration layers the server read that sit in the project (a path, or a document's path)
        "project_layers": sorted({str(d.get("path")) for d in documents
                                  if str(d.get("path", "")).startswith(root)}),
        # what each channel lists that names a marker: its id or name (else the whole entry)
        "listed": {path: sorted(str(item.get("id") or item.get("name") or json.dumps(item, sort_keys=True))
                                for item in items if MARK in json.dumps(item)) for path, items in listed.items()},
        "sentinels": sorted(p.name for p in sentinel.iterdir() if p.name != "control"),
    }
    record(result, tmp_path)
    return result


def test_a_run_loads_nothing_from_the_projects_opencode_directory(tmp_path):
    """With AEW's flag, no project layer is read, no project marker is listed and no project code runs. With the
    flag removed (the same procedure), every one of those channels shows the project: its config files and
    ``.opencode/`` directory are read, its agents, commands, skills, plugins and MCP server are listed, and its
    plugins' code and its MCP command run. A project tool module is not imported at start even in the control, so the
    tool directories are planted but not asserted on."""
    control = measure_project(tmp_path, flag=False)
    root = os.path.realpath(tmp_path / "project-control")
    assert control["project_layers"] == sorted([f"{root}/opencode.json", f"{root}/opencode.jsonc",
                                                f"{root}/.opencode/opencode.json", f"{root}/.opencode/opencode.jsonc",
                                                f"{root}/.opencode"]), control
    named = {kind: {f"{MARK}-{where}-{kind}" for where in ("root", "dir", "jsonc")}
             | {f"{MARK}-md-{kind}", f"{MARK}-md-{kind}s"} for kind in ("agent", "command")}
    named["agent"] |= {f"{MARK}-md-mode", f"{MARK}-md-modes"}  # a mode file is listed as an agent
    assert control["listed"] == {
        "/api/agent": sorted(named["agent"]), "/api/command": sorted(named["command"]),
        "/api/skill": sorted(f"{MARK}-{base}" for base in ("opencode-skill", "opencode-skills", "claude-skills",
                                                            "agents-skills")),
        "/api/plugin": [f"{MARK}-plugin", f"{MARK}-plugins"], "/api/mcp": [f"{MARK}-mcp"]}, control
    assert control["sentinels"] == ["project-mcp", "project-plugin", "project-plugins"], control

    flagged = measure_project(tmp_path, flag=True)
    assert flagged["project_layers"] == [], flagged
    assert all(items == [] for items in flagged["listed"].values()), flagged
    assert flagged["sentinels"] == [], flagged


class WellKnown(http.server.BaseHTTPRequestHandler):
    """A local ``.well-known/opencode`` endpoint that records every request it gets."""
    hits: list[str] = []
    manifest = json.dumps({"auth": {"command": ["true"], "env": "AEW_PROBE_TOKEN"},
                           "config": {"command": {f"{MARK}-wellknown-command": {"template": MARK}}}}).encode()

    def do_GET(self) -> None:
        self.hits.append(self.path)
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(self.manifest)))
        self.end_headers()
        self.wfile.write(self.manifest)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def wellknown():
    WellKnown.hits = []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), WellKnown)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def sources(server: Server, where: dict[str, str], origin: str) -> list[str]:
    return [i.get("id") for i in (get(server.client, "/api/integration", where) or {}).get("data") or []
            if origin in json.dumps(i)]


def test_no_project_file_adds_a_wellknown_source(tmp_path, wellknown):
    """The remote layer's sources are, in the bundle, one list in the server's own database (``wellknown:sources``),
    in AEW's private state, set only by the server's route and by a one-time import of the legacy ``auth.json`` in the
    XDG data directory; no project path feeds it. The control: the route adds one, with the server password, and the
    server fetches its manifest and lists it; without the password the route is refused. Then the project names the
    same origin in the shapes nearest those inputs (the legacy credential file's ``wellknown`` entries, at the
    project's root and in ``.opencode/``, a served-looking ``.well-known/opencode``, and a config key), with the flag
    and without it: no fetch, no source. Without the flag the project's ``.opencode/opencode.json`` is read, so its
    key was seen and ignored."""
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    config = control_config(tmp_path, sentinel)

    empty = tmp_path / "project-route"
    empty.mkdir()
    where = location(os.path.realpath(empty))
    tree, server = started(tmp_path, "route", empty, config, flag=True)
    try:
        version = gate(server, sentinel, where)
        with pytest.raises(OpenCodeError) as refused:
            Client(server.url, "not-" + server.password).post("/api/experimental/integration/wellknown",
                                                              {"url": wellknown}, where)
        assert refused.value.status == 401, refused.value
        assert WellKnown.hits == [] and sources(server, where, wellknown) == []
        server.client.post("/api/experimental/integration/wellknown", {"url": wellknown}, where)
        added = sources(server, where, wellknown)
    finally:
        tree.kill()
    assert WellKnown.hits == ["/.well-known/opencode"], WellKnown.hits
    assert added == [wellknown], added
    record({"run": "wellknown-route", "version": version, "hits": list(WellKnown.hits), "sources": added}, tmp_path)

    legacy = json.dumps({wellknown: {"type": "wellknown", "key": "AEW_PROBE_TOKEN", "token": MARK}})
    for flag in (True, False):
        WellKnown.hits = []
        run = f"wellknown-project-{'flag' if flag else 'control'}"
        project = tmp_path / run
        for rel in ("auth.json", ".opencode/auth.json", ".well-known/opencode"):
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
            (project / rel).write_text(legacy, encoding="utf-8")
        (project / ".opencode" / "opencode.json").write_text(json.dumps({"wellknown": [wellknown]}))
        where = location(os.path.realpath(project))
        (sentinel / "control").unlink()
        tree, server = started(tmp_path, run, project, config, flag=flag)
        try:
            version = gate(server, sentinel, where)
            found = sources(server, where, wellknown)
            layers = {str(d.get("path")) for d in get(server.client, "/api/config", where) or []}
        finally:
            tree.kill()
        record({"run": run, "version": version, "hits": list(WellKnown.hits), "sources": found}, tmp_path)
        assert WellKnown.hits == [] and found == [], (run, WellKnown.hits, found)
        read = os.path.join(os.path.realpath(project), ".opencode", "opencode.json") in layers
        assert read is not flag, (run, sorted(layers))
