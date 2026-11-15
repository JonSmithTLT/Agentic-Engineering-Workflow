"""Run the real worker and contained Lead against the local scripted model."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from harness_qualify import model
from harness_qualify.core import private_env
from harness_qualify.opencode import SYNTHETIC_KEY

from aew.capability import consent, ops
from aew.engine.api import Engine
from aew.harness import runlog
from aew.harness.opencode import projection
from aew.surface import lead_text, mcp

from . import measure

# The worker uses this catalog model's context limit, but the relay upstream is the scripted server.
MODEL = "gpt-5.4"
BIG_USAGE = {**model.ZERO_USAGE, "input_tokens": 5_000_000, "total_tokens": 5_000_000}
SUMMARY = """## Objective
- (none)

## Requirements
- (none)

## Decisions
- (none)

## Work State
### Completed
- ran echo e231-probe-step

### Active
- (none)

### Blocked
- (none)

## Next Move
1. run echo e231-after-compaction

## Relevant Files
- (none)

## Important Context
- (none)"""


def shell(command: str) -> dict:
    return {"call": ["bash", "shell"], "arguments": {"command": command, "description": "E231 scripted read"}}


def typed(name: str, **arguments: Any) -> dict:
    return {"call": [*(prefix + name for prefix in measure.LEAD_PREFIXES), name], "arguments": arguments}


@contextmanager
def launched_worker(binary: Path, out: Path, llm: model.ResponsesModel) -> Iterator[tuple[Any, str, str]]:
    from aewflow import create_planned_ticket, sample_project
    from fake_harness import POLICY, HarnessLab

    private = private_env(out / "worker-private", harness="opencode")
    private["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin"))
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(private, AEW_OPENCODE_BIN=str(binary), LANG="C.UTF-8", PYTHONDONTWRITEBYTECODE="1")
    lab = None
    try:
        fixture = out / "fixture"
        project = sample_project(fixture)
        policy = {**POLICY, "harness": "opencode", "provider_env": ["OPENAI_API_KEY"],
                  "profiles": {"standard": {"provider": "openai", "model": MODEL, "effort": "medium"}}}
        lab = HarnessLab.create(project, fixture, policy=policy, extra_env={"OPENAI_API_KEY": SYNTHETIC_KEY},
                                upstreams={"openai": llm.base_url})
        lab.env.pop("AEW_HARNESS_ADAPTERS", None)
        wid = create_planned_ticket(lab.project, fixture)
        inv = lab.lead("work", "assign", wid)["invocation"]
        lab.lead("work", "transition", wid, "--to", "RUNNING")
        run = lab.lead("harness", "launch", inv)["run"]
        yield lab, wid, run
    finally:
        try:
            if lab is not None:
                lab.cleanup()
        finally:
            os.environ.clear()
            os.environ.update(old)


def containment_facts(label: dict) -> dict:
    return {"filesystem": label.get("filesystem"), "mechanism": label.get("mechanism"),
            "network_mode": (label.get("network") or {}).get("mode")}


def worker_facts(directory: Path) -> dict:
    saved = runlog.read_record(directory)
    if saved is None:
        raise ValueError("missing saved worker run record")
    label = saved["containment"]
    path = directory / "harness/opencode-config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    denies = sorted({rule["resource"] for rule in config.get("experimental", {}).get("policies", [])
                     if rule.get("action") == "provider.use" and rule.get("effect") == "deny"})
    return {"containment": containment_facts(label), "provider_denies": denies}


def worker(binary: Path, out: Path) -> dict:
    llm = model.start("responses", [
        {**shell("echo e231-probe-step"), "usage": BIG_USAGE},
        {"text": SUMMARY},
        shell("echo e231-after-compaction"),
        {"text": "Worker finished."},
    ], capture_wire=True)
    credential = ""
    try:
        with launched_worker(binary, out, llm) as (lab, _wid, run):
            credential = lab.project.token
            state = lab.wait(run, timeout=420)["status"]
            facts = worker_facts(runlog.run_dir(lab.aew_root, run))
    finally:
        llm.close()
        measure.save_requests(out / "requests", llm.requests, credential)
    requests = [r for r in llm.requests if r.get("main")]
    if len(requests) < 3:
        raise ValueError("the worker did not reach the scripted compaction and its next request")
    original = next(item for item in requests[0]["body"]["input"] if item.get("role") == "user")
    rows = []
    for request in requests:
        items = request["body"].get("input") or []
        last = measure.text_of(items[-1]) if items else ""
        rows.append({
            "raw_bytes": request["raw_bytes"],
            "input_items": len(items),
            "first_message_survives": original in items,
            "compaction_request": "summarize the conversation" in last.lower(),
            "summary_present": any("<conversation-checkpoint>" in measure.text_of(item) for item in items),
        })
    if not any(row["compaction_request"] for row in rows) or not any(row["summary_present"] for row in rows):
        raise ValueError("no compaction and checkpoint pair was captured")
    return {"status": state, **facts, "first_request": measure.request_parts(requests[0]),
            "requests": rows}


def at_terminal(lab: Any, binary: Path, out: Path, llm: model.ResponsesModel, start: int, expected: int) -> None:
    import pty
    import select

    env = {**lab.env, **private_env(out / "lead-private", harness="opencode"),
           "AEW_OPENCODE_BIN": str(binary), "AEW_LEAD_TOKEN": lab.project.token,
           "OPENAI_API_KEY": SYNTHETIC_KEY, "TERM": "xterm-256color"}
    env = {k: v for k, v in env.items() if not k.startswith("GIT_")}
    attach = ("import fcntl, os, sys, termios\nfcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
              "os.execv(sys.executable, [sys.executable, '-m', 'aew', *sys.argv[1:]])\n")
    argv = ["-C", str(lab.root), "opencode", "--provider-env", "OPENAI_API_KEY", "--",
            "--prompt", "E231 scripted Lead probe."]
    master, slave = pty.openpty()
    try:
        try:
            proc = subprocess.Popen([sys.executable, "-c", attach, *argv], env=env,
                                    stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        finally:
            os.close(slave)
        try:
            deadline = time.monotonic() + 300
            prompt = consent.screen([]).splitlines()[-1].encode()
            tail = b""
            answered = False
            while proc.poll() is None and time.monotonic() < deadline:
                if len([r for r in llm.requests[start:] if r.get("main")]) >= expected:
                    return
                if select.select([master], [], [], 0.25)[0]:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    tail = (tail + data)[-65536:]
                    if not answered and tail.endswith(prompt):
                        os.write(master, f"{consent.NONE}\n".encode())
                        answered = True
            raise ValueError(f"the contained Lead did not finish the scripted calls (exit {proc.poll()})")
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
    finally:
        os.close(master)


def calibration(lab: Any) -> tuple[str, str, dict, dict]:
    from aew.harness.opencode.lead import pushes_wakes

    engine = Engine.discover(lab.root)
    runs = runlog.run_dir(engine.aew_root, "unused").parent
    [marker] = runs.glob("lead-*/label.json")
    label = json.loads(marker.read_text(encoding="utf-8"))
    tools = ops.placed(label, contained=True)
    guide = lead_text.guide_for(engine)
    systems = {wake: projection.lead_config(contained=label, tools=tools, push_wake=wake)["agents"][
        projection.LEAD_AGENT]["system"] for wake in (False, True)}
    return guide, systems[pushes_wakes(engine)], {
        "push_wake": pushes_wakes(engine),
        "system": {str(wake).lower(): {"utf8_bytes": len(text.encode("utf-8")), "json_utf8_bytes": measure.size(text),
                                      "json_ascii_bytes": measure.size(text, ascii_only=True)}
                   for wake, text in systems.items()},
        "guide": {"utf8_bytes": len(guide.encode("utf-8")), "json_utf8_bytes": measure.size(guide),
                  "json_ascii_bytes": measure.size(guide, ascii_only=True)},
        "mcp_compact_ascii_bytes": mcp.advertised_bytes(mcp.tools_list("normal")),
    }, containment_facts(label)


def lead(binary: Path, out: Path) -> dict:
    llm = model.start("responses", [shell("echo e231-worker"), {"text": "Worker finished."}], capture_wire=True)
    credential = ""
    try:
        with launched_worker(binary, out, llm) as (lab, wid, run):
            credential = lab.project.token
            worker_status = lab.wait(run, timeout=300)["status"]
            worker_observation = worker_facts(runlog.run_dir(lab.aew_root, run))
            turns = [
                typed("status"), typed("work_show", work_id=wid), typed("harness_wait", runs=[run], timeout_s=1),
                shell("aew status"), shell(f"aew work show {wid}"), shell(f"aew harness wait {run} --timeout 1"),
                {"text": "Lead probe finished."},
            ]
            with llm._lock:
                start = len(llm.requests)
                llm.script = llm.script[:llm._main] + turns
            at_terminal(lab, binary, out, llm, start, len(turns))
            guide, system, offline, contained = calibration(lab)
            for name, text in (("system.txt", system), ("guide.txt", guide)):
                (out / name).write_text(text, encoding="utf-8", newline="\n")
    finally:
        llm.close()
        measure.save_requests(out / "requests", llm.requests, credential)
    requests = [r for r in llm.requests[start:] if r.get("main")]
    return {"containment": contained, "worker_status": worker_status, "worker": worker_observation,
            "offline": offline, "request_start": start, **measure.lead_measurements(requests, guide, system)}
