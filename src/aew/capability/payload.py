"""A provider's payload: the pinned fetch, the offline import and the check of the pin (STG-15, A-38: CAPR-03, CAPR-04).

A payload is one executable taken from a release archive. Both are pinned: the archive by its SHA-256 and size, the
executable by its own SHA-256 and size. The archive's pin is checked as it is read, at the fetch and at an import;
the executable's at its install and at every check (:func:`verify`). Nothing is run from an archive, and nothing but
the record's one member is read out of it, so an archive's other entries (links, absolute or parent paths) are never
written anywhere.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import tarfile
import zipfile
import zlib
from pathlib import Path
from typing import IO, Any

from aew.capability import store
from aew.errors import IntegrityError, Unavailable
from aew.util import write_temp

FETCH_TIMEOUT_S = 60.0  # one socket operation (connect, or one read) of the fetch; the archive is a few MB
CHUNK = 1 << 16


class PinMismatch(IntegrityError):
    """A payload, or the archive it comes from, does not match its pin: it is refused (``details["reason"]``)."""


def fetch(payload: dict[str, Any]) -> bytes:
    """The archive from the record's source, read to at most its pinned size and checked against its pin. Raises
    ``Unavailable`` (reason ``fetch_failed``) when it cannot be fetched, and ``PinMismatch`` when it is not the pinned
    archive."""
    import urllib.error
    import urllib.request

    source = payload["source"]
    try:  # the record's source is an https URL (the schema's pattern); urllib honours HTTPS_PROXY
        with urllib.request.urlopen(source, timeout=FETCH_TIMEOUT_S) as response:  # noqa: S310  # https only
            data = _read_bounded(response, payload["archive_size"], what=source)
    except PinMismatch:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Unavailable(f"the pinned payload could not be fetched from {source}: {exc}", source=source,
                          reason="fetch_failed") from None
    check_archive(data, payload, what=source)
    return data


def _read_bounded(fh: IO[bytes], size: int, *, what: str) -> bytes:
    data = fh.read(size + 1)
    if len(data) > size:
        raise PinMismatch(f"{what} is larger than its pinned archive ({size} bytes), so it is refused",
                          reason="archive_size", pinned_size=size)
    return data


def check_archive(data: bytes, payload: dict[str, Any], *, what: str) -> None:
    got = hashlib.sha256(data).hexdigest()
    if got != payload["archive_sha256"] or len(data) != payload["archive_size"]:
        raise PinMismatch(f"{what} does not match its pin (sha256 {got}, {len(data)} bytes; pinned "
                          f"{payload['archive_sha256']}, {payload['archive_size']} bytes), so it is refused",
                          reason="archive_pin", sha256=got, pinned=payload["archive_sha256"])


def member(data: bytes, payload: dict[str, Any]) -> bytes:
    """The record's one member of a checked archive, a regular file, checked against the executable's pin."""
    name = payload["member"]
    try:
        if payload["source"].endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                info = archive.getinfo(name)
                if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise KeyError(name)
                with archive.open(info) as fh:
                    body = fh.read(payload["size"] + 1)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                entry = archive.getmember(name)
                extracted = archive.extractfile(entry) if entry.isfile() else None
                if extracted is None:
                    raise KeyError(name)
                body = extracted.read(payload["size"] + 1)
    except KeyError:
        raise PinMismatch(f"the pinned archive holds no regular file {name}", reason="member_missing",
                          member=name) from None
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError, zlib.error, RuntimeError,
            NotImplementedError) as exc:  # the last three: an encrypted entry, an unknown method, damaged data (F7)
        raise PinMismatch(f"the pinned archive cannot be read ({exc})", reason="archive_unreadable") from None
    got = hashlib.sha256(body).hexdigest()
    if got != payload["sha256"] or len(body) != payload["size"]:
        raise PinMismatch(f"the archive's {name} does not match its pin (sha256 {got}; pinned {payload['sha256']}), "
                          "so it is refused", reason="payload_pin", sha256=got, pinned=payload["sha256"])
    return body


def install(name: str, command: str, payload: dict[str, Any], body: bytes, directory: Path | None = None) -> Path:
    """Write a checked executable into its own directory, read-only and executable, replacing any copy there."""
    target_dir = store.payload_dir(name, payload["sha256"], directory)
    target = target_dir / store.executable_name(command)
    with store.writing(directory or store.root()):
        target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = write_temp(target_dir, body, prefix=f".{target.name}.")
        try:
            os.chmod(tmp, 0o500)  # the operator's own, as a contained run is: read and run, never written
            if target.exists():
                os.chmod(target, 0o700)  # Windows refuses to replace a read-only file
            os.replace(tmp, target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    return target


def path_of(name: str, command: str, payload: dict[str, Any], directory: Path | None = None) -> Path:
    return store.payload_dir(name, payload["sha256"], directory) / store.executable_name(command)


def verify(path: Path, payload: dict[str, Any]) -> str | None:
    """None when the installed executable matches its pin; otherwise why not. Run at every check (CAPR-03)."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK):
                digest.update(chunk)
    except OSError as exc:
        return f"it cannot be read ({exc})"
    got = digest.hexdigest()
    return None if got == payload["sha256"] else f"its sha256 is {got}, and its pin is {payload['sha256']}"


def discard(name: str, payload: dict[str, Any], directory: Path | None = None) -> None:
    """Remove a refused payload, so the next fetch or import can replace it."""
    target = store.payload_dir(name, payload["sha256"], directory)
    if not target.is_dir():
        return
    # A payload left behind is refused again at every read: say so, never ignore it
    with store.writing(directory or store.root()):
        for child in target.iterdir():  # Windows will not remove a read-only file
            os.chmod(child, 0o700)
        shutil.rmtree(target)
