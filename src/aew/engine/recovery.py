"""Bounded recovery: one automatic relaunch of a stage's failed launch (M4-E E8b; plan v3 E8; BRP R5-3 as amended by
A2; amendment 1, R2-m2).

**Off by default.** ``execution.recovery.relaunch_launch_failed`` is 0 unless the operator adopts 1; at 0 a failed
launch stops its stage at ``launch_failed`` and the Lead decides, as before. The setting and the breaker's bounds are
operational policy, snapshotted at each recovery decision (A3 §5): a change before the relaunch commits re-evaluates
that pending recovery inside the relaunch's own transaction, and never stales anything else.

**Where (N2c).** Only the stage runner calls :meth:`Recovery.relaunch`, at a stage's ``launch_failed`` stop, under the
broker's Lead credential (``aew.surface.stage``). A launch from ``aew harness launch``, ``--launch`` on the CLI or the
recovery ``cli`` escape never reaches it, and the supervisor's part stays authority-reducing: it only observes, and
says what it observed over its acknowledgement pipe (``aew.harness.supervisor``).

**Eligibility** (BRP-04, BRP-06; A2 §2 to §6), every condition required:

- the reason code is on :data:`ALLOW_LIST`, a set of its own (not the validation module's ``V.TRANSIENT``). The code
  is taken only from where the launcher got it (``reason_code_source``): the supervisor's acknowledgement over its
  pipe, or the launcher's own value when custody was never acknowledged. Anything else, a code read from the
  model-writable run directory included, counts as ``unknown`` (R2-m2, R3-n1). Nothing maps a real failure to an
  allow-listed code yet (``contract.launch_failure_code``), so no failure reaches one by default;
- the invocation is still active, the failed run is its latest and holds its current credential, and its dispatch
  decision, base binding and legality digest are those bound at the failure;
- the Ticket's state and attempt are those bound at the failure, and no blocked report, unresolved finding, open
  anomaly or required disposition exists for it (BRP §6);
- it is the invocation's first relaunch; a second failure raises attention and nothing more;
- the termination proof for this platform holds (:func:`termination_proof`), and the no-side-effect proof for every
  channel (:func:`no_side_effect_proof`): what cannot be observed makes the run ineligible;
- the relaunch breaker for the failure's scope is closed. An eligible failure is counted in it; the one that reaches
  the threshold opens it, is not relaunched, and the operator is notified (``breaker_tripped``, subject
  ``relaunch_breaker``). Only ``aew recovery breaker reset`` at the operator endpoint closes it.

**The relaunch** is one Lead transaction: a new ``harness.launch`` decision, then the failed run's credential is
revoked, the revocation confirmed through the normal check (``run_authority_problem``), and only then a new credential
minted for the new run id (A2 §3). The invocation's ``relaunch`` record binds the failed run, both proofs, the
revocation reference, the reason code, the breaker's state, the policy snapshot, the stage intent and the new run
(A2 §7). Both runs stay in ``runs[]``. The new run goes to its supervisor like any launch.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from aew.engine import faults
from aew.engine import gates as G
from aew.engine.authority import issue_token, revoke
from aew.engine.base import V2
from aew.engine.steering import GUARANTEE, OperatorPrincipal
from aew.engine.store import Transition
from aew.errors import (
    AEWError,
    IllegalTransition,
    MigrationRequired,
    NotFound,
    PermissionDenied,
    StaleRevision,
    UsageError,
)
from aew.harness import contract as K
from aew.knowledge import evidence as E
from aew.util import sha256_text, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.harness_ops import Harness

# The launch-failure codes R5-3 may relaunch (plan v3 E8: initial and narrow; A2 §5). Its own set: never the
# validation module's transient codes. ``server_start_transport`` only before the task prompt was delivered, which the
# network channel's proof requires of every relaunch anyway.
ALLOW_LIST = frozenset({K.SPAWN_RACE, K.SERVER_START_TRANSPORT})
# Where a launch failure's code may come from (``HarnessLaunchFailed``'s ``reason_code_source``): the supervisor's
# acknowledgement, over its pipe, or the launcher's own value. ``run_record`` and anything else count as ``unknown``.
TRUSTED_SOURCES = frozenset({"acknowledgement", "launcher"})
# A cause shared by every harness and provider on this host: its failures count in the project-wide breaker scope.
SHARED_CAUSES = frozenset({K.SPAWN_RACE})
PROJECT_SCOPE = "project"
BREAKER_SUBJECT = "relaunch_breaker"
BREAKER_DEFAULTS = {"threshold": 3, "window_s": 300}  # A2 §6: 3 eligible failures in 5 minutes

# Why a failed launch is not relaunched (the verdict's ``reasons``).
RELAUNCH_OFF = "relaunch_off"
REASON_NOT_ALLOWED = "reason_not_allowed"
INVOCATION_NOT_ACTIVE = "invocation_not_active"
RUN_SUPERSEDED = "run_superseded"
BINDING_CHANGED = "binding_changed"
TICKET_CHANGED = "ticket_changed"
ADVERSE_RECORD = "adverse_record"
ALREADY_RELAUNCHED = "already_relaunched"
TERMINATION_UNPROVEN = "termination_unproven"
SIDE_EFFECT_POSSIBLE = "side_effect_possible"
BREAKER_OPEN = "breaker_open"
BREAKER_TRIPPED = "breaker_tripped"

# A2 §2, per platform: every mechanism that applies must agree. ``supervisor_exited`` is the launcher's own
# observation of the supervisor process; the rest are the supervisor's (``ProcessTree.termination``).
TERMINATION = {
    "linux": ("record_ended", "tree_empty", "pids_gone", "sentinel_released", "supervisor_exited"),
    "win32": ("record_ended", "tree_empty", "pids_gone", "supervisor_exited"),
}


def setting(policy: dict[str, Any] | None) -> dict[str, Any]:
    """The recovery policy snapshot a decision binds: the switch, the breaker's bounds and their digest."""
    given = (policy or {}).get("recovery") or {}
    snap = {"relaunch_launch_failed": int(given.get("relaunch_launch_failed") or 0),
            "breaker": {**BREAKER_DEFAULTS, **(given.get("breaker") or {})}}
    return {**snap, "digest": sha256_text(repr(sorted((k, repr(v)) for k, v in snap.items())))}


def acknowledged_code(details: dict[str, Any]) -> tuple[str, str | None]:
    """A launch failure's code as eligibility may read it: the code the launcher took from the supervisor's
    acknowledgement or set itself, and ``unknown`` for any other source or any value outside the closed set."""
    code, source = details.get("reason_code"), details.get("reason_code_source")
    if source not in TRUSTED_SOURCES or not isinstance(code, str) or code not in K.LAUNCH_FAILURE_CODES:
        return K.UNKNOWN_LAUNCH_FAILURE, source if isinstance(source, str) else None
    return code, source


def failure_of(details: dict[str, Any], *, intent: str | None) -> dict[str, Any]:
    """What a ``HarnessLaunchFailed`` raised in this process says, as recovery reads it: the run, its invocation, the
    acknowledged code and the observations that came with the acknowledgement (none otherwise)."""
    code, source = acknowledged_code(details)
    observations = details.get("observations") if details.get("reason_code_source") == "acknowledgement" else None
    return {"run": details.get("run"), "invocation": details.get("invocation"), "reason_code": code,
            "reason_code_source": source, "observations": copy.deepcopy(observations) if isinstance(
                observations, dict) else None, "intent": intent}


def termination_proof(observations: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """A2 §2: the observations this platform's proof needs, each of which must be ``True``. A missing, unreadable or
    false one, or a platform with no rule, is a gap; a stale heartbeat or a ``launch_failed`` label proves nothing."""
    obs = observations or {}
    platform = str(obs.get("platform") or "")
    rule = TERMINATION.get("linux" if platform.startswith("linux") else platform)
    if not observations:
        return {"platform": platform or None, "observed": {}}, ["no observation reached the launcher"]
    if rule is None:
        return {"platform": platform, "observed": {}}, [f"no termination proof is defined on {platform!r}"]
    observed = {name: obs.get(name) for name in rule}
    gaps = [f"{name}: {observed[name]!r}" for name in rule if observed[name] is not True]
    if obs.get("termination_error"):
        gaps.append(f"termination: {obs['termination_error']}")
    return {"platform": platform, "observed": observed}, gaps


class Recovery:
    """Relaunch eligibility, the relaunch's commit, and the relaunch breaker (M4-E E8b)."""

    def __init__(self, k: Kernel, *, harness: Harness) -> None:
        self.k = k
        self.harness = harness

    # ------------------------------------------------------------------ the decision

    def decide(self, failure: dict[str, Any]) -> dict[str, Any]:
        """The recovery decision at a stage's ``launch_failed`` stop: the verdict against the committed state, with the
        policy snapshot it was taken under and what it binds of the failure (A2 §7: the relaunch record binds these
        values as they were at failure time). Read-only."""
        state = self.k.store.read()
        policy, _ = self.k.execution_policy()
        snap = setting(policy)
        binding = self._binding(state, failure)
        verdict = self.evaluate(state, failure, binding, snap)
        return {**verdict, "failure": failure, "binding": binding, "policy": snap}

    def _binding(self, state: dict[str, Any], failure: dict[str, Any]) -> dict[str, Any] | None:
        inv = state["invocations"].get(str(failure.get("invocation")))
        if inv is None:
            return None
        unit = state["work"].get(inv["work_unit"]) or {}
        return {"decision": (inv.get("dispatch") or {}).get("decision"),
                "base": _digest(inv.get("snapshot")),
                "legality_digest": (inv.get("dispatch") or {}).get("legality_digest"),
                "token_id": inv.get("token_id"), "unit_state": unit.get("state"), "attempts": unit.get("attempts"),
                "execution_attempt": (unit.get("execution") or {}).get("attempt")}

    def evaluate(self, state: dict[str, Any], failure: dict[str, Any], binding: dict[str, Any] | None,
                 snap: dict[str, Any]) -> dict[str, Any]:
        """Every eligibility condition against ``state``: the verdict, each unmet condition's code and detail, both
        proofs, and the breaker scope. Called at the decision and again inside the relaunch's transaction."""
        reasons: dict[str, list[str]] = {}

        def no(code: str, detail: str) -> None:
            reasons.setdefault(code, []).append(detail)

        if snap["relaunch_launch_failed"] != 1:
            no(RELAUNCH_OFF, "execution.recovery.relaunch_launch_failed is 0: the Lead decides (BRP §5)")
        code = failure.get("reason_code") or K.UNKNOWN_LAUNCH_FAILURE
        if code not in ALLOW_LIST:
            no(REASON_NOT_ALLOWED, f"{code} (from {failure.get('reason_code_source') or 'no trusted source'}) is not "
                                   "on the relaunch allow-list")
        termination, gaps = termination_proof(failure.get("observations"))
        for gap in gaps:
            no(TERMINATION_UNPROVEN, gap)
        if reasons:  # off, unproven or never relaunched: the rest is not read (no workspace is fingerprinted)
            return {"eligible": False, "reasons": sorted(reasons), "detail": reasons, "reason_code": code,
                    "scope": None, "termination_proof": termination, "no_side_effect_proof": {}}
        inv_id, run = str(failure.get("invocation")), failure.get("run")
        inv = state["invocations"].get(inv_id)
        side_effects: dict[str, Any] = {}
        scope = None
        if inv is None or binding is None:
            no(INVOCATION_NOT_ACTIVE, f"{inv_id} is not an invocation of this project")
        else:
            scope = scope_of(inv, code)
            self._invocation_checks(state, inv_id, inv, run, binding, no)
            side_effects = self.no_side_effect_proof(state, inv_id, inv, run, failure.get("observations"), no)
            breaker = ((state.get("recovery") or {}).get("breakers") or {}).get(scope) or {}
            if breaker.get("open"):
                no(BREAKER_OPEN, f"the relaunch breaker for {scope} is open since {breaker['open'].get('at')}: "
                                 "`aew recovery breaker reset` at the operator endpoint closes it")
        return {"eligible": not reasons, "reasons": sorted(reasons), "detail": reasons, "reason_code": code,
                "scope": scope, "termination_proof": termination, "no_side_effect_proof": side_effects}

    def _invocation_checks(self, state: dict[str, Any], inv_id: str, inv: dict[str, Any], run: Any,
                           binding: dict[str, Any], no: Any) -> None:
        if inv.get("status") != "active":
            no(INVOCATION_NOT_ACTIVE, f"{inv_id} is {inv.get('status')}")
        runs = inv.get("runs") or []
        if not runs or runs[-1]["run"] != run or runs[-1].get("token_id") != inv.get("token_id"):
            no(RUN_SUPERSEDED, f"{run} is not {inv_id}'s latest run holding its current credential")
        if inv.get("relaunch") or any(r.get("kind") == "relaunch" for r in runs):
            no(ALREADY_RELAUNCHED, f"{inv_id} was relaunched once already: a second failure raises attention only")
        now = self._binding(state, {"invocation": inv_id}) or {}
        for name in ("decision", "base", "legality_digest", "token_id"):
            if now.get(name) != binding.get(name) or binding.get(name) is None:
                no(BINDING_CHANGED, f"{name}: bound {binding.get(name)!r}, now {now.get(name)!r}")
        if inv.get("dispatch", {}).get("legality_digest") != self.k.policy_digests()["legality_digest"]:
            no(BINDING_CHANGED, "the legality-affecting policy changed since the dispatch")
        tok = (state["tokens"].get(inv.get("token_id")) or {}).get("scope") or {}
        if tok.get("generation") != state["lead"]["generation"]:
            no(BINDING_CHANGED, "the credential was issued under a superseded Lead generation")
        for name in ("unit_state", "attempts", "execution_attempt"):
            if now.get(name) != binding.get(name):
                no(TICKET_CHANGED, f"{name}: bound {binding.get(name)!r}, now {now.get(name)!r}")
        for item in self._adverse(state, inv["work_unit"]):
            no(ADVERSE_RECORD, item)

    def _adverse(self, state: dict[str, Any], wid: str) -> list[str]:
        """BRP §6: a blocked report, an unresolved finding, an open anomaly or a required disposition for the subject.
        One that cannot be read counts."""
        from aew.engine import disposition_ops as DO

        unit = state["work"].get(wid) or {}
        found = [f"open anomaly {an}" for an, a in sorted((state.get("anomalies") or {}).items())
                 if a.get("subject") == wid]
        found += [f"unresolved finding {f['id']}" for f in G.open_required_findings(unit)]
        try:
            marked = DO.marks(self.k.policy("gates"))
            found += [f"required disposition {i['id']}" for i in DO.undisposed(DO.unit_items(marked, unit), unit)]
        except (AEWError, OSError) as exc:
            found.append(f"the dispositions could not be read: {exc}")
        try:
            records, _ = E.scan(self.k.aew_root, wid)
            found += [f"blocked report {e['id']}" for e in records if e.get("result") == "blocked"]
        except (AEWError, OSError) as exc:
            found.append(f"the evidence store could not be read: {exc}")
        return found

    def no_side_effect_proof(self, state: dict[str, Any], inv_id: str, inv: dict[str, Any], run: Any,
                             observations: dict[str, Any] | None, no: Any) -> dict[str, Any]:
        """A2 §4, per channel (plan v3 E8's table). The run log, the bridge and the network come from the supervisor's
        acknowledgement; the evidence store, the workspace and its refs are read here. Any channel that cannot be
        observed fails the proof."""
        obs = observations or {}
        proof: dict[str, Any] = {}
        requests = obs.get("bridge_requests")
        proof["run_log"] = proof["bridge"] = requests
        if requests != 0:
            no(SIDE_EFFECT_POSSIBLE, f"bridge and run log: {requests!r} tool request(s) reached the run's bridge")
        delivered = obs.get("prompt_delivered")
        proof["network"] = {"prompt_delivered": delivered}
        if delivered is not False:
            no(SIDE_EFFECT_POSSIBLE, "network: not observable while shared, and the supervisor does not record the "
                                     f"task prompt as never delivered ({delivered!r})")
        try:
            produced = [e["id"] for e in E.scan(self.k.aew_root, inv["work_unit"])[0]
                        if e["producer"].get("run") == run]
        except (AEWError, OSError) as exc:
            produced = [f"unreadable: {exc}"]
        proof["evidence"] = produced
        if produced:
            no(SIDE_EFFECT_POSSIBLE, f"evidence: {', '.join(produced)}")
        bound = inv.get("snapshot") or {}
        try:
            workspace, workspace_id, _ = self.harness.invocations.invocation_workspace(state, inv)
            now = self.harness.invocations.snapshot_of(workspace, workspace_id)
        except (AEWError, OSError) as exc:
            now = {"error": str(exc)}
        proof["workspace"] = {"bound": bound.get("relevant_inputs_fingerprint"),
                              "now": now.get("relevant_inputs_fingerprint")}
        proof["refs"] = {"bound": bound.get("base_revision"), "now": now.get("base_revision")}
        for channel in ("workspace", "refs"):
            if proof[channel]["bound"] is None or proof[channel]["bound"] != proof[channel]["now"]:
                why = f" ({now['error']})" if "error" in now else ""
                no(SIDE_EFFECT_POSSIBLE, f"{channel}: dispatch bound {proof[channel]['bound']!r}, now "
                                         f"{proof[channel]['now']!r}{why}")
        return proof

    # ------------------------------------------------------------------ the relaunch

    def relaunch(self, *, token: str, decision: dict[str, Any]) -> dict[str, Any]:
        """Commit the relaunch ``decision`` allowed, re-evaluated inside the transaction under the policy in force
        then (a setting changed since the decision re-evaluates this pending recovery, never STALE_POLICY), and hand
        the new run to its supervisor. Returns ``{"relaunched": False, ...}`` with the verdict when the commit finds
        it ineligible, or records only the breaker's opening; raises ``HarnessLaunchFailed`` when the new run fails
        too (attention only: the invocation has had its one relaunch)."""
        faults.pause("recovery.before_relaunch_commit")  # tests: a setting changed while the recovery is pending
        failure, binding = decision["failure"], decision["binding"]
        inv_id = str(failure["invocation"])
        out: dict[str, Any] = {}
        for attempt in range(3):  # follow the revision across others' commits; everything is re-evaluated each time
            expect_rev = int(self.k.store.read()["revision"])
            try:
                with self.k.lead_txn(token, expect_rev, "harness.launch") as ctx:
                    out = self._commit(ctx, failure, binding, decision["policy"])
                    out["revision"] = ctx.session.revision + 1
                break
            except _Ineligible as nothing:  # nothing pending commits: an empty transaction would only move the revision
                return {"relaunched": False, **nothing.args[0], "revision": int(self.k.store.read()["revision"])}
            except StaleRevision:
                if attempt == 2:
                    raise
        credential = out.pop("credential", None)
        if credential is None:  # the breaker opened at this failure: recorded, nothing relaunched
            return out
        launched = self.harness.spawn_relaunched(inv_id, out["new_run"], credential)
        del credential
        return {**out, "launch": launched}

    def _commit(self, ctx: Any, failure: dict[str, Any], binding: dict[str, Any] | None,
                decided_under: dict[str, Any]) -> dict[str, Any]:
        state = ctx.state
        policy, _ = self.k.execution_policy()
        snap = setting(policy)
        verdict = self.evaluate(state, failure, binding, snap)
        changed = snap["digest"] != decided_under["digest"]
        common = {"verdict": verdict, "policy": snap, "reevaluated": changed}
        if not verdict["eligible"]:
            raise _Ineligible(common)
        breaker = self._count(state, verdict["scope"], failure, snap)
        if breaker["open"]:  # it was closed (the verdict requires it): this failure reached the threshold
            ctx.op = "recovery.breaker_trip"
            ctx.summary = (f"relaunch breaker for {verdict['scope']} opened at {failure['run']}'s launch failure "
                           f"({verdict['reason_code']}): relaunch is off for that scope until the operator resets it")
            ctx.refs.extend([f"run:{failure['run']}", str(failure.get("intent") or "")])
            verdict = {**verdict, "eligible": False, "reasons": [BREAKER_TRIPPED],
                       "detail": {BREAKER_TRIPPED: [f"{len(breaker['failures'])} eligible launch failures in "
                                                    f"{snap['breaker']['window_s']}s in {verdict['scope']}"]}}
            return {"relaunched": False, **common, "verdict": verdict, "breaker": copy.deepcopy(breaker)}
        inv_id, failed = str(failure["invocation"]), str(failure["run"])
        inv = state["invocations"][inv_id]
        self.harness.dispatch.decide_in(ctx, "harness.launch", inv["work_unit"], invocation=inv_id)
        runs = inv["runs"]
        new_run = K.run_id(inv_id, len(runs) + 1)
        # A2 §3: revoke the failed run's credential, confirm through the normal check that it no longer acts, and only
        # then mint the new run's.
        old = inv["token_id"]
        revoke(state, old, f"relaunched: {new_run} (recovery, {verdict['reason_code']})")
        confirmed = self.harness.run_authority_problem(state, inv_id, failed, old)
        if not (confirmed or "").startswith("credential revoked"):
            raise IllegalTransition(f"{failed}'s credential revocation could not be confirmed ({confirmed!r}): the "
                                    "relaunch is not committed", reason="revocation_unconfirmed")
        tok = state["tokens"][old]
        credential = issue_token(state, "invocation", dict(tok["scope"]))
        inv["token_id"] = credential.split(".")[1]
        runs.append({"run": new_run, "harness": inv["execution_profile"]["harness"], "token_id": inv["token_id"],
                     "launched_at": utc_now(), "kind": "relaunch", "generation": state["lead"]["generation"]})
        inv["relaunch"] = {
            "failed_run": failed, "new_run": new_run, "reason_code": verdict["reason_code"],
            "reason_code_source": failure.get("reason_code_source"),
            "termination_proof": verdict["termination_proof"], "no_side_effect_proof": verdict["no_side_effect_proof"],
            "revocation": {"token_id": old, "revoked_at": tok["revoked_at"], "reason": tok["revoke_reason"],
                           "confirmed": confirmed},
            "breaker": {"scope": verdict["scope"], **copy.deepcopy(breaker)}, "policy": snap,
            "intent": str(failure.get("intent") or ""), "at": utc_now(), "rev": ctx.session.revision + 1}
        ctx.refs.extend([f"run:{new_run}", f"run:{failed}", str(failure.get("intent") or "")])
        ctx.summary = (f"{new_run} relaunched for {inv_id} after {failed}'s launch failure ({verdict['reason_code']}): "
                       f"recovery policy {snap['digest'][:12]}, stage {failure.get('intent')}; credential rotated")
        return {"relaunched": True, **common, "new_run": new_run, "failed_run": failed, "credential": credential,
                "record": copy.deepcopy(inv["relaunch"])}

    def _count(self, state: dict[str, Any], scope: str, failure: dict[str, Any],
               snap: dict[str, Any]) -> dict[str, Any]:
        """Count an eligible failure in its scope's breaker window, and open the breaker at the threshold (A2 §6)."""
        threshold, window = int(snap["breaker"]["threshold"]), int(snap["breaker"]["window_s"])
        breakers = state.setdefault("recovery", {"breakers": {}}).setdefault("breakers", {})
        breaker = breakers.setdefault(scope, {"failures": [], "open": None})
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=window)
        breaker["failures"] = [f for f in breaker["failures"] if _parse(f["at"]) >= cutoff]
        breaker["failures"].append({"at": _iso(now), "run": str(failure["run"]), "reason_code": failure["reason_code"]})
        if len(breaker["failures"]) >= threshold:
            breaker["open"] = {"at": _iso(now), "reason_codes": sorted({f["reason_code"] for f in breaker["failures"]}),
                               "runs": [f["run"] for f in breaker["failures"]]}
        breaker["failures"] = breaker["failures"][-threshold:]  # fixed size (plan v3 §2.7)
        return breaker

    # ------------------------------------------------------------------ the breaker, for the operator

    def breaker_status(self) -> dict[str, Any]:
        state = self.k.store.read()
        try:
            policy, _ = self.k.execution_policy()
            snap = setting(policy)
        except AEWError:
            snap = setting(None)
        breakers = copy.deepcopy(((state.get("recovery") or {}).get("breakers")) or {})
        return {"subject": BREAKER_SUBJECT, "relaunch_launch_failed": snap["relaunch_launch_failed"],
                "threshold": snap["breaker"]["threshold"], "window_s": snap["breaker"]["window_s"],
                "open": sorted(s for s, b in breakers.items() if b.get("open")), "breakers": breakers}

    def reset_preview(self, scope: str | None) -> dict[str, Any]:
        """What a reset would close, or its refusal, before the operator is asked at the endpoint."""
        state = self.k.store.read()
        return {"project": self.k.project_id, "scopes": self._open_scopes(state, scope),
                "revision": state["revision"]}

    def reset(self, principal: OperatorPrincipal, *, scope: str | None, reason: str,
              scopes: list[str]) -> dict[str, Any]:
        """Close the relaunch breaker for ``scope`` (every open scope when None): the operator endpoint's commit, after
        its peer check and the challenge at its console (plan v3 E8: ``relaunch_breaker_reset``). Refused unless it
        closes exactly the ``scopes`` the operator was shown."""
        if not isinstance(principal, OperatorPrincipal):
            raise PermissionDenied("resetting the relaunch breaker is the operator's, through the operator endpoint "
                                   "(`aew operator serve`); nothing else can authorize it")
        if not reason.strip():
            raise UsageError("resetting the relaunch breaker needs a reason")
        with self.k.store.session() as s:
            state = s.state
            if state.get("schema") != V2:
                raise MigrationRequired("this project's control state is v1: migrate it first")
            self.k.check_manifest_pin(state)
            now_open = self._open_scopes(state, scope)
            if now_open != sorted(scopes):
                raise IllegalTransition(f"the open relaunch breaker scopes changed while the operator was asked (shown "
                                        f"{sorted(scopes)}, now {now_open}): run `aew recovery breaker reset` again",
                                        reason="stale_breaker")
            actor = {"kind": "operator", "principal": principal.record()}
            breakers = state["recovery"]["breakers"]
            for name in now_open:
                breakers[name] = {"failures": [], "open": None,
                                  "reset": {"at": utc_now(), "reason": reason[:400], "by": principal.record()}}
            rev = s.commit(Transition(op="recovery.breaker_reset", actor=actor, refs=list(now_open), reason=reason,
                                      summary=f"relaunch breaker reset by the operator at the operator endpoint: "
                                              f"{', '.join(now_open)}"))
        return {"ok": True, "subject": BREAKER_SUBJECT, "reset": now_open, "revision": rev, "guarantee": GUARANTEE}

    @staticmethod
    def _open_scopes(state: dict[str, Any], scope: str | None) -> list[str]:
        breakers = ((state.get("recovery") or {}).get("breakers")) or {}
        if scope is not None and scope not in breakers:
            raise NotFound(f"no relaunch breaker scope {scope!r}", known=sorted(breakers))
        found = sorted(s for s, b in breakers.items() if b.get("open") and (scope is None or s == scope))
        if not found:
            raise IllegalTransition("no relaunch breaker is open" + (f" for {scope}" if scope else ""),
                                    reason="breaker_closed")
        return found


class _Ineligible(Exception):  # noqa: N818  carries an ineligible verdict out of the transaction, which commits nothing
    """``args[0]``: the verdict, the policy snapshot and whether the setting changed since the decision."""


def scope_of(inv: dict[str, Any], code: str) -> str:
    """The breaker scope of a failure: project-wide when its cause is shared, else the harness and provider endpoint
    the invocation was dispatched to (A2 §6)."""
    if code in SHARED_CAUSES:
        return PROJECT_SCOPE
    profile = inv.get("execution_profile") or {}
    return f"{profile.get('harness') or 'unknown'}:{profile.get('provider') or 'unknown'}"


def _digest(value: Any) -> str | None:
    if value is None:
        return None
    return sha256_text(repr(sorted(value.items())) if isinstance(value, dict) else repr(value))


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
