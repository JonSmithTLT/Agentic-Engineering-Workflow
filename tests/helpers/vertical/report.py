"""The `vertical` lane's job summary (``vertical.yml``): how many scenarios measured nothing, first.

A scenario is **not measured** when it ended before its verdict: its ledger says so (``Ledger.ended_by``), or it
wrote no ledger at all (a crash or a timeout before its ``finally``), or its ledger cannot be read. It counts in no
counter and against no threshold, and the summary's first line gives the count, so an always-red check says when it
measured nothing (the designer's addendum 1 to the oracle's hand-off, outcome 9). On a platform outside the enforced
gate (Windows, the operator's Q1(e)) that line leads with its unqualified state, the count after it. The scenarios
are the test cases of the lane's JUnit report. Without a readable report the count is unknown, and the line says so
and why. It reports, and gates nothing.

The limits: a worker death under ``--max-worker-restart 0`` ends the session but pytest still writes its report,
which holds only the scenarios that ran; the count is of those, and the ones that never started are absent (only a
run that wrote no readable report reads unknown).
Only the #213 hang diagnosis records ``NOT_A_SCENARIO`` (it writes no ledger by
design); any test that records it is listed apart, with its result, never hidden.

Usage: ``python -m vertical.report <ledgers directory>`` (with ``tests/helpers`` on the path); it reads
``<directory>/junit.xml`` and each ``<directory>/<scenario>/vertical-ledger.json``.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from vertical.ledger import ENFORCED_PLATFORMS, WINDOWS_UNQUALIFIED, ledger_dir_name

JUNIT = "junit.xml"
LEDGER, SUMMARY = "vertical-ledger.json", "vertical-summary.txt"
PASSED, FAILED, NOT_MEASURED = "passed", "failed", "not measured"
UNKNOWN, TEARDOWN = "verdict unknown", "passed, errored in teardown"
# The JUnit property a test of the lane that is not a scenario records (``record_property``). Only the #213 hang
# diagnosis records it: it writes no ledger by design, so it is listed apart and never counted as not measured.
NOT_A_SCENARIO = "vertical_not_a_scenario"


def cases(junit: Path) -> list[tuple[str, str, str | None]] | None:
    """Each test case of the JUnit report: its name, its result (passed, failed, or passed and errored in teardown),
    and why it is not a scenario (None for a scenario). None when there is no readable report."""
    try:
        # The lane's own JUnit report, written by this job's pytest a step earlier: not untrusted input
        root = ET.parse(junit).getroot()  # noqa: S314  (this job's own pytest output)
    except (OSError, ET.ParseError):
        return None
    out = []
    for case in root.iter("testcase"):
        failures = [c for c in case if c.tag in ("failure", "error")]
        teardown = bool(failures) and all(c.tag == "error" and "teardown" in str(c.get("message") or "")
                                          for c in failures)
        result = TEARDOWN if teardown else FAILED if failures else PASSED
        apart = next((p.get("value") for p in case.iter("property") if p.get("name") == NOT_A_SCENARIO), None)
        out.append((str(case.get("name")), result, apart))
    return out


def _ledger(path: Path) -> tuple[dict[str, Any] | None, bool]:
    """The ledger at ``path`` (None when absent), and whether it was there but unreadable."""
    if not path.is_file():
        return None, False
    try:
        return json.loads(path.read_text(encoding="utf-8")), False
    except (OSError, ValueError):
        return None, True


def cell(text: str, limit: int = 160) -> str:
    """One table cell: whitespace collapsed and ``|`` escaped, then bounded."""
    return " ".join(text.split()).replace("|", "\\|")[:limit]


def rows(directory: Path) -> tuple[list[dict[str, Any]], bool, list[str]]:
    """Each scenario's outcome, whether a readable JUnit report gave the scenarios (else the ledgers found are
    listed), and the test cases that are not scenarios, each with its result."""
    every = cases(directory / JUNIT)
    from_junit = every is not None
    if every is None:
        every = [(d.name, UNKNOWN, None) for d in sorted(directory.iterdir()) if (d / LEDGER).is_file()] \
            if directory.is_dir() else []
    apart = [f"{name} ({result}; {why})" for name, result, why in every if why]
    out = []
    for name, result, why in every:
        if why:
            continue
        ledger, unreadable = _ledger(directory / ledger_dir_name(name) / LEDGER)
        if unreadable:
            outcome, reason = NOT_MEASURED, "unreadable ledger"
        elif ledger is None:
            outcome, reason = NOT_MEASURED, "no ledger (it ended before its verdict: a crash or a timeout)"
        elif not ledger.get("measured", True):
            outcome, reason = NOT_MEASURED, str((ledger.get("not_measured") or {}).get("error") or "")
        else:
            outcome, reason = result, ""
        containment = ((ledger or {}).get("hard_limits") or {}).get("containment") or {}
        out.append({"scenario": name, "outcome": outcome, "why": reason, "lead_label": containment.get("lead"),
                    "platform": (ledger or {}).get("platform")})
    return out, from_junit, apart


def report(directory: Path) -> str:
    found, from_junit, apart = rows(directory)
    total = len(found)
    unmeasured = sum(1 for r in found if r["outcome"] == NOT_MEASURED)
    platform = next((r["platform"] for r in found if r["platform"]), "win32" if sys.platform == "win32" else "linux")
    if from_junit:
        head = f"not measured: {unmeasured} of {total}" + (" (nothing was measured)" if unmeasured == total else "")
    else:
        head = (f"not measured: unknown (pytest wrote no readable JUnit report: the run ended before its summary); "
                f"{total} ledgers found, {unmeasured} of them not measured")
    state = "" if platform in ENFORCED_PLATFORMS else f"{WINDOWS_UNQUALIFIED}. "  # Q1(e): it leads, on Windows
    counted = {o: sum(1 for r in found if r["outcome"] == o) for o in (PASSED, FAILED, TEARDOWN, UNKNOWN)}
    lines = [f"### {state}vertical ({platform}): {head}", "",
             f"measured {total - unmeasured}: " + ", ".join(f"{n} {o}" for o, n in counted.items() if n), "",
             *([f"not scenarios (no ledger by design): {'; '.join(apart)}", ""] if apart else []),
             "| Scenario | Result | Lead label | Why not measured |", "|---|---|---|---|"]
    lines += [f"| {cell(r['scenario'])} | {r['outcome']} | {r['lead_label'] or '-'} | {cell(r['why']) or '-'} |"
              for r in found]
    for r in found:
        summary = directory / ledger_dir_name(r["scenario"]) / SUMMARY
        if summary.is_file():
            lines += ["", "```", summary.read_text(encoding="utf-8", errors="replace").rstrip(), "```"]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    sys.stdout.write(report(Path(argv[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
