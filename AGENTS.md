# Working on AEW: rules for every agent and contributor

These rules bind every coding agent and contributor working in this repository, whatever the harness. AEW asks the
same of the work it orchestrates (Workflow Contract v0.7, "Independent review"): implementation is separated from
review, findings return to implementation, and nothing is commit-ready while a mandatory finding is open.

The operator owns this file and the review guide; a change to either is merged by the operator (rule 5).

## 1. Every pull request gets an independent review

- **Independent means a fresh context.** The reviewer is not the author's session, and never saw the author's reasoning.
  It gets the diff, the plan or design the work implements, and the repository. The same model is allowed (the
  Contract's review level R1).
- **How a review is done is in the [review guide](docs/implementation/review-guide.md),** which every review brief
  loads: the finding format, the labels, defect classes (M1), one pass raises everything, how minors and nits are
  fixed or followed on, one full round and a quick check, proportion in a test-only pull request, and what counts as
  a security finding. Where it says what an author does, it binds authors too, and builder briefs load it.
- **The review is posted on the pull request** as a comment that names the head commit it reviewed, and ends with a
  verdict line: `Review: CLEAR at <sha>` or `Review: FINDINGS at <sha>`. A review of an earlier commit does not cover
  later commits: after fixes, the reviewer (or a new independent one) posts a new verdict at the new head, except
  where §4 allows a merge without one.
- **CI at the exact head.** Every review, every pull-request description, and every author comment that asks for
  review or lists fixes gives the CI observation for its exact head commit in its body (review guide §6). The verdict
  line stays as above.

## 2. What a finding blocks

Blockers and majors, and a security finding an agent can reach whatever its label (review guide §3, §10), are fixed
in the pull request they were raised on, before merge. Minors and nits do not block a merge, and they are never
dropped (operator, 2026-10-24):
- while the author is changing the pull request anyway (other than to fix a trivial point, to record a follow-on, or
  to merge `main` as a re-render), it fixes them in the same pass;
- a trivial one, such as a docstring or a line of wording, is fixed before merge when that causes no large delay;
- every other one is a tracked follow-on, recorded before merge: the series' next pull request that has not merged
  fixes it, or a register note names it and what is meant to fix it (review guide §7).

A follow-up pull request is otherwise only for genuinely new scope. An author who disagrees with a finding answers it
on the pull request, and the reviewer either withdraws it or the operator decides.

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

- the latest review verdict is `Review: CLEAR` at that commit (a CLEAR may list minors and nits as follow-ons: §2,
  and review guide §7), or the latest verdict is at an earlier commit and the commits since it change only what that
  review's points name, as trivial fixes or follow-on notes or rows after a CLEAR or as the fixes that need no further
  check after a quick check (review guide §7, §8), apart from a re-render (review guide §7);
- where the latest verdict lists minors or nits, or commits follow it, the author's comment at that commit names, for
  each point, the commit that fixed it or where it is tracked (review guide §7);
- every required check is green (the `assurance` job);
- no review conversation is unresolved, no point disputed under §2 is still open, and the pull request is not a
  draft.

Merge one pull request at a time. Do not update other branches with `main` unless they conflict: `main`'s full push
run checks the merged result (testing strategy §3). If `main` goes red, fixing it comes before any other merge.

## 5. Reserved for the operator

- a pull request labelled `operator-merge`, which the operator or a reviewer may add to any pull request;
- a change to this file, to the [review guide](docs/implementation/review-guide.md), or to the repository's rulesets.

## 6. Repository hygiene

- **The repository is public.** Commit nothing that names a private project, host or person, and no credentials.
  Secret-scan every change before committing it, and the branch's commits before pushing.
- **A gate reads the commit, and its own exit code decides.** A gate (a secret scan, a test run, a check) runs on the
  commit or the staged change, never on the working tree alone. Run it on its own, never through a pipe: piped, the
  last command's exit code is the one that counts, so a failing gate can pass.
- **Security findings stay private until fixed.** Never describe an unfixed vulnerability in an issue, a pull
  request or a commit message.
- Test lanes, the CI gate and the rules for adding tests are in
  [`docs/implementation/testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md).

## 7. A reference record names the requirements it serves

The generated reference (`docs/reference/`) states what the code is and holds no requirement; the trace from
requirements to records belongs to the design side (operator, 2026-10-23).
- **A pull request that adds a reference record names, in its description, the requirement IDs the record serves.**
  IDs only, never requirement text. The IDs come from the hand-off the pull request builds, or from the designer when
  the hand-off names none.
- **A record that serves no adopted requirement says "none", with a line on why.** It is not refused: the next trace
  flags it for the operator.
- **The IDs never go in the generated reference.** `tests/unit/test_reference.py` fails on one in `docs/reference/`.
