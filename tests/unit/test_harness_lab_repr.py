"""A failed harness test never prints its lab's environment values (``fake_harness.Env``). A live lab's environment
holds the operator's real provider key, and the live run of 2026-11-06 printed it: pytest's long traceback prints each
frame's arguments, the lab among them, and the lab's repr held its environment. The value planted here is synthetic."""

from __future__ import annotations

import secrets
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fake_harness import Env, HarnessLab

NAME = "OPENCODE_API_KEY"


def fails(lab: Any, env: Any) -> None:
    assert lab is None and env is None, "a lab command failed"


def traceback_of(lab: Any, env: Any) -> str:
    with pytest.raises(AssertionError) as caught:
        fails(lab, env)
    return str(caught.getrepr(style="long", funcargs=True))  # as pytest reports a failure: each frame's arguments


def planted_lab(tmp_path: Path) -> tuple[HarnessLab, str, list[dict[str, Any]]]:
    planted = "sk-planted-" + secrets.token_hex(12)
    passed: list[dict[str, Any]] = []
    project = SimpleNamespace(root=tmp_path, aew=lambda *args, env=None: passed.append(env))
    return HarnessLab(project, tmp_path, {NAME: planted, "AEW_LAUNCH_ACK_S": "240"}), planted, passed


def test_a_failed_tests_traceback_names_the_labs_variables_and_never_their_values(tmp_path):
    lab, planted, passed = planted_lab(tmp_path)
    lab.aew("lead", "show", env={"EXTRA": "1"})
    text = traceback_of(lab, passed[0])
    assert NAME in text and "EXTRA" in text  # the variables are still named, for the reader of a failure
    assert planted not in text
    assert planted not in repr(lab) and planted not in str(lab.env) and planted not in repr(passed[0])
    assert passed[0][NAME] == planted and passed[0]["EXTRA"] == "1"  # what the command gets is unchanged


def test_the_planted_control_a_plain_environment_in_the_same_traceback_prints_its_value(tmp_path):
    lab, planted, _ = planted_lab(tmp_path)
    assert planted in traceback_of(None, dict(lab.env))  # so the check above can see a leak where there is one
    assert isinstance(lab.env, Env) and isinstance(HarnessLab(lab.project, tmp_path).env, Env)
