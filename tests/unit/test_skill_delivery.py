"""Skills reach workers by their card's fit (register E127; the designer's rulings of 2026-11-03 §3 and 2026-11-04).

AEW's own install ships four skills with a manifest of hashes. A card's ``skills:`` and ``optional_skills`` decide what
a run may reach. The supervisor copies what is exposed into the run's own folder, the projection lets the ``skill`` tool
list exactly those, and the agent is told, from the plan, which to load. The record says what was offered, exposed,
delivered and loaded. Nothing here runs a model: the live test is on the VM (``tests/live/e127_skills``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from aew import roles, skills
from aew.engine import guide
from aew.engine.role_ops import Roles
from aew.harness.contract import LaunchContract
from aew.harness.opencode import adapter as A
from aew.harness.opencode import projection
from aew.knowledge import context as ctxmod

SHIPPED = Path(skills.__file__).resolve().parent / skills.SHIPPED
FOUR = ["acceptance-verification", "adversarial-review", "c-development", "python-development"]


def contract(*, role: str = "implementer", card: str = "engineer", requested: list[str] | None = None,
             optional: list[str] | None = None, planned: dict[str, Any] | None = None) -> LaunchContract:
    extra: dict[str, Any] = {"card_skills": requested or [], "card_optional_skills": optional or [],
                             "card_capabilities": ["exact_code_search"], "provider_env": []}
    if planned is not None:
        extra["skills"] = planned
    return LaunchContract(
        run="R-INV-0001-1", invocation="INV-0001", work_unit="T-0001", role=role, scope="ticket",
        card={"id": card, "version": 2, "sha256": "0" * 64},
        execution_profile={"harness": "opencode", "provider": "openai", "model": "m", "effort": None},
        workspace="/ws", expected_kinds=["implementation_report"], operations=["submit.implementation_report"],
        pack_path="/p", pack_sha256="2" * 64, pack_text="# pack\n", continuation=None, run_dir="/r",
        scratch="/r/scratch", extra=extra)


def effect(rules: list[dict[str, str]], action: str, resource: str = "*") -> str:
    """OpenCode's evaluation, with its wildcard (``*`` is ``.*``, crossing ``/``: skills probe, check 5)."""
    out = "ask"
    for r in rules:
        pattern = "^" + ".*".join(re.escape(p) for p in r["resource"].split("*")) + "$"
        if r["action"] in (action, "*") and re.match(pattern, resource):
            out = r["effect"]
    return out


# ---------------------------------------------------------------------------------------------- the install


def test_the_four_ship_with_a_manifest_that_hashes_exactly_their_allow_listed_files():
    assert sorted(skills.shipped()) == FOUR
    for name, entry in skills.entries().items():
        on_disk = {p.relative_to(SHIPPED / name).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (SHIPPED / name).rglob("*") if p.is_file()}
        assert on_disk == entry["files"], name  # nothing unlisted ships, and nothing listed is missing
        assert all(skills.allowed(rel) for rel in on_disk), name
        assert not any(rel.startswith("evals/") for rel in on_disk), name
        assert skills.tree_sha256(on_disk) == entry["sha256"]
        assert entry["label"] == skills.LABEL == "unevaluated"
        assert skills.check(name)[0] is None


def test_each_shipped_skill_names_itself_by_its_folder_states_its_version_and_says_when_not_to_use_it():
    """OpenCode's id is the folder's name and its rules match the id; a skill with no description loads but is never
    listed (skills probe, 2026-11-04). The ruling's §4: a description says when not to use it."""
    for name, entry in skills.entries().items():
        text = (SHIPPED / name / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        assert re.search(rf"^name: {re.escape(name)}$", front, re.M), name
        assert re.search(rf"^  version: '{re.escape(entry['version'])}'$", front, re.M), name
        description = re.search(r"^description: (.+)$", front, re.M)
        assert description and re.search(r"\b(skip|not)\b", description.group(1), re.I), name


def test_the_package_data_ships_every_file_the_manifest_lists():
    """``pyproject.toml``'s globs reach each listed file, so an installed AEW has what the manifest says."""
    text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    globs = json.loads(re.search(r'^"aew\.skills" = (\[.*\])$', text, re.M).group(1))  # type: ignore[union-attr]
    for name, entry in skills.entries().items():
        for rel in entry["files"]:
            assert any(Path(f"{skills.SHIPPED}/{name}/{rel}").match(g) for g in globs), (name, rel)


@pytest.mark.parametrize("rel, ok", [
    ("SKILL.md", True), ("references/a.md", True), ("examples/good/a.md", True),
    ("evals/cases.yaml", False), ("references/SKILL.md", False), ("examples/x/SKILL.md", False),
    ("notes.md", False), ("../SKILL.md", False), ("references/../SKILL.md", False), ("/SKILL.md", False),
    ("references\\a.md", False), ("references", False)])
def test_the_allow_list_ships_only_skill_md_references_and_examples(rel, ok):
    assert skills.allowed(rel) is ok


def test_a_manifest_that_names_evals_or_a_nested_skill_is_refused(monkeypatch):
    """A9 and A4: ``evals/`` never ships (``specification.md``: never runtime resources), and a nested ``SKILL.md``
    would be a skill of its own (OpenCode scans ``**/SKILL.md``)."""
    real = dict(skills.entries()["c-development"])
    for extra in ("evals/cases.yaml", "references/deep/SKILL.md"):
        planted = {**real, "files": {**real["files"], extra: "0" * 64}}
        monkeypatch.setattr(skills, "entries", lambda p=planted: {"c-development": p})
        assert skills.check("c-development") == (skills.OUTSIDE_ALLOW_LIST, {})
        assert skills.plan([], ["c-development"])["reasons"] == {"c-development": skills.OUTSIDE_ALLOW_LIST}


def test_a_changed_installed_file_reports_a_mismatch_and_the_run_goes_on(monkeypatch):
    real = skills._read
    monkeypatch.setattr(skills, "_read", lambda n, rel: real(n, rel) + (b"x" if n == "c-development" else b""))
    planned = skills.plan(["c-development"], ["python-development"])
    assert planned["exposed"] == ["python-development"]
    assert planned["unavailable"] == ["c-development"]
    assert planned["reasons"] == {"c-development": skills.HASH_MISMATCH}


# ---------------------------------------------------------------------------------------------- the plan


def test_exposed_is_both_lists_that_ship_and_offered_is_the_optional_beyond_skills():
    """A1: ``exposed`` is ``(requested ∪ offered) ∩ provided`` (11-04 §5), so an optional skill is reachable."""
    planned = skills.plan(["adversarial-review", "security-review"],
                          ["adversarial-review", "c-development", "frontend-design"])
    assert planned["requested"] == ["adversarial-review", "security-review"]
    assert planned["offered"] == ["c-development", "frontend-design"]  # a name in both counts as skills:
    assert planned["exposed"] == ["adversarial-review", "c-development"]
    assert planned["unavailable"] == ["security-review"]  # only what skills: asked for
    assert planned["reasons"] == {"frontend-design": "not_shipped", "security-review": "not_shipped"}
    assert [d["name"] for d in planned["delivered"]] == planned["exposed"]
    for d in planned["delivered"]:
        entry = skills.entries()[d["name"]]
        assert d == {"name": d["name"], "version": entry["version"], "sha256": entry["sha256"], "label": "unevaluated",
                     "bytes": (SHIPPED / d["name"] / "SKILL.md").stat().st_size}


@pytest.mark.parametrize("name", ["../shipped/c-development", "shipped/c-development", "c-development/",
                                  str(SHIPPED / "c-development"), "C-DEVELOPMENT", "c-development/../c-development"])
def test_a_card_resolves_a_name_by_manifest_lookup_never_by_path(name):
    """A10: a project card names shipped skills; it cannot add text or reach a file by its path."""
    planned = skills.plan([name], [name])
    assert planned["exposed"] == [] and planned["reasons"] == {name: "not_shipped"}


def test_a_projects_own_card_can_name_shipped_skills_and_add_none(tmp_path):
    (tmp_path / "mine.yaml").write_text(
        "schema: aew/role/v1\nrole: mine\ndisplay_name: Mine\nextends: implementer\npurpose: p\n"
        "skills: [mine-skill]\noptional_skills: [c-development, ../../evil]\n", encoding="utf-8")
    (tmp_path / "mine-skill").mkdir()
    (tmp_path / "mine-skill" / "SKILL.md").write_text("---\nname: mine-skill\ndescription: d\n---\n", "utf-8")
    card = roles.load_catalog(tmp_path).get("mine")
    planned = skills.plan(card.meta["skills"], card.meta["optional_skills"])
    assert planned["exposed"] == ["c-development"]
    assert planned["reasons"] == {"../../evil": "not_shipped", "mine-skill": "not_shipped"}


def test_every_optional_skill_a_built_in_card_names_is_shipped():
    """The ruling's §2 test (``skills:`` can't have it yet: two cards name skills not written)."""
    for card in roles.builtin_cards().values():
        assert set(card.meta.get("optional_skills") or []) <= skills.shipped(), card.id


def test_the_cards_name_the_shipped_skills_with_their_versions_moved():
    cards = roles.builtin_cards()
    assert cards["code_reviewer"].meta["skills"] == ["adversarial-review"]
    assert cards["verifier"].meta["skills"] == ["acceptance-verification"]
    assert cards["engineer"].meta["optional_skills"] == ["python-development", "c-development"]
    assert {c: cards[c].meta["version"] for c in ("code_reviewer", "verifier", "engineer")} == {
        "code_reviewer": 2, "verifier": 2, "engineer": 2}


# ---------------------------------------------------------------------------------------------- the copy


def test_the_copy_holds_exactly_the_exposed_skills_and_their_listed_files(tmp_path):
    planned = skills.plan(["adversarial-review", "security-review"], ["python-development"])
    root = tmp_path / "harness" / "skills"
    delivered = skills.deliver(planned, root)
    assert delivered == planned
    assert sorted(p.name for p in root.iterdir()) == ["adversarial-review", "python-development"]
    assert skills.root_problems(root, delivered["exposed"]) == []
    for d in delivered["delivered"]:
        files = {p.relative_to(root / d["name"]).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (root / d["name"]).rglob("*") if p.is_file()}
        assert files == skills.entries()[d["name"]]["files"] and skills.tree_sha256(files) == d["sha256"]


def test_nothing_exposed_leaves_no_folder_and_a_fresh_copy_replaces_an_old_one(tmp_path):
    root = tmp_path / "skills"
    (root / "leftover").mkdir(parents=True)
    (root / "stray.md").write_text("x", encoding="utf-8")
    assert skills.deliver(skills.plan(["code-review"]), root)["exposed"] == []
    assert not root.exists()
    skills.deliver(skills.plan(["c-development"]), root)
    assert sorted(p.name for p in root.iterdir()) == ["c-development"]


def test_a_stray_file_at_the_root_or_a_nested_skill_is_found(tmp_path):
    """A4: OpenCode scans ``{*.md,**/SKILL.md}`` at the entry's root, so either would become a skill of its own."""
    root = tmp_path / "skills"
    skills.deliver(skills.plan(["c-development"]), root)
    (root / "notes.md").write_text("x", encoding="utf-8")
    (root / "c-development" / "references").mkdir()
    (root / "c-development" / "references" / "SKILL.md").write_text("x", encoding="utf-8")
    (root / "other").mkdir()
    assert skills.root_problems(root, ["c-development"]) == ["c-development/references/SKILL.md", "notes.md",
                                                              "other"]


def test_a_copy_that_would_hold_a_nested_skill_drops_that_skill_and_the_run_goes_on(tmp_path, monkeypatch):
    """A4 at the copy: whatever ``check`` hands over, ``deliver`` leaves nothing at the root but allow-listed files. The
    planted file is in the manifest's hash too, so the copy's re-hash passes and only the root's own check stands."""
    real, real_entries = skills.check, skills.entries()
    nested = b"---\nname: x\n---\n"
    files = {**real_entries["c-development"]["files"], "references/SKILL.md": hashlib.sha256(nested).hexdigest()}
    entries = {**real_entries, "c-development": {**real_entries["c-development"], "files": files,
                                                 "sha256": skills.tree_sha256(files)}}

    checked = {n: real(n) for n in ("c-development", "python-development")}  # before the manifest is planted

    def planted(name: str):
        why, found = checked[name]
        return (None, {**found, "references/SKILL.md": nested}) if name == "c-development" else (why, found)

    planned = skills.plan([], ["c-development", "python-development"])
    monkeypatch.setattr(skills, "check", planted)
    monkeypatch.setattr(skills, "entries", lambda: entries)
    root = tmp_path / "skills"
    delivered = skills.deliver(planned, root)
    assert delivered["exposed"] == ["python-development"]
    assert delivered["reasons"] == {"c-development": "copy_failed"}
    assert [d["name"] for d in delivered["delivered"]] == ["python-development"]
    assert sorted(p.name for p in root.iterdir()) == ["python-development"]


def test_a_copy_that_fails_reports_copy_failed_and_the_rest_is_delivered(tmp_path, monkeypatch):
    real = Path.write_bytes

    def failing(self: Path, data: bytes) -> int:
        if "acceptance-verification" in self.parts:
            raise OSError("disk full")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing)
    delivered = skills.deliver(skills.plan(["acceptance-verification", "c-development"]), tmp_path / "s")
    assert delivered["exposed"] == ["c-development"] and delivered["unavailable"] == ["acceptance-verification"]
    assert delivered["reasons"] == {"acceptance-verification": "copy_failed"}


# ---------------------------------------------------------------------------------------------- the projection


AT = projection.skills_at("/r/harness", "/")


@pytest.mark.parametrize("role", ["implementer", "reviewer"])
def test_the_skill_rules_are_exactly_the_copied_set_with_the_folder_readable_and_never_editable(tmp_path, role):
    """A2 and A5: a ``skill allow`` rule for every copied skill and no other; the folder's read grant always goes with
    its edit deny (the read grant alone let a model write an unbound copy: skills probe, check 7)."""
    planned = skills.plan(["adversarial-review", "security-review"], ["c-development", "frontend-design"])
    root = tmp_path / "skills"
    delivered = skills.deliver(planned, root)
    assert delivered["exposed"] == planned["exposed"] == ["adversarial-review", "c-development"]  # never widened
    c = contract(role=role, planned=delivered)
    config = projection.invocation_config(c, skills_dir=AT)
    rules = config["permissions"]
    allowed = sorted(r["resource"] for r in rules if r["action"] == "skill" and r["effect"] == "allow")
    assert allowed == delivered["exposed"] == sorted(p.name for p in root.iterdir())
    for name in ("security-review", "frontend-design", "opencode", "report", "anything"):
        assert effect(rules, "skill", name) == "deny", name  # OpenCode's built-ins stay hidden
    inside = "/r/harness/skills/c-development/SKILL.md"
    assert effect(rules, "external_directory", inside) == "allow"
    assert effect(rules, "edit", inside) == "deny"
    assert effect(rules, "edit", "/ws/src/a.py") == ("allow" if role == "implementer" else "deny")
    assert effect(rules, "external_directory", "/r/harness/opencode-config.json") == "deny"
    assert config["skills"] == ["/r/harness/skills"]


def test_the_skills_entry_is_one_plain_path_string_and_absent_when_nothing_is_exposed():
    """A6: an object entry loads nothing, silently (skills probe, 2026-11-04)."""
    config = projection.invocation_config(contract(planned=skills.plan([], ["c-development"])), skills_dir=AT)
    assert config["skills"] == [AT.folder] and all(isinstance(e, str) for e in config["skills"])
    none = projection.invocation_config(contract(planned=skills.plan(["code-review"])), skills_dir=AT)
    assert "skills" not in none
    assert not any(r["action"] in ("external_directory", "edit") and r["resource"] == AT.pattern
                   for r in none["permissions"])
    with pytest.raises(ValueError):
        projection.invocation_config(contract(planned=skills.plan(["c-development"])))


def test_the_launch_record_the_rules_and_harness_config_read_one_plan():
    """The contract carries the plan; the projection never computes its own (11-04 §1)."""
    planned = {**skills.plan([], ["c-development"]), "copy": "read_only_bind"}
    c = contract(optional=["python-development"], planned=planned)  # the card's lists differ: the plan wins
    assert projection.skills(c) is planned
    rules = projection.invocation_config(c, skills_dir=AT)["permissions"]
    assert [r["resource"] for r in rules if r["action"] == "skill" and r["effect"] == "allow"] == ["c-development"]


# ---------------------------------------------------------------------------------------------- what the agent is told


def lines(planned: dict[str, Any]) -> list[str]:
    return [s for s in projection.system_text(contract(planned=planned), planned).splitlines()
            if "skill" in s.lower()]


def test_only_skills_all_shipped_tells_it_to_load_them_and_nothing_else():
    """``code_reviewer``'s case: one clause, which qualifies the pack's "Skills to load"."""
    assert lines(skills.plan(["adversarial-review"])) == [
        "- Load `adversarial-review` with the `skill` tool before you start, unless its description says it does not "
        "fit this task. This qualifies the contract's \"Skills to load\"."]


def test_only_optional_tells_it_what_else_the_tool_lists():
    """``engineer``'s case."""
    assert lines(skills.plan([], ["python-development", "c-development"])) == [
        "- The `skill` tool also lists `c-development`, `python-development`: load one only when your task matches its "
        "description."]


def test_an_unshipped_skill_with_a_shipped_optional_one_says_both():
    """``security_reviewer``'s case before its skill ships."""
    said = lines(skills.plan(["security-review"], ["adversarial-review"]))
    assert said == ["- The `skill` tool also lists `adversarial-review`: load one only when your task matches its "
                    "description.",
                    "- Skills your role card requests that this harness does not provide: security-review. Proceed "
                    "without them and say so in your report."]


def test_one_of_two_skills_shipped_loads_one_and_names_the_other_unavailable():
    said = lines(skills.plan(["c-development", "c-review"]))
    assert said[0].startswith("- Load `c-development` with the `skill` tool")
    assert said[1].startswith("- Skills your role card requests that this harness does not provide: c-review.")
    assert len(said) == 2


def test_no_skills_says_nothing_about_skills():
    assert lines(skills.plan([])) == []


# ---------------------------------------------------------------------------------------------- the pack


def card_lines(card: dict[str, Any]) -> list[str]:
    inputs = ctxmod.PackInputs.__new__(ctxmod.PackInputs)
    object.__setattr__(inputs, "card", card)
    return ctxmod._card_section(inputs)


def test_the_pack_offers_optional_skills_conditionally_and_renders_nothing_from_the_manifest(monkeypatch):
    """A3: the pack carries the card's pinned lists, never what is shipped, so a re-hash between dispatch and relaunch
    leaves the pack byte-identical and ``_g_pack`` passes (11-04 §1)."""
    engineer = roles.builtin_cards()["engineer"].meta
    before = card_lines(engineer)
    assert "Skills to load (how the work is done): none" in before
    assert ("Optional skills (load one only if the `skill` tool lists it and your task matches): python-development, "
            "c-development") in before
    monkeypatch.setattr(skills, "entries", lambda: {})
    monkeypatch.setattr(skills, "check", lambda name: (skills.NOT_SHIPPED, {}))
    assert card_lines(engineer) == before


def test_a_card_without_optional_skills_renders_as_before():
    """A pinned card from before the field, or one whose optional names are all in ``skills:``: no new line."""
    old = {k: v for k, v in roles.builtin_cards()["python_engineer"].meta.items()}
    both = {**old, "optional_skills": ["python-development"]}
    assert card_lines(old) == card_lines(both)
    assert not any(s.startswith("Optional skills") for s in card_lines(old))


def test_the_packs_sources_pin_the_cards_skills_only():
    assert skills.pins(["adversarial-review", "security-review"]) == [
        {"name": "skill:adversarial-review", "path": None, "sha256": skills.entries()["adversarial-review"]["sha256"],
         "version": "0.6.0", "label": "unevaluated"}]


# ---------------------------------------------------------------------------------------------- loaded


def part(name: str, status: Any = "completed", given: Any = None) -> dict[str, Any]:
    return {"type": "tool", "id": "prt_call", "name": name, "state": {"status": status, "input": given}}


EXPOSED = frozenset({"c-development", "python-development"})


def test_a_load_is_a_completed_call_of_an_exposed_id_and_everything_else_is_only_counted():
    content = [part("skill", given={"id": "c-development"}), part("skill", given={"id": "c-development"}),
               part("skill", given={"id": "opencode"}), part("skill", "error", {"id": "python-development"}),
               part("skill", "running", '{"id": "python-de'), part("skill", given={"id": 7}),
               {"type": "tool", "name": "skill"}, part("read", given={"path": "x"}), {"type": "text", "text": "hi"}]
    assert A.skill_loads(content, EXPOSED) == (["c-development", "c-development"], 5)


class Pages:
    """The few GETs ``_take_snapshot`` makes, over a fixed message list."""

    def __init__(self, messages: list[dict[str, Any]], *, cursor: bool = False) -> None:
        self.messages, self.cursor = messages, cursor

    def get(self, path: str, params: Any = None, **_: Any) -> dict[str, Any]:
        if path.endswith("/message"):
            return {"data": self.messages, **({"cursor": {"next": "c"}} if self.cursor else {})}
        if path == "/api/session":
            return {"data": []}
        return {"data": {"outcome": "succeeded", "tokens": {}, "cost": 0}}


def collected(tmp_path: Path, messages: list[dict[str, Any]], *, cursor: bool = False) -> dict[str, Any]:
    adapter = A.OpenCodeAdapter(None, tmp_path, lambda e: None)
    adapter.session, adapter.client = "ses_1", Pages(messages, cursor=cursor)  # type: ignore[assignment]
    adapter.skills = skills.plan([], sorted(EXPOSED))
    adapter._take_snapshot()
    return adapter.collect()


DENIED = "a-name-the-model-wrote"
MESSAGES = [{"type": "assistant", "content": [part("skill", given={"id": "python-development"}),
                                              part("skill", given={"id": DENIED}), part("read")]},
            {"type": "user", "content": [part("skill", given={"id": "c-development"})]},
            {"type": "assistant", "content": [part("skill", given={"id": "python-development"})]}]


def test_loaded_and_skill_other_sum_to_the_skill_calls_and_keep_no_model_written_id(tmp_path):
    """A8: ``skill_other`` is a count; an id the model wrote is never stored (11-04 §5)."""
    out = collected(tmp_path, MESSAGES)
    assert out["loaded"] == {"python-development": 2} and out["skill_other"] == 1
    assert sum(out["loaded"].values()) + out["skill_other"] == out["tools_called"]["skill"] == 3
    assert DENIED not in json.dumps(out)


def test_a_truncated_snapshot_or_none_leaves_loaded_unknown(tmp_path):
    out = collected(tmp_path, MESSAGES, cursor=True)
    assert out["tools_called"]["skill"] and "loaded" not in out and "skill_other" not in out
    adapter = A.OpenCodeAdapter(None, tmp_path, lambda e: None)
    assert "loaded" not in adapter.collect() and "skill_other" not in adapter.collect()


def test_an_error_reading_loaded_never_reaches_the_run(tmp_path, monkeypatch):
    """A7: ``_take_snapshot`` runs on the poll path and at teardown: an error there ends the run or loses its record."""
    def broken(content: Any, exposed: frozenset[str]) -> tuple[list[str], int]:
        raise RuntimeError("unreadable")

    monkeypatch.setattr(A, "skill_loads", broken)
    out = collected(tmp_path, MESSAGES)
    assert out["tools_called"] == {"skill": 3, "read": 1} and out["steps"] == 2
    assert "loaded" not in out and "skill_other" not in out


# ---------------------------------------------------------------------------------------------- the Lead


def test_the_lead_is_told_to_staff_by_language_from_the_cards_and_the_install(monkeypatch):
    """11-04 §6: the Lead had only the cards' ``use_when``. Derived: a card's skill that stops shipping leaves it."""
    text = guide.staffing_text()
    for card in ("python_engineer", "c_engineer"):
        meta = roles.builtin_cards()[card].meta
        assert f"`{card}` when {meta['use_when'][0]}, so its run loads `{meta['skills'][0]}`" in text
    assert "Otherwise the default, `engineer`, whose run may load `python-development` or `c-development`" in text
    monkeypatch.setattr(skills, "shipped", lambda: frozenset({"python-development"}))
    fewer = guide.staffing_text()
    assert "c_engineer" not in fewer and "`c-development`" not in fewer
    monkeypatch.setattr(skills, "shipped", lambda: frozenset())
    assert guide.staffing_text() == ""


def test_role_list_shows_optional_skills_and_validate_names_unshipped_ones_without_failing(tmp_path, monkeypatch):
    class K:
        aew_root = tmp_path
        manifest: dict[str, Any] = {}

    (tmp_path / "roles").mkdir()
    (tmp_path / "roles" / "mine.yaml").write_text(
        "schema: aew/role/v1\nrole: mine\ndisplay_name: Mine\nextends: reviewer\npurpose: p\n"
        "optional_skills: [c-development, not-yet]\n", encoding="utf-8")
    ops = Roles(K(), units=None)  # type: ignore[arg-type]
    listed = {c["id"]: c for c in ops.role_list()["cards"]}
    assert listed["engineer"]["optional_skills"] == ["python-development", "c-development"]
    assert listed["mine"]["optional_skills"] == ["c-development", "not-yet"]
    whole = ops.role_validate()
    assert whole["ok"] is True and whole["optional_unshipped"] == {"mine": ["not-yet"]}
    one = ops.role_validate(str(tmp_path / "roles" / "mine.yaml"))
    assert one["ok"] is True and one["optional_unshipped"] == ["not-yet"]
