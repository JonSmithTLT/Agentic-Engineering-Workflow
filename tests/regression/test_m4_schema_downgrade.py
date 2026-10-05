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
from invariants import load_control
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def test_the_baseline_engine_refuses_a_control_file_with_the_queue_and_the_outbox(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)  # a held lease and a live custody invocation
    state = load_control(p.root)
    assert state["schema"] == "aew/control/v2" and state["queue"]["lease"] is not None
    baseline = json.loads((ROOT / "tests/fixtures/baseline/control.schema.42239e1.json").read_text(encoding="utf-8"))
    errors = sorted(e.message for e in Draft202012Validator(baseline).iter_errors(state))
    assert "Additional properties are not allowed ('outbox', 'queue' were unexpected)" in errors, errors
    # The custodian is an invocation without a role or credential: the baseline refuses that shape too, so even a
    # file stripped of the queue could not smuggle a lease's custodian past an older engine.
    assert any("'role' is a required property" in e for e in errors), errors


def test_queue_is_a_v2_only_key():
    from aew.engine.base import V2_ONLY_KEYS

    assert "queue" in V2_ONLY_KEYS  # the v1 rule refuses it (register E36: test_schemas_records.py)
