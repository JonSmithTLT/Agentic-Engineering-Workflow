"""Apply the T1 prototype's wiring edits to the frozen tree (idempotence is not attempted: run once on a clean branch)."""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1])


def edit(rel, old, new, count=1):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    if s.count(old) != count:
        raise SystemExit(f"{rel}: expected {count} occurrence(s) of {old[:70]!r}, found {s.count(old)}")
    p.write_text(s.replace(old, new), encoding="utf-8")
    print("edited", rel)


# A. schema registry + $defs accessor
edit("src/aew/schemas/__init__.py",
     '    "history": "history.schema.json",\n}',
     '    "history": "history.schema.json",\n    "surface": "surface.schema.json",\n}')
edit("src/aew/schemas/__init__.py",
     'def validate(name: str, instance: Any, *, source: str) -> None:',
     'def schema_defs(name: str) -> dict[str, Any]:\n'
     '    """The ``$defs`` of a schema, as plain data (a transport advertising the shape of what it returns)."""\n'
     '    return json.loads(json.dumps(cast(dict[str, Any], _validator(name).schema).get("$defs", {})))\n\n\n'
     'def validate(name: str, instance: Any, *, source: str) -> None:')

# B. the Lead broker: a `lead.tool` operation, and run_cli as a module function both transports share
edit("src/aew/harness/lead_broker.py",
     'OPERATIONS: bridge.Operations = {"lead.cli": {"argv": list, "cwd": str, "stdin": str},\n'
     '                                 "lead.whoami": {}}  # does this session hold Lead authority? (M3-D10)',
     'OPERATIONS: bridge.Operations = {"lead.cli": {"argv": list, "cwd": str, "stdin": str},\n'
     '                                 "lead.whoami": {},  # does this session hold Lead authority? (M3-D10)\n'
     '                                 # the typed Lead surface (aew.surface, T1): one tool, its arguments as JSON text\n'
     '                                 "lead.tool": {"name": str, "arguments": str}}')
edit("src/aew/harness/lead_broker.py",
     '        if op == "lead.whoami":\n'
     '            lead = self.engine.store.read()["lead"]\n'
     '            return {"generation": lead["generation"], "session_label": lead.get("session_label")}\n'
     '        return self._run_cli(list(args["argv"]), args["cwd"], args["stdin"])\n',
     '        if op == "lead.whoami":\n'
     '            lead = self.engine.store.read()["lead"]\n'
     '            return {"generation": lead["generation"], "session_label": lead.get("session_label")}\n'
     '        if op == "lead.tool":\n'
     '            return self._run_tool(args["name"], args["arguments"])\n'
     '        return self._run_cli(list(args["argv"]), args["cwd"], args["stdin"])\n'
     '\n'
     '    def _run_tool(self, name: str, arguments: str) -> dict[str, Any]:\n'
     '        """The typed surface (``aew.surface``, T1): one tool, run with the held credential. Its ``cli`` tool runs\n'
     '        through ``_run_cli``, so every refusal above applies to it unchanged."""\n'
     '        import json\n'
     '\n'
     '        from aew.surface import run as surface_run\n'
     '\n'
     '        try:\n'
     '            parsed = json.loads(arguments)\n'
     '        except ValueError:\n'
     '            raise errors.UsageError("lead.tool: arguments must be a JSON object, as text") from None\n'
     '        if not isinstance(parsed, dict):\n'
     '            raise errors.UsageError("lead.tool: arguments must be a JSON object, as text")\n'
     '        cwd = str(self.engine.repo_root)\n'
     '        with dispatch.channel("lead_mcp"):  # its dispatches record that the typed surface carried them\n'
     '            return surface_run.run_tool(self.engine, self._token, name, parsed,\n'
     '                                        run_cli=lambda argv, stdin: self._run_cli(argv, cwd, stdin))\n')
edit("src/aew/harness/lead_broker.py",
     '    def _run_cli(self, argv: list[str], cwd: str, stdin: str) -> dict[str, Any]:\n'
     '        from aew.cli.main import build_parser\n'
     '        from aew.engine.api import Engine\n'
     '\n'
     '        parser = build_parser()\n',
     '    def _run_cli(self, argv: list[str], cwd: str, stdin: str) -> dict[str, Any]:\n'
     '        return run_cli(self.engine, self._token, argv, cwd, stdin)\n'
     '\n'
     '\n'
     'def run_cli(engine: Any, token: str, argv: list[str], cwd: str, stdin: str, *,\n'
     '            channel: str = "lead_broker") -> dict[str, Any]:\n'
     '    """One Lead-authenticated command, parsed as the CLI parses it and run with ``token``, under the broker\'s\n'
     '    refusals. The broker calls it for ``lead.cli``; the typed surface\'s ``cli`` tool calls it on every transport,\n'
     '    so the primitive surface has one definition (WC §15.6, invariant 21)."""\n'
     '    from aew.cli.main import build_parser\n'
     '    from aew.engine.api import Engine\n'
     '\n'
     '    parser = build_parser()\n')
# the body of the old method now lives in the module function: fix its self-references and indentation
p = ROOT / "src/aew/harness/lead_broker.py"
s = p.read_text(encoding="utf-8")
start = s.index("def run_cli(engine: Any, token: str")
body_start = s.index("    parser = build_parser()\n", start)
end = s.index("\n\ndef forward(", start)
body = s[body_start:end]
body = body.replace("self.engine.aew_root", "engine.aew_root").replace("ns.token = self._token", "ns.token = token")
body = body.replace('with dispatch.channel("lead_broker"):  # its dispatches record that the broker relayed them (M4-A)',
                    'with dispatch.channel(channel):  # its dispatches record who carried them (M4-A)')
out = []
for ln in body.split("\n"):
    out.append(ln[4:] if ln.startswith("    ") else ln)
s = s[:body_start] + "\n".join(out) + s[end:]
p.write_text(s, encoding="utf-8")
print("edited run_cli body")

# C. CLI: `aew lead tool` and `aew lead mcp`
edit("src/aew/cli/commands.py",
     '    q.add_argument("harness_command", nargs=argparse.REMAINDER, help="-- COMMAND [ARGS...]")\n'
     '    q.set_defaults(handler=_lead_session)\n',
     '    q.add_argument("harness_command", nargs=argparse.REMAINDER, help="-- COMMAND [ARGS...]")\n'
     '    q.set_defaults(handler=_lead_session)\n'
     '\n'
     '    q = lsub.add_parser("tool", help="run one tool of the typed Lead surface: the same catalog the MCP server "\n'
     '                                     "serves, over the CLI (aew.surface; architecture review T1)")\n'
     '    q.add_argument("name", nargs="?", help="a tool name (see --list)")\n'
     '    q.add_argument("--arguments", default="{}", help="the tool\'s arguments as a JSON object (or via --fields)")\n'
     '    q.add_argument("--list", action="store_true", help="list the tools and their argument schemas")\n'
     '    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN); none inside a Lead session")\n'
     '    q.set_defaults(handler=_lead_tool)\n'
     '\n'
     '    q = lsub.add_parser("mcp", help="serve the typed Lead surface over MCP (stdio): spawned by the Lead\'s harness "\n'
     '                                    "inside a Lead session, or run in an operator shell that holds AEW_LEAD_TOKEN")\n'
     '    q.set_defaults(handler=_lead_mcp)\n')
edit("src/aew/cli/commands.py",
     'def _opencode(args: argparse.Namespace) -> Any:\n',
     'def _lead_tool(args: argparse.Namespace) -> Any:\n'
     '    import json\n'
     '\n'
     '    from aew.harness import lead_broker\n'
     '    from aew.surface import contract, run\n'
     '\n'
     '    if args.list:\n'
     '        return {"ok": True, "surface": contract.SURFACE_VERSION,\n'
     '                "tools": [contract.mcp_tool(t) for t in contract.exposed()]}\n'
     '    if not args.name:\n'
     '        raise UsageError("name a tool, or --list")\n'
     '    try:\n'
     '        arguments = json.loads(args.arguments)\n'
     '    except ValueError:\n'
     '        raise UsageError("--arguments must be a JSON object") from None\n'
     '    if not isinstance(arguments, dict):\n'
     '        raise UsageError("--arguments must be a JSON object")\n'
     '    engine, token = _engine(args), _lead_token(args)\n'
     '    return run.run_tool(engine, token, args.name, arguments,\n'
     '                        run_cli=lambda argv, stdin: lead_broker.run_cli(engine, token, argv, str(engine.repo_root),\n'
     '                                                                       stdin, channel="cli"))\n'
     '\n'
     '\n'
     'def _lead_mcp(args: argparse.Namespace) -> Any:\n'
     '    from aew.surface import mcp\n'
     '\n'
     '    mcp.serve(lambda: _engine(args))\n'
     '    return None\n'
     '\n'
     '\n'
     'def _opencode(args: argparse.Namespace) -> Any:\n')

# D. the Lead projection: the MCP server and its tools
edit("src/aew/harness/opencode/projection.py",
     '    rule("question", "allow"),\n]',
     '    rule("question", "allow"),\n'
     '    rule("aew_*", "allow"),  # the typed Lead surface\'s tools (the `aew` MCP server below): the engine refuses or commits\n]')
edit("src/aew/harness/opencode/projection.py",
     '    "- You never hold or see the Lead credential. This session\'s Lead broker carries out Lead-authenticated `aew` "\n'
     '    "commands for you. Mutations still need `--expect-rev <revision>` (from `aew status` or the previous command).",',
     '    "- You never hold or see the Lead credential. This session\'s Lead broker carries out Lead-authenticated `aew` "\n'
     '    "commands for you. Mutations still need `--expect-rev <revision>` (from `aew status` or the previous command).",\n'
     '    "- Prefer the `aew_*` tools (status, resume, explain, ticket_draft, ticket_start, ticket_request_review, "\n'
     '    "ticket_request_verification, harness_wait, checkpoint, cli): typed arguments, no shell, and every result "\n'
     '    "carries the new `revision`, the steps that completed, where a bundle stopped, and the actions and decisions "\n'
     '    "open next. `aew_cli` runs any other `aew` command with its arguments as a list.",')
edit("src/aew/harness/opencode/projection.py",
     '    system = f"{LEAD_SYSTEM}\\n\\n{guide}" if guide else LEAD_SYSTEM\n'
     '    return {"share": "disabled", "default_agent": LEAD_AGENT,\n',
     '    from aew.surface.contract import SERVER_NAME\n'
     '\n'
     '    system = f"{LEAD_SYSTEM}\\n\\n{guide}" if guide else LEAD_SYSTEM\n'
     '    # The typed Lead surface (T1): OpenCode spawns `aew lead mcp` in the TUI\'s curated environment, which holds the\n'
     '    # broker\'s coordinates and no credential; its tools appear as `aew_<name>`.\n'
     '    return {"share": "disabled", "default_agent": LEAD_AGENT,\n'
     '            "mcp": {SERVER_NAME: {"type": "local", "command": ["aew", "lead", "mcp"], "enabled": True}},\n')

# E. the CLI enumeration: the two new commands dispatch only through the engine's registered entrypoints
edit("tests/unit/test_dispatch_decision.py",
     '"lead takeover", "manifest adopt",',
     '"lead takeover", "lead tool", "lead mcp", "manifest adopt",')

# F. the probe agent: a text form of the revision for argv
edit("tests/helpers/mcp_probe_agent.py",
     '    if isinstance(value, str) and value == "$revision":\n        return (previous or {}).get("revision")\n',
     '    if isinstance(value, str) and value == "$revision":\n        return (previous or {}).get("revision")\n'
     '    if isinstance(value, str) and value == "$revision_text":\n        return str((previous or {}).get("revision"))\n')
# the server advertises no outputSchema per tool (it would repeat ~3 KB eleven times in every prompt, G2/F13)
edit("src/aew/surface/mcp.py",
     '    schema = output_schema()\n    return {"tools": [contract.mcp_tool(t, schema) for t in contract.exposed()]}',
     '    return {"tools": [contract.mcp_tool(t) for t in contract.exposed()]}  # no per-tool outputSchema: context cost')
print("all edits applied")
