"""tools/harness_qualify, the harness qualification tool (a developer tool): its harness-neutral core against a stub
pack, its scripted model, and its OpenCode pack against the fake OpenCode server. The run against the real binary
(regenerating the pinned 2.0.18 fixtures exactly) is the live lane's: tests/live/test_harness_qualify_live.py."""

from __future__ import annotations

import ast
import http.client
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import fake_opencode
import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "harness_qualify"
FIXTURES = ROOT / "tests" / "fixtures" / "opencode"
if str(TOOL.parent) not in sys.path:
    sys.path.append(str(TOOL.parent))

import harness_qualify as HQ  # noqa: E402
from harness_qualify import core, model  # noqa: E402
from harness_qualify import opencode as OC  # noqa: E402

# ------------------------------------------------------------------------------------------------- the stub pack


class StubPack:
    """A second harness that is not OpenCode: its own version rule, checks, capabilities, pin and fixture."""

    harness = "stubharness"
    version_source = None

    def __init__(self, behaviour: dict[str, Any]) -> None:
        self.behaviour = behaviour

    def declared(self) -> dict[str, str]:
        return {"cap_ok": "a", "cap_broken": "b", "cap_vm": "c", "cap_untested": "declared, but no check covers it"}

    def read_version(self, binary: Path, work: Path, env: dict[str, str]) -> str:
        assert env["HOME"].startswith(str(work)) and "STUB_API_KEY" not in env  # the core's private environment
        return binary.read_text(encoding="utf-8").split()[-1]

    def checks(self) -> list[core.Check]:
        b = self.behaviour

        def ok(ctx: core.Context) -> core.Outcome:
            return core.Outcome(core.PASS, {"stub.answer": b["answer"], "stub.version": ctx.version})

        def broken(ctx: core.Context) -> core.Outcome:
            raise RuntimeError("the stub harness crashed")

        return [core.Check("stub.ok", ok, ("cap_ok",)),
                core.Check("stub.broken", broken, ("cap_broken",)),
                core.Check("stub.vm", ok, ("cap_vm",), platform=core.VM),
                core.Check("stub.other", ok, ("not_declared",), depth=core.API)]

    def pinned(self, fixtures: Path) -> tuple[str, dict[str, Any]]:
        return "1.0", {**json.loads((fixtures / "stub-1.0.json").read_text(encoding="utf-8")), "stub.feeling": "fine"}

    def render(self, version: str, facts: Any, fixtures: Path) -> dict[str, tuple[bytes | None, str]]:
        return {f"stub-{version}.json": (core.dump({k: facts[k] for k in ("stub.answer", "stub.version")}),
                                         "measured")}

    def unmeasured(self) -> dict[str, str]:
        return {"stub.feeling": "a person's, not a run's"}

    def adoptable(self, facts: Any, pinned: Any) -> list[str]:
        return []


def stub_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: int) -> tuple[Any, ...]:
    monkeypatch.setattr(core, "has_bubblewrap", lambda: False)  # this host's answer is not the test's
    monkeypatch.setenv("STUB_API_KEY", "synthetic-must-not-pass")
    binary = tmp_path / "stub-binary"
    binary.write_text("stubharness 1.0", encoding="utf-8")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    (fixtures / "stub-1.0.json").write_bytes(core.dump({"stub.answer": 42, "stub.version": "1.0"}))
    return HQ.run(StubPack({"answer": answer}), binary, out=tmp_path / "out", fixtures=fixtures)


def test_the_core_runs_a_second_harness_pack_and_assumes_nothing_of_opencode(tmp_path, monkeypatch):
    record, diff, fixtures, _ = stub_run(tmp_path, monkeypatch, 42)
    by = {r["id"]: r for r in record.checks}
    assert (record.harness, record.version) == ("stubharness", "1.0")
    assert record.binary_sha256 == core.sha256_file(tmp_path / "stub-binary")
    assert by["stub.ok"]["status"] == core.PASS
    assert by["stub.broken"]["status"] == core.ERROR and "the stub harness crashed" in by["stub.broken"]["notes"][0]
    assert by["stub.vm"]["status"] == core.SKIPPED and "bubblewrap" in by["stub.vm"]["notes"][0]
    assert diff.clean and diff.not_measured == {"stub.feeling": "a person's, not a run's"}
    assert fixtures == [{"fixture": "stub-1.0.json", "status": "identical", "how": "measured"}]
    # The core's own modules name no harness: every harness fact is a pack's (``__init__.pack_for`` is the registry).
    for name in ("core.py", "model.py", "neutral.py", "capabilities.py"):
        tree = ast.parse((TOOL / name).read_text(encoding="utf-8"))
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + \
                  [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [m for m in imports if "opencode" in m or "codex" in m], (name, imports)
    assert "opencode" not in (TOOL / "core.py").read_text(encoding="utf-8").lower()


def test_a_declared_capability_with_no_check_is_unchecked_and_a_broken_one_fails(tmp_path, monkeypatch):
    record, *_ = stub_run(tmp_path, monkeypatch, 42)
    caps = {k: v["status"] for k, v in record.capabilities.items()}
    assert caps == {"cap_ok": core.PASS, "cap_broken": core.FAIL, "cap_vm": core.SKIPPED,
                    "cap_untested": core.UNCHECKED, "not_declared": "undeclared"}


def test_a_changed_fact_appears_in_the_diff_and_the_fixture_differs(tmp_path, monkeypatch):
    """The ablation: the stub measures 41 where the pin says 42."""
    _, diff, fixtures, _ = stub_run(tmp_path, monkeypatch, 41)
    assert diff.lines()[0] == "~ stub.answer: 42 -> 41"
    assert fixtures[0]["status"] == "differs"


def test_the_private_environment_passes_no_credential_proxy_or_home(tmp_path):
    base = {"PATH": "/bin", "HOME": "/home/operator", "XDG_DATA_HOME": "/home/operator/.local/share",
            "OPENAI_API_KEY": "x", "GITHUB_TOKEN": "x", "HTTPS_PROXY": "http://proxy", "AEW_HOME": "x",
            "OPENCODE_CONFIG": "x", "SOME_SECRET": "x", "LANG": "C.UTF-8"}
    env = core.private_env(tmp_path, base, harness="opencode")
    dropped = {"OPENAI_API_KEY", "GITHUB_TOKEN", "HTTPS_PROXY", "AEW_HOME", "OPENCODE_CONFIG", "SOME_SECRET"}
    assert not dropped & set(env)
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
                 "APPDATA", "LOCALAPPDATA", "TMPDIR", "TEMP", "TMP"):
        assert Path(env[name]).is_relative_to(tmp_path), name
    assert env["PATH"] == "/bin" and "127.0.0.1" in env["NO_PROXY"]


# ---------------------------------------------------------------------------------------------- the scripted model

def _sse(llm: Any, body: dict[str, Any]) -> list[dict[str, Any]]:
    conn = http.client.HTTPConnection(llm.base_url.split("//")[1].split("/")[0], timeout=10)
    conn.request("POST", "/v1/responses", json.dumps(body), {"Content-Type": "application/json"})
    text = conn.getresponse().read().decode()
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_the_scripted_model_calls_the_offered_tool_and_reports_the_usage_it_was_given():
    usage = {"input_tokens": 9, "input_tokens_details": {"cached_tokens": 4}, "output_tokens": 3,
             "output_tokens_details": {"reasoning_tokens": 1}}
    llm = model.start("responses", [{"call": ["shell", "write"], "arguments": {"$path": "/w/a.txt"}, "usage": usage}])
    try:
        tools = [{"type": "function", "name": "write", "parameters": {"properties": {"filePath": {}, "content": {}}}}]
        events = _sse(llm, {"model": "m", "stream": True, "tools": tools, "input": []})
        aux = _sse(llm, {"model": "m", "stream": True, "input": []})  # a title request: no tools
        conn = http.client.HTTPConnection(llm.base_url.split("//")[1].split("/")[0], timeout=10)
        conn.request("GET", "/v1/responses", headers={"Upgrade": "websocket", "Connection": "Upgrade"})
        assert conn.getresponse().status == 501
    finally:
        llm.close()
    call = next(e["item"] for e in events if e["type"] == "response.output_item.done")
    assert (call["type"], call["name"], json.loads(call["arguments"])) == ("function_call", "write",
                                                                         {"filePath": "/w/a.txt"})
    assert events[-1]["response"]["usage"] == {**usage, "total_tokens": 12}
    assert aux[-1]["response"]["usage"]["input_tokens"] == 0
    assert llm.upgrades == 1 and [r["main"] for r in llm.requests if r["method"] == "POST"] == [True, False]
    assert all("Authorization" not in json.dumps(r) or r["auth"] in ("present", "absent") for r in llm.requests)


# --------------------------------------------------------------------------------- the OpenCode pack, offline parts

def test_the_pinned_fixtures_layouts_are_reproduced_from_their_own_data():
    """The pack writes each fixture as the pinned one is laid out, so a regeneration is byte for byte."""
    usage = (FIXTURES / "usage-2.0.18-openai.json").read_bytes()
    assert (OC._render_json(json.loads(usage)) + "\n").encode() == usage
    pinned = (FIXTURES / "openapi-2.0.18.min.json").read_bytes()
    spec = json.loads(pinned)
    trimmed = OC.trim(spec, version="2.0.18", full_sha256=spec["x-aew-fixture"]["full_sha256"])
    assert core.dump(trimmed) == pinned  # the trimming is the pin's: trimming the trimmed document changes nothing


def test_the_pinned_usage_is_disjoint_and_a_changed_stored_count_is_not():
    cases = json.loads((FIXTURES / "usage-2.0.18-openai.json").read_text(encoding="utf-8"))["cases"]
    assert OC.classify(cases) == "disjoint"
    cases[0]["stored"]["input"] += cases[0]["raw"]["input_tokens_details"]["cached_tokens"]  # input counted inclusive
    assert OC.classify(cases) == "unknown"


def test_a_doctored_pin_shows_the_changed_fact_in_the_diff(tmp_path):
    """The ablation through the pack's own pin reader: one stored count changed in a copy of the fixtures."""
    doctored = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, doctored)
    path = doctored / "usage-2.0.18-openai.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["cases"][0]["stored"]["input"] = 3001
    path.write_text(json.dumps(doc), encoding="utf-8")
    pack = OC.OpenCodePack(FIXTURES)
    _, measured = pack.pinned(FIXTURES)
    _, pinned = pack.pinned(doctored)
    assert core.fact_diff(measured, pinned).lines() == ["~ usage.openai.cases[0].stored.input: 3001 -> 3000"]


def test_the_feed_gives_the_version_and_each_files_digest():
    text = ("version: 9.8.7\nfiles:\n  - url: opencode-desktop-linux-x86_64.rpm\n    sha512: c2hhNTEy\n"
            "    size: 123\npath: opencode-desktop-linux-x86_64.rpm\n")
    feed = OC.Feed(fetch=lambda url: text)
    assert feed.latest() == [core.Release("9.8.7", OC.FEED.rsplit("/", 1)[0] + "/opencode-desktop-linux-x86_64.rpm",
                                          "c2hhNTEy", "sha512", 123)]


def test_every_capability_opencode_declares_is_reported_and_the_checks_split_by_platform():
    pack = OC.OpenCodePack(FIXTURES)
    checks = pack.checks()
    keyed = {c for check in checks for c in check.capabilities}
    assert keyed <= set(pack.declared())
    assert {"attach_to_operator_session", "mark_non_operator_input"} == set(pack.declared()) - keyed  # unchecked
    assert [c.id for c in checks if c.platform == core.VM] == ["containment.self_test"]


# ----------------------------------------------------------------------------- the OpenCode pack, fake server

API_CHECKS = ["api.openapi", "api.wake_idle_session", "api.queue_until_turn_end", "api.steer_running_turn",
              "api.interrupt_turn", "usage.live_citations", "ripgrep.download"]


def fake_binary(tmp_path: Path, knobs: dict[str, Any] | None = None) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "default.json").write_text(json.dumps({"steps": [], "server": knobs or {}}), encoding="utf-8")
    return fake_opencode.write_launcher(tmp_path / "bin", scripts)


def test_the_opencode_pack_against_the_fake_server_measures_its_api_and_names_what_it_cannot(tmp_path):
    record, diff, fixtures, _ = HQ.run(OC.OpenCodePack(FIXTURES), fake_binary(tmp_path), out=tmp_path / "out",
                                       fixtures=FIXTURES, only=API_CHECKS)
    by = {r["id"]: r["status"] for r in record.checks}
    assert record.version == "2.0.18"
    assert {k: by[k] for k in API_CHECKS[:5]} == dict.fromkeys(API_CHECKS[:5], core.PASS)
    # the fake is not the build the citations were read from: not comparable, never a pass or a changed fact
    assert by["usage.live_citations"] == core.SKIPPED and by["ripgrep.download"] == core.FAIL
    assert diff.not_measured["live_usage.bundle_identifiers"].startswith("usage.live_citations skipped: not comparable")
    assert by["usage.openai"] == core.SKIPPED  # not selected: never reported as passed
    # The fake serves the pinned trimmed document, so the trimming reproduces it; only the full document's hash
    # (which the fake cannot have) differs.
    changed = [d for d in diff.changed if d.fact == "openapi.min"]
    assert [d.path for d in changed] == [".x-aew-fixture.full_sha256"]
    assert record.capabilities["read_progress"]["status"] == core.SKIPPED
    assert record.capabilities["attach_to_operator_session"]["status"] == core.UNCHECKED
    assert "login.oauth_shape" in record.unmeasured


def test_an_operation_the_served_api_drops_fails_its_capability_and_shows_in_the_diff(tmp_path):
    """The ablation through a served document: the fake drops session.interrupt."""
    binary = fake_binary(tmp_path, {"openapi_drop": ["POST /api/session/{sessionID}/interrupt"]})
    record, diff, *_ = HQ.run(OC.OpenCodePack(FIXTURES), binary, out=tmp_path / "out", fixtures=FIXTURES,
                              only=["api.openapi", "api.interrupt_turn"])
    assert record.capabilities["interrupt_turn"]["status"] == core.FAIL
    assert "- openapi.min.paths./api/session/{sessionID}/interrupt: " in "\n".join(diff.lines())
    assert "operation POST /api/session/{sessionID}/interrupt is missing" in record.facts["openapi.problems"]


def test_the_cli_writes_the_record_diff_and_report(tmp_path):
    out = tmp_path / "out"
    code = HQ_main(["--binary", str(fake_binary(tmp_path)), "--out", str(out), "--only", "api.openapi"])
    record = json.loads((out / "record.json").read_text(encoding="utf-8"))
    assert code == 1  # the fake's full-document hash differs from the pin's
    assert record["schema"] == core.SCHEMA and record["harness"] == "opencode" and record["binary_sha256"]
    assert (out / "diff.txt").read_text(encoding="utf-8").startswith("~ openapi.min.x-aew-fixture.full_sha256")
    assert "Capabilities (declared by the adapter):" in (out / "report.txt").read_text(encoding="utf-8")


def HQ_main(argv: list[str]) -> int:  # noqa: N802
    import importlib

    return importlib.import_module("harness_qualify.__main__").main(argv)


@pytest.mark.parametrize(("body", "status"), [
    ("def test_a():\n    pass\n", core.PASS),
    ("import pytest\n\ndef test_a():\n    pass\n\n@pytest.mark.skip('needs a model')\ndef test_b():\n    pass\n",
     core.SKIPPED),
    ("def test_a():\n    assert False\n", core.FAIL),
])
def test_a_suite_run_with_any_skip_is_reported_skipped_never_passed(tmp_path, body, status):
    from harness_qualify import neutral

    suite = tmp_path / "suite" / "test_suite.py"
    suite.parent.mkdir()
    suite.write_text(body, encoding="utf-8")
    ctx = core.Context(binary=tmp_path / "bin", work=tmp_path / "work", env=core.private_env(tmp_path / "env"),
                       version="1")
    assert neutral._pytest(ctx, "STUB_BIN", [str(suite)], ["--rootdir", str(suite.parent)]).status == status


def test_in_the_binary_the_citations_were_read_from_a_missing_identifier_fails(tmp_path):
    binary = tmp_path / "bundle.bin"
    binary.write_bytes(b"...yield*e.project(hd,(i)=>Pc(r))...")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    cite = "opencode-cli 9.9.9 (bundled JavaScript)"
    doc = {"source": {"binary_sha256": core.sha256_file(binary), "evidence": [
        {"id": "E1", "file": cite, "identifier": "yield*e.project(hd,(i)=>Pc(r))"},
        {"id": "E2", "file": cite, "identifier": "session.step.ended"},
        {"id": "E3", "file": "packages/core/src/x.ts", "lines": "1-2"}]}}  # a source citation: carried, not searched
    (fixtures / "live-usage-9.9.9.json").write_text(json.dumps(doc), encoding="utf-8")
    ctx = core.Context(binary=binary, work=tmp_path / "w", env={}, version="9.9.9")
    out = OC.check_live_usage_citations(ctx, fixtures, "9.9.9")
    assert (out.status, out.facts, out.notes) == (core.FAIL, {"live_usage.bundle_identifiers": {"E1": True,
                                                                                               "E2": False}},
                                                  ["not in this binary: E2"])


def test_the_credential_columns_are_read_from_aews_own_sql():
    cols = OC.credential_columns()
    assert {"integration_id", "method_id", "active", "value", "time_updated", "id", "label", "time_created"} == set(
        cols)
