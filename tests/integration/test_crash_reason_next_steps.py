"""The content-filter next step in a crashed run's reason, followed on the real CLI (PR #310 review, F1).

The unit tests prove that every printed command parses. This proves that doing what the message says works: the
relaunch is accepted and keeps the pin, and cancelling then dispatching with ``--model`` gives a new invocation pinned
to the chosen model; before the cancel, the dispatch is refused because the invocation is still active.
"""

from __future__ import annotations

import re
import shlex

import pytest
from aewflow import create_planned_ticket, sample_project
from fake_harness import HarnessLab

from aew.harness.supervisor import Supervisor

FENCE = re.compile(r"```sh\n(.*?)```", re.S)
INLINE = re.compile(r"`(aew [^`]*)`")
DETAIL = "the agent's turn ended: failed (provider.content-filter, 200: invalid_prompt: flagged)"


@pytest.fixture
def fake_lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def printed_reason(inv: str, wid: str) -> str:
    """The reason the supervisor gives a run of ``inv`` that exits on a content filter."""
    supervisor = Supervisor.__new__(Supervisor)
    supervisor.inv_id = inv
    supervisor.record = {"contract": {"expected_kinds": []}, "work_unit": wid}
    supervisor._evidence = lambda **_kwargs: []  # type: ignore[method-assign]
    ended: list[str] = []
    supervisor._finish = lambda status, reason, **_kwargs: ended.append(reason)  # type: ignore[method-assign]
    Supervisor._finish_exited(supervisor, {"exit_code": 1, "detail": DETAIL})
    return ended[0]


def run_printed(lab: HarnessLab, command: str, stdin: str = "", *, model: str | None = None):
    """Run a printed ``aew ...`` command as a Lead: the revision placeholder is the project's current revision."""
    argv = shlex.split(command.replace("<revision from aew status>", str(lab.project.rev())))[1:]
    if model:
        argv = [model if a == "PROVIDER/MODEL" else a for a in argv]
    return lab.project.aew(*argv, "--token", lab.project.token, env=lab.env, input=stdin or None)


def test_the_content_filter_next_step_can_be_followed_to_a_new_model(fake_lab, tmp_path):
    lab = fake_lab
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "exit", "code": 3}])
    out = lab.lead("work", "assign", wid, "--launch")
    inv, run = out["invocation"], out["launch"]["run"]
    assert lab.wait(run)["status"] == "crashed"
    pin = lab.ok("invoke", "show", inv)["execution_profile"]

    reason = printed_reason(inv, wid)
    (relaunch,) = INLINE.findall(FENCE.sub("", reason))
    cancel, create, _redispatch = (block.splitlines() for block in FENCE.findall(reason))

    # "Relaunch it": accepted, and the pin stays (ADR-0010).
    res = run_printed(lab, relaunch)
    assert res.returncode == 0, res.stderr or res.stdout
    lab.wait(res.json["run"])
    assert lab.ok("invoke", "show", inv)["execution_profile"] == pin

    # "dispatch a new invocation on another model" while this one is active is refused, for the reason the cancel
    # command above it answers: the old invocation is still active.
    early = run_printed(lab, create[0], model="fakeprov/other-model")
    assert early.returncode != 0 and "still active" in (early.error or {}).get("message", early.stderr)

    # "cancel it": the heredoc body is the reason.
    res = run_printed(lab, cancel[0].removesuffix("<<'EOF'").strip(), "\n".join(cancel[1:-1]) + "\n")
    assert res.returncode == 0, res.stderr or res.stdout
    assert lab.ok("invoke", "show", inv)["status"] == "cancelled"

    # "dispatch a new invocation on another model": pinned to it by the Lead.
    res = run_printed(lab, create[0], model="fakeprov/other-model")
    assert res.returncode == 0, res.stderr or res.stdout
    new_pin = lab.ok("invoke", "show", res.json["invocation"])["execution_profile"]
    assert new_pin["model"] == "other-model" and new_pin["selected_by"] == "lead"
    lab.wait(res.json["launch"]["run"])
