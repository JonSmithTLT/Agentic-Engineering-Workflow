"""Install checksum-pinned tools for evidence collection and publication."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

GITLEAKS_VERSION = "8.28.0"
GITLEAKS = {
    "linux": (f"gitleaks_{GITLEAKS_VERSION}_linux_x64.tar.gz",
              "a65b5253807a68ac0cafa4414031fd740aeb55f54fb7e55f386acb52e6a840eb"),
    "win32": (f"gitleaks_{GITLEAKS_VERSION}_windows_x64.zip",
              "da6458e8864af553807de1c46a7a8eac0880bd6b99ba56288e87e86a45af884f"),
}
GITLEAKS_URL = f"https://github.com/gitleaks/gitleaks/releases/download/v{GITLEAKS_VERSION}/"
# A single attempt stalled with 0 bytes for its whole 20 s on three Windows shards on 2026-11-26 (register E3), and a
# lane with no scanner withholds its report, so assurance fails although its tests passed. So the download is tried a
# bounded number of times: each attempt ends after 10 s below 1 KiB/s (a stall) or 20 s in all, and the whole is at
# most 3 x 25 s + 6 s of backoff. That time comes out of the job's absolute test deadline (AEW_JOB_DEADLINE), never
# past the lane step's timeout. Only the download is retried: a checksum mismatch is never a reason to try again.
SCANNER_ATTEMPTS = 3
SCANNER_BACKOFF_S = (2.0, 4.0)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def download_scanner(archive: str, path: Path) -> None:
    for attempt in range(1, SCANNER_ATTEMPTS + 1):
        try:
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--connect-timeout", "5",
                            "--speed-limit", "1024", "--speed-time", "10", "--max-time", "20",
                            "--output", str(path), GITLEAKS_URL + archive],
                           check=True, timeout=25, creationflags=_NO_WINDOW)
            return
        except subprocess.SubprocessError as exc:
            if attempt == SCANNER_ATTEMPTS:
                raise
            print(f"evidence scanner download attempt {attempt} of {SCANNER_ATTEMPTS} failed ({exc}); retrying",
                  flush=True)
            time.sleep(SCANNER_BACKOFF_S[attempt - 1])
PYSPY = {
    "linux": "6a80ec05eb8a6883863a367c6a4d4f2d57de68466f7956b6367d4edd5c61bb29",
    "win32": "d92e522bd40e9bf7d87c204033ce5bb5c828fca45fa28d970f58d71128069fdc",
}


def install_scanner(target: Path) -> None:
    archive, digest = GITLEAKS[sys.platform]
    binary = "gitleaks.exe" if sys.platform == "win32" else "gitleaks"
    if not (target / binary).exists():
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / archive
            download_scanner(archive, path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("evidence scanner checksum mismatch")
            if sys.platform == "win32":
                with zipfile.ZipFile(path) as bundle:
                    (target / binary).write_bytes(bundle.read(binary))
            else:
                with tarfile.open(path) as bundle:
                    stream = bundle.extractfile(binary)
                    if stream is None:
                        raise ValueError("evidence scanner binary missing")
                    (target / binary).write_bytes(stream.read())
                (target / binary).chmod(0o755)


def install_spy(target: Path) -> None:
    stamp = target / "py-spy-0.4.1"
    if stamp.exists():
        return
    with tempfile.TemporaryDirectory() as temporary:
        requirements = Path(temporary) / "requirements.txt"
        requirements.write_text("py-spy==0.4.1 --hash=sha256:" + PYSPY[sys.platform] + "\n", encoding="utf-8")
        subprocess.run([sys.executable, "-m", "pip", "install", "--require-hashes", "--only-binary=:all:",
                        "-r", str(requirements)], check=True, timeout=60, creationflags=_NO_WINDOW)
    stamp.touch()


def main(*, scanner_only: bool = False) -> None:
    target = Path(os.environ["RUNNER_TEMP"]) / "evidence-tools"
    target.mkdir(parents=True, exist_ok=True)
    with Path(os.environ["GITHUB_PATH"]).open("a", encoding="utf-8") as output:
        output.write(str(target) + "\n")
    tools = [("scanner", "scan", install_scanner)]
    if not scanner_only:
        tools.append(("spy", "py-spy", install_spy))
    for key, label, install in tools:
        try:
            install(target)
            available = True
        except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile, tarfile.TarError):
            print(f"::warning::evidence defect: {label} unavailable")
            available = False
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"{key}={str(available).lower()}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner-only", action="store_true", help="prepare a standalone evidence publication")
    main(scanner_only=parser.parse_args().scanner_only)
