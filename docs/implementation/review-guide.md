# Review guide: how an independent review is done

**Status:** governing from A0's merge (the AGENTS.md content review; operator decision of 2026-10-24). It holds the
review procedure that `AGENTS.md` §1 carried until then. `AGENTS.md` keeps the rules and points here. The operator
owns this guide: a change to it is merged by the operator (`AGENTS.md` rule 5). Every review brief loads it.

## 1. The kinds of review

- **A full review** (a "full round") covers the whole diff against `main`, with the reviewer's own choice of tests. It
  is the default. Rounds are counted in full reviews only.
- **A delta review** follows a CLEAR whose only open points are nits (§7).
- **A targeted review** follows the last full round of the stop rule (§8).
- **A re-render check** (§7) is mechanical, not a review: it carries the last verdict to a head that only merges
  `main` and re-renders.
- Delta and targeted reviews have the same shape (§7). Everything in this guide applies to every kind unless a section
  says otherwise.

## 2. The finding format

Severity (blocker, major, minor or nit); `file:line`; the guarantee broken; a concrete scenario; the fix; reproduced or
not (with the command); confidence. No findings about taste in code style, and no redesign unless a guarantee cannot be
met otherwise. Add a "what looks sound" list.

## 3. Labels: what the review's own label decides

Each finding carries a severity, and a minor carries its fails label (§8). Every finding also names its precondition
class (§10). The review labels each, and its label decides. The author cannot relabel a point.

- **A nit** is a point whose fix changes no behaviour and breaks no guarantee: wording in docs, a comment, a docstring,
  a test name, a stale reference. Changing text that tests or operators rely on, such as an error message or a reason
  code, is behaviour and never a nit. An unlabelled point is not a nit. Where a rule of this guide sets a severity, as
  §9 does, that rule decides.

## 4. A repeatable defect class (designer ruling, 2026-10-12, M1)

Its finding also states the governing invariant, the affected scope, a reproducible way to enumerate the class where
that is feasible, and the known limits of its coverage. A claim that the class is fully fixed needs evidence from a
reproducible check at the relevant revision. A semantic class that no mechanism enumerates reliably gets documented
reasoning for its coverage instead, and is never claimed to be mechanically complete.

## 5. One pass raises everything

A review lists every finding and nit it would raise at that commit. Nothing is held back as "optional" for a later
round. A later review still raises a real defect an earlier pass missed.

## 6. CI at the exact head (designer ruling, 2026-10-12, C1)

A CLEAR was recorded at heads whose CI was red, and nobody read it. Every review (the comment that carries its verdict
line), every pull-request description, and every author comment that asks for review or lists fixes gives the CI
observation for its exact head commit in its body: which checks and runs, their completion state, and how and when it
was observed. An author who hands back fixes posts such a comment; a push alone is not a hand-back. A review CLEAR is
not CI qualification. A failing required check is named. A failure also seen on the base may inform its attribution
but does not automatically waive the requirement. Unknown attribution remains UNKNOWN.

## 7. Nits after a CLEAR get one short delta review

The operator, 2026-10-10; the product rule of the Cross-Feature Integration Design v0.5, §15. When the verdict is
`Review: CLEAR` and its only open points are nits:
- The author fixes them in ordinary commits on top of the reviewed commit, changing only what the nits name, and posts
  a comment that cites the CLEAR and lists each nit with how it was fixed.
- The reviewer, or a new independent one, does one short delta review. It covers the whole diff since the CLEAR, runs
  only the tests that touch it (CI is the matrix), and ends with a verdict at the new head as usual.
- If the delta review finds a blocker, major or minor finding, or any change in behaviour beyond the named fixes, its
  verdict is `Review: FINDINGS`, or it first widens into a full review and gives that review's verdict. Otherwise its
  CLEAR closes the nits.
- **A point the delta review raises.** A nit whose fix changes only the wording of a document, a comment or a
  docstring, and nothing that runs or that tests or operators read (a doctest, help text, an error message or a reason
  code), is fixed and checked by one more short delta check of that fix alone. Any other point it raises, or a nit
  whose fix changes anything else, is fixed and reviewed in a full review. If that second check raises anything, the
  next review is a full one.
- **A merge of `main` or a rebase** takes the work off this path: the next review is a full one, unless the merge is
  a re-render.
- **A re-render keeps the verdict** (operator, 2026-10-24). With R the reviewed head, H the new head, M the newest
  commit of `main` that H contains, and B the newest commit of `main` that R contains, H is a re-render of R when all of
  these hold:
  - R is an ancestor of H. A rebase is never a re-render.
  - Outside the generated files, the paths that differ between M and H are exactly those that differ between B and R;
    each is byte-identical at H and at R; and none of them differs between B and M. So `main` changed no file the
    pull request changes, and no conflict outside the generated files was resolved, by hand or by taking a side.
  - The generated files are what `python tools/reference.py render` writes (all of `docs/reference/`) and what
    `python tools/register.py render` writes (`future-work.md` and `decisions-due.md`), and both generators' `check`
    pass at H. `register.py render` also rewrites the register's YAML, which is a source: a render that changes it,
    or a YAML both sides changed, is not a re-render. The list is closed; another generator joins it only by a change
    to this guide.

  R's verdict and its open points then hold at H, and a delta or targeted review in progress continues. The check
  needs no judgement, so the reviewer or the Lead runs it, never the pull request's author. Its comment names R, H and
  M, gives the commands and their output and the CI observation at H (§6), and ends with R's verdict line at H. CI at
  H is still required (`AGENTS.md` §4): it is the only check of how `main`'s changes and the pull request's combine.
- A nit the author disputes goes through `AGENTS.md` §2 before this path applies. A blocker, major or minor finding is
  never a nit.

## 8. The stop rule (operator, 2026-10-21; for pull requests, 2026-10-24)

A review round with no blocker or major, where every minor fails closed, is the last full round.
- **Closed or open.** A minor fails closed when its worst case refuses, stops or raises a false alarm. It fails open
  when its worst case lets through, or reports as passing, something a guarantee forbids. The review labels each minor
  with its worst case, and its label decides. A minor with no label, or whose worst case fits neither description, is
  open. "Stops" means stops the guarded action, not the guard.
- **The last full round's verdict is `Review: FINDINGS`**: its closed minors are open points. The targeted review gives
  the next verdict.
- **The answer is the smallest that meets the finding,** for the findings of the last full round: narrowing a claim (a
  claim in the pull request or its code, never an adopted text except as §10 allows) or stating a limit where that
  suffices (M1's known limits), otherwise the smallest code change, adding no check, option, module, dependency or
  call to a host tool that the finding does not name.
- **One short targeted review** then checks the whole diff since the last full round, in the shape of §7's delta
  review. If it raises a blocker, a major or a minor that fails open, a full round reopens. A minor that fails closed,
  or a nit, is fixed and checked by one more short check of that fix alone; if that check raises anything, the next
  review is a full one. A merge of `main` that is not a re-render (§7), or a rebase, ends it: the next review is a full
  one.

## 9. Proportion in a test-only pull request (operator, 2026-10-24; M1 stands)

A pull request that changes only tests, test helpers and CI test tooling, and no product code. Everything else in this
guide applies unchanged.
- **The fix is proven, not assumed** (for a pull request that fixes a test). The review undoes the fix on a copy, and
  each test the pull request names as fixed must fail; a pull request that names none names them first. For an
  intermittent failure, the pull request names how it is reproduced (a loop count, an injected delay or a pinned
  seed), and the undone fix fails under it. The reviewer also runs the changed tests, with the fix in place, in one
  session with their neighbours (the modules that share the changed helper, fixture or directory, or a resource it
  uses, such as a port, an environment variable or a temporary path), and they pass.
- **A gap in the pull request's enumeration of its defect class is a finding only when the reviewer shows a live
  instance at that commit:** a site the stated invariant covers that violates it at that commit, shown by the command
  that finds it. A gap with no live instance (a spelling, binding or helper that the detectors the pull request adds or
  relies on cannot see) is a nit, whatever else the reviewer would call it. Its fix names the gap among the limits
  stated in the pull request's description and the detector's docstring, as M1 requires, and changes no behaviour.
  When the review's other points are nits too, the verdict is CLEAR, and the fix takes the delta review of §7.
- **Not covered:** a pull request that deletes, skips, marks as expected to fail or loosens a test or a gate (a weaker
  or removed assertion; a changed expected value or pinned fixture; a wider tolerance or timeout; a retry or rerun; a
  lowered baseline or threshold, such as `tests/coverage-baseline.json` or `TOLERANCE` in
  `tools/ci/coverage_gate.py`), adds a platform skip, or changes which tests CI runs or requires. It keeps the full
  review, because it can hide a failure.

## 10. Precondition classes, and what is fixed after the PR (operator, 2026-10-24)

The designer's ruling on the operator's decision of 2026-10-24 (proportionate review dispositions). These are the
cases where a finding is not fixed in its pull request (`AGENTS.md` §2). The precondition classes and the sort after
the third full round apply from each pull request's next full round after 2026-10-24.
- **Every finding names its precondition class.**
  - **Agent-reachable:** a contained agent can use it on its own, or can create its precondition through anything AEW
    gives it.
  - **AEW-created:** AEW's own code, setup or install writes the precondition, or an AEW crash or interruption leaves
    it. Cuts, crash leftovers and AEW's own routes are this class, so they stay in scope.
  - **Host-only:** the precondition is host configuration that AEW neither creates nor can be driven to create: root's
    or the operator's own route, NAT rule, group, service or link. Or it is code other than AEW's running as the
    operator or as root, which the threat model excludes, such as malware or a compromised host. "Root touched it" is
    not the test.
- **A host-only finding** becomes a stated residual plus a register row by default, whatever its severity, and not a
  fix round. The designer can pull one back to "fix now", saying why.
- **After the third full round on a pull request**, the designer sorts each remaining minor that fails open:
  - **fix now**, in this pull request, if it is a direct route a contained agent can use on its own to a credential,
    an approval, an owner fact, or an escape;
  - **otherwise, a stated limit plus a register row.** A gap the agent can use only with a precondition it cannot create
    itself leans this way.
  - A blocker or a major is not sorted: it stays "fix now" unless it is host-only. The stop rule (§8) still applies to
    every round.
- **A residual has two texts.** The private one holds the mechanism and its evidence, outside this repository, until it
  is fixed. The public one, in the run's label where the run carries one, the pull request's Known limits and the stage
  note, says what is not detected, its precondition class and its worst case. It does not describe the mechanism or
  call it "fails open". The register row is public too: it names the deferred outcome, not the mechanism.
- **Adopted text.** Where a residual or a sort narrows an adopted guarantee, the decision is the authority for that
  narrowing. The stage note records it, and the contract's next revision names it beside its rule. Any other narrowing
  of adopted text still goes to the operator.
- **Nits ride the next pull request of S12-2's series** (operator, 2026-10-24, for the STG-12 S12-2 pull requests 2 to
  8). A CLEAR in that series whose only open points are nits merges once `assurance` is green, and its nits are fixed in
  the next pull request of the series, listed in its description, and checked by its review. The last pull request of
  the series fixes its own nits. Only nits ride; a minor is fixed in its own pull request.
