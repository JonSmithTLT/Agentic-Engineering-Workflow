"""The pack-truth prototype gate (the pack-truth plan, reviewed CLEAR, §2.3; PT-1's first commit).

Two roles (implementer, reviewer) × two modes (harness: the launch prompt and the OpenCode system text; manual: `aew
context pack` and `aew context show`), each with the worker commands' results and help. Each cell's fixture is built
unhooked; its hooked and unhooked renders run in separate processes, each on its own copy of that state (pt_harness).
The gate: every span traced, the planted control met, and strip-equivalence in all four cells.

The controls are both kinds: positive plants that must trace to their own key (§2.3), and negative plants, one per
judge branch, that must come out untraced (F4 of the prototype's review; pt_negatives).

The harness cells run the worker commands in this process with the invocation's credential, not through the custody
bridge (item 11 of the review). The bridge's own texts are handed to PT-2: each is a refusal it raises
(``bridge.validate_request``, ``rebuild_error``), PT-2's capture scope (§2.5), and a bridge cell needs the supervisor
processes that are PT-2's second prerequisite. Its success path relays the result methods' dicts, which these cells
trace.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pt_harness as H
import pt_hook
import pt_negatives as N
import pt_scan
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
    """The node key (``pt_hook.node_keys``, as JSON) of the one string constant of src/aew/``rel`` on ``line`` (an
    f-string part: on its f-string's line) that contains ``contains``."""
    tree = ast.parse((pt_hook.PKG / rel).read_text(encoding="utf-8"))
    keys = pt_hook.node_keys(tree)
    found = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and n.lineno == line and contains in n.value]
    assert len(found) == 1, (rel, line, contains, found)
    return json.dumps(keys[id(found[0])])


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
    """Every cell, hooked and unhooked, each in its own process on its own copy of the cell's state. A render that
    fails is kept as its error, so each test fails on its own assertion (F6 of the review)."""
    return {(role, mode): (H.run(fixtures[role], mode, hooked=True, check=False),
                           H.run(fixtures[role], mode, hooked=False, check=False))
            for role in H.ROLES for mode in H.MODES}


@pytest.fixture(scope="module")
def registry_inputs() -> None:
    """Kept for the review's probe: the registry's inputs are read per cell now (``pt_trace.facts``)."""
    return None


def judged(fx: H.Fixture, hooked: dict[str, Any], registry_inputs: Any = None) -> list[T.Judged]:
    assert "error" not in hooked, hooked.get("error")
    return T.judge_render(hooked, T.facts(fx.spec, fx.pristine))


def test_strip_equivalence_every_cell(renders):
    """§2.3: in all four cells the hooked render, every marker removed, is byte-identical to the unhooked one. The two
    copies hold the same state, so no registry value needs normalising: the comparison is exact."""
    differences = {cell: H.strip_equivalence(hooked, plain, []) for cell, (hooked, plain) in renders.items()}
    assert {cell: d for cell, d in differences.items() if d} == {}
    for cell, (hooked, plain) in renders.items():
        assert set(hooked["texts"]) == set(plain["texts"]), cell
        # every delivery point rendered, and none refused
        assert all(e["code"] == 0 for e in plain["texts"].values()), (cell, plain["texts"])


def test_every_span_traced_every_cell(renders, fixtures):
    """§2.3: every span of the pattern in every cell traces to one source: a unit, a fenced authored input its
    accessor confirms, a registered value its accessor confirms, a JSON key or field of its delivery point, or
    argparse's own output."""
    for (role, mode), (hooked, _) in renders.items():
        result = judged(fixtures[role], hooked)
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
                       (Path(T.__file__), "JSON_RESULTS"), (Path(T.__file__), "NESTED_RECORDS"),
                       (Path(pt_scan.__file__), "PRODUCER_DISPOSITIONS"), (Path(pt_hook.__file__), "FENCED_FIELDS"),
                       (Path(N.__file__), "PLANTS")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        display = next(st.value for st in tree.body if isinstance(st, ast.AnnAssign)
                       and isinstance(st.target, ast.Name) and st.target.id == name)
        keys = [ast.unparse(k) for k in display.keys]  # type: ignore[union-attr]
        assert len(keys) == len(set(keys)), name


def control(fx: H.Fixture, quoted: Path | None = None) -> dict[str, Any]:
    return H.run(fx, "manual", hooked=True, plants=PLANTS, yaml_plants=YAML_PLANTS, quoted=quoted)


@pytest.fixture(scope="module")
def controlled(fixtures) -> tuple[dict[str, Any], list[T.Judged]]:
    fx = fixtures["reviewer"]
    hooked = control(fx)
    return hooked, judged(fx, hooked)


def spans_of(result: list[T.Judged], token: str, text: str = "context show") -> list[T.Judged]:
    return [j for j in result if j.span == token and j.text == text]


def test_control_baseline_per_hit_and_test_quoted_copy(fixtures, controlled):
    """§2.3: a token planted in a baseline unit and one in a per-hit unit each trace to their own key, and a copy of
    the product string quoted in a test, loaded into the hooked process, changes nothing."""
    hooked, result = controlled
    assert [j.detail for j in spans_of(result, PER_HIT[0])] == [PER_HIT[3]]
    assert [j.detail for j in spans_of(result, BASELINE[0])] == [BASELINE[3]]
    assert QUOTED_COPY in H.strip_render(hooked)["context show"]["stdout"]
    with_copy = control(fixtures["reviewer"], quoted=Path(__file__))
    assert judged(fixtures["reviewer"], with_copy) == result
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


# ---------------------------------------------------------------------------------------- negative controls (F4)

NEGATIVES = ["fence-edit", "value-unregistered", "value-refused", "ref-rebound", "data-mutated", "json-key",
             "json-value", "help-prose", "cli-metavar"]
# plant -> (delivery point, a token or text every span inside which must be untraced)
NEGATIVE_SPANS: dict[str, tuple[str, str]] = {
    "fence-edit": ("context show", "AEW_PT_NEG_FENCE"),
    "value-unregistered": ("context show", "AEW_PT_NEG_VALUE"),
    "value-refused": ("context show", "AEW_PT_NEG_ACCESSOR"),
    "ref-rebound": ("context show", "AEW_PT_NEG_REF"),
    "data-mutated": ("context show", "AEW_PT_NEG_DATA"),
    "json-key": ("whoami", "AEW_PT_NEG_KEY"),
    "json-value": ("whoami", "AEW_PT_NEG_JSON"),
    "help-prose": ("help whoami", N.HELP),
    "cli-metavar": ("help whoami", N.METAVAR),
}


@pytest.fixture(scope="module")
def negatives(fixtures) -> tuple[dict[str, Any], list[T.Judged]]:
    fx = fixtures["implementer"]
    hooked = H.run(fx, "manual", hooked=True, negatives=NEGATIVES)
    return hooked, judged(fx, hooked)


def planted(hooked: dict[str, Any], result: list[T.Judged], text: str, plant: str) -> list[T.Judged]:
    """The judged spans that lie inside an occurrence of ``plant`` in ``text`` (its stripped, judged form)."""
    stripped = pt_hook.strip(T.judged_text(text, hooked["texts"][text])[0])
    start = stripped.find(plant)
    assert start >= 0, (text, plant)
    return [j for j in result if j.text == text and start <= j.start and j.end <= start + len(plant)]


@pytest.mark.parametrize("plant", NEGATIVES)
def test_negative_control_comes_out_untraced(negatives, plant):
    """F4: for each judge branch, a planted string that the branch must not accept (product prose with no unit, a value
    the registry does not name or its accessor refuses, a key outside the closed list, help prose argparse did not
    generate) comes out untraced, so a branch widened to accept a whole position fails the gate."""
    hooked, result = negatives
    text, token = NEGATIVE_SPANS[plant]
    spans = planted(hooked, result, text, token) if " " in token else \
        [j for j in result if j.text == text and token in j.span]
    assert spans, (plant, text, token)
    assert {j.source for j in spans} == {"untraced"}, (plant, spans)


def test_negative_control_tampered_card_in_a_manual_cell(fixtures):
    """Item 4 of the review: a stored card whose content differs from the built-in card it names reaches the manual
    cells (`context pack` regenerates and only reports the mismatch); its prose is not wrapped, so it is untraced."""
    fx = fixtures["reviewer"]
    hooked = H.run(fx, "manual", hooked=True, tampered_card=True)
    assert json.loads(hooked["texts"]["context pack"]["stdout"])["matches_recorded"] is False
    spans = [j for j in judged(fx, hooked) if j.span == "AEW_PT_NEG_CARD"]
    assert spans and {j.source for j in spans} == {"untraced"}


def test_data_markers_keep_whitespace_outside(renders, fixtures):
    """Item 6 of the review: a YAML leaf, a fence or a `+` value is wrapped with its leading and trailing whitespace
    outside the marker, so a renderer's `strip()` of it still strips it. The invariant holds in every cell and in a
    control that plants whitespace around a YAML leaf and a `+` value."""
    for cell, (hooked, _) in renders.items():
        assert T.whitespace_inside(hooked) == [], cell
    fx = fixtures["implementer"]
    rel, path = N.YAML_WS_LEAF[0].format(role="implementer"), N.YAML_WS_LEAF[1]
    hooked = H.run(fx, "manual", hooked=True, negatives=["plus-ws"], yaml_plants={rel: {path: N.YAML_WS_TOKEN}})
    shown = H.strip_render(hooked)["context show"]["stdout"]
    assert N.YAML_WS_TOKEN.strip() in shown and N.PLUS_WS.strip() in shown  # the plants reached the pack
    assert T.whitespace_inside(hooked) == []


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
    planted_file = fx.pristine / "repo" / "calc" / "notes.txt"
    planted_file.write_text(f"a note with a marker {chr(0xE003)} in it\n", encoding="utf-8", newline="\n")
    try:
        with pytest.raises(H.MarkerInInput, match="notes.txt"):
            H.run(fx, "manual", hooked=True)
    finally:
        planted_file.unlink()
    assert H.scan_for_markers(fx.pristine) == []
