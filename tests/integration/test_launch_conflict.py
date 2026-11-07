"""The launch conflict check for concurrent workers' files, end to end through the CLI (register E151; A-09
``CNI-03.a``, ``CNI-03.g``; ``aew.engine.conflicts``).

With ``mutating_concurrency`` above 1, a worker is held, not started, when its Ticket's declared scope can meet another
live mutating Ticket's scope or the paths that Ticket has changed, or when those paths cannot be read. The check runs
at assignment and again at each harness launch, against what the other worker has changed by then. Each case has its
planted control: the same Tickets admitted once the condition is gone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aewflow import create_planned_ticket, integrate, sample_project, to_commit_ready
from fake_harness import HarnessLab
from invariants import assert_control_invariants

from aew.util import dump_yaml, load_yaml

ONE = ("calc/one.py", "tests/test_one.py")
TWO = ("calc/two.py", "tests/test_two.py")


def concurrency(p, cap: int) -> None:
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": cap}),
                     encoding="utf-8", newline="\n")
    p.pin_policy()


def refused(p, *args, env: dict[str, str] | None = None) -> dict:
    rev = p.rev()
    res = p.aew(*args, "--expect-rev", str(rev), env={"AEW_LEAD_TOKEN": p.token, **(env or {})})
    assert res.returncode != 0, res.stdout
    assert p.rev() == rev  # a hold changes nothing
    return res.error


def held_by(error: dict) -> list[dict]:
    assert error["code"] == "DISPATCH_REFUSED", error
    return [b for b in error["details"]["blocking_conditions"] if b["code"] == "FILES_CONFLICT"]


def workspace(p, wid: str) -> Path:
    return Path(p.ok("work", "show", wid)["control"]["workspace"]["path"])


@pytest.fixture
def calc(tmp_path):
    p = sample_project(tmp_path)
    concurrency(p, 3)
    return p


def test_an_overlapping_pair_is_held_and_the_hold_says_why_and_what_it_waits_on(calc, tmp_path):
    first, _ = to_commit_ready(calc, tmp_path, title="Add subtract()", scope=("calc/**", "tests/**"))
    second = create_planned_ticket(calc, tmp_path, title="Add two", scope=TWO)
    invocation = calc.ok("work", "show", first)["control"]["implementer_invocation"]
    error = refused(calc, "work", "assign", second)
    [hold] = held_by(error)
    assert hold["details"]["work_id"] == first and hold["details"]["reasons"] == ["scopes_overlap"]
    assert hold["details"]["scope_pairs"] == [["calc/two.py", "calc/**"], ["tests/test_two.py", "tests/**"]]
    message = hold["message"]
    assert message.startswith(f"{second} is held, not started: {first} is live ({invocation}, workspace ")
    assert (f"{second} waits until {first} is integrated or cancelled, either of which releases its workspace"
            in message)
    assert message in error["message"]  # the refusal the Lead reads carries it whole
    assert calc.ok("work", "show", second)["control"]["state"] == "READY"
    # The planted control: once the first is integrated, which releases its workspace, nothing holds the second.
    integrate(calc, first)
    calc.lead("work", "assign", second)
    assert_control_invariants(calc)


def test_a_disjoint_pair_runs_at_once(calc, tmp_path):
    first = create_planned_ticket(calc, tmp_path, title="Add one", scope=ONE)
    second = create_planned_ticket(calc, tmp_path, title="Add two", scope=TWO)
    third = create_planned_ticket(calc, tmp_path, title="Change one", scope=("calc/one.py",))
    calc.lead("work", "assign", first)
    out = calc.lead("work", "assign", second)
    assert out["dispatch"]["allowed"] and "FILES_CONFLICT" not in out["dispatch"]["reason_codes"]
    assert workspace(calc, first) != workspace(calc, second)
    # The planted control: a third whose scope meets the first's is held, so the check was looking.
    [hold] = held_by(refused(calc, "work", "assign", third))
    assert hold["details"]["work_id"] == first
    assert_control_invariants(calc)


def test_a_live_ticket_whose_changed_paths_cannot_be_read_holds_the_dispatch(calc, tmp_path):
    """An inability to establish non-interference is a conflict, never a clearance (``CNI-03.a``)."""
    first = create_planned_ticket(calc, tmp_path, title="Add one", scope=ONE)
    second = create_planned_ticket(calc, tmp_path, title="Add two", scope=TWO)
    calc.lead("work", "assign", first)
    ws = workspace(calc, first)
    away = ws.with_name(ws.name + "-moved")
    ws.rename(away)
    try:
        [hold] = held_by(refused(calc, "work", "assign", second))
    finally:
        away.rename(ws)
    assert hold["details"]["reasons"] == ["paths_unknown"]
    assert str(ws) in hold["details"]["unreadable"]
    assert f"AEW cannot read which files {first} has changed" in hold["message"]
    assert f"or until {first}'s workspace can be read" in hold["message"]
    # The planted control: the same workspace, readable again, holds nothing.
    calc.lead("work", "assign", second)
    assert_control_invariants(calc)


def test_an_earlier_clear_answer_is_not_relied_on_when_the_dispatch_takes_effect(calc, tmp_path):
    """``CNI-X30``: two Tickets each found clear on the same state cannot both be admitted. The decision is made
    again inside the transaction that makes it effective, so the second sees the first."""
    first = create_planned_ticket(calc, tmp_path, title="Add one", scope=("calc/**",))
    second = create_planned_ticket(calc, tmp_path, title="Add two", scope=TWO)
    for wid in (first, second):
        explained = calc.ok("dispatch", "explain", wid, "--entrypoint", "work.assign")
        assert explained["allowed"], explained
    calc.lead("work", "assign", first)
    [hold] = held_by(refused(calc, "work", "assign", second))
    assert hold["details"]["work_id"] == first
    assert not calc.ok("dispatch", "explain", second, "--entrypoint", "work.assign")["allowed"]


def test_at_concurrency_one_the_cap_answers_first(tmp_path):
    """The default (``mutating_concurrency: 1``) is unchanged: a second mutating Ticket meets the cap, whatever its
    scope."""
    p = sample_project(tmp_path)
    first = create_planned_ticket(p, tmp_path, title="Add one", scope=ONE)
    second = create_planned_ticket(p, tmp_path, title="Add two", scope=("calc/**",))
    p.lead("work", "assign", first)
    error = refused(p, "work", "assign", second)
    assert error["code"] == "CONCURRENCY_LIMIT", error


# ---------------------------------------------------------------- the check again at effect


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    concurrency(lab.project, 2)
    yield lab
    lab.cleanup()


def test_a_launch_is_checked_again_against_what_the_other_worker_has_changed(lab, tmp_path):
    """Both Tickets are assigned while disjoint; then the first worker changes a file inside the second's scope (a
    stray write outside its own). The second's launch, the moment its worker would start writing, is held naming that
    file. The planted control: with the file gone the same launch is admitted, and the first's own relaunch never
    conflicts with its own workspace."""
    p = lab.project
    first = create_planned_ticket(p, tmp_path, title="Add one", scope=ONE)
    second = create_planned_ticket(p, tmp_path, title="Add two", scope=TWO)
    one = lab.lead("work", "assign", first)["invocation"]
    two = lab.lead("work", "assign", second)["invocation"]
    stray = workspace(p, first) / "calc/two.py"
    stray.write_text("TWO = 2\n", encoding="utf-8")
    [hold] = held_by(refused(p, "harness", "launch", two, env=lab.env))
    assert hold["details"]["reasons"] == ["touched_in_scope"]
    assert hold["details"]["touched_in_scope"] == ["calc/two.py"]
    assert f"{first} has already changed calc/two.py, inside {second}'s scope" in hold["message"]
    explained = lab.ok("dispatch", "explain", second, "--invocation", two)  # the query equals the execution
    assert [b["message"] for b in explained["blocking_conditions"] if b["code"] == "FILES_CONFLICT"] == \
        [hold["message"]]

    stray.unlink()
    lab.script(two, [])
    lab.script(one, [])
    run = lab.lead("harness", "launch", two)["run"]
    lab.wait(run)
    run = lab.lead("harness", "launch", one)["run"]  # its own changes never hold it
    lab.wait(run)
    assert_control_invariants(p)
