"""Measure the actual collection and publication interval on the hosted runner."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def main(mode: str, path: Path, label: str = "") -> None:
    if mode == "mark":
        path.write_text(str(time.monotonic()), encoding="utf-8")
        return
    elapsed = time.monotonic() - float(path.read_text())
    text = f"evidence timing {label} {elapsed:.3f}s"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
            output.write(text + "\n")
    path.unlink()


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "")
