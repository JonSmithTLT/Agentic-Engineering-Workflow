"""Parser-facing command forms printed by harness recovery diagnostics."""

from __future__ import annotations

import argparse
import re
import threading
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import printed_commands as P
import pytest

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


def _parse(command: str, *, fenced: bool) -> argparse.Namespace:
    """Parse a command as a reader would run it (``printed_commands.parse``: the revision filled with 17, a fenced
    block's body through ``fields.expand``, any other ``<...>`` an unfilled placeholder), and check that a fenced
    block's single-quoted ``reason:`` or ``rationale:`` value arrives as written."""
    [args] = P.parse(command, fenced=fenced)
    if fenced:
        _, body = P.split(command, fenced=True)
        [line] = (body or "").splitlines()
        match = re.fullmatch(r"(reason|rationale): '(.+)'", line)
        assert match, f"the body is not one single-quoted value: {line!r}"
        key, value = match.groups()
        assert getattr(args, key) == value.replace("''", "'"), (key, getattr(args, key), value)
    assert "--expect-rev" not in command
    return args


_commands = P.commands


def _id_of(args: argparse.Namespace) -> str | None:
    """The run, invocation or stage intent a parsed command names (None: a command that takes none)."""
    return next((v for v in (getattr(args, k, None) for k in ("invocation", "run", "intent")) if v), None)


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
    adapter.contract = SimpleNamespace(invocation="INV-1234", run="R-INV-1234-1")
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
    return stages._launch_check({"n": 2, "outputs": {"runs": ["R-INV-0012-1"]}}, "SI-0003")["message"]


@pytest.mark.parametrize(("role", "scope"), [("implementer", "ticket"), ("reviewer", "ticket"), ("verifier", "ticket"),
                                           ("verifier", "integration"), ("implementer", "integration"),
                                           ("investigator", "observation")])
def test_a_moved_snapshot_is_snapshot_moved_only_for_a_ticket_implementer(tmp_path, monkeypatch, role, scope):
    """Register E400 (#651 review, m1): a run that ended with its evidence on a snapshot that has moved stops as
    ``snapshot_moved`` only for an implementer at ticket scope, whose next step is a relaunch or a fresh attempt with
    a recovery section; under any other role or scope it stays ``not_live``, as before."""
    stages = StageIntents.__new__(StageIntents)
    stages.k = SimpleNamespace(aew_root=tmp_path)
    stages.run_evidence = lambda state, run: {"invocation": "INV-0012", "work_unit": "T-0007", "role": role,
                                              "scope": scope, "evidence": ["INV-0012-impl-2"], "taken": [],
                                              "bound": False}
    monkeypatch.setattr(runlog, "run_dir", lambda *_args: tmp_path)
    monkeypatch.setattr(runlog, "observed_status", lambda *_args: ("ended_with_evidence", None))
    launch = stages._launch_check({"n": 2, "outputs": {"runs": ["R-INV-0012-1"]}}, "SI-0003", state={})
    expected = "snapshot_moved" if (role, scope) == ("implementer", "ticket") else "not_live"
    assert launch["status"] == expected, launch


def test_an_unreadable_stage_run_pauses_without_reporting_an_end(tmp_path, monkeypatch):
    from aew.engine.stage_intents import _refuse_unless_continuable

    stages = StageIntents.__new__(StageIntents)
    stages.k = SimpleNamespace(aew_root=tmp_path)
    monkeypatch.setattr(runlog, "observed_status", lambda *_: ("unreadable", None))
    launch = stages._launch_check({"n": 1, "outputs": {"runs": ["R-INV-0012-1"]}}, "SI-0003")
    assert launch["status"] == "unreadable" and "could not be read" in launch["message"]
    checks = dict.fromkeys(("policy", "contract", "subject", "rebinds"), {"status": "ok"})
    with pytest.raises(IllegalTransition, match="could not be read"):
        _refuse_unless_continuable({"id": "SI-0003"}, {"checks": {**checks, "launch": launch}})


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
    with pytest.raises(MessagingSnapshotMismatch) as raised:
        send_route("disabled", "enabled", "next-step", invocation=harness_contract.invocation_of_run("R-INV-0012-1"))
    return str(raised.value)


_PROVIDER_AUTH = {"reason_code": harness_contract.PROVIDER_AUTH_FAILED,
                  "contract": {"extra": {"provider_env": ["API_KEY"]}}}


@pytest.mark.parametrize(
    "case, named",
    [
        # `named` is every run, invocation and stage intent the message's commands must name, exactly: a command that
        # prints a placeholder where the code knows the id, or names the wrong one, fails (#313 review, F1).
        pytest.param(_live_run, {"RUN-1", "INV-1"}, id="live-run-stop-and-replace"),
        pytest.param(_post_commit, {"INV-1"}, id="post-commit-launch-failure"),
        pytest.param(_no_custody, {"INV-1"}, id="no-custody-acknowledgement"),
        pytest.param(_current_run, {"INV-1"}, id="current-run-refusal"),
        pytest.param(lambda m, t: _resume(m, t, None), {"INV-1"}, id="ended-run-cancel"),
        pytest.param(lambda m, t: _resume(m, t, _PROVIDER_AUTH), {"INV-1"}, id="provider-auth-cancel"),
        pytest.param(lambda m, t: _stage(m, t, harness_contract.UNCONFIRMED), {"INV-0012", "SI-0003"},
                     id="stage-launch-failure"),
        pytest.param(lambda m, t: _stage(m, t, "ended"), {"INV-0012"}, id="stage-run-ended"),
        pytest.param(_send_route, {"INV-0012"}, id="messaging-snapshot-mismatch"),
        pytest.param(_adapter_variant, {"INV-1234"}, id="adapter-variant-refusal"),
        pytest.param(_adapter_disabled, {"INV-1234"}, id="adapter-disabled-refusal"),
        pytest.param(_adapter_timeout, {"INV-1234"}, id="adapter-catalog-timeout"),
        pytest.param(_adapter_ended, {"INV-1234"}, id="adapter-ended-turn"),
    ],
)
def test_changed_guidance_renders_parser_accepted_commands(
    case: Callable[[pytest.MonkeyPatch, Path], str], named: set[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    message = case(monkeypatch, tmp_path)
    commands = _commands(message)
    assert commands
    ids = {_id_of(_parse(command, fenced=fenced)) for command, fenced in commands}
    assert ids - {None} == named, message


def test_a_stage_launch_failure_keeps_the_stages_own_abandon_remedy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The stage's remedy is abandoning the intent; an `invoke cancel` alone leaves it unresolved and the subject
    blocked (#313 review, F4). The abandon command includes the `rationale:` body."""
    message = _stage(monkeypatch, tmp_path, harness_contract.UNCONFIRMED)
    abandon = [args for command, fenced in _commands(message)
               if (args := _parse(command, fenced=fenced)).__dict__.get("stage_cmd") == "abandon"]
    assert [(a.intent, a.rationale) for a in abandon] == [("SI-0003", "stage launch failed")]
    assert len(message) < 2000  # the intent keeps its stopped error's message[:2000]


def test_a_relaunch_hint_without_an_invocation_names_where_to_find_one() -> None:
    """With no id in reach the placeholder names its source; it is never a bare `<INV>` (#313 review, F1)."""
    with pytest.raises(MessagingSnapshotMismatch) as raised:
        send_route("disabled", "enabled", "next-step")
    command = "aew harness launch <invocation from aew harness status> --prior-value <run from aew harness status>"
    assert command in raised.value.message
    assert "<INV>" not in raised.value.message


@pytest.mark.parametrize("value", [
    "it's done", "a\nb", "EOF", "x\nEOF\ny", "tab\there", "back\\slash \"quoted\"\n", "#1 : not a comment",
    " line separator", "\x07bell", "emoji \U0001f600\r\n",
])
def test_fields_command_roundtrip(value: str) -> None:
    """Whatever the value, the printed block is one command line, a body of one line, and `EOF` alone, and the value
    arrives as written: a quote is doubled, and a line break or other unprintable character is escaped in a
    double-quoted scalar, so no body line can be `EOF` (#313 review, N3)."""
    block = harness_contract.fields_command("aew invoke cancel INV-1", "reason", value)
    [(command, fenced)] = _commands(block)
    assert fenced and len(command.splitlines()) == 3
    [args] = P.parse(command, fenced=True)
    assert args.reason == value


def test_harness_send_hands_the_runs_invocation_to_the_route_it_refuses_with(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The mismatch is reported for the named run before any write, naming the invocation to relaunch (#313)."""
    harness = Harness.__new__(Harness)
    harness.coordination = SimpleNamespace(project_switch=lambda _state: "disabled")
    harness.archive = SimpleNamespace(archived_credential=lambda _key: None)
    run = "R-INV-0012-1"
    entry = {"run": run, "coordination": {"messaging": "enabled"}}
    state = {"invocations": {"INV-0012": {"runs": [entry], "status": "active"}}}
    harness.k = SimpleNamespace(aew_root=tmp_path,
                                store=SimpleNamespace(session=lambda: nullcontext(SimpleNamespace(state=state))))
    monkeypatch.setattr("aew.engine.harness_ops.require_lead", lambda *_args, **_kwargs: {})
    with pytest.raises(MessagingSnapshotMismatch) as raised:
        harness.harness_send(token="token", run=run, text="hello")
    assert "`aew harness launch INV-0012 --prior-value R-INV-0012-1`" in raised.value.message


@pytest.mark.parametrize("status", [harness_contract.STARTING, harness_contract.RUNNING, harness_contract.UNREADABLE,
                                    harness_contract.ENDED_WITH_EVIDENCE, harness_contract.LAUNCH_FAILED,
                                    harness_contract.ENDED_WITHOUT_EVIDENCE, harness_contract.CRASHED,
                                    harness_contract.TERMINATED, harness_contract.UNCONFIRMED, harness_contract.LOST])
def test_a_run_is_relaunchable_exactly_where_the_guidance_says_relaunch(status, tmp_path, monkeypatch):
    """Register E233: the action projection offers a relaunch where ``contract.relaunchable`` says so, and that is
    where the engine's own guidance for the run tells the Lead to relaunch it, for every status a run is observed
    in, an ordinary end and a rejected credential alike."""
    harness = Harness.__new__(Harness)
    harness.k = SimpleNamespace(tmp=tmp_path, aew_root=tmp_path, execution_policy=lambda: ({"provider_env": []}, None),
                                store=SimpleNamespace(current=lambda: {"lead": {}}))
    harness._wait_on = lambda runs, _state: f"wait on {runs}"  # type: ignore[method-assign]
    harness._after_run = lambda *_args: "ingest it"  # type: ignore[method-assign]
    monkeypatch.setattr(runlog, "run_dir", lambda *_args: tmp_path)
    monkeypatch.setattr("aew.engine.harness_ops.E.scan", lambda *_args: ([], None))
    state = {"invocations": {"INV-1": {"status": "active", "work_unit": "WU-1", "role": "implementer",
                                         "runs": [{"run": "RUN-1"}]}}}
    relaunch = "`aew harness launch INV-1 --prior-value RUN-1`"
    for record in (None, _PROVIDER_AUTH):
        monkeypatch.setattr(runlog, "observed_status", lambda *_args, record=record: (status, record))
        [row] = harness.harness_resume(state)
        assert (relaunch in row["action"]) == harness_contract.relaunchable(status), row["action"]
