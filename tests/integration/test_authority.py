"""Lead authority, credentials and operator authorization (WC §5, §6; KC §7.2; AT-4b)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pytest
from conftest import IS_WINDOWS, Project, clean_env, git, run_aew


def control_bytes(p: Project) -> bytes:
    return (p.root / ".aew/state/control.yaml").read_bytes()


def all_files_text(root: Path) -> str:
    chunks = []
    for f in root.rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            chunks.append(f.read_bytes().decode("utf-8", "replace"))
    return "\n".join(chunks)


# ------------------------------------------------------------------ init & candidates


def test_init_discovers_candidates_but_confers_no_authority(repo):
    p = Project(repo)
    out = p.ok("init")
    paths = {c["path"]: c for c in out["authority_candidates"]}
    assert paths["docs/adr/"]["suggested_class"] == "decisions"
    assert paths["docs/adr/"]["confidence"] == "high"
    assert paths["README.md"]["confidence"] == "low"
    listing = p.ok("authority", "list")
    assert listing["accepted"] == []
    assert all(c["status"] == "proposed" for c in listing["candidates"])
    questions = (repo / ".aew/knowledge/OPEN-QUESTIONS.md").read_text()
    for c in out["authority_candidates"]:
        assert c["id"] in questions
    # Nothing is duplicated into .aew: candidates are references only.
    assert not (repo / ".aew/knowledge/0001-use-aew.md").exists()


def test_accept_and_reject_candidates(project):
    cands = {c["path"]: c["id"] for c in project.ok("authority", "list")["candidates"]}
    res = project.as_operator("authority_accept", candidate_id=cands["docs/adr/"], klass="decisions",
                              decided_by="operator")
    decision = project.root / f".aew/decisions/{res['decision']}.md"
    assert decision.exists() and "authority_acceptance" in decision.read_text()
    project.lead("authority", "reject", cands["README.md"], "--reason", "orientation only")
    listing = project.ok("authority", "list")
    assert [a["path"] for a in listing["accepted"]] == ["docs/adr/"]
    status = {c["path"]: c["status"] for c in listing["candidates"]}
    assert status["README.md"] == "rejected"
    assert project.ok("status", "--json")["contradictions"] == []


def test_manifest_edit_outside_engine_detected_and_adopted(project):
    manifest = project.root / ".aew/project.yaml"
    manifest.write_text(manifest.read_text().replace("profile: base", "profile: python"))
    cands = project.ok("authority", "list")["candidates"]
    res = project.aew("authority", "accept", cands[0]["id"], "--class", "orientation",
                      "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.returncode == 6 and res.error["code"] == "INTEGRITY_ERROR"
    assert project.ok("status", "--json")["contradictions"]
    project.lead("manifest", "adopt", "--reason", "profile corrected by operator")
    assert project.ok("status", "--json")["contradictions"] == []


@pytest.mark.parametrize("argv", [
    ("authority", "accept", "{cand}", "--class", "decisions", "--decided-by", "operator"),
    ("work", "staff", "{wid}", "--review", "security_reviewer", "--by", "operator", "--pin"),
])
def test_a_decision_recorded_as_the_operators_needs_the_operator_at_their_terminal(project, argv):
    """Operator, 2026-10-06: "if my name is attached to it I should have actually approved". A flag that says the
    operator decided is refused unless the operator typed the code back at their own terminal; with no terminal (an
    agent's shell, this test) nothing is recorded. The engine refuses the same without the terminal's authorization."""
    from aew.engine.api import Engine
    from aew.errors import OperatorAuthorizationRequired

    cand = next(c["id"] for c in project.ok("authority", "list")["candidates"] if c["status"] == "proposed")
    wid = project.lead("work", "create", "ticket", "--title", "t", "--class", "1")["id"] \
        if argv[0] == "work" else ""
    args = [a.format(cand=cand, wid=wid) for a in argv]
    before = control_bytes(project)
    res = project.aew(*args, "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.error["code"] == "OPERATOR_AUTHORIZATION_REQUIRED", res.stderr
    assert control_bytes(project) == before
    engine = Engine.discover(project.root)
    with pytest.raises(OperatorAuthorizationRequired):
        if argv[0] == "work":
            engine.work_staff(token=project.token, expect_rev=project.rev(), work_id=wid, review=["security_reviewer"],
                              selected_by="operator", authorization={"authorized_by": "lead"})
        else:
            engine.authority_accept(token=project.token, expect_rev=project.rev(), candidate_id=cand,
                                    klass="decisions", decided_by="operator")
    assert control_bytes(project) == before


@pytest.mark.parametrize("by", ["operator", "lead"])
def test_the_cli_asks_the_operator_exactly_when_the_record_names_them(project, monkeypatch, by):
    """PR #103 re-review, N3: through the real CLI handlers, a record attributed to the operator is confirmed at the
    terminal and carries `authorized_by: operator-tty`; the Lead's own record never prompts. (The terminal itself is
    substituted in-process: no terminal exists here.)"""
    from aew import operator
    from aew.cli.main import main

    asked: list[str] = []
    confirmed = {"authorized_by": "operator-tty", "challenge_code": "X"}
    monkeypatch.setattr(operator, "authorize", lambda text, **_: asked.append(text) or confirmed)
    monkeypatch.delenv("AEW_LEAD_BROKER", raising=False)
    monkeypatch.chdir(project.root)
    cand = next(c["id"] for c in project.ok("authority", "list")["candidates"] if c["status"] == "proposed")
    wid = project.lead("work", "create", "ticket", "--title", "t", "--class", "1")["id"]
    assert main(["authority", "accept", cand, "--class", "decisions", "--decided-by", by, "--token", project.token,
                 "--expect-rev", str(project.rev())]) == 0
    assert main(["work", "staff", wid, "--review", "security_reviewer", "--by", by, "--token", project.token,
                 "--expect-rev", str(project.rev())]) == 0
    decisions = "".join(f.read_text(encoding="utf-8") for f in (project.root / ".aew/decisions").glob("*.md"))
    if by == "operator":
        assert [a.split(":")[0] for a in asked] == ["RECORD as YOUR decision", "RECORD as YOUR selection"], asked
        assert decisions.count("operator-tty") == 2
    else:
        assert asked == [] and "operator-tty" not in decisions


OPERATOR_DECISIONS = ("authority accept", "authority reject", "manifest adopt", "migrate")


def _names_the_operator(text: str) -> None:
    for command in OPERATOR_DECISIONS:
        if f"aew {command}" in text:
            assert "operator" in text, (command, text)


def test_what_the_lead_is_told_to_do_never_hands_it_an_operator_decision(project):
    """PR #103 review, F1: a Lead session refuses the operator's decisions, so the next actions and refusals the Lead
    reads say the operator runs them, at their own terminal, rather than sending the Lead into a refusal."""
    from invariants import load_control

    from aew.engine.base import as_v1
    from aew.engine.store import serialize_control
    from aew.harness import lead_broker

    assert {frozenset(c.split()) for c in OPERATOR_DECISIONS} == set(lead_broker.OPERATOR_DECIDED)
    actions = project.ok("status", "--json")["next_actions"]
    assert any("aew authority accept" in a for a in actions), actions
    for action in actions:
        _names_the_operator(action)
    manifest = project.root / ".aew/project.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"# edited\n")
    res = project.aew("checkpoint", "--next", "x", "--token", project.token, "--expect-rev", str(project.rev()))
    assert "aew manifest adopt" in res.error["message"]
    _names_the_operator(res.error["message"])
    project.lead("manifest", "adopt", "--reason", "reviewed")
    control = project.root / ".aew/state/control.yaml"
    control.write_bytes(serialize_control(as_v1(load_control(project.root))))
    res = project.aew("checkpoint", "--next", "x", "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.error["code"] == "MIGRATION_REQUIRED" and "aew migrate" in res.error["message"]
    _names_the_operator(res.error["message"])
    actions = project.ok("status", "--json")["next_actions"]
    assert any("aew migrate" in a for a in actions), actions
    for action in actions:
        _names_the_operator(action)


# ------------------------------------------------------------------ credentials


def test_acquire_only_when_vacant(project):
    res = project.aew("lead", "acquire", "--expect-rev", str(project.rev()))
    assert res.returncode == 4 and res.error["code"] == "PERMISSION_DENIED"
    # Register V2: the refusal names the holder and the way on when the holding session is gone.
    assert "aew lead takeover" in res.error["message"] and "interrupts nothing" in res.error["message"]
    details = res.error["details"]
    assert details["session_label"] == "lead-a" and details["active_invocations"] == []
    assert details["next"] == "aew lead takeover" and details["generation"] == 1


def test_a_refused_acquire_names_what_a_takeover_would_interrupt(tmp_path):
    from aewflow import assign, create_planned_ticket, sample_project

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    assign(p, wid)  # an implementer is active
    res = p.aew("lead", "acquire", "--expect-rev", str(p.rev()))
    details = res.error["details"]
    assert res.error["code"] == "PERMISSION_DENIED" and len(details["active_invocations"]) == 1
    assert f"interrupts the active invocation(s) {details['active_invocations'][0]}" in res.error["message"]
    assert details["interrupted_work"] == [wid] and "aew resume" in res.error["message"]


def test_a_refused_acquire_advises_reconcile_only_for_a_lease_the_takeover_leaves(tmp_path):
    """The advice follows the takeover's outcome (independent review of #78). An active integration verifier on a
    prepared candidate: the takeover interrupts the Ticket, which retires its entry and lease, so there is nothing to
    reconcile. A validated candidate with no active role invocation: the lease survives its dead custodian and is
    reconciled."""
    from aewflow import prepare_and_validate, sample_project, to_commit_ready

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    res = p.aew("lead", "acquire", "--expect-rev", str(p.rev()))
    assert res.error["details"]["interrupted_work"] == [wid], res.error
    assert "integrate reconcile" not in res.error["message"] and "aew resume" in res.error["message"]

    q = sample_project(tmp_path / "validated")
    wid2, _ = to_commit_ready(q, tmp_path / "validated")
    prepare_and_validate(q, wid2)
    res = q.aew("lead", "acquire", "--expect-rev", str(q.rev()))
    assert res.error["details"]["interrupted_work"] == [] and res.error["details"]["active_invocations"] == []
    assert f"`aew integrate reconcile {wid2}`" in res.error["message"], res.error


def test_token_issued_in_one_process_verified_in_another(project):
    # project.token came from a separate `aew lead acquire` process; this is another process.
    cands = project.ok("authority", "list")["candidates"]
    project.lead("authority", "reject", cands[0]["id"])


@pytest.mark.parametrize("mangle", ["tamper", "malformed", "empty-secret"])
def test_forged_credentials_rejected(project, mangle):
    token = project.token
    if mangle == "tamper":
        token = token[:-1] + ("A" if token[-1] != "A" else "B")
    elif mangle == "malformed":
        token = "lead-token-please"
    else:
        token = token.rsplit(".", 1)[0] + "."
    before = control_bytes(project)
    res = project.aew("manifest", "adopt", "--reason", "x", "--token", token, "--expect-rev", str(project.rev()))
    assert res.returncode == 4 and res.error["code"] == "PERMISSION_DENIED"
    assert control_bytes(project) == before


def test_no_raw_secret_is_ever_written(project):
    secret = project.token.rsplit(".", 1)[1]
    offer = project.lead("lead", "handoff", "offer")["offer"]
    text = all_files_text(project.root) + all_files_text(project.root.parent)
    assert secret not in text
    assert offer.rsplit(".", 1)[1] not in text
    # ...while durable verifiers exist so separate processes can verify.
    assert "verifier:" in (project.root / ".aew/state/control.yaml").read_text()


# ------------------------------------------------------------------ handoff & stale writers (AT-4b)


@pytest.mark.acceptance("AT-4b")
def test_superseded_lead_rejected_after_handoff(project):
    old = project.token
    offer = project.lead("lead", "handoff", "offer")["offer"]
    accepted = project.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(project.rev()),
                          "--session-label", "lead-b")
    new = accepted["token"]
    assert accepted["generation"] == 2

    before = control_bytes(project)
    res = project.aew("manifest", "adopt", "--reason", "x", "--token", old, "--expect-rev", str(project.rev()))
    assert res.returncode == 3 and res.error["code"] == "STALE_AUTHORITY"
    res = project.aew("manifest", "adopt", "--reason", "x", "--token", new, "--expect-rev", str(project.rev() - 1))
    assert res.returncode == 3 and res.error["code"] == "STALE_REVISION"
    assert control_bytes(project) == before

    decision = accepted["decision"]
    assert "authority_transfer" in (project.root / f".aew/decisions/{decision}.md").read_text()
    assert (project.root / ".aew/state/HANDOFF.md").exists()


def test_pending_handoff_freezes_outgoing_lead(project):
    project.lead("lead", "handoff", "offer")
    cands = project.ok("authority", "list")["candidates"]
    res = project.aew("authority", "reject", cands[0]["id"], "--token", project.token,
                      "--expect-rev", str(project.rev()))
    assert res.returncode == 4
    project.lead("lead", "handoff", "cancel")
    project.lead("authority", "reject", cands[0]["id"])


@pytest.mark.acceptance("AT-4b")
def test_takeover_cannot_be_self_authorized(project):
    rev = project.rev()
    before = control_bytes(project)
    attempts = [
        (["--reason", "lead lost"], None, None),
        (["--reason", "lead lost"], {"AEW_OPERATOR_CONFIRMED": "1", "AEW_OPERATOR": "yes"}, "yes\ny\n"),
        (["--reason", "lead lost", "--operator-confirmed"], None, None),
        (["--reason", "lead lost", "--yes"], None, "yes\n"),
    ]
    for extra, env, stdin in attempts:
        res = project.aew("lead", "takeover", "--expect-rev", str(rev), *extra, env=env, input=stdin)
        assert res.returncode != 0
        code = json.loads(res.stderr)["error"]["code"] if res.stderr.startswith("{") else "USAGE"
        assert code in {"OPERATOR_AUTHORIZATION_REQUIRED", "USAGE"}, res.stderr
    assert control_bytes(project) == before
    assert project.ok("lead", "show")["generation"] == 1


def pty_takeover_token(root: Path, rev: int, label: str) -> str:
    """A takeover at a real terminal; the new Lead credential, read from the terminal it was written to."""
    result, screen = _pty_takeover(root, rev, label)
    written = re.search(r"^token: (aew1\.\S+)$", screen, re.M)
    assert result["token"] == "(written to your terminal)" and written, screen
    return written.group(1)


def _pty_takeover(root: Path, rev: int, label: str) -> tuple[dict, str]:
    import pty
    import select

    argv = [sys.executable, "-m", "aew", "-C", str(root), "lead", "takeover", "--expect-rev", str(rev),
            "--reason", "Lead session lost", "--session-label", label]
    pid, fd = pty.fork()
    if pid == 0:  # child: controlling terminal is the pty slave
        os.execvpe(argv[0], argv, clean_env())  # noqa: S606 (argv is fixed above)
    buf = b""
    answered = False
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 1.0)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if not answered:
            match = re.search(rb"confirmation code ([0-9A-F]{6})", buf)
            if match:
                os.write(fd, match.group(1) + b"\n")  # the operator reads the screen and types
                answered = True
    _, status = os.waitpid(pid, 0)
    text = buf.decode("utf-8", "replace").replace("\r\n", "\n")
    assert os.waitstatus_to_exitcode(status) == 0, text
    return json.loads(text[text.index("{", text.index("> ")):]), text


@pytest.mark.acceptance("AT-4b")
@pytest.mark.serial  # a real pseudo-terminal and a forked child answering within a deadline
@pytest.mark.skipif(
    IS_WINDOWS,
    reason="POSIX pty operator path. A Windows console session would appear on the developer desktop, so on "
           "Windows the refusal path is tested here and AT-1 substitutes the terminal channel in-process",
)
def test_operator_authorized_takeover_supersedes_everyone(project):
    a_token = project.token
    offer = project.lead("lead", "handoff", "offer")["offer"]
    b_token = project.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(project.rev()))["token"]
    rev = project.rev()
    result, screen = _pty_takeover(project.root, rev, "lead-c")
    assert result["generation"] == 3
    # The prompt names who asked and where the credential goes; the credential reaches the terminal, not stdout.
    assert "requested by" in screen and "credential to  : this terminal only" in screen
    assert result["token"] == "(written to your terminal)"
    written = re.search(r"^token: (aew1\.\S+)$", screen, re.M)
    assert written, screen
    c_token = written.group(1)
    for stale in (a_token, b_token):
        res = project.aew("manifest", "adopt", "--reason", "x", "--token", stale, "--expect-rev", str(project.rev()))
        assert res.error["code"] == "STALE_AUTHORITY"
    decision = (project.root / f".aew/decisions/{result['decision']}.md").read_text()
    assert "operator-tty" in decision and "Lead session lost" in decision
    cands = project.ok("authority", "list")["candidates"]
    project.token = c_token
    project.lead("authority", "reject", cands[0]["id"])


@pytest.mark.acceptance("AT-7")
def test_worktree_copy_of_aew_is_not_an_authority(project, tmp_path):
    git("add", "-A", ".aew", cwd=project.root)
    git("commit", "-q", "-m", "commit aew state", cwd=project.root)
    wt = tmp_path / "rogue-worktree"
    git("worktree", "add", "-q", str(wt), "HEAD", cwd=project.root)
    res = run_aew("-C", str(wt), "status", "--json")
    assert res.returncode == 6 and res.error["code"] == "WORKSPACE_NOT_AUTHORITY"
