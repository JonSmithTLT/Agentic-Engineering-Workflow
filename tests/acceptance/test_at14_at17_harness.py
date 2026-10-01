"""M3 acceptance scenarios AT-14..AT-17 (ADR-0009, ADR-0010): a Ticket through harnesses, the disposable harness,
isolated review and credential custody. Stated once in ``tests/helpers/harness_acceptance.py``; here each runs
against the fake harness and against the real OpenCode adapter with the fake V2 server (the Lead through
``aew opencode``). The live lane runs the same scenarios on real OpenCode 2.0.18
(``tests/live/test_opencode_acceptance_live.py``)."""

from __future__ import annotations

import pytest

from harness_acceptance import ACCEPTANCE
from harness_conformance import FakeDriver, FakeOpenCodeDriver, run_scenario

DRIVERS = [FakeDriver(), FakeOpenCodeDriver()]
by_driver = pytest.mark.parametrize("driver", DRIVERS, ids=lambda d: d.name)


@pytest.mark.acceptance("AT-14")
@by_driver
def test_at14_a_ticket_end_to_end_through_harnesses(driver, tmp_path):
    run_scenario(ACCEPTANCE["AT-14"], driver, tmp_path)


@pytest.mark.acceptance("AT-15")
@by_driver
def test_at15_the_harness_is_disposable(driver, tmp_path):
    run_scenario(ACCEPTANCE["AT-15"], driver, tmp_path)


@pytest.mark.acceptance("AT-16")
@by_driver
def test_at16_review_is_isolated(driver, tmp_path):
    run_scenario(ACCEPTANCE["AT-16"], driver, tmp_path)


@pytest.mark.acceptance("AT-17")
@by_driver
def test_at17_credential_custody_for_invocations_and_the_lead(driver, tmp_path):
    run_scenario(ACCEPTANCE["AT-17"], driver, tmp_path)
