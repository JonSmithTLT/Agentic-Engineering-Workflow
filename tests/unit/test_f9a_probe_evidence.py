"""The F9-A MS0 probe's committed evidence and source hold nothing of the hosts they ran on (F9-A plan v4, amendment 1,
A9; ADR-0017 D8).

The probe ran on the operator's Windows machine and on the Rocky 8 reference VM. Its raw run trees carry host paths
(every event's ``location.directory``, the binary's path, the run directories) and stay private; only summaries,
tables and source excerpts are committed. Two guards keep it so, over the evidence directory and the probe's own
source (``tests/live/f9a_delivery_probe/``, including its shell scripts):

- no absolute Windows or POSIX path, and no JSON key that carries one (``location``, ``directory``, ``binary``), in
  the fast tier on every platform;
- no word of the local account's name, run locally before committing and skipped in CI, where the account is the
  runner's and means nothing. It names no account itself: it asks the operating system.
"""

from __future__ import annotations

import getpass
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "implementation" / "adr" / "evidence" / "f9a-delivery-probe-2026-10-10"
PROBE = ROOT / "tests" / "live" / "f9a_delivery_probe"
SCANNED = (EVIDENCE, PROBE)

# What each directory must hold, so that neither guard passes over an empty or renamed directory.
EXPECTED = {
    EVIDENCE: {"README.md", "probe-results.md", "summary-windows.json", "summary-rocky8.json", "table-windows.md",
               "table-rocky8.md", "src-excerpts.txt"},
    PROBE: {"probe.py", "fake_model.py", "summarize.py", "table.py", "timeline.py", "p5_table.py", "src_excerpts.py",
            "run_case.sh", "run_linux.sh"},
}

HOST_PATHS = {
    # A drive path; the lookbehind keeps the "s:/" of "https://" out.
    "drive path": re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]"),
    "UNC prefix": re.compile(r"\\\\"),
    "POSIX home": re.compile(r"/home/"),
    "macOS user directory": re.compile(r"/Users/"),
    "root's home": re.compile(r"/root/"),
    "%APPDATA%": re.compile(r"%APPDATA%"),
    "%USERPROFILE%": re.compile(r"%USERPROFILE%"),
    "home-relative path": re.compile(r"~/"),
}
PATH_KEYS = frozenset({"location", "directory", "binary"})


def files() -> list[Path]:
    return sorted(p for d in SCANNED for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def keys_at_any_depth(value: Any, where: str = "") -> Iterator[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in PATH_KEYS:
                yield f"{where}/{k}"
            yield from keys_at_any_depth(v, f"{where}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from keys_at_any_depth(v, f"{where}[{i}]")


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def test_both_directories_hold_what_the_guards_scan():
    for directory, names in EXPECTED.items():
        present = {p.name for p in directory.iterdir() if p.is_file()}
        assert names <= present, f"{directory.relative_to(ROOT).as_posix()} lacks {sorted(names - present)}"


def test_the_f9a_probe_evidence_holds_no_host_path_or_location_key():
    found = []
    for path in files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        for name, pattern in HOST_PATHS.items():
            found += [f"{rel}:{line_of(text, m.start())}: {name}" for m in pattern.finditer(text)]
        if path.suffix == ".json":
            found += [f"{rel}: key {k}" for k in keys_at_any_depth(json.loads(text))]
    assert found == []


def local_account_words() -> set[str]:
    """The local account as the operating system names it: the login name and the home directory's last component,
    each whole and each space-separated part of it."""
    whole = set()
    try:
        whole.add(getpass.getuser())
    except (KeyError, OSError):  # no login name in this environment
        pass
    whole.add(Path.home().name)
    return {w for name in whole for w in (name, *name.split()) if w.strip()}


@pytest.mark.skipif(bool(os.environ.get("CI")), reason="local-only: in CI the account is the runner's")
def test_the_f9a_probe_evidence_names_no_local_account():
    words = local_account_words()
    assert words, "the local account could not be read"
    # Case-sensitive and whole-word, so random ids (``ses_…``, ``msg_…``) cannot match by accident.
    patterns = [re.compile(r"(?<!\w)" + re.escape(w) + r"(?!\w)") for w in sorted(words)]
    found = []
    for path in files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        # Report where, never what: the failure message must not repeat the name.
        found += [f"{rel}:{line_of(text, m.start())}" for p in patterns for m in p.finditer(text)]
    assert found == [], "the local account's name appears at these places"
