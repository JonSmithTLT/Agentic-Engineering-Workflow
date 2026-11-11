"""Bounded Lead diagnostics and a local traceback record for the operator."""

from __future__ import annotations

import json
import logging
import re
import traceback
import unicodedata
from pathlib import Path
from uuid import uuid4

from aew import errors
from aew.harness import tool_calls
from aew.harness.contract import CREDENTIAL_SHAPED, redact
from aew.util import utc_now

DEFECT_LOG_REL = "local/lead/defects.jsonl"
# Keep the most recent end of the traceback, including the exception, within a small fraction of one rotated file.
MAX_TRACE = 16 * 1024
# Match surface/readable.py's ROW * WHY_ROWS. Count JSON escapes as well so non-ASCII causes fit on the wire.
MAX_MESSAGE = 72 * 6
# A message plus seven bounded fields and the JSON envelope fit in two KiB (the per-call telemetry budget).
MAX_ERROR_BYTES = 2048
_DETAIL_FIELDS = ("op", "at", "exception", "cause_code", "defect", "committed", "stage_intent")
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.-]+\Z")
# Four labels of this size leave room in the message for the record ID, recovery step and cause.
_MESSAGE_FIELD = 48
log = logging.getLogger(__name__)


def redact_text(text: str) -> str:
    return CREDENTIAL_SHAPED.sub("<redacted>", redact(text))


def field(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = redact_text(value)
    return cleaned[:tool_calls.MAX_FIELD] if _IDENTIFIER.fullmatch(cleaned) else "<unknown>"


def bounded_message(text: str, limit: int = MAX_MESSAGE, *, authored: bool = True) -> str:
    """Single-line authored text, with a bound that also holds for JSON's ASCII representation."""
    text = " ".join("".join(" " if c.isspace() else c for c in redact_text(text)
                            if c.isspace() or not unicodedata.category(c).startswith("C")).split())
    if authored:
        text = text.replace("`", "｀")
    used = 0
    for index, char in enumerate(text):
        used += len(json.dumps(char)) - 2
        if used > limit:
            return text[:index].rstrip()
    return text


def public_details(exc: errors.Defect) -> dict[str, str | int | None]:
    """The only fields a DEFECT may send to MCP."""
    out: dict[str, str | int | None] = {}
    for key in _DETAIL_FIELDS:
        value = exc.details.get(key)
        if key == "committed":
            out[key] = value if type(value) is int and 0 <= value <= 2**63 - 1 else None
        else:
            out[key] = field(value) if isinstance(value, str) else None
    return out


def record(aew_root: Path | None, exc: Exception, *, defect: str, op: str, step: str, ingress: str,
           exception: str, cause_code: str | None) -> None:
    """Keep the redacted traceback in local telemetry, never in a tool result."""
    try:
        if aew_root is not None:
            trace = redact_text("".join(traceback.format_exception(exc)))
            tool_calls.append(aew_root, {"time": utc_now(), "defect": defect, "op": op, "step": step,
                                         "ingress": field(ingress), "exception": exception, "cause_code": cause_code,
                                         "traceback": trace[-MAX_TRACE:]}, log_rel=DEFECT_LOG_REL)
    except Exception:  # noqa: BLE001  defect telemetry must never replace the original failure
        log.warning("the defect log dropped record %s", defect)


def report(aew_root: Path | None, exc: Exception, *, op: str, at: str, ingress: str, committed: int | None,
           stage_intent: str | None, next_action: str) -> errors.Defect:
    defect = "DF-" + uuid4().hex[:12]
    op, at = field(op) or "<unknown>", field(at) or "<unknown>"
    exception = field(type(exc).__name__) or "<unknown>"
    cause_code = field(exc.code) if isinstance(exc, errors.AEWError) else None
    record(aew_root, exc, defect=defect, op=op, step=at, ingress=ingress, exception=exception, cause_code=cause_code)
    labels = f"{op[:_MESSAGE_FIELD]} at {at[:_MESSAGE_FIELD]}: {exception[:_MESSAGE_FIELD]}"
    if cause_code:
        labels += f" ({cause_code[:_MESSAGE_FIELD]})"
    message = f"DEFECT {labels}. Record {defect}. {next_action.replace('{defect}', defect)}"
    if isinstance(exc, errors.AEWError):
        prefix = message + " Cause: "
        cause = bounded_message(exc.message, MAX_MESSAGE - len(prefix))
        if cause:
            message = prefix + cause
    return errors.Defect(message, op=op, at=at, exception=exception, cause_code=cause_code, defect=defect,
                         committed=committed, stage_intent=field(stage_intent))
