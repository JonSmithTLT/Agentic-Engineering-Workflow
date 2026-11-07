# Reviewing tool and configuration changes

Use when a version, preview flag, selector, root, include/exclude rule or documented invocation can change enforcement.

1. Pin base/head tool versions, invocation, working directory, environment and representative target paths. Read that version's option semantics; a small flag can affect several rule families, fixes, formatting or output schemas. Do not infer effective scope from the config diff alone.
2. Obtain resolved settings for actual files under each relevant configuration root and compare base/head. Account for inherited/nested config, CLI overrides, path discovery and defaults. Keep raw settings plus a focused semantic diff; an output-format change can break consumers even when rules are unchanged.
3. Run known-valid, known-invalid and missing-coverage controls inside the same discovery roots as production targets, in isolated copies. A scratch file outside that root may load defaults and falsely pass. Challenge each accepting exception, selector or exclusion. Confirm the tool actually analyzed the fixtures.
4. Compare findings and fixes across representative inputs. For Ruff, preview can affect more than new rules, and preview enablement is distinct from rule selection. Use the pinned version's resolved settings (for example `ruff check path/to/file.py --show-settings`) and actual findings; never invent a fixed universal expansion count.
5. After reverting, compare resolved settings and behavior again. A reverted file does not prove the version, environment or CLI override reverted. Preserve the original workspace; never undo a control by resetting another worker's changes.

Review bundled CI YAML and documented commands for quoting, cwd, environment, discovery and exit-status semantics. Syntactically valid YAML is not proof the invoked command enforces the intended contract. Report unreachable inputs, missing versions and unavailable execution as limits.
