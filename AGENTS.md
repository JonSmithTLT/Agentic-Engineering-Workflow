# Working on AEW: rules for every agent and contributor

These rules bind every coding agent and contributor working in this repository, whatever the harness. AEW asks the
same of the work it orchestrates (Workflow Contract v0.7, "Independent review"): implementation is separated from
review, findings return to implementation, and nothing is commit-ready while a mandatory finding is open.

The operator owns this file; a change to it is merged by the operator (rule 5).

## 1. Every pull request gets an independent review

- **Independent means a fresh context.** The reviewer is not the author's session, and never saw the author's reasoning.
  It gets the diff, the plan or design the work implements, and the repository. The same model is allowed (the
  Contract's review level R1).
- **The finding format:** severity (blocker, major or minor); `file:line`; the guarantee broken; a concrete scenario;
  the fix; reproduced or not (with the command); confidence. No style findings, and no redesign unless a guarantee
  cannot be met otherwise. Add a "what looks sound" list.
- **The review is posted on the pull request** as a comment that names the head commit it reviewed, and ends with a
  verdict line: `Review: CLEAR at <sha>` or `Review: FINDINGS at <sha>`.
- A review of an earlier commit does not cover later commits. After fixes, the reviewer (or a new independent one)
  checks the fixes and posts a new verdict at the new head.

## 2. Findings are fixed in the same pull request

Every finding is fixed in the pull request it was raised on, nits included, before merge. "Merge now, fix in a
follow-up" is not allowed; a follow-up pull request is only for genuinely new scope. An author who disagrees with a
finding answers it on the pull request, and the reviewer either withdraws it or the operator decides.

## 3. Finish before you start

An author does not start new work while one of its own pull requests has open review findings, a red required check,
or a merge conflict. It fixes those first. There is no limit on how many pull requests may be open: work that is clean
and waiting for review or CI does not block new work.

## 4. Merging

The author may merge its own pull request when all of these hold on the **current head commit**:

- the latest review verdict is `Review: CLEAR` at that commit;
- every required check is green (the `assurance` job);
- no review conversation is unresolved, and the pull request is not a draft.

Merge one pull request at a time. Do not update other branches with `main` unless they conflict: every push to `main`
runs the full gate, which checks each merge. If `main` goes red, fixing it comes before any other merge.

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
