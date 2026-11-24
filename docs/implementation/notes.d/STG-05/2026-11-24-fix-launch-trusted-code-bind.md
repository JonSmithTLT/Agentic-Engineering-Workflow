**AEW's own code lies outside every writable bind (2026-11-24; the relay handoff's RLY-05).** Every supervisor and
provider relay is a host process that imports AEW afresh, so `layout.for_run` now refuses a layout whose writable bind
reaches AEW's own code (`CONTAINMENT_UNAVAILABLE`, reason `trusted_code_writable`, or `trusted_code_symlink` where the
bind holds a symbolic link on the code's spelling). The code is read from the filesystem at each launch
(`layout.trusted_code`): the `aew` package, its parent (the import path `procs.engine_imports` gives every process that
receives a credential), every symbolic link in the package's tree (an editable install's tree of links), and every
directory on the launching process's import path but the script's own (which `-P` removes from every process the engine
starts). Each is checked as spelled and where it leads, by the store's rule (CB-07): under a writable bind it is safe
only when the first directory below the bind on its path is re-bound read-only after it, which is what keeps a virtual
environment in the project safe (its prefix is re-bound). Under `required` the launch is refused; under `allow_weaker`
it runs labelled weaker with the refusal as its `weaker_because`, and enters the register of weaker contexts like every
other weaker launch (E112's pattern, through `containment.establish`). The package and its parent are on the
self-test's protected list. `aew doctor` gains a `trusted-code` line in a project on Linux: PASS, or FAIL under
`required` (WARN under `allow_weaker`) where AEW's code lies in the project or a policy writable root. ADR-0009,
amendment 2026-11-24.
