"""The contained Lead's session, as a test drives it on Linux (STG-05 CS-4).

`aew opencode` runs at a terminal (a pseudo-terminal the test holds as the operator's), with its broker on the host,
and a fake TUI (the `opencode` launcher below) in the Lead's sandbox, on the relayed terminal. The fake TUI either acts
as the Lead's model would, through `aew` and the broker (the fake agent, whose steps are raw tool actions that no
harness permission rule sees), or calls each relayed provider the way its SDK would. The operator's home is synthetic:
no real OpenCode login is ever read. Used by tests/integration/test_lead_contained_session.py and by the server
residual's tests in tests/integration/test_opencode_adapter.py (ST-38), which cover a worker's run and the Lead's
session alike.
"""

from __future__ import annotations

import http.server
import json
import os
import select
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aewflow import sample_project
from conftest import clean_env
from discovery.rules import split_refusal
from fake_harness import AGENT, POLICY, HarnessLab
from fake_opencode import CREDENTIAL_TABLE as CREDENTIAL_TABLE

from aew.harness import procs
from aew.harness.opencode.capabilities import TESTED_VERSIONS

KEYS = {"openai": "sk-synthetic-openai-0001", "anthropic": "sk-ant-synthetic-0002", "opencode": "synthetic-oc-0003"}
SECRET = "sk-provider-secret-must-not-reach-the-lead-model"
# The operator's TUI preferences (`cli.json`, with a plugin the Lead leaves out) and recent models (`model.json`).
PREFERENCES = {"theme": {"name": "synthetic"}, "plugins": ["synthetic-plugin"]}
RECENT_MODELS = {"recent": [{"providerID": "openai", "modelID": "gpt-5.5"}]}

LAUNCHER = """import json, os, pathlib, sqlite3, sys, time
here = pathlib.Path(__file__).resolve().parent
if sys.argv[1:2] == ["--version"]:
    print("opencode v{version}")
    sys.exit(0)
db = pathlib.Path(os.environ.get("XDG_DATA_HOME", "/nonexistent")) / "opencode" / "opencode.db"
if sys.argv[1:3] == ["session", "list"]:  # its first run makes its database, as 2.0.18's does
    db.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(db).execute({table!r}).connection.commit()
    (here / "made-db").write_text("x")
    sys.exit(0)
if sys.argv[1:2] == ["serve"]:  # the Lead's server: it announces an address, and its lease is its stdin
    (here / "serve-argv.json").write_text(json.dumps(sys.argv[1:]))
    print(json.dumps({{"url": "http://127.0.0.1:4100"}}), flush=True)
    sys.stdin.buffer.read()
    sys.exit(0)
for name in ("OPENCODE_PASSWORD", "OPENCODE_SERVER_PASSWORD"):  # the real server removes them (--stdio, measured)
    os.environ.pop(name, None)
(here / "tui-argv.json").write_text(json.dumps(sys.argv[1:]))
if (here / "mode").read_text().strip() == "agent":
    sys.argv = ["fake_agent", "--script", str(here / "tui-script.json"), "--transcript", str(here / "tui.jsonl")]
    sys.path.insert(0, {helpers!r})
    import fake_agent
    sys.exit(fake_agent.main())
# The providers: call each relayed provider at the baseURL its configuration names, with the variable its SDK reads,
# or, for a provider in oauth.json, with its row in the TUI's own login store, as the ChatGPT login's plugin does
# (its access token, and its account id in chatgpt-account-id). rounds.json asks for more rounds: before each, the
# fake says round-<n> and waits for go-<n>.
import http.client, urllib.parse
config = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
out = {{"env": dict(os.environ), "calls": {{}}, "later": [], "visible": {{}}, "logins": []}}
oauth = json.loads((here / "oauth.json").read_text()) if (here / "oauth.json").exists() else []
if oauth:
    out["logins"] = [{{"integration": i, **json.loads(v)}} for i, v in sqlite3.connect(
        f"{{db.as_uri()}}?mode=ro", uri=True).execute("SELECT integration_id, value FROM credential WHERE active = 1")]
def call(provider, headers):
    settings = config.get("providers", {{}}).get(provider, {{}}).get("settings", {{}})
    base = urllib.parse.urlsplit(settings.get("baseURL", ""))
    if not base.port:
        return None
    try:
        conn = http.client.HTTPConnection(base.hostname, base.port, timeout=10)
        conn.request("POST", base.path + "/probe", body=b"{{}}", headers={{**headers, "Content-Type": "x"}})
        answer = conn.getresponse()
        return [answer.status, answer.read().decode()]
    except OSError as exc:
        return [None, repr(exc)]
def one_round():
    calls = {{}}
    for provider, variable in json.loads((here / "variables.json").read_text()).items():
        calls[provider] = call(provider, {{"Authorization": "Bearer " + os.environ.get(variable, "")}})
    for row in (r for r in out["logins"] if r["integration"] in oauth and r.get("type") == "oauth"):
        calls[row["integration"]] = call(row["integration"], {{
            "Authorization": "Bearer " + row["access"],
            "chatgpt-account-id": row.get("metadata", {{}}).get("accountID", "")}})
    return {{p: c for p, c in calls.items() if c is not None}}
out["calls"] = one_round()
rounds = int((here / "rounds.json").read_text()) if (here / "rounds.json").exists() else 1
for n in range(1, rounds):
    (here / f"round-{{n}}").write_text("x")
    deadline = time.monotonic() + 60
    while not (here / f"go-{{n}}").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    out["later"].append(one_round())
for path in json.loads((here / "look.json").read_text()):
    out["visible"][path] = sorted(os.listdir(path)) if os.path.isdir(path) else os.path.exists(path)
(here / "inside.json").write_text(json.dumps(out))
"""


class Upstream:
    """A provider's stand-in upstream on the host's loopback: it records each request's path and Authorization, and
    its account header (the ChatGPT login's) apart."""

    def __init__(self, *, path: str = "/v1") -> None:
        self.seen: list[tuple[str, str]] = []
        self.accounts: list[str] = []
        seen, accounts = self.seen, self.accounts

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802  # http.server's naming
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                seen.append((self.path, self.headers.get("Authorization") or ""))
                accounts.append(self.headers.get("chatgpt-account-id") or "")
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: Any) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}{path}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def synthetic_home(root: Path, logins: dict[str, str] | None = None,
                   oauth: dict[str, dict[str, Any]] | None = None) -> Path:
    """The operator's home: a synthetic OpenCode login database (2.0.18's schema), with an API key for each provider
    in ``logins`` and an OAuth value for each in ``oauth``, and a configuration with an MCP server, which the
    contained Lead must neither show nor load."""
    from aew.harness.opencode import login

    home = root / "home"
    db = home / ".local" / "share" / "opencode" / login.DB
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.execute(CREDENTIAL_TABLE)
    rows = [*((p, "api", {"type": "key", "key": k}) for p, k in (logins or {}).items()),
            *((p, str(v.get("methodID")), v) for p, v in (oauth or {}).items())]
    for i, (provider, method, value) in enumerate(rows):
        con.execute("INSERT INTO credential VALUES (?, ?, 'l', ?, NULL, ?, 1, 1, 1)",
                    (f"cred_{i}", provider, json.dumps(value), method))
    con.commit()
    con.close()
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "opencode.json").write_text('{"mcp": {"servers": {"docs": {}}}}\n')
    (home / ".config" / "opencode" / "cli.json").write_text(json.dumps(PREFERENCES))
    state = home / ".local" / "state" / "opencode"
    state.mkdir(parents=True)
    (state / "model.json").write_text(json.dumps(RECENT_MODELS))
    (state / "prompt-history.jsonl").write_text('{"input": "synthetic prompt of another project"}\n')
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
    launcher = LAUNCHER.format(helpers=str(AGENT.parent), table=CREDENTIAL_TABLE, version=TESTED_VERSIONS[0])
    (tui / "opencode.py").write_text(launcher, encoding="utf-8")
    lab.env["AEW_OPENCODE_BIN"] = str(tui / "opencode.py")
    return lab, tui


def at_the_terminal(lab: HarnessLab, home: Path, *args: str, extra: dict[str, str] | None = None,
                    timeout: float = 120, refreshing_upstream: str | None = None) -> dict[str, Any]:
    """`aew opencode` at a terminal the test holds: standard input is a pseudo-terminal that is its controlling
    terminal (as at the operator's shell); its standard output and error are collected. Returns the exit code, the
    result JSON (after the relay's reset), the refusal's error with what stderr held before and after it
    (``discovery.rules.split_refusal``), and whether the terminal got its settings back. A synthetic refreshing
    upstream replaces the built-in URL in the test subprocess only."""
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
        refreshing_upstream = sys.argv.pop(1)
        if not refreshing_upstream:
            os.execv(sys.executable, [sys.executable, "-m", "aew", *sys.argv[1:]])

        import runpy
        from aew.harness.containment import netns

        netns.REFRESHING_UPSTREAMS["openai"] = refreshing_upstream
        runpy.run_module("aew", run_name="__main__", alter_sys=True)
    """)
    command = [sys.executable, "-c", wrapper, refreshing_upstream or "", "-C", str(lab.root), "opencode", *args]
    proc = subprocess.Popen(command, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
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
    stderr = err.decode("utf-8", "replace")
    ahead, error, after = split_refusal(stderr) if proc.returncode else (stderr, None, "")
    return {"code": proc.returncode, "result": result, "stdout": out, "stderr": stderr, "error": error,
            "before": ahead, "after": after.strip(), "restored": restored, "terminal": bytes(shown)}


def agent_session(tmp_path: Path, steps: list[dict[str, Any]] | Callable[[HarnessLab], list[dict[str, Any]]], *,
                  logins: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[int, Any]]:
    """A contained Lead session in its own project under ``tmp_path`` whose model takes ``steps`` (the fake agent's,
    or made from the lab) and ends: the session's result and each step's result. The operator's stored login holds
    ``logins``, by default one synthetic key (a Lead with no provider relayed is refused at start: the designer's
    ruling of 2026-11-06)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    lab, tui = make_lab(tmp_path)
    try:
        home = synthetic_home(tmp_path, {"anthropic": KEYS["anthropic"]} if logins is None else logins)
        (tui / "mode").write_text("agent")
        (tui / "tui-script.json").write_text(json.dumps(steps(lab) if callable(steps) else steps))
        done = at_the_terminal(lab, home)
        assert done["code"] == 0, done["stderr"][-3000:]
        transcript = tui / "tui.jsonl"
        lines = transcript.read_text().splitlines() if transcript.exists() else []
        return done, {e["i"]: e["result"] for e in map(json.loads, lines)}
    finally:
        lab.cleanup()


def guide_of(lab: HarnessLab) -> str:
    from aew.engine.api import Engine
    from aew.surface import lead_text

    return lead_text.guide_for(Engine.discover(lab.root))
