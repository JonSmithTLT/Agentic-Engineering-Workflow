"""The catalog of the typed Lead surface, v1 (typed-lead-surface-design-v0.2 §3.1, §3.2, §3.5; F15.1).

Data only. Each row states a tool's kind, its base operation class, the exact JSON Schema of its arguments (closed:
``additionalProperties: false`` everywhere), the engine primitives it expands to in order, the judgment inputs it
always carries, the arguments that promote an invocation to ``JUDGMENT_BEARING`` (§12.7), whether it advances the
workflow (``progression``: the only rows a stage runner may ever auto-run), its build status and the surface profiles
that offer it. Transports render their tool lists from this table and call :mod:`aew.surface.run`; conformance
tests enumerate it against the dispatch registry.

F15.1 builds the queries, the wait, the single-step ``checkpoint`` and the recovery-only ``cli`` escape. The stages
and the publication decision tool are ``DESIGNED``: their full contract is here so the tests pin it today, they are
never listed, and a call is refused before the runner (F15.2 builds them over the StageIntent journal, §12.5).
"""

from __future__ import annotations

from typing import Any, NamedTuple

from aew.surface.context import NORMAL, PROFILES, RECOVERY

# The catalog imports no engine code, so the MCP transport that renders it (`aew lead mcp`, which must hold no
# authority) does not either. These mirror aew.engine.primitives and aew.engine.dispatch exactly (tested).
MECHANICAL, POLICY_RESOLVED, JUDGMENT_BEARING = "MECHANICAL", "POLICY_RESOLVED", "JUDGMENT_BEARING"
OPERATION_CLASSES = (MECHANICAL, POLICY_RESOLVED, JUDGMENT_BEARING)

QUERY = "query"  # reads committed state and local telemetry; never commits
WAIT = "wait"  # blocks on local run telemetry and committed events; never commits
STAGE = "stage"  # one Lead decision: a guarded sequence of primitives, each its own durable transition
DECISION = "decision"  # a single-primitive judgment tool (publication, §3.1)
PRIMITIVE = "primitive"  # the recovery escape: one existing `aew` command
KINDS = (QUERY, WAIT, STAGE, DECISION, PRIMITIVE)

BUILT = "built"
DESIGNED = "designed"  # in the contract, not implemented: never listed, refused before the runner if called

BOTH = (NORMAL, RECOVERY)


class Tool(NamedTuple):
    name: str
    kind: str
    base_class: str
    description: str
    input_schema: dict[str, Any]
    expands_to: tuple[str, ...] = ()  # primitive ids, in run order
    required_judgments: tuple[str, ...] = ()  # judgment inputs every invocation carries (§3.5)
    promotes: tuple[str, ...] = ()  # arguments that, when supplied, make the invocation JUDGMENT_BEARING (§3.2)
    dispatches: bool = False  # creates an invocation or run; always with the run's supervisor taking custody
    mutates: bool = False
    progression: bool = False  # advances the workflow: eligible for the stage runner (F15.2), never a query or wait
    status: str = BUILT
    profiles: tuple[str, ...] = BOTH

    @property
    def built(self) -> bool:
        return self.status == BUILT


# ---------------------------------------------------------------------------------------------- schema pieces

def _obj(properties: dict[str, Any], required: tuple[str, ...] = (), **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False, **extra}
    if required:
        out["required"] = list(required)
    return out


def _strings(description: str, *, min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "array", "items": {"type": "string", "minLength": 1}, "description": description}
    if min_items:
        out["minItems"] = min_items
    if max_items is not None:
        out["maxItems"] = max_items
    return out


EXPECT_REV = {"type": "integer", "minimum": 0,
              "description": "the `revision` of your last result; if the state moved since, nothing changes "
                             "(STALE_REVISION)"}
WORK_ID = {"type": "string", "pattern": "^[A-Z]+-[0-9]+$", "description": "a work unit id, e.g. T-0012"}
TEXT = {"type": "string", "description": "free text, stored as given; no shell ever sees it"}
EVIDENCE_ID = {"type": "string", "minLength": 1, "description": "the evidence id you inspected"}
EXECUTION = _obj({
    "profile": {"type": "string", "minLength": 1},
    "model": {"type": "string", "minLength": 1, "description": "PROVIDER/MODEL instead of a profile"},
    "effort": {"type": "string", "minLength": 1},
}, description="a Lead override of execution policy (ADR-0010); supplying it makes the call judgment-bearing")
ASSURANCE = {"description": "'none', or the review and verification cards that become required gates",
             "oneOf": [{"const": "none"},
                       _obj({"review": _strings("review cards"), "verify": _strings("verification cards")})]}
PLAN = _obj({"body": {**TEXT, "description": "the plan, Markdown"},
             "affected": _strings("paths the plan changes"),
             "assurance": ASSURANCE, "reason": TEXT},
            ("body", "assurance"), description="a plan to propose (never accepted by this stage)")

# Handoff text stays a bounded mechanism, not a free-form memory store (operator, 2026-10-05).
NOTE_MAX, NEXT_MAX = 8000, 500

# The dispatch entrypoints a decision can be asked of: every one that is not covered by another (tested to equal
# aew.engine.dispatch.ENTRYPOINTS without the covered ones).
EXPLAINABLE = sorted(("harness.launch", "integrate.prepare", "invoke.create.mutating", "invoke.create.non_mutating",
                      "invoke.create.parent", "work.assign", "work.dispatch", "work.redispatch"))


# ---------------------------------------------------------------------------------------------- the catalog

def _catalog(*tools: Tool) -> dict[str, Tool]:
    out: dict[str, Tool] = {}
    for t in tools:
        if t.kind not in KINDS or t.base_class not in OPERATION_CLASSES or t.status not in (BUILT, DESIGNED):
            raise ValueError(f"tool {t.name}: unknown kind, class or status")
        if not set(t.profiles) <= set(PROFILES):
            raise ValueError(f"tool {t.name}: unknown profile")
        if t.name in out:
            raise ValueError(f"tool {t.name} is declared twice")
        out[t.name] = t
    return out


TOOLS: dict[str, Tool] = _catalog(
    # ---- queries
    Tool("status", QUERY, MECHANICAL,
         "AEW status: the project (Lead, work, runs, next actions) or one work unit's control record.",
         _obj({"work_id": WORK_ID})),
    Tool("resume", QUERY, MECHANICAL,
         "Rebuild the Lead's context from durable state: objective, active work, runs, contradictions, next actions. "
         "Call it first after any restart.",
         _obj({})),
    Tool("work_show", QUERY, MECHANICAL, "One work unit: its record, plans, evidence, gates and integration.",
         _obj({"work_id": WORK_ID}, ("work_id",))),
    Tool("explain", QUERY, MECHANICAL,
         "The dispatch decision a dispatch would get now (allowed or not, with every blocking condition), from the "
         "predicate the dispatch itself uses.",
         _obj({"work_id": WORK_ID,
               "entrypoint": {"type": "string", "enum": EXPLAINABLE,
                              "description": "which dispatch; default: the unit's next one"},
               "role": {"type": "string", "enum": ["implementer", "reviewer", "verifier"]},
               "card": {"type": "string", "minLength": 1},
               "scope": {"type": "string", "enum": ["ticket", "integration"]},
               "invocation": {"type": "string", "minLength": 1,
                              "description": "explain a harness launch of this invocation instead"}},
              anyOf=[{"required": ["work_id"]}, {"required": ["invocation"]}])),
    Tool("harness_status", QUERY, MECHANICAL, "Harness runs: status, heartbeat, evidence produced.",
         _obj({"invocation": {"type": "string", "minLength": 1}})),
    # ---- the wait
    Tool("harness_wait", WAIT, MECHANICAL,
         "Block until the first of the named runs is no longer running, then return its status, evidence and the "
         "runs still running. One call replaces polling.",
         _obj({"runs": {**_strings("run ids, e.g. R-INV-0003-1", min_items=1, max_items=16), "uniqueItems": True},
               "timeout_s": {"type": "integer", "minimum": 1, "maximum": 600,
                             "description": "default 600"}}, ("runs",))),
    # ---- the one normal-profile mutation: a single engine transaction, so no stage intent (§3.4)
    Tool("checkpoint", STAGE, MECHANICAL,
         "Record a checkpoint note and your next intended action (before a pause or a handoff).",
         _obj({"expect_rev": EXPECT_REV,
               "note": {**TEXT, "maxLength": NOTE_MAX},
               "next": {**TEXT, "maxLength": NEXT_MAX, "description": "the next intended action"}},
              ("expect_rev",)),
         expands_to=("checkpoint",), mutates=True),
    # ---- the recovery escape: catalogued, never on the normal profile (§12.2)
    Tool("cli", PRIMITIVE, JUDGMENT_BEARING,
         "Recovery: run one `aew` command, arguments as a list (no shell). The session supplies Lead authentication.",
         _obj({"argv": _strings("the command and its arguments", min_items=1),
               "stdin": {"type": "string", "description": "text for an argument given as '-'"}},
              ("argv",)),
         required_judgments=("undeclared",), mutates=True, profiles=(RECOVERY,)),
    # ---- designed in F15.1, built by F15.2 over the StageIntent journal
    Tool("ticket_draft", STAGE, JUDGMENT_BEARING,
         "Create a Ticket from your proposition and, if given, propose its plan (proposed, not accepted).",
         _obj({"expect_rev": EXPECT_REV, "title": {"type": "string", "minLength": 1},
               "risk_class": {"type": "integer", "minimum": 0, "maximum": 4},
               "scope": _strings("allowed change path globs"), "goal": _strings("goal-backwards criteria"),
               "contract": _strings("contract criteria"), "non_mutating": {"type": "boolean"},
               "parent": WORK_ID, "depends_on": _strings("ID or ID:mutating|evidence"),
               "rationale": TEXT, "body": TEXT, "card": {"type": "string", "minLength": 1},
               "plan": PLAN},
              ("expect_rev", "title", "risk_class")),
         expands_to=("work.create", "plan.propose"), required_judgments=("ticket_proposition", "plan_proposal"),
         mutates=True, progression=True, status=DESIGNED),
    Tool("ticket_start", STAGE, POLICY_RESOLVED,
         "Start a READY mutating Ticket: assign by policy, launch its run, move it to RUNNING.",
         _obj({"expect_rev": EXPECT_REV, "work_id": WORK_ID, "execution": EXECUTION}, ("expect_rev", "work_id")),
         expands_to=("work.assign", "dispatch.launch", "work.transition"), promotes=("execution",),
         dispatches=True, mutates=True, progression=True, status=DESIGNED),
    Tool("ticket_request_review", STAGE, POLICY_RESOLVED,
         "Submit a RUNNING Ticket for review: move it to REVIEW_PENDING and launch the reviewers policy requires.",
         _obj({"expect_rev": EXPECT_REV, "work_id": WORK_ID, "execution": EXECUTION}, ("expect_rev", "work_id")),
         expands_to=("work.transition", "invoke.create.mutating", "dispatch.launch"), promotes=("execution",),
         dispatches=True, mutates=True, progression=True, status=DESIGNED),
    Tool("ticket_request_verification", STAGE, JUDGMENT_BEARING,
         "Accept the named review report, move the Ticket to VERIFY_PENDING and launch the verifiers policy requires.",
         _obj({"expect_rev": EXPECT_REV, "work_id": WORK_ID, "review_evidence": EVIDENCE_ID,
               "execution": EXECUTION}, ("expect_rev", "work_id", "review_evidence")),
         expands_to=("review.ingest", "work.transition", "invoke.create.mutating", "dispatch.launch"),
         required_judgments=("accept_review_evidence",), promotes=("execution",),
         dispatches=True, mutates=True, progression=True, status=DESIGNED),
    Tool("ticket_prepare", STAGE, JUDGMENT_BEARING,
         "Accept the named verification and prepare the integration candidate. Publication stays a separate decision.",
         _obj({"expect_rev": EXPECT_REV, "work_id": WORK_ID, "verification_evidence": EVIDENCE_ID,
               "execution": EXECUTION}, ("expect_rev", "work_id", "verification_evidence")),
         expands_to=("verify.ingest", "work.transition", "integrate.prepare", "invoke.create.mutating",
                     "dispatch.launch"),
         required_judgments=("accept_verification",), promotes=("execution",),
         dispatches=True, mutates=True, progression=True, status=DESIGNED),
    Tool("integration_publish", DECISION, JUDGMENT_BEARING,
         "Publish the prepared integration candidate: calling this is your publication decision.",
         _obj({"expect_rev": EXPECT_REV, "work_id": WORK_ID,
               "prepared_candidate": {"type": "string", "minLength": 1}},
              ("expect_rev", "work_id", "prepared_candidate")),
         expands_to=("integrate.publish",), required_judgments=("publish_candidate",),
         mutates=True, progression=True, status=DESIGNED),
)


def tool(name: str) -> Tool | None:
    return TOOLS.get(name)


def exposed(profile: str) -> list[Tool]:
    """The tools a transport offers on ``profile``: built ones, in catalog order."""
    return [t for t in TOOLS.values() if t.built and profile in t.profiles]


def callable_on(t: Tool | None, profile: str) -> bool:
    """Whether a caller on ``profile`` can call ``t`` now. Presentation only: never legality, never auto_runnable."""
    return t is not None and t.built and profile in t.profiles
