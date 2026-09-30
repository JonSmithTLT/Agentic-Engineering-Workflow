"""Findings of the M3 read-only audit (`docs/implementation/m3-audit-findings.md`) that change code.

Each regression was written, and seen failing, before its fix. X1 and X2 came from the dogfood and live with its
findings (`test_m3_dogfood_findings.py`).
"""

from __future__ import annotations

from aewflow import sample_project


def _doctor(p) -> dict:
    return {c["check"]: c for c in p.ok("doctor", "--json")["checks"]}


def test_doctor_says_whether_yaml_runs_on_libyaml(tmp_path, monkeypatch):
    """A2. Step 7's 3.8-5.9x speed-up (m3-performance.md P1) depends on PyYAML being built with libyaml, and AEW
    falls back to pure Python without a word, so a target machine without it (the offline Rocky 8 wheelhouse is
    unverified) would be several times slower with nothing saying why."""
    from aew import util

    p = sample_project(tmp_path)
    yaml_check = _doctor(p)["yaml"]
    assert yaml_check["status"] == ("PASS" if util.yaml_backend() == "libyaml" else "WARN"), yaml_check
    assert util.yaml_backend() in yaml_check["detail"]

    import yaml

    monkeypatch.setattr(util, "_SafeLoader", yaml.SafeLoader)  # PyYAML without libyaml
    assert util.yaml_backend() == "pure-python"
