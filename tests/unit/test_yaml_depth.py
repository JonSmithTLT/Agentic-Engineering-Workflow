"""YAML nesting is bounded (``util.YAML_MAX_DEPTH``), on both sides. libyaml's composer recurses in C with no depth
check, so a hostile document deep enough kills the process on Windows (a stack overflow, no exception); the
pure-Python composer raises RecursionError. So a document past the bound is refused before anything is composed, as a
ValidationFailed (reason ``yaml_too_deep``) on every platform and Python. AEW's writer holds the same bound, so a
document AEW wrote is never refused when it is read back, and the control store's own files, checked against their
hashes first, are read without the pass."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
import yaml

from aew import util
from aew.cli import fields
from aew.engine.store import Transition
from aew.errors import UsageError, ValidationFailed

ROOT = Path(__file__).resolve().parents[2]


def flow(depth: int) -> str:
    return "k: " + "[" * depth + "x" + "]" * depth + "\n"


def block(depth: int) -> str:
    return "".join(f"{'  ' * i}k{i}:\n" for i in range(depth + 1)) + f"{'  ' * (depth + 1)}v\n"


def nested(depth: int) -> object:
    """``depth`` mappings, one inside the other."""
    data: object = "x"
    for _ in range(depth):
        data = {"k": data}
    return data


@pytest.mark.parametrize("shape", [flow, block], ids=["flow", "block"])
def test_a_document_nested_past_the_bound_is_refused_and_one_at_the_bound_reads(shape):
    # flow(n) nests n sequences in one mapping, block(n) n mappings: both are n + 1 deep with the outer mapping
    at_bound = shape(util.YAML_MAX_DEPTH - 1)
    assert util.yaml_too_deep(at_bound) is None and util.load_yaml(at_bound) is not None
    with pytest.raises(ValidationFailed) as refused:
        util.load_yaml(shape(util.YAML_MAX_DEPTH), source="hostile.yaml")
    assert refused.value.details == {"reason": util.YAML_TOO_DEEP, "limit": util.YAML_MAX_DEPTH,
                                     "line": refused.value.details["line"]}
    assert refused.value.message.startswith("hostile.yaml: the YAML nests deeper than 64 levels")


def test_a_document_deep_enough_to_crash_the_composer_is_refused_in_process():
    """200,000 levels: composing this kills the interpreter on Windows (about 2,660 levels on Python 3.11), so a
    refusal here, in this process, shows the bound is checked before the document is composed."""
    with pytest.raises(ValidationFailed) as refused:
        util.load_yaml(flow(200_000))
    assert refused.value.details["reason"] == util.YAML_TOO_DEEP and refused.value.details["line"] == 1


def test_a_syntax_error_is_still_invalid_yaml_and_not_a_depth_refusal():
    with pytest.raises(ValidationFailed) as refused:
        util.load_yaml("k: [unclosed\n", source="broken.yaml")
    assert "invalid YAML" in refused.value.message and "reason" not in refused.value.details


def test_a_cli_fields_value_nested_past_the_bound_is_a_usage_error_not_a_recursion_error():
    with pytest.raises(UsageError, match="nests deeper than 64 levels"):
        fields._load(flow(5_000))
    assert fields._load("title: a\ngoal: [b, c]\n") == {"title": "a", "goal": ["b", "c"]}


@pytest.mark.parametrize("dump", [util.dump_yaml, util.safe_dump_yaml], ids=["dump_yaml", "safe_dump_yaml"])
def test_aew_writes_a_document_at_the_bound_reads_it_back_and_refuses_one_past_it(dump):
    """Nothing AEW writes can be refused when it is read: control state has free-form objects, and with a bound on
    reading alone, one deep value committed there would make the project's own store unreadable."""
    at_bound = nested(util.YAML_MAX_DEPTH)
    assert util.load_yaml(dump(at_bound)) == at_bound
    with pytest.raises(ValidationFailed) as refused:
        dump(nested(util.YAML_MAX_DEPTH + 1))
    assert refused.value.details == {"reason": util.YAML_TOO_DEEP, "limit": util.YAML_MAX_DEPTH}
    assert util.load_yaml(dump([nested(util.YAML_MAX_DEPTH - 1)] * 3)) == [nested(util.YAML_MAX_DEPTH - 1)] * 3


def test_the_bounded_writers_write_exactly_what_they_wrote_before():
    sample = {"id": "DR-0001", "subject": {"id": "T-0001", "kind": "ticket"}, "choice": "keep", "rev": 3,
              "notes": ["a: b", "multi\nline", "üñí", "#1"], "nested": [{"k": [1, 2, {"x": None}]}], "empty": {}}

    class Unbounded(util._SafeDumperBase):  # type: ignore[valid-type,misc]
        pass

    Unbounded.add_representer(str, util._str_representer)
    assert util.dump_yaml(sample) == yaml.dump(sample, Dumper=Unbounded, sort_keys=False, allow_unicode=True,
                                               default_flow_style=False, width=100)
    assert util.safe_dump_yaml(sample) == yaml.safe_dump(sample, sort_keys=False, allow_unicode=True)


def test_a_commit_whose_state_nests_past_the_bound_is_refused_and_writes_nothing(tmp_path):
    """A token's scope is free-form in control state's schema, so a value nested that deep passes validation; the
    commit is refused when control state is serialized, before anything touches disk."""
    from store_model import check_invariants, init, one_transaction

    store = init(tmp_path)
    one_transaction(store)
    control = tmp_path / "state" / "control.yaml"
    txn = tmp_path / "state" / "txn"
    before, txns = control.read_bytes(), sorted(txn.glob("*"))
    with store.session() as s:
        s.state["tokens"]["deep"] = {"kind": "lead", "verifier": "0" * 64, "scope": nested(util.YAML_MAX_DEPTH),
                                     "issued_at": "2026-10-23T00:00:00Z", "issued_by_generation": 0}
        s.write("records/item-deep.md", "x\n")
        with pytest.raises(ValidationFailed) as refused:
            s.commit(Transition(op="deep", actor={"kind": "test"}))
    assert refused.value.details["reason"] == util.YAML_TOO_DEEP
    assert control.read_bytes() == before and sorted(txn.glob("*")) == txns  # no redo record either
    assert not (tmp_path / "records" / "item-deep.md").exists()
    assert check_invariants(tmp_path) == 1
    one_transaction(store)  # the store is untouched: the next commit proceeds
    assert check_invariants(tmp_path) == 2


def yaml_documents() -> list[Path]:
    """Every YAML file in the checkout (the web app's dependencies and git's own files left out)."""
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".venv", "__pycache__"}]
        found += [Path(dirpath) / f for f in filenames if f.endswith((".yaml", ".yml"))]
    return sorted(found)


def test_every_yaml_document_in_the_repository_is_within_the_bound():
    """The bound never refuses a document AEW has: the deepest is 13 levels (the dashboard contract, 2026-10-23)."""
    documents = yaml_documents()
    assert len(documents) > 50 and ROOT / ".github" / "workflows" / "ci.yml" in documents
    too_deep = {}
    for path in documents:
        try:
            line = util.yaml_too_deep(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue  # not YAML AEW parses (a template, a deliberate syntax error); its parse would be refused anyway
        if line is not None:
            too_deep[str(path.relative_to(ROOT))] = line
    assert too_deep == {}


# Every place the product composes or writes YAML outside util's bounded functions, and why it is safe. `yaml.parse`
# (events only) composes nothing and is allowed anywhere. A new call site joins a list with its reason, or goes through
# `util.load_yaml`, `util.dump_yaml` or `util.safe_dump_yaml`. Coverage: calls written `yaml.<name>(...)` on the
# module itself, which is how every module imports it today; `from yaml import ...`, an alias of the module, or a
# loader or dumper class driven directly would not be seen (none in src/aew on 2026-10-23).
COMPOSERS = {"load", "safe_load", "full_load", "unsafe_load", "load_all", "safe_load_all", "full_load_all",
             "unsafe_load_all", "compose", "compose_all"}
DUMPERS = {"dump", "safe_dump", "dump_all", "safe_dump_all", "serialize", "serialize_all", "emit"}
COMPOSING = {
    "src/aew/util.py": "load_yaml (bounded by yaml_too_deep first) and load_own_yaml (below)",
    "src/aew/cli/fields.py": "_load: bounded by yaml_too_deep first",
    "src/aew/dashboard/contract.py": "the dashboard contract: a file of AEW's own, not a project's",
    "src/aew/maps/rules.py": "the installed rule table (package data)",
    "src/aew/stg02/adopted.py": "vendored adopted files, read only after their sealed sha256 matches",
}
WRITING = {"src/aew/util.py": "dump_yaml and safe_dump_yaml, both through the bounded representer"}
# The reads that skip the depth pass (util.load_own_yaml): files only dump_yaml writes, checked against their hash.
OWN_YAML = {
    "src/aew/engine/store.py": "control state (its checksum trailer) and a redo record (its sha256 in control state)",
}


def yaml_calls(names: set[str]) -> set[str]:
    found: set[str] = set()
    for path in sorted((ROOT / "src" / "aew").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in names
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "yaml"):
                found.add(path.relative_to(ROOT).as_posix())
    return found


def test_every_place_the_product_composes_yaml_is_bounded_or_reads_only_aews_own_files():
    found = yaml_calls(COMPOSERS)
    assert found == set(COMPOSING), (sorted(found - set(COMPOSING)), sorted(set(COMPOSING) - found))


def test_every_place_the_product_writes_yaml_is_bounded():
    found = yaml_calls(DUMPERS)
    assert found == set(WRITING), (sorted(found - set(WRITING)), sorted(set(WRITING) - found))


def test_only_the_control_stores_own_reads_skip_the_depth_pass():
    found: set[str] = set()
    for path in sorted((ROOT / "src" / "aew").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name) and node.id == "load_own_yaml" and isinstance(node.ctx, ast.Load):
                found.add(path.relative_to(ROOT).as_posix())
    assert found == set(OWN_YAML), (sorted(found - set(OWN_YAML)), sorted(set(OWN_YAML) - found))
