"""STG-05 CB-08: the store (``.aew/state``) is group-readable whatever the umask, and nothing else AEW writes changes.

Output-side: the engine runs for real under each umask, then every path in the store is walked. Nothing between the
engine's writes and the walk changes a mode: the one-time migration never runs in these tests (the control file keeps
the store's mode throughout, which is its record), so a writer that forgets the store's mode fails here without being
listed. The workload names what it must have produced (handoffs, an overflow sidecar the engine staged, a sealed
segment), so the walk cannot pass by finding nothing. The migration has tests of its own below.
Windows has no permission bits: those tests are POSIX only (pinned in tests/platform-skips.yaml).
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import create_unit, integrate, sample_project, to_commit_ready  # noqa: E402
from log_fixture import extend_log  # noqa: E402
from store_model import init, make_store, one_transaction  # noqa: E402

from aew.engine import outbox  # noqa: E402
from aew.engine import store as store_mod  # noqa: E402
from aew.engine.store import STORE_DIR_MODE, STORE_FILE_MODE  # noqa: E402

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows has none")

# Enough revisions for `aew history compact` to seal one segment.
LONG = outbox.LOG_WINDOW + outbox.SEGMENT_SIZE + 8


def mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def store_modes(aew: Path) -> dict[str, int]:
    """Every path in the store, the store directory itself included (a trailing ``/`` marks a directory)."""
    out = {"state/": mode(aew / "state")}
    for d, dirs, files in os.walk(aew / "state"):
        for name in dirs:
            out[(Path(d) / name).relative_to(aew).as_posix() + "/"] = mode(Path(d) / name)
        for name in files:
            out[(Path(d) / name).relative_to(aew).as_posix()] = mode(Path(d) / name)
    return out


def want(rel: str) -> int:
    return STORE_DIR_MODE if rel.endswith("/") else STORE_FILE_MODE


def not_exact(found: dict[str, int]) -> dict[str, str]:
    return {rel: oct(m) for rel, m in found.items() if m != want(rel)}


@pytest.fixture
def umask():
    old = os.umask(0o022)
    os.umask(old)

    def set_mask(value: int) -> None:
        os.umask(value)

    yield set_mask
    os.umask(old)


@posix
@pytest.mark.parametrize("mask", [0o077, 0o002], ids=["umask077", "umask002"])
def test_every_file_the_engine_writes_in_the_store_has_exactly_the_stores_mode_whatever_the_umask(tmp_path, umask,
                                                                                                   mask):
    umask(mask)  # the CLI processes below inherit it
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integrate(p, wid)
    aew = p.root / ".aew"
    found = store_modes(aew)
    assert {"state/CURRENT.md", "state/control.yaml", "state/txn/", "state/log/"} <= set(found)
    assert not_exact(found) == {}  # the engine's writes alone: nothing has changed a mode since
    # A long log for the compactor, from a fixture that writes files directly. Its own new files are given the store's
    # modes here; the control file it rewrites in place keeps the engine's, so the migration stays out of the test.
    before = set(found)
    extend_log(aew, LONG, overflow_every=97)
    for rel in set(store_modes(aew)) - before:
        os.chmod(aew / rel, want(rel))
    assert mode(aew / "state" / "control.yaml") == STORE_FILE_MODE
    assert p.ok("history", "compact", "--json")["sealed"], "the compaction sealed nothing: the test proves nothing"
    create_unit(p, "ticket", "After the compaction")  # a real commit on top
    offer = p.lead("lead", "handoff", "offer")["offer"]  # last: the handoff supersedes this Lead's credential
    p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))
    found = store_modes(aew)
    assert any(rel.startswith("state/log/seg-") for rel in found)
    assert any(r.startswith("state/handoffs/") and not r.endswith("/") for r in found), sorted(found)
    assert not_exact(found) == {}
    # Everything else keeps AEW's 0600, even where the umask would allow more.
    others = [path for top in ("work", "evidence", "decisions") for path in (aew / top).rglob("*") if path.is_file()]
    assert others and {path.relative_to(aew).as_posix(): oct(mode(path)) for path in others
                       if mode(path) != 0o600} == {}


@posix
@pytest.mark.parametrize("mask", [0o077, 0o002], ids=["umask077", "umask002"])
def test_an_overflow_sidecar_the_engine_stages_has_the_stores_mode_and_a_staged_write_outside_it_keeps_0600(
        tmp_path, umask, mask):
    umask(mask)
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)  # 70 events: the complete set is staged and applied as a sidecar
    found = store_modes(root)
    assert "state/log/000002.events.yaml" in found, sorted(found)
    assert not_exact(found) == {}
    records = list((root / "records").glob("*.md"))
    assert records and {r.name: oct(mode(r)) for r in records if mode(r) != 0o600} == {}


def pre_modes(aew: Path) -> None:
    """The store as AEW wrote it before CB-08."""
    for rel in store_modes(aew):
        os.chmod(aew / rel, 0o700 if rel.endswith("/") else 0o600)


@posix
def test_a_store_from_before_the_modes_gets_them_once_and_doctor_reports_one_changed_later(tmp_path, umask):
    umask(0o022)
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    pre_modes(aew)
    assert all(m in (0o600, 0o700) for m in store_modes(aew).values())
    checks = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}  # doctor's locked read recovers first
    assert checks["store-modes"]["status"] == "PASS", checks["store-modes"]
    assert not_exact(store_modes(aew)) == {}
    # The migration ran once: the control file's mode records it, so a mode changed later is reported, not repaired.
    later = aew / "state" / "log" / "000000.yaml"
    os.chmod(later, 0o600)
    p.ok("status", "--json")
    assert mode(later) == 0o600
    check = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}["store-modes"]
    assert check["status"] == "WARN" and "state/log/000000.yaml" in check["detail"], check
    assert "chmod -R u+rwX,g+rX .aew/state" in check["detail"]


@posix
def test_an_interrupted_migration_runs_again_until_the_control_file_has_the_mode(tmp_path, umask):
    umask(0o022)
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    pre_modes(aew)
    os.chmod(aew / "state" / "CURRENT.md", 0o640)  # part-way: some paths re-moded, the control file (last) not yet
    p.ok("status", "--json")
    assert mode(aew / "state" / "log" / "000000.yaml") == STORE_FILE_MODE
    assert mode(aew / "state" / "control.yaml") == STORE_FILE_MODE


@posix
def test_the_migration_changes_only_what_lacks_the_bits_and_finishes_past_a_path_it_may_not_change(tmp_path, umask,
                                                                                                  monkeypatch):
    """A path owned by another account (``chmod`` is EPERM for a non-owner, even to the mode it has) never stops a
    command: the migration leaves it, finishes, and `aew doctor` names it."""
    umask(0o022)
    root = tmp_path / ".aew"
    one_transaction(init(root))
    pre_modes(root)
    already = root / "state" / "CURRENT.md"
    os.chmod(already, 0o644)  # has the bits: the migration must not touch it
    foreign = root / "state" / "log" / "000001.yaml"  # lacks them, and this process may not change it
    real_chmod, touched = os.chmod, []

    def chmod(path, m, *a, **kw):
        touched.append(Path(path))
        if Path(path) in (already, foreign):
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_chmod(path, m, *a, **kw)

    monkeypatch.setattr(store_mod.os, "chmod", chmod)
    store = make_store(root)
    store.read()  # recovery migrates, and does not fail
    assert already.resolve() not in [t.resolve() for t in touched]
    assert mode(root / "state" / "control.yaml") == STORE_FILE_MODE  # the migration finished
    assert store.mode_problems() == ["state/log/000001.yaml"]  # what is left, for doctor to name


@posix
def test_a_path_the_compactor_prunes_during_a_walk_fails_neither_the_migration_nor_doctor(tmp_path, umask,
                                                                                         monkeypatch):
    """The compactor removes log records without the control lock: a name a walk listed may be gone when it is
    looked at."""
    umask(0o022)
    root = tmp_path / ".aew"
    one_transaction(init(root))
    pre_modes(root)
    real_walk = os.walk

    def walk(top, *a, **kw):
        for d, dirs, files in real_walk(top, *a, **kw):
            if Path(d).name == "log" and files:
                (Path(d) / files[0]).unlink()  # pruned after listing, as `log_compact._unlink` would
            yield d, dirs, files

    monkeypatch.setattr(store_mod.os, "walk", walk)
    store = make_store(root)
    assert store.mode_problems() is not None
    store.read()
    assert mode(root / "state" / "control.yaml") == STORE_FILE_MODE


@posix
def test_a_store_directory_that_is_a_link_still_gets_the_stores_modes(tmp_path, umask):
    umask(0o077)
    root = tmp_path / ".aew"
    one_transaction(init(root))
    (root / "state").rename(root / "state.real")
    (root / "state").symlink_to(root / "state.real", target_is_directory=True)
    store = make_store(root)
    one_transaction(store)
    for rel in ("control.yaml", "log/000002.yaml", "log/000002.events.yaml", "CURRENT.md"):
        assert mode(root / "state.real" / rel) == STORE_FILE_MODE, rel
    assert store.mode_problems() == []


def test_the_primary_group_check_names_what_makes_a_group_not_user_private():
    from aew.doctor import private_group_check

    ok = private_group_check("op", "op", [], [], listed=12, remote=[])
    assert ok["status"] == "PASS" and "among the 12 accounts this host lists" in ok["detail"]
    assert private_group_check("op", "op", ["op"], [], listed=1, remote=[])["status"] == "PASS"  # oneself is no other
    shared = private_group_check("op", "staff", ["op", "ana"], ["bo"], listed=3, remote=[])
    assert shared["status"] == "WARN"
    for part in ("named 'staff'", "other members (ana)", "primary group of bo"):
        assert part in shared["detail"], shared["detail"]
    # Accounts from a directory service need not all be listed: a group that looks private is not confirmed.
    unseen = private_group_check("op", "op", [], [], listed=12, remote=["sss"])
    assert unseen["status"] == "WARN" and "sss" in unseen["detail"] and "cannot confirm" in unseen["detail"]
    # Configured but not serving (review of #230, m7): named, and no bar to a PASS.
    idle = private_group_check("op", "op", [], [], listed=12, remote=[], idle=["sss"])
    assert idle["status"] == "PASS" and "sss is configured for accounts but not serving" in idle["detail"]
    # The PASS claims only what was checked: the group, with the store's files' group left to `store-group` (m6).
    assert "`store-group` checks their group" in ok["detail"] and "to you alone" not in ok["detail"]


def test_the_name_service_sources_beyond_this_hosts_files_are_found(tmp_path):
    from aew.doctor import directory_sources

    conf, pipe, etc = tmp_path / "nsswitch.conf", tmp_path / "nss", tmp_path / "etc"
    etc.mkdir()
    (etc / "passwd").write_text("root:x:0:0::/root:/bin/sh\n", encoding="utf-8")
    pipe.write_text("", encoding="utf-8")  # sssd's responder is there: `sss` serves
    conf.write_text("# a comment: passwd: ldap\npasswd:     files sss systemd\nshadow: files\n"
                    "group:  files [SUCCESS=merge] sss winbind # trailing\nhosts: files dns\n", encoding="utf-8")
    assert directory_sources(conf, sss_pipe=pipe, etc=etc) == (["sss", "winbind"], [])
    pipe.unlink()  # RL8's default profile lists `sss` whether or not sssd runs (review of #230, m7)
    assert directory_sources(conf, sss_pipe=pipe, etc=etc) == (["winbind"], ["sss"])
    conf.write_text("passwd: files systemd\ngroup: files compat\n", encoding="utf-8")
    assert directory_sources(conf, sss_pipe=pipe, etc=etc) == ([], [])
    (etc / "group").write_text("wheel:x:10:\n+@netgroup\n", encoding="utf-8")  # NIS lines: `compat` goes remote (N5)
    assert directory_sources(conf, sss_pipe=pipe, etc=etc) == (["compat (NIS lines in /etc/passwd or /etc/group)"], [])
    assert directory_sources(tmp_path / "absent") == ([], [])


def test_doctor_reports_a_uid_with_no_account_entry_instead_of_crashing(monkeypatch):
    """Review of #230, m5: a container's or a user namespace's uid has no passwd entry, and `getpwuid` raised out of
    doctor with a traceback. It is a WARN now."""
    if sys.platform == "win32":
        from aew.doctor import primary_group

        assert primary_group() is None  # no POSIX accounts to look up
        return
    import pwd

    from aew.doctor import environment_checks

    def missing(uid):
        raise KeyError(f"getpwuid(): uid not found: {uid}")

    monkeypatch.setattr(pwd, "getpwuid", missing)
    found = {c["check"]: c for c in environment_checks()}
    assert found["primary-group"]["status"] == "WARN" and "has no account entry" in found["primary-group"]["detail"]


def test_an_environment_check_that_raises_is_reported_and_the_others_still_run(monkeypatch):
    """The class behind m5 (review of #230): every environment check goes through one guard, as project checks do."""
    from aew import doctor

    def broken():
        raise RuntimeError("synthetic: the check broke")

    monkeypatch.setattr(doctor, "_git", broken)
    found = {c["check"]: c for c in doctor.environment_checks()}
    assert found["git"]["status"] == "FAIL" and "synthetic: the check broke" in found["git"]["detail"]
    assert {"python", "module:yaml", "yaml"} <= set(found)


def test_doctor_names_store_paths_whose_group_is_not_the_operators(tmp_path):
    """Review of #230, m6: the store's modes make it group-readable, so a path whose group is another (written under
    `sg`, or below a set-group-ID directory) is readable by that group. `store-group` names them, and AEW changes
    nothing."""
    from conftest import make_git_repo

    from aew.engine.api import Engine
    from aew.engine.store import ControlStore, operator_gid

    e = Engine.initialize(make_git_repo(tmp_path / "repo", {"README.md": "# g\n"}), project_id="g")
    store = ControlStore(e.aew_root)
    gid = operator_gid()
    if gid is None:  # Windows: no groups
        assert store.group_problems(0) is None
        return
    mine = os.stat(store.store_dir).st_gid
    assert store.group_problems(mine) == []
    other = store.group_problems(mine + 1)  # a synthetic gid: every path is "another group" against it
    assert other and ("state/", mine) in other and all(g == mine for _, g in other)
    check = {c["check"]: c for c in e.doctor_checks()}["store-group"]
    assert check["status"] == ("PASS" if mine == gid else "WARN"), check


def test_doctor_reports_the_operators_primary_group_where_there_are_posix_groups(tmp_path):
    from aew.doctor import environment_checks

    found = [c for c in environment_checks() if c["check"] == "primary-group"]
    if sys.platform == "win32":
        assert found == []  # no POSIX groups, so nothing to state
    else:
        assert [c["status"] for c in found] in (["PASS"], ["WARN"])
