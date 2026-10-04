"""Make the frozen checkout's test helpers importable from the review folder (never from inside the tree)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

TREE = Path(__file__).resolve().parents[1] / "tree"
for p in (TREE / "tests", TREE / "tests" / "helpers"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
for key in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_FAULT", "AEW_FAULT_MODE", "AEW_PAUSE"):
    os.environ.pop(key, None)
