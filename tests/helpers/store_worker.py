"""Subprocess worker: ``python store_worker.py <root> <count> [expect_rev]``.

Runs ``count`` workload transactions against the store at ``root``. Used to
crash a real process (AEW_FAULT) and to race two writers.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store_model import make_store, one_transaction  # noqa: E402

from aew.errors import StaleRevision  # noqa: E402


def main() -> int:
    root = Path(sys.argv[1])
    count = int(sys.argv[2])
    expect_rev = int(sys.argv[3]) if len(sys.argv) > 3 else None
    store = make_store(root)
    for _ in range(count):
        try:
            one_transaction(store, expect_rev=expect_rev)
        except StaleRevision:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
