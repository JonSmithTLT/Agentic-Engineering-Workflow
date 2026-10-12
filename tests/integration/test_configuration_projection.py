"""The configuration read projection, engine and CLI (register F46.1; the F46.1 proposal §3, §4, §7 and §9).

`Engine.configuration` projects the execution policy field by field, and `aew settings show` serves it. These tests
are the proposal's §9 tests that belong to slice F1a; the HTTP halves (the served routes, the adopted 0.1.4 contract,
the ETag) belong to F1c. Every credential-shaped value is synthetic, built at run time from the patterns' own home and
checked against the pattern it claims to match.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import clean_env, policy_pins, run_aew
from credential_shapes import synthetic
from invariants import load_control

from aew.engine import configuration as C
from aew.engine import steering as S
from aew.engine.api import Engine
from aew.engine.base import POLICY_PINS
from aew.engine.store import serialize_control
from aew.errors import ValidationFailed
from aew.harness import contract as K
from aew.harness import registry
from aew.policy import config_paths as P
from aew.policy import execution as X
from aew.schemas import schema
from aew.util import dump_yaml, load_yaml, sha256_file

NO_WINDOW: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
SRC = Path(C.__file__).resolve().parents[1]

POLICY: dict[str, Any] = {
    "schema": "aew/execution/v1", "configured": True, "harness": "opencode", "description": "the fixture's routing",
    "profiles": {
        "standard": {"model": "vendor/model-standard", "effort": "high", "deadline_s": 600,
                     "description": "the default profile"},
        "review": {"provider": "other", "model": "model-review", "effort": "max", "max_steps": 30},
        "light": {"model": "vendor/model-light", "harness": "site-harness"},
    },
    "routing": {"default": "standard", "archetypes": {"reviewer": "review"}, "classes": {"0": "light"},
                "cards": {"researcher": "review"}},
    "provider_env": ["VENDOR_API_KEY", "OTHER_API_KEY"],
    "steering": {"mode": "walk", "envelope": {"max_auto_actions": 20}},
    "containment": {"mode": "allow_weaker", "writable": ["/srv/cache"], "hide": []},
    "maps": {"pack_slices": "structural"},
    "notify": {"command": ["notify-tool", "--quiet"], "timeout_s": 5},
}


SECRET = "sk-" + "synthetic-" + "0123456789abcdef"  # synthetic only: matches the strict sk- pattern
assert K.credential_shaped(SECRET)


# ------------------------------------------------------------------------------------------------- the fixture


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, **NO_WINDOW)


def new_engine(path: Path) -> Engine:
    """An initialized project (with one authority candidate, docs/adr), its git run with no window."""
    repo = path / "repo"
    (repo / "docs/adr").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "AEW Test")
    git(repo, "config", "user.email", "aew-test@invalid")
    git(repo, "config", "core.autocrlf", "false")
    (repo / "README.md").write_text("# fixture\n", encoding="utf-8", newline="\n")
    (repo / "docs/adr/0001-use-aew.md").write_text("# ADR 1\n", encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")
    return Engine.initialize(repo, project_id="cfg")


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    return new_engine(tmp_path)


def aew(e: Engine) -> Path:
    return e.aew_root


def write_policy(e: Engine, policy: Any, rel: str = X.REL_PATH) -> None:
    text = policy if isinstance(policy, str) else dump_yaml(policy)
    (aew(e) / rel).write_text(text, encoding="utf-8", newline="\n")


def set_control(e: Engine, **changes: Any) -> None:
    """Fixture setup only: change the committed control state directly (as `Project.pin_policy` does)."""
    state = load_control(e.repo_root)
    for key, value in changes.items():
        if value is ...:
            state.pop(key, None)
        else:
            state[key] = value
    (aew(e) / "state/control.yaml").write_bytes(serialize_control(state))


def pin_now(e: Engine) -> None:
    """Pin the manifest and every policy file as they are now."""
    set_control(e, manifest_sha256=sha256_file(aew(e) / "project.yaml"), **{POLICY_PINS: policy_pins(e.repo_root)})


def configured(e: Engine, policy: Any = None) -> Engine:
    write_policy(e, POLICY if policy is None else policy)
    pin_now(e)
    return e


def index(e: Engine) -> dict[str, Any]:
    return Engine.discover(e.repo_root).configuration()


def execution(e: Engine, **kwargs: Any) -> dict[str, Any]:
    return Engine.discover(e.repo_root).configuration("execution", **kwargs)


def doc(e: Engine, name: str) -> dict[str, Any]:
    return next(d for d in index(e)["documents"] if d["document"] == name)


def field_values(node: Any) -> list[dict[str, Any]]:
    out = []
    if isinstance(node, dict):
        if {"path", "state", "edit", "editable"} <= set(node):
            out.append(node)
        for v in node.values():
            out += field_values(v)
    elif isinstance(node, list):
        for v in node:
            out += field_values(v)
    return out


def fieldvalue_problems(fv: dict[str, Any]) -> list[str]:
    """§3.1's table (D2): one withheld representation. The F1c contract test validates the same against 0.1.4."""
    out = [f"missing {k}" for k in ("path", "state", "class", "edit", "editable") if k not in fv]
    state, withheld = fv.get("state"), fv.get("withheld")
    if state == "SET" and withheld and "value" in fv:
        out.append("a withheld SET carries a value")
    if state == "SET" and not withheld and ("value" not in fv or fv["value"] is None):
        out.append("a shown SET has no value")
    if state == "NULL" and (fv.get("value", ...) is not None or withheld):
        out.append("NULL is value null and never withheld")
    if state == "ABSENT" and ("value" in fv or withheld):
        out.append("ABSENT has no value and is never withheld")
    return out


def only_profiles(profiles: dict[str, Any]) -> dict[str, Any]:
    """POLICY with these profiles, routed by default to the first and by nothing else (so it stays valid)."""
    return POLICY | {"profiles": profiles, "routing": {"default": next(iter(profiles))}}


def by_name(projection: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    return {p["name"]: p for p in projection["profiles"]}


def all_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# ------------------------------------------------------------------------------------------------- differential


def test_adopted_projection_equals_execution_policy(engine):
    """m7: in ADOPTED and UNPINNED, every projected value equals what `Engine.execution_policy()` reads."""
    e = configured(engine)
    for setup in ("adopted", "unpinned"):
        if setup == "unpinned":
            set_control(e, **{POLICY_PINS: ...})
        policy, _sha = Engine.discover(e.repo_root).execution_policy()
        out = execution(e)
        assert out["document"]["state"] == {"adopted": C.ADOPTED, "unpinned": C.UNPINNED}[setup]
        shown = [fv for fv in field_values(out) if "value" in fv and fv["state"] == "SET"]
        assert len(shown) >= 20
        for fv in shown:
            location = P.resolve(policy, fv["path"])
            node = policy
            for step in location:
                node = node[step]
            assert fv["value"] == (len(node) if isinstance(node, list) else node), fv
        assert [p["name"] for p in out["profiles"]] == sorted(policy["profiles"])


def test_projection_routing_equals_engine_route(engine):
    """Every `routed_by` entry is what `aew.policy.execution.route` selects for that card, class or archetype, and
    the resolution order is route's own precedence."""
    e = configured(engine)
    policy = Engine.discover(e.repo_root).execution_policy()[0]
    out = execution(e)
    for row in out["profiles"]:
        for entry in row["routed_by"]:
            kind, _, key = entry.partition(":")
            got = X.route(policy, archetype=key if kind == "archetype" else "no-such-archetype",
                          card_id=key if kind == "card" else None,
                          risk_class=int(key) if kind == "class" else None)
            assert got == (row["name"], entry), (row["name"], entry)
    everything = {"routing": {"default": "standard", "cards": {"c": "light"}, "classes": {"1": "review"},
                              "archetypes": {"a": "standard"}}}
    choices = [X.route(everything, archetype="a", card_id="c", risk_class=1)[1],
               X.route(everything, archetype="a", card_id=None, risk_class=1)[1],
               X.route(everything, archetype="a", card_id=None, risk_class=None)[1],
               X.route(everything, archetype="z", card_id=None, risk_class=None)[1]]
    assert [c.partition(":")[0] for c in choices] == out["routing"]["resolution_order"]


def test_projection_identity_equals_pin(engine):
    """Each profile's identity is the pair a dispatch pins (`execution.resolve` with the adapter's identity)."""
    e = configured(engine)
    policy, sha = Engine.discover(e.repo_root).execution_policy()
    for name, row in by_name(execution(e)).items():
        pin = X.resolve(policy, sha, archetype="implementer", card_id=None, risk_class=None,
                        request={"profile": name}, identity=registry.model_identity)
        assert pin is not None and row["identity"] is not None
        assert (row["identity"]["provider"], row["identity"]["model"]) == (pin["provider"], pin["model"]), name


def test_config_digest_is_one_function(engine, monkeypatch):
    """m7: one `def config_digest` in src/, and the projection calls that module function (a second
    implementation, or an inline hash, fails this)."""
    defs = [path for path in SRC.rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef) and node.name == "config_digest"]
    assert defs == [Path(C.__file__).resolve()]
    e = configured(engine)
    calls = []
    monkeypatch.setattr(C, "config_digest", lambda *a: calls.append(a) or f"sha256:{len(calls):064d}")
    out = index(e)
    assert [d["digest"] for d in out["documents"]] == [f"sha256:{i:064d}" for i in range(1, len(calls) + 1)]
    assert calls[0][1] == "project" and {c[1] for c in calls[1:]} == {"guardrails", "checks", "gates", "execution"}


def test_digest_ignores_unrelated_commits(engine):
    """A Lead commit moves the control revision; no document's digest moves (the ETag half is F1c's)."""
    e = configured(engine)
    before = index(e)
    token = e.lead_acquire(expect_rev=0)["token"]
    e.checkpoint(token=token, expect_rev=e.store.read_committed()["revision"], note="unrelated")
    assert e.store.read_committed()["revision"] >= 2
    after = index(e)
    assert [d["digest"] for d in after["documents"]] == [d["digest"] for d in before["documents"]]


# --------------------------------------------------------------------------------------------- states and digests


def _drop(e: Engine) -> None:
    (aew(e) / X.REL_PATH).unlink()


def _append(path: Path, text: str = "# edited\n") -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")


INVALID_POLICY = {"schema": "aew/execution/v1", "configured": True, "profiles": {}, "routing": {"default": None}}

# §4.2's table: (setup, state, in_force). Each starts from an initialized project with POLICY written, unpinned.
ROWS: dict[str, tuple[Any, str, bool]] = {
    "manifest_drifted": (lambda e: (pin_now(e), _append(aew(e) / "project.yaml")),
                         C.MANIFEST_DRIFTED, False),
    "no_pins_absent": (lambda e: (_drop(e), set_control(e, **{POLICY_PINS: ...})), C.ABSENT, True),
    "no_pins_valid": (lambda e: set_control(e, **{POLICY_PINS: ...}), C.UNPINNED, True),
    "no_pins_invalid": (lambda e: (write_policy(e, INVALID_POLICY), set_control(e, **{POLICY_PINS: ...})),
                        C.INVALID, False),
    "pinned_absent_absent": (lambda e: (_drop(e), pin_now(e)), C.ABSENT, True),
    "pinned_absent_created": (lambda e: (_drop(e), pin_now(e), write_policy(e, POLICY)), C.DRIFTED, False),
    "deleted": (lambda e: (pin_now(e), _drop(e)), C.DRIFTED, False),
    "edited": (lambda e: (pin_now(e), write_policy(e, POLICY | {"description": "edited by hand"})), C.DRIFTED, False),
    "adopted": (pin_now, C.ADOPTED, True),
    "tightened": (lambda e: (write_policy(e, INVALID_POLICY), pin_now(e)), C.INVALID, False),
    "not_in_pins": (lambda e: (pin_now(e), set_control(e, **{POLICY_PINS: {
        k: v for k, v in policy_pins(e.repo_root).items() if k != X.REL_PATH}})), C.DRIFTED, False),
}


MATCHES_ADOPTED = {"pinned_absent_absent", "adopted", "tightened"}  # the truth column of on_disk_matches_adopted


def row_engine(engine: Engine, row: str) -> Engine:
    write_policy(engine, POLICY)
    set_control(engine, **{POLICY_PINS: ...})
    ROWS[row][0](engine)
    return engine


@pytest.mark.parametrize("row", sorted(ROWS))
def test_document_states(engine, row):
    """m2: every row of §4.2's table, its `in_force`, and the values shown in that state."""
    e = row_engine(engine, row)
    _setup, state, in_force = ROWS[row]
    entry = doc(e, "execution")
    out = execution(e)
    assert (entry["state"], entry["in_force"]) == (state, in_force)
    assert (out["document"]["state"], out["document"]["in_force"], out["document"]["digest"]) == (
        state, in_force, entry["digest"])
    shows_values = row in ("no_pins_valid", "adopted", "pinned_absent_created", "edited", "not_in_pins")
    assert bool(out["profiles"]) is shows_values, row
    assert bool(out["document"]["violations"]) is (row in ("no_pins_invalid", "tightened")), row
    # The on-disk bytes are the adopted ones: a real pin equal to the file, or a pinned absence of an absent file.
    assert out["document"]["on_disk_matches_adopted"] is (row in MATCHES_ADOPTED), row
    others = [d for d in index(e)["documents"] if d["document"] not in ("execution", "project")]
    if row == "manifest_drifted":
        assert index(e)["manifest"]["state"] == C.DRIFTED and doc(e, "project")["state"] == C.DRIFTED
        assert {d["state"] for d in others} == {C.MANIFEST_DRIFTED}
        assert {d["same_file_as"] for d in index(e)["documents"]} == {None}
    for fv in field_values(out):
        assert fieldvalue_problems(fv) == [], fv


def test_digest_distinct_per_input_case(tmp_path):
    """m2: two rows share a digest only when their path, pin and disk inputs are equal."""
    seen: dict[str, tuple[Any, ...]] = {}
    for i, row in enumerate(sorted(ROWS)):
        e = row_engine(new_engine(tmp_path / str(i)), row)
        k = Engine.discover(e.repo_root)._k
        d = C._execution_document(C.documents(k, C.read_committed(k)))
        inputs = (d.rel, d.adopted, d.on_disk)
        assert seen.setdefault(d.digest, inputs) == inputs, (row, inputs, seen[d.digest])
    assert len(seen) >= 9


def lead(e: Engine) -> tuple[str, Any]:
    token = e.lead_acquire(expect_rev=e.store.read_committed()["revision"])["token"]
    return token, lambda: e.store.read_committed()["revision"]


def test_digest_ignores_authority_decision(engine):
    """m1: an `authority_accept` rewrites and re-pins the manifest; the execution digest does not move."""
    e = configured(engine)
    before = {d["document"]: d["digest"] for d in index(e)["documents"]}
    token, rev = lead(e)
    candidate = e.authority_list()["candidates"][0]["id"]
    e.authority_accept(token=token, expect_rev=rev(), candidate_id=candidate, klass="decisions")
    after = {d["document"]: d["digest"] for d in index(e)["documents"]}
    assert after["execution"] == before["execution"] and doc(e, "execution")["state"] == C.ADOPTED
    assert after["project"] != before["project"]


def test_digest_changes_on_adopt_on_hand_edit_and_per_document(engine):
    e = configured(engine)
    d0 = {d["document"]: d["digest"] for d in index(e)["documents"]}
    write_policy(e, POLICY | {"description": "edited by hand"})
    d1 = {d["document"]: d["digest"] for d in index(e)["documents"]}
    assert d1["execution"] != d0["execution"]  # on a hand edit
    assert {k: v for k, v in d1.items() if k != "execution"} == {k: v for k, v in d0.items() if k != "execution"}
    token, rev = lead(e)
    e.manifest_adopt(token=token, expect_rev=rev(), reason="reviewed", authorization={"authorized_by": "operator-tty"})
    d2 = {d["document"]: d["digest"] for d in index(e)["documents"]}
    assert d2["execution"] not in (d0["execution"], d1["execution"]) and doc(e, "execution")["state"] == C.ADOPTED
    _append(aew(e) / "policy/gates.yaml")
    d3 = {d["document"]: d["digest"] for d in index(e)["documents"]}
    assert d3["gates"] != d2["gates"] and d3["execution"] == d2["execution"]  # per document


# ------------------------------------------------------------------------------- the read side of F46.2's conditions


def test_inventory_names_each_drifted_document(engine):
    """n3: with `gates` drifted, the inventory names it by logical name, with no path, and no document can be
    written."""
    e = configured(engine)
    _append(aew(e) / "policy/gates.yaml")
    out = index(e)
    assert doc(e, "gates")["state"] == C.DRIFTED and doc(e, "execution")["state"] == C.ADOPTED
    assert "policy/gates.yaml" not in all_text(out) and "gates.yaml" not in all_text(out)
    for d in out["documents"]:
        assert d["write"] == C.capability(C.UNSUPPORTED, "AWAITS_F46_2")


def _with_manifest_policy(e: Engine, **entries: str) -> None:
    manifest = load_yaml((aew(e) / "project.yaml").read_text(encoding="utf-8"))
    manifest["policy"].update(entries)
    (aew(e) / "project.yaml").write_text(dump_yaml(manifest), encoding="utf-8", newline="\n")


PRICES = ("schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\nsource: \"synthetic\"\n"
          "prices:\n  p/m: {input: 1.0}\n")


def test_inventory_lists_extra_policy_document(engine):
    """R1: a manifest `pricing` entry, hand-edited after adoption, is DRIFTED by logical name with its own digest."""
    e = configured(engine)
    (aew(e) / "policy/pricing.yaml").write_text(PRICES, encoding="utf-8", newline="\n")
    _with_manifest_policy(e, pricing="policy/pricing.yaml")
    pin_now(e)
    adopted = doc(e, "pricing")
    assert adopted["state"] == C.ADOPTED
    (aew(e) / "policy/pricing.yaml").write_text(PRICES.replace("1.0", "2.0"), encoding="utf-8", newline="\n")
    pricing = doc(e, "pricing")
    assert pricing["state"] == C.DRIFTED and pricing["in_force"] is False
    assert pricing["supported"] == C.capability(C.UNSUPPORTED, "AWAITS_LATER_F46")
    assert pricing["digest"] != adopted["digest"] and "pricing.yaml" not in all_text(index(e))
    assert doc(e, "execution")["state"] == C.ADOPTED


def test_inventory_keys_sharing_a_file(engine):
    """T1: two keys naming one file share state and `in_force`; the later names the earlier's index."""
    e = configured(engine)
    _with_manifest_policy(e, extra="policy/gates.yaml")
    pin_now(e)
    gates, extra = doc(e, "gates"), doc(e, "extra")
    assert (gates["state"], gates["in_force"]) == (extra["state"], extra["in_force"]) == (C.ADOPTED, True)
    assert gates["same_file_as"] is None and extra["same_file_as"] == gates["index"] < extra["index"]
    _append(aew(e) / "policy/gates.yaml")
    assert doc(e, "gates")["state"] == doc(e, "extra")["state"] == C.DRIFTED
    names = [d["document"] for d in index(e)["documents"]]
    assert names[0] == "project" and names[-1] == "extra" and "execution" in names  # U1: the manifest's key order


@pytest.mark.parametrize("profiles", [
    {"standard": {"model": "vendor/m", "max_steps": "many"}},  # schema-invalid under `execution`, valid YAML
    {"standard": {"effort": "high"}},  # a profile without `model`
    ["standard"],  # profiles as a list
], ids=["schema_invalid", "profile_without_model", "profiles_as_list"])
def test_a_file_shared_by_two_keys_is_valid_only_under_every_name(engine, profiles):
    """R1: the execution file, also named by a later manifest key, is valid only if it validates as the execution
    policy too: pinned execution-invalid content is INVALID on both entries, never in force, its values not shown,
    and the read never raises."""
    _with_manifest_policy(engine, zz_alias=X.REL_PATH)  # a later key naming the execution policy's file
    e = configured(engine, only_profiles({"standard": {"model": "vendor/m"}}) | {"profiles": profiles})
    for name in ("execution", "zz_alias"):
        assert (doc(e, name)["state"], doc(e, name)["in_force"]) == (C.INVALID, False), name
    out = execution(e)
    assert out["document"]["state"] == C.INVALID and out["document"]["violations"] and out["profiles"] == []
    res = run_aew("-C", str(e.repo_root), "settings", "show", "execution", "--json")
    assert res.returncode == 0 and res.json["document"]["violations"], res.stderr


# ------------------------------------------------------------------------------------------------- secrets (§7)


def cli_outputs(e: Engine, env: dict[str, str] | None = None) -> str:
    out = []
    for args in (["settings", "show"], ["settings", "show", "--json"], ["settings", "show", "execution"],
                 ["settings", "show", "execution", "--json"]):
        res = run_aew("-C", str(e.repo_root), *args, env=env)
        assert res.returncode == 0, res.stderr
        out.append(res.stdout + res.stderr)
    return "\n".join(out)


def test_no_secret_values_anywhere(engine):
    """M1: a synthetic provider-shaped key in every slot where a typed value can reach output appears in none of the
    CLI's output, nor any absolute path. (The HTTP body and the server log are F1c's half.)"""
    e = engine
    slots = {
        "provider_env": POLICY | {"provider_env": ["VENDOR_API_KEY", f"bad {SECRET}"]},
        "model_whitespace": POLICY | {"profiles": {"standard": {"model": f"vendor/m {SECRET}"}}},
        "route_key": POLICY | {"routing": {"default": "standard", "cards": {SECRET: "standard"}}},
        "route_target": POLICY | {"routing": {"default": "standard", "cards": {"researcher": SECRET}}},
        "profile_target_name": POLICY | {"routing": {"default": SECRET}},
        "yaml_syntax": f"profiles: [\n  {SECRET}: x\n  - b\n",
        "type": POLICY | {"configured": SECRET},
        "pattern": POLICY | {"profiles": {"standard": {"model": "vendor/m", "effort": f"x {SECRET}"}}},
    }
    for slot, policy in slots.items():
        configured(e, policy)
        outputs = cli_outputs(e)
        assert SECRET not in outputs, slot
        assert str(e.repo_root) not in outputs and str(e.repo_root).replace("\\", "/") not in outputs, slot
        assert str(e.repo_root.parent) not in outputs, slot


def test_credential_prefix_withheld_everywhere(engine):
    """n1, p2, p5: a value matching each strict pattern, in every field of rule 8's scope the schema admits it in, is
    withheld as `credential_shaped` or in the index form, and appears nowhere in the projection."""
    name_shape = re.compile(schema("execution")["$defs"]["name"]["pattern"])
    var_shape = re.compile(schema("execution")["properties"]["provider_env"]["items"]["pattern"])
    named_patterns = 0
    for pattern in K.CREDENTIAL_PATTERNS:
        value = synthetic(pattern)
        # The same shape in lower case where the pattern admits it: a valid document admits it as a profile name.
        name = value.lower() if re.fullmatch(pattern, value.lower()) and name_shape.search(value.lower()) else None
        name_ok = name is not None
        named_patterns += name_ok
        var_ok = var_shape.search(value) is not None  # admitted as a provider_env name
        profiles: dict[str, Any] = {
            "standard": {"model": "vendor/model-a", "description": f"key {value}"},
            "by-model": {"model": f"vendor/{value}"},
            "by-provider": {"provider": value, "model": "model-b"},
            "by-harness": {"model": "vendor/model-c", "harness": value},
            "by-effort": {"model": "vendor/model-d", "effort": value},
        }
        if name:
            profiles[name] = {"model": "vendor/model-e"}
        policy = POLICY | {
            "description": f"top {value}", "profiles": profiles,
            "routing": {"default": "standard", "cards": {value: name or "standard"},
                        "archetypes": {value: "standard"}},
            "provider_env": ["VENDOR_API_KEY", *([value] if var_ok else [])],
        }
        out = execution(configured(engine, policy))
        assert out["document"]["state"] == C.ADOPTED, (pattern, out["document"]["violations"])
        assert value not in all_text(out) and (name is None or name not in all_text(out)), pattern
        rows = {p["index"]: p for p in out["profiles"]}
        keys = list(profiles)
        assert out["description"]["withheld"] == C.CREDENTIAL_SHAPED
        assert rows[0]["fields"]["description"]["withheld"] == C.CREDENTIAL_SHAPED
        for key, field in (("by-model", "model"), ("by-provider", "provider"), ("by-harness", "harness")):
            row = rows[keys.index(key)]
            assert row["fields"][field]["withheld"] == C.CREDENTIAL_SHAPED, (pattern, key)
            assert row["identity"] is None and row["connection_id"] is None
            assert row["identity_error"]["code"] == C.FIELD_WITHHELD
            assert row["identity_error"]["withheld_reason"] == C.CREDENTIAL_SHAPED
        assert rows[keys.index("by-effort")]["fields"]["effort"]["withheld"] == C.CREDENTIAL_SHAPED
        if name:
            named = rows[keys.index(name)]
            assert named["name"] is None and all("/@" in fv["path"] for fv in field_values(named["fields"]))
            assert out["routing"]["cards"]["entries"][0]["profile"]["withheld"] == C.CREDENTIAL_SHAPED
        assert out["routing"]["cards"]["entries"][0]["key"] is None
        assert out["routing"]["archetypes"]["entries"][0]["key"] is None
        assert "card:@0" in rows[keys.index(name) if name else 0]["routed_by"]
        assert "archetype:@0" in rows[0]["routed_by"]
        if var_ok:
            assert out["provider_env"]["entries"][1] == {"index": 1, "name": None, "valid_name": True}
            assert out["observed"]["provider_env"][1]["name"] is None
        assert {(c["harness"], c["provider"]) for c in out["connections"]} == {("opencode", "vendor")}
        # as an extra key (an INVALID document's violation)
        invalid = execution(configured(engine, POLICY | {value: 1}))
        assert value not in all_text(invalid)
        assert {v["extra_key"] for v in invalid["document"]["violations"]} == {f"@{len(POLICY)}"}
    assert named_patterns >= 3  # the profile-name slot is exercised (sk-, glpat-, xox in lower case)


def test_withheld_profile_key_does_not_escape(engine):
    """D3: a credential-shaped profile key with a nested violation is `@i` in every path, and appears in no output."""
    e = configured(engine, only_profiles({"standard": {"model": "vendor/m"},
                                          SECRET: {"model": "vendor/m", "max_steps": "many"}}))
    out = execution(e)
    assert out["document"]["state"] == C.INVALID
    assert [v["path"] for v in out["document"]["violations"]] == ["/profiles/@1/max_steps"]
    assert SECRET not in all_text(out) and SECRET not in all_text(index(e)) and SECRET not in cli_outputs(e)


def test_shown_as_written_is_declared(engine):
    """§7: an unprefixed synthetic token is shown as written in exactly the declared fields, and in no other."""
    token = "unprefixedsynthetictoken0123456789"
    assert not K.credential_shaped(token)
    policy = POLICY | {
        "description": token, "harness": token,
        "profiles": {token: {"model": f"{token}/{token}", "provider": token, "effort": token, "description": token}},
        "routing": {"default": token, "cards": {token: token}},
        "provider_env": [token],
        "notify": {"command": [token]},  # never shown
        "containment": {"mode": "required", "writable": [token], "hide": [token]},  # never shown
    }
    out = execution(configured(engine, policy))
    assert out["document"]["state"] == C.ADOPTED
    row = out["profiles"][0]
    shown = {
        "description": out["description"]["value"], "harness": out["harness"]["value"],
        "profile.description": row["fields"]["description"]["value"], "profile.name": row["name"],
        "profile.provider": row["fields"]["provider"]["value"], "profile.effort": row["fields"]["effort"]["value"],
        "routing.default": out["routing"]["default"]["value"],
        "route key": out["routing"]["cards"]["entries"][0]["key"],
        "route target": out["routing"]["cards"]["entries"][0]["profile"]["value"],
        "routed_by card": row["routed_by"][0], "provider_env": out["provider_env"]["entries"][0]["name"],
        "connection provider": out["connections"][0]["provider"],
    }
    assert row["fields"]["model"]["value"] == f"{token}/{token}"
    assert all(token in str(v) for v in shown.values()), shown
    # Nowhere else: strip the declared fields and what derives from them (the identity from the model, every path
    # through a shown name or key, the observed names that mirror provider_env, the effective harness), and the token
    # is gone: the notify command and the containment paths are never shown.
    rest = json.loads(json.dumps(out))
    for fv in field_values(rest):
        fv.pop("path")
        fv.pop("value", None)
        fv.pop("effective", None)
    for row_ in rest["profiles"]:
        row_.update(name=None, identity=None, routed_by=[])
    rest["routing"]["cards"]["entries"][0]["key"] = None
    for entry in [*rest["provider_env"]["entries"], *rest["observed"]["provider_env"]]:
        entry["name"] = None
    for conn in rest["connections"]:
        conn.update(harness=None, provider=None)
    for switch in rest["controls"]["switches"]:
        switch.pop("path")
    assert token not in all_text(rest)
    assert out["controls"]["notify"]["configured"] is True
    assert out["controls"]["containment"]["writable_count"] == 1 == out["controls"]["containment"]["hide_count"]


def test_credential_lookalikes_are_shown_in_the_projection(engine):
    """p1, Q4: a description naming prefixes, profiles named like keys, dated model ids and a git sha as a card id
    stay shown."""
    sha = "4f0a7101c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7"
    policy = POLICY | {
        "description": "the `sk-` key and AKIA prefixes",
        "profiles": {"sk-fast": {"model": "vendor/model-2025-08-07"},
                     "sk-implementer-review-fast": {"model": "vendor/model-2024-11-20"}},
        "routing": {"default": "sk-fast", "cards": {sha: "sk-implementer-review-fast"}},
    }
    out = execution(configured(engine, policy))
    assert out["description"]["value"] == policy["description"]
    assert set(by_name(out)) == {"sk-fast", "sk-implementer-review-fast"}
    assert by_name(out)["sk-fast"]["fields"]["model"]["value"] == "vendor/model-2025-08-07"
    assert out["routing"]["cards"]["entries"][0]["key"] == sha
    assert f"card:{sha}" in by_name(out)["sk-implementer-review-fast"]["routed_by"]


def test_identity_null_when_model_withheld(engine):
    """p2 (designer D2): `openai/sk-proj-<synthetic>` gives a null identity and `field_withheld`."""
    model = "openai/" + "sk-proj-" + "synthetic0123456789abcde"  # synthetic only: 24 characters after the prefix
    assert K.credential_shaped(model) and len(model.split("sk-proj-")[1]) == 24
    out = execution(configured(engine, only_profiles({"standard": {"model": model}})))
    row = by_name(out)["standard"]
    assert row["fields"]["model"]["withheld"] == C.CREDENTIAL_SHAPED and "value" not in row["fields"]["model"]
    assert model not in all_text(out)
    assert row["identity"] is None and row["connection_id"] is None
    assert row["identity_error"]["code"] == C.FIELD_WITHHELD
    assert row["identity_error"]["withheld_reason"] == C.CREDENTIAL_SHAPED
    assert row["identity_error"]["field_path"] == "/profiles/standard/model"


def test_identity_error_code_matches_withheld(engine):
    """D2: every `field_withheld` error's `withheld_reason` is its field's own `withheld`."""
    policy = only_profiles({
        "a": {"model": f"vendor/{SECRET}"}, "b": {"model": "vendor/m", "provider": "x" * 129},
        "c": {"model": "vendor/m", "harness": "Not A Harness"}, "d": {"model": "vendor/m", "provider": SECRET}})
    out = execution(configured(engine, policy))
    errors = [p for p in out["profiles"] if (p["identity_error"] or {}).get("code") == C.FIELD_WITHHELD]
    assert len(errors) == 4
    for row in errors:
        err = row["identity_error"]
        field = next(fv for fv in field_values(row["fields"]) if fv["path"] == err["field_path"])
        assert field["withheld"] == err["withheld_reason"], row


# --------------------------------------------------------------------------------------------------- everything else


def test_field_metadata(engine):
    out = execution(configured(engine))
    root = schema("execution")
    props = root["properties"]
    steering = out["controls"]["steering"]
    assert steering["mode"]["allowed"] == props["steering"]["properties"]["mode"]["enum"]
    assert out["controls"]["containment"]["mode"]["allowed"] == props["containment"]["properties"]["mode"]["enum"]
    switches = {s["path"]: s for s in out["controls"]["switches"]}
    for (block, key), allowed in X.STRING_SWITCHES.items():
        switch = switches[f"/{block}/{key}"]
        assert switch["value"]["allowed"] == list(allowed) and switch["default"] == allowed[0]
        assert switch["value"]["class"] == props[block]["properties"][key]["x-aew-class"]
    model = by_name(out)["standard"]["fields"]["model"]
    assert model["path"] == "/profiles/standard/model" and "allowed" not in model
    assert model["class"] == root["$defs"]["profile"]["properties"]["model"]["x-aew-class"]
    envelope = steering["envelope"]["max_auto_actions"]
    assert envelope["state"] == "SET" and envelope["value"] == 20 and "effective" not in envelope
    # R7: a description is the field's own, never an enclosing object's. The execution schema describes its blocks,
    # not its fields, so no projected field carries one today (a register note asks for per-field descriptions).
    assert "description" in root["$defs"]["profile"] and "description" in props["steering"]["properties"]["envelope"]
    for fv in field_values(out):
        assert fv.get("description") == own_description(fv["path"]), fv["path"]
        assert fv["editable"] is False  # write is UNSUPPORTED in F1
    assert C.field_metadata(("probe",)) == {"class": None}  # a field the schema lacks: nothing invented
    # a node that has its own description gets it (clipped to the bound), so the rule is "own", not "none"
    envelope_text = props["steering"]["properties"]["envelope"]["description"]
    assert C.field_metadata(("steering", "envelope"))["description"] == C._clip(envelope_text)
    assert len(C._clip(envelope_text).encode("utf-8")) <= C.MAX_DESCRIPTION_BYTES


def own_description(path: str) -> str | None:
    """The schema's own description of the field at ``path`` (an independent walk: properties, then the map's values,
    then a list's items; a `$ref` followed), clipped as the projection clips it; None when it has none."""
    root = schema("execution")
    node: dict[str, Any] = root
    for token in P.tokens(path):
        while "$ref" in node:
            node = root["$defs"][node["$ref"].rsplit("/", 1)[-1]]
        props = node.get("properties") or {}
        node = props.get(P.unescape(token)) or node.get("additionalProperties") or node.get("items") or {}
    text = node.get("description")
    if text is None and "$ref" in node:
        text = root["$defs"][node["$ref"].rsplit("/", 1)[-1]].get("description")
    return None if text is None else C._clip(text)


def test_every_enum_fits_and_the_complete_lists_hold_their_invariants():
    """§3.5's complete lists: every schema enum has at most 16 values, the switches fit, the activities and the
    resolution order are fixed."""
    def enums(node: Any) -> list[list[Any]]:
        if isinstance(node, dict):
            return ([node["enum"]] if isinstance(node.get("enum"), list) else []) + [
                e for v in node.values() for e in enums(v)]
        return [e for v in node for e in enums(v)] if isinstance(node, list) else []
    assert all(len(e) <= C.MAX_ALLOWED for e in enums(schema("execution")))
    assert len(X.STRING_SWITCHES) <= C.MAX_SWITCHES
    assert len(C.ACTIVITIES) == 4 and len(C.RESOLUTION_ORDER) == 4


COMPLETE = {"activities", "allowed", "resolution_order", "switches", "reasons"}  # §3.5's complete rows (+ Capability)


def unclassified_lists(node: Any, where: str = "") -> list[str]:
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, list) and key not in COMPLETE and f"{key}_truncated" not in node \
                    and "truncated" not in node:
                out.append(f"{where}/{key}")
            out += unclassified_lists(value, f"{where}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out += unclassified_lists(value, f"{where}/{i}")
    return out


def bounded_policy() -> dict[str, Any]:
    profiles = {f"p{i:03d}": {"model": f"prov{min(i, 32) if i <= 32 else 0:02d}/m"} for i in range(100)}
    return POLICY | {
        "profiles": profiles,
        "routing": {"default": "p000", "cards": {f"card-{i:03d}": "p000" for i in range(300)}},
        "provider_env": [f"VAR_{i:03d}" for i in range(70)],
    }


def test_bounds_and_truncation(engine):
    """Every flagged list at its cap sets its flag; every list is complete by an invariant or flagged (D4)."""
    out = execution(configured(engine, bounded_policy()))
    assert out["profiles_truncated"] and len(out["profiles"]) == C.MAX_PROFILES
    assert out["routing"]["cards"]["truncated"] and len(out["routing"]["cards"]["entries"]) == C.MAX_ROUTE_ENTRIES
    p000 = by_name(out)["p000"]
    assert p000["routed_by_truncated"] and len(p000["routed_by"]) == C.MAX_ROUTED_BY
    assert out["connections_truncated"] and len(out["connections"]) == C.MAX_CONNECTIONS
    prov00 = next(c for c in out["connections"] if c["provider"] == "prov00")
    assert prov00["profiles_truncated"] and len(prov00["profiles"]) == C.MAX_CONNECTION_PROFILES
    assert out["provider_env"]["entries_truncated"] and out["observed"]["provider_env_truncated"]
    assert len(out["observed"]["provider_env"]) == C.MAX_PROVIDER_ENV
    invalid = execution(configured(engine, POLICY | {"profiles": {f"p{i:03d}": {} for i in range(60)}}))
    assert invalid["document"]["violations_truncated"] and len(invalid["document"]["violations"]) == C.MAX_VIOLATIONS
    _with_manifest_policy(engine, **{f"extra{i:02d}": "policy/gates.yaml" for i in range(20)})
    pin_now(engine)
    many = index(engine)
    assert many["documents_truncated"] and len(many["documents"]) == C.MAX_DOCUMENTS
    oversized = execution(configured(engine, oversized_policy()))
    for projection in (out, invalid, many, oversized, execution(configured(engine))):
        assert unclassified_lists(projection) == []
        assert long_strings(projection) == []  # Appendix A: 512 bytes a string, 256 a path (R5)


def long_strings(node: Any, where: str = "", out: list[str] | None = None) -> list[str]:
    """Every emitted string over Appendix A's bound: 256 bytes for a path, 512 for any other string."""
    out = [] if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            long_strings(v, f"{where}/{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            long_strings(v, f"{where}/{i}", out)
    elif isinstance(node, str):
        limit = 256 if where.endswith("/path") or where.endswith("field_path") else 512
        if len(node.encode("utf-8")) > limit:
            out.append(f"{where} ({len(node.encode('utf-8'))} B > {limit})")
    return out


def oversized_policy() -> dict[str, Any]:
    return only_profiles({"standard": {"model": "vendor/m", "effort": "e" * 3000, "description": "p" * 5000}}) | {
        "description": "d" * 5000, "harness": "opencode", "provider_env": ["V" * 3000, "VENDOR_API_KEY"]}


def test_over_bound_strings_are_withheld_never_clipped(engine):
    """R5: a string over its bound has no value and `withheld: too_long`; nothing is clipped, so no shown value is
    content that is not the file's. A name over the bound is null. One byte under the bound is shown whole."""
    out = execution(configured(engine, oversized_policy()))
    standard = by_name(out)["standard"]["fields"]
    for fv in (out["description"], standard["effort"], standard["description"]):
        assert fv["state"] == "SET" and fv["withheld"] == C.TOO_LONG and "value" not in fv, fv["path"]
    assert out["provider_env"]["entries"][0] == {"index": 0, "name": None, "valid_name": True}
    assert out["observed"]["provider_env"][0]["name"] is None
    assert out["provider_env"]["entries"][1]["name"] == "VENDOR_API_KEY"
    exact = "x" * C.MAX_STRING_BYTES
    shown = execution(configured(engine, only_profiles({"standard": {"model": "vendor/m"}}) | {"description": exact}))
    assert shown["description"]["value"] == exact


def test_every_list_classified():
    """§3.5: the classification check itself fails on a list with neither a flag nor a complete-by-invariant row."""
    assert unclassified_lists({"profiles": [], "profiles_truncated": False, "allowed": []}) == []
    assert unclassified_lists({"profiles": []}) == ["/profiles"]
    assert unclassified_lists({"x": {"entries": [], "truncated": False}, "y": [{"routed_by": []}]}) == [
        "/y", "/y/0/routed_by"]


def test_truncated_connections_keep_profile_connection_id(engine):
    out = execution(configured(engine, bounded_policy()))
    listed = {c["connection_id"] for c in out["connections"]}
    assert all(p["connection_id"] for p in out["profiles"])
    unlisted = [p for p in out["profiles"] if p["connection_id"] not in listed]
    assert unlisted and unlisted[0]["name"] == "p032"


def test_connections_join_key(engine):
    """n4: stable for the same `(harness, provider)`, different otherwise, a newline in the harness cannot alias;
    each profile points at its connection, and each connection lists its profiles by index."""
    assert C.connection_id("cfg", "a", "b") == C.connection_id("cfg", "a", "b")
    assert C.connection_id("cfg", "a\nb", "c") != C.connection_id("cfg", "a", "b\nc")
    assert C.connection_id("cfg", "a", "b") != C.connection_id("other", "a", "b")
    out = execution(configured(engine))
    rows = by_name(out)
    assert rows["standard"]["connection_id"] != rows["review"]["connection_id"]
    for conn in out["connections"]:
        assert conn["connection_id"] == C.connection_id("cfg", conn["harness"], conn["provider"])
        for i in conn["profiles"]:
            assert next(p for p in out["profiles"] if p["index"] == i)["connection_id"] == conn["connection_id"]
    assert {(c["harness"], c["provider"]) for c in out["connections"]} == {
        ("opencode", "vendor"), ("opencode", "other"), ("site-harness", "vendor")}


def test_yaml_error_from_problem_mark(engine):
    """N4: the line and column are the parser's mark, one-based; no message text is used."""
    text = "schema: aew/execution/v1\nprofiles:\n  a: [1, 2\n  b: unterminated-synthetic-marker\n"
    with pytest.raises(yaml.YAMLError) as raised:
        yaml.safe_load(text)
    mark = raised.value.problem_mark  # type: ignore[attr-defined]
    out = execution(configured(engine, text))
    assert out["document"]["yaml_error"] == {"code": "YAML_SYNTAX", "line": mark.line + 1, "column": mark.column + 1}
    assert out["document"]["violations"] == [] and "unterminated-synthetic-marker" not in all_text(out)


def test_yaml_error_without_mark_is_null():
    """web 2: no mark gives null line and column (the schema half is F1c's contract test)."""
    assert C.yaml_error(None) == {"code": "YAML_SYNTAX", "line": None, "column": None}
    try:
        raise ValidationFailed("no mark") from yaml.YAMLError("bare")
    except ValidationFailed as exc:
        assert C.yaml_error(exc) == {"code": "YAML_SYNTAX", "line": None, "column": None}


def test_extra_key_named_or_indexed(engine):
    """N3: an extra key is named when it has a safe shape, and is `@i` otherwise."""
    out = execution(configured(engine, POLICY | {"extra_setting": 1, "has space": 2}))
    extras = {v["extra_key"] for v in out["document"]["violations"] if v["code"] == "additionalProperties"}
    assert extras == {"extra_setting", f"@{len(POLICY) + 1}"}
    assert all(v["path"] == "" for v in out["document"]["violations"])


def test_non_string_key_is_indexed(engine):
    """N2: an INVALID document with a key `1:` beside a key `"1"` gives two distinct violation paths."""
    text = "schema: aew/execution/v1\nconfigured: false\nrouting: {default: null}\nprofiles:\n  1: {}\n  '1': {}\n"
    out = execution(configured(engine, text))
    paths = sorted(v["path"] for v in out["document"]["violations"])
    assert "/profiles/@0" in paths and "/profiles/1" in paths


def test_semantic_problems_are_structured(engine):
    policy = POLICY | {"routing": {"default": None, "cards": {"researcher": "missing"}}}
    out = execution(configured(engine, policy))
    assert [(v["path"], v["code"]) for v in out["document"]["violations"]] == [
        ("/routing/cards/researcher", X.NO_SUCH_PROFILE), ("/routing/default", X.NO_DEFAULT_ROUTE)]
    assert "missing" not in all_text(out["document"])


def test_steering_envelope_effective_defaults(engine):
    """n5: with the envelope ABSENT, each field's effective value is `ENVELOPE_DEFAULTS`'s, from the default."""
    out = execution(configured(engine, {k: v for k, v in POLICY.items() if k != "steering"}))
    envelope = out["controls"]["steering"]["envelope"]
    assert set(envelope) == set(S.ENVELOPE_DEFAULTS)
    for key, default in S.ENVELOPE_DEFAULTS.items():
        assert envelope[key]["state"] == "ABSENT" and "value" not in envelope[key]
        assert (envelope[key]["effective"], envelope[key]["effective_source"]) == (default, "default")


def test_fieldvalue_four_cases(engine):
    """D2: SET withheld (no value), a configured NULL (`value: null`), ABSENT (no value) and supplied-effective
    (ABSENT with an effective value from the default) each hold §3.1's table; a withheld SET carrying `value: null`
    breaks it. (The schema half, against the adopted 0.1.4, is F1c's.)"""
    policy = {k: v for k, v in POLICY.items() if k != "steering"} | {
        "profiles": POLICY["profiles"] | {"x": {"model": f"vendor/{SECRET}", "effort": None}}}
    out = execution(configured(engine, policy))
    x = by_name(out)["x"]["fields"]
    cases = {"set_withheld": x["model"], "null": x["effort"], "absent": x["max_steps"],
             "supplied_effective": out["controls"]["steering"]["envelope"]["repetition_n"]}
    assert cases["set_withheld"]["state"] == "SET" and "value" not in cases["set_withheld"]
    assert cases["null"]["state"] == "NULL" and cases["null"]["value"] is None
    assert cases["absent"]["state"] == "ABSENT" and "value" not in cases["absent"]
    assert cases["supplied_effective"]["effective_source"] == "default"
    for fv in [*cases.values(), *field_values(out)]:
        assert fieldvalue_problems(fv) == [], fv
    assert fieldvalue_problems(cases["set_withheld"] | {"value": None}) == ["a withheld SET carries a value"]


def test_withheld_key_path_not_editable(engine):
    """D3: a path with an `@` segment is never editable, even once write is AVAILABLE; an identity path in F46.2's
    scope is."""
    e = configured(engine, POLICY | {"profiles": POLICY["profiles"] | {SECRET: {"model": "vendor/m"}}})
    k = Engine.discover(e.repo_root)._k
    c = C.read_committed(k)
    document = load_yaml((aew(e) / X.REL_PATH).read_text(encoding="utf-8"))
    proj = C._Projector(k, c, document, C.AVAILABLE)
    masked = proj.fv(("profiles", SECRET, "model"), C._model_id, C.F46_2)
    shown = proj.fv(("profiles", "standard", "model"), C._model_id, C.F46_2)
    later = proj.fv(("steering", "mode"), C._text, C.LATER)
    assert masked["path"] == "/profiles/@3/model" and masked["editable"] is False
    assert shown["editable"] is True and later["editable"] is False


def test_unknown_harness_identity_imports_nothing(engine, tmp_path, monkeypatch):
    """nit 5: a non-builtin harness's identity uses C1's inherited rule and imports no adapter module, even when the
    rendering process's `AEW_HARNESS_ADAPTERS` names one."""
    marker = tmp_path / "imported.marker"
    module = tmp_path / "site_adapter.py"
    module.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
                      "from aew.harness.base import HarnessAdapter\nclass Adapter(HarnessAdapter):\n    pass\n",
                      encoding="utf-8")
    monkeypatch.setenv(registry.ENV, f"site-harness={module.as_posix()}:Adapter")
    out = execution(configured(engine))
    light = by_name(out)["light"]
    assert light["identity_rule"] == "inherited" and light["identity"]["harness_ref"] == "vendor/model-light"
    assert by_name(out)["standard"]["identity_rule"] == "adapter"
    assert not marker.exists() and "aew_harness_site-harness" not in sys.modules


def test_read_only_and_lock_free(engine, monkeypatch):
    """The projection never takes the control lock (it reads the committed state lock-free, never `Kernel.manifest`)
    and changes no file."""
    from aew.engine import lock

    e = configured(engine)
    before = {p: p.read_bytes() for p in aew(e).rglob("*") if p.is_file()}

    def refuse(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("the configuration projection took the control lock")

    monkeypatch.setattr(lock.FileLock, "__enter__", refuse)
    fresh = Engine.discover(e.repo_root)
    fresh.configuration()
    fresh.configuration("execution")
    after = {p: p.read_bytes() for p in aew(e).rglob("*") if p.is_file()}
    assert after == before


COLLISIONS = {  # what an open in the middle of a replace raises on Windows (both observed under a real replace loop)
    "sharing_violation": lambda: PermissionError(13, "the process cannot access the file (simulated)"),
    "reported_missing": lambda: FileNotFoundError(2, "the file is missing mid-replace (simulated)"),
}


@pytest.mark.parametrize("collision", sorted(COLLISIONS))
@pytest.mark.parametrize("rel", ["project.yaml", X.REL_PATH])
def test_a_read_racing_a_replace_retries_and_never_misreads(engine, monkeypatch, rel, collision):
    """R4: a writer replaces a file (with identical bytes) while the lock-free read opens it. The read collides once
    (a sharing violation, or the file reported missing), and meanwhile a stat of the file fails, so it looks absent.
    Ordered by events: the writer replaces only after the collision, and the read retries only after the replacement.
    The read retries through the store's one owner and reports the true state, never DRIFTED or MANIFEST_DRIFTED."""
    if collision == "reported_missing" and sys.platform != "win32":
        pytest.skip("only Windows reports a present file missing mid-replace; POSIX rename is atomic")
    e = configured(engine)
    target = aew(e) / rel
    data = target.read_bytes()
    collided, replaced = threading.Event(), threading.Event()
    real_read_bytes, real_is_file = Path.read_bytes, Path.is_file

    def read_bytes(self: Path) -> bytes:
        if self == target and not collided.is_set():
            collided.set()
            assert replaced.wait(30), "the writer never replaced the file"
            raise COLLISIONS[collision]()
        return real_read_bytes(self)

    def is_file(self: Path) -> bool:  # a stat in the middle of the replace fails
        return False if self == target else real_is_file(self)

    def writer() -> None:
        assert collided.wait(30), "the read never opened the file"
        tmp = target.with_name(target.name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        replaced.set()

    fresh = Engine.discover(e.repo_root)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "is_file", is_file)
    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    out = fresh.configuration("execution")
    thread.join(30)
    assert collided.is_set() and replaced.is_set() and not thread.is_alive()
    assert (out["document"]["state"], out["document"]["in_force"]) == (C.ADOPTED, True)
    assert target.read_bytes() == data


# --------------------------------------------------------------------------------------------------------- the CLI


def test_settings_show_cli_equals_the_engine(engine):
    """`aew settings show [execution] [--json]` serves `Engine.configuration` as is; the text form is the same
    data."""
    e = configured(engine)
    env = clean_env({"VENDOR_API_KEY": "synthetic-present-value"})
    for args, document in ((["settings", "show"], None), (["settings", "show", "execution"], "execution")):
        res = run_aew("-C", str(e.repo_root), *args, "--json", env=env)
        assert res.returncode == 0, res.stderr
        want = Engine.discover(e.repo_root).configuration(document, env=env)
        assert res.json == json.loads(json.dumps(want))
        text = run_aew("-C", str(e.repo_root), *args, env=env)
        assert text.returncode == 0 and yaml.safe_load(text.stdout) == res.json


def test_observed_reports_its_own_environment(engine):
    """m5: `observed` is the rendering process's environment, captioned for where it was checked; presence and a
    problem code, never a value."""
    e = configured(engine)
    present = "synthetic-present-value"
    res = run_aew("-C", str(e.repo_root), "settings", "show", "execution", "--json",
                  env={"VENDOR_API_KEY": present, "OTHER_API_KEY": ""})
    observed = res.json["observed"]
    assert observed["checked_in"] == C.CLI_ENVIRONMENT
    assert observed["caption"] == C.OBSERVED_CAPTIONS[C.CLI_ENVIRONMENT]
    assert [(o["name"], o["present"], o["problem"]) for o in observed["provider_env"]] == [
        ("VENDOR_API_KEY", True, None), ("OTHER_API_KEY", False, "unset")]
    assert present not in res.stdout
    server = execution(e, observed_in=C.DASHBOARD_SERVER_ENVIRONMENT, env={"OTHER_API_KEY": "x"})["observed"]
    assert server["caption"] == C.OBSERVED_CAPTIONS[C.DASHBOARD_SERVER_ENVIRONMENT]
    assert [(o["present"], o["problem"]) for o in server["provider_env"]] == [(False, "unset"), (True, None)]


def test_settings_show_refusals(engine, tmp_path):
    """The entry's refusals: USAGE (no such document), PROJECT_NOT_FOUND, INTEGRITY_ERROR (a damaged control.yaml)."""
    e = configured(engine)
    res = run_aew("-C", str(e.repo_root), "settings", "show", "gates")
    assert res.returncode != 0 and res.error["code"] == "USAGE"
    outside = tmp_path / "outside"
    outside.mkdir()
    res = run_aew("-C", str(outside), "settings", "show")
    assert res.returncode != 0 and res.error["code"] == "PROJECT_NOT_FOUND"
    (aew(e) / "state/control.yaml").write_text("schema: [damaged\n", encoding="utf-8")
    res = run_aew("-C", str(e.repo_root), "settings", "show")
    assert res.returncode != 0 and res.error["code"] == "INTEGRITY_ERROR"
