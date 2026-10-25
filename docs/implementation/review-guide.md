# Review guide: how an independent review is done

**Status:** governing from A0's merge (the AGENTS.md content review; operator decision of 2026-10-24). It holds the
review procedure that `AGENTS.md` §1 carried until then. `AGENTS.md` keeps the rules and points here. The operator
owns this guide: a change to it is merged by the operator (`AGENTS.md` rule 5). Every review brief loads it.

## 1. The kinds of review

- **A full review** (a "full round") covers the whole diff against `main`, with the reviewer's own choice of tests. It
  is the default, and a pull request gets one (§8).
- **A quick check** follows a full review whose verdict is FINDINGS, or a merge of `main` that is not a re-render, or
  a rebase (§7, §8). It covers the whole diff since the full review, or after such a merge or a rebase, the whole diff
  against `main`.
- **A re-render check** (§7) is mechanical, not a review: it carries the last verdict to a head that only merges
  `main` and re-renders.
- A CLEAR whose open points are minors and nits takes no further review: they are fixed or followed on as §7 says.
  Everything in this guide applies to every kind unless a section says otherwise.

## 2. The finding format

Severity (blocker, major, minor or nit); `file:line`; the guarantee broken; a concrete scenario; the fix; reproduced or
not (with the command); confidence. No findings about taste in code style, and no redesign unless a guarantee cannot be
met otherwise. Add a "what looks sound" list.

## 3. Labels: what the review's own label decides

Each finding carries a severity. What counts as a security finding is in §10. The review labels each point, and its
label decides. The author cannot relabel a point.

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

## 7. Minors and nits after a CLEAR are fixed or followed on

The operator, 2026-10-25, in place of the delta review after nits of 2026-10-10: a minor or a nit never blocks a
merge (`AGENTS.md` §2), and none is dropped. A review whose open points are only minors and nits ends `Review: CLEAR`
and lists each one, with its label and its fix line, as a follow-on. Each is then handled in one of three ways:
- **In the same pass,** when the author is changing the pull request anyway (for a blocker or a major), and checked
  by the quick check that follows (§8).
- **Before merge, when trivial:** a fix that changes only the wording of a document, a comment or a docstring, and
  nothing that runs or that tests or operators read (a doctest, help text, an error message or a reason code), goes
  in on top of the CLEAR with no further review round, when it causes no real delay. The author's comment lists each
  with how it was fixed, and CI at the new head is green (`AGENTS.md` §4).
- **Otherwise as a tracked follow-on.** In a series, the next pull request fixes it, lists it in its description, and
  its review checks it; the last pull request of a series fixes its own or tracks them. Outside a series, a register
  note on the row the work belongs to, or a new row, tracks it until a pull request fixes it.

The rest of this section:
- **A merge of `main` or a rebase** after the CLEAR takes one quick check of the whole diff against `main` at the new
  head, unless the merge is a re-render.
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

  R's verdict and its open points then hold at H, and a quick check in progress continues. The check
  needs no judgement, so the reviewer or the Lead runs it, never the pull request's author. Its comment names R, H and
  M, gives the commands and their output and the CI observation at H (§6), and ends with R's verdict line at H. CI at
  H is still required (`AGENTS.md` §4): it is the only check of how `main`'s changes and the pull request's combine.
- A point the author disputes goes through `AGENTS.md` §2 before this path applies. A blocker or a major is never a
  minor or a nit.

## 8. One full round, then a quick check (operator decision, 2026-10-24, the security depth reset)

It replaces the repeated rounds of the stop rule of 2026-10-21. A pull request gets one full review.
- **Its blockers and majors are fixed** in the pull request, with its minors and nits in the same pass (`AGENTS.md`
  §2). A full review with an open blocker or major gives `Review: FINDINGS`. One whose open points are only minors and
  nits is CLEAR, and they are handled as §7 says.
- **The answer is the smallest that meets the finding:** narrowing a claim (a claim in the pull request or its code,
  never an adopted text) or stating a limit where that suffices (M1's known limits), otherwise the smallest code
  change, adding no check, option, module, dependency or call to a host tool that the finding does not name.
- **One quick check** then covers the whole diff since the full review, runs only the tests that touch it (CI is the
  matrix), and ends with a verdict at the new head. The pull request then merges on green CI (`AGENTS.md` §4).
- **There is no further full round,** and no sort of minors into those that fail open or closed. If the quick check
  finds an agent-reachable blocker or major in a fix (§10), that fix is mended and checked again quickly. Any other
  blocker or major it raises is fixed in the pull request, which then merges on green CI with no further check. A
  minor or a nit it raises is handled as §7 says. So the path ends.
- **A merge of `main` that is not a re-render (§7), or a rebase,** made while the pull request is on this path, takes
  one quick check of the whole diff against `main` at the new head. CI at the head checks how the two combine.
- **Work already past one full round** on 2026-10-24 gets only its quick check.

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
  When the review's other points are minors and nits too, the verdict is CLEAR, and the point is handled as §7 says.
- **Not covered:** a pull request that deletes, skips, marks as expected to fail or loosens a test or a gate (a weaker
  or removed assertion; a changed expected value or pinned fixture; a wider tolerance or timeout; a retry or rerun; a
  lowered baseline or threshold, such as `tests/coverage-baseline.json` or `TOLERANCE` in
  `tools/ci/coverage_gate.py`), adds a platform skip, or changes which tests CI runs or requires. It keeps the full
  review, because it can hide a failure.

## 10. What counts as a security finding (operator decision, 2026-10-24, the security depth reset)

AEW's security work is for three things, and only these:
- a contained agent cannot fake the operator's approval;
- a contained agent cannot forge an owner fact, that is, a record saying the operator decided something;
- a contained agent cannot read a credential, or act as the operator outside its sandbox.

What follows from them:
- **A security finding counts only if a contained agent can do one of those on its own,** with what AEW gives it:
  such a finding is agent-reachable. An AEW bug that lets an agent do one of the three is agent-reachable, and counts.
- **Anything else is not filed:** not as a finding, not as a residual, and not as a register row. That covers a
  precondition needing root, the host's own configuration, hardware, a compromised host, malware, an unusual
  deployment, or a second fault the agent cannot cause. Residuals and register rows already written stay.
- **Ordinary bugs still count.** Where the product does the wrong thing in normal use, or loses or corrupts work, the
  finding is a normal bug finding.
- **Briefs and reviews.** Builder and reviewer briefs do not ask for escape probes, attack reproductions, hunts for
  host side doors, or precondition classes. A test that shows the product refuses what it should is an ordinary
  product test, and it stays: for example, the sandbox refusing a credential path, or a non-writer refusing a store
  write. A reviewer reads the change and its tests against the three guarantees and for ordinary bugs.
- **The basics are done by ordinary good practice.** The PIN, the keys and TLS use standard libraries and their
  defaults, and get an ordinary review: no custom hardening, and no review beyond ordinary practice.

**The posture behind it: AEW stays easy to use, so agents never want to go around it.**
- **The main defence is a good governed path.** An agent goes around a process only if it is compromised, which is
  unlikely, or if going around it is easier than following it, or if following it doesn't help the agent get its work
  done.
- **So friction is a security cost, not a safety margin.** Every design and review asks: is the governed path the
  easiest way for an agent to get this done? Where it isn't, fix the path. Don't add a wall.
- **A refusal an agent meets** says what happened and what to do instead, and it offers a way to ask for more.
- **Containment stays for the unlikely compromised case,** kept to the core routes of the three guarantees above.

**Which findings may be fixed after their pull request** (`AGENTS.md` §2): minors and nits, as §7 says (operator,
2026-10-25). It generalises the nits-ride of S12-2's series (operator, 2026-10-24, for its pull requests 2 to 10). A
security finding an agent can reach is never followed on, whatever its label.
