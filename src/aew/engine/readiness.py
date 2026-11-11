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


def readiness_checks(execution: dict[str, Any] | None, site: str = DOCTOR, *,
                     admitted: set[str] | None = None) -> list[dict[str, str]]:
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
    from aew.harness.containment import netns

    profiles = _relay_profiles(execution)
    names = execution.get("provider_env") or []
    candidates = {provider for provider in profiles.values()
                  if netns.stored_key_candidate(provider, names, os.environ, execution, on_relay_route=True)}
    if admitted is None:
        keys, unavailable = netns.doctor_worker_keys(os.environ, candidates) if candidates else ({}, None)
        stored = set(keys)
        del keys
    else:
        stored, unavailable = admitted & candidates, None
    supplied = {netns.PROVIDER_KEY_ENV[p] for p in stored}
    # Only the pinned provider's row satisfies its own variable. Any other profile
    # still needs that same name from the environment.
    universally_supplied = supplied if (
        len(set(profiles.values())) == 1 and len(profiles) == len(execution.get("profiles") or {})
    ) else set()
    rows: list[dict[str, str]] = []
    if execution.get("profiles"):
        rows.append(_row("model-refs", *_model_refs_doctor(execution)))
    if execution.get("provider_env"):
        rows.append(_row("provider-env", *_provider_env_doctor(execution, site, supplied=universally_supplied)))
    if execution.get("profiles"):
        found = _provider_key_doctor(execution, profiles, stored, unavailable)
        if found is not None:
            rows.append(_row("provider-key", *found))
    found = _client_cert_doctor(execution)
    if found is not None:
        rows.append(_row("client-cert", *found))
    return rows


def readiness_findings(execution: dict[str, Any] | None, site: str = START, *,
                       admitted: set[str] | None = None) -> list[str]:
    """Each FAIL and WARN readiness row as one entry with its cause and fix, worded for ``site``; empty when every row
    passes."""
    return [f"readiness {r['status']} ({r['check']}): {r['detail']}"
            for r in readiness_checks(execution, site, admitted=admitted)
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


def _provider_env_doctor(policy: dict[str, Any], site: str = DOCTOR, *,
                         supplied: set[str] | None = None) -> tuple[str, str]:
    """The provider variables the policy names, as a launch from this environment would find them (FAIL: a launch
    from here is refused, naming each; never their values). At a start or a launch (``site`` :data:`START`) the
    process already has its environment, so the fix is to exit the session, set the variable and start it again."""
    from aew.harness import agentenv

    names = [str(n) for n in policy.get("provider_env") or [] if n not in (supplied or ())]
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
    if supplied:
        detail = "stored OpenCode login: " + ", ".join(sorted(supplied))
        return "PASS", detail + (f"; environment: {', '.join(names)}" if names else "")
    return "PASS", (f"set in this environment: {', '.join(names)} (values not shown; {caveat}: restart one that "
                    "started before they were set)")


def _relay_profiles(policy: dict[str, Any]) -> dict[str, str]:
    from aew.harness import registry
    from aew.harness.containment import netns

    profiles: dict[str, str] = {}
    for name in sorted(policy.get("profiles") or {}):
        try:
            pair = X.model_pair(policy, name, registry.model_identity)
            relay = registry.load(X.profile_harness(policy, policy["profiles"][name])).PROVIDER_RELAY
        except AEWError:  # reported by the model-refs line, or the launch's own refusal
            continue
        if netns.relay_route(policy, relay) and pair.provider in netns.PROVIDER_KEY_ENV:
            profiles[name] = pair.provider
    return profiles


def _provider_key_doctor(policy: dict[str, Any], profiles: dict[str, str], stored: set[str],
                         unavailable: str | None) -> tuple[str, str] | None:
    from aew.harness.containment import netns

    names = [str(n) for n in policy.get("provider_env") or []]
    missing: dict[str, list[str]] = {}
    sources = []
    for name, provider in profiles.items():
        variable = netns.provider_key_missing(provider, names, os.environ, on_relay_route=True,
                                              stored=provider in stored)
        if variable is not None:
            missing.setdefault(f"{provider} ({variable})", []).append(name)
        else:
            source = "stored OpenCode login" if provider in stored else "environment"
            sources.append(f"{name}: {source}")
    detail = "; ".join(sources)
    if stored - netns.CATALOG_ADDRESSED:
        detail += ". Workers and the contained Lead share one rate-limit bucket per model when using the same key."
    if missing:
        return "FAIL", ("a harness launch from this environment is refused (provider_key_missing), since its provider "
                        "would get no key: " + "; ".join(f"{p}, for profile(s) {', '.join(v)}"
                                                          for p, v in sorted(missing.items()))
                        + ". AEW does not use OpenCode's free models; " + netns.FREE_TIER_RULE + " Name the variable "
                        "in the execution policy's provider_env, set it in the terminal you start AEW from, and pin "
                        "a paid model" + (f". {unavailable}" if unavailable else "")
                        + (f". Available sources: {detail}" if detail else ""))
    if detail:
        return "PASS", detail
    return None


def _client_cert_doctor(policy: dict[str, Any]) -> tuple[str, str] | None:
    """Each client certificate the policy names, as the relay will read it at a launch (``client_cert.inspect``, the
    check the relay's start makes, and ``client_cert.no_relay``, a launch's): FAIL with the same lines a launch is
    refused with, each naming its file; PASS with each certificate's expiry; None when the policy names none. Paths
    only, never a file's contents (register E123)."""
    from aew.harness.containment import client_cert, netns

    certs = client_cert.configured(policy)
    if not certs:
        return None
    problems, ready = [], []
    for provider, found in sorted(certs.items()):
        lines, not_after = client_cert.inspect(found)
        no_relay = client_cert.no_relay(provider, policy, on_relay_route=netns.relay_route(policy, True))
        lines += [no_relay] if no_relay else []
        if lines:
            problems.append(f"{provider}: " + "; ".join(lines))
        else:
            until = f", valid until {not_after:%Y-%m-%d %H:%M} UTC" if not_after else ""
            ready.append(f"{provider}: the relay presents {found.cert}{until}, with the key named in "
                         f"{found.field('key')}, and trusts {found.ca} alone")
    if problems:
        return "FAIL", ("a harness launch whose provider needs a client certificate is refused: "
                        + " | ".join(problems))
    ready_line = "; ".join(ready) + " (read at each launch: a renewal or a swapped CA file is picked up by the next)"
    if (((policy.get("containment") or {}).get("mode")) or "") == "allow_weaker":  # E123 review, M1
        return "WARN", (ready_line + "; containment.mode is allow_weaker: a launch whose sandbox can't be established "
                        "here runs with no relay, and is refused for these providers (client_cert_no_relay)")
    return "PASS", ready_line
