"""Edits to existing files for the ADR-0013 D9 service-identity spike (branch review/t4-d9-service-identity).
Run from the review directory: .venv/Scripts/python repro/apply_d9_edits.py"""

from __future__ import annotations

import pathlib
import sys

TREE = pathlib.Path(__file__).resolve().parents[1] / "tree"


def patch(rel: str, pairs: list[tuple[str, str]], *, count: int = 1) -> None:
    p = TREE / rel
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        n = s.count(old)
        assert n == count, (rel, old[:70], n)
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8", newline="\n")
    print("patched", rel)


# 1. the credential kind
patch("src/aew/schemas/control.schema.json", [(
    '              "lead",\n              "invocation",\n              "handoff_offer"\n',
    '              "lead",\n              "invocation",\n              "handoff_offer",\n              "service"\n')])

# 2. the error
patch("src/aew/errors.py", [(
    '    code = "OPERATOR_AUTHORIZATION_REQUIRED"\n',
    '    code = "OPERATOR_AUTHORIZATION_REQUIRED"\n\n\n'
    'class ClosureViolation(PermissionDenied):\n'
    '    """A service principal\'s transition would change control state outside its closed family (ADR-0013 D9)."""\n\n'
    '    code = "TRANSACTION_CLOSURE"\n')])

# 3. authority: the service kind
patch("src/aew/engine/authority.py", [
    ("from aew.errors import PermissionDenied, StaleAuthority\n",
     "from aew.errors import IntegrityError, PermissionDenied, StaleAuthority\n"),
    ('    "researcher": frozenset({"submit.research_record", "context.read"}),\n}\n',
     '    "researcher": frozenset({"submit.research_record", "context.read"}),\n}\n\n'
     '# Service principals (ADR-0013 D9 spike): a project-scoped identity bound to one closed transaction family, with\n'
     '# its own credential kind. Not a role (no invocation, no work unit, no operation table) and not the Lead (no\n'
     '# generation): it survives handoff and takeover, and the Lead may rotate or revoke it at any time. The family is\n'
     '# enforced twice: by ``Kernel.service_txn`` and, independently, by the control store at commit (``closure``).\n'
     'SERVICE_FAMILIES: dict[str, str] = {"knowledge_service": "knowledge"}\n'),
])
with (TREE / "src/aew/engine/authority.py").open("a", encoding="utf-8", newline="\n") as f:
    f.write('''

# ---------------------------------------------------------------------------- service principals (ADR-0013 D9)


def service_token_id(state: dict[str, Any], service: str) -> str | None:
    """The service's current (unrevoked) credential id; at most one exists (oracle rule 30)."""
    live = [t for t, r in state["tokens"].items()
            if r["kind"] == "service" and r["scope"].get("service") == service and r["revoked_at"] is None]
    if len(live) > 1:
        raise IntegrityError(f"{service} holds {len(live)} live credentials; a service holds at most one", live=live)
    return live[0] if live else None


def issue_service_token(state: dict[str, Any], service: str, issued_by: dict[str, Any]) -> str:
    """Issue the service's credential, revoking the previous one in the same state change (rotation is re-issuance,
    as for invocations). The scope names the service and its family and records who issued it; it carries no
    generation, because the credential grants no Lead authority that a new generation could supersede."""
    family = SERVICE_FAMILIES.get(service)
    if family is None:
        raise PermissionDenied(f"unknown service principal {service!r}", service=service)
    previous = service_token_id(state, service)
    if previous:
        revoke(state, previous, "rotated by the Lead")
    scope = {"service": service, "family": family,
             "issued_by": {k: issued_by.get(k) for k in ("kind", "session_label", "generation")}}
    return issue_token(state, "service", scope)


def require_service(state: dict[str, Any], token: str, family: str, *,
                    archived: ArchivedCredential | None = None) -> dict[str, Any]:
    """Return the actor record for a valid service credential bound to ``family``. No generation check: a service
    holds no Lead authority, so a Lead handoff or takeover supersedes nothing of its; only revocation ends it."""
    token_id, record = _lookup(state, token, archived)
    if record["kind"] != "service":
        raise PermissionDenied("this operation requires a service credential", presented=record["kind"])
    scope = record["scope"]
    if record["revoked_at"] is not None:
        raise StaleAuthority(f"the {scope.get('service')} credential was revoked: {record.get('revoke_reason')}",
                             token_id=token_id, revoke_reason=record.get("revoke_reason"))
    if scope.get("family") != family:
        raise PermissionDenied(f"{scope.get('service')} may commit only {scope.get('family')}.* transitions",
                               service=scope.get("service"), family=scope.get("family"), requested=family)
    return {"kind": "service", "service": scope["service"], "family": family, "token_id": token_id}


def credential_kind(state: dict[str, Any], token: str, *, archived: ArchivedCredential | None = None) -> str:
    """The kind of a valid credential (lead, invocation, handoff_offer, service), to route a command to the right
    transaction. Authority itself is checked by the ``require_*`` function the route leads to."""
    return _lookup(state, token, archived)[1]["kind"]
''')
print("appended src/aew/engine/authority.py")

# 4. the store enforces the closure at commit
patch("src/aew/engine/store.py", [
    ("from aew.engine import faults\n", "from aew.engine import faults\nfrom aew.engine.closure import closure_for, enforce\n"),
    ("        # Validate before anything touches disk so a rejected transition leaves no trace.\n",
     "        # A service principal's transition is closed: the store compares what it would write with what is committed\n"
     "        # and refuses anything outside the family, whatever layer asked (ADR-0013 D9).\n"
     "        closure = closure_for(transition.actor)\n"
     "        if closure is not None:\n"
     "            enforce(closure, before, after, transition.op, [w.path for w in writes] + sorted(prewritten))\n"
     "        # Validate before anything touches disk so a rejected transition leaves no trace.\n"),
])

# 5. the kernel: service_txn and routing
base = TREE / "src/aew/engine/base.py"
s = base.read_text(encoding="utf-8")
s = s.replace("from aew.engine.authority import require_lead\n",
              "from aew.engine.authority import credential_kind, require_lead, require_service\n", 1)
if "PermissionDenied" not in s.split("from aew.knowledge import render", 1)[0]:
    s = s.replace("from aew.errors import (\n", "from aew.errors import (\n    PermissionDenied,\n", 1)
s = s.replace(
    "    dispatch_decisions: list[Any] = field(default_factory=list)\n\n    @property\n    def state(self)",
    "    dispatch_decisions: list[Any] = field(default_factory=list)\n"
    "    # False for a service principal's transition (ADR-0013 D9): the archival finalizer appends the operation's own\n"
    "    # entries and archives nothing, so the commit changes only what the family owns.\n"
    "    archival: bool = True\n\n    @property\n    def state(self)", 1)
service_txn = '''
    @contextmanager
    def service_txn(self, token: str, expect_rev: int | None, op: str, *, family: str,
                    reason: str | None = None) -> Iterator[TxnContext]:
        """A closed-family transition by a service principal (ADR-0013 D9): a service credential bound to ``family``,
        the expected revision, an op inside the family, no archival. The store checks the closure again at commit."""
        if not op.startswith(family + "."):
            raise PermissionDenied(f"{op} is outside the {family}.* family", family=family, op=op)
        with self.store.session() as s:
            actor = require_service(s.state, token, family, archived=self.archived_credential)
            if expect_rev is None:
                raise StaleRevision("control mutations must state the expected revision (--expect-rev)",
                                    current=s.revision)
            if expect_rev != s.revision:
                raise StaleRevision(f"expected control revision {expect_rev}, current is {s.revision}",
                                    expected=expect_rev, current=s.revision)
            if s.state.get("schema") != V2:
                raise MigrationRequired("this project's control state is v1: a service may not write it; the Lead "
                                        "migrates it first (`aew migrate --expect-rev N`)",
                                        schema=s.state.get("schema"), next_action="aew migrate --expect-rev N")
            self.check_manifest_pin(s.state)
            ctx = TxnContext(session=s, actor=actor, archival=False)
            yield ctx
            self.finalizers.run(ctx)
            s.commit(Transition(op=ctx.op or op, actor=actor, summary=ctx.summary, reason=reason, refs=ctx.refs),
                     expect_rev=expect_rev, state=ctx.commit_state)
            for effect in ctx.after_commit:
                try:
                    effect()
                except (AEWError, OSError):
                    pass

    def actor_txn(self, token: str, expect_rev: int | None, op: str, *, family: str,
                  reason: str | None = None) -> AbstractContextManager[TxnContext]:
        """Route a transition by the credential's kind: a service credential commits through ``service_txn`` (and
        is bound to ``family``), anything else through ``lead_txn`` (which refuses every kind but the Lead's)."""
        if credential_kind(self.store.read(), token, archived=self.archived_credential) == "service":
            return self.service_txn(token, expect_rev, op, family=family, reason=reason)
        return self.lead_txn(token, expect_rev, op, reason=reason)

    def new_decision(
        self,
        ctx: TxnContext,'''
assert s.count("\n    def new_decision(\n        self,\n        ctx: TxnContext,") == 1
s = s.replace("\n    def new_decision(\n        self,\n        ctx: TxnContext,", service_txn, 1)
if "AbstractContextManager" not in s:
    s = s.replace("from contextlib import contextmanager\n", "from contextlib import AbstractContextManager, contextmanager\n", 1)
base.write_text(s, encoding="utf-8", newline="\n")
print("patched src/aew/engine/base.py")

# 6. the archival finalizer archives nothing for a service transition
patch("src/aew/engine/archive_ops.py", [(
    '        work = state["work"]\n'
    '        order = sorted((w for w, u in work.items() if u["state"] in H.TERMINAL),\n'
    '                       key=lambda w: (-H.depth(state, w), w))\n'
    '        retained = self._retained(state, order)\n'
    '        archived = set(order)\n'
    '        lead_ended = self._ended_lead_credentials(state)\n'
    '        retired = self._retired_observations(state, order)\n'
    '        # Removing a retired observation is an obligation that outlives its invocation: it stays listed until the\n'
    '        # directory is gone, and every commit retries it, so a crash or a failed removal never loses it.\n'
    '        ctx.after_commit.extend(lambda p=o["path"]: self._prune_observation(p) for o in retired)\n',
    '        work = state["work"]\n'
    '        if not ctx.archival:\n'
    '            # A closed-family (service) transition archives nothing and ends no credential: it appends its own\n'
    '            # entries only, and finished units wait for the next Lead commit (ADR-0013 D9).\n'
    '            order, lead_ended = [], []\n'
    '            retained = list(state.get("retained_workspaces", []))\n'
    '            retired = list(state.get("retired_observations", []))\n'
    '        else:\n'
    '            order = sorted((w for w, u in work.items() if u["state"] in H.TERMINAL),\n'
    '                           key=lambda w: (-H.depth(state, w), w))\n'
    '            retained = self._retained(state, order)\n'
    '            lead_ended = self._ended_lead_credentials(state)\n'
    '            retired = self._retired_observations(state, order)\n'
    '            # Removing a retired observation is an obligation that outlives its invocation: it stays listed until\n'
    '            # the directory is gone, and every commit retries it, so a crash or a failed removal never loses it.\n'
    '            ctx.after_commit.extend(lambda p=o["path"]: self._prune_observation(p) for o in retired)\n'
    '        archived = set(order)\n')])

# 7. knowledge ops route by credential kind
patch("src/aew/engine/knowledge_ops.py", [
    ('        with self.k.lead_txn(token, expect_rev, "knowledge.capture") as ctx:\n',
     '        with self.k.actor_txn(token, expect_rev, "knowledge.capture", family="knowledge") as ctx:\n'),
    ('        with self.k.lead_txn(token, expect_rev, "knowledge.dispose") as ctx:\n',
     '        with self.k.actor_txn(token, expect_rev, "knowledge.dispose", family="knowledge") as ctx:\n'),
    ("Prototype scope: the Lead commits (``lead_txn``); the service identity the draft's D9 proposes is not modelled, so\n"
     "the closed-transaction property (oracle rule 28) is asserted by tests on what a ``knowledge.*`` commit changes.\n",
     "Committers: the Lead (``lead_txn``) or the ``knowledge_service`` principal (``service_txn``, ADR-0013 D9 spike), chosen\n"
     "by the credential's kind. The service's commits are closed to the ``knowledge.*`` family by the control store itself;\n"
     "the closed-transaction property (oracle rule 28) is asserted by tests on what a ``knowledge.*`` commit changes.\n"),
])
patch("src/aew/engine/knowledge_ops.py", [(
    '"revision": ctx.session.committed_revision}', '"actor": ctx.actor["kind"], "revision": ctx.session.committed_revision}')],
    count=2)

# 8. the CLI accepts a service credential for knowledge commands
patch("src/aew/cli/knowledge_commands.py", [
    ("import argparse\nfrom typing import Any\n\nfrom aew.cli.commands import _add_json, _add_lead, _engine, _lead_token, _read_text_arg\n",
     "import argparse\nimport os\nfrom typing import Any\n\nfrom aew.cli.commands import _add_json, _add_lead, _engine, _read_text_arg\n"),
    ("def _record(args: argparse.Namespace) -> dict[str, Any]:\n",
     "def _actor_token(args: argparse.Namespace) -> str:\n"
     '    """The Lead\'s credential or the knowledge service\'s (ADR-0013 D9): --token, AEW_SERVICE_TOKEN or AEW_LEAD_TOKEN."""\n'
     '    token = getattr(args, "token", None) or os.environ.get("AEW_SERVICE_TOKEN") or os.environ.get("AEW_LEAD_TOKEN")\n'
     "    if not token:\n"
     '        raise UsageError("a credential is required: pass --token, or set AEW_SERVICE_TOKEN or AEW_LEAD_TOKEN")\n'
     "    return token\n\n\n"
     "def _record(args: argparse.Namespace) -> dict[str, Any]:\n"),
])
patch("src/aew/cli/knowledge_commands.py", [("_lead_token(a)", "_actor_token(a)")], count=2)

# 9. registration
patch("src/aew/cli/commands.py", [
    ("    from aew.cli import history_commands, knowledge_commands, work_commands\n",
     "    from aew.cli import history_commands, knowledge_commands, service_commands, work_commands\n"),
    ("    knowledge_commands.register(sub)\n", "    knowledge_commands.register(sub)\n    service_commands.register(sub)\n"),
])

# 10. the engine facade
patch("src/aew/engine/api.py", [
    ("from aew.engine.lead_ops import Lead\n", "from aew.engine.lead_ops import Lead\nfrom aew.engine.service_ops import Services\n"),
    ("        self._knowledge = Knowledge(k, archive=archive)\n",
     "        self._knowledge = Knowledge(k, archive=archive)\n        self._services = Services(k)\n"),
    ("    def knowledge_case(self, **kw: Any) -> dict[str, Any]:\n",
     "    def service_issue(self, **kw: Any) -> dict[str, Any]:\n        return self._services.service_issue(**kw)\n\n"
     "    def service_revoke(self, **kw: Any) -> dict[str, Any]:\n        return self._services.service_revoke(**kw)\n\n"
     "    def service_show(self) -> dict[str, Any]:\n        return self._services.service_show()\n\n"
     "    def service_txn(self, token: str, expect_rev: int | None, op: str, *, family: str,\n"
     "                    reason: str | None = None) -> AbstractContextManager[TxnContext]:\n"
     "        return self._k.service_txn(token, expect_rev, op, family=family, reason=reason)\n\n"
     "    def actor_txn(self, token: str, expect_rev: int | None, op: str, *, family: str,\n"
     "                  reason: str | None = None) -> AbstractContextManager[TxnContext]:\n"
     "        return self._k.actor_txn(token, expect_rev, op, family=family, reason=reason)\n\n"
     "    def knowledge_case(self, **kw: Any) -> dict[str, Any]:\n"),
])

# 11. the Lead broker never emits a service credential into a model session
patch("src/aew/harness/lead_broker.py", [
    ('frozenset({"lead", "handoff", "offer"}), frozenset({"lead", "handoff", "accept"}))\n',
     'frozenset({"lead", "handoff", "offer"}), frozenset({"lead", "handoff", "accept"}),\n'
     '                       frozenset({"service", "issue"}))\n'),
    ('        return (f"`aew {\' \'.join(sorted(path))}` would put a Lead credential or offer secret into this session; "\n'
     '                "Lead acquisition, handoff, takeover and release are operator actions at the operator\'s own terminal")\n',
     '        return (f"`aew {\' \'.join(sorted(path))}` would put a Lead, service or offer credential into this session; "\n'
     '                "Lead acquisition, handoff, takeover, release and service issuance are operator actions at the "\n'
     '                "operator\'s own terminal")\n'),
])

# 12. tests: environment scrub, dispatch registry, invariants
patch("tests/conftest.py", [(
    '    for key in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_FAULT", "AEW_FAULT_MODE"):\n',
    '    for key in ("AEW_LEAD_TOKEN", "AEW_SERVICE_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_FAULT", "AEW_FAULT_MODE"):\n')])
patch("tests/unit/test_dispatch_decision.py", [(
    '"role validate", "status",\n', '"role validate",\n    "service issue", "service revoke", "service show", "status",\n')])
patch("tests/helpers/invariants.py", [
    ("def control_violations(root: Path) -> list[str]:\n",
     "def service_violations(state: dict[str, Any]) -> list[str]:\n"
     '    """Rule 30 (ADR-0013 D9): a service principal holds at most one live credential; a service credential names\n'
     "    its service and family and carries no Lead generation; a transition a service committed is in its family.\"\"\"\n"
     "    problems: list[str] = []\n"
     "    live: dict[str, list[str]] = {}\n"
     '    for tid, rec in state["tokens"].items():\n'
     '        if rec["kind"] != "service":\n'
     "            continue\n"
     '        scope = rec["scope"]\n'
     '        if not scope.get("service") or not scope.get("family"):\n'
     '            problems.append(f"service credential {tid} names no service or family: {scope}")\n'
     '        if "generation" in scope:\n'
     '            problems.append(f"service credential {tid} is bound to a Lead generation")\n'
     '        if rec["revoked_at"] is None:\n'
     '            live.setdefault(scope.get("service", "?"), []).append(tid)\n'
     "    for service, tids in live.items():\n"
     "        if len(tids) > 1:\n"
     '            problems.append(f"{service} holds {len(tids)} live credentials: {sorted(tids)}")\n'
     '    last = state.get("last_transition") or {}\n'
     '    actor = last.get("actor") or {}\n'
     '    if actor.get("kind") == "service" and not str(last.get("op", "")).startswith(f"{actor.get(\'family\')}."):\n'
     '        problems.append(f"a service committed {last.get(\'op\')}, outside its {actor.get(\'family\')} family")\n'
     "    return problems\n\n\n"
     "def control_violations(root: Path) -> list[str]:\n"),
    ("    problems = control_violations(root)\n    assert not problems",
     "    problems = control_violations(root) + service_violations(load_control(root))\n    assert not problems"),
])
print("all edits applied")
sys.exit(0)
