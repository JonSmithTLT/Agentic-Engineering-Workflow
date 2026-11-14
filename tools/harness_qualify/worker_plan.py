"""Keyless qualification of the worker OAuth route in a verified loopback-only namespace.

Run with ``python tools/harness_qualify --binary <pinned-cli> --out <dir>
--only login.worker_plan_route --no-network``. The check records evidence and leaves adoption unchanged.
"""

from __future__ import annotations

import http.client
import json
import socket
import sqlite3
import subprocess
import time
from collections.abc import Callable
from contextlib import closing
from typing import Any

from aew.harness.containment import netns, relay
from aew.harness.opencode import capabilities, login

from . import model
from .core import FAIL, PASS, Context, Outcome, network_state

PATH = "/backend-api/codex"
ACCESS = "synthetic-qualify-plan-access"
ACCOUNT = "synthetic-qualify-plan-account"
FACT = "login.worker_plan_route"


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
    upstream = fake_upstream([{"text": "done"}], observe_headers=lambda headers: request_headers.append(
        (headers.get("Authorization") == f"Bearer {ACCESS}", headers.get("chatgpt-account-id") == ACCOUNT)))
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
                catalog, cost = _turn(oc, ctx, env, f"http://127.0.0.1:{port}{PATH}")
                requests_before_retry = len(upstream.requests)
                busy = True
                _turn(oc, ctx, env, f"http://127.0.0.1:{port}{PATH}")
                retry_count = service.counts().get("credential:unreadable_retryable", 0)
                retry = retry_count == 1 and len(upstream.requests) > requests_before_retry
                before = len(destinations)
                expires = int(time.time() * 1000) + 60_000
                with closing(sqlite3.connect(host_db)) as db, db:
                    db.execute("UPDATE credential SET value = ?", (value(ACCESS, ACCOUNT, expires),))
                with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=5)) as client:
                    client.request("POST", PATH + "/responses", b"{}", {"Authorization": f"Bearer {sentinel}"})
                    answer = client.getresponse()
                    expiry = {"status": answer.status, "expired": b"(expired)" in answer.read(),
                              "connected": len(destinations) != before}
        paths = sorted({req["path"] for req in upstream.requests})
        facts: dict[str, Any] = {"paths": paths, "authorization_substituted": bool(request_headers)
                                 and all(auth for auth, _ in request_headers),
                                 "account_id_substituted": bool(request_headers) and all(a for _, a in request_headers),
                                 "only_fake_upstream": bool(destinations) and set(destinations) == {
                                     (target.host, target.port)},
                                 "key_in_environment": "OPENAI_API_KEY" in env, "model_listed": catalog,
                                 "reported_cost": cost, "saw_503": retry_count == 1, "retried_503": retry,
                                 "one_minute_expiry": expiry}
        ok = (paths and all(path.startswith(PATH + "/") for path in paths)
              and facts["authorization_substituted"] and facts["account_id_substituted"]
              and facts["only_fake_upstream"] and not facts["key_in_environment"] and catalog and cost
              and facts["saw_503"]
              and expiry == {"status": 401, "expired": True, "connected": False})
        return Outcome(PASS if ok else FAIL, {FACT: facts})
    finally:
        upstream.close()


def _turn(oc: Any, ctx: Context, env: dict[str, str], base: str) -> tuple[bool, list[Any]]:
    work = ctx.work / "worker"
    with oc.serve(ctx.binary, work, env, oc.server_config(base)) as server:
        loc = oc.location(str((work / "project").resolve()))
        deadline = time.monotonic() + oc.TURN_S
        listed = False
        while time.monotonic() < deadline:
            catalog = (server.client.get("/api/model", loc) or {}).get("data") or []
            listed = any(m.get("providerID") == "openai" and m.get("id") == oc.MODEL for m in catalog)
            if listed:
                break
            time.sleep(0.25)
        if not listed:
            return False, []
        session = server.client.post("/api/session", {
            "title": "worker plan qualification", "agent": oc.AGENT, "model": {"providerID": "openai", "id": oc.MODEL},
            "location": {"directory": str((work / "project").resolve())}, "permissions": oc._ALL_ALLOWED})
        sid = (session.get("data") or session)["id"]
        mid = "msg_" + oc.secrets.token_hex(12)
        server.client.post(f"/api/session/{sid}/prompt", {"id": mid, "text": "Use the scripted response."})
        deadline = time.monotonic() + oc.TURN_S
        while time.monotonic() < deadline:
            messages = oc._messages(server, sid)
            if any(m.get("id") == mid for m in messages) and messages[-1].get("type") == "idle":
                return True, [m.get("cost") for m in messages if m.get("type") == "assistant"]
            time.sleep(0.25)
        return True, []
