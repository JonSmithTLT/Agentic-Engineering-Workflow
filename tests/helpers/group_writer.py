"""Subprocess store writer for the store-group tests: ``python group_writer.py <aew root> commit|hold [<hold file>]``.

``commit`` runs one workload transaction and exits: a short-lived ``aew`` command. ``hold`` commits once, writes
``<hold file>.ready``, then stays a running store writer while ``<hold file>`` exists (120 s at most), commits again
when ``<hold file>.again`` appears, and exits: a long-lived writer such as a Lead broker. Its host and its credentials
come from the test's seam (``host_seam``), so a test can give it a session older than the group.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store_model import make_store, one_transaction  # noqa: E402

LIMIT_S = 120.0


def main() -> int:
    root, mode = Path(sys.argv[1]), sys.argv[2]
    store = make_store(root)
    one_transaction(store)
    if mode == "commit":
        return 0
    hold = Path(sys.argv[3])
    Path(str(hold) + ".ready").write_text("ready\n", encoding="utf-8")
    again = Path(str(hold) + ".again")
    deadline = time.monotonic() + LIMIT_S
    while hold.exists() and time.monotonic() < deadline:
        if again.exists():
            again.unlink()
            one_transaction(store)
            Path(str(hold) + ".done").write_text("done\n", encoding="utf-8")
        time.sleep(0.05)
    return 0


if __name__ == "__main__":
    sys.exit(main())
