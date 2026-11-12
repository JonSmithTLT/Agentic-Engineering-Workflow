"""Delivery eligibility is verified independently of telemetry and filtered before the shared body cap."""

from __future__ import annotations

import json

import pytest
from test_coordination_store import world

from aew.harness import told_messages as T
from aew.harness import wake_queue


@pytest.fixture
def w(tmp_path):
    return world(tmp_path)


def test_local_told_suppresses_only_delivery_not_durable_attention_and_old_generation_does_not(w):
    lead = w.send()["message"]["id"]
    mid = w.reply(lead)["message"]["id"]
    root = w.root / ".aew"
    generation = w.e.store.read()["lead"]["generation"]
    T.record(root, generation, [mid], current=lambda: True)
    assert w.e.message_delivery_view()["awaiting_lead"] == []
    assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == [mid]
    (root / T.REL).write_text(json.dumps({"generation": generation - 1, "messages": [mid]}), encoding="utf-8")
    assert [m["id"] for m in w.e.message_delivery_view()["awaiting_lead"]] == [mid]


def test_told_filtering_before_the_cap_does_not_strand_the_next_invocations_reply(w):
    lead = w.send()["message"]["id"]
    ids = [w.reply(lead, body=f"reply {i}")["message"]["id"] for i in range(20)]
    w.lead("invoke_cancel", invocation=w.inv, reason="settle a full unseen batch")
    replacement = w.lead("invoke_create", work_id=w.wid, role="implementer")
    second = w.send(to=replacement["invocation"])["message"]["id"]
    last = w.reply(second, body="last", invocation_token=replacement["invocation_token"])["message"]["id"]
    # Suppress exactly the current bounded view, not the omitted ID. The next delivery must expose that ID.
    first = w.e.message_delivery_view()
    carried = {m["id"] for m in first["awaiting_lead"]}
    assert len(carried) == 20 and first["omitted"] == 1
    T.record(w.root / ".aew", w.e.store.read()["lead"]["generation"], carried, current=lambda: True)
    next_view = w.e.message_delivery_view()
    remaining = (set(ids) | {last}) - carried
    assert {m["id"] for m in next_view["awaiting_lead"]} == remaining
    assert w.e.message_result_ids({"coordination": next_view}) == sorted(remaining)
    # Local cursors affect only live wake conditions. Settled bodies are recovered through pinned hot-list seals.
    settled = w.e.message_delivery_view(invocations={w.inv}, after={w.inv: 999})
    assert {m["id"] for m in settled["awaiting_lead"]} == remaining & set(ids)


@pytest.mark.parametrize("doc", [None, {"generation": 1, "posted_messages": ["bad"]},
    {"generation": True, "posted_messages": ["MSG-INV-0001-2"]},
    {"generation": 0, "posted_messages": ["MSG-INV-0001-2"]}])
def test_invalid_or_old_posted_state_has_no_suppression(tmp_path, doc):
    path = tmp_path / wake_queue.WAKES_REL
    path.parent.mkdir(parents=True)
    path.write_text("{" if doc is None else json.dumps({"schema": wake_queue.SCHEMA, **doc}), encoding="utf-8")
    assert wake_queue.posted_messages(tmp_path, 1) == set()
