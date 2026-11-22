"""Absolute-time staged close: no total-byte cap, no fake-clock hang on a broken loop."""

import socket
from types import SimpleNamespace

from aew import http_close as H


def test_a_trickling_sender_cannot_renew_the_absolute_close_deadline(monkeypatch):
    now = [0.0]
    waits, shutdowns, closes = [], [], []
    calls = [0]

    class Sender:
        def settimeout(self, seconds):
            waits.append(seconds)

        def shutdown(self, how):
            shutdowns.append(how)

        def close(self):
            closes.append(True)

        def recv(self, size):
            calls[0] += 1
            assert calls[0] <= 3, "drain renewed its deadline instead of using an absolute bound"
            now[0] += H.REFUSAL_DRAIN_S / 2
            return b"x"

    monkeypatch.setattr(H, "time", SimpleNamespace(monotonic=lambda: now[0]))
    H.close_after_response(Sender())
    assert calls == [2] and waits == [H.REFUSAL_DRAIN_S, H.REFUSAL_DRAIN_S / 2]
    assert shutdowns == [socket.SHUT_WR] and closes == [True]


def test_large_input_is_discarded_to_eof_without_a_byte_cap(monkeypatch):
    calls, closes = [0], []
    chunks = 2 * 1024 * 1024 // H.RECV_CHUNK

    class Sender:
        def settimeout(self, seconds):
            assert seconds == H.REFUSAL_DRAIN_S

        def shutdown(self, how):
            assert how == socket.SHUT_WR

        def close(self):
            closes.append(True)

        def recv(self, size):
            calls[0] += 1
            assert calls[0] <= chunks + 1, "drain ignored EOF"
            return b"x" * size if calls[0] <= chunks else b""

    monkeypatch.setattr(H, "time", SimpleNamespace(monotonic=lambda: 0.0))
    H.close_after_response(Sender())
    assert calls == [chunks + 1] and closes == [True]
