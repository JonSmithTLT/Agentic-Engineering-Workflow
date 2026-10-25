"""A stand-in capability provider with ripgrep's shape, for the capability register's tests (STG-15, CAP-1): a
`/bin/sh` script of builtins on POSIX, a copy of Windows' own `findstr.exe` on Windows, pinned like ripgrep's
payloads in an archive built here."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from aew.capability import ops, records, store
from aew.engine.steering import OperatorPrincipal

IS_WINDOWS = os.name == "nt"
KEY = records.platform_key()
TEXT = "needle one\nhay\nneedle two needle\n"
FOUND = "needle one\nneedle two needle"
SCRIPT = ('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "fake 1.0"; exit 0; fi\n'
          'while IFS= read -r line; do case "$line" in *needle*) echo "$line";; esac; done < "$2"\n')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _body() -> bytes:
    if IS_WINDOWS:
        return Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "findstr.exe").read_bytes()
    return SCRIPT.encode()


def _health(expect: str = FOUND) -> dict[str, Any]:
    if IS_WINDOWS:  # findstr: the first line of a one-line file is its version line
        return {"version": {"args": ["/c:fake", "version.txt"], "expect": "fake 1.0"},
                "fixture": {"files": {"version.txt": "fake 1.0\n", "fixture.txt": TEXT},
                            "args": ["/c:needle", "fixture.txt"], "expect": expect}}
    return {"version": {"args": ["--version"], "expect": "fake 1.0"},
            "fixture": {"files": {"fixture.txt": TEXT}, "args": ["--search", "fixture.txt"], "expect": expect}}


def _archive(body: bytes, member: str, *, kind: str = "tar.gz") -> bytes:
    out = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(out, "w") as z:
            z.writestr(member, body)
    else:
        with tarfile.open(fileobj=out, mode="w:gz") as t:
            info = tarfile.TarInfo(member)
            info.size, info.mode = len(body), 0o755
            t.addfile(info, io.BytesIO(body))
    return out.getvalue()


MEMBER = "fake-1.0/fake.exe" if IS_WINDOWS else "fake-1.0/fake"
SOURCE = "https://example.invalid/releases/fake-1.0.tar.gz"


def _record(body: bytes, archive: bytes, *, health: dict[str, Any] | None = None, version: str = "1.0",
            platforms: tuple[str, ...] = (KEY,), **fields: Any) -> dict[str, Any]:
    pinned = {"source": SOURCE, "archive_sha256": _sha(archive), "archive_size": len(archive), "member": MEMBER,
              "sha256": _sha(body), "size": len(body)}
    return {"type": "cli", "command": "fake", "capabilities": ["FAKE_SEARCH"], "placement": "sandbox",
            "effect": "read_only", "path": "first", "evidence": "source_text",
            "needs": {"network": False, "credentials": False, "providers": []}, "version": version,
            "payloads": {k: pinned for k in platforms}, "health": health or _health(), **fields}


def make_register(tmp_path, monkeypatch):
    """An empty register of the test's own, AEW shipping the stand-in alone, and no network at all."""
    root = tmp_path / "register"
    monkeypatch.setattr(store, "ROOT_OVERRIDE", root)
    body = _body()
    archive = _archive(body, MEMBER)
    shipped = {"fake": _record(body, archive)}
    monkeypatch.setattr(records, "shipped", lambda: shipped)

    def no_network(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("the test fetched from the network")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    return {"root": root, "body": body, "archive": archive, "shipped": shipped, "tmp": tmp_path}


def _principal() -> OperatorPrincipal:
    return OperatorPrincipal(uid=os.getuid() if hasattr(os, "getuid") else None, method="peer_credentials",
                             endpoint_pid=os.getpid(), endpoint_started_at="2026-10-25T00:00:00Z")


def _bundle(reg: dict[str, Any], data: bytes | None = None, name: str = "fake-1.0.tar.gz") -> Path:
    directory = reg["tmp"] / "bundle"
    directory.mkdir(exist_ok=True)
    (directory / name).write_bytes(reg["archive"] if data is None else data)
    return directory


def _import(reg: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return ops.apply(_principal(), ops.preview(ops.IMPORT, {"path": str(_bundle(reg, **kw))}))


def _plant_host_copy(reg: dict[str, Any], monkeypatch) -> Path:
    directory = reg["tmp"] / "host-bin"
    directory.mkdir()
    exe = directory / store.executable_name("fake")
    exe.write_bytes(reg["body"])
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join([str(directory), os.environ.get("PATH", "")]))
    return exe
