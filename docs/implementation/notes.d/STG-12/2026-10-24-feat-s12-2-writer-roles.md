**S12-2, pull request 3 of 9 (2026-10-24): the writers' reach cut per role of the CLI.**
The writer map ([`docs/reference/writers.md`](../../../reference/writers.md)) said, for every writer the CLI reaches,
that all four of the CLI's roles reach it. Now each writer's `entry_points` is cut by the command that runs it.

- **Why a cut.** `aew.cli.main:_main` declares four roles (`aew`, `aew dashboard serve`, `aew lead mcp`, `aew (worker
  run)`), but a process runs one command, and the command decides the role (`process_kind.cli_entry_point`, the owner,
  asked at generation time and not restated). The CLI hands a command to its handler through `args.handler`, which no
  call names, so the call graph alone cannot say which role runs which handler.
- **How it reads.** Each `parser.set_defaults(handler=...)` is the handler of the command path its parser expression
  spells: `argparse.ArgumentParser(...)` is the empty path, `p.add_subparsers(...)` the path of `p`, `p.add_parser("w")`
  that path and `w`; a parameter is the argument of every static call of its function, a name is the assignment that
  dominates the use (the register functions assign `p` and `q` again and again), a loop over literal rows gives one
  command per row. A handler written as a lambda is a function of its own (its calls are not the registering
  function's, else the whole engine would be on the path every command shares). Of the 105 registrations in the tree,
  all 105 are read (109 command paths), and `tests/integration/test_reference_writers.py` holds the cut equal, command
  for command, to the map of the parser `build_parser` really builds.
- **What a record says now.** A handler is reached by the role of its command only; what `_main` calls itself (the
  parser's construction, the path every command shares) by all four. A writer the general handlers reach and the
  worker role is not given carries one item, anchored at `aew.process_kind:require_writer`, saying the role the
  environment selects is no command's, that the call graph gives it nothing (so its absence from `entry_points` is no
  evidence), and that a write a non-writer may not make is refused by that gate (tested at run time by a named test,
  not proved here). A handler whose command cannot be read is
  not guessed: it counts as run by every role, and the writers behind it name the function that registers it (none
  today). The earlier item anchored at `_main` is gone.
- **The check.** A store write (a store-transaction writer, or a direct writer outside `local/`) reached from an entry
  point of kind `non_writer` is listed on the page and held empty by a tree test; writers under `local/` that a
  non-writer reaches are listed too, as permitted (`local/` is rebuildable data kept out of git; the check is keyed on
  the path prefix and the mechanism).
- **Limits, stated on the page.** A handler that calls its engine method by a name held in a variable
  (`getattr(engine, name)(...)`: the `integrate` commands) is not followed. A sibling path named by something that is
  neither fixed nor made by the process is an unresolved write (it used to fold into its path).
- **Carried from the review of the writer map (nits that ride this pull request).** A flags or mode name that the
  function only augments is unreadable, not decided by its augmentations (both readers); the `.suffix +` and f-string
  spellings of a sibling named from the path's own name, and a sibling named by a parameter, are no longer folded into
  their path's record; the figure of path records carrying the role item was 85, not 86.
- **What a change to a CLI command does.** Adding or moving a `set_defaults(handler=...)` changes the page's counts:
  run `python tools/reference.py render` and commit `docs/reference/`.
