"""STG-05 CB-08: the store (``.aew/state``) has exactly its target group and modes whatever the umask, and nothing else
AEW writes changes (D-CS1-10 and D-CS1-11 as A-36 amends them; WIS-00's bound).

Output-side: the engine runs for real under each umask and each kind of group, then every path in the store is walked.
Nothing between the engine's writes and the walk changes a group or mode: the migration never runs in the walk test
(the control file keeps the target throughout, which is its record), so a writer that forgets the target fails here
without being listed. The workload names what it must have produced (handoffs, an overflow sidecar the engine staged,
a sealed segment), so the walk cannot pass by finding nothing. The host is synthetic (``tests/helpers/group_host.py``),
with groups this process really holds. The migration has tests of its own below, and the rest of the rule is in
``test_store_group.py``. Windows has no permission bits or groups: those tests are POSIX only (pinned in
tests/platform-skips.yaml).
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

import group_host as gh  # noqa: E402
from aewflow import create_unit, integrate, sample_project, to_commit_ready  # noqa: E402
from log_fixture import extend_log  # noqa: E402
from store_model import init, make_store, one_transaction  # noqa: E402

from aew.engine import outbox  # noqa: E402
from aew.engine import store as store_mod  # noqa: E402
from aew.engine import store_group as sg  # noqa: E402

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows has none")

# Enough revisions for `aew history compact` to seal one segment.
LONG = outbox.LOG_WINDOW + outbox.SEGMENT_SIZE + 8
KINDS = ["user_private", "local_aew", "owner_only"]


def mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def kind_host(kind: str) -> tuple[sg.HostGroups, int, tuple[int, int]]:
    """A host of each kind, and the group and modes its store must have."""
    egid, s = gh.held()
    if kind == "user_private":
        return gh.make_host(primary=egid), egid, sg.GROUP_READ
    if kind == "local_aew":
        return gh.make_host(primary=egid, user_private=False, aew=s), s, sg.GROUP_READ
    return gh.make_host(primary=egid, user_private=False), egid, sg.OWNER_ONLY


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
@pytest.mark.parametrize("kind", KINDS)
def test_every_store_path_has_exactly_the_target_group_and_modes_under_each_kind_of_group_whatever_the_umask(
        tmp_path, umask, monkeypatch, kind, mask):
    host, gid, modes = kind_host(kind)
    gh.install_children(monkeypatch, tmp_path, host)  # every `aew` process the workload starts reads this host
    umask(mask)  # the CLI processes below inherit it
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integrate(p, wid)
    aew = p.root / ".aew"
    found = gh.store_state(aew)
    assert {"state/CURRENT.md", "state/control.yaml", "state/txn/", "state/log/"} <= set(found)
    assert gh.off_target(found, gid, modes) == {}  # the engine's writes alone: nothing has changed a mode since
    # A long log for the compactor, from a fixture that writes files directly. Its own new files are given the target
    # here; the control file it rewrites in place keeps the engine's, so the migration stays out of the test.
    before = set(found)
    extend_log(aew, LONG, overflow_every=97)
    for rel in set(gh.store_state(aew)) - before:
        os.chown(aew / rel, -1, gid)
        os.chmod(aew / rel, modes[1] if rel.endswith("/") else modes[0])
    assert gh.store_state(aew)["state/control.yaml"] == (gid, modes[0])
    assert p.ok("history", "compact", "--json")["sealed"], "the compaction sealed nothing: the test proves nothing"
    create_unit(p, "ticket", "After the compaction")  # a real commit on top
    offer = p.lead("lead", "handoff", "offer")["offer"]  # last: the handoff supersedes this Lead's credential
    p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))
    found = gh.store_state(aew)
    assert any(rel.startswith("state/log/seg-") for rel in found)
    assert any(r.startswith("state/handoffs/") and not r.endswith("/") for r in found), sorted(found)
    assert gh.off_target(found, gid, modes) == {}
    # Everything else keeps AEW's 0600, even where the umask would allow more.
    others = [path for top in ("work", "evidence", "decisions") for path in (aew / top).rglob("*") if path.is_file()]
    assert others and {path.relative_to(aew).as_posix(): oct(mode(path)) for path in others
                       if mode(path) != 0o600} == {}


@posix
@pytest.mark.parametrize("mask", [0o077, 0o002], ids=["umask077", "umask002"])
@pytest.mark.parametrize("kind", KINDS)
def test_an_overflow_sidecar_the_engine_stages_has_the_target_and_a_staged_write_outside_it_keeps_0600(
        tmp_path, umask, monkeypatch, kind, mask):
    host, gid, modes = kind_host(kind)
    gh.install(monkeypatch, host)
    umask(mask)
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)  # 70 events: the complete set is staged and applied as a sidecar
    found = gh.store_state(root)
    assert "state/log/000002.events.yaml" in found, sorted(found)
    assert gh.off_target(found, gid, modes) == {}
    records = list((root / "records").glob("*.md"))
    assert records and {r.name: oct(mode(r)) for r in records if mode(r) != 0o600} == {}


def pre_modes(aew: Path) -> None:
    """The store as AEW wrote it before CB-08."""
    for rel in gh.store_state(aew):
        os.chmod(aew / rel, 0o700 if rel.endswith("/") else 0o600)


@posix
def test_a_store_from_before_the_modes_gets_them_once_and_doctor_reports_one_changed_later(tmp_path, umask,
                                                                                          monkeypatch):
    umask(0o022)
    egid, _s = gh.held()
    gh.install_children(monkeypatch, tmp_path, gh.make_host(primary=egid))
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    pre_modes(aew)
    assert all(m in (0o600, 0o700) for _g, m in gh.store_state(aew).values())
    checks = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}  # doctor's locked read walks first
    assert checks["store-modes"]["status"] == "PASS", checks["store-modes"]
    assert gh.off_target(gh.store_state(aew), egid, sg.GROUP_READ) == {}
    # The migration ran: the control file's group and mode record it, so a mode changed later is reported, not
    # repaired.
    later = aew / "state" / "log" / "000000.yaml"
    os.chmod(later, 0o600)
    p.ok("status", "--json")
    assert mode(later) == 0o600
    check = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}["store-modes"]
    assert check["status"] == "WARN" and "state/log/000000.yaml" in check["detail"], check
    assert f"`chgrp {egid} <path>`" in check["detail"] and "`chmod 0640 <file>`" in check["detail"], check


@posix
def test_an_interrupted_migration_runs_again_until_the_control_file_has_the_target(tmp_path, umask, monkeypatch):
    umask(0o022)
    egid, _s = gh.held()
    gh.install_children(monkeypatch, tmp_path, gh.make_host(primary=egid))
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    pre_modes(aew)
    os.chmod(aew / "state" / "CURRENT.md", 0o640)  # part-way: some paths re-moded, the control file (last) not yet
    p.ok("status", "--json")
    assert mode(aew / "state" / "log" / "000000.yaml") == sg.GROUP_READ[0]
    assert mode(aew / "state" / "control.yaml") == sg.GROUP_READ[0]


@posix
def test_the_migration_sets_exact_modes_and_finishes_past_a_path_it_may_not_change(tmp_path, umask, monkeypatch):
    """A path owned by another account (``chmod`` is EPERM for a non-owner, even to the mode it has) never stops a
    command: the migration leaves it, finishes, and `aew doctor` names it. A path wider than the target is narrowed
    (WIS-00's bound), not kept as CS-1 kept it."""
    umask(0o022)
    egid, _s = gh.held()
    gh.install(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    one_transaction(init(root))
    pre_modes(root)
    wide = root / "state" / "CURRENT.md"
    os.chmod(wide, 0o644)  # above the bound: the migration narrows it
    foreign = root / "state" / "log" / "000001.yaml"  # this process may not change it
    real_chmod = os.chmod

    def chmod(path, m, *a, **kw):
        if Path(path) == foreign:
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_chmod(path, m, *a, **kw)

    monkeypatch.setattr(store_mod.os, "chmod", chmod)
    store = make_store(root)
    store.read()  # the open walks, and does not fail
    assert mode(wide) == sg.GROUP_READ[0]
    assert mode(root / "state" / "control.yaml") == sg.GROUP_READ[0]  # the migration finished
    assert store.path_problems(store.group_view().target) == [("state/log/000001.yaml", egid, 0o600)]


@posix
def test_a_path_the_compactor_prunes_during_a_walk_fails_neither_the_migration_nor_doctor(tmp_path, umask,
                                                                                         monkeypatch):
    """The compactor removes log records without the control lock: a name a walk listed may be gone when it is
    looked at."""
    umask(0o022)
    egid, _s = gh.held()
    gh.install(monkeypatch, gh.make_host(primary=egid))
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
    assert store.path_problems(sg.Target(egid, *sg.GROUP_READ)) is not None
    store.read()
    assert mode(root / "state" / "control.yaml") == sg.GROUP_READ[0]


@posix
def test_a_store_directory_that_is_a_link_still_gets_the_target(tmp_path, umask, monkeypatch):
    umask(0o077)
    egid, _s = gh.held()
    gh.install(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    one_transaction(init(root))
    (root / "state").rename(root / "state.real")
    (root / "state").symlink_to(root / "state.real", target_is_directory=True)
    store = make_store(root)
    one_transaction(store)
    for rel in ("control.yaml", "log/000002.yaml", "log/000002.events.yaml", "CURRENT.md"):
        assert mode(root / "state.real" / rel) == sg.GROUP_READ[0], rel
    assert store.path_problems(store.group_view().target) == []


def test_an_environment_check_that_raises_is_reported_and_the_others_still_run(monkeypatch):
    """The class behind m5 (review of #230): every environment check goes through one guard, as project checks do."""
    from aew import doctor

    def broken():
        raise RuntimeError("synthetic: the check broke")

    monkeypatch.setattr(doctor, "_git", broken)
    found = {c["check"]: c for c in doctor.environment_checks()}
    assert found["git"]["status"] == "FAIL" and "synthetic: the check broke" in found["git"]["detail"]
    assert {"python", "module:yaml", "yaml"} <= set(found)


@posix
@pytest.mark.parametrize("kind", ["user_private", "local_aew", "unlistable", "lacking"])
def test_doctor_reports_the_group_its_kind_roots_record_its_writers_and_whether_wis_can_be_qualified(
        tmp_path, monkeypatch, kind):
    """D-CS1-11's doctor lines: the store's group and its kind, root's record and what it says, whether the group is
    private and if not which part fails (with the record root writes to get group mode back), each running writer
    that lacks the group, and whether WIS can be qualified here as far as the store goes."""
    from conftest import make_git_repo

    from aew.engine.api import Engine

    egid, s = gh.held()
    host = {"user_private": gh.make_host(primary=egid),
            "local_aew": gh.make_host(primary=egid, user_private=False, aew=s),
            "unlistable": gh.make_host(primary=egid, unlistable=("sss",)),
            "lacking": gh.make_host(primary=egid, user_private=False, aew=gh.unheld())}[kind]
    gh.install(monkeypatch, host)
    e = Engine.initialize(make_git_repo(tmp_path / "repo", {"README.md": "# g\n"}), project_id="g")
    checks = {c["check"]: c for c in e.doctor_checks()}
    group, writers, wis = checks["store-group"], checks["store-writers"], checks["wis-store"]
    assert checks["store-modes"]["status"] == "PASS", checks["store-modes"]
    if kind == "user_private":
        assert group["status"] == "PASS" and "your user-private primary group" in group["detail"]
        assert "Root's group record" in group["detail"] and "absent" in group["detail"]
        assert wis["status"] == "PASS" and "the qualification gate's" in wis["detail"]
    elif kind == "local_aew":
        assert group["status"] == "PASS" and "'aew-op'" in group["detail"] and "local AEW group" in group["detail"]
        assert "names aew-op (gid" in group["detail"] and writers["status"] == "PASS" and wis["status"] == "PASS"
    elif kind == "unlistable":
        assert group["status"] == "WARN" and "WIS-01a part 3 (for your primary group)" in group["detail"], group
        assert "sss" in group["detail"] and "configured counts, running or not" in group["detail"]
        assert f"Group=op {egid}" in group["detail"] and "Signal=sss" in group["detail"], group
        assert wis["status"] == "WARN" and "WIS cannot be qualified on this host" in wis["detail"]
    else:
        assert group["status"] == "PASS"  # the group is private; this process just does not hold it
        assert writers["status"] == "WARN" and f"this process (pid {os.getpid()})" in writers["detail"], writers
        assert "Restart each" in writers["detail"] and wis["status"] == "WARN"
