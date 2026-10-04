"""Second pass of T1 wiring: the broker's run_cli indentation, the pinned OpenCode MCP config shape, the protocol
revision list, the capability probe, and long lines."""
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


# 1. the module-level run_cli: its first statement lost its indentation in the de-indent pass
edit("src/aew/harness/lead_broker.py",
     "    parser = build_parser()\n\nparser = build_parser()\n" if False else
     "    from aew.engine.api import Engine\n\nparser = build_parser()\n",
     "    from aew.engine.api import Engine\n\n    parser = build_parser()\n")

# 2. the Lead projection: the pinned 2.0.18 schema is mcp.servers.<name> = {type: local, command: [...]}
edit("src/aew/harness/opencode/projection.py",
     '            "mcp": {SERVER_NAME: {"type": "local", "command": ["aew", "lead", "mcp"], "enabled": True}},\n',
     '            "mcp": {"servers": {SERVER_NAME: {"type": "local", "command": ["aew", "lead", "mcp"]}}},\n')

# 3. the capability probe: the configuration keys the Lead projection now sets (checked against the served schema)
edit("src/aew/harness/opencode/capabilities.py",
     '    "Config.InfoEncoded": {"agents": O, "plugins": A, "snapshots": B, "update": S, "share": S, "lsp": B,\n'
     '                           "formatter": B, "default_agent": S, "permissions": A, "commands": O},',
     '    "Config.InfoEncoded": {"agents": O, "plugins": A, "snapshots": B, "update": S, "share": S, "lsp": B,\n'
     '                           "formatter": B, "default_agent": S, "permissions": A, "commands": O, "mcp": O},\n'
     '    "Mcp.LocalConfigEncoded": {"type": S, "command": A},  # the Lead surface\'s MCP server (T1)')

# 4. MCP protocol revisions OpenCode 2.0.18 speaks ("legacy" up to 2025-11-25)
edit("src/aew/surface/mcp.py",
     'PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first; the client\'s is echoed if we know it',
     'PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")  # newest first; a known one is echoed')

# 5. long lines
edit("src/aew/surface/contract.py",
     '               "review_evidence": {"type": "string", "description": "the review report you inspected (its evidence id)"},',
     '               "review_evidence": {"type": "string",\n'
     '                                   "description": "the review report you inspected (its evidence id)"},')
edit("tests/unit/test_dispatch_decision.py",
     '    "lead takeover", "lead tool", "lead mcp", "manifest adopt", "migrate", "opencode", "plan accept", "plan adopt", "plan lint",\n',
     '    "lead takeover", "lead tool", "lead mcp", "manifest adopt", "migrate", "opencode", "plan accept", "plan adopt",\n'
     '    "plan lint",\n')
edit("tests/unit/test_surface.py",
     '    assert not out["ok"] and out["stopped"]["boundary"] == "not_found" and out["stopped"]["error"]["code"] == "NOT_FOUND"\n',
     '    assert not out["ok"] and out["stopped"]["boundary"] == "not_found"\n'
     '    assert out["stopped"]["error"]["code"] == "NOT_FOUND"\n')
edit("tests/unit/test_surface.py",
     '    assert by_id[1]["result"]["serverInfo"]["name"] == contract.SERVER_NAME and "tools" in by_id[1]["result"]["capabilities"]\n',
     '    assert by_id[1]["result"]["serverInfo"]["name"] == contract.SERVER_NAME\n'
     '    assert "tools" in by_id[1]["result"]["capabilities"]\n')

# 6. a test: the Lead projection validates against the pinned OpenCode configuration schema
edit("tests/unit/test_surface.py",
     '# ---------------------------------------------------------------------------------------------- MCP framing\n',
     '# ---------------------------------------------------------------------------------------------- the projection\n'
     '\n'
     '\n'
     'def test_the_lead_projection_matches_the_pinned_opencode_configuration_schema():\n'
     '    """The MCP server entry is spelled as OpenCode 2.0.18\'s own schema spells it (the capability probe checks the\n'
     '    same keys against a served server)."""\n'
     '    from pathlib import Path\n'
     '\n'
     '    from aew.harness.opencode import capabilities, projection\n'
     '\n'
     '    spec = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "opencode" / "openapi-2.0.18.min.json")\n'
     '                      .read_text(encoding="utf-8"))\n'
     '    root = {"$ref": "#/components/schemas/Config.InfoEncoded", "components": spec["components"]}\n'
     '    config = projection.lead_config("guide text")\n'
     '    problems = [f"{list(e.absolute_path)}: {e.message}" for e in Draft202012Validator(root).iter_errors(config)]\n'
     '    assert not problems, problems\n'
     '    assert config["mcp"]["servers"][contract.SERVER_NAME]["command"] == ["aew", "lead", "mcp"]\n'
     '    assert capabilities.problems(spec) == [] if hasattr(capabilities, "problems") else True\n'
     '\n'
     '\n'
     '# ---------------------------------------------------------------------------------------------- MCP framing\n')
print("fixes applied")
