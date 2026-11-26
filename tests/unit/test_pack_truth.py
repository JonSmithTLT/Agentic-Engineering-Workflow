"""What a worker reads is true: plain asserts over the text as AEW renders it (operator, 2026-11-04: a false line in a
pack or preamble is a product defect).

Each guard is a function of the rendered text or the role's definition, so its planted cases run the same code:
- a pack promises only sections it has, and each archetype's knowledge list is sections its pack can have;
- every operation in a pack's allowed list and every `aew` command a worker's text prints is one its custody bridge
  offers, and each `submit.<kind>` listed is a kind the engine accepts from that role at that scope. Its limit: a
  card's "Restricted to operations" line is not read (the built-in `plan_assessor` card restricts; its allowed list,
  which the guard reads, is derived from the same restriction);
- no worker's text both asks for a credential and says there is none, and neither the preamble nor the pack corrects
  the other about it. Its limit: the system text's skill lines qualify the pack's on purpose (ADR-0006, amendment
  2026-11-05), which no guard here reads;
- a report format is what the engine accepts as it stands, its other values listed beside it from what the engine
  validates, and it names no scope (the engine fills in the dispatched one);
- a role that may not change the tree it evaluates is told what a check that writes there does to its submission;
- an evaluating role's instructions fit its scope: none names an input its pack there does not carry (a diff, check
  output, open findings), and none asks for a field its scope's report refuses (register E366);
- no pack sends a role to its shell for a capability that one of its own operations serves (a check it may run is its
  targeted test execution, and the only run whose evidence it can cite), and each such capability is named with the
  command for it (register E368). Its limit: the capabilities are those ``evidence.OPERATION_CAPABILITIES`` lists, and a
  line counts as sending to the shell when it has the word;
- a run's system text says what its first message holds: each text of that message, in order, by the heading it
  starts with (register E368), prints only commands on the bridge and asks for no credential;
- a role with no credential is told to stop, never to get one, and what an archetype tells any role asks for no
  credential and names only commands that parse (D2 does not scan these two).

The matrix is every dispatchable archetype, every scope it runs at and every built-in card, each with all of its
optional inputs and with none, so a section that depends on the scope or the data is seen both ways.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

import pytest
from discovery import rules

from aew import roles
from aew.cli.work_commands import NO_INVOCATION_AUTHORITY
from aew.errors import AEWError, UsageError
from aew.harness import bridge
from aew.harness import contract as K
from aew.harness.opencode import projection
from aew.knowledge import context as ctx
from aew.knowledge import evidence as E
from aew.schemas import schema, validate_property
from aew.util import load_yaml

SCOPES = {"implementer": ["ticket"],
          "reviewer": ["ticket", "observation", "parent", "integration", E.ASSESSMENT_SCOPE],
          "verifier": ["ticket", "observation", "parent", "integration"], "investigator": ["observation"],
          "researcher": ["observation"], "planner": ["observation"]}
DISPATCHABLE = [name for name in roles.ARCHETYPES if roles.archetype(name).get("dispatchable")]
PROMISE = "- Required knowledge (included below): "
SECTION = {"implementation_report": "implementation", "review": "review", "verification": "verification",
           "discovery_record": "discovery", "research_record": "research", "plan_proposal": "proposal",
           E.PLAN_ASSESSMENT: "assessment"}
CARDS = sorted(roles.builtin_cards().items())


def inputs(role: str, scope: str, *, full: bool, role_def: dict[str, Any] | None = None,
           card: dict[str, Any] | None = None) -> ctx.PackInputs:
    optional: dict[str, Any] = {}
    if full:
        optional = {
            "inputs": [{"id": "E-1", "kind": "discovery_record", "from": "T-1", "freshness": "CURRENT", "basis": "b",
                        "summary": ["fact: f"]}],
            "failure_evidence": {"id": "E-2", "result": "fail", "claims": [], "suspected_cause": None},
            "codebase_map": ["## Codebase map", "", "a row"],
            "hierarchy": [{"id": "S-1", "kind": "story", "title": "t", "risk_class": 1}],
            "history": [{"id": "H-1", "sha256": "0" * 64, "kind": "review", "source": "s", "reason": "r",
                         "content": "x: y"}],
            "subject": {"id": "E-3", "kind": "discovery_record", "sha256": "0" * 64, "content": "x: y"},
            "children": [{"id": "T-2", "kind": "ticket", "state": "DONE", "title": "t", "integrated_commit": "1" * 40,
                          "diff": "+a line"}],
            "request": [{"id": "S-1", "kind": "story", "title": "t", "body": "the request",
                         "acceptance": {"goal_backwards": ["g"]}}],
        }
    return ctx.PackInputs(
        invocation_id="INV-1", role=role, role_def=role_def or roles.archetype(role), work_id="T-1", title="a title",
        scope=scope, specialty=None, workspace="/ws/T-1",
        snapshot={"relevant_inputs_fingerprint": "tree:0", "workspace_id": "ws-0", "base_revision": "0" * 40},
        record_meta={"initial_risk_class": 1, "acceptance": {"goal_backwards": ["g"], "contract": ["c"]},
                     "scope": {"paths": ["src/**"]}},
        record_body="a body", plan={"accepted": 1, "sha256": "0" * 64}, plan_text="a plan", guardrails_text="",
        checks={"unit": {"configured": True, "description": "unit tests"}}, authority=[], card=card, **optional)


def card_scopes(card: roles.Card) -> list[str]:
    """The scopes a card is dispatched at: those whose report it writes (a plan assessor's card only at the assessor's
    scope, a code reviewer's never there; ``evidence.kinds_for``)."""
    outputs = set(card.meta.get("outputs") or roles.archetype(card.archetype)["evidence_kinds"])
    return [s for s in SCOPES[card.archetype] if outputs & E.kinds_for(card.archetype, s)]


def matrix() -> list[tuple[str, str, bool, dict[str, Any] | None]]:
    cases: list[tuple[str, str, bool, dict[str, Any] | None]] = []
    cases += [(role, scope, full, None) for role in DISPATCHABLE for scope in SCOPES[role] for full in (True, False)]
    cases += [(c.archetype, scope, True, c.meta) for _, c in CARDS for scope in card_scopes(c)]
    return cases


def launch(pack: str, role: str, scope: str = "ticket", card: dict[str, Any] | None = None) -> K.LaunchContract:
    """A harness run's contract for ``pack``, as ``harness_contract`` records a card's lists (``extra``)."""
    card = card or {}
    return K.LaunchContract(
        run="R-INV-1-1", invocation="INV-1", work_unit="T-1", role=role, scope=scope,
        card={"id": card["role"]} if card else None,
        execution_profile={}, workspace="/ws/T-1", expected_kinds=sorted(E.kinds_for(role, scope)),
        operations=sorted(E.submit_operations(roles.archetype(role)["engine_operations"], role, scope)),
        pack_path="/p", pack_sha256="0" * 64,
        pack_text=pack, continuation={"previous_runs": ["R-INV-1-0"], "evidence": [], "changed_paths": []},
        run_dir="/r", scratch="/s",
        extra={"card_skills": card.get("skills") or [], "card_optional_skills": card.get("optional_skills") or []})


def prompt(pack: str, role: str, scope: str = "ticket") -> str:
    """The whole text a harness run's worker is given as its first message."""
    return launch(pack, role, scope).prompt


def system(contract: K.LaunchContract) -> str:
    """The run's system text (OpenCode's, the one built-in adapter), with the skills its card's lists give it."""
    return projection.system_text(contract, projection.skills(contract))


# ------------------------------------------------------------------------------------- the guards


def knowledge_gaps(role: str, role_def: dict[str, Any], scopes: list[str]) -> list[str]:
    """Names in the archetype's list that no pack of this role, with everything it can hold, has a section for."""
    delivered = {s.name for scope in scopes
                 for s in ctx.sections(inputs(role, scope, full=True, role_def=role_def))}
    return [name for name in role_def["context"]["knowledge"] if ctx.KNOWLEDGE_SECTIONS.get(name) not in delivered]


def false_promises(p: ctx.PackInputs) -> list[str]:
    """Names the rendered pack promises and does not have."""
    parts = ctx.sections(p)
    line = next(ln for part in parts for ln in part.head if ln.startswith(PROMISE))
    names = [n for n in line.removeprefix(PROMISE).split(", ") if n]
    delivered = {s.name for s in parts}
    return [n for n in names if ctx.KNOWLEDGE_SECTIONS.get(n) not in delivered]


def operations_off_the_bridge(text: str, role: str = "reviewer", scope: str | None = "ticket") -> list[str]:
    """Operations in the pack's allowed list, and `aew` commands in ``text``, that the bridge lacks, and each
    `submit.<kind>` listed for a kind the engine refuses this role at this scope (``evidence.kinds_for``; #581 review,
    F1). A prohibition may name what only the Lead runs (the planner's `aew plan adopt`): it tells the worker not to, so
    it is not scanned."""
    allowed = re.search(r"^### Allowed engine operations\n+((?:- .*\n?)+)", text, re.M)
    missing = []
    for op in re.findall(r"^- (\S+)$", allowed.group(1) if allowed else "", re.M):
        key = "submit" if op.startswith("submit.") else op
        if key not in bridge.OPERATIONS and op != "(none)":
            missing.append(op)
        elif key == "submit" and op.removeprefix("submit.") not in E.kinds_for(role, scope):
            missing.append(op)
    offered = re.sub(r"^(?:### Prohibited|Additional prohibitions:)\n+(?:- .*\n?)+", "", text, flags=re.M)
    for suggestion in rules.suggestions(rules.Output(site="unit", plane=rules.MODEL, text=offered)):
        argv = list(suggestion.argv)
        if argv[:1] == ["-C"]:
            argv = argv[2:]
        if not ({".".join(argv[:2]), *argv[:1]} & set(bridge.OPERATIONS)):
            missing.append(suggestion.text)
    return missing


def asks_for_a_credential(text: str) -> bool:
    return bool(rules.o_secret(text, rules.MODEL))


def says_there_is_none(text: str) -> bool:
    return "no credential" in text.lower()


def report_format_problems(pack: str, role: str, scope: str | None = None) -> list[str]:
    """Why the pack's report format is not what the engine accepts as it stands (a `<...>` placeholder is a string to
    the schema, so filling those in is all a copy needs), or does not list a field's other values."""
    fence = re.search(r"^```markdown\n---\n(.*?)\n---\n", pack, re.S | re.M)
    if fence is None:
        return ["no report format"]
    meta = load_yaml(fence.group(1))
    kind = ctx.output_template(role, scope)[0]
    assert kind is not None
    problems = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str) and "#" in value:
            problems.append(f"a comment inside a value: {value}")

    walk(meta)
    section = meta.get(SECTION[kind]) or {}
    if "scope" in section:
        problems.append("names a scope")
    try:
        E.check_submission(role, kind, meta, scope=scope)
        filled = {"scope": "ticket", **section} if kind == "verification" else section  # as the engine fills it
        validate_property("evidence", SECTION[kind], filled, source="the template")
    except AEWError as exc:
        problems.append(exc.message)
    allowed = ctx._allowed_values(role, scope)
    if "result" in meta and meta["result"] not in allowed["result"]:
        problems.append(f"result {meta['result']!r} is refused")
    listed = next((ln for ln in pack.splitlines() if ln.startswith("Allowed values: ")), "")
    problems += [f"{name} does not list {value}" for name, values in allowed.items() for value in values
                 if not re.search(rf"`{name}` is [^;]*\b{value}\b", listed)]
    return problems


def commands_in(text: str) -> list[rules.Suggestion]:
    return rules.suggestions(rules.Output(site="unit", plane=rules.MODEL, text=text))


def asks_or_misprints(text: str) -> list[str]:
    """Each credential ask in ``text``, and each command in it that does not parse as printed, placeholders as values
    (O-SECRET and O-CMD, on text D2 does not scan). Prose may name a command without its required arguments."""
    problems = rules.o_secret(text, rules.MODEL) + rules.o_secret(text, rules.OPERATOR)
    return problems + [p for s in commands_in(text) if (p := rules.o_cmd(s))]


def archetype_prose(role: str) -> str:
    """Every sentence an archetype tells a role, one to a line."""
    definition = roles.archetype(role)
    return "\n".join(line for key in ("authority", "responsibilities", "prohibited", "outputs")
                     for line in definition.get(key) or [])


# Words in a role's instructions that send it to an input, each with the pack sections that deliver that input
# (register E366): an instruction may name one only where its pack has one of them. A diff is the change's, or a
# child's integrated one in a parent's child work ("child-diffs": the children section holding one).
INPUTS = {r"\bdiffs?\b": {"change", "child-diffs"}, r"\b(?:the|this) change\b": {"change"},
          r"\bcheck (?:output|results)\b": {"check-results"},
          r"\b(?:earlier|open) (?:review )?findings\b|\bre-review": {"open-findings"}}
# The roles that evaluate another's work from what their pack carries. An implementer's diff is its own workspace's,
# never a pack input, so its words name no input here.
EVALUATORS = {"reviewer", "verifier"}
# Words that ask a role for a report field, each with the field: the scope's report must take it (its schema section).
FIELDS = {r"\bresolved\b": "resolved_findings"}


def instructions(p: ctx.PackInputs) -> str:
    """What the pack tells the role to do: its contract (authority, responsibilities, completion criteria) and its
    card, never the sections that carry the inputs themselves, nor the card's selection guidance (the Lead's)."""
    return "\n".join(line for s in ctx.sections(p) if s.name in {"contract", "role-card"} for line in s.head
                     if not line.startswith("Selection guidance"))


def scope_misfits(p: ctx.PackInputs) -> list[str]:
    """Each instruction that names an input the pack at its scope does not deliver, or asks for a field the scope's
    report refuses."""
    if p.role not in EVALUATORS:
        return []
    delivered = {s.name for s in ctx.sections(p)}
    delivered |= {"child-diffs"} if "children" in delivered and ctx.child_diffs(p) else set()
    text = instructions(p)
    out = [f"names {' or '.join(sorted(sections))} ({m.group(0)!r}), which this pack does not deliver"
           for word, sections in INPUTS.items() if not sections & delivered for m in [re.search(word, text, re.I)] if m]
    kind = ctx.output_template(p.role, p.scope)[0]
    if kind:
        section = schema("evidence")["properties"][SECTION[kind]]
        out += [f"asks for {field} ({m.group(0)!r}), which a {kind} refuses" for word, field in FIELDS.items()
                if field not in (section.get("properties") or {}) for m in [re.search(word, text, re.I)] if m]
    return out


def allowed_operations(pack: str) -> list[str]:
    block = re.search(r"^### Allowed engine operations\n+((?:- .*\n?)+)", pack, re.M)
    return re.findall(r"^- (\S+)$", block.group(1) if block else "", re.M)


def sent_to_the_shell_for_what_an_operation_serves(pack: str) -> list[str]:
    """Each capability a line of ``pack`` sends the role to its shell for, although one of the operations the pack
    allows it serves that capability (``evidence.OPERATION_CAPABILITIES``): the shell run records nothing it can cite.
    Any line with the word counts, not one template's."""
    served = E.served_by_operation(allowed_operations(pack))
    return [f"{capability} ({operation})" for line in pack.splitlines() if re.search(r"\bshell\b", line, re.I)
            for capability, operation in served.items() if re.search(rf"\b{capability}\b", line)]


def first_message_misdescribed(text: str, parts: list[str]) -> list[str]:
    """Why what ``text`` says the first message holds is not what it is. ``parts``: the texts of that message, in
    order. The sentence names each by the heading it starts with, in that order, and nothing else."""
    said = re.search(r"\bThe first message [^.]*\.", text)
    named = re.findall(r'"(# [^"]+)"', said.group(0)) if said else []
    starts = [next((h for h in named if part.startswith(h)), None) for part in parts]
    out = [f"does not name the text that starts {part.splitlines()[0]!r}"
           for part, h in zip(parts, starts, strict=True) if h is None]
    if not out and named != starts:
        out.append(f"names {named}, and the message holds {starts}")
    return out


def check_trap(pack: str, role: str) -> str | None:
    """What is wrong with what ``pack`` says about a check that writes, if anything."""
    offered, said = ctx.OPERATION_COMMANDS["check.run"] in pack, ctx.CHECK_WRITES_NOTE in pack
    if offered and role != "implementer" and not said:
        return "unsaid"
    if said and (not offered or role == "implementer"):
        return "said where it does not apply"
    return None


# ------------------------------------------------------------------------------------- the real text


@pytest.mark.parametrize("role", DISPATCHABLE)
def test_every_name_in_an_archetypes_knowledge_list_is_a_section_its_pack_can_have(role):
    assert knowledge_gaps(role, roles.archetype(role), SCOPES[role]) == []


def test_the_archetypes_without_a_pack_are_the_ones_not_dispatchable():
    """Lead and frontier_advisor list knowledge too, but no dispatch renders a pack for them: nothing there is promised
    to a reader, and a role that becomes dispatchable joins the matrix above."""
    assert set(roles.ARCHETYPES) - set(DISPATCHABLE) == {"lead", "frontier_advisor"}
    assert set(DISPATCHABLE) == set(SCOPES) == set(ctx.OUTPUT_TEMPLATES)


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_a_pack_promises_only_the_sections_it_has(role, scope, full, card):
    assert false_promises(inputs(role, scope, full=full, card=card)) == []


def test_a_section_that_is_absent_is_not_promised_and_one_that_is_present_is():
    def promise(p: ctx.PackInputs) -> list[str]:
        return next(ln for ln in ctx.render(p).splitlines() if ln.startswith(PROMISE)).removeprefix(PROMISE).split(", ")

    ticket = promise(inputs("reviewer", "ticket", full=False))
    assert {"change_diff", "check_results", "implementation_structured_summary"} <= set(ticket)
    parent = promise(inputs("reviewer", "parent", full=False))
    assert not {"change_diff", "check_results", "implementation_structured_summary"} & set(parent)
    assert "failure_evidence" not in promise(inputs("implementer", "ticket", full=False))
    assert "failure_evidence" in promise(inputs("implementer", "ticket", full=True))
    assert "codebase_map" not in promise(inputs("investigator", "observation", full=False))
    assert "codebase_map" in promise(inputs("investigator", "observation", full=True))


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_every_operation_a_workers_text_names_is_on_its_bridge(role, scope, full, card):
    text = prompt(ctx.render(inputs(role, scope, full=full, card=card)), role, scope)
    assert operations_off_the_bridge(text, role, scope) == []


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_a_workers_text_never_asks_for_a_credential_and_says_there_is_none(role, scope, full, card):
    pack = ctx.render(inputs(role, scope, full=full, card=card))
    text = prompt(pack, role)
    assert says_there_is_none(text)  # the harness run's one statement of the fact
    assert not asks_for_a_credential(text)
    # One owner: the variable is named by neither text, so neither has to correct the other.
    assert "AEW_INVOCATION_TOKEN" not in text
    assert not says_there_is_none(pack) and not asks_for_a_credential(pack)  # a pack serves both modes: it is silent


@pytest.mark.parametrize("role", DISPATCHABLE)
def test_context_read_is_the_only_operation_left_off_the_list(role):
    """So a new operation with no bridge entry is a failure here, not a line quietly missing from every pack."""
    operations = roles.archetype(role)["engine_operations"]
    assert set(operations) - set(ctx._on_the_bridge(operations)) == {"context.read"}


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_a_report_format_is_what_the_engine_accepts_and_lists_the_other_values(role, scope, full, card):
    assert report_format_problems(ctx.render(inputs(role, scope, full=full, card=card)), role, scope) == []


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_a_roles_instructions_fit_its_scope(role, scope, full, card):
    """Register E366: no instruction sends a role to an input its pack at that scope does not carry (a diff, check
    output, earlier findings), and none asks for a field the scope's report refuses (a plan assessment's
    `resolved_findings`)."""
    assert scope_misfits(inputs(role, scope, full=full, card=card)) == []


@pytest.mark.parametrize(("text", "problem"), [
    ("- evaluate the change against the requirement, diff and check output", "names change"),
    ("- when re-reviewing, state which earlier findings are resolved", "names open-findings"),
    ("- state which findings are resolved", "asks for resolved_findings"),
    ("- trace every requirement to the plan", None),
])
def test_the_scope_fit_guard_right_wrong_and_missing(monkeypatch, text, problem):
    """Planted lines in an assessor's contract: each misfit is named; a line that fits is not."""
    p = inputs("reviewer", E.ASSESSMENT_SCOPE, full=False)
    monkeypatch.setitem(p.role_def, "responsibilities", [*p.role_def["responsibilities"], text.removeprefix("- ")])
    found = scope_misfits(p)
    assert found == [] if problem is None else any(problem in f for f in found), found


@pytest.mark.parametrize(("name", "card"), CARDS)
def test_a_card_says_responsibilities_of_its_own_only_when_it_has_some(name, card):
    """Review m3: a card without responsibilities (the plan assessor's are its scope's) gets no empty block for them."""
    head = "\n".join(next(s.head for s in ctx.sections(inputs(card.archetype, card_scopes(card)[0], full=False,
                                                                card=card.meta)) if s.name == "role-card"))
    assert ("Card responsibilities" in head) is bool(card.meta.get("responsibilities")), name


@pytest.mark.parametrize("diffs", [True, False])
def test_a_parent_reviewer_is_told_to_evaluate_each_childs_diff_only_where_its_pack_carries_one(diffs):
    """Register E366, review m1: a parent's child work carries each child's integrated diff, so the change duty is
    given for it there, with no check results (a parent pack has none)."""
    p = inputs("reviewer", "parent", full=True)
    if not diffs:
        p = dataclasses.replace(p, children=[{k: v for k, v in c.items() if k != "diff"} for c in p.children])
    text = instructions(p)
    assert ("evaluate each child's integrated change below; look for defects" in text) is diffs, text
    assert "check results" not in text


@pytest.mark.parametrize(("text", "problem", "diffs"), [
    ("- check each child's integrated diff", None, True),
    ("- check each child's integrated diff", "names change or child-diffs", False),
    ("- evaluate this change", "names change", True),
    ("- read the check output", "names check-results", True),
])
def test_a_parents_child_diffs_are_a_diff_it_may_name_and_nothing_more(monkeypatch, text, problem, diffs):
    """Planted lines in a parent reviewer's contract: its child work carries each child's integrated diff when one is
    there (``_children``), never the change under review or check output."""
    p = inputs("reviewer", "parent", full=True)
    if not diffs:
        p = dataclasses.replace(p, children=[{k: v for k, v in c.items() if k != "diff"} for c in p.children])
    monkeypatch.setitem(p.role_def, "responsibilities", [*p.role_def["responsibilities"], text.removeprefix("- ")])
    found = scope_misfits(p)
    assert found == [] if problem is None else any(problem in f for f in found), found


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_no_pack_sends_a_role_to_its_shell_for_what_one_of_its_operations_serves(role, scope, full, card):
    """Register E368 (the worker-pack audit's F3): the verifier's card listed targeted test execution among what "no
    tool of AEW's serves (use your shell ...)", and a shell run is no evidence its report can cite."""
    assert sent_to_the_shell_for_what_an_operation_serves(ctx.render(inputs(role, scope, full=full, card=card))) == []


@pytest.mark.parametrize(("name", "card"), CARDS)
def test_a_capability_an_operation_serves_is_named_with_its_command_only_for_a_role_that_holds_it(name, card):
    """A card's capability that one of its role's operations serves is printed with that operation's command; a role
    without the operation (a reviewer has no ``check.run``) is not offered the command."""
    scope = card_scopes(card)[0]
    pack = ctx.render(inputs(card.archetype, scope, full=False, card=card.meta))
    requested = [*card.meta.get("required_capabilities", []), *card.meta.get("optional_capabilities", [])]
    served = E.served_by_operation(allowed_operations(pack))
    line = next((ln for ln in pack.splitlines() if ln.startswith("Capabilities an AEW command serves")), "")
    for capability in requested:
        command = f"{capability} ({ctx.OPERATION_COMMANDS[served[capability]]})" if capability in served else None
        assert (command is not None and command in line) or (command is None and capability not in line), (name, line)
    assert bool(line) is bool(set(requested) & set(served)), name


def test_a_card_whose_role_lacks_the_operation_keeps_the_capability_on_the_shell_line():
    """The limit, stated: a reviewer's card that asks for targeted test execution has no ``check.run`` to serve it, so
    the pack still says no tool serves it. Whether such a role should run tests at all is the card author's."""
    card = {**roles.builtin_cards()["code_reviewer"].meta, "required_capabilities": [E.CHECK_CAPABILITY]}
    pack = ctx.render(inputs("reviewer", "ticket", full=False, card=card))
    assert f"commands): {E.CHECK_CAPABILITY}" in pack and "Capabilities an AEW command serves" not in pack
    assert sent_to_the_shell_for_what_an_operation_serves(pack) == []


@pytest.mark.parametrize(("line", "found"), [
    ("Capabilities no tool of AEW's serves (use your shell and the project's own commands): build_execution", []),
    ("Capabilities no tool of AEW's serves (use your shell and the project's own commands): targeted_test_execution, "
     "inspect_authoritative_state", ["targeted_test_execution (check.run)"]),
    ("- run targeted_test_execution in your Shell, then report", ["targeted_test_execution (check.run)"]),
    ("Capabilities an AEW command serves: targeted_test_execution (`aew check run <check-id>`)", []),
])
def test_the_mechanism_guard_right_wrong_and_missing(line, found):
    """Planted lines beside a list that allows ``check.run``; and with no such operation allowed, nothing is found."""
    assert sent_to_the_shell_for_what_an_operation_serves(
        f"### Allowed engine operations\n- check.run\n- submit.verification\n\n{line}\n") == found
    assert sent_to_the_shell_for_what_an_operation_serves(
        f"### Allowed engine operations\n- submit.review\n\n{line}\n") == []


def test_every_operation_that_serves_a_capability_has_a_command_and_is_on_the_bridge():
    """The two tables agree, and the check command is the one the check guard reads. That a real check's evidence
    names ``evidence.CHECK_CAPABILITY`` as its method is read from one in
    ``test_evidence_gates.test_the_operators_check_run_runs_in_a_sandbox_of_its_own_and_records_its_label`` (#613
    review, m4). Limit (n3): the first line restates the table, so a new operation that serves a capability fails
    nothing here until it is added."""
    assert E.OPERATION_CAPABILITIES == {"check.run": (E.CHECK_CAPABILITY,)}
    assert set(ctx.OPERATION_COMMANDS) == set(E.OPERATION_CAPABILITIES) <= set(bridge.OPERATIONS)
    assert check_trap(f"{ctx.OPERATION_COMMANDS['check.run']}\n{ctx.CHECK_WRITES_NOTE}", "verifier") is None


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_a_runs_system_text_says_what_its_first_message_holds(role, scope, full, card):
    """Register E368 (the worker-pack audit's F4): the first message is the run's preamble and then the pack, and the
    system text said it "is your AEW launch contract". The same text prints only commands on the bridge and asks for
    no credential: the third text a worker is always sent, held to what the other two are."""
    contract = launch(ctx.render(inputs(role, scope, full=full, card=card)), role, scope, card)
    text = system(contract)
    assert contract.prompt.startswith(K.preamble(contract) + "\n\n" + contract.pack_text)
    assert first_message_misdescribed(text, [K.preamble(contract), contract.pack_text]) == []
    assert operations_off_the_bridge(text, role, scope) == []
    assert says_there_is_none(text) and not asks_for_a_credential(text)


@pytest.mark.parametrize(("sentence", "problem"), [
    ('The first message is rules ("# AEW harness run"), then your contract ("# AEW launch contract").', None),
    ("The first message is your AEW launch contract. It is authoritative.", "does not name the text that starts"),
    ('The first message is your launch contract ("# AEW launch contract").', "'# AEW harness run R-INV-1-1'"),
    ('The first message is your contract ("# AEW launch contract"), then the rules ("# AEW harness run").', "names ["),
    ('The first message is rules ("# AEW harness run"), a map ("# Map") and a contract ("# AEW launch contract").',
     "names ["),
    ("You are a bounded reviewer.", "does not name the text that starts"),
])
def test_the_first_message_guard_right_wrong_and_missing(sentence, problem):
    contract = launch(ctx.render(inputs("reviewer", "ticket", full=False)), "reviewer")
    found = first_message_misdescribed(sentence, [K.preamble(contract), contract.pack_text])
    assert found == [] if problem is None else any(problem in f for f in found), found


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_a_role_that_may_not_change_its_tree_is_told_what_a_check_that_writes_does(role, scope, full, card):
    assert check_trap(ctx.render(inputs(role, scope, full=full, card=card)), role) is None


def test_a_role_with_no_credential_is_told_to_stop_and_never_to_get_one():
    assert asks_or_misprints(NO_INVOCATION_AUTHORITY) == []
    assert [s.argv for s in commands_in(NO_INVOCATION_AUTHORITY)] == [("harness", "launch"), ("whoami", "--help")]
    assert "stop and report" in NO_INVOCATION_AUTHORITY
    assert "AEW_INVOCATION_TOKEN" not in NO_INVOCATION_AUTHORITY
    # Printed bare, it adds no id placeholder; so it says where the arguments are, and the route with no invocation yet.
    assert "dispatches it with `--launch`" in NO_INVOCATION_AUTHORITY
    assert "`aew harness launch` (see its `--help`)" in NO_INVOCATION_AUTHORITY


def test_the_refusal_adds_nothing_d2_would_list_beyond_an_unstructured_refusal():
    """The refusal's text is clean of every rule but O-WORDS, which it has always had: no id to fill in."""
    refusal = {"code": "USAGE", "message": NO_INVOCATION_AUTHORITY, "details": {}}
    found = rules.check(rules.Output(site="cli:aew whoami|USAGE", plane=rules.MODEL, refusal=refusal))
    assert [f.rule for f in found] == ["O-WORDS"], found


def test_check_run_with_no_credential_refuses_the_same_way(monkeypatch):
    for name in ("AEW_INVOCATION_TOKEN", bridge.ENV_ENDPOINT, bridge.ENV_KEY):
        monkeypatch.delenv(name, raising=False)
    args = rules.parse(["check", "run", "unit"], complete=True)
    with pytest.raises(UsageError) as refused:
        args.handler(args)
    assert refused.value.message == NO_INVOCATION_AUTHORITY


@pytest.mark.parametrize("role", roles.ARCHETYPES)
def test_an_archetype_asks_for_no_credential_and_names_only_commands_that_parse(role):
    assert asks_or_misprints(archetype_prose(role)) == []


def test_the_lead_is_told_to_launch_by_every_route_that_dispatches_and_each_takes_the_flag():
    """Which route applies is the guide's: this holds that the line names them all and that `--launch` is real on each,
    not that a route fits a given unit."""
    lines = [line for line in archetype_prose("lead").splitlines() if "`--launch`" in line]
    assert len(lines) == 1
    routes = [s.argv for s in commands_in(lines[0])]
    assert routes == [("work", "assign"), ("work", "dispatch"), ("invoke", "create"), ("guide",)]
    for route in routes[:-1]:
        whole = (*route, "<T>", "--launch", "--expect-rev", "<revision from aew status>")
        assert rules.o_cmd(rules.Suggestion(whole, " ".join(whole), structured=True)) is None


@pytest.mark.parametrize(("role", "says"), [("planner", False), ("investigator", True), ("researcher", True)])
def test_only_a_role_with_a_question_is_told_a_pass_answers_it(role, says):
    pack = ctx.render(inputs(role, "observation", full=False))
    assert ("the question is answered" in pack) is says


# ------------------------------------------------------------------------------------- planted cases


def test_the_knowledge_guard_finds_a_name_with_no_section_and_one_whose_section_this_role_never_has():
    right = roles.archetype("planner")
    missing = {**right, "context": {**right["context"], "knowledge": ["requirement", "open_questions"]}}
    wrong = {**right, "context": {**right["context"], "knowledge": ["requirement", "failure_evidence"]}}
    assert knowledge_gaps("planner", right, ["observation"]) == []
    assert knowledge_gaps("planner", missing, ["observation"]) == ["open_questions"]
    assert knowledge_gaps("planner", wrong, ["observation"]) == ["failure_evidence"]


@pytest.mark.parametrize(("promised", "gaps"), [("guardrails", []), ("change_diff", ["change_diff"]),
                                                 ("open_questions", ["open_questions"])])
def test_the_promise_guard_right_wrong_and_missing(monkeypatch, promised, gaps):
    """Right: a section the pack has. Wrong: a known name whose section this pack lacks. Missing: a name with none."""
    parts = [ctx.Section("contract", ctx.CONSTRAINTS, [PROMISE + promised]), ctx.Section("guardrails", ctx.WORK, [])]
    monkeypatch.setattr(ctx, "sections", lambda _: parts)
    assert false_promises(inputs("reviewer", "parent", full=False)) == gaps


@pytest.mark.parametrize(("text", "off"), [
    ("### Allowed engine operations\n- check.run\n- submit.review\n\nRun `aew submit --kind k --file f`"
     " or `aew -C \"/ws\" whoami` or `aew check run unit`", []),
    ("### Allowed engine operations\n- (none)\n\n", []),
    ("### Allowed engine operations\n- context.read\n\n", ["context.read"]),
    ("### Allowed engine operations\n- harness.launch\n\n", ["harness.launch"]),
    ("Then run `aew work transition T-1 --to RUNNING`.", ["aew work transition T-1 --to RUNNING"]),
    ("### Prohibited\n- running `aew work transition T-1 --to RUNNING`\n\n", []),
    # A submit the engine refuses this role at this scope is off, though its prefix is on the bridge (#581 F1).
    ("### Allowed engine operations\n- submit.review\n- submit.plan_assessment\n\n", ["submit.plan_assessment"]),
    ("### Allowed engine operations\n- submit.verification\n\n", ["submit.verification"]),
])
def test_the_bridge_guard_right_wrong_and_missing(text, off):
    assert operations_off_the_bridge(text) == off


@pytest.mark.parametrize(("planted", "problem"), [
    (lambda pack: pack, None),  # right
    (lambda pack: pack.replace("result: pass\n", "result: 'pass  # or: blocked'\n"), "a comment inside a value"),
    (lambda pack: pack.replace("result: pass\n", "result: fail\n"), "result 'fail' is refused"),
    (lambda pack: pack.replace("implementation:\n", "implementation:\n  scope: x\n"), "names a scope"),
    (lambda pack: pack.replace("implementation:\n", "state: DONE\nimplementation:\n"), "state"),
    (lambda pack: pack.replace("`result` is pass (complete) or blocked", "`result` is pass"), "does not list blocked"),
    (lambda pack: pack.replace("```markdown\n", "```text\n"), "no report format"),
])
def test_the_report_format_guard_right_wrong_and_missing(planted, problem):
    pack = ctx.render(inputs("implementer", "ticket", full=False))
    found = report_format_problems(planted(pack), "implementer")
    assert found == [] if problem is None else any(problem in p for p in found), found


def test_the_report_format_guard_finds_the_scope_the_verifier_template_offered():
    pack = ctx.render(inputs("verifier", "parent", full=False))
    planted = pack.replace("verification:\n", "verification:\n  scope: <ticket|integration>\n")
    assert report_format_problems(pack, "verifier") == []
    assert "names a scope" in report_format_problems(planted, "verifier")


@pytest.mark.parametrize(("text", "problem"), [
    ("Run `aew whoami --help`.", None),
    ("invocation credential required: pass --invocation-token or set AEW_INVOCATION_TOKEN", "asks to"),
    ("pass each subagent its generated launch contract and invocation credential, nothing more", "asks to"),
    ("Start it with `aew invoke create <T> --launhc`.", "--launhc"),
])
def test_the_text_guard_right_wrong_and_missing(text, problem):
    found = asks_or_misprints(text)
    assert found == [] if problem is None else any(problem in p for p in found), found


@pytest.mark.parametrize(("role", "offered", "said", "trap"), [
    ("investigator", True, True, None),
    ("investigator", True, False, "unsaid"),
    ("planner", False, False, None),
    ("planner", False, True, "said where it does not apply"),
    ("implementer", True, False, None),
    ("implementer", True, True, "said where it does not apply"),
])
def test_the_check_guard_right_wrong_and_missing(role, offered, said, trap):
    pack = (ctx.OPERATION_COMMANDS["check.run"] + "\n" if offered else "") + (ctx.CHECK_WRITES_NOTE if said else "")
    assert check_trap(pack, role) == trap


@pytest.mark.parametrize(("text", "asks", "none"), [
    ("There is no credential to set.", False, True),
    ("Set `AEW_INVOCATION_TOKEN=<credential>` for every `aew` command below.", True, False),
    ("There is no credential to set.\nSet `AEW_INVOCATION_TOKEN=<credential>` for every `aew` command.", True, True),
    ("Run `aew whoami`.", False, False),
])
def test_the_credential_guard_tells_an_ask_from_a_denial(text, asks, none):
    assert asks_for_a_credential(text) is asks and says_there_is_none(text) is none


@pytest.mark.parametrize("card", [None, *(c.meta for _, c in CARDS if c.archetype == "reviewer")])
def test_only_a_plan_assessor_is_told_it_may_submit_a_plan_assessment(card):
    """#581 review, F1: the reviewer archetype holds the grant, but a reviewer of a change, with any card, is offered
    only the review, and the assessor only its assessment."""
    for scope in SCOPES["reviewer"]:
        listed = allowed_operations(ctx.render(inputs("reviewer", scope, full=True, card=card)))
        if scope == E.ASSESSMENT_SCOPE:
            assert f"submit.{E.PLAN_ASSESSMENT}" in listed and "submit.review" not in listed, (scope, listed)
        else:
            assert f"submit.{E.PLAN_ASSESSMENT}" not in listed, (scope, listed)
