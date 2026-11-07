"""The capability register's core (STG-15, CAP-1; A-38: CAPR-02, CAPR-03, CAPR-04, CAPR-12, CAPR-13).

Every status has its planted controls: the right case, the wrong case and the missing one. Gate rows shown here:
CAPR-Q01 (a payload with one byte changed reads REFUSED with the reason, at import and at the next check), Q04 (status
follows the health check: broken -> UNAVAILABLE with its cause, re-pinned -> STALE until checked, never checked ->
NOT_ESTABLISHED) and Q05 (offline, a bundle import makes the capability FUNCTIONAL_ONLY). The provider is a stand-in
with ripgrep's shape: a `/bin/sh` script of builtins on POSIX, a copy of Windows' own `findstr.exe` on Windows, each
pinned like ripgrep's payloads, in an archive built here. Nothing is fetched from the network.
"""

from __future__ import annotations

import copy
import io
import json
import os
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from capability_stand_in import (
    KEY,
    MEMBER,
    SOURCE,
    _archive,
    _bundle,
    _health,
    _import,
    _plant_host_copy,
    _principal,
    _record,
    _sha,
    make_register,
)
from conftest import IS_WINDOWS

from aew import errors, process_kind
from aew.capability import ops, records, status, store
from aew.capability import payload as P

URLOPEN = urllib.request.urlopen  # the real one: `make_register` replaces it with one that fails the test


@pytest.fixture
def reg(tmp_path, monkeypatch):
    return make_register(tmp_path, monkeypatch)


def test_a_workers_own_aew_neither_fetches_nor_records_and_the_operators_does(reg, monkeypatch):
    """The register is the operator's, and AEW downloads no tool the operator did not choose (the operator,
    2026-11-05). An agent's own `aew` starts on its allow-listed environment, so where no sandbox holds it, a fetch and
    a record would land in a register of its choosing: its `aew capability check` is refused before anything is read,
    and a self-test's results are not recorded. The operator's check fetches and records."""
    asked: list[Any] = []

    def fetched(pinned: dict[str, Any]) -> bytes:
        asked.append(pinned)
        return reg["archive"]

    monkeypatch.setattr(P, "fetch", fetched)
    tools = {"fake": {"tried": [{"ok": True, "cause": None, "path": "x", "sha256": "0" * 64, "record_digest": "d",
                                 "version": "v", "kind": status.AEW_COPY}]}}
    key = f"{status.AEW_COPY}:fake"
    for worker in ("aew (worker run)", "aew (contained Lead)"):
        with process_kind.declared_as(worker):
            with pytest.raises(errors.PermissionDenied) as refused:
                ops.check()
            assert refused.value.details["reason"] == "operator_only" and "operator" in refused.value.message
            ops.record_contained(tools)
    assert asked == [] and key not in (store.read().get("checks") or {})
    ops.record_contained(tools)
    assert key in store.read()["checks"]
    ops.check("fake")
    assert asked


CHECK, APPLY = ("aew.capability.ops", "check"), ("aew.capability.ops", "apply")
GET, ASK = ("aew.capability.consent", "get"), ("aew.capability.consent", "ask")
Name = tuple[str, str]  # (module, its top-level name or Class.method)


def _aliases(tree: Any, mod: str, is_package: bool, modules: set[str]) -> dict[str, tuple[str, str | None]]:
    """Each name a module imports, anywhere in it: (a module, None) or (a module, a name in it)."""
    import ast

    package = mod if is_package else mod.rpartition(".")[0]
    out: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
            for a in node.names:
                full = f"{base}.{a.name}"
                out[a.asname or a.name] = (full, None) if full in modules else (base, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = (a.name if a.asname else a.name.split(".")[0], None)
    return out


def _used(node: Any, mod: str, alias: dict[str, tuple[str, str | None]], modules: set[str]) -> set[Name]:
    """What ``node`` names: a name of its own module, an imported name, or a name reached through an imported
    module."""
    import ast

    found: set[Name] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            target = alias.get(n.id)
            found.add((target[0], target[1]) if target and target[1] else (mod, n.id))
        elif isinstance(n, ast.Attribute):
            chain, value = [n.attr], n.value
            while isinstance(value, ast.Attribute):
                chain.insert(0, value.attr)
                value = value.value
            if isinstance(value, ast.Name) and value.id in alias and alias[value.id][1] is None:
                whole = ".".join([str(alias[value.id][0]), *chain])
                owner = max((m for m in modules if whole == m or whole.startswith(m + ".")), key=len, default=None)
                if owner is not None and whole != owner:
                    found.add((owner, whole[len(owner) + 1:].split(".")[0]))
    return found


def _references() -> dict[Name, set[Name]]:
    """What each function in AEW's source names, by name, within a module or through an imported module."""
    import ast

    src = Path(ops.__file__).resolve().parents[2]
    files = {".".join(f.relative_to(src).with_suffix("").parts).removesuffix(".__init__"): f
             for f in src.joinpath("aew").rglob("*.py")}
    modules = set(files)
    refs: dict[Name, set[Name]] = {}
    for mod, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        alias = _aliases(tree, mod, path.name == "__init__.py", modules)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                refs.setdefault((mod, node.name), set()).update(_used(node, mod, alias, modules))
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    name = f"{node.name}.{item.name}" if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        else node.name
                    refs.setdefault((mod, name), set()).update(_used(item, mod, alias, modules))
            else:
                refs.setdefault((mod, "<module>"), set()).update(_used(node, mod, alias, modules))
    return refs


def _reach(refs: dict[Name, set[Name]], start: Name, doors: tuple[Name, ...] = ()) -> set[Name]:
    """Every function from which ``start`` can be reached, not following past a door."""
    reached, todo = set(), [start]
    while todo:
        target = todo.pop()
        for caller, used in refs.items():
            if target in used and caller not in reached and caller != target:
                reached.add(caller)
                if caller not in doors:  # a door: what reaches it is the door's own caller, below
                    todo.append(caller)
    return reached


def _callers(refs: dict[Name, set[Name]], target: Name) -> set[Name]:
    return {c for c, used in refs.items() if target in used}


def test_no_route_but_the_operators_own_commands_reaches_the_fetch():
    """The operator, 2026-11-05: AEW downloads no tool unless the operator chooses it. Every function in AEW's source
    from which ``payload.fetch`` can be reached, by name, within a module or through an imported module, comes through
    one of three doors: ``ops.check`` (`aew capability check`, which downloads only a tool it names), ``consent.get``
    (what the operator chose: at `aew init`, at the Lead's start and by `aew capability fetch`), each refused to an
    agent's own `aew` and to the Lead's broker, and ``ops.apply`` (an add the operator approved at the operator
    endpoint, with its principal). Nothing else reaches the download, and each door's callers are named. A worker's
    launch, the broker, a supervisor or an agent's tool that came to reach it another way would be named here. Its
    limit: a method called through an object is not followed, so a door's caller that is a method is named, never its
    own callers."""
    refs = _references()
    reached = _reach(refs, ("aew.capability.payload", "fetch"), (CHECK, APPLY, GET))
    assert reached == {("aew.capability.ops", n) for n in ("_fetched", "fetch", "_add_downloads")} | {
        CHECK, APPLY, GET}, sorted(reached)  # `_apply_add` installs what was downloaded before the lock
    assert _callers(refs, CHECK) == {("aew.cli.capability_commands", "_check"), GET}
    assert _callers(refs, GET) == {("aew.capability.consent", n) for n in ("at_init", "at_lead_start", "at_fetch")}
    assert _callers(refs, APPLY) == {("aew.harness.operator_endpoint", "OperatorEndpoint._capability_change")}
    assert _callers(refs, ("aew.capability.consent", "at_init")) == {("aew.cli.commands", "_init")}
    hook = ("aew.harness.opencode.lead", "_tools_before_the_tui")  # after the start's own refusals, both branches
    assert _callers(refs, ("aew.capability.consent", "at_lead_start")) == {hook}
    assert _callers(refs, hook) == {("aew.harness.opencode.lead", "run")}
    assert _callers(refs, ("aew.capability.consent", "at_fetch")) == {("aew.cli.capability_commands", "_fetch")}


def test_only_the_operators_three_moments_reach_the_consent_screen():
    """The designer's ruling (STG-15, 2026-11-05): a worker's launch never asks and never downloads, since no human is
    there. The screen is reached through `aew init`, the Lead's start and `aew capability fetch` only, each with the
    one caller the test above names: no supervisor, containment, adapter or broker reaches it any other way."""
    refs = _references()
    entries = tuple(("aew.capability.consent", n) for n in ("at_init", "at_lead_start", "at_fetch"))
    assert _reach(refs, ASK, entries) == set(entries), sorted(_reach(refs, ASK, entries))
    assert _reach(refs, ("aew.capability.consent", "read_terminal"), entries) == set(entries)


def test_a_fetch_error_never_carries_its_text_into_the_status_the_record_or_the_line(reg, monkeypatch, capsys):
    """The designer's rule 1: a proxy's URL can carry its credentials, and a fetch's error can carry that URL. The
    status, the register's record, the run's record and the operator's line say why in AEW's own words, a closed
    reason. The fetch is the operator's `aew capability check`'s, the only one there is."""
    import urllib.error

    proxy = "http://user:hunter2@proxy.invalid:3128"
    monkeypatch.setenv("HTTPS_PROXY", proxy)

    def through_the_proxy(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.URLError(f"Tunnel connection failed via {proxy}: 407 Proxy Authentication Required")

    monkeypatch.setattr("urllib.request.urlopen", through_the_proxy)
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    with pytest.raises(errors.Unavailable) as raised:
        P.fetch(records.shipped()["fake"]["payloads"][records.platform_key()])
    assert "hunter2" not in raised.value.message and raised.value.details["fetch_reason"] == "unreachable"
    checked = ops.check("fake")
    flags = ops.flag_missing({"fake": {"command": "fake", "served": None, "path": None}})
    said = json.dumps([store.read(), ops.listing(), checked, flags, ops.run_record(flags)], default=str)
    said += capsys.readouterr().err
    assert "hunter2" not in said and "user:" not in said, said
    failed = store.read()["fetch_failures"][f"fake:{records.platform_key()}"]
    assert failed["code"] == "unreachable" and P.FETCH_REASONS["unreachable"] in failed["reason"]
    assert flags and flags[0]["reason"] == "fetch_failed"


def test_a_source_with_a_user_in_it_is_shown_without_one():
    assert P.shown_source("https://u:p@example.invalid/a.tgz") == "https://example.invalid/a.tgz"
    assert P.shown_source("https://example.invalid/a.tgz") == "https://example.invalid/a.tgz"


def _garbling_proxy() -> tuple[str, Any]:
    """A loopback stand-in proxy that answers a CONNECT with something that is not HTTP, and its closer."""
    import socket
    import threading

    server = socket.create_server(("127.0.0.1", 0))
    server.settimeout(10)

    def serve() -> None:
        try:
            conn, _ = server.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(10)
            try:
                conn.recv(4096)
                conn.sendall(b"this is not http\r\n\r\n")
            except OSError:
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    def close() -> None:
        server.close()
        thread.join(10)

    return f"http://user:hunter2@127.0.0.1:{server.getsockname()[1]}", close


@pytest.mark.parametrize("proxy, code", [("garbles", "unreachable"), ("http://user:hunter2@127.0.0.1:notaport",
                                                                     "bad_source")])
def test_a_proxy_that_breaks_http_gives_a_closed_reason_never_a_crash(reg, monkeypatch, capsys, proxy, code):
    """Quick check of #330, m-b: `http.client`'s own errors (a proxy that answers in something other than HTTP, a
    proxy port that is not a number) are a closed reason too, through the real `urllib` and only to the loopback: the
    operator's check records the failure, and no output carries the proxy's synthetic credential."""
    import urllib.request

    monkeypatch.setattr("urllib.request.urlopen", URLOPEN)
    monkeypatch.setattr(urllib.request, "_opener", None)  # urlopen's opener reads the proxy once: rebuild it
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY",
                 "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    close = None
    if proxy == "garbles":
        proxy, close = _garbling_proxy()
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    try:
        checked = ops.check("fake")
    finally:
        if close:
            close()
    flags = ops.flag_missing(STUB)
    said = json.dumps([checked, store.read(), ops.listing(), flags], default=str) + capsys.readouterr().err
    assert "hunter2" not in said and "user:" not in said, said
    assert store.read()["fetch_failures"][f"fake:{records.platform_key()}"]["code"] == code
    assert [f["reason"] for f in flags] == ["fetch_failed"]


def test_a_source_with_a_user_or_password_is_refused_at_add_and_on_a_read_without_repeating_it(reg):
    """Quick check of #330, m-b: a source with a user and password in it is refused, so the register, which every
    sandbox reads, never keeps one; and the refusal says so in AEW's words, never the source's."""
    _import(reg)
    before = (reg["root"] / store.REGISTER).read_bytes()
    record = _record(reg["body"], reg["archive"], description="with a user")
    record["payloads"][KEY] = {**record["payloads"][KEY], "source": SOURCE.replace("https://", "https://u:hunter2@")}
    with pytest.raises(errors.ValidationFailed) as refused:
        _add(reg, record)
    said = json.dumps(refused.value.to_dict())
    assert "user or password" in said and "hunter2" not in said, said
    assert (reg["root"] / store.REGISTER).read_bytes() == before
    with pytest.raises(errors.ValidationFailed):  # the schema's own pattern refuses it as well
        from aew import schemas
        schemas.validate("capability-records", {"schema": records.SCHEMA, "providers": {"fake": record}}, source="t")
    state = store.read()  # one kept from before: refused on a read, without the password
    state["operator_records"]["fake"] = {"record": record, "base_digest": records.digest(reg["shipped"]["fake"])}
    with store.locked() as root:
        store.write(state, root)
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "user or password" in cap["cause"]
    assert "hunter2" not in json.dumps(ops.listing(), default=str), ops.listing()


STUB = {"fake": {"command": "fake", "served": None, "path": None}}


def test_a_launch_without_the_pinned_copy_flags_it_once_per_state_and_one_with_it_says_nothing(reg, monkeypatch,
                                                                                                capsys):
    """The operator, 2026-11-05: a launch that goes on without a pinned tool never does it quietly. One line per tool
    and state on the operator's terminal (the designer's rule 2), a change of state says so again, and a tool bound
    again clears it. The line never names a download: a launch never makes one."""
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    first = ops.flag_missing(STUB)
    line = capsys.readouterr().err
    assert line.count("\n") == 1 and line.startswith("aew: attention: fake in this run is a stub that fails"), line
    assert "it is not installed on this host" in line and "The run goes on" in line
    assert "`aew capability fetch fake` downloads it" in line.split("Fix:")[1]  # the operator's own choice to make
    assert "aew capability import" in line and "fetch" not in line.split("Fix:")[0], line
    assert "download" not in line.split("Fix:")[0], line  # the launch itself never names one: it never makes one
    assert [f["reason"] for f in first] == ["not_installed"]
    assert ops.flag_missing(STUB) == first and capsys.readouterr().err == ""  # the record keeps it; no repeat
    pinned = records.shipped()["fake"]["payloads"][records.platform_key()]
    with store.locked():
        state = store.read()
        state["fetch_failures"][f"fake:{records.platform_key()}"] = {
            "at": "2026-11-05T00:00:00Z", "reason": "x", "sha256": pinned["sha256"], "code": "unreachable"}
        store.write(state)
    ops.flag_missing(STUB)
    assert "the fetch failed (at 2026-11-05T00:00:00Z)" in capsys.readouterr().err  # a new state says so again
    assert ops.flag_missing({"fake": {"command": "fake", "served": status.AEW_COPY, "path": "x"}}) == []
    assert capsys.readouterr().err == "" and "fake" not in store.read()["flagged"]  # bound: nothing, and cleared
    ops.flag_missing(STUB)
    assert "aew: attention: fake" in capsys.readouterr().err  # missing again: said again


def test_twenty_runs_without_the_pinned_copy_give_twenty_records_and_one_flag(reg, monkeypatch, capsys):
    """The operator, 2026-11-05: "the missing tool acts the same as missing skills and is logged and not voided".
    Every run's record carries every missing tool with its closed reason, as a run's missing skills are kept; the
    operator's line is once per tool and state, and it never removes a tool from a record."""
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    runs = [ops.run_record(ops.flag_missing(STUB)) for _ in range(20)]
    assert capsys.readouterr().err.count("aew: attention: fake") == 1
    assert len(runs) == 20 and all(r["unavailable"] == ["fake"] and r["reasons"] == {"fake": "not_installed"}
                                   and [d["served"] for d in r["detail"]] == ["stub"] for r in runs), runs


def test_the_flag_goes_only_to_the_operators_terminal(reg, monkeypatch, capsys):
    """A supervisor's stderr is its run's log, and a worker's own `aew` is the agent's: neither prints the line, and
    neither marks it seen, so the operator's next launch at a terminal says it. Each run's record still has it."""
    monkeypatch.setattr(ops, "_to_terminal", lambda: False)
    assert ops.flag_missing(STUB) and capsys.readouterr().err == ""
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    with process_kind.declared_as("aew (worker run)"):
        assert ops.flag_missing(STUB) and capsys.readouterr().err == ""
    ops.flag_missing(STUB)
    assert "aew: attention: fake" in capsys.readouterr().err


def test_a_refused_launch_neither_says_the_run_goes_on_nor_marks_the_flag_seen(reg, monkeypatch, capsys):
    """Quick check of #330, m-a: the line says "The run goes on", so only a launch whose self-test passed prints it and
    marks it seen; the next launch that goes on, with the same tool missing, says it. The sandbox's pieces are stood
    in for, in process."""
    from types import SimpleNamespace

    from aew.harness import containment as C
    from aew.harness.containment import probe

    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    monkeypatch.setattr(C, "supported", lambda: True)
    monkeypatch.setattr(C, "for_run", lambda **_k: SimpleNamespace(net_dir=None))
    monkeypatch.setattr(C, "retire_private_git", lambda *_a, **_k: None)
    monkeypatch.setattr(C, "label", lambda **k: {"contained": k.get("contained")})
    monkeypatch.setattr(probe, "mechanism", lambda _layout: "stand-in")
    verdict = {"ok": False}
    monkeypatch.setattr(probe, "self_test", lambda *_a, **_k: {"ok": verdict["ok"], "reason": "stand-in failure",
                                                                "tools": {"fake": {**STUB["fake"], "tried": []}}})
    base = reg["root"].parent
    (base / "ws").mkdir()
    launch: dict[str, Any] = dict(role="reviewer", scope="ticket", workspace=str(base / "ws"),
                                  run_dir=base / "runs" / "r1", scratch=str(base / "s"), bridge_dir=None,
                                  policy={"containment": {"mode": "required"}}, project=str(base))
    with pytest.raises(errors.ContainmentUnavailable):
        C.establish(**launch)
    assert capsys.readouterr().err == "" and "fake" not in (store.read().get("flagged") or {})
    verdict["ok"] = True
    _, label = C.establish(**launch)
    assert "aew: attention: fake" in capsys.readouterr().err and label["missing_tools"]["unavailable"] == ["fake"]


@pytest.mark.parametrize("tried, reason", [([{"kind": status.AEW_COPY, "ok": False}], "check_failed"),
                                           ([], "not_served_here")])
def test_a_checked_copy_that_did_not_serve_this_run_says_why_from_the_runs_own_evidence(reg, monkeypatch, capsys,
                                                                                         tried, reason):
    """Quick check of #330, m-c: AEW's copy reads usable (checked, and it passed), but this run got the stub, its own
    result not recorded yet (the short lock gave way, or the register is masked). The reason is the run's own: its
    check failed inside, or the copy did not serve there; never "it was never checked"."""
    _import(reg)
    assert store.read()["checks"][f"{status.AEW_COPY}:fake"]["ok"] is True
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    flags = ops.flag_missing({"fake": {**STUB["fake"], "tried": tried}})
    line = capsys.readouterr().err
    assert [f["reason"] for f in flags] == [reason] and status.NOT_SERVING_WHY[reason] in line, line
    assert "never checked" not in line


def test_a_flag_line_that_cannot_be_written_never_stops_the_launch(reg, monkeypatch):
    """Quick check of #330, m-d (CAPR-12): the operator's terminal went away between the check and the write. The line
    is lost; the run's record keeps the tool."""

    class Gone:
        def write(self, _text: str) -> int:
            raise BrokenPipeError("the terminal went away")

    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    monkeypatch.setattr(ops.sys, "stderr", Gone())
    assert [f["tool"] for f in ops.flag_missing(STUB)] == ["fake"]


def test_a_launch_behind_a_long_holder_of_the_lock_gives_way_and_the_next_records_it(reg, monkeypatch):
    """CAPR-12: recording a check never stops a launch for as long as a register command may wait."""
    monkeypatch.setattr(store, "RECORD_WAIT_S", 0.2)
    monkeypatch.setattr(store, "LOCK_TIMEOUT_S", 20.0)
    tools = {"fake": {"tried": [{"ok": True, "cause": None, "path": "x", "sha256": "0" * 64, "record_digest": "d",
                                 "version": "v", "kind": status.AEW_COPY}]}}
    started = time.monotonic()
    with store.locked():
        ops.record_contained(tools)
        spent = time.monotonic() - started
    assert spent < 10.0, spent  # the short wait, well before the store's own would have ended
    key = f"{status.AEW_COPY}:fake"
    assert key not in (store.read().get("checks") or {})
    ops.record_contained(tools)
    assert store.read()["checks"][key]["where"] == status.IN_SANDBOX


def _cap(cap: str = "FAKE_SEARCH") -> dict[str, Any]:
    return next(c for c in ops.listing()["capabilities"] if c["id"] == cap)


# ---------------------------------------------------------------------------------------------- the records


def test_the_shipped_records_validate_and_name_capabilities_in_d01_form():
    shipped = records.validate(records.load_yaml(records.SHIPPED_TEXT, source="shipped"), source="shipped")
    rg = shipped["ripgrep"]
    assert rg["capabilities"] == ["EXACT_CODE_SEARCH", "TEXT_SEARCH"] and rg["command"] == "rg"
    assert rg["placement"] == "sandbox" and rg["path"] == "first" and rg["needs"] == {
        "network": False, "credentials": False, "providers": []}
    assert set(rg["payloads"]) == {"linux-x86_64", "linux-aarch64", "windows-x86_64"}
    for key, pinned in rg["payloads"].items():  # every payload is the release's own archive of this version
        assert pinned["source"].startswith(f"https://github.com/BurntSushi/ripgrep/releases/download/{rg['version']}/")
        assert pinned["member"].endswith("/rg.exe" if key.startswith("windows") else "/rg")
    assert rg["health"]["version"]["expect"] == f"ripgrep {rg['version']}"


# The first bundle's other five (FIRST-BUNDLE.md): provider, command, capability
FIRST_BUNDLE = {"fd": ("fd", "FILE_FIND"), "jq": ("jq", "JSON_QUERY"), "yq": ("yq-go", "YAML_QUERY"),
                "ast-grep": ("ast-grep", "STRUCTURAL_CODE_SEARCH"), "universal-ctags": ("uctags", "SYMBOL_OUTLINE")}


def test_the_first_bundle_ships_each_member_optional_under_an_unambiguous_name_for_windows_and_linux():
    """Each of the five has a record with a payload for Windows and for Linux x86_64 (the operator's hosts), is
    optional (the harness runs none of them) and comes last on PATH under its own name, so a project's own tool keeps
    the plain name (CAPR-04). yq and ctags have other implementations under the plain name, and Rocky 8's `sg` is
    shadow-utils', so none of those names is AEW's. Universal Ctags' check names the variant: Rocky 8's Exuberant
    `ctags` never passes as it."""
    shipped = records.shipped()
    assert set(shipped) == {"ripgrep", *FIRST_BUNDLE}, sorted(shipped)
    for name, (command, capability) in FIRST_BUNDLE.items():
        record = shipped[name]
        assert (record["command"], record["capabilities"]) == (command, [capability]), name
        assert record["path"] == "own_name" and not records.needed(record), name
        assert record["placement"] == "sandbox" and record["effect"] == "read_only", name
        assert {"linux-x86_64", "windows-x86_64"} <= set(record["payloads"]), name
        for key, pinned in record["payloads"].items():
            assert P.kind(pinned["source"]) == P.EXECUTABLE or pinned["member"].rsplit("/", 1)[-1] in (
                "ast-grep", "ast-grep.exe", "ctags", "ctags.exe", "fd", "fd.exe", "yq_linux_amd64",
                "yq_windows_amd64.exe"), (name, key)
    assert {r["command"] for r in shipped.values()}.isdisjoint({"yq", "ctags", "sg"})
    ctags = shipped["universal-ctags"]["health"]["version"]
    assert ctags["expect"].startswith("Universal Ctags") and not "Exuberant Ctags 5.8".startswith(ctags["expect"])
    assert P.kind(shipped["jq"]["payloads"]["linux-x86_64"]["source"]) == P.EXECUTABLE
    assert P.kind(shipped["ast-grep"]["payloads"]["linux-x86_64"]["source"]) == P.ZIP  # the manylinux_2_28 wheel


@pytest.mark.parametrize("source, kind", [
    ("https://h/a/x-1.0.tar.gz", P.TAR_GZ), ("https://h/a/x-1.0.zip", P.ZIP), ("https://h/a/x-1.0-py3-none.whl", P.ZIP),
    ("https://h/a/x-linux-amd64", P.EXECUTABLE), ("https://h/a/x-windows-amd64.exe", P.EXECUTABLE),
    ("https://h/a/x-1.0.ZIP", P.ZIP), ("https://h/a/x-1.0.Tar.Gz", P.TAR_GZ),  # endings compare without case
    ("https://h/a/x-1.0.tar.xz", P.EXECUTABLE),  # not an archive AEW reads: its record is refused (below)
])
def test_a_payloads_kind_is_its_sources_ending(source, kind):
    assert P.kind(source) == kind


@pytest.mark.parametrize("ending", [".tar.xz", ".tgz", ".tar.bz2", ".tar.zst", ".7z", ".gz", ".XZ", ".bz2", ".rar",
                                    ".tar"])
def test_an_archive_aew_does_not_read_is_refused_never_taken_for_a_bare_executable(reg, ending):
    """Review of #349, m2: with the download's own digest as both pins, such a record would validate as a bare
    executable and fail only at its health check, naming the wrong cause; it is refused at validation, saying what
    AEW reads. The control: the same payload as a bare executable validates."""
    record = copy.deepcopy(reg["shipped"]["fake"])
    record["payloads"][KEY] = _bare(reg["body"])
    records.validate({"schema": records.SCHEMA, "providers": {"fake": copy.deepcopy(record)}}, source="test")
    record["payloads"][KEY]["source"] += ending
    with pytest.raises(errors.ValidationFailed) as exc:
        records.validate({"schema": records.SCHEMA, "providers": {"fake": record}}, source="test")
    assert "AEW reads only .tar.gz, .zip and .whl archives" in json.dumps(exc.value.to_dict())


def test_a_bare_payload_off_its_pin_is_refused_by_member_itself():
    """Review of #349, n1: the second check of a bare download, for a caller that skipped the first."""
    pinned = {"source": "https://example.invalid/fake-linux-amd64", "archive_sha256": _sha(GOOD),
              "archive_size": len(GOOD), "sha256": _sha(GOOD), "size": len(GOOD)}
    assert P.member(GOOD, pinned) == GOOD
    with pytest.raises(P.PinMismatch) as exc:
        P.member(GOOD + b"x", pinned)
    assert exc.value.details["reason"] == "payload_pin"


def test_the_sandbox_checks_the_needed_tools_first(tmp_path, monkeypatch):
    """Review of #349, m1: the self-test checks the plan's tools in order, under one budget for all of them, so
    ripgrep, the one tool the harness needs, comes before the optional five, though it does not sort first by name."""
    from aew.capability import bind

    monkeypatch.setattr(store, "ROOT_OVERRIDE", tmp_path / "register")
    names = [t.provider for t in bind.plan()]
    assert names[0] == "ripgrep" and sorted(names) != names, names
    assert names[1:] == sorted(n for n in records.shipped() if not records.needed(records.shipped()[n]))


def _bare(body: bytes, **change: Any) -> dict[str, Any]:
    return {"source": "https://example.invalid/releases/fake-linux-amd64", "archive_sha256": _sha(body),
            "archive_size": len(body), "sha256": _sha(body), "size": len(body), **change}


@pytest.mark.parametrize("base, change, refused", [
    ("bare", lambda p, body: p.update(member="fake"), "has no `member`"),
    ("bare", lambda p, body: p.update(archive_sha256=_sha(body + b"x")), "are the same"),
    ("bare", lambda p, body: p.update(archive_size=len(body) + 1), "are the same"),
    ("archive", lambda p, body: p.pop("member"), "names the executable in it"),
    ("archive", lambda p, body: (p.pop("member"), p.update(source="https://example.invalid/fake-1.0-py3-none.whl")),
     "names the executable in it"),
])
def test_a_payloads_member_follows_its_kind(reg, base, change, refused):
    """An archive names its one member; a bare executable names none, and its download's pin is the executable's.
    Each base validates as it stands (the right case), and each change is refused saying why."""
    record = copy.deepcopy(reg["shipped"]["fake"])
    if base == "bare":
        record["payloads"][KEY] = _bare(reg["body"])
    records.validate({"schema": records.SCHEMA, "providers": {"fake": copy.deepcopy(record)}}, source="test")
    change(record["payloads"][KEY], reg["body"])
    with pytest.raises(errors.ValidationFailed) as exc:
        records.validate({"schema": records.SCHEMA, "providers": {"fake": record}}, source="test")
    assert refused in json.dumps(exc.value.to_dict()), exc.value.to_dict()


@pytest.mark.parametrize("change, refused", [
    (lambda r: r.update(placement="host"), "host placement"),
    (lambda r: r["needs"].update(credentials=True), "place"),  # CAPR-Q11's words: it belongs on the host
    (lambda r: r["needs"].update(network=True), "widen"),
    (lambda r: r["needs"].update(providers=["other"]), "other providers"),
    (lambda r: r["payloads"][KEY].update(member="../escape"), "parent directory"),
    (lambda r: r.update(capabilities=["exact_code_search"]), "does not match"),  # not D-01's form
    (lambda r: r.update(extra=1), "does not match"),
])
def test_a_record_that_fails_validation_is_refused_with_its_reason(reg, change, refused):
    record = copy.deepcopy(reg["shipped"]["fake"])
    change(record)
    with pytest.raises(errors.ValidationFailed) as exc:
        records.validate({"schema": records.SCHEMA, "providers": {"fake": record}}, source="test")
    assert refused in json.dumps(exc.value.to_dict()), exc.value.to_dict()


def test_platform_keys():
    assert records.platform_key("linux", "x86_64") == "linux-x86_64"
    assert records.platform_key("linux", "aarch64") == "linux-aarch64"
    assert records.platform_key("win32", "AMD64") == "windows-x86_64"
    assert records.platform_key("sunos5", "sparc") == "sunos5-sparc"  # no record names it: UNSUPPORTED


# ---------------------------------------------------------------------------------------------- the statuses


def test_where_no_context_is_contained_the_status_says_the_download_stays_reachable(reg):
    """CAP-1 PR 2: no sandbox on Windows, so no bind, and its capabilities say so. A Linux run the policy allows to be
    weaker says so on its label, as a register per host cannot know one project's policy."""
    from aew.harness import containment

    assert _cap()["limitations"] == ([status.NOT_BOUND] if IS_WINDOWS else [])
    assert "download stays reachable" in status.NOT_BOUND
    assert containment.label(contained=False)["register_tools"] == status.NOT_BOUND
    assert "register_tools" not in containment.label(contained=True, mechanism="m")


def test_a_payload_not_installed_reads_unavailable_with_its_cause_and_fix(reg):
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and cap["assessment_status"] == status.NOT_ESTABLISHED
    assert cap["cause"] == "its pinned payload is not on this host: it is not installed"
    assert "`aew capability fetch fake` downloads it" in cap["fix"] and "aew capability import" in cap["fix"]


def test_q05_an_offline_bundle_import_makes_the_capability_functional_only(reg):
    """CAPR-Q05 (and CAPR-X01's status half): with no network, the import checks the pin, installs the executable
    and runs its health check. The register's state and change log say so."""
    out = _import(reg)
    assert [i["provider"] for i in out["imported"]] == ["fake"] and "passed" in out["imported"][0]["check"]
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["pinned"] and cap["cause"] is None
    assert cap["version"] == "1.0" and cap["checked_at"]
    installed = Path(cap["path"])
    assert installed.read_bytes() == reg["body"] and installed.parent.parent.parent.name == store.PAYLOADS
    assert sorted(p.name for p in installed.parent.iterdir()) == [installed.name]  # a directory of its own
    log = [json.loads(line) for line in (reg["root"] / store.CHANGES).read_text(encoding="utf-8").splitlines()]
    assert log[-1]["command"] == "import" and log[-1]["principal"]["guarantee"] == "dev"
    assert log[-1]["authorized_by"] == "operator-endpoint" and "challenge_code" not in json.dumps(log)


def test_a_renamed_archive_still_imports_by_its_digest(reg):
    _import(reg, name="renamed.tar.gz")
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_q01_an_archive_with_one_byte_changed_is_refused_at_import(reg):
    """...matched by the archive's own digest, so the operator is shown the refusal before approving anything."""
    tampered = bytearray(reg["archive"])
    tampered[len(tampered) // 2] ^= 1
    bundle = _bundle(reg, data=bytes(tampered))
    change = ops.preview(ops.IMPORT, {"path": str(bundle)})
    assert len(change.lines) == 2 and change.lines[1].startswith(f"  REFUSE {bundle / 'fake-1.0.tar.gz'} for fake")
    assert "does not match its pin" in change.lines[1]
    out = ops.apply(_principal(), change)
    assert out["imported"] == [] and "does not match its pin" in out["refused"][0]["reason"]
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "does not match its pin" in cap["cause"]
    assert not (reg["root"] / store.PAYLOADS).exists() or not any((reg["root"] / store.PAYLOADS).rglob("fake*"))


def test_a_refused_import_never_makes_a_good_installed_payload_read_refused(reg, monkeypatch):
    """Review F4: a good import, then a bundle whose archive is refused, then `check`: the installed payload matches
    its pin, so it reads FUNCTIONAL_ONLY before the check and after it, which clears the earlier refusal; the host's
    unpinned copy never serves in its place."""
    _import(reg)
    _plant_host_copy(reg, monkeypatch)
    tampered = bytearray(reg["archive"])
    tampered[len(tampered) // 2] ^= 1
    out = _import(reg, data=bytes(tampered))
    assert out["imported"] == [] and out["refused"]
    assert store.read()["refused"]  # the refused import is recorded
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.AEW_COPY
    ops.check("fake", offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.AEW_COPY
    assert store.read()["refused"] == {}


def test_q01_an_installed_payload_with_one_byte_changed_is_refused_at_the_next_check(reg, monkeypatch):
    """...and removed, so a later check fetches it again: online, the pinned archive comes back FUNCTIONAL_ONLY."""
    _import(reg)
    installed = Path(_cap()["path"])
    os.chmod(installed, 0o700)
    data = bytearray(installed.read_bytes())
    data[-1] ^= 1
    installed.write_bytes(bytes(data))
    assert _cap()["observed_status"] == status.REFUSED  # every read checks the pin, not only a check
    said = ops.check("fake")["checked"]["fake"]
    assert any("refused its installed payload" in s for s in said), said
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "does not match its pin" in cap["cause"]
    assert not installed.exists()
    monkeypatch.setattr(P, "fetch", lambda pinned: reg["archive"])
    ops.check("fake")
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_a_check_downloads_only_a_tool_it_names_and_never_offline(reg, monkeypatch):
    """The operator, 2026-11-05: AEW downloads only what the operator chooses. A check of everything downloads nothing
    and names the command that would; naming the tool is the choice, and offline is never."""
    fetched: list[str] = []

    def fetch(pinned: dict[str, Any]) -> bytes:
        fetched.append(pinned["source"])
        return reg["archive"]

    monkeypatch.setattr(P, "fetch", fetch)
    ops.check("fake", offline=True)
    assert fetched == [] and _cap()["observed_status"] == status.UNAVAILABLE
    out = ops.check()
    assert fetched == [] and _cap()["observed_status"] == status.UNAVAILABLE
    assert any("`aew capability fetch fake` downloads it" in line for line in out["checked"]["fake"]), out["checked"]
    ops.check("fake")
    assert fetched == [SOURCE] and _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    ops.check("fake")
    assert fetched == [SOURCE]  # a payload on this host is checked, never fetched again


def test_a_failed_fetch_reads_unavailable_with_its_cause(reg, monkeypatch):
    def down(pinned: dict[str, Any]) -> bytes:
        raise errors.Unavailable("the pinned payload could not be fetched: no route", reason="fetch_failed")

    monkeypatch.setattr(P, "fetch", down)
    ops.check("fake")
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and "the fetch failed" in cap["cause"]
    assert "no route" in cap["cause"]


def test_q04_a_never_checked_payload_reads_not_established(reg):
    pinned = reg["shipped"]["fake"]["payloads"][KEY]
    P.install("fake", "fake", pinned, reg["body"])  # on the host, never checked
    assert _cap()["observed_status"] == status.NOT_ESTABLISHED
    ops.check(offline=True)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_q04_a_broken_provider_reads_unavailable_with_its_cause(reg, monkeypatch):
    broken = _record(reg["body"], reg["archive"], health=_health(expect="needle three"))
    monkeypatch.setattr(records, "shipped", lambda: {"fake": broken})
    _import(reg)
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and "its check failed" in cap["cause"]
    assert "fixture query printed" in cap["cause"] and "needle three" in cap["cause"]


def test_q04_a_re_pinned_record_reads_stale_until_it_is_checked(reg, monkeypatch):
    """A new pin: the payload checked under the old one is no proof of the new one, which is not here yet."""
    _import(reg)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    body = reg["body"] + (b"\n" if not IS_WINDOWS else b"\0")  # a different executable: a new pin
    archive = _archive(body, MEMBER)
    repinned = _record(body, archive)
    monkeypatch.setattr(records, "shipped", lambda: {"fake": repinned})
    cap = _cap()
    assert cap["observed_status"] == status.STALE and "its pin changed since it was checked" in cap["cause"]
    assert "aew capability fetch fake" in cap["fix"]
    monkeypatch.setattr(P, "fetch", lambda pinned: archive)
    ops.check("fake")
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and Path(cap["path"]).read_bytes() == body


def test_q04_a_changed_record_reads_stale_until_it_is_checked(reg, monkeypatch):
    _import(reg)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    changed = copy.deepcopy(reg["shipped"]["fake"])
    changed["description"] = "a changed record, the same pin"
    monkeypatch.setattr(records, "shipped", lambda: {"fake": changed})
    cap = _cap()
    assert cap["observed_status"] == status.STALE and "record or its pin changed" in cap["cause"]
    ops.check(offline=True)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


@pytest.mark.parametrize("fact", ["kernel", "libc", "harness"])
def test_q04_a_host_change_reads_stale_naming_it(reg, monkeypatch, fact):
    then = {"kernel": "k1", "libc": "glibc 2.28", "harness": "/opt/opencode (1 bytes, modified 1)"}
    monkeypatch.setattr(status, "host_facts", lambda: dict(then))
    _import(reg)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    monkeypatch.setattr(status, "host_facts", lambda: {**then, fact: "changed"})
    cap = _cap()
    said = "the harness this process would launch" if fact == "harness" else f"the {fact}"
    assert cap["observed_status"] == status.STALE and f"{said} changed" in cap["cause"]


def test_the_harness_fact_is_the_one_this_process_would_launch_and_its_staleness_says_so(reg, monkeypatch, tmp_path):
    """Review F9's stated limit: the harness fact follows the reading process's environment, so a reader that would
    launch another harness reads the check STALE, saying it is the harness this process would launch."""
    from aew.harness.opencode.adapter import BIN_ENV

    harness = tmp_path / "opencode-cli"
    harness.write_bytes(b"a stand-in, never run")
    monkeypatch.setenv(BIN_ENV, str(harness))
    _import(reg)
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    monkeypatch.setenv(BIN_ENV, str(tmp_path / "no-such-opencode"))
    cap = _cap()
    assert cap["observed_status"] == status.STALE
    assert f"the harness this process would launch changed ({harness.resolve()}" in cap["cause"]
    monkeypatch.setenv(BIN_ENV, str(harness))
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_no_payload_for_the_platform_reads_unsupported(reg, monkeypatch):
    other = _record(reg["body"], reg["archive"], platforms=("sunos5-sparc",))
    monkeypatch.setattr(records, "shipped", lambda: {"fake": other})
    cap = _cap()
    assert cap["observed_status"] == status.UNSUPPORTED and KEY in cap["cause"]


def test_an_invalid_operator_record_is_refused_never_served(reg):
    _import(reg)
    state = store.read()
    bad = copy.deepcopy(reg["shipped"]["fake"])
    bad["placement"] = "host"
    state["operator_records"]["fake"] = {"record": bad, "base_digest": records.digest(reg["shipped"]["fake"])}
    with store.locked() as root:
        store.write(state, root)
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "host placement" in cap["cause"]


def test_a_refused_operator_record_of_its_own_keeps_its_capabilities_in_the_listing_as_refused(reg):
    """Review F11: an operator record no shipped record backs (``mine``, serving ``MINE_SEARCH``), refused on a read,
    keeps its well-formed capability in the listing and in doctor, REFUSED with its cause; a malformed ID is not."""
    _import(reg)
    state = store.read()
    bad = copy.deepcopy(reg["shipped"]["fake"])
    bad.update(placement="host", capabilities=["MINE_SEARCH", "not an id"])
    state["operator_records"]["mine"] = {"record": bad, "base_digest": None}
    with store.locked() as root:
        store.write(state, root)
    listing = ops.listing()
    assert [c["id"] for c in listing["capabilities"]] == ["FAKE_SEARCH", "MINE_SEARCH"]
    cap = _cap("MINE_SEARCH")
    assert cap["observed_status"] == status.REFUSED and cap["provider"] == "mine"
    assert "its record is refused" in cap["cause"] and "not an id" in cap["cause"]
    assert ("capability:MINE_SEARCH", "WARN") in [(n, s) for n, s, _ in ops.doctor_checks()]


def test_an_unreadable_register_refuses_every_capability_with_its_cause(reg):
    reg["root"].mkdir(parents=True)
    (reg["root"] / store.REGISTER).write_text("{not json", encoding="utf-8")
    cap = _cap()
    assert cap["observed_status"] == status.REFUSED and "not JSON" in cap["cause"]


# ---------------------------------------------------------------------------------------------- host copies


def test_a_host_copy_serves_named_unpinned_beside_the_cause_for_aews_copy(reg, monkeypatch):
    """CAPR-04: AEW's copy absent, the host's serves on its own: NOT_ESTABLISHED until checked, then FUNCTIONAL_ONLY
    with the limitation naming it unpinned, beside AEW's copy's cause."""
    exe = _plant_host_copy(reg, monkeypatch)
    cap = _cap()
    assert cap["observed_status"] == status.NOT_ESTABLISHED and cap["copy"] == status.HOST_COPY
    assert cap["path"] == str(exe.resolve()) and status.UNPINNED in cap["limitations"]
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.HOST_COPY
    assert not cap["pinned"] and cap["version"] is None and status.UNPINNED in cap["limitations"]
    assert cap["cause"].startswith("AEW's copy: its pinned payload is not on this host")
    exe.write_bytes(reg["body"] + b"\n")  # the host's copy changed under its check
    assert _cap()["observed_status"] == status.STALE


def test_a_host_copy_of_another_version_serves_and_its_version_is_named(reg, monkeypatch):
    """A host copy is not AEW's pin, so its check asks that it is the provider, not that it is the pinned version
    (measured on the Rocky 8 VM: its /usr/bin/rg is ripgrep 14.1.1, AEW pins 15.1.0)."""
    newer = _record(reg["body"], reg["archive"], version="2.0", health={
        **_health(), "version": {**_health()["version"], "expect": "fake 2.0"}})
    monkeypatch.setattr(records, "shipped", lambda: {"fake": newer})
    _plant_host_copy(reg, monkeypatch)
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.HOST_COPY
    assert "it reports fake 1.0" in cap["limitations"] and status.UNPINNED in cap["limitations"]


def test_a_refused_aew_copy_never_serves_silently_and_a_host_copy_is_named(reg, monkeypatch):
    tampered = bytearray(reg["archive"])
    tampered[10] ^= 1
    _import(reg, data=bytes(tampered))
    _plant_host_copy(reg, monkeypatch)
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["copy"] == status.HOST_COPY
    assert "AEW's copy: its payload was refused" in cap["cause"] and status.UNPINNED in cap["limitations"]


def test_with_host_copies_off_a_host_copy_never_serves(reg, monkeypatch):
    exe = _plant_host_copy(reg, monkeypatch)
    ops.apply(_principal(), ops.preview(ops.HOST_COPIES, {"on": False}))
    ops.check(offline=True)
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and cap["copy"] == status.AEW_COPY
    assert str(exe.resolve()) in cap["cause"] and "host copies off" in cap["cause"]
    ops.apply(_principal(), ops.preview(ops.HOST_COPIES, {"on": True}))
    ops.check(offline=True)
    assert _cap()["copy"] == status.HOST_COPY


def test_with_no_copy_at_all_the_capability_is_unavailable_with_its_cause(reg):
    cap = _cap()
    assert cap["observed_status"] == status.UNAVAILABLE and cap["copy"] == status.AEW_COPY
    assert cap["limitations"] == ([status.NOT_BOUND] if IS_WINDOWS else [])


# ---------------------------------------------------------------------------------------------- operator records


def _add(reg: dict[str, Any], record: dict[str, Any], **args: Any) -> dict[str, Any]:
    text = json.dumps({"schema": records.SCHEMA, "providers": {"fake": record}})  # JSON is YAML
    return ops.apply(_principal(), ops.preview(ops.ADD, {"text": text, "source": "test", **args}))


def test_an_operator_override_is_kept_across_an_upgrade_and_reports_the_difference(reg, monkeypatch):
    override = _record(reg["body"], reg["archive"], description="the operator's own")
    out = _add(reg, override, bundle=str(_bundle(reg)))
    assert out["added"] == ["fake"]
    view = ops.listing()
    assert view["overrides"] == [] and _cap()["observed_status"] == status.FUNCTIONAL_ONLY
    assert next(p for p in view["providers"] if p["name"] == "fake")["layer"] == "operator"
    upgraded = copy.deepcopy(reg["shipped"]["fake"])
    upgraded["version"] = "2.0"
    monkeypatch.setattr(records, "shipped", lambda: {"fake": upgraded})
    view = ops.listing()
    assert view["overrides"] == [{"provider": "fake", "differences": ["version: 1.0 -> 2.0"]}]
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY and _cap()["version"] == "1.0"  # the override serves
    assert any(n == "capability-records" and s == "WARN" and "version: 1.0 -> 2.0" in d
               for n, s, d in ops.doctor_checks())


def test_an_add_that_fails_validation_changes_nothing(reg):
    _import(reg)
    before = (reg["root"] / store.REGISTER).read_bytes()
    with pytest.raises(errors.ValidationFailed, match="nothing changed"):
        _add(reg, {**_record(reg["body"], reg["archive"]), "placement": "host"})
    broken = _record(reg["body"], reg["archive"], health=_health(expect="none"), description="breaks")
    with pytest.raises(errors.ValidationFailed, match="health check failed"):
        _add(reg, broken, bundle=str(_bundle(reg)))
    assert (reg["root"] / store.REGISTER).read_bytes() == before


def test_an_add_whose_payload_is_new_and_fails_its_check_leaves_no_payload(reg):
    body = reg["body"] + b"\n" if not IS_WINDOWS else reg["body"]
    archive = _archive(body, MEMBER)
    broken = _record(body, archive, health=_health(expect="none"))
    with pytest.raises(errors.ValidationFailed):
        _add(reg, broken, bundle=str(_bundle(reg, data=archive)))
    assert not P.path_of("fake", "fake", broken["payloads"][KEY]).exists()


def test_a_sandbox_record_that_needs_a_credential_is_refused_saying_place_it_on_the_host(reg):
    """CAPR-Q11 and CAPR-X09."""
    record = _record(reg["body"], reg["archive"])
    record["needs"]["credentials"] = True
    with pytest.raises(errors.ValidationFailed) as exc:
        _add(reg, record)
    assert "on the host, where it holds the credential itself" in json.dumps(exc.value.to_dict())


def test_remove_takes_only_operator_records_and_the_shipped_record_serves_again(reg):
    with pytest.raises(errors.NotFound, match="reviewed AEW release"):
        ops.preview(ops.REMOVE, {"name": "fake"})
    _add(reg, _record(reg["body"], reg["archive"], description="mine"), bundle=str(_bundle(reg)))
    change = ops.preview(ops.REMOVE, {"name": "fake"})
    assert "AEW's shipped record fake serves again" in change.lines[0]
    ops.apply(_principal(), change)
    provider = next(p for p in ops.listing()["providers"] if p["name"] == "fake")
    assert provider["layer"] == "shipped"


def test_a_change_shown_before_another_lands_is_refused_never_applied_on_what_was_not_shown(reg):
    """Review F10: two projects' endpoints change one host's register. A change is applied only on the basis it was
    shown against (the operator's records and the host-copies setting); a check in between changes neither."""
    def text(record: dict[str, Any]) -> str:
        return json.dumps({"schema": records.SCHEMA, "providers": {"fake": record}})

    shown = ops.preview(ops.ADD, {"text": text(_record(reg["body"], reg["archive"], description="A's")),
                                  "source": "A", "bundle": str(_bundle(reg))})
    _add(reg, _record(reg["body"], reg["archive"], description="B's"), bundle=str(_bundle(reg)))  # lands between
    with pytest.raises(errors.ValidationFailed) as exc:
        ops.apply(_principal(), shown)
    assert exc.value.details["reason"] == "register_changed" and "nothing changed" in exc.value.message
    assert store.read()["operator_records"]["fake"]["record"]["description"] == "B's"
    off = ops.preview(ops.HOST_COPIES, {"on": False})
    ops.apply(_principal(), ops.preview(ops.HOST_COPIES, {"on": False}))
    with pytest.raises(errors.ValidationFailed, match="changed since this change was shown"):
        ops.apply(_principal(), off)
    on = ops.preview(ops.HOST_COPIES, {"on": True})
    ops.check(offline=True)  # writes only checks: no authority, so the shown change still applies
    ops.apply(_principal(), on)
    assert store.read()["host_copies"] is True


def test_apply_is_refused_without_the_endpoints_principal(reg):
    change = ops.preview(ops.HOST_COPIES, {"on": False})
    for forged in (None, {"uid": 0, "method": "peer_credentials"}, "operator"):
        with pytest.raises(errors.PermissionDenied) as exc:
            ops.apply(forged, change)
        assert exc.value.details["reason"] == "operator_principal_required"
    assert store.read()["host_copies"] is True


def test_apply_refuses_an_import_whose_record_changed_since_the_preview(reg, monkeypatch):
    change = ops.preview(ops.IMPORT, {"path": str(_bundle(reg))})
    moved = _record(reg["body"] + b"x", _archive(reg["body"] + b"x", MEMBER))
    monkeypatch.setattr(records, "shipped", lambda: {"fake": moved})
    out = ops.apply(_principal(), change)
    assert out["imported"] == [] and "changed since the preview" in out["skipped"][0]["reason"]


# ---------------------------------------------------------------------------------------------- payloads


def test_a_zip_payload_is_read_like_a_tarball(reg, monkeypatch):
    archive = _archive(reg["body"], MEMBER, kind="zip")
    record = _record(reg["body"], archive)
    record["payloads"][KEY]["source"] = "https://example.invalid/releases/fake-1.0.zip"
    monkeypatch.setattr(records, "shipped", lambda: {"fake": record})
    _import(reg, data=archive, name="fake-1.0.zip")
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def test_a_bare_executable_is_fetched_bounded_installed_and_imported_as_itself(reg, monkeypatch):
    """jq's shape: the download is the executable. The fetch reads it to its pinned size and checks its pin, the
    install writes it as it came, and an offline import of the same file makes it FUNCTIONAL_ONLY; bytes off the pin
    are refused, never installed."""
    record = copy.deepcopy(reg["shipped"]["fake"])
    record["payloads"][KEY] = _bare(reg["body"])
    monkeypatch.setattr(records, "shipped", lambda: {"fake": record})
    path = P.path_of("fake", "fake", record["payloads"][KEY])
    limit = len(reg["body"]) + 1
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: _Bounded(
        _Response(reg["body"][:-1] + b"X"), limit))
    said = ops.fetch(["fake"])["fake"]
    assert "refused" in said[0] and not path.exists(), said
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: _Bounded(
        _Response(reg["body"] + b"x" * 64), limit))
    assert "refused" in ops.fetch(["fake"])["fake"][0] and not path.exists()
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: _Bounded(_Response(reg["body"]), limit))
    said = ops.fetch(["fake"])["fake"]
    assert said[0].startswith("downloaded") and path.read_bytes() == reg["body"], said
    assert P.verify(path, record["payloads"][KEY]) is None
    P.discard("fake", record["payloads"][KEY])
    _import(reg, data=reg["body"], name="fake-linux-amd64")
    assert _cap()["observed_status"] == status.FUNCTIONAL_ONLY


def test_a_wheel_is_read_as_the_zip_it_is(reg):
    """ast-grep's Linux payload is its manylinux_2_28 wheel: the member is read out of it like any zip's."""
    archive = _archive(reg["body"], MEMBER, kind="zip")
    pinned = {**reg["shipped"]["fake"]["payloads"][KEY], "source": "https://example.invalid/fake-1.0-py3-none.whl",
              "archive_sha256": _sha(archive), "archive_size": len(archive)}
    assert P.member(archive, pinned) == reg["body"]


def test_a_tar_member_named_from_the_archives_own_dot_is_read(reg):
    """yq's Linux archive names its executable `./yq_linux_amd64`: the record names it so, and it is read."""
    archive = _archive(reg["body"], "./fake")
    pinned = {**reg["shipped"]["fake"]["payloads"][KEY], "member": "./fake", "archive_sha256": _sha(archive),
              "archive_size": len(archive)}
    records.validate({"schema": records.SCHEMA, "providers": {"fake": {**reg["shipped"]["fake"],
                                                                       "payloads": {KEY: pinned}}}}, source="test")
    assert P.member(archive, pinned) == reg["body"]


def test_an_archive_without_its_member_as_a_regular_file_is_refused(reg):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as t:
        link = tarfile.TarInfo(MEMBER)
        link.type, link.linkname = tarfile.SYMTYPE, "/bin/sh"
        t.addfile(link)
    archive = out.getvalue()
    pinned = {**reg["shipped"]["fake"]["payloads"][KEY], "archive_sha256": _sha(archive), "archive_size": len(archive)}
    with pytest.raises(P.PinMismatch) as exc:
        P.member(archive, pinned)
    assert exc.value.details["reason"] == "member_missing"


def test_a_fetch_reads_no_more_than_the_pinned_size_and_checks_the_pin(monkeypatch, reg):
    pinned = reg["shipped"]["fake"]["payloads"][KEY]

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: Any) -> None:
            self.close()

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response(reg["archive"] + b"more"))
    with pytest.raises(P.PinMismatch) as exc:
        P.fetch(pinned)
    assert exc.value.details["reason"] == "archive_size"
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response(b"x" * len(reg["archive"])))
    with pytest.raises(P.PinMismatch) as exc:
        P.fetch(pinned)
    assert exc.value.details["reason"] == "archive_pin"
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response(reg["archive"]))
    assert P.fetch(pinned) == reg["archive"]

    def unreachable(url: str, timeout: float) -> Any:
        raise OSError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    with pytest.raises(errors.Unavailable) as down:
        P.fetch(pinned)
    assert down.value.details["reason"] == "fetch_failed"


# ---------------------------------------------------------------------------------------------- doctor


def test_doctor_names_each_capability_pass_when_usable_and_warn_never_fail_otherwise(reg):
    """CAPR-12: no provider is required, so a missing needed one is a WARN with its cause and fix, never a FAIL."""
    from aew import doctor

    reg["shipped"]["fake"].update(needed=True, degrades="the stand-in's search")
    rows = {c["check"]: c for c in doctor.environment_checks() if c["check"].startswith("capability:")}
    assert rows["capability:FAKE_SEARCH"]["status"] == "WARN" and ops.OPTIONAL_LINE not in rows
    assert rows["capability:FAKE_SEARCH"]["detail"].startswith("UNAVAILABLE:")
    assert "fix: `aew capability fetch fake` downloads it" in rows["capability:FAKE_SEARCH"]["detail"]
    _import(reg)
    rows = {c["check"]: c for c in doctor.environment_checks() if c["check"].startswith("capability:")}
    assert rows["capability:FAKE_SEARCH"]["status"] == "PASS"
    assert rows["capability:FAKE_SEARCH"]["detail"].startswith("FUNCTIONAL_ONLY: served by fake 1.0, AEW's pinned")


def test_doctor_gives_optional_tools_the_operator_did_not_choose_one_line_not_a_warning_each(reg, monkeypatch):
    """Review of #349, m3: an optional tool absent because the operator never chose it, or declined it, is not a
    warning: such tools share one UNAVAILABLE line naming each and `aew capability fetch NAME`. A failed fetch of one
    is a warning again, and a needed one always is (the test above)."""
    from aew.capability import consent

    def rows() -> dict[str, tuple[str, str]]:
        return {n: (s, d) for n, s, d in ops.doctor_checks()}

    got = rows()
    assert "capability:FAKE_SEARCH" not in got, got
    level, detail = got[ops.OPTIONAL_LINE]
    assert level == "UNAVAILABLE" and "fake (FAKE_SEARCH; it is not installed on this host)" in detail, detail
    assert "`aew capability fetch NAME` downloads one" in detail
    consent.decline([o for o in consent.offers() if o.provider == "fake"])
    level, detail = rows()[ops.OPTIONAL_LINE]
    assert level == "UNAVAILABLE" and "the operator declined to download it" in detail, detail

    def unreachable(url: str, timeout: float) -> Any:
        raise OSError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    ops.fetch(["fake"])
    got = rows()
    assert got["capability:FAKE_SEARCH"][0] == "WARN" and ops.OPTIONAL_LINE not in got, got


def test_doctor_names_the_harness_a_host_prerequisite(tmp_path, monkeypatch):
    """CAPR-12 (the designer's CAP-1 rule 9): doctor names the harness; without one AEW runs and launches refuse."""
    from aew import doctor
    from aew.harness.opencode.adapter import BIN_ENV

    monkeypatch.setenv(BIN_ENV, str(tmp_path / "no-such-opencode"))
    row = next(c for c in doctor.environment_checks() if c["check"] == "harness")
    assert row["status"] == "WARN" and "harness launches are refused" in row["detail"] and BIN_ENV in row["detail"]
    present = tmp_path / "opencode-cli"
    present.write_bytes(b"")
    monkeypatch.setenv(BIN_ENV, str(present))
    row = next(c for c in doctor.environment_checks() if c["check"] == "harness")
    assert row["status"] == "PASS" and str(present) in row["detail"]


def test_a_register_that_cannot_be_written_refuses_the_change_with_its_own_reason(reg, monkeypatch):
    """CAPR-Q02's face here: where the register cannot be written (a contained run's sandbox sees it read-only; here a
    file stands where its directory would be), a check is refused with its reason, never a crash, and the OS's own
    words stay out of the message (a sandbox's command checks read its output for them)."""
    blocker = reg["tmp"] / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(store, "ROOT_OVERRIDE", blocker / "register")
    with pytest.raises(errors.PermissionDenied) as exc:
        ops.check(offline=True)
    assert exc.value.details["reason"] == "register_not_writable" and exc.value.details["errno"]
    assert "Read-only file system" not in exc.value.message and "Permission denied" not in exc.value.message


def test_every_register_write_path_refuses_with_the_typed_reason(reg, monkeypatch):
    """Review F1's class: the state, the change log, a payload's install and discard, and the lock's own file each
    refuse an unwritable register with ``register_not_writable``, saying where `check` runs, never with an OSError."""
    import errno as errno_

    from aew.engine.lock import FileLock

    blocked = reg["tmp"] / "a-file"
    blocked.write_text("x", encoding="utf-8")
    under = blocked / "register"  # a file stands where the register's directory would be
    pinned = {"sha256": "0" * 64}

    def erofs(*_a: Any, ignore_errors: bool = False, **_k: Any) -> None:  # as a read-only file system answers
        if not ignore_errors:
            raise OSError(errno_.EROFS, "Read-only file system")

    real = reg["tmp"] / "real"
    P.install("fake", "fake", pinned, b"x", real)
    calls = {
        "write": lambda: store.write(store.empty(), under),
        "record_change": lambda: store.record_change("x", {}, None, under),
        "install": lambda: P.install("fake", "fake", pinned, b"x", under),
        "locked": lambda: store.locked(under).__enter__(),
    }
    for name, call in calls.items():
        with pytest.raises(errors.PermissionDenied) as exc:
            call()
        assert exc.value.details["reason"] == store.NOT_WRITABLE, name
        assert "`aew capability check` at the operator's own terminal" in exc.value.message, name
    with monkeypatch.context() as m, pytest.raises(errors.PermissionDenied) as exc:
        m.setattr(P.shutil, "rmtree", erofs)
        P.discard("fake", pinned, real)
    assert exc.value.details == {"path": str(real), "errno": "EROFS", "reason": store.NOT_WRITABLE}
    assert P.path_of("fake", "fake", pinned, real).exists()  # left in place, and said so
    with monkeypatch.context() as m, pytest.raises(errors.PermissionDenied) as exc:
        m.setattr(FileLock, "__exit__", erofs)
        with store.locked(real):
            pass
    assert exc.value.details["reason"] == store.NOT_WRITABLE


def test_the_seven_statuses_are_the_adopted_d01_schemas_and_each_name_is_one_of_them():
    """Review F5: the statuses' owner is the adopted D-01 read schema (CapabilityData.observed_status, S01-04); the
    names the register uses are exactly its values."""
    names = {status.QUALIFIED, status.FUNCTIONAL_ONLY, status.NOT_ESTABLISHED, status.UNSUPPORTED,
             status.UNAVAILABLE, status.STALE, status.REFUSED}
    assert set(status.STATUSES) == names and len(status.STATUSES) == 7
    assert status.USABLE <= names and status.NOT_SERVING <= names


# ---------------------------------------------------------------------------------------------- the payload's guards
# Review F6: each guard the payload claims, proved by a plant that only that guard stops. Each plant is pinned by its
# own archive's digest and size (as an operator's record pinning it would be), so it reaches `member()`.

GOOD = b"#!/bin/sh\necho good\n" * 8


def _pin_for(data: bytes, kind: str, body: bytes = GOOD) -> dict[str, Any]:
    return {"source": f"https://example.invalid/fake-1.0.{kind}", "archive_sha256": _sha(data),
            "archive_size": len(data), "member": MEMBER, "sha256": _sha(body), "size": len(body)}


def _tgz(*entries: tuple[str, str, bytes, str]) -> bytes:
    """(name, kind, data, link name), kind one of file, sym, hard."""
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as t:
        for name, kind, data, link in entries:
            info = tarfile.TarInfo(name)
            info.mode = 0o755
            if kind == "file":
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
            else:
                info.type, info.linkname = {"sym": tarfile.SYMTYPE, "hard": tarfile.LNKTYPE}[kind], link
                t.addfile(info)
    return out.getvalue()


def _zip(data: bytes, *, symlink: bool = False) -> bytes:
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(MEMBER)
        info.compress_type = zipfile.ZIP_DEFLATED
        if symlink:
            info.external_attr, info.create_system = 0o120777 << 16, 3
        z.writestr(info, data)
    return out.getvalue()


class _Bounded:
    """A reader that fails an unbounded read, or one past ``limit``: a guard's bound is then what a test sees."""

    def __init__(self, fh: Any, limit: int) -> None:
        self.fh, self.limit = fh, limit

    def read(self, n: int | None = -1) -> bytes:
        assert n is not None and 0 <= n <= self.limit, f"read({n}) past the bound {self.limit}"
        return self.fh.read(n)

    def __enter__(self) -> _Bounded:
        return self

    def __exit__(self, *exc: Any) -> None:
        close = getattr(self.fh, "close", None)
        if close is not None:
            close()


def test_a_fetch_never_reads_past_the_pinned_archive_size(monkeypatch, reg):
    pinned = reg["shipped"]["fake"]["payloads"][KEY]
    limit = pinned["archive_size"] + 1
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: _Bounded(io.BytesIO(reg["archive"] + b"x" * (1 << 20)), limit))
    with pytest.raises(P.PinMismatch) as exc:
        P.fetch(pinned)
    assert exc.value.details["reason"] == "archive_size"
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: _Bounded(io.BytesIO(reg["archive"]), limit))
    assert P.fetch(pinned) == reg["archive"]


def test_an_oversized_member_is_read_only_to_its_pinned_size_in_a_tar_and_a_zip(monkeypatch):
    import zipfile

    big = GOOD + bytes(1 << 20)
    oversized = (("tar.gz", _tgz((MEMBER, "file", big, ""))), ("zip", _zip(big)))
    controls = (("tar.gz", _tgz((MEMBER, "file", GOOD, ""))), ("zip", _zip(GOOD)))
    limit = len(GOOD) + 1
    real_extract, real_open = tarfile.TarFile.extractfile, zipfile.ZipFile.open
    monkeypatch.setattr(tarfile.TarFile, "extractfile", lambda self, m: _Bounded(real_extract(self, m), limit))
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda self, m, *a, **k: _Bounded(real_open(self, m, *a, **k), limit))
    for kind, data in oversized:
        with pytest.raises(P.PinMismatch) as exc:
            P.member(data, _pin_for(data, kind))
        assert exc.value.details["reason"] == "payload_pin", kind
    for kind, data in controls:
        assert P.member(data, _pin_for(data, kind)) == GOOD, kind


def test_a_link_at_the_members_name_is_refused_even_when_it_leads_to_the_pinned_bytes():
    """Only a regular file is the member: a tar symlink or hard link to an in-archive file that matches the pin, and
    a zip entry with symlink attributes whose bytes match it, are each refused as no regular file."""
    real = "fake-1.0/real"
    plants = {
        "tar symlink": ("tar.gz", _tgz((real, "file", GOOD, ""), (MEMBER, "sym", b"", "real"))),
        "tar hard link": ("tar.gz", _tgz((real, "file", GOOD, ""), (MEMBER, "hard", b"", real))),
        "zip symlink": ("zip", _zip(GOOD, symlink=True)),
    }
    for label, (kind, data) in plants.items():
        with pytest.raises(P.PinMismatch) as exc:
            P.member(data, _pin_for(data, kind))
        assert exc.value.details["reason"] == "member_missing", label


def test_an_oversized_bundle_file_named_like_the_pin_is_read_bounded_and_said_larger(reg, monkeypatch):
    """Review F6 and F13: the import reads a file named like a pinned archive only to the pin's size, and its
    refusal gives the file's own size and says it is larger than its pin."""
    import builtins

    pinned = reg["shipped"]["fake"]["payloads"][KEY]
    bundle = _bundle(reg, data=reg["archive"] + bytes(1 << 20))
    size = (bundle / "fake-1.0.tar.gz").stat().st_size
    monkeypatch.setattr(ops, "open", lambda f, mode="r", *a, **k: _Bounded(builtins.open(f, mode, *a, **k),
                                                                            pinned["archive_size"] + 1),
                        raising=False)
    change = ops.preview(ops.IMPORT, {"path": str(bundle)})
    refuse = [line for line in change.lines if "REFUSE" in line]
    assert len(refuse) == 1 and "is larger than its pin" in refuse[0], change.lines
    assert f"({size} bytes; pinned {pinned['archive_size']} bytes)" in refuse[0]
    assert "sha256" not in refuse[0]  # the prefix's digest is not the file's


def test_an_encrypted_unsupported_or_damaged_zip_entry_is_refused_as_unreadable():
    """Review F7: the three zip read errors that are not BadZipFile are refused like it, so an add's rollback runs."""
    import struct

    good = _zip(GOOD)

    def patched(fn: Any) -> bytes:
        b = bytearray(good)
        fn(b)
        return bytes(b)

    def encrypted(b: bytearray) -> None:
        for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            i = b.find(sig)
            struct.pack_into("<H", b, i + off, struct.unpack_from("<H", b, i + off)[0] | 0x1)

    def shrink(b: bytearray) -> None:
        for sig, off in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
            struct.pack_into("<H", b, b.find(sig) + off, 1)

    def corrupt(b: bytearray) -> None:
        i = b.find(b"PK\x03\x04")
        n, extra = struct.unpack_from("<HH", b, i + 26)
        for j in range(i + 30 + n + extra, i + 38 + n + extra):
            b[j] ^= 0xFF

    for label, fn in (("encrypted", encrypted), ("unsupported method", shrink), ("damaged deflate", corrupt)):
        data = patched(fn)
        with pytest.raises(P.PinMismatch) as exc:
            P.member(data, _pin_for(data, "zip"))
        assert exc.value.details["reason"] == "archive_unreadable", label
