"""Scripted stdio MCP peer for the tool-list experiment."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

FIRST, ADDED = "probe_a", "probe_b"
NOTICE = {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}


def serve(declared: bool, order: str, log: Path) -> None:
    tools = [{"name": FIRST, "description": "Add a second synthetic tool", "inputSchema": {"type": "object"}}]

    def send(message: dict) -> None:
        print(json.dumps({"jsonrpc": "2.0", **message}), flush=True)

    with log.open("a", encoding="utf-8", newline="\n") as methods:
        for line in sys.stdin:
            message = json.loads(line)
            method, request_id = message["method"], message.get("id")
            print(method, file=methods, flush=True)
            if request_id is None:
                continue
            result: dict = {}
            changed = method == "tools/call" and len(tools) == 1
            if method == "initialize":
                result = {
                    "protocolVersion": message["params"]["protocolVersion"],
                    "capabilities": {"tools": {"listChanged": declared}},
                    "serverInfo": {"name": "lead-probe", "version": "1"},
                }
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "tools/call":
                result = {"content": [{"type": "text", "text": "ok"}]}
                if changed:
                    tools.append({"name": ADDED, "description": "Added mid-session", "inputSchema": {"type": "object"}})
                    if order == "before":
                        send(NOTICE)
                        time.sleep(0.2)
            send({"id": request_id, "result": result})
            if changed and order == "after":
                send(NOTICE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("declared", choices=("true", "false"))
    parser.add_argument("order", choices=("before", "after"))
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    serve(args.declared == "true", args.order, args.log)
