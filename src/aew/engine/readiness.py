"""Readiness (register E125; V-01's step 11, which the operator's decision of 2026-11-02 makes a local readiness
surface): what a launch from this environment would meet in the execution policy, before any launch and structural
only. Its one owner, for ``aew doctor`` (the engine facade's ``doctor_checks``), the start of ``aew opencode``
(``aew.doctor.readiness_lines``) and every launch the Lead makes (``Harness._with_readiness``)."""

from __future__ import annotations

import os
from typing import Any

from aew.errors import AEWError
from aew.policy import execution as X

# Where a readiness row is read (review of #360, m2): ``aew doctor``, or a start or a launch (``aew opencode``, every
# Lead launch), whose own process keeps the environment it has, so its fix says to restart that session.
DOCTOR, START = "doctor", "start"


def readiness_checks(execution: dict[str, Any] | None, site: str = DOCTOR) -> list[dict[str, str]]:
    """Readiness: what a launch from this environment would meet in the execution policy, before any launch, and
    structural only (no provider is called): each profile's model as the harness will be given it, the provider
    variables, and each profile's provider key (ADR-0010 amendment 2026-10-11; the M4 user acceptance test's doubled
    model id and silently dropped key). Each row is a launch's own check, and a FAIL names its cause and its fix.

    The one owner of these rows (register E125; V-01's step 11, which the operator's decision of 2026-11-02 makes a
    local readiness surface): ``aew doctor`` shows them; ``aew opencode`` prints each FAIL and WARN at its start, and
    every launch the Lead makes carries them in ``readiness`` (:func:`readiness_findings`). ``site`` words each fix
    for where it is read, from the same check. They add no refusal of their own: a launch refuses where its own check
    fails, as before."""
    if execution is None:
        return []
    rows: list[dict[str, str]] = []
    if execution.get("profiles"):
        rows.append(_row("model-refs", *_model_refs_doctor(execution)))
    if execution.get("provider_env"):
        rows.append(_row("provider-env", *_provider_env_doctor(execution, site)))
    if execution.get("profiles"):
        found = _provider_key_doctor(execution)
        if found is not None:
            rows.append(_row("provider-key", *found))
    return rows


def readiness_findings(execution: dict[str, Any] | None, site: str = START) -> list[str]:
    """Each FAIL and WARN readiness row as one entry with its cause and fix, worded for ``site``; empty when every row
    passes."""
    return [f"readiness {r['status']} ({r['check']}): {r['detail']}" for r in readiness_checks(execution, site)
            if r["status"] in ("FAIL", "WARN")]


def _row(check: str, status: str, detail: str) -> dict[str, str]:
    return {"check": check, "status": status, "detail": detail}


def _model_refs_doctor(policy: dict[str, Any]) -> tuple[str, str]:
    """Each profile's model through its harness adapter's model identity: the reference the harness is given, or
    why the profile's model maps to no provider/model pair and what to write instead (FAIL). Structural: whether the
    harness lists that model is readiness, which needs the harness itself."""
    from aew.harness import registry

    refs, problems = [], []
    for name in sorted(policy["profiles"]):
        try:
            pair = X.model_pair(policy, name, registry.model_identity)
        except AEWError as exc:
            problems.append(exc.message)
            continue
        refs.append(f"{name}: {pair.harness_ref}")
    if problems:
        return "FAIL", "; ".join(problems) + "; dispatch with these profiles is refused until they are fixed"
    return "PASS", "the harness is given " + "; ".join(refs)


def _provider_env_doctor(policy: dict[str, Any], site: str = DOCTOR) -> tuple[str, str]:
    """The provider variables the policy names, as a launch from this environment would find them (FAIL: a launch
    from here is refused, naming each; never their values). At a start or a launch (``site`` :data:`START`) the
    process already has its environment, so the fix is to exit the session, set the variable and start it again."""
    from aew.harness import agentenv

    names = [str(n) for n in policy.get("provider_env") or []]
    problems = agentenv.provider_env_problems(names, os.environ)
    # Doctor reads its own terminal's environment; a Lead session already running reads the one it started with
    # (review of PR #214, F2), so both lines say so.
    caveat = ("doctor checks this terminal's environment; a Lead session (`aew opencode`, `aew lead session`) that "
              "is already running keeps the environment it started with")
    if problems and site == START:
        missing = ", ".join(n for n, _ in problems)
        return "FAIL", ("a harness launch from this Lead session will be refused: " + "; ".join(w for _, w in problems)
                        + f". A Lead session keeps the environment it started with, so set {missing} first: exit "
                        "the session, set it in the terminal you start AEW from, then start `aew opencode` again")
    if problems:
        return "FAIL", ("a harness launch from this environment is refused: " + "; ".join(w for _, w in problems)
                        + f" ({caveat})")
    return "PASS", (f"set in this environment: {', '.join(names)} (values not shown; {caveat}: restart one that "
                    "started before they were set)")


def _provider_key_doctor(policy: dict[str, Any]) -> tuple[str, str] | None:
    """Each profile's provider as a launch from this environment would find its key on the relay route
    (``netns.provider_key_missing``, the check every such launch makes): FAIL naming the profiles whose launch is
    refused (``provider_key_missing``) and the fix; PASS when every profile whose key AEW can judge has one; None
    when there is nothing to judge (no profile on the relay route, as on Windows, or no provider whose key variable
    AEW knows). Names only, never a value."""
    from aew.harness import registry
    from aew.harness.containment import netns

    names = [str(n) for n in policy.get("provider_env") or []]
    missing: dict[str, list[str]] = {}
    judged = []
    for name in sorted(policy["profiles"]):
        try:
            pair = X.model_pair(policy, name, registry.model_identity)
            relay = registry.load(X.profile_harness(policy, policy["profiles"][name])).PROVIDER_RELAY
        except AEWError:  # reported by the model-refs line, or the launch's own refusal
            continue
        on_route = netns.relay_route(policy, relay)
        if not on_route or pair.provider not in netns.PROVIDER_KEY_ENV:
            continue
        judged.append(name)
        variable = netns.provider_key_missing(pair.provider, names, os.environ, on_relay_route=on_route)
        if variable is not None:
            missing.setdefault(f"{pair.provider} ({variable})", []).append(name)
    if missing:
        return "FAIL", ("a harness launch from this environment is refused (provider_key_missing), since its provider "
                        "would get no key: " + "; ".join(f"{p}, for profile(s) {', '.join(v)}"
                                                          for p, v in sorted(missing.items()))
                        + ". AEW does not use OpenCode's free models; " + netns.FREE_TIER_RULE + " Name the variable "
                        "in the execution policy's provider_env, set it in the terminal you start AEW from, and pin "
                        "a paid model")
    if judged:
        return "PASS", f"a provider key reaches the run for profile(s) {', '.join(judged)} (names only)"
    return None
