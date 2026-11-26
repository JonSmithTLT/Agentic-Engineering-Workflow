"""Lead-authored reports, stored apart from workflow evidence (E157, SYS-40)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.coordination.render import escaped
from aew.errors import IntegrityError, NotFound, UsageError, ValidationFailed
from aew.harness.contract import redact
from aew.schemas import validate
from aew.util import utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel

SCHEMA = "aew/report/v1"
LABEL = "Lead-authored report (unreviewed, not evidence)"
DIRECTORY = "reports"
# Like a checkpoint's NOTE_MAX, a report is bounded authored text, with a separate budget per Lead session.
MAX_BYTES = 8000
MAX_PER_SESSION = 20
MAX_TITLE = 120  # this title is listed in automatic context without its body
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
        record = json.loads((root / _rel(report_id)).read_text(encoding="utf-8"))
        validate("report", record, source=report_id)
    except FileNotFoundError:
        raise NotFound(f"no Lead report {report_id!r}", reason="report_not_found") from None
    except (OSError, ValueError, ValidationFailed) as exc:
        raise IntegrityError(f"Lead report {report_id} cannot be read", reason="report_unreadable") from exc
    if record["id"] != report_id:
        raise IntegrityError(f"Lead report {report_id} has the wrong record id", reason="report_id_mismatch")
    return record


def summaries(root: Path, revision: int) -> dict[str, Any] | None:
    """A labelled list of visible reports. Its entries carry only id and title."""
    visible = ((created, path.stem) for path in (root / DIRECTORY).glob("LR-*.json")
               if (created := _visible_revision(path.stem, revision)))
    items = []
    for _, report_id in sorted(visible, reverse=True):
        try:
            title = read(root, report_id, revision)["title"]
        except (NotFound, IntegrityError):
            continue  # an optional report must never block a workflow query; an explicit read gives the reason
        items.append({"id": report_id, "title": escaped(title)})
    return {"label": LABEL, "items": items} if items else None


def read_view(root: Path, report_id: str, revision: int) -> dict[str, str]:
    """Read a report as plain text and provenance from the caller's committed snapshot, without taking a lock."""
    record = read(root, report_id, revision)
    return {"id": record["id"], "title": record["title"], "body": record["body"], "format": "text", "label": LABEL}


def render(report: dict[str, str]) -> str:
    """Quote report text as data, with terminal control sequences escaped."""
    title = escaped(report["title"])
    body = "\n".join("    " + line for line in escaped(report["body"]).split("\n"))
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
            ctx.refs.append(path)
            ctx.summary = f"Lead report {report_id} written"
        return {"ok": True, "id": report_id, "label": LABEL, "show": show_command(report_id),
                "revision": ctx.session.committed_revision}

    def show(self, report_id: str) -> dict[str, str]:
        return read_view(self.k.aew_root, report_id, self.k.store.current()["revision"])
