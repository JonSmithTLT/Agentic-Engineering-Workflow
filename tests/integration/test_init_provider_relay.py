"""The operator's final init result includes the same live provider requests as doctor."""

from __future__ import annotations

import hashlib
import json
import sys
from contextlib import closing

import pytest
from conftest import make_git_repo
from fake_opencode import ProviderUpstream
from host_env import clean_launching_env
from lead_session import synthetic_home

from aew.cli.main import main
from aew.engine.api import Engine
from aew.harness import model_list, runlog
from aew.policy import execution


@pytest.mark.parametrize(("as_json", "reply", "network"), [
    (False, 401, "proxy_only"), (True, 200, "proxy_only"),
    (True, 0, "proxy_only"), (False, 200, "isolated"),
])
def test_init_reports_the_saved_login_and_worker_export_separately(tmp_path, monkeypatch, capsys, as_json,
                                                                 reply, network):
    root = make_git_repo(tmp_path / "project")
    saved, exported = "synthetic-init-saved", "synthetic-init-export"
    home = synthetic_home(tmp_path / "operator", {"openai": saved})
    clean_launching_env(monkeypatch, home)
    monkeypatch.setenv("OPENAI_API_KEY", exported)
    store = home / ".local/share/opencode/opencode.db"
    before = store.read_bytes()
    saved_hash, export_hash = (hashlib.sha256(v.encode()).hexdigest() for v in (saved, exported))
    with closing(ProviderUpstream()) as upstream:
        upstream.models_status[saved_hash] = reply
        monkeypatch.setattr(execution, "TEMPLATE", execution.TEMPLATE +
                            f"\ncontainment:\n  network:\n    mode: {network}\n    upstreams:\n"
                            f"      openai: {upstream.url}\n")
        argv = ["-C", str(root), "init", "--model", "openai/gpt-x", "--fetch-tool", "none"]
        assert main([*argv, "--json"] if as_json else argv) == 0
        shown = capsys.readouterr()
        report = json.loads(shown.out)
        assert report["ok"] and report["revision"] == 0
        worker, lead = report["provider_relay"]
        assert worker["detail"].startswith("worker profile default") and lead["detail"].startswith("default Lead")
        if sys.platform.startswith("linux") and network == "proxy_only":
            assert sorted(upstream.model_requests) == sorted([("/v1/models", saved_hash), ("/v1/models", export_hash)])
            assert worker["status"] == "PASS" and "environment" in worker["detail"]
            status, detail = {401: ("FAIL", "provider answered HTTP 401"), 200: ("PASS", "provider answered HTTP 200"),
                              0: ("WARN", "relay answered HTTP 502")}[reply]
            assert lead["status"] == status and detail in lead["detail"] and "saved OpenCode API key" in lead["detail"]
        else:
            assert worker["status"] == lead["status"] == "WARN" and not upstream.model_requests
        assert not upstream.seen  # no model completion or other POST
    engine = Engine.discover(root)
    assert engine.store.current()["revision"] == 0 and before == store.read_bytes()
    assert not (engine.aew_root / model_list.CACHE_REL).exists()
    assert not list((engine.aew_root / runlog.RUNS_REL).glob("doctor-*"))
    persisted = b"".join(p.read_bytes() for p in engine.aew_root.rglob("*") if p.is_file())
    for secret in (saved, exported, "upstream-private-value", "private-provider-error", "aew-relay-"):
        assert secret not in shown.out + shown.err and secret.encode() not in persisted


def test_init_without_a_configured_model_or_login_names_what_was_unchecked(tmp_path, monkeypatch, capsys):
    root = make_git_repo(tmp_path / "project")
    clean_launching_env(monkeypatch, tmp_path / "empty-home")
    assert main(["-C", str(root), "init", "--fetch-tool", "none", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    worker, lead = report["provider_relay"]
    assert report["revision"] == 0 and worker["status"] == lead["status"] == "WARN"
    assert "no worker profile selected" in worker["detail"] and "default Lead" in lead["detail"]
