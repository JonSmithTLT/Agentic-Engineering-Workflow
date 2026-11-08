"""`aew init` writes the bundled price table (register F25, plan U2): a new project's runs on a qualified route get a
cost, an unqualified route stays unpriced, and the table says how old it is."""

from __future__ import annotations

from pathlib import Path

from aew.engine import usage_ops as O
from aew.harness import usage as U
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.util import load_yaml

TABLE = Path(O.__file__).resolve().parent.parent / "policy" / "default_pricing.yaml"


def bundled() -> O.Prices:
    return O.Prices(TABLE.read_bytes(), source=str(TABLE))


def test_init_puts_the_bundled_price_table_in_force_and_says_how_old_it_is(project):
    aew_root = project.root / ".aew"
    assert (aew_root / "policy" / "pricing.yaml").read_bytes() == TABLE.read_bytes()
    assert load_yaml((aew_root / "project.yaml").read_text(encoding="utf-8"), source="m")["policy"]["pricing"]
    view = project.ok("usage", "show", "--json")
    assert view["basis"]["current_table"]["as_of"] == bundled().table["as_of"]
    assert view["basis"]["current_table"]["sha256"] == bundled().sha256


def test_the_report_names_the_tables_source_and_says_these_are_list_prices(project):
    """The design's amendment of 2026-11-08 rests on this: a report names its source and its kind of rate."""
    text = project.aew("usage", "show").stdout
    assert bundled().table["source"] in text
    assert "list prices" in text and "not a contract's or a gateway's rate" in text


def test_every_row_of_the_bundled_table_is_on_a_provider_the_adapter_declares_semantics_for():
    table = bundled().table
    declared = {p for by_provider in OpenCodeAdapter.token_semantics.values() for p in by_provider}
    assert table["prices"] and {key.split("/", 1)[0] for key in table["prices"]} <= declared
    assert set(table["base_tier_only"]) <= set(table["prices"])


def test_every_row_of_the_bundled_table_prices_reasoning_so_disjoint_counters_are_not_unpriced():
    assert all(row["reasoning"] == row["output"] for row in bundled().table["prices"].values())


def _record(provider: str, model: str, semantics: str) -> dict:
    return U.normalize({"tokens": {"input": 1_000_000, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}},
                       [{}], [{"provider": provider, "model": model, "effort": None}], semantics,
                       source="harness:opencode")


def test_a_qualified_provider_gets_a_cost_from_the_bundled_table_and_an_unmeasured_route_stays_unpriced():
    prices = bundled()
    provider, model = next(k for k in prices.table["prices"] if k not in prices.table["base_tier_only"]).split("/", 1)
    figure, _ = O.derive(_record(provider, model, U.DISJOINT), prices)
    assert figure["usd"] > 0 and "floor" not in figure
    assert O.derive(_record(provider, model, U.UNKNOWN), prices)[0] == {"unpriced": O.UNPRICED_SEMANTICS_UNKNOWN}


def test_a_model_with_context_tiers_reads_as_a_floor_under_the_bundled_table():
    prices = bundled()
    key = next(iter(prices.table["base_tier_only"]))
    figure, _ = O.derive(_record(*key.split("/", 1), U.DISJOINT), prices)
    assert figure["floor"] is True and "at least $" in O._row_figure(figure)
