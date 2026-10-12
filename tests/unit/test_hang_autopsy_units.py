"""The hang autopsy's pieces, without a session (the hang-and-flake diagnosis plan, G3 H1-H5): the one evidence writer
(redacted, capped, never ``.json``), the process set by (pid, start time), the flight recorder, the child's
diagnostics defaults and its bounded stack files, and the nesting rule's checker. The end-to-end guarantees (a hung
test, the session deadline, the sentinel) are in ``tests/integration/test_hang_autopsy.py``."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import bounds
import childdiag
import flight_recorder
import harness_diagnostics as hd
import proctree
import pytest
from conftest import IS_WINDOWS

TOKEN = "aew1.tk_" + "0" * 16 + "." + "A" * 43  # built here: no credential-shaped string sits in any file


# ---------------------------------------------------------------------------------------------- the writer (L1)

def test_everything_the_autopsy_writes_is_redacted_and_never_named_json(tmp_path):
    work = tmp_path / "work"
    (work / ".aew" / "state").mkdir(parents=True)
    (work / ".aew" / "state" / "control.json").write_text(f'{{"token": "{TOKEN}"}}', encoding="utf-8")
    (work / "events.jsonl").write_text(f'{{"exported": "AEW_LEAD_TOKEN={TOKEN}"}}\n', encoding="utf-8")
    (work / "notes.txt").write_text("nothing secret\n", encoding="utf-8")
    dest = tmp_path / "report" / hd.AUTOPSY_DIR / "t"
    copied, failed = hd.copy_tree(work, dest / "workdir")
    hd.write_text(dest, "processes", f"1 python -m aew --token {TOKEN}\n")
    assert not failed
    written = [p for p in dest.rglob("*") if p.is_file()]
    assert sorted(p.name for p in written) == ["control.json.txt", "events.jsonl.txt", "notes.txt", "processes.txt"]
    assert not list(dest.rglob("*.json"))
    for p in written:
        text = p.read_text(encoding="utf-8")
        assert TOKEN not in text, p
    assert "aew1.<redacted>" in (dest / "workdir" / ".aew" / "state" / "control.json.txt").read_text(encoding="utf-8")
    assert (work / ".aew" / "state" / "control.json").exists()  # copied, never moved


def test_a_file_over_its_cap_keeps_its_tail_with_a_note_and_the_total_cap_refuses_the_rest(tmp_path):
    text = "".join(f"line {i}\n" for i in range(2000))
    out = hd.write_text(tmp_path, "big", text, cap=1000)
    assert out is not None
    kept = out.read_text(encoding="utf-8")
    assert kept.startswith(hd.TRUNCATED) and kept.endswith("line 1999\n") and len(kept) < 1100
    budget = hd.Budget(total=50)
    assert hd.write_text(tmp_path, "small", "x" * 40, budget=budget) is not None
    assert hd.write_text(tmp_path, "over", "x" * 40, budget=budget) is None
    assert budget.refused and "over.txt" in budget.refused[0]


def test_a_redaction_is_never_cut_through_by_the_cap(tmp_path):
    out = hd.write_text(tmp_path, "edge", "x" * 100 + TOKEN + "\nend\n", cap=60)
    assert out is not None and TOKEN[:20] not in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- the process set (P1)

def P(pid: int, ppid: int, start: int) -> proctree.Proc:
    return proctree.Proc(pid, ppid, start, f"p{pid}")


def test_the_session_set_follows_parents_by_start_time_and_never_takes_in_a_reused_pid():
    controller = P(100, 1, 1000)
    table = [
        controller,
        P(200, 100, 1100),  # a worker
        P(300, 200, 1200),  # its helper child
        P(400, 100, 900),  # "parent" 100, but started before the controller: pid 100 was reused, not ours
        P(500, 400, 950),  # its child: unrelated as well
        P(600, 100, 1300),  # the sentinel: excluded by identity
        P(700, 600, 1400),  # and what descends from it
        P(800, 999, 1500),  # unrelated
    ]
    found = proctree.descendants(controller.identity, table, exclude=[(600, 1300)])
    assert [p.pid for p in found] == [200, 300]
    assert [p.pid for p in proctree.children_first(found)] == [300, 200]


def test_a_reused_pid_is_not_the_same_process():
    me = proctree.identity(os.getpid())
    assert me is not None and proctree.same(me)
    assert not proctree.same((os.getpid(), me[1] + 1))
    assert not proctree.end((os.getpid(), me[1] + 1))  # a mismatched start time is never ended


def test_the_process_table_lists_this_process_and_a_child_under_it():
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
    try:
        me = proctree.identity(os.getpid())
        assert me is not None
        under = proctree.descendants(me, proctree.table())
        assert child.pid in {p.pid for p in under}
        ident = proctree.identity(child.pid)
        assert ident is not None and proctree.end(ident)
        child.wait(30)
    finally:
        child.kill()


def test_the_file_holder_lookup_names_the_process_holding_a_file(tmp_path):
    held = tmp_path / "held.txt"
    held.write_text("x", encoding="utf-8")
    ready = tmp_path / "ready"
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    code = (f"import pathlib, time; f = open({str(held)!r}, 'a'); pathlib.Path({str(ready)!r}).write_text('1'); "
            "time.sleep(60)")
    holder = subprocess.Popen([sys.executable, "-c", code], **kwargs)
    try:
        bounds.bounded_wait("test.holder_ready", ready.exists, seconds=30, gone=lambda: holder.poll() is not None)
        found = proctree.holders([str(held)])[str(held)]
        holder_pids = {holder.pid} | {p.pid for p in proctree.descendants(proctree.identity(holder.pid) or (0, 0),
                                                                          proctree.table())}
        assert holder_pids & {p.pid for p in found}, (holder.pid, found)
    finally:
        holder.kill()
        holder.wait(30)


# ---------------------------------------------------------------------------------------------- the flight recorder

def test_the_recorder_keeps_the_last_failed_paths_and_its_codes():
    flight_recorder.clear()
    err = PermissionError(13, "denied")
    flight_recorder.io("replace", "a.txt", err)
    flight_recorder.io("read", "b.txt")
    flight_recorder.io("replace", "c.txt", err)
    flight_recorder.io("replace", "a.txt", err)
    assert flight_recorder.failed_paths() == ["a.txt", "c.txt"]
    last = flight_recorder.snapshot()[-1]
    assert last["kind"] == "io" and last["ok"] is False and last["errno"] == 13
    for _ in range(flight_recorder.CAPACITY + 10):
        flight_recorder.record("noise")
    assert len(flight_recorder.snapshot()) == flight_recorder.CAPACITY  # a ring: bounded whatever happens
    flight_recorder.clear()


# ---------------------------------------------------------------------------------------------- childdiag (L5, P3)

def test_a_childs_periodic_dump_is_at_least_30s_apart_by_default():
    assert childdiag.MIN_INTERVAL_S >= 30


def test_a_childs_stack_file_alternates_two_generations_without_a_rename(tmp_path):
    """faulthandler appends; past the cap the child cancels, truncates the other file, re-arms, then closes the old
    one. Both generations are kept and readable, and nothing is renamed."""
    code = ("import childdiag, time\n"
            "d = childdiag._installed\n"
            "deadline = time.monotonic() + 60\n"
            "while d.rotations < 3 and time.monotonic() < deadline:\n"
            "    time.sleep(0.2)\n"
            "print('rotations', d.rotations)\n")
    env = childdiag.child_env(tmp_path, interval=1)
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    helper = Path(childdiag.__file__)
    proc = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(helper.parent)!r}); "
                           "import childdiag; childdiag.install(cap=200); exec(" + repr(code) + ")"],
                          env=env, capture_output=True, text=True, timeout=120, **kwargs)
    out = "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("out-*.log"))
    import autopsy  # a native crash names itself (review of #217, m5: the Windows CPython 3.13 faulthandler residual)

    assert proc.returncode == 0, proc.stderr + out + autopsy.native_crashes(tmp_path)
    assert "rotations 3" in out, out
    gens = sorted(tmp_path.glob("stacks-*.txt"))
    assert [g.name.split(".")[-2] for g in gens] == ["a", "b"]
    assert all("Thread" in g.read_text(encoding="utf-8") or "generation" in g.read_text(encoding="utf-8")
               for g in gens)


def test_childdiag_does_nothing_without_a_directory(monkeypatch):
    monkeypatch.delenv(childdiag.ENV_DIR, raising=False)
    assert childdiag._installed is None
    assert childdiag.install() is None


# ---------------------------------------------------------------------------------------------- bounds (H5)

def lane(test_timeout: float | None = 600, deadline: float | None = 900, job_min: float = 20, **kw) -> bounds.Lane:
    return bounds.Lane(workflow="w.yml", job="j", step="s", command="pytest", job_timeout_s=job_min * 60,
                       test_timeout_s=test_timeout, deadline_s=deadline, margin_s=bounds.DEADLINE_MARGIN_S,
                       lane=kw.get("lane"), xdist=False, max_worker_restart=None, hang_dir=None, lane_report=None)


def test_the_nesting_rule_names_each_broken_link():
    assert bounds.nesting_problems(lane(), []) == []
    assert "not below --session-deadline" in bounds.nesting_problems(lane(test_timeout=900), [])[0]
    assert "before the job's timeout-minutes" in bounds.nesting_problems(lane(deadline=1000), [])[0]
    assert "no --session-deadline" in bounds.nesting_problems(lane(deadline=None), [])[0]
    chat = bounds.Bound("vertical.chat", 1800.0, None, frozenset({"vertical"}))
    found = bounds.nesting_problems(lane(test_timeout=1800, deadline=2400, job_min=45, lane="vertical"), [chat])
    assert found and "bound vertical.chat (1800s) is not below --test-timeout 1800s" in found[0]
    inner = bounds.Bound("inner", 50.0, "outer")
    outer = bounds.Bound("outer", 40.0)
    assert any("not below its enclosing bound outer" in p for p in bounds.nesting_problems(lane(), [inner, outer]))


def test_a_bounded_wait_names_its_bound_and_records_how_it_ended():
    flight_recorder.clear()
    with pytest.raises(bounds.BoundExpired, match="bound test.never"):
        bounds.bounded_wait("test.never", lambda: False, seconds=0.2, poll_s=0.01)
    assert bounds.bounded_wait("test.soon", lambda: "yes", seconds=1) == "yes"
    assert bounds.bounded_wait("test.gone", lambda: False, seconds=5, gone=lambda: True) is None
    ended = [(e["name"], e["ended"]) for e in flight_recorder.snapshot() if e["kind"] == "wait"]
    assert ended == [("test.never", "timeout"), ("test.soon", "ok"), ("test.gone", "gone")]
    flight_recorder.clear()


def test_a_workflow_loop_repeats_its_pytest_and_folded_commands_are_parsed(tmp_path):
    wf = tmp_path / "w.yml"
    wf.write_text("""jobs:
  a:
    timeout-minutes: 60
    steps:
      - run: >-
          python -m pytest -q --lane fast --test-timeout 600
          --session-deadline 900 --hang-dir "${{ runner.temp }}/h"
      - shell: bash
        run: |
          for i in $(seq 1 10); do
            python -m pytest -q --lane serial --test-timeout 240 \\
              --session-deadline 270 || exit 1
          done
""", encoding="utf-8")
    found = bounds.workflow_lanes(tmp_path)
    assert [(x.lane, x.test_timeout_s, x.deadline_s, x.repeats) for x in found] == [
        ("fast", 600, 900, 1), ("serial", 240, 270, 10)]
    assert found[0].hang_dir == "X/h"


@pytest.mark.skipif(not IS_WINDOWS, reason="the job object is Windows'; Linux's set is the subreaper and start times, "
                                           "tested above with a synthetic table")
def test_a_session_job_lists_exactly_its_members_and_refuses_breakaway():
    code = ("import os, subprocess, sys, time\n"
            f"sys.path.insert(0, {str(Path(proctree.__file__).parent)!r})\n"
            "import proctree\n"
            "job = proctree.Job('aew-test-' + str(os.getpid()))\n"
            "job.assign_self()\n"
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], creationflags=0x08000000)\n"
            "try:\n"
            "    subprocess.Popen([sys.executable, '-c', 'pass'], creationflags=0x08000000 | 0x01000000)\n"
            "    print('breakaway allowed')\n"
            "except OSError:\n"
            "    print('breakaway refused')\n"
            "print('members', sorted(job.pids()), 'mine', os.getpid(), c.pid)\n"
            "c.kill()\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    assert "breakaway refused" in out.stdout, out.stdout + out.stderr
    line = next(x for x in out.stdout.splitlines() if x.startswith("members"))
    mine = line.split("mine")[1].split()
    assert all(m in line.split("mine")[0] for m in mine), line


def test_a_job_that_runs_pytest_without_its_absolute_deadline_is_named(tmp_path):
    """Review of #217, M1: the pin names a job whose sessions have no AEW_JOB_DEADLINE, one that sets it after its
    first pytest step, and one whose value does not match its timeout."""
    good = 'echo "AEW_JOB_DEADLINE=$(( $(date +%s) + 960 ))" >> "$GITHUB_ENV"'
    (tmp_path / "w.yml").write_text(f"""jobs:
  none:
    timeout-minutes: 20
    steps:
      - run: python -m pytest -q
  late:
    timeout-minutes: 20
    steps:
      - run: python -m pytest -q
      - shell: bash
        run: '{good}'
  wrong:
    timeout-minutes: 30
    steps:
      - shell: bash
        run: '{good}'
      - run: python -m pytest -q
  right:
    timeout-minutes: 20
    steps:
      - shell: bash
        run: '{good}'
      - run: python -m pytest -q
""", encoding="utf-8")
    found = bounds.job_deadline_problems(tmp_path)
    assert [p.split(":")[0] for p in found] == ["w.yml none", "w.yml late", "w.yml wrong"], found


def test_a_helper_childs_native_crash_names_itself(tmp_path):
    """Review of #217, m5: a child's fatal-error dump (childdiag's ``fatal-<pid>.txt``) is named in the failure, so the
    known faulthandler residual reads as itself, never as an unexplained failure."""
    import autopsy

    assert autopsy.native_crashes(tmp_path) == ""
    (tmp_path / "fatal-41.txt").write_text("", encoding="utf-8")  # armed, nothing happened
    (tmp_path / "fatal-42.txt").write_text("Windows fatal exception: access violation\n\nThread 0x1 ...\n",
                                           encoding="utf-8")
    assert autopsy.native_crashes(tmp_path) == ("fatal-42.txt: Windows fatal exception: access violation "
                                                "(see the file for every thread's stack)")


LINUX_ONLY = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="the session's subreaper and its reaper are Linux's; Windows uses the job")


def _status_with_a_reap_in_the_record_window(own) -> tuple[int, int]:
    """Create a child through ``own``'s wrapper that exits at once, and run a reaper pass while the child is a zombie
    and not yet recorded (the seam, ordered by events). Returns its ``wait()`` status and how many the pass reaped."""
    import threading
    import types

    import session_deadline as sd

    fake = types.SimpleNamespace(spawn=lambda: subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"]))
    own._wrap(fake, "spawn", lambda proc: proc.pid)
    reaper = sd.Reaper(own)
    passed = threading.Event()

    def seam(pid):
        bounds.bounded_wait("test.child_is_a_zombie", lambda: (proctree.linux_state(pid) or ("",))[0] == "Z",
                            seconds=30)
        threading.Thread(target=lambda: (reaper.poll(), passed.set()), daemon=True).start()
        passed.wait(2)  # unlocked: the pass reaps here; locked: it waits for the recording, after this seam

    own.seam = seam
    proc = fake.spawn()
    status = proc.wait(30)
    passed.wait(30)
    return status, reaper.reaped


@LINUX_ONLY
def test_a_child_that_exits_before_it_is_recorded_keeps_its_exit_status():
    """Review of #217, F1: a child that ends between its creating call's return and its recording was reaped by the
    session's reaper, and ``wait()`` then said 0. Creation and recording are now one step for the reaper (its lock).
    Differential, in one test: without the lock the same sequence loses the status."""
    import contextlib

    import session_deadline as sd

    assert _status_with_a_reap_in_the_record_window(sd.OwnChildren()) == (3, 0)
    unlocked = sd.OwnChildren()
    unlocked.lock = contextlib.nullcontext()  # the earlier code: nothing holds the reaper off
    status, reaped = _status_with_a_reap_in_the_record_window(unlocked)
    assert reaped >= 1 and status != 3, (status, reaped)


@LINUX_ONLY
def test_the_reaper_refuses_to_start_where_it_cannot_record_this_processs_children(monkeypatch):
    """Review of #217, F2: a Python whose ``subprocess`` path is not where the wrapper looks makes the session refuse,
    loudly and before wrapping anything, instead of reaping every child a test starts."""
    import session_deadline as sd

    fork = os.fork
    monkeypatch.delattr(subprocess, "_fork_exec")
    with pytest.raises(RuntimeError, match="subprocess._fork_exec not found"):
        sd.OwnChildren().install()
    assert os.fork is fork  # nothing was wrapped
