"""The contained Lead's session end to end, on Linux (STG-05 CS-4, outcomes 1 to 3, 6 and 7).

`aew opencode` runs at a terminal (a pseudo-terminal this test holds as the operator's), with its broker on the host,
and a fake TUI (the `opencode` launcher below) in the Lead's sandbox, on the relayed terminal. The fake TUI either acts
as the Lead's model would, through `aew` and the broker (the fake agent), or calls each relayed provider the way its SDK
would. The operator's home is synthetic: no real OpenCode login is ever read. tests/integration/test_opencode_lead.py
has the session's Windows path, which runs labelled not contained.
"""

from __future__ import annotations

import http.server
import json
import os
import select
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from aewflow import sample_project
from conftest import clean_env
from fake_harness import AGENT, POLICY, HarnessLab, contains_credential

from aew.harness import procs
from aew.harness.containment import netns
from aew.harness.opencode import lead, login, projection

pytestmark = [pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                                 reason="the Lead is contained on Linux (bubblewrap); Windows runs it labelled not "
                                 "contained"), pytest.mark.autopsy]

KEYS = {"openai": "sk-synthetic-openai-0001", "anthropic": "sk-ant-synthetic-0002", "opencode": "synthetic-oc-0003"}
SECRET = "sk-provider-secret-must-not-reach-the-lead-model"

LAUNCHER = """import json, os, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
if sys.argv[1:2] == ["--version"]:
    print("opencode v2.0.18")
    sys.exit(0)
(here / "tui-argv.json").write_text(json.dumps(sys.argv[1:]))
if (here / "mode").read_text().strip() == "agent":
    sys.argv = ["fake_agent", "--script", str(here / "tui-script.json"), "--transcript", str(here / "tui.jsonl")]
    sys.path.insert(0, {helpers!r})
    import fake_agent
    sys.exit(fake_agent.main())
# The providers: call each relayed provider at the baseURL its configuration names, with the variable its SDK reads.
import http.client, urllib.parse
config = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
out = {{"env": dict(os.environ), "calls": {{}}, "visible": {{}}}}
for provider, variable in json.loads((here / "variables.json").read_text()).items():
    settings = config.get("providers", {{}}).get(provider, {{}}).get("settings", {{}})
    base = urllib.parse.urlsplit(settings.get("baseURL", ""))
    if not base.port:
        continue
    try:
        conn = http.client.HTTPConnection(base.hostname, base.port, timeout=10)
        conn.request("POST", base.path + "/probe", body=b"{{}}",
                     headers={{"Authorization": "Bearer " + os.environ.get(variable, ""), "Content-Type": "x"}})
        answer = conn.getresponse()
        out["calls"][provider] = [answer.status, answer.read().decode()]
    except OSError as exc:
        out["calls"][provider] = [None, repr(exc)]
for path in json.loads((here / "look.json").read_text()):
    out["visible"][path] = sorted(os.listdir(path)) if os.path.isdir(path) else os.path.exists(path)
(here / "inside.json").write_text(json.dumps(out))
"""


class Upstream:
    """A provider's stand-in upstream on the host's loopback: it records each request's path and Authorization."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []
        seen = self.seen

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802  # http.server's naming
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                seen.append((self.path, self.headers.get("Authorization") or ""))
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: Any) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def synthetic_home(root: Path, logins: dict[str, str] | None = None) -> Path:
    """The operator's home: a synthetic OpenCode login database (2.0.18's schema) and configuration with an MCP
    server, which the contained Lead must neither show nor load."""
    home = root / "home"
    db = home / ".local" / "share" / "opencode" / login.DB
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE credential (id text PRIMARY KEY, integration_id text, label text NOT NULL, value text "
                "NOT NULL, connector_id text, method_id text, active integer, time_created integer NOT NULL, "
                "time_updated integer NOT NULL)")
    for i, (provider, key) in enumerate((logins or {}).items()):
        con.execute("INSERT INTO credential VALUES (?, ?, 'l', ?, NULL, 'api', 1, 1, 1)",
                    (f"cred_{i}", provider, json.dumps({"type": "key", "key": key})))
    con.commit()
    con.close()
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "opencode.json").write_text('{"mcp": {"servers": {"docs": {}}}}\n')
    return home


def make_lab(tmp_path: Path, *, upstreams: dict[str, str] | None = None, mode: str | None = None,
             writable_extra: list[str] = ()) -> tuple[HarnessLab, Path]:  # type: ignore[assignment]
    tui = tmp_path / "sync" / "tui"
    containment: dict[str, Any] = {"writable": [str(tmp_path / "fake-scripts"), str(tmp_path / "sync"),
                                                *writable_extra]}
    if upstreams:
        containment["network"] = {"upstreams": upstreams}
    if mode:
        containment["mode"] = mode
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy={**POLICY, "containment": containment},
                            extra_env={"OPENAI_API_KEY": SECRET})
    tui.mkdir(parents=True)
    (tui / "opencode.py").write_text(LAUNCHER.format(helpers=str(AGENT.parent)), encoding="utf-8")
    lab.env["AEW_OPENCODE_BIN"] = str(tui / "opencode.py")
    return lab, tui


def at_the_terminal(lab: HarnessLab, home: Path, *args: str, extra: dict[str, str] | None = None,
                    timeout: float = 120) -> dict[str, Any]:
    """`aew opencode` at a terminal the test holds: standard input is a pseudo-terminal that is its controlling
    terminal (as at the operator's shell); its standard output and error are collected. Returns the exit code, the
    result JSON (after the relay's reset), the error, and whether the terminal got its settings back."""
    import pty
    import termios

    master, slave = pty.openpty()
    before = termios.tcgetattr(slave)
    env = clean_env({**lab.env, "AEW_LEAD_TOKEN": lab.project.token, "HOME": str(home), **(extra or {})})
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "OPENCODE_DB",
                 "OPENCODE_CONFIG"):
        env.pop(name, None)  # the synthetic home's defaults, never the runner's own OpenCode
    wrapper = textwrap.dedent("""
        import fcntl, os, sys, termios
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        os.execv(sys.executable, [sys.executable, "-m", "aew", *sys.argv[1:]])
    """)
    proc = subprocess.Popen([sys.executable, "-c", wrapper, "-C", str(lab.root), "opencode", *args], stdin=slave,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    shown = bytearray()
    try:
        deadline = time.monotonic() + timeout
        while proc.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                shown += os.read(master, 65536)
        if proc.poll() is None:
            proc.kill()
        out, err = proc.communicate(timeout=30)
        restored = termios.tcgetattr(slave) == before
    finally:
        os.close(master)
        os.close(slave)
    text = out.decode("utf-8", "replace").rsplit(procs.TERMINAL_LEAVE.decode(), 1)[-1].strip()
    try:
        result = json.loads(text) if text else None
    except ValueError:
        result = None
    error = None
    if proc.returncode:
        try:
            error = json.loads(err.decode()[err.decode().index("{"):])["error"]
        except (ValueError, KeyError):
            error = None
    return {"code": proc.returncode, "result": result, "stdout": out, "stderr": err.decode("utf-8", "replace"),
            "error": error, "restored": restored, "terminal": bytes(shown)}


def guide_of(lab: HarnessLab) -> str:
    from aew.engine.api import Engine

    return Engine.discover(lab.root).lead_guide()


# --------------------------------------------------------------------------------------- outcomes 1, 2, 6 and 7

def test_the_contained_lead_acts_through_its_broker_from_its_sandbox_on_its_relayed_terminal(tmp_path):
    """The TUI runs in a self-tested `lead` sandbox (rows 1 to 6 on the label, with the network: `proxy_only`, any
    public address), on the relayed terminal, which gets its settings back at the end. Its environment is AEW's: no
    AEW credential, no provider key, no operator `XDG_*` or OpenCode configuration, AEW's XDG directories under
    `.aew/local/harness`, both proxy variables at the egress proxy, and the contained line in its system text. From
    there the Lead's model mutates AEW state through the broker, a credential-emitting command is refused, and a read
    works."""
    lab, tui = make_lab(tmp_path)
    try:
        home = synthetic_home(tmp_path)
        (tui / "mode").write_text("agent")
        sync = tmp_path / "sync"
        (tui / "tui-script.json").write_text(json.dumps([
            {"do": "dump_env", "path": str(sync / "env")},
            {"do": "aew", "args": ["lead", "show"]},
            {"do": "lead", "args": ["checkpoint", "--next", "dispatch T-0001 with --launch"]},
            {"do": "aew", "args": ["lead", "handoff", "offer", "--expect-rev", "1"]},
            {"do": "aew", "args": ["resume", "--json"]},
            {"do": "read", "path": str(home / ".local/share/opencode/opencode.db")}]))
        done = at_the_terminal(lab, home, extra={"XDG_RUNTIME_DIR": str(tmp_path / "operator-runtime"),
                                                 "XDG_CURRENT_DESKTOP": "operator-desktop",
                                                 "XDG_DATA_DIRS": str(tmp_path / "operator-data-dirs")})
        assert done["code"] == 0, done["stderr"][-3000:]
        out = done["result"]
        transcript = (tui / "tui.jsonl").read_text() if (tui / "tui.jsonl").exists() else ""
        assert out["exit"] == 0, (done["stdout"].split(procs.TERMINAL_LEAVE)[0][-3000:], transcript)
        assert (out["seat"], out["opencode"]) == ("held by your AEW_LEAD_TOKEN", "2.0.18")
        label = out["containment"]
        assert label["filesystem"] == "os_readonly_roots" and sorted(label["self_test"]["rows"]) == list("123456")
        assert all(r["ok"] for r in label["self_test"]["rows"].values())
        assert label["network"]["mode"] == "proxy_only" and label["network"]["egress_policy"] == "any_public"
        run_dir = lab.aew_root / "local" / "harness" / "runs" / label["session"]
        assert json.loads((run_dir / "label.json").read_text())["session"] == label["session"]
        assert done["restored"]
        assert json.loads((tui / "tui-argv.json").read_text()) == ["--standalone", str(lab.root)]

        env = json.loads((sync / "env").read_text())
        assert SECRET not in json.dumps(env) and not contains_credential(json.dumps(env))
        assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "OPENAI_API_KEY", "AEW_OPENCODE_BIN",
                    "OPENCODE_CONFIG"} & set(env)
        assert {"AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"} <= set(env) and env[lead.CONTAINED_ENV] == "1"
        harness = str(lab.aew_root / "local" / "harness")
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
            assert env[name].startswith(harness), (name, env[name])
        assert {k for k in env if k.startswith("XDG_")} == {"XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                                                            "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"}  # none the operator's
        egress = f"http://127.0.0.1:{netns.EGRESS_PORT}"
        assert env["HTTPS_PROXY"] == env["HTTP_PROXY"] == egress and "127.0.0.1" in env["NO_PROXY"]
        assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == projection.lead_config(guide_of(lab), contained=label)
        assert "your OpenCode configuration is not loaded in the contained Lead; its MCP servers are left out: docs" \
            in done["stderr"]

        steps = {e["i"]: e["result"] for e in map(json.loads, (tui / "tui.jsonl").read_text().splitlines())}
        assert steps[1]["exit"] == 0 and "revision" in steps[1]["stdout_json"], steps[1]  # a read, lock-free
        assert steps[2]["exit"] == 0, steps[2]  # a Lead mutation, carried out by the broker on the host
        assert ((steps[3].get("stderr_json") or {}).get("error") or {}).get("code") == "USAGE"
        assert steps[4]["stdout_json"]["lead_note"] == "dispatch T-0001 with --launch"
        assert steps[5] == {"readable": False, "error": "FileNotFoundError"}  # the login store is masked
    finally:
        lab.cleanup()


# --------------------------------------------------------------------------------------------------- outcome 3

def test_every_provider_in_the_stored_login_has_its_own_relay_and_the_sandbox_holds_only_sentinels(tmp_path):
    """Each provider of the operator's stored login whose key OpenCode reads from a known variable gets its own relay
    on the host: from inside, a call to the baseURL its configuration names, with the variable its SDK reads, reaches
    that provider's upstream with the real key, while the sandbox holds only a sentinel. opencode's key is not relayed
    (its models carry their own catalog address) and is not inside at all. `--provider-env` feeds google's relay."""
    ups = {p: Upstream() for p in ("openai", "anthropic", "google")}
    try:
        lab, tui = make_lab(tmp_path, upstreams={p: u.url for p, u in ups.items()})
        try:
            home = synthetic_home(tmp_path, KEYS)
            (tui / "mode").write_text("providers")
            (tui / "variables.json").write_text(json.dumps(netns.PROVIDER_KEY_ENV))
            (tui / "look.json").write_text(json.dumps([str(home / ".local/share/opencode"),
                                                       str(home / ".config/opencode")]))
            fed = "synthetic-google-fed-0005"
            done = at_the_terminal(lab, home, "--provider-env", "GOOGLE_GENERATIVE_AI_API_KEY",
                                   extra={"GOOGLE_GENERATIVE_AI_API_KEY": fed})
            assert done["code"] == 0, done["stderr"][-3000:]
            inside = json.loads((tui / "inside.json").read_text())
            blob = json.dumps(inside["env"])
            for value in (*KEYS.values(), fed, SECRET):
                assert value not in blob
            relays = done["result"]["containment"]["network"]["provider_relays"]
            assert relays == {p: u.url for p, u in ups.items()}
            for provider, upstream in ups.items():
                sentinel = inside["env"][netns.PROVIDER_KEY_ENV[provider]]
                assert sentinel.startswith("aew-relay-")
                assert inside["calls"][provider][0] == 200, inside["calls"]
                want = fed if provider == "google" else KEYS[provider]
                assert upstream.seen == [("/v1/probe", f"Bearer {want}")], (provider, upstream.seen)
            assert "OPENCODE_API_KEY" not in inside["env"] and "opencode" not in inside["calls"]
            # empty under the mask, or absent where the home is under /tmp, private inside (the mask itself:
            # tests/integration/test_lead_containment.py, whose home is not)
            assert all(seen in ([], False) for seen in inside["visible"].values()), inside["visible"]
            assert "opencode (key): not relayed" in done["stderr"]
            assert "--provider-env GOOGLE_GENERATIVE_AI_API_KEY feeds the google relay on the host" in done["stderr"]
        finally:
            lab.cleanup()
    finally:
        for u in ups.values():
            u.close()


# --------------------------------------------------------------------------------------------- outcomes 1 and 6

def test_a_lead_whose_containment_fails_is_refused_under_required_and_runs_labelled_under_allow_weaker(tmp_path):
    """Required (the default): nothing runs, and the refusal says what failed and what fixes it. Allow-weaker: the TUI
    runs as it does elsewhere, labelled workdir_separation_only with the reason, and the start line says so."""
    missing = str(tmp_path / "no-such-root")
    lab, tui = make_lab(tmp_path, writable_extra=[missing])
    try:
        home = synthetic_home(tmp_path)
        (tui / "mode").write_text("agent")
        (tui / "tui-script.json").write_text(json.dumps([]))
        refused = at_the_terminal(lab, home)
        assert refused["code"] != 0 and refused["error"]["code"] == "CONTAINMENT_UNAVAILABLE", refused["stderr"]
        assert "not an existing directory" in refused["error"]["message"] and refused["restored"]
        assert not (tui / "tui-argv.json").exists()
    finally:
        lab.cleanup()
    weaker_root = tmp_path / "weaker"
    weaker_root.mkdir()
    lab, tui = make_lab(weaker_root, mode="allow_weaker", writable_extra=[missing])
    try:
        home = synthetic_home(weaker_root)
        (tui / "mode").write_text("agent")
        (tui / "tui-script.json").write_text(json.dumps([]))
        done = at_the_terminal(lab, home)
        assert done["code"] == 0, done["stderr"][-3000:]
        label = done["result"]["containment"]
        assert label["filesystem"] == "workdir_separation_only"
        assert "not an existing directory" in label["weaker_because"]
        assert "the Lead runs NOT contained" in done["stderr"]
        assert (tui / "tui-argv.json").exists()
    finally:
        lab.cleanup()
