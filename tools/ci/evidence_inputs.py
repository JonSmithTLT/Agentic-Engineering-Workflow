"""Select the priority evidence once, before either scanned publication."""

from __future__ import annotations

import shutil
import sys
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
    present = copied = False
    if not source.is_dir() or is_link(source):
        return present, copied
    for path in sorted(source.rglob("*")):
        if any(is_link(p) for p in (path, *path.parents) if p.is_relative_to(source)) or not path.is_file():
            continue
        present = True
        relative = path.relative_to(source)
        if priority(relative):
            out = target / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
            copied = True
    return present, copied


if __name__ == "__main__":
    present, copied = prepare(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"present={str(present).lower()}")
    print(f"watchdog={str(copied).lower()}")
