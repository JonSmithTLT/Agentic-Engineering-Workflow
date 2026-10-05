"""Canonical encoding and content hashes (design §4: "schema-defined ordering/encoding").

One encoding for everything that is hashed: JSON with sorted keys, no insignificant whitespace, UTF-8 and no ASCII
escaping. A YAML file and the JSON it parses to therefore hash the same, and key order never changes a hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_of(value: Any) -> str:
    """The content hash of a JSON-compatible value."""
    return hashlib.sha256(canonical(value)).hexdigest()


def tree_sha256(root: Path) -> str:
    """The content hash of a directory: every regular file's path (relative, ``/``-separated) and bytes. Empty
    directories and file metadata do not count; a symbolic link is refused, so a hash never depends on where it
    points."""
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"{path} is a symbolic link; a hashed tree holds regular files only")
        if path.is_file():
            entries.append([path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()])
    if not entries:
        raise ValueError(f"{root} holds no files to hash")
    return sha256_of(entries)
