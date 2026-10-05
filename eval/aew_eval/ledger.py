"""The append-only attempt ledger (evaluation component design v0.2, section 3; decisions 5 and 6).

An experiment's directory holds ``attempts.jsonl`` and ``runs/``:

* :meth:`AttemptLedger.register` appends a ``registered`` line, flushed and synced to disk, **before** the runner
  takes any provider or model action. From then on the attempt counts: a runner killed at any later point leaves it
  visible as ``runner_lost``; it can never vanish from the sample.
* :meth:`AttemptLedger.finalize` publishes the run's ``aew/eval-run/v1`` result once, create-if-absent, and appends a
  ``finalized`` line naming its content hash. A result is never rewritten; :meth:`AttemptLedger.verify` detects an
  edited or missing result.
* One preregistered cell is one attempt. A retry is a new attempt linked to the one it retries, allowed only under the
  frozen retry policy (an attempt whose validity the policy names, at most ``max_retries`` per cell).

Concurrency and durability (independent review of PR #75):

* Each read-check-write (``register``, ``finalize``) holds the experiment's exclusive lock, ``attempts.lock``, across
  processes and threads, so two runners can never both see a cell free. Reading checks the ledger's consistency
  (a run registered twice, a cell attempted twice outside a retry, a forked retry chain, a result finalized twice)
  and refuses an inconsistent one.
* Every write writes all its bytes or raises. Every line ends with a newline, so bytes after the last newline are an
  append that never returned success: readers ignore them, and the next append, under the lock, truncates them
  first. A result is written to a temporary file and published by a rename that never replaces an existing file;
  a published result whose ``finalized`` line is missing (a crash between the two) is completed by finalizing the
  same record again, and refused if it differs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew_eval import prereg
from aew_eval.canonical import sha256_of
from aew_eval.schemas import Invalid, validate

ATTEMPT = "aew/eval-attempt/v1"
RUN = "aew/eval-run/v1"
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
O_BINARY = getattr(os, "O_BINARY", 0)
LOCK_TIMEOUT_S = 120.0


def _write_all(fd: int, data: bytes, what: str) -> None:
    """``os.write`` may write fewer bytes than asked; ``fsync`` never completes the rest."""
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            raise OSError(f"writing {what} made no progress ({len(data) - len(view)} of {len(data)} bytes written)")
        view = view[n:]


@contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    """An exclusive lock on ``path`` across processes and threads (each holder opens its own descriptor)."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | O_BINARY, 0o644)
    try:
        if sys.platform == "win32":
            import msvcrt

            deadline = time.monotonic() + LOCK_TIMEOUT_S
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise Invalid(f"{path.name} stayed locked for {LOCK_TIMEOUT_S:.0f} s") from None
                    time.sleep(0.01)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Attempt:
    run_id: str
    registered: dict[str, Any]
    finalized: dict[str, Any] | None = None
    retries: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """``valid`` and the other validity verdicts once finalized; ``runner_lost`` while it is not."""
        return self.finalized["validity"] if self.finalized else "runner_lost"


class AttemptLedger:
    def __init__(self, directory: Path, frozen: dict[str, Any]) -> None:
        self.dir = directory
        self.frozen = frozen
        self.prereg_sha256 = prereg.verify(frozen)
        self.path = directory / "attempts.jsonl"
        self.lock = directory / "attempts.lock"
        self.runs = directory / "runs"

    # ------------------------------------------------------------------ reading

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.dir.mkdir(parents=True, exist_ok=True)
        with _exclusive(self.lock):
            yield

    def lines(self) -> list[dict[str, Any]]:
        """The complete lines. Bytes after the last newline are a torn append that never returned success: ignored
        here, truncated by the next append."""
        if not self.path.exists():
            return []
        raw = self.path.read_bytes()
        out = []
        for n, chunk in enumerate(raw[:raw.rfind(b"\n") + 1].split(b"\n")[:-1], 1):
            if not chunk.strip():
                continue
            try:
                line = json.loads(chunk.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise Invalid(f"{self.path.name} line {n} is corrupt ({exc}): a complete line is never rewritten, "
                              "so inspect the file") from None
            validate(ATTEMPT, line, what=f"{self.path.name} line {n}")
            if line["preregistration_sha256"] != self.prereg_sha256:
                raise Invalid(f"{self.path.name} line {n} belongs to another preregistration")
            out.append(line)
        return out

    def attempts(self) -> dict[str, Attempt]:
        """Every attempt, refusing a ledger whose lines contradict the one-attempt-per-cell rule."""
        found: dict[str, Attempt] = {}
        cells: dict[str, str] = {}
        for line in self.lines():
            rid = line["run_id"]
            if line["event"] == "registered":
                if rid in found:
                    raise Invalid(f"{self.path.name}: {rid} is registered twice")
                cell = line["assignment"]["cell"]
                retry_of = line["retry_of"]
                if retry_of is None:
                    if cell in cells:
                        raise Invalid(f"{self.path.name}: cell {cell} has two first attempts ({cells[cell]}, {rid})")
                    cells[cell] = rid
                else:
                    original = found.get(retry_of)
                    if original is None or original.registered["assignment"]["cell"] != cell:
                        raise Invalid(f"{self.path.name}: {rid} retries {retry_of}, not an earlier attempt of {cell}")
                    if original.retries:
                        raise Invalid(f"{self.path.name}: {retry_of} is retried twice ({original.retries[0]}, {rid})")
                    original.retries.append(rid)
                found[rid] = Attempt(rid, line)
            else:
                attempt = found.get(rid)
                if attempt is None or attempt.finalized is not None:
                    raise Invalid(f"{self.path.name}: {rid} is finalized "
                                  f"{'twice' if attempt else 'without a registration'}")
                attempt.finalized = line
        return found

    def status(self) -> dict[str, str]:
        """Every attempt and where it stands: a validity verdict, or ``runner_lost``."""
        return {rid: a.status for rid, a in sorted(self.attempts().items())}

    def _result_path(self, run_id: str) -> Path:
        return self.runs / (run_id.split("/", 1)[1] + ".json")

    # ------------------------------------------------------------------ writing

    def _append(self, line: dict[str, Any]) -> None:
        """Append one line, under the lock: a torn tail left by an append that failed is truncated first."""
        validate(ATTEMPT, line, what="the attempt line")
        data = (json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | O_BINARY, 0o644)
        try:
            raw = self.path.read_bytes()
            complete = raw.rfind(b"\n") + 1
            if complete != len(raw):
                os.ftruncate(fd, complete)
            os.lseek(fd, complete, os.SEEK_SET)
            _write_all(fd, data, f"{self.path.name}'s {line['event']} line for {line['run_id']}")
            os.fsync(fd)  # durable before the caller takes any provider action
        finally:
            os.close(fd)

    def register(self, *, run_id: str, cell: str, requested_profile: dict[str, Any],
                 retry_of: str | None = None) -> dict[str, Any]:
        """Register an attempt of one preregistered cell. Call before the first provider or model action."""
        with self._locked():
            return self._register(run_id=run_id, cell=cell, requested_profile=requested_profile, retry_of=retry_of)

    def _register(self, *, run_id: str, cell: str, requested_profile: dict[str, Any],
                  retry_of: str | None) -> dict[str, Any]:
        experiment = self.frozen["experiment"]
        if not RUN_ID.match(run_id) or not run_id.startswith(f"{experiment}/"):
            raise Invalid(f"run id {run_id!r} must be {experiment}/<name>")
        order = {o["cell"]: o for o in self.frozen["assignment"]["order"]}
        if cell not in order:
            raise Invalid(f"{cell} is not a cell of preregistration {experiment!r}")
        attempts = self.attempts()
        if run_id in attempts:
            raise Invalid(f"run {run_id} is already registered: an attempt is counted once")
        same_cell = [a for a in attempts.values() if a.registered["assignment"]["cell"] == cell]
        if retry_of is None:
            if same_cell:
                raise Invalid(f"cell {cell} already has attempt {same_cell[0].run_id}: a further attempt is a retry of "
                              "it, under the preregistered retry policy")
        else:
            self._check_retry(attempts, cell, retry_of, same_cell)
        line = {"schema": ATTEMPT, "event": "registered", "experiment": experiment,
                "preregistration_sha256": self.prereg_sha256, "run_id": run_id, "at": _now(),
                "case": order[cell]["case"], "arm": order[cell]["arm"],
                "assignment": {"cell": cell, "order_index": order[cell]["order_index"]},
                "requested_profile": requested_profile, "retry_of": retry_of}
        self._append(line)
        return line

    def _check_retry(self, attempts: dict[str, Attempt], cell: str, retry_of: str, same_cell: list[Attempt]) -> None:
        policy = self.frozen["validity_rules"]["retry_policy"]
        original = attempts.get(retry_of)
        if original is None or original.registered["assignment"]["cell"] != cell:
            raise Invalid(f"{retry_of} is not an attempt of cell {cell}")
        latest = max(same_cell, key=lambda a: a.registered["at"])
        if latest.run_id != retry_of:
            raise Invalid(f"retry the cell's latest attempt ({latest.run_id}), not {retry_of}")
        if original.status not in policy["allowed_for"]:
            raise Invalid(f"{retry_of} is {original.status}; the preregistered retry policy allows a retry only of "
                          f"{policy['allowed_for'] or 'nothing'}")
        if len(same_cell) - 1 >= policy["max_retries"]:
            raise Invalid(f"cell {cell} has used its {policy['max_retries']} preregistered retries")

    def finalize(self, record: dict[str, Any]) -> str:
        """Publish a registered attempt's result, once. Returns its content hash."""
        validate(RUN, record, what=f"the result of {record.get('run_id')}")
        if "legacy" in record:
            raise Invalid("a mapped historical record is not a result of this ledger")
        with self._locked():
            return self._finalize(record)

    def _mismatches(self, record: dict[str, Any], reg: dict[str, Any]) -> list[str]:
        """What a result claims that its registration or the frozen preregistration contradicts."""
        f = self.frozen
        case = next(c for c in f["cases"] if c["id"] == reg["case"])
        arm = next(a for a in f["arms"] if a["id"] == reg["arm"])
        checks = {
            "experiment": (record["experiment"], reg["experiment"]),
            "preregistration": (record["preregistration_sha256"], self.prereg_sha256),
            "case": (record["case"]["id"], reg["case"]),
            "arm": (record["arm"]["id"], reg["arm"]),
            "cell": ((record["assignment"] or {}).get("cell"), reg["assignment"]["cell"]),
            "assignment order": ((record["assignment"] or {}).get("order_index"), reg["assignment"]["order_index"]),
            "randomization seed": ((record["assignment"] or {}).get("randomization_seed"), f["assignment"]["seed"]),
            "requested profile": (record["profile"]["requested"], reg["requested_profile"]),
            "case fixture hash": (record["case"]["sha256"], case["sha256"]),
            "case oracle hash": (record["case"]["hidden_sha256"], case["hidden_sha256"]),
            "arm kind": (record["arm"]["kind"], arm["kind"]),
            "arm configuration hash": (record["arm"]["config_sha256"], sha256_of(arm["config"])),
        }
        return [name for name, (got, want) in checks.items() if got != want]

    def _finalize(self, record: dict[str, Any]) -> str:
        rid = record["run_id"]
        attempt = self.attempts().get(rid)
        if attempt is None:
            raise Invalid(f"run {rid} was never registered: an attempt is registered before it runs")
        if attempt.finalized is not None:
            raise Invalid(f"run {rid} is already finalized: a result is immutable (re-analysis is a new artifact)")
        reg = attempt.registered
        wrong = self._mismatches(record, reg)
        if wrong:
            raise Invalid(f"the result of {rid} does not match its registration and preregistration: "
                          f"{', '.join(wrong)} (an observed profile goes in profile.observed, never requested)")
        data = (json.dumps(record, sort_keys=True, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        path = self._result_path(rid)
        self._publish(path, data)
        digest = hashlib.sha256(data).hexdigest()
        self._append({"schema": ATTEMPT, "event": "finalized", "experiment": reg["experiment"],
                      "preregistration_sha256": self.prereg_sha256, "run_id": rid, "at": _now(),
                      "result_sha256": digest, "validity": record["validity"]["status"]})
        return digest

    def _publish(self, path: Path, data: bytes) -> None:
        """Write the result to a temporary file, then publish it by a rename that never replaces an existing file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() == data:
                return  # published by a finalize that crashed before its line: this one completes it
            raise Invalid(f"{path.name} exists without a finalized line and differs from this result: inspect it, "
                          "never overwrite it")
        tmp = path.with_name(f".{path.name}.{os.getpid()}.partial")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | O_BINARY, 0o644)
        try:
            _write_all(fd, data, path.name)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            if sys.platform == "win32":
                os.rename(tmp, path)  # refuses an existing target
            else:
                os.link(tmp, path)  # likewise; then the temporary name goes
                os.unlink(tmp)
                dfd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
        except FileExistsError:
            tmp.unlink(missing_ok=True)
            raise Invalid(f"{path.name} appeared while it was being published: inspect it") from None

    def verify(self) -> list[str]:
        """Problems with the published results: a finalized result missing or edited since. Empty when sound."""
        problems = []
        for rid, a in sorted(self.attempts().items()):
            if a.finalized is None:
                continue
            path = self._result_path(rid)
            if not path.is_file():
                problems.append(f"{rid}: its finalized result {path.name} is missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != a.finalized["result_sha256"]:
                problems.append(f"{rid}: {path.name} changed after it was finalized")
        return problems
