"""Hold a real Windows handle that conflicts with Python's file open."""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

import pytest


@contextmanager
def blocked_read(path: Path, *, release: bool = True, replace_gap: bool = False) -> Iterator[None]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # DELETE access plus full sharing: the CRT open does not grant FILE_SHARE_DELETE to this handle.
    handle = kernel.CreateFileW(str(path), 0x00010000, 0x7, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    timer = None
    hidden = path.with_suffix(".pending")
    moved = False

    def publish() -> None:
        try:
            if moved:
                hidden.rename(path)
        finally:
            kernel.CloseHandle(handle)

    try:
        with pytest.raises(PermissionError):
            path.read_bytes()
        if replace_gap:
            # Model the Windows open that reports a missing name while publication is in flight.
            path.rename(hidden)
            moved = True
            with pytest.raises(FileNotFoundError):
                path.read_bytes()
        if release:
            # Remain held past the first read but release within the shared retry budget (280 ms).
            timer = threading.Timer(0.1, publish)
            timer.start()
        yield
    finally:
        if timer is None:
            publish()
        else:
            timer.join()
