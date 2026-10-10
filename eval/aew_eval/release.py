"""The release bundle, the run manifest and the release ledger: the evaluator's side of a release (F19 plan v5 §2.3,
§2.8; ADR-0018 D3, D4, D6; the held-out corpus isolation decision of 2026-10-06, §2).

**The bundle** is built from typed inputs only: the case's :class:`~aew_eval.fixture.Snapshot` (its starting files,
never its manifest), the task's bytes, the arm's frozen entry and the run manifest. It carries no preregistration, no
oracle, no hidden commitment and nothing of another case:

* ``files/<path>``: the starting point, as :func:`aew_eval.fixture.starting_files` gives it;
* ``task.md``: the task statement's bytes, when the case has one;
* ``task.json``: the run id, the case id, the arm (id, kind, configuration), whether it is seeded, and the task file;
* ``run-manifest.json``: the run's terms (``aew/m4h-run-manifest/v1``).

**The run manifest** (interface I2) is what M4-E's ``aew operator grant-publication --manifest`` verifies by its SHA-256
and reads ``task_input_sha256`` from: the seal and treatment hashes, the run, its cell, the caps, and the pre-grant
bounds (``max_publications``, the envelope duration). S12 seals the values; S4 builds and validates the record.

**The release ledger**, ``releases.jsonl`` beside the attempt ledger, gets one event per protocol step, written with
the attempt ledger's durability (one synced, newline-terminated line under the experiment's release lock, a torn tail
truncated by the next append). Each line names the SHA-256 of the line before it, so an edited, inserted or removed
line breaks the chain. The trailing lines, which no later line names, are anchored twice (PR #189 review, F5):

* every append then writes the chain's new head to ``releases.head`` (replaced atomically and synced, under the same
  lock), so removing the last lines, a ``preflight_refused`` refusal or a run's ``finalized`` event among them, no
  longer matches the anchor;
* :meth:`ReleaseLedger.verify` cross-checks the attempt ledger: every attempt registered with a release has its
  ``registered`` event, and every finalized one its ``finalized`` event naming the same result hash.

A crash between an append and its anchor, or an anchor that could not be rewritten (retried briefly, then left: the
append has succeeded once its line is durable), leaves the anchor one line behind; ``verify`` reports that as a lag,
never as removed lines, and the next append repairs it. Every read takes the release lock and reads the file once.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew_eval import fixture
from aew_eval.canonical import canonical
from aew_eval.ledger import _exclusive, append_line, complete_lines  # noqa: PLC2701 (one locking rule for both ledgers)
from aew_eval.schemas import Invalid, validate
from aew_eval.transport import DEFAULT_LIMITS, Entry, Limits, pack

RUN_MANIFEST = "aew/m4h-run-manifest/v1"
EVENT = "aew/m4h-release-event/v1"
GENESIS = hashlib.sha256(EVENT.encode("utf-8")).hexdigest()
ANCHOR_TRIES = 8
TASK_FILE = "task.md"


@dataclass(frozen=True)
class RunTerms:
    """A run's terms as the seal fixes them (S12): the run manifest's inputs other than the run itself."""

    seal_sha256: str
    treatment_sha256: str
    cap_usd: float
    wall_s: float
    max_publications: int
    envelope_duration_s: int


def task_bytes(task: str | None) -> bytes:
    """The task statement exactly as released: UTF-8, LF line ends; empty when the case has none."""
    return b"" if task is None else task.replace("\r\n", "\n").encode("utf-8")


def run_manifest(terms: RunTerms, *, run_id: str, cell: str, task: bytes) -> dict[str, Any]:
    """The run's ``aew/m4h-run-manifest/v1``, validated. ``task_input_sha256`` is the released task's hash."""
    record = {"schema": RUN_MANIFEST, "seal_sha256": terms.seal_sha256, "run_id": run_id, "cell": cell,
              "task_input_sha256": hashlib.sha256(task).hexdigest(),
              "caps": {"usd": terms.cap_usd, "wall_s": terms.wall_s}, "treatment_sha256": terms.treatment_sha256,
              "max_publications": terms.max_publications, "envelope_duration_s": terms.envelope_duration_s}
    validate(RUN_MANIFEST, record, what=f"the run manifest of {run_id}")
    return record


@dataclass(frozen=True)
class Bundle:
    tar: bytes
    sha256: str  # the bundle manifest's hash: the attempt's release.bundle_sha256
    run_manifest_sha256: str
    task_input_sha256: str


def build_bundle(snap: fixture.Snapshot, *, run_id: str, arm: dict[str, Any], seeded: bool, task: bytes,
                 manifest: dict[str, Any], limits: Limits = DEFAULT_LIMITS) -> Bundle:
    """The release bundle of one run. ``arm`` is the frozen preregistration's arm entry; only its id, kind and
    configuration cross."""
    if manifest["run_id"] != run_id or manifest["task_input_sha256"] != hashlib.sha256(task).hexdigest():
        raise Invalid(f"the run manifest is not {run_id}'s, or not for this task")
    descriptor = {"run_id": run_id, "case": snap.case.id,
                  "arm": {"id": arm["id"], "kind": arm["kind"], "config": arm["config"]},
                  "seeded": seeded, "task_file": TASK_FILE if task else None}
    entries = [Entry(f"files/{rel}", "file", data=data)
               for rel, data in fixture.starting_files(snap, seeded=seeded).items()]
    manifest_bytes = canonical(manifest)
    entries += [Entry("task.json", "file", data=canonical(descriptor)),
                Entry("run-manifest.json", "file", data=manifest_bytes)]
    if task:
        entries.append(Entry(TASK_FILE, "file", data=task))
    data, digest = pack(entries, limits=limits)
    return Bundle(data, digest, hashlib.sha256(manifest_bytes).hexdigest(), manifest["task_input_sha256"])


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ReleaseLedger:
    """An experiment's ``releases.jsonl``: append-only, hash-chained, synced like the attempt ledger."""

    def __init__(self, directory: Path, experiment: str) -> None:
        self.dir = directory
        self.experiment = experiment
        self.path = directory / "releases.jsonl"
        self.lock = directory / "releases.lock"
        self.anchor = directory / "releases.head"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.dir.mkdir(parents=True, exist_ok=True)
        with _exclusive(self.lock):
            yield

    def _raw_lines(self) -> list[bytes]:
        """The complete lines, from one read of the file."""
        return complete_lines(self.path).split(b"\n")[:-1]

    def _parse(self, raw: list[bytes]) -> list[dict[str, Any]]:
        out = []
        for n, chunk in enumerate(raw, 1):
            try:
                line = json.loads(chunk.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise Invalid(f"{self.path.name} line {n} is corrupt ({exc})") from None
            validate(EVENT, line, what=f"{self.path.name} line {n}")
            out.append(line)
        return out

    def lines(self) -> list[dict[str, Any]]:
        """Every complete line, parsed and validated (a torn tail is ignored, as in the attempt ledger), read once
        under the release lock, so a concurrent append is never seen half-way."""
        with self._locked():
            return self._parse(self._raw_lines())

    def head(self) -> str:
        """The chain's head: the SHA-256 of the last complete line (the genesis hash when there is none)."""
        with self._locked():
            raw = self._raw_lines()
        return hashlib.sha256(raw[-1]).hexdigest() if raw else GENESIS

    def append(self, run_id: str, event: str, data: dict[str, Any] | None = None) -> str:
        """Append one event; returns the chain's new head (this line's hash). Once the line is durable the append
        has succeeded: a failure to rewrite the anchor afterwards never fails it, and leaves the anchor one line
        behind, which :meth:`verify` reports as a lag (PR #189 re-review, M2)."""
        with self._locked():
            raw = self._raw_lines()
            line = {"schema": EVENT, "seq": len(raw), "prev_sha256": hashlib.sha256(raw[-1]).hexdigest()
                    if raw else GENESIS, "experiment": self.experiment, "run_id": run_id, "event": event,
                    "at": _now(), "data": data or {}}
            validate(EVENT, line, what="the release event")
            encoded = canonical(line)
            append_line(self.path, encoded + b"\n", f"{self.path.name}'s {event} event for {run_id}")
            head = hashlib.sha256(encoded).hexdigest()
            self._write_anchor(head)
            return head

    def _write_anchor(self, head: str) -> bool:
        """Rewrite the anchor; retried briefly (a Windows reader holding the file refuses the rename). False when it
        could not be written: the line it anchors is durable either way."""
        for attempt in range(ANCHOR_TRIES):
            tmp = self.anchor.with_name(f".{self.anchor.name}.{os.getpid()}.{secrets.token_hex(6)}.partial")
            try:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_BINARY", 0), 0o644)
                try:
                    os.write(fd, head.encode("ascii") + b"\n")
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.replace(tmp, self.anchor)
                return True
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                time.sleep(0.02 * (attempt + 1))
        return False

    def verify(self, heads: Iterable[str] = (), attempts: Mapping[str, Any] | None = None) -> list[str]:
        """Problems with the chain, read once under the release lock: a line that does not name its predecessor's
        hash or breaks the sequence, a line of another experiment, a chain that does not end at its anchor (an anchor
        exactly one line behind is reported as a lag, an append whose anchor was not written; one naming no line of
        the chain, or further behind, as removed lines), any of ``heads`` (the chain hashes run records name) no
        longer in it, and, given ``attempts`` (:meth:`AttemptLedger.attempts`), a released attempt whose
        ``registered`` or ``finalized`` event is missing or names another result. Empty when sound."""
        with self._locked():
            raw = self._raw_lines()
            anchor = self.anchor.read_text(encoding="ascii").strip() if self.anchor.is_file() else None
        problems = []
        try:
            parsed = self._parse(raw)
        except Invalid as exc:
            return [str(exc)]
        chain = [GENESIS]
        for n, (chunk, line) in enumerate(zip(raw, parsed, strict=True)):
            if line["seq"] != n:
                problems.append(f"line {n + 1} has sequence number {line['seq']}: a line was removed or inserted")
            if line["prev_sha256"] != chain[-1]:
                problems.append(f"line {n + 1} does not follow the line before it: the chain was edited")
            if line["experiment"] != self.experiment:
                problems.append(f"line {n + 1} belongs to experiment {line['experiment']!r}")
            chain.append(hashlib.sha256(chunk).hexdigest())
        hashes = set(chain[1:])
        problems += [f"the chain no longer holds {h}, which a run record names" for h in heads if h not in hashes]
        named = anchor or GENESIS
        if named != chain[-1]:
            if len(chain) >= 2 and named == chain[-2]:
                problems.append(f"the anchor lags the chain by one line (it names {named}; the chain ends at "
                                f"{chain[-1]}): an append whose anchor was not written, not a removal")
            else:
                problems.append(f"the chain ends at {chain[-1]}, but its anchor names {anchor or 'no line'}: its "
                                "last lines were removed")
        for rid, attempt in sorted((attempts or {}).items()):
            if "release" not in attempt.registered:
                continue
            events = {ln["event"]: ln for ln in parsed if ln["run_id"] == rid}
            if "registered" not in events:
                problems.append(f"{rid} was registered with a release, and its registered event is missing")
            if attempt.finalized is not None:
                fin = events.get("finalized")
                if fin is None or fin["data"].get("result_sha256") != attempt.finalized["result_sha256"]:
                    problems.append(f"{rid} is finalized, and its finalized event is missing or names another "
                                    "result")
        return problems
