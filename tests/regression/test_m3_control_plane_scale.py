"""Scale regression (M3 plan §2.10; m3-performance.md): no control-plane command does per-unit work it need not do.

Timing-free and CI-safe. Every measured command runs as the real CLI with ``AEW_PROFILE``, and its deterministic
counts (git subprocesses, control-state parses, commits, view renders, evidence scans) are compared on one project
at N units and again after it grew to 4N (``tools/perf/control_plane.py`` builds it: an engine-made template plus
cloned DONE and planned Tickets). They must be equal, except where the growth is the command's own job, listed
in ``PER_UNIT`` with exactly how much it may grow. A command that spawned git, parsed or scanned per unit would
multiply them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "perf"))

import control_plane as CP  # noqa: E402

COUNTED = ("git", "parse", "commit", "render", "scan")
SMALL, LARGE = 12, 48


def open_tickets(root: Path) -> int:
    state = CP.Engine.discover(root).store.read()
    return sum(1 for u in state["work"].values() if u["kind"] == "ticket" and u["state"] not in {"DONE", "CANCELLED"})


def per_unit(added_units: int, added_open: int) -> dict[str, dict[str, int]]:
    """Growth that is the command's own job. resume reports integrity contradictions (KC §15.1) by verifying every
    unit's sealed evidence, and each open Ticket's unmet gates."""
    return {"resume": {"scan": added_units + added_open}}


def counts(runner: CP.Runner) -> dict[str, dict[str, int]]:
    return {name: runner.run(args, mutation=(name, args) in CP.MUTATIONS)[1].get("counts", {})
            for name, args in CP.READS + CP.MUTATIONS}


def test_no_command_does_per_unit_work(tmp_path):
    t = CP.build(tmp_path / "repo", SMALL)
    runner = CP.Runner(t)
    small, open_before = counts(runner), open_tickets(t.root)
    CP.grow(t.root, LARGE)
    CP.validate(t.root)
    runner.resnapshot()
    large = counts(runner)
    allowed = per_unit(LARGE - SMALL, open_tickets(t.root) - open_before)
    growth = {}
    for name in small:
        for key in COUNTED:
            a, b = small[name].get(key, 0), large[name].get(key, 0)
            if b - a != allowed.get(name, {}).get(key, 0):
                growth[f"{name}: {key}"] = (a, b)
    assert not growth, f"counts that grew with the project ({SMALL} -> {LARGE} units): {growth}"


def test_no_engine_operation_changes_the_shared_parse(tmp_path, monkeypatch):
    """The store reuses its parse of unchanged bytes and hands callers copies. Every load during a real workload (a
    Ticket through its whole lifecycle, reviews, dispatches, then every read command in-process) is checked against a
    fresh parse of the file: an operation that changed the shared parse in place would be caught at the next read."""
    import aew.engine.store as ST

    original = ST.ControlStore._load

    def checked(self):
        state = original(self)
        assert state == ST.deserialize_control(self.control_path.read_bytes(), source="check"), \
            "the store's shared parse was changed in place"
        return state

    monkeypatch.setattr(ST.ControlStore, "_load", checked)
    t = CP.make_template(tmp_path / "repo")
    eng = t.eng
    for read in (eng.status, eng.resume, eng.work_tree, eng.harness_status, lambda: eng.gate_show("T-0003")):
        read()
    assert eng.store.read()["revision"] == t.rev()
