"""The adapter-neutral harness conformance suite against the fake harness (CI). The OpenCode driver runs the
same scenarios in the opt-in live lane (M3 step 4)."""

from __future__ import annotations

import pytest

from harness_conformance import SCENARIOS, FakeDriver, run_scenario


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_fake_harness_conforms(scenario, tmp_path):
    run_scenario(scenario, FakeDriver(), tmp_path)
