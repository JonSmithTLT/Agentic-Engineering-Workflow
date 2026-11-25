"""The Lead's own skills (register E161; the operator's decision of 2026-11-06, items 6 to 8; the designer's decision of
2026-11-06, the Lead's skills and MCP servers, (a)).

The Lead has no card, so AEW's skill manifest holds its list (``lead``), and the same helper that decides what a run is
exposed decides what the Lead is (``aew.skills.plan``, every id optional). The copy goes into the Lead's own state, the
same ``aew.skills.deliver`` a run's supervisor uses. The contained Lead is offered only that copy: every other id
denied, the compatibility plugin off. The Lead that is not contained gets AEW's folder and ids beside the operator's own
skills, which stay at ``ask``. Its text names its skills from the plan, and its record says what it was given. Nothing
here runs a model: the live check is ``tests/live/test_lead_skills_live.py``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew import roles, skills
from aew.harness import lead_broker
from aew.harness.opencode import lead, projection

LEAD_LIST = ["delegation-handoffs", "engineering-planning", "requirements-clarification"]
AT = projection.skills_at("/p/.aew/local/harness/lead", "/")


def effect(rules: list[dict[str, str]], action: str, resource: str = "*") -> str:
    """OpenCode's evaluation, last match wins, with its wildcard (``*`` is ``.*``: skills probe, check 5)."""
    out = "ask"
    for r in rules:
        pattern = "^" + ".*".join(re.escape(p) for p in r["resource"].split("*")) + "$"
        if r["action"] in (action, "*") and re.match(pattern, resource):
            out = r["effect"]
    return out


def lead_agent(config: dict[str, Any]) -> dict[str, Any]:
    return config["agents"][projection.LEAD_AGENT]


def contained(**kw: Any) -> dict[str, Any]:
    label = {"filesystem": "os_readonly_roots", "network": {"mode": "proxy_only"}}
    return projection.lead_config(contained=label, skills_dir=AT, **kw)


# ---------------------------------------------------------------------------------------------- the list


def test_the_lead_list_is_three_shipped_skills_all_optional_and_unevaluated():
    assert list(skills.lead()) == LEAD_LIST
    planned = projection.lead_skills()
    assert planned == skills.plan((), skills.lead())  # the helper a run's plan comes from, never one of its own
    assert (planned["requested"], planned["offered"], planned["exposed"]) == ([], LEAD_LIST, LEAD_LIST)
    assert (planned["unavailable"], planned["reasons"]) == ([], {})
    assert {d["label"] for d in planned["delivered"]} == {skills.LABEL} == {"unevaluated"}


def test_a_lead_list_naming_an_unshipped_skill_reports_it_and_offers_the_rest(monkeypatch):
    shipped = skills.manifest()
    monkeypatch.setattr(skills, "manifest", lambda: {**shipped, "lead": ["engineering-planning", "never-shipped"]})
    planned = projection.lead_skills()
    assert planned["exposed"] == ["engineering-planning"]
    assert planned["reasons"] == {"never-shipped": skills.NOT_SHIPPED}


def test_the_lead_is_offered_exactly_the_lead_list_in_both_modes():
    for config in (contained(), projection.lead_config(skills_dir=AT)):
        rules = lead_agent(config)["permissions"]
        allowed = [r["resource"] for r in rules if r["action"] == "skill" and r["effect"] == "allow"]
        assert allowed == LEAD_LIST
        assert config["skills"] == [AT.folder]


def test_no_role_card_is_offered_a_skill_it_does_not_name():
    """The `lead` list is the Lead's alone: no card's run gets a skill from it, only from its own lists."""
    for card in roles.builtin_cards().values():
        named = set(card.meta.get("skills") or []) | set(card.meta.get("optional_skills") or [])
        planned = skills.plan(card.meta.get("skills") or [], card.meta.get("optional_skills") or [])
        assert set(planned["exposed"]) <= named, card.id


# ---------------------------------------------------------------------------------------------- the two modes


def test_the_contained_lead_is_offered_only_its_copy_every_other_skill_denied_and_the_plugin_off():
    config = contained()
    rules = lead_agent(config)["permissions"]
    assert rules[:len(projection.LEAD_RULES)] == projection.LEAD_RULES
    for name in LEAD_LIST:
        assert effect(rules, "skill", name) == "allow"
    for other in ("opencode", "browser", "an-operators-own", "python-development"):
        assert effect(rules, "skill", other) == "deny", other
    assert config["plugins"] == [projection.COMPATIBILITY_PLUGIN]  # no ~/.claude or ~/.agents skills
    inside = AT.folder + "/engineering-planning/references/mechanical-inventories.md"
    assert effect(rules, "external_directory", inside) == "allow" and effect(rules, "edit", inside) == "deny"


def test_the_uncontained_lead_adds_aews_ids_beside_the_operators_own_skills_left_at_ask():
    config = projection.lead_config(skills_dir=AT)
    rules = lead_agent(config)["permissions"]
    for name in LEAD_LIST:
        assert effect(rules, "skill", name) == "allow"
    assert effect(rules, "skill", "an-operators-own") == "ask"
    assert effect(rules, "skill", "browser") == "deny"  # still refused by design
    assert "plugins" not in config  # the operator's own sources stay
    assert effect(rules, "edit", AT.folder + "/delegation-handoffs/SKILL.md") == "deny"


def test_the_lead_gets_no_mcp_server_but_aews_own_in_either_mode():
    """The operator, 2026-11-06, item 7: no MCP servers beyond AEW's own for the Lead in the alpha."""
    for config in (contained(), projection.lead_config(skills_dir=AT)):
        assert list(config["mcp"]["servers"]) == [projection.LEAD_MCP_SERVER]


def test_a_lead_configuration_without_a_folder_has_no_skills_entry_and_no_skill_rule_of_aews():
    config = projection.lead_config()
    assert "skills" not in config and "plugins" not in config
    assert lead_agent(config)["permissions"] == projection.LEAD_RULES
    assert "`skill` tool" not in lead_agent(config)["system"]


def test_nothing_exposed_gives_no_skills_entry_no_allow_and_no_line():
    nothing = skills.plan((), ())
    for config in (contained(skills_planned=nothing), projection.lead_config(skills_dir=AT, skills_planned=nothing)):
        assert "skills" not in config
        rules = lead_agent(config)["permissions"]
        assert not [r for r in rules if r["action"] == "skill" and r["effect"] == "allow"]
        assert "`skill` tool" not in lead_agent(config)["system"]


# ---------------------------------------------------------------------------------------------- the text


def test_the_leads_text_names_its_skills_derived_from_the_plan():
    for config, beside in ((contained(), False), (projection.lead_config(skills_dir=AT), True)):
        [line] = [s for s in lead_agent(config)["system"].splitlines() if "`skill` tool" in s]
        assert line == projection.lead_skills_text(projection.lead_skills(), contained=not beside)[0]
        assert all(f"`{name}`" in line for name in LEAD_LIST)
        assert ("Your own OpenCode skills are listed beside them" in line) is beside
    # derived: a plan that exposes one names that one only
    one = {**projection.lead_skills(), "exposed": ["engineering-planning"]}
    [line] = projection.lead_skills_text(one, contained=True)
    assert "`engineering-planning`" in line and "`delegation-handoffs`" not in line


def test_the_text_names_what_the_copy_delivered_never_a_failed_one(tmp_path, monkeypatch):
    real = skills.check
    monkeypatch.setattr(skills, "check", lambda n: (skills.HASH_MISMATCH, {}) if n == "delegation-handoffs"
                        else real(n))
    engine = SimpleNamespace(aew_root=tmp_path / ".aew")
    planned = lead.deliver_lead_skills(engine)
    assert planned["exposed"] == ["engineering-planning", "requirements-clarification"]
    config = projection.lead_config(skills_dir=lead.lead_skills_at(engine), skills_planned=planned)
    assert "`delegation-handoffs`" not in lead_agent(config)["system"]
    assert effect(lead_agent(config)["permissions"], "skill", "delegation-handoffs") == "ask"


# ---------------------------------------------------------------------------------------------- the copy and record


def test_the_copy_goes_into_the_leads_own_state_and_holds_exactly_the_list(tmp_path):
    engine = SimpleNamespace(aew_root=tmp_path / ".aew")
    planned = lead.deliver_lead_skills(engine)
    at = lead.lead_skills_at(engine)
    assert at.folder == os.path.realpath(engine.aew_root / lead.LEAD_DIR / "skills") and os.path.isabs(at.folder)
    assert planned["exposed"] == LEAD_LIST
    assert sorted(p.name for p in Path(at.folder).iterdir()) == LEAD_LIST
    assert skills.root_problems(Path(at.folder), planned["exposed"]) == []
    assert not list(Path(at.folder).rglob("evals"))


def test_a_lead_copy_that_fails_reports_copy_failed_and_the_start_goes_on(tmp_path, monkeypatch):
    def broken(planned: Any, root: Path) -> Any:
        root.mkdir(parents=True)
        raise PermissionError("denied")

    monkeypatch.setattr(skills, "deliver", broken)
    engine = SimpleNamespace(aew_root=tmp_path / ".aew")
    planned = lead.deliver_lead_skills(engine)
    assert planned["exposed"] == [] and planned["delivered"] == []
    assert planned["reasons"] == {name: skills.COPY_FAILED for name in LEAD_LIST}
    assert not Path(lead.lead_skills_at(engine).folder).exists()


@pytest.mark.parametrize("bound, copy", [(True, "read_only_bind"), (False, "rules_only")])
def test_the_sessions_record_says_what_it_was_given_and_how_the_copy_was_kept(bound, copy):
    planned = projection.lead_skills()
    assert lead.skills_label(planned, bound) == {**planned, "copy": copy}
    nothing = skills.plan((), ())
    assert lead.skills_label(nothing, bound) == nothing  # no copy, so nothing to say of one


def test_the_presentation_copies_once_seated_and_hands_the_plan_to_the_harness_that_builds_it(tmp_path, monkeypatch):
    monkeypatch.setattr(lead, "guide_of", lambda engine, switches=None: "")
    monkeypatch.setattr(lead, "pushes_wakes", lambda engine: False)
    engine = SimpleNamespace(aew_root=tmp_path / ".aew")
    weaker = lead_broker.WeakerLead(engine, ["opencode"], kind="lead_opencode", who="aew opencode")
    holder = SimpleNamespace()
    for kw in ({"weaker": weaker}, {"contained": holder}):
        env = lead.session_presentation(engine, provider_env=[], **kw)({"PATH": os.defpath}, frozenset())
        config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        assert config["skills"] == [lead.lead_skills_at(engine).folder]
    assert weaker.label_extra["skills"]["exposed"] == LEAD_LIST
    assert weaker.label_extra["skills"]["copy"] == "rules_only"
    assert holder.skills_planned["exposed"] == LEAD_LIST
