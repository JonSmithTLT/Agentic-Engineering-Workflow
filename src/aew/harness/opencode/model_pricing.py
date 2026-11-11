"""OpenCode catalog pricing and paid-model admission."""

from __future__ import annotations

import math
from typing import Any


def _valid_rate(rate: Any) -> bool:
    return (
        isinstance(rate, (int, float)) and not isinstance(rate, bool)
        and (isinstance(rate, int) or math.isfinite(rate)) and rate >= 0
    )


def zero_cost(entry: dict[str, Any]) -> bool:
    """Whether the catalog shows zero cost or cannot establish usable pricing."""
    costs = entry.get("cost")
    if not isinstance(costs, list) or any(not isinstance(tier, dict) for tier in costs):
        return True
    rates = [tier.get(name, 0) for tier in costs for name in ("input", "output")]
    return not all(map(_valid_rate, rates)) or not any(rate > 0 for rate in rates)


def free_model(ref: str, catalog: list[dict[str, Any]]) -> str | None:
    """Why ``ref`` (``provider/model``) is a free model, or None when it is not one."""
    provider, _, model = ref.partition("/")
    if model.endswith("-free") or "-free-" in model or model == "free":
        return f"{ref}: a -free id"
    if not catalog:
        return f"{ref}: the catalog read came back empty, so free cannot be told from paid"
    if not any(m.get("providerID") == provider for m in catalog):
        return f"{ref}: the catalog lists no {provider} model, so free cannot be told from paid"
    entry = next((m for m in catalog if m.get("providerID") == provider and m.get("id") == model), None)
    if entry is not None and zero_cost(entry):
        return f"{ref}: the catalog prices it at zero or has unusable pricing"
    if entry is not None and provider == "opencode" and not _has_paid_base(entry):
        return f"{ref}: the catalog has no verified paid base price"
    return None


def _has_paid_base(entry: dict[str, Any]) -> bool:
    tiers = entry.get("cost")
    base = [tier for tier in tiers if isinstance(tier, dict) and "tier" not in tier] if isinstance(tiers, list) else []
    rates: list[Any] = [base[0].get(name) for name in ("input", "output")] if len(base) == 1 else []
    return len(rates) == 2 and all(map(_valid_rate, rates)) and any(rate > 0 for rate in rates)


def paid_base_problem(entry: dict[str, Any]) -> str | None:
    """A worker's OpenCode Zen pin requires a verified paid base price."""
    model = entry.get("id")
    if isinstance(model, str) and model:
        ref = f"opencode/{model}"
        if free_model(ref, [entry]) is None:
            return None
        label = f"model {ref}"
    else:
        label = "the OpenCode model with a missing or invalid catalog id"
    return (f"{label} does not have a verified paid base price; dispatch a new invocation with "
            "--profile or --model to pin a paid OpenCode model or choose another provider")
