#!/usr/bin/env python3
"""Import the frontend's production build into the Python package, with its provenance (design note §4.13, R20).

    python tools/dashboard/import_build.py <dist> --source-commit <sha> --builder-image sha256:<id> \\
        --node v22.22.2 --npm 10.9.7 --built-at 2026-10-06T02:24:21Z

``<dist>`` is the production ``dist/`` the pinned offline builder produced from a clean detached checkout of
``--source-commit`` (``web/scripts/offline-gate.sh``; ``web/docs/how-to/pinned-web-builder.md``). The commit is the
one agreed with the web agent and the operator, never the newest frontend by default.

The tool refuses anything in ``<dist>`` that is not a regular file named ``index.html`` or ``favicon.svg`` or directly
under ``assets/`` (no links, no nested directories, nothing else), replaces ``src/aew/dashboard/static/`` with the
build, and writes ``BUILD.json``. Every digest it records that is not a file of the build is read from this
repository's git objects at the source commit (the commit's tree, ``web/``'s tree, ``package.json``,
``package-lock.json`` and the contract), so the record says what the commit holds, not what a working tree holds.
A rebuild is a new import, a new ``BUILD.json`` and a reviewed diff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "aew" / "dashboard" / "static"
SCHEMA = "aew/dashboard-build/v1"
CONTRACT_REL = "docs/design/dashboard-api-v1-provisional.yaml"
TOP_FILES = frozenset({"index.html", "favicon.svg"})
ASSET_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True,
                          creationflags=NO_WINDOW).stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_files(dist: Path) -> dict[str, Path]:
    """Every file of the build by its published path, or ``SystemExit`` naming what is refused."""
    if not (dist / "index.html").is_file():
        raise SystemExit(f"{dist} has no index.html: not a production build")
    files: dict[str, Path] = {}
    for entry in sorted(dist.rglob("*")):
        rel = entry.relative_to(dist).as_posix()
        if entry.is_symlink():
            raise SystemExit(f"refused: {rel} is a link")
        if entry.is_dir():
            if rel != "assets":
                raise SystemExit(f"refused: directory {rel} (only assets/ is allowed)")
            continue
        if not entry.is_file():
            raise SystemExit(f"refused: {rel} is not a regular file")
        parts = rel.split("/")
        if not (rel in TOP_FILES or (len(parts) == 2 and parts[0] == "assets" and ASSET_NAME.match(parts[1]))):
            raise SystemExit(f"refused: {rel} (only index.html, favicon.svg and assets/<name>)")
        files[rel] = entry
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Import the frontend's production build into the package.")
    ap.add_argument("dist", type=Path)
    ap.add_argument("--source-commit", required=True)
    ap.add_argument("--builder-image", required=True, help="the pinned offline builder's immutable image id")
    ap.add_argument("--node", required=True, help="node --version inside the builder")
    ap.add_argument("--npm", required=True, help="npm --version inside the builder")
    ap.add_argument("--built-at", required=True, help="UTC time the build finished, YYYY-MM-DDTHH:MM:SSZ")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", a.builder_image):
        raise SystemExit("--builder-image is an immutable sha256:<64 hex> image id")
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", a.built_at):
        raise SystemExit("--built-at is YYYY-MM-DDTHH:MM:SSZ")
    commit = git("rev-parse", "--verify", f"{a.source_commit}^{{commit}}").decode().strip()
    files = build_files(a.dist)
    record = {
        "schema": SCHEMA,
        "source": {"commit": commit, "tree": git("rev-parse", f"{commit}^{{tree}}").decode().strip(),
                   "web_tree": git("rev-parse", f"{commit}:web").decode().strip()},
        "contract": {"path": CONTRACT_REL, "sha256": sha256(git("show", f"{commit}:{CONTRACT_REL}"))},
        "builder": {"image": a.builder_image, "node": a.node, "npm": a.npm,
                    "procedure": "web/scripts/offline-gate.sh (npm run build), clean detached checkout"},
        "inputs": {"web/package.json": sha256(git("show", f"{commit}:web/package.json")),
                   "web/package-lock.json": sha256(git("show", f"{commit}:web/package-lock.json"))},
        "built_at": a.built_at,
        "files": {rel: sha256(path.read_bytes()) for rel, path in sorted(files.items())},
    }
    if STATIC.exists():
        shutil.rmtree(STATIC)
    (STATIC / "assets").mkdir(parents=True)
    for rel, path in files.items():
        shutil.copyfile(path, STATIC / rel)
    (STATIC / "BUILD.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                       newline="\n")
    print(f"imported {len(files)} files from {commit[:12]} into {STATIC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
