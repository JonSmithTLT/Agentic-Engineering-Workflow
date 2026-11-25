"""HTTP/1.1 as the provider relay (``relay.py``) and the egress proxy (``egress.py``) read and write it: what a
request's head may hold, read from a client, and the framing both forward. One owner, which the egress proxy imports
without importing the relay (the relay imports the egress proxy's ``Service``).

A field line is ``name: value`` (RFC 9112 §5). Its name is a token (RFC 9110 §5.1), and its value holds visible
characters, ``obs-text``, spaces and horizontal tabs only (RFC 9110 §5.5): any other control character (CR, LF, NUL,
the rest of C0, and DEL) refuses the line, never passes it on. A head whose lines end in a bare LF therefore never reads
as fields: its LFs stay inside the line around them, and the line is refused.
"""

from __future__ import annotations

import re

# RFC 9110 §5.6.2: a method and a field name.
TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
# Hop-by-hop (RFC 9110 §7.6.1), plus Expect, which the relay and the egress proxy each answer themselves (a 100 Continue
# before the body): never forwarded either way.
HOP_BY_HOP = frozenset({"connection", "keep-alive", "proxy-connection", "proxy-authorization", "proxy-authenticate",
                        "te", "trailer", "upgrade", "expect"})
# RFC 9110 §5.5: what a field value may not hold. HTAB (\x09) is allowed; every other C0 control and DEL are not.
_CONTROL = re.compile(rb"[\x00-\x08\x0a-\x1f\x7f]")


def has_control(value: bytes) -> bool:
    """Whether ``value`` holds a control character a field value may not hold (all but HTAB). A chunk-size line's
    extension and a trailer field are held to the same rule (RFC 9112 §7.1.1, §7.1.2)."""
    return _CONTROL.search(value) is not None


class BadField(ValueError):
    """A field line that is not ``name: value`` as RFC 9110 allows it; the message says which part, never the line."""


def fields(lines: list[bytes]) -> list[tuple[str, str]]:
    """The head's field lines (those after its request line, split on CRLF) as ``(name, value)``, the value without
    its surrounding spaces and tabs. Raises :class:`BadField` for a line without a colon, a name that is not a token
    (which includes a folded line, RFC 9112 §5.2), or a value holding a control character other than HTAB."""
    out = []
    for raw in lines:
        name, sep, value = raw.partition(b":")
        try:
            text = name.decode("ascii")
        except UnicodeDecodeError:
            text = ""
        if not sep or not TOKEN.fullmatch(text):
            raise BadField("a request header is not Name: value")
        if has_control(value):
            raise BadField(f"the value of request header {text} holds a control character, which a header value "
                           "may not hold (RFC 9110 §5.5)")
        out.append((text, value.strip(b" \t").decode("latin-1")))
    return out


def chunk_size(line: bytes) -> int | None:
    """A chunk-size line's size (``line`` without its CRLF), or None when its size is not hex digits alone
    (``1*HEXDIG``, RFC 9112 §7.1), or the line holds a control character other than HTAB, in its size or its
    extension (RFC 9112 §7.1.1; :func:`has_control`). ``int`` would also take a sign or underscores, and a negative
    size never ends its chunk (#257's quick check, Q1). Only spaces and tabs around the size are dropped."""
    if has_control(line):
        return None
    token = line.split(b";", 1)[0].strip(b" \t")
    return int(token, 16) if re.fullmatch(rb"[0-9A-Fa-f]+", token) else None


def head(line: str, headers: list[tuple[str, str]]) -> bytes:
    """A message head: its start line, its fields, and the empty line that ends it."""
    return ("\r\n".join([line, *(f"{k}: {v}" for k, v in headers)]) + "\r\n\r\n").encode("latin-1")


def close_head(head: bytes) -> bytes:
    """A response head with its hop-by-hop headers out and ``Connection: close`` in."""
    lines = head[:-4].split(b"\r\n")
    named_fields = [(raw.split(b":", 1)[0].strip().lower().decode("latin-1"), raw) for raw in lines[1:]]
    named = {t.strip().lower().decode("latin-1") for name, raw in named_fields if name == "connection"
             for t in raw.split(b":", 1)[-1].split(b",")}
    kept = [raw for name, raw in named_fields if name not in HOP_BY_HOP and name not in named]
    return b"\r\n".join([lines[0], *kept, b"Connection: close"]) + b"\r\n\r\n"
