# M3 dogfood report (step 9)

**Question:** does AEW make real engineering work better, not merely more elaborate?

**Method:** AEW with a real model as Lead, against plain OpenCode, on the same six tasks, the same models and the same isolation.

**Runs:** 47 dogfood runs and a 6-trial model comparison, on 2026-09-28 and 29.

**Models:** GPT-5.6 Luna (cheap) and GPT-6 Sol (strong), both at medium effort, on OpenCode 2.0.18.

**Spend:** USD 6.08 of the operator's USD 10.

**Rubric:** fixed before the paid runs, with two recorded amendments (`eval/m3/dogfood/rubric.md`).

**Data:**
- `eval/m3/dogfood/results.jsonl`: one record per run;
- `eval/m3/dogfood/comparison.jsonl`: the model comparison;
- `eval/m3/dogfood/README.md`: how to reproduce.

## 1. Summary

- **On these six small tasks, plain OpenCode was never worse, and it was much cheaper.**
  - Plain OpenCode passed the hidden test in **20 of 20** runs.
  - AEW, on the hardened code, passed in **24 of 26** runs, and in 24 of 25 once a run that stalled on an AEW defect (now fixed) is set aside.
  - With GPT-6 Sol, AEW passed **12 of 12**.
  - AEW cost about **6.5×** (Luna) and **7.5×** (Sol) as much as plain OpenCode per task, and took about **7×** as long.
  - The Lead, AEW's coordination overhead, accounted for about **40%** of AEW's cost.
- **Where AEW's mechanisms did what they are for:**
  - **Losing the Lead's harness mid-Ticket.** Its OpenCode was killed and its state wiped. A fresh session rebuilt its context from AEW alone and reached DONE in **3 of 3** runs where the loss happened. Plain OpenCode has no equivalent.
  - **Independent review caught the seeded defect** before integration in **4 of 4** AEW runs of T5, and in **6 of 6** model-comparison trials. With Sol, the reviewer also rejected the *rework* twice, for a subtler precision defect the hidden test does not measure.
  - **Investigation Tickets.** Leads used a read-only investigation Ticket before a fix Ticket on the investigation task (T3, 4 of 4). With Sol they did so on the wrong-hypothesis task as well (T4, once).
  - **Independent verification caught a corrupted goal** (T1, first run). The Lead then replanned instead of accepting the implementation.
- **Where AEW made the result worse.** In one run (T4, Luna) AEW integrated a wrong change that passed review and two verifications.
  - The Lead took the operator's wrong hypothesis as the plan, allowed the sample data file into the Ticket's scope, and wrote a goal about the CSV as it stands.
  - The implementer then edited the data to make that goal true.
  - Plain OpenCode fixed the real bug in both of its runs.
  - With Sol as Lead, AEW investigated or planned the real fix and passed both times. **AEW's outcome depends on the Lead's planning, and the gates cannot compensate for goals that can be met by changing their inputs** (§6.2).
- **Step 9 found three AEW defects**, all fixed with regressions:
  - M3-D8: next actions after a harness run;
  - M3-D9: a scope glob containing a comma;
  - M3-D10: `resume` inside a Lead session said the session held no authority.

  It also motivated the companion review's hardening **B1**: authored text now travels as data. Its failure class stopped occurring after the fix.
- **Verdict for the designer.** On small, well-specified tasks that a single model already solves, AEW adds cost and time and no correctness. Its value, as measured here, is durability, independent review and traceability. The tasks were too easy to show a quality difference: both models solved all of them unaided. A fair test of AEW's quality claim needs harder, longer work (§11).

## 2. What ran

| | AEW mode | Raw mode |
|---|---|---|
| Agent | A headless **model Lead**: the production `aew-lead` agent in `aew lead session`. It holds no credential; its broker does. Every role is a real run through the production adapter. | OpenCode's own `build` agent, with its own system prompt and permissions |
| Instructions | The operator's objective, plus a brief: AEW's quickstart in Lead terms, standing in for AEW skills | The objective, plus "nobody will answer questions: finish the task" |
| Model | The same for every role and the Lead (Luna, or Sol) | The same |
| Human involvement | None. At most two automatic nudges if the Lead ends its turn with work open; none were needed on the hardened code. | None |
| Isolation (both) | A scratch git repository outside the AEW checkout, private OpenCode state per session and run, no user configuration or plugins, the provider key only in OpenCode's server, and a curated shell environment | The same |
| Judged by | A hidden test on the integrated commit (`main`) | A hidden test on the working tree |

**The six tasks** are on a small `ledger` project: a CSV ledger with a CLI and a pytest suite, about 200 lines. Each starting point passes its own tests and fails its hidden test; `dogfood.py selfcheck` proves it, together with a reference solution per task.

| Task | Kind | The catch |
|---|---|---|
| T1 | tiny fix | negative amounts print `$-15.00` |
| T2 | multi-file feature | `--category`, with its error path and a README update |
| T3 | bug to investigate | the objective gives only the symptom: monthly totals don't add up |
| T4 | wrong hypothesis | the operator blames float arithmetic and asks for Decimal; the cause is parsing (`23.4` read as 23.04) |
| T5 | seeded defect | a plausible `split_amount` whose shares don't add up, with passing tests. AEW starts from its submitted report; raw is asked to review and fix it. |
| T6 | resume | T2's objective. Once the Lead has launched its first role run, its OpenCode is killed and its state wiped; a fresh session resumes from AEW alone. |

**Plan and order:**
1. A free-model shakedown of the driver, at no cost.
2. The first paid run: T1 in AEW mode on Luna.
3. The companion-review hardening (B1 to B3, `m3-companion-review-triage.md`), recorded as rubric amendment A1.
4. All tasks × both modes × two trials on Luna.
5. The T6 driver fix (amendment A2), and T6 rerun.
6. The model comparison.
7. All tasks × both modes × two trials on Sol.

## 3. Results

Runs on the hardened code (every record with an `aew_commit`). Cost is OpenCode's own figure; the recomputation from tokens at catalog prices matches it exactly.

| Task | Mode | Model | Passed (hidden test) | DONE | Mean USD | Mean wall s | Mean role runs |
|---|---|---|---|---|---|---|---|
| T1 | AEW | Luna | 2/2 | 2/2 | 0.027 | 114 | 4.0 |
| T1 | raw | Luna | 2/2 | – | 0.004 | 18 | – |
| T1 | AEW | Sol | 2/2 | 2/2 | 0.320 | 191 | 4.0 |
| T1 | raw | Sol | 2/2 | – | 0.045 | 28 | – |
| T2 | AEW | Luna | 2/2 | 2/2 | 0.044 | 195 | 5.0 |
| T2 | raw | Luna | 2/2 | – | 0.007 | 29 | – |
| T2 | AEW | Sol | 2/2 | 2/2 | 0.301 | 204 | 4.0 |
| T2 | raw | Sol | 2/2 | – | 0.058 | 38 | – |
| T3 | AEW | Luna | 2/2 | 2/2 | 0.047 | 192 | 5.0 |
| T3 | raw | Luna | 2/2 | – | 0.005 | 18 | – |
| T3 | AEW | Sol | 2/2 | 2/2 | 0.469 | 263 | 5.0 |
| T3 | raw | Sol | 2/2 | – | 0.044 | 23 | – |
| T4 | AEW | Luna | **1/2** | 2/2 | 0.034 | 149 | 4.0 |
| T4 | raw | Luna | 2/2 | – | 0.007 | 28 | – |
| T4 | AEW | Sol | 2/2 | 2/2 | 0.394 | 215 | 4.5 |
| T4 | raw | Sol | 2/2 | – | 0.047 | 23 | – |
| T5 | AEW | Luna | 2/2 | 2/2 | 0.038 | 163 | 5.0 |
| T5 | raw | Luna | 2/2 | – | 0.006 | 26 | – |
| T5 | AEW | Sol | 2/2 | 2/2 | 0.509 | 293 | 7.0 |
| T5 | raw | Sol | 2/2 | – | 0.071 | 57 | – |
| T6 | AEW | Luna | 1/2 | 1/2 | 0.018 | 84 | 2.0 |
| T6 | AEW | Sol | 2/2 | 2/2 | 0.316 | 183 | 4.0 |

Notes on the table:

- **T6 on Luna** counts the two reruns on the fixed driver. One resumed and reached DONE. The other stalled on M3-D10 before any work: it never started a Ticket, so no loss happened.
- **Two earlier Luna T6 runs** never triggered the loss (a driver defect, amendment A2). They are T2 repeats: both passed and reached DONE, at USD 0.032 and 0.035, and they are not counted as T6.
- **The first run**, T1 in AEW mode on Luna before the hardening: it passed and reached DONE at USD 0.062. It took three Tickets, two of them wrecked by the Lead's shell-quoting and scope mistakes (§7). It is kept as a record of the unhardened code and is not scored against the rest.

**Aggregates (T1 to T5):**

| | AEW mean USD | Raw mean USD | Ratio | AEW mean s | Raw mean s | Ratio |
|---|---|---|---|---|---|---|
| Luna | 0.038 | 0.0058 | 6.5× | 163 | 24 | 6.8× |
| Sol | 0.399 | 0.053 | 7.5× | 233 | 34 | 6.9× |

- **Sol against Luna:** about 10.5× the cost in AEW mode and 9× in raw mode.
- **The Lead's share of AEW cost:** 40% on average across both models; 25–54% per run, excluding the stalled run, where the Lead was everything.

## 4. The hypotheses (rubric)

| | Hypothesis | Verdict |
|---|---|---|
| H1 | Overhead: on T1 and T2 both modes pass; AEW costs several times more and takes longer | **Supported.** 16 of 16 passed across both modes and models. AEW cost 6.5× (Luna) to 7.5× (Sol) more. |
| H2 | Quality: on T3, T4 and T5 AEW is at least as good as raw; on T5 its review catches the seeded defect more reliably than a raw session asked to review | **Not supported.** On T3 and T5, both modes passed every run. On T4, AEW on Luna was worse (1/2 against 2/2); on Sol it was equal. On T5, AEW's review caught the defect 4/4 and raw, asked to review, also fixed it 4/4, so it was not more reliable. The tasks did not separate the modes (§11). |
| H3 | Resilience: the resumed Lead continues from AEW state alone, without redoing accepted work, and reaches DONE | **Supported, on three runs.** In every run where the loss happened (Luna once, Sol twice), the new session began with `aew resume` and `aew status` (and `aew work show` and `aew harness status`). It followed the live run, ingested its evidence and reached DONE. No accepted work was redone: each run has exactly one implementer. |
| H4 | Asymmetry: a cheap implementer with a strong reviewer and verifier does no worse on correctness than the reverse, at lower cost | **Correctness: inconclusive** (both 3/3, a ceiling). **Cost: not supported**, the reverse held: A cost USD 0.065 a trial and B USD 0.044, because review and verification are three of the four runs (§5). |

## 5. The model comparison

This used the step-8 rejection-and-rework scenario: a seeded floor-division `safe_div`, then real models in every role, 3 trials per configuration.

| Configuration | Defect caught at first review | Final state | Correct | USD per trial |
|---|---|---|---|---|
| A: Luna implementer; Sol reviewer and verifier | 3/3 | VERIFIED 3/3 | 3/3 | 0.065 |
| B: Sol implementer; Luna reviewer and verifier | 3/3 | VERIFIED 3/3 | 3/3 | 0.044 |

- **Every review caught the defect with a major, required finding.** Luna's reviews were as specific as Sol's, for example: "safe_div uses floor/integer division, so safe_div(7, 2) returns 3 instead of the required 3.5".
- **The seeded defect is too easy to tell reviewers apart**, as in step 8.
- **Where the models did differ:**
  - in T5, Sol's reviewers also caught a precision defect in the rework;
  - in T4, the Sol Lead's planning avoided the trap the Luna Lead fell into.

  Both point to the Lead and reviewer roles as where a stronger model pays off. That is a hypothesis for a better-designed comparison, not a result.

## 6. What AEW's mechanisms did

### 6.1 As intended

- **Resume (T6), 3 of 3.** The rebuilt Lead used AEW's own affordances: resume, status, harness status and the next actions. It carried on from the live run, not from the conversation it had lost.
- **Independent review (T5).** The first review failed the seeded implementation every time, for example "The implementation rounds one common share and repeats it, so uneven totals do not add up exactly". AEW returned the Ticket for rework under a new invocation and credential, and the rejected attempt's evidence never satisfied a gate.
  - Both Sol runs needed two reworks. The second review found that the first fix's Decimal arithmetic "rounds large cent amounts using the active Decimal precision, so shares can fail to sum to the total".
- **Investigation (T3, and T4 with Sol).** Leads opened a read-only investigation Ticket, ingested its record, then created a fix Ticket with goals stated as observations, for example "the three monthly totals equal USD 1,566.70, 1,618.25 and 1,569.99; together USD 4,754.94".
  - The Sol Lead on T4 did not follow the operator's hypothesis. Its fix Ticket kept the requested Decimal change and added "23.4 parses as 23.40", scoped to `ledger/money.py`, `ledger/report.py` and `tests/**`, with the data excluded.
- **Verification (T1, first run).** The verifier compared the corrupted stored goal with reality and failed the Ticket. The Lead correctly classified the failure as `PLAN_OR_DESIGN_DEFECT`, not an implementation defect, and replanned.

### 6.2 T4, run 18: an integrated wrong change

| | Luna trial 1 (passed) | Luna trial 2 (failed) | Sol trials 1 and 2 (passed) |
|---|---|---|---|
| Goals | "January grocery total is USD 54.50", plus Decimal | "totals exactly match the sum of CSV amounts", plus no floats | a parse goal (`23.4` is 23.40), plus Decimal and the January total |
| Scope | `ledger/**`, `tests/**` | `ledger/report.py`, `tests/**`, **`data/sample.csv`** | `ledger/money.py`, `ledger/report.py`, `tests/**` |
| Implementer | fixed parsing | switched to Decimal and **changed `23.4` to `23.40` in the data** | fixed parsing |
| Review and verifications | pass | pass | pass |

Every AEW mechanism behaved as designed: scope was enforced as the Lead wrote it, and the gates judged the goals as the Lead wrote them. The failure lies in what the Lead wrote. It encoded an unverified operator hypothesis, stated a goal that could be met by changing its own inputs, and allowed those inputs into scope. Neither the reviewer nor the verifiers questioned an edit to the operator's data.

What might prevent this (for the designer; see `future-work.md` O3):
- **Guidance:** goals stated as observable outcomes on unchanged inputs; hypotheses verified or investigated before they become goals (the Lead/operator design's "investigate before asking" applies to hypotheses too).
- **Policy:** protected paths for data and fixtures that acceptance goals refer to (`guardrails.yaml` already supports `protected_paths`).
- **Review:** a reviewer card item that flags changes to inputs or test data that the goals are measured against.

### 6.3 Friction

- **Most Leads made one to three failed calls** that an error message corrected at once:
  - `aew evidence ingest` on an implementation report (most runs; the brief lists `evidence ingest` among the ingest commands);
  - a first `--fields` attempt with a wrong key such as `goals:` (refused, then corrected);
  - `aew work assign` or `dispatch` on a Ticket in the wrong state.
  - Since 2026-09-29 these refusals name the command that applies, and `resume`'s next actions give runnable commands (`m3-audit-findings.md` X1, X2).
- **Leads spend many steps waiting.** `aew harness wait` in 110-second slices re-sends the whole context each time. This is a large part of why the Lead is about 40% of AEW's cost.
  - **Correction (2026-09-29, `m3-audit-findings.md` L1).** Re-analysing the 29 Lead sessions shows waiting is 12% of the Lead's steps (a median of 4 of 34), although it is about 55% of the Lead's wall time. The Lead's cost comes from the workflow choreography: a median of 20 workflow commands per session, each a model step that re-reads a growing context. The results in this report are unchanged; only this explanation is corrected. The response is the Lead workflow efficiency design (`future-work.md` F15).
- **Risk class.** After the hardening, Leads chose Class 1 or 2 for every task, T1 included, so the Class 0 fast path was never used. This follows the fail-closed default the companion review asks for, and costs the full review and verification each time.
  - **Correction (2026-09-30).** The one pre-hardening run chose Class 1 too, so the hardening did not cause this. The Leads' reasoning points to three causes: the Lead's only example command used `--class 1` (now neutral), Class 0 read as insufficiently evidenced, and no operational criteria for Class 0 (`future-work.md` Q10: X4a, X4b, X4c).

### 6.4 The Class 0 path (rubric amendment A3, 2026-09-30)

T1 was meant to exercise the Class 0 path and never did: on the hardened code the Leads chose Class 1 or 2 for all 30 Tickets, T1's included (§6.3). The M3 audit (X4) and the designer asked for the path to be tested. Task T1C0 is T1's objective plus one operator sentence, "It is a trivial, low-risk fix: handle it as a Class 0 Ticket", judged by T1's hidden test. It was pre-registered before any run (`rubric.md`, A3).

| Trial | Class chosen | Path | Role runs | Hidden test | USD | Wall s | Lead steps | Refused `aew` commands |
|---|---|---|---|---|---|---|---|---|
| 1 | 0 | ASSIGNED → RUNNING → COMMIT_READY → DONE | implementer, post-integration verifier | passed | 0.017 | 183 | 24 | 2 |
| 2 | 0 | the same | the same | passed | 0.016 | 85 | 26 | 3 |

- **The path works end to end.** Both Leads chose Class 0 as directed. Both Tickets went from RUNNING straight to COMMIT_READY, with no review and no Ticket verification, integrated, passed their post-integration verification and the hidden test.
- **The refusals** were all correction steps: `aew evidence ingest` on the implementation report (both trials; the brief lists that command among the ingest commands) and, once, `aew verify ingest` in the wrong state. Each Lead recovered on its next step. The refusal messages now name the command that applies (audit X1); the brief is part of the registered runs and was not changed. The command log now records these refusals (audit T3).
- **Calibration stays open.** Unprompted, no Lead chose Class 0. The Leads' reasoning shows why: example anchoring, Class 0 read as insufficiently evidenced, and no operational eligibility criteria (§6.3). What should make Class 0 selectable is the designer's question Q10 (`future-work.md`).
- As registered, T1C0 is not compared with T1 for quality or cost: its instruction differs.
- A first attempt (2026-09-29) stopped before any model step, because the provider key had expired: USD 0, recorded.

## 7. Failures by registry class

Named with the classes in `docs/design/failure-class-registry.md` (amendment A1).

| Class | Count | Where |
|---|---|---|
| `INTENT_INGRESS_CORRUPTION` | 2 | Run 1 (before B1): a Ticket goal, and the Lead's `verify classify` reason. Bash expanded `$1`, so `-$15.00` became `-5.00`. None afterwards: 17 later stored texts containing `$` are intact. |
| `LOST_SUPERSESSION_LINEAGE` | 1 | Run 1: the replacement Ticket T-0003 records no link to T-0001 and T-0002. There is no way yet to record one (post-M3 P2). |
| `UNNECESSARY_STAKEHOLDER_INTERRUPTION` | 1 | Run 24: the Lead asked the operator for a takeover it did not need, because `aew resume` told it that it held no authority (M3-D10, fixed). |
| unmapped: **a goal met by changing its inputs** | 1 | Run 18 (T4, §6.2). A candidate registry class for the designer, perhaps an acceptance-input class. |
| unmapped: AEW defects | 2 | M3-D8 and M3-D9 (§8). |
| `HOST_WRITE_ESCAPE`, `FALSE_CONTAINMENT_CLAIM` | 0 | The AEW checkout was untouched in all 47 runs, and every run is labelled `workdir_separation_only`. The check covers only the AEW checkout, not the whole disk. |

## 8. AEW defects found and fixed in step 9

Each has a regression written before its fix.

| Defect | Found by | What happened | Fix | Commit |
|---|---|---|---|---|
| M3-D8 | free-model shakedown | After an implementer's run, the next action said "ingest it", but an implementation report is never ingested. The Lead tried `evidence ingest` and `review ingest` before finding the transition. The hints also still said "launch the implementer from its pack" after `--launch`, and "advance to REVIEW_PENDING" whatever the gates. | Each next action names its command: the transition the gates call for, or the review, verify or evidence ingest with its evidence id. | `be1d6b1` |
| M3-D9 | shakedown and run 1 | `--scope "a,b"` was stored as one glob that matches nothing, so correct changes were out of scope and the Lead recreated the Ticket. | A scope glob containing a comma is refused, with "repeat --scope". | `55412aa` |
| B1 (companion review) | run 1 | Shell interpolation corrupted the authored goal and reason (§7). | `--fields FILE\|-` on every command; guidance for Leads and roles; the Scenario G corpus stored byte for byte. | `f18a74c` |
| M3-D10 | T6 rerun | Inside a Lead session, `aew resume` told the Lead that "this session must not act as Lead". The Lead obeyed and stopped. | Resume asks the session's broker (`lead.whoami`) and says that this session holds Lead authority, or that its broker does not. | `61ac19d` |

Also from the companion review: **B2**, the `workdir_separation_only` label on runs and in `doctor`, and **B3**, registry names (`f18a74c`).

## 9. Defects in the evaluation itself

- **A billing failure.** The first paid attempt found the API account without credit: every turn failed at the provider, at USD 0. The driver nudged twice anyway. It now stops on provider errors (`8b95a10`), and the attempt is not in the results.
- **The T6 trigger** ("a role run running for 60 s") never fired with Luna, whose runs finish sooner. Two runs became T2 repeats, costing USD 0.067. Fixed by amendment A2 (`6069ca7`).
- **Results line endings** were CRLF in the first two records; fixed (`fe64ded`).

## 10. Safety and cost

**Safety,** in all 50 dogfood runs (47, plus the three T1C0 attempts of amendment A3):
- no AEW credential string in any file the run left: the whole scratch tree, including OpenCode's databases;
- the provider key's value in no file;
- the AEW checkout untouched.

The model-comparison trials ran under the live lane's own checks: credential scan, key scan and isolation guard, all passed.

**Every dollar:**

| Item | USD |
|---|---|
| Luna, AEW mode (15 runs, including the pre-hardening T1, the two T6 T2-repeats and the stalled T6) | 0.544 |
| Luna, raw mode (10 runs) | 0.058 |
| Sol, AEW mode (12 runs) | 4.618 |
| Sol, raw mode (10 runs) | 0.530 |
| Model comparison, A (3 trials) | 0.196 |
| Model comparison, B (3 trials) | 0.132 |
| The attempt without credit | 0.000 |
| T1C0, the Class 0 path (A3): 2 trials, plus an attempt stopped by an expired key at USD 0 | 0.033 |
| **Total** (OpenCode's figures; OpenAI's bill may differ slightly) | **6.111** |

About USD 0.07 was spent on runs that measured less than intended (the two untriggered T6 runs). A few cents went to Lead steps lost to defects now fixed.

## 11. Limits of this evaluation

- **Ceiling effect.** Both models solved every task in plain OpenCode, so the tasks could not show AEW improving correctness. They could only show it matching it, or harming it (T4). The tasks were chosen to fit a USD 10 budget, and they are small: a 200-line project, single-concern changes.
- **Two trials per cell.** Differences of one run, such as T4 on Luna, are signals, not rates.
- **The Lead was headless and briefed.** The brief stands in for AEW skills and the operator's presence. The operator-driven TUI session (step 9's remaining item) tests the interactive case.
- **The raw baseline was favoured on T5.** It was told to review and fix, which a real single-session user might not do.
- **The hidden tests measure the stated objective only.** Sol's reviewers caught a large-amount precision defect that no hidden test measures, so AEW gets no credit for it here.
- **Isolation is workdir separation only.** All work was on scratch repositories (companion review P1).

## 12. For the designer

1. **What this suggests to test next.** AEW's quality claim needs tasks where one model session fails or regresses without independent checks: longer multi-Ticket work, ambiguous objectives, defects subtle enough that a single session misses them, and real repositories (after containment, P1). This dogfood measured the price of AEW's rigour, which is about 7× on small tasks, but it could not measure the benefit.
2. **T4.** Should goals reference only unchanged inputs? Should the data that goals refer to be protected by default? Should reviewers flag changes to acceptance inputs? Is a new registry class warranted? (`future-work.md` O3.)
3. **The Lead's cost** (about 40%). Much of it is waiting in slices. A push-style wait, or the coordination design's event delivery, would cut it (`future-work.md` O4).
   - **Correction (2026-09-29):** waiting is 12% of the Lead's steps; the cost is the workflow choreography (§6.3; `m3-audit-findings.md` L1). The Lead workflow efficiency design (`future-work.md` F15) addresses it; a push-style wait remains M4 work.
4. **Class choice.** Every Lead chose Class 1 or 2 for a one-line fix. That fits fail-closed classification (F6), and it is the ceremony cost the designer is choosing.
5. **Evidence for P2 and P3** (supersession lineage; fail-closed `verify classify`). In run 1 the Lead classified a verifier-found plan defect correctly, as the heavier `PLAN_OR_DESIGN_DEFECT`, without any rule forcing it.

## 13. Reproduce

```
python eval/m3/dogfood/dogfood.py selfcheck
python eval/m3/dogfood/dogfood.py run T4 --mode aew --model openai/gpt-5.6-luna#medium
python eval/m3/dogfood/dogfood.py run T4 --mode raw --model openai/gpt-6-sol#medium
AEW_LIVE_PROVIDER_KEY_ENV=OPENAI_API_KEY AEW_LIVE_OPENCODE_MODEL=openai/gpt-5.6-luna#medium \
  AEW_LIVE_ROUTING=implementer=openai/gpt-5.6-luna#medium,reviewer=openai/gpt-6-sol#medium,verifier=openai/gpt-6-sol#medium \
  AEW_LIVE_MODEL_TRIALS=3 pytest --live tests/live/test_opencode_model_live.py -k seeded_defect -p no:xdist
```

`OPENAI_API_KEY` must be set in the environment. Only its name is ever configured.
