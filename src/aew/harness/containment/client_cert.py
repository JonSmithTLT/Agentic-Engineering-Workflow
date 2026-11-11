"""A provider's client certificate, presented by its relay (register E123; the designer's ruling of 2026-11-02, the
relay presents the certificate).

A provider that requires a client certificate (mTLS) is reached the way any other is: through the run's provider relay
(``relay.py``), outside the sandbox. The execution policy names three files for it, under
``containment.network.client_certs.<provider>``: ``cert`` (the client certificate, PEM), ``key`` (its private key, PEM,
with no passphrase) and ``ca`` (the CA file the provider's own certificate is checked against). Their paths are the
operator's, and AEW never copies, stores or prints the key:

* **Read at the relay's start** (:func:`context`): a renewal, or a CA file swapped at the same path, is picked up by the
  next launch.
* **No fallback:** a certificate that is configured and cannot be used refuses the launch, with one plain line per
  problem, each naming its file (:func:`inspect`): unreadable, expired or not yet valid, not matching its key, a key
  OpenSSL cannot read, a CA file that holds no certificate, an upstream that is not ``https://``. ``aew doctor`` shows
  the same lines before any launch (``engine.readiness``). A run with no relay refuses the provider (:func:`no_relay`):
  a ``shared`` or ``isolated`` network, Windows, or a sandbox that could not be established under ``allow_weaker``,
  which is known only after ``establish`` (``supervisor.contain_launch``). A Lead with no relay is told at its start
  (:func:`unrelayed_lines`), and goes on with its other providers.
* **Kept from every sandbox:** the certificate and key paths are masked in every contained run (:func:`mask_entries`,
  read by ``layout.establish``), so the launch's self-test proves from inside that they cannot be read. The CA file is
  not: it may be the system's bundle, which the sandbox's own TLS needs.
* **The key's path in AEW's own lines:** a launch's refusal, a readiness line and the relay's label name the key by its
  policy field, and the certificate and CA file by path and field; the relay's answers on a failed handshake
  (``relay._tls_refused``), which reach the sandbox, name the policy field and the CA file only. The run's layout record
  lists the key's path among its masked paths (``layout.describe``'s ``hidden``), as it lists every mask, and the
  self-test's check of them can name it: the policy that names it is readable by the Lead in any case.

The trust is the CA file's alone, not the system's as well: the provider's certificate is checked against the CA the
operator swaps when a change is announced. A provider AEW knows a key variable for (``netns.PROVIDER_KEY_ENV``) still
needs that variable on the relay route; AEW requires none for a provider of its own id, with its upstream in
``containment.network.upstreams`` (whether OpenCode needs a placeholder key for one is the designer's check, left to
its first run).
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import os
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aew.errors import ContainmentUnavailable
from aew.harness.containment.relay import TLS_MINIMUM

FIELD = "containment.network.client_certs"
FILES = ("cert", "key", "ca")
WHAT = {"cert": "client certificate", "key": "client key", "ca": "CA"}
# The closed reasons of a refusal over a client certificate: one that cannot be used, a run with no relay, and a
# contained Lead whose only certificate provider no OpenCode profile pins a model of (E123 quick check, N3).
UNUSABLE, NO_RELAY, NO_MODEL = "client_cert_unusable", "client_cert_no_relay", "client_cert_no_model"


@dataclass(frozen=True)
class ClientCert:
    """One provider's three files, as the policy names them (``~`` expanded)."""

    provider: str
    cert: str
    key: str
    ca: str
    upstream: str | None = None  # containment.network.upstreams.<provider>, when the policy names one

    def field(self, name: str) -> str:
        return f"{FIELD}.{self.provider}.{name}"


def entries(network: Mapping[str, Any] | None) -> dict[str, ClientCert]:
    """The client certificates a policy's ``containment.network`` names, by provider id. The schema requires all three
    files of each; one that is not a string here (a policy the schema did not check) is left out."""
    if not isinstance(network, Mapping):
        return {}
    found = network.get("client_certs")
    out: dict[str, ClientCert] = {}
    for provider, files in (found.items() if isinstance(found, Mapping) else ()):
        if isinstance(files, Mapping) and all(isinstance(files.get(f), str) and files.get(f) for f in FILES):
            out[str(provider)] = ClientCert(str(provider), *(os.path.expanduser(str(files[f])) for f in FILES),
                                            upstream=_upstream(network, str(provider)))
    return out


def _upstream(network: Mapping[str, Any], provider: str) -> str | None:
    upstreams = network.get("upstreams")
    url = upstreams.get(provider) if isinstance(upstreams, Mapping) else None
    return str(url) if isinstance(url, str) else None


def configured(policy: Mapping[str, Any] | None) -> dict[str, ClientCert]:
    """:func:`entries` of a whole execution policy."""
    containment = (policy or {}).get("containment") or {}
    return entries(containment.get("network") if isinstance(containment, Mapping) else None)


def for_provider(provider: str | None, policy: Mapping[str, Any] | None) -> ClientCert | None:
    return configured(policy).get(provider or "")


def mask_entries(network: Mapping[str, Any] | None) -> list[tuple[str, str, str]]:
    """Each certificate and key path to mask, with what names it and what it is, as ``layout._named`` lists a secret."""
    return [(getattr(c, f), c.field(f), f"the {WHAT[f]} the relay presents for {c.provider}")
            for c in entries(network).values() for f in ("cert", "key")]


def no_relay(provider: str | None, policy: Mapping[str, Any] | None, *, on_relay_route: bool,
             lead: bool = False) -> str | None:
    """The refusal of a run whose provider needs a client certificate when the run would reach it without AEW's relay,
    which alone presents it; None when the provider needs none, or the run is on the relay route. ``lead``: the
    contained Lead's start, whose other way forward is a provider of its own, not a profile (E123 quick check, N4)."""
    found = for_provider(provider, policy)
    if found is None or on_relay_route:
        return None
    other = ("give the Lead a provider that needs no certificate: log in with your own OpenCode at your own terminal "
             "(`opencode auth login`), or pass a key with `--provider-env NAME`, then start `aew opencode` again"
             if lead else "pin a profile whose provider needs no certificate")
    return (f"the run's provider {provider} needs the client certificate named in {found.field('cert')}, and only "
            "AEW's provider relay presents it: this run would reach the provider without it (its network mode is not "
            "proxy_only; it is not contained, as on Windows; or its sandbox could not be established here and the "
            "policy allows weaker runs). Run it on Linux with containment.network.mode: proxy_only (the default) and "
            f"containment that works (`aew doctor` names what is missing), or {other}")


def unrelayed_lines(policy: Mapping[str, Any] | None, who: str) -> list[str]:
    """One start line for each provider the policy names a client certificate for, for a Lead that runs with no relay
    (E123 review, m3): that provider won't work this session. The Lead isn't refused: it may use other providers."""
    return [f"{who}: the {c.provider} provider needs the client certificate named in {c.field('cert')}, which only "
            "AEW's provider relay presents, and this Lead runs with no relay: it can't use that provider this session "
            "(a contained Lead on Linux can)\n" for c in configured(policy).values()]


def inspect(found: ClientCert, *, now: dt.datetime | None = None) -> tuple[list[str], dt.datetime | None]:
    """What stands in the way of presenting ``found``'s certificate, one plain line per problem, each naming its file
    and never its contents; and the certificate's expiry, when it could be read."""
    problems: list[str] = []
    for name in FILES:
        path = getattr(found, name)
        try:
            with open(path, "rb") as f:
                text = f.read(1) if name == "key" else f.read()  # never more of the key than whether it can be read
        except OSError as exc:
            problems.append(f"the {WHAT[name]} file {_named(found, name)} cannot be read: "
                            f"{exc.strerror or type(exc).__name__}")
            continue
        if name == "cert":
            problems += _validity(found, text, now or dt.datetime.now(dt.UTC))
    if problems:
        return problems + _scheme(found), None
    context = _context()
    try:
        context.load_cert_chain(found.cert, found.key, password=_no_passphrase)
    except ssl.SSLError as exc:
        if exc.reason == "KEY_VALUES_MISMATCH":
            problems.append(f"the client certificate {_named(found, 'cert')} does not match the key named in "
                            f"{found.field('key')}: name the key that goes with it there")
        else:
            problems.append(f"the client key file named in {found.field('key')} is not a PEM private key OpenSSL can "
                            "read without a passphrase (AEW does not take one)")
    try:
        context.load_verify_locations(cafile=found.ca)
    except (ssl.SSLError, OSError):
        problems.append(f"the CA file {_named(found, 'ca')} holds no certificate OpenSSL can read")
    return problems + _scheme(found), _not_after(found)


def _scheme(found: ClientCert) -> list[str]:
    """An upstream the relay reaches in plain http, where the certificate would never be presented (E123 review, m1).
    The schema can't refuse it: ``upstreams`` is a map of its own."""
    if found.upstream is None or found.upstream.lower().startswith("https://"):
        return []
    return [f"the provider's upstream {found.upstream} (containment.network.upstreams.{found.provider}) is not "
            "https://: the relay presents a client certificate only over TLS, so it would never be used"]


def _named(found: ClientCert, name: str) -> str:
    """How a line names one of the files: the certificate and the CA file by path and field; the key by its field
    alone. Every refusal and readiness line reaches the Lead, whose model needs no pointer to the key, masked or not."""
    if name == "key":
        return f"named in {found.field('key')}"
    return f"{getattr(found, name)} ({found.field(name)})"


def context(found: ClientCert, *, now: dt.datetime | None = None) -> ssl.SSLContext:
    """The relay's TLS context for ``found``: the certificate presented, the provider's checked against the CA file
    alone, TLS 1.2 at least. Read now, at the relay's start. Raises ``ContainmentUnavailable`` (:data:`UNUSABLE`) on
    any problem :func:`inspect` finds: the launch is refused, never served without the certificate."""
    problems, _ = inspect(found, now=now)
    if problems:
        raise ContainmentUnavailable(
            f"the provider {found.provider}'s client certificate cannot be used, so the run is refused (the relay "
            "never connects without it): " + "; ".join(problems) + ". `aew doctor` shows the same",
            provider=found.provider, reason=UNUSABLE)
    out = _context()
    out.load_cert_chain(found.cert, found.key, password=_no_passphrase)
    out.load_verify_locations(cafile=found.ca)
    return out


def _context() -> ssl.SSLContext:
    """A verifying client context with no trust of its own yet: the CA file is the only one it gets. Built by hand,
    not with ``ssl.create_default_context``, whose Python 3.13 flags (``VERIFY_X509_STRICT``,
    ``VERIFY_X509_PARTIAL_CHAIN``) this leaves unset: strict mode rejects internal CAs that lack an Authority Key
    Identifier, and an internal CA is what this route is for (E123 review, n1)."""
    out = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # check_hostname and CERT_REQUIRED are this protocol's defaults
    out.minimum_version = TLS_MINIMUM
    return out


def _no_passphrase() -> bytes:
    """Given to OpenSSL for a key with a passphrase, so it fails rather than asks on the terminal."""
    return b""


def _not_after(found: ClientCert) -> dt.datetime | None:
    try:
        with open(found.cert, "rb") as f:
            window = validity(f.read())
    except OSError:
        return None
    return window[1] if window else None


def _validity(found: ClientCert, text: bytes, now: dt.datetime) -> list[str]:
    window = validity(text)
    if window is None:
        return [f"the client certificate file {_named(found, 'cert')} holds no PEM certificate AEW can read"]
    not_before, not_after = window
    if now > not_after:
        return [f"the client certificate {_named(found, 'cert')} expired on {not_after:%Y-%m-%d %H:%M} UTC: put the "
                "renewed one at that path, or name it there, and start the run again"]
    if now < not_before:
        return [f"the client certificate {_named(found, 'cert')} is not valid until {not_before:%Y-%m-%d %H:%M} UTC"]
    return []


# ---------------------------------------------------------------------------------------- a certificate's validity
# The standard library reads no certificate's dates, and the runtime takes no new dependency for two fields. So the
# first PEM certificate's DER is walked as far as TBSCertificate's validity (RFC 5280 §4.1): [0] version, serial,
# signature, issuer, then validity.

_BEGIN, _END = b"-----BEGIN CERTIFICATE-----", b"-----END CERTIFICATE-----"


def validity(text: bytes) -> tuple[dt.datetime, dt.datetime] | None:
    """(notBefore, notAfter) of the first PEM certificate in ``text``, in UTC; None when there is none to read."""
    start = text.find(_BEGIN)
    end = text.find(_END, start + len(_BEGIN)) if start >= 0 else -1
    if start < 0 or end < 0:
        return None
    try:
        der = base64.b64decode(b"".join(text[start + len(_BEGIN):end].split()), validate=True)
        cert, _ = _tlv(der, 0, 0x30)
        tbs, _ = _tlv(der, cert, 0x30)
        at = tbs
        if der[at] == 0xA0:  # [0] EXPLICIT version
            at = _skip(der, at)
        for _ in range(3):  # serialNumber, signature, issuer
            at = _skip(der, at)
        validity_at, _ = _tlv(der, at, 0x30)
        not_before, after_at = _time(der, validity_at)
        not_after, _ = _time(der, after_at)
        return not_before, not_after
    except (binascii.Error, ValueError, IndexError):
        return None


def _header(der: bytes, at: int) -> tuple[int, int, int]:
    """(tag, content start, content length) of the TLV at ``at``."""
    tag, first = der[at], der[at + 1]
    if first < 0x80:
        return tag, at + 2, first
    count = first & 0x7F
    if count == 0 or count > 4:
        raise ValueError("unsupported DER length")
    return tag, at + 2 + count, int.from_bytes(der[at + 2:at + 2 + count], "big")


def _tlv(der: bytes, at: int, tag: int) -> tuple[int, int]:
    """The content start and the end of the TLV at ``at``, which must have ``tag``."""
    found, start, length = _header(der, at)
    if found != tag or start + length > len(der):
        raise ValueError("unexpected DER")
    return start, start + length


def _skip(der: bytes, at: int) -> int:
    _, start, length = _header(der, at)
    return start + length


def _time(der: bytes, at: int) -> tuple[dt.datetime, int]:
    """A UTCTime or GeneralizedTime (RFC 5280 §4.1.2.5: always UTC, with seconds), and where the next TLV starts."""
    tag, start, length = _header(der, at)
    raw = der[start:start + length].decode("ascii")
    if tag == 0x17:  # UTCTime: YYMMDDHHMMSSZ, 50-99 meaning 19xx
        year = int(raw[:2])
        raw = f"{1900 + year if year >= 50 else 2000 + year}{raw[2:]}"
    elif tag != 0x18:  # GeneralizedTime: YYYYMMDDHHMMSSZ
        raise ValueError("not a time")
    when = dt.datetime.strptime(raw, "%Y%m%d%H%M%SZ").replace(tzinfo=dt.UTC)
    return when, start + length
