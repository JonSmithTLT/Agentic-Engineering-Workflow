"""DV-4 (the designer, 2026-10-29): under ``required`` the operator's own ``aew check run`` runs its check contained,
or is refused naming ``allow_weaker``; where the policy allows a weaker run it runs labelled so, in the register of
weaker contexts while it runs. The backstop: a check spawned with no layout under ``required`` is refused, whatever
started it. Each with its planted failure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aew.engine.evidence_ops import EvidenceCommands
from aew.errors import ContainmentUnavailable
from aew.harness import containment, procs
from aew.harness import weaker_register as W
from aew.policy import checks as C

CONTAINED = {"filesystem": "os_readonly_roots", "network": {"mode": "proxy_only"}, "self_test": {"ok": True},
             "process_ownership": "pid_namespace"}


class Layout:
    net_dir = None
    env = {"TMPDIR": "/tmp"}


@pytest.fixture
def direct(tmp_path, monkeypatch):
    """The direct route's own frame, with the check runner stood in for: it records what it was given."""
    policy: dict = {}
    commands = object.__new__(EvidenceCommands)
    commands.k = type("K", (), {"policy": lambda self, name: policy, "execution_policy": lambda self: (policy, None),
                                "aew_root": tmp_path / ".aew", "repo_root": tmp_path})()
    ran: list[dict] = []

    def run(cfg, workspace, **kw):
        marker = Path(kw["env"].get(W.MARKER) or workspace / "none")
        ran.append({**kw, "live": [e["kind"] for e in W.read().live],
                    "label": json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None})
        return {"exit_code": 0, "duration_s": 0.0, "log": "", "command": ["stand-in"], "outcome": "ran",
                "spawn_errno": None}

    monkeypatch.setattr(C, "run", run)
    monkeypatch.setattr(containment, "retire_private_git", lambda run_dir: None)
    return commands, policy, ran


def call(commands, tmp_path):
    return commands._check_run_direct({"command": ["true"]}, tmp_path, {"role": "implementer", "scope": "ticket"})


def test_under_required_a_check_whose_sandbox_cannot_be_established_is_refused_naming_allow_weaker(direct, tmp_path,
                                                                                                  monkeypatch):
    commands, _, ran = direct

    def refuse(**kw):
        raise ContainmentUnavailable("containment self-test failed: row 2", self_test={"ok": False})

    monkeypatch.setattr(containment, "establish", refuse)
    with pytest.raises(ContainmentUnavailable) as refused:
        call(commands, tmp_path)
    assert containment.ALLOW_WEAKER_REMEDY in refused.value.message and "Nothing ran" in refused.value.message
    assert refused.value.details["self_test"] == {"ok": False}
    assert ran == [], "no check process started"
    assert not list((tmp_path / ".aew/local/harness/runs").glob("check-*")), "nothing ran in its directory (N3)"


def test_a_contained_check_runs_in_its_sandbox_and_writes_no_register_entry(direct, tmp_path, monkeypatch):
    commands, policy, ran = direct
    layout = Layout()
    monkeypatch.setattr(containment, "establish", lambda **kw: (layout, dict(CONTAINED)))
    out = call(commands, tmp_path)
    [given] = ran
    assert given["layout"] is layout and given["policy"] is policy and given["live"] == []
    assert out["containment"] == CONTAINED and given["env"]["TMPDIR"] == "/tmp"
    assert "AEW_LEAD_TOKEN" not in given["env"] and "AEW_INVOCATION_TOKEN" not in given["env"]
    assert not list(W.root().glob("check_run-*.json"))


def test_where_the_policy_allows_it_a_weaker_check_runs_labelled_and_live_in_the_register(direct, tmp_path,
                                                                                          monkeypatch):
    commands, _, ran = direct
    weaker = containment.label(contained=False, reason="the execution policy allows weaker runs")
    monkeypatch.setattr(containment, "establish", lambda **kw: (None, weaker))
    # an owner that held the whole tree: on Linux a bare process group's end is unowned, so that its run keeps its
    # label (the next test)
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")
    out = call(commands, tmp_path)
    [given] = ran
    assert given["layout"] is None and "check_run" in given["live"], "entered before the check started"
    assert given["env"][W.MARKER].endswith("label.json")
    assert given["label"]["filesystem"] == weaker["filesystem"], "its marker names its label while it runs"
    assert out["containment"]["weaker_because"]
    assert "check_run" not in [e["kind"] for e in W.read().live], "ended once the check returned"
    [ended] = [json.loads(f.read_text(encoding="utf-8")) for f in W.root().glob("check_run-*.json")]
    run_dir = Path(given["env"][W.MARKER]).parent
    assert ended["outcome"] == "clean" and not run_dir.exists(), "a clean end takes the run's directory (N3)"


def test_a_weaker_check_whose_end_is_not_clean_keeps_only_its_label_for_its_live_entry(direct, tmp_path, monkeypatch):
    """#321 review, N3: the run's directory goes with the run, but for the label its entry's marker names while that
    entry may still be live."""
    commands, _, ran = direct
    weaker = containment.label(contained=False, reason="the execution policy allows weaker runs")
    monkeypatch.setattr(containment, "establish", lambda **kw: (None, weaker))
    monkeypatch.setattr(W, "ownership_of", lambda label: "process_group")  # held less than the whole tree: unowned
    call(commands, tmp_path)
    [given] = ran
    run_dir = Path(given["env"][W.MARKER]).parent
    [ended] = [json.loads(f.read_text(encoding="utf-8")) for f in W.root().glob("check_run-*.json")]
    assert ended["outcome"] == "unowned"
    assert [p.name for p in run_dir.iterdir()] == ["label.json"]


def test_the_supervisors_route_passes_its_decision_and_does_not_decide_again(monkeypatch, tmp_path):
    """A run's supervisor passes its label: check_run never establishes a second sandbox for it, nor enters it twice."""
    import inspect

    source = inspect.getsource(EvidenceCommands.check_run)
    assert "if label is None:" in source and "self._check_run_direct(" in source
    from aew.harness import supervisor

    assert "label=self.record[\"containment\"]" in inspect.getsource(supervisor.Supervisor.handle)


def test_under_required_a_check_with_no_layout_is_refused_whatever_started_it(tmp_path, monkeypatch):
    """The backstop (DV-4): it closes the supervisor's window before its run's containment is decided, too."""
    monkeypatch.setattr(containment, "supported", lambda: True)  # `required`, the Linux default, on any host
    spawned: list = []

    def spawn(self, *a, **k):
        spawned.append(a)
        raise OSError(2, "stand-in: nothing is started")

    monkeypatch.setattr(procs.ProcessTree, "spawn", spawn)
    with pytest.raises(ContainmentUnavailable) as refused:
        C.run({"command": ["true"]}, tmp_path, policy=None)
    assert refused.value.details["reason"] == "check_uncontained"
    assert containment.ALLOW_WEAKER_REMEDY in refused.value.message and spawned == []
    allowed = {"containment": {"mode": "allow_weaker"}}
    monkeypatch.setattr(containment, "supported", lambda: False)  # a weaker run, where the policy allows it
    out = C.run({"command": ["true"]}, tmp_path, policy=allowed)
    assert spawned and out["outcome"] in ("ran", "spawn_failed")


def test_a_process_tree_that_requires_a_layout_starts_nothing_without_one():
    tree = procs.ProcessTree(require_layout=True)
    with pytest.raises(ContainmentUnavailable):
        tree.spawn(["true"])
    tree.close()
