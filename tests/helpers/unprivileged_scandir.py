"""A directory listing as an unprivileged account sees it, for the tests of the project's `.env` scan.

These tests may run as root, which lists every directory whatever its mode. Installed with
:func:`listing_as_unprivileged`, ``os.scandir`` refuses a directory its owner may not read, as it would for an account
that is not root. It can also make one entry's type unreadable. Only the layout is built with it installed: the sandbox
itself runs as it always does.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

_REAL = os.scandir


class _Unreadable:
    """A directory entry whose type cannot be read: ``is_dir`` and ``is_file`` raise as a failed ``stat`` does."""

    def __init__(self, entry: os.DirEntry[str]) -> None:
        self.name, self.path = entry.name, entry.path

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        raise PermissionError(errno.EACCES, "Permission denied", self.path)

    is_file = is_dir

    def is_symlink(self) -> bool:
        raise PermissionError(errno.EACCES, "Permission denied", self.path)


class _Listing:
    def __init__(self, path: Any, unreadable: set[str]) -> None:
        self._it = _REAL(path)
        self._unreadable = unreadable

    def __enter__(self) -> _Listing:
        return self

    def __exit__(self, *exc: object) -> None:
        self._it.close()

    def __iter__(self) -> Iterator[Any]:
        for entry in self._it:
            yield _Unreadable(entry) if entry.path in self._unreadable else entry

    def close(self) -> None:
        self._it.close()


@contextmanager
def listing_as_unprivileged(monkeypatch: pytest.MonkeyPatch, *, unreadable: tuple[str, ...] = (),
                            too_long: tuple[str, ...] = (), unlistable: tuple[str, ...] = ()) -> Iterator[None]:
    """``os.scandir`` refuses a directory whose owner has no read permission, and each of ``unlistable`` whatever its
    mode (EACCES: Windows' ``chmod`` cannot take a directory's list permission away), and each of ``too_long``
    (ENAMETOOLONG); each entry at a path in ``unreadable`` has a type that cannot be read."""
    bad = {os.fspath(p) for p in unreadable}
    long = {os.fspath(p) for p in too_long}
    refused = {os.fspath(p) for p in unlistable}

    def scandir(path: Any = ".") -> Any:
        if isinstance(path, int):  # a directory already open: its permissions were checked when it was opened
            return _REAL(path)
        where = os.fspath(path)
        if where in long:
            raise OSError(errno.ENAMETOOLONG, "File name too long", where)
        if where in refused or not os.stat(where).st_mode & stat.S_IRUSR:
            raise PermissionError(errno.EACCES, "Permission denied", where)
        return _Listing(path, bad)

    with monkeypatch.context() as patch:
        patch.setattr(os, "scandir", scandir)
        yield
