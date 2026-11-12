"""Real OS-lock, crash and simultaneous union boundaries for the disposable told-message record."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aew.engine.lock import FileLock
from aew.harness import told_messages as T

HELPER = Path(__file__).resolve().parents[1] / "helpers" / "told_message_writer.py"
A, B = "MSG-INV-0001-1", "MSG-INV-0002-1"


@pytest.mark.parametrize("where", ["before", "after"])
def test_a_crash_on_either_side_of_rename_keeps_a_complete_old_or_new_union(tmp_path, where):
    T.record(tmp_path, 1, [A], current=lambda: True)
    child = subprocess.run([sys.executable, "-B", str(HELPER), str(tmp_path), "1", B, "--crash", where],
                           capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert child.returncode == 77, child.stderr
    assert T.read(tmp_path, 1) == ({A} if where == "before" else {A, B})
    # The OS released both locks when the process died. Its next ordinary union loses no committed ID.
    T.record(tmp_path, 1, [B], current=lambda: True)
    assert T.read(tmp_path, 1) == {A, B}


def test_simultaneous_brokers_union_without_lost_ids_under_the_stable_os_lock(tmp_path):
    gate = tmp_path / "go"
    processes = []
    expected = set()
    try:
        for n in range(4):
            ids = [f"MSG-INV-{n + 1:04d}-{i}" for i in range(1, 21)]
            expected.update(ids)
            ready = tmp_path / f"ready-{n}"
            processes.append(subprocess.Popen([sys.executable, "-B", str(HELPER), str(tmp_path), "1", *ids,
                                                "--ready", str(ready), "--gate", str(gate)],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        deadline = time.monotonic() + 20
        while len(list(tmp_path.glob("ready-*"))) != 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(list(tmp_path.glob("ready-*"))) == 4
        gate.touch()
        for child in processes:
            _, err = child.communicate(timeout=30)
            assert child.returncode == 0, err
        assert T.read(tmp_path, 1) == expected
        assert {p.name for p in (tmp_path / T.REL).parent.iterdir()} == {
            "told-messages.json", "told-messages.lock", "told-messages.lock.queue"}
    finally:
        for child in processes:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)


def test_authority_changed_while_a_real_process_waits_for_the_lock_prevents_its_write(tmp_path):
    T.record(tmp_path, 1, [A], current=lambda: True)
    before = (tmp_path / T.REL).read_bytes()
    authority, checked = tmp_path / "authority", tmp_path / "checked"
    authority.write_text("1", encoding="utf-8")
    child = None
    try:
        with FileLock(tmp_path / T.LOCK_REL):
            child = subprocess.Popen([sys.executable, "-B", str(HELPER), str(tmp_path), "1", B,
                                      "--authority", str(authority), "--checked", str(checked)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + 20
            while not checked.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert checked.exists() and child.poll() is None
            authority.write_text("2", encoding="utf-8")
        _, err = child.communicate(timeout=30)
        assert child.returncode != 0 and b"lost authority while waiting" in err
        assert (tmp_path / T.REL).read_bytes() == before
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)


def test_a_real_relayed_read_process_cannot_create_a_receipt_or_its_lock_directory(tmp_path):
    child = subprocess.run([sys.executable, "-B", str(HELPER), str(tmp_path), "1", A, "--non-writer"],
                           capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert child.returncode != 0
    error = json.loads(child.stderr)["error"]
    assert error["code"] == "PERMISSION_DENIED" and error["details"]["reason"] == "non_writer_process"
    assert not list(tmp_path.iterdir())


pytestmark = pytest.mark.serial
