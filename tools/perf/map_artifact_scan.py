#!/usr/bin/env python3
"""What a dispatch's search for a stored map costs: a measurement, run by hand (register E184; ``aew.maps.store``
SCAN_MAX).

    python tools/perf/map_artifact_scan.py [--count 256] [--newest 256] [--repeat 5]

It stores ``count`` artifacts the size of the generator's caps (``tests/fixtures/maps/caps.json``, each with another
source revision) in a temporary directory, then times ``store.find_structural`` with a window of ``newest`` (default
``SCAN_MAX``): a miss, which reads every artifact in the window, and a hit on the oldest. It prints the best of
``repeat`` runs and the cost per artifact. It reads
no repository and writes only under its temporary directory.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aew.maps import store  # noqa: E402

CAPS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "maps" / "caps.json"


def best(repeat: int, call) -> float:  # type: ignore[no-untyped-def]
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        call()
        times.append(time.perf_counter() - start)
    return min(times)


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--count", type=int, default=store.SCAN_MAX, help="artifacts stored")
    ap.add_argument("--newest", type=int, default=store.SCAN_MAX, help="the search's window (store.SCAN_MAX)")
    ap.add_argument("--repeat", type=int, default=5, help="runs per figure; the best is printed")
    args = ap.parse_args()
    window = args.newest
    caps = {k: v for k, v in json.loads(CAPS.read_bytes()).items() if k != "artifact_sha256"}
    generator = caps["generator"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        size = 0
        for i in range(args.count):
            sha, rel = store.write_artifact(root, {**caps, "source_revision": f"{i:040x}"})
            size = (root / rel).stat().st_size
            time.sleep(0.002)  # distinct modification times, so "newest first" has an order to follow
        miss = best(args.repeat, lambda: store.find_structural(root, source_revision="f" * 40, generator=generator,
                                                               newest=window))
        oldest = f"{0:040x}"
        hit = best(args.repeat, lambda: store.find_structural(root, source_revision=oldest, generator=generator,
                                                              newest=window))
        assert store.find_structural(root, source_revision=oldest, generator=generator,
                                     newest=window) is not None or args.count > window
    read = min(args.count, window)
    print(f"{args.count} artifacts of {size:,d} bytes; window {window} (SCAN_MAX {store.SCAN_MAX})")
    print(f"miss (reads {read}): {miss * 1000:.1f} ms, {miss / read * 1000:.3f} ms per artifact")
    print(f"hit on the oldest: {hit * 1000:.1f} ms")


if __name__ == "__main__":
    main()
