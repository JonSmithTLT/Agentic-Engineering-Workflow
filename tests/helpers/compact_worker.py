"""Subprocess worker: ``python compact_worker.py <root> <window>``.

Compacts the store-model log at ``root`` (``log_compact.compact`` with the control lock, as ``aew history compact``
does) behind a ``window`` small enough for a test. Used to race a lockless reader in another process against a real
compaction, and to hold one at a sealing point (``AEW_PAUSE``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store_model import make_store  # noqa: E402

from aew.engine import log_compact  # noqa: E402


def main() -> int:
    result = log_compact.compact(make_store(Path(sys.argv[1])), window=int(sys.argv[2]))
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
