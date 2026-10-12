"""The configuration read's change note against the projection's real output (register F46.1, slice F1b; the note's
§6). The real output is the owner: Appendix A, merged into the accepted 0.1.3, must validate every index and execution
projection the engine emits over a corpus, with every object closed, and every property it defines must be emitted.

The corpus is F1a's own (imported, never restated): every row of the proposal's §4.2 state table, the hostile
documents, the bounded and the oversized policies, and documents built for the withheld `@i` keys, the identity
errors, the document inventory's extra and shared entries and a drifted manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import run_aew
from dashboard_contract import CONFIG_NOTE_REL, config_base_contract, note_text, proposed
from test_configuration_hostile import CASES, SHARED
from test_configuration_projection import (
    POLICY,
    ROWS,
    SECRET,
    _append,
    _with_manifest_policy,
    aew,
    bounded_policy,
    configured,
    new_engine,
    only_profiles,
    oversized_policy,
    pin_now,
    row_engine,
)

from aew.dashboard.contract import Contract
from aew.engine import configuration as C
from aew.engine.api import Engine

ENVELOPE = {"project_id": "cfg", "control_revision": "0", "generated_at": "2026-10-12T00:00:00Z"}


@pytest.fixture(scope="module")
def contract() -> Contract:
    merged = proposed(note_text(rel=CONFIG_NOTE_REL), config_base_contract())
    return Contract(raw=yaml.safe_dump(merged, sort_keys=False).encode("utf-8"))


def projections(e: Engine) -> list[tuple[str, dict[str, Any]]]:
    fresh = Engine.discover(e.repo_root)
    env = {"VENDOR_API_KEY": "x"}
    return [("ConfigurationIndex", fresh.configuration()),
            *[("ExecutionConfiguration", fresh.configuration("execution", observed_in=site, env=env))
              for site in C.OBSERVED_CAPTIONS]]


def problems(contract: Contract, e: Engine) -> list[str]:
    out = []
    for name, data in projections(e):
        out += [f"{name}: {p}" for p in contract.violations(name, data)]
        envelope = {"ConfigurationIndex": "ConfigurationIndexResponse",
                    "ExecutionConfiguration": "ConfigurationExecutionResponse"}[name]
        out += [f"{envelope}: {p}" for p in contract.violations(envelope, {"schema_version": "0.1.4", **ENVELOPE,
                                                                           "data": data})]
    return out


# Documents beyond F1a's state rows and hostile corpus, each exercising a part of the appendix's shapes.
def withheld_keys(e: Engine) -> None:
    configured(e, POLICY | {"profiles": POLICY["profiles"] | {SECRET: {"model": "vendor/m"}},
                            "routing": POLICY["routing"] | {"cards": {SECRET: SECRET, "researcher": "review"}}})


def identity_errors(e: Engine) -> None:
    configured(e, only_profiles({"bare": {"model": "no-provider"}, "conflict": {"provider": "a", "model": "b/m"},
                                 "shown": {"model": "vendor/m", "harness": "site-harness"}}))


def inventory(e: Engine) -> None:
    configured(e)
    (aew(e) / "policy/pricing.yaml").write_text("schema: synthetic\n", encoding="utf-8", newline="\n")
    _with_manifest_policy(e, pricing="policy/pricing.yaml", alias="policy/gates.yaml", **{SECRET: "policy/x.yaml"})
    pin_now(e)
    _append(aew(e) / "policy/gates.yaml")


def manifest_drifted(e: Engine) -> None:
    configured(e)
    _append(aew(e) / "project.yaml")


def many_documents(e: Engine) -> None:
    configured(e)
    _with_manifest_policy(e, **{f"extra{i:02d}": "policy/gates.yaml" for i in range(20)})
    pin_now(e)


EXTRA = {"withheld_keys": withheld_keys, "identity_errors": identity_errors, "inventory": inventory,
         "manifest_drifted": manifest_drifted, "many_documents": many_documents,
         "bounded": lambda e: configured(e, bounded_policy()), "oversized": lambda e: configured(e, oversized_policy())}


def build(tmp_path: Path, kind: str, name: str) -> Engine:
    e = new_engine(tmp_path)
    if kind == "row":
        return row_engine(e, name)
    if kind == "extra":
        EXTRA[name](e)
        return e
    if name in SHARED:
        _with_manifest_policy(e, zz_alias="policy/execution.yaml")
    policy = CASES[name]
    if isinstance(policy, bytes):
        (aew(e) / "policy/execution.yaml").write_bytes(policy)
        pin_now(e)
    else:
        configured(e, policy)
    return e


CORPUS = ([("row", n) for n in sorted(ROWS)] + [("hostile", n) for n in sorted(CASES)]
          + [("extra", n) for n in sorted(EXTRA)])


@pytest.mark.parametrize("kind,name", CORPUS, ids=[f"{k}-{n}" for k, n in CORPUS])
def test_the_projection_validates_against_the_appendix(contract, tmp_path, kind, name):
    """Every index and execution projection (from the CLI's and the dashboard server's observation site) is valid
    under Appendix A merged into 0.1.3, envelope included."""
    assert problems(contract, build(tmp_path, kind, name)) == []


CLI_CASES = [("row", "adopted"), ("row", "manifest_drifted"), ("row", "no_pins_invalid"), ("row", "deleted"),
             ("extra", "withheld_keys"), ("extra", "inventory"), ("hostile", "yaml_mark")]


@pytest.mark.parametrize("kind,name", CLI_CASES, ids=[f"{k}-{n}" for k, n in CLI_CASES])
def test_the_cli_json_validates_against_the_appendix(contract, tmp_path, kind, name):
    """What `aew settings show [execution] --json` prints, from its own process, validates as the routes' data."""
    e = build(tmp_path, kind, name)
    for args, schema_name in ((["settings", "show", "--json"], "ConfigurationIndex"),
                              (["settings", "show", "execution", "--json"], "ExecutionConfiguration")):
        res = run_aew("-C", str(e.repo_root), *args)
        assert res.returncode == 0, res.stderr
        assert contract.violations(schema_name, res.json) == [], (args, contract.violations(schema_name, res.json))


def schema_properties(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            found |= set(node["properties"])
        for value in node.values():
            found |= schema_properties(value)
    elif isinstance(node, list):
        for value in node:
            found |= schema_properties(value)
    return found


def emitted_keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in emitted_keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in emitted_keys(v)}
    return set()


def test_every_property_the_appendix_defines_is_emitted(contract, tmp_path):
    """The appendix promises nothing the projection does not write: every property name its schemas define appears in
    the projection's output over a corpus that reaches each part (by name: a name used in two places is counted once,
    the limit of this check; the per-object closure is the validation test's)."""
    base = config_base_contract()
    merged = proposed(note_text(rel=CONFIG_NOTE_REL), base)
    added = {n: s for n, s in merged["components"]["schemas"].items() if n not in base["components"]["schemas"]}
    defined = schema_properties(added) - {"schema_version", "project_id", "control_revision", "generated_at", "data"}
    seen: set[str] = set()
    for i, name in enumerate(["identity_errors", "withheld_keys", "inventory", "oversized"]):
        seen |= {k for _, data in projections(build(tmp_path / str(i), "extra", name)) for k in emitted_keys(data)}
    for i, row in enumerate(["no_pins_invalid", "edited"]):
        seen |= {k for _, data in projections(build(tmp_path / f"r{i}", "row", row)) for k in emitted_keys(data)}
    yaml_case = build(tmp_path / "y", "hostile", "yaml_mark")
    seen |= {k for _, data in projections(yaml_case) for k in emitted_keys(data)}
    assert sorted(defined - seen) == [], json.dumps(sorted(defined - seen))


# The optional properties of FieldValue (the note's §5.1): each is present in some of the four cases, never in all.
OPTIONAL = {"FieldValue": {"value", "withheld", "effective", "effective_source", "allowed", "description"}}


def object_keys(schemas: dict[str, Any], node: Any, instance: Any, where: str, acc: dict[str, set[str]]) -> None:
    """Record, per object schema (a named one by its name, an inline one by its path), the intersection of the key sets
    of every emitted instance: the keys that were present in all of them."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[1]
        return object_keys(schemas, schemas[name], instance, name, acc)
    if "anyOf" in node:
        kind = {dict: "object", list: "array", str: "string", type(None): "null", bool: "boolean"}.get(type(instance))
        for i, branch in enumerate(node["anyOf"]):
            resolved = schemas[branch["$ref"].rsplit("/", 1)[1]] if "$ref" in branch else branch
            if kind == resolved.get("type") or (kind == "object" and "properties" in resolved):
                return object_keys(schemas, branch, instance, f"{where}/anyOf{i}", acc)
        return None
    if isinstance(instance, dict) and "properties" in node:
        acc[where] = acc[where] & set(instance) if where in acc else set(instance)
        for key, value in instance.items():
            if key in node["properties"]:
                object_keys(schemas, node["properties"][key], value, f"{where}/{key}", acc)
    elif isinstance(instance, list) and "items" in node:
        for value in instance:
            object_keys(schemas, node["items"], value, f"{where}[]", acc)
    return None


def required_gaps(doc: dict[str, Any], instances: list[tuple[str, Any]]) -> list[str]:
    """Every object whose emitted instances all carry a key its `required` lacks (and that is not declared optional)."""
    schemas = doc["components"]["schemas"]
    acc: dict[str, set[str]] = {}
    for name, data in instances:
        object_keys(schemas, schemas[name], data, name, acc)
    out = []
    for where, always in sorted(acc.items()):
        node = schemas[where] if where in schemas else None
        required = set(node["required"]) if node else None
        if required is None:  # an inline object: find it by walking its path
            required = set(inline(schemas, where).get("required", []))
        missing = always - required - OPTIONAL.get(where, set())
        if missing:
            out.append(f"{where}: {sorted(missing)}")
    return out


def inline(schemas: dict[str, Any], where: str) -> dict[str, Any]:
    head, *rest = where.split("/")
    node = schemas[head]
    for step in rest:
        while "$ref" in node:
            node = schemas[node["$ref"].rsplit("/", 1)[1]]
        if step.endswith("[]"):
            node = node["properties"][step[:-2]]["items"]
        elif step.startswith("anyOf"):
            node = node["anyOf"][int(step[5:])]
        else:
            node = node["properties"][step]
    while "$ref" in node:
        node = schemas[node["$ref"].rsplit("/", 1)[1]]
    return node


@pytest.fixture(scope="module")
def emitted(tmp_path_factory) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for i, (kind, name) in enumerate(CORPUS):
        out += projections(build(tmp_path_factory.mktemp(f"c{i}"), kind, name))
    return out


def test_every_key_emitted_in_every_instance_is_required(contract, emitted):
    """The projection never omits a key its object has in every instance, so Appendix A must require it: a `required`
    list that has lost a name would let the page treat an always-sent field as optional. The optional FieldValue set
    is stated once, above; the check is derived from the output over the whole corpus."""
    assert len(emitted) >= 2 * len(CORPUS)
    assert required_gaps(contract.document, emitted) == []


def test_the_required_check_finds_a_dropped_name(contract, emitted):
    doc = json.loads(json.dumps(contract.document))
    schemas = doc["components"]["schemas"]
    schemas["FieldValue"]["required"] = [r for r in schemas["FieldValue"]["required"] if r != "editable"]
    profile = schemas["ExecutionProfile"]
    profile["required"] = [r for r in profile["required"] if r != "connection_id"]
    gaps = required_gaps(doc, emitted)
    assert any(g.startswith("FieldValue") and "editable" in g for g in gaps), gaps
    assert any(g.startswith("ExecutionProfile") and "connection_id" in g for g in gaps), gaps


def test_the_paths_and_routes_fit_their_bounds(contract, emitted):
    """The contract-only bounds (the note's §5.4): every emitted locator is within `ConfigurationPath`'s 256 and every
    `routed_by` entry within 256, over the whole corpus."""
    schemas = contract.document["components"]["schemas"]
    path_max = schemas["ConfigurationPath"]["maxLength"]
    route_max = schemas["ExecutionProfile"]["properties"]["routed_by"]["items"]["maxLength"]
    paths: list[str] = []
    routes: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("path", "field_path") and isinstance(value, str):
                    paths.append(value)
                elif key == "routed_by":
                    routes.extend(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for _name, data in emitted:
        walk(data)
    assert paths and routes
    assert max(map(len, paths)) <= path_max and max(map(len, routes)) <= route_max
