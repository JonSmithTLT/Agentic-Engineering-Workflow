"""T6 network-containment probe, part 2: what OpenCode 2.0.18 `serve` does on the network at startup, and whether
it comes up with no network at all (Rocky 8.10; stdlib only; run with python3.11).

    python3.11 opencode_net_probe.py /path/to/opencode-cli

A  shared network, strace -f -e connect: every non-loopback connect() the server (and anything it starts) makes
   while coming up, answering /api/info, and loading its model catalog (/api/model polled, as the adapter does).
   Also with HTTP(S)_PROXY pointing at a logging CONNECT proxy on the host: does the Bun runtime honour the proxy
   variables (then the proxy log names the hosts)?
B  --unshare-net, fresh private XDG state: does `serve` start, answer /api/info, and does /api/model ever list
   models? What does its stderr say?
C  --unshare-net, with the model catalog cache copied from run A: same questions (air-gap seeding).

The server is started the way the adapter starts it: ``serve --stdio --hostname 127.0.0.1 --port 0``, private XDG
dirs, OPENCODE_CONFIG_CONTENT, OPENCODE_DISABLE_PROJECT_CONFIG=1, OPENCODE_DISABLE_AUTOUPDATE=1, OPENCODE_PASSWORD.
Inside --unshare-net the host cannot reach the server's loopback, so the probe runs its HTTP client *inside* the
sandbox too (one python process starts the server and polls it).
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT: list[str] = []
BWRAP = shutil.which("bwrap") or "/usr/bin/bwrap"
PY = sys.executable
CLI = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/opencode-2.0.18/opt/OpenCode/resources/opencode-cli")
CONFIG = {"$schema": "https://opencode.ai/config.json", "autoupdate": False, "share": "disabled",
          "lsp": False, "formatter": False}


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


DRIVER = r'''
import os, sys, json, subprocess, time, http.client, base64, socket
cli, state, config, log, wait_s = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
strace = sys.argv[6] if len(sys.argv) > 6 else ""
env = {k: v for k, v in os.environ.items() if k in ("PATH","HOME","USER","LANG","TERM","TMPDIR","HTTP_PROXY","HTTPS_PROXY","NO_PROXY","http_proxy","https_proxy","no_proxy","OPENAI_API_KEY","ANTHROPIC_API_KEY")}
env.update({"XDG_CONFIG_HOME": f"{state}/config", "XDG_DATA_HOME": f"{state}/data", "XDG_CACHE_HOME": f"{state}/cache",
            "XDG_STATE_HOME": f"{state}/state", "OPENCODE_CONFIG_CONTENT": config, "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_PASSWORD": "probe-password", "TMPDIR": "/tmp"})
for d in ("config","data","cache","state"): os.makedirs(f"{state}/{d}", exist_ok=True)
argv = [cli, "serve", "--stdio", "--hostname", "127.0.0.1", "--port", "0"]
if strace: argv = ["strace", "-f", "-e", "trace=connect", "-o", strace, "-s", "200", *argv]
t0 = time.perf_counter()
p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(log, "wb"), env=env, cwd=state, text=True)
url = None
while time.perf_counter() - t0 < 60:
    line = p.stdout.readline()
    if not line:
        break
    if line.startswith("{"):
        try: url = json.loads(line).get("url"); break
        except Exception: pass
print(json.dumps({"announced": url, "start_s": round(time.perf_counter()-t0, 2), "exit": p.poll()}), flush=True)
if url:
    host, port = url.split("//")[1].rstrip("/").split(":"); auth = "Basic " + base64.b64encode(b"opencode:probe-password").decode()
    def get(path):
        c = http.client.HTTPConnection(host, int(port), timeout=10); c.request("GET", path, headers={"Authorization": auth}); r = c.getresponse(); b = r.read(); c.close(); return r.status, b
    try:
        s, b = get("/api/info"); print(json.dumps({"info": s, "version": json.loads(b).get("version") if s == 200 else b[:100].decode(errors="replace")}), flush=True)
    except Exception as e: print(json.dumps({"info": f"{type(e).__name__}: {e}"}), flush=True)
    t1 = time.perf_counter(); models = None; last = None
    while time.perf_counter() - t1 < wait_s:
        try:
            s, b = get("/api/model?" + __import__("urllib.parse").parse.urlencode({"location[directory]": state}))
            last = (s, b[:120].decode(errors="replace"))
            if s == 200:
                doc = json.loads(b); data = doc.get("data") if isinstance(doc, dict) else doc
                n = len(data) if isinstance(data, list) else None
                if n: models = n; last = (s, str(sorted({str(m.get("providerID") or m.get("provider") or "?") for m in data}))[:200], [str(m.get("id") or m.get("model") or "?") for m in data if (m.get("providerID") or m.get("provider")) != "opencode"][:8]); break
        except Exception as e: last = str(e)
        time.sleep(1.0)
    print(json.dumps({"models": models, "catalog_wait_s": round(time.perf_counter()-t1, 1), "last": last}), flush=True)
    time.sleep(2)
try:
    p.stdin.close()
except Exception: pass
try: p.wait(timeout=15)
except subprocess.TimeoutExpired: p.kill(); p.wait()
print(json.dumps({"exit": p.returncode, "state_files": sorted(str(x.relative_to(state)) for x in __import__("pathlib").Path(state).rglob("*") if x.is_file() and x.name not in ("server.log", "trace.txt"))[:40]}), flush=True)
'''

PROXYLOG = r'''
import socket, threading, select, sys
LOG = open(sys.argv[2], "a")
def pump(a,b):
    try:
        while True:
            r,_,_=select.select([a,b],[],[])
            for s in r:
                d=s.recv(65536)
                if not d: return
                (b if s is a else a).sendall(d)
    except OSError: pass
    finally:
        for s in (a,b):
            try: s.close()
            except OSError: pass
def handle(c):
    try:
        head=b""
        while b"\r\n\r\n" not in head:
            d=c.recv(4096)
            if not d: return
            head+=d
        line=head.split(b"\r\n")[0].decode(); method,target,_=line.split(" ",2)
        LOG.write(f"{method} {target}\n"); LOG.flush()
        if method=="CONNECT":
            host,port=target.rsplit(":",1); u=socket.create_connection((host,int(port)),timeout=10)
            c.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n"); pump(c,u)
        else:
            c.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"); c.close()
    except Exception as e:
        LOG.write(f"ERR {e}\n"); LOG.flush()
ls=socket.socket(); ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); ls.bind(("127.0.0.1", int(sys.argv[1]))); ls.listen(64)
while True:
    c,_=ls.accept(); threading.Thread(target=handle,args=(c,),daemon=True).start()
'''


def sandbox(*extra: str, net: bool) -> list[str]:
    argv = [BWRAP, "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--ro-bind", "/", "/",
            "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
    if not net:
        argv.append("--unshare-net")
    return [*argv, *extra, "--"]


def drive(state: Path, *, net: bool, wait_s: float, strace: bool, env: dict | None = None) -> list[dict]:
    log = state / "server.log"
    trace = str(state / "trace.txt") if strace else ""
    argv = [*sandbox("--bind", str(state), str(state), net=net), PY, "-c", DRIVER, CLI, str(state), json.dumps(CONFIG),
            str(log), str(wait_s), trace]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=wait_s + 120, env={**os.environ, **(env or {})})
    out = []
    for line in r.stdout.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"raw": line})
    if r.stderr.strip():
        out.append({"driver_stderr": r.stderr.strip()[-500:]})
    return out


def connects(trace: Path) -> dict[str, int]:
    """Non-loopback AF_INET/AF_INET6 connect() targets in an strace -f trace, counted."""
    seen: dict[str, int] = {}
    if not trace.exists():
        return seen
    for line in trace.read_text(errors="replace").splitlines():
        m = re.search(r'connect\(\d+, \{sa_family=AF_INET6?, sin6?_port=htons\((\d+)\), .*?inet_(?:pton|addr)\([^"]*"([^"]+)"', line)
        if not m:
            continue
        port, addr = m.group(1), m.group(2)
        if addr.startswith("127.") or addr == "::1":
            continue
        seen[f"{addr}:{port}"] = seen.get(f"{addr}:{port}", 0) + 1
    return seen


def catalog_main() -> None:
    """D/E: does a configured provider's model list need the network? A dummy provider key is set in the server
    environment (never a real one); the question is whether the pinned-model check (adapter: /api/model must list
    provider/model#variant) can pass with --unshare-net from the embedded catalog alone."""
    base = Path.home() / ".aew-test-tmp"
    base.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="review-t6-cat-", dir=base))
    say("# T6 probe part 3: provider catalog with and without network (dummy OPENAI_API_KEY in the server env)")
    env = {"OPENAI_API_KEY": "sk-dummy-not-a-key"}
    for tag, net in (("D shared net", True), ("E --unshare-net", False)):
        say("")
        say("## " + tag)
        d = work / tag.split()[0]
        d.mkdir()
        for rec in drive(d, net=net, wait_s=30, strace=False, env=env):
            if "last" in rec and isinstance(rec.get("last"), list):
                rec["last"] = rec["last"][:3]
            say("  " + json.dumps(rec)[:600])
    (HERE / "opencode_net_probe.catalog.out.txt").write_text(chr(10).join(OUT) + chr(10), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[2] == "--catalog":
        return catalog_main()
    base = Path.home() / ".aew-test-tmp"
    base.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="review-t6-oc-", dir=base))
    say("# T6 network containment probe, part 2: OpenCode 2.0.18 serve")
    say(f"cli {CLI}; version: {subprocess.run([CLI, '--version'], capture_output=True, text=True).stdout.strip()}")
    say(f"config: {json.dumps(CONFIG)}")

    # A1: shared net, strace
    say("\n## A1: shared network, strace -f -e connect, fresh XDG state, 45 s catalog wait")
    sa = work / "A1"; sa.mkdir()
    for rec in drive(sa, net=True, wait_s=45, strace=True):
        say("  " + json.dumps(rec))
    say("  non-loopback connect() targets: " + json.dumps(connects(sa / "trace.txt")))
    try:
        hosts = {}
        for addrport in connects(sa / "trace.txt"):
            addr = addrport.rsplit(":", 1)[0]
            try: hosts[addr] = socket.gethostbyaddr(addr)[0]
            except OSError: hosts[addr] = "?"
        say("  reverse lookups: " + json.dumps(hosts))
    except Exception as e:
        say(f"  reverse lookups failed: {e}")
    srv_log = (sa / "server.log").read_text(errors="replace")
    say("  server.log (last 15 lines):\n    " + "\n    ".join(srv_log.strip().splitlines()[-15:]))

    # A2: shared net, HTTP(S)_PROXY to a logging proxy
    say("\n## A2: shared network, HTTP_PROXY/HTTPS_PROXY -> logging CONNECT proxy on the host (does Bun honour them?)")
    sb = work / "A2"; sb.mkdir()
    plog = sb / "proxy.log"; plog.write_text("")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); pport = s.getsockname()[1]; s.close()
    proxy = subprocess.Popen([PY, "-c", PROXYLOG, str(pport), str(plog)])
    time.sleep(0.5)
    penv = {"HTTP_PROXY": f"http://127.0.0.1:{pport}", "HTTPS_PROXY": f"http://127.0.0.1:{pport}",
            "http_proxy": f"http://127.0.0.1:{pport}", "https_proxy": f"http://127.0.0.1:{pport}", "NO_PROXY": "127.0.0.1,localhost"}
    for rec in drive(sb, net=True, wait_s=30, strace=True, env=penv):
        say("  " + json.dumps(rec))
    proxy.kill(); proxy.wait()
    say("  proxy log: " + json.dumps(plog.read_text().strip().splitlines()[:20]))
    say("  non-loopback connect() targets with proxy env set: " + json.dumps(connects(sb / "trace.txt")))

    # B: no network, fresh state
    say("\n## B: --unshare-net, fresh XDG state (no catalog cache), 45 s catalog wait")
    sc = work / "B"; sc.mkdir()
    for rec in drive(sc, net=False, wait_s=45, strace=False):
        say("  " + json.dumps(rec))
    say("  server.log (last 15 lines):\n    " + "\n    ".join((sc / "server.log").read_text(errors="replace").strip().splitlines()[-15:]))

    # C: no network, cache seeded from A1
    say("\n## C: --unshare-net, XDG cache copied from A1 (seeded catalog), 30 s catalog wait")
    sd = work / "C"; sd.mkdir()
    for sub in ("cache", "data", "config", "state"):
        if (sa / sub).exists():
            shutil.copytree(sa / sub, sd / sub)
    say("  seeded files: " + json.dumps(sorted(str(p.relative_to(sd)) for p in sd.rglob("*") if p.is_file())[:40]))
    for rec in drive(sd, net=False, wait_s=30, strace=False):
        say("  " + json.dumps(rec))
    say("  server.log (last 15 lines):\n    " + "\n    ".join((sd / "server.log").read_text(errors="replace").strip().splitlines()[-15:]))

    (HERE / "opencode_net_probe.out.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    shutil.copy(sa / "trace.txt", HERE / "opencode_net_probe.A1.trace.txt") if (sa / "trace.txt").exists() else None
    shutil.rmtree(work, ignore_errors=True)
    say(f"\ncleaned {work}")


if __name__ == "__main__":
    main()
