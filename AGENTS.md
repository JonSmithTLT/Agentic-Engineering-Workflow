# Working on AEW: rules for every agent and contributor

These rules bind every coding agent and contributor working in this repository, whatever the harness. AEW asks the
same of the work it orchestrates (Workflow Contract v0.7, "Independent review"): implementation is separated from
review, findings return to implementation, and nothing is commit-ready while a mandatory finding is open.

The operator owns this file; a change to it is merged by the operator (rule 5).

## 1. Every pull request gets an independent review

- **Independent means a fresh context.** The reviewer is not the author's session, and never saw the author's reasoning.
  It gets the diff, the plan or design the work implements, and the repository. The same model is allowed (the
  Contract's review level R1).
- **The finding format:** severity (blocker, major, minor or nit); `file:line`; the guarantee broken; a concrete
  scenario; the fix; reproduced or not (with the command); confidence. No findings about taste in code style, and no
  redesign unless a guarantee cannot be met otherwise. Add a "what looks sound" list.
- **A repeatable defect class** (designer ruling, 2026-10-12, M1): its finding also states the governing invariant,
  the affected scope, a reproducible way to enumerate the class where that is feasible, and the known limits of that
  coverage. A claim that the class is fully fixed needs evidence from a reproducible check at the relevant revision. A
  semantic class that no mechanism enumerates reliably gets documented reasoning for its coverage instead, and is
  never claimed to be mechanically complete.
- **A nit** is a point whose fix changes no behaviour and breaks no guarantee: wording in docs, a comment, a docstring,
  a test name, a stale reference. Changing text that tests or operators rely on, such as an error message or a reason
  code, is behaviour and never a nit. The review's own label decides. The author cannot relabel a point, and an
  unlabelled point is not a nit.
- **One pass raises everything.** A review lists every finding and nit it would raise at that commit. Nothing is held
  back as "optional" for a later round. A later review still raises a real defect an earlier pass missed.
- **The review is posted on the pull request** as a comment that names the head commit it reviewed, and ends with a
  verdict line: `Review: CLEAR at <sha>` or `Review: FINDINGS at <sha>`.
- **CI at the exact head** (designer ruling, 2026-10-12, C1; a CLEAR was recorded at heads whose CI was red, and nobody
  read it). Every review comment, and every author comment that asks for review or lists fixes, gives the CI
  observation for its exact head commit in its body: which checks and runs, their completion state, and how and when
  it was observed. The verdict line stays as above. A review CLEAR is not CI qualification. A failing required check
  is named. A failure also seen on the base may inform its attribution but does not automatically waive the
  requirement, and an attribution that is not shown stays UNKNOWN.
- A review of an earlier commit does not cover later commits. After fixes, the reviewer (or a new independent one)
  checks the fixes and posts a new verdict at the new head.
- **Nits after a CLEAR get one short delta review** (operator, 2026-10-10; the product rule of the Cross-Feature
  Integration Design v0.5, §15). When the verdict is `Review: CLEAR` and its only open points are nits:
  - The author fixes them in ordinary commits on top of the reviewed commit, changing only what the nits name, and
    posts a comment that cites the CLEAR and lists each nit with how it was fixed.
  - The reviewer, or a new independent one, does one short delta review. It covers the whole diff since the CLEAR,
    runs only the tests that touch it (CI is the matrix), and ends with a verdict at the new head as usual.
  - If the delta review finds a blocker, major or minor finding, or any change in behaviour beyond the named fixes,
    its verdict is `Review: FINDINGS`, or it first widens into a normal review (full scope, its own choice of tests)
    and gives that review's verdict. Otherwise its CLEAR closes the nits.
  - The short path is used once per CLEAR: nits raised by the delta review itself are fixed and reviewed normally.
  - A merge of `main` or a rebase takes the work off this path: the next review is a normal one.
  - A nit the author disputes goes through §2 before this path applies. A blocker, major or minor finding is never a
    nit.

## 2. Findings are fixed in the same pull request

Every finding is fixed in the pull request it was raised on, nits included, before merge. "Merge now, fix in a
follow-up" is not allowed; a follow-up pull request is only for genuinely new scope. An author who disagrees with a
finding answers it on the pull request, and the reviewer either withdraws it or the operator decides.

## 3. Work while waiting, but never on top of unmerged work

- **Waiting is not blocked.** While a pull request waits for review or CI, its author may work on anything that does
  not depend on it, such as an unrelated Ticket. There is no limit on how many pull requests may be open.
- **Nothing builds on unmerged work.** Work that depends on an open pull request starts only after that pull request
  merges. Do not branch from it or stack another pull request on it.
- **Feedback comes first.** When one of an author's pull requests gets review findings, a red required check or a
  merge conflict, the author brings its current step to a safe stopping point, then fixes those before continuing
  other work.

## 4. Merging

The author may merge its own pull request when all of these hold on the **current head commit**:

- the latest review verdict is `Review: CLEAR` at that commit (after nits, that is the verdict of the review §1
  requires);
- every required check is green (the `assurance` job);
- no review conversation is unresolved, no point disputed under §2 is still open, and the pull request is not a
  draft.

Merge one pull request at a time. Do not update other branches with `main` unless they conflict: `main`'s full push
run checks the merged result. When merges land close together, a superseded pending run may be cancelled and the next
run verifies the newest tip, which contains every earlier merge (testing strategy §3). If `main` goes red, fixing it
comes before any other merge.

## 5. Reserved for the operator

- a pull request labelled `operator-merge`, which the operator or a reviewer may add to any pull request;
- a change to this file or to the repository's rulesets.

## 6. Repository hygiene

- **The repository is public.** Commit nothing that names a private project, host or person, and no credentials.
  Secret-scan every change before committing it, and the branch's commits before pushing.
- **Security findings stay private until fixed.** Never describe an unfixed vulnerability in an issue, a pull
  request or a commit message.
- Test lanes, the CI gate and the rules for adding tests are in
  [`docs/implementation/testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md).
