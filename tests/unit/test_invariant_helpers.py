"""The invariant oracle itself (tests/helpers/invariants.py) holds on every record shape the engine writes."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from invariants import cap_violations, load_control
from sleep_patch import patch_sleep
from store_model import init

from aew.engine import store as S
from aew.engine.store import READ_RETRIES


def test_the_concurrency_cap_check_reads_an_engine_custodian_without_a_role(tmp_path: Path):
    """M4-D's `integration_attempt` custodian has a `kind` and no `role`. The seeded hierarchy walks crashed on it
    (`KeyError: 'role'`) whenever the non-mutating cap was set and an integration lease was held (nightly, 2026-10-06
    to 2026-10-09). It is never an executor, so it never counts against the cap."""
    (tmp_path / ".aew" / "policy").mkdir(parents=True)
    (tmp_path / ".aew" / "policy" / "gates.yaml").write_text("non_mutating_concurrency: 1\n", encoding="utf-8")
    state = {"work": {}, "invocations": {
        "INV-1": {"kind": "integration_attempt", "status": "active", "work_unit": "T-0001"},
        "INV-2": {"role": "investigator", "status": "active", "work_unit": "T-0002", "scope": "observation"},
    }}
    assert cap_violations(tmp_path, state) == []
    state["invocations"]["INV-3"] = {"role": "researcher", "status": "active", "work_unit": "T-0003",
                                     "scope": "observation"}
    assert cap_violations(tmp_path, state) == [
        "2 non-mutating Tickets have active executors ['T-0002', 'T-0003']; the policy cap is 1"]


# ---------------------------------------------------------------------------------------------- load_control


def _racing_reads(monkeypatch: pytest.MonkeyPatch, failures: int | None) -> tuple[list[Path], list[float]]:
    """``Path.read_bytes`` fails with the PermissionError of a read that races a replace (the old file is
    delete-pending) ``failures`` times, always when None, then reads; and every sleep is counted, not slept. Returns
    (reads, sleeps). Both patches reach only the test's own thread, as ``sleep_patch`` requires: another thread's reads
    and sleeps stay real."""
    real = Path.read_bytes
    owner = threading.get_ident()
    reads: list[Path] = []

    def read_bytes(self: Path) -> bytes:
        if threading.get_ident() != owner:
            return real(self)
        reads.append(self)
        if failures is None or len(reads) <= failures:
            raise PermissionError(13, "Permission denied: the old file is delete-pending")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    return reads, patch_sleep(monkeypatch, S)


def _control_root(tmp_path: Path) -> Path:
    (tmp_path / ".aew").mkdir()
    init(tmp_path / ".aew")
    return tmp_path


@pytest.mark.parametrize("racing", [1, READ_RETRIES - 1])
def test_a_control_read_that_races_a_commits_replace_waits_it_out(tmp_path, monkeypatch, racing):
    """A custody worker or the engine commits while a test reads (and polls) ``control.yaml``: on Windows the read can
    collide with the atomic replace for a moment. ``load_control`` retries as the engine's own lock-free read does
    (``store.retry_lock_free``), so the read is the whole committed state, not a PermissionError (PR #242, F1)."""
    root = _control_root(tmp_path)
    committed = load_control(root)
    reads, sleeps = _racing_reads(monkeypatch, racing)
    assert load_control(root) == committed
    assert len(reads) == racing + 1 and len(sleeps) == racing


def test_a_control_read_that_keeps_failing_raises_after_the_engines_retries(tmp_path, monkeypatch):
    """The bound is the engine's (``READ_RETRIES`` attempts, then the last error): a file that stays unreadable is an
    error, not a wait without end."""
    root = _control_root(tmp_path)
    reads, sleeps = _racing_reads(monkeypatch, None)
    with pytest.raises(PermissionError):
        load_control(root)
    assert len(reads) == READ_RETRIES and len(sleeps) == READ_RETRIES - 1


def test_a_missing_control_file_is_an_error_at_once_not_a_retry(tmp_path, monkeypatch):
    """Only a PermissionError is the race; an absent file fails the test that read it, at once."""
    reads, sleeps = _racing_reads(monkeypatch, 0)
    with pytest.raises(FileNotFoundError):
        load_control(tmp_path)
    assert len(reads) == 1 and sleeps == []


def test_the_racing_read_patch_reaches_only_the_tests_own_thread(tmp_path, monkeypatch):
    """A thread an earlier test left running reads for real while the patch is on, and its read is not counted
    (review of #242 at 8d75ea4c, N1)."""
    other = tmp_path / "other.bin"
    other.write_bytes(b"1")
    reads, _ = _racing_reads(monkeypatch, None)  # every read of the test's own thread fails
    seen: list[bytes] = []
    thread = threading.Thread(target=lambda: seen.append(other.read_bytes()))
    thread.start()
    thread.join(10)
    assert seen == [b"1"] and reads == []
