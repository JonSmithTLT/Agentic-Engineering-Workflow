"""Check the states and stacks in published lane evidence."""

from __future__ import annotations

import contextlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "helpers"))
from bounds import CHEAP_FILE  # noqa: E402
from evidence_files import (  # noqa: E402
    BEFORE_EXECUTION,
    BEFORE_TESTS,
    BEFORE_TESTS_OUTCOME,
    CANCEL_COLLECTION,
    FRAME,
    FRESH_S,
    INTERRUPTION_REASONS,
    LANE_REPORT_SCHEMA,
    NOT_SAMPLED,
    OUTSIDE_CALL,
    PREFIX,
    SAMPLING_POLICY,
    WARNING,
    WATCHDOG_HEADER,
    WORKER_PHASES,
    cancel_outcome,
    entries,
    failure_overflow,
    finished_without_tests,
    owner,
    policy_samples,
    priority,
    publishable,
    pytest_phase,
    receipt_phases,
    report_json,
    report_shows_no_test,
    sampling_failures,
    stack_file,
    state,
    test_frame,
)


def outside_call(texts: dict, observed: dict, stacks: list, *, sampled: bool) -> bool:
    """A live worker owes no interruption stack only by a typed cancellation outcome the bundle bears out (register
    E3), and only for the observation that outcome belongs to: a worker in a lane whose sampling is off, with no
    retained sample of its identity and no failed sampling attach of it, or one in setup, teardown or between tests by
    the frames its cancellation collection retained. A worker inside its test's call always owes one."""
    pid, start = observed["pid"], observed["start"]
    policies = list(rows_named(texts, SAMPLING_POLICY))
    failed = any(path.name == sampling_failures(pid, start) for path in texts)
    for row in rows_named(texts, cancel_outcome(pid, start)):
        if ((row.get("pid"), row.get("start"), row.get("node")) != (pid, start, observed["node"])
                or observed.get("collect_at") is None or row.get("collect_at") != observed["collect_at"]):
            continue
        if (row.get("outcome") == NOT_SAMPLED and not sampled and not failed and policies
                and not any(policy_samples(policy) for policy in policies)):
            return True
        if row.get("outcome") in OUTSIDE_CALL and any(
                reason == CANCEL_COLLECTION and pytest_phase(frames) == row["outcome"] for reason, frames in stacks):
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


def before_tests_problems(texts: dict, running: set) -> list[str]:
    """Where the bundle contradicts or lacks its record that the lane was cancelled before any test started (register
    E3). The record stands in for a worker observation and a running name only when every copy agrees, every session
    is listed, every registered worker is listed by identity with its lifecycle receipt, which reached the recorded
    phase and never execution, a finished session's own files show that it began no test, and no autopsy of a test,
    watchdog header, interruption record, test result or running name shows a test begun (review of #579, M1 and m1)."""
    problems = []
    copies = {json.dumps(row, sort_keys=True) for row in rows_named(texts, BEFORE_TESTS)}
    record = json.loads(copies.pop()) if len(copies) == 1 else {}
    sessions = record.get("sessions")
    if record.get("outcome") != BEFORE_TESTS_OUTCOME or not isinstance(sessions, list) or not all(
            isinstance(row, dict) and isinstance(row.get("workers"), list) for row in sessions):
        return ["no single readable before-tests observation"]
    listed = {}
    for row in sessions:
        for worker in row["workers"]:
            if not isinstance(worker, dict) or worker.get("phase") not in BEFORE_EXECUTION:
                problems.append(f"{row.get('session')}: a worker not recorded before its first test")
            else:
                listed[(PurePosixPath(str(row.get("session"))).name, worker.get("worker"))] = worker
    names = {PurePosixPath(str(row.get("session"))).name for row in sessions}
    reports = []
    files = defaultdict(dict)  # each published session's files, by name, across the bundle's copies
    for path, text in texts.items():
        if path.suffix == ".json":
            with contextlib.suppress(ValueError):
                doc = json.loads(text)
                if isinstance(doc, dict) and doc.get("schema") == LANE_REPORT_SCHEMA:
                    reports.append(doc)
                    # A collection error is reported before any test; any other result is a test that ran.
                    if not report_shows_no_test({**doc, "complete": True, "collected": None}):
                        problems.append(f"{path.name}: the lane report has a test's result")
            continue
        if "autopsy" in path.parts[:-1]:
            under = path.parts[len(path.parts) - 1 - path.parts[::-1].index("autopsy") + 1]
            if not under.startswith("session-"):
                problems.append(f"autopsy/{under}: a test's autopsy")
            elif path.parent.name == under:
                files[under][path.name] = text
            continue
        if path.name.startswith("hang-") and WATCHDOG_HEADER.match(text):
            problems.append(f"{path.name}: a test was in flight")
        elif re.fullmatch(r"(?:interrupted|cancelled)-[0-9]+", path.stem):
            problems.append(f"{path.name}: a worker was observed in a test")
    for session, published in sorted(files.items()):
        if session not in names:
            problems.append(f"{session}: a session the observation does not list")
            continue
        if "session-finished.txt" in published and (why := finished_without_tests(published, reports)):
            problems.append(f"{session}: the session had finished, and {why}")
        for name, text in sorted(published.items()):
            if re.fullmatch(r"(?:interrupted|cancelled)-[0-9]+\.txt", name):
                problems.append(f"{session}/{name}: a worker was observed in a test")
            elif ident := re.fullmatch(r"(worker-gw[0-9]+)-pid\.txt", name):
                worker = listed.get((session, ident[1]), {})
                start = published.get(f"{ident[1]}-start.txt", "")
                if (not text.strip().isdecimal() or not start.strip().isdecimal()
                        or (worker.get("pid"), worker.get("start")) != (int(text), int(start))):
                    problems.append(f"{session}: {ident[1]} is not recorded, by pid and start, before its first test")
            elif name.endswith("-lifecycle.txt") and WORKER_PHASES[-1] in text.split():
                problems.append(f"{session}/{name}: a worker had started its tests")
    for (session, name), worker in sorted(listed.items()):
        phases = receipt_phases(files.get(session, {}).get(f"worker-{worker.get('pid')}-{worker.get('start')}"
                                                           f"-lifecycle.txt", ""))
        # The receipt must have reached the recorded phase: a worker can go on collecting after the observation until
        # the lane is ended, so a later phase short of execution still bears it out.
        if phases is None or worker["phase"] not in phases or WORKER_PHASES[-1] in phases:
            problems.append(f"{session}: {name} has no lifecycle receipt bearing out its recorded phase")
    if running:
        problems.append("a running test name was published")
    return problems


ELISION = re.compile(r"Use -v+ to (?:get more diff|show)|Omitting \d+ identical items|Skipping \d+ identical leading")
FAILURE_PHASES = ("collect", "setup", "call", "teardown")


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
            # xdist's controller emits a synthetic TestReport with when="???" for a crashed worker.
            worker_crash = phase == "???" and re.fullmatch(r"worker 'gw[0-9]+' crashed while running "
                                                          + re.escape(repr(node)), crash)
            if phase not in FAILURE_PHASES and not worker_crash:
                defect("failure-report", f"{detail}: missing or unrecognized failure phase")
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


def evidence_problems(root: Path, *, kind: str | None = None, require_stacks: bool = False,
                      cancel_reason: dict | None = None) -> list[str]:
    """Check published states and warning-death stacks, also used by the hosted proof."""
    defects = []

    def report(rule: str, detail: str) -> None:
        defects.append(f"evidence defect: [{rule}] {detail}")

    files = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    texts = {path: data.decode("utf-8", errors="replace") for path, data in files.items()}
    if kind in {"cancel", "cancel-after-tests", "cancel-before-tests"}:
        from cancel_evidence import REASON_FILE, valid

        if not valid(cancel_reason):
            report("cancel-reason", "no verified cancellation reason and replacement or manual/API observation")
        for early in rows_named(texts, REASON_FILE):
            if valid(early) and valid(cancel_reason) and any(
                    early.get(k) != cancel_reason.get(k) for k in ("kind", "run", "head_sha", "event", "message")):
                report("cancel-reason", "collected cancellation reason conflicts with the completed-run observation")
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
                    if isinstance(doc, dict) and doc.get("schema") == LANE_REPORT_SCHEMA:
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
                    samples = [(sample, frames) for ring, text in texts.items() if "snapshots" in ring.parts
                               for sample, frames in entries(text)
                               if sample.get("pid") == observed["pid"] and sample.get("start") == observed["start"]]
                    stacks = [(sample["reason"], frames) for sample, frames in samples
                              if sample.get("node") == observed["node"]
                              and sample.get("reason") in INTERRUPTION_REASONS and abs(sample["at"] - seen) <= 10]
                    if (not any(test_frame(observed["node"], frames) for _, frames in stacks)
                            and not outside_call(texts, observed, stacks, sampled=bool(samples))):
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
    if kind in {"cancel", "cancel-before-tests"} and any(path.stem in {"cutoff", "session-deadline"}
                                                          for path in files):
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
    if kind == "cancel-before-tests":
        # It stands in for the cancellation's worker observation and running name only as the bundle bears it out.
        for problem in before_tests_problems(texts, running):
            report("before-tests", problem)
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
                        if (not watched or (pid, birth) not in births or sample.get("reason") != WARNING
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
