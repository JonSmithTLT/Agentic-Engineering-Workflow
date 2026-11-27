"""The Lead's own skills (register E161; the operator's decision of 2026-11-06, items 6 to 8; the designer's decision of
2026-11-06, the Lead's skills and MCP servers, (a)).

The Lead has no card, so AEW's skill manifest holds its list (``lead``), and the same helper that decides what a run is
exposed decides what the Lead is (``aew.skills.plan``, every id optional). The copy goes into a folder of each start's
own, beside the Lead's state and never in it, by the same ``aew.skills.deliver`` a run's supervisor uses, which never
follows a link. The contained Lead is offered only that copy: every other id denied, the compatibility plugin off. The
Lead that is not contained gets AEW's folder and ids beside the operator's own skills, which stay at ``ask``. Its text
names its skills from the plan, and its record says what it was given. Nothing here runs a model: the live check is
``tests/live/test_lead_skills_live.py``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew import roles, skills
from aew.harness import lead_broker
from aew.harness.opencode import lead, projection

# E161's three, and `ci-evidence-triage` by the operator's answer of 2026-11-26 (E136's fourth batch).
LEAD_LIST = ["ci-evidence-triage", "delegation-handoffs", "engineering-planning", "requirements-clarification"]
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
    planned, at = lead.deliver_lead_skills(engine)
    assert planned["exposed"] == [name for name in LEAD_LIST if name != "delegation-handoffs"]
    config = projection.lead_config(skills_dir=at, skills_planned=planned)
    assert "`delegation-handoffs`" not in lead_agent(config)["system"]
    assert effect(lead_agent(config)["permissions"], "skill", "delegation-handoffs") == "ask"


# ---------------------------------------------------------------------------------------------- the copy and record


def test_each_start_copies_into_its_own_folder_outside_the_leads_state_holding_exactly_the_list(tmp_path):
    engine = SimpleNamespace(aew_root=tmp_path / ".aew")
    first, first_at = lead.deliver_lead_skills(engine)
    planned, at = lead.deliver_lead_skills(engine)
    parent = os.path.realpath(engine.aew_root / lead.LEAD_SKILLS_DIR)
    state = os.path.realpath(engine.aew_root / lead.LEAD_DIR)
    assert os.path.isabs(at.folder) and Path(at.folder).parent.parent == Path(parent)
    assert not Path(at.folder).is_relative_to(state)  # never in the Lead's state
    assert at.folder != first_at.folder and not os.path.lexists(first_at.folder)  # an earlier start's copy goes
    assert first["exposed"] == planned["exposed"] == LEAD_LIST
    assert sorted(p.name for p in Path(at.folder).iterdir()) == LEAD_LIST
    assert skills.root_problems(Path(at.folder), planned["exposed"]) == [] and skills.verify(planned, Path(at.folder))
    assert not list(Path(at.folder).rglob("evals"))
    assert lead.lead_skills_at(engine).folder == os.sep.join([parent, lead.EACH_START, "skills"])  # --print-config's


def test_a_linked_lead_skills_folder_is_left_alone_and_reported(tmp_path):
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    (outside / "file").write_text("kept")
    (outside / "sub" / "f").write_text("kept")
    kept = sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*"))

    def intact() -> bool:
        return sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == kept

    planned = projection.lead_skills()
    failed = {name: skills.COPY_FAILED for name in LEAD_LIST}
    # the copy's folder a link: left as it is, nothing listed or removed through it
    root = tmp_path / "state" / "skills"
    root.parent.mkdir()
    root.symlink_to(outside, target_is_directory=True)
    delivered = skills.deliver(planned, root)
    assert (delivered["exposed"], delivered["reasons"]) == ([], failed)
    assert root.is_symlink() and intact() and skills.root_problems(root, LEAD_LIST) == ["."]
    assert not skills.verify(planned, root)
    # its parent a link: nothing made or removed under it
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    assert skills.deliver(planned, linked / "sub")["reasons"] == failed and intact()
    # the Lead's: a link where an earlier start's copy was is never followed, and the start goes on
    engine = SimpleNamespace(aew_root=tmp_path / ".aew")
    parent = engine.aew_root / lead.LEAD_SKILLS_DIR
    parent.mkdir(parents=True)
    (parent / "earlier").symlink_to(outside, target_is_directory=True)
    delivered, at = lead.deliver_lead_skills(engine)
    assert delivered["exposed"] == LEAD_LIST and intact()
    # and where the whole folder is a link, nothing is copied through it
    (parent / "earlier").unlink()
    shutil.rmtree(parent)
    parent.symlink_to(outside, target_is_directory=True)
    delivered, at = lead.deliver_lead_skills(engine)
    assert (delivered["exposed"], delivered["reasons"]) == ([], failed) and intact()


def test_a_copy_changed_after_delivery_is_never_taken_for_the_delivered_one(tmp_path):
    """What the contained start checks again just before it binds the copy (``aew.skills.verify``)."""
    planned, at = lead.deliver_lead_skills(SimpleNamespace(aew_root=tmp_path / ".aew"))
    folder = Path(at.folder)
    assert skills.verify(planned, folder)
    (folder / "notes.md").write_text("extra")
    assert not skills.verify(planned, folder)
    (folder / "notes.md").unlink()
    (folder / LEAD_LIST[0] / skills.SKILL_FILE).write_text("changed")
    assert not skills.verify(planned, folder)
    assert lead.undelivered(planned)["reasons"] == {name: skills.COPY_FAILED for name in LEAD_LIST}


def test_a_lead_copy_that_fails_reports_copy_failed_and_the_start_goes_on(tmp_path, monkeypatch):
    def broken(planned: Any, root: Path) -> Any:
        root.mkdir(parents=True)
        raise PermissionError("denied")

    monkeypatch.setattr(skills, "deliver", broken)
    engine = SimpleNamespace(aew_root=tmp_path / ".aew")
    planned, at = lead.deliver_lead_skills(engine)
    assert planned["exposed"] == [] and planned["delivered"] == []
    assert planned["reasons"] == {name: skills.COPY_FAILED for name in LEAD_LIST}
    assert not Path(at.folder).exists()


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
        [folder] = config["skills"]  # this start's own copy, made by the callback and holding exactly the list
        assert Path(folder).parent.parent == Path(os.path.realpath(engine.aew_root / lead.LEAD_SKILLS_DIR))
        assert Path(folder).is_dir() and skills.root_problems(Path(folder), LEAD_LIST) == []
        assert skills.verify({"exposed": LEAD_LIST}, Path(folder))
    assert holder.skills_at.folder == folder
    assert weaker.label_extra["skills"]["exposed"] == LEAD_LIST
    assert weaker.label_extra["skills"]["copy"] == "rules_only"
    assert holder.skills_planned["exposed"] == LEAD_LIST
