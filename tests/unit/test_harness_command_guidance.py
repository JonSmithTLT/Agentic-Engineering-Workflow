"""Parser-facing command forms printed by harness recovery diagnostics."""

from __future__ import annotations

import argparse
import re
import shlex
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
    UsageError,
)
from aew.harness import contract as harness_contract
from aew.harness import runlog
from aew.harness.opencode import adapter as adapter_module

ROOT = Path(__file__).parents[2]


REVISION = "<revision from aew status>"
BLOCK = re.compile(r"```sh\n(.*?)\n```", flags=re.DOTALL)
BODY_LINE = re.compile(r"(reason|rationale): '(.+)'")
PLACEHOLDER = re.compile(r"<[^<>\s][^<>]*>")


def _parse(command: str, *, fenced: bool) -> argparse.Namespace:
    """Parse a command as a reader would run it, after filling the revision with 17. A fenced block must close with a
    line that is exactly ``EOF`` and carry a single-quoted ``reason:`` or ``rationale:`` body, which goes through
    ``fields.expand``; an inline command is one line. Any other ``<...>`` left over is an unfilled placeholder."""
    filled = command.replace(REVISION, "17")
    head, sep, rest = filled.partition(" <<'EOF'")
    body = None
    if fenced:
        assert sep and rest.startswith("\n") and rest.endswith("\nEOF"), f"heredoc not closed by EOF: {command!r}"
        body = rest[1:-len("EOF")]
        [line] = body.splitlines()
        match = BODY_LINE.fullmatch(line)
        assert match, f"the body is not one single-quoted value: {line!r}"
    else:
        assert not sep and "\n" not in command, f"an inline command is one line: {command!r}"
    assert not PLACEHOLDER.search(head + (body or "")), f"an unfilled placeholder is left in {command!r}"
    tokens = shlex.split(head)
    assert tokens.pop(0) == "aew"
    parser = build_parser()
    old_stdin = sys.stdin
    try:
        sys.stdin = StringIO(body or "")
        args = parser.parse_args(fields.expand(tokens, parser))
    finally:
        sys.stdin = old_stdin
    if body is not None:
        key, value = BODY_LINE.fullmatch(body.strip()).groups()
        assert getattr(args, key) == value, (key, getattr(args, key), value)
    if "--expect-rev" in tokens:
        assert args.expect_rev == 17
    return args


def _commands(message: str) -> list[tuple[str, bool]]:
    """Every complete command a runtime message prints: each fenced ``sh`` block, then each inline code span outside
    the blocks. The pair is the command and whether it is fenced."""
    fenced = [(block, True) for block in BLOCK.findall(message)]
    rest = BLOCK.sub("", message)
    assert "EOF" not in rest and "<<" not in rest, f"a heredoc outside a fenced block: {message!r}"
    return fenced + [(span, False) for span in re.findall(r"`(aew [^`]*)`", rest)]


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
    return stages._launch_check({"n": 2, "outputs": {"runs": ["R-INV-0012-1"]}}, "SI-0003")["message"]


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


@pytest.mark.parametrize("fenced", [True, False])
def test_the_parse_check_refuses_a_broken_printed_command(fenced: bool) -> None:
    """The check itself fails on each defect it exists for: an unterminated heredoc, an unquoted or wrong-key body,
    a placeholder left unfilled, and a heredoc inside a code span."""
    good = "aew invoke cancel INV-1 --expect-rev <revision from aew status> --fields - <<'EOF'\nreason: 'why'\nEOF"
    if fenced:
        assert _parse(good, fenced=True).reason == "why"
        for broken in (good.removesuffix("\nEOF"), good.replace("'why'", "why"), good.replace("INV-1", "<INV>"),
                       good.replace("reason:", "why:"), good + "\nEOF2"):
            with pytest.raises((AssertionError, SystemExit, UsageError)):
                _parse(broken, fenced=True)
    else:
        with pytest.raises(AssertionError):
            _parse(good, fenced=False)


def test_a_stage_launch_failure_keeps_the_stages_own_abandon_remedy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The stage's remedy is abandoning the intent; an `invoke cancel` alone leaves it unresolved and the subject
    blocked (#313 review, F4). The abandon command comes with its revision and a `rationale:` body."""
    message = _stage(monkeypatch, tmp_path, harness_contract.UNCONFIRMED)
    abandon = [args for command, fenced in _commands(message)
               if (args := _parse(command, fenced=fenced)).__dict__.get("stage_cmd") == "abandon"]
    assert [(a.intent, a.expect_rev, a.rationale) for a in abandon] == [("SI-0003", 17, "stage launch failed")]
    assert len(message) < 2000  # the intent keeps its stopped error's message[:2000]


def test_a_relaunch_hint_without_an_invocation_names_where_to_find_one() -> None:
    """With no id in reach the placeholder names its source; it is never a bare `<INV>` (#313 review, F1)."""
    with pytest.raises(MessagingSnapshotMismatch) as raised:
        send_route("disabled", "enabled", "next-step")
    assert "aew harness launch <invocation from aew harness status> --expect-rev" in raised.value.message
    assert "<INV>" not in raised.value.message


def test_a_quote_in_a_printed_reason_is_escaped_so_the_body_still_parses() -> None:
    block = harness_contract.fields_command("aew invoke cancel INV-1 --expect-rev <revision from aew status>",
                                            "reason", "it's done")
    [(command, fenced)] = _commands(block)
    assert fenced and "reason: 'it''s done'" in command
    filled = command.replace(REVISION, "17")
    head, _, rest = filled.partition(" <<'EOF'\n")
    parser = build_parser()
    old_stdin = sys.stdin
    try:
        sys.stdin = StringIO(rest.removesuffix("\nEOF"))
        args = parser.parse_args(fields.expand(shlex.split(head)[1:], parser))
    finally:
        sys.stdin = old_stdin
    assert args.reason == "it's done"


def test_harness_send_hands_the_runs_invocation_to_the_route_it_refuses_with(monkeypatch: pytest.MonkeyPatch) -> None:
    """`harness send` knows the run it was given, so its mismatch refusal names that run's invocation (#313 review,
    F1). The route is decided inside `_lead_request`'s admit; this drives it with a run whose snapshot disagrees."""
    harness = Harness.__new__(Harness)
    harness.coordination = SimpleNamespace(project_switch=lambda _state: "disabled")
    monkeypatch.setattr("aew.engine.harness_ops.run_messaging_snapshot", lambda _entry: "enabled")
    monkeypatch.setattr("aew.engine.harness_ops.SNAPSHOT_RECORDED", True)
    admitted: list[Callable[[dict[str, object], dict[str, object]], None]] = []

    def capture(_token: str, _run: str, _kind: str, _payload: dict[str, str], *, current: bool, admit: Callable[
            [dict[str, object], dict[str, object]], None]) -> dict[str, object]:
        admitted.append(admit)
        return {}

    monkeypatch.setattr(harness, "_lead_request", capture, raising=False)
    harness.harness_send(token="token", run="R-INV-0012-1", text="hello")
    with pytest.raises(MessagingSnapshotMismatch) as raised:
        admitted[0]({}, {"run": "R-INV-0012-1"})
    assert "`aew harness launch INV-0012 --expect-rev <revision from aew status>`" in raised.value.message
