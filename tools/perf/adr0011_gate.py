"""ADR-0011's completion criteria, judged from ``control_plane.py sweep`` results (implementation plan §7.2).

Usage::

    python tools/perf/adr0011_gate.py FLAT.json [--hierarchy HIERARCHY.json] [--ab AB.json]

FLAT.json is a sweep with the points 20:250, 20:3000 and the active series at 250 completed (20, 200, 500 and 1,000
open); HIERARCHY.json a ``sweep --hierarchy`` with 250 and 3,000 completed. Prints one Markdown table of verdicts and
exits 1 if any criterion fails. A1 is reported, not judged: the ADR asks for the slope and any knee.

AB.json is ``control_plane.py ab`` at 20:250 and 20:3000: both points measured in turns, so a change in the machine's
speed reaches both alike. When given, it judges the flat series' H2, and the sweep's own H2 rows are reported only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

H1_GROWTH, H1_SHARE, H2_DELTA_S, H3_S, HEARTBEAT_S = 1.25, 0.20, 0.25, 0.25, 2.5
READS = {"lead show", "status", "work tree", "gate show", "context pack", "harness status"}
WRITES = {"checkpoint (commit path)", "dispatch (work dispatch)", "review ingest"}
BOUNDS = {**{op: 2.0 for op in READS}, **{op: 4.0 for op in WRITES}, "resume": 8.0}


def point(results: list[dict[str, Any]], open_: int, completed: int) -> dict[str, Any]:
    for r in results:
        if r["point"] == {"open": open_, "completed": completed}:
            return r
    raise SystemExit(f"no sweep point {open_} open, {completed} completed")


def ops(r: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {o["op"]: o for o in r["ops"] if not o["op"].startswith("CLI floor")}


def history_series(results: list[dict[str, Any]], open_: int, label: str,
                   paired: dict[str, Any] | None = None) -> list[tuple[str, str, bool | None]]:
    small, large = point(results, open_, 250), point(results, open_, 3000)
    out: list[tuple[str, str, bool | None]] = []
    growth = large["footprint"]["control_bytes"] / small["footprint"]["control_bytes"]
    out.append((f"H1 {label}: hot state at 3,000 / at 250 completed", f"{growth:.3f}x (<= {H1_GROWTH}x)",
                growth <= H1_GROWTH))
    share = large["footprint"]["history_bytes"]["total"] / large["footprint"]["control_bytes"]
    out.append((f"H1 {label}: history share of hot state at 3,000", f"{share:.1%} (<= {H1_SHARE:.0%})",
                share <= H1_SHARE))
    a, b = ops(small), ops(large)
    for op in a:
        delta = b[op]["wall_s"] - a[op]["wall_s"]
        out.append((f"H2 {label}: `{op}`, 3,000 minus 250", f"{delta:+.3f} s (<= +{H2_DELTA_S} s)",
                    None if paired else delta <= H2_DELTA_S))
    if paired:
        assert paired["points"] == [{"open": open_, "completed": 250}, {"open": open_, "completed": 3000}], paired
        for op, v in paired["ops"].items():
            if op.startswith("CLI floor"):
                continue
            delta = v["paired_delta_s"][0]
            out.append((f"H2 {label}, paired ({paired['rounds']} rounds): `{op}`, 3,000 minus 250",
                        f"{delta:+.3f} s (<= +{H2_DELTA_S} s)", delta <= H2_DELTA_S))
    for op, bound in BOUNDS.items():
        if op in b:
            out.append((f"Bound {label}: `{op}` at 3,000", f"{b[op]['wall_s']:.2f} s (<= {bound} s)",
                        b[op]["wall_s"] <= bound))
    reparse = large["micro"]["control_reparse_s"]
    out.append((f"H3 {label}: re-parse of a changed hot state at 3,000", f"{reparse * 1000:.1f} ms (<= {H3_S} s)",
                reparse <= H3_S))
    out.append((f"Heartbeat bound {label}", f"{reparse * 1000:.1f} ms (<= {HEARTBEAT_S} s)", reparse <= HEARTBEAT_S))
    same = {k: v for k, v in a["resume"]["counts"].items() if k != "parse_bytes"} == \
        {k: v for k, v in b["resume"]["counts"].items() if k != "parse_bytes"}
    out.append((f"H4 {label}: `resume` does the same reads and scans at 250 and 3,000",
                "identical counters" if same else f"{a['resume']['counts']} vs {b['resume']['counts']}", same))
    return out


def active_series(results: list[dict[str, Any]]) -> list[tuple[str, str, None]]:
    lo, hi = point(results, 20, 250), point(results, 1000, 250)
    units = hi["point"]["open"] - lo["point"]["open"]
    out: list[tuple[str, str, None]] = [(
        "A1: hot bytes per open unit, 20 to 1,000 open",
        f"{(hi['footprint']['control_bytes'] - lo['footprint']['control_bytes']) / units / 1000:.2f} KB "
        "(M3 baseline 0.9-1.3 KB)", None)]
    a, b = ops(lo), ops(hi)
    for op in a:
        ms = (b[op]["wall_s"] - a[op]["wall_s"]) / units * 1000
        out.append((f"A1: `{op}` per open unit", f"{ms:.2f} ms (M3 baseline 0-2 ms)", None))
    knees = []
    for o in (20, 200, 500, 1000):
        r = point(results, o, 250)
        knees.append(f"{o}: {ops(r)['resume']['wall_s']:.2f} s")
    out.append(("A1: `resume` along the series (look for a knee)", ", ".join(knees), None))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("flat", type=Path)
    ap.add_argument("--hierarchy", type=Path)
    ap.add_argument("--ab", type=Path, help="control_plane.py ab at 20:250,20:3000: judges the flat series' H2")
    args = ap.parse_args()
    flat = json.loads(args.flat.read_text(encoding="utf-8"))
    paired = json.loads(args.ab.read_text(encoding="utf-8")) if args.ab else None
    rows: list[tuple[str, str, bool | None]] = [*history_series(flat, 20, "flat", paired), *active_series(flat)]
    if args.hierarchy:
        rows += history_series(json.loads(args.hierarchy.read_text(encoding="utf-8")), 5, "hierarchy")
    print("| Criterion | Measured | Verdict |\n|---|---|---|")
    for name, measured, ok in rows:
        print(f"| {name} | {measured} | {'report' if ok is None else 'pass' if ok else '**FAIL**'} |")
    return 0 if all(ok is not False for _, _, ok in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
