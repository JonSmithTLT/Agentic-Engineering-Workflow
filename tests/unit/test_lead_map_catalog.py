"""The Lead's typed `map` tool's catalog row (register F15.8, the mapping series' PR A2): its schema derives from the
worker bridge's map rows and the map reads' bounds, its calls are checked against the rows, and with `maps.reads` off
the Lead's tool list, guide and system text are byte for byte what they were before the row existed."""

from __future__ import annotations

import json

import pytest

from aew.capability import store as capability_store
from aew.harness import bridge
from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.maps import query, reads, structural
from aew.surface import contract, lead_text, mcp, presentation
from aew.surface.context import NORMAL, RECOVERY, switches_for
from aew.surface.validate import AdapterInputError, check_call

MAPS_ON = frozenset({contract.MAPS})
SWITCHES = {"off": frozenset(), "messaging": frozenset({contract.MESSAGING})}
PARTS = (NORMAL, RECOVERY, "guide", "system")


def surface(switches: frozenset[str]) -> dict[str, str]:
    """The Lead's surface for ``switches``: each listing (compact JSON, ASCII escapes), the guide's core and the whole
    system text, as the pool gate renders them."""
    listings = {p: json.dumps(mcp.tools_list(p, switches), separators=(",", ":"), ensure_ascii=True)
                for p in (NORMAL, RECOVERY)}
    guide = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches)
    system = projection.lead_config(guide, push_wake=True, switches=switches)["agents"][projection.LEAD_AGENT]["system"]
    return {**listings, "guide": guide, "system": system}


def before_the_row(switches: frozenset[str]) -> dict[str, str]:
    """The same surface with the `map` row gone from the catalog, with its compact description and the core's line
    for it: the Lead's surface as it was before this row existed, rendered from today's code. So the comparison holds
    whatever else changes in the Lead's text (a pinned digest of one day's text broke on every later change to it: the
    merge with main at #592's `.env` line, CI of #654 at 85c362ff)."""
    with pytest.MonkeyPatch.context() as m:  # copies without the entry: a table's own order is never disturbed
        for module, name in ((contract, "_SWITCH_TOOLS"), (lead_text, "WHEN"), (presentation, "DESCRIPTIONS")):
            m.setattr(module, name, {k: v for k, v in getattr(module, name).items() if k != "map"})
        return surface(switches)


@pytest.fixture
def placement(monkeypatch):
    monkeypatch.setattr(capability_store, "read", lambda directory=None: capability_store.empty())


@pytest.mark.parametrize("mode", sorted(SWITCHES))
def test_the_leads_map_tool_is_absent_and_the_surface_byte_identical_when_maps_reads_is_off(mode, placement):
    """F15.8: switched off, the Lead's tool lists, guide and system text are byte for byte what they are without the
    row, with messaging off and on; even with `maps.reads` on, the row is the only change. (The off listings' bytes
    are also pinned as they stand, in `test_message_send`'s `OFF_LIST_SHA`.)"""
    off, before = surface(SWITCHES[mode]), before_the_row(SWITCHES[mode])
    assert {part: off[part] for part in PARTS} == {part: before[part] for part in PARTS}
    assert before_the_row(SWITCHES[mode] | MAPS_ON) == before  # without the row, the switch offers nothing
    assert "`map`" not in off["guide"] and '"name":"map"' not in off[NORMAL]
    on = surface(SWITCHES[mode] | MAPS_ON)
    assert "`map`" in on["guide"] and '"name":"map"' in on[NORMAL] and on != before
    # On, the row and the core's line for it are all that change: the listing is the off one plus the row.
    rows = json.loads(on[NORMAL])["tools"]
    assert [r["name"] for r in rows] == [*[r["name"] for r in json.loads(off[NORMAL])["tools"]], "map"]
    assert json.dumps({"tools": rows[:-1]}, separators=(",", ":"), ensure_ascii=True) == off[NORMAL]
    assert on["system"].removesuffix(on["guide"]) == off["system"].removesuffix(off["guide"])


@pytest.mark.parametrize("leak", ["unswitched_row", "unswitched_line"])
def test_a_map_row_or_line_offered_without_the_switch_fails_the_comparison(leak, placement, monkeypatch):
    """The comparison can fail: a `map` row registered without its switch, or a core line shown without the row,
    changes the off surface, and the off surface no longer equals the one without the row."""
    before = before_the_row(frozenset())
    if leak == "unswitched_row":
        monkeypatch.setitem(contract.TOOLS, "map", contract.catalog(MAPS_ON)["map"]._replace(switch=None))
    else:
        shown = lead_text.uses

        def uses(profile: str = NORMAL, switches: frozenset[str] = frozenset()) -> tuple:
            return (*shown(profile, switches), lead_text.guide.ToolUse("map", lead_text.WHEN["map"]))

        monkeypatch.setattr(lead_text, "uses", uses)
    assert surface(frozenset()) != before


def test_the_map_tools_arguments_are_the_bridge_rows_bounded_strings():
    """Derived, not restated: `read` names each bridge row without its prefix, the other arguments are exactly the
    rows' (plus `work_id`, the Ticket `scope: ticket` reads), every one a string, and each bounded by its owner."""
    schema = contract.catalog(MAPS_ON)["map"].input_schema
    properties = schema["properties"]
    assert properties["read"] == {"enum": [op.removeprefix("map.") for op in bridge.MAP_OPERATIONS]}
    assert set(properties) == {"read", "work_id", *(a for args in bridge.MAP_OPERATIONS.values() for a in args)}
    assert all(t is str for args in bridge.MAP_OPERATIONS.values() for t in args.values())
    for name, prop in properties.items():
        bounded = "enum" in prop or (prop.get("type") == "string" and "maxLength" in prop)
        assert bounded or "pattern" in prop and prop["pattern"].endswith("}$"), name
        assert "enum" not in prop or all(isinstance(v, str) for v in prop["enum"]), name
    assert properties["text"]["maxLength"] == reads.TEXT_MAX == query.TEXT_MAX
    assert properties["kind"]["enum"] == list(reads.KINDS) == list(query.KINDS)
    assert properties["section"]["maxLength"] == max(map(len, structural.SECTIONS))
    assert properties["scope"]["enum"] == [s for s in query.SCOPES if s]
    assert str(reads.SEARCH_LIMIT_MAX).isdigit() and len(str(reads.SEARCH_LIMIT_MAX)) == 3
    assert schema["required"] == ["read"] and schema["additionalProperties"] is False


def test_a_bridge_map_row_argument_the_tool_does_not_bound_fails_the_catalog(monkeypatch):
    """Ablation: a new argument on a worker's map row with no bound here stops the catalog from building."""
    monkeypatch.setitem(bridge.MAP_OPERATIONS, "map.search", {**bridge.MAP_OPERATIONS["map.search"], "root": str})
    with pytest.raises(ValueError, match="bridge's map rows' arguments"):
        contract._map_schema()


def test_the_map_tool_is_a_mechanical_read_offered_on_both_profiles_and_never_auto_run():
    t = contract.catalog(MAPS_ON)["map"]
    assert t.kind == contract.QUERY and t.base_class == contract.MECHANICAL and t.switch == contract.MAPS
    assert not t.mutates and not t.dispatches and not t.progression and t.expands_to == ()
    assert t.profiles == contract.BOTH and mcp.tool_entry(t)["annotations"]["readOnlyHint"] is True


@pytest.mark.parametrize(("arguments", "violation"), [
    ({"read": "search"}, "text: required for read search"),
    ({"read": "search", "text": "x", "section": "languages"}, "section: not taken by read search"),
    ({"read": "show", "text": "x"}, "text: not taken by read show"),
    ({"read": "show", "scope": "ticket"}, "work_id: required with scope ticket"),
    ({"read": "show", "work_id": "T-0001"}, "work_id: required with scope ticket"),
    ({"read": "search", "text": "x", "work_id": "T-0001"}, "work_id: not taken by read search"),
])
def test_a_map_call_with_another_reads_arguments_is_an_input_error(arguments, violation):
    with pytest.raises(AdapterInputError) as refused:
        check_call("map", arguments, NORMAL, MAPS_ON)
    violations = refused.value.details["violations"]
    assert refused.value.code == "INVALID_ARGUMENTS" and any(violation in v for v in violations)


@pytest.mark.parametrize("arguments", [
    {"read": "search", "text": "x" * (reads.TEXT_MAX + 1)}, {"read": "search", "text": "x", "limit": "1000"},
    {"read": "search", "text": "x", "limit": 5}, {"read": "search", "text": "x", "commit": "HEAD"},
    {"read": "show", "root": "0" * 64}, {"read": "outline"},
])
def test_a_map_call_outside_the_schema_never_reaches_the_runner(arguments):
    """No argument names a commit or a root, every value is a bounded string, and only the rows' reads exist."""
    with pytest.raises(AdapterInputError) as refused:
        check_call("map", arguments, NORMAL, MAPS_ON)
    assert refused.value.code == "INVALID_ARGUMENTS"


def test_the_map_tool_is_unknown_without_the_switch():
    with pytest.raises(AdapterInputError) as refused:
        check_call("map", {"read": "show"}, NORMAL, frozenset({contract.MESSAGING}))
    assert refused.value.code == "UNKNOWN_TOOL"


class _Engine:
    def __init__(self, policy, *, messaging=False):
        self.policy, self.messaging = policy, messaging

    def messaging_enabled(self):
        return self.messaging

    def execution_policy(self):
        if isinstance(self.policy, Exception):
            raise self.policy
        return self.policy, None


@pytest.mark.parametrize(("policy", "on"), [
    ({"maps": {"reads": "structural"}}, True), ({"maps": {"reads": "off"}}, False), ({"maps": {}}, False),
    (None, False), (OSError("unreadable"), False),
])
def test_the_sessions_snapshot_holds_maps_reads_exactly_when_the_adopted_policy_has_it_on(policy, on):
    for messaging in (False, True):
        got = switches_for(_Engine(policy, messaging=messaging))
        assert (contract.MAPS in got) == on and (contract.MESSAGING in got) == messaging


def test_aew_map_search_takes_its_kinds_and_limits_from_the_map_reads_owner(monkeypatch):
    """#654's review, m2: the CLI's `--kind` choices and its `--limit` help are derived from ``aew.maps.reads``, so a
    changed bound reaches the parser and its help as it reaches the tool's schema and the query module."""
    from aew.cli.main import build_parser

    monkeypatch.setattr(reads, "KINDS", ("path", "any", "planted"))
    monkeypatch.setattr(reads, "SEARCH_LIMIT", 7)
    monkeypatch.setattr(reads, "SEARCH_LIMIT_MAX", 9)
    parser = build_parser()
    search = parser._subparsers._group_actions[0].choices["map"]._subparsers._group_actions[0].choices["search"]
    options = {a.dest: a for a in search._actions}
    assert tuple(options["kind"].choices) == ("path", "any", "planted") and options["kind"].default == "path"
    assert "(default: path)" in options["kind"].help
    assert "(default 7, at most 9)" in options["limit"].help
