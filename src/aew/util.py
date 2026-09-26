"""Small shared helpers: time, hashing, YAML/frontmatter I/O, crash-safe file writes."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from aew.errors import IntegrityError, ValidationFailed

IS_WINDOWS = sys.platform == "win32"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str | None:
    """Return the file's sha256, or None when it does not exist."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
    except FileNotFoundError:
        return None
    return digest.hexdigest()


# --------------------------------------------------------------------------- YAML


class _Dumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_representer)


def dump_yaml(data: Any) -> str:
    return yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    )


def load_yaml(text: str, *, source: str = "<yaml>") -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationFailed(f"{source}: invalid YAML: {exc}") from exc


def read_yaml(path: Path) -> Any:
    return load_yaml(path.read_text(encoding="utf-8"), source=str(path))


# --------------------------------------------------------------------------- frontmatter

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def parse_frontmatter(text: str, *, source: str = "<document>") -> tuple[dict[str, Any], str]:
    text = text.replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if not match:
        raise ValidationFailed(f"{source}: missing YAML frontmatter")
    meta = load_yaml(match.group(1), source=source) or {}
    if not isinstance(meta, dict):
        raise ValidationFailed(f"{source}: frontmatter must be a mapping")
    return meta, match.group(2)


def render_frontmatter(meta: dict[str, Any], body: str) -> str:
    body = body.replace("\r\n", "\n")
    if body and not body.endswith("\n"):
        body += "\n"
    return f"---\n{dump_yaml(meta)}---\n{body}"


# --------------------------------------------------------------------------- crash-safe writes


def fsync_dir(path: Path) -> None:
    """Persist a directory entry change (rename/create). No-op on Windows."""
    if IS_WINDOWS:
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_temp(directory: Path, data: bytes, prefix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return Path(tmp)


def _replace_with_retry(src: Path, dst: Path) -> None:
    # Windows refuses to replace a file another process holds open (editors,
    # indexers, antivirus). Retry briefly instead of failing the transition.
    deadline = time.monotonic() + 5.0
    while True:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not IS_WINDOWS or time.monotonic() > deadline:
                raise
            time.sleep(0.05)


def atomic_write(path: Path, data: bytes | str) -> None:
    """Replace ``path`` so readers see either the old or the complete new content."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    tmp = _write_temp(path.parent, raw, prefix=f".{path.name}.")
    try:
        _replace_with_retry(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(path.parent)


def create_exclusive(path: Path, data: bytes | str) -> None:
    """Atomically publish a new immutable file; fail if ``path`` already exists."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    tmp = _write_temp(path.parent, raw, prefix=f".{path.name}.")
    try:
        if IS_WINDOWS:
            os.rename(tmp, path)  # never overwrites on Windows
        else:
            os.link(tmp, path)  # atomic "publish if absent"
            tmp.unlink()
    except FileExistsError:
        tmp.unlink(missing_ok=True)
        raise IntegrityError(f"refusing to overwrite immutable file {path}") from None
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(path.parent)


# --------------------------------------------------------------------------- paths & globs


def to_posix(path: str | Path) -> str:
    return str(path).replace("\\", "/")


@lru_cache(maxsize=512)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(path: str, pattern: str) -> bool:
    """Match a repo-relative POSIX path against a glob supporting ``**``."""
    return _glob_regex(to_posix(pattern)).match(to_posix(path)) is not None


def glob_any(path: str, patterns: list[str]) -> bool:
    return any(glob_match(path, p) for p in patterns)
