"""Scale regression for the StageIntent journal (M4-E E3; plan v3 §6, TIS-35): ended intents leave the hot state, so
nothing a Lead runs every turn grows with them, and an ended intent is read back without scanning for it.

Timing-free, like test_m3_control_plane_scale.py: `resume` and `status` run as the real CLI with ``AEW_PROFILE``, and
their counts (git subprocesses, control-state parses, commits, renders, evidence scans) must be equal on one project
with N ended stages and on one with 4N."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aewflow import create_planned_ticket, sample_project
from invariants import load_control

from aew.engine import stage_intents as SI
from aew.engine.api import Engine

COUNTED = ("git", "parse", "commit", "render", "scan")
SMALL, LARGE = 3, 12


def ended_stages(p, tmp_path: Path, n: int) -> list[str]:
    """``n`` one-step stages that completed, half on a Ticket (cold under the unit), half on the project."""
    wid = create_planned_ticket(p, tmp_path)
    out = []
    for i in range(n):
        e = Engine.discover(p.root)
        sid = e.stage_open(token=p.token, expect_rev=p.rev(), tool="probe", contract_digest="0" * 64, arguments={},
                           judgment_inputs=[], base_class="MECHANICAL", effective_class="MECHANICAL",
                           plan=[{"primitive": "checkpoint"}], subject=wid if i % 2 else None,
                           ingress="test")["intent"]
        with SI.step(sid, 1, final=True):
            e.checkpoint(token=p.token, expect_rev=p.rev(), note=f"stage {i}")
        out.append(sid)
    return out


def counts(p, tmp_path: Path, name: str) -> dict[str, dict[str, int]]:
    out = {}
    for command in (("resume", "--json"), ("status", "--json")):
        profile = tmp_path / f"{name}-{command[0]}.jsonl"
        res = p.aew(*command, env={"AEW_PROFILE": str(profile)})
        assert res.returncode == 0, res.stderr
        out[command[0]] = json.loads(profile.read_text(encoding="utf-8").splitlines()[-1]).get("counts", {})
    return out


def test_cold_intent_read_latency(tmp_path, monkeypatch):
    small = sample_project(tmp_path / "small")
    large = sample_project(tmp_path / "large")
    ended_stages(small, tmp_path / "small", SMALL)
    ended = ended_stages(large, tmp_path / "large", LARGE)
    for p in (small, large):
        assert "stage_intents" not in load_control(p.root)  # every ended stage left the hot state
    a, b = counts(small, tmp_path, "small"), counts(large, tmp_path, "large")
    growth = {f"{c}: {k}": (a[c].get(k, 0), b[c].get(k, 0)) for c in a for k in COUNTED
              if a[c].get(k, 0) != b[c].get(k, 0)}
    assert not growth, f"counts that grew with the ended stages ({SMALL} -> {LARGE}): {growth}"

    def no_scan(self, *args, **kwargs):
        pytest.fail(f"a cold intent read listed {self}")

    e = Engine.discover(large.root)
    state = e._k.store.read()  # the store's own crash recovery lists .aew; the lookup itself must not
    monkeypatch.setattr(Path, "glob", no_scan)
    monkeypatch.setattr(Path, "iterdir", no_scan)
    assert [e._stages.read(state, s)["id"] for s in (ended[0], ended[1])] == [ended[0], ended[1]]
