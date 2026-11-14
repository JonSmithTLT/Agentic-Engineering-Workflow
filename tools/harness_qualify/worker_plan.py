"""Keyless qualification of the worker OAuth route in a verified loopback-only namespace.

Run with ``python tools/harness_qualify --binary <pinned-cli> --out <dir>
--only login.worker_plan_route --no-network``. The check records evidence and leaves adoption unchanged.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import socket
import sqlite3
import subprocess
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from aew.harness.containment import netns, relay
from aew.harness.opencode import capabilities, login
from aew.harness.opencode.adapter import declared_only

from . import model
from .core import FAIL, PASS, Context, Outcome, network_state

PATH = "/backend-api/codex"
ACCESS = "synthetic-qualify-plan-access"
ACCOUNT = "synthetic-qualify-plan-account"
FACT = "login.worker_plan_route"
# GPT-5.5 and its effort variants come from the 2.2.6 catalog endpoint, captured 2026-11-14 UTC.
CATALOG_SOURCE = "https://models.opencode.ai/experimental/v2.0/api.json"
CAPTURE = Path(__file__).with_name("openai-gpt-5.5-catalog.json")
MODEL = "gpt-5.5"
VARIANT = "medium"
PRICES = {"input": 7, "output": 19}  # synthetic prices per million tokens
USAGE = {**model.ZERO_USAGE, "input_tokens": 1000, "output_tokens": 100}


def _seed_catalog(ctx: Context, env: dict[str, str]) -> dict[str, Any]:
    """Keep the captured model's routing and capabilities and replace its pricing for the synthetic probe."""
    catalog = json.loads(CAPTURE.read_bytes())
    entry = catalog["openai"]["models"][MODEL]
    entry["cost"] = {"text": {kind: {"price": rate} for kind, rate in PRICES.items()}}
    raw = json.dumps(catalog, sort_keys=True).encode()
    path = ctx.work / "synthetic-models.json"
    path.write_bytes(raw)
    env.update(OPENCODE_MODELS_PATH=str(path.resolve()), OPENCODE_DISABLE_MODELS_FETCH="1")
    prices = {kind: item["price"] for kind, item in entry["cost"]["text"].items()}
    return {"seeded": True, "source": CATALOG_SOURCE, "captured_on": "2026-11-14",
            "sha256": hashlib.sha256(raw).hexdigest(), "prices_per_million": prices}


def check(ctx: Context, *, fake_upstream: Callable[..., model.ResponsesModel] = model.ResponsesModel) -> Outcome:
    """The fake upstream factory is an in-process tools seam. Policy and environment cannot set it."""
    from . import opencode as oc

    if not network_state().startswith("blocked: run under"):
        return Outcome(FAIL, notes=["run this probe with --no-network in a verified loopback-only namespace"])
    if ctx.version not in capabilities.TESTED_VERSIONS:
        return Outcome(FAIL, notes=["the binary is not the pinned OpenCode version"])
    env = {name: value for name, value in ctx.env.items() if name.upper() != "OPENAI_API_KEY"}
    env.pop("OPENCODE_DB", None)
    ctx.work.mkdir(parents=True, exist_ok=True)
    if not login.db_path(env).resolve().is_relative_to(ctx.work.resolve()):
        return Outcome(FAIL, notes=["the synthetic worker database must be inside the private probe directory"])
    seed = _seed_catalog(ctx, env)
    subprocess.run([*oc.command(ctx.binary), "session", "list"], cwd=ctx.work, env=env, check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    worker_db = login.db_path(env)
    host_db = ctx.work / "synthetic-operator.db"
    sentinel = relay.sentinel()
    now = int(time.time() * 1000)

    def value(access: str, account: str, expires: int) -> str:
        return json.dumps({"type": "oauth", "methodID": "chatgpt-browser", "access": access,
                           "refresh": login.RELAY_NO_REFRESH, "expires": expires, "metadata": {"accountID": account}})

    login.own_store(worker_db, ctx.work)
    if not worker_db.is_file():
        return Outcome(FAIL, notes=["offline session list did not create the private worker database"])
    with closing(sqlite3.connect(worker_db)) as worker, closing(sqlite3.connect(host_db)) as host:
        login.require_schema(worker, "credential", login.CREDENTIAL_SCHEMA)
        if worker.execute("SELECT 1 FROM credential LIMIT 1").fetchone():
            return Outcome(FAIL, notes=["the worker seed already contains credentials"])
        worker.backup(host)
        for db, access, account in ((worker, sentinel, "synthetic-placeholder"), (host, ACCESS, ACCOUNT)):
            with db:
                db.execute(login.CREDENTIAL_INSERT, (
                    "cred_aew_openai", "openai", "AEW relay", value(access, account, now + 86400_000),
                    "chatgpt-browser", 1, now, now,
                ))
    resolver = login.StoredLogin("openai", {"OPENCODE_DB": str(host_db)})
    request_headers: list[tuple[bool, bool]] = []

    def observe_headers(headers: Any) -> None:
        request_headers.append((headers.get("Authorization") == f"Bearer {ACCESS}",
                                headers.get("chatgpt-account-id") == ACCOUNT))

    upstream = fake_upstream([{"text": "done", "usage": USAGE}] * 2, observe_headers=observe_headers)
    try:
        target = relay.Upstream(upstream.base_url.removesuffix("/v1") + PATH)
        if target.host != "127.0.0.1" or target.scheme != "http":
            return Outcome(FAIL, notes=["the qualification upstream must be loopback HTTP"])
        destinations: list[tuple[str, int]] = []

        def connect(host: str, port: int, timeout: float) -> socket.socket:
            destinations.append((host, port))
            if (host, port) != (target.host, target.port):
                raise OSError("the probe can only connect to the fake upstream")
            return socket.create_connection((host, port), timeout=timeout)

        busy = False

        def grant() -> relay.Grant:
            nonlocal busy
            if busy:
                busy = False
                raise relay.Unavailable("synthetic busy store", cause="unreadable", retryable=True)
            return netns._grant(sentinel, resolver.worker_grant)

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with relay.ProviderRelay(target, {}, listener=listener, connect=connect, resolve=grant) as service:
                base = f"http://127.0.0.1:{port}{PATH}"
                listing_problem, cost = _turn(oc, ctx, env, base)
                baseline = any(req.get("main") and req["path"] == PATH + "/responses" for req in upstream.requests)
                requests_before_retry = len(upstream.requests)
                retry_count = 0
                if baseline:
                    busy = True
                    _turn(oc, ctx, env, base)
                    retry_count = service.counts().get("credential:unreadable_retryable", 0)
                retry = retry_count == 1 and len(upstream.requests) > requests_before_retry
                busy = False
                before = len(destinations)
                expires = int(time.time() * 1000) + 60_000
                with closing(sqlite3.connect(host_db)) as db, db:
                    db.execute("UPDATE credential SET value = ?", (value(ACCESS, ACCOUNT, expires),))
                with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=5)) as client:
                    client.request("POST", PATH + "/responses", b"{}", {"Authorization": f"Bearer {sentinel}"})
                    answer = client.getresponse()
                    expiry = {"status": answer.status, "expired": b"(expired)" in answer.read(),
                              "connected": len(destinations) != before}
                counts = service.counts()
        paths = sorted({req["path"] for req in upstream.requests})
        auth = bool(request_headers) and all(auth for auth, _ in request_headers)
        account = bool(request_headers) and all(account for _, account in request_headers)
        only_fake = bool(destinations) and set(destinations) == {(target.host, target.port)}
        key_in_env = "OPENAI_API_KEY" in env
        facts: dict[str, Any] = {
            "paths": paths, "authorization_substituted": auth, "account_id_substituted": account,
            "only_fake_upstream": only_fake, "key_in_environment": key_in_env,
            "model": {"providerID": "openai", "id": MODEL, "variant": VARIANT},
            "catalog": seed, "model_listed": listing_problem is None,
            "scripted_usage": USAGE, "reported_cost": cost, "saw_503": retry_count == 1,
            "retried_503": retry, "one_minute_expiry": expiry, "relay_counts": counts,
        }
        notes = [note for passed, note in (
            (baseline, "No scripted model request reached the fake upstream through the plan relay"),
            (all(path.startswith(PATH + "/") for path in paths), "A request fell outside the Codex path prefix"),
            (auth, "The relay did not demonstrate Authorization substitution"),
            (account, "The relay did not demonstrate account-id substitution"),
            (only_fake, "The relay did not demonstrate exclusive use of the fake upstream"),
            (not key_in_env, "OPENAI_API_KEY was present in the worker environment"),
            (listing_problem is None, listing_problem),
            (all(rate > 0 for rate in seed["prices_per_million"].values()), "The catalog seed did not price usage"),
            (baseline and bool(cost) and all(type(value) in (int, float) and value == 0 for value in cost),
             "OpenCode did not report zero cost for the priced synthetic turn" if baseline
             else "No scripted model turn ran, so there is no turn cost to verify"),
            (retry_count == 1, "The relay did not deliver exactly one retryable credential 503"),
            (expiry == {"status": 401, "expired": True, "connected": False},
             "The one-minute expiry did not return 401 (expired) without an upstream connection"),
        ) if not passed]
        return Outcome(FAIL if notes else PASS, {FACT: facts}, notes=notes)
    finally:
        upstream.close()


def _turn(oc: Any, ctx: Context, env: dict[str, str], base: str) -> tuple[str | None, list[Any]]:
    work = ctx.work / "worker"
    with oc.serve(ctx.binary, work, env, oc.server_config(base, model_id=MODEL)) as server:
        loc = oc.location(str((work / "project").resolve()))
        deadline = time.monotonic() + oc.TURN_S
        match = None
        while time.monotonic() < deadline:
            catalog = (server.client.get("/api/model", loc) or {}).get("data") or []
            match = next((m for m in catalog if m.get("providerID") == "openai" and m.get("id") == MODEL
                          and not declared_only(m)), None)
            if match is not None:
                break
            time.sleep(0.25)
        if match is None:
            return "The pinned model was never offered by the OAuth catalog", []
        if VARIANT not in [v.get("id") for v in match.get("variants") or []]:
            return f"The pinned model did not offer the {VARIANT} variant", []
        if match.get("enabled") is False:
            return "The pinned model was disabled", []
        session = server.client.post("/api/session", {
            "title": "worker plan qualification", "agent": oc.AGENT,
            "model": {"providerID": "openai", "id": MODEL, "variant": VARIANT},
            "location": {"directory": str((work / "project").resolve())}, "permissions": oc._ALL_ALLOWED})
        sid = (session.get("data") or session)["id"]
        mid = "msg_" + oc.secrets.token_hex(12)
        server.client.post(f"/api/session/{sid}/prompt", {"id": mid, "text": "Use the scripted response."})
        deadline = time.monotonic() + oc.TURN_S
        while time.monotonic() < deadline:
            messages = oc._messages(server, sid)
            if any(m.get("id") == mid for m in messages) and messages[-1].get("type") == "idle":
                return None, [m.get("cost") for m in messages if m.get("type") == "assistant"]
            time.sleep(0.25)
        return None, []
