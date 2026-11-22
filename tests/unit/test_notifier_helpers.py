"""The notifier helpers' bounded wait (tests/helpers/notifier.py): what a timeout says (review of #276, F2 and N3).

``until`` reports its describer's account on a timeout, and a describer that raises is reported in the message, never in
place of the timeout. ``thread_stack`` gives a running thread's stack, and none for a thread that has ended, whose
identifier may already name a newer thread."""

from __future__ import annotations

import threading

import pytest
from notifier import liveness_record, thread_stack, until

from aew.harness import broker_liveness


def test_a_describer_that_raises_never_hides_the_timeout():
    failed = r"timed out after 0.1s \(wait\.never\) waiting for x; the describer failed: ZeroDivisionError"
    with pytest.raises(AssertionError, match=failed):
        until(lambda: None, "wait.never", "x", describe=lambda: str(1 / 0))


def test_wait_for_close_retries_an_unreadable_beat_and_returns_the_closed_observation(monkeypatch, tmp_path):
    closed = {"closed_at": 1.0}
    reads = iter((broker_liveness.Unreadable(), None, {"closed_at": None}, closed))
    monkeypatch.setattr(broker_liveness, "read", lambda root: next(reads))
    assert until(lambda: liveness_record(tmp_path, closed=True), what="the closed beat") is closed


class _Recycled(threading.Thread):
    """A thread that has ended, whose identifier now names a running thread: this one."""

    @property
    def ident(self) -> int | None:
        return threading.get_ident()


def test_an_ended_thread_has_no_stack_even_once_its_identifier_names_another():
    ended = _Recycled(target=lambda: None, name="test-ended", daemon=True)
    ended.start()
    ended.join(10)
    assert not ended.is_alive()
    assert thread_stack(ended) == "(no stack: the thread is not running)"
    assert "test_an_ended_thread_has_no_stack" in thread_stack(threading.current_thread())  # a running one's own
