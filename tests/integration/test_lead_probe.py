"""Offline checks of the E231 probe. The local fixtures do not run OpenCode."""

from __future__ import annotations

import errno
import http.client
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import lead_text

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
from harness_qualify import model, opencode  # noqa: E402
from lead_probe import __main__ as cli  # noqa: E402
from lead_probe import listchanged, measure, network, standin  # noqa: E402

ARGV = ["--binary", "unusable-binary", "--out", "uncreated-output"]
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def loopback(monkeypatch):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(network.socket, "if_nameindex", lambda: [(1, "lo")])
    monkeypatch.setattr(network, "default_routes", lambda: [])


@pytest.mark.parametrize("problem", [None, TimeoutError(), OSError(errno.EACCES, "unexpected failure")])
def test_the_probe_starts_nothing_when_a_real_route_is_open(monkeypatch, tmp_path, problem):
    loopback(monkeypatch)
    monkeypatch.setenv(cli.REEXEC, "1")

    def connect(*_args, **_kwargs):
        if problem is not None:
            raise problem
        return socket.socket()

    monkeypatch.setattr(socket, "create_connection", connect)
    monkeypatch.setattr(cli, "measure", lambda *_: pytest.fail("probe reached the binary"))
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: pytest.fail("unexpected spawn"))
    binary = tmp_path / "placeholder"
    binary.touch()
    assert cli.main(["--binary", str(binary), "--out", str(tmp_path / "out")]) == 2


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_the_probe_refuses_where_no_loopback_namespace_exists(monkeypatch, capsys, platform):
    monkeypatch.delenv(cli.REEXEC, raising=False)
    monkeypatch.setattr(cli.sys, "platform", platform)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: pytest.fail("unexpected spawn"))
    assert cli.main(ARGV) == 2
    expected = "Windows is not supported" if platform == "win32" else "unshare not found"
    assert expected in capsys.readouterr().err


def test_no_flag_or_variable_skips_the_namespace(monkeypatch, tmp_path):
    loopback(monkeypatch)
    monkeypatch.setenv(cli.REEXEC, "1")
    monkeypatch.setattr(network.socket, "if_nameindex", lambda: [(1, "lo"), (2, "eth0")])
    monkeypatch.setattr(cli, "measure", lambda *_: pytest.fail("forged marker reached the binary"))
    binary = tmp_path / "placeholder"
    binary.touch()
    args = ["--binary", str(binary), "--out", str(tmp_path / "out")]
    assert cli.main(args) == cli.main([*args, "--no-network"]) == 2
    monkeypatch.delenv(cli.REEXEC)
    monkeypatch.setenv("HQ_UNSHARE_NET", "1")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/" + name)
    calls = []

    def spawn(cmd, *, env, check):
        calls.append((cmd, env[cli.REEXEC], check))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", spawn)
    assert cli.main(ARGV) == 0
    [(cmd, marker, _check)] = calls
    assert cmd[:2] == ["/usr/bin/unshare", "-rn"] and marker == "1"


def test_listchanged_config_denies_keyless_providers_and_uses_a_loopback_upstream(tmp_path):
    catalog = ["opencode", "opencode-go"]
    assert set(cli.prove_catalog(catalog)) >= set(catalog)
    with pytest.raises(ValueError, match="new-keyless"):
        cli.prove_catalog([*catalog, "new-keyless"])
    config = listchanged.config("http://127.0.0.1:3/v1", True, "after", tmp_path / "methods")
    assert config["experimental"]["policies"] == projection.lead_provider_policies()
    assert config["providers"]["openai"]["settings"]["baseURL"] == "http://127.0.0.1:3/v1"
    with pytest.raises(ValueError, match="loopback"):
        listchanged.config("http://192.0.2.1:3/v1", False, "before", tmp_path / "methods")


@pytest.mark.parametrize("value", [opencode.SYNTHETIC_KEY, "fixture-lead-credential"])
def test_a_body_carrying_the_key_or_lead_credential_is_flagged(tmp_path, value):
    body = {"input": [value]}
    with pytest.raises(ValueError, match="body withheld"):
        measure.save_requests(tmp_path / "requests", [{"body": body, "wire": json.dumps(body)}],
                              "fixture-lead-credential")
    assert not list((tmp_path / "requests").iterdir())


def test_the_scripted_model_records_each_requests_received_bytes():
    server = model.start("responses", [], capture_wire=True)
    try:
        host, port = server.base_url.split("/")[2].split(":")
        conn = http.client.HTTPConnection(host, int(port), timeout=5)
        try:
            for body in (b'{ "input": []  }\n', b'{"input":[]}'):
                conn.request("POST", "/v1/responses", body)
                assert conn.getresponse().read()
            assert [row["raw_bytes"] for row in server.requests] == [17, 12]
        finally:
            conn.close()
    finally:
        server.close()


def fixture_request():
    guide = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS)
    system = projection.lead_config()["agents"][projection.LEAD_AGENT]["system"]
    body = {"instructions": f"{system}\n\n{guide}\n<env>synthetic</env>", "tools": [
        {"name": measure.LEAD_PREFIXES[0] + "status", "parameters": {"$defs": {}, "$ref": "#"}},
        {"name": "shell", "parameters": {}},
    ], "input": [{"role": "user", "content": "synthetic"}]}
    wire = json.dumps(body, ensure_ascii=False).encode()
    return {"body": body, "raw_bytes": len(wire)}, guide, system


def test_a_lead_requests_parts_sum_to_its_body():
    request, guide, system = fixture_request()
    parts = measure.request_parts(request, guide=guide, system=system)
    represented = (sum(parts["instruction_bytes"].values()) + sum(parts["aew_tool_bytes"].values())
                   + sum(parts["builtin_tool_bytes"].values()) + sum(parts["input_bytes"].values())
                   + parts["other_field_bytes"])
    assert parts["raw_bytes"] == represented + parts["wire_framing_and_encoding_bytes"]
    assert parts["instruction_bytes"]["environment"] == len("<env>synthetic</env>")
    assert set(parts["aew_tool_bytes"]) == {"status"} and set(parts["builtin_tool_bytes"]) == {"shell"}
    assert parts["input_bytes"]["first_user"] == measure.size(request["body"]["input"][0])
    assert parts["other_field_bytes"] == 0


def test_the_guide_and_aew_tools_split_by_their_owners_names(monkeypatch):
    request, guide, system = fixture_request()
    guide = guide.replace(guide.splitlines()[0], "# Synthetic renderer heading", 1)
    request["body"]["instructions"] = f"{system}\n\n{guide}"
    request["body"]["tools"][0]["name"] = "fixture-server_status"
    monkeypatch.setattr(measure, "LEAD_PREFIXES", ("fixture-server_",))
    parts = measure.request_parts(request, guide=guide, system=system)
    assert parts["instruction_bytes"]["guide"] == measure.size(guide) - 2
    assert parts["aew_tool_features"]["status"] == {"annotations": False, "$defs": True, "$ref": True}


def test_typed_and_relayed_results_pair_by_call_id():
    parts = [
        {"type": "function_call", "name": measure.LEAD_PREFIXES[0] + "status", "call_id": "typed"},
        {"type": "function_call", "name": "shell", "call_id": "shell", "arguments": '{"command":"aew status"}'},
        {"type": "function_call_output", "call_id": "shell", "output": "short"},
        {"type": "function_call_output", "call_id": "typed", "output": "a longer reply"},
    ]
    rows = measure.results([{"body": {"input": parts[:2]}}, {"body": {"input": parts[2:]}}])
    assert [(r["route"], r["output_bytes"]) for r in rows] == [("typed", 14), ("relayed", 5)]


@pytest.mark.parametrize("declared,order", [("true", "before"), ("false", "after")])
def test_the_stand_in_declares_as_told_and_announces_after_its_first_call(tmp_path, declared, order):
    methods = [
        {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"id": 2, "method": "tools/list"},
        {"id": 3, "method": "tools/call"},
        {"id": 4, "method": "tools/list"},
        {"id": 5, "method": "tools/call"},
    ]
    proc = subprocess.run(
        [sys.executable, "-B", str(standin.__file__), declared, order, str(tmp_path / "methods")],
        input="".join(json.dumps(message) + "\n" for message in methods), text=True, capture_output=True,
        timeout=10, creationflags=FLAGS, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=True,
    )
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert replies[0]["result"]["capabilities"] == {"tools": {"listChanged": declared == "true"}}
    assert [r.get("id") for r in replies] == ([1, 2, None, 3, 4, 5] if order == "before" else [1, 2, 3, None, 4, 5])
    assert [t["name"] for t in replies[4]["result"]["tools"]] == [standin.FIRST, standin.ADDED]


def test_the_record_names_the_commit_binary_sha_and_network_proof(monkeypatch):
    loopback(monkeypatch)

    def blocked(*_args, **_kwargs):
        raise OSError(errno.ENETUNREACH, "no route")

    monkeypatch.setattr(socket, "create_connection", blocked)
    proof = network.prove()
    result = cli.record("a" * 40, "2.2.6", "b" * 64, proof, ["opencode"], ["opencode"])
    assert result["aew_commit"] == "a" * 40
    assert result["opencode"]["sha256"] == "b" * 64
    assert result["network"]["interfaces"] == ["lo"]
    assert set(result["network"]["unreachable"]) == {*network.NAMES, *network.ADDRESSES}


def test_the_pinned_version_accepts_the_binary_display_and_refuses_other_versions():
    assert cli.pinned_version("opencode v2.2.6") == cli.pinned_version("2.2.6") == "2.2.6"
    with pytest.raises(ValueError, match="unqualified"):
        cli.pinned_version("opencode v0.0.0")


def test_code_mode_bytes_end_before_the_mcp_section():
    code = "# Code Mode\nUse the scripted tools.\n"
    tags = "<mcp_instructions>mcp</mcp_instructions>\nskills preamble\n<available_skills>skills</available_skills>"
    counts = measure.instructions_parts(f"system\n\n# guide\n{code}{tags}", "# guide", "system")
    assert counts["code_mode"] == measure.size(code) - 2
    assert counts["other_instruction_text"] == measure.size("\n\n\n\nskills preamble\n") - 2


@pytest.mark.parametrize("line", ["zen/free model", "zen/free-model (free)", "@zen/free-model",
                                  "zen:eu/free-model", "zen\tfree-model"])
def test_catalog_refuses_and_saves_unparsed_output(monkeypatch, tmp_path, line):
    raw = f"opencode/big-pickle\n{line}\n"
    monkeypatch.setattr(cli, "run_binary", lambda *_: raw)
    with pytest.raises(ValueError, match="unparsed OpenCode models line"):
        cli.catalog(Path("unused"), tmp_path, {})
    assert (tmp_path / "models.txt").read_bytes() == raw.encode()


@pytest.mark.parametrize(("sha", "commit", "listing", "reason"), [
    ("wrong", "a" * 40, "opencode/example", "does not match the Linux x64 pin"),
    ("pinned", None, "opencode/example", "clean Git checkout"),
    ("pinned", "a" * 40 + "+dirty", "opencode/example", "clean Git checkout"),
    ("pinned", "a" * 40, "zen/example", "known keyless control provider"),
    ("pinned", "a" * 40, "opencode/example\nzen/example", "missing from the deny policy: zen"),
])
def test_measure_refuses_before_any_leg(monkeypatch, tmp_path, sha, commit, listing, reason):
    expected = cli.pinned_sha()
    monkeypatch.setattr(cli, "sha256_file", lambda _: expected if sha == "pinned" else sha)
    monkeypatch.setattr(cli, "aew_revision", lambda: commit)
    monkeypatch.setattr(cli, "run_binary", lambda *args: "opencode v2.2.6" if args[-1] == "--version" else listing)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match=reason):
        cli.measure(Path("unused"), out, [], {})
    assert not (out / "record.json").exists()


def test_linux_pin_is_valid_and_refuses_missing_or_malformed_digests(monkeypatch):
    version = cli.TESTED_VERSIONS[0]
    assert cli.pinned_sha(version) == cli.LEAD_PROBE_LINUX_X64_SHA256[version]
    with pytest.raises(ValueError, match="no valid Linux x64 probe hash"):
        cli.pinned_sha("unknown")
    monkeypatch.setitem(cli.LEAD_PROBE_LINUX_X64_SHA256, version, "x" * 64)
    with pytest.raises(ValueError, match="no valid Linux x64 probe hash"):
        cli.pinned_sha(version)


def test_measure_refuses_a_package_from_different_source(monkeypatch, tmp_path):
    import shutil

    source = tmp_path / "src/aew"
    source.mkdir(parents=True)
    (source / "__init__.py").write_bytes(b"original")
    installed = tmp_path / "installed"
    shutil.copytree(source, installed)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    init = installed / "__init__.py"
    cli.verify_package(init)
    init.write_bytes(b"changed!")
    monkeypatch.setattr(cli.aew, "__file__", str(init))
    monkeypatch.setattr(cli, "run_binary", lambda *_: pytest.fail("wrong package reached the binary"))
    with pytest.raises(ValueError, match="imported aew differs"):
        cli.measure(Path("unused"), tmp_path / "out", [], {})


def test_measure_refuses_a_leg_whose_private_python_imports_different_aew(monkeypatch, tmp_path):
    source = tmp_path / "src/aew"
    source.mkdir(parents=True)
    local_init = source / "__init__.py"
    local_init.write_bytes(b"checkout")
    other = tmp_path / "other"
    other.mkdir()
    other_init = other / "__init__.py"
    other_init.write_bytes(b"wrong package")
    binary = tmp_path / "opencode"
    binary.write_bytes(b"stub binary")
    digest = cli.sha256_file(binary)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.aew, "__file__", str(local_init))
    monkeypatch.setattr(cli, "pinned_sha", lambda: digest)
    monkeypatch.setattr(cli, "aew_revision", lambda: "a" * 40)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(
        cmd, 0, stdout=str(other_init).encode("utf-8"),
    ))
    monkeypatch.setattr(cli, "run_binary", lambda *_: pytest.fail("wrong private import reached the binary"))
    with pytest.raises(ValueError, match="imported aew differs"):
        cli.measure(binary, tmp_path / "out", ["worker"], {})


def test_inner_exit_is_returned_without_a_windows_hold(monkeypatch, capsys):
    loopback(monkeypatch)
    monkeypatch.delenv(cli.REEXEC, raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(cmd, 7))
    assert cli.main(ARGV) == 7
    assert "Windows" not in capsys.readouterr().err


def test_routes_follow_broker_tables(monkeypatch):
    from aew.harness import lead_broker

    assert measure.shell_route("aew status") == "relayed"
    assert measure.shell_route("aew work show T-0001") == "contained-local"
    monkeypatch.setitem(lead_broker.RELAYED_READS, frozenset({"work", "show"}), frozenset())
    assert measure.shell_route("aew work show T-0001") == "relayed"
    assert measure.shell_route("echo synthetic") == measure.shell_route("aew made-up") == "other"


def test_reanalysis_uses_saved_text_and_keeps_the_measured_commit(monkeypatch, tmp_path):
    request, guide, system = fixture_request()
    capture = tmp_path / "capture"
    lead = capture / "lead"
    (lead / "requests").mkdir(parents=True)
    (lead / "guide.txt").write_bytes(guide.encode())
    (lead / "system.txt").write_bytes(system.encode())
    request["body"]["input"] += [
        item for n in range(6) for item in (
            {"type": "function_call", "call_id": str(n), "name": "shell", "arguments": '{"command":"aew status"}'},
            {"type": "function_call_output", "call_id": str(n), "output": "fixture"},
        )
    ]
    wire = json.dumps(request["body"], ensure_ascii=False).encode()
    (lead / "requests/003.json").write_bytes(wire)
    record = {"schema": "aew/lead-probe/v1", "aew_commit": "a" * 40,
              "legs": {"lead": {"request_start": 3}}}
    original = json.dumps(record).encode()
    (capture / "record.json").write_bytes(original)
    out = tmp_path / "reanalyzed"
    analysing_commit = "b" * 40
    monkeypatch.setattr(cli, "aew_revision", lambda: analysing_commit)
    assert cli.main(["--analyse", str(capture), "--out", str(out)]) == 0
    revised = json.loads((out / "record.json").read_bytes())
    assert revised["aew_commit"] == record["aew_commit"] and "analysis" not in revised
    assert revised["analysed_with"] == analysing_commit
    assert revised["legs"]["lead"]["first_request"]["raw_bytes"] == len(wire)
    assert len(revised["legs"]["lead"]["results"]) == 6
    assert (capture / "record.json").read_bytes() == original


def test_worker_facts_come_from_saved_label_and_config(monkeypatch, tmp_path):
    from lead_probe import session

    monkeypatch.setattr(session.runlog, "read_record", lambda directory: {
        "containment": {"filesystem": "fixture", "mechanism": "fixture isolation", "network": {"mode": "closed"}},
    })
    config = tmp_path / "harness/opencode-config.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"experimental": {"policies": [
        {"action": "provider.use", "resource": "example", "effect": "deny"},
        {"action": "provider.use", "resource": "allowed", "effect": "allow"},
    ]}}), encoding="utf-8", newline="\n")
    assert session.worker_facts(tmp_path) == {
        "containment": {"filesystem": "fixture", "mechanism": "fixture isolation", "network_mode": "closed"},
        "provider_denies": ["example"],
    }
