"""`tools/pricing_table.py`: the bundled table's generator (register F25, plan U2)."""

from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from pathlib import Path

import pytest

from aew.engine import usage_ops as O
from aew.errors import ValidationFailed
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


def test_the_bundled_table_is_what_the_generator_writes_from_the_saved_catalog():
    """A hand-edited price, or a removed base-tier mark, fails here: the table is the catalog's, byte for byte."""
    saved = json.loads(T.SAVED.read_text(encoding="utf-8"))
    bundled = O.Prices(T.OUT.read_bytes(), source=str(T.OUT)).table
    as_of = saved.pop("as_of")
    assert T.render(saved, as_of) == T.OUT.read_bytes()  # a hand-bumped date fails too
    assert T.CATALOG_URL in bundled["source"] and "list prices" in bundled["source"]
    assert hashlib.sha256(T.SAVED.read_bytes()).hexdigest() in bundled["source"]  # names the catalog it came from


def test_a_catalog_missing_a_declared_provider_writes_nothing():
    with pytest.raises(KeyError):
        T.build({"openai": {"models": {}}}, "2026-11-08")


def test_the_generator_refuses_a_bad_date_before_writing_anything(tmp_path, monkeypatch):
    out, saved = tmp_path / "table.yaml", tmp_path / "catalog.json"
    monkeypatch.setattr(T, "OUT", out)
    monkeypatch.setattr(T, "SAVED", saved)
    catalog = tmp_path / "models.json"
    catalog.write_text(json.dumps(CATALOG), encoding="utf-8")
    with pytest.raises(ValidationFailed):
        T.main(["--catalog", str(catalog), "--as-of", "soon"])
    assert not out.exists() and not saved.exists()


def test_the_bundled_table_ships_in_the_package():
    """`aew init` reads it from the installed package: a wheel without this line has no table, and init fails."""
    root = Path(__file__).resolve().parents[2]
    package_data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
    package = T.OUT.parent.relative_to(root / "src").as_posix().replace("/", ".")
    assert T.OUT.name in package_data["package-data"][package]
