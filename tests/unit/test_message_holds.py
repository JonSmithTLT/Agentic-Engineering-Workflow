"""No telemetry event can authorize a worker-message delivery; run endings use the record lane explicitly."""

from __future__ import annotations

import pytest

from aew.harness import contract as K
from aew.harness import progress as P


@pytest.mark.parametrize("digest", [None, {}, {"state": "working", "messages": ["MSG-INV-0001-2"]}])
def test_message_holds_requires_the_exact_verified_eligible_identity(digest):
    trigger = {"why": K.WORKER_MESSAGE, "message": "MSG-INV-0001-2"}
    assert not P.holds(digest, trigger)
    assert not P.holds(digest, trigger, eligible_messages={"MSG-INV-0002-2"})
    assert P.holds(digest, trigger, eligible_messages={"MSG-INV-0001-2"})
    assert not P.holds(digest, {"why": K.WORKER_MESSAGE}, eligible_messages={"MSG-INV-0001-2"})


def test_ended_is_an_explicit_record_fact_and_quiet_is_not_a_wait_trigger():
    assert not P.holds({"state": P.ENDED}, {"why": K.RUN_ENDED})
    assert P.holds(None, {"why": K.RUN_ENDED}, run_ended=True)
    assert not P.holds({}, {"why": K.QUIET}, run_ended=True)


def test_every_run_or_message_reason_has_a_positive_holds_case():
    cases = {
        K.RUN_ENDED: P.holds(None, {"why": K.RUN_ENDED}, run_ended=True),
        K.WORKER_MESSAGE: P.holds(None, {"why": K.WORKER_MESSAGE, "message": "m"}, eligible_messages={"m"}),
        K.OUT_OF_SCOPE: P.holds({"out_of_scope": ["x"]}, {"why": K.OUT_OF_SCOPE, "path": "x"}),
        K.TEST_FAILED: P.holds({"red_commands": ["pytest"]}, {"why": K.TEST_FAILED, "command": "pytest"}),
        K.WORKER_IDLE: P.holds({"state": P.IDLE}, {"why": K.WORKER_IDLE}),
    }
    # Push-only quiet/loop reasons are checked by WakeQueue, not a run digest's holds predicate.
    assert set(cases) == set(K.WHY) - set(K.PUSHED_ONLY)
    assert all(cases.values())
