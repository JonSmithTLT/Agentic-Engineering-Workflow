"""Fake V2's tool-step event order (A1 A8): the real child finishes before its call and then its step end."""

from __future__ import annotations

import os
import threading
import time

import fake_opencode as fake
import pytest

from aew.harness import agentenv


@pytest.mark.parametrize("failed", [False, True])
def test_a_fake_v2_step_ends_after_its_tool_call(tmp_path, monkeypatch, failed):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "harness" / "xdg-data"))
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", "{}")
    monkeypatch.setenv("OPENCODE_PASSWORD", "synthetic-test-password")
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "synthetic-test-password")
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    app = fake.FakeOpenCode(scripts)
    frames = []
    app.emit = lambda kind, data: frames.append((kind, data))
    s = fake.Session({"id": "session", "model": {"providerID": "fake", "id": "fake-model"},
                      "location": {"directory": str(tmp_path)}})
    s.env = {k: v for k, v in os.environ.items() if k.upper() in agentenv.WINDOWS_KEEP | agentenv.POSIX_KEEP | {"PATH"}}
    ready, release = tmp_path / "ready", tmp_path / "release"
    # An actual child announces itself before blocking, so the pre-completion assertions do not depend on a sleep.
    step = {"do": "wait_file", "pidfile": str(ready), "path": str(release), "timeout": 30}
    errors = []

    def run():
        try:
            app.run_step(s, 0, step)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while not ready.exists() and not errors and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists() and not errors
        assert [kind for kind, _ in frames] == ["session.step.started", "session.tool.input.started",
                                               "session.tool.called"]
        if failed:
            s.interrupted.set()
            assert s.proc is not None
            s.proc.kill()
        else:
            release.touch()
    finally:
        release.touch()
        thread.join(30)
    assert not thread.is_alive() and not errors
    kinds = [kind for kind, _ in frames]
    assert kinds == ["session.step.started", "session.tool.input.started", "session.tool.called",
                     "session.tool.failed" if failed else "session.tool.success", "session.step.ended"]
    assert len({data["assistantMessageID"] for _, data in frames}) == 1
    assert frames[1][1]["id"] == frames[2][1]["id"] == frames[3][1]["id"]
