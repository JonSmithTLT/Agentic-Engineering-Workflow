**S12-2, pull request 6 of 10 (2026-10-24): the concurrency family (DOC-03), and the follow-ons of the reviews of the layout
(#261) and placement (#264) pull requests.**
One family joins the generated reference ([`docs/reference/`](../../../reference/README.md)): 14 records (561 in all),
one of them complete by construction.

- **Concurrency** ([`concurrency.md`](../../../reference/concurrency.md)): 4 lock records and 10 records of the functions
  that work without the control lock.
  - A **lock** is a `FileLock` construction found by where its class was imported from, keyed by the `.aew`-relative path
    the value flow places it on (`local/control.lock`, `local/dashboard/endpoint.lock`, `local/maps/registry.lock`,
    `local/operator/endpoint.lock`). Each has its **opener** (the function that constructs it), its **takers** (the
    opener's callers when it returns the lock, each with the operation name it passes; else the opener), the entry points
    that reach each taker and their kinds, its timeout, and whether the opener calls `process_kind.require_writer` first
    (a non-writer is refused before the lock is opened). The control lock's opener is one function, the store's
    `control_lock`, so its record is complete by construction and a second opener is refused by the generator and by two
    tree tests; its takers (`ControlStore.session`, `read`, `create`, and the compactor's publish) are a lower bound.
  - A **lock-free member** is a function or class that works without the control lock: the four `aew.process_kind` names
    in its module docstring (parsed from it, not restated), and six this family declares: the compactor's build, re-read
    and prune, because its module docstring says they run without the lock (a sentence of it is quoted for a member only
    if it names that member's work), and the wake mark's writer, reader and waiter, because the wake signal is advisory
    (their docstrings say nothing of a lock, so the call graph's finding is the only support there). Each carries the
    first sentence of its own docstring (**observes**), the sentences of its own or its module's docstring that say it needs no lock
    (**says**, with a design citation elided and a sentence that still names one left out: the reference holds no such
    id), whether its static call closure reaches a function that takes a lock (all ten do not), and the entry points that
    reach it. A tree test runs each member a test can run with the control lock held by another store of the process and
    checks that a locking read times out meanwhile.
  - Found twice: the `FileLock` constructions and the calls of the opener by `ast` (by import source) and by tokens (by
    spelling), held equal per module. What neither sees (an in-process `threading` lock, a file created with `O_EXCL`,
    another lock class, an opener called through `getattr`, a `FileLock` bound to another name) is listed on the page,
    one probe each, with the live instances the tree has (the integration queue's checkout sync lock, the `threading`
    locks of the dashboard and the harness).
- **Carried from the review of the layout pull request (#261), N-1 to N-14.** N-1: the layout's flag is
  `masked_by_containment`, and the page, the docstring and a tree test (a run directory inside `.aew`) say that a run's
  own directories are bound back into the mask. N-2: the unresolved-writes pointer names the writers family and its key.
  N-3: a tree test that every function that writes the control file is one that validates the state it writes. N-4: the
  control-keys text names the oracle's check, `ticket_field_violations`, and not a rule number. N-5: this note series'
  heading ("5 of 10"). N-6 and N-12: the page and the docstring do not gloss `AEW_GITIGNORE` and state the rule for
  `named_by`. N-7: the two negative clauses of the worker-run item have planted cases. N-8: planted wrong cases for the
  read detectors (the copy's destination, the keyword forms, a bare call named like a method). N-9: directory walks and
  the other reads by a primitive that is not listed are on the list of what the layout cannot see. N-10: the two orderings
  of the control-key anchor and each flag of the layout. N-11: a tree test imports each constant `named_by` finds and
  each anchor the control-keys family spells. N-13: planted cases for the two near-equivalent survivors. N-14: a pointer
  in the roles note.
- **Carried from the review of the placement pull request (#264), F1 to F8, and the designer's addendum 6.** F1: the
  page, the docstring and a tree test say the store's apply step is not a writer because the staging sites are, except
  for the events sidecar the commit stages itself. F2: three limits the cap sweep did not see (`MRO_DEPTH`,
  `FSTRING_LIMIT`, `ASSIGNMENT_DEPTH`) are named and listed in `caps()` (the first two measured, the third chosen), `DEPTH`
  is measured too (see below), and the sweep now sees a number in a comparison or a parameter default, an annotated or lower-case
  constant, a slice from the end and an `islice`. F3: the tests that double every cap derive them from `caps()`. F4: a
  planted case, with a placed alternative beside the capped one, for each site a cap can stop. F5: "outside `.aew`" is
  "followed to a place outside it". F6: the placement note does not restate a record count. F7: the list and dict edits
  the reading does not follow are on the writers page's cannot-see list. F8: each alternative of the root rule is
  refused alone. Addendum 6: the reason of a value a cap stopped names the cap, its number and where the number comes
  from, takes precedence over a later "computed" in a join, a sum, an f-string and a sibling, and is stated beside it
  where a site is both. **No reason in the committed reference changes** (no cap binds in this tree), so the next pack's
  difference from this one is the concurrency records and the carried wording, not a cap.
- **Addendum 7: every cap takes one of two arms.** A cap gives a marked item or fails `check`, and never drops a record.
  `caps()` and the writers page name the arm of each. `MRO_DEPTH` (a list of classes) and `TYPING_DEPTH` (a call edge,
  which a dropped receiver typing reads as "not known") bound something with no item to mark, so when the reading would
  go past the cap the reader raises an error that names the cap, its number and its source, and `check` and `render`
  both fail (a planted case one level deeper for each shape, and this tree with the cap one below its figure). A
  receiver whose typing needs itself is a cycle and is unknown, not the cap's. The headroom tests stay as an early
  warning. Every other cap marks the item: `DEPTH`, `CALLERS`, `VALUES`, `FSTRING_LIMIT`, `ASSIGNMENT_DEPTH` and
  `writers_roles.DEPTH`.
- **The caps are measured over the whole render.** The figures the page prints and the tests hold each cap to (twice
  the figure) are the largest over every family that runs the evaluator, under one `measuring()` in `reference.py`, and
  not the writers family's alone: the layout's reads reach 16 deep and 30 values where the writers reach 10 and 17. So
  `DEPTH` is 32 and `VALUES` 60 (a raise that changes no record); `TYPING_DEPTH` is 24 against a figure of 11. This was
  review point C-1 of the concurrency pull request.
- **A finding the precedence made.** `DEPTH` was 14 and "held to twice what the tree needs" by a test that halved it.
  While a depth cut under a join read as a computed segment, halving it changed nothing the test could see; with the
  reason kept, the tree is seen to need more (the figure the page prints), and the cap follows it.
- **Carried from the review of the concurrency pull request (#267), C-1 to C-10.** C-1: the figures over the whole
  render (above). C-2: a depth cut in the dict reader is the cap's and no longer reads as a computed segment, and a test
  finds every `depth <= 0` guard by AST and holds each to a planted case. C-3 and C-4: the wake mark's three members are
  declared because the signal is advisory, and a sentence of the compactor's docstring is quoted only for the member
  whose work it names, without a trailing colon. C-5: a planted case for each cap site and boundary the review's mutants
  survived. C-6 and C-7: the code comment states no figure, and `ASSIGNMENT_DEPTH` is "chosen". C-8: "provably outside"
  is "followed to a place outside it" in the layout family and the older notes. C-9: the cannot-see list names the live
  instances. C-10: a module-level call is counted by both detectors and the section heading is held.
- **What a change does.** Taking a new lock, or calling the store's lock from another function, moves
  `concurrency.md`; a second opener of the control lock fails the generator. Run `python tools/reference.py render` and
  commit `docs/reference/`.
