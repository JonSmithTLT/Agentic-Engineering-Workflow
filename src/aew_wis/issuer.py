"""The issuer's core: WIS-02's read, its held state, attestation and renewal, and the witness (WIS-02 to WIS-06, WIS-09).

It reads its one store through a :class:`View` (the bound directory, and what the kernel shows of it) and takes no
content from any caller (round 1, B-1): its only inputs are the store's files, root's anchor and its own clock. The
service (:mod:`aew_wis.service`) drives it; tests drive it with a view onto a store the real engine wrote.

**Each read** takes ``control.yaml`` once and applies WIS-02's checks in its order, the root-field row first; the
sequence and every outcome follow the adopted reference model (``verify_wis.py``'s ``Issuer._read``), with the
engine's own rules where the reference has labelled stand-ins (YAML, the checksum trailer, 256-record segments and their
overflow payloads; :mod:`aew_wis.engine_rules`). A record resolves as the engine's lock-free reader resolves it: from
its per-revision file, else from its verified sealed segment, the two required equal where both exist. A latching
outcome sets the head to ``CHAIN_FORK``, and nothing is attested again until root re-anchors (WIS-11); a non-latching
one changes nothing. Where the checks cannot run at all (the mount table or ``statx`` unreadable), the read is
``STORE_UNREADABLE``: that is no evidence of a replacement, and it does not latch.

**The held state** is one file per anchor (``held-<epoch>.json`` in the ``StateDirectory``), written to a temporary
file, fsynced, renamed over the old one and the directory fsynced, whenever what it holds changes: the pinned head
(revision, ``h``, the whole head record and ``control_sha256``), the latch, the latest attestation and the few before
it. The head record's ``h`` commits, by the hash chain the issuer verified record by record from the anchor, to every
record it accepted (WIS-02's "every transition record it has accepted"); the records themselves stay in the store. A
new anchor (a new epoch) starts a new file, which is how a re-anchor clears a latch; a held file that cannot be read
for the current anchor is treated as latched.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from aew_wis import engine_rules as R
from aew_wis import facts as F
from aew_wis import wire as W
from aew_wis.identity import Identity, IdentityUnavailable

HELD_SCHEMA = "aew/wis-held/v1"
RECENT = 4  # attestations kept for the witness besides the latest: a superseded one answers current: false
_HEX64 = re.compile(r"[0-9a-f]{64}")
_STORE_REF = re.compile(r"store:[0-9a-f]{32}")
_FS_ID = re.compile(r"(uuid:[0-9A-Za-z-]{1,64}|dev:[0-9]{1,4}:[0-9]{1,7})")
_INSTANCE = re.compile(r"[0-9a-f]{32}")
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)  # Windows: no newline translation (the state is canonical bytes)
ANCHOR_KEYS = ("store_ref", "store_fs_id", "store_ino", "store_btime", "store_fs_path", "revision", "h", "anchored_at")


class View(Protocol):
    """What the issuer sees of its store: ``root`` holds ``state/`` (the bound store directory) as an AEW root
    does, and :meth:`probe` gives the bound directory's identity, its bind's root field as ``fs_path``, and its owner."""

    root: Path

    def probe(self) -> tuple[Identity, int]: ...


class AnchorRefused(ValueError):
    """Root's anchor is not one the issuer may run with: it refuses to start."""


# ---------------------------------------------------------------------------------------------- root's anchor

def check_anchor(anchor: Any, instance: str) -> dict[str, Any]:
    """WIS-11's anchor record, as the wire states it, for this instance: ``store_ref`` is ``store:<instance>``."""
    if not _INSTANCE.fullmatch(instance):
        raise AnchorRefused(f"the instance name {instance!r} is not 32 lowercase hex characters")
    if not isinstance(anchor, dict) or set(anchor) != set(ANCHOR_KEYS):
        raise AnchorRefused(f"the anchor must have exactly {', '.join(ANCHOR_KEYS)}")

    def num(v: Any, low: int) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and v >= low

    a = anchor
    problems = [k for k, ok in (
        ("store_ref", isinstance(a["store_ref"], str) and _STORE_REF.fullmatch(a["store_ref"])),
        ("store_fs_id", isinstance(a["store_fs_id"], str) and _FS_ID.fullmatch(a["store_fs_id"])),
        ("store_ino", num(a["store_ino"], 1)),
        ("store_btime", a["store_btime"] is None or num(a["store_btime"], 0)),
        ("store_fs_path", isinstance(a["store_fs_path"], str) and a["store_fs_path"].startswith("/")
         and len(a["store_fs_path"]) <= 4096),
        ("revision", num(a["revision"], 0)),
        ("h", isinstance(a["h"], str) and _HEX64.fullmatch(a["h"])),
        ("anchored_at", isinstance(a["anchored_at"], str) and _parses(a["anchored_at"])),
    ) if not ok]
    if problems:
        raise AnchorRefused(f"the anchor's {', '.join(problems)} {'is' if len(problems) == 1 else 'are'} not valid")
    if a["store_ref"] != W.STORE_REF_PREFIX + instance:
        raise AnchorRefused(f"the anchor names {a['store_ref']}, not this instance's store:{instance}")
    return dict(anchor)


def _parses(s: str) -> bool:
    try:
        W.parse_time(s)
    except ValueError:
        return False
    return True


def read_root_file(path: Path) -> bytes:
    """A file root wrote for the issuer (its anchor): refused unless every directory from the first one below ``/``
    down to it, and the file itself, is owned by root, not writable by group or others, and not a symbolic link."""
    parts = path.parts
    for i in range(2, len(parts) + 1):
        p = Path(*parts[:i])
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise AnchorRefused(f"{p} is not root's: a symbolic link, not owned by root, or writable by group or others")
    return path.read_bytes()


# ---------------------------------------------------------------------------------------------- the held state

@dataclass
class Held:
    head: dict[str, Any]
    latched_by: str | None = None
    head_record: dict[str, Any] | None = None
    control_sha256: str | None = None
    latest: dict[str, Any] | None = None
    recent: list[dict[str, Any]] = field(default_factory=list)
    gap_since: str | None = None

    def to_json(self, epoch: str) -> bytes:
        return R.canonical_json({"schema": HELD_SCHEMA, "epoch": epoch, "head": self.head, "latched_by": self.latched_by,
                                 "head_record": self.head_record, "control_sha256": self.control_sha256,
                                 "latest": self.latest, "recent": self.recent, "gap_since": self.gap_since})

    @classmethod
    def fresh(cls, anchor: dict[str, Any]) -> Held:
        return cls(head={"revision": anchor["revision"], "h": anchor["h"], "state": W.ANCHORED})

    @classmethod
    def from_json(cls, raw: bytes, epoch: str) -> Held:
        doc = json.loads(raw)
        if not isinstance(doc, dict) or doc.get("schema") != HELD_SCHEMA or doc.get("epoch") != epoch:
            raise ValueError("not this anchor's held state")
        head = doc["head"]
        if not (isinstance(head, dict) and isinstance(head.get("revision"), int) and isinstance(head.get("h"), str)
                and head.get("state") in (W.ANCHORED, W.FORKED)):
            raise ValueError("the held head is not valid")
        return cls(head=head, latched_by=doc["latched_by"], head_record=doc["head_record"],
                   control_sha256=doc["control_sha256"], latest=doc["latest"], recent=list(doc["recent"]),
                   gap_since=doc["gap_since"])


def held_path(state_dir: Path, epoch: str) -> Path:
    return state_dir / f"held-{epoch.split(':', 1)[1]}.json"


def write_atomically(path: Path, data: bytes) -> None:
    """Temporary file, fsync, rename over the old one, fsync the directory: a stop mid-write leaves the old state or
    the new one (WIS-01)."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW | _O_BINARY, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    if hasattr(os, "O_DIRECTORY"):
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


# ---------------------------------------------------------------------------------------------- the issuer

class Issuer:
    """One store's issuer. Its public surface takes no content from any caller: ``read``, ``witness`` and the
    accessors (the reference's N02)."""

    def __init__(self, *, instance: str, anchor: dict[str, Any], view: View, state_dir: Path, signer: Any,
                 tripwires: W.Tripwires) -> None:
        problems = tripwires.problems()
        if problems:
            raise AnchorRefused("; ".join(problems))
        self.anchor = check_anchor(anchor, instance)
        self.store_ref = self.anchor["store_ref"]
        self.issuer_ref = f"issuer:aew-wis-issuer@{instance}"
        self.wis_epoch = W.epoch_of(self.anchor)
        self.view, self.state_dir, self.signer, self.tripwires = view, state_dir, signer, tripwires
        self.path = held_path(state_dir, self.wis_epoch)
        self.last_read, self.last_read_at = "OK", self.anchor["anchored_at"]
        self.reads = 0  # reads this process made: the witness answers ISSUER_UNAVAILABLE until the first
        self.stopping = False  # set by the service on a stop signal
        self.held = self._load()

    def _load(self) -> Held:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return Held.fresh(self.anchor)
        try:
            return Held.from_json(raw, self.wis_epoch)
        except (ValueError, KeyError, TypeError):
            # The held state for this anchor exists and cannot be read: whether it was latched is unknown, so it is
            # latched, until root re-anchors (a new epoch, a new file).
            held = Held.fresh(self.anchor)
            held.head["state"], held.latched_by = W.FORKED, "CHAIN_FORK"
            return held

    def _save(self) -> None:
        write_atomically(self.path, self.held.to_json(self.wis_epoch))

    @property
    def head(self) -> dict[str, Any]:
        return self.held.head

    @property
    def latest(self) -> dict[str, Any] | None:
        return self.held.latest

    # ------------------------------------------------------------------ WIS-02

    def read(self, now: datetime) -> str:
        """One read of the store: its outcome. Attests on a new head and renews by this re-read (WIS-04, WIS-05)."""
        outcome = self._read(now)
        changed = False
        if outcome in W.LATCHING and self.held.head["state"] != W.FORKED:
            self.held.head["state"], self.held.latched_by = W.FORKED, outcome  # until root re-anchors (WIS-11)
            changed = True
        gap = W.iso(now) if outcome == "REVISION_GAP" else None
        if (gap is None) != (self.held.gap_since is None):
            self.held.gap_since, changed = gap, True
        if changed:
            self._save()
        self.last_read, self.last_read_at = outcome, W.iso(now)
        self.reads += 1
        return outcome

    def gap_age(self, now: datetime) -> timedelta | None:
        """How long a ``REVISION_GAP`` has persisted; an hour of it is a reason for root to re-anchor (WIS-02)."""
        return now - W.parse_time(self.held.gap_since) if self.held.gap_since else None

    def _resolve(self, revision: int, since: int) -> tuple[str, dict[str, Any] | None]:
        """A record as the engine's lock-free reader resolves it: ``("OK", record or None)``, ``("BROKEN", None)``
        when its sealed segment fails verification, ``("FORK", None)`` when its file and its sealed copy differ."""
        unsealed = R._read_record(self.view.root, revision)
        index = R.segment_of(revision)
        # As LogView caches them for one reader: a segment is immutable once published, so one read loads each once;
        # one found absent is looked up again whenever a revision is missing from the unsealed side (a compaction
        # publishes the segment before it prunes the files).
        if index not in self._segments or (unsealed is None and self._segments[index] is None):
            try:
                self._segments[index] = R.load_segment(self.view.root, index, since)
            except (R.IntegrityError, R.ValidationFailed):  # the second: an overflow payload that does not parse
                return "BROKEN", None  # an honest engine verifies a segment before it prunes, so never publishes one
        segment = self._segments[index]
        sealed = segment.record(revision) if segment is not None else None
        if unsealed is not None and sealed is not None and unsealed != sealed:
            return "FORK", None
        return "OK", unsealed if unsealed is not None else sealed

    def _read(self, now: datetime) -> str:
        self._segments: dict[int, R.Segment | None] = {}  # this read's sealed segments (:meth:`_resolve`)
        held, head = self.held, self.held.head
        if head["state"] == W.FORKED:
            return "CHAIN_FORK"
        try:
            ident, _owner = self.view.probe()
        except IdentityUnavailable:
            return "STORE_UNREADABLE"
        a = self.anchor
        if ident.fs_path != a["store_fs_path"]:
            return "STORE_REPLACED"  # the bound directory was renamed or deleted (review R3-3)
        if (ident.fs_id, ident.ino, ident.btime) != (a["store_fs_id"], a["store_ino"], a["store_btime"]):
            return "STORE_REPLACED"  # another directory is at the store's path (review R2-1, R3-4)
        try:
            raw = (self.view.root / R.CONTROL_REL).read_bytes()
        except OSError:
            return "STORE_UNREADABLE"
        try:
            body = R.control_body(raw, source=R.CONTROL_REL)
        except UnicodeDecodeError:
            return "STORE_UNREADABLE"
        except R.IntegrityError:
            return "CHECKSUM_INVALID"
        try:
            state = R.load_yaml(body, source=R.CONTROL_REL)
            top, last, since = _control_shape(state)
            facts = F.facts(state)
        except (R.ValidationFailed, F.NotAFact, ValueError):
            return "STORE_UNREADABLE"
        if top < head["revision"]:
            return "CHAIN_FORK"  # history went backwards
        if top == head["revision"]:
            expect = held.head_record or {"revision": head["revision"], "h": head["h"]}
            if (last if held.head_record else {"revision": last["revision"], "h": last["h"]}) != expect:
                return "CHAIN_FORK"  # another record at the held head
            if held.control_sha256 is not None and W.sha(raw) != held.control_sha256:
                return "CHAIN_FORK"  # the content changed under the same revision (round 1, M-2)
            if held.head_record is None:
                held.head_record, held.control_sha256 = last, W.sha(raw)
                self._save()
            latest = held.latest
            if (latest is None or latest["key_id"] != self.signer.key_id
                    or W.parse_time(latest["valid_until"]) - now < timedelta(seconds=self.tripwires.renew_before)):
                self._attest(facts, raw, now)  # WIS-05: a renewal is the issuer's own re-read
            return "OK"
        try:
            how, at_head = self._resolve(head["revision"], since)
            if how == "BROKEN":
                return "CHAIN_BROKEN"
            if how == "FORK":
                return "CHAIN_FORK"  # a record's file and its sealed copy differ
            if at_head is None and head["revision"] != a["revision"]:
                return "REVISION_GAP"
            if at_head is not None and (at_head != held.head_record if held.head_record else at_head.get("h") != head["h"]):
                return "CHAIN_FORK"  # a past record was rewritten (round 1, m-1)
            recs = []
            for r in range(head["revision"] + 1, top):
                how, rec = self._resolve(r, since)
                if how == "BROKEN":
                    return "CHAIN_BROKEN"
                if how == "FORK":
                    return "CHAIN_FORK"
                if rec is None:
                    return "REVISION_GAP"  # in neither its file nor a segment; an hour of this is a reason to re-anchor
                recs.append(rec)
            recs.append(last)  # the newest record is in control.yaml whole; its log copy may lag (store._post_commit)
            how, logged = self._resolve(top, since)
        except (OSError, R.ValidationFailed, UnicodeDecodeError):
            return "STORE_UNREADABLE"
        prev = head["h"]
        for r, rec in zip(range(head["revision"] + 1, top + 1), recs, strict=True):
            try:
                ok = isinstance(rec, dict) and rec.get("revision") == r and rec.get("h") == R.transition_hash(prev, rec)
            except (TypeError, ValueError):
                ok = False
            if not ok:
                return "CHAIN_BROKEN"
            prev = rec["h"]
        if how == "BROKEN":
            return "CHAIN_BROKEN"
        if last["revision"] != top or how == "FORK" or (logged is not None and logged != last):
            return "STATE_MISMATCH"
        head.update(revision=top, h=last["h"])
        held.head_record, held.control_sha256 = last, W.sha(raw)
        self._attest(facts, raw, now)
        return "OK"

    # ------------------------------------------------------------------ WIS-04 to WIS-06

    def _attest(self, facts: dict[str, Any], raw: bytes, now: datetime) -> dict[str, Any] | None:
        if self.stopping:
            return None  # WIS-01: on a stop signal, it attests nothing more
        unsigned = W.attestation(issuer_ref=self.issuer_ref, key_id=self.signer.key_id, store_ref=self.store_ref,
                                 wis_epoch=self.wis_epoch, revision=self.held.head["revision"], h=self.held.head["h"],
                                 control_sha256=W.sha(raw), issued_at=now, validity=self.tripwires.validity,
                                 facts=facts)
        a = W.seal(unsigned, self.signer.sign)
        self.held.recent = [*([self.held.latest] if self.held.latest else []), *self.held.recent][:RECENT]
        self.held.latest = a
        self._save()
        return a

    def current(self, a: dict[str, Any], now: datetime) -> bool:
        """WIS-06: only the latest attestation, under the current key, before its ``valid_until``, while ANCHORED."""
        latest = self.held.latest
        return (latest is not None and a["proof_ref"] == latest["proof_ref"] and a["key_id"] == self.signer.key_id
                and now < W.parse_time(a["valid_until"]) and self.held.head["state"] == W.ANCHORED)

    def witness(self, proof_ref: str, peer_uid: int, operator_uid: int, now: datetime) -> tuple[int, dict[str, Any]]:
        """WIS-09: ``GET /wis/v1/attestations/{proof_ref}``. ``(status, body)``: a ``WitnessResponse``, or a
        ``Problem`` (``PEER_NOT_PERMITTED`` for any peer whose UID is not the operator's)."""
        if peer_uid != operator_uid:
            return 403, W.problem("PEER_NOT_PERMITTED")
        if self.reads == 0 or self.stopping:
            return 503, W.problem("ISSUER_UNAVAILABLE")  # it has not read its store since it started, or is stopping
        found = next((a for a in ([self.held.latest] if self.held.latest else []) + self.held.recent
                      if a["proof_ref"] == proof_ref), None)
        latest = self.held.latest
        if found is None or latest is None:
            return 404, W.problem("NOT_FOUND")
        head = {"store_ref": self.store_ref, "revision": self.held.head["revision"], "h": self.held.head["h"],
                "proof_ref": latest["proof_ref"], "state": self.held.head["state"], "last_read_at": self.last_read_at,
                "last_read": self.last_read}
        return 200, W.witness_response(found, current=self.current(found, now), head=head)


def _control_shape(state: Any) -> tuple[int, dict[str, Any], int]:
    """``(revision, last_transition, outbox.since)`` of a parsed control state, or ``ValueError``: what WIS-02's
    third row requires to be there (a revision, a hash-chained ``last_transition`` and the work units)."""
    if not isinstance(state, dict):
        raise ValueError("the control state is not a mapping")
    top, last, outbox = state.get("revision"), state.get("last_transition"), state.get("outbox")
    if isinstance(top, bool) or not isinstance(top, int) or top < 0:
        raise ValueError("the control state has no revision")
    if not (isinstance(last, dict) and isinstance(last.get("revision"), int) and isinstance(last.get("h"), str)
            and _HEX64.fullmatch(last["h"])):
        raise ValueError("the control state has no hash-chained last_transition")
    since = outbox.get("since") if isinstance(outbox, dict) else None
    if isinstance(since, bool) or not isinstance(since, int) or since < 0:
        raise ValueError("the control state has no outbox start")
    return top, last, since
