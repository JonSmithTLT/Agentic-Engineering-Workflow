"""Check the states and stacks in published lane evidence."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "helpers"))
from bounds import CHEAP_FILE  # noqa: E402
from evidence_files import (  # noqa: E402
    FRAME,
    FRESH_S,
    PREFIX,
    WATCHDOG_HEADER,
    entries,
    failure_overflow,
    owner,
    priority,
    publishable,
    report_json,
    stack_file,
    state,
)


def test_frame(node: str, frames: str) -> bool:
    source, _, test = node.partition("::")
    function = test.split("[", 1)[0].split("::")[-1]
    for frame in FRAME.finditer(frames):
        file = frame.group("file") or frame.group("spy_file")
        called = frame.group("function") or frame.group("spy_function")
        if ("/" + file.replace("\\", "/")).endswith("/" + source.replace("\\", "/")) and called == function:
            return True
    return False


def rows_named(texts: dict, name: str):
    for path, text in texts.items():
        if path.name == name:
            try:
                row = json.loads(text)
                if isinstance(row, dict):
                    yield row
            except ValueError:
                continue


ELISION = re.compile(r"Use -v+ to (?:get more diff|show)|Omitting \d+ identical items|Skipping \d+ identical leading")


def failure_problems(path: Path, report: dict) -> list[str]:
    problems = []

    def defect(rule: str, detail: str) -> None:
        problems.append(f"evidence defect: [{rule}] {detail}")

    if not isinstance(report.get("results"), dict):
        return ["evidence defect: [failure-report] lane report has no results mapping"]
    for node, result in report.get("results", {}).items():
        if not isinstance(result, dict):
            defect("failure-report", f"{node}: invalid result")
            continue
        if result.get("outcome") not in ("failed", "error"):
            continue
        failures = result.get("failures") or [{}]
        if not isinstance(failures, list):
            defect("failure-report", f"{node}: invalid failure records")
            continue
        for failure in failures:
            if not isinstance(failure, dict) or any(not isinstance(failure.get(key, ""), str)
                                                    for key in ("phase", "crash", "longrepr", "overflow")):
                defect("failure-report", f"{node}: invalid failure record")
                continue
            phase = failure.get("phase") or "unknown phase"
            detail = f"{node} ({phase})"
            text = failure.get("longrepr") or ""
            crash = failure.get("crash") or ""
            location = failure.get("overflow")
            if location:
                relative = Path(location)
                if (len(relative.parts) != 2 or not failure_overflow(relative)
                        or not (path.parent / relative).is_file()):
                    defect("failure-overflow", f"{detail}: missing full failure file")
                else:
                    try:
                        text = (path.parent / relative).read_text(encoding="utf-8")
                    except (OSError, UnicodeError):
                        defect("failure-overflow", f"{detail}: unreadable full failure file")
            # ReprFileLocation supplies a path, line and message. Some collection and native reports have just text.
            message = re.split(r":[0-9]+: ", crash, maxsplit=1)[-1].strip()
            # Native exception groups indent their exception lines with one or more tree bars.
            lines = (re.sub(r"^(?:E\s+)?(?:\|\s+)*", "", row.strip()) for row in text.splitlines())
            # Compare the actual exception line or its native file:line rendering. A class name in source code
            # (e.g. pytest.raises) does not establish the cause. Pytest can prefix rewritten asserts with the type.
            matching = any(row == message or row == "AssertionError: " + message
                           or re.split(r":[0-9]+: ", row, maxsplit=1)[-1] == message
                           or row.startswith(message) and len(crash) == CHEAP_FILE for row in lines)
            if not failure.get("longrepr") or not message or not matching:
                defect("failure-text", f"{detail}: no failure text with its exception line")
            if ELISION.search(text):
                defect("failure-elision", f"{detail}: pytest elided failure text")
    return problems


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
        chunks = [p for p in texts if p.parent == inventory.parent
                  and re.fullmatch(r"inventory-part-[0-9]+\.txt", p.name)]
        declared = re.search(r"(?m)^inventory parts: ([0-9]+)$", listing)
        expected_parts = int(declared[1]) if declared else 0
        if len(chunks) != expected_parts or any(not 1 <= int(p.stem.split("-")[-1]) <= expected_parts for p in chunks):
            report("inventory", "missing or unexpected continuation of the publication inventory")
        listing += "".join(texts[p] for p in chunks)
        for line in listing.splitlines():
            if line.startswith("evidence defect: ") and ": withheld/omitted" in line:
                report("omission", line.removeprefix("evidence defect: "))
        if "evidence defect: job cap exceeded" in listing:
            report("cap", "job cap exceeded")
        if "evidence defect: inventory cap exceeded" in listing:
            report("cap", "inventory cap exceeded")
        if "scan unavailable" in listing:
            report("scan-unavailable", "scan unavailable")
        if "unlisted writer" in listing:
            report("writer-source", "unlisted writer in the evidence source")
        for path, data in files.items():
            if not path.is_relative_to(inventory.parent):
                continue
            relative = path.relative_to(inventory.parent)
            if path in chunks:
                continue
            if report_json(relative):
                try:
                    doc = json.loads(texts[path])
                except ValueError:
                    report("failure-report", f"{relative}: unreadable scanned JSON")
                else:
                    if isinstance(doc, dict) and doc.get("schema") == "aew/lane-report/v1":
                        defects.extend(failure_problems(path, doc))
            if owner(relative) is None:
                report("writer-path", f"{relative}: unlisted writer")
            if (relative.name != "inventory.txt" and listing.startswith("gitleaks ")
                    and (not publishable(relative) or (inventory.parent.name.endswith("-watchdog")
                                                      and not priority(relative)))):
                report("file-class", f"{relative}: outside the published bundle's file classes")
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
    abrupt = {"sigkill": "controller-lost", "worker-killed": "worker-killed", "oom": "oom", "cancel": "cancelled",
              "time-limit-github": "interrupted"}
    if kind in abrupt:
        records = {}
        causes = {abrupt[kind]: kind}
        if kind in {"cancel", "time-limit-github"}:
            causes.update(cancelled=kind, interrupted=kind)
        if kind == "oom":
            # A cgroup event can coincide with a separate worker crash. Each observation needs its own sample.
            causes["worker-killed"] = "worker-killed"
        for path, body in texts.items():
            marker, _, suffix = path.stem.rpartition("-")
            cause = causes.get(marker)
            if cause is None or not suffix.isdecimal():
                continue
            try:
                row = json.loads(body)
                records[(cause, int(row["pid"]), int(row["start"]))] = row
            except (ValueError, KeyError, TypeError):
                report("death-record", f"{path.name}: unreadable worker identity")
        if kind in {"worker-killed", "oom"}:
            for down in (p for p in files if re.fullmatch(r"worker-gw[0-9]+-down", p.stem)):
                gateway = down.stem.removesuffix("-down")
                workers = list(down.parent.glob(f"session-*/{gateway}-pid.txt"))
                attributed = False
                for pid_file in workers:
                    try:
                        pid = int(texts[pid_file])
                        birth = int(texts[pid_file.with_name(gateway + "-start.txt")])
                        crash = json.loads(texts[pid_file.with_name(f"worker-killed-{pid}.txt")])
                        attributed |= (crash["pid"], crash["start"]) == (pid, birth)
                    except (KeyError, TypeError, ValueError):
                        continue
                if not attributed:
                    report("death-record", f"{down.name}: no matching xdist worker-crash identity")
        if not any(cause == kind for cause, _, _ in records):
            report("death-record", f"{kind}: no pre-cleanup worker observation")
        for (cause, pid, start), row in records.items():
            node = row.get("node")
            sample_node = row.get("snapshot_node")
            stamp, death = row.get("snapshot_at"), row.get("at")
            age = row.get("age_s")
            if not all(isinstance(value, str) and "::" in value for value in (node, sample_node)):
                report("snapshot-label", f"{cause} pid {pid}: missing active or sampled test identity")
            valid_age = (all(isinstance(t, (int, float)) and math.isfinite(t) for t in (stamp, death, age))
                         and 0 <= death - stamp <= FRESH_S and abs(age - (death - stamp)) < .002)
            if not valid_age:
                report("snapshot-age", f"{cause} pid {pid}: missing or stale sample age")
            captured = [sample for path, body in texts.items()
                        if path.name == f"{pid}.txt" and "snapshots" in path.parts
                        for sample, _ in entries(body) if sample.get("pid") == pid and sample.get("start") == start
                        and sample.get("at") == stamp and sample.get("node") == sample_node]
            if not captured:
                report("snapshot", f"{cause} pid {pid}: no matching retained sample")
        if kind == "cancel":
            for path, body in texts.items():
                if not re.fullmatch(r"(?:cancelled|interrupted)-[0-9]+", path.stem):
                    continue
                try:
                    observed = json.loads(body)
                    if not observed.get("alive_when_observed"):
                        continue
                    seen = observed.get("collect_at", observed["at"])
                    stacks = (frames for ring, text in texts.items() if "snapshots" in ring.parts
                              for sample, frames in entries(text) if sample.get("node") == observed["node"]
                              and sample.get("pid") == observed["pid"] and sample.get("start") == observed["start"]
                              and sample.get("reason") in {"warning", "cancel collection"}
                              and abs(sample["at"] - seen) <= 10)
                    if not any(test_frame(observed["node"], frames) for frames in stacks):
                        report("live-stack", f"{path.name}: live worker lacks its interruption stack")
                except (KeyError, TypeError, ValueError):
                    report("death-record", f"{path.name}: unreadable live-worker observation")
        if kind == "oom":
            counters = list(rows_named(texts, "runner-resources-oom.txt"))
            if not any(isinstance(row.get("oom_kill_before"), int) and isinstance(row.get("oom_kill_after"), int)
                       and row["oom_kill_after"] > row["oom_kill_before"] for row in counters):
                report("oom-event", "no increase in the cgroup's oom_kill counter")
            peaks = list(rows_named(texts, "runner-resources-high-water.txt"))
            if any(row.get("pressure_seen") for row in counters) and not peaks:
                report("pressure", "the observed high-water crossing has no usable pressure record")
            for peak in peaks:
                if not peak.get("top_workers") or not all(
                    any(sample.get("reason") == "memory pressure" and sample.get("pid") == worker["pid"]
                        and sample.get("node") == worker["node"] and test_frame(worker["node"], frames)
                        for path, text in texts.items() if "snapshots" in path.parts
                        for sample, frames in entries(text)) for worker in peak["top_workers"]
                ):
                    report("pressure", "observed high-water crossing has no RSS list or pressure sample")
    if kind == "cancel" and any(path.stem in {"cutoff", "session-deadline"} for path in files):
        report("false-cutoff", "cancel: a local cutoff or session deadline also fired")
    if kind and kind not in {"normal", "cancel", "oom"}:
        names = {path.stem for path in files}
        expected = {"deadline": {"session-deadline"}, "time-limit": {"cutoff"},
                    "hang": {"session-deadline", "cutoff"}}.get(kind, set())
        if expected and not names.intersection(expected):
            report("kind", f"{kind}: missing kind marker")
    running = set()
    current = {}
    births = set()
    for path, text in texts.items():
        ident = re.fullmatch(r"(worker-gw[0-9]+|controller)-pid", path.stem)
        if ident:
            try:
                births.add((int(text), int(texts[path.with_name(ident[1] + "-start.txt")])))
            except (KeyError, ValueError):
                pass
        if path.name.startswith("hang-"):
            match = WATCHDOG_HEADER.match(text)
            if match:
                running.add(match[1])
                ident = re.fullmatch(r"hang-(?:main|gw[0-9]+)-([0-9]+)", path.stem)
                if ident:
                    current[int(ident[1])] = (match[1], float(match[4]))
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
                if PREFIX in text:
                    for sample, frames in entries(text):
                        pid, birth = sample.get("pid"), sample.get("start")
                        watched = current.get(pid)
                        if (not watched or (pid, birth) not in births or sample.get("reason") != "warning"
                                or sample.get("node") != watched[0] or sample.get("test_began") != watched[1]
                                or node not in {watched[0], watched[0].split("[", 1)[0]}):
                            continue
                        if test_frame(watched[0], frames):
                            matched = True
                            break
                    if matched:
                        break
                    continue
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
