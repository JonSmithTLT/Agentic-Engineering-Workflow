"""`aew doctor --run-checks` enters a weaker check in the register of weaker contexts as `aew check run` does (G3
addendum 7; register E153): live while its check runs, the check given the marker, and ended, with its directory and
copy gone, once it returns. The check runner and the sandbox are stood in for; the copy is a real clone."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from aew.harness import check_changes, containment
from aew.harness import weaker_register as W
from aew.policy import checks as C


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()


def test_a_weaker_doctor_check_is_live_in_the_register_while_it_runs_and_carries_the_marker(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", cwd=repo)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    git("add", "README.md", cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "c", cwd=repo)
    commit = git("rev-parse", "HEAD", cwd=repo)
    engine = SimpleNamespace(aew_root=repo / ".aew", repo_root=repo, manifest={},
                             execution_policy=lambda: ({}, None), workspaces_root=lambda: tmp_path / "ws",
                             snapshot_of=lambda path, wid: {"relevant_inputs_fingerprint": "git-tree:same"})
    weaker = containment.label(contained=False, reason="the execution policy allows weaker runs")
    monkeypatch.setattr(containment, "establish", lambda **kw: (None, weaker))
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")  # an owner that held the whole tree
    ran: list[dict] = []

    def run(cfg, workspace, **kw):
        marker = Path(kw["env"][W.MARKER])
        ran.append({**kw, "live": [e["kind"] for e in W.read().live], "workspace": workspace,
                    "label": json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None})
        return {"exit_code": 0, "duration_s": 0.0, "log": "", "command": ["stand-in"], "outcome": "ran",
                "spawn_errno": None}

    monkeypatch.setattr(C, "run", run)
    out = check_changes.run_once(engine, "probe", {"command": ["true"]}, commit)
    [given] = ran
    assert "doctor_check" in given["live"], "entered before the check started"
    assert given["env"][W.MARKER].endswith("label.json") and given["label"] == weaker, "its marker names its label"
    assert out == {"outcome": "ran", "exit_code": 0, "paths": [], "mutated": False}
    assert "doctor_check" not in [e["kind"] for e in W.read().live], "ended once the check returned"
    [ended] = [json.loads(f.read_text(encoding="utf-8")) for f in W.root().glob("doctor_check-*.json")]
    assert ended["outcome"] == "clean"
    assert not Path(given["env"][W.MARKER]).parent.exists() and not Path(given["workspace"]).exists()
