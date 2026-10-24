"""Reads for a polled predicate: a file another thread or process is rewriting answers "not yet", never an error.

On Windows a read of a file that is being replaced (``os.replace``) can fail for a moment with ``PermissionError``
while the old file is delete-pending, and a writer that writes in place can be read half-written. A predicate passed to
``until`` reads through these two, so such a read is None and the poll tries again. The class and its scan are in
tests/unit/test_polling_predicates.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_text_or_none(path: Path | str) -> str | None:
    """The file's text, or None when the read fails (a missing file, or one mid-replace on Windows), so a poll waits."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def read_json_or_none(path: Path | str) -> Any | None:
    """The file's JSON, or None when it cannot be read or does not parse yet (half-written), so a poll waits."""
    text = read_text_or_none(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None
