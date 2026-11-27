"""F28's credentialing provider relay (F28 §3.3, network containment design v0.2; STG-05 CS-3b).

The harness's provider ``baseURL`` is a loopback port in its sandbox, which the shim forwards to this relay's socket
file. The relay runs in the run's supervisor, outside the sandbox, and holds the provider's credential: the sandbox
holds only a sentinel in its place (:func:`sentinel`). For each request it:

1. reads the request head (``origin-form`` only: a target that names a host is refused, so the sandbox never chooses
   where the relay connects), and a header value with a control character other than HTAB is refused 400
   (``bad_header``; RFC 9110 §5.5, :mod:`aew.harness.containment.http1`). Its path must lie inside the upstream's
   prefix, spelled unambiguously (:data:`OUTSIDE_UPSTREAM_PATH`), and name an operation the relay's policy allows
   (:data:`OPERATION_NOT_PERMITTED`): the provider's model calls and its model list (:data:`DEFAULT_OPERATIONS`), and
   any other the operator's adopted execution policy names for the provider (``containment.network.relay_operations``,
   read on the host at the relay's start: never the request's or the sandbox's to widen). Either refusal is answered 403
   before anything is connected. A model call's body is held to the provider's allowed operations as its path is
   (register E361): it is read whole (within :data:`MAX_BODY`, and within :data:`MAX_HELD` for all the bodies the relay
   holds at once) before anything is connected, must be one JSON object (:data:`BODY_UNREADABLE`), and may use a field
   of :func:`body_fields` only when the operator's adopted policy opts that field in for the provider
   (``containment.network.relay_body_fields``, read on the host at the relay's start, as ``relay_operations`` is): else
   it is refused 403 (:data:`BODY_FIELD_NOT_PERMITTED`), naming the field, and nothing is connected. Any other
   operation's body is streamed as it comes;
2. puts the real credential where the sentinel is, in a credential header only (:data:`CREDENTIAL_HEADERS`): never in
   any other header, which an upstream might echo back. A credential header without a sentinel passes as it came:
   it carries what the sandbox already had, which is no key (a launch whose provider would get none is refused before
   it starts: ``netns.provider_key_missing``). A credential that
   can change while the relay runs (a stored login the operator's own harness refreshes) is resolved for each
   request instead (``resolve``), with the headers that go with it; one that cannot be used now is answered 401,
   or 503 for a busy or locked store, with the resolver's message (:class:`Unavailable`), and nothing is connected;
3. drops the hop-by-hop headers, sets ``Host`` to the upstream's and asks for ``Connection: close``. A header the
   login's grant sets (``login_headers``, such as ChatGPT's account id) is the grant's alone: the client's, which holds
   a placeholder, is dropped whether or not the grant has a value for it.
   **Placeholders:** a sentinel this relay did not issue, anywhere in the request line or the headers (a credential
   header after the swap, any other header, the target), refuses the request 401 before anything is connected, so no
   such placeholder goes upstream in them: :data:`OTHER_PLACEHOLDER` when this run issued it to another provider,
   :data:`STALE_PLACEHOLDER` when no relay of the run did (an earlier session's, kept in a store), each with its own
   remedy. This relay's own sentinel is swapped in a credential header only, and passes elsewhere as it came (it stands
   for nothing outside the relay). The body is never read for one: a prompt may quote a placeholder;
4. connects to its one fixed upstream, through the operator's HTTP proxy when the provider's environment names one,
   over TLS for ``https``;
5. sends the request and its body (a model call's as it was read, framed by its length; any other's framed as it
   came, by ``Content-Length`` or chunked), then streams the response back as it comes, until the upstream ends it,
   the client goes away or the stream's time is up. It removes a credential from a failed answer's body before it
   reaches the run: on a route whose grant holds a credential, a non-2xx answer is held first, until its end, the
   record's excerpt bound (:data:`EXCERPT_RAW_BYTES`) or :data:`EXCERPT_DRAIN_S`, so a slow one's head goes on up to
   that much later, and the grant's credential values in its body are taken out by the record's own redaction
   (:class:`_Scrub`). One whole within the hold that holds none goes on exactly as it came; one whole that holds one
   goes on without it, framed by its new length; any other goes on cleaned as it comes, unencoded and re-framed
   (:meth:`ProviderRelay._failed_answer`). A 2xx answer streams as it comes, untouched.

**Bounds:** the relay bounds request size, the model-call bodies it holds, concurrency and stream time, each an
implementation bound below, set by the host-side code that starts the relay and never by a request or the sandbox. A
body over :data:`MAX_BODY` is refused 413 (:data:`REQUEST_TOO_LARGE`): before anything is connected when its
``Content-Length`` says so, and, for a chunked body, whose every byte is counted as it goes (its framing and trailer
included), at the chunk or trailer line that would pass the bound, so the upstream never gets the request whole. A
model call's body, read whole for its scope, is held within :data:`MAX_HELD` across the relay, with an estimate of
its parse while it is checked, until it has gone upstream: one that would pass it beside the others is refused 503
(:data:`RELAY_BUSY`), one that would pass it alone 413 (:data:`REQUEST_TOO_LARGE`), and nothing is connected. A
request that finds :data:`MAX_ACTIVE` others in progress on the relay is refused 503 (:data:`RELAY_BUSY`) before its
head is read, and nothing is connected. A response that has not ended :data:`STREAM_TIMEOUT` after the request was sent
is ended (:data:`STREAM_TIMEOUT_REASON`), answered 504 if its head had not come.

**Outcome:** the relay never retries. Once any byte of a request may have gone upstream, a broken connection is
:data:`UPSTREAM_OUTCOME_UNKNOWN` (outcome ``unknown``: the provider may have accepted it), never
``upstream_unreachable``, which says the request was not sent: a client that retries one must not take it for the
other. A request refused while its body was still arriving (too large, stalled, malformed, or its client closing or
resetting its connection) is ``refused`` even after its head went upstream, as the upstream never got it whole. A
non-2xx answer whose body then breaks stays ``forwarded``: the provider had settled the call. A stream the relay itself
ends, as the run ends or its client goes, stays ``forwarded`` too. A body with neither length nor chunking that the
upstream cuts ends at the harness in a clean close, as its own end would, and so does a failed answer cleaned as it
streams to an HTTP/1.0 client (which is never sent chunks): HTTP/1.1 cannot mark it, and the shim's leg is a socket
file, which carries no reset. Only the record tells the two apart (``upstream_broken``).

**The record:** a fixed operation label distinguishes recognized model calls and model lists without recording the
request target; only a request refused for its operation, once past the path check, also records its method and its
endpoint under the prefix, with no query, so the operator can see what to list. Each request, whatever became of it, is
one entry given to the relay's ``record`` (one per request, when the request ends): when, the provider route, the fixed
destination, what became of its credential header (:data:`SWAP_OUTCOMES`), the login kind, what the relay answered and,
for one it forwarded, the upstream's status, with a short excerpt of a failure's body, redacted, and how its stream
ended (``ended``). Each entry also carries its own ``request_id`` (random, one per request: the relay makes one attempt
per request), the sha256 of the execution policy the relay was started from (``policy_sha256``) and, where a client
certificate is used, the sha256 of its leaf as read at the relay's start (``client_certificate_sha256``; never key
material). Never a credential value. A forwarded request is also counted by its upstream status class when that is
not 2xx, so a 401 is never counted only as ``allowed``.

One request per connection: each answer says ``Connection: close``. The upstream is fixed, so the relay never judges
a destination: ruling R-6 is the egress proxy's (``egress.py``), and this module does not use it. A host-local upstream
(F18.8's Provider Gateway) is allowed for the same reason.

**Streaming:** the response is relayed by one thread per connection, reading the upstream only when the client has
taken the last chunk (a ``sendall`` that blocks is the backpressure), and watching the client: when it goes away, the
upstream connection is closed at once. It is counted ``cancelled`` only when it went before the response's end (its
``Content-Length``, or its last chunk): OpenCode closes as soon as it has a whole answer, before the upstream's own
close arrives (seen in the live lane, 2026-10-24), and that is no cancelled turn (:class:`_Body`).
"""

from __future__ import annotations

import base64
import itertools
import json
import re
import secrets
import selectors
import socket
import ssl
import time
import urllib.parse
import zlib
from collections.abc import Callable, Collection, Mapping
from typing import TYPE_CHECKING, Any, Literal

from aew.errors import ValidationFailed
from aew.harness.containment.egress import CHUNK, Service
from aew.harness.containment.http1 import HOP_BY_HOP, TOKEN, BadField, fields
from aew.harness.containment.http1 import chunk_size as _chunk_size
from aew.harness.containment.http1 import close_head as _close_head
from aew.harness.containment.http1 import head as _head
from aew.http_close import REFUSAL_DRAIN_S, close_after_response

if TYPE_CHECKING:
    from aew.harness.containment.client_cert import ClientCert

# Implementation bounds, not policy. A provider request's head from OpenCode 2.0.18 is about 1 KiB (measured on the
# Rocky VM, 2026-10-24); 32 KiB is nginx's default for a request head (large_client_header_buffers 4 8k).
MAX_HEAD = 32 * 1024
HEAD_TIMEOUT = 30.0     # the whole request head, from when the relay starts reading it
CONNECT_TIMEOUT = 10.0  # a SYN nobody answers, and the TLS handshake
BODY_TIMEOUT = 60.0     # a pause inside the request body
# Implementation bound: a request's body. Above the largest request a provider documents taking (Anthropic's Messages
# API: 32 MB; OpenAI's image inputs: 50 MB in all), so no model call OpenCode makes reaches it.
MAX_BODY = 64 * 1024 * 1024
# Implementation bound: what one relay holds at once for the model-call bodies it reads whole for their scope before
# anything is sent (register E361): each body, from its first byte until it has gone upstream, and the estimated cost of
# parsing it (:func:`_scan`) while it is checked. Without it the worst case would be MAX_BODY times MAX_ACTIVE
# (2 GiB) of bodies, and their parse many times that; with it, one body at MAX_BODY whose bulk is its strings (images,
# documents) fits, and so do many of the sizes model calls take (a turn's context is a few MiB at most).
MAX_HELD = 256 * 1024 * 1024
# Implementation bound: what parsing one JSON value of a body costs at most, beyond its text and its strings' text
# (:func:`_scan`). Measured with tracemalloc (2026-11-24, #551's review, m3, and its quick checks, q1 and q4): 28-62
# bytes per value across arrays of empty objects, empty arrays, small objects, numbers and strings; the most, up to
# about 133 per value on CPython 3.11 (each pair counted twice, by its ``:`` and its ``,``), for a compact object of
# many short unique keys whose values are each a new number object, at a size just past a dict's resize. 160 holds
# that shape's peak to about 0.8 of the estimate on 3.11 (a little less on 3.13).
PARSE_VALUE_BYTES = 160
# What any parse holds besides (its objects' headers, the parser's state): 1-2 KiB measured alike; 16 KiB margin.
PARSE_BASE_BYTES = 16 * 1024
# Implementation bound: how deep a model call's body may nest its arrays and objects (its top-level object is 1). It is
# checked before the body is parsed, so the relay answers a deep body the same on every interpreter: CPython 3.11's
# decoder refuses one past its recursion limit (about 1000), and 3.12's takes far deeper (#551, CI at 04c50cce). A
# model call's body nests a few levels, and a tool's parameter schema some more; 128 leaves a wide margin below both.
MAX_NESTING = 128
# Implementation bound: the requests one relay serves at once (one thread each). OpenCode runs a session's subagents in
# parallel, each with one model call open at a time, besides a title request: 32 is far above what a session holds
# open (not measured), and bounds the threads and sockets a sandbox can make its relay hold.
MAX_ACTIVE = 32
# Implementation bound: a response, from the request's end to the response's end, its head included. A provider's own
# SDK gives up on a request after 10 minutes by default (OpenAI's and Anthropic's); an hour is no model call's stream,
# and bounds one the provider never ends.
STREAM_TIMEOUT = 3600.0
TLS_MINIMUM = ssl.TLSVersion.TLSv1_2  # every upstream context's floor, a client certificate's included
SENTINEL_PREFIX = "aew-relay-"
STALE_PLACEHOLDER = "stale_placeholder"
OTHER_PLACEHOLDER = "other_placeholder"
# What became of a request's credential header: its sentinel swapped for the credential; none carried one; or one
# carried a sentinel this relay does not hold, and the request was refused.
SWAP_OUTCOMES = ("swapped", "none", "refused_unknown_placeholder")
# A run label's ``network.provider_relay`` (F28 §3.1; :func:`describe`): the run's network started a provider relay, or
# it did not. Every reader takes them from here (register E148; #649's review, F2).
RELAY_CONFIGURED, RELAY_NONE = "configured", "none"
PROVIDER_RELAY_STATES = (RELAY_CONFIGURED, RELAY_NONE)
# The refusals of a request outside the relay's operation scope (register STG-05): a path outside the upstream's
# prefix, or spelled so an upstream might read it as another one; and an operation the relay's policy does not allow.
OUTSIDE_UPSTREAM_PATH = "outside_upstream_path"
OPERATION_NOT_PERMITTED = "operation_not_permitted"
# The refusals of a model call's body outside the relay's scope (register E361): a field its policy does not opt in for
# the provider (:func:`body_fields`), and a body the relay cannot read as one JSON object (so cannot hold to it).
BODY_FIELD_NOT_PERMITTED = "body_field_not_permitted"
BODY_UNREADABLE = "body_unreadable"
# The refusals and ends of the relay's bounds (module docstring, "Bounds"), and the outcome of a request that may have
# reached the upstream when its connection broke ("Outcome").
REQUEST_TOO_LARGE = "request_too_large"
RELAY_BUSY = "relay_busy"
STREAM_TIMEOUT_REASON = "stream_timeout"
UPSTREAM_OUTCOME_UNKNOWN = "upstream_outcome_unknown"
# The shim's answer when a relay leg's socket file takes no connection (:func:`unreachable_answer`): the relay is gone,
# as while its run ends, so the harness gets a reason, never a bare reset.
RELAY_UNREACHABLE = "relay_unreachable"
# What became of a request, in its entry: answered by the upstream; refused, with nothing (or, for a body refused as it
# arrived, never the whole request) sent; or unknown, once any byte went upstream and the exchange did not end whole.
OUTCOMES = ("forwarded", "refused", "unknown")
# How a forwarded request's stream ended, in its entry's ``ended`` (and ``stream_timeout`` for a request whose response
# head never came). A stream cut by the run's end (``relay_closed``) or by its client (``client_gone``) stays
# ``forwarded``: the relay ended it, not the provider; so does a non-2xx answer whose body broke, which the provider had
# already settled.
STREAM_ENDS = ("complete", "client_gone", "upstream_broken", "stream_timeout", "relay_closed")
# The operations every relay forwards (:func:`_operation`'s labels): a model call and the model list. Anything else
# goes upstream only when the operator's adopted policy names it (:func:`listed_operations`). That these cover
# OpenCode's calls through the relay is derived, not measured in a session of the pinned version
# (tests/fixtures/opencode/relay-operations-2.2.6.json says from what).
DEFAULT_OPERATIONS = frozenset({"model", "models_list"})
# The label of a request allowed only by an entry of the policy's ``relay_operations``.
POLICY_OPERATION = "policy_listed"
# Implementation bound: how much of a failed answer's body the record keeps. A provider's error is a short JSON object
# (OpenAI's 401 for a wrong key is about 250 bytes); the record is for "why", not the whole answer.
EXCERPT_BYTES = 512
# The headers a provider SDK carries its key in: OpenAI's and most others' bearer token, Anthropic's, Azure OpenAI's
# and Google's. The relay puts a credential nowhere else.
CREDENTIAL_HEADERS = frozenset({"authorization", "x-api-key", "api-key", "x-goog-api-key"})
# Resolve-mode forwards the target raw. Accept only unreserved path characters and literal separators so
# neither percent decoding nor upstream-specific path parameter handling can change its interpretation.
_RESOLVED_PATH = re.compile(r"/[A-Za-z0-9._~/\-]*")
# A key-mode path is held to the same rule, with ``:`` too: Google's model calls name their method after one
# (``/models/<id>:generateContent``). Its query passes as it came: it cannot move the path.
_KEYED_PATH = re.compile(r"/[A-Za-z0-9._~/:\-]*")
# What the policy may name in ``relay_operations``: a method and an exact path under the upstream's prefix.
_POLICY_ENTRY = re.compile(r"(GET|POST|PUT|PATCH|DELETE) (/[A-Za-z0-9._~/:\-]*)")
# What the policy may name in ``relay_body_fields``: one of :data:`BODY_FIELDS`, or a tool other than one the client
# runs itself, by its type (``tools.<type>``, :func:`body_fields`).
_BODY_FIELD_ENTRY = re.compile(r"tools\.[a-z0-9_]+")
_PHRASES = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 408: "Request Timeout",
            413: "Content Too Large", 431: "Request Header Fields Too Large", 501: "Not Implemented",
            502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout"}

Connector = Callable[[str, int, float], socket.socket]
# What a resolver gives one request: each sentinel's value, and the headers the relay sets (replacing any of the same
# name the client sent), such as an account header a stored login carries.
Grant = tuple[Mapping[str, str], Mapping[str, str]]


CredentialCause = Literal["expired", "kind_changed", "unknown_shape", "missing", "unreadable"]


class Unavailable(Exception):
    """A name-only refusal whose message is sent to the client and whose cause is counted."""

    def __init__(self, message: str, *, cause: CredentialCause, retryable: bool = False) -> None:
        super().__init__(message)
        self.cause: CredentialCause = cause
        self.retryable = retryable


def sentinel() -> str:
    """A placeholder for one provider variable inside the sandbox: random, so the relay never mistakes text a client
    happens to send for it, and worthless outside this run's relay."""
    return SENTINEL_PREFIX + secrets.token_hex(16)


class Upstream:
    """The relay's one destination, from the execution policy: ``scheme://host[:port][/base path]``."""

    def __init__(self, url: str) -> None:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.query or parts.fragment \
                or parts.username or parts.password:
            raise ValidationFailed(f"provider upstream {url!r} is not an http(s)://host[:port][/path] URL",
                                   upstream=url, reason="bad_upstream")
        try:
            port = parts.port
        except ValueError:
            raise ValidationFailed(f"provider upstream {url!r} has a bad port", upstream=url,
                                   reason="bad_upstream") from None
        self.url = url
        self.scheme = parts.scheme
        self.host = parts.hostname
        self.port = port or (443 if parts.scheme == "https" else 80)
        self.path = parts.path.rstrip("/")
        default = (self.scheme, self.port) in (("https", 443), ("http", 80))
        self.authority = (f"[{self.host}]" if ":" in self.host else self.host) + ("" if default else f":{self.port}")


class Proxy:
    """The operator's own HTTP proxy for the relay's upstream (``HTTPS_PROXY`` and the like in the provider's
    environment): ``http://[user:password@]host:port``. The relay asks it for a ``CONNECT`` to the upstream."""

    def __init__(self, url: str) -> None:
        parts = urllib.parse.urlsplit(url if "://" in url else f"http://{url}")
        if parts.scheme != "http" or not parts.hostname:
            raise ValidationFailed("the provider's proxy variable names a proxy the relay cannot use: only an "
                                   "http://host:port proxy is supported", reason="bad_proxy")
        self.host, self.port = parts.hostname, parts.port or 80
        self.auth = None
        if parts.username is not None:
            raw = f"{urllib.parse.unquote(parts.username)}:{urllib.parse.unquote(parts.password or '')}"
            self.auth = "Basic " + base64.b64encode(raw.encode()).decode()


def _connect(host: str, port: int, timeout: float) -> socket.socket:
    return socket.create_connection((host, port), timeout=timeout)  # every address the name has, in turn


def stale_message() -> str:
    """The refusal of a placeholder no relay of the session issued, with the step for each place it can come from: an
    earlier session's AEW login row (a start removes those), or a login saved inside the Lead, in the Lead's own store,
    which no start removes. Its step acts on the Lead's store alone, never on the operator's own OpenCode login."""
    from aew.harness.opencode.lead import LEAD_DIR
    from aew.harness.opencode.login import STORE_REL
    from aew.knowledge.manifest import AEW_DIR

    return ("AEW: this request carries a key placeholder no relay of this session issued, so it was not sent to the "
            "provider. An earlier session's login row holds one, and each start removes those: start the run again "
            "(for the Lead, `aew opencode`). If it comes back after a fresh start, a login saved inside the Lead holds "
            f"it, in the Lead's own store, which a start keeps: with the Lead stopped, move {AEW_DIR}/{LEAD_DIR}/"
            f"{STORE_REL} aside (OpenCode makes a new one, without the Lead's earlier sessions), then start it again. "
            "Your own OpenCode login is not involved")


OTHER_MESSAGE = ("AEW: this request carries the placeholder this run gave another provider's key, which stands for "
                 "nothing at this provider, so it was not sent. The harness sends that key to the wrong provider: "
                 "check the provider settings the run was given (starting again does not change them)")


def _placeholders(value: str, own: Collection[str], foreign: Collection[str]) -> None:
    """Refuse ``value`` when it holds a sentinel other than one of ``own`` (which pass as they came):
    :data:`OTHER_PLACEHOLDER` for one of ``foreign`` (this run issued it to another provider), else
    :data:`STALE_PLACEHOLDER`. The value is never echoed."""
    rest = value
    for token in own:
        rest = rest.replace(token, "")
    if SENTINEL_PREFIX not in rest:
        return
    if any(token in rest for token in foreign):
        raise _Refused(401, OTHER_PLACEHOLDER, OTHER_MESSAGE)
    raise _Refused(401, STALE_PLACEHOLDER, stale_message())


def _credential(value: str, credentials: Mapping[str, str], foreign: Collection[str] = ()) -> tuple[str, str | None]:
    """A credential header's value with its sentinel, alone or after a scheme (``Bearer <sentinel>``), swapped, and
    the sentinel used, if any. A sentinel left in the credential header is refused (:func:`_placeholders`),
    including this relay's own, as it would go where the credential goes."""
    scheme, sep, token = value.partition(" ")
    if sep and token.strip() in credentials:
        return f"{scheme} {credentials[token.strip()]}", token.strip()
    if value.strip() in credentials:
        return credentials[value.strip()], value.strip()
    _placeholders(value, (), foreign)
    return value, None


def _unambiguous(path: str) -> bool:
    """Whether ``path`` has no empty, ``.`` or ``..`` segment, which an upstream might fold into another path."""
    return "//" not in path and not {".", ".."}.intersection(path.split("/"))


def listed_operations(entries: Collection[str], *, resolved: bool = False) -> frozenset[tuple[str, str]]:
    """The operations a provider's ``containment.network.relay_operations`` entries add to :data:`DEFAULT_OPERATIONS`:
    each ``METHOD /path``, the path exact and relative to the prefix of whichever upstream the provider's relay uses
    (``POST /embeddings`` under ``https://api.openai.com/v1``; the same entry applies under a stored login's
    upstream). Raises ``ValidationFailed`` (reason ``bad_relay_operation``) on any other form (a path that ends in
    ``/`` among them), for a stored-login relay (``resolved``) on a path it could never match (one with ``:``, which its
    paths never hold), and on a model call or the model list, in any case (#551's review, m6, and its quick check)."""
    out = set()
    for entry in entries:
        found = _POLICY_ENTRY.fullmatch(entry) if isinstance(entry, str) else None
        if found is None or found[2].endswith("/") or not _unambiguous(found[2]):
            raise ValidationFailed(f"relay operation {entry!r} is not METHOD /path (GET, POST, PUT, PATCH or DELETE, "
                                   "and a path under the provider's upstream, such as POST /embeddings)",
                                   entry=str(entry), reason="bad_relay_operation")
        if resolved and not _RESOLVED_PATH.fullmatch(found[2]):
            raise ValidationFailed(f"relay operation {entry!r} names a path the stored login's relay never forwards "
                                   "(its paths hold no ':'), and the entry applies to that relay too: take it out, "
                                   "or use the API-key route for this provider", entry=str(entry),
                                   reason="bad_relay_operation")
        if _default_operation(found[1], found[2], fold=True):  # in any case an upstream might take it in
            raise ValidationFailed(f"relay operation {entry!r} is a model call or the model list, which every relay "
                                   "forwards already, a model call's body held to its scope: take it out (to allow a "
                                   "field of a model call's body, name it in containment.network.relay_body_fields)",
                                   entry=str(entry), reason="bad_relay_operation")
        out.add((found[1], found[2]))
    return frozenset(out)


# The model-call endpoints of each provider route (:func:`_operation`), relative to the upstream's prefix
_MODEL_ENDPOINTS = ("/responses", "/chat/completions", "/completions", "/messages")
_GOOGLE_MODEL_CALL = r"/models/[^/:]+:(?:generateContent|streamGenerateContent)"


def _default_operation(method: str, endpoint: str, *, fold: bool = False) -> str | None:
    """Which of :data:`DEFAULT_OPERATIONS` ``method`` and ``endpoint`` are, if either: as the relay matches a request
    (exactly), or, with ``fold``, in any letter case, as an upstream might."""
    key = endpoint.casefold() if fold else endpoint
    if method == "GET" and key == "/models":
        return "models_list"
    if method == "POST" and (key in _MODEL_ENDPOINTS or re.fullmatch(_GOOGLE_MODEL_CALL, endpoint,
                                                                      re.IGNORECASE if fold else 0)):
        return "model"
    return None


def _operation(method: str, target: str, base: str, listed: Collection[tuple[str, str]] = ()) -> str:
    """Recognize API operations relative to the exact configured base, without retaining the path or query: a model
    call, the model list, one the policy lists (:data:`POLICY_OPERATION`), else ``unknown``. A model call is one
    whatever the policy lists, so its body is held to its scope (#551's review, m6)."""
    path = target.partition("?")[0]
    if not path.startswith(base + "/"):
        return "unknown"
    endpoint = path[len(base):]
    default = _default_operation(method, endpoint)
    if default is not None:
        return default
    if (method, endpoint) in listed:
        return POLICY_OPERATION
    return "unknown"


# The fields of a model call's body that ask the provider for more than the call itself: an object stored with the
# provider (an earlier response, a conversation, a prompt, a file, a context cache, a container) or a server of its
# own. The relay refuses each unless the policy opts it in for the provider (register E361). No provider's request
# surface is pinned in this repository, so the list is an implementation choice, from each provider's request reference
# (OpenAI's Responses and Chat Completions, Anthropic's Messages, Google's generateContent; 2026-11). A tool is held by
# the converse rule: only one the client runs itself passes (:func:`_tool_label`), any other is ``tools.<type>``.
BODY_FIELDS = frozenset({"previous_response_id", "conversation", "prompt", "web_search_options", "mcp_servers",
                         "container", "cached_content", "file_id", "file_url", "file_data"})


def _key(name: str) -> str:
    """A body key as an upstream's parser might match it: without ``_`` or ``-``, case folded (Google's takes both
    ``cachedContent`` and ``cached_content``; a case-insensitive decoder takes any case)."""
    return name.replace("_", "").replace("-", "").casefold()


def _label(name: str) -> str:
    """A tool's type or key as a ``tools.<type>`` label: snake case, its date suffix out (``web_search_20250305``)."""
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()
    return "tools." + (re.sub(r"[^a-z0-9_]+", "_", re.sub(r"_\d{8}$", "", snake)).strip("_") or "untyped")


# Each model-call route's body (:func:`_operation`'s ``model`` endpoints): its top-level fields of :data:`BODY_FIELDS`;
# where its content lies (the top-level keys whose values hold it) and the keys to descend through there (never a tool
# call's own arguments, whose keys are the model's); and the keys there that name a file by reference in place of
# content the request carries.
_ROUTES: dict[str, tuple[dict[str, str], tuple[str, ...], frozenset[str], dict[str, str]]] = {
    "responses": ({"previousresponseid": "previous_response_id", "conversation": "conversation", "prompt": "prompt"},
                  ("input",), frozenset({"content", "output"}), {"fileid": "file_id", "fileurl": "file_url"}),
    "chat": ({"websearchoptions": "web_search_options"}, ("messages",), frozenset({"content", "file"}),
             {"fileid": "file_id"}),
    "messages": ({"mcpservers": "mcp_servers", "container": "container"}, ("messages", "system"),
                 frozenset({"content", "source"}), {"fileid": "file_id"}),
    "gemini": ({"cachedcontent": "cached_content"}, ("contents", "systeminstruction"),
               frozenset({"parts", "functionresponse"}), {"filedata": "file_data"}),
}


def _route(endpoint: str) -> str | None:
    """Which of :data:`_ROUTES` a model call's endpoint (relative to the upstream's prefix) is."""
    if endpoint == "/responses":
        return "responses"
    if endpoint in ("/chat/completions", "/completions"):
        return "chat"
    if endpoint == "/messages":
        return "messages"
    return "gemini" if endpoint.startswith("/models/") else None


def _tool_label(route: str, tool: Any) -> list[str]:
    """The labels of a tool the client does not run itself: none for a function (OpenAI's ``function`` or ``custom``,
    Anthropic's untyped or ``custom``, Google's ``functionDeclarations``). Every key an upstream might read as the
    tool's type counts, so a tool is a function only when each says so (#551's review, m2). Raises ``ValueError`` on a
    tool that is not an object."""
    if not isinstance(tool, dict):
        raise ValueError("a tool is not an object")
    if route == "gemini":
        return [_label(k) for k in tool if _key(k) != "functiondeclarations"]
    kinds = [v for k, v in tool.items() if _key(k) == "type"]
    if not kinds:
        return [] if route == "messages" else ["tools.untyped"]
    return [_label(kind) if isinstance(kind, str) else "tools.untyped" for kind in kinds
            if kind not in ("function", "custom")]


def _walk(node: Any, descend: frozenset[str], named: Mapping[str, str], found: set[str]) -> None:
    """Add to ``found`` the label of each key of ``named`` in ``node``, through lists and the keys of ``descend``.
    Iterative: a body nested as deep as the parser takes is walked whole (#551's review, m4)."""
    stack = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            for name, value in item.items():
                key = _key(name)
                if key in named:
                    found.add(named[key])
                if key in descend:
                    stack.append(value)


def body_fields(endpoint: str, document: Mapping[str, Any]) -> set[str]:
    """The fields of :data:`BODY_FIELDS`, and the ``tools.<type>`` of each tool the client does not run itself, that a
    model call's JSON body uses. Raises ``ValueError`` on a ``tools`` that is not a list of objects."""
    route = _route(endpoint)
    if route is None:
        return set()
    top, roots, descend, named = _ROUTES[route]
    found: set[str] = set()
    for name, value in document.items():
        key = _key(name)
        if key in top:
            found.add(top[key])
        if key in roots:
            _walk(value, descend, named, found)
        if key == "tools":
            if not isinstance(value, list):
                raise ValueError("tools is not a list")
            for tool in value:
                found.update(_tool_label(route, tool))
    return found


def opted_body_fields(entries: Collection[str]) -> frozenset[str]:
    """The fields a provider's ``containment.network.relay_body_fields`` entries opt in: each one of
    :data:`BODY_FIELDS` or a ``tools.<type>``. Raises ``ValidationFailed`` (reason ``bad_relay_body_field``) on any
    other, so a misspelt entry never opts nothing in silently."""
    for entry in entries:
        if not isinstance(entry, str) or not (entry in BODY_FIELDS or _BODY_FIELD_ENTRY.fullmatch(entry)):
            raise ValidationFailed(f"relay body field {entry!r} is not one the relay holds a model call's body to: "
                                   f"one of {', '.join(sorted(BODY_FIELDS))}, or tools.<type> (such as "
                                   "tools.web_search)", entry=str(entry), reason="bad_relay_body_field")
    return frozenset(entries)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A JSON object whose keys are each given once: parsers differ on which of two of a name they keep."""
    out = dict(pairs)
    if len(out) != len(pairs):
        raise ValueError("a JSON object repeats a key")
    return out


def _constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


# A byte's step in nesting depth: +1 for ``[`` and ``{``, -1 for ``]`` and ``}``; every other byte is dropped first
_NESTING_STEP = [0] * 256
_NESTING_STEP[ord("[")] = _NESTING_STEP[ord("{")] = 1
_NESTING_STEP[ord("]")] = _NESTING_STEP[ord("}")] = -1
_NOT_BRACKET = bytes(b for b in range(256) if not _NESTING_STEP[b])
# Every byte but a quote and the JSON structure, dropped to leave a body's skeleton (:func:`_scan`)
_NOT_SKELETON = bytes(b for b in range(256) if b not in b'"[]{},:')
# Implementation bound: how much of a skeleton :func:`_scan` splits at once, so what the scan holds beyond its copies is
# bounded by a constant, never by the body's number of strings; and what it holds for each byte of a piece at most
# (its pieces, their list, and the join's view of each; the nesting levels: measured about 50, 2026-11-24)
SCAN_CHUNK = 64 * 1024
SCAN_CHUNK_BYTES = 64


def _scan(body: bytes | bytearray) -> tuple[int, int]:
    """What a body's parse would hold, as an upper estimate, and how deep its arrays and objects nest, read without
    parsing it and without recursion, so the relay checks both before it parses (#551's review, m3 and m4).

    The estimate (m3): its text, at the width Python stores it at (one byte a character, two from U+0100, four from
    U+10000), its strings' text again at the width they may take (a ``\\u`` escape may widen one),
    :data:`PARSE_VALUE_BYTES` for each value, counted from its ``[``, ``{``, ``,`` and ``:`` outside strings, and
    :data:`PARSE_BASE_BYTES`. The scan itself holds at most two copies of the body beside it, each at most its size,
    and what one :data:`SCAN_CHUNK` of its skeleton splits into (:data:`SCAN_CHUNK_BYTES` for each byte of it), all
    held by its caller before it starts (:func:`_scan_hold`); the estimate counts the chunk's share too."""
    size = len(body)
    # A string's escapes out first: each escaped backslash (left to right, so a run of them pairs as a parser reads
    # it), then each escaped quote; then all but its quotes and structure. Each copy is at most the body's size, and
    # at most two are held at once. The skeleton is bytes, so a piece of one byte or none is a shared object when it
    # is split out (a regex over strings would hold state or a new piece for each, as many as the body has)
    skeleton = bytes(body.replace(b"\\\\", b"").replace(b'\\"', b"").translate(None, _NOT_SKELETON))
    text = 4 if re.search(rb"[\xf0-\xf4]", body) else 2 if re.search(rb"[\xc4-\xef]", body) else 1
    strings = 4 if text == 4 or re.search(rb"\\u[dD][89abAB]", body) else \
        2 if text == 2 or re.search(rb"\\u(?!00)", body) else 1
    values, depth, level, inside = 1, 0, 0, False
    for at in range(0, len(skeleton), SCAN_CHUNK):  # once escapes are out, every other piece lies outside a string
        pieces = skeleton[at:at + SCAN_CHUNK].split(b'"')
        outside = b"".join(pieces[1 if inside else 0::2])
        inside ^= len(pieces) % 2 == 0  # an odd number of quotes in this chunk
        del pieces
        values += sum(outside.count(c) for c in b"[{,:")
        brackets = outside.translate(None, _NOT_BRACKET)
        # A running maximum, one level at a time: never a list of them (#551's quick check, q3)
        depth = max(depth, max(itertools.accumulate(map(_NESTING_STEP.__getitem__, brackets), initial=level)))
        level += brackets.count(b"[") + brackets.count(b"{") - brackets.count(b"]") - brackets.count(b"}")
    del skeleton
    chunk = SCAN_CHUNK_BYTES * min(size, SCAN_CHUNK)
    return size * (text + strings) + values * PARSE_VALUE_BYTES + PARSE_BASE_BYTES + chunk, depth


def _scan_hold(size: int) -> int:
    """What :func:`_scan` holds beside a body of ``size`` bytes, whatever the body: two copies of it, and one
    :data:`SCAN_CHUNK` of its skeleton split up. Its caller holds it before the scan (#551's quick check, q2)."""
    return 2 * size + SCAN_CHUNK_BYTES * min(size, SCAN_CHUNK)


def _document(body: bytes | bytearray) -> dict[str, Any]:
    """A model call's body as one JSON object, strictly: UTF-8 with no byte-order mark, no repeated key, no NaN or
    Infinity (its nesting is checked before, by :func:`_scan`). Raises ``ValueError`` on anything else."""
    try:
        document = json.loads(body.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant)
    except RecursionError:
        raise ValueError("the JSON nests too deeply") from None
    if not isinstance(document, dict):
        raise ValueError("the body is not a JSON object")
    return document


class _Refused(Exception):
    """An answer the relay gives itself. ``outcome`` is the entry's: ``refused``, or ``unknown`` for an answer given
    once the request may have reached the upstream (:data:`OUTCOMES`)."""

    def __init__(self, status: int, reason: str, message: str, *, outcome: str = "refused") -> None:
        super().__init__(message)
        self.status, self.reason, self.message, self.outcome = status, reason, message, outcome

    def response(self) -> bytes:
        body = self.message.encode()
        head = (f"HTTP/1.1 {self.status} {_PHRASES[self.status]}\r\nX-AEW-Refusal: {self.reason}\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n")
        return head.encode() + body


def unreachable_answer() -> str:
    """The fixed answer the in-sandbox shim gives on a relay leg whose relay takes no connection
    (:data:`RELAY_UNREACHABLE`), in the relay's own refusal form. The shim imports nothing of AEW, so ``netns`` puts it
    in the leg's spec (``netns.shim_spec``)."""
    return _Refused(502, RELAY_UNREACHABLE, "AEW: the provider relay is not taking connections: the run is ending, or "
                    "its supervisor stopped. This request was not sent to the provider").response().decode("latin-1")


class ProviderRelay(Service):
    """Serves ``listener`` for one run's provider. ``credentials`` maps each sentinel to the value it stands for, or
    ``resolve`` gives that map and the headers to set for each request (raising :class:`Unavailable` when it has
    none to give); ``proxy`` is the operator's HTTP proxy, if any. ``tls`` is the upstream's context: a provider's
    client certificate's (``client_cert.context``, with ``client`` the files it was read from, for the answers on a
    failed handshake), else the system's default verifying context; tests give their own. ``connect`` is a seam for
    tests (a plain connect to the upstream's name). ``record`` takes each request's entry (see the module's "The
    record"), with ``route`` (the provider) and ``login`` (``key``, ``oauth`` or ``none``) in it; a record that fails
    is counted (``record_failed``) and never fails the request. ``operations`` are the operations the operator's
    adopted policy adds for this provider (:func:`listed_operations`'s entries); the relay forwards no other.
    ``body_fields`` are the model-call body fields it opts in for this provider (:func:`opted_body_fields`'s entries);
    the relay refuses a model call whose body uses any other of :func:`body_fields`. ``max_body``, ``max_held``,
    ``max_active`` and ``stream_timeout`` are the relay's bounds (:data:`MAX_BODY`, :data:`MAX_HELD`,
    :data:`MAX_ACTIVE`, :data:`STREAM_TIMEOUT`), the host's to set; ``policy_sha256`` is the sha256 of the execution
    policy the relay was started from, for its record."""

    name = "aew-relay"

    def __init__(self, upstream: Upstream, credentials: Mapping[str, str], *, listener: socket.socket | None = None,
                 proxy: Proxy | None = None, connect: Connector = _connect, tls: ssl.SSLContext | None = None,
                 head_timeout: float = HEAD_TIMEOUT, connect_timeout: float = CONNECT_TIMEOUT,
                 body_timeout: float = BODY_TIMEOUT, resolve: Callable[[], Grant] | None = None,
                 client: ClientCert | None = None, record: Callable[[dict[str, Any]], None] | None = None,
                 route: str | None = None, login: str = "none", login_headers: Collection[str] = (),
                 issued: Collection[str] = (), sources: Mapping[str, str] | None = None,
                 operations: Collection[str] = (), body_fields: Collection[str] = (), max_body: int = MAX_BODY,
                 max_held: int = MAX_HELD, max_active: int = MAX_ACTIVE, stream_timeout: float = STREAM_TIMEOUT,
                 policy_sha256: str | None = None) -> None:
        listed = listed_operations(operations, resolved=resolve is not None)  # refused before anything is served
        opted = opted_body_fields(body_fields)
        super().__init__(listener=listener)
        self.upstream, self.proxy = upstream, proxy
        self.listed, self.opted = listed, opted
        self._credentials = dict(credentials)
        self.sources = dict(sources or {})  # sentinel to logical source name; only the name goes in a record
        self._resolve = resolve
        self.login_headers = frozenset(h.lower() for h in login_headers)
        self.own = frozenset(credentials) | frozenset(issued)  # the sentinels this relay issued (a grant's included)
        # The sentinels the run issued to its other relays and variables (netns sets it once they all exist): one of
        # them here is another provider's placeholder, refused as such
        self.foreign: frozenset[str] = frozenset()
        self._record, self.route, self.login = record, route, login
        self._retryable_pending = False
        self._connect, self._tls = connect, tls
        self.client = client
        self.head_timeout, self.connect_timeout, self.body_timeout = head_timeout, connect_timeout, body_timeout
        self.max_body, self.max_active, self.stream_timeout = max_body, max_active, stream_timeout
        self.max_held = max_held
        self._active = 0  # the requests in progress (:meth:`_admit`)
        self._held = 0  # the bytes of model-call bodies held now (:meth:`_reserve`)
        self.policy_sha256 = policy_sha256
        self.client_sha256: str | None = None
        if client is not None:  # the leaf the context was loaded from, read once: its digest only, never the key
            from aew.harness.containment import client_cert

            self.client_sha256 = client_cert.public_snapshot(client)["sha256"]

    def start(self) -> ProviderRelay:
        super().start()
        return self

    def close(self) -> None:
        super().close()
        self._credentials.clear()
        self.sources.clear()
        self._resolve = None

    def _grant(self) -> Grant:
        resolve = self._resolve
        if resolve is None:
            return self._credentials, {}
        try:
            grant = resolve()
            with self._lock:
                self._retryable_pending = False
            return grant
        except Unavailable as exc:
            self._count(f"credential:{exc.cause}" + ("_retryable" if exc.retryable else ""))
            with self._lock:
                self._retryable_pending = exc.retryable
            if exc.cause == "unreadable" and exc.retryable:
                raise _Refused(503, "credential_unreadable", str(exc)) from None
            raise _Refused(401, "credential_unavailable", str(exc)) from None

    def _admit(self) -> bool:
        """Take one of the relay's :data:`MAX_ACTIVE` places, or say there is none."""
        with self._lock:
            if self._active >= self.max_active:
                return False
            self._active += 1
            return True

    def _leave(self) -> None:
        with self._lock:
            self._active -= 1

    def _reserve(self, n: int) -> None:
        """Hold ``n`` more bytes of a model call's body within :attr:`max_held`, or refuse the request."""
        with self._lock:
            if self._held + n > self.max_held:
                raise _Refused(503, RELAY_BUSY, f"the provider relay is holding {self.max_held} bytes of request "
                               "bodies, its bound, so this request was not sent to the provider. Send it again once "
                               "one of them has ended")
            self._held += n

    def _release(self, n: int) -> None:
        with self._lock:
            self._held -= n

    def _too_large(self) -> _Refused:
        return _Refused(413, REQUEST_TOO_LARGE, f"the request's body exceeds the provider relay's bound of "
                        f"{self.max_body} bytes, so it was not sent to the provider whole. Send a smaller request")

    def retryable_pending(self) -> bool:
        with self._lock:
            return self._retryable_pending

    def _check_target(self, target: str) -> None:
        """Refuse a target whose path is outside the upstream's prefix, or spelled so that an upstream might read it
        as another path (an empty, ``.`` or ``..`` segment, a percent escape, a fragment)."""
        path = target.partition("?")[0]
        pattern = _RESOLVED_PATH if self._resolve is not None else _KEYED_PATH
        if (not path.startswith(f"{self.upstream.path}/") or not pattern.fullmatch(path) or not _unambiguous(path)
                or "#" in target or any(c <= " " or c == "\x7f" for c in target)):
            whose = "the stored login's upstream path" if self._resolve is not None else \
                f"the run's provider upstream path ({self.upstream.path or '/'})"
            raise _Refused(403, OUTSIDE_UPSTREAM_PATH, "the provider relay takes only unambiguous paths under "
                           f"{whose}: this request was not sent. Address the provider's API at the base URL AEW gave "
                           "the harness")

    def _check_operation(self, method: str, operation: str) -> None:
        """Refuse an operation outside the relay's policy: :data:`DEFAULT_OPERATIONS` and what the policy lists."""
        if operation in DEFAULT_OPERATIONS or operation == POLICY_OPERATION:
            return
        route = self.route or "<provider>"
        raise _Refused(403, OPERATION_NOT_PERMITTED, f"the provider relay forwards only the operations its policy "
                       f"allows for {route}: model calls and the model list, and any the operator's adopted execution "
                       f"policy names in containment.network.relay_operations.{route}. This {method} request was not "
                       "sent to the provider. If the run needs it, the operator names it there as METHOD /path (the "
                       "path under the provider's upstream), adopts the policy and starts the run again")

    def _check_body(self, endpoint: str, body: bytearray, entry: dict[str, Any], reserve: Callable[[int], None],
                    release: Callable[[int], None]) -> None:
        """Refuse a model call's body the relay cannot hold to its scope (:data:`BODY_UNREADABLE`), or one that uses a
        field the policy does not opt in for the provider (:data:`BODY_FIELD_NOT_PERMITTED`, naming each). Its parse
        is held within :attr:`max_held` (:func:`_scan`) while it is checked. An empty body has no field, and
        goes as it came."""
        if not body:
            return
        held = _scan_hold(len(body))  # what the scan holds, before it starts
        reserve(held)
        try:
            cost, depth = _scan(body)
            reserve(max(cost - held, 0))
            held = max(cost, held)
            if depth > MAX_NESTING:  # before the parser, whose own limit differs between interpreters
                raise ValueError(f"the JSON nests deeper than {MAX_NESTING} levels")
            fields = body_fields(endpoint, _document(body))
        except (ValueError, RecursionError) as exc:
            raise _Refused(400, BODY_UNREADABLE, f"the provider relay holds a model call's body to the operations "
                           f"its policy allows, so reads it as one JSON object (UTF-8, each key once), and could not "
                           f"read this one ({exc}): it was not sent to the provider") from None
        finally:  # the parse is over: what it held is free again
            release(held)
        refused = sorted(fields - self.opted)
        if not refused:
            return
        entry["body_fields"] = refused
        route = self.route or "<provider>"
        raise _Refused(403, BODY_FIELD_NOT_PERMITTED, f"the provider relay holds a model call's body to the operations "
                       f"its policy allows for {route}, and this body uses {', '.join(refused)}, which that policy "
                       "does not opt in, so it was not sent to the provider. If the run needs it, the operator names "
                       f"it in the adopted execution policy's containment.network.relay_body_fields.{route}, adopts "
                       "the policy and starts the run again")

    def handle(self, conn: socket.socket) -> None:
        """Serve one request on ``conn`` to its end, and close it."""
        if not self._track(conn):
            conn.close()
            return
        admitted = False
        upstream: socket.socket | None = None
        answered = False  # once the response's head has gone to the client, nothing else may be sent it
        entry: dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "route": self.route,
                                 "destination": f"{self.upstream.host}:{self.upstream.port}", "login": self.login,
                                 "swap": "none", "operation": "unknown", "outcome": None, "reason": None,
                                 "status": None, "answered": None}
        entry.update(configured_sources=sorted(set(self.sources.values())), swapped_sources=[],
                     client_certificate_configured=self.client is not None,
                     upstream_headers_written=False, transport="not_established", ended=None,
                     request_id=secrets.token_hex(8), policy_sha256=self.policy_sha256,
                     client_certificate_sha256=self.client_sha256)
        held: list[str] = []  # this request's credential values, kept out of the record's excerpt
        excerpt: _Excerpt | None = None
        # What this request holds within max_held (_reserve): its body until it has gone upstream, and the estimate of
        # its parse while it is checked (#551's review, m5)
        reserved = 0

        def reserve(n: int) -> None:
            nonlocal reserved
            if reserved + n > self.max_held:  # more than the relay holds for all its requests: it never would
                raise _Refused(413, REQUEST_TOO_LARGE, f"the request's body is too large for the provider relay to "
                               f"hold to its scope within its bound of {self.max_held} bytes, so it was not sent to "
                               "the provider. Send a smaller request")
            self._reserve(n)
            reserved += n

        def release(n: int) -> None:
            nonlocal reserved
            self._release(n)
            reserved -= n

        try:
            admitted = self._admit()
            if not admitted:  # before its head is read: a sandbox cannot make the relay hold more than its bound
                raise _Refused(503, RELAY_BUSY, f"the provider relay is serving {self.max_active} requests, its bound, "
                               "so this request was not sent to the provider. Send it again once one of them has ended")
            head, early = _read_head(conn, self.head_timeout)
            method, target, headers = self._request(head)
            entry["operation"] = _operation(method, target, self.upstream.path, self.listed)
            if entry["operation"] not in DEFAULT_OPERATIONS and entry["operation"] != POLICY_OPERATION:
                # What the operator would list to allow it (the path check has passed): the method, and the endpoint
                # relative to the upstream's prefix, without its query
                entry.update(method=method, endpoint=target.partition("?")[0][len(self.upstream.path):])
            self._check_operation(method, entry["operation"])  # before the grant and the connect: nothing connected
            framing = _framing(headers)
            if framing[0] == "length" and framing[1] > self.max_body:
                raise self._too_large()  # nothing connected; a chunked body is counted as it comes (_send_body)
            credentials, extra = self._grant()  # before anything is connected: a refusal connects nothing
            held = [*credentials.values(), *extra.values()]
            try:
                rewritten, swapped = self._rewrite(headers, credentials, extra)
                _placeholders(target, credentials, self.foreign)
            except _Refused as refused:
                if refused.reason in (STALE_PLACEHOLDER, OTHER_PLACEHOLDER):
                    entry["swap"] = "refused_unknown_placeholder"
                raise
            entry["swap"] = "swapped" if swapped else "none"
            entry["swapped_sources"] = sorted(swapped)
            body: bytearray | None = None
            if entry["operation"] == "model":  # its body is held to its scope: read whole, before anything connects
                if any(k.lower() == "content-encoding" and v.strip().lower() not in ("", "identity")
                       for k, v in headers):
                    raise _Refused(400, BODY_UNREADABLE, "the provider relay holds a model call's body to the "
                                   "operations its policy allows, so reads it, and takes it only without a "
                                   "Content-Encoding: it was not sent to the provider")
                if framing[0] == "length":  # held before a 100 Continue asks the client for it
                    reserve(framing[1])
            # Only to HTTP/1.1 (_request has checked the version): no 1xx goes to an HTTP/1.0 client, which ignores the
            # expectation, and its body is read all the same (RFC 9110 §15.2, §10.1.1; the review of #587, m1)
            http11 = head.split(b"\r\n", 1)[0].endswith(b" HTTP/1.1")
            if http11 and any(k.lower() == "expect" and v.lower() == "100-continue" for k, v in headers):
                conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
            if entry["operation"] == "model":
                body = self._read_whole(conn, framing, early, reserve)
                endpoint = target.partition("?")[0][len(self.upstream.path):]
                self._check_body(endpoint, body, entry, reserve, release)
                # Sent as it was read, framed by its length: the request's own framing is not sent on
                rewritten = [(k, v) for k, v in rewritten if k.lower() not in ("content-length", "transfer-encoding")]
                rewritten.insert(-1, ("Content-Length", str(len(body))))
            upstream = self._connect_upstream()
            if isinstance(upstream, ssl.SSLSocket):
                verified = upstream.context.check_hostname and upstream.context.verify_mode == ssl.CERT_REQUIRED
                entry["transport"] = "tls_verified" if verified else "tls_unverified"
            else:
                entry["transport"] = "http"
            if not self._track(upstream):
                entry.update(outcome="refused", reason="closed")
                return
            wire_head = _head(f"{method} {target} HTTP/1.1", rewritten)
            entry["upstream_headers_written"] = None  # on a partial write sendall cannot say how many bytes left
            upstream.sendall(wire_head)
            entry["upstream_headers_written"] = True
            if body is None:
                self._send_body(conn, upstream, framing, early)
            else:
                if body:
                    upstream.sendall(body)
                body = None  # the held body is not kept while its response streams, nor held within max_held
                release(reserved)
            deadline = time.monotonic() + self.stream_timeout
            reader, response = self._relay_head(conn, upstream, deadline)
            status = _status_code(response)
            tracked = _Body(response, method)
            failed = status is None or not 200 <= status < 300
            if failed:
                excerpt = _Excerpt(response)
            # On a route whose grant holds a credential, a failed answer's body is held, and the grant's credential
            # values taken out, before it goes on (:meth:`_failed_answer`); a 2xx answer, and any answer on a route
            # that holds none, streams as it came
            holding = failed and bool(_Scrub(held).values) and tracked.kind != "none"
            ended: str | None = None
            clean: _Clean | None = None
            if not holding:
                conn.sendall(_close_head(response))
            answered = True  # from here nothing of the relay's own may go to the client: it would read as the answer
            self._count("allowed")
            entry.update(outcome="forwarded", status=status, answered=status)
            if failed:  # "allowed" means only not blocked; this is how it went
                self._count(f"upstream_status:{status}")
            if holding:
                assert excerpt is not None
                ended, clean = self._failed_answer(conn, upstream, reader, response, tracked, excerpt, held,
                                                   deadline, http11)
            if ended is None:
                ended = self._stream(conn, upstream, reader, tracked, excerpt, deadline, clean)
            entry["ended"] = ended
            settled = status is not None and status >= 300  # the provider answered no: a cut body changes nothing
            if entry["ended"] in ("upstream_broken", "stream_timeout") and not settled:  # it may have done the call
                reason = UPSTREAM_OUTCOME_UNKNOWN if entry["ended"] == "upstream_broken" else STREAM_TIMEOUT_REASON
                entry.update(outcome="unknown", reason=reason)
                self._count(reason)
        except _Refused as refused:
            if refused.reason == STREAM_TIMEOUT_REASON:  # no response head by the bound (_relay_head)
                entry["ended"] = "stream_timeout"
            if not answered:
                self._answer(conn, refused, entry)
        except ssl.SSLError as exc:  # the upstream's TLS: in the handshake, or (TLS 1.3) an alert on the first read
            if not answered:
                refused = _tls_refused(exc, self.upstream, self.client)
                if refused.reason == "tls_failed" and entry["upstream_headers_written"] is not False:
                    refused = self._unknown()  # not a refused handshake: the request may have been read
                self._answer(conn, refused, entry)
        except OSError:
            if answered:  # only the client is written to unguarded once the response's head has gone
                entry["ended"] = "client_gone"
            elif entry["upstream_headers_written"] is False:  # not one byte of the request went upstream
                self._answer(conn, _Refused(502, "upstream_unreachable", "the provider relay could not reach "
                                            f"{self.upstream.url}, the run's fixed provider upstream: this request "
                                            "was not sent"), entry)
            else:
                self._answer(conn, self._unknown(), entry)
        except Exception:  # anything else is counted, and answered with a fixed 502 when nothing was relayed yet
            self._count("relay_error")
            if not answered:
                self._answer(conn, _Refused(502, "relay_error", "the provider relay could not serve this request")
                             if entry["upstream_headers_written"] is False else self._unknown(), entry)
        finally:
            if admitted:
                self._leave()
            if reserved:
                self._release(reserved)
            if upstream is not None:
                self._untrack(upstream)
            self._untrack(conn)
            if excerpt is not None:
                entry["excerpt"] = excerpt.text(held)
            self._write(entry)

    def _unknown(self) -> _Refused:
        return _Refused(502, UPSTREAM_OUTCOME_UNKNOWN, f"the connection to {self.upstream.url} broke after the request "
                        "was sent, or as it was: the provider may have accepted it, and the relay does not send it "
                        "again. Check the provider before repeating it", outcome="unknown")

    def _write(self, entry: dict[str, Any]) -> None:
        if self._record is None:
            return
        try:
            self._record(entry)
        except Exception:  # the record is evidence of the request, never a reason to fail it
            self._count("record_failed")

    def _answer(self, conn: socket.socket, refused: _Refused, entry: dict[str, Any] | None = None) -> None:
        if entry is not None:
            entry.update(outcome=refused.outcome, reason=refused.reason, answered=refused.status)
        self._count(refused.reason)
        try:
            conn.settimeout(self.head_timeout)
            conn.sendall(refused.response())
            close_after_response(conn, REFUSAL_DRAIN_S)
        except OSError:
            pass

    def _request(self, head: bytes) -> tuple[str, str, list[tuple[str, str]]]:
        lines = head.split(b"\r\n")
        try:
            method, target, version = lines[0].decode("ascii").split(" ")
        except (UnicodeDecodeError, ValueError):
            raise _Refused(400, "bad_request", "the request line is not METHOD /path HTTP/1.1") from None
        if not TOKEN.fullmatch(method) or version not in ("HTTP/1.1", "HTTP/1.0"):
            raise _Refused(400, "bad_request", "the request line is not METHOD /path HTTP/1.1")
        if self._resolve is None and (not target.startswith("/") or any(c <= " " or c == "\x7f" for c in target)):
            raise _Refused(400, "not_origin_form", "the provider relay takes a path only (/v1/...): it always "
                           "connects to the run's fixed provider upstream, which a request cannot name")
        self._check_target(target)
        try:  # a value with a control character is refused here, before anything connects (RFC 9110 §5.5)
            headers = fields(lines[1:])
        except BadField as exc:
            raise _Refused(400, "bad_header", str(exc)) from None
        if any(k.lower() == "upgrade" for k, _ in headers):
            raise _Refused(501, "upgrade", "the provider relay serves plain HTTP requests, not a protocol upgrade "
                           "(WebSocket); AEW sets the provider's transport to http")
        return method, target, headers

    def _rewrite(self, headers: list[tuple[str, str]], credentials: Mapping[str, str],
                 extra: Mapping[str, str]) -> tuple[list[tuple[str, str]], set[str]]:
        """Hop-by-hop headers (and any the client's ``Connection`` names) out; ``Host`` the upstream's; the
        credential in for its sentinel, in a credential header only; the grant's headers in place of any of the same
        name, and the client's of a name in ``login_headers`` dropped; ``Connection: close``. A sentinel this relay did
        not issue, in any header kept, is refused (:func:`_placeholders`). Returns the headers and the
        logical sources swapped into them."""
        named = {t.strip().lower() for k, v in headers if k.lower() == "connection" for t in v.split(",")}
        replaced = {k.lower() for k in extra} | self.login_headers
        out = [("Host", self.upstream.authority)]
        swapped: set[str] = set()
        for name, value in headers:
            low = name.lower()
            if low in HOP_BY_HOP or low in named or low == "host" or low in replaced:
                continue
            if low in CREDENTIAL_HEADERS:
                value, one = _credential(value, credentials, self.foreign)
                if one is not None:
                    swapped.add(self.sources.get(one, "unknown"))
            else:
                _placeholders(value, credentials, self.foreign)
            out.append((name, value))
        out += list(extra.items())
        out.append(("Connection", "close"))
        return out, swapped

    def _connect_upstream(self) -> socket.socket:
        if self._closed.is_set():
            raise _Refused(502, "closed", "the provider relay is closing: the run is ending")
        up = self.upstream
        if self.proxy is None:
            sock = self._connect(up.host, up.port, self.connect_timeout)
        else:
            sock = self._connect(self.proxy.host, self.proxy.port, self.connect_timeout)
            try:
                self._tunnel(sock)
            except BaseException:
                sock.close()
                raise
        if up.scheme == "https":
            context = self._tls or _tls_context()
            sock.settimeout(self.connect_timeout)
            try:
                sock = context.wrap_socket(sock, server_hostname=up.host)
            except BaseException:
                sock.close()
                raise
        sock.settimeout(None)
        return sock

    def _tunnel(self, sock: socket.socket) -> None:
        """Ask the operator's proxy for a tunnel to the upstream; anything but a 200 is the upstream unreachable."""
        assert self.proxy is not None
        host, port = self.upstream.host, self.upstream.port
        target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
        if self.proxy.auth:
            lines.append(f"Proxy-Authorization: {self.proxy.auth}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        try:
            head, _ = _read_head(sock, self.connect_timeout)
        except _Refused as exc:
            raise OSError(f"the operator's proxy gave no answer to CONNECT {target}: {exc.message}") from None
        status = head.split(b"\r\n", 1)[0]
        if status.split(b" ")[1:2] != [b"200"]:
            raise OSError(f"the operator's proxy refused CONNECT {target}: {status[:80]!r}")

    def _send_body(self, conn: socket.socket, upstream: socket.socket, framing: tuple[str, int],
                   early: bytes) -> None:
        """The request body, as its head frames it: ``Content-Length`` bytes, or chunks to the last one and its
        trailer. What the client sends beyond it is not relayed (one request per connection). :attr:`max_body` bounds
        every byte of a chunked body as it goes upstream: its size lines with any extension, its data, each chunk's
        CRLF and its trailer section. A chunk that would pass it is refused at its size line, and a trailer line at
        that line, neither of them sent: the upstream never gets the request whole. A chunk's data not followed by
        exactly CRLF is refused as malformed. Chunk extensions and trailer fields are held to the same field-value rule
        as the head's (RFC 9112 §7.1.1, §7.1.2; RFC 9110 §5.5): a size line with a control character other than HTAB
        is refused ``bad_chunk``, a trailer line that is not a field ``bad_header``, neither of them sent."""
        self._body(conn, framing, early, upstream.sendall, framed=True)

    def _read_whole(self, conn: socket.socket, framing: tuple[str, int], early: bytes,
                    reserve: Callable[[int], None]) -> bytearray:
        """A model call's body, read whole and unframed (its data alone), within :attr:`max_body` as
        :meth:`_send_body` bounds it, each byte held within :attr:`max_held` before it is read: a chunked body's
        through ``reserve`` as its size lines declare them (a ``Content-Length`` is held before, by :meth:`handle`)."""
        out = bytearray()
        self._body(conn, framing, early, out.extend, framed=False, reserve=reserve)
        return out

    def _body(self, conn: socket.socket, framing: tuple[str, int], early: bytes, sink: Callable[[bytes], Any], *,
              framed: bool, reserve: Callable[[int], None] | None = None) -> None:
        """The request body's bytes to ``sink``: with its chunked framing (``framed``), or its data alone."""
        kind, length = framing
        reader = _Reader(conn, early, self.body_timeout)
        if kind == "length":
            left = length
            while left:
                data = reader.read(min(left, CHUNK))
                sink(data)
                left -= len(data)
        elif kind == "chunked":
            total = 0

            def counted(n: int) -> None:  # before the bytes go: one that would pass the bound is never sent
                nonlocal total
                total += n
                if total > self.max_body:
                    raise self._too_large()
                if reserve is not None:
                    reserve(n)

            while True:
                line = reader.line()
                size = _chunk_size(line[:-2])  # without its CRLF, which reader.line() ends every line with
                if size is None:
                    raise _Refused(400, "bad_chunk", "the request body's chunked encoding is malformed")
                counted(len(line) + (size + 2 if size else 0))  # the whole chunk, as its size line declares it
                if framed:
                    sink(line)
                if size == 0:
                    while True:  # the trailer section, to its empty line
                        trailer = reader.line()
                        counted(len(trailer))
                        if trailer != b"\r\n":  # a trailer field is held to a header's rule (RFC 9112 §7.1.2)
                            try:
                                fields([trailer[:-2]])
                            except BadField as exc:
                                raise _Refused(400, "bad_header", f"a trailer field: {exc}") from None
                        if framed:
                            sink(trailer)
                        if trailer == b"\r\n":
                            return
                left = size
                while left:
                    data = reader.read(min(left, CHUNK))
                    sink(data)
                    left -= len(data)
                end = reader.read(2)
                if len(end) < 2:
                    end += reader.read(1)
                if end != b"\r\n":
                    raise _Refused(400, "bad_chunk", "a chunk's data is not followed by CRLF")
                if framed:
                    sink(end)

    def _relay_head(self, conn: socket.socket, upstream: socket.socket,
                    deadline: float | None = None) -> tuple[_Reader, bytes]:
        """The response's final head, its interim 1xx heads sent on first, as they come. Returns the reader and the
        final head as the upstream sent it, which its caller sends on (:meth:`handle`). One that has not come by
        ``deadline`` is answered 504 (:data:`STREAM_TIMEOUT_REASON`, outcome ``unknown``: the request was sent)."""
        reader = _Reader(upstream, b"", None)
        while True:
            head = reader.head(deadline)
            status = head.split(b"\r\n", 1)[0].split(b" ")
            if not (len(status) > 1 and status[1].startswith(b"1") and status[1] != b"101"):
                return reader, head
            conn.sendall(head)

    def _failed_answer(self, conn: socket.socket, upstream: socket.socket, reader: _Reader, response: bytes,
                       body: _Body, excerpt: _Excerpt, held: list[str], deadline: float,
                       http11: bool) -> tuple[str | None, _Clean | None]:
        """Send a failed answer on with the request's credential values (``held``) out of its body. Its first bytes
        are held first (:meth:`_hold`): a body whole in them that holds none, or in a coding the relay does not read,
        goes on exactly as it came. One that holds one goes on without it (:class:`_Clean`), framed by its new length
        when it is whole; one that is not whole yet goes on cleaned as it comes. Returns how the body ended, when it
        has, and what cleans the rest, when it streams on (:meth:`_stream`)."""
        raw, payload, ended = self._hold(upstream, reader, body, excerpt, deadline)
        clean: _Clean | None = None
        first = b""
        if excerpt.coding in READABLE_CODINGS:
            try:
                clean = _Clean(excerpt.coding, held, chunked=http11)
                first = clean.take(payload)
                if ended == "complete":
                    first += clean.end()
            except zlib.error:  # not what its coding says: a client cannot read it either
                clean = None
        if clean is None or (ended is not None and not clean.scrub.found):
            conn.sendall(_close_head(response) + raw)
            return ended, None
        if ended == "complete":
            conn.sendall(clean.head(response, len(first)) + first)
            return ended, None
        conn.sendall(clean.head(response) + clean.frame(first))  # a body cut here never gets its last chunk
        return ended, clean

    def _hold(self, upstream: socket.socket, reader: _Reader, body: _Body,
              excerpt: _Excerpt, deadline: float) -> tuple[bytes, bytes, str | None]:
        """A failed answer's first bytes, before any of them goes on: until its end, :data:`EXCERPT_RAW_BYTES` (the
        excerpt's bound), :data:`EXCERPT_DRAIN_S` (a provider's error body comes with its head or right after it) or
        ``deadline``, whichever comes first. Returns them as the upstream sent them, their payload, and how the body
        ended (:data:`STREAM_ENDS`) if it did."""
        raw, payload = bytearray(), bytearray()

        def take(data: bytes) -> None:
            raw.extend(data)
            payload.extend(body.feed(data))
            excerpt.feed(data)

        if reader.buffer:
            take(reader.take())
        until = min(time.monotonic() + EXCERPT_DRAIN_S, deadline)
        ended: str | None = None
        while not body.done and len(raw) < EXCERPT_RAW_BYTES:
            left = until - time.monotonic()
            if left <= 0:
                break
            try:
                upstream.settimeout(left)
                data = upstream.recv(CHUNK)
            except TimeoutError:
                break
            except OSError:
                ended = "upstream_broken"
                break
            if not data:
                ended = "complete" if body.kind == "close" else "upstream_broken"
                break
            take(data)
        if body.done:
            ended = "complete"
        elif ended is not None and self._closed.is_set():  # the run's end closed it, not the upstream
            ended = "relay_closed"
        return bytes(raw), bytes(payload), ended

    def _stream(self, conn: socket.socket, upstream: socket.socket, reader: _Reader, body: _Body,
                excerpt: _Excerpt | None = None, deadline: float | None = None, clean: _Clean | None = None) -> str:
        """The response's body as it streams, until the upstream ends it. A client that goes away ends it at once,
        and so do :meth:`close` and ``deadline`` (:data:`STREAM_TIMEOUT`). ``excerpt`` sees the body's first bytes as
        they pass (a failed answer's). ``clean`` is what takes a failed answer's credentials out as it goes
        (:meth:`_failed_answer`), and ends it once its framing says it has ended. Returns how it ended
        (:data:`STREAM_ENDS`): ``upstream_broken`` when the upstream's connection failed, or closed before the end its
        framing names."""
        if deadline is None:
            deadline = time.monotonic() + self.stream_timeout

        def onward(data: bytes) -> bytes:  # what of the upstream's bytes goes to the client
            payload = body.feed(data)
            if clean is None:
                return data
            if clean.finished:
                return b""
            try:
                out = clean.frame(clean.take(payload))
                return out + clean.last() if body.done else out
            except zlib.error:  # the rest is not what its coding says: it ends here, short of its end
                raise OSError("a failed answer's body is not what its coding says") from None

        if reader.buffer:
            data = reader.take()
            sent = onward(data)
            if excerpt is not None:
                excerpt.feed(data)
            if not _send_by(conn, sent, deadline):
                return "complete" if body.done else "stream_timeout"
        with selectors.DefaultSelector() as selector:
            selector.register(upstream, selectors.EVENT_READ)
            selector.register(conn, selectors.EVENT_READ)
            selector.register(self._wake_r, selectors.EVENT_READ)
            while True:
                left = deadline - time.monotonic()
                if left <= 0:  # a response the upstream keeps open after its end is complete, not cut
                    return "complete" if body.done else "stream_timeout"
                pending = isinstance(upstream, ssl.SSLSocket) and upstream.pending() > 0
                ready = set() if pending else {key.fileobj for key, _ in selector.select(left)}
                if self._wake_r in ready:
                    return "relay_closed"
                if conn in ready and _gone(conn):
                    if body.done:
                        return "complete"
                    self._count("cancelled")  # it went before the response's end: a cancelled turn
                    if excerpt is not None:  # the record still gets the failure's body, whoever stopped reading
                        excerpt.drain(upstream, body)
                    return "client_gone"
                if pending or upstream in ready:
                    try:
                        upstream.settimeout(max(deadline - time.monotonic(), 0.001))
                        data = upstream.recv(CHUNK)
                    except TimeoutError:  # a TLS record that never completed
                        return "complete" if body.done else "stream_timeout"
                    except OSError:
                        return "complete" if body.done else "upstream_broken"
                    if not data:
                        if body.kind == "close" and clean is not None:  # the end only the close names
                            _send_by(conn, clean.last(), deadline)
                        return "complete" if body.done or body.kind == "close" else "upstream_broken"
                    try:
                        sent = onward(data)
                    except OSError:
                        return "upstream_broken"
                    if excerpt is not None:
                        excerpt.feed(data)
                    if not _send_by(conn, sent, deadline):
                        return "complete" if body.done else "stream_timeout"


def _send_by(conn: socket.socket, data: bytes, deadline: float) -> bool:
    """Send ``data`` to the client by ``deadline`` (a client that does not read holds the stream: the backpressure),
    or say it did not go."""
    conn.settimeout(max(deadline - time.monotonic(), 0.001))
    try:
        conn.sendall(data)
    except TimeoutError:
        return False
    return True


class _Body:
    """How far a response's body has been relayed: whether its end, by its framing (RFC 9112 §6.3), has gone to the
    client. A body with neither length nor chunking ends only when the upstream closes, so it is never ``done`` here.
    Chunked bodies are followed chunk by chunk, to the last chunk and its trailer section."""

    def __init__(self, head: bytes, method: str) -> None:
        status = head.split(b"\r\n", 1)[0].split(b" ")
        code = status[1] if len(status) > 1 else b""
        fields = [raw.split(b":", 1) for raw in head[:-4].split(b"\r\n")[1:]]
        values = [(f[0].strip().lower(), f[1].strip().lower()) for f in fields if len(f) == 2]
        codings = [v for k, v in values if k == b"transfer-encoding"]
        lengths = {v for k, v in values if k == b"content-length"}
        self.state, self.left, self.line = "size", 0, b""
        if method == "HEAD" or code in (b"204", b"304"):
            self.kind = "none"
        elif codings and codings[-1].split(b",")[-1].strip() == b"chunked":
            self.kind = "chunked"
        elif len(lengths) == 1 and next(iter(lengths)).isdigit():
            self.kind, self.left = "length", int(next(iter(lengths)))
        else:
            self.kind = "close"
        self.done = self.kind == "none" or (self.kind == "length" and self.left == 0)

    def feed(self, data: bytes) -> bytes:
        """Follow ``data``, the body's next bytes as the upstream sent them, and return its payload: the body's own
        bytes, without a chunked body's framing (:class:`_Clean` reads it). Once the framing cannot be read, the rest
        is payload as it comes, as a body without length or chunking is."""
        if self.done or self.kind == "none":
            return b""
        if self.kind == "close":
            return data
        if self.kind == "length":
            payload = data[:max(self.left, 0)]
            self.left -= len(data)
            self.done = self.left <= 0
            return payload
        out = bytearray()
        i = 0
        while i < len(data) and not self.done:
            if self.state == "data":  # the chunk's bytes and their CRLF
                take = min(self.left, len(data) - i)
                out += data[i:i + max(min(take, self.left - 2), 0)]  # its CRLF is framing
                i, self.left = i + take, self.left - take
                if not self.left:
                    self.state = "size"
                continue
            end = data.find(b"\n", i)
            if end < 0:
                self.line += data[i:]
                if len(self.line) > MAX_HEAD:  # no chunk-size line or trailer field is this long: framing unknown
                    self.kind = "close"
                return bytes(out)
            line, self.line, i = (self.line + data[i:end]).rstrip(b"\r"), b"", end + 1
            if self.state == "trailer":
                self.done = not line
                continue
            size = _chunk_size(line)
            if size is None:
                self.kind = "close"
                return bytes(out + data[i:])
            self.state, self.left = ("trailer", 0) if size == 0 else ("data", size + 2)
        return bytes(out)


def _status_code(head: bytes) -> int | None:
    """A response head's status code, or None when its status line has none."""
    parts = head.split(b"\r\n", 1)[0].split(b" ")
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None


# Implementation bound: how much of a failed answer's raw body is read for its excerpt, with room for chunk framing
# and a compressed body's header before the :data:`EXCERPT_BYTES` of text.
EXCERPT_RAW_BYTES = 16 * 1024
# Implementation bound: how long the record waits for a failed answer's body once its client has gone (a client may
# close as soon as it has the status). A provider's error body comes with its head or right after it.
EXCERPT_DRAIN_S = 2.0
_ELLIPSIS_MASKED = re.compile(r"\S{2,}\.{3}\S{2,}")  # a provider's own masking of a key it was sent (abcd...wxyz)
REDACTED = b"<redacted>"
# The codings of a failed answer's body the relay reads to remove a credential from it (:class:`_Clean`), as the
# record's excerpt reads them (:meth:`_Excerpt.text`); a body in any other passes as it came.
READABLE_CODINGS = frozenset({"identity", "gzip", "x-gzip", "deflate"})


class _Scrub:
    """The one owner of taking a request's credential values out of what the upstream answered: the record's excerpt
    (:meth:`_Excerpt.text`) and a failed answer's body on its way to the client (:class:`_Clean`). Each of ``held``
    (values of four characters or more, the longest first where two start at one place) becomes :data:`REDACTED`.
    Bytes go through as they come (:meth:`feed`), holding back only what could be the start of a value, until
    :meth:`end`. :attr:`found` says whether one was taken out."""

    def __init__(self, held: Collection[str]) -> None:
        self.values = sorted({v.encode() for v in held if len(v) >= 4}, key=len, reverse=True)
        self.keep = max((len(v) for v in self.values), default=1) - 1
        self.tail = b""
        self.found = False

    def feed(self, data: bytes) -> bytes:
        buf = self.tail + data
        cut = len(buf) - self.keep  # a value that starts at or after it may not be whole yet
        out = bytearray()
        i = 0
        while True:
            starts = [(at, -len(v), v) for v in self.values if 0 <= (at := buf.find(v, i)) < cut]
            if not starts:
                break
            at, _, value = min(starts)
            out += buf[i:at] + REDACTED
            i = at + len(value)
            self.found = True
        out += buf[i:max(cut, i)]
        self.tail = buf[max(cut, i):]
        return bytes(out)

    def end(self) -> bytes:
        self.keep, rest = 0, self.tail
        self.tail = b""
        return self.feed(rest)


def scrub(data: bytes, held: Collection[str]) -> bytes:
    """``data`` with each of ``held`` taken out (:class:`_Scrub`)."""
    scrubbed = _Scrub(held)
    return scrubbed.feed(data) + scrubbed.end()


class _Clean:
    """A failed answer's body on its way to the client, with the request's credential values taken out
    (:class:`_Scrub`): its payload de-chunked by its :class:`_Body`, inflated when ``gzip`` or ``deflate``, and sent
    on unencoded, framed by ``Content-Length`` when it is whole, else chunked to an HTTP/1.1 client (``chunked``) and
    ended by the close to an HTTP/1.0 one. Only a body in a coding the relay reads comes here
    (:data:`READABLE_CODINGS`). Raises ``zlib.error`` on a body its coding does not describe."""

    def __init__(self, coding: str, held: Collection[str], *, chunked: bool) -> None:
        self.scrub = _Scrub(held)
        self.inflate = (zlib.decompressobj(zlib.MAX_WBITS | (16 if "gzip" in coding else 0))
                        if coding != "identity" else None)
        self.chunked = chunked
        self.finished = False  # its rest and last chunk have gone: what the upstream sends after is not the body

    def take(self, payload: bytes) -> bytes:
        """What of ``payload`` (the body's next bytes, unframed) can go on now, its credentials out."""
        return self.scrub.feed(self.inflate.decompress(payload) if self.inflate is not None else payload)

    def end(self) -> bytes:
        """The rest, once the body has ended."""
        return self.scrub.feed(self.inflate.flush() if self.inflate is not None else b"") + self.scrub.end()

    def frame(self, data: bytes) -> bytes:
        """``data`` as it goes to the client: one chunk, or as it is. An empty chunk would end the body, so none."""
        return b"%x\r\n%s\r\n" % (len(data), data) if self.chunked and data else data

    def last(self) -> bytes:
        """The body's rest and, chunked, its last chunk, once."""
        if self.finished:
            return b""
        self.finished = True
        return self.frame(self.end()) + (b"0\r\n\r\n" if self.chunked else b"")

    def head(self, response: bytes, length: int | None = None) -> bytes:
        """``response`` as it goes to the client: its framing and coding replaced, by ``length`` when the body is
        whole, else chunked (or none), and ``Connection: close``."""
        lines = response[:-4].split(b"\r\n")
        drop = {b"content-length", b"transfer-encoding", b"content-encoding"}
        kept = [raw for raw in lines[1:] if raw.split(b":", 1)[0].strip().lower() not in drop]
        if length is not None:
            kept.append(b"Content-Length: %d" % length)
        elif self.chunked:
            kept.append(b"Transfer-Encoding: chunked")
        return _close_head(b"\r\n".join([lines[0], *kept]) + b"\r\n\r\n")


class _Excerpt:
    """The start of a failed answer's body, as text for the record: de-chunked, inflated when ``gzip`` or ``deflate``
    (any other coding is named, not read), redacted over the whole of what was read (:data:`EXCERPT_RAW_BYTES`), and
    only then cut to :data:`EXCERPT_BYTES` characters (:meth:`text`)."""

    def __init__(self, head: bytes) -> None:
        values = {}
        for raw in head[:-4].split(b"\r\n")[1:]:
            name, sep, value = raw.partition(b":")
            if sep:
                values[name.strip().lower()] = value.strip().lower().decode("latin-1")
        self.chunked = values.get(b"transfer-encoding", "").split(",")[-1].strip() == "chunked"
        self.coding = values.get(b"content-encoding", "identity") or "identity"
        self.raw = bytearray()

    def feed(self, data: bytes) -> None:
        if len(self.raw) < EXCERPT_RAW_BYTES:
            self.raw += data[:EXCERPT_RAW_BYTES - len(self.raw)]

    def drain(self, upstream: socket.socket, body: _Body) -> None:
        """Read the rest of the body from ``upstream`` for the record alone, its client gone: until its end, the
        :data:`EXCERPT_RAW_BYTES` bound, or :data:`EXCERPT_DRAIN_S`, whichever comes first. Nothing is sent on."""
        deadline = time.monotonic() + EXCERPT_DRAIN_S
        try:
            while not body.done and len(self.raw) < EXCERPT_RAW_BYTES:
                left = deadline - time.monotonic()
                if left <= 0:
                    return
                upstream.settimeout(left)
                data = upstream.recv(CHUNK)
                if not data:
                    return
                body.feed(data)
                self.feed(data)
        except OSError:  # a timeout, or the upstream gone: the record keeps what it has
            return

    def text(self, held: list[str]) -> str:
        from aew.harness.defects import redact_text

        data = _unchunk(bytes(self.raw)) if self.chunked else bytes(self.raw)
        if self.coding in READABLE_CODINGS - {"identity"}:
            try:
                inflate = zlib.decompressobj(zlib.MAX_WBITS | (16 if "gzip" in self.coding else 0))
                data = inflate.decompress(data, EXCERPT_RAW_BYTES)
            except zlib.error:
                return f"(a {self.coding} body that could not be read)"
        elif self.coding != "identity":
            return f"(a {self.coding} body: not read)"
        # Redacted whole, then cut: a value that crosses the cut is removed whole, never left less its tail
        text = scrub(data[:EXCERPT_RAW_BYTES], held).decode("utf-8", "replace")
        text = re.sub(re.escape(SENTINEL_PREFIX) + r"\S*", "<redacted placeholder>", text)
        return redact_text(_ELLIPSIS_MASKED.sub("<redacted>", text))[:EXCERPT_BYTES]


def _unchunk(raw: bytes) -> bytes:
    """A chunked body's data, as far as ``raw`` holds whole chunk-size lines (a chunk cut short is kept as it is)."""
    out, i = bytearray(), 0
    while True:
        end = raw.find(b"\r\n", i)
        size = _chunk_size(raw[i:end]) if end >= 0 else None
        if not size:
            return bytes(out)
        out += raw[end + 2:end + 2 + size]
        i = end + 2 + size + 2


class RequestLog:
    """Where a run's relays record each request: one JSON line per request in ``path``, a file on the host outside
    every sandbox (the run's directory). Appends are serialized, as several relays share it."""

    def __init__(self, path: Any) -> None:
        import threading

        self.path = path
        self._lock = threading.Lock()

    def __call__(self, entry: dict[str, Any]) -> None:
        import json

        line = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
        with self._lock, open(self.path, "ab") as out:
            out.write(line)


def _tls_context() -> ssl.SSLContext:
    """The system's default verifying context, with its floor stated: TLS 1.2 is already the default's minimum on every
    interpreter AEW supports, set here so that a reader, or a scanner, need not know that (#257's quick check, Q2)."""
    context = ssl.create_default_context()
    context.minimum_version = TLS_MINIMUM
    return context


# What the provider says, in its TLS alert, when it does not take the client certificate (or got none): OpenSSL's
# reason names for those alerts. With TLS 1.3 the alert comes after the handshake, on the first read.
_CERT_ALERTS = frozenset({"TLSV13_ALERT_CERTIFICATE_REQUIRED", "SSLV3_ALERT_BAD_CERTIFICATE",
                          "SSLV3_ALERT_CERTIFICATE_EXPIRED", "SSLV3_ALERT_CERTIFICATE_REVOKED",
                          "SSLV3_ALERT_CERTIFICATE_UNKNOWN", "SSLV3_ALERT_UNSUPPORTED_CERTIFICATE",
                          "TLSV1_ALERT_UNKNOWN_CA", "TLSV1_ALERT_ACCESS_DENIED"})


def _tls_refused(exc: ssl.SSLError, upstream: Upstream, client: ClientCert | None) -> _Refused:
    """A failed TLS connection to the upstream as a plain answer, never a bare handshake error (register E123). It
    reaches the sandbox, so it names the policy field and the CA file, never the certificate's or the key's path."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        trust = (f"the CA file {client.ca} ({client.field('ca')}): if the provider's CA changed, put the new one there "
                 "and start the run again") if client else "the system's trusted CAs"
        return _Refused(502, "upstream_untrusted", f"the provider relay does not trust {upstream.url}'s certificate "
                        f"({exc.verify_message}): it checks it against {trust}")
    if exc.reason in _CERT_ALERTS:
        if client is None:
            return _Refused(502, "client_cert_required", f"{upstream.url} refused the connection over its client "
                            f"certificate ({exc.reason}), and the policy names none: name one in "
                            "containment.network.client_certs.<provider>")
        return _Refused(502, "client_cert_refused", f"{upstream.url} refused the client certificate named in "
                        f"{client.field('cert')} ({exc.reason}): `aew doctor` checks it, and the provider may not "
                        "accept it")
    if client is None and exc.reason == "SSLV3_ALERT_HANDSHAKE_FAILURE":
        # TLS 1.2's answer to a missing certificate (E123 review, m2). It also means a cipher or version mismatch, so
        # it is not in _CERT_ALERTS, and is worded as a likelihood. A server that ends the handshake and then answers
        # HTTP 400 for the missing certificate (nginx's `ssl_verify_client on`) is relayed as it answered.
        return _Refused(502, "client_cert_required", f"the TLS connection to {upstream.url} failed ({exc.reason}): "
                        "the provider may require a client certificate, and the policy names none: name one in "
                        "containment.network.client_certs.<provider>")
    return _Refused(502, "tls_failed", f"the TLS connection to {upstream.url} failed ({exc.reason or exc})")


class _Reader:
    """Buffered reads from one socket, each with ``timeout`` (None: none)."""

    def __init__(self, sock: socket.socket, buffered: bytes, timeout: float | None) -> None:
        self.sock, self.buffer, self.timeout = sock, buffered, timeout

    def _more(self) -> None:
        self.sock.settimeout(self.timeout)
        try:
            data = self.sock.recv(CHUNK)
        except TimeoutError:
            raise _Refused(408, "body_timeout", "the request body stopped arriving") from None
        except ConnectionError:  # a client that resets mid-body: the upstream never gets it whole (#542, m6)
            data = b""
        if not data:
            raise _Refused(400, "incomplete", "the connection closed before the message was complete")
        self.buffer += data

    def take(self) -> bytes:
        out, self.buffer = self.buffer, b""
        return out

    def read(self, most: int) -> bytes:
        if not self.buffer:
            self._more()
        out, self.buffer = self.buffer[:most], self.buffer[most:]
        return out

    def line(self) -> bytes:
        while b"\r\n" not in self.buffer:
            if len(self.buffer) > MAX_HEAD:
                raise _Refused(400, "bad_chunk", "a chunk-size line is too long")
            self._more()
        end = self.buffer.index(b"\r\n") + 2
        out, self.buffer = self.buffer[:end], self.buffer[end:]
        return out

    def head(self, deadline: float | None = None) -> bytes:
        """A response head, by ``deadline`` if one is given (else :attr:`timeout` for each read)."""
        while b"\r\n\r\n" not in self.buffer:
            if len(self.buffer) > MAX_HEAD:
                raise OSError(f"the upstream's response head exceeds {MAX_HEAD} bytes")
            if deadline is not None:
                self.sock.settimeout(max(deadline - time.monotonic(), 0.001))
            try:
                data = self.sock.recv(CHUNK)
            except TimeoutError:
                if deadline is None:
                    raise
                raise _Refused(504, STREAM_TIMEOUT_REASON, "the provider did not answer within the provider relay's "
                               "time bound for a response; it may still have accepted the request, which the relay "
                               "does not send again", outcome="unknown") from None
            if not data:
                raise OSError("the upstream closed before its response head was complete")
            self.buffer += data
        end = self.buffer.index(b"\r\n\r\n") + 4
        out, self.buffer = self.buffer[:end], self.buffer[end:]
        return out


def _gone(conn: socket.socket) -> bool:
    """Whether a client the relay is streaming to has closed (or reset) its connection. Anything it sends meanwhile is
    not relayed: one request per connection."""
    try:
        return not conn.recv(CHUNK)
    except ConnectionError:
        return True


def _read_head(conn: socket.socket, timeout: float) -> tuple[bytes, bytes]:
    """``(head without its final CRLF CRLF, what followed it)``, with one deadline for the whole head."""
    deadline = time.monotonic() + timeout
    buf = b""
    while True:
        end = buf.find(b"\r\n\r\n")
        if 0 <= end <= MAX_HEAD:
            return buf[:end], buf[end + 4:]
        if len(buf) > MAX_HEAD:
            raise _Refused(431, "header_too_large", f"the request's head exceeds {MAX_HEAD} bytes")
        left = deadline - time.monotonic()
        try:
            if left <= 0:
                raise TimeoutError
            conn.settimeout(left)
            data = conn.recv(4096)
        except TimeoutError:
            raise _Refused(408, "header_timeout", "no complete request arrived in time") from None
        except ConnectionError:  # reset before its head was whole: as a close is (#542, m6)
            data = b""
        if not data:
            raise _Refused(400, "incomplete", "the connection closed before its request was complete")
        buf += data


def _framing(headers: list[tuple[str, str]]) -> tuple[str, int]:
    """How the request's body is framed (RFC 9112 §6): chunked, a length, or none."""
    encodings = [v.strip().lower() for k, v in headers if k.lower() == "transfer-encoding"]
    lengths = {v.strip() for k, v in headers if k.lower() == "content-length"}
    if encodings:
        if lengths or encodings[-1].split(",")[-1].strip() != "chunked":
            raise _Refused(400, "bad_framing", "a request with Transfer-Encoding must end in chunked and carry no "
                           "Content-Length")
        return "chunked", 0
    if len(lengths) > 1:
        raise _Refused(400, "bad_framing", "the request carries different Content-Length values")
    if lengths:
        value = lengths.pop()
        if not (value.isascii() and value.isdigit()):  # str.isdigit alone takes other scripts' digits
            raise _Refused(400, "bad_framing", "the request's Content-Length is not a number")
        return "length", int(value)
    return "none", 0


def describe(relay: ProviderRelay | None) -> dict[str, Any]:
    """For the run's label: ``network.provider_relay`` (F28 §3.1) and its fixed upstream, and whether it presents a
    client certificate (by its policy field: the label reaches the sandbox, so never a path)."""
    if relay is None:
        return {"provider_relay": RELAY_NONE}
    return {"provider_relay": RELAY_CONFIGURED, "provider_upstream": relay.upstream.url,
            **({"provider_upstream_proxy": f"{relay.proxy.host}:{relay.proxy.port}"} if relay.proxy else {}),
            **({"provider_client_cert": relay.client.field("cert")} if relay.client else {})}
