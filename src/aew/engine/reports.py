"""Lead-authored reports, stored apart from workflow evidence (E157, SYS-40)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine.store import ControlStore, read_replaced
from aew.errors import AEWError, IntegrityError, NotFound, UsageError, ValidationFailed
from aew.harness.contract import redact
from aew.schemas import validate
from aew.util import escape_display_controls, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel

SCHEMA = "aew/report/v1"
LABEL = "Lead-authored report (unreviewed, not evidence)"
DIRECTORY = "reports"
# Like a checkpoint's NOTE_MAX, a report is bounded authored text, with a separate budget per Lead session.
MAX_BYTES = 8000
MAX_PER_SESSION = 20
MAX_TITLE = 120  # this title is listed in automatic context without its body
RECENT_KEY = "recent_lead_reports"
RECENT_LIMIT = 20
# ASCII JSON for the summary must leave room for the rest of a result under OpenCode's whole-line cut.
SUMMARY_BYTES = 8 * 1024
REPORT_ID = re.compile(r"LR-(\d+)-(LS-[0-9a-f]{12}|LG-\d+)", re.ASCII)
BROKER_SESSION_ID = re.compile(r"LS-[0-9a-f]{12}")


def _rel(report_id: str) -> str:
    return f"{DIRECTORY}/{report_id}.json"


def show_command(report_id: str) -> str:
    return f"aew report show {report_id}"


def _visible_revision(report_id: str, revision: int) -> int:
    match = REPORT_ID.fullmatch(report_id)
    if match is None or len(match[1]) > len(str(revision)):
        return 0
    created = int(match[1])
    return created if 1 <= created <= revision and match[1] == str(created) else 0


def read(root: Path, report_id: str, revision: int) -> dict[str, Any]:
    """Read a single report from the given committed revision. User input is an id, never a path."""
    if not _visible_revision(report_id, revision):
        raise NotFound(f"no Lead report {report_id!r}", reason="report_not_found")
    try:
        record = json.loads(_read_published(root, report_id).decode("utf-8"))
        validate("report", record, source=report_id)
    except FileNotFoundError:
        raise NotFound(f"no Lead report {report_id!r}", reason="report_not_found") from None
    except (OSError, ValueError, ValidationFailed) as exc:
        raise IntegrityError(f"Lead report {report_id} cannot be read", reason="report_unreadable") from exc
    if record["id"] != report_id:
        raise IntegrityError(f"Lead report {report_id} has the wrong record id", reason="report_id_mismatch")
    return record


def _read_published(root: Path, report_id: str) -> bytes:
    path = root / _rel(report_id)
    try:
        return read_replaced(path)
    except FileNotFoundError:
        if _pending_apply(root, report_id):
            raise IntegrityError(f"Lead report {report_id} is awaiting publication. Retry after `aew status` "
                                 "applies the committed writes.", reason="report_pending_apply") from None
    # A writer may have applied the transaction while the reader checked the committed state.
    return read_replaced(path)


def _pending_apply(root: Path, report_id: str) -> bool:
    store = ControlStore(root)
    try:
        state = store.read_committed()
    except AEWError:
        return False
    transition = state.get("last_transition") or {}
    return (transition.get("op") == "report.write" and _rel(report_id) in transition.get("refs", ())
            and not store.applied(state["revision"]))


def summaries(state: dict[str, Any]) -> dict[str, Any] | None:
    """Project recent titles from the caller's committed snapshot without reading any report files."""
    items: list[dict[str, str]] = []
    view = {"label": LABEL, "items": items}
    remaining = SUMMARY_BYTES - len(json.dumps(view))
    for report in state.get(RECENT_KEY, ()):
        item = {"id": report["id"], "title": escape_display_controls(report["title"])}
        size = len(json.dumps(item)) + (2 if items else 0)  # ASCII JSON, including the separator between items
        if size > remaining:
            break
        items.append(item)
        remaining -= size
    return view if items else None


def read_view(root: Path, report_id: str, revision: int) -> dict[str, str]:
    """Read a report as plain text and provenance from the caller's committed snapshot, without taking a lock."""
    record = read(root, report_id, revision)
    return {"id": record["id"], "title": record["title"], "body": record["body"], "format": "text", "label": LABEL}


def render(report: dict[str, str]) -> str:
    """Quote report text as data, with terminal control sequences escaped."""
    title = escape_display_controls(report["title"])
    body = "\n".join("    " + line for line in escape_display_controls(report["body"]).split("\n"))
    return f"{LABEL} {report['id']}\nTitle: {title}\nReport text (data):\n\n{body}"


class Reports:
    def __init__(self, k: Kernel) -> None:
        self.k = k

    def write(self, *, token: str, expect_rev: int, title: str, body: str,
              session_id: str | None = None) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "report.write") as ctx:
            try:
                size = len(title.encode("utf-8")) + len(body.encode("utf-8"))
            except UnicodeEncodeError:
                raise UsageError("Lead report text must be valid UTF-8", reason="report_encoding") from None
            if size > MAX_BYTES:
                raise UsageError(f"Lead report title and body exceed the {MAX_BYTES}-byte report size limit",
                                 reason="report_size", size=size, limit=MAX_BYTES)
            if not title.strip() or len(title) > MAX_TITLE or title.splitlines() != [title]:
                raise UsageError(f"A Lead report needs a nonempty, single-line title of at most {MAX_TITLE} characters",
                                 reason="report_title", limit=MAX_TITLE)
            if not body.strip():
                raise UsageError("A Lead report needs a body", reason="report_body")

            # A broker's session id comes from the broker, never from arguments. The direct typed transport has no
            # broker session, so its current authenticated Lead generation owns that transport's count.
            if session_id is not None and BROKER_SESSION_ID.fullmatch(session_id) is None:
                raise IntegrityError("invalid Lead broker session id", reason="report_session")
            generation = ctx.actor["generation"]
            scope = session_id or f"LG-{generation}"
            root = self.k.aew_root / DIRECTORY
            if sum(1 for path in root.glob(f"LR-*-{scope}.json")
                   if _visible_revision(path.stem, ctx.session.revision)) >= MAX_PER_SESSION:
                raise UsageError(f"Lead session has reached its limit of {MAX_PER_SESSION} reports",
                                 reason="report_count", limit=MAX_PER_SESSION)

            report_id = f"LR-{ctx.session.revision + 1}-{scope}"
            record = {"schema": SCHEMA, "kind": "lead_report", "id": report_id, "title": redact(title),
                      "body": redact(body), "generation": generation, "created_at": utc_now()}
            validate("report", record, source=report_id)
            path = _rel(report_id)
            ctx.session.write(path, json.dumps(record, ensure_ascii=False) + "\n")
            recent = ctx.state.get(RECENT_KEY, [])
            ctx.state[RECENT_KEY] = [{"id": report_id, "title": record["title"]}, *recent][:RECENT_LIMIT]
            ctx.refs.append(path)
            ctx.summary = f"Lead report {report_id} written"
        return {"ok": True, "id": report_id, "label": LABEL, "show": show_command(report_id),
                "revision": ctx.session.committed_revision}

    def show(self, report_id: str) -> dict[str, str]:
        return read_view(self.k.aew_root, report_id, self.k.store.current()["revision"])
