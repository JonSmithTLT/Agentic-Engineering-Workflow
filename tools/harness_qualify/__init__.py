"""harness_qualify: qualify a harness binary against what AEW relies on (a developer tool, not product surface).

Given a binary path, it runs a probe pack's checks offline, with no key and with private homes and XDG folders, using
a scripted local model. It writes a record (harness, version, binary sha256, each check's result, each declared
capability's status) and a diff of every measured fact against the pinned version's fixtures, and it can write the
fixtures those facts make. A later ``aew harness qualify`` wraps :func:`run` without a rewrite: the CLI is a thin layer.

Layout: :mod:`.core` (harness-neutral runner, record, fact diff, fixture check), :mod:`.model` (the scripted model,
behind an interface), :mod:`.neutral` (AEW's own suites as checks), :mod:`.capabilities` (the capability names checks
are keyed by), and one pack per harness: :mod:`.opencode`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import Diff, Pack, Record, fact_diff, fixture_report, qualify, report

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {"opencode": ROOT / "tests" / "fixtures" / "opencode"}


def pack_for(harness: str, fixtures: Path | None = None) -> Pack:
    if harness == "opencode":
        from .opencode import OpenCodePack

        return OpenCodePack(fixtures or FIXTURES["opencode"])
    raise ValueError(f"no probe pack for {harness!r} (built: opencode; Codex's comes with F24)")


def run(pack: Pack, binary: Path, *, out: Path, fixtures: Path, only: Any = None, slow: bool = False,
        keep: bool = False) -> tuple[Record, Diff, list[dict[str, str]], list[str]]:
    """Qualify ``binary``: the record, the diff against the pin, the fixture report and what is worth adopting."""
    record = qualify(pack, binary, out=out, only=only, slow=slow, keep=keep)
    _pinned_version, pinned = pack.pinned(fixtures)
    diff = fact_diff(record.facts, pinned, unmeasured=record.unmeasured, checks=record.checks)
    fixtures_out = fixture_report(pack, record.version, record.facts, fixtures)
    return record, diff, fixtures_out, pack.adoptable(record.facts, pinned)


__all__ = ["Diff", "Pack", "Record", "fact_diff", "fixture_report", "pack_for", "qualify", "report", "run"]
