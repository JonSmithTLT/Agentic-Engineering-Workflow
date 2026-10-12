"""The pack-truth search pattern: what counts as a span in model-facing text (the pack-truth plan, reviewed CLEAR, §2.2
and §2.6; v8 §2.1's span rule).

This module is the pattern's one owner in the repository: the provenance hook's tracer (``pt_hook``) imports it, and
PT-1's ratchet search will too. A span is the matched word, not the clause delimiter before it (`; run` spans `run`).
"""

from __future__ import annotations

import re

# A clause starts at the start of the text, or after `;`, `:`, `.`, `(`, a comma, "then", "or", "and", or a spaced
# dash. One definition, so the pattern and the phrasing check split clauses identically.
CLAUSE_SPLIT = r"[;:.(]\s*|,\s+|\bthen\s+|\bor\s+|\band\s+|\s[—–-]\s+"
# Imperative verbs (the plan's §2.7 list, with `reference` and `state`).
VERBS = ("run start stop give pass try use see rebuild fetch request ingest classify validate commit propose resolve "
         "publish decide accept waive advance close audit requeue acknowledge declare staff abandon redo create choose "
         "upgrade clear drop prepare enable wait generate move replace review configure install reinstall restart "
         "restore revert remove rerun re-run ask approve delete set export edit fix check record explain load return "
         "write take open select merge rebase reconcile tell contact retry "
         "revalidate put send repeat re-verify "
         "add acquire append attach call change checkpoint cite complete continue defer deliver dispose do follow get "
         "initialize join list make pin print promote queue quote raise read rebind recover refresh release re-enable "
         "reconstruct reply restrict seal serve show stash steer strip supersede trust vacate verify walk name lower "
         "type plan work need lock map store guard fail exit default limit field reference state").split()
# `aew` in lower case is the command (the product name "AEW" is not a hit); AEW_* variable names; the rest any case;
# a design-document citation points a reader at a document it may not have; instructions addressed to another
# principal; and an imperative verb at the start of a clause.
PAT = re.compile(r"\baew\b|AEW_[A-Z_]+|\b(?:WC|KC) §|\bADR-\d{4}\b|(?i:check run|\bsubmit\b|--file|--invocation-token|"
                 r"credential|connected|\bcontain(ed|ment)?\b|\.md\b|\.ya?ml\b|workspace|scratch|engine operations|"
                 r"skills? to load|included below|"
                 r"\b(re)?dispatch|\brelaunch|\bmigrate|\badopt|\bcancel|\bthe operator\b|\bthe Lead\b|\bdelete it\b|"
                 r"\bretry\b|"
                 r"(?:^\s*|" + CLAUSE_SPLIT + r")(?:" + "|".join(map(re.escape, VERBS)) + r")\b)")
# The clause delimiter a match may start with: not part of the span.
LEAD = re.compile(r"^(?:[\s;:.(,—–-]|then\s+|or\s+|and\s+)+", re.I)


def spans(text: str) -> list[tuple[int, int]]:
    """Every span of the pattern in ``text``, as ``(start, end)`` with the leading clause delimiter dropped."""
    out = []
    for m in PAT.finditer(text):
        start, end = m.span()
        start += len(m.group(0)) - len(LEAD.sub("", m.group(0)))
        if start < end:
            out.append((start, end))
    return out
