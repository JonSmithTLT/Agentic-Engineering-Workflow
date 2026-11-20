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
