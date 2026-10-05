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
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew_eval import prereg
from aew_eval.schemas import Invalid, validate

ATTEMPT = "aew/eval-attempt/v1"
RUN = "aew/eval-run/v1"
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


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
        self.runs = directory / "runs"

    # ------------------------------------------------------------------ reading

    def lines(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for n, text in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not text.strip():
                continue
            line = json.loads(text)
            validate(ATTEMPT, line, what=f"{self.path.name} line {n}")
            if line["preregistration_sha256"] != self.prereg_sha256:
                raise Invalid(f"{self.path.name} line {n} belongs to another preregistration")
            out.append(line)
        return out

    def attempts(self) -> dict[str, Attempt]:
        found: dict[str, Attempt] = {}
        for line in self.lines():
            rid = line["run_id"]
            if line["event"] == "registered":
                found[rid] = Attempt(rid, line)
                if line["retry_of"]:
                    found[line["retry_of"]].retries.append(rid)
            else:
                found[rid].finalized = line
        return found

    def status(self) -> dict[str, str]:
        """Every attempt and where it stands: a validity verdict, or ``runner_lost``."""
        return {rid: a.status for rid, a in sorted(self.attempts().items())}

    def _result_path(self, run_id: str) -> Path:
        return self.runs / (run_id.split("/", 1)[1] + ".json")

    # ------------------------------------------------------------------ writing

    def _append(self, line: dict[str, Any]) -> None:
        validate(ATTEMPT, line, what="the attempt line")
        self.dir.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)  # durable before the caller takes any provider action
        finally:
            os.close(fd)

    def register(self, *, run_id: str, cell: str, requested_profile: dict[str, Any],
                 retry_of: str | None = None) -> dict[str, Any]:
        """Register an attempt of one preregistered cell. Call before the first provider or model action."""
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
        rid = record["run_id"]
        attempt = self.attempts().get(rid)
        if attempt is None:
            raise Invalid(f"run {rid} was never registered: an attempt is registered before it runs")
        if attempt.finalized is not None:
            raise Invalid(f"run {rid} is already finalized: a result is immutable (re-analysis is a new artifact)")
        reg = attempt.registered
        expected = {"experiment": reg["experiment"], "preregistration_sha256": self.prereg_sha256}
        if any(record[k] != v for k, v in expected.items()) or record["case"]["id"] != reg["case"] \
                or record["arm"]["id"] != reg["arm"] or record["assignment"]["cell"] != reg["assignment"]["cell"]:
            raise Invalid(f"the result of {rid} does not match its registration (experiment, preregistration, case, "
                          "arm and cell)")
        data = (json.dumps(record, sort_keys=True, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        path = self._result_path(rid)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
        except FileExistsError:
            raise Invalid(f"{path.name} exists without a finalized line: inspect it, never overwrite it") from None
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        digest = hashlib.sha256(data).hexdigest()
        self._append({"schema": ATTEMPT, "event": "finalized", "experiment": reg["experiment"],
                      "preregistration_sha256": self.prereg_sha256, "run_id": rid, "at": _now(),
                      "result_sha256": digest, "validity": record["validity"]["status"]})
        return digest

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
