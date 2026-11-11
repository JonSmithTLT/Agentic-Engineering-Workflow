"""Worker receipt writes use held authority and only IDs actually returned; no control lock across a socket send."""

from __future__ import annotations

import pytest
from test_coordination_store import world

from aew.errors import ReplyNotInThread, StaleAuthority


@pytest.fixture
def w(tmp_path):
    return world(tmp_path)


def test_the_send_releases_the_control_lock_and_cannot_consume_a_message_added_during_it(w):
    first = w.send()["message"]["id"]
    returned = []
    later = []

    def send(result):
        returned.append(result)
        later.append(w.send("A message not carried by this result.")["message"]["id"])

    revision = w.rev()
    w.e.message_deliver_wait(invocation_token=w.worker, after="", send=send)
    assert [m["id"] for m in returned[0]["messages"]] == [first]
    pending = w.e.message_waiting(invocation_token=w.worker, after="")
    assert [m["id"] for m in pending["messages"]] == later
    assert w.rev() == revision


def test_a_failed_bridge_send_writes_no_delivery_and_keeps_the_message_pending(w):
    mid = w.send()["message"]["id"]
    before = w.thread_path().read_bytes()

    def closed(result):
        raise OSError("client closed before send")

    with pytest.raises(OSError):
        w.e.message_deliver_wait(invocation_token=w.worker, after="", send=closed)
    assert w.thread_path().read_bytes() == before
    assert [m["id"] for m in w.e.message_waiting(invocation_token=w.worker, after="")["messages"]] == [mid]


def test_authority_lost_during_the_send_never_appends_to_the_sealed_thread(w):
    w.send()
    sealed = []

    def send(result):
        w.lead("invoke_cancel", invocation=w.inv, reason="ended while the result was in flight")
        sealed.append(w.thread_path().read_bytes())

    with pytest.raises(StaleAuthority):
        w.e.message_deliver_wait(invocation_token=w.worker, after="", send=send)
    assert w.thread_path().read_bytes() == sealed[0]
    thread = w.e.message_thread(w.inv)
    assert "sealed" in thread and not any(f["kind"] == "DELIVERED" for f in thread["messages"][0]["facts"])


def test_worker_tail_reads_consume_nothing_and_after_cannot_name_another_thread(w):
    mid = w.send()["message"]["id"]
    before = w.thread_path().read_bytes()
    view = w.e.message_read_worker(invocation_token=w.worker)
    assert view["thread"] == w.inv and [m["id"] for m in view["messages"]] == [mid]
    assert w.thread_path().read_bytes() == before
    with pytest.raises(ReplyNotInThread):
        w.e.message_waiting(invocation_token=w.worker, after="MSG-INV-9999-1")
    assert w.thread_path().read_bytes() == before
