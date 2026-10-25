"""The notifier helpers' bounded wait (tests/helpers/notifier.py): what a timeout says (review of #276, F2 and N3).

``until`` reports its describer's account on a timeout, and a describer that raises is reported in the message, never in
place of the timeout. ``thread_stack`` gives a running thread's stack, and none for a thread that has ended, whose
identifier may already name a newer thread."""

from __future__ import annotations

import threading

import pytest
from notifier import thread_stack, until


def test_a_describer_that_raises_never_hides_the_timeout():
    with pytest.raises(AssertionError, match=r"timed out waiting for x; the describer failed: ZeroDivisionError"):
        until(lambda: None, 0.1, "x", describe=lambda: str(1 / 0))


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
