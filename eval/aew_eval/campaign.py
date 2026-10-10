"""One released cell: the evaluator's side of the evaluator/arm-host split (F19 plan v5 §2.3, S4; ADR-0018; the
held-out corpus isolation decision of 2026-10-06, §2 and §3).

:func:`run_released_cell` runs one preregistered cell **on an arm host**, through a
:class:`~aew_eval.transport.Transport`. The evaluator holds the corpus, the preregistration, the ledgers and the
oracle; the arm host gets one task's release bundle and nothing else. The order is the release protocol's (§2.3),
less what later slices add (the reset is S6's, the supervisor S8's, the classifier S7's):

1. **Refuse before anything is counted** (:class:`Refused`): the frozen inputs, as the single-host runner checks them;
   the arm must be ``scripted`` (deny by default: every model arm waits for its supervisor, S8 and S9); a case with an
   oracle must have the committed one on this side.
2. **Preflight** the arm host, bound to the run, the treatment, the base and the snapshot. A held-out case is never
   released on a preflight that is not established (HOC-11): the refusal is recorded in the release ledger, and
   nothing is registered.
3. **Register** the attempt with its ``release`` block (host, snapshot, the preflight's and the bundle's hashes)
   **before the bundle leaves**.
4. **Release** the bundle; the arm host verifies it against its manifest.
5. **Run** the arm there.
6. **Collect** the final tree as a bundle, under hostile receive (:func:`aew_eval.transport.receive`).
7. **Finalize** once, in :func:`aew_eval.runner.score_run`'s shape (``outcome.scoring`` deferred, with the export
   and its hash), so the oracle scores it afterwards on this side. Each fact names who attests it
   (``outcome.attested_by``: the evaluator, the guest agent, the hypervisor, or the model).

Every step appends to ``releases.jsonl``. Nothing here runs an arm: this module imports no arm runner and calls none
(a static test checks it). The validity verdicts written here are provisional until S7's frozen classifier: every
failure after registration is a counted ``invalid_measurement`` with its reason code, never a vanished sample.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew_eval import fixture, hidden, prereg
from aew_eval.arms import ScriptedArm
from aew_eval.canonical import sha256_of
from aew_eval.ledger import RUN_ID, AttemptLedger
from aew_eval.release import ReleaseLedger, RunTerms, build_bundle, run_manifest, task_bytes
from aew_eval.schemas import Invalid
from aew_eval.transport import Limits, Received, TransferError, Transport, receive

RUN = "aew/eval-run/v1"
EVALUATOR, GUEST, HYPERVISOR, MODEL = "evaluator", "guest_agent", "hypervisor", "model_influenced"
ATTESTERS = (EVALUATOR, GUEST, HYPERVISOR, MODEL)
RELEASED_KINDS = frozenset({"scripted"})  # deny by default: every other kind waits for the supervisor (S8, S9)


class Refused(Invalid):
    """The cell was refused before its attempt was registered: nothing is counted, nothing was released."""


class Failure(Exception):  # noqa: N818 (a step's counted failure, carried to the finalize; never escapes)
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


def _call(transport: Transport, verb: str, run_id: str, **kw: Any) -> Any:
    """A call whose transport failure or refused reply is a counted failure of this run."""
    try:
        reply = transport.call(verb, run_id=run_id, **kw)
    except TransferError as exc:
        raise Failure(exc.code if exc.code == "TRANSFER_CORRUPT" else f"TRANSPORT_ERROR:{exc.code}",
                      exc.detail) from None
    if not reply.ok:
        error = reply.error or {"code": "UNKNOWN", "message": ""}
        code = error["code"]
        raise Failure(code if code == "TRANSFER_CORRUPT" else f"ARMHOST_REFUSED:{code}", error["message"])
    return reply


def run_released_cell(frozen: dict[str, Any], *, ledger_dir: Path, cell: str, cases: dict[str, Path],
                      transport: Transport, collect_root: Path, run_name: str, terms: RunTerms,
                      retry_of: str | None = None, hidden_root: Path | None = None,
                      limits: Limits | None = None) -> dict[str, Any]:
    """Run ``cell`` once on ``transport``'s arm host; returns the finalized result. ``collect_root`` is where the
    evaluator keeps what it collects (a fresh ``<run_name>`` under it). Raises :class:`Refused` when nothing was
    registered."""
    env_root = hidden.take_root()  # first: nothing this process starts later can inherit it
    limits = limits or transport.limits
    # 1. Refuse before anything is counted.
    try:
        hidden_root = hidden.resolve_root(hidden_root) if hidden_root is not None else env_root
        if not isinstance(frozen, dict):
            raise Invalid("the preregistration is not a mapping")
        experiment = frozen["experiment"]
        ledger = AttemptLedger(ledger_dir, frozen)  # verifies the frozen record
        order = {o["cell"]: o for o in frozen["assignment"]["order"]}
        if cell not in order:
            raise Invalid(f"{cell} is not a cell of preregistration {experiment!r}")
        entry = order[cell]
        arm = next(a for a in frozen["arms"] if a["id"] == entry["arm"])
        if arm["kind"] not in RELEASED_KINDS:
            raise Invalid(f"arm {arm['id']} is {arm['kind']!r}: a released cell runs the scripted arm only until "
                          "the run supervisor exists (F19 plan v5, S8 and S9)")
        if entry["case"] not in cases:
            raise Invalid(f"no manifest given for case {entry['case']}")
        case = fixture.load(cases[entry["case"]])
        if case.id != entry["case"]:
            raise Invalid(f"{cases[entry['case']]} is case {case.id}, not {entry['case']}")
        snap = fixture.snapshot(case)
        prereg.require_inputs(frozen, case=case.id, arm=arm["id"], case_sha256=snap.sha256,
                              hidden_sha256=case.manifest["hidden_sha256"], roles=frozen["profiles"]["roles"],
                              arm_config=arm["config"])
        commitment = case.manifest["hidden_sha256"]
        held_out = case.id in frozen["held_out"]
        oracle = hidden.Oracle.locate(hidden_root, case.id) if commitment and hidden_root else None
        hidden.require(hidden_root, oracle, case=case.id, commitment=commitment, held_out=held_out)
        ScriptedArm().check(arm["config"], snap)
        seeded = bool(arm["config"].get("seeded"))
        run_id = f"{experiment}/{run_name}"
        if not RUN_ID.match(run_id):
            raise Invalid(f"run id {run_id!r} must be <experiment>/<name>")
        collected = collect_root / run_name
        if collected.exists():
            raise Invalid(f"{collected} exists: every run's collection goes to a fresh directory")
        task = task_bytes(case.manifest.get("task"))
        manifest = run_manifest(terms, run_id=run_id, cell=cell, task=task)
        bundle = build_bundle(snap, run_id=run_id, arm=arm, seeded=seeded, task=task, manifest=manifest,
                              limits=limits)
        start = fixture.starting_files(snap, seeded=seeded)
        base_sha256 = fixture._digest(start)  # noqa: SLF001 (one hashing rule for every tree)
    except Exception as exc:  # noqa: BLE001 (anything before registering, an unreadable file included, is a refusal)
        raise Refused(f"{type(exc).__name__}: {exc}" if not isinstance(exc, Invalid) else str(exc)) from None
    releases = ReleaseLedger(ledger_dir, experiment)
    host = transport.host
    # 2. Preflight, bound to the run, the treatment, the base and the snapshot.
    binding = {"run_id": run_id, "treatment_sha256": terms.treatment_sha256, "base_sha256": base_sha256,
               "snapshot_uuid": host.snapshot_uuid}
    try:
        reply = transport.call("preflight", run_id=run_id, args={"binding": binding})
        if not reply.ok:
            raise Invalid(f"the arm host refused its preflight: {reply.error}")
        found = reply.result
        if found["binding"] != binding:
            raise Invalid("the preflight answered for another binding")
        if held_out and not found["established"]:
            raise Invalid(f"case {case.id} is held out and the arm host's preflight did not establish corpus "
                          "isolation: nothing is released (held-out corpus isolation decision, §3; HOC-11)")
    except Exception as exc:  # noqa: BLE001 (a preflight that fails or refuses releases nothing)
        reason = exc.code if isinstance(exc, TransferError) else "PREFLIGHT_REFUSED"
        releases.append(run_id, "preflight_refused", {"host": host.name, "reason": reason, "detail": str(exc)[-600:]})
        raise Refused(f"preflight on {host.name}: {exc}") from None
    preflight_sha256 = sha256_of(found)
    releases.append(run_id, "preflight", {"host": host.name, "preflight_sha256": preflight_sha256,
                                          "established": found["established"]})
    # 3. Register, before the bundle leaves.
    release = {"host": host.name, "snapshot_uuid": host.snapshot_uuid, "preflight_sha256": preflight_sha256,
               "bundle_sha256": bundle.sha256}
    try:
        line = ledger.register(run_id=run_id, cell=cell, requested_profile=frozen["profiles"]["roles"],
                               retry_of=retry_of, release=release)
    except Invalid as exc:  # refused before writing anything (a counted cell, a reused run id)
        raise Refused(str(exc)) from None
    except Exception as exc:  # noqa: BLE001 (as the single-host runner: refused only if provably unwritten)
        try:
            written = run_id in ledger.attempts()
        except Exception:  # noqa: BLE001
            written = True
        if written:
            raise RuntimeError(f"registering {run_id} failed after its line may have been written ({exc}): the "
                               "attempt is runner_lost") from exc
        raise Refused(str(exc)) from None
    releases.append(run_id, "registered", {"bundle_sha256": bundle.sha256})
    # 4-6. Release, run, collect. A failure from here on is counted, with its reason.
    validity: dict[str, Any] = {"status": "valid", "reason_code": None}
    ran: dict[str, Any] = {}
    outcome: dict[str, Any] = {}
    received: Received | None = None
    try:
        reply = _call(transport, "release", run_id, args={"bundle_sha256": bundle.sha256}, payload=bundle.tar)
        if reply.result["bundle_sha256"] != bundle.sha256:
            raise Failure("TRANSFER_CORRUPT", "the arm host received another bundle")
        releases.append(run_id, "released", {"bundle_sha256": bundle.sha256,
                                              "run_manifest_sha256": bundle.run_manifest_sha256})
        ran = _call(transport, "run", run_id, args={"deadline_s": terms.wall_s},
                    timeout_s=terms.wall_s + limits.timeout_s).result
        releases.append(run_id, "ran", {"base_commit": ran["base_commit"], "error": ran["error"]})
        reply = _call(transport, "collect", run_id)
        collected.parent.mkdir(parents=True, exist_ok=True)
        try:
            received = receive(reply.payload, collected, limits=limits,
                               expected_sha256=reply.result["manifest_sha256"])
        except TransferError as exc:
            raise Failure(exc.code if exc.code == "TRANSFER_CORRUPT" else f"RESULT_REFUSED:{exc.code}",
                          exc.detail) from None
        other = {**reply.result["other"]}
        export = collected / "tree"
        export.mkdir(exist_ok=True)
        final = fixture.files_of(export)
        now = fixture.WorkTree(final.files, {**{p[len("tree/"):]: f"{fixture.LINK} -> {t}"
                                                for p, t in received.links.items()}, **other})
        outcome["changed_paths"] = fixture.changed_paths(start, now)
        if reply.result["other_omitted"]:
            outcome["changed_paths_omitted"] = reply.result["other_omitted"]
        outcome["scoring"] = {"deferred": True, "export": str(export.resolve()),
                              "export_sha256": fixture._digest(fixture._read_tree(export, "export")),  # noqa: SLF001
                              "oracle_commitment": commitment}
        outcome["score"] = None
        releases.append(run_id, "collected", {"manifest_sha256": received.sha256})
        if ran["error"] is not None:
            validity = {"status": "invalid_measurement", "reason_code": "ARMHOST_ARM_ERROR"}
            outcome["error"] = ran["error"]
    except Failure as exc:
        validity = {"status": "invalid_measurement", "reason_code": exc.reason_code}
        outcome["error"] = exc.detail[-600:]
        releases.append(run_id, "failed", {"reason_code": exc.reason_code})
    except Exception as exc:  # noqa: BLE001 (the attempt is counted either way; the reason is recorded)
        validity = {"status": "invalid_measurement", "reason_code": f"EVALUATOR_ERROR:{type(exc).__name__}"}
        outcome["error"] = str(exc)[-600:]
        releases.append(run_id, "failed", {"reason_code": validity["reason_code"]})
    chain = releases.head()
    # 7. Finalize, once, in score_run's shape.
    record = {
        "schema": RUN, "experiment": experiment, "preregistration_sha256": frozen["canonical_sha256"],
        "run_id": run_id,
        "case": {"id": case.id, "sha256": snap.sha256, "hidden_sha256": commitment},
        "arm": {"id": arm["id"], "kind": arm["kind"], "config_sha256": sha256_of(arm["config"])},
        "profile": {"requested": line["requested_profile"], "observed": [], "mismatch": None},
        "aew": {}, "harness": ran.get("harness", {}),
        "environment": {**ran.get("environment", {}), "host": host.name},
        "assignment": {**line["assignment"], "randomization_seed": frozen["assignment"]["seed"]},
        "validity": validity, "started_at": ran.get("started_at"), "ended_at": ran.get("ended_at"),
        "wall_s": ran.get("wall_s"),
        "limits": {"deadline_s": terms.wall_s, "caps": {"usd": terms.cap_usd, "wall_s": terms.wall_s}},
        # The arm host's own outcome is kept under its own key: nothing it reports can stand in for a fact the
        # evaluator records (a forged ``scoring`` block, say).
        "outcome": {**outcome, "arm_outcome": ran.get("outcome", {}), "base_commit": ran.get("base_commit"),
                    "safety": {"checkout_untouched": None},  # the arm host has no AEW checkout to touch
                    "release": {**release, "run_manifest_sha256": bundle.run_manifest_sha256,
                                "task_input_sha256": bundle.task_input_sha256, "chain_sha256": chain},
                    "attested_by": ATTESTED_BY},
        "aew_facts": {}, "cost": {}, "notes": None,
    }
    digest = ledger.finalize(record)
    releases.append(run_id, "finalized", {"result_sha256": digest, "validity": validity["status"]})
    return record


# Who attests each fact of a released run's record (plan v5 §4). Keys are the record's paths.
ATTESTED_BY: dict[str, str] = {
    "case": EVALUATOR, "arm": EVALUATOR, "assignment": EVALUATOR, "profile.requested": EVALUATOR,
    "outcome.release": EVALUATOR, "outcome.release.snapshot_uuid": HYPERVISOR,
    "outcome.changed_paths": EVALUATOR, "outcome.scoring": EVALUATOR, "validity": EVALUATOR,
    "environment": GUEST, "environment.host": EVALUATOR, "harness": GUEST, "started_at": GUEST, "ended_at": GUEST,
    "wall_s": GUEST,
    "outcome.base_commit": GUEST, "outcome.arm_outcome": GUEST,
    "outcome.scoring.export": MODEL,  # the delivered tree is the model's work; its hash is the evaluator's
}

