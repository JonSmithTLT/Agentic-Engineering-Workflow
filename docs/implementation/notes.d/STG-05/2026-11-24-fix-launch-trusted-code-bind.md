**AEW's own code lies outside every writable bind (2026-11-24; the relay handoff's RLY-05).** Every supervisor and
provider relay is a host process that imports AEW afresh, so `layout.for_run` refuses a layout whose writable bind
reaches AEW's own code (`CONTAINMENT_UNAVAILABLE`, reason `trusted_code_writable`, or `trusted_code_symlink` where the
bind holds a symbolic link on the code's spelling that is not below a read-only re-bind).

- **What is counted** (`layout.trusted_code`, read from the filesystem at each launch): the `aew` package; its parent
  (the import path `procs.engine_imports` gives every process that receives a credential); every symbolic link in the
  package's tree; and every directory on the launching process's import path, named by where it comes from. The first
  entry (the script's directory, or the working directory under `python -m`) counts unless `-P` removed it, because
  the contained Lead's relays are served in the launching process. An installed `aew` command's directory needs no
  exception: it lies outside every writable bind or under the re-bound interpreter prefix.
- **The rule** is the store's (CB-07), checked as spelled and where it leads: under a writable bind a piece is safe
  only when the first directory below the bind on its path is re-bound read-only after it, as a project's virtual
  environment is (its prefix is re-bound), and a link is safe only strictly below that directory (its `lib64` link).
  Both spellings are always checked, so a held link whose target lies elsewhere under the bind is refused too.
- **Outcome:** under `required` the launch is refused, with the remedy for that kind of code
  (`layout.trusted_code_remedy`); under `allow_weaker` it runs labelled weaker and enters the register of weaker
  contexts (E112's pattern, through `containment.establish`). The package and its parent are on the self-test's
  protected list. `aew doctor` has a `trusted-code` line in a project on Linux, from the same binds
  (`layout.lead_trusted_code_exposed`).
- **Known limits.** Not checked; keep these outside writable binds: import paths reached only through meta-path finders
  (editable installs of dependencies), `.pth` directories created after the launch, adapter files from
  `AEW_HARNESS_ADAPTERS`, a writable bind nested inside an import-path directory other than the interpreter's prefix,
  third-party modules linked from elsewhere, and paths on case-insensitive filesystems (compared by their spelling).

ADR-0009, amendment 2026-11-24.
