"""Select the priority evidence once, before either scanned publication."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

from stage_evidence import is_link


def priority(path: Path) -> bool:
    return (path.name.startswith(("hang-", "runner-resources-"))
            or "snapshots" in path.parts
            or "-stacks" in path.name
            or ("autopsy" in path.parts and (any(p.startswith("session-") for p in path.parts)
                                            or path.name.startswith(("reason", "stacks")))))


def prepare(source: Path, target: Path) -> tuple[bool, bool]:
    target.mkdir(parents=True, exist_ok=True)
    names = target.with_name(target.name.removesuffix("-watchdog-input") + "-names")
    names.mkdir(parents=True, exist_ok=True)
    header = "typed source names\nfinding inventory.txt (publisher)\n"
    name_index = []
    metadata = source / "runner-resources-job.txt"
    if metadata.is_file():
        job = json.loads(metadata.read_text(encoding="utf-8"))["job_label"]
        digest = hashlib.sha256(job.encode()).hexdigest()
        (names / "job-label-sha256.txt").write_text(digest + "\n", encoding="utf-8")
        name_index.append("finding job-label-sha256.txt (evidence_inputs)\n")
    present = copied = False
    if not source.is_dir() or is_link(source):
        (names / "inventory.txt").write_text(header + "".join(name_index), encoding="utf-8")
        return present, copied
    for path in sorted(source.rglob("*")):
        if any(is_link(p) for p in (path, *path.parents) if p.is_relative_to(source)) or not path.is_file():
            continue
        present = True
        relative = path.relative_to(source)
        if re.fullmatch(r"running-\d+\.txt", path.name):
            from watchdog import SOURCE_TEST

            node = path.read_text(encoding="utf-8").strip()
            safe = node if SOURCE_TEST.fullmatch(node) else "<unrecognized test>"
            (names / path.name).write_text(safe + "\n", encoding="utf-8")
            name_index.append(f"finding {path.name} (watchdog)\n")
        if priority(relative):
            out = target / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
            copied = True
    (names / "inventory.txt").write_text(header + "".join(name_index), encoding="utf-8")
    return present, copied


if __name__ == "__main__":
    started = time.monotonic()
    present, copied = prepare(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"present={str(present).lower()}")
    print(f"watchdog={str(copied).lower()}")
    print(f"evidence timing prepare {time.monotonic() - started:.3f}s", file=sys.stderr)
