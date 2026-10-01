"""Spike probe 4: what instructions/skills a session actually receives under isolation, and whether the
agent's shell can reach its own server API. Uses one short free-model prompt per variant."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from v2lib import isolated_env, new_id, start_server

PY = sys.executable
API_PROBE = """import sys, urllib.request, urllib.error
try:
    print("STATUS", urllib.request.urlopen(sys.argv[1] + "/api/info", timeout=10).status)
except urllib.error.HTTPError as exc:
    print("STATUS", exc.code)
"""


def workspace(root: Path) -> Path:
    ws = root / "proj" / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "AGENTS.md").write_text("SPIKE-AGENTS-MD-MARKER\n")
    for base, name in ((root / "proj" / ".claude" / "skills", "ancestor-claude-skill"),
                       (ws / ".opencode" / "skills", "project-opencode-skill"),
                       (ws / ".agents" / "skills", "project-agents-skill")):
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: probe {name}\n---\nbody\n")
    if not (ws / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)
    (root / "api_probe.py").write_text(API_PROBE)
    return ws


def main(root: Path, out: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    root = Path(__import__('os').path.realpath(root))  # long path: 8.3 names confuse project/home detection
    ws = workspace(root)
    res: dict = {}
    model = {"providerID": "opencode", "id": "longcat-2.5-preview-free"}
    for label, disable, cfg in (("project_on", False, {}),
                                ("project_off", True, {}),
                                ("project_on_compat_off", False, {"plugins": ["-opencode.config.compatibility"]}),
                                ("project_off_compat_off", True, {"plugins": ["-opencode.config.compatibility"]})):
        srv = start_server(isolated_env(root / f"st-{label}", config={"snapshots": False, **cfg},
                                        disable_project=disable), ws)
        ev = srv.subscribe()
        loc = {"location[directory]": str(ws)}
        time.sleep(3)
        st, sk = srv.get("/api/skill", params=loc)
        st, sess = srv.post("/api/session", {"model": model, "location": {"directory": str(ws)},
                                             "permissions": [{"action": "*", "resource": "*", "effect": "allow"}]})
        sid = sess["data"]["id"]
        t0 = time.perf_counter()
        srv.post(f"/api/session/{sid}/prompt", {"id": new_id("msg"), "text": "Reply with only: OK"})
        ev.wait_for(lambda f: f.get("type", "") in {"session.execution.succeeded", "session.execution.failed"}
                    and f["_t"] > t0, 180)
        st, ins = srv.get(f"/api/experimental/session/{sid}/instructions/entries")
        st, ctx = srv.get(f"/api/session/{sid}/context")
        ctx_text = json.dumps(ctx)
        keys: set[str] = set()
        for f in ev.frames:
            if f.get("type") == "session.instructions.updated" and (f.get("data") or {}).get("sessionID") == sid:
                keys |= set(((f.get("data") or {}).get("delta") or {}).keys())
        entry = {"instruction_keys": sorted(keys),
                 "skills_api": [s.get("id") for s in (sk or {}).get("data", [])],
                 "instructions_entries": [e.get("key") or e.get("id") or str(e)[:80]
                                          for e in (ins or {}).get("data", [])] if isinstance(ins, dict) else ins,
                 "context_status": st,
                 "context_mentions": {m: m in ctx_text for m in ("SPIKE-AGENTS-MD-MARKER", "ancestor-claude-skill",
                                                                 "project-opencode-skill", "project-agents-skill")},
                 "context_sample": ctx_text[:600]}
        if label == "project_off_compat_off":
            cmd = f'"{PY}" "{root / "api_probe.py"}" {srv.url}'
            srv.post(f"/api/session/{sid}/shell", {"id": new_id("msg"), "command": cmd}, timeout=60)
            time.sleep(2)
            st, msgs = srv.get(f"/api/session/{sid}/message", params={"order": "desc", "limit": "5"})
            shells = [m for m in (msgs or {}).get("data", []) if m.get("type") == "shell"]
            entry["server_api_from_shell"] = (shells[0].get("output") or {}).get("output") if shells else None
        srv.close_lease()
        res[label] = entry
    (out / "probe_exposure.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1)[:8000])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
