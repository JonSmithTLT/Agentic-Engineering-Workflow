"""The capability register's provider records (STG-15, A-38: CAPR-02, CAPR-04, CAPR-13).

One record shape for every provider, AEW's shipped ones and the operator's (``capability-records`` schema). The
shipped records are this module's text: read-only, changed only by a reviewed AEW release. The operator's records
override a shipped record of the same name (:mod:`.store` holds them, :mod:`.ops` writes them).

The first shipped record is ripgrep, the base bundle's first member (CAPR-R03; the stage's FIRST-BUNDLE.md). Its
version is the one OpenCode 2.0.18 and 2.0.22 download when no ``rg`` is on their PATH (measured in their CLI's own
code, 2026-10-25), so the harness gets the ripgrep it was built against. Its payloads are the release's own archives
(https://github.com/BurntSushi/ripgrep/releases/tag/15.1.0): each archive matched the ``.sha256`` file the release
publishes beside it, and the executable's digest was taken from the archive before anything ran. x86_64 Linux takes
the static musl build, which runs on the Rocky 8 family (glibc 2.28); aarch64 Linux takes the release's GNU build, the
one OpenCode takes.
"""

from __future__ import annotations

import json
import platform
import re
import sys
from functools import cache
from typing import Any

from aew import schemas
from aew.errors import IntegrityError, ValidationFailed
from aew.util import load_yaml, sha256_text

SCHEMA = "aew/capability-records/v1"

SHIPPED_TEXT = """\
schema: aew/capability-records/v1
providers:
  ripgrep:
    description: "ripgrep: exact code and text search; OpenCode's glob and grep tools run it"
    type: cli
    command: rg
    capabilities: [EXACT_CODE_SEARCH, TEXT_SEARCH]
    placement: sandbox
    effect: read_only
    path: first
    evidence: source_text
    license: MIT OR Unlicense
    needs: {network: false, credentials: false, providers: []}
    version: 15.1.0
    payloads:
      linux-x86_64:
        source: https://github.com/BurntSushi/ripgrep/releases/download/15.1.0/ripgrep-15.1.0-x86_64-unknown-linux-musl.tar.gz
        archive_sha256: 1c9297be4a084eea7ecaedf93eb03d058d6faae29bbc57ecdaf5063921491599
        archive_size: 2263077
        member: ripgrep-15.1.0-x86_64-unknown-linux-musl/rg
        sha256: ebeaf56f8a25e102e9419933423738b3a2a613a444fd749d695e15eba53f71f2
        size: 5445512
      linux-aarch64:
        source: https://github.com/BurntSushi/ripgrep/releases/download/15.1.0/ripgrep-15.1.0-aarch64-unknown-linux-gnu.tar.gz
        archive_sha256: 2b661c6ef508e902f388e9098d9c4c5aca72c87b55922d94abdba830b4dc885e
        archive_size: 1869959
        member: ripgrep-15.1.0-aarch64-unknown-linux-gnu/rg
        sha256: 968cabe8efed72fd8fd482cb76b6084fcb695fc5293af7fb62296b02f487fb69
        size: 4543848
      windows-x86_64:
        source: https://github.com/BurntSushi/ripgrep/releases/download/15.1.0/ripgrep-15.1.0-x86_64-pc-windows-msvc.zip
        archive_sha256: 124510b94b6baa3380d051fdf4650eaa80a302c876d611e9dba0b2e18d87493a
        archive_size: 1810687
        member: ripgrep-15.1.0-x86_64-pc-windows-msvc/rg.exe
        sha256: decdd4992f3f1b9a5ef9898f1b40ab16886d579d6516b4efd3d5eaa19364e408
        size: 4266496
    health:
      version: {args: [--version], expect: ripgrep 15.1.0}
      fixture:
        files: {fixture.txt: "needle one\\nhay\\nneedle two needle\\n"}
        args: [--no-config, --count-matches, --fixed-strings, needle, fixture.txt]
        expect: "3"
"""

# sys.platform and platform.machine() -> the payload keys of the schema
_OS = {"linux": "linux", "win32": "windows", "darwin": "darwin"}
_MACHINE = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}


def platform_key(system: str | None = None, machine: str | None = None) -> str:
    """This host's payload key (``linux-x86_64``, ``windows-x86_64``...). A host no record can name gets a key no
    record has, so its every payload reads UNSUPPORTED."""
    s = system or sys.platform
    os_name = _OS.get("linux" if s.startswith("linux") else s, s)
    m = (machine if machine is not None else platform.machine()).lower()
    return f"{os_name}-{_MACHINE.get(m, m or 'unknown')}"


def digest(record: dict[str, Any]) -> str:
    """A record's identity: a changed record, or a new pin, is a new digest, and its capabilities read STALE until
    they are checked again (CAPR-03)."""
    return sha256_text(json.dumps(record, sort_keys=True, separators=(",", ":")))


def validate(doc: Any, *, source: str) -> dict[str, dict[str, Any]]:
    """The records of ``doc``, which must match the schema; raises ``ValidationFailed`` with every violation."""
    schemas.validate("capability-records", doc, source=source)
    problems = [f"{name}: {why}" for name, record in doc["providers"].items() for why in record_problems(record)]
    if problems:
        raise ValidationFailed(f"{source}: the records are refused: {'; '.join(problems)}", violations=problems,
                               reason="record_refused")
    return dict(doc["providers"])


def capability_ids(record: Any) -> list[str]:
    """The well-formed capability IDs a record names, by the schema's own pattern, even where the record as a whole is
    refused: its capabilities then read REFUSED with its cause, and never drop out of the listing (review F11)."""
    item = schemas.schema("capability-records")["$defs"]["provider"]["properties"]["capabilities"]["items"]
    named = record.get("capabilities") if isinstance(record, dict) else None
    return [c for c in named if isinstance(c, str) and len(c) <= item["maxLength"]
            and re.fullmatch(item["pattern"], c)] if isinstance(named, list) else []


def record_problems(record: dict[str, Any]) -> list[str]:
    """What the schema cannot say about a record that matches it, each as a refusal with what to do instead. Host
    placement, network widening and provider dependencies are not built: CAP-1 is sandbox-placed and offline
    (CAPR-R03), and the first two are protected changes (CAPR-13)."""
    out = []
    if record["placement"] == "host":
        out.append("host placement is a protected change (CAPR-13) that AEW does not offer yet; place it in the "
                   "sandbox, where it runs with the agent's own authority")
    if record["needs"]["credentials"] and record["placement"] == "sandbox":
        out.append("a provider that needs a credential cannot be placed in the sandbox, where the agent could read "
                   "it (CAPR-07); it belongs on the host, where it holds the credential itself")
    if record["needs"]["network"]:
        out.append("a provider that needs a network route its context lacks would widen that network, a protected "
                   "change (CAPR-13) that AEW does not offer yet")
    if record["needs"]["providers"]:
        out.append("a provider that needs other providers is not supported yet; give it a self-contained payload")
    for key, payload in record["payloads"].items():
        if ".." in payload["member"].split("/"):
            out.append(f"payload {key}: its member {payload['member']!r} names a parent directory")
    return out


@cache
def shipped() -> dict[str, dict[str, Any]]:
    """AEW's own records. One that fails validation is a defect of this release, never the operator's to fix."""
    try:
        return validate(load_yaml(SHIPPED_TEXT, source="aew.capability.records.SHIPPED_TEXT"),
                        source="AEW's shipped capability records")
    except ValidationFailed as exc:  # pragma: no cover - a test validates the shipped text
        raise IntegrityError(f"AEW's shipped capability records are invalid, a defect of this release: "
                             f"{exc.message}", reason="shipped_records_invalid") from None


def differences(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """The fields that differ between two records, as one line each: what an upgrade reports where the operator's
    override and the new shipped record differ (CAPR-04)."""
    out = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        if key == "payloads":
            changed = sorted(k for k in set(old.get(key) or {}) | set(new.get(key) or {})
                             if (old.get(key) or {}).get(k) != (new.get(key) or {}).get(k))
            out.append(f"payloads: {', '.join(changed)} differ")
        elif isinstance(old.get(key), (str, int, bool)) and isinstance(new.get(key), (str, int, bool)):
            out.append(f"{key}: {old.get(key)} -> {new.get(key)}")
        else:
            out.append(f"{key} differs")
    return out
