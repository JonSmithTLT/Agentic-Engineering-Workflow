"""Select the priority evidence once, before either scanned publication."""

from __future__ import annotations

import re
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
    names = target.with_name(target.name.removesuffix("-watchdog-input") + "-names")
    names.mkdir(parents=True, exist_ok=True)
    name_index = []
    present = copied = False
    if not source.is_dir() or is_link(source):
        (names / "inventory.txt").write_text("typed source names\n" + "".join(name_index), encoding="utf-8")
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
    (names / "inventory.txt").write_text("typed source names\n" + "".join(name_index), encoding="utf-8")
    return present, copied


if __name__ == "__main__":
    present, copied = prepare(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"present={str(present).lower()}")
    print(f"watchdog={str(copied).lower()}")
