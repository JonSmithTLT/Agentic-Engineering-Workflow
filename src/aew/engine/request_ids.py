"""Generation-scoped create receipts committed with their control effect."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, NamedTuple

from aew.errors import IdempotencyConflict, IntegrityError, UsageError
from aew.harness.contract import EXPECT_REV, invocation_of_run
from aew.util import sha256_text

INDEX = "control_requests"
# Same explicit-id alphabet and length as coordination's message id (D-8).
EXPLICIT_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")


def _digest(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


class ControlRequest(NamedTuple):
    id: str
    digest: str
    arguments: dict[str, str]

    @classmethod
    def prepare(cls, request_id: str | None, **arguments: Any) -> ControlRequest | None:
        if request_id is None:
            return None
        if not isinstance(request_id, str) or EXPLICIT_ID.fullmatch(request_id) is None:
            raise UsageError(
                "request_id must be 1–64 characters from A–Z, a–z, 0–9, period, underscore, colon or hyphen"
            )
        try:
            digest = _digest(arguments)
            # These prefixes only diagnose which fields changed. The full digest decides equality.
            digests = {name: _digest(value)[:12] for name, value in arguments.items()}
        except (TypeError, ValueError) as exc:
            raise UsageError("request-id arguments must be JSON values") from exc
        return cls(request_id, digest, digests)

    def replay(self, state: dict[str, Any], generation: int, op: str) -> dict[str, Any] | None:
        index = state.get(INDEX)
        if index is None or index["generation"] != generation:
            return None
        entry = index["operations"].get(op, {}).get(self.id)
        if entry is None:
            return None
        if entry["digest"] != self.digest:
            before = entry["arguments"]
            changed = sorted(name for name in before.keys() | self.arguments.keys()
                             if before.get(name) != self.arguments.get(name))
            description = ", ".join(changed) or "field digest prefixes matched"
            raise IdempotencyConflict(
                f"{op} request {self.id!r} already committed with different arguments: {description}",
                op=op, request_id=self.id, fields=changed,
            )
        return _render(state, op, entry)

    def remember(self, state: dict[str, Any], generation: int, op: str, ref: tuple[str, str] | None,
                 revision: int, metadata: dict[str, Any] | None = None) -> None:
        if ref is None:
            raise IntegrityError(f"{op} did not record its request identity")
        unit, record = ref
        if unit not in state["work"]:
            return
        index = state.get(INDEX)
        if index is None or index["generation"] != generation:
            index = state[INDEX] = {"generation": generation, "operations": {}}
        index["operations"].setdefault(op, {})[self.id] = {
            "arguments": dict(self.arguments), "digest": self.digest,
            "unit": unit, "ref": record, "revision": revision,
            **({"metadata": deepcopy(metadata)} if metadata else {}),
        }


def prune_archived(projected: dict[str, Any], archived: set[str]) -> None:
    index = projected.get(INDEX)
    if index is None or not archived:
        return
    operations = {op: {key: entry for key, entry in receipts.items() if entry["unit"] not in archived}
                  for op, receipts in index["operations"].items()}
    remaining = {op: receipts for op, receipts in operations.items() if receipts}
    if remaining:
        projected[INDEX] = {"generation": index["generation"], "operations": remaining}
    else:
        projected.pop(INDEX)


def _render(state: dict[str, Any], op: str, receipt: dict[str, Any]) -> dict[str, Any]:
    wid, ref = receipt["unit"], receipt["ref"]
    unit = state["work"][wid]
    common = {"ok": True, "replayed": True, "revision": receipt["revision"]}
    metadata = deepcopy(receipt.get("metadata", {}))
    if op == "work.create":
        return common | {"id": wid, "record": unit["record"]} | metadata
    if op == "work.promote":
        return common | {"work_id": unit["promoted_from"], "promoted_to": wid, "decision": ref}
    if op == "plan.propose":
        plan = next(p for p in unit["plans"] if str(p["revision"]) == ref)
        return common | {"work_id": wid, "revision_number": plan["revision"], "path": plan["path"]}
    if op == "harness.launch":
        inv_id = invocation_of_run(ref)
        inv = state["invocations"][inv_id]
        runs = inv["runs"]
        i = next(i for i, run in enumerate(runs) if run["run"] == ref)
        public = ("run", "harness", "launched_at", "kind", "generation", "dispatch")
        return common | {"invocation": inv_id, "run": ref, "superseded": runs[i - 1]["run"] if i else None,
                         "run_record": deepcopy({k: runs[i][k] for k in public if k in runs[i]})}
    inv = state["invocations"][ref]
    # The rotate step is shared by mutating, non-mutating and parent invocations.
    status = f"aew harness status {ref}"
    credential = {"status": "NOT_REPLAYABLE"}
    if inv.get("runs") or inv["status"] != "active":
        credential["next_action"] = status
    else:
        credential["rotate"] = f"aew harness launch {ref} {EXPECT_REV}"
    identity = common | {"invocation": ref, "invocation_token": None, "credential_replay": credential}
    if op == "work.redispatch":
        return identity | {"work_id": wid, "observation": deepcopy(inv["observation"])} | metadata
    result = {"role": inv["role"], "role_card": (inv.get("card") or {}).get("id"), "scope": inv["scope"],
              "evaluated_snapshot": deepcopy(inv.get("snapshot")), "pack": deepcopy(inv.get("pack"))}
    if inv["scope"] == "observation":
        result["subject"] = deepcopy(inv["subject"])
    if inv["scope"] in {"observation", "parent"}:
        result["observation"] = deepcopy(inv["observation"])
    return identity | result | metadata
