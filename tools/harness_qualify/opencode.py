"""The OpenCode probe pack: how to start OpenCode, its API check, its fact probes and its version source.

Every server is a private ``<binary> serve --stdio`` with the core's private homes and XDG folders, AEW's settings that
keep project configuration and auto-update off, a fresh server password, and (for the behaviour checks) OpenAI pointed
at the core's scripted model on loopback with a synthetic key. No real provider, key or model is ever reached.

The facts, and the fixtures they make (``tests/fixtures/opencode/``):

- ``openapi.min``: the served document trimmed as ``openapi-<v>.min.json`` is (the operations of
  ``capabilities.REQUIRED_OPERATIONS`` and every schema they, ``REQUIRED_FIELDS`` and ``REQUIRED_ENUMS`` reach);
- ``usage.openai``: the stored message tokens for each raw Responses usage of ``usage-<v>-openai.json``'s cases, and
  the token semantics they show (``adapter.token_semantics``);
- ``live_usage.citations``: each bundled-code identifier ``live-usage-<v>.json`` cites, searched in the binary;
- ``tool_parts``: the tool-call fields steering reads (write, edit, shell and every part's ``time``), from a real run;
- ``catalog.declared_only``, ``relay.transport_http``, ``relay.websocket_first``, ``ripgrep.download_version`` and
  ``api.policy_actions``.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import re
import secrets
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from aew.harness import procs
from aew.harness import usage as U
from aew.harness.opencode import capabilities as C
from aew.harness.opencode import projection
from aew.harness.opencode.adapter import OpenCodeAdapter, declared_only
from aew.harness.opencode.client import Server, location

from . import model as scripted
from .core import API, CITATION, FAIL, PASS, SKIPPED, Check, Context, Outcome, Release, dump
from .core import sha256_file as core_sha256
from .neutral import neutral_checks

HARNESS = "opencode"
MODEL = "aew-qualify-scripted"  # a model only AEW's configuration names: no catalog offers it
AGENT = "aew-qualify"
SYNTHETIC_KEY = "sk-aew-qualify-synthetic-not-a-key"
TURN_S = 90.0
FEED = "https://opencode.ai/update/api/latest/desktop/opencode/latest-linux.yml"
_ALL_ALLOWED = [{"action": "*", "resource": "*", "effect": "allow"}]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ------------------------------------------------------------------------------------------------ starting the server

def server_config(base_url: str | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {"snapshots": False, "update": "disable", "share": "disabled", "lsp": False,
                              "formatter": False}
    if base_url is not None:
        ref = {"providerID": "openai", "model": MODEL}
        agent = {"model": ref, "mode": "primary", "system": "Do exactly what the scripted model says.",
                 "permissions": _ALL_ALLOWED}
        config.update({"default_agent": AGENT, "agents": {AGENT: agent, **{a: {"model": ref} for a in
                                                                           ("title", "summary", "compaction")}},
                       "providers": {"openai": {"settings": {"baseURL": base_url, "transport": "http"},
                                                "models": {MODEL: {"settings": {"baseURL": base_url}}}}}})
    return config


def command(binary: Path) -> list[str]:
    """The adapter's rule (``adapter.binary_command``) for a given path: a ``.py`` binary (the fake server) runs with
    this Python."""
    return [sys.executable, str(binary)] if binary.suffix == ".py" else [str(binary)]


@contextlib.contextmanager
def serve(binary: Path, work: Path, env: dict[str, str], config: dict[str, Any] | None = None,
          extra_env: Mapping[str, str] | None = None) -> Iterator[Server]:
    """A private server, ended (with everything it started) when the block ends."""
    work.mkdir(parents=True, exist_ok=True)
    full = {**env, **(extra_env or {}), "OPENCODE_CONFIG_CONTENT": json.dumps(config or server_config(),
                                                                                sort_keys=True),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_PASSWORD": secrets.token_hex(16)}
    tree = procs.ProcessTree()
    (work / "project").mkdir(exist_ok=True)
    try:
        server = Server.start(tree.spawn, command(binary), env=full, cwd=str(work / "project"),
                              log_path=work / "server.log")
        try:
            yield server
        finally:
            server.close()
    finally:
        tree.kill()


def raw_get(server: Server, path: str) -> bytes:
    auth = "Basic " + base64.b64encode(f"opencode:{server.password}".encode()).decode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # loopback http only: Server.start refuses any other address
    req = urllib.request.Request(server.url + path, headers={"Authorization": auth})  # noqa: S310 (loopback http)
    with opener.open(req, timeout=60) as r:
        return r.read()


def read_version(binary: Path, work: Path, env: dict[str, str]) -> str:
    with serve(binary, work, env) as server:
        version = (server.client.get("/api/info") or {}).get("version")
    if not isinstance(version, str) or not version.strip():  # never "None" in a record or a fixture's name
        raise ValueError(f"the server's /api/info names no version ({version!r})")
    return version.strip()


# --------------------------------------------------------------------------------------------------- the served API

def _refs(node: Any, acc: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                acc.add(v.rsplit("/", 1)[-1])
            else:
                _refs(v, acc)
    elif isinstance(node, list):
        for v in node:
            _refs(v, acc)


def trim(spec: dict[str, Any], *, version: str, full_sha256: str) -> dict[str, Any]:
    """The pinned fixture's trimming: the operations the adapter probes, and every schema reachable from them and
    from the probe's required fields and enums."""
    schemas = (spec.get("components") or {}).get("schemas") or {}
    paths: dict[str, dict[str, Any]] = {}
    for op in C.REQUIRED_OPERATIONS:
        entry = (spec["paths"].get(op.path) or {}).get(op.method.lower())
        if entry is not None:
            paths.setdefault(op.path, {})[op.method.lower()] = entry
    seeds: set[str] = set(C.REQUIRED_FIELDS) | set(C.REQUIRED_ENUMS) | {name for name, _ in C.REQUIRED_FIELD_ENUMS}
    _refs(paths, seeds)
    keep: set[str] = set()
    todo = list(seeds)
    while todo:
        name = todo.pop()
        if name in keep or name not in schemas:
            continue
        keep.add(name)
        found: set[str] = set()
        _refs(schemas[name], found)
        todo += found
    return {"components": {"schemas": {k: schemas[k] for k in sorted(keep)}}, "info": spec.get("info"),
            "openapi": spec.get("openapi"), "paths": paths,
            "x-aew-fixture": {"full_sha256": full_sha256,
                              "note": "trimmed to the operations and schemas the AEW OpenCode adapter probes",
                              "source": f"GET /openapi.json of OpenCode {version} (opencode-cli serve)"}}


def full_sha256(raw: bytes) -> str:
    """The served document's own bytes' sha256 (the Lead's ruling for the bump, 2026-11-07: the raw-bytes hash is the
    one that counts). The 2.0.18 fixture's header carries the hash of an earlier re-serialization (``json.dumps``
    with ``indent=1``, CRLF), kept as the record of how that fixture was made."""
    return hashlib.sha256(raw).hexdigest()


def _policy_actions(spec: dict[str, Any]) -> list[str]:
    """The ``action`` enum of ``Config.InfoEncoded.experimental.policies`` items (inline), read by the probe's own
    accessor (``capabilities.field_enum``)."""
    return sorted(C.field_enum(spec, "Config.InfoEncoded", "experimental.policies[].action"))


def served_api(ctx: Context) -> dict[str, Any]:
    def fetch() -> dict[str, Any]:
        with serve(ctx.binary, ctx.work / "api", ctx.env) as server:
            raw = raw_get(server, "/openapi.json")
            info = server.client.get("/api/info")
        return {"raw": raw, "spec": json.loads(raw), "info": info}
    return ctx.once("served_api", fetch)


def check_openapi(ctx: Context) -> Outcome:
    api = served_api(ctx)
    spec, raw = api["spec"], api["raw"]
    problems = C.problems(spec) + C.version_problems(api["info"].get("version"))
    ops = sum(1 for e in spec["paths"].values() for m in e if m in ("get", "post", "put", "patch", "delete"))
    facts = {"openapi.min": trim(spec, version=ctx.version, full_sha256=full_sha256(raw)),
             "openapi.served_sha256": hashlib.sha256(raw).hexdigest(),
             "openapi.counts": {"operations": ops, "schemas": len(spec["components"]["schemas"])},
             "openapi.problems": problems, "api.policy_actions": _policy_actions(spec)}
    return Outcome(FAIL if problems else PASS, facts, problems)


def _api_capability(ctx: Context, needs: list[tuple[str, str]]) -> Outcome:
    """The served API offers what a capability's adapter path uses: each ``("op", "METHOD /path")`` or
    ``("enum", "Schema=value")``. API depth only: it says the route exists, not that it behaves."""
    spec = served_api(ctx)["spec"]
    missing = []
    for kind, what in needs:
        if kind == "op":
            method, path = what.split(" ", 1)
            if (spec["paths"].get(path) or {}).get(method.lower()) is None:
                missing.append(what)
        else:
            name, value = what.split("=", 1)
            if value not in C._enum(spec, spec["components"]["schemas"].get(name)):
                missing.append(what)
    return Outcome(FAIL if missing else PASS, notes=[f"missing {m}" for m in missing])


# ------------------------------------------------------------------------------------ a turn with the scripted model

def run_turns(ctx: Context, script: list[dict[str, Any]], prompt: str, name: str,
              edit: Any = None) -> dict[str, Any]:
    """One session, one prompt, the scripted model answering: the session, its messages and what the model saw."""
    llm = scripted.start("responses", script)
    work = ctx.work / name
    try:
        config = server_config(llm.base_url)
        if edit is not None:
            edit(config)
        with serve(ctx.binary, work, ctx.env, config, {"OPENAI_API_KEY": SYNTHETIC_KEY}) as server:
            directory = str((work / "project").resolve())
            loc = location(directory)
            deadline = time.monotonic() + TURN_S
            catalog: list[dict[str, Any]] = []
            while time.monotonic() < deadline:  # the catalog loads asynchronously
                catalog = (server.client.get("/api/model", loc) or {}).get("data") or []
                if any(m.get("id") == MODEL for m in catalog):
                    break
                time.sleep(0.25)
            session = server.client.post("/api/session", {
                "title": "harness qualify", "agent": AGENT, "model": {"providerID": "openai", "id": MODEL},
                "location": {"directory": directory}, "permissions": _ALL_ALLOWED})
            sid = (session.get("data") or session)["id"]
            mid = "msg_" + secrets.token_hex(12)
            server.client.post(f"/api/session/{sid}/prompt", {"id": mid, "text": prompt})
            messages: list[dict[str, Any]] = []
            while time.monotonic() < deadline:
                active = (server.client.get("/api/session/active") or {}).get("data") or {}
                messages = _messages(server, sid)
                ids = [m.get("id") for m in messages]
                if sid not in active and mid in ids and messages[-1].get("type") == "idle" \
                        and ids.index(mid) < len(ids) - 1:
                    break
                time.sleep(0.3)
            else:
                raise TimeoutError(f"the turn did not end within {TURN_S:.0f}s (see {name}/server.log)")
            info = server.client.get(f"/api/session/{sid}")
            return {"session": info.get("data") or info, "messages": messages, "catalog": catalog,
                    "requests": llm.requests, "upgrades": llm.upgrades, "directory": directory}
    finally:
        llm.close()


def _messages(server: Server, sid: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = None
    for _ in range(50):
        params = {"limit": "100", **({"cursor": cursor} if cursor else {"order": "asc"})}
        page = server.client.get(f"/api/session/{sid}/message", params) or {}
        out += page.get("data") or []
        cursor = ((page.get("cursor") or {}).get("next"))
        if not cursor or not page.get("data"):
            break
    return out


def _tokens(t: Mapping[str, Any]) -> dict[str, Any]:
    cache = t.get("cache") or {}
    return {"input": t.get("input"), "output": t.get("output"), "reasoning": t.get("reasoning"),
            "cache": {"read": cache.get("read"), "write": cache.get("write")}}


def classify(cases: list[dict[str, Any]]) -> str:
    """``disjoint`` when every stored breakdown is the raw usage split into non-overlapping parts (input excludes the
    cached and cache-written tokens, output excludes reasoning), as ``usage.DISJOINT`` means; else ``unknown``."""
    for c in cases:
        r, s = c["raw"], c["stored"]
        d = r.get("input_tokens_details") or {}
        reasoning = (r.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
        want = {"input": r["input_tokens"] - d.get("cached_tokens", 0) - d.get("cache_write_tokens", 0),
                "output": max(0, r["output_tokens"] - reasoning), "reasoning": reasoning,
                "cache": {"read": d.get("cached_tokens", 0), "write": d.get("cache_write_tokens", 0)}}
        if s != want:
            return U.UNKNOWN
    return U.DISJOINT


def usage_inputs(fixtures: Path, version: str) -> list[dict[str, Any]]:
    """The probe's inputs: each pinned case's name and raw usage (its ``stored`` is what the run measures)."""
    doc = json.loads((fixtures / f"usage-{version}-openai.json").read_text(encoding="utf-8"))
    return [{"name": c["name"], "raw": c["raw"]} for c in doc["cases"]]


def check_usage(ctx: Context, fixtures: Path, pinned: str) -> Outcome:
    cases = usage_inputs(fixtures, pinned)
    script = [{"call": ["bash", "shell"], "arguments": {"command": "echo step", "description": "step"},
               "usage": c["raw"]} for c in cases] + [{"text": "done"}]
    run = run_turns(ctx, script, "run the scripted steps", "usage")
    steps = [m for m in run["messages"] if m.get("type") == "assistant"]
    if len(steps) < len(cases):
        return Outcome(FAIL, notes=[f"{len(steps)} assistant steps for {len(cases)} cases"])
    measured = [{"name": c["name"], "raw": c["raw"], "stored": _tokens(m.get("tokens") or {})}
                for c, m in zip(cases, steps, strict=False)]  # steps past the cases are the closing text turn
    entry = next((m for m in run["catalog"] if m.get("id") == MODEL), {})
    facts = {"usage.openai": {"token_semantics": classify(measured), "cases": measured},
             # adapter.declared_only's reading of the entry the server made from AEW's configuration alone
             "catalog.declared_only": {"listed": bool(entry), "declared_only": bool(entry) and declared_only(entry)},
             "relay.transport_http": {"upgrades": run["upgrades"],
                                      "route": sorted({r["path"] for r in run["requests"] if r["method"] == "POST"})},
             "prompt.idle_session_starts_turn": bool(steps)}
    disjoint = facts["usage.openai"]["token_semantics"] == U.DISJOINT
    notes = [] if disjoint else ["usage is not disjoint"]
    return Outcome(PASS if not notes else FAIL, facts, notes)


def check_websocket_default(ctx: Context) -> Outcome:
    """Without ``transport: http``, does OpenAI's SDK try a WebSocket first (``projection.WEBSOCKET_FIRST``)?"""
    def no_transport(config: dict[str, Any]) -> None:
        config["providers"]["openai"]["settings"].pop("transport")

    run = run_turns(ctx, [{"text": "done"}], "say done", "websocket", edit=no_transport)
    return Outcome(PASS, {"relay.websocket_first": {"openai": run["upgrades"] > 0}})


NOTE, EXIT = "hq-note.txt", 3  # the file the scripted run writes then edits, and its command's exit code


def check_tool_parts(ctx: Context) -> Outcome:
    """A real run writes a file, edits it and runs a command that exits 3; steering's own reader of tool parts
    (``progress.Tracker``) must then find that one file, that command and its exit code, and the command's completion
    time. Steering's reads are its code's, not restated here; the parts' field names are recorded as
    ``tool_parts`` for the diff."""
    script = [{"call": ["write"], "arguments": {"$path": f"{{dir}}/{NOTE}", "content": "one\n"}},
              {"call": ["edit"], "arguments": {"$path": f"{{dir}}/{NOTE}", "oldString": "one", "newString": "two"}},
              {"call": ["bash", "shell"], "arguments": {"command": f"exit {EXIT}", "description": "exit"}},
              {"text": "done"}]
    directory = str((ctx.work / "parts" / "project").resolve())
    for turn in script:
        for k, v in list((turn.get("arguments") or {}).items()):
            if isinstance(v, str):
                turn["arguments"][k] = v.replace("{dir}", directory)
    run = run_turns(ctx, script, "run the scripted tools", "parts")
    parts = [p for m in run["messages"] if m.get("type") == "assistant" for p in m.get("content") or []
             if isinstance(p, dict) and p.get("type") == "tool"]
    by: dict[str, dict[str, Any]] = {}
    for p in parts:
        state = p.get("state") or {}
        holder = state if ("input" in state or "metadata" in state) else p
        files = (holder.get("metadata") or {}).get("files")
        by[str(p.get("name"))] = {
            "input": sorted((holder.get("input") or {}).keys()),
            "metadata": sorted((holder.get("metadata") or {}).keys()),
            "metadata.files[]": sorted(files[0].keys()) if isinstance(files, list) and files else None,
            "metadata.exit": (holder.get("metadata") or {}).get("exit"),
            "time": sorted((p.get("time") or state.get("time") or {}).keys()),
            "where": "state" if holder is state else "part"}
    facts = {"tool_parts": by}
    from aew.harness import progress

    tracker = progress.Tracker(run="harness-qualify", workspace=directory, scope_paths=None, clock=time.time)
    state = progress.empty_state(started_at=0.0)
    for m in run["messages"]:
        if m.get("type") == "assistant":
            tracker.observe(state, m)
    last = state.get("last_command") or {}
    notes = []
    if state.get("files") != [NOTE]:
        notes.append(f"steering read the files {state.get('files')}, not [{NOTE!r}] (write and edit name it)")
    if last.get("text") != f"exit {EXIT}" or last.get("exit") != EXIT:
        notes.append(f"steering read the last command as {last.get('text')!r}, exit {last.get('exit')!r}")
    if last.get("at") is None:
        notes.append("steering read no completion time on the command")
    return Outcome(FAIL if notes else PASS, facts, notes)


# ------------------------------------------------------------------------------------------------- the login store

def credential_schema() -> list[list[str]]:
    """The ``credential`` table AEW knows, each column's name and declared type in order: ``login.CREDENTIAL_SCHEMA``,
    its one owner (the Lead's login seed writes only to a table exactly like it, E118)."""
    from aew.harness.opencode import login

    return [[name, kind] for name, kind in login.CREDENTIAL_SCHEMA]


def check_login_store(ctx: Context) -> Outcome:
    """A synthetic key stored through the server's own API (``integration.connect.key``) in this check's private
    home, then read back with AEW's own reader (``login.stored``). The database read is the one this check made: a
    path outside its folder is refused, so no operator's or run's store is ever read. OAuth rows need a real login
    flow, so their shape stays a citation (``login.oauth_shape``).

    The store itself, for the facts the Lead's own store handling rests on (E118): the database is ``login.DB``;
    ``credential`` is ``login.CREDENTIAL_SCHEMA``; and every table holding a session's rules column is one of
    ``login.SESSION_TABLES``, or the Lead's clear would pass a renamed one over without a word. Every table and its
    columns are recorded (``store.schema``, pinned as ``store-<v>.json``), so the diff names any table a release adds,
    renames or changes."""
    import sqlite3

    from aew.harness.opencode import login

    work = ctx.work / "login"
    with serve(ctx.binary, work, ctx.env) as server:
        deadline = time.monotonic() + TURN_S
        while time.monotonic() < deadline:  # integrations load asynchronously, like the catalog
            listed = server.client.get("/api/integration") or {}
            if any(i.get("id") == "openai" for i in (listed.get("data") or []) if isinstance(i, dict)):
                break
            time.sleep(0.25)
        server.client.post("/api/integration/openai/connect/key", {"key": SYNTHETIC_KEY})
    db = login.db_path(ctx.env)
    if not db.resolve().is_relative_to(ctx.work.resolve()):
        raise RuntimeError("refused: the login database is not this check's own")
    if not db.is_file():  # the store has another name: say which files the server made, never read them
        made = sorted(p.name for p in db.parent.glob("*") if p.is_file()) if db.parent.is_dir() else []
        return Outcome(FAIL, {"store.files": made}, [f"no {login.DB} in the server's data folder: it holds {made}"])
    con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        # S608: each table name is one this database itself listed
        tables = {t: [[str(r[1]), str(r[2]).lower()] for r in con.execute(f"PRAGMA table_info('{t}')")]  # noqa: S608
                  for t in names if not t.startswith("sqlite_")}
        raw = con.execute("SELECT value FROM credential WHERE integration_id = 'openai'").fetchone()
    finally:
        con.close()
    schema = tables.get("credential", [])
    rules = sorted(t for t, cols in tables.items()
                   if t != "permission" and login.SESSION_RULES_COLUMN in {c for c, _ in cols})
    unknown_rules = sorted(set(rules) - set(login.SESSION_TABLES))
    logins, why = login.stored(ctx.env)
    read = {x.integration: x.kind for x in logins}
    fields = sorted(json.loads(raw[0])) if raw else []
    # a reason code, never `why`: it names the database's host path, and records are shared
    reads_as = read.get("openai") or ("unreadable" if why else "no_row")
    facts = {"login.store": {"schema": schema, "key_row_reads_as": reads_as, "key_value_fields": fields,
                             "rules_tables_unknown": unknown_rules},
             "store.schema": tables}
    notes = []
    if schema != credential_schema():
        notes.append(f"credential is not login.CREDENTIAL_SCHEMA: {schema}")
    if read.get("openai") != "key":
        notes.append(f"the synthetic key row reads as {reads_as}")
    if unknown_rules:
        notes.append(f"session rules held in tables the Lead's clear does not know: {unknown_rules} "
                     f"(login.SESSION_TABLES is {list(login.SESSION_TABLES)})")
    return Outcome(FAIL if notes else PASS, facts, notes)


# ------------------------------------------------------------------------------------------------ citations (bundle)

def _bundle(ctx: Context) -> bytes:
    return ctx.once("bundle", lambda: ctx.binary.read_bytes())


# The version probe P1's live-usage citations were read at (``live-usage-<v>.json``). It moves when they are re-read
# for a new pin; until then the pin's run reports them not comparable (a hold row in the register).
LIVE_USAGE_READ_AT = "2.0.18"


def live_usage_version(fixtures: Path, pinned: str) -> str:
    """The version whose ``live-usage-<v>.json`` stands for the pin: its own when the citations were re-read for it,
    else :data:`LIVE_USAGE_READ_AT`'s."""
    return pinned if (fixtures / f"live-usage-{pinned}.json").exists() else LIVE_USAGE_READ_AT


def check_live_usage_citations(ctx: Context, fixtures: Path, pinned: str) -> Outcome:
    """Each identifier ``live-usage-<v>.json`` cites in the bundled JavaScript, searched in this binary. The bundle is
    minified, and minified names differ from build to build (the Linux 2.0.18 build lacks 12 of the 20, measured
    2026-11-07), so the search is a fact only in the binary the citations were read from (``source.binary_sha256``).
    In any other build it is reported as not comparable, with the count found: the citations are then re-read for
    that build. The file:line citations of the tag's source are not in a binary, so they are carried, not checked."""
    doc = json.loads((fixtures / f"live-usage-{pinned}.json").read_text(encoding="utf-8"))
    blob = _bundle(ctx)
    found = {e["id"]: e["identifier"].encode() in blob for e in doc["source"]["evidence"]
             if "bundled JavaScript" in str(e.get("file")) and e.get("identifier")}
    missing = sorted(k for k, v in found.items() if not v)
    if doc["source"].get("binary_sha256") != core_sha256(ctx.binary):
        return Outcome(SKIPPED, notes=[
            f"not comparable: the citations were read from another build, and minified names differ by build "
            f"({len(found) - len(missing)} of {len(found)} found here); re-read them for this binary"])
    notes = [f"not in this binary: {', '.join(missing)}"] if missing else []
    return Outcome(FAIL if missing else PASS, {"live_usage.bundle_identifiers": found}, notes)


def check_ripgrep(ctx: Context) -> Outcome:
    versions = sorted({m.decode() for m in re.findall(rb"ripgrep/releases/download/(\d+\.\d+\.\d+)/", _bundle(ctx))})
    return Outcome(PASS if len(versions) == 1 else FAIL, {"ripgrep.download_version": versions},
                   [] if len(versions) == 1 else [f"download versions found: {versions}"])


# -------------------------------------------------------------------------------------------------- the version feed

class Feed:
    """OpenCode's desktop update feed (``latest-linux.yml``): the version and the rpm's sha512 the feed gives."""

    def __init__(self, url: str = FEED, fetch: Any = None) -> None:
        self.url = url
        self.fetch = fetch or _fetch_https

    def latest(self) -> list[Release]:
        return parse_feed(self.fetch(self.url), self.url)


def _fetch_https(url: str) -> str:
    if not url.startswith("https://"):
        raise ValueError(f"the feed is fetched over https only, not {url!r}")
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (https only, checked above)
        return r.read().decode()


def parse_feed(text: str, url: str = FEED) -> list[Release]:
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    out = []
    for m in re.finditer(r"-\s*url:\s*(\S+)\s+sha512:\s*(\S+)(?:\s+size:\s*(\d+))?", text):
        # the live feed gives absolute URLs (2026-11-07); a relative one is the feed's own folder's
        where = m.group(1) if re.match(r"https?://", m.group(1)) else url.rsplit("/", 1)[0] + "/" + m.group(1)
        out.append(Release(version=version.group(1) if version else "?", url=where, digest=m.group(2),
                           size=int(m.group(3)) if m.group(3) else None))
    return out


# -------------------------------------------------------------------------------------------------------- the pack

def _render_json(value: Any, indent: int = 0, width: int = 120, prefix: int = 0) -> str:
    """The usage fixture's hand layout: two-space indent, and an object or array on one line when it fits ``width``."""
    flat = json.dumps(value)
    if not isinstance(value, (dict, list)) or not value or indent + prefix + len(flat) <= width:
        return flat
    pad, inner = " " * indent, " " * (indent + 2)
    if isinstance(value, dict):
        rows = [f'{inner}{json.dumps(k)}: {_render_json(v, indent + 2, width, len(json.dumps(k)) + 2)}'
                for k, v in value.items()]
        return "{\n" + ",\n".join(rows) + f"\n{pad}}}"
    rows = [f"{inner}{_render_json(v, indent + 2, width)}" for v in value]
    return "[\n" + ",\n".join(rows) + f"\n{pad}]"


class OpenCodePack:
    harness = HARNESS

    def __init__(self, fixtures: Path) -> None:
        self.fixtures = fixtures
        self.version_source = Feed()
        # The pinned version, whose fixtures are the inputs and the pin: the adapter's tested version (its owner).
        self.pinned_version = C.TESTED_VERSIONS[0]

    def declared(self) -> Mapping[str, Mapping[str, Any]]:
        return {name: {"status": s.status, "how": s.how, "register": s.register}
                for name, s in OpenCodeAdapter.harness_capabilities.items()}

    def read_version(self, binary: Path, work: Path, env: dict[str, str]) -> str:
        return read_version(binary, work, env)

    def checks(self) -> list[Check]:
        from .messaging import checks as messaging_checks

        fx, pin = self.fixtures, self.pinned_version
        api = [
            Check("api.openapi", check_openapi, depth=API,
                  says="the served API has everything capabilities.problems checks; trims it as the pinned fixture",
                  measures=("openapi.min", "openapi.problems", "api.policy_actions")),
            Check("api.wake_idle_session",
                  lambda c: _api_capability(c, [("op", "POST /api/session/{sessionID}/prompt")]),
                  ("wake_idle_session",), depth=API, says="session.prompt is served"),
            Check("api.queue_until_turn_end",
                  lambda c: _api_capability(c, [("enum", "Session.Inbox.Delivery=queue")]),
                  ("queue_until_turn_end",), depth=API, says="delivery: queue is served"),
            Check("api.steer_running_turn",
                  lambda c: _api_capability(c, [("enum", "Session.Inbox.Delivery=steer")]),
                  ("steer_running_turn",), depth=API, says="delivery: steer is served"),
            Check("api.interrupt_turn",
                  lambda c: _api_capability(c, [("op", "POST /api/session/{sessionID}/interrupt")]),
                  ("interrupt_turn",), depth=API, says="session.interrupt is served"),
            Check("api.read_model_list",
                  lambda c: _api_capability(c, [("op", "GET /api/model")]),
                  ("read_model_list",), depth=API, says="the model catalog doctor reads is served"),
        ]
        behaviour = [
            Check("usage.openai", lambda c: check_usage(c, fx, pin), ("read_usage", "wake_idle_session"),
                  says="each raw Responses usage, stored as the message's tokens: the token semantics; also the "
                       "declared-only catalog entry, the http transport, and a prompt starting an idle session",
                  measures=("usage.openai", "catalog.declared_only", "relay.transport_http")),
            Check("progress.tool_parts", check_tool_parts, ("read_progress",),
                  says="write input.path, edit metadata.files, shell input.command and metadata.exit, time.*",
                  measures=("tool_parts",)),
        ]
        behaviour.append(Check("relay.websocket_default", check_websocket_default,
                               says="without transport http, OpenAI's SDK tries a WebSocket first",
                               measures=("relay.websocket_first",)))
        behaviour.append(Check("login.store", check_login_store, measures=("login.store", "store.schema"),
                               says="a synthetic key, stored by the server in a private home, reads as AEW's login "
                                    "reader expects; the store is the one the Lead's own store handling knows"))
        citations = [
            Check("usage.live_citations", lambda c: check_live_usage_citations(c, fx, live_usage_version(fx, pin)),
                  ("read_usage",),
                  depth=CITATION, says="every bundled-code identifier probe P1 cites is in this binary",
                  measures=("live_usage.bundle_identifiers",)),
            Check("ripgrep.download", check_ripgrep, depth=CITATION,
                  says="the ripgrep version OpenCode downloads when none is on PATH",
                  measures=("ripgrep.download_version",)),
        ]
        # The live lane's driver cannot drive some actions (``harness_conformance``'s "cannot drive" skip): its
        # limits, not tests that went unrun.
        return [*api, *messaging_checks(), *behaviour, *citations,
                *neutral_checks(HARNESS, "AEW_OPENCODE_BIN", conformance=["tests/live/test_opencode_live.py"],
                                allowed_skips={r"^opencode-live cannot drive \[": 1})]

    def pinned(self, fixtures: Path) -> tuple[str, dict[str, Any]]:
        version = self.pinned_version
        load = lambda name: json.loads((fixtures / name).read_text(encoding="utf-8"))  # noqa: E731
        spec = load(f"openapi-{version}.min.json")
        usage = load(f"usage-{version}-openai.json")
        live = load(f"live-usage-{live_usage_version(fixtures, version)}.json")
        facts: dict[str, Any] = {
            "openapi.min": spec, "openapi.problems": C.problems(spec), "api.policy_actions": _policy_actions(spec),
            "usage.openai": {"token_semantics": usage["token_semantics"], "cases": usage["cases"]},
            "live_usage.bundle_identifiers": {e["id"]: True for e in live["source"]["evidence"]
                                              if "bundled JavaScript" in str(e.get("file")) and e.get("identifier")},
            # The adapter's own assumptions, owned by its code: a declared-only entry (adapter.declared_only), the
            # http transport (projection.relayed), and the ripgrep AEW ships (capability.records).
            "catalog.declared_only": {"listed": True, "declared_only": True},
            "ripgrep.download_version": [_shipped_ripgrep()],
            # login._read's key shape ({type: "key", key}), and every column AEW's credential SQL names
            # login._read's key shape ({type: "key", key}), and the credential table AEW writes to (CREDENTIAL_SCHEMA)
            "login.store": {"schema": credential_schema(), "key_row_reads_as": "key",
                            "key_value_fields": ["key", "type"], "rules_tables_unknown": []},
            "relay.transport_http": {"upgrades": 0, "route": ["/v1/responses"]},
            "relay.websocket_first": {"openai": "openai" in projection.WEBSOCKET_FIRST},
        }
        tool_parts = fixtures / f"tool-parts-{version}.json"
        if tool_parts.exists():
            facts["tool_parts"] = load(tool_parts.name)["tool_parts"]
        store = fixtures / f"store-{version}.json"
        if store.exists():
            facts["store.schema"] = load(store.name)["tables"]
        messaging = fixtures / f"messaging-{version}.json"
        if messaging.exists():
            facts.update(load(messaging.name)["facts"])
        return version, facts

    def render(self, version: str, facts: Mapping[str, Any], fixtures: Path) -> dict[str, tuple[bytes | None, str]]:
        out: dict[str, tuple[bytes | None, str]] = {}
        if "openapi.min" in facts:
            out[f"openapi-{version}.min.json"] = (dump(facts["openapi.min"]), "measured: the served API, trimmed")
        usage = facts.get("usage.openai")
        pinned_usage = fixtures / f"usage-{self.pinned_version}-openai.json"
        if usage and pinned_usage.exists():
            carried = json.loads(pinned_usage.read_text(encoding="utf-8"))
            doc = {"harness": HARNESS, "version": version, "provider": "openai",
                   "token_semantics": usage["token_semantics"], "source": carried["source"], "cases": usage["cases"]}
            tag = str(carried["source"].get("tag") or f"v{carried['version']}")  # the citations' own, not the file's
            out[f"usage-{version}-openai.json"] = (
                (_render_json(doc) + "\n").encode(),
                "measured: token_semantics and each case's stored tokens; carried: `source` (citations of the "
                + (f"{tag} tag" if tag == f"v{version}" else f"{tag} tag: re-read them at v{version}") + ")")
        out[f"live-usage-{version}.json"] = (
            None, "authored, not a measurement: its findings, cases and event payloads are written from source "
                  "reading; the run searches the binary for each bundled-code identifier it cites and says whether the "
                  "binary is the one they were read from (usage.live_citations)")
        if "store.schema" in facts:
            out[f"store-{version}.json"] = (
                dump({"harness": HARNESS, "version": version, "probe": "harness_qualify login.store",
                      "tables": facts["store.schema"]}),
                "measured: the store a private server made, every table and its columns")
        if "tool_parts" in facts:
            out[f"tool-parts-{version}.json"] = (
                dump({"harness": HARNESS, "version": version, "probe": "harness_qualify progress.tool_parts",
                       "tool_parts": facts["tool_parts"]}), "measured: a real run with the scripted model")
        messaging = {k: v for k, v in facts.items() if k.startswith("messaging.")}
        if messaging:
            out[f"messaging-{version}.json"] = (
                dump({"harness": HARNESS, "version": version, "facts": messaging}),
                "measured: messaging behaviour with the scripted loopback model; platform is in the run record")
        return out

    def unmeasured(self) -> Mapping[str, str]:
        return {
            "login.oauth_shape": "an OAuth row needs a real login flow with a provider; the key row is measured "
                                 "(login.store), the OAuth shape stays login.py's citation",
            "lead.tui_preferences": "cli.json is read by the TUI, which needs a terminal and a person; not run "
                                    "offline",
            "readable.tui_display": "what OpenCode's TUI shows a person is seen, not served",
            "live_usage.findings": "probe P1's findings are source reading, not a run's output (usage.live_citations "
                                   "checks the identifiers they rest on)",
        }

    def adoptable(self, facts: Mapping[str, Any], pinned: Mapping[str, Any]) -> list[str]:
        new = sorted(set(facts.get("api.policy_actions") or []) - set(pinned.get("api.policy_actions") or []))
        return [f"policy actions: {', '.join(new)}"] if new else []


def _shipped_ripgrep() -> str:
    from aew.capability import records

    text = Path(records.__file__).read_text(encoding="utf-8")
    m = re.search(r"ripgrep/releases/download/(\d+\.\d+\.\d+)/", text)
    return m.group(1) if m else "?"
