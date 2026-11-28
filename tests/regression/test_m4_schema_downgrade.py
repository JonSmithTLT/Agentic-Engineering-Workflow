"""Downgrade safety of M4-D's control state (the M4-D plan §1.1; M4 report §2.6, M4-B7).

The schema stays ``aew/control/v2``, additive: queue and lease state carry authority, so an engine that cannot read
them must not open the file at all. Engines before M4-D validate control state on every load with a closed top level,
so a control file with a ``queue`` (and ADR-0012's ``outbox`` marker) fails closed in them: they can neither read nor
write it. Proven here against the vendored schema of the baseline engine (42239e1).
"""

from __future__ import annotations

import json
from pathlib import Path

from aewflow import sample_project, to_commit_ready
from invariants import baseline_control, load_control
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def test_the_baseline_engine_refuses_a_control_file_with_the_queue_and_the_outbox(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)  # a held lease and a live custody invocation
    state = load_control(p.root)
    assert state["schema"] == "aew/control/v2" and state["queue"]["lease"] is not None
    baseline = json.loads((ROOT / "tests/fixtures/baseline/control.schema.42239e1.json").read_text(encoding="utf-8"))
    errors = sorted(e.message for e in Draft202012Validator(baseline).iter_errors(baseline_control(state, baseline)))
    unexpected = "Additional properties are not allowed ('outbox', 'policy_sha256', 'queue' were unexpected)"
    assert unexpected in errors, errors
    # The custodian is an invocation without a role or credential: the baseline refuses that shape too, so even a
    # file stripped of the queue could not smuggle a lease's custodian past an older engine.
    assert any("'role' is a required property" in e for e in errors), errors


def test_queue_is_a_v2_only_key():
    from aew.engine.base import V2_ONLY_KEYS

    assert "queue" in V2_ONLY_KEYS  # the v1 rule refuses it (register E36: test_schemas_records.py)


def test_the_baseline_engine_refuses_a_control_file_with_an_unfinished_stage(tmp_path):
    """M4-E E3 (plan v3 §2.7): a hot StageIntent binds a Lead generation and the policy a stage's next step must still
    satisfy, so an engine that cannot read it must not open the file."""
    from aew.engine.api import Engine
    from aew.engine.base import V2_ONLY_KEYS

    p = sample_project(tmp_path)
    Engine.discover(p.root).stage_open(token=p.token, tool="probe", contract_digest="0" * 64,
                                       arguments={}, judgment_inputs=[], base_class="MECHANICAL",
                                       effective_class="MECHANICAL", plan=[{"primitive": "checkpoint"}],
                                       subject=None, ingress="test")
    state = load_control(p.root)
    assert "stage_intents" in state and "stage_intents" in V2_ONLY_KEYS
    baseline = json.loads((ROOT / "tests/fixtures/baseline/control.schema.42239e1.json").read_text(encoding="utf-8"))
    errors = sorted(e.message for e in Draft202012Validator(baseline).iter_errors(baseline_control(state, baseline)))
    assert any("Additional properties are not allowed" in e and "'stage_intents'" in e for e in errors), errors


def test_an_engine_before_e87_refuses_a_control_file_holding_a_carry(tmp_path):
    """Register E87 (#658's review, M1): a carried obligation binds the promoted work, and an engine that cannot read
    one would read only each ancestor's ``policy``, lowering that work. The unit's key is invisible to an older
    engine's unit schema, so the carry is registered at the top level (``obligation_carry``), which the closed top
    level of the engine before E87 (``main`` at 92dfe68, vendored) refuses. Planted control: the same project before
    the promotion validates under it."""
    from aew.engine.base import V2_ONLY_KEYS
    from aew.schemas import _registry

    p = sample_project(tmp_path)
    epic = p.lead("work", "create", "epic", "--title", "Initiative", "--class", "1")["id"]
    story = p.lead("work", "create", "story", "--title", "Payments", "--class", "1", "--parent", epic,
                   "--min-descendant-class", "3", "--rationale", "money moves")["id"]
    ticket = p.lead("work", "create", "ticket", "--title", "Charge", "--class", "1", "--parent", story)["id"]
    vendored = ROOT / "tests/fixtures/baseline/control.schema.92dfe68.json"
    # Its references resolve to today's schemas, which E87 leaves unchanged.
    before_e87 = Draft202012Validator(json.loads(vendored.read_text(encoding="utf-8")), registry=_registry())
    assert list(before_e87.iter_errors(load_control(p.root))) == []
    p.lead("work", "promote", ticket, "--to", "story", "--title", "Wider", "--reason", "scope grew")
    state = load_control(p.root)
    assert "obligation_carry" in state and "obligation_carry" in V2_ONLY_KEYS
    errors = sorted(e.message for e in before_e87.iter_errors(state))
    assert errors == ["Additional properties are not allowed ('obligation_carry' was unexpected)"], errors
