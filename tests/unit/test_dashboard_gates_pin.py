"""The dashboard shows the gates policy only as adopted (the policy pin; PR #118 review, N4)."""

from __future__ import annotations

from aew.dashboard.reader import StateReader
from aew.knowledge.manifest import DEFAULT_GATES
from aew.util import dump_yaml, sha256_bytes

GATES = DEFAULT_GATES


def test_the_dashboard_reads_the_gates_policy_only_as_adopted(tmp_path):
    path = tmp_path / "gates.yaml"
    path.write_text(dump_yaml(GATES), encoding="utf-8", newline="\n")
    adopted = sha256_bytes(path.read_bytes())
    assert StateReader._read_gates(path, True, adopted) == GATES
    assert StateReader._read_gates(path, False, None) == GATES  # a project from before the pin
    path.write_bytes(path.read_bytes() + b"# edited\n")
    assert StateReader._read_gates(path, True, adopted) == {}  # an edit nobody adopted is not shown as policy
