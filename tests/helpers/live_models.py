"""Which models a live run may use (the operator, 2026-11-06): never one of OpenCode's free models, whatever provider
serves it. A paid model is allowed, each run approved by the operator, and that includes a paid OpenCode Zen model
(``opencode/gpt-5-nano`` with a relayed key, proved 2026-11-06): the rule is about the price, not the provider.

A model is free when its id says so (a ``-free`` id, as the Zen free models are named) or when the catalog the
OpenCode server serves (``/api/model``, its ``cost`` list of ``Model.Cost`` in the pinned 2.0.18 schema) prices it at
zero, every input and output rate of every tier. A catalog read that came back empty, or lists no model of the
provider, cannot tell free from paid, so it refuses too (review E127 M2: an empty read let ``opencode/big-pickle``, free
but not named ``-free``, through). A model of a listed provider that the catalog does not list cannot launch anyway
(the adapter refuses an unlisted pin, and a keyless catalog leaves a paid one out), so it is left to the launch."""

from __future__ import annotations

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
    return None
