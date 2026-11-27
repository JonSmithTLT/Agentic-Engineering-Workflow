"""Hold a real Windows handle that conflicts with Python's file open."""

from __future__ import annotations

import ctypes
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace

import pytest

from aew.engine import store


@contextmanager
def blocked_read(path: Path, *, release: bool = True, replace_gap: bool = False,
                 release_after: int = 1) -> Iterator[None]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # DELETE access plus full sharing: the CRT open does not grant FILE_SHARE_DELETE to this handle.
    handle = kernel.CreateFileW(str(path), 0x00010000, 0x7, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    hidden = path.with_name(f".{path.name}.held.tmp")
    moved = False
    released = False
    sleeps = 0
    owner = threading.get_ident()

    def publish() -> None:
        nonlocal released
        if released:
            return
        try:
            if moved:
                hidden.rename(path)
        finally:
            kernel.CloseHandle(handle)
            released = True

    def release_on_retry(delay: float) -> None:
        nonlocal sleeps
        if threading.get_ident() == owner:
            sleeps += 1
            if sleeps == release_after:
                publish()
        time.sleep(delay)

    try:
        with pytest.raises(PermissionError):
            path.read_bytes()
        if replace_gap:
            # Model the Windows open that reports a missing name while publication is in flight.
            path.rename(hidden)
            moved = True
            with pytest.raises(FileNotFoundError):
                path.read_bytes()
        with pytest.MonkeyPatch.context() as patch:
            if release:
                # The first actual retry releases the handle, independent of imports and scheduling.
                patch.setattr(store, "time", SimpleNamespace(monotonic=time.monotonic, sleep=release_on_retry))
            yield
            if release:
                assert released, "the reader did not retry the held handle"
    finally:
        publish()


@contextmanager
def held_by_a_reader(path: Path, *, release_after: int | None = 1) -> Iterator[None]:
    """``path`` held open by a reader the way Python's own ``open`` holds it (no ``FILE_SHARE_DELETE``), so a removal
    is refused with a sharing violation until the reader lets go: on Windows a real handle, elsewhere (where an open
    file can be removed) the same refusal injected into ``Path.unlink`` for this path alone, with ``aew.util`` told it
    runs on Windows. The ``release_after``-th retry pause of the thread that entered releases it, independent of
    scheduling; ``None`` holds it to the end and models a reader that outlasts the wait."""
    from aew import util

    owner = threading.get_ident()
    target = Path(path)
    windows = util.IS_WINDOWS
    reader = open(target, "rb") if windows else None  # held across the yield, closed in publish()
    held = True
    sleeps = 0
    skipped = 0.0  # the owner's pauses advance its clock without sleeping: a hold that outlasts the wait costs no time

    def publish() -> None:
        nonlocal held
        if held and reader is not None:
            reader.close()
        held = False

    def pause(delay: float) -> None:
        nonlocal sleeps, skipped
        if threading.get_ident() != owner:
            time.sleep(delay)
            return
        sleeps += 1
        if sleeps == release_after:
            publish()
        skipped += delay

    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if held and self == target:
            error = PermissionError(13, "The process cannot access the file because it is being used by another "
                                        "process", str(self))
            error.winerror = 32  # type: ignore[attr-defined]
            raise error
        real_unlink(self, missing_ok=missing_ok)

    clock = SimpleNamespace(monotonic=lambda: time.monotonic() + skipped, sleep=pause)
    try:
        with pytest.MonkeyPatch.context() as patch:
            if not windows:
                patch.setattr(util, "IS_WINDOWS", True)
                patch.setattr(Path, "unlink", unlink)
            with pytest.raises(PermissionError):
                target.unlink()  # the hold is real: an unguarded removal is refused
            patch.setattr(util, "time", clock)
            yield
            if release_after is not None:
                assert not held, "the removal did not retry the held file"
    finally:
        publish()
