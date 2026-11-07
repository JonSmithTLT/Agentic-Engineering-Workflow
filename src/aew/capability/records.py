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
one OpenCode takes. It is needed: OpenCode's glob and grep tools run it, so its search fails without it.

The rest of the first bundle (FIRST-BUNDLE.md): fd, jq, yq (mikefarah's, in Go), ast-grep and Universal Ctags. Each is
optional, since the harness runs none of them, and is offered under its own name, last on a contained context's PATH
(``path: own_name``), so a project's own tools keep theirs (CAPR-04). yq and Universal Ctags have other
implementations under the plain name (a Python ``yq``; Rocky 8's Exuberant ``ctags``), so AEW's are ``yq-go`` and
``uctags``; ast-grep's is ``ast-grep``, never ``sg``, which is shadow-utils' on Rocky 8. Each payload is a release's
own download, which matched the digest its host publishes for it, and each executable's digest was taken from the
download before anything ran. For Linux x86_64 each runs on the Rocky 8 family (glibc 2.28), read from the executable:
fd, jq, yq and Universal Ctags are static; ast-grep's release build needs glibc 2.34, so it is taken from the
project's own manylinux_2_28 wheel, which needs 2.28. jq is released as a bare executable. Universal Ctags publishes
no release build for Linux: both its payloads are the project's own nightly builds of commit 8249436 (the Linux one in
ctags-nightly-build, the Windows one in ctags-win32), whose source, under GPL-2.0, is that commit's
(https://github.com/universal-ctags/ctags/tree/82494361bb3e7d4f7cf1d2bdc0d0e9001c926e45). Its version check asks
only that it is Universal Ctags: the build prints 6.2.0, which is not the commit, and the payload's pin is.
"""

from __future__ import annotations

import json
import platform
import re
import sys
from functools import cache
from typing import Any

from aew import schemas
from aew.capability import payload as P
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
    needed: true
    degrades: "OpenCode's search: its glob and grep tools fail without it"
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
  fd:
    description: "fd: find files by name or pattern"
    type: cli
    command: fd
    capabilities: [FILE_FIND]
    placement: sandbox
    effect: read_only
    path: own_name
    evidence: source_text
    license: MIT OR Apache-2.0
    needs: {network: false, credentials: false, providers: []}
    version: 10.5.0
    payloads:
      linux-x86_64:
        source: https://github.com/sharkdp/fd/releases/download/v10.5.0/fd-v10.5.0-x86_64-unknown-linux-musl.tar.gz
        archive_sha256: 761c72dc8e120d85b22292063be8a796e2eeb20eb3e4f38b8fa2343ccf3514a7
        archive_size: 1573549
        member: fd-v10.5.0-x86_64-unknown-linux-musl/fd
        sha256: e79642a479d2816c887047476bbe6ad229465f30de031033574dee2a095e0037
        size: 3708016
      windows-x86_64:
        source: https://github.com/sharkdp/fd/releases/download/v10.5.0/fd-v10.5.0-x86_64-pc-windows-msvc.zip
        archive_sha256: a227701b8551c35a9931d9f6da75503cf86d88e182d71fb849a70864c5d57cd7
        archive_size: 1535063
        member: fd-v10.5.0-x86_64-pc-windows-msvc/fd.exe
        sha256: d67d27a8e375ed7e9bca2b506a9dd5082bc24547aeba908b863f6f8b8ab0c3b9
        size: 4104192
    health:
      version: {args: [--version], expect: fd 10.5.0}
      fixture:
        files: {needle.txt: "x\\n", hay.txt: "y\\n"}
        args: [--no-ignore, --color, never, --glob, "needle*"]
        expect: needle.txt
  jq:
    description: "jq: query and transform JSON"
    type: cli
    command: jq
    capabilities: [JSON_QUERY]
    placement: sandbox
    effect: read_only
    path: own_name
    evidence: source_text
    license: MIT
    needs: {network: false, credentials: false, providers: []}
    version: 1.8.2
    payloads:
      linux-x86_64:
        source: https://github.com/jqlang/jq/releases/download/jq-1.8.2/jq-linux-amd64
        archive_sha256: b1c22172dd303f3be49e935aa56aa48a8b7a46e0bc838b4997d3bb451495870f
        archive_size: 2267912
        sha256: b1c22172dd303f3be49e935aa56aa48a8b7a46e0bc838b4997d3bb451495870f
        size: 2267912
      windows-x86_64:
        source: https://github.com/jqlang/jq/releases/download/jq-1.8.2/jq-windows-amd64.exe
        archive_sha256: a6fc67fedaf9128a3309a1e2ebb8b986aeccf70122ee46d2cb4849e423f0c627
        archive_size: 1035264
        sha256: a6fc67fedaf9128a3309a1e2ebb8b986aeccf70122ee46d2cb4849e423f0c627
        size: 1035264
    health:
      version: {args: [--version], expect: jq-1.8.2}
      fixture:
        files: {fixture.json: "{\\"a\\": [1, 2, 3]}\\n"}
        args: [-c, ".a | add", fixture.json]
        expect: "6"
  yq:
    description: "yq (mikefarah's, in Go): query and edit YAML; named yq-go, so a project's own yq keeps its name"
    type: cli
    command: yq-go
    capabilities: [YAML_QUERY]
    placement: sandbox
    effect: read_only
    path: own_name
    evidence: source_text
    license: MIT
    needs: {network: false, credentials: false, providers: []}
    version: 4.54.1
    payloads:
      linux-x86_64:
        source: https://github.com/mikefarah/yq/releases/download/v4.54.1/yq_linux_amd64.tar.gz
        archive_sha256: e68a456f90c577af3fe4960184b3a3cf5c461e0348407c10f107da3a5fec8972
        archive_size: 5726505
        member: ./yq_linux_amd64
        sha256: 8e34fc298390875de416e6a4afcb8cabeceb25d9aa8506c1a2f9353cf702ea5f
        size: 14168224
      windows-x86_64:
        source: https://github.com/mikefarah/yq/releases/download/v4.54.1/yq_windows_amd64.zip
        archive_sha256: c2fb1234e58a3b80e358a0a8baeaf7ec51bfa698bbe40e2fcab0ed37d590c107
        archive_size: 5829372
        member: yq_windows_amd64.exe
        sha256: b645f47ebb3a0d2fbab52998550bbd0a1706f23b5ca5f5b48e638c580bb70928
        size: 14615040
    health:
      version: {args: [--version], expect: "yq (https://github.com/mikefarah/yq/) version v4.54.1"}
      fixture:
        files: {fixture.yaml: "a:\\n  b: 3\\n"}
        args: [eval, .a.b, fixture.yaml]
        expect: "3"
  ast-grep:
    description: "ast-grep: structural code search by syntax-tree pattern"
    type: cli
    command: ast-grep
    capabilities: [STRUCTURAL_CODE_SEARCH]
    placement: sandbox
    effect: read_only
    path: own_name
    evidence: source_text
    license: MIT
    needs: {network: false, credentials: false, providers: []}
    version: 0.51.0
    payloads:
      linux-x86_64:
        source: https://files.pythonhosted.org/packages/b5/58/5f644df6460b0788871f9354b5a61797d0ac3adbeed2786fc872d79ced30/ast_grep_cli-0.51.0-py3-none-manylinux_2_28_x86_64.whl
        archive_sha256: 17007574681fe872473850780304b3df57ca98ac575d88957972fea8c3810c26
        archive_size: 8753377
        member: ast_grep_cli-0.51.0.data/scripts/ast-grep
        sha256: bd9e202969472ab6bd1e3fa0b498ba5fc87deef0810666ee5311940befbd1e24
        size: 52562384
      windows-x86_64:
        source: https://github.com/ast-grep/ast-grep/releases/download/0.51.0/app-x86_64-pc-windows-msvc.zip
        archive_sha256: 1a5b7824c5925ac34257f806488e54860817cefd855fd308d13df7550d068908
        archive_size: 16249102
        member: ast-grep.exe
        sha256: 8ac5d5e90484e727c6ca53114c77c93b26e63a42bf9db07efda5008a5a4165a3
        size: 54041600
    health:
      version: {args: [--version], expect: ast-grep 0.51.0}
      fixture:
        files: {fixture.py: "def f(x):\\n    return x + 1\\n"}
        args: [run, --pattern, "$A + 1", --lang, python, --files-with-matches, fixture.py]
        expect: fixture.py
  universal-ctags:
    description: "Universal Ctags: a symbol outline of source files; named uctags, so another ctags keeps its name"
    type: cli
    command: uctags
    capabilities: [SYMBOL_OUTLINE]
    placement: sandbox
    effect: read_only
    path: own_name
    evidence: source_text
    license: GPL-2.0
    needs: {network: false, credentials: false, providers: []}
    version: 6.2.0+g8249436
    payloads:
      linux-x86_64:
        source: https://github.com/universal-ctags/ctags-nightly-build/releases/download/2026.10.08%2B82494361bb3e7d4f7cf1d2bdc0d0e9001c926e45/uctags-2026.10.08-linux-x86_64.release.tar.gz
        archive_sha256: 0309295a80caf71d4632badf1e94f696903598c92cc52d1c8fbbc18d03ca38d5
        archive_size: 3603052
        member: uctags-2026.10.08-linux-x86_64.release/bin/ctags
        sha256: b4c060955aba2af0c2545c3915b87406b9c238cbe7d930cf9a1f1bc5901131cf
        size: 3930048
      windows-x86_64:
        source: https://github.com/universal-ctags/ctags-win32/releases/download/2026-10-09/p6.2.20260927.0-3-g8249436/ctags-2026-10-09_p6.2.20260927.0-3-g8249436-x64.zip
        archive_sha256: 6a46c61e1185abd53b7c28c91b31447f38cbaf56078a79b3473b223fa57af55d
        archive_size: 3160613
        member: ctags.exe
        sha256: d771472342929bda11a6011da74de7f292384db64aa53cec15f57af9a04a8af6
        size: 4990995
    health:
      version: {args: [--version], expect: Universal Ctags}
      fixture:
        files: {fixture.c: "int answer(void) { return 42; }\\n"}
        args: [--options=NONE, -o, "-", --fields=, --extras=, --excmd=number, fixture.c]
        expect: "answer\\tfixture.c\\t1"
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
    with_user = _sources_with_a_user(doc)
    if with_user:  # before the schema, whose message would repeat the source and its password
        problems = [f"{name}: payload {key}: its source carries a user or password, which the register would keep "
                    f"where every sandbox reads it; give a source without one" for name, key in with_user]
        raise ValidationFailed(f"{source}: the records are refused: {'; '.join(problems)}", violations=problems,
                               reason="record_refused")
    schemas.validate("capability-records", doc, source=source)
    problems = [f"{name}: {why}" for name, record in doc["providers"].items() for why in record_problems(record)]
    if problems:
        raise ValidationFailed(f"{source}: the records are refused: {'; '.join(problems)}", violations=problems,
                               reason="record_refused")
    return dict(doc["providers"])


def _sources_with_a_user(doc: Any) -> list[tuple[str, str]]:
    """Each (provider, platform key) whose payload's source has a user or password in it (quick check of #330, m-b).
    The schema's pattern refuses one too; this says so in AEW's words, never the source's own."""
    providers = doc.get("providers") if isinstance(doc, dict) else None
    out = []
    for name, record in (providers or {}).items() if isinstance(providers, dict) else ():
        payloads = record.get("payloads") if isinstance(record, dict) else None
        for key, payload in (payloads or {}).items() if isinstance(payloads, dict) else ():
            got = payload.get("source") if isinstance(payload, dict) else None
            if isinstance(got, str) and "@" in got.partition("://")[2].partition("/")[0]:
                out.append((str(name), str(key)))
    return out


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
        out += [f"payload {key}: {why}" for why in _payload_problems(payload)]
    if record.get("needed") and not record.get("degrades"):
        out.append("a needed provider says what degrades without it (`degrades`), which the operator's prompt shows "
                   "beside it; add it, or mark the provider optional (`needed: false`)")
    return out


def _payload_problems(payload: dict[str, Any]) -> list[str]:
    """A payload's member, by what its source downloads (``payload.kind``): an archive names the one member it takes,
    and a bare executable names none, its download being the executable, so its two pins are one."""
    member = payload.get("member")
    if P.kind(payload["source"]) != P.EXECUTABLE:
        if member is None:
            return ["its source is an archive, so it names the executable in it (`member`)"]
        return [f"its member {member!r} names a parent directory"] if ".." in member.split("/") else []
    if member is not None:
        return ["its source is a bare executable (not a .tar.gz, .zip or .whl), so it has no `member`; name the "
                "archive, or leave `member` out"]
    if (payload["archive_sha256"], payload["archive_size"]) != (payload["sha256"], payload["size"]):
        return ["its source is a bare executable, whose download is the executable itself, so its download's pin "
                "(`archive_sha256`, `archive_size`) and the executable's (`sha256`, `size`) are the same"]
    return []


def needed(record: dict[str, Any]) -> bool:
    """Whether the harness relies on the provider (the record's ``needed``, default false): the operator's prompt lists
    a needed tool in full, and Enter takes it (the designer's ruling, STG-15, 2026-11-05). Stated on the record, never
    inferred, and an operator's record of the same name overrides it (CAPR-04's two layers)."""
    return bool(record.get("needed"))


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
