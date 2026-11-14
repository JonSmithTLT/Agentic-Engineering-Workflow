"""Stage bounded text evidence and release its contents only after a clean scan."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

JOB_CAP = 64 * 1024 * 1024
INDEX_CAP = 64 * 1024
SAFE_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")


def stage(source: Path, destination: Path) -> str:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    with TemporaryDirectory(dir=destination.parent) as temporary:
        candidate = Path(temporary) / "contents"
        candidate.mkdir()
        left = JOB_CAP - INDEX_CAP
        kept = omitted = 0
        inventory = bytearray()
        for file in sorted(source.rglob("*.txt")):
            relative = file.relative_to(source)
            if (not any(part in {"autopsy", "harness-runs"} for part in relative.parts[:-1])
                    and not file.name.startswith("hang-")):
                continue
            if any(not SAFE_PART.fullmatch(part) for part in relative.parts):
                omitted += 1
                continue
            if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                   for p in (file, *file.parents) if p.is_relative_to(source)):
                omitted += 1
                continue
            try:
                with file.open("rb") as stream:
                    data = stream.read(min(left, 4 * 1024 * 1024) + 1)
                data.decode("utf-8")
            except (OSError, UnicodeError):
                omitted += 1
                continue
            if len(data) > min(left, 4 * 1024 * 1024) or b"\x00" in data:
                omitted += 1
                continue
            out = candidate / relative
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
                ["gitleaks", "dir", "--redact", "--no-banner", "--report-format", "json",
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
