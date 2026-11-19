"""Check hosted stack attachment from the supervisor and a later collection step."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "helpers"))
import proctree  # noqa: E402


def probe_wait(ready: Path) -> None:
    ready.write_text("ready\n", encoding="utf-8")
    threading.Event().wait(180)


def attach(identity: tuple[int, int]) -> str:
    binary = shutil.which("py-spy")
    if binary is None or not proctree.same(identity):
        raise RuntimeError("first-push check failed: py-spy or its live target is missing")
    prefixes = [[]]
    if sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true":
        prefixes.append(["sudo", "-n"])
    for prefix in prefixes:
        result = subprocess.run([*prefix, binary, "dump", "--nonblocking", "--pid", str(identity[0])],
                                capture_output=True, text=True, timeout=3,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0 and "probe_wait" in result.stdout:
            mode = "sudo" if prefix else "unelevated"
            print(f"first-push attachment check passed: {mode}; Python {sys.version.split()[0]}")
            return mode
    raise RuntimeError("first-push check failed: neither permitted attachment form captured the target frame")


def main(mode: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    record = directory / "identity.json"
    if mode == "target":
        probe_wait(directory / "ready")
        return
    if mode == "start":
        child = subprocess.Popen([sys.executable, __file__, "target", str(directory)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        until = time.monotonic() + 5
        while not (directory / "ready").exists() and time.monotonic() < until:
            time.sleep(0.05)
        identity = proctree.identity(child.pid)
        if identity is None or not (directory / "ready").exists():
            child.kill()
            raise RuntimeError("first-push attachment target did not start")
        record.write_text(json.dumps(identity), encoding="utf-8")
        try:
            attach(identity)
        except BaseException:
            proctree.end(identity)
            raise
    else:
        if not record.is_file():
            raise RuntimeError("first-push later-step target was not recorded")
        identity = tuple(json.loads(record.read_text()))
        try:
            selected = attach(identity)
            with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
                output.write(f"AEW_PYSPY_SUDO={int(selected == 'sudo')}\n")
        finally:
            proctree.end(identity)


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
