# Work density checkpoint 1 — phone navigation corrections

PR #52. Independent re-review **pending**. This packet addresses only F1 and F2 from `web/docs/reviews/work-density-checkpoint-1-independent-review.md`; the original reviewer disposition remains CHANGES REQUESTED until re-checked.

## Committed source

- Runtime: `032a316dcb8a70cbaf91abce45306d383d5705e1`.
- Tree: `cdb5c0036f7819a69ce0e9aa6bc0a649f6e798cc`.
- Corrections: `bed0044` followed by `032a316`.
- Parent review packet: `ee9342c`; independently reviewed original runtime: `c899c70`.

The remote main merge was fast-forwarded without modifying its Engine changes. Correction commits touch frontend presentation, regression tests, behavior documentation and the supplied review record only. Contracts, generated types and dependency lock are unchanged.

## Findings and behavior

| Finding | Correction | Re-check |
|---|---|---|
| F1: phone child selection kept Results scroll and lost focus | A visible phone Detail waits for the matching loaded Work heading and focuses it through `focusBelowHeader`, after the route/history layout settles. Pending focus work is cancelled on selection/pane departure. | S-0001 → Inspect children → T-0001, with Results scrolled down; title and RUNNING visible, heading focused. Covers pointer and Enter selection. |
| F2: Back focused an off-screen Results heading | Capture the originating Results link. On history return, restore that connected link after native scroll restoration; fall back to the Results heading if the link is no longer loaded. | Back from T-0001 restores visible child-link focus; Forward restores visible detail heading. |

Explicit Results/Detail switching also handles the same selected record. Desktop row selection retains link focus. Refresh and unrelated URL disclosures do not retrigger heading focus. No new reads, cache identity, polling policy, inferred explanations or API fields are introduced.

## Verification

The pinned offline gate passed: artifact checks, unchanged generated accepted types, typecheck, lint, **167 tests in 19 files**, production and demo builds, and production exclusion. Builder: `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, network disabled. Node v22.22.2/npm 10.9.7.

The first correction commit's gate found three unqualified browser globals in the new test assertions. These were corrected before the final clean build. No screenshots or successful build evidence are attributed to that failed attempt.

`freeze-w06-evidence.sh 032a316dcb8a70cbaf91abce45306d383d5705e1` uses a clean detached checkout of the exact runtime commit. Complete production/demo manifests and their before/after verification, runtime hashes, commands, suite outputs and screenshots are archived in `web/docs/reviews/work-density-checkpoint-1-correction/`. Final freeze **PASS**: W01 (16 groups), W02 (11), W03 (12), HTTP demo (5), W04 (22), W05 (25), W06 (22). Source stayed clean and both complete build manifests were unchanged afterward.

Complete build-manifest SHA-256: production `486c3a2c531c0c46fd5f850fc771598321ce47154a777c67ba21775110f7f89a`; demo `19030453fa2102481cd834472e61b4d0462ee0588b76bddb9275f1859afbe75a`. The archived `manifest.json` hashes every evidence file, including command logs. The freeze procedure's inherited recorder measurements compare different W05/W06 workflows; they are not a Work performance claim. Build chunk-size advisories and jsdom's unimplemented scroll warning remain visible in the logs; real Chromium geometry checks passed.

Compiled W02 adds desktop keyboard-position preservation and phone Detail/Back/Forward geometry checks. HTTP demo adds a service-worker-blocked phone task beginning at scroll 652, Enter selection, Back/Forward, and reopening the same selection through Results/Detail. Pages continue replacing content.

Supplementary in-app browser inspection of this clean build: phone 390×844, header bottom 108; selected T-0001 heading top approximately 439 at scroll 0; Back focuses its Results link at top approximately 411 with restored scroll approximately 639. Desktop 1440×1000 retains the selected Results anchor as the active element. These are observations, not a timing or physical-device claim. Screenshots are `phone-detail.jpg`, `phone-back.jpg`, and `desktop-row-focus.jpg`.

Strict premium audit of the frozen source: exit 0, zero findings (`--mode strict --no-write`). Static checks do not establish usability acceptance.

## Re-review task

On phone, open S-0001, Inspect children, select T-0001 from scrolled Results with mouse and Enter. Confirm visible record title/state and heading focus. Use browser Back and Forward and check that the focused row or heading remains visible below the sticky header. Reopen the same record with the pane switch. On desktop, confirm row focus and sequential keyboard position survive selection.

The original independent review's coverage limits remain: no real browser zoom, shown-data refresh failure, full unaffected Runs/Evidence visual comparison, or physical-device review. Existing automated regressions supply separate coverage and are not independent acceptance. No further cleanup checkpoint is included in this correction.
