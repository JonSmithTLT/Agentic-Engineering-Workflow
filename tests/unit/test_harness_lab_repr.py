"""A failed harness test never prints its lab's environment values (``fake_harness.Env``). A live lab's environment
can hold a provider key, and pytest's traceback prints each frame's arguments, the lab among them.

Proved on the report pytest itself writes: a failing test is run in its own pytest, with the default traceback, and
its captured report is read. The value planted is synthetic."""

from __future__ import annotations

import dataclasses
import os
import secrets
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fake_harness import Env, HarnessLab

import aew

NAME = "OPENCODE_API_KEY"
HELPERS = Path(__file__).resolve().parents[1] / "helpers"
FAILING = '''
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from fake_harness import HarnessLab

PLANTED = {planted!r}


def lab(env):
    return HarnessLab(SimpleNamespace(root=Path(".")), Path("."), env)


def a_lab_command_failed(the_lab, env):
    assert the_lab is None, "a lab command failed"


@dataclass
class Plain:  # what the lab was: an environment held as a plain dict
    env: dict


def test_with_key():
    the_lab = lab({{{name!r}: PLANTED, "AEW_LAUNCH_ACK_S": "240"}})
    a_lab_command_failed(the_lab, the_lab.env)


def test_plain_control():
    a_lab_command_failed(Plain({{{name!r}: PLANTED}}), {{{name!r}: PLANTED}})


def test_without_key():
    the_lab = lab({{"AEW_LAUNCH_ACK_S": "240"}})
    a_lab_command_failed(the_lab, the_lab.env)
'''


def report(tmp_path: Path, test: str, planted: str) -> str:
    """The report a default pytest run writes for ``test``, which fails."""
    (tmp_path / "test_failing_lab.py").write_text(FAILING.format(planted=planted, name=NAME), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(HELPERS), str(Path(aew.__file__).resolve().parents[1])])}
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    done = subprocess.run([sys.executable, "-m", "pytest", "-c", str(tmp_path / "pytest.ini"), "-p", "no:cacheprovider",
                           "-p", "no:xdist", f"test_failing_lab.py::{test}"], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=120, creationflags=flags)
    assert done.returncode == 1, done.stdout + done.stderr  # the test failed, and its report was written
    return done.stdout + done.stderr


@pytest.fixture
def planted() -> str:
    return "sk-planted-" + secrets.token_hex(12)


def test_a_failed_tests_report_names_the_labs_variables_and_never_their_values(tmp_path, planted):
    text = report(tmp_path, "test_with_key", planted)
    assert "HarnessLab(" in text and NAME in text  # the lab is printed, its variables named
    assert planted not in text


def test_the_wrong_case_an_environment_held_as_a_plain_dict_prints_its_value_in_the_same_report(tmp_path, planted):
    assert planted in report(tmp_path, "test_plain_control", planted)  # so the check above can see a leak


def test_the_missing_case_a_lab_with_no_key_reports_as_before(tmp_path, planted):
    text = report(tmp_path, "test_without_key", planted)
    assert "HarnessLab(" in text and "AEW_LAUNCH_ACK_S" in text and NAME not in text and planted not in text


def test_every_other_helper_object_that_holds_a_token_or_a_credential_leaves_it_out_of_its_repr():
    """The sweep of ``tests/helpers`` and ``tests/live`` for objects holding an environment, a token or a key: these
    dataclasses print their fields; the others found hold none (``fake_opencode``'s ``Session`` and ``FakeOpenCode``
    keep ``object``'s repr)."""
    from aewflow import Role
    from conftest import Project
    from vertical.scripted_operator import Operator

    for cls, names in ((Project, {"token"}), (Role, {"token"}), (Operator, {"shell_env", "credential"})):
        assert {f.name for f in dataclasses.fields(cls) if f.name in names and not f.repr} == names, cls


def test_what_each_command_gets_is_unchanged_and_never_printed(tmp_path, planted):
    passed: list[Any] = []
    lab = HarnessLab(SimpleNamespace(root=tmp_path, aew=lambda *a, env=None: passed.append(env)), tmp_path,
                     {NAME: planted})
    lab.aew("lead", "show", env={"EXTRA": "1"})
    assert isinstance(lab.env, Env) and isinstance(passed[0], Env) and isinstance(HarnessLab(None, tmp_path).env, Env)
    assert passed[0] == {NAME: planted, "EXTRA": "1"}
    assert planted not in repr(lab) and planted not in str(lab.env) and planted not in repr(passed[0])
