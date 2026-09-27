"""Execution policy (ADR-0010): which harness, provider, model and effort run an invocation.

Model routing is policy, not architecture (WC §18). The policy is resolved exactly once, when an
invocation is created, and the result is pinned on it: editing the policy never changes an in-flight
invocation, and every harness run of that invocation uses the same pin. There is no built-in provider
or model. An unconfigured policy pins nothing (``execution: null``), and harness launch refuses such
an invocation; scripted roles, which never launch a harness, are unaffected.

Resolution, most specific first: role card, then risk class, then archetype, then the default route.
The Lead may override one dispatch (``--profile``, or ``--model PROVIDER/MODEL`` and ``--effort``);
the pin then records ``selected_by: lead``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.errors import UsageError, ValidationFailed
from aew.schemas import validate
from aew.util import read_yaml, sha256_file

REL_PATH = "policy/execution.yaml"  # conventional location; project.yaml policy.execution overrides it
DEFAULT_HARNESS = "opencode"
EFFORT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")

TEMPLATE = """\
# AEW execution policy (ADR-0010): which harness, provider, model and effort run each invocation.
# It is resolved once at dispatch and pinned on the invocation, so editing this file never changes an
# in-flight invocation. There is no built-in provider or model: until `configured: true`, invocations
# are dispatched without a pinned execution and `aew harness launch` refuses them. The Lead can still
# pin one dispatch explicitly with `--profile NAME` or `--model PROVIDER/MODEL [--effort E]`.
#
# Secrets never go in this file. `provider_env` lists only the NAMES of environment variables that the
# harness server process needs (for example a provider API key); the agent's own shell never gets them.
#
# Routing, most specific first: cards (role card id), classes (risk class "0".."4"), archetypes
# (implementer, reviewer, verifier, investigator, researcher, planner), then default. `effort` is the
# harness's reasoning-effort variant. Use provider and model ids exactly as the harness lists them.
#
# Example (illustrative ids):
#   configured: true
#   harness: opencode
#   profiles:
#     standard: {provider: anthropic, model: claude-sonnet-5, effort: high}
#     light: {provider: anthropic, model: claude-haiku-4-5, effort: low}
#   routing:
#     default: standard
#     archetypes: {reviewer: standard}
#     classes: {"0": light}
#     cards: {}
#   provider_env: [ANTHROPIC_API_KEY]
schema: aew/execution/v1
configured: false
harness: opencode
profiles: {}
routing:
  default: null
  archetypes: {}
  classes: {}
  cards: {}
provider_env: []
"""


def policy_path(aew_root: Path, manifest: dict[str, Any]) -> Path:
    rel = (manifest.get("policy") or {}).get("execution") or REL_PATH
    return aew_root / rel


def load(aew_root: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The execution policy and the sha256 of its file, or ``(None, None)`` when the file is absent.

    A project initialized before M3 has no file: it behaves exactly like an unconfigured policy.
    A present but invalid file fails closed (no dispatch can pin from a policy AEW cannot read).
    """
    path = policy_path(aew_root, manifest)
    if not path.exists():
        return None, None
    data = read_yaml(path)
    validate("execution", data, source=str(path))
    check_semantics(data, source=str(path))
    return data, sha256_file(path)


def check_semantics(policy: dict[str, Any], *, source: str) -> None:
    profiles = policy["profiles"]
    routing = policy["routing"]
    problems = []
    targets = [("routing.default", routing.get("default"))] if routing.get("default") else []
    for table in ("archetypes", "classes", "cards"):
        targets += [(f"routing.{table}.{key}", name) for key, name in (routing.get(table) or {}).items()]
    problems += [f"{where}: no profile {name!r}" for where, name in targets if name not in profiles]
    if policy["configured"] and not routing.get("default"):
        problems.append("routing.default: a configured policy needs a default route")
    if problems:
        raise ValidationFailed(f"{source}: execution policy is inconsistent", violations=problems)


def route(policy: dict[str, Any], *, archetype: str, card_id: str | None, risk_class: int | None) -> tuple[str, str]:
    """(profile name, the rule that selected it) for a configured policy."""
    routing = policy["routing"]
    if card_id and card_id in (routing.get("cards") or {}):
        return routing["cards"][card_id], f"card:{card_id}"
    if risk_class is not None and str(risk_class) in (routing.get("classes") or {}):
        return routing["classes"][str(risk_class)], f"class:{risk_class}"
    if archetype in (routing.get("archetypes") or {}):
        return routing["archetypes"][archetype], f"archetype:{archetype}"
    return routing["default"], "default"


def _pin(policy: dict[str, Any], name: str, *, selected_by: str, rule: str, sha: str | None) -> dict[str, Any]:
    profile = policy["profiles"][name]
    return {"profile": name, "harness": profile.get("harness") or policy.get("harness") or DEFAULT_HARNESS,
            "provider": profile["provider"], "model": profile["model"], "effort": profile.get("effort"),
            "max_steps": profile.get("max_steps"), "deadline_s": profile.get("deadline_s"),
            "selected_by": selected_by, "rule": rule, "policy_sha256": sha}


def _check_effort(effort: str) -> None:
    if not effort or set(effort) - EFFORT_CHARS:
        raise UsageError(f"--effort {effort!r} is not a valid effort name (letters, digits, '.', '_', '-')")


def resolve(policy: dict[str, Any] | None, sha: str | None, *, archetype: str, card_id: str | None,
            risk_class: int | None, request: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The execution pin for a new invocation, or None when nothing selects one (unconfigured policy)."""
    request = {k: v for k, v in (request or {}).items() if v is not None}
    unknown = set(request) - {"profile", "model", "effort"}
    if unknown:
        raise UsageError(f"unknown execution selection {sorted(unknown)}")
    if "profile" in request and "model" in request:
        raise UsageError("--profile and --model are alternatives; pass one")
    if "effort" in request:
        _check_effort(request["effort"])
    if "model" in request:
        provider, _, model = str(request["model"]).partition("/")
        if not provider or not model or any(c.isspace() for c in request["model"]):
            raise UsageError("--model is PROVIDER/MODEL, exactly as the harness lists it")
        return {"profile": None, "harness": (policy or {}).get("harness") or DEFAULT_HARNESS, "provider": provider,
                "model": model, "effort": request.get("effort"), "max_steps": None, "deadline_s": None,
                "selected_by": "lead", "rule": "lead:model", "policy_sha256": sha}
    if "profile" in request:
        name = request["profile"]
        if policy is None or name not in policy["profiles"]:
            raise UsageError(f"no execution profile {name!r} in {REL_PATH}",
                             profiles=sorted((policy or {}).get("profiles") or {}))
        pin = _pin(policy, name, selected_by="lead", rule="lead:profile", sha=sha)
    else:
        if policy is None or not policy["configured"]:
            if "effort" in request:
                raise UsageError("--effort adjusts a selected model, but the execution policy is unconfigured; "
                                 "also pass --profile or --model")
            return None
        name, rule = route(policy, archetype=archetype, card_id=card_id, risk_class=risk_class)
        pin = _pin(policy, name, selected_by="policy", rule=rule, sha=sha)
    if "effort" in request and request["effort"] != pin["effort"]:
        pin.update(effort=request["effort"], selected_by="lead", rule=f"{pin['rule']}+lead:effort")
    return pin
