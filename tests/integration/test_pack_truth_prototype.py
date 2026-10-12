"""The pack-truth prototype gate (the pack-truth plan, reviewed CLEAR, §2.3; PT-1's first commit).

Two roles (implementer, reviewer) × two modes (harness: the launch prompt and the OpenCode system text; manual: `aew
context pack` and `aew context show`), each with the worker commands' results and help. Each cell's fixture is built
unhooked; its hooked and unhooked renders run in separate processes, each on its own copy of that state (pt_harness).
The gate: every span traced, the planted control met, and strip-equivalence in all four cells.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import pt_harness as H
import pt_hook
import pt_trace as T
import pytest

# The planted control (§2.3). Each token matches the pattern (`AEW_[A-Z_]+`), so each is a span, and each must trace
# to its own key. The keys are the inventory's (file, scope, hash) for the plan's base, where the per-hit unit is
# dispositioned D and the baseline unit is baseline (work: PT-1).
CONTEXT = "knowledge/context.py"
REVIEWER_YAML = "src/aew/roles/archetypes/reviewer.yaml"
PER_HIT = ("AEW_PT_PLANT_PERHIT", 196, "Workspace", "src/aew/knowledge/context.py|_launch_contract|1ecced61d852de4a")
BASELINE = ("AEW_PT_PLANT_BASELINE", 271, "risk class", "src/aew/knowledge/context.py|_requirement|3021e2d34598925c")
YAML_LEAF = ("AEW_PT_PLANT_YAML", "responsibilities[0]", f"{REVIEWER_YAML}|responsibilities[0]|54f7a6bcb10670ef")
NESTED = ("AEW_PT_PLANT_NESTED", "authority[0]", f"{REVIEWER_YAML}|authority[0]|79e03b46e8290719")
# The interpolated registry value: the cells' state lives under a directory whose name is this token, so every
# workspace and state path a cell renders carries it.
VALUE_TOKEN = "AEW_PT_PLANT_VALUE"
CHECK_UNIT_KEY = "src/aew/knowledge/context.py|_check_results|0df49bc082264636"
# The test-quoted copy: a product string, as the control renders it, quoted in a test (it must change nothing).
QUOTED_COPY = "- Workspace: ` AEW_PT_PLANT_PERHIT "


def constant_site(rel: str, line: int, contains: str) -> str:
    """``line:col`` of the string constant on ``line`` of src/aew/``rel`` that contains ``contains``."""
    tree = ast.parse((pt_hook.PKG / rel).read_text(encoding="utf-8"))
    found = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and n.lineno == line and contains in n.value]
    assert len(found) == 1, (rel, line, contains, found)
    return f"{found[0].lineno}:{found[0].col_offset}"


PLANTS = {CONTEXT: {constant_site(CONTEXT, PER_HIT[1], PER_HIT[2]): PER_HIT[0],
                    constant_site(CONTEXT, BASELINE[1], BASELINE[2]): BASELINE[0]}}
YAML_PLANTS = {REVIEWER_YAML: {YAML_LEAF[1]: YAML_LEAF[0], NESTED[1]: NESTED[0]}}


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(VALUE_TOKEN)


@pytest.fixture(scope="module")
def fixtures(base: Path) -> dict[str, H.Fixture]:
    return {role: H.build(base, role) for role in H.ROLES}


@pytest.fixture(scope="module")
def renders(fixtures: dict[str, H.Fixture]) -> dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]:
    """Every cell, hooked and unhooked, each in its own process on its own copy of the cell's state."""
    return {(role, mode): (H.run(fixtures[role], mode, hooked=True), H.run(fixtures[role], mode, hooked=False))
            for role in H.ROLES for mode in H.MODES}


@pytest.fixture(scope="module")
def registry_inputs() -> tuple[frozenset[str], tuple[str, ...]]:
    return T.field_names(), T.cli_identifiers()


def judged(fx: H.Fixture, hooked: dict[str, Any], registry_inputs: tuple[frozenset[str], tuple[str, ...]]
           ) -> list[T.Judged]:
    fields, cli = registry_inputs
    return T.judge_render(hooked, T.facts(fx.spec, fx.pristine, fields=fields, cli=cli))


def test_strip_equivalence_every_cell(renders):
    """§2.3: in all four cells the hooked render, every marker removed, is byte-identical to the unhooked one. The two
    copies hold the same state, so no registry value needs normalising: the comparison is exact."""
    for cell, (hooked, plain) in renders.items():
        assert H.strip_equivalence(hooked, plain, []) == [], cell
        assert set(hooked["texts"]) == set(plain["texts"]), cell
        # every delivery point rendered, and none refused
        assert all(e["code"] == 0 for e in plain["texts"].values()), (cell, plain["texts"])


def test_every_span_traced_every_cell(renders, fixtures, registry_inputs):
    """§2.3: every span of the pattern in every cell traces to one source: a unit, a fenced authored input, a
    registered value its accessor confirms, a named JSON field, or a CLI identifier of the live parser."""
    for (role, mode), (hooked, _) in renders.items():
        result = judged(fixtures[role], hooked, registry_inputs)
        assert result, (role, mode)
        untraced = [j for j in result if j.source == "untraced"]
        assert untraced == [], (role, mode, untraced)
        # the pack and the worker commands' results are traced, not only the help
        assert {j.text for j in result} >= {"whoami", "submit", "help aew"} | (
            {"prompt", "system text"} if mode == "harness" else {"context pack", "context show"})


def test_every_value_class_has_an_accessor_and_the_tables_are_distinct():
    """The closed registry: every class it names has an accessor, and no hand-listed key is written twice (a dict
    display keeps the last of two equal keys silently)."""
    assert set(T.VALUE_SITES.values()) | set(T.JSON_FIELDS.values()) <= set(T.CLASSES)
    for path, name in ((Path(T.__file__), "VALUE_SITES"), (Path(T.__file__), "JSON_FIELDS"),
                       (Path(pt_hook.__file__), "HOOK_FUNCTIONS"), (Path(pt_hook.__file__), "FENCED_FIELDS")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        display = next(st.value for st in tree.body if isinstance(st, ast.AnnAssign)
                       and isinstance(st.target, ast.Name) and st.target.id == name)
        keys = [ast.unparse(k) for k in display.keys]  # type: ignore[union-attr]
        assert len(keys) == len(set(keys)), name


def control(fx: H.Fixture, quoted: Path | None = None) -> dict[str, Any]:
    return H.run(fx, "manual", hooked=True, plants=PLANTS, yaml_plants=YAML_PLANTS, quoted=quoted)


@pytest.fixture(scope="module")
def controlled(fixtures, registry_inputs) -> tuple[dict[str, Any], list[T.Judged]]:
    fx = fixtures["reviewer"]
    hooked = control(fx)
    return hooked, judged(fx, hooked, registry_inputs)


def spans_of(result: list[T.Judged], token: str, text: str = "context show") -> list[T.Judged]:
    return [j for j in result if j.span == token and j.text == text]


def test_control_baseline_per_hit_and_test_quoted_copy(fixtures, controlled, registry_inputs):
    """§2.3: a token planted in a baseline unit and one in a per-hit unit each trace to their own key, and a copy of
    the product string quoted in a test, loaded into the hooked process, changes nothing."""
    hooked, result = controlled
    assert [j.detail for j in spans_of(result, PER_HIT[0])] == [PER_HIT[3]]
    assert [j.detail for j in spans_of(result, BASELINE[0])] == [BASELINE[3]]
    assert QUOTED_COPY in H.strip_render(hooked)["context show"]["stdout"]
    with_copy = control(fixtures["reviewer"], quoted=Path(__file__))
    assert judged(fixtures["reviewer"], with_copy, registry_inputs) == result
    assert H.strip_render(with_copy) == H.strip_render(hooked)


def test_check_unit_span_traces_to_context_310(controlled):
    """§2.3: the `check \\`unit\\`` span of the reviewer's check results traces to context.py:310."""
    hooked, result = controlled
    hits = [j for j in result if j.text == "context show" and j.span == "check" and "check `unit`" in j.context]
    assert [j.detail for j in hits] == [CHECK_UNIT_KEY]
    units = [u for u in hooked["registry"]["units"].values()
             if f"{u['file']}|{u['scope']}|{u['hash']}" == CHECK_UNIT_KEY]
    assert {u["line"] for u in units} == {310}


def test_control_yaml_value_nested(controlled):
    """§2.3: a YAML prose leaf traces to its leaf's key; an interpolated registry value traces to its registered site
    and class; a nested marker (a joined list of wrapped data) resolves to the innermost, the YAML leaf, inside the
    join's value marker."""
    hooked, result = controlled
    assert [j.detail for j in spans_of(result, YAML_LEAF[0])] == [YAML_LEAF[2]]
    nested = spans_of(result, NESTED[0])
    assert [j.detail for j in nested] == [NESTED[2]]
    outer = nested[0].chain[1]
    assert outer.startswith("value:")
    site = hooked["registry"]["values"][outer.split(":", 1)[1]]
    assert (site["file"], site["function"], site["expr"]) == (
        "src/aew/knowledge/context.py", "_launch_contract", '"; ".join(p.role_def["authority"])')
    sites = {}
    for j in spans_of(result, VALUE_TOKEN):
        v = hooked["registry"]["values"][j.chain[0].split(":", 1)[1]]
        sites[(v["file"], v["line"], v["function"], v["expr"])] = (j.source, j.detail)
    assert sites[("src/aew/knowledge/context.py", 196, "_launch_contract", "p.workspace")] == ("value",
                                                                                               "workspace path")
    # wherever the token is rendered, it is traced as a registry value, never as product text
    everywhere = [j for j in result if j.span == VALUE_TOKEN]
    assert everywhere and {j.source for j in everywhere} <= {"value", "json-field"}


def tree_digest(*roots: Path, skip: Path | None = None) -> dict[str, str]:
    out = {}
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file() and (skip is None or skip not in p.parents) and "__pycache__" not in p.parts:
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_hooked_render_read_only(fixtures, base):
    """§2.3 (V10-4, V11-3): the hooked process may write only to its own state copy. A write it attempts outside the
    copy is refused before it happens, and nothing outside the copy changes: the pristine copies, the other cell, the
    product and these helpers."""
    fx = fixtures["implementer"]
    outside = base / "outside-the-copy.txt"
    before = tree_digest(base, pt_hook.PKG, H.HELPERS, skip=fx.root)
    hooked = H.run(fx, "harness", hooked=True, probe_write=outside)
    after = tree_digest(base, pt_hook.PKG, H.HELPERS, skip=fx.root)
    assert hooked["refused"] == [f"open {outside}"]
    assert not outside.exists()
    spec_files = {k for k in after if Path(k).name.startswith("spec-")}
    assert {k: v for k, v in after.items() if k not in spec_files} == \
        {k: v for k, v in before.items() if k not in spec_files}
    # it did write, inside its own copy: the check log and the submitted report
    assert hooked["texts"]["check run"]["code"] == 0 and hooked["texts"]["submit"]["code"] == 0


def test_marker_chars_in_input_fail(fixtures):
    """§2.3 (V10-5): any input to a hooked render that holds U+E000-E005 fails it closed, before the render starts:
    here a fixture project file. The planted file is removed, byte for byte, afterwards."""
    fx = fixtures["implementer"]
    planted = fx.pristine / "repo" / "calc" / "notes.txt"
    planted.write_text("a note with a marker  in it\n", encoding="utf-8", newline="\n")
    try:
        with pytest.raises(H.MarkerInInput, match="notes.txt"):
            H.run(fx, "manual", hooked=True)
    finally:
        planted.unlink()
    assert H.scan_for_markers(fx.pristine) == []
