# Guides and reference material

Read for instructions someone must follow or facts someone must look up.

**Guides:** organize around the task and expected result. Put prerequisites before the action that needs them: environment/version, starting state and permissions. Use the actual command or control label. Specify where a command runs, which placeholders must be replaced, what success looks like and what to do for the relevant failure. Do not include every possible failure or a tour of internals.

Verify commands exist in the supported version and that arguments mean what the prose says. Follow the guide literally in a clean permitted environment when possible. Writing a deletion, deployment or paid-service example does not authorize executing it. Inspect semantics and use safe fixtures/dry-run modes only when their behavior is known; mark remaining execution limits. Do not present an unrun command as tested. Preserve correct quoting, paths and output bytes through the publishing tool.

**Reference:** identify the authoritative API/schema/registry or contract. Generate repetitive fields/value lists from it when feasible. Otherwise link to it or keep a focused comparison check that detects missing and extra values. Do not execute unsafe imports just to generate a list. Describe required/optional fields, null/absent distinctions, defaults, units and failure behavior where relevant. Examples illustrate the contract; they do not silently define a stricter one.

Keep facts at one maintained owner rather than creating parallel manual lists. Revalidate locators against the revision a reader uses; a stable symbol/section plus revision may survive edits better than a line number alone. Current instructions should describe current behavior. Put history in release notes/version control unless migration or compatibility requires it here.

For a contract/change note, identify downstream shape and behavior differences first, including additions, removals and changed meaning. Rehearse an available consumer's adoption in isolation where authorized. A proposed migration is not a successfully exercised migration.
