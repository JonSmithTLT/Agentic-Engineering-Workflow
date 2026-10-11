"""The closed launch-failure reason codes (M4-E E8a; plan v3 n8, amendment 1 R2-m2): one lowercase vocabulary whose
launch-failure set is disjoint from the adapter codes, and a mapping that leaves every failure no test reproduces
`unknown`. The launches that produce each mapped code are in tests/integration/test_launch_failure_codes.py."""

from __future__ import annotations

import pytest

from aew.engine import harness_ops
from aew.harness import contract as K
from aew.harness.opencode import adapter as opencode

SITES = (K.CUSTODY, K.START, K.HANDOFF, K.LAUNCHER)
# What the plan names (n8), in the record's lowercase.
N8 = {"spawn_race", "server_start_transport", "containment_refused", "credential_denied", "config_error",
      "quota_exhausted", "auth_failed", "provider_outage", "incompatible_config", "unknown"}


def test_launch_and_adapter_reason_codes_are_disjoint_and_lowercase():
    assert K.LAUNCH_FAILURE_CODES == N8
    every = K.LAUNCH_FAILURE_CODES | K.ADAPTER_REASON_CODES
    assert all(code == code.lower() and code.isidentifier() for code in every)
    assert not K.LAUNCH_FAILURE_CODES & K.ADAPTER_REASON_CODES
    # Every code an adapter reports is an adapter code, never a launch-failure one.
    assert set(opencode.REASON_CODES.values()) <= K.ADAPTER_REASON_CODES
    # The mapping only ever yields the closed set, whatever it is asked.
    asked = [None, "", "AEW_ERROR", "STALE_AUTHORITY", "HARNESS_INCOMPATIBLE", K.PROVIDER_AUTH_FAILED]
    assert {K.launch_failure_code(site, code) for site in SITES for code in asked} <= K.LAUNCH_FAILURE_CODES


@pytest.mark.parametrize("code", sorted(N8))
def test_the_adapters_provider_auth_comparisons_never_meet_a_launch_failure(code):
    """`provider_auth_failed` keeps its own headline and next action (register V1): a `launch_failed` record carries a
    launch-failure code, which is never equal to it, so neither comparison changes for a launch failure."""
    record = {"status": K.LAUNCH_FAILED, "reason": "a launch failure", "reason_code": code}
    assert harness_ops._reason_code(record) == code != K.PROVIDER_AUTH_FAILED
    assert harness_ops._headline("R-INV-0001-1", K.LAUNCH_FAILED, record) is None
    adapter_record = {**record, "status": K.CRASHED, "reason_code": K.PROVIDER_AUTH_FAILED}
    assert "provider rejected the credential" in (harness_ops._headline("R-INV-0001-1", K.CRASHED, adapter_record)
                                                  or "")


@pytest.mark.parametrize("site", SITES)
def test_unmapped_launch_failure_is_unknown(site):
    """n8, the mapping half (E8a): any failure no test reproduces at its site is `unknown`, so none reaches an
    allow-listed code (`spawn_race`, `server_start_transport`) by default. That `unknown` never relaunches is E8b's
    `test_a2[unknown_reason_ineligible]`."""
    unmapped = [None, "", "AEW_ERROR", "HARNESS_LAUNCH_FAILED", "CONTAINMENT_UNAVAILABLE", "PERMISSION_DENIED",
                "ILLEGAL_TRANSITION", "LOCK_TIMEOUT", "spawn_race", "server_start_transport", "not a code"]
    mapped = {(K.CUSTODY, "STALE_AUTHORITY"), (K.START, "HARNESS_INCOMPATIBLE")}
    unmapped += [code for s, code in mapped if s != site]  # a code mapped at one site is not mapped at the others
    assert {K.launch_failure_code(site, code) for code in unmapped} == {K.UNKNOWN_LAUNCH_FAILURE}
    assert K.launch_failure_code(site) == K.UNKNOWN_LAUNCH_FAILURE
    # An error that names a cause its code does not tell apart is never mapped by its code (PR #185 review, F1):
    # OpenCode's catalog wait running out is HARNESS_INCOMPATIBLE, but timing-dependent.
    assert {K.launch_failure_code(site, code, cause) for _, code in mapped
            for cause in (K.CATALOG_TIMEOUT, K.AGENT_LOAD_TIMEOUT)} == {K.UNKNOWN_LAUNCH_FAILURE}
    # Every mapped pair, and only these, each with the launch in the integration tests that produces it.
    assert {(s, c) for s in SITES for c in ("STALE_AUTHORITY", "HARNESS_INCOMPATIBLE")
            if K.launch_failure_code(s, c) != K.UNKNOWN_LAUNCH_FAILURE} == mapped
    assert {K.launch_failure_code(s, c) for s, c in mapped}.isdisjoint({K.SPAWN_RACE, K.SERVER_START_TRANSPORT})


@pytest.mark.parametrize("ack", [{}, {"reason_code": None}, {"reason_code": ["credential_denied"]},
                                 {"reason_code": "provider_auth_failed"}, {"reason_code": "SPAWN_RACE"},
                                 {"reason_code": "a free-text reason"}])
def test_an_acknowledgement_without_a_closed_code_is_passed_on_as_unknown(ack):
    assert harness_ops._acknowledged_code(ack) == {"reason_code": "unknown", "reason_code_source": "acknowledgement"}


def test_a_closed_code_in_an_acknowledgement_is_passed_on():
    assert harness_ops._acknowledged_code({"reason_code": "credential_denied"}) == {
        "reason_code": "credential_denied", "reason_code_source": "acknowledgement"}
