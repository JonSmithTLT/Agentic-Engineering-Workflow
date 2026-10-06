"""The frontend's production build, served from the package (design note §4.13, §4.14 R23; F20.5).

``src/aew/dashboard/static/`` holds the build the main line imported (``tools/dashboard/import_build.py``):
``index.html``, ``favicon.svg``, ``assets/*`` and ``BUILD.json``, which binds the frontend source commit, the
contract digest, the builder and every file's SHA-256. ``aew dashboard serve --static DIR`` serves an unpacked build
instead (the web agent's local runs); F20.6's acceptance uses the packaged build only.

Resolution. A request path is percent-decoded once and must then be a plain relative path: no ``..`` or ``.``
segment, no backslash, no encoded separator (``%2F``, ``%5C``), no NUL, no empty segment (refused, ``400``). A path
with no extension that is not under ``/api/`` or ``/assets/`` is the SPA fallback (``index.html``, for deep links such
as ``/work/T-0012``); a path with an extension is served only when it names a regular file inside the root, else
``404``. ``/mockServiceWorker.js`` is always ``404``. ``BUILD.json`` is provenance, not content, and is never served.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from urllib.parse import unquote

INDEX = "index.html"
BUILD_JSON = "BUILD.json"
ASSETS_PREFIX = "/assets/"
# Withheld by the resolved file's own name, so any casing a case-insensitive filesystem (Windows, macOS) resolves to
# them is withheld too (lead developer's review of PR #90).
NEVER_SERVED = frozenset({"mockserviceworker.js", BUILD_JSON.casefold()})
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json; charset=utf-8",
         ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
         ".map": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json"}
ENCODED_SEPARATOR = re.compile(r"%(2f|5c|00)", re.IGNORECASE)
IMMUTABLE = "max-age=31536000, immutable"
NO_STORE = "no-store"


class BadPath(Exception):
    """The path cannot name a file safely: ``400``."""


@dataclass(frozen=True)
class Asset:
    path: Path
    content_type: str
    cache_control: str


def packaged_root() -> Path | None:
    """The build shipped in the package, or ``None`` when this install carries none."""
    root = Path(str(resources.files("aew.dashboard") / "static"))
    return root if (root / INDEX).is_file() else None


def build_record(root: Path) -> dict | None:
    """The root's ``BUILD.json`` (provenance), or ``None``."""
    try:
        data = json.loads((root / BUILD_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _extension(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


def _contained(root: Path, segments: list[str]) -> Path | None:
    """The regular file ``segments`` names once every link is resolved, if it is still inside ``root`` and is not
    a withheld name; else ``None``."""
    base = root.resolve()
    target = base.joinpath(*segments).resolve()
    if base not in target.parents or not target.is_file() or target.name.casefold() in NEVER_SERVED:
        return None
    return target


def resolve(root: Path, raw_path: str) -> Asset | None:
    """The file a static request path names (``None``: ``404``), or :class:`BadPath`."""
    if ENCODED_SEPARATOR.search(raw_path):
        raise BadPath("an encoded separator")
    try:
        path = unquote(raw_path, errors="strict")
    except UnicodeDecodeError:
        raise BadPath("not UTF-8") from None
    if not path.startswith("/") or "\\" in path or "\x00" in path:
        raise BadPath("not a plain path")
    segments = path[1:].split("/")
    if path == "/":
        segments = []
    elif any(s in ("", ".", "..") for s in segments):
        raise BadPath("an empty, . or .. segment")
    if not segments or (not _extension(segments[-1]) and not path.startswith(ASSETS_PREFIX)):
        index = _contained(root, [INDEX])  # the SPA fallback for deep links, held to the same checks
        return Asset(index, TYPES[".html"], NO_STORE) if index is not None else None
    ext = _extension(segments[-1])
    if ext not in TYPES:
        return None
    target = _contained(root, segments)
    if target is None:
        return None
    cache = IMMUTABLE if path.startswith(ASSETS_PREFIX) else NO_STORE
    return Asset(target, TYPES[ext], cache)
