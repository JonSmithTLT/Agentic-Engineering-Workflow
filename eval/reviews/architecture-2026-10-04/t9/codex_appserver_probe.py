"""T9 live probe 2: the Codex app-server (codex-cli 0.160.0) handshake, MCP spawn of `aew lead mcp`, and what tool
schemas reach the model.

Run on the VM in the review venv (the T1 patch gives `aew lead mcp`):

    source ~/aew-review/venv/bin/activate
    python codex_appserver_probe.py ~/aew-review/codex/pkg/bin/codex

Method: a private CODEX_HOME with a config.toml that selects a custom model provider pointed at a fake Responses API
endpoint on the host loopback (logs every request, answers 500), `approval_policy = "never"`, `sandbox_mode`
read-only, hooks off, no plugins, shell environment not inherited; the `aew` MCP server declared with
`env_vars = ["AEW_LEAD_TOKEN"]` so the credential is forwarded from the app-server's environment and never written
to a file. The app-server speaks newline JSON-RPC over stdio. Variants:

  C0  no MCP server (baseline Codex tool set in the request)
  C1  mcp_servers.aew = `aew lead mcp` (direct)
  C2  C1 + enabled_tools = ["status", "resume"]      does filtering remove schemas from the request?
  C3  C1 with sandbox_mode = "workspace-write"        does the tool set change with the sandbox?
  C4  C1 without AEW_LEAD_TOKEN in the environment   a failed MCP server: what does the app-server report?

Measured per variant: initialize response, mcpServerStatus/list (the server's runtime status and tool count),
thread/start response, the notifications seen, and the first model request (path, bytes, tools, instructions).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tool_request_probe import Captured, fake_endpoint, make_lab, sh  # noqa: E402  (the OpenCode probe's helpers)

CODEX = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/aew-review/codex/pkg/bin/codex")
OUT: list[str] = []
MODEL = "gpt-6-sol"


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


def config_toml(variant: str, *, base_url: str, repo: Path, venv_bin: str) -> str:
    sandbox = "workspace-write" if variant == "C3" else "read-only"
    lines = [
        f'model = "{MODEL}"',
        'model_provider = "probe"',
        'approval_policy = "never"',
        f'sandbox_mode = "{sandbox}"',
        "",
        "[model_providers.probe]",
        'name = "Probe endpoint"',
        f'base_url = "{base_url}"',
        'wire_api = "responses"',
        'env_key = "PROBE_API_KEY"',
        "request_max_retries = 0",
        "stream_max_retries = 0",
        "",
        "[features]",
        "hooks = false",
        *(["multi_agent = false", "code_mode_host = false"] if variant == "C5" else []),
        *(["code_mode_host = false"] if variant == "C6" else []),
        *(["multi_agent = false"] if variant == "C7" else []),
        "",
        "[shell_environment_policy]",
        'inherit = "none"',
        "",
        "[history]",
        'persistence = "none"',
    ]
    if variant != "C0":
        lines += ["", "[mcp_servers.aew]", f'command = "{venv_bin}/aew"', 'args = ["lead", "mcp"]',
                  f'cwd = "{repo}"', 'env_vars = ["AEW_LEAD_TOKEN", "PATH", "HOME"]', "startup_timeout_sec = 30",
                  "required = false"]
        if variant == "C2":
            lines.append('enabled_tools = ["status", "resume"]')
    return "\n".join(lines) + "\n"


class AppServer:
    """One app-server over stdio: requests with ids, notifications collected on a thread."""

    def __init__(self, argv: list[str], env: dict, cwd: str, log: Path) -> None:
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(log, "wb"), env=env,
                                  cwd=cwd, text=True, bufsize=1)
        self.pending: dict[int, dict] = {}
        self.notes: list[dict] = []
        self.server_requests: list[dict] = []
        self.lock = threading.Lock()
        self.n = 0
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        for line in self.p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            with self.lock:
                if "method" in msg and "id" in msg:
                    self.server_requests.append(msg)
                elif "method" in msg:
                    self.notes.append(msg)
                elif "id" in msg:
                    self.pending[msg["id"]] = msg

    def send(self, msg: dict) -> None:
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def request(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        self.n += 1
        rid = self.n
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params if params is not None else {}})
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout:
            with self.lock:
                if rid in self.pending:
                    return self.pending.pop(rid)
            if self.p.poll() is not None:
                return {"error": {"message": f"app-server exited with {self.p.returncode}"}}
            time.sleep(0.05)
        return {"error": {"message": f"timeout waiting for {method}"}}

    def notify(self, method: str, params: dict | None = None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        try:
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()


def run_variant(variant: str, *, cap: Captured, base_url: str, repo: Path, token: str, work: Path) -> dict:
    venv_bin = str(Path(sys.executable).parent)
    home = work / variant / "codex-home"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(config_toml(variant, base_url=base_url, repo=repo, venv_bin=venv_bin), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "USER", "LANG", "TERM")}
    env.update({"CODEX_HOME": str(home), "PROBE_API_KEY": "sk-dummy-not-a-key", "PATH": f"{venv_bin}:{env.get('PATH', '')}"})
    if variant != "C4":
        env["AEW_LEAD_TOKEN"] = token
    out: dict = {"variant": variant}
    t0 = time.perf_counter()
    argv = [CODEX, "app-server"]
    if variant == "C5":
        argv += ["--disable", "multi_agent", "--disable", "code_mode_host", "-c", "features.multi_agent=false"]
    if variant == "C8":  # exec kept, but MCP tools not deferred (if the flag still exists) and sub-agents off
        argv += ["--disable", "multi_agent", "-c", "features.tool_search_always_defer_mcp_tools=false"]
    out_cfg = (home / "config.toml").read_text(encoding="utf-8")
    srv = AppServer(argv, env, str(repo), work / variant / "app-server.log")
    r = srv.request("initialize", {"clientInfo": {"name": "aew-review-probe", "title": "AEW review probe", "version": "0"},
                                   "capabilities": {"experimentalApi": False}})
    out["initialize_s"] = round(time.perf_counter() - t0, 2)
    out["argv_extra"] = argv[2:]
    out["config_features"] = [l for l in out_cfg.splitlines() if "=" in l and ("false" in l or "true" in l)]
    res = r.get("result") or {}
    out["initialize"] = {k: (v if len(json.dumps(v)) < 200 else "...") for k, v in res.items()} if res else r.get("error")
    srv.notify("initialized")
    before = len(cap.requests)
    r = srv.request("thread/start", {"cwd": str(repo), "model": MODEL, "approvalPolicy": "never",
                                     "sandbox": "workspace-write" if variant == "C3" else "read-only"}, timeout=60)
    res = r.get("result") or {}
    thread = (res.get("thread") or {})
    out["thread_start"] = ({"sandbox": res.get("sandbox"), "approvalPolicy": res.get("approvalPolicy"), "model": res.get("model"),
                            "modelProvider": res.get("modelProvider"), "reasoningEffort": res.get("reasoningEffort"),
                            "instructionSources": res.get("instructionSources"), "thread_id": thread.get("id"),
                            "cliVersion": thread.get("cliVersion")} if res else r.get("error"))
    tid = thread.get("id")
    # MCP status, polled until the aew server has a runtime status (or 30 s)
    t1 = time.perf_counter()
    status = None
    while time.perf_counter() - t1 < 30:
        r = srv.request("mcpServerStatus/list", ({"threadId": tid} if tid else {}), timeout=20)
        data = (r.get("result") or {}).get("data") or (r.get("result") or {}).get("servers") or []
        if r.get("error"):
            status = {"error": r["error"]}; break
        aew = next((s for s in data if s.get("name") == "aew"), None)
        if variant == "C0":
            status = {"servers": [s.get("name") for s in data]}; break
        if aew and aew.get("runtimeStatus") is not None:
            status = {k: aew.get(k) for k in ("name", "runtimeStatus", "serverInfo", "authStatus")}
            tools = aew.get("tools")
            if isinstance(tools, dict):
                status["tool_count"] = len(tools); status["tool_names"] = sorted(tools)[:14]
            elif isinstance(tools, list):
                status["tool_count"] = len(tools); status["tool_names"] = sorted(str(t.get("name", t)) for t in tools)[:14]
            else:
                status["tools_field"] = type(tools).__name__
            break
        time.sleep(0.5)
    out["mcp_status"] = status if status is not None else {"timeout": True, "servers": [s.get("name") for s in data]}
    out["mcp_status_s"] = round(time.perf_counter() - t1, 1)
    if tid:
        r = srv.request("turn/start", {"threadId": tid, "input": [{"type": "text", "text": "Reply with one word: ready."}]}, timeout=30)
        out["turn_start"] = "ok" if r.get("result") is not None else r.get("error")
        t2 = time.perf_counter()
        while len(cap.requests) == before and time.perf_counter() - t2 < 60:
            time.sleep(0.25)
        out["model_request_after_s"] = round(time.perf_counter() - t2, 1)
    reqs = cap.requests[before:]
    if reqs:
        body = reqs[0]["body"] or {}
        (HERE / f"codex_request_{variant}.json").write_text(json.dumps(body, indent=1), encoding="utf-8")
        tools = body.get("tools") or []
        names = [(t.get("function") or t).get("name") if isinstance(t, dict) else str(t) for t in tools]
        instr = body.get("instructions") or ""
        at = next((i for i in (body.get("input") or []) if i.get("type") == "additional_tools"), None)
        if at:
            summary = []
            for t in at.get("tools") or []:
                if t.get("type") == "namespace":
                    summary.append({"namespace": t.get("name"), "tools": [f"{x.get('name')}:{len(json.dumps(x))}" for x in t.get("tools") or []]})
                else:
                    summary.append({"tool": t.get("name"), "type": t.get("type"), "bytes": len(json.dumps(t)), "defer": bool(t.get("defer_loading"))})
            out["additional_tools"] = {"bytes": len(json.dumps(at)), "entries": summary}
        out["request"] = {"path": reqs[0]["path"], "bytes": reqs[0]["bytes"], "api": "responses" if "/responses" in reqs[0]["path"] else reqs[0]["path"],
                          "tool_count": len(tools), "tools_bytes": len(json.dumps(tools)), "tool_names": names,
                          "aew_tools": [n for n in names if n and "aew" in n], "instructions_bytes": len(instr),
                          "input_items": len(body.get("input") or []), "model": body.get("model"),
                          "other_keys": sorted(k for k in body if k not in ("tools", "instructions", "input"))}
    else:
        out["request"] = None
    time.sleep(1.0)
    with srv.lock:
        out["notifications"] = sorted({n.get("method") for n in srv.notes})
        mcp_notes = [n.get("params") for n in srv.notes if n.get("method") == "mcpServer/startupStatus/updated"]
        out["mcp_startup_notes"] = [json.dumps(p)[:300] for p in mcp_notes][:3]
        out["server_requests"] = [q.get("method") for q in srv.server_requests]
        errs = [json.dumps(n.get("params"))[:300] for n in srv.notes if n.get("method") in ("error", "configWarning", "warning")]
        out["errors"] = errs[:4]
    if tid:
        srv.request("turn/interrupt", {"threadId": tid}, timeout=10)
    srv.close()
    tail = (work / variant / "app-server.log").read_bytes()[-2000:].decode(errors="replace")
    out["log_tail"] = [l[:200] for l in tail.splitlines() if any(k in l.lower() for k in ("mcp", "error", "warn", "aew"))][-6:]
    subprocess.run(["pkill", "-u", os.environ.get("USER", ""), "-f", "aew lead mcp"], capture_output=True)
    return out


def main() -> None:
    base = Path.home() / ".aew-test-tmp"
    base.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="review-t9-codex-", dir=base))
    say("# T9 live probe 2: Codex app-server handshake, MCP spawn and the model request")
    say(f"codex: {subprocess.run([CODEX, '--version'], capture_output=True, text=True).stdout.strip()}; aew: "
        f"{subprocess.run(['aew', '--version'], capture_output=True, text=True).stdout.strip()}; python {sys.version.split()[0]}")
    cap = Captured()
    ep = fake_endpoint(cap)
    base_url = f"http://127.0.0.1:{ep.server_address[1]}/v1"
    repo, token, rev = make_lab(base)
    say(f"lab project {repo}; Lead seat acquired at revision {rev} (credential in memory and the app-server's environment only)")
    wanted = sys.argv[2:] or ["C0", "C1", "C2", "C3", "C4", "C5", "C8"]
    try:
        for variant in wanted:
            say(f"\n## {variant}")
            try:
                res = run_variant(variant, cap=cap, base_url=base_url, repo=repo, token=token, work=work)
            except Exception as exc:
                import traceback
                res = {"variant": variant, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc().splitlines()[-4:]}
                subprocess.run(["pkill", "-u", os.environ.get("USER", ""), "-f", "codex app-server"], capture_output=True)
            for k, v in res.items():
                say(f"  {k}: {json.dumps(v)[:1200]}")
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
        (HERE / "codex_appserver_probe.out.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
        shutil.rmtree(repo.parent, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
        say(f"cleaned {repo.parent} and {work}")


if __name__ == "__main__":
    main()
