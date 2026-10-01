"""M3 step 9: defects the dogfood found (a real model Lead acting on AEW's own guidance). Permanent regressions.

M3-D8. AEW's next actions sent a Lead after harness runs the wrong way:

- for a run that ended with evidence it always said "ingest it", but an implementer's report is never ingested (a
  model Lead tried ``aew evidence ingest`` and ``aew review ingest`` on it before finding the transition);
- an ASSIGNED Ticket whose implementer was already launched (``--launch``) still said "launch the implementer from
  its pack";
- a RUNNING Ticket said "advance to REVIEW_PENDING" whatever its gates are (a Class 0 Ticket goes to COMMIT_READY).

Now each next action names the command that applies, and following it is legal.

M3-D9. Two model Leads (a free model and GPT-5.6 Luna) gave a Ticket's scope as one comma-separated value
(``--scope "ledger/money.py,tests/test_money.py"``). AEW stored it as a single glob that matches no path, so the
implementer's correct change was out of scope and the Lead cancelled and recreated the Ticket. A scope glob with a
comma is now refused at creation, saying to repeat ``--scope``.

M3-D10. Inside a Lead session (``aew opencode``, or the dogfood's headless Lead), ``aew resume`` told the Lead that
"this session must not act as Lead unless authority is transferred" (handoff or takeover): resume is read-only, runs
without the broker, and assumed the reader holds no authority. A GPT-5.6 Luna Lead believed it, wrote a checkpoint
asking the operator for a takeover, and stopped. Resume now asks the session's Lead broker, and says that this session
holds Lead authority, or that its broker no longer does. Outside a Lead session its guidance is unchanged.
"""

from __future__ import annotations

import json
import sys

import pytest

from aewflow import SUBTRACT_PATCH, create_planned_ticket, sample_project
from conftest import IS_WINDOWS, run_aew
from fake_harness import AGENT, IMPL_REPORT, HarnessLab, credential_hits
from invariants import assert_control_invariants

IMPLEMENT = [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
             {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]
REVIEW = {"claim": "independent review of the change against plan and contracts",
          "producer": {"model": "fake-model"},
          "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()
    assert not credential_hits(tmp_path)


def actions(lab, wid: str) -> list[str]:
    return [a for a in lab.ok("status", "--json")["next_actions"] if a.startswith(f"{wid}:")]


def says_ingest(action: str) -> bool:
    return "ingest it" in action or any(f"aew {c} ingest" in action for c in ("evidence", "review", "verify"))


@pytest.mark.parametrize("cls, after", [(0, "COMMIT_READY"), (1, "REVIEW_PENDING")])
def test_after_an_implementer_run_the_next_action_is_its_transition_never_an_ingest(lab, tmp_path, cls, after):
    wid = create_planned_ticket(lab.project, tmp_path, cls=cls)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    assert lab.wait("R-INV-0001-1")["status"] == "ended_with_evidence"

    assigned = actions(lab, wid)
    assert not any(says_ingest(a) or "from its pack" in a for a in assigned), assigned
    assert any(f"aew work transition {wid} --to RUNNING" in a for a in assigned), assigned
    lab.lead("work", "transition", wid, "--to", "RUNNING")

    running = actions(lab, wid)
    assert not any(says_ingest(a) for a in running), running
    assert any(f"aew work transition {wid} --to {after}" in a for a in running), running
    lab.lead("work", "transition", wid, "--to", after)  # the advice is a legal step
    assert_control_invariants(lab.project)


def test_a_scope_glob_with_a_comma_is_refused_saying_to_repeat_the_option(tmp_path):
    p = sample_project(tmp_path)
    rev = p.rev()
    ticket = ["work", "create", "ticket", "--title", "Fix negatives", "--class", "0", "--goal", "negatives print -$1"]
    res = p.aew(*ticket, "--scope", "calc/core.py,tests/test_core.py", "--token", p.token, "--expect-rev", str(rev))
    assert res.returncode != 0, res.stdout
    message = res.error["message"]
    assert "calc/core.py,tests/test_core.py" in message and "repeat --scope" in message, message
    assert p.rev() == rev  # nothing was created
    wid = p.lead(*ticket, "--scope", "calc/core.py", "--scope", "tests/test_core.py")["id"]
    assert p.ok("work", "show", wid)["control"]["kind"] == "ticket"


def test_resume_inside_a_lead_session_says_this_session_holds_lead_authority(tmp_path):
    p = sample_project(tmp_path)
    script, transcript = tmp_path / "lead-script.json", tmp_path / "lead.jsonl"
    script.write_text(json.dumps([{"do": "aew", "args": ["resume", "--json"]}]), encoding="utf-8")
    res = run_aew("-C", str(p.root), "lead", "session", "--", sys.executable, str(AGENT), "--script", str(script),
                  "--transcript", str(transcript), env={"AEW_LEAD_TOKEN": p.token}, timeout=300)
    assert res.returncode == 0, res.stderr
    [step] = [json.loads(line)["result"] for line in transcript.read_text(encoding="utf-8").splitlines()]
    inside = json.loads(step["stdout"])
    assert inside["lead"]["holder_reachable"] == "this_session"
    assert inside["authority_guidance"].startswith("This session holds Lead authority"), inside["authority_guidance"]
    assert "must not act as Lead" not in inside["authority_guidance"]

    outside = p.ok("resume", "--json")  # no Lead session: the guidance for a fresh reader is unchanged
    assert outside["lead"]["holder_reachable"] == "unknown" and "must not act as Lead" in outside["authority_guidance"]


def test_resume_in_a_lead_session_whose_broker_is_gone_says_it_holds_no_authority(tmp_path):
    p = sample_project(tmp_path)
    gone = r"\\.\pipe\aew-lead-broker-gone" if IS_WINDOWS else str(tmp_path / "gone.sock")
    report = p.ok("resume", "--json", env={"AEW_LEAD_BROKER": gone, "AEW_LEAD_BROKER_KEY": "00" * 32})
    assert report["lead"]["holder_reachable"] == "no"
    assert report["authority_guidance"].startswith("This session's Lead broker does not hold Lead authority")
    assert "must not act as Lead" in report["authority_guidance"]


def test_every_run_states_its_real_containment_and_nothing_claims_more(lab, tmp_path):
    """Companion review B2 (AEW-INV-ISO-001, FALSE_CONTAINMENT_CLAIM): until AEW has OS-level containment, run
    metadata and operator status say `workdir_separation_only`, so its absence is never read as containment."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    lab.wait("R-INV-0001-1")
    assert lab.record("R-INV-0001-1")["containment"] == "workdir_separation_only"
    [run] = lab.ok("harness", "status")["runs"]
    assert run["containment"] == "workdir_separation_only"
    doctor = {c["check"]: c for c in lab.ok("doctor", "--json")["checks"]}
    assert doctor["containment"]["status"] == "WARN"
    assert doctor["containment"]["detail"].startswith("workdir separation only")
    assert "no OS-level filesystem containment" in doctor["containment"]["detail"]


def test_after_a_reviewer_run_the_next_action_names_the_review_ingest(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    lab.wait("R-INV-0001-1")
    lab.lead("work", "transition", wid, "--to", "RUNNING")
    lab.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    lab.script("R-INV-0002-1", [{"do": "submit", "kind": "review", "meta": REVIEW}])
    lab.lead("invoke", "create", wid, "--role", "reviewer", "--launch")
    assert lab.wait("R-INV-0002-1")["status"] == "ended_with_evidence"

    review = [a for a in actions(lab, wid) if "R-INV-0002-1" in a]
    assert review and all(f"aew review ingest {wid} --evidence INV-0002-" in a for a in review), review
    evidence = review[0].split("--evidence ")[1].split("`")[0]
    lab.lead("review", "ingest", wid, "--evidence", evidence)  # the advice is a legal step
    assert lab.ok("work", "show", wid)["control"]["state"] == "REVIEW_PASSED"


def _refusal(p, *args, stdin=None) -> str:
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()), input=stdin)
    assert res.returncode != 0, res.stdout
    return res.error["message"]


def test_a_refusal_names_the_command_that_applies_instead(tmp_path):
    """M3 audit X1, from the dogfood (§6.3): most Leads made one to three calls that a refusal then corrected, and
    each correction cost a model step, because the refusal said what was wrong and never what to do instead:
    `evidence ingest` or `work dispatch` on a mutating Ticket, `work assign` or `review ingest` in the wrong state,
    and a mistyped `--fields` key (`goals:`)."""
    from aewflow import assign

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    assert f"aew work assign {wid} --launch" in _refusal(p, "work", "dispatch", wid)
    assign(p, wid)
    assert f"aew work transition {wid} --to REVIEW_PENDING" in _refusal(p, "evidence", "ingest", wid,
                                                                         "--evidence", "INV-0001-impl-1")
    assert "aew work transition <T> --to REVIEW_PENDING" in _refusal(p, "work", "assign", wid)
    assert f"aew work transition {wid} --to REVIEW_PENDING" in _refusal(p, "review", "ingest", wid,
                                                                         "--evidence", "INV-0001-impl-1")
    assert "did you mean --goal?" in _refusal(p, "work", "create", "ticket", "--class", "1", "--fields", "-",
                                              stdin="title: 'x'\ngoals: ['y']\n")


def test_next_actions_give_commands_a_lead_can_run(repo, tmp_path):
    """M3 audit X2, from the dogfood: 37 `--help` lookups in 29 Lead sessions, 20 of them `aew authority --help`,
    because `resume` named commands without their arguments (`aew authority list`, then accept/reject;
    `aew plan propose/accept`; `aew work assign`). Each next action now gives a command with its unit id, its required
    options and `--expect-rev N` (placeholders in <...>)."""
    from conftest import Project

    from aewflow import create_unit

    fresh = Project(repo)
    fresh.ok("init")
    actions = "\n".join(fresh.ok("resume", "--json")["next_actions"])
    assert "aew authority accept <candidate> --class <" in actions and "--expect-rev N" in actions, actions

    p = sample_project(tmp_path / "sample")  # `repo` above is tmp_path/repo
    wid = p.lead("work", "create", "ticket", "--title", "t", "--class", "1", "--goal", "g", "--scope", "calc/**")["id"]
    story = create_unit(p, "story", "s")
    actions = "\n".join(p.ok("resume", "--json")["next_actions"])
    assert f"aew plan propose {wid} --file - --assurance none|--review <card>|--verify <card> --expect-rev N"         in actions, actions
    assert f"aew plan accept {wid} --revision <n> --expect-rev N" in actions, actions
    assert f"aew work create ticket --parent {story}" in actions, actions
    plan = tmp_path / "plan.md"
    plan.write_text("Do it.\n", encoding="utf-8")
    p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan))
    p.lead("plan", "accept", wid, "--revision", "1")
    actions = "\n".join(p.ok("resume", "--json")["next_actions"])
    assert f"aew work assign {wid} --launch --expect-rev N" in actions, actions


class _PromptServer:
    """Just enough of a V2 server to take a prompt."""

    def __init__(self) -> None:
        self.posts: list[tuple[str, dict]] = []

    def alive(self) -> bool:
        return True

    def post(self, path, body=None, params=None, **_):
        self.posts.append((path, body))
        return {"data": {"id": (body or {}).get("id")}}


def test_the_headless_lead_takes_a_new_turn_after_its_last_one_ended(tmp_path, monkeypatch):
    """Rubric A5, a defect of the dogfood driver: its headless Lead is one session of several turns (a nudge, and
    since A5 a debrief, starts a new turn after the last one ended), and its `say` restarts the turn monitor itself.
    Audit I3 made the adapter refuse a message to an ended turn, which is right for a role run, where nothing would
    watch it. Here it made every nudge and debrief raise instead: the debrief of all six A5 runs was never asked."""
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "eval" / "m3" / "dogfood"))
    import headless

    session = headless.HeadlessSession(tmp_path / "lead")
    try:
        server = _PromptServer()
        session.server = session.client = server
        session.session, session.sent, session.turn = "ses_1", ["msg_first"], "ended"
        monkeypatch.setattr(session, "_watch", lambda: None)  # the monitor is not under test
        session.say("One last question.")
        assert [path for path, _ in server.posts] == ["/api/session/ses_1/prompt"]
        assert session.turn == "running" and len(session.sent) == 2
    finally:
        session.tree.close()


class _SavedSessionServer(_PromptServer):
    """A server that has a saved session: it can be read, and given a shell environment."""

    def __init__(self, session: str) -> None:
        super().__init__()
        self.session, self.puts = session, []

    def get(self, path, params=None, **_):
        if path == f"/api/session/{self.session}":
            return {"data": {"id": self.session}}
        raise AssertionError(f"unexpected GET {path}")

    def put(self, path, body=None, **_):
        self.puts.append((path, body))
        return {"data": {}}


def test_a_saved_headless_session_is_reopened_with_its_shell_environment_curated_again(tmp_path, monkeypatch):
    """Rubric A6 reopens each finished Lead's saved session to ask it the debrief. A session's shell environment
    lives only in the server's memory, so a reopened session would give its shell the new server's own environment,
    which holds the provider key. `resume` must set the curated one again, and create nothing."""
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "eval" / "m3" / "dogfood"))
    import headless

    session = headless.HeadlessSession(tmp_path / "lead")
    server = _SavedSessionServer("ses_saved")

    def start(**_):
        session.server = session.client = server
        session.state_dir = tmp_path / "lead" / "harness"

    class NoEvents:
        def __init__(self, *_):
            pass

        def start(self):
            pass

    monkeypatch.setattr(session, "_start", start)
    monkeypatch.setattr(headless, "EventStream", NoEvents)
    try:
        session.resume(session="ses_saved", directory=tmp_path, config={}, provider_env=["OPENAI_API_KEY"],
                       profile={"provider": "openai", "model": "gpt-5.6-luna", "effort": "medium"},
                       env={"PATH": "bin"})
        assert server.posts == [] and session.session == "ses_saved"
        assert server.puts == [("/api/session/ses_saved/environment", {"variables": {"PATH": "bin"}})]
    finally:
        session.tree.close()


# --------------------------------------------------------------- the scope case (report §6.6) and the debriefs (A6)


OUT_OF_SCOPE_REPORT = {
    "claim": "subtract implemented with a focused test", "result": "blocked",
    "producer": {"model": "scripted", "harness": "pytest"},
    "implementation": {"files_changed": ["calc/core.py", "tests/test_subtract.py"], "checks_run": ["unit"],
                       "deviations": ["calc/core.py is outside the Ticket's declared scope"],
                       "self_review": {"completed": True, "notes": "the change is right; the scope is not"}},
}


def _implemented_outside_its_scope(p, tmp_path) -> str:
    """A Ticket whose scope misses the code (report §6.6): the implementer changes calc/, which the scope does not
    cover, and reports that it is blocked."""
    from aewflow import assign

    wid = create_planned_ticket(p, tmp_path, scope=("lib/**", "tests/**"))
    impl = assign(p, wid)
    impl.write(SUBTRACT_PATCH)
    assert impl.check("unit")["result"] == "pass"
    impl.submit("implementation_report", OUT_OF_SCOPE_REPORT, "Blocked by the Ticket's scope.\n")
    return wid


def test_after_a_blocked_implementation_the_next_action_says_what_blocks_it(tmp_path):
    """E8 (report §6.6): the implementer fixed a file outside the Ticket's scope and reported `blocked`, yet
    `aew status` proposed the accepting transition, which the gate refused, and proposed it again after the
    refusal: the next actions tested only that a report existed. They must say what blocks the Ticket, and never
    propose a transition its gates will refuse."""
    p = sample_project(tmp_path)
    wid = _implemented_outside_its_scope(p, tmp_path)
    running = [a for a in p.ok("status", "--json")["next_actions"] if a.startswith(f"{wid}:")]
    assert not any("--to REVIEW_PENDING" in a for a in running), running
    assert any("blocked" in a and "calc/core.py" in a and f"aew gate show {wid}" in a for a in running), running


def test_a_change_outside_the_scope_is_refused_saying_what_the_lead_can_do(tmp_path):
    """E9 (report §6.6): the refusal named the path outside the scope and nothing else, and the Lead spent four
    `--help` lookups finding out that a scope cannot change. The refusal must say so, and what the Lead can do."""
    p = sample_project(tmp_path)
    wid = _implemented_outside_its_scope(p, tmp_path)
    message = _refusal(p, "work", "transition", wid, "--to", "REVIEW_PENDING")
    assert "scope is fixed" in message and f"aew work transition {wid} --to CANCELLED" in message, message


def test_work_create_warns_about_scope_globs_that_match_no_tracked_file(tmp_path):
    """E10 (report §6.6): a Lead that could not look at the project guessed seven scope globs, none of them the
    code's directory, and AEW accepted them without a word. Creation now names the globs that match no tracked
    file: a warning, not a refusal, since a Ticket may create new directories."""
    p = sample_project(tmp_path)
    out = p.lead("work", "create", "ticket", "--title", "t", "--class", "1", "--goal", "g",
                 "--scope", "src/**", "--scope", "calc/**")
    warnings = " ".join(out.get("warnings") or [])
    assert "src/**" in warnings and "calc/**" not in warnings, out


def test_the_lead_is_told_how_to_read_the_project_and_that_a_scope_is_fixed():
    """E11 (report §6.6; the A6 debriefs): no Lead was told it can read files (its tools were never named), and one
    guessed a scope, which is fixed once the Ticket exists. Eight of the twelve guided Leads were also surprised by
    the authority-candidate step that comes first, which the guide did not mention."""
    from aew.engine import guide
    from aew.harness.opencode import projection
    from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES

    assert "read, glob and grep" in projection.LEAD_SYSTEM
    text = guide.render(DEFAULT_GATES, DEFAULT_CHECKS)
    assert "read, glob and grep" in text and "scope is fixed" in text
    assert "authority candidates" in text


def test_the_dogfood_brief_describes_the_leads_real_permissions(monkeypatch):
    """O5 (report §6.6; A6): the brief said the Lead's shell runs "read-only `git` commands" (it runs four) and
    never named its read tools, so a Lead tried `git grep` and `git ls-files` and then guessed a scope. It also
    listed `aew evidence ingest` among the ingest commands (the most refused command), and said Class 0 skips
    verification "before integration" without the post-integration one, which three Leads read as a conflict."""
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "eval" / "m3" / "dogfood"))
    import dogfood

    assert "`git status|diff|log|show`" in dogfood.WORKING and "read, glob and grep" in dogfood.WORKING
    assert "accepted by its transition" in dogfood.WORKING
    assert "post-integration verification" in dogfood.WORKING


def test_harness_wait_shows_the_result_of_each_evidence_item(lab, tmp_path):
    """E8 (report §6.6): `aew harness wait` listed a run's evidence ids without their results or what to do next
    (the docs said it gave both), so the Lead never saw that its implementer's report said `blocked`, and went
    straight to a transition the gate refused."""
    wid = create_planned_ticket(lab.project, tmp_path, cls=1)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    out = lab.wait("R-INV-0001-1")
    assert out["status"] == "ended_with_evidence"
    assert set(out.get("results") or {}) == set(out["evidence"]) and set(out["results"].values()) == {"pass"}, out
    assert f"aew work transition {wid} --to RUNNING" in (out.get("next_action") or ""), out
