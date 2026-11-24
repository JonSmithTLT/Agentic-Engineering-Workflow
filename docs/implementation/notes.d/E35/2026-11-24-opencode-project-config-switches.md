**Both of OpenCode's project-config switches (2026-11-24).** OpenCode 2.2.6 reads two names for its project-config
switch, `OPENCODE_CONFIG_PROJECT_DISABLE` first and then `OPENCODE_DISABLE_PROJECT_CONFIG`. AEW sets both of OpenCode's
project-config switches, and `OPENCODE_DISABLE_AUTOUPDATE`, to `1`, last in every OpenCode environment it builds: a
worker's server (`adapter.server_env`), the Lead's TUI (`lead.tui_env`), the Lead's contained and not-contained starts,
and the qualification and Lead-probe tools. The names have one owner, `capabilities.FIXED_SWITCHES`, which
`aew harness config` derives its report from. A provider variable (`provider_env`, `--provider-env`) named `OPENCODE_*`
is now refused with the code `harness_variable` (a built-in provider's key, such as `OPENCODE_API_KEY`, apart), and the
configuration read's change note lists the new code. Still open on this row: the E35 probe's case for the first name,
for the next commit of the pull request that carries the probe.
