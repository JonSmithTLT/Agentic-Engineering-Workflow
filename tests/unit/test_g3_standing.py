"""G3-C's PR C1: G3's standing on this host (the STG-03 hand-off's addendum 7, ruling 2), its readers, and B3.

The standing's conditions are judged on stand-ins: the platform passed in, ``request.sock`` and the confirmer at paths
under the test's directory, the project's policy as a launch reads it, and a register of weaker contexts of the test's
own. Each condition fails alone with its own reason, and every reader prints what the one function says."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew import doctor, g3client
from aew import g3standing as S
from aew.harness import containment
from aew.harness import weaker_register as W
from aew.harness.containment import netns

REPO = Path(__file__).resolve().parents[2]
WEAK = containment.label(contained=False, reason="planted")
CONTAINED = {"containment": {"mode": "required", "network": {"mode": "proxy_only"}}}


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A Linux host with G3 installed, a register created more than a window ago and holding nothing: G3 counts."""
    sock, confirmer = tmp_path / "request.sock", tmp_path / "aew-g3-confirm"
    sock.write_bytes(b"")
    confirmer.write_bytes(b"")
    # Linux, for the modules that judge the platform only: the register's own lock stays this host's
    linux = SimpleNamespace(platform="linux")
    for module in (S, containment, netns, doctor):
        monkeypatch.setattr(module, "sys", linux)
    monkeypatch.setattr(g3client, "REQUEST_SOCK", str(sock))
    monkeypatch.setattr(S, "CONFIRMER", str(confirmer))
    reg = tmp_path / "weaker-contexts"
    monkeypatch.setattr(W, "ROOT_OVERRIDE", reg)
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: None)
    monkeypatch.setattr(W, "_now_ticks", lambda: ("boot-1", 1000))
    monkeypatch.setattr(W, "enforced", lambda: False)
    W.sweep()  # creates it; then its creation is backdated past the window, as on a host where G3 has counted
    created = json.loads((reg / W.CREATED).read_text())
    created["created_epoch"] -= W.WINDOW_S + 60
    (reg / W.CREATED).write_text(json.dumps(created))
    return {"sock": sock, "confirmer": confirmer, "reg": reg}


def test_g3_counts_when_every_condition_holds(host):
    found = S.standing(CONTAINED)
    assert found.counts and found.condition is None and found.reason is None
    assert S.standing(project=False).counts  # a reader with no project: conditions 1 and 3


# ------------------------------------------------------------------------------------- each condition, alone

def test_condition_1_g3_is_a_linux_profile(host):
    found = S.standing(CONTAINED, platform="win32")
    assert (found.counts, found.condition) == (False, 1) and "Linux profile" in (found.reason or "")


def test_condition_1_request_sock_is_where_g3_listens(host):
    host["sock"].unlink()
    found = S.standing(CONTAINED)
    assert (found.counts, found.condition) == (False, 1)
    assert found.reason == f"G3 is not on this host: {host['sock']} does not exist"
    assert "g3/install.sh" in (found.fix or "") and "systemctl start aew-g3.service" in (found.fix or "")


def test_condition_1_the_confirmer_is_at_its_install_path(host):
    host["confirmer"].unlink()
    found = S.standing(CONTAINED)
    assert (found.counts, found.condition) == (False, 1)
    assert found.reason == f"the confirmer is not installed: {host['confirmer']} does not exist"


def test_the_confirmers_path_is_the_installers():
    """Condition 1 restates the confirmer's install path, as the client restates REQUEST_SOCK: held to
    `g3/install.sh`'s CONFIRM_LINK, read as text (the installer is a shell script, not imported)."""
    text = (REPO / "g3" / "install.sh").read_text(encoding="utf-8")
    (link,) = re.findall(r"^CONFIRM_LINK=(\S+)$", text, flags=re.M)
    assert S.CONFIRMER == link


@pytest.mark.parametrize("policy, said", [
    (None, "this project has no execution policy"),  # missing: none to judge, so it fails
    ({"containment": {"mode": "allow_weaker"}}, "containment.mode: allow_weaker"),
    ({"containment": {"mode": "required", "network": {"mode": "shared"}}}, "network mode shared"),
])
def test_condition_2_the_projects_policy_keeps_every_launch_contained(host, policy, said):
    found = S.standing(policy)
    assert (found.counts, found.condition) == (False, 2) and said in (found.reason or "")
    assert found.fix == S.POLICY_FIX
    assert found.line().startswith("G3 does not count for this project: ")  # condition 2 is per project (#365 n1)
    assert S.standing(policy, project=False).counts  # a reader with no project does not judge it


@pytest.mark.parametrize("network", ["proxy_only", "isolated"])
def test_condition_2_either_contained_network_counts(host, network):
    assert S.standing({"containment": {"mode": "required", "network": {"mode": network}}}).counts


def entry(**kw: Any) -> W.Entry:
    return W.enter(**{"kind": "worker_run", "label": WEAK, "ownership": "subreaper", **kw})


def test_condition_3_a_weaker_context_live_in_another_project_fails_the_standing(host):
    e = entry(project="/elsewhere/other-project")
    e.started()
    found = S.standing(CONTAINED)
    assert (found.counts, found.condition) == (False, 3)
    assert found.reason and e.id in found.reason and "/elsewhere/other-project" in found.reason
    assert found.fix and "end it, or wait for it to end" in found.fix


def test_condition_3_a_context_that_ended_inside_the_window_still_fails_and_one_before_it_does_not(host):
    e = entry()
    e.started()
    e.end([])
    ended = json.loads(e.path.read_text())["ended_epoch"]
    found = S.standing(CONTAINED, now=ended + W.WINDOW_S - 1)
    assert (found.counts, found.condition) == (False, 3) and "in the last 15 minutes" in (found.reason or "")
    assert S.standing(CONTAINED, now=ended + W.WINDOW_S + 1).counts


def test_condition_3_the_registers_creation_fails_the_standing_for_the_window(tmp_path, monkeypatch, host):
    fresh = tmp_path / "fresh-register"
    monkeypatch.setattr(W, "ROOT_OVERRIDE", fresh)
    now = time.time()
    found = S.standing(CONTAINED, now=now)  # the standing's sweep creates it: a weaker context that ended then
    assert (found.counts, found.condition) == (False, 3) and "was created at" in (found.reason or "")
    assert S.standing(CONTAINED, now=now + W.WINDOW_S + 1).counts


def test_a_register_that_cannot_be_swept_here_is_read_as_it_is_and_never_counts_by_default(tmp_path, monkeypatch,
                                                                                          host):
    """Inside a sandbox the register is read-only: the sweep fails, and the reading stands without it, which only
    holds longer. A register never created reads as not counting."""
    monkeypatch.setattr(W, "ROOT_OVERRIDE", tmp_path / "never-created")

    def refused(now: float | None = None) -> None:
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(W, "sweep", refused)
    found = S.standing(CONTAINED)
    assert (found.counts, found.condition) == (False, 3) and "not been created" in (found.reason or "")


def test_the_standing_is_computed_per_call_never_cached(host):
    assert S.standing(CONTAINED).counts
    host["sock"].unlink()
    assert not S.standing(CONTAINED).counts


def test_the_first_failing_condition_decides(host):
    host["sock"].unlink()
    entry().started()
    found = S.standing(None)  # 1, 2 and 3 all fail: the first is said, with its own reason and fix
    assert found.condition == 1 and str(host["sock"]) in (found.reason or "") and "install G3" in (found.fix or "")


# --------------------------------------------------------------------------------- the readers, from one owner

def test_doctors_g3_line_is_the_standings_and_never_fails(host, monkeypatch):
    """On Linux: PASS when G3 counts and its service answers; WARN with the standing's own line otherwise; never
    FAIL, since G3 is optional. Outside a project it says condition 2 is per project. Off Linux there is no line."""
    monkeypatch.setattr(g3client, "probe", lambda sock_path=None: None)
    engine = type("E", (), {"execution_policy": lambda self: (CONTAINED, "sha")})()
    line = doctor.g3_check(engine)
    assert line is not None and line["status"] == "PASS" and line["detail"].startswith(S.standing(CONTAINED).line())
    outside = doctor.g3_check(None)
    assert outside is not None and outside["status"] == "PASS" and "condition 2 is per project" in outside["detail"]
    monkeypatch.setattr(g3client, "probe", lambda sock_path=None: "the G3 service did not answer")
    silent = doctor.g3_check(engine)
    assert silent is not None and silent["status"] == "WARN" and "does not answer" in silent["detail"]
    host["sock"].unlink()
    warned = doctor.g3_check(engine)
    assert warned == {"check": "g3", "status": "WARN", "detail": S.standing(CONTAINED).line()}
    assert doctor.g3_check(engine, platform="win32") is None


def test_the_request_command_says_the_standing_before_the_confirmer_and_goes_ahead(host, tmp_path, monkeypatch,
                                                                                    capsys):
    """`aew g3 request` prints the standing's line before it asks the confirmer, with the probe; when G3 does not
    count it still asks, saying approving admits nothing."""
    from aew.cli.main import main
    from aew.engine.custody_ops import LEAD_SESSION_VARS
    from aew.errors import Unavailable

    for var in LEAD_SESSION_VARS:
        monkeypatch.delenv(var, raising=False)
    host["sock"].unlink()
    order: list[str] = []
    monkeypatch.setattr(g3client, "probe", lambda sock_path=None: order.append("probe") or "it is not there")
    monkeypatch.setattr(g3client, "check_set", lambda c: c)
    monkeypatch.setattr(g3client, "with_proofs", lambda c: c)

    def asked(cset: Any, sock_path: str | None = None) -> Any:
        order.append("confirmer")
        raise Unavailable("stop here", reason="g3_unreachable")

    monkeypatch.setattr(g3client, "request_approval", asked)
    (tmp_path / "set.json").write_bytes(b"{}")
    (tmp_path / "token").write_bytes(b"synthetic-token\n")
    main(["g3", "request", str(tmp_path / "set.json"), "--o01", "http://127.0.0.1:4261", "--token-file",
          str(tmp_path / "token"), "--json"])
    err = capsys.readouterr().err
    assert order == ["probe", "confirmer"]
    assert f"aew g3: {S.standing(project=False).line()}\n" in err
    assert "the G3 service does not answer: it is not there" in err
    assert "approving admits nothing; the action stays held" in err


def test_a_weaker_launch_on_a_g3_host_says_when_g3_counts_again(host, capsys):
    """Addendum 7: on a G3 host a weaker launch's line says when G3 counts again: on this host 15 minutes after it
    ends, and for its project while the policy says so; an eval lane's gives the host clause alone. Not a G3 host:
    nothing is said."""
    entry(project="/p/one")
    err = capsys.readouterr().err
    assert f"aew: {S.weaker_launch_line(kind='worker_run', project='/p/one')}\n" in err
    assert "15 minutes after this launch ends, and for /p/one only while its policy" in err
    assert "An approval window you did not open is not yours to approve: decline it." in err
    W.enter(kind="eval_raw", label=WEAK, ownership="process_group", project="/p/one")
    lane = capsys.readouterr().err
    assert "15 minutes after this launch ends. An approval" in lane and "/p/one" not in lane
    host["sock"].unlink()
    entry(project="/p/one")
    assert "G3 counts" not in capsys.readouterr().err


# ----------------------------------------------------------------------------------------------------- B3

def test_b3_what_holds_an_entry_live_is_named_with_its_process_and_working_directory(host, monkeypatch):
    """B3 (the designer's ruling for G3-C): an unreadable process that started after a weaker context keeps its entry
    live, as a contained run in a project AEW has no entry for would. The standing's reason names it, its working
    directory, and the fix; its label is never trusted."""
    e = entry(project="/p/one")
    e.started()
    other = W.Proc(pid=4242, start_id="linux:boot-1:3000", ticks=3000, env=None,
                   cmdline=("python", "-m", "aew.harness.supervisor"), cwd="/home/op/unnamed-project")
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: W.Scan(procs=[other], boot="boot-1", now_ticks=5000))
    e.end(None)  # the owner does not know what survived: unowned, held by what the scan cannot rule out
    found = S.standing(CONTAINED)
    assert (found.counts, found.condition) == (False, 3)
    reason = found.reason or ""
    assert "process 4242 (python -m aew.harness.supervisor; in /home/op/unnamed-project)" in reason
    assert "a contained run in a project AEW has no entry for" in reason and "end it, or wait for it to end" in reason


def test_b3_a_working_directory_that_cannot_be_read_is_said_so():
    p = W.Proc(pid=7, start_id=None, ticks=None, env=None, cmdline=("x",))
    assert "its working directory cannot be read" in W.unreadable_process(p)


def test_b3_a_hardened_supervisor_is_named_by_its_run_directory_whatever_its_command_lines_length(host, monkeypatch):
    """#365 review M1: B3's process is a hardened supervisor, which is not dumpable, so its working directory cannot be
    read; its command line can, and its ``--run-dir`` is that working directory. The reason names it in full, however
    long the interpreter's path makes the command (the supervisor's argv as ``harness_ops`` spawns it)."""
    run_dir = "/home/operator/projects/unnamed-project/.aew/runs/R-20261107-0001"
    python = "/home/operator/.local/share/aew/venvs/aew-0.9.0-py3.11/bin/python3.11"
    argv = (python, "-P", "-s", "-m", "aew.harness.supervisor", "--run-dir", run_dir)
    assert len(" ".join(argv[:-1])) > 80  # the run directory falls past the command's cut
    supervisor = W.Proc(pid=4243, start_id="linux:boot-1:3000", ticks=3000, env=None, cmdline=argv, cwd=None)
    said = W.unreadable_process(supervisor)
    assert f"its run directory {run_dir})" in said and said.startswith("process 4243 (")
    e = entry(project="/p/one")
    e.started()
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: W.Scan(procs=[supervisor], boot="boot-1",
                                                                          now_ticks=5000))
    e.end(None)
    assert run_dir in (S.standing(CONTAINED).reason or "")


def test_b3_a_command_line_reaches_the_operator_without_its_control_characters():
    """#365 review m1: an unreadable process's command line and working directory are shown to the operator (doctor,
    `aew g3 request`), never trusted: a newline or a terminal escape in them cannot forge a line or move the cursor."""
    forged = W.Proc(pid=9, start_id=None, ticks=None, env=None,
                    cmdline=("x\naew g3: G3 counts here", "\x1b[2J", "--run-dir", "/r\x1b]0;t\x07"), cwd=None)
    for p in (forged, W.Proc(pid=9, start_id=None, ticks=None, env=None, cmdline=("x",), cwd="/w\n\x1b[1A")):
        said = W.unreadable_process(p)
        assert not any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in said), said


def test_b3_the_sweep_records_what_holds_an_entry_and_the_reading_shows_it(host, monkeypatch):
    e = entry(project="/p/one")
    e.started()
    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: W.Scan(failed="/proc: planted", boot="boot-1"))
    e.end(None)
    data = json.loads(e.path.read_text())
    del data["held_by"]  # as an owner that wrote no holder left it: only the sweep can name one
    e.path.write_text(json.dumps(data))
    found = S.standing(CONTAINED)  # the standing sweeps before it reads
    assert "held by the scan failed: /proc: planted" in (found.reason or "")
    assert json.loads(e.path.read_text())["held_by"] == ["the scan failed: /proc: planted"]
