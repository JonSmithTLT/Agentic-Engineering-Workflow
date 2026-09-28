"""A scripted, model-free 'agent' process for the fake harness.

It runs with exactly the environment a real harness gives model-controlled processes, and acts on AEW
the way a model would: by running the `aew` command. Every step's outcome is appended to the run's
transcript, which stands in for a harness's own persisted conversation (custody scans read it).

Script: a JSON list of steps, e.g. ``{"do": "submit", "kind": "implementation_report", "meta": {...}}``.
``--script`` runs a whole script as one long-lived process (the fake harness); ``--step-file`` runs one step,
the way a harness's shell tool runs one command (the OpenCode drivers).

``{evidence:<name>}`` in a step's arguments is the newest evidence id this agent has seen in its own command
output (its transcript) whose id names ``<name>`` (``check-unit``, ``review``, ``verify``): the way a model
reads an id from the output of a command it ran, e.g. a verifier citing its own check results.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
CRED = r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}"
EVIDENCE_REF = re.compile(r"\{evidence:([A-Za-z0-9_-]+)\}")


def seen_evidence(transcript: Path, name: str) -> str | None:
    """The newest evidence id in this agent's own command output whose id names ``name``."""
    lines = transcript.read_text(encoding="utf-8").splitlines() if transcript.exists() else []
    for line in reversed(lines):
        out = (json.loads(line).get("result") or {}).get("stdout_json")
        ids = out.get("evidence") if isinstance(out, dict) else None
        for eid in reversed([ids] if isinstance(ids, str) else ids if isinstance(ids, list) else []):
            if f"-{name}-" in str(eid):
                return str(eid)
    return None


def resolve(value: Any, transcript: Path) -> Any:
    """Replace ``{evidence:<name>}`` references (an unresolved one stays as written, so its command fails)."""
    if isinstance(value, str):
        return EVIDENCE_REF.sub(lambda m: seen_evidence(transcript, m.group(1)) or m.group(0), value)
    if isinstance(value, list):
        return [resolve(v, transcript) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, transcript) for k, v in value.items()}
    return value


def aew_argv() -> list[str]:
    exe = shutil.which("aew")
    return [exe] if exe else [sys.executable, "-m", "aew"]


def run(argv: list[str], *, input_bytes: bytes | None = None, **kw: Any) -> dict[str, Any]:
    if input_bytes is not None:  # piped into the command, byte for byte, as a shell pipe delivers it
        proc = subprocess.run(argv, input=input_bytes, capture_output=True, creationflags=NO_WINDOW, **kw)
        out, err = (b.decode("utf-8", "replace").replace("\r\n", "\n") for b in (proc.stdout, proc.stderr))
        return {"exit": proc.returncode, "stdout": out, "stderr": err}
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, **kw)
    return {"exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def aew(*args: str, env: dict[str, str] | None = None, input_bytes: bytes | None = None) -> dict[str, Any]:
    out = run([*aew_argv(), *args], env={**os.environ, **env} if env else None, input_bytes=input_bytes)
    for stream in ("stdout", "stderr"):
        try:
            out[f"{stream}_json"] = json.loads(out[stream])
        except ValueError:
            pass
    return out


def bridge_env(s: dict[str, Any]) -> tuple[str, str]:
    """The environment names of the bridge a step talks to: this run's, or the Lead session's."""
    if s.get("bridge") == "lead":
        return ("AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY")
    return ("AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY")


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
    if do in {"aew", "lead", "submit", "submit_raw"}:
        s = resolve(s, Path(state["transcript"]))
    if do == "write":
        for rel, content in s["files"].items():
            target = Path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        return {"wrote": sorted(s["files"])}
    if do == "aew":  # {FORGED_CREDENTIAL} is built here, so no credential-shaped string sits in any file
        forged = "aew1.tk_" + "0" * 16 + "." + "F" * 43
        return aew(*[a.replace("{FORGED_CREDENTIAL}", forged) for a in s["args"]], env=s.get("env"))
    if do == "check":
        return aew("check", "run", s["id"])
    if do == "lead":  # a Lead command at the current revision (the Lead's harness, through the Lead bridge)
        rev = json.loads(aew("lead", "show")["stdout"])["revision"]
        return aew(*s["args"], "--expect-rev", str(rev))
    if do == "submit_raw":  # whatever text the model produced, well-formed or not, written as its tools write it
        data = s["text"].encode(s.get("encoding", "utf-8"))  # e.g. "utf-8-sig" or "utf-16": Windows PowerShell 5.1
        if s.get("stdin"):
            return aew("submit", "--kind", s["kind"], "--file", "-", input_bytes=data)
        path = Path(state["tmp"]) / f"submission-{state['n']}.md"
        path.write_bytes(data)
        return aew("submit", "--kind", s["kind"], "--file", str(path))
    if do == "submit":
        import yaml
        path = Path(state["tmp"]) / f"submission-{state['n']}.md"
        path.write_text(f"---\n{yaml.safe_dump(s['meta'], sort_keys=False)}---\n{s.get('body', 'Report.')}\n",
                        encoding="utf-8")
        return aew("submit", "--kind", s["kind"], "--file", str(path))
    if do == "wait_file":  # optionally announce this process first, so a test can watch it while it waits
        if s.get("pidfile"):
            Path(s["pidfile"]).write_text(str(os.getpid()), encoding="utf-8")
        if s.get("ready"):
            Path(s["ready"]).write_text("x", encoding="utf-8")
        return {"found": wait_file(s["path"], s.get("timeout", 60))}
    if do == "model_step":  # the model answers once (a real harness driver sends a real prompt here)
        return {}
    if do == "note":  # the model's own remark: it stays in this run's conversation, never in AEW state
        return {"note": s["text"]}
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
                                                      key=s.get("key"), env_names=bridge_env(s))}
        except Exception as exc:
            return {"ok": False, "code": getattr(exc, "code", type(exc).__name__), "message": str(exc)}
    if do == "bridge_payload":  # send an arbitrary request object over this run's bridge
        from multiprocessing.connection import Client
        names = bridge_env(s)
        endpoint, key = os.environ[names[0]], bytes.fromhex(os.environ[names[1]])
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


def record(transcript: Path, i: int, s: dict[str, Any], result: dict[str, Any]) -> None:
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"i": i, "do": s["do"], "result": result}) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script")
    parser.add_argument("--step-file")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--transcript", required=True)
    args = parser.parse_args()
    transcript = Path(args.transcript)
    if args.step_file:
        s = json.loads(Path(args.step_file).read_text(encoding="utf-8"))
        record(transcript, args.index, s, step(s, {"tmp": str(transcript.parent), "n": args.index,
                                                   "transcript": str(transcript)}))
        return 0
    spec = json.loads(Path(args.script).read_text(encoding="utf-8"))
    steps = spec["steps"] if isinstance(spec, dict) else spec
    state = {"tmp": str(transcript.parent), "n": 0, "transcript": str(transcript)}
    for i, s in enumerate(steps):
        state["n"] = i
        record(transcript, i, s, step(s, state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
