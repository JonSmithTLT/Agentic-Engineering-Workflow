"""R-6's host-local check on a real kernel (STG-05 CS-3a; ruling R-6; F28 §3.4).

An address the kernel delivers to this host is refused, whatever route makes it local. Each case makes addresses local
one way, in its own fresh user and network namespace (``unshare -rn``: no privilege on the host, and nothing in it is
reachable from anywhere else), checks that the kernel lists what it planted, and asks :func:`peer.host_route` there
about each address. Nothing connects anywhere. Every case has a neighbouring address that is not local, which must
not be refused. The addresses are documentation and reserved ones.

Linux only: Windows has no network namespaces (pinned in ``tests/platform-skips.yaml``). The dump's parser is tested
on every platform in ``tests/unit/test_egress_peer.py``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aew.harness.containment import peer

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="network namespaces are Linux's")

SRC = Path(peer.__file__).resolve().parents[3]  # this checkout's src, whatever checkout the venv's aew is from
TIMEOUT = 60
# The kernel adds an address's own routes (its local and anycast ones) from deferred work, even with nodad, so a
# case waits for them. The test's choice: far beyond the milliseconds they take under load.
LISTED_WITHIN = 10

# Runs as root of its own user and network namespace: brings loopback up, plants the case, waits until the kernel
# lists the planted route (at most LISTED_WITHIN seconds), then prints host_route for each address as JSON. With
# "unreadable", it asks again with the tables read by a reader that fails, and by one that stops before the kernel's
# end marker.
CHILD = """
import contextlib, functools, json, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
from aew.harness.containment import peer

case = json.loads(sys.argv[2])
for command in [["link", "set", "lo", "up"], *case["plant"]]:
    if command[0] == "write":
        with open(command[1], "w") as sysctl:
            sysctl.write(command[2])
    else:
        subprocess.run(["ip", *command], check=True, timeout=10, capture_output=True)
deadline = time.monotonic() + float(sys.argv[3])
while True:
    listing = subprocess.run(["ip", *case["listing"]], check=True, timeout=10, capture_output=True, text=True).stdout
    if case["listed"] in listing:
        break
    if time.monotonic() > deadline:
        sys.exit("the kernel does not list the planted route: " + listing)
    time.sleep(0.05)
result = {"readable": {value: peer.host_route(value) for value in case["addresses"]}}

def fails(family):
    raise PermissionError(13, "synthetic: the tables cannot be read")
    yield b""

def cut(family):
    with contextlib.closing(peer._route_dump(family)) as datagrams:
        for data in datagrams:
            offset = 0
            while offset < len(data):
                length, kind = peer._NLMSG.unpack_from(data, offset)[:2]
                if kind == peer._NLMSG_DONE:
                    yield data[:offset]
                    return
                offset += (length + 3) & ~3
            yield data

if case.get("unreadable"):
    real = peer.local_routes
    for name, reader in (("fails", fails), ("cut", cut)):
        peer.local_routes = functools.partial(real, read=reader)
        result[name] = {value: peer.host_route(value) for value in case["addresses"]}
print(json.dumps(result))
"""

V6_LOCAL = ["-6", "route", "show", "table", "all", "type", "local"]
V4_LOCAL = ["-4", "route", "show", "table", "all", "type", "local"]
CASES = {
    "an address on an interface": {
        "plant": [["-6", "addr", "add", "3ffe:2::1/64", "dev", "lo", "nodad"]],
        "listing": V6_LOCAL, "listed": "local 3ffe:2::1 dev lo",
        "addresses": {"3ffe:2::1": "host_interface", "3ffe:2::2": None},
    },
    "an IPv6 local route": {
        "plant": [["-6", "route", "add", "local", "3ffe:1::/64", "dev", "lo"]],
        "listing": V6_LOCAL, "listed": "local 3ffe:1::/64 dev lo table local",
        "addresses": {"3ffe:1::5": "host_interface", "3ffe:1:0:1::5": None},
    },
    "an IPv6 local route in a table a rule reaches": {
        "plant": [["-6", "rule", "add", "to", "3ffe:3::/64", "table", "100"],
                  ["-6", "route", "add", "local", "3ffe:3::/64", "dev", "lo", "table", "100"]],
        "listing": V6_LOCAL, "listed": "local 3ffe:3::/64 dev lo table 100",
        "addresses": {"3ffe:3::5": "host_interface", "3ffe:3:0:1::5": None},
    },
    "an IPv4 local route": {
        "plant": [["-4", "route", "add", "local", "198.51.100.0/25", "dev", "lo"]],
        "listing": V4_LOCAL, "listed": "local 198.51.100.0/25 dev lo table local",
        "addresses": {"198.51.100.5": "host_interface", "::ffff:198.51.100.5": "host_interface",
                      "198.51.100.200": None},
    },
    "an IPv4 local route in a table a rule reaches": {
        "plant": [["-4", "rule", "add", "to", "203.0.113.0/25", "table", "100"],
                  ["-4", "route", "add", "local", "203.0.113.0/25", "dev", "lo", "table", "100"]],
        "listing": V4_LOCAL, "listed": "local 203.0.113.0/25 dev lo table 100",
        "addresses": {"203.0.113.5": "host_interface", "203.0.113.200": None},
    },
    # The subnet-router anycast address of a forwarding host's prefix, and the prefix's own address: both are this
    # host's.
    "an IPv6 anycast address": {
        "plant": [["write", "/proc/sys/net/ipv6/conf/all/forwarding", "1"],
                  ["-6", "addr", "add", "3ffe:4::1/64", "dev", "lo", "nodad"]],
        "listing": ["-6", "route", "show", "table", "local", "type", "anycast"], "listed": "anycast 3ffe:4:: dev lo",
        "addresses": {"3ffe:4::": "host_interface", "3ffe:4::1": "host_interface", "3ffe:4::2": None},
    },
    "tables that cannot be read": {
        "plant": [["-6", "route", "add", "local", "3ffe:1::/64", "dev", "lo"]],
        "listing": V6_LOCAL, "listed": "local 3ffe:1::/64 dev lo table local",
        "addresses": {"3ffe:9::5": None, "198.51.100.200": None},
        "unreadable": True,
    },
}


def _namespaces() -> str | None:
    """Why unprivileged user and network namespaces cannot be made here, or None."""
    for tool in ("unshare", "ip"):
        if shutil.which(tool) is None:
            return f"{tool} is not installed"
    made = subprocess.run(["unshare", "-rn", "true"], capture_output=True, text=True, timeout=TIMEOUT, check=False)
    if made.returncode:
        return f"unshare -rn failed: {made.stderr.strip()}"
    return None


def test_an_address_the_kernel_delivers_to_this_host_is_refused_whatever_route_makes_it_local():
    unavailable = _namespaces()
    if unavailable:
        pytest.skip(f"unprivileged user and network namespaces are not available: {unavailable}")
    results = {}
    for name, case in CASES.items():
        run = subprocess.run(["unshare", "-rn", sys.executable, "-I", "-c", CHILD, str(SRC), json.dumps(case),
                              str(LISTED_WITHIN)], capture_output=True, text=True, timeout=TIMEOUT, check=False)
        assert run.returncode == 0, f"{name}: {run.stderr.strip()}"
        results[name] = json.loads(run.stdout)
    for name, case in CASES.items():
        assert results[name]["readable"] == case["addresses"], name
    unreadable = results["tables that cannot be read"]
    assert unreadable["fails"] == unreadable["cut"] == {"3ffe:9::5": "host_interface",
                                                        "198.51.100.200": "host_interface"}
