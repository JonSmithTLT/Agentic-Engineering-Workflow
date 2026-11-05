"""What a contained context gets of the capability register (STG-15, CAP-1 PR 2; CAPR-04, CAPR-12; the designer's CAP-1
ruling 1): one lookup that never misses, in real sandboxes.

Most tests use a stand-in provider, ``fake``, shipped with ripgrep's shape. The context kinds at the end go through
each one's real route, in a child ``aew`` that has AEW's real shipped records and no payload (the session's fetch is
off), so ``rg`` resolves to the context's own entry whatever the host has. The rows with a real OpenCode are
``tests/live/test_capability_q08_live.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_planned_ticket, sample_project, to_commit_ready
from capability_stand_in import (
    _archive,
    _import,
    _plant_host_copy,
    _record,
    make_register,
    register_holding_a_failed_fetch,
)
from fake_harness import POLICY, HarnessLab
from host_env import GUARDED, clean_launching_env

from aew import doctor
from aew.capability import ops, records, status, store
from aew.capability import payload as P
from aew.engine.api import Engine
from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import layout as L
from aew.policy import checks as checks_module
from aew.util import dump_yaml, load_yaml

pytestmark = [pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                                 reason="Linux bubblewrap containment: Windows has no contained context"),
              GUARDED]

ROLES = [("implementer", "ticket"), ("lead", "project"), ("reviewer", "ticket"), ("verifier", "integration"),
         ("investigator", "ticket"), ("researcher", "ticket"), ("planner", "ticket"), ("frontier_advisor", "ticket")]


def test_the_roles_here_are_every_role_a_layout_has():
    assert {r for r, _ in ROLES} == set(L.WORKSPACE_ACCESS)


class World:
    """A project, a register of its own with the stand-in as AEW's one shipped record, and ways into a sandbox."""

    def __init__(self, tmp_path: Path, monkeypatch: Any) -> None:
        self.reg = make_register(tmp_path, monkeypatch)
        self.monkeypatch = monkeypatch
        self.tmp = tmp_path
        self.project = tmp_path / "project"
        (self.project / ".aew").mkdir(parents=True)
        self.worktree = tmp_path / "worktree"  # a worker's workspace is a worktree of its own, never the project
        self.worktree.mkdir()
        for repo in (self.project, self.worktree):
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        self.runs = tmp_path / "runs"
        self.runs.mkdir()
        self.count = 0
        # A PATH with no copy of the stand-in on it, whatever the host has, and a home of the test's own
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        (tmp_path / "home").mkdir()
        clean_launching_env(monkeypatch, tmp_path / "home")

    def layout(self, role: str = "reviewer", scope: str = "ticket", **kw: Any) -> C.Layout:
        self.count += 1
        run = self.runs / f"R-{self.count}"
        return C.for_run(role=role, scope=scope, workspace=self._workspace(role), run_dir=run,
                         scratch=str(run / "scratch"), bridge_dir=None, policy={}, project=str(self.project),
                         runs=str(self.runs), **kw)

    def _workspace(self, role: str) -> str:
        return str(self.project if role == "lead" else self.worktree)

    def establish(self, role: str = "reviewer", scope: str = "ticket") -> tuple[C.Layout, dict[str, Any]]:
        self.count += 1
        run = self.runs / f"R-{self.count}"
        layout, label = C.establish(role=role, scope=scope, workspace=self._workspace(role), run_dir=run,
                                    scratch=str(run / "scratch"), bridge_dir=None,
                                    policy={"containment": {"network": {"mode": "isolated"}}},
                                    project=str(self.project))
        assert layout is not None
        return layout, label

    def sh(self, layout: C.Layout, script: str, *, path: str = "/usr/bin:/bin") -> subprocess.CompletedProcess[str]:
        tree = procs.ProcessTree(layout=layout)
        try:
            proc = tree.spawn(["sh", "-c", script], cwd=self._workspace(layout.role), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                              env={"PATH": path, "LANG": "C.UTF-8", **layout.env})
            out, err = proc.communicate(timeout=60)
            return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        finally:
            tree.close()

    @property
    def pinned(self) -> dict[str, Any]:
        return self.reg["shipped"]["fake"]["payloads"][records.platform_key()]

    @property
    def payload(self) -> Path:
        return P.path_of("fake", "fake", self.pinned)

    def status(self) -> dict[str, Any]:
        return next(c for c in ops.listing()["capabilities"] if c["id"] == "FAKE_SEARCH")

    def state(self) -> dict[str, Any]:
        return store.read()

    def tamper(self) -> None:
        os.chmod(self.payload, 0o700)
        data = bytearray(self.payload.read_bytes())
        data[-2] ^= 1
        self.payload.write_bytes(bytes(data))
        os.chmod(self.payload, 0o500)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


# ------------------------------------------------------------------------------------- what serves (Q08's table)


@pytest.mark.parametrize(("role", "scope"), ROLES, ids=[r for r, _ in ROLES])
def test_in_every_role_aews_pinned_copy_comes_first_on_path_and_no_write_reaches_it(world, role, scope):
    """CAPR-04, CAPR-Q02: read-only, whatever the role: the entry, the payload and the register all refuse a write."""
    _import(world.reg)
    layout, label = world.establish(role, scope)
    assert label["self_test"]["ok"] is True
    entry = Path(layout.tools_first) / "fake"
    before = world.payload.read_bytes()
    done = world.sh(layout, f"""
        [ "$(command -v fake)" = "{entry}" ] || {{ echo "found $(command -v fake)"; exit 90; }}
        [ "${{PATH%%:*}}" = "{layout.tools_first}" ] || {{ echo "PATH=$PATH"; exit 91; }}
        fake --version | grep -q 'fake 1.0' || exit 92
        for target in "{layout.tools_first}/new" "{entry}" "{world.payload}" "{world.payload.parent}/new" \
                      "{store.root()}/register.json" "{store.root()}/new"; do
          if ( : >> "$target" ) 2>/dev/null; then echo "wrote $target"; exit 93; fi
        done""")
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert world.payload.read_bytes() == before
    assert label["self_test"]["tools"]["fake"]["served"] == status.AEW_COPY


def test_a_writable_bind_of_the_payload_fails_the_launch_self_test(world):
    """A2's proof: the self-test itself finds a register a sandbox could write, so such a launch never starts."""
    from aew.harness.containment import probe

    _import(world.reg)
    good = world.layout()
    assert str(world.reg["root"]) in good.protected
    broken = L.replace(good, tool_binds=(), writable=(*good.writable, str(world.reg["root"])))
    test = probe.self_test(broken, sentinel_dir=world.tmp, sibling_dir=world.tmp)
    assert test["ok"] is False and str(world.reg["root"]) in test["reason"]


def test_with_no_payload_and_a_host_copy_the_host_serves_named_as_unpinned_beside_the_cause(world):
    """CAPR-04: the first row. It serves on its own check, and the status names it, unpinned, with AEW's cause."""
    host = _plant_host_copy(world.reg, world.monkeypatch)
    layout, label = world.establish()
    assert label["self_test"]["tools"]["fake"]["served"] == status.HOST_COPY
    entry = Path(layout.tools_first) / "fake"
    assert entry.resolve() == host.resolve()
    done = world.sh(layout, 'command -v fake; fake --version')
    assert done.stdout.splitlines() == [str(entry), "fake 1.0"], done
    cap = world.status()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.HOST_COPY
    assert cap["path"] == str(host.resolve()) and cap["pinned"] is False
    assert status.UNPINNED in cap["limitations"]
    assert "AEW's copy: its pinned payload is not on this host" in cap["cause"]
    detail = next(d for n, _, d in ops.doctor_checks() if n == "capability:FAKE_SEARCH")
    assert "unpinned" in detail and str(host.resolve()) in detail


def test_with_no_copy_at_all_the_stub_fails_with_the_cause_and_the_lookup_still_ends_there(world):
    """Ruling 1's row that matters most, in the sandbox: a lookup finds it, its run fails with the cause, nothing is
    served, and the launch goes on (CAPR-12). That OpenCode then does not download is the live row's."""
    layout, label = world.establish()
    assert label["self_test"]["ok"] is True  # a provider never fails a launch
    assert label["self_test"]["tools"]["fake"]["served"] is None
    entry = Path(layout.tools_first) / "fake"
    done = world.sh(layout, 'command -v fake; fake --search anything; echo "exit $?"')
    assert done.stdout.splitlines() == [str(entry), "exit 127"], done
    assert "its pinned payload is not on this host" in done.stderr and "aew capability check" in done.stderr
    assert "Meanwhile, search with `grep -rn` or `find`" in done.stderr  # the agent's own step (review of #330, m5)
    cap = world.status()
    assert cap["observed_status"] == status.UNAVAILABLE and "not on this host" in cap["cause"]
    assert "aew capability check" in cap["fix"]


def test_a_refused_payload_never_serves_and_a_host_copy_then_does_named_unpinned(world):
    """CAPR-Q01, CAPR-04, A5: one byte off its pin; checked at the launch, not only at `aew capability check`."""
    _import(world.reg)
    world.tamper()
    layout, label = world.establish()
    assert label["self_test"]["tools"]["fake"]["served"] is None
    done = world.sh(layout, 'fake --version; echo "exit $?"')
    assert done.stdout.splitlines() == ["exit 127"], done
    assert "does not match its pin" in done.stderr
    assert world.status()["observed_status"] == status.REFUSED
    host = _plant_host_copy(world.reg, world.monkeypatch)
    layout, label = world.establish()
    assert label["self_test"]["tools"]["fake"]["path"] == str(host.resolve())
    cap = world.status()
    assert cap["copy"] == status.HOST_COPY and status.UNPINNED in cap["limitations"]
    assert "does not match its pin" in cap["cause"]


def test_with_host_copies_off_a_host_copy_never_serves(world):
    """CAPR-04: the operator may turn them off."""
    from capability_stand_in import _principal

    host = _plant_host_copy(world.reg, world.monkeypatch)
    ops.apply(_principal(), ops.preview(ops.HOST_COPIES, {"on": False}))
    layout, label = world.establish()
    assert label["self_test"]["tools"]["fake"]["served"] is None
    done = world.sh(layout, 'fake --version; echo "exit $?"', path=f"{host.parent}:/usr/bin:/bin")
    assert done.stdout.splitlines() == ["exit 127"], done  # first on PATH, ahead of the host's own directory
    assert world.status()["observed_status"] == status.UNAVAILABLE


def test_a_host_copy_only_the_host_can_see_becomes_the_stub_never_a_dangling_link(world):
    """A7: read on the host this copy runs, and a sandbox's /tmp is its own, so it is not there. The check inside says
    so; a dangling link would be passed over by the harness's `which`, which is the download's way in."""
    directory = world.tmp / "host-only"
    directory.mkdir()
    exe = directory / "fake"
    exe.write_bytes(world.reg["body"])
    exe.chmod(0o755)
    world.monkeypatch.setenv("PATH", f"{directory}:/usr/bin:/bin")
    assert status.health(exe, world.reg["shipped"]["fake"], pinned=False)[0] is True  # on the host it passes
    layout, label = world.establish()
    tool = label["self_test"]["tools"]["fake"]
    assert tool["served"] is None and "could not start in the sandbox" in tool["cause"]
    entry = Path(layout.tools_first) / "fake"
    assert not entry.is_symlink() and os.access(entry, os.X_OK)
    done = world.sh(layout, 'command -v fake; fake --version; echo "exit $?"', path=f"{directory}:/usr/bin:/bin")
    assert done.stdout.splitlines() == [str(entry), "exit 127"], done
    assert "could not start in the sandbox" in done.stderr
    assert world.status()["observed_status"] != status.FUNCTIONAL_ONLY  # never read as usable from the host


def test_a_pinned_copy_that_fails_its_check_inside_does_not_serve_and_the_status_says_why(world, monkeypatch):
    """CAPR-Q04: a matching pin is not enough, the check decides (here its fixture query expects something else)."""
    shipped = world.reg["shipped"]["fake"]
    _import(world.reg)
    broken = {**shipped, "health": {**shipped["health"], "fixture": {**shipped["health"]["fixture"], "expect": "no"}}}
    monkeypatch.setattr(records, "shipped", lambda: {"fake": broken})
    layout, label = world.establish()
    tool = label["self_test"]["tools"]["fake"]
    assert tool["served"] is None and "its fixture query printed" in tool["cause"]
    assert world.sh(layout, 'fake --version; echo "exit $?"').stdout.splitlines() == ["exit 127"]
    cap = world.status()
    assert cap["observed_status"] == status.UNAVAILABLE and "its fixture query printed" in cap["cause"]


def test_a_hanging_provider_costs_its_budget_and_never_the_launch(world, monkeypatch):
    """CAPR-12: the probe's own time is what refuses a launch, and a tool cannot use it up."""
    from aew.harness.containment import probe

    assert probe.TOOLS_BUDGET_S < probe.TIMEOUT_S  # what makes this hold at its real size, without waiting for it
    body = b'#!/bin/sh\nexec sleep 600\n'
    archive = _archive(body, "fake-1.0/fake")
    shipped = {"fake": _record(body, archive)}
    monkeypatch.setattr(records, "shipped", lambda: shipped)
    world.reg["shipped"] = shipped
    monkeypatch.setattr(probe, "TOOLS_BUDGET_S", 1.0)
    P.install("fake", "fake", world.pinned, body)
    layout, label = world.establish()
    assert label["self_test"]["ok"] is True
    assert "time for tools" in label["self_test"]["tools"]["fake"]["cause"]
    assert world.sh(layout, 'fake --version; echo "exit $?"').stdout.splitlines() == ["exit 127"]


def test_a_register_nothing_can_read_leaves_the_lookup_ending_at_a_stub(world, monkeypatch):
    """CAPR-12: an unreadable register is a cause, never a miss and never a refused launch."""
    world.reg["root"].mkdir(parents=True, exist_ok=True)
    (world.reg["root"] / store.REGISTER).write_text("not json")
    layout, label = world.establish()
    assert label["self_test"]["ok"] is True
    done = world.sh(layout, 'fake --version; echo "exit $?"')
    assert done.stdout.splitlines() == ["exit 127"] and "is not JSON" in done.stderr, done


def test_a_refused_operator_record_keeps_its_lookup_at_a_stub_with_its_cause(world):
    state = store.empty()
    state["operator_records"]["fake"] = {"record": {"command": "fake", "path": "first"}, "base_digest": None}
    with store.locked():
        store.write(state)
    layout, _ = world.establish()
    done = world.sh(layout, 'fake --version; echo "exit $?"')
    assert done.stdout.splitlines() == ["exit 127"] and "its record is refused" in done.stderr, done


# ---------------------------------------------------------------------------------------------- PATH


def test_a_record_of_its_own_name_comes_last_so_the_project_keeps_the_hosts_tool_and_has_no_stub(world, monkeypatch):
    """CAPR-04, CAPR-X10; one mechanism for every record. PR 3's tools add records, not code."""
    shipped = world.reg["shipped"]["fake"]
    own = {**shipped, "path": "own_name"}
    monkeypatch.setattr(records, "shipped", lambda: {"fake": own})
    project_tool = world.tmp / "project-tools"
    project_tool.mkdir()
    (project_tool / "fake").write_text('#!/bin/sh\necho the host one\n')
    (project_tool / "fake").chmod(0o755)
    layout = world.layout()
    assert layout.tools_last is not None and layout.contained_path("/a:/b") == (
        f"{layout.tools_first}:/a:/b:{layout.tools_last}")
    assert not (Path(layout.tools_first) / "fake").exists()  # no stub: nothing looks it up unasked
    assert not (Path(layout.tools_last) / "fake").exists()  # and nothing to link
    _import({**world.reg, "shipped": {"fake": own}})
    layout, label = world.establish()
    assert label["self_test"]["tools"]["fake"]["served"] == status.AEW_COPY
    done = world.sh(layout, 'command -v fake')
    assert done.stdout.strip() == str(Path(layout.tools_last) / "fake"), done
    # A host's tool of that name, earlier on PATH, is what the project gets
    bindir = L.replace(layout, readonly=(*layout.readonly, str(project_tool)))
    done = world.sh(bindir, 'command -v fake; fake', path=f"{project_tool}:/usr/bin:/bin")
    assert done.stdout.splitlines() == [str(project_tool / "fake"), "the host one"], done


def test_the_contained_path_is_set_whichever_environment_the_caller_built():
    """One owner: a caller's PATH keeps its order behind the entries, and is not doubled when it already holds them."""
    layout = L.Layout(role="r", access="read", bwrap="/b", writable=(), readonly=(), tools_first="/t/first")
    assert layout.contained_path("/usr/bin:/bin") == "/t/first:/usr/bin:/bin"
    assert layout.contained_path("/t/first:/usr/bin") == "/t/first:/usr/bin"
    assert layout.contained_path("") == "/t/first"
    argv = L.bwrap_argv(layout, ["x"], path="/usr/bin")
    assert argv[argv.index("--setenv"):argv.index("--setenv") + 3] == ["--setenv", "PATH", "/t/first:/usr/bin"]
    assert "--setenv" not in L.bwrap_argv(L.replace(layout, tools_first=None), ["x"], path="/usr/bin")


def test_a_spawn_keeps_the_path_its_own_environment_gave_behind_the_entries(world):
    """N2's proof: the caller's environment decides the rest of PATH, not this process's."""
    layout = world.layout()
    done = world.sh(layout, 'printf "%s" "$PATH"', path="/custom/bin:/usr/bin:/bin")
    assert done.stdout == f"{layout.tools_first}:/custom/bin:/usr/bin:/bin", done


def test_a_context_with_no_sandbox_says_the_download_stays_reachable():
    """Windows, and a Linux run the policy allows to be weaker: no bind, and its label says so."""
    assert C.label(contained=False, reason="the policy")["register_tools"] == status.NOT_BOUND
    assert "download stays reachable" in status.NOT_BOUND


def test_a_probe_whose_tool_check_breaks_still_reports_and_the_launch_goes_on(world, monkeypatch):
    """CAPR-12: a spec the probe cannot use is reported as nothing for that tool, and serves nothing."""
    from aew.capability import bind

    monkeypatch.setattr(bind.Tool, "spec", lambda self: {"provider": self.provider, "broken": True})
    layout, label = world.establish()
    assert label["self_test"]["ok"] is True
    assert world.sh(layout, 'fake --version; echo "exit $?"').stdout.splitlines() == ["exit 127"]


def test_with_no_ripgrep_anywhere_doctor_names_it_with_the_fix_and_an_agents_run_works(tmp_path):
    """CAPR-Q06, CAPR-X06, by the real CLI and a real supervisor: a host with no `rg` (this PATH holds everything of
    the host's but that, as the VM has its own). ``test_doctor_names_a_missing_provider...`` plants one too."""
    farm = tmp_path / "no-rg-bin"
    farm.mkdir()
    for entry in os.scandir("/usr/bin"):
        if entry.name != "rg":
            (farm / entry.name).symlink_to(entry.path)
    sync = tmp_path / "sync"
    policy = {**POLICY, "containment": {"writable": [str(tmp_path / "fake-scripts"), str(sync)],
                                        "network": {"mode": "shared"}}}
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy)
    base = tmp_path / "data"
    register_holding_a_failed_fetch(base)
    bin_dir = os.path.dirname(sys.executable)
    env = {"XDG_DATA_HOME": str(base), "PATH": f"{bin_dir}:{farm}"}
    try:
        wid = create_planned_ticket(lab.project, tmp_path)
        lab.script("default", [{"do": "dump_env", "path": str(sync / "env.json")},
                               {"do": "touch", "path": str(sync / "ran")}])
        run = lab.lead("work", "assign", wid, "--launch", env=env)["launch"]["run"]
        lab.until(lambda: (sync / "ran").exists(), what="the agent's run, with no ripgrep anywhere")
        assert lab.record(run)["containment"]["self_test"]["tools"]["ripgrep"]["served"] is None
        doctor_rows = {c["check"]: c for c in lab.ok("doctor", "--json", env=env)["checks"]}
        row = doctor_rows["capability:EXACT_CODE_SEARCH"]
        assert row["status"] == "WARN" and "not on this host" in row["detail"]
        assert "aew capability check" in row["detail"] and doctor_rows["containment"]["status"] != "FAIL"
        assert "ripgrep" not in doctor_rows  # RG-1's own line is gone
    finally:
        lab.cleanup()


def test_a_process_inside_never_reads_the_contexts_own_entries_as_a_host_copy(world, monkeypatch, tmp_path):
    """Inside, `aew capability list` looks along a PATH that starts with the entries: a stub there is no host copy."""
    layout = world.layout()
    monkeypatch.setenv("PATH", f"{layout.tools_first}:/usr/bin:/bin")
    assert status.find_host_copy("fake") is None


# ---------------------------------------------------------------------------------------------- the fetch at a launch


class Network:
    """In place of the network, in process: what a fetch asks for, and what it gets."""

    def __init__(self, monkeypatch: Any, body: bytes | Exception) -> None:
        self.asked: list[str] = []
        self.body = body
        monkeypatch.setattr("urllib.request.urlopen", self.urlopen)
        monkeypatch.setattr(ops, "LAUNCH_FETCH", True)

    def urlopen(self, url: str, timeout: float = 0.0) -> Any:
        import io

        self.asked.append(url)
        if isinstance(self.body, Exception):
            raise self.body
        return io.BytesIO(self.body)


def test_a_fresh_host_has_the_base_tools_before_the_first_use_with_no_operator_step(world, monkeypatch):
    """CAPR-Q10, with a fixture's archive in place of the network: fetched, checked inside, recorded, serving."""
    net = Network(monkeypatch, world.reg["archive"])
    layout, label = world.establish()
    assert net.asked == [world.pinned["source"]]
    assert label["self_test"]["tools"]["fake"]["served"] == status.AEW_COPY
    cap = world.status()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["pinned"] is True
    assert cap["limitations"] == []  # checked in a sandbox, not on the host
    assert world.state()["checks"]["aew:fake"]["where"] == status.IN_SANDBOX
    world.establish()
    assert len(net.asked) == 1  # once: it is there now


def test_a_failed_fetch_never_stops_the_run_and_the_status_says_why(world, monkeypatch):
    """CAPR-12, A6: the launch goes on with the stub, the cause is the failure's, and an offline host pays once. The
    operator's `aew capability check` always tries."""
    net = Network(monkeypatch, OSError("no route to host"))
    layout, label = world.establish()
    assert label["self_test"]["ok"] is True
    cap = world.status()
    assert cap["observed_status"] == status.UNAVAILABLE and "no route to host" in cap["cause"]
    assert "no route to host" in world.sh(layout, "fake --version").stderr
    world.establish()
    assert len(net.asked) == 1  # not again at the next launch, within the retry time
    state = world.state()
    state["fetch_failures"][f"fake:{records.platform_key()}"]["at"] = "2020-01-01T00:00:00Z"
    with store.locked():
        store.write(state)
    world.establish()
    assert len(net.asked) == 2  # and again after it
    ops.check()
    assert len(net.asked) == 3


def test_a_fetched_archive_off_its_pin_is_refused_at_the_launch_and_not_fetched_again(world, monkeypatch):
    """CAPR-Q01 at the launch's fetch."""
    data = bytearray(world.reg["archive"])
    data[len(data) // 2] ^= 1
    net = Network(monkeypatch, bytes(data))
    layout, _ = world.establish()
    assert world.status()["observed_status"] == status.REFUSED and not world.payload.exists()
    assert world.sh(layout, 'fake --version; echo "exit $?"').stdout.splitlines() == ["exit 127"]
    world.establish()
    assert len(net.asked) == 1


def test_a_fetch_that_stalls_costs_a_launch_its_bound_and_no_more(world, monkeypatch, capsys):
    """CAPR-12: a socket that keeps answering slowly is bounded as a whole, and recorded as a failure. Behind a holder
    of the register's lock (the operator's `aew capability check`, mid-fetch), its record waits only the short wait and
    gives way, so the launch costs the two bounds `starting_limit_s` adds (review of #330, M1)."""
    import threading
    import time

    from aew.harness import supervisor

    release, held, holder_done = threading.Event(), threading.Event(), threading.Event()
    stall_s = 30.0
    net = Network(monkeypatch, b"")
    monkeypatch.setattr(ops.P, "fetch", lambda _p: release.wait(stall_s) and b"")
    monkeypatch.setattr(ops.P, "LAUNCH_FETCH_BOUND_S", 0.2)
    monkeypatch.setattr(store, "RECORD_WAIT_S", 0.5)
    monkeypatch.setattr(store, "LOCK_TIMEOUT_S", stall_s)

    def holder() -> None:
        with store.locked():
            held.set()
            holder_done.wait(stall_s)

    lock_holder = threading.Thread(target=holder, daemon=True)
    lock_holder.start()
    assert held.wait(10)
    started = time.monotonic()
    try:
        ops.fetch_at_launch()
        behind_holder = time.monotonic() - started
    finally:
        holder_done.set()
        lock_holder.join(10)
    assert behind_holder < 0.2 + 0.5 + 3.0, behind_holder  # the bound and the short wait, never the store's whole wait
    assert "fetching fake for this host's capability register (at most 0.2 s)" in capsys.readouterr().err
    assert supervisor.starting_limit_s(None) - supervisor.STARTING_MARGIN_S >= (
        ops.P.LAUNCH_FETCH_BOUND_S + 2 * store.RECORD_WAIT_S)  # what the deadline adds covers both waits
    started = time.monotonic()
    try:
        ops.fetch_at_launch()
        spent = time.monotonic() - started
        _, label = world.establish()
    finally:
        release.set()
    assert spent < stall_s / 2, spent  # it stopped waiting at its bound, well before the stalled fetch would have ended
    assert net.asked == [] and label["self_test"]["ok"] is True
    assert "did not finish within" in world.status()["cause"]


def test_a_register_under_a_host_mask_stays_out_and_its_pinned_copy_becomes_the_stub(world, monkeypatch):
    """The ADR's case (review of #330, m4): AEW's own pinned copy, present on the host in a register the layout masks
    whole. Binding it would re-open the mask, so it is not bound; the launch goes on, the check inside fails, the entry
    is the stub, and the status never reads it as usable."""
    from aew.harness.containment import probe

    _import(world.reg)
    register = os.path.realpath(store.root())
    masks = (*L.host_masks(), register)
    monkeypatch.setattr(L, "host_masks", lambda: masks)
    monkeypatch.setattr(probe, "host_masks", lambda: masks)
    layout, label = world.establish()
    assert label["self_test"]["ok"] is True  # never a refused launch (CAPR-12)
    assert register not in layout.tool_binds
    argv = L.bwrap_argv(layout, ["true"])
    assert not [i for i, a in enumerate(argv) if a == "--ro-bind-try" and argv[i + 1] == register], argv
    tool = label["self_test"]["tools"]["fake"]
    assert tool["served"] is None and tool["cause"], tool
    entry = Path(layout.tools_first) / "fake"
    assert not entry.is_symlink() and os.access(entry, os.X_OK)
    assert world.status()["observed_status"] != status.FUNCTIONAL_ONLY


def test_no_variable_turns_the_launchs_fetch_off(world, monkeypatch):
    """The Lead's condition: nothing an installed AEW reads disables it, and the test seam is in process only."""
    net = Network(monkeypatch, world.reg["archive"])
    for name in ("AEW_CAPABILITY_FETCH", "AEW_OFFLINE", "AEW_NO_FETCH"):
        monkeypatch.setenv(name, "off")
    world.establish()
    assert net.asked == [world.pinned["source"]]
    assert not [v for v in vars(ops).values() if isinstance(v, str) and v.startswith("AEW_")]


def test_a_tests_child_register_stays_off_the_network_and_never_reads_as_healthy(world, monkeypatch):
    """How a child `aew` stays off the network, in the status's own words."""
    net = Network(monkeypatch, world.reg["archive"])
    register_holding_a_failed_fetch(world.tmp / "base")
    monkeypatch.setattr(store, "ROOT_OVERRIDE", world.tmp / "base" / "aew" / "capability")
    world.establish()
    assert net.asked == []
    cap = world.status()
    assert cap["observed_status"] == status.UNAVAILABLE and "this child never fetches" in cap["cause"]


def test_the_status_says_when_a_launch_next_tries_a_failed_fetch_and_names_the_check(world, monkeypatch):
    """A failure the operator can act on: the time, and the command that does not wait for it."""
    Network(monkeypatch, OSError("no route to host"))
    world.establish()
    failed = world.state()["fetch_failures"][f"fake:{records.platform_key()}"]["at"]
    when = status.next_fetch(failed)
    assert when is not None
    cause = world.status()["cause"]
    assert f"a launch tries again from {when.strftime('%Y-%m-%dT%H:%M:%SZ')}" in cause
    assert "`aew capability check` tries now" in cause


def test_a_register_that_cannot_be_written_never_stops_a_launch(world, monkeypatch):
    """CAPR-12: the fetch and the record of a check both give way."""
    Network(monkeypatch, world.reg["archive"])

    def refused(*_a: Any, **_k: Any) -> None:
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(store, "atomic_write", refused)
    _, label = world.establish()
    assert label["self_test"]["ok"] is True


# ---------------------------------------------------------------------------------------------- the health check


def test_the_check_reads_the_sandbox_not_the_host(world):
    """A7, at `aew capability check`: a copy that passes on the host and is not in a sandbox fails, and says so."""
    directory = world.tmp / "host-only"
    directory.mkdir()
    (directory / "fake").write_bytes(world.reg["body"])
    (directory / "fake").chmod(0o755)
    world.monkeypatch.setenv("PATH", f"{directory}:/usr/bin:/bin")
    out = ops.check(offline=True)
    assert "could not start in the sandbox" in " ".join(out["checked"]["fake"])
    assert world.state()["checks"]["host:fake"]["where"] == status.IN_SANDBOX
    assert world.status()["observed_status"] == status.UNAVAILABLE


def test_where_no_sandbox_can_be_made_the_check_runs_here_and_the_status_says_so(world, monkeypatch):
    _import(world.reg)
    monkeypatch.setattr(C, "tool_checks", lambda _tools: None)
    ops.check(offline=True)
    assert world.state()["checks"]["aew:fake"]["where"] == status.ON_HOST
    cap = world.status()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and status.HOST_CHECKED in cap["limitations"]


def test_an_import_and_an_add_are_checked_in_a_sandbox_before_they_take_effect(world):
    """CAPR-13."""
    _import(world.reg)
    assert world.state()["checks"]["aew:fake"]["where"] == status.IN_SANDBOX


def test_a_launch_records_a_check_only_when_a_result_changed(world, monkeypatch):
    """An ordinary launch takes no lock: its result is the one the register holds."""
    _import(world.reg)
    world.establish()
    state = world.state()
    state["checks"]["aew:fake"]["at"] = "2020-01-01T00:00:00Z"  # a time no write of this test's could give
    with store.locked():
        store.write(state)
    world.establish()
    assert world.state()["checks"]["aew:fake"]["at"] == "2020-01-01T00:00:00Z"  # its time too: nothing was written


def test_the_status_goes_stale_on_a_new_pin_and_is_checked_again_at_the_next_launch(world, monkeypatch):
    """CAPR-Q04 at a launch."""
    _import(world.reg)
    world.establish()
    shipped = world.reg["shipped"]["fake"]
    moved = {**shipped, "description": "the same payload, a changed record"}
    monkeypatch.setattr(records, "shipped", lambda: {"fake": moved})
    assert world.status()["observed_status"] == status.STALE
    world.establish()
    assert world.status()["observed_status"] == status.FUNCTIONAL_ONLY


def test_doctor_shows_what_its_sandbox_found(world, monkeypatch):
    """The contained check replaces RG-1's line: one sandbox, the containment line's, and no `ripgrep` line."""
    _import(world.reg)
    assert "aew:fake" in world.state()["checks"]
    state = world.state()
    del state["checks"]["aew:fake"]
    with store.locked():
        store.write(state)
    assert world.status()["observed_status"] == status.NOT_ESTABLISHED
    lines = C.doctor_checks({"containment": {"network": {"mode": "isolated"}}}, "unsupported")
    assert [n for n, _, _ in lines] == ["containment"]
    assert world.status()["observed_status"] == status.FUNCTIONAL_ONLY
    assert world.state()["checks"]["aew:fake"]["where"] == status.IN_SANDBOX


def test_doctor_names_a_missing_provider_with_its_fix_and_stays_a_warning(world, monkeypatch):
    """CAPR-Q06, in process: a host copy absent and present (the test plants both, whatever this host has)."""
    C.doctor_checks({"containment": {"network": {"mode": "isolated"}}}, "unsupported")
    row = next(c for c in doctor.environment_checks() if c["check"] == "capability:FAKE_SEARCH")
    assert row["status"] == "WARN" and "not on this host" in row["detail"] and "aew capability check" in row["detail"]
    host = _plant_host_copy(world.reg, monkeypatch)
    C.doctor_checks({"containment": {"network": {"mode": "isolated"}}}, "unsupported")
    row = next(c for c in doctor.environment_checks() if c["check"] == "capability:FAKE_SEARCH")
    assert row["status"] == "PASS" and "unpinned" in row["detail"] and str(host.resolve()) in row["detail"]


def test_inside_a_sandbox_a_check_of_the_register_is_refused_and_changes_nothing(tmp_path, monkeypatch):
    """CAPR-Q02, by the commands themselves, from a real sandbox, on a real register."""
    data = tmp_path / "data"
    (tmp_path / "home").mkdir()
    clean_launching_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(store, "ROOT_OVERRIDE", None)
    root = store.root()
    root.mkdir(parents=True)
    (root / store.REGISTER).write_text(json.dumps(store.empty()))
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    project, worktree = tmp_path / "project", tmp_path / "worktree"
    for repo in (project, worktree):
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    run = tmp_path / "runs" / "R-1"
    run.parent.mkdir()
    layout = C.for_run(role="implementer", scope="ticket", workspace=str(worktree), run_dir=run,
                       scratch=str(run / "scratch"), bridge_dir=None, policy={}, project=str(project),
                       runs=str(run.parent))
    tree = procs.ProcessTree(layout=layout)
    src = str(Path(ops.__file__).resolve().parents[2])
    try:
        proc = tree.spawn([sys.executable, "-m", "aew", "capability", "check", "--offline"], cwd=str(worktree),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "XDG_DATA_HOME": str(data),
                               "PYTHONPATH": src, "LANG": "C.UTF-8", **layout.env})
        out, err = proc.communicate(timeout=120)
    finally:
        tree.close()
    assert proc.returncode != 0 and "register_not_writable" in (out + err), (out, err)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


# ---------------------------------------------------------------------------------------------- each context kind


def _check_cfg(out: Path) -> dict[str, Any]:
    """A project check that writes what its PATH resolves ``rg`` to, where a test can read it."""
    return {"configured": True, "cwd": ".", "timeout_s": 60,
            "command": ["sh", "-c", f'{{ command -v rg; printf "%s\\n" "$PATH"; }} > "{out}"']}


def _says_the_entry(path: Path, *, run_dir: str | None = None) -> str:
    """The entry a context's check or agent found: the first PATH entry holds it, and it is its own directory's."""
    found, path_line = path.read_text(encoding="utf-8").splitlines()[:2]
    first = path_line.split(":")[0]
    assert found == f"{first}/rg" and first.endswith(f"/{Path('tools') / 'first'}"), (found, path_line)
    assert run_dir is None or first.startswith(run_dir)
    return found


def _write_checks(project: Any, **checks: dict[str, Any]) -> None:
    policy = project.root / ".aew/policy/checks.yaml"
    doc = load_yaml(policy.read_text(encoding="utf-8"))
    doc["checks"].update(checks)
    policy.write_text(dump_yaml(doc), encoding="utf-8", newline="\n")


def test_a_worker_runs_with_the_entries_first_on_its_harnesss_path_and_its_label_says_what_served(tmp_path):
    """The worker's context, by the real route: a real supervisor, the sandbox it establishes, its harness's env."""
    sync = tmp_path / "sync"
    policy = {**POLICY, "containment": {"writable": [str(tmp_path / "fake-scripts"), str(sync)],
                                        "network": {"mode": "shared"}}}
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy)
    try:
        wid = create_planned_ticket(lab.project, tmp_path)
        lab.script("default", [{"do": "dump_env", "path": str(sync / "env.json")}])
        run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
        lab.until(lambda: (sync / "env.json").exists(), what="the agent has run")
        path = json.loads((sync / "env.json").read_text(encoding="utf-8"))["PATH"].split(":")
        first = path[0]
        assert first.endswith("/tools/first") and run in first, first
        assert path[1] == os.path.dirname(sys.executable), path  # behind it, what the caller's environment built
        tools = lab.record(run)["containment"]["self_test"]["tools"]["ripgrep"]
        assert tools["command"] == "rg" and tools["found"] == f"{first}/rg"
    finally:
        lab.cleanup()


def test_a_check_a_worker_runs_gets_the_entries_too(tmp_path):
    """A check through the worker's bridge, in the run's layout with no network (``for_check``)."""
    sync = tmp_path / "sync"
    policy = {**POLICY, "containment": {"writable": [str(tmp_path / "fake-scripts"), str(sync)]}}
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy)
    try:
        _write_checks(lab.project, unit=_check_cfg(sync / "check.txt"))
        lab.project.pin_policy()
        wid = create_planned_ticket(lab.project, tmp_path)
        lab.script("default", [{"do": "check", "id": "unit"}, {"do": "touch", "path": str(sync / "done")}])
        lab.lead("work", "assign", wid, "--launch")
        lab.until(lambda: (sync / "done").exists(), what="the agent's check has run")
        _says_the_entry(sync / "check.txt")
    finally:
        lab.cleanup()


def test_for_check_keeps_the_entries_with_no_network(world):
    """The layout a check starts in is the run's: A1's check kind, at its one line."""
    _import(world.reg)
    layout, _ = world.establish("implementer", "ticket")
    check = L.for_check(layout)
    assert check.network == L.ISOLATED and check.tools_first == layout.tools_first
    env = {**checks_module.allowlist_env(check)}
    out = checks_module.run({"command": ["sh", "-c", "command -v fake; fake --version"], "cwd": ".", "timeout_s": 60},
                            world.worktree, policy=None, env=env, layout=layout)
    assert f"{layout.tools_first}/fake" in out["log"] and "fake 1.0" in out["log"], out


def test_the_operators_own_check_run_gets_the_entries(tmp_path):
    """`aew check run`'s own sandbox (DV-4), by the real CLI."""
    from aewflow import assign

    project = sample_project(tmp_path)
    out = tmp_path / "direct.txt"
    # Its sandbox's writable roots are the policy's: the file it writes is read back here
    execution = project.root / ".aew/policy/execution.yaml"
    doc = load_yaml(execution.read_text(encoding="utf-8")) if execution.exists() else {}
    doc.setdefault("containment", {})["writable"] = [str(tmp_path)]
    (tmp_path / "keep").mkdir()
    doc["containment"]["writable"] = [str(tmp_path / "keep")]
    execution.write_text(dump_yaml(doc), encoding="utf-8", newline="\n")
    out = tmp_path / "keep" / "direct.txt"
    _write_checks(project, unit=_check_cfg(out))
    project.pin_policy()
    wid = create_planned_ticket(project, tmp_path)
    assign(project, wid).check("unit")
    _says_the_entry(out)


def test_a_validation_run_gets_the_entries(tmp_path, monkeypatch):
    """Checks-mode validation, the verifier's layout, by the real run. Its executor is not in this process, so what
    it found comes back through the file its check wrote."""
    project = sample_project(tmp_path)
    (tmp_path / "home").mkdir()
    (tmp_path / "keep").mkdir()
    out = tmp_path / "keep" / "validation.txt"
    execution = project.root / ".aew/policy/execution.yaml"
    doc = load_yaml(execution.read_text(encoding="utf-8")) if execution.exists() else {}
    doc.setdefault("containment", {})["writable"] = [str(tmp_path / "keep")]
    execution.write_text(dump_yaml(doc), encoding="utf-8", newline="\n")
    _write_checks(project, probe=_check_cfg(out))
    gates = project.root / ".aew/policy/gates.yaml"
    g = load_yaml(gates.read_text(encoding="utf-8"))
    kept = {k: v for k, v in (g.get("post_integration") or {}).items() if k == "custody_register_s"}
    g["post_integration"] = {"verification": True, "checks": ["probe"], "validation": "checks", **kept}
    gates.write_text(dump_yaml(g), encoding="utf-8", newline="\n")
    project.pin_policy()
    wid, _ = to_commit_ready(project, tmp_path)
    assert project.lead("integrate", "prepare", wid)["ok"]
    engine = Engine(project.root, project.root / ".aew")
    engine._validation.backoff_s = 0.0
    clean_launching_env(monkeypatch, tmp_path / "home")
    done = engine.integrate_validate(token=project.token, expect_rev=project.rev(), work_id=wid)
    assert done["ok"], done
    _says_the_entry(out)


def test_the_lead_gets_the_entries_in_its_own_layout(world, monkeypatch, tmp_path):
    """The Lead's context: its layout (``test_lead_containment.py`` holds the shape) and what its TUI's argv carries."""
    _import(world.reg)
    layout, label = world.establish("lead", "project")
    assert label["self_test"]["tools"]["fake"]["served"] == status.AEW_COPY
    done = world.sh(layout, 'command -v fake; fake --version')
    assert done.stdout.splitlines() == [f"{layout.tools_first}/fake", "fake 1.0"], done
    argv = C.bwrap_argv(layout, ["opencode"], path="/venv/bin:/usr/bin")
    assert argv[argv.index("--setenv"):argv.index("--setenv") + 3] == ["--setenv", "PATH",
                                                                       f"{layout.tools_first}:/venv/bin:/usr/bin"]


def test_a_layout_the_register_is_not_in_any_more_still_starts(world):
    """A payload may go during a run (a check refuses it): the register's bind is `--ro-bind-try`, so only that tool's
    use fails, and a check that starts later is not refused."""
    _import(world.reg)
    layout, _ = world.establish()
    shutil.rmtree(world.reg["root"])
    done = world.sh(layout, 'echo started; fake --version; echo "exit $?"')
    assert done.returncode == 0 and done.stdout.splitlines()[0] == "started", done
    assert done.stdout.splitlines()[-1] != "exit 0"
