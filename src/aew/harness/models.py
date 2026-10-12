"""The model identity: the one rule that maps a model id to AEW's provider/model pair (ADR-0010, amendment 2026-10-11).

It is the harness adapter's (``HarnessAdapter.model_identity``, which every adapter inherits unless its harness names
models differently): every place that resolves a profile's model reaches it there, never by splitting text itself.

OpenCode lists and prints a model as ``provider/model`` (``openai/gpt-x``; a routing provider's model may itself
contain ``/``: ``router/vendor/model``). AEW pins a provider and a model apart, and OpenCode's session takes them apart
(``Model.Ref``: ``providerID`` and ``id``). So an id typed exactly as OpenCode printed it, under its own provider,
became ``openai/openai/gpt-x`` (found by the M4 user acceptance test). This module is the only place that splits or
joins them:

* ``provider: p, model: p/m``: the provider's own prefix is removed, silently; the pair is ``(p, m)``;
* no ``provider``, ``model: p/m``: the provider is taken from the prefix; the pair is ``(p, m)``;
* ``provider: p, model: m`` (no ``/``): the pair is ``(p, m)``, as before;
* ``provider: p, model: q/m`` with ``q`` not ``p``: refused, naming the field, the value and the ids it could mean.
  AEW cannot tell from the text alone whether ``q/m`` is another provider's id or a model of ``p`` whose own id
  contains ``/``, so it never guesses: the full listed id (``p/q/m``) is always accepted.

A provider's own catalog (``GET /v1/models``) lists bare ids, which are never stripped: :func:`from_catalog`. Each
result carries the raw catalog identity, AEW's pair, and the harness reference, so a chooser (register F46.3) fills
the id from the catalog and never prefixes or strips anything itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from aew.errors import ValidationFailed

SEP = "/"


@dataclass(frozen=True)
class ModelIdentity:
    """A model as listed (``catalog_id``), as AEW pins it (``provider``, ``model``), and as OpenCode names it."""

    catalog_id: str
    provider: str
    model: str

    @property
    def harness_ref(self) -> str:
        return f"{self.provider}{SEP}{self.model}"

    def as_dict(self) -> dict[str, str]:
        return {"catalog_id": self.catalog_id, "provider": self.provider, "model": self.model,
                "harness_ref": self.harness_ref}


class ModelIdRefused(ValidationFailed):
    """A model id that does not map to one provider/model pair; ``details`` name the ``field``, the ``value`` and
    the ``suggestions`` (the ids the operator may have meant)."""


def _bad(text: str) -> bool:
    return not text or any(c.isspace() for c in text)


def from_profile(provider: str | None, model: str, *, field: str = "model") -> ModelIdentity:
    """The identity of a profile's ``provider`` and ``model`` as typed (``field`` names the model's field in the
    message: ``profiles.standard.model``, ``--model``)."""
    raw = str(model)
    head, sep, rest = raw.partition(SEP)
    if _bad(raw) or (sep and (not head or not rest)):
        raise ModelIdRefused(f"{field}: {raw!r} is not a model id: write it exactly as the harness lists it "
                             "(provider/model, for example vendor/model-name)", reason="model_id_malformed",
                             field=field, value=raw)
    if provider is None or provider == "":
        if not sep:
            raise ModelIdRefused(f"{field}: {raw!r} names no provider: write the id exactly as the harness lists it "
                                 f"(provider/{raw}), or set the profile's provider", reason="model_id_no_provider",
                                 field=field, value=raw)
        return ModelIdentity(raw, head, rest)
    provider = str(provider)
    if not sep:
        return ModelIdentity(raw, provider, raw)
    if head == provider:
        return ModelIdentity(raw, provider, rest)
    suggestions = [f"{head}{SEP}{rest}", f"{provider}{SEP}{raw}"]
    raise ModelIdRefused(
        f"{field}: {raw!r} carries the provider prefix {head!r}, but the profile's provider is {provider!r}. Did you "
        f"mean {suggestions[0]} (provider {head}, as the harness lists it)? If the harness lists the model as "
        f"{suggestions[1]}, write that id. Either way, the simplest form is the id exactly as the harness prints it, "
        "with no separate provider", reason="model_id_provider_conflict", field=field, value=raw, provider=provider,
        suggestions=suggestions)


def from_listing(listed: str) -> ModelIdentity:
    """An id as OpenCode lists or prints it (``provider/model``)."""
    return from_profile(None, listed, field="listed id")


def from_catalog(provider: str, listed: str) -> ModelIdentity:
    """An id as a provider's own catalog lists it (``GET /v1/models``): bare, under that provider, never stripped,
    even when it contains ``/`` (a routing provider's ``vendor/model``)."""
    if _bad(str(provider)) or SEP in str(provider) or _bad(str(listed)):
        raise ModelIdRefused(f"catalog entry {provider!r}/{listed!r} is not a provider and a model id",
                             reason="model_id_malformed", field="catalog", value=str(listed))
    return ModelIdentity(str(listed), str(provider), str(listed))
