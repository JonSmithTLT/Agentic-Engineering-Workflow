"""The switch offer through the real engine: real init, the real answer's logic, the real adoption and its record.

Only the terminal is scripted (``switch_offer.terminal`` and ``operator.ask``). The two registered rows take an existing
project from what it holds: `mutating_concurrency` at 1, and no price table.
"""

from __future__ import annotations

import dataclasses
import io
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from aewflow import NOT_THE_DEFAULT_CAP, sample_project
from invariants import load_control

from aew import operator, process_kind, switch_offer
from aew.engine import stage_intents as SI
from aew.engine import usage_ops as O
from aew.engine.api import Engine
from aew.errors import PermissionDenied, StalePolicy
from aew.harness import lead_broker, procs
from aew.harness.opencode import lead
from aew.knowledge.manifest import DEFAULT_GATES
from aew.maps import service as maps

ZERO = "0" * 64
MUTATING, TABLE = (o.switch for o in switch_offer.OFFERS)
GATES, PRICES, MANIFEST = "policy/gates.yaml", "policy/pricing.yaml", "project.yaml"
BOTH = [MUTATING, TABLE]


class Terminal:
    """The operator at their terminal: each reply is typed back to the next prompt. ``CODE`` is the code the prompt
    shows, and an exception is what the read raises (a timeout)."""

    def __init__(self, *replies: Any) -> None:
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt: str, *, timeout: float = 0) -> str:
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return re.search(r"Type ([0-9A-F]{6}) and", prompt)[1] if reply == "CODE" else reply


@pytest.fixture
def old(tmp_path):
    """A project from before both defaults moved, adopted as it is: `mutating_concurrency` 1, no table."""
    p = sample_project(tmp_path)
    gates = p.root / ".aew" / GATES
    default = f"mutating_concurrency: {DEFAULT_GATES['mutating_concurrency']}"
    assert default in gates.read_text(encoding="utf-8")
    gates.write_text(gates.read_text(encoding="utf-8").replace(default, "mutating_concurrency: 1"), encoding="utf-8",
                     newline="\n")
    _manifest(p, lambda policy: policy.pop("pricing"))
    (p.root / ".aew" / PRICES).unlink()
    p.adopt_policy()
    return p


def _manifest(p, change) -> None:
    path = p.root / ".aew" / MANIFEST
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data["policy"])
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")


def engine(p) -> Engine:
    return Engine.discover(p.root)


def _rows(*names: str) -> tuple[Any, ...]:
    return tuple(o for o in switch_offer.OFFERS if o.switch in names)


@pytest.fixture
def at_terminal(monkeypatch):
    """The operator's terminal, with the replies given; replaces the suite's stub."""

    def script(*replies: Any) -> Terminal:
        term = Terminal(*replies)
        monkeypatch.setattr(switch_offer, "terminal", lambda: True)
        monkeypatch.setattr(operator, "ask", term)
        return term

    return script


def start(p) -> tuple[switch_offer.Decision, io.StringIO]:
    out = io.StringIO()
    return switch_offer.at_lead_start(engine(p), out), out


def take(p, *answers: Any, at_terminal) -> tuple[Terminal, str]:
    term = at_terminal(*answers)
    decision, out = start(p)
    decision.apply(p.token)
    return term, out.getvalue()


def only_row(monkeypatch, name: str) -> None:
    monkeypatch.setattr(switch_offer, "OFFERS", _rows(name))


def snapshot(p, *rels: str) -> dict[str, bytes | None]:
    return {rel: (p.root / ".aew" / rel).read_bytes() if (p.root / ".aew" / rel).exists() else None for rel in rels}


def doctor(p) -> dict[str, str]:
    return {check: detail for check, _, detail in switch_offer.doctor_rows(engine(p))}


def decisions(p) -> list[dict[str, Any]]:
    return [yaml.safe_load(f.read_text(encoding="utf-8").split("---")[1])
            for f in sorted((p.root / ".aew/decisions").glob("D-*.md"))]


# ------------------------------------------------------------------------------------------ who is asked (rule 1)

def test_a_switch_offer_is_asked_only_at_the_operators_terminal_in_aew_opencode(old, at_terminal):
    silent, out = start(old)  # the suite's stub: no terminal
    assert silent.taken == [] and out.getvalue() == ""
    assert set(doctor(old)) == {f"switch-offer:{MUTATING}", f"switch-offer:{TABLE}"}
    term = at_terminal("CODE", "CODE")
    decision, _ = start(old)
    assert len(term.prompts) == 2 and [t[0].switch for t in decision.taken] == BOTH
    assert snapshot(old, PRICES)[PRICES] is None  # asking writes nothing: it is applied with the credential


def test_aew_lead_session_never_offers():
    """`aew lead session` passes no ``with_token``, so nothing can be applied there."""
    import inspect

    from aew.cli import commands

    assert "switch_offer" not in inspect.getsource(commands) and "with_token" not in inspect.getsource(commands)
    assert inspect.signature(lead_broker.run_session).parameters["with_token"].default is None


@pytest.mark.parametrize("row", BOTH)
def test_a_lead_session_is_never_asked_a_switch_offer(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
    term = at_terminal("CODE")
    monkeypatch.setenv("AEW_LEAD_BROKER", "/synthetic/broker")
    decision, out = start(old)
    assert term.prompts == [] and decision.taken == [] and out.getvalue() == ""


@pytest.mark.parametrize("row", BOTH)
def test_an_agents_own_aew_never_asks_a_switch_offer(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
    term = at_terminal("CODE")
    monkeypatch.setattr(process_kind, "kind", lambda: process_kind.NON_WRITER)
    decision, _ = start(old)
    assert term.prompts == [] and decision.taken == []


def test_an_operator_using_the_lead_token_variable_is_still_asked(old, at_terminal, monkeypatch):
    """How an operator legitimately starts `aew opencode`: only a broker's coordinates mark a Lead session."""
    term = at_terminal("", "")
    monkeypatch.setenv("AEW_LEAD_TOKEN", "synthetic-not-a-token")
    start(old)
    assert len(term.prompts) == 2


# ------------------------------------------------------------------------------------------ when it offers (rule 2)

def test_a_hand_set_value_is_never_offered(old):
    gates = old.root / ".aew" / GATES
    gates.write_text(gates.read_text(encoding="utf-8").replace("mutating_concurrency: 1",
                                                               f"mutating_concurrency: {NOT_THE_DEFAULT_CAP}"),
                     encoding="utf-8", newline="\n")
    old.adopt_policy()
    assert f"switch-offer:{MUTATING}" not in doctor(old)


def test_a_project_already_at_the_default_is_not_offered(tmp_path):
    p = sample_project(tmp_path)
    assert doctor(p) == {}


def test_an_absent_key_whose_default_already_holds_is_not_offered(old):
    gates = old.root / ".aew" / GATES
    gates.write_text(gates.read_text(encoding="utf-8").replace("mutating_concurrency: 1\n", ""), encoding="utf-8",
                     newline="\n")
    old.adopt_policy()
    assert f"switch-offer:{MUTATING}" not in doctor(old)


def _operational_row(**kw: Any) -> switch_offer.SwitchOffer:
    """A test row on an operational key that init doesn't write, as maps' and messaging's later rows are."""
    return switch_offer.key_offer("test_row", file=GATES, key_path=("history_audit", "test_absent"), old_values=(),
                                  to_value=lambda: 9, effective=lambda v: 5 if v is switch_offer.ABSENT else v,
                                  legality=False, schema="unchecked", text=lambda o: "a test row",
                                  done=lambda o: "test row done", **kw)


def test_an_absent_key_at_an_older_effective_value_is_offered(old):
    row = _operational_row()
    assert row.opening(old.root / ".aew") == switch_offer.Opening("5", "9")


def test_an_absent_file_is_not_offered(old):
    row = switch_offer.key_offer("test_row", file="policy/not-there.yaml", key_path=("a",), old_values=(1,),
                                 to_value=lambda: 2, effective=lambda v: 1, legality=False, schema="gates",
                                 text=lambda o: "", done=lambda o: "")
    assert row.opening(old.root / ".aew") is None


def test_the_table_is_not_offered_to_a_project_that_names_one_and_its_file_is_untouched(old, at_terminal, monkeypatch):
    only_row(monkeypatch, TABLE)
    ours = "policy/our-prices.yaml"  # not init's path: only the manifest's naming it can say the project has a table
    (old.root / ".aew" / ours).write_bytes(b"schema: aew/pricing/v1\ncurrency: USD\nas_of: '2026-01-01'\n"
                                           b"source: ours\nprices:\n  p/m: {input: 1.0}\n")
    _manifest(old, lambda policy: policy.update(pricing=ours))
    old.adopt_policy()
    before = snapshot(old, ours, PRICES, MANIFEST)
    term = at_terminal("CODE")
    decision, _ = start(old)
    assert term.prompts == [] and decision.taken == [] and doctor(old) == {}
    assert snapshot(old, ours, PRICES, MANIFEST) == before


def test_the_table_is_not_offered_over_a_file_the_manifest_doesnt_name(old, at_terminal, monkeypatch):
    """A table the operator took out of force keeps its file, and the offer never overwrites it."""
    only_row(monkeypatch, TABLE)
    (old.root / ".aew" / PRICES).write_bytes(b"kept: by the operator\n")
    before = snapshot(old, PRICES)
    term = at_terminal("CODE")
    start(old)
    assert term.prompts == [] and doctor(old) == {} and snapshot(old, PRICES) == before


# ------------------------------------------------------------------------------------------ what taking it does

def test_taking_it_changes_only_that_key_and_keeps_comments(old, at_terminal, monkeypatch):
    only_row(monkeypatch, MUTATING)
    gates = old.root / ".aew" / GATES
    text = "# the operator's note\n" + gates.read_text(encoding="utf-8").replace(
        "mutating_concurrency: 1\n", "mutating_concurrency: 1   # why we hold this\n") + "# the last word\n"
    gates.write_text(text, encoding="utf-8", newline="\n")
    old.adopt_policy()
    take(old, "CODE", at_terminal=at_terminal)
    to = DEFAULT_GATES["mutating_concurrency"]
    assert gates.read_text(encoding="utf-8") == text.replace("mutating_concurrency: 1 ", f"mutating_concurrency: {to} ")
    assert doctor(old) == {}


def test_taking_the_table_adds_one_line_to_a_hand_edited_manifest_and_keeps_the_rest_byte_for_byte(old, at_terminal,
                                                                                                    monkeypatch):
    only_row(monkeypatch, TABLE)
    path = old.root / ".aew" / MANIFEST
    text = path.read_text(encoding="utf-8")
    head, tail = text.split("policy:\n", 1)
    edited = f"# the operator's note\n{head}policy: # ours\n  # the guardrails come first\n{tail}# the last word\n"
    path.write_text(edited, encoding="utf-8", newline="\n")
    old.adopt_policy()
    before = path.read_bytes()
    take(old, "CODE", at_terminal=at_terminal)
    after = path.read_bytes()
    added = b"  pricing: policy/pricing.yaml\n"
    assert after.count(added) == 1 and after.replace(added, b"") == before
    assert (old.root / ".aew" / PRICES).read_bytes() == O.bundled_table()
    assert engine(old).manifest["policy"]["pricing"] == PRICES


def test_a_manifest_it_cant_edit_as_text_is_refused_and_says_how_by_hand(old, at_terminal, monkeypatch):
    only_row(monkeypatch, TABLE)
    path = old.root / ".aew" / MANIFEST
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=True), encoding="utf-8", newline="\n")
    old.adopt_policy()
    before = snapshot(old, PRICES, MANIFEST)
    rev = old.rev()
    _, said = take(old, "CODE", at_terminal=at_terminal)
    assert snapshot(old, PRICES, MANIFEST) == before and old.rev() == rev
    assert "is unchanged" in said and "default_pricing.yaml" in said


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_an_edit_keeps_the_files_own_line_endings_and_a_missing_last_one(newline):
    raw = newline.join(["# a", "policy:", "  gates: g  # b", "other: 1"]).encode()
    edited = switch_offer.edit_key(raw, ("policy", "pricing"), "p.yaml")
    assert edited == newline.join(["# a", "policy:", "  gates: g  # b", "  pricing: p.yaml", "other: 1"]).encode()
    assert switch_offer.edit_key(b"a: 1", ("b",), 2) == b"a: 1\nb: 2\n"


def test_an_edit_that_would_change_anything_else_is_refused():
    with pytest.raises(switch_offer.HandChange):
        switch_offer.edit_key(b"policy: {gates: g}\n", ("policy", "pricing"), "p.yaml")


@pytest.mark.parametrize("row", BOTH)
def test_taking_it_adopts_as_the_operators_with_manifest_adopts_record(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
    before = len(decisions(old))
    _, said = take(old, "CODE", at_terminal=at_terminal)
    assert "adopted as your decision" in said
    record = decisions(old)[-1]
    assert len(decisions(old)) == before + 1 and record["type"] == "manifest_adoption"
    assert record["decided_by"]["kind"] == "operator" and record["decided_by"]["authorized_by"] == "operator-tty"
    assert record["reason"].startswith(f"switch offer: {row} ")
    drift = engine(old).policy_pin_drift(load_control(old.root))
    assert drift == [] and engine(old).manifest_pin_ok(load_control(old.root))


# ------------------------------------------------------------------------------- adopting only its own (rule 3)

@pytest.mark.parametrize("row", BOTH)
def test_any_other_drift_refuses_and_lists_it(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
    guard = old.root / ".aew/policy/guardrails.yaml"
    guard.write_text(guard.read_text(encoding="utf-8") + "# an edit nobody adopted\n", encoding="utf-8", newline="\n")
    term = at_terminal("CODE")
    decision, out = start(old)
    assert term.prompts == [] and decision.taken == []
    assert "policy/guardrails.yaml" in out.getvalue() and "the offer returns" in out.getvalue()
    assert "policy/guardrails.yaml" in doctor(old)[f"switch-offer:{row}"]


@pytest.mark.parametrize("row,files", [(MUTATING, [GATES]), (TABLE, [PRICES, MANIFEST])])
def test_a_drift_after_the_check_is_refused_inside_the_adopt_and_leaves_neither_file(old, at_terminal, monkeypatch, row,
                                                                                     files):
    """A real refusal, by `only=` inside the real adoption's transaction."""
    only_row(monkeypatch, row)
    before = snapshot(old, *files)
    rev = old.rev()
    term = at_terminal("CODE")
    decision, out = start(old)
    assert term.prompts
    guard = old.root / ".aew/policy/guardrails.yaml"
    edited = guard.read_text(encoding="utf-8") + "# arrived after the check\n"
    guard.write_text(edited, encoding="utf-8", newline="\n")
    decision.apply(old.token)
    assert "is unchanged" in out.getvalue() and "policy/guardrails.yaml" in out.getvalue()
    assert snapshot(old, *files) == before and old.rev() == rev
    assert guard.read_text(encoding="utf-8") == edited  # never the offer's to touch


@pytest.mark.parametrize("row,files", [(MUTATING, [GATES]), (TABLE, [PRICES, MANIFEST])])
def test_a_failed_adopt_restores_every_file_it_wrote(old, at_terminal, monkeypatch, row, files):
    """A real failure: the real adoption refuses a credential that isn't the Lead's."""
    only_row(monkeypatch, row)
    before = snapshot(old, *files)
    at_terminal("CODE")
    decision, out = start(old)
    decision.apply("synthetic-not-the-lead")
    assert "is unchanged" in out.getvalue() and snapshot(old, *files) == before
    assert not decisions(old)[-1]["reason"].startswith("switch offer")
    assert engine(old).manifest_pin_ok(load_control(old.root))


def test_a_table_the_adoption_refuses_leaves_neither_file(old, at_terminal, monkeypatch):
    """A real failure inside the adoption: the bytes don't validate as a price table."""
    only_row(monkeypatch, TABLE)
    before = snapshot(old, PRICES, MANIFEST)
    at_terminal("CODE")
    decision, out = start(old)
    monkeypatch.setattr(O, "bundled_table", lambda: b"not: a price table\n")
    decision.apply(old.token)
    assert "is unchanged" in out.getvalue() and snapshot(old, PRICES, MANIFEST) == before


def test_a_failed_adopt_leaves_a_file_someone_else_changed(old, at_terminal, monkeypatch):
    only_row(monkeypatch, TABLE)
    before = snapshot(old, MANIFEST)
    at_terminal("CODE")
    decision, out = start(old)
    real = Engine.manifest_adopt

    def theirs_first(self: Engine, **kw: Any) -> Any:
        (self.aew_root / PRICES).write_bytes(b"theirs\n")
        return real(self, **{**kw, "token": "synthetic-not-the-lead"})

    monkeypatch.setattr(Engine, "manifest_adopt", theirs_first)
    decision.apply(old.token)
    assert snapshot(old, MANIFEST) == before and (old.root / ".aew" / PRICES).read_bytes() == b"theirs\n"
    assert PRICES in out.getvalue() and "left as it is" in out.getvalue()


def test_only_refuses_a_never_pinned_project_where_an_adopt_would_pin_everything(old):
    from aew.engine.store import serialize_control
    from aew.errors import IllegalTransition

    state = load_control(old.root)
    del state["policy_sha256"]
    (old.root / ".aew/state/control.yaml").write_bytes(serialize_control(state))
    with pytest.raises(IllegalTransition, match="no file was ever pinned"):
        engine(old).manifest_adopt(token=old.token, expect_rev=old.rev(), reason="r", only=[GATES],
                                   authorization={"authorized_by": "operator-tty", "challenge_code": "X"})


def test_a_never_pinned_project_is_not_asked_and_says_why(old, at_terminal):
    from aew.engine.store import serialize_control

    state = load_control(old.root)
    del state["policy_sha256"]
    (old.root / ".aew/state/control.yaml").write_bytes(serialize_control(state))
    term = at_terminal("CODE", "CODE")
    decision, out = start(old)
    assert term.prompts == [] and decision.taken == [] and "never pinned" in out.getvalue()


# ------------------------------------------------------------------------------------------ the answer (rule 4)

def test_authorize_still_refuses_an_empty_answer(monkeypatch):
    """The one approval site keeps its meaning for every other caller: only the offer reads Enter as a no."""
    monkeypatch.setattr(operator, "ask", lambda prompt, timeout=0: "")
    with pytest.raises(PermissionDenied, match="refused or mistyped"):
        operator.authorize("adopt this")


def test_enter_alone_never_authorizes_and_only_the_code_does(monkeypatch):
    monkeypatch.setattr(operator, "ask", lambda prompt, timeout=0: "  ")
    assert operator.answer("switch") == operator.Answer(None, True)
    monkeypatch.setattr(operator, "ask", lambda prompt, timeout=0: "not the code")
    with pytest.raises(PermissionDenied):
        operator.answer("switch")
    monkeypatch.setattr(operator, "ask", lambda prompt, timeout=0: re.search(r"code ([0-9A-F]{6})", prompt)[1])
    assert operator.answer("switch").authorization["authorized_by"] == "operator-tty"


def test_the_switch_prompt_names_what_changes_and_no_credential_destination(old, at_terminal):
    term = at_terminal("", "")
    start(old)
    named = (f"{GATES} mutating_concurrency", "project.yaml policy.pricing")
    for prompt, changes in zip(term.prompts, named, strict=True):
        assert "credential to" not in prompt and changes in prompt
        assert "Enter alone keeps" in prompt and "won't ask again" in prompt
    assert "Enter alone keeps 1" in term.prompts[0] and "Enter alone keeps no table" in term.prompts[1]


def test_a_declined_offer_is_not_asked_again_and_doctor_keeps_showing_it(old, at_terminal, monkeypatch):
    only_row(monkeypatch, MUTATING)
    term = at_terminal("")
    decision, out = start(old)
    assert decision.taken == [] and "won't ask again" in out.getvalue()
    assert len(term.prompts) == 1
    again = at_terminal("CODE")
    start(old)
    assert again.prompts == []
    assert "Declined switch" in doctor(old)[f"switch-offer:{MUTATING}"]
    assert (old.root / ".aew/local/switch-offers.json").is_file()


@pytest.mark.parametrize("answers,taken,left_pending", [
    (("", "CODE"), [TABLE], MUTATING), (("CODE", ""), [MUTATING], TABLE), (("wrong", "CODE"), [TABLE], MUTATING)])
def test_each_answer_stands_alone(old, at_terminal, answers, taken, left_pending):
    term = at_terminal(*answers)
    decision, _ = start(old)
    assert len(term.prompts) == 2 and [t[0].switch for t in decision.taken] == taken
    decision.apply(old.token)
    assert list(doctor(old)) == [f"switch-offer:{left_pending}"]


@pytest.mark.parametrize("reply", ["wrong", PermissionDenied("operator authorization timed out")],
                         ids=["wrong_code", "timeout"])
def test_a_wrong_code_or_a_timeout_is_not_remembered(old, at_terminal, monkeypatch, reply):
    only_row(monkeypatch, MUTATING)
    at_terminal(reply)
    decision, out = start(old)
    assert decision.taken == [] and "asked again next start" in out.getvalue()
    assert not (old.root / ".aew/local/switch-offers.json").exists()
    term = at_terminal("")
    start(old)
    assert len(term.prompts) == 1


def test_a_damaged_memory_reads_as_no_answers(old, at_terminal, monkeypatch):
    only_row(monkeypatch, MUTATING)
    path = old.root / ".aew/local/switch-offers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{not json")
    term = at_terminal("")
    start(old)
    assert len(term.prompts) == 1


def test_a_later_default_raise_is_a_new_offer(old, at_terminal, monkeypatch):
    only_row(monkeypatch, MUTATING)
    at_terminal("")
    start(old)
    monkeypatch.setitem(DEFAULT_GATES, "mutating_concurrency", 3)
    term = at_terminal("")
    start(old)
    assert len(term.prompts) == 1


# ------------------------------------------------------------------------------- open stages: the screen, and its truth

def open_stage(p, steps: int = 3) -> str:
    return engine(p).stage_open(token=p.token, expect_rev=p.rev(), tool="probe", contract_digest=ZERO,
                                arguments={"why": "a test"}, judgment_inputs=[], base_class="MECHANICAL",
                                effective_class="MECHANICAL", plan=[{"primitive": "checkpoint"}] * steps, subject=None,
                                ingress="test")["intent"]


def run_step(p, si: str, n: int) -> None:
    with SI.step(si, n):
        engine(p).checkpoint(token=p.token, expect_rev=p.rev(), note=f"{si} {n}", next_action=f"after {n}")


def test_open_stage_intents_are_named_for_a_legality_switch_and_the_table_says_it_stops_none(old, at_terminal):
    si = open_stage(old)
    assert si
    term = at_terminal("", "")
    start(old)
    first, second = term.prompts
    assert "stops as STALE_POLICY" in first and "Open now: 1." in first
    assert "open stages carry on" in second and "STALE_POLICY" not in second


def test_taking_the_table_through_the_real_offer_stales_no_open_stage(old, at_terminal, monkeypatch):
    """The real offer, the real writer and the real adoption, with a stage open across them (F25 §11's route)."""
    only_row(monkeypatch, TABLE)
    si = open_stage(old)
    run_step(old, si, 1)
    before = engine(old).policy_digests()
    _, said = take(old, "CODE", at_terminal=at_terminal)
    assert "in force at" in said
    after = engine(old).policy_digests()
    assert after["legality_digest"] == before["legality_digest"]
    assert after["operational_digest"] != before["operational_digest"]
    assert engine(old).stage_recheck(si, contract_digest=ZERO, plan=None)["checks"]["policy"]["status"] == "ok"
    run_step(old, si, 2)
    assert len({s["legality_digest"] for s in engine(old).stage_intent(si)["steps"]}) == 1


def test_taking_the_cap_through_the_real_offer_stops_an_open_stage_as_the_screen_says(old, at_terminal, monkeypatch):
    only_row(monkeypatch, MUTATING)
    si = open_stage(old)
    run_step(old, si, 1)
    take(old, "CODE", at_terminal=at_terminal)
    with pytest.raises(StalePolicy) as exc:
        run_step(old, si, 2)
    assert exc.value.details["intent"] == si and "how this version of AEW reads it" in exc.value.message


@pytest.mark.parametrize("row", switch_offer.OFFERS, ids=lambda o: o.switch)
def test_each_offers_legality_flag_matches_the_digest(old, at_terminal, monkeypatch, row):
    monkeypatch.setattr(switch_offer, "OFFERS", (row,))
    before = engine(old).policy_digests()
    take(old, "CODE", at_terminal=at_terminal)
    after = engine(old).policy_digests()
    assert (after["legality_digest"] != before["legality_digest"]) is row.legality
    assert doctor(old) == {}  # it was really taken, so the flag was really tested


# ------------------------------------------------------------------------------------------ the start (rule 5)

def test_after_adopt_runs_after_the_commit_and_cannot_undo_it(old, at_terminal, monkeypatch):
    seen: list[Any] = []

    def after(e: Engine, token: str) -> None:
        seen.append((maps.first_map(e)["reason"], token, load_control(old.root)["revision"]))
        raise RuntimeError("the map failed")

    rev = old.rev()
    row = switch_offer.key_offer(
        "test_row", file=GATES, key_path=("history_audit", "max_unverified_entries"), old_values=(5,),
        to_value=lambda: 9, effective=lambda v: v, legality=False, schema="gates", text=lambda o: "a test row",
        done=lambda o: "done", after_adopt=after)
    gates = old.root / ".aew" / GATES
    data = yaml.safe_load(gates.read_text(encoding="utf-8"))
    data.setdefault("history_audit", {})["max_unverified_entries"] = 5
    gates.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")
    old.adopt_policy()
    rev = old.rev()
    monkeypatch.setattr(switch_offer, "OFFERS", (row,))
    _, said = take(old, "CODE", at_terminal=at_terminal)
    assert seen == [("already_selected", old.token, rev + 1)], seen
    assert "adopted, but its next step failed" in said and old.rev() == rev + 1


def _fake_session(monkeypatch) -> None:
    class Broker:
        superseded = False
        env: dict[str, str] = {}
        server = type("S", (), {"private_dir": None})()

        def __init__(self, engine: Any, token: str) -> None:
            pass

        def start(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(lead_broker, "LeadBroker", Broker)
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    monkeypatch.setattr(procs, "run_session_tree", lambda command, **k: (0, "clean"))


def _contained(_dir: Any, env: dict[str, str]) -> lead_broker.Harness:
    return lead_broker.Harness(argv=["harness"], env=env, relay=False, label={}, close=lambda: None)


@pytest.mark.parametrize("acquire", [True, False], ids=["acquire", "held"])
def test_the_offer_reaches_the_adopt_with_a_token_on_both_acquire_paths(old, at_terminal, monkeypatch, acquire):
    only_row(monkeypatch, TABLE)
    _fake_session(monkeypatch)
    at_terminal("CODE")
    decision, out = start(old)
    e = decision.engine
    if acquire:
        e.lead_release(token=old.token, expect_rev=old.rev())
        monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    else:
        monkeypatch.setenv("AEW_LEAD_TOKEN", old.token)
    lead_broker.run_session(e, ["harness"], acquire=acquire, session_label=None, keep_seat=True, env={},
                            contained=_contained, with_token=decision.apply)
    assert "in force at" in out.getvalue(), out.getvalue()
    assert decisions(old)[-1]["reason"].startswith(f"switch offer: {TABLE} ")


def test_aew_opencode_wires_the_offer_into_the_session_on_the_start_path_it_takes(monkeypatch, tmp_path):
    """Asked at `aew opencode`'s start, and what was taken is what the session is given."""
    seen: dict[str, Any] = {}
    made = switch_offer.Decision()
    monkeypatch.setenv("AEW_LEAD_TOKEN", "synthetic-not-a-token")
    monkeypatch.setenv("OPENCODE_DB", str(tmp_path / "no-login.db"))
    monkeypatch.setattr(lead, "contained_here", lambda: False)
    monkeypatch.setattr(lead, "check_version", lambda: "2.2.6")
    monkeypatch.setattr(lead, "guide_of", lambda engine: "")
    monkeypatch.setattr(lead, "command", lambda engine, extra: ["opencode"])
    monkeypatch.setattr(switch_offer, "at_lead_start", lambda engine, out: made)
    monkeypatch.setattr(lead_broker, "run_session", lambda engine, argv, **k: seen.update(k) or {"ok": True})
    engine_ = type("E", (), {"execution_policy": lambda self: ({"containment": {"mode": "allow_weaker"}}, None)})()
    lead.run(engine_, acquire=False, session_label=None, keep_seat=False, provider_env=[], extra_args=[],
             print_config=False)
    assert seen["with_token"] == made.apply


def test_a_start_refused_after_the_answer_writes_nothing(old, at_terminal, monkeypatch):
    only_row(monkeypatch, TABLE)
    before = snapshot(old, PRICES, MANIFEST)
    rev = old.rev()
    at_terminal("CODE")
    decision, _ = start(old)
    assert decision.taken  # and `apply` never runs: the start was refused here
    assert snapshot(old, PRICES, MANIFEST) == before and old.rev() == rev
    term = at_terminal("")
    start(old)
    assert len(term.prompts) == 1  # asked again


def test_nothing_about_the_offer_stops_the_start(old, at_terminal, monkeypatch):
    def boom(_root: Path) -> None:
        raise RuntimeError("a broken row")

    row = switch_offer.SwitchOffer(switch="broken", legality=False, opening=boom, edits=boom, text=lambda o: "",
                                   changes="", done=lambda o: "", by_hand="")
    monkeypatch.setattr(switch_offer, "OFFERS", (row,))
    at_terminal("CODE")
    decision, out = start(old)
    assert decision.taken == [] and "could not be read" in out.getvalue()

    good = dataclasses.replace(row, opening=lambda _r: switch_offer.Opening("a", "b"), text=lambda o: "t")
    monkeypatch.setattr(switch_offer, "OFFERS", (good,))
    at_terminal("CODE")
    decision, out = start(old)
    assert len(decision.taken) == 1
    decision.apply(old.token)  # edits raises RuntimeError: said, never raised
    assert "the broken offer failed" in out.getvalue()


def test_to_value_is_the_owners_default(old, monkeypatch):
    row = _rows(MUTATING)[0]
    monkeypatch.setitem(DEFAULT_GATES, "mutating_concurrency", 7)
    assert row.opening(old.root / ".aew") == switch_offer.Opening("1", "7")
    assert yaml.safe_load(row.edits(old.root / ".aew")[GATES])["mutating_concurrency"] == 7
