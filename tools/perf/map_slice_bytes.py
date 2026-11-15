#!/usr/bin/env python3
"""The map slice's size at its bounds: a measurement, run by hand (register E184; ``aew.maps.slices`` SLICE_MAX_BYTES).

    python tools/perf/map_slice_bytes.py [--names 8,30,60,120]

For each directory-name length it builds an in-memory repository that fills the slice's row and hint bounds (ROWS
directories and HINTS vendored ones, each name that many characters long), generates its structural map, and prints
the slice body's UTF-8 bytes with a CURRENT freshness line and with a STALE one naming metadata paths, and whether
the byte bound cut anything. It reads no repository and writes nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "helpers"))

from map_trees import tree_of  # noqa: E402  (a test helper: an in-memory TrackedTree)

from aew.maps import rules, slices, structural  # noqa: E402
from aew.maps.canonical import seal  # noqa: E402

CURRENT = {"status": "CURRENT", "reasons": [], "reason": None, "against_commit": "b" * 40}
STALE = {"status": "STALE", "reasons": ["path_listing", "metadata"], "reason": "path_listing",
         "against_commit": "b" * 40, "metadata_paths": [f"pkg{i:02d}/{'m' * 40}/package.json" for i in range(10)],
         "metadata_paths_omitted": 5}


def files(length: int) -> dict[str, Any]:
    stem = "d" * max(1, length - 3)
    out: dict[str, Any] = {f"{stem}{i:03d}/x.py": b"" for i in range(slices.ROWS + 5)}
    out |= {f"v{stem[1:]}{i:03d}/vendor/v.c": b"" for i in range(slices.HINTS + 5)}
    return out


def size(lines: list[str]) -> int:
    return sum(len(line.encode("utf-8")) + 1 for line in lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--names", default="8,30,60,120", help="directory-name lengths, comma-separated")
    args = ap.parse_args()
    print(f"bound: {slices.ROWS} rows, {slices.HINTS} hints, {slices.SLICE_MAX_BYTES} bytes")
    for length in (int(n) for n in args.names.split(",")):
        record = structural.generate(tree_of(files(length)), rules.load())
        record = {**record, "artifact_sha256": seal(record)[0]}
        for label, fresh in (("CURRENT", CURRENT), ("STALE", STALE)):
            body = slices.body(record, fresh, [])
            cut = any("byte bound" in line for line in body)
            note = "  (cut by the byte bound)" if cut else ""
            print(f"names {length:4d} chars, {label:7s}: {size(body):6,d} bytes{note}")


if __name__ == "__main__":
    main()
