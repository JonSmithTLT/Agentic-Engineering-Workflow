"""The `vertical` lane's job summary (``vertical.yml``): how many scenarios measured nothing, first.

A scenario is **not measured** when it ended before its verdict: its ledger says so (``Ledger.ended_by``), or it
wrote no ledger at all (a crash or a timeout before its ``finally``). It counts in no counter and against no
threshold, and the summary's first words give the count, so an always-red check says when it measured nothing (the
designer's addendum 1 to the oracle's hand-off, outcome 9). The scenarios are the test cases of the lane's JUnit
report; the rest of each one's story is its ledger's own summary, which follows. It reports, and gates nothing.

Usage: ``python -m vertical.report <ledgers directory>`` (with ``tests/helpers`` on the path); it reads
``<directory>/junit.xml`` and each ``<directory>/<scenario>/vertical-ledger.json``.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from vertical.ledger import ledger_dir_name

JUNIT = "junit.xml"
LEDGER, SUMMARY = "vertical-ledger.json", "vertical-summary.txt"
MEASURED_PASSED, MEASURED_FAILED, NOT_MEASURED = "passed", "failed", "not measured"


def cases(junit: Path) -> list[tuple[str, bool]] | None:
    """Each test case of the JUnit report: its name, and whether pytest passed it; None when there is no report."""
    if not junit.is_file():
        return None
    out = []
    # The lane's own JUnit report, written by this job's pytest a step earlier: not untrusted input
    for case in ET.parse(junit).getroot().iter("testcase"):  # noqa: S314  (this job's own pytest output)
        failed = any(child.tag in ("failure", "error") for child in case)
        out.append((str(case.get("name")), not failed))
    return out


def rows(directory: Path) -> tuple[list[dict[str, Any]], bool]:
    """Each scenario's outcome, and whether the JUnit report gave the scenarios (else the ledgers found do)."""
    found = cases(directory / JUNIT)
    if found is None:
        found = [(d.name, False) for d in sorted(directory.iterdir()) if (d / LEDGER).is_file()] \
            if directory.is_dir() else []
    out = []
    for name, passed in found:
        path = directory / ledger_dir_name(name) / LEDGER
        ledger = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        if ledger is None:
            outcome, why = NOT_MEASURED, "no ledger (it ended before its verdict: a crash or a timeout)"
        elif not ledger.get("measured", True):
            outcome, why = NOT_MEASURED, str((ledger.get("not_measured") or {}).get("error") or "")
        else:
            outcome, why = (MEASURED_PASSED if passed else MEASURED_FAILED), ""
        containment = ((ledger or {}).get("hard_limits") or {}).get("containment") or {}
        out.append({"scenario": name, "outcome": outcome, "why": why, "lead_label": containment.get("lead"),
                    "platform": (ledger or {}).get("platform")})
    return out, cases(directory / JUNIT) is not None


def report(directory: Path) -> str:
    found, from_junit = rows(directory)
    total = len(found)
    unmeasured = [r for r in found if r["outcome"] == NOT_MEASURED]
    passed = sum(1 for r in found if r["outcome"] == MEASURED_PASSED)
    platform = next((r["platform"] for r in found if r["platform"]), sys.platform)
    head = f"not measured: {len(unmeasured)} of {total}"
    if total and len(unmeasured) == total:
        head += " (nothing was measured)"
    lines = [f"### vertical ({platform}): {head}", "",
             f"measured {total - len(unmeasured)}: {passed} passed their verdict, "
             f"{total - len(unmeasured) - passed} failed it"
             + ("" if from_junit else " (no JUnit report: the scenarios are the ledgers found)"), "",
             "| Scenario | Result | Lead label | Why not measured |", "|---|---|---|---|"]
    lines += [f"| {r['scenario']} | {r['outcome']} | {r['lead_label'] or '-'} | {r['why'][:160] or '-'} |"
              for r in found]
    for r in found:
        summary = directory / ledger_dir_name(r["scenario"]) / SUMMARY
        if summary.is_file():
            lines += ["", "```", summary.read_text(encoding="utf-8").rstrip(), "```"]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    sys.stdout.write(report(Path(argv[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
