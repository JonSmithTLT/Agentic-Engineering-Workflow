"""STG-02 push-back 3, compare-and-fence across real processes: two processes submit the same command set under the
same client key at the same moment, against one ledger file. Exactly one dispatches; the other's answer is the
stored receipt, identical byte for byte, and HEB holds exactly one operation. Real-process concurrency is the
property, so the module is in the ``serial`` lane.

The overlap is forced, not hoped for (review M1): each worker holds its transaction open for :data:`HOLD_S` right after
its key lookup, so the second worker's lookup always falls inside the first's transaction. The mutant this kills is a
ledger whose ``transaction()`` takes no lock up front (a plain ``BEGIN``, or ``BEGIN IMMEDIATE`` removed): both
lookups then see no key, both dispatch, and the test sees two owner operations or two un-replayed receipts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.serial
HOLD_S = 0.5

SRC = Path(__file__).resolve().parents[2] / "src"
WORKER = r"""
import json, sys, time
from datetime import UTC, datetime
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from aew.stg02 import ledger as L
from aew.stg02 import server as SV
_key = L.Txn.key
def held_key(self, *a):
    out = _key(self, *a)
    time.sleep(float(sys.argv[4]))  # inside the transaction: the other worker's lookup overlaps this one
    return out
L.Txn.key = held_key
s = SV.Slice(Path(sys.argv[2]), fixture_recipient=True)
req = SV.driver_config(s)["command"]["continue_eligible_work"]
go = float(sys.argv[3])
while time.time() < go:
    time.sleep(0.001)
receipt, replayed = s.carrier.submit(req, s.fx.recipient, datetime.now(UTC))
print(json.dumps({"receipt": receipt, "replayed": replayed}, sort_keys=True))
"""


def test_two_processes_with_one_key_dispatch_once_and_both_see_the_one_receipt(tmp_path: Path):
    state = tmp_path / "state"
    go = time.time() + 3.0
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    argv = [sys.executable, "-c", WORKER, str(SRC), str(state), str(go), str(HOLD_S)]
    procs = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw)
             for _ in range(2)]
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
        outs.append(json.loads(out))
    assert sorted(o["replayed"] for o in outs) == [False, True]
    assert outs[0]["receipt"] == outs[1]["receipt"]
    from aew.stg02.ledger import Ledger

    with Ledger(state / "stg02-ledger.sqlite3").reading() as t:
        assert len(t.owner_ops("fixture:installation-slice", "fixture:recipient-operator", datetime.now(UTC))) == 1
