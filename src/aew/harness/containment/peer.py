"""What the egress proxy may connect to, judged by the peer address (STG-05 CS-3a; ruling R-6; F28 §3.4).

The proxy runs in the host's network namespace, so every address it connects to is a host route. **R-6:** it never
connects to a loopback, link-local or host-local address, even one its allowlist lists. :func:`host_route` is that
rule's one owner. It is called on resolved addresses, before the connect and again on the connected socket's peer
address, never on a name: a name raises.

- **Host-local** is "this host" (``0.0.0.0/8`` and ``::``, which a Linux connect delivers to loopback) and every
  address in the kernel's local table (:func:`is_host_address`), not a list of interfaces: the kernel decides what it
  delivers locally, AnyIP routes included.
- **IPv6 forms of an IPv4 address** are judged by the IPv4 address too: IPv4-mapped (``::ffff:0:0/96``, which a
  dual-stack socket connects to over IPv4), IPv4-compatible (``::/96``, deprecated) and NAT64's well-known prefix
  (``64:ff9b::/96``). Zone ids are dropped (``fe80::1%eth0``).
- **The credentialing relay is not judged here.** Its upstream is fixed by the execution profile and the model cannot
  redirect it (F28 §3.3), so a host-local upstream such as F18.8's gateway is allowed. The exemption is structural:
  only the egress proxy calls this module, and nothing here takes an exemption.

:func:`not_public` is the any-public-address policy's test (the operator, 2026-10-21, decision 3; CS-4 selects it for
the Lead): "public" is globally reachable, the designer's reading. Private, shared and the other special-purpose
ranges are not public, as well as what R-6 refuses.

The ranges are this module's own tables, from IANA's IPv4 and IPv6 Special-Purpose Address Registries (both last
updated 2025-10-09), not ``ipaddress``'s ``is_loopback``, ``is_private`` and ``is_global``: their answers differ by
interpreter (``::ffff:127.0.0.1`` is loopback on 3.13 and not on 3.11, and AEW supports 3.11), and a refusal must not.
Two blocks are refused whole although a few addresses in them are globally reachable anycast services
(``192.0.0.0/24`` and ``2001::/23``): stricter, and none of them is an egress destination. ``2002::/16`` (6to4),
whose reachability IANA gives as not applicable, is refused too.
"""

from __future__ import annotations

import errno
import ipaddress
import socket
from collections.abc import Callable
from typing import Any

IP = ipaddress.IPv4Address | ipaddress.IPv6Address

# R-6's ranges: (block, reason). Nothing in them is ever connected to.
_IPV4_HOST_ROUTE = (
    ("0.0.0.0/8", "this_host"),        # RFC 791 §3.2, RFC 1122 §3.2.1.3: a Linux connect reaches loopback
    ("127.0.0.0/8", "loopback"),       # RFC 1122 §3.2.1.3
    ("169.254.0.0/16", "link_local"),  # RFC 3927, the cloud metadata address 169.254.169.254 among them
)
_IPV6_HOST_ROUTE = (
    ("::/128", "this_host"),   # RFC 4291: the unspecified address
    ("::1/128", "loopback"),   # RFC 4291
    ("fe80::/10", "link_local"),  # RFC 4291
)
# Not globally reachable, beyond R-6's ranges: (block, reason). IPv4 is a list of exceptions; IPv6 is public only
# inside global unicast (2000::/3, RFC 4291) and outside these.
_IPV4_NOT_PUBLIC = (
    ("10.0.0.0/8", "private"),              # RFC 1918
    ("100.64.0.0/10", "shared"),            # RFC 6598
    ("172.16.0.0/12", "private"),           # RFC 1918
    ("192.0.0.0/24", "ietf_protocol"),      # RFC 6890 §2.1, whole (see the docstring)
    ("192.0.2.0/24", "documentation"),      # RFC 5737
    ("192.88.99.0/24", "deprecated_relay"),  # RFC 7526: 6to4 relay anycast
    ("192.168.0.0/16", "private"),          # RFC 1918
    ("198.18.0.0/15", "benchmarking"),      # RFC 2544
    ("198.51.100.0/24", "documentation"),   # RFC 5737
    ("203.0.113.0/24", "documentation"),    # RFC 5737
    ("224.0.0.0/4", "multicast"),           # RFC 5771 (not a unicast destination)
    ("240.0.0.0/4", "reserved"),            # RFC 1112 §4, the limited broadcast 255.255.255.255 among them
)
_IPV6_GLOBAL_UNICAST = ipaddress.IPv6Network("2000::/3")
_IPV6_NOT_PUBLIC = (
    ("2001::/23", "ietf_protocol"),     # RFC 2928, whole (see the docstring); Teredo 2001::/32 among them
    ("2001:db8::/32", "documentation"),  # RFC 3849
    ("2002::/16", "six_to_four"),       # RFC 3056
    ("3fff::/20", "documentation"),     # RFC 9637
    ("5f00::/16", "srv6"),              # RFC 9602
)
_MAPPED = ipaddress.IPv6Network("::ffff:0:0/96")      # RFC 4291 §2.5.5.2
_COMPATIBLE = ipaddress.IPv6Network("::/96")          # RFC 4291 §2.5.5.1 (deprecated)
_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")        # RFC 6052 §2.1


def _table(rows: tuple[tuple[str, str], ...]) -> tuple[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, str], ...]:
    return tuple((ipaddress.ip_network(block), reason) for block, reason in rows)


_V4_ROUTE, _V6_ROUTE = _table(_IPV4_HOST_ROUTE), _table(_IPV6_HOST_ROUTE)
# Every reason host_route() gives.
HOST_ROUTE_REASONS = frozenset(reason for _, reason in _IPV4_HOST_ROUTE + _IPV6_HOST_ROUTE) | {"host_interface"}
_V4_NOT_PUBLIC, _V6_NOT_PUBLIC = _table(_IPV4_NOT_PUBLIC), _table(_IPV6_NOT_PUBLIC)


def address(value: Any) -> IP:
    """``value`` as an IP address: a literal, an address object, or a socket address tuple (``getpeername()``'s).
    Anything else raises ``ValueError``, a name above all: R-6 judges addresses, never names."""
    if isinstance(value, tuple) and value:
        value = value[0]
    if isinstance(value, ipaddress.IPv4Address | ipaddress.IPv6Address):
        ip = value
    elif isinstance(value, str) and value:
        ip = ipaddress.ip_address(value)  # a name, or an empty or malformed literal, raises ValueError
    else:
        raise ValueError(f"not an IP address: {value!r}")
    if isinstance(ip, ipaddress.IPv6Address) and ip.scope_id:
        ip = ipaddress.IPv6Address(ip.packed)
    return ip


def _embedded(ip: IP) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 form carries: mapped, compatible (not ``::`` or ``::1``) or NAT64."""
    if not isinstance(ip, ipaddress.IPv6Address):
        return None
    if ip in _MAPPED or ip in _NAT64 or (ip in _COMPATIBLE and int(ip) > 1):
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def _forms(ip: IP) -> list[IP]:
    """Every address a connect to ``ip`` may be delivered to. A mapped address is its IPv4 address; a compatible or
    NAT64 one is judged both as itself and as the IPv4 address it carries."""
    inner = _embedded(ip)
    if inner is None:
        return [ip]
    return [inner] if ip in _MAPPED else [ip, inner]


def _lookup(ip: IP, v4: tuple[Any, ...], v6: tuple[Any, ...]) -> str | None:
    for network, reason in v4 if isinstance(ip, ipaddress.IPv4Address) else v6:
        if ip in network:
            return reason
    return None


def is_host_address(ip: IP) -> bool:
    """Whether ``ip`` is in this host's local table: a ``bind`` to it (port 0, never listened on) succeeds only for an
    address the kernel delivers locally. Fails closed: any error but ``EADDRNOTAVAIL`` (Windows' WSAEADDRNOTAVAIL,
    10049, is the same ``errno``) counts as local, an IPv6 address on a host without IPv6 among them.

    Residual: with ``net.ipv4.ip_nonlocal_bind=1`` (or its IPv6 twin) every address binds, so every address counts as
    local and the proxy refuses all egress. Safe, and surprising: the refusal's reason is ``host_interface``."""
    family = socket.AF_INET if isinstance(ip, ipaddress.IPv4Address) else socket.AF_INET6
    try:
        probe = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return True
    try:
        probe.bind((str(ip), 0))
    except OSError as exc:
        return exc.errno != errno.EADDRNOTAVAIL
    finally:
        probe.close()
    return True


def host_route(value: Any, *, is_local: Callable[[IP], bool] = is_host_address) -> str | None:
    """R-6: why connecting to ``value`` from the host's namespace would reach the host itself (``loopback``,
    ``link_local``, ``this_host`` or ``host_interface``), or None. ``value`` is an address (:func:`address`)."""
    forms = _forms(address(value))
    for ip in forms:
        reason = _lookup(ip, _V4_ROUTE, _V6_ROUTE)
        if reason:
            return reason
    for ip in forms:
        if is_local(ip):
            return "host_interface"
    return None


def not_public(value: Any) -> str | None:
    """Why ``value`` is not a globally reachable address (R-6's static ranges included), or None. It never consults
    the host, so it is the same everywhere; the proxy calls :func:`host_route` first, whatever the policy."""
    ip = address(value)
    if ip in _MAPPED or ip in _NAT64:
        ip = _embedded(ip) or ip
    reason = _lookup(ip, _V4_ROUTE, _V6_ROUTE) or _lookup(ip, _V4_NOT_PUBLIC, _V6_NOT_PUBLIC)
    if reason is None and isinstance(ip, ipaddress.IPv6Address) and ip not in _IPV6_GLOBAL_UNICAST:
        reason = "not_global_unicast"
    return reason
