"""Check the states and stacks in published lane evidence."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "helpers"))
from evidence_files import FRAME, WATCHDOG_HEADER, owner, stack_file, state  # noqa: E402


def evidence_problems(root: Path, *, kind: str | None = None, require_stacks: bool = False) -> list[str]:
    """Check published states and warning-death stacks, also used by the hosted proof."""
    defects = []

    def report(rule: str, detail: str) -> None:
        defects.append(f"evidence defect: [{rule}] {detail}")

    files = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    texts = {path: data.decode("utf-8", errors="replace") for path, data in files.items()}
    inventories = {path: text for path, text in texts.items() if path.name == "inventory.txt"}
    if not inventories:
        report("inventory", "missing publication inventory")
    for inventory, listing in inventories.items():
        if "evidence defect: job cap exceeded" in listing:
            report("cap", "job cap exceeded")
        if "scan unavailable" in listing:
            report("scan-unavailable", "scan unavailable")
        if "unlisted writer" in listing:
            report("writer-source", "unlisted writer in the evidence source")
        for path, data in files.items():
            if not path.is_relative_to(inventory.parent):
                continue
            relative = path.relative_to(inventory.parent)
            if owner(relative) is None:
                report("writer-path", f"{relative}: unlisted writer")
            label = state(relative, data)
            if f"{label} {relative.as_posix()} (" not in listing:
                report("label", f"{relative}: missing or false publication state ({label})")
            text = texts[path]
            if path.name == "collection-incomplete.txt":
                report("collection", "collection incomplete")
            if ((path.name == "tools-unavailable.txt" and "unavailable" in text)
                    or ("snapshots" in relative.parts and text.startswith("evidence defect: py-spy unavailable"))):
                report("tools", text.strip())
            first, _, dump = text.partition("\n")
            header_denies_fire = first.rstrip("\r").endswith("; not fired") or "; not fired; monotonic " in first
            if stack_file(relative) and header_denies_fire and (FRAME.search(dump) or dump.startswith("Timeout (")):
                report("contradiction", f"{relative}: header denies a recorded fire")
            if path.name.startswith("hang-"):
                if "was still running after" in text and not FRAME.search(text):
                    report("false-timeout", f"{relative}: timeout claimed without stacks")
                if "fired after" in text and not FRAME.search(text):
                    report("false-fired", f"{relative}: fired claimed without stacks")
            if (stack_file(relative) and ("every thread's stack" in text or "Timeout (" in text)
                    and not FRAME.search(text)):
                report("false-stack", f"{relative}: stack header without stacks")
    if kind == "cancel" and any(path.stem == "cutoff" for path in files):
        report("false-cutoff", "cancel: cutoff marker claimed during the planted cancellation")
    if kind and kind not in {"normal", "cancel", "oom"}:
        names = {path.stem for path in files}
        expected = {"deadline": {"session-deadline"}, "time-limit": {"cutoff"},
                    "hang": {"session-deadline", "cutoff"}}.get(kind, set())
        if expected and not names.intersection(expected):
            report("kind", f"{kind}: missing kind marker")
    running = set()
    for path, text in texts.items():
        if path.name.startswith("hang-"):
            match = WATCHDOG_HEADER.match(text)
            if match:
                running.add(match[1])
        elif path.name.startswith("running-"):
            running.update(text.splitlines())
    if require_stacks or kind in {"cancel", "sigkill", "deadline", "time-limit", "hang"}:
        if not running or "<unrecognized test>" in running:
            report("running", "missing running test name")
    if require_stacks:
        for node in running:
            source = node.split("::", 1)[0].replace("\\", "/")
            function = node.rsplit("::", 1)[-1].split("[", 1)[0]
            matched = False
            for path, text in texts.items():
                tags = [text]
                tags.extend(reason.read_text(encoding="utf-8", errors="replace")
                            for reason in path.parent.glob("reason*.txt"))
                # Autopsy's reason tags its stack file. Snapshots and watchdogs tag themselves.
                if path.name.startswith("worker-") and "-deadline-stacks" in path.name:
                    worker = path.name.split("-deadline-stacks", 1)[0]
                    pid_file = path.parent / f"{worker}-pid.txt"
                    if pid_file.is_file():
                        pid = pid_file.read_text().strip()
                        tags.extend(header for hp, header in texts.items()
                                    if hp.name == f"hang-{worker.removeprefix('worker-')}-{pid}.txt")
                tagged = any(node in tag for tag in tags)
                if not tagged and node.endswith(function):
                    tagged = any(node + "[" in tag for tag in tags)
                for frame in FRAME.finditer(text) if tagged else ():
                    file = frame.group("file") or frame.group("spy_file")
                    called = frame.group("function") or frame.group("spy_function")
                    if ("/" + file.replace("\\", "/")).endswith("/" + source) and called == function:
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                report("stacks", f"{node}: no stack from the running test's module")
    return sorted(set(defects))
