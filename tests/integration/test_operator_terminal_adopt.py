"""Settings adopted, and authority decided, at the operator's own terminal with no Lead credential (register E331).

The terminal is substituted in-process (``operator.ask``, ``operator.has_terminal``), as the takeover tests do; the
register of weaker contexts through its one reader, ``g3standing.no_weaker_context``.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from conftest import Project
from invariants import assert_control_invariants, load_control

from aew import g3standing, operator, operator_adopt, process_kind
from aew.cli.main import main
from aew.engine import pinned_copies
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.errors import ChangedSinceRead, IllegalTransition, PermissionDenied, StalePolicy
from aew.util import read_yaml, sha256_bytes

WEAKER = "a weaker agent context is live on this host: lead_opencode W-0001 in elsewhere (running)"
ZERO = "0" * 64


class Terminal:
    """The operator's terminal: each prompt kept, each answer given by ``answer(prompt)``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answer: Any = "yes") -> None:
        self.prompts: list[str] = []
        self.answer = answer
        monkeypatch.setattr(operator, "has_terminal", lambda: True)
        monkeypatch.setattr(operator, "discard_typed_ahead", lambda: None)
        monkeypatch.setattr(operator, "ask", self.ask)

    def ask(self, prompt: str, **_: Any) -> str:
        self.prompts.append(prompt)
        return self.answer(prompt) if callable(self.answer) else self.answer


def typed_code(prompt: str) -> str:
    return re.search(r"confirmation code ([0-9A-F]{6})", prompt)[1]


@pytest.fixture
def clear(monkeypatch):
    """The register of weaker contexts is clear on this host, and no Lead credential is in the operator's shell."""
    monkeypatch.setattr(g3standing, "no_weaker_context", lambda now=None: None)
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)


def cli(project: Project, capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, Any]:
    capsys.readouterr()
    assert main(["-C", str(project.root), *argv]) in (0, None)
    return json.loads(capsys.readouterr().out)


def control_bytes(p: Project) -> bytes:
    return (p.root / ".aew/state/control.yaml").read_bytes()


def edit_gates(p: Project, line: str) -> bytes:
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_bytes(gates.read_bytes() + line.encode("utf-8") + b"\n")
    return gates.read_bytes()


def decision(p: Project, did: str) -> dict[str, Any]:
    import yaml

    return yaml.safe_load((p.root / f".aew/decisions/{did}.md").read_text(encoding="utf-8").split("---", 2)[1])


def assert_the_operators_own(p: Project, did: str, confirmation: str) -> None:
    by = decision(p, did)["decided_by"]
    assert by["kind"] == "operator" and by["authorized_by"] == "operator-tty" and by["confirmation"] == confirmation
    assert not {"generation", "session_label", "recorded_by_lead"} & by.keys(), by  # no Lead actor
    actor = load_control(p.root)["last_transition"]["actor"]
    assert actor == {"kind": "operator", "authorized_by": "operator-tty", "confirmation": confirmation}, actor


def test_the_operator_adopts_a_settings_edit_with_no_lead_credential_and_the_lead_keeps_its_seat(
        project, monkeypatch, capsys, clear):
    p = project
    seat = Engine.discover(p.root).lead_show()
    raw = edit_gates(p, "# reviewed by the operator")
    terminal = Terminal(monkeypatch)
    out = cli(p, capsys, "manifest", "adopt", "--reason", "loosened nothing")
    [prompt] = terminal.prompts
    assert "ADOPT as YOUR decision" in prompt and "+# reviewed by the operator" in prompt
    assert f"now    : {sha256_bytes(raw)}" in prompt and "Type yes and press Enter" in prompt
    assert "typed-back code" not in prompt and operator_adopt.SEAT_LINE in " ".join(prompt.split("\n"))
    assert out["adopted"] == ["policy/gates.yaml"]
    assert_the_operators_own(p, out["decision"], "plain")
    after = Engine.discover(p.root).lead_show()
    assert (after["status"], after["generation"]) == (seat["status"], seat["generation"])
    p.lead("checkpoint", "--next", "the Lead goes on")  # its credential still holds the seat
    assert_control_invariants(p)


def test_a_weaker_context_on_this_host_asks_the_typed_back_code_naming_the_weaker_run(project, monkeypatch, capsys):
    p = project
    monkeypatch.setattr(g3standing, "no_weaker_context", lambda now=None: (WEAKER, "end it"))
    edit_gates(p, "# reviewed")
    before = control_bytes(p)
    plain = Terminal(monkeypatch, "yes")
    assert main(["-C", str(p.root), "manifest", "adopt", "--reason", "r"]) == PermissionDenied.exit_code
    assert WEAKER in plain.prompts[0] and control_bytes(p) == before  # a plain yes is no code
    terminal = Terminal(monkeypatch, typed_code)
    out = cli(p, capsys, "manifest", "adopt", "--reason", "r")
    assert f"A typed-back code is asked because {WEAKER}." in " ".join(terminal.prompts[0].split("\n"))
    assert_the_operators_own(p, out["decision"], "code")


def test_a_file_changed_after_its_diff_was_shown_commits_nothing(project, monkeypatch, clear):
    p = project
    edit_gates(p, "# shown")

    def edit_then_yes(_prompt: str) -> str:
        edit_gates(p, "# not shown")
        return "yes"

    before = control_bytes(p)
    Terminal(monkeypatch, edit_then_yes)
    with pytest.raises(ChangedSinceRead):
        operator_adopt.adopt(Engine.discover(p.root), reason="r")
    assert control_bytes(p) == before


@pytest.mark.parametrize(("where", "code", "reason"), [
    ("lead_session", "PERMISSION_DENIED", "aew_session"),
    ("worker_run", "PERMISSION_DENIED", "aew_session"),
    ("non_writer", "PERMISSION_DENIED", "non_writer_process"),
    ("no_terminal", "OPERATOR_AUTHORIZATION_REQUIRED", "no_terminal"),
])
@pytest.mark.parametrize("argv", [("manifest", "adopt", "--reason", "r"),
                                  ("authority", "accept", "C-001", "--class", "orientation"),
                                  ("authority", "reject", "C-001")])
def test_an_operator_terminal_decision_is_refused_in_a_session_a_non_writer_or_without_a_terminal(
        project, monkeypatch, capsys, clear, where, code, reason, argv):
    p = project
    edit_gates(p, "# edited")
    terminal = Terminal(monkeypatch)
    if where == "lead_session":
        monkeypatch.setenv("AEW_LEAD_BROKER", "synthetic")
    elif where == "worker_run":
        monkeypatch.setenv("AEW_INVOCATION_TOKEN", "synthetic")
    elif where == "non_writer":
        monkeypatch.setattr(process_kind, "kind", lambda: process_kind.NON_WRITER)
    else:
        monkeypatch.setattr(operator, "has_terminal", lambda: False)
    before = control_bytes(p)
    refusal = operator_adopt.problem(f"aew {' '.join(argv[:2])}")
    assert refusal is not None and refusal.code == code and refusal.details["reason"] == reason
    assert "nothing is changed" in refusal.message and ("Run it yourself" in refusal.message)
    with pytest.raises(PermissionDenied) as raised:
        if argv[0] == "manifest":
            operator_adopt.adopt(Engine.discover(p.root), reason="r")
        else:
            operator_adopt.decide_authority(Engine.discover(p.root), action=argv[1], candidate=_candidate(p),
                                            klass="orientation")
    assert raised.value.code == code
    assert terminal.prompts == [] and control_bytes(p) == before


def _candidate(p: Project) -> str:
    return next(c["id"] for c in Engine.discover(p.root).authority_list()["candidates"] if c["status"] == "proposed")


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_the_operator_decides_authority_with_no_lead_credential_and_the_record_names_no_lead(
        project, monkeypatch, capsys, clear, action):
    p = project
    candidate = _candidate(p)
    shown = Engine.discover(p.root).authority_candidate(candidate)
    seat = Engine.discover(p.root).lead_show()["generation"]
    terminal = Terminal(monkeypatch)
    extra = ("--class", "orientation") if action == "accept" else ("--reason", "orientation only")
    out = cli(p, capsys, "authority", action, candidate, *extra)
    assert f"SHA-256 {shown['digest']}" in terminal.prompts[0]
    assert_the_operators_own(p, out["decision"], "plain")
    status = {c["id"]: c["status"] for c in Engine.discover(p.root).authority_list()["candidates"]}
    assert status[candidate] == ("accepted" if action == "accept" else "rejected")
    assert Engine.discover(p.root).lead_show()["generation"] == seat


def test_a_lead_decision_still_takes_the_lead_credential_and_the_engine_refuses_one_without(project):
    with pytest.raises(Exception) as refused:
        Engine.discover(project.root).authority_accept(candidate_id=_candidate(project), klass="orientation",
                                                       decided_by="lead")
    assert getattr(refused.value, "details", {}).get("reason") == "lead_credential_required"


def test_a_running_leads_next_step_bound_to_the_old_settings_meets_stale_policy(project, monkeypatch, clear):
    p = project
    e = Engine.discover(p.root)
    si = e.stage_open(token=p.token, tool="probe", contract_digest=ZERO, arguments={"why": "a test"},
                      judgment_inputs=[], base_class="MECHANICAL", effective_class="MECHANICAL",
                      plan=[{"primitive": "checkpoint"}] * 2, subject=None, ingress="test")["intent"]
    with SI.step(si, 1):
        e.checkpoint(token=p.token, note="step 1")
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(gates.read_text(encoding="utf-8") + "mutating_concurrency: 7\n", encoding="utf-8", newline="\n")
    Terminal(monkeypatch)
    operator_adopt.adopt(Engine.discover(p.root), reason="a legality setting")
    with pytest.raises(StalePolicy), SI.step(si, 2):
        Engine.discover(p.root).checkpoint(token=p.token, note="step 2")
    assert Engine.discover(p.root).lead_show()["status"] == "active"  # the seat is the Lead's still
    assert_control_invariants(p)


def test_the_diff_shown_is_against_the_adopted_bytes_and_an_edited_copy_is_never_shown(project, monkeypatch, clear):
    p = project
    edit_gates(p, "# first")
    Terminal(monkeypatch)
    operator_adopt.adopt(Engine.discover(p.root), reason="first")
    pinned = load_control(p.root)["policy_sha256"]["policy/gates.yaml"]
    kept = p.root / ".aew" / pinned_copies.DIR / pinned
    assert sha256_bytes(kept.read_bytes()) == pinned
    edit_gates(p, "# second")
    terminal = Terminal(monkeypatch, "no")
    with pytest.raises(PermissionDenied):
        operator_adopt.adopt(Engine.discover(p.root), reason="second")
    shown = terminal.prompts[0]
    assert "+# second" in shown and "+# first" not in shown and " # first" in shown  # only the change since the pin
    kept.write_bytes(b"forged: not the pinned version\n")
    assert pinned_copies._kept(p.root / ".aew", pinned) is None  # named by its digest, read back only if it matches
    terminal = Terminal(monkeypatch, "no")
    with pytest.raises(PermissionDenied):
        operator_adopt.adopt(Engine.discover(p.root), reason="second")
    assert "forged" not in terminal.prompts[0]


def test_a_command_that_writes_its_own_change_adopts_exactly_it_and_leaves_nothing_on_a_refusal(
        project, monkeypatch, clear):
    """The hook E164's commands adopt through: the bytes are written only once confirmed, adopted as `only`, and a
    refused confirmation or another drifted file leaves every file as it was."""
    p = project
    gates = p.root / ".aew/policy/gates.yaml"
    original = gates.read_bytes()
    new = original + b"# written by the command\n"
    Terminal(monkeypatch, "no")
    with pytest.raises(PermissionDenied):
        operator_adopt.adopt(Engine.discover(p.root), reason="r", command="aew policy route",
                             edits={"policy/gates.yaml": new}, lines=["  route  : a test"])
    assert gates.read_bytes() == original
    checks = p.root / ".aew/policy/checks.yaml"
    checks.write_bytes(checks.read_bytes() + b"# drifted\n")
    with pytest.raises(IllegalTransition) as refused:
        operator_adopt.adopt(Engine.discover(p.root), reason="r", command="aew policy route",
                             edits={"policy/gates.yaml": new})
    assert refused.value.details["reason"] == "other_files_changed" and gates.read_bytes() == original
    checks.write_bytes(checks.read_bytes().removesuffix(b"# drifted\n"))
    terminal = Terminal(monkeypatch)
    out = operator_adopt.adopt(Engine.discover(p.root), reason="r", command="aew policy route",
                               edits={"policy/gates.yaml": new}, lines=["  route  : a test"])
    assert "route  : a test" in terminal.prompts[0] and "+# written by the command" in terminal.prompts[0]
    assert out["adopted"] == ["policy/gates.yaml"] and gates.read_bytes() == new
    assert read_yaml(p.root / ".aew/policy/gates.yaml") is not None


# ---------------------------------------------------------------------------------------------- review of #641


def test_a_missing_copy_falls_back_to_the_committed_bytes_and_with_neither_the_file_is_shown_whole(
        project, monkeypatch, clear):
    """Point 2: the pinned bytes come from the file's git history when no kept copy holds them; with neither, the
    prompt says so and shows the file whole, never other bytes as the pinned version."""
    from conftest import git

    p = project
    git("add", "-A", cwd=p.root)
    git("commit", "-q", "-m", "the pinned settings", cwd=p.root)
    pinned = load_control(p.root)["policy_sha256"]["policy/gates.yaml"]
    assert sha256_bytes((p.root / ".aew/policy/gates.yaml").read_bytes()) == pinned  # the commit holds the pin
    (p.root / ".aew" / pinned_copies.DIR / pinned).unlink(missing_ok=True)
    edit_gates(p, "# after the commit")
    terminal = Terminal(monkeypatch, "no")
    with pytest.raises(PermissionDenied):
        operator_adopt.adopt(Engine.discover(p.root), reason="r")
    shown = terminal.prompts[0]
    assert "+# after the commit" in shown and "not on this host" not in shown
    added = [line for line in shown.splitlines() if line.startswith("    +") and not line.startswith("    +++")]
    assert added == ["    +# after the commit"]  # a diff against the committed bytes, not the file whole
    Terminal(monkeypatch)
    operator_adopt.adopt(Engine.discover(p.root), reason="r")  # a new pin, its bytes in no commit
    pinned = load_control(p.root)["policy_sha256"]["policy/gates.yaml"]
    (p.root / ".aew" / pinned_copies.DIR / pinned).unlink()
    edit_gates(p, "# with neither")
    terminal = Terminal(monkeypatch, "no")
    with pytest.raises(PermissionDenied):
        operator_adopt.adopt(Engine.discover(p.root), reason="r")
    shown = " ".join(terminal.prompts[0].split())
    assert "the pinned version's bytes are not on this host" in shown and "the file is shown whole" in shown
    assert "+# after the commit" in shown and "+# with neither" in shown  # whole: every line is shown as added


def test_the_hook_puts_its_files_back_when_the_adoption_fails_after_writing_them(project, monkeypatch, clear):
    """Point 3: the bytes are written once confirmed; the adoption then refuses them (they do not validate), and every
    file is back as it was, with nothing committed."""
    p = project
    gates = p.root / ".aew/policy/gates.yaml"
    original = gates.read_bytes()
    before = control_bytes(p)
    Terminal(monkeypatch)
    with pytest.raises(Exception) as refused:
        operator_adopt.adopt(Engine.discover(p.root), reason="r", command="aew policy route",
                             edits={"policy/gates.yaml": b"mutating_concurrency: not a number\n"})
    assert getattr(refused.value, "code", None) == "VALIDATION_FAILED", refused.value
    assert gates.read_bytes() == original and control_bytes(p) == before


def test_the_hook_refuses_a_project_whose_files_were_never_pinned_and_says_so(project, monkeypatch, clear):
    """Point 8: nothing to diff against, and `only=` never makes a first pin: the refusal says the files were never
    pinned, and what pins them."""
    from aew.engine.store import serialize_control

    p = project
    state = load_control(p.root)
    del state["policy_sha256"]
    (p.root / ".aew/state/control.yaml").write_bytes(serialize_control(state))
    gates = p.root / ".aew/policy/gates.yaml"
    original = gates.read_bytes()
    terminal = Terminal(monkeypatch)
    with pytest.raises(IllegalTransition) as refused:
        operator_adopt.adopt(Engine.discover(p.root), reason="r", command="aew policy route",
                             edits={"policy/gates.yaml": original + b"# x\n"})
    assert refused.value.details["reason"] == "never_pinned" and "never pinned" in refused.value.message
    assert "aew manifest adopt --reason <reason>" in refused.value.message
    assert terminal.prompts == [] and gates.read_bytes() == original


def test_the_operators_transaction_admits_only_the_operators_confirmation_and_its_own_family(project):
    """Point 4: `operator_txn` itself refuses no authorization and one that is not the operator's terminal, and any op
    outside its closed family, committing nothing."""
    from aew.engine.authority import OPERATOR_OPS
    from aew.errors import OperatorAuthorizationRequired

    p = project
    k = Engine.discover(p.root)._k
    before = control_bytes(p)
    for authorization in (None, {"authorized_by": "lead"}, {}):
        with pytest.raises(OperatorAuthorizationRequired), k.operator_txn(authorization, "manifest.adopt"):
            pytest.fail("admitted")
    with pytest.raises(PermissionDenied) as refused, k.operator_txn({"authorized_by": "operator-tty"}, "checkpoint"):
        pytest.fail("admitted")
    assert refused.value.details["reason"] == "not_operator_op" and refused.value.code == "PERMISSION_DENIED"
    assert control_bytes(p) == before and OPERATOR_OPS == {"manifest.adopt", "authority.accept", "authority.reject"}


@pytest.mark.parametrize(("weaker", "answer", "says"), [
    (None, "no", "type yes to confirm"),
    ((WEAKER, "end it"), "no", "type back the code it shows"),
])
def test_a_refused_confirmation_says_nothing_changed_and_how_to_try_again(project, monkeypatch, weaker, answer, says):
    """Point 6: both forms' refusals say what happened, that nothing changed, and what to do."""
    p = project
    monkeypatch.setattr(g3standing, "no_weaker_context", lambda now=None: weaker)
    edit_gates(p, "# edited")
    before = control_bytes(p)
    Terminal(monkeypatch, answer)
    with pytest.raises(PermissionDenied) as refused:
        operator_adopt.adopt(Engine.discover(p.root), reason="r")
    assert refused.value.details["reason"] == "not_confirmed"
    assert "nothing is changed" in refused.value.message and says in refused.value.message
    assert control_bytes(p) == before


def test_the_plain_prompt_warns_about_the_answer_and_the_code_prompt_about_the_code(project, monkeypatch):
    """Point 7: the plain form has no code to give away, so its warning is about who answers."""
    p = project
    edit_gates(p, "# edited")
    for weaker, shown, absent in ((None, operator.PLAIN_WARNING, operator.RELAY_WARNING),
                                  ((WEAKER, "end it"), operator.RELAY_WARNING, operator.PLAIN_WARNING)):
        monkeypatch.setattr(g3standing, "no_weaker_context", lambda now=None, w=weaker: w)
        terminal = Terminal(monkeypatch, "no")
        with pytest.raises(PermissionDenied):
            operator_adopt.adopt(Engine.discover(p.root), reason="r")
        assert shown in terminal.prompts[0] and absent not in terminal.prompts[0]


def test_authority_decisions_follow_the_register_until_the_operator_rules_otherwise(project, monkeypatch, clear):
    """Point 1 awaits the operator: today the register decides for authority decisions too. The ruling is the one
    constant, and setting it asks the code whatever the register says."""
    p = project
    assert operator_adopt.AUTHORITY_CODE_ALWAYS is None
    monkeypatch.setattr(operator_adopt, "AUTHORITY_CODE_ALWAYS", "an authority decision always takes the code")
    terminal = Terminal(monkeypatch, typed_code)
    operator_adopt.decide_authority(Engine.discover(p.root), action="reject", candidate=_candidate(p))
    assert "A typed-back code is asked because an authority decision always takes the code." in " ".join(
        terminal.prompts[0].split("\n"))
