"""The feature verdicts each harness version was given, one file per harness (``verdicts/<harness>.yaml``): the record
a bump writes and the next bump builds on (the operator, 2026-11-07: one owner, which a pull request's body points at
instead of restating). Each verdict names a feature, one of :data:`VERDICTS`, its reason, and the register row that
carries it, or none. The report names how many are recorded for the version it measured, or that none are, which is
the next bump's work."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.util import load_yaml

HERE = Path(__file__).resolve().parent / "verdicts"
SCHEMA = "aew/harness-verdicts/v1"
VERDICTS = ("adopt", "consume", "deny", "hold", "hold -> consume", "ignore")


def path(harness: str) -> Path:
    return HERE / f"{harness}.yaml"


def load(harness: str) -> dict[str, list[dict[str, Any]]]:
    """``{version: [verdict, ...]}`` for ``harness``, empty when it has no file. A file that is not the schema, or a
    verdict outside :data:`VERDICTS`, is refused: a record nobody can read is no record."""
    file = path(harness)
    if not file.is_file():
        return {}
    doc = load_yaml(file.read_text(encoding="utf-8"), source=str(file))
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or doc.get("harness") != harness:
        raise ValueError(f"{file}: not a {SCHEMA} record for {harness}")
    out: dict[str, list[dict[str, Any]]] = {}
    for version, entry in (doc.get("versions") or {}).items():
        rows = (entry or {}).get("verdicts") or []
        for row in rows:
            if not isinstance(row, dict) or not row.get("feature") or not row.get("reason") \
                    or row.get("verdict") not in VERDICTS:
                raise ValueError(f"{file}: {version}: each verdict needs a feature, a reason and one of {VERDICTS}")
        out[str(version)] = rows
    return out


def lines(harness: str, version: str) -> list[str]:
    """The report's section: the verdicts recorded for ``version``, counted by kind, or that none are yet."""
    rows = load(harness).get(version)
    where = path(harness).relative_to(HERE.parents[2]).as_posix()
    if not rows:
        return [f"  none recorded for {version}: the bump records each new feature's verdict in {where}"]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    kinds = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    return [f"  {len(rows)} recorded for {version} ({kinds}) in {where}"]
