"""`aew integrate custody` refuses to run in a Lead session, and its refusal says so in its details: reason
`lead_session` and the session variables it found (S3/T1; the surface map's keep-out proof reads them)."""

from __future__ import annotations

import pytest

from aew import errors
from aew.engine import custody_ops


def test_the_lead_session_refusal_names_its_reason_and_the_variables_it_found():
    with pytest.raises(errors.PermissionDenied) as refused:
        custody_ops.refuse_lead_session({"AEW_LEAD_BROKER": "127.0.0.1:9", "AEW_LEAD_BROKER_KEY": "00"})
    assert refused.value.details == {"variables": ["AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"],
                                     "reason": custody_ops.LEAD_SESSION}
    assert custody_ops.LEAD_SESSION == "lead_session"


def test_outside_a_lead_session_there_is_no_refusal():
    assert custody_ops.refuse_lead_session({}) is None
