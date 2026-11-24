"""Project status from the retained Lead and worker provider-relay journals."""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew.engine.configuration import model_id_problem
from aew.harness import defects, runlog
from aew.harness.containment import relay

_RUN = re.compile(r"(?:R-INV-[0-9]{4,}-[0-9]+|lead-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6})")
_STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_BUCKETS = ("upstream_2xx", "upstream_non_2xx", "refused", "unknown")


def _code(value: Any) -> int | None:
    return value if isinstance(value, int) and 100 <= value <= 599 else None


def valid_stamp(value: Any) -> bool:
    if not isinstance(value, str) or not _STAMP.fullmatch(value):
        return False
    try:
        dt.datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _observation(raw: bytes, run: str) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    try:
        row = json.loads(raw)
        if not isinstance(row, dict):
            return None
        at, route = row.get("at"), row.get("route")
        if not valid_stamp(at):
            return None
    except (ValueError, RecursionError):
        return None
    if (not isinstance(route, str) or model_id_problem(route) or relay.SENTINEL_PREFIX in route
            or defects.redact_text(route) != route):
        return None
    login, swap, outcome = row.get("login"), row.get("swap"), row.get("outcome")
    if login not in ("key", "oauth", "none") or swap not in relay.SWAP_OUTCOMES:
        return None
    if outcome not in (*relay.OUTCOMES, None):
        return None
    reason = row.get("reason")
    reason = reason if isinstance(reason, str) and re.fullmatch(r"[a-z_]{1,64}", reason) else None
    operation = row.get("operation")
    return route, {"at": at, "run": run, "role": "lead" if run.startswith("lead-") else "worker",
                   "login": login, "swap": swap, "outcome": outcome or "unknown",
                   "operation": operation if operation in ("model", "models_list") else "unknown",
                   "status": _code(row.get("status")) if outcome in ("forwarded", "unknown") else None,
                   "answered": _code(row.get("answered")),
                   "reason": reason if outcome in ("refused", "unknown") else None}, row


def _count(row: dict[str, Any]) -> str:
    if row["outcome"] == "refused":
        return "refused"
    if row["status"] is None or row["outcome"] == "unknown":  # the provider may have done it, whatever its status
        return "unknown"
    return "upstream_2xx" if 200 <= row["status"] < 300 else "upstream_non_2xx"


def _regular_dir(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT


def visit(aew_root: Path, observe: Callable[[str, dict[str, Any], dict[str, Any]], None], *,
          on_run: Callable[[Path], bool] | None = None) -> bool:
    """Read each eligible run and its complete journal rows. Return true if any retained evidence was unreadable."""
    partial = False
    try:
        parent = aew_root / runlog.RUNS_REL
        if not _regular_dir(parent):
            return True
        for directory in parent.iterdir():
            run = directory.name
            if not _RUN.fullmatch(run):
                continue
            try:
                if not _regular_dir(directory):
                    partial = True
                    continue
                if on_run is not None and not on_run(directory):
                    partial = True
                data = runlog.read_regular(directory / runlog.RELAY_REQUESTS)
            except FileNotFoundError:  # older runs, unrelayed runs, or a run with no completed requests
                continue
            except OSError:
                partial = True
                continue
            # Appends end with a newline. A reader can see an incomplete final append while the run is active.
            for raw in io.BytesIO(data):
                if not raw.endswith(b"\n"):
                    break
                observation = _observation(raw, run)
                if observation is None:
                    partial = True
                    continue
                observe(*observation)
    except FileNotFoundError:
        pass
    except OSError:
        partial = True
    return partial


def summary(aew_root: Path) -> dict[str, Any]:
    """One count per complete recorded request. For ties use run ID, then append order within the run."""
    routes: dict[str, Any] = {}

    def observe(provider: str, row: dict[str, Any], _raw: dict[str, Any]) -> None:
        if provider not in routes:
            routes[provider] = {"counts": dict.fromkeys(_BUCKETS, 0), "last_request": None, "last_model": None}
        view = routes[provider]
        view["counts"][_count(row)] += 1
        fields = ("last_request", "last_model") if row["operation"] == "model" else ("last_request",)
        for field in fields:
            previous = view[field]
            if previous is None or (row["at"], row["run"]) >= (previous["at"], previous["run"]):
                view[field] = row

    partial = visit(aew_root, observe)
    return {"partial": partial, "routes": dict(sorted(routes.items()))}


def _result(row: dict[str, Any]) -> str:
    if row["outcome"] == "refused":
        code = f" HTTP {row['answered']}" if row["answered"] is not None else ""
        result = f"relay refused{code} ({row['reason'] or 'unknown reason'})"
    elif row["outcome"] == "unknown":  # the request may have reached the provider: never "not sent"
        result = f"outcome unknown ({row['reason'] or 'unknown reason'})"
    elif row["status"] is not None:
        result = f"upstream HTTP {row['status']}"
    else:
        result = "upstream status unknown"
    return f"{result}, {row['login']} login, swap {row['swap']}, {row['at']} ({row['role']} {row['run']})"


def render(report: dict[str, Any]) -> list[str]:
    lines = ["Provider relay (recorded Lead and worker requests)"]
    if report["partial"]:
        lines.append("  Partial history: results and counts cover readable records. A journal over "
                     f"{runlog.MAX_RECORD_BYTES // (1 << 20)} MiB is omitted in full.")
    if not report["routes"]:
        lines.append("  No recorded provider requests found.")
    for provider, view in report["routes"].items():
        counts = view["counts"]
        lines.append(f"  {provider}: {sum(counts.values())} recorded ({counts['upstream_2xx']} upstream 2xx, "
                     f"{counts['upstream_non_2xx']} upstream non-2xx, {counts['refused']} relay refused, "
                     f"{counts['unknown']} unknown)")
        model, last = view["last_model"], view["last_request"]
        lines.append(f"    Last recognized model request: {_result(model) if model else 'none recorded'}")
        if last["operation"] != "model":
            lines.append(f"    Last provider request ({last['operation']}): {_result(last)}")
    return lines
