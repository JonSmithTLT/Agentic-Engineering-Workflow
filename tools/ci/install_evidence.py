"""Install checksum-pinned tools for evidence collection and publication."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

GITLEAKS = {
    "linux": ("gitleaks_8.28.0_linux_x64.tar.gz", "a65b5253807a68ac0cafa4414031fd740aeb55f54fb7e55f386acb52e6a840eb"),
    "win32": ("gitleaks_8.28.0_windows_x64.zip", "da6458e8864af553807de1c46a7a8eac0880bd6b99ba56288e87e86a45af884f"),
}
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
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--connect-timeout", "5",
                            "--max-time", "20", "--output", str(path),
                            "https://github.com/gitleaks/gitleaks/releases/download/v8.28.0/" + archive],
                           check=True, timeout=25)
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
                        "-r", str(requirements)], check=True, timeout=60)
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
