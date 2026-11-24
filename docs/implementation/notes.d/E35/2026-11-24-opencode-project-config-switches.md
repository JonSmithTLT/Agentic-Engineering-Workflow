**Both of OpenCode's project-config switches (2026-11-24).** OpenCode 2.2.6 reads two names for its project-config
switch, `OPENCODE_CONFIG_PROJECT_DISABLE` first and then `OPENCODE_DISABLE_PROJECT_CONFIG`. AEW sets both of OpenCode's
project-config switches, and `OPENCODE_DISABLE_AUTOUPDATE`, to `1`, last in every OpenCode environment it builds: a
worker's server (`adapter.server_env`), the Lead's TUI (`lead.tui_env`), the Lead's contained and not-contained starts,
and the qualification and Lead-probe tools. The names have one owner, `capabilities.FIXED_SWITCHES`, which
`aew harness config` derives its report from. A provider variable (`provider_env`, `--provider-env`) named `OPENCODE_*`
is now refused with the code `harness_variable` (a built-in provider's key, such as `OPENCODE_API_KEY`, apart), and the
configuration read's change note lists the new code. The live probe
(`tests/live/test_opencode_project_config_live.py`) removes both switches for its control and measures the read order
in the server's own environment: with only `OPENCODE_DISABLE_PROJECT_CONFIG=1`, nothing loads; with
`OPENCODE_CONFIG_PROJECT_DISABLE=0` beside it, the project loads as in the control, so the first name is the one read
and both must be set. A keep-list case checks that the first name in the environment AEW builds from, at `0`, `false`
or empty, never reaches the server. The qualification tool's direct OpenCode call (`worker_plan`) and the Lead's
version check get the same switches.

Follow-on (web developer): the Settings page's known problem values (`web/`) gain `harness_variable`, which the
configuration read can now report.
