"""The OpenCode adapter's token-semantics mapping, pinned against the qualified harness version (F25, the cost and
usage ledger design v0.2 R4 rule 1 and §7 slice 1: "the adapter's token_semantics mapping pinned against the 2.0.18
OpenAPI fixture in the harness conformance suite").

The qualified pairs: ``openai`` on OpenCode 2.0.18, from OpenCode's source (the fixture cites tag, commit and lines),
and on 2.2.6, measured; and on 2.2.6 one route of OpenCode Zen (``opencode``), its Responses route, measured by a live
turn (its fixture holds the two calls' usage and the meter's record). Every other provider, route and version
resolves to ``unknown``, which is never priced."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from aew.engine import usage_ops as O
from aew.harness import usage as U
from aew.harness.opencode.adapter import ZEN_RESPONSES, OpenCodeAdapter, catalog_routes
from aew.harness.opencode.capabilities import TESTED_VERSIONS

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "opencode"
                      / f"usage-{TESTED_VERSIONS[0]}-openai.json")
                     .read_text(encoding="utf-8"))
ZEN = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "opencode"
                  / "usage-2.2.6-opencode-responses.json").read_text(encoding="utf-8"))
UNIT_PRICES = O.Prices(b"schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\nsource: test\nprices:\n"
                       b"  openai/gpt-6.1: {input: 1, output: 1, reasoning: 1, cache_read: 1, cache_write: 1}\n",
                       source="test")


def declared(version: str, provider: str) -> str:
    return U.resolve_semantics(OpenCodeAdapter.token_semantics, version, [provider])


def test_the_mapping_names_only_the_qualified_version_and_provider():
    assert FIXTURE["version"] in TESTED_VERSIONS
    assert {v: dict(m) for v, m in OpenCodeAdapter.token_semantics.items()} == {
        "2.0.18": {"openai": "disjoint"},
        "2.2.6": {"openai": "disjoint", "opencode": {ZEN_RESPONSES: "disjoint"}}}
    assert declared(FIXTURE["version"], FIXTURE["provider"]) == FIXTURE["token_semantics"] == "disjoint"


@pytest.mark.parametrize("provider", ["anthropic", "bedrock", "google", "openrouter", "opencode", "azure"])
def test_a_provider_without_a_qualified_mapping_is_unknown_and_never_priced(provider):
    assert declared("2.0.18", provider) == "unknown"
    rec = U.normalize({"tokens": {"input": 10, "output": 5, "reasoning": 0, "cache": {"read": 0, "write": 0}}}, [{}],
                      [{"provider": provider, "model": "gpt-6.1", "effort": None}], declared("2.0.18", provider),
                      source="harness:opencode")
    assert O.derive(rec, UNIT_PRICES)[0] == {"unpriced": "unpriced_token_semantics_unknown"}


def test_another_opencode_version_has_no_pinned_mapping_and_is_unknown():
    assert declared("2.0.19", "openai") == "unknown"
    assert declared("1.0.0", "openai") == "unknown"


def test_providers_that_disagree_or_a_missing_provider_are_unknown():
    assert U.resolve_semantics(OpenCodeAdapter.token_semantics, "2.0.18", ["openai", "anthropic"]) == "unknown"
    assert U.resolve_semantics(OpenCodeAdapter.token_semantics, "2.0.18", [None]) == "unknown"
    assert U.resolve_semantics(OpenCodeAdapter.token_semantics, None, ["openai"]) == "unknown"


def stored_by_the_cited_mapper(raw: dict) -> dict:
    """OpenCode 2.0.18's computation as the fixture cites it (open-responses.ts:843-859, events.ts:20-85,
    usage.ts:11-19), restated so the fixture's stored values are checked, not merely trusted."""
    cached = raw["input_tokens_details"]["cached_tokens"]
    written = raw["input_tokens_details"]["cache_write_tokens"]
    reasoning = raw["output_tokens_details"]["reasoning_tokens"]
    return {"input": raw["input_tokens"] - (cached + written), "output": max(0, raw["output_tokens"] - reasoning),
            "reasoning": reasoning, "cache": {"read": cached, "write": written}}


def test_the_fixture_cites_the_source_it_was_qualified_from():
    source = FIXTURE["source"]
    assert source["tag"] == "v2.0.18" and len(source["commit"]) == 40
    assert {e["file"] for e in source["evidence"]} == {"packages/core/src/session/usage.ts",
                                                       "packages/ai/src/schema/events.ts",
                                                       "packages/ai/src/protocols/open-responses.ts"}
    cases = FIXTURE["cases"]
    assert len(cases) >= 2
    assert any(c["stored"]["reasoning"] > 0 and c["stored"]["cache"]["read"] > 0 and c["stored"]["cache"]["write"] > 0
               for c in cases)


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=[c["name"] for c in FIXTURE["cases"]])
def test_disjoint_openai_counters_bill_each_raw_token_exactly_once(case):
    raw, stored = case["raw"], case["stored"]
    assert stored == stored_by_the_cited_mapper(raw)
    assert stored["input"] + stored["cache"]["read"] + stored["cache"]["write"] == raw["input_tokens"]
    assert stored["output"] + stored["reasoning"] == raw["output_tokens"]
    # Priced at $1 per million tokens in every bucket, the disjoint buckets cost exactly the raw tokens once.
    rec = U.normalize({"tokens": stored}, [{}], [{"provider": "openai", "model": "gpt-6.1", "effort": None}],
                      declared("2.0.18", "openai"), source="harness:opencode")
    assert rec["tokens_trust"] == "harness_reported"
    figure, _ = O.derive(rec, UNIT_PRICES)
    assert figure == {"usd": Decimal(raw["input_tokens"] + raw["output_tokens"]).scaleb(-6)}


# ---------------------------------------------------------------- OpenCode Zen (`opencode`), declared per route

ZEN_MODEL = ("opencode", ZEN["model"])


def zen(routes: dict[tuple[str, str], str] | None, *items: object, version: str = "2.2.6") -> str:
    return U.resolve_semantics(OpenCodeAdapter.token_semantics, version, list(items), routes)


def test_zens_responses_route_is_disjoint_and_no_other_zen_route_is_inferred():
    assert ZEN["route"] == ZEN_RESPONSES and ZEN["token_semantics"] == "disjoint"
    responses = {ZEN_MODEL: ZEN_RESPONSES}
    assert zen(responses, ZEN_MODEL) == "disjoint"
    # A route not measured, a model with no route, the provider named without its model, another version: unknown.
    for route in ("@opencode/ai/providers/anthropic", "@opencode/ai/providers/openai-compatible",
                  "@opencode/ai/providers/google", "@opencode/ai/providers/mistral"):
        assert zen({ZEN_MODEL: route}, ZEN_MODEL) == "unknown", route
    assert zen(None, ZEN_MODEL) == "unknown"
    assert zen(responses, "opencode") == "unknown"
    assert zen(responses, ZEN_MODEL, version="2.0.18") == "unknown"
    # One record carries one declaration: a Zen model on another route beside it is unknown.
    other = ("opencode", "claude-haiku-5-5")
    assert zen({**responses, other: "@opencode/ai/providers/anthropic"}, ZEN_MODEL, other) == "unknown"
    # A provider declared for all its models still resolves from a (provider, model) pair, routes or not.
    assert zen(None, ("openai", "gpt-6.1")) == zen(responses, ("openai", "gpt-6.1"), ZEN_MODEL) == "disjoint"


def test_the_route_of_a_model_is_its_catalog_package_for_routed_providers_only():
    catalog = [{"providerID": "opencode", "id": "gpt-5.6-luna", "package": ZEN_RESPONSES},
               {"providerID": "opencode", "id": "claude-haiku-5-5", "package": "@opencode/ai/providers/anthropic"},
               {"providerID": "opencode", "id": "no-package"},
               {"providerID": "openai", "id": "gpt-6.1", "package": "@ai-sdk/openai"}]
    assert catalog_routes(catalog, OpenCodeAdapter.token_semantics) == {
        ("opencode", "gpt-5.6-luna"): ZEN_RESPONSES,
        ("opencode", "claude-haiku-5-5"): "@opencode/ai/providers/anthropic"}


def test_zens_live_calls_split_disjoint_are_the_meters_record_and_bill_each_raw_token_once():
    """The live turn's two calls (token counts and cost only): Zen's ``input_tokens`` counts cache reads and cache
    writes, its ``output_tokens`` counts reasoning, so split as the cited mapper splits OpenAI's they equal the meter's
    final record in every category, and the provider's per-call costs sum to the meter's provider cost."""
    calls = ZEN["calls"]
    stored = [stored_by_the_cited_mapper(c) for c in calls]
    total = {"input": sum(s["input"] for s in stored), "output": sum(s["output"] for s in stored),
             "reasoning": sum(s["reasoning"] for s in stored),
             "cache_read": sum(s["cache"]["read"] for s in stored),
             "cache_write": sum(s["cache"]["write"] for s in stored)}
    assert total == ZEN["meter"]["tokens"] == {"input": 241, "output": 80, "reasoning": 115, "cache_read": 2163,
                                               "cache_write": 3427}
    assert sum(total.values()) == sum(c["total_tokens"] for c in calls) == 6026
    assert round(sum(c["cost"] for c in calls), 8) == ZEN["meter"]["provider_cost_usd"]
    # A split that left the cache writes in the input would not hold: the meter is not merely equal to any split.
    assert sum(c["input_tokens"] - c["input_tokens_details"]["cached_tokens"] for c in calls) != total["input"]
    # Zen's own breakdown agrees: its input is the disjoint input, and its output includes reasoning.
    for call, split in zip(calls, stored, strict=True):
        own = call["opencode"]["tokens"]
        assert own["input"] == split["input"] and own["output"] == split["output"] + split["reasoning"]
    rec = U.normalize({"tokens": {"input": total["input"], "output": total["output"], "reasoning": total["reasoning"],
                                  "cache": {"read": total["cache_read"], "write": total["cache_write"]}}},
                      [{}], [{"provider": "opencode", "model": "gpt-6.1", "effort": None}],
                      zen({("opencode", "gpt-6.1"): ZEN_RESPONSES}, ("opencode", "gpt-6.1")), source="harness:opencode")
    zen_prices = O.Prices(b"schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\nsource: test\nprices:\n"
                          b"  opencode/gpt-6.1: {input: 1, output: 1, reasoning: 1, cache_read: 1, cache_write: 1}\n",
                          source="test")
    assert O.derive(rec, zen_prices)[0] == {"usd": Decimal(6026).scaleb(-6)}


def test_the_run_record_resolves_a_zen_model_through_the_routes_the_adapter_bound():
    """``OpenCodeAdapter._usage_record`` resolves each effective (provider, model), or the pinned one when no step
    named a model, through the routes its catalog read bound (``catalog_routes``)."""
    from types import SimpleNamespace

    def record(effective: list[dict], routes: dict) -> str:
        adapter = SimpleNamespace(
            snapshot={"session": {"tokens": {"input": 1, "output": 1, "reasoning": 0,
                                             "cache": {"read": 0, "write": 0}}},
                      "assistant": [{}], "truncated": False},
            name="opencode", token_semantics=OpenCodeAdapter.token_semantics, health={"version": "2.2.6"},
            contract=SimpleNamespace(execution_profile={"provider": "opencode", "model": "gpt-5.6-luna"}),
            _routes=routes, foreign_sessions=[])
        return OpenCodeAdapter._usage_record(adapter, effective)["token_semantics"]

    luna = {"provider": "opencode", "model": "gpt-5.6-luna", "effort": None}
    bound = {("opencode", "gpt-5.6-luna"): ZEN_RESPONSES}
    assert record([luna], bound) == record([], bound) == "disjoint"
    assert record([luna], {}) == record([], {}) == "unknown"
    assert record([{**luna, "model": "claude-haiku-5-5"}], bound) == "unknown"
