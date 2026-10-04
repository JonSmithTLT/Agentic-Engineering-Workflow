"""R2 (POSIX): two processes hold the control lock at once after the lock file is unlinked under the first.

    python lock_identity.py <dir>

Process 1 takes FileLock(<dir>/local/control.lock) and holds it. The lock file is then unlinked (as removing
`.aew/local`, which ADR-0011 calls disposable, does). Process 2 opens the path anew: a different inode, so its
flock() succeeds immediately while process 1 still holds its lock.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HOLDER = r"""
import sys, time
from pathlib import Path
from aew.engine.lock import FileLock
with FileLock(Path(sys.argv[1]) / "local" / "control.lock", timeout=5):
    print("P1 holds the lock", flush=True)
    time.sleep(float(sys.argv[2]))
print("P1 released", flush=True)
"""
TAKER = r"""
import sys, time
from pathlib import Path
from aew.engine.lock import FileLock
t0 = time.monotonic()
try:
    with FileLock(Path(sys.argv[1]) / "local" / "control.lock", timeout=3):
        print(f"P2 ACQUIRED after {time.monotonic() - t0:.2f}s while P1 still holds it", flush=True)
except Exception as exc:
    print(f"P2 refused: {type(exc).__name__} after {time.monotonic() - t0:.2f}s", flush=True)
"""


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    (root / "local").mkdir(parents=True, exist_ok=True)
    p1 = subprocess.Popen([sys.executable, "-c", HOLDER, str(root), "8"], stdout=sys.stdout)
    time.sleep(1.5)
    print("control: a second taker is refused while the file is in place")
    subprocess.run([sys.executable, "-c", TAKER, str(root)], check=False)
    os.unlink(root / "local" / "control.lock")
    print("after unlinking local/control.lock:")
    subprocess.run([sys.executable, "-c", TAKER, str(root)], check=False)
    p1.wait()


if __name__ == "__main__":
    main()
