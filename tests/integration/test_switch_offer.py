"""The switch offer through the real engine: real init, the real answer's logic, the real adoption and its record.

Only the terminal is scripted (``switch_offer.terminal`` and ``operator.ask``). The two registered rows take an existing
project from what it holds: `mutating_concurrency` at 1, and no price table.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from aewflow import NOT_THE_DEFAULT_CAP, sample_project
from conftest import run_aew
from invariants import load_control

from aew import operator, process_kind, switch_offer
from aew.cli import main as cli
from aew.engine import stage_intents as SI
from aew.engine import usage_ops as O
from aew.engine.api import Engine
from aew.errors import AEWError, PermissionDenied, StalePolicy
from aew.harness import contract as K
from aew.harness import lead_broker, procs
from aew.harness.opencode import lead
from aew.knowledge.manifest import DEFAULT_GATES
from aew.maps import service as maps

ZERO = "0" * 64
MUTATING, TABLE = (o.switch for o in switch_offer.OFFERS)
GATES, PRICES, MANIFEST = "policy/gates.yaml", "policy/pricing.yaml", "project.yaml"
BOTH = [MUTATING, TABLE]
FROZEN = Path(__file__).resolve().parents[1] / "fixtures" / "switch-offer-old-project"


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


@pytest.fixture(autouse=True)
def leave_the_real_terminal_alone(monkeypatch):
    """The terminal here is scripted, so a run's own terminal is never read or flushed. The tests of the discard itself
    run it in a process with a pty of its own."""
    monkeypatch.setattr(operator, "discard_typed_ahead", lambda: None)


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


def test_aew_lead_session_never_offers(old, at_terminal, monkeypatch):
    """The real command, at a terminal, on a project with both pending: nothing asks and nothing can be applied."""
    term = at_terminal("CODE", "CODE")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(lead_broker, "run_session", lambda engine, command, **k: seen.update(k) or {"ok": True})
    cli.main(["-C", str(old.root), "lead", "session"])
    assert "contained" in seen, "the command never reached the session"
    assert term.prompts == [] and seen.get("with_token") is None


@pytest.mark.parametrize("variable", ["AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"])
@pytest.mark.parametrize("row", BOTH)
def test_a_lead_session_is_never_asked_a_switch_offer(old, at_terminal, monkeypatch, row, variable):
    only_row(monkeypatch, row)
    term = at_terminal("CODE")
    monkeypatch.setenv(variable, "/synthetic/broker")
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


def test_the_cap_is_not_offered_on_a_file_the_manifest_doesnt_put_in_force(old, at_terminal, monkeypatch):
    """The manifest names another gates file, holding the operator's value: the old file holds nothing to switch."""
    only_row(monkeypatch, MUTATING)
    ours = "policy/our-gates.yaml"
    gates = old.root / ".aew" / GATES
    theirs = f"mutating_concurrency: {NOT_THE_DEFAULT_CAP}".encode()
    (old.root / ".aew" / ours).write_bytes(gates.read_bytes().replace(b"mutating_concurrency: 1", theirs))
    _manifest(old, lambda policy: policy.update(gates=ours))
    old.adopt_policy()
    assert b"mutating_concurrency: 1" in gates.read_bytes()
    term = at_terminal("CODE")
    decision, _ = start(old)
    assert term.prompts == [] and decision.taken == [] and doctor(old) == {}


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
    return switch_offer.key_offer("test_row", label="a test row", file=GATES, policy_key="gates",
                                  key_path=("history_audit", "test_absent"), old_values=(),
                                  to_value=lambda: 9, effective=lambda v: 5 if v is switch_offer.ABSENT else v,
                                  legality=False, schema="unchecked", text=lambda o: "a test row",
                                  done=lambda o: "test row done", **kw)


def test_an_absent_key_at_an_older_effective_value_is_offered(old):
    row = _operational_row()
    assert row.opening(old.root / ".aew") == switch_offer.Opening("5", "9")


def test_an_absent_file_is_not_offered(old):
    row = switch_offer.key_offer("test_row", label="a test row", file="policy/not-there.yaml", policy_key="not_there",
                                 key_path=("a",), old_values=(1,), to_value=lambda: 2, effective=lambda v: 1,
                                 legality=False, schema="gates", text=lambda o: "", done=lambda o: "")
    _manifest(old, lambda policy: policy.update(not_there="policy/not-there.yaml"))
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


def test_an_edit_it_cant_make_is_never_asked_and_says_how_by_hand(old, at_terminal, monkeypatch):
    only_row(monkeypatch, TABLE)
    path = old.root / ".aew" / MANIFEST
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=True), encoding="utf-8", newline="\n")
    old.adopt_policy()
    before = snapshot(old, PRICES, MANIFEST)
    rev = old.rev()
    term, said = take(old, "CODE", at_terminal=at_terminal)
    assert term.prompts == [] and snapshot(old, PRICES, MANIFEST) == before and old.rev() == rev
    assert "can't make that edit" in said and "default_pricing.yaml" in said
    assert "default_pricing.yaml" in doctor(old)[f"switch-offer:{TABLE}"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_an_edit_keeps_the_files_own_line_endings_and_a_missing_last_one(newline):
    raw = newline.join(["# a", "policy:", "  gates: g  # b", "other: 1"]).encode()
    edited = switch_offer.edit_key(raw, ("policy", "pricing"), "p.yaml")
    assert edited == newline.join(["# a", "policy:", "  gates: g  # b", "  pricing: p.yaml", "other: 1"]).encode()
    assert switch_offer.edit_key(b"a: 1", ("b",), 2) == b"a: 1\nb: 2\n"


def test_an_edit_that_would_change_anything_else_is_refused():
    with pytest.raises(switch_offer.HandChange):
        switch_offer.edit_key(b"policy: {gates: g}\n", ("policy", "pricing"), "p.yaml")


@pytest.mark.parametrize("raw,key_path", [(b'"mutating_concurrency": 1\nother: 3\n', ("mutating_concurrency",)),
                                           (b"'policy':\n  gates: g\n", ("policy", "pricing"))],
                         ids=["leaf", "parent"])
def test_a_quoted_key_is_refused_rather_than_given_a_second_key(raw, key_path):
    with pytest.raises(switch_offer.HandChange, match="can't be edited as text"):
        switch_offer.edit_key(raw, key_path, 2)


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
    assert "at the switch offer" in record["summary"] and "manual edit" not in record["summary"]
    drift = engine(old).policy_pin_drift(load_control(old.root))
    assert drift == [] and engine(old).manifest_pin_ok(load_control(old.root))


def _follow_the_hand_route(p, line: str, monkeypatch) -> None:
    """Do what the printed line says, from the project's root, and run its command as printed."""
    root = p.root
    set_key = re.search(r"set (\S+) to (\S+) in (\S+);", line)
    if set_key:
        key, value, rel = set_key.groups()
        path = root / rel
        path.write_bytes(re.sub(rf"(?m)^{key}: .*$", f"{key}: {value}", path.read_bytes().decode()).encode())
    else:
        steps = r"copy `(.+?)` to (\S+), add `(.+?)` under `policy:` in (\S+);"
        source, rel, entry, manifest = re.search(steps, line).groups()
        (root / rel).write_bytes(Path(source).read_bytes())
        path = root / manifest
        path.write_bytes(path.read_bytes().replace(b"policy:\n", f"policy:\n  {entry}\n".encode(), 1))
    printed = re.search(r"`(aew manifest adopt [^`]+)`", line)[1]
    command = shlex.split(printed.replace(K.REVISION, str(p.rev())).replace("<reason>", "'by hand'"))
    argv = command[1:]
    monkeypatch.setenv("AEW_LEAD_TOKEN", p.token)
    monkeypatch.setattr(operator, "ask", lambda prompt, timeout=0: re.search(r"code ([0-9A-F]{6})", prompt)[1])
    assert cli.main(["-C", str(root), *argv]) in (0, None)


@pytest.mark.parametrize("row", BOTH)
def test_the_hand_route_runs_as_printed_and_takes_the_declined_switch(old, at_terminal, monkeypatch, row):
    """The only way back from a remembered no, followed as the screen and doctor print it."""
    only_row(monkeypatch, row)
    _, said = take(old, "", at_terminal=at_terminal)
    line = doctor(old)[f"switch-offer:{row}"]
    assert line.split("To take it: ")[1].rstrip(".") in said
    _follow_the_hand_route(old, line, monkeypatch)
    assert doctor(old) == {}
    state = load_control(old.root)
    assert engine(old).policy_pin_drift(state) == [] and engine(old).manifest_pin_ok(state)
    if row == MUTATING:
        assert engine(old)._k.policy("gates")["mutating_concurrency"] == DEFAULT_GATES["mutating_concurrency"]
    else:
        assert engine(old).manifest["policy"]["pricing"] == PRICES
        assert (old.root / ".aew" / PRICES).read_bytes() == O.bundled_table()


@pytest.mark.parametrize("row", BOTH)
def test_every_line_naming_the_adopt_gives_the_paths_and_flags_it_needs(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
    adopt = f"`aew manifest adopt --reason <reason> {K.EXPECT_REV}`"
    guard = old.root / ".aew/policy/guardrails.yaml"
    guard.write_text(guard.read_text(encoding="utf-8") + "# an edit\n", encoding="utf-8", newline="\n")
    assert adopt in doctor(old)[f"switch-offer:{row}"]  # the blocked line
    old.adopt_policy()
    _, said = take(old, "CODE", at_terminal=at_terminal)  # the line that says how to change it later
    assert adopt in said and ".aew/" in said


# ------------------------------------------------------------------------------- adopting only its own (rule 3)

def _second_call(row: switch_offer.SwitchOffer, then: Any) -> switch_offer.SwitchOffer:
    """The row with ``then`` run at its second ``edits``: past the start's trial and `_take`'s re-check, so what it does
    reaches only what comes after them."""
    calls: list[int] = []

    def edits(root: Path) -> dict[str, bytes]:
        calls.append(1)
        if len(calls) == 2:
            then(root)
        return row.edits(root)

    return dataclasses.replace(row, edits=edits)


@pytest.mark.parametrize("row,own,edit", [
    (MUTATING, GATES, lambda data: data.update(non_mutating_concurrency=7)),
    (TABLE, MANIFEST, lambda data: data.setdefault("workspaces", {}).update(root="../somewhere-else"))])
def test_another_edit_of_the_rows_own_file_while_the_prompt_waits_is_not_adopted_with_it(old, at_terminal, monkeypatch,
                                                                                         row, own, edit):
    """`only=` compares names, so the row's own file has to be seen as drifted before the row writes it."""
    only_row(monkeypatch, row)
    at_terminal("CODE")
    rev = old.rev()
    decision, out = start(old)
    path = old.root / ".aew" / own
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(data)
    theirs = yaml.safe_dump(data, sort_keys=False).encode()
    path.write_bytes(theirs)
    decision.apply(old.token)
    assert "is unchanged" in out.getvalue() and own in out.getvalue() and "changed while you answered" in out.getvalue()
    assert path.read_bytes() == theirs and old.rev() == rev
    assert not decisions(old)[-1]["reason"].startswith("switch offer")


@pytest.mark.parametrize("row,theirs", [(MUTATING, GATES), (TABLE, PRICES)])
def test_a_switch_the_operator_changed_after_answering_is_left_as_it_is(old, at_terminal, monkeypatch, row, theirs):
    only_row(monkeypatch, row)
    at_terminal("CODE")
    decision, out = start(old)
    rev = old.rev()
    path = old.root / ".aew" / theirs
    if row == MUTATING:
        path.write_bytes(path.read_bytes().replace(b"mutating_concurrency: 1", b"mutating_concurrency: 7"))
    else:
        path.write_bytes(b"theirs\n")
    held = path.read_bytes()
    decision.apply(old.token)
    assert "left as it is" in out.getvalue() and path.read_bytes() == held and old.rev() == rev


@pytest.mark.parametrize("row", BOTH)
def test_an_unadopted_manifest_refuses_and_is_named(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
    path = old.root / ".aew" / MANIFEST
    path.write_bytes(path.read_bytes() + b"# an edit nobody adopted\n")
    term = at_terminal("CODE")
    decision, out = start(old)
    assert term.prompts == [] and decision.taken == [] and MANIFEST in out.getvalue()
    assert MANIFEST in doctor(old)[f"switch-offer:{row}"]


def test_a_row_whose_own_file_has_an_unadopted_edit_is_not_asked(old, at_terminal, monkeypatch):
    only_row(monkeypatch, MUTATING)
    gates = old.root / ".aew" / GATES
    gates.write_bytes(gates.read_bytes() + b"# a note\n")
    term = at_terminal("CODE")
    _, out = start(old)
    assert term.prompts == [] and GATES in out.getvalue()


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
    guard = old.root / ".aew/policy/guardrails.yaml"
    edited = guard.read_text(encoding="utf-8") + "# arrived after the check\n"
    monkeypatch.setattr(switch_offer, "OFFERS", (_second_call(_rows(row)[0],
                                                              lambda _: guard.write_text(edited, encoding="utf-8",
                                                                                         newline="\n")),))
    before = snapshot(old, *files)
    rev = old.rev()
    term = at_terminal("CODE")
    decision, out = start(old)
    assert term.prompts
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


def test_a_file_it_could_not_put_back_is_named_as_that(old, at_terminal, monkeypatch):
    only_row(monkeypatch, TABLE)
    at_terminal("CODE")
    decision, out = start(old)

    def refused(self: Path, **_: Any) -> None:
        raise PermissionError("the file is locked")

    monkeypatch.setattr(Path, "unlink", refused)
    decision.apply("synthetic-not-the-lead")
    monkeypatch.undo()
    assert PRICES in out.getvalue() and "could not be put back" in out.getvalue()
    assert "changed since" not in out.getvalue()


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


def test_the_offers_answer_discards_what_was_typed_before_it_asks_and_authorize_doesnt(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(operator, "discard_typed_ahead", lambda: seen.append("discard"))

    def reply(prompt: str, timeout: float = 0) -> str:
        seen.append("ask")
        return re.search(r"code ([0-9A-F]{6})", prompt)[1]

    monkeypatch.setattr(operator, "ask", reply)
    operator.answer("switch")
    assert seen == ["discard", "ask"]
    seen.clear()
    operator.authorize("adopt this")  # its behaviour is unchanged: an empty answer only refuses there
    assert seen == ["ask"]


TYPED_AHEAD = """
import os, select, sys, time
pid, fd = os.forkpty()
if pid == 0:
    time.sleep(1.0)  # the start's earlier steps
    from aew import operator
    got = operator.answer("a switch", instruction="Type {code} and Enter", purpose="x", timeout=20)
    os.write(1, f"RESULT declined={got.declined}".encode())
    os._exit(0)
os.write(fd, b"\\n")  # typed before any prompt
buf, sent, end = b"", 0.0, time.time() + 25
while time.time() < end and b"RESULT" not in buf:
    if select.select([fd], [], [], 0.2)[0]:
        try:
            buf += os.read(fd, 4096)
        except OSError:
            break
    if b"Type " in buf and not sent:
        sent = time.time() + 1.5
    if sent and time.time() > sent:  # nothing came of the first Enter: now one typed at the prompt
        sys.stdout.write("NOTHING READ BEFORE THE PROMPT\\n" if b"RESULT" not in buf else "")
        os.write(fd, b"\\n")
        sent = end
    time.sleep(0.05)
os.waitpid(pid, 0)
sys.stdout.write(buf.decode("utf-8", "replace"))
"""


@pytest.mark.skipif(sys.platform == "win32", reason="a pseudo-terminal is POSIX's")
def test_enter_typed_before_the_prompt_shows_isnt_an_answer_and_one_typed_at_it_is():
    """A real pty: the second prompt of a start can meet an Enter meant for the first."""
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}}
    done = subprocess.run([sys.executable, "-c", TYPED_AHEAD], capture_output=True, text=True, env=env, timeout=60,
                          stdin=subprocess.DEVNULL)
    assert "NOTHING READ BEFORE THE PROMPT" in done.stdout, done.stdout + done.stderr
    assert "RESULT declined=True" in done.stdout, done.stdout + done.stderr


IN_THE_BACKGROUND = """
import os, signal, sys, time
pid, fd = os.forkpty()
if pid == 0:
    inner = os.fork()
    if inner == 0:
        os.setpgid(0, 0)  # a background group of this terminal
        from aew import operator
        operator.discard_typed_ahead()
        os._exit(7)
    end = time.time() + 15
    while time.time() < end:
        got, status = os.waitpid(inner, os.WUNTRACED | os.WNOHANG)
        if got:
            if os.WIFSTOPPED(status):
                os.kill(inner, signal.SIGKILL)
            os.write(1, f"RESULT stopped={os.WIFSTOPPED(status)}\\n".encode())
            os._exit(0)
        time.sleep(0.05)
    os.write(1, b"RESULT nothing\\n")
    os._exit(0)
buf = b""
try:
    while b"RESULT" not in buf or b"\\n" not in buf.split(b"RESULT", 1)[1]:
        buf += os.read(fd, 4096)
except OSError:
    pass
os.waitpid(pid, 0)
sys.stdout.write(buf.decode("utf-8", "replace"))
"""


@pytest.mark.skipif(sys.platform == "win32", reason="a pseudo-terminal is POSIX's")
def test_discarding_never_stops_a_process_in_the_background_of_its_terminal():
    """The flush from a background group is SIGTTOU: the process stops, and no timeout wakes it. It held a test run for
    41 minutes until the first version asked whether it was in the foreground."""
    done = subprocess.run([sys.executable, "-c", IN_THE_BACKGROUND], capture_output=True, text=True, timeout=60,
                          stdin=subprocess.DEVNULL)
    assert "RESULT stopped=False" in done.stdout, done.stdout + done.stderr


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
    named = (f".aew/{GATES} mutating_concurrency", f".aew/{MANIFEST} policy.pricing")
    for prompt, changes in zip(term.prompts, named, strict=True):
        assert "credential to" not in prompt and changes in prompt
        assert "Enter alone keeps" in prompt and "won't ask again" in prompt
    assert "Enter alone keeps 1" in term.prompts[0] and "Enter alone keeps no table" in term.prompts[1]


@pytest.mark.parametrize("row", BOTH)
def test_a_declined_offer_is_not_asked_again_and_doctor_keeps_showing_it(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
    term = at_terminal("")
    decision, out = start(old)
    assert decision.taken == [] and "won't ask again" in out.getvalue()
    assert len(term.prompts) == 1
    again = at_terminal("CODE")
    start(old)
    assert again.prompts == []
    assert "Declined switch" in doctor(old)[f"switch-offer:{row}"]
    assert (old.root / ".aew/local/switch-offers.json").is_file()
    label = _rows(row)[0].label
    assert f"{label} keeps" in out.getvalue() and f"{row} keeps" not in out.getvalue()


@pytest.mark.parametrize("row", BOTH)
def test_a_process_that_cant_read_the_answers_says_so_rather_than_pending(old, at_terminal, monkeypatch, row):
    """A contained Lead's `aew doctor` runs in its sandbox, where `.aew/local` is masked: stood in for by moving it."""
    only_row(monkeypatch, row)
    at_terminal("")
    start(old)
    memory = old.root / ".aew/local/switch-offers.json"
    memory.rename(memory.with_suffix(".away"))
    assert "Answered at" in doctor(old)[f"switch-offer:{row}"]
    with process_kind.declared_as("aew (contained Lead)"):
        line = doctor(old)[f"switch-offer:{row}"]
    assert "already answered" in line and "Answered at" not in line


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
@pytest.mark.parametrize("row", BOTH)
def test_a_wrong_code_or_a_timeout_is_not_remembered(old, at_terminal, monkeypatch, reply, row):
    only_row(monkeypatch, row)
    at_terminal(reply)
    decision, out = start(old)
    assert decision.taken == [] and "asked again next start" in out.getvalue()
    assert not (old.root / ".aew/local/switch-offers.json").exists()
    term = at_terminal("")
    start(old)
    assert len(term.prompts) == 1


@pytest.mark.parametrize("row", BOTH)
def test_a_damaged_memory_reads_as_no_answers(old, at_terminal, monkeypatch, row):
    only_row(monkeypatch, row)
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
        "test_row", label="a test row", file=GATES, policy_key="gates",
        key_path=("history_audit", "max_unverified_entries"), old_values=(5,),
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


@pytest.mark.parametrize("contained,steps", [(True, ["readiness", "provider", "tools", "offer", "session"]),
                                              (False, ["readiness", "tools", "offer", "session"])],
                         ids=["contained", "uncontained"])
def test_aew_opencode_wires_the_offer_into_the_session_on_the_start_path_it_takes(monkeypatch, tmp_path, contained,
                                                                                  steps):
    """Asked at `aew opencode`'s start on both paths, after everything else that can refuse and before the seat, and
    what was taken is what the session is given. Linux's only start is the contained one."""
    seen: dict[str, Any] = {}
    order: list[str] = []
    made = switch_offer.Decision()

    class Lead:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def announce(self, _out: Any) -> None:
            pass

        def require_provider(self) -> None:
            order.append("provider")

    def offers(engine: Any, out: Any) -> switch_offer.Decision:
        order.append("offer")
        return made

    def session(engine: Any, argv: Any, **k: Any) -> dict[str, Any]:
        order.append("session")
        seen.update(k)
        return {"ok": True}

    monkeypatch.setenv("AEW_LEAD_TOKEN", "synthetic-not-a-token")
    monkeypatch.setenv("OPENCODE_DB", str(tmp_path / "no-login.db"))
    monkeypatch.setattr(lead, "contained_here", lambda: contained)
    monkeypatch.setattr(lead, "ContainedLead", Lead)
    monkeypatch.setattr(lead, "check_version", lambda: "2.2.6")
    monkeypatch.setattr(lead, "guide_of", lambda engine: "")
    monkeypatch.setattr(lead, "command", lambda engine, extra: ["opencode"])
    monkeypatch.setattr(lead, "_readiness", lambda engine: order.append("readiness"))
    monkeypatch.setattr(lead, "_tools_before_the_tui", lambda **k: order.append("tools"))
    monkeypatch.setattr(switch_offer, "at_lead_start", offers)
    monkeypatch.setattr(lead_broker, "run_session", session)
    engine_ = type("E", (), {"execution_policy": lambda self: ({"containment": {"mode": "allow_weaker"}}, None)})()
    lead.run(engine_, acquire=False, session_label=None, keep_seat=False, provider_env=[], extra_args=[],
             print_config=False)
    assert seen["with_token"] == made.apply
    assert order == steps


def test_aew_doctor_shows_the_offer_through_the_real_command(old):
    res = run_aew("-C", str(old.root), "doctor", "--json")
    rows = {r["check"]: r for r in json.loads(res.stdout)["checks"]}
    assert rows[f"switch-offer:{MUTATING}"]["status"] == "PASS"
    assert "Switch offer: mutating concurrency, 1 -> " in rows[f"switch-offer:{MUTATING}"]["detail"]
    assert "Switch offer: the price table, no table -> " in rows[f"switch-offer:{TABLE}"]["detail"]


@pytest.mark.parametrize("row", BOTH)
def test_a_start_refused_after_the_answer_writes_nothing(old, at_terminal, monkeypatch, row):
    """A real refusal: the real session, asked to acquire a seat that is really held."""
    only_row(monkeypatch, row)
    _fake_session(monkeypatch)
    before = snapshot(old, GATES, PRICES, MANIFEST)
    rev = old.rev()
    at_terminal("CODE")
    decision, _ = start(old)
    assert decision.taken
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    with pytest.raises(AEWError):
        lead_broker.run_session(decision.engine, ["harness"], acquire=True, session_label=None, keep_seat=True, env={},
                                contained=_contained, with_token=decision.apply)
    assert snapshot(old, GATES, PRICES, MANIFEST) == before and old.rev() == rev
    term = at_terminal("")
    start(old)
    assert len(term.prompts) == 1  # asked again


def test_a_project_init_really_wrote_before_the_defaults_moved_takes_both_and_ends_clean(old, at_terminal):
    """The files `aew init` wrote at the commit before either default moved, frozen: what an existing project really
    holds, where `old` builds its files from today's. Only these two: no row reads the rest."""
    for name, rel in (("gates.yaml", GATES), (MANIFEST, MANIFEST)):
        (old.root / ".aew" / rel).write_bytes((FROZEN / name).read_bytes())
    old.adopt_policy()
    assert [s.offer.switch for s in switch_offer.standings(engine(old))] == BOTH
    term, said = take(old, "CODE", "CODE", at_terminal=at_terminal)
    assert len(term.prompts) == 2 and doctor(old) == {}, said
    state = load_control(old.root)
    assert engine(old).policy_pin_drift(state) == [] and engine(old).manifest_pin_ok(state)
    assert engine(old)._k.policy("gates")["mutating_concurrency"] == DEFAULT_GATES["mutating_concurrency"]
    assert engine(old).manifest["policy"]["pricing"] == PRICES


def test_nothing_about_the_offer_stops_the_start(old, at_terminal, monkeypatch):
    def boom(_root: Path) -> None:
        raise RuntimeError("a broken row")

    row = switch_offer.SwitchOffer(switch="broken", label="broken", legality=False, opening=boom, edits=boom,
                                   text=lambda o: "", changes="", done=lambda o: "", by_hand=lambda o: "")
    monkeypatch.setattr(switch_offer, "OFFERS", (row,))
    at_terminal("CODE")
    decision, out = start(old)
    assert decision.taken == [] and "could not be read" in out.getvalue()

    fine = dataclasses.replace(row, opening=lambda _r: switch_offer.Opening("a", "b"), edits=lambda _r: {},
                               text=lambda o: "t")
    monkeypatch.setattr(switch_offer, "OFFERS", (_second_call(fine, boom),))
    at_terminal("CODE")
    decision, out = start(old)
    assert len(decision.taken) == 1
    decision.apply(old.token)  # the second edits raises RuntimeError: said, never raised
    assert "the offer for broken failed" in out.getvalue()


def test_a_row_that_breaks_ends_that_row_and_not_the_next(old, at_terminal, monkeypatch):
    first, second = switch_offer.OFFERS

    def boom(_opening: Any) -> str:
        raise RuntimeError("a row's text")

    monkeypatch.setattr(switch_offer, "OFFERS", (dataclasses.replace(first, text=boom), second))
    term = at_terminal("")
    _, out = start(old)
    assert "could not be read" in out.getvalue() and len(term.prompts) == 1


def test_an_edit_that_stops_being_possible_after_the_answer_says_how_by_hand(old, at_terminal, monkeypatch):
    row = _rows(TABLE)[0]

    def hand(_root: Path) -> None:
        raise switch_offer.HandChange("it can't be edited now")

    monkeypatch.setattr(switch_offer, "OFFERS", (_second_call(row, hand),))
    rev = old.rev()
    _, said = take(old, "CODE", at_terminal=at_terminal)
    assert "is unchanged: it can't be edited now" in said and "default_pricing.yaml" in said and old.rev() == rev


def test_to_value_is_the_owners_default(old, monkeypatch):
    row = _rows(MUTATING)[0]
    monkeypatch.setitem(DEFAULT_GATES, "mutating_concurrency", 7)
    assert row.opening(old.root / ".aew") == switch_offer.Opening("1", "7")
    assert yaml.safe_load(row.edits(old.root / ".aew")[GATES])["mutating_concurrency"] == 7
