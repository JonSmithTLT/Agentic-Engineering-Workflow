"""`tools/pricing_table.py`: the bundled table's generator (register F25, plan U2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aew.engine import usage_ops as O
from aew.util import dump_yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import pricing_table as T  # noqa: E402  (tools/ is not a package; the path is set just above)

TIER = {"tier": {"type": "context", "size": 272000}, "input": 9, "output": 9}
CATALOG = {
    "openai": {"models": {
        "tiered": {"cost": {"input": 1, "output": 2, "cache_read": 0.1, "tiers": [TIER]}},
        "flat": {"cost": {"input": 1, "output": 2}},
        "no-cost": {},
    }},
    "opencode": {"models": {
        "responses": {"cost": {"input": 3, "output": 4}, "provider": {"npm": "@ai-sdk/openai"}},
        "anthropic-route": {"cost": {"input": 3, "output": 4}, "provider": {"npm": "@ai-sdk/anthropic"}},
    }},
    "other": {"models": {"m": {"cost": {"input": 1, "output": 1}}}},
}


def test_the_generator_writes_only_measured_routes_at_base_rates_and_marks_tiered_models():
    table = T.build(CATALOG, "2026-11-08")
    assert set(table["prices"]) == {"openai/tiered", "openai/flat", "opencode/responses"}
    assert table["prices"]["openai/tiered"] == {"input": 1, "output": 2, "cache_read": 0.1, "reasoning": 2}
    assert table["base_tier_only"] == {"openai/tiered": {"above_context_tokens": 272000}}


def test_the_generators_table_is_one_the_ledger_accepts():
    O.Prices(dump_yaml(T.build(CATALOG, "2026-11-08")).encode("utf-8"), source="t")


def test_the_bundled_table_is_what_the_generator_writes_in_shape():
    bundled = O.Prices(T.OUT.read_bytes(), source=str(T.OUT)).table
    assert bundled["schema"] == "aew/pricing/v1" and T.CATALOG_URL in bundled["source"]
    with pytest.raises(KeyError):
        T.build({"openai": {"models": {}}}, "2026-11-08")  # a catalog missing a declared provider is not half-written
