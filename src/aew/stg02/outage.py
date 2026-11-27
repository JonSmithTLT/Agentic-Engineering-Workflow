"""The O-02 profile of the D-01 read wire, independent of the HTTP producer."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from aew import process_kind
from aew.errors import AEWError, OutageReadRefused
from aew.stg02 import wire

RECIPIENT = "aew:local-account"
POLICY = "o02:outage-historical-discovery"
ISSUER = "aew:engine"
WORK_KINDS = ("epic", "story", "ticket")
RESOLVE_KINDS = ("assurance_basis", "assurance_evidence", "assurance_determination", "hold", "composition_commitment",
                 "dependency_conflict", "package")
REFUSAL = ("This is the operator's outage read, run outside AEW's sandbox. In a Lead session use `aew status`; "
           "in a worker run use `aew check run`. Outside a sandbox, run an `aew` command that writes, such as "
           "`aew status`, once to restore `.aew/local`.")
KNOWLEDGE_DESTINATION = "Read lessons through archived work units at /v1/read/work/{work_kind}/{work_id}."
HOLD_DESTINATION = "Read the unit a hold would bind under /v1/read/work and /v1/read/assurance."
LIMIT_DEFAULT = 25
LIMIT_MAX = 100


@dataclass(frozen=True)
class Route:
    path: str
    mode: str
    projection: str | None = None
    destination: str | None = None


# A-45's profile over the frozen D-01 route inventory. The conformance test checks modes and paths against OpenAPI.
ROUTES = (
    Route("coverage", "list", destination="Run aew read with no route to list what this channel covers."),
    Route("waiting", "list", "waiting"),
    Route("attention", "list", "attention"),
    Route("attachments", "list", "attachments"),
    Route("attachments/{attachment_id}", "detail", "attachments"),
    Route("work", "list", "work"),
    Route("work/{work_kind}/{work_id}", "detail", "work"),
    Route("work/{work_kind}/{work_id}/packages", "list", "packages"),
    Route("assurance/{subject_kind}/{subject_id}", "detail", "assurance"),
    Route("research/claims/{claim_id}", "detail",
          destination="No read is available here until research claims are built."),
    Route("knowledge", "list", destination=KNOWLEDGE_DESTINATION),
    Route("knowledge/{knowledge_id}/versions/{version_id}", "detail", destination=KNOWLEDGE_DESTINATION),
    Route("knowledge/{knowledge_id}/versions/{version_id}/activity", "list", destination=KNOWLEDGE_DESTINATION),
    Route("resolve", "detail", "resolve"),
    Route("capabilities", "list", destination="No read is available here until the capability records are pinned."),
    Route("runs", "list", "runs"),
    Route("runs/{execution_id}", "detail", "runs"),
    Route("continuation-state/{work_id}", "detail", "continuation"),
    Route("owner-operations", "list", destination="No outage read is available until owner operations are committed."),
    Route("holds/{hold_id}/recovery", "detail", destination=HOLD_DESTINATION),
)
PREFIX = "/v1/read/"
AGENT_ATTENTION_DESTINATION = "No read is available here until an agent's raise is a committed record."


def profile() -> str:
    lines = ["Usage: aew [-C DIR] read [--human] [ROUTE]",
             "D-01 path IDs use unpadded base64url. Lists accept limit and cursor query parameters.", ""]
    for route in ROUTES:
        line = PREFIX + route.path
        if route.projection:
            line += "  served (owner lane only)" if route.path == "attention" else "  served"
        else:
            line += f"  unsupported. {route.destination}"
        lines.append(line)
    return "\n".join(lines)


def refuse(reason: str, title: str = "", **details: Any) -> OutageReadRefused:
    return OutageReadRefused(title, reason=reason, **details)


def _project_root(start: Path, *, listing: bool) -> Path | None:
    from aew.engine.base import Kernel
    from aew.engine.store import control_lock_visible
    from aew.harness.operator_client import lead_session_problem

    # Session markers can refuse only. The actual project lock is masked from contained processes.
    if (os.environ.get(process_kind.AGENT_ENDPOINT_ENV) or os.environ.get(process_kind.LEAD_CONTAINED_ENV)
            or lead_session_problem()):
        raise refuse("authentication_unqualified", REFUSAL)
    try:
        _, root = Kernel.locate(start)
    except (AEWError, OSError, ValueError):
        if listing:
            return None  # this is the static command profile, which contains no project data
        raise refuse("authentication_unqualified", REFUSAL) from None
    if not control_lock_visible(root):
        raise refuse("authentication_unqualified", REFUSAL)
    return root


def _path_values(template: str, path: str) -> dict[str, str] | None:
    expected, actual = template.split("/"), path.split("/")
    if len(expected) != len(actual) or any(t != a for t, a in zip(expected, actual, strict=True)
                                           if not t.startswith("{")):
        return None
    values = {}
    try:
        for segment, value in zip(expected, actual, strict=True):
            if not segment.startswith("{"):
                continue
            name = segment[1:-1]
            if name.endswith("_kind"):
                choices = WORK_KINDS if name == "work_kind" else ("story", "ticket", "package")
                if value not in choices:
                    raise ValueError(value)
                values[name] = value
            else:
                values[name] = wire.decode_id(value, min_len=2, max_len=256)
    except ValueError:
        raise refuse("invalid_request") from None
    return values


@dataclass(frozen=True)
class Request:
    route: Route
    path_values: dict[str, str]
    query: dict[str, str]
    limit: int


def _request(value: str) -> Request:
    try:
        url = urlsplit(value)
        if (not value.startswith(PREFIX) or url.scheme or url.netloc or url.fragment
                or any(ch.isspace() for ch in value) or re.search(r"%(?![0-9a-fA-F]{2})", url.query)):
            raise ValueError(value)
        pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True, errors="strict", max_num_fields=6)
    except (UnicodeError, ValueError):
        raise refuse("invalid_request") from None
    query = dict(pairs)
    if len(query) != len(pairs) or any(not v or "%" in v for v in query.values()):
        raise refuse("invalid_request")
    for route in ROUTES:
        path_values = _path_values(route.path, url.path.removeprefix(PREFIX))
        if path_values is not None:
            break
    else:
        raise refuse("invalid_request")
    keys = set(query)
    accepted = {"limit", "cursor"} if route.mode == "list" else set()
    accepted |= {"work": {"kind"}, "attention": {"lane"}, "resolve": {"kind", "id", "revision", "generation",
                                                                   "package_digest"},
                 "owner-operations": {"owner", "scope_ref", "attachment_ref"}}.get(route.path, set())
    if not keys <= accepted:
        raise refuse("invalid_request")
    if route.path == "work" and query.get("kind", "ticket") not in WORK_KINDS:
        raise refuse("invalid_request")
    if route.path == "attention" and query.get("lane", "owner_issued") not in ("owner_issued", "agent_attention"):
        raise refuse("invalid_request")
    if route.path == "resolve" and (
        query.get("kind") not in RESOLVE_KINDS or not wire.REF.fullmatch(query.get("id", ""))
        or any(not wire.REF.fullmatch(query[key]) or "/" in query[key]
               for key in ("revision", "generation") if key in query)
        or ("package_digest" in query and not re.fullmatch(r"sha256:[a-f0-9]{64}", query["package_digest"]))
    ):
        raise refuse("invalid_request")
    size = query.get("limit", str(LIMIT_DEFAULT))
    if not re.fullmatch(r"[0-9]{1,3}", size) or not 1 <= int(size) <= LIMIT_MAX:
        raise refuse("invalid_request")
    return Request(route, path_values, query, int(size))


@dataclass(frozen=True)
class Response:
    body: dict[str, Any]
    notes: tuple[str, ...] = ()
    destination: str | None = None


def _result(request: Request, items: list[dict[str, Any]], *, outcome: str, now: str, correlation: str,
            limitations: set[str], collection: str = "") -> dict[str, Any]:
    page = None
    if request.route.mode == "list":
        pos = 0
        next_cursor = None
        more = False
        if outcome in {"historical", "partial"}:
            filters = {key: value for key, value in request.query.items() if key != "cursor"}
            digest = hashlib.sha256(wire.canonical([request.route.path, request.path_values, filters, collection,
                                                     [item["ref"] for item in items]])).hexdigest()
            cursor = request.query.get("cursor")
            if cursor:
                match = re.fullmatch(r"o02\.([0-9]{1,12})\.([a-f0-9]{64})", cursor)
                if not match or match[2] != digest or not 0 < int(match[1]) < len(items):
                    raise refuse("cursor_stale_or_unauthorized")
                pos = int(match[1])
            end = pos + request.limit
            more = end < len(items)
            next_cursor = f"o02.{end}.{digest}" if more else None
            items = items[pos:end]
        page = {"page_size": request.limit, "next_cursor": next_cursor, "has_more": more,
                "scope": "effective_recipient_view", "membership": "unknown"}
    return {"wire_version": wire.D01_VERSION, "mode": request.route.mode, "outcome": outcome,
            "projection_as_of": now, "continuity": "revalidate_required" if items else "unknown", "items": items,
            "page": page, "limitations": sorted(limitations), "correlation_id": correlation, "collection_basis": None,
            "effective_recipient_ref": RECIPIENT}


def _unsupported(root: Path, request: Request, *, now: str, correlation: str,
                 limitations: set[str], destination: str) -> Response:
    if request.route.destination == HOLD_DESTINATION:
        raise refuse("not_found_or_not_disclosable", destination=destination)
    body = _result(request, [], outcome="unsupported", now=now, correlation=correlation, limitations=limitations)
    if request.route.path == "knowledge":
        from aew.engine.store import retry_lock_free
        from aew.knowledge.manifest import load_manifest

        try:
            # The schema needs a project scope even though this route reads no Knowledge or control facts.
            project_id = retry_lock_free(lambda: load_manifest(root))["project"]["id"]
        except (AEWError, OSError, ValueError, KeyError):
            raise refuse("owner_unavailable") from None
        body["journal_selection"] = {"selection_kind": "aev_finalized_adverse_determination",
                                     "status": "not_established", "owner_source": None,
                                     "scope_ref": f"aew:project:{project_id}"}
    return Response(body, destination=destination)


def read(start: Path, route: str | None, correlation: str) -> Response | None:
    """Authorize the local caller, resolve the profile, and only then inspect the selected store."""
    from aew.stg02.outage_host import qualified
    from aew.stg02.outage_store import OutageStore

    root = _project_root(start, listing=route is None)
    if route is None:
        return None
    assert root is not None
    request = _request(route)
    now = wire.utc(datetime.now(UTC))
    limitations = {"historical_only", "source_unqualified"}
    if not qualified():
        limitations.add("G4_unqualified")
    destination = request.route.destination
    if request.query.get("lane") == "agent_attention":
        destination = AGENT_ATTENTION_DESTINATION
    if destination is not None:
        return _unsupported(root, request, now=now, correlation=correlation, limitations=limitations,
                            destination=destination)
    try:
        store = OutageStore.open(root, now)
    except (AEWError, OSError, ValueError):
        if request.route.projection == "continuation":
            raise refuse("owner_unavailable") from None
        body = _result(request, [], outcome="unavailable", now=now, correlation=correlation,
                       limitations=limitations | {"source_unavailable"})
        return Response(body)
    items = store.project(request)
    limitations |= store.limitations
    outcome = "partial" if "partial_source" in limitations else "historical"
    return Response(_result(request, items, outcome=outcome, now=now, correlation=correlation,
                            limitations=limitations, collection=f"{store.scope}:{store.version}"), tuple(store.notes))


def render(response: Response) -> str:
    body = response.body
    as_of = body["projection_as_of"]
    outcome = body["outcome"]
    lines = [f"{outcome} as of {as_of}", "Limitations: " + ", ".join(body["limitations"]), *response.notes]
    if outcome == "unsupported":
        lines += ["Not read on this channel.", response.destination or ""]
    elif outcome == "unavailable":
        lines.append(f"The store could not be read as of {as_of}.")
    elif not body["items"]:
        lines.append(f"None committed as of {as_of}.")
    else:
        # JSON-quoted values keep narrative and terminal control characters inert in the text rendering too.
        lines.extend(json.dumps(item, ensure_ascii=True, indent=2) for item in body["items"])
    if body["page"] and body["page"]["has_more"]:
        lines.append(f"Next page cursor: {body['page']['next_cursor']}")
    return "\n".join(lines)
