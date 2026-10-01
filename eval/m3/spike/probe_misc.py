"""Spike probe 5: variant pinning, invalid variant, server killed mid-run, `run --standalone --format json` baseline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from v2lib import NO_WINDOW, PINNED_BIN, isolated_env, new_id, start_server

PY = sys.executable


def main(root: Path, out: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    root = Path(os.path.realpath(root))
    ws = root / "ws"
    ws.mkdir(exist_ok=True)
    if not (ws / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)
    res: dict = {}
    env = isolated_env(root / "st", config={"snapshots": False, "plugins": ["-opencode.config.compatibility"]})
    srv = start_server(env, ws)
    ev = srv.subscribe()
    loc = {"location[directory]": str(ws)}
    for _ in range(60):
        st, m = srv.get("/api/model", params=loc)
        if (m or {}).get("data"):
            break
        time.sleep(0.5)
    allow = [{"action": "*", "resource": "*", "effect": "allow"}]

    # ---- pinned variant is recorded as the effective one
    ref = {"providerID": "opencode", "id": "space-bunny-free", "variant": "high"}
    st, sess = srv.post("/api/session", {"model": ref, "location": {"directory": str(ws)}, "permissions": allow})
    sid = sess["data"]["id"]
    t0 = time.perf_counter()
    srv.post(f"/api/session/{sid}/prompt", {"id": new_id("msg"), "text": "Reply with only: OK"})
    step = ev.wait_for(lambda f: f.get("type") == "session.step.started" and f["_t"] > t0, 180)
    ev.wait_for(lambda f: f.get("type", "").startswith("session.execution.") and f.get("type") !=
                "session.execution.started" and f["_t"] > t0, 180)
    st, msgs = srv.get(f"/api/session/{sid}/message", params={"order": "desc", "limit": "3"})
    res["variant_pin"] = {"session_model": sess["data"].get("model"),
                          "step_started_model": (step or {}).get("data", {}).get("model"),
                          "assistant_models": [m.get("model") for m in msgs["data"] if m.get("type") == "assistant"]}

    # ---- invalid variant: where does it fail?
    bad = {"providerID": "opencode", "id": "space-bunny-free", "variant": "no-such-variant"}
    st, sess = srv.post("/api/session", {"model": bad, "location": {"directory": str(ws)}, "permissions": allow})
    r: dict = {"create_status": st, "create_body": str(sess)[:300]}
    if st == 200:
        sid2 = sess["data"]["id"]
        t0 = time.perf_counter()
        pst, p = srv.post(f"/api/session/{sid2}/prompt", {"id": new_id("msg"), "text": "Reply with only: OK"})
        term = ev.wait_for(lambda f: f.get("type", "").startswith("session.execution.") and f.get("type") !=
                           "session.execution.started" and (f.get("data") or {}).get("sessionID") == sid2
                           and f["_t"] > t0, 120)
        r.update(prompt_status=pst, terminal=(term or {}).get("type"), error=(term or {}).get("data", {}).get("error"))
    bad_model = {"providerID": "opencode", "id": "no-such-model"}
    st, sess = srv.post("/api/session", {"model": bad_model, "location": {"directory": str(ws)}, "permissions": allow})
    r["bad_model_create_status"] = st
    r["bad_model_body"] = str(sess)[:300]
    res["invalid_variant"] = r

    # ---- server killed mid-run: what the client observes
    st, sess = srv.post("/api/session", {"model": {"providerID": "opencode", "id": "longcat-2.5-preview-free"},
                                         "location": {"directory": str(ws)}, "permissions": allow})
    sid3 = sess["data"]["id"]
    t0 = time.perf_counter()
    srv.post(f"/api/session/{sid3}/prompt", {"id": new_id("msg"), "text": f"Use the shell tool to run: {PY} -c "
                                             "\"import time; time.sleep(60)\" then reply done."})
    ev.wait_for(lambda f: f.get("type") == "session.tool.called" and f["_t"] > t0, 120)
    srv.proc.kill()
    time.sleep(2)
    try:
        after = srv.get("/api/info", timeout=5)
    except Exception as exc:  # noqa: BLE001
        after = repr(exc)[:200]
    res["server_killed"] = {"sse_error": ev.error, "request_after_kill": str(after)[:200]}
    # restart on the same state: the session persists (on-disk DB); its outcome is?
    srv2 = start_server(env, ws)
    st, info = srv2.get(f"/api/session/{sid3}")
    st2, active = srv2.get("/api/session/active")
    res["server_killed"]["after_restart"] = {"status": st, "outcome": (info or {}).get("data", {}).get("outcome"),
                                             "active": active}
    srv2.close_lease()

    # ---- `run --standalone --format json` baseline (isolated state)
    env_run = isolated_env(root / "st-run", config={"snapshots": False, "plugins": ["-opencode.config.compatibility"]})
    t0 = time.perf_counter()
    proc = subprocess.run([str(PINNED_BIN), "run", "--standalone", "--format", "json", "--model",
                           "opencode/longcat-2.5-preview-free", "Reply with only: OK"], cwd=str(ws), env=env_run,
                          capture_output=True, timeout=300, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    lines = [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    parsed = []
    for ln in lines:
        try:
            parsed.append(json.loads(ln))
        except ValueError:
            parsed.append({"_raw": ln[:200]})
    res["run_baseline"] = {"exit": proc.returncode, "wall_s": round(time.perf_counter() - t0, 2),
                           "types": [p.get("type") for p in parsed],
                           "step_finish": [p.get("part") for p in parsed if p.get("type") == "step_finish"][:2],
                           "stderr_tail": proc.stderr.decode("utf-8", "replace")[-400:]}
    (out / "probe_misc.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
