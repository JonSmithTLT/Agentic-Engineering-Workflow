"""`aew doctor` states what a launch would meet, before any launch and without calling a provider: Windows' unqualified
containment state on Windows (operator decision 2026-10-11: never silently absent), and the provider-variable rule a
launch and the Lead session share (ADR-0010 amendment 2026-10-11). Synthetic names and values only."""

from __future__ import annotations

import sys

import pytest

from aew import doctor
from aew.harness import agentenv

CREDENTIAL = "aew1.tk_0123456789abcdef.abcdefghijklmnopqrstuvwxyz"


@pytest.mark.parametrize("platform_name", ["win32", "linux", "darwin"])
def test_doctor_states_windows_unqualified_containment_on_windows_and_only_there(monkeypatch, platform_name):
    monkeypatch.setattr(sys, "platform", platform_name)
    lines = [c for c in doctor.environment_checks() if c["check"] == "platform"]
    if platform_name != "win32":
        assert lines == []
        return
    [line] = lines
    assert line["status"] == "WARN"  # stated, not a failure: Windows is outside the enforced gate, not broken
    assert line["detail"].startswith("Windows: UNQUALIFIED (excluded from the enforced gate): ")
    for why in ("workdir separation only", "no OS filesystem containment", "no isolation between runs",
                "an uncontained Lead", "Low-integrity containment backend", "qualification self-tests"):
        assert why in line["detail"], why


def test_the_windows_line_is_rendered_first_so_it_is_never_missed(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert doctor.environment_checks()[0]["check"] == "platform"


@pytest.mark.parametrize(("name", "env", "why"), [
    ("VENDOR_KEY", {}, "VENDOR_KEY is not set in this environment: set VENDOR_KEY in the terminal you start AEW from"),
    ("VENDOR_KEY", {"VENDOR_KEY": ""}, "VENDOR_KEY is not set in this environment"),
    ("AEW_LEAD_TOKEN", {"AEW_LEAD_TOKEN": CREDENTIAL}, "AEW_LEAD_TOKEN is an AEW variable"),
    ("VENDOR_KEY", {"VENDOR_KEY": CREDENTIAL}, "VENDOR_KEY holds an AEW credential"),
])
def test_a_provider_variable_a_harness_cannot_get_is_named_with_its_fix_and_never_its_value(name, env, why):
    [(found, text)] = agentenv.provider_env_problems([name], env)
    assert found == name and text.startswith(why)
    assert CREDENTIAL not in text


def test_the_fix_for_an_unset_provider_variable_names_both_shells():
    [(_, text)] = agentenv.provider_env_problems(["VENDOR_KEY"], {})
    assert "export VENDOR_KEY=" in text and "$env:VENDOR_KEY = " in text


def test_a_set_provider_variable_is_no_problem():
    assert agentenv.provider_env_problems(["VENDOR_KEY", "HTTPS_PROXY"],
                                          {"VENDOR_KEY": "synthetic", "HTTPS_PROXY": "http://proxy.example:3128"}) == []


def test_inside_a_lead_session_the_fix_says_the_session_must_be_restarted():
    """A launch the Lead or its steering loop makes reads the session's own environment, which a variable set in
    another terminal never reaches (review of PR #214, F2)."""
    with agentenv.session_host("this Lead session (`aew opencode` or `aew lead session`)"):
        [(_, text)] = agentenv.provider_env_problems(["VENDOR_KEY"], {})
    assert "this Lead session (`aew opencode` or `aew lead session`) started without VENDOR_KEY" in text
    assert "restart `aew opencode` (or `aew lead session`) from that terminal" in text
    [(_, outside)] = agentenv.provider_env_problems(["VENDOR_KEY"], {})
    assert "started without" not in outside and "already running keeps the environment it started with" in outside


def test_a_lead_session_marks_its_process_as_the_launch_host_while_it_runs(monkeypatch):
    from aew.harness import lead_broker, procs

    seen = []

    class Broker:
        env: dict = {}
        superseded = None

        def __init__(self, *_):
            pass

        def start(self):
            seen.append(("start", agentenv.env_fix("VENDOR_KEY")))

        def close(self):
            pass

    class Store:
        def current(self):
            return {"revision": 0, "invocations": {}}

    class Engine:
        repo_root = "."
        store = Store()

    def tree(command, *, env, cwd):
        seen.append(("run", agentenv.env_fix("VENDOR_KEY")))
        return 0, "clean"

    monkeypatch.setattr(lead_broker, "LeadBroker", Broker)
    monkeypatch.setattr(procs, "run_session_tree", tree)
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    monkeypatch.setenv("AEW_LEAD_TOKEN", "synthetic")
    lead_broker.run_session(Engine(), ["harness"], acquire=False, session_label=None, keep_seat=False, env={})
    assert [k for k, _ in seen] == ["start", "run"]
    assert all("this Lead session" in text and "started without" in text for _, text in seen)
    assert "started without" not in agentenv.env_fix("VENDOR_KEY")  # only while the session runs


@pytest.mark.parametrize("platform_name", ["win32", "linux"])
def test_a_provider_variable_name_is_looked_up_with_the_platforms_case_rule_everywhere(monkeypatch, tmp_path,
                                                                                      platform_name):
    """Windows names are case-insensitive and a copied ``dict(os.environ)`` holds them upper-cased, so the up-front
    check, doctor and the server's environment use one lookup and agree (review of PR #214, F4)."""
    from aew.harness.opencode import adapter

    monkeypatch.setattr(sys, "platform", platform_name)
    upper = {"PATH": "", "VENDOR_KEY": "synthetic"}  # what the supervisor's dict(os.environ) holds on Windows
    problems = agentenv.provider_env_problems(["Vendor_Key"], upper)
    if platform_name == "win32":
        assert problems == []
        env = adapter.server_env(upper, tmp_path, provider_env=["Vendor_Key"], config={}, password="p")
        assert env["Vendor_Key"] == "synthetic"
    else:
        assert [n for n, _ in problems] == ["Vendor_Key"]  # POSIX names are exact: refused up front, never later


def test_the_live_environment_and_its_copy_agree_on_a_mixed_case_name(monkeypatch):
    """On this host, whatever its platform: the check over ``os.environ`` (the launcher's) and over a copied dict
    (the supervisor's) give the same answer for a mixed-case name."""
    import os

    monkeypatch.setenv("AEWTEST_Mixed_Key", "synthetic")
    live = agentenv.provider_env_problems(["AEWTEST_Mixed_Key"], os.environ)
    copied = agentenv.provider_env_problems(["AEWTEST_Mixed_Key"], dict(os.environ))
    assert live == copied == []
