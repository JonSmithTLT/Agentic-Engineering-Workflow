"""A scripted, model-free 'agent' process for the fake harness.

It runs with exactly the environment a real harness gives model-controlled processes, and acts on AEW
the way a model would: by running the `aew` command. Every step's outcome is appended to the run's
transcript, which stands in for a harness's own persisted conversation (custody scans read it).

Script: a JSON list of steps, e.g. ``{"do": "submit", "kind": "implementation_report", "meta": {...}}``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
CRED = r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}"


def aew_argv() -> list[str]:
    exe = shutil.which("aew")
    return [exe] if exe else [sys.executable, "-m", "aew"]


def run(argv: list[str], **kw: Any) -> dict[str, Any]:
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, **kw)
    return {"exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def aew(*args: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    out = run([*aew_argv(), *args], env={**os.environ, **env} if env else None)
    for stream in ("stdout", "stderr"):
        try:
            out[f"{stream}_json"] = json.loads(out[stream])
        except ValueError:
            pass
    return out


def wait_file(path: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.05)
    return False


CHILD_DUMP = ("import json, os, sys; json.dump(dict(os.environ), open(sys.argv[1], 'w', encoding='utf-8'))")
SCAN = ("import os, re, sys\n"
        "pat = re.compile(sys.argv[1]); hits = []\n"
        "for root in sys.argv[3:]:\n"
        "    for base, dirs, files in os.walk(root):\n"
        "        for f in files:\n"
        "            p = os.path.join(base, f)\n"
        "            try:\n"
        "                if pat.search(open(p, 'rb').read().decode('latin-1')): hits.append(p)\n"
        "            except OSError: pass\n"
        "open(sys.argv[2], 'w').write('\\n'.join(hits))\n")


def step(s: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    do = s["do"]
    if do == "write":
        for rel, content in s["files"].items():
            target = Path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        return {"wrote": sorted(s["files"])}
    if do == "aew":
        return aew(*s["args"], env=s.get("env"))
    if do == "check":
        return aew("check", "run", s["id"])
    if do == "submit":
        import yaml
        path = Path(state["tmp"]) / f"submission-{state['n']}.md"
        path.write_text(f"---\n{yaml.safe_dump(s['meta'], sort_keys=False)}---\n{s.get('body', 'Report.')}\n",
                        encoding="utf-8")
        return aew("submit", "--kind", s["kind"], "--file", str(path))
    if do == "wait_file":
        return {"found": wait_file(s["path"], s.get("timeout", 60))}
    if do == "touch":
        Path(s["path"]).write_text(s.get("text", "x"), encoding="utf-8")
        return {}
    if do == "sleep":
        time.sleep(s["s"])
        return {}
    if do == "hang":
        while True:
            time.sleep(1)
    if do == "exit":
        sys.stdout.flush()
        os._exit(s.get("code", 0))
    if do == "dump_env":
        Path(s["path"]).write_text(json.dumps(dict(os.environ)), encoding="utf-8")
        return {}
    if do == "child_env":  # a model-controlled child process inspects its environment
        out = run([sys.executable, "-c", CHILD_DUMP, s["path"]])
        shell = run(["cmd", "/c", "set"] if sys.platform == "win32" else ["env"])
        Path(s["shell_path"]).write_text(shell["stdout"], encoding="utf-8")
        return {"child_exit": out["exit"], "shell_exit": shell["exit"]}
    if do == "read_parent_environ":  # Linux: try to read the supervisor's initial environment
        pid = os.getppid() if s["pid"] == "ppid" else s["pid"]
        try:
            data = Path(f"/proc/{pid}/environ").read_bytes().decode("latin-1")
            return {"readable": True, "has_credential": bool(__import__("re").search(CRED, data)),
                    "has_lead_var": "AEW_LEAD_TOKEN" in data}
        except OSError as exc:
            return {"readable": False, "error": str(exc)}
    if do == "scan":  # look for any credential string in files the agent can reach
        out = run([sys.executable, "-c", SCAN, CRED, s["out"], *s["roots"]])
        hits = Path(s["out"]).read_text(encoding="utf-8").split("\n") if Path(s["out"]).exists() else []
        return {"exit": out["exit"], "hits": [h for h in hits if h]}
    if do == "bridge_raw":  # talk to a bridge directly, bypassing the CLI
        from aew.harness import bridge
        try:
            return {"ok": True, "result": bridge.call(s["op"], s["args"], endpoint=s.get("endpoint"),
                                                      key=s.get("key"))}
        except Exception as exc:
            return {"ok": False, "code": getattr(exc, "code", type(exc).__name__), "message": str(exc)}
    if do == "bridge_payload":  # send an arbitrary request object over this run's bridge
        from multiprocessing.connection import Client
        endpoint, key = os.environ["AEW_AGENT_ENDPOINT"], bytes.fromhex(os.environ["AEW_AGENT_KEY"])
        fam = "AF_PIPE" if endpoint.startswith("\\\\.\\pipe\\") else "AF_UNIX"
        conn = Client(endpoint, family=fam, authkey=key)
        conn.send_bytes(s["raw"].encode("utf-8") if "raw" in s else json.dumps(s["request"]).encode("utf-8"))
        reply = json.loads(conn.recv_bytes().decode("utf-8"))
        conn.close()
        return reply
    if do == "spawn_orphan":  # a descendant that tries to outlive the run
        code = ("import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(600)")
        # A new process group, no console: as detached as a same-job process can be (no DETACHED_PROCESS,
        # whose children would open visible consoles).
        kw: dict[str, Any] = {"creationflags": NO_WINDOW | 0x00000200} if sys.platform == "win32" else {}
        subprocess.Popen([sys.executable, "-c", code, s["pidfile"]], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        wait_file(s["pidfile"], 30)
        return {}
    if do == "cwd":
        Path(s["path"]).write_text(os.getcwd(), encoding="utf-8")
        return {}
    if do == "pid":
        Path(s["path"]).write_text(str(os.getpid()), encoding="utf-8")
        return {}
    raise SystemExit(f"unknown step {do}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--transcript", required=True)
    args = parser.parse_args()
    steps = json.loads(Path(args.script).read_text(encoding="utf-8"))
    transcript = Path(args.transcript)
    state = {"tmp": str(transcript.parent), "n": 0}
    for i, s in enumerate(steps):
        state["n"] = i
        result = step(s, state)
        with transcript.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"i": i, "do": s["do"], "result": result}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
