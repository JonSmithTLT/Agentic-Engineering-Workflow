"""Which post-integration validation a Ticket gets, and what binds a validation run (M4-D5; the M4-D5 plan rev 3).

``gates.post_integration.validation`` chooses between a model verifier (``verifier``, the default) and AEW's own
deterministic checks (``checks``): a scalar, or ``{by_class: {"0": checks, ...}, default: verifier}`` keyed by the
Ticket's **local** risk class. There is no "effective numeric class": a class inherited from ancestors never chooses
the mode (that would revive numeric ancestor inheritance).

Effective obligations are a separate input, and they override: a Ticket must have an integration verifier when

* an ancestor Story or Epic lists the gate ``post_integration_verifier`` in its ``mandatory_gates``, or
* an ancestor's explicit minimum-class rule (``min_descendant_class``) names a class whose mode is ``verifier``.

Otherwise the class policy may choose ``checks``.

The **obligation binding** is the digest of the legality-affecting inputs this resolution read (the
``post_integration`` policy, the local class, the ancestors' floor and verifier obligations). A validation run pins it
and re-resolves it before it commits; a change abandons the run (``STALE_OBLIGATION``). It is the legality binding of
the pre-F15.2 amendment A3 for this one action; operational settings are never part of it.
"""

from __future__ import annotations

import errno
import hashlib
import json
from typing import Any

from aew.policy import checks as C

VERIFIER, CHECKS = "verifier", "checks"
MODES = (VERIFIER, CHECKS)
INTEGRATION_VERIFIER_GATE = "post_integration_verifier"

# The whole run's deadline: the checks' own timeouts plus an allowance for the executor between them, capped.
ORCHESTRATION_ALLOWANCE_S = 120
DEADLINE_CAP_S = 6 * 3600

# Infrastructure retry (rev 3 correction 4): a positive allow-list, engine-owned and narrow. Anything else, including
# resource exhaustion and every unknown reason, is not retried.
SPAWN_RACE = "SPAWN_RACE"  # the executable was being written as it was started (ETXTBSY): the classic spawn race
SANDBOX_SETUP_TRANSIENT = "SANDBOX_SETUP_TRANSIENT"  # the containment self-test timed out rather than failed
TRANSIENT = frozenset({SPAWN_RACE, SANDBOX_SETUP_TRANSIENT})
MAX_INFRA_ATTEMPTS = 2  # per run identity: the first run and one retry
BACKOFF_S = 30.0
BREAKER_THRESHOLD = 3  # infrastructure failures, project-wide ...
BREAKER_WINDOW_S = 600  # ... within this window, trip the breaker


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def mode_for_class(post: dict[str, Any], risk_class: int) -> str:
    """The policy's preferred mode for a Ticket of ``risk_class`` (its local class)."""
    setting = post.get("validation", VERIFIER)
    if isinstance(setting, str):
        return setting
    return str((setting.get("by_class") or {}).get(str(risk_class), setting.get("default", VERIFIER)))


def obligation(state: dict[str, Any], work_id: str, gates_policy: dict[str, Any]) -> dict[str, Any]:
    """The resolved validation obligation of ``work_id``: ``mode``, whether a verifier is required and why, and the
    ``binding`` digest of the inputs read."""
    post = gates_policy.get("post_integration") or {}
    unit = state["work"][work_id]
    local = int(unit["risk_class"])
    sources: list[str] = []
    floors: dict[str, int] = {}
    parent = unit.get("parent")
    while parent:
        anc = state["work"][parent]
        policy = anc.get("policy") or {}
        if INTEGRATION_VERIFIER_GATE in (policy.get("mandatory_gates") or []):
            sources.append(f"{parent} mandatory gate {INTEGRATION_VERIFIER_GATE}")
        if policy.get("min_descendant_class") is not None:
            floors[parent] = int(policy["min_descendant_class"])
        parent = anc.get("parent")
    # Each ancestor's explicit rule on its own: a mapping need not be monotonic, so one ancestor's higher floor that
    # maps to checks never hides another's lower floor that maps to a verifier (PR #91 review, finding 3).
    for anc_id, cls in sorted(floors.items()):
        if mode_for_class(post, cls) == VERIFIER:
            sources.append(f"{anc_id} minimum descendant class {cls}, whose validation is {VERIFIER}")
    floor = max(floors.values()) if floors else None
    preferred = mode_for_class(post, local)
    required = bool(sources)
    mode = VERIFIER if required else preferred
    basis = {"post_integration": {k: post.get(k) for k in ("verification", "checks", "validation")},
             "local_class": local, "floors": dict(sorted(floors.items())), "verifier_sources": sorted(sources)}
    return {"mode": mode, "preferred": preferred, "verifier_required": required, "sources": sorted(sources),
            "local_class": local, "floor": floor, "binding": _digest(basis)}


def check_set(post: dict[str, Any], checks_policy: dict[str, Any], guardrails: dict[str, Any]) -> dict[str, Any]:
    """The exact current post-integration check set: each check's definition digest, and the set's digest. A check
    that is not configured has no definition (``None``), so the set can never pass until policy defines it."""
    definitions = C.current_definitions(checks_policy, guardrails)
    entries = [{"check_id": c, "definition_sha256": definitions.get(c)} for c in post.get("checks") or []]
    return {"checks": entries, "digest": _digest(entries)}


def deadline_s(post: dict[str, Any], checks_policy: dict[str, Any]) -> int:
    """The run's hard deadline: ``validation_deadline_s`` when policy sets it, otherwise the sum of the checks'
    timeouts plus the orchestration allowance; capped either way."""
    explicit = post.get("validation_deadline_s")
    if explicit:
        return min(int(explicit), DEADLINE_CAP_S)
    total = 0
    for check_id in post.get("checks") or []:
        cfg = (checks_policy.get("checks") or {}).get(check_id) or {}
        total += 0 if check_id in C.BUILTIN else int(cfg.get("timeout_s", C.DEFAULT_TIMEOUT_S))
    return min(total + ORCHESTRATION_ALLOWANCE_S, DEADLINE_CAP_S)


def classify_spawn_failure(spawn_errno: int | None) -> str:
    """The reason code of a check that could not start. Only ETXTBSY is the allow-listed race."""
    if spawn_errno == getattr(errno, "ETXTBSY", -1):
        return SPAWN_RACE
    if spawn_errno == errno.ENOENT:
        return "CHECK_EXECUTABLE_MISSING"
    if spawn_errno in (errno.ENOMEM, errno.EAGAIN):
        return "SPAWN_RESOURCE_EXHAUSTED"
    return "CHECK_SPAWN_FAILED"


def classify_containment_failure(exc: Any) -> str:
    """The reason code of a sandbox that could not be established for the run. A self-test that timed out is the
    allow-listed transient case; a self-test that failed, or a missing bubblewrap, is not retried."""
    test = (getattr(exc, "details", None) or {}).get("self_test") or {}
    if "TimeoutExpired" in str(test.get("reason") or ""):
        return SANDBOX_SETUP_TRANSIENT
    return "CONTAINMENT_SELF_TEST_FAILED" if test else "CONTAINMENT_UNAVAILABLE"


def policy_problems(gates_policy: dict[str, Any]) -> list[str]:
    """What is wrong with the validation settings (the policy consistency check)."""
    post = gates_policy.get("post_integration") or {}
    setting = post.get("validation", VERIFIER)
    problems = []
    modes = [setting] if isinstance(setting, str) else [*(setting.get("by_class") or {}).values(),
                                                         setting.get("default", VERIFIER)]
    if CHECKS in modes and not post.get("checks"):
        problems.append("gates.post_integration.validation selects checks, but post_integration.checks lists none: "
                        "checks-mode validation would prove nothing")
    return problems
