"""Subprocess worker: ``python lock_worker.py <lock> <takes> <hold_s> <name> <order> <go>``.

Takes the ``FileLock`` at ``lock`` ``takes`` times back to back, holding it ``hold_s`` each time, and appends ``name``
to ``order`` while it holds it, so that file is the exact order of holders. It writes ``<go>.<name>.ready`` once
imported and starts when ``go`` exists, so racers start together. Prints its waits (asked to held, in seconds) as a
JSON list. Exits 2 if ``go`` never appears.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from aew.engine.lock import FileLock

GO_WAIT_S = 60  # bounded: the test writes ``go`` once every racer is ready, and fails on its own bound before this


def main() -> int:
    lock, takes, hold, name = Path(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    order, go = Path(sys.argv[5]), Path(sys.argv[6])
    go.with_name(f"{go.name}.{name}.ready").write_text("ready")
    deadline = time.monotonic() + GO_WAIT_S
    while not go.exists():
        if time.monotonic() > deadline:
            return 2
        time.sleep(0.002)
    waits = []
    for _ in range(takes):
        asked = time.monotonic()
        with FileLock(lock):
            waits.append(time.monotonic() - asked)
            with order.open("a", encoding="utf-8") as fh:
                fh.write(name)
            time.sleep(hold)
    print(json.dumps(waits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
