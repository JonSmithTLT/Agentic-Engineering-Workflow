from __future__ import annotations

from aew import SPEC_SET, __version__


def test_version(aew_cli, tmp_path):
    res = aew_cli("--version", cwd=tmp_path)
    assert res.returncode == 0
    assert __version__ in res.stdout and SPEC_SET in res.stdout


def test_doctor_environment_outside_project(aew_cli, tmp_path):
    res = aew_cli("doctor", "--json", cwd=tmp_path)
    report = res.json
    names = {c["check"]: c["status"] for c in report["checks"]}
    assert names["python"] == "PASS"
    assert names["git"] == "PASS"
    assert names["module:yaml"] == "PASS"
    # Outside a project the project check reports absence, not failure.
    assert names.get("project") in (None, "UNAVAILABLE")
    assert res.returncode == 0
