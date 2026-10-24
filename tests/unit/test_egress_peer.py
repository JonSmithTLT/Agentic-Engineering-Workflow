"""R-6's predicate and "public", as pure functions on address values (STG-05 CS-3a; F28 §3.4).

Nothing here connects anywhere. The kernel oracle is replaced where a case needs a host interface, and is called for
real only on the loopback address and a documentation address.
"""

from __future__ import annotations

import errno
import ipaddress
import socket
import types

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


@pytest.mark.parametrize(("fake", "local"), [
    (_FakeSocketModule(bind_error=errno.EADDRNOTAVAIL), False),   # right: not in the local table
    (_FakeSocketModule(), True),                                  # every address binds (ip_nonlocal_bind=1)
    (_FakeSocketModule(bind_error=errno.EACCES), True),           # the oracle cannot tell: local
    (_FakeSocketModule(create_error=errno.EAFNOSUPPORT), True),   # no such family on this host: local
], ids=["not-local", "nonlocal-bind", "cannot-tell", "no-family"])
def test_an_oracle_that_cannot_say_not_local_counts_the_address_as_local(monkeypatch, fake, local):
    monkeypatch.setattr(peer, "socket", fake)
    assert peer.is_host_address(ipaddress.IPv4Address("8.8.8.8")) is local
    assert peer.host_route("8.8.8.8") == (None if not local else "host_interface")
    assert fake.closed == (0 if fake.create_error is not None else 2)
