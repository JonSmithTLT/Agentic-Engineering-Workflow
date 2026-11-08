"""``aew doctor``'s read of the harness's model list (register E153; the designer's ruling (a), relayed 2026-11-07).

By default, doctor reads the list a launch would read, with what of a launch's configuration the list depends on: the
harness binary, the projected configuration for the profile's provider and model (a worker's role, with no card's
skills or tools, which the list does not depend on), the containment and network rule
(:func:`aew.harness.supervisor.contain_launch`, the one owner a run's supervisor shares) and the catalog fetch (the
adapter's ``read_model_list``, which shares its server start with ``launch``). No session is created and no model is
called; the server and everything it started are reaped when the read ends. The read is bounded by the launch's own
start deadline (``supervisor.starting_limit_s``), and one that runs out is a red row with its fix.

A list is cached by the binary's sha256 and the hash of the projected configuration (:func:`cache_key`), so an
unchanged environment reads it once; ``aew doctor --refresh`` reads it again. The rows refuse nothing: each pinned
model the list does not offer is a FAIL that names the model and the ones the provider does list, and dispatch refuses
where its own launch check fails, as before.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from aew.errors import AEWError
from aew.harness import registry, runlog
from aew.policy import execution as X
from aew.util import atomic_write, utc_now

CHECK = "model-list"
CACHE_REL = "local/doctor/model-lists.json"
CACHE_KEEP = 16  # the most recent lists kept; an older one is read again when asked for
ROLE, SCOPE = "implementer", "ticket"  # the sandbox a worker's launch gets: what the read meets


def _row(status: str, detail: str) -> dict[str, str]:
    return {"check": CHECK, "status": status, "detail": detail}


def doctor_rows(engine: Any, *, refresh: bool = False) -> list[dict[str, str]]:
    """One ``model-list`` row: each profile's pinned model against the list its harness offers, read as a launch reads
    it. FAIL names each pinned model the list does not offer, with the models the provider does list, and each cause a
    launch would be refused for (a provider key missing, a catalog that offered nothing in time); WARN where the list
    could not be read and a launch would not be stopped by the same cause (no binary here, a sandbox not established
    here). None of it refuses anything. Profiles of one harness and provider share a read that lists their model
    (review of #367, N2): the list does not depend on which of its models is pinned."""
    policy, sha = engine.execution_policy()
    if not policy or not policy.get("profiles"):
        return []
    found: list[str] = []
    problems: list[str] = []
    unread: list[str] = []
    read: dict[tuple[str, str], tuple[dict[str, Any], str]] = {}
    for name in sorted(policy["profiles"]):
        try:
            pin = X.resolve(policy, sha, archetype=ROLE, card_id=None, risk_class=None, request={"profile": name},
                            identity=registry.model_identity)
            adapter_cls = registry.load(pin["harness"])
        except AEWError:  # the model-refs row names a profile that maps to no model
            continue
        if not hasattr(adapter_cls, "read_model_list"):  # a harness without the capability (harness_capabilities)
            continue
        shared = read.get((str(pin["harness"]), str(pin["provider"])))
        if shared is not None and any(m["providerID"] == pin["provider"] and m["id"] == pin["model"]
                                      for m in shared[0].get("models") or []):
            listing, when = shared  # a read that stopped at another pin is reused only where it lists this one
        else:
            try:
                listing, when = _listing(engine, policy, pin, adapter_cls, refresh=refresh)
            except _Unread as exc:
                (problems if exc.red else unread).append(f"profile {name}: {exc}")
                continue
            read[(str(pin["harness"]), str(pin["provider"]))] = (listing, when)
        found.append(_judge(name, pin, listing, when, problems))
    if problems:
        return [_row("FAIL", "; ".join(problems) + "; a launch of these profiles is refused until they are fixed"
                     + (f" ({'; '.join(unread)})" if unread else ""))]
    if unread:
        return [_row("WARN", "the model list was not read: " + "; ".join(unread)
                     + (f" ({'; '.join(f for f in found if f)})" if any(found) else ""))]
    return [_row("PASS", "; ".join(found))] if found else []


def _judge(name: str, pin: dict[str, Any], listing: dict[str, Any], when: str, problems: list[str]) -> str:
    """Profile ``name``'s pinned model against ``listing``: its PASS text, or an entry in ``problems``."""
    provider, model, effort = str(pin["provider"]), str(pin["model"]), pin.get("effort")
    ref = f"{provider}/{model}"
    models = listing.get("models") or []
    where = f"{pin['harness']} {listing.get('version') or ''}".rstrip() + f"'s model list ({when})"
    match = next((m for m in models if m["providerID"] == provider and m["id"] == model), None)
    if match is None:
        same = sorted(f"{m['providerID']}/{m['id']}" for m in models if m["providerID"] == provider)
        offered = (f"{provider} lists {', '.join(same)}" if same else
                   f"it lists no model of {provider}; the providers it lists are "
                   f"{', '.join(sorted({m['providerID'] for m in models})) or 'none'}")
        problems.append(f"profile {name}: {ref} is not in {where}: {offered}. Set profiles.{name}.model to a model "
                        f"it lists" + (f", such as {same[0]}" if same else ", with that provider's variable set")
                        + " (edit the execution policy and adopt it)")
        return ""
    if match.get("enabled") is False:
        problems.append(f"profile {name}: {ref} is disabled in {where}; enable it in the harness, or set "
                        f"profiles.{name}.model to another model it lists")
        return ""
    if effort and str(effort) not in match.get("variants", []):
        problems.append(f"profile {name}: {ref} has no variant {effort!r} (the profile's effort) in {where}; it "
                        f"offers {', '.join(match.get('variants') or []) or 'none'}; set profiles.{name}.effort to "
                        "one of them")
        return ""
    return f"profile {name}: {ref} is in {where}"


class _Unread(Exception):
    """The list was not read. ``red``: a launch would fail the same way, so the row is a FAIL with its fix."""

    def __init__(self, message: str, *, red: bool) -> None:
        super().__init__(message)
        self.red = red


def _contract(run_dir: Path, pin: dict[str, Any], policy: dict[str, Any]) -> Any:
    from aew.harness.contract import LaunchContract

    return LaunchContract(run=run_dir.name, invocation="doctor", work_unit="doctor", role=ROLE, scope=SCOPE,
                          card=None, execution_profile=dict(pin), workspace=str(run_dir / "workspace"),
                          expected_kinds=[], operations=[], pack_path="", pack_sha256="", pack_text="",
                          continuation=None, run_dir=str(run_dir),
                          extra={"provider_env": [str(n) for n in policy.get("provider_env") or []]},
                          scratch=str(run_dir / "scratch"))


def cache_key(adapter_cls: Any, policy: dict[str, Any], pin: dict[str, Any]) -> str | None:
    """The binary's sha256 and the hash of the projected configuration, as one key; None without a binary. The
    projection is hashed over a fixed run directory, as its paths are the run's own, with the policy's containment and
    network rule beside it (the parts of a launch's configuration the projection does not carry)."""
    binary = adapter_cls.model_list_binary()
    if binary is None:
        return None
    digest = hashlib.sha256()
    with Path(binary).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    projected = adapter_cls.projected_config(_contract(Path("/aew-doctor/run"), pin, policy))
    rule = {k: policy.get(k) for k in ("containment", "provider_env")}  # the network rule is containment's
    config = hashlib.sha256(json.dumps([projected, rule], sort_keys=True, default=str).encode()).hexdigest()
    return f"{digest.hexdigest()}:{config}"


def _listing(engine: Any, policy: dict[str, Any], pin: dict[str, Any], adapter_cls: Any, *,
             refresh: bool) -> tuple[dict[str, Any], str]:
    """The list for ``pin``: cached under its key, or read now (and cached when the read completed)."""
    try:
        key = cache_key(adapter_cls, policy, pin)
    except AEWError as exc:
        raise _Unread(f"no harness binary to read it from: {exc.message}", red=False) from None
    if key is None:
        raise _Unread("no harness binary to read it from", red=False)
    path = engine.aew_root / CACHE_REL
    cache = _load(path)
    if not refresh and key in cache:
        return cache[key], f"read {cache[key]['read_at']}, cached: `aew doctor --refresh` reads it again"
    bound = _bound(pin)
    # The default doctor can now wait for a harness to start and its catalog to fill (review of #367, F5): say so.
    print(f"aew doctor: reading {pin['harness']}'s model list for {pin['provider']}/{pin['model']} as a launch reads "
          f"it (up to {bound:.0f}s, the launch's start deadline; the list is cached, and `aew doctor --refresh` reads "
          "it again)", file=sys.stderr, flush=True)
    listing = read(engine, policy, pin, adapter_cls)
    if listing.get("complete"):
        entry = {**listing, "read_at": utc_now()}
        cache = {k: v for k, v in cache.items() if k != key}
        kept = dict(sorted(cache.items(), key=lambda kv: str(kv[1].get("read_at")))[-(CACHE_KEEP - 1):])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, json.dumps({**kept, key: entry}, indent=1, sort_keys=True))
        except OSError:
            pass  # read again next time
    return listing, "read just now"


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("models"), list)} \
        if isinstance(data, dict) else {}


def _bound(pin: dict[str, Any]) -> float:
    from aew.harness import supervisor

    return supervisor.starting_limit_s(pin["harness"])


def read(engine: Any, policy: dict[str, Any], pin: dict[str, Any], adapter_cls: Any) -> dict[str, Any]:
    """Read the list as a launch of ``pin`` would: its containment and network (``contain_launch``), its process tree,
    its server, its catalog; nothing else. Everything it started is reaped, and its directory removed, whatever
    happens. Raises :class:`_Unread`."""
    from aew.errors import ContainmentUnavailable, HarnessIncompatible, HarnessLaunchFailed
    from aew.harness import containment, procs, supervisor, weaker_register
    from aew.harness.containment import netns

    bound = _bound(pin)
    until = time.monotonic() + bound
    run_dir = runlog.run_dir(engine.aew_root, f"doctor-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-"
                                              f"{secrets.token_hex(3)}")
    contract = _contract(run_dir, pin, policy)
    marker = run_dir / "label.json"
    weaker = None
    tree = None
    network = None
    try:
        try:
            Path(contract.workspace).mkdir(parents=True)  # inside the try: what it made is removed (#367, F6)
            Path(contract.scratch).mkdir(parents=True)
        except OSError as exc:
            raise _Unread(f"its directory could not be made ({type(exc).__name__}: {exc})", red=False) from None
        try:
            layout, label, network, weaker = supervisor.contain_launch(
                policy, adapter_cls, provider=pin.get("provider"), provider_env=contract.extra["provider_env"],
                role=contract.role, scope=contract.scope, workspace=contract.workspace, run_dir=run_dir,
                scratch=contract.scratch, bridge_dir=None, bridge=None, project=engine.repo_root,
                aew_root=engine.aew_root, kind="doctor_model_list", marker=marker)
        except HarnessIncompatible as exc:  # a launch is refused for it, so the row is red (#367, F4)
            reason = exc.details.get("reason")
            raise _Unread(f"a launch would be refused{' (' + str(reason) + ')' if reason else ''}: {exc.message}"
                          + ("; the provider-key row says the same" if reason == netns.PROVIDER_KEY_MISSING else ""),
                          red=True) from None
        except ContainmentUnavailable as exc:
            raise _Unread(f"a launch's containment was not established here, so the list was not read: {exc.message}",
                          red=False) from None
        # The tree first: from here, the network it holds is closed whatever fails (review of #367, F7).
        tree = procs.ProcessTree(layout=layout, network=network)  # no layout and no network off Linux
        marker.write_text(json.dumps(label, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        adapter = adapter_cls(tree, run_dir, lambda _event: None)
        if weaker is not None:
            weaker.started()
        try:
            # As every launch's server carries it, so a server that outlives doctor is found by its marker (#367, F3)
            listing = adapter.read_model_list(contract, {weaker_register.MARKER: str(marker)}, until=until)
        except HarnessIncompatible as exc:
            raise _Unread(f"a launch would be refused: {exc.message}", red=True) from None
        except (HarnessLaunchFailed, AEWError) as exc:
            raise _Unread(f"the harness did not start as a launch starts it: {exc.message}; a launch from here fails "
                          "the same way (see `aew harness status` after one, or run `aew doctor --refresh` again)",
                          red=True) from None
        except OSError as exc:
            raise _Unread(f"the harness did not start as a launch starts it: {type(exc).__name__}: {exc}",
                          red=True) from None
        if listing.get("empty"):
            raise _Unread(f"{pin['harness']} offered no model at all within its catalog wait, as a launch waits for "
                          "it: a launch from here would be refused the same way, which is timing-dependent, never a "
                          "lasting answer about the pinned model. Check the network the execution policy allows for "
                          "the harness's model catalog and the provider variables it names, then run "
                          "`aew doctor --refresh`", red=True)
        if not listing.get("complete"):
            raise _Unread(f"the model list was not read within {bound:.0f}s, a launch's own start deadline "
                          f"({supervisor.START_ENV}), so a launch from here would be abandoned the same way; check "
                          "the network the execution policy allows for the harness's model catalog, or raise "
                          f"{supervisor.START_ENV}, then run `aew doctor --refresh`", red=True)
        return listing
    finally:
        if tree is not None:
            tree.kill()
        elif network is not None:
            network.close()
        if weaker is not None:  # ended once its processes are proven ended (G3 addendum 7, ruling 2)
            weaker.end(tree.survivors() if tree is not None else [])
        containment.retire_private_git(run_dir)
        keep = weaker is not None and weaker.data.get("outcome") != "clean"  # the entry's marker names label.json
        for path in run_dir.iterdir() if run_dir.is_dir() else ():
            if keep and path.name == "label.json":
                continue
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
        if not keep:
            shutil.rmtree(run_dir, ignore_errors=True)
