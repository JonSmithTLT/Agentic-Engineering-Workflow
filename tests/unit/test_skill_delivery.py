"""Skills reach workers by their card's fit (register E127; the designer's rulings of 2026-11-03 §3 and 2026-11-04).

AEW's own install ships its skills with a manifest of hashes (the Lead's list among them: ``test_lead_skills.py``). A
card's ``skills:`` and ``optional_skills`` decide what a run may reach. The supervisor copies what is exposed into the
run's own folder, the projection lets the ``skill`` tool list exactly those, and the agent is told, from the plan,
which to load. The record says what was offered, exposed, delivered and loaded. Nothing here runs a model: the live
test is ``tests/live/test_skills_live.py``, on the VM.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
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
SHIPS = ["acceptance-verification", "adversarial-review", "c-development", "c-review", "ci-evidence-triage",
         "codebase-investigation", "debugging-root-cause-analysis", "delegation-handoffs", "empirical-evaluation",
         "engineering-planning", "mechanical-enumeration",
         "python-development", "requirements-clarification", "security-review", "technical-writing", "test-design"]
UNSHIPPED = "never-shipped"  # a name no skill will take, so these tests never churn as skills ship


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


def test_the_shipped_skills_ship_with_a_manifest_that_hashes_exactly_their_allow_listed_files():
    assert sorted(skills.shipped()) == SHIPS
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


# Code is not prose: a fenced block or an inline code span holds no link (E136: an example's
# ``HANDLERS[path](record)``). A backtick fence's info string holds no backtick, so a line that opens with three
# backticks and holds another is not a fence (CommonMark; E136's review, m2).
CODE = re.compile(r"^ {0,3}(```(?![^\n]*`)|~~~).*?^ {0,3}\1[^\n]*$|`[^`\n]+`", re.M | re.S)
INLINE = re.compile(r"\]\(\s*<?([^)\s<>]*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s<>]+)>?", re.M)


def link_targets(text: str) -> list[str]:
    """Every link a Markdown file's prose holds, inline or reference-style, raw (fragment and all); an inline ``](``
    the pattern cannot read fails rather than being skipped."""
    prose = CODE.sub("", text)
    found = INLINE.findall(prose)
    assert len(found) == prose.count("]("), "an inline link the pattern cannot read"
    return found + DEFINITION.findall(prose)


def test_every_link_in_a_shipped_skill_reaches_a_shipped_file_and_skill_md_links_every_one():
    """The pointer rule (E142): a step moved to ``references/`` or ``examples/`` is read only through its link, so a
    broken link loses the step silently. ``specification.md``: each runtime resource has an explicit link from the
    entrypoint. Every link form is read: inline with a ``#fragment``, a ``"title"`` or ``<angle brackets>``, and a
    reference-style definition; an inline ``](`` the pattern cannot read fails rather than being skipped (E142's
    review). A link to a fragment of the same file names no file and is left out. Code holds no link
    (:data:`CODE`).

    Known limits, none met by a shipped file: an indented (four-space) code block is read as prose; a code span of
    two or more backticks, or one that crosses a line, is not recognised; a fence of four or more backticks or tildes
    closes at the first three; HTML anchors and ``<autolinks>`` are not read."""
    for name, entry in skills.entries().items():
        listed = set(entry["files"])
        linked_from_skill_md: set[str] = set()
        for rel in listed:
            here = PurePosixPath(rel).parent
            for raw in link_targets((SHIPPED / name / rel).read_text(encoding="utf-8")):
                target = raw.split("#", 1)[0]
                if not target and raw.startswith("#"):
                    continue
                assert target and "://" not in target, (name, rel, raw)
                resolved = posixpath.normpath((here / target).as_posix())
                assert resolved in listed, (name, rel, target)
                if rel == skills.SKILL_FILE:
                    linked_from_skill_md.add(resolved)
        assert linked_from_skill_md == listed - {skills.SKILL_FILE}, name


def test_a_line_opening_with_backticks_that_holds_another_is_no_fence_so_the_link_after_it_is_read():
    """E136's review (m2): taken as a fence, the line would hide every link up to the next fence, so a broken link
    after it would pass."""
    planted = "```not`a fence\nSee [the step](references/missing.md).\n\n```\ncode\n```\n"
    assert "references/missing.md" in link_targets(planted)
    assert link_targets("```text\nSee [x](hidden.md).\n```\n") == []  # a real fence still hides its contents


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
    planned = skills.plan(["adversarial-review", UNSHIPPED],
                          ["adversarial-review", "c-development", "frontend-design"])
    assert planned["requested"] == ["adversarial-review", UNSHIPPED]
    assert planned["offered"] == ["c-development", "frontend-design"]  # a name in both counts as skills:
    assert planned["exposed"] == ["adversarial-review", "c-development"]
    assert planned["unavailable"] == [UNSHIPPED]  # only what skills: asked for
    assert planned["reasons"] == {"frontend-design": "not_shipped", UNSHIPPED: "not_shipped"}
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
    """The ruling's §2 test."""
    for card in roles.builtin_cards().values():
        assert set(card.meta.get("optional_skills") or []) <= skills.shipped(), card.id


def test_every_skill_a_built_in_card_requests_is_shipped():
    """E142: ``security_reviewer`` and ``c_reviewer`` asked for skills AEW did not ship, so their runs were told
    "does not provide". Now every built-in card's ``skills:`` is shipped, and a new card naming an unwritten skill
    fails here."""
    for card in roles.builtin_cards().values():
        assert set(card.meta.get("skills") or []) <= skills.shipped(), card.id


@pytest.mark.parametrize("card, skill", [("security_reviewer", "security-review"), ("c_reviewer", "c-review")])
def test_the_specialist_reviewers_get_their_skill_delivered_and_nothing_reported_missing(tmp_path, card, skill):
    planned = skills.plan(roles.builtin_cards()[card].meta["skills"])
    assert (planned["exposed"], planned["unavailable"], planned["reasons"]) == ([skill], [], {})
    delivered = skills.deliver(planned, tmp_path / "skills")
    assert delivered["exposed"] == [skill]
    assert skills.root_problems(tmp_path / "skills", delivered["exposed"]) == []
    said = lines(delivered)
    assert said == [said[0]] and said[0].startswith(f"- Load `{skill}` with the `skill` tool")


def test_the_cards_name_the_shipped_skills_with_their_versions_moved():
    cards = roles.builtin_cards()
    assert cards["code_reviewer"].meta["skills"] == ["adversarial-review"]
    assert cards["verifier"].meta["skills"] == ["acceptance-verification"]
    assert cards["engineer"].meta["optional_skills"] == OFFERED["engineer"]
    # code_reviewer went to 3 for register E126's three lines on test work, after the skills moved it to 2. E136's
    # first batch moved engineer to 3 and the four others it touched to 2; its second batch moves each card it offers
    # a skill to one more: code_reviewer and engineer to 4, the other five to 3. Its third moves code_reviewer to 5,
    # and `technical_writer` (E167) starts at 1. Its fourth moves the four cards it offers a skill to one more:
    # code_reviewer to 6, verifier and investigator to 4, researcher to 2.
    assert {c: cards[c].meta["version"] for c in ("code_reviewer", "verifier", "engineer", "python_engineer",
                                                  "c_engineer", "investigator", "planner", "technical_writer",
                                                  "researcher")} == {
        "code_reviewer": 6, "verifier": 4, "engineer": 4, "python_engineer": 3, "c_engineer": 3, "investigator": 4,
        "planner": 3, "technical_writer": 1, "researcher": 2}


# E136's first batch: the two candidates whose text is public in this repository, on the cards they fit, as
# optional_skills only (a card's skills: loads in every run, so a foundational skill there waits for its cost measured).
BATCH_1 = {
    "investigator": ["codebase-investigation", "debugging-root-cause-analysis"],
    "planner": ["codebase-investigation"],
    "engineer": ["debugging-root-cause-analysis"],
    "python_engineer": ["debugging-root-cause-analysis"],
    "c_engineer": ["debugging-root-cause-analysis"],
}


@pytest.mark.parametrize("card, batch", sorted(BATCH_1.items()))
def test_the_first_e136_batch_is_offered_on_its_cards_delivered_and_listed_never_requested(tmp_path, card, batch):
    meta = roles.builtin_cards()[card].meta
    assert not set(batch) & set(meta.get("skills") or [])
    planned = skills.plan(meta.get("skills") or [], meta.get("optional_skills"))
    assert set(batch) <= set(planned["offered"]) and set(batch) <= set(planned["exposed"])
    assert (planned["unavailable"], planned["reasons"]) == ([], {})
    delivered = skills.deliver(planned, tmp_path / "skills")
    assert delivered["exposed"] == planned["exposed"]
    assert skills.root_problems(tmp_path / "skills", delivered["exposed"]) == []
    listed = next(line for line in lines(delivered) if line.startswith("- The `skill` tool lists "))
    assert all(f"`{name}`" in listed for name in batch), listed


# E136's second batch, the planning and testing group, by the operator's mapping of 2026-11-25: optional_skills only.
# `engineering-planning` and `requirements-clarification` already ship for the Lead (E161); a card reads the same copy.
BATCH_2 = {
    "planner": ["engineering-planning", "requirements-clarification"],
    "investigator": ["requirements-clarification", "mechanical-enumeration"],
    "engineer": ["test-design"],
    "python_engineer": ["test-design"],
    "c_engineer": ["test-design"],
    "verifier": ["test-design", "mechanical-enumeration"],
    "code_reviewer": ["mechanical-enumeration"],
}
# E136's third batch, by the designer's decision of 2026-11-06 on the Lead's skills and document work: (c) puts
# `technical-writing` on `code_reviewer` (E167), and the Lead's two items, accepted there, put the language skills on
# it too. optional_skills only; the language skills already ship (E127).
BATCH_3 = {"code_reviewer": ["technical-writing", "python-development", "c-development"]}
# E136's fourth batch, the evidence group, by the operator's answer of 2026-11-26 ("Your rec is fine on 2"):
# optional_skills only. `ci-evidence-triage` is also on the Lead's own list (``test_lead_skills.py``).
BATCH_4 = {
    "researcher": ["empirical-evaluation"],
    "investigator": ["empirical-evaluation"],
    "verifier": ["ci-evidence-triage"],
    "code_reviewer": ["ci-evidence-triage"],
}
BATCHES = (BATCH_1, BATCH_2, BATCH_3, BATCH_4)
# Every built-in card's offered list, whole: E127's language skills on the default implementer, then E136's batches.
OFFERED = {card: ([] if card != "engineer" else ["python-development", "c-development"])
           + [name for batch in BATCHES for name in batch.get(card, [])]
           for card in {"engineer", *(card for batch in BATCHES for card in batch)}}


@pytest.mark.parametrize("card, batch", sorted(BATCH_2.items()))
def test_the_second_e136_batch_is_offered_on_its_cards_delivered_and_listed_never_requested(tmp_path, card, batch):
    meta = roles.builtin_cards()[card].meta
    assert not set(batch) & set(meta.get("skills") or [])
    planned = skills.plan(meta.get("skills") or [], meta.get("optional_skills"))
    assert set(batch) <= set(planned["offered"]) and set(batch) <= set(planned["exposed"])
    assert (planned["unavailable"], planned["reasons"]) == ([], {})
    delivered = skills.deliver(planned, tmp_path / "skills")
    assert delivered["exposed"] == planned["exposed"]
    assert sorted(p.name for p in (tmp_path / "skills").iterdir()) == delivered["exposed"]
    assert skills.root_problems(tmp_path / "skills", delivered["exposed"]) == []
    listed = next(line for line in lines(delivered) if line.startswith("- The `skill` tool lists "))
    assert all(f"`{name}`" in listed for name in batch), listed


@pytest.mark.parametrize("card, batch", sorted(BATCH_3.items()))
def test_the_third_e136_batch_is_offered_on_its_card_delivered_and_listed_never_requested(tmp_path, card, batch):
    meta = roles.builtin_cards()[card].meta
    assert not set(batch) & set(meta.get("skills") or [])
    planned = skills.plan(meta.get("skills") or [], meta.get("optional_skills"))
    assert set(batch) <= set(planned["offered"]) and set(batch) <= set(planned["exposed"])
    assert (planned["unavailable"], planned["reasons"]) == ([], {})
    delivered = skills.deliver(planned, tmp_path / "skills")
    assert delivered["exposed"] == planned["exposed"]
    assert sorted(p.name for p in (tmp_path / "skills").iterdir()) == delivered["exposed"]
    assert skills.root_problems(tmp_path / "skills", delivered["exposed"]) == []
    listed = next(line for line in lines(delivered) if line.startswith("- The `skill` tool lists "))
    assert all(f"`{name}`" in listed for name in batch), listed


@pytest.mark.parametrize("card, batch", sorted(BATCH_4.items()))
def test_the_fourth_e136_batch_is_offered_on_its_cards_delivered_and_listed_never_requested(tmp_path, card, batch):
    meta = roles.builtin_cards()[card].meta
    assert not set(batch) & set(meta.get("skills") or [])
    planned = skills.plan(meta.get("skills") or [], meta.get("optional_skills"))
    assert set(batch) <= set(planned["offered"]) and set(batch) <= set(planned["exposed"])
    assert (planned["unavailable"], planned["reasons"]) == ([], {})
    delivered = skills.deliver(planned, tmp_path / "skills")
    assert delivered["exposed"] == planned["exposed"]
    assert sorted(p.name for p in (tmp_path / "skills").iterdir()) == delivered["exposed"]
    assert skills.root_problems(tmp_path / "skills", delivered["exposed"]) == []
    listed = next(line for line in lines(delivered) if line.startswith("- The `skill` tool lists "))
    assert all(f"`{name}`" in listed for name in batch), listed


def test_the_technical_writer_is_an_implementer_card_whose_run_is_told_to_load_technical_writing(tmp_path):
    """E167 (the designer's decision of 2026-11-06, (c)): a delegated document is a mutating Ticket under a card on
    the implementer archetype, with ``technical-writing`` in ``skills:``, so every run of it is told to load it and
    its pack's ``sources`` pin it. The card widens nothing: its capabilities are the archetype's own."""
    card = roles.builtin_cards()["technical_writer"]
    assert card.archetype == "implementer" and card.meta["skills"] == ["technical-writing"]
    assert set(card.meta["required_capabilities"]) == set(roles.archetype("implementer")["capabilities"])
    assert not card.meta.get("optional_capabilities") and not card.meta.get("restrict")
    planned = skills.plan(card.meta["skills"], card.meta.get("optional_skills") or [])
    assert (planned["requested"], planned["exposed"]) == (["technical-writing"], ["technical-writing"])
    assert (planned["offered"], planned["unavailable"], planned["reasons"]) == ([], [], {})
    delivered = skills.deliver(planned, tmp_path / "skills")
    assert skills.root_problems(tmp_path / "skills", delivered["exposed"]) == []
    said = lines(delivered)
    assert said == [said[0]] and said[0].startswith("- Load `technical-writing` with the `skill` tool")


def test_every_built_in_card_is_offered_exactly_its_mapped_skills_and_nothing_else():
    """Fit is per card and judged in review (E136): a card gains or loses an offered skill only by a re-hash PR that
    names it, so each card's ``optional_skills`` is exactly its mapping, in order, and a card with none has none."""
    for card in roles.builtin_cards().values():
        assert (card.meta.get("optional_skills") or []) == OFFERED.get(card.id, []), card.id


# ---------------------------------------------------------------------------------------------- the copy


def test_the_copy_holds_exactly_the_exposed_skills_and_their_listed_files(tmp_path):
    planned = skills.plan(["adversarial-review", UNSHIPPED], ["python-development"])
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


def test_the_copy_takes_only_the_manifests_files_even_when_the_install_holds_another(tmp_path, monkeypatch):
    """Review E127 M1 (O1): an allow-listed file the manifest does not list is in the installed folder, and the run's
    copy never holds it. The re-hash is over the manifest's paths and the root check over the allow-list, so only the
    copy loop keeps it out, and ``delivered.sha256`` goes on describing what the run can read."""
    package = tmp_path / "pkg"
    shutil.copytree(Path(skills.__file__).resolve().parent, package)
    references = package / skills.SHIPPED / "c-development" / "references"
    references.mkdir(exist_ok=True)
    (references / "unlisted.md").write_text("x", encoding="utf-8")
    assert skills.allowed("references/unlisted.md")  # so the allow-list alone would let it through

    class Resources:
        @staticmethod
        def files(_name: str) -> Path:
            return package

    monkeypatch.setattr(skills, "resources", Resources)
    root = tmp_path / "copy"
    delivered = skills.deliver(skills.plan([], ["c-development"]), root)
    assert delivered["exposed"] == ["c-development"]
    copied = sorted(p.relative_to(root / "c-development").as_posix() for p in (root / "c-development").rglob("*")
                    if p.is_file())
    assert copied == sorted(skills.entries()["c-development"]["files"])


# ---------------------------------------------------------------------------------------------- the projection


AT = projection.skills_at("/r/harness", "/")


@pytest.mark.parametrize("role", ["implementer", "reviewer"])
def test_the_skill_rules_are_exactly_the_copied_set_with_the_folder_readable_and_never_editable(tmp_path, role):
    """A2 and A5: a ``skill allow`` rule for every copied skill and no other; the folder's read grant always goes with
    its edit deny (the read grant alone let a model write an unbound copy: skills probe, check 7)."""
    planned = skills.plan(["adversarial-review", UNSHIPPED], ["c-development", "frontend-design"])
    root = tmp_path / "skills"
    delivered = skills.deliver(planned, root)
    assert delivered["exposed"] == planned["exposed"] == ["adversarial-review", "c-development"]  # never widened
    c = contract(role=role, planned=delivered)
    config = projection.invocation_config(c, skills_dir=AT)
    rules = config["permissions"]
    allowed = sorted(r["resource"] for r in rules if r["action"] == "skill" and r["effect"] == "allow")
    assert allowed == delivered["exposed"] == sorted(p.name for p in root.iterdir())
    for name in (UNSHIPPED, "frontend-design", "opencode", "report", "anything"):
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
        "- The `skill` tool lists `c-development`, `python-development`: load each one whose description matches your "
        "task."]


def test_an_unshipped_skill_with_a_shipped_optional_one_says_both():
    """A card whose ``skills:`` names a skill AEW does not ship (``security_reviewer``'s case before E142)."""
    said = lines(skills.plan([UNSHIPPED], ["adversarial-review"]))
    assert said == ["- The `skill` tool lists `adversarial-review`: load each one whose description matches your task.",
                    f"- Skills your role card requests that this harness does not provide: {UNSHIPPED}. Proceed "
                    "without them and say so in your report."]


def test_the_tool_lists_clause_names_what_was_delivered_never_an_unshipped_or_failed_one(tmp_path, monkeypatch):
    """Review E127 M1 (O2): the clause draws on ``exposed``, not on ``offered``. A project card's unshipped optional
    name, and one whose copy failed, are offered but not listed by the tool, so the system text never names them."""
    planned = skills.plan([], ["c-development", "ignore-this-text", "python-development"])
    assert planned["offered"] != planned["exposed"]  # the sets differ, so the test can tell them apart
    assert lines(planned) == ["- The `skill` tool lists `c-development`, `python-development`: load each one whose "
                              "description matches your task."]
    real = Path.write_bytes

    def failing(self: Path, data: bytes) -> int:
        if "python-development" in self.parts:
            raise OSError("disk full")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing)
    delivered = skills.deliver(planned, tmp_path / "copy")
    assert delivered["reasons"]["python-development"] == skills.COPY_FAILED
    assert lines(delivered) == ["- The `skill` tool lists `c-development`: load each one whose description matches "
                                "your task."]


def test_one_of_two_skills_shipped_loads_one_and_names_the_other_unavailable():
    said = lines(skills.plan(["c-development", UNSHIPPED]))
    assert said[0].startswith("- Load `c-development` with the `skill` tool")
    assert said[1].startswith(f"- Skills your role card requests that this harness does not provide: {UNSHIPPED}.")
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
    assert ("Optional skills (load one only if the `skill` tool lists it and your task matches): "
            + ", ".join(engineer["optional_skills"])) in before  # the card's own list, in its order
    monkeypatch.setattr(skills, "entries", lambda: {})
    monkeypatch.setattr(skills, "check", lambda name: (skills.NOT_SHIPPED, {}))
    assert card_lines(engineer) == before


def test_a_card_without_optional_skills_renders_as_before():
    """A pinned card from before the field, or one whose optional names are all in ``skills:``: no new line."""
    old = {k: v for k, v in roles.builtin_cards()["python_engineer"].meta.items() if k != "optional_skills"}
    both = {**old, "optional_skills": ["python-development"]}
    assert card_lines(old) == card_lines(both)
    assert not any(s.startswith("Optional skills") for s in card_lines(old))


def test_the_packs_sources_pin_the_cards_skills_only():
    assert skills.pins(["adversarial-review", UNSHIPPED]) == [
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
    for card in ("python_engineer", "c_engineer", "technical_writer"):
        meta = roles.builtin_cards()[card].meta
        assert f"`{card}` when {meta['use_when'][0]}, so its run loads `{meta['skills'][0]}`" in text
    assert ("Otherwise the default, `engineer`, whose run may load `python-development` or `c-development` when its "
            "task matches.") in text
    monkeypatch.setattr(skills, "shipped", lambda: frozenset({"python-development"}))
    fewer = guide.staffing_text()
    assert "c_engineer" not in fewer and "`c-development`" not in fewer
    assert "technical_writer" not in fewer and "`technical-writing`" not in fewer
    monkeypatch.setattr(skills, "shipped", lambda: frozenset())
    assert guide.staffing_text() == ""


def test_the_staffing_line_names_what_the_offering_implementer_cards_all_offer_apart_from_the_language(monkeypatch):
    """E136's review (m1): a skill the implementer cards all offer is not about the language, so the default's clause
    names only what a language card requests, and one more sentence names the rest: the intersection of the
    ``optional_skills`` of the implementer cards that offer any, derived, never restated. A card that offers none
    (`technical_writer`, E167) is left out by name, so "every" is said only when it is true of every card."""
    text = guide.staffing_text()
    cards = dict(roles.builtin_cards())
    implementers = sorted(c.id for c in cards.values() if c.archetype == "implementer")
    offering = [c for c in implementers if cards[c].meta.get("optional_skills")]
    assert offering == ["c_engineer", "engineer", "python_engineer"] and "technical_writer" in implementers
    named = ("The runs of `c_engineer`, `engineer` and `python_engineer` may also load "
             "`debugging-root-cause-analysis` or `test-design` when their task matches.")
    assert text.endswith(named) and text.count("debugging-root-cause-analysis") == text.count("`test-design`") == 1
    assert "Every implementer card" not in text

    def without(card: str, offered: list[str] | None = None) -> str:
        changed = dict(cards)
        if offered is None:
            del changed[card]
        else:
            c = cards[card]
            changed[card] = roles.Card(c.id, {**c.meta, "optional_skills": offered}, c.source, c.path, c.sha256)
        monkeypatch.setattr(roles, "builtin_cards", lambda: changed)
        return guide.staffing_text()

    # With every implementer card offering them, the sentence says "every", as it did before the writer card.
    assert without("technical_writer").endswith(
        "Every implementer card's run may also load `debugging-root-cause-analysis` or `test-design` when its task "
        "matches.")
    # A card that stops offering them leaves the sentence, and the others keep it.
    fewer = without("c_engineer", [])
    assert fewer.endswith("The runs of `engineer` and `python_engineer` may also load "
                          "`debugging-root-cause-analysis` or `test-design` when their task matches.")
    # A skill only some of the offering cards offer is not in it, and with none shared there is no sentence.
    one = without("c_engineer", ["test-design"])
    assert one.endswith("may also load `test-design` when their task matches.")
    assert "debugging-root-cause-analysis" not in one
    none = without("c_engineer", ["mechanical-enumeration"])
    assert "may also load" not in none and none.endswith("when its task matches.")


def test_the_staffing_line_names_a_lone_offering_card_once_and_never_repeats_its_language_skills(monkeypatch):
    """With the default card the only one that offers anything, everything it offers is "shared": the sentence is
    about that one card, and leaves out the language skills its own clause has just named."""
    cards = dict(roles.builtin_cards())
    for card in ("c_engineer", "python_engineer"):
        c = cards[card]
        cards[card] = roles.Card(c.id, {**c.meta, "optional_skills": []}, c.source, c.path, c.sha256)
    monkeypatch.setattr(roles, "builtin_cards", lambda: cards)
    text = guide.staffing_text()
    assert text.endswith("Otherwise the default, `engineer`, whose run may load `python-development` or "
                         "`c-development` when its task matches. The run of `engineer` may also load "
                         "`debugging-root-cause-analysis` or `test-design` when its task matches.")
    assert text.count("`python-development`") == 2  # its language card's clause and the default's, never a third


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
    assert listed["engineer"]["optional_skills"] == roles.builtin_cards()["engineer"].meta["optional_skills"]
    assert listed["mine"]["optional_skills"] == ["c-development", "not-yet"]
    whole = ops.role_validate()
    assert whole["ok"] is True and whole["optional_unshipped"] == {"mine": ["not-yet"]}
    one = ops.role_validate(str(tmp_path / "roles" / "mine.yaml"))
    assert one["ok"] is True and one["optional_unshipped"] == ["not-yet"]
