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
  loads: the finding format, the labels, defect classes (M1), one pass raises everything, nits after a CLEAR, one full
  round and a quick check, proportion in a test-only pull request, and what counts as a security finding. Where it says
  what an author does, it binds authors too, and builder briefs load it.
- **The review is posted on the pull request** as a comment that names the head commit it reviewed, and ends with a
  verdict line: `Review: CLEAR at <sha>` or `Review: FINDINGS at <sha>`. A review of an earlier commit does not cover
  later commits: after fixes, the reviewer (or a new independent one) posts a new verdict at the new head.
- **CI at the exact head.** Every review, every pull-request description, and every author comment that asks for
  review or lists fixes gives the CI observation for its exact head commit in its body (review guide §6). The verdict
  line stays as above.

## 2. Findings are fixed in the same pull request

Every finding is fixed in the pull request it was raised on, nits included, before merge. "Merge now, fix in a
follow-up" is not allowed; a follow-up pull request is only for genuinely new scope. The only exceptions are those the
review guide's §10 lists. An author who disagrees with a finding answers it on the pull request, and the reviewer
either withdraws it or the operator decides.

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

- the latest review verdict is `Review: CLEAR` at that commit (after nits, that is the verdict of the review the
  review guide requires), or the latest is a quick check that raised points needing no further check (review guide
  §8), the commits since it change only what those points name, apart from a re-render (review guide §7), and the
  author's comment at that commit lists how each was fixed;
- every required check is green (the `assurance` job);
- no review conversation is unresolved, no point disputed under §2 is still open, and the pull request is not a
  draft.

Merge one pull request at a time. Do not update other branches with `main` unless they conflict: `main`'s full push
run checks the merged result. When merges land close together, a superseded pending run may be cancelled and the next
run verifies the newest tip, which contains every earlier merge (testing strategy §3). If `main` goes red, fixing it
comes before any other merge.

## 5. Reserved for the operator

- a pull request labelled `operator-merge`, which the operator or a reviewer may add to any pull request;
- a change to this file, to the [review guide](docs/implementation/review-guide.md), or to the repository's rulesets.

## 6. Repository hygiene

- **The repository is public.** Commit nothing that names a private project, host or person, and no credentials.
  Secret-scan every change before committing it, and the branch's commits before pushing.
- **Security findings stay private until fixed.** Never describe an unfixed vulnerability in an issue, a pull
  request or a commit message.
- Test lanes, the CI gate and the rules for adding tests are in
  [`docs/implementation/testing-and-ci-strategy.md`](docs/implementation/testing-and-ci-strategy.md).
