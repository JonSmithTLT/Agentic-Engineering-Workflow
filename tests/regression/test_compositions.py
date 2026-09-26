"""Composition tests for the 2026-09-26 review: operations that are individually tested,
exercised in the sequences where the review found unguarded interactions.

Every scenario ends with the cross-operation invariant oracle.
"""

from __future__ import annotations

from aewflow import integrate, sample_project, to_commit_ready
from invariants import assert_control_invariants


def test_invariants_hold_on_the_normal_serial_lifecycle(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    assert_control_invariants(p)
    integrate(p, wid)
    assert_control_invariants(p)
