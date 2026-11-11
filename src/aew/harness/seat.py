"""Host identity for the Lead generation start and evidence of processes left behind."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

from aew.errors import PermissionDenied
from aew.harness import procs
from aew.util import atomic_write

OPENCODE_ACQUIRE = "opencode_acquire"
VACANT_START = "vacant_start"
LEAD_ACQUIRE = "lead_acquire"
TAKEOVER = "takeover"
HANDOFF = "handoff"
SEAT_RESUME = "seat_resume"
RESUMABLE = frozenset({OPENCODE_ACQUIRE, VACANT_START, SEAT_RESUME})
Leftovers = list[tuple[int, str]] | int | None  # None means the outcome is unknown


def _windows_sid() -> str:  # pragma: windows-only
    if sys.platform != "win32":
        raise RuntimeError("a Windows SID is only available on Windows")
    import ctypes as c
    from ctypes import wintypes as w

    kernel = c.WinDLL("kernel32", use_last_error=True)
    advapi = c.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.LocalFree.restype = c.c_void_p
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.POINTER(w.LPWSTR)]
    token = w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, c.byref(token)):  # TOKEN_QUERY
        raise c.WinError(c.get_last_error())
    try:
        size = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, c.byref(size))  # TokenUser
        data = c.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, data, size, c.byref(size)):
            raise c.WinError(c.get_last_error())
        # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first member is the SID pointer.
        sid = c.cast(data, c.POINTER(c.c_void_p))[0]
        name = w.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, c.byref(name)):
            raise c.WinError(c.get_last_error())
        try:
            return c.wstring_at(name)
        finally:
            kernel.LocalFree(c.cast(name, c.c_void_p))
    finally:
        kernel.CloseHandle(token)


def principal() -> tuple[str, int | str]:
    return socket.gethostname(), _windows_sid() if sys.platform == "win32" else os.getuid()


def start_identity(kind: str) -> dict[str, Any]:
    host, user = principal()
    pid = os.getpid()
    start = procs.start_id(pid)
    if kind in RESUMABLE and not start:
        raise PermissionDenied("cannot establish the identity of this OpenCode session", reason="seat_identity_unknown")
    return {"host": host, "user": user, "pid": pid, "start_id": start}


def _path(root: Path, generation: int) -> Path:
    return root / "local" / "lead" / f"leftovers-{generation}.json"


def read_leftovers(root: Path, generation: int) -> Leftovers:
    try:
        record = json.loads(_path(root, generation).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or type(record.get("generation")) is not int or record["generation"] != generation:
        return None
    left = record.get("processes")
    if sys.platform == "win32":
        return left if type(left) is int and left >= 0 else None
    if isinstance(left, list) and all(
        isinstance(entry, list) and len(entry) == 2 and type(entry[0]) is int and entry[0] > 0
        and isinstance(entry[1], str) and entry[1] for entry in left
    ):
        return [(pid, start) for pid, start in left]
    return None


def write_leftovers(root: Path, generation: int, left: Leftovers) -> None:
    path = _path(root, generation)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps({"generation": generation, "processes": left}))


def empty_leftovers() -> list[tuple[int, str]] | int:
    return 0 if sys.platform == "win32" else []


def remaining(previous: Leftovers, survivors: list[tuple[int, str | None]], ownership: str | None) -> Leftovers:
    if previous is None or ownership not in {"clean", "survivors"}:
        return None
    if isinstance(previous, int):
        return previous + len(survivors)
    if any(not start for _, start in survivors):
        return None
    return sorted({(pid, start) for pid, start in previous
                   if procs.same_process(pid, start) or (procs.start_id(pid) is None and procs.pid_alive(pid))}
                  | {(pid, start) for pid, start in survivors if start})


def describe_leftovers(left: Leftovers) -> str:
    if left is None:
        return "unknown"
    if not left:
        return "none"
    if isinstance(left, int):
        return f"{left} process(es)"
    return ", ".join(f"pid {pid} ({start})" for pid, start in left)
