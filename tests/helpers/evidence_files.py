"""Evidence file families and their states. JSON and autopsy families share owners."""

from __future__ import annotations

import os
import re
from pathlib import Path

# The directory owner is recursive. New writers extend this table and its enumeration test.
WRITERS = (
    ("inventory.txt", "publisher"),
    ("job-label-sha256.txt", "evidence_inputs"),
    ("hang-*.txt", "watchdog"),
    ("running-*.txt", "watchdog"),
    ("running-*.tmp", "watchdog"),
    ("collection-incomplete.txt", "evidence_inputs"),
    ("tools-unavailable.txt", "evidence_inputs"),
    ("autopsy/**", "autopsy/session_deadline/harness_diagnostics/flight_recorder"),
    ("harness-runs/**", "harness_diagnostics"),
    ("snapshots/*.txt", "lane_step"),
    ("runner-resources-*.txt", "lane_step"),
    ("*vertical*.json", "vertical"),
    ("vertical-series.jsonl", "vertical"),
    ("*.json", "lanes"),
    ("junit.xml", "pytest"),
    ("vertical-summary.txt", "vertical"),
    ("dispatch.txt", "flake-dispatch"),
)
WATCHDOG_PREFIX = "aew hang watchdog: "
ARMED_NOTE = "a dump below records a fire"
WATCHDOG_HEADER = re.compile(
    rf"{WATCHDOG_PREFIX}(.+) started ([^;]+); limit ([0-9.]+)s; {ARMED_NOTE}; monotonic ([0-9.]+)")
FRAME = re.compile(
    r'(?m)^\s*(?:File "(?P<file>[^"\n]+)", line \d+,? in (?P<function>[\w.<>]+)'
    r'|(?P<spy_function>[\w.<>]+) \((?P<spy_file>[^\n]+\.py):\d+\))')


def open_observation(path: Path):
    """Read an in-flight file without preventing its owner from removing or renaming it."""
    if os.name != "nt":
        return path.open(encoding="utf-8", errors="replace")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    generic_read, open_existing = 0x80000000, 3
    share_read_write_delete = 1 | 2 | 4
    handle = create(str(path), generic_read, share_read_write_delete, None, open_existing, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except OSError:
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise
    return os.fdopen(fd, encoding="utf-8", errors="replace")


def owner(path: Path) -> str | None:
    for pattern, writer in WRITERS:
        if pattern.endswith("/**") and pattern[:-3] in path.parts[:-1]:
            return writer
        if path.match(pattern):
            return writer
    return None


def stack_file(path: Path) -> bool:
    return path.name.startswith(("hang-", "stacks.")) or "-stacks" in path.name or "snapshots" in path.parts


def state(path: Path, data: bytes) -> str:
    if not data:
        return "empty"
    text = data.decode("utf-8", errors="replace")
    if path.name.startswith("hang-") or "-stacks" in path.name:
        first, _, body = text.partition("\n")
        if first.startswith("armed ") or (first.startswith("aew hang watchdog:") and " started " in first):
            return "finding" if body.strip() else "armed-placeholder"
        return "finding" if FRAME.search(text) or "Timeout (" in text else "armed-placeholder"
    return "finding"


def stacks_ablated() -> bool:
    return bool(os.environ.get("AEW_EVIDENCE_PLANT")) and os.environ.get("AEW_EVIDENCE_ABLATE") == "stacks"
