"""The operator's confirmation of a plan acceptance and of a publish (the operator's ruling of 2026-11-26; E350).

Accepting a Ticket's plan and publishing its candidate are the operator's decisions. In the operator's words: "Its me
basically approving a plan fits requirements and final verification of the outputs actually does what I want it to".
So when a Lead session carries one out, through its broker's relay, its typed tools or its steering loop, the commit
needs the operator's confirmation, given through the operator endpoint's challenge, the out-of-band path `aew lead mode
raise` uses (A1 §1.1):

1. The operator runs `aew operator confirm plan <T>` or `aew operator confirm publish <T>` at their own terminal.
2. The endpoint previews the decision here (:func:`preview`): the exact plan revision and its SHA-256, or the exact
   candidate commit and its base. It shows them on its console with a one-time code, and the operator types the code
   back at their terminal.
3. The endpoint records the confirmation (:func:`confirm`), with the ``OperatorPrincipal`` only it constructs, bound
   to that plan or candidate: one per decision and unit, in :data:`REL` under ``.aew``, written under the control lock.
4. The Lead's `plan accept` or publish uses it in its own commit, once (:func:`consume`). That commit's summary names
   it, and the commit declares its provenance (:data:`aew.engine.outbox.CONFIRMATION_USED`: the id, what it binds,
   when and by which principal), so the record outlives the held one it drops. A plan or candidate other than the one
   confirmed is refused, and so is a call with no confirmation: the refusal says what to ask the operator.

**Why it is not a control commit.** A Lead asks the operator at the revision it read, and its call states that
revision (`--expect-rev`). A confirmation that moved the revision would refuse the very call it answers as stale, on
every plan and every publish. So it is held beside control state, changes no revision, and enters the transition log
with the commit that uses it.

**How long one stands.** A confirmation does not end with the Lead's generation, as a steering raise does: the
generation it was given under is recorded, never checked. It stands until a Lead session's call uses it, the
operator's own `plan accept` or publish of that unit drops it, or the operator confirms the same decision on the same
unit again, which replaces it. There is no command that withdraws one.

**Nothing a Lead passes counts.** No argument, flag or reason string carries a confirmation: the engine reads it only
from what the endpoint recorded, and a Lead session cannot reach the endpoint (`lead_broker.OPERATOR_ENDPOINT`).

**Who is asked.** A call that a Lead session carries is: its channel (:mod:`aew.engine.dispatch`) is not the operator's
own CLI or an in-process caller (:data:`OPERATOR_CHANNELS`). The broker runs every Lead's command and typed tool, in
both the contained and the uncontained Lead session, so this one check covers both, and the client in the Lead's shell
never asks again. The operator's own `aew plan accept` or `aew integrate publish`, at their own terminal with the Lead
credential, is the decision itself and asks nothing more.

**Interim** (E350): the wire track replaces the typed code with DECIDE_WORK_PROPOSAL and APPROVE_INTEGRATION as
G3-protected O-01 actions. A consumed G3 approval would then stand in for the code at the endpoint, as it does for the
steering raise (`g3_adapter.BINDINGS`), and the binding and consumption here stay as they are.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from aew.engine import dispatch, outbox
from aew.engine.base import V2
from aew.errors import IllegalTransition, MigrationRequired, NotFound, OperatorAuthorizationRequired, UsageError
from aew.knowledge.records import format_id
from aew.util import atomic_write, utc_now

if TYPE_CHECKING:
    from pathlib import Path

    from aew.engine.base import Kernel, TxnContext

PLAN, PUBLISH = "plan", "publish"
DECISIONS = (PLAN, PUBLISH)
# What each decision lets a Lead session commit: the plan's acceptance, and the publish's intent commit (the
# publication decision; its CAS, sync and DONE follow it, and `integrate reconcile` finishes one already decided).
COMMITS = {PLAN: "plan.accept", PUBLISH: "integrate.publishing"}
# The channels that are the operator's own: the `aew` CLI outside a Lead session, and an in-process caller.
OPERATOR_CHANNELS = frozenset({dispatch.CLI, dispatch.DIRECT})
# Where the standing confirmations are held, under ``.aew``: beside control state, never in it (the module's note).
REL = "local/operator/confirmations.json"
SCHEMA = "aew/operator-confirmations/v1"
# Reason codes of the refusals (stable: the Lead's text and tests read them).
REQUIRED, STALE = "operator_confirmation_required", "operator_confirmation_stale"
MOVED = "operator_confirmation_moved"
NOT_ENDPOINT = "operator_confirmation_not_endpoint"  # a principal the operator endpoint did not construct
NO_TERMINAL = "no_terminal"  # `aew operator confirm` with no terminal to type the code back at


def command(decision: str, work_id: str, revision: int | str | None = None) -> str:
    """The operator's command for a confirmation: the one owner of its words, which every refusal and text uses."""
    tail = f" --revision {revision}" if decision == PLAN and revision is not None else ""
    return f"aew operator confirm {decision} {work_id}{tail}"


def required() -> bool:
    """Whether the call in progress needs the operator's confirmation: a Lead session carries it."""
    return dispatch.current_channel() not in OPERATOR_CHANNELS


def _unit(state: dict[str, Any], work_id: str) -> dict[str, Any]:
    unit = (state.get("work") or {}).get(work_id)
    if unit is None:
        raise NotFound(f"no active work unit {work_id}", work_id=work_id)
    return unit


def subject(state: dict[str, Any], decision: str, work_id: str, revision: int | None = None) -> dict[str, Any]:
    """What a confirmation of ``decision`` on ``work_id`` binds now, or the refusal that says why there is nothing to
    confirm: a plan's revision, path and SHA-256 (the proposed revision named, else the newest proposed one), or a
    publish's candidate commit and base."""
    unit = _unit(state, work_id)
    if decision == PLAN:
        proposed = [p for p in unit.get("plans") or [] if p.get("status") == "proposed"]
        named = [p for p in proposed if revision is None or p["revision"] == revision]
        if not named:
            which = f"plan revision {revision}" if revision is not None else "plan revision"
            raise IllegalTransition(f"{work_id} has no proposed {which} to confirm: the Lead proposes one first",
                                    work_id=work_id, revision=revision,
                                    proposed=[p["revision"] for p in proposed])
        plan = max(named, key=lambda p: p["revision"])
        return {"revision": plan["revision"], "path": plan["path"], "sha256": plan["sha256"]}
    if decision == PUBLISH:
        integ = unit.get("integration") or {}
        if unit.get("state") != "COMMIT_READY" or not integ.get("candidate") or integ.get("status") == "publishing":
            raise IllegalTransition(f"{work_id} has no prepared integration candidate to confirm: it is "
                                    f"{unit.get('state')}, integration {integ.get('status')}", work_id=work_id,
                                    state=unit.get("state"), integration=integ.get("status"))
        return {"candidate": integ["candidate"], "base": integ.get("base"),
                "changed_paths": list(integ.get("changed_paths") or [])}
    raise UsageError(f"a confirmation is of {' or '.join(DECISIONS)}", decision=decision)


def _binds(decision: str, bound: dict[str, Any]) -> str:
    """The one value a confirmation is bound to: the plan's SHA-256, or the candidate commit."""
    return str(bound["sha256"] if decision == PLAN else bound["candidate"])


def preview(k: Kernel, decision: str, work_id: str, revision: int | None = None) -> dict[str, Any]:
    """What a confirmation would bind, or its refusal, before the operator is asked: the endpoint shows it with its
    challenge, and :func:`confirm` refuses if it moved."""
    state = k.store.current()
    return {"project": k.project_id, "decision": decision, "work_id": work_id,
            "title": _unit(state, work_id).get("title"), "subject": subject(state, decision, work_id, revision),
            "generation": int(state["lead"]["generation"]), "revision": state["revision"]}


def confirm(k: Kernel, principal: Any, bound: dict[str, Any]) -> dict[str, Any]:
    """The operator endpoint's record of a confirmation it challenged for, as :func:`preview` bound it. Refused when
    the plan or candidate moved since the operator was shown it. A newer confirmation of the same decision and unit
    replaces an older one. Written under the control lock, and no control commit (the module's note)."""
    from aew.engine.steering import OperatorPrincipal  # local: publication modules never import steering (CWR §11)

    if not isinstance(principal, OperatorPrincipal):
        raise OperatorAuthorizationRequired("a plan or publish confirmation is the operator's, through the operator "
                                            "endpoint (`aew operator serve`); nothing else can give it",
                                            reason=NOT_ENDPOINT)
    decision, work_id = bound["decision"], bound["work_id"]
    with k.store.session() as s:  # the lock and the state as it stands; nothing is committed
        state = s.state
        if state.get("schema") != V2:
            raise MigrationRequired("this project's control state is v1: migrate it first")
        now = subject(state, decision, work_id, bound["subject"].get("revision"))
        if _binds(decision, now) != _binds(decision, bound["subject"]):
            raise OperatorAuthorizationRequired(
                f"the {_what(decision)} of {work_id} changed while the operator was asked; nothing was confirmed: run "
                f"`{command(decision, work_id)}` again", reason=MOVED, shown=_binds(decision, bound["subject"]),
                current=_binds(decision, now))
        held = _read(k.aew_root)
        cid = format_id("OC", held["next"])
        held["next"] += 1
        held["standing"][_key(decision, work_id)] = {
            "id": cid, "decision": decision, "work_id": work_id, "binds": _binds(decision, now), "subject": now,
            "generation": int(state["lead"]["generation"]), "at": utc_now(), "rev": s.revision,
            "by": principal.record()}
        _write(k.aew_root, held)
    return {"ok": True, "confirmation": cid, "decision": decision, "work_id": work_id, "subject": now,
            "revision": s.revision, "guarantee": principal.guarantee}


def consume(k: Kernel, ctx: TxnContext, decision: str, work_id: str, binds: str, *,
            revision: int | None = None) -> str | None:
    """In a Lead transaction that commits ``decision`` on ``work_id`` for ``binds`` (the plan's SHA-256, or the
    candidate commit): the operator's confirmation of exactly that, and its id; or the refusal. It is dropped once the
    commit has landed, so it is used once, and a transaction that fails later keeps it. ``None`` when the call is the
    operator's own (:func:`required`): it is the decision itself, so a confirmation still standing for it is dropped
    with it, never left for a later call."""
    held = _read(k.aew_root)["standing"].get(_key(decision, work_id))
    if held is not None:
        ctx.after_commit.append(lambda: _drop(k.aew_root, decision, work_id, held["id"]))
    if not required():
        return None
    then = command(decision, work_id, revision)
    if held is None:
        # Says what the operator does, never what they are challenged with: the challenge is the operator's and
        # stays at their terminal (O-SECRET: a model is never asked for a code).
        raise OperatorAuthorizationRequired(
            f"the {_what(decision)} of {work_id} is the operator's decision, and it waits for their confirmation, "
            f"which they give in their own channel: tell the operator it waits for them to run `{then}` at their own "
            "terminal, and call this again once they have confirmed it. Nothing this session passes counts as their "
            "confirmation", reason=REQUIRED, decision=decision, work_id=work_id, ask_operator=then)
    if held["binds"] != binds:
        raise OperatorAuthorizationRequired(
            f"the operator confirmed the {_what(decision)} of {work_id} for {held['binds'][:12]}, not the "
            f"{binds[:12]} this would commit: ask the operator to run `{then}` again for the current one, then call "
            "this again", reason=STALE, decision=decision, work_id=work_id, confirmed=held["binds"], current=binds,
            ask_operator=then)
    # Its provenance goes into this commit's record, since the held one is dropped once the commit lands (review of
    # #618, m1). The ids count again if `.aew/local` is removed, so what it binds and when stand beside the id.
    ctx.events.append({"kind": outbox.CONFIRMATION_USED, "id": held["id"], "decision": decision, "work": work_id,
                       "binds": held["binds"], "at": held["at"], "generation": held["generation"], "by": held["by"]})
    return str(held["id"])


def standing(aew_root: Path) -> list[dict[str, Any]]:
    """The confirmations not yet used, oldest first."""
    return sorted(_read(aew_root)["standing"].values(), key=lambda c: c["id"])


def _read(aew_root: Path) -> dict[str, Any]:
    """The held confirmations. A file that is missing, unreadable or not this schema holds none: a confirmation that
    cannot be read is not one."""
    try:
        held = json.loads((aew_root / REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        held = None
    if (not isinstance(held, dict) or held.get("schema") != SCHEMA or not isinstance(held.get("next"), int)
            or not isinstance(held.get("standing"), dict)):
        return {"schema": SCHEMA, "next": 1, "standing": {}}
    return held


def _write(aew_root: Path, held: dict[str, Any]) -> None:
    path = aew_root / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(held, indent=2, sort_keys=True) + "\n")


def _drop(aew_root: Path, decision: str, work_id: str, cid: str) -> None:
    """Remove the confirmation ``cid`` once the commit that used it has landed (under the same control lock); a newer
    one that replaced it meanwhile stays."""
    held = _read(aew_root)
    if (held["standing"].get(_key(decision, work_id)) or {}).get("id") == cid:
        del held["standing"][_key(decision, work_id)]
        _write(aew_root, held)


def _key(decision: str, work_id: str) -> str:
    return f"{decision}:{work_id}"


def _what(decision: str) -> str:
    return "plan acceptance" if decision == PLAN else "publish"
