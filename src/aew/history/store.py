"""Reading, appending and verifying the history manifest of one AEW root (ADR-0011; implementation plan R1, R8).

Every write goes through a control-store ``Session``, so a transition that archives history commits it together with
the hot root at the one ADR-0001 commit point: the records first, then any sealed segment, then the tail. Each of
those writes carries a fault point that crash-safety tests use (``history.after_bundle``, ``history.mid_seal``,
``history.after_tail``).

Reads take a root (``manifest.empty_root()`` shape) and never hold the control lock: sealed segments and records are
immutable, and the tail is checked against the root it is read for. A tail that does not start at the newest sealed
segment's end or does not end at that root (it was replaced since) is reported as an ``IntegrityError``; callers that
read outside the lock copy the root and tail together (ADR-0011 audit, plan R2). Damage a read meets (bytes that are
not UTF-8, a file that cannot be read) is an ``IntegrityError`` too, so verification reports it rather than raising.
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
from aew.util import create_exclusive, load_yaml, sha256_bytes, sha256_file, sha256_text

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
    damaged: list[dict[str, Any]] = field(default_factory=list)  # entries whose record is missing or changed

    @property
    def ok(self) -> bool:
        return not self.problems and self.through is not None


_READ: Any = object()  # read the tail from disk (rather than from a snapshot of its bytes)


class History:
    """The history manifest under ``aew_root``.

    Reads that may run outside the control lock (an audit, R2) take ``tail_raw``: the tail's bytes as copied under
    the lock together with the root (None: there was no tail file). Sealed segments and records are immutable, so
    only the tail needs the snapshot.
    """

    def __init__(self, aew_root: Path) -> None:
        self.root = aew_root

    # ------------------------------------------------------------------ files

    def _read(self, rel: str) -> bytes | None:
        try:
            return (self.root / rel).read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise IntegrityError(f"history file {rel} cannot be read: {exc.strerror or exc}", path=rel) from exc

    @staticmethod
    def _text(raw: bytes, rel: str) -> str:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IntegrityError(f"{rel} is not UTF-8 text", path=rel) from exc

    def segment(self, seq: int) -> tuple[dict[str, Any], str]:
        """Sealed segment ``seq`` and its file hash."""
        rel = M.segment_rel(seq)
        raw = self._read(rel)
        if raw is None:
            raise IntegrityError(f"history segment {rel} is missing", path=rel)
        doc = M.parse_file(self._text(raw, rel), source=rel, sealed=True)
        if doc["seq"] != seq:
            raise IntegrityError(f"{rel} declares itself segment {doc['seq']}", path=rel)
        return doc, sha256_bytes(raw)

    def segment_header(self, seq: int) -> tuple[dict[str, Any], str]:
        """Sealed segment ``seq``'s header (``schema``, ``seq``, ``start``, ``prev``) and its file hash, without
        parsing its entries. The header is rendered before the entries; a file laid out otherwise is parsed whole,
        which is slower but gives the same answer."""
        rel = M.segment_rel(seq)
        raw = self._read(rel)
        if raw is None:
            raise IntegrityError(f"history segment {rel} is missing", path=rel)
        text = self._text(raw, rel)
        cut = text.find("\nentries:")
        try:
            head = load_yaml(text[:cut], source=rel) if cut > 0 else None
        except ValidationFailed:
            head = None
        if not isinstance(head, dict) or not {"schema", "seq", "start", "prev"} <= head.keys():
            head = M.parse_file(text, source=rel, sealed=True)
        if head["schema"] != M.SEGMENT_SCHEMA or head["seq"] != seq:
            raise IntegrityError(f"{rel} is not sealed segment {seq}", path=rel)
        return {k: head[k] for k in ("schema", "seq", "start", "prev")}, sha256_bytes(raw)

    def pinned_segment(self, root: dict[str, Any], seq: int) -> dict[str, Any]:
        """Sealed segment ``seq``, proven to be the one ``root`` pins before it is read from. It starts at its position
        and its entries continue the hash chain, and its file hash is linked to the root through every later sealed
        segment: each one's ``prev`` holds the file hash of the one before, and the newest is the root's
        ``sealed_head``. So any change to any of those files is a contradiction when it is accessed. The later
        segments are only hashed and their headers read, which costs a fraction of a millisecond each."""
        sealed = root["sealed_head"]
        if not sealed or not 1 <= seq <= sealed["seq"]:
            raise IntegrityError(f"history segment {seq} is not sealed under this root")
        rel = M.segment_rel(seq)
        doc, digest = self.segment(seq)
        if doc["start"]["count"] != (seq - 1) * M.SEGMENT_SIZE or (seq == 1 and doc["start"]["h"] != M.GENESIS_H):
            raise IntegrityError(f"{rel} does not start at its position in the history", start=doc["start"])
        end = M.fold(doc["start"], doc["entries"], source=rel)
        pin = {"seq": seq, "sha256": digest}
        for later in range(seq + 1, sealed["seq"] + 1):
            head, later_digest = self.segment_header(later)
            if head["prev"] != pin or (later == seq + 1 and head["start"] != end):
                raise IntegrityError(f"{M.segment_rel(later)} does not link to the segment before it",
                                     found=head["prev"], expected=pin)
            pin = {"seq": later, "sha256": later_digest}
        if pin != sealed:
            raise IntegrityError("the sealed segments do not lead to the one the hot root pins", found=pin,
                                 sealed_head=sealed)
        return doc

    def tail_bytes(self) -> bytes | None:
        """The tail file's bytes, for a snapshot taken under the control lock (None: no tail file yet)."""
        return self._read(M.TAIL_REL)

    def tail(self, root: dict[str, Any], *, tail_raw: Any = _READ) -> dict[str, Any]:
        """The tail for ``root``, checked against it: it follows the root's newest sealed segment and its entries end
        exactly at the root. An empty history may have no tail file yet."""
        validate_def("history", "root", root, source="history root")
        sealed = root["sealed_head"]
        raw = self._read(M.TAIL_REL) if tail_raw is _READ else tail_raw
        if raw is None:
            if root["count"] or sealed:
                raise IntegrityError(f"history tail {M.TAIL_REL} is missing", path=M.TAIL_REL)
            return {"seq": 1, "start": {"count": 0, "h": M.GENESIS_H}, "prev": None, "entries": []}
        doc = M.parse_file(self._text(raw, M.TAIL_REL), source=M.TAIL_REL, sealed=False)
        if doc["prev"] != sealed or doc["seq"] != (sealed["seq"] if sealed else 0) + 1:
            raise IntegrityError(f"{M.TAIL_REL} does not follow the root's newest sealed segment",
                                 tail_prev=doc["prev"], sealed_head=sealed)
        # The tail starts where the newest sealed segment ends (the genesis for the first tail), so its entries are
        # exactly those after that boundary. With the count fixed, ending at the root pins the starting hash too: a
        # different one would need a SHA-256 preimage of ``head_h``.
        boundary = (sealed["seq"] if sealed else 0) * M.SEGMENT_SIZE
        if doc["start"]["count"] != boundary or (not sealed and doc["start"]["h"] != M.GENESIS_H):
            raise IntegrityError(f"{M.TAIL_REL} does not start where the newest sealed segment ends",
                                 tail_start=doc["start"], expected_count=boundary)
        end = M.fold(doc["start"], doc["entries"], source=M.TAIL_REL)
        if end != {"count": root["count"], "h": root["head_h"]}:
            raise IntegrityError(f"{M.TAIL_REL} does not end at the hot root", tail_end=end,
                                 root={"count": root["count"], "h": root["head_h"]})
        return doc

    # ------------------------------------------------------------------ lookup

    def entry(self, root: dict[str, Any], seq: int, *, tail_raw: Any = _READ) -> dict[str, Any]:
        """Entry ``seq`` of the history ``root`` pins (1-based)."""
        if not 1 <= seq <= root["count"]:
            raise IntegrityError(f"history has no entry {seq} (it has {root['count']})")
        sealed = root["sealed_head"]
        if sealed and seq <= sealed["seq"] * M.SEGMENT_SIZE:
            doc = self.pinned_segment(root, M.segment_of(seq))
        else:
            doc = self.tail(root, tail_raw=tail_raw)
        entry = doc["entries"][seq - doc["start"]["count"] - 1]
        if entry["seq"] != seq:
            raise IntegrityError(f"history entry {seq} is out of place")
        return entry

    def walk(self, root: dict[str, Any], since: dict[str, Any] | None = None, *,
             tail_raw: Any = _READ) -> Iterator[dict[str, Any]]:
        """Every entry after ``since`` ({count, h}; default the genesis) through ``root``, in order, checking the chain
        as it goes: that ``since`` is on it, each entry's hash, each file's start and segment link, and that the walk
        ends exactly at ``root``. Raises ``IntegrityError`` at the first inconsistency."""
        validate_def("history", "root", root, source="history root")
        state = dict(since) if since else {"count": 0, "h": M.GENESIS_H}
        if state["count"] > root["count"]:
            raise IntegrityError("the starting point is beyond the current history", since=state, count=root["count"])
        if state["count"] == 0 and state["h"] != M.GENESIS_H:
            raise IntegrityError("an empty starting point must be the genesis hash")
        if state["count"] and self.entry(root, state["count"], tail_raw=tail_raw)["h"] != state["h"]:
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
        doc = self.tail(root, tail_raw=tail_raw)
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
               records: bool = True, tail_raw: Any = _READ) -> Verification:
        """Verify the history from ``since`` (an earlier verified root's {count, h}; default everything) through
        ``root``: the chain, and with ``records`` each record's content against its entry. Never raises for what it
        finds; every problem is reported."""
        start = dict(since) if since else {"count": 0, "h": M.GENESIS_H}
        report = Verification(start=start)
        try:
            for entry in self.walk(root, since, tail_raw=tail_raw):
                report.entries += 1
                if records:
                    report.records += 1
                    try:
                        found = sha256_file(self.root / entry["path"])
                    except OSError as exc:
                        report.problems.append(f"entry {entry['seq']} ({entry['id']}): {entry['path']} cannot be "
                                               f"read: {exc.strerror or exc}")
                        report.damaged.append({"seq": entry["seq"], "kind": entry["kind"], "id": entry["id"]})
                        continue
                    if found is None:
                        report.problems.append(f"entry {entry['seq']} ({entry['id']}): {entry['path']} is missing")
                    elif found != entry["sha256"]:
                        report.problems.append(f"entry {entry['seq']} ({entry['id']}): {entry['path']} does not hold "
                                               "the content its entry pins")
                    if found != entry["sha256"]:
                        report.damaged.append({"seq": entry["seq"], "kind": entry["kind"], "id": entry["id"]})
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
