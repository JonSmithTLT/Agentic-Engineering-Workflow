"""The run-usage record, ``aew/run-usage/v1``: one bounded, normalized object per harness run (F25, the cost and
usage ledger design v0.2 §5.1 to §5.3, ledger CUL).

The adapter normalizes, the supervisor records, the engine copies (R2). Every harness adapter builds its record with
:func:`normalize` from its own raw snapshot, so a second adapter fills the same shape. Nothing here is a dollar figure
AEW computed: ``provider_cost_usd`` is the provider's own number, labelled by ``provider_cost_trust`` (R3), and the
derived cost is computed at read time by ``engine/usage_ops.py`` (R4), never stored.

``token_semantics`` is the adapter's declaration of how the reported counters overlap (R4 rule 1). It is chosen per
provider from a mapping pinned to the qualified harness version by the harness conformance tests; a version or a
provider the mapping does not name is ``unknown``, never a guess, and ``unknown`` is never priced.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA = "aew/run-usage/v1"

# The closed enumeration of how a harness's reported counters overlap (R4 rule 1). New semantics are a schema
# addition with a conformance fixture, never a formula in policy.
DISJOINT = "disjoint"
INPUT_INCLUDES_CACHE_READ = "input_includes_cache_read"
INPUT_INCLUDES_CACHE_READ_OUTPUT_INCLUDES_REASONING = "input_includes_cache_read_output_includes_reasoning"
OUTPUT_INCLUDES_REASONING = "output_includes_reasoning"
UNKNOWN = "unknown"
TOKEN_SEMANTICS = (DISJOINT, INPUT_INCLUDES_CACHE_READ, INPUT_INCLUDES_CACHE_READ_OUTPUT_INCLUDES_REASONING,
                   OUTPUT_INCLUDES_REASONING, UNKNOWN)

# The categories AEW names (R1); anything else a harness reports is summed into ``unknown``.
NAMED: tuple[str, ...] = ("input", "output", "reasoning", "cache_read", "cache_write")
CATEGORIES: tuple[str, ...] = (*NAMED, "unknown")

TOKENS_TRUST = ("harness_reported", "partial", "absent")
PROVIDER_COST_TRUST = ("reported", "zero_with_tokens", "absent")
MODEL_CHECK = ("match", "mismatch", "effort_unreported", "no_model_step", "unreported")

# "The bound is a number, not an adjective" (R1): at most 2 KiB serialized, at most 8 distinct effective entries.
# The string lengths below and the caps make the bound a consequence of the schema (``run-usage.schema.json`` holds
# the same numbers; tests/unit/test_usage_record.py checks the worst case against MAX_BYTES).
MAX_BYTES = 2048
MAX_EFFECTIVE = 8
MAX_PROVIDER = 24
MAX_MODEL = 48
MAX_EFFORT = 12
MAX_SOURCE = 32          # "harness:<adapter name>"
MAX_TOKENS = 10**13 - 1      # per category; a larger counter is not a counter AEW believes (treated as unreported)
MAX_COUNT = 10**7 - 1        # steps, foreign sessions, effective_truncated
MAX_WALL_S = 10.0**7
MAX_COST_USD = 10.0**7


def serialized_size(record: Mapping[str, Any]) -> int:
    """The bytes the bound counts: compact, key-sorted JSON (the representation is fixed so the bound is too)."""
    return len(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def identifier(value: Any, limit: int) -> str | None:
    """An identifier within its bound, or None: an over-long or non-string id is not shortened (a shortened model id
    could name another model's price row); it becomes unknown, which prices nothing.

    The bound is in serialized bytes (UTF-8, JSON-escaped), the unit MAX_BYTES counts: a limit in characters let a
    non-ASCII id take up to four times its share, and the record past 2 KiB (#133 review, finding 2)."""
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return None
    try:
        size = len(json.dumps(value, ensure_ascii=False).encode("utf-8")) - 2
    except UnicodeEncodeError:  # a lone surrogate (JSON "\ud800") has no UTF-8 form: unknown, never a failed result
        return None
    return value if size <= limit else None


def _count(value: Any, limit: int = MAX_TOKENS) -> int | None:
    """A non-negative integral counter, or None when the value is not one (bool, negative, non-finite, too large)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or value != int(value)):
        return None
    out = int(value)
    return out if 0 <= out <= limit else None


def _flatten(tokens: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """``{"cache": {"read": 1}}`` -> ``{"cache_read": 1}``: a harness's nested counters under AEW's flat names."""
    out: dict[str, Any] = {}
    for key, value in tokens.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out.update(_flatten(value, f"{name}_"))
        else:
            out[name] = value
    return out


def _wall(wall_s: float | None) -> float | None:
    return None if wall_s is None else round(min(max(float(wall_s), 0.0), MAX_WALL_S), 1)


def normalize_tokens(raw: Any) -> tuple[dict[str, int], str]:
    """A harness's reported counters as AEW's six categories, with ``tokens_trust`` (R1, R3).

    ``harness_reported`` when every named category was reported, ``partial`` when some counter was, ``absent`` when
    none. A category not reported is ``0`` (and the trust says so); a counter AEW does not name is summed into
    ``unknown``."""
    tokens: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    if not isinstance(raw, Mapping):
        return tokens, "absent"
    seen: set[str] = set()
    for name, value in _flatten(raw).items():
        n = _count(value)
        if n is None:
            continue
        if name in NAMED:
            tokens[name] = n
            seen.add(name)
        else:
            tokens["unknown"] = min(tokens["unknown"] + n, MAX_TOKENS)
            seen.add("unknown")
    trust = "absent" if not seen else "harness_reported" if set(NAMED) <= seen else "partial"
    return tokens, trust


def provider_cost(raw: Any, tokens: Mapping[str, int]) -> tuple[float | None, str]:
    """The provider's reported cost and its trust (R3): ``zero_with_tokens`` when it is ``0`` against non-zero tokens
    (the subscription-login case: that number is not a price)."""
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw) \
            or not 0 <= raw <= MAX_COST_USD:
        return None, "absent"
    usd = round(float(raw), 9)
    if usd == 0 and any(tokens.values()):
        return usd, "zero_with_tokens"
    return usd, "reported"


def bound_effective(effective: Iterable[Any]) -> tuple[list[dict[str, Any]], int]:
    """The supervisor's effective list as it stands, capped at 8 distinct entries; the excess counted (R1)."""
    out: list[dict[str, Any]] = []
    extra = 0
    for e in effective:
        if not isinstance(e, Mapping):
            continue
        entry: dict[str, Any] = {"provider": identifier(e.get("provider"), MAX_PROVIDER),
                                 "model": identifier(e.get("model"), MAX_MODEL),
                                 "effort": identifier(e.get("effort"), MAX_EFFORT)}
        # R1's entries are {provider, model, effort}: whether an effort went unreported is the run record's
        # ``model_check`` (its status word is copied beside the record), not a per-entry flag here.
        if entry in out:
            continue
        if len(out) < MAX_EFFECTIVE:
            out.append(entry)
        else:
            extra += 1
    return out, min(extra, MAX_COUNT)


def _partitions(tokens_by_model: Any) -> list[dict[str, Any]] | None:
    if not isinstance(tokens_by_model, Iterable) or isinstance(tokens_by_model, str | bytes | Mapping):
        return None
    out: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for p in tokens_by_model:
        if not isinstance(p, Mapping):
            return None
        tokens, trust = normalize_tokens(p.get("tokens"))
        if trust != "harness_reported":  # a partial partition's zeros are not counts: it is no partition (#133, 2)
            return None
        key = (identifier(p.get("provider"), MAX_PROVIDER), identifier(p.get("model"), MAX_MODEL))
        # One partition per model: a harness that reports a model twice has its counters summed, so the record
        # never holds two rows a projection would have to reconcile (#133 review, finding 1).
        if key in out:
            for cat, n in tokens.items():
                out[key]["tokens"][cat] += n
                if out[key]["tokens"][cat] > MAX_TOKENS:  # capping would hide a mismatch with the totals: no partition
                    return None
        else:
            out[key] = {"provider": key[0], "model": key[1], "tokens": tokens}
    # A partition that cannot be bounded is no partition: the run is then priced as a model mix would be (unpriced).
    return list(out.values()) if 0 < len(out) <= MAX_EFFECTIVE else None


def resolve_semantics(mapping: Mapping[str, Mapping[str, str]], version: Any, providers: Iterable[Any]) -> str:
    """The declared semantics for the providers a run used, under the harness version that ran (R4 rule 1).

    ``mapping`` is ``{harness version: {provider: semantics}}``, pinned by the conformance tests. A version or a
    provider it does not name is ``unknown``; providers that disagree are ``unknown`` too (one record carries one
    declaration)."""
    table = mapping.get(str(version)) if version is not None else None
    found = {(table or {}).get(p, UNKNOWN) if isinstance(p, str) else UNKNOWN for p in providers}
    if len(found) != 1:
        return UNKNOWN
    (only,) = found
    return only if only in TOKEN_SEMANTICS else UNKNOWN


# The fields a usage copy (R5, slice 2) adds, at their longest: a record the adapter builds is measured with them,
# so it stays within MAX_BYTES once copied.
MAX_RUN_ID = 32
MAX_PROFILE = 32
LONGEST_COPY_FIELDS: dict[str, Any] = {
    "run": "R" * MAX_RUN_ID, "recorded_at": "2026-10-05T12:00:00Z", "status": "ended_without_evidence",
    "requested": {"provider": "p" * MAX_PROVIDER, "model": "m" * MAX_MODEL, "effort": "e" * MAX_EFFORT,
                  "profile": "q" * MAX_PROFILE},
    "model_check": "effort_unreported", "pricing_sha256": "0" * 64}


def normalize(raw_usage: Any, raw_assistant: Any, effective: Iterable[Any], semantics: str, *, source: str,
              truncated: bool = False, foreign_sessions: int = 0, tokens_by_model: Any = None,
              wall_s: float | None = None) -> dict[str, Any]:
    """The adapter's ``usage_record`` (R2): R1's record minus what the supervisor and the engine add (``run``,
    ``recorded_at``, ``status``, ``requested``, ``model_check``).

    ``raw_usage`` is the harness's session totals (``{"tokens": {...}, "cost": n}``); when it carries no counters,
    the per-step ``tokens`` of ``raw_assistant`` are summed instead. ``raw_assistant`` is the run's model calls (its
    length is ``steps``). ``truncated`` says the adapter stopped paging those calls before the end."""
    usage = raw_usage if isinstance(raw_usage, Mapping) else {}
    steps = [m for m in raw_assistant or [] if isinstance(m, Mapping)] if isinstance(raw_assistant, Iterable) else []
    tokens, trust = normalize_tokens(usage.get("tokens"))
    if trust == "absent" and steps:
        summed: dict[str, int] = {}
        trusts = set()
        for m in steps:
            t, tr = normalize_tokens(m.get("tokens"))
            trusts.add(tr)
            for k, v in t.items():
                summed[k] = min(summed.get(k, 0) + v, MAX_TOKENS)
        if trusts - {"absent"}:
            tokens = summed
            # A step without counters, or a truncated page, leaves the sum short of the run's usage.
            trust = "harness_reported" if trusts == {"harness_reported"} and not truncated else "partial"
    usd, cost_trust = provider_cost(usage.get("cost"), tokens)
    bounded, extra = bound_effective(effective)
    record: dict[str, Any] = {
        "schema": SCHEMA, "source": identifier(source, MAX_SOURCE) or UNKNOWN, "effective": bounded,
        "effective_truncated": extra, "tokens_by_model": None,
        "token_semantics": semantics if semantics in TOKEN_SEMANTICS else UNKNOWN, "wall_s": _wall(wall_s),
        "steps": min(len(steps), MAX_COUNT), "tokens": tokens, "tokens_trust": trust,
        "provider_cost_usd": usd, "provider_cost_trust": cost_trust,
        "foreign_sessions": min(max(int(foreign_sessions), 0), MAX_COUNT), "truncated": bool(truncated)}
    partitions = _partitions(tokens_by_model)
    if partitions is not None:
        with_partitions = {**record, "tokens_by_model": partitions}
        # The partition is optional; the bound is not. A partition that would push the copied record past 2 KiB is
        # dropped, which leaves a multi-model run unpriced (a mix), never mispriced.
        if serialized_size({**with_partitions, **LONGEST_COPY_FIELDS}) <= MAX_BYTES:
            record = with_partitions
    return record


def absent_record(*, source: str) -> dict[str, Any]:
    """The record for a run that reported nothing: counted as a run with unknown usage, never omitted (R5)."""
    return normalize(None, None, (), UNKNOWN, source=source)


def with_wall_time(record: Any, wall_s: float | None) -> Any:
    """The supervisor's one addition to the adapter's record: the run's wall time (R1: started_at to the terminal
    status, which only the supervisor observes). Anything that is not a record is returned unchanged."""
    if not isinstance(record, dict) or record.get("schema") != SCHEMA or wall_s is None:
        return record
    record["wall_s"] = _wall(wall_s)
    return record
