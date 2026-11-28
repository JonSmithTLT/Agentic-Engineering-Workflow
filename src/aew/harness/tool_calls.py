"""The Lead broker's per-call typed-tool log (M4-E plan v3 E5a, n7; TLS-27 and VGX-21's reported metrics).

The broker appends one JSON line per typed-tool call it serves (``lead.tool``) to ``.aew/local/lead/tool-calls.jsonl``:
the tool, a digest of its arguments (never the arguments: they may carry authored text), its effective operation class,
whether it succeeded, where it stopped and with which error code, the control revision before and after, the stage
intent it opened or resolved, and how long it took. M4-H computes steps per Ticket, refusals and reads between
mutations from it together with the harness transcripts.

The same log holds the session's lookups (E231: the operator's failure criterion for the guide's core, 2026-11-25: a
Lead that "fails to use typed tools correctly, is using help all the time for shell commands"): one line per relayed
``aew guide`` read and per ``--help`` lookup its shell asks for (:func:`lookup`). Every line the broker writes names the
Lead session it served (``session``, one per broker) and its generation, so :func:`counters` reads, per session, the
typed calls that stopped (by error code: a stop is not always the Lead's misuse), defects and ill-formed arguments,
guide reads and help lookups: what the scripted probe, the
dogfood and UAT compare (``aew lead telemetry``).

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
DEFECT_LOG_REL = "local/lead/defects.jsonl"
MAX_BYTES = 1 << 20  # one file; a line is a few hundred bytes, so some thousands of calls each
KEEP = 4  # rotated files kept: tool-calls.1.jsonl (newest) .. tool-calls.4.jsonl
MAX_FIELD = 128  # characters kept of a field the caller controls (the tool name, ingress, profile) or echoes (a code)
MAX_LINE = 2048  # what a line can reach with every field at its bound (tested)
INPUT_ERROR = "input_error"  # the boundary of a call that never reached the runner (an AdapterInputError)
GUIDE, HELP = "guide", "help"  # the kinds of lookup line (:func:`lookup`)
DEFECT = "DEFECT"

log = logging.getLogger(__name__)
_lock = threading.Lock()  # one broker serves calls from several threads (a cooperative wait runs unserialized)


def path(aew_root: Path) -> Path:
    return Path(aew_root) / LOG_REL


def rotated(aew_root: Path, n: int) -> Path:
    return Path(aew_root) / f"local/lead/tool-calls.{n}.jsonl"


def _rotated(aew_root: Path, n: int, log_rel: str) -> Path:
    if log_rel == DEFECT_LOG_REL:
        return Path(aew_root) / f"local/lead/defects.{n}.jsonl"
    return rotated(aew_root, n)


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
          duration_ms: int, session: str | None = None, generation: int | None = None) -> dict[str, Any]:
    """One line: from the call's ``StageResult``, or its adapter input error, or the refusal that ended it before
    either (an unknown ingress, a lost bridge). ``session`` and ``generation``: the Lead session that served it."""
    out: dict[str, Any] = {"at": utc_now(), "session": _short(session), "generation": _int(generation),
                           "tool": _short(tool), "arguments_sha256": arguments_digest(arguments),
                           "ingress": _short(ingress), "profile": _short(profile), "effective_class": None, "ok": False,
                           "boundary": None, "error_code": None, "revision_before": revision_before,
                           "revision_after": None, "stage_intent": None, "duration_ms": duration_ms}
    if result is not None:
        stopped = result.get("stopped") or {}
        stopped_error: dict[str, Any] = stopped.get("error") or {}
        error = stopped_error
        out.update(effective_class=_short(result.get("effective_operation_class")), ok=bool(result.get("ok")),
                   boundary=_short(stopped.get("boundary")),
                   error_code=_short(stopped_error.get("code")),
                   revision_after=_int(result.get("revision")), stage_intent=_short(result.get("stage_intent_id")))
    elif input_error is not None:
        out.update(boundary=INPUT_ERROR, error_code=_short(input_error.get("code")))
    elif error is not None:
        out.update(boundary="error", error_code=_short(error.get("code")))
    if out["error_code"] == DEFECT and error is not None:
        detail = error.get("details") or {}
        out.update({name: _short(detail.get(name)) for name in ("exception", "defect", "cause_code")})
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


def lookup(aew_root: Path, *, kind: str, session: str | None, generation: int | None, command: str,
           section: str | None = None, ok: bool | None = None) -> None:
    """One lookup line: a relayed ``aew guide`` read (``kind`` :data:`GUIDE`, with the section asked for, and whether
    it was printed) or a ``--help`` lookup (:data:`HELP`, with the command words it asked about). Never raises, like
    :func:`record`; the words are the caller's, cut to ``MAX_FIELD``, and never an argument's value."""
    try:
        append(aew_root, {"at": utc_now(), "session": _short(session), "generation": _int(generation),
                          "lookup": _short(kind), "command": _short(command), "section": _short(section),
                          "ok": ok if isinstance(ok, bool) else None})
    except Exception as exc:  # noqa: BLE001  telemetry: a defect here must never change or fail the lookup
        log.warning("the typed-tool call log dropped a lookup: %s: %s", type(exc).__name__, exc)


COUNTERS = ("typed_calls", "stopped", "defects", "invalid_arguments", "guide_reads", "help_lookups")


def counters(lines: list[dict[str, Any]]) -> dict[str | None, dict[str, Any]]:
    """Per Lead session (lines from before sessions were named fall under ``None``): its typed calls; those that
    stopped with an error code (a defect aside), by code in ``stopped_codes``, since a stop is not always the Lead's
    misuse (a launch that failed, a publish that only rebuilt, a report that failed: review of #593, m4); defects;
    and arguments the adapter refused before the runner (``INVALID_ARGUMENTS``, an unknown tool); its guide reads, by
    section; and its help lookups, by command. A line is counted by what it says, never by what it was meant to say: a
    guide read of a section that does not exist is a guide read that failed (``ok`` false), and still a read."""
    out: dict[str | None, dict[str, Any]] = {}
    for line in lines:
        session = line.get("session")
        row = out.setdefault(None if session is None else str(session), {
            **dict.fromkeys(COUNTERS, 0), "generation": line.get("generation"), "first_at": line.get("at"),
            "last_at": None, "stopped_codes": {}, "guide_sections": {}, "help_commands": {}})
        row["last_at"] = line.get("at")
        kind = line.get("lookup")
        if kind == GUIDE:
            row["guide_reads"] += 1
            name = line.get("section") or "(list)"
            row["guide_sections"][name] = row["guide_sections"].get(name, 0) + 1
        elif kind == HELP:
            row["help_lookups"] += 1
            name = line.get("command") or "aew"
            row["help_commands"][name] = row["help_commands"].get(name, 0) + 1
        elif "tool" in line:
            row["typed_calls"] += 1
            if line.get("ok"):
                continue
            if line.get("boundary") == INPUT_ERROR:
                row["invalid_arguments"] += 1
            elif line.get("error_code") == DEFECT:
                row["defects"] += 1
            elif (code := line.get("error_code")) is not None:
                row["stopped"] += 1
                row["stopped_codes"][code] = row["stopped_codes"].get(code, 0) + 1
    return out


def render_counters(sessions: dict[str | None, dict[str, Any]], skipped: int = 0) -> str:
    """``aew lead telemetry``: one paragraph per session, oldest first, and how many lines did not parse."""
    torn = f" {skipped} line(s) that did not parse were skipped." if skipped else ""
    if not sessions:
        return f"No Lead session has written to .aew/{LOG_REL} yet.{torn}"
    out = [f"Lead sessions, from .aew/{LOG_REL} (local telemetry, oldest first; rotated files included):{torn}"]
    for name, row in sessions.items():
        def by(counts: dict[str, int]) -> str:
            return f" ({', '.join(f'{k} {v}' for k, v in counts.items())})" if counts else ""

        out += ["", f"- {name or '(no session named: written before sessions were)'}, generation "
                    f"{row['generation']}, {row['first_at']} to {row['last_at']}: {row['typed_calls']} typed calls; "
                    f"{row['stopped']} stopped{by(row['stopped_codes'])}, {row['defects']} defects, "
                    f"{row['invalid_arguments']} with invalid arguments; "
                    f"{row['guide_reads']} guide reads{by(row['guide_sections'])}; "
                    f"{row['help_lookups']} help lookups{by(row['help_commands'])}."]
    return "\n".join(out)


def append(aew_root: Path, line: dict[str, Any], *, log_rel: str = LOG_REL) -> None:
    """Append ``line``, rotating first when the file is full. Never raises: the log is telemetry."""
    try:
        target = Path(aew_root) / log_rel
        text = json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n"
        with _lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                full = target.stat().st_size + len(text) > MAX_BYTES
            except FileNotFoundError:
                full = False
            if full:
                _rotate(aew_root, target, log_rel)
            with target.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    except OSError as exc:
        log.warning("the local log %s could not be written: %s", log_rel, exc)


def _rotate(aew_root: Path, target: Path, log_rel: str) -> None:
    for n in range(KEEP - 1, 0, -1):  # the oldest kept is overwritten by the one before it
        source = _rotated(aew_root, n, log_rel)
        if source.exists():
            os.replace(source, _rotated(aew_root, n + 1, log_rel))
    os.replace(target, _rotated(aew_root, 1, log_rel))


def read(aew_root: Path) -> list[dict[str, Any]]:
    """Every line kept, oldest first (the rotated files, then the current one)."""
    return read_counted(aew_root)[0]


def read_counted(aew_root: Path) -> tuple[list[dict[str, Any]], int]:
    """Every line kept, oldest first, and how many lines were skipped because they do not parse as a JSON object (a
    torn write: review of #593, n4). Telemetry: a bad line costs a count, never the read."""
    from aew.engine.store import retry_lock_free

    out: list[dict[str, Any]] = []
    skipped = 0
    for p in [*(rotated(aew_root, n) for n in range(KEEP, 0, -1)), path(aew_root)]:
        try:
            text = retry_lock_free(p.read_bytes).decode("utf-8", "replace")
        except FileNotFoundError:
            continue
        for raw in text.splitlines():
            if not raw.strip():
                continue
            try:
                line = json.loads(raw)
            except ValueError:
                line = None
            if isinstance(line, dict):
                out.append(line)
            else:
                skipped += 1
    return out, skipped
