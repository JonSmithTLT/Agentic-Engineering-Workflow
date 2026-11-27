"""The G3 client's per-host approval records (A-44 BOY-05.a, BOY-05.c, BOY-14; register E101), on every platform: what
a record holds and never holds, its atomic owner-only write, its pruning, the client's writes at the start, after each
read and at the exit, and its reading through a service that does not answer until the approval's expiry.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from aew import g3client as C
from aew import g3records as R
from aew.errors import OperatorAuthorizationRequired
from aew.harness import weaker_register
from aew.stg02 import wire as W

SRC = Path(C.__file__).resolve().parent
T0 = datetime(2026, 11, 27, 12, tzinfo=UTC)
# Planted where a record must never carry them (BOY-Q02): a typed value, a rendering line's text, a consent record
TYPED = "typed-value-planted-e101"
CONSENT = "consent:g3:planted-e101"


def pending(life_s: float = 300, now: datetime = T0) -> dict[str, Any]:
    """G3's PendingApproval with a rendering: two members' TEMPLATE lines, a typed field and an owner fact."""
    return {"approval_ref": "g3:approval:" + "ab" * 16, "state": "PENDING", "expires_at": W.utc(now + timedelta(
        seconds=life_s)), "set_digest": "sha256:" + "0" * 64, "rendering_digest": "sha256:" + "1" * 64,
        "consent_record": {"consent_set_ref": CONSENT},
        "rendering": [
            {"template_id": "g3:action:steering.mode.raise", "values": {}, "source": {"kind": "TEMPLATE"}},
            {"template_id": "g3:field", "values": {"value": TYPED},
             "source": {"kind": "TYPED_FIELD", "field_path": "intents[0].subject"}},
            {"template_id": "g3:action:owner.operation", "values": {}, "source": {"kind": "TEMPLATE"}},
            {"template_id": "g3:action:steering.mode.raise", "values": {}, "source": {"kind": "TEMPLATE"}},
        ]}


class Clock:
    def __init__(self, t: datetime = T0) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def test_a_record_holds_only_its_fields_and_never_a_typed_value_a_rendering_line_or_a_consent_record(
        tmp_path: Path) -> None:
    w = R.Writer(pending(), project="calc", directory=tmp_path, now=Clock())
    raw = w.path.read_text(encoding="utf-8")
    record = json.loads(raw)
    assert set(record) == R.FIELDS and R.valid(record)
    assert record["actions"] == ["steering.mode.raise", "owner.operation"]  # G3's TEMPLATE ids, each once, in order
    assert record["starter_role"] == "operator" and record["project"] == "calc" and record["from_request"] is None
    assert record["client"]["pid"] == os.getpid()
    for planted in (TYPED, CONSENT, "intents[0]", "rendering", "set_digest"):
        assert planted not in raw


def test_each_write_is_atomic_and_the_record_is_the_operators_alone(tmp_path: Path, monkeypatch) -> None:
    """A reader never sees a torn record: each write goes through a temporary file renamed over it. On Linux the
    directory is 0700 and the file 0600; on Windows no record is ever written (G3 refuses there before an approval
    exists), so the bits are not asserted there."""
    from aew import util

    writes: list[Path] = []
    real = util.atomic_write
    monkeypatch.setattr(util, "atomic_write", lambda p, d: writes.append(p) or real(p, d))
    directory = tmp_path / "state" / "aew" / "g3" / "requests"
    w = R.Writer(pending(), project=None, directory=directory, now=Clock())
    w.read(R.PENDING)
    w.finish("declined")
    assert writes == [w.path] * 3 and [p.name for p in directory.iterdir()] == [w.path.name]  # no temporary left
    if sys.platform != "win32":
        assert directory.stat().st_mode & 0o777 == 0o700 and w.path.stat().st_mode & 0o777 == 0o600


def test_the_client_writes_at_the_start_after_each_read_and_at_its_exit(tmp_path: Path) -> None:
    clock = Clock()
    w = R.Writer(pending(), project=None, directory=tmp_path, now=clock)
    first = json.loads(w.path.read_text())
    assert (first["state"], first["read_at"], first["g3_answered_at"], first["outcome"], first["exited_at"]) == (
        "PENDING", W.utc(T0), W.utc(T0), None, None)
    clock.t = T0 + timedelta(seconds=3)
    w.read(R.NO_ANSWER)  # no answer moves the read, never the time G3 last answered
    after = json.loads(w.path.read_text())
    assert (after["state"], after["read_at"], after["g3_answered_at"]) == ("NO_ANSWER", W.utc(clock.t), W.utc(T0))
    clock.t = T0 + timedelta(seconds=4)
    w.read(R.APPROVED)
    w.finish("approved_submitted")
    last = json.loads(w.path.read_text())
    assert (last["g3_answered_at"], last["outcome"], last["exited_at"]) == (
        W.utc(clock.t), "approved_submitted", W.utc(clock.t))


def test_a_record_leaves_by_its_expiry_plus_g3_06s_window_and_the_next_write_prunes_it(tmp_path: Path) -> None:
    """BOY-05.c: at most 25 minutes after the start, the window being G3-06's ceiling (the weaker register's)."""
    assert R.window_s() == weaker_register.WINDOW_S
    clock = Clock()
    old = R.Writer(pending(life_s=60), project=None, directory=tmp_path, now=clock)
    (tmp_path / "torn.json").write_text("{", encoding="utf-8")
    os.utime(tmp_path / "torn.json", (T0.timestamp(), T0.timestamp()))
    clock.t = T0 + timedelta(seconds=60 + R.window_s())  # not past yet: kept
    R.Writer(pending(now=clock.t) | {"approval_ref": "g3:approval:two"}, project=None, directory=tmp_path, now=clock)
    assert old.path.exists()
    clock.t += timedelta(seconds=C.EXPIRY_CEILING_S)
    R.Writer(pending(now=clock.t) | {"approval_ref": "g3:approval:three"}, project=None, directory=tmp_path,
             now=clock)
    assert not old.path.exists() and not (tmp_path / "torn.json").exists()


def test_a_write_that_fails_never_stops_the_client_and_says_why(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")
    w = R.Writer(pending(), project=None, directory=blocker / "requests", now=Clock())
    assert w.failed and "Error" in w.failed
    w.read(R.PENDING)  # still nothing raised


class _Service:
    """request.sock's GET, answering ``answers`` in turn, the last repeated, on the test's clock."""

    def __init__(self, answers: list[Any], clock: list[float]) -> None:
        self.answers, self.calls, self.clock = answers, 0, clock

    def __call__(self, sock_path: Any, method: str, path: str, body: Any = None, *, timeout: float = 0) -> Any:
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        assert self.calls < 10_000
        if answer == "none":
            from aew.errors import Unavailable

            raise Unavailable("no answer", reason="g3_unreachable")
        if answer == 503:
            return 503, {"code": "G3_UNAVAILABLE"}
        reply: dict[str, Any] = {"state": answer}
        if answer == "APPROVED":
            reply["consent_record"] = {"consent_set_ref": "consent:one"}
        return 200, reply


def _wait(monkeypatch, answers: list[Any], life_s: float = 20) -> tuple[Any, list[str], list[str]]:
    mono = [0.0]
    monkeypatch.setattr(C, "_g3", _Service(answers, mono))
    reads: list[str] = []
    said: list[str] = []

    def sleep(s: float) -> None:
        mono[0] += max(s, 0.01)

    try:
        out = C.await_decision(pending(life_s), now=lambda: T0, clock=lambda: mono[0], sleep=sleep,
                               on_read=reads.append, say=said.append, keep_reading=True)
    except OperatorAuthorizationRequired as exc:
        out = exc
    return out, reads, said


@pytest.mark.parametrize("silence", ["none", 503])
def test_the_client_keeps_reading_through_no_answer_until_the_expiry_and_says_so_once(monkeypatch, silence) -> None:
    """BOY-05.a: no answer or a 503 no longer ends the wait. Each read is recorded; the client prints once that G3 is
    not answering, until when it keeps trying, and that Ctrl+C stops it; and a service that answers again is read."""
    out, reads, said = _wait(monkeypatch, [silence, silence, "PENDING", "APPROVED"])
    assert out == {"consent_set_ref": "consent:one"}
    assert reads == ["NO_ANSWER", "NO_ANSWER", "PENDING", "APPROVED"]
    assert len(said) == 1 and "not answering" in said[0] and "Ctrl+C stops it" in said[0]
    assert "until 12:00:25 UTC" in said[0]  # the approval's 20 s life and the grace
    out, reads, said = _wait(monkeypatch, [silence])
    assert isinstance(out, OperatorAuthorizationRequired) and out.details["reason"] == "unanswered_until_expiry"
    assert set(reads) == {"NO_ANSWER"} and len(said) == 1


def test_the_stale_read_bound_is_the_clients_timeout_plus_two_polls() -> None:
    """BOY-14: a snapshot of the client's own constants, which moves when they move."""
    assert C.STALE_READ_S == C.TIMEOUT_S + 2 * C.POLL_S == 32


def _calls_to(tree: ast.AST, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and (
        (isinstance(n.func, ast.Attribute) and n.func.attr == name) or (isinstance(n.func, ast.Name)
                                                                       and n.func.id == name))]


def test_every_caller_in_aew_of_g3s_approval_request_writes_the_record() -> None:
    """BOY-Q04: each module that asks G3 for an approval makes a record writer and passes its reads to the wait: the
    command, and the operator endpoint's G3 path (G3-C's C3), which came after A-44 named the command alone."""
    callers = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _calls_to(tree, "request_approval") and path.name != "g3client.py":
            callers.append(path.relative_to(SRC).as_posix())
            assert _calls_to(tree, "Writer"), path
            waits = _calls_to(tree, "await_decision")
            assert waits and all(any(k.arg == "on_read" for k in w.keywords) for w in waits), path
    assert callers == ["cli/g3_commands.py", "harness/g3_adapter.py"]


def test_only_the_client_writes_or_prunes_the_directory() -> None:
    """BOY-05.a: of the modules that use the record module, only the G3 clients (the command and the operator
    endpoint's G3 path) make a writer, and none prunes but through it (the attention module, so the dashboard and
    status, only reads)."""
    writers = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if path.name == "g3records.py" or "g3records" not in text:
            continue
        tree = ast.parse(text)
        if _calls_to(tree, "Writer") or _calls_to(tree, "prune"):
            writers.append(path.relative_to(SRC).as_posix())
    assert writers == ["cli/g3_commands.py", "harness/g3_adapter.py"]
