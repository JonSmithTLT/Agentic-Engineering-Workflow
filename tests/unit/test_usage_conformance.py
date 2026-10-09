"""The OpenCode adapter's token-semantics mapping, pinned against the qualified harness version (F25, the cost and
usage ledger design v0.2 R4 rule 1 and §7 slice 1: "the adapter's token_semantics mapping pinned against the 2.0.18
OpenAPI fixture in the harness conformance suite").

The one qualified pair is OpenCode 2.0.18 with ``openai``, from OpenCode's source (the fixture cites tag, commit and
lines). Every other provider, and every other version, resolves to ``unknown``, which is never priced."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from aew.engine import usage_ops as O
from aew.harness import usage as U
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.harness.opencode.capabilities import TESTED_VERSIONS

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "opencode" / "usage-2.0.18-openai.json")
                     .read_text(encoding="utf-8"))
UNIT_PRICES = O.Prices(b"schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\nsource: test\nprices:\n"
                       b"  openai/gpt-6.1: {input: 1, output: 1, reasoning: 1, cache_read: 1, cache_write: 1}\n",
                       source="test")


def declared(version: str, provider: str) -> str:
    return U.resolve_semantics(OpenCodeAdapter.token_semantics, version, [provider])


def test_the_mapping_names_only_the_qualified_version_and_provider():
    assert FIXTURE["version"] in TESTED_VERSIONS
    assert {v: dict(m) for v, m in OpenCodeAdapter.token_semantics.items()} == {"2.0.18": {"openai": "disjoint"}}
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
