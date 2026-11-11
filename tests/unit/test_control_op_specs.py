"""The revision contract is keyed by control operation, independent of stage primitives."""

from __future__ import annotations

import ast
import hashlib
import json
from contextlib import nullcontext
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from types import SimpleNamespace

import pytest

from aew.engine import primitives as P

ENGINE = Path(P.__file__).resolve().parent
DIRECT_COMMIT_MODULES = {"lead_ops.py", "migrate_ops.py"}
FORWARDERS = {("api.py", "lead_txn"), ("validation_ops.py", "txn")}


def _strings(node, bindings, seen=frozenset()):
    """Resolve literal names and both arms of a conditional, or mark the expression unreadable."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _strings(node.body, bindings, seen) | _strings(node.orelse, bindings, seen)
    if isinstance(node, ast.Name) and node.id in bindings and node.id not in seen:
        return _strings(bindings[node.id], bindings, seen | {node.id})
    return {None}


class EntryScan(ast.NodeVisitor):
    def __init__(self, file):
        self.file = file
        self.function = None
        self.bindings = {}
        self.entries = set()
        self.unreadable = set()
        self.forwarders = set()

    def visit_FunctionDef(self, node):
        previous = self.function, self.bindings
        self.function, self.bindings = node.name, self.bindings.copy()
        self.generic_visit(node)
        self.function, self.bindings = previous

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.bindings[target.id] = node.value
        self.generic_visit(node)

    def _record(self, expression, line):
        values = _strings(expression, self.bindings)
        if None in values:
            self.unreadable.add((self.file, line, ast.unparse(expression) if expression else "<missing>"))
        self.entries.update(values - {None})

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
            validation_entry = (self.file == "validation_ops.py" and name == "txn"
                                and isinstance(node.func.value, ast.Name) and node.func.value.id == "who")
            if name == "lead_txn" or validation_entry:
                location = self.file, self.function
                expr = node.args[2] if len(node.args) > 2 else next(
                    (kw.value for kw in node.keywords if kw.arg == "op"), None)
                if location in FORWARDERS and isinstance(expr, ast.Name) and expr.id == "op":
                    self.forwarders.add(location)
                else:
                    self._record(expr, node.lineno)
            if name == "commit" and self.file in DIRECT_COMMIT_MODULES and node.args:
                transition = node.args[0]
                if (isinstance(transition, ast.Call) and isinstance(transition.func, ast.Name)
                        and transition.func.id == "Transition"):
                    self._record(next((kw.value for kw in transition.keywords if kw.arg == "op"), None), node.lineno)
        self.generic_visit(node)


def _static_entries():
    entries = set()
    forwarders = set()
    unreadable = set()
    for path in ENGINE.glob("*.py"):
        scan = EntryScan(path.name)
        scan.visit(ast.parse(path.read_text(encoding="utf-8"), filename=path.name))
        entries.update(scan.entries)
        forwarders.update(scan.forwarders)
        unreadable.update(scan.unreadable)
    assert not unreadable
    assert forwarders == FORWARDERS
    # The coordination writer records under its own revision compare and has no Transition.
    entries.add("message.record_lead")
    return entries


def test_control_op_specs_match_static_entry_sites():
    entries = _static_entries()
    assert entries == P.CONTROL_OP_SPECS.keys()
    assert len(entries) == 65


def test_static_scan_reports_undeclared_and_unreadable_entries():
    scan = EntryScan("planted.py")
    scan.visit(ast.parse(
        'OP = "checkpoint"\n'
        'def planted(k, choice):\n'
        '    name = OP if choice else "unknown.write"\n'
        '    k.lead_txn(token, rev, name)\n'
        '    k.lead_txn(token, rev, compute_op())\n'
    ))
    assert scan.entries & P.CONTROL_OP_SPECS.keys() == {"checkpoint"}
    assert scan.entries - P.CONTROL_OP_SPECS.keys() == {"unknown.write"}
    assert scan.unreadable == {("planted.py", 5, "compute_op()")}


def test_control_op_specs_leave_primitive_lookups_at_the_base():
    # 8a3810b6. Include the keys and every PrimitiveSpec field in the snapshot.
    declared = {name: P.spec_for(name) for name in P.SPECS}
    digest = hashlib.sha256(json.dumps(declared, sort_keys=True).encode()).hexdigest()
    assert digest == "711b072ff6661795e9b556916ed3676bbd8fab3213c879072f54c0831b8f08f1"
    assert declared == P.SPECS
    for name in (P.CONTROL_OP_SPECS.keys() - declared.keys()) | {"unknown.write"}:
        assert P.spec_for(name) == P.PrimitiveSpec(
            name, P.JUDGMENT_BEARING, ("undeclared",), (), (), "unknown", "unknown", None, False,
        )


# Exercise the operation handlers independently of the source scan. The recorder
# stops at the transaction boundary, before any handler can mutate state.
TRANSACTION_HANDLERS = {
    ("api", "ProjectAdmin"): "authority_accept authority_reject manifest_adopt",
    ("disposition_ops", "Dispositions"): "dispose",
    ("evidence_ops", "EvidenceCommands"): (
        "_invoke_ticket invoke_cancel _ingest_ticket_review _ingest_ticket_verification "
        "_classify_ticket_verification waive"
    ),
    ("gate_ops", "GateRepair"): "gate_replace",
    ("harness_ops", "Harness"): "harness_launch",
    ("hierarchy_ops", "Hierarchy"): (
        "invoke_evidence_unit ingest_evidence_unit_report classify_parent_verification "
        "work_close work_cancel work_move work_promote work_depend"
    ),
    ("history_ops", "HistoryCommands"): "history_load history_audit",
    ("integration_ops", "Integration"): (
        "integrate_prepare integrate_defer integrate_requeue integrate_reorder "
        "integrate_publish _finish_publish integrate_reconcile"
    ),
    ("lead_ops", "Lead"): "lead_handoff_offer lead_handoff_cancel lead_release",
    ("migrate_ops", "Migration"): "_upgrade_v2",
    ("nonmutating_ops", "NonMutating"): (
        "work_acknowledge_input work_dispatch work_redispatch evidence_ingest work_accept "
        "invoke_evidence_unit ingest_evidence_unit_report plan_adopt plan_reconfirm"
    ),
    ("resume_ops", "Resume"): "checkpoint",
    ("role_ops", "Roles"): "work_staff",
    ("stage_intents", "StageIntents"): "open stop close abandon continue_",
    ("steering", "Steering"): "lower request",
    ("validation_ops", "Validation"): "_pin _commit_txn _abandon _end_infra _release_unavailable breaker_reset",
    ("workspace_ops", "Assignment"): "work_assign",
    ("work_ops", "WorkCommands"): "work_create work_reclassify plan_propose plan_accept work_transition work_reconcile",
}

HANDLER_CASES = {
    "authority_accept": [{"klass": "contracts"}],
    "manifest_adopt": [{"authorization": {"authorized_by": "operator-tty"}}],
    "dispose": [{"choice": "accept_risk", "follow_up": None}],
    "waive": [{"gate": "gate"}],
    "work_depend": [{"add": ["T-0002"]}],
    "work_create": [{"kind": "epic", "risk_class": 1}],
    "work_reclassify": [{"risk_class": 2}],
    "history_audit": [{"token": "synthetic", "expect_rev": 1}],
    "_upgrade_v2": [{"expect_rev": 1}],
    "open": [{"ingress": "test", "plan": [{}], "base_class": P.MECHANICAL, "effective_class": P.MECHANICAL}],
    "lower": [{"mode": "crawl"}],
    "request": [{"kind": "raise"}],
    "_ingest_ticket_verification": [{"scope": "ticket"}, {"scope": "integration"}],
    "ingest_evidence_unit_report": [{"kind": "review"}, {"kind": "verify"}],
}


class ReachedTransaction(BaseException):
    pass


def _call_handler(handler, supplied):
    args = []
    kwargs = {}
    for name, param in signature(handler).parameters.items():
        if name not in supplied and param.default is not Parameter.empty:
            continue
        value = supplied.get(name, "synthetic")
        if param.kind == Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[name] = value
    handler(*args, **kwargs)


def test_control_op_specs_match_runtime_transaction_entries(monkeypatch, tmp_path):
    from aew.engine import api, history_ops, migrate_ops, validation_ops
    from aew.engine.base import V2

    seen = set()

    def record(token, revision, op, **kwargs):
        seen.add(op)
        raise ReachedTransaction

    state = {
        "schema": V2, "revision": 1,
        "cold": {"root": {"count": 0, "head_h": "root"}},
        "work": {"synthetic": {"queue_entry": "Q-1"}},
        "queue": {"entries": {"Q-1": {"work": "synthetic"}}, "lease": {"entry": "Q-1", "reconcile": True}},
    }
    session = SimpleNamespace(state=state, revision=1)
    store = SimpleNamespace(current=lambda: state, session=lambda: nullcontext(session))
    k = SimpleNamespace(lead_txn=record, store=store, aew_root=tmp_path, archived_credential=None)
    monkeypatch.setattr(history_ops, "require_lead", lambda *a, **kw: None)
    monkeypatch.setattr(migrate_ops, "require_lead", lambda *a, **kw: None)
    for (module, owner), methods in TRANSACTION_HANDLERS.items():
        cls = getattr(import_module(f"aew.engine.{module}"), owner)
        obj = cls.__new__(cls)
        obj.k = k
        if cls is history_ops.HistoryCommands:
            obj.cold = SimpleNamespace(tail_bytes=lambda: b"", verify=lambda *a, **kw: SimpleNamespace(
                entries=0, records=0, problems=[], damaged=[]))
        if cls is migrate_ops.Migration:
            obj.archive = SimpleNamespace(legacy_units=lambda state: ["old"])
        for method in methods.split():
            for case in HANDLER_CASES.get(method, [{}]):
                values = {"who": validation_ops.Principal(validation_ops.LEAD, "synthetic"), **case}
                with pytest.raises(ReachedTransaction):
                    _call_handler(getattr(obj, method), values)

    _record_non_transaction_entries(k, seen, monkeypatch)
    assert seen == _static_entries()
    facade = api.Engine.__new__(api.Engine)
    facade._k = k
    with pytest.raises(ReachedTransaction):
        facade.lead_txn("synthetic", 1, "unknown.write")
    assert seen - P.CONTROL_OP_SPECS.keys() == {"unknown.write"}


def _record_non_transaction_entries(k, seen, monkeypatch):
    from aew.engine import coordination_ops, lead_ops, migrate_ops
    from aew.engine.base import V1

    def commit(transition, **kwargs):
        seen.add(transition.op)
        raise ReachedTransaction

    def record_message(*args, **kwargs):
        seen.add("message.record_lead")
        raise ReachedTransaction

    def nothing(*args, **kwargs):
        return None

    state = {
        "schema": V1, "revision": 1, "invocations": {}, "work": {}, "tokens": {},
        "lead": {"status": "vacant", "generation": 1, "session_label": None,
                 "handoff": {"carry_invocations": [], "record": "handoff"}},
    }
    session = SimpleNamespace(state=state, revision=1, commit=commit)
    k.store = SimpleNamespace(current=lambda: state, session=lambda: nullcontext(session))
    k.check_manifest_pin = nothing
    k.new_decision = lambda *a, **kw: "decision"
    k.project_id = "synthetic"
    k.finalizers = SimpleNamespace(run=nothing)

    archive = SimpleNamespace(end_lead_credentials=nothing, archived_credential=nothing)
    queue = SimpleNamespace(sync=nothing)
    coordination = SimpleNamespace(seal_ending=nothing, register_on_migrate=nothing)
    lead = lead_ops.Lead(k, archive=archive, queue=queue, coordination=coordination)
    monkeypatch.setattr(lead, "_new_lead", lambda *args: "synthetic")
    monkeypatch.setattr(lead_ops, "verify_offer", lambda *args: "offer")
    monkeypatch.setattr(lead_ops.operator, "authorize", lambda *args: {"authorized_by": "operator-tty"})
    with pytest.raises(ReachedTransaction):
        lead.lead_acquire(expect_rev=1)
    state["lead"]["status"] = "active"
    with pytest.raises(ReachedTransaction):
        lead.lead_handoff_accept(offer="synthetic", expect_rev=1)
    with pytest.raises(ReachedTransaction):
        lead.lead_takeover(expect_rev=1, reason="synthetic")

    migration = migrate_ops.Migration(k, hierarchy=None, archive=archive, coordination=coordination)
    monkeypatch.setattr(migration, "discard_unreachable", lambda: [])
    with pytest.raises(ReachedTransaction):
        migration.migrate(token="synthetic", expect_rev=1)

    writer = coordination_ops.Coordination(k, archive=archive)
    monkeypatch.setattr(coordination_ops, "require_lead", lambda *a, **kw: {"generation": 1})
    monkeypatch.setattr(writer, "_require_recordable", nothing)
    monkeypatch.setattr(writer, "_invocation", lambda *a: {"work_unit": "T-0001"})
    monkeypatch.setattr(coordination_ops, "read_thread",
                        lambda *a: SimpleNamespace(messages=[], facts=[], by_id=dict, invocation="INV-0001"))
    monkeypatch.setattr(writer, "_require_recipient", nothing)
    monkeypatch.setattr(writer, "_require_room", nothing)
    monkeypatch.setattr(writer, "_check_refs", nothing)
    monkeypatch.setattr(writer, "_record", nothing)
    monkeypatch.setattr(writer, "_write", record_message)
    with pytest.raises(ReachedTransaction):
        writer.message_record_lead(token="synthetic", expect_rev=1, to="INV-0001", body="synthetic")


def test_journal_labels_follow_the_spec_of_the_entered_operation():
    expected = {
        "integration_ops.py": {
            "_moved_head": {"integrate.stale", "integrate.rebuild"},
            "integrate_publish": {"integrate.superseded"},
            "_finish_publish": {"integrate.withdrawn", "integrate.stale"},
        },
        "evidence_ops.py": {"_ingest_ticket_verification": {"verify.ingest"}},
    }
    covers = {
        "integrate.stale": {"integrate.publishing", "integrate.publish"},
        "integrate.rebuild": {"integrate.publishing", "integrate.publish"},
        "integrate.superseded": {"integrate.publishing"},
        "integrate.withdrawn": {"integrate.publish"},
        "verify.ingest": {"verify.ingest.integration"},
    }
    actual = {}
    actual_covers = {}
    for path in ENGINE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        for fn in functions:
            labels = {ast.literal_eval(node.value) for node in ast.walk(fn)
                      if isinstance(node, ast.Assign)
                      and any(ast.unparse(target) == "ctx.op" for target in node.targets)}
            if labels:
                actual.setdefault(path.name, {})[fn.name] = labels
                callers = [fn] if fn.name != "_moved_head" else [
                    other for other in functions
                    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                           and node.func.attr == fn.name for node in ast.walk(other))
                ]
                for caller in callers:
                    scan = EntryScan(path.name)
                    scan.visit(caller)
                    assert not scan.unreadable
                    for label in labels:
                        actual_covers.setdefault(label, set()).update(scan.entries - {label})
    assert actual == expected
    assert actual_covers == covers
    for entries in covers.values():
        assert entries <= P.CONTROL_OP_SPECS.keys()
