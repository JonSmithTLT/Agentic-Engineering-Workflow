"""The `aew-lead` MCP transport without a harness (F15.1 slice C; typed-lead-surface-design-v0.2 §4): the framing,
profile filtering and the context budget, adapter errors that never reach the broker, the fail-closed start, the
custody properties a static reading can prove, and the Lead projection against the pinned OpenCode 2.0.18 schema."""

from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from aew.harness import contract as K
from aew.harness.opencode import capabilities, projection
from aew.surface import contract, mcp
from aew.surface.errors import AdapterInputError

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "opencode"
SPEC = json.loads((FIXTURES / "openapi-2.0.18.min.json").read_text(encoding="utf-8"))


def _result(ok: bool = True) -> dict[str, Any]:
    return {"ok": ok, "revision": 7, "tool": "status"}


class Spy:
    def __init__(self, reply: Any = None, raises: Exception | None = None) -> None:
        self.calls: list[tuple[str, Any, str]] = []
        self.reply, self.raises = reply or _result(), raises

    def __call__(self, name, arguments, profile):
        self.calls.append((name, arguments, profile))
        if self.raises:
            raise self.raises
        return self.reply


def rpc(server, method, params=None, rid=1):
    return server.handle({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


# ---------------------------------------------------------------------------------------------- the protocol


def test_the_handshake_echoes_a_known_revision_or_answers_with_the_newest():
    server = mcp.Server(Spy())
    for asked in mcp.PROTOCOL_VERSIONS:
        assert rpc(server, "initialize", {"protocolVersion": asked})["result"]["protocolVersion"] == asked
    out = rpc(server, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert out["protocolVersion"] == mcp.PROTOCOL_VERSIONS[0]
    assert out["serverInfo"]["name"] == "aew-lead" and out["capabilities"] == {"tools": {"listChanged": False}}
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None and server.initialized
    assert rpc(server, "ping")["result"] == {}
    assert rpc(server, "resources/list")["result"] == {"resources": []}
    assert rpc(server, "prompts/list")["result"] == {"prompts": []}
    assert rpc(server, "nope")["error"]["code"] == mcp.METHOD_NOT_FOUND


def test_the_normal_list_omits_the_cli_escape_and_designed_tools_and_fits_the_budget():
    normal = mcp.tools_list("normal")
    names = [t["name"] for t in normal["tools"]]
    # The exact list per slice (M4-E plan v3 §2.6): E2 adds `steering`, E3c `resolve`.
    assert names == ["status", "resume", "work_show", "explain", "harness_status", "harness_wait", "checkpoint",
                     "steering", "resolve"]
    recovery = [t["name"] for t in mcp.tools_list("recovery")["tools"]]
    assert recovery == [*names, "cli"]
    size = len(json.dumps(normal, separators=(",", ":")))
    assert size < 12_000 and len(names) <= 16, f"the normal advertised surface is {size} bytes"
    by_name = {t["name"]: t for t in normal["tools"]}
    assert by_name["status"]["annotations"]["readOnlyHint"] and by_name["harness_wait"]["annotations"]["idempotentHint"]
    assert not by_name["checkpoint"]["annotations"]["readOnlyHint"]
    assert not by_name["steering"]["annotations"]["readOnlyHint"]
    assert not by_name["resolve"]["annotations"]["readOnlyHint"]
    # Under §2.6's 11,900-byte stop line with every M4-E tool built: E3c's `resolve` takes no more than the 771 bytes
    # the plan measured for it with E5's dispositions (5,135 bytes at E3c).
    assert len(json.dumps(by_name["resolve"], separators=(",", ":"))) <= 771
    assert all("title" not in t["annotations"] for t in normal["tools"])  # trimmed (plan v3 §2.6)
    assert all("outputSchema" not in t for t in normal["tools"])  # the result is structured content, not advertised


def test_a_call_returns_the_stage_result_as_structured_content_with_is_error_from_ok():
    spy = Spy()
    out = rpc(mcp.Server(spy), "tools/call", {"name": "status", "arguments": {}})["result"]
    assert out["structuredContent"] == _result() and out["isError"] is False
    assert json.loads(out["content"][0]["text"]) == _result()
    assert spy.calls == [("status", {}, "normal")]
    refused = rpc(mcp.Server(Spy(_result(ok=False))), "tools/call", {"name": "status"})["result"]
    assert refused["isError"] is True and refused["structuredContent"]["ok"] is False  # not discarded


@pytest.mark.parametrize(("profile", "params", "code"), [
    ("normal", {"name": "nope", "arguments": {}}, "UNKNOWN_TOOL"),
    ("normal", {"name": "ticket_start", "arguments": {"expect_rev": 1, "work_id": "T-0001"}}, "TOOL_NOT_BUILT"),
    ("normal", {"name": "cli", "arguments": {"argv": ["status"]}}, "TOOL_NOT_EXPOSED"),
    ("normal", {"name": "checkpoint", "arguments": {"expect_rev": "one"}}, "INVALID_ARGUMENTS"),
    ("recovery", {"name": "status", "arguments": "not an object"}, "INVALID_ARGUMENTS"),
])
def test_ill_formed_calls_are_input_errors_that_never_reach_the_broker(profile, params, code):
    spy = Spy()
    out = rpc(mcp.Server(spy, profile=profile), "tools/call", params)
    assert out["error"]["code"] == mcp.INVALID_PARAMS
    assert out["error"]["data"]["adapter_input_error"]["code"] == code
    assert spy.calls == []


def test_an_unreachable_broker_is_a_transport_error_and_nothing_is_claimed_about_aew():
    spy = Spy(raises=AdapterInputError("BROKER_UNREACHABLE", "the Lead broker could not be reached: closed"))
    out = rpc(mcp.Server(spy), "tools/call", {"name": "status", "arguments": {}})
    assert out["error"]["code"] == mcp.BROKER_UNREACHABLE and "result" not in out
    assert out["error"]["data"]["adapter_input_error"]["code"] == "BROKER_UNREACHABLE"


def test_malformed_input_is_a_protocol_error_and_the_session_survives(capsys):
    server = mcp.Server(Spy(raises=RuntimeError("defect")))
    assert server.handle_line("{not json")[0]["error"]["code"] == mcp.PARSE_ERROR
    assert server.handle_line("[]")[0]["error"]["code"] == mcp.INVALID_REQUEST
    assert server.handle({"id": 1, "method": "ping"})["error"]["code"] == mcp.INVALID_REQUEST
    assert server.handle({"jsonrpc": "2.0", "id": 3, "result": {}}) is None  # a response: ignored
    batch = server.handle_line(json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                           {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                           {"jsonrpc": "2.0", "id": 2, "method": "ping"}]))
    assert len(batch) == 1 and [r["id"] for r in batch[0]] == [1, 2]  # one array per batch (PR #95 re-review)
    assert server.handle_line(json.dumps([{"jsonrpc": "2.0", "method": "notifications/initialized"}])) == []
    defect = rpc(server, "tools/call", {"name": "status", "arguments": {}})
    assert defect["error"]["code"] == mcp.INTERNAL_ERROR and rpc(server, "ping")["result"] == {}


def test_stdout_carries_the_protocol_only():
    import io

    stdin = io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n\n{"jsonrpc":"2.0","method":"notifications/x"}\n')
    stdout = io.BytesIO()
    assert mcp.Server(Spy()).serve(stdin, stdout) == 0
    lines = stdout.getvalue().decode("utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


def test_ingress_is_read_while_a_tool_waits_and_every_call_is_answered():
    """A `harness_wait` in flight never queues the next request on the same connection (PR #95 review): a status
    and a ping sent after it are answered while it still blocks, and at end of input it is still answered."""
    import os
    import threading

    release = threading.Event()

    def forward(name, arguments, profile):
        if name == "harness_wait":
            release.wait(30)
        return {"ok": True, "revision": 7, "tool": name}

    read_end, write_end = os.pipe()
    out_read, out_write = os.pipe()
    stdin, stdout, replies = os.fdopen(read_end, "rb"), os.fdopen(out_write, "wb"), os.fdopen(out_read, "rb")
    feed = os.fdopen(write_end, "wb")
    server = threading.Thread(target=lambda: (mcp.Server(forward).serve(stdin, stdout), stdout.close()))
    server.start()
    for rid, method, params in [(1, "tools/call", {"name": "harness_wait", "arguments": {"runs": ["R-1"]}}),
                                (2, "tools/call", {"name": "status", "arguments": {}}), (3, "ping", {})]:
        feed.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n").encode())
        feed.flush()
    early = {json.loads(replies.readline())["id"] for _ in range(2)}
    assert early == {2, 3} and not release.is_set()  # answered while the wait still blocks
    feed.close()  # end of input with the wait in flight
    release.set()
    last = json.loads(replies.readline())
    assert last["id"] == 1 and last["result"]["structuredContent"]["tool"] == "harness_wait"
    server.join(10)
    assert not server.is_alive() and replies.read() == b""


# ---------------------------------------------------------------------------------------------- custody


def test_it_serves_only_inside_a_live_lead_session():
    base = {"PATH": "/usr/bin"}
    assert "live Lead session" in mcp.environment_problem(base)
    session = {**base, "AEW_LEAD_BROKER": "pipe", "AEW_LEAD_BROKER_KEY": "00" * 32}
    assert mcp.environment_problem(session) is None
    for name in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_AGENT_KEY"):
        assert name in mcp.environment_problem({**session, name: "x"})
    assert "credential-shaped" in mcp.environment_problem({**session, "OTHER": "aew1.tk_" + "a" * 16 + "." + "b" * 24})


def test_its_refusal_list_covers_every_credential_variable_but_the_brokers_own_coordinates():
    assert set(K.CREDENTIAL_ENV) - {"AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"} <= set(mcp.FORBIDDEN_ENV)
    assert set(mcp.FORBIDDEN_ENV) <= set(K.CREDENTIAL_ENV)


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def test_the_mcp_process_has_no_path_to_authority():
    """No engine, no runner, no token: statically, and in a fresh interpreter that imports the transport."""
    source = ROOT / "src" / "aew" / "surface" / "mcp.py"
    imported = _imports(source)
    assert not any(m.startswith("aew.engine") or m in ("aew.surface.run", "aew.surface.projection",
                                                       "aew.surface.classify", "subprocess") for m in imported)
    text = source.read_text(encoding="utf-8")
    assert "Engine" not in text.replace("Engine remains", "") and "_lead_token" not in text
    tree = ast.parse(text)
    forbidden = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "FORBIDDEN_ENV" for t in n.targets))
    uses = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "AEW_LEAD_TOKEN"]
    # the one use in code: the list of variables whose presence refuses the start
    assert len(uses) == 1 and uses[0] in list(ast.walk(forbidden))
    handler = ast.get_source_segment((ROOT / "src/aew/cli/commands.py").read_text(encoding="utf-8"), next(
        n for n in ast.walk(ast.parse((ROOT / "src/aew/cli/commands.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "_lead_mcp"))
    assert handler and "_engine" not in handler and "_lead_token" not in handler and "token" not in handler
    probe = subprocess.run([sys.executable, "-c", "import sys, aew.surface.mcp; "
                            "print(sorted(m for m in sys.modules if m.startswith('aew.engine')))"],
                           capture_output=True, text=True, timeout=60, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    assert probe.stdout.strip() == "[]"


# ---------------------------------------------------------------------------------------------- the Lead projection


def _schema_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]})


def test_the_lead_projection_matches_the_pinned_opencode_configuration_schema():
    config = projection.lead_config("guide text")
    errors = sorted(_schema_validator("Config.InfoEncoded").iter_errors(config), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:5]]
    server = config["mcp"]["servers"]["aew-lead"]
    assert server == {"type": "local", "command": ["aew", "lead", "mcp"], "codemode": False}
    assert "environment" not in server  # the server inherits the curated session environment, and nothing more
    rules = config["agents"]["aew-lead"]["permissions"]
    assert {"action": "aew-lead_*", "effect": "allow", "resource": "*"} in rules


def test_the_probe_fails_closed_on_a_release_that_respells_mcp_configuration():
    assert capabilities.problems(SPEC) == []
    for schema, field in (("Config.InfoEncoded", "mcp"), ("Mcp.LocalConfigEncoded", "codemode"),
                          ("Mcp.LocalConfigEncoded", "command")):
        doctored = copy.deepcopy(SPEC)
        del doctored["components"]["schemas"][schema]["properties"][field]
        assert capabilities.problems(doctored), (schema, field)
    doctored = copy.deepcopy(SPEC)
    doctored["components"]["schemas"]["Config.InfoEncoded"]["properties"]["mcp"]["properties"].pop("servers")
    assert capabilities.problems(doctored)


def test_the_catalogs_listed_tools_are_its_built_rows_only():
    assert {t.name for t in contract.exposed("recovery")} == {t.name for t in contract.TOOLS.values() if t.built}


def test_a_tool_call_without_an_id_is_dropped_unrun(capsys):
    """MCP requests carry an id: a `tools/call` without one would commit with no reply, so it never reaches the
    broker (PR #95 re-review)."""
    spy = Spy()
    server = mcp.Server(spy)
    assert server.handle({"jsonrpc": "2.0", "method": "tools/call",
                          "params": {"name": "checkpoint", "arguments": {"expect_rev": 3}}}) is None
    assert server.handle({"jsonrpc": "2.0", "method": "ping"}) is None
    assert spy.calls == []
    assert "dropped tools/call sent without an id" in capsys.readouterr().err


def test_waits_never_hold_every_worker():
    """However many waits are in flight, a status is answered at once: waits have a lane of their own (PR #95
    re-review: eight waits held all eight workers, and a status queued behind them)."""
    import os
    import threading

    release = threading.Event()
    waiting = threading.Semaphore(0)

    def forward(name, arguments, profile):
        if name == "harness_wait":
            waiting.release()
            release.wait(30)
        return {"ok": True, "revision": 7, "tool": name}

    read_end, write_end = os.pipe()
    out_read, out_write = os.pipe()
    stdin, stdout, replies = os.fdopen(read_end, "rb"), os.fdopen(out_write, "wb"), os.fdopen(out_read, "rb")
    feed = os.fdopen(write_end, "wb")
    server = threading.Thread(target=lambda: (mcp.Server(forward).serve(stdin, stdout), stdout.close()))
    server.start()
    waits = mcp.MAX_WAITS + 2
    try:
        for rid in range(1, waits + 1):
            feed.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                    "params": {"name": "harness_wait", "arguments": {"runs": ["R-1"]}}}) + "\n")
                       .encode())
        feed.flush()
        for _ in range(mcp.MAX_WAITS):
            assert waiting.acquire(timeout=10)  # every wait worker is blocked
        feed.write((json.dumps({"jsonrpc": "2.0", "id": 100, "method": "tools/call",
                                "params": {"name": "status", "arguments": {}}}) + "\n").encode())
        feed.flush()
        first = json.loads(replies.readline())
        assert first["id"] == 100 and not release.is_set()  # answered while all the waits still block
    finally:
        feed.close()
        release.set()
    rest = {json.loads(replies.readline())["id"] for _ in range(waits)}
    assert rest == set(range(1, waits + 1))
    server.join(10)
    assert not server.is_alive()


def test_a_call_with_malformed_params_is_answered_and_the_server_reads_on():
    """Routing a call to its lane reads its tool name on the reader thread: params that are not an object get the
    protocol error and the next request is still answered (PR #95 re-review: they ended the server)."""
    import io

    lines = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1]},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": "x"},
             [{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": ["harness_wait"]}],
             {"jsonrpc": "2.0", "id": 4, "method": "ping"}]
    stdin = io.BytesIO("".join(json.dumps(m) + "\n" for m in lines).encode())
    stdout = io.BytesIO()
    assert mcp.Server(Spy()).serve(stdin, stdout) == 0
    out = [json.loads(line) for line in stdout.getvalue().decode().splitlines()]
    flat = [r for o in out for r in (o if isinstance(o, list) else [o])]
    assert {r["id"]: r.get("error", {}).get("code") for r in flat} == {1: mcp.INVALID_PARAMS, 2: mcp.INVALID_PARAMS,
                                                                      3: mcp.INVALID_PARAMS, 4: None}

