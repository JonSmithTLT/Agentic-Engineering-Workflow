"""The Lead contained, on Linux (STG-05 CS-4; CB-01, CB-05, CB-12 rows 1 to 6).

Every test builds the real Lead layout (``for_run`` role ``lead``, scope ``project``) in a project with a store and a
``.aew/local``, and runs real processes in it through ``ProcessTree(layout=...)``, or the launch self-test. The project
lives outside ``/tmp`` (the sandbox has a private ``/tmp``), so each attempt meets the host's file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from aew.errors import ContainmentUnavailable
from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import egress, netns, probe
from aew.harness.containment import layout as L

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                                reason="Linux bubblewrap containment (Windows: the Lead runs labelled not contained)")

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV, **(env or {})})


class LeadLab:
    """A project with a store, a `.aew/local` holding another run's state and a control lock, and a synthetic home."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "proj"
        self.repo.mkdir()
        assert git("init", "-q", cwd=self.repo).returncode == 0
        (self.repo / "f.txt").write_text("base\n")
        git("add", "f.txt", cwd=self.repo)
        assert git("commit", "-q", "-m", "base", cwd=self.repo).returncode == 0
        for d in (".aew/state/log", ".aew/local/harness/runs/R-other/harness"):
            (self.repo / d).mkdir(parents=True)
        (self.repo / ".aew" / "state" / "control.json").write_text('{"revision": 1}\n')
        (self.repo / ".aew" / "local" / "control.lock").write_text("")
        (self.repo / ".aew" / "local" / "harness" / "runs" / "R-other" / "harness" / "bridge.key").write_text("K\n")
        self.home = root / "home"
        (self.home / ".local" / "share" / "opencode").mkdir(parents=True)
        (self.home / ".local" / "share" / "opencode" / "opencode.db").write_text("SYNTHETIC-LOGIN-STORE\n")
        (self.home / ".config" / "opencode").mkdir(parents=True)
        (self.home / ".config" / "opencode" / "opencode.json").write_text('{"mcp": {}}\n')
        self.run = self.repo / ".aew" / "local" / "harness" / "runs" / "lead-1"
        self.state = self.repo / ".aew" / "local" / "harness" / "lead"

    def layout(self, **kw: Any) -> C.Layout:
        return C.for_run(role="lead", scope="project", workspace=str(self.repo), run_dir=self.run,
                         scratch=str(self.run / "scratch"), bridge_dir=None, policy=kw.pop("policy", None),
                         home=str(self.home), project=str(self.repo), runs=str(self.run.parent), env={},
                         state_dir=str(self.state), **kw)

    def sh(self, layout: C.Layout, script: str) -> subprocess.CompletedProcess[str]:
        tree = procs.ProcessTree(layout=layout)
        try:
            proc = tree.spawn(["sh", "-c", script], cwd=str(self.repo), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                              env={"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C.UTF-8",
                                   **GIT_ENV, **layout.env})
            out, err = proc.communicate(timeout=60)
            return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        finally:
            tree.close()


@pytest.fixture
def lead_lab() -> Iterator[LeadLab]:
    base = Path(os.environ.get("AEW_CONTAINMENT_TEST_DIR") or Path.home() / ".aew-test-tmp")
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="lead-", dir=base))
    try:
        yield LeadLab(root)
    finally:
        for p in root.rglob("*"):  # git makes objects read-only
            try:
                p.chmod(0o700 if p.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ outcome 2

def test_the_lead_writes_its_working_tree_and_never_aew_or_the_git_metadata(lead_lab):
    """CS-4 outcome 2 (ruling R-2): the working tree is writable; `.aew` (the store with it) and the real git metadata
    are read-only; git's status, diff and log work on the run's private index and object store."""
    lab = lead_lab
    before = {p: p.read_bytes() for p in (lab.repo / ".aew" / "state" / "control.json", lab.repo / ".git" / "HEAD")}
    done = lab.sh(lab.layout(), "printf edited > f.txt && printf new > g.txt && git add g.txt && "
                                "git status --porcelain && git diff --cached --stat && git log --oneline -1 && "
                                "{ printf x >> .aew/state/control.json; echo store=$?; } 2>/dev/null; "
                                "{ mv .aew .aew-moved; echo rename=$?; } 2>/dev/null; "
                                "{ printf x > .git/HEAD; echo head=$?; } 2>/dev/null")
    assert (lab.repo / "f.txt").read_text() == "edited" and (lab.repo / "g.txt").read_text() == "new"
    assert "g.txt" in done.stdout and "base" in done.stdout, done.stdout + done.stderr  # status, diff, log
    assert "store=1" in done.stdout and "rename=1" in done.stdout and "head=1" in done.stdout, done.stdout
    assert {p: p.read_bytes() for p in before} == before
    assert (lab.repo / ".aew").is_dir() and not (lab.repo / ".aew-moved").exists()
    assert "g.txt" not in git("diff", "--cached", "--name-only", cwd=lab.repo).stdout  # the real index: untouched


def test_from_the_leads_sandbox_aew_local_holds_only_its_own_directories(lead_lab):
    """CS-4 outcome 2: no control lock, no other run's state or socket; only the Lead's run directories and state."""
    lab = lead_lab
    done = lab.sh(lab.layout(), "ls -A .aew/local; echo ---; ls -A .aew/local/harness; echo ---; "
                                "ls -A .aew/local/harness/runs; echo ---; "
                                "touch .aew/local/mine.lock 2>/dev/null; echo lock=$?")
    parts = [p.split() for p in done.stdout.split("---\n")]
    assert parts[0] == ["harness"] and sorted(parts[1]) == ["lead", "runs"] and parts[2] == ["lead-1"], done.stdout
    assert "lock=1" in done.stdout


def test_the_operators_opencode_login_and_configuration_are_empty_from_the_leads_sandbox(lead_lab):
    lab = lead_lab
    done = lab.sh(lab.layout(), f"ls -A {lab.home}/.local/share/opencode {lab.home}/.config/opencode")
    assert "opencode.db" not in done.stdout and "opencode.json" not in done.stdout, done.stdout


# ------------------------------------------------------------------------------------------- outcome 6, rows

def lead_establish(lab: LeadLab, monkeypatch, *, terminal: bool = True, mode: str | None = None,
                   network: str | None = None) -> tuple[C.Layout | None, dict[str, Any]]:
    monkeypatch.setenv("HOME", str(lab.home))
    policy: dict[str, Any] = {"containment": {}}
    if mode:
        policy["containment"]["mode"] = mode
    if network:
        policy["containment"]["network"] = {"mode": network}
    return C.establish(role="lead", scope="project", workspace=str(lab.repo), run_dir=lab.run,
                       scratch=str(lab.run / "scratch"), bridge_dir=None, policy=policy, project=str(lab.repo), env={},
                       egress_policy=egress.AnyPublic(), state_dir=str(lab.state),
                       relayed_terminal={"forbid": None} if terminal else None)


def test_the_leads_self_test_passes_rows_1_to_6_with_its_relayed_terminal_and_any_public_egress(lead_lab, monkeypatch):
    """CS-4 outcome 6: the launch self-test runs on the Lead's own layout, every row passes and is on the label with
    the network mode: row 1 under any-public (R-6 refuses the host's own port), row 4's Lead form (its controlling
    terminal is the relayed one), row 6 (`.aew` a read-only mount point below the writable tree)."""
    layout, label = lead_establish(lead_lab, monkeypatch)
    try:
        assert layout is not None and label["filesystem"] == C.CONTAINED
        rows = label["self_test"]["rows"]
        assert sorted(rows) == ["1", "2", "3", "4", "5", "6"]
        assert {n: r["reason"] for n, r in rows.items() if not r["ok"]} == {}
        assert label["network"]["mode"] == L.PROXY_ONLY and rows["1"]["mode"] == L.PROXY_ONLY
        assert rows["1"]["egress_refused"]["why"] == "a host address (R-6)"
        assert rows["4"]["relayed"] is True and rows["4"]["dev_tty"] == "opened"
        aew = os.path.join(os.path.realpath(lead_lab.repo), ".aew")
        assert rows["6"]["stores"][0]["below"] == {aew: {"mount_point": True, "readonly": True}}
    finally:
        if layout is not None and layout.net_dir:
            shutil.rmtree(layout.net_dir, ignore_errors=True)


def test_row_6_fails_closed_when_the_aew_re_bind_is_missing_from_the_leads_sandbox(lead_lab, monkeypatch):
    """The forgotten route: the Lead's tree without the `.aew` re-bind. The host's own check (CB-07) refuses such a
    layout before anything runs; here the layout passes it and the sandbox loses the re-bind afterwards, and row 6,
    reading the mount table inside, fails, so `required` refuses the launch."""
    aew = os.path.join(os.path.realpath(lead_lab.repo), ".aew")
    real = probe.bwrap_argv

    def without_aew(layout, cmd, **kw):
        out = real(layout, cmd, **kw)
        at = next(i for i in range(out.index("--")) if out[i:i + 3] == ["--ro-bind", aew, aew])
        return out[:at] + out[at + 3:]

    monkeypatch.setattr(probe, "bwrap_argv", without_aew)
    with pytest.raises(ContainmentUnavailable, match="row 6 ") as refused:
        lead_establish(lead_lab, monkeypatch, network=L.SHARED)
    row = refused.value.details["self_test"]["rows"]["6"]
    assert row["ok"] is False and "is not a mount point inside" in row["reason"]


def test_row_4_for_the_lead_fails_closed_without_the_shims_controlling_terminal_step(lead_lab, monkeypatch):
    """Ruling R-7: without the shim's `ctty` step, the probe on the relayed terminal has no controlling terminal, so
    row 4's Lead form fails, and so does a launch on it."""
    real = netns.shim_argv
    monkeypatch.setattr(netns, "shim_argv", lambda spec, argv: real({k: v for k, v in spec.items() if k != "ctty"},
                                                                    argv))
    with pytest.raises(ContainmentUnavailable, match="row 4 ") as refused:
        lead_establish(lead_lab, monkeypatch, network=L.SHARED)
    assert "is not the relay's pseudo-terminal" in refused.value.details["self_test"]["rows"]["4"]["reason"]


def test_a_lead_that_falls_back_to_allow_weaker_is_labelled_so(lead_lab, monkeypatch):
    """CS-4 outcome 1: a Lead whose sandbox fails runs only under `allow_weaker`, labelled workdir_separation_only with
    the reason and the failing row, the label G3 reads as not established."""
    monkeypatch.setattr(netns, "shim_argv", lambda spec, argv: argv)  # no ctty step: row 4 fails
    layout, label = lead_establish(lead_lab, monkeypatch, mode=C.ALLOW_WEAKER, network=L.SHARED)
    assert layout is None and label["filesystem"] == C.WORKDIR_ONLY
    assert "row 4" in label["weaker_because"] and label["self_test"]["rows"]["4"]["ok"] is False
