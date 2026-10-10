"""The AEW engine facade: the single state authority used by every adapter.

The CLI (and a future MCP adapter) call these methods; neither implements
workflow semantics of its own (WC §15.6, invariant 21).

``Engine`` is the composition root (register E5): it builds the Kernel and the collaborators, each given
exactly the collaborators it uses, fills the seams between them (``seams``) in a fixed order, and delegates
every public operation to the one collaborator that owns it. No collaborator holds a reference to the Engine.
"""

from __future__ import annotations

import re
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from aew import SPEC_SET
from aew.engine import usage_ops
from aew.engine.archive_ops import Archive
from aew.engine.assurance_ops import Assurance
from aew.engine.base import POLICY_PINS, Kernel, TxnContext, policy_files
from aew.engine.context_ops import ContextPacks
from aew.engine.dispatch import Dispatch
from aew.engine.evidence_ops import EvidenceCommands, Gates
from aew.engine.harness_ops import Harness
from aew.engine.hierarchy_ops import Hierarchy
from aew.engine.history_ops import HistoryCommands
from aew.engine.integration_ops import Integration
from aew.engine.lead_ops import Lead
from aew.engine.migrate_ops import Migration
from aew.engine.nonmutating_ops import Inputs, NonMutating
from aew.engine.ports import ArchivePort, RolesPort, SteeringPort
from aew.engine.queue_ops import Queue
from aew.engine.resume_ops import Resume
from aew.engine.role_ops import Roles
from aew.engine.seams import GuardTable, KindRegistry, StateHooks
from aew.engine.stage_intents import StageIntents
from aew.engine.status_ops import StatusViews
from aew.engine.steering import OperatorPrincipal, Steering
from aew.engine.store import ControlStore
from aew.engine.validation_ops import Validation
from aew.engine.work_ops import WorkCommands, WorkUnits
from aew.engine.workspace_ops import Assignment, Invocations, mutating_cap
from aew.errors import AEWError, IllegalTransition, IntegrityError, NotFound, UsageError
from aew.harness import contract as K
from aew.history import manifest as history_manifest
from aew.knowledge import discovery
from aew.knowledge.manifest import (
    AEW_DIR,
    DEFAULT_CHECKS,
    DEFAULT_GATES,
    DEFAULT_GUARDRAILS,
    MANIFEST,
    default_manifest,
    load_manifest,
    open_questions_template,
    project_overview_template,
    render_manifest,
    roles_readme,
)
from aew.operator import require_operator_attribution
from aew.policy import execution as X
from aew.schemas import validate
from aew.util import dump_yaml, load_yaml, sha256_bytes, sha256_text, utc_now
from aew.workspace import git

AEW_GITIGNORE = "# Rebuildable/runtime data (KC §5.3) and spent redo records.\nlocal/\nstate/txn/\n"
AUTHORITY_CLASSES = ("contracts", "decisions", "schemas", "source", "orientation")


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-._")
    return slug or "project"


class ProjectAdmin:
    """The project's authority registry, manifest adoption and `aew doctor`."""

    def __init__(self, k: Kernel, *, roles: RolesPort, steering: SteeringPort, archive: ArchivePort) -> None:
        self.k = k
        self.roles = roles
        self.steering = steering
        self.archive = archive

    def authority_list(self) -> dict[str, Any]:
        self.k.store.read()  # recovery + integrity
        return {"accepted": self.k.manifest["authority"]["accepted"],
                "candidates": self.k.manifest["authority"]["candidates"]}

    def _rewrite_manifest(self, ctx, manifest: dict[str, Any]) -> None:
        validate("project", manifest, source="updated manifest")
        text = render_manifest(manifest)
        ctx.session.write(MANIFEST, text, immutable=False)
        ctx.state["manifest_sha256"] = sha256_text(text)

    def authority_accept(self, *, token: str, expect_rev: int, candidate_id: str, klass: str,
                         decided_by: str = "lead", reason: str | None = None,
                         authorization: dict[str, str] | None = None) -> dict[str, Any]:
        if klass not in AUTHORITY_CLASSES:
            raise UsageError(f"class must be one of {AUTHORITY_CLASSES}")
        require_operator_attribution(decided_by == "operator", authorization, "an authority decision")
        with self.k.lead_txn(token, expect_rev, "authority.accept", reason=reason) as ctx:
            manifest = self._fresh_manifest()
            candidate = self._candidate(manifest, candidate_id)
            if candidate["status"] != "proposed":
                raise IllegalTransition(f"{candidate_id} is already {candidate['status']}")
            by = dict(ctx.actor, kind="operator" if decided_by == "operator" else "lead",
                      recorded_by_lead=True, **(authorization or {}))
            decision = self.k.new_decision(
                ctx, "authority_acceptance",
                f"Accepted {candidate['path']} as {klass} authority",
                decided_by=by, reason=reason, evidence_refs=[candidate["path"]],
            )
            candidate["status"] = "accepted"
            manifest["authority"]["accepted"].append(
                {"id": candidate_id, "path": candidate["path"], "class": klass, "decision": decision})
            self._rewrite_manifest(ctx, manifest)
            ctx.summary = f"authority accepted: {candidate['path']} ({klass})"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def authority_reject(self, *, token: str, expect_rev: int, candidate_id: str,
                         reason: str | None = None) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "authority.reject", reason=reason) as ctx:
            manifest = self._fresh_manifest()
            candidate = self._candidate(manifest, candidate_id)
            if candidate["status"] != "proposed":
                raise IllegalTransition(f"{candidate_id} is already {candidate['status']}")
            decision = self.k.new_decision(ctx, "authority_rejection",
                                         f"Rejected {candidate['path']} as project authority", reason=reason)
            candidate["status"] = "rejected"
            self._rewrite_manifest(ctx, manifest)
            ctx.summary = f"authority candidate rejected: {candidate['path']}"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision}

    def manifest_adopt(self, *, token: str, expect_rev: int, reason: str,
                       authorization: dict[str, str] | None = None) -> dict[str, Any]:
        """Accept a reviewed manual edit of project.yaml or of the policy files it names by re-pinning them (recorded
        decision). A project whose policy files were never pinned has them pinned here. The operator's decision, always
        confirmed at their own terminal: whoever can edit the policy must not also approve the edit, and a Lead holding
        the raw credential is refused like a Lead session (PR #118 review, finding 1)."""
        require_operator_attribution(True, authorization, "adopting an edit of project.yaml or the policy files")
        manifest_path = self.k.aew_root / MANIFEST
        # Credential and revision are checked by lead_txn before any state-dependent answer.
        with self.k.lead_txn(token, expect_rev, "manifest.adopt", reason=reason, _adopting_manifest=True) as ctx:
            manifest_changed = not self.k.manifest_pin_ok(ctx.state)
            drift = self.k.policy_pin_drift(ctx.state)
            if not manifest_changed and drift == []:
                raise IllegalTransition("project.yaml and the policy files match their pins; nothing to adopt")
            raw = manifest_path.read_bytes()  # pin the exact bytes on disk, not a newline-normalized view
            manifest = load_yaml(raw.decode("utf-8"), source=str(manifest_path))
            validate("project", manifest, source=str(manifest_path))
            pins = self._read_policy_pins(manifest)
            changed = ([MANIFEST] if manifest_changed else []) + (drift or [])
            what = ", ".join(changed) + (" (policy files pinned for the first time)" if drift is None else "")
            decision = self.k.new_decision(ctx, "manifest_adoption", f"Adopted a reviewed manual edit of {what}",
                                         reason=reason, decided_by=dict(ctx.actor, kind="operator",
                                                                        recorded_by_lead=True, **(authorization or {})))
            ctx.state["manifest_sha256"] = sha256_bytes(raw)
            ctx.state[POLICY_PINS] = pins
            # An adopted steering default takes effect here only if it is not a raise (M4-E plan v3 §2.1, N1).
            self.steering.on_adopt(ctx, self.k._execution_policy(manifest, pins)[0])
            ctx.summary = f"manifest and policy re-pinned: {what}"
        return {"ok": True, "decision": decision, "revision": ctx.session.committed_revision, "adopted": changed}

    def _read_policy_pins(self, manifest: dict[str, Any]) -> dict[str, str | None]:
        """The policy files' pins, each hashed from the same bytes it is validated from: a file that does not parse or
        match its schema is refused, never pinned."""
        names = {rel: name for name, rel in (manifest.get("policy") or {}).items()}
        pins: dict[str, str | None] = {}
        optional = X.policy_path(self.k.aew_root, manifest).relative_to(self.k.aew_root).as_posix()
        for rel in policy_files(manifest):
            path = self.k.aew_root / rel
            if not path.is_file():
                if rel != optional:  # only the execution policy may be absent (PR #118 review, finding 3)
                    raise IntegrityError(f"{AEW_DIR}/{rel} is missing: project.yaml names it as required policy; "
                                         "restore it or change project.yaml before adopting", files=[rel])
                pins[rel] = None
                continue
            raw = path.read_bytes()
            data = load_yaml(raw.decode("utf-8"), source=str(path))
            name = names.get(rel, "execution")
            if name in ("guardrails", "checks", "gates", "execution"):
                validate(name, data, source=str(path))
            if name == "pricing":  # parsed as the ledger parses it (a YAML date is the table's `as_of` string)
                from aew.engine.usage_ops import Prices

                Prices(raw, source=str(path))
            if name == "execution":
                X.check_semantics(data, source=str(path))
            pins[rel] = sha256_bytes(raw)
        return pins

    def _fresh_manifest(self) -> dict[str, Any]:
        return load_manifest(self.k.aew_root)

    @staticmethod
    def _candidate(manifest: dict[str, Any], candidate_id: str) -> dict[str, Any]:
        for c in manifest["authority"]["candidates"]:
            if c["id"] == candidate_id:
                return c
        raise NotFound(f"no authority candidate {candidate_id}")

    def _git_drivers_doctor(self) -> tuple[str, str]:
        """Every configured git driver and whether AEW's own git runs it (M4-B review)."""
        drivers: dict[str, dict[str, Any]] = {}
        effective = {d["config"]: d for d in git.configured_drivers(self.k.repo_root)}  # the last definition wins
        for d in effective.values():
            entry = drivers.setdefault(d["driver"], {"kinds": set(), "commands": []})
            entry["kinds"].add(d["kind"])
            if d["key"] in {"clean", "smudge", "process", "command", "textconv", "driver"} and d["value"]:
                entry["commands"].append(f"{d['config']} = `{d['value']}` ({d['origin']})")
        if not drivers:
            return "PASS", "no git filter, diff or merge drivers are configured"
        trusted = git.trusted_drivers()

        def describe(name: str) -> str:
            return f"{name} ({'/'.join(sorted(drivers[name]['kinds']))}: {'; '.join(drivers[name]['commands'])})"
        on = [n for n in sorted(drivers) if n in trusted]
        off = [n for n in sorted(drivers) if n not in trusted]
        listing = (f"AEW's git runs: {', '.join(map(describe, on)) or 'none'}. Switched off (not in "
                   f"containment.trusted_git_drivers): {', '.join(map(describe, off)) or 'none'}")
        risky = [n for n in on for c in drivers[n]["commands"]
                 if (cmd := c.split("`")[1].split()[0] if "`" in c else "") and not Path(cmd).is_absolute()
                 and ("/" in cmd or "\\" in cmd)]
        if risky:
            return "WARN", (f"trusted driver(s) {sorted(set(risky))} run a program by a relative path, which resolves "
                            "inside the repository where agents can edit it: point them at an installed program. "
                            + listing)
        commit = self.k.authoritative_commit()
        try:
            needed = git.untrusted_filters(self.k.repo_root, commit) if commit else []
        except AEWError:
            needed = []
        if needed:
            path = X.policy_path(self.k.aew_root, self.k.manifest)
            inside = path.is_relative_to(self.k.repo_root)
            shown = path.relative_to(self.k.repo_root).as_posix() if inside else str(path)
            return "FAIL", git.untrusted_filters_message(needed, shown, from_doctor=True)
        return "PASS", listing

    def _endpoint_doctor(self, state: dict[str, Any]) -> tuple[str, str]:
        """The operator endpoint and its label (M4-E plan v3 §2.1): it answers a ping or it does not, and every record
        it makes is `guarantee: dev` with the same-uid residuals stated."""
        from aew.harness import operator_client

        try:
            configured = self.steering.policy_default() is not None
        except Exception:  # noqa: BLE001 (an unreadable policy is reported above)
            configured = False
        try:
            info = operator_client.ping(self.k.aew_root)
        except AEWError:
            info = None
        if info is None:
            if not configured and "steering" not in state:
                return "PASS", "not running (steering is not configured; the endpoint is needed only to raise it)"
            return "WARN", ("not running: raising the Lead's steering mode, and unattended Run's notifications, need "
                            "`aew operator serve --dev` in the operator's own terminal")
        host = state["lead"].get("host_uid")
        same = host is None or host == info.get("uid")
        return "WARN", (f"running (pid {info['pid']}), guarantee {info['guarantee']}: not A1/F18 production authority "
                        f"until F18.6{' (the Lead host runs as the same uid)' if same and host is not None else ''}; "
                        f"process dumpable: {info.get('dumpable')}; same-uid residuals: "
                        + "; ".join(info.get("residuals") or []))

    def doctor_checks(self) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []

        def add(name: str, status: str, detail: str) -> None:
            checks.append({"check": name, "status": status, "detail": detail})

        try:
            state = self.k.store.read()
            add("control-state", "PASS", f"revision {state['revision']}, checksum and schema valid")
        except Exception as exc:  # report, never crash
            add("control-state", "FAIL", f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")
            return checks
        try:
            _ = self.k.manifest
            add("manifest", "PASS", "project.yaml parses and matches its schema")
        except Exception as exc:
            add("manifest", "FAIL", f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")
            return checks
        add("manifest-pin", "PASS" if self.k.manifest_pin_ok(state) else "FAIL",
            "project.yaml matches its pinned hash" if self.k.manifest_pin_ok(state)
            else "project.yaml modified outside AEW; the operator reviews it, then `aew manifest adopt`")
        drift = self.k.policy_pin_drift(state)
        if drift is None:
            add("policy-pin", "WARN", "the policy files are not pinned (a project initialized before the pin): the "
                "operator reviews them, then `aew manifest adopt` pins them")
        else:
            add("policy-pin", "FAIL" if drift else "PASS",
                f"modified outside AEW: {', '.join(drift)}; the operator reviews them, then `aew manifest adopt`"
                if drift else "the policy files match their pinned hashes")
        for name in ("guardrails", "checks", "gates"):
            try:
                self.k.policy(name)
                add(f"policy:{name}", "PASS", "valid")
            except Exception as exc:
                add(f"policy:{name}", "FAIL", str(exc))
        found = self.roles.policy_problems()
        add("policy:consistency", "FAIL" if found else "PASS",
            " ".join(found) if found else "gates, checks and role cards agree")
        try:
            execution, _ = self.k.execution_policy()
            if execution is None or not execution["configured"]:
                add("policy:execution", "WARN", "execution policy unconfigured: harness launch is refused until "
                    f"{X.REL_PATH} is configured (or the Lead pins --profile/--model on dispatch)")
            else:
                add("policy:execution", "PASS", f"configured; default profile {execution['routing']['default']}")
        except Exception as exc:
            add("policy:execution", "FAIL", str(exc))
        # F25 (the cost and usage ledger design v0.2 R4, R6): the price table, the snapshots usage records name (the
        # hot state and the recent ring: a bounded read; `aew usage show --all` covers the whole archive), and the
        # hot runs' copy state.
        add("policy:pricing", *usage_ops.pricing_doctor(self.k.manifest, self.k.pricing))
        try:
            recent = [b for r in state.get("recent") or [] if (b := self.archive.bundle(state, r["id"])) is not None]
            add("pricing-snapshots", *usage_ops.snapshot_doctor(state, self.k.aew_root, recent))
        except Exception as exc:  # report, never crash
            add("pricing-snapshots", "FAIL", f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")
        add("usage-ledger", *usage_ops.ledger_doctor(state, usage_ops.Reader(self.k.aew_root, None)))
        from aew.harness import containment
        from aew.harness import contract as K
        try:
            policy_now = self.k.execution_policy()[0]
        except Exception:
            policy_now = None
        # The actual guarantee, probed live and never implied (AEW-INV-ISO-001, M4-B).
        add("containment", *containment.doctor(policy_now, K.CONTAINMENT_NOTE))
        add("git-drivers", *self._git_drivers_doctor())
        try:
            checks_policy = self.k.policy("checks")
            unconfigured = [k for k, v in checks_policy["checks"].items() if not v.get("configured")]
            if unconfigured:
                add("checks-configured", "WARN",
                    f"unconfigured checks {unconfigured}: gates requiring them stay blocked")
            else:
                add("checks-configured", "PASS", "all declared checks configured")
            cap = mutating_cap(self.k.policy("gates"))
            add("mutating-concurrency", "PASS",
                f"{cap}: up to {cap} mutating Ticket(s) hold a live workspace at once, each in its own worktree; "
                "integration stays serialized (gates.yaml mutating_concurrency)")
        except Exception:  # noqa: S110 (the policy checks above already reported an unreadable policy)
            pass
        from aew.engine import log_compact
        add("transition-log", *log_compact.window_status(self.k.aew_root, state["revision"]))  # ADR-0012 D6
        lead = state["lead"]
        add("lead", "PASS" if lead["status"] == "active" else "WARN",
            f"{lead['status']} (generation {lead['generation']})")
        add("operator-endpoint", *self._endpoint_doctor(state))
        proposed = [c["id"] for c in self.k.manifest["authority"]["candidates"] if c["status"] == "proposed"]
        if proposed:
            add("authority", "WARN", f"unclassified authority candidates: {proposed}")
        return checks


class Engine:
    """The facade over the Engine's collaborators; see the module docstring."""

    def __init__(self, repo_root: Path, aew_root: Path) -> None:
        k = self._k = Kernel(repo_root, aew_root)
        hooks, guards, kinds = StateHooks(), GuardTable(), KindRegistry()
        self._archive = archive = Archive(k)
        self._units = units = WorkUnits(k, hooks=hooks, guards=guards, archive=archive)
        self._history = history = HistoryCommands(k, units=units, archive=archive)
        self._roles = roles = Roles(k, units=units)
        self._invocations = invocations = Invocations(k, roles=roles)
        self._queue = queue = Queue(k, invocations=invocations)
        self._inputs = inputs = Inputs(k)
        self._packs = packs = ContextPacks(k, units=units, archive=archive)
        self._gates = gates = Gates(k, units=units, roles=roles, invocations=invocations, kinds=kinds, archive=archive)
        self._dispatch = dispatch = Dispatch(k)
        self._assurance = assurance = Assurance(k, gates=gates)
        self._work = work = WorkCommands(k, units=units, roles=roles, invocations=invocations, archive=archive)
        self._assignment = assignment = Assignment(k, units=units, roles=roles, invocations=invocations,
                                                   inputs=inputs, packs=packs, dispatch=dispatch)
        self._nm = nm = NonMutating(k, units=units, roles=roles, invocations=invocations, inputs=inputs, packs=packs,
                                    gates=gates, work=work, archive=archive, dispatch=dispatch)
        self._hierarchy = hierarchy = Hierarchy(k, units=units, roles=roles, invocations=invocations, inputs=inputs,
                                                gates=gates, nm=nm, archive=archive, history=history,
                                                dispatch=dispatch)
        self._evidence = evidence = EvidenceCommands(k, units=units, roles=roles, invocations=invocations,
                                                     inputs=inputs, packs=packs, gates=gates, nm=nm, kinds=kinds,
                                                     archive=archive, dispatch=dispatch, queue=queue)
        self._integration = integration = Integration(k, units=units, invocations=invocations, gates=gates,
                                                      dispatch=dispatch, queue=queue)
        queue.legal = integration.require_legal
        self._validation = Validation(k, units=units, invocations=invocations, gates=gates, queue=queue)
        self._harness = harness = Harness(k, invocations=invocations, packs=packs, gates=gates, archive=archive,
                                          dispatch=dispatch)
        self._lead = lead = Lead(k, archive=archive, queue=queue)
        self._views = views = StatusViews(k)
        self._resume = resume = Resume(k, units=units, roles=roles, inputs=inputs, gates=gates, hierarchy=hierarchy,
                                       lead=lead, views=views, harness=harness, history=history, kinds=kinds)
        self._steering = steering = Steering(k)
        self._project = ProjectAdmin(k, roles=roles, steering=steering, archive=archive)
        self._migration = Migration(k, hierarchy=hierarchy, archive=archive)
        self._stages = stages = StageIntents(k, archive=archive)
        # The seams, in their documented order (tests/unit/test_engine_composition.py pins them).
        hooks.before.append(integration.before_state_change)
        hooks.after.extend([invocations.on_state_change, integration.on_state_change])
        guards.register_all(units.guard_registrations())
        guards.register_all(gates.guard_registrations())
        guards.register_all(nm.guard_registrations())
        for owner in (gates, evidence, nm, hierarchy, resume):
            kinds.register_all(owner.kind_registrations())
        kinds.require_complete()
        # M4-A: every dispatch entrypoint's guards, by the collaborator that owns each check.
        for owner in (assignment, nm, evidence, hierarchy, harness, assurance, integration, queue):
            dispatch.register_all(owner.dispatch_guards())
        dispatch.require_complete()
        # The dispatch check first (a new invocation or run needs an allowed decision), then the integration queue
        # (M4-D: entries follow their Tickets, a dead custodian marks its lease for reconciliation), then archival
        # (ADR-0011: finished work leaves the hot state, with its retired queue entries; plan R6). The usage copy
        # (F25 R5) runs just before archival, so a bundle carries every run's usage into the cold state. The stage
        # journal comes first (M4-E E3): a stage step is refused for what it is (STALE_POLICY, a stale owner) before
        # any other finalizer judges the commit, and a completed stage's record is on its unit before archival.
        k.finalizers.steps.extend([stages.finalize, dispatch.finalize, queue.finalize, self._validation.finalize,
                                   usage_ops.UsageCopy(k.aew_root, k.pricing).finalize, archive.finalize])
        k.archived_credential = archive.archived_credential  # an archived credential stays stale authority (R7)

    @classmethod
    def discover(cls, start: Path) -> Engine:
        """The Engine of the authoritative project for ``start`` (``Kernel.locate``)."""
        return cls(*Kernel.locate(start))

    @classmethod
    def initialize(
        cls,
        repo_root: Path,
        *,
        project_id: str | None = None,
        name: str | None = None,
        branch: str | None = None,
        workspaces_root: str | None = None,
    ) -> Engine:
        repo_root = repo_root.resolve()
        top = git.toplevel(repo_root)
        if top is None or top.resolve() != repo_root:
            raise UsageError(f"{repo_root} is not the top level of a git repository")
        if git.is_linked_worktree(repo_root):
            raise UsageError("initialize AEW in the main worktree, not a linked worktree")
        aew_root = repo_root / AEW_DIR
        if (aew_root / "state" / "control.yaml").exists():
            raise IntegrityError(f"{aew_root} is already an initialized AEW project")
        branch = branch or git.current_branch(repo_root)
        if not branch:
            raise UsageError("HEAD is detached; pass --branch to name the authoritative branch")
        project_id = project_id or _slug(repo_root.name)
        name = name or repo_root.name
        workspaces_root = workspaces_root or f"../.aew-workspaces/{project_id}"

        manifest = default_manifest(project_id, name, branch, workspaces_root)
        candidates = discovery.discover_candidates(repo_root)
        manifest["authority"]["candidates"] = candidates
        validate("project", manifest, source="new manifest")
        manifest_text = render_manifest(manifest)
        files = {
            MANIFEST: manifest_text,
            ".gitignore": AEW_GITIGNORE,
            "knowledge/PROJECT.md": project_overview_template(name),
            "knowledge/OPEN-QUESTIONS.md": open_questions_template() + discovery.open_questions_for(candidates),
            "policy/guardrails.yaml": dump_yaml(DEFAULT_GUARDRAILS),
            "policy/checks.yaml": dump_yaml(DEFAULT_CHECKS),
            "policy/gates.yaml": dump_yaml(DEFAULT_GATES),
            X.REL_PATH: X.TEMPLATE,
            "roles/README.md": roles_readme(),
        }
        state = {
            "schema": "aew/control/v2",
            "project_id": project_id,
            "spec_set": SPEC_SET,
            "revision": 0,
            "manifest_sha256": sha256_text(manifest_text),
            POLICY_PINS: {rel: sha256_text(files[rel]) if rel in files else None for rel in policy_files(manifest)},
            "lead": {"schema": "aew/lead/v1", "status": "vacant", "generation": 0, "session_label": None,
                     "token_id": None, "acquired_at": None, "handoff": None},
            "tokens": {},
            "counters": {"ticket": 0, "story": 0, "epic": 0, "invocation": 0, "decision": 0, "handoff": 0},
            "latest_handoff": None,
            "next_action": None,
            "work": {},
            "invocations": {},
            "cold": {"root": history_manifest.empty_root()},  # ADR-0011: finished work is archived here
            "last_transition": {
                "revision": 0, "at": utc_now(), "actor": {"kind": "operator", "command": "aew init"},
                "op": "init", "summary": f"AEW project '{project_id}' initialized", "reason": None,
                "refs": [], "txn": None,
            },
        }
        ControlStore(aew_root).create(state, files)
        return cls(repo_root, aew_root)

    # ------------------------------------------------------------------ delegation (one owner per operation)

    @property
    def repo_root(self) -> Path:
        return self._k.repo_root

    @property
    def aew_root(self) -> Path:
        return self._k.aew_root

    @property
    def store(self) -> ControlStore:
        return self._k.store

    @property
    def authoritative_branch(self) -> Any:
        return self._k.authoritative_branch

    def authoritative_commit(self) -> str | None:
        return self._k.authoritative_commit()

    def authority_accept(self, *, token: str, expect_rev: int, candidate_id: str, klass: str, decided_by: str = "lead",
                         reason: str | None = None, authorization: dict[str, str] | None = None) -> dict[str, Any]:
        return self._project.authority_accept(token=token, expect_rev=expect_rev, candidate_id=candidate_id,
                                              klass=klass, decided_by=decided_by, reason=reason,
                                              authorization=authorization)

    def authority_list(self) -> dict[str, Any]:
        return self._project.authority_list()

    def authority_reject(self, *, token: str, expect_rev: int, candidate_id: str,
                         reason: str | None = None) -> dict[str, Any]:
        return self._project.authority_reject(token=token, expect_rev=expect_rev, candidate_id=candidate_id,
                                              reason=reason)

    def check_manifest_pin(self, state: dict[str, Any]) -> None:
        return self._k.check_manifest_pin(state)

    def check_run(self, *, invocation_token: str, check_id: str, env: dict[str, str] | None = None,
                  layout: Any = None, trees: Any = None, ending: Any = None) -> dict[str, Any]:
        return self._evidence.check_run(invocation_token=invocation_token, check_id=check_id, env=env, layout=layout,
                                        trees=trees, ending=ending)

    def checkpoint(self, *, token: str, expect_rev: int, note: str = "", next_action: str | None = None) -> dict[str,
                   Any]:
        return self._resume.checkpoint(token=token, expect_rev=expect_rev, note=note, next_action=next_action)

    def classify_parent_verification(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                                     reason: str) -> dict[str, Any]:
        return self._hierarchy.classify_parent_verification(token=token, expect_rev=expect_rev, work_id=work_id,
                                                            classification=classification, reason=reason)

    def context_pack(self, inv_id: str) -> dict[str, Any]:
        return self._packs.context_pack(inv_id)

    def context_show(self, inv_id: str) -> str:
        return self._packs.context_show(inv_id)

    def dispatch_binding_problem(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        return self._units.dispatch_binding_problem(state, work_id)

    def doctor_checks(self) -> list[dict[str, str]]:
        return self._project.doctor_checks()

    def evidence_gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._gates.evidence_gate_context(state, work_id)

    def evidence_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._nm.evidence_ingest(token=token, expect_rev=expect_rev, work_id=work_id, evidence_id=evidence_id)

    def execution_policy(self) -> tuple[dict[str, Any] | None, str | None]:
        return self._k.execution_policy()

    def gate_context(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return self._gates.gate_context(state, work_id)

    def dispatch_explain(self, work_id: str, *, entrypoint: str | None = None, role: str | None = None,
                         card: str | None = None, scope: str = "ticket",
                         invocation: str | None = None) -> dict[str, Any]:
        """The dispatch decision the named (or the unit's next) dispatch would get now: the same predicate the
        dispatch evaluates in its own transaction (M4-A)."""
        state = self._k.store.read()
        if invocation is None and not work_id:
            raise UsageError("name a work unit, or --invocation for a harness launch")
        if invocation is not None:
            inv = state["invocations"].get(invocation)
            if inv is None:
                raise NotFound(f"no invocation {invocation}")
            return self._dispatch.explain("harness.launch", inv["work_unit"], invocation=invocation)
        unit = self._units.unit(state, work_id)
        name = entrypoint or self._next_entrypoint(unit)
        return self._dispatch.explain(name, work_id, role=role, card_id=card, scope=scope)

    @staticmethod
    def _next_entrypoint(unit: dict[str, Any]) -> str:
        if unit["kind"] != "ticket":
            return "invoke.create.parent"
        if not unit.get("mutating"):
            return "work.dispatch" if unit["state"] in {"READY", "BLOCKED"} else (
                "work.redispatch" if unit["state"] in {"ASSIGNED", "RUNNING"} else "invoke.create.non_mutating")
        return "work.assign" if unit["state"] in {"READY", "BLOCKED"} else "invoke.create.mutating"

    def plan_lint(self, work_id: str, *, revision: int | None = None) -> dict[str, Any]:
        """Deterministic plan lint (v0.4 §18) of a Ticket's accepted plan, or of the named revision."""
        state = self._k.store.read()
        unit = self._units.unit(state, work_id)
        if unit["kind"] != "ticket":
            raise UsageError("plan lint applies to Tickets (their scope and acceptance)")
        plans = {p["revision"]: p for p in unit.get("plans") or []}
        chosen = plans.get(revision) if revision is not None else plans.get((unit.get("plan") or {}).get("accepted"))
        if revision is not None and chosen is None:
            raise NotFound(f"{work_id} has no plan revision {revision}")
        from aew.engine import assurance as A
        from aew.knowledge.records import read_record

        affected = list(read_record(self._k.aew_root / chosen["path"], "plan").meta.get("affected_paths") or []) \
            if chosen else []
        findings = A.plan_lint(meta=self._gates.record_meta(unit), affected=affected,
                               guardrails=self._k.policy("guardrails"), checks=self._k.policy("checks"),
                               mutating=bool(unit.get("mutating")))
        return {"ok": True, "work_id": work_id, "revision": chosen["revision"] if chosen else None,
                "clean": not findings, "errors": [f for f in findings if f["severity"] == "error"],
                "warnings": [f for f in findings if f["severity"] == "warning"]}

    def gate_show(self, work_id: str) -> dict[str, Any]:
        return self._gates.gate_show(work_id)

    def harness_config(self, harness: str, *, invocation: str | None = None, lead: bool = False) -> dict[str, Any]:
        from aew.harness.opencode import lead as oclead

        return self._harness.harness_config(harness, invocation=invocation, lead=lead,
                                            lead_projection=lambda: oclead.describe(self, provider_env=[]))

    def harness_contract(self, state: dict[str, Any], inv_id: str, run: str) -> K.LaunchContract:
        return self._harness.harness_contract(state, inv_id, run)

    def harness_interrupt(self, *, token: str, run: str) -> dict[str, Any]:
        return self._harness.harness_interrupt(token=token, run=run)

    def harness_launch(self, *, token: str, expect_rev: int, invocation: str, replace: bool = False) -> dict[str, Any]:
        return self._harness.harness_launch(token=token, expect_rev=expect_rev, invocation=invocation, replace=replace)

    def harness_resume(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return self._harness.harness_resume(state)

    def harness_send(self, *, token: str, run: str, text: str) -> dict[str, Any]:
        return self._harness.harness_send(token=token, run=run, text=text)

    def harness_status(self, invocation: str | None = None) -> dict[str, Any]:
        return self._harness.harness_status(invocation)

    def harness_stop(self, *, token: str, run: str, reason: str) -> dict[str, Any]:
        return self._harness.harness_stop(token=token, run=run, reason=reason)

    def harness_wait(self, runs: str | list[str], *, timeout: float = 600.0, any_: bool = False) -> dict[str, Any]:
        return self._harness.harness_wait(runs, timeout=timeout, any_=any_)

    def ingest_evidence_unit_report(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str,
                                    kind: str) -> dict[str, Any]:
        return self._evidence.ingest_evidence_unit_report(token=token, expect_rev=expect_rev, work_id=work_id,
                                                          evidence_id=evidence_id, kind=kind)

    def input_status(self, state: dict[str, Any], work_id: str) -> list[dict[str, Any]]:
        return self._inputs.input_status(state, work_id)

    def integrate_prepare(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        return self._integration.integrate_prepare(token=token, expect_rev=expect_rev, work_id=work_id)

    def integrate_publish(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        return self._integration.integrate_publish(token=token, expect_rev=expect_rev, work_id=work_id)

    def integrate_reconcile(self, *, token: str, expect_rev: int, work_id: str) -> dict[str, Any]:
        return self._integration.integrate_reconcile(token=token, expect_rev=expect_rev, work_id=work_id)

    def integrate_validate(self, *, token: str, expect_rev: int, work_id: str, wait: bool = False,
                           diagnostic: bool = False) -> dict[str, Any]:
        return self._validation.integrate_validate(token=token, expect_rev=expect_rev, work_id=work_id, wait=wait,
                                                   diagnostic=diagnostic)

    def integrate_breaker_status(self) -> dict[str, Any]:
        return self._validation.breaker_status()

    def integrate_breaker_reset(self, *, token: str, expect_rev: int, reason: str,
                                authorization: dict[str, str]) -> dict[str, Any]:
        return self._validation.breaker_reset(token=token, expect_rev=expect_rev, reason=reason,
                                              authorization=authorization)

    def integrate_defer(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        return self._integration.integrate_defer(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def integrate_requeue(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        return self._integration.integrate_requeue(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def integrate_reorder(self, *, token: str, expect_rev: int, work_id: str, before: str | None,
                          reason: str) -> dict[str, Any]:
        return self._integration.integrate_reorder(token=token, expect_rev=expect_rev, work_id=work_id, before=before,
                                                   reason=reason)

    def invocation_whoami(self, *, invocation_token: str) -> dict[str, Any]:
        return self._harness.invocation_whoami(invocation_token=invocation_token)

    def invoke_cancel(self, *, token: str, expect_rev: int, invocation: str, reason: str) -> dict[str, Any]:
        return self._evidence.invoke_cancel(token=token, expect_rev=expect_rev, invocation=invocation, reason=reason)

    def invoke_create(self, *, token: str, expect_rev: int, work_id: str, role: str | None = None,
                      card: str | None = None, scope: str = "ticket", execution_profile: dict[str, Any] | None = None,
                      launch: bool = False) -> dict[str, Any]:
        return self._evidence.invoke_create(token=token, expect_rev=expect_rev, work_id=work_id, role=role, card=card,
                                            scope=scope, execution_profile=execution_profile, launch=launch)

    def invoke_evidence_unit(self, *, token: str, expect_rev: int, work_id: str, role: str | None, card: str | None,
                             scope: str, execution_profile: dict[str, Any] | None = None,
                             launch: bool = False) -> dict[str, Any]:
        return self._evidence.invoke_evidence_unit(token=token, expect_rev=expect_rev, work_id=work_id, role=role,
                                                   card=card, scope=scope, execution_profile=execution_profile,
                                                   launch=launch)

    def invoke_show(self, invocation: str) -> dict[str, Any]:
        return self._evidence.invoke_show(invocation)

    def launch_dispatched(self, result: dict[str, Any]) -> dict[str, Any]:
        return self._harness.launch_dispatched(result)

    def lead_acquire(self, *, expect_rev: int, session_label: str | None = None) -> dict[str, Any]:
        return self._lead.lead_acquire(expect_rev=expect_rev, session_label=session_label)

    def lead_guide(self) -> str:
        return self._resume.lead_guide()

    def lead_handoff_accept(self, *, offer: str, expect_rev: int, session_label: str | None = None) -> dict[str, Any]:
        return self._lead.lead_handoff_accept(offer=offer, expect_rev=expect_rev, session_label=session_label)

    def lead_handoff_cancel(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        return self._lead.lead_handoff_cancel(token=token, expect_rev=expect_rev)

    def lead_handoff_offer(self, *, token: str, expect_rev: int, note: str = "",
                           carry_invocations: list[str] | None = None) -> dict[str, Any]:
        return self._lead.lead_handoff_offer(token=token, expect_rev=expect_rev, note=note,
                                             carry_invocations=carry_invocations)

    def lead_release(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        return self._lead.lead_release(token=token, expect_rev=expect_rev)

    def lead_show(self) -> dict[str, Any]:
        return self._lead.lead_show()

    def lead_takeover(self, *, expect_rev: int, reason: str, session_label: str | None = None) -> dict[str, Any]:
        return self._lead.lead_takeover(expect_rev=expect_rev, reason=reason, session_label=session_label)

    def lead_txn(self, token: str, expect_rev: int | None, op: str, *, reason: str | None = None,
                 allow_pending: bool = False, _adopting_manifest: bool = False) -> AbstractContextManager[TxnContext]:
        return self._k.lead_txn(token, expect_rev, op, reason=reason, allow_pending=allow_pending,
                                _adopting_manifest=_adopting_manifest)

    @property
    def manifest(self) -> Any:
        return self._k.manifest

    def manifest_adopt(self, *, token: str, expect_rev: int, reason: str,
                       authorization: dict[str, str] | None = None) -> dict[str, Any]:
        return self._project.manifest_adopt(token=token, expect_rev=expect_rev, reason=reason,
                                            authorization=authorization)

    def manifest_pin_ok(self, state: dict[str, Any]) -> bool:
        return self._k.manifest_pin_ok(state)

    def policy_pin_drift(self, state: dict[str, Any], manifest: dict[str, Any] | None = None) -> list[str] | None:
        return self._k.policy_pin_drift(state, manifest)

    def new_decision(self, ctx: TxnContext, decision_type: str, summary: str, *, work_unit: str | None = None,
                     classification: str | None = None, evidence_refs: list[str] | None = None,
                     resulting_transition: dict[str, Any] | None = None, reason: str | None = None,
                     decided_by: dict[str, Any] | None = None, body: str = "") -> str:
        return self._k.new_decision(ctx, decision_type, summary, work_unit=work_unit, classification=classification,
                                    evidence_refs=evidence_refs, resulting_transition=resulting_transition,
                                    reason=reason, decided_by=decided_by, body=body)

    def plan_accept(self, *, token: str, expect_rev: int, work_id: str, revision: int) -> dict[str, Any]:
        return self._work.plan_accept(token=token, expect_rev=expect_rev, work_id=work_id, revision=revision)

    def plan_adopt(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str, source: str,
                   reason: str | None = None, review: list[str] | None = None, verify: list[str] | None = None,
                   no_assurance: bool = False) -> dict[str, Any]:
        return self._nm.plan_adopt(token=token, expect_rev=expect_rev, work_id=work_id, evidence_id=evidence_id,
                                   source=source, reason=reason, review=review, verify=verify,
                                   no_assurance=no_assurance)

    def plan_binding_problem(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        return self._units.plan_binding_problem(state, work_id)

    def plan_propose(self, *, token: str, expect_rev: int, work_id: str, body: str, reason: str | None = None,
                     affected_paths: list[str] | None = None, review: list[str] | None = None,
                     verify: list[str] | None = None, no_assurance: bool = False) -> dict[str, Any]:
        return self._work.plan_propose(token=token, expect_rev=expect_rev, work_id=work_id, body=body, reason=reason,
                                       affected_paths=affected_paths, review=review, verify=verify,
                                       no_assurance=no_assurance)

    def plan_reconfirm(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        return self._nm.plan_reconfirm(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def policy(self, name: str) -> dict[str, Any]:
        return self._k.policy(name)

    @property
    def project_id(self) -> Any:
        return self._k.project_id

    def render_resume(self, r: dict[str, Any]) -> str:
        return self._resume.render_resume(r)

    def render_status(self, report: dict[str, Any]) -> str:
        return self._views.render_status(report)

    def resume(self, session: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._resume.resume(session)

    def review_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._evidence.review_ingest(token=token, expect_rev=expect_rev, work_id=work_id,
                                            evidence_id=evidence_id)

    def role_list(self) -> dict[str, Any]:
        return self._roles.role_list()

    def role_show(self, card_id: str) -> dict[str, Any]:
        return self._roles.role_show(card_id)

    def role_validate(self, path: str | None = None) -> dict[str, Any]:
        return self._roles.role_validate(path)

    def run_authority_problem(self, state: dict[str, Any], inv_id: str, run: str, token_id: str) -> str | None:
        return self._harness.run_authority_problem(state, inv_id, run, token_id)

    def snapshot_of(self, path: str | Path, workspace_id: str) -> dict[str, Any]:
        return self._invocations.snapshot_of(path, workspace_id)

    def status(self, work_id: str | None = None) -> dict[str, Any]:
        out = self._resume.status(work_id)
        if work_id is None:
            state = self._k.store.read()
            view = self._steering.view(state)
            if view["configured"] or "steering" in state:  # legacy/manual projects show nothing new (decision 3)
                from aew.harness import operator_client

                out["steering"] = view | {"operator_endpoint": operator_client.status(self._k.aew_root)}
        return out

    # ---------------------------------------------------------------- steering (M4-E E2; A1 §1)

    def steering_lower(self, *, token: str, expect_rev: int, mode: str, rationale: str = "") -> dict[str, Any]:
        return self._steering.lower(token=token, expect_rev=expect_rev, mode=mode, rationale=rationale)

    def steering_request(self, *, token: str, expect_rev: int, kind: str, rationale: str, mode: str | None = None,
                         action_ref: str | None = None) -> dict[str, Any]:
        return self._steering.request(token=token, expect_rev=expect_rev, kind=kind, rationale=rationale, mode=mode,
                                      action_ref=action_ref)

    def steering_raise_preview(self, mode: str) -> dict[str, Any]:
        return self._steering.raise_preview(mode)

    def steering_raise(self, principal: OperatorPrincipal, *, mode: str, generation: int,
                       legality_digest: str) -> dict[str, Any]:
        """The operator endpoint's commit of a raise; ``principal`` only the endpoint constructs (A1 §1.1)."""
        return self._steering.raise_mode(principal, mode=mode, generation=generation, legality_digest=legality_digest)

    def steering_view(self) -> dict[str, Any]:
        return self._steering.view(self._k.store.read())

    # ---------------------------------------------------------------- the stage journal (M4-E E3)

    def policy_digests(self) -> dict[str, str]:
        """The legality and operational digests in force (A3), which a stage binds and rechecks."""
        return self._k.policy_digests()

    def stage_open(self, *, token: str, expect_rev: int, tool: str, contract_digest: str, arguments: dict[str, Any],
                   judgment_inputs: list[str], base_class: str, effective_class: str, plan: list[dict[str, Any]],
                   subject: str | None, ingress: str) -> dict[str, Any]:
        return self._stages.open(token=token, expect_rev=expect_rev, tool=tool, contract_digest=contract_digest,
                                 arguments=arguments, judgment_inputs=judgment_inputs, base_class=base_class,
                                 effective_class=effective_class, plan=plan, subject=subject, ingress=ingress)

    def stage_stop(self, *, token: str, expect_rev: int, intent: str, n: int, boundary: str, code: str, message: str,
                   reason: str | None = None) -> dict[str, Any]:
        return self._stages.stop(token=token, expect_rev=expect_rev, intent=intent, n=n, boundary=boundary,
                                 code=code, message=message, reason=reason)

    def stage_close(self, *, token: str, expect_rev: int, intent: str) -> dict[str, Any]:
        return self._stages.close(token=token, expect_rev=expect_rev, intent=intent)

    def stage_abandon(self, *, token: str, expect_rev: int, intent: str, rationale: str) -> dict[str, Any]:
        return self._stages.abandon(token=token, expect_rev=expect_rev, intent=intent, rationale=rationale)

    def stage_intents_view(self) -> list[dict[str, Any]]:
        return self._stages.view(self._k.store.read())

    def stage_intent(self, intent: str) -> dict[str, Any]:
        return self._stages.read(self._k.store.read(), intent)

    def submit(self, *, invocation_token: str, kind: str, text: str) -> dict[str, Any]:
        return self._evidence.submit(invocation_token=invocation_token, kind=kind, text=text)

    # ---------------------------------------------------------------- history (ADR-0011)

    def history_show(self, record_id: str) -> dict[str, Any]:
        return self._history.history_show(record_id)

    def history_log(self, *, since: int, kinds: list[str] | None = None, follow: bool = False, timeout: float = 30.0,
                    limit: int = 500) -> dict[str, Any]:
        """The transition log after revision ``since`` (ADR-0012 D3): each logical transition in order, its complete
        events (an overflow resolved and verified), the chain checked. The cursor is the revision: pass the returned
        ``next`` as the next ``since``. ``follow`` waits up to ``timeout`` seconds for a transition after ``since``
        (woken by ``local/wake``, re-checked every 2 s regardless). Reading takes no control lock beyond the brief
        read that finds the current revision."""
        from aew.engine import outbox

        if since < 0:
            raise UsageError("--since is a revision number, 0 or more")
        if not 1 <= limit <= 5000:
            raise UsageError("--limit must be 1 to 5000")
        unknown = sorted(set(kinds or []) - set(outbox.DERIVED_KINDS) - set(outbox.DECLARED_KINDS))
        if unknown:
            raise UsageError(f"unknown event kind(s) {unknown}: one of "
                             f"{', '.join(outbox.DERIVED_KINDS + outbox.DECLARED_KINDS)}")
        seen = self._control_identity()  # before the read: a commit in between changes it, and is then noticed
        state = self._k.store.read()
        if since > state["revision"]:
            raise UsageError(f"--since {since} is after the current revision {state['revision']}")
        if follow and since == state["revision"]:
            def committed() -> dict[str, Any] | None:
                """Lock-free until control.yaml itself changed (ADR-0012 D3: the authority file's identity, not a
                locked read per wake; D1 review F3). Every commit replaces the file, so its identity changes."""
                nonlocal seen
                now = self._control_identity()
                if now == seen:
                    return None
                seen = now
                s = self._k.store.read()
                return s if s["revision"] > since else None

            state = outbox.wait_for(committed, self._k.aew_root, timeout=timeout) or state
        through = min(state["revision"], since + limit)
        wanted = set(kinds or []) or None
        found = []
        for record in outbox.read_transitions(self._k.aew_root, since, through, outbox=state.get("outbox")):
            if record["revision"] == state["revision"] and {k: v for k, v in record.items() if k != "events"} != {
                    k: v for k, v in state["last_transition"].items() if k != "events"}:
                raise IntegrityError(f"the newest log record (revision {record['revision']}) is not the committed "
                                     "last transition", revision=record["revision"])
            narrowed = outbox.matches(record, wanted)
            if narrowed is not None:
                found.append(narrowed)
        return {"ok": True, "since": since, "through": through, "revision": state["revision"], "next": through,
                "transitions": found}

    def _control_identity(self) -> tuple[int, int, int] | None:
        """``control.yaml``'s identity (mtime, size, file id): a commit replaces the file, so it changes."""
        import os

        try:
            st = os.stat(self._k.store.control_path)
        except OSError:
            return None
        return st.st_mtime_ns, st.st_size, st.st_ino

    def history_compact(self) -> dict[str, Any]:
        """Seal the transition log's revisions older than its 4,096-revision window into 256-transition segments
        (ADR-0012 D6). Maintenance, off the commit path: it changes the log's physical representation only, never a
        logical transition, and needs no Lead credential (``aew.engine.log_compact``)."""
        from aew.engine import log_compact

        return log_compact.compact(self._k.store)

    def history_list(self, *, kind: str | None = None, since: str | None = None, until: str | None = None,
                     limit: int = 50, before: int | None = None) -> dict[str, Any]:
        return self._history.history_list(kind=kind, since=since, until=until, limit=limit, before=before)

    def history_links(self, record_id: str, *, depth: int = 1) -> dict[str, Any]:
        return self._history.history_links(record_id, depth=depth)

    def history_load(self, *, token: str, expect_rev: int, record_id: str, into: str, reason: str) -> dict[str, Any]:
        return self._history.history_load(token=token, expect_rev=expect_rev, record_id=record_id, into=into,
                                          reason=reason)

    def history_audit(self, *, full: bool = False, token: str | None = None,
                      expect_rev: int | None = None) -> dict[str, Any]:
        return self._history.history_audit(full=full, token=token, expect_rev=expect_rev)

    def history_reindex(self) -> dict[str, Any]:
        return self._history.history_reindex()

    def history_search(self, terms: list[str], *, kinds: list[str] | None = None, since: str | None = None,
                       until: str | None = None, limit: int = 10) -> dict[str, Any]:
        """Register F21's Arm B prototype: explicit raw-history search, only while switched on
        (``aew.engine.recall``)."""
        return self._history.history_search(terms, kinds=kinds, since=since, until=until, limit=limit)

    def migrate(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        return self._migration.migrate(token=token, expect_rev=expect_rev)

    # ---------------------------------------------------------------- read collaborators (the dashboard, F20.2)
    # The dashboard projects committed state through the same collaborators every command reads with; it never
    # mutates, and it reads the state itself lock-free (``ControlStore.read_committed``).

    @property
    def archive(self) -> Archive:
        return self._archive

    @property
    def units(self) -> WorkUnits:
        return self._units

    def audit_status(self, state: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._history.audit_status(state, policy=policy)

    def contradictions(self, state: dict[str, Any], manifest: dict[str, Any] | None = None) -> list[str]:
        return self._views.contradictions(state, manifest)

    def next_actions(self, state: dict[str, Any]) -> list[str]:
        return self._resume.next_actions(state)

    def archived_credential(self, state: dict[str, Any], token_id: str) -> dict[str, Any] | None:
        """A credential archived with finished work (ADR-0011 R7), for checks outside the engine (the Lead broker, a
        run's supervisor): presenting it again is stale authority, never an unknown credential."""
        return self._archive.archived_credential(state, token_id)

    def verify_classify(self, *, token: str, expect_rev: int, work_id: str, classification: str,
                        reason: str) -> dict[str, Any]:
        return self._evidence.verify_classify(token=token, expect_rev=expect_rev, work_id=work_id,
                                              classification=classification, reason=reason)

    def verify_ingest(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str) -> dict[str, Any]:
        return self._evidence.verify_ingest(token=token, expect_rev=expect_rev, work_id=work_id,
                                            evidence_id=evidence_id)

    def waive(self, *, token: str, expect_rev: int, work_id: str, reason: str, gate: str | None = None,
              finding: str | None = None) -> dict[str, Any]:
        return self._evidence.waive(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason, gate=gate,
                                    finding=finding)

    def work_accept(self, *, token: str, expect_rev: int, work_id: str, reason: str | None = None) -> dict[str, Any]:
        return self._nm.work_accept(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def work_acknowledge_input(self, *, token: str, expect_rev: int, work_id: str, evidence_id: str, source: str,
                               reason: str) -> dict[str, Any]:
        return self._nm.work_acknowledge_input(token=token, expect_rev=expect_rev, work_id=work_id,
                                               evidence_id=evidence_id, source=source, reason=reason)

    def work_assign(self, *, token: str, expect_rev: int, work_id: str, execution_profile: dict[str, Any] | None = None,
                    launch: bool = False) -> dict[str, Any]:
        return self._assignment.work_assign(token=token, expect_rev=expect_rev, work_id=work_id,
                                            execution_profile=execution_profile, launch=launch)

    def work_cancel(self, *, token: str, expect_rev: int, work_id: str, reason: str) -> dict[str, Any]:
        return self._hierarchy.work_cancel(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def work_close(self, *, token: str, expect_rev: int, work_id: str, reason: str | None = None) -> dict[str, Any]:
        return self._hierarchy.work_close(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason)

    def work_create(self, *, token: str, expect_rev: int, kind: str, title: str, risk_class: int,
                    mutating: bool | None = None, parent: str | None = None, depends_on: list[str] | None = None,
                    scope_paths: list[str] | None = None, goal_backwards: list[str] | None = None,
                    contract: list[str] | None = None, mandatory_gates: list[str] | None = None,
                    min_descendant_class: int | None = None, rationale: str | None = None,
                    external_refs: list[str] | None = None, body: str = "", card: str | None = None,
                    promoted_from: str | None = None, acceptance_checks: list[str] | None = None,
                    acceptance_inputs: list[str] | None = None,
                    class0_assertions: list[str] | None = None) -> dict[str, Any]:
        return self._work.work_create(token=token, expect_rev=expect_rev, kind=kind, title=title, risk_class=risk_class,
                                      mutating=mutating, parent=parent, depends_on=depends_on, scope_paths=scope_paths,
                                      goal_backwards=goal_backwards, contract=contract, mandatory_gates=mandatory_gates,
                                      min_descendant_class=min_descendant_class, rationale=rationale,
                                      external_refs=external_refs, body=body, card=card, promoted_from=promoted_from,
                                      acceptance_checks=acceptance_checks, acceptance_inputs=acceptance_inputs,
                                      class0_assertions=class0_assertions)

    def work_depend(self, *, token: str, expect_rev: int, work_id: str, add: list[str] | None = None,
                    remove: list[str] | None = None, reason: str) -> dict[str, Any]:
        return self._hierarchy.work_depend(token=token, expect_rev=expect_rev, work_id=work_id, add=add, remove=remove,
                                           reason=reason)

    def work_dispatch(self, *, token: str, expect_rev: int, work_id: str, card: str | None = None,
                      execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        return self._nm.work_dispatch(token=token, expect_rev=expect_rev, work_id=work_id, card=card,
                                      execution_profile=execution_profile, launch=launch)

    def work_list(self, *, state_filter: str | None = None) -> dict[str, Any]:
        return self._work.work_list(state_filter=state_filter)

    def work_move(self, *, token: str, expect_rev: int, work_id: str, parent: str | None, reason: str) -> dict[str,
                  Any]:
        return self._hierarchy.work_move(token=token, expect_rev=expect_rev, work_id=work_id, parent=parent,
                                         reason=reason)

    def work_promote(self, *, token: str, expect_rev: int, work_id: str, to: str, title: str, reason: str,
                     risk_class: int | None = None) -> dict[str, Any]:
        return self._hierarchy.work_promote(token=token, expect_rev=expect_rev, work_id=work_id, to=to, title=title,
                                            reason=reason, risk_class=risk_class)

    def work_reclassify(self, *, token: str, expect_rev: int, work_id: str, risk_class: int,
                        reason: str) -> dict[str, Any]:
        return self._work.work_reclassify(token=token, expect_rev=expect_rev, work_id=work_id, risk_class=risk_class,
                                          reason=reason)

    def work_reconcile(self, *, token: str, expect_rev: int, work_id: str, to: str, reason: str,
                       inspection: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._nm.work_reconcile(token=token, expect_rev=expect_rev, work_id=work_id, to=to, reason=reason,
                                       inspection=inspection)

    def work_redispatch(self, *, token: str, expect_rev: int, work_id: str, reason: str, card: str | None = None,
                        execution_profile: dict[str, Any] | None = None, launch: bool = False) -> dict[str, Any]:
        return self._nm.work_redispatch(token=token, expect_rev=expect_rev, work_id=work_id, reason=reason, card=card,
                                        execution_profile=execution_profile, launch=launch)

    def work_roles(self, work_id: str) -> dict[str, Any]:
        return self._gates.work_roles(work_id)

    def work_show(self, work_id: str) -> dict[str, Any]:
        return self._work.work_show(work_id)

    def work_staff(self, *, token: str, expect_rev: int, work_id: str, execute: list[str] | None = None,
                   review: list[str] | None = None, verify: list[str] | None = None, forbid: list[str] | None = None,
                   remove: list[str] | None = None, selected_by: str = "lead", pin: bool = False,
                   reason: str | None = None, authorization: dict[str, str] | None = None) -> dict[str, Any]:
        return self._roles.work_staff(token=token, expect_rev=expect_rev, work_id=work_id, execute=execute,
                                      review=review, verify=verify, forbid=forbid, remove=remove,
                                      selected_by=selected_by, pin=pin, reason=reason, authorization=authorization)

    def work_transition(self, *, token: str, expect_rev: int, work_id: str, to: str,
                        reason: str | None = None) -> dict[str, Any]:
        return self._work.work_transition(token=token, expect_rev=expect_rev, work_id=work_id, to=to, reason=reason)

    def work_tree(self, root: str | None = None) -> dict[str, Any]:
        return self._hierarchy.work_tree(root)

    def _require_gates(self, gc: dict[str, Any], names: list[str], *, what: str) -> None:
        return self._gates.require_gates(gc, names, what=what)
