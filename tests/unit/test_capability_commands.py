"""`aew capability` and its operator authorization (STG-15, CAP-1; A-38: CAPR-05; the designer's CAP-1 ruling 1).

`list` and `check` need no authorization. `import`, `add`, `remove` and `host-copies` are the operator's: each asks the
project's operator endpoint once, whose console shows the exact change and a code typed back at the requesting
terminal, and the endpoint applies what it showed. They are on no agent's surface: the Lead broker refuses them, no
typed tool runs them and the worker bridge offers no such operation. `check` is never a Lead session's either.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from capability_stand_in import _bundle, _plant_host_copy, make_register
from conftest import run_aew

from aew import errors, operator
from aew.capability import records, status, store
from aew.cli.capability_commands import refuse_lead_session
from aew.cli.main import build_parser, main
from aew.engine.api import Engine
from aew.engine.custody_ops import LEAD_SESSION, LEAD_SESSION_VARS
from aew.harness import bridge, lead_broker, operator_client, operator_endpoint
from aew.surface import contract

CHANGES = (["capability", "import", "bundle"], ["capability", "add", "record.yaml"],
           ["capability", "remove", "fake"], ["capability", "host-copies", "off"])


@pytest.fixture
def reg(tmp_path, monkeypatch):
    return make_register(tmp_path, monkeypatch)


class Console:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str) -> None:
        self.lines.append(text)

    def code(self) -> str:
        found = re.findall(r"confirmation code ([0-9A-F]{6})", "".join(self.lines))
        assert found, self.lines
        return found[-1]


@pytest.fixture
def endpoint(project):
    console = Console()
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=console, dev=True, timeout=10)
    ep.start()
    yield ep, console
    ep.close()


def _run(capsys, *argv: str) -> tuple[int, Any, Any]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, json.loads(out) if out.strip().startswith("{") else out, json.loads(err) if err.strip() else None


# ---------------------------------------------------------------------------------------------- no agent's surface


def test_the_register_changes_are_refused_by_the_lead_broker_and_its_recovery_escape():
    """The broker's `run_cli` (where the relay of `lead.cli` and the typed surface's `cli` escape, the recovery
    profile's included, both end) refuses the four changes with the register's own refusal, saying whose they are and
    what to do, not the generic "run this one directly" (review F8); `check` is refused there too."""
    for argv in CHANGES:
        with pytest.raises(errors.PermissionDenied) as exc:
            lead_broker.run_cli(object(), "token", list(argv), ".", "", channel="lead_broker")
        assert "capability register" in exc.value.message and "operator endpoint" in exc.value.message, argv
        assert "aew capability list" in exc.value.message, argv
    with pytest.raises(errors.PermissionDenied):
        lead_broker.run_cli(object(), "token", ["capability", "check", "--offline"], ".", "", channel="lead_broker")
    parser = build_parser()
    for argv in (["capability", "list"], ["capability", "check"]):  # no authority: not operator-only
        assert lead_broker.refuses_locally(parser.parse_args(argv)) is None, argv


def test_no_typed_tool_and_no_worker_bridge_operation_runs_a_register_command():
    assert not [t for t in contract.TOOLS.values()
                if "capability" in t.name or any(p.startswith("capability") for p in t.expands_to)]
    assert not [op for op in bridge.OPERATIONS if "capability" in op]


def test_a_lead_session_is_refused_every_register_change_and_the_check(project):
    for argv in [*CHANGES, ["capability", "check", "--offline"]]:
        res = run_aew("-C", str(project.root), *argv, env={"AEW_LEAD_BROKER": "x", "AEW_LEAD_BROKER_KEY": "y"})
        error = json.loads(res.stderr)["error"]
        assert res.returncode != 0 and "Lead session" in error["message"], (argv, res.stderr)
        assert error["code"] in ("USAGE", "PERMISSION_DENIED"), error  # the client's refusal, or the command's own


def test_an_aew_a_test_starts_writes_the_sessions_register_never_the_hosts(tmp_path):
    """Review F2: a child `aew` gets the session's own register base (conftest's ``clean_env``), so its check writes
    there; the session's end checks the host's register is as the session found it."""
    import conftest

    assert conftest.CHILD_DATA_BASE is not None
    res = run_aew("-C", str(tmp_path), "capability", "check", "--offline", "--json")  # first: it writes somewhere
    assert res.returncode == 0, res.stderr
    assert (conftest.CHILD_DATA_BASE / "aew" / "capability" / store.REGISTER).is_file()
    name = store.base_variable()
    assert conftest.clean_env()[name] == str(conftest.CHILD_DATA_BASE)
    assert conftest.clean_env({name: str(tmp_path)})[name] == str(tmp_path)  # a test's own base stays its own


def test_the_check_refuses_in_a_lead_sessions_environment_naming_it():
    with pytest.raises(errors.PermissionDenied) as exc:
        refuse_lead_session("check", {v: "x" for v in LEAD_SESSION_VARS})
    assert exc.value.details == {"variables": list(LEAD_SESSION_VARS), "reason": LEAD_SESSION}
    refuse_lead_session("check", {})


# ---------------------------------------------------------------------------------------------- the commands


def test_list_reads_the_hosts_register_outside_any_project(reg, tmp_path, capsys):
    code, out, _ = _run(capsys, "-C", str(tmp_path), "capability", "list", "--json")
    assert code == 0 and out["root"] == str(reg["root"])
    assert [c["id"] for c in out["capabilities"]] == ["FAKE_SEARCH"]
    assert out["capabilities"][0]["observed_status"] == status.UNAVAILABLE
    code, text, _ = _run(capsys, "-C", str(tmp_path), "capability", "list")
    assert code == 0 and "FAKE_SEARCH" in text and "UNAVAILABLE" in text


def test_check_runs_without_authorization_and_writes_only_status(reg, tmp_path, monkeypatch, capsys):
    _plant_host_copy(reg, monkeypatch)
    code, out, _ = _run(capsys, "-C", str(tmp_path), "capability", "check", "--offline", "--json")
    assert code == 0 and out["capabilities"][0]["observed_status"] == status.FUNCTIONAL_ONLY
    state = store.read()
    assert state["operator_records"] == {} and state["host_copies"] is True and set(state["checks"]) == {
        f"{status.HOST_COPY}:fake"}
    assert not (reg["root"] / store.CHANGES).exists()  # no operator change was made


def test_a_change_without_a_terminal_is_refused_before_the_endpoint_is_asked(project, reg, monkeypatch, capsys):
    monkeypatch.setattr(operator, "has_terminal", lambda: False)
    code, _, err = _run(capsys, "-C", str(project.root), "capability", "host-copies", "off")
    assert code != 0 and err["error"]["code"] == "OPERATOR_AUTHORIZATION_REQUIRED"
    assert "aew operator serve --dev" in err["error"]["message"]
    assert store.read()["host_copies"] is True


def test_an_add_of_a_record_too_large_for_the_endpoint_is_refused_before_anything_is_sent(project, reg, monkeypatch,
                                                                                          capsys, tmp_path):
    """Review F12: a record file over the endpoint request's bound is refused at the requesting terminal, typed, with
    the limit, and the endpoint is never asked (over 16 KiB it was an untyped `bad message length`)."""
    from aew.capability import ops

    asked: list[Any] = []
    monkeypatch.setattr(operator, "has_terminal", lambda: True)
    monkeypatch.setattr(operator_client, "request_capability_change", lambda *a, **k: asked.append(a))
    wide = "# " + "\u00e9" * (ops.MAX_RECORD_TEXT // 2)  # two bytes each: the bound falls inside a character
    for size, body in ((ops.MAX_RECORD_TEXT + 1, b"#" * (ops.MAX_RECORD_TEXT + 1)), (20 * 1024, b"#" * 20 * 1024),
                       (len(wide.encode()), wide.encode())):
        record = tmp_path / f"record-{size}.yaml"
        record.write_bytes(body)
        code, _, err = _run(capsys, "-C", str(project.root), "capability", "add", str(record))
        assert code != 0 and err["error"]["code"] == "USAGE", err
        assert err["error"]["details"]["limit"] == ops.MAX_RECORD_TEXT and str(record) in err["error"]["message"]
    assert asked == []


def test_a_change_with_no_endpoint_running_says_how_the_operator_authorizes_it(project, reg, monkeypatch, capsys):
    monkeypatch.setattr(operator, "has_terminal", lambda: True)
    code, _, err = _run(capsys, "-C", str(project.root), "capability", "host-copies", "off")
    assert code != 0 and err["error"]["code"] == "NOT_FOUND"
    assert "aew operator serve --dev" in err["error"]["message"]
    assert store.read()["host_copies"] is True


# ---------------------------------------------------------------------------------------------- the endpoint


def test_a_change_needs_the_code_shown_on_the_endpoints_console(project, reg, endpoint):
    ep, console = endpoint
    prompts: list[str] = []

    def wrong(prompt: str) -> str:
        prompts.append(prompt)
        return "000000"

    with pytest.raises(errors.PermissionDenied):
        operator_client.request_capability_change(project.root / ".aew", "host_copies", {"on": False}, ask=wrong,
                                                  requester="test")
    assert store.read()["host_copies"] is True and not (reg["root"] / store.CHANGES).exists()
    shown = "".join(console.lines)
    assert "TURN host copies OFF" in shown and "change digest" in shown and "guarantee           : dev" in shown

    def right(prompt: str) -> str:
        prompts.append(prompt)
        return console.code()

    out = operator_client.request_capability_change(project.root / ".aew", "host_copies", {"on": False}, ask=right,
                                                    requester="test")
    assert out["applied"] == "host_copies" and store.read()["host_copies"] is False
    assert console.code() not in "".join(prompts)  # the code is on the endpoint's console, never at the requester
    log = json.loads((reg["root"] / store.CHANGES).read_text(encoding="utf-8").splitlines()[-1])
    assert log["principal"]["endpoint"]["pid"] == ep.pid and log["principal"]["guarantee"] == "dev"


def test_a_change_the_register_moved_under_is_refused_at_the_requesting_terminal(project, reg, endpoint):
    """Review F10, end to end: another change lands while the operator types the code, so the endpoint refuses the
    shown one, and the requesting terminal gets VALIDATION_FAILED, reason register_changed (the surface map's)."""
    from capability_stand_in import _principal

    from aew.capability import ops

    _, console = endpoint

    def another_lands_then_answer(prompt: str) -> str:
        ops.apply(_principal(), ops.preview(ops.HOST_COPIES, {"on": False}))
        return console.code()

    with pytest.raises(errors.ValidationFailed) as exc:
        operator_client.request_capability_change(project.root / ".aew", "host_copies", {"on": False},
                                                  ask=another_lands_then_answer, requester="test")
    assert exc.value.code == "VALIDATION_FAILED" and exc.value.details.get("reason") == "register_changed"
    assert len((reg["root"] / store.CHANGES).read_text(encoding="utf-8").splitlines()) == 1  # only the other's


def test_the_endpoint_applies_the_bundle_it_showed_not_what_is_there_after(project, reg, endpoint):
    """What the operator approved is what is applied: the import's archive is the bytes the endpoint read for the
    preview, so a bundle swapped while the code is being typed changes nothing."""
    _, console = endpoint
    bundle = _bundle(reg)

    def swap_then_answer(prompt: str) -> str:
        tampered = bytearray(reg["archive"])
        tampered[20] ^= 1
        (bundle / "fake-1.0.tar.gz").write_bytes(bytes(tampered))
        return console.code()

    out = operator_client.request_capability_change(project.root / ".aew", "import", {"path": str(bundle)},
                                                    ask=swap_then_answer, requester="test")
    assert [i["provider"] for i in out["imported"]] == ["fake"]
    pinned = records.shipped()["fake"]["payloads"][records.platform_key()]
    assert pinned["archive_sha256"] in "".join(console.lines)
    from aew.capability import ops

    assert next(c for c in ops.listing()["capabilities"])["observed_status"] == status.FUNCTIONAL_ONLY


def test_a_change_refused_at_its_preview_never_reaches_the_operator(project, reg, endpoint):
    _, console = endpoint
    with pytest.raises(errors.NotFound):
        operator_client.request_capability_change(project.root / ".aew", "remove", {"name": "fake"},
                                                  ask=lambda p: "x", requester="test")
    with pytest.raises(errors.UsageError):
        operator_client.request_capability_change(project.root / ".aew", "unknown", {}, ask=lambda p: "x",
                                                  requester="test")
    assert console.lines == []


def test_the_endpoint_offers_the_register_change(project, endpoint):
    assert "capability_change" in operator_client.ping(Path(project.root) / ".aew")["operations"]
