"""Stage bounded text evidence and withhold the files identified by the scanner."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

JOB_CAP = 64 * 1024 * 1024
INDEX_CAP = 64 * 1024
FINDINGS_EXIT = 23
CONFIG = Path(__file__).with_name("evidence-gitleaks.toml").resolve()
SAFE_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
EXTRA_TEXT = {"junit.xml", "vertical-summary.txt", "dispatch.txt"}
WORKDIR_TEXT = {".stdout", ".stderr", ".log", ".txt", ".jsonl", ".json", ".yaml", ".yml", ".md", ".py"}


def visible(part: str) -> str:
    if SAFE_PART.fullmatch(part):
        return part
    digest = hashlib.sha256(part.encode()).hexdigest()[:12]
    return f"file-{digest}-{re.sub(r'[^A-Za-z0-9_.-]', '_', part)[-90:]}"


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


@dataclass(frozen=True)
class Hit:
    rule: str
    line: int
    end_line: int
    column: int
    match: str


def findings(report: Path, candidate: Path, staged: set[Path]) -> dict[Path, list[Hit]]:
    """Accept only findings that can be attributed to an exact staged file."""
    hits = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(hits, list) or not hits:
        raise ValueError("missing gitleaks findings")
    withheld: dict[Path, list[Hit]] = {}
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("File"), str):
            raise ValueError("missing gitleaks file")
        path = Path(hit["File"])
        if path.is_absolute():
            path = path.relative_to(candidate)
        elif path not in staged:
            path = (candidate.parent / path).relative_to(candidate)
        rule = hit.get("RuleID")
        if path not in staged or not isinstance(rule, str) or not SAFE_PART.fullmatch(rule):
            raise ValueError("unattributable gitleaks finding")
        line = hit.get("StartLine")
        if type(line) is not int or line < 1:
            raise ValueError("missing gitleaks line")
        end = hit.get("EndLine")
        column = hit.get("StartColumn")
        match = hit.get("Match")
        withheld.setdefault(path, []).append(Hit(rule, line, end if type(end) is int else 0,
                                               column if type(column) is int else 0,
                                               match if isinstance(match, str) else ""))
    return withheld


def scan(candidate: Path, report: Path, staged: set[Path]) -> dict[Path, list[Hit]]:
    report.unlink(missing_ok=True)
    result = subprocess.run(
        ["gitleaks", "dir", "--no-banner", "--ignore-gitleaks-allow", "--report-format", "json",
         "--config", str(CONFIG), "--exit-code", str(FINDINGS_EXIT),
         "--report-path", str(report), str(candidate)],
        cwd=report.parent, capture_output=True, timeout=60, check=False,
    )
    if result.returncode == 0:
        return {}
    if result.returncode != FINDINGS_EXIT:
        raise ValueError("gitleaks failed")
    return findings(report, candidate, staged)


def mask(file: Path, hits: list[Hit]) -> bool:
    """Use byte offsets and exact reported matches. Uncertain spans stay private."""
    original = file.read_bytes()
    offsets = [0, *(match.end() for match in re.finditer(b"\n", original)), len(original)]
    spans = []
    for hit in hits:
        if not (hit.match and hit.column > 0 and hit.line <= hit.end_line < len(offsets)):
            return False
        # The pinned scanner can report a column one byte late on lines after the first.
        start = offsets[hit.line - 1] + max(0, hit.column - 2)
        raw = hit.match.encode()
        # Some rules report the secret inside the match at the reported column.
        window = original[start:offsets[hit.end_line]]
        if window.count(raw) != 1:
            return False
        start += window.index(raw)
        spans.append((start, start + len(raw), hit.rule))
    merged: list[tuple[int, int, str]] = []
    for start, end, rule in sorted(spans):
        if merged and start < merged[-1][1]:
            left, right, first_rule = merged.pop()
            merged.append((left, max(right, end), first_rule))
        else:
            merged.append((start, end, rule))
    for start, end, rule in reversed(merged):
        replacement = f"<redacted:{rule}>".encode() + b"\n" * original[start:end].count(b"\n")
        original = original[:start] + replacement + original[end:]
    file.write_bytes(original)
    return True


def stage(source: Path, destination: Path) -> str:
    source, destination = source.absolute(), destination.absolute()
    if destination.exists():
        raise FileExistsError(destination)
    with TemporaryDirectory(dir=destination.parent) as temporary:
        candidate = Path(temporary) / "contents"
        candidate.mkdir()
        left = JOB_CAP - INDEX_CAP
        kept = omitted = 0
        inventory = bytearray()
        staged: set[Path] = set()

        def files():
            if not source.is_dir() or is_link(source):
                return
            for directory, subdirs, names in os.walk(source):
                root = Path(directory)
                subdirs[:] = sorted(name for name in subdirs if not is_link(root / name))
                yield from (root / name for name in sorted(names))

        for file in files():
            relative = file.relative_to(source)
            diagnostic = (file.suffix == ".txt"
                          and ({"autopsy", "harness-runs"}.intersection(relative.parts[:-1])
                               or file.name.startswith("hang-")))
            if not diagnostic and file.name not in EXTRA_TEXT:
                continue
            try:
                if any(is_link(p) for p in (file, *file.parents) if p.is_relative_to(source)) or not file.is_file():
                    omitted += 1
                    continue
                if "workdir" in relative.parts:
                    original = Path(file.name.removesuffix(".txt"))
                    forbidden = any(word in part.lower() for part in relative.parts
                                    for word in ("credential", "secret", "auth.json", ".env", ".git"))
                    if forbidden or (original.suffix.lower() not in WORKDIR_TEXT
                                     and original.name != "heartbeat"):
                        omitted += 1
                        continue
                with file.open("rb") as stream:
                    data = stream.read(min(left, 4 * 1024 * 1024) + 1)
                data.decode("utf-8")
            except (OSError, UnicodeError):
                omitted += 1
                continue
            if len(data) > min(left, 4 * 1024 * 1024) or b"\x00" in data:
                omitted += 1
                continue
            parts = tuple(visible(part) for part in relative.parts)
            if "workdir" in relative.parts and ".aew" in relative.parts:
                index = relative.parts.index("workdir")
                parts = (*parts[:index], "harness", *parts[index + 1:])
            out = candidate.joinpath(*parts)
            if out.exists():
                omitted += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            staged.add(out.relative_to(candidate))
            left -= len(data)
            line = f"file-{kept:05d} ({len(data)} bytes)\n".encode()
            if len(inventory) + len(line) < INDEX_CAP - 512:
                inventory.extend(line)
            kept += 1

        report = Path(temporary) / "scan.json"
        publish = False
        try:
            initial = scan(candidate, report, staged)
            masked = {path for path, hits in initial.items() if mask(candidate / path, hits)}
            withheld = {path: hits for path, hits in initial.items() if path not in masked}
            for path in withheld:
                (candidate / path).unlink()
            if masked:
                remaining = scan(candidate, report, staged - withheld.keys())
                withheld.update(remaining)
                for path in remaining:
                    (candidate / path).unlink()
            entries = {
                (path.as_posix(), hit.rule, hit.line, action)
                for action, group in (("masked", {p: initial[p] for p in masked - withheld.keys()}),
                                      ("withheld", withheld))
                for path, hits in group.items() for hit in hits
            }
            listing = "".join(f"{action} {path}:{line} ({rule})\n"
                              for path, rule, line, action in sorted(entries)).encode()
            if len(listing) > INDEX_CAP - 512:
                raise ValueError("gitleaks findings exceed inventory cap")
            if sum((candidate / path).stat().st_size for path in staged - withheld.keys()) > JOB_CAP - INDEX_CAP:
                raise ValueError("masked evidence exceeds job cap")
            if initial:
                inventory = bytearray(listing)
            status = (f"gitleaks masked {len(masked - withheld.keys())} files; withheld {len(withheld)} files"
                      if initial else "gitleaks clean")
            publish = True
        except (OSError, ValueError, subprocess.TimeoutExpired):
            status = "gitleaks scan unavailable"
        header = f"{status}\n{kept} candidate files, {omitted} omitted\n"
        if publish:
            candidate.rename(destination)
        else:
            destination.mkdir()
        (destination / "inventory.txt").write_bytes(header.encode() + inventory)
        return status


if __name__ == "__main__":
    destination = Path(sys.argv[2])
    print(stage(Path(sys.argv[1]), destination))
    for line in (destination / "inventory.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith(("masked ", "withheld ")):
            print(line, file=sys.stderr)
