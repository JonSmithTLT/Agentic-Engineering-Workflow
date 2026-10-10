"""The coordination store (register F9, F9-A MS1; ADR-0017; F9-A plan v4 D-1 to D-12, D-15, D-31, D-32).

A Lead message and a worker reply are recorded on the invocation's own append-only thread under the control lock,
committing nothing: identity, idempotency, replies, bounded refs and the switch, with no surface. While messaging is
off (the default, and M4-H's treatment) nothing is written: no thread, no marker, no ``.aew/coordination/``.

Projects are built in process through the engine's own commands (as ``tools/perf/control_plane.py`` builds its
templates), so each test costs one git repository and no CLI process.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from conftest import make_git_repo, policy_pins
from invariants import assert_control_invariants, load_control

from aew import util
from aew.coordination import layout as L
from aew.engine import coordination_ops as C
from aew.engine.api import Engine
from aew.engine.base import POLICY_PINS, as_v1
from aew.engine.store import serialize_control
from aew.errors import (
    AEWError,
    CoordinationLimit,
    IdempotencyConflict,
    IllegalTransition,
    IntegrityError,
    LeadInboxFull,
    MessagingDisabled,
    MigrationRequired,
    NotAWorker,
    RefOutOfScope,
    RefUnknown,
    ReplyNotInThread,
    StaleAuthority,
    StaleRevision,
    ValidationFailed,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "perf"))
import control_plane as CP  # noqa: E402

OPERATOR = {"authorized_by": "operator-tty"}  # the terminal channel, substituted in-process (conftest.as_operator)
EXECUTION = ".aew/policy/execution.yaml"
QUICK_CHECKS = {"schema": "aew/checks/v1", "baseline_failures": [],
                "checks": {"unit": {"configured": True, "command": ["{python}", "-c", "import calc.core"], "cwd": ".",
                                    "timeout_s": 120, "description": "import check"}}}


@dataclass
class World:
    """One project with a RUNNING Ticket and its active implementer."""

    root: Path
    e: Engine
    token: str
    wid: str
    inv: str
    worker: str  # the implementer's invocation credential
    workspace: Path

    def rev(self) -> int:
        return self.e.store.read()["revision"]

    def lead(self, method: str, **kw: Any) -> Any:
        return getattr(self.e, method)(token=self.token, expect_rev=self.rev(), **kw)

    def send(self, body: str = "Requirement 4 is not met: check shutdown while recv() blocks.", **kw: Any) -> Any:
        kw.setdefault("token", self.token)
        kw.setdefault("to", self.inv)
        if "expect_rev" not in kw:
            kw["expect_rev"] = self.rev()
        return self.e.message_record_lead(body=body, **kw)

    def reply(self, in_reply_to: str | None, body: str = "Confirmed; correcting it.", **kw: Any) -> Any:
        kw.setdefault("invocation_token", self.worker)
        return self.e.message_record_worker(in_reply_to=in_reply_to, body=body, **kw)

    def thread_path(self, inv: str | None = None) -> Path:
        return self.root / ".aew" / L.thread_rel(self.wid, inv or self.inv)

    def control_bytes(self) -> bytes:
        return (self.root / ".aew/state/control.yaml").read_bytes()

    def coordination_files(self) -> list[str]:
        aew = self.root / ".aew"
        return sorted(p.relative_to(aew).as_posix() for p in aew.rglob("*")
                      if "coordination" in p.relative_to(aew).parts)


def set_messaging(root: Path, value: str | None) -> None:
    """Edit the execution policy's switch (``None`` removes the key); adoption is the caller's."""
    policy = root / EXECUTION
    data = util.load_yaml(policy.read_text(encoding="utf-8"))
    if value is None:
        data.pop("coordination", None)
    else:
        data["coordination"] = {"messaging": value}
    policy.write_text(util.dump_yaml(data), encoding="utf-8", newline="\n")


def pin(root: Path) -> None:
    """Fixture setup only: pin the policy files as they are, as if the project had been initialized with them."""
    state = load_control(root)
    state[POLICY_PINS] = policy_pins(root)
    (root / ".aew/state/control.yaml").write_bytes(serialize_control(state))


def world(tmp_path: Path, *, messaging: str | None = "enabled", checks: bool = False) -> World:
    root = make_git_repo(tmp_path / "repo", CP.FILES)
    Engine.initialize(root, project_id="calc")
    if checks:
        (root / ".aew/policy/checks.yaml").write_text(util.dump_yaml(QUICK_CHECKS), encoding="utf-8", newline="\n")
    pin(root)
    e = Engine.discover(root)
    token = e.lead_acquire(expect_rev=0, session_label="lead-a")["token"]
    w = World(root, e, token, "", "", "", root)
    if messaging is not None:  # the operator's adoption, which also registers the project when it enables (MS2, D-39)
        set_messaging(root, messaging)
        e.manifest_adopt(token=token, expect_rev=w.rev(), reason=f"messaging {messaging}", authorization=OPERATOR)

    w.wid = w.lead("work_create", kind="ticket", title="Add subtract()", risk_class=1, mutating=True,
                   scope_paths=["calc/**", "tests/**"], goal_backwards=["calc.core.subtract(5, 3) == 2"],
                   contract=["changes stay in calc/ and tests/"])["id"]
    w.lead("plan_propose", no_assurance=True, work_id=w.wid, body=CP.PLAN, affected_paths=["calc/core.py"])
    w.lead("plan_accept", work_id=w.wid, revision=1)
    out = w.lead("work_assign", work_id=w.wid)
    w.lead("work_transition", work_id=w.wid, to="RUNNING")
    w.inv, w.worker, w.workspace = out["invocation"], out["invocation_token"], Path(out["workspace"]["path"])
    return w


@pytest.fixture
def w(tmp_path) -> World:
    return world(tmp_path)


# ---------------------------------------------------------------------------------------------- identity


def test_a_message_names_its_sender_recipient_unit_revision_and_invocation(w):
    """D-6 (invariant 15): every message names who sent it (with the Lead generation), to whom, about which unit and
    invocation, through which channel, and the revision it was checked against."""
    rev = w.rev()
    sent = w.send(channel="lead_broker")
    m = sent["message"]
    assert sent["ok"] and not sent["duplicate"] and sent["thread"] == w.inv and sent["revision"] == rev
    assert m["id"] == f"MSG-{w.inv}-1" and m["thread"] == w.inv and m["seq"] == 1
    assert m["sender"] == "lead:1" and m["recipient"] == f"invocation:{w.inv}"
    assert m["work_unit"] == w.wid and m["channel"] == "lead_broker" and m["checked_rev"] == rev
    assert m["kind"] == "instruction" and m["in_reply_to"] is None and m["refs"] == []
    assert m["schema"] == "aew/coordination-message/v1" and m["created_at"]
    replied = w.reply(m["id"])["message"]
    assert replied["sender"] == f"invocation:{w.inv}" and replied["recipient"] == "lead:1"
    assert replied["kind"] == "status" and replied["channel"] == "run_bridge" and replied["in_reply_to"] == m["id"]
    assert sent["facts"] == [{"kind": "RECORDED"}]
    assert_control_invariants(w)


def test_ticket_revision_is_null_on_a_dormant_project(w):
    """D-9: Ticket revisions are F4's; on a project that records none the binding is null. The enabled case lands with
    whichever of MS1 and F4 S2c merges second."""
    assert w.send()["message"]["ticket_revision"] is None
    assert all(m["ticket_revision"] is None for m in w.e.message_thread(w.inv)["messages"])


def test_message_ids_are_stable_and_ordered_within_a_thread(w):
    """D-2: ``MSG-<INV>-<n>`` is the thread's own sequence, contiguous; reading never renumbers."""
    first = w.send("one")["message"]["id"]
    second = w.reply(first, "two")["message"]["id"]
    third = w.send("three", in_reply_to=second)["message"]["id"]
    assert [first, second, third] == [f"MSG-{w.inv}-{n}" for n in (1, 2, 3)]
    for _ in range(2):
        read = w.e.message_thread(w.inv)
        assert [m["id"] for m in read["messages"]] == [first, second, third]
        assert [m["seq"] for m in read["messages"]] == [1, 2, 3] and read["lines"] == 3


def test_recording_takes_the_control_lock_and_moves_no_revision(w, monkeypatch):
    """D-4: the append happens under the control lock, and nothing is committed: the control file, its revision, the
    last transition and the transition log are exactly as they were."""
    held = []
    real = C._append_line
    monkeypatch.setattr(C, "_append_line", lambda path, line: (held.append(w.e.store.held), real(path, line)))
    before, logs = w.control_bytes(), sorted((w.root / ".aew/state/log").glob("*"))
    sent = w.send()
    w.reply(sent["message"]["id"])
    assert held == [1, 1]  # each append ran inside the writer's locked session
    assert w.control_bytes() == before and sorted((w.root / ".aew/state/log").glob("*")) == logs
    assert sent["revision"] == load_control(w.root)["revision"]


# ---------------------------------------------------------------------------------------------- revision and retries


def test_a_lead_message_with_a_stale_expect_rev_records_nothing(w):
    """D-4 step 2, D-17 (N2): ``expect_rev`` is the revision the Lead read, checked under the lock before anything else
    runs; a stale one is refused and no thread, marker or line is written."""
    stale = w.rev() - 1
    with pytest.raises(StaleRevision) as exc:
        w.send(expect_rev=stale)
    assert exc.value.details["current"] == w.rev()
    with pytest.raises(StaleRevision):
        w.send(expect_rev=None)
    assert w.coordination_files() == []


def test_a_lead_retry_with_a_new_expect_rev_returns_the_existing_message(w):
    """D-8 (N2): ``expect_rev`` is not part of the derivation. A Lead whose retry was refused as stale re-reads and
    retries with the new revision, and gets the original back: the first attempt was recorded."""
    first = w.send(expect_rev=w.rev())
    w.lead("checkpoint", note="the revision moves", next_action="retry the message")
    with pytest.raises(StaleRevision):
        w.send(expect_rev=first["revision"])
    again = w.send(expect_rev=w.rev())
    assert again["duplicate"] and again["message"] == first["message"]
    assert len(w.e.message_thread(w.inv)["messages"]) == 1


def test_a_retry_with_the_same_idempotency_id_returns_the_existing_message(w):
    """D-8, F9-A1 §6: a retry after a lost response returns the existing message with its facts; nothing is added."""
    first = w.send(idempotency_id="lead-7:fix-shutdown")
    size = w.thread_path().stat().st_size
    again = w.send(idempotency_id="lead-7:fix-shutdown")
    assert again["duplicate"] and again["message"] == first["message"] and again["facts"] == [{"kind": "RECORDED"}]
    assert "note" not in again  # an explicit id: the repeat was the sender's own retry
    assert w.thread_path().stat().st_size == size
    reply = w.reply(first["message"]["id"], idempotency_id="r1")
    assert w.reply(first["message"]["id"], idempotency_id="r1")["message"] == reply["message"]
    assert len(w.e.message_thread(w.inv)["messages"]) == 2


def test_a_verbatim_retry_without_an_idempotency_id_returns_the_existing_message(w):
    """D-8: an omitted id is derived from the content, so a verbatim retry returns the original, and the answer says
    that a deliberate repeat needs an explicit id. Different content is a new message."""
    first = w.send("Also test peer disconnect.")
    again = w.send("Also test peer disconnect.")
    assert again["duplicate"] and again["message"]["id"] == first["message"]["id"]
    assert "explicit idempotency_id" in again["note"]
    assert first["message"]["idempotency_id"].startswith("sha256:")
    deliberate = w.send("Also test peer disconnect.", idempotency_id="again-on-purpose")
    other = w.send("Also test peer disconnect, twice.")
    assert not deliberate["duplicate"] and not other["duplicate"]
    assert len(w.e.message_thread(w.inv)["messages"]) == 3


def test_a_new_generation_resending_a_superseded_message_records_a_new_one(w):
    """D-8 (F2): ids are scoped by sender including the generation, so a new Lead's re-send after a handoff never
    matches the old generation's message; the new generation's own retry still does."""
    old = w.send("Re-run the integration test.")["message"]
    offer = w.lead("lead_handoff_offer", note="handing over", carry_invocations=[w.inv])["offer"]
    accepted = w.e.lead_handoff_accept(offer=offer, expect_rev=w.rev(), session_label="lead-b")
    w.token = accepted["token"]
    new = w.send("Re-run the integration test.")
    assert not new["duplicate"] and new["message"]["id"] != old["id"] and new["message"]["sender"] == "lead:2"
    assert w.send("Re-run the integration test.")["message"] == new["message"]
    assert [m["sender"] for m in w.e.message_thread(w.inv)["messages"]] == ["lead:1", "lead:2"]


def test_derived_idempotency_ids_never_collide_across_field_boundaries():
    """D-8 (F2): the derivation hashes a canonical JSON array, so moving text across a field boundary changes it."""
    base = ("lead:1", "INV-0001", None, "instruction", "ab", ["ticket:T-0001"])
    variants = [
        base,
        ("lead:1", "INV-0001", None, "instruction", "a", ["bticket:T-0001"]),
        ("lead:1", "INV-0001", None, "instructio", "nab", ["ticket:T-0001"]),
        ("lead:1", "INV-00011", None, "instruction", "ab", ["ticket:T-0001"]),
        ("lead:", "1INV-0001", None, "instruction", "ab", ["ticket:T-0001"]),
        ("lead:1", "INV-0001", None, "instruction", "ab", ["ticket:T-", "0001"]),
        ("lead:1", "INV-0001", "", "instruction", "ab", ["ticket:T-0001"]),
        ("lead:2", "INV-0001", None, "instruction", "ab", ["ticket:T-0001"]),
    ]
    ids = {C.derived_idempotency_id(*v) for v in variants}
    assert len(ids) == len(variants)
    assert C.derived_idempotency_id(*base) == C.derived_idempotency_id(*base)


def test_the_same_idempotency_id_with_different_content_is_refused(w):
    """D-8: the same id with another body, kind, refs or reply target is refused, naming the message and what differs;
    nothing is recorded."""
    first = w.send("Check shutdown.", idempotency_id="k1")["message"]
    for change, field in (({"body": "Check startup."}, "body"), ({"kind": "question"}, "kind"),
                          ({"refs": ["ticket:" + w.wid]}, "refs"), ({"in_reply_to": first["id"]}, "in_reply_to")):
        kw = {"body": "Check shutdown.", "idempotency_id": "k1", **change}
        with pytest.raises(IdempotencyConflict) as exc:
            w.send(**kw)
        assert exc.value.details["existing"] == first["id"] and exc.value.details["fields"] == [field]
    assert len(w.e.message_thread(w.inv)["messages"]) == 1


RACER = """
import json, os, sys, time
from pathlib import Path
from aew.engine.api import Engine
root, inv, rev, go = sys.argv[1:]
while not Path(go).exists():
    time.sleep(0.005)
out = Engine.discover(Path(root)).message_record_lead(token=os.environ["RACE_LEAD_TOKEN"], expect_rev=int(rev), to=inv,
                                                     body="race", idempotency_id="race-1")
print(json.dumps({"id": out["message"]["id"], "duplicate": out["duplicate"]}))
"""


def test_two_processes_racing_one_idempotency_id_record_one_message(w, tmp_path):
    """D-4, D-8: the idempotency check and the append run under one control lock, so two processes sending the same
    id at once record one message, and the loser gets it back as a duplicate."""
    go = tmp_path / "go"
    kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    env = {**os.environ, "RACE_LEAD_TOKEN": w.token}
    procs = [subprocess.Popen([sys.executable, "-c", RACER, str(w.root), w.inv, str(w.rev()), str(go)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw) for _ in range(2)]
    time.sleep(0.5)  # both started and polling (a late starter still races correctly: it finds the message)
    go.write_text("go", encoding="utf-8")
    results = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
        results.append(json.loads(out))
    assert {r["id"] for r in results} == {f"MSG-{w.inv}-1"}
    assert sorted(r["duplicate"] for r in results) == [False, True]
    assert len(w.e.message_thread(w.inv)["messages"]) == 1


# ---------------------------------------------------------------------------------------------- the thread on disk


def test_the_first_thread_writes_the_project_marker_first_and_fsyncs_it(w, monkeypatch):
    """D-31 (N5): before the project's first thread file exists, the marker is published create-exclusive (its bytes
    synced before the rename) and its directory and ``.aew/`` are synced. Later messages leave it as it is."""
    aew = w.root / ".aew"
    marker, thread = aew / L.MARKER_REL, w.thread_path()
    events: list[tuple[str, str, bool]] = []
    real_create, real_sync = util.create_exclusive, util.fsync_dir

    def create(path, data):
        events.append(("create", Path(path).relative_to(aew).as_posix(), thread.exists()))
        real_create(path, data)

    def sync(path):
        events.append(("sync", Path(path).relative_to(aew).as_posix() or ".", thread.exists()))
        real_sync(path)

    monkeypatch.setattr(util, "create_exclusive", create)
    monkeypatch.setattr(util, "fsync_dir", sync)
    w.send()
    assert events[:3] == [("create", L.MARKER_REL, False), ("sync", L.COORDINATION_DIR, False), ("sync", ".", False)]
    record = util.load_yaml(marker.read_text(encoding="utf-8"))
    assert record["schema"] == L.MARKER_SCHEMA and record["first_thread"] == w.inv and record["created_at"]
    assert "recreated" not in record
    before = marker.read_bytes()
    events.clear()
    w.send("a second message")
    assert marker.read_bytes() == before and events == []


def test_a_removed_marker_is_recreated_and_says_so(w):
    """D-31: the marker is never removed by AEW. A writer that finds it gone while a thread exists writes it again,
    marked as a recreation with its time, so `doctor` and the audit can still see that the original was deleted."""
    w.send()
    marker = w.root / ".aew" / L.MARKER_REL
    original = util.load_yaml(marker.read_text(encoding="utf-8"))
    marker.unlink()
    w.send("after the marker was removed")
    again = util.load_yaml(marker.read_text(encoding="utf-8"))
    assert again["recreated"] is True and again["recreated_at"] and again["first_thread"] == w.inv
    assert "recreated" not in original


def test_creating_a_thread_fsyncs_its_directory(w, monkeypatch):
    """F13c: a new thread file's directory entry is synced once the file exists; appends to it sync the file only."""
    synced: list[tuple[Path, bool]] = []
    real = util.fsync_dir
    monkeypatch.setattr(util, "fsync_dir", lambda p: (synced.append((Path(p), w.thread_path().exists())), real(p)))
    w.send()
    assert (w.thread_path().parent, True) in synced
    synced.clear()
    w.send("another")
    assert synced == []


@pytest.mark.parametrize("leftover", ["directory", "empty_file", "torn_line", "first_line_then_crash"])
def test_a_retry_after_a_crashed_first_attempt_still_syncs_every_directory_entry(tmp_path, monkeypatch, leftover):
    """F13c, D-31 (PR #160 review, m2; re-review R1): whatever a crashed first attempt left behind, every directory
    entry the thread depends on is synced before its first complete line exists: `.aew/coordination/` and `.aew/`
    (the marker is durable before the thread), then the thread's directory and its unit's directory. The leftovers:
    the marker and the thread's directory; also an empty file; also a torn first line; or the first line itself,
    appended and synced, with the process dying right after. In the last case the syncs ran in the crashed attempt,
    before its append, and the retry is answered as a duplicate with nothing left to sync."""
    w = world(tmp_path)
    aew = w.root / ".aew"
    events: list[tuple[str, bool]] = []  # (a directory synced, or "append"), and whether a complete line existed

    def complete() -> bool:
        return w.thread_path().is_file() and b"\n" in w.thread_path().read_bytes()

    real_sync, real_append = util.fsync_dir, C._append_line
    monkeypatch.setattr(util, "fsync_dir", lambda p: (
        events.append((Path(p).resolve().relative_to(aew.resolve()).as_posix() or ".", complete())), real_sync(p)))
    monkeypatch.setattr(C, "_append_line", lambda path, line: (events.append(("append", complete())),
                                                               real_append(path, line)))
    syncs = [L.COORDINATION_DIR, ".", f"work/{w.wid}/coordination", f"work/{w.wid}"]
    body = "the instruction"
    if leftover == "first_line_then_crash":
        class Crash(BaseException):
            """The process dies between the line's fsync and anything after it."""

        def append_then_die(path, line):
            events.append(("append", complete()))
            real_append(path, line)
            raise Crash

        monkeypatch.setattr(C, "_append_line", append_then_die)
        with pytest.raises(Crash):
            w.send(body)
        assert events == [(d, False) for d in syncs] + [("append", False)]  # synced before the first line existed
        monkeypatch.setattr(C, "_append_line", lambda path, line: (events.append(("append", complete())),
                                                                   real_append(path, line)))
        events.clear()
        assert w.send(body)["duplicate"]  # the retry is answered from the thread
        assert events == []
    else:
        util.create_exclusive(aew / L.MARKER_REL, util.dump_yaml({"schema": L.MARKER_SCHEMA, "created_at": "then",
                                                                  "first_thread": w.inv}))
        w.thread_path().parent.mkdir(parents=True)
        if leftover != "directory":
            w.thread_path().write_bytes(b"" if leftover == "empty_file" else b'{"h":"00","mess')
        events.clear()
        assert not w.send(body)["duplicate"]
        assert events == [(d, False) for d in syncs] + [("append", False)]
    assert [m["id"] for m in w.e.message_thread(w.inv)["messages"]] == [f"MSG-{w.inv}-1"]
    events.clear()
    w.send("a later message")
    assert events == [("append", True)]  # later appends sync no directory


def test_a_writer_whose_control_lock_is_not_intact_writes_nothing(w, monkeypatch):
    """D-4 (PR #160 review, m1): the thread writer makes the commit's check (`require_lock_intact`) before it writes,
    so a writer that may no longer exclude others writes no marker, no repair and no line. (The lock is reported lost
    here; the POSIX test below removes it for real.)"""
    from aew.engine.lock import FileLock

    monkeypatch.setattr(FileLock, "intact", lambda self: False)
    with pytest.raises(IntegrityError) as exc:
        w.send()
    assert exc.value.details["reason"] == "lock_lost" and w.coordination_files() == []


@pytest.mark.skipif(sys.platform == "win32", reason="Windows refuses to remove an open file")
def test_a_writer_whose_lock_file_was_removed_appends_nothing_and_the_thread_stays_readable(w, monkeypatch):
    """D-4 (PR #160 review, m1; `repro/r2_lock_split_append.py`): `.aew/local/` deleted under a running writer lets a
    second writer lock a new file and append. The first writer then finds its lock not intact and appends nothing, so
    the chain never forks: the thread stays readable and writable."""
    first = w.send("first")["message"]["id"]
    w.reply(first, "ack")
    real = C.Coordination._ensure_marker
    raced = {"done": False}

    def racing(self, invocation):  # runs between the writer's lock checks: another writer gets in here
        if not raced["done"]:
            raced["done"] = True
            (w.root / ".aew/local/control.lock").unlink()
            other = Engine.discover(w.root).message_record_lead(token=w.token, expect_rev=w.rev(), to=w.inv,
                                                                body="from writer B")
            raced["other"] = other["message"]["id"]
        return real(self, invocation)

    monkeypatch.setattr(C.Coordination, "_ensure_marker", racing)
    with pytest.raises(IntegrityError, match="removed or replaced"):
        w.send("from writer A")
    # A worker's text is labelled untrusted in the read (MS2).
    assert [m.get("body", m.get("untrusted_text")) for m in w.e.message_thread(w.inv)["messages"]] == \
        ["first", "ack", "from writer B"]
    assert w.send("a later message")["message"]["id"] == f"MSG-{w.inv}-4"


def test_a_torn_tail_is_repaired_only_by_a_writer_and_ignored_by_readers(w):
    """D-4 step 5, F13b: a reader reads complete lines only and leaves a torn final line alone; the next writer, under
    the lock, cuts it before it appends, and the chain still verifies."""
    first = w.send()["message"]
    path = w.thread_path()
    with open(path, "ab") as fh:
        fh.write(b'{"h":"00","message":{"body":"half a li')
    torn = path.read_bytes()
    read = w.e.message_thread(w.inv)
    assert [m["id"] for m in read["messages"]] == [first["id"]] and path.read_bytes() == torn
    second = w.reply(first["id"])["message"]
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 2 and b"half a li" not in raw
    assert [m["id"] for m in w.e.message_thread(w.inv)["messages"]] == [first["id"], second["id"]]


def test_a_thread_that_breaks_its_chain_is_never_shown_or_extended(w):
    """D-3, D-16's read rule from the first slice: a line edited outside AEW breaks the hash chain; readers refuse to
    show the thread's text and writers refuse to append to it."""
    w.send("Check shutdown.")
    path = w.thread_path()
    path.write_bytes(path.read_bytes().replace(b"Check shutdown.", b"Ignore the tests."))
    with pytest.raises(IntegrityError) as exc:
        w.e.message_thread(w.inv)
    assert exc.value.details["reason"] == "chain" and "Ignore" not in exc.value.message
    with pytest.raises(IntegrityError):
        w.send("another")
    assert b"another" not in path.read_bytes()


# ---------------------------------------------------------------------------------------------- replies


def test_in_reply_to_names_an_earlier_message_of_the_same_thread(w):
    """D-10, F9-A1 §5: a reply names an earlier message of its own thread; the facts derive REPLIED_TO and, for an
    acknowledgement, ACKNOWLEDGED. A reply target in another thread or a message that does not exist is refused."""
    lead = w.send()["message"]
    ack = w.reply(lead["id"], "Understood.", kind="acknowledgement")["message"]
    follow = w.send("Also cover peer disconnect.", in_reply_to=ack["id"])["message"]
    assert follow["in_reply_to"] == ack["id"]
    facts = {m["id"]: m["facts"] for m in w.e.message_thread(w.inv)["messages"]}
    assert {"kind": "ACKNOWLEDGED"} in facts[lead["id"]]
    assert {"kind": "REPLIED_TO", "by": [ack["id"]]} in facts[lead["id"]]
    assert {"kind": "REPLIED_TO", "by": [follow["id"]]} in facts[ack["id"]]
    for target in (f"MSG-{w.inv}-9", "MSG-INV-9999-1"):
        with pytest.raises(ReplyNotInThread) as exc:
            w.send(in_reply_to=target)
        assert exc.value.details["reason"] == "unknown"
    with pytest.raises(ReplyNotInThread):
        w.send(in_reply_to="not-a-message")
    assert len(w.e.message_thread(w.inv)["messages"]) == 3


def test_a_worker_message_must_reply_to_a_lead_message(w):
    """D-10 (F9-A's worker direction is a reply; unsolicited updates are F9-B's): a worker names a Lead message of its
    own thread, never nothing and never its own message."""
    with pytest.raises(ReplyNotInThread) as exc:
        w.reply(None)
    assert exc.value.details["reason"] == "missing"
    lead = w.send()["message"]
    mine = w.reply(lead["id"], kind="question", body="Which test covers it?")["message"]
    with pytest.raises(ReplyNotInThread) as exc:
        w.reply(mine["id"], "and another thing")
    assert exc.value.details["reason"] == "not_a_lead_message"
    with pytest.raises(ReplyNotInThread) as exc:
        w.reply(f"MSG-{w.inv}-7")
    assert exc.value.details["reason"] == "unknown"
    assert [m["id"] for m in w.e.message_thread(w.inv)["messages"]] == [lead["id"], mine["id"]]


# ---------------------------------------------------------------------------------------------- bounds and refs


def test_bodies_are_bounded_and_never_carry_a_credential(w):
    """D-7: a body is 1 to 4,000 characters, never blank, and never carries an AEW credential (its harness would
    persist it); kinds are the eight of F9-A1 §9. Each refusal names its bound, and nothing is written."""
    with pytest.raises(CoordinationLimit) as exc:
        w.send("x" * (L.MAX_BODY_CHARS + 1))
    assert exc.value.details == {"bound": "body_chars", "limit": 4000, "actual": 4001}
    assert w.send("x" * L.MAX_BODY_CHARS)["ok"]
    with pytest.raises(CoordinationLimit) as exc:
        w.send(f"use this: {w.token}")
    assert exc.value.details["bound"] == "credential" and w.token not in exc.value.message
    with pytest.raises(CoordinationLimit):
        w.reply(f"MSG-{w.inv}-1", body=f"my credential is {w.worker}")
    for blank in ("", "   \n"):
        with pytest.raises(ValidationFailed):
            w.send(blank)
    with pytest.raises(ValidationFailed) as exc:
        w.send(kind="command")
    assert exc.value.details["reason"] == "kind"
    with pytest.raises(ValidationFailed):
        w.send(idempotency_id="has spaces")
    raw = w.thread_path().read_bytes()
    assert raw.count(b"\n") == 1 and w.token.encode() not in raw and w.worker.encode() not in raw
    assert (L.MAX_BODY_CHARS, L.MAX_REFS, L.MAX_REF_CHARS, L.MAX_THREAD_MESSAGES, L.MAX_UNDELIVERED_LEAD,
            L.MAX_UNSEEN_WORKER) == (4000, 8, 200, 200, 16, 20)


def test_thread_bounds_refuse_with_the_bound_named(w, monkeypatch):
    """D-7: at most 16 Lead messages the worker has not had (a reply or a delivery fact says it had one), at most 20
    worker messages the Lead has not seen (LEAD_INBOX_FULL), and at most 200 messages per thread."""
    sent = [w.send(f"instruction {n}")["message"]["id"] for n in range(L.MAX_UNDELIVERED_LEAD)]
    with pytest.raises(CoordinationLimit) as exc:
        w.send("one too many")
    assert exc.value.details["bound"] == "undelivered_lead_messages" and len(exc.value.details["pending"]) == 16
    w.reply(sent[0], "had the first")  # a reply shows the worker had it: one slot frees
    assert w.send("now it fits")["ok"]
    for n in range(L.MAX_UNSEEN_WORKER - 1):
        w.reply(sent[1], f"progress {n}")
    with pytest.raises(LeadInboxFull) as exc:
        w.reply(sent[1], "flooding")
    assert exc.value.code == "LEAD_INBOX_FULL" and exc.value.details["bound"] == "unseen_worker_messages"
    assert isinstance(exc.value, CoordinationLimit)
    count = len(w.e.message_thread(w.inv)["messages"])
    monkeypatch.setattr(L, "MAX_THREAD_MESSAGES", count)
    with pytest.raises(CoordinationLimit) as exc:
        w.send("past the thread bound")
    assert exc.value.details == {"bound": "thread_messages", "limit": count}


def test_refs_are_bounded_resolved_and_scoped(w):
    """D-12: refs are ``kind:value``, at most 8 of at most 200 characters. AEW ids must exist (``source`` is checked
    for syntax only), and a worker cites only its own unit, thread, Ticket and runs. A ref grants nothing and is
    stored as written."""
    other = w.lead("work_create", kind="ticket", title="Other work", risk_class=1, mutating=True,
                   scope_paths=["calc/**"], goal_backwards=["other"], contract=["none"])["id"]
    policy = w.root / EXECUTION
    policy.write_text(policy.read_text(encoding="utf-8") + "# reviewed\n", encoding="utf-8", newline="\n")
    decision = w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="a reviewed comment",
                                  authorization=OPERATOR)["decision"]  # a project decision, about no unit
    lead = w.send(refs=[f"ticket:{w.wid}", "source:calc/core.py#L1-L2", "source:tests/test_core.py"])["message"]
    assert lead["refs"] == [f"ticket:{w.wid}", "source:calc/core.py#L1-L2", "source:tests/test_core.py"]
    ok = [f"ticket:{other}", f"message:{lead['id']}", f"decision:{decision}", "source:calc/core.py#L3"]
    assert w.send("lead refs", refs=ok)["message"]["refs"] == ok  # the Lead may cite any existing id
    with pytest.raises(CoordinationLimit) as exc:
        w.send(refs=["source:a.py"] * (L.MAX_REFS + 1))
    assert exc.value.details["bound"] == "refs"
    with pytest.raises(CoordinationLimit) as exc:
        w.send(refs=["source:" + "a" * L.MAX_REF_CHARS])
    assert exc.value.details["bound"] == "ref_chars"
    unknown = ["evidence:INV-0099-impl-1", "ticket:T-0099", f"ticket:{w.wid}@r2", "finding:F-1", f"run:R-{w.inv}-1",
               f"message:MSG-{w.inv}-99", "message:MSG-INV-9999-1", "decision:D-0099", "nonsense",
               "url:http://example.invalid", "source:/etc/passwd", "source:../outside.py", "source:C:/x.py",
               "source:a.py#L5-L2", "source:a\\b.py", "source:"]
    for ref in unknown:
        with pytest.raises(RefUnknown):
            w.send(refs=[ref])
    for ref in (f"ticket:{other}", "message:MSG-INV-9999-1", "run:R-INV-9999-1", f"decision:{decision}"):
        with pytest.raises(RefOutOfScope):
            w.reply(lead["id"], refs=[ref])
    with pytest.raises(RefUnknown):
        w.reply(lead["id"], refs=[f"run:R-{w.inv}-1"])  # its own invocation, but no such run
    mine = [f"ticket:{w.wid}", f"message:{lead['id']}", "source:calc/core.py"]
    assert w.reply(lead["id"], refs=mine)["message"]["refs"] == mine
    assert len(w.e.message_thread(w.inv)["messages"]) == 3


def _review(w: World, *, disposition: str, findings: list[dict[str, Any]], resolved: list[str]) -> str:
    """A reviewer of the Ticket submits a review; the Lead ingests it. Returns the review's evidence id."""
    token = w.lead("invoke_create", work_id=w.wid, role="reviewer")["invocation_token"]
    meta = {**CP.REVIEW, "review": {**CP.REVIEW["review"], "disposition": disposition, "findings": findings,
                                    "resolved_findings": resolved}}
    evidence = w.e.submit(invocation_token=token, kind="review", text=CP.submission(meta))["evidence"]
    w.lead("review_ingest", work_id=w.wid, evidence_id=evidence)
    return evidence


def test_finding_refs_resolve_qualified_or_unique_and_are_scoped(tmp_path):
    """D-12 (PR #160 review, m3): a unit stores a review's finding as `<evidence id>#<finding id>`.
    - The qualified ref `finding:<evidence id>#<finding id>` resolves to the unit that holds it: the Lead may cite any
      unit's finding, a worker only its own unit's (REF_OUT_OF_SCOPE otherwise).
    - The short ref `finding:<finding id>` resolves within the thread's own unit only, when exactly one finding has
      that id; when two reviews used it, it is refused as ambiguous, naming the qualified ids."""
    w = world(tmp_path, checks=True)
    other = w.lead("work_create", kind="ticket", title="Investigate calc.core", risk_class=1, mutating=False,
                   scope_paths=["calc/**"], goal_backwards=["current behaviour of calc.core is documented"],
                   contract=["read only"])["id"]
    w.lead("plan_propose", no_assurance=True, work_id=other, body="Read calc/core.py; record facts.\n")
    w.lead("plan_accept", work_id=other, revision=1)
    investigator = w.lead("work_dispatch", work_id=other)
    w.lead("work_transition", work_id=other, to="RUNNING")

    def implement(token: str, extra: str = "") -> None:
        for rel, text in CP.PATCH.items():
            (w.workspace / rel).write_text(text + extra, encoding="utf-8", newline="\n")
        w.e.check_run(invocation_token=token, check_id="unit")
        w.e.submit(invocation_token=token, kind="implementation_report", text=CP.submission(CP.REPORT))
        w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")

    implement(w.worker)
    first = _review(w, disposition="changes_required", resolved=[], findings=[
        {"id": "F-1", "severity": "major", "summary": "missing negative test", "required": True}])
    w.lead("work_transition", work_id=w.wid, to="RUNNING")
    implement(w.lead("invoke_create", work_id=w.wid, role="implementer")["invocation_token"], "\n# rework\n")
    second = _review(w, disposition="pass", resolved=[f"{first}#F-1"], findings=[
        {"id": "F-1", "severity": "minor", "summary": "name the case", "required": False},
        {"id": "G-2", "severity": "minor", "summary": "a docstring", "required": False}])
    w.lead("work_transition", work_id=w.wid, to="VERIFY_PENDING")
    verifier = w.lead("invoke_create", work_id=w.wid, role="verifier")
    to = verifier["invocation"]

    qualified = [f"finding:{first}#F-1", f"finding:{second}#F-1", f"finding:{second}#G-2", "finding:G-2"]
    lead = w.send("see these findings", to=to, refs=qualified)["message"]
    assert lead["refs"] == qualified  # both forms resolve on the unit's own thread
    with pytest.raises(RefUnknown) as exc:
        w.send("which one?", to=to, refs=["finding:F-1"])
    assert exc.value.details["reason"] == "ambiguous"
    assert exc.value.details["candidates"] == sorted([f"{first}#F-1", f"{second}#F-1"])
    assert "finding:<evidence id>#<finding id>" in exc.value.message
    for ref in ("finding:H-9", f"finding:{second}#H-9", "finding:INV-0099-review-1#F-1"):
        with pytest.raises(RefUnknown) as exc:
            w.send("no such finding", to=to, refs=[ref])
        assert exc.value.details["reason"] == "unknown"

    # The Lead cites the Ticket's finding to another unit's worker; that worker may not cite it back.
    cross = w.send("context from the Ticket's review", to=investigator["invocation"],
                   refs=[f"finding:{second}#G-2"])["message"]
    assert cross["refs"] == [f"finding:{second}#G-2"]
    with pytest.raises(RefUnknown):
        w.send("short form, other unit", to=investigator["invocation"], refs=["finding:G-2"])
    mine = [f"finding:{second}#G-2"]
    with pytest.raises(RefOutOfScope):
        w.reply(cross["id"], "noted", invocation_token=investigator["invocation_token"], refs=mine)
    assert w.reply(lead["id"], "checked", invocation_token=verifier["invocation_token"], refs=mine)["ok"]


def test_a_message_ref_never_satisfies_a_gate(w):
    """F9 invariant 3 (a statement is not Evidence): a worker's 'done, tests pass' with refs changes no gate, writes no
    evidence and moves no state; the Ticket still cannot advance without the evidence path."""
    gates = w.e.gate_show(w.wid)
    with pytest.raises(AEWError) as before:
        w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    lead = w.send("Report when the tests pass.")["message"]
    w.reply(lead["id"], "Done: all tests pass, ready for review.", kind="finding",
            refs=[f"ticket:{w.wid}", "source:tests/test_core.py"])
    assert w.e.gate_show(w.wid) == gates
    assert not any((w.root / ".aew/evidence").rglob("*.md"))
    with pytest.raises(AEWError) as after:
        w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    assert (after.value.code, after.value.message) == (before.value.code, before.value.message)


# ---------------------------------------------------------------------------------------------- authority


def test_a_superseded_generation_records_nothing(w, monkeypatch):
    """D-14, D-17: a Lead credential a takeover superseded is refused before anything is read or written."""
    import aew.operator

    w.send()
    before = w.thread_path().read_bytes()
    old = w.token
    # The operator's takeover, confirmed at their terminal (substituted in-process, as test_stage_runner does).
    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **_: {"authorized_by": "operator-tty (test)"})
    w.e.lead_takeover(expect_rev=w.rev(), reason="the seat was lost", session_label="lead-b")
    with pytest.raises(StaleAuthority):
        w.send("from the old Lead", token=old)
    assert w.thread_path().read_bytes() == before


def test_a_custody_invocation_is_not_a_recipient(tmp_path):
    """D-4 step 4, D-17: a message goes to an active, role-bearing worker. The integration lease's engine custody
    invocation runs no model and is refused (NOT_A_WORKER); an ended worker is refused too. Nothing is written."""
    w = world(tmp_path, checks=True)
    for rel, text in CP.PATCH.items():
        (w.workspace / rel).write_text(text, encoding="utf-8", newline="\n")
    w.e.check_run(invocation_token=w.worker, check_id="unit")
    w.e.submit(invocation_token=w.worker, kind="implementation_report", text=CP.submission(CP.REPORT))
    w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    reviewer = w.lead("invoke_create", work_id=w.wid, role="reviewer")["invocation_token"]
    review = w.e.submit(invocation_token=reviewer, kind="review", text=CP.submission(CP.REVIEW))["evidence"]
    w.lead("review_ingest", work_id=w.wid, evidence_id=review)
    w.lead("work_transition", work_id=w.wid, to="VERIFY_PENDING")
    verifier = w.lead("invoke_create", work_id=w.wid, role="verifier")["invocation_token"]
    checks = [w.e.check_run(invocation_token=verifier, check_id=c)["evidence"] for c in ("unit", "guardrails")]
    claims = [{"type": "goal_backwards", "claim": "subtract works", "result": "pass", "checks": checks[:1]},
              {"type": "contract", "claim": "scope respected", "result": "pass", "checks": checks[1:]}]
    verification = w.e.submit(invocation_token=verifier, kind="verification", text=CP.submission(
        {"claim": "behavior verified", "producer": {"model": "test"},
         "verification": {"scope": "ticket", "claims": claims}}))["evidence"]
    w.lead("verify_ingest", work_id=w.wid, evidence_id=verification)
    w.lead("work_transition", work_id=w.wid, to="COMMIT_READY")
    w.lead("integrate_prepare", work_id=w.wid)
    state = load_control(w.root)
    custodian = next(i for i, v in state["invocations"].items()
                     if v.get("kind") == "integration_attempt" and v["status"] == "active")
    with pytest.raises(NotAWorker) as exc:
        w.send(to=custodian)
    assert exc.value.details == {"invocation": custodian, "kind": "integration_attempt"}
    ended = next(i for i, v in state["invocations"].items() if v.get("role") and v["status"] != "active")
    with pytest.raises(IllegalTransition) as exc:
        w.send(to=ended)
    assert exc.value.details["reason"] == "recipient_not_active"
    assert w.coordination_files() == []


def test_a_v1_project_records_no_message(w):
    """G1: recording on a v1 project is refused (MIGRATION_REQUIRED), so `aew migrate` never meets a thread."""
    state = load_control(w.root)
    (w.root / ".aew/state/control.yaml").write_bytes(serialize_control(as_v1(state)))
    with pytest.raises(MigrationRequired):
        w.send()
    with pytest.raises(MigrationRequired):
        w.reply(f"MSG-{w.inv}-1")
    assert w.coordination_files() == []


# ---------------------------------------------------------------------------------------------- the switch


def test_the_switch_is_read_from_adopted_bytes_only(tmp_path):
    """D-15: only the operator's adoption turns messaging on. An unadopted edit reads as off, in either direction; a
    YAML boolean is refused at adoption with its cause; and nothing is written while it reads off."""
    w = world(tmp_path, messaging=None)
    set_messaging(w.root, "enabled")  # edited, not adopted
    with pytest.raises(MessagingDisabled) as exc:
        w.send()
    assert exc.value.details["reason"] == "not_adopted" and w.coordination_files() == []
    policy = w.root / EXECUTION
    edited = policy.read_bytes()
    policy.write_bytes(edited.replace(b"messaging: enabled", b"messaging: on"))
    with pytest.raises(ValidationFailed) as refused:
        w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="turn it on", authorization=OPERATOR)
    assert refused.value.details["reason"] == "yaml_boolean"
    policy.write_bytes(edited)
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="turn messaging on", authorization=OPERATOR)
    assert w.send()["ok"]
    set_messaging(w.root, "disabled")  # an unadopted edit never keeps it on either
    with pytest.raises(MessagingDisabled) as exc:
        w.send("after the edit")
    assert exc.value.details["reason"] == "not_adopted"
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="turn messaging off", authorization=OPERATOR)
    with pytest.raises(MessagingDisabled) as exc:
        w.send("after adopting off")
    assert exc.value.details["reason"] == "switched_off"
    assert len(w.e.message_thread(w.inv)["messages"]) == 1  # what was recorded stays readable


@pytest.mark.parametrize("setting", [None, "disabled"])
def test_with_messaging_off_the_engine_records_nothing(tmp_path, setting):
    """Off means absent (the operator's decision: OFF in M4-H, built behind a switch): with the key absent or
    `disabled`, a Lead message and a worker reply are refused and nothing is written: no thread, no marker, no
    `.aew/coordination/`, no change to control state or the wake signal."""
    w = world(tmp_path, messaging=setting)
    before = w.control_bytes()
    wake = (w.root / ".aew/local/wake").read_bytes() if (w.root / ".aew/local/wake").exists() else None
    with pytest.raises(MessagingDisabled) as exc:
        w.send()
    assert exc.value.code == "MESSAGING_DISABLED" and exc.value.details["reason"] == "switched_off"
    with pytest.raises(MessagingDisabled):
        w.reply(f"MSG-{w.inv}-1")
    assert w.e.message_thread(w.inv)["messages"] == []  # reading creates nothing either
    assert w.coordination_files() == []
    assert not (w.root / ".aew" / L.COORDINATION_DIR).exists() and not w.thread_path().parent.exists()
    assert w.control_bytes() == before
    assert ((w.root / ".aew/local/wake").read_bytes() if (w.root / ".aew/local/wake").exists() else None) == wake


# The policy files `aew init` writes, and their digests, captured at the base commit (677e4ac) before F9-A existed.
INIT_POLICY_SHA256 = {
    "policy/checks.yaml": "f06632f61b021fe69f372d08cb2385c96b3b6954454cea72fa31e37c57e7bbe2",
    "policy/execution.yaml": "2d36d67ee0185d77ebb1c9fc57c31c78d62edc3a578b6700e972138fa6c59fd3",
    "policy/gates.yaml": "b676e7da71583adf2815f95b9728f4e1230348daa72ed4bc95d9050ef9e791f3",
    "policy/guardrails.yaml": "7d48716add96baf7d0e509c0eca70701c2ea0332a839dd7435c1d773b1f8bcf0",
}
INIT_POLICY_DIGESTS = {
    "legality_digest": "sha256:e35bc2c2a63baada8a49a817af6632246baff9f325f5716adb6a4d6887b11bb6",
    "operational_digest": "sha256:656c7e5fe5947690a7b5287e9b0309b24bb451ed41c84dd39b2dd0473396d06c",
}


def test_with_messaging_off_init_policy_bytes_and_digests_match_the_goldens(tmp_path):
    """D-32 (F8): `aew init`, the shipped default execution policy and `aew migrate` never write `coordination`: the
    policy bytes and both digests of a new project are the ones from before F9-A, and a migration leaves the policy
    as it found it."""
    from aew.engine.base import policy_files
    from aew.knowledge.manifest import load_manifest
    from aew.policy import execution as X
    from aew.util import sha256_file

    root = make_git_repo(tmp_path / "fresh", CP.FILES)
    e = Engine.initialize(root, project_id="golden", name="golden", branch="main")
    aew = root / ".aew"
    assert {rel: sha256_file(aew / rel) for rel in policy_files(load_manifest(aew))} == INIT_POLICY_SHA256
    assert e.policy_digests() == INIT_POLICY_DIGESTS
    assert "coordination" not in X.TEMPLATE and "coordination" not in util.load_yaml(X.TEMPLATE)
    assert X.messaging(util.load_yaml(X.TEMPLATE)) == "disabled" and X.messaging(None) == "disabled"

    w = world(tmp_path / "migrated", messaging=None)
    policy = {p: p.read_bytes() for p in (w.root / ".aew/policy").glob("*.yaml")}
    (w.root / ".aew/state/control.yaml").write_bytes(serialize_control(as_v1(load_control(w.root))))
    w.e.migrate(token=w.token, expect_rev=w.rev())
    assert load_control(w.root)["schema"] == "aew/control/v2"
    assert {p: p.read_bytes() for p in (w.root / ".aew/policy").glob("*.yaml")} == policy
    assert not (w.root / ".aew" / L.COORDINATION_DIR).exists()


# ---------------------------------------------------------------------------------------------- static


LEGALITY_MODULES = (
    "aew/engine/authority.py", "aew/engine/dependencies.py", "aew/engine/dispatch.py", "aew/engine/freshness.py",
    "aew/engine/gates.py", "aew/engine/hierarchy.py", "aew/engine/transitions.py", "aew/engine/evidence_ops.py",
    "aew/engine/workspace_ops.py", "aew/engine/work_ops.py", "aew/engine/hierarchy_ops.py",
    "aew/engine/nonmutating_ops.py", "aew/engine/integration_ops.py", "aew/engine/queue_ops.py",
    "aew/engine/validation_ops.py", "aew/engine/assurance.py", "aew/engine/assurance_ops.py",
    "aew/engine/stage_intents.py", "aew/knowledge/evidence.py",
)


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out |= {node.module} | {f"{node.module}.{a.name}" for a in node.names}
    return out


def _is_coordination(module: str) -> bool:
    return module == "aew.coordination" or module.startswith("aew.coordination.") \
        or module.startswith("aew.engine.coordination_ops")


def test_legality_modules_never_import_coordination():
    """F9 invariant 1 (coordination is not authority), statically: no module that decides legality (gates, dispatch,
    transitions, authority, evidence, the policy package) imports coordination, and in the engine only the
    collaborator itself and the composition root do. A later slice that needs another importer names it here."""
    src = ROOT / "src"
    legality = [src / rel for rel in LEGALITY_MODULES] + sorted((src / "aew/policy").glob("*.py"))
    assert all(p.is_file() for p in legality)
    offenders = [p.relative_to(src).as_posix() for p in legality if any(map(_is_coordination, _imports(p)))]
    assert offenders == []
    importers = {p.relative_to(src).as_posix() for p in (src / "aew").rglob("*.py")
                 if any(map(_is_coordination, _imports(p))) and "aew/coordination/" not in p.as_posix()}
    # MS2: the store's seal check and archival's seal pins know only the leaf layout's paths and keys (plan D-16).
    assert importers == {"aew/engine/api.py", "aew/engine/coordination_ops.py", "aew/engine/store.py",
                         "aew/engine/archive_ops.py"}
    for leaf_only in ("aew/engine/store.py", "aew/engine/archive_ops.py"):
        assert {m for m in _imports(src / leaf_only) if _is_coordination(m)} == {"aew.coordination",
                                                                                 "aew.coordination.layout"}, leaf_only
