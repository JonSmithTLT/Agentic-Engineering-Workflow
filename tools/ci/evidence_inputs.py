"""Select the priority evidence once, before either scanned publication."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/helpers"))
from evidence_files import stack_file  # noqa: E402
from stage_evidence import is_link  # noqa: E402


def priority(path: Path) -> bool:
    return (stack_file(path) or path.name.startswith("runner-resources-")
            or ("autopsy" in path.parts and (any(p.startswith("session-") for p in path.parts)
                                            or path.name.startswith(("reason", "stacks")))))


def prepare(source: Path, target: Path, *, job: str = "", collection: str = "success",
            copy_priority: bool = True, unavailable: tuple[str, ...] = (), attachment: str = "") -> tuple[bool, bool]:
    target.mkdir(parents=True, exist_ok=True)
    names = target.with_name(target.name.removesuffix("-watchdog-input") + "-names")
    names.mkdir(parents=True, exist_ok=True)
    header = "typed source names\nfinding inventory.txt (publisher)\n"
    name_index = []
    if job:
        digest = hashlib.sha256(job.encode()).hexdigest()
        (names / "job-label-sha256.txt").write_text(digest + "\n", encoding="utf-8")
        name_index.append("finding job-label-sha256.txt (evidence_inputs)\n")
    if collection != "success":
        (names / "collection-incomplete.txt").write_text("evidence defect: collection incomplete\n", encoding="utf-8")
        name_index.append("finding collection-incomplete.txt (evidence_inputs)\n")
    if unavailable:
        (names / "tools-unavailable.txt").write_text("".join(f"evidence defect: {tool} unavailable\n"
                                                             for tool in unavailable), encoding="utf-8")
        name_index.append("finding tools-unavailable.txt (evidence_inputs)\n")
    if attachment in {"unelevated", "sudo -n", "unavailable"}:
        (names / "runner-resources-attachment.txt").write_text(attachment + "\n", encoding="utf-8")
        name_index.append("finding runner-resources-attachment.txt (lane_step)\n")
    has_source = source.is_dir() and not is_link(source)
    from watchdog import SOURCE_TEST

    for path in source.glob("running-*.txt") if has_source else ():
        if not re.fullmatch(r"running-\d+\.txt", path.name) or is_link(path):
            continue
        try:
            node = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue  # a live writer moved or locked it
        safe = node if SOURCE_TEST.fullmatch(node) else "<unrecognized test>"
        (names / path.name).write_text(safe + "\n", encoding="utf-8")
        name_index.append(f"finding {path.name} (watchdog)\n")
    (names / "inventory.txt").write_text(header + "".join(name_index), encoding="utf-8")
    present = copied = False
    if not has_source or not copy_priority:
        return present, copied
    for path in sorted(source.rglob("*")):
        if any(is_link(p) for p in (path, *path.parents) if p.is_relative_to(source)) or not path.is_file():
            continue
        present = True
        relative = path.relative_to(source)
        try:
            if priority(relative):
                out = target / relative
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, out)
                copied = True
        except OSError:
            # A surviving writer can remove a file or hold it open amid collection.
            continue
    return present, copied


if __name__ == "__main__":
    started = time.monotonic()
    present, copied = prepare(Path(sys.argv[1]), Path(sys.argv[2]), job=os.environ.get("JOB_LABEL", ""),
                              collection=os.environ.get("COLLECTION_OUTCOME", "success"),
                              attachment=os.environ.get("ATTACHMENT_PROBE", ""),
                              unavailable=tuple(label for key, label in (("SCANNER_AVAILABLE", "scan"),
                                                                          ("SPY_AVAILABLE", "py-spy"))
                                                if os.environ.get("JOB_LABEL") and os.environ.get(key) != "true"),
                              copy_priority=os.environ.get("LANE_OUTCOME") != "success"
                              or os.environ.get("COLLECTION_OUTCOME", "success") != "success")
    print(f"present={str(present).lower()}")
    print(f"watchdog={str(copied).lower()}")
    print(f"evidence timing prepare {time.monotonic() - started:.3f}s", file=sys.stderr)
