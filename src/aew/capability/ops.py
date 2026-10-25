"""The capability register's operations (STG-15, A-38: CAPR-03, CAPR-04, CAPR-05, CAPR-12, CAPR-13).

* :func:`listing`: every capability's status on this host, its provider, its cause and its fix. A read: ``aew
  capability list`` and ``aew doctor`` show it, and need no authorization.
* :func:`check`: fetch what a record pins and this host lacks (online), check every payload against its pin, run the
  health checks and record their results. It writes the checks' results and payloads to an existing pin, never a
  record or a setting, so it changes no authority and needs none.
* The operator's changes, ``import``, ``add``, ``remove`` and ``host-copies``, change what a contained context gets,
  so they are the operator's alone (CAPR-05; the designer's CAP-1 ruling 1): a change is previewed
  (:func:`preview`), shown at the operator endpoint's console, and applied by the endpoint (:func:`apply`) once the
  operator typed its code back. :func:`apply` takes the endpoint's ``OperatorPrincipal``, which only the endpoint
  constructs, and applies exactly what was shown: the bundle bytes the preview read, the record text it validated.
  A change that fails validation changes nothing, and says why (CAPR-13).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.capability import payload as P
from aew.capability import records, status, store
from aew.capability.status import Copy
from aew.errors import AEWError, IntegrityError, NotFound, PermissionDenied, Unavailable, UsageError, ValidationFailed
from aew.util import load_yaml, sha256_text, utc_now

IMPORT, ADD, REMOVE, HOST_COPIES = "import", "add", "remove", "host_copies"
CHANGES = (IMPORT, ADD, REMOVE, HOST_COPIES)
MAX_RECORD_TEXT = 12 * 1024  # an add's record text travels in one operator endpoint request (its MAX_MESSAGE, 16 KiB)


# ---------------------------------------------------------------------------------------------- reading


def listing(directory: Path | None = None) -> dict[str, Any]:
    """Every capability with its status on this host (D-01's ``observed_status``; its ``assessment_status`` stays
    NOT_ESTABLISHED while no qualification record exists), each provider with its copies, and any operator override
    whose shipped record changed under it."""
    try:
        state = store.read(directory)
    except IntegrityError as exc:  # an unreadable register refuses every capability, with its cause
        return _unreadable(exc)
    eff = status.effective(state)
    facts = status.host_facts()
    providers = {name: _provider(name, entry, state, facts, directory) for name, entry in eff.items()}
    caps: dict[str, list[str]] = {}
    for name, entry in eff.items():
        for cap in _capabilities_of(name, entry):
            caps.setdefault(cap, []).append(name)
    capabilities = [_capability(cap, [providers[n] for n in names]) for cap, names in sorted(caps.items())]
    overrides = [{"provider": name, "differences": entry["upgrade"]} for name, entry in eff.items() if entry["upgrade"]]
    return {"root": str(directory or store.root()), "platform": records.platform_key(),
            "host_copies": bool(state["host_copies"]), "capabilities": capabilities,
            "providers": list(providers.values()), "overrides": overrides}


def _capabilities_of(name: str, entry: dict[str, Any]) -> list[str]:
    record = entry["record"] or records.shipped().get(name) or {}
    return [c for c in record.get("capabilities") or [] if isinstance(c, str)]


def _provider(name: str, entry: dict[str, Any], state: dict[str, Any], facts: dict[str, str | None],
              directory: Path | None) -> dict[str, Any]:
    record = entry["record"]
    aew = status.aew_copy(name, record, entry["problem"], state, facts=facts, directory=directory)
    host: Copy | None = None
    note = None
    if record is not None and aew.status in status.NOT_SERVING:
        if state["host_copies"]:
            host = status.host_copy(name, record, state, facts=facts, directory=directory)
        elif (found := status.find_host_copy(record["command"], directory)) is not None:
            note = (f"this host's {found} does not serve: the operator turned host copies off (`aew capability "
                    "host-copies on` turns them on)")
    return {"name": name, "layer": entry["layer"], "command": (record or {}).get("command"),
            "version": (record or {}).get("version"), "aew_copy": aew.describe(),
            "host_copy": host.describe() if host is not None else None, "note": note,
            "serving": host if host is not None else aew, "aew": aew}


def _capability(cap: str, providers: list[dict[str, Any]]) -> dict[str, Any]:
    """CAPR-01: the first provider whose copy is usable serves (one provider per capability in the base bundle); else
    the first provider's state, with its cause."""
    chosen = next((p for p in providers if p["serving"].status in status.USABLE), providers[0])
    serving: Copy = chosen["serving"]
    aew: Copy = chosen["aew"]
    host = serving.kind == status.HOST_COPY
    causes = [f"AEW's copy: {aew.cause}"] if host and aew.cause else []
    if serving.cause:
        causes.append(f"the host's copy: {serving.cause}" if host else serving.cause)
    if chosen["note"]:
        causes.append(chosen["note"])
    return {"id": cap, "observed_status": serving.status, "assessment_status": status.NOT_ESTABLISHED,
            "provider": chosen["name"], "copy": serving.kind, "path": serving.path,
            "version": None if host else chosen["version"], "pinned": not host,
            "cause": "; ".join(causes) or None, "limitations": list(serving.limitations),
            "checked_at": serving.checked_at, "fix": serving.fix or (aew.fix if host else None)}


def _unreadable(exc: IntegrityError) -> dict[str, Any]:
    caps = sorted({c for r in records.shipped().values() for c in r["capabilities"]})
    return {"root": str(store.root()), "platform": records.platform_key(), "host_copies": None,
            "capabilities": [{"id": c, "observed_status": status.REFUSED, "assessment_status": status.NOT_ESTABLISHED,
                              "provider": None, "copy": None, "path": None, "version": None, "pinned": False,
                              "cause": exc.message, "limitations": [], "checked_at": None,
                              "fix": "move the register file aside, then `aew capability check`"} for c in caps],
            "providers": [], "overrides": []}


def public(view: dict[str, Any]) -> dict[str, Any]:
    """A listing as commands print it: the copies' objects dropped."""
    return {**view, "providers": [{k: v for k, v in p.items() if k not in ("serving", "aew")}
                                  for p in view["providers"]]}


def render(view: dict[str, Any]) -> str:
    """``aew capability list`` without ``--json``: one line per capability, then any upgrade differences."""
    lines = [f"capability register: {view['root']} ({view['platform']}; host copies "
             f"{'on' if view['host_copies'] else 'off' if view['host_copies'] is not None else 'unknown'})"]
    for c in view["capabilities"]:
        who = (f"{c['provider']} {c['version']} (AEW's pinned copy)" if c["pinned"] and c["provider"] else
               f"{c['provider']}: the host's {c['path']}, unpinned" if c["provider"] else "no provider")
        lines.append(f"{c['id']:<20} {c['observed_status']:<16} {who}"
                     + (f"; {c['cause']}" if c["cause"] else "")
                     + (f"; checked {c['checked_at']}" if c["checked_at"] else "")
                     + (f"; fix: {c['fix']}" if c["fix"] else ""))
    for o in view["overrides"]:
        lines.append(f"override {o['provider']}: AEW's shipped record changed under it, and the override is kept: "
                     + "; ".join(o["differences"]))
    return "\n".join(lines)


def doctor_checks() -> list[tuple[str, str, str]]:
    """``aew doctor``'s capability lines, read from the same listing (S01-21): PASS where the capability is usable,
    otherwise WARN, never FAIL, since no provider is required for AEW to run (CAPR-12)."""
    view = listing()
    out = []
    for c in view["capabilities"]:
        who = (f"served by {c['provider']} {c['version']}, AEW's pinned copy at {c['path']}" if c["pinned"] and
               c["observed_status"] in status.USABLE else
               f"served by the host's {c['path']} ({c['provider']}), unpinned" if c["copy"] == status.HOST_COPY else
               f"{c['provider'] or 'no provider'}")
        detail = f"{c['observed_status']}: {who}" + (f"; {c['cause']}" if c["cause"] else "") \
            + (f"; checked {c['checked_at']}" if c["checked_at"] else "") + (f"; fix: {c['fix']}" if c["fix"] else "")
        out.append((f"capability:{c['id']}", "PASS" if c["observed_status"] in status.USABLE else "WARN", detail))
    for o in view["overrides"]:
        out.append(("capability-records", "WARN", f"the operator's record {o['provider']} overrides AEW's shipped "
                    "record, which this AEW changed; the override is kept: " + "; ".join(o["differences"])))
    return out


# ---------------------------------------------------------------------------------------------- the check


def check(selector: str | None = None, *, offline: bool = False, directory: Path | None = None) -> dict[str, Any]:
    """Fetch, verify and check every provider, or the one ``selector`` names (a provider or a capability ID), and
    record the results. Online, a payload this host lacks is fetched from its record's source, checked against its
    pin as it is read (``offline``: never). A payload that does not match its pin is refused and removed; the next
    check fetches it again. A host copy is checked where AEW's copy cannot serve and host copies are on."""
    with store.locked(directory) as root:
        state = store.read(root)
        eff = status.effective(state)
        names = _select(eff, selector)
        facts = status.host_facts()
        done = {name: _check_one(name, eff[name], state, facts, offline=offline, directory=root) for name in names}
        store.write(state, root)
    return {"checked": done, **public(listing(directory))}


def _select(eff: dict[str, dict[str, Any]], selector: str | None) -> list[str]:
    if selector is None:
        return sorted(eff)
    if selector in eff:
        return [selector]
    named = sorted(n for n, e in eff.items() if selector in _capabilities_of(n, e))
    if not named:
        raise NotFound(f"no provider or capability named {selector!r}; `aew capability list` shows them",
                       selector=selector, known=sorted(eff))
    return named


def _check_one(name: str, entry: dict[str, Any], state: dict[str, Any], facts: dict[str, str | None], *,
               offline: bool, directory: Path) -> list[str]:
    record = entry["record"]
    if record is None:
        return [f"its record is refused: {entry['problem']}"]
    key = records.platform_key()
    pinned = record["payloads"].get(key)
    said: list[str] = []
    if pinned is not None:
        path = P.path_of(name, record["command"], pinned, directory)
        refused_now = False
        if path.exists() and (wrong := P.verify(path, pinned)) is not None:
            _refuse(state, name, key, pinned, f"the installed payload {path} does not match its pin: {wrong}")
            P.discard(name, pinned, directory)
            said.append(f"refused its installed payload ({wrong})")
            refused_now = True
        if not path.exists() and not offline and not refused_now:
            said.append(_fetch(name, record, pinned, state, key, directory))
        if path.exists():
            said.append(_record_health(state, f"{status.AEW_COPY}:{name}", path, record, pinned["sha256"], facts))
    aew = status.aew_copy(name, record, None, state, facts=facts, directory=directory)
    if aew.status in status.NOT_SERVING and state["host_copies"]:
        found = status.find_host_copy(record["command"], directory)
        if found is not None:
            said.append("the host's copy: " + _record_health(state, f"{status.HOST_COPY}:{name}", found, record,
                                                            status.file_sha256(found), facts, pinned=False))
    return said


def _fetch(name: str, record: dict[str, Any], pinned: dict[str, Any], state: dict[str, Any], key: str,
           directory: Path) -> str:
    try:
        body = P.member(P.fetch(pinned), pinned)
    except P.PinMismatch as exc:
        _refuse(state, name, key, pinned, exc.message)
        return f"refused the fetched payload: {exc.message}"
    except Unavailable as exc:
        state.setdefault("fetch_failures", {})[f"{name}:{key}"] = {"at": utc_now(), "reason": exc.message,
                                                                    "sha256": pinned["sha256"]}
        return f"could not fetch it: {exc.message}"
    _installed(state, name, key)
    P.install(name, record["command"], pinned, body, directory)
    return f"fetched {pinned['source']}"


def _installed(state: dict[str, Any], name: str, key: str) -> None:
    state.setdefault("refused", {}).pop(f"{name}:{key}", None)
    state.setdefault("fetch_failures", {}).pop(f"{name}:{key}", None)


def _refuse(state: dict[str, Any], name: str, key: str, pinned: dict[str, Any], reason: str) -> None:
    state.setdefault("refused", {})[f"{name}:{key}"] = {"at": utc_now(), "reason": reason, "sha256": pinned["sha256"]}


def _record_health(state: dict[str, Any], check_key: str, path: Path, record: dict[str, Any], sha256: str,
                   facts: dict[str, str | None], *, pinned: bool = True) -> str:
    """Run the record's health check on ``path`` and record its result. A host copy (``pinned=False``) takes its
    provider's health check, and its result is bound to its file's digest alone: it has no record of its own."""
    ok, cause, first = status.health(path, record, pinned=pinned)
    state.setdefault("checks", {})[check_key] = {
        "ok": ok, "cause": cause, "at": utc_now(), "path": str(path), "sha256": sha256, "facts": facts,
        "record_digest": records.digest(record) if pinned else None, "version": first}
    return f"checked {path}: {'passed' if ok else 'failed: ' + str(cause)}"


# ---------------------------------------------------------------------------------------------- the operator's changes


@dataclass
class Change:
    """One operator change, as the operator endpoint shows it before the operator approves it: ``lines`` is what its
    console shows, ``digest`` binds them, and ``data`` is exactly what :func:`apply` applies (an import's archive
    bytes, as the preview read them)."""

    kind: str
    lines: list[str]
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return sha256_text("\n".join(self.lines))


def preview(kind: str, args: dict[str, Any], *, directory: Path | None = None) -> Change:
    """The change ``kind`` would make, read and validated, changing nothing. Refused here, before the operator is
    asked, when it cannot be applied."""
    if kind == IMPORT:
        return _preview_import(str(args.get("path") or ""), directory)
    if kind == ADD:
        return _preview_add(str(args.get("text") or ""), str(args.get("source") or "the record file"),
                            args.get("bundle"), directory)
    if kind == REMOVE:
        return _preview_remove(str(args.get("name") or ""), directory)
    if kind == HOST_COPIES:
        if not isinstance(args.get("on"), bool):
            raise UsageError("host-copies takes on or off")
        return _preview_host_copies(bool(args["on"]), directory)
    raise UsageError(f"no capability register change {kind!r}; the changes are {', '.join(CHANGES)}")


def apply(principal: Any, change: Change, *, directory: Path | None = None) -> dict[str, Any]:
    """Apply a previewed change under the register's lock, as the operator endpoint does once the operator approved
    it. Refused without the endpoint's ``OperatorPrincipal``. Re-validated against the register as it is now: what
    changed since the preview is refused, never applied on a stale view."""
    from aew.engine.steering import OperatorPrincipal

    if not isinstance(principal, OperatorPrincipal):
        raise PermissionDenied("a change to the capability register is the operator's, approved at the operator "
                               "endpoint (`aew operator serve --dev`); nothing else applies one",
                               reason="operator_principal_required")
    with store.locked(directory) as root:
        state = store.read(root)
        what = {IMPORT: _apply_import, ADD: _apply_add, REMOVE: _apply_remove,
                HOST_COPIES: _apply_host_copies}[change.kind](change, state, root)
        store.write(state, root)
        entry = store.record_change(change.kind, {"change": change.lines, "digest": change.digest, **what,
                                                  "principal": principal.record()},
                                    {"authorized_by": "operator-endpoint"}, root)
    return {"applied": change.kind, "change": change.lines, "recorded": entry["at"], **what}


def _bundle_files(path: str) -> list[Path]:
    if not path:
        raise UsageError("import takes the path of a bundle: a release archive, or a directory of them")
    target = Path(path)
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(p for p in target.iterdir() if p.is_file())
    raise NotFound(f"no bundle at {path}: give a release archive, or a directory of them", path=path)


Matched = tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]


def _match_bundle(files: list[Path], eff: dict[str, dict[str, Any]], key: str) -> Matched:
    """(the archives that match a pin for this platform, read; the ones that carry a pinned archive's name but not its
    pin; what else the bundle holds). Matched by digest, so a renamed archive still imports."""
    pins = [(name, k, payload) for name, e in sorted(eff.items()) if e["record"] is not None
            for k, payload in e["record"]["payloads"].items()]
    held, refused, other = [], [], []
    for f in files:
        size = f.stat().st_size
        candidates = [(n, k, p) for n, k, p in pins if p["archive_size"] == size or Path(p["source"]).name == f.name]
        if not candidates:
            other.append(f"{f.name}: matches no pinned archive")
            continue
        with open(f, "rb") as fh:
            data = fh.read(max(p["archive_size"] for _, _, p in candidates) + 1)
        sha = hashlib.sha256(data).hexdigest()
        hits = [(n, k, p) for n, k, p in candidates if p["archive_sha256"] == sha and p["archive_size"] == len(data)]
        for n, k, p in hits:
            if k == key:
                held.append({"name": n, "file": str(f), "data": data, "sha256": sha, "payload": p})
            else:
                other.append(f"{f.name}: {n}'s archive for {k}, not this platform ({key})")
        if not hits:
            for n, k, p in candidates:
                if Path(p["source"]).name == f.name and k == key:
                    refused.append({"name": n, "file": str(f), "payload": p,
                                    "reason": f"the bundle's {f.name} does not match its pin (sha256 {sha}, "
                                              f"{len(data)} bytes; pinned {p['archive_sha256']}, "
                                              f"{p['archive_size']} bytes)"})
            if not any(r["file"] == str(f) for r in refused):
                other.append(f"{f.name}: matches no pinned archive")
    return held, refused, other


def _preview_import(path: str, directory: Path | None) -> Change:
    files = _bundle_files(path)
    eff = status.effective(store.read(directory))
    key = records.platform_key()
    held, refused, other = _match_bundle(files, eff, key)
    if not held and not refused:
        raise NotFound(f"the bundle {path} holds no archive pinned for this platform ({key}): "
                       + ("; ".join(other) or "it is empty"), path=path, platform=key)
    lines = [f"IMPORT into this host's capability register ({directory or store.root()}), for {key}:"]
    lines += [f"  {h['name']} {eff[h['name']]['record']['version']} from {h['file']} (archive sha256 {h['sha256']}, "
              f"executable sha256 {h['payload']['sha256']})" for h in held]
    lines += [f"  REFUSE {r['file']} for {r['name']}: {r['reason']}" for r in refused]
    lines += [f"  skip {o}" for o in other]
    return Change(IMPORT, lines, {"held": held, "refused": refused})


def _apply_import(change: Change, state: dict[str, Any], root: Path) -> dict[str, Any]:
    eff = status.effective(state)
    key = records.platform_key()
    facts = status.host_facts()
    imported, refused, skipped = [], [], []
    for r in change.data["refused"]:
        _refuse(state, r["name"], key, r["payload"], r["reason"])
        refused.append({"provider": r["name"], "file": r["file"], "reason": r["reason"]})
    for h in change.data["held"]:
        record = (eff.get(h["name"]) or {}).get("record")
        pinned = (record or {}).get("payloads", {}).get(key)
        if record is None or pinned != h["payload"]:
            skipped.append({"provider": h["name"], "file": h["file"],
                            "reason": "its record changed since the preview; import the bundle again"})
            continue
        try:
            body = P.member(h["data"], pinned)
        except P.PinMismatch as exc:
            _refuse(state, h["name"], key, pinned, exc.message)
            refused.append({"provider": h["name"], "file": h["file"], "reason": exc.message})
            continue
        _installed(state, h["name"], key)
        path = P.install(h["name"], record["command"], pinned, body, root)
        said = _record_health(state, f"{status.AEW_COPY}:{h['name']}", path, record, pinned["sha256"], facts)
        imported.append({"provider": h["name"], "file": h["file"], "path": str(path), "check": said})
    return {"imported": imported, "refused": refused, "skipped": skipped}


def _preview_add(text: str, source: str, bundle: Any, directory: Path | None) -> Change:
    if len(text.encode("utf-8")) > MAX_RECORD_TEXT:
        raise UsageError(f"{source} is larger than {MAX_RECORD_TEXT} bytes, the most one operator endpoint request "
                         "carries; one record is far smaller")
    try:
        added = records.validate(load_yaml(text, source=source), source=source)
    except AEWError as exc:
        raise ValidationFailed(f"the record was not added, and nothing changed: {exc.message}",
                               **exc.details) from None
    key = records.platform_key()
    lines = [f"ADD to this host's capability register ({directory or store.root()}) the operator's records:"]
    data: dict[str, Any] = {"records": added, "held": {}}
    eff = status.effective(store.read(directory))
    for name, record in sorted(added.items()):
        pinned = record["payloads"].get(key)
        if pinned is None:
            raise ValidationFailed(f"the record {name} was not added, and nothing changed: it has no payload for this "
                                   f"platform ({key}), so its health check cannot run here (CAPR-13)",
                                   provider=name, platform=key, reason="no_payload_for_platform")
        shipped = records.shipped().get(name)
        lines.append(f"  {name}: `{record['command']}` serving {', '.join(record['capabilities'])}, version "
                     f"{record['version']}, placed in the sandbox, PATH {record['path']}; payload for {key}: "
                     f"{pinned['source']} (archive sha256 {pinned['archive_sha256']}, executable sha256 "
                     f"{pinned['sha256']}); record digest {records.digest(record)}")
        if shipped is not None:
            lines.append(f"    overrides AEW's shipped {name}: " + ("; ".join(records.differences(shipped, record))
                                                                   or "no field differs"))
        elif name in eff and eff[name]["layer"] == "operator":
            lines.append(f"    replaces the operator's earlier record {name}")
    if bundle:
        held, _, _ = _match_bundle(_bundle_files(str(bundle)), {n: {"record": r} for n, r in added.items()}, key)
        data["held"] = {h["name"]: h["data"] for h in held}
        lines += [f"  payload of {h['name']} from {h['file']}" for h in held]
    return Change(ADD, lines, data)


def _apply_add(change: Change, state: dict[str, Any], root: Path) -> dict[str, Any]:
    """Validated before it takes effect (CAPR-13): each record's payload is fetched (or taken from the bundle shown)
    and checked against its pin, and its health check must pass; otherwise nothing changes."""
    key = records.platform_key()
    facts = status.host_facts()
    trial = {**state, "checks": dict(state.get("checks") or {}), "refused": dict(state.get("refused") or {}),
             "fetch_failures": dict(state.get("fetch_failures") or {})}
    made: list[tuple[str, dict[str, Any]]] = []
    added = []
    try:
        for name, record in sorted(change.data["records"].items()):
            pinned = record["payloads"][key]
            path = P.path_of(name, record["command"], pinned, root)
            if not path.exists():
                data = change.data["held"].get(name)
                if data is not None:  # the bundle's bytes, as the preview read and showed them
                    P.check_archive(data, pinned, what="the bundle's archive")
                body = P.member(data if data is not None else P.fetch(pinned), pinned)
                P.install(name, record["command"], pinned, body, root)
                made.append((name, pinned))
            elif (wrong := P.verify(path, pinned)) is not None:
                raise P.PinMismatch(f"the payload already at {path} does not match its pin: {wrong}",
                                    reason="payload_pin")
            said = _record_health(trial, f"{status.AEW_COPY}:{name}", path, record, pinned["sha256"], facts)
            if not trial["checks"][f"{status.AEW_COPY}:{name}"]["ok"]:
                raise ValidationFailed(f"{name}'s health check failed: {said}", provider=name, reason="health_failed")
            added.append(name)
    except AEWError as exc:
        for name, pinned in made:
            P.discard(name, pinned, root)
        raise ValidationFailed(f"the records were not added, and nothing changed: {exc.message}",
                               **{k: v for k, v in exc.details.items() if k != "reason"},
                               reason=exc.details.get("reason") or "validation_failed") from None
    state["checks"] = trial["checks"]
    for name in added:
        record = change.data["records"][name]
        shipped = records.shipped().get(name)
        state.setdefault("operator_records", {})[name] = {
            "record": record, "added_at": utc_now(), "base_digest": records.digest(shipped) if shipped else None,
            "base_record": shipped}
        _installed(state, name, key)
    return {"added": added}


def _preview_remove(name: str, directory: Path | None) -> Change:
    state = store.read(directory)
    if name not in (state.get("operator_records") or {}):
        shipped = name in records.shipped()
        raise NotFound(f"no operator record named {name!r}" + (": AEW's shipped records are changed only by a "
                       "reviewed AEW release; add an operator record of the same name to override one" if shipped
                       else ""), name=name, operator_records=sorted(state.get("operator_records") or {}))
    after = (f"AEW's shipped record {name} serves again" if name in records.shipped()
             else f"no record named {name} remains, and its capabilities lose this provider")
    return Change(REMOVE, [f"REMOVE from this host's capability register ({directory or store.root()}) the "
                           f"operator's record {name}: {after}"], {"name": name})


def _apply_remove(change: Change, state: dict[str, Any], root: Path) -> dict[str, Any]:
    name = change.data["name"]
    if (state.get("operator_records") or {}).pop(name, None) is None:
        raise NotFound(f"the operator's record {name} was removed since the preview", name=name)
    return {"removed": name}


def _preview_host_copies(on: bool, directory: Path | None) -> Change:
    now = bool(store.read(directory)["host_copies"])
    effect = ("a copy the host has on its PATH serves where AEW's copy is absent or refused, named as unpinned" if on
              else "a copy the host has never serves: where AEW's copy is absent or refused, the capability reads "
                   "UNAVAILABLE or REFUSED with its cause")
    return Change(HOST_COPIES, [f"TURN host copies {'ON' if on else 'OFF'} in this host's capability register "
                                f"({directory or store.root()}; now {'on' if now else 'off'}): {effect}"], {"on": on})


def _apply_host_copies(change: Change, state: dict[str, Any], root: Path) -> dict[str, Any]:
    state["host_copies"] = bool(change.data["on"])
    return {"host_copies": state["host_copies"]}

