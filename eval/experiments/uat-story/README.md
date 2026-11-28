# The UAT story workload (`uat-story-v1`)

**What it is for:** the operator's user acceptance test of AEW on a story-sized piece of work in a real codebase, and
a manual comparison: the same tree and the same opening request through AEW, then through the harness alone
(OpenCode, no AEW), on the same model.

**The headline is escapes, not pass rate.** A capable worker makes the visible tests pass almost every time, so
"the tests are green" tells the two runs apart poorly. What the comparison counts is wrong work that got through: an
item the run said was done whose hidden checks fail. Four items carry an escape trap for this ("Escape traps").

**What it is not:** an experiment. Nothing is preregistered, no attempt is registered and no result is evidence for
M4-H or any treatment effect. It reuses F19's case material and its hidden-evaluator channel so that the two runs are
scored the same way, by checks neither run could see. One run of each arm is a demonstration, not a measurement.

## The work

One opening request ([`opening-request.md`](opening-request.md)) asks for one Story of eight items on the link policy
extension of the lower-bound qualification lane's fixture (Python-Markdown 3.11.0 plus that lane's seeded extension).
Items 1 to 3 are that lane's cases LBQ-1 to LBQ-3, unchanged; items 4 to 8 are new. [`workload.yaml`](workload.yaml)
lists each item's id, the oracle that scores it, the order the request states (`depends_on`), the items whose correct
change edits the same file (`shares`), and what it exercises.

| Task | Item | What it exercises in AEW |
|---|---|---|
| UAT-1 | mixed-case and whitespace-prefixed blocked schemes get through (a symptom, not a file) | navigation to a cause three directories deep past a same-named decoy and a stale TODO naming the wrong fix; the map; declared review and verification |
| UAT-2 | a new `rel_external` option | a change whose obvious local part (the tree processor) is incomplete without the option table, its validation, the documentation and tests; two escape traps |
| UAT-3 | a dependable `report()` and strict mode, four criteria | requirement loss on a longer task; one criterion needs an investigation outside the extension; an escape trap |
| UAT-4 | image sources are not checked (a symptom), after item 3 | a stated dependency; the same function as items 2, 3 and 7, so the integration queue must order them or one is reworked; declared review and verification; an escape trap |
| UAT-5 | enable the extension by its short name, here and in a built package | a scope trap: the fix needs files outside the extension, which the request says to raise before changing |
| UAT-6 | review a contributor's branch, `contrib/allowed-schemes`, without merging it | a branch-review Ticket (`aew work create ticket --non-mutating --review-ref contrib/allowed-schemes`), its checks run only contained; nothing reaches `main` |
| UAT-7 | the allow-list done properly, after the review, six lettered requirements and "fix whatever the review found" | a long task where one requirement is easy to drop; the review's findings feed the work, since the request does not restate them; the same file and function as items 1 to 4; declared review and verification |
| UAT-8 | the documentation site, the extensions index and a changelog of items 1 to 7, last | a Ticket the request says needs no independent review or verification; history search to list what the Story did; requirement loss |

**The shape of the plan.** UAT-1, UAT-2, UAT-3, UAT-5 and UAT-6 can start at once. UAT-4 waits for UAT-3, UAT-7 for
UAT-6, and UAT-8 for every mutating item. AEW runs two mutating Tickets at once only when their scopes cannot name the
same file, so how the Lead draws the scopes (one shared test module, or one per item) decides how much runs in
parallel. UAT-2, UAT-3, UAT-4 and UAT-7 all change the tree processor's one loop and the extension's documentation
page; UAT-1 and UAT-7 both change `rules.py`.

```
UAT-1 ──────────────┐
UAT-2 ──────────────┤
UAT-3 ── UAT-4 ─────┤
UAT-5 ──────────────┼── UAT-8
UAT-6 ── UAT-7 ─────┘
```

## Escape traps

An escape trap is a place where wrong work can pass every test the run can see. Each is scored by a hidden oracle of
its own, validated against a plausible escaped solution as well as the start and the reference. Four kinds, on items
2, 3 and 4 (`escape_trap` in `workload.yaml`); which kind sits where, and how, is private:

- **an existing test the obvious change breaks**, where the quickest way back to green is to weaken, skip or delete
  the test instead of fixing the change;
- **a requirement only the request states**, which no test in the tree checks;
- **a breakage far from the edit**, in a module whose tests are not the extension's: a run that only runs the
  extension's tests does not see it, the whole suite (the project's configured check) does;
- **a change whose obvious diff reads right and is subtly wrong**, which a shallow review approves.

## The starting tree

[`materialize.py`](materialize.py) builds it, the same way for both arms:

```sh
python eval/experiments/uat-story/materialize.py <new directory> > <new directory>.start.json
```

- `main`: the pinned upstream (the lower-bound lane's [`upstream.yaml`](../lower-bound-qualification/upstream.yaml):
  taken from that lane's fetched copy when `qualify.py fetch` has run, otherwise cloned at the pinned tag and refused
  at any other commit or tree), plus that lane's seeded overlay, **without its distractor test**
  (`test_wikilinks_spaces.py`). Here the project's configured check is the whole upstream suite, and the starting
  point must pass it. `Markdown.egg-info` is committed although upstream ignores it: a Ticket workspace is built from
  the commit, and without that metadata the suite cannot resolve its extensions.
- this workload's own seeded files, [`fixture/overlay/`](fixture/overlay/), beside the others (never replacing one):
  a module of the comments site that uses the extension, with its tests, and more of the extension's own tests.
- `contrib/allowed-schemes`: one commit over `main` by a contributor, the files in
  [`fixture/contrib-branch/`](fixture/contrib-branch/): an allow-list mode, with its own passing tests. Whether it is
  safe to merge is the question of item 6. The answer and the reasons are private.
- Fixed author names and dates: two builds of the same inputs have the same commit ids. The printed `main` and
  branch commits are how the operator confirms that the AEW tree and the raw tree are the same tree.
- Not byte for byte the upstream tag: text is written with LF line ends and no file keeps an executable bit, as the
  lane reads its fixtures, so upstream's CRLF test fixture (`tests/misc/CRLF_line_ends.txt`) and `checklinks.sh`'s mode
  differ. Both runs get the same tree, so the comparison is unaffected.

The upstream suite passes on `main` and on the branch.

## Scoring

**The private evaluation root must not be on the host while either run is going.** It holds the oracles and the
reference solution. The raw run (OpenCode alone) is not contained, and AEW's Lead session is not either, so anything
the operator's user can read, they can read. Bring it onto the host only after both runs have ended, then score.

Each task has a hidden oracle in the private evaluation root, in the format of the lower-bound lane's
(`cases/<id>/oracle/checks.py`), validated against the untouched starting tree (it fails exactly its task's criteria)
and against a reference solution (every check passes). A private script scores a finished tree, the AEW run's `main`
or the raw run's working files, against every oracle through F19's hidden-evaluator channel
([`hidden.py`](../../aew_eval/hidden.py)) and prints a pass/fail table per task. The oracles and their validation,
the reference solution, the contributor branch's flaws and the scoring script are private and are not described
here.

Item 6's deliverable is a review, not a tree. The operator saves, as text, what the run told them about the branch
(AEW: the review record's body and the Lead's answer to "is it safe to merge?"; raw: the agent's answer) and gives it
to the scorer. Its checks are lexical and assisted: the operator confirms each by reading the review.

The scorer refuses an oracle whose content no longer matches its validated hash: that row is not scored.

## Files

| File | What it is |
|---|---|
| `opening-request.md` | the one message the operator pastes, identical for both arms |
| `workload.yaml` | the tasks: ids, oracles, stated dependencies, shared files, what each exercises |
| `materialize.py` | builds the starting repository |
| `fixture/overlay/` | this workload's seeded files on `main` |
| `fixture/contrib-branch/` | the contributor's change, committed on `contrib/allowed-schemes` |
