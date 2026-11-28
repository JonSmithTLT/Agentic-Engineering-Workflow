"""A continue's commit summary names the evidence it took, and reads it back whole (E400; quick check of #651, n1).

``stage_intents.took`` writes the clause and ``taken_in`` reads it; invariant 63 reads a continue's summary through
``taken_in`` only, so an id that does not round-trip would be a false violation.
"""

from __future__ import annotations

import pytest

from aew.engine import stage_intents as SI

AWKWARD_IDS = [
    "INV-0001-check-unit.fast",
    "INV-0001-check-a;b",
    "INV-0001-check-a, b",
    'INV-0001-check-"quoted"',
    "INV-0001-check-ünïcode",
    "INV-0001-check-line\nbreak",
    f"INV-0001-check-{SI.TOOK_PREFIX}{{}}",
]


@pytest.mark.parametrize("evidence_id", AWKWARD_IDS)
def test_any_evidence_id_a_continue_took_reads_back_whole_from_its_summary(evidence_id):
    summary = "continue T-0001's stage" + SI.took({"R-INV-0001-1": [evidence_id, "INV-0001-report"]})
    assert "\n" not in summary
    assert SI.taken_in(summary) == {"R-INV-0001-1": [evidence_id, "INV-0001-report"]}


def test_a_summary_that_took_nothing_reads_back_as_nothing_taken():
    assert SI.took({}) == ""
    assert SI.taken_in("continue T-0001's stage") == {}


@pytest.mark.parametrize("clause", ["not json", "[1, 2]", '{"R-1": "not a list"}', '{"R-1": [1]}',
                                    '{"R-1": ["E-1"]} trailing'])
def test_a_took_clause_that_does_not_read_back_is_reported_not_ignored(clause):
    assert SI.taken_in(f"continue T-0001's stage{SI.TOOK_PREFIX}{clause}") is None
