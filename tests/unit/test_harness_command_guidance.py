"""Parser-facing command forms printed by harness recovery diagnostics."""

from __future__ import annotations

import re
import sys
import threading
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from aew.cli import fields
from aew.cli.main import build_parser
from aew.engine.harness_ops import Harness, send_route
from aew.engine.stage_intents import StageIntents
from aew.errors import (
    HarnessError,
    HarnessIncompatible,
    HarnessLaunchFailed,
    IllegalTransition,
    MessagingSnapshotMismatch,
)
from aew.harness import contract as harness_contract
from aew.harness import runlog
from aew.harness.opencode import adapter as adapter_module

ROOT = Path(__file__).parents[2]


def _parse(command: str) -> None:
    """Parse a command rendered by a diagnostic, including its fields document."""
    command = command.replace("`", "").replace("<revision from aew status>", "17")
    command, _, document = command.partition(" <<'EOF'")
    document = document.split("\nEOF", 1)[0].lstrip("\n")
    tokens = command.split()
    assert tokens.pop(0) == "aew"
    parser = build_parser()
    old_stdin = sys.stdin
    try:
        sys.stdin = StringIO(document)
        parser.parse_args(fields.expand(tokens, parser))
    finally:
        sys.stdin = old_stdin


def _commands(message: str) -> list[str]:
    """Return every complete command printed in a runtime message."""
    return re.findall(r"`(aew [^`]*)`", message, flags=re.DOTALL)


class _NoCustodyProcess:
    pid = 123

    class _Stdin:
        def write(self, _data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    stdin = _Stdin()

    def kill(self) -> None:
        pass


class _CatalogClient:
    def __init__(self, models: list[dict[str, object]]) -> None:
        self.models = models

    def get(self, *_args: object) -> dict[str, object]:
        return {"data": self.models}


def _adapter_for_catalog(models: list[dict[str, object]]) -> adapter_module.OpenCodeAdapter:
    adapter = adapter_module.OpenCodeAdapter.__new__(adapter_module.OpenCodeAdapter)
    adapter.client = _CatalogClient(models)
    adapter.directory = "."
    adapter._relayed = False
    adapter.contract = SimpleNamespace(invocation="INV-1234")
    return adapter


def _live_run(monkeypatch: pytest.MonkeyPatch, _tmp: Path) -> str:
    harness = Harness.__new__(Harness)
    harness.k = SimpleNamespace(aew_root=_tmp)
    monkeypatch.setattr(runlog, "may_be_live", lambda *_args: True)
    blocker = harness._g_not_live(
        {}, "WU-1", {"invocation": "INV-1", "inv": {"runs": [{"run": "RUN-1", "launched_at": "now"}]}},
    )
    return blocker.message


def _post_commit(monkeypatch: pytest.MonkeyPatch, tmp: Path) -> str:
    harness = Harness.__new__(Harness)
    harness.k = SimpleNamespace(aew_root=tmp, repo_root=tmp)
    monkeypatch.setattr("aew.engine.harness_ops.faults.hit", lambda *_args: None)
    monkeypatch.setattr("aew.engine.harness_ops.supervisor_env", lambda: {})
    monkeypatch.setattr("aew.engine.harness_ops.procs.spawn_detached",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no supervisor")))
    with pytest.raises(HarnessLaunchFailed) as raised:
        harness._spawn_run("INV-1", "RUN-1", "credential")
    return str(raised.value)


def _no_custody(monkeypatch: pytest.MonkeyPatch, tmp: Path) -> str:
    harness = Harness.__new__(Harness)
    harness.k = SimpleNamespace(aew_root=tmp, repo_root=tmp)
    monkeypatch.setattr("aew.engine.harness_ops.faults.hit", lambda *_args: None)
    monkeypatch.setattr("aew.engine.harness_ops.procs.spawn_detached", lambda *_args, **_kwargs: _NoCustodyProcess())
    monkeypatch.setattr("aew.engine.harness_ops._read_acks", lambda *_args: [])
    with pytest.raises(HarnessLaunchFailed) as raised:
        harness._spawn_run("INV-1", "RUN-1", "credential")
    return str(raised.value)


def _current_run(monkeypatch: pytest.MonkeyPatch, tmp: Path) -> str:
    class Session:
        state = {"invocations": {"INV-1": {"status": "active", "runs": [{"run": "RUN-1"}]}}}

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

    harness = Harness.__new__(Harness)
    harness.k = SimpleNamespace(aew_root=tmp, store=SimpleNamespace(session=lambda: Session()))
    harness.archive = SimpleNamespace(archived_credential=False)
    monkeypatch.setattr("aew.engine.harness_ops.require_lead", lambda *_args, **_kwargs: "lead")
    monkeypatch.setattr(runlog, "observed_status", lambda *_args: ("ended", None))
    with pytest.raises(IllegalTransition) as raised:
        harness._lead_request("token", "RUN-1", "interrupt", {}, current=True)
    return str(raised.value)


def _stage(monkeypatch: pytest.MonkeyPatch, tmp: Path, status: str) -> str:
    stages = StageIntents.__new__(StageIntents)
    stages.k = SimpleNamespace(aew_root=tmp)
    monkeypatch.setattr(runlog, "run_dir", lambda *_args: tmp)
    monkeypatch.setattr(runlog, "observed_status", lambda *_args: (status, None))
    return stages._launch_check({"n": 2, "outputs": {"runs": ["RUN-1"]}})["message"]


def _resume(monkeypatch: pytest.MonkeyPatch, tmp: Path, record: dict[str, object] | None) -> str:
    harness = Harness.__new__(Harness)
    harness.k = SimpleNamespace(
        tmp=tmp, aew_root=tmp, execution_policy=lambda: ({"provider_env": ["POLICY_KEY"]}, None),
    )
    monkeypatch.setattr(runlog, "run_dir", lambda *_args: tmp)
    monkeypatch.setattr(runlog, "observed_status", lambda *_args: ("ended", record))
    monkeypatch.setattr("aew.engine.harness_ops.E.scan", lambda *_args: ([], None))
    state = {"invocations": {"INV-1": {"status": "active", "work_unit": "WU-1", "role": "implementer",
                                         "runs": [{"run": "RUN-1"}]}}}
    return harness.harness_resume(state)[0]["action"]


def _adapter_variant(_monkeypatch: pytest.MonkeyPatch, _tmp: Path) -> str:
    adapter = _adapter_for_catalog([{"providerID": "openai", "id": "gpt", "variants": []}])
    with pytest.raises(HarnessIncompatible) as raised:
        adapter._await_model({"provider": "openai", "model": "gpt", "effort": "high"})
    return str(raised.value)


def _adapter_disabled(_monkeypatch: pytest.MonkeyPatch, _tmp: Path) -> str:
    adapter = _adapter_for_catalog([{"providerID": "openai", "id": "gpt", "enabled": False}])
    with pytest.raises(HarnessIncompatible) as raised:
        adapter._await_model({"provider": "openai", "model": "gpt"})
    return str(raised.value)


def _adapter_timeout(monkeypatch: pytest.MonkeyPatch, _tmp: Path) -> str:
    monkeypatch.setattr(adapter_module, "CATALOG_WAIT_S", -1.0)
    adapter = _adapter_for_catalog([])
    with pytest.raises(HarnessIncompatible) as raised:
        adapter._await_model({"provider": "openai", "model": "gpt"})
    return str(raised.value)


def _adapter_ended(_monkeypatch: pytest.MonkeyPatch, _tmp: Path) -> str:
    adapter = _adapter_for_catalog([])
    adapter.turn = "ended"
    adapter.sent = []
    adapter.session = "session"
    adapter._lock = threading.RLock()
    with pytest.raises(HarnessError) as raised:
        adapter.send("text", "steer")
    return str(raised.value)


def _send_route(monkeypatch: pytest.MonkeyPatch, _tmp: Path) -> str:
    monkeypatch.setattr("aew.engine.harness_ops.SNAPSHOT_RECORDED", True)
    with pytest.raises(MessagingSnapshotMismatch) as raised:
        send_route("disabled", "enabled", "next-step")
    return str(raised.value)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(_live_run, id="live-run-stop-and-replace"),
        pytest.param(_post_commit, id="post-commit-launch-failure"),
        pytest.param(_no_custody, id="no-custody-acknowledgement"),
        pytest.param(_current_run, id="current-run-refusal"),
        pytest.param(lambda m, t: _resume(m, t, None), id="ended-run-cancel"),
        pytest.param(lambda m, t: _resume(m, t, {"reason_code": harness_contract.PROVIDER_AUTH_FAILED,
                                                 "contract": {"extra": {"provider_env": ["API_KEY"]}}}),
                          id="provider-auth-cancel"),
        pytest.param(lambda m, t: _stage(m, t, harness_contract.UNCONFIRMED), id="stage-launch-failure"),
        pytest.param(lambda m, t: _stage(m, t, "ended"), id="stage-run-ended"),
        pytest.param(_send_route, id="messaging-snapshot-mismatch"),
        pytest.param(_adapter_variant, id="adapter-variant-refusal"),
        pytest.param(_adapter_disabled, id="adapter-disabled-refusal"),
        pytest.param(_adapter_timeout, id="adapter-catalog-timeout"),
        pytest.param(_adapter_ended, id="adapter-ended-turn"),
    ],
)
def test_changed_guidance_renders_parser_accepted_commands(
    case: Callable[[pytest.MonkeyPatch, Path], str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    message = case(monkeypatch, tmp_path)
    commands = _commands(message)
    assert commands
    for command in commands:
        _parse(command)
