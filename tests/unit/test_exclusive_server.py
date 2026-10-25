"""Every listener in ``src`` holds its port alone (``aew.exclusive_server``; register E75).

The enumeration is mechanical. Every class in ``src`` that derives from a ``socketserver`` server, and every site that
binds or listens (``.bind(``, ``create_server(``, ``multiprocessing``'s ``Listener(`` and a stdlib server called
directly), is found in the code and in its string constants: the probe's sandboxed payload is one. A server class
must be :class:`~aew.exclusive_server.ExclusiveServer` or derive from it; every other site is in :data:`SITES` with
the reason it cannot share a port. A new site fails until it is classified there, and a row whose site has gone fails
too. The behaviour is then shown on each platform: a second bind on a held port is refused.
"""

from __future__ import annotations

import ast
import re
import socket
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from aew.dashboard.server import _Listener
from aew.exclusive_server import ExclusiveServer

ROOT = Path(__file__).resolve().parents[2]
STDLIB_SERVERS = frozenset({
    "BaseServer", "TCPServer", "UDPServer", "UnixStreamServer", "UnixDatagramServer", "ThreadingTCPServer",
    "ThreadingUDPServer", "ForkingTCPServer", "ForkingUDPServer", "ThreadingUnixStreamServer",
    "ThreadingUnixDatagramServer", "HTTPServer", "ThreadingHTTPServer"})
LISTENING_CALLS = frozenset({"bind", "create_server", "Listener"}) | STDLIB_SERVERS
IN_A_STRING = re.compile(r"(?:\.(bind)|\b(create_server|Listener))\(")
PIPE_OR_UNIX = ("a Unix socket, or on Windows a named pipe (bridge.private_address); a second listener on either is "
                "refused (multiprocessing creates a pipe's first instance with FILE_FLAG_FIRST_PIPE_INSTANCE)")
# (file, enclosing scope, call): how many sites, and why none can share a TCP port with another listener
SITES: dict[tuple[str, str, str], tuple[int, str]] = {
    ("src/aew/dashboard/control.py", "ControlServer.__init__", "Listener"): (1, PIPE_OR_UNIX),
    ("src/aew/harness/bridge.py", "BridgeServer.__init__", "Listener"): (1, PIPE_OR_UNIX),
    ("src/aew/harness/operator_endpoint.py", "OperatorEndpoint.start", "Listener"): (1, PIPE_OR_UNIX),
    ("src/aew/harness/containment/netns.py", "listen", "bind"): (1, "a Unix socket file"),
    ("src/aew/harness/containment/peer.py", "_binds", "bind"): (
        1, "port 0 and never listened on: it asks the kernel whether an address is this host's"),
    ("src/aew/harness/containment/probe.py", "_control", "bind"): (1, "a Unix socket file; Linux only"),
    ("src/aew/harness/containment/probe.py", "_network", "bind"): (1, "an abstract Unix socket; Linux only"),
    ("src/aew/harness/containment/probe.py", "_network", "create_server"): (
        2, "Linux only: _network yields None on win32, and Linux refuses a second listener on a held port"),
    ("src/aew/harness/containment/probe.py", "<module>", "create_server in a string"): (
        1, "the probe's payload, which runs in the Linux sandbox's own network namespace"),
    ("src/aew/harness/containment/shim.py", "listen", "bind"): (1, "a Unix socket file, in the Linux sandbox"),
    ("src/aew/harness/containment/shim.py", "listen", "create_server"): (
        1, "in the Linux sandbox's own network namespace"),
}


def _name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def scan(label: str, source: str) -> tuple[Counter[tuple[str, str, str]], dict[str, list[str]]]:
    """``label``'s listening sites, counted by (file, enclosing scope, call), and its classes by their base names."""
    sites: Counter[tuple[str, str, str]] = Counter()
    classes: dict[str, list[str]] = {}

    def visit(node: ast.AST, scope: list[str]) -> None:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = [b for b in map(_name, node.bases) if b]
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = [*scope, node.name]
        where = ".".join(scope) or "<module>"
        if isinstance(node, ast.Call) and _name(node.func) in LISTENING_CALLS:
            sites[(label, where, _name(node.func) or "")] += 1
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for found in IN_A_STRING.finditer(node.value):
                sites[(label, where, f"{found.group(1) or found.group(2)} in a string")] += 1
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(ast.parse(source), [])
    return sites, classes


def unshared(classes: dict[str, list[str]]) -> list[str]:
    """The server classes that do not derive from ExclusiveServer, through any chain of classes in ``classes``."""
    def exclusive(name: str, seen: frozenset[str] = frozenset()) -> bool:
        return name == "ExclusiveServer" or any(exclusive(b, seen | {name}) for b in classes.get(name, [])
                                                if b not in seen)

    def server(name: str, seen: frozenset[str] = frozenset()) -> bool:
        return any(b in STDLIB_SERVERS or (b not in seen and server(b, seen | {name})) for b in classes.get(name, []))

    return sorted(n for n in classes if n != "ExclusiveServer" and server(n) and not exclusive(n))


def problems(sources: dict[str, str], table: dict[tuple[str, str, str], tuple[int, str]]) -> list[str]:
    found: Counter[tuple[str, str, str]] = Counter()
    classes: dict[str, list[str]] = {}
    for label, source in sources.items():
        sites, named = scan(label, source)
        found += sites
        classes |= named
    out = [f"{name} is a server that does not derive from ExclusiveServer" for name in unshared(classes)]
    out += [f"{site}: {n} listening site(s), not classified in SITES" for site, n in sorted(found.items())
            if table.get(site, (0, ""))[0] != n and site[2] not in STDLIB_SERVERS]
    out += [f"{site}: calls a stdlib server directly, not ExclusiveServer" for site in sorted(found)
            if site[2] in STDLIB_SERVERS]
    out += [f"{site}: in SITES, but no such site is left" for site in sorted(table) if site not in found]
    return out


def test_every_listener_in_src_is_exclusive_or_classified_with_why_it_cannot_share_a_port():
    sources = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
               for p in sorted((ROOT / "src").rglob("*.py"))}
    assert problems(sources, SITES) == []


SYNTHETIC = '''
from http.server import ThreadingHTTPServer
from aew.exclusive_server import ExclusiveServer
class Good(ExclusiveServer):
    pass
class AlsoGood(Good):
    pass
PAYLOAD = "s = socket.create_server(('127.0.0.1', 1))"
def serve(path):
    sock.bind(path)
'''
CLASSIFIED = {("m.py", "<module>", "create_server in a string"): (1, "planted"), ("m.py", "serve", "bind"): (1, "x")}


@pytest.mark.parametrize(("source", "table", "says"), [
    (SYNTHETIC, CLASSIFIED, []),  # right: servers that derive from the rule, and classified sites
    (SYNTHETIC + "class Shared(ThreadingHTTPServer):\n    pass\n", CLASSIFIED,
     ["Shared is a server that does not derive from ExclusiveServer"]),
    (SYNTHETIC + "class Deeper(AlsoGood):\n    pass\nclass Mixed(Deeper, ThreadingHTTPServer):\n    pass\n",
     CLASSIFIED, []),  # a chain that reaches the rule is enough
    (SYNTHETIC + "srv = ThreadingHTTPServer(('127.0.0.1', 0), H)\n", CLASSIFIED,
     ["('m.py', '<module>', 'ThreadingHTTPServer'): calls a stdlib server directly, not ExclusiveServer"]),
    (SYNTHETIC + "def other():\n    s.bind(('127.0.0.1', 0))\n", CLASSIFIED,
     ["('m.py', 'other', 'bind'): 1 listening site(s), not classified in SITES"]),
    (SYNTHETIC + "def serve2(path):\n    sock = Listener(path)\n", CLASSIFIED,
     ["('m.py', 'serve2', 'Listener'): 1 listening site(s), not classified in SITES"]),
    (SYNTHETIC.replace("PAYLOAD = ", "PAYLOAD = 'x'; OLD = "), CLASSIFIED, []),  # still one string site at module level
    (SYNTHETIC.replace("    sock.bind(path)\n", "    pass\n"), CLASSIFIED,
     ["('m.py', 'serve', 'bind'): in SITES, but no such site is left"]),  # missing: a stale row
    (SYNTHETIC + "def serve(path):\n    other.bind(path)\n", CLASSIFIED,
     ["('m.py', 'serve', 'bind'): 2 listening site(s), not classified in SITES"]),  # one more in a classified scope
], ids=["right", "wrong_server", "chain", "direct_stdlib", "new_bind", "new_listener", "string", "stale", "count"])
def test_the_enumeration_finds_each_kind_of_site_and_each_unclassified_or_stale_one(source, table, says):
    assert problems({"m.py": source}, table) == says


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 (stdlib signature)
        pass


def explicit_bind(port: int, *, reuse: bool) -> None:
    """A plain socket's bind and listen on ``port``, with ``SO_REUSEADDR`` when ``reuse`` (http.server's default)."""
    with socket.socket() as s:
        if reuse:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen(1)


@pytest.mark.parametrize("make", [
    lambda address: ExclusiveServer(address, Quiet),
    lambda address: _Listener(address, Quiet, b""),  # the dashboard's
], ids=["exclusive_server", "dashboard_listener"])
def test_a_port_an_aew_server_holds_is_refused_to_any_second_listener(make):
    """Windows let a second ``SO_REUSEADDR`` listener share a port the dashboard held (register E75); Linux never did.
    Here neither does: not a plain socket with or without the option, and not a second server of the same kind."""
    held = make(("127.0.0.1", 0))
    try:
        port = held.server_address[1]
        for reuse in (True, False):
            with pytest.raises(OSError):
                explicit_bind(port, reuse=reuse)
        with pytest.raises(OSError):
            make(("127.0.0.1", port))
    finally:
        held.server_close()


def test_create_server_sets_no_address_reuse_on_windows_so_its_port_is_refused_to_a_second_listener():
    """Shown rather than assumed: ``socket.create_server`` sets ``SO_REUSEADDR`` only off Windows, so the probe's and
    the shim's listeners (:data:`SITES`) cannot share a port there either, and a second listener on one is refused on
    every platform."""
    with socket.create_server(("127.0.0.1", 0)) as held:
        if sys.platform == "win32":
            assert held.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        for reuse in (True, False):
            with pytest.raises(OSError):
                explicit_bind(held.getsockname()[1], reuse=reuse)
