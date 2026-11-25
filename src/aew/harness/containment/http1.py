"""What an HTTP/1.1 request's head may hold, read from a client: one owner for the provider relay (``relay.py``) and
the egress proxy (``egress.py``), which imports it without importing the relay.

A field line is ``name: value`` (RFC 9112 §5). Its name is a token (RFC 9110 §5.1), and its value holds visible
characters, ``obs-text``, spaces and horizontal tabs only (RFC 9110 §5.5): any other control character (CR, LF, NUL,
the rest of C0, and DEL) refuses the line, never passes it on. A head whose lines end in a bare LF therefore never reads
as fields: its LFs stay inside the line around them, and the line is refused.
"""

from __future__ import annotations

import re

# RFC 9110 §5.6.2: a method and a field name.
TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
# RFC 9110 §5.5: what a field value may not hold. HTAB (\x09) is allowed; every other C0 control and DEL are not.
_CONTROL = re.compile(rb"[\x00-\x08\x0a-\x1f\x7f]")


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
        if _CONTROL.search(value):
            raise BadField(f"the value of request header {text} holds a control character, which a header value "
                           "may not hold (RFC 9110 §5.5)")
        out.append((text, value.strip(b" \t").decode("latin-1")))
    return out
