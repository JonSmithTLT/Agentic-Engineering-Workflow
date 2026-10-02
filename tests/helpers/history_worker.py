"""Subprocess worker: ``python history_worker.py <root> <units> [prewritten]``.

Runs one archival transaction of ``units`` units against the store at ``root``, so a real process can be killed at a
history fault point (AEW_FAULT).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from history_model import archive  # noqa: E402
from store_model import make_store  # noqa: E402


def main() -> int:
    archive(make_store(Path(sys.argv[1])), int(sys.argv[2]), prewritten=len(sys.argv) > 3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
