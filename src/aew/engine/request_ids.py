"""Generation-scoped create receipts committed with their control effect."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, NamedTuple

from aew.errors import IdempotencyConflict, IntegrityError, UsageError
from aew.harness.contract import EXPECT_REV
from aew.util import sha256_text

INDEX = "control_requests"
# Same explicit-id alphabet and length as coordination's message id (D-8).
EXPLICIT_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")


class ControlRequest(NamedTuple):
    id: str
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
            digests = {
                name: sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))
                for name, value in arguments.items()
            }
        except (TypeError, ValueError) as exc:
            raise UsageError("request-id arguments must be JSON values") from exc
        return cls(request_id, digests)

    def replay(self, state: dict[str, Any], generation: int, op: str) -> dict[str, Any] | None:
        index = state.get(INDEX)
        if index is None or index["generation"] != generation:
            return None
        entry = index["operations"].get(op, {}).get(self.id)
        if entry is None:
            return None
        before = entry["arguments"]
        changed = sorted(name for name in before.keys() | self.arguments.keys()
                         if before.get(name) != self.arguments.get(name))
        if changed:
            raise IdempotencyConflict(
                f"{op} request {self.id!r} already committed with different arguments: {', '.join(changed)}",
                op=op, request_id=self.id, fields=changed,
            )
        return deepcopy(entry["result"])

    def remember(self, state: dict[str, Any], generation: int, op: str, result: dict[str, Any] | None,
                 revision: int) -> None:
        if result is None:
            raise IntegrityError(f"{op} did not record its request result")
        index = state.get(INDEX)
        if index is None or index["generation"] != generation:
            index = state[INDEX] = {"generation": generation, "operations": {}}
        index["operations"].setdefault(op, {})[self.id] = {
            "arguments": dict(self.arguments), "result": deepcopy(result) | {"revision": revision},
        }


def without_invocation_credential(result: dict[str, Any]) -> dict[str, Any]:
    invocation = result["invocation"]
    return result | {
        "invocation_token": None,
        "credential_replay": {
            "status": "NOT_REPLAYABLE",
            "rotate": f"aew harness launch {invocation} --replace {EXPECT_REV}",
        },
    }
