"""The live lane's model guard (``tests/helpers/live_models.py``): a live run never uses one of OpenCode's free models,
and a paid model is allowed whatever provider serves it, a paid OpenCode Zen model included (the operator, 2026-11-06).
The live lane is never collected in CI, so its guard is proved here."""

from __future__ import annotations

from live_models import free_model, zero_cost

from aew.harness.opencode.model_pricing import paid_base_problem

PAID = {"input": 0.05, "output": 0.4, "cache": {"read": 0.005, "write": 0}}
NOTHING = {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}}
CATALOG = [
    {"providerID": "opencode", "id": "gpt-5-nano", "cost": [PAID]},
    {"providerID": "opencode", "id": "big-pickle", "cost": [NOTHING]},
    {"providerID": "opencode", "id": "grok-code", "cost": []},
    {"providerID": "openai", "id": "gpt-5-nano", "cost": [PAID]},
    {"providerID": "anthropic", "id": "tiered", "cost": [NOTHING, {**NOTHING, "output": 2.0}]},
]


def test_a_paid_opencode_zen_model_is_not_refused_for_its_provider():
    assert free_model("opencode/gpt-5-nano", CATALOG) is None
    assert free_model("openai/gpt-5-nano", CATALOG) is None


def test_malformed_zen_catalog_entries_get_the_paid_model_refusal():
    entry = {"providerID": "opencode", "id": "synthetic-model"}
    for rate in ("not-a-number", {}, True):
        malformed = {**entry, "cost": [{"input": rate, "output": 1}]}
        assert not zero_cost(malformed)
        problem = paid_base_problem(malformed)
        assert problem and "opencode/synthetic-model does not have a verified paid base price" in problem
    for invalid in ({"cost": [PAID]}, {"id": [], "cost": [PAID]}):
        problem = paid_base_problem(invalid)
        assert problem and "missing or invalid catalog id" in problem and "--profile or --model" in problem


def test_a_model_the_catalog_prices_at_zero_is_refused_whatever_its_provider():
    assert "zero" in free_model("opencode/big-pickle", CATALOG)
    assert "zero" in free_model("opencode/grok-code", CATALOG)  # no cost listed is no price
    assert free_model("openai/big-pickle", [{**CATALOG[1], "providerID": "openai"}])


def test_a_free_id_is_refused_even_when_the_catalog_does_not_list_it():
    assert "-free" in free_model("opencode/minimax-m2.5-free", [])
    assert "-free" in free_model("openrouter/some-model-free", CATALOG)


def test_a_catalog_read_that_cannot_tell_free_from_paid_refuses_and_never_passes_a_free_model():
    """Review E127 M2: ``big-pickle`` is free and not named ``-free``; an empty read must not let it through."""
    assert "empty" in free_model("opencode/big-pickle", [])
    assert "empty" in free_model("opencode/gpt-5-nano", [])
    assert "no anthropic model" in free_model("anthropic/claude-x", CATALOG[:2])


def test_a_model_paid_in_any_tier_is_not_zero_cost_and_an_unlisted_paid_id_is_left_to_the_launch():
    assert not zero_cost(CATALOG[4])
    assert free_model("anthropic/tiered", CATALOG) is None
    assert free_model("openai/not-listed", CATALOG) is None  # the adapter refuses an unlisted pin at launch
    assert not zero_cost({"cost": PAID})  # a single object, as the config schema allows
