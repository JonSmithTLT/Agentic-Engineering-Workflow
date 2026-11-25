**The project's `.env` files are now masked by containment, 2026-11-25.** Every layout `for_run` makes shows the
project, so each one masks the `.env` files at the project's top level (`*.env` and `*.env.*`, but `.env.example`) as
a `containment.hide` entry is masked: in place in the Lead's tree, named on its launch line, and left out of the
project in a worker's view. The OpenCode read rules derive their names from containment's, and the Lead's system text
and ADR-0009 (amendment of 2026-11-25) now say that containment hides them, as the system text states. A nested `.env`
file is named in `containment.hide`.
