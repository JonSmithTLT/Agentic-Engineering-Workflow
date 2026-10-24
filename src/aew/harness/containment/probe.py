"""The launch self-test: the run's own assembled layout, exercised before any harness process starts (M4-B).

A probe process runs inside the layout and tries what containment must stop and what the role must be able to do:

* append to an existing sentinel outside every writable root, and create a new sibling next to the workspace;
* open each protected path for writing (checked with ``access(W_OK)``, which a read-only mount refuses without
  changing anything): the repository's real git metadata, the project's ``.aew``, and two markers the host places
  for the probe only, one in the host's temporary directory (where every run's bridge socket lives) and one in a
  sibling run's directory (M4-B review: whatever widened the layout, reaching these fails the test);
* create a file in every writable root.

The host then checks the outcome itself: the sentinel is byte-identical, the sibling does not exist, each writable
root's file arrived on the host (a bind that is not the host's path is not a writable root). A layout that passes
is contained; anything else is a failure with its reason. The test catches bind-order mistakes, such as a broad
writable root laid over the read-only host.

The probe also reads what the gates' rows need (STG-05 CB-12, rows 1 to 5), each judged by the host and recorded on
the run's label, pass or fail:

* **row 1, the network** (F28 §3.6; CS-3b): in a network of its own, the probe runs under the run's shim, with the
  run's legs pointed at stand-ins the host starts in the run's network directory: a provider relay whose upstream is a
  listener of the host's (with a credential of the probe's own), and an egress proxy with the run's allowlist. The host
  judges: the sandbox's network namespace is not the launcher's; a direct connection out, TCP or UDP, has no route; a
  loopback port and an abstract socket the host holds are not there; the listening ports inside are only the shim's
  and the probe's; the supervisor reaches the probe through the shim; a request through the relay reaches its
  upstream with the credential in place of its sentinel; the egress proxy refuses a target off the allowlist; the
  bridge answers by its path. A run on the host's network records its mode and claims nothing;
* **row 2:** ``/run`` is a read-only tmpfs holding only what the layout put there, and no socket of a failing class
  (:mod:`.sockets`) is reachable inside. The host reads the kernel's socket table, with a listener of its own bound
  first as the control, and the probe checks each path socket in it, by device and inode, at every path the
  sandbox's mount table exposes it at (D-CS2-2). In a network of its own, an abstract socket the host holds that is
  listed inside fails it (D-CS2-5); on the host's network each is a fact, with its class;
* **row 3:** no display credential is readable, and no :data:`~.layout.DISPLAY_ENV` variable reaches the process
  (the probe is handed each of them, set, so a sandbox that does not unset them fails);
* **row 4:** the process has no controlling terminal. The kernel refuses ``TIOCSTI`` on a terminal that is not the
  caller's controlling terminal, to a caller without ``CAP_SYS_ADMIN`` in the initial user namespace, so with none
  no descriptor it holds accepts it. The probe checks the property and never pushes input anywhere;
* **row 5:** the writes above, and each mask holds: secret directories list empty, secret files read empty, a runs
  mask shows only the run's own directories, and neither marker is visible.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from aew.harness.containment import sockets
from aew.harness.containment.layout import (
    DISPLAY_ENV,
    NET_SHIM,
    PROXY_ONLY,
    SANDBOX_TMP,
    VAR_RUN,
    Layout,
    _within,
    bwrap_argv,
    host_masks,
)

TIMEOUT_S = 30.0
VERSION_TIMEOUT_S = 10.0
BOUND_S = TIMEOUT_S + VERSION_TIMEOUT_S  # the self-test and the mechanism check, at a run's start
CANARY = "aew-self-test"  # the value of each DISPLAY_ENV variable the probe is handed
# Row 2's words for a reachable socket of the launching user's whose holder cannot be identified (D-CS2-6), which
# `aew doctor` shows with the row's reason
UNIDENTIFIED_REMEDY = (" (its holder, a process of the launching user's, cannot be identified, so it counts as a "
                       "credential: stop that process, move its socket under a masked path, or set containment.mode: "
                       "allow_weaker to run labelled workdir_separation_only)")
# Row 1: addresses that are never routed anywhere real, TEST-NET-1 (RFC 5737) and IPv6's documentation prefix
# (RFC 3849), which a connection out of a namespace with only its loopback cannot reach at all (F28 §1, P1: at once,
# ENETUNREACH); a name on no allowlist, and never resolvable (.invalid, RFC 6761); and how long the probe waits for the
# host's connection through the shim.
OUTSIDE, OUTSIDE6 = "192.0.2.1", "2001:db8::1"
UNREACHABLE = ("ENETUNREACH", "EHOSTUNREACH")
UNLISTED = "aew-probe.invalid:443"
SERVER_WAIT_S = 10.0
# How long the host waits for its echo thread once the sandbox has ended: its connection then ends at once (the shim is
# gone), so this bounds only a thread between two attempts.
ECHO_JOIN_S = 2.0
PROBE_SERVER, PROBE_RELAY, PROBE_EGRESS = f"{NET_SHIM}/probe-server.sock", "probe-relay.sock", "probe-egress.sock"

# Standard library only, and isolated (-I): it runs in the sandbox. Its definitions come first, so a test can read them
# without running it (``exec`` with another ``__name__``).
_PAYLOAD = r"""
import errno, json, os, re, shutil, stat, sys, time
def append(p):
    try:
        fd = os.open(p, os.O_WRONLY | os.O_APPEND)
    except OSError:
        return False
    try:
        os.write(fd, b"x")
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
def create(p):
    try:
        os.close(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        return True
    except OSError:
        return False
def unescape(raw):
    return os.fsdecode(re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m.group(1), 8)]), raw))
def mountinfo(path="/proc/self/mountinfo"):
    # (major:minor, root within its filesystem, mount point, type, read-only), in mount order: of several mounts at
    # one path, the last is on top. Split as the kernel writes it (as sockets.mounts does): records at the newline,
    # fields at single spaces; a line that does not parse raises ValueError
    with open(path, "rb") as f:
        lines = f.read().split(b"\n")
    if lines[-1] != b"":
        raise ValueError(path + " does not end with a newline")
    out = []
    for line in lines[:-1]:
        left, sep, right = line.partition(b" - ")
        fields, rest = left.split(b" "), right.split(b" ")
        if not sep or len(fields) < 6 or not re.fullmatch(rb"[0-9]+:[0-9]+", fields[2]) or not rest[0]:
            raise ValueError("a line of %s is not a mount's: %r" % (path, line[:80]))
        out.append((fields[2].decode(), unescape(fields[3]), unescape(fields[4]), os.fsdecode(rest[0]),
                    b"ro" in fields[5].split(b",")))
    return out
def mount_table(path="/proc/self/mountinfo"):
    # (the table, []) or ([], [what went wrong]): the row fails on the second
    try:
        return mountinfo(path), []
    except (OSError, ValueError) as e:
        return [], [{"path": path, "error": str(e)}]
def inside_paths(socket, table):
    # each spelling of the socket (as listed, and with its directory resolved on the host), and its place under every
    # mount of its filesystem whose root holds it
    spellings = [(socket["path"], socket.get("fspath"))]
    if socket.get("real"):
        spellings.append((socket["real"]["path"], socket["real"].get("fspath")))
    out = []
    for path, fs in spellings:
        if path not in out:
            out.append(path)
        for majmin, root, point, _, _ in table if fs is not None else ():
            base = root.rstrip("/")
            if majmin == socket["majmin"] and (fs == root or fs.startswith(base + "/")):
                p = point.rstrip("/") + fs[len(base):] or "/"
                if p not in out:
                    out.append(p)
    return out
def reachable(candidates, table):
    # each socket found inside, the same file (device and inode), with where; and each check that failed
    found, errors = [], []
    for c in candidates:
        at = []
        for p in inside_paths(c, table):
            try:
                st = os.lstat(p)
            except (FileNotFoundError, NotADirectoryError):
                continue
            except OSError as e:
                errors.append({"path": p, "error": errno.errorcode.get(e.errno, str(e.errno))})
                continue
            if stat.S_ISSOCK(st.st_mode) and (st.st_dev, st.st_ino) == (c["dev"], c["ino"]):
                at.append(p)
        if at:
            found.append({"path": c["path"], "inside": at})
    return found, errors
def masked_tree(root, allowed):
    # what is in a host mask: anything that is neither what the layout put there nor on the way to it
    extra = []
    for d, dirs, files in os.walk(root):
        keep = []
        for n in dirs + files:
            p = os.path.join(d, n)
            if p in allowed:
                continue
            if any(a.startswith(p + "/") for a in allowed) and n in dirs and not os.path.islink(p):
                keep.append(n)
            else:
                extra.append(p)
        dirs[:] = [n for n in dirs if n in keep]
    return extra
def reads(p):
    try:
        with open(p, "rb") as f:
            return "empty" if not f.read(1) else "readable"
    except FileNotFoundError:
        return "absent"
    except IsADirectoryError:
        return "readable"
    except OSError:
        return "unreadable"
def listing(p):
    try:
        return sorted(os.listdir(p))
    except FileNotFoundError:
        return None
    except OSError as e:
        return [errno.errorcode.get(e.errno, str(e.errno))]
def terminal():
    fields = open("/proc/self/stat", "rb").read().rsplit(b")", 1)[1].split()
    try:
        os.close(os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY))
        tty = "opened"
    except OSError as e:
        tty = errno.errorcode.get(e.errno, str(e.errno))
    return {"tty_nr": int(fields[4]), "dev_tty": tty, "session_leader": os.getsid(0) == os.getpid()}
def failure(e):
    return errno.errorcode.get(e.errno, str(e.errno)) if e.errno else type(e).__name__
def attempt(family, address, dgram=False):
    # "connected" (or "sent", for UDP), else the error's name: a route out, or none
    import socket
    s = socket.socket(family, socket.SOCK_DGRAM if dgram else socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        if dgram:
            s.sendto(b"x", address)
            return "sent"
        s.connect(address)
        return "connected"
    except OSError as e:
        return failure(e)
    finally:
        s.close()
def listening():
    # [protocol, port] of every listening TCP socket and every bound UDP one in this network namespace
    out = []
    for proto in ("tcp", "tcp6", "udp", "udp6"):
        try:
            with open("/proc/net/" + proto, "rb") as f:
                lines = f.read().split(b"\n")[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) > 3 and (proto.startswith("udp") or fields[3] == b"0A"):
                out.append([proto, int(fields[1].rsplit(b":", 1)[1], 16)])
    return out
def abstract_names():
    names = []
    with open("/proc/net/unix", "rb") as f:
        lines = f.read().split(b"\n")[1:]
    for line in lines:
        m = re.fullmatch(rb"[0-9A-Fa-f]+: [0-9A-Fa-f]{8} [0-9A-Fa-f]{8} [0-9A-Fa-f]{8} [0-9A-Fa-f]{4} [0-9A-Fa-f]{2} +"
                         rb"[0-9]+(?: (.+))?", line, re.DOTALL)
        if m and m.group(1) and m.group(1).startswith(b"@"):
            names.append(os.fsdecode(m.group(1)))
    return names
def exchange(port, request):
    # one HTTP exchange with a loopback port inside: its status line and body, or the error
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=10)
    except OSError as e:
        return {"error": failure(e)}
    data = b""
    try:
        s.sendall(request)
        while len(data) < 65536:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    except OSError as e:
        return {"error": failure(e)}
    finally:
        s.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return {"status": head.split(b"\r\n")[0].decode("latin-1"), "body": body.decode("latin-1")}
def network(net, server):
    import socket
    out = {"netns": os.readlink("/proc/self/ns/net"), "listening": listening(), "abstract": abstract_names(),
           "direct": attempt(socket.AF_INET, (net["outside"], 9)),
           "direct_udp": attempt(socket.AF_INET, (net["outside"], 9), dgram=True),
           "direct6": attempt(socket.AF_INET6, (net["outside6"], 9)) if socket.has_ipv6 else "EAFNOSUPPORT",
           "host_port": attempt(socket.AF_INET, ("127.0.0.1", net["host_port"])),
           "host_abstract": attempt(socket.AF_UNIX, "\0" + net["host_abstract"])}
    if net.get("bridge"):
        out["bridge"] = attempt(socket.AF_UNIX, net["bridge"])
    out["relay"] = exchange(net["provider_port"], ("GET " + net["relay_path"] + " HTTP/1.1\r\nHost: probe\r\n"
                                                   "Authorization: Bearer " + net["sentinel"] + "\r\n\r\n").encode())
    out["egress"] = exchange(net["egress_port"], ("CONNECT " + net["unlisted"] + " HTTP/1.1\r\nHost: "
                                                  + net["unlisted"] + "\r\n\r\n").encode())
    # the supervisor's leg in, through the shim: the host connects and the probe echoes what it sent. A connection the
    # host gave up on before the shim reached this listener arrives empty, and the next one is taken
    end = time.monotonic() + net["server_wait"]
    out["server"] = "no_connection"
    while out["server"] != "echoed":
        try:
            server.settimeout(max(0.01, end - time.monotonic()))
            conn, _ = server.accept()
        except OSError as e:
            out["server"] = failure(e)
            break
        try:
            conn.settimeout(5)
            data = conn.recv(64)
            if data:
                conn.sendall(data)
                out["server"] = "echoed"
                conn.recv(1)  # the host hangs up once it has the echo: the shim exits with this process
        except OSError:
            pass
        finally:
            conn.close()
    return out
if __name__ == "__main__":
    spec = json.loads(sys.stdin.read())
    net = spec.get("network")
    server = None
    if net:  # listening before anything else, so the host's connection through the shim finds it
        import socket
        server = socket.create_server(("127.0.0.1", net["server_port"]))
    table, unread = mount_table()
    top = {point: (fstype, ro) for _, _, point, fstype, ro in table}
    t0 = time.monotonic()
    found, errors = reachable(spec["candidates"], table)
    errors = unread + errors
    print(json.dumps({
        "sentinel_written": append(spec["sentinel"]),
        "sibling_created": create(spec["sibling"]),
        "writable": {p: create(os.path.join(p, spec["name"])) for p in spec["writable"]},
        "protected_writable": [p for p in spec["protected"] if os.access(p, os.W_OK)],
        "pid": os.getpid(),
        "host_masks": {h: {"type": (top.get(h) or [None])[0], "readonly": (top.get(h) or [None, False])[1],
                           "extra": masked_tree(h, set(spec["inside_host_masks"]))} for h in spec["host_masks"]},
        "var_run": os.path.realpath(spec["var_run"]) if os.path.lexists(spec["var_run"]) else None,
        "inside": {"reachable": found, "errors": errors, "seconds": round(time.monotonic() - t0, 3)},
        "display_files": {p: reads(p) for p in spec["display_files"]},
        "env_set": [n for n in spec["unset_env"] if n in os.environ],
        "terminal": terminal(),
        "hide_dirs": {p: listing(p) for p in spec["hide_dirs"]},
        "hide_files": {p: reads(p) for p in spec["hide_files"]},
        "hide_runs": {p: listing(p) for p in spec["hide_runs"]},
        "markers_visible": [m for m in spec["markers"] if os.path.lexists(m)],
        "network": network(net, server) if net else None,
        "tools": {"rg": shutil.which("rg", path=spec["path"])},
    }))
"""


@contextlib.contextmanager
def _control() -> Iterator[tuple[str, str]]:
    """``(its path, its directory)``: a listener of the probe's own, bound before the socket table is read. A table
    that does not list it is not this network namespace's (D-CS2-2). In a fresh private directory of the host's /tmp,
    whatever TMPDIR says, which no sandbox sees (its /tmp is its own; as ``bridge.private_address``)."""
    if sys.platform == "win32":
        raise OSError("no Unix socket table on Windows")
    tmp = "/tmp"  # noqa: S108
    directory = tempfile.mkdtemp(prefix="aew-probe-", dir=tmp if os.path.isdir(tmp) else None)
    path = os.path.join(directory, "control")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(path)
        listener.listen(1)
        yield path, directory
    finally:
        listener.close()
        shutil.rmtree(directory, ignore_errors=True)


def _inventory(*, own: tuple[str, ...], env: Mapping[str, str]) -> dict[str, Any]:
    """The host's side of row 2's socket check: :func:`.sockets.inventory`, with the control bound around the read,
    and how long it took; a table that cannot be read is an ``error``."""
    t0 = time.monotonic()
    try:
        with _control() as (control, directory):
            out = sockets.inventory(control=control, own=(*own, directory), env=env)
    except OSError as exc:
        out = {"error": f"the socket table could not be read ({type(exc).__name__}: {exc})"}
    except ValueError as exc:  # a record that does not parse is never dropped (review of #244)
        out = {"error": f"the socket inventory could not parse the kernel's tables ({exc})"}
    return {**out, "seconds": round(time.monotonic() - t0, 3)}


def _candidates(inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What the probe needs of each path socket the host found: where to look (each spelling, and its place in its
    filesystem) and what to match (device and inode)."""
    return [{**{k: c[k] for k in ("path", "dev", "ino", "majmin", "fspath")}, "real": c.get("real")}
            for c in inventory.get("candidates") or []]


def _probe_upstream(listener: socket.socket, token: str, seen: list[str | None]) -> None:
    """Row 1's provider upstream: answers each request with ``token`` and records the credential it carried."""
    while True:
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        with conn:
            try:
                conn.settimeout(TIMEOUT_S)
                buf = b""
                while b"\r\n\r\n" not in buf and len(buf) < 65536:
                    data = conn.recv(4096)
                    if not data:
                        break
                    buf += data
                fields = [line.split(b":", 1) for line in buf.split(b"\r\n\r\n")[0].split(b"\r\n")[1:]]
                seen.append(next((v[1].strip().decode("latin-1") for v in fields
                                  if len(v) == 2 and v[0].strip().lower() == b"authorization"), None))
                body = token.encode()
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                             + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            except OSError:
                continue


def _echo(path: str, deadline: float, out: dict[str, Any], ended: threading.Event) -> None:
    """Row 1's leg in: connect to the shim's socket, as the supervisor does, until the probe echoes a token. The probe
    accepts after its other checks, so a connection the shim made waits in its backlog until then: the wait for the
    echo is the whole deadline. One the shim could not forward yet (no probe listening) ends at once, and is retried;
    the probe passes over such a one, arriving empty. Nothing is retried once the sandbox has ended (``ended``)."""
    token = secrets.token_hex(8).encode()
    out["server"] = "no_answer"
    while not ended.is_set() and time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:  # pyright: ignore[reportAttributeAccessIssue]
                s.settimeout(max(0.1, deadline - time.monotonic()))
                s.connect(path)
                s.sendall(token)
                if s.recv(64) == token:
                    out["server"] = "echoed"
                    return
        except OSError:
            pass
        time.sleep(0.05)


@contextlib.contextmanager
def _network(layout: Layout, *, egress_policy: Any, bridge: str | None) -> Iterator[dict[str, Any] | None]:
    """Row 1's stand-ins, in the run's own network directory, for as long as the probe runs: the probe's relay (its
    upstream a listener of the host's, with a credential of the probe's own) and an egress proxy with the run's
    allowlist, where the run has them; a loopback port and an abstract socket the host holds, which must not be there
    inside. None for a run on the host's network."""
    if not layout.private_network or not layout.net_dir or sys.platform == "win32":
        yield None
        return
    from aew.harness.containment import egress, netns, relay

    directory = layout.net_dir
    with contextlib.ExitStack() as stack:
        state: dict[str, Any] = {"seen": [], "token": secrets.token_hex(16), "relay": False, "egress": False,
                                 "server_socket": os.path.join(directory, PROBE_SERVER)}
        for name in (PROBE_SERVER, PROBE_RELAY, PROBE_EGRESS):
            stack.callback(Path(directory, name).unlink, missing_ok=True)
        sentinel = ""
        if layout.network == PROXY_ONLY:
            upstream = socket.create_server(("127.0.0.1", 0))
            stack.callback(upstream.close)
            threading.Thread(target=_probe_upstream, args=(upstream, state["token"], state["seen"]),
                             name="aew-probe-upstream", daemon=True).start()
            state["secret"], sentinel = secrets.token_hex(16), relay.sentinel()
            target = relay.Upstream(f"http://127.0.0.1:{upstream.getsockname()[1]}/aew-probe")
            probe_relay = relay.ProviderRelay(target, {sentinel: state["secret"]},
                                              listener=netns.listen(os.path.join(directory, PROBE_RELAY))).start()
            stack.callback(probe_relay.close)
            state["relay"] = True
            if egress_policy is not None:
                proxy = egress.EgressProxy(egress_policy,
                                           listener=netns.listen(os.path.join(directory, PROBE_EGRESS))).start()
                stack.callback(proxy.close)
                state["egress"] = True
        held = socket.create_server(("127.0.0.1", 0))
        stack.callback(held.close)
        abstract = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # pyright: ignore[reportAttributeAccessIssue]
        stack.callback(abstract.close)
        state["abstract"] = f"aew-probe-{secrets.token_hex(8)}"
        abstract.bind("\0" + state["abstract"])
        abstract.listen(1)
        state["shim"] = netns.shim_spec(directory, server=PROBE_SERVER,
                                        relay_sock=PROBE_RELAY if state["relay"] else None,
                                        egress_sock=PROBE_EGRESS if state["egress"] else None)
        state["inside"] = {"server_port": netns.SERVER_PORT, "server_wait": SERVER_WAIT_S, "outside": OUTSIDE,
                           "outside6": OUTSIDE6, "host_port": held.getsockname()[1], "host_abstract": state["abstract"],
                           "bridge": bridge, "provider_port": netns.PROVIDER_PORT, "egress_port": netns.EGRESS_PORT,
                           "relay_path": "/aew-probe/check", "sentinel": sentinel, "unlisted": UNLISTED}
        yield state


def self_test(layout: Layout, *, sentinel_dir: Path, sibling_dir: Path, own: tuple[str, ...] = (),
              env: Mapping[str, str] | None = None, egress_policy: Any = None,
              bridge: str | None = None) -> dict[str, Any]:
    """Run the probe in ``layout``. Returns ``{"ok": bool, "reason": str | None, "rows": {...}, "tools": {...}, ...}``;
    never raises for a containment failure (the caller decides by policy). ``tools`` says where, on the launching
    environment's ``PATH``, the sandbox finds each tool a harness needs from the host (``{"rg": path or None}``).
    ``own`` holds the run's own socket directories (its bridge, its network directory); ``env`` is the launching
    environment the socket classes read (default: this process's). For row 1: ``egress_policy`` is the run's egress
    allowlist (None: the run has no egress proxy), and ``bridge`` the run's bridge socket, which must answer inside."""
    with _network(layout, egress_policy=egress_policy, bridge=bridge) as net:
        return _self_test(layout, sentinel_dir=sentinel_dir, sibling_dir=sibling_dir, own=own, env=env, net=net)


def _self_test(layout: Layout, *, sentinel_dir: Path, sibling_dir: Path, own: tuple[str, ...],
               env: Mapping[str, str] | None, net: dict[str, Any] | None) -> dict[str, Any]:
    from aew.harness.containment import netns

    name = f".aew-containment-probe-{secrets.token_hex(8)}"
    sentinel = sentinel_dir / f"{name}.sentinel"
    sibling = sibling_dir / f"{name}.sibling"
    content = secrets.token_hex(16).encode()
    sentinel.write_bytes(content)
    markers = _markers(layout, name)
    extra = [str(m) for m in markers] + [str(Path(v) / ".aew") for v in layout.visible
                                         if (Path(v) / ".aew").is_dir()]
    inventory = _inventory(own=own, env=os.environ if env is None else env)
    spec = {"sentinel": str(sentinel), "sibling": str(sibling), "name": name,
            "writable": list(layout.writable), "protected": [*layout.protected, *extra],
            "candidates": _candidates(inventory),
            "host_masks": list(_host_masks(layout)), "inside_host_masks": list(layout.inside_host_masks()),
            "var_run": VAR_RUN, "display_files": list(layout.display_files), "unset_env": list(DISPLAY_ENV),
            "hide_dirs": list(layout.hide_dirs), "hide_files": list(layout.hide_files),
            "hide_runs": list(layout.hide_runs),
            # the markers a mask hides: a sibling run's, and the temporary directory's when it is /tmp (TMPDIR may
            # name a directory the read-only root shows; the bridge sockets live under /tmp whatever it says)
            "markers": [str(m) for m in markers if any(_within(str(m), h) for h in (SANDBOX_TMP, *layout.hide_runs))],
            "network": net["inside"] if net else None,
            # the PATH a run's harness gets (the launching environment's), on which the probe looks for the tools a
            # harness needs from the host: ripgrep, which OpenCode otherwise downloads (the designer's RG-1)
            "path": (os.environ if env is None else env).get("PATH", "")}
    result: dict[str, Any] = {"ok": False, "reason": None, "probe": name}
    argv = [sys.executable, "-I", "-c", _PAYLOAD]
    echo: threading.Thread | None = None
    probed = threading.Event()  # the sandbox has ended: the echo has its answer, or never will
    if net:  # under the run's shim, in the one sandbox, as the harness runs (F28 §3.2)
        argv = netns.shim_argv(net["shim"], argv)
        echo = threading.Thread(target=_echo, args=(net["server_socket"], time.monotonic() + TIMEOUT_S, net, probed),
                                name="aew-probe-echo", daemon=True)
        echo.start()
    try:
        try:  # the spec on stdin: one argument is capped at 128 KiB (MAX_ARG_STRLEN), and it grows with the sockets
            done = subprocess.run(bwrap_argv(layout, argv), input=json.dumps(spec),
                                  capture_output=True, text=True, timeout=TIMEOUT_S,
                                  env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
                                       **dict.fromkeys(DISPLAY_ENV, CANARY)})
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["reason"] = f"the sandbox could not run: {type(exc).__name__}: {exc}"
            return result
        finally:
            probed.set()
            if echo is not None:
                echo.join(ECHO_JOIN_S)
        if done.returncode != 0:
            err = (done.stderr or "").strip().splitlines()
            last = err[-1] if err else "no output"
            result["reason"] = f"the sandbox could not start (exit {done.returncode}): {last}"
            return result
        try:
            seen = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result["reason"] = "the probe reported nothing readable"
            return result
        rows = _rows(layout, {**seen, "inventory": inventory}, written=(sentinel, content), sibling=sibling,
                     name=name, net=net)
        problems = [f"row {n} ({row['name']}): {row['reason']}" for n, row in rows.items() if not row["ok"]]
        result.update(ok=not problems, reason="; ".join(problems) or None, probe_pid=seen.get("pid"), rows=rows,
                      tools=seen.get("tools") or {})
        return result
    finally:
        for m in markers:
            m.unlink(missing_ok=True)
            if m.parent.name.endswith(".probe-run"):
                m.parent.rmdir()
        sentinel.unlink(missing_ok=True)
        if sibling.exists():
            sibling.unlink()
        for root in layout.writable:
            (Path(root) / name).unlink(missing_ok=True)


def _rows(layout: Layout, seen: dict[str, Any], *, written: tuple[Path, bytes], sibling: Path,
          name: str, net: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """CB-12's rows 1 to 5, judged on the host from what the probe saw. Each row says what it checked."""
    return {"1": _row1(layout, seen, net), "2": _row2(layout, seen, net), "3": _row3(seen), "4": _row4(seen),
            "5": _row5(layout, seen, written=written, sibling=sibling, name=name)}


def _row(name: str, problems: list[str], **facts: Any) -> dict[str, Any]:
    return {"name": name, "ok": not problems, "reason": "; ".join(problems) or None, **facts}


def _netns(pid: str = "self") -> str | None:
    """A process's network namespace, as ``/proc`` names it (``net:[<inode>]``), or None where it cannot be read
    (another user's process, PID 1 among them, for an unprivileged launcher)."""
    try:
        return os.readlink(f"/proc/{pid}/ns/net")
    except OSError:
        return None


def _row1(layout: Layout, seen: dict[str, Any], net: dict[str, Any] | None) -> dict[str, Any]:
    """F28 §3.6 and the hand-off's outcome 4, in a network of its own (see the module docstring). On the host's
    network the row records the mode and claims nothing (F28 §3.1: ``shared`` is topology, not containment)."""
    if not layout.private_network:
        return _row("network", [], mode=layout.network, claim="none: the run shares the host's network")
    inside = seen.get("network") or {}
    if net is None or not inside:
        return _row("network", ["the probe did not report its network"], mode=layout.network)
    from aew.harness.containment import netns

    problems = []
    launcher, init = _netns(), _netns("1")
    if not inside.get("netns") or inside["netns"] in (launcher, init):
        problems.append(f"the sandbox's network namespace ({inside.get('netns')}) is the host's")
    for key, what, also in (("direct", "TCP", ()), ("direct_udp", "UDP", ()),
                            ("direct6", "IPv6 TCP", ("EAFNOSUPPORT", "EADDRNOTAVAIL"))):
        if inside.get(key) not in (*UNREACHABLE, *also):
            problems.append(f"a direct {what} connection out of the sandbox did not fail for want of a route "
                            f"({inside.get(key)})")
    if inside.get("host_port") == "connected":
        problems.append("a loopback port the host holds is reachable inside")
    if inside.get("host_abstract") == "connected" or f"@{net['abstract']}" in (inside.get("abstract") or []):
        problems.append("an abstract socket the host holds is reachable inside")
    allowed = {netns.SERVER_PORT, *([netns.PROVIDER_PORT] if net["relay"] else []),
               *([netns.EGRESS_PORT] if net["egress"] else [])}
    extra = [p for p in inside.get("listening") or [] if p[0] not in ("tcp", "tcp6") or p[1] not in allowed]
    if extra:
        problems.append(f"ports listen inside beyond the shim's: {extra}")
    if net.get("server") != "echoed":
        problems.append(f"the supervisor could not reach the sandbox's loopback through the shim ({net.get('server')}; "
                        f"inside: {inside.get('server')})")
    relayed = inside.get("relay") or {}
    if net["relay"]:
        if relayed.get("status", "").split(" ")[1:2] != ["200"] or relayed.get("body") != net["token"]:
            problems.append(f"a request through the provider relay did not reach its upstream ({relayed})")
        elif net["seen"] != [f"Bearer {net['secret']}"]:
            problems.append("the provider relay did not put the credential in place of its sentinel")
    elif "status" in relayed:
        problems.append("a provider route answers inside a network with none")
    refused = inside.get("egress") or {}
    if net["egress"] and refused.get("status", "").split(" ")[1:2] != ["403"]:
        problems.append(f"the egress proxy did not refuse {UNLISTED}, which is on no allowlist ({refused})")
    elif not net["egress"] and "status" in refused:
        problems.append("an egress route answers inside a run that has none")
    if net["inside"].get("bridge") and inside.get("bridge") != "connected":
        problems.append(f"the bridge does not answer inside by its path ({inside.get('bridge')})")
    return _row("network", problems, mode=layout.network, netns={"inside": inside.get("netns"), "launcher": launcher},
                provider_relay="probe upstream" if net["relay"] else "none", egress=net["egress"],
                checks={k: inside.get(k) for k in ("direct", "direct_udp", "direct6", "host_port", "host_abstract",
                                                   "bridge", "server")},
                listening=inside.get("listening") or [], server=net.get("server"))


def _host_masks(layout: Layout) -> tuple[str, ...]:
    """The trees row 2 finds masked: the host's runtime trees as they are now (``layout.host_masks``), whatever the
    layout says, and the layout's own: a layout that lost its ``/run`` mask fails the row instead of passing it."""
    return tuple(dict.fromkeys((*host_masks(), *layout.hide_host)))


def _row2(layout: Layout, seen: dict[str, Any], net: dict[str, Any] | None = None) -> dict[str, Any]:
    """``/run`` masked, and the socket inventory (D-CS2-2): fails closed on a table that cannot be read or does not
    list the control, and on a check inside that errors; a reachable path socket of a failing class fails it. An
    abstract socket the host holds fails it when it is listed inside a network of the run's own, and is a fact, with
    its class, on the host's network (D-CS2-5); what the inventory cannot see is named (D-CS2-3)."""
    problems = []
    masks = seen.get("host_masks") or {}
    for h in _host_masks(layout):
        mask = masks.get(h) or {}
        if mask.get("type") != "tmpfs" or not mask.get("readonly"):
            problems.append(f"{h} is not a read-only tmpfs inside (it is {mask.get('type')}, "
                            f"{'read-only' if mask.get('readonly') else 'writable'})")
        if mask.get("extra"):
            problems.append(f"{h} holds what the layout did not put there: {', '.join(mask['extra'][:5])}")
    var_run = seen.get("var_run")
    if var_run is not None and not any(_within(var_run, h) for h in _host_masks(layout)):
        problems.append(f"{VAR_RUN} leads to {var_run}, outside the masked {', '.join(_host_masks(layout))}")
    inventory, inside = seen.get("inventory") or {}, seen.get("inside") or {}
    if inventory.get("error"):
        problems.append(inventory["error"])
    elif not inventory.get("control"):
        problems.append("the socket table does not list the probe's own listener, so it is not this network "
                        "namespace's")
    problems += [f"the socket inventory could not check {e['path']} inside ({e['error']})"
                 for e in inside.get("errors") or []]
    classes = {c["path"]: c for c in inventory.get("candidates") or []}
    found = [{"path": r["path"], "class": classes[r["path"]]["class"], "inside": r["inside"],
              **({"listed": classes[r["path"]]["listed"]} if classes[r["path"]]["listed"] != r["path"] else {}),
              **({"holder": classes[r["path"]]["holder"]} if classes[r["path"]].get("holder") else {})}
             for r in inside.get("reachable") or [] if r["path"] in classes]
    problems += [f"a {s['class']} socket is reachable: {s['path']}"
                 + (f" (inside at {', '.join(s['inside'])})" if s["inside"] != [s["path"]] else "")
                 + (UNIDENTIFIED_REMEDY if s.get("holder") == sockets.UNIDENTIFIED else "")
                 for s in found if s["class"] in sockets.FAILING]
    # checked at their own paths only: no mount of their filesystem above them on the host (review of #244)
    untranslated = [{"path": c["path"], "class": c["class"]} for c in classes.values()
                    if c.get("fspath") is None and (c.get("real") or {}).get("fspath") is None]
    planted = f"@{net['abstract']}" if net and net.get("abstract") else None  # row 1's own, held for the probe
    held = [s for s in inventory.get("abstract") or [] if s["name"] != planted]
    abstract: dict[str, Any] = {"network": layout.network, "sockets": held}
    if layout.private_network:  # D-CS2-5: the host's abstract sockets are not in a network of the run's own
        listed = (seen.get("network") or {}).get("abstract")
        if listed is None:
            problems.append("the probe did not list the abstract sockets inside its network")
        abstract["visible_inside"] = [s for s in held if s["name"] in set(listed or [])]
        problems += [f"an abstract {s['class']} socket the host holds is listed inside: {s['name']}"
                     for s in abstract["visible_inside"]]
    return _row("run_and_sockets", problems, host_masks=masks, sockets=found, table=inventory.get("table"),
                checked=len(classes), abstract=abstract,
                unresolved=inventory.get("unresolved") or [], relative=inventory.get("relative") or [],
                unchecked=inventory.get("unchecked") or [], untranslated=untranslated,
                unreadable_processes=inventory.get("unreadable") or [],
                not_covered=list(sockets.NOT_COVERED),
                seconds={"host": inventory.get("seconds"), "inside": inside.get("seconds")})


def _row3(seen: dict[str, Any]) -> dict[str, Any]:
    files = seen.get("display_files") or {}
    readable = [p for p, state in files.items() if state not in ("absent", "empty", "unreadable")]
    problems = [f"display credential {p} is readable from inside" for p in readable]
    problems += [f"{n} reaches a contained process" for n in seen.get("env_set") or []]
    return _row("display", problems, files=files, env_set=seen.get("env_set") or [])


def _row4(seen: dict[str, Any]) -> dict[str, Any]:
    """No controlling terminal, read on the started process itself: ``tty_nr`` 0 in its own ``/proc/self/stat`` and
    ``ENXIO`` from ``/dev/tty``. Whether it leads its session is a fact on the label, not a condition: under
    bubblewrap's ``--new-session`` the session's leader is bubblewrap's own process in the sandbox (seen on CI)."""
    term = seen.get("terminal") or {}
    problems = []
    if term.get("tty_nr") != 0 or term.get("dev_tty") != errno.errorcode[errno.ENXIO]:
        problems.append(f"the process has a controlling terminal (tty_nr {term.get('tty_nr')}, /dev/tty "
                        f"{term.get('dev_tty')})")
    return _row("terminal", problems, **term)


def _row5(layout: Layout, seen: dict[str, Any], *, written: tuple[Path, bytes], sibling: Path,
          name: str) -> dict[str, Any]:
    problems = []
    sentinel, content = written
    if sentinel.read_bytes() != content or seen.get("sentinel_written"):
        problems.append(f"a file outside the writable roots was modified ({sentinel})")
    if sibling.exists():
        problems.append(f"a new file was created outside the writable roots ({sibling})")
    for root, created in (seen.get("writable") or {}).items():
        if not created or not (Path(root) / name).exists():
            problems.append(f"writable root {root} is not writable on the host from inside")
    for path in seen.get("protected_writable") or []:
        problems.append(f"protected path {path} is writable from inside")
    for path, entries in (seen.get("hide_dirs") or {}).items():
        if entries:  # None: absent, hidden with a masked tree
            problems.append(f"masked directory {path} is not empty inside")
    for path, state in (seen.get("hide_files") or {}).items():
        if state not in ("absent", "empty"):
            problems.append(f"masked file {path} is {state} inside")
    for path, entries in (seen.get("hide_runs") or {}).items():
        own = {os.path.relpath(p, path).split(os.sep)[0] for p in (*layout.writable, *layout.readonly)
               if _within(p, path) and p != path}
        if entries is None:
            problems.append(f"the runs mask {path} is missing inside")
        elif set(entries) - own:
            problems.append(f"the runs mask {path} shows {sorted(set(entries) - own)} beyond this run's own "
                            "directories")
    problems += [f"{m} is visible from inside" for m in seen.get("markers_visible") or []]
    return _row("binds_and_masks", problems)


def _markers(layout: Layout, name: str) -> list[Path]:
    """Files the probe must not be able to write: one in the host's temporary directory, one in a sibling run."""
    import tempfile

    out = [Path(tempfile.gettempdir()) / f"{name}.tmp-marker"]
    for runs in layout.hide_runs:
        sibling = Path(runs) / f"{name}.probe-run"
        sibling.mkdir()
        out.append(sibling / "marker")
    for m in out:
        m.write_bytes(b"")
    return out


def mechanism(layout: Layout) -> str:
    """``bubblewrap <version>`` of the binary the layout uses."""
    try:
        out = subprocess.run([layout.bwrap, "--version"], capture_output=True, text=True, timeout=VERSION_TIMEOUT_S,
                             stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return out or "bubblewrap"
