"""Names, canonical bytes and identity for project maps (plan §3.2, §3.3; ADR-0015). Pure: no I/O.

* **Names.** Git paths are bytes. A path is rendered once, here, into a string that is safe everywhere it goes: valid
  UTF-8 is kept, except that every control, format and line- or paragraph-separator character (Unicode categories Cc,
  Cf, Zl and Zp: C0, DEL, C1, bidi overrides, zero-width characters, U+2028, U+2029) and every invalid byte becomes
  ``\\xNN`` per byte, and a backslash becomes ``\\\\``. A rendered string is one line and displays as what it is. The
  rendering is injective, so two paths never share a name, and it never
  produces a lone surrogate, so serialization cannot fail on a hostile name.
* **Identity.** ``artifact_sha256`` is the sha256 of the record's canonical JSON (sorted keys, no whitespace, ASCII,
  integers only) without ``artifact_sha256`` itself; no YAML emitter is involved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

BLOB, TREE, COMMIT = "blob", "tree", "commit"
GITLINK_MODE, SYMLINK_MODE = "160000", "120000"
REGULAR_MODES = frozenset({"100644", "100755"})


@dataclass(frozen=True)
class Entry:
    """One entry of a commit's recursive tree listing (``ls-tree -r -l``): ``size`` is None for a gitlink."""

    mode: str
    type: str
    oid: str
    size: int | None
    path: str  # rendered (``render_bytes``)
    utf8: bool = True  # whether the raw name was valid UTF-8

    @property
    def regular(self) -> bool:
        return self.type == BLOB and self.mode in REGULAR_MODES

    @property
    def symlink(self) -> bool:
        return self.mode == SYMLINK_MODE

    @property
    def gitlink(self) -> bool:
        return self.mode == GITLINK_MODE or self.type == COMMIT


# Every code point in the Unicode categories Cc (C0, DEL, C1), Cf (bidi overrides and isolates, zero-width characters,
# the BOM, ...), Zl and Zp (U+2028, U+2029: line breaks to Python's ``splitlines``), frozen from Unicode 15.1.0 rather
# than read from ``unicodedata``: Python 3.11 and 3.13 ship different Unicode versions, and the rendering is part of
# the record's bytes, so it must not depend on the interpreter (T5-INV-08). A change here changes output bytes: bump
# ``structural.VERSION`` (PR #126 review, F1; T5-INV-07).
ESCAPED_RANGES = (
    (0x0000, 0x001F), (0x007F, 0x009F), (0x00AD, 0x00AD), (0x0600, 0x0605), (0x061C, 0x061C), (0x06DD, 0x06DD),
    (0x070F, 0x070F), (0x0890, 0x0891), (0x08E2, 0x08E2), (0x180E, 0x180E), (0x200B, 0x200F), (0x2028, 0x202E),
    (0x2060, 0x2064), (0x2066, 0x206F), (0xFEFF, 0xFEFF), (0xFFF9, 0xFFFB), (0x110BD, 0x110BD), (0x110CD, 0x110CD),
    (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0001, 0xE0001), (0xE0020, 0xE007F),
)
ESCAPED_UNICODE_VERSION = "15.1.0"
_ESCAPED = frozenset(c for lo, hi in ESCAPED_RANGES for c in range(lo, hi + 1))


def _escape_char(ch: str) -> str:
    code = ord(ch)
    if ch == "\\":
        return "\\\\"
    if 0xDC80 <= code <= 0xDCFF:  # an invalid byte, carried by surrogateescape
        return f"\\x{code - 0xDC00:02x}"
    if code in _ESCAPED:  # per UTF-8 byte, like an invalid byte: the rendering stays injective
        return "".join(f"\\x{b:02x}" for b in ch.encode("utf-8"))
    if 0xD800 <= code <= 0xDFFF:  # a lone surrogate from parsed text (JSON allows one): never emitted raw
        return f"\\u{code:04x}"
    return ch


def render_bytes(raw: bytes) -> tuple[str, bool]:
    """A raw Git name as a safe string, and whether it was valid UTF-8."""
    try:
        text = raw.decode("utf-8")
        valid = True
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "surrogateescape")
        valid = False
    return "".join(_escape_char(ch) for ch in text), valid


def render_text(text: str, limit: int = 200) -> str:
    """Repository-controlled text (a parsed value) as a bounded, escaped string: data, never markup (T5-INV-07)."""
    return "".join(_escape_char(ch) for ch in text[:limit])


def _check(value: Any, where: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return
    if isinstance(value, float):
        raise TypeError(f"{where}: a project-map record holds integers only")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"{where}: keys are strings")
            _check(v, f"{where}.{k}")
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            _check(v, f"{where}[{i}]")
        return
    raise TypeError(f"{where}: {type(value).__name__} is not canonical JSON")


def canonical_json(value: Any) -> bytes:
    _check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal(record: dict[str, Any]) -> tuple[str, bytes]:
    """The artifact's identity and its stored bytes: the canonical JSON with ``artifact_sha256`` added."""
    body = {k: v for k, v in record.items() if k != "artifact_sha256"}
    digest = sha256(canonical_json(body))
    return digest, canonical_json({**body, "artifact_sha256": digest})


def listing_sha256(entries: list[Entry]) -> str:
    """The path-listing input (plan §2): ``mode type path`` for every entry, plus the object id for gitlinks only, so
    a content-only edit leaves it unchanged while an added, deleted or renamed path or a submodule bump changes it."""
    lines = sorted(f"{e.mode} {e.type} {e.path}" + (f" {e.oid}" if e.gitlink else "") for e in entries)
    return sha256("".join(line + "\n" for line in lines).encode("utf-8"))
