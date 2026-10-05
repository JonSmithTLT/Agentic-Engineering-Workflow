"""ADR-0012 D6 (M4-D slice D2) on real projects and real processes: `aew history compact` behind the real
4,096-revision window, `history log` across the sealed/unsealed boundary, doctor's window check, processes killed at
both sealing fault points, and a lockless reader in one process racing a compaction in another.

A project's log is lengthened with synthetic transitions (``log_fixture.extend_log``) rather than thousands of real
commits; the records are shaped like real ones and chained from the committed head, and real commits follow."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

from aewflow import create_planned_ticket, sample_project  # noqa: E402
from conftest import clean_env  # noqa: E402
from invariants import assert_control_invariants, load_control  # noqa: E402
from log_fixture import extend_log  # noqa: E402
from store_model import init, outbox_violations  # noqa: E402

from aew.engine import outbox  # noqa: E402
from aew.engine.faults import CRASH_EXIT_CODE  # noqa: E402

SEG = outbox.SEGMENT_SIZE
LONG = outbox.LOG_WINDOW + 2 * SEG + 88  # two segments eligible; more than LOG_WINDOW + 256 unsealed before
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def long_project(tmp_path: Path):
    p = sample_project(tmp_path)
    extend_log(p.root / ".aew", LONG, overflow_every=97)
    return p


def log(p, *args: str) -> dict:
    return p.ok("history", "log", *args, "--json")


def doctor_log_check(p) -> dict:
    [check] = [c for c in p.aew("doctor", "--json").json["checks"] if c["check"] == "transition-log"]
    return check


def test_compact_end_to_end_and_history_log_across_the_sealed_boundary(tmp_path):
    p = long_project(tmp_path)
    before = log(p, "--since", "0", "--limit", "5000")["transitions"]
    assert [t["revision"] for t in before] == list(range(1, LONG + 1))
    assert doctor_log_check(p)["status"] == "WARN"

    out = p.ok("history", "compact", "--json")
    assert out["sealed"] == [0, 1] and out["segments"] == 2 and out["pending"] == []
    assert out["unsealed"] == LONG + 1 - 2 * SEG <= outbox.LOG_WINDOW + SEG
    log_dir = p.root / ".aew/state/log"
    assert (log_dir / "seg-000000.yaml").exists() and (log_dir / "seg-000001.yaml").exists()
    assert not (log_dir / f"{2 * SEG - 1:06d}.yaml").exists() and (log_dir / f"{2 * SEG:06d}.yaml").exists()
    check = doctor_log_check(p)
    assert check["status"] == "PASS" and "2 sealed segment(s)" in check["detail"]

    # The same logical transitions, whatever their representation; the cursor is still the revision.
    assert log(p, "--since", "0", "--limit", "5000")["transitions"] == before
    page = log(p, "--since", str(2 * SEG - 3), "--limit", "6")  # across the sealed/unsealed boundary
    assert [t["revision"] for t in page["transitions"]] == list(range(2 * SEG - 2, 2 * SEG + 4))
    assert page["next"] == 2 * SEG + 3
    sealed_overflow = 97  # in segment 0: its complete events come from the sealed payload
    [t] = log(p, "--since", str(sealed_overflow - 1), "--limit", "1")["transitions"]
    assert len(t["events"]) == 70 and t["event_overflow"]["event_count"] == 70
    narrowed = log(p, "--since", "0", "--limit", "600", "--kind", "decision.recorded")["transitions"]
    assert [t["revision"] for t in narrowed if t["revision"] < 2 * SEG] == [97, 194, 291, 388, 485]
    assert all({e["kind"] for e in t["events"]} == {"decision.recorded"} for t in narrowed)
    # --follow from a cursor behind the window returns at once, walking the segments
    followed = log(p, "--since", "10", "--limit", "3", "--follow", "--timeout", "5")
    assert [t["revision"] for t in followed["transitions"]] == [11, 12, 13]

    # Real commits continue the chain on top; compaction again finds nothing to do.
    create_planned_ticket(p, tmp_path)
    assert_control_invariants(p)
    again = p.ok("history", "compact", "--json")
    assert again["sealed"] == [] and again["resumed"] == []


def test_follow_waits_for_the_next_commit_after_compaction(tmp_path):
    p = long_project(tmp_path)
    p.ok("history", "compact", "--json")
    rev = load_control(p.root)["revision"]
    follower = subprocess.Popen(
        [sys.executable, "-m", "aew", "-C", str(p.root), "history", "log", "--since", str(rev), "--follow",
         "--timeout", "60", "--json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        env=clean_env(), stdin=subprocess.DEVNULL, **NO_WINDOW)
    time.sleep(1.0)
    create_planned_ticket(p, tmp_path)
    out, err = follower.communicate(timeout=90)
    assert follower.returncode == 0, err
    got = json.loads(out)
    assert got["transitions"] and got["transitions"][0]["revision"] == rev + 1


@pytest.mark.parametrize("point", ["log.seal.after_segment", "log.seal.mid_prune"])
def test_a_compaction_killed_at_each_sealing_point_recovers(tmp_path, point):
    p = long_project(tmp_path)
    before = log(p, "--since", "0", "--limit", "5000")["transitions"]
    res = p.aew("history", "compact", "--json", env={"AEW_FAULT": point})
    assert res.returncode == CRASH_EXIT_CODE, res.stderr
    log_dir = p.root / ".aew/state/log"
    assert (log_dir / "seg-000000.yaml").exists() and not (log_dir / "seg-000001.yaml").exists()
    remaining = [r for r in range(SEG) if (log_dir / f"{r:06d}.yaml").exists()]
    assert remaining == (list(range(SEG)) if point == "log.seal.after_segment" else list(range(SEG // 2, SEG)))
    # Between the crash and the re-run every logical transition still reads, and the oracle holds.
    assert log(p, "--since", "0", "--limit", "5000")["transitions"] == before
    assert_control_invariants(p)
    out = p.ok("history", "compact", "--json")
    assert out["resumed"] == [0] and out["sealed"] == [1]
    assert log(p, "--since", "0", "--limit", "5000")["transitions"] == before
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- reader races

def run_compactor(root: Path, window: int, env: dict[str, str] | None = None) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(HELPERS / "compact_worker.py"), str(root), str(window)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env(env),
                            **NO_WINDOW)


def read_all(root: Path, state: dict) -> list[dict]:
    return list(outbox.read_transitions(root, 0, state["revision"], outbox=state["outbox"]))


@pytest.mark.serial
@pytest.mark.parametrize("point", ["log.seal.after_segment", "log.seal.mid_prune"])
def test_a_lockless_reader_reads_everything_while_another_process_is_held_mid_seal(tmp_path, point):
    """Deterministic: the compacting process is held at each sealing point (AEW_PAUSE) while this process reads."""
    init(tmp_path)
    state = extend_log(tmp_path, 2 * SEG + 30, overflow_every=13)
    truth = read_all(tmp_path, state)
    hold = tmp_path.parent / f"hold-{point}"
    hold.write_text("")
    proc = run_compactor(tmp_path, 8, {"AEW_PAUSE": f"{point}={hold}"})
    try:
        deadline = time.monotonic() + 60
        while not Path(f"{hold}.reached").exists():
            assert proc.poll() is None and time.monotonic() < deadline, proc.stderr.read() if proc.stderr else ""
            time.sleep(0.05)
        assert read_all(tmp_path, state) == truth
    finally:
        hold.unlink()
    out, err = proc.communicate(timeout=120)
    assert proc.returncode == 0, err
    assert json.loads(out)["sealed"] == [0, 1]
    assert read_all(tmp_path, state) == truth
    assert outbox_violations(tmp_path, state) == []


@pytest.mark.serial
def test_a_lockless_reader_races_a_compaction_in_another_process_without_a_false_gap(tmp_path):
    """Free-running: this process reads the whole log in a loop, without the control lock, while another process
    seals and prunes four segments. Every read must be complete and identical."""
    init(tmp_path)
    state = extend_log(tmp_path, 4 * SEG + 30, overflow_every=13)
    truth = read_all(tmp_path, state)
    proc = run_compactor(tmp_path, 8)
    reads = 0
    while proc.poll() is None:
        assert read_all(tmp_path, state) == truth
        reads += 1
    out, err = proc.communicate(timeout=10)
    assert proc.returncode == 0, err
    assert json.loads(out)["sealed"] == [0, 1, 2, 3]
    assert read_all(tmp_path, state) == truth and reads >= 1
    assert outbox_violations(tmp_path, state) == []
    if os.environ.get("AEW_VERBOSE_RACES"):
        print(f"{reads} complete reads during the compaction")
