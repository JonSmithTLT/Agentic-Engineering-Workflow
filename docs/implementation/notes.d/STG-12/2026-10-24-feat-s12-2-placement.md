**S12-2, pull request 4 of 10 (2026-10-24): place the writes the writer map lost, and hold every cap of the reading.**
The writer map ([`docs/reference/writers.md`](../../../reference/writers.md)) left 43 write sites as `unresolved`
records, which the trace takes one by one. This pull request places the ones the reading can place, records the ones that
are followed to a place outside `.aew`, and says why each of the rest stays: 43 become 22. It also applies the designer's rule for
caps to the whole generator (below).

- **Why these rules, and not point fixes.** The 43 had a few causes in common, so each rule closes a cause:
  - *Destructuring and returns.* `a, b = x, y` binds each target to its element, and `a, b = f(...)` binds target `i` to
    the `i`-th element of what `f` returns (read in `f`, with the call's arguments bound); this includes `self`
    attributes. A key of a dict literal is read whether the dict is named, a module constant (a computed key is each
    value) or returned by a call. A loop over literal rows takes the element of each row for each target. Closes the
    `session.write` sites the trace cares most about (`work create`, plan proposals, history records) and the history
    prewrite.
  - *A value on the command line.* `args.run_dir`, where `args = parser.parse_args()`, is what the start of that process
    spells after `--run-dir` in the argument list it builds (a list holding the flag and the module's dotted name; the
    supervisor's start is the one). The run directory is `.aew/local/harness/runs/<run>`, so the supervisor's, the run
    log's and the containment layout's writes are placed there, not "outside". A flag no AEW start passes
    (`--state-dir` of the STG-02 server) stays unresolved, with that reason.
  - *Lists and callbacks.* A loop over a list passed as an argument takes the elements the caller built (through a
    conditional iterable, a slice, `sorted`, a glob and `append`); the keys of the mapping a callback returns are read
    through the constructor that stores it (the store's renderer: `state/CURRENT.md`, `state/HANDOFF.md`). A callback
    is followed as a value only; the reach still follows calls only.
  - *The store's apply step is the write mechanism.* `ControlStore._apply` writes what a transaction staged, from the redo
    record; the paths are the staging sites' (`session.write`), which are the writers and records. Like `aew.util` and
    the store's `write_file` it writes for others, so it is not a writer.
- **A shape addition: `writers:outside:<module>:<symbol>:<primitive>`.** A write followed to a place outside `.aew` (a temporary
  directory, the task workspaces' directory, the repository's working tree, the console, the null device, an in-memory
  database, an absolute path) was listed on the page only. Each of the 35 is now a record: fact `{primitive, mechanism,
  root}`, coverage `lower-bound` with nothing unresolved. A function that also writes under `.aew` has its path records
  as well. A root names a place, never a path of the machine (the family's record rules refuse a separator, a drive or a
  home, beside the generator's text rule over `index.json`). The design side's reader takes every record with no
  problem.
- **Caps (the designer's rule, workspace e350605): the class, not the instance.** Every cap or cut of the generator is
  listed in `writers_flow.caps()` and `writers_roles.caps()`, each with its source, what it bounds and what the reading
  does past it, and the writers page prints that list. Past a cap there is a marked item or a failed check, never
  silence, with a planted case per kind: the value, call-site and depth caps make the value unknown and the site an
  unresolved write; the receiver-typing depth leaves the writer reached only through it with the no-chain item; the
  parser reader's two caps leave the registration undecided (run by every role). The sweep found two silences: the keys
  of a mapping passed from more than `CALLERS` call sites read the first 24 and dropped the rest, and the functions a
  callback parameter can be did the same and, at the depth limit, returned nothing. Both are marked now. Mechanical
  guards: a sweep test finds every integer named like a cap and every slice cut at a number or a constant in the
  generator, and fails on one that is neither listed nor excused as a display truncation (the one excuse: an expression
  quoted in a reason, cut with `...`); and a tree test doubles every cap and holds every record and the page unchanged,
  so no record of the tree is lost to a cap.
- **Two caps were binding, and are measured now.** `VALUES` was 16: placing the store's rendered views made a set of
  17, and five directory records (`knowledge`, `policy`, `roles`, `state/log`, `state/txn`) were replaced by one
  unresolved write with a generic reason. It is 40, held to twice the largest set the tree makes (a tree test; the page
  prints the size). `DEPTH` was 6: the run directory a supervisor is handed needs 7 calls or parameters, and at 6 the
  reading gave the coarser `runs/{}` records and no sign (doubling the cap added `R-{}-{}/git/index` and
  `.../git/objects`). It is 14, and a test halves it. The packs cut on `main` are unaffected: with only the cap rule
  applied to `b879f6bd`, `index.json` and `gaps.md` render byte-identical; and doubling or multiplying by ten every cap
  of `7bfba053` and of `b879f6bd` leaves the writers records unchanged (the first pack predates the writers family).
- **What stays unresolved (22), and why.**
  - *Named by the environment or by whoever starts the process:* `faults.pause` (`AEW_PAUSE`), `profile.cli_finish`
    (an environment variable), the STG-02 server's state directory and driver-config path (3).
  - *Chosen at run time:* the harness adapters' run directory (the adapter class comes from a registry the operator may
    extend by environment): 4 in the adapter and client, `runlog.write_live`, `usage_live.Meter._persist`.
  - *Through an object this reading does not type:* `Supervisor.start`'s scratch directory is an attribute of the
    contract that `self.engine.harness_contract(...)` returns (1); the worktrees' `remove` reads workspace entries of the
    control state (1).
  - *Output of another program:* the two worktree allocations write a path that `git` printed (2).
  - *Not placed:* `ControlStore._remove_temp_files` (its root-level temporary files are directly under `.aew`, which has
    no slot in the declared set: a decision, not a key invented here), `Migration.discard_unreachable` (paths listed
    from a scan), and the containment probe's markers (5; its layout's directory lists are values of a dataclass
    built by a function of the layout module).
- **Carried from the review of the roles cut (#258) and the designer's rulings.** `LOCAL` is held to a line of
  `AEW_GITIGNORE` by a tree test (N1); a root that is not the CLI's is not given an unread command's handlers, planted
  (N2); a function that writes both the store and `local/` is a store writer only, planted (N3); the page says the
  counts of writer functions reached are lower bounds, not every count (N5). The worker-run item is on each path record
  that any CLI command's handler reaches, whatever that command's own role (addendum 5, N4): 105 records, of which 85
  before the placement rules; the records with no chain and those only a supervisor reaches carry none. The "Not
  checked" line says a write whose destination is not placed carries no role reach and is not checked. These commits
  are identical to those of the layout pull request, so whichever merges second merges clean.
- **What a change to writing code does** is as before: run `python tools/reference.py render` and commit
  `docs/reference/`. A change that makes a cap bind fails the doubling or halving test, and is a decision.
- **Amended in pull request 6 (the review of this pull request, F1 to F8).** The page and the docstring now say that the
  store's apply step is not a writer because the staging sites are, except for the events sidecar `_commit_unprofiled`
  stages itself (F1). `DEPTH` is 20, not 14: a depth cut under a join read as a computed segment, which hid that the tree
  needs 10; it is measured now and held to twice that, with `MRO_DEPTH`, `FSTRING_LIMIT` and `ASSIGNMENT_DEPTH`, three
  limits the sweep did not see, now caps (F2). A reason that a cap makes names the cap, its number and its source, and
  takes precedence over a later "computed" (addendum 6 of the hand-off). "Outside `.aew`" is "followed to a place
  outside it" (F5), and the record count above is not restated (F6).
