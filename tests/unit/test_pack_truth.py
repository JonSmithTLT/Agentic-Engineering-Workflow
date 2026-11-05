"""What a worker reads is true: plain asserts over the text as AEW renders it (operator, 2026-11-04: a false line in a
pack or preamble is a product defect).

Each guard is a function of the rendered text or the role's definition, so its planted cases run the same code:
- a pack promises only sections it has, and each archetype's knowledge list is sections its pack can have;
- every operation and `aew` command a worker's text names is one its custody bridge offers;
- no worker's text both asks for a credential and says there is none, and no text corrects another;
- a report format is what the engine accepts as it stands, its other values listed beside it from what the engine
  validates, and it names no scope (the engine fills in the dispatched one);
- a role that may not change the tree it evaluates is told what a check that writes there does to its submission;
- a role with no credential is told to stop, never to get one, and what an archetype tells any role asks for no
  credential and names only commands that parse (D2 does not scan these two).

The matrix is every dispatchable archetype, every scope it runs at and every built-in card, each with all of its
optional inputs and with none, so a section that depends on the scope or the data is seen both ways.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from discovery import rules

from aew import roles
from aew.cli.work_commands import NO_INVOCATION_AUTHORITY
from aew.errors import AEWError, UsageError
from aew.harness import bridge
from aew.harness import contract as K
from aew.knowledge import context as ctx
from aew.knowledge import evidence as E
from aew.schemas import validate_property
from aew.util import load_yaml

SCOPES = {"implementer": ["ticket"], "reviewer": ["ticket", "observation", "parent", "integration"],
          "verifier": ["ticket", "observation", "parent", "integration"], "investigator": ["observation"],
          "researcher": ["observation"], "planner": ["observation"]}
DISPATCHABLE = [name for name in roles.ARCHETYPES if roles.archetype(name).get("dispatchable")]
PROMISE = "- Required knowledge (included below): "
SECTION = {"implementation_report": "implementation", "review": "review", "verification": "verification",
           "discovery_record": "discovery", "research_record": "research", "plan_proposal": "proposal"}
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
            "children": [{"id": "T-2", "kind": "ticket", "state": "DONE", "title": "t"}],
        }
    return ctx.PackInputs(
        invocation_id="INV-1", role=role, role_def=role_def or roles.archetype(role), work_id="T-1", title="a title",
        scope=scope, specialty=None, workspace="/ws/T-1",
        snapshot={"relevant_inputs_fingerprint": "tree:0", "workspace_id": "ws-0", "base_revision": "0" * 40},
        record_meta={"initial_risk_class": 1, "acceptance": {"goal_backwards": ["g"], "contract": ["c"]},
                     "scope": {"paths": ["src/**"]}},
        record_body="a body", plan={"accepted": 1, "sha256": "0" * 64}, plan_text="a plan", guardrails_text="",
        checks={"unit": {"configured": True, "description": "unit tests"}}, authority=[], card=card, **optional)


def matrix() -> list[tuple[str, str, bool, dict[str, Any] | None]]:
    cases: list[tuple[str, str, bool, dict[str, Any] | None]] = []
    cases += [(role, scope, full, None) for role in DISPATCHABLE for scope in SCOPES[role] for full in (True, False)]
    cases += [(c.archetype, scope, True, c.meta) for _, c in CARDS for scope in SCOPES[c.archetype]]
    return cases


def prompt(pack: str, role: str) -> str:
    """The whole text a harness run's worker is given."""
    return K.LaunchContract(
        run="R-INV-1-1", invocation="INV-1", work_unit="T-1", role=role, scope="ticket", card=None,
        execution_profile={}, workspace="/ws/T-1", expected_kinds=sorted(roles.archetype(role)["evidence_kinds"]),
        operations=sorted(roles.archetype(role)["engine_operations"]), pack_path="/p", pack_sha256="0" * 64,
        pack_text=pack, continuation={"previous_runs": ["R-INV-1-0"], "evidence": [], "changed_paths": []},
        run_dir="/r", scratch="/s").prompt


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


def operations_off_the_bridge(text: str) -> list[str]:
    """Operations in the pack's allowed list, and `aew` commands in ``text``, that the bridge lacks. A prohibition may
    name what only the Lead runs (the planner's `aew plan adopt`): it tells the worker not to, so it is not scanned."""
    allowed = re.search(r"^### Allowed engine operations\n+((?:- .*\n?)+)", text, re.M)
    missing = []
    for op in re.findall(r"^- (\S+)$", allowed.group(1) if allowed else "", re.M):
        key = "submit" if op.startswith("submit.") else op
        if key not in bridge.OPERATIONS and op != "(none)":
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


def report_format_problems(pack: str, role: str) -> list[str]:
    """Why the pack's report format is not what the engine accepts as it stands (a `<...>` placeholder is a string to
    the schema, so filling those in is all a copy needs), or does not list a field's other values."""
    fence = re.search(r"^```markdown\n---\n(.*?)\n---\n", pack, re.S | re.M)
    if fence is None:
        return ["no report format"]
    meta = load_yaml(fence.group(1))
    kind = ctx.OUTPUT_TEMPLATES[role][0]
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
        E.check_submission(role, kind, meta)
        filled = {"scope": "ticket", **section} if kind == "verification" else section  # as the engine fills it
        validate_property("evidence", SECTION[kind], filled, source="the template")
    except AEWError as exc:
        problems.append(exc.message)
    allowed = ctx._allowed_values(role)
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


def check_trap(pack: str, role: str) -> str | None:
    """What is wrong with what ``pack`` says about a check that writes, if anything."""
    offered, said = "aew check run <check-id>" in pack, ctx.CHECK_WRITES_NOTE in pack
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
    assert operations_off_the_bridge(prompt(ctx.render(inputs(role, scope, full=full, card=card)), role)) == []


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
    assert report_format_problems(ctx.render(inputs(role, scope, full=full, card=card)), role) == []


@pytest.mark.parametrize(("role", "scope", "full", "card"), matrix())
def test_a_role_that_may_not_change_its_tree_is_told_what_a_check_that_writes_does(role, scope, full, card):
    assert check_trap(ctx.render(inputs(role, scope, full=full, card=card)), role) is None


def test_a_role_with_no_credential_is_told_to_stop_and_never_to_get_one():
    assert asks_or_misprints(NO_INVOCATION_AUTHORITY) == []
    assert [s.argv for s in commands_in(NO_INVOCATION_AUTHORITY)] == [("harness", "launch"), ("whoami", "--help")]
    assert "stop and report" in NO_INVOCATION_AUTHORITY
    assert "AEW_INVOCATION_TOKEN" not in NO_INVOCATION_AUTHORITY


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


def test_the_lead_is_told_to_launch_and_the_line_it_is_told_parses_whole():
    launches = [s for s in commands_in(archetype_prose("lead")) if "--launch" in s.argv]
    assert launches
    assert [rules.o_cmd(rules.Suggestion(s.argv, s.text, structured=True)) for s in launches] == [None] * len(launches)


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
    pack = ("aew check run <check-id>\n" if offered else "") + (ctx.CHECK_WRITES_NOTE if said else "")
    assert check_trap(pack, role) == trap


@pytest.mark.parametrize(("text", "asks", "none"), [
    ("There is no credential to set.", False, True),
    ("Set `AEW_INVOCATION_TOKEN=<credential>` for every `aew` command below.", True, False),
    ("There is no credential to set.\nSet `AEW_INVOCATION_TOKEN=<credential>` for every `aew` command.", True, True),
    ("Run `aew whoami`.", False, False),
])
def test_the_credential_guard_tells_an_ask_from_a_denial(text, asks, none):
    assert asks_for_a_credential(text) is asks and says_there_is_none(text) is none
