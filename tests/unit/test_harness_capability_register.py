"""Each gap in the harness capability declarations names a row that exists in the register (steering design §7: a gap
is "noted as work for us to add to the AEW build of Codex", and that note is a register row)."""

from __future__ import annotations

from pathlib import Path

import yaml

from aew.harness import harness_capabilities as H

REGISTER = Path(__file__).resolve().parents[2] / "docs" / "implementation" / "future-work.yaml"


def register_ids(*, open_only: bool) -> set[str]:
    """The register's row ids, read as `tools/register.py`'s `rows` reads them: an open row is one outside the
    `Closed` sections."""
    data = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    return {str(row["#"]) for section in data["sections"]
            if not (open_only and section["title"].startswith("Closed"))
            for row in section["rows"] if "#" in row}


def test_every_gap_names_an_open_row_of_the_register():
    """A gap's row holds the work: it must exist, and be open (a closed row holds nothing)."""
    ids = register_ids(open_only=True)
    gaps = [(h, c, s.register) for h, col in H.declarations().items() for c, s in col.items() if s.status == H.GAP]
    assert gaps, "PR 0 found Codex gaps; they are recorded"
    for harness, cap, row in gaps:
        assert row in ids, f"{harness} {cap}: register row {row} is not an open row of the register"


def test_a_closed_row_is_not_an_open_row():  # the control of the case above
    closed = register_ids(open_only=False) - register_ids(open_only=True)
    assert closed, "the register has closed rows"
    assert not closed & register_ids(open_only=True)
