"""The model identity (ADR-0010 amendment 2026-10-11): one adapter-owned rule maps a model id, typed exactly as the
harness prints it, to the provider/model pair AEW pins, so the harness is never given a doubled reference."""

from __future__ import annotations

import pytest

from aew.errors import UsageError, ValidationFailed
from aew.harness import models, registry
from aew.harness.base import HarnessAdapter
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.harness.opencode.projection import config_model, model_ref
from aew.policy import execution as X

SHA = "0" * 64


def policy(**profiles):
    return {"schema": "aew/execution/v1", "configured": True, "harness": "opencode", "profiles": profiles,
            "routing": {"default": "standard", "archetypes": {}, "classes": {}, "cards": {}}, "provider_env": []}


def pin(p, request=None):
    return X.resolve(p, SHA, archetype="implementer", card_id="implementer", risk_class=1, request=request,
                     identity=registry.model_identity)


@pytest.mark.parametrize(("provider", "model"), [("vendor", "vendor/model-a"), (None, "vendor/model-a"),
                                                 ("vendor", "model-a")])
def test_a_model_id_typed_as_the_harness_prints_it_pins_the_provider_and_the_model_apart(provider, model):
    profile = {"model": model, "effort": "high", **({"provider": provider} if provider else {})}
    got = pin(policy(standard=profile))
    assert (got["provider"], got["model"]) == ("vendor", "model-a")
    # so the harness is given vendor/model-a, never vendor/vendor/model-a
    assert model_ref(got) == {"providerID": "vendor", "id": "model-a", "variant": "high"}
    assert config_model(got) == {"providerID": "vendor", "model": "model-a", "variant": "high"}


def test_the_identity_carries_the_raw_id_the_pair_and_the_harness_reference():
    assert models.from_profile("vendor", "vendor/model-a").as_dict() == {
        "catalog_id": "vendor/model-a", "provider": "vendor", "model": "model-a", "harness_ref": "vendor/model-a"}
    assert models.from_listing("router/maker/model-b").as_dict() == {
        "catalog_id": "router/maker/model-b", "provider": "router", "model": "maker/model-b",
        "harness_ref": "router/maker/model-b"}


def test_a_providers_own_catalog_id_is_never_stripped_even_when_it_contains_a_slash():
    """A direct provider's ``GET /v1/models`` lists bare ids; a routing provider's may be ``maker/model``."""
    assert models.from_catalog("vendor", "model-a").harness_ref == "vendor/model-a"
    routed = models.from_catalog("router", "maker/model-b")
    assert (routed.catalog_id, routed.provider, routed.model) == ("maker/model-b", "router", "maker/model-b")
    assert routed.harness_ref == models.from_listing("router/maker/model-b").harness_ref  # one rule, both directions


def test_a_prefix_naming_another_provider_is_refused_naming_the_field_the_value_and_the_fix():
    with pytest.raises(ValidationFailed) as refused:
        pin(policy(standard={"provider": "vendor", "model": "other/model-a"}))
    err = refused.value
    assert err.details["field"] == "profiles.standard.model" and err.details["value"] == "other/model-a"
    assert err.details["reason"] == "model_id_provider_conflict"
    assert err.details["suggestions"] == ["other/model-a", "vendor/other/model-a"]
    assert "profiles.standard.model" in err.message and "'other/model-a'" in err.message
    assert "Did you mean other/model-a" in err.message and "vendor/other/model-a" in err.message


def test_a_model_of_a_routing_provider_is_written_as_the_harness_lists_it():
    got = pin(policy(standard={"provider": "router", "model": "router/maker/model-b"}))
    assert (got["provider"], got["model"]) == ("router", "maker/model-b")
    got = pin(policy(standard={"model": "router/maker/model-b"}))
    assert (got["provider"], got["model"]) == ("router", "maker/model-b")


@pytest.mark.parametrize(("profile", "reason"), [
    ({"model": "model-a"}, "model_id_no_provider"),
    ({"model": "/model-a"}, "model_id_malformed"),
    ({"model": "vendor/"}, "model_id_malformed"),
    ({"provider": "vendor", "model": "model a"}, "model_id_malformed"),
    ({"model": "openai/MODEL_ID"}, "model_id_malformed"),
    ({"model": "openai/YOUR_MODEL_ID"}, "model_id_malformed"),
    ({"model": "openai/<model>"}, "model_id_malformed"),
    ({"model": "openai/<id>suffix"}, "model_id_malformed"),
    ({"model": "openai/<id"}, "model_id_malformed"),
    ({"model": "openai/id>"}, "model_id_malformed"),
    ({"model": "<openai>/model"}, "model_id_malformed"),
])
def test_a_model_id_that_maps_to_no_pair_is_refused_with_its_reason(profile, reason):
    with pytest.raises(ValidationFailed) as refused:
        pin(policy(standard=profile))
    assert refused.value.details["reason"] == reason and refused.value.details["field"] == "profiles.standard.model"
    if reason == "model_id_malformed" and ("<" in profile["model"] or ">" in profile["model"] or
                                           "MODEL_ID" in profile["model"] or "YOUR_MODEL_ID" in profile["model"]):
        assert refused.value.details["value"] == profile["model"]
        assert "opencode models" in refused.value.message
        assert "profiles.standard.model" in refused.value.message
        assert "full provider/model ID" in refused.value.message


def test_a_placeholder_in_the_explicit_provider_part_is_refused():
    with pytest.raises(ValidationFailed) as refused:
        pin(policy(standard={"provider": "<openai>", "model": "model"}))
    assert refused.value.details["reason"] == "model_id_malformed"
    assert refused.value.details["value"] == "<openai>"
    assert refused.value.details["field"] == "profiles.standard.provider"
    assert refused.value.details["model"] == "model"


def test_catalog_and_listing_placeholders_are_provider_owned_ids():
    assert models.from_catalog("vendor", "MODEL_ID").model == "MODEL_ID"
    assert models.from_listing("vendor/MODEL_ID").model == "MODEL_ID"


@pytest.mark.parametrize("model", ["openai/model-id", "openai/myMODEL_IDmodel", "openai/myidmodel"])
def test_legitimate_model_and_id_substrings_are_not_placeholders(model):
    assert models.from_profile(None, model).harness_ref == model


def test_the_leads_model_override_uses_the_same_rule():
    got = pin(policy(standard={"model": "vendor/model-a"}), request={"model": "router/maker/model-b"})
    assert (got["provider"], got["model"], got["rule"]) == ("router", "maker/model-b", "lead:model")
    with pytest.raises(UsageError) as refused:
        pin(None, request={"model": "model-a"})
    assert "PROVIDER/MODEL" in refused.value.message and refused.value.details["field"] == "--model"


def test_every_profile_model_resolves_through_the_harness_adapter():
    """The adapter owns the rule: the engine's resolution asks the profile's harness adapter, and an adapter whose
    harness names models differently is the one place that changes it."""
    assert OpenCodeAdapter.model_identity is not None
    assert registry.model_identity("opencode", "vendor", "vendor/model-a", "f").model == "model-a"
    # an adapter that cannot be loaded here gets the inherited rule, so its pin is the same pair
    assert registry.model_identity("no-such-harness", None, "vendor/model-a", "f") == HarnessAdapter.model_identity(
        None, "vendor/model-a", field="f")

    class Renaming(HarnessAdapter):  # a harness whose ids carry no provider
        @classmethod
        def model_identity(cls, provider, model, *, field="model"):
            return models.ModelIdentity(model, "fixed", model)

    calls = []

    def identity(harness, provider, model, field):
        calls.append((harness, provider, model, field))
        return Renaming.model_identity(provider, model, field=field)

    got = X.resolve(policy(standard={"model": "vendor/model-a", "harness": "renaming"}), SHA,
                    archetype="implementer", card_id=None, risk_class=None, identity=identity)
    assert calls == [("renaming", None, "vendor/model-a", "profiles.standard.model")]
    assert (got["harness"], got["provider"], got["model"]) == ("renaming", "fixed", "vendor/model-a")


def test_a_profile_may_omit_the_provider_in_the_schema():
    from aew.schemas import validate

    validate("execution", policy(standard={"model": "vendor/model-a"}), source="test")
    with pytest.raises(ValidationFailed):
        validate("execution", policy(standard={"provider": "vendor"}), source="test")  # the model stays required


CATALOG_SHAPES = [models.from_catalog("vendor", "model-a"), models.from_catalog("router", "maker/model-b"),
                  models.from_catalog("router", "router/auto"), models.from_listing("vendor/model-a"),
                  models.from_listing("router/maker/model-b"), models.from_listing("router/router/auto")]


@pytest.mark.parametrize("identity", CATALOG_SHAPES, ids=lambda x: x.catalog_id)
def test_a_chooser_saving_the_harness_reference_round_trips_every_catalog_shape(identity):
    """A chooser writes ``model: <harness_ref>`` and no provider (review of PR #214, F3): that profile resolves to the
    very pair the catalog entry named, whatever the model id contains."""
    fields = identity.profile_fields()
    assert fields == {"model": identity.harness_ref}
    got = pin(policy(standard=fields))
    assert (got["provider"], got["model"]) == (identity.provider, identity.model)


def test_the_split_pair_of_a_nested_catalog_id_is_not_a_profile_form():
    """Documented, not guaranteed: written back split, a routing provider's nested model is a conflicting prefix."""
    nested = models.from_catalog("router", "maker/model-b")
    with pytest.raises(ValidationFailed) as refused:
        pin(policy(standard={"provider": nested.provider, "model": nested.model}))
    assert refused.value.details["reason"] == "model_id_provider_conflict"


def test_a_providers_own_model_id_that_begins_with_its_name_is_written_in_full():
    """The provider's own prefix is removed silently (N1): ``router/auto`` under ``router`` pins ``auto``; the model
    OpenCode prints as ``router/router/auto`` is written in full."""
    assert (pin(policy(standard={"provider": "router", "model": "router/auto"}))["model"]) == "auto"
    assert (pin(policy(standard={"model": "router/router/auto"}))["model"]) == "router/auto"
