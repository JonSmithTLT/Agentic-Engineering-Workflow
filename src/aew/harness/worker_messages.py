"""Supervisor-owned worker messaging (D-20 to D-23, A1 A3). No worker ever supplies an invocation or credential."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aew import errors
from aew.harness import bridge, wait_binding

if TYPE_CHECKING:
    from aew.harness.supervisor import Supervisor


class _Ended(Exception):
    pass


def connected(conn: Any) -> bool:
    """A wait has no second request: EOF, a broken pipe or unexpected further bytes all end its lifetime."""
    try:
        return not conn.poll(0)
    except (EOFError, OSError):
        return False


class WorkerMessages:
    def __init__(self, supervisor: Supervisor) -> None:
        self.owner = supervisor
        self.delivery_lock = threading.RLock()
        self._pending = 0

    @property
    def waiting(self) -> bool:
        """Live transport must hold this delivery lock while checking the hold and selecting/posting a message."""
        with self.delivery_lock:
            return self._pending > 0

    def wait(self, args: dict[str, Any], conn: Any) -> bridge.ResultDelivery:
        try:
            timeout = float(args["timeout_s"])
        except ValueError:
            raise errors.UsageError("message wait timeout must be a finite number of seconds") from None
        if not math.isfinite(timeout) or not 0 <= timeout <= wait_binding.MAX_WAIT_S:
            raise errors.UsageError(f"message wait timeout must be between 0 and {wait_binding.MAX_WAIT_S} seconds")
        return bridge.ResultDelivery(lambda send: self._wait(args["after"], timeout, conn, send))

    def _wait(self, after: str, timeout: float, conn: Any, send: Callable[[Any], None]) -> None:
        sup = self.owner
        server = sup.bridge
        assert server is not None
        with server.serialized():
            sup.require_message_authority()
        deadline = time.monotonic() + timeout
        adapter = sup.adapter
        test_binding = bool(getattr(adapter, "TEST_ONLY_WAIT_BINDS_TO_RUN_END", False))
        if not getattr(adapter, "reports_steps", False) and not test_binding:
            raise errors.WaitUnsupported("this adapter/platform has no qualified foreground call/step lifetime "
                                         "reporting; reply and end your turn instead of waiting")
        with self.delivery_lock:
            self._pending += 1
        try:
            try:
                binding = self._bind(adapter, test_binding, deadline, conn)
            except _Ended:
                send({"outcome": "ended_early", "messages": []})
                return
            while True:
                if (sup._ending.is_set() or server.closed or not connected(conn)
                        or (not test_binding and not adapter.wait_binding_valid(binding))):
                    send({"outcome": "ended_early", "messages": [],
                          "next_action": "the wait ended early; call `aew message wait` again"})
                    return
                sent = False

                def final_send(result: Any) -> None:
                    nonlocal sent

                    def deliver() -> None:
                        nonlocal sent
                        if sup._ending.is_set() or server.closed or not connected(conn):
                            raise _Ended
                        sup.require_message_authority()
                        send(result)
                        sent = True

                    if test_binding:
                        deliver()
                    elif not adapter.while_wait_bound(binding, deliver):
                        raise _Ended

                try:
                    with self.delivery_lock, server.serialized():
                        sup.require_message_authority()
                        sup.engine.message_deliver_wait(invocation_token=sup._credential, after=after, send=final_send)
                except _Ended:
                    send({"outcome": "ended_early", "messages": [],
                          "next_action": "the wait ended early; call `aew message wait` again"})
                    return
                if sent:
                    return
                if time.monotonic() >= deadline:
                    try:
                        final_send({"outcome": "timed_out", "messages": []})
                    except _Ended:
                        send({"outcome": "ended_early", "messages": [],
                              "next_action": "the wait ended early; call `aew message wait` again"})
                    return
                sup._ending.wait(min(0.1, max(0, deadline - time.monotonic())))
        finally:
            with self.delivery_lock:
                self._pending -= 1

    def _bind(self, adapter: Any, test_binding: bool, deadline: float, conn: Any) -> Any:
        sup = self.owner
        server = sup.bridge
        assert server is not None
        if test_binding:
            sup.events({"event": "message_wait_test_binding", "run": sup.run})
            return None
        grace = min(deadline, time.monotonic() + wait_binding.CALL_GRACE_S)
        while True:
            binding = adapter.wait_binding()
            if binding is not None:
                return binding
            if sup._ending.is_set() or server.closed or not connected(conn):
                raise _Ended
            with server.serialized():
                sup.require_message_authority()
            if time.monotonic() >= grace:
                raise errors.WaitOutsideAStep("no foreground shell call is open after the 2 s grace; nothing was "
                                              "delivered. Use a foreground shell call; otherwise reply and end "
                                              "your turn. Messages remain available for live delivery")
            sup._ending.wait(min(0.05, max(0, grace - time.monotonic())))
