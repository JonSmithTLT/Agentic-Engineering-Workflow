"""OpenCode messaging behaviour probes, directly against a private server, never adapter.deliver.

The model and foreground shell have explicit release boundaries. Observations are reduced to semantic facts;
raw requests, messages and paths stay in the private run. API enum presence is not behaviour evidence.
"""

from __future__ import annotations

import json
import math
import os
import shlex
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from aew.harness.opencode.client import EventStream, location

from . import model, opencode
from .core import FAIL, PASS, Check, Context, Outcome


def until(predicate: Callable[[], Any], what: str, seconds: float = 30) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise TimeoutError(f"messaging probe did not observe {what}")


def session(server: Any, directory: str) -> str:
    until(lambda: any(m.get("id") == opencode.MODEL for m in
                     ((server.client.get("/api/model", location(directory)) or {}).get("data") or [])),
          "the scripted model catalog")
    made = server.client.post("/api/session", {
        "title": "messaging qualification", "agent": opencode.AGENT,
        "model": {"providerID": "openai", "id": opencode.MODEL},
        "location": {"directory": directory}, "permissions": opencode._ALL_ALLOWED})
    return (made.get("data") or made)["id"]


def main_requests(llm: Any) -> list[dict[str, Any]]:
    return [r for r in llm.requests if r.get("main")]


def http(server: Any, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    """Keep the actual HTTP code: a POST's 200 is not an admission observation."""
    connection = server.client.connection(timeout=30)
    try:
        connection.request(method, path, body=json.dumps(body) if body is not None else None,
                           headers=server.client.headers())
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if raw else None
    finally:
        connection.close()


def data(value: Any) -> Any:
    return value.get("data", value) if isinstance(value, dict) else value


def inbox_identity(value: Any) -> Any:
    """Canonicalize only absent versus empty optional attachment arrays. No identity, time, mode, text or metadata
    is dropped. Both raw responses are retained in the measurement for investigation of any failed comparison."""
    if not isinstance(value, dict) or not isinstance(value.get("payload"), dict):
        return value
    payload = {k: v for k, v in value["payload"].items() if k not in ("agents", "files", "skills") or v != []}
    return {**value, "payload": payload}


def expected_reply(value: Any, sid: str, mid: str, text: str, metadata: dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    payload = value.get("payload") or {}
    return (value.get("id") == mid and value.get("sessionID") == sid and value.get("type") == "user"
            and payload.get("text") == text and payload.get("metadata") == metadata)


def expected_inbox(value: Any, sid: str, mid: str, mode: str, text: str, metadata: dict[str, Any]) -> bool:
    """The first, pre-admission response still has the original mode and a valid enqueue timestamp."""
    if not expected_reply(value, sid, mid, text, metadata):
        return False
    created = (value.get("time") or {}).get("created")
    return (value.get("delivery") == mode and isinstance(created, (int, float)) and not isinstance(created, bool)
            and math.isfinite(created) and created >= 0)


def identity_measurement(ctx: Context) -> dict[str, Any]:
    """Observe idempotency before and after admission for both modes, including a changed payload/mode and an ID
    owned by another session. Held duplicate retries always explicitly use resume:false."""
    work = ctx.work / "identity"
    llm = model.start("responses", [])
    facts: dict[str, Any] = {}
    details: dict[str, Any] = {}
    try:
        with opencode.serve(ctx.binary, work, ctx.env, opencode.server_config(llm.base_url),
                            {"OPENAI_API_KEY": opencode.SYNTHETIC_KEY}) as server:
            directory = str((work / "project").resolve())
            for mode in ("steer", "queue"):
                sid = session(server, directory)
                path = f"/api/session/{sid}/prompt"
                mid = "msg_hq_identity_" + mode
                payload = {"id": mid, "text": "HQ_IDENTITY_" + mode, "delivery": mode, "resume": False,
                           "metadata": {"aew_probe": "identity", "ordinal": 1}}
                before = len(main_requests(llm))
                status, first = http(server, "POST", path, payload)
                first = data(first)
                facts[mode + ".first_identity_valid"] = expected_inbox(
                    first, sid, mid, mode, payload["text"], payload["metadata"])
                retry_status, retry = http(server, "POST", path, payload)
                changed_status, changed = http(server, "POST", path, {
                    **payload, "text": "HQ_WRONG_TEXT", "delivery": "queue" if mode == "steer" else "steer"})
                # Give an incorrectly resumed retry a chance to reach the model; then inspect both REST and requests.
                time.sleep(0.3)
                code, _ = http(server, "GET", f"/api/session/{sid}/message/{mid}")
                facts[mode + ".accepted_not_admitted"] = status == 200 and code == 404
                facts[mode + ".duplicate_pending"] = retry_status == 200 and inbox_identity(
                    data(retry)) == inbox_identity(first)
                facts[mode + ".changed_pending_returns_original"] = changed_status == 200 and inbox_identity(
                    data(changed)) == inbox_identity(first)
                facts[mode + ".held_retry_does_not_wake"] = len(main_requests(llm)) == before and sid not in (
                    (server.client.get("/api/session/active") or {}).get("data") or {})
                server.client.post(path, {"id": "msg_hq_wake_" + mode, "text": "HQ_WAKE", "delivery": mode})
                until(lambda sid=sid, mid=mid: http(server, "GET", f"/api/session/{sid}/message/{mid}")[0] == 200,
                      "held-message admission")
                until(lambda sid=sid: sid not in ((server.client.get("/api/session/active") or {}).get("data") or {}),
                      "the identity turn end")
                admitted = data(http(server, "GET", f"/api/session/{sid}/message/{mid}")[1])
                facts[mode + ".metadata_round_trip"] = isinstance(admitted, dict) and admitted.get(
                    "metadata") == payload["metadata"]
                before_retry = len(main_requests(llm))
                status, retried = http(server, "POST", path, payload)
                changed_status, changed = http(server, "POST", path, {
                    **payload, "text": "HQ_WRONG_TEXT", "delivery": "queue" if mode == "steer" else "steer"})
                facts[mode + ".duplicate_admitted"] = status == 200 and inbox_identity(data(retried)) == inbox_identity(
                    first)
                facts[mode + ".changed_admitted_returns_original"] = changed_status == 200 and inbox_identity(
                    data(changed)) == inbox_identity(first)
                after = data(retried)
                facts[mode + ".admitted_identity_valid"] = expected_reply(
                    after, sid, mid, payload["text"], payload["metadata"])
                facts[mode + ".admitted_created_time_preserved"] = isinstance(after, dict) and isinstance(
                    first, dict) and after.get("time") == first.get("time")
                facts[mode + ".admitted_delivery_preserved"] = isinstance(after, dict) and isinstance(
                    first, dict) and after.get("delivery") == first.get("delivery")
                details[mode] = {"first": first, "admitted_retry_status": status, "admitted_retry": after,
                                 "admitted_changed_status": changed_status, "admitted_changed": data(changed)}
                time.sleep(0.3)
                facts[mode + ".admitted_retry_does_not_wake"] = len(main_requests(llm)) == before_retry and sid not in (
                    (server.client.get("/api/session/active") or {}).get("data") or {})
                users = [m for m in opencode._messages(server, sid) if m.get("type") == "user"]
                facts[mode + ".admitted_once"] = sum(m.get("id") == mid for m in users) == 1
                facts[mode + ".staged_first"] = [m.get("id") for m in users][:2] == [mid, "msg_hq_wake_" + mode]
                other = session(server, directory)
                code, body = http(server, "POST", f"/api/session/{other}/prompt", payload)
                facts[mode + ".other_record_conflicts"] = code == 409 and isinstance(body, dict) and body.get(
                    "_tag") == "ConflictError"
    finally:
        llm.close()
    facts["_responses"] = details
    return facts


IDENTITY_FACTS = ("accepted_not_admitted", "duplicate_pending", "changed_pending_returns_original",
                  "duplicate_admitted", "changed_admitted_returns_original", "metadata_round_trip", "admitted_once",
                  "other_record_conflicts", "held_retry_does_not_wake")
IDENTITY_FACTS += ("admitted_retry_does_not_wake", "admitted_created_time_preserved", "admitted_delivery_preserved",
                   "first_identity_valid", "admitted_identity_valid")
HELD_FACTS = ("accepted_not_admitted", "held_retry_does_not_wake", "admitted_retry_does_not_wake", "staged_first")


def identity_check(ctx: Context, name: str) -> Outcome:
    observed = ctx.once("messaging.identity", lambda: identity_measurement(ctx))
    keys = IDENTITY_FACTS if name == "prompt_identity" else HELD_FACTS
    facts = {mode + "." + key: observed.get(mode + "." + key) for mode in ("steer", "queue") for key in keys}
    if name == "prompt_identity":
        from .reevaluate import identity_outcome

        return identity_outcome(facts, observed.get("_responses"))
    failed = [key for key, value in facts.items() if value is not True]
    measured = {"messaging." + name: facts}
    if name == "prompt_identity":
        measured["measurement.prompt_identity"] = observed.get("_responses", {})
    return Outcome(FAIL if failed else PASS, measured, failed)


def admission(server: Any, sid: str, mid: str, *, untagged: bool = False) -> str:
    """A raw REST admission observation. An untagged 404 checks session existence, never guesses admission."""
    status, body = http(server, "GET", f"/api/session/{sid}/message/{mid}")
    if status == 200:
        return "admitted"
    if status != 404:
        return "unknown"
    # Controlled response fault: prove the existence fallback against the same real server, not a guessed admission.
    tag = body.get("_tag") if isinstance(body, dict) and not untagged else None
    if tag == "MessageNotFoundError":
        return "pending"
    if tag == "SessionNotFoundError":
        return "session_lost"
    status, _ = http(server, "GET", f"/api/session/{sid}")
    return "pending" if status == 200 else "session_lost" if status == 404 else "unknown"


def loss_measurement(ctx: Context) -> dict[str, Any]:
    work = ctx.work / "loss"
    llm = model.start("responses", [])
    facts: dict[str, Any] = {}
    try:
        with opencode.serve(ctx.binary, work, ctx.env, opencode.server_config(llm.base_url),
                            {"OPENAI_API_KEY": opencode.SYNTHETIC_KEY}) as server:
            for mode in ("steer", "queue"):
                sid = session(server, str((work / "project").resolve()))
                mid = "msg_hq_loss_" + mode
                server.client.post(f"/api/session/{sid}/prompt", {
                    "id": mid, "text": "HQ_HELD", "delivery": mode, "resume": False})
                status, body = http(server, "GET", f"/api/session/{sid}/message/{mid}")
                facts[mode + ".missing_message_tag"] = status == 404 and isinstance(body, dict) and body.get(
                    "_tag") == "MessageNotFoundError"
                facts[mode + ".held_not_admitted"] = admission(server, sid, mid) == "pending"
                facts[mode + ".untagged_pending"] = admission(server, sid, mid, untagged=True) == "pending"
                server.client.delete(f"/api/session/{sid}")
                status, body = http(server, "GET", f"/api/session/{sid}/message/{mid}")
                facts[mode + ".missing_session_tag"] = status == 404 and isinstance(body, dict) and body.get(
                    "_tag") == "SessionNotFoundError"
                facts[mode + ".lost_not_admitted"] = admission(server, sid, mid) == "session_lost"
                facts[mode + ".untagged_loss"] = admission(server, sid, mid, untagged=True) == "session_lost"
    finally:
        llm.close()
    return facts


LOSS_FACTS = ("missing_message_tag", "held_not_admitted", "missing_session_tag", "lost_not_admitted",
              "untagged_pending", "untagged_loss")


def loss_check(ctx: Context) -> Outcome:
    observed = loss_measurement(ctx)
    facts = {mode + "." + key: observed.get(mode + "." + key)
             for mode in ("steer", "queue") for key in LOSS_FACTS}
    failed = [key for key, value in facts.items() if value is not True]
    return Outcome(FAIL if failed else PASS, {"messaging.session_loss": facts}, failed)


def binding_facts(events: list[dict[str, Any]]) -> dict[str, bool]:
    """Validate the observed call/step identities and ordering, not a digest. Missing and mismatched frames fail.
    This is qualification tooling, not the worker wait's implementation."""
    step = None
    names: dict[str, str] = {}
    opened: set[str] = set()
    calls: set[str] = set()
    completed: set[str] = set()
    failures: set[str] = set()
    steps = 0
    ended = 0
    execution_end = False
    parallel = False
    valid = True
    for event in events:
        kind, body = event.get("type"), event.get("data") or {}
        identity = body.get("assistantMessageID")
        cid = body.get("id")
        if kind == "session.step.started":
            valid &= step is None and bool(identity)
            step = identity
            steps += 1
        elif kind == "session.tool.input.started":
            valid &= bool(cid) and identity == step
            names[cid] = body.get("name")
        elif kind == "session.tool.called":
            valid &= bool(cid) and cid in names and identity == step and cid not in calls
            calls.add(cid)
            if names.get(cid) in ("bash", "shell"):
                opened.add(cid)
                parallel |= len(opened) >= 2
        elif kind in ("session.tool.success", "session.tool.failed"):
            validation_failure = kind == "session.tool.failed" and body.get("executed") is False and cid in names
            valid &= (cid in calls or validation_failure) and cid not in completed and identity == step
            if cid in calls:
                completed.add(cid)
            opened.discard(cid)
            if kind == "session.tool.failed":
                failures.add(cid)
        elif kind in ("session.step.ended", "session.step.failed"):
            valid &= bool(step) and identity == step and not opened
            step = None
            ended += 1
        elif kind in ("session.execution.succeeded", "session.execution.failed", "session.execution.interrupted"):
            valid &= step is None and not opened
            execution_end = True
    return {"call_step_identity_order": bool(valid and steps and steps == ended and calls and calls == completed),
            "parallel_shell_calls": parallel,
            "completion_and_failure": bool(failures and completed - failures),
            "execution_end": execution_end}


def binding_measurement(ctx: Context) -> dict[str, Any]:
    work = ctx.work / "binding"
    work.mkdir(parents=True, exist_ok=True)
    release = work / "release"
    script = work / "child.py"
    script.write_text(
        "import json,os,pathlib,sys,time\n"
        f"root=pathlib.Path({str(work)!r})\n"
        "name=sys.argv[1]\n"
        "pending=root/(name+'-started.tmp')\n"
        "pending.write_text(json.dumps({'pid':os.getpid(),'parent':os.getppid()}))\n"
        "pending.replace(root/(name+'-started'))\n"
        "deadline=time.monotonic()+40\n"
        "while not (root/'release').exists():\n"
        " if time.monotonic()>deadline: raise TimeoutError('probe release missing')\n"
        " time.sleep(.05)\n"
        "(root/(name+'-completed')).touch()\n"
        "sys.exit(0 if name=='long' else 7)\n", encoding="utf-8")
    commands = {name: shlex.join([sys.executable, str(script), name]) for name in ("long", "short")}
    # Explicit sh plus trailing ':' exercises a real parent shell, not an exec-replaced interpreter.
    commands["short"] = "sh -c " + shlex.quote(commands["short"] + "; :")
    llm = model.start("responses", [{"calls": [
        {"call": ["bash", "shell"], "arguments": {"command": commands["long"], "description": "long call"}},
        {"call": ["bash", "shell"], "arguments": {
            "command": commands["short"], "description": "short shell timeout", "timeout": 1000}},
        {"call": ["bash", "shell"], "arguments": {
            "command": None, "description": "intentional invalid tool argument to observe tool.failed"}}]},
        {"text": "HQ_BOUND_CALLS_DONE"}])
    events: list[dict[str, Any]] = []
    try:
        with opencode.serve(ctx.binary, work, ctx.env, opencode.server_config(llm.base_url),
                            {"OPENAI_API_KEY": opencode.SYNTHETIC_KEY}) as server:
            sid = session(server, str((work / "project").resolve()))
            stream = EventStream(server.client, lambda e: events.append(e) if
                                 (e.get("data") or {}).get("sessionID") == sid else None, server.alive)
            try:
                stream.start()
                if not stream.connected.is_set() or stream.last_error:
                    raise RuntimeError("the event stream was not connected")
                server.client.post(f"/api/session/{sid}/prompt", {"id": "msg_hq_binding", "text": "HQ_BINDING"})
                until(lambda: (work / "long-started").exists() and (work / "short-started").exists(),
                      "both foreground child processes")

                def short_ended() -> bool:
                    calls = {(e.get("data") or {}).get("id") for e in events
                             if e.get("type") == "session.tool.called" and
                             ((e.get("data") or {}).get("input") or {}).get("command") == commands["short"]}
                    return any(e.get("type") in ("session.tool.success", "session.tool.failed") and
                               (e.get("data") or {}).get("id") in calls for e in events)

                until(short_ended,
                      "the short call's failure beside the still-running call")
                facts = {"short_call_ends_before_step": not any(e.get("type") in (
                    "session.step.ended", "session.step.failed") for e in events)}
                child = json.loads((work / "short-started").read_text(encoding="utf-8"))
                facts["real_shell_child_started"] = all(isinstance(child.get(k), int) and child[k] > 0
                                                        for k in ("pid", "parent"))
                facts["distinct_shell_child"] = facts["real_shell_child_started"] and child["pid"] != child["parent"]
                process = {"child_alive_after_timeout": process_alive(child["pid"]),
                           "parent_alive_after_timeout": process_alive(child["parent"])}
                release.touch()
                until(lambda: any(e.get("type") == "session.execution.succeeded" for e in events),
                      "the execution end")
                facts.update(binding_facts(list(events)))
                # A real forced stream drop, followed by another real turn whose frames must arrive after reconnect.
                before = len(events)
                stream._drop()
                until(lambda: stream.drops >= 1, "the stream drop")
                until(lambda: stream._sock is not None, "the reconnected event stream")
                server.client.post(f"/api/session/{sid}/prompt", {"id": "msg_hq_reconnect", "text": "HQ_RECONNECT"})
                until(lambda: any(e.get("type") == "session.execution.succeeded" for e in events[before:]),
                      "post-reconnect execution frames")
                facts["stream_drop_and_reconnect"] = stream.drops >= 1
                facts["process_observation"] = process  # informative either way, never an assumed orphan outcome
                return facts
            finally:
                release.touch()
                stream.close()
    finally:
        release.touch()
        llm.close()


BINDING_FACTS = ("call_step_identity_order", "parallel_shell_calls", "completion_and_failure", "execution_end",
                 "short_call_ends_before_step", "real_shell_child_started", "distinct_shell_child",
                 "stream_drop_and_reconnect")


def process_alive(pid: int) -> bool:
    """Observe only a probe-owned process ID. A zombie has ended even though kill(pid, 0) still succeeds."""
    from pathlib import Path

    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        os.kill(pid, 0)
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        return False


def binding_check(ctx: Context) -> Outcome:
    observed = binding_measurement(ctx)
    facts = {key: observed.get(key) for key in BINDING_FACTS}
    failed = [key for key, value in facts.items() if value is not True]
    process = observed.get("process_observation")
    if not isinstance(process, dict) or set(process) != {
            "child_alive_after_timeout", "parent_alive_after_timeout"} or not all(
                isinstance(value, bool) for value in process.values()):
        failed.append("missing real shell/child outcome observation")
    else:
        facts["process_observation"] = process
    return Outcome(FAIL if failed else PASS, {"messaging.wait_binding": facts}, failed)


def timeout_measurement(ctx: Context) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    for name, timeout in (("default", None), ("short", 1000)):
        work = ctx.work / name
        work.mkdir(parents=True, exist_ok=True)
        started, completed = work / "started", work / "completed"
        script = work / "timeout.py"
        script.write_text(
            "import pathlib,time\n"
            f"pathlib.Path({str(started)!r}).touch()\n"
            "time.sleep(150)\n"
            f"pathlib.Path({str(completed)!r}).touch()\n", encoding="utf-8")
        arguments = {"command": shlex.join([sys.executable, str(script)]), "description": "measure shell timeout"}
        if timeout is not None:
            arguments["timeout"] = timeout
        llm = model.start("responses", [{"call": ["bash", "shell"], "arguments": arguments}, {"text": "done"}])
        try:
            with opencode.serve(ctx.binary, work, ctx.env, opencode.server_config(llm.base_url),
                                {"OPENAI_API_KEY": opencode.SYNTHETIC_KEY}) as server:
                sid = session(server, str((work / "project").resolve()))
                server.client.post(f"/api/session/{sid}/prompt", {"id": "msg_hq_timeout_" + name, "text": "HQ_TIMEOUT"})
                until(started.exists, "the timeout command start")
                start = time.monotonic()
                until(lambda sid=sid: any(p.get("type") == "tool" and (
                    p.get("status") in ("completed", "error") or (p.get("state") or {}).get("status") in (
                        "completed", "error")) for m in opencode._messages(server, sid)
                    for p in m.get("content") or [] if isinstance(p, dict)), "the shell timeout result", seconds=175)
                observed[name + "_seconds"] = round(time.monotonic() - start, 2)
                observed[name + "_stopped_before_completion"] = not completed.exists()
                until(lambda sid=sid: sid not in ((server.client.get("/api/session/active") or {}).get("data") or {}),
                      "the timeout turn end")
        finally:
            llm.close()
    return observed


def timeout_check(ctx: Context) -> Outcome:
    observed = timeout_measurement(ctx)
    default, short = observed.get("default_seconds"), observed.get("short_seconds")
    numbers = all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and n > 0
                  for n in (default, short))
    # A full second is reserved for observation/poll delay in addition to the design's 30 s margin.
    maximum = max(0, min(90, math.floor(default) - 31)) if numbers else 0
    measured = {**observed, "maximum_safe_wait_seconds": maximum}
    notes = []
    if not numbers or maximum <= 0:
        notes.append("no positive safe wait budget measured")
    if observed.get("default_stopped_before_completion") is not True:
        notes.append("the foreground default did not stop the command")
    if observed.get("short_stopped_before_completion") is not True or not numbers or not short < default:
        notes.append("the shorter tool timeout was not observed")
    facts = {"positive_safe_wait_budget": numbers and maximum > 0,
             "foreground_default_stops_command": observed.get("default_stopped_before_completion") is True,
             "shorter_timeout_observed": numbers and short < default and
             observed.get("short_stopped_before_completion") is True}
    # Pin semantics, not wall-clock jitter. The exact measured durations/budget stay in the qualification record.
    return Outcome(FAIL if notes else PASS, {"messaging.shell_timeout": facts,
                                          "measurement.shell_timeout": measured}, notes)


def boundary_measurement(ctx: Context) -> dict[str, Any]:
    """Queue before steer, once during a model request and once during a foreground shell. The first following
    model request must contain the steers, not the queues. Both blocked actions must complete untruncated."""
    work = ctx.work / "boundary"
    work.mkdir(parents=True, exist_ok=True)
    entered, release = threading.Event(), threading.Event()
    started, finish, completed = (work / name for name in ("shell-started", "shell-release", "shell-completed"))
    script = work / "foreground.py"
    script.write_text(
        "import pathlib,time\n"
        f"pathlib.Path({str(started)!r}).touch()\n"
        "deadline=time.monotonic()+45\n"
        f"while not pathlib.Path({str(finish)!r}).exists():\n"
        " if time.monotonic()>deadline: raise TimeoutError('probe release missing')\n"
        " time.sleep(.05)\n"
        f"pathlib.Path({str(completed)!r}).touch()\n"
        "print('HQ_FOREGROUND_COMPLETED')\n", encoding="utf-8")
    llm = model.start("responses", [
        {"call": ["bash", "shell"], "arguments": {
            "command": shlex.join([sys.executable, str(script)]), "description": "probe foreground boundary"},
         "entered": entered, "release": release}, {"text": "HQ_TURN_COMPLETED"}])
    ids = {name: "msg_hq_" + name for name in ("initial", "q1", "s1", "q2", "s2")}
    try:
        with opencode.serve(ctx.binary, work, ctx.env, opencode.server_config(llm.base_url),
                            {"OPENAI_API_KEY": opencode.SYNTHETIC_KEY}) as server:
            sid = session(server, str((work / "project").resolve()))

            def prompt(name: str, mode: str | None = None) -> None:
                server.client.post(f"/api/session/{sid}/prompt", {
                    "id": ids[name], "text": "HQ_" + name, **({"delivery": mode} if mode else {})})

            def messages() -> list[dict[str, Any]]:
                return opencode._messages(server, sid)

            def admitted() -> set[str]:
                return {m.get("id") for m in messages()}

            prompt("initial")
            if not entered.wait(30):
                raise TimeoutError("the initial model request was not observed")
            prompt("q1", "queue")
            prompt("s1", "steer")
            during_model = admitted()
            release.set()
            until(started.exists, "the foreground shell start")
            # Reaching the shell proves the in-flight model response was not discarded by steer.
            during_shell = admitted()
            prompt("q2", "queue")
            prompt("s2", "steer")
            before_release = admitted()
            finish.touch()
            until(lambda: all(i in admitted() for i in ids.values()), "all five prompt admissions")
            until(lambda: len(main_requests(llm)) >= 2, "the next model request")
            until(lambda: sid not in ((server.client.get("/api/session/active") or {}).get("data") or {}),
                  "the completed queued turns")
            recorded = messages()
            users = [m.get("id") for m in recorded if m.get("type") == "user" and m.get("id") in ids.values()]
            following = json.dumps(main_requests(llm)[1]["body"].get("input"), sort_keys=True)
            parts = [p for m in recorded for p in m.get("content") or [] if isinstance(p, dict)
                     and p.get("type") == "tool"]
            exits = [(p.get("metadata") or (p.get("state") or {}).get("metadata") or {}).get("exit") for p in parts]
            return boundary_facts(ids, during_model, during_shell, before_release, users, following,
                                  started.exists(), completed.exists(), exits)
    finally:
        release.set()
        finish.touch()
        llm.close()


def boundary_facts(ids: dict[str, str], during_model: set[str], during_shell: set[str], before_release: set[str],
                   users: list[str], following: str, started: bool, completed: bool,
                   exits: list[Any]) -> dict[str, bool]:
    """Reduce raw admission samples/transcript/request/tool outcomes. The deterministic seam plants violations here,
    before the check verdict, rather than replacing a check's verdict or trusting a declared API enum."""
    first = {ids["q1"], ids["s1"]}
    all_pending = {ids[n] for n in ("q1", "q2", "s1", "s2")}
    return {
        "model_not_interrupted": not (first & during_model) and started,
        "shell_not_interrupted": not (first & during_shell) and not (all_pending & before_release)
        and completed and 0 in exits,
        "tool_output_not_truncated": "HQ_FOREGROUND_COMPLETED" in following,
        "steer_before_next_request": all("HQ_" + n in following for n in ("s1", "s2")),
        "queue_not_before_turn_end": all("HQ_" + n not in following for n in ("q1", "q2")),
        "steer_fifo": [i for i in users if i in (ids["s1"], ids["s2"])] == [ids["s1"], ids["s2"]],
        "queue_fifo": [i for i in users if i in (ids["q1"], ids["q2"])] == [ids["q1"], ids["q2"]],
        "steer_overtakes_queue": users == [ids[n] for n in ("initial", "s1", "s2", "q1", "q2")],
    }


BOUNDARY_FACTS = {
    "steer_boundary": ("model_not_interrupted", "shell_not_interrupted", "tool_output_not_truncated",
                       "steer_before_next_request", "steer_fifo"),
    "queue_boundary": ("queue_not_before_turn_end", "queue_fifo", "steer_overtakes_queue"),
}


def boundary_check(ctx: Context, name: str) -> Outcome:
    observed = ctx.once("messaging.boundaries", lambda: boundary_measurement(ctx))
    facts = {k: observed.get(k) for k in BOUNDARY_FACTS[name]}
    failed = [key for key, value in facts.items() if value is not True]
    return Outcome(FAIL if failed else PASS, {"messaging." + name: facts}, failed)


def checks() -> list[Check]:
    return [Check("messaging.steer_boundary", lambda c: boundary_check(c, "steer_boundary"),
                  ("steer_running_turn",), says="steer preserves in-flight model/shell work, is FIFO and precedes "
                  "the next request", measures=("messaging.steer_boundary",)),
            Check("messaging.queue_boundary", lambda c: boundary_check(c, "queue_boundary"),
                  ("queue_until_turn_end",), says="queue waits for turn end, is FIFO, and steer overtakes it",
                  measures=("messaging.queue_boundary",)),
            Check("messaging.prompt_identity", lambda c: identity_check(c, "prompt_identity"),
                  ("steer_running_turn", "queue_until_turn_end"),
                  says="both timings: metadata, deterministic ID retries/mismatch and 200 versus 409",
                  measures=("messaging.prompt_identity",)),
            Check("messaging.held_resume", lambda c: identity_check(c, "held_resume"),
                  ("wake_idle_session", "steer_running_turn", "queue_until_turn_end"),
                  says="both timings: resume:false holds, retries do not wake, default resume admits staged first",
                  measures=("messaging.held_resume",)),
            Check("messaging.session_loss", loss_check, ("steer_running_turn", "queue_until_turn_end"),
                  says="both timings: tagged missing message versus missing session, no false admission",
                  measures=("messaging.session_loss",)),
            Check("messaging.wait_binding", binding_check, ("report_step_and_shell_calls",),
                  says="call/step identity and order, parallel completion/failure, execution end and stream reconnect",
                  measures=("messaging.wait_binding",)),
            Check("messaging.shell_timeout", timeout_check, ("report_step_and_shell_calls",),
                  says="measure the foreground default and a shorter timeout; safe wait <=min(90, default minus 30)",
                  measures=("messaging.shell_timeout",))]
