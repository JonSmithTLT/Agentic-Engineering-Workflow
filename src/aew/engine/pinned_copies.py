"""The bytes of each pinned settings file, kept so the operator's adoption can show its diff (register E331).

Control state pins ``project.yaml`` and every policy file by its sha256 (ADR-0001), and holds no copy of the bytes. The
operator's terminal adoption shows each file's diff against the version its pin holds, so the pinned bytes are kept
here when a pin is written (``aew init``, an adoption, an authority decision's rewrite of ``project.yaml``),
content-addressed under ``.aew/local/pinned/``: rebuildable runtime data, gitignored with the rest of ``local/``.

It is a display aid and never authority. A copy is named by its digest and read back only when its bytes hash to that
name, so an edited copy is never shown as the pinned version; a missing one falls back to the newest git commits that
hold the file (:func:`pinned`), and else the prompt says the pinned bytes are not on this host. What the adoption
commits is bound to the digests shown, never to a copy.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from pathlib import Path

from aew.errors import AEWError
from aew.util import atomic_write, sha256_bytes

DIR = "local/pinned"
GIT_COMMITS = 10  # how far back a missing copy is looked for in the file's own git history


def _path(aew_root: Path, sha: str) -> Path:
    return aew_root / DIR / sha


def keep(aew_root: Path, raw: bytes) -> None:
    """Keep ``raw`` by its digest. Best effort: a copy that cannot be written only means a later prompt falls back."""
    path = _path(aew_root, sha256_bytes(raw))
    with contextlib.suppress(OSError, AEWError):
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, raw)


def keep_files(aew_root: Path, pins: Mapping[str, str | None]) -> None:
    """Keep each file under ``aew_root`` whose bytes now are the ones its pin names (after a commit wrote the pins)."""
    for rel, sha in pins.items():
        if sha is None:
            continue
        with contextlib.suppress(OSError):
            raw = (aew_root / rel).read_bytes()
            if sha256_bytes(raw) == sha:
                keep(aew_root, raw)


def _kept(aew_root: Path, sha: str) -> bytes | None:
    try:
        raw = _path(aew_root, sha).read_bytes()
    except OSError:
        return None
    return raw if sha256_bytes(raw) == sha else None


def _from_git(repo_root: Path, path: str, sha: str) -> bytes | None:
    from aew.workspace import git

    try:
        # object_git, bounded and windowless: the history a pin's bytes are looked for in is read like any object
        commits = git.object_git("log", f"-n{GIT_COMMITS}", "--format=%H", "--", path, cwd=repo_root, check=False)
        for commit in commits.stdout.decode("ascii", "replace").split():
            shown = git.object_git("cat-file", "blob", f"{commit}:{path}", cwd=repo_root, check=False)
            if shown.returncode == 0 and sha256_bytes(shown.stdout) == sha:
                return shown.stdout
    except (OSError, AEWError):
        return None
    return None


def pinned(repo_root: Path, aew_root: Path, rel: str, sha: str) -> bytes | None:
    """The bytes the pin ``sha`` of ``.aew/<rel>`` holds, or None when this host has neither a copy nor a commit."""
    kept = _kept(aew_root, sha)
    if kept is not None:
        return kept
    try:
        path = (aew_root / rel).relative_to(repo_root).as_posix()
    except ValueError:
        return None
    return _from_git(repo_root, path, sha)
