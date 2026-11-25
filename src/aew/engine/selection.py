"""Observe a project-declared affected-test selection on a disposable candidate copy (E243)."""

from __future__ import annotations

import json
import posixpath
import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from aew.errors import AEWError, IntegrityError
from aew.harness import check_changes, procs
from aew.policy import checks
from aew.schemas import iter_errors
from aew.util import create_exclusive, glob_any, sha256_bytes, sha256_text


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def _inputs(selector: dict[str, Any]) -> list[str]:
    if "inputs" in selector:
        return selector["inputs"]
    # An argv token referring to a project file is its default input. Resolve both the command's cwd and
    # project-root-relative paths, so a removed script is also recognized from the changed-path set.
    args = [part.replace("\\", "/") for part in selector["command"] if part and "{" not in part]
    return [posixpath.normpath(part) for part in args] + [
        posixpath.normpath(posixpath.join(selector.get("cwd", "."), part)) for part in args]


def _usable_paths(paths: list[str] | None) -> bool:
    return paths is not None and not any("\n" in path or "\r" in path for path in paths)


def _run_within(budget_s: float, run: Callable[[procs.CheckTrees], dict[str, Any]]) -> dict[str, Any]:
    """Bound waiting for the whole copy operation. Its owner finishes cleanup even if validation has moved on."""
    if budget_s <= 0:
        return {"outcome": "timeout"}
    trees = procs.CheckTrees()
    result: Future[dict[str, Any]] = Future()

    def finish() -> None:
        try:
            result.set_result(run(trees))
        except BaseException as exc:
            result.set_exception(exc)

    # A late operation can only retire its copy. The validation thread alone records and attributes the selection.
    threading.Thread(target=finish, name="aew-validation-selector", daemon=False).start()
    try:
        return result.result(timeout=budget_s)
    except TimeoutError:
        return {"outcome": "timeout"}
    finally:
        trees.end(wait_s=0)


def observe(project: Any, snapshot_of: Callable[[Path, str], dict[str, Any]], selector: dict[str, Any],
            candidate: str | None, paths: list[str] | None, *, budget_s: float | None = None) -> dict[str, Any]:
    """Return evidence about the selector itself. The result is advisory even if the command cannot run."""
    def unknown(reason: str, **details: Any) -> dict[str, Any]:
        return {"result": "unknown", "reason": reason, **details}

    if not candidate:
        return unknown("selection_not_run")
    if not _usable_paths(paths):
        return unknown("changed_files_not_known")
    assert paths is not None
    inputs = _inputs(selector)
    if any(glob_any(path, inputs) for path in paths):
        return unknown("selector_changed_by_subject")
    try:
        if budget_s is None:
            out = check_changes.run_copy(project, snapshot_of, selector, candidate, changed_paths=paths)
        else:
            out = _run_within(min(budget_s, selector.get("timeout_s", checks.DEFAULT_TIMEOUT_S)),
                              lambda trees: check_changes.run_copy(project, snapshot_of, selector, candidate,
                                                                 changed_paths=paths, trees=trees))
    except (AEWError, OSError):
        return unknown("selector_could_not_start")
    if out.get("not_run") or out["outcome"] == "spawn_failed":
        return unknown("selector_could_not_start")
    if out["outcome"] == "timeout":
        return unknown("selector_timed_out")
    if out.get("mutated"):
        return unknown("selector_mutated_inputs")
    if out["exit_code"] != 0:
        return unknown("selector_failed", exit_code=out["exit_code"])
    lines = out.get("selection_items")
    items = list(dict.fromkeys(filter(None, lines or [])))
    if lines is None or any(item == "*" or "\r" in item or "\0" in item for item in items) or (
            not items and not selector.get("may_select_none")):
        return unknown("selector_no_output")
    return {"result": "known", "items": items}


def _read(root: Path, rel: str) -> tuple[dict[str, Any], dict[str, str]] | None:
    try:
        raw = (root / rel).read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None
    if iter_errors("selection", value):
        return None
    return value, {"path": rel, "sha256": sha256_bytes(raw)}


def reuse_or_run(project: Any, snapshot_of: Callable[[Path, str], dict[str, Any]], *, directory: str,
                 selector: dict[str, Any], candidate: str | None, snapshot: str,
                 paths: list[str] | None, budget_s: float) -> tuple[dict[str, Any], dict[str, str]] | None:
    """Cache by snapshot and complete selector and changed-path commitments. Never reuse a mismatched record."""
    paths = sorted(set(paths)) if paths is not None else None
    fields = {"snapshot": snapshot, "selector_sha256": sha256_text(_json(selector)),
              "changed_paths_sha256": sha256_text(_json(paths))}
    root = project.aew_root
    rel = f"{directory}/selection-{sha256_text(_json(fields))}.json"
    if (root / rel).exists():
        cached = _read(root, rel)
        return cached if cached and all(cached[0][k] == v for k, v in fields.items()) else None

    value = {"schema": "aew/selection/v1", **fields,
             **observe(project, snapshot_of, selector, candidate, paths, budget_s=budget_s)}
    raw = _json(value)
    try:
        create_exclusive(root / rel, raw)
    except IntegrityError:
        # Another execution published the immutable record first.
        cached = _read(root, rel)
        return cached if cached and all(cached[0][k] == v for k, v in fields.items()) else None
    except OSError:
        return None
    return value, {"path": rel, "sha256": sha256_text(raw)}


def read_pinned(root: Path, reference: dict[str, str] | None, *, directory: str,
                snapshot: str) -> dict[str, Any] | None:
    """Use only the exact record bound by finished staging to this snapshot."""
    if reference is None:
        return None
    rel = reference["path"]
    path = Path(rel)
    if path.parent != Path(directory) or not path.name.startswith("selection-") or path.suffix != ".json":
        return None
    found = _read(root, rel)
    return found[0] if found and found[1] == reference and found[0]["snapshot"] == snapshot else None
