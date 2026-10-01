"""Execution policy: schema, consistency, routing precedence and Lead overrides (ADR-0010)."""

from __future__ import annotations

import pytest

from aew.errors import UsageError, ValidationFailed
from aew.knowledge.manifest import default_manifest
from aew.policy import execution as X
from aew.schemas import validate
from aew.util import dump_yaml, load_yaml

SHA = "0" * 64


def configured(**routing):
    return {
        "schema": "aew/execution/v1", "configured": True, "harness": "opencode",
        "profiles": {"standard": {"provider": "p", "model": "m-std", "effort": "high"},
                     "light": {"provider": "p", "model": "m-light", "effort": "low", "max_steps": 40},
                     "careful": {"provider": "q", "model": "m-care", "harness": "other", "deadline_s": 900}},
        "routing": {"default": "standard", "archetypes": {}, "classes": {}, "cards": {}, **routing},
        "provider_env": ["P_API_KEY"],
    }


def resolve(policy, *, archetype="implementer", card_id="implementer", risk_class=1, request=None):
    return X.resolve(policy, SHA, archetype=archetype, card_id=card_id, risk_class=risk_class, request=request)


def test_template_is_valid_and_unconfigured():
    policy = load_yaml(X.TEMPLATE)
    validate("execution", policy, source="template")
    X.check_semantics(policy, source="template")
    assert policy["configured"] is False and policy["profiles"] == {}
    assert resolve(policy) is None  # no built-in provider or model


def test_no_policy_file_behaves_as_unconfigured(tmp_path):
    manifest = default_manifest("p", "p", "main", "../ws")
    assert X.load(tmp_path, manifest) == (None, None)
    assert resolve(None) is None


def test_manifest_can_relocate_the_policy(tmp_path):
    manifest = default_manifest("p", "p", "main", "../ws")
    manifest["policy"]["execution"] = "policy/elsewhere.yaml"
    (tmp_path / "policy").mkdir()
    (tmp_path / "policy/elsewhere.yaml").write_text(dump_yaml(configured()), encoding="utf-8")
    policy, sha = X.load(tmp_path, manifest)
    assert policy["configured"] and len(sha) == 64


def test_routing_precedence_card_then_class_then_archetype_then_default():
    policy = configured(archetypes={"reviewer": "careful", "implementer": "careful"},
                        classes={"0": "light", "3": "careful"}, cards={"calc_engineer": "light"})
    assert resolve(policy, card_id="calc_engineer", risk_class=3)["rule"] == "card:calc_engineer"
    assert resolve(policy, card_id="calc_engineer", risk_class=3)["profile"] == "light"
    assert resolve(policy, card_id="implementer", risk_class=0)["rule"] == "class:0"
    assert resolve(policy, archetype="reviewer", card_id="reviewer", risk_class=2)["rule"] == "archetype:reviewer"
    assert resolve(policy, archetype="verifier", card_id="verifier", risk_class=2)["rule"] == "default"


def test_pin_carries_profile_fields_policy_hash_and_harness_precedence():
    pin = resolve(configured(archetypes={"implementer": "careful"}))
    assert pin == {"profile": "careful", "harness": "other", "provider": "q", "model": "m-care", "effort": None,
                   "max_steps": None, "deadline_s": 900, "selected_by": "policy", "rule": "archetype:implementer",
                   "policy_sha256": SHA}
    assert resolve(configured())["harness"] == "opencode"  # the policy-level harness when the profile has none


def test_lead_overrides_are_recorded_as_lead_selections():
    policy = configured()
    by_profile = resolve(policy, request={"profile": "light"})
    assert (by_profile["profile"], by_profile["selected_by"], by_profile["rule"]) == ("light", "lead", "lead:profile")
    by_model = resolve(policy, request={"model": "prov/some-model:v2", "effort": "max"})
    assert (by_model["provider"], by_model["model"], by_model["effort"]) == ("prov", "some-model:v2", "max")
    assert by_model["profile"] is None and by_model["selected_by"] == "lead"
    effort_only = resolve(policy, request={"effort": "low"})
    assert (effort_only["profile"], effort_only["effort"]) == ("standard", "low")
    assert (effort_only["selected_by"], effort_only["rule"]) == ("lead", "default+lead:effort")
    same_effort = resolve(policy, request={"effort": "high"})  # no change: still the policy's selection
    assert same_effort["selected_by"] == "policy"


def test_explicit_model_works_without_a_configured_policy():
    pin = resolve(None, request={"model": "prov/m"})
    assert pin["harness"] == X.DEFAULT_HARNESS and pin["selected_by"] == "lead" and pin["policy_sha256"] == SHA


@pytest.mark.parametrize("request_, why", [
    ({"profile": "light", "model": "p/m"}, "alternatives"),
    ({"model": "no-provider"}, "PROVIDER/MODEL"),
    ({"model": "/m"}, "PROVIDER/MODEL"),
    ({"model": "p/m with space"}, "PROVIDER/MODEL"),
    ({"profile": "missing"}, "no execution profile"),
    ({"effort": "high; rm -rf"}, "not a valid effort"),
    ({"temperature": "0"}, "unknown execution selection"),
])
def test_bad_lead_selections_are_refused(request_, why):
    with pytest.raises(UsageError, match=why):
        resolve(configured(), request=request_)


def test_effort_alone_needs_a_selected_model():
    with pytest.raises(UsageError, match="unconfigured"):
        resolve(load_yaml(X.TEMPLATE), request={"effort": "high"})


@pytest.mark.parametrize("routing, why", [
    ({"default": "nope"}, "routing.default: no profile 'nope'"),
    ({"archetypes": {"reviewer": "nope"}}, "routing.archetypes.reviewer"),
    ({"classes": {"2": "nope"}}, "routing.classes.2"),
    ({"cards": {"x": "nope"}}, "routing.cards.x"),
    ({"default": None}, "needs a default route"),
])
def test_inconsistent_policies_fail_closed(routing, why):
    with pytest.raises(ValidationFailed) as exc:
        X.check_semantics(configured(**routing), source="t")
    assert any(why in v for v in exc.value.details["violations"])


@pytest.mark.parametrize("mutate", [
    lambda p: p["profiles"]["standard"].update(api_key="sk-secret"),  # secrets never live in the policy
    lambda p: p.update(provider_env=["P_API_KEY=sk-secret"]),          # names only, never values
    lambda p: p["profiles"]["standard"].update(temperature=0.2),       # no sampling knobs (not sent by V2)
    lambda p: p["routing"]["classes"].update({"7": "standard"}),
    lambda p: p["profiles"]["standard"].update(provider="a/b"),
    lambda p: p.update(extra=True),
])
def test_schema_rejects_secrets_and_unknown_fields(mutate):
    policy = configured()
    mutate(policy)
    with pytest.raises(ValidationFailed):
        validate("execution", policy, source="t")
