"""The relay presents a provider's client certificate (register E123; the designer's ruling of 2026-11-02).

Synthetic only: a throwaway CA, a server certificate and client certificates are made here, in ``tmp_path``, with the
``cryptography`` library (the ``g3`` extra, which the test lanes install). The provider is a local TLS server on
127.0.0.1 that **requires** a client certificate; the relay's connect is a seam that reaches it there, so no name is
resolved and nothing leaves the host. No real certificate, key or provider key is read, and no provider is called.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import socket
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from host_env import GUARDED

from aew.engine import readiness
from aew.errors import ContainmentUnavailable
from aew.harness.containment import client_cert, layout, netns, relay
from aew.harness.containment.relay import ProviderRelay, Upstream

if TYPE_CHECKING:
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec

pytestmark = GUARDED  # a mask plan is built here: none of it may read the host's home

TIMEOUT = 10.0
HOST = "provider.test"  # the server certificate's name; never resolved (the connect seam goes to 127.0.0.1)
PROVIDER = "mtls"
NOW = dt.datetime.now(dt.UTC)
# No body: the provider reads the head alone, and a close with unread bytes would reset the connection
REQUEST = b"POST /v1/chat/completions HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n"
OK = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"


# ---------------------------------------------------------------------------------------------- a throwaway PKI

# `cryptography` is imported where it is used, as in test_g3_facts.py: the lanes job collects changed test modules
# with pytest alone installed, and the test lanes install it (the g3 extra).

def _name(cn: str) -> x509.Name:
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


@dataclass
class Issued:
    cert: x509.Certificate
    key: ec.EllipticCurvePrivateKey


def issue(cn: str, issuer: Issued | None = None, *, ca: bool = False, server: bool = False,
          not_before: dt.datetime | None = None, not_after: dt.datetime | None = None) -> Issued:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    builder = (x509.CertificateBuilder().subject_name(_name(cn))
               .issuer_name(issuer.cert.subject if issuer else _name(cn)).public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(not_before or NOW - dt.timedelta(days=1))
               .not_valid_after(not_after or NOW + dt.timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if server:
        builder = builder.add_extension(x509.SubjectAlternativeName(
            [x509.DNSName(HOST), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
    return Issued(builder.sign(issuer.key if issuer else key, hashes.SHA256()), key)


def cert_pem(issued: Issued) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return issued.cert.public_bytes(serialization.Encoding.PEM)


def key_pem(issued: Issued, passphrase: bytes | None = None) -> bytes:
    from cryptography.hazmat.primitives import serialization

    encryption: Any = (serialization.BestAvailableEncryption(passphrase) if passphrase
                       else serialization.NoEncryption())
    return issued.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption)


@dataclass
class Pki:
    dir: Path
    ca: Issued
    server: Issued
    client: Issued
    other_ca: Issued

    def write(self, name: str, data: bytes) -> str:
        path = self.dir / name
        path.write_bytes(data)
        return str(path)

    def files(self, **override: bytes) -> client_cert.ClientCert:
        """The provider's three files on disk: the good client certificate, its key, and the CA that signed the
        server's, unless ``override`` gives other contents."""
        data = {"cert": cert_pem(self.client), "key": key_pem(self.client), "ca": cert_pem(self.ca), **override}
        return client_cert.ClientCert(PROVIDER, *(self.write(f"client-{f}.pem", data[f]) for f in client_cert.FILES))


@pytest.fixture
def pki(tmp_path: Path) -> Pki:
    ca = issue("AEW test CA", ca=True)
    other = issue("another CA", ca=True)
    return Pki(tmp_path, ca, issue(HOST, ca, server=True), issue("aew-relay", ca), other)


def policy_of(found: client_cert.ClientCert, mode: str | None = None) -> dict[str, Any]:
    network: dict[str, Any] = {"client_certs": {found.provider: {"cert": found.cert, "key": found.key,
                                                                 "ca": found.ca}}}
    if mode:
        network["mode"] = mode
    return {"containment": {"network": network}}


# ---------------------------------------------------------------------------------------------- the provider

@dataclass
class Seen:
    head: bytes = b""
    peer: dict[str, Any] | None = None
    error: BaseException | None = None


@contextmanager
def provider(pki: Pki, *, trusts: Issued | None = None) -> Iterator[tuple[int, Seen]]:
    """A local TLS server that requires a client certificate signed by ``trusts`` (default: the test CA), and answers
    one request 200."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(pki.write("server.pem", cert_pem(pki.server)), pki.write("server-key.pem",
                                                                                     key_pem(pki.server)))
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cadata=cert_pem(trusts or pki.ca).decode())
    listener = socket.create_server(("127.0.0.1", 0))
    listener.settimeout(TIMEOUT)
    seen = Seen()

    def serve() -> None:
        try:
            raw, _ = listener.accept()
        except OSError:
            return
        raw.settimeout(TIMEOUT)
        try:
            with context.wrap_socket(raw, server_side=True) as tls:
                seen.peer = tls.getpeercert()
                while b"\r\n\r\n" not in seen.head:
                    data = tls.recv(4096)
                    if not data:
                        break
                    seen.head += data
                tls.sendall(OK)
        except (ssl.SSLError, OSError) as exc:
            seen.error = exc
        finally:
            raw.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], seen
    finally:
        listener.close()
        thread.join(TIMEOUT)
    assert not thread.is_alive(), "the provider's thread did not end"


def ask(port: int, *, tls: ssl.SSLContext | None, client: client_cert.ClientCert | None) -> tuple[bytes, ProviderRelay]:
    """One request through a relay to the provider on ``port``: what the client got, and the relay."""
    service = ProviderRelay(Upstream(f"https://{HOST}:{port}/v1"), {},
                            connect=lambda _h, _p, t: socket.create_connection(("127.0.0.1", port), timeout=t),
                            tls=tls, client=client, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
                            body_timeout=TIMEOUT)
    near, served = socket.socketpair()
    near.settimeout(TIMEOUT)
    thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
    thread.start()
    try:
        near.sendall(REQUEST)
        answer = b""
        while data := near.recv(65536):
            answer += data
    finally:
        near.close()
        thread.join(TIMEOUT)
        service.close()
    assert not thread.is_alive(), "the relay's handler did not end"
    return answer, service


def trusting(pki: Pki) -> ssl.SSLContext:
    """A context that trusts the provider and presents no certificate: what the relay has with none configured."""
    out = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    out.load_verify_locations(cadata=cert_pem(pki.ca).decode())
    return out


# ---------------------------------------------------------------------------------------------- presenting it

def test_the_relay_presents_the_policys_certificate_and_the_provider_takes_it(pki):
    found = pki.files()
    tls, client = netns.relay_tls(PROVIDER, policy_of(found))
    assert client == found
    with provider(pki) as (port, seen):
        answer, service = ask(port, tls=tls, client=client)
    assert answer.startswith(b"HTTP/1.1 200"), answer
    assert seen.error is None and seen.head.startswith(b"POST /v1/chat/completions")
    assert seen.peer is not None and ((("commonName", "aew-relay"),),) == seen.peer["subject"]
    assert relay.describe(service)["provider_client_cert"] == f"{client_cert.FIELD}.{PROVIDER}.cert"


def test_a_provider_with_no_certificate_configured_gets_none(pki):
    assert netns.relay_tls(PROVIDER, {}) == (None, None)


def test_without_a_certificate_the_provider_refuses_and_the_answer_says_what_to_name(pki):
    with provider(pki) as (port, seen):
        answer, _ = ask(port, tls=trusting(pki), client=None)
    assert b" 502 " in answer.split(b"\r\n")[0] and b"X-AEW-Refusal: client_cert_required" in answer, answer
    assert b"containment.network.client_certs" in answer, answer
    assert seen.error is not None, "the provider was not asked for a certificate"


def test_a_certificate_the_provider_does_not_take_is_named_by_its_field_and_never_by_a_path(pki):
    rogue = issue("aew-relay", pki.other_ca)  # signed by a CA the provider does not trust
    found = pki.files(cert=cert_pem(rogue), key=key_pem(rogue))
    with provider(pki) as (port, _):
        answer, _ = ask(port, tls=client_cert.context(found), client=found)
    assert b"X-AEW-Refusal: client_cert_refused" in answer, answer
    assert found.field("cert").encode() in answer
    assert found.cert.encode() not in answer and found.key.encode() not in answer


def test_a_provider_certificate_the_ca_file_does_not_sign_is_untrusted_naming_the_ca_file(pki):
    found = pki.files(ca=cert_pem(pki.other_ca))
    with provider(pki) as (port, _):
        answer, _ = ask(port, tls=client_cert.context(found), client=found)
    assert b"X-AEW-Refusal: upstream_untrusted" in answer, answer
    assert found.ca.encode() in answer and found.field("ca").encode() in answer
    assert found.key.encode() not in answer


def test_a_ca_file_swapped_at_the_same_path_is_picked_up_by_the_next_start(pki):
    found = pki.files(ca=cert_pem(pki.other_ca))
    with provider(pki) as (port, _):
        answer, _ = ask(port, tls=netns.relay_tls(PROVIDER, policy_of(found))[0], client=found)
    assert b"upstream_untrusted" in answer, answer
    Path(found.ca).write_bytes(cert_pem(pki.ca))  # the announced CA, swapped in at the same path
    with provider(pki) as (port, _):
        answer, _ = ask(port, tls=netns.relay_tls(PROVIDER, policy_of(found))[0], client=found)
    assert answer.startswith(b"HTTP/1.1 200"), answer


# ---------------------------------------------------------------------------------------------- refusing to start

def _expired(pki: Pki) -> dict[str, bytes]:
    old = issue("aew-relay", pki.ca, not_before=NOW - dt.timedelta(days=60), not_after=NOW - dt.timedelta(days=1))
    return {"cert": cert_pem(old), "key": key_pem(old)}


def _future(pki: Pki) -> dict[str, bytes]:
    later = issue("aew-relay", pki.ca, not_before=NOW + dt.timedelta(days=2), not_after=NOW + dt.timedelta(days=60))
    return {"cert": cert_pem(later), "key": key_pem(later)}


CASES = {
    "expired": (_expired, "cert", "expired on"),
    "not_yet_valid": (_future, "cert", "is not valid until"),
    "mismatched_key": (lambda p: {"key": key_pem(issue("x", p.ca))}, "cert", "does not match the key named in"),
    "key_with_a_passphrase": (lambda p: {"key": key_pem(p.client, b"synthetic")}, "key", "without a passphrase"),
    "not_a_certificate": (lambda p: {"cert": b"not a certificate\n"}, "cert", "holds no PEM certificate"),
    "ca_file_with_no_certificate": (lambda p: {"ca": b"nothing here\n"}, "ca", "holds no certificate OpenSSL"),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_certificate_that_cannot_be_used_refuses_the_relays_start_with_its_own_line(pki, case):
    make, named, says = CASES[case]
    found = pki.files(**make(pki))
    with pytest.raises(ContainmentUnavailable) as raised:
        netns.relay_tls(PROVIDER, policy_of(found))
    message = raised.value.message
    assert raised.value.details["reason"] == client_cert.UNUSABLE
    assert says in message and found.field(named) in message, message
    if named != "key":
        assert getattr(found, named) in message, message  # the file itself, by path
    assert found.key not in message, message


@pytest.mark.parametrize("missing", client_cert.FILES)
def test_an_unreadable_file_refuses_the_start_naming_it(pki, missing):
    found = pki.files()
    Path(getattr(found, missing)).unlink()
    with pytest.raises(ContainmentUnavailable) as raised:
        netns.relay_tls(PROVIDER, policy_of(found))
    message = raised.value.message
    assert "cannot be read" in message and found.field(missing) in message, message
    assert found.key not in message


def test_the_validity_of_a_certificate_is_read_whichever_time_form_it_carries(pki):
    """RFC 5280: UTCTime up to 2049, GeneralizedTime from 2050."""
    for year in (2049, 2051):
        end = dt.datetime(year, 6, 1, 12, 0, 0, tzinfo=dt.UTC)
        issued = issue("x", pki.ca, not_before=dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC), not_after=end)
        assert client_cert.validity(cert_pem(issued)) == (dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC), end)
    assert client_cert.validity(b"no certificate") is None


# ---------------------------------------------------------------------------------------------- no relay, doctor, masks

def test_a_run_with_no_relay_refuses_a_provider_that_needs_a_certificate(pki):
    found = pki.files()
    message = client_cert.no_relay(PROVIDER, policy_of(found, "shared"), on_relay_route=False)
    assert message is not None and found.field("cert") in message and "proxy_only" in message
    assert client_cert.no_relay(PROVIDER, policy_of(found), on_relay_route=True) is None
    assert client_cert.no_relay("openai", policy_of(found), on_relay_route=False) is None


def test_doctor_shows_the_lines_a_launch_would_be_refused_with(pki, monkeypatch):
    monkeypatch.setattr(netns, "relay_route", lambda policy, provider_relay: True)
    good = pki.files()
    row = next(r for r in readiness.readiness_checks(policy_of(good)) if r["check"] == "client-cert")
    assert row["status"] == "PASS" and good.cert in row["detail"] and "valid until" in row["detail"], row
    bad = pki.files(**_expired(pki))
    row = next(r for r in readiness.readiness_checks(policy_of(bad)) if r["check"] == "client-cert")
    problems, _ = client_cert.inspect(bad)
    assert row["status"] == "FAIL" and all(p in row["detail"] for p in problems), row
    monkeypatch.setattr(netns, "relay_route", lambda policy, provider_relay: False)
    row = next(r for r in readiness.readiness_checks(policy_of(good, "shared")) if r["check"] == "client-cert")
    assert row["status"] == "FAIL" and "only AEW's provider relay presents it" in row["detail"], row


def test_the_certificate_and_key_are_masked_from_every_sandbox_and_the_ca_file_is_not(pki):
    found = pki.files()
    network = policy_of(found)["containment"]["network"]
    plan = layout._mask_plan(None, [], {}, [], named_extra=client_cert.mask_entries(network))
    masked = {*plan.left_out, *plan.files, *plan.dirs}
    real = {str(Path(p).resolve()) for p in masked}
    assert str(Path(found.cert).resolve()) in real and str(Path(found.key).resolve()) in real, plan
    assert str(Path(found.ca).resolve()) not in real
    said = dict(plan.what)
    assert any(found.field("key") == source for _, source, _ in client_cert.mask_entries(network))
    assert any("client key the relay presents" in v for v in said.values()), said


def _key_body(path: str) -> bytes:
    """A key file's base64, without its armour: what a leak of the key would show."""
    return b"".join(line for line in Path(path).read_bytes().splitlines() if line and not line.startswith(b"-----"))


def _details(policy: dict[str, Any]) -> bytes:
    return " | ".join(r["detail"] for r in readiness.readiness_checks(policy)).encode()


def test_the_keys_bytes_and_path_appear_in_no_answer_refusal_label_or_readiness_line(pki, monkeypatch):
    monkeypatch.setattr(netns, "relay_route", lambda policy, provider_relay: True)
    found = pki.files()
    said: list[tuple[client_cert.ClientCert, bytes]] = []
    with provider(pki) as (port, _):
        answer, service = ask(port, tls=client_cert.context(found), client=found)
    said += [(found, answer), (found, repr(relay.describe(service)).encode()),
             (found, _details(policy_of(found)))]
    for case in CASES.values():  # each refusal, read while its own key is on disk
        broken = pki.files(**case[0](pki))
        with pytest.raises(ContainmentUnavailable) as raised:
            client_cert.context(broken)
        said += [(broken, raised.value.message.encode()),
                 (broken, _details(policy_of(broken)))]
    for files, text in said:
        assert _key_body(files.key) not in text and files.key.encode() not in text, text
