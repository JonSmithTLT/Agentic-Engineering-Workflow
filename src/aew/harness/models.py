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

**An operator-typed reference that is template text is refused** before any launch, naming the field and the
fix: :func:`from_profile` (a profile, ``--model``) refuses a ``provider`` or ``model`` that contains ``<`` or ``>``, or
has ``MODEL_ID`` or ``YOUR_MODEL_ID`` as a whole ``/``-separated segment. The rule is exactly that and no more:
the match is case-sensitive, so other spellings of template text pass (``model_id``, ``your-model-id``, ``$MODEL_ID``,
``{model}``, ``[model]``, ``TODO``), and the configuration projection's own grammar (``engine/configuration.py``,
``MODEL_ID``) is stricter than this rule (review of PR #309, F5). :func:`from_listing` and :func:`from_catalog` take
what the harness or the provider lists and never apply it: a provider's own id is its own.

**What a chooser writes back: ``model: <harness_ref>``, with no separate ``provider``**
(:meth:`ModelIdentity.profile_fields`). Only that form round-trips: ``from_profile(None, x.harness_ref)`` is ``x``'s
pair for every identity ``x`` this module returns, except an id the provider lists that reads as template text
(``vendor/MODEL_ID``): the listing accepts it and the profile rule refuses it (review of PR #309, F3). The split pair
does not round-trip either, for a model whose own id contains ``/``:
``from_catalog("router", "maker/model-b")`` is the pair ``(router, maker/model-b)``, and a profile
``{provider: router, model: maker/model-b}`` is refused as a conflicting prefix (review of PR #214, F3).

**The silent strip has one consequence to know.** ``{provider: p, model: p/m}`` always pins ``(p, m)``. A provider
whose own model id itself begins with ``p/`` (OpenCode prints it ``p/p/m``) is therefore written in full, as OpenCode
prints it: ``model: p/p/m``, for example ``router/router/auto`` (review of PR #214, N1).
"""

from __future__ import annotations

from dataclasses import dataclass

from aew.errors import ValidationFailed

SEP = "/"
# Why a model id maps to no provider/model pair: the `reason` of every ModelIdRefused, and the codes a configuration
# projection reports as `identity_error.code` (register F46.1).
MALFORMED, NO_PROVIDER, PROVIDER_CONFLICT = (
    "model_id_malformed", "model_id_no_provider", "model_id_provider_conflict")
REFUSAL_REASONS = (MALFORMED, NO_PROVIDER, PROVIDER_CONFLICT)
PLACEHOLDER_WORDS = frozenset(("MODEL_ID", "YOUR_MODEL_ID"))


@dataclass(frozen=True)
class ModelIdentity:
    """A model as listed (``catalog_id``), as AEW pins it (``provider``, ``model``), and as OpenCode names it."""

    catalog_id: str
    provider: str
    model: str

    @property
    def harness_ref(self) -> str:
        return f"{self.provider}{SEP}{self.model}"

    def profile_fields(self) -> dict[str, str]:
        """What a profile (or a chooser's save) writes to select this model: the harness reference as ``model`` and no
        ``provider``, the one form that maps back to this same pair whatever the model id contains."""
        return {"model": self.harness_ref}

    def as_dict(self) -> dict[str, str]:
        return {"catalog_id": self.catalog_id, "provider": self.provider, "model": self.model,
                "harness_ref": self.harness_ref}


class ModelIdRefused(ValidationFailed):
    """A model id that does not map to one provider/model pair; ``details`` name the ``field``, the ``value`` and
    the ``suggestions`` (the ids the operator may have meant)."""


def _bad(text: str) -> bool:
    return not text or any(c.isspace() for c in text)


def _is_placeholder(text: str) -> bool:
    return any(char in text for char in "<>") or any(
        part in PLACEHOLDER_WORDS for part in text.split(SEP))


def _placeholder(text: str, field: str, provider: str | None = None, model: str | None = None, *,
                 of_provider: str | None = None) -> ModelIdRefused:
    """The refusal for template text in ``field``; ``of_provider`` is the model's field when ``field`` is the
    provider's, whose next step differs (a full provider/model id there is not a provider, review of PR #309, F1).
    The listing command is OpenCode's, the one harness built in; the field names where the value was typed (F2)."""
    if of_provider is not None:
        step = ("replace it with the provider id alone (the part before the first `/` in `opencode models`), or "
                f"remove `provider` and write the full provider/model ID in {of_provider}")
    else:
        step = ("replace it with a real provider/model ID. Find one with `opencode models`, then write the full "
                f"provider/model ID in {field}")
    return ModelIdRefused(f"{field}: {text!r} is a literal placeholder value; {step}", reason=MALFORMED, field=field,
                          value=text, provider=provider, model=model if model is not None else text)


def from_profile(provider: str | None, model: str, *, field: str = "model") -> ModelIdentity:
    """The identity of a profile's ``provider`` and ``model`` as typed (``field`` names the model's field in the
    message: ``profiles.standard.model``, ``--model``). Template text in either is refused first (see the module
    docstring for exactly what counts); the rest is :func:`_pair`."""
    provider_text = str(provider) if provider is not None else None
    if provider_text is not None and _is_placeholder(provider_text):
        raise _placeholder(provider_text, f"{field.rsplit('.', 1)[0]}.provider" if "." in field else "provider",
                           provider_text, str(model), of_provider=field)
    raw = str(model)
    if _is_placeholder(raw):
        raise _placeholder(raw, field, provider_text, raw)
    return _pair(provider, model, field)


def _pair(provider: str | None, model: str, field: str) -> ModelIdentity:
    """The one parse of a provider and a model as typed or listed: shared by :func:`from_profile` and
    :func:`from_listing`, so the split lives once (review of PR #309, F4)."""
    raw = str(model)
    head, sep, rest = raw.partition(SEP)
    if _bad(raw) or (sep and (not head or not rest)):
        raise ModelIdRefused(f"{field}: {raw!r} is not a model id: write it exactly as the harness lists it "
                             "(provider/model, for example vendor/model-name)", reason=MALFORMED,
                             field=field, value=raw)
    if provider is None or provider == "":
        if not sep:
            raise ModelIdRefused(f"{field}: {raw!r} names no provider: write the id exactly as the harness lists it "
                                 f"(provider/{raw}), or set the profile's provider", reason=NO_PROVIDER,
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
        "with no separate provider", reason=PROVIDER_CONFLICT, field=field, value=raw, provider=provider,
        suggestions=suggestions)


def from_listing(listed: str) -> ModelIdentity:
    """An id as OpenCode lists or prints it (``provider/model``)."""
    return _pair(None, listed, "listed id")


def from_catalog(provider: str, listed: str) -> ModelIdentity:
    """An id as a provider's own catalog lists it (``GET /v1/models``): bare, under that provider, never stripped,
    even when it contains ``/`` (a routing provider's ``vendor/model``)."""
    provider_text, listed_text = str(provider), str(listed)
    if _bad(provider_text) or SEP in provider_text or _bad(listed_text):
        raise ModelIdRefused(f"catalog entry {provider!r}/{listed!r} is not a provider and a model id",
                             reason=MALFORMED, field="catalog", value=str(listed))
    return ModelIdentity(listed_text, provider_text, listed_text)
