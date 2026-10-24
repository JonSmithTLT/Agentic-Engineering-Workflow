"""What a failed harness test leaves behind (register E3: a test that fails and then passes is a defect to find).

A harness test's evidence is its run directories: ``run.json`` (the status and reason), ``supervisor.log`` (a crash's
traceback), ``events.jsonl``, the heartbeat's age and the fake agent's own log and transcript. They live in the test's
``tmp_path``, which CI throws away, and an assertion such as "no transcript step 2" names none of them, so a Windows
failure on 2026-10-09 could not be told apart as a stalled supervisor (``lost``) or a crashed one.

When a test that created a ``HarnessLab`` fails, this module:

- adds an ``aew harness runs`` section to the failure report: every run's recorded and observed status, its reason,
  the heartbeat's age and the tail of each log;
- copies those files, redacted, to ``<lane report directory>/harness-runs/<test>/<run>/`` (or ``--harness-evidence``),
  which CI uploads even when the job fails. Each copy ends in ``.txt``: the assurance tools read every ``*.json``
  under the report directory as a lane report.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

import pytest

from aew.harness import contract as K
from aew.harness import runlog

# The labs created by the test that is running (one process runs one test at a time, xdist included).
LABS: list[Any] = []
TAIL_LINES = 30
LINE_CHARS = 300  # a transcript line holds a whole command's output
MAX_COPY_BYTES = 1 << 20
EVIDENCE = ("run.json", "supervisor.log", "events.jsonl", "heartbeat", "harness/agent.log",
            "harness/transcript.jsonl", "harness/prompt.md")


def addoption(parser: pytest.Parser) -> None:
    parser.getgroup("aew-lanes").addoption(
        "--harness-evidence", dest="aew_harness_evidence", default=None, metavar="DIR",
        help="where a failed harness test's run files are copied (default: the lane report's directory)")


def evidence_dir(config: pytest.Config) -> Path | None:
    explicit = config.getoption("aew_harness_evidence", None)
    if explicit:
        return Path(explicit)
    report = config.getoption("aew_lane_report", None)
    return Path(report).resolve().parent / "harness-runs" if report else None


def register(lab: Any) -> None:
    LABS.append(lab)


def _read(path: Path) -> bytes:
    """A file's bytes, retried briefly: on Windows a read can collide with the supervisor's atomic replace of the
    same file (``runlog._read_text``), and the run is often still live when a test fails."""
    deadline = time.monotonic() + 2
    while True:
        try:
            return path.read_bytes()
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


def _redacted(path: Path) -> str:
    """The whole file, redacted before anything is cut: a cut through a credential leaves a piece the pattern no
    longer matches (#136 review, F1)."""
    return K.redact(_read(path).decode("utf-8", "replace"))


def _tail(path: Path, lines: int = TAIL_LINES) -> str:
    try:
        text = _redacted(path)
    except OSError as exc:
        return f"<unreadable: {type(exc).__name__}>"
    return "\n".join(line if len(line) <= LINE_CHARS else line[:LINE_CHARS] + " …"
                     for line in text.splitlines()[-lines:])


def run_dirs(lab: Any) -> list[Path]:
    runs = runlog.run_dir(lab.aew_root, "x").parent
    return sorted(p for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []


def describe_run(directory: Path) -> str:
    """One run as a failure report shows it: what its record says, what an observer sees, and its logs' tails."""
    record = runlog.read_record(directory) or {}
    observed, _ = runlog.observed_status(directory)
    age = runlog.heartbeat_age(directory)
    lines = [f"run {directory.name}: recorded {record.get('status', '<no run.json>')}, observed {observed}, "
             f"heartbeat {'absent' if age is None else f'{age:.1f}s old'}",
             f"  reason: {record.get('reason')}",
             f"  custody_at {record.get('custody_at')}, started_at {record.get('started_at')}, "
             f"ended_at {record.get('ended_at')}, supervisor_pid {record.get('supervisor_pid')}"]
    for name in ("supervisor.log", "events.jsonl", "harness/agent.log", "harness/transcript.jsonl"):
        path = directory / name
        if path.exists():
            lines.append(f"  --- {name} (last {TAIL_LINES} lines)")
            lines.extend(f"  {line}" for line in _tail(path).splitlines())
    return "\n".join(lines)


def describe(lab: Any) -> str:
    dirs = run_dirs(lab)
    if not dirs:
        return f"{lab.root}: no harness runs"
    return f"{lab.root} at {time.strftime('%H:%M:%S')}:\n" + "\n".join(describe_run(d) for d in dirs)


def _safe(nodeid: str) -> str:
    """A directory name for one test: readable, bounded for Windows paths, and unique (its full id's digest: two ids
    that differ only in punctuation, such as parametrized URLs, never share a directory; #136 review, F2)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nodeid)[-120:] + "-" + hashlib.sha256(nodeid.encode()).hexdigest()[:10]


def copy_evidence(lab: Any, dest: Path) -> tuple[list[Path], list[str]]:
    """Copy each run's evidence files, redacted, as ``<name>.txt`` (never ``*.json``: see the module docstring).
    Returns what was copied and what could not be: one unreadable file never stops the rest (#136 review, F3)."""
    copied, failed = [], []
    for directory in run_dirs(lab):
        for name in EVIDENCE:
            src = directory / name
            if not src.is_file():
                continue
            target = dest / directory.name / (name.replace("/", "__") + ".txt")
            try:
                if name == "heartbeat":
                    text = f"mtime age {runlog.heartbeat_age(directory)}s\n"
                else:  # redacted whole, then the tail kept on a line boundary
                    text = _redacted(src)
                    if len(text) > MAX_COPY_BYTES:  # the tail, from a line boundary when one leaves anything
                        cut = text[-MAX_COPY_BYTES:]
                        _, sep, rest = cut.partition("\n")
                        text = "[… earlier text not copied]\n" + (rest if sep and rest else cut)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="")  # the source's own line ends, untranslated
                copied.append(target)
            except OSError as exc:
                failed.append(f"{directory.name}/{name}: {type(exc).__name__}: {exc}")
    return copied, failed


def report(item: pytest.Item, rep: pytest.TestReport) -> None:
    """Attach the labs' runs to a failed report, and copy their evidence where CI uploads it."""
    if not rep.failed or not LABS:
        return
    sections = []
    for lab in LABS:
        try:
            sections.append(describe(lab))
        except Exception as exc:  # diagnostics never replace the failure they describe
            sections.append(f"{getattr(lab, 'root', '?')}: diagnostics failed: {type(exc).__name__}: {exc}")
    dest = evidence_dir(item.config)
    if dest is not None:
        target = dest / f"{_safe(item.nodeid)}-{rep.when}"
        failed: list[str] = []
        for i, lab in enumerate(LABS):
            try:
                failed += copy_evidence(lab, target / f"lab{i}" if len(LABS) > 1 else target)[1]
            except OSError as exc:  # the lab's run directory itself could not be listed
                failed.append(f"{getattr(lab, 'root', '?')}: {type(exc).__name__}: {exc}")
        sections.append(f"run files copied to {target}" + "".join(f"\n  not copied: {f}" for f in failed))
    rep.sections.append(("aew harness runs", "\n\n".join(sections)))


def forget() -> None:
    LABS.clear()


# ---------------------------------------------------------------------------------------------- the autopsy's writer
#
# The hang-and-flake autopsy (tests/helpers/autopsy.py, the session deadline and its sentinel) writes only through the
# functions below, so there is one evidence path with one set of rules:
#
# - **redaction:** every text is passed through ``K.redact`` whole, before anything is cut;
# - **size:** each file is capped (its tail kept, from a line boundary, with a note), and the whole autopsy too, by a
#   :class:`Budget` its writer shares;
# - **names:** nothing written ends in ``.json``: every file name gets ``.txt`` appended unless it already ends so
#   (``events.jsonl`` becomes ``events.jsonl.txt``). The assurance tools also skip the ``autopsy`` directory itself
#   (``tools/ci``), so a name that slipped this rule would still not be read as a lane report.

AUTOPSY_DIR = "autopsy"  # under the hang directory; tools/ci/check_assurance.py and update_durations.py skip it
AUTOPSY_FILE_CAP = 512 * 1024
AUTOPSY_TOTAL_CAP = 64 * 1024 * 1024
TRUNCATED = "[… earlier text not copied: the autopsy's per-file cap]\n"


class Budget:
    """The bytes an autopsy may still write (shared by every writer of one autopsy directory)."""

    def __init__(self, total: int = AUTOPSY_TOTAL_CAP) -> None:
        self.left = total
        self.refused: list[str] = []

    def take(self, name: str, size: int) -> bool:
        if size > self.left:
            self.refused.append(f"{name}: {size} bytes (the autopsy's total cap left {self.left})")
            return False
        self.left -= size
        return True


def safe_name(name: str) -> str:
    """A file name an assurance tool can never read as a lane report: ``.txt`` appended unless already there."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[-150:] or "_"
    return name if name.endswith(".txt") else name + ".txt"


def safe_dir(name: str) -> str:
    """A directory name for one test or process (as :func:`_safe`: readable, bounded, unique)."""
    return _safe(name)


def capped(text: str, cap: int = AUTOPSY_FILE_CAP) -> str:
    """The tail of ``text`` within ``cap`` characters, cut on a line boundary when that leaves anything."""
    if len(text) <= cap:
        return text
    cut = text[-cap:]
    _, sep, rest = cut.partition("\n")
    return TRUNCATED + (rest if sep and rest else cut)


def write_text(dest_dir: Path, name: str, text: str, *, budget: Budget | None = None, append: bool = False,
               cap: int = AUTOPSY_FILE_CAP) -> Path | None:
    """Write ``text`` redacted, capped and safely named under ``dest_dir``. Returns the path, or None when the
    autopsy's total budget refused it (the refusal is kept in the budget, and reported by its writer)."""
    body = capped(K.redact(text), cap)
    target = dest_dir / safe_name(name)
    if budget is not None and not budget.take(target.name, len(body.encode("utf-8", "replace"))):
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    with target.open("a" if append else "w", encoding="utf-8", errors="replace", newline="") as fh:
        fh.write(body)
    return target


def copy_file(src: Path, dest_dir: Path, name: str | None = None, *, budget: Budget | None = None,
              cap: int = AUTOPSY_FILE_CAP) -> Path | None:
    """Copy one file, redacted whole and then capped, as ``<name>.txt`` (never ``*.json``). Read with the short
    sharing-violation retry of :func:`_read`, since a child may still be writing it."""
    return write_text(dest_dir, name or src.name, _read(src).decode("utf-8", "replace"), budget=budget, cap=cap)


def copy_tree(src: Path, dest: Path, *, budget: Budget | None = None, cap: int = AUTOPSY_FILE_CAP,
              max_files: int = 2000) -> tuple[list[Path], list[str]]:
    """Copy a directory (a test's working directory, a child's diagnostics) file by file through :func:`copy_file`:
    redacted, capped, renamed so nothing ends in ``.json``. Never a move: the original is left to its owner. Returns
    what was copied and what was not (unreadable, over a cap, or past ``max_files``); one failure never stops the
    rest."""
    copied: list[Path] = []
    failed: list[str] = []
    try:
        files = sorted(p for p in src.rglob("*") if p.is_file())
    except OSError as exc:
        return copied, [f"{src}: {type(exc).__name__}: {exc}"]
    for i, path in enumerate(files):
        rel = path.relative_to(src)
        if i >= max_files:
            failed.append(f"{len(files) - max_files} more files not copied (max {max_files})")
            break
        try:
            out = copy_file(path, dest / rel.parent, rel.name, budget=budget, cap=cap)
        except OSError as exc:
            failed.append(f"{rel.as_posix()}: {type(exc).__name__}: {exc}")
            continue
        if out is None:
            failed.append(f"{rel.as_posix()}: refused by the autopsy's total cap")
        else:
            copied.append(out)
    return copied, failed
