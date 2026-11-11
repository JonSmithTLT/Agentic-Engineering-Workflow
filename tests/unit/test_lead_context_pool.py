"""E231's offline byte ceiling for the contained OpenCode Lead."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import date
from pathlib import Path

import pytest

from aew.capability import ops as capability
from aew.capability import store as capability_store
from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import contract, lead_text, mcp
from aew.surface.context import NORMAL
from aew.util import load_yaml

RECORD_PATH = "docs/implementation/lead-context-pool.yaml"
RECORD = Path(__file__).resolve().parents[2] / RECORD_PATH
MESSAGING_ON = frozenset({contract.MESSAGING})
# TLS-21 as amended by LEAD-CONTEXT-BUDGET-2026-11-10 retains the offered-tool ceiling.
TOOL_LIMIT = 16


@dataclass(frozen=True)
class Pool:
    system_bytes: int
    guide_bytes: int
    join_bytes: int
    mcp_bytes: int

    @property
    def total(self) -> int:
        return self.system_bytes + self.guide_bytes + self.join_bytes + self.mcp_bytes


def read_baseline(record: dict) -> Pool:
    assert record["schema"] == "aew/lead-context-pool/v1"
    baseline = record["baseline"]
    assert baseline["push_wake"] is True and baseline["switches"] == sorted(MESSAGING_ON)
    parts = {part.name: baseline[part.name] for part in fields(Pool)}
    assert all(type(part) is int and part > 0 for part in parts.values()), "invalid baseline byte count"
    return Pool(**parts)


def operator_count(entry: object, name: str, count_key: str) -> int:
    location = f"{RECORD_PATH} {name}"
    assert isinstance(entry, dict) and set(entry) == {count_key, "operator", "date"}, (
        f"{location} requires exactly {count_key}, operator, and date"
    )
    count = entry[count_key]
    assert type(count) is int and count > 0, f"{location}.{count_key} must be a positive byte count"
    assert isinstance(entry["operator"], str) and entry["operator"].strip(), f"{location} requires the operator's words"
    quoted_date = entry["date"]
    try:
        valid_date = isinstance(quoted_date, str) and date.fromisoformat(quoted_date).isoformat() == quoted_date
    except ValueError:
        valid_date = False
    assert valid_date, f"{location}.date must be a quoted ISO date"
    return count


def approved_ceiling(record: dict) -> int:
    """Validate the derived ceiling against the operator's cap and return that cap."""
    baseline = read_baseline(record)
    allocations = record["allocations"]
    # These names are operator-approved. A new name needs an operator decision recorded with the allocation.
    assert set(allocations) == {"E158", "E160", "E162", "messaging_guide_line", "E176"}
    for name, entry in allocations.items():
        assert type(entry["bytes"]) is int, name
        assert entry["kind"] in {"estimate", "measured"} and entry["source"].strip(), name
        assert entry["kind"] != "estimate" or entry["bytes"] > 0, name
    ceiling = baseline.total + sum(entry["bytes"] for entry in allocations.values())
    assert ceiling > 0, "the context pool needs a positive ceiling"
    cap = operator_count(record.get("approval"), "approval", "ceiling_bytes")
    if "wip_allowance" in record:
        cap = operator_count(record["wip_allowance"], "wip_allowance", "count")
        assert cap > ceiling, (
            f"{RECORD_PATH} wip_allowance.count ({cap} B) must exceed the derived ceiling ({ceiling} B). "
            "Retire the overtaken raise or record a new operator-approved wip_allowance."
        )
    assert ceiling <= cap, (
        f"{RECORD_PATH} baseline plus allocations ({ceiling} B) exceed the operator's {cap} B cap. "
        "Correct the recorded bytes or record the operator's raise in wip_allowance."
    )
    return cap


def render_pool(label: dict, switches: frozenset[str]) -> Pool:
    tools = capability.placed(label, contained=True)
    assert tools["tools"], "the fixture must exercise the placed-tool line"
    guide = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches)
    config = projection.lead_config(guide, contained=label, tools=tools, push_wake=True)
    full = config["agents"][projection.LEAD_AGENT]["system"]
    system = full.removesuffix("\n\n" + guide)
    assert system != full, "lead_config must append the guide with its separator"
    listing = mcp.tools_list(NORMAL, switches=switches)
    system_bytes = len(system.encode("utf-8"))
    guide_bytes = len(guide.encode("utf-8"))
    join_bytes = len(full.encode("utf-8")) - system_bytes - guide_bytes
    return Pool(system_bytes, guide_bytes, join_bytes, mcp.advertised_bytes(listing))


def component_changes(pool: Pool, baseline: Pool) -> str:
    previous = asdict(baseline)
    return ", ".join(
        f"{name.removesuffix('_bytes')} {value} B ({value - previous[name]:+d} B from baseline)"
        for name, value in asdict(pool).items() if value != previous[name]
    ) or "all components match baseline"


def check_pool(pool: Pool, record: dict, *, switches: frozenset[str]) -> None:
    cap = approved_ceiling(record)
    assert pool.total <= cap, (
        f"Lead context pool uses {pool.total} B, {pool.total - cap} B over its {cap} B cap "
        f"({component_changes(pool, read_baseline(record))}). "
        f"In {RECORD_PATH}, record the landed item's measured delta or the operator's wip_allowance."
    )
    if switches == MESSAGING_ON:
        remaining = sum(entry["bytes"] for entry in record["allocations"].values() if entry["kind"] == "estimate")
        slack = cap - pool.total
        assert slack <= remaining, (
            f"Lead context pool uses {pool.total} B under its {cap} B cap, leaving {slack} B of slack "
            f"for {remaining} B of estimates ({component_changes(pool, read_baseline(record))}). "
            f"Account for the {slack - remaining} B saving in {RECORD_PATH} baseline and lower the recorded cap."
        )


@pytest.fixture
def record() -> dict:
    return load_yaml(RECORD.read_text(encoding="utf-8"), source=str(RECORD))


@pytest.fixture
def host_independent_placement(monkeypatch):
    monkeypatch.setattr(capability_store, "read", lambda directory=None: capability_store.empty())


@pytest.mark.parametrize("switches", [MESSAGING_ON, frozenset()], ids=["messaging-on", "messaging-off"])
def test_the_contained_normal_lead_fits_its_context_pool(record, switches, host_independent_placement):
    pool = render_pool(record["baseline"]["containment"], switches)
    check_pool(pool, record, switches=switches)


def check_tool_count(count: int) -> None:
    assert count <= TOOL_LIMIT, f"normal surface offers {count} tools (limit {TOOL_LIMIT})"


@pytest.mark.parametrize("switches", [MESSAGING_ON, frozenset()], ids=["messaging-on", "messaging-off"])
def test_the_normal_surface_stays_within_the_offered_tool_limit(switches):
    listing = mcp.tools_list(NORMAL, switches=switches)
    assert ("message_send" in {tool["name"] for tool in listing["tools"]}) == bool(switches)
    check_tool_count(len(listing["tools"]))


@pytest.mark.parametrize("part", ["system_bytes", "guide_bytes", "join_bytes", "mcp_bytes"])
def test_each_component_can_exhaust_the_pool(record, part):
    cap = approved_ceiling(record)
    baseline = read_baseline(record)
    name = part.removesuffix("_bytes")
    at_limit = replace(baseline, **{part: getattr(baseline, part) + cap - baseline.total})
    check_pool(at_limit, record, switches=MESSAGING_ON)
    grown = getattr(at_limit, part) + 1
    message = rf"1 B over its {cap} B cap .*{name} {grown} B.*{RECORD_PATH}.*wip_allowance"
    with pytest.raises(AssertionError, match=message):
        check_pool(replace(at_limit, **{part: grown}), record, switches=MESSAGING_ON)


def test_a_smaller_rendered_guide_requires_a_lower_baseline_and_cap(record, monkeypatch, host_independent_placement):
    label = record["baseline"]["containment"]
    original = render_pool(label, MESSAGING_ON)
    # Start at the floor so guide growth since the recorded baseline cannot absorb the saving.
    record["baseline"].update(asdict(original))
    record["approval"]["ceiling_bytes"] = original.total + sum(
        entry["bytes"] for entry in record["allocations"].values() if entry["kind"] == "estimate"
    )
    cap = approved_ceiling(record)
    name, meaning, _example = lead_text.guide.CLASS_TEXT["0"]
    monkeypatch.setitem(lead_text.guide.CLASS_TEXT, "0", (name, meaning, "x"))
    smaller = render_pool(label, MESSAGING_ON)
    freed = original.guide_bytes - smaller.guide_bytes
    assert freed > 0 and smaller.total == original.total - freed
    message = rf"{cap} B cap.*guide {smaller.guide_bytes} B.*{freed} B saving.*{RECORD_PATH}"
    with pytest.raises(AssertionError, match=message):
        check_pool(smaller, record, switches=MESSAGING_ON)
    check_pool(render_pool(label, frozenset()), record, switches=frozenset())
    record["baseline"]["guide_bytes"] = smaller.guide_bytes
    with pytest.raises(AssertionError, match=rf"{cap} B cap.*{freed} B saving.*{RECORD_PATH}"):
        check_pool(smaller, record, switches=MESSAGING_ON)
    record["approval"]["ceiling_bytes"] -= freed
    check_pool(smaller, record, switches=MESSAGING_ON)


def test_one_tool_over_the_count_limit_fails_independently_of_bytes():
    check_tool_count(TOOL_LIMIT)
    with pytest.raises(AssertionError, match=f"{TOOL_LIMIT + 1} tools"):
        check_tool_count(TOOL_LIMIT + 1)


@pytest.mark.parametrize(("change", "message"), [
    ({"operator": " "}, "requires the operator's words"),
    ({"count": True}, "positive byte count"),
    ({"date": "11/11/2026"}, "quoted ISO date"),
    ({"date": load_yaml("date: 2026-11-11")["date"]}, "quoted ISO date"),
    ({"count": 0}, "positive byte count"),
    ({"extra": "value"}, "requires exactly"),
])
@pytest.mark.parametrize(("name", "count_key"), [("approval", "ceiling_bytes"), ("wip_allowance", "count")])
def test_operator_records_require_the_exact_shape(record, change, message, name, count_key):
    original = approved_ceiling(record)
    record[name] = {count_key: original + (name == "wip_allowance"), "operator": "Synthetic decision",
                    "date": "2026-11-11"}
    assert approved_ceiling(record) == record[name][count_key]
    record[name].update({count_key if key == "count" else key: value for key, value in change.items()})
    with pytest.raises(AssertionError, match=rf"{RECORD_PATH} {name}.*{message}"):
        approved_ceiling(record)


def test_a_raise_requires_every_key(record):
    record["wip_allowance"] = {"count": approved_ceiling(record) + 1, "operator": "Synthetic decision"}
    with pytest.raises(AssertionError, match="wip_allowance requires exactly"):
        approved_ceiling(record)


@pytest.mark.parametrize("additional", [0, 1], ids=["equal", "overtaken"])
def test_an_overtaken_raise_names_both_figures(record, additional):
    original = approved_ceiling(record)
    cap = original + 1
    record["wip_allowance"] = {"count": cap, "operator": "Synthetic decision", "date": "2026-11-11"}
    assert approved_ceiling(record) == cap
    record["baseline"]["guide_bytes"] += 1 + additional
    with pytest.raises(AssertionError, match=rf"wip_allowance.count .*{cap} B.*derived ceiling .*{cap + additional} B"):
        approved_ceiling(record)


@pytest.mark.parametrize("change", ["estimate", "measured", "approval"])
def test_baseline_plus_allocations_cannot_raise_the_operator_cap(record, change):
    if change == "approval":
        record["approval"]["ceiling_bytes"] = 1
    else:
        record["allocations"]["E176"].update(bytes=23_000, kind=change)
    cap = record["approval"]["ceiling_bytes"]
    with pytest.raises(AssertionError, match=rf"{RECORD_PATH}.*{cap} B cap.*wip_allowance"):
        approved_ceiling(record)
