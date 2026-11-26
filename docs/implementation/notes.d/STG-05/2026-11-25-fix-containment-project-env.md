**The project's `.env` files are now masked by containment, 2026-11-25.** Every layout `for_run` makes shows the
project, so each one masks the project's `.env` files present at the launch, at any depth (`*.env` and `*.env.*`, but
`.env.example`), in place by the empty read-only file; the Lead's launch line names them. The OpenCode read rules
derive their names from containment's, and the Lead's system text and ADR-0009 (amendment of 2026-11-25, with its
limits) now say that containment hides them, as the system text states.
