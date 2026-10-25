**S12-2, pull request 6 of 10 (2026-10-24): the concurrency family (DOC-03), and the nits of the review of the layout pull
request (#261).**
One family joins the generated reference ([`docs/reference/`](../../../reference/README.md)): 14 records (500 in all),
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
    in its module docstring (parsed from it, not restated), and six this family declares because the code says so (the
    compactor's build, re-read and prune; the wake mark's writer, reader and waiter). Each carries the first sentence of
    its own docstring (**observes**), the sentences of its own or its module's docstring that say it needs no lock
    (**says**, with a design citation elided and a sentence that still names one left out: the reference holds no such
    id), whether its static call closure reaches a function that takes a lock (all ten do not), and the entry points that
    reach it. A tree test runs each member a test can run with the control lock held by another store of the process and
    checks that a locking read times out meanwhile.
  - Found twice: the `FileLock` constructions and the calls of the opener by `ast` (by import source) and by tokens (by
    spelling), held equal per module. What neither sees (an in-process `threading` lock, a file created with `O_EXCL`,
    another lock class, an opener called through `getattr`, a `FileLock` bound to another name) is listed on the page,
    one probe each.
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
- **What a change does.** Taking a new lock, or calling the store's lock from another function, moves
  `concurrency.md`; a second opener of the control lock fails the generator. Run `python tools/reference.py render` and
  commit `docs/reference/`.
