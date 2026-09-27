"""Spike probe 2: session lifecycle against a free model (V2 2.0.18, private server, isolated state).

Each section records what actually happened; nothing here is assumed. Output: probe_lifecycle.json.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from v2lib import isolated_env, new_id, start_server

PY = sys.executable
RESULTS: dict[str, Any] = {}


def section(name: str):
    def deco(fn):
        def run(*a, **kw):
            t0 = time.perf_counter()
            try:
                RESULTS[name] = {"ok": True, **(fn(*a, **kw) or {})}
            except Exception as exc:  # noqa: BLE001 - spike records failures
                RESULTS[name] = {"ok": False, "error": repr(exc), "trace": traceback.format_exc()[-1500:]}
            RESULTS[name]["elapsed_s"] = round(time.perf_counter() - t0, 2)
            print(f"== {name}: ok={RESULTS[name]['ok']} ({RESULTS[name]['elapsed_s']}s)", flush=True)
        return run
    return deco


def ruleset(*, edit: str = "deny", shell: str = "allow") -> list[dict[str, str]]:
    rules = [{"action": "*", "resource": "*", "effect": "deny"}]
    rules += [{"action": a, "resource": "*", "effect": "allow"} for a in ("read", "glob", "grep")]
    rules += [{"action": "shell", "resource": "*", "effect": shell},
              {"action": "edit", "resource": "*", "effect": edit}]
    rules += [{"action": a, "resource": "*", "effect": "deny"}
              for a in ("external_directory", "subagent", "question", "skill", "webfetch", "websearch")]
    return rules


def make_workspace(root: Path) -> Path:
    ws = root / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "README.md").write_text("# spike workspace\n")
    (ws / "AGENTS.md").write_text("SPIKE-AGENTS-MD: if you can read this sentence, project AGENTS.md was loaded.\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)
    subprocess.run(["git", "-c", "user.name=s", "-c", "user.email=s@x", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "-c", "user.name=s", "-c", "user.email=s@x", "commit", "-qm", "init"], cwd=ws, check=True)
    # an ancestor project skill: does the project walk expose it?
    sk = root / ".claude" / "skills" / "spike-ancestor-skill"
    sk.mkdir(parents=True, exist_ok=True)
    (sk / "SKILL.md").write_text("---\nname: spike-ancestor-skill\ndescription: ancestor leak probe\n---\nbody\n")
    return ws


def terminal(sid: str):
    return lambda f: f.get("type", "").startswith("session.execution.") and \
        f.get("type") != "session.execution.started" and (f.get("data") or {}).get("sessionID") == sid


def summarize_messages(srv, sid: str) -> dict[str, Any]:
    st, msgs = srv.get(f"/api/session/{sid}/message", params={"order": "asc", "limit": "200"})
    out: dict[str, Any] = {"status": st, "types": [], "assistant": [], "tools": [], "texts": []}
    for m in (msgs or {}).get("data", []) if isinstance(msgs, dict) else []:
        out["types"].append(m.get("type"))
        if m.get("type") == "assistant":
            out["assistant"].append({"model": m.get("model"), "tokens": m.get("tokens"), "cost": m.get("cost"),
                                     "finish": m.get("finish"), "error": m.get("error")})
            for c in m.get("content", []):
                if c.get("type") == "tool":
                    stt = c.get("state") or {}
                    out["tools"].append({"name": c.get("name"), "state": stt.get("status") or list(stt)[:3],
                                         "input": str(stt.get("input"))[:200]})
                elif c.get("type") == "text":
                    out["texts"].append(str(c.get("text"))[:300])
        if m.get("type") == "shell":
            out["texts"].append("SHELL:" + json.dumps(m)[:600])
        if m.get("type") == "idle":
            out.setdefault("idle", []).append(m.get("outcome"))
    return out


def prompt_and_wait(srv, ev, sid: str, text: str, timeout: float = 240, delivery: str | None = None) -> dict:
    mid = new_id("msg")
    body = {"id": mid, "text": text}
    if delivery:
        body["delivery"] = delivery
    t0 = time.perf_counter()
    st, item = srv.post(f"/api/session/{sid}/prompt", body)
    first = ev.wait_for(lambda f: f.get("type") == "session.step.started"
                        and (f.get("data") or {}).get("sessionID") == sid and f["_t"] > t0, timeout)
    term = ev.wait_for(lambda f: terminal(sid)(f) and f["_t"] > t0, timeout)
    wst, _ = srv.post(f"/api/experimental/session/{sid}/wait", {}, timeout=timeout)
    return {"prompt_status": st, "inbox_item_type": (item or {}).get("data", {}).get("type") if isinstance(item, dict)
            else item, "first_step_s": round(first["_t"] - t0, 2) if first else None,
            "terminal": term.get("type") if term else None, "terminal_s": round(term["_t"] - t0, 2) if term else None,
            "wait_status": wst}


def main(root: Path, out: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    ws = make_workspace(root)
    server_secret = "SRVSECRET-" + secrets.token_hex(16)
    canary = "CANARY-" + secrets.token_hex(16)

    # ---------------------------------------------------------------- skills / instructions exposure
    @section("exposure")
    def exposure():
        res = {}
        for label, disable, cfg in (("project_on", False, {}),
                                    ("project_off", True, {}),
                                    ("project_off_compat_off", True, {"plugins": ["-opencode.config.compatibility"]}),
                                    ("project_on_compat_off", False, {"plugins": ["-opencode.config.compatibility"]})):
            srv = start_server(isolated_env(root / f"exp-{label}", config=cfg, disable_project=disable), ws)
            loc = {"location[directory]": str(ws)}
            st, sk = srv.get("/api/skill", params=loc)
            st2, sess = srv.post("/api/session", {"location": {"directory": str(ws)}})
            sid = (sess or {}).get("data", {}).get("id")
            st3, ins = srv.get(f"/api/experimental/session/{sid}/instructions/entries") if sid else (None, None)
            res[label] = {"skills": [s.get("id") for s in (sk or {}).get("data", [])],
                          "instructions": ins if not isinstance(ins, dict) else
                          [{k: (str(v)[:120] if k in {"content", "text"} else v) for k, v in e.items()}
                           for e in ins.get("data", [])] if isinstance(ins.get("data"), list) else ins}
            srv.close_lease()
        return res
    exposure()

    # ---------------------------------------------------------------- main server
    config = {"snapshots": False, "plugins": ["-opencode.config.compatibility"],
              "agents": {"aew": {"mode": "primary", "system": "You are a spike test agent. Follow instructions "
                                 "exactly and briefly.", "permissions": ruleset()}}}
    env = isolated_env(root / "main", config=config, extra={"SPIKE_SERVER_SECRET": server_secret})
    srv = start_server(env, ws)
    RESULTS["server_start_s"] = round(srv.started_s, 3)
    loc = {"location[directory]": str(ws)}
    ev = srv.subscribe()
    RESULTS["first_event"] = ev.frames[0].get("type") if ev.frames else None

    @section("catalog")
    def catalog():
        t0 = time.perf_counter()
        models: list = []
        while time.perf_counter() - t0 < 90:
            st, m = srv.get("/api/model", params=loc)
            models = (m or {}).get("data", []) if isinstance(m, dict) else []
            if models:
                break
            time.sleep(0.5)
        st, d = srv.get("/api/model/default", params=loc)
        default = (d or {}).get("data") or {}
        return {"catalog_ready_s": round(time.perf_counter() - t0, 2), "count": len(models),
                "models": [{"p": x.get("providerID"), "id": x.get("id"),
                            "variants": [v.get("id") for v in x.get("variants") or []]} for x in models],
                "default": {"providerID": default.get("providerID"), "id": default.get("id"),
                            "variants": [v.get("id") for v in default.get("variants") or []]}}
    catalog()
    model = RESULTS["catalog"].get("default") or {}
    variant = (model.get("variants") or [None])[0]
    model_ref = {"providerID": model.get("providerID"), "id": model.get("id")}
    if variant:
        model_ref["variant"] = variant
    RESULTS["model_ref"] = model_ref

    state: dict[str, Any] = {}

    @section("create_and_env")
    def create_and_env():
        t0 = time.perf_counter()
        st, sess = srv.post("/api/session", {"title": "aew-spike", "agent": "aew", "model": model_ref,
                                             "location": {"directory": str(ws)}, "permissions": ruleset(),
                                             "metadata": {"aew_invocation": "INV-SPIKE", "aew_run": "R-SPIKE-1"}})
        create_s = time.perf_counter() - t0
        info = (sess or {}).get("data") or {}
        state["sid"] = info.get("id")
        curated = {k: v for k, v in env.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE",
                                                                 "HOME", "COMSPEC", "PATHEXT", "WINDIR"}}
        curated["SPIKE_SESSION_CANARY"] = canary
        est, _ = srv.request("PUT", f"/api/session/{state['sid']}/environment", body={"variables": curated})
        return {"create_status": st, "create_s": round(create_s, 3), "info_keys": sorted(info),
                "session_model": info.get("model"), "session_agent": info.get("agent"),
                "session_permissions_len": len(info.get("permissions") or []), "env_status": est,
                "curated_names": sorted(curated)}
    create_and_env()
    sid = state.get("sid")

    @section("shell_env")
    def shell_env():
        cmd = f'"{PY}" -c "import os,json;print(json.dumps(sorted(os.environ)))"'
        st, r = srv.post(f"/api/session/{sid}/shell", {"id": new_id("msg"), "command": cmd}, timeout=120)
        time.sleep(1)
        msgs = summarize_messages(srv, sid)
        shell_texts = [t for t in msgs["texts"] if t.startswith("SHELL:")]
        joined = " ".join(shell_texts)
        return {"status": st, "response": str(r)[:800], "server_secret_name_visible": "SPIKE_SERVER_SECRET" in joined,
                "opencode_password_visible": "OPENCODE_PASSWORD" in joined, "canary_name_visible":
                    "SPIKE_SESSION_CANARY" in joined, "shell_messages": shell_texts[-1:]}
    shell_env()

    @section("prompt_basic")
    def prompt_basic():
        r = prompt_and_wait(srv, ev, sid, f"Use the shell tool to run exactly this command: {PY} -c \"print(40+2)\" "
                                          "Then reply with only the number it printed.")
        r["messages"] = summarize_messages(srv, sid)
        st, info = srv.get(f"/api/session/{sid}")
        r["session_outcome"] = (info or {}).get("data", {}).get("outcome")
        r["session_tokens"] = (info or {}).get("data", {}).get("tokens")
        r["session_cost"] = (info or {}).get("data", {}).get("cost")
        return r
    prompt_basic()

    @section("interrupt")
    def interrupt():
        t0 = time.perf_counter()
        mid = new_id("msg")
        srv.post(f"/api/session/{sid}/prompt", {"id": mid, "text": f"Use the shell tool to run exactly: {PY} -c "
                                                "\"import time; time.sleep(90); print('slept')\" and then reply done."})
        called = ev.wait_for(lambda f: f.get("type") == "session.tool.called" and f["_t"] > t0
                             and (f.get("data") or {}).get("sessionID") == sid, 180)
        time.sleep(3)
        st, active = srv.get("/api/session/active")
        ist, ir = srv.post(f"/api/session/{sid}/interrupt", {}, params={"resume": "false"})
        term = ev.wait_for(lambda f: terminal(sid)(f) and f["_t"] > t0, 60)
        return {"tool_called_s": round(called["_t"] - t0, 2) if called else None, "active_before": active,
                "interrupt_status": ist, "interrupt_resp": ir, "terminal": term.get("type") if term else None,
                "reason": (term or {}).get("data", {}).get("reason"),
                "interrupt_to_terminal_s": round(term["_t"] - t0, 2) if term else None}
    interrupt()

    @section("steer_queue")
    def steer_queue():
        t0 = time.perf_counter()
        srv.post(f"/api/session/{sid}/prompt", {"id": new_id("msg"), "text": f"Use the shell tool to run exactly: {PY} "
                                                "-c \"import time; time.sleep(20); print('first')\" then reply 'first done'."})
        called = ev.wait_for(lambda f: f.get("type") == "session.tool.called" and f["_t"] > t0
                             and (f.get("data") or {}).get("sessionID") == sid, 180)
        s1, steer = srv.post(f"/api/session/{sid}/prompt", {"id": new_id("msg"), "delivery": "steer",
                                                            "text": "Additionally reply with the word STEERED."})
        s2, queue_ = srv.post(f"/api/session/{sid}/prompt", {"id": new_id("msg"), "delivery": "queue",
                                                             "text": "Now reply with only the word QUEUED."})
        deadline = time.time() + 300
        while time.time() < deadline:
            st, active = srv.get("/api/session/active")
            if sid not in ((active or {}).get("data") or {}):
                break
            time.sleep(2)
        inbox = [f.get("type") for f in ev.frames if f["_t"] > t0 and f.get("type", "").startswith("session.inbox")]
        msgs = summarize_messages(srv, sid)
        tail = " ".join(msgs["texts"][-6:])
        return {"tool_called": bool(called), "steer_status": s1, "queue_status": s2, "inbox_events": inbox,
                "steered_seen": "STEERED" in tail, "queued_seen": "QUEUED" in tail, "last_texts": msgs["texts"][-4:],
                "terminals": [f.get("type") for f in ev.frames if f["_t"] > t0 and terminal(sid)(f)]}
    steer_queue()

    @section("deny_tools")
    def deny_tools():
        t0 = time.perf_counter()
        r = prompt_and_wait(srv, ev, sid, "Using your file editing or writing tool (NOT the shell), create a file named "
                                          "created.txt containing hi. Then try to delegate a task with the subagent tool. "
                                          "Then list which tools you have available, by name.", timeout=240)
        tools = [f.get("data", {}).get("name") or f.get("data", {}) for f in ev.frames
                 if f["_t"] > t0 and f.get("type") == "session.tool.called"]
        r["tool_calls"] = [str(t)[:120] for t in tools]
        r["file_created"] = (ws / "created.txt").exists()
        r["last_texts"] = summarize_messages(srv, sid)["texts"][-2:]
        return r
    deny_tools()

    @section("server_api_from_shell")
    def server_api_from_shell():
        code = ("import urllib.request as u,urllib.error as e\\ntry:\\n print(u.urlopen('%s/api/info').status)\\n"
                "except e.HTTPError as x:\\n print('HTTP',x.code)" % srv.url)
        cmd = f'"{PY}" -c "exec(\'{code}\')"'
        st, r = srv.post(f"/api/session/{sid}/shell", {"id": new_id("msg"), "command": cmd}, timeout=60)
        time.sleep(1)
        shell = [t for t in summarize_messages(srv, sid)["texts"] if t.startswith("SHELL:")]
        return {"status": st, "last_shell": shell[-1:]}
    server_api_from_shell()

    @section("print_canary")
    def print_canary():
        cmd = f'"{PY}" -c "import os;print(os.environ.get(\'SPIKE_SESSION_CANARY\'))"'
        st, r = srv.post(f"/api/session/{sid}/shell", {"id": new_id("msg"), "command": cmd}, timeout=60)
        return {"status": st}
    print_canary()

    @section("ask_blocks")
    def ask_blocks():
        rules = ruleset() + [{"action": "shell", "resource": "*", "effect": "ask"}]
        st, sess = srv.post("/api/session", {"agent": "aew", "model": model_ref, "location": {"directory": str(ws)},
                                             "permissions": rules})
        sid2 = sess["data"]["id"]
        t0 = time.perf_counter()
        srv.post(f"/api/session/{sid2}/prompt", {"id": new_id("msg"),
                                                 "text": f"Use the shell tool to run: {PY} -c \"print(7)\""})
        asked = ev.wait_for(lambda f: f.get("type") == "permission.asked" and f["_t"] > t0
                            and (f.get("data") or {}).get("sessionID") == sid2, 180)
        time.sleep(10)
        st, active = srv.get("/api/session/active")
        still_running = sid2 in ((active or {}).get("data") or {})
        st2, pending = srv.get(f"/api/session/{sid2}/permission")
        req = (asked or {}).get("data", {}).get("id")
        rst, _ = srv.post(f"/api/session/{sid2}/permission/{req}/reply", {"decision": "reject"}) if req else (None, None)
        term = ev.wait_for(lambda f: terminal(sid2)(f) and f["_t"] > t0, 120)
        return {"asked": bool(asked), "asked_action": (asked or {}).get("data", {}).get("action"),
                "still_running_after_10s": still_running, "pending_count": len((pending or {}).get("data", [])),
                "reply_status": rst, "terminal_after_reject": term.get("type") if term else None}
    ask_blocks()

    # ---------------------------------------------------------------- teardown + leak scan
    RESULTS["event_types"] = sorted({f.get("type") for f in ev.frames})
    (out / "events_sample.json").write_text(json.dumps(ev.frames[:400], indent=1, default=str)[:400000])
    RESULTS["lease_exit_s"] = srv.close_lease()

    @section("leak_scan")
    def leak_scan():
        hits: dict[str, list[str]] = {"server_secret": [], "canary": []}
        for p in (root / "main").rglob("*"):
            if p.is_file():
                b = p.read_bytes()
                if server_secret.encode() in b:
                    hits["server_secret"].append(str(p.relative_to(root)))
                if canary.encode() in b:
                    hits["canary"].append(str(p.relative_to(root)))
        return hits
    leak_scan()

    @section("memory_db")
    def memory_db():
        env2 = isolated_env(root / "mem", config={"snapshots": False}, extra={"OPENCODE_DB": ":memory:"})
        s1 = start_server(env2, ws)
        st, sess = s1.post("/api/session", {"location": {"directory": str(ws)}})
        sid3 = sess["data"]["id"]
        s1.close_lease()
        s2 = start_server(env2, ws)
        st2, got = s2.get(f"/api/session/{sid3}")
        s2.close_lease()
        files = [str(p.relative_to(root / "mem")) for p in (root / "mem").rglob("*.db*")]
        return {"after_restart_status": st2, "db_files": files}
    memory_db()

    (out / "probe_lifecycle.json").write_text(json.dumps(RESULTS, indent=1, default=str))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
