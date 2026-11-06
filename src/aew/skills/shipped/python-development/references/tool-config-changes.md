# Implementing tooling/configuration changes

Use for linter, formatter, test runner, build tool or configuration changes.

Pin the supported tool version and compare effective settings before/after for real target files under each applicable root, including CLI and environment overrides. Read version-specific semantics for broad switches such as preview; a small edit can affect rules, fixes, formatting and output consumed by other tools.

Plant a valid case, a rule-breaking case and a missing/discovery case in an isolated copy inside the actual configuration root. Verify they were collected and that each exception or accepting branch rejects a near-miss. An arbitrary temporary directory may silently load defaults. For Ruff, inspect file-specific `--show-settings` with the pinned executable as well as the actual diagnostics; preview enablement does not itself select every preview rule.

After a revert, check resolved settings and controls again. Include shipped CI YAML and documented commands: quoting, cwd, environment, version pins, discovery and failure exit status are part of the change. Adding an enumerated member also requires finding guards that walk that domain, rather than guessing tests from their names. Preserve logs and report unavailable checks.
