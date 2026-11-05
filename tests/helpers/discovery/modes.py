"""Per-rule modes of D2 (discovery-layer spec v3.4, §5). Pinned here and in docs/implementation/vertical-uat.md §8;
``tests/unit/test_discovery_registry.py`` checks that the two agree. A mode changes only by the operator's decision:
lowering one from enforce fails a pull request without the ``operator-merge`` label (``discovery_ratchet.py``).

``shadow``: the rule's findings are reported, never failing a run. ``enforce``: a new ``(rule, output-site key)`` fails
the run, and an allow-listed entry no longer observed fails a run complete for it, a pull request's full tier included
(the allow-list may only shrink). Every rule starts in shadow, as the vertical UAT did: enforcing is the operator's
decision, made once the reports have been read.
"""

from __future__ import annotations

SHADOW, ENFORCE = "shadow", "enforce"
MODE_VALUES = (SHADOW, ENFORCE)

RULES = ("O-IDS", "O-CMD", "O-CODE", "O-WORDS", "O-SECRET", "O-ENV")

MODES: dict[str, str] = {
    "O-IDS": SHADOW,
    "O-CMD": SHADOW,
    "O-CODE": SHADOW,
    "O-WORDS": SHADOW,
    "O-SECRET": SHADOW,
    "O-ENV": SHADOW,
}
