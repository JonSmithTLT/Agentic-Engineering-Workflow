"""Open the kit with a scripted Lead and synthetic login. All provider routes are inert."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from conftest import Project, clean_env
from fake_harness import HarnessLab
from host_env import clean_launching_env
from vertical import workers
from vertical.chat import Mailbox
from vertical.ledger import Ledger
from vertical.scripted_operator import (
    OFFLINE_KEY,
    Operator,
    lead_spec,
    new_world,
    world_around_init,
    world_fixtures,
)

from aew.harness.containment import netns
from aew.kit import MONEY_SCOPE, OPENING_REQUEST, launch_argv, prepare
from aew.kit.receipt import SCHEMA, write_receipt


def offline_policy(doc):
    providers = {*netns.PROVIDER_KEY_ENV, "fakeprov"}
    doc["containment"]["network"] = {"upstreams": {p: f"https://{p}.invalid/v1" for p in providers}}


def scrub_provider_environment(monkeypatch):
    for key in set(netns.PROVIDER_KEY_ENV.values()) | {"OPENCODE_DB", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR"}:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def offline_kit(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    clean_launching_env(monkeypatch, home)
    for kind in ("cache", "config", "data", "state"):
        monkeypatch.setenv(f"XDG_{kind.upper()}_HOME", str(home / kind))
    # Plant a synthetic value so dropping the scrub cannot pass on a machine with no provider keys.
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-must-not-reach-child")
    scrub_provider_environment(monkeypatch)

    world = new_world(tmp_path)
    dest = tmp_path / "kit"
    lab = HarnessLab(Project(dest / "repo"), tmp_path, world.env)
    ledger = Ledger("E117")
    fixtures = {**world_fixtures(lab), "containment.network.upstreams": offline_policy}
    known = {"fakeprov": OFFLINE_KEY}
    env = clean_env(lab.env)
    assert env["AEW_OPENCODE_BIN"] == world.env["AEW_OPENCODE_BIN"]
    assert not set(netns.PROVIDER_KEY_ENV.values()) & env.keys()
    assert env[OFFLINE_KEY] == "synthetic-offline-provider-key"
    assert Path(env["OPENCODE_DB"]).is_relative_to(tmp_path)
    assert all(Path(env[name]).is_relative_to(home) for name in env if name == "HOME" or name.startswith("XDG_")
               and name.endswith("_HOME"))
    # On Windows the fake executable is the isolation boundary. Linux additionally relays only inert upstreams.
    with world_around_init(ledger, fixtures, known):
        engine = prepare(dest, "fakeprov/worker", "fakeprov/lead")
    policy = engine.execution_policy()[0]
    assert policy["harness"] == "fake"
    for provider in {*netns.PROVIDER_KEY_ENV, "fakeprov"}:
        assert netns.upstream(provider, policy).url == f"https://{provider}.invalid/v1"

    try:
        yield dest, engine, lab, ledger
    finally:
        lab.cleanup()


def test_dry_run_has_only_inert_provider_routes(offline_kit):
    dest, engine, lab, _ = offline_kit
    assert engine.repo_root == dest / "repo"
    assert lab.env[OFFLINE_KEY]


def test_the_kit_reaches_its_first_ticket_with_a_fake_lead(tmp_path, offline_kit):
    dest, engine, lab, ledger = offline_kit
    chat = Mailbox(tmp_path / "sync/chat", "operator")
    op = Operator(lab, ledger, tmp_path, chat)
    op.allowed_heads.add(engine.authoritative_commit())
    draft = {**workers.DRAFT, "scope": list(MONEY_SCOPE),
             "plan": {**workers.DRAFT["plan"], "affected": list(MONEY_SCOPE)}}
    spec = {**lead_spec(lab), "draft": draft}
    argv = launch_argv(dest, (), "fakeprov/lead")
    session = op.open_session("start", argv[5:], spec)
    lab.closers.extend(op.closers)
    assert op.first_words(session) is not None, session.output()[-1500:]
    op.say("ask", OPENING_REQUEST)
    # The scripted Lead creates one Ticket and then asks to approve its plan. Do not approve it.
    message = chat.receive(90, gone=session.ended)
    assert (message.get("type"), message.get("label")) == ("ask", "plan"), message
    assert engine.work_show("T-0001")["id"] == "T-0001"
    assert op.end_session(session) == 0
    receipt = json.loads(write_receipt(dest).read_text(encoding="utf-8"))
    assert receipt["schema"] == SCHEMA
    assert receipt["kind"] == "dry_run"
    assert receipt["readability"] == "not asked"
    assert receipt["scope"]["created_tickets"] == ["T-0001"]
    label = "workdir_separation_only" if sys.platform == "win32" else "os_readonly_roots"
    assert receipt["systems"]["SYS-02"]["lead"] == [label]
    assert receipt["systems"]["SYS-06"]["typed_stage_intents"]
    assert receipt["systems"]["SYS-08"]["stage_intents"]
