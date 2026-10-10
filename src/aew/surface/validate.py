"""Adapter input validation (typed-lead-surface-design-v0.2 §3.3, §12.8).

A call whose tool is unknown, designed, not offered on the caller's profile, or whose arguments do not match the
tool's schema never reaches the runner: it commits nothing and is reported as an ``AdapterInputError``, never as a
``StageResult`` and never as an engine refusal. Both transports report it the same way.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from aew.surface import contract
from aew.surface.contract import Tool
from aew.surface.errors import CODES, AdapterInputError

__all__ = ["CODES", "AdapterInputError", "check_call"]

@cache
def _validator(name: str) -> Draft202012Validator:
    # The argument schemas are AEW's own: test_surface_contract checks them against the metaschema once.
    return Draft202012Validator(contract.TOOLS[name].input_schema)


def check_call(name: Any, arguments: Any, profile: str) -> Tool:
    """The tool a well-formed call names, or ``AdapterInputError``."""
    t = contract.tool(name) if isinstance(name, str) else None
    if t is None:
        raise AdapterInputError("UNKNOWN_TOOL", f"no tool {name!r}",
                                offered=[x.name for x in contract.exposed(profile)])
    if not t.built:
        raise AdapterInputError("TOOL_NOT_BUILT", f"{t.name} is designed but not built yet",
                                offered=[x.name for x in contract.exposed(profile)])
    if profile not in t.profiles:
        raise AdapterInputError("TOOL_NOT_EXPOSED", f"{t.name} is not offered on the {profile} surface profile",
                                offered=[x.name for x in contract.exposed(profile)])
    if not isinstance(arguments, dict):
        raise AdapterInputError("INVALID_ARGUMENTS", f"{t.name}: the arguments must be a JSON object")
    errors = sorted(_validator(t.name).iter_errors(arguments), key=lambda e: list(e.absolute_path))
    if errors:
        raise AdapterInputError(
            "INVALID_ARGUMENTS", f"{t.name}: the arguments do not match the tool's schema",
            violations=[f"{'/'.join(map(str, e.absolute_path)) or '<arguments>'}: {e.message}" for e in errors[:20]])
    if t.name == "steering":
        _check_steering(arguments)
    if t.name == "explain":
        _check_explain(arguments)
    if t.name == "resolve" and not arguments["rationale"].strip():
        # Kept out of the schema to keep the advertised bytes (plan v3 §2.6); an input error all the same.
        raise AdapterInputError("INVALID_ARGUMENTS", "resolve: the rationale says why, and is never blank",
                                violations=["rationale: blank"])
    return t


def _check_steering(arguments: dict[str, Any]) -> None:
    """The arguments each `steering` action needs and allows (plan v3 §2.6; frozen decision 8): a mismatch is an input
    error, never a partial request."""
    required, allowed = contract.STEERING_ARGUMENTS[arguments["action"]]
    given = set(arguments) - {"expect_rev", "action"}
    missing = [a for a in required if a not in arguments]
    extra = sorted(given - set(allowed))
    if missing or extra:
        raise AdapterInputError(
            "INVALID_ARGUMENTS", f"steering: action {arguments['action']} takes {', '.join(allowed)}",
            violations=[*(f"{a}: required for {arguments['action']}" for a in missing),
                        *(f"{a}: not taken by {arguments['action']}" for a in extra)])


def _check_explain(arguments: dict[str, Any]) -> None:
    """`explain` names a unit, an invocation or a stage; a stage's `arguments` match that stage's own schema, its
    `expect_rev` aside (M4-E E4; kept out of the advertised schema, plan v3 §2.6). A mismatch is an input error."""
    if not {"work_id", "invocation", "stage"} & set(arguments):
        raise AdapterInputError("INVALID_ARGUMENTS", "explain: name a work_id, an invocation or a stage",
                                violations=["<arguments>: one of work_id, invocation or stage is required"])
    if "stage" not in arguments:
        if "arguments" in arguments:
            raise AdapterInputError("INVALID_ARGUMENTS", "explain: arguments are a stage's, and need its stage",
                                    violations=["arguments: given without stage"])
        return
    t = contract.tool(arguments["stage"])
    if t is None or t.kind not in (contract.STAGE, contract.DECISION) or not t.progression:
        raise AdapterInputError("INVALID_ARGUMENTS", f"explain: {arguments['stage']!r} is not a stage",
                                violations=["stage: not a stage of the catalog"],
                                stages=[x.name for x in contract.TOOLS.values() if x.progression])
    given = {**(arguments.get("arguments") or {}), "expect_rev": 0}
    if "work_id" in arguments:
        given.setdefault("work_id", arguments["work_id"])
    errors = sorted(_validator(t.name).iter_errors(given), key=lambda e: list(e.absolute_path))
    if errors:
        raise AdapterInputError(
            "INVALID_ARGUMENTS", f"explain: the arguments do not match {t.name}'s schema",
            violations=[f"arguments/{'/'.join(map(str, e.absolute_path)) or '<arguments>'}: {e.message}"
                        for e in errors[:20]])
