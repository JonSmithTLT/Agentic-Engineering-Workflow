"""Reading fake OpenCode's database while its server writes it (the Windows flake of
``test_harness_send_defaults_to_next_step_and_posts_steer``, seen three times by 2026-11-07).

``FakeOpenCode.persist`` swaps the database in with ``os.replace`` and already waits out a reader that holds the file.
The other side had no such wait: on Windows a read that meets the swap gets PermissionError for that moment, and the
test failed. Every reader now goes through ``fake_opencode.read_db``, which waits that moment out, bounded.
"""

from __future__ import annotations

import json
from pathlib import Path

import fake_opencode
import pytest
from sleep_patch import patch_sleep


def test_a_read_that_meets_the_swap_waits_it_out_and_returns_the_database(tmp_path, monkeypatch):
    db = tmp_path / "fake-db.json"
    db.write_text(json.dumps({"ses_1": {"prompts": [{"delivery": "steer"}]}}), encoding="utf-8")
    real_read, refused = Path.read_text, [0]

    def swapping(self: Path, *args, **kwargs) -> str:
        if self == db and refused[0] < 3:
            refused[0] += 1
            raise PermissionError(13, "Permission denied", str(self))
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", swapping)
    patch_sleep(monkeypatch, fake_opencode)
    assert fake_opencode.read_db(db) == {"ses_1": {"prompts": [{"delivery": "steer"}]}}
    assert refused[0] == 3


def test_a_file_that_stays_locked_still_fails_after_the_bound(tmp_path, monkeypatch):
    db = tmp_path / "fake-db.json"
    db.write_text("{}", encoding="utf-8")
    tries = [0]

    def locked(self: Path, *args, **kwargs) -> str:
        tries[0] += 1
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "read_text", locked)
    patch_sleep(monkeypatch, fake_opencode)
    with pytest.raises(PermissionError):
        fake_opencode.read_db(db)
    assert tries[0] == 100


def test_no_database_yet_reads_as_empty(tmp_path):
    assert fake_opencode.read_db(tmp_path / "fake-db.json") == {}


def test_every_reader_of_the_database_in_the_tests_goes_through_read_db():
    """The class, not the instance: a test that reads ``fake-db.json`` by hand would bring the flake back."""
    assert hand_readers(Path(__file__).resolve().parents[1]) == []


def hand_readers(tests: Path) -> list[str]:
    """Each place under ``tests`` that names ``fake-db.json`` without ``read_db(`` on the same line (fake_opencode.py,
    the writer, and this module are left out)."""
    found = []
    for path in sorted(tests.rglob("*.py")):
        if path.name in {"fake_opencode.py", Path(__file__).name}:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "fake-db.json" in line and "read_db(" not in line:
                found.append(f"{path.relative_to(tests).as_posix()}:{n}")
    return found


def test_the_sweep_finds_a_reader_by_hand(tmp_path):
    (tmp_path / "test_x.py").write_text('db = json.loads((d / "fake-db.json").read_text())\n', encoding="utf-8")
    (tmp_path / "test_y.py").write_text('db = fake_opencode.read_db(d / "fake-db.json")\n', encoding="utf-8")
    assert hand_readers(tmp_path) == ["test_x.py:1"]
