"""The Lead broker's test seams stay test seams (the flake audit's seam #3).

``LeadBroker(clock=, idle=)`` and ``broker_liveness.Beat(clock=, idle=)`` let a test step the watchdog and the beat
thread, and stamp the liveness record from a clock the test moves. An agent that could reach either could slow or fake
what the operator is told about the broker, so:
- each defaults to the real one, ``time.time`` and ``threading.Event``, as a keyword-only parameter, and a Beat built
  without them uses them;
- no production code passes either: the scan of ``src/aew`` finds one call that names them, the broker passing its own
  to its Beat.

The scan reads ``src/aew`` only. What it does not see, each a defect the reviewer reads for, pinned in ``MISSED``: an
alias of either class, ``functools.partial``, an attribute assigned after construction, a subclass's
``super().__init__(..., clock=)``, and an explicit ``LeadBroker.__init__(..., clock=)``. A call through ``**kwargs``
it cannot name fails the scan instead.
"""

from __future__ import annotations

import ast
import inspect
import threading
import time
from pathlib import Path

import pytest

from aew.harness import broker_liveness, lead_broker

SRC = Path(lead_broker.__file__).resolve().parents[1]  # src/aew
SEAMS = ("clock", "idle")
CLASSES = ("LeadBroker", "Beat")
# The one call that names a seam: the broker passes its own seams through to its Beat.
PASSED_THROUGH = {("harness/lead_broker.py", "Beat", seam, seam) for seam in SEAMS}


def seam_calls(source: str, label: str) -> set[tuple[str, str, str, str]]:
    """Each call of ``LeadBroker`` or ``Beat`` in ``source`` that passes a seam, as (file, class, keyword, value), and
    a ``**`` in such a call as keyword ``**``."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in CLASSES:
            continue
        for keyword in node.keywords:
            if keyword.arg is None or keyword.arg in SEAMS:
                found.add((label, name, keyword.arg or "**", ast.unparse(keyword.value)))
    return found


def test_the_seams_default_to_the_real_clock_and_event(tmp_path):
    for cls in (lead_broker.LeadBroker, broker_liveness.Beat):
        params = inspect.signature(cls).parameters
        assert params["clock"].default is time.time and params["idle"].default is threading.Event, cls
        assert params["clock"].kind is params["idle"].kind is inspect.Parameter.KEYWORD_ONLY, cls
    beat = broker_liveness.Beat(tmp_path, generation=1, poll_s=5.0, wedge_after_s=60.0)
    assert beat._clock is time.time and type(beat._stop) is threading.Event


def test_no_production_code_passes_a_seam():
    found = set()
    for path in sorted(SRC.rglob("*.py")):
        found |= seam_calls(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    assert found == PASSED_THROUGH


@pytest.mark.parametrize(("source", "expected"), [
    ("LeadBroker(engine, token, clock=fake)\n", {("x.py", "LeadBroker", "clock", "fake")}),
    ("lead_broker.LeadBroker(engine, token, idle=Steps)\n", {("x.py", "LeadBroker", "idle", "Steps")}),
    ("broker_liveness.Beat(root, generation=1, poll_s=1.0, wedge_after_s=2.0, clock=lambda: 0.0)\n",
     {("x.py", "Beat", "clock", "lambda: 0.0")}),
    ("LeadBroker(engine, token, **options)\n", {("x.py", "LeadBroker", "**", "options")}),
    ("LeadBroker(engine, token)\nBeat(root, generation=1, poll_s=1.0, wedge_after_s=2.0)\n", set()),
    ("Other(clock=fake)\n", set()),
])
def test_the_scan_finds_a_seam_passed(source, expected):
    assert seam_calls(source, "x.py") == expected


# The spellings the scan does not see (the module docstring): each passes a seam, and the scan finds nothing.
MISSED = {
    "alias": "Broker = LeadBroker\nBroker(engine, token, clock=fake)\n",
    "partial": "functools.partial(LeadBroker, clock=fake)(engine, token)\n",
    "set_later": "broker = LeadBroker(engine, token)\nbroker._beat._clock = fake\n",
    "subclass": "class Slow(LeadBroker):\n    def __init__(self, engine, token):\n"
                "        super().__init__(engine, token, clock=fake)\n",
    "explicit_init": "LeadBroker.__init__(broker, engine, token, idle=Steps)\n",
}


@pytest.mark.parametrize("spelling", sorted(MISSED))
def test_the_spellings_the_scan_does_not_see_stay_pinned(spelling):
    assert seam_calls(MISSED[spelling], "x.py") == set()
