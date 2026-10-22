"""STG-05 CB-08: the store (``.aew/state``) is group-readable whatever the umask, and nothing else AEW writes changes.

Output-side: the engine runs for real (init, commits, an integration, a compaction) under each umask, then every path
in the store is walked. A new writer of the store that forgets the store's modes fails here without being listed.
Windows has no permission bits: those tests are POSIX only (pinned in tests/platform-skips.yaml).
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import create_unit, integrate, sample_project, to_commit_ready  # noqa: E402
from log_fixture import extend_log  # noqa: E402

from aew.engine import outbox  # noqa: E402
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
def test_every_file_the_engine_writes_in_the_store_is_group_readable_whatever_the_umask(tmp_path, umask, mask):
    umask(mask)  # the CLI processes below inherit it
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integrate(p, wid)
    aew = p.root / ".aew"
    extend_log(aew, LONG, overflow_every=97)  # a fixture writes these directly, with the umask's modes
    # It rewrote the control file in place, which kept its mode; a store written so before CB-08 had a 0600 one.
    os.chmod(aew / "state" / "control.yaml", 0o600)
    assert p.ok("history", "compact", "--json")["sealed"], "the compaction sealed nothing: the test proves nothing"
    create_unit(p, "ticket", "After the compaction")  # a real commit on top
    found = store_modes(aew)
    assert any(rel.startswith("state/log/seg-") for rel in found)
    want = {rel: STORE_DIR_MODE if rel.endswith("/") else STORE_FILE_MODE for rel in found}
    below = {rel: oct(m) for rel, m in found.items() if m & want[rel] != want[rel]}
    assert not below, f"store paths below {STORE_FILE_MODE:o}/{STORE_DIR_MODE:o}: {below}"
    if mask == 0o077:  # nothing wider: the fixture's 0600 files were migrated, the engine's were written so
        assert {rel: oct(m) for rel, m in found.items() if m != want[rel]} == {}
    # The engine's own writes are exactly the store's modes, whatever the umask lets through.
    seg = next(rel for rel in found if rel.startswith("state/log/seg-"))
    for rel in ("state/", "state/log/", "state/control.yaml", "state/CURRENT.md", seg,
                f"state/log/{p.rev():06d}.yaml"):
        assert found[rel] == want[rel], f"{rel}: {oct(found[rel])}"
    # Everything else keeps AEW's 0600, even where the umask would allow more.
    others = [path for top in ("work", "evidence", "decisions") for path in (aew / top).rglob("*") if path.is_file()]
    assert others and {path.relative_to(aew).as_posix(): oct(mode(path)) for path in others
                       if mode(path) != 0o600} == {}


@posix
def test_a_store_from_before_the_modes_gets_them_once_and_doctor_reports_one_changed_later(tmp_path, umask):
    umask(0o022)
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    for rel in store_modes(aew):  # the store as AEW wrote it before CB-08
        os.chmod(aew / rel, 0o700 if rel.endswith("/") else 0o600)
    assert all(m in (0o600, 0o700) for m in store_modes(aew).values())
    checks = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}  # doctor's locked read recovers first
    assert checks["store-modes"]["status"] == "PASS", checks["store-modes"]
    assert {rel: oct(m) for rel, m in store_modes(aew).items()
            if m != (STORE_DIR_MODE if rel.endswith("/") else STORE_FILE_MODE)} == {}
    # The migration ran once: the control file's mode records it, so a mode changed later is reported, not repaired.
    later = aew / "state" / "log" / "000000.yaml"
    os.chmod(later, 0o600)
    p.ok("status", "--json")
    assert mode(later) == 0o600
    check = {c["check"]: c for c in p.aew("doctor", "--json").json["checks"]}["store-modes"]
    assert check["status"] == "WARN" and "state/log/000000.yaml" in check["detail"], check


@posix
def test_an_interrupted_migration_runs_again_until_the_control_file_has_the_mode(tmp_path, umask):
    umask(0o022)
    p = sample_project(tmp_path)
    aew = p.root / ".aew"
    for rel in store_modes(aew):
        os.chmod(aew / rel, 0o700 if rel.endswith("/") else 0o600)
    os.chmod(aew / "state" / "CURRENT.md", 0o640)  # part-way: some paths re-moded, the control file (last) not yet
    p.ok("status", "--json")
    assert mode(aew / "state" / "log" / "000000.yaml") == STORE_FILE_MODE
    assert mode(aew / "state" / "control.yaml") == STORE_FILE_MODE


def test_the_primary_group_check_names_what_makes_a_group_not_user_private():
    from aew.doctor import private_group_check

    assert private_group_check("op", "op", [], [])["status"] == "PASS"
    assert private_group_check("op", "op", ["op"], [])["status"] == "PASS"  # listing oneself is no other member
    shared = private_group_check("op", "staff", ["op", "ana"], ["bo"])
    assert shared["status"] == "WARN"
    for part in ("named 'staff'", "other members (ana)", "primary group of bo"):
        assert part in shared["detail"], shared["detail"]


def test_doctor_reports_the_operators_primary_group_where_there_are_posix_groups(tmp_path):
    from aew.doctor import environment_checks

    found = [c for c in environment_checks() if c["check"] == "primary-group"]
    if sys.platform == "win32":
        assert found == []  # no POSIX groups, so nothing to state
    else:
        assert [c["status"] for c in found] in (["PASS"], ["WARN"])
