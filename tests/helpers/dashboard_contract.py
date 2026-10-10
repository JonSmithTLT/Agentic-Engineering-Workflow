"""The dashboard contract's history and the maps and history search change note, as the tests read them (register
F20.8; ``docs/design/proposals/dashboard-maps-and-history-search-v0.1.md``, "Readiness on the main line").

* The 0.1.2 contract comes from git, at the commit its accepted review names, and its digest is checked: every later
  minor version is compared with it, whatever the working tree's contract has become.
* The note's appendix is its fenced YAML blocks after the appendix heading, merged in order into the 0.1.2 contract.
* The note is checked against the accepted contract in one of three modes, decided by its status line: one-way
  before adoption, strict at the adopted version, and the compatibility check for a later minor version.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from aew.dashboard import contract as CT

ROOT = Path(__file__).resolve().parents[2]
NOTE_REL = "docs/design/proposals/dashboard-maps-and-history-search-v0.1.md"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APPENDIX_HEADING = re.compile(r"^## Appendix A\b")
YAML_FENCE = re.compile(r"^```yaml\s*$")
STATUS_LINE = re.compile(r"^- \*\*Status:\*\*")
ADOPTED = re.compile(r"as adopted in contract `(?P<version>[0-9.]+)` at `(?P<sha>[0-9a-f]{7,40})`; served at "
                     r"adoption: (?P<routes>(?:`/[^`]*`(?:, )?)+)")


def git_show(commit: str, rel: str, root: Path = ROOT) -> bytes:
    """A file as committed; a clear failure when this clone lacks the commit (CI's core job has full history)."""
    got = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{rel}"], capture_output=True,
                         creationflags=NO_WINDOW)
    if got.returncode != 0:
        raise AssertionError(f"git cannot show {commit}:{rel} in this clone (a shallow clone lacks it; fetch the "
                             f"full history): {got.stderr.decode(errors='replace').strip()}")
    return got.stdout


def approval(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / CT.APPROVAL_REL).read_text(encoding="utf-8"))


def base_contract(root: Path = ROOT) -> dict[str, Any]:
    """The accepted 0.1.2 contract, from git at its reviewed commit, its digest checked against the approval."""
    review = CT.base_review(approval(root))
    raw = git_show(review["reviewed_commit"], CT.CONTRACT_REL, root)
    assert hashlib.sha256(raw).hexdigest() == review["sha256"], "the 0.1.2 contract at its reviewed commit"
    return yaml.safe_load(raw.decode("utf-8"))


def note_text(root: Path = ROOT) -> str:
    return (root / NOTE_REL).read_text(encoding="utf-8")


def appendix(text: str) -> list[dict[str, Any]]:
    """The appendix's YAML blocks, in order: every ```yaml fence after the appendix heading."""
    blocks: list[dict[str, Any]] = []
    inside, current, block = False, None, []
    for line in text.splitlines():
        if APPENDIX_HEADING.match(line):
            inside = True
            continue
        if not inside:
            continue
        if current is None and YAML_FENCE.match(line):
            current, block = "yaml", []
            continue
        if current is not None and line.strip() == "```":
            loaded = yaml.safe_load("\n".join(block))
            assert isinstance(loaded, dict), "every appendix block is a mapping merged into the contract"
            blocks.append(loaded)
            current = None
            continue
        if current is not None:
            block.append(line)
    assert current is None, "an appendix block is not closed"
    return blocks


def proposed(text: str, base: dict[str, Any]) -> dict[str, Any]:
    """The contract the note proposes: 0.1.2 with the appendix merged in."""
    return CT.merged(base, *appendix(text))


def adopted(text: str) -> tuple[str, str, list[str]] | None:
    """The note's adopted line, ``(version, sha, served routes)``, or None before adoption. Read from the status
    bullet only, so prose that describes the line's form never counts as one."""
    status, collecting = [], False
    for line in text.splitlines():
        if STATUS_LINE.match(line):
            collecting = True
        elif collecting and (line.startswith("- **") or not line.strip()):
            break
        if collecting:
            status.append(line.strip())
    m = ADOPTED.search(" ".join(status))
    if m is None:
        return None
    return m.group("version"), m.group("sha"), re.findall(r"`(/[^`]*)`", m.group("routes"))


def stripped(document: dict[str, Any]) -> dict[str, Any]:
    return CT.normalized({"paths": document.get("paths"), "components": document.get("components")})


def note_problems(text: str, accepted: dict[str, Any], base: dict[str, Any]) -> list[str]:
    """Why the note and the accepted contract disagree, in the mode the note's status line sets (change note,
    "Readiness on the main line"); empty when they agree. The appendix itself must always compile and pass the
    compatibility check against 0.1.2."""
    mine = proposed(text, base)
    base_paths = set(base["paths"])
    problems = [f"appendix: {p}" for p in CT.compile_problems(mine) + CT.compatibility(base, mine, base_paths)]
    problems += [f"contract: {p}" for p in CT.compile_problems(accepted)]
    line = adopted(text)
    version = str(accepted["info"]["version"])
    if line is None:  # one-way: any amendment of the additions passes, a change to a 0.1.2 shape does not
        problems += [f"contract against 0.1.2: {p}" for p in CT.compatibility(base, accepted, base_paths)]
    elif version == line[0]:  # strict at the adopted version: the note and the contract cannot drift apart
        if stripped(mine) != stripped(accepted):
            problems.append(f"contract {version} differs from the note's appendix, which it adopted")
    else:  # a later minor version: what was served at adoption stays equal; what was pending may change
        if CT.parse_version(version) < CT.parse_version(line[0]):
            problems.append(f"contract {version} is older than the adopted {line[0]}")
        covered = base_paths | set(line[2])
        problems += [f"contract against {line[0]}: {p}" for p in CT.compatibility(mine, accepted, covered)]
    return problems
