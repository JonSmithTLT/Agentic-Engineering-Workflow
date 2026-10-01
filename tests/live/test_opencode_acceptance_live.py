"""Live lane: the M3 acceptance scenarios AT-14..AT-17 on a real OpenCode 2.0.18 server (opt-in: ``--live``).

The scenarios are the ones CI runs against the fake harness and the fake V2 server
(``tests/acceptance/test_at14_at17_harness.py``), stated once in ``tests/helpers/harness_acceptance.py``. Here every
role run is the real adapter with a real private ``opencode-cli serve`` and private state; each role's model turn
is a real prompt to a free model (``AEW_LIVE_OPENCODE_MODEL``), and its tool calls run through the real session's
shell endpoint. The Lead acts through AEW's harness-neutral Lead broker (``aew lead session``): the real TUI needs a
terminal, so the operator's own TUI session is its live check (M3 plan §9). What the live driver cannot observe is
skipped inside the scenario, not asserted: the delivered prompt (the steps are scripted, not prompted) and a
second execution profile (one free model). Run it with::

    pytest --live tests/live/test_opencode_acceptance_live.py -p no:xdist -q
"""

from __future__ import annotations

import os

import pytest

from harness_acceptance import ACCEPTANCE
from harness_conformance import OpenCodeDriver, run_scenario

from aew.harness.opencode import adapter

pytestmark = pytest.mark.skipif(not os.environ.get(adapter.BIN_ENV) and adapter.default_binary() is None,
                                reason="no OpenCode binary (set AEW_OPENCODE_BIN)")


@pytest.mark.parametrize("at", sorted(ACCEPTANCE))
def test_acceptance_on_opencode_2_0_18(at, tmp_path):
    run_scenario(ACCEPTANCE[at], OpenCodeDriver(), tmp_path)
