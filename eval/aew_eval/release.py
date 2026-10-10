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
truncated by the next append). Each line names the SHA-256 of the line before it, so an edited or removed line breaks
the chain; the run record names the chain's head after its collection, which also catches a removed last line.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
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

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.dir.mkdir(parents=True, exist_ok=True)
        with _exclusive(self.lock):
            yield

    def _raw_lines(self) -> list[bytes]:
        return [chunk for chunk in complete_lines(self.path).split(b"\n")[:-1]]

    def lines(self) -> list[dict[str, Any]]:
        """Every complete line, parsed and validated (a torn tail is ignored, as in the attempt ledger)."""
        out = []
        for n, chunk in enumerate(self._raw_lines(), 1):
            try:
                line = json.loads(chunk.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise Invalid(f"{self.path.name} line {n} is corrupt ({exc})") from None
            validate(EVENT, line, what=f"{self.path.name} line {n}")
            out.append(line)
        return out

    def head(self) -> str:
        """The chain's head: the SHA-256 of the last complete line (the genesis hash when there is none)."""
        raw = self._raw_lines()
        return hashlib.sha256(raw[-1]).hexdigest() if raw else GENESIS

    def append(self, run_id: str, event: str, data: dict[str, Any] | None = None) -> str:
        """Append one event; returns the chain's new head (this line's hash)."""
        with self._locked():
            raw = self._raw_lines()
            line = {"schema": EVENT, "seq": len(raw), "prev_sha256": hashlib.sha256(raw[-1]).hexdigest()
                    if raw else GENESIS, "experiment": self.experiment, "run_id": run_id, "event": event,
                    "at": _now(), "data": data or {}}
            validate(EVENT, line, what="the release event")
            encoded = canonical(line)
            append_line(self.path, encoded + b"\n", f"{self.path.name}'s {event} event for {run_id}")
            return hashlib.sha256(encoded).hexdigest()

    def verify(self, heads: Iterable[str] = ()) -> list[str]:
        """Problems with the chain: a line that does not name its predecessor's hash or breaks the sequence, a line of
        another experiment, and any of ``heads`` (the chain hashes run records name) no longer in it. Empty when
        sound."""
        problems = []
        prev = GENESIS
        hashes = set()
        try:
            parsed = self.lines()
        except Invalid as exc:
            return [str(exc)]
        for n, (chunk, line) in enumerate(zip(self._raw_lines(), parsed, strict=True)):
            if line["seq"] != n:
                problems.append(f"line {n + 1} has sequence number {line['seq']}: a line was removed or inserted")
            if line["prev_sha256"] != prev:
                problems.append(f"line {n + 1} does not follow the line before it: the chain was edited")
            if line["experiment"] != self.experiment:
                problems.append(f"line {n + 1} belongs to experiment {line['experiment']!r}")
            prev = hashlib.sha256(chunk).hexdigest()
            hashes.add(prev)
        problems += [f"the chain no longer holds {h}, which a run record names" for h in heads if h not in hashes]
        return problems
