"""Subjects shown for approvals and compared by their committing transactions."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from aew.errors import ChangedSinceRead, IntegrityError
from aew.util import sha256_text


def digest(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


PRIOR_LOG_WINDOW = 64


def prior_state(op: str, subject: str, expected: str | None, current: str, *,
                root: Path, state: dict[str, Any]) -> None:
    prior(op, subject, "state", expected, current, root=root, state=state,
          event=lambda row: row["kind"] == "work.state" and row["id"] == subject)


def prior(op: str, subject: str, field: str, expected: str | None, current: str, *,
          root: Path, state: dict[str, Any], event: Callable[[dict[str, Any]], bool] | None = None,
          record: str | None = None, work_id: str | None = None) -> None:
    require_binding(op, subject, field, expected, work_id=work_id)
    if expected == current:
        return
    source = ""
    if record is None and event is not None:
        from aew.engine.outbox import LogView

        since = (state.get("outbox") or {}).get("since")
        if since is not None:
            log = LogView(root, since, retries=0)
            through = state["revision"]
            for revision in range(through, max(since - 1, through - PRIOR_LOG_WINDOW), -1):
                try:
                    rows = log.events(log.record(revision)) or ()
                except IntegrityError:
                    source = "The change record could not be read. "
                    break
                if any(event(row) for row in rows):
                    record = f"control revision {revision}"
                    break
        if record is None and not source:
            source = f"No matching change record in the last {PRIOR_LOG_WINDOW} commits. "
    refuse_change(op, subject, field, expected, current, changed_by=record,
                  next_step=source + "Read the current value before deciding whether to try again.")


def parent_change(work_id: str) -> Callable[[dict[str, Any]], bool]:
    return lambda row: row["kind"] == "work.binding" and row["id"] == work_id and row["field"] == "parent"


def parent_value(unit: dict[str, Any]) -> str:
    return unit.get("parent") or "none"


def promotion_value(unit: dict[str, Any]) -> str:
    return f"{unit['kind']}:{parent_value(unit)}"


def run_value(invocation: dict[str, Any]) -> str:
    runs = invocation.get("runs") or []
    return runs[-1]["run"] if runs else "none"


def override_value(state: dict[str, Any]) -> str:
    return ((state.get("steering") or {}).get("override") or {}).get("record") or "none"


def role_plan_digest(unit: dict[str, Any]) -> str:
    plan = unit.get("role_plan") or {}
    return digest({slot: plan.get(slot, []) for slot in ("execute", "review", "verify", "forbidden")})


def bound_argv(argv: tuple[str, ...], value: str) -> list[str]:
    return [*argv, "--prior-value", value]


def refuse_change(op: str, subject: str, field: str, expected: Any, current: Any, *,
                  changed_by: Any = None, next_step: str, reason: str = "changed_since_read", **details: Any) -> None:
    change = f" Changed by {changed_by}." if changed_by is not None else ""
    raise ChangedSinceRead(
        f"{op}: {subject}'s {field} changed since read (expected {expected}, current {current}).{change} {next_step}",
        op=op, subject=subject, field=field, expected=expected, current=current,
        changed_by=changed_by, next_step=next_step, reason=reason, **details,
    )


_Binding = TypeVar("_Binding")


def require_binding(op: str, subject: str, field: str, binding: _Binding | None, *,
                    work_id: str | None = None) -> _Binding:
    """Missing observations never become approvals of whatever is current at commit."""
    if binding is None:
        step = _binding_step(op, subject, field, work_id)
        raise ChangedSinceRead(
            f"{op}: the call has no binding for {subject}'s {field}. {step}",
            op=op, subject=subject, field=field, reason="missing_binding", next_step=step,
        )
    return binding


def _binding_step(op: str, subject: str, field: str, work_id: str | None) -> str:
    if op == "manifest.adopt":
        return ("Review the changed files shown by `aew manifest adopt --reason <reason>` at the operator terminal. "
                "API callers read `manifest_approval()` and pass its result as `binding`.")
    status = f"aew status {work_id or subject}"
    if op in {"integrate.defer", "integrate.requeue"}:
        return (f"Read the queue decision for {work_id or subject} with `work_show` and pass the shown "
                "`--prior-value` from its CLI fallback.")
    if field != "approval subject":
        command = {
            "harness.launch": f"aew harness status {subject}",
            "steering.lower": "aew status --json",
            "work.staff": f"aew work roles {subject}",
        }.get(op, status)
        return (f"Read the current {field} with `{command}` and pass it as `--prior-value` "
                "(`prior_value` in a typed call).")
    if op == "integrate.publishing":
        return (f"Read the current candidate with `{status} --json` and pass it as `--candidate` "
                "(`prepared_candidate` in the stage call).")
    if op == "integrate.breaker_reset":
        return ("Read the current failure list and digest with `aew integrate breaker status`. "
                "API callers pass the shown digest as `binding`.")
    if op in {"authority.accept", "authority.reject"}:
        return ("Review the candidate shown by the authority command at the terminal. API callers read "
                "`authority_candidate()` and pass its digest as `binding`. An explicit acceptance digest uses "
                "`--approval-digest`.")
    if op == "work.gate_replace":
        return "Read the replacement in the typed `resume` projection and pass its `approval_digest` to `resolve`."
    if op == "work.dispose":
        return ("Read the disposition decision in the typed `resume` projection and pass its digest as "
                "`--approval-digest` (`approval_digest` in `resolve`).")
    command = {
        "stage.continue": "aew resume --json",
        "waive": f"aew gate show {work_id}",
        "work.close": f"aew gate show {subject}",
    }.get(op, f"{status} --json")
    return f"Read the approval subject with `{command}` and pass its digest as `--approval-digest` (`approval_digest`)."


def compare(op: str, subject: str, expected: str | None, current: str | None, *,
            next_step: str = "Read the subject again and decide anew.", work_id: str | None = None,
            **details: Any) -> None:
    """A digest mismatch may include uncommitted file edits, so it has no general change-record lookup."""
    if op != "manifest.adopt":
        require_binding(op, subject, "approval subject", expected, work_id=work_id)
    if expected != current:
        refuse_change(op, subject, "approval subject", expected, current, next_step=next_step, **details)


def execution_record_digest(record: dict[str, Any]) -> str:
    return digest({"id": record["id"], "sha256": record["sha256"]})


def closeout_digest(snapshot: dict[str, Any]) -> str:
    return digest({"children_digest": snapshot["children_digest"], "base_revision": snapshot["base_revision"]})


def cascade_digest(work_id: str, descendants: list[str]) -> str:
    return digest({"parent": work_id, "descendants": sorted(descendants)})


def input_subject(evidence_id: str, sha256: str, commit: str | None) -> dict[str, Any]:
    value = {"evidence": evidence_id, "sha256": sha256, "commit": commit}
    return {"subject": value, "digest": digest(value)}


def failure_digest(unit: dict[str, Any], evidence_id: str | None) -> str:
    sha = next((r["sha256"] for r in unit.get("evidence", []) if r["id"] == evidence_id), None)
    return digest({"id": evidence_id, "sha256": sha})


def failure_ref(op: str, unit: dict[str, Any], evidence_id: str | None, binding: str | None, *,
                work_id: str) -> str | None:
    compare(op, evidence_id or "verification failure", binding, failure_digest(unit, evidence_id), work_id=work_id)
    return f"{evidence_id}@record:{binding}"


def gate_digest(context: dict[str, Any], gate: str) -> str:
    return digest({"gate": gate, "snapshot": context["snapshot"], "obligations": context["obligations"],
                   "result": context["gates"].get(gate)})


def command(op: str, work_id: str, binding: str, *options: str) -> list[str]:
    """The relay arguments carry the digest of the subject shown."""
    route = {"input.acknowledge": "work acknowledge-input", "waive": "gate waive"}.get(op, op.replace(".", " "))
    return [*route.split(), work_id, *options, "--approval-digest", binding]
