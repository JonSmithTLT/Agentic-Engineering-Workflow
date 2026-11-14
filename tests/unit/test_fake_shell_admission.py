"""Planted barrier controls, independent of OpenCode stream/call lifetime: 31 seconds on a stepped clock.

The real shell/CLI/bridge boundary stays in test_worker_messages; these controls enumerate the fake shell's
two pre-admission outcomes without a real-time sleep or another host process."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import fake_agent as agent
import proctree


def shell_case(tmp_path, monkeypatch, *, exit_before_binding=False):
    bound = tmp_path / "wait-bound"
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds
        if now[0] >= 31.0:
            bound.touch()

    class Shell:
        pid = 42000
        returncode = 7 if exit_before_binding else None
        kills = 0
        waits = []

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.waits.append(timeout)
            if self.returncode is None:
                raise subprocess.TimeoutExpired("planted shell", timeout)
            return self.returncode

        def kill(self):
            self.kills += 1
            self.returncode = 1

    shell = Shell()
    root = proctree.Proc(shell.pid, 1, 10, "powershell.exe", "powershell -Command aew message wait --timeout 5")
    child = proctree.Proc(42001, shell.pid, 11, "aew.exe", "aew.exe message wait --timeout 5")
    monkeypatch.setattr(agent, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleep))
    monkeypatch.setattr(agent, "subprocess", SimpleNamespace(Popen=lambda *_, **__: shell,
                        TimeoutExpired=subprocess.TimeoutExpired))
    monkeypatch.setattr(agent, "proctree", SimpleNamespace(start_time=lambda _: root.start, table=lambda: [root, child],
                        descendants=proctree.descendants, describe=proctree.describe))
    result = agent.step({"do": "shell", "command": "aew message wait --timeout 5", "timeout_s": 1,
                         "timeout_after_file": str(bound)}, {"tmp": str(tmp_path), "n": 2})
    return result, shell, now[0], bound


def test_shell_admission_past_the_old_30_second_deadline_starts_only_the_post_binding_timer(tmp_path, monkeypatch):
    result, shell, elapsed, bound = shell_case(tmp_path, monkeypatch)
    assert elapsed >= 31.0 and bound.exists(), result
    assert not result.get("barrier_error") and result["timed_out"], result
    assert shell.kills == 1 and shell.waits == [1, None]  # the unchanged shell timeout, only after admission
    evidence = Path(result["admission_file"]).read_text(encoding="utf-8")
    assert "bound: True" in evidence and "aew child started: OBSERVED pids [42001]" in evidence


def test_shell_exit_before_admission_is_not_killed_or_timed_out(tmp_path, monkeypatch):
    result, shell, _, bound = shell_case(tmp_path, monkeypatch, exit_before_binding=True)
    assert result["exit"] == 7 and not result["timed_out"] and not bound.exists()
    assert result["barrier_error"] == "shell exited before wait binding"
    assert shell.kills == 0 and not shell.waits
