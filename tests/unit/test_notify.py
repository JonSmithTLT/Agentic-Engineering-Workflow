"""The operator notifier, the event spool and the watcher's derivations (M4-E E7a; plan v3 §2.7, §2.8 and E7, operator
decision 1; amendment 1, E7a's row and §2).

Delivery runs an argv with no shell, a sanitized environment, a bounded time (the whole process tree is killed) and a
bounded output (counted, never kept), and the child inherits no endpoint handle. A spool line is untrusted: capped,
validated against its writer's closed enum, rate-bounded and labelled unauthenticated. Each event is delivered once per
occurrence, and the watcher commits nothing. The legality modules never import the notifier."""

from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from legality_modules import LEGALITY_MODULES, legality_modules
from notifier import adopt, dead_pid, raise_to, received, recorder, request, script, seed, takeover, until

from aew import errors, schemas
from aew.engine.api import Engine
from aew.harness import broker_liveness, event_spool, notify, procs, runlog

SRC = Path(__file__).resolve().parents[2] / "src" / "aew"

def event(**over: Any) -> dict[str, Any]:
    return notify.payload(**{"event": "hard_deadline", "project_id": "p", "subject": "R-INV-0001-1",
                             "reason": "deadline", "ref": None, "revision": 1, "source": "spool:run-R-INV-0001-1",
                             "authenticated": False, **over})


# ---------------------------------------------------------------------------------------------- delivery


def test_notifier_timeout_kills_the_process_tree(tmp_path):
    """Past `timeout_s` the notifier and everything it started are killed, and the delivery is a failure."""
    pids = tmp_path / "pids"
    body = f"""\
import os, subprocess, sys, time
kw = {{"creationflags": 0x08000000}} if sys.platform == "win32" else {{}}
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], **kw)
open({str(pids)!r}, "w").write(f"{{os.getpid()}} {{child.pid}}")
time.sleep(120)
"""
    started = time.monotonic()
    out = notify.deliver([sys.executable, "-I", script(tmp_path, "hang", body)], event(), timeout_s=1.5,
                         max_output_bytes=1024)
    assert out["outcome"] == "failed" and out["reason"] == "timeout" and out["timed_out"]
    assert time.monotonic() - started < 30
    parent, child = (int(p) for p in until(lambda: pids.exists() and pids.read_text().split(), what="the pids"))
    until(lambda: not procs.pid_alive(parent) and not procs.pid_alive(child), 15, "the notifier's tree to be killed")


def test_notifier_output_is_bounded_and_counted(tmp_path):
    """Output past `max_output_bytes` is discarded and counted; no output is kept in the log, only the counts."""
    body = "import sys\nsys.stdin.read()\nsys.stdout.write('x' * 100000)\nsys.stdout.flush()\n"
    out = notify.deliver([sys.executable, "-I", script(tmp_path, "loud", body)], event(), timeout_s=10,
                         max_output_bytes=1000)
    assert out["outcome"] == "delivered" and out["exit_code"] == 0
    assert out["output_bytes"] == 1000 and out["discarded_bytes"] == 99000
    assert not [k for k in out if "output" in k and k != "output_bytes"]


def test_notifier_environment_is_sanitized(tmp_path, monkeypatch):
    """The notifier gets the curated keep-list only: no AEW_* variable, no provider key, no credential value."""
    monkeypatch.setenv("AEW_LEAD_TOKEN", "aew1.tk_0123456789abcdef.abcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("AEW_ANYTHING", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-synthetic-test-key")
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "synthetic")
    monkeypatch.setenv("UNRELATED_SHELL_VAR", "kept-out")
    monkeypatch.setenv("TZ", "aew1.tk_0123456789abcdef.abcdefghijklmnopqrstuvwxyz")  # a kept name, a credential value
    dump = tmp_path / "env.json"
    body = f"import json, os, sys\nsys.stdin.read()\njson.dump(dict(os.environ), open({str(dump)!r}, 'w'))\n"
    out = notify.deliver([sys.executable, "-I", script(tmp_path, "env", body)], event(), timeout_s=10,
                         max_output_bytes=1024)
    assert out["outcome"] == "delivered", out
    env = json.loads(dump.read_text())
    names = {k.upper() for k in env}
    assert "PATH" in names
    assert not [k for k in names if k.startswith("AEW_")], names
    assert not names & {"OPENAI_API_KEY", "SOME_SERVICE_TOKEN", "UNRELATED_SHELL_VAR", "TZ"}, names
    assert not [v for v in env.values() if "aew1.tk_" in v]


def test_a_notifier_that_cannot_start_or_fails_is_a_delivery_failure(tmp_path):
    missing = notify.deliver([str(tmp_path / "no-such-notifier")], event(), timeout_s=5, max_output_bytes=10)
    assert missing["outcome"] == "failed" and missing["reason"] == "spawn_failed"
    failing = notify.deliver([sys.executable, "-I", "-c", "import sys; sys.exit(3)"], event(), timeout_s=10,
                             max_output_bytes=10)
    assert failing["outcome"] == "failed" and failing["reason"] == "exit_code" and failing["exit_code"] == 3


def test_every_notification_is_a_valid_closed_payload():
    """`aew/notify-event/v1`: plan v3's fields plus source, authenticated and an optional reason_code; strings capped
    and cleaned; an event outside §2.8's table is refused."""
    e = event(reason="a\x1b[31m" + "r" * 1000, subject="R-INV-0001-1‮")
    assert set(e) == {"schema", "event", "project_id", "subject", "reason", "ref", "revision", "at", "source",
                      "authenticated"}
    assert len(e["reason"]) == 512 and "\x1b" not in e["reason"] and "‮" not in e["subject"]
    with pytest.raises(errors.ValidationFailed):
        event(event="anything_else")
    with pytest.raises(errors.ValidationFailed):
        event(source="spool:../escape")
    assert event(reason_code="spawn_race")["reason_code"] == "spawn_race"


# ---------------------------------------------------------------------------------------------- the spool


def _spool_lines(aew_root: Path, writer: str, lines: list[str | bytes]) -> None:
    path = event_spool.file_of(aew_root, writer)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:
        for line in lines:
            fh.write((line.encode("utf-8") if isinstance(line, str) else line) + b"\n")


def _line(run: str, **over: Any) -> str:
    return json.dumps({"schema": event_spool.SCHEMA, "event": "hard_deadline", "at": "2026-10-10T00:00:00Z",
                       "subject": run, "reason": "deadline", "ref": None, **over})


def test_spool_lines_are_capped_validated_rate_bounded_and_unauthenticated(project, tmp_path):
    """Amendment 1, m9: an oversize line is dropped and counted; a line outside its writer's closed enum, about another
    run, or from a writer with no events yet is invalid; strings are capped and cleaned; at most ten deliveries per
    writer per minute; every spool notification says `authenticated: false`."""
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    root = project.root / ".aew"
    run = "R-INV-0007-1"
    writer = event_spool.run_writer(run)
    runlog.run_dir(root, run).mkdir(parents=True)  # a supervisor writes only for a run its launcher made
    _spool_lines(root, writer, [
        _line(run, reason="first"),
        "x" * (event_spool.MAX_LINE + 900),  # oversize: dropped once, its rest never parsed
        "{not json",
        _line(run, event="generation_ended"),  # not a run writer's event
        _line("R-INV-0008-1", reason="about another run"),
        _line(run, reason="\x1b]0;evil\x07" + "y" * 2000),
        *[_line(run, reason=f"flood {n}") for n in range(15)],
    ])
    _spool_lines(root, event_spool.BROKER, [_line(run)])  # the broker has no spool events before M4-E E7b
    watcher = notify.Watcher(project.root, root)
    watcher.start()
    try:
        until(lambda: len(received(out)) >= notify.RATE_PER_MINUTE, what="ten deliveries")
        watcher.pass_once()
        assert watcher.drain()
    finally:
        watcher.close()
    got = received(out)
    assert len(got) == notify.RATE_PER_MINUTE  # 17 valid lines; the rest of this minute's are dropped
    assert {e["source"] for e in got} == {f"spool:{writer}"} and not [e for e in got if e["authenticated"]]
    assert all(e["subject"] == run for e in got)
    capped = next(e for e in got if "yyy" in (e["reason"] or ""))
    assert len(capped["reason"]) <= event_spool.MAX_STRING and "\x1b" not in capped["reason"]
    summary = notify.summary(root)
    assert summary is not None
    assert summary["dropped"] == {"oversize": 1, "invalid": 4, "rate": 7}, summary["dropped"]
    log = notify.deliveries(root)
    assert sorted(x["outcome"] for x in log) == ["delivered"] * 10 + ["dropped"] * 7


def test_a_spool_pass_is_bounded_in_lines_and_files(tmp_path):
    """At most 256 new lines per file and 64 files per pass, oldest first; what is left is read by the next pass,
    and a line still being written waits for its newline."""
    root = tmp_path / ".aew"
    big = event_spool.run_writer("R-INV-0001-1")
    _spool_lines(root, big, [_line("R-INV-0001-1", reason=f"n{n}") for n in range(300)])
    reader = event_spool.Reader(root, {})
    first = reader.scan()
    assert len(first.lines) == event_spool.LINES_PER_PASS and first.more
    second = reader.scan()
    assert len(second.lines) == 300 - event_spool.LINES_PER_PASS and not second.more
    path = event_spool.file_of(root, big)
    with path.open("ab") as fh:
        fh.write(_line("R-INV-0001-1", reason="partial").encode("utf-8"))  # no newline yet
    assert reader.scan().lines == []
    with path.open("ab") as fh:
        fh.write(b"\n")
    assert [x.reason for x in reader.scan().lines] == ["partial"]
    for n in range(70):
        _spool_lines(root, event_spool.run_writer(f"R-INV-{n:04d}-9"), [_line(f"R-INV-{n:04d}-9")])
    many = event_spool.Reader(root, reader.cursors).scan()
    assert len({x.writer for x in many.lines}) == event_spool.FILES_PER_PASS and many.more


def test_a_rotated_spool_file_is_read_to_its_end_before_the_new_one(tmp_path, monkeypatch):
    root = tmp_path / ".aew"
    writer = event_spool.run_writer("R-INV-0001-1")
    monkeypatch.setattr(event_spool, "MAX_BYTES", 600)
    reader = event_spool.Reader(root, {})
    event_spool.append(root, writer, "hard_deadline", subject="R-INV-0001-1", reason="one")
    assert [x.reason for x in reader.scan().lines] == ["one"]
    for n in range(2, 6):
        event_spool.append(root, writer, "hard_deadline", subject="R-INV-0001-1", reason=f"n{n}")
    assert event_spool.file_of(root, writer, rotated=True).exists()
    assert [x.reason for x in reader.scan().lines] == ["n2", "n3", "n4", "n5"]


def test_a_spool_append_never_fails_its_writer(tmp_path):
    root = tmp_path / ".aew"
    event_spool.spool_dir(root).mkdir(parents=True)
    event_spool.file_of(root, "run-R-INV-0001-1").mkdir()  # not a regular file
    event_spool.append(root, "run-R-INV-0001-1", "launch_failed", subject="R-INV-0001-1", reason="x")
    event_spool.append(root, "../outside", "launch_failed", subject="x", reason="x")
    assert not (tmp_path / "outside.jsonl").exists()


# ---------------------------------------------------------------------------------------------- once per occurrence


def _crashed_broker(project) -> None:
    raise_to(Engine.discover(project.root), "run")
    generation = Engine.discover(project.root).store.read()["lead"]["generation"]
    broker_liveness.write(project.root / ".aew", {
        "schema": broker_liveness.SCHEMA, "pid": dead_pid(), "process_started": time.time() - 5,
        "generation": generation, "beat_at": time.time(), "watchdog_tick_at": time.time(), "wedge_after_s": 62.0})


def spooled(project, event: str, reason: str, run: str = "R-INV-0001-1") -> None:
    """A supervisor's append, for a run whose directory its launcher made."""
    root = project.root / ".aew"
    runlog.run_dir(root, run).mkdir(parents=True, exist_ok=True)
    event_spool.append(root, event_spool.run_writer(run), event, subject=run, reason=reason)


def _breaker(state: dict[str, Any]) -> None:
    state["queue"] = {"next_seq": 1, "lease": None, "entries": {}, "validation_breaker": {
        "failures": [], "open": {"at": "2026-10-10T00:00:00Z", "codes": ["SANDBOX_UNAVAILABLE"], "runs": ["V-1"]}}}


def _reconcile(state: dict[str, Any]) -> None:
    state["queue"] = {"next_seq": 2, "entries": {}, "lease": {
        "entry": "Q-0001", "custodian": "INV-0009", "generation": 1, "granted_at": "2026-10-10T00:00:00Z",
        "reconcile": {"reason": "custodian INV-0009 is cancelled", "at": "2026-10-10T00:00:01Z"}}}


SEEDS = {
    "generation_ended": lambda project, mp: takeover(project, mp),
    "broker_gone": lambda project, mp: _crashed_broker(project),
    "raise_requested": lambda project, mp: request(project, "raise"),
    "confirmation_requested": lambda project, mp: request(project, "confirmation"),
    "breaker_tripped[validation]": lambda project, mp: seed(project, _breaker),
    "custodian_lost[reconcile]": lambda project, mp: seed(project, _reconcile),
    "hard_deadline": lambda project, mp: spooled(project, "hard_deadline", "deadline"),
    "launch_failed": lambda project, mp: spooled(project, "launch_failed", "custody refused"),
}


@pytest.mark.parametrize("case", list(SEEDS))
def test_event_delivered_once_per_occurrence(project, tmp_path, monkeypatch, case):
    """§2.8: each event is delivered once per occurrence, keyed in the delivery log: across passes, and across a
    restarted endpoint (a new watcher reads the log)."""
    name = case.split("[")[0]
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    root = project.root / ".aew"
    watcher = notify.Watcher(project.root, root)
    watcher.pass_once()  # the watcher's cursor starts here
    watcher.start()
    try:
        SEEDS[case](project, monkeypatch)
        until(lambda: [e for e in received(out) if e["event"] == name], what=f"{name} to be delivered")
        for _ in range(3):
            watcher.pass_once()
        assert watcher.drain()
    finally:
        watcher.close()
    again = notify.Watcher(project.root, root)
    again.start()
    try:
        again.pass_once()
        assert again.drain()
    finally:
        again.close()
    got = [e for e in received(out) if e["event"] == name]
    assert len(got) == 1, got
    keys = [x["key"] for x in notify.deliveries(root) if x["event"] == name]
    assert len(keys) == len(set(keys)) == 1
    assert got[0]["authenticated"] is (got[0]["source"] == "control_state")
    schemas.validate("notify-event", got[0], source="test")


def test_the_watcher_moves_no_revision(project, tmp_path, monkeypatch):
    """The watcher reads control state lock-free, derives and delivers, and commits nothing (amendment 1, m9): the
    revision stands through its passes and deliveries, and its modules call no commit path."""
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    request(project, "raise")
    seed(project, _breaker)
    spooled(project, "launch_failed", "x")
    before = project.rev()
    control = (project.root / ".aew/state/control.yaml").read_bytes()
    watcher = notify.Watcher(project.root, project.root / ".aew")
    watcher.start()
    try:
        until(lambda: len(received(out)) >= 3, what="the deliveries")
        for _ in range(3):
            watcher.pass_once()
        assert watcher.drain()
    finally:
        watcher.close()
    assert project.rev() == before
    assert (project.root / ".aew/state/control.yaml").read_bytes() == control
    for module in ("harness/notify.py", "harness/event_spool.py", "harness/broker_liveness.py"):
        tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
        calls = {getattr(n.func, "attr", getattr(n.func, "id", None))
                 for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not calls & {"session", "commit", "lead_txn"}, (module, calls)
        attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not attributes & {"_authorizing", "_engine_lock"}, module  # never the endpoint's locks


# ---------------------------------------------------------------------------------------------- the boundary


def test_legality_modules_never_import_notify():
    """CWR §11's static boundary, for the notifier (amendment 1, nit 6): no legality, gate, transition, dispatch,
    plan-assurance, lint, evidence-acceptance or publication module, nor the policy package, imports `harness.notify`
    (or the spool or the liveness record it reads), at module level or inside a function. The set is the F9 boundary
    test's, with the guards and the surface's availability and classification (`tests/helpers/legality_modules.py`)."""
    banned = {"aew.harness.notify", "aew.harness.event_spool", "aew.harness.broker_liveness"}
    found = []
    modules = legality_modules()
    assert len(modules) > len(LEGALITY_MODULES) and all(p.is_file() for p in modules)  # the policy package too
    for path in modules:
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found += [(rel, a.name) for a in node.names if a.name in banned]
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module in banned:
                    found.append((rel, node.module))
                elif node.module == "aew.harness":
                    found += [(rel, a.name) for a in node.names if f"aew.harness.{a.name}" in banned]
    assert found == []


# ---------------------------------------------------------------------------------------------- review of PR #184


def _liveness(**over: Any) -> dict[str, Any]:
    now = time.time()
    return {"schema": broker_liveness.SCHEMA, "pid": 4242, "process_started": None, "generation": 1, "beat_at": now,
            "watchdog_tick_at": now, "wedge_after_s": 62.0, **over}


@pytest.mark.parametrize("field,value", [("pid", "2" + "0" * 21), ("pid", "0"), ("generation", "2" + "0" * 21),
                                         ("beat_at", "NaN"), ("watchdog_tick_at", "-Infinity"),
                                         ("wedge_after_s", "NaN"), ("wedge_after_s", "Infinity"),
                                         ("closed_at", "1e300")])
def test_an_out_of_range_or_non_finite_liveness_record_is_rejected(tmp_path, field, value):
    """A pid no OS can name, or a non-finite or absurd number, is no record the broker wrote: rejected by `read()`,
    so it can neither fail the watcher nor slip past the staleness and wedge checks (NaN compares false)."""
    root = tmp_path / ".aew"
    body = ", ".join(f'"{k}": {value if k == field else json.dumps(v)}' for k, v in _liveness().items())
    if field not in _liveness():
        body += f', "{field}": {value}'
    broker_liveness.path(root).parent.mkdir(parents=True)
    broker_liveness.path(root).write_text("{" + body + "}", encoding="utf-8")
    assert broker_liveness.read(root) is None, body
    broker_liveness.write(root, _liveness())
    assert broker_liveness.read(root) is not None  # the same record, well formed, is read


def test_a_process_check_that_cannot_answer_is_unprovable_never_an_error(monkeypatch):
    from aew.harness import operator_client

    def overflow(record: dict[str, Any]) -> bool:
        raise OverflowError("signed integer is greater than maximum")  # Linux's os.kill for a pid past pid_t

    monkeypatch.setattr(operator_client, "same_process", overflow)
    now = time.time()
    assert broker_liveness.judge(_liveness(), generation=1, poll_s=1.0, now=now) is None
    stale = broker_liveness.judge(_liveness(watchdog_tick_at=now - 100), generation=1, poll_s=1.0, now=now)
    assert stale is not None and stale.reason == "stale"


def test_a_failing_source_never_stops_the_others_and_shows_in_status(project, tmp_path, monkeypatch):
    """Each source is isolated: the liveness record failing (here as Linux's `os.kill` fails for a pid past
    `pid_t`) never stops control-state or spool notifications, and the failing source is shown in `status`."""
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    root = project.root / ".aew"

    def failing(aew_root: Path) -> dict[str, Any]:
        raise OverflowError("signed integer is greater than maximum")

    monkeypatch.setattr(broker_liveness, "read", failing)
    watcher = notify.Watcher(project.root, root)
    watcher.pass_once()
    request(project, "raise")
    takeover(project, monkeypatch)
    spooled(project, "launch_failed", "x")
    watcher.start()
    try:
        until(lambda: {e["event"] for e in received(out)} >= {"generation_ended", "launch_failed"},
              what="the other sources' events")
        watcher.pass_once()
        assert watcher.drain()
    finally:
        watcher.close()
    summary = notify.summary(root)
    assert summary is not None and summary["attention"] and summary["pass_error"]["sources"] == ["liveness"]
    assert "OverflowError" in summary["pass_error"]["error"] and summary["dropped"]["liveness_failed"] >= 1
    engine = Engine.discover(project.root)
    assert "the notifier's watcher cannot read liveness" in engine.render_status(engine.status())


def events_of(out: Path, name: str) -> list[dict[str, Any]]:
    return [e for e in received(out) if e["event"] == name]


def test_spool_floods_never_displace_control_state_events(project, tmp_path, monkeypatch):
    """Control-state events have their own lane, served first, and are never recorded dropped: seventy runs' spool
    lines (a burst of failed launches, or a forger) are bounded across writers, and a takeover found meanwhile is
    still delivered, first."""
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    root = project.root / ".aew"
    watcher = notify.Watcher(project.root, root)
    watcher.pass_once()
    for n in range(70):
        spooled(project, "launch_failed", "x", run=f"R-INV-{n:04d}-1")
    watcher.pass_once()  # the delivery thread is not running yet: the spool lane fills
    takeover(project, monkeypatch)
    watcher.pass_once()
    assert not [x for x in notify.deliveries(root) if x["event"] == "generation_ended"]  # never a non-final record
    watcher.start()
    try:
        until(lambda: events_of(out, "generation_ended"), 60, "generation_ended")
        assert watcher.drain(120)
    finally:
        watcher.close()
    got = received(out)
    assert got[0]["event"] == "generation_ended"  # served before every queued spool event
    assert len(events_of(out, "launch_failed")) == notify.SPOOL_PER_MINUTE
    assert notify.summary(root)["dropped"]["spool_rate"] == 70 - notify.SPOOL_PER_MINUTE


def test_spool_lines_for_a_run_that_does_not_exist_are_dropped(project, tmp_path):
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    root = project.root / ".aew"
    event_spool.append(root, "run-R-INV-0042-1", "launch_failed", subject="R-INV-0042-1", reason="invented")
    watcher = notify.Watcher(project.root, root)
    watcher.start()
    try:
        watcher.pass_once()
        watcher.pass_once()
        assert watcher.drain()
    finally:
        watcher.close()
    assert received(out) == [] and notify.summary(root)["dropped"]["unknown_run"] == 1
    assert not event_spool.file_of(root, "run-R-INV-0042-1").exists()  # read, counted, retired


def test_queued_events_survive_an_endpoint_restart(project, tmp_path, monkeypatch):
    """An event leaves the outstanding set only once the log records it: events queued when the endpoint stops are
    delivered by the next one (the transition cursor saved never passes them; spool events are saved), once."""
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    root = project.root / ".aew"
    watcher = notify.Watcher(project.root, root)
    watcher.pass_once()
    takeover(project, monkeypatch)
    spooled(project, "hard_deadline", "deadline")
    watcher.pass_once()  # both queued; the delivery thread never ran
    watcher.close()
    assert received(out) == [] and notify.deliveries(root) == []
    again = notify.Watcher(project.root, root)
    again.start()
    try:
        until(lambda: len(received(out)) >= 2, what="both events after the restart")
        for _ in range(2):
            again.pass_once()
        assert again.drain()
    finally:
        again.close()
    assert sorted(e["event"] for e in received(out)) == ["generation_ended", "hard_deadline"]
    [spool] = events_of(out, "hard_deadline")
    assert not spool["authenticated"] and spool["source"] == "spool:run-R-INV-0001-1"


def test_a_delivery_killed_by_close_is_not_a_failure(project, tmp_path):
    """Stopping the endpoint kills a delivery in flight: that is not a failed delivery (no count, no attention), and
    the event stays outstanding for the next endpoint."""
    started = tmp_path / "started"
    slow = script(tmp_path, "slow", f"import sys, time\nsys.stdin.read()\nopen({str(started)!r}, 'w').close()\n"
                                    "time.sleep(60)\n")
    adopt(project, command=[sys.executable, "-I", slow], timeout_s=30)
    root = project.root / ".aew"
    watcher = notify.Watcher(project.root, root)
    watcher.pass_once()
    request(project, "raise")
    watcher.start()
    try:
        until(started.exists, what="the slow notifier to start")
    finally:
        watcher.close()
    summary = notify.summary(root)
    assert summary is not None and summary["failed"] == 0 and not summary["attention"]
    assert notify.deliveries(root) == []  # not recorded: still outstanding
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    again = notify.Watcher(project.root, root)
    again.start()
    try:
        until(lambda: events_of(out, "raise_requested"), what="the event after the restart")
        assert again.drain()
    finally:
        again.close()
    assert len(events_of(out, "raise_requested")) == 1


def test_a_spool_line_is_bounded_by_its_encoded_bytes(tmp_path):
    """A reason of characters JSON escapes (twelve bytes each outside the BMP) is shortened until the line fits, so
    the reader never drops a line a supervisor wrote."""
    root = tmp_path / ".aew"
    event_spool.append(root, "run-R-INV-0001-1", "launch_failed", subject="R-INV-0001-1", reason="\U0001F600" * 400)
    size = event_spool.file_of(root, "run-R-INV-0001-1").stat().st_size
    found = event_spool.Reader(root, {}).scan()
    assert size <= event_spool.MAX_LINE + 1 and not found.dropped
    [line] = found.lines
    assert line.reason and set(line.reason) == {"\U0001F600"}


def test_a_run_file_is_retired_only_after_its_last_line_is_read(project, monkeypatch):
    """The run's status is read before its file is checked for unread lines: a supervisor appends its last line
    before its terminal record, so a line appended between the two checks is never deleted unread."""
    from aew.harness import contract as K

    root = project.root / ".aew"
    run = "R-INV-0001-1"
    writer = event_spool.run_writer(run)
    runlog.run_dir(root, run).mkdir(parents=True)
    event_spool.append(root, writer, "launch_failed", subject=run, reason="first")
    watcher = notify.Watcher(project.root, root)
    assert len(event_spool.Reader(root, watcher.cursors).scan().lines) == 1

    def observed_status(directory: Path) -> tuple[str, None]:  # the supervisor's last append, then its record
        event_spool.append(root, writer, "hard_deadline", subject=run, reason="deadline")
        return K.TERMINATED, None

    monkeypatch.setattr(runlog, "observed_status", observed_status)
    watcher._retire_spool()
    assert event_spool.file_of(root, writer).exists()
    assert [x.event for x in event_spool.Reader(root, watcher.cursors).scan().lines] == ["hard_deadline"]


def _handoff(project, monkeypatch) -> None:
    engine = Engine.discover(project.root)
    offer = engine.lead_handoff_offer(token=project.token, expect_rev=project.rev())["offer"]
    project.token = engine.lead_handoff_accept(offer=offer, expect_rev=project.rev())["token"]


def _release(project, monkeypatch) -> None:
    Engine.discover(project.root).lead_release(token=project.token, expect_rev=project.rev())


@pytest.mark.parametrize("reason,end", [("takeover", takeover), ("handoff", _handoff), ("release", _release)])
def test_generation_ended_names_each_control_state_reason(project, tmp_path, monkeypatch, reason, end):
    """A takeover, an accepted handoff and a release each end the generation, named with its reason, from the
    transition log: a release keeps the generation number, so it names the releasing Lead's."""
    command, out = recorder(tmp_path)
    adopt(project, command=command)
    root = project.root / ".aew"
    generation = Engine.discover(project.root).store.read()["lead"]["generation"]
    watcher = notify.Watcher(project.root, root)
    watcher.pass_once()
    end(project, monkeypatch)
    watcher.start()
    try:
        watcher.pass_once()
        assert watcher.drain()
    finally:
        watcher.close()
    [ended] = events_of(out, "generation_ended")
    assert (ended["reason"], ended["subject"], ended["source"]) == (reason, f"lead generation {generation}",
                                                                   "control_state")
