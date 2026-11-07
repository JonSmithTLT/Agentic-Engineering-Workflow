"""Live lane: tools/harness_qualify against the real pinned OpenCode binary (opt-in: ``--live``).

The proof that the tool measures what AEW already trusts: run offline, with no key, private homes and the scripted
model, it regenerates the pinned fixtures byte for byte and finds no changed fact. Run it with::

    pytest --live tests/live/test_harness_qualify_live.py -p no:xdist -q
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from aew.harness.opencode import adapter

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.append(str(ROOT / "tools"))

import harness_qualify as HQ  # noqa: E402

BINARY = os.environ.get(adapter.BIN_ENV) or adapter.default_binary()
pytestmark = pytest.mark.skipif(not BINARY, reason="no OpenCode binary (set AEW_OPENCODE_BIN)")
FIXTURES = ROOT / "tests" / "fixtures" / "opencode"


def test_the_pinned_binary_regenerates_its_fixtures_exactly(tmp_path):
    pack = HQ.pack_for("opencode")
    v = pack.pinned_version
    record, diff, fixtures, _ = HQ.run(pack, Path(BINARY), out=tmp_path, fixtures=FIXTURES)
    assert record.version == v
    assert not [r for r in record.checks if r["status"] not in ("pass", "skipped")], record.checks
    assert diff.clean, diff.lines()
    status = {f["fixture"]: f["status"] for f in fixtures}
    assert status == {f"openapi-{v}.min.json": "identical", f"usage-{v}-openai.json": "identical",
                      f"tool-parts-{v}.json": "identical", f"store-{v}.json": "identical",
                      f"live-usage-{v}.json": "not regenerated"}
