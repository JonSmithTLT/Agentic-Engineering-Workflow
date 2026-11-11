"""Guide/system/catalog consume the broker's one post-offer adopted snapshot, not an earlier policy read."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_coordination_store import OPERATOR, set_messaging, world

from aew.harness import contract as K
from aew.harness import lead_broker, procs
from aew.harness.opencode import lead, projection
from aew.surface import contract, mcp


@pytest.mark.parametrize("contained", [False, True])
@pytest.mark.parametrize("adopted", [False, True])
def test_post_offer_snapshot_is_shared_even_if_policy_changes_after_the_broker_takes_it(
        tmp_path, monkeypatch, contained, adopted):
    w = world(tmp_path, messaging="disabled")
    monkeypatch.setenv("AEW_LEAD_TOKEN", w.token)
    captured = {}
    holder = SimpleNamespace(guide="old pre-offer guide", surface_switches=frozenset()) if contained else None

    def apply(token):
        assert token == w.token
        if adopted:
            set_messaging(w.root, "enabled")
            w.e.manifest_adopt(token=token, expect_rev=w.rev(), reason="test the post-apply snapshot",
                               authorization=OPERATOR)

    original = lead.session_presentation(w.e, provider_env=[], contained=holder)

    def prepare(env, switches):
        assert switches == (frozenset({"coordination.messaging"}) if adopted else frozenset())
        # The adoption changed again after the broker's capture. Presentation must not split the two versions.
        set_messaging(w.root, "disabled" if adopted else "enabled")
        w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="after capture", authorization=OPERATOR)
        return original(env, switches)

    def harness(private_dir, env):
        captured.update(env)
        return lead_broker.Harness(argv=["not-started"], env=env, relay=False, label={}, close=lambda: None)

    monkeypatch.setattr(procs, "run_session_tree", lambda *args, **kwargs: (0, "clean"))
    lead_broker.run_session(w.e, ["not-started"], acquire=False, session_label=None, keep_seat=True,
                            contained=harness, env={}, with_token=apply, prepare_env=prepare)
    selected = frozenset(json.loads(captured.get(contract.ENV_SWITCHES, "[]")))
    config = json.loads(captured["OPENCODE_CONFIG_CONTENT"])
    system = config["agents"][projection.LEAD_AGENT]["system"]
    listing = mcp.Server(lambda *args: {}, switches=selected).dispatch("tools/list", {})
    assert ("message_send" in {t["name"] for t in listing["tools"]}) == adopted
    assert ("`message_send`" in system) == ("`worker_message`" in system) == adopted
    assert system.count(K.MESSAGE_READ_COST) == int(adopted)
    assert w.e.messaging_enabled() != adopted  # presentation didn't grant authority against the newer policy
    if contained:
        assert holder.surface_switches == selected and (K.MESSAGE_READ_COST in holder.guide) == adopted
