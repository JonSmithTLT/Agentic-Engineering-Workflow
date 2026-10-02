"""Reading, appending and verifying the history manifest of one AEW root (ADR-0011; implementation plan R1, R8).

Every write goes through a control-store ``Session``, so a transition that archives history commits it together with
the hot root at the one ADR-0001 commit point: the records first, then any sealed segment, then the tail. Each of
those writes carries a fault point that crash-safety tests use (``history.after_bundle``, ``history.mid_seal``,
``history.after_tail``).

Reads take a root (``manifest.empty_root()`` shape) and never hold the control lock: sealed segments and records are
immutable, and the tail is checked against the root it is read for. A tail that does not end at that root (it was
replaced since) is reported as an ``IntegrityError``; callers that read outside the lock copy the root and tail
together (ADR-0011 audit, plan R2).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import faults
from aew.errors import IntegrityError, ValidationFailed
from aew.history import manifest as M
from aew.schemas import validate_def
from aew.util import create_exclusive, sha256_bytes, sha256_file, sha256_text

if TYPE_CHECKING:
    from aew.engine.store import Session

# Where history records live (relative to the AEW root): a terminal unit's bundle and annotations beside its other
# records (investigation §3.1), the Lead's generations and audit records under history/.
RECORD_GLOBS = ("work/*/archive.yaml", "work/*/annotations/*.yaml", "history/lead/*.yaml",
                "history/lead/annotations/*.yaml", "history/audits/*.yaml")


def bundle_rel(work_id: str) -> str:
    return f"work/{work_id}/archive.yaml"


def annotation_rel(subject: str, seq: int) -> str:
    return f"work/{subject}/annotations/{seq:04d}.yaml"


@dataclass
class Verification:
    """What a verification walked: from which chain state, through which, and what it found."""

    start: dict[str, Any]
    through: dict[str, Any] | None = None  # the chain state reached; None when the chain itself is broken
    entries: int = 0
    records: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and self.through is not None


class History:
    """The history manifest under ``aew_root``."""

    def __init__(self, aew_root: Path) -> None:
        self.root = aew_root

    # ------------------------------------------------------------------ files

    def _read(self, rel: str) -> bytes | None:
        try:
            return (self.root / rel).read_bytes()
        except FileNotFoundError:
            return None

    def segment(self, seq: int) -> tuple[dict[str, Any], str]:
        """Sealed segment ``seq`` and its file hash."""
        rel = M.segment_rel(seq)
        raw = self._read(rel)
        if raw is None:
            raise IntegrityError(f"history segment {rel} is missing", path=rel)
        doc = M.parse_file(raw.decode("utf-8"), source=rel, sealed=True)
        if doc["seq"] != seq:
            raise IntegrityError(f"{rel} declares itself segment {doc['seq']}", path=rel)
        return doc, sha256_bytes(raw)

    def tail(self, root: dict[str, Any]) -> dict[str, Any]:
        """The tail for ``root``, checked against it: it follows the root's newest sealed segment and its entries end
        exactly at the root. An empty history may have no tail file yet."""
        validate_def("history", "root", root, source="history root")
        sealed = root["sealed_head"]
        raw = self._read(M.TAIL_REL)
        if raw is None:
            if root["count"] or sealed:
                raise IntegrityError(f"history tail {M.TAIL_REL} is missing", path=M.TAIL_REL)
            return {"seq": 1, "start": {"count": 0, "h": M.GENESIS_H}, "prev": None, "entries": []}
        doc = M.parse_file(raw.decode("utf-8"), source=M.TAIL_REL, sealed=False)
        if doc["prev"] != sealed or doc["seq"] != (sealed["seq"] if sealed else 0) + 1:
            raise IntegrityError(f"{M.TAIL_REL} does not follow the root's newest sealed segment",
                                 tail_prev=doc["prev"], sealed_head=sealed)
        end = M.fold(doc["start"], doc["entries"], source=M.TAIL_REL)
        if end != {"count": root["count"], "h": root["head_h"]}:
            raise IntegrityError(f"{M.TAIL_REL} does not end at the hot root", tail_end=end,
                                 root={"count": root["count"], "h": root["head_h"]})
        return doc

    # ------------------------------------------------------------------ lookup

    def entry(self, root: dict[str, Any], seq: int) -> dict[str, Any]:
        """Entry ``seq`` of the history ``root`` pins (1-based)."""
        if not 1 <= seq <= root["count"]:
            raise IntegrityError(f"history has no entry {seq} (it has {root['count']})")
        sealed = root["sealed_head"]
        if sealed and seq <= sealed["seq"] * M.SEGMENT_SIZE:
            doc, _ = self.segment(M.segment_of(seq))
        else:
            doc = self.tail(root)
        entry = doc["entries"][seq - doc["start"]["count"] - 1]
        if entry["seq"] != seq:
            raise IntegrityError(f"history entry {seq} is out of place")
        return entry

    def walk(self, root: dict[str, Any], since: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Every entry after ``since`` ({count, h}; default the genesis) through ``root``, in order, checking the chain
        as it goes: that ``since`` is on it, each entry's hash, each file's start and segment link, and that the walk
        ends exactly at ``root``. Raises ``IntegrityError`` at the first inconsistency."""
        validate_def("history", "root", root, source="history root")
        state = dict(since) if since else {"count": 0, "h": M.GENESIS_H}
        if state["count"] > root["count"]:
            raise IntegrityError("the starting point is beyond the current history", since=state, count=root["count"])
        if state["count"] == 0 and state["h"] != M.GENESIS_H:
            raise IntegrityError("an empty starting point must be the genesis hash")
        if state["count"] and self.entry(root, state["count"])["h"] != state["h"]:
            raise IntegrityError("the starting point is not on the current history's chain", since=state)
        sealed = root["sealed_head"]
        last_sealed = sealed["seq"] if sealed else 0
        first = M.segment_of(state["count"] + 1)
        prev = None
        if first > 1 and first <= last_sealed + 1:
            raw = self._read(M.segment_rel(first - 1))
            if raw is None:
                raise IntegrityError(f"history segment {M.segment_rel(first - 1)} is missing")
            prev = {"seq": first - 1, "sha256": sha256_bytes(raw)}
        for seq in range(first, last_sealed + 1):
            doc, digest = self.segment(seq)
            yield from self._continue(doc, state, prev, M.segment_rel(seq))
            prev = {"seq": seq, "sha256": digest}
        if sealed and prev != sealed:
            raise IntegrityError("the newest sealed segment does not match the hot root", found=prev,
                                 sealed_head=sealed)
        doc = self.tail(root)
        yield from self._continue(doc, state, doc["prev"], M.TAIL_REL)
        if state != {"count": root["count"], "h": root["head_h"]}:
            raise IntegrityError("the history does not end at the hot root", reached=state)

    @staticmethod
    def _continue(doc: dict[str, Any], state: dict[str, Any], prev: dict[str, Any] | None,
                  source: str) -> Iterator[dict[str, Any]]:
        """The entries of one file after ``state``, chained from it (``state`` is advanced in place)."""
        if doc["prev"] != prev:
            raise IntegrityError(f"{source} does not link to the segment before it", found=doc["prev"], expected=prev)
        entries = doc["entries"]
        if doc["start"]["count"] == state["count"]:
            if doc["start"] != state:
                raise IntegrityError(f"{source} does not start where the chain is", start=doc["start"], chain=state)
        elif not doc["start"]["count"] < state["count"] < doc["start"]["count"] + len(entries) + 1:
            raise IntegrityError(f"{source} does not hold the entries after {state['count']}")
        todo = entries[state["count"] - doc["start"]["count"]:]
        end = M.fold(state, todo, source=source)
        for entry in todo:
            yield entry
        state.update(end)

    # ------------------------------------------------------------------ verification

    def verify(self, root: dict[str, Any], since: dict[str, Any] | None = None, *,
               records: bool = True) -> Verification:
        """Verify the history from ``since`` (an earlier verified root's {count, h}; default everything) through
        ``root``: the chain, and with ``records`` each record's content against its entry. Never raises for what it
        finds; every problem is reported."""
        start = dict(since) if since else {"count": 0, "h": M.GENESIS_H}
        report = Verification(start=start)
        try:
            for entry in self.walk(root, since):
                report.entries += 1
                if records:
                    report.records += 1
                    found = sha256_file(self.root / entry["path"])
                    if found is None:
                        report.problems.append(f"entry {entry['seq']} ({entry['id']}): {entry['path']} is missing")
                    elif found != entry["sha256"]:
                        report.problems.append(f"entry {entry['seq']} ({entry['id']}): {entry['path']} does not hold "
                                               "the content its entry pins")
            report.through = {"count": root["count"], "h": root["head_h"]}
        except (IntegrityError, ValidationFailed) as exc:
            report.problems.append(f"chain: {exc.message}")
        return report

    def unreferenced(self, referenced: set[str]) -> list[str]:
        """History records on disk that no entry references: benign unreachable objects (ADR-0011), for example a
        bundle pre-written by a migration whose commit never happened."""
        found = {p.relative_to(self.root).as_posix() for pattern in RECORD_GLOBS for p in self.root.glob(pattern)
                 if p.is_file()}
        return sorted(found - referenced)

    # ------------------------------------------------------------------ writing (inside a control Session)

    @staticmethod
    def write_record(session: Session, rel: str, content: str) -> str:
        """Stage an immutable history record (a bundle, an annotation, an audit record); its SHA-256."""
        session.write(rel, content, immutable=True, fault="history.after_bundle")
        return sha256_text(content)

    def append(self, session: Session, root: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        """Stage ``items`` (entry fields without ``seq`` and ``h``) as the next entries; the new root. A tail that
        reaches ``SEGMENT_SIZE`` entries is sealed in the same transaction and a new empty tail started, so the cost
        of an append does not depend on how much history there is."""
        tail = self.tail(root)
        seq, start, prev, entries = tail["seq"], dict(tail["start"]), tail["prev"], list(tail["entries"])
        count, h, sealed = root["count"], root["head_h"], root["sealed_head"]
        for fields in items:
            entry = M.new_entry(count + 1, h, fields)
            entries.append(entry)
            count, h = entry["seq"], entry["h"]
            if len(entries) == M.SEGMENT_SIZE:
                text = M.render_file(sealed=True, seq=seq, start=start, prev=prev, entries=entries)
                session.write(M.segment_rel(seq), text, immutable=True, fault="history.mid_seal")
                sealed = prev = {"seq": seq, "sha256": sha256_text(text)}
                seq, start, entries = seq + 1, {"count": count, "h": h}, []
        session.write(M.TAIL_REL, M.render_file(sealed=False, seq=seq, start=start, prev=prev, entries=entries),
                      immutable=False, fault="history.after_tail")
        return {"count": count, "head_h": h, "sealed_head": sealed}


def prewrite(aew_root: Path, rel: str, content: str) -> str:
    """Write an immutable record before the transaction that references it (``Session.prewritten``; plan R8). The
    record must be deterministic: if the file already exists it must hold exactly ``content`` (a retry after an
    interrupted migration), otherwise this refuses. Its SHA-256."""
    digest = sha256_text(content)
    target = aew_root / rel
    found = sha256_file(target)
    if found is not None:
        if found != digest:
            raise IntegrityError(f"{rel} already exists with other content; history records are immutable", path=rel)
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    create_exclusive(target, content)
    faults.hit("history.after_prewrite")
    return digest
