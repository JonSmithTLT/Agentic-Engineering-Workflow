"""`aew usage show` and the status summary: the ledger's projections (``usage_ops``) over what a read names (F25, the
cost and usage ledger design v0.2 R6, R7, R9).

This module only gathers: the target (a run, an invocation, a unit's tree or the project), the archived bundles that
target covers, and the table in effect now. Every figure comes from ``usage_ops``'s one projection, which the JSON is
and the text renders; nothing here sums anything.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aew.engine import usage_ops as O
from aew.errors import NotFound, UsageError, ValidationFailed
from aew.harness import contract as K

if TYPE_CHECKING:
    from aew.engine.archive_ops import Archive
    from aew.engine.base import Kernel

_UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")  # the history index's `at` form (`aew history list`'s bounds)
PAGE = 200  # archived units read per page of the `--all` walk, newest first (as `aew history list` pages)


class UsageReads:
    """The ledger's read surfaces."""

    def __init__(self, k: Kernel, *, archive: Archive) -> None:
        self.k = k
        self.archive = archive

    def reader(self) -> O.Reader:
        """A reader under the table in effect now. A table that is named and cannot be used is refused with a typed
        error, never read as no table: `aew doctor`'s `policy:pricing` names the fix."""
        try:
            return O.Reader(self.k.aew_root, self.k.pricing())
        except FileNotFoundError as exc:  # named in the manifest, and neither on disk nor pinned (#368 review, m2)
            rel = (self.k.manifest.get("policy") or {}).get("pricing")
            raise ValidationFailed(f"the price table {rel} is named by the manifest and cannot be read; `aew doctor` "
                                   "checks it (policy:pricing)", reason="pricing_table_missing", path=rel) from exc

    def summary(self, state: dict[str, Any]) -> dict[str, Any]:
        """The status report's bounded summary of the hot state (R9). A table that cannot be used leaves the figures
        under current prices unpriced with their own reason and says why, so `aew status` itself never fails over a
        price."""
        try:
            reader, problem = self.reader(), None
        except Exception as exc:  # status reports; `aew doctor` and `aew usage show` refuse with the typed error
            reader = O.Reader(self.k.aew_root, None, unusable=True)
            problem = f"{getattr(exc, 'code', type(exc).__name__)}: {exc}"
        out = O.status_summary(state, reader)
        if problem:
            out["pricing_problem"] = problem
        return out

    def show(self, target: str | None = None, *, walk_all: bool = False, since: str | None = None,
             until: str | None = None) -> dict[str, Any]:
        """One view: a run's row, an invocation's rows and sum, a unit's tree (its own and its descendants' totals),
        or the project (the hot state plus the `recent` ring, or with ``walk_all`` every archived unit, bounded by
        ``since``/``until``). Hot state first, then the archive, for each."""
        if target is not None and (walk_all or since or until):
            raise UsageError("--all, --since and --until are for the project's view; a run, invocation or unit is "
                             "read whole, hot or archived")
        if (since or until) and not walk_all:
            raise UsageError("--since and --until bound the archive walk: give them with --all")
        for name, stamp in (("--since", since), ("--until", until)):
            if stamp is not None and not _UTC.fullmatch(stamp):  # compared as text with the index's `at`
                raise UsageError(f"{name} must be a UTC timestamp like 2026-10-02T00:00:00Z")
        state = self.k.store.current()
        reader = self.reader()
        if target is None:
            return self._with_basis({"target": {"kind": "project"},
                                     **self._project(state, reader, walk_all, since, until)}, reader)
        run_of = K.invocation_of_run(target)
        if run_of is not None:
            found = self._run(state, target, run_of, reader)
            if found is not None:
                return self._with_basis(found, reader)
        inv = state["invocations"].get(target) or self.archive.archived_invocation(state, target)
        if inv is not None:
            return self._with_basis({"target": {"kind": "invocation", "id": target},
                                     **reader.invocation(target, inv)}, reader)
        if target in state["work"] or self.archive.bundle(state, target) is not None:
            return self._with_basis({"target": {"kind": "unit", "id": target},
                                     **O.unit_projection(state, target, reader, list(self._subtree(state, target)))},
                                    reader)
        raise NotFound(f"no run, invocation or work unit {target}", reason="usage_target_unknown")

    @staticmethod
    def _with_basis(view: dict[str, Any], reader: O.Reader) -> dict[str, Any]:
        return {**view, "basis": O.basis(reader.current)}

    def _run(self, state: dict[str, Any], run: str, inv_id: str, reader: O.Reader) -> dict[str, Any] | None:
        inv = state["invocations"].get(inv_id) or self.archive.archived_invocation(state, inv_id)
        for entry in (inv or {}).get("runs") or []:
            if entry.get("run") == run:
                row = reader.run_row(entry, inv_id)
                return {"target": {"kind": "run", "id": run}, "row": O.public_row(row)}
        return None

    def _bundle(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        """An archived unit's bundle with the unit as it stands now (later moves applied), so the tree places it
        under its current parent."""
        doc = self.archive.bundle(state, work_id)
        return None if doc is None else dict(doc, unit=self.archive.archived_unit(state, work_id))

    def _subtree(self, state: dict[str, Any], work_id: str) -> Iterator[dict[str, Any]]:
        """The bundles a unit's tree needs: the unit if it is archived, and every archived descendant, found below
        each node by the index (a hot Story's finished Tickets are archived)."""
        if work_id not in state["work"]:
            doc = self._bundle(state, work_id)
            if doc is not None:
                yield doc
        hot = sorted(w for w, u in state["work"].items() if u.get("parent") == work_id)
        archived = [w for w, _ in self.archive.archived_children(state, work_id)]
        for child in hot + archived:
            yield from self._subtree(state, child)

    def _project(self, state: dict[str, Any], reader: O.Reader, walk_all: bool, since: str | None,
                 until: str | None) -> dict[str, Any]:
        # The project's totals need no parent, so each bundle is loaded once, as stored (`bundle`), and summed as it
        # comes: the walk holds one bundle at a time (R7; #368 review, m3).
        if not walk_all:
            recent = (b for r in state.get("recent") or [] if (b := self.archive.bundle(state, r["id"])) is not None)
            return O.project_projection(state, reader, recent)
        # The walk reads every archived unit entry: complete, unless bounded (then it is a window, never complete).
        return O.project_projection(state, reader, self._walk(state, since, until), walk_all=True, since=since,
                                    until=until, archive_complete=True)

    def _walk(self, state: dict[str, Any], since: str | None, until: str | None) -> Iterator[dict[str, Any]]:
        """Every archived unit's bundle in the bounds, newest first, page by page, each loaded once."""
        if state.get("schema") != "aew/control/v2":
            return
        index, before, seen = self.archive.index(state), None, set()
        while True:
            page = index.list(kind="unit", since=since, until=until, limit=PAGE, before_seq=before)
            for entry in page:
                if entry["id"] not in seen and entry["id"] not in state["work"]:
                    seen.add(entry["id"])
                    doc = self.archive.bundle(state, entry["id"])
                    if doc is not None:
                        yield doc
            if len(page) < PAGE:
                return
            before = page[-1]["seq"]
