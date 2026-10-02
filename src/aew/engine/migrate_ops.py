"""`aew migrate`: a v1 project's control state becomes v2 in one transaction (ADR-0011; implementation plan R8, §3).

The migration is the archival finalizer (R6) run once over the whole v1 state: every DONE or CANCELLED unit leaves the
hot state, deepest first, with its invocations and credentials, and the parent summaries, ``archived_refs``,
frontiers and ``recent`` follow, exactly as if each unit had been archived at the commit that finished it.

What makes one transaction practical (R8):
- **Bundles are written before the commit** (``TxnContext.prewrite``) and the commit references them by hash. They
  are deterministic: a retry after an interrupted migration writes the same bytes, and a bundle whose commit never
  happened is an unreferenced record, which is benign (ADR-0011).
- **The redo record** carries only the sealed segments, the tail and the root; ``last_transition`` records the count
  and hash of the pre-written list.

**Existing parent evidence stays current (R3).** A parent's children digest changes form at v2. Each open parent
keeps ``legacy_digest: {v1, v2_at_migration}``, and evidence bound to its v1 digest counts as current while its
v2 digest is still the one recorded at migration (``hierarchy_ops``).

The migration refuses while any harness run may be live (invariant 7): a run's supervisor holds custody of its
invocation, which the migration would archive or rewrite under it. It is idempotent: on a v2 project it does nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aew.engine import hierarchy as H
from aew.engine.authority import require_lead
from aew.engine.base import V2, TxnContext
from aew.engine.store import Transition
from aew.errors import AEWError, IllegalTransition, StaleRevision
from aew.harness import runlog
from aew.history import manifest as M

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import HierarchyPort


class Migration:
    """``aew migrate`` (Lead)."""

    def __init__(self, k: Kernel, *, hierarchy: HierarchyPort) -> None:
        self.k = k
        self.hierarchy = hierarchy

    def live_runs(self, state: dict[str, Any]) -> list[str]:
        """The harness runs whose supervisor may still hold custody: each invocation's latest run, conservatively (a
        run launched moments ago with no record yet counts)."""
        out = []
        for inv in state["invocations"].values():
            runs = inv.get("runs") or []
            if runs and runlog.may_be_live(runlog.run_dir(self.k.aew_root, runs[-1]["run"]),
                                           runs[-1].get("launched_at")):
                out.append(runs[-1]["run"])
        return sorted(out)

    def migrate(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        with self.k.store.session() as s:
            actor = require_lead(s.state, token, archived=self.k.archived_credential)
            if expect_rev != s.revision:
                raise StaleRevision(f"expected control revision {expect_rev}, current is {s.revision}",
                                    expected=expect_rev, current=s.revision)
            state = s.state
            if state["schema"] == V2:
                return {"ok": True, "migrated": False, "schema": V2, "revision": s.revision,
                        "summary": "the control state is already v2; nothing to migrate"}
            self.k.check_manifest_pin(state)
            live = self.live_runs(state)
            if live:
                raise IllegalTransition("a harness run may still be live; stop it or wait for it to end "
                                        "(`aew harness stop|wait`) before migrating", runs=live)
            # The v1 digest of each open parent, before the state changes form (R3).
            legacy = {wid: self.hierarchy.children_digest(state, wid) for wid, u in sorted(state["work"].items())
                      if H.is_parent(u) and u["state"] not in H.TERMINAL}
            before = {"units": len(state["work"]), "invocations": len(state["invocations"]),
                      "tokens": len(state["tokens"])}
            state["schema"] = V2
            state["cold"] = {"root": M.empty_root()}
            ctx = TxnContext(session=s, actor=actor, prewrite=True)
            self.k.finalizers.run(ctx)  # archival (R6), with its records pre-written (R8)
            committed = ctx.commit_state or state
            for wid, v1 in legacy.items():
                committed["work"][wid]["legacy_digest"] = {
                    "v1": v1, "v2_at_migration": self.hierarchy.children_digest(committed, wid)}
            archived = (committed["cold"].get("archived") or {})
            summary = (f"control state migrated to v2: {before['units'] - len(committed['work'])} finished units "
                       f"archived ({archived.get('done', 0)} DONE, {archived.get('cancelled', 0)} CANCELLED), "
                       f"{len(committed['work'])} open units stay hot")
            revision = s.commit(Transition(op="migrate", actor=actor, summary=summary,
                                           reason="ADR-0011: finished work leaves the hot state"),
                                expect_rev=expect_rev, state=committed)
        for effect in ctx.after_commit:  # retired observation worktrees, as after any archival commit
            try:
                effect()
            except (AEWError, OSError):
                pass
        return {"ok": True, "migrated": True, "schema": V2, "revision": revision, "summary": summary,
                "archived": {"units": before["units"] - len(committed["work"]),
                             "invocations": before["invocations"] - len(committed["invocations"]),
                             "credentials": before["tokens"] - len(committed["tokens"])},
                "history": {"entries": committed["cold"]["root"]["count"]},
                "hot": {"units": len(committed["work"]), "invocations": len(committed["invocations"]),
                        "credentials": len(committed["tokens"])},
                "legacy_digests": sorted(legacy)}
