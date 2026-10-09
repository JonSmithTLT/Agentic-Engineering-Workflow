"""Which declared primitives a stage step can run (M4-E E3; #140 re-review, finding 1).

A stage step is one primitive in one Lead transaction, and the journal checks the transaction's op against the
planned primitive's. So every declared primitive is either refused at a stage's opening (``NOT_STEPS``), or every op
``commit_ops`` names for it is an op some Lead transaction in the engine is entered under: a map that named an op no
transaction uses would open stages whose steps could never commit."""

from __future__ import annotations

import re
from pathlib import Path

from aew.engine import primitives as P

ENGINE = Path(P.__file__).resolve().parent
LEAD_TXN_OP = re.compile(r"lead_txn\(\s*[^,()]+,\s*[^,()]+,\s*\"([a-z_.]+)\"")


def lead_txn_ops() -> set[str]:
    return {m.group(1) for f in ENGINE.glob("*.py") for m in LEAD_TXN_OP.finditer(f.read_text(encoding="utf-8"))}


def test_every_declared_primitive_is_a_runnable_step_or_refused_at_opening():
    ops = lead_txn_ops()
    assert {"checkpoint", "work.assign", "steering.lower", "invoke.create"} <= ops  # the scan finds the engine's ops
    missing = {p: sorted(P.commit_ops(p) - ops) for p in P.SPECS if p not in P.NOT_STEPS and P.commit_ops(p) - ops}
    assert not missing, f"primitives whose commit op no Lead transaction is entered under: {missing}"
    assert P.NOT_STEPS <= set(P.SPECS)  # only declared primitives are listed as not steps
