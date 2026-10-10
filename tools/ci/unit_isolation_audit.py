#!/usr/bin/env python3
"""The audit cross-check of the ``fast`` tier's static guard (CI plan v7 §7, V3-3): a test-only pytest plugin.

The static guard (``test_nothing_outside_the_unit_lane_reaches_a_unit_module``) is what makes the ``fast`` tier
safe; this audit checks that guard against reality, once, through ``.github/workflows/unit-isolation-audit.yml``. The
audit run collects only the heavy test directories, so no module of the unit directory is ever loaded legitimately:
each of these is a violation, at collection or at runtime, whoever caused it (the record names the importer from the
stack and the running test):

- an ``import`` audit event whose module name is a unit module's basename (the event carries no file name);
- an ``open`` event (``io.open_code`` included) on a ``.py`` or ``.pyc`` path under the unit directory;
- a ``subprocess.Popen`` whose argv or environment names such a path.

The unit directory is passed in (``--unit-isolation-dir``), never named here, so this file is outside the static
guard's allowlist. Each process writes its violations to its own JSON file under ``--unit-isolation-report``; the
workflow's last step (``python tools/ci/unit_isolation_audit.py --check DIR``) fails if any file holds one.

    python -m pytest -p unit_isolation_audit --unit-isolation-dir DIR --unit-isolation-report OUT ...
    python tools/ci/unit_isolation_audit.py --check OUT
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

SCHEMA = "aew/unit-isolation-audit/v1"
_state = threading.local()


class Auditor:
    """Classifies audit events against one unit directory and records the violations."""

    def __init__(self, unit_dir: Path, extra_names: tuple[str, ...] = ()) -> None:
        self.unit_dir = unit_dir.resolve()
        self.prefix = os.path.normcase(str(self.unit_dir)) + os.sep
        self.names = {p.stem for p in self.unit_dir.rglob("*.py")} | set(extra_names)
        self.violations: list[dict[str, Any]] = []

    def _under(self, path: str) -> bool:
        try:
            full = os.path.normcase(os.path.abspath(path))
        except (TypeError, ValueError):
            return False
        return full.startswith(self.prefix)

    def _names_path(self, text: str) -> bool:
        return self._under(text) or os.path.normcase(str(self.unit_dir)) in os.path.normcase(text)

    def classify(self, event: str, args: tuple[Any, ...]) -> str | None:
        """Why this event is a violation, or ``None``."""
        if event == "import" and args and isinstance(args[0], str):
            if args[0].rsplit(".", 1)[-1] in self.names:
                return f"import of {args[0]}"
        elif event == "open" and args:
            path = args[0]
            if isinstance(path, bytes):
                path = os.fsdecode(path)
            if isinstance(path, os.PathLike):
                path = os.fspath(path)
            if isinstance(path, str) and path.endswith((".py", ".pyc")) and self._under(path):
                return f"open of {path}"
        elif event == "subprocess.Popen" and len(args) >= 2:
            argv = args[1] if isinstance(args[1], (list, tuple)) else [args[1]]
            env = args[3] if len(args) >= 4 and isinstance(args[3], dict) else {}
            for value in [*argv, *env.values()]:
                text = os.fsdecode(value) if isinstance(value, (bytes, os.PathLike)) else value
                if isinstance(text, str) and self._names_path(text):
                    return f"subprocess naming {text}"
        return None

    def hook(self, event: str, args: tuple[Any, ...]) -> None:
        if event not in ("import", "open", "subprocess.Popen") or getattr(_state, "busy", False):
            return
        _state.busy = True  # the hook's own work (the stack, the record) raises events too
        try:
            why = self.classify(event, args)
            if why:
                stack = [f"{f.filename}:{f.lineno}" for f in traceback.extract_stack()[:-1]
                         if "importlib" not in f.filename and not f.filename.startswith("<frozen")]
                self.violations.append({"event": event, "why": why, "test": os.environ.get("PYTEST_CURRENT_TEST"),
                                        "importer": stack[-1] if stack else None, "stack": stack[-8:]})
        finally:
            _state.busy = False


_auditor: Auditor | None = None


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("unit-isolation-audit", "the fast tier's audit cross-check (CI plan v7 §7)")
    group.addoption("--unit-isolation-dir", default=None, help="the unit directory no audited test may load")
    group.addoption("--unit-isolation-report", default=None, help="directory for this process's violations (JSON)")


def pytest_configure(config: Any) -> None:
    global _auditor
    unit_dir = config.getoption("--unit-isolation-dir")
    if not unit_dir or _auditor is not None:
        return
    _auditor = Auditor(Path(unit_dir), extra_names=("test_spec_pin",))
    sys.addaudithook(_auditor.hook)  # cannot be removed: this plugin is loaded only in the audit run


def pytest_unconfigure(config: Any) -> None:
    out = config.getoption("--unit-isolation-report")
    if _auditor is None or not out:
        return
    where = Path(out)
    where.mkdir(parents=True, exist_ok=True)
    worker = getattr(config, "workerinput", {}).get("workerid", "main")
    (where / f"audit-{worker}-{os.getpid()}.json").write_text(
        json.dumps({"schema": SCHEMA, "unit_dir": str(_auditor.unit_dir), "violations": _auditor.violations},
                   indent=1) + "\n", encoding="utf-8")


def check(report_dir: Path) -> list[str]:
    """Every recorded violation, as one line each; a missing or empty report directory is a problem too (the audit
    did not run)."""
    files = sorted(report_dir.rglob("audit-*.json")) if report_dir.is_dir() else []
    if not files:
        return [f"no audit reports under {report_dir}: the audit did not run"]
    problems = []
    for f in files:
        for v in json.loads(f.read_text(encoding="utf-8")).get("violations", []):
            problems.append(f"{f.name}: {v['why']} (test {v.get('test') or 'collection'}; from {v.get('importer')})")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "--check":
        print("usage: unit_isolation_audit.py --check REPORT_DIR", file=sys.stderr)
        return 2
    problems = check(Path(args[1]))
    for p in problems:
        print(p)
    print(f"unit isolation audit: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
