"""Stage bounded text evidence and release its contents only after a clean scan."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

JOB_CAP = 64 * 1024 * 1024
INDEX_CAP = 64 * 1024
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
            left -= len(data)
            line = f"file-{kept:05d} ({len(data)} bytes)\n".encode()
            if len(inventory) + len(line) < INDEX_CAP - 512:
                inventory.extend(line)
            kept += 1

        report = Path(temporary) / "scan.json"
        try:
            result = subprocess.run(
                ["gitleaks", "dir", "--redact", "--no-banner", "--ignore-gitleaks-allow", "--report-format", "json",
                 "--report-path", str(report), str(candidate)],
                cwd=temporary, capture_output=True, timeout=60, check=False,
            )
            if result.returncode == 0:
                status = "gitleaks clean"
            else:
                hits = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else []
                rules = sorted({hit["RuleID"] for hit in hits if SAFE_PART.fullmatch(hit.get("RuleID", ""))})
                status = f"gitleaks withheld contents ({', '.join(rules)})" if rules else "gitleaks scan failed"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            status = "gitleaks scan unavailable"
        header = f"{status}\n{kept} candidate files, {omitted} omitted\n"
        if status == "gitleaks clean":
            candidate.rename(destination)
        else:
            destination.mkdir()
        (destination / "inventory.txt").write_bytes(header.encode() + inventory)
        return status


if __name__ == "__main__":
    print(stage(Path(sys.argv[1]), Path(sys.argv[2])))
