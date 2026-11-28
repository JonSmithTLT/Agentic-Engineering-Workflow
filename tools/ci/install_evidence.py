"""Install checksum-pinned tools for evidence collection and publication."""

from __future__ import annotations

import argparse
import hashlib
import io
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
# most 3 x 25 s + 6 s of backoff. In a lane that time comes out of the job's absolute test deadline (AEW_JOB_DEADLINE);
# the --scanner-only installs (publish-evidence, the cancel record, and the lane's retry after a passing pytest, whose
# time comes from the publication budget a passing lane does not spend) have no such deadline, so there it adds to the
# step's run time. Only the download is retried: a checksum mismatch is never a reason to try again.
SCANNER_ATTEMPTS = 3
SCANNER_BACKOFF_S = (2.0, 4.0)
# On 2026-11-27 all three attempts of one Linux lane got HTTP 403 from the release host within 6 s (run 46048405164,
# register E3), and `main` went red with every test passed. So the verified archive is kept in the Actions cache, keyed
# on the platform, the archive (which names the version) and the pinned digest, and the lane action restores it before
# this installer runs and saves it after a miss: a warm job downloads nothing. A cached archive is trusted no more than
# a downloaded one: its bytes are checked against the pinned digest on every install, and a mismatch is discarded and
# downloaded afresh, so the cache can save a download but never supply a scanner the pin does not name.
SCANNER_CACHE = "evidence-scanner"
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


def scanner_cache() -> tuple[Path, str]:
    """The Actions cache entry for the pinned archive: its directory and its key, which the lane action reads from
    `--cache-entry` rather than restating either."""
    archive, digest = GITLEAKS[sys.platform]
    return Path(os.environ["RUNNER_TEMP"]) / SCANNER_CACHE, f"{SCANNER_CACHE}-{sys.platform}-{archive}-{digest}"


def scanner_archive(archive: str, digest: str) -> bytes:
    """The pinned archive's bytes, verified: from the cache when they match the digest, else downloaded. The cache is
    best effort: a cache that cannot be read or written costs a download or the next job's hit, never the install of
    bytes that were verified (review of #659)."""
    cached = scanner_cache()[0] / archive
    try:
        if cached.is_file():
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() == digest:
                return data
            print("evidence scanner cache does not match the pinned digest; downloading", flush=True)
            cached.unlink()
    except OSError as exc:
        print(f"::warning::evidence scanner cache unreadable ({exc}); downloading", flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / archive
        download_scanner(archive, path)
        data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("evidence scanner checksum mismatch")
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    except OSError as exc:
        print(f"::warning::evidence scanner not kept in the cache ({exc}); installing it anyway", flush=True)
    return data


def install_scanner(target: Path) -> None:
    archive, digest = GITLEAKS[sys.platform]
    binary = "gitleaks.exe" if sys.platform == "win32" else "gitleaks"
    if not (target / binary).exists():
        # The bytes extracted are the bytes verified: nothing is read back from disk after the check.
        data = io.BytesIO(scanner_archive(archive, digest))
        if sys.platform == "win32":
            with zipfile.ZipFile(data) as bundle:
                (target / binary).write_bytes(bundle.read(binary))
        else:
            with tarfile.open(fileobj=data) as bundle:
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


def cache_entry() -> None:
    path, key = scanner_cache()
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"path={path}\nkey={key}\n")


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
    parser.add_argument("--cache-entry", action="store_true", help="name the scanner's Actions cache path and key")
    arguments = parser.parse_args()
    if arguments.cache_entry:
        cache_entry()
    else:
        main(scanner_only=arguments.scanner_only)
