"""The store (``.aew/state``) is owner-only whatever the umask: files 0600, directories 0700 (operator, 2026-10-24).

Output-side: the engine runs for real under each umask, then every path in the store is walked. Nothing between the
engine's writes and the walk changes a mode: the one-time narrowing never runs in these tests (the store directory and
the control file stay owner-only throughout, which is its record), so a writer that leaves a path wider fails here
without being listed. The workload names what it must have produced (handoffs, an overflow sidecar the engine staged, a
sealed segment), so the walk cannot pass by finding nothing. The narrowing of a store written group-readable (STG-05
CS-1's CB-08 modes) has tests of its own below. The modes are literals here, not the store's constants, so a change of
those constants fails these tests.
Windows has no permission bits: those tests are POSIX only (pinned in tests/platform-skips.yaml).
"""

from __future__ import annotations

import errno
import os
import shutil
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

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; Windows has none")

# Enough revisions for `aew history compact` to seal one segment.
LONG = outbox.LOG_WINDOW + outbox.SEGMENT_SIZE + 8
OWNER_FILE, OWNER_DIR = 0o600, 0o700
CS1_FILE, CS1_DIR = 0o640, 0o750  # the group-readable modes STG-05 CS-1 wrote the store with (CB-08)


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
    return OWNER_DIR if rel.endswith("/") else OWNER_FILE


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
def test_every_path_the_engine_writes_in_the_store_is_owner_only_whatever_the_umask(tmp_path, umask, mask):
    umask(mask)  # the CLI processes below inherit it
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integrate(p, wid)
    aew = p.root / ".aew"
    found = store_modes(aew)
    assert {"state/CURRENT.md", "state/control.yaml", "state/txn/", "state/log/"} <= set(found)
    assert not_exact(found) == {}  # the engine's writes alone: nothing has changed a mode since
    # A long log for the compactor, from a fixture that writes files directly. Its own new files are made owner-only
    # here; the control file it rewrites in place keeps the engine's, so the narrowing stays out of the test.
    before = set(found)
    extend_log(aew, LONG, overflow_every=97)
    for rel in set(store_modes(aew)) - before:
        os.chmod(aew / rel, want(rel))
    assert mode(aew / "state" / "control.yaml") == OWNER_FILE
    assert p.ok("history", "compact", "--json")["sealed"], "the compaction sealed nothing: the test proves nothing"
    create_unit(p, "ticket", "After the compaction")  # a real commit on top
    offer = p.lead("lead", "handoff", "offer")["offer"]  # last: the handoff supersedes this Lead's credential
    p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))
    found = store_modes(aew)
    assert any(rel.startswith("state/log/seg-") for rel in found)
    assert any(r.startswith("state/handoffs/") and not r.endswith("/") for r in found), sorted(found)
    assert not_exact(found) == {}
    # Everything else keeps AEW's 0600 too, even where the umask would allow more.
    others = [path for top in ("work", "evidence", "decisions") for path in (aew / top).rglob("*") if path.is_file()]
    assert others and {path.relative_to(aew).as_posix(): oct(mode(path)) for path in others
                       if mode(path) != 0o600} == {}


@posix
@pytest.mark.parametrize("mask", [0o077, 0o002], ids=["umask077", "umask002"])
def test_an_overflow_sidecar_the_engine_stages_is_owner_only_whatever_the_umask(tmp_path, umask, mask):
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


@posix
def test_a_new_store_is_owner_only_from_its_first_file_even_under_an_empty_umask(tmp_path, umask):
    umask(0o000)  # mkdir would give 0777 and an open 0666: only the store's own modes stand between
    root = tmp_path / ".aew"
    init(root)
    found = store_modes(root)
    assert {"state/", "state/control.yaml", "state/CURRENT.md"} <= set(found), sorted(found)
    assert not_exact(found) == {}


def wider(aew: Path, files: int, dirs: int) -> None:
    """The store as an earlier version wrote it: every file ``files`` and every directory ``dirs``."""
    for rel in store_modes(aew):
        os.chmod(aew / rel, dirs if rel.endswith("/") else files)


@posix
@pytest.mark.parametrize("start", [(CS1_FILE, CS1_DIR), (OWNER_FILE, 0o755)], ids=["cs1_group_readable",
                                                                                   "before_cs1_umask022"])
def test_a_store_written_wider_is_narrowed_once_and_doctor_reports_a_path_widened_later(tmp_path, umask, start):
    umask(0o022)
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    wider(aew, *start)
    assert not_exact(store_modes(aew))
    checks = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}  # doctor's locked read recovers first
    assert checks["store-modes"]["status"] == "PASS", checks["store-modes"]
    assert not {"primary-group", "store-group"} & set(checks), sorted(checks)  # no group matters to the store
    assert not_exact(store_modes(aew)) == {}
    # The narrowing ran once: the store directory's and the control file's modes record it, so a mode widened later
    # is reported, not repaired.
    later = aew / "state" / "log" / "000000.yaml"
    os.chmod(later, CS1_FILE)
    p.ok("status", "--json")
    assert mode(later) == CS1_FILE
    check = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}["store-modes"]
    assert check["status"] == "WARN" and "state/log/000000.yaml" in check["detail"], check
    assert "chmod -R go-rwx .aew/state" in check["detail"]


@posix
def test_an_interrupted_narrowing_runs_again_until_the_store_directory_is_owner_only(tmp_path, umask):
    umask(0o022)
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    wider(aew, CS1_FILE, CS1_DIR)
    # Part-way: the control file (first) and some paths narrowed; the store directory (last) not yet.
    os.chmod(aew / "state" / "control.yaml", OWNER_FILE)
    os.chmod(aew / "state" / "CURRENT.md", OWNER_FILE)
    p.ok("status", "--json")
    assert mode(aew / "state" / "log" / "000000.yaml") == OWNER_FILE
    assert mode(aew / "state") == OWNER_DIR
    assert not_exact(store_modes(aew)) == {}


@posix
def test_files_an_earlier_version_writes_into_a_narrowed_store_are_narrowed_at_the_next_open(tmp_path, umask):
    """An earlier AEW (CS-1's) committing into a store already narrowed writes its control file and new files
    group-readable, into directories that stay owner-only: the control file alone takes the narrowing to them."""
    umask(0o022)
    root = tmp_path / ".aew"
    one_transaction(init(root))
    assert not_exact(store_modes(root)) == {}
    for rel in ("control.yaml", "CURRENT.md", "log/000001.yaml"):
        os.chmod(root / "state" / rel, CS1_FILE)
    make_store(root).read()
    assert not_exact(store_modes(root)) == {}


@posix
@pytest.mark.parametrize("refusal", [None, errno.EPERM, errno.EOPNOTSUPP], ids=["does_nothing", "eperm", "eopnotsupp"])
def test_where_the_file_system_keeps_no_permission_bits_no_open_walks_the_store_and_doctor_says_so_once(
        tmp_path, umask, monkeypatch, refusal):
    """A file system that keeps no permission bits (drvfs without `metadata`, vfat, CIFS without Unix extensions) shows
    every path wide, and its `chmod` changes nothing, raising nothing or a refusal (vfat with `fmask`: EPERM). The
    narrowing tries the control file, sees it stay wide, and stops: no open walks the store, and `store-modes` says
    once why the store cannot be owner-only, instead of naming every path (review of #256, F1 and F4)."""
    from conftest import make_git_repo

    from aew.engine.api import Engine

    umask(0o022)
    e = Engine.initialize(make_git_repo(tmp_path / "repo", {"README.md": "# g\n"}), project_id="g")
    wider(e.aew_root, 0o777, 0o777)  # how every path reads there
    touched = []

    def chmod(path, m, *a, **kw):
        touched.append(Path(path).name)
        if refusal is not None:
            raise OSError(refusal, os.strerror(refusal), str(path))

    monkeypatch.setattr(store_mod.os, "chmod", chmod)
    modes = {c["check"]: c for c in e.doctor_checks()}["store-modes"]
    store_mod.ControlStore(e.aew_root).read()  # another open, by another process's store
    assert touched and set(touched) == {"control.yaml"}, touched  # the narrowing's first step at each open, no walk
    assert modes["status"] == "WARN" and "keeps no permission bits" in modes["detail"], modes
    assert "state/" not in modes["detail"], modes


@posix
def test_a_control_file_that_is_a_link_is_never_followed_and_doctor_names_it(tmp_path, umask):
    """The narrowing never follows a link out of the store (review of #256, F3): a control file that is one, made by
    hand, is left as it is, and so is the file it names; `aew doctor` names it. The next commit replaces it with a
    file, and the next open narrows the store."""
    umask(0o022)
    root = tmp_path / ".aew"
    one_transaction(init(root))
    wider(root, CS1_FILE, CS1_DIR)
    control, outside = root / "state" / "control.yaml", tmp_path / "control-elsewhere.yaml"
    os.replace(control, outside)
    os.chmod(outside, 0o644)
    control.symlink_to(outside)
    store = make_store(root)
    store.read()
    assert mode(outside) == 0o644
    named = [rel for rel in store.mode_problems() or [] if rel.startswith("state/control.yaml")]
    assert named == ["state/control.yaml (a symbolic link, which AEW never follows: the next commit replaces it with a "
                     "file)"], store.mode_problems()
    one_transaction(store)
    assert not control.is_symlink()
    store.read()
    assert not_exact(store_modes(root)) == {}


@posix
def test_the_narrowing_changes_only_what_has_group_or_other_bits_and_finishes_past_a_path_it_may_not_change(
        tmp_path, umask, monkeypatch):
    """A path owned by another account (``chmod`` is EPERM for a non-owner, even to the mode it has) never stops a
    command: the narrowing leaves it, finishes, and `aew doctor` names it."""
    umask(0o022)
    root = tmp_path / ".aew"
    one_transaction(init(root))
    wider(root, CS1_FILE, CS1_DIR)
    already = root / "state" / "CURRENT.md"
    os.chmod(already, 0o400)  # owner-only already: the narrowing must not touch it
    foreign = root / "state" / "log" / "000001.yaml"  # wider, and this process may not change it
    real_chmod, touched = os.chmod, []

    def chmod(path, m, *a, **kw):
        touched.append(Path(path))
        if Path(path) in (already, foreign):
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_chmod(path, m, *a, **kw)

    monkeypatch.setattr(store_mod.os, "chmod", chmod)
    store = make_store(root)
    store.read()  # recovery narrows, and does not fail
    assert already.resolve() not in [t.resolve() for t in touched]
    assert mode(root / "state" / "control.yaml") == OWNER_FILE  # the narrowing finished
    assert store.mode_problems() == ["state/log/000001.yaml"]  # what is left, for doctor to name


@posix
def test_a_path_the_compactor_prunes_during_a_walk_fails_neither_the_migration_nor_doctor(tmp_path, umask,
                                                                                         monkeypatch):
    """The compactor removes log records without the control lock: a name a walk listed may be gone when it is
    looked at."""
    umask(0o022)
    root = tmp_path / ".aew"
    one_transaction(init(root))
    wider(root, CS1_FILE, CS1_DIR)
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
    assert mode(root / "state" / "control.yaml") == OWNER_FILE


@posix
def test_a_store_directory_that_is_a_link_still_gets_the_stores_modes(tmp_path, umask):
    umask(0o002)  # a directory made without the store's mode would be 0775
    root = tmp_path / ".aew"
    one_transaction(init(root))
    (root / "state").rename(root / "state.real")
    (root / "state").symlink_to(root / "state.real", target_is_directory=True)
    shutil.rmtree(root / "state.real" / "txn", ignore_errors=True)  # made again below, through the link
    store = make_store(root)
    one_transaction(store)  # 70 events: the redo record is staged in a new txn directory
    assert mode(root / "state.real" / "txn") == OWNER_DIR
    for rel in ("control.yaml", "log/000002.yaml", "log/000002.events.yaml", "CURRENT.md"):
        assert mode(root / "state.real" / rel) == OWNER_FILE, rel
    assert store.mode_problems() == []


def test_an_environment_check_that_raises_is_reported_and_the_others_still_run(monkeypatch):
    """The class behind m5 (review of #230): every environment check goes through one guard, as project checks do."""
    from aew import doctor

    def broken():
        raise RuntimeError("synthetic: the check broke")

    monkeypatch.setattr(doctor, "_git", broken)
    found = {c["check"]: c for c in doctor.environment_checks()}
    assert found["git"]["status"] == "FAIL" and "synthetic: the check broke" in found["git"]["detail"]
    assert {"python", "module:yaml", "yaml"} <= set(found)
