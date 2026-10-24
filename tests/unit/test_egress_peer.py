"""R-6's predicate and "public", as pure functions on address values (STG-05 CS-3a; F28 §3.4).

Nothing here connects anywhere. The kernel oracle is replaced where a case needs a host interface, and is called for
real only on the loopback address and a documentation address. The routing tables' dump is parsed from synthetic
bytes; the real tables are read with planted routes in ``tests/integration/test_egress_host_local.py``.
"""

from __future__ import annotations

import errno
import ipaddress
import socket
import struct
import types
from collections.abc import Iterator

import pytest

from aew.harness.containment import peer


def never_local(ip: peer.IP) -> bool:
    return False


@pytest.mark.parametrize(("value", "reason"), [
    ("127.0.0.1", "loopback"),
    ("127.255.255.254", "loopback"),
    ("::1", "loopback"),
    ("::ffff:127.0.0.1", "loopback"),        # IPv4-mapped: a dual-stack connect goes to 127.0.0.1
    ("::127.0.0.1", "loopback"),             # IPv4-compatible (deprecated)
    ("64:ff9b::7f00:1", "loopback"),         # NAT64's well-known prefix carrying 127.0.0.1
    ("169.254.169.254", "link_local"),       # the cloud metadata address
    ("::ffff:169.254.169.254", "link_local"),
    ("fe80::1", "link_local"),
    ("fe80::1%eth0", "link_local"),
    ("0.0.0.0", "this_host"),  # noqa: S104 (a value R-6 judges; nothing binds it) a Linux connect reaches loopback
    ("0.1.2.3", "this_host"),
    ("::", "this_host"),
    ("::ffff:0.0.0.0", "this_host"),
])
def test_r6_refuses_every_address_that_reaches_the_host_and_names_its_class(value, reason):
    assert peer.host_route(value, is_local=never_local) == reason
    assert reason in peer.HOST_ROUTE_REASONS


def test_r6_refuses_an_address_of_the_hosts_own_interface_in_every_form():
    interface = {ipaddress.ip_address("10.9.8.7"), ipaddress.ip_address("2001:4860:4860::1")}

    def local(ip: peer.IP) -> bool:
        return ip in interface

    assert peer.host_route("10.9.8.7", is_local=local) == "host_interface"
    assert peer.host_route("::ffff:10.9.8.7", is_local=local) == "host_interface"  # judged as its IPv4 address
    assert peer.host_route("64:ff9b::a09:807", is_local=local) == "host_interface"  # and as the IPv4 it carries
    assert peer.host_route("2001:4860:4860::1", is_local=local) == "host_interface"
    assert peer.host_route("10.9.8.6", is_local=local) is None


@pytest.mark.parametrize("form", ["64:ff9b::a09:807", "::a09:807"], ids=["nat64", "compatible"])
def test_r6_judges_a_carried_ipv4_form_as_itself_too(form):
    """A NAT64 or IPv4-compatible address in the local table is refused even when the IPv4 address it carries is not
    there."""
    def local(ip: peer.IP) -> bool:
        return ip == ipaddress.ip_address(form)

    assert peer.host_route(form, is_local=local) == "host_interface"
    assert peer.host_route("10.9.8.7", is_local=local) is None


@pytest.mark.parametrize("value", [
    "10.0.0.5", "203.0.113.7", "8.8.8.8", "2001:4860:4860::8888", "64:ff9b::808:808", "fd00::1", "::ffff:8.8.8.8",
])
def test_r6_admits_an_address_that_does_not_reach_the_host(value):
    """Values only: R-6 refuses host routes, not private or documentation addresses (the allowlist may list one)."""
    assert peer.host_route(value, is_local=never_local) is None


@pytest.mark.parametrize("value", ["localhost", "gateway.example", "127.1", "", None, 2130706433, ()])
def test_r6_never_judges_a_name_or_a_missing_address(value):
    with pytest.raises(ValueError):
        peer.host_route(value, is_local=never_local)
    with pytest.raises(ValueError):
        peer.not_public(value)


def test_r6_judges_a_connected_sockets_peer_address_tuple():
    assert peer.host_route(("127.0.0.1", 443), is_local=never_local) == "loopback"
    assert peer.host_route(("fe80::1%eth0", 443, 0, 2), is_local=never_local) == "link_local"
    assert peer.host_route(("8.8.8.8", 443), is_local=never_local) is None


# One address from every block of IANA's IPv4 and IPv6 Special-Purpose Address Registries (both last updated
# 2025-10-09), and a public neighbour of each boundary. None means public. "stricter" marks an address IANA lists as
# globally reachable that the module refuses with its whole block (see its docstring).
@pytest.mark.parametrize(("value", "reason"), [
    ("0.0.0.1", "this_host"),
    ("10.1.2.3", "private"),
    ("11.0.0.1", None),
    ("100.64.0.1", "shared"),
    ("100.127.255.254", "shared"),
    ("100.128.0.1", None),
    ("127.0.0.1", "loopback"),
    ("169.254.1.1", "link_local"),
    ("172.16.0.1", "private"),
    ("172.31.255.254", "private"),
    ("172.32.0.1", None),
    ("192.0.0.1", "ietf_protocol"),      # 192.0.0.0/29, service continuity
    ("192.0.0.8", "ietf_protocol"),      # dummy address
    ("192.0.0.9", "ietf_protocol"),      # stricter: PCP anycast
    ("192.0.0.10", "ietf_protocol"),     # stricter: TURN anycast
    ("192.0.0.170", "ietf_protocol"),    # NAT64/DNS64 discovery
    ("192.0.2.1", "documentation"),
    ("192.31.196.1", None),              # AS112-v4
    ("192.52.193.1", None),              # AMT
    ("192.88.99.1", "deprecated_relay"),
    ("192.88.99.2", "deprecated_relay"),  # 6a44 relay anycast
    ("192.168.1.1", "private"),
    ("192.175.48.1", None),              # direct delegation AS112
    ("198.18.0.1", "benchmarking"),
    ("198.19.255.254", "benchmarking"),
    ("198.51.100.1", "documentation"),
    ("203.0.113.1", "documentation"),
    ("224.0.0.1", "multicast"),
    ("239.255.255.250", "multicast"),
    ("240.0.0.1", "reserved"),
    ("255.255.255.255", "reserved"),
    ("8.8.8.8", None),
    ("::1", "loopback"),
    ("::", "this_host"),
    ("::ffff:10.0.0.1", "private"),      # IPv4-mapped: judged as its IPv4 address
    ("::ffff:8.8.8.8", None),
    ("::127.0.0.1", "not_global_unicast"),  # IPv4-compatible
    ("64:ff9b::808:808", None),          # NAT64 well-known prefix: judged by the IPv4 it carries
    ("64:ff9b::a00:1", "private"),
    ("64:ff9b:1::1", "not_global_unicast"),  # local-use NAT64
    ("100::1", "not_global_unicast"),    # discard-only
    ("100:0:0:1::1", "not_global_unicast"),  # dummy prefix
    ("2001::1", "ietf_protocol"),        # Teredo
    ("2001:1::1", "ietf_protocol"),      # stricter: PCP anycast
    ("2001:1::3", "ietf_protocol"),      # stricter: DNS-SD SRP anycast
    ("2001:2::1", "ietf_protocol"),      # benchmarking
    ("2001:3::1", "ietf_protocol"),      # stricter: AMT
    ("2001:4:112::1", "ietf_protocol"),  # stricter: AS112-v6
    ("2001:10::1", "ietf_protocol"),     # deprecated ORCHID
    ("2001:20::1", "ietf_protocol"),     # stricter: ORCHIDv2
    ("2001:30::1", "ietf_protocol"),     # stricter: drone remote ID
    ("2001:200::1", None),               # just past 2001::/23
    ("2001:db8::1", "documentation"),
    ("2002::1", "six_to_four"),
    ("2620:4f:8000::1", None),           # direct delegation AS112
    ("3fff::1", "documentation"),
    ("5f00::1", "srv6"),
    ("fc00::1", "not_global_unicast"),   # unique-local
    ("fd12:3456::1", "not_global_unicast"),
    ("fe80::1", "link_local"),
    ("ff02::1", "not_global_unicast"),   # multicast
    ("2001:4860:4860::8888", None),
    ("2606:4700:4700::1111", None),
])
def test_public_means_globally_reachable_by_the_iana_registries(value, reason):
    assert peer.not_public(value) == reason


def test_the_kernels_local_table_holds_loopback_and_not_a_documentation_address():
    """The real oracle, on every platform: Windows reports a non-local bind as WSAEADDRNOTAVAIL (10049), which is
    ``errno.EADDRNOTAVAIL`` there, so failing closed does not make every address local."""
    assert peer.is_host_address(ipaddress.IPv4Address("127.0.0.1"))
    assert not peer.is_host_address(ipaddress.IPv4Address("192.0.2.1"))
    assert peer.host_route("8.8.8.8") is None


class _FakeSocketModule:
    """Stands in for ``socket`` inside :mod:`peer` only: its sockets' ``bind`` does what the case says."""

    AF_INET, AF_INET6, SOCK_STREAM = socket.AF_INET, socket.AF_INET6, socket.SOCK_STREAM

    def __init__(self, bind_error: int | None = None, create_error: int | None = None) -> None:
        self.bind_error, self.create_error = bind_error, create_error
        self.closed = 0

    def socket(self, family: int, kind: int) -> types.SimpleNamespace:
        if self.create_error is not None:
            raise OSError(self.create_error, "synthetic")

        def bind(address: tuple[str, int]) -> None:
            if self.bind_error is not None:
                raise OSError(self.bind_error, "synthetic")

        def close() -> None:
            self.closed += 1

        return types.SimpleNamespace(bind=bind, close=close)


@pytest.mark.parametrize(("errors", "local"), [
    ({"bind_error": errno.EADDRNOTAVAIL}, False),   # right: not in the local table
    ({}, True),                                     # every address binds (ip_nonlocal_bind=1)
    ({"bind_error": errno.EACCES}, True),           # the oracle cannot tell: local
    ({"create_error": errno.EAFNOSUPPORT}, True),   # no such family on this host: local
], ids=["not-local", "nonlocal-bind", "cannot-tell", "no-family"])
def test_an_oracle_that_cannot_say_not_local_counts_the_address_as_local(monkeypatch, errors, local):
    fake = _FakeSocketModule(**errors)
    monkeypatch.setattr(peer, "socket", fake)
    monkeypatch.setattr(peer, "local_routes", lambda family: [])  # the bind test alone: no local route covers it
    assert peer.is_host_address(ipaddress.IPv4Address("8.8.8.8")) is local
    assert peer.host_route("8.8.8.8") == (None if not local else "host_interface")
    assert fake.closed == (0 if fake.create_error is not None else 2)


# A synthetic rtnetlink route dump (linux/netlink.h, linux/rtnetlink.h), the kernel's wire format.
NEWROUTE, NOOP, ERROR, DONE, OVERRUN = 24, 1, 2, 3, 4
UNICAST, LOCAL, ANYCAST = 1, 2, 4
DUMP_INTR = 0x10


def message(kind: int, body: bytes = b"", flags: int = 0) -> bytes:
    length = 16 + len(body)
    return struct.pack("=IHHII", length, kind, flags, 1, 0) + body + bytes(-length % 4)


def attribute(kind: int, value: bytes) -> bytes:
    return struct.pack("=HH", 4 + len(value), kind) + value + bytes(-len(value) % 4)


def route(destination: str | None, prefix_length: int, *, kind: int = LOCAL, table: int = 255, family: int = 0,
          flags: int = 0, raw_destination: bytes | None = None) -> bytes:
    """One RTM_NEWROUTE message: a route of ``kind`` to ``destination``/``prefix_length`` in ``table``."""
    if destination is not None:
        ip = ipaddress.ip_address(destination)
        family = family or (socket.AF_INET if ip.version == 4 else socket.AF_INET6)
        raw_destination = ip.packed if raw_destination is None else raw_destination
    family = family or socket.AF_INET6
    attributes = attribute(15, struct.pack("=I", table))  # RTA_TABLE
    if raw_destination is not None:
        attributes = attribute(1, raw_destination) + attributes  # RTA_DST
    header = struct.pack("=BBBBBBBBI", family, prefix_length, 0, 0, table if table < 256 else 252, 0, 0, kind, 0)
    return message(NEWROUTE, header + attributes, flags)


END = message(DONE, struct.pack("=i", 0))


def dump(*datagrams: bytes):
    def read(family: int) -> Iterator[bytes]:
        yield from datagrams
    return read


def test_the_route_dump_gives_every_local_route_of_its_family_in_every_table():
    """Right: the local routes of every table, across datagrams; unicast, anycast and the other family's are not."""
    read = dump(route("3ffe:1::", 64) + route("3ffe:3::", 64, table=100) + message(NOOP),
                route("2001:db8::", 32, kind=UNICAST) + route("3ffe:4::", 128, kind=ANYCAST)
                + route("198.51.100.0", 24) + END)
    assert peer.local_routes(socket.AF_INET6, read=read) == [ipaddress.ip_network("3ffe:1::/64"),
                                                             ipaddress.ip_network("3ffe:3::/64")]
    assert peer.local_routes(socket.AF_INET, read=read) == [ipaddress.ip_network("198.51.100.0/24")]


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6], ids=["ipv4", "ipv6"])
def test_a_local_default_route_covers_every_address(family):
    """A route with no destination is the default route: its prefix is every address of the family."""
    every = ipaddress.ip_network("0.0.0.0/0" if family == socket.AF_INET else "::/0")
    assert peer.local_routes(family, read=dump(route(None, 0, family=family) + END)) == [every]


@pytest.mark.parametrize("datagrams", [
    [message(ERROR, struct.pack("=i", -1) + bytes(16)) + END],
    [route("3ffe:1::", 64) + message(DONE, struct.pack("=i", -16))],
    [route("3ffe:1::", 64, flags=DUMP_INTR) + END],
    [route("3ffe:1::", 64)],
    [],
    [route("3ffe:1::", 64)[:-8], END],
    [bytes(8)],
    [message(OVERRUN) + END],
    [message(NEWROUTE, struct.pack("=BBBBBBBBI", socket.AF_INET6, 64, 0, 0, 255, 0, 0, LOCAL, 0)
             + struct.pack("=HH", 64, 1) + bytes(16)) + END],
    [route(None, 24, raw_destination=bytes(4)) + END],
    [route(None, 64) + END],
    [route("3ffe:1::", 129) + END],
    [message(NEWROUTE, bytes(8)) + END],
], ids=["error", "done-with-error", "interrupted", "no-end-marker", "nothing", "message-cut-short",
        "header-cut-short", "overrun", "attribute-cut-short", "destination-wrong-size", "prefix-without-destination",
        "prefix-too-long", "route-cut-short"])
def test_a_route_dump_that_is_not_whole_is_never_read_as_complete(datagrams):
    with pytest.raises(ValueError):
        peer.local_routes(socket.AF_INET6, read=dump(*datagrams))


def cannot_read(error: Exception):
    def routes(family: int) -> list[peer.Network]:
        raise error
    return routes


@pytest.mark.parametrize(("routes", "local"), [
    (lambda family: [ipaddress.ip_network("3ffe:1::/64")], True),        # right: a local route covers it
    (lambda family: [ipaddress.ip_network("3ffe:1:0:1::/64")], False),   # no local route covers it
    (cannot_read(PermissionError(13, "synthetic")), True),               # the tables cannot be read: local
    (cannot_read(ValueError("synthetic: not whole")), True),            # the dump is not whole: local
], ids=["covered", "not-covered", "cannot-read", "not-whole"])
def test_an_address_a_local_route_covers_is_local_and_unreadable_tables_count_as_local(monkeypatch, routes, local):
    monkeypatch.setattr(peer, "_ROUTE_TABLES", True)
    monkeypatch.setattr(peer, "_binds", lambda ip, family: False)
    monkeypatch.setattr(peer, "local_routes", routes)
    assert peer.is_host_address(ipaddress.ip_address("3ffe:1::5")) is local
    assert peer.host_route("3ffe:1::5") == ("host_interface" if local else None)


def test_where_the_tables_are_not_read_the_bind_test_is_the_whole_check(monkeypatch):
    monkeypatch.setattr(peer, "_ROUTE_TABLES", False)
    monkeypatch.setattr(peer, "_binds", lambda ip, family: False)
    monkeypatch.setattr(peer, "local_routes", cannot_read(AssertionError("the tables were read")))
    assert peer.is_host_address(ipaddress.ip_address("3ffe:1::5")) is False


def test_the_real_tables_hold_loopback_on_linux_and_are_never_read_as_empty_elsewhere():
    """The real dump, in the test's own namespace. Off Linux it raises rather than give no routes."""
    if peer._ROUTE_TABLES:
        assert any(ipaddress.ip_address("127.0.0.1") in prefix for prefix in peer.local_routes(socket.AF_INET))
    else:
        with pytest.raises(OSError):
            peer.local_routes(socket.AF_INET)
