"""The G3 service's fixed facts (A-37; STG-03, G3-A): the deployment's tripwires, the PIN's bounds, the key, the issuer
identity, the wire, and what the service may import from AEW.

Each tripwire is planted at its limit (accepted) and one beyond it (refused at start, never clamped): the approval
expiry (G3-02), the consent validity (G3-06), the PIN minimum and the lockout count (G3-05).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from aew.errors import ValidationFailed
from aew_g3 import DEPLOYMENT_FILE, ROOT, deployment, pinstore, render, wire
from aew_g3.keys import KeyStore, key_id_of
from aew_g3.service import PROOF, app_specific_id, issuer_ref_from_machine_id
from tests.helpers import g3 as G

AT_LIMIT = {"approval_expiry_minutes": 10, "consent_validity_minutes": 15, "pin_min_length": 6, "lockout_after": 5}
BEYOND = {"approval_expiry_minutes": 11, "consent_validity_minutes": 16, "pin_min_length": 5, "lockout_after": 6}


# ------------------------------------------------------------------------------------------------ G3-14 deployment
def test_the_shipped_deployment_file_is_the_one_the_service_reads_and_every_value_is_at_its_limit() -> None:
    assert DEPLOYMENT_FILE == G.SHIPPED_DEPLOYMENT.resolve() and ROOT == (G.REPO / "g3").resolve()
    assert json.loads(DEPLOYMENT_FILE.read_bytes()) == AT_LIMIT
    assert deployment.load(DEPLOYMENT_FILE) == deployment.Deployment(**AT_LIMIT)


def test_the_deployment_keys_the_service_checks_are_exactly_the_shipped_files_both_ways() -> None:
    """Two detectors of the closed key list: the checker's table, and the file root installs."""
    shipped = set(json.loads(DEPLOYMENT_FILE.read_bytes()))
    assert set(deployment.TRIPWIRES) <= shipped and shipped <= set(deployment.TRIPWIRES)


@pytest.mark.parametrize("key", sorted(AT_LIMIT))
def test_each_tripwire_is_accepted_at_its_limit_and_stops_the_service_one_beyond(key: str, tmp_path: Path) -> None:
    assert deployment.deployment_errors(dict(AT_LIMIT, **{key: AT_LIMIT[key]})) == []
    assert deployment.deployment_errors(dict(AT_LIMIT, **{key: BEYOND[key]})) == [f"BEYOND_TRIPWIRE:{key}"]
    f = tmp_path / "deployment.json"
    f.write_bytes(json.dumps(dict(AT_LIMIT, **{key: BEYOND[key]})).encode())
    with pytest.raises(ValidationFailed) as e:
        deployment.load(f)
    assert e.value.details["reason"] == "DEPLOYMENT_INVALID"
    assert e.value.details["errors"] == [f"BEYOND_TRIPWIRE:{key}"]


@pytest.mark.parametrize("key", sorted(AT_LIMIT))
@pytest.mark.parametrize("bad", ["absent", None, "10", 0, -1, True, 1.5])
def test_a_missing_or_malformed_deployment_value_stops_the_service(key: str, bad: Any) -> None:
    values = {k: v for k, v in AT_LIMIT.items() if k != key}
    if bad != "absent":
        values[key] = bad
    assert deployment.deployment_errors(values) == [f"MISSING:{key}"]


def test_the_deployment_may_tighten_each_value_the_safe_way() -> None:
    assert deployment.deployment_errors({"approval_expiry_minutes": 1, "consent_validity_minutes": 1,
                                         "pin_min_length": 128, "lockout_after": 1}) == []


def test_an_unknown_key_a_minimum_no_pin_can_meet_or_a_non_object_stops_the_service(tmp_path: Path) -> None:
    assert deployment.deployment_errors(dict(AT_LIMIT, lockout_afer=3)) == ["UNKNOWN:lockout_afer"]
    assert deployment.deployment_errors(dict(AT_LIMIT, pin_min_length=129)) == ["BEYOND_WIRE:pin_min_length"]
    assert deployment.deployment_errors([AT_LIMIT]) == ["NOT_AN_OBJECT:deployment"]
    f = tmp_path / "deployment.json"
    f.write_bytes(b"{not json")
    with pytest.raises(ValidationFailed) as e:
        deployment.load(f)
    assert e.value.details["reason"] == "DEPLOYMENT_UNREADABLE"
    with pytest.raises(ValidationFailed):
        deployment.load(tmp_path / "absent.json")


# ------------------------------------------------------------------------------------------------ G3-05 the PIN
@pytest.mark.parametrize(("minimum", "length", "ok"), [(6, 6, True), (6, 5, False), (8, 8, True), (8, 7, False),
                                                       (6, 128, True), (6, 129, False)])
def test_set_pin_takes_a_pin_from_the_deployments_minimum_to_the_wires_maximum(tmp_path: Path, minimum: int,
                                                                                length: int, ok: bool) -> None:
    dep = deployment.Deployment(**dict(AT_LIMIT, pin_min_length=minimum))
    pin = "p" * length
    if ok:
        pinstore.set_pin(tmp_path, pin, dep)
        rec = pinstore.read(tmp_path)
        assert rec.matches(pin) and not rec.matches(pin + "x") and rec.min_length == minimum
    else:
        with pytest.raises(ValidationFailed) as e:
            pinstore.set_pin(tmp_path, pin, dep)
        assert e.value.details["reason"] == "PIN_LENGTH"
        assert not (tmp_path / pinstore.PIN_FILE).exists()


def test_the_pin_record_holds_a_salted_scrypt_hash_and_never_the_pin(tmp_path: Path) -> None:
    dep = deployment.Deployment(**AT_LIMIT)
    first = pinstore.set_pin(tmp_path, G.PIN, dep)
    a = (tmp_path / pinstore.PIN_FILE).read_bytes()
    second = pinstore.set_pin(tmp_path, G.PIN, dep)
    b = (tmp_path / pinstore.PIN_FILE).read_bytes()
    assert G.PIN.encode() not in a and G.PIN.encode() not in b
    rec = json.loads(a)
    assert rec["n"] >= 2 ** 14 and rec["r"] == 8 and set(rec) == {"pin_id", "salt", "hash", "n", "r", "p",
                                                                   "min_length"}
    assert first != second and json.loads(b)["salt"] != rec["salt"], "each set is a fresh salt and a fresh pin_id"
    assert not list(tmp_path.glob("*.new"))
    if sys.platform != "win32":
        assert (tmp_path / pinstore.PIN_FILE).stat().st_mode & 0o777 == 0o600


def test_the_wires_pin_bounds_are_the_profiles_floor_and_the_set_pin_ceiling() -> None:
    pin = wire.schema()["$defs"]["ApprovalDecision"]["properties"]["pin"]
    assert pin["minLength"] == deployment.TRIPWIRES["pin_min_length"][1] == 6
    assert pin["maxLength"] == deployment.pin_max_length() == 128


# ------------------------------------------------------------------------------------------------ G3-09 the key
def test_the_key_is_a_p256_file_mode_0600_whose_id_is_the_sha256_of_its_public_key(tmp_path: Path) -> None:
    import hashlib

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    ks = KeyStore(tmp_path)
    key = serialization.load_pem_private_key((tmp_path / "signing-key.pem").read_bytes(), password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1)
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert ks.key_id == hashlib.sha256(der).hexdigest() == key_id_of(key.public_key())
    assert KeyStore(tmp_path).key_id == ks.key_id, "a restart keeps the key"
    if sys.platform != "win32":
        assert (tmp_path / "signing-key.pem").stat().st_mode & 0o777 == 0o600
    record = {"a": 1}
    sig = ks.sign(record)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,200}", sig)
    assert ks.verifies(dict(record, key_id=ks.key_id, signature=sig)) is False, "key_id is part of what is signed"
    signed = {"a": 1, "key_id": ks.key_id}
    assert ks.verifies(dict(signed, signature=ks.sign(signed)))
    assert not ks.verifies(dict(signed, a=2, signature=ks.sign(signed)))


def test_published_keys_and_the_issuer_ref_are_readable_files_in_the_runtime_keys_directory(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    ks = KeyStore(tmp_path / "state")
    ks.publish(tmp_path / "run" / "keys", G.ISSUER)
    names = sorted(p.name for p in (tmp_path / "run" / "keys").iterdir())
    assert names == sorted([f"{ks.key_id}.pub", "issuer_ref"])
    assert (tmp_path / "run" / "keys" / "issuer_ref").read_bytes() == G.ISSUER.encode() + b"\n"
    assert b"PRIVATE" not in (tmp_path / "run" / "keys" / f"{ks.key_id}.pub").read_bytes()
    if sys.platform != "win32":
        assert all((tmp_path / "run" / "keys" / n).stat().st_mode & 0o777 == 0o644 for n in names)


# ------------------------------------------------------------------------------------------------ issuer_ref
# Known answers from systemd itself (249, WSL Ubuntu, 2026-10-25): `systemd-id128 machine-id
# --app-specific=8799075224ae4f699e730c18f9133411` with each synthetic machine id bind-mounted over /etc/machine-id.
KNOWN = {"0123456789abcdef0123456789abcdef": "02963991e7da4d4890e62c6810fa9e30",
         "fedcba9876543210fedcba9876543210": "8f9d9d58f31e4fb0b583fa954001084b"}


@pytest.mark.parametrize(("machine_id", "expected"), sorted(KNOWN.items()))
def test_the_issuer_is_systemds_app_specific_machine_id_for_g3_and_fits_the_wire(machine_id: str,
                                                                                 expected: str) -> None:
    assert app_specific_id(machine_id + "\n") == expected
    ref = issuer_ref_from_machine_id(machine_id)
    assert ref == "g3:host:" + expected  # hand-off addendum 3: the fixed prefix
    pattern = wire.schema()["$defs"]["ConsentRecord"]["properties"]["issuer_ref"]["pattern"]
    assert re.match(pattern, ref)
    assert machine_id not in ref


def test_the_known_answers_include_an_id_that_starts_with_a_digit_which_bare_g3_would_not_fit() -> None:
    """Hand-off addendum 3's test: the prefix is what keeps such a host's records on the wire."""
    pattern = wire.schema()["$defs"]["ConsentRecord"]["properties"]["issuer_ref"]["pattern"]
    digit_first = next(v for v in KNOWN.values() if v[0].isdigit())
    assert not re.match(pattern, "g3:" + digit_first) and re.match(pattern, "g3:host:" + digit_first)


@pytest.mark.parametrize("bad", ["", "\n", "0" * 32, "0123456789ABCDEF0123456789ABCDEF", "0123456789abcdef",
                                 "uninitialized", "0123456789abcdef0123456789abcdeg"])
def test_a_missing_or_malformed_machine_id_gives_no_issuer(bad: str) -> None:
    with pytest.raises(ValueError):
        issuer_ref_from_machine_id(bad)


# ------------------------------------------------------------------------------------------------ the wire
def test_the_vendored_wire_is_a26s_and_its_problem_codes_and_statuses_are_the_services() -> None:
    assert wire.WIRE == "g3-0.6.1-candidate"
    problem = wire.schema()["$defs"]["Problem"]["properties"]
    assert set(wire.STATUS) == set(problem["code"]["enum"])
    assert set(wire.STATUS.values()) == set(problem["status"]["enum"])
    assert PROOF.pattern == wire.schema()["$defs"]["Proof"]["pattern"]


def test_r2_1_the_rendering_limit_is_derived_from_the_sealed_o01_schema() -> None:
    o01 = wire.o01_schema()
    per = render.member_line_limits(o01, wire.registry())
    members = o01["$defs"]["CommandSet"]["properties"]["intents"]["maxItems"]
    defs = wire.schema()["$defs"]
    assert defs["PendingApproval"]["properties"]["rendering"]["maxItems"] == 3 + members * max(per.values()) == 243
    assert defs["ConsentRecord"]["properties"]["intent_refs"]["maxItems"] == members
    assert defs["ConsentRecord"]["properties"]["member_proofs"]["maxProperties"] == members
    assert f"intents\\[[0-{members - 1}]\\]" in defs["RenderingLine"]["properties"]["source"]["properties"][
        "field_path"]["pattern"]


@pytest.mark.parametrize("edit", ["array", "open"])
def test_r2_1_a_protected_intent_with_an_array_or_an_open_object_is_refused_as_unbounded(edit: str) -> None:
    import copy

    o01 = copy.deepcopy(wire.o01_schema())
    target = next(b for b in o01["$defs"]["Intent"]["allOf"]
                  if b["if"]["properties"]["action"]["const"] == "ATTACH_LEAD")["then"]["properties"]["target"]
    while "$ref" in target:
        target = o01["$defs"][target["$ref"].split("/")[-1]]
    if edit == "array":
        target["properties"]["extra"] = {"type": "array", "items": {"type": "string"}}
    else:
        target["additionalProperties"] = True
    with pytest.raises(ValueError, match="unbounded"):
        render.member_line_limits(o01, wire.registry())


def _schema_leaves(action: str, index: int) -> set[str]:
    """The second detector of G3-03's covered leaves: from the sealed O-01 schema, never from an instance."""
    defs = wire.o01_schema()["$defs"]

    def resolve(x: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in x:
            x = defs[x["$ref"].split("/")[-1]]
        return x

    def walk(x: dict[str, Any], path: str) -> set[str]:
        x = resolve(x)
        if x.get("type") == "object" or "properties" in x:
            return set().union(*(walk(v, f"{path}.{k}") for k, v in x["properties"].items()))
        return {path}

    intent = defs["Intent"]
    target = next(b for b in intent["allOf"] if b["if"]["properties"]["action"]["const"] == action)
    out = set().union(*(walk(v, f"intents[{index}].{k}") for k, v in intent["properties"].items() if k != "target"))
    return out | walk(target["then"]["properties"]["target"], f"intents[{index}].target")


def test_the_covered_leaves_the_rendering_shows_agree_both_ways_with_the_o01_schemas_leaves() -> None:
    """Two independently written detectors of the leaves G3-03 requires: the instance walk the service renders
    from (render.leaves), and the sealed schema's own properties."""
    cs = G.base_set()
    cs["intents"].append(dict(cs["intents"][0], intent_ref="intent:zz-second"))
    by_instance = {f for f, _ in render.leaves(cs)}
    by_schema = set(render.SET_FIELDS) | _schema_leaves("ATTACH_LEAD", 0) | _schema_leaves("ATTACH_LEAD", 1)
    assert by_instance - by_schema == set() and by_schema - by_instance == set()


# ------------------------------------------------------------------------------------------------ apartness
ALLOWED_AEW = {"aew.errors", "aew.stg02.adopted", "aew.stg02.wire"}


def test_the_service_imports_from_aew_only_the_sealed_o01_files_sw02_and_the_error_types() -> None:
    """The service stays small and apart: it derives O-01 and SW-02 from their one owner and takes AEW's typed
    errors, and nothing else of AEW (no engine, no harness, no store)."""
    modules: dict[str, set[str]] = {}
    for f in sorted((ROOT / "aew_g3").glob("*.py")):
        for node in ast.walk(ast.parse(f.read_bytes())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                # `from aew.stg02 import adopted` imports the submodule; `from aew.errors import X` imports a name.
                names = ([f"{node.module}.{a.name}" for a in node.names] if node.module in ("aew", "aew.stg02")
                         else [node.module])
            for n in names:
                if n == "aew" or n.startswith("aew."):
                    modules.setdefault(n, set()).add(f.name)
    assert set(modules) - ALLOWED_AEW == set(), modules
    assert set(modules) == ALLOWED_AEW, "control: the detector sees the imports the service does make"

