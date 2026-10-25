"""The capability register's core (STG-15, CAP-1; A-38: CAPR-02, CAPR-03, CAPR-04, CAPR-12, CAPR-13).

Every status has its planted controls: the right case, the wrong case and the missing one. Gate rows shown here:
CAPR-Q01 (a payload with one byte changed reads REFUSED with the reason, at import and at the next check), Q04 (status
follows the health check: broken -> UNAVAILABLE with its cause, re-pinned -> STALE until checked, never checked ->
NOT_ESTABLISHED) and Q05 (offline, a bundle import makes the capability FUNCTIONAL_ONLY). The provider is a stand-in
with ripgrep's shape: a `/bin/sh` script of builtins on POSIX, a copy of Windows' own `findstr.exe` on Windows, each
pinned like ripgrep's payloads, in an archive built here. Nothing is fetched from the network.
"""

from __future__ import annotations

import copy
import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any

import pytest
from capability_stand_in import (
    KEY,
    MEMBER,
    SOURCE,
    _archive,
    _bundle,
    _health,
    _import,
    _plant_host_copy,
    _principal,
    _record,
    _sha,
    make_register,
)
from conftest import IS_WINDOWS

from aew import errors
from aew.capability import ops, records, status, store
from aew.capability import payload as P


@pytest.fixture
def reg(tmp_path, monkeypatch):
    return make_register(tmp_path, monkeypatch)


def _cap(cap: str = "FAKE_SEARCH") -> dict[str, Any]:
    return next(c for c in ops.listing()["capabilities"] if c["id"] == cap)


# ---------------------------------------------------------------------------------------------- the records


def test_the_shipped_records_validate_and_name_capabilities_in_d01_form():
    shipped = records.validate(records.load_yaml(records.SHIPPED_TEXT, source="shipped"), source="shipped")
    rg = shipped["ripgrep"]
    assert rg["capabilities"] == ["EXACT_CODE_SEARCH", "TEXT_SEARCH"] and rg["command"] == "rg"
    assert rg["placement"] == "sandbox" and rg["path"] == "first" and rg["needs"] == {
        "network": False, "credentials": False, "providers": []}
    assert set(rg["payloads"]) == {"linux-x86_64", "linux-aarch64", "windows-x86_64"}
    for key, pinned in rg["payloads"].items():  # every payload is the release's own archive of this version
        assert pinned["source"].startswith(f"https://github.com/BurntSushi/ripgrep/releases/download/{rg['version']}/")
        assert pinned["member"].endswith("/rg.exe" if key.startswith("windows") else "/rg")
    assert rg["health"]["version"]["expect"] == f"ripgrep {rg['version']}"


@pytest.mark.parametrize("change, refused", [
    (lambda r: r.update(placement="host"), "host placement"),
    (lambda r: r["needs"].update(credentials=True), "place"),  # CAPR-Q11's words: it belongs on the host
    (lambda r: r["needs"].update(network=True), "widen"),
    (lambda r: r["needs"].update(providers=["other"]), "other providers"),
    (lambda r: r["payloads"][KEY].update(member="../escape"), "parent directory"),
    (lambda r: r.update(capabilities=["exact_code_search"]), "does not match"),  # not D-01's form
    (lambda r: r.update(extra=1), "does not match"),
])
def test_a_record_that_fails_validation_is_refused_with_its_reason(reg, change, refused):
    record = copy.deepcopy(reg["shipped"]["fake"])
    change(record)
    with pytest.raises(errors.ValidationFailed) as exc:
        records.validate({"schema": records.SCHEMA, "providers": {"fake": record}}, source="test")
    assert refused in json.dumps(exc.value.to_dict()), exc.value.to_dict()


def test_platform_keys():
    assert records.platform_key("linux", "x86_64") == "linux-x86_64"
    assert records.platform_key("linux", "aarch64") == "linux-aarch64"
    assert records.platform_key("win32", "AMD64") == "windows-x86_64"
    assert records.platform_key("sunos5", "sparc") == "sunos5-sparc"  # no record names it: UNSUPPORTED


# ---------------------------------------------------------------------------------------------- the statuses


def test_a_payload_never_fetched_reads_unavailable_with_its_cause_and_fix(reg):
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and cap["assessment_status"] == status.NOT_ESTABLISHED
    assert "never fetched or imported" in cap["cause"]
    assert "aew capability check" in cap["fix"] and "aew capability import" in cap["fix"]


def test_q05_an_offline_bundle_import_makes_the_capability_functional_only(reg):
    """CAPR-Q05 (and CAPR-X01's status half): with no network, the import checks the pin, installs the executable
    and runs its health check. The register's state and change log say so."""
    out = _import(reg)
    assert [i["provider"] for i in out["imported"]] == ["fake"] and "passed" in out["imported"][0]["check"]
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["pinned"] and cap["cause"] is None
    assert cap["version"] == "1.0" and cap["checked_at"]
    installed = Path(cap["path"])
    assert installed.read_bytes() == reg["body"] and installed.parent.parent.parent.name == store.PAYLOADS
    assert sorted(p.name for p in installed.parent.iterdir()) == [installed.name]  # a directory of its own
    log = [json.loads(line) for line in (reg["root"] / store.CHANGES).read_text(encoding="utf-8").splitlines()]
    assert log[-1]["command"] == "import" and log[-1]["principal"]["guarantee"] == "dev"
    assert log[-1]["authorized_by"] == "operator-endpoint" and "challenge_code" not in json.dumps(log)


def test_a_renamed_archive_still_imports_by_its_digest(reg):
    _import(reg, name="renamed.tar.gz")
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_q01_an_archive_with_one_byte_changed_is_refused_at_import(reg):
    """...matched by the archive's own digest, so the operator is shown the refusal before approving anything."""
    tampered = bytearray(reg["archive"])
    tampered[len(tampered) // 2] ^= 1
    bundle = _bundle(reg, data=bytes(tampered))
    change = ops.preview(ops.IMPORT, {"path": str(bundle)})
    assert len(change.lines) == 2 and change.lines[1].startswith(f"  REFUSE {bundle / 'fake-1.0.tar.gz'} for fake")
    assert "does not match its pin" in change.lines[1]
    out = ops.apply(_principal(), change)
    assert out["imported"] == [] and "does not match its pin" in out["refused"][0]["reason"]
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "does not match its pin" in cap["cause"]
    assert not (reg["root"] / store.PAYLOADS).exists() or not any((reg["root"] / store.PAYLOADS).rglob("fake*"))


def test_q01_an_installed_payload_with_one_byte_changed_is_refused_at_the_next_check(reg, monkeypatch):
    """...and removed, so a later check fetches it again: online, the pinned archive comes back FUNCTIONAL_ONLY."""
    _import(reg)
    installed = Path(_cap()["path"])
    os.chmod(installed, 0o700)
    data = bytearray(installed.read_bytes())
    data[-1] ^= 1
    installed.write_bytes(bytes(data))
    assert _cap()["observed_status"] == status.REFUSED  # every read checks the pin, not only a check
    said = ops.check("fake")["checked"]["fake"]
    assert any("refused its installed payload" in s for s in said), said
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "does not match its pin" in cap["cause"]
    assert not installed.exists()
    monkeypatch.setattr(P, "fetch", lambda pinned: reg["archive"])
    ops.check("fake")
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_an_online_check_fetches_checks_and_never_fetches_offline(reg, monkeypatch):
    fetched: list[str] = []

    def fetch(pinned: dict[str, Any]) -> bytes:
        fetched.append(pinned["source"])
        return reg["archive"]

    monkeypatch.setattr(P, "fetch", fetch)
    ops.check(offline=True)
    assert fetched == [] and _cap()["observed_status"] == status.UNAVAILABLE
    ops.check()
    assert fetched == [SOURCE] and _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    ops.check()
    assert fetched == [SOURCE]  # a payload on this host is checked, never fetched again


def test_a_failed_fetch_reads_unavailable_with_its_cause(reg, monkeypatch):
    def down(pinned: dict[str, Any]) -> bytes:
        raise errors.Unavailable("the pinned payload could not be fetched: no route", reason="fetch_failed")

    monkeypatch.setattr(P, "fetch", down)
    ops.check()
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and "the fetch failed" in cap["cause"]
    assert "no route" in cap["cause"]


def test_q04_a_never_checked_payload_reads_not_established(reg):
    pinned = reg["shipped"]["fake"]["payloads"][KEY]
    P.install("fake", "fake", pinned, reg["body"])  # on the host, never checked
    assert _cap()["observed_status"] == status.NOT_ESTABLISHED
    ops.check(offline=True)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_q04_a_broken_provider_reads_unavailable_with_its_cause(reg, monkeypatch):
    broken = _record(reg["body"], reg["archive"], health=_health(expect="needle three"))
    monkeypatch.setattr(records, "shipped", lambda: {"fake": broken})
    _import(reg)
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and "its check failed" in cap["cause"]
    assert "fixture query printed" in cap["cause"] and "needle three" in cap["cause"]


def test_q04_a_re_pinned_record_reads_stale_until_it_is_checked(reg, monkeypatch):
    """A new pin: the payload checked under the old one is no proof of the new one, which is not here yet."""
    _import(reg)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    body = reg["body"] + (b"\n" if not IS_WINDOWS else b"\0")  # a different executable: a new pin
    archive = _archive(body, MEMBER)
    repinned = _record(body, archive)
    monkeypatch.setattr(records, "shipped", lambda: {"fake": repinned})
    cap = _cap()
    assert cap["observed_status"] == status.STALE and "its pin changed since it was checked" in cap["cause"]
    assert "aew capability check" in cap["fix"]
    monkeypatch.setattr(P, "fetch", lambda pinned: archive)
    ops.check("fake")
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and Path(cap["path"]).read_bytes() == body


def test_q04_a_changed_record_reads_stale_until_it_is_checked(reg, monkeypatch):
    _import(reg)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    changed = copy.deepcopy(reg["shipped"]["fake"])
    changed["description"] = "a changed record, the same pin"
    monkeypatch.setattr(records, "shipped", lambda: {"fake": changed})
    cap = _cap()
    assert cap["observed_status"] == status.STALE and "record or its pin changed" in cap["cause"]
    ops.check(offline=True)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


@pytest.mark.parametrize("fact", ["kernel", "libc", "harness"])
def test_q04_a_host_change_reads_stale_naming_it(reg, monkeypatch, fact):
    then = {"kernel": "k1", "libc": "glibc 2.28", "harness": "/opt/opencode (1 bytes, modified 1)"}
    monkeypatch.setattr(status, "host_facts", lambda: dict(then))
    _import(reg)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    monkeypatch.setattr(status, "host_facts", lambda: {**then, fact: "changed"})
    cap = _cap()
    assert cap["observed_status"] == status.STALE and f"the {fact} changed" in cap["cause"]


def test_no_payload_for_the_platform_reads_unsupported(reg, monkeypatch):
    other = _record(reg["body"], reg["archive"], platforms=("sunos5-sparc",))
    monkeypatch.setattr(records, "shipped", lambda: {"fake": other})
    cap = _cap()
    assert cap["observed_status"] == status.UNSUPPORTED and KEY in cap["cause"]


def test_an_invalid_operator_record_is_refused_never_served(reg):
    _import(reg)
    state = store.read()
    bad = copy.deepcopy(reg["shipped"]["fake"])
    bad["placement"] = "host"
    state["operator_records"]["fake"] = {"record": bad, "base_digest": records.digest(reg["shipped"]["fake"])}
    with store.locked() as root:
        store.write(state, root)
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "host placement" in cap["cause"]


def test_an_unreadable_register_refuses_every_capability_with_its_cause(reg):
    reg["root"].mkdir(parents=True)
    (reg["root"] / store.REGISTER).write_text("{not json", encoding="utf-8")
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "not JSON" in cap["cause"]


# ---------------------------------------------------------------------------------------------- host copies


def test_a_host_copy_serves_named_unpinned_beside_the_cause_for_aews_copy(reg, monkeypatch):
    """CAPR-04: AEW's copy absent, the host's serves on its own: NOT_ESTABLISHED until checked, then FUNCTIONAL_ONLY
    with the limitation naming it unpinned, beside AEW's copy's cause."""
    exe = _plant_host_copy(reg, monkeypatch)
    cap = _cap()
    assert cap["observed_status"] == status.NOT_ESTABLISHED and cap["copy"] == status.HOST_COPY
    assert cap["path"] == str(exe.resolve()) and status.UNPINNED in cap["limitations"]
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.HOST_COPY
    assert not cap["pinned"] and cap["version"] is None and status.UNPINNED in cap["limitations"]
    assert cap["cause"].startswith("AEW's copy: its pinned payload is not on this host")
    exe.write_bytes(reg["body"] + b"\n")  # the host's copy changed under its check
    assert _cap()["observed_status"] == status.STALE


def test_a_host_copy_of_another_version_serves_and_its_version_is_named(reg, monkeypatch):
    """A host copy is not AEW's pin, so its check asks that it is the provider, not that it is the pinned version
    (measured on the Rocky 8 VM: its /usr/bin/rg is ripgrep 14.1.1, AEW pins 15.1.0)."""
    newer = _record(reg["body"], reg["archive"], version="2.0", health={
        **_health(), "version": {**_health()["version"], "expect": "fake 2.0"}})
    monkeypatch.setattr(records, "shipped", lambda: {"fake": newer})
    _plant_host_copy(reg, monkeypatch)
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.HOST_COPY
    assert "it reports fake 1.0" in cap["limitations"] and status.UNPINNED in cap["limitations"]


def test_a_refused_aew_copy_never_serves_silently_and_a_host_copy_is_named(reg, monkeypatch):
    tampered = bytearray(reg["archive"])
    tampered[10] ^= 1
    _import(reg, data=bytes(tampered))
    _plant_host_copy(reg, monkeypatch)
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.HOST_COPY
    assert "AEW's copy: its payload was refused" in cap["cause"] and status.UNPINNED in cap["limitations"]


def test_with_host_copies_off_a_host_copy_never_serves(reg, monkeypatch):
    exe = _plant_host_copy(reg, monkeypatch)
    ops.apply(_principal(), ops.preview(ops.HOST_COPIES, {"on": False}))
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and cap["copy"] == status.AEW_COPY
    assert str(exe.resolve()) in cap["cause"] and "host copies off" in cap["cause"]
    ops.apply(_principal(), ops.preview(ops.HOST_COPIES, {"on": True}))
    ops.check(offline=True)
    assert _cap()["copy"] == status.HOST_COPY


def test_with_no_copy_at_all_the_capability_is_unavailable_with_its_cause(reg):
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and cap["copy"] == status.AEW_COPY
    assert cap["limitations"] == []


# ---------------------------------------------------------------------------------------------- operator records


def _add(reg: dict[str, Any], record: dict[str, Any], **args: Any) -> dict[str, Any]:
    text = json.dumps({"schema": records.SCHEMA, "providers": {"fake": record}})  # JSON is YAML
    return ops.apply(_principal(), ops.preview(ops.ADD, {"text": text, "source": "test", **args}))


def test_an_operator_override_is_kept_across_an_upgrade_and_reports_the_difference(reg, monkeypatch):
    override = _record(reg["body"], reg["archive"], description="the operator's own")
    out = _add(reg, override, bundle=str(_bundle(reg)))
    assert out["added"] == ["fake"]
    view = ops.listing()
    assert view["overrides"] == [] and _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    assert next(p for p in view["providers"] if p["name"] == "fake")["layer"] == "operator"
    upgraded = copy.deepcopy(reg["shipped"]["fake"])
    upgraded["version"] = "2.0"
    monkeypatch.setattr(records, "shipped", lambda: {"fake": upgraded})
    view = ops.listing()
    assert view["overrides"] == [{"provider": "fake", "differences": ["version: 1.0 -> 2.0"]}]
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY and _cap()["version"] == "1.0"  # the override serves
    assert any(n == "capability-records" and s == "WARN" and "version: 1.0 -> 2.0" in d
               for n, s, d in ops.doctor_checks())


def test_an_add_that_fails_validation_changes_nothing(reg):
    _import(reg)
    before = (reg["root"] / store.REGISTER).read_bytes()
    with pytest.raises(errors.ValidationFailed, match="nothing changed"):
        _add(reg, {**_record(reg["body"], reg["archive"]), "placement": "host"})
    broken = _record(reg["body"], reg["archive"], health=_health(expect="none"), description="breaks")
    with pytest.raises(errors.ValidationFailed, match="health check failed"):
        _add(reg, broken, bundle=str(_bundle(reg)))
    assert (reg["root"] / store.REGISTER).read_bytes() == before


def test_an_add_whose_payload_is_new_and_fails_its_check_leaves_no_payload(reg):
    body = reg["body"] + b"\n" if not IS_WINDOWS else reg["body"]
    archive = _archive(body, MEMBER)
    broken = _record(body, archive, health=_health(expect="none"))
    with pytest.raises(errors.ValidationFailed):
        _add(reg, broken, bundle=str(_bundle(reg, data=archive)))
    assert not P.path_of("fake", "fake", broken["payloads"][KEY]).exists()


def test_a_sandbox_record_that_needs_a_credential_is_refused_saying_place_it_on_the_host(reg):
    """CAPR-Q11 and CAPR-X09."""
    record = _record(reg["body"], reg["archive"])
    record["needs"]["credentials"] = True
    with pytest.raises(errors.ValidationFailed) as exc:
        _add(reg, record)
    assert "on the host, where it holds the credential itself" in json.dumps(exc.value.to_dict())


def test_remove_takes_only_operator_records_and_the_shipped_record_serves_again(reg):
    with pytest.raises(errors.NotFound, match="reviewed AEW release"):
        ops.preview(ops.REMOVE, {"name": "fake"})
    _add(reg, _record(reg["body"], reg["archive"], description="mine"), bundle=str(_bundle(reg)))
    change = ops.preview(ops.REMOVE, {"name": "fake"})
    assert "AEW's shipped record fake serves again" in change.lines[0]
    ops.apply(_principal(), change)
    provider = next(p for p in ops.listing()["providers"] if p["name"] == "fake")
    assert provider["layer"] == "shipped"


def test_apply_is_refused_without_the_endpoints_principal(reg):
    change = ops.preview(ops.HOST_COPIES, {"on": False})
    for forged in (None, {"uid": 0, "method": "peer_credentials"}, "operator"):
        with pytest.raises(errors.PermissionDenied) as exc:
            ops.apply(forged, change)
        assert exc.value.details["reason"] == "operator_principal_required"
    assert store.read()["host_copies"] is True


def test_apply_refuses_an_import_whose_record_changed_since_the_preview(reg, monkeypatch):
    change = ops.preview(ops.IMPORT, {"path": str(_bundle(reg))})
    moved = _record(reg["body"] + b"x", _archive(reg["body"] + b"x", MEMBER))
    monkeypatch.setattr(records, "shipped", lambda: {"fake": moved})
    out = ops.apply(_principal(), change)
    assert out["imported"] == [] and "changed since the preview" in out["skipped"][0]["reason"]


# ---------------------------------------------------------------------------------------------- payloads


def test_a_zip_payload_is_read_like_a_tarball(reg, monkeypatch):
    archive = _archive(reg["body"], MEMBER, kind="zip")
    record = _record(reg["body"], archive)
    record["payloads"][KEY]["source"] = "https://example.invalid/releases/fake-1.0.zip"
    monkeypatch.setattr(records, "shipped", lambda: {"fake": record})
    _import(reg, data=archive, name="fake-1.0.zip")
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_an_archive_without_its_member_as_a_regular_file_is_refused(reg):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as t:
        link = tarfile.TarInfo(MEMBER)
        link.type, link.linkname = tarfile.SYMTYPE, "/bin/sh"
        t.addfile(link)
    archive = out.getvalue()
    pinned = {**reg["shipped"]["fake"]["payloads"][KEY], "archive_sha256": _sha(archive), "archive_size": len(archive)}
    with pytest.raises(P.PinMismatch) as exc:
        P.member(archive, pinned)
    assert exc.value.details["reason"] == "member_missing"


def test_a_fetch_reads_no_more_than_the_pinned_size_and_checks_the_pin(monkeypatch, reg):
    pinned = reg["shipped"]["fake"]["payloads"][KEY]

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: Any) -> None:
            self.close()

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response(reg["archive"] + b"more"))
    with pytest.raises(P.PinMismatch) as exc:
        P.fetch(pinned)
    assert exc.value.details["reason"] == "archive_size"
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response(b"x" * len(reg["archive"])))
    with pytest.raises(P.PinMismatch) as exc:
        P.fetch(pinned)
    assert exc.value.details["reason"] == "archive_pin"
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response(reg["archive"]))
    assert P.fetch(pinned) == reg["archive"]

    def unreachable(url: str, timeout: float) -> Any:
        raise OSError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    with pytest.raises(errors.Unavailable) as down:
        P.fetch(pinned)
    assert down.value.details["reason"] == "fetch_failed"


# ---------------------------------------------------------------------------------------------- doctor


def test_doctor_names_each_capability_pass_when_usable_and_warn_never_fail_otherwise(reg):
    """CAPR-12: no provider is required, so a missing one is a WARN with its cause and fix, never a FAIL."""
    from aew import doctor

    rows = {c["check"]: c for c in doctor.environment_checks() if c["check"].startswith("capability:")}
    assert rows["capability:FAKE_SEARCH"]["status"] == "WARN"
    assert rows["capability:FAKE_SEARCH"]["detail"].startswith("UNAVAILABLE:")
    assert "fix: `aew capability check`" in rows["capability:FAKE_SEARCH"]["detail"]
    _import(reg)
    rows = {c["check"]: c for c in doctor.environment_checks() if c["check"].startswith("capability:")}
    assert rows["capability:FAKE_SEARCH"]["status"] == "PASS"
    assert rows["capability:FAKE_SEARCH"]["detail"].startswith("FUNCTIONAL_ONLY: served by fake 1.0, AEW's pinned")


def test_doctor_names_the_harness_a_host_prerequisite(tmp_path, monkeypatch):
    """CAPR-12 (the designer's CAP-1 rule 9): doctor names the harness; without one AEW runs and launches refuse."""
    from aew import doctor
    from aew.harness.opencode.adapter import BIN_ENV

    monkeypatch.setenv(BIN_ENV, str(tmp_path / "no-such-opencode"))
    row = next(c for c in doctor.environment_checks() if c["check"] == "harness")
    assert row["status"] == "WARN" and "harness launches are refused" in row["detail"] and BIN_ENV in row["detail"]
    present = tmp_path / "opencode-cli"
    present.write_bytes(b"")
    monkeypatch.setenv(BIN_ENV, str(present))
    row = next(c for c in doctor.environment_checks() if c["check"] == "harness")
    assert row["status"] == "PASS" and str(present) in row["detail"]
