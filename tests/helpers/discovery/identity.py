"""The discovery lanes' identity check (discovery-layer spec v3.4, §5 and §6.1, J2): before anything is judged, the
`aew` this process imports must be the commit under test, or the lane would judge another product's texts silently.
The caller passes the paths: the lane's conftest names its own checkout."""

from __future__ import annotations

import tomllib
from pathlib import Path


def problems(aew_file: str, version: str, src: Path, pyproject: Path) -> list[str]:
    """Why the imported ``aew`` (its ``__file__`` and ``__version__``) is not the checkout's own (``src``, and the
    version ``pyproject`` declares), or ``[]``."""
    out = []
    if not Path(aew_file).resolve().is_relative_to(src.resolve()):
        out.append(f"aew is imported from {aew_file}, not from the commit under test ({src})")
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    if version != declared:
        out.append(f"aew reports version {version}, the commit under test declares {declared}")
    return out
