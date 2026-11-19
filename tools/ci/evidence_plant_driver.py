"""Apply an external signal to a hosted plant after its worker is in a test."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lane_step import identities  # noqa: E402


def main(root: Path, kind: str) -> None:
    until = time.monotonic() + 90
    while time.monotonic() < until:
        workers = list(root.glob("hang-gw*.txt"))
        controllers = [(directory, identity) for directory, identity in identities(root)
                       if (directory / "controller-pid.txt").exists()
                       and (directory / "controller-pid.txt").read_text().split()[0] == str(identity[0])]
        if workers and controllers:
            time.sleep(2)
            _, identity = controllers[0]
            if kind == "cancel":
                if os.name == "nt":
                    import proctree

                    proctree.end(identity)
                else:
                    os.kill(identity[0], signal.SIGINT)
            elif kind == "sigkill":
                os.kill(identity[0], signal.SIGKILL)
            return
        time.sleep(0.1)
    raise SystemExit("plant did not start before external signal deadline")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
