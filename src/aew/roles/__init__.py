"""Role archetypes (authority classes) and the Role-card catalog (ADR-0006).

* **Archetypes** are built into AEW. Authority — which engine operations and
  evidence kinds a credential may use — is enforced in code keyed by archetype
  (``aew.engine.authority.ROLE_OPERATIONS``); the archetype YAML states it and a
  test keeps both equal.
* **Role cards** (built-in deck + project catalog) extend exactly one dispatchable
  archetype. They may add purpose, advisory ``use_when`` guidance,
  responsibilities, skills, capabilities, knowledge and outputs, or *narrow*
  permissions. They can never widen authority; every rule below is enforced when
  a catalog loads and again at dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from aew.errors import NotFound, PermissionDenied, ValidationFailed
from aew.schemas import validate
from aew.util import load_yaml, sha256_bytes

ARCHETYPES = ("lead", "investigator", "researcher", "planner", "implementer", "reviewer", "verifier",
              "frontier_advisor")

# Authority-sensitive capabilities must lie within the archetype's envelope. Ordinary
# read/analysis capabilities come from cards; resolving them against the workbench
# profile is the Capability Contract's job (M6).
AUTHORITY_SENSITIVE_CAPABILITIES = frozenset({
    "source_mutation", "control_state_mutation", "integration_control", "publication",
    "verification_failure_classification", "plan_acceptance", "work_state_transition",
})

SLOT_ARCHETYPES = {"execute": {"implementer", "investigator", "researcher", "planner"},
                   "review": {"reviewer"}, "verify": {"verifier"}}


@dataclass(frozen=True)
class Card:
    id: str
    meta: dict[str, Any]
    source: str  # "builtin" or "project"
    path: str
    sha256: str

    @property
    def archetype(self) -> str:
        return self.meta["extends"]

    def pin(self) -> dict[str, Any]:
        """Identity recorded on every invocation: editing the card later never changes it."""
        return {"id": self.id, "version": self.meta.get("version"), "source": self.source, "path": self.path,
                "sha256": self.sha256, "content": self.meta}


@lru_cache(maxsize=None)
def archetype(name: str) -> dict[str, Any]:
    if name not in ARCHETYPES:
        raise NotFound(f"no role archetype {name!r}; archetypes are {', '.join(ARCHETYPES)}")
    text = resources.files(__package__).joinpath("archetypes", f"{name}.yaml").read_text(encoding="utf-8")
    data = load_yaml(text, source=f"archetypes/{name}.yaml")
    validate("role-archetype", data, source=f"archetypes/{name}.yaml")
    return data


def validate_card(meta: dict[str, Any], *, source: str) -> None:
    """Schema + authority-escalation checks for one card."""
    validate("role", meta, source=source)
    base_name = meta["extends"]
    if base_name not in ARCHETYPES:
        raise ValidationFailed(f"{source}: extends unknown archetype {base_name!r}")
    base = archetype(base_name)
    if not base["dispatchable"]:
        raise PermissionDenied(f"{source}: cards cannot extend {base_name!r} (not a dispatchable authority class)")
    restrict = meta.get("restrict") or {}
    extra_ops = sorted(set(restrict.get("operations", [])) - set(base["engine_operations"]))
    if extra_ops:
        raise PermissionDenied(f"{source}: restrict.operations may only narrow {base_name}; not allowed: {extra_ops}")
    requested = set(meta.get("required_capabilities", [])) | set(meta.get("optional_capabilities", []))
    escalating = sorted((requested & AUTHORITY_SENSITIVE_CAPABILITIES) - set(base["authority_capabilities"]))
    if escalating:
        raise PermissionDenied(
            f"{source}: authority-sensitive capabilities exceed the {base_name} envelope: {escalating}")
    if meta.get("specialty") and base_name != "reviewer":
        raise ValidationFailed(f"{source}: specialty is only meaningful on reviewer cards")


def _read_card(text: str, *, source: str, origin: str, path: str) -> Card:
    meta = load_yaml(text, source=path)
    if not isinstance(meta, dict):
        raise ValidationFailed(f"{path}: a card must be a mapping")
    validate_card(meta, source=path)
    return Card(meta["role"], meta, origin, path, sha256_bytes(text.encode("utf-8")))


@lru_cache(maxsize=None)
def builtin_cards() -> dict[str, Card]:
    cards: dict[str, Card] = {}
    for entry in sorted(resources.files(__package__).joinpath("cards").iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".yaml"):
            card = _read_card(entry.read_text(encoding="utf-8"), source=entry.name, origin="builtin",
                              path=f"aew/roles/cards/{entry.name}")
            cards[card.id] = card
    return cards


@dataclass
class Catalog:
    cards: dict[str, Card]
    problems: list[str]

    def get(self, card_id: str) -> Card:
        card = self.cards.get(card_id)
        if card is None:
            raise NotFound(f"no role card {card_id!r} in the catalog", available=sorted(self.cards))
        return card


def load_catalog(project_dir: Path | None, *, rel_prefix: str = "roles") -> Catalog:
    """Built-in deck + project catalog. Invalid or colliding project cards are reported, never loaded."""
    cards = dict(builtin_cards())
    problems: list[str] = []
    if project_dir is not None and project_dir.is_dir():
        for path in sorted(project_dir.glob("*.yaml")):
            rel = f"{rel_prefix}/{path.name}"
            try:
                raw = path.read_bytes()
                card = _read_card(raw.decode("utf-8"), source=rel, origin="project", path=rel)
                card = Card(card.id, card.meta, card.source, card.path, sha256_bytes(raw))
            except (ValidationFailed, PermissionDenied, NotFound) as exc:
                problems.append(exc.message if exc.message.startswith(rel) else f"{rel}: {exc.message}")
                continue
            if card.id in cards:
                problems.append(f"{rel}: card id {card.id!r} collides with {cards[card.id].source} card "
                                f"{cards[card.id].path}; ids must be unique across catalogs")
                continue
            cards[card.id] = card
    return Catalog(cards, problems)


def default_card(archetype_name: str) -> str | None:
    return archetype(archetype_name).get("default_card")
