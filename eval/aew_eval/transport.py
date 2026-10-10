"""The evaluator/arm-host transport and the bundle format (F19 plan v5 §2.2, §2.3; ADR-0018 D2, D5).

The evaluator initiates every call, and the arm host runs no listener. A call is one **request frame** and one **reply
frame**: a single line of JSON (``aew/m4h-armhost/v1``, at most :attr:`Limits.json_bytes`), then exactly
``payload_bytes`` of payload: a tar for ``release`` (evaluator to arm host) and ``collect`` (arm host to evaluator),
nothing otherwise. Every frame is bounded, strict JSON (no ``NaN`` or ``Infinity``) and schema-validated before
anything reads it, and nothing may follow its payload.

**Bundles.** A bundle is a tar built by :func:`pack`: regular files, and links carried as data entries (their target
text, never followed), with ``MANIFEST.json`` (``aew/m4h-bundle-manifest/v1``) naming every entry's hash. The bundle's
hash is the manifest's. :func:`receive` is the **hostile receive** both sides apply to whatever arrives:

* a stream tar parser that accepts only regular files, directories and link data entries; a hard link, device, FIFO,
  sparse file or any other type refuses the whole bundle;
* relative, normalized, valid UTF-8 paths only (:func:`check_path`: :func:`aew_eval.fixture.safe_relative`, no
  component over 255 bytes, and no two that differ only in case), each file written with ``O_EXCL`` (and
  ``O_NOFOLLOW`` where the platform has it) under a fresh directory this call creates; a link is recorded, never
  created, so nothing written can leave the directory; a write the host refuses is ``WRITE_REFUSED``;
* the bounds of :class:`Limits` (per file, in total, in entries, the manifest's own size: ``MANIFEST_TOO_LARGE``) and
  a deadline;
* the manifest recomputed from what arrived and compared byte for byte, and with the hash the caller expected
  (``TRANSFER_CORRUPT`` otherwise).

A refusal removes what it wrote and raises :class:`TransferError` with a stable ``code``. :func:`pack` refuses
(``OVER_BOUNDS``) whatever :func:`receive` would, the manifest's size and the tar's size on the wire included.

**Transports.** :class:`LocalTransport` runs the arm-host agent (:mod:`aew_eval.armhost`) as a separate process on
this machine, rooted in its own directory, with an allow-listed environment: the stand-in for the SSH transport (S6)
in tests and on Windows CI; it hands the agent its bounds as a host record (``--limits``) and reads the agent's
stderr to its end, keeping the tail. :class:`RecordingTransport` wraps another and keeps every byte that crosses it,
for the canary tests. Neither imports the arm host: the evaluator never runs an arm in its own process.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from aew_eval import fixture
from aew_eval.canonical import canonical
from aew_eval.schemas import Invalid, validate

PROTOCOL = "aew/m4h-armhost/v1"
MANIFEST = "aew/m4h-bundle-manifest/v1"
MANIFEST_NAME = "MANIFEST.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
CHUNK = 1 << 20
MiB = 1 << 20
COMPONENT_BYTES = 255


@dataclass(frozen=True)
class Limits:
    """The transfer bounds (plan v5 §2.3, R4-n5). S12 seals the values a campaign uses, raised to the sealed deliverable
    bound plus the session databases' calibration maximum when that is larger; these are the floors."""

    file_bytes: int = 64 * MiB
    total_bytes: int = 2048 * MiB
    entries: int = 200_000
    json_bytes: int = 1 * MiB
    timeout_s: float = 600.0

    def tar_bytes(self) -> int:
        """The most a bounded tar can take on the wire: the content, a header block or three per entry, the manifest
        and the end-of-archive blocks."""
        return self.total_bytes + self.entries * 2048 + self.file_bytes + 64 * 1024


DEFAULT_LIMITS = Limits()


class TransferError(Invalid):
    """A frame or bundle refused. ``code`` is stable: tests and the run record rely on it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.detail = message


# ---------------------------------------------------------------------------------------------- frames

def encode_frame(message: dict[str, Any], payload: bytes = b"") -> bytes:
    """One frame: the message as one line of canonical JSON, then the payload. ``payload_bytes`` is set here."""
    message = {**message, "schema": PROTOCOL, "payload_bytes": len(payload)}
    validate(PROTOCOL, message, what=f"the {message.get('kind')} frame")
    return canonical(message) + b"\n" + payload


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def _loads(raw: bytes) -> Any:
    """Strict JSON: ``NaN`` and ``Infinity`` are refused (the instrument's canonical encoding has none)."""
    return json.loads(raw.decode("utf-8"), parse_constant=_no_constant)


def decode_frame(data: bytes, *, what: str, limits: Limits, max_payload: int) -> tuple[dict[str, Any], bytes]:
    """A frame's message and payload, refused unless the JSON line is within the bound, parses, validates, and is
    followed by exactly the payload it declares (itself within ``max_payload``)."""
    end = data.find(b"\n", 0, limits.json_bytes + 1)
    if end < 0:
        if len(data) > limits.json_bytes:
            raise TransferError(f"{what.upper()}_TOO_LARGE",
                                f"the {what}'s JSON exceeds {limits.json_bytes} bytes without ending")
        raise TransferError(f"{what.upper()}_MALFORMED", f"the {what} has no complete JSON line")
    try:
        message = _loads(data[:end])
    except (ValueError, RecursionError) as exc:  # json's errors, and UnicodeDecodeError, are ValueErrors
        raise TransferError(f"{what.upper()}_MALFORMED", f"the {what}'s JSON does not parse ({exc})") from None
    try:
        validate(PROTOCOL, message, what=f"the {what}")
    except Invalid as exc:
        raise TransferError(f"{what.upper()}_MALFORMED", str(exc)) from None
    declared = message["payload_bytes"]
    if declared > max_payload:
        raise TransferError("PAYLOAD_TOO_LARGE", f"the {what} declares {declared} payload bytes; the bound is "
                            f"{max_payload}")
    payload = data[end + 1:]
    if len(payload) != declared:
        raise TransferError(f"{what.upper()}_MALFORMED", f"the {what} declares {declared} payload bytes and carries "
                            f"{len(payload)}")
    return message, payload


def read_frame(stream: BinaryIO, *, what: str, limits: Limits, max_payload: int) -> tuple[dict[str, Any], bytes]:
    """:func:`decode_frame` over a stream, reading no more than the bounds allow."""
    line = stream.readline(limits.json_bytes + 1)
    payload = b""
    if line.endswith(b"\n"):
        try:
            declared = _loads(line).get("payload_bytes", 0)
        except (ValueError, AttributeError, RecursionError):
            declared = 0
        if isinstance(declared, int) and 0 < declared <= max_payload:  # otherwise decode_frame names the refusal
            payload = stream.read(declared)
        if len(payload) == declared and stream.read(1):  # exactly payload_bytes, then the end (review F9)
            raise TransferError(f"{what.upper()}_MALFORMED", f"the {what} carries bytes after its payload")
    return decode_frame(line + payload, what=what, limits=limits, max_payload=max_payload)


# ---------------------------------------------------------------------------------------------- bundles

@dataclass(frozen=True)
class Entry:
    """One bundle entry: a regular file's bytes, or a link's target text (``kind`` ``file`` or ``link``)."""

    path: str
    kind: str
    data: bytes = b""
    target: str = ""


def check_path(rel: str, what: str) -> str:
    """A bundle path: relative, normalized, ``/``-separated, the same file on every platform, valid UTF-8 (a name
    that is not cannot be written to a manifest), at most 4096 characters, and no component over 255 bytes (no file
    system holds a longer one: PR #189 review, F1 and F7)."""
    if not isinstance(rel, str) or len(rel) > 4096:
        raise TransferError("UNSAFE_PATH", f"{what}: a path is a string of at most 4096 characters")
    try:
        encoded = [part.encode("utf-8") for part in rel.split("/")]
    except UnicodeEncodeError:
        raise TransferError("UNSAFE_PATH", f"{what}: {printable(rel)} is not valid UTF-8") from None
    if any(len(part) > COMPONENT_BYTES for part in encoded):
        raise TransferError("UNSAFE_PATH", f"{what}: a component of {printable(rel)[:200]} is over "
                            f"{COMPONENT_BYTES} bytes")
    try:
        return fixture.safe_relative(rel, what)
    except Invalid as exc:
        raise TransferError("UNSAFE_PATH", str(exc)) from None


def printable(text: str) -> str:
    """``text`` as something JSON and UTF-8 can always carry: an undecodable byte (a surrogate escape on Linux, a lone
    surrogate on Windows) becomes a backslash escape."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def manifest_of(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": MANIFEST, "entries": sorted(entries, key=lambda e: e["path"])}


def _tarinfo(name: str, *, size: int = 0, kind: bytes = tarfile.REGTYPE, target: str = "") -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size, info.type, info.linkname = size, kind, target
    info.mode = 0o644
    info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
    return info


def pack(entries: Iterable[Entry], *, limits: Limits = DEFAULT_LIMITS) -> tuple[bytes, str]:
    """A bundle: the tar's bytes and its hash (the canonical manifest's SHA-256). Refuses (``OVER_BOUNDS``,
    ``UNSAFE_PATH``, ``PATH_CONFLICT``) what :func:`receive` would refuse, so a sound packer never sends it: the
    entries, each file and the total, and also the manifest's own size and the tar's size on the wire (PR #189
    review, F3)."""
    buf = io.BytesIO()
    listed: list[dict[str, Any]] = []
    seen: dict[str, tuple[str, str]] = {}
    total = 0
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for entry in sorted(entries, key=lambda e: e.path):
            rel = check_path(entry.path, "a bundle entry")
            if rel == MANIFEST_NAME:
                raise TransferError("PATH_CONFLICT", f"{MANIFEST_NAME} is the bundle's own manifest")
            _claim(seen, rel, "file" if entry.kind == "file" else "link")
            if len(listed) + 1 > limits.entries:
                raise TransferError("OVER_BOUNDS", f"more than {limits.entries} entries")
            if entry.kind == "file":
                if len(entry.data) > limits.file_bytes:
                    raise TransferError("OVER_BOUNDS", f"{rel} is {len(entry.data)} bytes; the bound is "
                                        f"{limits.file_bytes}")
                total += len(entry.data)
                if total > limits.total_bytes:
                    raise TransferError("OVER_BOUNDS", f"more than {limits.total_bytes} bytes in total")
                tar.addfile(_tarinfo(rel, size=len(entry.data)), io.BytesIO(entry.data))
                listed.append({"path": rel, "kind": "file", "sha256": hashlib.sha256(entry.data).hexdigest(),
                               "size": len(entry.data)})
            elif entry.kind == "link":
                try:
                    entry.target.encode("utf-8")
                except UnicodeEncodeError:
                    raise TransferError("UNSAFE_PATH", f"{rel}: its link target is not valid UTF-8") from None
                tar.addfile(_tarinfo(rel, kind=tarfile.SYMTYPE, target=entry.target))
                listed.append({"path": rel, "kind": "link", "target": entry.target})
            else:
                raise TransferError("ENTRY_TYPE_REFUSED", f"{rel}: a bundle holds files and links only")
            if buf.tell() > limits.tar_bytes():
                raise TransferError("OVER_BOUNDS", f"the bundle passes {limits.tar_bytes()} bytes on the wire")
        manifest = canonical(manifest_of(listed))
        if len(manifest) > limits.file_bytes:
            raise TransferError("OVER_BOUNDS", f"the manifest is {len(manifest)} bytes; the bound is "
                                f"{limits.file_bytes}")
        tar.addfile(_tarinfo(MANIFEST_NAME, size=len(manifest)), io.BytesIO(manifest))
    if buf.tell() > limits.tar_bytes():
        raise TransferError("OVER_BOUNDS", f"the bundle passes {limits.tar_bytes()} bytes on the wire")
    return buf.getvalue(), hashlib.sha256(manifest).hexdigest()


def _claim(seen: dict[str, tuple[str, str]], rel: str, kind: str) -> None:
    """Record ``rel`` as ``kind``, refusing a duplicate, a name differing from an earlier one only in case (it would
    land differently on Windows and Linux), or a path under a file or link."""
    parts = rel.split("/")
    for n in range(1, len(parts)):
        path = "/".join(parts[:n])
        prior = seen.setdefault(path.casefold(), (path, "dir"))
        if prior[0] != path:
            raise TransferError("PATH_CONFLICT", f"{path} and {prior[0]} differ only in case")
        if prior[1] != "dir":
            raise TransferError("PATH_CONFLICT", f"{rel} lies under {path}, which is a {prior[1]}")
    prior = seen.get(rel.casefold())
    if prior is not None:
        if prior[0] != rel:
            raise TransferError("PATH_CONFLICT", f"{rel} and {prior[0]} differ only in case")
        if not (prior[1] == "dir" and kind == "dir"):
            raise TransferError("PATH_CONFLICT", f"{rel} arrives twice (as a {prior[1]} and as a {kind})")
    seen[rel.casefold()] = (rel, kind)


@dataclass
class Received:
    """What a bundle delivered: its files (path to SHA-256 and size), written under ``root``; its links (path to
    target text), recorded only; and its hash."""

    root: Path
    files: dict[str, tuple[str, int]] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)
    sha256: str = ""


def receive(data: bytes, dest: Path, *, limits: Limits = DEFAULT_LIMITS,
            expected_sha256: str | None = None) -> Received:
    """Hostile receive of the bundle ``data`` into ``dest``, which must not exist. Returns what arrived; refuses with
    :class:`TransferError` (and removes ``dest``) on any rule broken."""
    if len(data) > limits.tar_bytes():
        raise TransferError("PAYLOAD_TOO_LARGE", f"the bundle is {len(data)} bytes; the bound is {limits.tar_bytes()}")
    dest.mkdir(parents=False)  # fresh: FileExistsError if anything is there
    try:
        return _receive(data, dest, limits, expected_sha256)
    except TransferError:
        shutil.rmtree(dest, ignore_errors=True)  # only regular files and directories this call created
        raise
    except (tarfile.TarError, EOFError, ValueError, UnicodeError, RecursionError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise TransferError("TRANSFER_CORRUPT", f"the bundle does not parse ({type(exc).__name__}: {exc})") from None
    except OSError as exc:  # a path this host cannot hold (too long, say): refused with a stable code (review F7)
        shutil.rmtree(dest, ignore_errors=True)
        raise TransferError("WRITE_REFUSED", f"writing the bundle failed ({type(exc).__name__}: {exc})") from None
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def _receive(data: bytes, dest: Path, limits: Limits, expected: str | None) -> Received:
    deadline = time.monotonic() + limits.timeout_s
    out = Received(dest)
    seen: dict[str, tuple[str, str]] = {}
    manifest_bytes: bytes | None = None
    listed: list[dict[str, Any]] = []
    total = count = 0
    try:
        tar = tarfile.open(fileobj=io.BytesIO(data), mode="r|")
    except tarfile.TarError as exc:
        raise TransferError("TRANSFER_CORRUPT", f"the bundle is not a tar ({exc})") from None
    with tar:
        while True:
            if time.monotonic() >= deadline:
                raise TransferError("RECEIVE_TIMEOUT", f"receiving took over {limits.timeout_s:g} s")
            try:
                member = tar.next()
            except tarfile.TarError as exc:
                raise TransferError("TRANSFER_CORRUPT", f"the tar stream breaks ({exc})") from None
            if member is None:
                break
            count += 1
            if count > limits.entries + 1:
                raise TransferError("TOO_MANY_ENTRIES", f"more than {limits.entries} entries")
            name = member.name.rstrip("/") if member.isdir() else member.name
            if name == MANIFEST_NAME and member.isreg():
                if manifest_bytes is not None:
                    raise TransferError("TRANSFER_CORRUPT", f"{MANIFEST_NAME} arrives twice")
                if member.size > limits.file_bytes:
                    raise TransferError("MANIFEST_TOO_LARGE", f"{MANIFEST_NAME} is {member.size} bytes; the bound "
                                        f"is {limits.file_bytes}")
                manifest_bytes = _read_member(tar, member)
                continue
            rel = check_path(name, "a received entry")
            if member.sparse is not None or member.type == tarfile.GNUTYPE_SPARSE or any(
                    k.startswith("GNU.sparse") for k in member.pax_headers):
                raise TransferError("ENTRY_TYPE_REFUSED", f"{rel} is a sparse file; a bundle carries its content "
                                    "as written (review F10)")
            if member.isdir():
                _claim(seen, rel, "dir")
                _ensure_dirs(dest, rel.split("/"))
            elif member.issym():
                _claim(seen, rel, "link")
                out.links[rel] = member.linkname
                listed.append({"path": rel, "kind": "link", "target": member.linkname})
            elif member.isreg() and member.type in (tarfile.REGTYPE, tarfile.AREGTYPE):
                if member.size > limits.file_bytes:
                    raise TransferError("FILE_TOO_LARGE", f"{rel} is {member.size} bytes; the bound is "
                                        f"{limits.file_bytes}")
                total += member.size
                if total > limits.total_bytes:
                    raise TransferError("TOTAL_TOO_LARGE", f"more than {limits.total_bytes} bytes in total")
                _claim(seen, rel, "file")
                digest = _write_member(tar, member, dest, rel, deadline, limits)
                out.files[rel] = (digest, member.size)
                listed.append({"path": rel, "kind": "file", "sha256": digest, "size": member.size})
            else:
                raise TransferError("ENTRY_TYPE_REFUSED", f"{rel} is a {_type_name(member)}; a bundle carries "
                                    "regular files, directories and links as data only")
    if manifest_bytes is None:
        raise TransferError("TRANSFER_CORRUPT", f"the bundle has no {MANIFEST_NAME}")
    computed = canonical(manifest_of(listed))
    if manifest_bytes != computed:
        raise TransferError("TRANSFER_CORRUPT", "what arrived does not match the bundle's manifest")
    out.sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if expected is not None and out.sha256 != expected:
        raise TransferError("TRANSFER_CORRUPT", f"the bundle's manifest is {out.sha256}, not the {expected} its "
                            "sender recorded")
    return out


def _type_name(member: tarfile.TarInfo) -> str:
    names = {tarfile.LNKTYPE: "hard link", tarfile.CHRTYPE: "character device", tarfile.BLKTYPE: "block device",
             tarfile.FIFOTYPE: "FIFO", tarfile.CONTTYPE: "contiguous file", tarfile.GNUTYPE_SPARSE: "sparse file"}
    return names.get(member.type, f"tar entry of type {member.type!r}")


def _read_member(tar: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    fh = tar.extractfile(member)
    if fh is None:
        raise TransferError("TRANSFER_CORRUPT", f"{member.name} has no content")
    data = fh.read(member.size + 1)
    if len(data) != member.size:
        raise TransferError("TRANSFER_CORRUPT", f"{member.name} is shorter or longer than its header says")
    return data


def _ensure_dirs(dest: Path, parts: list[str]) -> Path:
    here = dest
    for part in parts:
        here = here / part
        try:
            os.mkdir(here)
        except FileExistsError:
            if not here.is_dir() or fixture.is_link(here):
                raise TransferError("PATH_CONFLICT", f"{here.relative_to(dest).as_posix()} exists and is not a "
                                    "directory this receive made") from None
    return here


def _write_member(tar: tarfile.TarFile, member: tarfile.TarInfo, dest: Path, rel: str, deadline: float,
                  limits: Limits) -> str:
    parts = rel.split("/")
    parent = _ensure_dirs(dest, parts[:-1])
    src = tar.extractfile(member)
    if src is None:
        raise TransferError("TRANSFER_CORRUPT", f"{rel} has no content")
    try:
        fd = os.open(parent / parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_BINARY | O_NOFOLLOW, 0o644)
    except FileExistsError:
        raise TransferError("PATH_CONFLICT", f"{rel} already exists in the received tree") from None
    h = hashlib.sha256()
    remaining = member.size
    try:
        while remaining:
            if time.monotonic() >= deadline:
                raise TransferError("RECEIVE_TIMEOUT", f"receiving took over {limits.timeout_s:g} s")
            chunk = src.read(min(CHUNK, remaining))
            if not chunk:
                raise TransferError("TRANSFER_CORRUPT", f"{rel} ends before its declared size")
            h.update(chunk)
            view = memoryview(chunk)
            while view:
                view = view[os.write(fd, view):]
            remaining -= len(chunk)
    finally:
        os.close(fd)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------- transports

@dataclass(frozen=True)
class Host:
    """An arm host as the evaluator knows it: its name and, with a hypervisor, the snapshot it is reset to."""

    name: str
    snapshot_uuid: str | None = None


@dataclass(frozen=True)
class Reply:
    message: dict[str, Any]
    payload: bytes = b""

    @property
    def ok(self) -> bool:
        return bool(self.message["ok"])

    @property
    def result(self) -> dict[str, Any]:
        return self.message["result"]

    @property
    def error(self) -> dict[str, str] | None:
        return self.message["error"]


class Transport:
    """One arm host's calls. Subclasses move bytes (:meth:`exchange`); framing, bounds and validation are here."""

    host: Host
    limits: Limits

    def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
        raise NotImplementedError

    def call(self, verb: str, *, run_id: str | None, args: dict[str, Any] | None = None, payload: bytes = b"",
             timeout_s: float | None = None) -> Reply:
        """One bounded call. Raises :class:`TransferError` for a transport failure or a reply that breaks a rule; a
        reply whose ``ok`` is false is returned for the caller to classify."""
        frame = encode_frame({"kind": "request", "verb": verb, "run_id": run_id, "args": args or {}}, payload)
        max_payload = self.limits.tar_bytes()
        raw = self.exchange(frame, timeout_s=timeout_s or self.limits.timeout_s,
                            max_reply=self.limits.json_bytes + 1 + max_payload)
        message, body = decode_frame(raw, what="reply", limits=self.limits, max_payload=max_payload)
        if message["kind"] == "reply" and not message["ok"] and message["verb"] != verb and message["error"]:
            # the agent refused the request before it could read its verb. Its code goes in the text only: a code
            # the guest chooses never stands for one the evaluator classifies (PR #189 review, N2)
            raise TransferError("REQUEST_REFUSED", f"{message['error']['code']}: {message['error']['message']}")
        if message["kind"] != "reply" or message["verb"] != verb:
            raise TransferError("REPLY_MALFORMED", f"a {verb} call got a {message['kind']} for {message['verb']}")
        return Reply(message, body)


ENV_KEEP = ("PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC", "LANG", "LC_ALL", "TZ")
BOOT = ("import sys; sys.path.insert(0, sys.argv[1]); from aew_eval.armhost import main; "
        "sys.exit(main(sys.argv[2:]))")


def limits_record(limits: Limits) -> dict[str, Any]:
    """The agent's limits as its host record holds them (``--limits``): S17 installs that file root-owned, so the
    sealed bounds reach the agent without the evaluator's request choosing them (PR #189 review, F12)."""
    return {"file_bytes": limits.file_bytes, "total_bytes": limits.total_bytes, "entries": limits.entries,
            "json_bytes": limits.json_bytes, "timeout_s": limits.timeout_s}


def load_limits(path: Path) -> Limits:
    record = json.loads(path.read_text(encoding="utf-8"), parse_constant=_no_constant)
    if not isinstance(record, dict) or set(record) != set(limits_record(DEFAULT_LIMITS)):
        raise ValueError(f"{path} is not a limits record")
    limits = Limits(file_bytes=int(record["file_bytes"]), total_bytes=int(record["total_bytes"]),
                    entries=int(record["entries"]), json_bytes=int(record["json_bytes"]),
                    timeout_s=float(record["timeout_s"]))
    if min(limits.file_bytes, limits.total_bytes, limits.entries, limits.json_bytes) <= 0 or limits.timeout_s <= 0:
        raise ValueError(f"{path}: every limit is positive")
    return limits


STDERR_TAIL = 64 * 1024


class LocalTransport(Transport):
    """The arm-host agent as a separate local process, rooted at ``root`` (the stand-in for S6's SSH transport). Its
    environment is an allow-list: nothing the evaluator holds (the hidden root above all) is inherited.
    ``agent_limits`` is the agent's host record of its bounds (by default the evaluator's ``limits``). ``root`` is the
    agent's work root; its private state root is the sibling ``<root>.state``, outside the work tree."""

    def __init__(self, root: Path, *, host: Host | None = None, limits: Limits = DEFAULT_LIMITS,
                 agent_limits: Limits | None = None, python: str = sys.executable) -> None:
        self.root = root.resolve()
        self.state_root = self.root.with_name(self.root.name + ".state")
        self.host = host or Host("local")
        self.limits = limits
        self.agent_limits = agent_limits or limits
        self.python = python
        self.boot = BOOT
        self.package_parent = str(Path(__file__).resolve().parents[1])

    def _env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
        home, tmp = self.root / "home", self.root / "tmp"
        home.mkdir(parents=True, exist_ok=True)
        tmp.mkdir(parents=True, exist_ok=True)
        for name in ("HOME", "USERPROFILE"):
            env[name] = str(home)
        for name in ("TEMP", "TMP", "TMPDIR"):
            env[name] = str(tmp)
        return env

    def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
        self.root.mkdir(parents=True, exist_ok=True)
        record = self.root.with_name(self.root.name + ".limits.json")  # outside the work tree, as on a host
        record.write_text(json.dumps(limits_record(self.agent_limits)), encoding="utf-8")
        argv = [self.python, "-I", "-B", "-c", self.boot, self.package_parent, "--root", str(self.root),
                "--limits", str(record), "--state", str(self.state_root)]
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=str(self.root), env=self._env(), creationflags=NO_WINDOW)
        out = bytearray()
        err = bytearray()
        over = threading.Event()

        def feed() -> None:
            try:
                assert proc.stdin is not None
                proc.stdin.write(request)
                proc.stdin.close()
            except OSError:
                pass  # the agent stopped reading; its reply (or exit) says why

        def drain(stream: Any, sink: bytearray, cap: int, flag: threading.Event) -> None:
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    return
                if len(sink) + len(chunk) > cap:
                    sink.extend(chunk[:cap - len(sink)])
                    flag.set()
                    proc.kill()
                    return
                sink.extend(chunk)

        def drain_tail(stream: Any, sink: bytearray) -> None:
            """Read stderr to its end, keeping the last :data:`STDERR_TAIL` bytes: a chatty agent never blocks on a
            full pipe (PR #189 review, F14)."""
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    return
                sink.extend(chunk)
                del sink[:max(0, len(sink) - STDERR_TAIL)]

        threads = [threading.Thread(target=feed, daemon=True),
                   threading.Thread(target=drain, args=(proc.stdout, out, max_reply, over), daemon=True),
                   threading.Thread(target=drain_tail, args=(proc.stderr, err), daemon=True)]
        for t in threads:
            t.start()
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise TransferError("TIMEOUT", f"the arm host did not answer within {timeout_s:g} s") from None
        finally:
            for t in threads:
                t.join(timeout=10)
        if over.is_set():
            raise TransferError("REPLY_TOO_LARGE", f"the reply exceeds {max_reply} bytes")
        if proc.returncode != 0:
            raise TransferError("HOST_FAILED", f"the arm-host agent exited {proc.returncode}: "
                                f"{bytes(err[-600:]).decode('utf-8', 'replace')}")
        return bytes(out)


class RecordingTransport(Transport):
    """Every byte that crosses ``inner``, both ways, kept in order (``frames``: ``(direction, verb, bytes)``).
    ``on_call(verb, request_message)`` runs before each request leaves, for tests that check what the evaluator had
    recorded by then."""

    def __init__(self, inner: Transport, on_call: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self.inner = inner
        self.host = inner.host
        self.limits = inner.limits
        self.on_call = on_call
        self.frames: list[tuple[str, str, bytes]] = []

    def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
        message = json.loads(request[:request.index(b"\n")].decode("utf-8"))
        if self.on_call is not None:
            self.on_call(message["verb"], message)
        self.frames.append(("sent", message["verb"], request))
        reply = self.inner.exchange(request, timeout_s=timeout_s, max_reply=max_reply)
        self.frames.append(("received", message["verb"], reply))
        return reply

    def crossed(self) -> bytes:
        """Every byte that crossed, both ways."""
        return b"".join(data for _, _, data in self.frames)
