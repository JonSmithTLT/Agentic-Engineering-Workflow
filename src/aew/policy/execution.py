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
from aew.util import load_yaml, sha256_bytes

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
#
# Containment (Linux): every harness run and the checks it runs execute in a bubblewrap sandbox that can write
# only the run's own roots. `containment: {mode: required}` is the default and refuses a launch whose sandbox
# cannot be established; `mode: allow_weaker` launches it labelled workdir_separation_only. `writable` adds
# directories every run may write (for example a shared build cache); `hide` masks further secrets.
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
    raw = path.read_bytes()
    return parse(raw, source=str(path)), sha256_bytes(raw)


def parse(raw: bytes, *, source: str) -> dict[str, Any]:
    """An execution policy from its file's bytes: parsed, schema-validated and semantically checked. Callers that pin
    the file hash these same bytes, so what is checked is what is used."""
    data = load_yaml(raw.decode("utf-8"), source=source)
    refuse_yaml_boolean(data, source=source)
    validate("execution", data, source=source)
    check_semantics(data, source=source)
    return data


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


PACK_SLICES_OFF, PACK_SLICES_STRUCTURAL = "off", "structural"


MESSAGING_DISABLED, MESSAGING_ENABLED = "disabled", "enabled"
PRESENTATION_STANDARD, PRESENTATION_COMPACT = "standard", "compact"


def refuse_yaml_boolean(policy: Any, *, source: str) -> None:
    """``maps.pack_slices`` is the string ``"off"`` or ``structural``. YAML 1.1 reads an unquoted ``off`` (and ``no``,
    ``false``, ``on``, ``yes``, ``true``) as a boolean, which the schema's enum would refuse without saying why: name
    the cause and the fix (PR #143 review, m1). Run before the schema, at parse and at adoption.

    ``coordination.messaging`` is a string enum, not a boolean (F9-A plan D-15), so ``messaging: on`` or ``yes`` is
    refused the same way, with the words to write instead."""
    maps = policy.get("maps") if isinstance(policy, dict) else None
    value = maps.get("pack_slices") if isinstance(maps, dict) else None
    if isinstance(value, bool):
        raise ValidationFailed(
            f"{source}: maps.pack_slices was read as the YAML boolean {str(value).lower()}: YAML reads an unquoted "
            f"off (or no, false, on, yes, true) as a boolean. Quote the value: pack_slices: \"{PACK_SLICES_OFF}\" (or "
            f"{PACK_SLICES_STRUCTURAL})", reason="yaml_boolean", field="maps.pack_slices",
            allowed=[PACK_SLICES_OFF, PACK_SLICES_STRUCTURAL])
    coordination = policy.get("coordination") if isinstance(policy, dict) else None
    value = coordination.get("messaging") if isinstance(coordination, dict) else None
    if isinstance(value, bool):
        raise ValidationFailed(
            f"{source}: coordination.messaging was read as the YAML boolean {str(value).lower()}: the switch is a "
            f"word, not a boolean. Write messaging: {MESSAGING_ENABLED} (or {MESSAGING_DISABLED})",
            reason="yaml_boolean", field="coordination.messaging", allowed=[MESSAGING_DISABLED, MESSAGING_ENABLED])


def messaging(policy: dict[str, Any] | None) -> str:
    """The coordination switch (``coordination.messaging``, F9-A plan D-15): ``disabled`` unless the policy says
    ``enabled``. Absent policy and absent key are ``disabled``. Callers pass the adopted policy only (D-15: the switch
    is read from adopted bytes, ``aew.engine.coordination_ops.messaging_switch``)."""
    value = ((policy or {}).get("coordination") or {}).get("messaging")
    return MESSAGING_ENABLED if value == MESSAGING_ENABLED else MESSAGING_DISABLED


def presentation(policy: dict[str, Any] | None) -> str:
    """The typed surface's presentation (``surface.presentation``, F9-A plan D-33): ``standard`` unless ``compact``."""
    value = ((policy or {}).get("surface") or {}).get("presentation")
    return PRESENTATION_COMPACT if value == PRESENTATION_COMPACT else PRESENTATION_STANDARD


def pack_slices(policy: dict[str, Any] | None) -> str:
    """The project-map switch (``maps.pack_slices``, register F22.1 plan §5.1): ``off`` unless the operator set it.
    Absent policy, absent key and an unreadable policy all mean ``off``, so a map can never change a pack by default."""
    return str(((policy or {}).get("maps") or {}).get("pack_slices") or PACK_SLICES_OFF)


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
