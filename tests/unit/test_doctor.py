"""``aew doctor`` reports absence and damage instead of degrading silently (register E2 coverage): a missing git, a
missing module, a PyYAML without libyaml, and an engine that fails to open each show up as a named check."""

from __future__ import annotations

import builtins
import shutil

from aew import doctor, util


def _by_name(checks):
    return {c["check"]: c for c in checks}


def test_a_missing_git_fails_by_name(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    git = _by_name(doctor.environment_checks())["git"]
    assert git["status"] == "FAIL" and "not found on PATH" in git["detail"]


def test_a_missing_module_fails_by_name(monkeypatch):
    real = builtins.__import__

    def no_jsonschema(name, *args, **kwargs):
        if name == "jsonschema":
            raise ImportError("No module named 'jsonschema'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_jsonschema)
    checks = _by_name(doctor.environment_checks())
    assert checks["module:jsonschema"] == {"check": "module:jsonschema", "status": "FAIL",
                                           "detail": "No module named 'jsonschema'"}
    assert checks["module:yaml"]["status"] == "PASS"


def test_a_pyyaml_without_libyaml_is_a_warning_not_a_failure(monkeypatch):
    monkeypatch.setattr(util, "yaml_backend", lambda: "pure-python")
    yaml = _by_name(doctor.environment_checks())["yaml"]
    assert yaml["status"] == "WARN" and "libyaml" in yaml["detail"]


def test_outside_a_project_the_project_check_is_unavailable_and_the_report_renders(tmp_path):
    report = doctor.run(str(tmp_path))
    project = _by_name(report["checks"])["project"]
    assert project["status"] == "UNAVAILABLE" and project["detail"].startswith("PROJECT_NOT_FOUND")
    text = doctor.render(report)
    lines = text.splitlines()
    assert lines[0] == f"aew {report['aew_version']} (spec set {report['spec_set']})"
    assert lines[-1] == f"doctor: {report['failures']} failure(s)"
    assert any(line.startswith("project") and "UNAVAILABLE" in line for line in lines)
