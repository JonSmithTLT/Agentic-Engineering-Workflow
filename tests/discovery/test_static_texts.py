"""D2 over the static texts (docs/implementation/vertical-uat.md §8): the Lead's system text and commands, the rendered
guide, the operator guides and every pack template. The scan is complete, so a new key and a stale one are both
decided here, on every pull request, by each rule's mode (``tests/helpers/discovery/modes.py``)."""

from __future__ import annotations

import sys
from pathlib import Path

from discovery import allowed, modes, static

GUIDES = Path(__file__).resolve().parents[2] / "docs" / "guides"


def test_the_static_texts_add_no_violation_and_keep_no_stale_entry():
    observed = {f.key for f in static.scan(static.read_guides(GUIDES, "docs/guides"))}
    listed = {k for k in allowed.load() if allowed.is_static(k)}
    verdict = allowed.decide(observed, listed, stale_scope="static")
    report = "\n".join(allowed.report(verdict))
    print(f"D2 static texts ({sys.platform}): {len(observed)} keys observed, {len(listed)} allow-listed; modes "
          + ", ".join(f"{r} {m}" for r, m in modes.MODES.items()) + "\n" + report)
    assert verdict.ok, report
