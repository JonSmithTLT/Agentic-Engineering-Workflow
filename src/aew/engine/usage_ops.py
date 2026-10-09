"""The cost and usage ledger's projections (F25, the cost and usage ledger design v0.2 §5.3 to §5.6, ledger CUL).

Usage facts are the run-usage records (``aew/run-usage/v1``, ``aew.harness.usage``). Everything here is computed
from them at read time and never written back (R7): a dollar figure is derived, never a fact (R4), and a total is a
projection, never a stored number. The pieces:

* the price table (``aew/pricing/v1``) and its content-addressed snapshots ``.aew/pricing/<sha256>.yaml``, written on
  the first usage copy under a digest and never rewritten (R4 rule 3);
* the bucket mapping by the record's declared ``token_semantics`` and the derivation (R4 rules 1, 2 and 4): unknown
  semantics, a missing price, an inconsistent counter or an unattributable model is ``unpriced`` with its reason,
  never zero, and the requested model is never used to price a run;
* ``copy_run_usage`` (R5): the idempotent copy of a run's record into ``inv.runs[].usage``. Its three call paths
  (ingestion and cancel, relaunch, archival) and the manifest's ``policy.pricing`` are slice 2 (design §6, §7);
* the projections per run, invocation, unit and project, with both derived figures, the counts and the project
  scope (R6, R7).

Money is ``Decimal`` inside the projections, so a total is exactly the sum of its parts at every level; ``to_json``
turns it into numbers for a surface.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from aew.errors import IntegrityError, ValidationFailed
from aew.harness import contract as K
from aew.harness import runlog
from aew.harness import usage as U
from aew.schemas import validate
from aew.util import create_exclusive, load_yaml, sha256_bytes, utc_now

PRICING_SCHEMA = "aew/pricing/v1"
SNAPSHOT_DIR = "pricing"  # under the AEW root: .aew/pricing/<sha256>.yaml (R4 rule 3)

# Why a figure is unpriced (R4). The first six are named by the design; the rest name the other ways a figure has
# nothing to price, so no unpriced run is ever silently a zero.
UNPRICED_SEMANTICS_UNKNOWN = "unpriced_token_semantics_unknown"
UNPRICED_INCONSISTENT = "unpriced_inconsistent_counters"
UNPRICED_CATEGORY = "unpriced_category"            # reported as "unpriced_category:<bucket>"
UNPRICED_MIX = "unpriced_effective_model_mix"
UNPRICED_MODEL = "unpriced_model"
UNPRICED_NO_TABLE = "unpriced_no_price_table"      # no table in effect (at record: pricing_sha256 is null)
UNPRICED_SNAPSHOT_MISSING = "unpriced_snapshot_missing"  # the snapshot the record names is gone (a doctor FAIL)
UNPRICED_TOKENS_ABSENT = "unpriced_tokens_absent"  # the harness reported no counters
UNPRICED_TOKENS_PARTIAL = "unpriced_tokens_partial"  # some categories unreported: their zeros are not counts
UNPRICED_NOT_RECORDED = "unpriced_not_recorded"    # a provisional row has no record-time snapshot yet (R6)
UNPRICED_USAGE_MISSING = "unpriced_usage_missing"  # neither a copy nor a run directory (R6 `missing`)
# The harness could not enumerate every model call (its message paging stopped short): the models it saw are not
# all the models that ran, so no attribution, and no semantics declared for them, covers the totals (#133 review, 1).
UNPRICED_INCOMPLETE = "unpriced_model_enumeration_incomplete"
# Per-model partitions that do not add up to the run's totals: pricing them would drop the difference (#133 review, 2).
UNPRICED_PARTITION_MISMATCH = "unpriced_partition_mismatch"

# How each declared semantics maps the reported counters onto non-overlapping billable buckets (R4 rule 1): the
# counter a bucket is carved out of. A counter that includes another bills only the difference, and a difference
# below zero is an inconsistent record, priced as nothing. Reasoning inside output is billed as output.
_INCLUDED: dict[str, dict[str, str]] = {
    U.DISJOINT: {},
    U.INPUT_INCLUDES_CACHE_READ: {"cache_read": "input"},
    U.OUTPUT_INCLUDES_REASONING: {"reasoning": "output"},
    U.INPUT_INCLUDES_CACHE_READ_OUTPUT_INCLUDES_REASONING: {"cache_read": "input", "reasoning": "output"},
}
_BILLED_INSIDE = {"reasoning"}  # included in its container and billed at the container's price, not on its own


# --------------------------------------------------------------------------- the price table and its snapshots


class Prices:
    """One price table: its exact bytes' digest and its parsed rows."""

    def __init__(self, raw: bytes, *, source: str) -> None:
        table = load_yaml(raw.decode("utf-8"), source=source)
        if isinstance(table, dict) and isinstance(table.get("as_of"), date):  # YAML reads `as_of: 2026-10-01` as a date
            table["as_of"] = table["as_of"].isoformat()
        validate("pricing", table, source=source)
        self.sha256 = sha256_bytes(raw)
        self.raw = raw
        self.table: dict[str, Any] = table

    def row(self, provider: Any, model: Any) -> dict[str, Any] | None:
        if not isinstance(provider, str) or not isinstance(model, str):
            return None
        return self.table["prices"].get(f"{provider}/{model}")


def read_price_table(path: Path) -> Prices | None:
    """The table at ``path``, or None when there is none (no derived cost: every surface says unpriced). A malformed
    table is refused (``VALIDATION_FAILED``), never read as an empty one."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        return Prices(raw, source=str(path))
    except UnicodeDecodeError as exc:
        raise ValidationFailed(f"{path}: the price table is not UTF-8 text", reason="pricing_not_text") from exc


def snapshot_path(aew_root: Path, sha: str) -> Path:
    return aew_root / SNAPSHOT_DIR / f"{sha}.yaml"


def write_pricing_snapshot(aew_root: Path, prices: Prices) -> str:
    """The table's exact bytes at ``.aew/pricing/<sha256>.yaml``, written once and never rewritten (R4 rule 3).

    An existing snapshot is left as it is when its bytes match its name; one that does not match is damage and is
    refused, never repaired by overwriting (``aew doctor`` reports it)."""
    path = snapshot_path(aew_root, prices.sha256)
    if path.exists():
        if sha256_bytes(path.read_bytes()) != prices.sha256:
            raise IntegrityError(f"the pricing snapshot {path.name} does not match its digest",
                                 reason="pricing_snapshot_mismatch", sha256=prices.sha256)
        return prices.sha256
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        create_exclusive(path, prices.raw)
    except IntegrityError:  # a concurrent writer published the same bytes first: content-addressed, so equal
        if sha256_bytes(path.read_bytes()) != prices.sha256:
            raise
    return prices.sha256


def read_pricing_snapshot(aew_root: Path, sha: str) -> Prices | None:
    """The snapshot a record names, or None when it is absent or does not match its digest."""
    path = snapshot_path(aew_root, sha)
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if sha256_bytes(raw) != sha:
        return None
    try:
        return Prices(raw, source=str(path))
    except (ValidationFailed, UnicodeDecodeError):
        return None


def named_snapshots(state: Mapping[str, Any], archived: Iterable[Mapping[str, Any]] = ()) -> set[str]:
    """Every pricing digest a copied usage record names, in the hot state and in the given archived bundles."""
    found: set[str] = set()
    for invocations in [state.get("invocations") or {}, *((b.get("invocations") or {}) for b in archived)]:
        for inv in invocations.values():
            for run in inv.get("runs") or []:
                sha = (run.get("usage") or {}).get("pricing_sha256")
                if isinstance(sha, str):
                    found.add(sha)
    return found


def pricing_doctor(manifest: Mapping[str, Any], read: Callable[[], Prices | None]) -> tuple[str, str]:
    """``aew doctor``'s ``policy:pricing`` (R4): no table is reported, never failed (the design's INFO: every derived
    cost is unpriced); a named table that cannot be read from its pinned bytes, or does not validate, is a FAIL."""
    rel = (manifest.get("policy") or {}).get("pricing")
    if rel is None:
        return "PASS", f"INFO: no price table; every derived cost is unpriced ({UNPRICED_NO_TABLE})"
    try:
        prices = read()
    except Exception as exc:  # the doctor reports; it never stops at the first problem
        return "FAIL", f"the price table {rel} cannot be used: {getattr(exc, 'code', type(exc).__name__)}: {exc}"
    if prices is None:
        return "FAIL", f"the price table {rel} is named but not in force"
    return "PASS", (f"{rel}: {len(prices.table['prices'])} price row(s) as of {prices.table['as_of']}, "
                    f"sha256 {prices.sha256[:12]}")


def snapshot_doctor(state: Mapping[str, Any], aew_root: Path,
                    archived: Iterable[Mapping[str, Any]] = ()) -> tuple[str, str]:
    """``aew doctor``'s ``pricing-snapshots`` (R4 rule 3: an ERROR, the repository's ``FAIL``): every snapshot a record
    names (in the hot state and the given archived bundles: the doctor passes the recent ring, a bounded read) is
    present and matches its digest, and every file in the snapshot directory is a snapshot of its own name. The second
    catches damage no record names: a copy that met a damaged snapshot records no table (``pricing_sha256: null``)."""
    bad = sorted(sha for sha in named_snapshots(state, archived) if read_pricing_snapshot(aew_root, sha) is None)
    stray = sorted(p.name for p in _snapshot_files(aew_root)
                   if not (p.name.endswith(".yaml") and read_pricing_snapshot(aew_root, p.name[:-5]) is not None))
    if bad or stray:
        parts = []
        if bad:
            parts.append(f"pricing snapshot(s) named by recorded usage are missing or damaged: {', '.join(bad)}; "
                         f"their runs' estimated_at_record is unpriced ({UNPRICED_SNAPSHOT_MISSING})")
        if stray:
            parts.append(f"file(s) in {SNAPSHOT_DIR}/ that are not the snapshot their name says: {', '.join(stray)}")
        return "FAIL", "; ".join(parts)
    return "PASS", ("every pricing snapshot named by recorded usage (hot state and recently archived units) is "
                    "present and matches its digest")


def _snapshot_files(aew_root: Path) -> list[Path]:
    directory = aew_root / SNAPSHOT_DIR
    return sorted(p for p in directory.iterdir() if p.is_file()) if directory.is_dir() else []


def ledger_doctor(state: Mapping[str, Any], reader: Reader) -> tuple[str, str]:
    """``aew doctor``'s ``usage-ledger`` (R6): how many hot runs are recorded, still provisional (in their run
    directory, awaiting their copy), or missing (neither: their usage is lost). Reads a run directory only for an
    uncopied run."""
    counts = {"recorded": 0, "provisional": 0, "missing": 0}
    for inv_id, inv in (state.get("invocations") or {}).items():
        for entry in inv.get("runs") or []:
            counts[reader.run_row(entry, inv_id)["state"]] += 1
    detail = (f"{counts['recorded']} hot run(s) recorded, {counts['provisional']} provisional (awaiting their copy), "
              f"{counts['missing']} missing")
    if counts["missing"]:
        return "WARN", detail + ": a missing run's usage is lost (no copy and no run directory); totals count it " \
                                "as missing, never as zero"
    return "PASS", detail


# --------------------------------------------------------------------------- the derivation (R4)


def billable_buckets(tokens: Mapping[str, int], semantics: str) -> dict[str, int] | str:
    """The reported counters as non-overlapping billable buckets under the declared semantics, or the unpriced
    reason (``unknown`` semantics, or a bucket that would go negative)."""
    included = _INCLUDED.get(semantics)
    if included is None:
        return UNPRICED_SEMANTICS_UNKNOWN
    buckets = {c: int(tokens.get(c) or 0) for c in U.CATEGORIES}
    for part, container in included.items():
        if buckets[part] > buckets[container]:
            return UNPRICED_INCONSISTENT
        if part in _BILLED_INSIDE:
            buckets[part] = 0
        else:
            buckets[container] -= buckets[part]
    return buckets


def _price(buckets: Mapping[str, int], row: Mapping[str, Any]) -> Decimal | str:
    total = Decimal(0)
    for bucket, count in buckets.items():
        if not count:
            continue  # a zero count in an unpriced bucket is fine (R4 rule 2)
        if bucket not in row:
            return f"{UNPRICED_CATEGORY}:{bucket}"
        total += Decimal(count) * Decimal(str(row[bucket]))
    return total.scaleb(-6)  # prices are per million tokens


def _model_key(provider: Any, model: Any) -> str | None:
    return f"{provider}/{model}" if isinstance(provider, str) and isinstance(model, str) else None


def _pieces(record: Mapping[str, Any]) -> list[tuple[Any, Any, Mapping[str, int]]] | str:
    """What is priced on which row (R4 rule 4): each partition on its own row; otherwise the whole run on its one
    effective model; otherwise unpriced. The requested model is never consulted."""
    if record.get("truncated"):
        return UNPRICED_INCOMPLETE
    partitions = record.get("tokens_by_model")
    if partitions:
        totals = record.get("tokens") or {}
        for category in totals.keys() | {c for p in partitions for c in (p.get("tokens") or {})}:
            if sum(int((p.get("tokens") or {}).get(category) or 0) for p in partitions) != int(
                    totals.get(category) or 0):
                return UNPRICED_PARTITION_MISMATCH
        # The schema cannot say "one partition per model", so a repeated model is summed here as normalize() sums it:
        # each model is priced once, on its whole count (#133 review, finding 1).
        # Merged on the price-row key, not the pair: ("a/b", "c") and ("a", "b/c") are both row "a/b/c".
        merged: dict[Any, tuple[Any, Any, dict[str, int]]] = {}
        for p in partitions:
            provider, model = p.get("provider"), p.get("model")
            key = _model_key(provider, model) or (provider, model)
            tokens = merged.setdefault(key, (provider, model, {}))[2]
            for category, n in (p.get("tokens") or {}).items():
                tokens[category] = tokens.get(category, 0) + int(n or 0)
        return list(merged.values())
    models = {(e.get("provider"), e.get("model")) for e in record.get("effective") or []}
    if len(models) > 1 or record.get("effective_truncated"):
        return UNPRICED_MIX
    if not models:
        return UNPRICED_MODEL
    (provider, model), = models
    return [(provider, model, record.get("tokens") or {})]


def derive(record: Mapping[str, Any], prices: Prices | None) -> tuple[dict[str, Any], list[tuple[str, Decimal]]]:
    """A run's derived cost under one table: ``{"usd": Decimal}`` or ``{"unpriced": reason}``, and the priced parts
    per ``provider/model`` (one part, or one per partition)."""
    if prices is None:
        return {"unpriced": UNPRICED_NO_TABLE}, []
    if record.get("tokens_trust") == "absent":
        return {"unpriced": UNPRICED_TOKENS_ABSENT}, []
    semantics = record.get("token_semantics")
    if semantics not in _INCLUDED:  # `unknown`, or anything the enumeration does not hold: fail closed
        return {"unpriced": UNPRICED_SEMANTICS_UNKNOWN}, []
    if record.get("tokens_trust") != "harness_reported":
        return {"unpriced": UNPRICED_TOKENS_PARTIAL}, []
    pieces = _pieces(record)
    if isinstance(pieces, str):
        return {"unpriced": pieces}, []
    parts: list[tuple[str, Decimal]] = []
    for provider, model, tokens in pieces:
        buckets = billable_buckets(tokens, semantics)
        if isinstance(buckets, str):
            return {"unpriced": buckets}, []
        row = prices.row(provider, model)
        key = _model_key(provider, model)
        if row is None or key is None:
            return {"unpriced": UNPRICED_MODEL}, []
        usd = _price(buckets, row)
        if isinstance(usd, str):
            return {"unpriced": usd}, []
        parts.append((key, usd))
    return {"usd": sum((usd for _, usd in parts), Decimal(0))}, parts


# --------------------------------------------------------------------------- the copy (R5; called from slice 2)


# The run statuses a copy may record (the run-usage schema's ``status``): the harness's own, and ``lost``.
RUN_STATUSES = frozenset({*K.TERMINAL, K.STARTING, K.RUNNING, K.UNCONFIRMED, K.LOST})


def _valid_record(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict) or candidate.get("schema") != U.SCHEMA:
        return None
    try:
        validate("run-usage", candidate, source="usage_record")
        U.serialized_size(candidate)  # a lone surrogate passes the schema but has no UTF-8 form (#133 review, 812943d)
        # NaN passes every schema bound (each comparison with it is false) and is not JSON: a copy goes into the
        # control state and the archive bundle, so a non-finite number is no record (#137 re-review, F2).
        json.dumps(candidate, allow_nan=False)
    except (ValidationFailed, UnicodeEncodeError, ValueError):
        return None
    return dict(candidate)


def copy_run_usage(state: dict[str, Any], inv_id: str, aew_root: Path, *, pricing: Prices | None,
                   now: str | None = None, final: bool = True) -> list[str]:
    """Copy each run's usage of one invocation into ``inv.runs[i].usage``, once (R5). Returns the runs copied.

    The run record is read once; its ``result.usage_record`` is taken when it is a well-formed bounded record, and
    otherwise the run is recorded with absent usage, so a run that crashed before reporting is counted, never
    omitted. A run whose usage is present is never rewritten. ``pricing`` is the table in effect now (the manifest's
    ``policy.pricing``, resolved by the caller): its digest is recorded and its snapshot written on first use.

    ``final=False`` (a transaction that ends or relaunches an invocation) copies only runs that have ended: a run
    still starting or running has not reported its usage yet, and a copy now would fix it as absent for ever. It
    stays ``provisional`` (R6) until a later transaction on the invocation, and at the latest the unit's archival,
    which copies every run (``final=True``): the bundle has a record for every run, a run still live then with its
    observed status and absent usage."""
    inv = state["invocations"][inv_id]
    pending = [r for r in inv.get("runs") or [] if "usage" not in r]
    if not pending:
        return []
    observed = [(entry, *runlog.observed_status(runlog.run_dir(aew_root, entry["run"]))) for entry in pending]
    if not final:
        observed = [o for o in observed if o[1] in K.TERMINAL]
    if not observed:
        return []
    sha = None
    if pricing is not None:
        try:
            sha = write_pricing_snapshot(aew_root, pricing)
        except (IntegrityError, OSError):  # a damaged or unwritable snapshot never fails a cancel (#137 review, F4)
            sha = None
    profile = inv.get("execution_profile") or {}
    # Requested ids are bounded as the adapter bounds effective ones: an id past its bound is unknown, so the copy
    # fits in 2 KiB without discarding the run's counters (#133 review, finding 2).
    requested = {"provider": U.identifier(profile.get("provider"), U.MAX_PROVIDER),
                 "model": U.identifier(profile.get("model"), U.MAX_MODEL),
                 "effort": U.identifier(profile.get("effort"), U.MAX_EFFORT),
                 "profile": U.identifier(profile.get("profile"), U.MAX_PROFILE)}
    copied: list[str] = []
    for entry, status, run_record in observed:
        # The run record is the run's own report, written where the run's user can write: every field is checked
        # before it is copied, and a status the record schema does not know is a run that stopped reporting (#137
        # review, F1 and F2: a copy goes into the archive bundle, which commit validation does not see).
        status = status if status in RUN_STATUSES else K.LOST
        result = (run_record or {}).get("result")
        record = _valid_record(result.get("usage_record") if isinstance(result, dict) else None) \
            or U.absent_record(source=f"harness:{entry.get('harness') or U.UNKNOWN}")
        model_check = (run_record or {}).get("model_check")
        check = model_check.get("status") if isinstance(model_check, dict) else None
        record.update(run=entry["run"], recorded_at=now or utc_now(), status=status, requested=requested,
                      model_check=check if check in U.MODEL_CHECK else "unreported", pricing_sha256=sha)
        if _valid_record(record) is None or U.serialized_size(record) > U.MAX_BYTES:
            # A local record that is well formed alone but does not fit once copied (a requested id past its
            # bound, say) is kept as a run with unknown usage: the bound holds whatever local/ held.
            record = {**U.absent_record(source=f"harness:{entry.get('harness') or U.UNKNOWN}"),
                      "run": entry["run"], "recorded_at": record["recorded_at"], "status": status,
                      "requested": {k: None for k in requested}, "model_check": "unreported", "pricing_sha256": sha}
        if _valid_record(record) is None:  # unreachable while every field above is checked; never archived unchecked
            raise IntegrityError(f"the usage copy for {entry['run']} is not a run-usage record",
                                 reason="usage_copy_invalid", run=entry["run"])
        entry["usage"] = record
        copied.append(entry["run"])
    return copied


class UsageCopy:
    """The usage copy as a Lead transaction's finalizer (see ``finalize``)."""

    def __init__(self, aew_root: Path, pricing: Callable[[], Prices | None]) -> None:
        self.aew_root, self.pricing = aew_root, pricing

    def finalize(self, ctx: Any) -> None:
        _finalize(ctx, self.aew_root, self.pricing)


def _finalize(ctx: Any, aew_root: Path, pricing: Callable[[], Prices | None]) -> None:
    """The usage copy as a Lead transaction's finalizer (R5), run before archival so a bundle carries what it copied.

    R5 names the transactions that copy: evidence ingestion, ``invoke cancel``, a relaunch, and archival. Each is a
    Lead transaction that ends an invocation, adds a run to it, or archives its unit, so the finalizer copies for
    every invocation whose status or run list this transaction changed (``final=False``: ended runs only) and for
    every invocation of a unit this commit archives (``final=True``). Covering the transaction rather than each
    handler means no ingestion path (Ticket, review, verification, non-mutating, parent) can be missed.

    A copy only adds ``usage`` to an existing run entry, so it derives no event (R5): ``run.added`` compares run ids
    and ``invocation.status`` the status field, and neither changes. ``pricing`` is read once and only when a copy
    happens, from the pinned bytes: a table edited outside AEW has already refused the transaction at its entry, as
    any policy edit does. A table that still cannot be read, or whose snapshot cannot be written or is damaged, records
    the copy with no table (``pricing_sha256: null``) rather than fail a cancel or an archival over a price: the usage
    facts are what is kept.

    A run still live when its unit is archived (a Ticket cancelled while its agent works) is copied with the status
    observed then and absent usage (R5: archival copies every run that still lacks it). What it reports later stays in
    ``local/`` only: the hot state no longer holds the invocation, and the bundle is never rewritten."""
    from aew.engine import hierarchy as H

    state = ctx.state
    if state.get("schema") != "aew/control/v2":
        return
    before = ctx.session.committed_view().get("invocations") or {}
    archiving = {w for w, u in state["work"].items() if u["state"] in H.TERMINAL}
    table: list[Prices | None] = []

    def prices() -> Prices | None:
        if not table:
            try:
                table.append(pricing())
            except (IntegrityError, ValidationFailed, FileNotFoundError, UnicodeDecodeError):
                table.append(None)
        return table[0]

    for inv_id, inv in state["invocations"].items():
        runs = inv.get("runs") or []
        if not runs or all("usage" in r for r in runs):
            continue
        old = before.get(inv_id)
        final = inv.get("work_unit") in archiving
        touched = old is not None and (old.get("status") != inv.get("status")
                                       or [r.get("run") for r in old.get("runs") or []] != [r.get("run") for r in runs])
        if final or touched:
            copy_run_usage(state, inv_id, aew_root, pricing=prices(), final=final)


# --------------------------------------------------------------------------- projections (R6, R7)


def _empty_figure() -> dict[str, Any]:
    return {"usd": Decimal(0), "priced": 0, "unpriced": 0, "reasons": {}}


def empty_totals() -> dict[str, Any]:
    return {"invocations": 0, "invocations_without_runs": 0, "runs": 0, "recorded": 0, "provisional": 0,
            "missing": 0, "tokens": dict.fromkeys(U.CATEGORIES, 0), "wall_s_sum": Decimal(0), "steps": 0,
            "provider_cost": {"reported_usd": Decimal(0), "reported": 0, "zero_with_tokens": 0, "absent": 0},
            "estimated_at_record": _empty_figure(), "estimated_under_current_prices": _empty_figure(),
            "by_model": {}}


def _add_figure(into: dict[str, Any], figure: Mapping[str, Any]) -> None:
    into["usd"] += figure["usd"]
    into["priced"] += figure["priced"]
    into["unpriced"] += figure["unpriced"]
    for reason, n in figure["reasons"].items():
        into["reasons"][reason] = into["reasons"].get(reason, 0) + n


def add_totals(into: dict[str, Any], other: Mapping[str, Any]) -> dict[str, Any]:
    """``into`` += ``other``, field by field (a roll-up is the plain sum of its parts)."""
    for key in ("invocations", "invocations_without_runs", "runs", "recorded", "provisional", "missing",
                "wall_s_sum", "steps"):
        into[key] += other[key]
    for cat in U.CATEGORIES:
        into["tokens"][cat] += other["tokens"][cat]
    for key, value in other["provider_cost"].items():
        into["provider_cost"][key] += value
    for name in ("estimated_at_record", "estimated_under_current_prices"):
        _add_figure(into[name], other[name])
    for key, model in other["by_model"].items():
        mine = into["by_model"].setdefault(key, _empty_model())
        mine["runs"] += model["runs"]
        for name in ("estimated_at_record_usd", "estimated_under_current_prices_usd"):
            mine[name] += model[name]
        for cat in U.CATEGORIES:
            mine["tokens"][cat] += model["tokens"][cat]
    return into


def _empty_model() -> dict[str, Any]:
    return {"runs": 0, "tokens": dict.fromkeys(U.CATEGORIES, 0), "estimated_at_record_usd": Decimal(0),
            "estimated_under_current_prices_usd": Decimal(0)}


class Reader:
    """What one read of the ledger needs: the AEW root (run directories, snapshots), the table in effect now, and a
    run-record reader (the run directory by default). Snapshots are read once per reader."""

    def __init__(self, aew_root: Path, current: Prices | None,
                 read_run: Callable[[str], dict[str, Any] | None] | None = None) -> None:
        self.aew_root = aew_root
        self.current = current
        self._read_run = read_run or (lambda run: runlog.read_record(runlog.run_dir(aew_root, run)))
        self._snapshots: dict[str, Prices | None] = {}

    def snapshot(self, sha: str) -> Prices | None:
        if sha not in self._snapshots:
            self._snapshots[sha] = read_pricing_snapshot(self.aew_root, sha)
        return self._snapshots[sha]

    def run_row(self, entry: Mapping[str, Any], inv_id: str) -> dict[str, Any]:
        """One run: its record and where it came from (R6: ``recorded`` in control state, ``provisional`` from the run
        directory, ``missing`` from neither), both derived figures, and the provider's cost with its trust."""
        record = entry.get("usage")
        if record is not None:
            state = "recorded"
            sha = record.get("pricing_sha256")
            if sha is None:
                at_record: dict[str, Any] = {"unpriced": UNPRICED_NO_TABLE}
                at_parts: list[tuple[str, Decimal]] = []
            else:
                snap = self.snapshot(sha)
                at_record, at_parts = derive(record, snap) if snap is not None else (
                    {"unpriced": UNPRICED_SNAPSHOT_MISSING}, [])
        else:
            run_record = self._read_run(entry["run"])
            if run_record is None:
                return {"run": entry["run"], "invocation": inv_id, "state": "missing", "usage": None,
                        "pricing_sha256": None, "estimated_at_record": {"unpriced": UNPRICED_USAGE_MISSING},
                        "estimated_under_current_prices": {"unpriced": UNPRICED_USAGE_MISSING},
                        "provider_cost": {"usd": None, "trust": "absent"}, "_parts": ([], [])}
            result = run_record.get("result")
            record = _valid_record(result.get("usage_record") if isinstance(result, dict) else None) \
                or U.absent_record(source=f"harness:{entry.get('harness') or U.UNKNOWN}")
            state, sha = "provisional", None
            at_record, at_parts = {"unpriced": UNPRICED_NOT_RECORDED}, []
        current, current_parts = derive(record, self.current)
        return {"run": entry["run"], "invocation": inv_id, "state": state, "usage": record, "pricing_sha256": sha,
                "estimated_at_record": at_record, "estimated_under_current_prices": current,
                "provider_cost": {"usd": record.get("provider_cost_usd"), "trust": record.get("provider_cost_trust")},
                "_parts": (at_parts, current_parts)}

    def invocation(self, inv_id: str, inv: Mapping[str, Any]) -> dict[str, Any]:
        """One invocation: its rows and their sum. An invocation without runs (a custody invocation, or one not yet
        launched) is normal: counted in ``invocations_without_runs`` and nothing else (R7)."""
        rows = [self.run_row(entry, inv_id) for entry in inv.get("runs") or []]
        totals = empty_totals()
        totals["invocations"] = 1
        totals["invocations_without_runs"] = 0 if rows else 1
        for row in rows:
            _count_row(totals, row)
        return {"invocation": inv_id, "work_unit": inv.get("work_unit"), "rows": [_public(r) for r in rows],
                "totals": totals}


def _count_row(totals: dict[str, Any], row: Mapping[str, Any]) -> None:
    totals["runs"] += 1
    totals[row["state"]] += 1
    record = row["usage"]
    trust = row["provider_cost"]["trust"]
    totals["provider_cost"][trust if trust in U.PROVIDER_COST_TRUST else "absent"] += 1
    if trust == "reported":  # never a zero_with_tokens or absent cost (R3)
        totals["provider_cost"]["reported_usd"] += Decimal(str(row["provider_cost"]["usd"]))
    for name in ("estimated_at_record", "estimated_under_current_prices"):
        figure, fig = row[name], totals[name]
        if "usd" in figure:
            fig["usd"] += figure["usd"]
            fig["priced"] += 1
        else:
            fig["unpriced"] += 1
            fig["reasons"][figure["unpriced"]] = fig["reasons"].get(figure["unpriced"], 0) + 1
    if record is None:
        return
    for cat in U.CATEGORIES:
        totals["tokens"][cat] += int(record["tokens"].get(cat) or 0)
    if record.get("wall_s") is not None:
        totals["wall_s_sum"] += Decimal(str(record["wall_s"]))
    totals["steps"] += int(record.get("steps") or 0)
    _count_models(totals["by_model"], row)


def _count_models(by_model: dict[str, Any], row: Mapping[str, Any]) -> None:
    """Per effective model: a single-model run under its model, each partition under its own, a mix under
    ``unpriced_effective_model_mix`` and a run with no effective model under ``no_effective_model``; never under the
    requested model (R7). A partitioned run counts once under each of its models."""
    record = row["usage"]
    pieces = _pieces(record)
    if isinstance(pieces, str):
        key = UNPRICED_MIX if pieces == UNPRICED_MIX else "no_effective_model"
        model = by_model.setdefault(key, _empty_model())
        model["runs"] += 1
        for cat in U.CATEGORIES:
            model["tokens"][cat] += int(record["tokens"].get(cat) or 0)
        return
    at_parts: dict[str, Decimal] = {}  # summed per key: two parts may share one (a projection is a sum, R6)
    current_parts: dict[str, Decimal] = {}
    for acc, parts in zip((at_parts, current_parts), row["_parts"], strict=True):
        for key, usd in parts:
            acc[key] = acc.get(key, Decimal(0)) + usd
    counted: set[str] = set()
    for provider, name, tokens in pieces:
        key = _model_key(provider, name) or "no_effective_model"
        model = by_model.setdefault(key, _empty_model())
        for cat in U.CATEGORIES:
            model["tokens"][cat] += int(tokens.get(cat) or 0)
        if key in counted:  # two unknown-id partitions share "no_effective_model": one run, its cost added once
            continue
        counted.add(key)
        model["runs"] += 1
        model["estimated_at_record_usd"] += at_parts.get(key, Decimal(0))
        model["estimated_under_current_prices_usd"] += current_parts.get(key, Decimal(0))


def _public(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _view(state: Mapping[str, Any], archived: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Work units and invocations from the hot state plus rehydrated archive bundles (``{id, unit, invocations}``)."""
    work = dict(state.get("work") or {})
    invocations = dict(state.get("invocations") or {})
    for bundle in archived:
        work.setdefault(bundle["id"], bundle["unit"])
        for inv_id, inv in (bundle.get("invocations") or {}).items():
            invocations.setdefault(inv_id, inv)
    return work, invocations


def unit_projection(state: Mapping[str, Any], unit_id: str, reader: Reader,
                    archived: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """A unit's tree (R7): its own invocations' totals, its descendants' totals (a Story sums its Tickets, an Epic its
    Stories), each kept separate, and each child's projection."""
    work, invocations = _view(state, archived)
    return _unit(unit_id, work, invocations, reader)


def _unit(unit_id: str, work: Mapping[str, Any], invocations: Mapping[str, Any], reader: Reader) -> dict[str, Any]:
    unit = work.get(unit_id) or {}
    own = empty_totals()
    rendered = []
    for inv_id in sorted(i for i, inv in invocations.items() if inv.get("work_unit") == unit_id):
        projected = reader.invocation(inv_id, invocations[inv_id])
        rendered.append(projected)
        add_totals(own, projected["totals"])
    children = [_unit(c, work, invocations, reader) for c in sorted(w for w, u in work.items()
                                                                     if u.get("parent") == unit_id)]
    descendants = empty_totals()
    for child in children:
        add_totals(descendants, child["own"])
        add_totals(descendants, child["descendants"])
    return {"unit": unit_id, "kind": unit.get("kind"), "own": own, "descendants": descendants,
            "invocations": rendered, "children": children}


def project_projection(state: Mapping[str, Any], reader: Reader, archived: Iterable[Mapping[str, Any]] = (), *,
                       walk_all: bool = False, since: str | None = None, until: str | None = None,
                       archive_complete: bool = False) -> dict[str, Any]:
    """The project's totals over the hot state plus the archived units given (the ``recent`` ring by default, the
    history walk with ``--all``), saying what they cover (R7, the designer's and lead developer's 2026-10-06
    clarification): ``scope: recent`` is never complete; an unbounded walk is ``scope: all``, complete only when the
    caller's walk covered every archived unit; a bounded walk is ``scope: window`` with its bounds, never complete."""
    work, invocations = _view(state, list(archived))
    totals = empty_totals()
    for inv_id in sorted(invocations):
        add_totals(totals, reader.invocation(inv_id, invocations[inv_id])["totals"])
    if not walk_all:
        scope: dict[str, Any] = {"scope": "recent", "archive_complete": False}
    elif since is not None or until is not None:
        scope = {"scope": "window", "archive_complete": False, "since": since, "until": until}
    else:
        scope = {"scope": "all", "archive_complete": bool(archive_complete)}
    return {**scope, "units": len(work), "totals": totals}


def to_json(value: Any) -> Any:
    """A projection as JSON values: money and wall time as numbers."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {k: to_json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_json(v) for v in value]
    return value
