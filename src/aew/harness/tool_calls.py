"""The Lead broker's per-call typed-tool log (M4-E plan v3 E5a, n7; TLS-27 and VGX-21's reported metrics).

The broker appends one JSON line per typed-tool call it serves (``lead.tool``) to ``.aew/local/lead/tool-calls.jsonl``:
the tool, a digest of its arguments (never the arguments: they may carry authored text), its effective operation class,
whether it succeeded, where it stopped and with which error code, the control revision before and after, the stage
intent it opened or resolved, and how long it took. M4-H computes steps per Ticket, refusals and reads between
mutations from it together with the harness transcripts.

It is telemetry under ``.aew/local/`` (git-ignored, rebuildable, KC §5.3): never control state, never read by a gate,
and never a reason a call fails: building or writing a line that fails for any reason is logged and the line dropped
(:func:`record`; PR #177 review, finding 4). It is bounded: every free-text field is cut to ``MAX_FIELD`` characters, so
a line stays under ``MAX_LINE`` bytes whatever the call carried; past ``MAX_BYTES`` the file is rotated to
``tool-calls.1.jsonl`` (the older ones shift up) and at most ``KEEP`` rotated files are kept.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from aew.util import sha256_bytes, utc_now

LOG_REL = "local/lead/tool-calls.jsonl"
MAX_BYTES = 1 << 20  # one file; a line is a few hundred bytes, so some thousands of calls each
KEEP = 4  # rotated files kept: tool-calls.1.jsonl (newest) .. tool-calls.4.jsonl
MAX_FIELD = 128  # characters kept of a field the caller controls (the tool name, ingress, profile) or echoes (a code)
MAX_LINE = 2048  # what a line can reach with every field at its bound (tested)
INPUT_ERROR = "input_error"  # the boundary of a call that never reached the runner (an AdapterInputError)

log = logging.getLogger(__name__)
_lock = threading.Lock()  # one broker serves calls from several threads (a cooperative wait runs unserialized)


def path(aew_root: Path) -> Path:
    return Path(aew_root) / LOG_REL


def rotated(aew_root: Path, n: int) -> Path:
    return Path(aew_root) / f"local/lead/tool-calls.{n}.jsonl"


def arguments_digest(arguments: Any) -> str:
    """The digest of a call's arguments as canonical JSON (the broker receives them as JSON text), or of the text as
    given when it is not JSON."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:  # not JSON, maybe not even encodable text (a lone surrogate): digest it as given
            return sha256_bytes(arguments.encode("utf-8", "surrogatepass"))
    return sha256_bytes(json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8", "surrogatepass"))


def _short(value: Any) -> str | None:
    return None if value is None else str(value)[:MAX_FIELD]


def entry(*, tool: str, arguments: Any, ingress: str, profile: str, result: dict[str, Any] | None,
          input_error: dict[str, Any] | None, error: dict[str, Any] | None, revision_before: int | None,
          duration_ms: int) -> dict[str, Any]:
    """One line: from the call's ``StageResult``, or its adapter input error, or the refusal that ended it before
    either (an unknown ingress, a lost bridge)."""
    out: dict[str, Any] = {"at": utc_now(), "tool": _short(tool), "arguments_sha256": arguments_digest(arguments),
                           "ingress": _short(ingress), "profile": _short(profile), "effective_class": None, "ok": False,
                           "boundary": None, "error_code": None, "revision_before": revision_before,
                           "revision_after": None, "stage_intent": None, "duration_ms": duration_ms}
    if result is not None:
        stopped = result.get("stopped") or {}
        out.update(effective_class=_short(result.get("effective_operation_class")), ok=bool(result.get("ok")),
                   boundary=_short(stopped.get("boundary")),
                   error_code=_short((stopped.get("error") or {}).get("code")),
                   revision_after=_int(result.get("revision")), stage_intent=_short(result.get("stage_intent_id")))
    elif input_error is not None:
        out.update(boundary=INPUT_ERROR, error_code=_short(input_error.get("code")))
    elif error is not None:
        out.update(boundary="error", error_code=_short(error.get("code")))
    return out


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def record(aew_root: Path, **fields: Any) -> None:
    """Build and append one line (:func:`entry`, :func:`append`). Never raises: whatever fails is logged, and the call
    it describes answers as it would have."""
    try:
        append(aew_root, entry(**fields))
    except Exception as exc:  # noqa: BLE001  telemetry: a defect here must never change or fail the call
        log.warning("the typed-tool call log dropped a line: %s: %s", type(exc).__name__, exc)


def append(aew_root: Path, line: dict[str, Any]) -> None:
    """Append ``line``, rotating first when the file is full. Never raises: the log is telemetry."""
    target = path(aew_root)
    text = json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with _lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                full = target.stat().st_size + len(text) > MAX_BYTES
            except FileNotFoundError:
                full = False
            if full:
                _rotate(aew_root)
            with target.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    except OSError as exc:
        log.warning("the typed-tool call log %s could not be written: %s", target, exc)


def _rotate(aew_root: Path) -> None:
    for n in range(KEEP - 1, 0, -1):  # the oldest kept is overwritten by the one before it
        if rotated(aew_root, n).exists():
            os.replace(rotated(aew_root, n), rotated(aew_root, n + 1))
    os.replace(path(aew_root), rotated(aew_root, 1))


def read(aew_root: Path) -> list[dict[str, Any]]:
    """Every line kept, oldest first (the rotated files, then the current one)."""
    out: list[dict[str, Any]] = []
    for p in [*(rotated(aew_root, n) for n in range(KEEP, 0, -1)), path(aew_root)]:
        if p.exists():
            out.extend(json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip())
    return out
