"""The future-work register is structured data (E30): `docs/implementation/future-work.yaml` is the source and
`future-work.md` the rendered view, kept identical by `tools/register.py`. Every row has a unique id and every open
row outside the gates and questions tables starts its target column with one of the register's own targets."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("register", ROOT / "tools" / "register.py")
assert _spec is not None and _spec.loader is not None
register = importlib.util.module_from_spec(_spec)
sys.modules["register"] = register
_spec.loader.exec_module(register)

DATA = yaml.safe_load(register.YAML.read_text(encoding="utf-8"))


def test_the_markdown_is_what_the_yaml_renders():
    assert DATA["schema"] == register.SCHEMA
    rendered = register.render_markdown(DATA)
    assert rendered == register.MD.read_text(encoding="utf-8"), (
        "docs/implementation/future-work.md is not rendered from future-work.yaml: edit the YAML and run "
        "`python tools/register.py render`")


def test_the_yaml_round_trips_through_the_markdown():
    """Parsing the rendered markdown gives back the same data, so either file could be reconstructed from the other."""
    assert register.parse_markdown(register.render_markdown(DATA)) == DATA


def test_ids_are_unique_and_open_rows_carry_a_target():
    assert register.problems(DATA) == []


def test_every_section_has_the_columns_its_rows_use():
    for section in DATA["sections"]:
        for row in section["rows"]:
            assert list(row) == section["columns"], f"§{section['number']}: {next(iter(row.values()))}"
