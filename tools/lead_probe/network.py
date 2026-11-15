"""Fail-closed network proof for the scripted probe."""

from __future__ import annotations

import errno
import socket
from pathlib import Path

NAMES = ("api.openai.com", "chatgpt.com", "opencode.ai")
ADDRESSES = ("8.8.8.8", "1.1.1.1", "192.0.2.1")
NO_ROUTE = {errno.ENETUNREACH, errno.EHOSTUNREACH}


def default_routes() -> list[str]:
    v4 = Path("/proc/net/route").read_text(encoding="ascii").splitlines()[1:]
    v6 = Path("/proc/net/ipv6_route")
    # Linux includes a reject sentinel in the IPv6 table even in an empty namespace.
    ipv6 = v6.read_text(encoding="ascii").splitlines() if v6.exists() else []
    return [
        *(line for line in v4 if line.split()[1] == "00000000" and line.split()[7] == "00000000"),
        *(line for line in ipv6 if line.split()[:2] == ["0" * 32, "00"]
          and not int(line.split()[8], 16) & 0x200),
    ]


def prove() -> dict:
    interfaces = sorted(name for _, name in socket.if_nameindex())
    if interfaces != ["lo"] or default_routes():
        raise ValueError("expected only loopback and no default route")
    blocked = {}
    for host in (*NAMES, *ADDRESSES):
        try:
            with socket.create_connection((host, 443), timeout=2):
                raise ValueError(f"unexpected connection to {host}:443")
        except socket.gaierror as exc:
            if host not in NAMES or exc.errno not in {socket.EAI_AGAIN, socket.EAI_NONAME, socket.EAI_FAIL}:
                raise ValueError(f"unproved network isolation for {host}") from exc
            blocked[host] = "resolution failed"
        except OSError as exc:
            if exc.errno not in NO_ROUTE:
                raise ValueError(f"unproved network isolation for {host}: {exc}") from exc
            blocked[host] = errno.errorcode[exc.errno]
    return {"interfaces": interfaces, "default_routes": [], "unreachable": blocked}
