"""The adapter-neutral harness conformance suite in CI: against the fake harness, and against the real OpenCode
adapter driving a fake OpenCode V2 server. The live lane runs the same scenarios on OpenCode 2.0.18
(tests/live/test_opencode_live.py)."""

from __future__ import annotations

import pytest
from harness_conformance import SCENARIOS, FakeDriver, FakeOpenCodeDriver, run_scenario


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_fake_harness_conforms(scenario, tmp_path):
    run_scenario(scenario, FakeDriver(), tmp_path)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_opencode_adapter_conforms(scenario, tmp_path):
    run_scenario(scenario, FakeOpenCodeDriver(), tmp_path)
