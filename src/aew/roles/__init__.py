"""Durable role definitions (WC §5): authority and context contracts, not agent identities."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

from aew.errors import NotFound
from aew.schemas import validate
from aew.util import load_yaml, sha256_text

ROLES = ("lead", "implementer", "reviewer", "specialist", "verifier", "planner", "investigator")


@lru_cache(maxsize=None)
def load(name: str) -> tuple[dict[str, Any], str]:
    """Return (definition, sha256 of the definition file)."""
    if name not in ROLES:
        raise NotFound(f"no role definition {name}")
    text = resources.files(__package__).joinpath(f"{name}.yaml").read_text(encoding="utf-8")
    data = load_yaml(text, source=f"roles/{name}.yaml")
    validate("role", data, source=f"roles/{name}.yaml")
    return data, sha256_text(text)
