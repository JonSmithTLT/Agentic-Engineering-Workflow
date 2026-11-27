"""Listing and stat as an unprivileged account sees them, for the tests of the project's `.env` scan.

These tests may run as root, which lists and searches every directory whatever its mode. Installed with
:func:`listing_as_unprivileged`, ``os.scandir`` refuses a directory its owner may not read, and ``os.stat``,
``os.lstat`` and a listed entry's ``stat`` refuse a path whose directory its owner may not search, as they would for
an account that is not root: a directory that can be read but not searched (0400, 0600, 0444) lists its names, and
nothing in it can be checked. Named paths can also be refused whatever their mode, as Windows' ``chmod`` cannot take a
directory's permissions away. Only the layout is built with it installed: the sandbox itself runs as it always does.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

_SCANDIR, _STAT, _LSTAT = os.scandir, os.stat, os.lstat


def _refused(path: str) -> PermissionError:
    return PermissionError(errno.EACCES, "Permission denied", path)


class _Entry:
    """A listed entry whose ``stat`` is checked as :func:`listing_as_unprivileged` checks one."""

    def __init__(self, entry: os.DirEntry[str], check: Any) -> None:
        self._entry, self._check = entry, check
        self.name, self.path = entry.name, entry.path

    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        self._check(self.path)
        return self._entry.stat(follow_symlinks=follow_symlinks)

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self._entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        return self._entry.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self) -> bool:
        return self._entry.is_symlink()


class _Listing:
    def __init__(self, path: Any, check: Any) -> None:
        self._it, self._check = _SCANDIR(path), check

    def __enter__(self) -> _Listing:
        return self

    def __exit__(self, *exc: object) -> None:
        self._it.close()

    def __iter__(self) -> Iterator[Any]:
        for entry in self._it:
            yield _Entry(entry, self._check)

    def close(self) -> None:
        self._it.close()


@contextmanager
def listing_as_unprivileged(monkeypatch: pytest.MonkeyPatch, *, unreadable: tuple[str, ...] = (),
                            too_long: tuple[str, ...] = (), unlistable: tuple[str, ...] = (),
                            unsearchable: tuple[str, ...] = ()) -> Iterator[None]:
    """``os.scandir`` refuses a directory whose owner has no read permission, and each of ``unlistable`` whatever its
    mode (EACCES), and each of ``too_long`` (ENAMETOOLONG); a stat of a path whose directory its owner has no search
    permission on, or that is in ``unsearchable`` whatever its mode, or of a path in ``unreadable``, is refused
    (EACCES)."""
    bad = {os.fspath(p) for p in unreadable}
    closed = {os.fspath(p) for p in unsearchable}
    long = {os.fspath(p) for p in too_long}
    refused = {os.fspath(p) for p in unlistable}

    def check(path: Any) -> None:
        where = os.fspath(path)
        if where in bad:
            raise _refused(where)
        parent = os.path.dirname(where)
        if parent in closed or (parent and parent != where and not _STAT(parent).st_mode & stat.S_IXUSR):
            raise _refused(where)

    def scandir(path: Any = ".") -> Any:
        if isinstance(path, int):  # a directory already open: its permissions were checked when it was opened
            return _SCANDIR(path)
        where = os.fspath(path)
        if where in long:
            raise OSError(errno.ENAMETOOLONG, "File name too long", where)
        if where in refused or not _STAT(where).st_mode & stat.S_IRUSR:
            raise _refused(where)
        return _Listing(path, check)

    def checked(real: Any) -> Any:
        def call(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            if not isinstance(path, int):
                check(path)
            return real(path, *args, **kwargs)
        return call

    with monkeypatch.context() as patch:
        patch.setattr(os, "scandir", scandir)
        patch.setattr(os, "stat", checked(_STAT))
        patch.setattr(os, "lstat", checked(_LSTAT))
        yield
