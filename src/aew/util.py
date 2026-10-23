"""Small shared helpers: time, hashing, YAML/frontmatter I/O, crash-safe file writes."""

from __future__ import annotations

import codecs
import hashlib
import os
import re
import sys
import tempfile
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from aew.errors import IntegrityError, UsageError, ValidationFailed

IS_WINDOWS = sys.platform == "win32"
_BYTE_ORDER_MARKS = ((codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"))


def decode_text(raw: bytes, *, source: str) -> str:
    """Text given to AEW is UTF-8. A byte-order mark is honoured and removed: UTF-8's, which Windows PowerShell 5.1
    writes for ``-Encoding utf8``, and UTF-16's, which it writes for ``>`` and ``Out-File``. Anything else that is
    not UTF-8 is refused: it is never decoded with a platform code page (found by the M3 step-8 live trials)."""
    encoding = "utf-8"
    for mark, codec in _BYTE_ORDER_MARKS:
        if raw.startswith(mark):
            raw, encoding = raw[len(mark):], codec
            break
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise UsageError(f"{source} is not {encoding.upper()} text (an undecodable byte at offset {exc.start}); "
                         "AEW reads text as UTF-8", source=source) from None


def read_text_input(value: str | None) -> str:
    """A ``--file``-style argument: a path, or ``-`` for stdin. Read once, as bytes (:func:`decode_text`)."""
    if not value:
        return ""
    if value == "-":
        stream = getattr(sys.stdin, "buffer", None)
        return decode_text(stream.read(), source="stdin") if stream is not None else sys.stdin.read()
    try:
        raw = Path(value).read_bytes()
    except OSError as exc:
        raise UsageError(f"cannot read {value}: {exc.strerror or exc}", path=value) from None
    return decode_text(raw, source=value)


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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


# libyaml when PyYAML was built with it (M3 step 7, m3-performance.md): about 6x faster in both directions on AEW's
# control state, with the same Python constructors and representers, so the values read and the bytes written are
# identical (checked on every YAML document of a large project; tests/unit/test_yaml_backends.py).
_SafeLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_SafeDumperBase = getattr(yaml, "CSafeDumper", yaml.SafeDumper)

# How deep a YAML document AEW reads or writes may nest, an implementation bound. libyaml's composer recurses in C with
# no depth check: on Windows it overflows the stack and kills the process, with no RecursionError to catch, from about
# 2,660 levels on Python 3.11 and 3,970 on 3.13 (measured 2026-10-23, PyYAML 6.0.3, the main thread; the nightly's
# Python 3.11 job had crashed on a 3,000-level hostile document every night since 2026-10-13). The pure-Python
# composer raises RecursionError from about 330. The deepest document AEW has is 13 levels (the dashboard contract),
# and a test keeps every YAML file in the repository within the bound. AEW's writer holds the same bound, so nothing
# AEW wrote is ever refused when it is read back: control state has free-form objects, and with a bound on reading
# alone one deep value committed there would make the project's own store unreadable.
YAML_MAX_DEPTH = 64
YAML_TOO_DEEP = "yaml_too_deep"  # the reason code a ValidationFailed carries for a document past the bound
_OPENS = (yaml.SequenceStartEvent, yaml.MappingStartEvent)
_CLOSES = (yaml.SequenceEndEvent, yaml.MappingEndEvent)


class _Bounded(yaml.representer.SafeRepresenter):
    """A representer that refuses a collection nested deeper than :data:`YAML_MAX_DEPTH`: AEW never writes a document
    it would not read back. It counts as reading does, one level per mapping or sequence."""

    _depth = 0

    def represent_mapping(self, tag: str, mapping: Any, flow_style: Any = None) -> yaml.MappingNode:
        self._enter()
        try:
            return super().represent_mapping(tag, mapping, flow_style)
        finally:
            self._depth -= 1

    def represent_sequence(self, tag: str, sequence: Any, flow_style: Any = None) -> yaml.SequenceNode:
        self._enter()
        try:
            return super().represent_sequence(tag, sequence, flow_style)
        finally:
            self._depth -= 1

    def _enter(self) -> None:
        self._depth += 1
        if self._depth > YAML_MAX_DEPTH:
            self._depth -= 1
            raise ValidationFailed(f"the data nests deeper than {YAML_MAX_DEPTH} levels: AEW does not write a YAML "
                                   "document it would not read back; give it less nesting", reason=YAML_TOO_DEEP,
                                   limit=YAML_MAX_DEPTH)


class _Dumper(_Bounded, _SafeDumperBase):  # type: ignore[valid-type,misc]
    pass


class _PyYAMLLayoutDumper(_Bounded, yaml.SafeDumper):
    pass


def yaml_backend() -> str:
    """``libyaml`` when PyYAML was built with it, else ``pure-python`` (``aew doctor`` reports it: M3 audit A2)."""
    return "libyaml" if _SafeLoader is getattr(yaml, "CSafeLoader", None) else "pure-python"


def _str_representer(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_representer)


def dump_yaml(data: Any) -> str:
    """``data`` as YAML in AEW's layout; nesting deeper than :data:`YAML_MAX_DEPTH` is a ValidationFailed (reason
    :data:`YAML_TOO_DEEP`), raised before anything is written."""
    return yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    )


def safe_dump_yaml(data: Any) -> str:
    """``data`` as YAML in PyYAML's own ``safe_dump`` layout, byte for byte, with :func:`dump_yaml`'s bound. The
    disposition records and ended stage intents have always been written in this layout, and their hashes are pinned
    where they are cited."""
    return yaml.dump(data, Dumper=_PyYAMLLayoutDumper, sort_keys=False, allow_unicode=True)


def yaml_too_deep(text: str, *, loader: Any = _SafeLoader, limit: int = YAML_MAX_DEPTH) -> int | None:
    """The 1-based line where ``text`` first nests deeper than ``limit``, or None. It reads the event stream, which
    libyaml and PyYAML both parse without recursing, so it is safe on a document that composing would crash on. Call
    it before composing anything that may be hostile; a syntax error raises ``yaml.YAMLError`` as composing would."""
    depth = 0
    for event in yaml.parse(text, Loader=loader):  # noqa: S506 - events only, nothing is constructed
        if isinstance(event, _OPENS):
            depth += 1
            if depth > limit:
                return event.start_mark.line + 1
        elif isinstance(event, _CLOSES):
            depth -= 1
    return None


def load_yaml(text: str, *, source: str = "<yaml>") -> Any:
    """``text`` as YAML, safely: a syntax error, or a nesting deeper than :data:`YAML_MAX_DEPTH` (reason
    :data:`YAML_TOO_DEEP`), is a ValidationFailed, never a crash."""
    try:
        line = yaml_too_deep(text)
        if line is not None:
            raise ValidationFailed(f"{source}: the YAML nests deeper than {YAML_MAX_DEPTH} levels (at line {line}): "
                                   "AEW does not read a document that deep", reason=YAML_TOO_DEEP,
                                   limit=YAML_MAX_DEPTH, line=line)
        return yaml.load(text, Loader=_SafeLoader)  # noqa: S506 (_SafeLoader is a SafeLoader subclass)
    except yaml.YAMLError as exc:
        raise ValidationFailed(f"{source}: invalid YAML: {exc}") from exc


def load_own_yaml(text: str, *, source: str) -> Any:
    """``text`` as YAML without :func:`load_yaml`'s depth pass, for the control store's own files only. Their bytes are
    checked against the hash recorded with them before this is called (control state's checksum trailer, a redo
    record's sha256 in control state), and only :func:`dump_yaml` writes them, which never nests past the bound, so the
    pass could not refuse them. It is skipped for its cost, which is linear in the file and paid by every command: 39 ms
    on an 89 ms parse at 50 units, 379 ms on 1.34 s at 500 (measured 2026-10-23, Windows, libyaml). The hash keeps out
    damage, not a writer: a process that could replace the files could recompute it, and the store's permissions keep
    other writers out. The callers are listed, with their reasons, in tests/unit/test_yaml_depth.py."""
    try:
        return yaml.load(text, Loader=_SafeLoader)  # noqa: S506 (_SafeLoader is a SafeLoader subclass)
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
    if IS_WINDOWS:  # pragma: windows-only
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_temp(directory: Path, data: bytes, prefix: str, *, mode: int = 0o600) -> Path:
    """A new temporary file in ``directory`` holding ``data``, fsynced, with permission bits ``mode``. ``mkstemp``
    creates it ``0600`` whatever the umask, and ``fchmod`` on its descriptor is not filtered by the umask either, so
    the mode is exactly ``mode`` (the store's files, STG-05 CB-08). Windows has no such bits: ``mode`` is ignored."""
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=".tmp")
    try:
        # sys.platform, not IS_WINDOWS: Pyright narrows a platform branch only on sys.platform, and os.fchmod is
        # POSIX-only (review of #230, m8)
        if sys.platform != "win32" and mode != 0o600:  # pragma: posix-only
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return Path(tmp)


def replace_with_retry(src: Path, dst: Path) -> None:
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


def atomic_write(path: Path, data: bytes | str, *, mode: int = 0o600) -> None:
    """Replace ``path`` so readers see either the old or the complete new content. The new file has mode ``mode``
    (``write_temp``): the replace publishes that very inode."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    tmp = write_temp(path.parent, raw, prefix=f".{path.name}.", mode=mode)
    try:
        replace_with_retry(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(path.parent)


def create_exclusive(path: Path, data: bytes | str, *, mode: int = 0o600) -> None:
    """Atomically publish a new immutable file with mode ``mode``; fail if ``path`` already exists."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    tmp = write_temp(path.parent, raw, prefix=f".{path.name}.", mode=mode)
    try:
        if IS_WINDOWS:  # pragma: windows-only
            os.rename(tmp, path)  # never overwrites on Windows
        else:  # pragma: posix-only
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
