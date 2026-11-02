"""The register of weaker contexts (G3 addendum 7, ruling 2; register E112), with the designer's ruling of 2026-11-01
on an entry's end: no entry ends while any process of its context may live. Each check plants its failure. The scan is
given as data (``Scan``/``Proc``), so these run on every platform; a test of the real ``/proc`` is Linux's."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from aew.errors import ContainmentUnavailable
from aew.harness import containment, procs
from aew.harness import weaker_register as W

REPO = Path(__file__).resolve().parents[2]
WEAK = containment.label(contained=False, reason="planted")
OWN = (os.getpid(), procs.start_id(os.getpid()))


@pytest.fixture
def reg(tmp_path, monkeypatch):
    """An empty register of the test's own, with no scan unless a test gives one."""
    monkeypatch.setattr(W, "ROOT_OVERRIDE", tmp_path / "weaker-contexts")
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: None)
    monkeypatch.setattr(W, "_now_ticks", lambda: ("boot-1", 1000))
    return tmp_path / "weaker-contexts"


def entry(**kw):
    return W.enter(**{"kind": "worker_run", "label": WEAK, "ownership": "subreaper", **kw})


def runs_of(tmp_path: Path) -> tuple[Path, Path]:
    """A project's AEW root and its runs directory, where a marker may name a record (#321 review, F2)."""
    aew = tmp_path / "repo" / ".aew"
    return aew, aew / "local" / "harness" / "runs"


def record(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def scan_of(*ps: W.Proc) -> W.Scan:
    return W.Scan(procs=list(ps), boot="boot-1", now_ticks=5000)


def later(s: float) -> float:
    return time.time() + s


# --------------------------------------------------------------------------------------------- what is weaker

@pytest.mark.parametrize("label, weaker", [
    ({"filesystem": "os_readonly_roots", "network": {"mode": "proxy_only"}, "self_test": {"ok": True}}, False),
    ({"filesystem": "os_readonly_roots", "network": {"mode": "isolated"}, "self_test": {"ok": True}}, False),
    ({"filesystem": "os_readonly_roots", "network": {"mode": "shared"}, "self_test": {"ok": True}}, True),
    ({"filesystem": "os_readonly_roots", "network": {"mode": "proxy_only"}}, True),
    ({"filesystem": "os_readonly_roots", "network": {"mode": "proxy_only"}, "self_test": {"ok": False}}, True),
    ({"filesystem": "workdir_separation_only", "network": {"mode": "proxy_only"}, "self_test": {"ok": True}}, True),
    (None, True),
])
def test_only_a_sandbox_on_a_network_of_its_own_with_a_passing_self_test_is_not_weaker(label, weaker):
    assert containment.weaker(label) is weaker


def test_a_contained_launch_writes_nothing(reg):
    label = {"filesystem": "os_readonly_roots", "network": {"mode": "proxy_only"}, "self_test": {"ok": True},
             "process_ownership": "pid_namespace"}
    assert W.enter_if_weaker(label, kind="worker_run", ownership="pid_namespace") is None
    assert not reg.exists()


# ------------------------------------------------------------------------------------------- writing and ending

def test_an_entry_is_live_while_its_owner_runs_and_ends_for_the_window_after_a_clean_end(reg):
    e = entry(project="/p", directory="/p/run", marker="/p/run/label.json")
    saved = json.loads(e.path.read_text(encoding="utf-8"))
    assert saved["owner"] == {"pid": OWN[0], "start_id": OWN[1]} and saved["kind"] == "worker_run"
    assert saved["label"] == WEAK and saved["marker"] == "/p/run/label.json"
    assert [x["why"] for x in W.read().live] == ["running"]
    e.started()
    e.end([])
    reading = W.read()
    assert reading.live == [] and [x["id"] for x in reading.recent] == [e.id] and not reading.clear
    assert W.read(now=later(W.WINDOW_S + 1)).clear


def test_an_entry_whose_context_started_nothing_ends_clean_at_once(reg):
    e = entry(ownership="process_group")
    e.end(None)  # an unknown outcome, but nothing ever started
    assert json.loads(e.path.read_text())["outcome"] == "clean"


def test_a_survivors_outcome_keeps_the_entry_live_until_each_is_proven_ended(reg, monkeypatch):
    e = entry()
    e.started()
    monkeypatch.setattr(procs, "same_process", lambda pid, sid: pid == 4242)
    e.end([(4242, "linux:boot-1:77")])
    assert json.loads(e.path.read_text())["outcome"] == "survivors"
    assert [x["why"] for x in W.read().live] == ["survivors still running: 4242"]
    monkeypatch.setattr(procs, "same_process", lambda pid, sid: False)  # the survivor ended
    assert W.read().live, "an end nobody recorded holds until a sweep proves it"
    W.sweep()
    assert W.read().live == [] and W.read().recent


def test_a_survivor_the_reaper_could_not_name_is_never_proven_ended(reg):
    e = entry()
    e.started()
    e.end([(0, None)])
    assert json.loads(e.path.read_text())["outcome"] == "survivors" and W.read().live


def test_a_killed_owner_leaves_its_context_live_until_a_clean_scan_or_a_boot(reg, monkeypatch):
    e = entry(owner_pid=99999, marker="/p/run.json")  # an owner that records nothing more
    monkeypatch.setattr(procs, "same_process", lambda pid, sid: False)
    assert [x["why"] for x in W.read().live][0].startswith("unowned")
    child = W.Proc(pid=5, start_id="linux:boot-1:3000", ticks=3000, env={W.MARKER: "/p/run.json"}, cmdline=("x",))
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(child))
    W.sweep()
    assert W.read().live, "a process carrying its marker still runs"
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of())
    W.sweep()
    assert W.read().live == [] and [x["id"] for x in W.read().recent] == [e.id]


def test_a_new_boot_ends_an_unowned_context(reg, monkeypatch):
    entry(owner_pid=99999)
    monkeypatch.setattr(procs, "same_process", lambda pid, sid: False)
    monkeypatch.setattr(W, "_now_ticks", lambda: ("boot-2", 10))  # 10 ticks since the new boot
    reading = W.read()
    assert reading.live == [] and [x["why"] for x in reading.recent] == ["ended by a reboot"]


def test_a_pid_reused_with_another_start_id_is_not_the_owner(reg):
    entry(owner_pid=os.getpid())
    path = next(p for p in reg.glob("worker_run-*.json"))
    data = json.loads(path.read_text())
    data["owner"]["start_id"] = "linux:another-boot:1" if sys.platform != "win32" else "win:1"
    path.write_text(json.dumps(data))
    assert [x["why"] for x in W.read().live][0].startswith("unowned"), "this pid is another process now"


# ---------------------------------------------------- the designer's ruling of 2026-11-01: (a), (c), and hosts

def test_a_bare_process_group_does_not_end_its_entry_while_a_detached_child_carries_its_marker(reg, monkeypatch):
    """(a): a child that started a session of its own left the group; only a scan finding none of it ends the entry."""
    e = entry(ownership="process_group", marker="/p/run.json")
    e.started()
    setsid = W.Proc(pid=6, start_id="linux:boot-1:2000", ticks=2000, env={W.MARKER: "/p/run.json"}, cmdline=("x",))
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(setsid))
    e.end([])
    data = json.loads(e.path.read_text())
    assert data["outcome"] == "unowned" and data["cleared_epoch"] is None and W.read().live
    assert "6 carries its marker" in data["reason"]


def test_a_clean_outcome_does_not_end_the_entry_while_a_process_carries_its_marker(reg, monkeypatch):
    """(c): the owner held the whole tree and reports no survivors, yet a marked process lives: not ended."""
    e = entry(ownership="subreaper", marker="/p/run.json")
    e.started()
    marked = W.Proc(pid=7, start_id="linux:boot-1:2000", ticks=2000, env={W.MARKER: "/p/run.json"}, cmdline=("x",))
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(marked))
    e.end([])
    assert json.loads(e.path.read_text())["outcome"] == "unowned" and W.read().live
    e2 = entry(ownership="subreaper", marker="/p/other.json")
    e2.started()
    e2.end([])  # nothing carries its marker: ended
    assert json.loads(e2.path.read_text())["outcome"] == "clean"


def test_a_forged_aew_command_line_makes_no_host(reg, monkeypatch, tmp_path):
    """A host is decided by identity, never by its command line: an unreadable process naming a real run directory is
    a host only when its start id is the one that run's record names."""
    aew, runs = runs_of(tmp_path)
    supervisor = {"supervisor_pid": 8, "supervisor_start_id": "linux:boot-1:9000"}
    run_dir = record(runs / "R-1" / "run.json", supervisor).parent
    e = entry(ownership="subreaper", marker="/p/run.json", aew_root=aew)
    e.started()
    argv = ("python", "-m", "aew.harness.supervisor", "--run-dir", str(run_dir))
    forged = W.Proc(pid=9, start_id="linux:boot-1:4000", ticks=4000, env=None, cmdline=argv)
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(forged))
    e.end([])
    data = json.loads(e.path.read_text())
    assert data["outcome"] == "unowned" and "9 cannot be read" in data["reason"]
    real = W.Proc(pid=8, start_id="linux:boot-1:9000", ticks=9000, env=None, cmdline=argv)
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(real))
    e2 = entry(ownership="subreaper", marker="/p/two.json", aew_root=aew)
    e2.started()
    e2.end([])
    assert json.loads(e2.path.read_text())["outcome"] == "clean", "the record's own supervisor is a host"


def test_an_unreadable_process_older_than_the_entry_does_not_block_its_end(reg, monkeypatch):
    agent = W.Proc(pid=10, start_id="linux:boot-1:500", ticks=500, env=None, cmdline=("ssh-agent",))
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(agent))
    e = entry(ownership="subreaper")  # written at tick 1000
    e.started()
    e.end([])
    assert json.loads(e.path.read_text())["outcome"] == "clean"


def test_a_failed_scan_is_never_clean(reg, monkeypatch):
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: W.Scan(failed="/proc: permission denied"))
    e = entry()
    e.started()
    e.end([])
    assert json.loads(e.path.read_text())["outcome"] == "unowned" and W.read().live


def test_a_scan_that_raises_is_a_failed_scan_and_the_entry_ends_unowned(reg, monkeypatch):
    """`Entry.end` never raises (#321 review, F2): any failure of its scan is a failed scan, unowned, never clean."""
    def broken(proc=None, uid=None):
        raise RecursionError("maximum recursion depth exceeded")

    e = entry()
    e.started()
    monkeypatch.setattr(W, "scan", broken)
    e.end([])
    data = json.loads(e.path.read_text())
    assert data["outcome"] == "unowned" and "the scan failed: RecursionError" in data["reason"] and W.read().live


def _held_by_a_stranger(monkeypatch, tmp_path, marker_of_readable: Path) -> W.Entry:
    """An entry of a project whose end an unreadable non-host process started after it blocks, and a readable process
    whose marker names ``marker_of_readable``: a file that says the stranger is a host."""
    aew, _ = runs_of(tmp_path)
    stranger = W.Proc(pid=31, start_id="linux:boot-1:4000", ticks=4000, env=None, cmdline=("x",))
    readable = W.Proc(pid=32, start_id="linux:boot-1:4100", ticks=4100, env={W.MARKER: str(marker_of_readable)},
                      cmdline=("y",))
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(stranger, readable))
    e = entry(ownership="subreaper", marker="/p/own.json", aew_root=aew)
    e.started()
    return e


def test_a_marker_is_followed_only_to_a_record_aew_wrote_in_a_project_an_entry_names(reg, monkeypatch, tmp_path):
    """#321 review, F2, scenario A: a process's environment chooses its marker, so a file anywhere else (a
    workspace's look-alike of a run directory included) that names another process as a host makes no host. The same
    record under the entry's own project's runs directory does."""
    claim = {"session_start_id": "linux:boot-1:4000"}
    aew, runs = runs_of(tmp_path)
    for forged in (record(tmp_path / "forged.json", claim),
                   record(tmp_path / "ws" / ".aew" / "local" / "harness" / "runs" / "R-9" / "label.json", claim)):
        e = _held_by_a_stranger(monkeypatch, tmp_path, forged)
        e.end([])
        assert json.loads(e.path.read_text())["outcome"] == "unowned", forged
    e = _held_by_a_stranger(monkeypatch, tmp_path, record(runs / "lead-1" / "label.json", claim))
    e.end([])
    assert json.loads(e.path.read_text())["outcome"] == "clean", "a record AEW wrote names its host"


def test_a_marker_record_past_the_parsers_depth_or_the_bound_is_no_record_and_the_end_never_raises(reg, monkeypatch,
                                                                                                tmp_path):
    """#321 review, F2, scenario B and the size cap: nesting past the parser's depth, or a file past
    ``runlog.MAX_RECORD_BYTES``, is no record: it names no host, and the end records its outcome."""
    from aew.harness import runlog

    _, runs = runs_of(tmp_path)
    deep = runs / "lead-1" / "label.json"
    deep.parent.mkdir(parents=True)
    deep.write_text("[" * 200_000)
    e = _held_by_a_stranger(monkeypatch, tmp_path, deep)
    e.end([])
    assert json.loads(e.path.read_text())["outcome"] == "unowned"
    big = record(runs / "lead-2" / "label.json", {"session_start_id": "linux:boot-1:4000", "pad": "x" * 64})
    monkeypatch.setattr(runlog, "MAX_RECORD_BYTES", 32)
    e = _held_by_a_stranger(monkeypatch, tmp_path, big)
    e.end([])
    assert json.loads(e.path.read_text())["outcome"] == "unowned", "a record past the bound names no host"
    W.sweep()  # nor does the sweep raise on either


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="a FIFO is POSIX's")
def test_a_marker_that_names_a_fifo_never_blocks_the_end(reg, monkeypatch, tmp_path):
    """#321 review, F2, scenario C: a FIFO in a run directory is opened without blocking and refused as no file."""
    import threading

    _, runs = runs_of(tmp_path)
    fifo = runs / "lead-1" / "label.json"
    fifo.parent.mkdir(parents=True)
    os.mkfifo(fifo)
    e = _held_by_a_stranger(monkeypatch, tmp_path, fifo)
    done = threading.Event()
    worker = threading.Thread(target=lambda: (e.end([]), done.set()), daemon=True)
    worker.start()
    assert done.wait(10), "the end blocked on the FIFO"
    assert json.loads(e.path.read_text())["outcome"] == "unowned"


def test_the_sweep_leaves_a_survivors_entry_live_while_a_named_survivor_runs(reg, monkeypatch):
    """#321 review, F4: a clean marker scan never ends a context whose named survivor is still the process it was."""
    e = entry()
    e.started()
    monkeypatch.setattr(procs, "same_process", lambda pid, sid: pid == 4242)
    e.end([(4242, "linux:boot-1:77")])
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of())  # nothing carries its marker
    W.sweep()
    assert [x["why"] for x in W.read().live] == ["survivors still running: 4242"]


def test_a_survivor_with_no_start_id_holds_its_entry_until_a_new_boot(reg, monkeypatch):
    """#321 review, F4: a survivor the reaper could not name is never proven ended, by a scan or with none (Windows):
    the entry stays live through a sweep, and a new boot ends it."""
    e = entry()
    e.started()
    e.end([(0, None)])
    for scan in (lambda proc=None, uid=None: None, lambda proc=None, uid=None: scan_of()):
        monkeypatch.setattr(W, "scan", scan)
        W.sweep()
        assert [x["why"] for x in W.read().live] == ["survivors still running: unnamed"]
    monkeypatch.setattr(W, "_now_ticks", lambda: ("boot-2", 10))
    assert W.read().live == []


# ------------------------------------------------------------------------------- a failed write, and the creation

def test_on_linux_a_weaker_launch_whose_entry_cannot_be_written_is_refused(tmp_path, monkeypatch):
    (tmp_path / "not-a-dir").write_text("x")
    monkeypatch.setattr(W, "ROOT_OVERRIDE", tmp_path / "not-a-dir" / "weaker-contexts")
    monkeypatch.setattr(W, "enforced", lambda: True)
    with pytest.raises(ContainmentUnavailable) as refused:
        entry()
    assert refused.value.details["reason"] == W.UNWRITABLE
    assert refused.value.details["register"] == str(tmp_path / "not-a-dir" / "weaker-contexts")
    monkeypatch.setattr(W, "enforced", lambda: False)  # Windows: no G3, no containment; it runs
    assert entry().path is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc and /dev are Linux's")
def test_a_register_that_resolves_into_the_kernels_own_trees_is_refused(tmp_path, monkeypatch):
    """The standard containment case (#316): a listed path that is a symlink into /proc or /dev."""
    for target in ("/proc/self", "/dev/shm"):
        link = tmp_path / Path(target).name
        link.symlink_to(target)
        monkeypatch.setattr(W, "ROOT_OVERRIDE", link / "weaker-contexts")
        monkeypatch.setattr(W, "enforced", lambda: True)
        with pytest.raises(ContainmentUnavailable, match="inside the kernel's own trees"):
            entry()


def test_the_scan_reads_only_each_processs_stat_cmdline_and_environ(tmp_path, monkeypatch):
    """It never follows a process's root or cwd link into its sandbox's trees."""
    proc = tmp_path / "proc"
    (proc / "sys/kernel/random").mkdir(parents=True)
    (proc / "sys/kernel/random/boot_id").write_bytes(b"boot-1\n")
    (proc / "uptime").write_bytes(b"100.0 50.0\n")
    p = proc / "41"
    p.mkdir()
    (p / "stat").write_bytes(b"41 (a b) S 1 41 41 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 777 0 0\n")
    (p / "cmdline").write_bytes(b"python\0-c\0pass\0")
    (p / "environ").write_bytes(W.MARKER.encode() + b"=/r/label.json\0PATH=/bin\0")
    (p / "root").mkdir()
    (p / "root" / "secret").write_bytes(b"never read")
    read: list[str] = []
    real = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: read.append(self.name) or real(self))
    monkeypatch.setattr(os, "sysconf", lambda name: 100, raising=False)
    seen = W.scan(proc, uid=(p.stat().st_uid))
    assert set(read) <= {"boot_id", "uptime", "stat", "cmdline", "environ"}
    assert [(x.pid, x.ticks, x.env[W.MARKER], x.cmdline) for x in seen.procs] == [
        (41, 777, "/r/label.json", ("python", "-c", "pass"))]
    assert seen.procs[0].start_id == procs.linux_start_id("boot-1", 777)


def test_the_registers_creation_counts_as_a_weaker_context_that_ended_then(reg):
    e = entry()
    e.started()
    e.end([])
    created = json.loads((reg / W.CREATED).read_text())
    assert not W.read(now=later(W.WINDOW_S + 1) - 1).clear or created  # sanity: written
    assert not W.read(now=created["created_epoch"] + W.WINDOW_S - 1).clear  # inside the window from its creation
    assert W.read(now=created["created_epoch"] + W.WINDOW_S + 1).clear


def test_a_register_never_created_on_this_host_is_never_clear(reg):
    assert not W.read().clear and W.read().created_epoch is None


def test_a_context_already_running_at_the_creation_stays_live_until_it_ends(reg, monkeypatch, tmp_path):
    """A contained label exempts a context only where AEW wrote it, in the creating owner's project: the same label in
    a workspace exempts nothing (#321 review, F2)."""
    aew, runs = runs_of(tmp_path)
    shut = {"filesystem": "os_readonly_roots", "network": {"mode": "proxy_only"}, "self_test": {"ok": True}}
    weaker, contained = record(runs / "R-1" / "label.json", WEAK), record(runs / "R-2" / "label.json", shut)
    forged = record(tmp_path / "workspace" / ".aew" / "local" / "harness" / "runs" / "R-3" / "label.json", shut)
    running = [W.Proc(pid=11, start_id="s-11", ticks=1, env={W.MARKER: str(weaker)}, cmdline=("x",)),
               W.Proc(pid=12, start_id="s-12", ticks=1, env={W.MARKER: str(contained)}, cmdline=("y",)),
               W.Proc(pid=13, start_id="s-13", ticks=1, env={"AEW_RUN": "R-1"}, cmdline=("z",)),  # older code
               W.Proc(pid=14, start_id="s-14", ticks=1, env={"PATH": "/bin"}, cmdline=("gpg-agent",)),
               W.Proc(pid=15, start_id="s-15", ticks=1, env={W.MARKER: str(forged)}, cmdline=("w",))]
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(*running))
    alive = {"s-11", "s-13", "s-15"}
    monkeypatch.setattr(procs, "same_process", lambda pid, sid: sid in alive)
    entry(aew_root=aew).end([])  # the register's first creation on this host, by an owner of this project
    found = sorted(x["why"] for x in W.read().live if x["kind"] == "found_at_creation")
    assert found == ["running"] * 3, "a weaker context, one older code started and a forged label; not a contained one"
    alive.clear()
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of())
    W.sweep()
    assert [x for x in W.read().live if x["kind"] == "found_at_creation"] == []


def test_at_the_creation_an_unreadable_aew_process_no_record_names_counts_as_weaker(reg, monkeypatch, tmp_path):
    """The designer's ruling of 2026-11-01: an unreadable process with AEW's command line and no record naming it is
    counted; one a run record names by its start id is a host, a forged pointer to that record makes none, and an
    unreadable process that is not AEW's (ssh-agent) is not counted."""
    aew, runs = runs_of(tmp_path)
    run_dir = record(runs / "R-1" / "run.json", {"supervisor_start_id": "s-21", "containment": WEAK}).parent
    sup = ("python", "-m", "aew.harness.supervisor", "--run-dir", str(run_dir))
    running = [W.Proc(pid=20, start_id="s-20", ticks=1, env=None, cmdline=("/venv/bin/aew", "work", "list")),
               W.Proc(pid=21, start_id="s-21", ticks=1, env=None, cmdline=sup),  # the record's own supervisor
               W.Proc(pid=22, start_id="s-22", ticks=1, env=None, cmdline=sup),  # a forged pointer to that record
               W.Proc(pid=23, start_id="s-23", ticks=1, env=None, cmdline=("ssh-agent", "-s"))]
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(*running))
    monkeypatch.setattr(procs, "same_process", lambda pid, sid: True)
    entry(aew_root=aew).end([])  # the creation, by an owner of the record's project
    found = json.loads((reg / W.CREATED).read_text())["found"]
    owners = sorted(json.loads((reg / f"{i}.json").read_text())["owner"]["pid"] for i in found)
    assert owners == [20, 22] and len([x for x in W.read().live if x["kind"] == "found_at_creation"]) == 2


def test_the_owner_that_creates_the_register_is_a_host_not_a_context_found_running(reg, monkeypatch):
    """#321 review, N1: the first weaker Lead on a host is hardened, so its own process is unreadable, with AEW's
    command line, and its entry is not yet written at the creation: its start id makes it a host, and only its own
    entry counts it."""
    me = W.Proc(pid=OWN[0], start_id=OWN[1], ticks=1, env=None, cmdline=("/venv/bin/aew", "lead", "session"))
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: scan_of(me))
    entry(kind="lead_session")
    assert json.loads((reg / W.CREATED).read_text())["found"] == []


def test_an_unreadable_entry_is_marked_never_dropped(reg):
    entry().end([])
    (reg / "worker_run-broken.json").write_text("{not json")
    reading = W.read()
    assert reading.unreadable == ["worker_run-broken.json"] and not reading.clear


def test_an_ended_entry_is_kept_for_the_window_then_pruned(reg):
    e = entry()
    e.started()
    e.end([])
    W.sweep(now=later(W.WINDOW_S - 5))
    assert e.path.exists()
    W.sweep(now=later(W.WINDOW_S + 5))
    assert not e.path.exists()


def test_the_window_is_g3s_tripwire_restated_with_its_source():
    """15 minutes, G3-06's tripwire: the longest a consent stays valid (read as text: the G3 package needs
    ``cryptography``)."""
    deployment = (REPO / "g3/aew_g3/deployment.py").read_text(encoding="utf-8")
    assert '"consent_validity_minutes": ("max", 15)' in deployment
    assert W.WINDOW_S == 15 * 60


def test_the_register_lives_beside_the_capability_registers_host_state(monkeypatch):
    from aew import hoststate
    from aew.capability import store

    monkeypatch.setattr(W, "ROOT_OVERRIDE", None)
    monkeypatch.setattr(store, "ROOT_OVERRIDE", None)
    assert W.root().parent == store.root().parent == hoststate.root()
