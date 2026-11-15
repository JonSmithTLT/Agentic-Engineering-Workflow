"""Measure relisting and model visibility across two prompts in one session."""

from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path

from harness_qualify import model, opencode
from harness_qualify.core import private_env

from aew.harness.opencode.client import location
from aew.harness.opencode.projection import lead_provider_policies

from . import measure, standin

SERVER = "stand"


def config(url: str, declared: bool, order: str, methods: Path) -> dict:
    from ipaddress import ip_address
    from urllib.parse import urlsplit

    target = urlsplit(url)
    if target.scheme != "http" or not ip_address(target.hostname or "").is_loopback:
        raise ValueError("the scripted server must use loopback HTTP")
    result = opencode.server_config(url)
    result["experimental"] = {"policies": lead_provider_policies()}
    result["mcp"] = {"servers": {SERVER: {
        "type": "local", "codemode": False, "pool": False,
        "command": [sys.executable, str(Path(standin.__file__).resolve()),
                    str(declared).lower(), order, str(methods)],
    }}}
    return result


def run(binary: Path, out: Path) -> list[dict]:
    cases = []
    for declared in (True, False):
        for order in ("before", "after"):
            case = out / f"{str(declared).lower()}-{order}"
            env = private_env(case / "private", harness="opencode")
            methods = case / "methods.txt"
            llm = model.start("responses", [
                {"call": [f"{SERVER}_{standin.FIRST}", standin.FIRST], "arguments": {}},
                {"text": "First turn finished."},
                {"text": "Second turn finished."},
            ], capture_wire=True)
            try:
                with opencode.serve(binary, case, env, config(llm.base_url, declared, order, methods),
                                    {"OPENAI_API_KEY": opencode.SYNTHETIC_KEY}) as server:
                    directory = str((case / "project").resolve())
                    ref = {"providerID": "openai", "id": opencode.MODEL}
                    deadline = time.monotonic() + opencode.TURN_S
                    while time.monotonic() < deadline:
                        models = (server.client.get("/api/model", location(directory)) or {}).get("data") or []
                        if any(entry.get("id") == opencode.MODEL for entry in models):
                            break
                        time.sleep(0.25)
                    else:
                        raise TimeoutError("the scripted model did not appear in the catalog")
                    session = server.client.post("/api/session", {
                        "title": "Tool-list probe", "agent": opencode.AGENT, "model": ref,
                        "location": {"directory": directory},
                    })
                    sid = (session.get("data") or session)["id"]
                    turns = []
                    for index in (1, 2):
                        start = len(llm.requests)
                        mid = "msg_" + secrets.token_hex(12)
                        server.client.post(f"/api/session/{sid}/prompt", {"id": mid, "text": f"Scripted turn {index}."})
                        deadline = time.monotonic() + opencode.TURN_S
                        while time.monotonic() < deadline:
                            active = (server.client.get("/api/session/active") or {}).get("data") or {}
                            messages = opencode._messages(server, sid)
                            ids = [message.get("id") for message in messages]
                            if sid not in active and mid in ids and messages[-1].get("type") == "idle" \
                                    and ids.index(mid) < len(ids) - 1:
                                break
                            time.sleep(0.25)
                        else:
                            raise TimeoutError(f"the scripted turn {index} did not become idle")
                        turns.append([r["tools"] for r in llm.requests[start:] if r.get("main")])
                        time.sleep(0.25)  # Allow a pending 100 ms relist to settle before the next prompt.
                if len(turns[0]) < 2 or not turns[1]:
                    raise ValueError("the stand-in call or second turn did not reach the scripted model")
                added = {f"{SERVER}_{standin.ADDED}", standin.ADDED}
                cases.append({
                    "declared": declared, "notification_order": order,
                    "mcp_methods": methods.read_text(encoding="utf-8").splitlines(), "tools_by_turn": turns,
                    "served_provider_ids": sorted({entry["providerID"] for entry in models}),
                    "next_request_has_added_tool": bool(added.intersection(turns[0][1])),
                    "next_turn_has_added_tool": bool(added.intersection(turns[1][0])),
                })
            finally:
                llm.close()
                measure.save_requests(case / "requests", llm.requests)
    return cases
