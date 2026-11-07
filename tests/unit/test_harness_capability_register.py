"""Each gap in the harness capability declarations names a row that exists in the register (steering design §7: a gap
is "noted as work for us to add to the AEW build of Codex", and that note is a register row)."""

from __future__ import annotations

from pathlib import Path

import yaml

from aew.harness import harness_capabilities as H

REGISTER = Path(__file__).resolve().parents[2] / "docs" / "implementation" / "future-work.yaml"


def register_ids() -> set[str]:
    data = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    rows: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "#" in node:
                rows.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return {str(r["#"]) for r in rows}


def test_every_gap_names_a_row_of_the_register():
    ids = register_ids()
    gaps = [(h, c, s.register) for h, col in H.declarations().items() for c, s in col.items() if s.status == H.GAP]
    assert gaps, "PR 0 found Codex gaps; they are recorded"
    for harness, cap, row in gaps:
        assert row in ids, f"{harness} {cap}: register row {row} does not exist"
