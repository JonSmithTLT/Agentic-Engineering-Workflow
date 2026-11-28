"""E148's proposed read-projection data comes only from the recorded run labels."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aew.dashboard import projections as P
from aew.dashboard.contract import Contract
from aew.errors import NotFound
from aew.harness import containment
from aew.harness.base import RELAY_FAMILY_SHOWN
from aew.harness.containment.netns import NETWORK_MODES
from aew.harness.containment.relay import PROVIDER_RELAY_STATES

ROOT = Path(__file__).resolve().parents[2]
INVOCATION = "INV-0001"


class Projector(P.Projector):
    def __init__(self, records, *, archived=False, custody=False):
        self.records = records
        self.invocation = {"runs": [{"run": run_id} for run_id in records]}
        self.invocation["kind"] = "integration_attempt" if custody else "work"
        self.state = {"invocations": {} if archived else {INVOCATION: self.invocation}, "schema": "aew/control/v2"}
        self.archive = self
        self.read = []

    def require(self, capability):
        assert capability == "runs"

    def rehydrate_invocation(self, state, inv_id):
        assert state is self.state
        return {"invocations": {INVOCATION: self.invocation}} if inv_id == INVOCATION else None

    def _observe(self, run):
        self.read.append(run)
        return "stopped", self.records[run]


def _label(network):
    return {"containment": {"filesystem": "os_readonly_roots", "network": network}}


def test_the_provider_route_projection_matches_the_proposed_data_schema():
    records = {
        "R-INV-0001-1": _label({"mode": "proxy_only", "provider_relay": "configured", "relay_family": "matches",
                                "provider_upstream": "https://example.invalid",
                                "provider_client_cert": "/private/cert"}),
        "R-INV-0001-2": _label({"mode": "proxy_only", "provider_relay": "configured", "relay_family": "unverified"}),
        "R-INV-0001-3": _label({"mode": "isolated", "provider_relay": "none", "relay_family": "matches"}),
        "R-INV-0001-4": _label("shared"),
        "R-INV-0001-5": None,
        "R-INV-0001-6": _label({"mode": ["unexpected"], "provider_relay": "other",
                                "relay_family": {"value": "bad"}}),
    }
    data = Projector(records, archived=True).run_provider_routes(INVOCATION)
    assert data == {
        "invocation": INVOCATION,
        "runs": [
            {"id": "R-INV-0001-1", "network_mode": "proxy_only", "provider_relay": "configured",
             "relay_family": "matches"},
            {"id": "R-INV-0001-2", "network_mode": "proxy_only", "provider_relay": "configured",
             "relay_family": "unverified"},
            {"id": "R-INV-0001-3", "network_mode": "isolated", "provider_relay": "none", "relay_family": None},
            # Read as `harness status` reads them (#649's review, F2): a label before CS-3b had no relay, and a run
            # with no label is the uncontained run's, on this platform's network
            {"id": "R-INV-0001-4", "network_mode": "shared", "provider_relay": "none", "relay_family": None},
            {"id": "R-INV-0001-5", "network_mode": containment.network(), "provider_relay": "none",
             "relay_family": None},
            {"id": "R-INV-0001-6", "network_mode": None, "provider_relay": None, "relay_family": None},
        ],
    }
    proposal = (ROOT / "docs/design/proposals/dashboard-run-provider-routes-v0.1.md").read_text(encoding="utf-8")
    addition = yaml.safe_load(proposal.split("```yaml\n", 1)[1].split("```", 1)[0])
    contract = Contract(ROOT / "docs/design/dashboard-api-v1-provisional.yaml")
    contract.schemas.update(addition)
    assert contract.violations("RunProviderRoutes", data) == []
    # The hand-off's enums are its owners' vocabularies, plus null (#656's review, m2: derive, don't restate)
    fields = addition["RunProviderRoutes"]["properties"]["runs"]["items"]["properties"]
    owners = {"network_mode": {*NETWORK_MODES, containment.NOT_PROVIDED}, "provider_relay": set(PROVIDER_RELAY_STATES),
              "relay_family": set(RELAY_FAMILY_SHOWN)}
    for name, owned in owners.items():
        assert set(fields[name]["enum"]) == {*owned, None}, name


def test_empty_and_unknown_invocations():
    projector = Projector({})
    assert projector.run_provider_routes(INVOCATION) == {"invocation": INVOCATION, "runs": []}
    with pytest.raises(NotFound):
        projector.run_provider_routes("INV-9999")
    with pytest.raises(NotFound):
        Projector({}, custody=True).run_provider_routes(INVOCATION)


def test_the_projection_reads_only_the_runs_visible_in_invocation_detail():
    runs = {f"R-INV-0001-{i}": None for i in range(1, 252)}
    projector = Projector(runs)
    response = projector.run_provider_routes(INVOCATION)
    assert [item["id"] for item in response["runs"]] == list(runs)[:250]
    assert projector.read == list(runs)[:250]
