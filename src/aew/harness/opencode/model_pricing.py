"""OpenCode catalog pricing and paid-model admission."""

from __future__ import annotations

import math
from typing import Any


def zero_cost(entry: dict[str, Any]) -> bool:
    """Whether a catalog entry prices the model at nothing: no cost at all, or every tier's input and output at 0."""
    costs = entry.get("cost")
    if isinstance(costs, dict):
        costs = [costs]
    if not costs:
        return True
    return all(float(c.get("input") or 0) == 0 and float(c.get("output") or 0) == 0
               for c in costs if isinstance(c, dict))


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
        return f"{ref}: the catalog prices it at zero"
    if entry is not None and provider == "opencode" and not _has_paid_base(entry):
        return f"{ref}: the catalog has no verified paid base price"
    return None


def _has_paid_base(entry: dict[str, Any]) -> bool:
    tiers = entry.get("cost")
    base = [tier for tier in tiers if isinstance(tier, dict) and "tier" not in tier] if isinstance(tiers, list) else []
    rates = [base[0].get(name) for name in ("input", "output")] if len(base) == 1 else []
    prices = [rate for rate in rates if isinstance(rate, (int, float)) and not isinstance(rate, bool)]
    return len(prices) == 2 and all(math.isfinite(rate) and rate >= 0 for rate in prices) \
        and any(rate > 0 for rate in prices)


def paid_base_problem(entry: dict[str, Any]) -> str | None:
    """A worker's OpenCode Zen pin requires a verified paid base price."""
    ref = f"opencode/{entry['id']}"
    if free_model(ref, [entry]) is not None:
        return (f"model {ref} does not have a verified paid base price; dispatch a new invocation with "
                "--profile or --model to pin a paid OpenCode model or choose another provider")
    return None
