**The probe (Now list item 6; harness ruling 11, W14), measured 2026-11-24 on OpenCode 2.2.6 (the pinned binary, its
`LEAD_PROBE_LINUX_X64_SHA256`) and 2.0.18, Linux x64, keyless and model-free:** `OPENCODE_DISABLE_PROJECT_CONFIG=1`,
on AEW's own server environment (`adapter.server_env`), excludes both layers on both versions. Nothing was loaded
despite the flag.
- **(a) The project's `.opencode/` directory, and every other project layer.** Planted: `opencode.json` at the root and
  in `.opencode/` (each with an agent and a command, the root one with a local MCP server whose command writes a
  sentinel), `.opencode/{agent,agents,command,commands}/*.md`, `.opencode/{plugin,plugins}/` modules that write a
  sentinel when imported, `.opencode/{tool,tools}/`, and skills under `.opencode/skill(s)/`, `.claude/skills/` and
  `.agents/skills/`. With the flag: no project layer in `GET /api/config`, no marker in `/api/agent`, `/api/command`,
  `/api/skill`, `/api/plugin` or `/api/mcp`, no sentinel (no plugin code ran, no MCP command ran). The control, the same
  procedure with the flag removed, shows every one of those loaded, and the plugin and MCP code run. A project tool
  module is not imported at start even in the control, so tools are planted but not asserted on.
- **(b) The remote `.well-known/opencode` layer.** Its sources are a list in the server's own database, under the run's
  private XDG data directory, which is new for each run. The control: `POST /api/experimental/integration/wellknown`
  with the server password adds a local origin, and the server fetches its manifest and lists it; without the password
  the route answers 401 and nothing is fetched. A project that names the same origin (the legacy credential file's
  `wellknown` entries at its root and in `.opencode/`, a `.well-known/opencode` file, config keys) causes no fetch and no
  source, with the flag or without it.
- **Why, from the bundle:** the flag is read once, where a server starts (`config.project`), and it empties the
  directory walk that finds `.opencode/`, `.claude/` and `.agents/` and the project's `opencode.json`. The TUI starts its
  server as a `serve --stdio` child with its environment extended, so the Lead's server reads the flag the same way.
- **Not measured here:** whether an agent can reach a run's server password (W3, ST-38), and the Lead's source store,
  which is not new for each session (the operator's own data directory, or a contained Lead's AEW state directory). The "nothing else loaded" conformance scenario on the model-visible
  request stays item 14.

Reproduce: `AEW_OPENCODE_BIN=<opencode binary> pytest --live tests/live/test_opencode_project_config_live.py -p no:xdist -q`
(`AEW_LIVE_RESULTS=<file>` records what each channel showed).
