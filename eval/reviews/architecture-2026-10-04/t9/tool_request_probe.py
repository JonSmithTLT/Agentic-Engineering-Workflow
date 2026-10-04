"""T9 live probe 1 (and T1's remaining live check): what tool schemas reach the model from OpenCode 2.0.18, with the
Lead projection's MCP server (`aew lead mcp`) spawned for real, and whether a permission `deny` removes a tool from
the request.

Run on the VM, in the review venv with the T1 patch applied (~/aew-review/dcd43f1):

    source ~/aew-review/venv/bin/activate
    python tool_request_probe.py ~/opencode-2.0.18/opt/OpenCode/resources/opencode-cli

Method: a fake OpenAI-compatible endpoint on the host loopback logs every request body and answers 500 (the model
never runs). The built-in `openai` provider is pointed at it (`providers.openai.settings.baseURL`; fallback: a
custom provider with package @ai-sdk/openai-compatible). A session with the `aew-lead` agent is prompted once per
variant; the logged request's `tools` array is the measurement.

Variants:
  V0  the Lead projection without an MCP server (baseline built-in tool set as the model sees it)
  V1  with mcp.servers.aew = `aew lead mcp` (T1), cwd = a lab AEW project, AEW_LEAD_TOKEN in its environment
  V2  V1 plus a permission rule denying the `aew_cli` tool: does it leave the request?
  V3  V1 plus `aew_*` denied entirely
  V4  V1 with the MCP server's `environment` lacking AEW_LEAD_TOKEN (the server must refuse to start: no bridge, no
      token); what does OpenCode do with a server that exits?

A real Lead credential is acquired on the lab project (`aew lead acquire`) and kept only in memory and in the
spawned server's environment; it is never written to a file here. The lab project is removed at the end.
"""

from __future__ import annotations

import base64
import http.client
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/opencode-2.0.18/opt/OpenCode/resources/opencode-cli")
OUT: list[str] = []
MODEL = {"providerID": "openai", "model": "gpt-6-sol"}
SESSION_MODEL = {"providerID": "openai", "id": "gpt-6-sol"}


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


# ------------------------------------------------------------------------------------------ the fake model endpoint

class Captured:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.lock = threading.Lock()


def fake_endpoint(cap: Captured) -> http.server.ThreadingHTTPServer:
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = {"_raw": raw[:200].decode(errors="replace")}
            with cap.lock:
                cap.requests.append({"path": self.path, "bytes": len(raw), "body": body,
                                     "auth_present": bool(self.headers.get("Authorization"))})
            msg = json.dumps({"error": {"message": "probe endpoint: no model here", "type": "server_error"}}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

        def do_GET(self):
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()

        def log_message(self, *a): pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ------------------------------------------------------------------------------------------ the lab AEW project

def sh(*argv: str, cwd: str | None = None, env: dict | None = None, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), cwd=cwd, env=env, input=input, capture_output=True, text=True, timeout=120)


def make_lab(base: Path) -> tuple[Path, str, int]:
    """A git repository with `aew init` run and the Lead seat acquired; the credential and the revision."""
    lab = Path(tempfile.mkdtemp(prefix="review-t9-lab-", dir=base))
    repo = lab / "project"
    repo.mkdir()
    genv = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    for cmd in (("git", "init", "-q", "-b", "main"),):
        sh(*cmd, cwd=str(repo), env=genv)
    (repo / "README.md").write_text("# probe\n", encoding="utf-8")
    sh("git", "add", ".", cwd=str(repo), env=genv)
    sh("git", "commit", "-qm", "seed", cwd=str(repo), env=genv)
    r = sh("aew", "init", "--json", cwd=str(repo), env=genv)
    if r.returncode != 0:
        r = sh("aew", "init", cwd=str(repo), env=genv)
    assert r.returncode == 0, r.stderr[-500:]
    r = sh("aew", "lead", "acquire", "--expect-rev", "0", "--session-label", "probe", "--json", cwd=str(repo), env=genv)
    if r.returncode != 0:
        r = sh("aew", "lead", "acquire", "--expect-rev", "0", "--session-label", "probe", cwd=str(repo), env=genv)
    assert r.returncode == 0, r.stderr[-500:] + r.stdout[-500:]
    import re
    m = re.search(r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}", r.stdout + r.stderr)
    assert m, f"no credential in the acquire output ({r.stdout[:200]!r})"
    token = m.group(0)
    mrev = re.search(r'"revision":\s*(\d+)|revision[^0-9]*(\d+)', r.stdout)
    rev = int(next(g for g in (mrev.groups() if mrev else ()) if g) or 1) if mrev else 1
    return repo, token, int(rev)


# ------------------------------------------------------------------------------------------ one OpenCode variant

PROVIDER_MODE = {"mode": "openai-baseurl"}


def opencode_config(variant: str, *, base_url: str, repo: Path, token: str | None, venv_bin: str) -> dict:
    sys.path.insert(0, str(Path(venv_bin).parent.parent))  # not needed when the venv is active; harmless
    from aew.harness.opencode import projection as P
    from aew.surface import contract as C

    cfg = P.lead_config(guide="")
    cfg.update({"snapshots": False, "update": "disable", "lsp": False, "formatter": False,
                "plugins": [P.COMPATIBILITY_PLUGIN]})
    if PROVIDER_MODE["mode"] == "openai-baseurl":
        cfg["providers"] = {"openai": {"settings": {"baseURL": base_url}}}
    else:
        cfg["providers"] = {"probe": {"package": "@ai-sdk/openai-compatible", "name": "Probe", "env": ["PROBE_API_KEY"],
                                      "settings": {"baseURL": base_url},
                                      "models": {"gpt-6-sol": {"name": "probe model", "limit": {"context": 200000, "output": 32000}}}}}
    cfg["agents"][P.LEAD_AGENT]["model"] = dict(MODEL)
    for name in P.AUXILIARY_AGENTS:
        cfg["agents"][name] = {"model": dict(MODEL)}
    rules = list(cfg["agents"][P.LEAD_AGENT]["permissions"])
    if variant == "V0":
        cfg.pop("mcp", None)
    else:
        env = {"PATH": f"{venv_bin}:{os.environ.get('PATH', '')}", "HOME": os.environ.get("HOME", "")}
        if token and variant != "V4":
            env["AEW_LEAD_TOKEN"] = token
        cfg["mcp"] = {"servers": {C.SERVER_NAME: {"type": "local", "command": ["aew", "lead", "mcp"],
                                                  "cwd": str(repo), "environment": env}}}
        if variant == "V5":  # Code Mode off: the server's tools are exposed to the model directly
            cfg["mcp"]["servers"][C.SERVER_NAME]["codemode"] = False
        if variant == "V6":  # run-style rules: nothing not named exists for the agent
            rules = [P.rule("*", "deny")] + [P.rule(a, "allow") for a in ("read", "glob", "grep", "shell")]
            cfg["mcp"]["servers"][C.SERVER_NAME]["codemode"] = False
        if variant == "V2":
            rules.append(P.rule("aew_cli", "deny"))
        if variant == "V3":
            rules.append(P.rule("aew_*", "deny"))
    cfg["agents"][P.LEAD_AGENT]["permissions"] = rules
    cfg["permissions"] = rules
    return cfg


def run_variant(variant: str, *, cap: Captured, base_url: str, repo: Path, token: str | None, work: Path) -> dict:
    venv_bin = str(Path(sys.executable).parent)
    cfg = opencode_config(variant, base_url=base_url, repo=repo, token=token, venv_bin=venv_bin)
    state = work / variant
    for d in ("config", "data", "cache", "state", "tmp"):
        (state / d).mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "USER", "LANG", "TERM")}
    env.update({"XDG_CONFIG_HOME": str(state / "config"), "XDG_DATA_HOME": str(state / "data"),
                "XDG_CACHE_HOME": str(state / "cache"), "XDG_STATE_HOME": str(state / "state"), "TMPDIR": str(state / "tmp"),
                "OPENCODE_CONFIG_CONTENT": json.dumps(cfg), "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
                "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_PASSWORD": "probe-password",
                "OPENAI_API_KEY": "sk-dummy-not-a-key", "PROBE_API_KEY": "sk-dummy-not-a-key"})
    (state / "config.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    log = open(state / "server.log", "wb")
    p = subprocess.Popen([CLI, "serve", "--stdio", "--hostname", "127.0.0.1", "--port", "0"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=log, env=env, cwd=str(repo), text=True)
    out: dict = {"variant": variant}
    t0 = time.perf_counter()
    url = None
    while time.perf_counter() - t0 < 60:
        line = p.stdout.readline()
        if not line:
            break
        if line.startswith("{"):
            url = json.loads(line).get("url"); break
    out["start_s"] = round(time.perf_counter() - t0, 2)
    if not url:
        out["error"] = "server did not announce"; p.kill(); return out
    host, port = url.split("//")[1].rstrip("/").split(":")
    auth = "Basic " + base64.b64encode(b"opencode:probe-password").decode()

    def req(method: str, path: str, body: dict | None = None, params: dict | None = None):
        q = ("?" + urllib.parse.urlencode(params)) if params else ""
        c = http.client.HTTPConnection(host, int(port), timeout=30)
        data = json.dumps(body).encode() if body is not None else None
        c.request(method, path + q, body=data, headers={"Authorization": auth, "Content-Type": "application/json"})
        r = c.getresponse(); raw = r.read(); c.close()
        try:
            return r.status, json.loads(raw) if raw else None
        except ValueError:
            return r.status, raw[:200].decode(errors="replace")

    loc = {"location[directory]": str(repo)}
    t1 = time.perf_counter()
    models = []
    while time.perf_counter() - t1 < 30:
        s, doc = req("GET", "/api/model", params=loc)
        models = ((doc.get("data") if isinstance(doc, dict) else doc) or []) if s == 200 else []
        if any(m.get("providerID") == MODEL["providerID"] and m.get("id") == MODEL["model"] for m in models):
            break
        time.sleep(0.5)
    out["catalog"] = {"wait_s": round(time.perf_counter() - t1, 1), "provider_models": sum(1 for m in models if m.get("providerID") == MODEL["providerID"]),
                      "providers": sorted({str(m.get("providerID")) for m in models})[:6]}
    ta = time.perf_counter()
    loaded = False
    while time.perf_counter() - ta < 20 and not loaded:
        s, agents = req("GET", "/api/agent", params=loc)
        if isinstance(agents, dict):
            agents = agents.get("data") or []
        loaded = s == 200 and any(isinstance(a, dict) and (a.get("id") == "aew-lead" or a.get("name") == "aew-lead")
                                  for a in (agents or []))
        if not loaded:
            time.sleep(0.5)
    out["agent_loaded"] = {"ok": loaded, "wait_s": round(time.perf_counter() - ta, 1),
                           "agents": sorted(str(a.get("id") or a.get("name")) for a in (agents or []) if isinstance(a, dict))[:12]}
    before = len(cap.requests)
    s, sess = req("POST", "/api/session", {"title": f"probe {variant}", "agent": "aew-lead", "model": SESSION_MODEL,
                                            "location": {"directory": str(repo)},
                                            "permissions": cfg["agents"]["aew-lead"]["permissions"], "metadata": {}})
    out["session"] = s if s not in (200, 201) else "ok"
    sid = None
    if isinstance(sess, dict):
        sid = (sess.get("data") or {}).get("id") if isinstance(sess.get("data"), dict) else sess.get("id")
    out["session_id"] = sid
    if sid:
        if variant not in ("V0",):
            time.sleep(6.0)  # give the spawned MCP server time to answer initialize/tools/list before the first model call
        s, _ = req("POST", f"/api/session/{sid}/prompt", {"id": f"msg_probe{int(time.time())}", "text": "Reply with one word: ready."})
        out["prompt"] = s
        t2 = time.perf_counter()
        errors = []
        while len(cap.requests) == before and time.perf_counter() - t2 < 45:
            time.sleep(0.5)
            s, page = req("GET", f"/api/session/{sid}/message", params={"order": "asc", "limit": "50"})
            items = (page.get("data") if isinstance(page, dict) else page) or []
            errors = [((m.get("info") or m).get("error") or {}) for m in items if isinstance(m, dict)
                      and ((m.get("info") or m).get("error"))]
            if errors:
                break
        out["model_request_after_s"] = round(time.perf_counter() - t2, 1)
        out["assistant_errors"] = [{k: str(e.get(k))[:200] for k in ("name", "type", "message") if e.get(k)} for e in errors][:2]
        if variant not in ("V0",):  # a second turn, 10 s later: do MCP tools appear once the server is surely ready?
            time.sleep(10.0)
            n1 = len(cap.requests)
            req("POST", f"/api/session/{sid}/prompt", {"id": f"msg_probe2{int(time.time())}", "text": "Again: one word."})
            t3 = time.perf_counter()
            while len(cap.requests) == n1 and time.perf_counter() - t3 < 30:
                time.sleep(0.5)
            if len(cap.requests) > n1:
                b2 = cap.requests[n1]["body"] or {}
                t2names = [((t.get("function") or t).get("name") if isinstance(t, dict) else str(t)) for t in (b2.get("tools") or [])]
                out["second_turn"] = {"tool_count": len(t2names), "aew_tools": [n for n in t2names if n and n.startswith("aew")],
                                      "system_bytes": len(b2.get("instructions") or "")}
                (HERE / f"request_{variant}_turn2.json").write_text(json.dumps(b2, indent=1), encoding="utf-8")
    # the MCP server process, if spawned
    ps = subprocess.run(["pgrep", "-u", os.environ.get("USER", ""), "-fa", "lead mcp"], capture_output=True, text=True).stdout
    out["mcp_processes"] = [l for l in ps.splitlines() if "pgrep" not in l][:3]
    reqs = cap.requests[before:]
    if reqs:
        r = reqs[0]
        body = r["body"] or {}
        (HERE / f"request_{variant}.json").write_text(json.dumps(body, indent=1), encoding="utf-8")
        tools = body.get("tools") or []
        names = []
        for t in tools:
            fn = t.get("function") if isinstance(t, dict) else None
            names.append((fn or t).get("name") if isinstance(fn or t, dict) else str(t))
        instr = body.get("instructions") or ""
        if not instr and isinstance(body.get("messages"), list):
            instr = "".join(m.get("content", "") if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
                            for m in body["messages"] if m.get("role") in ("system", "developer"))
        out["request"] = {"path": r["path"], "bytes": r["bytes"], "auth_present": r["auth_present"],
                          "api": "responses" if "/responses" in r["path"] else "chat" if "/chat" in r["path"] else r["path"],
                          "tool_count": len(tools), "tools_bytes": len(json.dumps(tools)), "tool_names": names,
                          "aew_tools": [n for n in names if n and n.startswith("aew")],
                          "system_bytes": len(instr), "model": body.get("model"), "requests_seen": len(reqs)}
    else:
        out["request"] = None
    # tail of the server log
    log.close()
    tail = (state / "server.log").read_bytes()[-1500:].decode(errors="replace")
    out["server_log_tail"] = [l for l in tail.splitlines() if "mcp" in l.lower() or "error" in l.lower()][-8:]
    try:
        p.stdin.close()
    except Exception:
        pass
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    subprocess.run(["pkill", "-u", os.environ.get("USER", ""), "-f", "aew lead mcp"], capture_output=True)
    return out


def main() -> None:
    base = Path.home() / ".aew-test-tmp"
    base.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="review-t9-oc-", dir=base))
    say("# T9 live probe 1: tool schemas in the model request, OpenCode 2.0.18, with `aew lead mcp` spawned for real")
    say(f"cli: {subprocess.run([CLI, '--version'], capture_output=True, text=True).stdout.strip()}; aew: "
        f"{subprocess.run(['aew', '--version'], capture_output=True, text=True).stdout.strip()}; python {sys.version.split()[0]}")
    cap = Captured()
    ep = fake_endpoint(cap)
    base_url = f"http://127.0.0.1:{ep.server_address[1]}/v1"
    repo, token, rev = make_lab(base)
    say(f"lab project {repo}; Lead seat acquired at revision {rev} (credential kept in memory only)")
    try:
        wanted = sys.argv[2:] or ["V0", "V1", "V2", "V3", "V4", "V5", "V6"]
        for variant in wanted:
            say(f"\n## {variant}")
            try:
                res = run_variant(variant, cap=cap, base_url=base_url, repo=repo, token=token, work=work)
            except Exception as exc:  # keep going; the note records what failed
                import traceback
                res = {"variant": variant, "error": f"{type(exc).__name__}: {exc}",
                       "trace": traceback.format_exc().splitlines()[-4:]}
                subprocess.run(["pkill", "-u", os.environ.get("USER", ""), "-f", "opencode-cli serve"], capture_output=True)
            for k, v in res.items():
                say(f"  {k}: {json.dumps(v)[:900]}")
    finally:
        genv = dict(os.environ)
        st = sh("aew", "status", "--json", cwd=str(repo), env=genv)
        try:
            cur = json.loads(st.stdout).get("revision", rev)
        except ValueError:
            cur = rev
        r = sh("aew", "lead", "release", "--expect-rev", str(cur), cwd=str(repo), env={**genv, "AEW_LEAD_TOKEN": token})
        say(f"\nseat released: {r.returncode == 0}")
        ep.shutdown()
        (HERE / "tool_request_probe.out.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
        shutil.rmtree(repo.parent, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
        say(f"cleaned {repo.parent} and {work}")


if __name__ == "__main__":
    main()
