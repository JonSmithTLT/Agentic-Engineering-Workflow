"""T6 network-containment probe, part 1: the namespace and the two bridges (Rocky 8.10, bubblewrap 0.4.0, stdlib only).

Run on the VM:  python3.11 netns_probe.py   (writes netns_probe.out.txt beside itself)

P1  --unshare-net: only lo exists; an outbound connect fails fast (no route), DNS fails fast.
P2  A filesystem AF_UNIX socket (the custody bridge's kind) bound read-only into a --unshare-net sandbox is
    connectable from inside; an abstract AF_UNIX socket is not (abstract sockets belong to the network namespace).
P3  Supervisor <-> private server across the namespace: a forwarder *inside* the sandbox listens on a unix socket in a
    bound-in directory and connects to the server on the sandbox's own 127.0.0.1; the host connects to the unix
    socket. Latency per request measured against plain loopback.
P4  Egress through a host-side allowlisting HTTP CONNECT proxy on a unix socket: inside the sandbox a forwarder
    127.0.0.1:3128 -> unix; python's urllib with HTTPS_PROXY/HTTP_PROXY reaches an allowed target (a local HTTP
    server on the host's loopback standing in for the gateway) and is refused for any other host. The provider key
    never enters the sandbox: the proxy adds it.
P5  slirp4netns as the alternative: a NAT uplink for the namespace (full egress, no allowlist), startup cost.
"""

from __future__ import annotations

import http.client
import http.server
import os
import select
import shutil
import socket
import socketserver
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


def say(s: str = "") -> None:
    print(s, flush=True)
    OUT.append(s)


def sandbox(*extra: str, net: bool = False) -> list[str]:
    argv = [BWRAP, "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
            "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
    if not net:
        argv.append("--unshare-net")
    return [*argv, *extra, "--"]


def run_in(code: str, *extra: str, net: bool = False, timeout: float = 30, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([*sandbox(*extra, net=net), PY, "-c", textwrap.dedent(code)], capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, **(env or {})})


# ----------------------------------------------------------------------------------------------- P1

def p1() -> None:
    say("\n## P1: --unshare-net")
    r = run_in("""
        import socket, time, os
        print("ifaces:", sorted(os.listdir("/sys/class/net")))
        t=time.perf_counter()
        try:
            s=socket.create_connection(("1.1.1.1",443),timeout=5); print("connect: UNEXPECTED success")
        except OSError as e: print(f"connect 1.1.1.1:443 -> {type(e).__name__}: {e} in {(time.perf_counter()-t)*1000:.0f} ms")
        t=time.perf_counter()
        try:
            socket.getaddrinfo("models.dev",443); print("dns: UNEXPECTED success")
        except OSError as e: print(f"dns models.dev -> {type(e).__name__}: {e} in {(time.perf_counter()-t)*1000:.0f} ms")
        s=socket.socket(); s.bind(("127.0.0.1",0)); print("sandbox loopback bind ok on port", s.getsockname()[1])
    """)
    say(r.stdout.strip() + (("\nstderr: " + r.stderr.strip()) if r.stderr.strip() else ""))


# ----------------------------------------------------------------------------------------------- P2

def p2() -> None:
    say("\n## P2: unix sockets across the namespace")
    d = tempfile.mkdtemp(prefix="t6-bridge-", dir=Path.home() / ".aew-test-tmp")
    os.chmod(d, 0o700)
    path = os.path.join(d, "s")
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(path)
    srv.listen(1)
    ab = socket.socket(socket.AF_UNIX)
    ab.bind(b"\0t6-abstract-probe")
    ab.listen(1)

    def accept(sock, tag):
        sock.settimeout(10)
        try:
            c, _ = sock.accept()
            c.sendall(tag)
            c.close()
        except OSError:
            pass

    for sock, tag in ((srv, b"fs-ok"), (ab, b"abstract-ok")):
        threading.Thread(target=accept, args=(sock, tag), daemon=True).start()
    r = run_in(f"""
        import socket
        for fam,addr in (("fs", {path!r}), ("abstract", b"\\0t6-abstract-probe")):
            s=socket.socket(socket.AF_UNIX); s.settimeout(3)
            try: s.connect(addr); print(fam, "->", s.recv(32).decode())
            except OSError as e: print(fam, "->", type(e).__name__, e)
    """, "--ro-bind", d, d)
    say(r.stdout.strip() + (("\nstderr: " + r.stderr.strip()) if r.stderr.strip() else ""))
    srv.close(); ab.close(); shutil.rmtree(d, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- P3

FORWARDER = r'''
import socket, threading, sys, os, select
def pump(a, b):
    try:
        while True:
            r,_,_ = select.select([a,b],[],[])
            for s in r:
                data = s.recv(65536)
                if not data: return
                (b if s is a else a).sendall(data)
    except OSError: pass
    finally:
        for s in (a,b):
            try: s.close()
            except OSError: pass
def serve(listen, connect):
    """listen/connect: ('unix', path) or ('tcp', host, port)"""
    ls = socket.socket(socket.AF_UNIX if listen[0]=='unix' else socket.AF_INET)
    if listen[0]=='tcp': ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(listen[1] if listen[0]=='unix' else (listen[1], listen[2])); ls.listen(64)
    while True:
        c,_ = ls.accept()
        try:
            u = socket.socket(socket.AF_UNIX if connect[0]=='unix' else socket.AF_INET)
            u.connect(connect[1] if connect[0]=='unix' else (connect[1], connect[2]))
        except OSError:
            c.close(); continue
        threading.Thread(target=pump, args=(c,u), daemon=True).start()
'''


def p3() -> None:
    say("\n## P3: supervisor -> private server through an in-sandbox unix forwarder")
    d = tempfile.mkdtemp(prefix="t6-fwd-", dir=Path.home() / ".aew-test-tmp")
    os.chmod(d, 0o700)
    sock = os.path.join(d, "server.sock")
    # Inside: an HTTP server on the sandbox's 127.0.0.1:0 (stands in for opencode-cli serve) plus the forwarder
    # unix -> that port. The sandbox prints the port, then serves until killed.
    code = FORWARDER + f"""
import http.server, json, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps({{"path":self.path,"ns":"sandbox"}}).encode(); self.send_response(200)
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*a): pass
srv=http.server.ThreadingHTTPServer(("127.0.0.1",0),H); port=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
print(json.dumps({{"url":f"http://127.0.0.1:{{port}}"}}),flush=True)
serve(('unix', {sock!r}), ('tcp','127.0.0.1',port))
"""
    proc = subprocess.Popen([*sandbox("--bind", d, d), PY, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    line = proc.stdout.readline().strip()
    say(f"sandbox announced: {line}")
    t0 = time.perf_counter()
    while not os.path.exists(sock) and time.perf_counter() - t0 < 5:
        time.sleep(0.02)
    url = line.split('"')[3]
    port = int(url.rsplit(":", 1)[1])
    try:
        http.client.HTTPConnection("127.0.0.1", port, timeout=2).request("GET", "/api/info")
        say("host -> sandbox 127.0.0.1:port directly: UNEXPECTED success")
    except OSError as e:
        say(f"host -> sandbox 127.0.0.1:{port} directly: {type(e).__name__} (as expected: different loopback)")

    class UnixConn(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX); self.sock.connect(sock)

    lat = []
    for i in range(200):
        c = UnixConn("localhost", timeout=5)
        t = time.perf_counter()
        c.request("GET", f"/api/info?{i}")
        body = c.getresponse().read()
        lat.append((time.perf_counter() - t) * 1000)
        c.close()
    lat.sort()
    say(f"host -> unix -> in-sandbox forwarder -> server: 200 requests, median {lat[100]:.2f} ms, p95 {lat[190]:.2f} ms; "
        f"body {body.decode()}")
    # baseline: plain loopback on the host
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a): pass
    base = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=base.serve_forever, daemon=True).start()
    lat = []
    for i in range(200):
        c = http.client.HTTPConnection("127.0.0.1", base.server_address[1], timeout=5)
        t = time.perf_counter(); c.request("GET", "/x"); c.getresponse().read(); lat.append((time.perf_counter() - t) * 1000); c.close()
    lat.sort()
    say(f"baseline plain loopback: median {lat[100]:.2f} ms, p95 {lat[190]:.2f} ms")
    base.shutdown(); proc.kill(); proc.wait(); shutil.rmtree(d, ignore_errors=True)
    say("note: the forwarder must be started by the sandbox command itself (a wrapper that starts it, then execs the "
        "harness); nsenter into the sandbox's netns from outside needs CAP_SYS_ADMIN over its user namespace")


# ----------------------------------------------------------------------------------------------- P4

PROXY = r'''
import socket, threading, select, sys, os
ALLOW = set(sys.argv[2].split(","))   # host:port entries the proxy will CONNECT to
KEY = os.environ.get("PROBE_PROVIDER_KEY", "")
LOG = open(sys.argv[3], "a")
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
        if method=="CONNECT":
            hostport=target
            if hostport not in ALLOW:
                LOG.write(f"DENY CONNECT {hostport}\n"); LOG.flush()
                c.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"); c.close(); return
            host,port=hostport.rsplit(":",1); u=socket.create_connection((host,int(port)),timeout=10)
            c.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n"); LOG.write(f"ALLOW CONNECT {hostport}\n"); LOG.flush()
            pump(c,u)
        else:  # plain HTTP proxying: the proxy may add the provider key here (the sandbox never has it)
            from urllib.parse import urlsplit
            u_=urlsplit(target); hostport=f"{u_.hostname}:{u_.port or 80}"
            if hostport not in ALLOW:
                LOG.write(f"DENY {method} {hostport}\n"); LOG.flush()
                c.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"); c.close(); return
            rest=head.split(b"\r\n",1)[1]
            req=f"{method} {u_.path or '/'}{'?'+u_.query if u_.query else ''} HTTP/1.1\r\n".encode()+ (f"Authorization: Bearer {KEY}\r\n".encode() if KEY else b"") + rest
            up=socket.create_connection((u_.hostname,u_.port or 80),timeout=10); up.sendall(req)
            LOG.write(f"ALLOW {method} {hostport} (key added: {bool(KEY)})\n"); LOG.flush()
            pump(c,up)
    except Exception as e:
        LOG.write(f"ERR {e}\n"); LOG.flush()
        try: c.close()
        except OSError: pass
ls=socket.socket(socket.AF_UNIX); ls.bind(sys.argv[1]); ls.listen(64)
while True:
    c,_=ls.accept(); threading.Thread(target=handle,args=(c,),daemon=True).start()
'''


def p4() -> None:
    say("\n## P4: egress through a host-side allowlisting proxy on a unix socket")
    d = tempfile.mkdtemp(prefix="t6-egress-", dir=Path.home() / ".aew-test-tmp")
    os.chmod(d, 0o700)
    psock = os.path.join(d, "proxy.sock")
    log = os.path.join(d, "proxy.log")
    seen = []

    class Gateway(http.server.BaseHTTPRequestHandler):  # stands in for the model gateway, on the host's loopback
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            self.send_response(200); self.send_header("Content-Length", "7"); self.end_headers(); self.wfile.write(b"gateway")
        def log_message(self, *a): pass
    gw = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    gw_port = gw.server_address[1]
    other = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    proxy = subprocess.Popen([PY, "-c", PROXY, psock, f"127.0.0.1:{gw_port}", log],
                             env={**os.environ, "PROBE_PROVIDER_KEY": "sk-probe-not-a-real-key"})
    t0 = time.perf_counter()
    while not os.path.exists(psock) and time.perf_counter() - t0 < 5:
        time.sleep(0.02)
    code = FORWARDER + f"""
import threading, urllib.request, urllib.error, os, time, json
threading.Thread(target=serve, args=(('tcp','127.0.0.1',3128), ('unix', {psock!r})), daemon=True).start()
time.sleep(0.2)
os.environ["HTTP_PROXY"]=os.environ["HTTPS_PROXY"]="http://127.0.0.1:3128"
print("env has provider key:", "PROBE_PROVIDER_KEY" in os.environ)
for url in ("http://127.0.0.1:{gw_port}/v1/models", "http://127.0.0.1:{other.server_address[1]}/v1/models", "http://example.com/"):
    t=time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=8) as r: print(f"{{url}} -> {{r.status}} {{r.read()[:20]!r}} in {{(time.perf_counter()-t)*1000:.0f}} ms")
    except urllib.error.HTTPError as e: print(f"{{url}} -> HTTP {{e.code}} (proxy refused) in {{(time.perf_counter()-t)*1000:.0f}} ms")
    except Exception as e: print(f"{{url}} -> {{type(e).__name__}}: {{e}}")
"""
    r = subprocess.run([*sandbox("--ro-bind", d, d), PY, "-c", code], capture_output=True, text=True, timeout=60)
    say(r.stdout.strip() + (("\nstderr: " + r.stderr.strip()[-800:]) if r.stderr.strip() else ""))
    say(f"gateway saw Authorization headers: {seen}")
    say("proxy log:\n  " + "\n  ".join(Path(log).read_text().strip().splitlines()))
    proxy.kill(); proxy.wait(); gw.shutdown(); other.shutdown(); shutil.rmtree(d, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- P5

def p5() -> None:
    say("\n## P5: slirp4netns (NAT uplink, no allowlist) as the alternative")
    slirp = shutil.which("slirp4netns")
    if not slirp:
        say("slirp4netns not installed"); return
    ready = tempfile.mktemp(prefix="t6-ready-", dir=Path.home() / ".aew-test-tmp")
    code = f"""
import os, time, socket, sys
open({ready!r},"w").write(str(os.getpid()))
for _ in range(300):
    if os.path.exists({ready!r}+".go"): break
    time.sleep(0.05)
t=time.perf_counter()
try:
    s=socket.create_connection(("1.1.1.1",443),timeout=5); print("outbound via slirp: ok in %.0f ms"%((time.perf_counter()-t)*1000)); s.close()
except OSError as e: print("outbound via slirp:", type(e).__name__, e)
try:
    s=socket.create_connection(("10.0.2.2",22),timeout=3); print("host via 10.0.2.2:22 reachable (slirp default; --disable-host-loopback does not cover it)"); s.close()
except OSError as e: print("host 10.0.2.2:22:", type(e).__name__)
print("ifaces:", sorted(os.listdir("/sys/class/net")))
"""
    # slirp4netns needs the sandbox's user+net namespaces: bwrap --unshare-user is implicit when unprivileged;
    # attach to the sandbox's pid (the python process, PID 1 of its pid ns is bwrap's child; we use the host pid).
    rdir = str(Path(ready).parent)
    proc = subprocess.Popen([*sandbox("--bind", rdir, rdir), PY, "-c", code], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    t0 = time.perf_counter()
    while not os.path.exists(ready) and time.perf_counter() - t0 < 10:
        time.sleep(0.02)
    # the pid written is namespace-local; find the host pid of our bwrap's child
    host_pid = None
    for _ in range(100):
        children = subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True).stdout.split()
        if children:
            host_pid = children[0]; break
        time.sleep(0.05)
    t1 = time.perf_counter()
    slirp_proc = subprocess.Popen([slirp, "--configure", "--mtu=65520", "--disable-host-loopback", str(host_pid), "tap0"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    say(f"slirp4netns attached to host pid {host_pid}: alive={slirp_proc.poll() is None} after {(time.perf_counter()-t1)*1000:.0f} ms")
    open(ready + ".go", "w").close()
    out, err = proc.communicate(timeout=30)
    say(out.strip() + (("\nsandbox stderr: " + err.strip()[-300:]) if err.strip() else ""))
    slirp_proc.kill(); se = slirp_proc.communicate()[1]
    if se.strip():
        say("slirp stderr: " + se.strip()[-300:])
    for p in (ready, ready + ".go"):
        try: os.unlink(p)
        except OSError: pass


def main() -> None:
    (Path.home() / ".aew-test-tmp").mkdir(exist_ok=True)
    say("# T6 network containment probe, part 1")
    say(f"kernel {os.uname().release}; bwrap {subprocess.run([BWRAP,'--version'],capture_output=True,text=True).stdout.strip()}; "
        f"python {sys.version.split()[0]}; max_user_namespaces {Path('/proc/sys/user/max_user_namespaces').read_text().strip()}")
    only = sys.argv[1:] or ["p1", "p2", "p3", "p4", "p5"]
    for step in (p1, p2, p3, p4, p5):
        if step.__name__ not in only:
            continue
        try:
            step()
        except Exception as exc:  # keep going; the note records what failed
            say(f"{step.__name__} FAILED: {type(exc).__name__}: {exc}")
    (HERE / "netns_probe.out.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
