"""The capability register's operations (STG-15, A-38: CAPR-03, CAPR-04, CAPR-05, CAPR-12, CAPR-13).

* :func:`listing`: every capability's status on this host, its provider, its cause and its fix. A read: ``aew
  capability list`` and ``aew doctor`` show it, and need no authorization.
* :func:`check`: fetch what a record pins and this host lacks (online), check every payload against its pin, run the
  health checks and record their results. It writes the checks' results and payloads to an existing pin, never a
  record or a setting, so it changes no authority and needs none.
* :func:`fetch_at_launch` and :func:`record_contained`: the same two writes, at a contained context's launch, which
  never stop it (CAPR-12). What the context then gets is :mod:`.bind`'s.
* The operator's changes, ``import``, ``add``, ``remove`` and ``host-copies``, change what a contained context gets,
  so they are the operator's alone (CAPR-05; the designer's CAP-1 ruling 1): a change is previewed
  (:func:`preview`), shown at the operator endpoint's console, and applied by the endpoint (:func:`apply`) once the
  operator typed its code back. :func:`apply` takes the endpoint's ``OperatorPrincipal``, which only the endpoint
  constructs, and applies exactly what was shown: the bundle bytes the preview read, the record text it validated.
  A change that fails validation changes nothing, and says why (CAPR-13).
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew import process_kind
from aew.capability import bind, records, status, store
from aew.capability import payload as P
from aew.capability.status import Copy
from aew.errors import AEWError, IntegrityError, NotFound, PermissionDenied, Unavailable, UsageError, ValidationFailed
from aew.util import load_yaml, sha256_text, utc_now

IMPORT, ADD, REMOVE, HOST_COPIES = "import", "add", "remove", "host_copies"
CHANGES = (IMPORT, ADD, REMOVE, HOST_COPIES)
MAX_RECORD_TEXT = 12 * 1024  # an add's record text travels in one operator endpoint request (its MAX_MESSAGE, 16 KiB)
# Tests turn the launch's fetch off in process, as they point the register elsewhere (``store.ROOT_OVERRIDE``); the
# product never sets it, and no variable reaches it, so an installed AEW always fetches what it lacks. A test's child
# `aew` starts from a register that holds a failure instead, which reads as what it is (``conftest``).
LAUNCH_FETCH = True


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
    if entry["record"] is not None:
        return list(entry["record"]["capabilities"])
    # A refused record still names what it serves: the shipped record's capabilities and its own (review F11)
    named = records.capability_ids(records.shipped().get(name)) + records.capability_ids(entry.get("held"))
    return list(dict.fromkeys(named))


def _provider(name: str, entry: dict[str, Any], state: dict[str, Any], facts: dict[str, str | None],
              directory: Path | None) -> dict[str, Any]:
    record = entry["record"]
    aew = status.aew_copy(name, record, entry["problem"], state, facts=facts, directory=directory)
    host: Copy | None = None
    note = None
    limits = [status.NOT_BOUND] if sys.platform == "win32" else []
    if record is not None and aew.status in status.NOT_SERVING:
        if state["host_copies"]:
            host = status.host_copy(name, record, state, facts=facts, directory=directory)
        elif (found := status.find_host_copy(record["command"], directory)) is not None:
            note = (f"this host's {found} does not serve: the operator turned host copies off (`aew capability "
                    "host-copies on` turns them on)")
    return {"name": name, "layer": entry["layer"], "command": (record or {}).get("command"),
            "version": (record or {}).get("version"), "aew_copy": aew.describe(),
            "host_copy": host.describe() if host is not None else None, "note": note,
            "serving": host if host is not None else aew, "aew": aew, "limitations": limits}


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
            "cause": "; ".join(causes) or None, "limitations": [*serving.limitations, *chosen["limitations"]],
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
    return {**view, "providers": [{k: v for k, v in p.items() if k not in ("serving", "aew", "limitations")}
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
    check fetches it again. Each copy's health check runs inside a sandbox, as its uses run (CAPR-13), so what it says
    is what a contained run sees; only where no sandbox can be made does it run here, and the status says so. A host
    copy is checked where AEW's copy cannot serve and host copies are on."""
    with store.locked(directory) as root:
        state = store.read(root)
        eff = status.effective(state)
        names = _select(eff, selector)
        facts = status.host_facts()
        done = {name: _acquire(name, eff[name], state, offline=offline, directory=root) for name in names}
        _check_health(names, eff, state, facts, done, root)
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


def _acquire(name: str, entry: dict[str, Any], state: dict[str, Any], *, offline: bool, directory: Path) -> list[str]:
    """What a check does before any health check: refuse a payload off its pin, and fetch one this host lacks."""
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
        elif path.exists():  # it matches its pin: an earlier refusal (a refused import or fetch) no longer holds (F4)
            _installed(state, name, key)
        if not path.exists() and not offline and not refused_now:
            said.append(_fetch(name, record, pinned, state, key, directory))
    return said


def _check_health(names: list[str], eff: dict[str, dict[str, Any]], state: dict[str, Any],
                  facts: dict[str, str | None], done: dict[str, list[str]], root: Path) -> None:
    """Each named provider's health check: in one sandbox, as its uses run (CAPR-13), or here where none can be made."""
    from aew.harness import containment

    seen = containment.tool_checks(bind.plan(root, state=state, names=names))
    if seen is None:
        for name in names:
            if eff[name]["record"] is not None:
                done[name] += _check_here(name, eff[name]["record"], state, facts, root)
        return
    _apply_contained(state, seen, facts)
    for name, tool in seen.items():
        for t in tool["tried"]:
            whose = "" if t["kind"] == status.AEW_COPY else "the host's copy: "
            done[name].append(f"{whose}checked {t['path']} in a sandbox: "
                              f"{'passed' if t['ok'] else 'failed: ' + str(t['cause'])}")


def _check_here(name: str, record: dict[str, Any], state: dict[str, Any], facts: dict[str, str | None],
                directory: Path) -> list[str]:
    """Where no sandbox can be made: AEW's copy, and the host's where AEW's cannot serve and host copies are on."""
    said: list[str] = []
    pinned = record["payloads"].get(records.platform_key())
    if pinned is not None:
        path = P.path_of(name, record["command"], pinned, directory)
        if path.exists():
            said.append(_record_here(state, f"{status.AEW_COPY}:{name}", path, record, pinned["sha256"], facts))
    aew = status.aew_copy(name, record, None, state, facts=facts, directory=directory)
    if aew.status in status.NOT_SERVING and state["host_copies"]:
        found = status.find_host_copy(record["command"], directory)
        if found is not None:
            said.append("the host's copy: " + _record_here(state, f"{status.HOST_COPY}:{name}", found, record,
                                                          status.file_sha256(found), facts, pinned=False))
    return said


def _fetched(pinned: dict[str, Any]) -> bytes | AEWError:
    """The pinned executable from its record's source, or why not."""
    try:
        return P.member(P.fetch(pinned), pinned)
    except (P.PinMismatch, Unavailable) as exc:
        return exc


def _take(name: str, record: dict[str, Any], pinned: dict[str, Any], state: dict[str, Any], key: str, directory: Path,
          got: bytes | AEWError) -> str:
    """Record one fetch's outcome and install what it brought."""
    if isinstance(got, P.PinMismatch):
        _refuse(state, name, key, pinned, got.message)
        return f"refused the fetched payload: {got.message}"
    if isinstance(got, AEWError):
        state.setdefault("fetch_failures", {})[f"{name}:{key}"] = {"at": utc_now(), "reason": got.message,
                                                                    "sha256": pinned["sha256"]}
        return f"could not fetch it: {got.message}"
    _installed(state, name, key)
    P.install(name, record["command"], pinned, got, directory)
    return f"fetched {pinned['source']}"


def _fetch(name: str, record: dict[str, Any], pinned: dict[str, Any], state: dict[str, Any], key: str,
           directory: Path) -> str:
    return _take(name, record, pinned, state, key, directory, _fetched(pinned))


# ---------------------------------------------------------------------------------------------- at a launch


def _due(state: dict[str, Any], directory: Path | None) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """What a launch fetches: each payload this host lacks that was neither refused nor failed lately. A refusal stays
    until ``aew capability check``, which is the operator's to run, and whose fix text the status gives."""
    key = records.platform_key()
    out = []
    for name, entry in sorted(status.effective(state).items()):
        pinned = (entry["record"] or {}).get("payloads", {}).get(key)
        if pinned is None or P.path_of(name, entry["record"]["command"], pinned, directory).exists():
            continue
        refused = (state.get("refused") or {}).get(f"{name}:{key}") or {}
        failed = (state.get("fetch_failures") or {}).get(f"{name}:{key}") or {}
        if refused.get("sha256") == pinned["sha256"]:
            continue
        if failed.get("sha256") == pinned["sha256"] and _within_retry(failed.get("at")):
            continue
        out.append((name, entry["record"], pinned))
    return out


def _within_retry(at: Any) -> bool:
    """A failure this recent is not tried again at a launch: each try can cost a launch
    :data:`P.LAUNCH_FETCH_BOUND_S`. An unreadable time: try again."""
    next_try = status.next_fetch(at)
    return next_try is not None and datetime.now(UTC) < next_try


def fetch_at_launch(directory: Path | None = None) -> None:
    """CAPR-04, CAPR-Q10: before a contained context's first use, with no step for the operator, fetch what this host
    lacks. It never stops the launch (CAPR-12): a failure is recorded, the status says why, and the run goes on with a
    host copy or the stub. The network wait is outside the register's lock and bounded as a whole, so a second launch
    does not queue behind it; two first launches may each fetch, and each installs the same pinned bytes. Its record
    waits only the short ``store.RECORD_WAIT_S`` for the lock: behind a long holder (`aew capability check` holds it
    across its fetches) it gives way, and the next launch fetches and records (review of #330, M1). Every wait here is
    one ``supervisor.starting_limit_s`` adds."""
    if not LAUNCH_FETCH:
        return
    if process_kind.kind() == process_kind.NON_WRITER:  # an agent's own `aew`: the register is the operator's
        return
    try:
        due = _due(store.read(directory), directory)
        if not due:
            return
        # Said where the operator sees it: a start that waits on the network says so (review of #330, m3)
        sys.stderr.write(f"aew: fetching {', '.join(name for name, _, _ in due)} for this host's capability register "
                         f"(at most {P.LAUNCH_FETCH_BOUND_S:g} s); the run goes on whatever comes of it\n")
        got: dict[str, bytes | AEWError] = {}

        def fetch_all() -> None:
            for name, _, pinned in due:
                got[name] = _fetched(pinned)

        worker = threading.Thread(target=fetch_all, name="aew-capability-fetch", daemon=True)
        worker.start()
        worker.join(P.LAUNCH_FETCH_BOUND_S)
        late = Unavailable(f"the fetch did not finish within {P.LAUNCH_FETCH_BOUND_S:g} s at this launch",
                           reason="fetch_failed")
        key = records.platform_key()
        with store.locked(directory, short=True) as root:
            state = store.read(root)
            for name, record, pinned in due:
                _take(name, record, pinned, state, key, root, got.get(name, late))
            store.write(state, root)
    except (AEWError, OSError):  # a register that cannot be read or written: every status read says so itself
        return


def record_contained(tools: dict[str, Any] | None, directory: Path | None = None) -> None:
    """Record what a sandbox's self-test found (``probe.self_test``'s ``tools``): the status follows the check inside
    (CAPR-03, CAPR-13). Written only where a result changed, so an ordinary launch takes no lock; never stops anything
    (CAPR-12): where it cannot be written, as inside a sandbox, or behind a long holder of the lock, the next one
    does."""
    if not tools:
        return
    if process_kind.kind() == process_kind.NON_WRITER:  # an agent's own `aew`: the register is the operator's
        return
    try:
        facts = status.host_facts()
        if not _apply_contained(store.read(directory), tools, facts):
            return
        with store.locked(directory, short=True) as root:
            state = store.read(root)
            _apply_contained(state, tools, facts)
            store.write(state, root)
    except (AEWError, OSError):
        return


def _apply_contained(state: dict[str, Any], tools: dict[str, Any], facts: dict[str, str | None]) -> bool:
    """Put a self-test's results in ``state``; whether any differs from what was there, the time aside."""
    changed = False
    checks = state.setdefault("checks", {})
    for name, tool in tools.items():
        for t in tool.get("tried") or []:
            try:
                sha256 = t["sha256"] or status.file_sha256(Path(t["path"]))
            except OSError:
                continue
            entry = {"ok": bool(t["ok"]), "cause": t["cause"], "path": str(t["path"]), "sha256": sha256, "facts": facts,
                     "record_digest": t["record_digest"], "version": t["version"], "where": status.IN_SANDBOX}
            key = f"{t['kind']}:{name}"
            if {k: v for k, v in (checks.get(key) or {}).items() if k != "at"} != entry:
                checks[key] = {**entry, "at": utc_now()}
                changed = True
    return changed


def _installed(state: dict[str, Any], name: str, key: str) -> None:
    state.setdefault("refused", {}).pop(f"{name}:{key}", None)
    state.setdefault("fetch_failures", {}).pop(f"{name}:{key}", None)


def _refuse(state: dict[str, Any], name: str, key: str, pinned: dict[str, Any], reason: str) -> None:
    state.setdefault("refused", {})[f"{name}:{key}"] = {"at": utc_now(), "reason": reason, "sha256": pinned["sha256"]}


def _record_health(state: dict[str, Any], check_key: str, path: Path, record: dict[str, Any], sha256: str,
                   facts: dict[str, str | None]) -> str:
    """AEW's copy at ``path`` checked before it takes effect (an import, an add; CAPR-13): inside a sandbox, as its uses
    run, or here where none can be made."""
    from aew.harness import containment

    name = check_key.split(":", 1)[1]
    tool = bind.Tool(name, record["command"], record["path"], record, ((status.AEW_COPY, str(path)),), sha256=sha256,
                     digest=records.digest(record))
    seen = containment.tool_checks((tool,))
    if seen is None or name not in seen:
        return _record_here(state, check_key, path, record, sha256, facts)
    _apply_contained(state, seen, facts)
    done = seen[name]["tried"][0]
    return f"checked {path} in a sandbox: {'passed' if done['ok'] else 'failed: ' + str(done['cause'])}"


def _record_here(state: dict[str, Any], check_key: str, path: Path, record: dict[str, Any], sha256: str,
                 facts: dict[str, str | None], *, pinned: bool = True) -> str:
    """Run the record's health check on ``path``, on this host, and record its result. A host copy (``pinned=False``)
    takes its provider's health check, and its result is bound to its file's digest alone: it has no record of its
    own."""
    ok, cause, first = status.health(path, record, pinned=pinned)
    state.setdefault("checks", {})[check_key] = {
        "ok": ok, "cause": cause, "at": utc_now(), "path": str(path), "sha256": sha256, "facts": facts,
        "record_digest": records.digest(record) if pinned else None, "version": first, "where": status.ON_HOST}
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
    asked, when it cannot be applied. It carries the register's basis as it was read before the change was (so a
    change that lands in between is refused at :func:`apply`, never applied on what the operator was not shown)."""
    basis = _basis(store.read(directory))
    if kind == IMPORT:
        change = _preview_import(str(args.get("path") or ""), directory)
    elif kind == ADD:
        change = _preview_add(str(args.get("text") or ""), str(args.get("source") or "the record file"),
                              args.get("bundle"), directory)
    elif kind == REMOVE:
        change = _preview_remove(str(args.get("name") or ""), directory)
    elif kind == HOST_COPIES:
        if not isinstance(args.get("on"), bool):
            raise UsageError("host-copies takes on or off")
        change = _preview_host_copies(bool(args["on"]), directory)
    else:
        raise UsageError(f"no capability register change {kind!r}; the changes are {', '.join(CHANGES)}")
    change.data["basis"] = basis
    return change


def _basis(state: dict[str, Any]) -> str:
    """What an operator change is shown against, and applied only on: the operator's records and the host-copies
    setting (review F10). The health checks' results are not part of it: a check changes no authority."""
    return sha256_text(json.dumps({"operator_records": state.get("operator_records") or {},
                                   "host_copies": state.get("host_copies")}, sort_keys=True))


def apply(principal: Any, change: Change, *, directory: Path | None = None) -> dict[str, Any]:
    """Apply a previewed change under the register's lock, as the operator endpoint does once the operator approved
    it. Refused without the endpoint's ``OperatorPrincipal``. Re-validated against the register as it is now: a
    change since the preview to the operator's records or the host-copies setting is refused (its basis), never
    applied on a stale view."""
    from aew.engine.steering import OperatorPrincipal

    if not isinstance(principal, OperatorPrincipal):
        raise PermissionDenied("a change to the capability register is the operator's, approved at the operator "
                               "endpoint (`aew operator serve --dev`); nothing else applies one",
                               reason="operator_principal_required")
    with store.locked(directory) as root:
        state = store.read(root)
        if change.data.get("basis") != _basis(state):
            raise ValidationFailed("the capability register's operator records or host-copies setting changed since "
                                   "this change was shown, so it was not applied, and nothing changed: ask for it "
                                   "again to see it against the register as it is now", reason="register_changed")
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
                    # A file larger than its pin is read only to the pin's size, so its own digest is not known: its
                    # size is what is said (review F13)
                    reason = (f"the bundle's {f.name} is larger than its pin ({size} bytes; pinned "
                              f"{p['archive_size']} bytes)" if size > p["archive_size"] else
                              f"the bundle's {f.name} does not match its pin (sha256 {sha}, {len(data)} bytes; "
                              f"pinned {p['archive_sha256']}, {p['archive_size']} bytes)")
                    refused.append({"name": n, "file": str(f), "payload": p, "reason": reason})
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


def check_record_size(text: str | bytes, source: str) -> None:
    """Refuse a record text one operator endpoint request cannot carry: at the requesting terminal before it is sent
    (its bytes, before they are decoded), and at the endpoint (review F12)."""
    if len(text if isinstance(text, bytes) else text.encode("utf-8")) > MAX_RECORD_TEXT:
        raise UsageError(f"{source} is larger than {MAX_RECORD_TEXT} bytes, the most one operator endpoint request "
                         "carries; one record is far smaller", path=source, limit=MAX_RECORD_TEXT)


def _preview_add(text: str, source: str, bundle: Any, directory: Path | None) -> Change:
    check_record_size(text, source)
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

