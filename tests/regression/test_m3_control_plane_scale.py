"""Scale regression (M3 plan §2.10; m3-performance.md): no control-plane command does per-unit work it need not do.

Timing-free and CI-safe. Every measured command runs as the real CLI with ``AEW_PROFILE``, and its deterministic
counts (git subprocesses, control-state parses, commits, view renders, evidence scans) are compared on one project
at N units and again after it grew to 4N (``tools/perf/control_plane.py`` builds it: an engine-made template plus
cloned DONE and planned Tickets). They must be equal, except where the growth is the command's own job, listed
in ``PER_UNIT`` with exactly how much it may grow. A command that spawned git, parsed or scanned per unit would
multiply them.

ADR-0011: each project is built in the M3 (v1) layout and migrated (``aew migrate``) before it is measured, since the
Lead's mutations are refused on v1. Finished work is then archived, so the commands see only the open units hot.
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


def per_unit(added_open: int) -> dict[str, dict[str, int]]:
    """Growth that is the command's own job. resume reports integrity contradictions (KC §15.1) by verifying every
    hot unit's sealed evidence, and each open Ticket's unmet gates: after the migration only open units are hot, so
    archived DONE Tickets add nothing (ADR-0011 H4)."""
    return {"resume": {"scan": 2 * added_open}}


def counts(runner: CP.Runner) -> dict[str, dict[str, int]]:
    return {name: runner.run(args, mutation=(name, args) in CP.MUTATIONS)[1].get("counts", {})
            for name, args in CP.READS + CP.MUTATIONS}


def measured(root: Path, units: int) -> tuple[dict[str, dict[str, int]], int]:
    t = CP.build(root, units)
    CP.migrate(t)
    return counts(CP.Runner(t)), open_tickets(root)


def test_no_command_does_per_unit_work(tmp_path):
    small, open_small = measured(tmp_path / "small" / "repo", SMALL)
    large, open_large = measured(tmp_path / "large" / "repo", LARGE)
    allowed = per_unit(open_large - open_small)
    growth = {}
    for name in small:
        for key in COUNTED:
            a, b = small[name].get(key, 0), large[name].get(key, 0)
            if b - a != allowed.get(name, {}).get(key, 0):
                growth[f"{name}: {key}"] = (a, b)
    assert not growth, f"counts that grew with the project ({SMALL} -> {LARGE} units): {growth}"


def test_the_footprint_attributes_every_byte_to_open_work_or_history(tmp_path):
    """The designer's metric for ADR-0011 (m3-performance.md §7): every byte of control.yaml is attributed to open
    units, to history, or to neither (the Lead, counters, structure), and each kind of unit grows only its own share.
    Timing-free: this pins the measurement, not a target."""
    t = CP.make_template(tmp_path / "repo")  # 3 open units (T-0002..T-0004), 1 completed (T-0001)
    CP.add_units(t.root, done=3, planned=2)
    before = CP.project_footprint(t.root)
    assert before["units"] == {"open": 5, "completed": 4}
    total = before["open_bytes"]["total"] + before["history_bytes"]["total"] + before["other_bytes"]
    assert total == before["control_bytes"] and 0 < before["other_bytes"] < 2048
    CP.add_units(t.root, done=5, planned=0)
    history = CP.project_footprint(t.root)
    assert history["open_bytes"] == before["open_bytes"]
    assert 0 <= history["other_bytes"] - before["other_bytes"] <= 16  # only the counters' digits
    grown = history["history_bytes"]["total"] - before["history_bytes"]["total"]
    assert grown == 5 * before["per_completed_unit_bytes"]
    CP.add_units(t.root, done=0, planned=4)
    active = CP.project_footprint(t.root)
    assert active["history_bytes"] == history["history_bytes"] and active["units"] == {"open": 9, "completed": 9}
    assert active["live_bytes"] > history["live_bytes"]


def test_after_migration_the_hot_state_holds_history_only_as_aggregates(tmp_path):
    """ADR-0011 H1, timing-free, on the scale-regression project: along the history series (20 open Tickets), four
    times the history leaves the hot state at most 1.25x its size, and history is at most 20% of it; the history is
    in the cold store. (H1's own points, 250 and 3,000 completed, are measured in P3: the property is the same, and
    a 3,000-unit migration takes minutes.)"""
    points = {}
    for completed in (250, 1000):
        t = CP.make_template(tmp_path / str(completed) / "repo")  # 3 open, 1 completed
        CP.add_units(t.root, done=completed - 1, planned=17)
        v1 = CP.project_footprint(t.root)
        assert v1["units"] == {"open": 20, "completed": completed} and v1["cold_bytes"] == 0
        CP.migrate(t)
        # ADR-0012 (D1 review, process note): the migration is a mass transition. Its events exceed the hot bound,
        # go to an overflow sidecar, and the log returns the complete set.
        engine = CP.Engine.discover(t.root)
        last = engine.store.read()["last_transition"]
        assert last["op"] == "migrate" and last["event_overflow"]["event_count"] > 64
        assert len(last["events"]) == 64 and (t.root / ".aew" / last["event_overflow"]["path"]).is_file()
        [migration] = engine.history_log(since=last["revision"] - 1)["transitions"]
        assert len(migration["events"]) == last["event_overflow"]["event_count"]
        hot = points[completed] = CP.project_footprint(t.root)
        assert hot["units"] == {"open": 20, "completed": 0}
        assert hot["open_bytes"] == v1["open_bytes"]  # open work is untouched
        assert hot["history_bytes"]["units"] == 0 and hot["history_bytes"]["invocations"] == 0
        assert hot["history_bytes"]["total"] <= 0.20 * hot["control_bytes"], hot["history_bytes"]
        assert hot["cold_bytes"] >= v1["history_bytes"]["units"]  # every finished record went to the cold store
    assert points[1000]["control_bytes"] <= 1.25 * points[250]["control_bytes"], \
        (points[250]["control_bytes"], points[1000]["control_bytes"])


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
