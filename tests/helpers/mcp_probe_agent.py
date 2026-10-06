"""A scripted MCP client standing in for the Lead's harness (F15.1): run as the harness command of `aew lead session`,
it spawns `aew lead mcp` the way OpenCode does (inherited environment, no `environment` of its own, no console window),
completes the handshake and runs scripted steps, writing one JSON line per step to a transcript.

Steps:
  {"rpc": METHOD, "params": {...}}          a request; the reply is recorded
  {"notify": METHOD}                        a notification; nothing is expected back
  {"call": TOOL, "arguments": {...}}        tools/call; "$revision" in arguments is replaced by the last result's
                                            revision ("$revision_text" by it as a string, for an argv)
  {"touch": PATH} / {"wait_file": PATH}     synchronize with the test
  {"server_env": PATH}                      write what the server's environment holds (names, and whether any value is
                                            credential-shaped): on Linux read from the server process itself, elsewhere
                                            from this process, whose environment the server inherits unchanged
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CREDENTIAL_RE = re.compile(r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}")


def _env_of(pid: int) -> dict[str, str]:
    proc = Path(f"/proc/{pid}/environ")
    if proc.exists():
        pairs = [p.split("=", 1) for p in proc.read_bytes().decode("utf-8", "replace").split("\0") if "=" in p]
        return dict(pairs)
    return dict(os.environ)


def _substitute(value: Any, revision: int | None) -> Any:
    if value == "$revision":
        return revision
    if value == "$revision_text":  # inside an argv, which is all strings
        return str(revision)
    if isinstance(value, dict):
        return {k: _substitute(v, revision) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, revision) for v in value]
    return value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--profile", default="normal")
    a = ap.parse_args()
    steps = json.loads(Path(a.script).read_text(encoding="utf-8"))
    kwargs: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    server = subprocess.Popen([sys.executable, "-m", "aew", "lead", "mcp", "--profile", a.profile],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    assert server.stdin is not None and server.stdout is not None and server.stderr is not None
    out = Path(a.transcript).open("w", encoding="utf-8")
    revision: int | None = None
    rid = 0
    for i, step in enumerate(steps):
        record: dict[str, Any] = {"i": i, "step": step}
        if "touch" in step:
            Path(step["touch"]).touch()
        elif "wait_file" in step:
            deadline = time.monotonic() + float(step.get("timeout", 120))
            while not Path(step["wait_file"]).exists() and time.monotonic() < deadline:
                time.sleep(0.05)
        elif "server_env" in step:
            env = _env_of(server.pid)
            Path(step["server_env"]).write_text(json.dumps({
                "names": sorted(env), "credential_shaped": [k for k, v in env.items() if CREDENTIAL_RE.search(v)],
                "from": "process" if Path(f"/proc/{server.pid}/environ").exists() else "inherited"}),
                encoding="utf-8")
        else:
            if "notify" in step:
                message: dict[str, Any] = {"jsonrpc": "2.0", "method": step["notify"]}
            else:
                rid += 1
                if "call" in step:
                    params = {"name": step["call"], "arguments": _substitute(step.get("arguments", {}), revision)}
                    message = {"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": params}
                else:
                    message = {"jsonrpc": "2.0", "id": rid, "method": step["rpc"], "params": step.get("params", {})}
            server.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            server.stdin.flush()
            if "notify" not in step:
                line = server.stdout.readline().decode("utf-8")
                reply = json.loads(line) if line.strip() else None
                record["reply"] = reply
                content = ((reply or {}).get("result") or {}).get("structuredContent")
                if isinstance(content, dict) and isinstance(content.get("revision"), int):
                    revision = content["revision"]
        out.write(json.dumps(record) + "\n")
        out.flush()
    server.stdin.close()
    try:
        code = server.wait(timeout=30)
    except subprocess.TimeoutExpired:
        server.kill()
        code = server.wait()
    tail = server.stderr.read().decode("utf-8", "replace")[-2000:]
    out.write(json.dumps({"i": "end", "server_exit": code, "server_stderr": tail,
                          "own_env": {"names": sorted(os.environ),
                                      "credential_shaped": [k for k, v in os.environ.items()
                                                            if CREDENTIAL_RE.search(v)]}}) + "\n")
    out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
