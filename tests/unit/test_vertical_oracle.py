"""V-01's acceptance oracle (``tests/helpers/vertical/oracle.py``): row V01-01's 13 steps, each step's state derived
from the code's own registries, no proposed name on the path, and each scenario's PIN budget derived from its path.

The vertical check itself is red on ``main`` by design (designer V-UAT-4) until its steps turn green; these tests hold
the derivation, not the states."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from vertical import oracle as O


def test_the_path_is_row_v01_01s_13_steps_each_with_its_derived_state():
    """Run with ``-s`` for the report: each step's state at this commit, its parts' and what holds it."""
    records = O.derive()
    assert [r["step"] for r in records] == list(range(1, 14)) == [s.n for s in O.STEPS]
    assert len({s.key for s in O.STEPS}) == 13
    for step, r in zip(O.STEPS, records, strict=True):
        assert step.catalog and step.serves or step.key == "configure", step
        assert {i.catalog for i in step.serves} <= set(step.catalog), step
        assert r["state"] in O.RANK and all(p["state"] in O.RANK for p in r["parts"])
        assert r["state"] == min((p["state"] for p in r["parts"]), key=O.RANK.__getitem__, default=O.NOT_BUILT)
        assert ("held_by" in r) == bool(step.held_by and not O.landed(r["state"])), r
    print("\n" + "\n".join(f"{r['step']:>2} {r['key']:<10} {r['state']:<16} {', '.join(r.get('held_by', []))}  "
                           + "; ".join(f"{p.get('action') or p.get('route') or p.get('act')}: {p['state']}"
                                       for p in r["parts"]) for r in records))


def _facts(**changes):
    return O.code_facts()._replace(**changes)


def test_an_unbuilt_surface_reports_not_built_with_what_holds_it():
    """Planted: with nothing in the registry and nothing served, every wire and read step is "not built" and names
    the row's holders; the steps the row holds by nothing name none."""
    empty = _facts(registry={}, served=frozenset())
    by_key = {r["key"]: r for r in O.derive(facts=empty)}
    assert by_key["setting"]["state"] == O.NOT_BUILT and by_key["setting"]["held_by"] == ["G3"]
    assert by_key["publish"]["held_by"] == ["G3", "I4-06", "I4-B7"]
    assert by_key["reopen"]["state"] == O.NOT_BUILT and by_key["reopen"]["held_by"] == ["G3"]
    assert by_key["preflight"]["state"] == O.NOT_BUILT and "held_by" not in by_key["preflight"]
    # A step with no serving surface at all (configure, A-39's console setup act) is not built, never built.
    assert by_key["configure"]["state"] == O.NOT_BUILT and by_key["configure"]["parts"][0]["act"] == "NO_COMMAND"
    # Without the CLI's command, the local step is not built either; the harness's own exit stays outside AEW.
    bare = {r["key"]: r for r in O.derive(facts=_facts(commands=frozenset()))}
    assert bare["init"]["state"] == O.NOT_BUILT and bare["exit"]["state"] == O.OUTSIDE


def test_a_step_moves_when_its_registry_entry_or_route_is_added():
    """Planted: an action added to a fixture registry moves its step with no edit to the path; so does a route the
    server's dispatch starts to serve, read from the server's own source by the reference's reader."""
    facts = O.code_facts()
    assert O.state_of("setting", facts)["state"] == O.NOT_BUILT
    registered = _facts(registry={**facts.registry, "ADOPT_MANIFEST_EDIT": O.G3})
    assert O.state_of("setting", registered)["state"] == O.REGISTRY_ONLY
    assert O.state_of("setting", registered)["held_by"] == ["G3"]
    admitted = _facts(registry={**facts.registry, "ADOPT_MANIFEST_EDIT": facts.admitted_origin})
    assert O.state_of("setting", admitted)["state"] == O.ADMITTED
    reached = _facts(registry={**facts.registry, "ADOPT_MANIFEST_EDIT": facts.admitted_origin},
                     owner_action="ADOPT_MANIFEST_EDIT")
    assert O.state_of("setting", reached) == {"step": 12, "key": "setting", "catalog": ["P04", "P14"],
                                              "state": O.REACHES_OWNER, "parts": [
                                                  {"catalog": "P14", "action": "ADOPT_MANIFEST_EDIT",
                                                   "state": O.REACHES_OWNER}]}

    from aew.stg02 import server

    _, reader = O.readers()
    source = inspect.getsource(server)
    anchor = 'if path == "/v1/read/waiting":'
    assert source.count(anchor) == 1
    planted = source.replace(anchor, 'if path == "/v1/read/capabilities" or path == "/v1/read/waiting":')
    served = reader.tie(sorted(facts.routes), reader.read(ast.parse(planted), vars(server))).served
    assert O.state_of("preflight", facts)["state"] == O.NOT_BUILT
    moved = O.state_of("preflight", _facts(served=frozenset(served)))
    assert moved["state"] == O.SERVED and "held_by" not in moved


def test_a_proposed_name_on_the_path_fails():
    """Planted: the frozen path's proposed names (`aew settings set`, `aew preflight`), a route outside the vendored
    D-01 matrix and an action no adoption places each fail; today's path has none."""
    assert O.proposed_names() == []
    planted = (O.Step(2, "configure", O._s("all"), ("L10",), (O.Local("L10", None, ("settings", "set")),), ()),
               O.Step(11, "preflight", O._s("V3"), ("P03",), (O.Local("P03", None, ("preflight",)),
                                                               O.Read("P03", "/v1/read/preflight")), ()),
               O.Step(12, "setting", O._s("V4"), ("P04",), (O.Wire("P04", "SETTINGS_SET", O.G3, "proposed"),), ()))
    found = O.proposed_names(planted)
    assert found == ["step 2 (configure): `aew settings set` is no command of the CLI",
                     "step 11 (preflight): `aew preflight` is no command of the CLI",
                     "step 11 (preflight): /v1/read/preflight is no route of the vendored D-01 matrix",
                     "step 12 (setting): SETTINGS_SET is neither in the O-01 registry nor placed by an adoption"]
    # Missing: a step that names nothing proposes nothing (configure has no serving surface yet).
    assert O.proposed_names([O.STEP["configure"]]) == []
    # A switched command is a command of the CLI: the parser is built with both switches on (review of #306, N3).
    switched = O.Step(14, "recall", O._s("V1"), ("X01",), (O.Local("X01", None, ("history", "search")),), ())
    assert O.proposed_names([switched]) == []


def test_each_registered_action_has_the_origin_the_row_gives_it():
    """The path is pinned against the live registry: each of its actions the registry carries has the row's origin;
    a fixture registry that disagrees is named; an action the registry does not carry is not compared."""
    facts = O.code_facts()
    assert O.registry_disagreements() == []
    on_path = {i.action for s in O.STEPS for i in s.serves if isinstance(i, O.Wire)}
    assert on_path & set(facts.registry) == {"ATTACH_LEAD", "REATTACH_LEAD", "CONTINUE_ELIGIBLE_WORK"}
    wrong = _facts(registry={**facts.registry, "ATTACH_LEAD": O.DELEGATED})
    assert O.registry_disagreements(facts=wrong) == [
        "step 3 (open): ATTACH_LEAD is PROTECTED_G3 on the path and CURRENT_DELEGATED_GRANT in the registry"]
    assert O.registry_disagreements(facts=_facts(registry={})) == []


def test_the_derivation_stops_when_the_carriers_admission_cannot_be_read(monkeypatch):
    """Missing: a carrier whose admission the reference's reader cannot find stops the derivation, never guesses a
    state."""
    real_commands, real_server = O.readers()
    blind = SimpleNamespace(read=lambda tree: real_commands.read(tree)._replace(origin=None))
    monkeypatch.setattr(O, "readers", lambda: (blind, real_server))
    O.code_facts.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="cannot derive the wire states"):
            O.code_facts()
        # A server dispatch string the reader cannot tie to a route of the matrix stops it too (review of #306, N5).
        from aew.stg02 import server

        planted = inspect.getsource(server).replace('if path == "/v1/read/waiting":',
                                                    'if path == "/v1/read/bogus" or path == "/v1/read/waiting":')
        untied = SimpleNamespace(read=lambda tree, values: real_server.read(ast.parse(planted), values),
                                 tie=real_server.tie)
        monkeypatch.setattr(O, "readers", lambda: (real_commands, untied))
        O.code_facts.cache_clear()
        with pytest.raises(RuntimeError, match="/v1/read/bogus"):
            O.code_facts()
    finally:
        O.code_facts.cache_clear()
    monkeypatch.undo()
    assert O.code_facts().served  # the real tree ties every string


def test_a_step_taken_todays_way_is_a_fallback_until_it_lands_and_then_has_no_driver(monkeypatch):
    """The scripted operator takes a step that has not landed today's way, a fallback whose evidence is the step's
    citation and derived state; once the step lands, the same workaround is `no_driver`, which fails the verdict."""
    from vertical import ledger as L
    from vertical import scripted_operator as S

    op = S.Operator.__new__(S.Operator)
    op.ledger = L.Ledger("unit")
    op.workaround("setting", "edit execution.yaml; aew manifest adopt", step="change_model")
    (fallback,) = op.ledger.operator_fallbacks()
    assert fallback["step"] == "change_model" and fallback["ideal"] == "step 12 (P14 ADOPT_MANIFEST_EDIT)"
    assert fallback["observed"] == "not built, held by G3"
    op.workaround("configure", "edit the policy files")
    assert op.ledger.operator_fallbacks()[-1]["ideal"] == "step 2 (L10 NO_COMMAND)"
    landed = _facts(registry={**O.code_facts().registry, "ADOPT_MANIFEST_EDIT": O.code_facts().admitted_origin},
                    owner_action="ADOPT_MANIFEST_EDIT")
    monkeypatch.setattr(O, "code_facts", lambda: landed)
    op.workaround("setting", "edit execution.yaml; aew manifest adopt", step="change_model")
    assert len(op.ledger.operator_fallbacks()) == 2
    (missing,) = [o for o in op.ledger.observations if o["kind"] == "no_driver"]
    assert (missing["oracle_step"], missing["state"]) == (12, O.REACHES_OWNER)


def test_each_scenarios_pin_budget_is_derived_from_its_path():
    """The operator's decision of 2026-10-24 (F1), with the matrix's budgets since A-39: V1 3, V2 4, V3 0 or 1 (open,
    if its path gets that far), V4 4, plus 1 per raise, and a raise after each open and reopen (the designer's ruling
    of 2026-10-30): with steering on V1 4, V2 6, V4 5. Derived from the path: these are what the derivation gives, not
    inputs."""
    budgets = {sc: O.pin_budget(O.path(sc)) for sc in O.INHERITS}
    assert budgets == {"V1": 3, "V2": 4, "V3": 0, "V4": 4}
    assert O.pin_budget(O.path("V3", also=("open",))) == 1
    assert {sc: O.pin_budget(O.path(sc, steering=True)) for sc in ("V1", "V2", "V4")} == {"V1": 4, "V2": 6, "V4": 5}
    keys = [s.key for s in O.path("V2", steering=True)]
    assert keys.count("raise") == 2 and keys[keys.index("open") + 1] == "raise" == keys[keys.index("reopen") + 1]
    assert "raise" not in [s.key for s in O.path("V2")] + [s.key for s in O.path("V3", steering=True)]
    assert [s.key for s in O.path("V1") if O.g3_protected(s)] == ["open", "plan", "publish"]
    assert [s.key for s in O.path("V4") if O.g3_protected(s)] == ["open", "plan", "publish", "setting"]
    assert "configure" in {s.key for s in O.path("V1")} and not O.g3_protected(O.STEP["configure"])  # A-39: no PIN


ROOT = Path(__file__).resolve().parents[2]
# Where the scripted operator takes the path's steps: the acceptance module and the operator's own helper.
TAKERS = (ROOT / "tests" / "acceptance" / "test_vertical_path.py",
          ROOT / "tests" / "helpers" / "vertical" / "scripted_operator.py")


def workaround_keys(sources: list[str]) -> set[str]:
    """The step keys passed to ``.workaround(`` in ``sources``: a string literal, or either branch of a conditional.
    Static: a key passed in a variable, or a call in another module, is not seen.

    The limit: this proves that a ``.workaround(`` call naming the step exists in the two files, not that the call is
    reached (a guard around it that never holds passes; review of #306, Q1). The runtime evidence is the vertical
    lane's ledger, whose fallbacks list each step taken today's way (``answer:plan``, ``answer:publish``)."""
    found: set[str] = set()
    for text in sources:
        for node in ast.walk(ast.parse(text)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "workaround"
                    and node.args):
                arg = node.args[0]
                for value in (arg.body, arg.orelse) if isinstance(arg, ast.IfExp) else (arg,):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        found.add(value.value)
    return found


def g3_steps_skipping_the_oracle(keys: set[str], steps=O.STEPS) -> dict[str, set[str]]:
    """Each scenario's G3-protected steps that no ``workaround`` call takes (review of #306, F1)."""
    out = {}
    for sc in ("V1", "V2", "V4"):
        for steering in (False, True):
            missing = {s.key for s in O.path(sc, steering=steering, steps=steps) if O.g3_protected(s)} - keys
            if missing:
                out[f"{sc}{' steering' if steering else ''}"] = missing
    return out


def test_every_g3_step_the_operator_takes_goes_through_the_oracle():
    """Every G3-protected step of V1, V2 and V4 (with steering off and on) that the scripted operator takes goes
    through the oracle (`Operator.workaround`): a fallback while it has not landed, `no_driver` once it has. Planted:
    a module that takes plan only through chat is named, and so is a G3 step added to the row in a fixture."""
    keys = workaround_keys([p.read_text(encoding="utf-8") for p in TAKERS])
    assert g3_steps_skipping_the_oracle(keys) == {}
    assert {"open", "plan", "publish", "reopen", "setting", "raise"} <= keys
    assert g3_steps_skipping_the_oracle(keys - {"plan"}) == {sc: {"plan"} for sc in (
        "V1", "V1 steering", "V2", "V2 steering", "V4", "V4 steering")}
    extra = O.Step(14, "extra", O._s("V1"), ("X01",), (O.Wire("X01", "CLOSE_ATTACHMENT", O.G3, "A-25"),), ("G3",))
    assert g3_steps_skipping_the_oracle(keys, (*O.STEPS, extra))["V1"] == {"extra"}
    assert workaround_keys(['op.workaround("a" if x else "b", "y")', "op.workaround(key, 'y')"]) == {"a", "b"}


def test_a_step_added_to_a_path_moves_its_budget_with_no_edit():
    """Planted: a G3-protected step added to V1's path in a fixture moves V1's budget, and V2's and V4's, which
    inherit V1's path; a step with no G3 action moves none."""
    extra = O.Step(14, "extra", O._s("V1"), ("X01",), (O.Wire("X01", "CLOSE_ATTACHMENT", O.G3, "A-25"),), ("G3",))
    plain = O.Step(15, "plain", O._s("V1"), ("X02",), (O.Wire("X02", "DELEGATED_CANCEL", O.DELEGATED, "A-24"),), ())
    steps = (*O.STEPS, extra, plain)
    assert {sc: O.pin_budget(O.path(sc, steps=steps)) for sc in O.INHERITS} == {"V1": 4, "V2": 5, "V3": 0, "V4": 5}
    assert O.pin_budget(O.path("V1", steps=(*O.STEPS, plain))) == 3
