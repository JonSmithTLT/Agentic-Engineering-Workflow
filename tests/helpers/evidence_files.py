"""The writers and publication states of test evidence files."""

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
    ("autopsy/**", "autopsy/session_deadline/harness_diagnostics/flight_recorder"),
    ("harness-runs/**", "harness_diagnostics"),
    ("snapshots/*.txt", "lane_step"),
    ("runner-resources-*.txt", "lane_step"),
    ("*.json", "lanes"),
    ("junit.xml", "pytest"),
    ("vertical-summary.txt", "vertical"),
    ("dispatch.txt", "flake-dispatch"),
)
FRAME = re.compile(r'(?m)^\s*(?:File "[^"\n]+", line \d+,? in \w+|[\w.<>]+ \([^\n]+\.py:\d+\))')


def owner(path: Path) -> str | None:
    name = path.as_posix()
    for pattern, writer in WRITERS:
        if pattern.endswith("/**") and name.startswith(pattern[:-2]):
            return writer
        if path.match(pattern):
            return writer
    return None


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


def ablated(rule: str) -> bool:
    chosen = os.environ.get("AEW_EVIDENCE_ABLATE")
    return bool(os.environ.get("AEW_EVIDENCE_PLANT")) and (
        chosen == rule or (rule == "stacks" and chosen in {"header-only", "zero-byte"}))
