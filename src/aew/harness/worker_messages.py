"""Supervisor-owned worker messaging (D-20 to D-23, A1 A3). No worker ever supplies an invocation or credential."""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aew import errors
from aew.coordination.layout import MAX_UNDELIVERED_LEAD
from aew.harness import bridge, wait_binding
from aew.harness.delivery import DEFAULT_WHEN, NEXT_STEP, WHEN_DELIVERY

if TYPE_CHECKING:
    from aew.harness.supervisor import Supervisor

_FINAL_CHECK_S = 5.0
_TICK_S = 0.25


class _Ended(Exception):
    pass


@dataclass
class _Offer:
    message: str
    prompt: str
    text: str
    metadata: dict[str, str]
    when: str
    wake: bool
    attempts: int = 0
    outcome: str = "uncertain"


@dataclass(frozen=True)
class FinalAdmissions:
    admitted: dict[str, str]
    interrupt_confirmed: bool
    deadline: float


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
        self._offers: dict[str, _Offer] = {}
        self._refused: set[str] = set()
        self._has_posted = False
        self._problem: str | None = None
        self._launch: tuple[str, list[str]] | None = None
        self._stop = threading.Event()
        self._drained = threading.Event()
        self._deadline: float | None = None
        self._drain_until: float | None = None

    @property
    def waiting(self) -> bool:
        """Live transport must hold this delivery lock while checking the hold and selecting/posting a message."""
        with self.delivery_lock:
            return self._pending > 0

    def launched(self, continuation: dict[str, Any] | None) -> None:
        ids = (continuation or {}).get("messages")
        if ids and (prompt := self.owner.adapter.coordination_launch_prompt()):
            self._launch = prompt, ids

    def start(self, deadline: float | None) -> None:
        """The heartbeat loop never waits on a control write or a transport call for messaging."""
        self._deadline = deadline

        def work() -> None:
            while not self._stop.is_set():
                drain = self._drain_until is not None
                try:
                    self.tick(select=self._can_post())
                except (errors.PermissionDenied, errors.IllegalTransition, errors.StaleAuthority):
                    pass  # authority or policy changed before the locked delivery check
                except (errors.AEWError, OSError) as exc:
                    self.report_problem(getattr(exc, "code", type(exc).__name__))
                if drain:
                    self._drained.set()
                    return
                self._stop.wait(_TICK_S)

        threading.Thread(target=work, name="aew-worker-message-delivery", daemon=True).start()

    def drained(self) -> bool:
        """Request a last admission read without waiting on the writer or provider from the watch loop."""
        if self._drain_until is None:
            self._drain_until = time.monotonic() + _FINAL_CHECK_S
        return self._drained.is_set() or time.monotonic() >= self._drain_until

    def stop(self) -> None:
        self._stop.set()

    @property
    def has_posted(self) -> bool:
        return self._has_posted

    def report_problem(self, code: str) -> None:
        if code != self._problem:
            self._problem = code
            self.owner.events({"event": "message_delivery_unavailable", "code": code})

    def tick(self, *, select: bool) -> None:
        sup = self.owner
        adapter = sup.adapter
        until = time.monotonic() + 2.0
        if self._launch:
            prompt, ids = self._launch
            outcome = adapter.coordination_admission(prompt)
            if outcome == "admitted":
                self._confirm(ids, "continuation", prompt)
                self._launch = None
            elif outcome in ("session_lost", "delivery_mismatch"):
                self._launch = None
        # Wait and transport serialize admission decisions. HTTP runs without the control-state lock.
        with self.delivery_lock:
            waiting = self.waiting
            for item in list(self._offers.values()):
                remaining = until - time.monotonic()
                if remaining <= 0 and select:
                    return
                outcome = adapter.coordination_admission(item.prompt, item.text, timeout=max(0.1, remaining))
                if outcome == "admitted":
                    self._confirm([item.message], "live", item.prompt)
                    del self._offers[item.message]
                elif outcome in ("session_lost", "delivery_mismatch"):
                    self._fail(item, outcome)
                elif (outcome == "pending" and item.outcome == "uncertain" and select
                      and (not waiting or item.when != NEXT_STEP)):
                    if item.attempts < 2:
                        self._post(item)
                    else:
                        self._fail(item, "unconfirmed")
                if item.message in self._offers:
                    self._offers[item.message] = self._offers.pop(item.message)
            if not select or not self._can_post() or not adapter.coordination_live or self._launch:
                return
            # Retry an uncertain earlier POST before sending another message so record order survives a lost response.
            blocked = {item.when for item in self._offers.values() if item.outcome == "uncertain"}
            if waiting:
                blocked.add(NEXT_STEP)
            if len(blocked) == len(WHEN_DELIVERY):
                return
            result = sup.engine.message_next_post(credential=sup._credential, run=sup.run, permit=self._can_post,
                                                 blocked=blocked)
            for mid in result["refused"]:
                if mid not in self._refused:
                    self._refused.add(mid)
                    sup.events({"event": "message_refused", "message": mid, "reason": "sender_revision"})
            message = result["message"]
            if message is None:
                return
            mid = message["id"]
            self._has_posted = True
            domain = f"{sup.engine.project_id}\0{mid}"
            prompt = "msg_" + hashlib.sha256(domain.encode()).hexdigest()[:26]
            when = message.get("when", DEFAULT_WHEN)
            offer = _Offer(mid, prompt, message["rendered"],
                           {"aew_message": mid, "aew_thread": sup.inv_id, "aew_when": when},
                           when, message.get("origin") == "harness_send")
            self._offers[mid] = offer
            self._post(offer)

    def _post(self, item: _Offer) -> None:
        if not self._can_post():
            return
        reported, problem = self.owner._authority()
        if not reported or problem:
            self._fail(item, "authority_unconfirmed")
            return
        self.owner.require_message_authority()
        if not self._can_post():
            return
        item.outcome = self.owner.adapter.coordination_post(
            item.prompt, item.text, item.metadata, retry=item.attempts > 0,
            delivery=WHEN_DELIVERY[item.when], wake=item.wake)
        item.attempts += 1
        if item.outcome not in ("offered", "uncertain"):
            self._fail(item, item.outcome)

    def _can_post(self) -> bool:
        return (not self._stop.is_set() and self._drain_until is None
                and (self._deadline is None or time.monotonic() < self._deadline))

    def capture_final_admissions(self) -> FinalAdmissions:
        """Ask the live adapter for one bounded snapshot before terminating the revoked run."""
        return self._capture_admissions(halt=True)

    def submit_admissions(self) -> dict[str, str] | None:
        """Settle observed admissions before entering the submission's control transaction."""
        if not self._offers or self._stop.is_set():
            return None
        return self._capture_admissions(halt=False).admitted

    def _capture_admissions(self, *, halt: bool) -> FinalAdmissions:
        adapter = self.owner.adapter
        deadline = time.monotonic() + _FINAL_CHECK_S
        offers = list(self._offers.values())[:MAX_UNDELIVERED_LEAD]
        admitted: dict[str, str] = {}
        results = threading.Lock()
        interrupt_confirmed = False

        def collect() -> None:
            nonlocal interrupt_confirmed
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if halt:
                interrupt_confirmed = adapter.coordination_halt(remaining)
            for item in offers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if adapter.coordination_admission(item.prompt, item.text, timeout=remaining) == "admitted":
                    with results:
                        if time.monotonic() < deadline:
                            admitted[item.message] = item.prompt

        check = threading.Thread(target=collect, name="aew-message-admissions", daemon=True)
        check.start()
        check.join(max(0.0, deadline - time.monotonic()))
        with results:
            return FinalAdmissions(admitted.copy(), interrupt_confirmed, deadline)

    def record_final_admissions(self, snapshot: FinalAdmissions) -> None:
        """Persist the snapshot after teardown, while the supervisor still holds the revoked credential."""
        sup = self.owner
        sup.events({"event": "message_final_admission_check", "interrupt_confirmed": snapshot.interrupt_confirmed,
                    "observed": len(snapshot.admitted)})
        try:
            sup.engine.message_final_check(credential=sup._credential, run=sup.run, admitted=snapshot.admitted,
                                           lock_timeout=max(0.0, snapshot.deadline - time.monotonic()))
        except (errors.AEWError, OSError) as exc:
            sup.events({"event": "message_final_admission_refused", "code": getattr(exc, "code", type(exc).__name__)})

    def _confirm(self, ids: list[str], via: str, prompt: str) -> None:
        if self._stop.is_set():
            return
        sup = self.owner
        sup.engine.message_confirm_delivery(credential=sup._credential, run=sup.run, ids=ids, via=via,
                                            transport_ref=prompt)

    def _fail(self, item: _Offer, reason: str) -> None:
        sup = self.owner
        sup.adapter.coordination_abandon(item.prompt)
        self._offers.pop(item.message, None)
        sup.events({"event": "message_delivery_failed", "message": item.message, "reason": reason})

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
                        pending = sup.engine.message_waiting(invocation_token=sup._credential, after=after)
                        if pending["messages"]:
                            sup.engine.message_deliver_wait(invocation_token=sup._credential, after=after,
                                                            send=final_send)
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
                binding, reason, lost_at = adapter.wait_binding_at_deadline()
                if binding is not None:
                    return binding
                refusal = errors.WaitBindingLostOnReconnect if lost_at is not None else errors.WaitOutsideAStep
                sup.events({"event": "message_wait_binding_refused", "run": sup.run, "reason": reason,
                            "binding_lost_at": lost_at, "code": refusal.code})
                if lost_at is not None:
                    raise refusal("the OpenCode event stream dropped since the last observed step boundary; "
                                  "the foreground shell call's lifetime is unknown and nothing was delivered. "
                                  "Retry the wait from a foreground shell call in a new step")
                raise errors.WaitOutsideAStep("no foreground shell call is open after the 2 s grace; nothing was "
                                              "delivered. Use a foreground shell call; otherwise reply and end "
                                              "your turn. Messages remain available for live delivery")
            sup._ending.wait(min(0.05, max(0, grace - time.monotonic())))
