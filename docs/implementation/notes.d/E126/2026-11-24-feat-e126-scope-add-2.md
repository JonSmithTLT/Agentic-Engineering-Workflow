**Second slice built (branch `feat/e126-scope-add-2`): seeing the add, and the three follow-ons of PR #540's quick
check.**
- **Status and the Lead's result list the added paths, never a count** (`WIS-02.f`): `aew status` gives each live
  Ticket's `scope_added` and a `scope added on the record:` line under it in the work graph (so in `CURRENT.md` and a
  handoff too), and the projection's `unit.scope_added` reaches E121's text as `scope added:` lines. Each entry names
  its correction, and the one that signed it off (`scope_ops.added_listing`).
- **The projection offers the add when the violation exists:** an `ADD_SCOPE` decision on `resolve` for each path the
  gate context reports outside the scope that is test code by name or directory, with the add's own query for its
  availability and no default. One the add would refuse, a sign-off stop included, is BLOCKED with the refusal among
  the blockers.
- **The guide and the review card:** the guide's scope rule names the exception, and its every-class list and the
  `code_reviewer` card (version 3) carry the same three lines on test work, for a Ticket's original scope as well
  (`guide.TEST_WORK`). The guide grew 429 B inside the Lead context pool's reserved room, with no allocation of its
  own; with PR #540's 57 B and earlier growth, 524 B of the 5,000 B of estimates are now taken.
- **m-a:** an add compares a conflict with another live Ticket by its facts (`reasons`, `touched_in_scope`,
  `outside_own_scope`, `scope_pairs`), not by its hold message, which names the whole scope; only a conflict that gains
  a fact refuses it (`scope_ops.widening_meets`).
- **m-b:** an implementer is told with `harness send` only while its run is STARTING or RUNNING
  (`runlog.observed_status`); an ended, lost or unreadable run is named the re-dispatch commands.
- **m-c:** a reviewer's pack shows the lines added and removed in the declared scope beside those in the added paths,
  from `git diff --numstat` against the base commit (`scope_ops.lines_changed`).

**Left:** nothing of the slice the designer's decisions of 2026-11-03, §2, describe, beyond what the design itself
defers (the operator's publish decision showing the paths, when V-01 builds it; any other kind of path; narrowing).
