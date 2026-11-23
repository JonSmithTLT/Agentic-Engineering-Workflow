"""Evidence file families and their states. JSON and autopsy families share owners."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileFamily:
    pattern: str
    writer: str | None
    scanned: bool = False
    priority: bool | Callable[[Path], bool] = False
    stack: bool = False


def autopsy_priority(path: Path) -> bool:
    return any(p.startswith("session-") for p in path.parts) or path.name.startswith(("reason", "stacks"))


# Ordered like the writers: a watchdog or running name keeps its owner even in a nested session.
FAMILIES = (
    FileFamily("inventory.txt", "publisher"),
    FileFamily("job-label-sha256.txt", "evidence_inputs"),
    FileFamily("hang-*.txt", "watchdog", scanned=True, priority=True),
    FileFamily("running-*.txt", "watchdog"),
    FileFamily("running-*.tmp", "watchdog"),
    FileFamily("collection-incomplete.txt", "evidence_inputs"),
    FileFamily("tools-unavailable.txt", "evidence_inputs"),
    FileFamily("autopsy/**", "autopsy/session_deadline/harness_diagnostics/flight_recorder",
               scanned=True, priority=autopsy_priority),
    FileFamily("harness-runs/**", "harness_diagnostics", scanned=True),
    FileFamily("snapshots/*.txt", "lane_step", scanned=True, priority=True),
    FileFamily("runner-resources-*.txt", "lane_step", scanned=True, priority=True),
    FileFamily("*vertical*.json", "vertical"),
    FileFamily("vertical-series.jsonl", "vertical"),
    FileFamily("*.json", "lanes"),
    FileFamily("junit.xml", "pytest", scanned=True),
    FileFamily("vertical-summary.txt", "vertical", scanned=True),
    FileFamily("dispatch.txt", "flake-dispatch", scanned=True),
    # Shape-only selectors preserve priority staging even for an unknown writer; full publication checks ownership.
    FileFamily("hang-*", None, priority=True, stack=True),
    FileFamily("stacks.*", None, priority=True, stack=True),
    FileFamily("*-stacks*", None, priority=True, stack=True),
    FileFamily("snapshots/**", None, scanned=True, priority=True, stack=True),
    FileFamily("runner-resources-*", None, priority=True),
)
WATCHDOG_PREFIX = "aew hang watchdog: "
ARMED_NOTE = "a dump below records a fire"
WATCHDOG_HEADER = re.compile(
    rf"{WATCHDOG_PREFIX}(.+) started ([^;]+); limit ([0-9.]+)s; {ARMED_NOTE}; monotonic ([0-9.]+)")
FRAME = re.compile(
    r'(?m)^\s*(?:File "(?P<file>[^"\n]+)", line \d+,? in (?P<function>[\w.<>]+)'
    r'|(?P<spy_function>[\w.<>]+) \((?P<spy_file>[^\n]+\.py):\d+\))')


FRESH_S = 60
PREFIX = "worker snapshot "


def entries(text: str):
    """Only complete, labelled samples. Each frame block ends at the next header."""
    for block in re.split(r"(?m)^" + re.escape(PREFIX), text)[1:]:
        header, _, frames = block.partition("\n")
        try:
            row = json.loads(header)
            if isinstance(row, dict) and FRAME.search(frames):
                yield row, frames
        except ValueError:
            continue


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


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


def families(path: Path):
    for family in FAMILIES:
        nested = family.pattern.endswith("/**")
        if (family.pattern[:-3] in path.parts[:-1] if nested else path.match(family.pattern)):
            yield family


def owner(path: Path) -> str | None:
    return next((family.writer for family in families(path) if family.writer), None)


def publishable(path: Path) -> bool:
    # Recursive directories accept text diagnostics only. The specific XML family is scanned as well.
    return any(family.scanned and (not family.pattern.endswith("/**") or path.suffix == ".txt")
               for family in families(path))


def stack_file(path: Path) -> bool:
    return any(family.stack for family in families(path))


def priority(path: Path) -> bool:
    return any(family.priority(path) if callable(family.priority) else family.priority for family in families(path))


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
