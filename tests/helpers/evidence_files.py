"""Evidence file families and their states. JSON and autopsy families share owners."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileFamily:
    pattern: str
    writer: str | None
    scanned: bool = False
    priority: bool | Callable[[Path], bool] = False
    stack: bool = False


def autopsy_priority(path: Path) -> bool:
    return any(p.startswith("session-") for p in path.parts) or path.name.startswith(("reason", "stacks"))


# Ordered like the writers: a watchdog or running name keeps its owner even in a nested session.
FAMILIES = (
    FileFamily("inventory.txt", "publisher"),
    FileFamily("inventory-part-*.txt", "publisher", scanned=True, priority=True),
    FileFamily("job-label-sha256.txt", "evidence_inputs"),
    FileFamily("hang-*.txt", "watchdog", scanned=True, priority=True),
    FileFamily("running-*.txt", "watchdog"),
    FileFamily("running-*.tmp", "watchdog"),
    FileFamily("collection-incomplete.txt", "evidence_inputs"),
    FileFamily("tools-unavailable.txt", "evidence_inputs"),
    FileFamily("autopsy/**", "autopsy/session_deadline/harness_diagnostics/flight_recorder",
               scanned=True, priority=autopsy_priority),
    FileFamily("harness-runs/**", "harness_diagnostics", scanned=True),
    FileFamily("snapshots/*.txt", "lane_step", scanned=True, priority=True),
    FileFamily("failures/*.txt", "lanes", scanned=True, priority=True),
    FileFamily("runner-resources-*.txt", "lane_step", scanned=True, priority=True),
    FileFamily("*vertical*.json", "vertical"),
    FileFamily("vertical-series.jsonl", "vertical"),
    FileFamily("*.json", "lanes"),
    FileFamily("junit.xml", "pytest", scanned=True),
    FileFamily("vertical-summary.txt", "vertical", scanned=True),
    FileFamily("dispatch.txt", "flake-dispatch", scanned=True),
    # Shape-only selectors preserve priority staging even for an unknown writer; full publication checks ownership.
    FileFamily("hang-*", None, priority=True, stack=True),
    FileFamily("stacks.*", None, priority=True, stack=True),
    FileFamily("*-stacks*", None, priority=True, stack=True),
    FileFamily("snapshots/**", None, scanned=True, priority=True, stack=True),
    FileFamily("runner-resources-*", None, priority=True),
)
WATCHDOG_PREFIX = "aew hang watchdog: "
ARMED_NOTE = "a dump below records a fire"
WATCHDOG_HEADER = re.compile(
    rf"{WATCHDOG_PREFIX}(.+) started ([^;]+); limit ([0-9.]+)s; {ARMED_NOTE}; monotonic ([0-9.]+)")
FRAME = re.compile(
    r'(?m)^\s*(?:File "(?P<file>[^"\n]+)", line \d+,? in (?P<function>[\w.<>]+)'
    r'|(?P<spy_function>[\w.<>]+) \((?P<spy_file>[^\n]+\.py):\d+\))')


FRESH_S = 60
PREFIX = "worker snapshot "
WARNING = "warning"
CANCEL_COLLECTION = "cancel collection"
# The sample reasons taken at an interruption: the Linux supervisor's pre-signal warning and the cancellation
# collection (lane_step --collect). Both retry inside one shared budget, and their stacks answer evidence_problems'
# live-stack check (register E3).
INTERRUPTION_REASONS = frozenset({WARNING, CANCEL_COLLECTION})
# worker_evidence.Monitor records the lane's periodic sampling policy here; the cancellation collection and the
# evidence check read it back through policy_samples (register E3).
SAMPLING_POLICY = "runner-resources-sampling.txt"
# Cancellation-collection outcomes for a worker with no sample in the owned tree. Only NOT_SAMPLED, in a lane whose
# periodic sampling is off (AEW_WORKER_SNAPSHOTS=0), owes no stack, and only while no sampling attach of it failed: in a
# lane that samples, a worker with no sample is a sampling gap and still owes its stack (register E3; review of #561,
# M1). Hosted CI samples every worker, a serial lane's controller included (operator, 2026-11-25).
NOT_SAMPLED = "not sampled in the owned tree"
SAMPLING_GAP = "never sampled although its lane's policy samples it"
# The Linux pre-signal warning's outcome for a worker outside the supervisor's tree. The warning's outcomes only say why
# a stack is missing; none of them excuses one (register E3).
OUTSIDE_TREE = "outside the supervisor's owned tree"
# The pytest phases outside a test's call, where a live worker has no test-function frame to give. evidence_problems
# accepts only these, and only when the retained frames themselves classify so (register E3).
OUTSIDE_CALL = ("setup", "teardown", "between tests")
# lane_step writes this only when it stops a lane for the Windows host's resources; the evidence check names that
# death by it (register E3).
HOST_STOP_FILE = "runner-resources-host-high-water.txt"
# The lifecycle receipt of a process that runs tests (session_deadline.PhaseReceipt): its phases, in order. An xdist
# worker keeps one, and so does a serial session's controller, which runs its tests itself; an xdist controller runs
# none and keeps none. The process runs no test before it records the last phase, which it writes on entering its
# first test's protocol.
WORKER_PHASES = ("collecting", "collection-ended", "execution-started")
BEFORE_EXECUTION = WORKER_PHASES[:-1]
# The name a serial session's controller is registered and listed under (`controller-pid`, `controller-start`), where
# an xdist worker's is `worker-gwN`.
CONTROLLER = "controller"
# A lane cancelled while its sessions were still starting has no test running and no worker in a test, so it has no
# worker observation or running name to give. worker_evidence.before_tests records that, from positive observations
# only, and evidence_problems accepts it as the cancellation's complete death evidence once the bundle bears it out
# (register E3: cancelled CI runs 45590135545, 45591135734, 45571060413 and 45570390239).
BEFORE_TESTS = "runner-resources-before-tests.txt"
BEFORE_TESTS_OUTCOME = "cancelled before any test started"
# The lane report's schema (lanes.py writes it) and the xdist controller's roster marker (session_deadline writes it),
# owned here so that the evidence check, which runs without pytest, reads them from their one definition.
LANE_REPORT_SCHEMA = "aew/lane-report/v1"
WORKER_COUNT = "worker-count"


def lifecycle_receipt(worker: str, pid: object, start: object) -> str:
    """The file name of the lifecycle receipt that the registered process ``worker`` (`worker-gwN`, or CONTROLLER for
    a serial session's controller) keeps in its session's directory, by its pid and start."""
    return f"{CONTROLLER if worker == CONTROLLER else 'worker'}-{pid}-{start}-lifecycle.txt"


def receipt_phases(text: str) -> list[str] | None:
    """The phases a lifecycle receipt records, in order, or None when it records none or is not a prefix of
    WORKER_PHASES."""
    try:
        phases = [line.split()[1] for line in text.splitlines()]
    except IndexError:
        return None
    return phases if phases and tuple(phases) == WORKER_PHASES[:len(phases)] else None


def report_shows_no_test(report: dict) -> bool:
    """Whether a lane report shows that no test ran: it is complete, and its only results are collection errors, which
    pytest reports before any test. Its ``collected`` list proves nothing: under xdist the controller fills it only
    as each worker goes down (review of #579, m4)."""
    results = report.get("results")
    return report.get("complete") is True and isinstance(results, dict) and all(
        isinstance(result, dict) and result.get("failures") and all(
            isinstance(failure, dict) and failure.get("phase") == "collect" for failure in result["failures"])
        for result in results.values())


def finished_without_tests(files: dict[str, str], reports: list[dict]) -> str | None:
    """Why a finished session's own files fall short of showing that it began no test, or None when they show it.

    An interrupt during start-up lets pytest end gracefully: the session writes ``session-finished`` and a complete
    lane report with no results (review of #579, M1). Every registered worker (``worker-gwN-pid`` and ``-start``) must
    have its lifecycle receipt, never past collection, and every lane report must be complete with no test's result.
    A serial session's controller keeps a receipt only once its collection begins, so it owes none, but one it kept
    must stop before its first test too.
    ``files`` maps the
    session directory's file names to their text."""
    for name in sorted(files):
        if re.fullmatch(rf"{CONTROLLER}-[0-9]+-[0-9]+-lifecycle\.txt", name):
            phases = receipt_phases(files[name])
            if phases is None or WORKER_PHASES[-1] in phases:
                return "its controller's lifecycle receipt does not stop before its first test"
        if not re.fullmatch(r"worker-gw[0-9]+-pid\.txt", name):
            continue
        worker = name.removesuffix("-pid.txt")
        try:
            receipt = lifecycle_receipt(worker, int(files[name]), int(files[worker + '-start.txt']))
        except (KeyError, ValueError):
            return f"{worker} has no recorded identity"
        phases = receipt_phases(files.get(receipt, ""))
        if phases is None or WORKER_PHASES[-1] in phases:
            return f"{worker} has no lifecycle receipt that stops before its first test"
    if not reports:
        return "no lane report shows what ran"
    if not all(report_shows_no_test(report) for report in reports):
        return "its lane report does not show that no test ran"
    return None


STUCK_MARKER = "stuck-after-finish.txt"  # session_deadline's STUCK marker, as written (its test pins the two)


def test_frame(node: str, frames: str) -> bool:
    source, _, test = node.partition("::")
    function = test.split("[", 1)[0].split("::")[-1]
    for frame in FRAME.finditer(frames):
        file = frame.group("file") or frame.group("spy_file")
        called = frame.group("function") or frame.group("spy_function")
        if ("/" + file.replace("\\", "/")).endswith("/" + source.replace("\\", "/")) and called == function:
            return True
    return False


def pytest_phase(frames: str) -> str:
    """Where a dump without its test-function frame stands in pytest's test protocol: one of OUTSIDE_CALL, ``call``
    (inside pytest_runtest_call, so the test's frame is missing), or ``indeterminate``. Between tests needs the run
    loop's own frame, so a dump that lost the main thread never reads as outside a call."""
    called = {(match.group("function") or match.group("spy_function")).rsplit(".", 1)[-1]
              for match in FRAME.finditer(frames)}
    if "pytest_runtest_call" in called:
        return "call"
    if "runtestprotocol" not in called:
        return "between tests" if "pytest_runtestloop" in called else "indeterminate"
    if "pytest_runtest_teardown" in called:
        return "teardown"
    if "pytest_runtest_setup" in called:
        return "setup"
    return "indeterminate"


def policy_samples(policy: dict) -> bool:
    """Whether the lane's periodic sampling policy samples its workers. An unknown or unreadable policy counts as
    sampling, so it never excuses a missing stack."""
    return policy.get("periodic") is not False


def sampling_failures(pid: int, start: int) -> str:
    """The snapshots file keeping the first failed periodic or pressure attach of one worker identity."""
    return f"{pid}-{start}-sampling-failures.txt"


def cancel_outcome(pid: int, start: int) -> str:
    """The snapshots file naming why the cancellation collection kept no test stack for one worker identity."""
    return f"{pid}-{start}-cancel-outcome.txt"


def warning_outcome(pid: int, start: int) -> str:
    """The snapshots file naming why the Linux pre-signal warning kept no test stack for one worker identity."""
    return f"{pid}-{start}-warning-outcome.txt"


def entries(text: str):
    """Only complete, labelled samples. Each frame block ends at the next header."""
    for block in re.split(r"(?m)^" + re.escape(PREFIX), text)[1:]:
        header, _, frames = block.partition("\n")
        try:
            row = json.loads(header)
            if isinstance(row, dict) and FRAME.search(frames):
                yield row, frames
        except ValueError:
            continue


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def open_observation(path: Path):
    """Read an in-flight file without preventing its owner from removing or renaming it."""
    if os.name != "nt":
        return path.open(encoding="utf-8", errors="replace")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    generic_read, open_existing = 0x80000000, 3
    share_read_write_delete = 1 | 2 | 4
    handle = create(str(path), generic_read, share_read_write_delete, None, open_existing, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except OSError:
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise
    return os.fdopen(fd, encoding="utf-8", errors="replace")


def families(path: Path):
    for family in FAMILIES:
        if family.pattern == "failures/*.txt" and not failure_overflow(path):
            continue
        nested = family.pattern.endswith("/**")
        if (family.pattern[:-3] in path.parts[:-1] if nested else path.match(family.pattern)):
            yield family


def owner(path: Path) -> str | None:
    return next((family.writer for family in families(path) if family.writer), None)


def publishable(path: Path) -> bool:
    # Recursive directories accept text diagnostics only. The specific XML family is scanned as well.
    return report_json(path) or any(family.scanned and (not family.pattern.endswith("/**") or path.suffix == ".txt")
               for family in families(path))


def report_json(path: Path) -> bool:
    # Existing root report/discovery JSON and the dispatch lane's explicitly named child reports.
    return path.suffix == ".json" and (len(path.parts) == 1 or (len(path.parts) == 2 and path.name == "report.json"
                                      and re.fullmatch(r"plants|shard|isolated-[0-9]+", path.parts[0]) is not None))


def stuck_marker(path: Path) -> bool:
    """A session's ``stuck-after-finish`` marker (``session_deadline.STUCK``): the one autopsy file the reports-only
    bundle carries, so the assurance jobs, which download only reports, can name a session the sentinel ended after it
    finished (register E3)."""
    return (len(path.parts) == 3 and path.parts[0] == "autopsy" and path.parts[1].startswith("session-")
            and path.name == STUCK_MARKER)


def failure_or_death(path: Path) -> bool:
    return (report_json(path) or failure_overflow(path) or priority(path)
            or ("autopsy" in path.parts and path.name.startswith("failure")))


def failure_overflow(path: Path) -> bool:
    return (path.parent.name == "failures" and report_json(path.parent.parent / "report.json")
            and re.fullmatch(r"[0-9a-f]{64}\.txt", path.name) is not None)


def stack_file(path: Path) -> bool:
    return any(family.stack for family in families(path))


def priority(path: Path) -> bool:
    return any(family.priority(path) if callable(family.priority) else family.priority for family in families(path))


def state(path: Path, data: bytes) -> str:
    if not data:
        return "empty"
    text = data.decode("utf-8", errors="replace")
    if path.name.startswith("hang-") or "-stacks" in path.name:
        first, _, body = text.partition("\n")
        if first.startswith("armed ") or (first.startswith("aew hang watchdog:") and " started " in first):
            return "finding" if body.strip() else "armed-placeholder"
        return "finding" if FRAME.search(text) or "Timeout (" in text else "armed-placeholder"
    return "finding"


def stacks_ablated() -> bool:
    return bool(os.environ.get("AEW_EVIDENCE_PLANT")) and os.environ.get("AEW_EVIDENCE_ABLATE") == "stacks"
