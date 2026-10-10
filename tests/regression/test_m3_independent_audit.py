"""Findings of the designer's independent M3 audit (`docs/archive/reviews/m3-independent-audit-2026-09-29.md`).

Each regression was written, and seen failing, before its fix.
"""

from __future__ import annotations

import sys
import textwrap
import time

import pytest

from aew.policy import checks
from aew.util import parse_frontmatter

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# A check whose process starts a child, then either hangs (and times out) or exits at once. The child waits for the
# test's "go" file, which the test writes only after the check has returned, then writes a marker: it must never get
# the chance, because the check's evidence is sealed when the check returns. (Ordered by the go file, not by a delay:
# under load a fixed delay can elapse while the check is still legitimately running.)
PARENT = textwrap.dedent("""\
    import subprocess, sys, time
    child = ("import time, pathlib, sys; m = pathlib.Path(sys.argv[1]); go = m.with_name('go'); t = time.time()\\n"
             "while not go.exists() and time.time() - t < 60: time.sleep(0.02)\\n"
             "m.write_text('child continued')")
    subprocess.Popen([sys.executable, "-c", child, sys.argv[1]], creationflags={flags},
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(float(sys.argv[2]))
""").format(flags=NO_WINDOW)


@pytest.mark.parametrize("parent_runs_s, timeout_s", [(30, 0.5), (0, 30)], ids=["parent-times-out", "parent-exits"])
def test_a_check_leaves_no_process_behind_when_it_returns(tmp_path, parent_runs_s, timeout_s):
    """I2. A check timing out (or its parent exiting) left its descendants running: `subprocess.run` ends only
    the direct child. The engine then took the after-snapshot and sealed the evidence while a descendant could
    still change the workspace. Every process a check starts must be gone when the check returns."""
    marker = tmp_path / "marker.txt"
    script = tmp_path / "parent.py"
    script.write_text(PARENT, encoding="utf-8")
    cfg = {"command": ["{python}", str(script), str(marker), str(parent_runs_s)], "timeout_s": timeout_s}
    result = checks.run(cfg, tmp_path)
    if parent_runs_s:
        assert result["exit_code"] is None and "TIMEOUT" in result["log"]
    else:
        assert result["exit_code"] == 0
    (tmp_path / "go").write_text("", encoding="utf-8")  # a surviving child writes its marker now
    time.sleep(1.5)
    assert not marker.exists(), "a process the check started outlived the check"


# --------------------------------------------------------------------------------------------- I3


class _TurnEndedServer:
    """Just enough of a V2 server for the adapter's poll: the last prompt was delivered and an idle follows it."""

    def __init__(self, session: str) -> None:
        self.session, self.posts = session, []

    def alive(self) -> bool:
        return True

    def get(self, path, params=None, **_):
        base = f"/api/session/{self.session}"
        if path == "/api/session/active":
            return {"data": {}}
        if path in (f"{base}/permission", f"{base}/form", f"{base}/inbox"):
            return {"data": []}
        if path.startswith(f"{base}/message/"):
            return {"data": {"id": path.rsplit("/", 1)[1], "type": "user", "time": {"created": 1}}}
        if path == f"{base}/message":
            return {"data": [{"id": "msg_idle", "type": "idle", "outcome": "succeeded", "time": {"created": 2}}]}
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, body=None, params=None, **_):
        self.posts.append((path, body))
        return {"data": {"id": (body or {}).get("id")}}


def _adapter_at_turn_end(tmp_path):
    import threading

    from aew.harness.opencode.adapter import OpenCodeAdapter

    events: list[dict] = []
    adapter = OpenCodeAdapter(None, tmp_path, events.append)
    adapter.session = "ses_1"
    fake = _TurnEndedServer(adapter.session)
    adapter.server = adapter.client = fake
    adapter.sent, adapter.turn = ["msg_contract"], "running"
    return adapter, fake, threading


def test_a_lead_message_sent_while_a_turn_is_being_closed_keeps_the_run_going(tmp_path):
    """I3. The poll decided the turn was over, then released the lock; a Lead `harness send` accepted by OpenCode
    in between (here: while the adapter takes its final snapshot) was then overwritten: the run ended with the
    message unanswered. A newer prompt must keep the run going."""
    adapter, fake, threading = _adapter_at_turn_end(tmp_path)

    def snapshot_while_the_lead_sends():
        lead = threading.Thread(target=adapter.send, args=("Also note the changed files.", "steer"))
        lead.start()
        lead.join(10)

    adapter._take_snapshot = snapshot_while_the_lead_sends
    adapter._poll()  # idle seen once
    adapter._poll()  # confirmed: the turn is closed, and the Lead's message arrives meanwhile
    assert [p for p, _ in fake.posts] == ["/api/session/ses_1/prompt"]
    assert len(adapter.sent) == 2
    assert adapter.turn == "running" and adapter.exit_code is None and adapter.inspect()["alive"]


def test_a_lead_message_sent_after_the_turn_ended_is_refused_never_revives_it(tmp_path):
    """I3, the other order. Once the turn has ended, the adapter's watcher has stopped; a `send` that set the turn
    back to "running" left a run that looked alive and that nothing watched. It must be refused (the supervisor
    records `request_failed`), and nothing may reach OpenCode."""
    from aew.errors import HarnessError

    adapter, fake, _ = _adapter_at_turn_end(tmp_path)
    adapter._take_snapshot = lambda: None
    adapter._poll()
    adapter._poll()
    assert adapter.turn == "ended"
    with pytest.raises(HarnessError):
        adapter.send("Too late.", "steer")
    assert fake.posts == [] and adapter.turn == "ended" and not adapter.inspect()["alive"]


# --------------------------------------------------------------------------------------------- I4


def _model_check(requested_effort, effective):
    from aew.harness.supervisor import Supervisor

    sup = Supervisor.__new__(Supervisor)  # only the comparison: no run, no process
    sup.record = {"timeline": [], "result": {"effective": effective},
                  "execution_profile": {"provider": "openai", "model": "gpt-6-sol", "effort": requested_effort}}
    sup.events = lambda _event: None
    sup._compare_effective()
    return sup.record["model_check"]


def test_the_adapter_tells_a_default_effort_from_an_unreported_one():
    """I4, at the adapter boundary. OpenCode's `default` variant is an observation (no effort variant ran); a
    missing or empty variant is not an observation at all. Both became `effort: None`."""
    from aew.harness.opencode.adapter import _effective

    observed = _effective([{"providerID": "openai", "id": "gpt-6-sol", "variant": "default"}])
    assert observed == [{"provider": "openai", "model": "gpt-6-sol", "effort": None}]
    for unreported in ({"providerID": "openai", "id": "gpt-6-sol"},
                       {"providerID": "openai", "id": "gpt-6-sol", "variant": ""}):
        assert _effective([unreported]) == [{"provider": "openai", "model": "gpt-6-sol", "effort": None,
                                             "effort_unreported": True}]


@pytest.mark.parametrize("requested, effective, status", [
    ("high", {"effort": None}, "mismatch"),                               # default ran, high was requested
    ("high", {"effort": None, "effort_unreported": True}, "effort_unreported"),  # cannot be verified: never "match"
    ("high", {"effort": "high"}, "match"),
    (None, {"effort": None}, "match"),                                    # nothing requested, default ran
    (None, {"effort": None, "effort_unreported": True}, "match"),         # nothing requested, nothing to verify
    (None, {"effort": "high"}, "mismatch"),
])
def test_a_requested_effort_is_verified_or_reported_unverified_never_assumed(requested, effective, status):
    """I4. The supervisor compared effort only when the harness reported one, so a run requested at `high` that
    ran at the default variant (or whose variant was not reported) was recorded `model_check: match`."""
    check = _model_check(requested, [{"provider": "openai", "model": "gpt-6-sol", **effective}])
    assert check["status"] == status, check


# --------------------------------------------------------------------------------------------- I5


def _expand(tmp_path, text: str) -> list[str]:
    from aew.cli import fields
    from aew.cli.main import build_parser

    path = tmp_path / "fields.yaml"
    path.write_bytes(text.encode("utf-8"))
    return fields.expand(["work", "create", "ticket", "--fields", str(path)], build_parser())


SILENTLY_CHANGED = {  # what the YAML layer stored for each, before this fix
    "comment after a value": "goal: Finish #1 with $5.00\n",            # "Finish"
    "comment after a list item": "goal:\n  - one # two\n",               # "one"
    "duplicate key": "goal: first\ngoal: second\n",                      # "second" only
    "two spellings of one option": "expect_rev: 1\nexpect-rev: 2\n",     # "2" only
    "anchor": "goal: &1 is the first case\n",                            # "is the first case"
    "alias": "title: &t x\ngoal: [*t]\n",                                # a copy of another value
    "tag": "goal: !x value\n",                                           # "value"
    "plain value over two lines": "goal: first line\n  second line\n",   # "first line second line"
}


@pytest.mark.parametrize("text", SILENTLY_CHANGED.values(), ids=SILENTLY_CHANGED.keys())
def test_fields_input_that_yaml_would_silently_change_is_refused(tmp_path, text):
    """I5. `--fields` protects authored text from the shell, but its YAML layer changed it silently: a ` #` began
    a comment, a repeated key replaced the first, anchors and tags were dropped, a plain value's line break became
    a space. Each is refused, saying how to write the value, so the author's text is never changed unseen."""
    from aew.errors import UsageError

    with pytest.raises(UsageError):
        _expand(tmp_path, text)


@pytest.mark.parametrize("text, goal", [
    ("goal: 'Finish #1 with $5.00'\n", "Finish #1 with $5.00"),
    (r"goal: 'it''s C:\temp\new: ok'" + "\n", r"it's C:\temp\new: ok"),
    ("goal: |-\n  Finish #1 with $5.00\n  and: more\n", "Finish #1 with $5.00\nand: more"),
    (r'{"goal": "Finish #1 with $5.00 in C:\\temp"}', r"Finish #1 with $5.00 in C:\temp"),
    ("goal: plain text stays as written\n", "plain text stays as written"),
    ("# a note on its own line\ngoal: x\n", "x"),
], ids=["single-quoted", "single-quoted backslashes", "block", "json", "plain", "own-line comment"])
def test_quoted_block_and_json_values_arrive_exactly(tmp_path, text, goal):
    assert f"--goal={goal}" in _expand(tmp_path, text)


def test_a_goal_is_stored_as_intended_or_refused_never_truncated(tmp_path):
    """I5, end to end: the stored goal is compared with the value its author intended."""
    from aewflow import sample_project

    p = sample_project(tmp_path)

    def create(text: str):
        return p.aew("work", "create", "ticket", "--class", "1", "--title", "t", "--fields", "-",
                     "--token", p.token, "--expect-rev", str(p.rev()), input=text)

    intended = "Finish #1 with $5.00"
    refused = create(f"goal: {intended}\n")
    assert refused.returncode != 0 and refused.error["code"] == "USAGE", refused.stdout
    assert "quote" in refused.error["message"]
    created = create(f"goal: '{intended}'\n")
    assert created.returncode == 0, created.stderr
    wid = created.json["id"]
    meta = parse_frontmatter((p.root / ".aew" / "work" / wid / "ticket.md").read_text(encoding="utf-8"), source=wid)[0]
    assert meta["acceptance"]["goal_backwards"] == [intended]


def test_invalid_fields_yaml_says_how_to_fix_it(tmp_path):
    """I5, seen in the dogfood: 5 of the Leads' 89 `--fields` inputs indented a key by one space (` goal:`), and the
    refusal was YAML's own "mapping values are not allowed here". It must say where, and what to do instead."""
    from aew.errors import UsageError

    with pytest.raises(UsageError) as refused:
        _expand(tmp_path, "title: Add category filtering\n goal:\n  - it filters\n")
    message = refused.value.message
    assert "line 2" in message and "beginning of its line" in message and "single quotes" in message, message


# --------------------------------------------------------------------------------------------- I1


def _redefine_check(p, check_id: str, **changes) -> None:
    import yaml as _yaml

    policy = p.root / ".aew" / "policy" / "checks.yaml"
    data = _yaml.safe_load(policy.read_text(encoding="utf-8"))
    data["checks"][check_id].update(changes)
    policy.write_text(_yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")
    p.adopt_policy()


def _unit_check(p, wid: str) -> dict:
    return p.ok("gate", "show", wid)["gates"]["local_checks"]["checks"]["unit"]


def test_a_passed_check_goes_stale_when_its_definition_changes(tmp_path):
    """I1. A passing `unit` result stayed CURRENT after `unit`'s command in policy/checks.yaml changed: the gate
    matched evidence by check id, workspace fingerprint and plan revision only, so one check id stood for two
    acceptance conditions. Decision (a): an in-flight Ticket satisfies the current definition, so the old result
    is STALE (never silently CURRENT) and the check must run again. A description is not part of the definition."""
    from aewflow import assign, create_planned_ticket, implement, sample_project

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    assert _unit_check(p, wid)["status"] == "CURRENT"
    _redefine_check(p, "unit", description="reworded, same check")
    assert _unit_check(p, wid)["status"] == "CURRENT"
    _redefine_check(p, "unit", command=["{python}", "-c", "raise SystemExit(1)"])
    stale = _unit_check(p, wid)
    assert stale["status"] == "STALE" and "definition" in stale.get("reason", ""), stale
    assert impl.check("unit")["result"] == "fail"  # run again under the definition now in force
    assert _unit_check(p, wid)["status"] == "FAILED"


def test_a_post_integration_check_counts_only_under_its_current_definition(tmp_path):
    """I1, the same boundary at publication: a policy-required post-integration check is satisfied only by a
    result for the check as it is defined now."""
    import copy

    from aewflow import prepare_and_validate, sample_project, to_commit_ready

    from aew.knowledge.manifest import DEFAULT_GATES

    gates = copy.deepcopy(DEFAULT_GATES)
    gates["local_checks"] = []  # only the post-integration requirement depends on `unit` here
    p = sample_project(tmp_path, gates=gates)
    wid, _ = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    _redefine_check(p, "unit", command=["{python}", "-c", "raise SystemExit(1)"])
    refused = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert refused.returncode != 0 and "post-integration" in refused.error["message"], refused.stdout
